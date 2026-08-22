"""Tests for services/model_cache.py — LRU eviction, cache hits, clear."""

import pytest

from services import model_cache as mc


@pytest.fixture(autouse=True)
def _clear_cache():
    mc.ModelCache.clear()
    yield
    mc.ModelCache.clear()


class TestLruEviction:
    def test_evicts_oldest_when_full(self, monkeypatch):
        call_count = 0

        class FakeModel:
            def __init__(self, key):
                self.key = key

        def fake_whisper_model(model_dir, device, compute_type, **kwargs):
            nonlocal call_count
            call_count += 1
            return FakeModel((model_dir, device, compute_type))

        monkeypatch.setattr(mc, "WhisperModel", fake_whisper_model)

        mc.ModelCache.get("md1", "cpu", "int8")
        mc.ModelCache.get("md1", "cuda", "float16")
        assert call_count == 2
        assert len(mc.ModelCache._models) == 2

        mc.ModelCache.get("md1", "cpu", "int8")

        mc.ModelCache.get("md2", "cpu", "int8")
        assert call_count == 3
        assert len(mc.ModelCache._models) == 2

        keys = list(mc.ModelCache._models.keys())
        assert ("md2", "cpu", "int8") in keys
        assert ("md1", "cpu", "int8") in keys
        assert ("md1", "cuda", "float16") not in keys


class TestCacheHit:
    def test_same_key_no_reload(self, monkeypatch):
        call_count = 0

        def fake_whisper_model(model_dir, device, compute_type, **kwargs):
            nonlocal call_count
            call_count += 1
            return object()

        monkeypatch.setattr(mc, "WhisperModel", fake_whisper_model)

        model1 = mc.ModelCache.get("md", "cpu", "int8")
        model2 = mc.ModelCache.get("md", "cpu", "int8")
        assert model1 is model2
        assert call_count == 1


class TestClear:
    def test_clear_drops_all(self, monkeypatch):
        monkeypatch.setattr(mc, "WhisperModel", lambda *a, **k: object())

        mc.ModelCache.get("md1", "cpu", "int8")
        mc.ModelCache.get("md2", "cpu", "int8")
        assert len(mc.ModelCache._models) == 2

        mc.ModelCache.clear()
        assert len(mc.ModelCache._models) == 0


class TestImportError:
    def test_raises_when_faster_whisper_missing(self, monkeypatch):
        monkeypatch.setattr(mc, "WhisperModel", None)

        with pytest.raises(ImportError, match="faster-whisper is not installed"):
            mc.ModelCache.get("md", "cpu", "int8")
