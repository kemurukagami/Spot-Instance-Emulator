from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel
from sie.head_node.core import PoolManager
from sie.head_node.api.websocket import ConnectionManager

router = APIRouter(prefix="/admin", tags=["admin"])

class InterruptRequest(BaseModel):
    instance_id: str
    warning_time: int = 120

class PoolManager_ConnectionManager:
    pool_manager: PoolManager = None
    connection_manager: ConnectionManager = None

managers = PoolManager_ConnectionManager()

@router.get("/instances")
async def get_instances() -> List[Dict[str, Any]]:
    """Get all registered instances"""
    instances = managers.pool_manager.get_all_instances()
    return [
        {
            "instance_id": inst.instance_id,
            "instance_type": inst.instance_type,
            "state": inst.state,
            "hardware": inst.hardware,
            "registered_at": inst.registered_at.isoformat(),
            "last_heartbeat": inst.last_heartbeat.isoformat()
        }
        for inst in instances
    ]

@router.get("/instances/{instance_id}")
async def get_instance(instance_id: str) -> Dict[str, Any]:
    """Get specific instance details"""
    instance = managers.pool_manager.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    return {
        "instance_id": instance.instance_id,
        "instance_type": instance.instance_type,
        "state": instance.state,
        "hardware": instance.hardware,
        "registered_at": instance.registered_at.isoformat(),
        "last_heartbeat": instance.last_heartbeat.isoformat(),
        "interruption_time": instance.interruption_time.isoformat() if instance.interruption_time else None
    }

@router.post("/interrupt")
async def trigger_interruption(request: InterruptRequest) -> Dict[str, str]:
    """Manually trigger instance interruption"""
    success = await managers.connection_manager.trigger_interruption(
        request.instance_id, 
        request.warning_time
    )
    if not success:
        raise HTTPException(status_code=404, detail="Instance not found")
    return {
        "status": "success",
        "message": f"Interruption triggered for instance {request.instance_id}"
    }

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Check pool health"""
    unhealthy = managers.pool_manager.check_health()
    total = len(managers.pool_manager.get_all_instances())
    return {
        "total_instances": total,
        "unhealthy_instances": unhealthy,
        "healthy_instances": total - len(unhealthy)
    }