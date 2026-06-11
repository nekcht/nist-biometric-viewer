"""Data models shared by parsers, decoders, and the UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from PIL import Image

Hand = Literal["left", "right", "unknown"]
DecodeStatus = Literal["decoded", "unsupported", "failed", "not_present"]


@dataclass(slots=True)
class NistRecord:
    record_type: int
    length: int | None = None
    idc: str | None = None
    fields: dict[str, object] = field(default_factory=dict)
    raw_start_offset: int | None = None
    raw_end_offset: int | None = None
    warnings: list[str] = field(default_factory=list)


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
    raw_metadata: dict[str, object] = field(default_factory=dict)
    image_bytes: bytes | None = field(default=None, repr=False)
    decoded_pil_image: Image.Image | None = field(default=None, repr=False)
    decode_status: DecodeStatus = "not_present"
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NistTransaction:
    source_path: Path
    version: str | None = None
    transaction_type: str | None = None
    records: list[NistRecord] = field(default_factory=list)
    biometric_images: list[BiometricImage] = field(default_factory=list)
    transaction_metadata: dict[str, str] = field(default_factory=dict)
    descriptive_metadata: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def reference_number(self) -> str:
        """Return the user-defined Type-2 MN1/2.012 reference number, when present."""
        return self.descriptive_metadata.get("MN1", "").strip()


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
