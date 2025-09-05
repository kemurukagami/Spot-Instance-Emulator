from pydantic import BaseModel
from typing import List, Optional

class CPUInfo(BaseModel):
    cores: int
    threads: int
    model: str
    frequency_mhz: float

class GPUInfo(BaseModel):
    model: str
    memory_mb: int
    count: int

class HardwareProfile(BaseModel):
    cpu: CPUInfo
    memory_mb: int
    gpus: Optional[List[GPUInfo]] = []
    storage_gb: int