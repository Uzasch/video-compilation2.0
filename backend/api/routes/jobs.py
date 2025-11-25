from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from services.bigquery import get_videos_info_by_ids, get_all_channel_assets, get_production_path
from services.storage import normalize_paths
from services.supabase import get_supabase_client
from services.logger import setup_validation_logger
from utils.video_utils import get_videos_info_batch
from datetime import datetime
from uuid import uuid4
import shutil
import logging
from pathlib import Path
from celery import Celery

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize Celery client for worker stats (will be configured in Task 5)
# For now, create basic Celery app for inspection
celery_app = Celery('workers', broker='redis://redis:6379/0')

# Request/Response Models
class VerifyJobRequest(BaseModel):
    channel_name: str
    video_ids: List[str] = []      # Optional: video IDs to fetch from BigQuery
    manual_paths: List[str] = []   # Optional: manual paths user added

class JobItem(BaseModel):
    position: int
    item_type: str  # 'intro', 'video', 'transition', 'outro', 'image'
    video_id: Optional[str] = None
    title: Optional[str] = None
    path: Optional[str] = None
    path_available: Optional[bool] = False  # For API response only (not saved to DB during verify)
    logo_path: Optional[str] = None
    duration: Optional[float] = None
    resolution: Optional[str] = None
    is_4k: Optional[bool] = None
    text_animation_text: Optional[str] = None  # Text to animate on video
    error: Optional[str] = None  # Error message if path not available

class VerifyJobResponse(BaseModel):
    default_logo_path: Optional[str]
    total_duration: float
    items: List[JobItem]

class SubmitJobRequest(BaseModel):
    user_id: str
    channel_name: str
    enable_4k: bool
    items: List[JobItem]

class SubmitJobResponse(BaseModel):
    job_id: str
    status: str

class MoveToProductionRequest(BaseModel):
    custom_filename: Optional[str] = None


@router.post("/verify", response_model=VerifyJobResponse)
async def verify_job(request: VerifyJobRequest, user_id: str, max_workers: int = 8):
    """
    Smart verification endpoint - handles both bulk and single item verification.

    Use Cases:
    1. Initial bulk verification: video_ids=[...], manual_paths=[]
    2. Single manual path: video_ids=[], manual_paths=["V:\\video.mp4"]
    3. Mixed: video_ids=[...], manual_paths=[...]

    Flow:
    1. Batch query BigQuery for all video_ids (if any)
    2. Get intro/outro/logo from BigQuery
    3. Collect all paths to verify (intro, outro, videos, manual paths)
    4. Batch check all paths exist (single operation)
    5. Get durations for all available items
    6. Return verified sequence

    Returns:
    - default_logo_path: Channel's default logo
    - total_duration: Sum of all durations
    - items: Array with verification status
    """
    supabase = get_supabase_client()

    # Get username for logging
    user_result = supabase.table('profiles').select('username').eq('id', user_id).execute()
    username = user_result.data[0]['username'] if user_result.data else 'unknown'

    # Setup validation logger
    validation_logger, log_path = setup_validation_logger(username)

    validation_logger.info("=== Verification Request ===")
    validation_logger.info(f"User: {username}")
    validation_logger.info(f"Channel: {request.channel_name}")
    validation_logger.info(f"Video IDs: {len(request.video_ids)}")
    validation_logger.info(f"Manual Paths: {len(request.manual_paths)}")
    validation_logger.info("")

    items = []
    position = 1

    # Step 1: Get channel branding assets (batched - single query)
    validation_logger.info("Step 1: Fetching channel branding assets (batched)...")
    assets = get_all_channel_assets(request.channel_name)
    intro_path = assets['intro']
    outro_path = assets['outro']
    logo_path = assets['logo']

    if logo_path:
        validation_logger.info(f"  Logo: {logo_path}")
    if intro_path:
        validation_logger.info(f"  Intro: {intro_path}")
    if outro_path:
        validation_logger.info(f"  Outro: {outro_path}")
    validation_logger.info("")

    # Step 2: Batch query BigQuery for video IDs
    videos_info = {}
    if request.video_ids:
        validation_logger.info("Step 2: Fetching video info from BigQuery (batch query)...")
        videos_info = get_videos_info_by_ids(request.video_ids)
        validation_logger.info(f"  Found {len(videos_info)}/{len(request.video_ids)} videos in BigQuery")
        validation_logger.info("")

    # Step 3: Collect all paths for verification (ffprobe will determine availability)
    all_paths = []
    path_to_item_map = {}  # Map path → item info

    # Add intro
    if intro_path:
        all_paths.append(intro_path)
        path_to_item_map[intro_path] = {'type': 'intro', 'position': position}
        position += 1

    # Add videos from BigQuery
    for video_id in request.video_ids:
        if video_id in videos_info:
            path = videos_info[video_id]["path"]
            all_paths.append(path)
            path_to_item_map[path] = {
                'type': 'video',
                'position': position,
                'video_id': video_id,
                'title': videos_info[video_id]["title"]
            }
        else:
            # Video ID not in BigQuery - add placeholder
            path_to_item_map[f"missing_{video_id}"] = {
                'type': 'video',
                'position': position,
                'video_id': video_id,
                'title': f'Video {video_id}',
                'error': 'Video ID not found in BigQuery'
            }
        position += 1

    # Add manual paths
    for manual_path in request.manual_paths:
        all_paths.append(manual_path)
        path_to_item_map[manual_path] = {
            'type': 'transition',  # Assume transition (can be updated later)
            'position': position
        }
        position += 1

    # Add outro
    if outro_path:
        all_paths.append(outro_path)
        path_to_item_map[outro_path] = {'type': 'outro', 'position': position}

    # Step 3: Get video metadata for all paths (ffprobe = existence check + metadata)
    validation_logger.info("Step 3: Getting video info via ffprobe (existence + metadata)...")
    validation_logger.info(f"  Processing {len(all_paths)} paths with {max_workers} workers")

    # Normalize paths before passing to ffprobe
    normalized_paths = normalize_paths(all_paths)

    # Batch get video info - if ffprobe succeeds, file exists; if fails, file doesn't exist
    videos_info_batch = get_videos_info_batch(normalized_paths, max_workers=max_workers)

    # Map back to original paths
    path_video_info = {}
    for original, normalized in zip(all_paths, normalized_paths):
        path_video_info[original] = videos_info_batch.get(normalized)

    # Count available (ffprobe succeeded) vs unavailable (ffprobe failed)
    available_count = sum(1 for info in path_video_info.values() if info is not None)
    validation_logger.info(f"  Available: {available_count}/{len(all_paths)}")
    validation_logger.info("")

    # Step 6: Build items with verification results
    total_duration = 0.0
    missing_count = 0

    # Rebuild items in position order
    sorted_items = sorted(path_to_item_map.items(), key=lambda x: x[1]['position'])

    for path, item_info in sorted_items:
        # Handle missing video IDs
        if path.startswith("missing_"):
            items.append(JobItem(
                position=item_info['position'],
                item_type='video',
                video_id=item_info['video_id'],
                title=item_info['title'],
                path=None,
                path_available=False,
                logo_path=logo_path,
                error=item_info['error']
            ))
            missing_count += 1
            continue

        # Get video info - if ffprobe succeeded, file exists and we have metadata
        video_info = path_video_info.get(path)
        exists = video_info is not None

        duration = None
        resolution = None
        is_4k = None

        if video_info:
            duration = video_info['duration']
            resolution = f"{video_info['width']}x{video_info['height']}"
            is_4k = video_info['is_4k']
            total_duration += duration

        # Create JobItem
        item_type = item_info['type']

        item = JobItem(
            position=item_info['position'],
            item_type=item_type,
            video_id=item_info.get('video_id'),
            title=item_info.get('title', item_type.capitalize()),
            path=path,
            path_available=exists,
            duration=duration,
            resolution=resolution,
            is_4k=is_4k,
            logo_path=logo_path if item_type == 'video' else None
        )

        items.append(item)

        if not exists:
            missing_count += 1

    # Summary
    validation_logger.info("=== Verification Summary ===")
    validation_logger.info(f"Total items: {len(items)}")
    validation_logger.info(f"Available: {available_count}")
    validation_logger.info(f"Missing: {missing_count}")
    validation_logger.info(f"Total duration: {total_duration:.2f}s ({total_duration/60:.2f} min)")

    if missing_count == 0:
        validation_logger.info("Result: SUCCESS")
    elif missing_count < len(items):
        validation_logger.info(f"Result: PARTIAL - {missing_count} items need attention")
    else:
        validation_logger.info("Result: FAILED - All items missing")

    return VerifyJobResponse(
        default_logo_path=logo_path,
        total_duration=total_duration,
        items=items
    )


@router.post("/submit", response_model=SubmitJobResponse)
async def submit_job(request: SubmitJobRequest):
    """
    Submit compilation job with full sequence.

    Prerequisites:
    - All items already verified via /verify endpoint
    - No additional verification needed (already done)

    Flow:
    1. Validate all paths are available
    2. Create job record in jobs table
    3. Insert all items into job_items table
    4. Queue Celery task for processing

    Handles ALL item types:
    - intro/outro: Branding videos (no logo overlay)
    - video: Main content (with video_id from BigQuery OR manual path)
    - transition: Mid-packing videos (manual path only)
    - image: Uploaded images with custom duration
    """
    supabase = get_supabase_client()

    try:
        # 1. Validate all paths are available
        unavailable_items = [
            item for item in request.items
            if not item.path_available
        ]

        if unavailable_items:
            unavailable_positions = [item.position for item in unavailable_items]
            raise HTTPException(
                status_code=400,
                detail=f"Cannot submit job. Items at positions {unavailable_positions} have unavailable paths. Please verify paths first."
            )

        job_id = str(uuid4())

        # 2. Create job record
        total_duration = sum(item.duration for item in request.items if item.duration)

        job_data = {
            'job_id': job_id,
            'user_id': request.user_id,
            'channel_name': request.channel_name,
            'status': 'queued',
            'progress': 0,
            'progress_message': 'Job queued',
            'enable_4k': request.enable_4k,
            'default_logo_path': next((item.logo_path for item in request.items if item.logo_path), None),
            'final_duration': total_duration,
            'moved_to_production': False
        }

        result = supabase.table('jobs').insert(job_data).execute()

        if not result.data:
            raise Exception("Failed to create job in database")

        # 3. Insert all items into job_items table
        items_data = []
        for item in request.items:
            items_data.append({
                'job_id': job_id,
                'position': item.position,
                'item_type': item.item_type,
                'video_id': item.video_id,  # Only for videos from BigQuery
                'title': item.title,
                'path': item.path,
                # Note: path_available not saved to DB - only used in API responses
                'logo_path': item.logo_path,  # Per-video logo
                'duration': item.duration,
                'resolution': item.resolution,
                'is_4k': item.is_4k,
                'text_animation_text': item.text_animation_text
            })

        supabase.table('job_items').insert(items_data).execute()

        # 4. Queue Celery task - determine which queue based on job features
        from workers.tasks import (
            process_standard_compilation,
            process_4k_compilation,
            process_gpu_compilation
        )

        # Count video items
        video_count = len([item for item in request.items if item.item_type == 'video'])

        # Check if text animation is enabled on any video
        has_text_animation = any(
            item.text_animation_text
            for item in request.items
            if item.item_type == 'video'
        )

        # Route to appropriate queue:
        # 1. Text animation enabled → gpu_queue (GPU-intensive subtitle rendering)
        # 2. 4K enabled and >20 videos → 4k_queue
        # 3. 4K disabled and >40 videos → 4k_queue
        # 4. All other jobs → default_queue
        if has_text_animation:
            # Text animation jobs need GPU for subtitle rendering
            task = process_gpu_compilation.delay(job_id)
            queue_name = "gpu_queue"
        elif (request.enable_4k and video_count > 20) or (not request.enable_4k and video_count > 40):
            # Large jobs go to 4k_queue (load balanced across all workers)
            task = process_4k_compilation.delay(job_id)
            queue_name = "4k_queue"
        else:
            # Standard/small jobs go to default_queue
            task = process_standard_compilation.delay(job_id)
            queue_name = "default_queue"

        logger.info(f"Job {job_id} queued to {queue_name} (task_id: {task.id}, videos: {video_count}, 4k: {request.enable_4k}, text_animation: {has_text_animation})")

        return SubmitJobResponse(
            job_id=job_id,
            status='queued'
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit job: {str(e)}")


@router.post("/{job_id}/move-to-production")
async def move_to_production(job_id: str, request: MoveToProductionRequest):
    """
    Move completed compilation to production with sanitized filename.

    Flow:
    1. Verify job is completed
    2. Get production path from BigQuery (per channel)
    3. Generate sanitized filename
    4. Copy from temp output_path to production location
    5. Update jobs table with production_path

    Filename format: channelname_yyyy-mm-dd_hhmmss.mp4
    """
    supabase = get_supabase_client()

    # 1. Get job
    result = supabase.table('jobs').select('*').eq('job_id', job_id).single().execute()
    job = result.data

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job['status'] != 'completed':
        raise HTTPException(status_code=400, detail="Job must be completed first")

    if job.get('moved_to_production'):
        raise HTTPException(status_code=400, detail="Already moved to production")

    # 2. Get production path from BigQuery
    production_base = get_production_path(job['channel_name'])
    if not production_base:
        raise HTTPException(
            status_code=404,
            detail=f"Production path not configured for channel: {job['channel_name']}"
        )

    # 3. Generate production filename
    if request.custom_filename:
        base_name = sanitize_filename(request.custom_filename)
    else:
        # Auto-generate: channelname_2025-01-18_143022.mp4
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        base_name = sanitize_filename(f"{job['channel_name']}_{timestamp}")

    production_filename = f"{base_name}.mp4"

    # 4. Define production path (from BigQuery)
    production_dir = Path(production_base)
    production_path = production_dir / production_filename

    # 5. Copy from temp to production
    temp_path = Path(job['output_path'])

    try:
        # Ensure production directory exists
        production_dir.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(temp_path, production_path)

        # 6. Update database
        supabase.table('jobs').update({
            'production_path': str(production_path),
            'moved_to_production': True,
            'production_moved_at': datetime.utcnow().isoformat()
        }).eq('job_id', job_id).execute()

        return {
            'success': True,
            'production_path': str(production_path),
            'filename': production_filename
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to move to production: {str(e)}")


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for production:
    - Remove file extension if present
    - Remove accents and non-ASCII characters
    - Replace spaces and special chars with underscores
    - Lowercase
    - Only English alphanumeric and underscores
    """
    import unicodedata
    import re

    # Remove file extension if present
    filename = filename.rsplit('.', 1)[0]

    # Remove accents and non-ASCII
    filename = unicodedata.normalize('NFKD', filename)
    filename = filename.encode('ASCII', 'ignore').decode('ASCII')

    # Replace spaces and special chars with underscore
    filename = re.sub(r'[^\w\s-]', '', filename)
    filename = re.sub(r'[-\s]+', '_', filename)

    return filename.lower()


@router.get("/{job_id}")
async def get_job_status(job_id: str):
    """Get job status by job_id"""
    supabase = get_supabase_client()

    try:
        result = supabase.table("jobs").select("*").eq("job_id", job_id).execute()

        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=404, detail="Job not found")

        return result.data[0]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {str(e)}")


@router.get("/queue/stats")
async def get_queue_stats(user_id: str):
    """
    Get queue statistics and user's job positions.

    Shows:
    - Total jobs in queue (queued + processing)
    - User's jobs with their queue positions
    - Active worker count (dynamically fetched from Celery)
    - Which jobs are processing vs waiting

    Args:
        user_id: User ID (from query parameter, passed by frontend)

    Returns:
        dict: Queue stats with user's job positions
    """
    supabase = get_supabase_client()

    try:
        # Get all queued and processing jobs ordered by creation time
        result = supabase.table('jobs')\
            .select('job_id, user_id, channel_name, status, created_at')\
            .in_('status', ['queued', 'processing'])\
            .order('created_at', desc=False)\
            .execute()

        all_jobs = result.data
        total_in_queue = len(all_jobs)

        # Get active worker count from Celery
        try:
            inspect = celery_app.control.inspect()
            active_workers_dict = inspect.active()

            if active_workers_dict:
                # Count unique workers
                active_workers = len(active_workers_dict.keys())
            else:
                # Fallback if no workers respond
                active_workers = 0
        except Exception as e:
            logger.warning(f"Failed to get active worker count from Celery: {e}")
            # Fallback to 0 workers if Celery inspection fails
            active_workers = 0

        # Calculate positions for user's jobs
        user_jobs = []
        for idx, job in enumerate(all_jobs):
            if job['user_id'] == user_id:
                position = idx + 1
                is_processing = position <= active_workers if active_workers > 0 else False

                user_jobs.append({
                    'job_id': job['job_id'],
                    'channel_name': job['channel_name'],
                    'queue_position': position,
                    'is_processing': is_processing,
                    'status': job['status'],
                    'waiting_count': max(0, position - active_workers) if active_workers > 0 else position
                })

        return {
            'total_in_queue': total_in_queue,
            'active_workers': active_workers,
            'user_jobs': user_jobs,
            'available_slots': max(0, active_workers - total_in_queue) if active_workers > 0 else 0
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get queue stats: {str(e)}")
