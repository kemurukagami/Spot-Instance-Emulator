import os
import subprocess
import logging
from typing import Dict, Set
from pathlib import Path

# CRITICAL SECURITY: Base system users that must NEVER be deleted
BASE_PROTECTED_USERS = {
    'root', 'daemon', 'bin', 'sys', 'sync', 'games', 'man', 'lp', 'mail', 
    'news', 'uucp', 'proxy', 'www-data', 'backup', 'list', 'irc', 'gnats',
    'nobody', 'systemd-network', 'systemd-resolve', 'syslog', 'messagebus',
    'uuidd', 'dnsmasq', 'landscape', 'pollinate', 'sshd', 'ubuntu', 'admin',
    'ec2-user', 'centos', 'fedora', 'debian', 'pi', 'vagrant', 'docker',
    'postgres', 'mysql', 'redis', 'nginx', 'apache', 'jenkins', 'git'
}

# DYNAMIC: Users detected at startup - this will be populated with ALL existing system users
PROTECTED_USERS = set()

# Users with UID < 1000 are typically system users
MIN_DELETABLE_UID = 1000
MAX_DELETABLE_UID = 65533

logger = logging.getLogger(__name__)

class UserManager:
    """Manages temporary system users on instance nodes"""
    
    def __init__(self):
        self.active_users: Dict[str, str] = {}  # username -> assignment_id
        self.user_assignments: Dict[str, str] = {}  # assignment_id -> username
        self._system_users_captured = False
        
    async def _capture_existing_system_users(self):
        """CRITICAL SECURITY: Capture ALL existing users to protect them from deletion"""
        global PROTECTED_USERS
        
        if self._system_users_captured:
            return  # Already captured
        
        try:
            logger.info("SECURITY: Capturing existing system users for protection")
            
            # Start with base protected users
            existing_users = set(BASE_PROTECTED_USERS)
            
            # Method 1: Parse /etc/passwd to get ALL users
            try:
                with open('/etc/passwd', 'r') as f:
                    for line in f:
                        if line.strip() and not line.startswith('#'):
                            username = line.split(':')[0]
                            existing_users.add(username)
            except Exception as e:
                logger.error(f"Error reading /etc/passwd: {e}")
            
            # Method 2: Get users via getent passwd (handles LDAP/AD users too)
            try:
                result = subprocess.run(['getent', 'passwd'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if line.strip():
                            username = line.split(':')[0]
                            existing_users.add(username)
            except Exception as e:
                logger.warning(f"getent passwd failed: {e}")
            
            # Update global protected users list
            PROTECTED_USERS.clear()
            PROTECTED_USERS.update(existing_users)
            
            logger.critical(f"SECURITY: Protected {len(PROTECTED_USERS)} existing users from deletion")
            logger.info(f"SECURITY: Sample protected users: {list(sorted(PROTECTED_USERS))[:10]}...")
            
            self._system_users_captured = True
            
        except Exception as e:
            logger.critical(f"CRITICAL SECURITY ERROR: Failed to capture system users: {e}")
            # Fail safe - use base protected users
            PROTECTED_USERS.clear()
            PROTECTED_USERS.update(BASE_PROTECTED_USERS)
            logger.critical(f"SECURITY: Using base protection list with {len(PROTECTED_USERS)} users")

    async def create_user(self, username: str, ssh_public_key: str, assignment_id: str) -> bool:
        """Create temporary system user with SSH access"""
        try:
            # CRITICAL: Ensure system users are captured before any operations
            await self._capture_existing_system_users()
            # CRITICAL SECURITY: Enforce spot- prefix for all created users
            if not username.startswith('spot-'):
                logger.critical(f"SECURITY: Attempted to create user without spot- prefix: {username}")
                return False
            
            # Additional safety: Check against protected users
            if username.lower() in PROTECTED_USERS:
                logger.critical(f"SECURITY: Attempted to create protected system user: {username}")
                return False
            
            logger.info(f"Creating user {username} for assignment {assignment_id}")
            
            # Check if user already exists
            if username in self.active_users:
                logger.warning(f"User {username} already exists")
                return False
            
            # 1. Create user with home directory - EXPLICITLY NO SUDO PRIVILEGES
            cmd = [
                'sudo', 'useradd', 
                '-m',  # Create home directory
                '-s', '/bin/bash',  # Set shell
                '-G', 'spot-users',  # ONLY add to spot-users group (isolated, no privileges)
                # CRITICAL: Do NOT add to sudo, wheel, admin, or any privileged groups
                username
            ]
            
            # First ensure spot-users group exists
            try:
                subprocess.run(['sudo', 'groupadd', 'spot-users'], 
                             check=False, capture_output=True)  # Don't fail if group exists
            except subprocess.SubprocessError:
                pass  # Group might already exist
                
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info(f"Created user {username}")
            
            # 2. Create .ssh directory with sudo
            ssh_dir = Path(f"/home/{username}/.ssh")
            subprocess.run(['sudo', 'mkdir', '-p', str(ssh_dir)], check=True)
            subprocess.run(['sudo', 'chmod', '700', str(ssh_dir)], check=True)
            
            # 3. Deploy SSH public key with sudo
            authorized_keys = ssh_dir / "authorized_keys"
            # Write to temp file first, then move with sudo
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
                temp_file.write(ssh_public_key + '\n')
                temp_file_path = temp_file.name
            
            # Move temp file to authorized_keys with sudo
            subprocess.run(['sudo', 'mv', temp_file_path, str(authorized_keys)], check=True)
            
            # 4. Set correct permissions and ownership
            subprocess.run(['sudo', 'chmod', '600', str(authorized_keys)], check=True)
            subprocess.run(['sudo', 'chown', f"{username}:{username}", str(ssh_dir)], check=True)
            subprocess.run(['sudo', 'chown', f"{username}:{username}", str(authorized_keys)], check=True)
            
            # 5. CRITICAL SECURITY: Verify user has NO sudo privileges
            if await self._user_has_sudo_privileges(username):
                logger.critical(f"SECURITY VIOLATION: Created user {username} has sudo privileges!")
                # Clean up the problematic user immediately
                try:
                    subprocess.run(['sudo', 'userdel', '-r', username], check=True, capture_output=True)
                except:
                    pass
                return False
            
            # Track the user
            self.active_users[username] = assignment_id
            self.user_assignments[assignment_id] = username
            
            logger.info(f"Successfully created user {username} with SSH access (verified no sudo)")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create user {username}: {e}")
            if e.stderr:
                logger.error(f"Error output: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error creating user {username}: {e}")
            return False
    
    async def delete_user(self, username: str, assignment_id: str) -> bool:
        """Delete temporary user and clean up resources with verification"""
        try:
            logger.info(f"Deleting user {username} for assignment {assignment_id}")
            
            # Verify assignment
            if assignment_id not in self.user_assignments:
                logger.warning(f"Assignment {assignment_id} not found")
                return False
                
            if self.user_assignments[assignment_id] != username:
                logger.warning(f"Assignment {assignment_id} does not match user {username}")
                return False
            
            # CRITICAL SECURITY CHECKS: Multiple layers of protection
            if not await self._is_safe_to_delete(username):
                logger.critical(f"SECURITY VIOLATION: Attempted to delete protected user {username}")
                return False
            
            # 1. Kill all user processes with verification
            await self._kill_user_processes_secure(username)
            
            # 2. Wait for processes to fully terminate
            await asyncio.sleep(1)
            
            # 3. Verify no processes are still running
            if await self._has_running_processes(username):
                logger.error(f"SECURITY: User {username} still has running processes after termination attempt")
                return False
            
            # 4. Remove user and home directory
            cmd = [
                'sudo', 'userdel', 
                '-r',  # Remove home directory
                '-f',  # Force removal
                username
            ]
            
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            # 5. Verify user is completely removed
            if await self._user_exists(username):
                logger.critical(f"SECURITY: User {username} still exists after deletion attempt")
                return False
            
            # Clean up tracking
            if username in self.active_users:
                del self.active_users[username]
            if assignment_id in self.user_assignments:
                del self.user_assignments[assignment_id]
            
            logger.info(f"Successfully deleted and verified removal of user {username}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to delete user {username}: {e}")
            if e.stderr:
                logger.error(f"Error output: {e.stderr}")
            # Log as security incident
            logger.critical(f"SECURITY: User deletion failure for {username} - manual cleanup required")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting user {username}: {e}")
            logger.critical(f"SECURITY: Unexpected user deletion failure for {username}")
            return False
    
    async def _kill_user_processes_secure(self, username: str):
        """Securely kill all user processes"""
        try:
            # Kill with SIGTERM first
            subprocess.run(['sudo', 'pkill', '-TERM', '-u', username], 
                         check=False, capture_output=True)
            await asyncio.sleep(2)  # Give processes time to terminate gracefully
            
            # Force kill any remaining processes
            subprocess.run(['sudo', 'pkill', '-KILL', '-u', username], 
                         check=False, capture_output=True)
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error killing processes for user {username}: {e}")
    
    async def _has_running_processes(self, username: str) -> bool:
        """Check if user still has running processes"""
        try:
            result = subprocess.run(['pgrep', '-u', username], 
                                  capture_output=True, text=True)
            return result.returncode == 0  # 0 means processes found
        except Exception:
            return False  # Assume no processes if check fails
    
    async def _user_exists(self, username: str) -> bool:
        """Check if user still exists in the system"""
        try:
            result = subprocess.run(['id', username], 
                                  capture_output=True, text=True)
            return result.returncode == 0  # 0 means user exists
        except Exception:
            return False
    
    async def _is_safe_to_delete(self, username: str) -> bool:
        """CRITICAL SECURITY: Comprehensive safety check before user deletion"""
        try:
            # Check 1: Explicit protected user list
            if username.lower() in PROTECTED_USERS:
                logger.critical(f"SECURITY: Attempted to delete protected system user {username}")
                return False
            
            # Check 2: Must have spot- prefix (our users only)
            if not username.startswith('spot-'):
                logger.critical(f"SECURITY: User {username} does not have spot- prefix")
                return False
            
            # Check 3: Check UID range (system users have UID < 1000)
            uid = await self._get_user_uid(username)
            if uid is not None and (uid < MIN_DELETABLE_UID or uid > MAX_DELETABLE_UID):
                logger.critical(f"SECURITY: User {username} has UID {uid} outside safe range ({MIN_DELETABLE_UID}-{MAX_DELETABLE_UID})")
                return False
            
            # Check 4: Must be in our tracking system
            if username not in self.active_users:
                logger.critical(f"SECURITY: User {username} not in our tracking system")
                return False
            
            # Check 5: Must be in spot-users group
            if not await self._user_in_spot_group(username):
                logger.critical(f"SECURITY: User {username} not in spot-users group")
                return False
            
            # Check 6: Must not be currently logged in via SSH
            if await self._user_logged_in(username):
                logger.warning(f"SECURITY: User {username} currently logged in - forcing logout")
                await self._force_logout_user(username)
            
            # Check 7: Home directory must be in expected location
            expected_home = f"/home/{username}"
            if not await self._home_directory_safe(username, expected_home):
                logger.critical(f"SECURITY: User {username} home directory not in safe location")
                return False
            
            logger.info(f"SECURITY: User {username} passed all safety checks for deletion")
            return True
            
        except Exception as e:
            logger.critical(f"SECURITY: Error during safety check for user {username}: {e}")
            return False  # Fail safe
    
    async def _get_user_uid(self, username: str) -> int:
        """Get user's UID"""
        try:
            result = subprocess.run(['id', '-u', username], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                return int(result.stdout.strip())
        except Exception as e:
            logger.error(f"Error getting UID for user {username}: {e}")
        return None
    
    async def _user_in_spot_group(self, username: str) -> bool:
        """Check if user is in spot-users group"""
        try:
            result = subprocess.run(['groups', username], 
                                  capture_output=True, text=True)
            return 'spot-users' in result.stdout
        except Exception:
            return False
    
    async def _user_logged_in(self, username: str) -> bool:
        """Check if user is currently logged in"""
        try:
            result = subprocess.run(['who'], capture_output=True, text=True)
            return username in result.stdout
        except Exception:
            return False
    
    async def _force_logout_user(self, username: str):
        """Force logout user from all sessions"""
        try:
            # Kill all login sessions
            subprocess.run(['sudo', 'pkill', '-KILL', '-u', username], 
                         check=False, capture_output=True)
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error forcing logout for user {username}: {e}")
    
    async def _home_directory_safe(self, username: str, expected_path: str) -> bool:
        """Verify home directory is in expected safe location"""
        try:
            # Get actual home directory
            result = subprocess.run(['getent', 'passwd', username], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                # Parse passwd entry: username:x:uid:gid:gecos:home:shell
                fields = result.stdout.strip().split(':')
                if len(fields) >= 6:
                    actual_home = fields[5]
                    # Must be exactly /home/username
                    return actual_home == expected_path
        except Exception as e:
            logger.error(f"Error checking home directory for user {username}: {e}")
        return False
    
    def list_active_users(self) -> Dict[str, str]:
        """Return currently active users"""
        return self.active_users.copy()
    
    def get_user_by_assignment(self, assignment_id: str) -> str:
        """Get username by assignment ID"""
        return self.user_assignments.get(assignment_id)
    
    async def setup_environment(self) -> bool:
        """Set up the environment for user management"""
        try:
            # This should be run once during instance node startup
            logger.info("Setting up user management environment")
            
            # CRITICAL: Capture existing system users FIRST
            await self._capture_existing_system_users()
            
            # Create spot-users group if it doesn't exist (WITHOUT sudo privileges)
            try:
                subprocess.run(['sudo', 'groupadd', 'spot-users'], 
                             check=False, capture_output=True)
                logger.info("Created spot-users group for user isolation")
            except subprocess.SubprocessError:
                pass  # Group might already exist
            
            # CRITICAL SECURITY: Verify spot-users group has NO sudo privileges
            await self._verify_no_sudo_privileges()
            
            # Note: In production, you would also:
            # 1. Configure /etc/sudoers.d/spot-instance-node for specific sudo permissions
            # 2. Set up resource limits in /etc/security/limits.conf
            # 3. Configure systemd user slices for resource isolation
            
            logger.info("User management environment setup complete")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup user management environment: {e}")
            return False
    
    async def _verify_no_sudo_privileges(self):
        """CRITICAL SECURITY: Verify spot-users group has NO sudo privileges"""
        try:
            logger.info("SECURITY: Verifying spot-users group has no sudo privileges")
            
            # Check /etc/sudoers and /etc/sudoers.d/ for any spot-users privileges
            sudo_files = ['/etc/sudoers']
            
            # Add files from sudoers.d directory
            try:
                import os
                sudoers_d = '/etc/sudoers.d'
                if os.path.exists(sudoers_d):
                    for file in os.listdir(sudoers_d):
                        sudo_files.append(os.path.join(sudoers_d, file))
            except Exception:
                pass
            
            security_violations = []
            
            for sudo_file in sudo_files:
                try:
                    with open(sudo_file, 'r') as f:
                        content = f.read()
                        # Check for any references to spot-users or spot- prefixed users
                        if 'spot-users' in content or 'spot-' in content:
                            # This is a potential security violation
                            lines = content.split('\n')
                            for i, line in enumerate(lines):
                                if ('spot-users' in line or 'spot-' in line) and not line.strip().startswith('#'):
                                    security_violations.append(f"{sudo_file}:{i+1}: {line.strip()}")
                                    
                except (PermissionError, FileNotFoundError):
                    # Can't read sudo files - this is expected for non-root
                    continue
                except Exception as e:
                    logger.warning(f"Error checking {sudo_file}: {e}")
            
            if security_violations:
                logger.critical("CRITICAL SECURITY VIOLATION: spot-users found in sudo configuration!")
                for violation in security_violations:
                    logger.critical(f"VIOLATION: {violation}")
                logger.critical("IMMEDIATE ACTION REQUIRED: Remove all spot-user sudo privileges")
                return False
            
            logger.info("SECURITY VERIFIED: No sudo privileges found for spot-users")
            return True
            
        except Exception as e:
            logger.error(f"Error verifying sudo privileges: {e}")
            return False
    
    async def _user_has_sudo_privileges(self, username: str) -> bool:
        """CRITICAL SECURITY: Check if user has any sudo privileges"""
        try:
            # Method 1: Check if user is in sudo/wheel groups
            try:
                result = subprocess.run(['groups', username], capture_output=True, text=True)
                if result.returncode == 0:
                    groups = result.stdout.strip().split()
                    privileged_groups = {'sudo', 'wheel', 'admin', 'root'}
                    user_groups = set(groups[2:])  # Skip "username :"
                    
                    if user_groups.intersection(privileged_groups):
                        logger.critical(f"SECURITY: User {username} in privileged groups: {user_groups.intersection(privileged_groups)}")
                        return True
            except Exception as e:
                logger.warning(f"Error checking user groups for {username}: {e}")
            
            # Method 2: Test actual sudo capability (safe test)
            try:
                # Use sudo -n -l to check what commands user can run without password
                result = subprocess.run(['sudo', '-n', '-l', '-U', username], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and 'ALL' in result.stdout:
                    logger.critical(f"SECURITY: User {username} has sudo ALL privileges")
                    return True
            except Exception as e:
                # This is expected to fail for users without sudo - that's good
                pass
            
            # Method 3: Check /etc/sudoers files for explicit user permissions
            sudo_files = ['/etc/sudoers']
            try:
                import os
                sudoers_d = '/etc/sudoers.d'
                if os.path.exists(sudoers_d):
                    for file in os.listdir(sudoers_d):
                        sudo_files.append(os.path.join(sudoers_d, file))
            except Exception:
                pass
            
            for sudo_file in sudo_files:
                try:
                    with open(sudo_file, 'r') as f:
                        for line_num, line in enumerate(f, 1):
                            if line.strip() and not line.strip().startswith('#'):
                                if username in line and ('ALL' in line or 'sudo' in line):
                                    logger.critical(f"SECURITY: User {username} found in {sudo_file}:{line_num}: {line.strip()}")
                                    return True
                except (PermissionError, FileNotFoundError):
                    continue
                except Exception as e:
                    logger.warning(f"Error checking {sudo_file}: {e}")
            
            return False  # No privileges found
            
        except Exception as e:
            logger.error(f"Error checking sudo privileges for {username}: {e}")
            return False  # Assume no privileges on error