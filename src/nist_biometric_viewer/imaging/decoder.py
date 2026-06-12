"""Decoder selection and safe dispatch."""

from __future__ import annotations

from abc import ABC, abstractmethod

from nist_biometric_viewer.core.models import BiometricImage

from .pillow_decoder import PillowDecoder
from .wsq_decoder import WsqDecoder


class DecoderBackend(ABC):
    @abstractmethod
    def decode(self, image: BiometricImage) -> BiometricImage:
        """Decode an image in place and return it."""


class ImageDecoder:
    """Select an in-memory decoder based on metadata and payload signatures."""

    PILLOW_FORMATS = {"JPEG", "JPG", "PNG", "JPEG2000", "JP2", "JPEG2K"}

    def __init__(self) -> None:
        self.pillow = PillowDecoder()
        self.wsq = WsqDecoder()

    def decode(self, image: BiometricImage) -> BiometricImage:
        if not image.image_bytes:
            image.decode_status = "not_present"
            image.warnings.append("Image data unavailable.")
            return image

        compression = (image.compression or _detect_compression(image.image_bytes) or "").upper()
        image.compression = compression or image.compression
        if compression == "WSQ":
            return self.wsq.decode(image)
        if compression in self.PILLOW_FORMATS:
            decoded = self.pillow.decode(image)
            if compression in {"JPEG2000", "JP2", "JPEG2K"} and decoded.decode_status == "failed":
                decoded.decode_status = "unsupported"
                decoded.warnings.append(
                    "JPEG2000 decoder not configured."
                )
            return decoded
        if compression == "RAW":
            image.decode_status = "unsupported"
            image.warnings.append(
                "RAW image layout unsupported."
            )
            return image

        image.decode_status = "unsupported"
        image.warnings.append(
            f"Unsupported compression: {image.compression or 'not specified'}."
        )
        return image


def _detect_compression(payload: bytes) -> str | None:
    if payload.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if payload.startswith(b"\x00\x00\x00\x0cjP  \r\n\x87\n") or payload.startswith(b"\xffO\xffQ"):
        return "JPEG2000"
    if payload.startswith(b"\xff\xa0"):
        return "WSQ"
    return None
