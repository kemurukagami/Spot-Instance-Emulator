from typing import Dict, Optional, List
from datetime import datetime, timedelta
import asyncio
import uuid
from sie.head_node.models.instance import Instance, WorkerConnection
from sie.common.constants import InstanceState, ConnectionState, HEARTBEAT_TIMEOUT
import logging

logger = logging.getLogger(__name__)

class PoolManager:
    def __init__(self):
        # Track physical worker connections
        self.workers: Dict[str, WorkerConnection] = {}  # worker_id -> WorkerConnection
        self.websocket_connections: Dict[str, any] = {}  # websocket_id -> connection
        self.worker_to_ws: Dict[str, str] = {}  # worker_id -> websocket_id
        
        # Track instance assignments (dynamic, can be created/destroyed)
        self.instances: Dict[str, Instance] = {}  # instance_id -> Instance
        self.worker_to_instance: Dict[str, str] = {}  # worker_id -> instance_id
        
    # Worker connection management
    def register_worker(self, worker: WorkerConnection, websocket_id: str) -> None:
        """Register a new worker connection"""
        worker.websocket_id = websocket_id
        self.workers[worker.worker_id] = worker
        self.worker_to_ws[worker.worker_id] = websocket_id
        logger.info(f"Registered worker {worker.worker_id} in {worker.connection_state.value} state")
        
    def unregister_worker(self, worker_id: str) -> None:
        """Remove worker connection (when disconnected)"""
        if worker_id in self.workers:
            # If worker has assigned instance, clean it up
            if worker_id in self.worker_to_instance:
                instance_id = self.worker_to_instance[worker_id]
                self.unassign_instance(instance_id)
            
            del self.workers[worker_id]
            if worker_id in self.worker_to_ws:
                del self.worker_to_ws[worker_id]
            logger.info(f"Unregistered worker {worker_id}")
            
    def update_worker_heartbeat(self, worker_id: str, connection_state: ConnectionState, instance_id: Optional[str] = None) -> bool:
        """Update worker heartbeat and sync state"""
        if worker_id in self.workers:
            worker = self.workers[worker_id]
            worker.last_heartbeat = datetime.utcnow()
            worker.connection_state = connection_state
            
            # Also update instance heartbeat if assigned
            if instance_id and instance_id in self.instances:
                self.instances[instance_id].last_heartbeat = datetime.utcnow()
            
            return True
        return False
        
    def get_worker(self, worker_id: str) -> Optional[WorkerConnection]:
        """Get worker by ID"""
        return self.workers.get(worker_id)
        
    def get_unassigned_workers(self) -> List[WorkerConnection]:
        """Get all workers in UNASSIGNED state"""
        return [w for w in self.workers.values() if w.connection_state == ConnectionState.UNASSIGNED]
        
    def get_assigned_workers(self) -> List[WorkerConnection]:
        """Get all workers in ASSIGNED state"""
        return [w for w in self.workers.values() if w.connection_state == ConnectionState.ASSIGNED]
    
    # Instance assignment management
    def assign_instance(self, worker_id: str, instance_type: str) -> Optional[str]:
        """Assign an instance ID to an unassigned worker"""
        if worker_id not in self.workers:
            logger.error(f"Cannot assign instance: worker {worker_id} not found")
            return None
            
        worker = self.workers[worker_id]
        if worker.connection_state != ConnectionState.UNASSIGNED:
            logger.error(f"Cannot assign instance: worker {worker_id} is not unassigned (state: {worker.connection_state})")
            return None
            
        # Generate unique instance ID
        instance_id = f"i-{uuid.uuid4().hex[:8]}"
        
        # Create instance record
        instance = Instance(
            instance_id=instance_id,
            instance_type=instance_type,
            worker_id=worker_id,
            state=InstanceState.RUNNING
        )
        
        # Update tracking
        self.instances[instance_id] = instance
        self.worker_to_instance[worker_id] = instance_id
        worker.connection_state = ConnectionState.ASSIGNED
        
        logger.info(f"Assigned instance {instance_id} ({instance_type}) to worker {worker_id}")
        return instance_id
        
    def unassign_instance(self, instance_id: str) -> bool:
        """Unassign an instance and return worker to UNASSIGNED state"""
        if instance_id not in self.instances:
            logger.error(f"Cannot unassign: instance {instance_id} not found")
            return False
            
        instance = self.instances[instance_id]
        worker_id = instance.worker_id
        
        # Clean up instance tracking
        del self.instances[instance_id]
        if worker_id in self.worker_to_instance:
            del self.worker_to_instance[worker_id]
            
        # Return worker to unassigned state
        if worker_id in self.workers:
            self.workers[worker_id].connection_state = ConnectionState.UNASSIGNED
            logger.info(f"Unassigned instance {instance_id}, worker {worker_id} returned to UNASSIGNED state")
            
        return True
        
    def mark_for_interruption(self, instance_id: str, warning_time: int = 120) -> bool:
        """Mark instance for interruption (worker moves to INTERRUPTED state)"""
        if instance_id not in self.instances:
            logger.error(f"Cannot interrupt: instance {instance_id} not found")
            return False
            
        instance = self.instances[instance_id]
        worker_id = instance.worker_id
        
        # Update both instance and worker states
        instance.state = InstanceState.INTERRUPTED
        instance.interruption_time = datetime.utcnow() + timedelta(seconds=warning_time)
        
        if worker_id in self.workers:
            self.workers[worker_id].connection_state = ConnectionState.INTERRUPTED
            
        logger.info(f"Marked instance {instance_id} for interruption in {warning_time}s")
        return True
        
    # Query methods
    def get_instance(self, instance_id: str) -> Optional[Instance]:
        """Get instance by ID"""
        return self.instances.get(instance_id)
        
    def get_all_instances(self) -> List[Instance]:
        """Get all assigned instances"""
        return list(self.instances.values())
        
    def get_all_workers(self) -> List[WorkerConnection]:
        """Get all connected workers"""
        return list(self.workers.values())
        
    def get_instance_for_worker(self, worker_id: str) -> Optional[Instance]:
        """Get assigned instance for a worker"""
        if worker_id in self.worker_to_instance:
            instance_id = self.worker_to_instance[worker_id]
            return self.instances.get(instance_id)
        return None
        
    def check_health(self) -> List[str]:
        """Check for workers that haven't sent heartbeat"""
        now = datetime.utcnow()
        unhealthy = []
        for worker_id, worker in self.workers.items():
            time_since_heartbeat = (now - worker.last_heartbeat).total_seconds()
            if time_since_heartbeat > HEARTBEAT_TIMEOUT:
                unhealthy.append(worker_id)
                logger.warning(f"Worker {worker_id} is unhealthy (no heartbeat for {time_since_heartbeat}s)")
        return unhealthy
        
    def get_websocket_id(self, worker_id: str) -> Optional[str]:
        """Get WebSocket connection ID for a worker"""
        return self.worker_to_ws.get(worker_id)