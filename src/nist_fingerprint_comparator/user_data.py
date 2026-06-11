"""Centralized per-user application data paths and baseline file installation."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

APP_DATA_DIRECTORY_NAME = "ForensicPrintComparator"
USER_DATA_ROOT_ENV = "FORENSICPRINT_COMPARATOR_USER_DATA_DIR"
USER_DATA_SUBDIRECTORIES = ("config", "logs", "history", "exports", "temp")


def get_user_data_dir() -> Path:
    """Return the per-user root shared by the app and Windows installer."""
    configured = os.environ.get(USER_DATA_ROOT_ENV)
    if configured:
        return Path(configured).expanduser()

    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_DATA_DIRECTORY_NAME

    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericDataLocation
    )
    base = Path(location) if location else Path.home() / ".local" / "share"
    return base / APP_DATA_DIRECTORY_NAME


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
    """Create the required per-user folders as an idempotent startup fallback."""
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
    return directories


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
        try:
            with source.open("rb") as source_file, destination.open("xb") as destination_file:
                shutil.copyfileobj(source_file, destination_file)
        except FileExistsError:
            continue
        installed.append(destination)
    return installed


def default_user_files_dir() -> Path:
    """Locate installer-owned default files in development and PyInstaller builds."""
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "default_user_files")
    candidates.append(Path(__file__).resolve().parents[2] / "installer" / "default_user_files")
    return next((path for path in candidates if path.is_dir()), candidates[-1])
