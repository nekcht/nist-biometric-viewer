"""Mouse-wheel zoomable and pannable biometric image viewer."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent, QPixmap, QWheelEvent
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView


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
        self.setToolTip(
            "Ctrl + wheel to zoom\nDrag to pan\nDouble-click to fit"
        )

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap_item.setPixmap(pixmap)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.fit_to_view()

    def clear_image(self) -> None:
        self._pixmap_item.setPixmap(QPixmap())
        self._scene.setSceneRect(0, 0, 1, 1)
        self.resetTransform()

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
        if (
            self._pixmap_item.pixmap().isNull()
            or not event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            event.ignore()
            return
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta == 0:
            event.ignore()
            return
        factor = 1.2 if delta > 0 else 1 / 1.2
        self.scale(factor, factor)
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.fit_to_view()
        event.accept()
