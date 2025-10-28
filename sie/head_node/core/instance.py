from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime
from sie.common.constants import InstanceState, ConnectionState

class WorkerConnection(BaseModel):
    """Represents a physical machine connected to the head node"""
    worker_id: str
    hardware: Dict[str, Any]
    instance_type: str  # Hardware-based instance type (e.g., p3.xlarge, m5.large)
    ip_address: str  # IP address of the worker machine
    connection_state: ConnectionState = ConnectionState.UNASSIGNED
    connected_at: datetime = Field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    websocket_id: Optional[str] = None
    
class Instance(BaseModel):
    """Represents a spot instance assignment on a worker"""
    instance_id: str
    instance_type: str
    worker_id: str  # Links to WorkerConnection
    user: str = "isaacy"  # User who requested this spot instance

    # Docker container fields
    container_name: Optional[str] = None  # spot-i-abc123
    ssh_port: Optional[int] = None        # Host port for SSH (e.g., 10001)
    ssh_username: str = "root"            # Username for SSH
    ssh_password: Optional[str] = None    # Generated password

    state: InstanceState = InstanceState.RUNNING
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    interruption_time: Optional[datetime] = None