"""Tests for services/model_service.py — download/delete/active-model guard."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import model_service as ms
from constants import MODEL_REGISTRY


class FakeFasterWhisper:
    """Stands in for the `faster_whisper` module during downloads."""

    def __init__(self, raise_on_download=None):
        self.calls = []
        self._raise = raise_on_download
        holder = self

        class WhisperModel:
            @staticmethod
            def download_model(model_name, output_dir):
                holder._download(model_name, output_dir)

        self.WhisperModel = WhisperModel

    def _download(self, model_name, output_dir):
        self.calls.append((model_name, output_dir))
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        (Path(output_dir) / "model.bin").write_bytes(b"fake")
        if self._raise:
            raise self._raise


class FakeLegacyFasterWhisper:
    """Old faster-whisper without the WhisperModel.download_model classmethod."""

    def __init__(self):
        self.calls = []
        holder = self

        class WhisperModel:
            pass

        self.WhisperModel = WhisperModel
        self.utils = SimpleNamespace(
            download_model=lambda model_name, output_dir: (
                holder.calls.append((model_name, output_dir)),
                Path(output_dir).mkdir(parents=True, exist_ok=True),
                (Path(output_dir) / "model.bin").write_bytes(b"fake"),
            )
        )


@pytest.fixture
def service(tmp_path):
    fake_config = SimpleNamespace(get=lambda key, default=None: "tiny")
    instance = ms.ModelService(fake_config)
    instance.models_path = tmp_path
    return instance


def test_is_downloaded_missing_dir(service):
    assert service.is_downloaded("small") is False


def test_is_downloaded_empty_dir(service, tmp_path):
    (tmp_path / "small").mkdir()
    assert service.is_downloaded("small") is False


def test_is_downloaded_with_files(service, tmp_path):
    model_dir = tmp_path / "small"
    model_dir.mkdir()
    (model_dir / "model.bin").write_bytes(b"x")
    assert service.is_downloaded("small") is True


def test_is_downloaded_empty_model_bin(service, tmp_path):
    model_dir = tmp_path / "small"
    model_dir.mkdir()
    (model_dir / "model.bin").write_bytes(b"")
    assert service.is_downloaded("small") is False


def test_is_downloaded_partial_download(service, tmp_path):
    # Interrupted download: leftover files but no model.bin
    model_dir = tmp_path / "small"
    model_dir.mkdir()
    (model_dir / "tokenizer.json").write_bytes(b"{}")
    (model_dir / ".cache").mkdir()
    assert service.is_downloaded("small") is False


def test_list_models_includes_registry_and_status(service, tmp_path):
    (tmp_path / "tiny").mkdir()
    (tmp_path / "tiny" / "model.bin").write_bytes(b"x")
    models = service.list_models()
    by_name = {m["name"]: m for m in models}
    assert set(by_name) == set(MODEL_REGISTRY)
    assert by_name["tiny"]["downloaded"] is True
    assert by_name["small"]["downloaded"] is False
    assert by_name["tiny"]["size_mb"] == MODEL_REGISTRY["tiny"]["size_mb"]
    assert by_name["large-v3"]["multilingual"] is True


def test_download_skips_when_already_downloaded(service, tmp_path, monkeypatch):
    (tmp_path / "tiny").mkdir()
    (tmp_path / "tiny" / "model.bin").write_bytes(b"x")
    fw = FakeFasterWhisper()
    monkeypatch.setattr(ms, "faster_whisper", fw)
    service.download("tiny")
    assert fw.calls == []


def test_download_rejects_unknown_model(service, monkeypatch):
    fw = FakeFasterWhisper()
    monkeypatch.setattr(ms, "faster_whisper", fw)
    with pytest.raises(ms.SySubsError, match="not in the registry"):
        service.download("gpt-4")


def test_download_without_faster_whisper(service, monkeypatch):
    monkeypatch.setattr(ms, "faster_whisper", None)
    with pytest.raises(ms.SySubsError, match="not installed"):
        service.download("tiny")


def test_download_success_uses_classmethod(service, monkeypatch):
    fw = FakeFasterWhisper()
    monkeypatch.setattr(ms, "faster_whisper", fw)
    service.download("small")
    assert fw.calls == [("small", str(service.models_path / "small"))]


def test_download_legacy_fallback_uses_utils(service, monkeypatch):
    fw = FakeLegacyFasterWhisper()
    monkeypatch.setattr(ms, "faster_whisper", fw)
    service.download("small")
    assert fw.calls == [("small", str(service.models_path / "small"))]


def test_download_permission_error_becomes_actionable(service, monkeypatch):
    fw = FakeFasterWhisper(raise_on_download=PermissionError("access denied"))
    monkeypatch.setattr(ms, "faster_whisper", fw)
    with pytest.raises(ms.SySubsError, match="Permission denied"):
        service.download("small")


def test_download_failure_cleans_up_partial_dir(service, tmp_path, monkeypatch):
    def failing_download(model_name, output_dir):
        (service.models_path / model_name).mkdir(parents=True, exist_ok=True)
        raise RuntimeError("network down")

    fw = FakeFasterWhisper()
    fw._download = failing_download
    monkeypatch.setattr(ms, "faster_whisper", fw)
    with pytest.raises(ms.SySubsError, match="Failed to download"):
        service.download("small")
    assert not (tmp_path / "small").exists()


def test_download_restores_hf_offline_env(service, monkeypatch):
    fw = FakeFasterWhisper()
    monkeypatch.setattr(ms, "faster_whisper", fw)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    service.download("small")
    assert os.environ.get("HF_HUB_OFFLINE") == "1"


def test_download_clears_env_when_it_was_absent(service, monkeypatch):
    fw = FakeFasterWhisper()
    monkeypatch.setattr(ms, "faster_whisper", fw)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    service.download("small")
    assert "HF_HUB_OFFLINE" not in os.environ


def test_delete_removes_model_dir(service, tmp_path):
    model_dir = tmp_path / "small"
    model_dir.mkdir()
    (model_dir / "model.bin").write_bytes(b"x")
    service.delete("small")
    assert not model_dir.exists()


def test_delete_blocks_active_model(service, tmp_path):
    # fake config returns "tiny" as the active model
    model_dir = tmp_path / "tiny"
    model_dir.mkdir()
    (model_dir / "model.bin").write_bytes(b"x")
    with pytest.raises(ms.SySubsError, match="currently active"):
        service.delete("tiny")
    assert model_dir.exists()


def test_delete_missing_model_is_quiet(service):
    service.delete("nope")  # must not raise
