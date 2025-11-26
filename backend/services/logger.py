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


def setup_job_logger(job_id: str, username: str, channel_name: str):
    """
    Create structured logger for each job.
    Log path: logs/{date}/{username}/jobs/{channel_name}_{job_id}/job.log

    Each job gets its own folder containing:
    - job.log: Main job log
    - ffmpeg_cmd.txt: FFmpeg command (written by progress_parser)
    - ffmpeg_stderr.txt: FFmpeg stderr output (written by progress_parser)

    Used for:
    - Celery worker job processing
    - FFmpeg progress tracking
    - Job-specific error logging

    Returns:
        tuple: (logger instance, log file path)
    """
    settings = get_settings()
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')

    # Create job-specific folder
    job_folder = f"{channel_name}_{job_id}"
    log_dir = Path(settings.log_dir) / date_str / username / "jobs" / job_folder
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "job.log"

    # Create logger
    logger = logging.getLogger(f"job_{job_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # Don't propagate to root logger
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
