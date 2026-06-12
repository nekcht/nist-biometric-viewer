"""Application resource lookup helpers."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon

APP_ICON_FILENAME = "nist_biometric_viewer.png"


def application_icon_path() -> Path:
    """Return the best available path to the application icon."""
    candidates = [
        Path(__file__).resolve().parents[3] / "resources" / APP_ICON_FILENAME,
        Path(sys.prefix) / "resources" / APP_ICON_FILENAME,
    ]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.insert(0, Path(bundle_root) / "resources" / APP_ICON_FILENAME)
    return next((path for path in candidates if path.is_file()), candidates[0])


def application_icon() -> QIcon:
    return QIcon(str(application_icon_path()))
