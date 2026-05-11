import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import ctranslate2
except ImportError:
    ctranslate2 = None

logger = logging.getLogger("sysubs")

@dataclass
class DeviceInfo:
    device: str
    compute_type: str
    cuda_available: bool

def setup_cuda_path():
    """
    On Windows, adds NVIDIA runtime DLL paths to the system PATH.
    Useful for dev environments where nvidia-*-cu12 packages are installed.
    """
    if sys.platform != "win32":
        return

    # Try to find nvidia packages in site-packages
    try:
        import site
        # Search in all site-packages
        for sp in site.getsitepackages() + [site.getusersitepackages()]:
            nvidia_dir = Path(sp) / "nvidia"
            if nvidia_dir.exists():
                # Common sub-packages that contain bin/DLLs
                for sub in ["cublas", "cudnn", "cuda_nvrtc"]:
                    bin_path = nvidia_dir / sub / "bin"
                    if bin_path.exists():
                        path_str = str(bin_path.absolute())
                        if path_str not in os.environ["PATH"]:
                            os.environ["PATH"] = path_str + os.pathsep + os.environ["PATH"]
                            logger.info(f"Added to PATH: {path_str}")
    except Exception as e:
        logger.warning(f"Failed to auto-inject CUDA paths: {e}")

def detect() -> DeviceInfo:
    """Detects the best available hardware for transcription."""
    setup_cuda_path() # Try to fix PATH before detection
    
    if ctranslate2 is None:
        logger.warning("ctranslate2 not found. Defaulting to CPU.")
        return DeviceInfo(device="cpu", compute_type="int8", cuda_available=False)

    try:
        cuda_available = ctranslate2.get_cuda_device_count() > 0
        if cuda_available:
            # Note: Even if count > 0, DLLs might be missing. 
            # We will handle the runtime error in the TranscriptionService.
            return DeviceInfo(device="cuda", compute_type="float16", cuda_available=True)
    except Exception as e:
        logger.warning(f"Error detecting CUDA: {e}. Defaulting to CPU.")
    
    # Default to CPU with int8 quantization for efficiency
    return DeviceInfo(device="cpu", compute_type="int8", cuda_available=False)

def resolve(device_override: str) -> DeviceInfo:
    """Resolves device info based on user override ('auto', 'cuda', 'cpu')."""
    if device_override == "auto":
        return detect()
    elif device_override == "cuda":
        return DeviceInfo(device="cuda", compute_type="float16", cuda_available=True)
    else: # "cpu"
        return DeviceInfo(device="cpu", compute_type="int8", cuda_available=False)
