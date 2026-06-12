"""Shared Reference Record selection for comparison groups."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
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

    referenceAppointmentChanged = Signal()

    def __init__(self, paths: list[Path] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._paths: list[Path] = []
        self._appointed_reference: Path | None = None
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.itemClicked.connect(self._appoint_item)
        self.itemActivated.connect(self._appoint_item)
        self.set_paths(paths or [])

    @property
    def reference_path(self) -> Path | None:
        return self._appointed_reference

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
        self._set_appointed_reference(previous_reference)

    def select_reference(self, path: Path | None) -> None:
        """Appoint a record, primarily for repeatable UI testing."""
        self._set_appointed_reference(path)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        super().keyPressEvent(event)
        if event.key() in {
            Qt.Key.Key_Down,
            Qt.Key.Key_Up,
            Qt.Key.Key_Home,
            Qt.Key.Key_End,
            Qt.Key.Key_PageDown,
            Qt.Key.Key_PageUp,
            Qt.Key.Key_Space,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        }:
            self._appoint_item(self.currentItem())

    def _appoint_item(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        self._set_appointed_reference(
            self._paths[item.data(Qt.ItemDataRole.UserRole)]
        )

    def _set_appointed_reference(self, path: Path | None) -> None:
        appointed = path if path in self._paths else None
        if appointed is None:
            self.clearSelection()
            self.setCurrentRow(-1)
        else:
            self.setCurrentRow(self._paths.index(appointed))
        if appointed == self._appointed_reference:
            return
        self._appointed_reference = appointed
        self.referenceAppointmentChanged.emit()


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
        self.record_list.referenceAppointmentChanged.connect(self._update_next_button)
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
