"""Compact two-column metadata table."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)


class MetadataPanel(QTableWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(["Field", "Value"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setAlternatingRowColors(True)
        self.setMaximumHeight(270)

    def set_rows(self, rows: Iterable[tuple[str, Any]]) -> None:
        filtered = [(label, _display(value)) for label, value in rows]
        self.setRowCount(len(filtered))
        for row, (label, value) in enumerate(filtered):
            self.setItem(row, 0, QTableWidgetItem(label))
            self.setItem(row, 1, QTableWidgetItem(value))
        self.resizeRowsToContents()


def _display(value: Any) -> str:
    if value is None or value == "":
        return "Not available"
    return str(value)
