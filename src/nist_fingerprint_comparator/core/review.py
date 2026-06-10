"""One-to-many review queue, internal history, and XLSX export."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import NistTransaction

ReviewDecisionValue = Literal["MATCH", "NO_MATCH", "PASS"]

HISTORY_COLUMNS = [
    "timestamp_utc",
    "decision",
    "file_a_name",
    "file_a_transaction_control_number",
    "file_b_name",
    "file_b_transaction_control_number",
]

EXPORT_HEADERS = {
    "timestamp_utc": "Timestamp UTC",
    "decision": "Decision",
    "file_a_name": "File A Name",
    "file_a_transaction_control_number": "File A Transaction Control Number",
    "file_b_name": "File B Name",
    "file_b_transaction_control_number": "File B Transaction Control Number",
}


@dataclass(slots=True)
class ReviewDecision:
    decision: ReviewDecisionValue
    candidate_number: int
    candidate_total: int
    file_a: NistTransaction
    file_b: NistTransaction
    timestamp_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    history_id: int | None = None


@dataclass(slots=True)
class ReviewQueue:
    file_a: NistTransaction | None = None
    candidate_paths: list[Path] = field(default_factory=list)
    current_index: int = -1
    decisions: list[ReviewDecision] = field(default_factory=list)

    def start(self, file_a: NistTransaction, candidate_paths: list[Path]) -> None:
        self.file_a = file_a
        self.candidate_paths = list(dict.fromkeys(candidate_paths))
        self.current_index = 0 if self.candidate_paths else -1
        self.decisions.clear()

    @property
    def current_path(self) -> Path | None:
        if 0 <= self.current_index < len(self.candidate_paths):
            return self.candidate_paths[self.current_index]
        return None

    @property
    def candidate_number(self) -> int:
        if self.current_path is not None:
            return self.current_index + 1
        return len(self.candidate_paths)

    @property
    def candidate_total(self) -> int:
        return len(self.candidate_paths)

    @property
    def is_complete(self) -> bool:
        return bool(self.candidate_paths) and self.current_index >= len(self.candidate_paths)

    def record(
        self,
        decision: ReviewDecisionValue,
        file_b: NistTransaction,
    ) -> ReviewDecision:
        if self.file_a is None or self.current_path is None:
            raise ValueError("No active comparison candidate is available.")
        review_decision = ReviewDecision(
            decision=decision,
            candidate_number=self.current_index + 1,
            candidate_total=len(self.candidate_paths),
            file_a=self.file_a,
            file_b=file_b,
        )
        self.decisions.append(review_decision)
        self.current_index += 1
        return review_decision

    def rollback_last(self) -> ReviewDecision | None:
        if not self.decisions:
            return None
        decision = self.decisions.pop()
        self.current_index -= 1
        return decision


class DecisionHistoryStore:
    """Persistent SQLite history for committed MATCH and NO_MATCH decisions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._initialize()

    def append(self, decision: ReviewDecision) -> int:
        if decision.decision == "PASS":
            raise ValueError("PASS decisions are ignored and cannot be saved to history.")
        row = decision_record(decision)
        placeholders = ", ".join("?" for _ in HISTORY_COLUMNS)
        columns = ", ".join(HISTORY_COLUMNS)
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                f"INSERT INTO decisions ({columns}) VALUES ({placeholders})",
                [row[column] for column in HISTORY_COLUMNS],
            )
            history_id = int(cursor.lastrowid)
        decision.history_id = history_id
        return history_id

    def delete(self, decision: ReviewDecision) -> None:
        if decision.history_id is None:
            raise ValueError("The decision does not have a persisted history record.")
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "DELETE FROM decisions WHERE id = ?",
                (decision.history_id,),
            )
            if cursor.rowcount != 1:
                raise ValueError("The persisted decision record could not be found.")
        decision.history_id = None

    def clear(self) -> int:
        """Delete every persisted decision and return the number removed."""
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute("DELETE FROM decisions")
            return max(cursor.rowcount, 0)

    def query(
        self,
        start_utc: datetime | None = None,
        end_utc: datetime | None = None,
    ) -> list[dict[str, str]]:
        clauses: list[str] = []
        parameters: list[str] = []
        if start_utc is not None:
            clauses.append("timestamp_utc >= ?")
            parameters.append(_utc_iso(start_utc))
        if end_utc is not None:
            clauses.append("timestamp_utc <= ?")
            parameters.append(_utc_iso(end_utc))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT {', '.join(HISTORY_COLUMNS)} FROM decisions"
                f"{where} ORDER BY timestamp_utc, id",
                parameters,
            ).fetchall()
        return [dict(zip(HISTORY_COLUMNS, row, strict=True)) for row in rows]

    def count(self) -> int:
        with closing(self._connect()) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0])

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            schema = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'decisions'"
            ).fetchone()
            if schema is not None and self._history_schema_requires_migration(
                connection,
                schema[0],
            ):
                self._migrate_history_schema(connection)
            connection.execute(_CREATE_HISTORY_TABLE_SQL)

    @staticmethod
    def _history_schema_requires_migration(
        connection: sqlite3.Connection,
        schema_sql: str,
    ) -> bool:
        columns = [
            row[1] for row in connection.execute("PRAGMA table_info(decisions)").fetchall()
        ]
        return columns != ["id", *HISTORY_COLUMNS] or "'PASS'" in schema_sql

    @staticmethod
    def _migrate_history_schema(connection: sqlite3.Connection) -> None:
        connection.execute("ALTER TABLE decisions RENAME TO decisions_before_migration")
        connection.execute(_CREATE_HISTORY_TABLE_SQL)
        connection.execute(
            f"INSERT INTO decisions (id, {', '.join(HISTORY_COLUMNS)}) "
            f"SELECT id, {', '.join(HISTORY_COLUMNS)} FROM decisions_before_migration "
            "WHERE decision IN ('MATCH', 'NO_MATCH')"
        )
        connection.execute("DROP TABLE decisions_before_migration")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)


class DecisionXlsxExporter:
    """Export selected internal-history rows to a readable XLSX workbook."""

    def export(self, path: Path, rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Decision History"
        sheet.append([EXPORT_HEADERS[column] for column in HISTORY_COLUMNS])
        for row in rows:
            sheet.append([row[column] for column in HISTORY_COLUMNS])

        header_fill = PatternFill("solid", fgColor="D9E3EC")
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for index, column in enumerate(HISTORY_COLUMNS, start=1):
            values = [EXPORT_HEADERS[column], *(str(row[column]) for row in rows)]
            sheet.column_dimensions[get_column_letter(index)].width = min(
                max(len(value) for value in values) + 2,
                72,
            )
        workbook.save(path)


def available_export_path(path: Path) -> Path:
    """Return the first numbered alternative that does not already exist."""
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def decision_record(decision: ReviewDecision) -> dict[str, str]:
    row = {
        "timestamp_utc": decision.timestamp_utc,
        "decision": decision.decision,
    }
    row.update(_transaction_fields("file_a", decision.file_a))
    row.update(_transaction_fields("file_b", decision.file_b))
    return row


def _transaction_fields(prefix: str, transaction: NistTransaction) -> dict[str, str]:
    return {
        f"{prefix}_name": transaction.source_path.name,
        f"{prefix}_transaction_control_number": transaction.transaction_metadata.get("1.009", ""),
    }


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


_CREATE_HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('MATCH', 'NO_MATCH')),
    file_a_name TEXT NOT NULL,
    file_a_transaction_control_number TEXT NOT NULL,
    file_b_name TEXT NOT NULL,
    file_b_transaction_control_number TEXT NOT NULL
)
"""
