import json
from pathlib import Path

import pytest

import nist_biometric_viewer.user_data as user_data
from nist_biometric_viewer.user_data import (
    APP_DATA_DIRECTORY_NAME,
    LEGACY_APP_DATA_DIRECTORY_NAMES,
    LEGACY_USER_DATA_ROOT_ENVS,
    TEMP_SESSION_MARKER,
    TEMP_SESSION_PREFIX,
    USER_DATA_ROOT_ENV,
    cleanup_stale_temp_dirs,
    create_archive_temp_directory,
    ensure_user_data_dirs,
    get_config_dir,
    get_exports_dir,
    get_history_dir,
    get_legacy_user_data_dirs,
    get_logs_dir,
    get_temp_dir,
    get_user_data_dir,
    install_default_user_files,
)


def test_windows_appdata_uses_stable_application_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(USER_DATA_ROOT_ENV, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert APP_DATA_DIRECTORY_NAME == "NistBiometricViewer"
    assert get_user_data_dir() == tmp_path / APP_DATA_DIRECTORY_NAME


def test_path_helpers_use_expected_per_user_structure(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "NistBiometricViewer"
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(root))

    assert get_user_data_dir() == root
    assert get_config_dir() == root / "config"
    assert get_logs_dir() == root / "logs"
    assert get_history_dir() == root / "history"
    assert get_exports_dir() == root / "exports"
    assert get_temp_dir() == root / "temp"


def test_legacy_user_data_names_remain_available_for_migration(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv(USER_DATA_ROOT_ENV, raising=False)
    for environment_name in LEGACY_USER_DATA_ROOT_ENVS:
        monkeypatch.delenv(environment_name, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert LEGACY_APP_DATA_DIRECTORY_NAMES == (
        "nistBiometricViewer",
        "ForensicPrintComparator",
    )
    expected = [tmp_path / "ForensicPrintComparator"]
    casing_only_legacy_path = tmp_path / "nistBiometricViewer"
    if casing_only_legacy_path != tmp_path / APP_DATA_DIRECTORY_NAME:
        expected.insert(0, casing_only_legacy_path)
    assert get_legacy_user_data_dirs() == expected


def test_legacy_user_data_environment_override_remains_supported(
    tmp_path: Path, monkeypatch
) -> None:
    legacy_root = tmp_path / "legacy-override"
    monkeypatch.delenv(USER_DATA_ROOT_ENV, raising=False)
    monkeypatch.setenv(LEGACY_USER_DATA_ROOT_ENVS[0], str(legacy_root))

    assert get_user_data_dir() == legacy_root
    assert get_legacy_user_data_dirs() == []


def test_current_user_data_environment_override_takes_precedence(
    tmp_path: Path, monkeypatch
) -> None:
    current_root = tmp_path / "current-override"
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(current_root))
    monkeypatch.setenv(LEGACY_USER_DATA_ROOT_ENVS[0], str(tmp_path / "legacy-override"))

    assert get_user_data_dir() == current_root


def test_ensure_user_data_dirs_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "user-data"
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(root))

    first = ensure_user_data_dirs()
    second = ensure_user_data_dirs()

    assert first == second
    assert all(path.is_dir() for path in first)


def test_archive_temp_directory_is_per_user_marked_and_self_cleaning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "user-data"
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(root))

    temporary_directory = create_archive_temp_directory()
    session_root = Path(temporary_directory.name)

    assert session_root.parent == root / "temp"
    assert (session_root / TEMP_SESSION_MARKER).is_file()
    assert (session_root / "contents").is_dir()

    temporary_directory.cleanup()

    assert not session_root.exists()


def test_stale_temp_cleanup_removes_only_old_marked_app_sessions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "user-data"
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(root))
    ensure_user_data_dirs()
    stale = get_temp_dir() / f"{TEMP_SESSION_PREFIX}stale"
    active = get_temp_dir() / f"{TEMP_SESSION_PREFIX}active"
    unknown = get_temp_dir() / "unrelated"
    for directory in (stale, active, unknown):
        directory.mkdir()
    (stale / TEMP_SESSION_MARKER).write_text(
        json.dumps({"pid": 10, "created": 0}),
        encoding="ascii",
    )
    (active / TEMP_SESSION_MARKER).write_text(
        json.dumps({"pid": 20, "created": 0}),
        encoding="ascii",
    )
    monkeypatch.setattr(user_data, "_process_is_running", lambda pid: pid == 20)

    cleaned, failed = cleanup_stale_temp_dirs(now=100, maximum_age_seconds=10)

    assert cleaned == [stale]
    assert failed == []
    assert not stale.exists()
    assert active.exists()
    assert unknown.exists()


def test_stale_temp_cleanup_failure_is_non_fatal(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "user-data"
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(root))
    ensure_user_data_dirs()
    stale = get_temp_dir() / f"{TEMP_SESSION_PREFIX}stale"
    stale.mkdir()
    (stale / TEMP_SESSION_MARKER).write_text(
        json.dumps({"pid": 10, "created": 0}),
        encoding="ascii",
    )
    monkeypatch.setattr(user_data, "_process_is_running", lambda _pid: False)
    monkeypatch.setattr(
        user_data.shutil,
        "rmtree",
        lambda _path: (_ for _ in ()).throw(PermissionError("locked")),
    )

    cleaned, failed = cleanup_stale_temp_dirs(now=100, maximum_age_seconds=10)

    assert cleaned == []
    assert failed == [stale]
    assert stale.exists()


def test_user_data_folder_write_failure_is_reported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(tmp_path / "user-data"))
    monkeypatch.setattr(
        user_data.tempfile,
        "NamedTemporaryFile",
        lambda **_kwargs: (_ for _ in ()).throw(PermissionError("denied")),
    )

    with pytest.raises(PermissionError):
        ensure_user_data_dirs()


def test_runtime_data_creation_does_not_write_to_working_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    working_directory = tmp_path / "installed-app"
    working_directory.mkdir()
    monkeypatch.chdir(working_directory)
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(tmp_path / "user-data"))

    ensure_user_data_dirs()
    temporary_directory = create_archive_temp_directory()
    temporary_directory.cleanup()

    assert list(working_directory.iterdir()) == []


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


def test_default_file_installation_migrates_legacy_config(
    tmp_path: Path, monkeypatch
) -> None:
    defaults = tmp_path / "defaults"
    default_settings = defaults / "config" / "settings.ini"
    default_settings.parent.mkdir(parents=True)
    default_settings.write_text("installer default", encoding="utf-8")
    legacy_settings = tmp_path / "ForensicPrintComparator" / "config" / "settings.ini"
    legacy_settings.parent.mkdir(parents=True)
    legacy_settings.write_text("legacy user setting", encoding="utf-8")
    monkeypatch.delenv(USER_DATA_ROOT_ENV, raising=False)
    for environment_name in LEGACY_USER_DATA_ROOT_ENVS:
        monkeypatch.delenv(environment_name, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    installed = install_default_user_files(defaults)
    settings = get_config_dir() / "settings.ini"

    assert installed == [settings]
    assert settings.read_text(encoding="utf-8") == "legacy user setting"


def test_failed_default_file_copy_removes_partial_destination(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "user-data"
    defaults = tmp_path / "defaults"
    source = defaults / "config" / "settings.ini"
    source.parent.mkdir(parents=True)
    source.write_text("installer default", encoding="utf-8")
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(root))

    def fail_copy(_source, destination) -> None:
        destination.write(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(user_data.shutil, "copyfileobj", fail_copy)

    with pytest.raises(OSError):
        install_default_user_files(defaults)

    assert not (root / "config" / "settings.ini").exists()


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


def test_windows_installer_creates_named_user_data_directory() -> None:
    installer = (
        Path(__file__).resolve().parents[1] / "installer" / "nist_biometric_viewer.iss"
    ).read_text(encoding="utf-8")

    assert '#define AppExeName "NistBiometricViewer.exe"' in installer
    assert '#define InstallDirectoryName "NistBiometricViewer"' in installer
    assert '#define AppDataName "NistBiometricViewer"' in installer
    assert 'DefaultDirName={localappdata}\\Programs\\{#InstallDirectoryName}' in installer
    assert "UsePreviousAppDir=no" in installer
    assert "PrivilegesRequired=lowest" in installer
    assert "OutputBaseFilename=NistBiometricViewer_Setup_{#AppVersion}" in installer
    assert 'Source: "{#SourceRoot}\\dist\\NistBiometricViewer\\*"' in installer
    assert "ForensicPrintComparator" not in installer
    assert 'Name: "desktopicon"' in installer
    assert "Flags: unchecked" in installer
    assert 'Name: "{userappdata}\\{#AppDataName}\\history"' in installer
    assert "uninsneveruninstall" in installer


def test_windows_build_rejects_missing_required_runtime_dependencies() -> None:
    build_script = (
        Path(__file__).resolve().parents[1] / "scripts" / "build_windows.ps1"
    ).read_text(encoding="utf-8")

    assert "import PIL, PyInstaller, PySide6, openpyxl, rarfile" in build_script
    assert "Required build dependencies are missing" in build_script
    assert '"NistBiometricViewer.spec"' in build_script
    assert '"NistBiometricViewer\\NistBiometricViewer.exe"' in build_script
    assert "ForensicPrintComparator" not in build_script
    assert build_script.index("import PIL, PyInstaller") < build_script.index(
        '$BuildDir = Join-Path $RepoRoot "build"'
    )
