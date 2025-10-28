# Spot Instance Emulator

A high-fidelity emulator for cloud spot instance behavior with trace-based availability simulation and Docker container isolation. Simulates AWS-like spot instances with interruptions, grace periods, and complete lifecycle management.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Configuration](#configuration)

---

## Features

**Trace-Based Simulation**: Replay real spot instance availability patterns from CSV trace files
**Docker Container Isolation**: Each spot instance runs in an isolated Docker container
**GPU Passthrough**: Full GPU access inside containers (NVIDIA GPUs)
**Realistic Interruptions**: 2-minute grace period warnings before termination
**Resource Limits**: Enforce CPU/RAM limits based on instance type
**SSH Access**: Direct SSH access to containers from anywhere
**Real-Time Visualization**: Web dashboard for monitoring simulation state
**Flexible Speed Control**: Run simulations at 1x, 10x, 50x, or any speed
**Multiple Workers**: Scale across multiple physical machines
**RESTful API**: Programmatic control via HTTP endpoints

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        HEAD NODE                            │
│  - Trace simulation controller                              │
│  - Spot instance pool manager                               │
│  - Worker orchestration                                     │
│  - REST API + WebSocket server                              │
│  - Real-time visualization dashboard                        │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ WebSocket
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐  ┌───────▼────────┐  ┌──────▼─────────┐
│  WORKER NODE 1 │  │  WORKER NODE 2 │  │  WORKER NODE N │
│                │  │                │  │                │
│  Container 1   │  │  Container 3   │  │  Container N   │
│  (spot-i-abc)  │  │  (spot-i-ghi)  │  │  (spot-i-xyz)  │
│  SSH: 10000    │  │  SSH: 10000    │  │  SSH: 10000    │
│  4x V100 GPUs  │  │  4x V100 GPUs  │  │  4x V100 GPUs  │
│                │  │                │  │                │
│  Container 2   │  │  Container 4   │  │                │
│  (spot-i-def)  │  │  (spot-i-jkl)  │  │                │
│  SSH: 10001    │  │  SSH: 10001    │  │                │
└────────────────┘  └────────────────┘  └────────────────┘
```

### Key Concepts

- **Head Node**: Central coordinator that manages trace simulation and worker assignments
- **Worker Node**: Physical machine that runs Docker containers (spot instances)
- **Spot Instance**: Virtual assignment from trace file, runs as isolated Docker container
- **Container**: Isolated environment with its own filesystem, processes, and SSH access
- **Trace File**: CSV file defining when spot instances appear/disappear over time

---

## System Requirements

### Head Node

- **OS**: Linux (Ubuntu 20.04+ recommended)
- **Python**: 3.8+
- **RAM**: 2GB minimum
- **Network**: Reachable by all worker nodes

### Worker Nodes

- **OS**: Linux (Ubuntu 20.04+ recommended)
- **Python**: 3.8+
- **Docker**: 20.10+
- **RAM**: 8GB+ (depends on instance types)
- **Storage**: 50GB+ for container data
- **GPUs** (optional): NVIDIA GPUs with driver 450.80.02+
- **Network**: Can reach head node

---

## Installation

### Step 1: Clone Repository

```bash
git clone <repository-url>
cd Spot-Instance-Emulator
```

### Step 2: Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Set Up Head Node

The head node only needs Python dependencies (already installed in Step 2).

**Verify installation:**
```bash
python run_head.py --help
```

### Step 4: Set Up Worker Nodes

**Each worker machine needs Docker and GPU support.**

#### Option A: Automated Setup (Recommended)

```bash
# Run one-time setup script (requires sudo)
sudo ./scripts/setup_worker.sh
```

This script:
- ✅ Installs Docker
- ✅ Installs NVIDIA Container Toolkit (for GPU support)
- ✅ Creates `/data` and `/datasets` directories
- ✅ Builds `spot-base:latest` Docker image
- ✅ Tests GPU passthrough

#### Option B: Manual Setup

**Install Docker:**
```bash
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl start docker
sudo systemctl enable docker
```

**Install NVIDIA Container Toolkit (for GPU support):**
```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)

# Add NVIDIA repository
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
    gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install toolkit
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

**Create directories:**
```bash
sudo mkdir -p /data /datasets
sudo chmod 755 /data /datasets
```

**Build Docker image:**
```bash
cd sie/docker
./build.sh
```

**Test GPU access:**
```bash
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
# Should display GPU information
```

### Step 5: Configure Firewall (If Needed)

**On head node:**
```bash
# Allow WebSocket connections from workers
sudo ufw allow 8000/tcp
```

**On worker nodes:**
```bash
# Allow SSH connections to containers
sudo ufw allow 10000:10100/tcp
```

---

## Quick Start

### 1. Prepare a Trace File

Create a simple trace file for testing:

```bash
mkdir -p traces

cat > traces/demo-trace.csv <<EOF
0,add,node1
0,add,node2
0,add,node3
60000,add,node4
120000,remove,node1
180000,add,node5
240000,remove,node2
300000,remove,node3
EOF
```

**Format:** `timestamp_ms,action,node_id`
- `timestamp_ms`: Milliseconds from trace start (0 = beginning)
- `action`: `add` (spot instance available) or `remove` (spot instance terminated)
- `node_id`: Unique identifier for the spot instance

### 2. Start Head Node

```bash
# Terminal 1
cd /path/to/Spot-Instance-Emulator
source .venv/bin/activate

python run_head.py \
  --trace-file traces/demo-trace.csv \
  --simulation-speed 10.0 \
  --instance-type p3.8xlarge \
  --port 8000
```

**Parameters:**
- `--trace-file`: Path to CSV trace file
- `--simulation-speed`: Speed multiplier (10.0 = 10x faster than real-time)
- `--instance-type`: Instance type for all trace nodes (default: p3.8xlarge)
- `--port`: Server port (default: 8000)

**Expected output:**
```
Starting Spot Instance Emulator - Head Node

Trace Simulation Enabled:
  Trace file: traces/demo-trace.csv
  Simulation speed: 10.0x
  Instance type: p3.8xlarge

External IP: 192.168.1.100:8000
WebSocket endpoint: ws://192.168.1.100:8000/ws
Admin API: http://192.168.1.100:8000/admin/
Visualization Dashboard: http://192.168.1.100:8000/visualization

INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

### 3. Start Worker Node

```bash
# Terminal 2 (can be on different machine)
cd /path/to/Spot-Instance-Emulator
source .venv/bin/activate

python run_instance.py \
  --head-node ws://192.168.1.100:8000/ws \
  --port 8001
```

**Parameters:**
- `--head-node`: WebSocket URL of head node
- `--port`: Local port for worker API (default: 8001)
- `--instance-type`: Override hardware detection (optional)

**Expected output:**
```
Starting Spot Instance Emulator - Instance Node

Worker ID: worker-gwhiz2-fb82525a
Instance type: p3.8xlarge (auto-detected from 4x V100 GPUs)
IP address: 192.168.1.100
Connecting to head node at ws://192.168.1.100:8000/ws
Connected to head node
```

### 4. Request a Spot Instance

```bash
# Terminal 3
curl -X POST http://192.168.1.100:8000/admin/request-spot-instance \
  -H "Content-Type: application/json" \
  -d '{"instance_type": "p3.8xlarge"}' | jq
```

**Response:**
```json
{
  "status": "success",
  "instance_id": "i-abc123def456",
  "spot_instance_id": "node1",
  "ip_address": "192.168.1.100",
  "ssh_port": 10000,
  "ssh_username": "root",
  "ssh_password": "aB3dEf9Gh2Jk4Lm6",
  "container_name": "spot-i-abc123def456",
  "ssh_command": "ssh -p 10000 root@192.168.1.100",
  "message": "Allocated p3.8xlarge spot instance container at 192.168.1.100:10000"
}
```

### 5. SSH Into Your Spot Instance

**From your local machine:**

```bash
ssh -p 10000 root@192.168.1.100
# Enter password: aB3dEf9Gh2Jk4Lm6
```

**Inside the container:**

```bash
# Verify environment
hostname
# Output: spot-i-abc123def456

nvidia-smi
# Output: 4x Tesla V100 GPUs

# Install your software
apt-get update
apt-get install -y python3 python3-pip

# Install ML frameworks
pip3 install torch torchvision

# Verify GPU access
python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
# Output: CUDA available: True

# Run your workload
python3 train.py
```

### 6. Observe Spot Interruption

When the trace reaches a `remove` event for your spot instance:

**In SSH session:**
```
# Connection suddenly drops
client_loop: send disconnect: Broken pipe
```

**Worker logs:**
```
⚠ Spot interruption: instance i-abc123def456 terminating in 12.0s real-time (120s sim-time at 10.0x speed)
INFO:     Stopping container spot-i-abc123def456 with signal SIGTERM
[After 12 seconds]
INFO:     Removing container spot-i-abc123def456
INFO:     Container removed, worker ready for new assignment
```

**Container lifecycle:**
1. SIGTERM sent to all processes (grace period starts)
2. After grace period: container and `/data` directory completely removed
3. Worker returns to UNASSIGNED state

---

## Usage

### Starting the System

**Minimal setup (single machine):**
```bash
# Terminal 1: Head node
python run_head.py --trace-file traces/p3-trace.csv --simulation-speed 10.0

# Terminal 2: Worker
python run_instance.py --head-node ws://localhost:8000/ws --port 8001

# Terminal 3: Request instance
curl -X POST http://localhost:8000/admin/request-spot-instance \
  -H "Content-Type: application/json" \
  -d '{"instance_type": "p3.8xlarge"}' | jq
```

**Multi-machine setup:**
```bash
# On head node server (e.g., headnode.example.com)
python run_head.py \
  --trace-file ~/traces/production-trace.csv \
  --simulation-speed 1.0 \
  --host 0.0.0.0 \
  --port 8000

# On worker server 1 (e.g., worker1.example.com)
python run_instance.py \
  --head-node ws://headnode.example.com:8000/ws \
  --port 8001

# On worker server 2 (e.g., worker2.example.com)
python run_instance.py \
  --head-node ws://headnode.example.com:8000/ws \
  --port 8001

# From your laptop
curl -X POST http://headnode.example.com:8000/admin/request-spot-instance \
  -H "Content-Type: application/json" \
  -d '{"instance_type": "p3.8xlarge"}' | jq
```

### Visualization Dashboard

Open in browser:
```
http://<head-node-ip>:8000/visualization
```

**Features:**
- Real-time spot instance pool visualization
- Worker status and assignments
- Simulation timeline with progress
- Interactive controls (pause/resume, speed, seek)
- Live updates via WebSocket

---

## Configuration

### Instance Types

The system auto-detects hardware and maps to AWS instance types:

**GPU Instances:**
- `p3.xlarge`: 1x V100, 4 vCPUs, 61GB RAM
- `p3.2xlarge`: 1x V100, 8 vCPUs, 61GB RAM
- `p3.8xlarge`: 4x V100, 32 vCPUs, 244GB RAM (default for p3-*.csv traces)
- `p3.16xlarge`: 8x V100, 64 vCPUs, 488GB RAM
- `g4dn.xlarge`: 1x T4, 4 vCPUs, 16GB RAM
- `g5.xlarge`: 1x A10G, 4 vCPUs, 16GB RAM

**CPU Instances:**
- `m5.large`: 2 vCPUs, 8GB RAM
- `m5.xlarge`: 4 vCPUs, 16GB RAM
- `t2.micro`: 1 vCPU, 1GB RAM

### Trace File Format

**Basic format:**
```csv
timestamp_ms,action,node_id
0,add,node1
60000,add,node2
120000,remove,node1
```

**Best practices:**
- Sort events by timestamp
- Use unique node IDs
- Start at timestamp 0
- Actions: `add` or `remove`

---