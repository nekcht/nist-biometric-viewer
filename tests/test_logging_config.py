import logging
from pathlib import Path

import nist_biometric_viewer.logging_config as logging_config
from nist_biometric_viewer.logging_config import (
    LOG_DIRECTORY_NAME,
    configure_logging,
    default_log_path,
)
from nist_biometric_viewer.user_data import APP_DATA_DIRECTORY_NAME


def test_default_log_path_uses_named_user_data_directory() -> None:
    path = default_log_path()

    assert path.parent.name == "logs"
    assert path.parent.parent.name == LOG_DIRECTORY_NAME
    assert LOG_DIRECTORY_NAME == APP_DATA_DIRECTORY_NAME
    assert path.name == "nist_biometric_viewer.log"


def test_configure_logging_writes_rotating_user_log_without_console_noise(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "logs" / "application.log"
    logger = logging.getLogger("nist_biometric_viewer")

    configured = configure_logging(log_path=output)
    logging.getLogger("nist_biometric_viewer.test").info("test log entry")
    for handler in logger.handlers:
        handler.flush()

    assert configured == output
    assert "test log entry" in output.read_text(encoding="utf-8")
    assert "Application logging initialized: <path>" not in output.read_text(encoding="utf-8")
    assert capsys.readouterr().err == ""
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()


def test_configure_logging_can_enable_developer_console_output(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "logs" / "application.log"
    logger = logging.getLogger("nist_biometric_viewer")

    configure_logging(log_path=output, console=True)
    logging.getLogger("nist_biometric_viewer.test").info("developer message")

    assert "developer message" in capsys.readouterr().err
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()


def test_configure_logging_rotates_and_limits_backups(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "logs" / "application.log"
    logger = logging.getLogger("nist_biometric_viewer")
    monkeypatch.setattr(logging_config, "LOG_MAX_BYTES", 128)
    monkeypatch.setattr(logging_config, "LOG_BACKUP_COUNT", 2)

    configure_logging(log_path=output)
    for index in range(40):
        logging.getLogger("nist_biometric_viewer.rotation").info(
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
