from celery import Celery
from celery.signals import worker_ready
from api.config import get_settings
import logging

settings = get_settings()

# Setup logging
logger = logging.getLogger(__name__)

# Initialize Celery
app = Celery(
    'video_compilation',
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=['workers.tasks']  # Auto-discover tasks
)

@worker_ready.connect
def log_worker_config(sender=None, **kwargs):
    """Log worker configuration when worker starts"""
    logger.info("=" * 60)
    logger.info("CELERY WORKER CONFIGURATION")
    logger.info("=" * 60)
    logger.info(f"  task_acks_late: {app.conf.task_acks_late}")
    logger.info(f"  task_reject_on_worker_lost: {app.conf.task_reject_on_worker_lost}")
    logger.info(f"  worker_prefetch_multiplier: {app.conf.worker_prefetch_multiplier}")
    logger.info(f"  task_track_started: {app.conf.task_track_started}")
    logger.info("=" * 60)

# Celery configuration
app.conf.update(
    # Task settings
    task_track_started=True,
    task_time_limit=10800,  # 3 hours max per task
    task_soft_time_limit=10200,  # 2h 50m soft limit
    worker_prefetch_multiplier=2,  # Prefetch next job for immediate file copying optimization

    # Acknowledgment settings (enables prefetch to work with concurrency=1)
    task_acks_late=True,  # Don't acknowledge task until completion (keeps next task in reserved state)
    task_reject_on_worker_lost=True,  # Retry task if worker crashes before completion

    # Result settings
    result_expires=86400,  # Keep results for 24 hours

    # Routing
    # Queue routing:
    # - gpu_queue: Text animation jobs (GPU-intensive subtitle rendering)
    # - 4k_queue: Large jobs (>40 videos)
    # - default_queue: Standard jobs
    task_routes={
        'workers.tasks.process_gpu_compilation': {'queue': 'gpu_queue'},
        'workers.tasks.process_4k_compilation': {'queue': '4k_queue'},
        'workers.tasks.process_standard_compilation': {'queue': 'default_queue'},
    },

    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)
