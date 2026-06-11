"""Application entry point."""

from __future__ import annotations

import ctypes
import logging
import sys

from PySide6.QtWidgets import QApplication

from . import __version__
from .logging_config import configure_logging
from .ui.main_window import MainWindow
from .ui.resources import application_icon
from .ui.styles import APP_STYLESHEET
from .user_data import ensure_user_data_dirs, install_default_user_files

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


def main() -> int:
    ensure_user_data_dirs()
    install_default_user_files()
    configure_logging()
    _install_exception_logger()
    LOGGER.info("Starting Nist Biometric Viewer")
    _configure_windows_app_identity()
    application = QApplication(sys.argv)
    application.setApplicationName("Nist Biometric Viewer")
    application.setApplicationDisplayName("Nist Biometric Viewer")
    application.setApplicationVersion(__version__)
    application.setOrganizationName("Hellenic Police")
    application.setWindowIcon(application_icon())
    application.setStyleSheet(APP_STYLESHEET)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
