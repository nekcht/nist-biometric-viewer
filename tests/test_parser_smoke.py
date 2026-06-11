from pathlib import Path

from nist_fingerprint_comparator.nist.parser import NistParser
from nist_fingerprint_comparator.nist.separators import FS_BYTES, GS_BYTES


def _tagged_record(record_type: int, fields: list[tuple[str, bytes]]) -> bytes:
    length = 0
    while True:
        parts = [f"{record_type}.001:{length}".encode()]
        parts.extend(f"{record_type}.{number}:".encode() + value for number, value in fields)
        record = GS_BYTES.join(parts) + FS_BYTES
        if len(record) == length:
            return record
        length = len(record)


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


def test_parser_returns_warnings_for_unrecognized_data() -> None:
    transaction = NistParser().parse_bytes(b"not-a-nist-record", Path("bad.dat"))

    assert len(transaction.records) == 1
    assert transaction.records[0].record_type == 0
    assert transaction.warnings


def test_parser_extracts_literal_type_2_mn1_user_defined_key() -> None:
    type_2 = _tagged_record(2, [("002", b"1"), ("MN1", b"UNIQUE-REFERENCE")])

    transaction = NistParser().parse_bytes(type_2, Path("sample.nist"))

    assert transaction.reference_number == "UNIQUE-REFERENCE"
    assert transaction.descriptive_metadata["MN1"] == "UNIQUE-REFERENCE"


def test_empty_input_is_nonfatal() -> None:
    transaction = NistParser().parse_bytes(b"")

    assert transaction.records == []
    assert transaction.warnings == ["Selected record is empty."]


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
