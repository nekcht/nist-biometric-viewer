"""Application logging configuration."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .core.loading import sanitize_diagnostic
from .user_data import APP_DATA_DIRECTORY_NAME, get_logs_dir

LOGGER_NAME = "nist_biometric_viewer"
LOG_DIRECTORY_NAME = APP_DATA_DIRECTORY_NAME
LOG_FILENAME = "nist_biometric_viewer.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5


class SanitizingLogFilter(logging.Filter):
    """Remove raw bytes, control characters, and full paths from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = sanitize_diagnostic(record.getMessage(), maximum_length=2000)
        record.msg = message or ""
        record.args = ()
        return True


def configure_logging(
    level: int = logging.INFO,
    log_path: Path | None = None,
    *,
    console: bool = False,
) -> Path | None:
    """Configure rotating user-data logs and optional developer console output."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.addFilter(SanitizingLogFilter())
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
    except OSError as exc:
        if not logger.handlers:
            logger.addHandler(logging.NullHandler())
        logger.error(
            "Could not configure application file logging: %s",
            type(exc).__name__,
        )
        return None
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SanitizingLogFilter())
    logger.addHandler(file_handler)
    logger.info("Application logging initialized")
    return target


def default_log_path() -> Path:
    return get_logs_dir() / LOG_FILENAME
