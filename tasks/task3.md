# Task 3: FastAPI Backend - Core Structure & Authentication

## Objective
Build the FastAPI application structure with authentication, configuration, and basic routes.

---

## 1. Configuration & Settings

**File: `backend/api/config.py`**

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # Supabase
    supabase_url: str
    supabase_key: str  # service_role key

    # BigQuery
    google_application_credentials: str
    bigquery_project_id: str = "ybh-deployment-testing"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # SMB Paths
    smb_base_path: str = r"\\192.168.1.6\Share3"
    smb_output_path: str = r"\\192.168.1.6\Share3\Public\video-compilation"

    # FFmpeg
    ffmpeg_path: str = "ffmpeg"

    # Logging
    log_level: str = "INFO"
    log_dir: str = "logs"

    # Temp
    temp_dir: str = "temp"

    # CORS
    cors_origins: list = ["http://localhost:3000", "http://192.168.1.104:3000"]

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings():
    return Settings()
```

---

## 2. Database Models (Pydantic)

**File: `backend/api/models.py`**

```python
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

# ============================================================================
# USER MODELS
# ============================================================================

class User(BaseModel):
    id: UUID
    username: str
    display_name: Optional[str] = None
    role: str = "user"
    created_at: datetime

class UserCreate(BaseModel):
    username: str
    display_name: Optional[str] = None

class LoginRequest(BaseModel):
    username: str

class LoginResponse(BaseModel):
    user: User
    message: str = "Login successful"

# ============================================================================
# JOB MODELS
# ============================================================================

class JobVideo(BaseModel):
    video_id: Optional[str] = None
    video_path: Optional[str] = None
    position: int
    filters: Optional[str] = None

class PackagingInsert(BaseModel):
    insert_after_position: int
    packaging_video_id: Optional[str] = None
    packaging_video_path: Optional[str] = None
    packaging_name: Optional[str] = None

class JobCreate(BaseModel):
    channel_name: str
    videos: List[JobVideo]
    packaging_inserts: Optional[List[PackagingInsert]] = []

    # Configuration
    has_intro: bool = False
    has_end_packaging: bool = False
    has_logo: bool = False

    # Features
    enable_4k: bool = False
    text_animation_enabled: bool = False
    text_animation_words: Optional[List[str]] = []

class JobStatus(BaseModel):
    job_id: UUID
    user_id: UUID
    channel_name: str
    status: str
    progress: int

    has_intro: bool
    has_end_packaging: bool
    has_logo: bool
    enable_4k: bool
    text_animation_enabled: bool
    text_animation_words: Optional[List[str]]

    output_path: Optional[str]
    final_duration: Optional[float]
    error_message: Optional[str]

    worker_id: Optional[str]
    queue_name: Optional[str]

    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

class JobSubmitResponse(BaseModel):
    job_id: UUID
    status: str
    message: str

# ============================================================================
# VALIDATION MODELS
# ============================================================================

class VideoValidation(BaseModel):
    video_id: Optional[str]
    video_path: Optional[str]
    exists: bool
    duration: Optional[float] = None
    resolution: Optional[str] = None
    is_4k: bool = False
    error: Optional[str] = None

class ValidationRequest(BaseModel):
    videos: List[JobVideo]
    channel_name: str
    check_logo: bool = False
    check_intro: bool = False
    check_end_packaging: bool = False

class ValidationResponse(BaseModel):
    videos: List[VideoValidation]
    logo: Optional[dict] = None
    intro: Optional[dict] = None
    end_packaging: Optional[dict] = None
    all_valid: bool

# ============================================================================
# HISTORY MODELS
# ============================================================================

class CompilationHistory(BaseModel):
    id: int
    job_id: UUID
    channel_name: str
    video_count: int
    total_duration: float
    output_filename: str
    created_at: datetime

# ============================================================================
# QUEUE MODELS
# ============================================================================

class QueueStatus(BaseModel):
    queue_name: str
    pending_count: int
    active_count: int

class AllQueuesStatus(BaseModel):
    queues: List[QueueStatus]
    total_pending: int
    total_active: int
```

---

## 3. Main FastAPI Application

**File: `backend/api/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from pathlib import Path

from api.config import get_settings
from api.routes import auth, jobs, queue, history, admin

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
```

---

## 4. Authentication Routes

**File: `backend/api/routes/auth.py`**

```python
from fastapi import APIRouter, HTTPException, Depends
from api.models import LoginRequest, LoginResponse, User
from services.supabase import get_supabase_client

router = APIRouter()

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Simple login - just check if username exists.
    No password required as per requirements.
    """
    supabase = get_supabase_client()

    try:
        # Check if user exists
        result = supabase.table("users").select("*").eq("username", request.username).execute()

        if result.data and len(result.data) > 0:
            user_data = result.data[0]
            user = User(**user_data)
            return LoginResponse(user=user, message="Login successful")
        else:
            raise HTTPException(status_code=404, detail="User not found")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@router.post("/logout")
async def logout():
    """Logout endpoint (placeholder for future session management)"""
    return {"message": "Logout successful"}

@router.get("/me", response_model=User)
async def get_current_user(user_id: str):
    """
    Get current user details.
    In production, this would use a session token.
    For now, user_id is passed as query parameter.
    """
    supabase = get_supabase_client()

    try:
        result = supabase.table("users").select("*").eq("id", user_id).execute()

        if result.data and len(result.data) > 0:
            return User(**result.data[0])
        else:
            raise HTTPException(status_code=404, detail="User not found")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")
```

---

## 5. Supabase Service

**File: `backend/services/supabase.py`**

```python
from supabase import create_client, Client
from api.config import get_settings
from functools import lru_cache

@lru_cache()
def get_supabase_client() -> Client:
    """Get Supabase client (cached)"""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_key)
```

---

## 6. Empty Route Files (Placeholders)

**File: `backend/api/routes/jobs.py`**
```python
from fastapi import APIRouter

router = APIRouter()

# Job submission, validation, status routes will be implemented in Task 4
```

**File: `backend/api/routes/queue.py`**
```python
from fastapi import APIRouter

router = APIRouter()

# Queue management routes will be implemented in Task 5
```

**File: `backend/api/routes/history.py`**
```python
from fastapi import APIRouter

router = APIRouter()

# History routes will be implemented in Task 6
```

**File: `backend/api/routes/admin.py`**
```python
from fastapi import APIRouter

router = APIRouter()

# Admin routes will be implemented in Task 6
```

---

## 7. Run & Test

### Start the FastAPI server:

```bash
cd backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### Test endpoints:

1. **Health check:**
   ```
   http://localhost:8000/health
   ```

2. **API docs (Swagger):**
   ```
   http://localhost:8000/docs
   ```

3. **Test login:**
   ```bash
   curl -X POST http://localhost:8000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "admin"}'
   ```

---

## Checklist

- [ ] `config.py` created with all settings
- [ ] `models.py` created with all Pydantic models
- [ ] `main.py` created with FastAPI app
- [ ] Authentication routes implemented
- [ ] Supabase service created
- [ ] Empty route files created
- [ ] Backend starts without errors
- [ ] Health check endpoint works
- [ ] API docs accessible at `/docs`
- [ ] Login endpoint works with test user

---

## Next: Task 4
Implement job submission, validation, and status endpoints.
