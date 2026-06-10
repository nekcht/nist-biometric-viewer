"""Pillow-backed image decoder."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from nist_fingerprint_comparator.core.models import BiometricImage


class PillowDecoder:
    """Decode formats supported by the installed Pillow build."""

    def decode(self, image: BiometricImage) -> BiometricImage:
        if not image.image_bytes:
            image.decode_status = "not_present"
            image.warnings.append("No embedded image payload is present.")
            return image
        try:
            with Image.open(BytesIO(image.image_bytes)) as opened:
                decoded = opened.copy()
            image.decoded_pil_image = decoded
            image.width = image.width or decoded.width
            image.height = image.height or decoded.height
            image.bit_depth = image.bit_depth or _bit_depth(decoded)
            image.decode_status = "decoded"
        except Exception as exc:
            image.decode_status = "failed"
            image.warnings.append(f"Image decoding failed: {exc}")
        return image


def _bit_depth(image: Image.Image) -> int | None:
    return {"1": 1, "L": 8, "P": 8, "RGB": 24, "RGBA": 32, "I;16": 16}.get(image.mode)
