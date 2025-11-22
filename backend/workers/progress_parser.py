import re
import subprocess
from services.supabase import get_supabase_client

def parse_ffmpeg_progress(line: str) -> dict:
    """
    Parse FFmpeg stderr output for progress information.

    Returns dict with:
        - current_time: seconds processed
        - fps: current fps
        - speed: processing speed multiplier
    """
    result = {}

    # Parse time: time=00:01:23.45
    time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
    if time_match:
        h, m, s = time_match.groups()
        result['current_time'] = int(h)*3600 + int(m)*60 + float(s)

    # Parse fps: fps=30
    fps_match = re.search(r'fps=\s*(\d+)', line)
    if fps_match:
        result['fps'] = int(fps_match.group(1))

    # Parse speed: speed=1.5x
    speed_match = re.search(r'speed=\s*(\d+\.?\d*)x', line)
    if speed_match:
        result['speed'] = float(speed_match.group(1))

    return result

def run_ffmpeg_with_progress(cmd: list, job_id: str, total_duration: float, logger, log_dir: str):
    """
    Run FFmpeg command and parse progress, updating Supabase in real-time.

    Args:
        cmd: FFmpeg command as list
        job_id: Job UUID
        total_duration: Total expected output duration in seconds
        logger: Job logger instance
        log_dir: Directory where log files are stored (for stderr and command files)
    """
    from pathlib import Path
    supabase = get_supabase_client()

    # Write full FFmpeg command to file (in same directory as logs)
    cmd_file = Path(log_dir) / f"ffmpeg_cmd.txt"
    with open(cmd_file, 'w', encoding='utf-8') as f:
        f.write(' '.join(cmd))
    logger.info(f"FFmpeg command written to: {cmd_file}")

    logger.info(f"Starting FFmpeg process")
    logger.info(f"Expected output duration: {total_duration:.2f}s")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1
    )

    last_progress = 0
    stderr_lines = []  # Collect all stderr for full error reporting

    for line in process.stderr:
        stderr_lines.append(line)  # Store all stderr lines

        # Parse progress
        parsed = parse_ffmpeg_progress(line)

        if 'current_time' in parsed:
            current_time = parsed['current_time']
            progress = int((current_time / total_duration) * 100)
            progress = min(progress, 99)  # Never show 100% until done

            # Only update if progress changed by at least 1%
            if progress > last_progress:
                try:
                    supabase.table('jobs').update({
                        'progress': progress,
                        'status': 'processing'
                    }).eq('job_id', job_id).execute()

                    logger.info(f"Progress: {progress}% (time: {current_time:.2f}s)")
                    last_progress = progress
                except Exception as e:
                    logger.error(f"Failed to update progress: {e}")

    # Wait for process to complete
    returncode = process.wait()

    # Write full stderr to file (in same directory as logs)
    stderr_file = Path(log_dir) / f"ffmpeg_stderr.txt"
    with open(stderr_file, 'w', encoding='utf-8') as f:
        f.writelines(stderr_lines)

    if returncode == 0:
        logger.info("FFmpeg completed successfully")
        logger.info(f"Full stderr written to: {stderr_file}")
    else:
        logger.error(f"FFmpeg failed with code {returncode}")
        logger.error(f"Full stderr written to: {stderr_file}")
        logger.error(f"Error output (last 50 lines):\n{''.join(stderr_lines[-50:])}")

    return returncode
