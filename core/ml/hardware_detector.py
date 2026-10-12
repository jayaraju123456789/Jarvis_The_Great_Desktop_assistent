"""
core/ml/hardware_detector.py — Runtime Hardware & Compute Profiler for JARVIS ML Agent.

Inspects:
1. Physical and logical CPU core count.
2. Total and available system RAM.
3. Free disk capacity in workspace.
4. Real CUDA GPU availability (verifies PyTorch CUDA runtime, not merely presence of graphics adapter).
5. GPU VRAM capacity if CUDA is active.
6. Generates hardware-aware execution strategy (CPU vs GPU, batch size, recommended model complexity).
"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


@dataclass
class HardwareProfile:
    os_name: str
    cpu_cores_logical: int
    cpu_cores_physical: int
    ram_total_gb: float
    ram_available_gb: float
    disk_free_gb: float
    cuda_available: bool
    cuda_device_name: Optional[str] = None
    cuda_vram_gb: Optional[float] = None
    recommended_device: str = "cpu"  # "cpu" | "cuda"
    recommended_batch_size: int = 32
    max_model_parameter_tier: str = "lightweight"  # lightweight (sklearn / small CNN) | medium | large

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        lines = [
            f"OS: {self.os_name} | CPU: {self.cpu_cores_logical} cores",
            f"RAM: {self.ram_available_gb:.1f} GB available / {self.ram_total_gb:.1f} GB total",
            f"Disk Free: {self.disk_free_gb:.1f} GB",
            f"CUDA GPU: {'Yes (' + str(self.cuda_device_name) + ', ' + str(self.cuda_vram_gb) + ' GB VRAM)' if self.cuda_available else 'No (CPU execution strategy enforced)'}",
            f"Execution Strategy: {self.recommended_device.upper()} | Model Tier: {self.max_model_parameter_tier}",
        ]
        return "\n".join(lines)


class HardwareDetector:
    """Inspects available hardware resources to guide scientific execution constraints."""

    @staticmethod
    def profile(target_dir: Optional[Path] = None) -> HardwareProfile:
        os_name = f"{platform.system()} {platform.release()}"
        cpu_logical = os.cpu_count() or 4
        cpu_physical = cpu_logical

        ram_total = 8.0
        ram_avail = 4.0

        if _PSUTIL_AVAILABLE:
            try:
                mem = psutil.virtual_memory()
                ram_total = round(mem.total / (1024 ** 3), 2)
                ram_avail = round(mem.available / (1024 ** 3), 2)
                cpu_physical = psutil.cpu_count(logical=False) or cpu_logical
            except Exception:
                pass

        # Disk space
        check_path = target_dir or Path.cwd()
        try:
            d = shutil.disk_usage(check_path)
            disk_free = round(d.free / (1024 ** 3), 2)
        except Exception:
            disk_free = 50.0

        # CUDA check (verify actual framework support, not just graphics card presence)
        cuda_avail = False
        cuda_name = None
        cuda_vram = None

        try:
            import torch
            if torch.cuda.is_available():
                cuda_avail = True
                cuda_name = torch.cuda.get_device_name(0)
                cuda_vram = round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2)
        except Exception:
            cuda_avail = False

        # Strategy selection
        if cuda_avail and cuda_vram and cuda_vram >= 4.0:
            rec_device = "cuda"
            rec_batch = 64 if cuda_vram >= 8.0 else 32
            tier = "medium" if cuda_vram < 10.0 else "large"
        else:
            rec_device = "cpu"
            rec_batch = 16 if ram_avail < 4.0 else 32
            tier = "lightweight"

        return HardwareProfile(
            os_name=os_name,
            cpu_cores_logical=cpu_logical,
            cpu_cores_physical=cpu_physical,
            ram_total_gb=ram_total,
            ram_available_gb=ram_avail,
            disk_free_gb=disk_free,
            cuda_available=cuda_avail,
            cuda_device_name=cuda_name,
            cuda_vram_gb=cuda_vram,
            recommended_device=rec_device,
            recommended_batch_size=rec_batch,
            max_model_parameter_tier=tier,
        )


# Global instance
hardware_detector = HardwareDetector()
