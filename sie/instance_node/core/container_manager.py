import subprocess
import secrets
import string
import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class ContainerManager:
    """Manage Docker containers for spot instance isolation"""

    @staticmethod
    def generate_password(length: int = 16) -> str:
        """Generate secure random password"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def create_container(
        container_name: str,
        ssh_port: int,
        password: str,
        instance_type: str,
        gpu_enabled: bool = True,
        base_image: str = "spot-base:latest"
    ) -> bool:
        """
        Create and start a Docker container for a spot instance.

        Args:
            container_name: Name for the container (e.g., spot-i-abc123)
            ssh_port: Host port to map to container port 22
            password: Root password for SSH access
            instance_type: AWS instance type (for resource limits)
            gpu_enabled: Whether to enable GPU access
            base_image: Docker image to use

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get resource limits based on instance type
            memory_limit, cpu_limit = ContainerManager._get_resource_limits(instance_type)

            # Prepare data directory for persistent storage
            data_dir = f"/data/{container_name}"
            subprocess.run(["mkdir", "-p", data_dir], check=True)

            # Build docker run command
            cmd = [
                "docker", "run",
                "-d",  # Detached mode
                "--name", container_name,
                "--hostname", container_name,
                "-p", f"{ssh_port}:22",  # SSH port mapping
                "--memory", memory_limit,  # Memory limit
                "--cpus", cpu_limit,  # CPU limit
                "-v", f"{data_dir}:/workspace",  # Persistent user data
                "-e", f"ROOT_PASSWORD={password}",  # Pass password as env var
                "--restart", "no",  # Don't auto-restart
            ]

            # Add GPU support if enabled
            if gpu_enabled:
                cmd.extend(["--gpus", "all"])

            # Add shared datasets if directory exists
            try:
                subprocess.run(["test", "-d", "/datasets"], check=True, capture_output=True)
                cmd.extend(["-v", "/datasets:/datasets:ro"])  # Read-only shared datasets
            except subprocess.CalledProcessError:
                pass  # /datasets doesn't exist, skip

            # Add image name
            cmd.append(base_image)

            # Run container
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )

            logger.info(f"Created container {container_name} on port {ssh_port}")

            # Wait for SSH to be ready (up to 10 seconds)
            for i in range(20):
                if ContainerManager._check_ssh_ready(ssh_port):
                    logger.info(f"SSH ready on port {ssh_port}")
                    return True
                time.sleep(0.5)

            logger.warning(f"Container created but SSH not ready on port {ssh_port}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create container {container_name}: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error creating container {container_name}: {e}")
            return False

    @staticmethod
    def _get_resource_limits(instance_type: str) -> Tuple[str, str]:
        """
        Get memory and CPU limits based on instance type.
        Returns (memory_limit, cpu_limit) as strings for docker.
        Uses 90% of actual resources to leave room for host.
        """
        # Define limits per instance type (90% of actual to leave room for host)
        limits = {
            # P3 instances (GPU)
            "p3.xlarge": ("55g", "3.5"),      # 61GB RAM, 4 cores
            "p3.2xlarge": ("55g", "7.0"),     # 61GB RAM, 8 cores
            "p3.8xlarge": ("220g", "28.0"),   # 244GB RAM, 32 cores
            "p3.16xlarge": ("440g", "56.0"),  # 488GB RAM, 64 cores

            # P2 instances (GPU)
            "p2.xlarge": ("55g", "3.5"),      # 61GB RAM, 4 cores
            "p2.8xlarge": ("440g", "28.0"),   # 488GB RAM, 32 cores
            "p2.16xlarge": ("665g", "56.0"),  # 732GB RAM, 64 cores

            # G4 instances (GPU)
            "g4dn.xlarge": ("14g", "3.6"),    # 16GB RAM, 4 cores
            "g4dn.2xlarge": ("29g", "7.2"),   # 32GB RAM, 8 cores
            "g4dn.4xlarge": ("58g", "14.4"),  # 64GB RAM, 16 cores
            "g4dn.8xlarge": ("116g", "28.8"), # 128GB RAM, 32 cores
            "g4dn.12xlarge": ("174g", "43.2"), # 192GB RAM, 48 cores

            # M5 instances (General purpose)
            "m5.large": ("7g", "1.8"),        # 8GB RAM, 2 cores
            "m5.xlarge": ("14g", "3.6"),      # 16GB RAM, 4 cores
            "m5.2xlarge": ("29g", "7.2"),     # 32GB RAM, 8 cores
            "m5.4xlarge": ("58g", "14.4"),    # 64GB RAM, 16 cores
            "m5.8xlarge": ("116g", "28.8"),   # 128GB RAM, 32 cores

            # R5 instances (Memory optimized)
            "r5.large": ("14g", "1.8"),       # 16GB RAM, 2 cores
            "r5.xlarge": ("29g", "3.6"),      # 32GB RAM, 4 cores
            "r5.2xlarge": ("58g", "7.2"),     # 64GB RAM, 8 cores
            "r5.4xlarge": ("116g", "14.4"),   # 128GB RAM, 16 cores
            "r5.8xlarge": ("233g", "28.8"),   # 256GB RAM, 32 cores
            "r5.12xlarge": ("349g", "43.2"),  # 384GB RAM, 48 cores

            # T2/T3 instances (Burstable)
            "t2.micro": ("0.9g", "0.9"),      # 1GB RAM, 1 core
            "t2.small": ("1.8g", "0.9"),      # 2GB RAM, 1 core
            "t2.medium": ("3.6g", "1.8"),     # 4GB RAM, 2 cores
            "t3.micro": ("0.9g", "1.8"),      # 1GB RAM, 2 cores
            "t3.small": ("1.8g", "1.8"),      # 2GB RAM, 2 cores
            "t3.medium": ("3.6g", "1.8"),     # 4GB RAM, 2 cores
            "t3.large": ("7g", "1.8"),        # 8GB RAM, 2 cores
            "t3.xlarge": ("14g", "3.6"),      # 16GB RAM, 4 cores
        }

        # Default to conservative limits if type unknown
        default_limits = ("7g", "1.8")
        result = limits.get(instance_type, default_limits)

        if instance_type not in limits:
            logger.warning(f"Unknown instance type {instance_type}, using default limits {default_limits}")

        return result

    @staticmethod
    def _check_ssh_ready(port: int) -> bool:
        """Check if SSH is accepting connections"""
        try:
            result = subprocess.run(
                ["nc", "-z", "localhost", str(port)],
                capture_output=True,
                timeout=1
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def stop_container(container_name: str, signal: str = "SIGTERM") -> bool:
        """
        Send signal to all processes in container.

        Args:
            container_name: Name of the container
            signal: Signal to send (SIGTERM or SIGKILL)
        """
        try:
            subprocess.run(
                ["docker", "kill", "--signal", signal, container_name],
                check=True,
                capture_output=True
            )
            logger.info(f"Sent {signal} to container {container_name}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to stop container {container_name}: {e.stderr}")
            return False

    @staticmethod
    def remove_container(container_name: str, force: bool = True) -> bool:
        """
        Remove a container and its data directory.

        Args:
            container_name: Name of the container
            force: Force removal even if running
        """
        try:
            # Remove container
            cmd = ["docker", "rm"]
            if force:
                cmd.append("-f")
            cmd.append(container_name)

            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"Removed container {container_name}")

            # Remove data directory
            data_dir = f"/data/{container_name}"
            try:
                subprocess.run(["rm", "-rf", data_dir], check=True, capture_output=True)
                logger.info(f"Removed data directory {data_dir}")
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to remove data directory {data_dir}: {e.stderr}")

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to remove container {container_name}: {e.stderr}")
            return False

    @staticmethod
    def container_exists(container_name: str) -> bool:
        """Check if a container exists"""
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name=^{container_name}$", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=True
            )
            return container_name in result.stdout
        except subprocess.CalledProcessError:
            return False

    @staticmethod
    def get_container_status(container_name: str) -> Optional[str]:
        """Get container status (running, exited, etc.)"""
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name=^{container_name}$", "--format", "{{.Status}}"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip() if result.stdout else None
        except subprocess.CalledProcessError:
            return None
