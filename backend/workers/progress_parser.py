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

def run_ffmpeg_with_progress(cmd: list, job_id: str, total_duration: float, logger, log_dir: str, worker_name: str = None):
    """
    Run FFmpeg command and parse progress, updating Supabase in real-time.
    Periodically checks for new jobs in queue and starts prefetching.

    Args:
        cmd: FFmpeg command as list
        job_id: Job UUID
        total_duration: Total expected output duration in seconds
        logger: Job logger instance
        log_dir: Directory where log files are stored (for stderr and command files)
        worker_name: Celery worker hostname (for prefetch checks)
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
    last_prefetch_check = 0  # Track when we last checked for prefetch
    last_cancel_check = 0  # Track when we last checked for cancellation
    stderr_lines = []  # Collect all stderr for full error reporting
    cancelled = False  # Flag to track if job was cancelled

    # Import prefetch function
    prefetch_func = None
    if worker_name:
        try:
            from workers.tasks import check_and_prefetch_next_job
            prefetch_func = check_and_prefetch_next_job
        except ImportError:
            logger.warning("Could not import prefetch function")

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

                # Check for cancellation every 5% progress
                if progress >= last_cancel_check + 5:
                    try:
                        job_status = supabase.table('jobs').select('status').eq('job_id', job_id).single().execute()
                        if job_status.data and job_status.data.get('status') == 'cancelled':
                            logger.warning(f"Job cancelled by user at {progress}% - terminating FFmpeg")
                            process.terminate()
                            process.wait(timeout=5)  # Wait up to 5 seconds for graceful termination
                            cancelled = True
                            break
                        last_cancel_check = progress
                    except Exception as e:
                        logger.warning(f"  Cancel check failed: {e}")

                # Check for new jobs to prefetch every 20% progress (separate from DB update)
                if prefetch_func and progress >= last_prefetch_check + 20:
                    try:
                        logger.info(f"  [Prefetch check at {progress}%]")
                        prefetch_func(worker_name, logger, current_job_id=job_id)
                        last_prefetch_check = progress
                    except Exception as e:
                        logger.warning(f"  Prefetch check failed: {e}")

    # If cancelled, clean up and raise exception
    if cancelled:
        # Try to kill if still running
        if process.poll() is None:
            process.kill()
        raise Exception("Job cancelled by user")

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
