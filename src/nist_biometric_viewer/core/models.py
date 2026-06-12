"""Data models shared by parsers, decoders, and the UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from PIL import Image

Hand = Literal["left", "right", "unknown"]
DecodeStatus = Literal["decoded", "unsupported", "failed", "not_present"]
RecordSupportStatus = Literal["supported", "partial", "unsupported"]
CompatibilityStatus = Literal["Compatible", "Partial", "Unsupported", "Failed"]


@dataclass(frozen=True, slots=True)
class CompatibilitySummary:
    status: CompatibilityStatus
    version: str | None
    transaction_type: str | None
    total_records: int
    supported_biometric_image_records: int
    unsupported_record_count: int
    unsupported_record_types: tuple[int, ...]
    unavailable_record_type_count: int
    partial_record_types: tuple[int, ...]
    warning_count: int

    @property
    def unsupported_records_text(self) -> str:
        labels = [f"Type-{record_type}" for record_type in self.unsupported_record_types]
        if self.unavailable_record_type_count:
            labels.append("Unavailable type")
        return ", ".join(labels) or "None"

    @property
    def partial_records_text(self) -> str:
        return ", ".join(
            f"Type-{record_type}" for record_type in self.partial_record_types
        ) or "None"

    def compact_text(self, separator: str = " | ") -> str:
        """Return a short summary containing no record payload or descriptive metadata."""
        lines = [f"Compatibility: {self.status}"]
        if self.version:
            lines.append(f"Version: {self.version}")
        if self.transaction_type:
            lines.append(f"Transaction: {self.transaction_type}")
        lines.extend(
            [
                f"Records: {self.total_records}",
                f"Supported images: {self.supported_biometric_image_records}",
                _unsupported_summary_text(self),
                f"Warnings: {self.warning_count}",
            ]
        )
        if self.partial_record_types:
            lines.append(f"Partial support: {self.partial_records_text}")
        return separator.join(lines)


@dataclass(slots=True)
class NistRecord:
    record_type: int
    length: int | None = None
    idc: str | None = None
    fields: dict[str, object] = field(default_factory=dict, repr=False)
    raw_start_offset: int | None = None
    raw_end_offset: int | None = None
    warnings: list[str] = field(default_factory=list)
    support_status: RecordSupportStatus = "supported"


@dataclass(slots=True)
class BiometricImage:
    record_type: int
    idc: str | None = None
    finger_position_code: str | None = None
    finger_name: str = "Unknown"
    hand: Hand = "unknown"
    impression_type: str | None = None
    width: int | None = None
    height: int | None = None
    bit_depth: int | None = None
    resolution_ppi: int | None = None
    compression: str | None = None
    capture_date: str | None = None
    source_agency: str | None = None
    quality: str | None = None
    raw_metadata: dict[str, object] = field(default_factory=dict, repr=False)
    image_bytes: bytes | None = field(default=None, repr=False)
    decoded_pil_image: Image.Image | None = field(default=None, repr=False)
    decode_status: DecodeStatus = "not_present"
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NistTransaction:
    source_path: Path = field(repr=False)
    version: str | None = None
    transaction_type: str | None = None
    records: list[NistRecord] = field(default_factory=list, repr=False)
    biometric_images: list[BiometricImage] = field(default_factory=list, repr=False)
    transaction_metadata: dict[str, str] = field(default_factory=dict, repr=False)
    descriptive_metadata: dict[str, str] = field(default_factory=dict, repr=False)
    warnings: list[str] = field(default_factory=list)
    inspection_failed: bool = field(default=False, repr=False)

    @property
    def reference_number(self) -> str:
        """Return the user-defined Type-2 MN1/2.012 reference number, when present."""
        return self.descriptive_metadata.get("MN1", "").strip()

    @property
    def compatibility_summary(self) -> CompatibilitySummary:
        unsupported_records = [
            record for record in self.records if record.support_status == "unsupported"
        ]
        partial_record_types = tuple(
            sorted(
                {
                    record.record_type
                    for record in self.records
                    if record.support_status == "partial"
                }
            )
        )
        unsupported_record_types = tuple(
            sorted({record.record_type for record in unsupported_records if record.record_type > 0})
        )
        unavailable_record_type_count = sum(
            record.record_type <= 0 for record in unsupported_records
        )
        warning_count = len(self.warnings) + self._image_only_warning_count()
        if self.inspection_failed:
            status: CompatibilityStatus = "Failed"
        elif self.biometric_images:
            status = (
                "Partial"
                if warning_count or unsupported_records or partial_record_types
                else "Compatible"
            )
        else:
            status = "Unsupported"
        return CompatibilitySummary(
            status=status,
            version=self.version,
            transaction_type=self.transaction_type,
            total_records=len(self.records),
            supported_biometric_image_records=len(self.biometric_images),
            unsupported_record_count=len(unsupported_records),
            unsupported_record_types=unsupported_record_types,
            unavailable_record_type_count=unavailable_record_type_count,
            partial_record_types=partial_record_types,
            warning_count=warning_count,
        )

    def _image_only_warning_count(self) -> int:
        transaction_warnings = set(self.warnings)
        return sum(
            warning not in transaction_warnings
            and f"Type-{image.record_type}: {warning}" not in transaction_warnings
            for image in self.biometric_images
            for warning in image.warnings
        )


@dataclass(slots=True)
class ComparisonSlot:
    position_code: str | None
    finger_name: str
    file_a_image: BiometricImage | None = None
    file_b_image: BiometricImage | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ComparisonSession:
    file_a: NistTransaction | None = None
    file_b: NistTransaction | None = None
    comparison_slots: list[ComparisonSlot] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def metadata_display_rows(image: BiometricImage) -> list[tuple[str, Any]]:
    """Return the standard compact metadata rows shown by the UI."""
    return [
        ("Record type", image.record_type),
        ("IDC", image.idc),
        ("Position code", image.finger_position_code),
        ("Finger", image.finger_name),
        ("Hand", image.hand.title()),
        ("Impression", image.impression_type),
        ("Dimensions", _dimensions(image.width, image.height)),
        ("Pixel depth", image.bit_depth),
        ("Resolution", f"{image.resolution_ppi} PPI" if image.resolution_ppi else None),
        ("Compression", image.compression),
        ("Capture date", image.capture_date),
        ("Source agency", image.source_agency),
        ("Quality", image.quality),
        ("Decode status", image.decode_status.replace("_", " ").title()),
    ]


def _dimensions(width: int | None, height: int | None) -> str | None:
    if width is None and height is None:
        return None
    return f"{width or '?'} x {height or '?'}"


def _unsupported_summary_text(summary: CompatibilitySummary) -> str:
    if not summary.unsupported_record_count:
        return "Unsupported: 0"
    return (
        f"Unsupported: {summary.unsupported_record_count} "
        f"({summary.unsupported_records_text})"
    )
