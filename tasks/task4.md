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

def get_video_path_by_id(video_id: str) -> Optional[str]:
    """
    Fetch video path from BigQuery by video_id.
    Returns the SMB path or None if not found.
    """
    client = get_bigquery_client()

    query = """
    SELECT path_nyt
    FROM `ybh-deployment-testing.ybh_assest_path.path`
    WHERE video_id = @video_id
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("video_id", "STRING", video_id)
        ]
    )

    try:
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()

        rows = list(results)
        if rows:
            path = rows[0]["path_nyt"]
            # Remove quotes if present
            if path and path.startswith('"') and path.endswith('"'):
                path = path[1:-1]
            return path
        return None

    except Exception as e:
        print(f"Error querying BigQuery for video_id {video_id}: {e}")
        return None

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
        print(f"Error querying BigQuery for {asset_type} of {channel_name}: {e}")
        return None

def get_all_channels() -> List[str]:
    """Get list of all channel names from BigQuery"""
    client = get_bigquery_client()

    query = """
    SELECT channel_name
    FROM `ybh-deployment-testing.ybh_assest_path.branding_assets`
    ORDER BY channel_name
    """

    try:
        query_job = client.query(query)
        results = query_job.result()
        return [row["channel_name"] for row in results]

    except Exception as e:
        print(f"Error fetching channels from BigQuery: {e}")
        return []

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
            print(f"BigQuery insert errors: {errors}")
            return False
        return True

    except Exception as e:
        print(f"Error inserting to BigQuery: {e}")
        return False
```

---

## 2. Storage Service (SMB Operations)

**File: `backend/services/storage.py`**

```python
import os
import shutil
from pathlib import Path
from api.config import get_settings

def convert_path_to_unix_style(path: str) -> str:
    """Convert Windows path to Unix-style for os.path operations"""
    if path:
        # Replace forward slashes with backslashes for Windows
        return path.replace("/", "\\")
    return path

def normalize_path_for_server(path: str) -> str:
    """Normalize path for SMB server access"""
    # Convert path and ensure proper format
    path = convert_path_to_unix_style(path)
    # Remove any quotes
    if path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    return path

def path_exists(path: str) -> bool:
    """Check if SMB path exists"""
    try:
        normalized = normalize_path_for_server(path)
        return os.path.exists(normalized)
    except Exception as e:
        print(f"Error checking path existence: {e}")
        return False

def copy_file_to_temp(source_path: str, job_id: str, filename: str) -> str:
    """
    Copy file from SMB to local temp directory.

    Returns: Local temp path
    """
    settings = get_settings()
    temp_dir = Path(settings.temp_dir) / str(job_id)
    temp_dir.mkdir(parents=True, exist_ok=True)

    source = normalize_path_for_server(source_path)
    dest = temp_dir / filename

    shutil.copy2(source, dest)

    return str(dest)

def copy_file_to_output(source_path: str, filename: str) -> str:
    """
    Copy processed file to SMB output directory.

    Returns: Output SMB path
    """
    settings = get_settings()
    output_dir = Path(settings.smb_output_path)

    dest = output_dir / filename
    shutil.copy2(source_path, dest)

    return str(dest)

def cleanup_temp_dir(job_id: str):
    """Clean up temp directory for a job"""
    settings = get_settings()
    temp_dir = Path(settings.temp_dir) / str(job_id)

    if temp_dir.exists():
        shutil.rmtree(temp_dir)
```

---

## 3. Video Utilities

**File: `backend/utils/video_utils.py`**

```python
import subprocess
import re
import json

def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            video_path
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return float(result.stdout.strip())
        return 0.0

    except Exception as e:
        print(f"Error getting video duration: {e}")
        return 0.0

def get_video_resolution(video_path: str) -> tuple:
    """
    Get video resolution (width, height) using ffprobe.

    Returns: (width, height) or (0, 0) if error
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'json',
            video_path
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            if 'streams' in data and len(data['streams']) > 0:
                stream = data['streams'][0]
                width = stream.get('width', 0)
                height = stream.get('height', 0)
                return (width, height)

        return (0, 0)

    except Exception as e:
        print(f"Error getting video resolution: {e}")
        return (0, 0)

def is_4k_video(video_path: str) -> bool:
    """Check if video is 4K (3840x2160 or higher)"""
    width, height = get_video_resolution(video_path)
    return width >= 3840 and height >= 2160
```

---

## 4. Job Routes - Validation

**File: `backend/api/routes/jobs.py`**

```python
from fastapi import APIRouter, HTTPException
from api.models import (
    ValidationRequest, ValidationResponse, VideoValidation,
    JobCreate, JobSubmitResponse, JobStatus
)
from services.bigquery import get_video_path_by_id, get_asset_path
from services.storage import path_exists, normalize_path_for_server
from services.supabase import get_supabase_client
from utils.video_utils import get_video_duration, get_video_resolution, is_4k_video
from uuid import uuid4

router = APIRouter()

@router.post("/validate", response_model=ValidationResponse)
async def validate_videos(request: ValidationRequest):
    """
    Validate videos before submission.
    Check if video IDs exist in BigQuery and paths are accessible.
    """
    validations = []
    all_valid = True

    # Validate each video
    for video in request.videos:
        validation = VideoValidation(
            video_id=video.video_id,
            video_path=video.video_path,
            exists=False
        )

        try:
            # Get path from BigQuery if video_id provided
            if video.video_id:
                path = get_video_path_by_id(video.video_id)
                if path:
                    validation.video_path = path
                else:
                    validation.error = f"Video ID {video.video_id} not found in database"
                    all_valid = False
                    validations.append(validation)
                    continue

            # Check if path exists
            if validation.video_path:
                normalized_path = normalize_path_for_server(validation.video_path)
                exists = path_exists(normalized_path)
                validation.exists = exists

                if exists:
                    # Get video metadata
                    validation.duration = get_video_duration(normalized_path)
                    width, height = get_video_resolution(normalized_path)
                    validation.resolution = f"{width}x{height}"
                    validation.is_4k = is_4k_video(normalized_path)
                else:
                    validation.error = "Video file not found at path"
                    all_valid = False
            else:
                validation.error = "No video path provided"
                all_valid = False

        except Exception as e:
            validation.error = str(e)
            all_valid = False

        validations.append(validation)

    # Validate assets if requested
    response_data = {
        "videos": validations,
        "all_valid": all_valid
    }

    if request.check_logo:
        logo_path = get_asset_path("logo", request.channel_name)
        if logo_path:
            response_data["logo"] = {
                "exists": path_exists(normalize_path_for_server(logo_path)),
                "path": logo_path
            }
        else:
            response_data["logo"] = {"exists": False, "path": None}
            all_valid = False

    if request.check_intro:
        intro_path = get_asset_path("intro", request.channel_name)
        if intro_path:
            response_data["intro"] = {
                "exists": path_exists(normalize_path_for_server(intro_path)),
                "path": intro_path
            }
        else:
            response_data["intro"] = {"exists": False, "path": None}
            all_valid = False

    if request.check_end_packaging:
        end_path = get_asset_path("end_packaging", request.channel_name)
        if end_path:
            response_data["end_packaging"] = {
                "exists": path_exists(normalize_path_for_server(end_path)),
                "path": end_path
            }
        else:
            response_data["end_packaging"] = {"exists": False, "path": None}
            all_valid = False

    response_data["all_valid"] = all_valid
    return ValidationResponse(**response_data)

@router.post("/submit", response_model=JobSubmitResponse)
async def submit_job(job: JobCreate, user_id: str):
    """
    Submit a new compilation job.
    Creates job in Supabase and queues it for processing.
    """
    supabase = get_supabase_client()

    try:
        job_id = uuid4()

        # Create job in Supabase
        job_data = {
            "job_id": str(job_id),
            "user_id": user_id,
            "channel_name": job.channel_name,
            "status": "queued",
            "progress": 0,
            "has_intro": job.has_intro,
            "has_end_packaging": job.has_end_packaging,
            "has_logo": job.has_logo,
            "enable_4k": job.enable_4k,
            "text_animation_enabled": job.text_animation_enabled,
            "text_animation_words": job.text_animation_words or []
        }

        result = supabase.table("jobs").insert(job_data).execute()

        if not result.data:
            raise Exception("Failed to create job in database")

        # Insert job videos
        for video in job.videos:
            video_data = {
                "job_id": str(job_id),
                "video_id": video.video_id,
                "video_path": video.video_path,
                "position": video.position,
                "filters": video.filters
            }
            supabase.table("job_videos").insert(video_data).execute()

        # Insert packaging inserts if any
        if job.packaging_inserts:
            for insert in job.packaging_inserts:
                insert_data = {
                    "job_id": str(job_id),
                    "insert_after_position": insert.insert_after_position,
                    "packaging_video_id": insert.packaging_video_id,
                    "packaging_video_path": insert.packaging_video_path,
                    "packaging_name": insert.packaging_name
                }
                supabase.table("job_packaging_inserts").insert(insert_data).execute()

        # TODO: Queue the job with Celery (Task 5)

        return JobSubmitResponse(
            job_id=job_id,
            status="queued",
            message="Job submitted successfully"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit job: {str(e)}")

@router.get("/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get job status by job_id"""
    supabase = get_supabase_client()

    try:
        result = supabase.table("jobs").select("*").eq("job_id", job_id).execute()

        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=404, detail="Job not found")

        return JobStatus(**result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {str(e)}")
```

---

## 5. Test the Endpoints

### 1. Get all channels:
```bash
curl http://localhost:8000/api/channels
```

### 2. Validate videos:
```bash
curl -X POST http://localhost:8000/api/jobs/validate \
  -H "Content-Type: application/json" \
  -d '{
    "videos": [
      {"video_id": "TJU5wYdTG4c", "position": 1}
    ],
    "channel_name": "YourChannel",
    "check_logo": true
  }'
```

### 3. Submit job:
```bash
curl -X POST http://localhost:8000/api/jobs/submit?user_id=<user-uuid> \
  -H "Content-Type: application/json" \
  -d '{
    "channel_name": "TestChannel",
    "videos": [
      {"video_id": "video1", "position": 1},
      {"video_id": "video2", "position": 2}
    ],
    "has_logo": true
  }'
```

---

## Checklist

- [ ] BigQuery service implemented
- [ ] Storage service (SMB operations) implemented
- [ ] Video utilities implemented
- [ ] Validation endpoint works
- [ ] Job submission endpoint works
- [ ] Job status endpoint works
- [ ] Tested with real video IDs
- [ ] Supabase tables populated correctly

---

## Next: Task 5
Implement Celery workers and FFmpeg processing.
