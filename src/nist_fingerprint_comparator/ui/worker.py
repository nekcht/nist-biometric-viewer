"""Background parsing and decoding worker."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from nist_fingerprint_comparator.imaging.decoder import ImageDecoder
from nist_fingerprint_comparator.nist.parser import NistParser

LOGGER = logging.getLogger(__name__)


class ParseWorker(QObject):
    started = Signal()
    progress = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self.path = path

    @Slot()
    def run(self) -> None:
        self.started.emit()
        try:
            self.progress.emit("Parsing transaction records...")
            transaction = NistParser().parse_file(self.path)
            decoder = ImageDecoder()
            total = len(transaction.biometric_images)
            for index, image in enumerate(transaction.biometric_images, start=1):
                self.progress.emit(f"Decoding biometric image {index} of {total}...")
                decoder.decode(image)
            self.finished.emit(transaction)
        except Exception as exc:
            LOGGER.exception("Transaction processing failed")
            self.failed.emit(f"Could not process the selected file: {exc}")
