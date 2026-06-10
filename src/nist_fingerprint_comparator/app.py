"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .logging_config import configure_logging
from .ui.main_window import MainWindow
from .ui.styles import APP_STYLESHEET


def main() -> int:
    configure_logging()
    application = QApplication(sys.argv)
    application.setApplicationName("NIST Fingerprint Comparator")
    application.setOrganizationName("NIST Fingerprint Comparator")
    application.setStyleSheet(APP_STYLESHEET)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
