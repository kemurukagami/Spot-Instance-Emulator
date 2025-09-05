# Instance Node Module

The instance node simulates an individual spot instance with hardware detection, health reporting, and interruption handling.

## Features

### 1. Hardware Detection
- **Automatic Detection**: Discovers system specifications on startup
- **CPU Information**: Cores, threads, model, frequency
- **Memory**: Total RAM available
- **GPU Detection**: NVIDIA GPU support via nvidia-smi
- **Storage**: Disk capacity detection
- **Custom Profiles**: Can override with specific instance type

### 2. WebSocket Client
- **Auto-Registration**: Connects and registers with head node on startup
- **Heartbeat System**: Sends health status every 30 seconds
- **Interruption Handling**: Receives and processes interruption commands
- **Auto-Reconnection**: Attempts to reconnect if connection lost
- **Graceful Shutdown**: Clean disconnection on termination

### 3. User-Facing REST API

#### GET /instance/status
Returns current instance status:
```json
{
  "instance_id": "i-abc123",
  "instance_type": "t2.micro",
  "state": "running",
  "hardware": {
    "cpu": {"cores": 2, "threads": 4, "model": "Intel Xeon"},
    "memory_mb": 8192,
    "gpus": [],
    "storage_gb": 100
  }
}
```

#### GET /instance/metadata
EC2-compatible metadata service:
```json
{
  "instance-id": "i-abc123",
  "instance-type": "t2.micro",
  "local-hostname": "instance-i-abc123",
  "local-ipv4": "10.0.0.1",
  "public-hostname": "ec2-instance-i-abc123.compute-1.amazonaws.com",
  "public-ipv4": "54.0.0.1"
}
```

#### GET /instance/termination-time
Returns scheduled termination information:
```json
{
  "termination_time": "2024-01-01T10:32:00Z",
  "time_remaining": 118.5
}
```

#### POST /webhook/configure
Configure webhook for interruption notifications:
```json
{
  "url": "http://myapp:3000/spot-interrupt",
  "enabled": true
}
```

### 4. Interruption Handling
- **2-Minute Warning**: Standard AWS spot instance behavior
- **Webhook Notifications**: Sends POST to configured URL
- **Graceful Termination**: Allows cleanup before shutdown
- **State Updates**: Tracks interruption status

## Architecture

### Core Components

1. **HardwareDetector** (`core/hardware.py`)
   - Uses psutil for system information
   - Detects CPU, memory, storage
   - Optional GPU detection via nvidia-smi

2. **WebSocketClient** (`core/websocket_client.py`)
   - Maintains connection to head node
   - Handles registration and heartbeats
   - Processes interruption messages
   - Manages reconnection logic

3. **Status API** (`api/status.py`)
   - Instance status endpoints
   - EC2 metadata emulation
   - Termination time tracking

4. **Webhook System** (`api/webhook.py`)
   - User notification configuration
   - Interruption notice delivery
   - Async HTTP client for webhooks

## Configuration

### Environment Variables
- `HEAD_NODE_URL`: WebSocket URL of head node (default: ws://localhost:8000/ws)
- `INSTANCE_ID`: Instance identifier (auto-generated if not set)
- `INSTANCE_TYPE`: AWS instance type (default: t2.micro)
- `INSTANCE_PORT`: REST API port (default: 8001)
- `WEBHOOK_URL`: URL for interruption notifications

### Command Line Arguments
```bash
python run_instance.py \
  --port 8001 \
  --instance-id i-custom \
  --instance-type p3.2xlarge \
  --head-node ws://head:8000/ws \
  --webhook-url http://app:3000/interrupt
```

## Interruption Flow

1. **Reception**: WebSocket receives INTERRUPT message from head node
2. **State Update**: Instance marked as "interrupted"
3. **Webhook Notification**: Immediate POST to configured webhook:
   ```json
   {
     "action": "terminate",
     "time": "2024-01-01T10:32:00Z",
     "instance_id": "i-abc123",
     "reason": "spot-interruption",
     "warning_seconds": 120
   }
   ```
4. **Countdown**: 2-minute timer starts
5. **Termination**: Clean shutdown after warning period

## Hardware Profile Format

```json
{
  "cpu": {
    "cores": 4,
    "threads": 8,
    "model": "Intel(R) Xeon(R) CPU E5-2686 v4",
    "frequency_mhz": 2300.0
  },
  "memory_mb": 16384,
  "gpus": [
    {
      "model": "Tesla V100-SXM2-16GB",
      "memory_mb": 16384,
      "count": 1
    }
  ],
  "storage_gb": 500
}
```

## Running an Instance Node

```bash
# Basic startup
python sie/instance_node/main.py

# With custom configuration
python run_instance.py --port 8001 --instance-type m5.large

# Multiple instances on different ports
python run_instance.py --port 8001
python run_instance.py --port 8002
python run_instance.py --port 8003
```

## Health Monitoring

The instance node maintains health through:
- **Heartbeats**: Sent every 30 seconds
- **State Reporting**: Current instance state in each heartbeat
- **Connection Monitoring**: Detects and handles disconnections
- **Automatic Recovery**: Attempts reconnection on failure

## Error Handling

- **Connection Failure**: Retries with exponential backoff
- **Registration Failure**: Logs error and retries
- **Webhook Failure**: Logs error but continues operation
- **Hardware Detection Failure**: Uses default values
- **Graceful Degradation**: Continues with partial functionality