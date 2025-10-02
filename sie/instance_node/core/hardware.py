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