"""Application logging configuration."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .user_data import APP_DATA_DIRECTORY_NAME, get_logs_dir

LOGGER_NAME = "nist_fingerprint_comparator"
LOG_DIRECTORY_NAME = APP_DATA_DIRECTORY_NAME
LOG_FILENAME = "nist_fingerprint_comparator.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5


def configure_logging(level: int = logging.INFO, log_path: Path | None = None) -> Path | None:
    """Configure rotating user-data and console logs without biometric payloads."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    target = log_path or default_log_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            target,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        logger.exception("Could not configure application file logging")
        return None
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.info("Application logging initialized: %s", target)
    return target


def default_log_path() -> Path:
    return get_logs_dir() / LOG_FILENAME
