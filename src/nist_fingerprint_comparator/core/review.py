"""One-to-many review queue, internal history, and XLSX export."""

from __future__ import annotations

import hashlib
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

ReviewDecisionValue = Literal["MATCH", "NO_MATCH"]

HISTORY_COLUMNS = [
    "timestamp_utc",
    "decision",
    "file_a_name",
    "file_a_sha256",
    "file_a_transaction_control_number",
    "file_b_name",
    "file_b_sha256",
    "file_b_transaction_control_number",
]

EXPORT_HEADERS = {
    "timestamp_utc": "Timestamp UTC",
    "decision": "Decision",
    "file_a_name": "File A Name",
    "file_a_sha256": "File A SHA-256",
    "file_a_transaction_control_number": "File A Transaction Control Number",
    "file_b_name": "File B Name",
    "file_b_sha256": "File B SHA-256",
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

    def rollback_last(self) -> None:
        if self.decisions:
            self.decisions.pop()
            self.current_index -= 1


class DecisionHistoryStore:
    """Persistent SQLite history with one committed row per user decision."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._initialize()

    def append(self, decision: ReviewDecision) -> None:
        row = decision_record(decision)
        placeholders = ", ".join("?" for _ in HISTORY_COLUMNS)
        columns = ", ".join(HISTORY_COLUMNS)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                f"INSERT INTO decisions ({columns}) VALUES ({placeholders})",
                [row[column] for column in HISTORY_COLUMNS],
            )

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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    decision TEXT NOT NULL CHECK(decision IN ('MATCH', 'NO_MATCH')),
                    file_a_name TEXT NOT NULL,
                    file_a_sha256 TEXT NOT NULL,
                    file_a_transaction_control_number TEXT NOT NULL,
                    file_b_name TEXT NOT NULL,
                    file_b_sha256 TEXT NOT NULL,
                    file_b_transaction_control_number TEXT NOT NULL
                )
                """
            )

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
        f"{prefix}_sha256": _sha256(transaction.source_path),
        f"{prefix}_transaction_control_number": transaction.transaction_metadata.get("1.009", ""),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
