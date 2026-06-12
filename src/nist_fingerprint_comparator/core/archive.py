"""Secure extraction and user-directed classification of comparison archives."""

from __future__ import annotations

import logging
import shutil
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from .loading import LoadingCancelled, LoadingError, LoadingStage, validate_loading_file

LOGGER = logging.getLogger(__name__)

NIST_ARCHIVE_SUFFIXES = {".nist", ".an2", ".an", ".eft", ".ebts", ".dat"}
MAX_ARCHIVE_MEMBERS = 10_000
MAX_ARCHIVE_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 1024 * 1024 * 1024


class ComparisonArchiveError(LoadingError):
    """Raised when an archive cannot provide a valid comparison group."""

    def __init__(
        self,
        message: str,
        *,
        title: str = "Archive could not be opened",
        user_message: str = "The selected archive is damaged or unsupported.",
        stage: LoadingStage = "archive_extraction",
        source_name: str | None = None,
        original_exception_type: str | None = None,
    ) -> None:
        super().__init__(
            title,
            user_message,
            stage=stage,
            technical_message=message,
            source_name=source_name,
            original_exception_type=original_exception_type,
        )


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
    should_cancel: Callable[[], bool] | None = None,
) -> ArchiveContents:
    """Extract supported ANSI/NIST records for later user classification."""
    cleanup_destination = False
    try:
        _raise_if_cancelled(should_cancel)
        validate_loading_file(archive_path, stage="archive_detection")
        try:
            destination.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ComparisonArchiveError(
                str(exc),
                title="Temporary folder unavailable",
                user_message="A secure temporary folder could not be created.",
                stage="temp_directory",
                source_name=archive_path.name,
                original_exception_type=type(exc).__name__,
            ) from exc
        if any(destination.iterdir()):
            raise ComparisonArchiveError(
                "Archive extraction destination is not empty.",
                title="Temporary folder unavailable",
                user_message="A secure temporary folder could not be prepared.",
                stage="temp_directory",
                source_name=archive_path.name,
            )
        cleanup_destination = True
        _raise_if_cancelled(should_cancel)
        suffix = archive_path.suffix.casefold()
        if suffix == ".zip":
            nist_paths = _prepare_zip_archive(archive_path, destination, should_cancel)
        elif suffix == ".rar":
            nist_paths = _prepare_rar_archive(archive_path, destination, should_cancel)
        else:
            raise ComparisonArchiveError(
                "Supported ZIP or RAR archive required.",
                title="Unsupported selection",
                user_message="Select NIST records, a ZIP archive, or a RAR archive.",
                stage="archive_detection",
                source_name=archive_path.name,
            )

        if len(nist_paths) < 2:
            raise ComparisonArchiveError(
                "Archive requires at least two supported ANSI/NIST records.",
                title="Records required",
                user_message="The archive must contain at least two supported NIST records.",
                stage="archive_validation",
                source_name=archive_path.name,
            )
        return ArchiveContents(
            nist_paths=sorted(nist_paths, key=lambda path: str(path).casefold()),
        )
    except Exception:
        if cleanup_destination:
            _clean_failed_destination(destination)
        raise


def _prepare_zip_archive(
    archive_path: Path,
    destination: Path,
    should_cancel: Callable[[], bool] | None,
) -> list[Path]:
    try:
        with ZipFile(archive_path) as archive:
            _validate_zip_members(archive, archive_path.name)
            return _extract_nist_files(archive, destination, should_cancel)
    except ComparisonArchiveError:
        raise
    except RuntimeError as exc:
        if "password" in str(exc).casefold() or "encrypted" in str(exc).casefold():
            raise _encrypted_archive_error(archive_path.name, exc) from exc
        raise _unreadable_archive_error(archive_path.name, exc) from exc
    except (BadZipFile, OSError) as exc:
        raise _unreadable_archive_error(archive_path.name, exc) from exc
    except NotImplementedError as exc:
        raise _unreadable_archive_error(archive_path.name, exc) from exc


def _prepare_rar_archive(
    archive_path: Path,
    destination: Path,
    should_cancel: Callable[[], bool] | None,
) -> list[Path]:
    try:
        import rarfile
    except ImportError as exc:
        raise ComparisonArchiveError(
            "Install or configure a compatible RAR extraction backend.",
            title="RAR unavailable",
            user_message="RAR support is not configured on this computer.",
            stage="archive_detection",
            source_name=archive_path.name,
            original_exception_type=type(exc).__name__,
        ) from exc
    try:
        with rarfile.RarFile(archive_path) as archive:
            _validate_rar_members(archive, archive_path.name)
            return _extract_rar_nist_files(archive, destination, should_cancel)
    except ComparisonArchiveError:
        raise
    except LoadingCancelled:
        raise
    except Exception as exc:
        name = type(exc).__name__
        message = str(exc).casefold()
        if "password" in message or "encrypted" in message:
            raise _encrypted_archive_error(archive_path.name, exc) from exc
        if name in {"RarCannotExec", "RarExecError"}:
            raise ComparisonArchiveError(
                "Install or configure a compatible RAR extraction backend.",
                title="RAR unavailable",
                user_message="RAR support is not configured on this computer.",
                stage="archive_detection",
                source_name=archive_path.name,
                original_exception_type=name,
            ) from exc
        raise _unreadable_archive_error(archive_path.name, exc) from exc


def build_archive_comparison_selection(
    contents: ArchiveContents,
    reference_path: Path,
) -> ArchiveComparisonSelection:
    """Use the selected Reference Record and classify every other record for comparison."""
    if reference_path not in contents.nist_paths:
        raise ComparisonArchiveError(
            "Reference Record is outside the archive.",
            title="Reference selection failed",
            user_message="The selected Reference Record is no longer available.",
            stage="reference_selection",
            source_name=reference_path.name,
        )
    comparison_paths = [path for path in contents.nist_paths if path != reference_path]
    if not comparison_paths:
        raise ComparisonArchiveError(
            "Archive requires a Comparison Record.",
            title="Records required",
            user_message="The archive must contain a Comparison Record.",
            stage="reference_selection",
            source_name=reference_path.name,
        )
    return ArchiveComparisonSelection(
        file_a_path=reference_path,
        candidate_paths=comparison_paths,
    )


def _extract_nist_files(
    archive: ZipFile,
    destination: Path,
    should_cancel: Callable[[], bool] | None,
) -> list[Path]:
    root = destination.resolve()
    extracted: list[Path] = []
    total_written = 0
    for member in archive.infolist():
        _raise_if_cancelled(should_cancel)
        if member.is_dir() or Path(member.filename).suffix.casefold() not in NIST_ARCHIVE_SUFFIXES:
            continue
        relative_path = _safe_member_path(member)
        output_path = root.joinpath(*relative_path.parts).resolve()
        if not output_path.is_relative_to(root):
            raise ComparisonArchiveError("Unsafe path found in ZIP archive.")
        if output_path.exists():
            raise ComparisonArchiveError("Duplicate ZIP destination path.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, output_path.open("wb") as output:
            total_written += _copy_archive_member(
                source,
                output,
                archive_name="ZIP",
                should_cancel=should_cancel,
                remaining_total_bytes=MAX_ARCHIVE_TOTAL_BYTES - total_written,
            )
        extracted.append(output_path)
    return extracted


def _extract_rar_nist_files(
    archive,
    destination: Path,
    should_cancel: Callable[[], bool] | None,
) -> list[Path]:
    root = destination.resolve()
    extracted: list[Path] = []
    total_written = 0
    for member in archive.infolist():
        _raise_if_cancelled(should_cancel)
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
            raise ComparisonArchiveError("Unsafe path found in RAR archive.")
        if output_path.exists():
            raise ComparisonArchiveError("Duplicate RAR destination path.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, output_path.open("wb") as output:
            total_written += _copy_archive_member(
                source,
                output,
                archive_name="RAR",
                should_cancel=should_cancel,
                remaining_total_bytes=MAX_ARCHIVE_TOTAL_BYTES - total_written,
            )
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
        or any(
            ":" in part or any(ord(character) < 32 for character in part)
            for part in path.parts
        )
        or is_symlink
    ):
        raise ComparisonArchiveError("Unsafe path found in archive.")
    return path


def _validate_zip_members(archive: ZipFile, source_name: str) -> None:
    members = archive.infolist()
    files = [member for member in members if not member.is_dir()]
    _validate_member_counts(files, source_name)
    destinations: set[str] = set()
    supported = 0
    for member in members:
        _safe_member_path(member)
        if member.is_dir():
            continue
        if member.flag_bits & 0x1:
            raise _encrypted_archive_error(source_name)
        _validate_member_size(member.file_size, source_name)
        destination = member.filename.replace("\\", "/").casefold()
        if destination in destinations:
            raise ComparisonArchiveError(
                "Duplicate archive destination path.",
                stage="archive_validation",
                source_name=source_name,
            )
        destinations.add(destination)
        if Path(member.filename).suffix.casefold() in NIST_ARCHIVE_SUFFIXES:
            supported += 1
    _validate_supported_count(supported, source_name)


def _validate_rar_members(archive, source_name: str) -> None:
    needs_password = getattr(archive, "needs_password", None)
    if callable(needs_password) and needs_password():
        raise _encrypted_archive_error(source_name)
    members = archive.infolist()
    files = [member for member in members if not member.isdir()]
    _validate_member_counts(files, source_name)
    destinations: set[str] = set()
    supported = 0
    for member in members:
        filename = member.filename
        symlink_attribute = getattr(member, "is_symlink", False)
        is_symlink = (
            symlink_attribute() if callable(symlink_attribute) else bool(symlink_attribute)
        )
        _safe_named_member_path(filename, is_symlink)
        if member.isdir():
            continue
        _validate_member_size(int(getattr(member, "file_size", 0)), source_name)
        destination = filename.replace("\\", "/").casefold()
        if destination in destinations:
            raise ComparisonArchiveError(
                "Duplicate archive destination path.",
                stage="archive_validation",
                source_name=source_name,
            )
        destinations.add(destination)
        if Path(filename).suffix.casefold() in NIST_ARCHIVE_SUFFIXES:
            supported += 1
    _validate_supported_count(supported, source_name)


def _validate_member_counts(files: list, source_name: str) -> None:
    if not files:
        raise ComparisonArchiveError(
            "Archive contains no files.",
            title="Empty archive",
            user_message="No files were found in the archive.",
            stage="archive_validation",
            source_name=source_name,
        )
    if len(files) > MAX_ARCHIVE_MEMBERS:
        raise ComparisonArchiveError(
            f"Archive contains more than {MAX_ARCHIVE_MEMBERS} files.",
            title="Archive could not be opened",
            user_message="The selected archive contains too many files.",
            stage="archive_validation",
            source_name=source_name,
        )
    total = sum(int(getattr(member, "file_size", 0)) for member in files)
    if total > MAX_ARCHIVE_TOTAL_BYTES:
        raise ComparisonArchiveError(
            f"Archive expands beyond {MAX_ARCHIVE_TOTAL_BYTES} bytes.",
            title="Archive could not be opened",
            user_message="The selected archive is too large to extract safely.",
            stage="archive_validation",
            source_name=source_name,
        )


def _validate_member_size(size: int, source_name: str) -> None:
    if size > MAX_ARCHIVE_MEMBER_BYTES:
        raise ComparisonArchiveError(
            f"Archive member exceeds {MAX_ARCHIVE_MEMBER_BYTES} bytes.",
            title="Archive could not be opened",
            user_message="The selected archive contains a file that is too large.",
            stage="archive_validation",
            source_name=source_name,
        )


def _validate_supported_count(supported: int, source_name: str) -> None:
    if supported == 0:
        raise ComparisonArchiveError(
            "Archive contains no supported NIST records.",
            title="No records found",
            user_message="The archive does not contain supported NIST records.",
            stage="archive_validation",
            source_name=source_name,
        )


def _encrypted_archive_error(
    source_name: str,
    exception: Exception | None = None,
) -> ComparisonArchiveError:
    return ComparisonArchiveError(
        "Encrypted archives are not supported.",
        title="Encrypted archive",
        user_message="Encrypted archives are not supported.",
        stage="archive_validation",
        source_name=source_name,
        original_exception_type=type(exception).__name__ if exception else None,
    )


def _unreadable_archive_error(
    source_name: str,
    exception: Exception,
) -> ComparisonArchiveError:
    return ComparisonArchiveError(
        str(exception),
        source_name=source_name,
        original_exception_type=type(exception).__name__,
    )


def _clean_failed_destination(destination: Path) -> None:
    try:
        if not destination.exists():
            return
        root = destination.resolve()
        for child in destination.iterdir():
            resolved = child.resolve()
            if not resolved.is_relative_to(root):
                LOGGER.warning("Skipped unsafe archive cleanup path")
                continue
            try:
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except Exception as exc:
                LOGGER.warning(
                    "Failed archive cleanup item: %s",
                    type(exc).__name__,
                )
    except Exception as exc:
        LOGGER.warning(
            "Failed archive destination cleanup: %s",
            type(exc).__name__,
        )


def _copy_archive_member(
    source,
    output,
    *,
    archive_name: str,
    should_cancel: Callable[[], bool] | None,
    remaining_total_bytes: int,
) -> int:
    written = 0
    while chunk := source.read(1024 * 1024):
        _raise_if_cancelled(should_cancel)
        written += len(chunk)
        if written > MAX_ARCHIVE_MEMBER_BYTES or written > remaining_total_bytes:
            raise ComparisonArchiveError(
                f"{archive_name} extraction exceeded the safety limit.",
                title="Archive could not be opened",
                user_message="The selected archive is too large to extract safely.",
                stage="archive_extraction",
            )
        output.write(chunk)
    return written


def _raise_if_cancelled(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel is not None and should_cancel():
        raise LoadingCancelled
