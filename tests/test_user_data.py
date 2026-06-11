from pathlib import Path

from nist_fingerprint_comparator.user_data import (
    APP_DATA_DIRECTORY_NAME,
    USER_DATA_ROOT_ENV,
    ensure_user_data_dirs,
    get_config_dir,
    get_exports_dir,
    get_history_dir,
    get_logs_dir,
    get_temp_dir,
    get_user_data_dir,
    install_default_user_files,
)


def test_windows_appdata_uses_stable_application_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(USER_DATA_ROOT_ENV, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert get_user_data_dir() == tmp_path / APP_DATA_DIRECTORY_NAME


def test_path_helpers_use_expected_per_user_structure(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ForensicPrintComparator"
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(root))

    assert get_user_data_dir() == root
    assert get_config_dir() == root / "config"
    assert get_logs_dir() == root / "logs"
    assert get_history_dir() == root / "history"
    assert get_exports_dir() == root / "exports"
    assert get_temp_dir() == root / "temp"


def test_ensure_user_data_dirs_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "user-data"
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(root))

    first = ensure_user_data_dirs()
    second = ensure_user_data_dirs()

    assert first == second
    assert all(path.is_dir() for path in first)


def test_default_files_do_not_overwrite_existing_config(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "user-data"
    defaults = tmp_path / "defaults"
    default_settings = defaults / "config" / "settings.ini"
    default_settings.parent.mkdir(parents=True)
    default_settings.write_text("installer default", encoding="utf-8")
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(root))

    installed = install_default_user_files(defaults)
    settings = get_config_dir() / "settings.ini"
    settings.write_text("user setting", encoding="utf-8")
    installed_again = install_default_user_files(defaults)

    assert installed == [settings]
    assert installed_again == []
    assert settings.read_text(encoding="utf-8") == "user setting"


def test_default_user_files_include_no_biometric_or_evidence_samples() -> None:
    defaults = Path(__file__).resolve().parents[1] / "installer" / "default_user_files"
    forbidden_extensions = {
        ".an2",
        ".eft",
        ".jp2",
        ".jpe",
        ".jpeg",
        ".jpg",
        ".nist",
        ".png",
        ".raw",
        ".tif",
        ".tiff",
        ".wsq",
    }

    files = [path for path in defaults.rglob("*") if path.is_file()]

    assert files
    assert not any(path.suffix.lower() in forbidden_extensions for path in files)
