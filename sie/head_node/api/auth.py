from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Dict, Any
from pydantic import BaseModel
from sie.head_node.core.user_manager import UserManager
from sie.head_node.models.user import User, InstanceAssignment
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()

# Global user manager (will be injected by main app)
user_manager: UserManager = None

class RegisterRequest(BaseModel):
    username: str
    ssh_public_key: str

class RefreshTokenRequest(BaseModel):
    username: str

class RequestInstanceRequest(BaseModel):
    instance_type: str = "t2.micro"

class RegisterResponse(BaseModel):
    username: str
    api_token: str
    message: str

class UserProfileResponse(BaseModel):
    username: str
    created_at: str
    last_active: str
    instance_limit: int
    current_instances: int
    is_active: bool

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Dependency to get current authenticated user"""
    if not user_manager:
        raise HTTPException(status_code=500, detail="User manager not initialized")
    
    username = user_manager.authenticate_token(credentials.credentials)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username

@router.post("/register", response_model=RegisterResponse)
async def register_user(request: RegisterRequest) -> RegisterResponse:
    """Register a new user with SSH public key"""
    if not user_manager:
        raise HTTPException(status_code=500, detail="User manager not initialized")
    
    try:
        user = user_manager.register_user(request.username, request.ssh_public_key)
        return RegisterResponse(
            username=user.username,
            api_token=user.api_token,
            message=f"User '{user.username}' registered successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")

@router.post("/token/refresh")
async def refresh_token(request: RefreshTokenRequest) -> Dict[str, str]:
    """Refresh user's API token"""
    if not user_manager:
        raise HTTPException(status_code=500, detail="User manager not initialized")
    
    try:
        new_token = user_manager.refresh_token(request.username)
        return {
            "api_token": new_token,
            "message": f"Token refreshed for user '{request.username}'"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(status_code=500, detail="Token refresh failed")

@router.get("/user/profile", response_model=UserProfileResponse)
async def get_user_profile(current_user: str = Depends(get_current_user)) -> UserProfileResponse:
    """Get current user's profile"""
    user = user_manager.get_user(current_user)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    current_instances = len(user_manager.get_user_instances(current_user))
    
    return UserProfileResponse(
        username=user.username,
        created_at=user.created_at.isoformat(),
        last_active=user.last_active.isoformat(),
        instance_limit=user.instance_limit,
        current_instances=current_instances,
        is_active=user.is_active
    )

@router.get("/test")
async def test_auth(current_user: str = Depends(get_current_user)) -> Dict[str, str]:
    """Test endpoint to verify authentication"""
    return {
        "message": f"Hello {current_user}! Authentication successful.",
        "user": current_user
    }