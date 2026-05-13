"""
utils/logger.py
---------------
Centralised logging setup for Smart API Tool.

Usage (in any module):
    from utils.logger import setup_logger
    logger = setup_logger(__name__)
    logger.info("Scraping: https://example.com")
"""

import logging
import os
from typing import Optional


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def setup_logger(
    name: str,
    level: str = "INFO",
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Create and return a named logger with console (and optional file) output.

    Args:
        name:     Logger name — pass __name__ from the calling module.
        level:    Log level string: DEBUG | INFO | WARNING | ERROR.
                  Defaults to INFO.
        log_file: Optional path to a log file (e.g. "logs/smart_api_tool.log").
                  If provided the directory is created automatically.

    Returns:
        A configured logging.Logger instance.
    """
    log_level = LEVEL_MAP.get(level.upper(), logging.INFO)
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if the logger is already configured
    if logger.handlers:
        return logger

    logger.setLevel(log_level)

    # ── Console handler ───────────────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ── File handler (optional) ───────────────────────────────────────────────
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Prevent log records from propagating to the root logger
    logger.propagate = False

    return logger
