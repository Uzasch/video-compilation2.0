# Ubuntu Host Setup (API Server Only)

This guide covers setting up the video compilation API server on Ubuntu.
The host only serves the API - it does NOT process videos. Workers run separately.

## Architecture

```
Ubuntu Host (this guide)
    - FastAPI backend (port 8000)
    - Redis (message broker)
    - Frontend (optional, port 3000)

Remote Workers (separate machines)
    - Celery workers
    - FFmpeg processing
    - GPU encoding
```

## Prerequisites

- Ubuntu 22.04 LTS or newer
- Python 3.11+
- Network access to Supabase
- Network access to SMB shares (for path verification only)

## Installation Steps

### 1. Install System Dependencies

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip redis-server ffmpeg git
```

### 2. Start Redis

```bash
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Verify
redis-cli ping
# Should return: PONG
```

### 3. Mount SMB Shares

The API needs access to SMB shares for path verification.

```bash
# Install CIFS utils
sudo apt install -y cifs-utils

# Create mount points
sudo mkdir -p /mnt/share /mnt/share2 /mnt/share3 /mnt/share4 /mnt/share5
sudo mkdir -p /mnt/new_share_1 /mnt/new_share_2 /mnt/new_share_3 /mnt/new_share_4

# Create credentials file (secure)
sudo nano /etc/samba/credentials
```

Add to `/etc/samba/credentials`:
```
username=your_username
password=your_password
```

Secure the file:
```bash
sudo chmod 600 /etc/samba/credentials
```

Add to `/etc/fstab`:
```
//192.168.1.6/Share   /mnt/share   cifs  credentials=/etc/samba/credentials,uid=1000,gid=1000,iocharset=utf8  0  0
//192.168.1.6/Share2  /mnt/share2  cifs  credentials=/etc/samba/credentials,uid=1000,gid=1000,iocharset=utf8  0  0
//192.168.1.6/Share3  /mnt/share3  cifs  credentials=/etc/samba/credentials,uid=1000,gid=1000,iocharset=utf8  0  0
//192.168.1.6/Share4  /mnt/share4  cifs  credentials=/etc/samba/credentials,uid=1000,gid=1000,iocharset=utf8  0  0
//192.168.1.6/Share5  /mnt/share5  cifs  credentials=/etc/samba/credentials,uid=1000,gid=1000,iocharset=utf8  0  0
//192.168.1.10/New_Share_1  /mnt/new_share_1  cifs  credentials=/etc/samba/credentials,uid=1000,gid=1000,iocharset=utf8  0  0
//192.168.1.10/New_Share_2  /mnt/new_share_2  cifs  credentials=/etc/samba/credentials,uid=1000,gid=1000,iocharset=utf8  0  0
//192.168.1.10/New_Share_3  /mnt/new_share_3  cifs  credentials=/etc/samba/credentials,uid=1000,gid=1000,iocharset=utf8  0  0
//192.168.1.10/New_Share_4  /mnt/new_share_4  cifs  credentials=/etc/samba/credentials,uid=1000,gid=1000,iocharset=utf8  0  0
```

Mount all:
```bash
sudo mount -a
```

### 4. Clone and Setup Project

```bash
cd /opt
sudo git clone <your-repo-url> video-compilation
sudo chown -R $USER:$USER video-compilation
cd video-compilation/backend

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 5. Create Environment File

```bash
nano /opt/video-compilation/backend/.env
```

Add:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
REDIS_URL=redis://localhost:6379/0
GOOGLE_APPLICATION_CREDENTIALS=/opt/video-compilation/backend/credentials/bigquery-key.json
CORS_ORIGINS=["http://localhost:3000","http://your-frontend-domain"]
```

### 6. Create Systemd Services

#### Backend API Service

```bash
sudo nano /etc/systemd/system/video-compilation-api.service
```

```ini
[Unit]
Description=Video Compilation API
After=network.target redis.service

[Service]
Type=simple
User=your-username
WorkingDirectory=/opt/video-compilation/backend
Environment=PATH=/opt/video-compilation/backend/venv/bin
ExecStart=/opt/video-compilation/backend/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 7. Start Services

```bash
sudo systemctl daemon-reload
sudo systemctl enable video-compilation-api
sudo systemctl start video-compilation-api

# Check status
sudo systemctl status video-compilation-api

# View logs
sudo journalctl -u video-compilation-api -f
```

## Code Changes Required

### 1. Remove Docker-specific Redis URL

File: `backend/api/config.py`

Change:
```python
redis_url: str = "redis://redis:6379/0"
```

To:
```python
redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
```

### 2. Remove Docker-specific Celery Broker

File: `backend/workers/celery_app.py`

Change:
```python
broker='redis://redis:6379/0'
```

To:
```python
import os
broker=os.getenv("REDIS_URL", "redis://localhost:6379/0")
```

### 3. Update SMB Keep-alive (Optional)

File: `backend/api/main.py`

The SMB keep-alive task can be removed or kept. Native Ubuntu CIFS mounts are more stable than Docker volumes, but keeping it doesn't hurt.

To remove, delete:
- `SMB_MOUNTS` list
- `KEEPALIVE_INTERVAL` constant
- `ping_mount()` function
- `smb_keepalive_task()` function
- Remove `keepalive_task` from lifespan

### 4. Remove Docker Network References

File: `backend/api/routes/jobs.py`

Change:
```python
celery_app = Celery('workers', broker='redis://redis:6379/0')
```

To:
```python
import os
celery_app = Celery('workers', broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
```

## Firewall Configuration

```bash
# Allow API port
sudo ufw allow 8000/tcp

# Allow Redis only from worker IPs (optional, for security)
sudo ufw allow from 192.168.1.0/24 to any port 6379
```

## Health Check

```bash
# Check API
curl http://localhost:8000/health

# Check Redis
redis-cli ping

# Check mounts
ls /mnt/share
```

## Troubleshooting

### API won't start

```bash
# Check logs
sudo journalctl -u video-compilation-api -n 50

# Test manually
cd /opt/video-compilation/backend
source venv/bin/activate
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### SMB mount issues

```bash
# Check mount status
mount | grep cifs

# Remount
sudo umount /mnt/share
sudo mount -a

# Check connectivity
ping 192.168.1.6
```

### Redis connection refused

```bash
# Check Redis status
sudo systemctl status redis-server

# Check Redis is listening
sudo netstat -tlnp | grep 6379
```

## Summary of Changes

| File | Change |
|------|--------|
| `backend/api/config.py` | Use env var for Redis URL |
| `backend/workers/celery_app.py` | Use env var for broker URL |
| `backend/api/routes/jobs.py` | Use env var for Celery broker |
| `backend/api/main.py` | Optional: remove SMB keep-alive |

Total: 3-4 files, ~10 lines of code changes.
