"""Helpers for tolerant tagged-field handling."""

from __future__ import annotations

import re
from typing import Any

from .separators import RS_BYTES, US_BYTES

TAG_RE = re.compile(rb"(?P<type>\d{1,2})\.(?P<number>\d{2,3}):")
FIRST_LENGTH_RE = re.compile(rb"^(?P<type>\d{1,2})\.0{1,2}1:(?P<length>\d+)")


def decode_text(value: bytes) -> str:
    """Decode field text while preserving subfield structure readably."""
    return (
        value.replace(RS_BYTES, b" | ")
        .replace(US_BYTES, b", ")
        .decode("utf-8", errors="replace")
        .strip()
    )


def scalar_text(fields: dict[str, object], key: str) -> str | None:
    value = fields.get(key)
    if value is None:
        return None
    if isinstance(value, bytes):
        return decode_text(value)
    return str(value).strip() or None


def scalar_int(fields: dict[str, object], key: str) -> int | None:
    value = scalar_text(fields, key)
    if value is None:
        return None
    match = re.search(r"\d+", value)
    if not match:
        return None
    try:
        return int(match.group())
    except ValueError:
        return None


def public_metadata(fields: dict[str, Any]) -> dict[str, object]:
    """Return fields suitable for display without exposing image bytes."""
    return {key: value for key, value in fields.items() if not key.endswith(".999")}
