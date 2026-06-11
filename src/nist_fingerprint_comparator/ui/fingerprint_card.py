"""Single fingerprint image and metadata card."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QStackedWidget, QVBoxLayout

from nist_fingerprint_comparator.core.models import BiometricImage, metadata_display_rows
from nist_fingerprint_comparator.imaging.qimage_utils import pil_to_qpixmap

from .image_viewer import ImageViewer
from .metadata_panel import MetadataPanel


class FingerprintCard(QFrame):
    def __init__(self, _title: str, image: BiometricImage | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(360)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.MinimumExpanding,
        )
        self.setStyleSheet(
            "FingerprintCard { background: white; border: 1px solid #d8dde3; border-radius: 6px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.viewer = ImageViewer()
        self.placeholder = QLabel()
        self.placeholder.setObjectName("placeholder")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.image_stack = QStackedWidget()
        self.image_stack.setMinimumHeight(self.viewer.minimumHeight())
        self.image_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.image_stack.addWidget(self.viewer)
        self.image_stack.addWidget(self.placeholder)
        layout.addWidget(self.image_stack, 1)

        self.metadata = MetadataPanel()
        layout.addWidget(self.metadata)

        self.warning = QLabel()
        self.warning.setObjectName("warning")
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)

        self.set_image(image)

    def set_image(self, image: BiometricImage | None) -> None:
        self.viewer.clear_image()
        if image is None:
            self.placeholder.setText("No image available")
            self.image_stack.setCurrentWidget(self.placeholder)
            self.metadata.set_rows([])
            self.warning.hide()
            return

        self.metadata.set_rows(metadata_display_rows(image))
        warnings = list(dict.fromkeys(image.warnings))
        if image.decode_status == "decoded" and image.decoded_pil_image is not None:
            self.viewer.set_pixmap(pil_to_qpixmap(image.decoded_pil_image))
            self.image_stack.setCurrentWidget(self.viewer)
        else:
            self.placeholder.setText("Image not decoded")
            self.image_stack.setCurrentWidget(self.placeholder)

        if warnings:
            self.warning.setText("\n".join(warnings))
            self.warning.show()
        else:
            self.warning.hide()

    def set_metadata_visible(self, visible: bool) -> None:
        self.metadata.setVisible(visible)
