"""Explicitly controlled zoomable and pannable biometric image viewer."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QToolButton,
)


class ImageViewer(QGraphicsView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)
        self.setScene(self._scene)
        self.setMinimumHeight(260)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setToolTip("Pan by dragging. Use the image controls to zoom or fit the image.")
        self._tool_overlay = QFrame(self.viewport())
        self._tool_overlay.setObjectName("imageToolOverlay")
        overlay_layout = QHBoxLayout(self._tool_overlay)
        overlay_layout.setContentsMargins(3, 3, 3, 3)
        overlay_layout.setSpacing(1)
        self.zoom_out_button = self._tool_button(
            "Zoom Out",
            _image_tool_icon("zoom-out"),
            self.zoom_out,
        )
        self.fit_button = self._tool_button(
            "Fit Image",
            _image_tool_icon("fit"),
            self.fit_to_view,
        )
        self.zoom_in_button = self._tool_button(
            "Zoom In",
            _image_tool_icon("zoom-in"),
            self.zoom_in,
        )
        overlay_layout.addWidget(self.zoom_out_button)
        overlay_layout.addWidget(self.fit_button)
        overlay_layout.addWidget(self.zoom_in_button)
        self._tool_overlay.adjustSize()
        self._tool_overlay.hide()

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap_item.setPixmap(pixmap)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.fit_to_view()
        self._tool_overlay.show()
        self._position_tool_overlay()

    def clear_image(self) -> None:
        self._pixmap_item.setPixmap(QPixmap())
        self._scene.setSceneRect(0, 0, 1, 1)
        self.resetTransform()
        self._tool_overlay.hide()

    def fit_to_view(self) -> None:
        if not self._pixmap_item.pixmap().isNull():
            self.resetTransform()
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def reset_zoom(self) -> None:
        self.fit_to_view()

    def zoom_in(self) -> None:
        if not self._pixmap_item.pixmap().isNull():
            self.scale(1.2, 1.2)

    def zoom_out(self) -> None:
        if not self._pixmap_item.pixmap().isNull():
            self.scale(1 / 1.2, 1 / 1.2)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_tool_overlay()

    def _tool_button(self, tooltip: str, icon: QIcon, callback) -> QToolButton:
        button = QToolButton(self._tool_overlay)
        button.setObjectName("imageToolButton")
        button.setIcon(icon)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(callback)
        return button

    def _position_tool_overlay(self) -> None:
        self._tool_overlay.adjustSize()
        x = max(8, self.viewport().width() - self._tool_overlay.width() - 8)
        self._tool_overlay.move(x, 8)
        self._tool_overlay.raise_()


def _image_tool_icon(kind: str) -> QIcon:
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#ffffff"), 1.8))
    if kind == "fit":
        painter.drawLine(3, 8, 3, 3)
        painter.drawLine(3, 3, 8, 3)
        painter.drawLine(12, 3, 17, 3)
        painter.drawLine(17, 3, 17, 8)
        painter.drawLine(3, 12, 3, 17)
        painter.drawLine(3, 17, 8, 17)
        painter.drawLine(12, 17, 17, 17)
        painter.drawLine(17, 12, 17, 17)
    else:
        painter.drawEllipse(3, 3, 10, 10)
        painter.drawLine(12, 12, 17, 17)
        painter.drawLine(6, 8, 10, 8)
        if kind == "zoom-in":
            painter.drawLine(8, 6, 8, 10)
    painter.end()
    return QIcon(pixmap)
