import psutil
import platform
import subprocess
from typing import List, Optional
from sie.instance_node.models import HardwareProfile, CPUInfo, GPUInfo
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