"""Source-file filtering for the current fingerprint review workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nist_biometric_viewer.core.biometrics import (
    FINGERPRINT_REVIEW,
    apply_biometric_workflow_filter,
)
from nist_biometric_viewer.core.loading import LoadingError
from nist_biometric_viewer.nist.parser import NistParser


@dataclass(frozen=True, slots=True)
class FingerprintSourceFilterResult:
    fingerprint_paths: list[Path]
    skipped_paths: list[Path]

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_paths)


def filter_fingerprint_source_paths(
    paths: list[Path],
) -> FingerprintSourceFilterResult:
    """Keep only source files containing fingerprint-compatible impressions."""
    parser = NistParser()
    fingerprint_paths: list[Path] = []
    skipped_paths: list[Path] = []
    for path in paths:
        try:
            transaction = parser.parse_file(path)
        except Exception as exc:
            raise LoadingError(
                "Record could not be loaded",
                "The selected NIST record could not be parsed.",
                stage="nist_parsing",
                source_name=path.name,
                technical_message=str(exc),
                original_exception_type=type(exc).__name__,
            ) from exc
        apply_biometric_workflow_filter(transaction, FINGERPRINT_REVIEW)
        if transaction.biometric_images:
            fingerprint_paths.append(path)
        else:
            skipped_paths.append(path)
    return FingerprintSourceFilterResult(
        fingerprint_paths=fingerprint_paths,
        skipped_paths=skipped_paths,
    )
