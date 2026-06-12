"""Safe in-memory conversion from Pillow images to Qt images."""

from __future__ import annotations

from PIL import Image
from PySide6.QtGui import QImage, QPixmap


def pil_to_qimage(image: Image.Image) -> QImage:
    """Convert a Pillow image to a detached QImage."""
    converted = image.convert("RGBA")
    data = converted.tobytes("raw", "RGBA")
    qimage = QImage(
        data,
        converted.width,
        converted.height,
        converted.width * 4,
        QImage.Format.Format_RGBA8888,
    )
    return qimage.copy()


def pil_to_qpixmap(image: Image.Image) -> QPixmap:
    return QPixmap.fromImage(pil_to_qimage(image))
