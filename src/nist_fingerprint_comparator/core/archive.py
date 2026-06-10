"""Secure extraction and classification of one-to-many comparison archives."""

from __future__ import annotations

import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from .errors import NistComparatorError
from .pairing import files_have_same_content

ARCHIVE_SUFFIX = "_files.zip"
NIST_NAME_PATTERN = re.compile(r"^(?P<reference>.+)[_-](?:fp|fi)$", re.IGNORECASE)


class ComparisonArchiveError(NistComparatorError):
    """Raised when a ZIP cannot provide one reference and at least one candidate."""


@dataclass(slots=True)
class ArchiveComparisonSelection:
    file_a_path: Path
    candidate_paths: list[Path]
    file_a_reference: str
    candidate_references: dict[Path, str]


def prepare_comparison_archive(
    archive_path: Path,
    destination: Path,
) -> ArchiveComparisonSelection:
    """Extract NIST files from an archive and identify File A from its filename."""
    file_a_reference = archive_reference(archive_path)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with ZipFile(archive_path) as archive:
            nist_paths = _extract_nist_files(archive, destination)
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise ComparisonArchiveError(f"Could not read ZIP archive: {exc}") from exc

    if not nist_paths:
        raise ComparisonArchiveError("The ZIP archive does not contain any .nist files.")

    references: dict[Path, str] = {}
    invalid_names: list[str] = []
    for path in nist_paths:
        reference = nist_reference(path)
        if reference is None:
            invalid_names.append(path.name)
        else:
            references[path] = reference
    if invalid_names:
        examples = ", ".join(sorted(invalid_names)[:3])
        raise ComparisonArchiveError(
            "Every .nist filename must end in '-fp', '_fp', '-fi', or '_fi'. "
            f"Invalid filename(s): {examples}"
        )

    file_a_matches = [
        path
        for path, reference in references.items()
        if reference.casefold() == file_a_reference.casefold()
    ]
    if not file_a_matches:
        raise ComparisonArchiveError(
            f"No .nist file matches File A reference '{file_a_reference}'."
        )
    if len(file_a_matches) > 1:
        names = ", ".join(path.name for path in sorted(file_a_matches))
        raise ComparisonArchiveError(
            f"More than one .nist file matches File A reference '{file_a_reference}': {names}"
        )

    file_a_path = file_a_matches[0]
    candidate_paths = sorted(
        (
            path
            for path in nist_paths
            if path != file_a_path and not files_have_same_content(file_a_path, path)
        ),
        key=lambda path: (references[path].casefold(), path.name.casefold()),
    )
    if not candidate_paths:
        raise ComparisonArchiveError(
            "The ZIP archive must contain at least one File B candidate that differs from File A."
        )
    return ArchiveComparisonSelection(
        file_a_path=file_a_path,
        candidate_paths=candidate_paths,
        file_a_reference=file_a_reference,
        candidate_references={path: references[path] for path in candidate_paths},
    )


def archive_reference(archive_path: Path) -> str:
    name = archive_path.name
    if not name.casefold().endswith(ARCHIVE_SUFFIX):
        raise ComparisonArchiveError(f"The ZIP filename must end in '{ARCHIVE_SUFFIX}'.")
    reference = name[: -len(ARCHIVE_SUFFIX)]
    if not reference:
        raise ComparisonArchiveError("The ZIP filename does not contain a File A reference.")
    return reference


def nist_reference(path: Path) -> str | None:
    match = NIST_NAME_PATTERN.fullmatch(path.stem)
    return match.group("reference") if match else None


def _extract_nist_files(archive: ZipFile, destination: Path) -> list[Path]:
    root = destination.resolve()
    extracted: list[Path] = []
    for member in archive.infolist():
        if member.is_dir() or not member.filename.casefold().endswith(".nist"):
            continue
        relative_path = _safe_member_path(member)
        output_path = root.joinpath(*relative_path.parts).resolve()
        if not output_path.is_relative_to(root):
            raise ComparisonArchiveError(f"Unsafe path found in ZIP archive: {member.filename}")
        if output_path.exists():
            raise ComparisonArchiveError(f"Duplicate ZIP destination path: {member.filename}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, output_path.open("wb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
        extracted.append(output_path)
    return extracted


def _safe_member_path(member: ZipInfo) -> PurePosixPath:
    normalized = member.filename.replace("\\", "/")
    path = PurePosixPath(normalized)
    mode = member.external_attr >> 16
    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or ":" in path.parts[0]
        or stat.S_ISLNK(mode)
    ):
        raise ComparisonArchiveError(f"Unsafe path found in ZIP archive: {member.filename}")
    return path
