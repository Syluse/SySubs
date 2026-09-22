"""Guards against tkinter's inherited config() method being shadowed.

MainWindow and ModelManagerWindow must never assign an attribute named
`self.config` — that name collides with tkinter's widget-configuration
method (analysis issue #4). The config manager is exposed as
`self.config_mgr` instead.
"""
import re
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent / "ui"


def _assert_no_config_shadow(path: Path):
    source = path.read_text(encoding="utf-8")
    match = re.search(r"self\.config\b", source)
    assert match is None, (
        f"{path.name}: found `self.config` (shadows tkinter config()): "
        f"{source[match.start():match.end() + 40]!r} — use `self.config_mgr`"
    )


def test_main_window_does_not_shadow_config():
    _assert_no_config_shadow(UI_DIR / "main_window.py")


def test_model_manager_window_does_not_shadow_config():
    _assert_no_config_shadow(UI_DIR / "model_manager.py")
