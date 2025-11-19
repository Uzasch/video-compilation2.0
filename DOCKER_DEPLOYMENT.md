# Docker Deployment Guide - Multi-PC Setup

## Overview

This system uses Docker to deploy across 3 PCs on your local network:

- **PC2 (192.168.1.83)**: Master node - runs everything (GTX 1060)
- **PC1 & PC3**: Worker nodes - run Celery workers only

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ PC2 (192.168.1.83) - Master (GTX 1060)                     │
│ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│ │   Redis     │  │   Backend   │  │  Frontend   │          │
│ │   :6379     │  │   :8000     │  │   :3000     │          │
│ └─────────────┘  └─────────────┘  └─────────────┘          │
│ ┌─────────────┐                                             │
│ │  Worker #1  │                                             │
│ └─────────────┘                                             │
└─────────────────────────────────────────────────────────────┘
                           │
                    Redis Queue (6379)
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼──────┐  ┌────────▼──────┐  ┌────────▼──────┐
│ PC1 Worker   │  │ PC3 Worker    │  │ PC2 Worker    │
│ (RTX GPU)    │  │ (GTX 750)     │  │ (GTX 1060)    │
└──────────────┘  └───────────────┘  └───────────────┘
```

---

## Prerequisites

### All PCs

1. **Docker Desktop** installed (for Windows)
   - Download: https://www.docker.com/products/docker-desktop
   - Enable WSL 2 backend

2. **Network access** to:
   - PC1: 192.168.1.104 (ports 6379, 8000, 3000)
   - SMB share: \\192.168.1.6\Share3

3. **Git** installed to clone the repository

4. **BigQuery credentials** file (same on all PCs)
   - Place in: `backend/credentials/bigquery-key.json`

---

## Step-by-Step Setup

### 1. PC1 Setup (Master)

#### Clone Repository
```bash
cd C:\Users\uzair\VSCode\video_compilation
git clone <repository-url> ybh-compilation-tool-2
cd ybh-compilation-tool-2
```

#### Create Environment File
```bash
# Create backend/.env
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=your-service-role-key
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/bigquery-key.json
BIGQUERY_PROJECT_ID=ybh-deployment-testing
REDIS_URL=redis://redis:6379/0
SMB_BASE_PATH=\\192.168.1.6\Share3
SMB_OUTPUT_PATH=\\192.168.1.6\Share3\Public\video-compilation
FFMPEG_PATH=ffmpeg
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Create frontend/video-compilation2.0/.env
VITE_API_URL=http://192.168.1.104:8000
VITE_SUPABASE_URL=https://xxxxx.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
```

#### Add BigQuery Credentials
```bash
mkdir -p backend/credentials
# Copy bigquery-key.json to backend/credentials/
```

#### Configure Windows Firewall
```powershell
# Run PowerShell as Administrator
netsh advfirewall firewall add rule name="Redis-6379" dir=in action=allow protocol=TCP localport=6379
netsh advfirewall firewall add rule name="FastAPI-8000" dir=in action=allow protocol=TCP localport=8000
netsh advfirewall firewall add rule name="Vite-3000" dir=in action=allow protocol=TCP localport=3000
```

#### Start All Services
```bash
docker-compose up -d
```

#### Verify Services
```bash
# Check all containers are running
docker-compose ps

# Should show:
# video-compilation-redis      running
# video-compilation-backend    running
# video-compilation-frontend   running
# video-compilation-celery     running

# Test Redis
docker exec -it video-compilation-redis redis-cli ping
# Should return: PONG

# Check backend logs
docker-compose logs -f backend

# Access frontend
# Open browser: http://192.168.1.104:3000
```

---

### 2. PC2 & PC3 Setup (Workers)

#### Clone Repository
```bash
cd C:\path\to\projects
git clone <repository-url> ybh-compilation-tool-2
cd ybh-compilation-tool-2
```

#### Create Environment File
```bash
# Create backend/.env
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=your-service-role-key
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/bigquery-key.json
BIGQUERY_PROJECT_ID=ybh-deployment-testing
REDIS_URL=redis://192.168.1.104:6379/0  # ← Point to PC1
SMB_BASE_PATH=\\192.168.1.6\Share3
SMB_OUTPUT_PATH=\\192.168.1.6\Share3\Public\video-compilation
FFMPEG_PATH=ffmpeg
```

#### Add BigQuery Credentials
```bash
mkdir -p backend/credentials
# Copy bigquery-key.json to backend/credentials/
```

#### Test Network Connection to PC1
```bash
# Test Redis connectivity
telnet 192.168.1.104 6379
# Should connect (press Ctrl+C to exit)

# Ping PC1
ping 192.168.1.104
```

#### Start Worker
```bash
docker-compose -f docker-compose.worker.yml up -d
```

#### Verify Worker
```bash
# Check worker is running
docker-compose -f docker-compose.worker.yml ps

# Check worker logs
docker-compose -f docker-compose.worker.yml logs -f

# You should see:
# "celery@worker ready"
# "Connected to redis://192.168.1.104:6379/0"
```

---

### 3. Verify Multi-PC Setup

#### On PC1 - Check All Workers

```bash
# Access Redis CLI
docker exec -it video-compilation-redis redis-cli

# List all Celery workers
keys celery*

# Check active workers
docker exec -it video-compilation-backend celery -A workers.celery_app inspect active
# Should show 3 workers

# Check registered queues
docker exec -it video-compilation-backend celery -A workers.celery_app inspect active_queues
```

Expected output:
```json
{
  "worker@PC1": [...],
  "worker@PC2": [...],
  "worker@PC3": [...]
}
```

#### Test Job Distribution

1. Open frontend: http://192.168.1.104:3000
2. Submit a compilation job
3. Watch logs on all PCs:

```bash
# PC1
docker-compose logs -f celery-worker

# PC2
docker-compose -f docker-compose.worker.yml logs -f

# PC3
docker-compose -f docker-compose.worker.yml logs -f
```

You should see one of the workers pick up the job.

---

## Common Commands

### PC1 (Master)

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# View logs (all services)
docker-compose logs -f

# View logs (specific service)
docker-compose logs -f backend
docker-compose logs -f celery-worker
docker-compose logs -f redis
docker-compose logs -f frontend

# Restart service
docker-compose restart backend

# Rebuild and restart (after code changes)
docker-compose up -d --build

# Remove all containers and volumes
docker-compose down -v
```

### PC2 & PC3 (Workers)

```bash
# Start worker
docker-compose -f docker-compose.worker.yml up -d

# Stop worker
docker-compose -f docker-compose.worker.yml down

# View logs
docker-compose -f docker-compose.worker.yml logs -f

# Restart worker
docker-compose -f docker-compose.worker.yml restart

# Rebuild worker (after code changes)
docker-compose -f docker-compose.worker.yml up -d --build
```

---

## Troubleshooting

### Worker Can't Connect to Redis

**Symptom**: Worker logs show "Connection refused" to Redis

**Solution**:
1. Check PC1 firewall allows port 6379
2. Verify Redis is running on PC1: `docker ps`
3. Test connection from worker PC:
   ```bash
   telnet 192.168.1.104 6379
   ```
4. Check `.env` has correct PC1 IP:
   ```env
   REDIS_URL=redis://192.168.1.104:6379/0
   ```

### Worker Can't Access SMB Share

**Symptom**: Worker logs show "Permission denied" or "Path not found"

**Solution**:
1. Map network drive on Windows:
   ```bash
   net use Z: \\192.168.1.6\Share3 /persistent:yes
   ```
2. Verify access from command prompt:
   ```bash
   dir \\192.168.1.6\Share3
   ```
3. Check SMB credentials in Windows Credential Manager

### Frontend Can't Connect to Backend

**Symptom**: Frontend shows "Network Error" or API calls fail

**Solution**:
1. Check backend is running on PC1:
   ```bash
   curl http://192.168.1.104:8000/health
   ```
2. Verify frontend `.env` has correct backend URL:
   ```env
   VITE_API_URL=http://192.168.1.104:8000
   ```
3. Check PC1 firewall allows port 8000

### Container Won't Start

**Symptom**: Docker container exits immediately

**Solution**:
1. Check logs:
   ```bash
   docker-compose logs backend
   ```
2. Common issues:
   - Missing `.env` file
   - Missing `bigquery-key.json`
   - Port already in use
   - Syntax error in `.env`

---

## Code Updates & Deployment

### Updating Code on All PCs

#### Option 1: Git Pull (Recommended)
```bash
# On all PCs
cd ybh-compilation-tool-2
git pull
docker-compose up -d --build  # PC1
docker-compose -f docker-compose.worker.yml up -d --build  # PC2/PC3
```

#### Option 2: Manual Sync
```bash
# Copy changes from PC1 to PC2/PC3
robocopy C:\Users\uzair\VSCode\video_compilation\ybh-compilation-tool-2\backend \\PC2\share\ybh-compilation-tool-2\backend /MIR
robocopy C:\Users\uzair\VSCode\video_compilation\ybh-compilation-tool-2\backend \\PC3\share\ybh-compilation-tool-2\backend /MIR

# Then rebuild on PC2/PC3
docker-compose -f docker-compose.worker.yml up -d --build
```

---

## Monitoring

### Real-time Monitoring

```bash
# PC1 - Monitor all services
docker stats

# PC1 - Monitor Redis queue size
docker exec -it video-compilation-redis redis-cli
> llen celery
> keys celery-task-meta-*

# PC1 - Flower (Celery monitoring) - Add to docker-compose.yml
# Access: http://192.168.1.104:5555
```

### Log Aggregation

Logs are stored in:
- `./logs/` on each PC
- Docker logs: `docker-compose logs`

---

## Production Considerations

### For Production Deployment:

1. **Use specific image tags** instead of rebuilding from source
2. **Set up log rotation** for Docker logs
3. **Configure resource limits** in docker-compose.yml:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '2'
         memory: 4G
   ```
4. **Enable GPU support** for hardware acceleration (already commented in worker config)
5. **Set up health checks** for all services
6. **Use Docker Swarm** or **Kubernetes** for better orchestration
7. **Implement auto-restart policies** (already configured: `restart: unless-stopped`)

---

## Summary

✅ **PC1** runs: Redis + Backend + Frontend + Worker
✅ **PC2/PC3** run: Worker only
✅ All workers connect to PC1's Redis queue
✅ All workers access same SMB share for videos
✅ Queue distributes jobs across 3 workers automatically
✅ Real-time updates via Supabase for all users

Your distributed video compilation system is now running!
