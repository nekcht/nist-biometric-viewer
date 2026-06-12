"""Background archive preparation, parsing, and decoding workers."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from nist_biometric_viewer.core.archive import prepare_comparison_archive
from nist_biometric_viewer.core.loading import (
    LoadingCancelled,
    loading_error_from_exception,
    validate_loading_file,
)
from nist_biometric_viewer.imaging.decoder import ImageDecoder
from nist_biometric_viewer.nist.parser import NistParser

LOGGER = logging.getLogger(__name__)


class ArchiveWorker(QObject):
    progress = Signal(str)
    finished = Signal(object)
    failed = Signal(object)
    cancelled = Signal()

    def __init__(self, archive_path: Path, destination: Path, parent=None) -> None:
        super().__init__(parent)
        self.archive_path = archive_path
        self.destination = destination

    @Slot()
    def run(self) -> None:
        try:
            self.progress.emit("Extracting records...")
            contents = prepare_comparison_archive(
                self.archive_path,
                self.destination,
                should_cancel=_interruption_requested,
            )
            self.finished.emit(contents)
        except LoadingCancelled:
            self.cancelled.emit()
        except Exception as exc:
            error = loading_error_from_exception(
                exc,
                title="Archive could not be opened",
                user_message="The selected archive is damaged or unsupported.",
                stage="archive_extraction",
                source=self.archive_path,
            )
            LOGGER.error("Loading failed: %s", error.log_details)
            self.failed.emit(error)


class ParseWorker(QObject):
    started = Signal()
    progress = Signal(str)
    finished = Signal(object)
    failed = Signal(object)
    cancelled = Signal()

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self.path = path

    @Slot()
    def run(self) -> None:
        self.started.emit()
        try:
            _raise_if_interrupted()
            validate_loading_file(self.path, stage="nist_parsing")
            self.progress.emit("Parsing...")
            try:
                transaction = NistParser().parse_file(self.path)
            except Exception as exc:
                raise loading_error_from_exception(
                    exc,
                    title="Record could not be loaded",
                    user_message="The selected NIST record could not be parsed.",
                    stage="nist_parsing",
                    source=self.path,
                ) from exc
            _raise_if_interrupted()
            decoder = ImageDecoder()
            total = len(transaction.biometric_images)
            for index, image in enumerate(transaction.biometric_images, start=1):
                _raise_if_interrupted()
                self.progress.emit(f"Decoding image {index} of {total}...")
                try:
                    decoder.decode(image)
                except Exception as exc:
                    image.decode_status = "failed"
                    image.warnings.append(
                        f"Image decoding failed: {type(exc).__name__}."
                    )
            self.finished.emit(transaction)
        except LoadingCancelled:
            self.cancelled.emit()
        except Exception as exc:
            error = loading_error_from_exception(
                exc,
                title="Record could not be loaded",
                user_message="The selected NIST record could not be parsed.",
                stage="nist_parsing",
                source=self.path,
            )
            LOGGER.error("Loading failed: %s", error.log_details)
            self.failed.emit(error)


def _interruption_requested() -> bool:
    return QThread.currentThread().isInterruptionRequested()


def _raise_if_interrupted() -> None:
    if _interruption_requested():
        raise LoadingCancelled
