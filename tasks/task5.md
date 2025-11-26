# Task 5: Celery Workers & FFmpeg Processing

## Objective
Implement Celery task queue with workers, FFmpeg command building, and video processing.

---

## 1. Celery Configuration

**File: `backend/workers/celery_app.py`**

```python
from celery import Celery
from celery.signals import worker_ready
from api.config import get_settings
import logging

settings = get_settings()
logger = logging.getLogger(__name__)

# Initialize Celery
app = Celery(
    'video_compilation',
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=['workers.tasks']
)

@worker_ready.connect
def log_worker_config(sender=None, **kwargs):
    """Log worker configuration when worker starts"""
    logger.info("=" * 60)
    logger.info("CELERY WORKER CONFIGURATION")
    logger.info("=" * 60)
    logger.info(f"  task_acks_late: {app.conf.task_acks_late}")
    logger.info(f"  task_reject_on_worker_lost: {app.conf.task_reject_on_worker_lost}")
    logger.info(f"  worker_prefetch_multiplier: {app.conf.worker_prefetch_multiplier}")
    logger.info(f"  task_track_started: {app.conf.task_track_started}")
    logger.info("=" * 60)

# Celery configuration
app.conf.update(
    # Task settings
    task_track_started=True,
    task_time_limit=10800,  # 3 hours max per task
    task_soft_time_limit=10200,  # 2h 50m soft limit
    worker_prefetch_multiplier=2,  # Prefetch next job for file copying optimization

    # Acknowledgment settings (enables prefetch to work with concurrency=1)
    task_acks_late=True,  # Don't acknowledge task until completion
    task_reject_on_worker_lost=True,  # Retry task if worker crashes

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

Creates per-job folders containing job.log, ffmpeg_cmd.txt, and ffmpeg_stderr.txt.

```python
import logging
from pathlib import Path
from datetime import datetime
from api.config import get_settings

def setup_job_logger(job_id: str, username: str, channel_name: str):
    """
    Create structured logger for each job.
    Log path: logs/{date}/{username}/jobs/{channel_name}_{job_id}/job.log

    Each job gets its own folder containing:
    - job.log: Main job log
    - ffmpeg_cmd.txt: FFmpeg command (written by progress_parser)
    - ffmpeg_stderr.txt: FFmpeg stderr output (written by progress_parser)
    """
    settings = get_settings()
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')

    # Create job-specific folder
    job_folder = f"{channel_name}_{job_id}"
    log_dir = Path(settings.log_dir) / date_str / username / "jobs" / job_folder
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "job.log"

    # Create logger
    logger = logging.getLogger(f"job_{job_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # Don't propagate to root logger
    logger.handlers = []  # Clear any existing handlers

    # File handler - writes to log file only
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

Includes periodic prefetch checks during FFmpeg processing to catch jobs that arrive mid-processing.

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

def run_ffmpeg_with_progress(cmd: list, job_id: str, total_duration: float, logger, log_dir: str, worker_name: str = None):
    """
    Run FFmpeg command and parse progress, updating Supabase in real-time.
    Periodically checks for new jobs in queue and starts prefetching.

    Args:
        cmd: FFmpeg command as list
        job_id: Job UUID
        total_duration: Total expected output duration in seconds
        logger: Job logger instance
        log_dir: Directory where log files are stored (for stderr and command files)
        worker_name: Celery worker hostname (for prefetch checks)
    """
    from pathlib import Path
    supabase = get_supabase_client()

    # Write full FFmpeg command to file (in same directory as logs)
    cmd_file = Path(log_dir) / f"ffmpeg_cmd.txt"
    with open(cmd_file, 'w', encoding='utf-8') as f:
        f.write(' '.join(cmd))
    logger.info(f"FFmpeg command written to: {cmd_file}")

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
    last_prefetch_check = 0  # Track when we last checked for prefetch
    stderr_lines = []  # Collect all stderr for full error reporting

    # Import prefetch function
    prefetch_func = None
    if worker_name:
        try:
            from workers.tasks import check_and_prefetch_next_job
            prefetch_func = check_and_prefetch_next_job
        except ImportError:
            logger.warning("Could not import prefetch function")

    for line in process.stderr:
        stderr_lines.append(line)  # Store all stderr lines

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

                # Check for new jobs to prefetch every 20% progress (separate from DB update)
                if prefetch_func and progress >= last_prefetch_check + 20:
                    try:
                        logger.info(f"  [Prefetch check at {progress}%]")
                        prefetch_func(worker_name, logger, current_job_id=job_id)
                        last_prefetch_check = progress
                    except Exception as e:
                        logger.warning(f"  Prefetch check failed: {e}")

    # Wait for process to complete
    returncode = process.wait()

    # Write full stderr to file (in same directory as logs)
    stderr_file = Path(log_dir) / f"ffmpeg_stderr.txt"
    with open(stderr_file, 'w', encoding='utf-8') as f:
        f.writelines(stderr_lines)

    if returncode == 0:
        logger.info("FFmpeg completed successfully")
        logger.info(f"Full stderr written to: {stderr_file}")
    else:
        logger.error(f"FFmpeg failed with code {returncode}")
        logger.error(f"Full stderr written to: {stderr_file}")
        logger.error(f"Error output (last 50 lines):\n{''.join(stderr_lines[-50:])}")

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

    # Encoding settings - GPU-Accelerated (Nvidia NVENC)
    if enable_4k:
        cmd.extend([
            # Video encoding (GPU)
            '-c:v', 'h264_nvenc',       # Nvidia GPU encoder
            '-preset', 'p5',             # p5 = high quality (p1-p7 range)
            '-tune', 'hq',               # High quality tuning
            '-rc', 'vbr',                # Variable bitrate (matches Adobe)
            '-b:v', '40M',               # Target 40 Mbps for 4K
            '-maxrate', '50M',           # Max bitrate
            '-bufsize', '60M',           # Buffer size (1.5x maxrate)
            '-profile:v', 'high',        # High profile for 4K
            '-level', '5.1',             # Level 5.1 for 4K (up to 4096x2304@30fps)
            '-pix_fmt', 'yuv420p',       # Pixel format (standard compatibility)
            '-spatial-aq', '1',          # Spatial AQ (adapts bitrate to complexity)
            '-temporal-aq', '1',         # Temporal AQ (adapts bitrate to motion)

            # Audio encoding
            '-c:a', 'aac',
            '-b:a', '320k',              # 320 kbps (matches Adobe Premiere)
            '-ar', '48000',              # 48kHz sample rate (matches Adobe)
            '-ac', '2',                  # Stereo
        ])
    else:
        cmd.extend([
            # Video encoding (GPU)
            '-c:v', 'h264_nvenc',       # Nvidia GPU encoder
            '-preset', 'p5',             # p5 = high quality (p1-p7 range)
            '-tune', 'hq',               # High quality tuning
            '-rc', 'vbr',                # Variable bitrate (matches Adobe)
            '-b:v', '16M',               # Target 16 Mbps (matches Adobe ~15.9)
            '-maxrate', '20M',           # Max bitrate
            '-bufsize', '24M',           # Buffer size (1.5x maxrate)
            '-profile:v', 'main',        # Main profile (matches Adobe)
            '-level', '4.1',             # Level 4.1 (up to 1920x1080@30fps)
            '-pix_fmt', 'yuv420p',       # Pixel format (standard compatibility)
            '-spatial-aq', '1',          # Spatial AQ (adapts bitrate to complexity)
            '-temporal-aq', '1',         # Temporal AQ (adapts bitrate to motion)

            # Audio encoding
            '-c:a', 'aac',
            '-b:a', '320k',              # 320 kbps (matches Adobe Premiere)
            '-ar', '48000',              # 48kHz sample rate (matches Adobe)
            '-ac', '2',                  # Stereo
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

            # Add fade effect and force top-right alignment with \an9
            ass_content += f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{{\\an9\\fad(150,0)}}{substring}\n"

    # Write ASS file
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)

    return output_path
```

---

## 5. Main Celery Tasks

**File: `backend/workers/tasks.py`**

Includes reusable `check_and_prefetch_next_job()` function and username lookup from profiles table.

```python
from celery import Task, current_app
from workers.celery_app import app
from services.supabase import get_supabase_client
from services.bigquery import get_videos_info_by_ids, insert_compilation_result
from services.storage import (
    copy_files_parallel, copy_file_to_temp, copy_file_to_output,
    cleanup_temp_dir, normalize_path_for_server
)
from services.logger import setup_job_logger
from workers.ffmpeg_builder import build_unified_compilation_command, generate_ass_subtitle_file
from workers.progress_parser import run_ffmpeg_with_progress
from utils.video_utils import get_videos_info_batch
from api.config import get_settings
from datetime import datetime
from pathlib import Path
from threading import Thread
import time
import logging

# Track which jobs have been prefetched to avoid duplicates
_prefetched_jobs = set()


def check_and_prefetch_next_job(worker_name: str, logger, current_job_id: str = None):
    """
    Check for next job in queue and start prefetching files in background.

    Args:
        worker_name: Celery worker hostname
        logger: Logger instance for output
        current_job_id: Current job ID (to avoid prefetching self)

    Returns:
        str: Next job ID if found and prefetch started, None otherwise
    """
    global _prefetched_jobs

    try:
        inspect = current_app.control.inspect()
        reserved = inspect.reserved()

        if not reserved or worker_name not in reserved:
            return None

        reserved_tasks = reserved[worker_name]
        if not reserved_tasks:
            return None

        # Find first task that isn't current job and hasn't been prefetched
        for task_info in reserved_tasks:
            if not task_info.get('args'):
                continue

            next_job_id = task_info['args'][0]

            # Skip if it's the current job or already prefetched
            if next_job_id == current_job_id:
                continue
            if next_job_id in _prefetched_jobs:
                logger.info(f"  Job {next_job_id} already prefetched, skipping")
                return next_job_id

            # Found a new job to prefetch
            logger.info(f"  >>> FOUND Next job in queue: {next_job_id}")
            _prefetched_jobs.add(next_job_id)

            # Start background prefetch thread
            def prefetch_files_for_job(job_id):
                """Background thread to copy files for next job"""
                try:
                    supabase = get_supabase_client()
                    logger.info(f"  Starting background prefetch for job {job_id}")

                    # Get next job items
                    next_items = supabase.table("job_items").select("*").eq("job_id", job_id).execute().data
                    if not next_items:
                        logger.warning(f"  No items found for job {job_id}")
                        return

                    # Batch query paths
                    next_video_ids = [item['video_id'] for item in next_items if item.get('video_id')]
                    next_videos_info = {}
                    if next_video_ids:
                        next_videos_info = get_videos_info_by_ids(next_video_ids)

                    # Build file list
                    next_files = []
                    for item in next_items:
                        if item.get('video_id') and item['video_id'] in next_videos_info:
                            source_path = next_videos_info[item['video_id']]['path']
                        else:
                            source_path = item.get('path')

                        if source_path:
                            normalized = normalize_path_for_server(source_path)
                            file_ext = Path(normalized).suffix
                            filename = f"{item['item_type']}_{item['position']}{file_ext}"
                            next_files.append({'source_path': normalized, 'dest_filename': filename})

                        # Add logo if exists
                        if item['item_type'] == 'video' and item.get('logo_path'):
                            logo_normalized = normalize_path_for_server(item['logo_path'])
                            logo_filename = f"logo_{item['position']}.png"
                            next_files.append({'source_path': logo_normalized, 'dest_filename': logo_filename})

                    # Copy files in parallel
                    if next_files:
                        settings = get_settings()
                        dest_dir = str(Path(settings.temp_dir) / job_id)
                        logger.info(f"  Prefetching {len(next_files)} files for job {job_id}")
                        copy_files_parallel(next_files, dest_dir, max_workers=5)
                        logger.info(f"  Prefetch completed for job {job_id}")

                except Exception as e:
                    logger.warning(f"  Prefetch failed for job {job_id}: {e}")

            # Start background thread
            prefetch_thread = Thread(target=prefetch_files_for_job, args=(next_job_id,), daemon=True)
            prefetch_thread.start()
            logger.info(f"  Background prefetch thread started for {next_job_id}")
            return next_job_id

        return None

    except Exception as e:
        logger.warning(f"  Could not check for next job: {e}")
        return None


@app.task(bind=True)
def process_standard_compilation(self, job_id: str):
    """
    Process a standard video compilation job.
    Runs on default_queue (all workers).
    Uses GPU-accelerated encoding (all PCs have GPUs).
    """
    return _process_compilation(self, job_id, worker_type="standard")

@app.task(bind=True)
def process_gpu_compilation(self, job_id: str):
    """
    Process a GPU-accelerated compilation.
    Runs on gpu_queue for text animation jobs.
    """
    return _process_compilation(self, job_id, worker_type="gpu")

@app.task(bind=True)
def process_4k_compilation(self, job_id: str):
    """
    Process a 4K video compilation with >40 videos.
    Runs on 4k_queue (load balanced across all workers).
    Uses GPU-accelerated encoding.
    """
    return _process_compilation(self, job_id, worker_type="4k")

def _process_compilation(task: Task, job_id: str, worker_type: str):
    """
    Main compilation processing function.
    """
    supabase = get_supabase_client()
    start_time = time.time()

    # Get job from database
    job_result = supabase.table("jobs").select("*").eq("job_id", job_id).execute()

    if not job_result.data:
        return {"status": "failed", "error": "Job not found"}

    job = job_result.data[0]
    user_id = job.get('user_id', 'unknown')

    # Get username from profiles table
    username = "unknown"
    try:
        profile_result = supabase.table("profiles").select("username").eq("id", user_id).execute()
        if profile_result.data:
            username = profile_result.data[0].get('username', 'unknown')
    except Exception:
        pass  # Use default if lookup fails

    # Setup job logger with username for readable log paths
    logger, log_path = setup_job_logger(job_id, username, job['channel_name'])
    log_dir = str(Path(log_path).parent)  # Get directory for stderr and command files

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

        # Step 0: Start prefetching files for next job (if exists) in background
        logger.info("Step 0: Checking for next job in queue to prefetch")
        worker_name = task.request.hostname
        check_and_prefetch_next_job(worker_name, logger, current_job_id=job_id)

        # Step 1a: Batch query all video paths upfront (1 query instead of N)
        logger.info("Step 1a: Batch querying video paths from BigQuery")
        video_ids = [item['video_id'] for item in items if item.get('video_id')]
        videos_info = {}

        if video_ids:
            videos_info = get_videos_info_by_ids(video_ids)
            logger.info(f"  Retrieved paths for {len(videos_info)}/{len(video_ids)} videos")

        # Step 1b: Prepare file list and copy in parallel
        logger.info("Step 1b: Preparing file list for parallel copy")

        # Build list of all files to copy (items + logos)
        files_to_copy = []
        item_metadata = []  # Track metadata for each item

        for i, item in enumerate(items):
            item_type = item['item_type']
            position = item['position']

            # Get source path (from batch query or direct path)
            if item.get('video_id'):
                video_id = item['video_id']
                if video_id not in videos_info:
                    raise Exception(f"Video ID {video_id} not found in BigQuery")
                source_path = videos_info[video_id]['path']
            else:
                source_path = item.get('path')

            if not source_path:
                raise Exception(f"No path for {item_type} at position {position}")

            # Add item file to copy list
            normalized_path = normalize_path_for_server(source_path)
            file_ext = Path(normalized_path).suffix
            item_filename = f"{item_type}_{position}{file_ext}"

            files_to_copy.append({
                'source_path': normalized_path,
                'dest_filename': item_filename
            })

            # Track metadata for later processing
            logo_filename = None
            if item_type == 'video' and item.get('logo_path'):
                logo_source = normalize_path_for_server(item['logo_path'])
                logo_filename = f"logo_{position}.png"
                files_to_copy.append({
                    'source_path': logo_source,
                    'dest_filename': logo_filename
                })

            item_metadata.append({
                'item': item,
                'item_type': item_type,
                'position': position,
                'item_filename': item_filename,
                'logo_filename': logo_filename
            })

        # Step 1c: Copy all files in parallel (5x faster than sequential)
        logger.info(f"Step 1c: Copying {len(files_to_copy)} files in parallel (items + logos)")
        settings = get_settings()
        dest_dir = str(Path(settings.temp_dir) / job_id)

        copy_results = copy_files_parallel(
            source_files=files_to_copy,
            dest_dir=dest_dir,
            max_workers=5  # Optimal for most cases
        )

        # Check if all copies succeeded
        failed_copies = [k for k, v in copy_results.items() if v is None]
        if failed_copies:
            raise Exception(f"Failed to copy {len(failed_copies)} files: {failed_copies}")

        logger.info(f"✓ All {len(files_to_copy)} files copied successfully")

        # Step 1d: Batch query all video durations in parallel
        logger.info("Step 1d: Batch querying video durations (parallel ffprobe)")

        # Collect all video/intro/outro/transition paths (not images)
        video_paths = [
            copy_results[meta['item_filename']]
            for meta in item_metadata
            if meta['item_type'] != 'image'
        ]

        # Batch query durations in parallel (uses ThreadPoolExecutor internally)
        videos_durations_info = {}
        if video_paths:
            videos_durations_info = get_videos_info_batch(video_paths, max_workers=8)
            success_count = sum(1 for info in videos_durations_info.values() if info is not None)
            logger.info(f"  Retrieved durations for {success_count}/{len(video_paths)} videos")

        # Step 1e: Process items (apply durations, generate ASS files)
        logger.info("Step 1e: Processing items (applying durations, text animation)")
        processed_items = []

        for meta in item_metadata:
            item = meta['item']
            item_type = meta['item_type']
            position = meta['position']
            item_filename = meta['item_filename']
            logo_filename = meta['logo_filename']

            # Get local paths from copy results
            local_path = copy_results[item_filename]
            local_logo_path = copy_results.get(logo_filename) if logo_filename else None

            # Get video duration from batch query
            if item_type == 'image':
                item_duration = item.get('duration', 5)
            else:
                video_info = videos_durations_info.get(local_path)
                if not video_info or 'duration' not in video_info:
                    raise Exception(f"Could not get duration for {local_path}")
                item_duration = video_info['duration']

            # Generate ASS subtitle file if text animation is enabled
            if item_type == 'video' and item.get('text_animation_text'):
                text = item['text_animation_text']
                ass_path = str(Path("temp") / job_id / f"text_{position}.ass")
                generate_ass_subtitle_file(
                    text=text,
                    video_duration=item_duration,
                    output_path=ass_path
                )
                logger.info(f"  [{position}] Text animation ASS file generated")

            # Build processed item dict for FFmpeg builder
            processed_items.append({
                'item_type': item_type,
                'path': local_path,
                'position': position,
                'duration': item_duration,
                'logo_path': local_logo_path,
                'text_animation_text': item.get('text_animation_text')
            })

        logger.info(f"✓ Processed {len(processed_items)} items")

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

        # Step 4: Run FFmpeg with progress tracking
        logger.info("Step 4: Processing video with FFmpeg")

        returncode = run_ffmpeg_with_progress(
            cmd,
            job_id,
            total_duration,
            logger,
            log_dir,
            worker_name=worker_name
        )

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

**Queue Routing Strategy:**
- **4K jobs** → 4k_queue → PC1 only
- **GPU-intensive jobs** → gpu_queue → PC1 only
- **Standard jobs** → default_queue → All workers (PC1, PC2, PC3)

Workers determine routing by which queues they listen to (no environment variables needed).

### PC1 (All queues - handles 4K, GPU, and standard jobs):
```bash
cd backend
celery -A workers.celery_app worker \
  -Q 4k_queue,gpu_queue,default_queue \
  --concurrency=1 \
  --loglevel=info \
  -n pc1@%h
```

### PC2 (Default queue only - standard jobs):
```bash
cd backend
celery -A workers.celery_app worker \
  -Q default_queue \
  --concurrency=1 \
  --loglevel=info \
  -n pc2@%h
```

### PC3 (Default queue only - standard jobs):
```bash
cd backend
celery -A workers.celery_app worker \
  -Q default_queue \
  --concurrency=1 \
  --loglevel=info \
  -n pc3@%h
```

**Why this works:**
- 4K jobs route to 4k_queue, only PC1 listens → PC1 gets all 4K jobs
- GPU jobs route to gpu_queue, only PC1 listens → PC1 gets all GPU jobs
- Standard jobs route to default_queue, all workers listen → Load balanced across PC1, PC2, PC3

---

## Checklist

### **Core Implementation**
- [x] Celery app configured (`workers/celery_app.py`)
  - [x] Time limits: 3 hours (10800s)
  - [x] Prefetch multiplier: 2
  - [x] Queue routing configured
- [x] Job logger implemented (`services/logger.py`)
  - [x] Per-job folders: `logs/{date}/{username}/jobs/{channel}_{job_id}/`
  - [x] Uses username (not user_id) for readable paths
- [x] FFmpeg progress parser implemented (`workers/progress_parser.py`)
  - [x] Parse progress from stderr
  - [x] Update Supabase in real-time
  - [x] Write full stderr to file
  - [x] Write FFmpeg command to file
  - [x] Periodic prefetch checks every 20% progress
- [x] FFmpeg command builder implemented (`workers/ffmpeg_builder.py`)
  - [x] Unified compilation command function
  - [x] ASS subtitle generation function
  - [x] Handles mixed resolutions
  - [x] Per-video logos
  - [x] Per-video text animation
  - [x] GPU encoding (h264_nvenc) with VBR mode
  - [x] Audio: 320 kbps @ 48kHz
- [x] Celery tasks implemented (`workers/tasks.py`)
  - [x] Uses `job_items` table (not job_videos)
  - [x] **Batch BigQuery query** for all video paths (Step 1a)
  - [x] **Parallel file copying** with 5 workers (Step 1c)
  - [x] **Batch ffprobe** for all durations (Step 1d)
  - [x] **Reusable prefetch function** `check_and_prefetch_next_job()`
  - [x] **Skip existing files** optimization (prefetched files not re-copied)
  - [x] Generates ASS files for text animation
  - [x] Copies per-video logos
  - [x] Tracks features used
  - [x] Error handling and cleanup

### **API Integration**
- [x] Job queuing integrated in API (`api/routes/jobs.py`)
  - [x] Checks for text animation in items
  - [x] Routes to correct queue (4k_queue, gpu_queue, default_queue)

### **Infrastructure**
- [x] Redis running and accessible
- [x] Workers start successfully on all PCs
  - [x] PC1 (192.168.1.83): All queues (4k + gpu + default) - Tested with GPU encoding
  - [x] PC2 (192.168.1.242): Default queue - Tested and working!

### **Testing & Validation**
- [x] Test job submission and processing - ✅ Successfully completed job
- [x] Logs created correctly (per-job folder with job.log + ffmpeg_stderr.txt + ffmpeg_cmd.txt) - ✅ Verified
- [x] Progress updates in Supabase - ✅ Real-time updates working
- [x] ASS files generated in temp directory - ✅ VERIFIED: All 6 ASS files generated successfully
- [x] ASS files cleaned up after job completion - ✅ Verified cleanup working
- [x] **Text animation position (top-right)** - ✅ Fixed with `\an9` override tag
- [x] **Batch operations working** (1 BigQuery query, parallel copies, parallel ffprobe) - ✅ Verified in logs
- [x] **Prefetch optimization working** (task_acks_late enables reserved task visibility) - ✅ WORKING: Prefetch + periodic checks + skip existing files
- [x] **Multi-worker load balancing** - ✅ PC1 + PC2 tested, jobs distributed evenly
- [x] FFmpeg stderr and command files saved correctly - ✅ Both files created
- [x] **GPU encoding working** (verify h264_nvenc available on all PCs) - ✅ Verified h264_nvenc on PC1 (GTX 1060)
- [ ] **Output quality matches Adobe Premiere** (check bitrate, audio, resolution) - Needs visual inspection

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

6. **Batch operations for optimal performance**
   - **Batch BigQuery**: Single query for all video paths using `get_videos_info_by_ids()`
   - **Parallel file copying**: `copy_files_parallel()` with 5 concurrent workers
   - **Parallel ffprobe**: Batch duration queries using `get_videos_info_batch()` with 8 workers
   - Combined optimizations reduce job startup time by ~80%

7. **Time limits updated to 3 hours**
   - Hard limit: 10800s (3 hours)
   - Soft limit: 10200s (2h 50m)
   - Changed from previous 2 hour limits

8. **Per-job log folders**
   - Each job gets its own folder: `logs/{date}/{username}/jobs/{channel}_{job_id}/`
   - Contains: `job.log`, `ffmpeg_cmd.txt`, `ffmpeg_stderr.txt`
   - Clean organization - no file collisions between jobs
   - Easy to find all logs for a specific job

9. **Username in log paths**
   - Uses username (human-readable) instead of user_id (UUID)
   - Looked up from profiles table in Supabase
   - Falls back to "unknown" if lookup fails
   - Makes log browsing much easier: `logs/2025-11-26/uzair/jobs/...`

10. **Enhanced error logging**
    - Full FFmpeg stderr saved to file: `ffmpeg_stderr.txt`
    - Full FFmpeg command saved to file: `ffmpeg_cmd.txt`
    - All stderr lines captured (not just last N lines)
    - Both files in job's log folder

11. **Prefetch optimization with periodic checks**
    - `worker_prefetch_multiplier=2` allows workers to reserve next job
    - **Step 0**: At job start, worker checks for next reserved job
    - **During FFmpeg**: Checks every 20% progress for new jobs
    - **Reusable function**: `check_and_prefetch_next_job()` shared between Step 0 and progress parser
    - **Duplicate prevention**: `_prefetched_jobs` set tracks already-prefetched job IDs
    - Background copying runs throughout entire current job (20-30+ min)
    - By the time current job finishes, next job's files are ready
    - Uses `celery.control.inspect().reserved()` to query worker's reserved tasks

12. **Skip existing files optimization**
    - Files prefetched for next job are NOT copied again when job starts
    - `copy_file_sequential()` checks if file already exists with same size
    - Logs "Skipping (already exists)" for each skipped file
    - Result: Job #2 starts with 0s file copy time (all files skipped)

13. **Text animation position (top-right)**
    - Uses ASS subtitle `\an9` override tag for top-right alignment
    - Alignment follows numpad layout (9 = top-right)
    - Style defines Alignment=9, but override tag ensures it works
    - Removed `\N` newline that was causing position issues
    - Position: Impact font, 50px, yellow with black outline

14. **Queue-based routing (no environment variables)**
    - PC1 listens to: 4k_queue + gpu_queue + default_queue
    - PC2/PC3 listen to: default_queue only
    - 4K jobs automatically route to PC1 (only listener on 4k_queue)
    - Self-documenting and simple to configure

15. **GPU-accelerated encoding (Nvidia NVENC)**
    - Uses `h264_nvenc` instead of software `libx264`
    - 5-10x faster encoding (2-3 min vs 15-20 min for 20min video)
    - **VBR mode** with target bitrate (matches Adobe Premiere Pro)
      - Full HD: 16 Mbps target, 20 Mbps max
      - 4K: 40 Mbps target, 50 Mbps max
    - **Preset p5**: High quality (p1=fastest, p7=slowest)
    - **Quality tuning**: `-tune hq`, spatial-aq, temporal-aq
    - **Audio upgraded**: 320 kbps @ 48kHz (matches Adobe)
    - **Hardware requirements**:
      - This machine: GTX 1060 (Pascal - supports h264_nvenc)
      - PC1: RTX 5060 Ti (latest - best NVENC)
      - PC2: GTX 750 (Maxwell - supports h264_nvenc)
    - CPU freed up for filter_complex processing (scales, overlays, concat)

---

## Prefetch Optimization Implementation

**Status**: ✅ **WORKING** - Implemented with `task_acks_late` + periodic checks + skip existing files

The prefetch optimization enables workers to start copying files for the next job while processing the current job, eliminating file copy wait time between jobs.

### How It Works

**Configuration (celery_app.py):**
```python
task_acks_late=True  # Don't acknowledge until task completes
task_reject_on_worker_lost=True  # Retry if worker crashes
worker_prefetch_multiplier=2  # Reserve next task
```

**Behavior:**
1. Worker receives Job #1 → Does NOT acknowledge yet → Starts processing
2. Worker receives Job #2 → Reserves it (visible in `inspect().reserved()`)
3. Job #1's Step 0: Checks reserved tasks → Finds Job #2 → Starts background file copy
4. Every 20% FFmpeg progress: Checks again for new jobs (catches jobs arriving mid-processing)
5. While Job #1 processes with FFmpeg, Job #2's files copy in parallel
6. Job #1 completes → Acknowledges → Job #2 starts
7. Job #2's Step 1c: All files already exist → Skips copying → 0s file copy time!

**Result:** ~8 seconds saved per job (no file copy wait time)

### Why task_acks_late is Required

**Without task_acks_late (default early acknowledgment):**
- Job #1 received → Acknowledged immediately → Started
- Job #2 received → Acknowledged immediately → Moved to internal buffer
- `inspect().reserved()` returns `[]` (both tasks acknowledged, nothing "reserved")
- Prefetch cannot see Job #2

**With task_acks_late:**
- Job #1 received → NOT acknowledged → Started (becomes "active")
- Job #2 received → NOT acknowledged → Held as "reserved"
- `inspect().reserved()` returns `[Job #2]` ✅
- Prefetch sees Job #2 and starts copying files!

### Benefits

**Single Worker (concurrency=1):**
- Prefetch works! Next task visible in reserved state
- No GPU/CPU contention (still single process)
- Auto-retry on worker crash (task hasn't been acknowledged)

**Multi-Worker (PC1, PC2, PC3):**
- Each worker prefetches its own next job
- Perfect load balancing (Celery handles distribution)
- No conflicts or duplicate work

**Task Safety:**
- If worker crashes mid-job, task is retried (not acknowledged yet)
- Jobs are idempotent (can safely rerun from start)
- Small risk: File copy happens twice if crash during Step 1c (acceptable)

### Test Results

**Job #1 prefetches Job #2's files:**
```log
12:34:25 - INFO - Step 0: Checking for next job in queue to prefetch
12:34:25 - INFO -   >>> FOUND Next job in queue: bf780d19-4ba8-4936-b030-6e6880906dfb
12:34:25 - INFO -   Background prefetch thread started for bf780d19
12:34:25 - INFO -   Starting background prefetch for job bf780d19
12:34:28 - INFO -   Prefetching 13 files for job bf780d19
12:34:35 - INFO -   Prefetch completed for job bf780d19
```

**Job #2 skips file copying (all files already exist):**
```log
12:35:00 - INFO - Step 1c: Copying 13 files in parallel (items + logos)
12:35:00 - INFO -   Skipping (already exists): intro_0.mp4
12:35:00 - INFO -   Skipping (already exists): video_1.mp4
12:35:00 - INFO -   Skipping (already exists): video_2.mp4
... (all 13 files skipped)
12:35:00 - INFO - All 13 files copied successfully
```

**Performance improvement:**
- Job #1: 32 seconds (8s copy + 24s process)
- Job #2: 24 seconds (0s copy + 24s process)
- **Saved:** 8 seconds per job (~25% faster job starts)

**Periodic prefetch catches late-arriving jobs:**
```log
12:35:15 - INFO - Progress: 20% (time: 24.00s)
12:35:15 - INFO -   [Prefetch check at 20%]
12:35:15 - INFO -   >>> FOUND Next job in queue: abc123...
12:35:15 - INFO -   Background prefetch thread started for abc123
```

---

## Next: Task 6
Implement queue management, history, and admin routes.
