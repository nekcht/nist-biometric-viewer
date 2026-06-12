"""Application preferences, storage, and export locations."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QDateTime, QSettings, QTimeZone

from nist_fingerprint_comparator.user_data import (
    ensure_user_data_dirs,
    get_config_dir,
    get_exports_dir,
    get_history_dir,
    get_legacy_user_data_dirs,
)

HISTORY_DATABASE_FILENAME = "decision_history.sqlite3"
SETTINGS_FILENAME = "settings.ini"
HISTORY_TIMEZONE_KEY = "history/timezone"
OFFER_SESSION_EXPORT_KEY = "export/offer_session_results"
AUTO_END_SESSION_KEY = "session/auto_end_when_complete"
HISTORY_TIMESTAMP_FORMAT = "HH:mm dd-MM-yyyy"


class AppSettings:
    def __init__(self, settings: QSettings | None = None) -> None:
        if settings is None:
            ensure_user_data_dirs()
            settings = QSettings(
                str(get_config_dir() / SETTINGS_FILENAME),
                QSettings.Format.IniFormat,
            )
        self._settings = settings

    def history_database_path(self) -> Path:
        current_path = get_history_dir() / HISTORY_DATABASE_FILENAME
        current_path.parent.mkdir(parents=True, exist_ok=True)
        if current_path.exists():
            return current_path
        for legacy_path in _legacy_history_paths():
            if legacy_path.exists():
                shutil.copy2(legacy_path, current_path)
                break
        return current_path

    def history_timezone_id(self) -> str:
        default_id = bytes(QTimeZone.systemTimeZoneId()).decode() or "UTC"
        timezone_id = str(self._settings.value(HISTORY_TIMEZONE_KEY, default_id))
        return timezone_id if QTimeZone(timezone_id.encode()).isValid() else "UTC"

    def set_history_timezone_id(self, timezone_id: str) -> None:
        if not QTimeZone(timezone_id.encode()).isValid():
            raise ValueError(f"Unknown timezone: {timezone_id}")
        self._settings.setValue(HISTORY_TIMEZONE_KEY, timezone_id)
        self._sync()

    def offer_session_export(self) -> bool:
        return bool(self._settings.value(OFFER_SESSION_EXPORT_KEY, True, type=bool))

    def set_offer_session_export(self, enabled: bool) -> None:
        self._settings.setValue(OFFER_SESSION_EXPORT_KEY, enabled)
        self._sync()

    def auto_end_session(self) -> bool:
        return bool(self._settings.value(AUTO_END_SESSION_KEY, False, type=bool))

    def set_auto_end_session(self, enabled: bool) -> None:
        self._settings.setValue(AUTO_END_SESSION_KEY, enabled)
        self._sync()

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
            recorded.toString(HISTORY_TIMESTAMP_FORMAT),
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
        return get_exports_dir()

    def _sync(self) -> None:
        self._settings.sync()
        if self._settings.status() != QSettings.Status.NoError:
            raise OSError("Settings storage is unavailable.")


def _legacy_history_paths() -> list[Path]:
    return [
        root / "history" / HISTORY_DATABASE_FILENAME
        for root in get_legacy_user_data_dirs()
    ]
