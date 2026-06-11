"""Application settings dialog."""

from __future__ import annotations

from PySide6.QtCore import QDateTime, Qt, QTimeZone
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    def __init__(
        self,
        history_timezone_id: str,
        offer_session_export: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        guidance = QLabel(
            "Select the timezone used when new comparison-history timestamps are recorded. "
            "Canonical UTC time is retained internally for reliable filtering."
        )
        guidance.setWordWrap(True)
        layout.addWidget(guidance)

        form = QFormLayout()
        self.timezone_combo = QComboBox()
        self.timezone_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.timezone_combo.setMaxVisibleItems(18)
        now = QDateTime.currentDateTimeUtc()
        for timezone_id_bytes in QTimeZone.availableTimeZoneIds():
            timezone_id = bytes(timezone_id_bytes).decode()
            timezone = QTimeZone(timezone_id_bytes)
            abbreviation = timezone.abbreviation(now)
            self.timezone_combo.addItem(f"{timezone_id} ({abbreviation})", timezone_id)
        selected_index = self.timezone_combo.findData(history_timezone_id)
        if selected_index >= 0:
            self.timezone_combo.setCurrentIndex(selected_index)
        form.addRow("History timezone", self.timezone_combo)
        layout.addLayout(form)

        self.offer_session_export_checkbox = QCheckBox(
            "Ask to export session results to XLSX when a session ends"
        )
        self.offer_session_export_checkbox.setChecked(offer_session_export)
        self.offer_session_export_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.offer_session_export_checkbox)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save Settings")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def history_timezone_id(self) -> str:
        return str(self.timezone_combo.currentData())

    @property
    def offer_session_export(self) -> bool:
        return self.offer_session_export_checkbox.isChecked()
