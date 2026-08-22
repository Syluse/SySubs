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
    Deduplicates to prevent PATH growth across repeated calls.
    """
    if sys.platform != "win32":
        return

    candidates = []

    # 1. System CUDA installation (CUDA_PATH env var or default location)
    try:
        system_root = Path(os.environ.get("SystemDrive", "C:") + "\\")
        cuda_dirs = sorted(system_root.glob("Program Files/NVIDIA GPU Computing Toolkit/CUDA/v*"))
        if not cuda_dirs:
            cuda_home = os.environ.get("CUDA_PATH")
            if cuda_home:
                cuda_dirs = [Path(cuda_home)]
        for cuda_dir in cuda_dirs:
            bin_path = (cuda_dir / "bin").absolute()
            if bin_path.exists():
                candidates.append(str(bin_path))
    except Exception as e:
        logger.warning(f"Failed to locate system CUDA: {e}")

    # 2. pip-installed nvidia packages (nvidia-*-cu12)
    try:
        import site
        for sp in site.getsitepackages() + [site.getusersitepackages()]:
            nvidia_dir = Path(sp) / "nvidia"
            if nvidia_dir.exists():
                for sub in ["cublas", "cudnn", "cuda_nvrtc"]:
                    bin_path = (nvidia_dir / sub / "bin").absolute()
                    if bin_path.exists():
                        candidates.append(str(bin_path))
    except Exception as e:
        logger.warning(f"Failed to locate pip nvidia packages: {e}")

    # Dedupe and prepend once
    current_paths = os.environ.get("PATH", "").split(os.pathsep)
    new_paths = []
    for p in candidates:
        if p not in current_paths and p not in new_paths:
            new_paths.append(p)

    if new_paths:
        os.environ["PATH"] = os.pathsep.join(new_paths) + os.pathsep + os.environ.get("PATH", "")
        for p in new_paths:
            logger.info(f"Added CUDA path to PATH: {p}")

# faster-whisper's CTranslate2 backend needs all of these loadable to run
# on device="cuda". cudart alone is not enough (e.g. cublas/cudnn may be
# missing), so every one must be verified before CUDA is selected.
REQUIRED_CUDA_DLLS = ["cudart64_*", "cublas64_*", "cublasLt64_*", "cudnn64_*"]

def _cuda_runtime_available() -> bool:
    """Checks whether every required CUDA DLL can actually be loaded.

    ctranslate2.get_cuda_device_count() can return > 0 even when part of
    the CUDA stack (cudart, cublas, cublasLt, cudnn) is missing or not
    loadable, causing a hard crash (segfault) inside WhisperModel(device="cuda").
    This function tries to load all required DLLs ahead of time.
    """
    import ctypes
    import glob

    search_dirs = set()

    # System CUDA installation
    cuda_base = os.environ.get("CUDA_PATH", "C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\*")
    search_dirs.update(glob.glob(os.path.join(cuda_base, "bin")))

    # pip-installed nvidia packages (nvidia-*-cu12)
    try:
        import site
        for sp in site.getsitepackages() + [site.getusersitepackages()]:
            for sub in ["cublas", "cudnn"]:
                bin_path = Path(sp) / "nvidia" / sub / "bin"
                if bin_path.is_dir():
                    search_dirs.add(str(bin_path.absolute()))
    except Exception:
        pass

    for d in os.environ.get("PATH", "").split(os.pathsep):
        if d and os.path.isdir(d):
            d_lower = d.lower()
            if "nvidia" in d_lower or "cuda" in d_lower or "site-packages" in d_lower:
                search_dirs.add(d)

    # Every required DLL must exist somewhere and load without error.
    for pattern in REQUIRED_CUDA_DLLS:
        candidates = []
        for d in search_dirs:
            candidates.extend(glob.glob(os.path.join(d, pattern + ".dll")))
        if not candidates:
            logger.debug(f"CUDA DLL not found: {pattern}.dll")
            return False
        try:
            ctypes.CDLL(candidates[0])
        except Exception:
            logger.debug(f"CUDA DLL failed to load: {candidates[0]}")
            return False

    return True


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
        if not _cuda_runtime_available():
            logger.warning("CUDA runtime DLLs not loadable. Falling back to CPU.")
            return DeviceInfo(device="cpu", compute_type="int8", cuda_available=False)
        return DeviceInfo(device="cuda", compute_type="float16", cuda_available=True)
    else:
        return DeviceInfo(device="cpu", compute_type="int8", cuda_available=False)
