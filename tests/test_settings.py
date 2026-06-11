from pathlib import Path

from PySide6.QtCore import QSettings

from nist_fingerprint_comparator.core.models import NistTransaction
from nist_fingerprint_comparator.core.review import DecisionHistoryStore, ReviewDecision
from nist_fingerprint_comparator.ui.settings import HISTORY_DATABASE_FILENAME, AppSettings
from nist_fingerprint_comparator.user_data import (
    APP_DATA_DIRECTORY_NAME,
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


def test_legacy_history_is_copied_and_opened_from_new_user_data_folder(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv(USER_DATA_ROOT_ENV, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    legacy_path = (
        tmp_path / "ForensicPrintComparator" / "history" / HISTORY_DATABASE_FILENAME
    )
    legacy_store = DecisionHistoryStore(legacy_path)
    legacy_store.append(
        ReviewDecision(
            "MATCH",
            1,
            1,
            NistTransaction(Path("reference.nist")),
            NistTransaction(Path("comparison.nist")),
        )
    )
    settings = AppSettings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))

    history_path = settings.history_database_path()

    assert history_path == (
        tmp_path / APP_DATA_DIRECTORY_NAME / "history" / HISTORY_DATABASE_FILENAME
    )
    assert history_path.exists()
    assert history_path != legacy_path
    assert DecisionHistoryStore(history_path).count() == 1


def test_history_ignores_nist_fingerprint_comparator_folder(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv(USER_DATA_ROOT_ENV, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    wrong_paths = [
        tmp_path / "NIST Fingerprint Comparator" / HISTORY_DATABASE_FILENAME,
        (
            tmp_path
            / "NIST Fingerprint Comparator"
            / "NIST Fingerprint Comparator"
            / HISTORY_DATABASE_FILENAME
        ),
        tmp_path / "NIST Fingerprint Comparator" / "history" / HISTORY_DATABASE_FILENAME,
    ]
    wrong_stores = [DecisionHistoryStore(path) for path in wrong_paths]
    for store in wrong_stores:
        store.append(
            ReviewDecision(
                "MATCH",
                1,
                1,
                NistTransaction(Path("wrong-reference.nist")),
                NistTransaction(Path("wrong-comparison.nist")),
            )
        )
    settings = AppSettings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))

    history_path = settings.history_database_path()

    assert history_path == (
        tmp_path / APP_DATA_DIRECTORY_NAME / "history" / HISTORY_DATABASE_FILENAME
    )
    assert not history_path.exists()
    assert DecisionHistoryStore(history_path).count() == 0
    assert all(store.count() == 1 for store in wrong_stores)


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
