from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
import re

class User(BaseModel):
    """User model for SSH key-based authentication"""
    username: str
    ssh_public_key: str
    api_token: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    instance_limit: int = 5
    is_active: bool = True
    
    @validator('username')
    def validate_username(cls, v):
        """Validate username follows Linux username conventions"""
        if not re.match(r'^[a-z][a-z0-9_-]*$', v):
            raise ValueError('Username must start with lowercase letter and contain only lowercase letters, numbers, hyphens, and underscores')
        if len(v) < 2 or len(v) > 32:
            raise ValueError('Username must be between 2 and 32 characters')
        return v
    
    @validator('ssh_public_key')
    def validate_ssh_key(cls, v):
        """Basic SSH public key validation"""
        if not v.strip():
            raise ValueError('SSH public key cannot be empty')
        
        # Check if it starts with a valid SSH key type
        valid_types = ['ssh-rsa', 'ssh-dss', 'ssh-ed25519', 'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521']
        if not any(v.strip().startswith(key_type) for key_type in valid_types):
            raise ValueError('SSH public key must start with a valid key type (ssh-rsa, ssh-ed25519, etc.)')
        
        # Basic format check (type + key + optional comment)
        parts = v.strip().split()
        if len(parts) < 2:
            raise ValueError('SSH public key must contain at least key type and key data')
        
        return v.strip()

class InstanceAssignment(BaseModel):
    """Instance assignment to user"""
    assignment_id: str
    instance_id: str
    username: str
    ssh_access: dict
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "active"  # active, terminating, terminated
    worker_id: str
    
class SSHAccessInfo(BaseModel):
    """SSH access information for user"""
    ssh_user: str
    ssh_host: str
    ssh_port: int = 22
    ssh_command: str
    connection_test: str
    instance_id: str
    worker_id: str