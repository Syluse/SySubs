import os
import sys
import shutil
import logging
from pathlib import Path
from constants import MODEL_REGISTRY
from services.model_cache import ModelCache
from infra.errors import ModelError

try:
    import faster_whisper
except ImportError:
    faster_whisper = None

logger = logging.getLogger("sysubs")

# Domain alias — model lifecycle errors are ModelErrors in the shared hierarchy.
# Kept as a module attribute so existing imports (ui, tests) keep working.
SySubsError = ModelError

class ModelService:
    def __init__(self, config_manager):
        self.config = config_manager
        self.models_path = self.get_models_path()
        self.models_path.mkdir(parents=True, exist_ok=True)

    def get_models_path(self) -> Path:
        """Resolves the models directory path."""
        if getattr(sys, 'frozen', False):
            # Frozen bundle: models/ sits next to the executable
            return Path(sys.executable).parent / "models"

        # Dev environment: project_root / models
        return Path(__file__).parent.parent / "models"

    def is_downloaded(self, model_name: str) -> bool:
        """Checks if a model directory contains a valid CTranslate2 model.

        A valid model must contain a non-empty 'model.bin'. Interrupted or
        partial downloads (only tokenizer files, a leftover .cache dir, etc.)
        are treated as NOT downloaded so the UI can offer a re-download.
        """
        model_bin = self.models_path / model_name / "model.bin"
        try:
            return model_bin.is_file() and model_bin.stat().st_size > 0
        except OSError:
            return False

    def list_models(self) -> list[dict]:
        """Returns a list of all models in registry with their on-disk status."""
        models = []
        for name, info in MODEL_REGISTRY.items():
            entry = info.copy()
            entry["name"] = name
            entry["downloaded"] = self.is_downloaded(name)
            models.append(entry)
        return models

    def download(self, model_name: str, progress_cb: callable = None):
        """Downloads a model using faster-whisper's utility."""
        if faster_whisper is None:
            raise SySubsError("faster-whisper is not installed.")

        if model_name not in MODEL_REGISTRY:
            raise SySubsError(f"Model '{model_name}' is not in the registry.")

        if self.is_downloaded(model_name):
            logger.info(f"Model '{model_name}' is already downloaded. Skipping.")
            return

        # A stale/partial directory (e.g. from an interrupted download) must be
        # removed so the fresh download can be written cleanly.
        stale_dir = self.models_path / model_name
        if stale_dir.exists():
            logger.warning(f"Removing incomplete model directory '{stale_dir}' before download.")
            shutil.rmtree(stale_dir)

        logger.info(f"Starting download of model: {model_name}")

        # Temporarily allow network (HF_HUB_OFFLINE may be set at startup
        # to prevent hangs during model loading, but downloads need it)
        old_offline = os.environ.pop("HF_HUB_OFFLINE", None)

        try:
            # Prefer the WhisperModel classmethod (present in newer faster-whisper);
            # fall back to the legacy utils helper for older versions.
            download_model = getattr(faster_whisper.WhisperModel, "download_model", None)
            if download_model is None:
                download_model = faster_whisper.utils.download_model
            download_model(
                model_name,
                output_dir=str(self.models_path / model_name),
            )
            if not self.is_downloaded(model_name):
                raise SySubsError(
                    f"Download of '{model_name}' appears incomplete (model.bin missing or empty). "
                    "Please try again."
                )
            logger.info(f"Successfully downloaded model: {model_name}")
            ModelCache.clear()
        except PermissionError:
            raise SySubsError(
                "Permission denied. Move the SySubs folder out of Program Files to a folder you own, "
                "such as your Desktop or Documents."
            )
        except Exception as e:
            self.delete(model_name)
            raise SySubsError(f"Failed to download model '{model_name}': {e}")
        finally:
            # Restore offline mode
            if old_offline is not None:
                os.environ["HF_HUB_OFFLINE"] = old_offline

    def delete(self, model_name: str):
        """Deletes a model directory from disk."""
        if model_name == self.config.get("model"):
            raise SySubsError(f"Cannot delete the currently active model: {model_name}")

        model_dir = self.models_path / model_name
        if model_dir.exists():
            try:
                shutil.rmtree(model_dir)
                logger.info(f"Deleted model directory: {model_name}")
                ModelCache.clear()
            except Exception as e:
                raise SySubsError(f"Failed to delete model directory '{model_name}': {e}")
        else:
            logger.warning(f"Attempted to delete non-existent model: {model_name}")
