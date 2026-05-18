import os
import subprocess
import sys
import uuid
import re
from pathlib import Path

class AudioExtractionError(Exception):
    """Custom exception for audio extraction failures."""
    pass

def get_ffmpeg_path() -> str:
    """Resolves the ffmpeg binary path, supporting PyInstaller bundles and dev environments."""
    if getattr(sys, 'frozen', False):
        # PyInstaller onedir: ffmpeg sits next to .exe (spec: ('ffmpeg.exe', '.'))
        exe_dir = Path(sys.executable).parent
        exe_ffmpeg = exe_dir / "ffmpeg.exe"
        if exe_ffmpeg.exists():
            return str(exe_ffmpeg)
        # Fallback: check inside _internal/ (MEIPASS)
        if hasattr(sys, '_MEIPASS'):
            meipass_ffmpeg = Path(sys._MEIPASS) / "ffmpeg.exe"
            if meipass_ffmpeg.exists():
                return str(meipass_ffmpeg)

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

def probe_duration(input_path: str) -> float:
    """Runs ffmpeg -i and parses duration from stderr."""
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
        
        # Look for "Duration: 00:00:00.00"
        match = re.search(r"Duration:\s+(\d+):(\d+):(\d+\.\d+)", result.stderr)
        if match:
            hours, minutes, seconds = match.groups()
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            
        raise AudioExtractionError(f"Could not parse duration from ffmpeg output: {result.stderr[:200]}...")
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        raise AudioExtractionError(f"ffmpeg probe failed: {e}")

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
