"""Model delete must not run on the UI thread (analysis issue #5).

`ModelService.delete` does a shutil.rmtree of up to ~3GB; calling it from
`ModelManagerWindow._delete_model` froze the window. The delete now runs
on a daemon worker thread and results drain through the window's poll
loop (same pattern as downloads).
"""
import threading
import time

import pytest

from services.model_service import SySubsError
from ui.model_manager import ModelManagerWindow


class FakeWidget:
    def __init__(self):
        self.calls = []

    def configure(self, **kwargs):
        self.calls.append(kwargs)


class FakeService:
    def __init__(self, exc=None, delay=0.05):
        self.exc = exc
        self.delay = delay
        self.thread_names = []

    def delete(self, model_name):
        self.thread_names.append(threading.current_thread().name)
        time.sleep(self.delay)
        if self.exc:
            raise self.exc


def make_window(service):
    """Build a ModelManagerWindow without touching tkinter."""
    win = object.__new__(ModelManagerWindow)
    win.model_service = service
    win.config_mgr = None
    win.on_change_callback = None
    win.rows = {
        "tiny": {
            "frame": None,
            "status_label": FakeWidget(),
            "dl_btn": FakeWidget(),
            "del_btn": FakeWidget(),
        }
    }
    win._deleting = set()
    win.delete_queues = {}
    win.download_queues = {}
    win._downloading = set()
    win._download_started = {}
    win.rendered = False
    win._render_models = lambda: setattr(win, "rendered", True)
    win.after_calls = []
    win.after = lambda delay, fn=None: win.after_calls.append((delay, fn))
    return win


def _drain(win, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and (win.delete_queues or win._deleting):
        win._poll_async()
        time.sleep(0.02)


def test_delete_runs_off_ui_thread():
    service = FakeService()
    win = make_window(service)

    win._delete_model("tiny")  # must return immediately, not block on rmtree

    deadline = time.monotonic() + 2.0
    while not service.thread_names and time.monotonic() < deadline:
        time.sleep(0.01)

    assert service.thread_names, "delete worker never ran"
    assert service.thread_names[0] != threading.current_thread().name, (
        f"model_service.delete ran on {service.thread_names[0]} — UI thread would freeze"
    )

    changed = []
    win.on_change_callback = lambda: changed.append(True)
    _drain(win)
    assert win.rendered, "success path should re-render the model list"
    assert changed, "success path should fire on_change_callback"


def test_delete_error_surfaces_inline_and_restores_button(monkeypatch):
    service = FakeService(exc=SySubsError("disk is locked"))
    win = make_window(service)
    boxes = []
    monkeypatch.setattr(
        "ui.model_manager.messagebox.showerror",
        lambda title, msg: boxes.append((title, msg)),
    )

    win._delete_model("tiny")
    _drain(win)

    assert boxes and "disk is locked" in boxes[0][1]
    assert any(c.get("text_color") == "red" for c in win.rows["tiny"]["status_label"].calls)
    assert "tiny" not in win._deleting
    assert "tiny" not in win.delete_queues
    # delete button re-enabled after failure (it was disabled when queued)
    assert any(c.get("state") == "normal" for c in win.rows["tiny"]["del_btn"].calls)


def test_delete_is_idempotent_while_in_flight():
    service = FakeService(delay=0.3)
    win = make_window(service)

    win._delete_model("tiny")
    win._delete_model("tiny")  # second click while first is running

    assert len(service.thread_names) <= 1, "duplicate delete threads spawned"
    _drain(win, timeout=3.0)
