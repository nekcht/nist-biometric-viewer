"""Secure extraction and user-directed classification of comparison archives."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from .errors import NistComparatorError

NIST_ARCHIVE_SUFFIXES = {".nist", ".an2", ".eft", ".dat"}


class ComparisonArchiveError(NistComparatorError):
    """Raised when an archive cannot provide a valid comparison group."""


@dataclass(slots=True)
class ArchiveContents:
    nist_paths: list[Path]


@dataclass(slots=True)
class ArchiveComparisonSelection:
    file_a_path: Path
    candidate_paths: list[Path]


def prepare_comparison_archive(
    archive_path: Path,
    destination: Path,
) -> ArchiveContents:
    """Extract supported ANSI/NIST records for later user classification."""
    destination.mkdir(parents=True, exist_ok=True)
    suffix = archive_path.suffix.casefold()
    if suffix == ".zip":
        nist_paths = _prepare_zip_archive(archive_path, destination)
    elif suffix == ".rar":
        nist_paths = _prepare_rar_archive(archive_path, destination)
    else:
        raise ComparisonArchiveError("Supported ZIP or RAR archive required.")

    if len(nist_paths) < 2:
        raise ComparisonArchiveError(
            "Archive requires at least two supported ANSI/NIST records."
        )
    return ArchiveContents(
        nist_paths=sorted(nist_paths, key=lambda path: str(path).casefold()),
    )


def _prepare_zip_archive(archive_path: Path, destination: Path) -> list[Path]:
    try:
        with ZipFile(archive_path) as archive:
            return _extract_nist_files(archive, destination)
    except ComparisonArchiveError:
        raise
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise ComparisonArchiveError(f"ZIP archive unreadable: {exc}") from exc


def _prepare_rar_archive(archive_path: Path, destination: Path) -> list[Path]:
    try:
        import rarfile
    except ImportError as exc:
        raise ComparisonArchiveError(
            "RAR extraction not configured."
        ) from exc
    try:
        with rarfile.RarFile(archive_path) as archive:
            return _extract_rar_nist_files(archive, destination)
    except ComparisonArchiveError:
        raise
    except Exception as exc:
        raise ComparisonArchiveError(f"RAR archive unreadable: {exc}") from exc


def build_archive_comparison_selection(
    contents: ArchiveContents,
    reference_path: Path,
) -> ArchiveComparisonSelection:
    """Use the selected Reference Record and classify every other record for comparison."""
    if reference_path not in contents.nist_paths:
        raise ComparisonArchiveError(
            "Reference Record is outside the archive."
        )
    comparison_paths = [path for path in contents.nist_paths if path != reference_path]
    if not comparison_paths:
        raise ComparisonArchiveError(
            "Archive requires a Comparison Record."
        )
    return ArchiveComparisonSelection(
        file_a_path=reference_path,
        candidate_paths=comparison_paths,
    )


def _extract_nist_files(archive: ZipFile, destination: Path) -> list[Path]:
    root = destination.resolve()
    extracted: list[Path] = []
    for member in archive.infolist():
        if member.is_dir() or Path(member.filename).suffix.casefold() not in NIST_ARCHIVE_SUFFIXES:
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


def _extract_rar_nist_files(archive, destination: Path) -> list[Path]:
    root = destination.resolve()
    extracted: list[Path] = []
    for member in archive.infolist():
        filename = member.filename
        if member.isdir() or Path(filename).suffix.casefold() not in NIST_ARCHIVE_SUFFIXES:
            continue
        symlink_attribute = getattr(member, "is_symlink", False)
        is_symlink = (
            symlink_attribute() if callable(symlink_attribute) else bool(symlink_attribute)
        )
        relative_path = _safe_named_member_path(filename, is_symlink)
        output_path = root.joinpath(*relative_path.parts).resolve()
        if not output_path.is_relative_to(root):
            raise ComparisonArchiveError(f"Unsafe path found in RAR archive: {filename}")
        if output_path.exists():
            raise ComparisonArchiveError(f"Duplicate RAR destination path: {filename}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, output_path.open("wb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
        extracted.append(output_path)
    return extracted


def _safe_member_path(member: ZipInfo) -> PurePosixPath:
    return _safe_named_member_path(
        member.filename,
        stat.S_ISLNK(member.external_attr >> 16),
    )


def _safe_named_member_path(filename: str, is_symlink: bool) -> PurePosixPath:
    normalized = filename.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or ":" in path.parts[0]
        or is_symlink
    ):
        raise ComparisonArchiveError(f"Unsafe path found in archive: {filename}")
    return path
