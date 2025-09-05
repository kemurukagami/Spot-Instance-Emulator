from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime
from sie.common.constants import InstanceState

class Instance(BaseModel):
    instance_id: str
    instance_type: str
    hardware: Dict[str, Any]
    state: InstanceState = InstanceState.PENDING
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    interruption_time: Optional[datetime] = None
    websocket_id: Optional[str] = None