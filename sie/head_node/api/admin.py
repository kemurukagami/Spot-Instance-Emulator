from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
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

class PoolManager_ConnectionManager:
    pool_manager: PoolManager = None
    connection_manager: ConnectionManager = None

managers = PoolManager_ConnectionManager()

@router.get("/workers")
async def get_workers() -> List[Dict[str, Any]]:
    """Get all connected workers"""
    workers = managers.pool_manager.get_all_workers()
    return [
        {
            "worker_id": worker.worker_id,
            "connection_state": worker.connection_state,
            "worker_ip": worker.worker_ip,
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
            "state": inst.state,
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
            "worker_ip": worker.worker_ip,
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
        "state": instance.state,
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