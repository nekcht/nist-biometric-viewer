"""Cross-file comparison slots for every biometric impression."""

from __future__ import annotations

import re
from pathlib import Path

from .models import BiometricImage, ComparisonSession, ComparisonSlot

FINGER_CODE_DETAILS: dict[str, tuple[str, str]] = {
    "1": ("Right Thumb", "right"),
    "2": ("Right Index", "right"),
    "3": ("Right Middle", "right"),
    "4": ("Right Ring", "right"),
    "5": ("Right Little", "right"),
    "6": ("Left Thumb", "left"),
    "7": ("Left Index", "left"),
    "8": ("Left Middle", "left"),
    "9": ("Left Ring", "left"),
    "10": ("Left Little", "left"),
}

ADDITIONAL_POSITION_DETAILS: dict[str, tuple[str, str]] = {
    "0": ("Unmapped biometric impression", "unknown"),
    "11": ("Plain right thumb", "right"),
    "12": ("Plain left thumb", "left"),
    "13": ("Plain right four-finger slap", "right"),
    "14": ("Plain left four-finger slap", "left"),
    "15": ("Plain two-thumb impression", "unknown"),
    "20": ("Unknown palm impression", "unknown"),
    "21": ("Right full palm", "right"),
    "22": ("Right writer's palm", "right"),
    "23": ("Left full palm", "left"),
    "24": ("Left writer's palm", "left"),
    "25": ("Right lower palm", "right"),
    "26": ("Right upper palm", "right"),
    "27": ("Left lower palm", "left"),
    "28": ("Left upper palm", "left"),
}

STANDARD_POSITION_CODES = tuple(str(code) for code in range(1, 11))


def files_have_same_content(file_a_path: Path, file_b_path: Path) -> bool:
    """Return whether two readable files contain exactly the same bytes."""
    try:
        if file_a_path.samefile(file_b_path):
            return True
        if file_a_path.stat().st_size != file_b_path.stat().st_size:
            return False
        with file_a_path.open("rb") as file_a, file_b_path.open("rb") as file_b:
            while True:
                file_a_chunk = file_a.read(1024 * 1024)
                file_b_chunk = file_b.read(1024 * 1024)
                if file_a_chunk != file_b_chunk:
                    return False
                if not file_a_chunk:
                    return True
    except OSError:
        return False


def finger_details(position_code: str | int | None) -> tuple[str, str]:
    """Map a common ANSI/NIST position code to a display name and hand."""
    if position_code is None:
        return "Unmapped biometric impression", "unknown"
    code = str(position_code).strip()
    if code in FINGER_CODE_DETAILS:
        return FINGER_CODE_DETAILS[code]
    if code in ADDITIONAL_POSITION_DETAILS:
        return ADDITIONAL_POSITION_DETAILS[code]
    if code:
        return "Unmapped biometric impression", "unknown"
    return "Unmapped biometric impression", "unknown"


def build_cross_file_comparison(
    file_a_images: list[BiometricImage],
    file_b_images: list[BiometricImage],
) -> ComparisonSession:
    """Build File A versus File B rows while preserving every biometric image."""
    session = ComparisonSession()
    file_a_by_code, file_a_unmapped = _group_images(file_a_images)
    file_b_by_code, file_b_unmapped = _group_images(file_b_images)
    all_codes = set(file_a_by_code) | set(file_b_by_code)

    for code in sorted(all_codes, key=_position_sort_key):
        file_a_candidates = _ranked(file_a_by_code.get(code, []))
        file_b_candidates = _ranked(file_b_by_code.get(code, []))
        count = max(len(file_a_candidates), len(file_b_candidates))
        name = finger_details(code)[0]
        for index in range(count):
            warnings = _duplicate_row_warnings(
                name,
                index,
                len(file_a_candidates),
                len(file_b_candidates),
            )
            session.comparison_slots.append(
                ComparisonSlot(
                    position_code=code,
                    finger_name=_row_name(name, index, count),
                    file_a_image=_at(file_a_candidates, index),
                    file_b_image=_at(file_b_candidates, index),
                    warnings=warnings,
                )
            )
            session.warnings.extend(warnings)

    for source, images in (("File A", file_a_unmapped), ("File B", file_b_unmapped)):
        for index, image in enumerate(images, start=1):
            session.comparison_slots.append(
                ComparisonSlot(
                    position_code=None,
                    finger_name=f"Unmapped biometric impression {index} ({source})",
                    file_a_image=image if source == "File A" else None,
                    file_b_image=image if source == "File B" else None,
                )
            )
    return session


def _group_images(
    images: list[BiometricImage],
) -> tuple[dict[str, list[tuple[int, BiometricImage]]], list[BiometricImage]]:
    by_code: dict[str, list[tuple[int, BiometricImage]]] = {}
    unmapped: list[BiometricImage] = []
    for index, image in enumerate(images):
        code = (image.finger_position_code or "").strip()
        if code:
            by_code.setdefault(code, []).append((index, image))
        else:
            unmapped.append(image)
    return by_code, unmapped


def _ranked(candidates: list[tuple[int, BiometricImage]]) -> list[BiometricImage]:
    return [image for _, image in sorted(candidates, key=_candidate_rank, reverse=True)]


def _at(images: list[BiometricImage], index: int) -> BiometricImage | None:
    return images[index] if index < len(images) else None


def _row_name(name: str, index: int, count: int) -> str:
    return f"{name} - record {index + 1}" if count > 1 else name


def _duplicate_row_warnings(
    name: str,
    index: int,
    file_a_count: int,
    file_b_count: int,
) -> list[str]:
    if file_a_count <= 1 and file_b_count <= 1:
        return []
    return [
        f"Multiple records exist for {name}; record {index + 1} is displayed as a separate "
        "cross-file comparison row."
    ]


def _position_sort_key(code: str) -> tuple[int, int | str]:
    if code in STANDARD_POSITION_CODES:
        return 0, int(code)
    if code.isdigit():
        return 1, int(code)
    return 2, code


def _candidate_rank(candidate: tuple[int, BiometricImage]) -> tuple[int, int, int, int]:
    index, image = candidate
    decoded = int(image.decode_status == "decoded")
    resolution = image.resolution_ppi if image.resolution_ppi is not None else -1
    quality = _parse_quality(image.quality)
    return decoded, resolution, quality, -index


def _parse_quality(value: str | None) -> int:
    if not value:
        return -1
    match = re.search(r"-?\d+", value)
    return int(match.group()) if match else -1
