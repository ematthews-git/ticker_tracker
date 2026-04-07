import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from config import LOG_PATH, LOG_LEVEL

def configure_logging() -> None:

    root = logging.getLogger()

    #Avoid adding handlers twice
    if root.handlers:
        return
    
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    root.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    #File handler
    log_dir = os.path.dirname(os.path.abspath(LOG_PATH))
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=5 * 1024 * 1024, #5mb
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    #console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)