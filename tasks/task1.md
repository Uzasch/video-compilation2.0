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

## Checklist

- [ ] Frontend dependencies installed
- [ ] Tailwind CSS configured
- [ ] Vite proxy configured
- [ ] Backend directory structure created
- [ ] Python virtual environment created
- [ ] Python dependencies installed
- [ ] `.env` files created and configured
- [ ] Redis installed and running
- [ ] Frontend dev server runs successfully
- [ ] Redis connection verified

---

## Next: Task 2
Configure Supabase database and create all necessary tables.
