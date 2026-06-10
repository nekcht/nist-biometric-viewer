from datetime import UTC, datetime
from pathlib import Path

from openpyxl import load_workbook

from nist_fingerprint_comparator.core.models import NistTransaction
from nist_fingerprint_comparator.core.review import (
    HISTORY_COLUMNS,
    DecisionHistoryStore,
    DecisionXlsxExporter,
    ReviewDecision,
    ReviewQueue,
    decision_record,
)


def _transaction(path: Path, control_number: str) -> NistTransaction:
    path.write_bytes(f"transaction-{control_number}".encode())
    return NistTransaction(source_path=path, transaction_metadata={"1.009": control_number})


def _decision(
    tmp_path: Path,
    suffix: str,
    timestamp: str,
    value: str = "MATCH",
) -> ReviewDecision:
    return ReviewDecision(
        decision=value,  # type: ignore[arg-type]
        candidate_number=1,
        candidate_total=1,
        file_a=_transaction(tmp_path / f"a-{suffix}.nist", f"A-{suffix}"),
        file_b=_transaction(tmp_path / f"b-{suffix}.nist", f"B-{suffix}"),
        timestamp_utc=timestamp,
    )


def test_review_queue_walks_one_reference_against_many_candidates(tmp_path: Path) -> None:
    file_a = _transaction(tmp_path / "a.nist", "A-001")
    candidates = [tmp_path / "b1.nist", tmp_path / "b2.nist", tmp_path / "b3.nist"]
    queue = ReviewQueue()
    queue.start(file_a, candidates)

    for index, path in enumerate(candidates, start=1):
        file_b = _transaction(path, f"B-{index:03}")
        queue.record("MATCH" if index == 2 else "NO_MATCH", file_b)

    assert queue.is_complete
    assert [decision.decision for decision in queue.decisions] == [
        "NO_MATCH",
        "MATCH",
        "NO_MATCH",
    ]


def test_internal_history_accumulates_across_future_sessions(tmp_path: Path) -> None:
    database = tmp_path / "history.sqlite3"
    first = DecisionHistoryStore(database)
    first.append(_decision(tmp_path, "1", "2026-06-10T08:00:00+00:00"))

    reopened = DecisionHistoryStore(database)
    reopened.append(_decision(tmp_path, "2", "2026-06-10T09:00:00+00:00", "NO_MATCH"))

    assert reopened.count() == 2
    assert [row["decision"] for row in reopened.query()] == ["MATCH", "NO_MATCH"]


def test_internal_history_query_filters_utc_time_range(tmp_path: Path) -> None:
    store = DecisionHistoryStore(tmp_path / "history.sqlite3")
    store.append(_decision(tmp_path, "1", "2026-06-09T23:00:00+00:00"))
    store.append(_decision(tmp_path, "2", "2026-06-10T12:00:00+00:00"))
    store.append(_decision(tmp_path, "3", "2026-06-11T01:00:00+00:00"))

    rows = store.query(
        datetime(2026, 6, 10, 0, 0, tzinfo=UTC),
        datetime(2026, 6, 10, 23, 59, tzinfo=UTC),
    )

    assert [row["file_a_transaction_control_number"] for row in rows] == ["A-2"]


def test_xlsx_export_contains_minimal_history_columns(tmp_path: Path) -> None:
    decision = _decision(tmp_path, "1", "2026-06-10T12:00:00+00:00", "NO_MATCH")
    output = tmp_path / "history.xlsx"

    DecisionXlsxExporter().export(output, [decision_record(decision)])

    workbook = load_workbook(output, read_only=True)
    rows = list(workbook["Decision History"].iter_rows(values_only=True))
    assert len(rows) == 2
    assert len(rows[0]) == len(HISTORY_COLUMNS)
    assert rows[1][1] == "NO_MATCH"
    assert rows[1][4] == "A-1"
    assert rows[1][7] == "B-1"


def test_queue_can_restore_candidate_after_persistence_failure(tmp_path: Path) -> None:
    file_a = _transaction(tmp_path / "a.nist", "A-001")
    file_b = _transaction(tmp_path / "b.nist", "B-001")
    queue = ReviewQueue()
    queue.start(file_a, [file_b.source_path])

    queue.record("MATCH", file_b)
    queue.rollback_last()

    assert queue.current_path == file_b.source_path
    assert queue.decisions == []
