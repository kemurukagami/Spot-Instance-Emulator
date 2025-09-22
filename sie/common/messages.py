from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from .constants import MessageType, InstanceState, ConnectionState

class BaseMessage(BaseModel):
    type: MessageType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
class RegisterMessage(BaseMessage):
    type: MessageType = MessageType.REGISTER
    worker_id: str  # Physical machine identifier
    hardware: Dict[str, Any]
    instance_id: Optional[str] = None  # Will be None for unassigned workers
    
class HeartbeatMessage(BaseMessage):
    type: MessageType = MessageType.HEARTBEAT
    worker_id: str
    connection_state: ConnectionState
    instance_id: Optional[str] = None  # Only present when assigned
    
class InterruptMessage(BaseMessage):
    type: MessageType = MessageType.INTERRUPT
    instance_id: str
    warning_time: int = 120  # seconds
    reason: str = "spot-interruption"
    
class AcknowledgeMessage(BaseMessage):
    type: MessageType = MessageType.ACKNOWLEDGE
    instance_id: str
    original_message_type: MessageType
    
class StatusMessage(BaseMessage):
    type: MessageType = MessageType.STATUS
    instance_id: str
    state: InstanceState
    details: Optional[Dict[str, Any]] = None
    
class AssignInstanceMessage(BaseMessage):
    type: MessageType = MessageType.ASSIGN_INSTANCE
    worker_id: str
    instance_id: str
    instance_type: str
    
class UnassignInstanceMessage(BaseMessage):
    type: MessageType = MessageType.UNASSIGN_INSTANCE
    instance_id: str
    worker_id: str

class CreateUserMessage(BaseMessage):
    type: MessageType = MessageType.CREATE_USER
    username: str
    ssh_public_key: str
    assignment_id: str
    
class DeleteUserMessage(BaseMessage):
    type: MessageType = MessageType.DELETE_USER
    username: str
    assignment_id: str