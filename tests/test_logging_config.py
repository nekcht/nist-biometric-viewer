import logging
from pathlib import Path

import nist_fingerprint_comparator.logging_config as logging_config
from nist_fingerprint_comparator.logging_config import (
    LOG_DIRECTORY_NAME,
    configure_logging,
    default_log_path,
)
from nist_fingerprint_comparator.user_data import APP_DATA_DIRECTORY_NAME


def test_default_log_path_uses_named_user_data_directory() -> None:
    path = default_log_path()

    assert path.parent.name == "logs"
    assert path.parent.parent.name == LOG_DIRECTORY_NAME
    assert LOG_DIRECTORY_NAME == APP_DATA_DIRECTORY_NAME
    assert path.name == "nist_fingerprint_comparator.log"


def test_configure_logging_writes_rotating_user_log(tmp_path: Path) -> None:
    output = tmp_path / "logs" / "application.log"
    logger = logging.getLogger("nist_fingerprint_comparator")

    configured = configure_logging(log_path=output)
    logging.getLogger("nist_fingerprint_comparator.test").info("test log entry")
    for handler in logger.handlers:
        handler.flush()

    assert configured == output
    assert "test log entry" in output.read_text(encoding="utf-8")
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()


def test_configure_logging_rotates_and_limits_backups(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "logs" / "application.log"
    logger = logging.getLogger("nist_fingerprint_comparator")
    monkeypatch.setattr(logging_config, "LOG_MAX_BYTES", 128)
    monkeypatch.setattr(logging_config, "LOG_BACKUP_COUNT", 2)

    configure_logging(log_path=output)
    for index in range(40):
        logging.getLogger("nist_fingerprint_comparator.rotation").info(
            "bounded log message %s with enough content to rotate",
            index,
        )
    for handler in logger.handlers:
        handler.flush()

    log_files = list(output.parent.glob("application.log*"))
    assert output in log_files
    assert len(log_files) <= 3
    assert all(path.stat().st_size <= 256 for path in log_files)
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()
