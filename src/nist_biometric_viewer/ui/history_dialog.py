"""Display and carefully manage the persistent decision history."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from nist_biometric_viewer.core.review import (
    DISPLAY_HISTORY_COLUMNS,
    EXPORT_HEADERS,
    HISTORY_DECISION_VALUES,
    HISTORY_ID_KEY,
    HistoryDecisionValue,
    decision_label,
)

HISTORY_DIALOG_HEADERS = {
    **EXPORT_HEADERS,
    "file_a_name": "Reference Record",
    "file_a_reference_number": "Reference Record (MN1)",
    "file_b_name": "Comparison Record",
    "file_b_reference_number": "Comparison Record (MN1)",
}
LOGGER = logging.getLogger(__name__)
HISTORY_PAGE_SIZE = 50
DECISION_COLUMN_INDEX = DISPLAY_HISTORY_COLUMNS.index("decision")


class DecisionHistoryDialog(QDialog):
    def __init__(
        self,
        rows: list[dict[str, str]],
        clear_history: Callable[[], int] | None = None,
        delete_record: Callable[[int], None] | None = None,
        change_decision: Callable[[int, HistoryDecisionValue], None] | None = None,
        export_history: Callable[[], None] | None = None,
        total_count: int | None = None,
        load_page: Callable[[int, int], list[dict[str, str]]] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._clear_history = clear_history
        self._delete_record = delete_record
        self._change_decision = change_decision
        self._export_history = export_history
        self._load_page = load_page
        self._all_rows = list(rows) if load_page is None else None
        self._total_count = len(rows) if total_count is None else max(total_count, len(rows))
        self._page_index = 0
        self.setWindowTitle("Comparison History")
        self.resize(1200, 650)
        layout = QVBoxLayout(self)

        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, len(DISPLAY_HISTORY_COLUMNS))
        self.table.setHorizontalHeaderLabels(
            [HISTORY_DIALOG_HEADERS[column] for column in DISPLAY_HISTORY_COLUMNS]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(False)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.table, 1)

        pagination_row = QHBoxLayout()
        pagination_row.addStretch(1)
        self.previous_page_button = QPushButton("Previous")
        self.previous_page_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.previous_page_button.clicked.connect(self._previous_page)
        pagination_row.addWidget(self.previous_page_button)
        self.page_label = QLabel()
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pagination_row.addWidget(self.page_label)
        self.next_page_button = QPushButton("Next")
        self.next_page_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_page_button.clicked.connect(self._next_page)
        pagination_row.addWidget(self.next_page_button)
        pagination_row.addStretch(1)
        layout.addLayout(pagination_row)

        button_row = QHBoxLayout()
        self.export_history_button = QPushButton("Export...")
        self.export_history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_history_button.clicked.connect(self._export)
        button_row.addWidget(self.export_history_button)
        self.change_decision_button = QPushButton("Change Decision...")
        self.change_decision_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change_decision_button.clicked.connect(self._change_selected_decision)
        button_row.addWidget(self.change_decision_button)
        self.delete_selected_button = QPushButton("Delete Selected...")
        self.delete_selected_button.setObjectName("deleteHistoryButton")
        self.delete_selected_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_selected_button.clicked.connect(self._confirm_delete_selected)
        button_row.addWidget(self.delete_selected_button)
        self.delete_history_button = QPushButton("Delete History...")
        self.delete_history_button.setObjectName("deleteHistoryButton")
        self.delete_history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_history_button.clicked.connect(self._confirm_delete_history)
        button_row.addWidget(self.delete_history_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        first_page = (
            self._all_rows[:HISTORY_PAGE_SIZE] if self._all_rows is not None else rows
        )
        self._display_rows(first_page)
        self._update_buttons()

    def _confirm_delete_selected(self) -> None:
        if self._delete_record is None:
            return
        row_index = self.table.currentRow()
        if row_index < 0:
            return
        item = self.table.item(row_index, 0)
        if item is None:
            return
        history_id = int(item.data(Qt.ItemDataRole.UserRole))
        response = QMessageBox.warning(
            self,
            "Delete history record",
            "Delete selected record? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            self._delete_record(history_id)
        except (OSError, ValueError, sqlite3.Error) as exc:
            LOGGER.error("History record deletion failed: %s", type(exc).__name__)
            QMessageBox.critical(self, "Delete failed", "The history record could not be deleted.")
            return
        if self._all_rows is not None:
            self._all_rows = [
                row for row in self._all_rows if int(row[HISTORY_ID_KEY]) != history_id
            ]
        self._total_count = max(self._total_count - 1, 0)
        self._page_index = min(self._page_index, self._last_page_index())
        self._show_page(self._page_index)

    def _change_selected_decision(self) -> None:
        if self._change_decision is None:
            return
        row_index = self.table.currentRow()
        if row_index < 0:
            return
        id_item = self.table.item(row_index, 0)
        decision_item = self.table.item(row_index, DECISION_COLUMN_INDEX)
        if id_item is None or decision_item is None:
            return
        history_id = int(id_item.data(Qt.ItemDataRole.UserRole))
        labels = [decision_label(value) for value in HISTORY_DECISION_VALUES]
        current_index = max(labels.index(decision_item.text()), 0)
        selected_label, accepted = QInputDialog.getItem(
            self,
            "Change decision",
            "Decision",
            labels,
            current_index,
            False,
        )
        if not accepted:
            return
        decision = HISTORY_DECISION_VALUES[labels.index(selected_label)]
        if decision_label(decision) == decision_item.text():
            return
        try:
            self._change_decision(history_id, decision)
        except (OSError, ValueError, sqlite3.Error) as exc:
            LOGGER.error("History decision update failed: %s", type(exc).__name__)
            QMessageBox.critical(
                self,
                "Change failed",
                "The history decision could not be changed.",
            )
            return
        if self._all_rows is not None:
            for row in self._all_rows:
                if int(row[HISTORY_ID_KEY]) == history_id:
                    row["decision"] = decision
                    break
        decision_item.setText(decision_label(decision))

    def _confirm_delete_history(self) -> None:
        if self._clear_history is None:
            return
        response = QMessageBox.warning(
            self,
            "Delete history",
            "Delete all history? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            self._clear_history()
        except (OSError, ValueError, sqlite3.Error) as exc:
            LOGGER.error("History deletion failed: %s", type(exc).__name__)
            QMessageBox.critical(self, "Delete failed", "History could not be deleted.")
            return
        if self._all_rows is not None:
            self._all_rows.clear()
        self._total_count = 0
        self._page_index = 0
        self._display_rows([])
        self._update_buttons()

    def _export(self) -> None:
        if self._export_history is not None:
            self._export_history()

    def _previous_page(self) -> None:
        self._show_page(self._page_index - 1)

    def _next_page(self) -> None:
        self._show_page(self._page_index + 1)

    def _show_page(self, page_index: int) -> None:
        if not 0 <= page_index <= self._last_page_index():
            return
        try:
            rows = self._rows_for_page(page_index)
        except (OSError, ValueError, sqlite3.Error) as exc:
            LOGGER.error("History page loading failed: %s", type(exc).__name__)
            QMessageBox.critical(self, "History unavailable", "History could not be loaded.")
            return
        self._page_index = page_index
        self._display_rows(rows)
        self._update_buttons()

    def _rows_for_page(self, page_index: int) -> list[dict[str, str]]:
        offset = page_index * HISTORY_PAGE_SIZE
        if self._all_rows is not None:
            return self._all_rows[offset : offset + HISTORY_PAGE_SIZE]
        if self._load_page is None:
            return []
        return self._load_page(offset, HISTORY_PAGE_SIZE)

    def _display_rows(self, rows: list[dict[str, str]]) -> None:
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, column in enumerate(DISPLAY_HISTORY_COLUMNS):
                value = decision_label(row[column]) if column == "decision" else row[column]
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(row[HISTORY_ID_KEY]))
                self.table.setItem(row_index, column_index, item)
        self.table.resizeColumnsToContents()

    def _last_page_index(self) -> int:
        return max((self._total_count - 1) // HISTORY_PAGE_SIZE, 0)

    def _update_buttons(self) -> None:
        has_rows = self._total_count > 0
        page_count = self._last_page_index() + 1
        has_multiple_pages = self._total_count > HISTORY_PAGE_SIZE
        self.summary_label.setText(_history_count_text(self._total_count))
        self.page_label.setText(f"Page {self._page_index + 1} of {page_count}")
        self.page_label.setVisible(has_multiple_pages)
        self.previous_page_button.setVisible(has_multiple_pages)
        self.next_page_button.setVisible(has_multiple_pages)
        self.previous_page_button.setEnabled(self._page_index > 0)
        self.next_page_button.setEnabled(self._page_index < self._last_page_index())
        self.export_history_button.setEnabled(has_rows and self._export_history is not None)
        self.delete_selected_button.setEnabled(
            self.table.currentRow() >= 0 and self._delete_record is not None
        )
        self.change_decision_button.setEnabled(
            self.table.currentRow() >= 0 and self._change_decision is not None
        )
        self.delete_history_button.setEnabled(has_rows and self._clear_history is not None)


def _history_count_text(count: int) -> str:
    return f"{count} decision" if count == 1 else f"{count} decisions"
