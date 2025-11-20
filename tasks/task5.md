# Task 5: Celery Workers & FFmpeg Processing

## Objective
Implement Celery task queue with workers, FFmpeg command building, and video processing.

---

## 1. Celery Configuration

**File: `backend/workers/celery_app.py`**

```python
from celery import Celery
from api.config import get_settings

settings = get_settings()

# Initialize Celery
app = Celery(
    'video_compilation',
    broker=settings.redis_url,
    backend=settings.redis_url
)

# Celery configuration
app.conf.update(
    # Task settings
    task_track_started=True,
    task_time_limit=7200,  # 2 hours max per task
    task_soft_time_limit=6600,  # 1h 50m soft limit
    worker_prefetch_multiplier=1,  # One job at a time per worker

    # Result settings
    result_expires=86400,  # Keep results for 24 hours

    # Routing
    task_routes={
        'workers.tasks.process_4k_compilation': {'queue': '4k_queue'},
        'workers.tasks.process_gpu_compilation': {'queue': 'gpu_queue'},
        'workers.tasks.process_standard_compilation': {'queue': 'default_queue'},
    },

    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)
```

---

## 2. Job Logger

**File: `backend/services/logger.py`**

```python
import logging
from pathlib import Path
from datetime import datetime
from api.config import get_settings

def setup_job_logger(job_id: str, username: str, channel_name: str):
    """
    Create structured logger for each job.
    Log path: logs/{date}/{username}/jobs/{channel_name}_{job_id}.log
    """
    settings = get_settings()
    date_str = datetime.now().strftime('%Y-%m-%d')
    log_dir = Path(settings.log_dir) / date_str / username / "jobs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"{channel_name}_{job_id}.log"

    # Create logger
    logger = logging.getLogger(f"job_{job_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # Don't propagate to root

    # Remove existing handlers
    logger.handlers = []

    # File handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)

    # Formatter (simple, not verbose)
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger, str(log_file)
```

---

## 3. FFmpeg Progress Parser

**File: `backend/workers/progress_parser.py`**

```python
import re
import subprocess
from services.supabase import get_supabase_client

def parse_ffmpeg_progress(line: str) -> dict:
    """
    Parse FFmpeg stderr output for progress information.

    Returns dict with:
        - current_time: seconds processed
        - fps: current fps
        - speed: processing speed multiplier
    """
    result = {}

    # Parse time: time=00:01:23.45
    time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
    if time_match:
        h, m, s = time_match.groups()
        result['current_time'] = int(h)*3600 + int(m)*60 + float(s)

    # Parse fps: fps=30
    fps_match = re.search(r'fps=\s*(\d+)', line)
    if fps_match:
        result['fps'] = int(fps_match.group(1))

    # Parse speed: speed=1.5x
    speed_match = re.search(r'speed=\s*(\d+\.?\d*)x', line)
    if speed_match:
        result['speed'] = float(speed_match.group(1))

    return result

def run_ffmpeg_with_progress(cmd: list, job_id: str, total_duration: float, logger):
    """
    Run FFmpeg command and parse progress, updating Supabase in real-time.

    Args:
        cmd: FFmpeg command as list
        job_id: Job UUID
        total_duration: Total expected output duration in seconds
        logger: Job logger instance
    """
    supabase = get_supabase_client()

    logger.info(f"Starting FFmpeg process")
    logger.info(f"Expected output duration: {total_duration:.2f}s")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1
    )

    last_progress = 0

    for line in process.stderr:
        # Parse progress
        parsed = parse_ffmpeg_progress(line)

        if 'current_time' in parsed:
            current_time = parsed['current_time']
            progress = int((current_time / total_duration) * 100)
            progress = min(progress, 99)  # Never show 100% until done

            # Only update if progress changed by at least 1%
            if progress > last_progress:
                try:
                    supabase.table('jobs').update({
                        'progress': progress,
                        'status': 'processing'
                    }).eq('job_id', job_id).execute()

                    logger.info(f"Progress: {progress}% (time: {current_time:.2f}s)")
                    last_progress = progress
                except Exception as e:
                    logger.error(f"Failed to update progress: {e}")

    # Wait for process to complete
    returncode = process.wait()

    if returncode == 0:
        logger.info("FFmpeg completed successfully")
    else:
        stderr = process.stderr.read() if process.stderr else ""
        logger.error(f"FFmpeg failed with code {returncode}")
        logger.error(f"Error output: {stderr}")

    return returncode
```

---

## 4. FFmpeg Command Builder

**File: `backend/workers/ffmpeg_builder.py`**

```python
from typing import List, Dict
from pathlib import Path


def build_unified_compilation_command(
    job_items: List[Dict],
    output_path: str,
    job_id: str,
    enable_4k: bool = False
) -> List[str]:
    """
    Build FFmpeg command for unified sequence compilation.
    Handles mixed resolutions, per-video logos, and per-video text animation.

    Features:
    - Scales and pads videos/images to target resolution (maintains aspect ratio)
    - Adds black padding for 16:9 ratio
    - Supports per-video logos (overlaid at top-right)
    - Supports per-video text animation using ASS subtitles
    - Processes all item types: intro, video, transition, outro, image

    Args:
        job_items: List of job items from job_items table (ordered by position)
        output_path: Output file path
        job_id: Job ID (for temp ASS file paths)
        enable_4k: Force 4K output resolution (default: Full HD)

    Returns:
        FFmpeg command as list of strings
    """
    cmd = ['ffmpeg']

    # Track input index separately (since logos and ASS files add extra inputs)
    input_index = 0
    item_input_indices = []  # Maps item position to its input index

    # Target resolution
    target_width = 3840 if enable_4k else 1920
    target_height = 2160 if enable_4k else 1080

    filter_complex = []

    # First pass: Add all video/image inputs
    for i, item in enumerate(job_items):
        item_type = item['item_type']
        path = item['path']

        if item_type == 'image':
            # Image as video segment
            duration = item.get('duration', 5)
            cmd.extend([
                '-loop', '1',
                '-t', str(duration),
                '-i', path
            ])
        else:
            # Regular video (intro, video, transition, outro)
            cmd.extend(['-i', path])

        item_input_indices.append(input_index)
        input_index += 1

    # Second pass: Process each item with filters
    for i, item in enumerate(job_items):
        item_type = item['item_type']
        item_input_idx = item_input_indices[i]

        if item_type == 'image':
            # Scale image and add padding
            duration = item.get('duration', 5)
            filter_complex.append(
                f"[{item_input_idx}:v]scale={target_width}:{target_height}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black,"
                f"fps=30[v{i}_scaled]"
            )

            # Create silent audio for image
            filter_complex.append(
                f"anullsrc=channel_layout=stereo:sample_rate=44100,"
                f"atrim=duration={duration}[a{i}]"
            )

            video_stream = f"[v{i}_scaled]"

        else:
            # Regular video - scale and pad
            filter_complex.append(
                f"[{item_input_idx}:v]scale={target_width}:{target_height}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black[v{i}_scaled]"
            )

            video_stream = f"[v{i}_scaled]"

        # Add logo overlay for videos (not intro, outro, transition, image)
        if item_type == 'video' and item.get('logo_path'):
            logo_path = item['logo_path']
            cmd.extend(['-i', logo_path])
            logo_input_idx = input_index
            input_index += 1

            filter_complex.append(
                f"{video_stream}[{logo_input_idx}:v]overlay=W-w-10:10[v{i}_logo]"
            )
            video_stream = f"[v{i}_logo]"

        # Add text animation for videos using ASS subtitles
        if item_type == 'video' and item.get('text_animation_text'):
            text = item['text_animation_text']
            video_duration = item.get('duration', 0)

            # Generate ASS file path
            ass_file = f"temp/{job_id}/text_{item['position']}.ass"

            # Note: ASS file should be generated before calling this function
            # Using subtitles filter for ASS overlay
            filter_complex.append(
                f"{video_stream}subtitles={ass_file}:force_style='Alignment=9,MarginR=40,MarginV=40'[v{i}_text]"
            )
            video_stream = f"[v{i}_text]"

        # Finalize video stream
        filter_complex.append(f"{video_stream}null[v{i}]")

        # Handle audio stream
        if item_type == 'image':
            # Silent audio already created above
            pass
        else:
            # Use original audio
            filter_complex.append(f"[{item_input_idx}:a]anull[a{i}]")

    # Concatenate all segments
    video_inputs = ''.join([f"[v{i}]" for i in range(len(job_items))])
    audio_inputs = ''.join([f"[a{i}]" for i in range(len(job_items))])
    filter_complex.append(
        f"{video_inputs}{audio_inputs}concat=n={len(job_items)}:v=1:a=1[outv][outa]"
    )

    # Join filters
    cmd.extend(['-filter_complex', ';'.join(filter_complex)])

    # Map output streams
    cmd.extend(['-map', '[outv]', '-map', '[outa]'])

    # Encoding settings
    if enable_4k:
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', 'slow',
            '-crf', '21',
            '-c:a', 'aac',
            '-b:a', '256k',
        ])
    else:
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '192k',
        ])

    cmd.extend([
        '-movflags', '+faststart',
        '-y',
        output_path
    ])

    return cmd


def generate_ass_subtitle_file(
    text: str,
    video_duration: float,
    output_path: str,
    letter_delay: float = 0.1,
    cycle_duration: float = 20.0,
    visible_duration: float = 10.0
) -> str:
    """
    Generate ASS subtitle file for letter-by-letter text animation.

    Args:
        text: The text to animate
        video_duration: Duration of the video in seconds
        output_path: Path to save the .ass file
        letter_delay: Seconds between each letter appearing (default: 0.1)
        cycle_duration: Seconds between animation cycles (default: 20)
        visible_duration: How long full text stays visible (default: 10)

    Returns:
        Path to the generated ASS file
    """
    # ASS subtitle header
    ass_content = f"""[Script Info]
Title: Animated Text
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Impact,50,&H00FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,3,9,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Calculate number of cycles needed
    num_cycles = int(video_duration / cycle_duration) + 1

    def format_time(seconds):
        """Convert seconds to ASS time format (H:MM:SS.CS)"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    # Generate animated text for each cycle
    for cycle in range(num_cycles):
        cycle_start = cycle * cycle_duration

        # Letter-by-letter animation
        for i in range(1, len(text) + 1):
            substring = text[:i]
            start_time = cycle_start + (i - 1) * letter_delay

            # Last letter stays until visible_duration ends
            if i == len(text):
                end_time = cycle_start + visible_duration
            else:
                end_time = cycle_start + i * letter_delay

            # Stop if we exceed video duration
            if start_time >= video_duration:
                break

            start_str = format_time(start_time)
            end_str = format_time(min(end_time, video_duration))

            # Add fade effect for smooth appearance
            ass_content += f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{{\\fad(150,0)}}{substring}\\N\n"

    # Write ASS file
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)

    return output_path
```

---

## 5. Main Celery Tasks

**File: `backend/workers/tasks.py`**

```python
from celery import Task
from workers.celery_app import app
from services.supabase import get_supabase_client
from services.bigquery import get_video_path_by_id, get_asset_path, insert_compilation_result
from services.storage import copy_file_to_temp, copy_file_to_output, cleanup_temp_dir, normalize_path_for_server
from services.logger import setup_job_logger
from workers.ffmpeg_builder import build_unified_compilation_command, generate_ass_subtitle_file
from workers.progress_parser import run_ffmpeg_with_progress
from utils.video_utils import get_video_duration
from datetime import datetime
import time
from pathlib import Path

@app.task(bind=True)
def process_standard_compilation(self, job_id: str):
    """
    Process a standard video compilation job.
    Runs on default_queue (PC2, PC3 workers).
    """
    return _process_compilation(self, job_id, worker_type="standard")

@app.task(bind=True)
def process_gpu_compilation(self, job_id: str):
    """
    Process a GPU-accelerated compilation.
    Runs on gpu_queue (PC1 only).
    """
    return _process_compilation(self, job_id, worker_type="gpu")

@app.task(bind=True)
def process_4k_compilation(self, job_id: str):
    """
    Process a 4K video compilation.
    Runs on 4k_queue (PC1 only).
    """
    return _process_compilation(self, job_id, worker_type="4k")

def _process_compilation(task: Task, job_id: str, worker_type: str):
    """
    Main compilation processing function.
    """
    supabase = get_supabase_client()
    start_time = time.time()

    # Get job from database
    job_result = supabase.table("jobs").select("*, users(username)").eq("job_id", job_id).execute()

    if not job_result.data:
        return {"status": "failed", "error": "Job not found"}

    job = job_result.data[0]
    username = job['users']['username'] if job.get('users') else 'unknown'

    # Setup job logger
    logger, log_path = setup_job_logger(job_id, username, job['channel_name'])

    logger.info(f"=== Starting Compilation Job {job_id} ===")
    logger.info(f"Worker: {task.request.hostname} ({worker_type})")
    logger.info(f"Channel: {job['channel_name']}")

    try:
        # Update job status
        supabase.table('jobs').update({
            'status': 'processing',
            'started_at': datetime.utcnow().isoformat(),
            'worker_id': task.request.hostname,
            'queue_name': task.request.delivery_info.get('routing_key', 'unknown')
        }).eq('job_id', job_id).execute()

        # Get job items (unified sequence: intro, videos, transitions, outro, images)
        items_result = supabase.table("job_items").select("*").eq("job_id", job_id).order("position").execute()
        items = items_result.data

        if not items:
            raise Exception("No items found for job")

        logger.info(f"Processing {len(items)} items in sequence")

        # Step 1: Copy files to temp and prepare items
        logger.info("Step 1: Copying files from SMB to temp")
        processed_items = []

        for i, item in enumerate(items):
            item_type = item['item_type']
            position = item['position']

            logger.info(f"  [{i+1}/{len(items)}] Processing {item_type} at position {position}")

            # Get source path (either from video_id or direct path)
            if item.get('video_id'):
                source_path = get_video_path_by_id(item['video_id'])
                if not source_path:
                    raise Exception(f"Video ID {item['video_id']} not found")
            else:
                source_path = item.get('path')

            if not source_path:
                raise Exception(f"No path for {item_type} at position {position}")

            # Copy file to temp
            normalized_path = normalize_path_for_server(source_path)
            file_ext = Path(normalized_path).suffix
            filename = f"{item_type}_{position}{file_ext}"
            local_path = copy_file_to_temp(normalized_path, job_id, filename)

            # Get video duration for this item
            if item_type == 'image':
                item_duration = item.get('duration', 5)
            else:
                item_duration = get_video_duration(local_path)

            # Copy logo if this video has one
            local_logo_path = None
            if item_type == 'video' and item.get('logo_path'):
                logo_source = normalize_path_for_server(item['logo_path'])
                logo_filename = f"logo_{position}.png"
                local_logo_path = copy_file_to_temp(logo_source, job_id, logo_filename)
                logger.info(f"    → Logo copied for position {position}")

            # Generate ASS subtitle file if text animation is enabled
            if item_type == 'video' and item.get('text_animation_text'):
                text = item['text_animation_text']
                ass_path = str(Path("temp") / job_id / f"text_{position}.ass")
                generate_ass_subtitle_file(
                    text=text,
                    video_duration=item_duration,
                    output_path=ass_path
                )
                logger.info(f"    → Text animation ASS file generated for position {position}")

            # Build processed item dict for FFmpeg builder
            processed_items.append({
                'item_type': item_type,
                'path': local_path,
                'position': position,
                'duration': item_duration,
                'logo_path': local_logo_path,
                'text_animation_text': item.get('text_animation_text')
            })

            logger.info(f"    ✓ Copied {Path(normalized_path).name}")

        # Step 2: Calculate total duration
        logger.info("Step 2: Calculating total duration")
        total_duration = sum([item['duration'] for item in processed_items])
        logger.info(f"  Total duration: {total_duration:.2f}s ({total_duration/60:.2f} min)")

        # Step 3: Build FFmpeg command
        logger.info("Step 3: Building FFmpeg command")
        output_filename = f"{job['channel_name']}_{job_id}.mp4"
        output_path = str(Path("temp") / job_id / output_filename)

        cmd = build_unified_compilation_command(
            job_items=processed_items,
            output_path=output_path,
            job_id=job_id,
            enable_4k=job.get('enable_4k', False)
        )

        # Step 4: Run FFmpeg
        logger.info("Step 4: Processing video with FFmpeg")
        returncode = run_ffmpeg_with_progress(cmd, job_id, total_duration, logger)

        if returncode != 0:
            raise Exception(f"FFmpeg failed with return code {returncode}")

        # Step 5: Copy to output
        logger.info("Step 5: Copying output to SMB")
        final_output_path = copy_file_to_output(output_path, output_filename)
        logger.info(f"  Output: {final_output_path}")

        # Step 6: Update job as completed
        processing_time = time.time() - start_time
        logger.info(f"Step 6: Job completed in {processing_time:.2f}s")

        supabase.table('jobs').update({
            'status': 'completed',
            'progress': 100,
            'output_path': final_output_path,
            'final_duration': total_duration,
            'completed_at': datetime.utcnow().isoformat()
        }).eq('job_id', job_id).execute()

        # Count actual video items (not intro, outro, transitions, images)
        video_count = len([item for item in items if item['item_type'] == 'video'])

        # Track features used
        features_used = []
        if any(item.get('logo_path') for item in items):
            features_used.append('logo_overlay')
        if any(item.get('text_animation_text') for item in items):
            features_used.append('text_animation')
        if any(item['item_type'] == 'image' for item in items):
            features_used.append('image_slides')
        if job.get('enable_4k'):
            features_used.append('4k_output')

        # Insert to BigQuery
        insert_compilation_result({
            "job_id": job_id,
            "username": username,
            "channel_name": job['channel_name'],
            "timestamp": datetime.utcnow().isoformat(),
            "video_count": video_count,
            "total_duration": total_duration,
            "output_path": final_output_path,
            "worker_id": task.request.hostname,
            "features_used": features_used,
            "processing_time": processing_time,
            "status": "completed"
        })

        # Cleanup temp files
        cleanup_temp_dir(job_id)

        logger.info("=== Job Completed Successfully ===")

        return {
            "status": "completed",
            "output_path": final_output_path,
            "duration": total_duration,
            "processing_time": processing_time
        }

    except Exception as e:
        logger.error(f"=== Job Failed ===")
        logger.error(f"Error: {str(e)}")

        # Update job as failed
        supabase.table('jobs').update({
            'status': 'failed',
            'error_message': str(e),
            'completed_at': datetime.utcnow().isoformat()
        }).eq('job_id', job_id).execute()

        # Cleanup
        try:
            cleanup_temp_dir(job_id)
        except:
            pass

        return {
            "status": "failed",
            "error": str(e)
        }
```

---

## 6. Queue Job from API

Update `backend/api/routes/jobs.py` to queue the job:

```python
# Add this import at the top
from workers.tasks import process_standard_compilation, process_gpu_compilation, process_4k_compilation

# In submit_job function, after creating job in Supabase, add:

# Determine which queue to use based on job features
has_text_animation = any(
    item.get('text_animation_text')
    for item in request.items
    if item.item_type == 'video'
)
video_count = len([item for item in request.items if item.item_type == 'video'])

if request.enable_4k:
    # 4K jobs go to PC1 (4k_queue)
    task = process_4k_compilation.delay(str(job_id))
    queue_name = "4k_queue"
elif has_text_animation or video_count > 50:
    # GPU-intensive jobs go to PC1 (gpu_queue)
    task = process_gpu_compilation.delay(str(job_id))
    queue_name = "gpu_queue"
else:
    # Standard jobs distributed across all workers (default_queue)
    task = process_standard_compilation.delay(str(job_id))
    queue_name = "default_queue"

# Update response with task ID
return JobSubmitResponse(
    job_id=job_id,
    status="queued",
    message=f"Job submitted successfully to {queue_name}"
)
```

---

## 7. Start Workers

### PC1 (Master - All queues):
```bash
cd backend
celery -A workers.celery_app worker -Q 4k_queue,gpu_queue,default_queue --concurrency=1 --loglevel=info -n worker_pc1@%h
```

### PC2 (Worker - Default queue only):
```bash
cd backend
celery -A workers.celery_app worker -Q default_queue --concurrency=1 --loglevel=info -n worker_pc2@%h
```

### PC3 (Worker - Default queue only):
```bash
cd backend
celery -A workers.celery_app worker -Q default_queue --concurrency=1 --loglevel=info -n worker_pc3@%h
```

---

## Checklist

- [ ] Celery app configured (`workers/celery_app.py`)
- [ ] Job logger implemented (`services/logger.py`)
- [ ] FFmpeg progress parser implemented (`workers/progress_parser.py`)
- [ ] FFmpeg command builder implemented (`workers/ffmpeg_builder.py`)
  - [ ] Unified compilation command function
  - [ ] ASS subtitle generation function
- [ ] Celery tasks implemented (`workers/tasks.py`)
  - [ ] Uses `job_items` table (not job_videos)
  - [ ] Generates ASS files for text animation
  - [ ] Copies per-video logos
  - [ ] Tracks features used
- [ ] Job queuing integrated in API (`api/routes/jobs.py`)
  - [ ] Checks for text animation in items
  - [ ] Routes to correct queue (4k_queue, gpu_queue, default_queue)
- [ ] Redis running
- [ ] Workers start successfully on all PCs
- [ ] Test job submission and processing
- [ ] Logs created correctly (INFO and ERROR levels)
- [ ] Progress updates in Supabase
- [ ] ASS files generated in temp directory
- [ ] ASS files cleaned up after job completion

---

## Key Implementation Notes

### **Changes from Initial Design:**

1. **Uses `job_items` table** instead of `job_videos`
   - Supports intro, video, transition, outro, image types
   - Each item can have different logo and text animation

2. **Per-video logos**
   - Each video item can have its own `logo_path`
   - Logos only applied to `item_type == 'video'` (not intro/outro/transitions/images)
   - Logo overlaid at top-right corner (W-w-10:10)

3. **Text animation via ASS subtitles**
   - Generates `.ass` files dynamically for each video with text
   - Letter-by-letter animation with cycling
   - Fixed timing: letter_delay=0.1s, cycle=20s, visible=10s
   - Uses Impact font
   - Files stored in `temp/{job_id}/text_{position}.ass`

4. **Mixed resolution handling**
   - Videos/images can be any resolution (4K, Full HD, HD, etc.)
   - All scaled to target resolution (1920x1080 or 3840x2160)
   - Black padding maintains 16:9 aspect ratio
   - Uses `force_original_aspect_ratio=decrease` + `pad`

5. **Feature tracking**
   - Tracks: logo_overlay, text_animation, image_slides, 4k_output
   - Stored in BigQuery for analytics

---

## Next: Task 6
Implement queue management, history, and admin routes.
