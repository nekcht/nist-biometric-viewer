import logging
import os
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from nist_biometric_viewer.core.loading import (
    LoadingError,
    sanitize_diagnostic,
    validate_loading_file,
)
from nist_biometric_viewer.core.models import BiometricImage, NistTransaction
from nist_biometric_viewer.core.review import DecisionHistoryStore
from nist_biometric_viewer.logging_config import SanitizingLogFilter
from nist_biometric_viewer.ui.main_window import MainWindow
from nist_biometric_viewer.ui.settings import HISTORY_DATABASE_FILENAME, AppSettings
from nist_biometric_viewer.ui.worker import ArchiveWorker, ParseWorker
from nist_biometric_viewer.user_data import USER_DATA_ROOT_ENV


def _window(tmp_path: Path) -> MainWindow:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    return MainWindow(
        settings=AppSettings(settings),
        history_store=DecisionHistoryStore(tmp_path / "history.sqlite3"),
    )


@pytest.mark.parametrize("name", ["missing.nist", "empty.nist"])
def test_invalid_direct_file_produces_controlled_loading_error(
    tmp_path: Path,
    name: str,
) -> None:
    path = tmp_path / name
    if name == "empty.nist":
        path.touch()

    with pytest.raises(LoadingError) as raised:
        validate_loading_file(path, stage="file_selection")

    assert raised.value.title in {"File not found", "File is empty"}
    assert raised.value.source_name == name


def test_archive_worker_emits_loading_error_instead_of_raising(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    archive.write_bytes(b"not a zip")
    errors: list[LoadingError] = []
    worker = ArchiveWorker(archive, tmp_path / "extracted")
    worker.failed.connect(errors.append)

    worker.run()

    assert len(errors) == 1
    assert errors[0].title == "Archive could not be opened"
    assert errors[0].stage == "archive_extraction"


def test_parser_fatal_failure_emits_controlled_loading_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "record.nist"
    path.write_bytes(b"record")
    errors: list[LoadingError] = []
    worker = ParseWorker(path)
    worker.failed.connect(errors.append)
    monkeypatch.setattr(
        "nist_biometric_viewer.ui.worker.NistParser.parse_file",
        lambda *_args: (_ for _ in ()).throw(ValueError("Unexpected end of record")),
    )

    worker.run()

    assert len(errors) == 1
    assert errors[0].title == "Record could not be loaded"
    assert errors[0].stage == "nist_parsing"
    assert errors[0].original_exception_type == "ValueError"


def test_decoder_failure_becomes_image_warning(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "record.nist"
    path.write_bytes(b"record")
    image = BiometricImage(
        record_type=14,
        finger_position_code="1",
        image_bytes=b"image payload",
    )
    transaction = NistTransaction(source_path=path, biometric_images=[image])
    finished: list[NistTransaction] = []
    errors: list[LoadingError] = []
    worker = ParseWorker(path)
    worker.finished.connect(finished.append)
    worker.failed.connect(errors.append)
    monkeypatch.setattr(
        "nist_biometric_viewer.ui.worker.NistParser.parse_file",
        lambda *_args: transaction,
    )
    monkeypatch.setattr(
        "nist_biometric_viewer.ui.worker.ImageDecoder.decode",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("decoder exploded")),
    )

    worker.run()

    assert finished == [transaction]
    assert errors == []
    assert image.decode_status == "failed"
    assert image.warnings == ["Image decoding failed: RuntimeError."]


def test_loading_error_recovery_restores_usable_screen(tmp_path: Path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    window = _window(tmp_path)
    window.page_stack.setCurrentWidget(window.workspace_page)
    window._first_pair_ready = True
    window._set_workspace_loading(True, "Loading...")
    archive_temp = TemporaryDirectory(dir=tmp_path)
    archive_temp_path = Path(archive_temp.name)
    (archive_temp_path / "partial.nist").write_bytes(b"partial")
    window._archive_temp_directory = archive_temp
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b = NistTransaction(source_path=tmp_path / "b.nist")
    window._review_queue.start(file_a, [file_b.source_path])
    decision = window._review_queue.record("MATCH", file_b)
    window._history_store.append(decision)
    shown: list[tuple[str, str, str]] = []

    def capture_dialog(dialog: QMessageBox) -> int:
        shown.append((dialog.windowTitle(), dialog.text(), dialog.detailedText()))
        return 0

    monkeypatch.setattr(QMessageBox, "exec", capture_dialog)

    window.handle_loading_error(
        LoadingError(
            "Record could not be loaded",
            "The selected NIST record could not be parsed.",
            stage="nist_parsing",
            technical_message="Unexpected end of record",
            source_name="record.nist",
            original_exception_type="ValueError",
        )
    )

    assert window.page_stack.currentWidget() is window.setup_page
    assert window.new_comparison_action.isEnabled()
    assert not window._workspace_loading
    assert window.workspace_page.isEnabled()
    assert window._history_store.count() == 1
    assert not archive_temp_path.exists()
    assert shown == [
        (
            "Record could not be loaded",
            "The selected NIST record could not be parsed.",
            "Stage: nist_parsing\nSource: record.nist\nReason: ValueError\n"
            "Unexpected end of record",
        )
    ]
    window.close()
    application.processEvents()


def test_log_sanitizer_omits_bytes_paths_and_encoded_data() -> None:
    secret = "A" * 100
    sanitized = sanitize_diagnostic(
        f"payload=b'SECRET-BIOMETRIC' path=C:\\cases\\person.nist encoded={secret}"
    )
    record = logging.LogRecord(
        "test",
        logging.ERROR,
        __file__,
        1,
        b"RAW-BIOMETRIC",
        (),
        None,
    )

    SanitizingLogFilter().filter(record)

    assert sanitized is not None
    assert "SECRET-BIOMETRIC" not in sanitized
    assert "person.nist" not in sanitized
    assert secret not in sanitized
    assert record.getMessage() == "<bytes omitted>"


def test_loading_log_details_omit_source_filename() -> None:
    error = LoadingError(
        "Record could not be loaded",
        "The selected record could not be loaded.",
        stage="nist_parsing",
        source_name="case-person-identifier.nist",
        original_exception_type="PermissionError",
    )

    assert "case-person-identifier.nist" in error.technical_details
    assert "case-person-identifier.nist" not in error.log_details
    assert "PermissionError" in error.log_details


def test_corrupt_history_does_not_crash_main_window_startup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "user-data"
    history_path = root / "history" / HISTORY_DATABASE_FILENAME
    history_path.parent.mkdir(parents=True)
    history_path.write_bytes(b"corrupt history")
    monkeypatch.setenv(USER_DATA_ROOT_ENV, str(root))
    monkeypatch.setattr(
        "nist_biometric_viewer.ui.main_window.QTimer.singleShot",
        lambda *_args: None,
    )
    settings = AppSettings(
        QSettings(str(root / "config" / "settings.ini"), QSettings.Format.IniFormat)
    )

    window = MainWindow(settings=settings)

    assert window._history_store is None
    assert not window.view_history_action.isEnabled()
    window.close()
    application.processEvents()


def test_history_write_failure_keeps_decision_unsaved_and_explains_problem(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    window = _window(tmp_path)
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b = NistTransaction(source_path=tmp_path / "b.nist")
    window._file_b = file_b
    window._review_queue.start(file_a, [file_b.source_path])
    window._history_store = SimpleNamespace(
        replace=lambda *_args: (_ for _ in ()).throw(sqlite3.OperationalError("locked"))
    )
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window._record_decision("MATCH")

    assert window._review_queue.decisions == []
    assert messages == [
        (
            "Decision not saved",
            "History is unavailable. The decision was not saved.",
        )
    ]
    window.close()
    application.processEvents()


def test_window_close_cleans_archive_temporary_directory(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    window = _window(tmp_path)
    archive_temp = TemporaryDirectory(dir=tmp_path)
    archive_temp_path = Path(archive_temp.name)
    (archive_temp_path / "record.nist").write_bytes(b"temporary")
    window._archive_temp_directory = archive_temp

    window.close()
    application.processEvents()

    assert not archive_temp_path.exists()
