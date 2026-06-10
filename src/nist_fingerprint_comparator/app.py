"""Application entry point."""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtWidgets import QApplication

from .logging_config import configure_logging
from .ui.main_window import MainWindow
from .ui.resources import application_icon
from .ui.styles import APP_STYLESHEET

WINDOWS_APP_USER_MODEL_ID = "HellenicPolice.NISTFingerprintComparator"


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
    configure_logging()
    _configure_windows_app_identity()
    application = QApplication(sys.argv)
    application.setApplicationName("NIST Fingerprint Comparator")
    application.setApplicationDisplayName("NIST Fingerprint Comparator")
    application.setOrganizationName("NIST Fingerprint Comparator")
    application.setWindowIcon(application_icon())
    application.setStyleSheet(APP_STYLESHEET)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
