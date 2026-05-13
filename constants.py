import os
from pathlib import Path

SUPPORTED_VIDEO_FORMATS = [".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"]
SUPPORTED_AUDIO_FORMATS = [".mp3", ".wav", ".aac", ".flac", ".m4a", ".ogg"]
SUPPORTED_FORMATS = SUPPORTED_VIDEO_FORMATS + SUPPORTED_AUDIO_FORMATS

APP_VERSION = "1.0.0"
GITHUB_URL = "https://github.com/syluse/SySubs"

MODEL_REGISTRY = {
    "tiny":     {"size_mb": 75,   "vram_gb": 1,  "ram_gb": 1,  "tier": "Fast: good for most computers"},
    "base":     {"size_mb": 145,  "vram_gb": 1,  "ram_gb": 1,  "tier": "Fast: good for most computers"},
    "small":    {"size_mb": 466,  "vram_gb": 2,  "ram_gb": 2,  "tier": "Balanced: good accuracy and speed"},
    "medium":   {"size_mb": 1500, "vram_gb": 5,  "ram_gb": 5,  "tier": "Accurate: needs a capable computer"},
    "large-v3": {"size_mb": 3100, "vram_gb": 10, "ram_gb": 10, "tier": "Most accurate: needs strong hardware"},
}

PRESETS = {
    "short-form": {"mode": "words", "value": 2, "max_lines": 1, "long_word_threshold": 10, "max_gap": 0.05},
    "landscape":  {"mode": "chars", "value": 42, "max_lines": 2, "max_gap": 0.8},
    "custom":     {"mode": "words", "value": 2, "max_lines": 1, "max_gap": 0.5},
}

DEFAULT_CONFIG = {
    "model": "tiny",
    "device": "auto",
    "compute_type": "auto",
    "language": None,
    "preset": "short-form",
    "custom_mode": "words",
    "custom_value": 2,
    "custom_max_lines": 1,
    "custom_max_gap": 0.05,
    "last_export_folder": None,
    "text_transform": "none",
    "strip_punctuation": False,
    "window_width": 950,
    "window_height": 700,
    "window_x": None,
    "window_y": None,
}

# AppData path resolution
APPDATA_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "SySubs"
CONFIG_PATH = APPDATA_DIR / "config.json"
LOG_PATH = APPDATA_DIR / "logs" / "sysubs.log"
LOG_MAX_BYTES = 1 * 1024 * 1024  # 1MB
