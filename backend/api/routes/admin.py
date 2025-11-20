from fastapi import APIRouter
from services.bigquery import clear_channels_cache, _channels_cache, CACHE_TTL, get_all_channels
import time

router = APIRouter()

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
