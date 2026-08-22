"""Tests for infra/errors.py — error hierarchy and friendly_error_message."""

import pytest

from infra.errors import (
    SySubsBaseError,
    AudioExtractionError,
    TranscriptionError,
    ModelError,
    friendly_error_message,
)


class TestSySubsBaseError:
    def test_message_stored(self):
        e = SySubsBaseError("something broke")
        assert e.message == "something broke"

    def test_str_returns_message(self):
        e = SySubsBaseError("something broke")
        assert str(e) == "something broke"


class TestAudioExtractionError:
    def test_is_base_error(self):
        e = AudioExtractionError("no audio")
        assert isinstance(e, SySubsBaseError)

    def test_message(self):
        e = AudioExtractionError("no audio")
        assert e.message == "no audio"


class TestTranscriptionError:
    def test_is_base_error(self):
        e = TranscriptionError("failed")
        assert isinstance(e, SySubsBaseError)


class TestModelError:
    def test_is_base_error(self):
        e = ModelError("bad model")
        assert isinstance(e, SySubsBaseError)


class TestFriendlyErrorMessage:
    def test_base_error_returns_message(self):
        e = SySubsBaseError("user message")
        assert friendly_error_message(e) == "user message"

    def test_import_error(self):
        e = ImportError("faster_whisper")
        result = friendly_error_message(e)
        assert "Missing dependency" in result

    def test_permission_error(self):
        e = PermissionError("denied")
        result = friendly_error_message(e)
        assert "Permission denied" in result

    def test_file_not_found_error(self):
        e = FileNotFoundError("missing.mp4")
        result = friendly_error_message(e)
        assert "File not found" in result

    def test_generic_exception(self):
        e = RuntimeError("weird bug")
        result = friendly_error_message(e)
        assert "Unexpected error" in result
        assert "weird bug" in result
