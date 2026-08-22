"""Tests for constants.py — Preset dataclass and named constants."""

import pytest

from constants import (
    Preset,
    PRESETS,
    MIN_GAP_SECONDS,
    UI_POLL_MS,
    DOWNLOAD_POLL_MS,
    PROGRESS_COOLDOWN_S,
    WORKER_JOIN_TIMEOUT_S,
)


class TestPresetDefaults:
    def test_mode(self):
        assert Preset().mode == "words"

    def test_value(self):
        assert Preset().value == 2

    def test_max_lines(self):
        assert Preset().max_lines == 1

    def test_long_word_threshold(self):
        assert Preset().long_word_threshold == 10

    def test_max_gap(self):
        assert Preset().max_gap == 0.05

    def test_text_transform(self):
        assert Preset().text_transform == "none"

    def test_strip_punctuation(self):
        assert Preset().strip_punctuation is False

    def test_show_language_tags(self):
        assert Preset().show_language_tags is False


class TestPresetsRegistry:
    def test_short_form_is_preset(self):
        assert isinstance(PRESETS["short-form"], Preset)

    def test_landscape_is_preset(self):
        assert isinstance(PRESETS["landscape"], Preset)

    def test_custom_is_preset(self):
        assert isinstance(PRESETS["custom"], Preset)

    def test_short_form_mode(self):
        assert PRESETS["short-form"].mode == "words"

    def test_short_form_value(self):
        assert PRESETS["short-form"].value == 2

    def test_landscape_mode(self):
        assert PRESETS["landscape"].mode == "chars"


class TestPresetMutable:
    def test_can_modify_attributes(self):
        p = PRESETS["short-form"]
        p.text_transform = "upper"
        p.strip_punctuation = True
        assert p.text_transform == "upper"
        assert p.strip_punctuation is True


class TestNamedConstants:
    def test_min_gap_seconds(self):
        assert MIN_GAP_SECONDS == 0.01

    def test_ui_poll_ms(self):
        assert UI_POLL_MS == 100

    def test_download_poll_ms(self):
        assert DOWNLOAD_POLL_MS == 250

    def test_progress_cooldown_s(self):
        assert PROGRESS_COOLDOWN_S == 0.5

    def test_worker_join_timeout_s(self):
        assert WORKER_JOIN_TIMEOUT_S == 5
