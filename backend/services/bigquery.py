from google.cloud import bigquery
from google.oauth2 import service_account
from api.config import get_settings
from functools import lru_cache
from typing import List, Optional, Dict
import logging
import time

logger = logging.getLogger(__name__)

# Cache for channels with TTL
_channels_cache = {"data": None, "timestamp": 0}
CACHE_TTL = 86400  # 24 hours (channels rarely change)

@lru_cache()
def get_bigquery_client():
    """Get BigQuery client (cached)"""
    settings = get_settings()
    credentials = service_account.Credentials.from_service_account_file(
        settings.google_application_credentials
    )
    return bigquery.Client(
        credentials=credentials,
        project=settings.bigquery_project_id
    )

def get_videos_info_by_ids(video_ids: List[str]) -> Dict[str, dict]:
    """
    Fetch video paths and titles from BigQuery in a single batch query.

    Args:
        video_ids: List of video IDs (e.g., ["TJU5wYdTG4c", "ABC123xyz", ...])

    Returns:
        Dict mapping video_id to {path, title}

        Example:
        {
            "TJU5wYdTG4c": {
                "path": "\\\\192.168.1.6\\Share3\\YBH\\video_001.mp4",
                "title": "Amazing Video Title"
            },
            "ABC123xyz": {
                "path": "\\\\192.168.1.6\\Share3\\YBH\\video_002.mp4",
                "title": "Another Great Video"
            }
        }

        Missing video IDs are simply not in the returned dict.
    """
    if not video_ids:
        return {}

    client = get_bigquery_client()

    query = """
    SELECT video_id, path_nyt, video_title
    FROM `ybh-deployment-testing.ybh_assest_path.path`
    WHERE video_id IN UNNEST(@video_ids)
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("video_ids", "STRING", video_ids)
        ]
    )

    try:
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()

        videos_info = {}
        for row in results:
            video_id = row["video_id"]
            path = row["path_nyt"]
            title = row.get("video_title", f"Video {video_id}")

            # Remove quotes if present
            if path and path.startswith('"') and path.endswith('"'):
                path = path[1:-1]

            videos_info[video_id] = {
                "path": path,
                "title": title
            }

        logger.info(f"BigQuery returned {len(videos_info)} videos out of {len(video_ids)} requested")
        if len(videos_info) < len(video_ids):
            missing = set(video_ids) - set(videos_info.keys())
            logger.warning(f"Missing video IDs from BigQuery: {missing}")

        return videos_info

    except Exception as e:
        logger.error(f"Error querying BigQuery for video IDs: {e}", exc_info=True)
        return {}

def get_all_channel_assets(channel_name: str) -> Dict[str, Optional[str]]:
    """
    Get all branding assets (logo, intro, end_packaging) in a single query.

    Args:
        channel_name: Channel name

    Returns:
        Dict with keys: 'logo', 'intro', 'outro'

    Example:
        {
            'logo': '\\\\192.168.1.6\\Share3\\Logos\\YBH.png',
            'intro': '\\\\192.168.1.6\\Share3\\Intros\\YBH_intro.mp4',
            'outro': '\\\\192.168.1.6\\Share3\\Outros\\YBH_outro.mp4'
        }
    """
    client = get_bigquery_client()

    query = """
    SELECT logo, intro_packaging, end_packaging
    FROM `ybh-deployment-testing.ybh_assest_path.branding_assets`
    WHERE channel_name = @channel_name
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("channel_name", "STRING", channel_name)
        ]
    )

    try:
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()

        rows = list(results)
        if rows:
            row = rows[0]
            return {
                'logo': row['logo'],
                'intro': row['intro_packaging'],
                'outro': row['end_packaging']
            }
        return {'logo': None, 'intro': None, 'outro': None}

    except Exception as e:
        logger.error(f"Error querying BigQuery for channel assets of {channel_name}: {e}", exc_info=True)
        return {'logo': None, 'intro': None, 'outro': None}

def get_all_channels() -> List[str]:
    """
    Get list of all channel names from BigQuery.
    Cached for 24 hours to reduce BigQuery queries.
    Channels rarely change, admin can manually clear cache if needed.
    """
    global _channels_cache

    now = time.time()

    # Check if cache is still valid
    if _channels_cache["data"] is not None and (now - _channels_cache["timestamp"]) < CACHE_TTL:
        return _channels_cache["data"]

    # Cache expired or empty - fetch from BigQuery
    client = get_bigquery_client()

    query = """
    SELECT channel_name
    FROM `ybh-deployment-testing.ybh_assest_path.branding_assets`
    ORDER BY channel_name
    """

    try:
        query_job = client.query(query)
        results = query_job.result()
        channels = [row["channel_name"] for row in results]

        # Update cache
        _channels_cache["data"] = channels
        _channels_cache["timestamp"] = now

        return channels

    except Exception as e:
        logger.error(f"Error fetching channels from BigQuery: {e}", exc_info=True)

        # Return cached data if available (even if expired)
        if _channels_cache["data"] is not None:
            return _channels_cache["data"]
        return []

def clear_channels_cache():
    """Manually clear the channels cache (for admin use)"""
    global _channels_cache
    _channels_cache = {"data": None, "timestamp": 0}
    logger.info("Channels cache cleared")

def get_production_path(channel_name: str) -> Optional[str]:
    """
    Get production output path for a channel from BigQuery.

    Args:
        channel_name: Channel name

    Returns:
        Production path (e.g., "\\\\192.168.1.6\\Share3\\Production\\YBH_Official")
        or None if not found
    """
    client = get_bigquery_client()

    query = """
    SELECT output_path
    FROM `ybh-deployment-testing.ybh_assest_path.branding_assets`
    WHERE channel_name = @channel_name
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("channel_name", "STRING", channel_name)
        ]
    )

    try:
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()

        rows = list(results)
        if rows and rows[0]["output_path"]:
            return rows[0]["output_path"]
        return None

    except Exception as e:
        logger.error(f"Error querying production path for {channel_name}: {e}", exc_info=True)
        return None

def insert_compilation_result(job_data: Dict):
    """
    Insert compilation result into Supabase compilation_history table.
    Called when job completes.

    Schema:
    - job_id: UUID
    - user_id: UUID
    - channel_name: TEXT
    - video_count: INTEGER
    - total_duration: FLOAT
    - output_filename: TEXT (extracted from output_path)
    - created_at: TIMESTAMPTZ (auto-generated)
    """
    from services.supabase import get_supabase_client
    from pathlib import Path

    supabase = get_supabase_client()

    # Extract filename from full path
    output_filename = Path(job_data["output_path"]).name if job_data.get("output_path") else None

    row_to_insert = {
        "job_id": str(job_data["job_id"]),
        "user_id": job_data["user_id"],
        "channel_name": job_data["channel_name"],
        "video_count": job_data["video_count"],
        "total_duration": job_data["total_duration"],
        "output_filename": output_filename
    }

    try:
        result = supabase.table('compilation_history').insert(row_to_insert).execute()

        if result.data:
            logger.info(f"Compilation history inserted for job {job_data['job_id']}")
            return True
        else:
            logger.error(f"Failed to insert compilation history for job {job_data['job_id']}")
            return False

    except Exception as e:
        logger.error(f"Error inserting to compilation_history: {e}", exc_info=True)
        return False
