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

def build_standard_compilation_command(
    video_paths: List[str],
    output_path: str,
    logo_path: str = None,
    intro_path: str = None,
    end_packaging_path: str = None,
    enable_4k: bool = False
) -> List[str]:
    """
    Build FFmpeg command for standard video compilation.

    Args:
        video_paths: List of video file paths
        output_path: Output file path
        logo_path: Optional logo overlay path
        intro_path: Optional intro video path
        end_packaging_path: Optional end packaging video path
        enable_4k: Force 4K output resolution
    """
    cmd = ['ffmpeg']

    # Input files
    all_inputs = []

    if intro_path:
        all_inputs.append(intro_path)

    all_inputs.extend(video_paths)

    if end_packaging_path:
        all_inputs.append(end_packaging_path)

    # Add inputs to command
    for input_path in all_inputs:
        cmd.extend(['-i', input_path])

    # Add logo as overlay if specified
    if logo_path:
        cmd.extend(['-i', logo_path])

    # Build filter complex
    filters = []
    current_index = 0

    # Target resolution
    target_width = 3840 if enable_4k else 1920
    target_height = 2160 if enable_4k else 1080

    # Scale and pad each input video
    for i in range(len(all_inputs)):
        filters.append(
            f"[{i}:v]scale={target_width}:{target_height}:"
            f"force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2[v{i}]"
        )

    # Concatenate videos
    concat_inputs = ''.join([f"[v{i}]" for i in range(len(all_inputs))])
    filters.append(f"{concat_inputs}concat=n={len(all_inputs)}:v=1:a=1[outv][outa]")

    # Add logo overlay if specified
    if logo_path:
        logo_index = len(all_inputs)
        filters.append(
            f"[outv][{logo_index}:v]overlay=W-w-10:10[finalv]"
        )
        video_output = "[finalv]"
    else:
        video_output = "[outv]"

    # Join filters
    filter_complex = ';'.join(filters)
    cmd.extend(['-filter_complex', filter_complex])

    # Map output
    cmd.extend(['-map', video_output])
    cmd.extend(['-map', '[outa]'])

    # Output encoding settings
    cmd.extend([
        '-c:v', 'libx264',
        '-preset', 'medium',
        '-crf', '23',
        '-c:a', 'aac',
        '-b:a', '192k',
        '-movflags', '+faststart',
        '-y',  # Overwrite output
        output_path
    ])

    return cmd

def build_4k_compilation_command(
    video_paths: List[str],
    output_path: str,
    logo_path: str = None,
    stretch_to_4k: bool = False
) -> List[str]:
    """
    Build FFmpeg command for 4K video compilation.
    Uses higher quality settings and handles 4K resolution properly.
    """
    cmd = ['ffmpeg']

    # Input files
    for path in video_paths:
        cmd.extend(['-i', path])

    if logo_path:
        cmd.extend(['-i', logo_path])

    # Build filters
    filters = []

    for i in range(len(video_paths)):
        if stretch_to_4k:
            # Force upscale to 4K
            filters.append(
                f"[{i}:v]scale=3840:2160:flags=lanczos[v{i}]"
            )
        else:
            # Maintain aspect ratio, pad if needed
            filters.append(
                f"[{i}:v]scale=3840:2160:force_original_aspect_ratio=decrease,"
                f"pad=3840:2160:(ow-iw)/2:(oh-ih)/2[v{i}]"
            )

    # Concatenate
    concat_inputs = ''.join([f"[v{i}]" for i in range(len(video_paths))])
    filters.append(f"{concat_inputs}concat=n={len(video_paths)}:v=1:a=1[outv][outa]")

    # Logo overlay
    if logo_path:
        logo_index = len(video_paths)
        filters.append(f"[outv][{logo_index}:v]overlay=W-w-20:20[finalv]")
        video_output = "[finalv]"
    else:
        video_output = "[outv]"

    filter_complex = ';'.join(filters)
    cmd.extend(['-filter_complex', filter_complex])

    cmd.extend(['-map', video_output])
    cmd.extend(['-map', '[outa]'])

    # 4K encoding settings (higher quality)
    cmd.extend([
        '-c:v', 'libx264',
        '-preset', 'slow',  # Better quality for 4K
        '-crf', '21',  # Higher quality
        '-c:a', 'aac',
        '-b:a', '256k',  # Higher audio bitrate
        '-movflags', '+faststart',
        '-y',
        output_path
    ])

    return cmd


def build_unified_compilation_command(
    job_items: List[Dict],
    output_path: str,
    enable_4k: bool = False
) -> List[str]:
    """
    Build FFmpeg command for unified sequence compilation.
    Supports intro, videos, transitions, outro, and images.

    Args:
        job_items: List of job items from job_items table (ordered by position)
        output_path: Output file path
        enable_4k: Force 4K output resolution

    Returns:
        FFmpeg command as list of strings
    """
    cmd = ['ffmpeg']

    inputs = []
    filter_complex = []

    # Target resolution
    target_width = 3840 if enable_4k else 1920
    target_height = 2160 if enable_4k else 1080

    # Process each item
    for i, item in enumerate(job_items):
        item_type = item['item_type']
        path = item['path']

        if item_type == 'image':
            # Image as video segment
            duration = item.get('duration', 5)
            inputs.extend([
                '-loop', '1',
                '-t', str(duration),
                '-i', path
            ])

            # Scale image and add padding
            filter_complex.append(
                f"[{i}:v]scale={target_width}:{target_height}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,"
                f"fps=30[v{i}_scaled]"
            )

            # Create silent audio for image
            filter_complex.append(
                f"anullsrc=channel_layout=stereo:sample_rate=44100,"
                f"atrim=duration={duration}[a{i}]"
            )

            # Set video stream for logo overlay check
            video_stream = f"[v{i}_scaled]"

        else:
            # Regular video (intro, video, transition, outro)
            inputs.extend(['-i', path])

            # Scale and pad video
            filter_complex.append(
                f"[{i}:v]scale={target_width}:{target_height}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2[v{i}_scaled]"
            )

            video_stream = f"[v{i}_scaled]"

        # Add logo overlay for videos (not intro, outro, transition, image)
        if item_type == 'video' and item.get('logo_path'):
            logo_path = item['logo_path']
            inputs.extend(['-i', logo_path])
            logo_index = len(inputs) // 2 - 1  # Calculate actual input index

            filter_complex.append(
                f"{video_stream}[{logo_index}:v]overlay=W-w-10:10[v{i}_logo]"
            )
            video_stream = f"[v{i}_logo]"

        # Add text animation for videos
        if item_type == 'video' and item.get('text_animation_words'):
            words = item['text_animation_words']
            text_filter = build_text_animation_filter(video_stream, words, i)
            filter_complex.append(text_filter)
            video_stream = f"[v{i}_text]"

        # Rename final video stream
        filter_complex.append(f"{video_stream}null[v{i}]")

        # Handle audio stream
        if item_type == 'image':
            # Silent audio already created above
            pass
        else:
            # Use original audio
            filter_complex.append(f"[{i}:a]anull[a{i}]")

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


def build_text_animation_filter(input_stream: str, words: List[str], item_index: int) -> str:
    """
    Build drawtext filter for word-by-word text animation.

    Args:
        input_stream: Input video stream label (e.g., "[v0_logo]")
        words: List of words to animate
        item_index: Index of the item (for output labeling)

    Returns:
        FFmpeg drawtext filter string
    """
    # Simple text animation - show all words at once for now
    # TODO: Implement word-by-word reveal based on timing
    text = ' '.join(words)

    return (
        f"{input_stream}drawtext="
        f"fontfile=/Windows/Fonts/arial.ttf:"
        f"text='{text}':"
        f"fontsize=50:"
        f"fontcolor=yellow:"
        f"x=(w-text_w)/2:"
        f"y=h-100:"
        f"borderw=2:"
        f"bordercolor=black[v{item_index}_text]"
    )
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
from workers.ffmpeg_builder import build_standard_compilation_command, build_4k_compilation_command
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

        # Get job videos
        videos_result = supabase.table("job_videos").select("*").eq("job_id", job_id).order("position").execute()
        videos = videos_result.data

        if not videos:
            raise Exception("No videos found for job")

        logger.info(f"Processing {len(videos)} videos")

        # Step 1: Resolve video paths and copy to temp
        logger.info("Step 1: Copying files from SMB to temp")
        local_video_paths = []

        for i, video in enumerate(videos):
            # Get path (either from video_id or direct path)
            if video.get('video_id'):
                video_path = get_video_path_by_id(video['video_id'])
                if not video_path:
                    raise Exception(f"Video ID {video['video_id']} not found")
            else:
                video_path = video.get('video_path')

            if not video_path:
                raise Exception(f"No path for video at position {video['position']}")

            # Copy to temp
            normalized_path = normalize_path_for_server(video_path)
            filename = f"video_{video['position']}_{Path(normalized_path).name}"
            local_path = copy_file_to_temp(normalized_path, job_id, filename)
            local_video_paths.append(local_path)

            logger.info(f"  [{i+1}/{len(videos)}] Copied {Path(normalized_path).name}")

        # Get asset paths if needed
        logo_path = None
        intro_path = None
        end_path = None

        if job.get('has_logo'):
            logo_path = get_asset_path("logo", job['channel_name'])
            if logo_path:
                logo_path = copy_file_to_temp(normalize_path_for_server(logo_path), job_id, "logo.png")
                logger.info(f"  Logo copied")

        if job.get('has_intro'):
            intro_path = get_asset_path("intro", job['channel_name'])
            if intro_path:
                intro_path = copy_file_to_temp(normalize_path_for_server(intro_path), job_id, "intro.mp4")
                logger.info(f"  Intro copied")

        if job.get('has_end_packaging'):
            end_path = get_asset_path("end_packaging", job['channel_name'])
            if end_path:
                end_path = copy_file_to_temp(normalize_path_for_server(end_path), job_id, "end.mp4")
                logger.info(f"  End packaging copied")

        # Step 2: Calculate total duration
        logger.info("Step 2: Calculating total duration")
        total_duration = sum([get_video_duration(p) for p in local_video_paths])
        if intro_path:
            total_duration += get_video_duration(intro_path)
        if end_path:
            total_duration += get_video_duration(end_path)

        logger.info(f"  Total duration: {total_duration:.2f}s ({total_duration/60:.2f} min)")

        # Step 3: Build FFmpeg command
        logger.info("Step 3: Building FFmpeg command")
        output_filename = f"{job['channel_name']}_{job_id}.mp4"
        output_path = str(Path("temp") / job_id / output_filename)

        if job.get('enable_4k'):
            cmd = build_4k_compilation_command(
                local_video_paths,
                output_path,
                logo_path=logo_path,
                stretch_to_4k=True
            )
        else:
            cmd = build_standard_compilation_command(
                local_video_paths,
                output_path,
                logo_path=logo_path,
                intro_path=intro_path,
                end_packaging_path=end_path,
                enable_4k=False
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

        # Insert to BigQuery
        insert_compilation_result({
            "job_id": job_id,
            "username": username,
            "channel_name": job['channel_name'],
            "timestamp": datetime.utcnow().isoformat(),
            "video_count": len(videos),
            "total_duration": total_duration,
            "output_path": final_output_path,
            "worker_id": task.request.hostname,
            "features_used": [],  # TODO: Track features
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

# Determine which queue to use
if job.enable_4k:
    task = process_4k_compilation.delay(str(job_id))
elif job.text_animation_enabled or len(job.videos) > 50:
    task = process_gpu_compilation.delay(str(job_id))
else:
    task = process_standard_compilation.delay(str(job_id))

# Update response with task ID
return JobSubmitResponse(
    job_id=job_id,
    status="queued",
    message=f"Job submitted successfully to {task.queue}"
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

- [ ] Celery app configured
- [ ] Job logger implemented
- [ ] FFmpeg progress parser implemented
- [ ] FFmpeg command builder implemented
- [ ] Celery tasks implemented
- [ ] Job queuing integrated in API
- [ ] Redis running
- [ ] Workers start successfully
- [ ] Test job submission and processing
- [ ] Logs created correctly
- [ ] Progress updates in Supabase

---

## Next: Task 6
Implement queue management, history, and admin routes.
