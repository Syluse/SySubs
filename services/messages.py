from dataclasses import dataclass
from typing import Optional

@dataclass
class ProgressMessage:
    type: str = "progress"
    elapsed: float = 0.0
    total: Optional[float] = None

@dataclass
class LogMessage:
    type: str = "log"
    message: str = ""

@dataclass
class PhaseMessage:
    type: str = "phase"
    phase: str = ""
    message: str = ""

@dataclass
class ResultMessage:
    type: str = "result"
    srt: str = ""

@dataclass
class CancelledMessage:
    type: str = "cancelled"

@dataclass
class ErrorMessage:
    type: str = "error"
    message: str = ""
