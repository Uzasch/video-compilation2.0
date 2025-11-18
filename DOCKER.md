# Docker Setup Guide

This project uses Docker to containerize the entire application stack for consistent development and deployment.

## Prerequisites

- Docker Desktop installed and running
- `.env` files configured (see `.env.example` files)

## Services

The `docker-compose.yml` defines the following services:

- **redis** - Redis server for Celery task queue (port 6379)
- **backend** - FastAPI application (port 8000)
- **celery-worker** - Celery worker for video processing tasks
- **frontend** - Vite development server (port 3000)

## Quick Start

### 1. Configure Environment Variables

Copy the example files and update with your credentials:

```bash
# Backend
cp backend/.env.example backend/.env
# Edit backend/.env with your Supabase, BigQuery credentials

# Frontend
cp frontend/video-compilation2.0/.env.example frontend/video-compilation2.0/.env
# Edit with your API URLs
```

### 2. Start All Services

```bash
# Start all containers in detached mode
docker compose up -d

# View logs
docker compose logs -f

# View logs for specific service
docker compose logs -f backend
```

### 3. Access the Application

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Redis:** localhost:6379

## Common Commands

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# Rebuild and start (after code changes to Dockerfile)
docker compose up -d --build

# View running containers
docker compose ps

# View logs
docker compose logs -f

# Execute command in container
docker compose exec backend bash
docker compose exec frontend sh

# Restart a service
docker compose restart backend

# Stop and remove all containers, networks, volumes
docker compose down -v
```

## Development Workflow

### Code Changes

- **Frontend/Backend code changes** are auto-reloaded (volumes mounted)
- **Dockerfile changes** require rebuild: `docker compose up -d --build`
- **Dependency changes** require rebuild

### Installing New Dependencies

**Backend:**
```bash
# Add to backend/requirements.txt
docker compose exec backend pip install <package>
# Or rebuild: docker compose up -d --build backend
```

**Frontend:**
```bash
# Add to frontend/video-compilation2.0/package.json
docker compose exec frontend npm install <package>
# Or rebuild: docker compose up -d --build frontend
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker compose logs backend

# Restart service
docker compose restart backend

# Rebuild and restart
docker compose up -d --build backend
```

### Port already in use

```bash
# Stop existing containers
docker compose down

# Or change ports in docker-compose.yml
```

### Reset everything

```bash
# Stop and remove all containers, networks, and volumes
docker compose down -v

# Rebuild from scratch
docker compose up -d --build
```

## Production Deployment

For production, use the production frontend build:

```bash
# Build production frontend
docker compose -f docker-compose.prod.yml up -d --build
```

## Notes

- Redis data persists in Docker volume `redis_data`
- Logs and temp files are mounted to host directories
- Hot reload enabled for development
- Environment variables loaded from `.env` files
