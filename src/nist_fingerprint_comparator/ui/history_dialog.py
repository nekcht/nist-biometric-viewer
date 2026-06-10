"""Read-only display of the persistent decision history."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from nist_fingerprint_comparator.core.review import EXPORT_HEADERS, HISTORY_COLUMNS


class DecisionHistoryDialog(QDialog):
    def __init__(self, rows: list[dict[str, str]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Decision History")
        self.resize(1200, 650)
        layout = QVBoxLayout(self)

        self.summary_label = QLabel(f"{len(rows)} decision record(s)")
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(len(rows), len(HISTORY_COLUMNS))
        self.table.setHorizontalHeaderLabels([EXPORT_HEADERS[column] for column in HISTORY_COLUMNS])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(False)
        for row_index, row in enumerate(rows):
            for column_index, column in enumerate(HISTORY_COLUMNS):
                self.table.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem(row[column]),
                )
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
