from pathlib import Path

from PySide6.QtCore import QSettings

from nist_fingerprint_comparator.ui.settings import HISTORY_DATABASE_FILENAME, AppSettings
from nist_fingerprint_comparator.user_data import (
    USER_DATA_ROOT_ENV,
    get_exports_dir,
    get_history_dir,
)


def test_internal_history_uses_application_data_location(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(tmp_path / "user-data"))
    settings = AppSettings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))

    assert settings.history_database_path() == get_history_dir() / HISTORY_DATABASE_FILENAME


def test_xlsx_export_defaults_to_per_user_exports(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(tmp_path / "user-data"))
    settings = AppSettings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))

    assert settings.default_export_path().parent == get_exports_dir()
    assert settings.default_export_path().suffix == ".xlsx"
    assert settings.default_session_export_path().parent == get_exports_dir()
    assert settings.default_session_export_path().suffix == ".xlsx"


def test_session_export_prompt_defaults_on_and_is_persisted(tmp_path: Path) -> None:
    settings = AppSettings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))

    assert settings.offer_session_export()

    settings.set_offer_session_export(False)

    assert not settings.offer_session_export()


def test_history_timezone_is_persisted_and_used_for_recorded_timestamp(tmp_path: Path) -> None:
    qsettings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings = AppSettings(qsettings)

    settings.set_history_timezone_id("UTC")
    timestamp_utc, timestamp, timezone_id = settings.history_timestamp_values()

    assert settings.history_timezone_id() == "UTC"
    assert timezone_id == "UTC"
    assert timestamp.startswith(timestamp_utc[:19])
    assert timestamp_utc.endswith("+00:00")
