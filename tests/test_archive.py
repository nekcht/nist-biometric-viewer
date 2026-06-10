from pathlib import Path
from zipfile import ZipFile

import pytest

from nist_fingerprint_comparator.core.archive import (
    ComparisonArchiveError,
    archive_reference,
    nist_reference,
    prepare_comparison_archive,
)


def _archive(path: Path, members: dict[str, bytes]) -> Path:
    with ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def test_archive_extracts_and_classifies_reference_and_candidates(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "A-001_files.zip",
        {
            "nested/A-001_fp.nist": b"reference",
            "nested/B-002-fi.nist": b"candidate-1",
            "B_003_fp.NIST": b"candidate-2",
            "notes.txt": b"ignored",
        },
    )

    selection = prepare_comparison_archive(archive, tmp_path / "extracted")

    assert selection.file_a_reference == "A-001"
    assert selection.file_a_path.name == "A-001_fp.nist"
    assert selection.file_a_path.read_bytes() == b"reference"
    assert {path.name for path in selection.candidate_paths} == {
        "B-002-fi.nist",
        "B_003_fp.NIST",
    }
    assert set(selection.candidate_references.values()) == {"B-002", "B_003"}


def test_archive_accepts_underscore_delimiter_for_file_a(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "REF123_files.zip",
        {
            "REF123_fi.nist": b"a",
            "OTHER-fp.nist": b"b",
        },
    )

    selection = prepare_comparison_archive(archive, tmp_path / "extracted")

    assert selection.file_a_path.name == "REF123_fi.nist"


def test_archive_excludes_candidate_with_same_contents_as_file_a(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "REF_files.zip",
        {
            "REF-fp.nist": b"same transaction",
            "COPY-fp.nist": b"same transaction",
            "OTHER-fp.nist": b"different transaction",
        },
    )

    selection = prepare_comparison_archive(archive, tmp_path / "extracted")

    assert [path.name for path in selection.candidate_paths] == ["OTHER-fp.nist"]


def test_archive_rejects_group_containing_only_a_copy_of_file_a(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "REF_files.zip",
        {
            "REF-fp.nist": b"same transaction",
            "COPY-fp.nist": b"same transaction",
        },
    )

    with pytest.raises(ComparisonArchiveError, match="differs from File A"):
        prepare_comparison_archive(archive, tmp_path / "extracted")


def test_archive_rejects_unsafe_nist_paths(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path / "REF_files.zip",
        {
            "../REF-fp.nist": b"a",
            "OTHER-fp.nist": b"b",
        },
    )

    with pytest.raises(ComparisonArchiveError, match="Unsafe path"):
        prepare_comparison_archive(archive, tmp_path / "extracted")

    assert not (tmp_path / "REF-fp.nist").exists()


@pytest.mark.parametrize(
    ("name", "members", "message"),
    [
        ("wrong.zip", {"REF-fp.nist": b"a", "B-fp.nist": b"b"}, "_files.zip"),
        ("REF_files.zip", {"B-fp.nist": b"b", "C-fi.nist": b"c"}, "No .nist file"),
        (
            "REF_files.zip",
            {"REF-fp.nist": b"a", "REF_fi.nist": b"a2", "B-fp.nist": b"b"},
            "More than one",
        ),
        ("REF_files.zip", {"REF-fp.nist": b"a"}, "at least one File B"),
        (
            "REF_files.zip",
            {"REF-fp.nist": b"a", "candidate.nist": b"b"},
            "Every .nist filename",
        ),
    ],
)
def test_archive_reports_invalid_comparison_groups(
    tmp_path: Path,
    name: str,
    members: dict[str, bytes],
    message: str,
) -> None:
    archive = _archive(tmp_path / name, members)

    with pytest.raises(ComparisonArchiveError, match=message):
        prepare_comparison_archive(archive, tmp_path / f"extracted-{len(members)}")


def test_reference_helpers_follow_archive_naming_rules() -> None:
    assert archive_reference(Path("CASE_42_files.zip")) == "CASE_42"
    assert nist_reference(Path("CASE_42-fi.nist")) == "CASE_42"
    assert nist_reference(Path("CASE_42_fp.nist")) == "CASE_42"
    assert nist_reference(Path("CASE_42.nist")) is None
