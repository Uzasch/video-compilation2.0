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
            # Extract share name and remaining path
            # smb://192.168.1.6/Share3/Public/video -> Share3, Public/video
            parts = path.replace("smb://", "").split("/")
            if len(parts) >= 2:
                share_name = parts[1]  # e.g., "Share3"
                remaining = "/".join(parts[2:]) if len(parts) > 2 else ""

                if IS_DOCKER and share_name in DOCKER_MOUNTS:
                    # Convert to Docker mount path
                    path = f"{DOCKER_MOUNTS[share_name]}/{remaining}".rstrip("/")
                else:
                    # Convert to UNC path
                    path = f"\\\\192.168.1.6\\{share_name}\\{remaining}".replace("/", "\\")
            else:
                # Fallback: simple conversion
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

                if IS_DOCKER and share_name in DOCKER_MOUNTS:
                    # Convert to Docker mount path
                    path = f"{DOCKER_MOUNTS[share_name]}/{remaining}".rstrip("/")
                else:
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
    use_optimal_method: bool = True
) -> Optional[str]:
    """
    Copy a single file with automatic method selection and fallback chain.

    Fallback chain (Docker/Linux):
      1. rsync (fastest, 3.5x faster than alternatives)
      2. cp (fallback, still faster than shutil)
      3. shutil (final fallback, cross-platform)

    Windows fallback chain:
      1. robocopy (fastest for Windows)
      2. shutil (final fallback)

    Args:
        source_path: Source file path (any format)
        dest_dir: Destination directory
        dest_filename: Optional destination filename (if None, use original name)
        use_optimal_method: If True, try OS-specific optimal method first; if False, use shutil only

    Returns:
        Destination file path if success, None if failed

    Performance (Docker, 695MB test):
        - rsync: 14-20s (FASTEST)
        - cp: 46-75s
        - shutil: 42-124s

    Note:
        For copying multiple files, use copy_files_parallel() for 3.5x speedup

    Example:
        Input:
            source_path = "V:\\Production\\video.mp4"
            dest_dir = "temp/abc-123"
            dest_filename = "video_001.mp4"

        Output: "temp/abc-123/video_001.mp4"
    """
    # Log parameters for debugging
    logger.info(f"copy_file_sequential called:")
    logger.info(f"  source_path: {source_path}")
    logger.info(f"  dest_dir: {dest_dir}")
    logger.info(f"  dest_filename: {dest_filename}")

    # Normalize source path
    normalized_source = normalize_paths([source_path])[0]
    source_file_path = Path(normalized_source)

    # Prepare destination
    dest_path = Path(dest_dir)
    dest_path.mkdir(parents=True, exist_ok=True)

    # Build dest_file path with consistent slashes (avoid Path / operator mixing slashes)
    if dest_filename:
        filename = dest_filename
        logger.info(f"  Using provided dest_filename: {filename}")
    else:
        filename = source_file_path.name
        logger.info(f"  Using source filename: {filename}")

    # Use appropriate separator based on path type
    if dest_dir.startswith('\\\\'):
        dest_file_str = f"{dest_dir}\\{filename}"
    else:
        dest_file_str = f"{dest_dir}/{filename}"
    dest_file = Path(dest_file_str)

    # Check if source exists
    if not source_file_path.exists():
        logger.error(f"Source file not found: {normalized_source}")
        return None

    # Check if destination already exists (skip if prefetched)
    if dest_file.exists():
        source_size = source_file_path.stat().st_size
        dest_size = dest_file.stat().st_size
        if source_size == dest_size:
            logger.info(f"  Skipping (already exists): {dest_file.name}")
            return dest_file_str  # Return consistent path string
        else:
            logger.warning(f"  File exists but size mismatch ({dest_size} != {source_size}), re-copying: {dest_file.name}")

    if not use_optimal_method:
        # Skip to shutil directly
        if _copy_with_shutil(normalized_source, dest_file):
            return dest_file_str
        return None

    # ========== LINUX / DOCKER ==========
    if IS_DOCKER:
        # Method 1: Try rsync (best for network shares)
        if is_rsync_available():
            if _copy_with_rsync(normalized_source, dest_file):
                return dest_file_str
            logger.warning("rsync failed, trying cp fallback")

        # Method 2: Try cp with retry logic
        if is_cp_available():
            if _copy_with_cp(normalized_source, dest_file):
                return dest_file_str
            logger.warning("cp failed, trying shutil fallback")

        # Method 3: Final fallback to shutil
        if _copy_with_shutil(normalized_source, dest_file):
            return dest_file_str
        return None

    # ========== WINDOWS ==========
    else:
        # Method 1: Try robocopy
        if _copy_with_robocopy(source_file_path, dest_path, dest_file):
            return dest_file_str
        logger.warning("robocopy failed, trying shutil fallback")

        # Method 2: Final fallback to shutil
        if _copy_with_shutil(normalized_source, dest_file):
            return dest_file_str
        return None


def _copy_with_rsync(source: str, dest: Path) -> Optional[str]:
    """
    Copy file using rsync (Linux - best for network shares).

    Timeout calculation:
        - Base: 300s (5 min) for files < 1GB
        - Large files: file_size_gb * 120s per GB
        - Min: 300s, Max: 3600s (1 hour)

    Examples:
        - 500 MB file: 300s (5 min)
        - 5 GB file: 600s (10 min)
        - 10 GB file: 1200s (20 min)
        - 50 GB file: 3600s (1 hour, capped)
    """
    try:
        # Calculate dynamic timeout based on file size
        file_size_bytes = os.path.getsize(source)
        file_size_gb = file_size_bytes / (1024 ** 3)

        # Dynamic timeout: 120 seconds per GB, min 300s, max 3600s (1 hour)
        io_timeout = max(300, min(3600, int(file_size_gb * 120)))
        process_timeout = io_timeout + 60  # Add 60s buffer for process overhead

        logger.info(f"File size: {file_size_gb:.2f} GB, timeout: {io_timeout}s")

        # Ensure dest is a full file path, not a directory
        dest_str = str(dest)
        logger.info(f"rsync dest path: {dest_str}")
        logger.info(f"rsync dest name: {dest.name}")

        cmd = [
            "rsync",
            f"--timeout={io_timeout}",  # Dynamic I/O timeout based on file size
            "--no-compress",            # Don't compress (video files are already compressed)
            "--whole-file",             # Copy entire file (faster for large files, no delta transfer)
            source,
            dest_str
        ]

        logger.info(f"Copying with rsync: {source} → {dest_str}")
        logger.info(f"rsync command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=process_timeout)

        if result.returncode == 0:
            # Verify the file was created with correct name
            if dest.exists():
                logger.info(f"✓ rsync successful: {dest_str}")
                return dest_str
            else:
                # Check if file was created with wrong name (rsync bug with directories)
                parent_dir = dest.parent
                source_name = Path(source).name
                wrong_dest = parent_dir / source_name
                if wrong_dest.exists():
                    logger.warning(f"rsync created file with source name, renaming: {wrong_dest} → {dest}")
                    wrong_dest.rename(dest)
                    return dest_str
                logger.warning(f"rsync returned success but file not found: {dest_str}")
                return None
        else:
            logger.warning(f"rsync failed (code {result.returncode}): {result.stderr}")
            return None

    except Exception as e:
        logger.warning(f"rsync error: {e}")
        return None


def _copy_with_cp(source: str, dest: Path) -> Optional[str]:
    """Copy file using cp with retry logic (Linux fallback)"""
    # Calculate dynamic timeout based on file size
    file_size_bytes = os.path.getsize(source)
    file_size_gb = file_size_bytes / (1024 ** 3)
    timeout = max(300, min(3600, int(file_size_gb * 120)))

    for attempt in range(3):
        try:
            cmd = ["cp", source, str(dest)]

            logger.info(f"Copying with cp (attempt {attempt + 1}/3): {source} → {dest}")
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, check=True)

            logger.info(f"✓ cp successful: {dest}")
            return str(dest)

        except subprocess.CalledProcessError as e:
            if attempt < 2:
                logger.warning(f"cp failed (attempt {attempt + 1}/3), retrying in 5 seconds...")
                time.sleep(5)
            else:
                logger.warning(f"cp failed after 3 attempts: {e.stderr}")
                return None
        except Exception as e:
            logger.warning(f"cp error: {e}")
            return None

    return None


def _copy_with_robocopy(source_file_path: Path, dest_path: Path, dest_file: Path) -> Optional[str]:
    """Copy file using robocopy (Windows)"""
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

        logger.info(f"Copying with robocopy: {source_file_path} → {dest_file}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)

        # Robocopy exit codes: 0-7 are success, 8+ are errors
        if result.returncode < 8:
            # Rename if needed
            temp_dest = dest_path / source_filename
            if temp_dest.exists() and temp_dest != dest_file:
                temp_dest.rename(dest_file)

            logger.info(f"✓ robocopy successful: {dest_file}")
            return str(dest_file)
        else:
            logger.warning(f"robocopy failed (code {result.returncode})")
            return None

    except Exception as e:
        logger.warning(f"robocopy error: {e}")
        return None


def _copy_with_shutil(source: str, dest: Path) -> Optional[str]:
    """Copy file using shutil (cross-platform fallback)"""
    try:
        logger.info(f"Copying with shutil: {source} → {dest}")
        logger.info(f"shutil dest name: {dest.name}")
        shutil.copy(source, dest)  # copy() not copy2() - no metadata

        # Verify the file was created with correct name
        if dest.exists():
            logger.info(f"✓ shutil copy successful: {dest}")
            return str(dest)
        else:
            # Check if shutil created file with wrong name
            parent_dir = dest.parent
            source_name = Path(source).name
            wrong_dest = parent_dir / source_name
            if wrong_dest.exists():
                logger.warning(f"shutil created file with source name, renaming: {wrong_dest} → {dest}")
                wrong_dest.rename(dest)
                return str(dest)
            logger.warning(f"shutil reported success but file not found: {dest}")
            return None

    except Exception as e:
        logger.error(f"✗ shutil copy failed {source}: {e}", exc_info=True)
        return None

def copy_files_parallel(
    source_files: List[Dict[str, str]],
    dest_dir: str,
    max_workers: int = 5,
    job_logger: logging.Logger = None,
    job_id: str = None
) -> Dict[str, Optional[str]]:
    """
    Copy multiple files in parallel using ThreadPoolExecutor.

    This provides 3.5x speedup compared to sequential copying when using rsync.

    Performance (Docker, 5 files, 695MB total):
        - Parallel (5 workers): 14.78s @ ~47 MB/s per file (FASTEST)
        - Sequential: 74.83s @ ~10 MB/s per file
        - Speedup: 5.06x faster with parallel

    Args:
        source_files: List of dicts with keys:
            - 'source_path': Source file path
            - 'dest_filename': Destination filename
        dest_dir: Destination directory (same for all files)
        max_workers: Number of parallel workers (default: 5, optimal for most cases)

    Returns:
        Dict mapping dest_filename to destination path (or None if failed)

    Example:
        files = [
            {'source_path': '\\\\nas\\video1.mp4', 'dest_filename': 'video_001.mp4'},
            {'source_path': '\\\\nas\\video2.mp4', 'dest_filename': 'video_002.mp4'},
            {'source_path': '\\\\nas\\video3.mp4', 'dest_filename': 'video_003.mp4'},
        ]
        results = copy_files_parallel(files, 'temp/job-123', max_workers=5)
        # Returns: {
        #   'video_001.mp4': 'temp/job-123/video_001.mp4',
        #   'video_002.mp4': 'temp/job-123/video_002.mp4',
        #   'video_003.mp4': None  # Failed to copy
        # }
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    log = job_logger or logger  # Use job logger if provided, else module logger

    if not source_files:
        return results

    log.info(f"Starting parallel copy of {len(source_files)} files with {max_workers} workers")

    def copy_single_wrapper(file_info):
        """Wrapper for parallel execution"""
        source_path = file_info['source_path']
        dest_filename = file_info['dest_filename']

        log.info(f"  Copying: {dest_filename}")
        try:
            result_path = copy_file_sequential(
                source_path=source_path,
                dest_dir=dest_dir,
                dest_filename=dest_filename,
                use_optimal_method=True
            )
            return dest_filename, result_path
        except Exception as e:
            logger.error(f"Error copying {dest_filename}: {e}", exc_info=True)
            return dest_filename, None

    # Execute copies in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(copy_single_wrapper, file_info): file_info
            for file_info in source_files
        }

        for future in as_completed(futures):
            dest_filename, result_path = future.result()
            results[dest_filename] = result_path

            if result_path:
                log.info(f"  ✓ Copied: {dest_filename}")
            else:
                log.error(f"  ✗ Failed: {dest_filename}")

            # Update progress and check for cancellation after each file completes
            if job_id:
                try:
                    from services.supabase import get_supabase_client
                    supabase = get_supabase_client()
                    copied_count = sum(1 for v in results.values() if v is not None)
                    total_count = len(source_files)
                    supabase.table('jobs').update({
                        'progress_message': f'Copying files... ({copied_count}/{total_count})'
                    }).eq('job_id', job_id).execute()
                    job_status = supabase.table('jobs').select('status').eq('job_id', job_id).execute()
                    if job_status.data and job_status.data[0].get('status') == 'cancelled':
                        log.warning(f"Job {job_id} cancelled - aborting remaining copies")
                        for f in futures:
                            f.cancel()
                        raise Exception("Job cancelled by user during file copy")
                except Exception as e:
                    if "cancelled by user" in str(e).lower():
                        raise
                    log.debug(f"Progress/cancellation check failed: {e}")

    # Summary
    successful = sum(1 for v in results.values() if v is not None)
    failed = len(results) - successful
    log.info(f"Parallel copy completed: {successful} succeeded, {failed} failed")

    return results


def normalize_path_for_server(path: str) -> str:
    """
    Normalize a single path (wrapper for normalize_paths that returns single path).

    Args:
        path: Path in any format

    Returns:
        Normalized path (UNC on Windows, Docker mount on Linux)
    """
    return normalize_paths([path])[0]


def convert_path_for_client(path: str, client_os: str = "windows") -> str:
    """
    Convert a UNC path to user-friendly format based on client OS.

    Args:
        path: UNC path (e.g., \\\\192.168.1.6\\Share3\\Public\\video.mp4)
        client_os: Target OS - "windows" or "mac"

    Returns:
        User-friendly path:
        - Windows: U:\\Public\\video.mp4
        - Mac: /Volumes/Share3/Public/video.mp4

    Example:
        Input: "\\\\192.168.1.6\\Share3\\Public\\video-compilation\\user\\file.mp4"
        Windows Output: "U:\\Public\\video-compilation\\user\\file.mp4"
        Mac Output: "/Volumes/Share3/Public/video-compilation/user/file.mp4"
    """
    if not path:
        return path

    # Handle UNC paths (\\192.168.1.6\Share3\...)
    if path.startswith("\\\\"):
        parts = path.split("\\")
        # parts[0] = '', parts[1] = '', parts[2] = '192.168.1.6', parts[3] = 'Share3', ...
        if len(parts) >= 4:
            share_name = parts[3]  # e.g., "Share3"
            remaining = "\\".join(parts[4:])  # Everything after share name

            if client_os.lower() == "mac":
                # Convert to macOS format: /Volumes/Share3/path/to/file
                return f"/Volumes/{share_name}/{remaining}".replace("\\", "/")
            else:
                # Convert to Windows drive letter format
                if share_name in SHARE_MAPPINGS:
                    drive = SHARE_MAPPINGS[share_name]  # e.g., "U:"
                    return f"{drive}\\{remaining}"
                else:
                    # Unknown share, return as-is
                    return path

    # Handle Docker mount paths (/mnt/share3/...)
    if path.startswith("/mnt/"):
        parts = path.split("/")
        if len(parts) >= 3:
            mount_name = parts[2]  # e.g., "share3"
            remaining = "/".join(parts[3:])

            # Find share name from DOCKER_MOUNTS
            share_name = None
            for share, mount in DOCKER_MOUNTS.items():
                if mount == f"/mnt/{mount_name}":
                    share_name = share
                    break

            if share_name:
                if client_os.lower() == "mac":
                    return f"/Volumes/{share_name}/{remaining}"
                else:
                    if share_name in SHARE_MAPPINGS:
                        drive = SHARE_MAPPINGS[share_name]
                        return f"{drive}\\{remaining}".replace("/", "\\")

    # Return as-is if format not recognized
    return path


def copy_file_to_temp(source_path: str, job_id: str, filename: str) -> str:
    """
    Copy a file to the temp directory for a job.

    Args:
        source_path: Source file path (already normalized)
        job_id: Job UUID
        filename: Destination filename

    Returns:
        Local temp file path

    Raises:
        Exception: If copy fails
    """
    settings = get_settings()
    dest_dir = Path(settings.temp_dir) / str(job_id)

    result = copy_file_sequential(source_path, str(dest_dir), filename)

    if not result:
        raise Exception(f"Failed to copy file to temp: {source_path}")

    return result


def copy_file_to_output(temp_path: str, filename: str, username: str = None) -> str:
    """
    Copy a file from temp to SMB output directory.
    Output path: {smb_output_path}/{username}/{filename}

    Example: \\\\192.168.1.6\\Share3\\Public\\video-compilation\\username\\channel_jobid.mp4

    Args:
        temp_path: Path to file in temp directory
        filename: Output filename
        username: Username for subdirectory (creates {smb_output_path}/{username}/)

    Returns:
        Final output file path (normalized with consistent slashes)

    Raises:
        Exception: If copy fails
    """
    settings = get_settings()

    # Use SMB output path (network share)
    output_dir = normalize_path_for_server(settings.smb_output_path)

    # Build path with consistent slashes (don't use Path() which uses OS-specific slashes)
    if username:
        # Use backslash for UNC paths, forward slash for Docker mount paths
        if output_dir.startswith('\\\\'):
            output_dir = f"{output_dir}\\{username}"
        else:
            output_dir = f"{output_dir}/{username}"

    # Create directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    result = copy_file_sequential(temp_path, output_dir, filename)

    if not result:
        raise Exception(f"Failed to copy file to output: {temp_path}")

    # Normalize the result path to use consistent backslashes for UNC paths
    if result.startswith('\\\\'):
        result = result.replace('/', '\\')

    return result


def cleanup_temp_dir(job_id: str):
    """
    Clean up temp directory for a job.
    Includes video files, logo files, and ASS subtitle files.

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
