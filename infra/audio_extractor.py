import os
import subprocess
import sys
import uuid
import re
import logging
from pathlib import Path

logger = logging.getLogger("sysubs")

class AudioExtractionError(Exception):
    """Custom exception for audio extraction failures."""
    pass

def get_ffmpeg_path() -> str:
    """Resolves the ffmpeg binary path, supporting frozen bundles and dev environments."""
    if getattr(sys, 'frozen', False):
        # Frozen onedir: ffmpeg sits next to the executable
        exe_dir = Path(sys.executable).parent
        exe_ffmpeg = exe_dir / "ffmpeg.exe"
        if exe_ffmpeg.exists():
            return str(exe_ffmpeg)

    # Portable / dev: check next to the script entry point
    try:
        script_dir = Path(sys.argv[0]).resolve().parent
        exe_ffmpeg = script_dir / "ffmpeg.exe"
        if exe_ffmpeg.exists():
            return str(exe_ffmpeg)
    except Exception:
        pass

    # Fallback to PATH for dev environment
    return "ffmpeg"

def probe_duration(input_path: str):
    """Returns the media duration in seconds, or None if it cannot be determined.

    Duration probing is best-effort: some containers/streams don't report it,
    so a probe failure must not abort transcription.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    ffmpeg_exe = get_ffmpeg_path()
    try:
        # ffmpeg outputs info to stderr
        result = subprocess.run(
            [ffmpeg_exe, "-i", input_path],
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning(f"ffmpeg probe failed: {e}")
        return None

    # Look for "Duration: 00:00:00.00" (seconds fraction optional)
    match = re.search(r"Duration:\s+(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if match:
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    # Fallback to ffprobe when available
    if ffmpeg_exe != "ffmpeg":
        ffprobe_exe = str(Path(ffmpeg_exe).with_name("ffprobe.exe"))
    else:
        ffprobe_exe = "ffprobe"
    try:
        probe = subprocess.run(
            [ffprobe_exe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", input_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        duration = probe.stdout.strip()
        if duration:
            return float(duration)
    except (subprocess.SubprocessError, FileNotFoundError, ValueError) as e:
        logger.warning(f"ffprobe fallback failed: {e}")

    logger.warning("Could not determine media duration from ffmpeg output.")
    return None

def extract(input_path: str) -> str:
    """Converts input file to 16kHz mono WAV in %TEMP%."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    ffmpeg_exe = get_ffmpeg_path()
    temp_dir = Path(os.environ.get("TEMP", os.environ.get("TMP", "/tmp")))
    output_path = temp_dir / f"sysubs_{uuid.uuid4()}.wav"
    
    # Command: 16kHz, mono, WAV
    cmd = [
        ffmpeg_exe, "-y",
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        str(output_path)
    ]
    
    try:
        result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
        if result.returncode != 0:
            raise AudioExtractionError(f"ffmpeg extraction failed (exit {result.returncode}): {result.stderr}")
        return str(output_path)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        raise AudioExtractionError(f"ffmpeg execution failed: {e}")
