from enum import Enum

class InstanceState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPING = "stopping"
    TERMINATED = "terminated"
    INTERRUPTED = "interrupted"

class MessageType(str, Enum):
    REGISTER = "register"
    HEARTBEAT = "heartbeat"
    STATUS = "status"
    INTERRUPT = "interrupt"
    ACKNOWLEDGE = "acknowledge"
    ERROR = "error"

DEFAULT_WARNING_TIME = 120  # seconds (2 minutes)
HEARTBEAT_INTERVAL = 30  # seconds
HEARTBEAT_TIMEOUT = 90  # seconds (3 missed heartbeats)