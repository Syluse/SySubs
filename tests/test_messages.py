"""Tests for services/messages.py — typed worker message dataclasses."""

import pytest

from services import messages as msg


class TestProgressMessage:
    def test_defaults(self):
        m = msg.ProgressMessage()
        assert m.type == "progress"
        assert m.elapsed == 0.0
        assert m.total is None

    def test_custom_values(self):
        m = msg.ProgressMessage(elapsed=5.0, total=10.0)
        assert m.elapsed == 5.0
        assert m.total == 10.0


class TestLogMessage:
    def test_defaults(self):
        m = msg.LogMessage()
        assert m.type == "log"
        assert m.message == ""

    def test_custom_message(self):
        m = msg.LogMessage(message="hello")
        assert m.message == "hello"


class TestPhaseMessage:
    def test_defaults(self):
        m = msg.PhaseMessage()
        assert m.type == "phase"
        assert m.phase == ""
        assert m.message == ""

    def test_custom_values(self):
        m = msg.PhaseMessage(phase="load", message="loading...")
        assert m.phase == "load"
        assert m.message == "loading..."


class TestResultMessage:
    def test_defaults(self):
        m = msg.ResultMessage()
        assert m.type == "result"
        assert m.srt == ""

    def test_custom_srt(self):
        m = msg.ResultMessage(srt="content")
        assert m.srt == "content"


class TestCancelledMessage:
    def test_defaults(self):
        m = msg.CancelledMessage()
        assert m.type == "cancelled"


class TestErrorMessage:
    def test_defaults(self):
        m = msg.ErrorMessage()
        assert m.type == "error"
        assert m.message == ""

    def test_custom_message(self):
        m = msg.ErrorMessage(message="oops")
        assert m.message == "oops"


class TestIsinstanceChecks:
    def test_progress_is_progress(self):
        assert isinstance(msg.ProgressMessage(), msg.ProgressMessage)

    def test_log_is_log(self):
        assert isinstance(msg.LogMessage(), msg.LogMessage)

    def test_phase_is_phase(self):
        assert isinstance(msg.PhaseMessage(), msg.PhaseMessage)

    def test_result_is_result(self):
        assert isinstance(msg.ResultMessage(), msg.ResultMessage)

    def test_cancelled_is_cancelled(self):
        assert isinstance(msg.CancelledMessage(), msg.CancelledMessage)

    def test_error_is_error(self):
        assert isinstance(msg.ErrorMessage(), msg.ErrorMessage)
