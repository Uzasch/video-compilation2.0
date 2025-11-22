#!/bin/bash
# Install NVIDIA Container Toolkit in WSL 2
# Run this script in WSL 2 Ubuntu terminal

set -e

echo "=== Installing NVIDIA Container Toolkit ==="

# 1. Setup package repository
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 2. Update package list
sudo apt-get update

# 3. Install NVIDIA Container Toolkit
sudo apt-get install -y nvidia-container-toolkit

# 4. Configure Docker to use NVIDIA runtime
sudo nvidia-ctk runtime configure --runtime=docker

# 5. Restart Docker (in WSL 2, Docker Desktop manages this)
echo ""
echo "=== Installation Complete! ==="
echo ""
echo "Next steps:"
echo "1. Restart Docker Desktop from Windows"
echo "2. Run: docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi"
echo "3. If nvidia-smi works, GPU is ready!"
