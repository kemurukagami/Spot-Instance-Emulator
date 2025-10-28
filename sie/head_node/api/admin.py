from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from sie.head_node.core import PoolManager
from sie.head_node.api.websocket import ConnectionManager

router = APIRouter(prefix="/admin", tags=["admin"])

class InterruptRequest(BaseModel):
    instance_id: str
    warning_time: int = 120

class AssignInstanceRequest(BaseModel):
    worker_id: str
    instance_type: str = "t2.micro"

class UnassignInstanceRequest(BaseModel):
    instance_id: str

class RequestSpotInstanceRequest(BaseModel):
    instance_type: str  # e.g., "p3.xlarge"

class Managers:
    pool_manager: PoolManager = None
    connection_manager: ConnectionManager = None
    simulation_controller: Optional[Any] = None  # Will be set from main.py

managers = Managers()

@router.get("/workers")
async def get_workers() -> List[Dict[str, Any]]:
    """Get all connected workers"""
    workers = managers.pool_manager.get_all_workers()
    return [
        {
            "worker_id": worker.worker_id,
            "connection_state": worker.connection_state.value,  # Explicitly get enum value
            "hardware": worker.hardware,
            "connected_at": worker.connected_at.isoformat(),
            "last_heartbeat": worker.last_heartbeat.isoformat(),
            "assigned_instance": managers.pool_manager.get_instance_for_worker(worker.worker_id).instance_id
                               if managers.pool_manager.get_instance_for_worker(worker.worker_id) else None
        }
        for worker in workers
    ]

@router.get("/instances")
async def get_instances() -> List[Dict[str, Any]]:
    """Get all assigned instances"""
    instances = managers.pool_manager.get_all_instances()
    return [
        {
            "instance_id": inst.instance_id,
            "instance_type": inst.instance_type,
            "worker_id": inst.worker_id,
            "state": inst.state.value,  # Explicitly get enum value
            "assigned_at": inst.assigned_at.isoformat(),
            "last_heartbeat": inst.last_heartbeat.isoformat(),
            "interruption_time": inst.interruption_time.isoformat() if inst.interruption_time else None
        }
        for inst in instances
    ]

@router.get("/workers/unassigned")
async def get_unassigned_workers() -> List[Dict[str, Any]]:
    """Get workers available for instance assignment"""
    workers = managers.pool_manager.get_unassigned_workers()
    return [
        {
            "worker_id": worker.worker_id,
            "hardware": worker.hardware,
            "connected_at": worker.connected_at.isoformat(),
            "last_heartbeat": worker.last_heartbeat.isoformat()
        }
        for worker in workers
    ]

@router.get("/instances/{instance_id}")
async def get_instance(instance_id: str) -> Dict[str, Any]:
    """Get specific instance details"""
    instance = managers.pool_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    # Get worker info too
    worker = managers.pool_manager.get_worker(instance.worker_id)

    return {
        "instance_id": instance.instance_id,
        "instance_type": instance.instance_type,
        "worker_id": instance.worker_id,
        "state": instance.state.value,  # Explicitly get enum value
        "assigned_at": instance.assigned_at.isoformat(),
        "last_heartbeat": instance.last_heartbeat.isoformat(),
        "interruption_time": instance.interruption_time.isoformat() if instance.interruption_time else None,
        "worker_hardware": worker.hardware if worker else None
    }

@router.post("/assign-instance")
async def assign_instance(request: AssignInstanceRequest) -> Dict[str, Any]:
    """Assign an instance ID to a worker"""
    instance_id = await managers.connection_manager.assign_instance(
        request.worker_id,
        request.instance_type
    )
    if not instance_id:
        raise HTTPException(status_code=400, detail="Failed to assign instance. Worker may not exist or not be unassigned.")
    
    return {
        "status": "success",
        "instance_id": instance_id,
        "worker_id": request.worker_id,
        "instance_type": request.instance_type,
        "message": f"Assigned instance {instance_id} to worker {request.worker_id}"
    }

@router.post("/unassign-instance")
async def unassign_instance(request: UnassignInstanceRequest) -> Dict[str, str]:
    """Unassign an instance and return worker to unassigned state"""
    success = await managers.connection_manager.unassign_instance(request.instance_id)
    if not success:
        raise HTTPException(status_code=404, detail="Instance not found")
    
    return {
        "status": "success",
        "message": f"Unassigned instance {request.instance_id}, worker returned to unassigned state"
    }

@router.post("/interrupt")
async def trigger_interruption(request: InterruptRequest) -> Dict[str, str]:
    """Manually trigger instance interruption (will auto-unassign after warning time)"""
    success = await managers.connection_manager.trigger_interruption(
        request.instance_id, 
        request.warning_time
    )
    if not success:
        raise HTTPException(status_code=404, detail="Instance not found")
    return {
        "status": "success",
        "message": f"Interruption triggered for instance {request.instance_id}. Will auto-unassign after {request.warning_time}s"
    }

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Check pool health"""
    unhealthy_workers = managers.pool_manager.check_health()
    total_workers = len(managers.pool_manager.get_all_workers())
    total_instances = len(managers.pool_manager.get_all_instances())
    unassigned_workers = len(managers.pool_manager.get_unassigned_workers())

    return {
        "total_workers": total_workers,
        "unhealthy_workers": unhealthy_workers,
        "healthy_workers": total_workers - len(unhealthy_workers),
        "total_instances": total_instances,
        "unassigned_workers": unassigned_workers,
        "assigned_workers": total_instances  # Same as instances since 1:1 mapping
    }

# Trace simulation endpoints
@router.get("/simulation/status")
async def get_simulation_status() -> Dict[str, Any]:
    """Get current simulation status"""
    if not managers.simulation_controller:
        return {"error": "Trace simulation not enabled"}

    return managers.simulation_controller.get_simulation_status()

@router.post("/simulation/pause")
async def pause_simulation() -> Dict[str, str]:
    """Pause trace simulation"""
    if not managers.simulation_controller:
        raise HTTPException(status_code=400, detail="Trace simulation not enabled")

    await managers.simulation_controller.pause_simulation()
    return {"status": "success", "message": "Simulation paused"}

@router.post("/simulation/resume")
async def resume_simulation() -> Dict[str, str]:
    """Resume trace simulation"""
    if not managers.simulation_controller:
        raise HTTPException(status_code=400, detail="Trace simulation not enabled")

    await managers.simulation_controller.resume_simulation()
    return {"status": "success", "message": "Simulation resumed"}

class SeekRequest(BaseModel):
    time_ms: int

@router.post("/simulation/seek")
async def seek_simulation(request: SeekRequest) -> Dict[str, str]:
    """Seek to specific time in trace"""
    if not managers.simulation_controller:
        raise HTTPException(status_code=400, detail="Trace simulation not enabled")

    await managers.simulation_controller.seek_to_time(request.time_ms)
    return {"status": "success", "message": f"Seeked to time {request.time_ms}ms"}

class SpeedRequest(BaseModel):
    speed: float

@router.post("/simulation/speed")
async def set_simulation_speed(request: SpeedRequest) -> Dict[str, str]:
    """Set simulation speed"""
    if not managers.simulation_controller:
        raise HTTPException(status_code=400, detail="Trace simulation not enabled")

    managers.simulation_controller.set_simulation_speed(request.speed)
    return {"status": "success", "message": f"Set simulation speed to {request.speed}x"}

@router.get("/spot-instances/available")
async def get_available_spot_instances() -> List[Dict[str, Any]]:
    """Get all available (unassigned) spot instances"""
    if not managers.simulation_controller:
        return []

    spot_instances = managers.pool_manager.get_available_spot_instances()
    return [
        {
            "spot_instance_id": spot.spot_instance_id,
            "instance_type": spot.instance_type,
            "available_since": spot.available_since.isoformat(),
            "is_assigned": spot.is_assigned
        }
        for spot in spot_instances
    ]

@router.get("/spot-instances/assigned")
async def get_assigned_spot_instances() -> List[Dict[str, Any]]:
    """Get all assigned spot instances"""
    if not managers.simulation_controller:
        return []

    spot_instances = managers.pool_manager.get_assigned_spot_instances()
    return [
        {
            "spot_instance_id": spot.spot_instance_id,
            "instance_type": spot.instance_type,
            "available_since": spot.available_since.isoformat(),
            "assigned_worker_id": spot.assigned_worker_id,
            "is_assigned": spot.is_assigned
        }
        for spot in spot_instances
    ]

@router.get("/trace-events/upcoming")
async def get_upcoming_trace_events() -> List[Dict[str, Any]]:
    """Get upcoming trace events"""
    if not managers.simulation_controller:
        return []

    events = managers.simulation_controller.get_upcoming_events(count=20)
    return [
        {
            "timestamp_ms": event.timestamp_ms,
            "action": event.action,
            "node_id": event.node_id
        }
        for event in events
    ]

class AssignSpotInstanceRequest(BaseModel):
    worker_id: str
    instance_type: Optional[str] = None
    spot_instance_id: Optional[str] = None  # For testing: specify exact spot instance (e.g., "node1")

@router.post("/assign-spot-instance")
async def assign_spot_instance(request: AssignSpotInstanceRequest) -> Dict[str, Any]:
    """Assign a spot instance to a worker (trace-based)"""
    if not managers.simulation_controller:
        # Fall back to regular assignment
        instance_id = await managers.connection_manager.assign_instance(
            request.worker_id,
            request.instance_type or "unknown"
        )
        if not instance_id:
            raise HTTPException(status_code=400, detail="Failed to assign instance")
        return {
            "status": "success",
            "instance_id": instance_id,
            "worker_id": request.worker_id,
            "message": f"Assigned regular instance {instance_id} to worker {request.worker_id}"
        }

    # Use connection_manager to send WebSocket message to worker
    spot_instance_id = await managers.connection_manager.assign_spot_instance(
        request.worker_id,
        request.instance_type,
        request.spot_instance_id
    )
    if not spot_instance_id:
        if request.spot_instance_id:
            raise HTTPException(status_code=400, detail=f"Spot instance {request.spot_instance_id} not available or already assigned")
        else:
            raise HTTPException(status_code=400, detail="No available spot instances matching criteria")

    return {
        "status": "success",
        "spot_instance_id": spot_instance_id,
        "worker_id": request.worker_id,
        "instance_type": request.instance_type,
        "message": f"Assigned spot instance {spot_instance_id} to worker {request.worker_id}"
    }

@router.post("/request-spot-instance")
async def request_spot_instance(request: RequestSpotInstanceRequest) -> Dict[str, Any]:
    """Request a spot instance (user-friendly API - auto-selects worker and creates Docker container)"""
    if not managers.simulation_controller:
        raise HTTPException(status_code=400, detail="Trace simulation not enabled")

    # Auto-select worker and assign spot instance (user defaults to "isaacy" in Instance metadata)
    result = await managers.connection_manager.request_spot_instance_for_user(
        instance_type=request.instance_type
    )

    if not result:
        raise HTTPException(status_code=400, detail=f"No available {request.instance_type} spot instances or workers")

    return {
        "status": "success",
        "instance_id": result["instance_id"],
        "spot_instance_id": result["spot_instance_id"],
        "ip_address": result["ip_address"],
        "ssh_port": result["ssh_port"],
        "ssh_username": result["ssh_username"],
        "ssh_password": result["ssh_password"],
        "instance_type": request.instance_type,
        "container_name": result["container_name"],
        "ssh_command": f"ssh -p {result['ssh_port']} {result['ssh_username']}@{result['ip_address']}",
        "message": f"Allocated {request.instance_type} spot instance container at {result['ip_address']}:{result['ssh_port']}"
    }