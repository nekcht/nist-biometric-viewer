"""Scrollable cross-file biometric impression comparison grid."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from nist_fingerprint_comparator.core.models import ComparisonSession

from .fingerprint_card import FingerprintCard


class ComparisonGrid(QScrollArea):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._header_container = QWidget(self)
        self._header_layout = QHBoxLayout(self._header_container)
        self._header_layout.setContentsMargins(12, 12, 12, 0)
        self._header_layout.setSpacing(12)
        self._header_container.hide()
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(14)
        self.setWidget(self._container)
        self._cards: list[FingerprintCard] = []
        self.session: ComparisonSession | None = None
        self.show_empty()

    def show_empty(self) -> None:
        self._clear()
        self._clear_headers()
        self.session = None
        message = QLabel("No comparison selected")
        message.setObjectName("placeholder")
        self._layout.addWidget(message)
        self._layout.addStretch(1)

    def set_session(self, session: ComparisonSession) -> None:
        self._clear()
        self.session = session
        self._set_record_headers(session)
        slot_warnings = {
            warning for slot in session.comparison_slots for warning in slot.warnings
        }
        general_warnings = [
            warning for warning in session.warnings if warning not in slot_warnings
        ]
        if general_warnings:
            warning = QLabel("\n".join(general_warnings))
            warning.setObjectName("warning")
            warning.setWordWrap(True)
            self._layout.addWidget(warning)
        if not session.comparison_slots:
            message = QLabel("No comparable impressions found")
            message.setObjectName("placeholder")
            self._layout.addWidget(message)
        for slot in session.comparison_slots:
            if slot.warnings:
                warning = QLabel("\n".join(slot.warnings))
                warning.setObjectName("warning")
                warning.setWordWrap(True)
                self._layout.addWidget(warning)
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(12)
            file_a = FingerprintCard(
                slot.finger_name,
                slot.file_a_image,
            )
            file_b = FingerprintCard(
                slot.finger_name,
                slot.file_b_image,
            )
            row_layout.addWidget(file_a, 1)
            row_layout.addWidget(file_b, 1)
            self._layout.addWidget(row)
            self._cards.extend([file_a, file_b])
        self._layout.addStretch(1)
        self.scroll_to_top()

    def reset_zoom(self) -> None:
        for card in self._cards:
            card.viewer.reset_zoom()

    def set_metadata_visible(self, visible: bool) -> None:
        for card in self._cards:
            card.set_metadata_visible(visible)

    def scroll_to_top(self) -> None:
        self.verticalScrollBar().setValue(0)
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(0))

    def _clear(self) -> None:
        self._cards.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _clear_headers(self) -> None:
        while self._header_layout.count():
            item = self._header_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._header_container.hide()
        self.setViewportMargins(0, 0, 0, 0)

    def _set_record_headers(self, session: ComparisonSession) -> None:
        self._clear_headers()
        self._header_layout.addWidget(
            self._record_header("Reference Record", session.file_a),
            1,
        )
        self._header_layout.addWidget(
            self._record_header("Comparison Record", session.file_b),
            1,
        )
        header_height = self._header_container.sizeHint().height()
        self.setViewportMargins(0, header_height + 8, 0, 0)
        self._header_container.show()
        self._position_headers()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_headers()

    def _position_headers(self) -> None:
        if self._header_container.isHidden():
            return
        viewport = self.viewport()
        header_height = self._header_container.sizeHint().height()
        self._header_container.setGeometry(
            viewport.x(),
            self.frameWidth(),
            viewport.width(),
            header_height,
        )
        self._header_container.raise_()

    @staticmethod
    def _record_header(source: str, transaction) -> QFrame:
        header = QFrame()
        header.setObjectName("recordHeader")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)
        title = QLabel(source)
        title.setObjectName("recordHeaderTitle")
        layout.addWidget(title)
        if transaction is None:
            filename = "Not loaded"
            reference_number = "Not available"
            summary = "Records: 0 | Biometric images: 0 | Warnings: 0"
        else:
            filename = transaction.source_path.name
            reference_number = transaction.reference_number or "Not available"
            summary = (
                f"Records: {len(transaction.records)} | "
                f"Biometric images: {len(transaction.biometric_images)} | "
                f"Warnings: {len(transaction.warnings)}"
            )
        filename_label = QLabel(filename)
        filename_label.setObjectName("recordHeaderFilename")
        filename_label.setWordWrap(True)
        reference_number_label = QLabel(f"Reference number: {reference_number}")
        reference_number_label.setObjectName("recordHeaderReferenceNumber")
        reference_number_label.setWordWrap(True)
        summary_label = QLabel(summary)
        summary_label.setObjectName("recordHeaderStats")
        summary_label.setWordWrap(True)
        layout.addWidget(filename_label)
        layout.addWidget(reference_number_label)
        layout.addWidget(summary_label)
        return header
