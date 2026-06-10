"""Application storage and export locations."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

HISTORY_DATABASE_FILENAME = "decision_history.sqlite3"


class AppSettings:
    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings()

    def history_database_path(self) -> Path:
        location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        base = Path(location) if location else Path.home() / ".nist_fingerprint_comparator"
        return base / HISTORY_DATABASE_FILENAME

    def default_export_path(self) -> Path:
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        base = Path(desktop) if desktop else Path.home()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return base / f"nist_decision_history_{timestamp}.xlsx"
