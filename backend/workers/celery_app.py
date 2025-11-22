from celery import Celery
from api.config import get_settings

settings = get_settings()

# Initialize Celery
app = Celery(
    'video_compilation',
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=['workers.tasks']  # Auto-discover tasks
)

# Celery configuration
app.conf.update(
    # Task settings
    task_track_started=True,
    task_time_limit=10800,  # 3 hours max per task
    task_soft_time_limit=10200,  # 2h 50m soft limit
    worker_prefetch_multiplier=2,  # Prefetch next job for immediate file copying optimization

    # Result settings
    result_expires=86400,  # Keep results for 24 hours

    # Routing
    # All PCs have GPU, so only 2 queues:
    # - 4k_queue: >40 videos AND 4K enabled
    # - default_queue: Everything else
    task_routes={
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
