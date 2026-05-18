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
    Searches both system CUDA installations and pip-installed nvidia packages.
    """
    if sys.platform != "win32":
        return

    # 1. System CUDA installation (CUDA_PATH env var or default location)
    try:
        cuda_home = os.environ.get("CUDA_PATH", "C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\*")
        candidates = sorted(Path(os.environ.get("SystemDrive", "C:")).glob("Program Files/NVIDIA GPU Computing Toolkit/CUDA/v*"))
        if not candidates:
            candidates = [Path(cuda_home)]
        for cuda_dir in candidates:
            bin_path = cuda_dir / "bin"
            if bin_path.exists():
                path_str = str(bin_path.absolute())
                if path_str not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = path_str + os.pathsep + os.environ.get("PATH", "")
                    logger.info(f"Added CUDA toolkit to PATH: {path_str}")
    except Exception as e:
        logger.warning(f"Failed to add system CUDA to PATH: {e}")

    # 2. pip-installed nvidia packages (nvidia-*-cu12)
    try:
        import site
        for sp in site.getsitepackages() + [site.getusersitepackages()]:
            nvidia_dir = Path(sp) / "nvidia"
            if nvidia_dir.exists():
                for sub in ["cublas", "cudnn", "cuda_nvrtc"]:
                    bin_path = nvidia_dir / sub / "bin"
                    if bin_path.exists():
                        path_str = str(bin_path.absolute())
                        if path_str not in os.environ.get("PATH", ""):
                            os.environ["PATH"] = path_str + os.pathsep + os.environ["PATH"]
                            logger.info(f"Added to PATH: {path_str}")
    except Exception as e:
        logger.warning(f"Failed to auto-inject CUDA paths: {e}")

def _cuda_runtime_available() -> bool:
    """Checks whether the CUDA runtime DLL can actually be loaded.

    ctranslate2.get_cuda_device_count() can return > 0 even when the
    full CUDA runtime (cudart, cublas, cudnn) isn't loadable later,
    causing a hard crash (segfault) inside WhisperModel(device="cuda").
    This function tries to load the key DLLs ahead of time.
    """
    try:
        import ctypes
        import glob
        # Locate cudart64_*.dll — the core CUDA runtime
        candidates = glob.glob(os.path.join(os.environ.get("CUDA_PATH", "C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\*"), "bin", "cudart64_*.dll"))
        if candidates:
            ctypes.CDLL(candidates[0])
            return True
    except Exception:
        pass

    # Fall back to PATH-based lookup
    try:
        import ctypes.util
        path = ctypes.util.find_library("cudart")
        if path:
            ctypes.CDLL(path)
            return True
    except Exception:
        pass
    return False


def detect() -> DeviceInfo:
    """Detects the best available hardware for transcription."""
    setup_cuda_path() # Try to fix PATH before detection
    
    if ctranslate2 is None:
        logger.warning("ctranslate2 not found. Defaulting to CPU.")
        return DeviceInfo(device="cpu", compute_type="int8", cuda_available=False)

    try:
        cuda_count = ctranslate2.get_cuda_device_count()
        if cuda_count > 0 and _cuda_runtime_available():
            return DeviceInfo(device="cuda", compute_type="float16", cuda_available=True)
        elif cuda_count > 0:
            logger.warning("CUDA device detected but runtime DLLs not loadable. Falling back to CPU.")
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
