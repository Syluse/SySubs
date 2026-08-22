class SySubsBaseError(Exception):
    """Base for all SySubs errors with user-friendly messages."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

class AudioExtractionError(SySubsBaseError):
    pass

class TranscriptionError(SySubsBaseError):
    pass

class ModelError(SySubsBaseError):
    pass

def friendly_error_message(exc: Exception) -> str:
    """Translates any exception into a user-friendly message."""
    if isinstance(exc, SySubsBaseError):
        return exc.message
    if isinstance(exc, ImportError):
        return f"Missing dependency: {exc}. Please reinstall SySubs."
    if isinstance(exc, PermissionError):
        return "Permission denied. Move SySubs to a folder you own (e.g. Desktop)."
    if isinstance(exc, FileNotFoundError):
        return f"File not found: {exc}"
    return f"Unexpected error: {exc}"
