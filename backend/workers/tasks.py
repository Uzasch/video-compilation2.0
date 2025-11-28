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
            'progress_message': 'Starting...',
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
        supabase.table('jobs').update({
            'progress_message': f'Copying {len(files_to_copy)} files...'
        }).eq('job_id', job_id).execute()

        settings = get_settings()
        dest_dir = str(Path(settings.temp_dir) / job_id)

        copy_results = copy_files_parallel(
            source_files=files_to_copy,
            dest_dir=dest_dir,
            max_workers=5,  # Optimal for most cases
            job_logger=logger
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
        supabase.table('jobs').update({
            'progress_message': 'Encoding video...'
        }).eq('job_id', job_id).execute()

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

        # Step 5: Copy to output (organized by username)
        logger.info("Step 5: Copying output to SMB")
        supabase.table('jobs').update({
            'progress_message': 'Copying output file...'
        }).eq('job_id', job_id).execute()

        final_output_path = copy_file_to_output(output_path, output_filename, username=username)
        logger.info(f"  Output: {final_output_path}")

        # Step 6: Update job as completed
        processing_time = time.time() - start_time
        logger.info(f"Step 6: Job completed in {processing_time:.2f}s")

        supabase.table('jobs').update({
            'status': 'completed',
            'progress': 100,
            'progress_message': 'Completed',
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
            "user_id": user_id,
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
            'progress_message': 'Failed',
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
