"""Record-to-domain conversion helpers."""

from __future__ import annotations

from nist_fingerprint_comparator.core.models import BiometricImage, NistRecord
from nist_fingerprint_comparator.core.pairing import finger_details

from .constants import COMPRESSION_NAMES
from .fields import public_metadata, scalar_int, scalar_text


def biometric_from_tagged(record: NistRecord) -> BiometricImage:
    """Build a biometric image model from a Type-13/14/15 tagged record."""
    prefix = str(record.record_type)
    fields = record.fields
    position = _first_component(scalar_text(fields, f"{prefix}.013"))
    finger_name, hand = finger_details(position)
    compression_raw = scalar_text(fields, f"{prefix}.011")
    image_bytes = fields.get(f"{prefix}.999")
    if not isinstance(image_bytes, bytes):
        image_bytes = None

    return BiometricImage(
        record_type=record.record_type,
        idc=record.idc,
        finger_position_code=position,
        finger_name=finger_name,
        hand=hand,  # type: ignore[arg-type]
        impression_type=scalar_text(fields, f"{prefix}.003"),
        width=scalar_int(fields, f"{prefix}.006"),
        height=scalar_int(fields, f"{prefix}.007"),
        bit_depth=scalar_int(fields, f"{prefix}.012"),
        resolution_ppi=_resolution_ppi(record),
        compression=normalize_compression(compression_raw),
        capture_date=scalar_text(fields, f"{prefix}.005"),
        source_agency=scalar_text(fields, f"{prefix}.004"),
        quality=scalar_text(fields, f"{prefix}.024"),
        raw_metadata=public_metadata(fields),
        image_bytes=image_bytes,
        decode_status="not_present" if image_bytes is None else "unsupported",
        warnings=list(record.warnings),
    )


def biometric_from_binary_type4(record: NistRecord, raw_record: bytes) -> BiometricImage:
    """Extract the standard fixed header and payload from a legacy Type-4 record."""
    position = str(raw_record[6]) if len(raw_record) > 6 else None
    finger_name, hand = finger_details(position)
    payload = raw_record[18:] if len(raw_record) > 18 else None
    compression_code = raw_record[17] if len(raw_record) > 17 else None
    compression = {0: "RAW", 1: "WSQ", 2: "JPEG", 3: "JPEG2000"}.get(compression_code)
    warnings = list(record.warnings)
    if compression is None and compression_code is not None:
        warnings.append(f"Unsupported Type-4 compression code: {compression_code}.")
    return BiometricImage(
        record_type=4,
        idc=record.idc,
        finger_position_code=position,
        finger_name=finger_name,
        hand=hand,  # type: ignore[arg-type]
        impression_type=str(raw_record[5]) if len(raw_record) > 5 else None,
        width=int.from_bytes(raw_record[13:15], "big") if len(raw_record) >= 15 else None,
        height=int.from_bytes(raw_record[15:17], "big") if len(raw_record) >= 17 else None,
        bit_depth=8,
        resolution_ppi=({0: 500, 1: 1000}.get(raw_record[12]) if len(raw_record) > 12 else None),
        compression=compression,
        raw_metadata=public_metadata(record.fields),
        image_bytes=payload,
        decode_status="unsupported" if payload else "not_present",
        warnings=warnings,
    )


def normalize_compression(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if normalized.startswith("WSQ"):
        return "WSQ"
    return COMPRESSION_NAMES.get(normalized, normalized)


def _first_component(value: str | None) -> str | None:
    if not value:
        return None
    for separator in (" | ", ",", ":", ";"):
        value = value.split(separator, maxsplit=1)[0]
    return value.strip() or None


def _resolution_ppi(record: NistRecord) -> int | None:
    prefix = str(record.record_type)
    units = scalar_int(record.fields, f"{prefix}.008")
    horizontal = scalar_int(record.fields, f"{prefix}.009")
    vertical = scalar_int(record.fields, f"{prefix}.010")
    samples = [value for value in (horizontal, vertical) if value]
    if not samples:
        return None
    scale = sum(samples) / len(samples)
    if units == 2:
        scale *= 2.54
    return round(scale)
