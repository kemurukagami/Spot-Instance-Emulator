# Head Node Module

The head node is the central supervisor that manages the pool of spot instances and orchestrates their lifecycle.

## Features

### 1. Instance Pool Management
- **Registration**: Accepts new instance connections via WebSocket
- **Tracking**: Maintains real-time inventory of all instances with their hardware specs
- **Health Monitoring**: Tracks heartbeats and identifies unhealthy instances
- **State Management**: Manages instance states (pending, running, interrupted, terminated)

### 2. WebSocket Communication
- **Bidirectional Messaging**: Real-time communication with instance nodes
- **Message Types Supported**:
  - `REGISTER`: New instance registration with hardware profile
  - `HEARTBEAT`: Periodic health checks from instances
  - `INTERRUPT`: Send interruption commands to instances
  - `ACKNOWLEDGE`: Confirmation of received messages
  - `STATUS`: Instance state updates

### 3. Admin API Endpoints

#### GET /admin/instances
Returns list of all registered instances with their details:
```json
[{
  "instance_id": "i-abc123",
  "instance_type": "t2.micro",
  "state": "running",
  "hardware": {...},
  "registered_at": "2024-01-01T10:00:00",
  "last_heartbeat": "2024-01-01T10:30:00"
}]
```

#### GET /admin/instances/{instance_id}
Returns detailed information about a specific instance.

#### POST /admin/interrupt
Triggers manual interruption for an instance:
```json
{
  "instance_id": "i-abc123",
  "warning_time": 120
}
```

#### GET /admin/health
Returns pool health status:
```json
{
  "total_instances": 10,
  "healthy_instances": 9,
  "unhealthy_instances": ["i-xyz789"]
}
```

## Architecture

### Core Components

1. **PoolManager** (`core/pool_manager.py`)
   - Maintains instance registry
   - Tracks WebSocket connections
   - Manages instance lifecycle
   - Monitors health via heartbeats

2. **ConnectionManager** (`api/websocket.py`)
   - Handles WebSocket connections
   - Routes messages between head node and instances
   - Manages connection lifecycle

3. **Admin Router** (`api/admin.py`)
   - REST API for administrative operations
   - Instance monitoring and control
   - Manual interruption triggers

## Configuration

### Environment Variables
- `HOST`: Server host (default: 0.0.0.0)
- `PORT`: Server port (default: 8000)

### Constants
- `HEARTBEAT_TIMEOUT`: 90 seconds (3 missed heartbeats)
- `DEFAULT_WARNING_TIME`: 120 seconds (2 minutes)

## WebSocket Protocol

### Connection Flow
1. Instance connects to `ws://head-node:8000/ws`
2. Instance sends REGISTER message with hardware profile
3. Head node acknowledges and adds to pool
4. Instance sends periodic HEARTBEAT messages
5. Head node can send INTERRUPT message anytime

### Message Format
All messages use JSON with required fields:
- `type`: Message type enum
- `timestamp`: UTC timestamp
- `instance_id`: Instance identifier
- Additional fields based on message type

## Running the Head Node

```bash
# Direct execution
python sie/head_node/main.py

# Using startup script
python run_head.py
```

## API Documentation

FastAPI auto-generates interactive documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Monitoring

The head node logs all significant events:
- Instance registrations/deregistrations
- Heartbeat failures
- Interruption triggers
- WebSocket connection events

## Error Handling

- **Connection Loss**: Automatically removes instance from pool
- **Missing Heartbeats**: Marks instance as unhealthy after timeout
- **Invalid Messages**: Logs error and continues operation
- **Duplicate Registration**: Updates existing instance data