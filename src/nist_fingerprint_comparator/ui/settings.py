"""Application preferences, storage, and export locations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QDateTime, QSettings, QStandardPaths, Qt, QTimeZone

HISTORY_DATABASE_FILENAME = "decision_history.sqlite3"
HISTORY_TIMEZONE_KEY = "history/timezone"
OFFER_SESSION_EXPORT_KEY = "export/offer_session_results"


class AppSettings:
    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings()

    def history_database_path(self) -> Path:
        location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        base = Path(location) if location else Path.home() / ".nist_fingerprint_comparator"
        current_path = base / HISTORY_DATABASE_FILENAME
        if current_path.exists():
            return current_path
        for legacy_path in _legacy_history_paths(base):
            if legacy_path.exists():
                return legacy_path
        return current_path

    def history_timezone_id(self) -> str:
        default_id = bytes(QTimeZone.systemTimeZoneId()).decode() or "UTC"
        timezone_id = str(self._settings.value(HISTORY_TIMEZONE_KEY, default_id))
        return timezone_id if QTimeZone(timezone_id.encode()).isValid() else "UTC"

    def set_history_timezone_id(self, timezone_id: str) -> None:
        if not QTimeZone(timezone_id.encode()).isValid():
            raise ValueError(f"Unknown timezone: {timezone_id}")
        self._settings.setValue(HISTORY_TIMEZONE_KEY, timezone_id)

    def offer_session_export(self) -> bool:
        return bool(self._settings.value(OFFER_SESSION_EXPORT_KEY, True, type=bool))

    def set_offer_session_export(self, enabled: bool) -> None:
        self._settings.setValue(OFFER_SESSION_EXPORT_KEY, enabled)

    def history_timestamp_values(self) -> tuple[str, str, str]:
        """Return canonical UTC and selected-timezone timestamps for a history record."""
        timestamp_utc = QDateTime.currentDateTimeUtc()
        timezone_id = self.history_timezone_id()
        recorded = timestamp_utc.toTimeZone(QTimeZone(timezone_id.encode()))
        utc_datetime = timestamp_utc.toPython()
        if utc_datetime.tzinfo is None:
            utc_datetime = utc_datetime.replace(tzinfo=UTC)
        return (
            utc_datetime.astimezone(UTC).isoformat(),
            recorded.toString(Qt.DateFormat.ISODateWithMs),
            timezone_id,
        )

    def default_export_path(self) -> Path:
        return self.default_export_directory() / (
            f"nist_decision_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

    def default_session_export_path(self) -> Path:
        return self.default_export_directory() / (
            f"nist_session_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

    @staticmethod
    def default_export_directory() -> Path:
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        return Path(desktop) if desktop else Path.home()


def _legacy_history_paths(current_base: Path) -> list[Path]:
    legacy_name = "NIST Fingerprint Comparator"
    return [
        current_base.parent / legacy_name / HISTORY_DATABASE_FILENAME,
        current_base.parent.parent / legacy_name / legacy_name / HISTORY_DATABASE_FILENAME,
    ]
