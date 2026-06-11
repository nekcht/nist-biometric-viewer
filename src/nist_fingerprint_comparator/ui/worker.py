"""Background archive preparation, parsing, and decoding workers."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from nist_fingerprint_comparator.core.archive import prepare_comparison_archive
from nist_fingerprint_comparator.imaging.decoder import ImageDecoder
from nist_fingerprint_comparator.nist.parser import NistParser

LOGGER = logging.getLogger(__name__)


class ArchiveWorker(QObject):
    progress = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, archive_path: Path, destination: Path, parent=None) -> None:
        super().__init__(parent)
        self.archive_path = archive_path
        self.destination = destination

    @Slot()
    def run(self) -> None:
        try:
            self.progress.emit("Extracting records...")
            contents = prepare_comparison_archive(self.archive_path, self.destination)
            self.finished.emit(contents)
        except Exception as exc:
            LOGGER.exception("Comparison archive processing failed")
            self.failed.emit(f"Archive processing failed: {exc}")


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
            self.progress.emit("Parsing...")
            transaction = NistParser().parse_file(self.path)
            decoder = ImageDecoder()
            total = len(transaction.biometric_images)
            for index, image in enumerate(transaction.biometric_images, start=1):
                self.progress.emit(f"Decoding image {index} of {total}...")
                decoder.decode(image)
            self.finished.emit(transaction)
        except Exception as exc:
            LOGGER.exception("Transaction processing failed")
            self.failed.emit(f"Record processing failed: {exc}")
