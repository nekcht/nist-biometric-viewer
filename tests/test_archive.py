import io
import sys
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from nist_fingerprint_comparator.core.archive import (
    ArchiveContents,
    ComparisonArchiveError,
    build_archive_comparison_selection,
    prepare_comparison_archive,
)


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


@pytest.mark.parametrize(
    "members",
    [
        {"only-one.nist": b"a"},
        {"notes.txt": b"a", "image.png": b"b"},
    ],
)
def test_archive_requires_at_least_two_supported_records(
    tmp_path: Path,
    members: dict[str, bytes],
) -> None:
    archive = _archive(tmp_path / "records.zip", members)

    with pytest.raises(ComparisonArchiveError, match="at least two supported"):
        prepare_comparison_archive(archive, tmp_path / "extracted")


def test_archive_selection_rejects_reference_outside_archive(tmp_path: Path) -> None:
    contents = ArchiveContents([tmp_path / "one.nist", tmp_path / "two.nist"])

    with pytest.raises(ComparisonArchiveError, match="not part of the extracted archive"):
        build_archive_comparison_selection(contents, tmp_path / "other.nist")
