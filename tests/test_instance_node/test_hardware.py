import unittest
from unittest.mock import Mock, patch, MagicMock
import subprocess
from sie.instance_node.core.hardware import HardwareDetector
from sie.instance_node.models import HardwareProfile, CPUInfo, GPUInfo


class TestHardwareDetector(unittest.TestCase):
    
    @patch('sie.instance_node.core.hardware.psutil')
    @patch('sie.instance_node.core.hardware.platform')
    def test_get_cpu_info(self, mock_platform, mock_psutil):
        """Test CPU info detection"""
        # Mock psutil CPU functions
        mock_psutil.cpu_count.side_effect = lambda logical: 4 if not logical else 8
        mock_freq = Mock()
        mock_freq.current = 2400.0
        mock_psutil.cpu_freq.return_value = mock_freq
        mock_platform.processor.return_value = "Intel(R) Core(TM) i7-8700K"
        
        cpu_info = HardwareDetector._get_cpu_info()
        
        self.assertEqual(cpu_info.cores, 4)
        self.assertEqual(cpu_info.threads, 8)
        self.assertEqual(cpu_info.model, "Intel(R) Core(TM) i7-8700K")
        self.assertEqual(cpu_info.frequency_mhz, 2400.0)
    
    @patch('sie.instance_node.core.hardware.psutil')
    @patch('sie.instance_node.core.hardware.platform')
    def test_get_cpu_info_no_frequency(self, mock_platform, mock_psutil):
        """Test CPU info when frequency is not available"""
        mock_psutil.cpu_count.side_effect = lambda logical: 2 if not logical else 4
        mock_psutil.cpu_freq.return_value = None
        mock_platform.processor.return_value = "Unknown CPU"
        
        cpu_info = HardwareDetector._get_cpu_info()
        
        self.assertEqual(cpu_info.cores, 2)
        self.assertEqual(cpu_info.threads, 4)
        self.assertEqual(cpu_info.frequency_mhz, 0)
    
    @patch('sie.instance_node.core.hardware.psutil')
    def test_get_memory(self, mock_psutil):
        """Test memory detection"""
        mock_memory = Mock()
        mock_memory.total = 8589934592  # 8 GB in bytes
        mock_psutil.virtual_memory.return_value = mock_memory
        
        memory_mb = HardwareDetector._get_memory()
        
        self.assertEqual(memory_mb, 8192)  # 8 GB in MB
    
    @patch('sie.instance_node.core.hardware.subprocess.run')
    def test_get_gpu_info_nvidia(self, mock_run):
        """Test NVIDIA GPU detection"""
        # Mock nvidia-smi output
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Tesla V100-SXM2-16GB, 16384\nTesla V100-SXM2-16GB, 16384"
        mock_run.return_value = mock_result
        
        gpus = HardwareDetector._get_gpu_info()
        
        self.assertEqual(len(gpus), 2)
        self.assertEqual(gpus[0].model, "Tesla V100-SXM2-16GB")
        self.assertEqual(gpus[0].memory_mb, 16384)
        self.assertEqual(gpus[0].count, 1)
    
    @patch('sie.instance_node.core.hardware.subprocess.run')
    def test_get_gpu_info_no_nvidia(self, mock_run):
        """Test GPU detection when nvidia-smi fails"""
        # Mock nvidia-smi failure
        mock_result = Mock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result
        
        gpus = HardwareDetector._get_gpu_info()
        
        self.assertEqual(len(gpus), 0)
    
    @patch('sie.instance_node.core.hardware.subprocess.run')
    def test_get_gpu_info_command_not_found(self, mock_run):
        """Test GPU detection when nvidia-smi is not installed"""
        mock_run.side_effect = FileNotFoundError()
        
        gpus = HardwareDetector._get_gpu_info()
        
        self.assertEqual(len(gpus), 0)
    
    @patch('sie.instance_node.core.hardware.subprocess.run')
    def test_get_gpu_info_timeout(self, mock_run):
        """Test GPU detection with timeout"""
        mock_run.side_effect = subprocess.TimeoutExpired('nvidia-smi', 5)
        
        gpus = HardwareDetector._get_gpu_info()
        
        self.assertEqual(len(gpus), 0)
    
    @patch('sie.instance_node.core.hardware.psutil')
    def test_get_storage(self, mock_psutil):
        """Test storage detection"""
        mock_disk = Mock()
        mock_disk.total = 536870912000  # 500 GB in bytes
        mock_psutil.disk_usage.return_value = mock_disk
        
        storage_gb = HardwareDetector._get_storage()
        
        self.assertEqual(storage_gb, 500)
    
    @patch('sie.instance_node.core.hardware.HardwareDetector._get_cpu_info')
    @patch('sie.instance_node.core.hardware.HardwareDetector._get_memory')
    @patch('sie.instance_node.core.hardware.HardwareDetector._get_gpu_info')
    @patch('sie.instance_node.core.hardware.HardwareDetector._get_storage')
    def test_detect_hardware(self, mock_storage, mock_gpu, mock_memory, mock_cpu):
        """Test complete hardware detection"""
        # Mock individual detection methods
        mock_cpu.return_value = CPUInfo(
            cores=4,
            threads=8,
            model="Intel i7",
            frequency_mhz=2400.0
        )
        mock_memory.return_value = 16384
        mock_gpu.return_value = [
            GPUInfo(model="GTX 1080", memory_mb=8192, count=1)
        ]
        mock_storage.return_value = 1000
        
        hardware = HardwareDetector.detect_hardware()
        
        self.assertIsInstance(hardware, HardwareProfile)
        self.assertEqual(hardware.cpu.cores, 4)
        self.assertEqual(hardware.memory_mb, 16384)
        self.assertEqual(len(hardware.gpus), 1)
        self.assertEqual(hardware.gpus[0].model, "GTX 1080")
        self.assertEqual(hardware.storage_gb, 1000)
    
    @patch('sie.instance_node.core.hardware.HardwareDetector._get_cpu_info')
    @patch('sie.instance_node.core.hardware.HardwareDetector._get_memory')
    @patch('sie.instance_node.core.hardware.HardwareDetector._get_gpu_info')
    @patch('sie.instance_node.core.hardware.HardwareDetector._get_storage')
    def test_detect_hardware_no_gpu(self, mock_storage, mock_gpu, mock_memory, mock_cpu):
        """Test hardware detection with no GPU"""
        mock_cpu.return_value = CPUInfo(
            cores=2,
            threads=2,
            model="Intel Celeron",
            frequency_mhz=1800.0
        )
        mock_memory.return_value = 4096
        mock_gpu.return_value = []
        mock_storage.return_value = 256
        
        hardware = HardwareDetector.detect_hardware()
        
        self.assertEqual(len(hardware.gpus), 0)
        self.assertEqual(hardware.memory_mb, 4096)
        self.assertEqual(hardware.storage_gb, 256)
    
    def test_hardware_profile_to_dict(self):
        """Test converting HardwareProfile to dictionary"""
        cpu = CPUInfo(cores=4, threads=8, model="Intel i7", frequency_mhz=2400.0)
        gpu = GPUInfo(model="RTX 3090", memory_mb=24576, count=1)
        
        profile = HardwareProfile(
            cpu=cpu,
            memory_mb=32768,
            gpus=[gpu],
            storage_gb=2000
        )
        
        profile_dict = profile.dict()
        
        self.assertIn("cpu", profile_dict)
        self.assertIn("memory_mb", profile_dict)
        self.assertIn("gpus", profile_dict)
        self.assertIn("storage_gb", profile_dict)
        self.assertEqual(profile_dict["cpu"]["cores"], 4)
        self.assertEqual(len(profile_dict["gpus"]), 1)
        self.assertEqual(profile_dict["gpus"][0]["model"], "RTX 3090")


if __name__ == "__main__":
    unittest.main()