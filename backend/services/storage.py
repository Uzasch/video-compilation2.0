import os
import subprocess
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from api.config import get_settings

logger = logging.getLogger(__name__)

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

# Docker mount path mappings (when running in Docker container)
DOCKER_MOUNTS = {
    "Share": "/mnt/share",
    "Share2": "/mnt/share2",
    "Share3": "/mnt/share3",
    "Share4": "/mnt/share4",
    "Share5": "/mnt/share5",
}

# Check if running in Docker with isolated network (needs mount conversion)
# If using host network mode on Windows, drives are directly accessible
IS_DOCKER = os.path.exists("/.dockerenv") and not os.path.exists("V:\\")

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
                if IS_DOCKER and share_name in DOCKER_MOUNTS:
                    # Convert to Docker mount path
                    path = f"{DOCKER_MOUNTS[share_name]}/{remaining}".replace("\\", "/")
                else:
                    # Convert to UNC path
                    path = f"\\\\192.168.1.6\\{share_name}\\{remaining}"
            normalized.append(path)
            continue

        # Case 4: Already Windows UNC (\\192.168.1.6\...)
        if path.startswith("\\\\"):
            # Extract share name from UNC path
            parts = path.split("\\")
            if len(parts) >= 4:
                share_name = parts[3]  # \\192.168.1.6\Share3\...
                remaining = "\\".join(parts[4:])

                if IS_DOCKER and share_name in DOCKER_MOUNTS:
                    # Convert to Docker mount path
                    path = f"{DOCKER_MOUNTS[share_name]}/{remaining}".replace("\\", "/")
                else:
                    # Keep as UNC
                    path = path.replace("/", "\\")
            normalized.append(path)
            continue

        # Case 5: Unknown format - keep as is
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
