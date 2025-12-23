import subprocess
import json
import logging
import time
from pathlib import Path
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

        # Wake up SMB mount by checking if path exists (handles stale connections)
        path_exists = False
        try:
            path_check_start = time.time()
            path_exists = Path(video_path).exists()
            path_check_elapsed = time.time() - path_check_start

            if path_check_elapsed > 2.0:
                logger.warning(f"Slow path check ({path_check_elapsed:.2f}s) for: {video_path} | Network may be slow")

            if not path_exists:
                logger.warning(f"Path does not exist: {video_path}")
                return None
        except OSError as e:
            logger.error(f"Network/IO error checking path {video_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Path check failed for {video_path}: {e}")
            return None

        logger.debug(f"Running ffprobe for: {video_path}")
        start_time = time.time()

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180  # 3 minutes for slow SMB connections
        )

        elapsed = time.time() - start_time
        logger.info(f"ffprobe completed in {elapsed:.2f}s for: {video_path}")

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
        elapsed = time.time() - start_time
        # Extract mount point for network debugging
        mount_point = "/".join(video_path.replace("\\", "/").split("/")[:4]) if "/" in video_path.replace("\\", "/") else video_path
        logger.error(f"ffprobe timeout after {elapsed:.1f}s for {video_path} | Mount: {mount_point} | Network share may be unresponsive")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for {video_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting video info for {video_path}: {e}", exc_info=True)
        return None

def get_videos_info_batch(video_paths: List[str], max_workers: int = 8) -> Dict[str, Optional[Dict]]:
    """
    Get video info for multiple videos in parallel (batch operation).

    Args:
        video_paths: List of video file paths
        max_workers: Maximum parallel ffprobe processes (default: 8, optimal for SMB shares)

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
        - Sequential: 98 videos × 1s = 98 seconds
        - Parallel (8 workers): 98 videos ÷ 8 = ~12 seconds (31s total with overhead)
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
