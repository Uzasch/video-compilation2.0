# Task 4: Job Submission & BigQuery Integration

## Objective
Implement job submission, video validation, and BigQuery integration for fetching video paths.

---

## 1. BigQuery Service

**File: `backend/services/bigquery.py`**

```python
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
    SELECT video_id, path_nyt, title
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
            title = row.get("title", f"Video {video_id}")

            # Remove quotes if present
            if path and path.startswith('"') and path.endswith('"'):
                path = path[1:-1]

            videos_info[video_id] = {
                "path": path,
                "title": title
            }

        return videos_info

    except Exception as e:
        logger.error(f"Error querying BigQuery for video IDs: {e}", exc_info=True)
        return {}

def get_asset_path(asset_type: str, channel_name: str) -> Optional[str]:
    """
    Get logo, intro, or end_packaging path from BigQuery.

    Args:
        asset_type: One of "logo", "intro", "end_packaging"
        channel_name: Channel name
    """
    client = get_bigquery_client()

    column_map = {
        "logo": "logo",
        "intro": "intro_packaging",
        "end_packaging": "end_packaging"
    }

    if asset_type not in column_map:
        return None

    column = column_map[asset_type]

    query = f"""
    SELECT {column}
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
            return rows[0][column]
        return None

    except Exception as e:
        logger.error(f"Error querying BigQuery for {asset_type} of {channel_name}: {e}", exc_info=True)
        return None

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
    SELECT production_path
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
        if rows and rows[0]["production_path"]:
            return rows[0]["production_path"]
        return None

    except Exception as e:
        logger.error(f"Error querying production path for {channel_name}: {e}", exc_info=True)
        return None

def insert_compilation_result(job_data: Dict):
    """
    Insert compilation result into BigQuery analytics table.
    Called when job completes.
    """
    client = get_bigquery_client()

    table_id = "ybh-deployment-testing.ybh_assest_path.compilation_results"

    rows_to_insert = [{
        "job_id": str(job_data["job_id"]),
        "user_username": job_data["username"],
        "channel_name": job_data["channel_name"],
        "timestamp": job_data["timestamp"],
        "video_count": job_data["video_count"],
        "total_duration": job_data["total_duration"],
        "output_path": job_data["output_path"],
        "worker_id": job_data["worker_id"],
        "features_used": job_data["features_used"],
        "processing_time_seconds": job_data["processing_time"],
        "status": job_data["status"]
    }]

    try:
        errors = client.insert_rows_json(table_id, rows_to_insert)
        if errors:
            logger.error(f"BigQuery insert errors: {errors}")
            return False
        return True

    except Exception as e:
        logger.error(f"Error inserting to BigQuery: {e}", exc_info=True)
        return False
```

---

## 2. Storage Service (SMB Operations)

**File: `backend/services/storage.py`**

**Cross-Platform File Copying:**
- **Linux/Docker**: rsync (preferred) → cp (fallback) → shutil (final fallback)
- **Windows**: robocopy (preferred) → shutil (fallback)
- Auto-detects environment and uses optimal copy method
- Built-in retry logic and timeout handling

```python
import os
import subprocess
import shutil
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from api.config import get_settings

logger = logging.getLogger(__name__)

# Check which copy tools are available
_RSYNC_AVAILABLE = None
_CP_AVAILABLE = None

def _check_command_available(cmd: str) -> bool:
    """Check if a command is available in PATH"""
    try:
        subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False

def is_rsync_available() -> bool:
    """Check if rsync is available (cached)"""
    global _RSYNC_AVAILABLE
    if _RSYNC_AVAILABLE is None:
        _RSYNC_AVAILABLE = _check_command_available("rsync")
        logger.info(f"rsync available: {_RSYNC_AVAILABLE}")
    return _RSYNC_AVAILABLE

def is_cp_available() -> bool:
    """Check if cp is available (cached)"""
    global _CP_AVAILABLE
    if _CP_AVAILABLE is None:
        _CP_AVAILABLE = _check_command_available("cp")
        logger.info(f"cp available: {_CP_AVAILABLE}")
    return _CP_AVAILABLE

# Drive letter mappings for SMB shares
SHARE_MAPPINGS = {
    "Share": "S:",
    "Share2": "T:",
    "Share3": "U:",
    "Share4": "V:",
    "Share5": "W:",
    "New_Share_1": "O:",
    "New_Share_2": "P:",
    "New_Share_3": "Q:",
    "New_Share_4": "R:",
}

def normalize_paths(paths: List[str]) -> List[str]:
    """
    Normalize multiple paths to Windows UNC format (batch operation).

    Handles:
    - Windows UNC: \\192.168.1.6\Share4\path\file.mp4
    - Drive letters: V:\path\file.mp4
    - SMB URLs: smb://192.168.1.6/Share4/path/file.mp4
    - macOS volumes: /Volumes/Share4/path/file.mp4

    Returns:
        List of normalized Windows UNC paths

    Example:
        Input: [
            "V:\\Production\\video.mp4",
            "smb://192.168.1.6/Share4/video2.mp4",
            "/Volumes/Share4/video3.mp4"
        ]
        Output: [
            "\\\\192.168.1.6\\Share4\\Production\\video.mp4",
            "\\\\192.168.1.6\\Share4\\video2.mp4",
            "\\\\192.168.1.6\\Share4\\video3.mp4"
        ]
    """
    normalized = []

    for path in paths:
        if not path:
            normalized.append(path)
            continue

        # Remove quotes if present
        path = path.strip().strip('"').strip("'")

        # Case 1: SMB URL (smb://192.168.1.6/Share4/...)
        if path.startswith("smb://"):
            path = path.replace("smb://", "\\\\")
            path = path.replace("/", "\\")
            normalized.append(path)
            continue

        # Case 2: macOS volume (/Volumes/Share4/...)
        if path.startswith("/Volumes/"):
            # Extract share name
            parts = path.split("/")
            if len(parts) >= 3:
                share_name = parts[2]  # e.g., "Share4"
                remaining = "/".join(parts[3:])
                # Convert to UNC: \\192.168.1.6\Share4\...
                path = f"\\\\192.168.1.6\\{share_name}\\{remaining}"
                path = path.replace("/", "\\")
            normalized.append(path)
            continue

        # Case 3: Drive letter (V:\Production\...)
        if len(path) >= 2 and path[1] == ":":
            drive = path[:2]  # e.g., "V:"
            # Find which share this drive maps to
            share_name = None
            for share, mapped_drive in SHARE_MAPPINGS.items():
                if mapped_drive == drive:
                    share_name = share
                    break

            if share_name:
                remaining = path[2:].lstrip("\\")
                path = f"\\\\192.168.1.6\\{share_name}\\{remaining}"
            normalized.append(path)
            continue

        # Case 4: Already Windows UNC (\\192.168.1.6\...)
        # Just ensure backslashes
        path = path.replace("/", "\\")
        normalized.append(path)

    return normalized

def check_paths_exist(paths: List[str], max_workers: int = 10) -> Dict[str, bool]:
    """
    Check if multiple paths exist in parallel (batch operation).

    Args:
        paths: List of paths to check (any format)
        max_workers: Maximum parallel checks (default: 10)

    Returns:
        Dict mapping original path to existence status

    Example:
        Input: ["\\\\192.168.1.6\\Share4\\video1.mp4", "V:\\video2.mp4"]
        Output: {
            "\\\\192.168.1.6\\Share4\\video1.mp4": True,
            "V:\\video2.mp4": False
        }

    Performance:
        - Sequential: 17 SMB paths × 0.1s = 1.7 seconds
        - Parallel (10 workers): 17 paths ÷ 10 = ~0.2 seconds
    """
    if not paths:
        return {}

    normalized = normalize_paths(paths)
    results = {}

    def check_single_path(path_tuple):
        """Check if a single path exists"""
        original, normalized_path = path_tuple
        try:
            exists = os.path.exists(normalized_path)
            if not exists:
                logger.warning(f"Path not found: {normalized_path}")
            return original, exists
        except Exception as e:
            logger.error(f"Error checking path {normalized_path}: {e}", exc_info=True)
            return original, False

    # Parallel path existence checks using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        path_tuples = list(zip(paths, normalized))

        # Submit all path checks
        future_to_path = {
            executor.submit(check_single_path, pt): pt
            for pt in path_tuples
        }

        # Collect results as they complete
        for future in as_completed(future_to_path):
            original, exists = future.result()
            results[original] = exists

    return results

def copy_file_sequential(
    source_path: str,
    dest_dir: str,
    dest_filename: Optional[str] = None,
    use_robocopy: bool = True
) -> Optional[str]:
    """
    Copy a single file (for progress tracking).

    Uses robocopy by default, falls back to shutil.copy() if robocopy fails.

    Args:
        source_path: Source file path (any format)
        dest_dir: Destination directory
        dest_filename: Optional destination filename (if None, use original name)
        use_robocopy: If True, try robocopy first; if False, use shutil directly

    Returns:
        Destination file path if success, None if failed

    Example:
        Input:
            source_path = "V:\\Production\\video.mp4"
            dest_dir = "temp/abc-123"
            dest_filename = "video_001.mp4"

        Output: "temp/abc-123/video_001.mp4"
    """
    # Normalize source path
    normalized_source = normalize_paths([source_path])[0]
    source_file_path = Path(normalized_source)

    # Prepare destination
    dest_path = Path(dest_dir)
    dest_path.mkdir(parents=True, exist_ok=True)

    if dest_filename:
        dest_file = dest_path / dest_filename
    else:
        dest_file = dest_path / source_file_path.name

    # Check if source exists
    if not source_file_path.exists():
        logger.error(f"Source file not found: {normalized_source}")
        return None

    # Method 1: Try robocopy first
    if use_robocopy:
        try:
            source_dir = str(source_file_path.parent)
            source_filename = source_file_path.name

            # Robocopy command
            cmd = [
                "robocopy",
                source_dir,
                str(dest_path),
                source_filename,
                "/R:3",      # Retry 3 times on failure
                "/W:5",      # Wait 5 seconds between retries
                "/NP",       # No progress (less verbose)
                "/NDL",      # No directory list
                "/NJH",      # No job header
                "/NJS"       # No job summary
            ]

            logger.info(f"Copying with robocopy: {normalized_source} → {dest_file}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            # Robocopy exit codes: 0-7 are success, 8+ are errors
            if result.returncode < 8:
                # Rename if needed
                temp_dest = dest_path / source_filename
                if dest_filename and temp_dest.exists() and temp_dest != dest_file:
                    temp_dest.rename(dest_file)

                logger.info(f"✓ Robocopy successful: {dest_file}")
                return str(dest_file)
            else:
                logger.warning(f"Robocopy failed (code {result.returncode}), falling back to shutil")
                # Fall through to shutil backup

        except Exception as e:
            logger.warning(f"Robocopy error: {e}, falling back to shutil")
            # Fall through to shutil backup

    # Method 2: Backup with shutil.copy() (no metadata)
    try:
        logger.info(f"Copying with shutil: {normalized_source} → {dest_file}")
        shutil.copy(normalized_source, dest_file)  # copy() not copy2() - no metadata
        logger.info(f"✓ Shutil copy successful: {dest_file}")
        return str(dest_file)

    except Exception as e:
        logger.error(f"✗ Failed to copy {normalized_source}: {e}", exc_info=True)
        return None

def cleanup_temp_dir(job_id: str):
    """
    Clean up temp directory for a job.

    Args:
        job_id: Job UUID
    """
    settings = get_settings()
    temp_dir = Path(settings.temp_dir) / str(job_id)

    if temp_dir.exists():
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"✓ Cleaned up temp dir: {temp_dir}")
        except Exception as e:
            logger.error(f"✗ Failed to clean up {temp_dir}: {e}", exc_info=True)
    else:
        logger.debug(f"Temp dir doesn't exist (already cleaned?): {temp_dir}")
```

---

## 3. Video Utilities

**File: `backend/utils/video_utils.py`**

```python
import subprocess
import json
import logging
from typing import Optional, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

def get_video_info(video_path: str) -> Optional[Dict]:
    """
    Get video duration and resolution in a single ffprobe call.

    Args:
        video_path: Path to video file

    Returns:
        Dict with video info or None if error:
        {
            "duration": 120.5,        # seconds (float)
            "width": 1920,            # pixels (int)
            "height": 1080,           # pixels (int)
            "is_4k": False            # bool
        }

    Example:
        info = get_video_info("\\\\192.168.1.6\\Share4\\video.mp4")
        if info:
            print(f"Duration: {info['duration']}s")
            print(f"Resolution: {info['width']}x{info['height']}")
            print(f"Is 4K: {info['is_4k']}")
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',  # First video stream
            '-show_entries', 'stream=width,height:format=duration',
            '-of', 'json',
            video_path
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            logger.error(f"ffprobe failed for {video_path}: {result.stderr}")
            return None

        data = json.loads(result.stdout)

        # Extract duration from format
        duration = None
        if 'format' in data and 'duration' in data['format']:
            duration = float(data['format']['duration'])

        # Extract resolution from stream
        width = 0
        height = 0
        if 'streams' in data and len(data['streams']) > 0:
            stream = data['streams'][0]
            width = stream.get('width', 0)
            height = stream.get('height', 0)

        # Check if valid video info
        if duration is None or width == 0 or height == 0:
            logger.warning(f"Incomplete video info for {video_path}: duration={duration}, {width}x{height}")
            return None

        return {
            "duration": duration,
            "width": width,
            "height": height,
            "is_4k": width >= 3840 and height >= 2160
        }

    except subprocess.TimeoutExpired:
        logger.error(f"ffprobe timeout for {video_path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for {video_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting video info for {video_path}: {e}", exc_info=True)
        return None

def get_videos_info_batch(video_paths: List[str], max_workers: int = 5) -> Dict[str, Optional[Dict]]:
    """
    Get video info for multiple videos in parallel (batch operation).

    Args:
        video_paths: List of video file paths
        max_workers: Maximum parallel ffprobe processes (default: 5)

    Returns:
        Dict mapping video_path to video info (or None if error)

    Example:
        paths = ["video1.mp4", "video2.mp4", "video3.mp4"]
        results = get_videos_info_batch(paths)

        for path, info in results.items():
            if info:
                print(f"{path}: {info['duration']}s, {info['width']}x{info['height']}")
            else:
                print(f"{path}: Failed to get info")

    Performance:
        - Sequential: 15 videos × 1s = 15 seconds
        - Parallel (5 workers): 15 videos ÷ 5 = 3 seconds
    """
    results = {}

    if not video_paths:
        return results

    logger.info(f"Getting video info for {len(video_paths)} videos (max_workers={max_workers})...")

    # Use ThreadPoolExecutor for parallel ffprobe calls
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_path = {
            executor.submit(get_video_info, path): path
            for path in video_paths
        }

        # Collect results as they complete
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                info = future.result()
                results[path] = info

                if info:
                    logger.debug(f"✓ {path}: {info['duration']:.2f}s, {info['width']}x{info['height']}")
                else:
                    logger.warning(f"✗ {path}: Failed to get info")

            except Exception as e:
                logger.error(f"✗ {path}: Exception during processing: {e}")
                results[path] = None

    success_count = sum(1 for info in results.values() if info is not None)
    logger.info(f"Completed: {success_count}/{len(video_paths)} successful")

    return results
```

---

## 4. Validation Logger

**File: `backend/services/logger.py`** (create this file)

```python
import logging
from pathlib import Path
from datetime import datetime
from api.config import get_settings

def setup_validation_logger(username: str):
    """
    Create validation logger for /verify endpoint.
    Log path: logs/{date}/{username}/verify/{HH-MM-SS-mmm}.log

    Used for:
    - Initial bulk verification (multiple video IDs)
    - Single item verification (when user adds manual path)
    - Any /verify call

    Logs both INFO and ERROR levels.
    File-only logging (no console output to keep Docker logs clean).

    Returns:
        tuple: (logger instance, log file path)
    """
    settings = get_settings()
    now = datetime.now()

    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H-%M-%S-%f')[:-3]  # HH-MM-SS-mmm (milliseconds)

    log_dir = Path(settings.log_dir) / date_str / username / "verify"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"{time_str}.log"

    # Create logger
    logger = logging.getLogger(f"validation_{username}_{time_str}")
    logger.setLevel(logging.INFO)  # Capture INFO and ERROR levels
    logger.propagate = False  # Don't propagate to root logger (no console output)
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

**Log Structure:**
```
logs/
├── 2025-11-19/
│   ├── Uzasch/
│   │   ├── verify/                    # All /verify calls
│   │   │   ├── 10-30-45-123.log       # Initial bulk verification
│   │   │   ├── 15-20-33-456.log       # Added manual path
│   │   │   └── 16-45-12-789.log       # Added another video ID
│   │   └── jobs/                      # Job processing logs (Task 5)
│   │       ├── YBH_Official_abc-123.log
│   │       ├── Tech_Channel_def-456.log
│   │       └── Gaming_Channel_ghi-789.log
│   └── admin/
│       ├── verify/
│       │   └── 09-15-20-001.log
│       └── jobs/
│           ├── News_Channel_xyz-999.log
│           └── Sports_Channel_aaa-111.log
```

**Benefits:**
- **Simple** - Only one verification log type
- **Complete history** - Every /verify call logged
- **Easy to browse** - All verification attempts in one folder
- **Helpful for debugging** - See what user verified and when
- **Automatic cleanup** - Delete old date folders

**Example Log Output - Initial Bulk Verification (with errors):**

File: `logs/2025-11-19/Uzasch/verify/15-30-45-123.log`

```log
15:30:45 - INFO - === Verification Request ===
15:30:45 - INFO - User: Uzasch
15:30:45 - INFO - Channel: YBH Official
15:30:45 - INFO - Video IDs: 15
15:30:45 - INFO - Manual Paths: 0
15:30:45 - INFO -
15:30:46 - INFO - Step 1: Fetching channel branding assets...
15:30:46 - INFO -   Logo: ✓ \\192.168.1.6\Share3\Assets\logo_ybh.png
15:30:46 - INFO -   Intro: ✓ \\192.168.1.6\Share3\Assets\intro_ybh.mp4
15:30:46 - INFO -   Outro: ✓ \\192.168.1.6\Share3\Assets\outro_ybh.mp4
15:30:46 - INFO -
15:30:46 - INFO - Step 2: Fetching video info from BigQuery (batch query)...
15:30:47 - INFO -   Found 14/15 videos in BigQuery
15:30:47 - INFO -
15:30:47 - INFO - Step 3: Batch checking all paths exist...
15:30:48 - INFO -   Checking 16 paths (intro + 14 videos + outro)
15:30:48 - ERROR - Path not found: \\192.168.1.6\Share3\YBH\video_003.mp4
15:30:48 - ERROR - Path not found: \\192.168.1.6\Share3\YBH\video_007.mp4
15:30:48 - ERROR - Path not found: \\192.168.1.6\Share3\YBH\video_012.mp4
15:30:49 - INFO -   13/16 paths available
15:30:49 - INFO -
15:30:49 - INFO - Step 4: Getting video info (duration + resolution) in parallel...
15:30:50 - INFO -   Got video info for 13/13 available videos
15:30:50 - INFO -
15:30:50 - INFO - === Verification Summary ===
15:30:50 - INFO - Total items: 16
15:30:50 - INFO - Available: 13
15:30:50 - INFO - Missing: 3
15:30:50 - INFO - Total duration: 1850.50s (30.84 min)
15:30:50 - INFO - Result: PARTIAL - 3 items need attention
```

**Example Log Output - Single Manual Path Added:**

File: `logs/2025-11-19/Uzasch/verify/16-45-12-789.log`

```log
16:45:12 - INFO - === Verification Request ===
16:45:12 - INFO - User: Uzasch
16:45:12 - INFO - Channel: YBH Official
16:45:12 - INFO - Video IDs: 0
16:45:12 - INFO - Manual Paths: 1
16:45:12 - INFO -
16:45:12 - INFO - Verifying manual path:
16:45:12 - INFO -   V:\Production\Kids\video.mp4
16:45:12 - INFO -   Normalized: \\192.168.1.6\Share4\Production\Kids\video.mp4
16:45:13 - INFO -   Status: ✓ Available
16:45:13 - INFO -   Duration: 120.50s
16:45:13 - INFO -
16:45:13 - INFO - === Verification Summary ===
16:45:13 - INFO - Total items: 1
16:45:13 - INFO - Available: 1
16:45:13 - INFO - Missing: 0
16:45:13 - INFO - Result: SUCCESS
```

---

## 5. Job Routes - Verify & Submit

**File: `backend/api/routes/jobs.py`**

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from services.bigquery import get_videos_info_by_ids, get_asset_path, get_production_path
from services.storage import normalize_paths, check_paths_exist
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
    text_animation_words: Optional[List[str]] = []
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
async def verify_job(request: VerifyJobRequest, user_id: str):
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
    logger, log_path = setup_validation_logger(username)

    logger.info("=== Verification Request ===")
    logger.info(f"User: {username}")
    logger.info(f"Channel: {request.channel_name}")
    logger.info(f"Video IDs: {len(request.video_ids)}")
    logger.info(f"Manual Paths: {len(request.manual_paths)}")
    logger.info("")

    items = []
    position = 1

    # Step 1: Get channel branding assets
    logger.info("Step 1: Fetching channel branding assets...")
    intro_path = get_asset_path("intro", request.channel_name)
    outro_path = get_asset_path("outro", request.channel_name)
    logo_path = get_asset_path("logo", request.channel_name)

    if logo_path:
        logger.info(f"  Logo: ✓ {logo_path}")
    if intro_path:
        logger.info(f"  Intro: ✓ {intro_path}")
    if outro_path:
        logger.info(f"  Outro: ✓ {outro_path}")
    logger.info("")

    # Step 2: Batch query BigQuery for video IDs
    videos_info = {}
    if request.video_ids:
        logger.info("Step 2: Fetching video info from BigQuery (batch query)...")
        videos_info = get_videos_info_by_ids(request.video_ids)
        logger.info(f"  Found {len(videos_info)}/{len(request.video_ids)} videos in BigQuery")
        logger.info("")

    # Step 3: Collect all paths for batch existence check
    all_paths_to_check = []
    path_to_item_map = {}  # Map path → item info

    # Add intro
    if intro_path:
        all_paths_to_check.append(intro_path)
        path_to_item_map[intro_path] = {'type': 'intro', 'position': position}
        position += 1

    # Add videos from BigQuery
    for video_id in request.video_ids:
        if video_id in videos_info:
            path = videos_info[video_id]["path"]
            all_paths_to_check.append(path)
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
        all_paths_to_check.append(manual_path)
        path_to_item_map[manual_path] = {
            'type': 'transition',  # Assume transition (can be updated later)
            'position': position
        }
        position += 1

    # Add outro
    if outro_path:
        all_paths_to_check.append(outro_path)
        path_to_item_map[outro_path] = {'type': 'outro', 'position': position}

    # Step 4: Batch check all paths exist
    logger.info("Step 3: Batch checking all paths exist...")
    logger.info(f"  Checking {len(all_paths_to_check)} paths")

    path_existence = check_paths_exist(all_paths_to_check)
    available_count = sum(1 for exists in path_existence.values() if exists)
    logger.info(f"  {available_count}/{len(all_paths_to_check)} paths available")
    logger.info("")

    # Step 5: Batch get video info (duration + resolution) for available paths
    logger.info("Step 4: Getting video info (duration + resolution) in parallel...")
    available_paths = [path for path, exists in path_existence.items() if exists]

    # Normalize paths before passing to ffprobe
    normalized_paths = normalize_paths(available_paths)

    # Batch get video info (parallel ffprobe calls)
    videos_info_batch = get_videos_info_batch(normalized_paths, max_workers=5)

    # Map back to original paths
    path_video_info = {}
    for original, normalized in zip(available_paths, normalized_paths):
        path_video_info[original] = videos_info_batch.get(normalized)

    success_info_count = sum(1 for info in path_video_info.values() if info is not None)
    logger.info(f"  Got video info for {success_info_count}/{len(available_paths)} available videos")
    logger.info("")

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

        # Get path existence
        exists = path_existence.get(path, False)

        # Get video info if path exists
        duration = None
        resolution = None
        is_4k = None

        if exists:
            video_info = path_video_info.get(path)
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
    logger.info("=== Verification Summary ===")
    logger.info(f"Total items: {len(items)}")
    logger.info(f"Available: {available_count}")
    logger.info(f"Missing: {missing_count}")
    logger.info(f"Total duration: {total_duration:.2f}s ({total_duration/60:.2f} min)")

    if missing_count == 0:
        logger.info("Result: SUCCESS")
    elif missing_count < len(items):
        logger.info(f"Result: PARTIAL - {missing_count} items need attention")
    else:
        logger.info("Result: FAILED - All items missing")

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
                'text_animation_words': item.text_animation_words or []
            })

        supabase.table('job_items').insert(items_data).execute()

        # 4. Queue Celery task (implemented in task5)
        # from workers.tasks import process_compilation
        # queue_name = '4k_queue' if request.enable_4k else 'default_queue'
        # process_compilation.apply_async(args=[job_id], queue=queue_name)

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
```

---

## 5. Image Upload Routes

**File: `backend/api/routes/uploads.py`**

**IMPORTANT: Docker Volume Mapping Required**

Add to `docker-compose.yml` under backend service volumes:
```yaml
volumes:
  - ./backend:/app
  - /app/venv
  - ./logs:/app/logs
  - ./temp:/app/temp
  - ./uploads:/app/uploads  # ← Add this for persistent image uploads
```

**And for worker nodes (`docker-compose.worker.yml`):**
```yaml
volumes:
  - ./backend:/app
  - /app/venv
  - ./logs:/app/logs
  - ./temp:/app/temp
  - ./uploads:/app/uploads  # ← Add this so workers can access uploaded images
```

---

```python
from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import uuid
import shutil
from typing import Optional

router = APIRouter(prefix="/uploads", tags=["uploads"])

UPLOAD_DIR = Path("uploads/images")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    """
    Upload an image file for use in compilation.
    Images can be inserted as static slides with custom duration.

    Returns:
        dict: Contains filename, path, and file size
    """
    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Generate unique filename
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = UPLOAD_DIR / unique_filename

    # Save file
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Validate file size
        file_size = file_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            file_path.unlink()
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024}MB"
            )

    except Exception as e:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    return {
        "filename": unique_filename,
        "path": str(file_path),
        "size": file_size
    }

@router.delete("/image/{filename}")
async def delete_image(filename: str):
    """Delete an uploaded image"""
    # Validate filename (prevent path traversal)
    if '/' in filename or '\\' in filename or '..' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = UPLOAD_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        file_path.unlink()
        return {"message": "File deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

@router.get("/image/{filename}")
async def get_image(filename: str):
    """Get info about an uploaded image"""
    # Validate filename
    if '/' in filename or '\\' in filename or '..' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = UPLOAD_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return {
        "filename": filename,
        "path": str(file_path),
        "size": file_path.stat().st_size
    }
```

**Register in `backend/api/main.py`:**

```python
from api.routes import jobs, uploads

app.include_router(jobs.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")
```

---

## 6. Admin Routes

**File: `backend/api/routes/admin.py`**

Update the placeholder admin routes file with cache management:

```python
from fastapi import APIRouter
from services.bigquery import clear_channels_cache

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
    from services.bigquery import _channels_cache, CACHE_TTL
    import time

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
```

**Usage:**

```bash
# Clear cache after adding a new channel
curl -X POST http://localhost:8000/api/admin/clear-channels-cache

# Check cache status
curl http://localhost:8000/api/admin/cache-status
```

---

## 7. Test the Endpoints

### 1. Get all channels:
**Note:** This would typically be called from frontend, not curl. For testing purposes, you can call `get_all_channels()` directly in Python or add a temporary test endpoint.

```python
# Test in Python
from services.bigquery import get_all_channels
channels = get_all_channels()
print(f"Channels: {channels}")
```

**Or add temporary test endpoint in admin.py:**
```python
@router.get("/channels")
async def get_channels_list():
    """Get list of all channels (for testing)"""
    from services.bigquery import get_all_channels
    channels = get_all_channels()
    return {"channels": channels, "count": len(channels)}
```

**Then test with:**
```bash
curl http://localhost:8000/api/admin/channels
```

---

### 2. Verify job (bulk verification):
```bash
curl -X POST "http://localhost:8000/api/jobs/verify?user_id=<user-uuid>" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_name": "YBH Official",
    "video_ids": ["TJU5wYdTG4c", "ABC123xyz", "DEF456abc"],
    "manual_paths": []
  }'
```

**Expected response:**
```json
{
  "default_logo_path": "\\\\192.168.1.6\\Share3\\Assets\\logo_ybh.png",
  "total_duration": 1850.5,
  "items": [
    {
      "position": 1,
      "item_type": "intro",
      "path": "\\\\192.168.1.6\\Share3\\Assets\\intro_ybh.mp4",
      "path_available": true,
      "duration": 10.5,
      "resolution": "1920x1080",
      "is_4k": false
    },
    {
      "position": 2,
      "item_type": "video",
      "video_id": "TJU5wYdTG4c",
      "title": "Amazing Video Title",
      "path": "\\\\192.168.1.6\\Share3\\YBH\\video_001.mp4",
      "path_available": true,
      "logo_path": "\\\\192.168.1.6\\Share3\\Assets\\logo_ybh.png",
      "duration": 120.5,
      "resolution": "1920x1080",
      "is_4k": false
    }
  ]
}
```

**Log created at:** `logs/2025-11-20/Uzasch/verify/14-30-45-123.log`

---

### 3. Verify single manual path:
```bash
curl -X POST "http://localhost:8000/api/jobs/verify?user_id=<user-uuid>" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_name": "YBH Official",
    "video_ids": [],
    "manual_paths": ["V:\\Production\\Kids\\transition.mp4"]
  }'
```

---

### 4. Submit job:
```bash
curl -X POST "http://localhost:8000/api/jobs/submit" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "<user-uuid>",
    "channel_name": "YBH Official",
    "enable_4k": false,
    "items": [
      {
        "position": 1,
        "item_type": "intro",
        "path": "\\\\192.168.1.6\\Share3\\Assets\\intro_ybh.mp4",
        "path_available": true,
        "duration": 10.5
      },
      {
        "position": 2,
        "item_type": "video",
        "video_id": "TJU5wYdTG4c",
        "title": "Amazing Video",
        "path": "\\\\192.168.1.6\\Share3\\YBH\\video_001.mp4",
        "path_available": true,
        "logo_path": "\\\\192.168.1.6\\Share3\\Assets\\logo_ybh.png",
        "duration": 120.5
      }
    ]
  }'
```

**Expected response:**
```json
{
  "job_id": "abc-123-def-456",
  "status": "queued"
}
```

---

### 5. Get job status:
```bash
curl http://localhost:8000/api/jobs/abc-123-def-456
```

---

### 6. Get queue stats:
```bash
curl "http://localhost:8000/api/jobs/queue/stats?user_id=<user-uuid>"
```

**Expected response:**
```json
{
  "total_in_queue": 5,
  "active_workers": 3,
  "user_jobs": [
    {
      "job_id": "abc-123",
      "channel_name": "YBH Official",
      "queue_position": 2,
      "is_processing": true,
      "status": "processing",
      "waiting_count": 0
    }
  ],
  "available_slots": 0
}
```

---

### 7. Upload image:
```bash
curl -X POST http://localhost:8000/api/uploads/image \
  -F "file=@/path/to/image.png"
```

---

### 8. Admin - Clear cache:
```bash
curl -X POST http://localhost:8000/api/admin/clear-channels-cache
```

---

### 9. Admin - Check cache status:
```bash
curl http://localhost:8000/api/admin/cache-status
```

**Expected response:**
```json
{
  "cached": true,
  "channels_count": 15,
  "cache_age_seconds": 7200,
  "cache_remaining_seconds": 79200,
  "is_expired": false
}
```

---

## Checklist

### Section 1: BigQuery Service
- [ ] `get_bigquery_client()` - cached client
- [ ] `get_videos_info_by_ids()` - **batch query** for videos (path + title)
- [ ] `get_asset_path()` - fetch logo/intro/outro
- [ ] `get_all_channels()` - with **24-hour TTL cache**
- [ ] `get_production_path()` - fetch production path per channel
- [ ] `clear_channels_cache()` - manual cache clearing
- [ ] `insert_compilation_result()` - analytics insert
- [ ] All functions use **proper logging** (not print statements)

### Section 2: Storage Service
- [ ] `normalize_paths()` - multi-format path normalization (UNC, drive letters, SMB URLs, macOS)
- [ ] `check_paths_exist()` - **parallel** path existence checking (10 workers)
- [ ] `copy_file_sequential()` - robocopy with shutil fallback
- [ ] Drive letter mappings configured (Share→S:, Share2→T:, etc.)

### Section 3: Video Utilities
- [ ] `get_video_info()` - combined duration + resolution in single ffprobe call
- [ ] `get_videos_info_batch()` - **parallel** batch processing (5 workers)
- [ ] Returns dict with duration, width, height, is_4k

### Section 4: Validation Logger
- [ ] `setup_validation_logger()` - single logger for all /verify calls
- [ ] Logs both INFO and ERROR levels
- [ ] File-only logging (no console output)
- [ ] Logs created in correct structure: `logs/{date}/{username}/verify/{timestamp}.log`

### Section 5: Job Routes
- [ ] `/verify` endpoint - smart verification (bulk + single item)
  - [ ] Fetches all videos in 1 BigQuery call (batch)
  - [ ] Parallel path existence checking
  - [ ] Parallel ffprobe for video info
  - [ ] Logs to verify folder
- [ ] `/submit` endpoint - job submission (no verification, already done)
- [ ] `/{job_id}` endpoint - job status lookup
- [ ] `/queue/stats` endpoint - dynamic worker count from Celery
- [ ] `/{job_id}/move-to-production` endpoint - uses production path from BigQuery

### Section 5 (Subsection): Image Upload Routes
- [ ] `/uploads/image` - image upload endpoint
- [ ] `/uploads/image/{filename}` DELETE - image delete endpoint
- [ ] `/uploads/image/{filename}` GET - image info endpoint
- [ ] File validation (size: 10MB max, type: jpg/png/gif/bmp/webp)

### Section 6: Admin Routes
- [ ] `/admin/clear-channels-cache` - clear cache endpoint
- [ ] `/admin/cache-status` - check cache status with age/TTL

### Testing
- [ ] Tested with real video IDs from BigQuery
- [ ] Batch query performs faster than individual queries (30 queries → 1 query)
- [ ] Parallel path checks faster (1.7s → 0.2s for 17 paths)
- [ ] Parallel ffprobe faster (15s → 3s for 15 videos)
- [ ] Cache TTL works correctly (24 hours)
- [ ] Manual cache clear works
- [ ] Validation logs created correctly
- [ ] Supabase tables populated correctly
- [ ] Dynamic worker count from Celery works

---

## Next: Task 5
Implement Celery workers and FFmpeg processing.
