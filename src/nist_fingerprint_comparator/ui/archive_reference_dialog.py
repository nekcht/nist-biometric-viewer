"""Shared Reference Record selection for comparison groups."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QStyle,
    QVBoxLayout,
)


class ReferenceRecordList(QListWidget):
    """List a record group and expose its appointed Reference Record."""

    def __init__(self, paths: list[Path] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._paths: list[Path] = []
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.set_paths(paths or [])

    @property
    def reference_path(self) -> Path | None:
        item = self.currentItem()
        if item is None:
            return None
        return self._paths[item.data(Qt.ItemDataRole.UserRole)]

    def set_paths(
        self,
        paths: list[Path],
        reference_path: Path | None = None,
    ) -> None:
        """Display a record group and optionally preserve its appointed reference."""
        previous_reference = reference_path or self.reference_path
        self._paths = list(paths)
        self.clear()
        common_root = _common_parent(self._paths)
        for index, path in enumerate(self._paths):
            item = QListWidgetItem(_display_path(path, common_root))
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.addItem(item)
        self.select_reference(previous_reference)

    def select_reference(self, path: Path | None) -> None:
        """Appoint a record, primarily for repeatable UI testing."""
        if path in self._paths:
            self.setCurrentRow(self._paths.index(path))
        else:
            self.setCurrentRow(-1)


class ArchiveReferenceDialog(QDialog):
    def __init__(self, paths: list[Path], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Reference Record")
        self.resize(680, 480)
        layout = QVBoxLayout(self)
        guidance = QLabel(
            "Select the Reference Record. All other records will be compared against it."
        )
        guidance.setObjectName("referenceGuidance")
        guidance.setWordWrap(True)
        layout.addWidget(guidance)

        self.record_list = ReferenceRecordList(paths)
        self.record_list.itemSelectionChanged.connect(self._update_next_button)
        self.record_list.itemDoubleClicked.connect(lambda _: self._validate_and_accept())
        layout.addWidget(self.record_list, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        next_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        next_button.setText("Next")
        next_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward)
        )
        buttons.accepted.connect(self._validate_and_accept)
        layout.addWidget(buttons)
        self._next_button = next_button
        self._update_next_button()

    @property
    def reference_path(self) -> Path | None:
        return self.record_list.reference_path

    def select_reference(self, path: Path) -> None:
        """Select a record, primarily for repeatable UI testing."""
        self.record_list.select_reference(path)

    def _validate_and_accept(self) -> None:
        if self.reference_path is None:
            QMessageBox.information(
                self,
                "Reference Record required",
                "Select a Reference Record.",
            )
            return
        self.accept()

    def _update_next_button(self) -> None:
        self._next_button.setEnabled(self.reference_path is not None)


def _common_parent(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    try:
        return Path(os.path.commonpath([str(path.parent) for path in paths]))
    except ValueError:
        return None


def _display_path(path: Path, common_root: Path | None) -> str:
    if common_root is None:
        return str(path)
    try:
        return str(path.relative_to(common_root))
    except ValueError:
        return str(path)
