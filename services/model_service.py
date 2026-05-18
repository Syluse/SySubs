import os
import sys
import shutil
import logging
from pathlib import Path
from constants import MODEL_REGISTRY

try:
    import faster_whisper
except ImportError:
    faster_whisper = None

logger = logging.getLogger("sysubs")

class SySubsError(Exception):
    """Base domain exception for SySubs."""
    pass

class ModelService:
    def __init__(self, config_manager):
        self.config = config_manager
        self.models_path = self.get_models_path()
        self.models_path.mkdir(parents=True, exist_ok=True)

    def get_models_path(self) -> Path:
        """Resolves the models directory path."""
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # PyInstaller bundle: models/ should be next to the executable
            # sys._MEIPASS is the temp folder for internal assets, 
            # but user models should be in a persistent location.
            # However, the PLAN.md says "models/ relative to executable".
            # For portable apps, this is usually sibling to .exe.
            exe_dir = Path(sys.executable).parent
            return exe_dir / "models"
        
        # Dev environment: project_root / models
        return Path(__file__).parent.parent / "models"

    def is_downloaded(self, model_name: str) -> bool:
        """Checks if a model directory exists and contains files."""
        model_dir = self.models_path / model_name
        if not model_dir.exists():
            return False
        # Basic check: should contain some files (like model.bin, config.json)
        return any(model_dir.iterdir())

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

        logger.info(f"Starting download of model: {model_name}")

        # Temporarily allow network (HF_HUB_OFFLINE may be set at startup
        # to prevent hangs during model loading, but downloads need it)
        old_offline = os.environ.pop("HF_HUB_OFFLINE", None)

        try:
            faster_whisper.utils.download_model(
                model_name,
                output_dir=str(self.models_path / model_name)
            )
            logger.info(f"Successfully downloaded model: {model_name}")
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
            except Exception as e:
                raise SySubsError(f"Failed to delete model directory '{model_name}': {e}")
        else:
            logger.warning(f"Attempted to delete non-existent model: {model_name}")
