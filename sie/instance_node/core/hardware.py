import psutil
import platform
import subprocess
import socket
import hashlib
from typing import List, Optional
from sie.instance_node.core.hardware_schema import HardwareProfile, CPUInfo, GPUInfo
import logging

logger = logging.getLogger(__name__)

class HardwareDetector:
    @staticmethod
    def detect_hardware() -> HardwareProfile:
        """Detect system hardware specifications"""
        cpu_info = HardwareDetector._get_cpu_info()
        memory_mb = HardwareDetector._get_memory()
        gpu_info = HardwareDetector._get_gpu_info()
        storage_gb = HardwareDetector._get_storage()
        
        return HardwareProfile(
            cpu=cpu_info,
            memory_mb=memory_mb,
            gpus=gpu_info,
            storage_gb=storage_gb
        )
    
    @staticmethod
    def _get_cpu_info() -> CPUInfo:
        """Get CPU information"""
        cpu_count = psutil.cpu_count(logical=False)
        cpu_threads = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq()
        
        return CPUInfo(
            cores=cpu_count,
            threads=cpu_threads,
            model=platform.processor() or "Unknown",
            frequency_mhz=cpu_freq.current if cpu_freq else 0
        )
    
    @staticmethod
    def _get_memory() -> int:
        """Get memory in MB"""
        mem = psutil.virtual_memory()
        return int(mem.total / (1024 * 1024))
    
    @staticmethod
    def _get_gpu_info() -> List[GPUInfo]:
        """Detect GPU information (simplified, works with NVIDIA)"""
        gpus = []
        try:
            # Try nvidia-smi for NVIDIA GPUs
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    parts = line.split(', ')
                    if len(parts) >= 2:
                        gpus.append(GPUInfo(
                            model=parts[0],
                            memory_mb=int(parts[1]),
                            count=1
                        ))
        except (subprocess.SubprocessError, FileNotFoundError):
            logger.info("No NVIDIA GPUs detected or nvidia-smi not available")
        
        return gpus
    
    @staticmethod
    def _get_storage() -> int:
        """Get storage in GB"""
        disk = psutil.disk_usage('/')
        return int(disk.total / (1024 * 1024 * 1024))
    
    @staticmethod
    def generate_worker_id() -> str:
        """Generate a unique worker ID based on machine characteristics"""
        try:
            # Use hostname as primary identifier
            hostname = socket.gethostname()

            # Get MAC addresses for additional uniqueness
            mac_addresses = []
            for interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == psutil.AF_LINK and addr.address and addr.address != "00:00:00:00:00:00":
                        mac_addresses.append(addr.address)

            # Create unique string from hostname + first MAC
            unique_str = hostname
            if mac_addresses:
                unique_str += "-" + mac_addresses[0].replace(":", "")

            # Hash to create shorter, consistent ID
            worker_hash = hashlib.md5(unique_str.encode()).hexdigest()[:8]

            return f"worker-{hostname}-{worker_hash}"

        except Exception as e:
            logger.warning(f"Could not generate worker ID from hardware: {e}")
            # Fallback to hostname only
            return f"worker-{socket.gethostname()}-unknown"

    @staticmethod
    def infer_instance_type(hardware: HardwareProfile) -> str:
        """
        Infer AWS-like instance type from hardware specifications.
        Maps hardware to common instance types based on GPU, CPU, and memory.
        """
        # GPU-based instances (highest priority)
        if hardware.gpus and len(hardware.gpus) > 0:
            gpu = hardware.gpus[0]
            gpu_model_lower = gpu.model.lower()

            # NVIDIA Tesla V100
            if 'v100' in gpu_model_lower:
                if len(hardware.gpus) >= 8:
                    return 'p3.16xlarge'
                elif len(hardware.gpus) >= 4:
                    return 'p3.8xlarge'
                elif len(hardware.gpus) >= 2:
                    return 'p3dn.24xlarge'
                else:
                    return 'p3.2xlarge'

            # NVIDIA Tesla K80
            elif 'k80' in gpu_model_lower:
                if len(hardware.gpus) >= 8:
                    return 'p2.16xlarge'
                elif len(hardware.gpus) >= 4:
                    return 'p2.8xlarge'
                else:
                    return 'p2.xlarge'

            # NVIDIA A100
            elif 'a100' in gpu_model_lower:
                if len(hardware.gpus) >= 8:
                    return 'p4d.24xlarge'
                elif len(hardware.gpus) >= 4:
                    return 'p4de.24xlarge'
                else:
                    return 'p4d.24xlarge'

            # NVIDIA T4
            elif 't4' in gpu_model_lower:
                if len(hardware.gpus) >= 4:
                    return 'g4dn.12xlarge'
                elif len(hardware.gpus) >= 2:
                    return 'g4dn.8xlarge'
                else:
                    return 'g4dn.xlarge'

            # NVIDIA RTX series (consumer/workstation GPUs)
            elif 'rtx' in gpu_model_lower or 'geforce' in gpu_model_lower:
                # Map to g4dn or g5 series based on memory
                if gpu.memory_mb >= 24000:  # 24GB+
                    return 'g5.12xlarge'
                elif gpu.memory_mb >= 16000:  # 16GB+
                    return 'g5.4xlarge'
                else:
                    return 'g4dn.xlarge'

            # Generic GPU fallback
            else:
                if len(hardware.gpus) >= 4:
                    return 'g4dn.12xlarge'
                else:
                    return 'g4dn.xlarge'

        # CPU and memory-based instances (no GPU)
        memory_gb = hardware.memory_mb / 1024
        cpu_cores = hardware.cpu.cores

        # High memory instances (> 128GB)
        if memory_gb >= 128:
            if cpu_cores >= 48:
                return 'r5.12xlarge'
            elif cpu_cores >= 24:
                return 'r5.8xlarge'
            elif cpu_cores >= 16:
                return 'r5.4xlarge'
            else:
                return 'r5.2xlarge'

        # Medium memory instances (32-128GB)
        elif memory_gb >= 32:
            if cpu_cores >= 32:
                return 'm5.8xlarge'
            elif cpu_cores >= 16:
                return 'm5.4xlarge'
            elif cpu_cores >= 8:
                return 'm5.2xlarge'
            else:
                return 'm5.xlarge'

        # Standard instances (8-32GB)
        elif memory_gb >= 8:
            if cpu_cores >= 16:
                return 'm5.4xlarge'
            elif cpu_cores >= 8:
                return 'm5.2xlarge'
            elif cpu_cores >= 4:
                return 'm5.xlarge'
            else:
                return 'm5.large'

        # Small instances (< 8GB)
        else:
            if cpu_cores >= 4:
                return 't3.xlarge'
            elif cpu_cores >= 2:
                return 't3.large'
            else:
                return 't2.micro'