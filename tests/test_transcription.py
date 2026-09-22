"""Tests for the transcription pipeline: load-phase abort, cleanup, worker messaging.

Regression coverage for analysis issue #1 (executor shutdown defeating
timeout/cancel) — the watchdog tests fail if run() blocks joining a stuck
model-load thread.
"""
import queue
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from constants import Preset
from infra.errors import TranscriptionError
from services.transcription import (
    TranscriptionCancelledError,
    TranscriptionService,
    TranscriptionWorker,
)
from services.messages import (
    CancelledMessage,
    ErrorMessage,
    LogMessage,
    PhaseMessage,
    ProgressMessage,
    ResultMessage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_word(start=0.0, end=0.5, word="hello"):
    return SimpleNamespace(start=start, end=end, word=word)


def make_segment(text="hello", start=0.0, end=1.0, words=None, language="en"):
    return SimpleNamespace(
        text=text,
        language=language,
        end=end,
        words=[make_word(start, end, text)] if words is None else words,
    )


class FakeModel:
    def __init__(self, segments=None, transcribe_exc=None):
        self.segments = segments if segments is not None else [make_segment()]
        self.transcribe_exc = transcribe_exc
        self.calls = []

    def transcribe(self, wav_path, **kwargs):
        self.calls.append((wav_path, kwargs))
        if self.transcribe_exc is not None:
            raise self.transcribe_exc
        info = SimpleNamespace(language="en")
        return iter(self.segments), info


def stub_cache(monkeypatch, impl):
    """Patch services.transcription.ModelCache with impl(model_dir, device, compute_type)."""
    class _Cache:
        @staticmethod
        def get(model_dir, device=None, compute_type=None):
            return impl(model_dir, device, compute_type)

    monkeypatch.setattr("services.transcription.ModelCache", _Cache)


def install_extract(monkeypatch, wav_path: Path):
    def _extract(input_path):
        wav_path.write_bytes(b"RIFF-fake-wav")
        return str(wav_path)

    monkeypatch.setattr("services.transcription.extract", _extract)


def base_kwargs(tmp_path, **overrides):
    src = tmp_path / "input.mp4"
    src.write_bytes(b"fake")
    kwargs = dict(
        file_path=str(src),
        model_name="tiny",
        language=None,
        device_info=SimpleNamespace(device="cpu", compute_type="int8", cuda_available=False),
        models_path=tmp_path,
        progress_cb=lambda elapsed, total: None,
        stop_event=threading.Event(),
    )
    kwargs.update(overrides)
    return kwargs


def drain_with_watchdog(gen, timeout=3.0):
    """Consume the run() generator in a thread; fail if it doesn't finish in time.

    On the pre-fix code, timeout/cancel aborts blocked in
    ThreadPoolExecutor.__exit__ (shutdown(wait=True)) and this watchdog fails
    instead of hanging the suite.
    """
    outcome = {}

    def _target():
        try:
            outcome["result"] = list(gen)
        except BaseException as e:  # noqa: BLE001 — outcome plumbing
            outcome["error"] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout)
    assert not t.is_alive(), (
        "run() did not abort within the watchdog window — "
        "stuck joining the model-load thread?"
    )
    return outcome


@pytest.fixture
def load_gate():
    """A load that blocks until released; teardown always releases it."""
    started = threading.Event()
    gate = threading.Event()

    def impl(model_dir, device=None, compute_type=None):
        started.set()
        gate.wait(30)
        return FakeModel()

    yield {"started": started, "gate": gate, "impl": impl}
    gate.set()


@pytest.fixture
def wav_path(tmp_path):
    return tmp_path / "sysubs_test.wav"


# ---------------------------------------------------------------------------
# Load-phase abort (regression for issue #1)
# ---------------------------------------------------------------------------

def test_load_timeout_aborts_without_joining_stuck_thread(
    monkeypatch, tmp_path, wav_path, load_gate
):
    stub_cache(monkeypatch, load_gate["impl"])
    install_extract(monkeypatch, wav_path)
    monkeypatch.setattr("services.transcription.probe_duration", lambda p: 10.0)
    monkeypatch.setattr("services.transcription.MODEL_LOAD_TIMEOUT_S", 0.3)

    gen = TranscriptionService.run(**base_kwargs(tmp_path))
    start = time.monotonic()
    outcome = drain_with_watchdog(gen, timeout=2.5)
    elapsed = time.monotonic() - start

    assert isinstance(outcome.get("error"), TranscriptionError)
    assert elapsed < 2.0, f"timeout abort took {elapsed:.2f}s — load thread was joined"
    assert load_gate["started"].is_set()


def test_cancel_during_load_aborts_promptly(
    monkeypatch, tmp_path, wav_path, load_gate
):
    stub_cache(monkeypatch, load_gate["impl"])
    install_extract(monkeypatch, wav_path)
    monkeypatch.setattr("services.transcription.probe_duration", lambda p: 10.0)
    monkeypatch.setattr("services.transcription.MODEL_LOAD_TIMEOUT_S", 30)

    stop = threading.Event()
    stop.set()
    gen = TranscriptionService.run(**base_kwargs(tmp_path, stop_event=stop))

    start = time.monotonic()
    outcome = drain_with_watchdog(gen, timeout=2.5)
    elapsed = time.monotonic() - start

    assert isinstance(outcome.get("error"), TranscriptionCancelledError)
    assert elapsed < 2.0, f"cancel abort took {elapsed:.2f}s — load thread was joined"


# ---------------------------------------------------------------------------
# Cancel during transcription + temp WAV cleanup
# ---------------------------------------------------------------------------

def test_cancel_during_segments_raises_and_deletes_wav(
    monkeypatch, tmp_path, wav_path
):
    stop = threading.Event()
    model = FakeModel()

    def segments():
        yield make_segment(text="one", start=0.0, end=1.0)
        stop.set()
        yield make_segment(text="two", start=1.0, end=2.0)

    model.segments = segments()
    stub_cache(monkeypatch, lambda *a, **k: model)
    install_extract(monkeypatch, wav_path)
    monkeypatch.setattr("services.transcription.probe_duration", lambda p: 10.0)

    gen = TranscriptionService.run(**base_kwargs(tmp_path, stop_event=stop))
    outcome = drain_with_watchdog(gen, timeout=5.0)

    assert isinstance(outcome.get("error"), TranscriptionCancelledError)
    assert not wav_path.exists(), "temp WAV must be deleted on cancel"


def test_success_deletes_temp_wav(monkeypatch, tmp_path, wav_path):
    stub_cache(monkeypatch, lambda *a, **k: FakeModel())
    install_extract(monkeypatch, wav_path)
    monkeypatch.setattr("services.transcription.probe_duration", lambda p: 10.0)

    result = list(TranscriptionService.run(**base_kwargs(tmp_path)))

    assert len(result) == 1
    assert not wav_path.exists(), "temp WAV must be deleted on success"


def test_transcribe_error_deletes_temp_wav(monkeypatch, tmp_path, wav_path):
    model = FakeModel(transcribe_exc=RuntimeError("bad wav"))
    stub_cache(monkeypatch, lambda *a, **k: model)
    install_extract(monkeypatch, wav_path)
    monkeypatch.setattr("services.transcription.probe_duration", lambda p: 10.0)

    outcome = drain_with_watchdog(
        TranscriptionService.run(**base_kwargs(tmp_path)), timeout=5.0
    )

    assert isinstance(outcome.get("error"), RuntimeError)
    assert not wav_path.exists(), "temp WAV must be deleted on error"


# ---------------------------------------------------------------------------
# CUDA fallback / error propagation
# ---------------------------------------------------------------------------

def test_cuda_load_failure_falls_back_to_cpu(monkeypatch, tmp_path, wav_path):
    calls = []

    def impl(model_dir, device=None, compute_type=None):
        calls.append((device, compute_type))
        if device == "cuda":
            raise RuntimeError("cublas missing")
        return FakeModel()

    stub_cache(monkeypatch, impl)
    install_extract(monkeypatch, wav_path)
    monkeypatch.setattr("services.transcription.probe_duration", lambda p: 10.0)

    kwargs = base_kwargs(
        tmp_path,
        device_info=SimpleNamespace(device="cuda", compute_type="float16", cuda_available=True),
    )
    result = list(TranscriptionService.run(**kwargs))

    assert len(result) == 1
    assert calls == [("cuda", "float16"), ("cpu", "int8")]


def test_cpu_load_error_propagates(monkeypatch, tmp_path, wav_path):
    def impl(model_dir, device=None, compute_type=None):
        raise RuntimeError("model.bin corrupt")

    stub_cache(monkeypatch, impl)
    install_extract(monkeypatch, wav_path)
    monkeypatch.setattr("services.transcription.probe_duration", lambda p: 10.0)

    outcome = drain_with_watchdog(
        TranscriptionService.run(**base_kwargs(tmp_path)), timeout=5.0
    )

    assert isinstance(outcome.get("error"), RuntimeError)
    assert not wav_path.exists(), "temp WAV must be deleted when load fails"


# ---------------------------------------------------------------------------
# Segment filtering
# ---------------------------------------------------------------------------

def test_segments_without_words_are_not_yielded(monkeypatch, tmp_path, wav_path):
    no_words = make_segment(text="skip", words=None)
    no_words.words = None
    with_words = make_segment(text="keep")
    model = FakeModel(segments=[no_words, with_words])
    stub_cache(monkeypatch, lambda *a, **k: model)
    install_extract(monkeypatch, wav_path)
    monkeypatch.setattr("services.transcription.probe_duration", lambda p: 10.0)

    result = list(TranscriptionService.run(**base_kwargs(tmp_path)))

    assert result == [with_words]


# ---------------------------------------------------------------------------
# Worker message mapping
# ---------------------------------------------------------------------------

def run_worker(monkeypatch, tmp_path, fake_run, formatter=None):
    q = queue.Queue()
    stop = threading.Event()
    monkeypatch.setattr(TranscriptionService, "run", fake_run)
    worker = TranscriptionWorker(
        result_queue=q,
        stop_event=stop,
        file_path=str(tmp_path / "in.mp4"),
        model_name="tiny",
        language=None,
        device_info=SimpleNamespace(device="cpu", compute_type="int8", cuda_available=False),
        models_path=tmp_path,
        preset_config=Preset(),
        formatter_func=formatter or (lambda segs, preset: "SRT-OUTPUT"),
    )
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive(), "worker thread did not finish"
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue.Empty:
            break
    return items


def test_worker_success_sends_result_message(monkeypatch, tmp_path):
    def fake_run(**kwargs):
        return iter([make_segment()])

    items = run_worker(monkeypatch, tmp_path, fake_run)

    types = [type(m) for m in items]
    assert types == [PhaseMessage, LogMessage, ResultMessage]
    assert items[-1].srt == "SRT-OUTPUT"
    assert items[0].phase == "load"


def test_worker_error_sends_friendly_error_message(monkeypatch, tmp_path):
    def fake_run(**kwargs):
        raise ValueError("boom")

    items = run_worker(monkeypatch, tmp_path, fake_run)

    assert any(isinstance(m, ErrorMessage) for m in items)
    err = next(m for m in items if isinstance(m, ErrorMessage))
    assert err.message == "Unexpected error: boom"


def test_worker_cancel_sends_cancelled_message(monkeypatch, tmp_path):
    def fake_run(**kwargs):
        raise TranscriptionCancelledError()

    items = run_worker(monkeypatch, tmp_path, fake_run)

    assert any(isinstance(m, CancelledMessage) for m in items)


def test_worker_progress_cooldown_emits_single_progress(monkeypatch, tmp_path):
    def fake_run(**kwargs):
        cb = kwargs["progress_cb"]
        for i in range(5):
            cb(elapsed=float(i), total=10.0)
        return iter([])

    items = run_worker(monkeypatch, tmp_path, fake_run)

    progress = [m for m in items if isinstance(m, ProgressMessage)]
    assert len(progress) == 1, f"expected cooldown to drop rapid repeats, got {len(progress)}"
    assert progress[0].elapsed == 0.0
