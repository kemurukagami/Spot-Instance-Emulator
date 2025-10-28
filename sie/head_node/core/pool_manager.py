from typing import Dict, Optional, List
from datetime import datetime, timedelta
import asyncio
import uuid
import random
import secrets
import string
from sie.head_node.core.instance import Instance, WorkerConnection
from sie.head_node.core.trace import TraceSimulator, AvailableSpotInstance
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

        # Trace-based spot instance simulation
        self.trace_simulator: Optional[TraceSimulator] = None
        self.spot_instance_to_worker: Dict[str, str] = {}  # spot_instance_id -> worker_id

        # Docker container management
        self.port_allocations: Dict[str, int] = {}  # worker_id -> next_available_port
        self.BASE_SSH_PORT = 10000  # Start SSH ports from 10000
        
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

    # Trace-based spot instance management
    def set_trace_simulator(self, trace_simulator: TraceSimulator) -> None:
        """Set the trace simulator for spot instance management"""
        self.trace_simulator = trace_simulator
        logger.info("Trace simulator enabled for spot instance management")

    def add_spot_instance(self, spot_instance_id: str, instance_type: str) -> None:
        """Add a new spot instance from trace (becomes available for assignment)"""
        if self.trace_simulator is None:
            logger.warning("Cannot add spot instance: trace simulator not enabled")
            return

        spot_instance = AvailableSpotInstance(
            spot_instance_id=spot_instance_id,
            instance_type=instance_type
        )
        self.trace_simulator.available_spot_instances[spot_instance_id] = spot_instance
        logger.info(f"Added spot instance {spot_instance_id} ({instance_type}) to available pool")

    def remove_spot_instance(self, spot_instance_id: str) -> Optional[str]:
        """
        Remove spot instance from trace (becomes unavailable, auto-unassign if needed)

        Returns:
            worker_id that was unassigned, or None if instance wasn't assigned
        """
        if self.trace_simulator is None:
            logger.warning("Cannot remove spot instance: trace simulator not enabled")
            return None

        if spot_instance_id not in self.trace_simulator.available_spot_instances:
            logger.warning(f"Cannot remove spot instance {spot_instance_id}: not found")
            return None

        spot_instance = self.trace_simulator.available_spot_instances[spot_instance_id]
        unassigned_worker = None

        # If spot instance is assigned to a worker, unassign it
        if spot_instance.is_assigned:
            worker_id = spot_instance.assigned_worker_id
            self._unassign_spot_instance_from_worker(spot_instance_id, worker_id)
            unassigned_worker = worker_id
            logger.info(f"Auto-unassigned worker {worker_id} due to spot instance {spot_instance_id} removal")

        # Remove from available pool
        del self.trace_simulator.available_spot_instances[spot_instance_id]
        logger.info(f"Removed spot instance {spot_instance_id} from available pool")

        return unassigned_worker

    def assign_spot_instance(self, worker_id: str, instance_type: Optional[str] = None, spot_instance_id: Optional[str] = None) -> Optional[str]:
        """
        Assign an available spot instance to a worker

        Args:
            worker_id: ID of the worker to assign to
            instance_type: Preferred instance type (if None, assigns any available)
            spot_instance_id: Specific spot instance ID to assign (for testing, e.g., "node1")

        Returns:
            The assigned spot instance ID, or None if assignment failed
        """
        if self.trace_simulator is None:
            # Fall back to legacy assignment if no trace simulator
            return self.assign_instance(worker_id, instance_type or "unknown")

        if worker_id not in self.workers:
            logger.error(f"Cannot assign spot instance: worker {worker_id} not found")
            return None

        worker = self.workers[worker_id]
        if worker.connection_state != ConnectionState.UNASSIGNED:
            logger.error(f"Cannot assign spot instance: worker {worker_id} is not unassigned (state: {worker.connection_state})")
            return None

        # If specific spot_instance_id is provided, assign that one
        if spot_instance_id:
            spot_instance = self.trace_simulator.available_spot_instances.get(spot_instance_id)
            if not spot_instance:
                logger.error(f"Cannot assign spot instance: {spot_instance_id} not found in available instances")
                return None
            if spot_instance.is_assigned:
                logger.error(f"Cannot assign spot instance: {spot_instance_id} is already assigned to worker {spot_instance.assigned_worker_id}")
                return None

            # Check if it has sufficient lifetime
            MIN_LIFETIME_MS = 120000  # 2 minutes in simulation time
            filtered = self._filter_by_remaining_lifetime([spot_instance], MIN_LIFETIME_MS)
            if not filtered:
                logger.error(f"Cannot assign spot instance: {spot_instance_id} has less than {MIN_LIFETIME_MS/1000}s remaining")
                return None

            # Use the specified spot instance
            spot_instance = filtered[0]
        else:
            # Find available spot instance
            available_spots = self.trace_simulator.get_unassigned_spot_instances()
            if instance_type:
                available_spots = [s for s in available_spots if s.instance_type == instance_type]

            # Filter out instances with less than 2 minutes remaining
            MIN_LIFETIME_MS = 120000  # 2 minutes in simulation time
            available_spots = self._filter_by_remaining_lifetime(available_spots, MIN_LIFETIME_MS)

            if not available_spots:
                logger.warning(f"No available spot instances with sufficient lifetime (requested type: {instance_type}, min lifetime: {MIN_LIFETIME_MS/1000}s)")
                return None

            # Randomly assign one of the available spot instances
            spot_instance = random.choice(available_spots)
        spot_instance.assigned_worker_id = worker_id
        self.spot_instance_to_worker[spot_instance.spot_instance_id] = worker_id

        # Calculate remaining lifetime for logging
        remaining_lifetime_str = "unknown"
        if self.trace_simulator and self.trace_simulator.events:
            current_time = self.trace_simulator.current_time_ms
            for event in self.trace_simulator.events:
                if (event.node_id == spot_instance.spot_instance_id and
                    event.action.value == "remove" and
                    event.timestamp_ms > current_time):
                    remaining_sim = (event.timestamp_ms - current_time) / 1000
                    remaining_real = remaining_sim / self.trace_simulator.simulation_speed
                    remaining_lifetime_str = f"{remaining_sim:.1f}s sim ({remaining_real:.1f}s real)"
                    break

        # Create traditional instance record for backward compatibility
        instance_id = f"i-{uuid.uuid4().hex[:8]}"
        instance = Instance(
            instance_id=instance_id,
            instance_type=spot_instance.instance_type,
            worker_id=worker_id,
            state=InstanceState.RUNNING
        )

        # Update tracking
        self.instances[instance_id] = instance
        self.worker_to_instance[worker_id] = instance_id
        worker.connection_state = ConnectionState.ASSIGNED

        logger.info(f"Assigned spot instance {spot_instance.spot_instance_id} ({spot_instance.instance_type}) to worker {worker_id} as instance {instance_id} (lifetime remaining: {remaining_lifetime_str})")
        return spot_instance.spot_instance_id

    def _filter_by_remaining_lifetime(self, spot_instances: List[AvailableSpotInstance], min_lifetime_ms: int) -> List[AvailableSpotInstance]:
        """
        Filter spot instances to only include those with sufficient remaining lifetime.

        Args:
            spot_instances: List of spot instances to filter
            min_lifetime_ms: Minimum required lifetime in milliseconds (simulation time)

        Returns:
            List of spot instances with at least min_lifetime_ms remaining
        """
        if not self.trace_simulator or not self.trace_simulator.events:
            return spot_instances

        current_time = self.trace_simulator.current_time_ms
        filtered = []

        for spot in spot_instances:
            # Find the next REMOVE event for this spot instance
            removal_time = None
            for event in self.trace_simulator.events:
                if (event.node_id == spot.spot_instance_id and
                    event.action.value == "remove" and
                    event.timestamp_ms > current_time):
                    removal_time = event.timestamp_ms
                    break

            # If no removal event found, instance lives forever (keep it)
            if removal_time is None:
                filtered.append(spot)
                logger.debug(f"Spot instance {spot.spot_instance_id} has no scheduled removal (keeping)")
                continue

            # Check if instance has sufficient lifetime remaining
            remaining_lifetime = removal_time - current_time
            if remaining_lifetime >= min_lifetime_ms:
                filtered.append(spot)
                logger.debug(f"Spot instance {spot.spot_instance_id} has {remaining_lifetime/1000:.1f}s remaining (keeping)")
            else:
                logger.debug(f"Spot instance {spot.spot_instance_id} only has {remaining_lifetime/1000:.1f}s remaining (filtering out, min required: {min_lifetime_ms/1000:.1f}s)")

        return filtered

    def request_spot_instance_for_user(self, instance_type: str) -> Optional[Dict[str, str]]:
        """
        Request a spot instance (user-friendly API) - auto-selects an available worker and creates Docker container

        Args:
            instance_type: Desired instance type (e.g., "p3.xlarge")

        Returns:
            Dict with instance_id, spot_instance_id, worker_id, ip_address, ssh_port, ssh_username, ssh_password, and container_name, or None if failed
        """
        if self.trace_simulator is None:
            logger.error("Cannot request spot instance: trace simulation not enabled")
            return None

        # Find an unassigned worker matching the instance type
        unassigned_workers = self.get_unassigned_workers()
        matching_workers = [w for w in unassigned_workers if w.instance_type == instance_type]

        if not matching_workers:
            logger.warning(f"No unassigned workers with instance type {instance_type}")
            return None

        # Pick first matching worker (could randomize if desired)
        worker = matching_workers[0]
        worker_id = worker.worker_id

        # Assign a spot instance to this worker
        spot_instance_id = self.assign_spot_instance(worker_id, instance_type)
        if not spot_instance_id:
            logger.error(f"Failed to assign spot instance to worker {worker_id}")
            return None

        # Get the instance that was created (user defaults to "isaacy" in Instance model)
        instance = self.get_instance_for_worker(worker_id)
        if not instance:
            logger.error(f"Instance not found after assignment for worker {worker_id}")
            return None

        # Generate Docker container configuration
        container_name = f"spot-{instance.instance_id}"
        ssh_port = self._allocate_ssh_port(worker_id)
        ssh_password = self._generate_secure_password()
        base_image = self._get_base_image(instance_type)

        # Update instance with container info
        instance.container_name = container_name
        instance.ssh_port = ssh_port
        instance.ssh_password = ssh_password

        logger.info(f"Allocated {instance_type} spot instance {spot_instance_id} to user {instance.user} at {worker.ip_address}:{ssh_port} (container: {container_name})")

        return {
            "instance_id": instance.instance_id,
            "spot_instance_id": spot_instance_id,
            "worker_id": worker_id,
            "ip_address": worker.ip_address,
            "ssh_port": ssh_port,
            "ssh_username": "root",
            "ssh_password": ssh_password,
            "container_name": container_name,
            "base_image": base_image
        }

    def _unassign_spot_instance_from_worker(self, spot_instance_id: str, worker_id: str) -> bool:
        """Internal method to unassign a spot instance from a worker"""
        if worker_id not in self.workers:
            logger.error(f"Cannot unassign: worker {worker_id} not found")
            return False

        # Find and remove instance record
        instance_id = self.worker_to_instance.get(worker_id)
        if instance_id and instance_id in self.instances:
            del self.instances[instance_id]

        # Clean up tracking
        if worker_id in self.worker_to_instance:
            del self.worker_to_instance[worker_id]
        if spot_instance_id in self.spot_instance_to_worker:
            del self.spot_instance_to_worker[spot_instance_id]

        # Update spot instance state
        if self.trace_simulator and spot_instance_id in self.trace_simulator.available_spot_instances:
            self.trace_simulator.available_spot_instances[spot_instance_id].assigned_worker_id = None

        # Return worker to unassigned state
        self.workers[worker_id].connection_state = ConnectionState.UNASSIGNED

        return True

    def get_available_spot_instances(self) -> List[AvailableSpotInstance]:
        """Get all unassigned spot instances"""
        if self.trace_simulator is None:
            return []
        return self.trace_simulator.get_unassigned_spot_instances()

    def get_assigned_spot_instances(self) -> List[AvailableSpotInstance]:
        """Get all assigned spot instances"""
        if self.trace_simulator is None:
            return []
        return self.trace_simulator.get_assigned_spot_instances()

    def get_spot_instance_for_worker(self, worker_id: str) -> Optional[AvailableSpotInstance]:
        """Get spot instance assigned to a specific worker"""
        if self.trace_simulator is None:
            return None
        return self.trace_simulator.get_spot_instance_by_worker(worker_id)

    # Docker container helper methods
    def _allocate_ssh_port(self, worker_id: str) -> int:
        """Allocate next available SSH port for a worker"""
        if worker_id not in self.port_allocations:
            self.port_allocations[worker_id] = self.BASE_SSH_PORT

        port = self.port_allocations[worker_id]
        self.port_allocations[worker_id] += 1
        return port

    def _release_ssh_port(self, worker_id: str, port: int):
        """Release an SSH port (for future optimization)"""
        # For now, we just increment and don't reuse
        # Could implement a free list for port reuse
        pass

    @staticmethod
    def _generate_secure_password(length: int = 16) -> str:
        """Generate a secure random password"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def _get_base_image(instance_type: str) -> str:
        """Get Docker base image (always minimal base - users install their own CUDA/software)"""
        # All instance types use the same minimal base image
        # Users can install their own CUDA, Python, frameworks, etc.
        return "spot-base:latest"