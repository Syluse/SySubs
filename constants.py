import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SUPPORTED_VIDEO_FORMATS = [".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"]
SUPPORTED_AUDIO_FORMATS = [".mp3", ".wav", ".aac", ".flac", ".m4a", ".ogg"]
SUPPORTED_FORMATS = SUPPORTED_VIDEO_FORMATS + SUPPORTED_AUDIO_FORMATS

APP_VERSION = "1.2.0"
GITHUB_URL = "https://github.com/syluse/SySubs"

MODEL_REGISTRY = {
    "tiny":     {"size_mb": 75,   "vram_gb": 1,  "ram_gb": 1,  "tier": "Fast: good for most computers",         "multilingual": False},
    "base":     {"size_mb": 145,  "vram_gb": 1,  "ram_gb": 1,  "tier": "Fast: good for most computers",         "multilingual": False},
    "small":    {"size_mb": 466,  "vram_gb": 2,  "ram_gb": 2,  "tier": "Balanced: good accuracy and speed",     "multilingual": False},
    "medium":   {"size_mb": 1500, "vram_gb": 5,  "ram_gb": 5,  "tier": "Accurate: needs a capable computer",    "multilingual": False},
    "large-v3": {"size_mb": 3100, "vram_gb": 10, "ram_gb": 10, "tier": "Most accurate: needs strong hardware",  "multilingual": True},
}

@dataclass
class Preset:
    mode: str = "words"
    value: int = 2
    max_lines: int = 1
    long_word_threshold: int = 10
    max_gap: float = 0.05
    text_transform: str = "none"
    strip_punctuation: bool = False
    show_language_tags: bool = False

PRESETS: dict[str, Preset] = {
    "short-form":   Preset(mode="words", value=2, max_lines=1, long_word_threshold=10, max_gap=0.05),
    "landscape":    Preset(mode="chars", value=42, max_lines=2, max_gap=0.8),
    "custom":       Preset(mode="words", value=2, max_lines=1, max_gap=0.5),
}

DEFAULT_CONFIG = {
    "model": "tiny",
    "device": "auto",
    "compute_type": "auto",
    "language": None,
    "multilingual": False,
    "lang_detect_threshold": 0.5,
    "lang_detect_segments": 1,
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

MIN_GAP_SECONDS = 0.01
UI_POLL_MS = 100
DOWNLOAD_POLL_MS = 250
PROGRESS_COOLDOWN_S = 0.5
WORKER_JOIN_TIMEOUT_S = 5
MODEL_DOWNLOAD_TIMEOUT_S = 1800
WINDOW_MIN_W = 850
WINDOW_MIN_H = 500
