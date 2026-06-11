import logging
from pathlib import Path

from nist_fingerprint_comparator.logging_config import (
    LOG_DIRECTORY_NAME,
    configure_logging,
    default_log_path,
)


def test_default_log_path_uses_named_user_data_directory() -> None:
    path = default_log_path()

    assert path.parent.name == "logs"
    assert path.parent.parent.name == LOG_DIRECTORY_NAME
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
