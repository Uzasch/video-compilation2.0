from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from services.bigquery import clear_channels_cache, _channels_cache, CACHE_TTL, get_all_channels, get_all_channel_assets
from services.supabase import get_supabase_client
from celery import Celery
from datetime import datetime, timedelta
import time
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize Celery client for worker inspection
celery_app = Celery('workers', broker='redis://redis:6379/0')


# Request/Response Models
class QueuePositionUpdate(BaseModel):
    job_id: str
    position: int


class ReorderQueueRequest(BaseModel):
    positions: List[QueuePositionUpdate]

@router.post("/clear-channels-cache")
async def clear_cache():
    """
    Manually clear the channels cache.

    Use this endpoint after adding a new channel to BigQuery.
    Otherwise, new channel will appear after 24 hours (cache TTL).

    Returns:
        dict: Success message
    """
    clear_channels_cache()
    return {
        "success": True,
        "message": "Channels cache cleared. Next request will fetch fresh data from BigQuery."
    }

@router.get("/cache-status")
async def get_cache_status():
    """
    Get current cache status.

    Returns:
        dict: Cache status with timestamp
    """
    if _channels_cache["data"] is None:
        return {
            "cached": False,
            "message": "Cache is empty"
        }

    age = time.time() - _channels_cache["timestamp"]
    remaining = max(0, CACHE_TTL - age)

    return {
        "cached": True,
        "channels_count": len(_channels_cache["data"]),
        "cache_age_seconds": int(age),
        "cache_remaining_seconds": int(remaining),
        "is_expired": age >= CACHE_TTL
    }

@router.get("/channels")
async def get_channels_list():
    """
    Get list of all channels (for testing and frontend use).

    Returns:
        dict: List of channel names and count
    """
    channels = get_all_channels()
    return {
        "channels": channels,
        "count": len(channels)
    }

@router.get("/channels/{channel_name}/logo")
async def get_channel_logo(channel_name: str):
    """
    Get logo path for a specific channel.

    Args:
        channel_name: Name of the channel

    Returns:
        dict: Logo path for the channel
    """
    assets = get_all_channel_assets(channel_name)
    if not assets or not assets.get('logo'):
        raise HTTPException(status_code=404, detail=f"Logo not found for channel: {channel_name}")

    return {
        "channel_name": channel_name,
        "logo_path": assets['logo']
    }


# ==================== QUEUE MANAGEMENT ====================

@router.get("/queue")
async def get_admin_queue():
    """
    Get all queued and processing jobs for admin queue management.

    Returns jobs ordered by queue_position (if set) then created_at.
    Includes user info for each job.
    """
    supabase = get_supabase_client()

    try:
        # Get queued and processing jobs
        result = supabase.table('jobs')\
            .select('job_id, user_id, channel_name, status, progress, progress_message, enable_4k, queue_position, queue_name, worker_id, created_at, started_at')\
            .in_('status', ['queued', 'processing'])\
            .order('queue_position', nullsfirst=False)\
            .order('created_at')\
            .execute()

        jobs = result.data or []

        # Get user info for each job
        user_ids = list(set(job['user_id'] for job in jobs if job.get('user_id')))
        users_map = {}

        if user_ids:
            users_result = supabase.table('profiles')\
                .select('id, username, display_name')\
                .in_('id', user_ids)\
                .execute()
            users_map = {u['id']: u for u in (users_result.data or [])}

        # Enrich jobs with user info
        for job in jobs:
            user = users_map.get(job.get('user_id'), {})
            job['username'] = user.get('username', 'Unknown')
            job['display_name'] = user.get('display_name', user.get('username', 'Unknown'))

        return {
            'jobs': jobs,
            'total': len(jobs),
            'queued': len([j for j in jobs if j['status'] == 'queued']),
            'processing': len([j for j in jobs if j['status'] == 'processing'])
        }

    except Exception as e:
        logger.error(f"Failed to get admin queue: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get queue: {str(e)}")


@router.post("/queue/reorder")
async def reorder_queue(request: ReorderQueueRequest):
    """
    Update queue positions for multiple jobs.

    Request body: { "positions": [{"job_id": "...", "position": 1}, ...] }

    Only queued jobs can be reordered. Processing jobs keep their position.
    """
    supabase = get_supabase_client()

    try:
        updated = 0
        errors = []

        for item in request.positions:
            # Only update queued jobs
            job_result = supabase.table('jobs')\
                .select('status')\
                .eq('job_id', item.job_id)\
                .single()\
                .execute()

            if not job_result.data:
                errors.append(f"Job {item.job_id} not found")
                continue

            if job_result.data['status'] != 'queued':
                errors.append(f"Job {item.job_id} is {job_result.data['status']}, cannot reorder")
                continue

            # Update position
            supabase.table('jobs')\
                .update({'queue_position': item.position})\
                .eq('job_id', item.job_id)\
                .execute()
            updated += 1

        return {
            'success': True,
            'updated': updated,
            'errors': errors if errors else None
        }

    except Exception as e:
        logger.error(f"Failed to reorder queue: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reorder queue: {str(e)}")


@router.post("/jobs/{job_id}/cancel")
async def admin_cancel_job(job_id: str):
    """
    Cancel a queued job (admin action).

    Only jobs with status 'queued' can be cancelled.
    """
    supabase = get_supabase_client()

    try:
        # Get job
        result = supabase.table('jobs')\
            .select('status, channel_name')\
            .eq('job_id', job_id)\
            .single()\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        if result.data['status'] != 'queued':
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel job with status '{result.data['status']}'. Only queued jobs can be cancelled."
            )

        # Update status
        supabase.table('jobs').update({
            'status': 'cancelled',
            'completed_at': datetime.utcnow().isoformat(),
            'error_message': 'Cancelled by admin'
        }).eq('job_id', job_id).execute()

        return {
            'success': True,
            'message': f"Job {job_id} cancelled",
            'channel_name': result.data['channel_name']
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {str(e)}")


# ==================== JOB HISTORY ====================

@router.get("/jobs")
async def get_all_jobs(
    status: Optional[str] = None,
    channel_name: Optional[str] = None,
    user_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
):
    """
    Get all jobs with optional filters (admin view).

    Args:
        status: Filter by status (queued, processing, completed, failed, cancelled)
        channel_name: Filter by channel
        user_id: Filter by user
        page: Page number (1-indexed)
        page_size: Items per page (max 100)
    """
    supabase = get_supabase_client()
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size

    try:
        # Build query
        query = supabase.table('jobs').select(
            'job_id, user_id, channel_name, status, progress, enable_4k, '
            'output_path, production_path, moved_to_production, '
            'final_duration, error_message, worker_id, queue_name, '
            'created_at, started_at, completed_at',
            count='exact'
        )

        # Apply filters
        if status:
            query = query.eq('status', status)
        if channel_name:
            query = query.eq('channel_name', channel_name)
        if user_id:
            query = query.eq('user_id', user_id)

        # Order and paginate
        query = query.order('created_at', desc=True).range(offset, offset + page_size - 1)

        result = query.execute()
        jobs = result.data or []
        total = result.count or 0

        # Get user info
        user_ids = list(set(job['user_id'] for job in jobs if job.get('user_id')))
        users_map = {}

        if user_ids:
            users_result = supabase.table('profiles')\
                .select('id, username, display_name')\
                .in_('id', user_ids)\
                .execute()
            users_map = {u['id']: u for u in (users_result.data or [])}

        # Enrich with user info
        for job in jobs:
            user = users_map.get(job.get('user_id'), {})
            job['username'] = user.get('username', 'Unknown')
            job['display_name'] = user.get('display_name', user.get('username', 'Unknown'))

        return {
            'jobs': jobs,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size if total > 0 else 1
        }

    except Exception as e:
        logger.error(f"Failed to get jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get jobs: {str(e)}")


# ==================== WORKER STATUS ====================

@router.get("/workers")
async def get_workers_status():
    """
    Get live worker status from Celery.

    Returns active workers, their current tasks, and stats.
    """
    try:
        inspect = celery_app.control.inspect()

        # Get active tasks (currently executing)
        active = inspect.active() or {}

        # Get reserved tasks (prefetched, waiting)
        reserved = inspect.reserved() or {}

        # Get worker stats
        stats = inspect.stats() or {}

        workers = []

        for worker_name in set(list(active.keys()) + list(stats.keys())):
            worker_active = active.get(worker_name, [])
            worker_reserved = reserved.get(worker_name, [])
            worker_stats = stats.get(worker_name, {})

            # Get current task info
            current_task = None
            if worker_active:
                task = worker_active[0]
                current_task = {
                    'task_id': task.get('id'),
                    'name': task.get('name', '').split('.')[-1],  # Get just the function name
                    'args': task.get('args', []),
                    'started': task.get('time_start')
                }

            # Extract useful stats
            pool = worker_stats.get('pool', {})

            workers.append({
                'name': worker_name,
                'status': 'busy' if worker_active else 'idle',
                'current_task': current_task,
                'reserved_count': len(worker_reserved),
                'processed_total': worker_stats.get('total', {}).get('celery.video_compilation', 0),
                'pool_processes': pool.get('max-concurrency', 1),
                'uptime': worker_stats.get('uptime', 0)
            })

        return {
            'workers': workers,
            'total_workers': len(workers),
            'busy_workers': len([w for w in workers if w['status'] == 'busy']),
            'idle_workers': len([w for w in workers if w['status'] == 'idle'])
        }

    except Exception as e:
        logger.warning(f"Failed to get worker status from Celery: {e}")
        # Return empty if Celery is not available
        return {
            'workers': [],
            'total_workers': 0,
            'busy_workers': 0,
            'idle_workers': 0,
            'error': 'Could not connect to Celery workers'
        }


# ==================== STATISTICS ====================

@router.get("/stats")
async def get_admin_stats():
    """
    Get system statistics for admin dashboard.

    Returns job counts by status, recent activity, and performance metrics.
    """
    supabase = get_supabase_client()

    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)

        # Get all jobs for counting
        all_jobs = supabase.table('jobs').select('status, created_at, completed_at, started_at, final_duration').execute()
        jobs = all_jobs.data or []

        # Count by status
        status_counts = {
            'queued': 0,
            'processing': 0,
            'completed': 0,
            'failed': 0,
            'cancelled': 0
        }

        completed_today = 0
        completed_week = 0
        total_duration = 0
        processing_times = []

        for job in jobs:
            status = job.get('status', 'unknown')
            if status in status_counts:
                status_counts[status] += 1

            # Count completed jobs
            if status == 'completed':
                completed_at = job.get('completed_at')
                if completed_at:
                    completed_dt = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
                    if completed_dt.replace(tzinfo=None) >= today_start:
                        completed_today += 1
                    if completed_dt.replace(tzinfo=None) >= week_start:
                        completed_week += 1

                # Track duration
                if job.get('final_duration'):
                    total_duration += job['final_duration']

                # Calculate processing time
                if job.get('started_at') and job.get('completed_at'):
                    started = datetime.fromisoformat(job['started_at'].replace('Z', '+00:00'))
                    completed = datetime.fromisoformat(job['completed_at'].replace('Z', '+00:00'))
                    processing_times.append((completed - started).total_seconds())

        # Calculate averages
        total_completed = status_counts['completed']
        total_jobs = len(jobs)

        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
        success_rate = (total_completed / total_jobs * 100) if total_jobs > 0 else 0

        return {
            'total_jobs': total_jobs,
            'by_status': status_counts,
            'completed_today': completed_today,
            'completed_this_week': completed_week,
            'total_video_duration_hours': round(total_duration / 3600, 1),
            'avg_processing_time_minutes': round(avg_processing_time / 60, 1),
            'success_rate': round(success_rate, 1)
        }

    except Exception as e:
        logger.error(f"Failed to get admin stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")
