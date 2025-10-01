from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Set
from datetime import datetime
from enum import Enum

class TraceAction(str, Enum):
    ADD = "add"
    REMOVE = "remove"

class TraceEvent(BaseModel):
    """Single event from trace file"""
    timestamp_ms: int
    action: TraceAction
    node_id: str

    def __lt__(self, other):
        """Enable sorting by timestamp"""
        return self.timestamp_ms < other.timestamp_ms

class AvailableSpotInstance(BaseModel):
    """Represents a spot instance that can be assigned to workers"""
    spot_instance_id: str  # From trace (e.g., "node1")
    instance_type: str     # e.g., "p3.xlarge"
    available_since: datetime = Field(default_factory=datetime.utcnow)
    assigned_worker_id: Optional[str] = None

    @property
    def is_assigned(self) -> bool:
        return self.assigned_worker_id is not None

class TraceSimulator(BaseModel):
    """Manages trace playback and spot instance availability"""
    events: List[TraceEvent] = Field(default_factory=list)
    current_time_ms: int = 0
    available_spot_instances: Dict[str, AvailableSpotInstance] = Field(default_factory=dict)
    start_time: datetime = Field(default_factory=datetime.utcnow)
    simulation_speed: float = 1.0  # 1.0 = real-time, 2.0 = 2x speed
    is_paused: bool = False

    class Config:
        arbitrary_types_allowed = True

    def get_unassigned_spot_instances(self) -> List[AvailableSpotInstance]:
        """Get all available spot instances that aren't assigned to workers"""
        return [spot for spot in self.available_spot_instances.values()
                if not spot.is_assigned]

    def get_assigned_spot_instances(self) -> List[AvailableSpotInstance]:
        """Get all spot instances currently assigned to workers"""
        return [spot for spot in self.available_spot_instances.values()
                if spot.is_assigned]

    def get_spot_instance_by_worker(self, worker_id: str) -> Optional[AvailableSpotInstance]:
        """Get spot instance assigned to a specific worker"""
        for spot in self.available_spot_instances.values():
            if spot.assigned_worker_id == worker_id:
                return spot
        return None

    def get_available_by_type(self, instance_type: str) -> List[AvailableSpotInstance]:
        """Get unassigned spot instances of a specific type"""
        return [spot for spot in self.get_unassigned_spot_instances()
                if spot.instance_type == instance_type]