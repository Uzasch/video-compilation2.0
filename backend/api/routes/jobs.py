from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from services.bigquery import get_videos_info_by_ids, get_all_channel_assets, get_production_path
from services.storage import normalize_paths, normalize_path_for_server
from services.supabase import get_supabase_client
from services.logger import setup_validation_logger, setup_job_logger
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
    include_intro: bool = True     # Include channel intro
    include_outro: bool = True     # Include channel outro
    enable_logos: bool = True      # Enable logo overlay on videos

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


class VerifyPathRequest(BaseModel):
    path: str


class VerifyPathResponse(BaseModel):
    path: str
    available: bool
    duration: Optional[float] = None
    resolution: Optional[str] = None
    is_4k: Optional[bool] = None


@router.post("/verify-path", response_model=VerifyPathResponse)
async def verify_single_path(request: VerifyPathRequest):
    """
    Verify a single path and return its metadata.

    Used when user manually enters a path and wants to check if it's accessible.
    Uses ffprobe to check existence and get video metadata.

    Returns:
        - path: The normalized path
        - available: Whether the path is accessible
        - duration: Video duration if available
        - resolution: Video resolution (WxH) if available
        - is_4k: Whether the video is 4K
    """
    from services.storage import normalize_paths

    # Normalize the path
    normalized_paths = normalize_paths([request.path])
    normalized_path = normalized_paths[0] if normalized_paths else request.path

    # Get video info using ffprobe
    videos_info = get_videos_info_batch([normalized_path], max_workers=1)
    video_info = videos_info.get(normalized_path)

    if video_info:
        return VerifyPathResponse(
            path=request.path,
            available=True,
            duration=video_info['duration'],
            resolution=f"{video_info['width']}x{video_info['height']}",
            is_4k=video_info['is_4k']
        )
    else:
        return VerifyPathResponse(
            path=request.path,
            available=False
        )


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

    # Apply user preferences for intro/outro/logos
    intro_path = assets['intro'] if request.include_intro else None
    outro_path = assets['outro'] if request.include_outro else None
    logo_path = assets['logo'] if request.enable_logos else None

    validation_logger.info(f"  Include intro: {request.include_intro}")
    validation_logger.info(f"  Include outro: {request.include_outro}")
    validation_logger.info(f"  Enable logos: {request.enable_logos}")
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

    # Step 3: Collect all items for verification
    # Use a LIST instead of dict to handle duplicate paths (same intro/outro, repeated videos)
    items_to_verify = []  # List of {position, path, type, video_id, title, error}

    # Add intro
    if intro_path:
        items_to_verify.append({
            'position': position,
            'path': intro_path,
            'type': 'intro',
            'title': 'Intro'
        })
        position += 1

    # Add videos from BigQuery
    for video_id in request.video_ids:
        if video_id in videos_info:
            items_to_verify.append({
                'position': position,
                'path': videos_info[video_id]["path"],
                'type': 'video',
                'video_id': video_id,
                'title': videos_info[video_id]["title"]
            })
        else:
            # Video ID not in BigQuery - add placeholder with no path
            items_to_verify.append({
                'position': position,
                'path': None,
                'type': 'video',
                'video_id': video_id,
                'title': f'Video {video_id}',
                'error': 'Video ID not found in BigQuery'
            })
        position += 1

    # Add manual paths
    for manual_path in request.manual_paths:
        items_to_verify.append({
            'position': position,
            'path': manual_path,
            'type': 'transition',
            'title': 'Transition'
        })
        position += 1

    # Add outro
    if outro_path:
        items_to_verify.append({
            'position': position,
            'path': outro_path,
            'type': 'outro',
            'title': 'Outro'
        })

    # Step 3: Get video metadata for all paths (ffprobe = existence check + metadata)
    # Collect unique paths to avoid redundant ffprobe calls
    all_paths = [item['path'] for item in items_to_verify if item['path']]
    unique_paths = list(set(all_paths))

    validation_logger.info("Step 3: Getting video info via ffprobe (existence + metadata)...")
    validation_logger.info(f"  Total items: {len(items_to_verify)}, Unique paths: {len(unique_paths)}")

    # Normalize paths before passing to ffprobe
    normalized_paths = normalize_paths(unique_paths)

    # Batch get video info - if ffprobe succeeds, file exists; if fails, file doesn't exist
    videos_info_batch = get_videos_info_batch(normalized_paths, max_workers=max_workers)

    # Map original paths to video info
    path_video_info = {}
    for original, normalized in zip(unique_paths, normalized_paths):
        path_video_info[original] = videos_info_batch.get(normalized)

    # Count available
    available_count = sum(1 for info in path_video_info.values() if info is not None)
    validation_logger.info(f"  Available: {available_count}/{len(unique_paths)}")
    validation_logger.info("")

    # Step 4: Build items with verification results
    total_duration = 0.0
    missing_count = 0

    for item_info in items_to_verify:
        path = item_info.get('path')

        # Handle items with no path (missing video IDs)
        if not path:
            items.append(JobItem(
                position=item_info['position'],
                item_type=item_info['type'],
                video_id=item_info.get('video_id'),
                title=item_info.get('title'),
                path=None,
                path_available=False,
                logo_path=logo_path if item_info['type'] == 'video' else None,
                error=item_info.get('error')
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

    # Get username for logging
    user_result = supabase.table('profiles').select('username').eq('id', job['user_id']).execute()
    username = user_result.data[0]['username'] if user_result.data else 'unknown'

    # Setup job logger (appends to existing job log)
    job_logger, log_path = setup_job_logger(job_id, username, job['channel_name'])

    job_logger.info("")
    job_logger.info("=== Move to Production ===")
    job_logger.info(f"Job ID: {job_id}")
    job_logger.info(f"Channel: {job['channel_name']}")
    job_logger.info(f"Custom filename requested: {request.custom_filename or 'None (auto-generate)'}")

    # 2. Get production path from BigQuery and normalize for server
    production_base_raw = get_production_path(job['channel_name'])
    if not production_base_raw:
        job_logger.error(f"Production path not configured for channel: {job['channel_name']}")
        raise HTTPException(
            status_code=404,
            detail=f"Production path not configured for channel: {job['channel_name']}"
        )

    # Normalize path (convert Windows UNC to Docker mount path)
    production_base = normalize_path_for_server(production_base_raw)
    job_logger.info(f"Production base path: {production_base_raw} -> {production_base}")

    # 3. Generate production filename
    if request.custom_filename:
        base_name = sanitize_filename(request.custom_filename)
        job_logger.info(f"Using custom filename: {request.custom_filename} -> {base_name}")
    else:
        # Auto-generate: channelname_2025-01-18_143022.mp4
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        base_name = sanitize_filename(f"{job['channel_name']}_{timestamp}")
        job_logger.info(f"Auto-generated filename: {base_name}")

    production_filename = f"{base_name}.mp4"

    # 4. Define production path (from BigQuery)
    production_dir = Path(production_base)
    production_path = production_dir / production_filename

    # 5. Copy from temp to production
    temp_path = Path(job['output_path'])

    job_logger.info(f"Source: {temp_path}")
    job_logger.info(f"Destination: {production_path}")

    try:
        # Ensure production directory exists
        production_dir.mkdir(parents=True, exist_ok=True)

        # Copy file
        job_logger.info("Copying file...")
        shutil.copy2(temp_path, production_path)
        job_logger.info("File copied successfully")

        # 6. Update database
        supabase.table('jobs').update({
            'production_path': str(production_path),
            'moved_to_production': True,
            'production_moved_at': datetime.utcnow().isoformat()
        }).eq('job_id', job_id).execute()

        job_logger.info("Database updated")
        job_logger.info(f"Result: SUCCESS - {production_filename}")

        return {
            'success': True,
            'production_path': str(production_path),
            'filename': production_filename
        }

    except Exception as e:
        job_logger.error(f"Failed to move to production: {str(e)}")
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


@router.get("/")
async def list_jobs(
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 50
):
    """
    List jobs with optional filtering.

    Args:
        status: Filter by status. Use 'active' for queued+processing, or specific status
        user_id: Filter by user ID (required for non-admin users)
        limit: Maximum number of jobs to return (default 50)

    Returns:
        List of jobs matching the criteria
    """
    supabase = get_supabase_client()

    try:
        query = supabase.table('jobs').select('*')

        # Filter by status
        if status == 'active':
            query = query.in_('status', ['queued', 'processing'])
        elif status:
            query = query.eq('status', status)

        # Filter by user
        if user_id:
            query = query.eq('user_id', user_id)

        # Order and limit
        query = query.order('created_at', desc=True).limit(limit)

        result = query.execute()
        return result.data or []

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list jobs: {str(e)}")


@router.get("/history")
async def get_job_history(
    user_id: Optional[str] = None,
    channel_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
):
    """
    Get compilation history (completed, failed, cancelled jobs).

    Args:
        user_id: Filter by user ID (required for non-admin users)
        channel_name: Filter by channel name
        date_from: Filter jobs completed on or after this date (YYYY-MM-DD)
        date_to: Filter jobs completed on or before this date (YYYY-MM-DD)
        page: Page number (1-indexed)
        page_size: Number of items per page (default 20, max 100)

    Returns:
        dict: { jobs: [...], total: int, page: int, page_size: int, total_pages: int }
    """
    supabase = get_supabase_client()
    page_size = min(page_size, 100)  # Cap at 100
    offset = (page - 1) * page_size

    try:
        # Build query for history (completed, failed, cancelled)
        query = supabase.table('jobs').select(
            'job_id, user_id, channel_name, status, enable_4k, '
            'output_path, production_path, moved_to_production, '
            'final_duration, error_message, created_at, completed_at',
            count='exact'
        ).in_('status', ['completed', 'failed', 'cancelled'])

        # Filter by user
        if user_id:
            query = query.eq('user_id', user_id)

        # Filter by channel
        if channel_name:
            query = query.eq('channel_name', channel_name)

        # Filter by date range (using completed_at)
        if date_from:
            query = query.gte('completed_at', f"{date_from}T00:00:00")
        if date_to:
            query = query.lte('completed_at', f"{date_to}T23:59:59")

        # Order by completion date (most recent first) and paginate
        query = query.order('completed_at', desc=True).range(offset, offset + page_size - 1)

        result = query.execute()
        total = result.count or 0
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1

        return {
            'jobs': result.data or [],
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get job history: {str(e)}")


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


@router.get("/{job_id}/items")
async def get_job_items(job_id: str):
    """
    Get all items for a job, ordered by position.

    Returns:
        List of job items with all fields
    """
    supabase = get_supabase_client()

    try:
        # First verify job exists
        job_result = supabase.table("jobs").select("job_id").eq("job_id", job_id).execute()
        if not job_result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get items ordered by position
        result = supabase.table("job_items")\
            .select("*")\
            .eq("job_id", job_id)\
            .order("position")\
            .execute()

        return result.data or []

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get job items: {str(e)}")


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    """
    Cancel a queued job.

    Only jobs with status 'queued' can be cancelled.
    Processing jobs cannot be cancelled (would need to implement Celery task revocation).

    Returns:
        Success message with updated status
    """
    supabase = get_supabase_client()

    try:
        # Get job
        result = supabase.table("jobs").select("*").eq("job_id", job_id).single().execute()
        job = result.data

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job['status'] != 'queued':
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel job with status '{job['status']}'. Only queued jobs can be cancelled."
            )

        # Update status to cancelled
        supabase.table("jobs").update({
            'status': 'cancelled',
            'completed_at': datetime.utcnow().isoformat(),
            'error_message': 'Cancelled by user'
        }).eq("job_id", job_id).execute()

        return {
            'success': True,
            'message': 'Job cancelled successfully',
            'job_id': job_id
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {str(e)}")


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
