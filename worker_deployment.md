# Worker PC Setup Guide - Complete Steps

This guide documents the complete process to set up a Celery worker on a secondary PC (PC2) to process video compilation jobs.

---

## Network Configuration

| Machine | IP Address | Role |
|---------|------------|------|
| PC1 (Main) | 192.168.1.83 | Redis server, API, primary worker |
| PC2 (Worker) | 192.168.1.242 | Secondary worker (this setup) |
| NAS (FIL-YBH-002) | 192.168.1.6 | SMB shares (Share, Share2-5) |
| NAS (FIL-YBH-003) | 192.168.1.10 | SMB shares (New_Share_1-4) |

---

## Prerequisites

- Windows 10/11 PC
- Docker Desktop installed
- Network access to PC1 (Redis) and NAS devices
- Admin privileges for WSL installation

---

## Step 1: Clone the Repository

```bash
cd C:\Users\uzair\Vscode\new_video_compilation
git clone https://github.com/Uzasch/video-compilation2.0.git
cd video-compilation2.0
```

---

## Step 2: Create Environment File

Create `backend/.env` with the following configuration:

```env
# ===========================================
# REDIS (Celery Broker) - REQUIRED
# ===========================================
# PC1 (192.168.1.83) is running Redis
REDIS_URL=redis://192.168.1.83:6379/0

# ===========================================
# SUPABASE - REQUIRED
# ===========================================
SUPABASE_URL=https://dvrmlwnxvzjjpalozxjr.supabase.co
SUPABASE_KEY=sb_secret_fq_ZKiWYpo0IUED4tq4LPA_a5jr-0rB

# ===========================================
# BIGQUERY - REQUIRED
# ===========================================
BIGQUERY_PROJECT_ID=ybh-deployment-testing
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/gcloud_secret.json

# ===========================================
# SMB PATHS - REQUIRED
# ===========================================
SMB_BASE_PATH=\\\\192.168.1.6\\Share3
SMB_OUTPUT_PATH=\\\\192.168.1.6\\Share3\\Public\\video-compilation

# ===========================================
# LOCAL PATHS
# ===========================================
TEMP_DIR=temp
LOG_DIR=logs

# ===========================================
# SERVER CONFIG
# ===========================================
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
FFMPEG_PATH=ffmpeg
LOG_LEVEL=INFO

# ===========================================
# CORS (PC1 and PC2 IPs for frontend access)
# ===========================================
CORS_ORIGINS=http://localhost:3000,http://192.168.1.83:3000,http://192.168.1.242:3000
```

---

## Step 3: Copy BigQuery Credentials

**IMPORTANT:** The credentials file is NOT in the git repo. Copy it manually from PC1.

```bash
# Create credentials folder
mkdir backend\credentials

# Copy gcloud_secret.json from PC1 to:
# backend/credentials/gcloud_secret.json
```

Options to copy:
- USB drive
- Network share from PC1
- SCP if SSH is available

---

## Step 4: Install/Update WSL

WSL2 is required for Docker networking and NVIDIA GPU support.

### Check WSL Status
```powershell
wsl --status
```

### Install or Update WSL
```powershell
# Run as Administrator
wsl --update
```

### Install Ubuntu Distribution
```powershell
wsl --install -d Ubuntu
```

### Verify Installation
```powershell
wsl --list --verbose
```

Expected output:
```
NAME                   STATE           VERSION
* docker-desktop       Running         2
  Ubuntu               Running         2
```

---

## Step 5: Install NVIDIA Container Toolkit

This enables GPU acceleration inside Docker containers.

### Run these commands in WSL Ubuntu:

```bash
# 1. Install prerequisites
wsl -d Ubuntu -e bash -c "sudo apt-get update && sudo apt-get install -y curl gnupg2"

# 2. Add NVIDIA GPG key
wsl -d Ubuntu -e bash -c "curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg"

# 3. Add NVIDIA repository
wsl -d Ubuntu -e bash -c "curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list"

# 4. Install NVIDIA Container Toolkit
wsl -d Ubuntu -e bash -c "sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit"

# 5. Configure Docker runtime
wsl -d Ubuntu -e bash -c "sudo nvidia-ctk runtime configure --runtime=docker"
```

### Restart Docker Desktop
After installing NVIDIA Container Toolkit, restart Docker Desktop:
- Right-click Docker Desktop icon in system tray
- Select "Restart"

---

## Step 6: Configure docker-compose.worker.yml

The `docker-compose.worker.yml` file in the project root contains:
- Worker configuration with GPU support
- SMB volume mounts with credentials
- Redis connection to PC1

### Key Configuration Points:

```yaml
services:
  celery-worker:
    command: celery -A workers.celery_app worker -Q 4k_queue,default_queue --concurrency=1 --loglevel=info -n pc2@%h
    environment:
      - REDIS_URL=redis://192.168.1.83:6379/0  # PC1's Redis
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    volumes:
      - smb_share:/mnt/share
      - smb_share2:/mnt/share2
      - smb_share3:/mnt/share3
      - smb_share4:/mnt/share4
      - smb_share5:/mnt/share5
      - smb_new_share_1:/mnt/new_share_1
      - smb_new_share_2:/mnt/new_share_2
      - smb_new_share_3:/mnt/new_share_3
      - smb_new_share_4:/mnt/new_share_4

volumes:
  smb_share3:
    driver: local
    driver_opts:
      type: cifs
      o: "username=uzair,password=Uzasch@2222,vers=3.0,file_mode=0777,dir_mode=0777"
      device: "//192.168.1.6/Share3"
  # ... other SMB volumes
```

### Update REDIS_URL if needed:
Edit `docker-compose.worker.yml` line 38:
```yaml
- REDIS_URL=redis://192.168.1.83:6379/0  # Point to PC1's Redis
```

---

## Step 7: Create Required Directories

```bash
cd C:\Users\uzair\Vscode\new_video_compilation\video-compilation2.0
mkdir logs
mkdir temp
mkdir uploads
```

---

## Step 8: Build and Start the Worker

```bash
cd C:\Users\uzair\Vscode\new_video_compilation\video-compilation2.0

# Build the Docker image
docker-compose -f docker-compose.worker.yml build

# Start the worker
docker-compose -f docker-compose.worker.yml up -d

# Check logs
docker-compose -f docker-compose.worker.yml logs -f
```

---

## Step 9: Verify Worker Status

### Check Worker Logs
```bash
docker-compose -f docker-compose.worker.yml logs --tail=50
```

### Expected Output:
```
 -------------- pc2@docker-desktop v5.5.3 (immunity)
--- ***** -----
-- ******* ---- Linux-6.6.87.2-microsoft-standard-WSL2-x86_64-with-glibc2.41
- *** --- * ---
- ** ---------- [config]
- ** ---------- .> app:         video_compilation:0x...
- ** ---------- .> transport:   redis://192.168.1.83:6379/0
- ** ---------- .> results:     redis://192.168.1.83:6379/0
- *** --- * --- .> concurrency: 1 (prefork)
-- ******* ---- .> task events: OFF
--- ***** -----
 -------------- [queues]
                .> 4k_queue         exchange=4k_queue(direct) key=4k_queue
                .> default_queue    exchange=default_queue(direct) key=default_queue

[tasks]
  . workers.tasks.process_4k_compilation
  . workers.tasks.process_gpu_compilation
  . workers.tasks.process_standard_compilation

[INFO/MainProcess] Connected to redis://192.168.1.83:6379/0
[INFO/MainProcess] mingle: searching for neighbors
[INFO/MainProcess] mingle: sync with 1 nodes
[INFO/MainProcess] mingle: sync complete
[INFO/MainProcess] ============================================================
[INFO/MainProcess] CELERY WORKER CONFIGURATION
[INFO/MainProcess] ============================================================
[INFO/MainProcess]   task_acks_late: True
[INFO/MainProcess]   task_reject_on_worker_lost: True
[INFO/MainProcess]   worker_prefetch_multiplier: 2
[INFO/MainProcess]   task_track_started: True
[INFO/MainProcess] ============================================================
[INFO/MainProcess] pc2@docker-desktop ready.
```

### Verify SMB Mounts
```bash
docker exec video-compilation-celery-worker ls -la /mnt/
```

Expected output:
```
drwxrwxrwx 2 root root 32768 new_share_1
drwxrwxrwx 2 root root     0 new_share_2
drwxrwxrwx 2 root root     0 new_share_3
drwxrwxrwx 2 root root     0 new_share_4
drwxrwxrwx 2 root root 16384 share
drwxrwxrwx 2 root root 49152 share2
drwxrwxrwx 2 root root  8192 share3
drwxrwxrwx 2 root root 16384 share4
drwxrwxrwx 2 root root 16384 share5
```

---

## Troubleshooting

### Redis Connection Refused
- Check PC1's firewall allows port 6379
- Verify Redis is bound to 0.0.0.0 on PC1
- Test connection: `telnet 192.168.1.83 6379`

### SMB Mounts Not Working
- Verify network access: `ping 192.168.1.6`
- Check credentials in docker-compose.worker.yml
- Ensure SMB share names are correct

### GPU Not Detected
- Verify NVIDIA Container Toolkit is installed
- Restart Docker Desktop after installation
- Test GPU: `docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi`

### Worker Not Picking Up Jobs
- Verify queue names match: `4k_queue`, `default_queue`
- Check REDIS_URL is correct
- Look for errors in worker logs

---

## Quick Reference Commands

```bash
# Start worker
docker-compose -f docker-compose.worker.yml up -d

# Stop worker
docker-compose -f docker-compose.worker.yml down

# View logs
docker-compose -f docker-compose.worker.yml logs -f

# Rebuild after code changes
docker-compose -f docker-compose.worker.yml build
docker-compose -f docker-compose.worker.yml up -d

# Check container status
docker ps

# Execute command in container
docker exec video-compilation-celery-worker <command>
```

---

## Summary Checklist

- [x] Clone repository
- [x] Create backend/.env file
- [x] Copy gcloud_secret.json credentials
- [x] Install/Update WSL
- [x] Install Ubuntu WSL distribution
- [x] Install NVIDIA Container Toolkit
- [x] Restart Docker Desktop
- [x] Create logs, temp, uploads directories
- [x] Update REDIS_URL to PC1's IP (192.168.1.83)
- [x] Build and start worker
- [x] Verify Redis connection
- [x] Verify SMB mounts
- [x] Worker ready to accept jobs

---

## File Locations

| File | Path | Notes |
|------|------|-------|
| Environment config | `backend/.env` | Redis, Supabase, BigQuery settings |
| BigQuery credentials | `backend/credentials/gcloud_secret.json` | Copy from PC1 |
| Worker compose | `docker-compose.worker.yml` | In project root |
| Logs | `logs/` | Worker log files |
| Temp files | `temp/` | Temporary processing files |

---

*Last updated: November 26, 2025*
es