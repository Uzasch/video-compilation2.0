# **Complete System Architecture Design**

## **Tech Stack (Recommended)**

### **Backend:**
- **FastAPI** (Python) - Modern, async, auto-docs, better than Flask
- **Celery** - Distributed task queue with Redis
- **Redis** - Queue broker + result backend
- **SQLAlchemy** - ORM for local database operations

### **Frontend:**
- **React + Vite** - Fast, modern
- **TanStack Query (React Query)** - Data fetching, caching
- **Socket.IO** - Real-time progress updates
- **Tailwind CSS** - Modern, fast styling
- **React Router** - Multi-page navigation

### **Databases:**
- **Supabase (PostgreSQL)** - Jobs, users, history, logs
- **BigQuery** - Video paths (from Sheets), analytics
- **Redis** - Queue, caching

### **Processing:**
- **FFmpeg** - Video encoding
- **Python subprocess** - FFmpeg execution with progress parsing

---

## **System Architecture Diagram**

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER BROWSERS                           │
│              (Multiple users on network via IP:PORT)            │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────────┐
│                    PC1 (Master Server)                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  React Frontend (Vite build served by FastAPI)          │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  FastAPI Server (REST API + WebSocket)                  │   │
│  │  - User authentication (simple login)                   │   │
│  │  - Job submission endpoints                             │   │
│  │  - Queue management (admin only)                        │   │
│  │  - History/logs endpoints                               │   │
│  │  - Real-time progress (Socket.IO)                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Celery Worker 1 (GPU - RTX)                            │   │
│  │  - Accepts: 4K jobs, high-priority                      │   │
│  │  - Concurrency: 1 (one job at a time)                   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────────┐
│                         Redis Server (PC1)                      │
│  ┌──────────────┬──────────────┬──────────────┬─────────────┐  │
│  │ default_queue│ gpu_queue    │ 4k_queue     │ Results     │  │
│  │ (PC2, PC3)   │ (PC1 only)   │ (PC1 only)   │ Cache       │  │
│  └──────────────┴──────────────┴──────────────┴─────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        ↓                   ↓
┌───────────────────┐  ┌───────────────────┐
│  PC2 (Worker)     │  │  PC3 (Worker)     │
│  Celery Worker 2  │  │  Celery Worker 3  │
│  (GTX 1060)       │  │  (GTX 750)        │
│  - default_queue  │  │  - default_queue  │
│  - Concurrency: 1 │  │  - Concurrency: 1 │
└───────────────────┘  └───────────────────┘
        │                   │
        └─────────┬─────────┘
                  ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Supabase (Cloud PostgreSQL)                  │
│  Tables:                                                         │
│  - users (id, username, role, created_at)                       │
│  - jobs (job_id, user_id, status, progress, channel, ...)      │
│  - job_videos (job_id, video_id, video_path, position, ...)    │
│  - job_features (job_id, text_animation, 4k_mode, ...)         │
│  - compilation_history (user filter, date filter)              │
│                                                                  │
│  Real-time: WebSocket subscriptions for job updates            │
└─────────────────────────────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────────┐
│                      BigQuery                                   │
│  - Video paths table (from Google Sheets)                       │
│  - Compilation results (analytics, long-term storage)           │
└─────────────────────────────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────────┐
│                   SMB Network Storage                           │
│  \\192.168.1.6\Share3\...                                       │
│  - Source videos                                                │
│  - Output compilations                                          │
│  - Packaging videos                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## **Database Schema**

### **Supabase Tables:**

```sql
-- Users table
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  username TEXT UNIQUE NOT NULL,
  display_name TEXT,
  role TEXT DEFAULT 'user' CHECK (role IN ('user', 'admin')),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Jobs table (main compilation jobs)
CREATE TABLE jobs (
  job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id),
  channel_name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'cancelled')),
  progress INTEGER DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),

  -- Job configuration
  has_intro BOOLEAN DEFAULT false,
  has_end_packaging BOOLEAN DEFAULT false,
  has_logo BOOLEAN DEFAULT false,

  -- Features
  enable_4k BOOLEAN DEFAULT false,
  text_animation_enabled BOOLEAN DEFAULT false,
  text_animation_words TEXT[], -- Array of words for animation

  -- Results
  output_path TEXT,
  final_duration FLOAT,
  error_message TEXT,

  -- Worker info
  worker_id TEXT,
  queue_name TEXT,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,

  -- Metadata
  metadata JSONB -- For extensibility
);

-- Job videos (many-to-many: job has many videos)
CREATE TABLE job_videos (
  id BIGSERIAL PRIMARY KEY,
  job_id UUID REFERENCES jobs(job_id) ON DELETE CASCADE,

  -- Video identification
  video_id TEXT, -- From BigQuery (if using video_id)
  video_path TEXT, -- Direct path (if premium/custom)

  -- Position in compilation
  position INTEGER NOT NULL,

  -- Video metadata
  duration FLOAT,
  resolution TEXT, -- e.g., "1920x1080", "3840x2160"
  is_4k BOOLEAN,

  -- Processing
  filters TEXT, -- FFmpeg filters for this video

  created_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(job_id, position)
);

-- Packaging inserts (videos between main videos)
CREATE TABLE job_packaging_inserts (
  id BIGSERIAL PRIMARY KEY,
  job_id UUID REFERENCES jobs(job_id) ON DELETE CASCADE,

  -- Insert position (after which video position)
  insert_after_position INTEGER NOT NULL,

  -- Packaging video
  packaging_video_id TEXT,
  packaging_video_path TEXT,
  packaging_name TEXT, -- e.g., "Transition A", "Call to Action"

  duration FLOAT,

  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Compilation history (for quick lookups)
CREATE TABLE compilation_history (
  id BIGSERIAL PRIMARY KEY,
  job_id UUID REFERENCES jobs(job_id),
  user_id UUID REFERENCES users(id),
  channel_name TEXT,

  video_count INTEGER,
  total_duration FLOAT,
  output_filename TEXT,

  created_at TIMESTAMPTZ DEFAULT NOW(),

  -- Indexes for filtering
  INDEX idx_user_channel (user_id, channel_name),
  INDEX idx_created_at (created_at DESC)
);

-- Enable real-time for job updates
ALTER PUBLICATION supabase_realtime ADD TABLE jobs;
```

### **BigQuery Tables:**

```sql
-- Video paths (external table linked to Google Sheets)
-- Already exists: ybh-deployment-testing.ybh_assest_path.path

-- Compilation results (analytics)
CREATE TABLE `ybh-deployment-testing.ybh_assest_path.compilation_results` (
  job_id STRING,
  user_username STRING,
  channel_name STRING,
  timestamp TIMESTAMP,
  video_count INT64,
  total_duration FLOAT64,
  output_path STRING,
  worker_id STRING,
  features_used ARRAY<STRING>, -- ["4k", "text_animation", "packaging_inserts"]
  processing_time_seconds FLOAT64,
  status STRING
);
```

---

## **API Endpoints**

### **Authentication:**
```
POST   /api/auth/login          # Simple login (username only)
POST   /api/auth/logout
GET    /api/auth/me             # Current user
```

### **Job Submission:**
```
POST   /api/jobs/submit         # Submit new compilation job
POST   /api/jobs/validate       # Validate videos before submitting
GET    /api/jobs/:job_id        # Get job details
GET    /api/jobs/:job_id/logs   # Get job logs
```

### **Queue Management (Admin only):**
```
GET    /api/queue/status        # All queues status
POST   /api/queue/reorder       # Reorder jobs
DELETE /api/queue/:job_id       # Cancel/remove job
POST   /api/queue/reset         # Clear all queues (emergency)
```

### **History:**
```
GET    /api/history             # User's past compilations (filters: date, channel)
GET    /api/history/:job_id     # Specific compilation details
```

### **Resources:**
```
GET    /api/channels            # List of channels (from BigQuery)
GET    /api/videos/search       # Search videos by ID (BigQuery)
GET    /api/packaging/list      # List available packaging videos
```

### **Admin:**
```
GET    /api/admin/workers       # Worker status
GET    /api/admin/stats         # System statistics
GET    /api/admin/logs          # System logs
```

### **WebSocket:**
```
WS     /ws/jobs/:job_id         # Real-time job progress updates
```

---

## **Worker Queue Strategy**

### **Multiple Queues Based on Requirements:**

```python
# Celery routing
CELERY_ROUTES = {
    'tasks.process_4k_compilation': {'queue': '4k_queue'},      # PC1 only (RTX GPU)
    'tasks.process_gpu_compilation': {'queue': 'gpu_queue'},    # PC1 only (RTX GPU)
    'tasks.process_standard_compilation': {'queue': 'default_queue'},  # PC2, PC3
}

# Worker configuration
# PC1 (RTX):
celery -A tasks worker -Q 4k_queue,gpu_queue,default_queue --concurrency=1

# PC2 (GTX 1060):
celery -A tasks worker -Q default_queue --concurrency=1

# PC3 (GTX 750):
celery -A tasks worker -Q default_queue --concurrency=1
```

### **Job Routing Logic:**

```python
def determine_queue(job):
    """Determine which queue to use based on job requirements"""

    # Check if 4K processing required
    if job.enable_4k:
        return '4k_queue'  # Only PC1 can handle

    # Check if text animation (complex filters)
    if job.text_animation_enabled:
        return 'gpu_queue'  # Prefer PC1 GPU

    # Check video count
    if len(job.videos) > 50:
        return 'gpu_queue'  # Heavy job, use best PC

    # Standard job - any worker
    return 'default_queue'
```

---

## **New Features Implementation**

### **1. Text Animation (Word-by-word):**

```python
# tasks.py
def build_text_animation_filters(words, timing_config):
    """
    Build FFmpeg drawtext filters for word-by-word animation
    Based on your add_word_animation.py example
    """
    filters = []

    for i, word in enumerate(words):
        cumulative_text = " ".join(words[:i+1])
        start_time = timing_config['word_delay'] * i

        # Alpha expression for fade in/out
        alpha_expr = f"if(lt(mod(t,{cycle_duration}),{start_time}),0,...)"

        input_label = "0:v" if i == 0 else f"v{i}"
        output_label = f"v{i+1}"

        drawtext = (
            f"[{input_label}]drawtext="
            f"fontfile={font_file}:"
            f"text='{cumulative_text}':"
            f"fontsize=50:"
            f"fontcolor=yellow:"
            f"alpha='{alpha_expr}'[{output_label}]"
        )

        filters.append(drawtext)

    return ";".join(filters)
```

### **2. True 4K Processing:**

```python
def check_all_videos_4k(video_paths):
    """Check if all videos are 4K resolution"""
    for path in video_paths:
        resolution = get_video_resolution(path)
        if resolution[0] < 3840 or resolution[1] < 2160:
            return False
    return True

def build_4k_compilation_command(videos, enable_4k_stretch):
    """
    Build FFmpeg command for 4K compilation
    - If all videos are 4K: maintain quality
    - If enable_4k_stretch: upscale all to 4K
    """
    filters = []

    for i, video in enumerate(videos):
        if enable_4k_stretch:
            # Force upscale to 4K
            filters.append(f"[{i}:v]scale=3840:2160:flags=lanczos[v{i}]")
        else:
            # Maintain aspect ratio, pad if needed
            filters.append(f"[{i}:v]scale=3840:2160:force_original_aspect_ratio=decrease,pad=3840:2160:(ow-iw)/2:(oh-ih)/2[v{i}]")

    # Concat
    concat_inputs = ''.join([f"[v{i}]" for i in range(len(videos))])
    filters.append(f"{concat_inputs}concat=n={len(videos)}:v=1:a=1[outv][outa]")

    return filters
```

### **3. Packaging Inserts Between Videos:**

```python
# Frontend: User can add packaging at specific positions
{
  "videos": [
    {"video_id": "abc123", "position": 1},
    {"video_id": "def456", "position": 2},
    {"video_id": "ghi789", "position": 3}
  ],
  "packaging_inserts": [
    {
      "insert_after_position": 1,  # After first video
      "packaging_path": "\\\\SERVER\\Packaging\\transition_a.mp4"
    },
    {
      "insert_after_position": 3,  # After third video
      "packaging_video_id": "PKG001"  # Or by ID
    }
  ]
}

# Backend: Build compilation with inserts
def build_compilation_with_packaging(videos, packaging_inserts):
    """Insert packaging videos at specified positions"""
    compiled_sequence = []

    for i, video in enumerate(videos):
        compiled_sequence.append(video)

        # Check if there's a packaging insert after this position
        for insert in packaging_inserts:
            if insert['insert_after_position'] == video['position']:
                compiled_sequence.append(insert)

    return compiled_sequence
```

### **4. FFmpeg Progress Parsing:**

```python
def run_ffmpeg_with_progress(cmd, job_id, total_duration):
    """
    Run FFmpeg and parse progress, update Supabase in real-time
    """
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    for line in process.stderr:
        if 'time=' in line:
            # Parse: time=00:01:23.45
            time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
            if time_match:
                h, m, s = time_match.groups()
                current_seconds = int(h)*3600 + int(m)*60 + float(s)
                progress = int((current_seconds / total_duration) * 100)

                # Update Supabase
                supabase.table('jobs').update({
                    'progress': min(progress, 99),
                    'status': 'processing'
                }).eq('job_id', job_id).execute()

    return process.wait()
```

### **5. Move to Production (Filename Sanitization):**

```python
import re
import unicodedata

def sanitize_filename(filename, channel_name, timestamp):
    """
    Sanitize filename for production:
    - Replace spaces with underscores
    - Remove special characters
    - Only English characters
    - Add channel and timestamp
    """
    # Remove accents and non-ASCII
    filename = unicodedata.normalize('NFKD', filename)
    filename = filename.encode('ASCII', 'ignore').decode('ASCII')

    # Replace spaces and special chars with underscore
    filename = re.sub(r'[^\w\s-]', '', filename)
    filename = re.sub(r'[-\s]+', '_', filename)

    # Build final name
    final_name = f"{channel_name}_{timestamp}_{filename}.mp4"

    return final_name.lower()
```

### **6. Structured Logging:**

```python
# logs/{date}/{username}/{channel_name}_{job_id}.log

import logging
from pathlib import Path

def setup_job_logger(job_id, username, channel_name):
    """Create structured logger for each job"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    log_dir = Path(f"logs/{date_str}/{username}")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"{channel_name}_{job_id}.log"

    logger = logging.getLogger(f"job_{job_id}")
    logger.setLevel(logging.INFO)  # Not verbose

    handler = logging.FileHandler(log_file)
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger

# Usage in worker:
job_logger = setup_job_logger(job.job_id, job.user.username, job.channel_name)
job_logger.info(f"Starting compilation with {len(videos)} videos")
job_logger.info(f"Copying files from SMB...")
job_logger.info(f"Running FFmpeg...")
job_logger.info(f"Completed in {duration}s")
```

---

## **UI Pages/Components**

### **Pages:**

1. **Login Page** (`/login`)
   - Simple username input
   - No password (as per requirement)

2. **Dashboard** (`/`)
   - Quick submit form
   - Active jobs list with real-time progress
   - Quick stats

3. **New Compilation** (`/new`)
   - Channel selection
   - Video IDs or paths input
   - Features toggles:
     - Enable 4K
     - Text animation (word input)
     - Add packaging inserts
     - Add intro/end/logo
   - Preview final duration
   - Validate button
   - Submit button

4. **History** (`/history`)
   - Past compilations table
   - Filters: Date range, Channel
   - Clickable rows → Details page

5. **Compilation Details** (`/compilation/:job_id`)
   - Job info
   - Video list used
   - Output path
   - Download log
   - Re-run option

6. **Admin Panel** (`/admin`) - Admin only
   - Queue management
     - Reorder jobs (drag & drop)
     - Cancel jobs
     - Reset queue
   - Worker status
   - System stats

---

## **Project Structure**

```
ybh-compilation-tool-2/
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Login.jsx
│   │   │   ├── Dashboard.jsx
│   │   │   ├── NewCompilation.jsx
│   │   │   ├── History.jsx
│   │   │   ├── CompilationDetails.jsx
│   │   │   └── Admin.jsx
│   │   ├── components/
│   │   │   ├── JobCard.jsx
│   │   │   ├── ProgressBar.jsx
│   │   │   ├── VideoList.jsx
│   │   │   ├── PackagingInsertForm.jsx
│   │   │   └── QueueManager.jsx
│   │   ├── hooks/
│   │   │   ├── useRealtimeJob.js      # Supabase real-time
│   │   │   ├── useJobProgress.js      # WebSocket progress
│   │   │   └── useAuth.js
│   │   ├── services/
│   │   │   ├── api.js                 # Axios instance
│   │   │   └── supabase.js
│   │   └── App.jsx
│   ├── package.json
│   └── vite.config.js
│
├── backend/
│   ├── api/
│   │   ├── main.py                    # FastAPI app
│   │   ├── routes/
│   │   │   ├── auth.py
│   │   │   ├── jobs.py
│   │   │   ├── queue.py
│   │   │   ├── history.py
│   │   │   └── admin.py
│   │   ├── models.py                  # Pydantic models
│   │   └── websocket.py               # Socket.IO handlers
│   │
│   ├── workers/
│   │   ├── celery_app.py              # Celery config
│   │   ├── tasks.py                   # Main tasks
│   │   ├── ffmpeg_builder.py          # FFmpeg command builder
│   │   ├── text_animation.py          # Text animation filters
│   │   └── progress_parser.py         # FFmpeg progress parsing
│   │
│   ├── services/
│   │   ├── supabase.py                # Supabase client
│   │   ├── bigquery.py                # BigQuery client
│   │   ├── storage.py                 # SMB operations
│   │   └── logger.py                  # Structured logging
│   │
│   ├── utils/
│   │   ├── path_converter.py
│   │   ├── filename_sanitizer.py
│   │   └── video_utils.py
│   │
│   └── requirements.txt
│
├── logs/                              # Structured logs (gitignored)
├── temp/                              # Temp processing files
├── .env                               # Environment variables
└── docker-compose.yml                 # Redis (optional)
```

---

## **Requirements Summary**

### **Core Features:**
- ✅ Server handles restarts (persistent queue via Redis/Celery)
- ✅ User tracking (who created each video)
- ✅ Progress bars from FFmpeg parsing
- ✅ Text animation on videos (word-by-word)
- ✅ True 4K mode (check all videos, stretch if needed)
- ✅ Packaging inserts between videos
- ✅ Past compilation history (user + channel filters)
- ✅ Move to production (filename sanitization)
- ✅ Final duration preview
- ✅ Simple structured logging (logs/{date}/{user}/{channel}_{job_id}.log)
- ✅ Admin queue management

### **Queue & Distribution:**
- ✅ Persistent queue (Redis + Celery)
- ✅ Auto-pick with conditions (queue routing by job requirements)
- ✅ Scalable (A, B, C process simultaneously)
- ✅ PC differences handled (GPU vs CPU queues)

### **User Access:**
- ✅ Multiple users
- ✅ Simple login (no authentication/password)
- ✅ Admin-only queue management

### **Deployment:**
- ✅ Local PCs (192.168.1.x)
- ✅ Browser access via IP:PORT
- ✅ PC1 runs API + Frontend + Worker
- ✅ PC2, PC3 run workers only

---

## **Next Steps**

1. **Set up the project structure** - Create folders, install dependencies
2. **Configure Supabase** - Create tables, enable real-time
3. **Set up Redis** - For Celery queue
4. **Build FastAPI backend** - API endpoints, WebSocket
5. **Build Celery workers** - Task processing, FFmpeg
6. **Build React frontend** - UI components, pages
7. **Test on one PC** - Get it working locally
8. **Deploy to all 3 PCs** - Distribute workers
