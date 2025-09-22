# SSH-Based User Authentication Guide

This guide explains how to use the SSH-based user authentication system in the Spot Instance Emulator.

## Overview

The SSH authentication system allows users to:
1. Register with their SSH public key
2. Request spot instances using API tokens
3. Get direct SSH access to assigned instances
4. Have temporary system users created/deleted automatically

## Quick Start

### 1. Generate SSH Key Pair (if you don't have one)
```bash
ssh-keygen -t rsa -b 2048 -f ~/.ssh/spot_key
```

### 2. Start the System
```bash
# Terminal 1: Start head node
python run_head.py

# Terminal 2: Start worker node  
python run_instance.py --port 8001
```

### 3. Register User
```bash
# Read your public key
PUBLIC_KEY=$(cat ~/.ssh/spot_key.pub)

# Register with the system
curl -X POST http://158.130.4.156:8000/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"myuser\", \"ssh_public_key\": \"$PUBLIC_KEY\"}"
```

Response:
```json
{
  "username": "myuser",
  "api_token": "sie-abc123...",
  "message": "User 'myuser' registered successfully"
}
```

### 4. Request Instance
```bash
# Use the API token from registration
curl -X POST http://158.130.4.156:8000/instances/request \
  -H "Authorization: Bearer sie-abc123..." \
  -H "Content-Type: application/json" \
  -d '{"instance_type": "t3.medium"}'
```

Response:
```json
{
  "assignment_id": "assign-xyz789",
  "instance_id": "i-abc12345",
  "instance_type": "t3.medium",
  "worker_id": "worker-hostname-hash",
  "status": "active",
  "ssh_access": {
    "ssh_user": "myuser",
    "ssh_host": "localhost",
    "ssh_port": 22,
    "ssh_command": "ssh myuser@localhost"
  }
}
```

### 5. SSH to Instance
```bash
# Wait a moment for user creation to complete
sleep 3

# SSH to your instance (use the ssh_host from the response)
# For local testing: ssh -i ~/.ssh/spot_key myuser@localhost
# For remote workers: ssh -i ~/.ssh/spot_key myuser@<worker_ip>
ssh -i ~/.ssh/spot_key myuser@<ssh_host_from_response>

# You now have full access to the hardware!
nvidia-smi  # Check GPUs
lscpu       # Check CPU
df -h       # Check storage
```

### 6. List Your Instances
```bash
curl -X GET http://158.130.4.156:8000/instances/mine \
  -H "Authorization: Bearer sie-abc123..."
```

### 7. Terminate Instance
```bash
curl -X DELETE http://158.130.4.156:8000/instances/assign-xyz789 \
  -H "Authorization: Bearer sie-abc123..."
```

## API Endpoints

### Authentication
- `POST /auth/register` - Register with SSH public key
- `POST /auth/token/refresh` - Refresh API token  
- `GET /auth/user/profile` - Get user profile
- `GET /auth/test` - Test authentication

### Instance Management
- `POST /instances/request` - Request spot instance
- `GET /instances/mine` - List user's instances
- `DELETE /instances/{assignment_id}` - Terminate instance

### Admin (for system administrators)
- `GET /admin/workers` - List all workers
- `GET /admin/workers/unassigned` - List available workers
- `GET /admin/instances` - List all instances
- `POST /admin/assign-instance` - Manually assign instance
- `POST /admin/interrupt` - Trigger interruption

## Features

### Full Hardware Access
- **GPUs**: Direct CUDA access with nvidia-smi
- **CPUs**: Full CPU access without virtualization overhead  
- **Storage**: Direct disk access
- **Network**: Full network interface access

### Security
- SSH key-only authentication (no passwords)
- Temporary system users (created/deleted per assignment)
- User isolation with spot-users group
- Resource limits enforced
- Process cleanup on termination

### Machine Reusability
- Same physical machine serves multiple users over time
- Workers stay connected between assignments
- Instant instance assignment to available workers
- Clean user environment for each assignment

## System Requirements

### Head Node
- Python 3.8+
- FastAPI and dependencies
- Network connectivity to workers

### Worker Nodes  
- Python 3.8+
- sudo permissions for user management
- SSH server running
- Hardware to be shared (GPUs, etc.)

### User Machine
- SSH client
- SSH key pair
- curl or HTTP client for API calls

## Troubleshooting

### SSH Connection Fails
1. Check if user was created: `id myuser`
2. Check SSH key: `cat /home/myuser/.ssh/authorized_keys`
3. Check SSH logs: `sudo tail -f /var/log/auth.log`
4. Verify worker is connected: `curl http://158.130.4.156:8000/admin/workers`
5. Check worker IP detection: Look for `worker_ip` in the admin/workers response
6. For remote workers: Ensure the worker connects from its external IP, not localhost

### User Creation Fails
1. Check worker logs for sudo permission errors
2. Ensure spot-users group exists: `getent group spot-users`
3. Check disk space for home directory creation
4. Verify WebSocket connection between head and worker

### API Authentication Fails
1. Check API token is correct and not expired
2. Verify Authorization header format: `Bearer <token>`
3. Check user profile: `curl -H "Authorization: Bearer <token>" http://158.130.4.156:8000/auth/user/profile`

## Example Test Script

Run the complete test suite:
```bash
python test_ssh_auth.py
```

This will test the entire workflow from registration to SSH access to cleanup.

## Multi-Machine Deployment

### Worker IP Detection
The system automatically detects worker IP addresses for SSH access:

1. **Local Testing**: Workers connecting from localhost (127.0.0.1) get `ssh_host: "localhost"`
2. **Remote Workers**: Workers connecting from external IPs get their actual IP as `ssh_host`
3. **Hostname Resolution**: Falls back to resolving worker hostname if IP detection fails

### Remote Worker Setup
For workers on different machines:

```bash
# Worker machine connects to head node's external IP
python run_instance.py --head-node ws://158.130.4.156:8000/ws --port 8001
```

The head node will automatically detect the worker's IP and provide it in SSH access info.

### Checking Worker IPs
```bash
# Check detected worker IPs
curl http://158.130.4.156:8000/admin/workers | jq '.[] | {worker_id, worker_ip}'
```

## Architecture Benefits

1. **No Containerization**: Full hardware access without Docker overhead
2. **Dynamic Assignment**: Instances assigned to users on-demand
3. **Machine Reuse**: Same hardware serves multiple users over time  
4. **Automatic Cleanup**: Users and resources cleaned up automatically
5. **Secure Isolation**: SSH key authentication with user isolation
6. **Automatic IP Detection**: SSH host automatically determined from worker connection