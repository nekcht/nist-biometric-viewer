"""Optional configured-timezone range selection for decision-history export."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import QDateTime, Qt, QTimeZone
from PySide6.QtWidgets import (
    QCheckBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)


class ExportHistoryDialog(QDialog):
    def __init__(self, timezone_id: str = "UTC", parent=None) -> None:
        super().__init__(parent)
        self.timezone_id = timezone_id
        timezone = QTimeZone(timezone_id.encode())
        if not timezone.isValid():
            timezone = QTimeZone.utc()
            self.timezone_id = "UTC"
        self.setWindowTitle("Export Comparison History")
        layout = QVBoxLayout(self)
        introduction = QLabel(
            f"Export all history or filter by {self.timezone_id} date/time range."
        )
        introduction.setWordWrap(True)
        layout.addWidget(introduction)

        self.filter_checkbox = QCheckBox(
            f"Filter by {self.timezone_id} date/time range"
        )
        self.filter_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.filter_checkbox.toggled.connect(self._set_range_enabled)
        layout.addWidget(self.filter_checkbox)

        form = QFormLayout()
        now = QDateTime.currentDateTimeUtc().toTimeZone(timezone)
        self.start_edit = QDateTimeEdit(now.addMonths(-1))
        self.end_edit = QDateTimeEdit(now)
        for edit in (self.start_edit, self.end_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("HH:mm dd-MM-yyyy")
            edit.setTimeZone(timezone)
        form.addRow("From", self.start_edit)
        form.addRow("To", self.end_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export XLSX")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._set_range_enabled(False)

    def selected_range_utc(self) -> tuple[datetime | None, datetime | None]:
        if not self.filter_checkbox.isChecked():
            return None, None
        return _to_utc(self.start_edit.dateTime()), _to_utc(self.end_edit.dateTime())

    def _set_range_enabled(self, enabled: bool) -> None:
        self.start_edit.setEnabled(enabled)
        self.end_edit.setEnabled(enabled)

    def _validate_and_accept(self) -> None:
        start_utc, end_utc = self.selected_range_utc()
        if start_utc is not None and end_utc is not None and start_utc > end_utc:
            QMessageBox.information(
                self,
                "Invalid time range",
                "Start time must be before end time.",
            )
            return
        self.accept()


def _to_utc(value: QDateTime) -> datetime:
    result = value.toUTC().toPython()
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)
