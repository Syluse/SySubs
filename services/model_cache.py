import logging
import threading
from collections import OrderedDict

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

logger = logging.getLogger("sysubs")

_MAX_CACHED_MODELS = 2

class ModelCache:
    """LRU cache for loaded Whisper models across transcription jobs.

    Keyed on (model_dir, device, compute_type). Keeps up to _MAX_CACHED_MODELS
    variants so switching devices (Auto → CUDA → CPU) doesn't always reload.
    """

    _lock = threading.Lock()
    _models: OrderedDict = OrderedDict()

    @classmethod
    def get(cls, model_dir, device, compute_type):
        key = (model_dir, device, compute_type)
        with cls._lock:
            if key in cls._models:
                cls._models.move_to_end(key)
                logger.debug(f"Reusing cached model for {key}.")
                return cls._models[key]

            if WhisperModel is None:
                raise ImportError("faster-whisper is not installed.")
            logger.info(f"Loading Whisper model from '{model_dir}' ({device}/{compute_type})...")
            model = WhisperModel(
                model_dir,
                device=device,
                compute_type=compute_type,
                local_files_only=True,
            )

            while len(cls._models) >= _MAX_CACHED_MODELS:
                evicted_key, evicted_model = cls._models.popitem(last=False)
                logger.debug(f"Evicted cached model: {evicted_key}")
                del evicted_model

            cls._models[key] = model
            return model

    @classmethod
    def clear(cls):
        """Drops all cached models."""
        with cls._lock:
            cls._models.clear()
