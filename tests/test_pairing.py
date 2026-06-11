from PIL import Image

from nist_fingerprint_comparator.core.models import BiometricImage
from nist_fingerprint_comparator.core.pairing import (
    build_cross_file_comparison,
    finger_details,
)


def _image(
    code: str | None,
    *,
    idc: str | None = None,
    status: str = "unsupported",
    resolution: int | None = None,
    quality: str | None = None,
) -> BiometricImage:
    name, hand = finger_details(code)
    return BiometricImage(
        record_type=14,
        idc=idc,
        finger_position_code=code,
        finger_name=name,
        hand=hand,  # type: ignore[arg-type]
        resolution_ppi=resolution,
        quality=quality,
        decoded_pil_image=Image.new("L", (10, 10)) if status == "decoded" else None,
        decode_status=status,  # type: ignore[arg-type]
    )


def test_common_and_other_position_mapping() -> None:
    assert finger_details("1") == ("Right Thumb", "right")
    assert finger_details(7) == ("Left Index", "left")
    assert finger_details("13") == ("Plain right four-finger slap", "right")
    assert finger_details("22") == ("Right writer's palm", "right")
    assert finger_details("99") == ("Unmapped biometric impression", "unknown")
    assert finger_details(None) == ("Unmapped biometric impression", "unknown")


def test_all_position_codes_are_compared_file_a_to_file_b() -> None:
    codes = [*(str(code) for code in range(1, 15)), "21", "23"]
    file_a = [_image(code, idc=f"A-{code}") for code in codes]
    file_b = [_image(code, idc=f"B-{code}") for code in codes]

    session = build_cross_file_comparison(file_a, file_b)

    assert len(session.comparison_slots) == len(codes)
    assert [slot.position_code for slot in session.comparison_slots] == codes
    assert all(slot.file_a_image.idc.startswith("A-") for slot in session.comparison_slots)
    assert all(slot.file_b_image.idc.startswith("B-") for slot in session.comparison_slots)


def test_plain_thumbs_slaps_and_palms_are_cross_file_rows() -> None:
    codes = ["11", "12", "13", "14", "21", "23"]
    file_a = [_image(code, idc=f"A-{code}") for code in codes]
    file_b = [_image(code, idc=f"B-{code}") for code in codes]

    session = build_cross_file_comparison(file_a, file_b)

    for slot, code in zip(session.comparison_slots, codes, strict=True):
        assert slot.position_code == code
        assert slot.file_a_image.idc == f"A-{code}"
        assert slot.file_b_image.idc == f"B-{code}"


def test_unknown_shared_position_code_is_compared_cross_file() -> None:
    file_a = _image("99", idc="A-99")
    file_b = _image("99", idc="B-99")

    session = build_cross_file_comparison([file_a], [file_b])

    assert len(session.comparison_slots) == 1
    assert session.comparison_slots[0].file_a_image is file_a
    assert session.comparison_slots[0].file_b_image is file_b


def test_missing_positions_remain_visible_without_same_file_pairing() -> None:
    file_a = [_image(None, idc="A-1"), _image(None, idc="A-2")]
    file_b = [_image(None, idc="B-1")]

    session = build_cross_file_comparison(file_a, file_b)

    assert len(session.comparison_slots) == 3
    assert [slot.file_b_image for slot in session.comparison_slots[:2]] == [None, None]
    assert session.comparison_slots[2].file_a_image is None
    assert session.comparison_slots[2].file_b_image is file_b[0]


def test_duplicate_records_are_ranked_and_displayed_as_separate_cross_file_rows() -> None:
    unsupported = _image("2", idc="A-low", status="unsupported", resolution=1000, quality="99")
    decoded_best = _image("2", idc="A-best", status="decoded", resolution=1000, quality="90")
    file_b_best = _image("2", idc="B-best", status="decoded", resolution=500, quality="50")

    session = build_cross_file_comparison([unsupported, decoded_best], [file_b_best])

    assert len(session.comparison_slots) == 2
    assert session.comparison_slots[0].file_a_image is decoded_best
    assert session.comparison_slots[0].file_b_image is file_b_best
    assert session.comparison_slots[1].file_a_image is unsupported
    assert session.comparison_slots[1].file_b_image is None
    assert session.comparison_slots[0].warnings == [
        "Multiple Right Index records. Best candidate selected."
    ]
    assert session.comparison_slots[1].warnings == ["Additional Right Index record."]


def test_no_biometric_images_are_dropped() -> None:
    file_a = [_image("1"), _image("1"), _image("14"), _image(None)]
    file_b = [_image("6"), _image("6"), _image("21"), _image("88")]

    session = build_cross_file_comparison(file_a, file_b)
    displayed = sum(slot.file_a_image is not None for slot in session.comparison_slots) + sum(
        slot.file_b_image is not None for slot in session.comparison_slots
    )

    assert displayed == len(file_a) + len(file_b)
