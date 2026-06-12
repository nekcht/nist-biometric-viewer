import io
import sys
from pathlib import Path
from types import SimpleNamespace
from zipfile import BadZipFile, ZipFile

import pytest

from nist_biometric_viewer.core.archive import (
    ArchiveContents,
    ComparisonArchiveError,
    build_archive_comparison_selection,
    prepare_comparison_archive,
)
from nist_biometric_viewer.core.loading import LoadingCancelled


def _archive(path: Path, members: dict[str, bytes]) -> Path:
    with ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def test_archive_extracts_supported_records_without_filename_conventions(
    tmp_path: Path,
) -> None:
    archive = _archive(
        tmp_path / "arbitrary-name.zip",
        {
            "nested/first-record.nist": b"first",
            "nested/evidence.an2": b"second",
            "third.EFT": b"third",
            "notes.txt": b"ignored",
        },
    )

    contents = prepare_comparison_archive(archive, tmp_path / "extracted")

    assert [path.name for path in contents.nist_paths] == [
        "evidence.an2",
        "first-record.nist",
        "third.EFT",
    ]
    assert [path.read_bytes() for path in contents.nist_paths] == [
        b"second",
        b"first",
        b"third",
    ]


def test_rar_archive_extracts_supported_records(tmp_path: Path, monkeypatch) -> None:
    members = [
        SimpleNamespace(filename="nested/reference.nist", isdir=lambda: False),
        SimpleNamespace(filename="comparison.an2", isdir=lambda: False),
        SimpleNamespace(filename="notes.txt", isdir=lambda: False),
    ]
    data = {
        "nested/reference.nist": b"reference",
        "comparison.an2": b"comparison",
        "notes.txt": b"ignored",
    }

    class FakeRarFile:
        def __init__(self, _path: Path) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            pass

        def infolist(self):
            return members

        def open(self, member):
            return io.BytesIO(data[member.filename])

    monkeypatch.setitem(sys.modules, "rarfile", SimpleNamespace(RarFile=FakeRarFile))
    (tmp_path / "records.rar").write_bytes(b"fake rar")

    contents = prepare_comparison_archive(tmp_path / "records.rar", tmp_path / "extracted")

    assert [path.name for path in contents.nist_paths] == ["comparison.an2", "reference.nist"]
    assert [path.read_bytes() for path in contents.nist_paths] == [b"comparison", b"reference"]


def test_selected_archive_reference_uses_every_other_record_for_comparison(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / name for name in ("one.nist", "two.nist", "three.nist")]
    contents = ArchiveContents(paths)

    selection = build_archive_comparison_selection(contents, paths[1])

    assert selection.file_a_path == paths[1]
    assert selection.candidate_paths == [paths[0], paths[2]]


def test_archive_keeps_record_with_same_contents_as_selected_reference(
    tmp_path: Path,
) -> None:
    archive = _archive(
        tmp_path / "records.zip",
        {
            "reference.nist": b"same transaction",
            "copy.nist": b"same transaction",
        },
    )
    contents = prepare_comparison_archive(archive, tmp_path / "extracted")

    selection = build_archive_comparison_selection(contents, contents.nist_paths[1])

    assert selection.candidate_paths == [contents.nist_paths[0]]


def test_archive_rejects_unsafe_nist_paths(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "records.zip",
        {
            "../reference.nist": b"a",
            "comparison.nist": b"b",
        },
    )

    with pytest.raises(ComparisonArchiveError, match="Unsafe path"):
        prepare_comparison_archive(archive, tmp_path / "extracted")

    assert not (tmp_path / "reference.nist").exists()


def test_archive_requires_at_least_two_supported_records(tmp_path: Path) -> None:
    archive = _archive(tmp_path / "records.zip", {"only-one.nist": b"a"})

    with pytest.raises(ComparisonArchiveError, match="at least two supported"):
        prepare_comparison_archive(archive, tmp_path / "extracted")


def test_empty_archive_has_controlled_error_and_cleans_destination(tmp_path: Path) -> None:
    archive = _archive(tmp_path / "empty.zip", {})
    destination = tmp_path / "extracted"

    with pytest.raises(ComparisonArchiveError) as raised:
        prepare_comparison_archive(archive, destination)

    assert raised.value.title == "Empty archive"
    assert raised.value.user_message == "No files were found in the archive."
    assert destination.exists()
    assert list(destination.iterdir()) == []


def test_archive_without_supported_records_has_controlled_error(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "no-records.zip",
        {"notes.txt": b"a", "image.png": b"b"},
    )

    with pytest.raises(ComparisonArchiveError) as raised:
        prepare_comparison_archive(archive, tmp_path / "extracted")

    assert raised.value.title == "No records found"
    assert raised.value.user_message == (
        "The archive does not contain supported NIST records."
    )


def test_corrupt_zip_has_controlled_error(tmp_path: Path) -> None:
    archive = tmp_path / "corrupt.zip"
    archive.write_bytes(b"not a zip")

    with pytest.raises(ComparisonArchiveError) as raised:
        prepare_comparison_archive(archive, tmp_path / "extracted")

    assert raised.value.title == "Archive could not be opened"
    assert raised.value.original_exception_type == BadZipFile.__name__


def test_encrypted_zip_has_controlled_error(tmp_path: Path, monkeypatch) -> None:
    archive = tmp_path / "encrypted.zip"
    archive.write_bytes(b"fake zip")
    member = SimpleNamespace(
        filename="reference.nist",
        is_dir=lambda: False,
        flag_bits=0x1,
        file_size=1,
        external_attr=0,
    )

    class FakeEncryptedZip:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            pass

        def infolist(self):
            return [member]

    monkeypatch.setattr(
        "nist_biometric_viewer.core.archive.ZipFile",
        lambda _path: FakeEncryptedZip(),
    )

    with pytest.raises(ComparisonArchiveError) as raised:
        prepare_comparison_archive(archive, tmp_path / "extracted")

    assert raised.value.title == "Encrypted archive"
    assert raised.value.user_message == "Encrypted archives are not supported."


def test_unsafe_ignored_archive_member_is_also_blocked(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "records.zip",
        {
            "reference.nist": b"a",
            "comparison.nist": b"b",
            "../ignored.txt": b"unsafe",
        },
    )
    destination = tmp_path / "extracted"

    with pytest.raises(ComparisonArchiveError, match="Unsafe path"):
        prepare_comparison_archive(archive, destination)

    assert destination.exists()
    assert list(destination.iterdir()) == []


def test_missing_rar_backend_has_controlled_error(tmp_path: Path, monkeypatch) -> None:
    archive = tmp_path / "records.rar"
    archive.write_bytes(b"fake rar")
    monkeypatch.setitem(sys.modules, "rarfile", None)

    with pytest.raises(ComparisonArchiveError) as raised:
        prepare_comparison_archive(archive, tmp_path / "extracted")

    assert raised.value.title == "RAR unavailable"
    assert raised.value.user_message == "RAR support is not configured on this computer."


def test_unavailable_rar_extraction_backend_has_controlled_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive = tmp_path / "records.rar"
    archive.write_bytes(b"fake rar")

    class RarCannotExec(Exception):
        pass

    class FakeRarFile:
        def __init__(self, _path: Path) -> None:
            pass

        def __enter__(self):
            raise RarCannotExec("backend missing")

        def __exit__(self, *_args) -> None:
            pass

    monkeypatch.setitem(sys.modules, "rarfile", SimpleNamespace(RarFile=FakeRarFile))

    with pytest.raises(ComparisonArchiveError) as raised:
        prepare_comparison_archive(archive, tmp_path / "extracted")

    assert raised.value.title == "RAR unavailable"
    assert raised.value.user_message == "RAR support is not configured on this computer."


def test_archive_selection_rejects_reference_outside_archive(tmp_path: Path) -> None:
    contents = ArchiveContents([tmp_path / "one.nist", tmp_path / "two.nist"])

    with pytest.raises(ComparisonArchiveError, match="outside the archive"):
        build_archive_comparison_selection(contents, tmp_path / "other.nist")


def test_archive_cancellation_cleans_partial_extraction(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "records.zip",
        {"reference.nist": b"a", "comparison.nist": b"b"},
    )
    destination = tmp_path / "extracted"
    checks = 0

    def should_cancel() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 3

    with pytest.raises(LoadingCancelled):
        prepare_comparison_archive(archive, destination, should_cancel=should_cancel)

    assert destination.exists()
    assert list(destination.iterdir()) == []


def test_archive_unavailable_destination_has_controlled_error(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "records.zip",
        {"reference.nist": b"a", "comparison.nist": b"b"},
    )
    blocked_parent = tmp_path / "blocked"
    blocked_parent.write_bytes(b"not a directory")

    with pytest.raises(ComparisonArchiveError) as raised:
        prepare_comparison_archive(archive, blocked_parent / "extracted")

    assert raised.value.title == "Temporary folder unavailable"
    assert raised.value.user_message == "A secure temporary folder could not be created."
