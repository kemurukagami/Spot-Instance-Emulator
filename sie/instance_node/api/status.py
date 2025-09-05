from fastapi import APIRouter
from typing import Dict, Any, Optional
from datetime import datetime
from sie.common.constants import InstanceState

router = APIRouter(prefix="/instance", tags=["instance"])

class InstanceStatus:
    instance_id: str = None
    instance_type: str = None
    state: InstanceState = InstanceState.PENDING
    hardware: dict = {}
    interruption_time: Optional[datetime] = None
    
status = InstanceStatus()

@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """Get current instance status"""
    return {
        "instance_id": status.instance_id,
        "instance_type": status.instance_type,
        "state": status.state,
        "hardware": status.hardware
    }

@router.get("/metadata")
async def get_metadata() -> Dict[str, Any]:
    """EC2-like metadata service"""
    return {
        "instance-id": status.instance_id,
        "instance-type": status.instance_type,
        "local-hostname": f"instance-{status.instance_id}",
        "local-ipv4": "10.0.0.1",  # Simulated
        "public-hostname": f"ec2-instance-{status.instance_id}.compute-1.amazonaws.com",
        "public-ipv4": "54.0.0.1"  # Simulated
    }

@router.get("/termination-time")
async def get_termination_time() -> Dict[str, Any]:
    """Get scheduled termination time"""
    if status.interruption_time:
        return {
            "termination_time": status.interruption_time.isoformat(),
            "time_remaining": (status.interruption_time - datetime.utcnow()).total_seconds()
        }
    return {"termination_time": None, "time_remaining": None}