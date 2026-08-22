"""Tests for infra/config_manager.py — defaults, merge, corruption, thread-safety, validation."""

import json
import threading

import pytest

from infra import config_manager as cm
from constants import DEFAULT_CONFIG


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "APPDATA_DIR", tmp_path)
    monkeypatch.setattr(cm, "CONFIG_PATH", tmp_path / "config.json")
    cm.ConfigManager._instance = None
    instance = cm.ConfigManager.get_instance()
    yield instance
    cm.ConfigManager._instance = None


def test_creates_defaults_on_first_run(cfg, tmp_path):
    assert cfg.config == DEFAULT_CONFIG
    assert (tmp_path / "config.json").exists()


def test_loads_existing_config(cfg, tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"model": "small", "custom_value": 7}),
        encoding="utf-8",
    )
    cm.ConfigManager._instance = None
    fresh = cm.ConfigManager.get_instance()
    assert fresh.get("model") == "small"
    assert fresh.get("custom_value") == 7
    # Missing keys still get defaults
    assert fresh.get("multilingual") == DEFAULT_CONFIG["multilingual"]


def test_corrupted_config_resets_to_defaults(cfg, tmp_path):
    (tmp_path / "config.json").write_text("{ not valid json !!!", encoding="utf-8")
    cm.ConfigManager._instance = None
    fresh = cm.ConfigManager.get_instance()
    assert fresh.config == DEFAULT_CONFIG


def test_get_returns_default_when_missing(cfg):
    assert cfg.get("nope", "fallback") == "fallback"
    assert cfg.get("nope") is None


def test_set_persists_to_disk(cfg, tmp_path):
    cfg.set("model", "medium")
    on_disk = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert on_disk["model"] == "medium"


def test_reset_restores_defaults(cfg):
    cfg.set("model", "large-v3")
    cfg.set("custom_value", 42)
    cfg.reset()
    assert cfg.config == DEFAULT_CONFIG
    assert cfg.get("model") == "tiny"


def test_singleton_returns_same_instance():
    assert cm.ConfigManager.get_instance() is cm.ConfigManager.get_instance()


def test_concurrent_sets_are_thread_safe(cfg):
    def writer(i):
        for j in range(20):
            cfg.set(f"key_{i}", i * 100 + j)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for i in range(8):
        value = cfg.get(f"key_{i}")
        assert value is not None and 0 <= value % 100 < 20
    # Disk stays valid JSON after concurrent writes
    from infra.config_manager import CONFIG_PATH
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["model"] == cfg.get("model")


# ------------------------------------------------------------- validation


@pytest.fixture
def cfg_file(tmp_path):
    return tmp_path / "config.json"


def test_unknown_keys_are_dropped(tmp_path, cfg_file, monkeypatch):
    cfg_file.write_text(json.dumps({
        "model": "tiny",
        "unknown_key": "garbage",
        "another_bad_one": 123,
    }))
    monkeypatch.setattr(cm, "APPDATA_DIR", tmp_path)
    monkeypatch.setattr(cm, "CONFIG_PATH", cfg_file)
    cm.ConfigManager._instance = None

    fresh = cm.ConfigManager.get_instance()
    assert fresh.get("model") == "tiny"
    assert fresh.get("unknown_key") is None
    assert fresh.get("another_bad_one") is None
    cm.ConfigManager._instance = None


def test_type_coercion(tmp_path, cfg_file, monkeypatch):
    cfg_file.write_text(json.dumps({
        "custom_value": "5",
        "strip_punctuation": 1,
        "multilingual": "yes",
    }))
    monkeypatch.setattr(cm, "APPDATA_DIR", tmp_path)
    monkeypatch.setattr(cm, "CONFIG_PATH", cfg_file)
    cm.ConfigManager._instance = None

    fresh = cm.ConfigManager.get_instance()
    assert fresh.get("custom_value") == 5
    assert fresh.get("strip_punctuation") is True
    assert fresh.get("multilingual") is True
    cm.ConfigManager._instance = None


def test_invalid_numeric_uses_default(tmp_path, cfg_file, monkeypatch):
    cfg_file.write_text(json.dumps({
        "custom_value": "not_a_number",
    }))
    monkeypatch.setattr(cm, "APPDATA_DIR", tmp_path)
    monkeypatch.setattr(cm, "CONFIG_PATH", cfg_file)
    cm.ConfigManager._instance = None

    fresh = cm.ConfigManager.get_instance()
    assert fresh.get("custom_value") == 2
    cm.ConfigManager._instance = None
