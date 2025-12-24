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

def upsert_videos_bulk(videos: List[Dict]) -> Dict:
    """
    Insert or update multiple videos in the BigQuery path table.
    If video_id exists, updates path_nyt and video_title.
    If video_id doesn't exist, inserts new row.

    Args:
        videos: List of dicts with keys: video_id, path_nyt, video_title

    Returns:
        Dict with keys: success, upserted, updated_ids, inserted_ids, errors

    Example:
        videos = [
            {"video_id": "abc123", "path_nyt": "\\\\192.168.1.6\\Share3\\video.mp4", "video_title": "My Video"},
            {"video_id": "xyz789", "path_nyt": "\\\\192.168.1.6\\Share3\\video2.mp4", "video_title": "Another Video"}
        ]
        result = upsert_videos_bulk(videos)
        # Returns: {"success": True, "upserted": 2, "updated_ids": ["abc123"], "inserted_ids": ["xyz789"], "errors": []}
    """
    if not videos:
        return {"success": True, "upserted": 0, "updated_ids": [], "inserted_ids": [], "errors": []}

    client = get_bigquery_client()
    table_id = "ybh-deployment-testing.ybh_assest_path.path"

    try:
        # Step 1: Check which video_ids already exist
        video_ids = [v["video_id"] for v in videos]
        existing_ids = set()

        check_query = """
        SELECT video_id
        FROM `ybh-deployment-testing.ybh_assest_path.path`
        WHERE video_id IN UNNEST(@video_ids)
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("video_ids", "STRING", video_ids)
            ]
        )
        check_job = client.query(check_query, job_config=job_config)
        for row in check_job.result():
            existing_ids.add(row["video_id"])

        logger.info(f"Found {len(existing_ids)} existing video IDs out of {len(video_ids)}")

        # Step 2: Separate into updates and inserts
        videos_to_update = [v for v in videos if v["video_id"] in existing_ids]
        videos_to_insert = [v for v in videos if v["video_id"] not in existing_ids]

        updated_ids = []
        inserted_ids = []
        errors = []

        # Step 3: Update existing videos (one by one for simplicity)
        for video in videos_to_update:
            update_query = """
            UPDATE `ybh-deployment-testing.ybh_assest_path.path`
            SET path_nyt = @path_nyt, video_title = @video_title
            WHERE video_id = @video_id
            """
            update_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("video_id", "STRING", video["video_id"]),
                    bigquery.ScalarQueryParameter("path_nyt", "STRING", video["path_nyt"]),
                    bigquery.ScalarQueryParameter("video_title", "STRING", video["video_title"]),
                ]
            )
            try:
                update_job = client.query(update_query, job_config=update_config)
                update_job.result()  # Wait for completion
                updated_ids.append(video["video_id"])
                logger.info(f"Updated video {video['video_id']}")
            except Exception as e:
                logger.error(f"Failed to update video {video['video_id']}: {e}")
                errors.append(f"Update failed for {video['video_id']}: {str(e)}")

        # Step 4: Insert new videos using SQL INSERT (not streaming)
        # Using SQL INSERT instead of insert_rows_json to avoid streaming buffer
        # which prevents immediate UPDATE/DELETE operations
        for video in videos_to_insert:
            insert_query = """
            INSERT INTO `ybh-deployment-testing.ybh_assest_path.path` (video_id, path_nyt, video_title)
            VALUES (@video_id, @path_nyt, @video_title)
            """
            insert_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("video_id", "STRING", video["video_id"]),
                    bigquery.ScalarQueryParameter("path_nyt", "STRING", video["path_nyt"]),
                    bigquery.ScalarQueryParameter("video_title", "STRING", video["video_title"]),
                ]
            )
            try:
                insert_job = client.query(insert_query, job_config=insert_config)
                insert_job.result()  # Wait for completion
                inserted_ids.append(video["video_id"])
                logger.info(f"Inserted video {video['video_id']}")
            except Exception as e:
                logger.error(f"Failed to insert video {video['video_id']}: {e}")
                errors.append(f"Insert failed for {video['video_id']}: {str(e)}")

        total_upserted = len(updated_ids) + len(inserted_ids)
        logger.info(f"Upsert complete: {len(updated_ids)} updated, {len(inserted_ids)} inserted")

        return {
            "success": total_upserted > 0 or len(errors) == 0,
            "upserted": total_upserted,
            "updated_ids": updated_ids,
            "inserted_ids": inserted_ids,
            "errors": errors
        }

    except Exception as e:
        logger.error(f"Error upserting videos to BigQuery: {e}", exc_info=True)
        return {
            "success": False,
            "upserted": 0,
            "updated_ids": [],
            "inserted_ids": [],
            "errors": [str(e)]
        }


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
