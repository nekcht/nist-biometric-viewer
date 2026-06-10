"""Scrollable cross-file biometric impression comparison grid."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from nist_fingerprint_comparator.core.models import ComparisonSession

from .fingerprint_card import FingerprintCard

DISCLAIMER = (
    "Visual comparison only. This application displays biometric images and metadata for "
    "human review. It does not perform biometric matching, similarity scoring, or identity "
    "verification."
)


class ComparisonGrid(QScrollArea):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
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
        self.session = None
        self._add_disclaimer()
        message = QLabel("Open File A and File B to begin visual fingerprint comparison.")
        message.setObjectName("placeholder")
        self._layout.addWidget(message)
        self._layout.addStretch(1)

    def set_session(self, session: ComparisonSession) -> None:
        self._clear()
        self.session = session
        self._add_disclaimer()
        self._add_file_summaries(session)
        self._add_section_title("Biometric Impression Comparisons")

        for slot in session.comparison_slots:
            code = slot.position_code or "No position code"
            label = QLabel(f"{code}. {slot.finger_name}")
            label.setObjectName("pairTitle")
            self._layout.addWidget(label)
            if slot.warnings:
                warning = QLabel("\n".join(slot.warnings))
                warning.setObjectName("warning")
                warning.setWordWrap(True)
                self._layout.addWidget(warning)
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(12)
            file_a = FingerprintCard(f"File A - {slot.finger_name}", slot.file_a_image)
            file_b = FingerprintCard(f"File B - {slot.finger_name}", slot.file_b_image)
            row_layout.addWidget(file_a, 1)
            row_layout.addWidget(file_b, 1)
            self._layout.addWidget(row)
            self._cards.extend([file_a, file_b])
        self._layout.addStretch(1)

    def reset_zoom(self) -> None:
        for card in self._cards:
            card.viewer.reset_zoom()

    def set_metadata_visible(self, visible: bool) -> None:
        for card in self._cards:
            card.set_metadata_visible(visible)

    def _clear(self) -> None:
        self._cards.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_disclaimer(self) -> None:
        disclaimer = QLabel(DISCLAIMER)
        disclaimer.setObjectName("disclaimer")
        disclaimer.setWordWrap(True)
        self._layout.addWidget(disclaimer)

    def _add_file_summaries(self, session: ComparisonSession) -> None:
        summaries = QWidget()
        layout = QHBoxLayout(summaries)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._summary_label("File A", session.file_a), 1)
        layout.addWidget(self._summary_label("File B", session.file_b), 1)
        self._layout.addWidget(summaries)

    @staticmethod
    def _summary_label(source: str, transaction) -> QLabel:
        if transaction is None:
            text = f"{source}\nNot loaded"
        else:
            text = (
                f"{source}: {transaction.source_path.name}\n"
                f"Records: {len(transaction.records)} | "
                f"Biometric images: {len(transaction.biometric_images)} | "
                f"Warnings: {len(transaction.warnings)}"
            )
        label = QLabel(text)
        label.setObjectName("fileSummary")
        label.setWordWrap(True)
        return label

    def _add_section_title(self, title: str) -> None:
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        self._layout.addWidget(label)
