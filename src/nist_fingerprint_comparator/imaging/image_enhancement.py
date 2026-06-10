"""Optional, non-destructive in-memory image enhancement helpers."""

from __future__ import annotations

from PIL import Image, ImageOps


def autocontrast(image: Image.Image) -> Image.Image:
    """Return an autocontrasted copy suitable for future UI controls."""
    return ImageOps.autocontrast(image.convert("L"))
