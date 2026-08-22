"""Tests for infra/audio_extractor.py — ffmpeg command construction, duration parsing."""

import subprocess

import pytest

from infra import audio_extractor as ae
from infra.audio_extractor import AudioExtractionError


class FakeResult:
    def __init__(self, returncode=0, stderr="", stdout=""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


@pytest.fixture
def media_file(tmp_path):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"")
    return str(path)


# ------------------------------------------------------------- ffmpeg path

def test_get_ffmpeg_path_finds_exe_next_to_script(monkeypatch, tmp_path):
    exe = tmp_path / "ffmpeg.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr("sys.argv", [str(tmp_path / "main.py")])
    assert ae.get_ffmpeg_path() == str(exe)


def test_get_ffmpeg_path_falls_back_to_path(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", [str(tmp_path / "main.py")])
    assert ae.get_ffmpeg_path() == "ffmpeg"


# ------------------------------------------------------------- probe_duration

def test_probe_duration_parses_ffmpeg_output(monkeypatch, media_file):
    monkeypatch.setattr(
        ae.subprocess, "run",
        lambda *a, **k: FakeResult(stderr="  Duration: 00:01:02.50, start: 0.000000"),
    )
    assert ae.probe_duration(media_file) == 62.5


def test_probe_duration_accepts_seconds_without_fraction(monkeypatch, media_file):
    monkeypatch.setattr(
        ae.subprocess, "run",
        lambda *a, **k: FakeResult(stderr="Duration: 00:00:05, bitrate: 1"),
    )
    assert ae.probe_duration(media_file) == 5.0


def test_probe_duration_falls_back_to_ffprobe(monkeypatch, media_file):
    def fake_run(cmd, **kwargs):
        if "-i" in cmd:
            return FakeResult(stderr="no duration here")
        return FakeResult(stdout="123.4\n")

    monkeypatch.setattr(ae.subprocess, "run", fake_run)
    assert ae.probe_duration(media_file) == 123.4


def test_probe_duration_returns_none_when_all_fail(monkeypatch, media_file):
    def fake_run(cmd, **kwargs):
        if "-i" in cmd:
            return FakeResult(stderr="garbage")
        return FakeResult(stdout="")

    monkeypatch.setattr(ae.subprocess, "run", fake_run)
    assert ae.probe_duration(media_file) is None


def test_probe_duration_missing_input_raises():
    with pytest.raises(FileNotFoundError):
        ae.probe_duration("does_not_exist.mp4")


def test_probe_duration_swallows_subprocess_errors(monkeypatch, media_file):
    def boom(cmd, **kwargs):
        raise subprocess.SubprocessError("nope")

    monkeypatch.setattr(ae.subprocess, "run", boom)
    assert ae.probe_duration(media_file) is None


# ------------------------------------------------------------- extract

def test_extract_builds_correct_ffmpeg_command(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMP", str(tmp_path))
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeResult()

    monkeypatch.setattr(ae.subprocess, "run", fake_run)
    out = ae.extract(str(source))

    cmd = captured["cmd"]
    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    assert "-ar" in cmd and "16000" in cmd
    assert "-ac" in cmd and "1" in cmd
    assert "-f" in cmd and "wav" in cmd
    assert cmd[-1] == out
    assert out.endswith(".wav")


def test_extract_raises_on_ffmpeg_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMP", str(tmp_path))
    source = tmp_path / "input.mp4"
    source.write_bytes(b"")
    monkeypatch.setattr(
        ae.subprocess, "run",
        lambda *a, **k: FakeResult(returncode=1, stderr="invalid data"),
    )
    with pytest.raises(AudioExtractionError, match="exit 1"):
        ae.extract(str(source))


def test_extract_missing_input_raises():
    with pytest.raises(FileNotFoundError):
        ae.extract("does_not_exist.mp4")
