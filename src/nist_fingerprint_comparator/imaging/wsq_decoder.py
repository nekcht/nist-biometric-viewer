"""Optional WSQ decoder adapter."""

from __future__ import annotations

import importlib

from nist_fingerprint_comparator.core.models import BiometricImage

from .pillow_decoder import PillowDecoder

WSQ_UNAVAILABLE_MESSAGE = (
    "WSQ decoder not installed. Install/configure NBIS or a WSQ Pillow plugin."
)


class WsqDecoder:
    """Try known Pillow WSQ plugins without claiming support when absent."""

    plugin_modules = ("pillow_wsq", "wsq")

    def decode(self, image: BiometricImage) -> BiometricImage:
        loaded_plugin = False
        for module_name in self.plugin_modules:
            try:
                importlib.import_module(module_name)
                loaded_plugin = True
                break
            except ImportError:
                continue

        if not loaded_plugin:
            image.decode_status = "unsupported"
            image.warnings.append(WSQ_UNAVAILABLE_MESSAGE)
            return image

        decoded = PillowDecoder().decode(image)
        if decoded.decode_status != "decoded":
            decoded.decode_status = "unsupported"
            decoded.warnings.append(WSQ_UNAVAILABLE_MESSAGE)
        return decoded
