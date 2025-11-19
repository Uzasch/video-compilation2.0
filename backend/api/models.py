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
