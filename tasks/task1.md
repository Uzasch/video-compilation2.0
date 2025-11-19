# Task 1: Project Setup & Dependencies

## Objective
Set up the complete project structure with all necessary dependencies for both frontend and backend.

---

## Frontend Setup

### 1. Additional Dependencies to Install

```bash
cd frontend

# UI & Styling
npm install tailwindcss postcss autoprefixer
npx tailwindcss init -p

# Data Fetching & State
npm install @tanstack/react-query axios

# Real-time Communication
npm install socket.io-client

# UI Components (optional but helpful)
npm install react-hot-toast  # For notifications
npm install lucide-react     # Icons

# Supabase Client
npm install @supabase/supabase-js
```

### 2. Configure Tailwind CSS

**File: `frontend/tailwind.config.js`**
```js
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

**File: `frontend/src/index.css`**
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

### 3. Vite Configuration for API Proxy

**File: `frontend/vite.config.js`**
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',  // Allow network access
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',  // FastAPI backend
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      }
    }
  },
  build: {
    outDir: '../backend/public',  // Build directly to backend
  }
})
```

---

## Backend Setup

### 1. Create Backend Directory Structure

```bash
cd ..
mkdir -p backend/api/routes
mkdir -p backend/workers
mkdir -p backend/services
mkdir -p backend/utils
mkdir -p logs
mkdir -p temp
```

### 2. Python Dependencies

**File: `backend/requirements.txt`**
```txt
# Web Framework
fastapi==0.109.0
uvicorn[standard]==0.27.0
python-socketio==5.11.0
python-multipart==0.0.6

# Task Queue
celery==5.3.6
redis==5.0.1

# Databases
supabase==2.3.0
google-cloud-bigquery==3.17.0
google-auth==2.27.0

# Utilities
python-dotenv==1.0.0
pydantic==2.6.0
pydantic-settings==2.1.0

# FFmpeg & Video
Pillow==10.2.0

# Logging
colorlog==6.8.0
```

### 3. Install Python Dependencies

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Environment Configuration

### 1. Create `.env` file

**File: `backend/.env`**
```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key

# BigQuery
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\uzair\secrets\gcloud_secret.json
BIGQUERY_PROJECT_ID=ybh-deployment-testing

# Redis
REDIS_URL=redis://localhost:6379/0

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# SMB Paths
SMB_BASE_PATH=\\\\192.168.1.6\\Share3
SMB_OUTPUT_PATH=\\\\192.168.1.6\\Share3\\Public\\video-compilation

# FFmpeg
FFMPEG_PATH=ffmpeg  # or full path if not in PATH

# Logging
LOG_LEVEL=INFO
```

**File: `frontend/.env`**
```env
VITE_API_URL=http://192.168.1.104:8000
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
```

---

## Redis Setup (Windows)

### Option 1: Docker (Recommended)
```bash
docker run -d -p 6379:6379 --name redis redis:alpine
```

### Option 2: WSL
```bash
wsl
sudo apt update
sudo apt install redis-server
redis-server
```

### Option 3: Windows Binary
Download from: https://github.com/microsoftarchive/redis/releases
Run: `redis-server.exe`

---

## Verify Setup

### 1. Test Redis Connection
```bash
redis-cli ping
# Should return: PONG
```

### 2. Test Frontend
```bash
cd frontend
npm run dev
# Should open at http://localhost:3000
```

### 3. Test Backend (after Task 2)
```bash
cd backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
# Should open at http://localhost:8000/docs
```

---

## Docker Deployment (Multi-PC Setup)

### Architecture Overview

```
PC1 (192.168.1.104) - Master
├── Redis (queue)
├── Backend (FastAPI)
├── Frontend (Vite)
└── Celery Worker #1

PC2 (192.168.1.X) - Worker
└── Celery Worker #2

PC3 (192.168.1.Y) - Worker
└── Celery Worker #3
```

### PC1 (Master) - Full Stack

**File: `docker-compose.yml`** (already exists)

Run all services:
```bash
docker-compose up -d
```

This starts:
- Redis (port 6379)
- Backend API (port 8000)
- Frontend (port 3000)
- Celery Worker #1

### PC2 & PC3 (Workers) - Worker Only

**File: `docker-compose.worker.yml`**

```yaml
services:
  # Celery Worker - Connects to PC1's Redis
  celery-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: video-compilation-celery-worker
    command: celery -A workers.celery_app worker --loglevel=info --hostname=worker@%h
    volumes:
      - ./backend:/app
      - /app/venv
      - ./logs:/app/logs
      - ./temp:/app/temp
      # Mount SMB share for video access
      - type: bind
        source: \\192.168.1.6\Share3
        target: /mnt/share3
    env_file:
      - ./backend/.env
    environment:
      - REDIS_URL=redis://192.168.1.104:6379/0  # Point to PC1's Redis
      - PYTHONUNBUFFERED=1
      - WORKER_NAME=${HOSTNAME}
    restart: unless-stopped
    network_mode: host
```

Run on PC2/PC3:
```bash
docker-compose -f docker-compose.worker.yml up -d
```

### Environment Variables

**PC1 `.env`:**
```env
# Supabase
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=your-service-role-key

# BigQuery
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/bigquery-key.json
BIGQUERY_PROJECT_ID=ybh-deployment-testing

# Redis (local)
REDIS_URL=redis://redis:6379/0

# SMB Paths
SMB_BASE_PATH=\\192.168.1.6\Share3
SMB_OUTPUT_PATH=\\192.168.1.6\Share3\Public\video-compilation

# FFmpeg
FFMPEG_PATH=ffmpeg

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```

**PC2/PC3 `.env`:**
```env
# Supabase (same as PC1)
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=your-service-role-key

# BigQuery (same as PC1)
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/bigquery-key.json
BIGQUERY_PROJECT_ID=ybh-deployment-testing

# Redis (point to PC1)
REDIS_URL=redis://192.168.1.104:6379/0

# SMB Paths (same as PC1)
SMB_BASE_PATH=\\192.168.1.6\Share3
SMB_OUTPUT_PATH=\\192.168.1.6\Share3\Public\video-compilation

# FFmpeg
FFMPEG_PATH=ffmpeg
```

### Network Configuration

**Firewall Rules (PC1):**
```bash
# Allow Redis port
netsh advfirewall firewall add rule name="Redis" dir=in action=allow protocol=TCP localport=6379

# Allow Backend API
netsh advfirewall firewall add rule name="FastAPI" dir=in action=allow protocol=TCP localport=8000

# Allow Frontend
netsh advfirewall firewall add rule name="Vite" dir=in action=allow protocol=TCP localport=3000
```

### Commands

**Start all services (PC1):**
```bash
docker-compose up -d
```

**Start worker only (PC2/PC3):**
```bash
docker-compose -f docker-compose.worker.yml up -d
```

**View logs:**
```bash
# PC1 - All services
docker-compose logs -f

# PC1 - Specific service
docker-compose logs -f backend
docker-compose logs -f celery-worker

# PC2/PC3 - Worker logs
docker-compose -f docker-compose.worker.yml logs -f
```

**Stop services:**
```bash
# PC1
docker-compose down

# PC2/PC3
docker-compose -f docker-compose.worker.yml down
```

**Rebuild after code changes:**
```bash
# PC1
docker-compose up -d --build

# PC2/PC3
docker-compose -f docker-compose.worker.yml up -d --build
```

### Verify Setup

**Check all workers are connected:**
```bash
# On PC1, access Redis CLI
docker exec -it video-compilation-redis redis-cli

# In Redis CLI
keys celery*
# Should see worker registrations from all 3 PCs
```

**Check Celery workers:**
```bash
# On PC1
docker exec -it video-compilation-backend celery -A workers.celery_app inspect active_queues
# Should show 3 workers
```

---

## Checklist

- [ ] Frontend dependencies installed
- [ ] Tailwind CSS configured
- [ ] Vite proxy configured
- [ ] Backend directory structure created
- [ ] Python virtual environment created (for local dev)
- [ ] Python dependencies installed
- [ ] `.env` files created and configured (PC1, PC2, PC3)
- [ ] Docker and Docker Compose installed (all PCs)
- [ ] `docker-compose.worker.yml` created
- [ ] Redis running on PC1 (port 6379 accessible)
- [ ] Backend API running on PC1 (port 8000 accessible)
- [ ] Frontend running on PC1 (port 3000 accessible)
- [ ] Celery workers running on all 3 PCs
- [ ] Firewall rules configured on PC1
- [ ] Network connectivity verified between PCs
- [ ] All workers can access SMB share (\\192.168.1.6\Share3)
- [ ] Verified 3 workers registered in Celery

---

## Next: Task 2
Configure Supabase database and create all necessary tables.
