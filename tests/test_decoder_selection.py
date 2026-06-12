from io import BytesIO

from PIL import Image

from nist_biometric_viewer.core.models import BiometricImage
from nist_biometric_viewer.imaging.decoder import ImageDecoder
from nist_biometric_viewer.imaging.wsq_decoder import WSQ_UNAVAILABLE_MESSAGE
from nist_biometric_viewer.nist.records import normalize_compression


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("L", (12, 18), color=80).save(output, format="PNG")
    return output.getvalue()


def test_pillow_decoder_decodes_png_and_fills_dimensions() -> None:
    image = BiometricImage(record_type=14, compression="PNG", image_bytes=_png_bytes())

    decoded = ImageDecoder().decode(image)

    assert decoded.decode_status == "decoded"
    assert decoded.decoded_pil_image is not None
    assert (decoded.width, decoded.height, decoded.bit_depth) == (12, 18, 8)


def test_signature_selects_decoder_when_compression_is_missing() -> None:
    image = BiometricImage(record_type=14, image_bytes=_png_bytes())

    decoded = ImageDecoder().decode(image)

    assert decoded.decode_status == "decoded"
    assert decoded.compression == "PNG"


def test_unsupported_wsq_does_not_crash() -> None:
    decoder = ImageDecoder()
    decoder.wsq.plugin_modules = ("module_that_does_not_exist_for_test",)
    image = BiometricImage(record_type=14, compression="WSQ", image_bytes=b"\xff\xa0test")

    decoded = decoder.decode(image)

    assert decoded.decode_status == "unsupported"
    assert WSQ_UNAVAILABLE_MESSAGE in decoded.warnings
    assert WSQ_UNAVAILABLE_MESSAGE == "WSQ decoder not configured."


def test_unknown_compression_is_reported() -> None:
    image = BiometricImage(record_type=14, compression="CUSTOM", image_bytes=b"payload")

    decoded = ImageDecoder().decode(image)

    assert decoded.decode_status == "unsupported"
    assert "CUSTOM" in decoded.warnings[-1]


def test_unavailable_jpeg2000_support_is_reported_as_unsupported() -> None:
    image = BiometricImage(record_type=14, compression="JPEG2000", image_bytes=b"not-jp2")

    decoded = ImageDecoder().decode(image)

    assert decoded.decode_status == "unsupported"
    assert decoded.warnings[-1] == "JPEG2000 decoder not configured."


def test_pillow_safety_failure_is_reported_without_raw_exception_details(
    monkeypatch,
) -> None:
    image = BiometricImage(record_type=14, compression="PNG", image_bytes=b"payload")
    monkeypatch.setattr(
        "nist_biometric_viewer.imaging.pillow_decoder.Image.open",
        lambda *_args: (_ for _ in ()).throw(
            Image.DecompressionBombError("sensitive decoder details")
        ),
    )

    decoded = ImageDecoder().decode(image)

    assert decoded.decode_status == "failed"
    assert decoded.warnings[-1] == "Image not decoded: DecompressionBombError."
    assert "sensitive decoder details" not in decoded.warnings[-1]


def test_wsq_profile_label_is_normalized() -> None:
    assert normalize_compression("WSQ20") == "WSQ"
