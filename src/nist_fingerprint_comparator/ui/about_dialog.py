"""Professional application and developer information dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout

from nist_fingerprint_comparator import __version__

from .resources import application_icon_path

ABOUT_TEXT = (
    "<p>Nist Biometric Viewer supports structured visual review of ANSI/NIST "
    "biometric transactions by presenting a Reference Record alongside Comparison Records.</p>"
    "<p><b>Scope</b><br>"
    "Visual review only. The application does not perform automated biometric matching, "
    "similarity scoring, identity verification, or decision-making.</p>"
    f"<p><b>Version</b><br>{__version__}</p>"
    "<p><b>Developed by</b><br>"
    "Nektarios Christou<br>"
    "Hellenic Police</p>"
    "<p><b>Contact</b><br>"
    '<a href="mailto:n.christou@police.gr">n.christou@police.gr</a><br>'
    '<a href="https://github.com/nekcht">github.com/nekcht</a></p>'
)


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About Nist Biometric Viewer")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(16)

        header = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(
            QPixmap(str(application_icon_path())).scaled(
                88,
                88,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        title = QLabel(
            "<span style='font-size:18pt; font-weight:600;'>Nist Biometric Viewer</span>"
            "<br><span style='color:#52606d;'>Professional biometric transaction review</span>"
        )
        title.setTextFormat(Qt.TextFormat.RichText)
        header.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)
        header.addSpacing(12)
        header.addWidget(title, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)

        self.details_label = QLabel(ABOUT_TEXT)
        self.details_label.setTextFormat(Qt.TextFormat.RichText)
        self.details_label.setWordWrap(True)
        self.details_label.setOpenExternalLinks(True)
        self.details_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        layout.addWidget(self.details_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
