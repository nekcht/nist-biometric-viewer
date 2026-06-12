"""Warning-based, pragmatic ANSI/NIST parser."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from nist_biometric_viewer.core.errors import NistParseError
from nist_biometric_viewer.core.models import NistRecord, NistTransaction

from .constants import SUPPORTED_RECORD_TYPES, SUPPORTED_TAGGED_IMAGE_RECORDS
from .fields import FIRST_LENGTH_RE, TAG_RE, decode_text, scalar_text
from .records import biometric_from_binary_type4, biometric_from_tagged
from .separators import FS, GS_BYTES

LOGGER = logging.getLogger(__name__)
TYPE_2_REFERENCE_NUMBER_FIELD = "2.012"
MN1_RE = re.compile(
    rb"(?<![A-Za-z0-9])MN1\s*(?:[:=]|\x1e|\x1f)\s*"
    rb"(?P<value>[^\x1c\x1d\x1e\x1f]+)",
    re.IGNORECASE,
)


class NistParser:
    """Parse common tagged ANSI/NIST records while retaining partial results."""

    def parse_file(self, path: str | Path) -> NistTransaction:
        source = Path(path)
        try:
            data = source.read_bytes()
        except OSError as exc:
            raise NistParseError(f"Record read failed: {exc}") from exc
        return self.parse_bytes(data, source_path=source)

    def parse_bytes(
        self, data: bytes, source_path: str | Path = Path("<memory>")
    ) -> NistTransaction:
        transaction = NistTransaction(source_path=Path(source_path))
        if not data:
            transaction.warnings.append("Selected record is empty.")
            return transaction

        for start, end, raw_record, split_warning in self._iter_records(data):
            try:
                record = self._parse_record(raw_record, start, end)
            except Exception as exc:  # Defensive boundary for malformed transactions.
                exception_type = type(exc).__name__
                LOGGER.warning(
                    "Record at offset %s could not be parsed: %s",
                    start,
                    exception_type,
                )
                transaction.warnings.append(
                    f"Record at offset {start} not parsed: {exception_type}."
                )
                continue
            if split_warning:
                record.warnings.append(split_warning)
            transaction.records.append(record)
            self._collect_record(transaction, record, raw_record)

        if not transaction.records:
            transaction.warnings.append("Unsupported record.")
        return transaction

    def _iter_records(self, data: bytes):
        offset = 0
        size = len(data)
        while offset < size:
            # A binary Type-4 record commonly begins with zero-valued length bytes.
            while offset < size and data[offset] in {FS, 10, 13}:
                offset += 1
            if offset >= size:
                return

            length_match = FIRST_LENGTH_RE.match(data[offset : offset + 80])
            if length_match:
                declared = int(length_match.group("length"))
                if declared > 0 and offset + declared <= size:
                    end = offset + declared
                    yield offset, end, data[offset:end], None
                    offset = end
                    continue

            if self._looks_like_binary_type4(data, offset):
                declared = int.from_bytes(data[offset : offset + 4], "big")
                if offset + declared <= size:
                    end = offset + declared
                    yield offset, end, data[offset:end], None
                    offset = end
                    continue

            separator = data.find(bytes([FS]), offset)
            end = size if separator < 0 else separator + 1
            warning = "Record boundary inferred; length unavailable."
            yield offset, end, data[offset:end], warning
            offset = end

    def _parse_record(self, raw: bytes, start: int, end: int) -> NistRecord:
        tag_match = TAG_RE.match(raw)
        if tag_match:
            record_type = int(tag_match.group("type"))
            fields, warnings = self._parse_tagged_fields(raw, record_type)
            idc = scalar_text(fields, f"{record_type}.002")
            declared_length = _safe_int(scalar_text(fields, f"{record_type}.001"))
            record = NistRecord(
                record_type=record_type,
                length=declared_length or len(raw),
                idc=idc,
                fields=fields,
                raw_start_offset=start,
                raw_end_offset=end,
                warnings=warnings,
            )
        elif self._looks_like_binary_type4(raw, 0):
            record = NistRecord(
                record_type=4,
                length=int.from_bytes(raw[:4], "big"),
                idc=str(raw[4]) if len(raw) > 4 else None,
                fields={"4.001": len(raw), "4.002": str(raw[4]) if len(raw) > 4 else None},
                raw_start_offset=start,
                raw_end_offset=end,
                warnings=[],
            )
        else:
            return NistRecord(
                record_type=0,
                length=len(raw),
                raw_start_offset=start,
                raw_end_offset=end,
                warnings=["Record type unavailable."],
            )

        if record.record_type not in SUPPORTED_RECORD_TYPES:
            record.warnings.append(
                f"Unsupported record type: Type-{record.record_type}."
            )
        return record

    def _parse_tagged_fields(
        self, raw: bytes, record_type: int
    ) -> tuple[dict[str, object], list[str]]:
        fields: dict[str, object] = {}
        warnings: list[str] = []
        image_tag = f"{record_type}.999:".encode()
        image_index = raw.find(image_tag)
        text_end = image_index if image_index >= 0 else len(raw)

        for chunk in raw[:text_end].rstrip(bytes([FS])).split(GS_BYTES):
            chunk = chunk.strip(bytes([FS]))
            match = TAG_RE.match(chunk)
            if not match:
                if chunk:
                    warnings.append("Tagged field skipped.")
                continue
            field_number = match.group("number").decode().zfill(3)
            key = f"{int(match.group('type'))}.{field_number}"
            fields[key] = decode_text(chunk[match.end() :])

        if image_index >= 0:
            payload_start = image_index + len(image_tag)
            payload = raw[payload_start:]
            if payload.endswith(bytes([FS])):
                payload = payload[:-1]
            fields[f"{record_type}.999"] = payload
            if not payload:
                warnings.append(f"Type-{record_type} image data is empty.")
        return fields, warnings

    def _collect_record(
        self, transaction: NistTransaction, record: NistRecord, raw_record: bytes
    ) -> None:
        record_type = record.record_type
        if record_type == 1:
            transaction.version = scalar_text(record.fields, "1.002")
            transaction.transaction_type = scalar_text(record.fields, "1.004")
            transaction.transaction_metadata.update(_string_fields(record.fields))
        elif record_type == 2:
            transaction.descriptive_metadata.update(_string_fields(record.fields))
            reference_number = _type_2_reference_number(record.fields, raw_record)
            if reference_number:
                transaction.descriptive_metadata["MN1"] = reference_number
        elif record_type in SUPPORTED_TAGGED_IMAGE_RECORDS:
            transaction.biometric_images.append(biometric_from_tagged(record))
        elif record_type == 4:
            transaction.biometric_images.append(biometric_from_binary_type4(record, raw_record))

        for warning in record.warnings:
            transaction.warnings.append(f"Type-{record_type}: {warning}")

    @staticmethod
    def _looks_like_binary_type4(data: bytes, offset: int) -> bool:
        if len(data) - offset < 18:
            return False
        declared = int.from_bytes(data[offset : offset + 4], "big")
        return 18 <= declared <= len(data) - offset and data[offset : offset + 1] == b"\x00"


def _string_fields(fields: dict[str, object]) -> dict[str, str]:
    return {key: str(value) for key, value in fields.items() if not isinstance(value, bytes)}


def _type_2_reference_number(
    fields: dict[str, object],
    raw_record: bytes,
) -> str | None:
    reference_number = scalar_text(fields, TYPE_2_REFERENCE_NUMBER_FIELD)
    if reference_number:
        return reference_number
    match = MN1_RE.search(raw_record)
    if match is None:
        return None
    return decode_text(match.group("value")) or None


def _safe_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None
