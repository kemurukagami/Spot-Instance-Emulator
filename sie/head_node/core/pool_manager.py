from typing import Dict, Optional, List
from datetime import datetime, timedelta
import asyncio
from sie.head_node.models import Instance
from sie.common.constants import InstanceState, HEARTBEAT_TIMEOUT
import logging

logger = logging.getLogger(__name__)

class PoolManager:
    def __init__(self):
        self.instances: Dict[str, Instance] = {}
        self.websocket_connections: Dict[str, any] = {}  # websocket_id -> connection
        self.instance_to_ws: Dict[str, str] = {}  # instance_id -> websocket_id
        
    def register_instance(self, instance: Instance, websocket_id: str) -> None:
        """Register a new instance in the pool"""
        instance.websocket_id = websocket_id
        instance.state = InstanceState.RUNNING
        self.instances[instance.instance_id] = instance
        self.instance_to_ws[instance.instance_id] = websocket_id
        logger.info(f"Registered instance {instance.instance_id}")
        
    def unregister_instance(self, instance_id: str) -> None:
        """Remove instance from the pool"""
        if instance_id in self.instances:
            instance = self.instances[instance_id]
            instance.state = InstanceState.TERMINATED
            del self.instances[instance_id]
            if instance_id in self.instance_to_ws:
                del self.instance_to_ws[instance_id]
            logger.info(f"Unregistered instance {instance_id}")
            
    def update_heartbeat(self, instance_id: str) -> bool:
        """Update last heartbeat time for instance"""
        if instance_id in self.instances:
            self.instances[instance_id].last_heartbeat = datetime.utcnow()
            return True
        return False
        
    def get_instance(self, instance_id: str) -> Optional[Instance]:
        """Get instance by ID"""
        return self.instances.get(instance_id)
        
    def get_all_instances(self) -> List[Instance]:
        """Get all registered instances"""
        return list(self.instances.values())
        
    def check_health(self) -> List[str]:
        """Check for instances that haven't sent heartbeat"""
        now = datetime.utcnow()
        unhealthy = []
        for instance_id, instance in self.instances.items():
            time_since_heartbeat = (now - instance.last_heartbeat).total_seconds()
            if time_since_heartbeat > HEARTBEAT_TIMEOUT:
                unhealthy.append(instance_id)
                logger.warning(f"Instance {instance_id} is unhealthy (no heartbeat for {time_since_heartbeat}s)")
        return unhealthy
        
    def mark_for_interruption(self, instance_id: str, warning_time: int = 120) -> bool:
        """Mark instance for interruption"""
        if instance_id in self.instances:
            instance = self.instances[instance_id]
            instance.state = InstanceState.INTERRUPTED
            instance.interruption_time = datetime.utcnow() + timedelta(seconds=warning_time)
            logger.info(f"Marked instance {instance_id} for interruption in {warning_time}s")
            return True
        return False
        
    def get_websocket_id(self, instance_id: str) -> Optional[str]:
        """Get WebSocket connection ID for an instance"""
        return self.instance_to_ws.get(instance_id)