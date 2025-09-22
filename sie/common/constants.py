from enum import Enum
import socket
import subprocess

class ConnectionState(str, Enum):
    UNASSIGNED = "unassigned"  # Connected worker, no instance ID assigned
    ASSIGNED = "assigned"      # Worker has been assigned an instance ID
    INTERRUPTED = "interrupted" # Instance interrupted but worker connection alive

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
    ASSIGN_INSTANCE = "assign_instance"
    UNASSIGN_INSTANCE = "unassign_instance"
    CREATE_USER = "create_user"
    DELETE_USER = "delete_user"
    ERROR = "error"

DEFAULT_WARNING_TIME = 120  # seconds (2 minutes)
HEARTBEAT_INTERVAL = 30  # seconds
HEARTBEAT_TIMEOUT = 90  # seconds (3 missed heartbeats)

def get_primary_ip() -> str:
    """Get the primary IP address for external connections"""
    try:
        # Method 1: Use ip route to get the IP used for external connections
        result = subprocess.run(['ip', 'route', 'get', '1.1.1.1'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'src' in line:
                    return line.split('src')[1].strip().split()[0]
    except (subprocess.SubprocessError, FileNotFoundError, IndexError):
        pass
    
    try:
        # Method 2: Connect to a remote address to determine local IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except (socket.error, OSError):
        pass
    
    try:
        # Method 3: Get hostname IP
        return socket.gethostbyname(socket.getfqdn())
    except socket.error:
        pass
    
    # Fallback
    return "127.0.0.1"