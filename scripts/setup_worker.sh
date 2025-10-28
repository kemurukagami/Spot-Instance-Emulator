#!/bin/bash
set -e

echo "=== Spot Instance Emulator - Worker Setup ==="
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root (sudo ./setup_worker.sh)"
    exit 1
fi

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Project root: $PROJECT_ROOT"
echo

# 1. Install Docker
echo "[1/5] Installing Docker..."
if ! command -v docker &> /dev/null; then
    apt-get update
    apt-get install -y docker.io
    systemctl start docker
    systemctl enable docker
    echo "✓ Docker installed"
else
    echo "✓ Docker already installed ($(docker --version))"
fi
echo

# 2. Install NVIDIA Container Toolkit (for GPU support)
echo "[2/5] Installing NVIDIA Container Toolkit..."
if ! command -v nvidia-ctk &> /dev/null; then
    distribution=$(. /etc/os-release;echo $ID$VERSION_ID)

    # Add NVIDIA GPG key
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

    # Add repository
    curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

    # Install toolkit
    apt-get update
    apt-get install -y nvidia-container-toolkit

    # Configure Docker to use NVIDIA runtime
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker

    echo "✓ NVIDIA Container Toolkit installed"
else
    echo "✓ NVIDIA Container Toolkit already installed"
fi
echo

# 3. Create data directories
echo "[3/5] Creating data directories..."
mkdir -p /data
mkdir -p /datasets
chmod 755 /data /datasets
echo "✓ Data directories created:"
echo "  - /data         (persistent container storage)"
echo "  - /datasets     (shared read-only datasets)"
echo

# 4. Build Docker base images
echo "[4/5] Building Docker base images..."
cd "$PROJECT_ROOT/sie/docker"
./build.sh
echo "✓ Base images built"
echo

# 5. Test Docker + GPU
echo "[5/5] Testing Docker GPU access..."
if nvidia-smi &> /dev/null; then
    echo "Testing GPU passthrough to container..."
    if docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
        echo "✓ GPU access working"
    else
        echo "⚠ Warning: GPU passthrough test failed. Check nvidia-docker configuration."
    fi
else
    echo "⚠ No GPU detected, skipping GPU test"
fi
echo

echo "=== Setup Complete ==="
echo
echo "You can now start the instance node:"
echo "  cd $PROJECT_ROOT"
echo "  source .venv/bin/activate"
echo "  python run_instance.py --head-node ws://<head-ip>:8000/ws --port 8001"
echo
echo "To test locally:"
echo "  # Terminal 1: Start head node"
echo "  python run_head.py --trace-file traces/p3-trace.csv --simulation-speed 10.0"
echo
echo "  # Terminal 2: Start instance node"
echo "  python run_instance.py --head-node ws://localhost:8000/ws --port 8001"
