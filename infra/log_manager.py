import logging
import logging.handlers
import queue
from datetime import datetime
from constants import LOG_PATH, LOG_MAX_BYTES

# Module-level queue for UI log consumption
ui_queue = queue.Queue()

def setup_logging() -> logging.Logger:
    """Configures the application logger with file and queue handlers."""
    logger = logging.getLogger("sysubs")
    
    # Defensive: skip if already set up
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.INFO)
    
    # Ensure log directory exists
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    
    # 1. File Handler (Rotating)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_PATH,
        maxBytes=LOG_MAX_BYTES,
        backupCount=0,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # 2. UI Queue Handler
    queue_handler = logging.handlers.QueueHandler(ui_queue)
    logger.addHandler(queue_handler)
    
    # Session Header
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"=== SySubs session started: {now} ===")
    
    return logger
