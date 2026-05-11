import json
import threading
from pathlib import Path
from constants import APPDATA_DIR, CONFIG_PATH, DEFAULT_CONFIG

class ConfigManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ConfigManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.lock = threading.Lock()
        self.config = {}
        
        # Ensure directories exist
        APPDATA_DIR.mkdir(parents=True, exist_ok=True)
        (APPDATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
        
        self._load_config()
        self._initialized = True

    @classmethod
    def get_instance(cls):
        return cls()

    def _load_config(self):
        """Loads config from disk or creates it with defaults."""
        if not CONFIG_PATH.exists():
            self.config = DEFAULT_CONFIG.copy()
            self._save_config()
            return

        try:
            with open(CONFIG_PATH, "r") as f:
                loaded_config = json.load(f)
                # Merge with DEFAULT_CONFIG to ensure new keys are present
                self.config = DEFAULT_CONFIG.copy()
                self.config.update(loaded_config)
        except (json.JSONDecodeError, OSError) as e:
            # log warning here once LogManager is ready, for now print
            print(f"Warning: Failed to load config: {e}. Resetting to defaults.")
            self.reset()

    def _save_config(self):
        """Writes current in-memory config to disk."""
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.config, f, indent=2)
        except OSError as e:
            print(f"Error: Failed to save config: {e}")

    def get(self, key: str, default=None):
        """Thread-safe read from config."""
        with self.lock:
            return self.config.get(key, default)

    def set(self, key: str, value):
        """Thread-safe update and write to disk."""
        with self.lock:
            self.config[key] = value
            self._save_config()

    def reset(self):
        """Overwrites config with defaults and writes to disk."""
        with self.lock:
            self.config = DEFAULT_CONFIG.copy()
            self._save_config()
