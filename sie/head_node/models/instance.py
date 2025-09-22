from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime
from sie.common.constants import InstanceState, ConnectionState

class WorkerConnection(BaseModel):
    """Represents a physical machine connected to the head node"""
    worker_id: str
    hardware: Dict[str, Any]
    connection_state: ConnectionState = ConnectionState.UNASSIGNED
    connected_at: datetime = Field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    websocket_id: Optional[str] = None
    worker_ip: Optional[str] = None  # IP address for SSH access
    
class Instance(BaseModel):
    """Represents a spot instance assignment on a worker"""
    instance_id: str
    instance_type: str
    worker_id: str  # Links to WorkerConnection
    state: InstanceState = InstanceState.RUNNING
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    interruption_time: Optional[datetime] = None