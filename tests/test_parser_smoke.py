import logging
from io import BytesIO
from pathlib import Path

from PIL import Image

from nist_biometric_viewer.imaging.decoder import ImageDecoder
from nist_biometric_viewer.nist.parser import NistParser
from nist_biometric_viewer.nist.separators import FS_BYTES, GS_BYTES


def _tagged_record(record_type: int, fields: list[tuple[str, bytes]]) -> bytes:
    length = 0
    while True:
        parts = [f"{record_type}.001:{length}".encode()]
        parts.extend(f"{record_type}.{number}:".encode() + value for number, value in fields)
        record = GS_BYTES.join(parts) + FS_BYTES
        if len(record) == length:
            return record
        length = len(record)


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("L", (1, 1), 0).save(output, format="PNG")
    return output.getvalue()


def test_parser_smoke_with_minimal_tagged_records() -> None:
    type_1 = _tagged_record(1, [("002", b"0500"), ("004", b"CAR")])
    type_2 = _tagged_record(
        2,
        [("002", b"1"), ("012", b"GR2SAP20260604921537")],
    )
    type_14 = _tagged_record(
        14,
        [
            ("002", b"2"),
            ("003", b"0"),
            ("004", b"AGENCY"),
            ("005", b"20260610"),
            ("006", b"800"),
            ("007", b"1000"),
            ("008", b"1"),
            ("009", b"500"),
            ("010", b"500"),
            ("011", b"PNG"),
            ("012", b"8"),
            ("013", b"7"),
            ("999", b"\x89PNG\r\n\x1a\nsynthetic\x1cinside-payload"),
        ],
    )

    transaction = NistParser().parse_bytes(type_1 + type_2 + type_14, Path("sample.an2"))

    assert len(transaction.records) == 3
    assert transaction.version == "0500"
    assert transaction.transaction_type == "CAR"
    assert transaction.descriptive_metadata["2.012"] == "GR2SAP20260604921537"
    assert transaction.descriptive_metadata["MN1"] == "GR2SAP20260604921537"
    assert transaction.reference_number == "GR2SAP20260604921537"
    image = transaction.biometric_images[0]
    assert image.record_type == 14
    assert image.finger_name == "Left Index"
    assert image.hand == "left"
    assert image.width == 800
    assert image.height == 1000
    assert image.resolution_ppi == 500
    assert image.image_bytes.startswith(b"\x89PNG")
    assert b"\x1cinside-payload" in image.image_bytes
    summary = transaction.compatibility_summary
    assert summary.status == "Compatible"
    assert summary.version == "0500"
    assert summary.transaction_type == "CAR"
    assert summary.total_records == 3
    assert summary.supported_biometric_image_records == 1
    assert summary.unsupported_record_count == 0
    assert summary.warning_count == 0


def test_parser_returns_warnings_for_unrecognized_data() -> None:
    transaction = NistParser().parse_bytes(b"not-a-nist-record", Path("bad.dat"))

    assert len(transaction.records) == 1
    assert transaction.records[0].record_type == 0
    assert transaction.warnings
    assert transaction.compatibility_summary.status == "Unsupported"
    assert transaction.compatibility_summary.unsupported_record_count == 1
    assert "No supported biometric images found." in transaction.warnings


def test_parser_extracts_literal_type_2_mn1_user_defined_key() -> None:
    type_2 = _tagged_record(2, [("002", b"1"), ("MN1", b"UNIQUE-REFERENCE")])

    transaction = NistParser().parse_bytes(type_2, Path("sample.nist"))

    assert transaction.reference_number == "UNIQUE-REFERENCE"
    assert transaction.descriptive_metadata["MN1"] == "UNIQUE-REFERENCE"


def test_empty_input_is_nonfatal() -> None:
    transaction = NistParser().parse_bytes(b"")

    assert transaction.records == []
    assert transaction.warnings == ["Selected record is empty."]
    assert transaction.compatibility_summary.status == "Failed"


def test_legacy_two_digit_type1_fields_are_canonicalized() -> None:
    type_1 = b"1.01:40\x1d1.02:0200\x1d1.04:ATP" + b" " * 11 + FS_BYTES

    transaction = NistParser().parse_bytes(type_1)

    assert transaction.records[0].record_type == 1
    assert transaction.version == "0200"
    assert transaction.transaction_type == "ATP"
    assert transaction.transaction_metadata["1.001"] == "40"


def test_binary_type4_starting_with_zero_length_bytes_is_parsed() -> None:
    payload = b"\xff\xa0synthetic-wsq"
    length = 18 + len(payload)
    header = (
        length.to_bytes(4, "big")
        + bytes([1, 0])
        + bytes([2, 255, 255, 255, 255, 255])
        + bytes([0])
        + (800).to_bytes(2, "big")
        + (1000).to_bytes(2, "big")
        + bytes([1])
    )

    transaction = NistParser().parse_bytes(header + payload)

    assert len(transaction.records) == 1
    assert transaction.records[0].record_type == 4
    image = transaction.biometric_images[0]
    assert image.finger_position_code == "2"
    assert image.width == 800
    assert image.height == 1000
    assert image.resolution_ppi == 500
    assert image.compression == "WSQ"
    assert image.image_bytes == payload
    assert transaction.compatibility_summary.status == "Partial"
    assert transaction.compatibility_summary.partial_record_types == (4,)


def test_unknown_and_missing_type_1_versions_remain_nonfatal() -> None:
    image = _tagged_record(
        14,
        [
            ("002", b"2"),
            ("011", b"PNG"),
            ("013", b"7"),
            ("999", b"synthetic-image"),
        ],
    )
    unknown_version = NistParser().parse_bytes(
        _tagged_record(1, [("002", b"9999"), ("004", b"CUSTOM")]) + image
    )
    missing_version = NistParser().parse_bytes(
        _tagged_record(1, [("004", b"CUSTOM")]) + image
    )

    assert unknown_version.version == "9999"
    assert unknown_version.compatibility_summary.status == "Compatible"
    assert missing_version.version is None
    assert missing_version.compatibility_summary.status == "Compatible"


def test_valid_type_14_image_remains_compatible_after_decode() -> None:
    transaction = NistParser().parse_bytes(
        _tagged_record(1, [("002", b"0500"), ("004", b"CAR")])
        + _tagged_record(
            14,
            [("002", b"2"), ("011", b"PNG"), ("013", b"7"), ("999", _png_bytes())],
        )
    )

    ImageDecoder().decode(transaction.biometric_images[0])

    assert transaction.biometric_images[0].decode_status == "decoded"
    assert transaction.compatibility_summary.status == "Compatible"
    assert transaction.compatibility_summary.warning_count == 0


def test_unsupported_record_is_visible_retained_and_makes_transaction_partial() -> None:
    type_1 = _tagged_record(1, [("002", b"0500"), ("004", b"CAR")])
    type_14 = _tagged_record(14, [("002", b"2"), ("999", b"safe-image")])
    type_10 = _tagged_record(
        10,
        [("002", b"3"), ("003", b"FACE"), ("999", b"RAW-BIOMETRIC-DATA")],
    )

    transaction = NistParser().parse_bytes(type_1 + type_14 + type_10)

    unsupported = transaction.records[-1]
    summary = transaction.compatibility_summary
    assert unsupported.record_type == 10
    assert unsupported.support_status == "unsupported"
    assert unsupported.length == len(type_10)
    assert unsupported.idc == "3"
    assert unsupported.raw_start_offset is not None
    assert unsupported.raw_end_offset is not None
    assert unsupported.warnings == ["Unsupported Type-10 record."]
    assert summary.status == "Partial"
    assert summary.unsupported_record_count == 1
    assert summary.unsupported_record_types == (10,)
    assert summary.unsupported_records_text == "Type-10"
    assert "Unsupported Type-10 record." in transaction.warnings
    assert "RAW-BIOMETRIC-DATA" not in summary.compact_text()
    assert "RAW-BIOMETRIC-DATA" not in repr(summary)


def test_parser_attaches_modality_classification_from_records_and_fields() -> None:
    type_13_palm = _tagged_record(
        13,
        [("002", b"1"), ("013", b"21"), ("999", b"latent-palm-image")],
    )
    type_14_finger = _tagged_record(
        14,
        [("002", b"2"), ("013", b"7"), ("999", b"fingerprint-image")],
    )
    type_17_iris = _tagged_record(17, [("002", b"3"), ("999", b"iris-image")])

    transaction = NistParser().parse_bytes(type_13_palm + type_14_finger + type_17_iris)

    assert transaction.records[0].biometric_classification.modality == "palm"
    assert transaction.records[1].biometric_classification.modality == "fingerprint"
    assert transaction.records[2].biometric_classification.modality == "iris"
    assert transaction.biometric_images[0].biometric_classification.modality == "palm"
    assert transaction.biometric_images[1].biometric_classification.modality == "fingerprint"


def test_unsupported_only_transaction_reports_unsupported_status() -> None:
    transaction = NistParser().parse_bytes(
        _tagged_record(17, [("002", b"4"), ("003", b"unsupported")])
    )

    summary = transaction.compatibility_summary
    assert summary.status == "Unsupported"
    assert summary.supported_biometric_image_records == 0
    assert summary.unsupported_record_count == 1
    assert summary.unsupported_record_types == (17,)
    assert "Unsupported Type-17 record." in transaction.warnings
    assert "No supported biometric images found." in transaction.warnings


def test_parser_failure_summary_and_logs_do_not_expose_raw_input(caplog) -> None:
    class FailingParser(NistParser):
        def _parse_record(self, raw: bytes, start: int, end: int):
            raise ValueError(f"unsafe payload: {raw!r}")

    raw = _tagged_record(14, [("002", b"2"), ("999", b"SECRET-BIOMETRIC-BYTES")])

    with caplog.at_level(logging.WARNING, logger="nist_biometric_viewer.nist.parser"):
        transaction = FailingParser().parse_bytes(raw)

    assert transaction.compatibility_summary.status == "Failed"
    assert "SECRET-BIOMETRIC-BYTES" not in transaction.compatibility_summary.compact_text()
    assert "SECRET-BIOMETRIC-BYTES" not in "\n".join(transaction.warnings)
    assert "SECRET-BIOMETRIC-BYTES" not in caplog.text
