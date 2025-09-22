from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Dict, Any
from pydantic import BaseModel
from sie.head_node.api.auth import get_current_user, user_manager
from sie.head_node.core.pool_manager import PoolManager
from sie.head_node.api.websocket import ConnectionManager
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/instances", tags=["instances"])

# Global managers (will be injected by main app)
pool_manager: PoolManager = None
connection_manager: ConnectionManager = None

class RequestInstanceRequest(BaseModel):
    instance_type: str = "t2.micro"

class TerminateInstanceRequest(BaseModel):
    assignment_id: str

class InstanceResponse(BaseModel):
    assignment_id: str
    instance_id: str
    instance_type: str
    worker_id: str
    status: str
    ssh_access: Dict[str, Any]
    created_at: str

@router.post("/request")
async def request_instance(
    request: RequestInstanceRequest,
    current_user: str = Depends(get_current_user)
) -> InstanceResponse:
    """Request a spot instance with user authentication"""
    if not all([user_manager, pool_manager, connection_manager]):
        raise HTTPException(status_code=500, detail="Services not initialized")
    
    try:
        # Get an unassigned worker
        unassigned_workers = pool_manager.get_unassigned_workers()
        if not unassigned_workers:
            raise HTTPException(status_code=503, detail="No available workers")
        
        # Select the first available worker (could implement more sophisticated selection)
        worker = unassigned_workers[0]
        
        # Assign instance to worker
        instance_id = await connection_manager.assign_instance(worker.worker_id, request.instance_type)
        if not instance_id:
            raise HTTPException(status_code=500, detail="Failed to assign instance to worker")
        
        # Assign instance to user
        assignment = user_manager.assign_instance(
            current_user, 
            instance_id, 
            worker.worker_id, 
            worker
        )
        
        # Get user's SSH public key
        user = user_manager.get_user(current_user)
        if not user:
            raise HTTPException(status_code=500, detail="User not found")
        
        # CRITICAL SECURITY: Enforce spot- prefix for system user creation
        system_username = f"spot-{current_user}" if not current_user.startswith('spot-') else current_user
        
        # Send message to worker to create system user with SSH key
        await connection_manager.create_user_on_worker(
            worker.worker_id,
            system_username,
            user.ssh_public_key,
            assignment.assignment_id
        )
        
        logger.info(f"User {current_user} requested instance {instance_id}")
        
        return InstanceResponse(
            assignment_id=assignment.assignment_id,
            instance_id=assignment.instance_id,
            instance_type=request.instance_type,
            worker_id=assignment.worker_id,
            status=assignment.status,
            ssh_access=assignment.ssh_access,
            created_at=assignment.created_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Instance request error: {e}")
        raise HTTPException(status_code=500, detail="Instance request failed")

@router.get("/mine")
async def get_my_instances(current_user: str = Depends(get_current_user)) -> List[InstanceResponse]:
    """Get user's current instances"""
    if not user_manager:
        raise HTTPException(status_code=500, detail="User manager not initialized")
    
    assignments = user_manager.get_user_instances(current_user)
    
    instances = []
    for assignment in assignments:
        # Get instance type from pool manager
        instance = pool_manager.get_instance(assignment.instance_id) if pool_manager else None
        instance_type = instance.instance_type if instance else "unknown"
        
        instances.append(InstanceResponse(
            assignment_id=assignment.assignment_id,
            instance_id=assignment.instance_id,
            instance_type=instance_type,
            worker_id=assignment.worker_id,
            status=assignment.status,
            ssh_access=assignment.ssh_access,
            created_at=assignment.created_at.isoformat()
        ))
    
    return instances

@router.delete("/{assignment_id}")
async def terminate_instance(
    assignment_id: str,
    current_user: str = Depends(get_current_user)
) -> Dict[str, str]:
    """Terminate user's instance"""
    if not all([user_manager, connection_manager]):
        raise HTTPException(status_code=500, detail="Services not initialized")
    
    # Get assignment and verify ownership
    assignment = user_manager.get_assignment(assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    if assignment.username != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to terminate this instance")
    
    try:
        # Trigger interruption with immediate termination
        success = await connection_manager.trigger_interruption(assignment.instance_id, warning_time=5)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to trigger instance termination")
        
        # Send message to worker to delete system user
        await connection_manager.delete_user_on_worker(
            assignment.worker_id,
            assignment.username,
            assignment_id
        )
        
        # Unassign from user
        user_manager.unassign_instance(assignment_id)
        
        logger.info(f"User {current_user} terminated instance {assignment.instance_id}")
        
        return {
            "message": f"Instance {assignment.instance_id} termination initiated",
            "assignment_id": assignment_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Instance termination error: {e}")
        raise HTTPException(status_code=500, detail="Instance termination failed")