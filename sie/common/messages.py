from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from .constants import MessageType, InstanceState

class BaseMessage(BaseModel):
    type: MessageType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
class RegisterMessage(BaseMessage):
    type: MessageType = MessageType.REGISTER
    instance_id: str
    instance_type: str
    hardware: Dict[str, Any]
    
class HeartbeatMessage(BaseMessage):
    type: MessageType = MessageType.HEARTBEAT
    instance_id: str
    state: InstanceState
    
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