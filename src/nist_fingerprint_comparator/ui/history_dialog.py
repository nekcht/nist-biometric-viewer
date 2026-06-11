"""Display and carefully manage the persistent decision history."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from nist_fingerprint_comparator.core.review import (
    DISPLAY_HISTORY_COLUMNS,
    EXPORT_HEADERS,
    HISTORY_ID_KEY,
)


class DecisionHistoryDialog(QDialog):
    def __init__(
        self,
        rows: list[dict[str, str]],
        clear_history: Callable[[], int] | None = None,
        delete_record: Callable[[int], None] | None = None,
        export_history: Callable[[], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._clear_history = clear_history
        self._delete_record = delete_record
        self._export_history = export_history
        self.setWindowTitle("Comparison History")
        self.resize(1200, 650)
        layout = QVBoxLayout(self)

        self.summary_label = QLabel(_history_count_text(len(rows)))
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(len(rows), len(DISPLAY_HISTORY_COLUMNS))
        self.table.setHorizontalHeaderLabels(
            [EXPORT_HEADERS[column] for column in DISPLAY_HISTORY_COLUMNS]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(False)
        for row_index, row in enumerate(rows):
            for column_index, column in enumerate(DISPLAY_HISTORY_COLUMNS):
                item = QTableWidgetItem(row[column])
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(row[HISTORY_ID_KEY]))
                self.table.setItem(row_index, column_index, item)
        self.table.resizeColumnsToContents()
        self.table.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.table, 1)

        button_row = QHBoxLayout()
        self.export_history_button = QPushButton("Export...")
        self.export_history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_history_button.setEnabled(bool(rows) and export_history is not None)
        self.export_history_button.clicked.connect(self._export)
        button_row.addWidget(self.export_history_button)
        self.delete_selected_button = QPushButton("Delete Selected...")
        self.delete_selected_button.setObjectName("deleteHistoryButton")
        self.delete_selected_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_selected_button.clicked.connect(self._confirm_delete_selected)
        button_row.addWidget(self.delete_selected_button)
        self.delete_history_button = QPushButton("Delete History...")
        self.delete_history_button.setObjectName("deleteHistoryButton")
        self.delete_history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_history_button.setEnabled(bool(rows) and clear_history is not None)
        self.delete_history_button.clicked.connect(self._confirm_delete_history)
        button_row.addWidget(self.delete_history_button)
        button_row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        button_row.addWidget(buttons)
        layout.addLayout(button_row)
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
            QMessageBox.critical(self, "Delete failed", str(exc))
            return
        self.table.removeRow(row_index)
        self._update_buttons()

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
            QMessageBox.critical(self, "Delete failed", str(exc))
            return
        self.table.setRowCount(0)
        self._update_buttons()

    def _export(self) -> None:
        if self._export_history is not None:
            self._export_history()

    def _update_buttons(self) -> None:
        has_rows = self.table.rowCount() > 0
        self.summary_label.setText(_history_count_text(self.table.rowCount()))
        self.export_history_button.setEnabled(has_rows and self._export_history is not None)
        self.delete_selected_button.setEnabled(
            self.table.currentRow() >= 0 and self._delete_record is not None
        )
        self.delete_history_button.setEnabled(has_rows and self._clear_history is not None)


def _history_count_text(count: int) -> str:
    return f"{count} decision" if count == 1 else f"{count} decisions"
