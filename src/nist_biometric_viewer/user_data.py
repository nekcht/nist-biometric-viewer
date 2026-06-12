"""Centralized per-user application data paths and baseline file installation."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QStandardPaths

APP_DATA_DIRECTORY_NAME = "NistBiometricViewer"
LEGACY_APP_DATA_DIRECTORY_NAMES = ("nistBiometricViewer", "ForensicPrintComparator")
USER_DATA_ROOT_ENV = "NIST_BIOMETRIC_VIEWER_USER_DATA_DIR"
LEGACY_USER_DATA_ROOT_ENVS = ("FORENSICPRINT_COMPARATOR_USER_DATA_DIR",)
USER_DATA_SUBDIRECTORIES = ("config", "logs", "history", "exports", "temp")
TEMP_SESSION_PREFIX = "archive-session-"
TEMP_SESSION_MARKER = ".nist-biometric-viewer-temp"
TEMP_SESSION_RETENTION_SECONDS = 24 * 60 * 60


def get_user_data_dir() -> Path:
    """Return the per-user root shared by the app and Windows installer."""
    configured = _configured_user_data_dir()
    if configured is not None:
        return configured

    return _user_data_base() / APP_DATA_DIRECTORY_NAME


def get_legacy_user_data_dirs() -> list[Path]:
    """Return former per-user roots eligible for one-time data migration."""
    if _configured_user_data_dir() is not None:
        return []
    base = _user_data_base()
    current = base / APP_DATA_DIRECTORY_NAME
    return [
        candidate
        for name in LEGACY_APP_DATA_DIRECTORY_NAMES
        if (candidate := base / name) != current
    ]


def _configured_user_data_dir() -> Path | None:
    for environment_name in (USER_DATA_ROOT_ENV, *LEGACY_USER_DATA_ROOT_ENVS):
        configured = os.environ.get(environment_name)
        if configured:
            return Path(configured).expanduser()
    return None


def _user_data_base() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata)

    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericDataLocation
    )
    return Path(location) if location else Path.home() / ".local" / "share"


def get_config_dir() -> Path:
    return get_user_data_dir() / "config"


def get_logs_dir() -> Path:
    return get_user_data_dir() / "logs"


def get_history_dir() -> Path:
    return get_user_data_dir() / "history"


def get_exports_dir() -> Path:
    return get_user_data_dir() / "exports"


def get_temp_dir() -> Path:
    """Return the non-evidence temporary-data directory reserved for the application."""
    return get_user_data_dir() / "temp"


def ensure_user_data_dirs() -> tuple[Path, ...]:
    """Create and verify the required per-user folders."""
    directories = (
        get_user_data_dir(),
        get_config_dir(),
        get_logs_dir(),
        get_history_dir(),
        get_exports_dir(),
        get_temp_dir(),
    )
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        _verify_writable_directory(directory)
    return directories


def create_archive_temp_directory() -> TemporaryDirectory:
    """Create a marked, self-cleaning archive session under per-user storage."""
    ensure_user_data_dirs()
    temporary_directory = TemporaryDirectory(
        prefix=TEMP_SESSION_PREFIX,
        dir=get_temp_dir(),
        ignore_cleanup_errors=False,
    )
    root = Path(temporary_directory.name)
    try:
        (root / TEMP_SESSION_MARKER).write_text(
            json.dumps({"pid": os.getpid(), "created": time.time()}),
            encoding="ascii",
        )
        (root / "contents").mkdir()
    except OSError:
        temporary_directory.cleanup()
        raise
    return temporary_directory


def cleanup_stale_temp_dirs(
    *,
    now: float | None = None,
    maximum_age_seconds: int = TEMP_SESSION_RETENTION_SECONDS,
) -> tuple[list[Path], list[Path]]:
    """Remove old, marked archive sessions while leaving unknown folders untouched."""
    cleaned: list[Path] = []
    failed: list[Path] = []
    current_time = time.time() if now is None else now
    temp_root = get_temp_dir()
    try:
        resolved_temp_root = temp_root.resolve()
        children = list(temp_root.iterdir())
    except OSError:
        return cleaned, [temp_root]

    for child in children:
        if not child.name.startswith(TEMP_SESSION_PREFIX):
            continue
        try:
            if (
                child.is_symlink()
                or not child.is_dir()
                or not child.resolve().is_relative_to(resolved_temp_root)
            ):
                continue
            marker = child / TEMP_SESSION_MARKER
            if not marker.is_file():
                continue
            try:
                marker_data = json.loads(marker.read_text(encoding="ascii"))
            except (TypeError, ValueError):
                marker_data = {}
            created = float(marker_data.get("created", marker.stat().st_mtime))
            pid = int(marker_data.get("pid", 0))
            if current_time - created < maximum_age_seconds or _process_is_running(pid):
                continue
            shutil.rmtree(child)
            cleaned.append(child)
        except (OSError, TypeError, ValueError):
            failed.append(child)
    return cleaned, failed


def install_default_user_files(defaults_root: Path | None = None) -> list[Path]:
    """Copy missing baseline files without replacing user-owned data."""
    root = defaults_root or default_user_files_dir()
    if not root.is_dir():
        return []

    installed: list[Path] = []
    ensure_user_data_dirs()
    for source in sorted(path for path in root.rglob("*") if path.is_file()):
        relative_path = source.relative_to(root)
        if any(part.startswith(".") for part in relative_path.parts):
            continue
        destination = get_user_data_dir() / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if _copy_missing_legacy_user_file(relative_path, destination):
            installed.append(destination)
            continue
        destination_created = False
        try:
            with source.open("rb") as source_file, destination.open("xb") as destination_file:
                destination_created = True
                shutil.copyfileobj(source_file, destination_file)
        except FileExistsError:
            continue
        except OSError:
            if destination_created:
                destination.unlink(missing_ok=True)
            raise
        installed.append(destination)
    return installed


def _copy_missing_legacy_user_file(relative_path: Path, destination: Path) -> bool:
    for legacy_root in get_legacy_user_data_dirs():
        source = legacy_root / relative_path
        if not source.is_file():
            continue
        destination_created = False
        try:
            with source.open("rb") as source_file, destination.open("xb") as destination_file:
                destination_created = True
                shutil.copyfileobj(source_file, destination_file)
        except FileExistsError:
            return False
        except OSError:
            if destination_created:
                destination.unlink(missing_ok=True)
            raise
        return True
    return False


def default_user_files_dir() -> Path:
    """Locate installer-owned default files in development and PyInstaller builds."""
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "default_user_files")
    candidates.append(Path(__file__).resolve().parents[2] / "installer" / "default_user_files")
    return next((path for path in candidates if path.is_dir()), candidates[-1])


def _verify_writable_directory(directory: Path) -> None:
    probe_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".write-test-",
            dir=directory,
            delete=False,
        ) as probe:
            probe_path = Path(probe.name)
            probe.write(b"ok")
    finally:
        if probe_path is not None:
            probe_path.unlink(missing_ok=True)


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [
                wintypes.DWORD,
                wintypes.BOOL,
                wintypes.DWORD,
            ]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            process = kernel32.OpenProcess(
                0x1000,
                False,
                pid,
            )
            if not process:
                return ctypes.get_last_error() == 5
            kernel32.CloseHandle(process)
            return True
        except (AttributeError, OSError):
            return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True
