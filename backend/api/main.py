from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from pathlib import Path

from api.config import get_settings
from api.routes import auth, jobs, queue, history, admin, uploads

settings = get_settings()

# Initialize FastAPI
app = FastAPI(
    title="YBH Video Compilation API",
    description="API for distributed video compilation system",
    version="2.0.0"
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
