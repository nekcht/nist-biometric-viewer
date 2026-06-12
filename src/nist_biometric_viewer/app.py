"""Application entry point."""

from __future__ import annotations

import ctypes
import logging
import sys

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .logging_config import configure_logging
from .ui.main_window import MainWindow
from .ui.resources import application_icon
from .ui.styles import APP_STYLESHEET
from .user_data import (
    cleanup_stale_temp_dirs,
    ensure_user_data_dirs,
    get_instance_lock_path,
    install_default_user_files,
)

WINDOWS_APP_USER_MODEL_ID = "HellenicPolice.NistBiometricViewer"
LOGGER = logging.getLogger(__name__)


def _install_exception_logger() -> None:
    original_hook = sys.excepthook

    def log_exception(exception_type, exception, traceback) -> None:
        if issubclass(exception_type, KeyboardInterrupt):
            original_hook(exception_type, exception, traceback)
            return
        LOGGER.critical("Unhandled application exception: %s", exception_type.__name__)
        original_hook(exception_type, exception, traceback)

    sys.excepthook = log_exception


def _configure_windows_app_identity() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined]
            WINDOWS_APP_USER_MODEL_ID
        )
    except (AttributeError, OSError):
        pass


def _acquire_instance_lock() -> tuple[QLockFile | None, QLockFile.LockError]:
    lock = QLockFile(str(get_instance_lock_path()))
    lock.setStaleLockTime(0)
    if lock.tryLock(0):
        return lock, QLockFile.LockError.NoError
    return None, lock.error()


def _run_application(application: QApplication) -> int:
    configure_logging()
    _install_exception_logger()
    LOGGER.info("Starting Nist Biometric Viewer")
    try:
        install_default_user_files()
    except OSError as exc:
        LOGGER.warning("Default configuration installation failed: %s", type(exc).__name__)
        QMessageBox.warning(
            None,
            "Configuration unavailable",
            "Default configuration files could not be installed. The application can continue.",
        )

    cleaned, cleanup_failures = cleanup_stale_temp_dirs()
    if cleaned:
        LOGGER.info("Removed stale temporary archive sessions: %s", len(cleaned))
    if cleanup_failures:
        LOGGER.warning("Stale temporary archive cleanup failures: %s", len(cleanup_failures))
        QMessageBox.warning(
            None,
            "Temporary files could not be removed",
            "Some old temporary files could not be removed. The application can continue.",
        )

    try:
        window = MainWindow()
    except Exception as exc:
        LOGGER.critical("Application startup failed: %s", type(exc).__name__)
        QMessageBox.critical(
            None,
            "Application could not start",
            "The application could not initialize its local data.",
        )
        return 1
    window.show()
    return application.exec()


def main() -> int:
    _configure_windows_app_identity()
    application = QApplication(sys.argv)
    application.setApplicationName("Nist Biometric Viewer")
    application.setApplicationDisplayName("Nist Biometric Viewer")
    application.setApplicationVersion(__version__)
    application.setOrganizationName("Hellenic Police")
    application.setWindowIcon(application_icon())
    application.setStyleSheet(APP_STYLESHEET)
    try:
        ensure_user_data_dirs()
    except OSError:
        QMessageBox.critical(
            None,
            "Folder unavailable",
            "Required application folders could not be created or accessed.",
        )
        return 1

    instance_lock, lock_error = _acquire_instance_lock()
    if instance_lock is None:
        if lock_error == QLockFile.LockError.LockFailedError:
            QMessageBox.information(
                None,
                "Nist Biometric Viewer is already running",
                "Only one instance of Nist Biometric Viewer can run at a time.",
            )
            return 0
        QMessageBox.critical(
            None,
            "Application could not start",
            "The application instance lock could not be created.",
        )
        return 1

    try:
        return _run_application(application)
    finally:
        instance_lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
