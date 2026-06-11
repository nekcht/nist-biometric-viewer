"""Controlled loading failures and defensive source-file validation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from .errors import NistComparatorError

LoadingStage = Literal[
    "file_selection",
    "archive_detection",
    "archive_extraction",
    "archive_validation",
    "temp_directory",
    "nist_parsing",
    "image_decoding",
    "reference_selection",
    "comparison_loading",
    "ui_transition",
    "unknown",
]

MAX_SOURCE_FILE_BYTES = 1024 * 1024 * 1024
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_BYTES_LITERAL = re.compile(r"""(?s)\bb(['"]).*?\1""")
_BASE64_LIKE = re.compile(r"\b[A-Za-z0-9+/]{80,}={0,2}\b")


class LoadingError(NistComparatorError):
    """A loading failure safe to pass from workers to the user interface."""

    def __init__(
        self,
        title: str,
        user_message: str,
        *,
        stage: LoadingStage,
        technical_message: str | None = None,
        source_name: str | None = None,
        recoverable: bool = True,
        original_exception_type: str | None = None,
    ) -> None:
        super().__init__(technical_message or user_message)
        self.title = title
        self.user_message = user_message
        self.technical_message = sanitize_diagnostic(technical_message)
        self.stage = stage
        self.source_name = sanitize_source_name(source_name)
        self.recoverable = recoverable
        self.original_exception_type = sanitize_diagnostic(original_exception_type)

    @property
    def technical_details(self) -> str:
        details = [f"Stage: {self.stage}"]
        if self.source_name:
            details.append(f"Source: {self.source_name}")
        if self.original_exception_type:
            details.append(f"Reason: {self.original_exception_type}")
        if self.technical_message:
            details.append(self.technical_message)
        return "\n".join(details)


def loading_error_from_exception(
    exception: Exception,
    *,
    title: str,
    user_message: str,
    stage: LoadingStage,
    source: Path | str | None = None,
) -> LoadingError:
    if isinstance(exception, LoadingError):
        return exception
    return LoadingError(
        title,
        user_message,
        stage=stage,
        technical_message=str(exception),
        source_name=_source_name(source),
        original_exception_type=type(exception).__name__,
    )


def validate_loading_file(
    path: Path,
    *,
    stage: LoadingStage,
    maximum_bytes: int = MAX_SOURCE_FILE_BYTES,
) -> None:
    """Reject missing, empty, unreadable, or excessive files before loading."""
    source_name = path.name
    try:
        if not path.exists():
            raise LoadingError(
                "File not found",
                "The selected file could not be found.",
                stage=stage,
                source_name=source_name,
            )
        if not path.is_file():
            raise LoadingError(
                "Unsupported selection",
                "Select NIST records, a ZIP archive, or a RAR archive.",
                stage=stage,
                source_name=source_name,
            )
        size = path.stat().st_size
        if size <= 0:
            raise LoadingError(
                "File is empty",
                "The selected file is empty.",
                stage=stage,
                source_name=source_name,
            )
        if size > maximum_bytes:
            raise LoadingError(
                "File is too large",
                "The selected file is too large to load safely.",
                stage=stage,
                source_name=source_name,
                technical_message=f"Size exceeds {maximum_bytes} bytes.",
            )
        with path.open("rb") as source:
            source.read(1)
    except LoadingError:
        raise
    except OSError as exc:
        raise LoadingError(
            "File cannot be read",
            "The selected file cannot be read.",
            stage=stage,
            source_name=source_name,
            technical_message=str(exc),
            original_exception_type=type(exc).__name__,
        ) from exc


def sanitize_source_name(value: str | None) -> str | None:
    if not value:
        return None
    return sanitize_diagnostic(Path(value).name, maximum_length=160)


def sanitize_diagnostic(
    value: object | None,
    *,
    maximum_length: int = 500,
) -> str | None:
    """Return one-line diagnostics without bytes, paths, or control characters."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{type(value).__name__} length={len(value)}>"
    text = _CONTROL_CHARACTERS.sub(" ", str(value))
    text = _BYTES_LITERAL.sub("<bytes omitted>", text)
    text = _BASE64_LIKE.sub("<encoded data omitted>", text)
    text = re.sub(r"(?i)(?:[a-z]:\\|/)[^\s]+", "<path>", text)
    text = " ".join(text.split())
    return text[:maximum_length] or None


def _source_name(source: Path | str | None) -> str | None:
    if source is None:
        return None
    return Path(source).name
