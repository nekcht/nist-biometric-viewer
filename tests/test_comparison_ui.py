# ruff: noqa: I001

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt, QTimeZone
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QToolButton

from nist_fingerprint_comparator.core.models import BiometricImage
from nist_fingerprint_comparator.core.models import NistTransaction
from nist_fingerprint_comparator.core.archive import ArchiveComparisonSelection
from nist_fingerprint_comparator.core.pairing import build_cross_file_comparison, finger_details
from nist_fingerprint_comparator.core.review import DecisionHistoryStore
from nist_fingerprint_comparator.ui.about_dialog import ABOUT_TEXT, AboutDialog
from nist_fingerprint_comparator.ui.comparison_grid import ComparisonGrid, DISCLAIMER
from nist_fingerprint_comparator.ui.export_dialog import ExportHistoryDialog
from nist_fingerprint_comparator.ui.history_dialog import DecisionHistoryDialog
from nist_fingerprint_comparator.ui.main_window import MainWindow
from nist_fingerprint_comparator.ui.resources import application_icon_path
from nist_fingerprint_comparator.ui.settings import AppSettings
from nist_fingerprint_comparator.ui.setup_dialog import ComparisonSetupDialog


def _window(tmp_path: Path) -> MainWindow:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    return MainWindow(
        settings=AppSettings(settings),
        history_store=DecisionHistoryStore(tmp_path / "history.sqlite3"),
    )


def _image(code: str) -> BiometricImage:
    name, hand = finger_details(code)
    return BiometricImage(
        record_type=14,
        finger_position_code=code,
        finger_name=name,
        hand=hand,  # type: ignore[arg-type]
        decode_status="unsupported",
    )


def test_ui_renders_every_impression_as_a_cross_file_row() -> None:
    application = QApplication.instance() or QApplication([])
    session = build_cross_file_comparison(
        [_image("1"), _image("13"), _image("21")],
        [_image("1"), _image("13"), _image("23")],
    )
    grid = ComparisonGrid()

    grid.set_session(session)

    assert grid.session is session
    assert [slot.position_code for slot in grid.session.comparison_slots] == [
        "1",
        "13",
        "21",
        "23",
    ]
    slap_slot = grid.session.comparison_slots[1]
    assert slap_slot.file_a_image.finger_position_code == "13"
    assert slap_slot.file_b_image.finger_position_code == "13"
    assert "does not perform biometric matching" in DISCLAIMER
    assert len(grid._cards) == 8
    grid.close()
    application.processEvents()


def test_main_window_records_final_queue_decision(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    file_a_path = tmp_path / "a.nist"
    file_b_path = tmp_path / "b.nist"
    file_a_path.write_bytes(b"a")
    file_b_path.write_bytes(b"b")
    file_a = NistTransaction(source_path=file_a_path)
    file_b = NistTransaction(source_path=file_b_path)
    window = _window(tmp_path)
    window._offer_session_export = lambda decisions: None
    window._file_a = file_a
    window._file_b = file_b
    window._review_queue.start(file_a, [file_b_path])

    window._record_decision("NO_MATCH")

    assert window._history_store.count() == 1
    assert window.results_label.text() == "Internal decision history: 1 record(s)"
    assert window.page_stack.currentWidget() is window.setup_page
    assert window._file_a is None
    assert window._file_b is None
    assert window._review_queue.candidate_paths == []
    assert not window.reset_zoom_action.isEnabled()
    assert "Review complete" in window.statusBar().currentMessage()
    window.close()
    application.processEvents()


def test_main_window_advances_to_next_candidate_after_decision(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    file_a_path = tmp_path / "a.nist"
    file_b1_path = tmp_path / "b1.nist"
    file_b2_path = tmp_path / "b2.nist"
    for path in (file_a_path, file_b1_path, file_b2_path):
        path.write_bytes(path.name.encode())
    file_a = NistTransaction(source_path=file_a_path)
    file_b1 = NistTransaction(source_path=file_b1_path)
    window = _window(tmp_path)
    window._offer_session_export = lambda decisions: None
    window._file_a = file_a
    window._file_b = file_b1
    window._review_queue.start(file_a, [file_b1_path, file_b2_path])
    requested: list[tuple[Path, str]] = []
    window._start_processing = lambda path, target: requested.append((path, target))

    window._record_decision("MATCH")

    assert requested == [(file_b2_path, "b")]
    assert window._review_queue.current_path == file_b2_path
    assert window._file_a is file_a
    assert window._file_b is None
    assert window.page_stack.currentWidget() is window.loading_page
    assert window._history_store.count() == 1
    window.close()
    application.processEvents()


def test_main_window_pass_advances_without_saving_history(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    file_a_path = tmp_path / "a.nist"
    file_b_path = tmp_path / "b.nist"
    file_a_path.write_bytes(b"a")
    file_b_path.write_bytes(b"b")
    file_a = NistTransaction(source_path=file_a_path)
    file_b = NistTransaction(source_path=file_b_path)
    window = _window(tmp_path)
    window._offer_session_export = lambda decisions: None
    window._file_a = file_a
    window._file_b = file_b
    window._review_queue.start(file_a, [file_b_path])

    window._record_decision("PASS")

    assert window._history_store.count() == 0
    assert window.results_label.text() == "Internal decision history: 0 record(s)"
    assert "0 decision(s) saved to internal history" in window.statusBar().currentMessage()
    window.close()
    application.processEvents()


def test_single_setup_starts_reference_loading_and_uses_internal_history(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    file_a_path = tmp_path / "a.nist"
    candidate_path = tmp_path / "b.nist"
    file_a_path.write_bytes(b"a")
    candidate_path.write_bytes(b"b")
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    app_settings = AppSettings(settings)
    window = MainWindow(
        settings=app_settings,
        history_store=DecisionHistoryStore(tmp_path / "history.sqlite3"),
    )
    started: list[tuple[Path, str]] = []
    window._start_processing = lambda path, target: started.append((path, target))

    window.start_comparison(file_a_path, [candidate_path])

    assert started == [(file_a_path, "a")]
    assert window._pending_candidate_paths == [candidate_path]
    assert window.page_stack.currentWidget() is window.loading_page
    assert window.loading_progress.minimum() == 0
    assert window.loading_progress.maximum() == 0

    window._processing_target = "a"
    window._processing_finished(NistTransaction(source_path=file_a_path))
    assert window.results_label.text() == "Internal decision history: 0 record(s)"
    assert window._start_candidate_after_thread
    window.close()
    application.processEvents()


def test_main_window_has_professional_menus_toolbar_and_hand_cursors(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    window = _window(tmp_path)
    window._offer_session_export = lambda decisions: None

    assert [action.text() for action in window.menuBar().actions()] == [
        "&File",
        "&Edit",
        "&View",
        "&Help",
    ]
    assert window.main_toolbar.iconSize().width() == 20
    assert window.export_history_action.text() == "Export Decision History..."
    assert window.clear_history_action.text() == "Delete All Decision History..."
    assert not window.clear_history_action.icon().isNull()
    assert window.match_button.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert window.no_match_button.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert window.pass_button.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert window.pass_button.text() == "PASS"
    assert window.view_history_action.text() == "View Decision History..."
    assert window.end_session_action.text() == "End Current Session"
    assert all(
        button.cursor().shape() == Qt.CursorShape.PointingHandCursor
        for button in window.main_toolbar.findChildren(QToolButton)
    )
    assert application_icon_path().is_file()
    assert not window.windowIcon().isNull()
    assert window.page_stack.currentWidget() is window.setup_page
    window.close()
    application.processEvents()


def test_workspace_appears_only_after_first_complete_pair(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    file_a_path = tmp_path / "a.nist"
    file_b_path = tmp_path / "b.nist"
    file_a_path.write_bytes(b"a")
    file_b_path.write_bytes(b"b")
    window = _window(tmp_path)
    requested: list[tuple[Path, str]] = []
    window._start_processing = lambda path, target: requested.append((path, target))

    window.start_comparison(file_a_path, [file_b_path])
    assert window.page_stack.currentWidget() is window.loading_page
    assert window.page_stack.currentWidget() is not window.workspace_page

    window._processing_target = "a"
    window._processing_finished(NistTransaction(source_path=file_a_path))
    assert window.page_stack.currentWidget() is window.loading_page
    window._thread_finished()
    assert requested[-1] == (file_b_path, "b")
    assert window.page_stack.currentWidget() is window.loading_page

    window._processing_target = "b"
    window._processing_finished(NistTransaction(source_path=file_b_path))
    assert window.page_stack.currentWidget() is window.workspace_page
    window.close()
    application.processEvents()


def test_manually_selected_same_file_shows_pass_warning(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    path = tmp_path / "same.nist"
    path.write_bytes(b"same transaction")
    transaction_a = NistTransaction(source_path=path)
    transaction_b = NistTransaction(source_path=path)
    window = _window(tmp_path)
    window._file_a = transaction_a
    window._file_b = transaction_b

    session = window._refresh_comparison()

    assert "same file" in session.warnings[0]
    assert "PASS is not saved to decision history" in session.warnings[0]
    assert window.comparison_grid.session is session
    window.close()
    application.processEvents()


def test_setup_dialog_collects_reference_and_candidate_group(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    file_a_path = tmp_path / "a.nist"
    candidate_paths = [tmp_path / "b1.nist", tmp_path / "b2.nist"]
    dialog = ComparisonSetupDialog(tmp_path)

    dialog.set_selection(file_a_path, candidate_paths)

    assert dialog.file_a_path == file_a_path
    assert dialog.candidate_paths == candidate_paths
    assert dialog.candidate_list.count() == 2
    dialog.close()
    application.processEvents()


def test_setup_dialog_accepts_zip_archive_as_alternative(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    archive_path = tmp_path / "REF_files.zip"
    dialog = ComparisonSetupDialog(tmp_path)

    dialog.set_archive_selection(archive_path)

    assert dialog.archive_path == archive_path
    assert dialog.file_a_path is None
    assert dialog.candidate_paths == []
    dialog.close()
    application.processEvents()


def test_archive_selection_loads_extracted_files_then_cleans_temporary_directory(
    tmp_path,
) -> None:
    application = QApplication.instance() or QApplication([])
    window = _window(tmp_path)
    archive_path = tmp_path / "REF_files.zip"
    extraction_requests: list[tuple[Path, Path]] = []
    parse_requests: list[tuple[Path, str]] = []
    window._start_archive_processing = lambda archive, destination: extraction_requests.append(
        (archive, destination)
    )
    window._start_processing = lambda path, target: parse_requests.append((path, target))

    window.start_archive_comparison(archive_path)

    assert extraction_requests[0][0] == archive_path
    extraction_directory = extraction_requests[0][1]
    assert extraction_directory.exists()
    file_a = extraction_directory / "REF-fp.nist"
    file_b = extraction_directory / "B-fp.nist"
    file_a.write_bytes(b"a")
    file_b.write_bytes(b"b")
    window._archive_processing_finished(
        ArchiveComparisonSelection(
            file_a_path=file_a,
            candidate_paths=[file_b],
            file_a_reference="REF",
            candidate_references={file_b: "B"},
        )
    )
    window._thread_finished()

    assert parse_requests == [(file_a, "a")]
    window._finish_review()
    assert not extraction_directory.exists()
    assert window.page_stack.currentWidget() is window.setup_page
    assert "Review complete" in window.statusBar().currentMessage()
    window.close()
    application.processEvents()


def test_previous_comparison_erases_last_record_and_reloads_candidate(
    tmp_path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    file_a_path = tmp_path / "a.nist"
    file_b1_path = tmp_path / "b1.nist"
    file_b2_path = tmp_path / "b2.nist"
    for path in (file_a_path, file_b1_path, file_b2_path):
        path.write_bytes(path.name.encode())
    file_a = NistTransaction(source_path=file_a_path)
    file_b1 = NistTransaction(source_path=file_b1_path)
    window = _window(tmp_path)
    window._file_a = file_a
    window._file_b = NistTransaction(source_path=file_b2_path)
    window._review_queue.start(file_a, [file_b1_path, file_b2_path])
    decision = window._review_queue.record("MATCH", file_b1)
    window._history_store.append(decision)
    window._candidate_ready = True
    window._set_decision_buttons_enabled(True)
    requested: list[tuple[Path, str]] = []
    window._start_processing = lambda path, target: requested.append((path, target))
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: QMessageBox.StandardButton.Yes,
    )

    window._go_to_previous_comparison()

    assert window._history_store.count() == 0
    assert window._review_queue.decisions == []
    assert window._review_queue.current_path == file_b1_path
    assert requested == [(file_b1_path, "b")]
    window.close()
    application.processEvents()


def test_end_session_keeps_completed_records_and_returns_to_setup(
    tmp_path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    file_a_path = tmp_path / "a.nist"
    file_b1_path = tmp_path / "b1.nist"
    file_b2_path = tmp_path / "b2.nist"
    for path in (file_a_path, file_b1_path, file_b2_path):
        path.write_bytes(path.name.encode())
    file_a = NistTransaction(source_path=file_a_path)
    file_b1 = NistTransaction(source_path=file_b1_path)
    window = _window(tmp_path)
    window._offer_session_export = lambda decisions: None
    window._file_a = file_a
    window._file_b = NistTransaction(source_path=file_b2_path)
    window._review_queue.start(file_a, [file_b1_path, file_b2_path])
    window._review_queue.record("PASS", file_b1)
    window._candidate_ready = True
    window._set_decision_buttons_enabled(True)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )

    window._end_current_session()

    assert window._history_store.count() == 0
    assert window.page_stack.currentWidget() is window.setup_page
    assert "Session ended" in window.statusBar().currentMessage()
    window.close()
    application.processEvents()


def test_completed_session_export_writes_only_session_rows_and_opens_folder(
    tmp_path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    output = tmp_path / "nist_session_decisions.xlsx"
    file_a_path = tmp_path / "a.nist"
    file_b_path = tmp_path / "b.nist"
    file_a_path.write_bytes(b"a")
    file_b_path.write_bytes(b"b")
    file_a = NistTransaction(source_path=file_a_path)
    file_b = NistTransaction(source_path=file_b_path)
    window = _window(tmp_path)
    window._review_queue.start(file_a, [file_b_path])
    decision = window._review_queue.record("MATCH", file_b)
    window._history_store.append(decision)
    monkeypatch.setattr(window._settings, "default_session_export_path", lambda: output)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    opened: list[str] = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )

    exported = window._offer_session_export([decision])

    assert exported == output
    assert output.exists()
    assert [Path(path) for path in opened] == [tmp_path]
    window.close()
    application.processEvents()


def test_pass_only_session_is_not_exported(tmp_path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    output = tmp_path / "nist_session_decisions.xlsx"
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b = NistTransaction(source_path=tmp_path / "b.nist")
    window = _window(tmp_path)
    window._review_queue.start(file_a, [file_b.source_path])
    decision = window._review_queue.record("PASS", file_b)
    monkeypatch.setattr(window._settings, "default_session_export_path", lambda: output)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: pytest.fail("PASS-only sessions must not prompt for export"),
    )

    exported = window._offer_session_export([decision])

    assert exported is None
    assert not output.exists()
    window.close()
    application.processEvents()


def test_completed_session_export_uses_selected_alternative_for_collision(
    tmp_path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    output = tmp_path / "session.xlsx"
    alternative = tmp_path / "session_2.xlsx"
    output.write_bytes(b"existing")
    file_a_path = tmp_path / "a.nist"
    file_b_path = tmp_path / "b.nist"
    file_a_path.write_bytes(b"a")
    file_b_path.write_bytes(b"b")
    file_a = NistTransaction(source_path=file_a_path)
    file_b = NistTransaction(source_path=file_b_path)
    window = _window(tmp_path)
    window._review_queue.start(file_a, [file_b_path])
    decision = window._review_queue.record("MATCH", file_b)
    window._history_store.append(decision)
    monkeypatch.setattr(window._settings, "default_session_export_path", lambda: output)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(window, "_resolve_existing_session_export", lambda path: alternative)
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: True)

    exported = window._offer_session_export([decision])

    assert exported == alternative
    assert output.read_bytes() == b"existing"
    assert alternative.exists()
    window.close()
    application.processEvents()


def test_history_dialog_displays_current_database_records(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    window = _window(tmp_path)
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b = NistTransaction(source_path=tmp_path / "b.nist")
    file_a.source_path.write_bytes(b"a")
    file_b.source_path.write_bytes(b"b")
    window._review_queue.start(file_a, [file_b.source_path])
    decision = window._review_queue.record("NO_MATCH", file_b)
    window._history_store.append(decision)

    dialog = DecisionHistoryDialog(window._history_store.query())

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 1).text() == "NO_MATCH"
    assert dialog.summary_label.text() == "1 decision record(s)"
    dialog.close()
    window.close()
    application.processEvents()


def test_main_window_can_delete_all_history_and_detach_active_decisions(
    tmp_path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b = NistTransaction(source_path=tmp_path / "b.nist")
    window = _window(tmp_path)
    window._review_queue.start(file_a, [file_b.source_path])
    decision = window._review_queue.record("MATCH", file_b)
    window._history_store.append(decision)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: QMessageBox.StandardButton.Yes,
    )

    window._clear_history()

    assert window._history_store.count() == 0
    assert decision.history_id is None
    assert window.results_label.text() == "Internal decision history: 0 record(s)"
    assert "Deleted 1 decision-history record(s)" in window.statusBar().currentMessage()
    assert window._offer_session_export(window._review_queue.decisions) is None
    window.close()
    application.processEvents()


def test_about_text_contains_developer_details() -> None:
    assert "Nektarios Christou" in ABOUT_TEXT
    assert "Hellenic Police" in ABOUT_TEXT
    assert "n.christou@police.gr" in ABOUT_TEXT
    assert "https://github.com/nekcht" in ABOUT_TEXT
    assert "Office of European Interoperability Applications" not in ABOUT_TEXT
    assert "Hellenic Police Headquarters" not in ABOUT_TEXT
    assert "10/06/2026" not in ABOUT_TEXT


def test_about_dialog_uses_clickable_professional_contact_details() -> None:
    application = QApplication.instance() or QApplication([])
    dialog = AboutDialog()

    assert dialog.details_label.openExternalLinks()
    assert "Visual review only" in dialog.details_label.text()
    assert "github.com/nekcht" in dialog.details_label.text()
    assert dialog.windowTitle() == "About NIST Fingerprint Comparator"
    dialog.close()
    application.processEvents()


def test_export_dialog_supports_optional_utc_range() -> None:
    application = QApplication.instance() or QApplication([])
    dialog = ExportHistoryDialog()

    assert dialog.selected_range_utc() == (None, None)
    assert dialog.start_edit.timeZone() == QTimeZone.utc()
    assert dialog.end_edit.timeZone() == QTimeZone.utc()
    dialog.filter_checkbox.setChecked(True)
    start, end = dialog.selected_range_utc()
    assert start is not None and end is not None
    assert start.tzinfo is not None and end.tzinfo is not None
    dialog.close()
    application.processEvents()
