#!/bin/bash
set -e

echo "=== Building Spot Instance Emulator Docker Image ==="
echo

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Build base image
echo "Building minimal base image..."
docker build -t spot-base:latest -f "$SCRIPT_DIR/base/Dockerfile" "$SCRIPT_DIR/base/"
echo "Base image built: spot-base:latest"
echo

echo "=== Image built successfully! ==="
echo
echo "This is a minimal Ubuntu 22.04 image with:"
echo "  - SSH server"
echo "  - Basic utilities (vim, nano, curl, wget, sudo)"
echo "  - Clean slate for users to install their own software"
echo
echo "Users can install their own:"
echo "  - Python/Conda/Julia/R"
echo "  - CUDA toolkit (any version)"
echo "  - ML frameworks (PyTorch, TensorFlow, JAX, etc.)"
echo "  - Any other packages"
echo
echo "Available images:"
docker images | grep -E "^spot-" || true
