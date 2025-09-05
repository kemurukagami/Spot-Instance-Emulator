# Common Module

Shared data structures, constants, and message formats used by both head node and instance nodes.

## Components

### 1. Constants (`constants.py`)

#### Instance States
- `PENDING`: Instance is initializing
- `RUNNING`: Instance is active and healthy
- `STOPPING`: Instance is shutting down
- `TERMINATED`: Instance has been terminated
- `INTERRUPTED`: Instance has received interruption notice

#### Message Types
- `REGISTER`: New instance registration
- `HEARTBEAT`: Health check message
- `STATUS`: State update message
- `INTERRUPT`: Interruption command
- `ACKNOWLEDGE`: Message acknowledgment
- `ERROR`: Error notification

#### Timing Constants
- `DEFAULT_WARNING_TIME`: 120 seconds (2-minute warning)
- `HEARTBEAT_INTERVAL`: 30 seconds
- `HEARTBEAT_TIMEOUT`: 90 seconds (3 missed heartbeats)

### 2. Message Formats (`messages.py`)

All messages inherit from `BaseMessage` with common fields:
- `type`: MessageType enum
- `timestamp`: UTC timestamp (auto-generated)

#### RegisterMessage
Instance registration with hardware profile:
```python
{
    "type": "register",
    "timestamp": "2024-01-01T10:00:00",
    "instance_id": "i-abc123",
    "instance_type": "t2.micro",
    "hardware": {
        "cpu": {...},
        "memory_mb": 8192,
        "gpus": [...],
        "storage_gb": 100
    }
}
```

#### HeartbeatMessage
Periodic health check:
```python
{
    "type": "heartbeat",
    "timestamp": "2024-01-01T10:00:30",
    "instance_id": "i-abc123",
    "state": "running"
}
```

#### InterruptMessage
Spot interruption command:
```python
{
    "type": "interrupt",
    "timestamp": "2024-01-01T10:30:00",
    "instance_id": "i-abc123",
    "warning_time": 120,
    "reason": "spot-interruption"
}
```

#### AcknowledgeMessage
Message receipt confirmation:
```python
{
    "type": "acknowledge",
    "timestamp": "2024-01-01T10:00:01",
    "instance_id": "i-abc123",
    "original_message_type": "register"
}
```

#### StatusMessage
Instance state update:
```python
{
    "type": "status",
    "timestamp": "2024-01-01T10:00:00",
    "instance_id": "i-abc123",
    "state": "interrupted",
    "details": {
        "interruption_time": "2024-01-01T10:32:00"
    }
}
```

## Usage

### Importing Constants
```python
from sie.common.constants import InstanceState, MessageType, HEARTBEAT_INTERVAL

# Use enums
state = InstanceState.RUNNING
msg_type = MessageType.HEARTBEAT

# Use timing constants
interval = HEARTBEAT_INTERVAL  # 30 seconds
```

### Creating Messages
```python
from sie.common.messages import RegisterMessage, HeartbeatMessage

# Create registration message
register_msg = RegisterMessage(
    instance_id="i-abc123",
    instance_type="t2.micro",
    hardware=hardware_dict
)

# Convert to JSON for transmission
json_data = register_msg.dict()
```

### Parsing Messages
```python
from sie.common.messages import HeartbeatMessage

# Parse incoming JSON
data = {"type": "heartbeat", "instance_id": "i-abc123", "state": "running"}
msg = HeartbeatMessage(**data)

# Access fields
print(msg.instance_id)
print(msg.state)
```

## Design Principles

1. **Type Safety**: Pydantic models ensure type validation
2. **Immutability**: Message objects are read-only after creation
3. **Extensibility**: Easy to add new message types or fields
4. **Consistency**: All messages follow same structure pattern
5. **No Business Logic**: Pure data structures, no behavior

## Message Flow

```
Instance Node                    Head Node
     |                              |
     |---- REGISTER message ------> |
     |                              |
     |<--- ACKNOWLEDGE message ---- |
     |                              |
     |---- HEARTBEAT message -----> |
     |      (every 30 sec)          |
     |                              |
     |<--- INTERRUPT message ------ |
     |      (on interruption)       |
     |                              |
     |---- STATUS message --------> |
     |    (state: interrupted)      |
```

## Validation

All messages are validated using Pydantic:
- Required fields must be present
- Types must match specifications
- Enums must be valid values
- Timestamps are automatically generated

Example validation error:
```python
# This will raise ValidationError
msg = RegisterMessage(
    instance_id="i-abc123"
    # Missing required fields: instance_type, hardware
)
```

## Future Extensions

The common module is designed to be extended with:
- Additional message types (pricing, capacity, etc.)
- New instance states (hibernating, rebalancing)
- Enhanced hardware specifications
- Message versioning for backward compatibility