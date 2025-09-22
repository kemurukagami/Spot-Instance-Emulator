from typing import Dict, Optional, List
import uuid
import secrets
import logging
from datetime import datetime
from sie.head_node.models.user import User, InstanceAssignment, SSHAccessInfo
from sie.head_node.models.instance import WorkerConnection, Instance

logger = logging.getLogger(__name__)

class UserManager:
    def __init__(self):
        # In-memory storage (in production, use a proper database)
        self.users: Dict[str, User] = {}  # username -> User
        self.api_tokens: Dict[str, str] = {}  # api_token -> username
        self.assignments: Dict[str, InstanceAssignment] = {}  # assignment_id -> InstanceAssignment
        self.user_instances: Dict[str, List[str]] = {}  # username -> [assignment_ids]
        
    def register_user(self, username: str, ssh_public_key: str) -> User:
        """Register a new user with SSH public key"""
        if username in self.users:
            raise ValueError(f"Username '{username}' already exists")
        
        # Generate API token
        api_token = self._generate_api_token()
        
        # Create user
        user = User(
            username=username,
            ssh_public_key=ssh_public_key,
            api_token=api_token
        )
        
        # Store user
        self.users[username] = user
        self.api_tokens[api_token] = username
        self.user_instances[username] = []
        
        logger.info(f"Registered new user: {username}")
        return user
    
    def get_user(self, username: str) -> Optional[User]:
        """Get user by username"""
        return self.users.get(username)
    
    def get_user_by_token(self, api_token: str) -> Optional[User]:
        """Get user by API token"""
        username = self.api_tokens.get(api_token)
        if username:
            return self.users.get(username)
        return None
    
    def authenticate_token(self, api_token: str) -> Optional[str]:
        """Authenticate API token and return username"""
        username = self.api_tokens.get(api_token)
        if username and username in self.users:
            # Update last active time
            self.users[username].last_active = datetime.utcnow()
            return username
        return None
    
    def refresh_token(self, username: str) -> str:
        """Refresh user's API token"""
        if username not in self.users:
            raise ValueError(f"User '{username}' not found")
        
        user = self.users[username]
        
        # Remove old token
        if user.api_token in self.api_tokens:
            del self.api_tokens[user.api_token]
        
        # Generate new token
        new_token = self._generate_api_token()
        user.api_token = new_token
        self.api_tokens[new_token] = username
        
        logger.info(f"Refreshed API token for user: {username}")
        return new_token
    
    def assign_instance(self, username: str, instance_id: str, worker_id: str, 
                       worker: WorkerConnection) -> InstanceAssignment:
        """Assign an instance to a user"""
        user = self.users.get(username)
        if not user:
            raise ValueError(f"User '{username}' not found")
        
        if not user.is_active:
            raise ValueError(f"User '{username}' is not active")
        
        # Check instance limit
        current_instances = len(self.user_instances.get(username, []))
        if current_instances >= user.instance_limit:
            raise ValueError(f"User '{username}' has reached instance limit ({user.instance_limit})")
        
        # Generate assignment ID
        assignment_id = f"assign-{uuid.uuid4().hex[:12]}"
        
        # Create SSH access info
        ssh_access = self._create_ssh_access_info(username, instance_id, worker_id, worker)
        
        # Create assignment
        assignment = InstanceAssignment(
            assignment_id=assignment_id,
            instance_id=instance_id,
            username=username,
            ssh_access=ssh_access.dict(),
            worker_id=worker_id
        )
        
        # Store assignment
        self.assignments[assignment_id] = assignment
        if username not in self.user_instances:
            self.user_instances[username] = []
        self.user_instances[username].append(assignment_id)
        
        logger.info(f"Assigned instance {instance_id} to user {username} (assignment: {assignment_id})")
        return assignment
    
    def unassign_instance(self, assignment_id: str) -> bool:
        """Unassign an instance from a user"""
        assignment = self.assignments.get(assignment_id)
        if not assignment:
            return False
        
        username = assignment.username
        assignment.status = "terminated"
        
        # Remove from user's instances
        if username in self.user_instances:
            if assignment_id in self.user_instances[username]:
                self.user_instances[username].remove(assignment_id)
        
        logger.info(f"Unassigned instance {assignment.instance_id} from user {username}")
        return True
    
    def get_user_instances(self, username: str) -> List[InstanceAssignment]:
        """Get all instances assigned to a user"""
        if username not in self.user_instances:
            return []
        
        assignments = []
        for assignment_id in self.user_instances[username]:
            assignment = self.assignments.get(assignment_id)
            if assignment and assignment.status == "active":
                assignments.append(assignment)
        
        return assignments
    
    def get_assignment(self, assignment_id: str) -> Optional[InstanceAssignment]:
        """Get assignment by ID"""
        return self.assignments.get(assignment_id)
    
    def get_assignment_by_instance(self, instance_id: str) -> Optional[InstanceAssignment]:
        """Get assignment by instance ID"""
        for assignment in self.assignments.values():
            if assignment.instance_id == instance_id and assignment.status == "active":
                return assignment
        return None
    
    def list_users(self) -> List[User]:
        """List all users"""
        return list(self.users.values())
    
    def _generate_api_token(self) -> str:
        """Generate a secure API token"""
        return f"sie-{secrets.token_urlsafe(32)}"
    
    def _create_ssh_access_info(self, username: str, instance_id: str, worker_id: str, 
                               worker: WorkerConnection) -> SSHAccessInfo:
        """Create SSH access information"""
        # We need to get the actual worker's IP address
        # For now, we'll use localhost if it's a local connection,
        # but in a real deployment, you'd get the worker's IP from:
        # 1. The WebSocket connection remote address
        # 2. Worker registration metadata
        # 3. A separate network discovery service
        
        # TODO: This should be improved to get actual worker IP
        # For multi-machine deployments, this needs to be the worker's real IP
        ssh_host = self._get_worker_ip_address(worker_id, worker)
        
        # CRITICAL SECURITY: Ensure we use the system username (with spot- prefix)
        system_username = f"spot-{username}" if not username.startswith('spot-') else username
        
        return SSHAccessInfo(
            ssh_user=system_username,
            ssh_host=ssh_host,
            ssh_port=22,
            ssh_command=f"ssh {system_username}@{ssh_host}",
            connection_test=f"ssh {system_username}@{ssh_host} 'echo connected'",
            instance_id=instance_id,
            worker_id=worker_id
        )
    
    def _get_worker_ip_address(self, worker_id: str, worker: WorkerConnection) -> str:
        """Get the IP address for SSH access to the worker"""
        # Method 1: Use the worker IP captured from WebSocket connection
        if worker.worker_ip and worker.worker_ip != "unknown":
            # Filter out localhost-like addresses for remote deployment guidance
            if worker.worker_ip in ["127.0.0.1", "::1"]:
                logger.info(f"Worker {worker_id} connected from localhost ({worker.worker_ip})")
                return "localhost"
            else:
                logger.info(f"Using worker IP {worker.worker_ip} for SSH access")
                return worker.worker_ip
        
        # Method 2: Try to resolve hostname from worker_id
        if "worker-" in worker_id:
            # Extract hostname from worker_id (format: worker-hostname-hash)
            parts = worker_id.split("-")
            if len(parts) >= 2:
                hostname = parts[1]
                try:
                    import socket
                    # Try to resolve hostname to IP
                    ip = socket.gethostbyname(hostname)
                    logger.info(f"Resolved worker hostname {hostname} to IP {ip}")
                    return ip
                except socket.gaierror:
                    logger.warning(f"Could not resolve hostname {hostname}")
        
        # Method 3: Fallback to localhost for local testing
        logger.warning("Could not determine worker IP - using localhost. For multi-machine deployment, ensure workers connect from their external IPs")
        return "localhost"