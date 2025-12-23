from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os
import asyncio
import logging
from pathlib import Path

from api.config import get_settings
from api.routes import auth, jobs, queue, history, admin, uploads

settings = get_settings()
logger = logging.getLogger(__name__)

# SMB mount keep-alive task
SMB_MOUNTS = [
    "/mnt/share",
    "/mnt/share2",
    "/mnt/share3",
    "/mnt/share4",
    "/mnt/share5",
    "/mnt/new_share_1",
    "/mnt/new_share_2",
    "/mnt/new_share_3",
    "/mnt/new_share_4",
]
KEEPALIVE_INTERVAL = 5  # seconds - aggressive to prevent stale
STALE_JOB_CHECK_INTERVAL = 60  # seconds - check for stuck jobs every minute
STALE_JOB_THRESHOLD = 300  # seconds - job is stale if queued for >5 minutes with no worker

def ping_mount(mount: str):
    """Ping a single mount to keep it alive."""
    try:
        list(Path(mount).iterdir())
    except Exception:
        pass

async def smb_keepalive_task():
    """Background task to keep SMB mounts alive by periodic access."""
    from concurrent.futures import ThreadPoolExecutor
    logger.info(f"Starting SMB keep-alive task (interval: {KEEPALIVE_INTERVAL}s)")

    with ThreadPoolExecutor(max_workers=len(SMB_MOUNTS)) as executor:
        while True:
            try:
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                # Ping all mounts in parallel
                loop = asyncio.get_event_loop()
                await asyncio.gather(*[
                    loop.run_in_executor(executor, ping_mount, mount)
                    for mount in SMB_MOUNTS
                ])
            except asyncio.CancelledError:
                logger.info("SMB keep-alive task stopped")
                break
            except Exception as e:
                logger.error(f"SMB keep-alive error: {e}")

async def stale_job_detector_task():
    """Background task to detect and re-dispatch stale jobs."""
    from api.config import get_settings
    from services.supabase import get_supabase_client
    from datetime import datetime, timezone, timedelta
    from celery import Celery

    logger.info(f"Starting stale job detector (interval: {STALE_JOB_CHECK_INTERVAL}s, threshold: {STALE_JOB_THRESHOLD}s)")
    celery_app = Celery('workers', broker=settings.redis_url, backend=settings.redis_url)

    while True:
        try:
            await asyncio.sleep(STALE_JOB_CHECK_INTERVAL)

            supabase = get_supabase_client()
            threshold_time = datetime.now(timezone.utc) - timedelta(seconds=STALE_JOB_THRESHOLD)

            # Find jobs that are queued but have no worker and were created >5 min ago
            result = supabase.table('jobs').select('job_id, task_id, created_at, enable_4k').eq('status', 'queued').is_('worker_id', 'null').lt('created_at', threshold_time.isoformat()).execute()

            stale_jobs = result.data if result.data else []

            for job in stale_jobs:
                job_id = job['job_id']
                task_id = job.get('task_id')

                # Check if task failed or is missing from Redis
                if task_id:
                    try:
                        from celery.result import AsyncResult
                        task_result = AsyncResult(task_id, app=celery_app)
                        task_state = task_result.state
                        # FAILURE = task failed, PENDING = task missing from Redis (never delivered or lost)
                        if task_state in ('FAILURE', 'PENDING'):
                            logger.warning(f"Stale job {job_id} has {task_state} task, re-dispatching...")

                            # Re-dispatch based on job type with delivery confirmation
                            from workers.tasks import process_standard_compilation, process_4k_compilation
                            from api.routes.jobs import submit_task_with_confirmation

                            if job.get('enable_4k'):
                                new_task = submit_task_with_confirmation(process_4k_compilation, job_id)
                            else:
                                new_task = submit_task_with_confirmation(process_standard_compilation, job_id)

                            # Update task_id
                            supabase.table('jobs').update({'task_id': new_task.id}).eq('job_id', job_id).execute()
                            logger.info(f"Re-dispatched stale job {job_id} with new task {new_task.id}")
                    except Exception as e:
                        logger.error(f"Error checking/re-dispatching stale job {job_id}: {e}")

        except asyncio.CancelledError:
            logger.info("Stale job detector stopped")
            break
        except Exception as e:
            logger.error(f"Stale job detector error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: launch background tasks
    keepalive_task = asyncio.create_task(smb_keepalive_task())
    stale_detector_task = asyncio.create_task(stale_job_detector_task())
    logger.info("Application started with SMB keep-alive and stale job detector")
    yield
    # Shutdown: cancel background tasks
    keepalive_task.cancel()
    stale_detector_task.cancel()
    try:
        await keepalive_task
        await stale_detector_task
    except asyncio.CancelledError:
        pass
    logger.info("Application shutdown complete")

# Initialize FastAPI
app = FastAPI(
    title="YBH Video Compilation API",
    description="API for distributed video compilation system",
    version="2.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["Jobs"])
app.include_router(queue.router, prefix="/api/queue", tags=["Queue"])
app.include_router(history.router, prefix="/api/history", tags=["History"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(uploads.router, prefix="/api", tags=["Uploads"])

# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "YBH Video Compilation API",
        "version": "2.0.0"
    }

# Serve frontend (production)
public_path = Path(__file__).parent.parent / "public"
if public_path.exists():
    app.mount("/assets", StaticFiles(directory=public_path / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Serve index.html for all non-API routes
        if not full_path.startswith("api/") and not full_path.startswith("ws/"):
            index_path = public_path / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
        return {"error": "Not found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True
    )
