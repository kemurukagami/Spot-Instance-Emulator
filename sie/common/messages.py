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
    instance_type: str  # Inferred from hardware (e.g., p3.xlarge, m5.large)
    ip_address: str  # IP address of the worker machine
    instance_id: Optional[str] = None  # Will be None for unassigned workers
    
class HeartbeatMessage(BaseMessage):
    type: MessageType = MessageType.HEARTBEAT
    worker_id: str
    connection_state: ConnectionState
    instance_id: Optional[str] = None  # Only present when assigned
    
class InterruptMessage(BaseMessage):
    type: MessageType = MessageType.INTERRUPT
    instance_id: str
    warning_time: int = 120  # seconds (in simulation time)
    reason: str = "spot-interruption"
    simulation_speed: float = 1.0  # Simulation speed multiplier
    
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

# Docker container messages
class CreateContainerMessage(BaseMessage):
    """Head node → Worker: Create Docker container for spot instance"""
    type: MessageType = MessageType.CREATE_CONTAINER
    container_name: str          # spot-i-abc123
    ssh_port: int                # Host port (e.g., 10001)
    ssh_password: str            # Generated password
    instance_type: str           # For resource limits
    base_image: str = "spot-base:latest"  # Docker image to use

class ContainerCreatedMessage(BaseMessage):
    """Worker → Head node: Container created successfully"""
    type: MessageType = MessageType.CONTAINER_CREATED
    container_name: str
    success: bool
    error: Optional[str] = None

class StopContainerMessage(BaseMessage):
    """Head node → Worker: Stop container (on interruption)"""
    type: MessageType = MessageType.STOP_CONTAINER
    container_name: str
    signal: str = "SIGTERM"

class RemoveContainerMessage(BaseMessage):
    """Head node → Worker: Remove container (on unassignment)"""
    type: MessageType = MessageType.REMOVE_CONTAINER
    container_name: str