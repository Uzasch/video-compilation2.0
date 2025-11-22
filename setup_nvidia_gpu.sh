#!/bin/bash
# NVIDIA Container Toolkit Installation Script
# Run this in WSL 2 Ubuntu terminal: bash setup_nvidia_gpu.sh

set -e  # Exit on error

echo "========================================"
echo "NVIDIA Container Toolkit Installation"
echo "========================================"
echo ""

# Check if running in WSL
if ! grep -q Microsoft /proc/version; then
    echo "WARNING: This script is designed for WSL 2 on Windows"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Step 1/7: Installing prerequisites..."
sudo apt-get update && sudo apt-get install -y curl gnupg2
echo "✓ Prerequisites installed"
echo ""

echo "Step 2/7: Configuring NVIDIA repository..."
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
    sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
echo "✓ Repository configured"
echo ""

echo "Step 3/7: Updating package list..."
sudo apt-get update
echo "✓ Package list updated"
echo ""

echo "Step 4/7: Installing NVIDIA Container Toolkit..."
sudo apt-get install -y nvidia-container-toolkit
echo "✓ NVIDIA Container Toolkit installed"
echo ""

echo "Step 5/7: Configuring Docker runtime..."
sudo nvidia-ctk runtime configure --runtime=docker
echo "✓ Docker runtime configured"
echo ""

echo "Step 6/7: Verifying installation..."
if command -v nvidia-ctk &> /dev/null; then
    echo "✓ nvidia-ctk is installed"
    nvidia-ctk --version
else
    echo "✗ nvidia-ctk not found!"
    exit 1
fi
echo ""

echo "========================================"
echo "Installation Complete!"
echo "========================================"
echo ""
echo "NEXT STEPS:"
echo ""
echo "1. RESTART Docker Desktop from Windows"
echo "   - Right-click Docker Desktop icon"
echo "   - Select 'Restart Docker Desktop'"
echo ""
echo "2. After Docker restarts, test GPU access:"
echo "   docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi"
echo ""
echo "3. If nvidia-smi works, restart your project containers:"
echo "   cd /mnt/c/Users/uzair/VSCode/video_compilation/ybh-compilation-tool-2"
echo "   docker-compose down"
echo "   docker-compose up -d"
echo ""
echo "4. Verify GPU in your application:"
echo "   docker exec video-compilation-celery nvidia-smi"
echo "   docker exec video-compilation-celery python -c \"from workers.ffmpeg_builder import check_gpu; print(f'GPU Available: {check_gpu()}')\""
echo ""
echo "5. Run test job - GPU encoding will be 5-10x faster!"
echo "   python test_job_submission.py"
echo ""
