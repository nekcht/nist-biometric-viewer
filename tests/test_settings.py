from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

from nist_fingerprint_comparator.ui.settings import HISTORY_DATABASE_FILENAME, AppSettings


def test_internal_history_uses_application_data_location(tmp_path: Path) -> None:
    settings = AppSettings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))

    assert settings.history_database_path().name == HISTORY_DATABASE_FILENAME


def test_xlsx_export_defaults_to_desktop(tmp_path: Path) -> None:
    settings = AppSettings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)

    assert settings.default_export_path().parent == (Path(desktop) if desktop else Path.home())
    assert settings.default_export_path().suffix == ".xlsx"
