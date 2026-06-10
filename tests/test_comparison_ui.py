# ruff: noqa: I001

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt, QTimeZone
from PySide6.QtWidgets import QApplication

from nist_fingerprint_comparator.core.models import BiometricImage
from nist_fingerprint_comparator.core.models import NistTransaction
from nist_fingerprint_comparator.core.pairing import build_cross_file_comparison, finger_details
from nist_fingerprint_comparator.core.review import DecisionHistoryStore
from nist_fingerprint_comparator.ui.comparison_grid import ComparisonGrid, DISCLAIMER
from nist_fingerprint_comparator.ui.export_dialog import ExportHistoryDialog
from nist_fingerprint_comparator.ui.main_window import ABOUT_TEXT, MainWindow
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

    assert [action.text() for action in window.menuBar().actions()] == [
        "&File",
        "&Edit",
        "&View",
        "&Help",
    ]
    assert window.main_toolbar.iconSize().width() == 18
    assert window.export_history_action.text() == "Export Decision History..."
    assert window.match_button.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert window.no_match_button.cursor().shape() == Qt.CursorShape.PointingHandCursor
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


def test_about_text_contains_developer_details() -> None:
    assert "Nektarios Christou" in ABOUT_TEXT
    assert "Hellenic Police" in ABOUT_TEXT
    assert "Office of European Interoperability Applications" in ABOUT_TEXT
    assert "European Information Systems Support Department" in ABOUT_TEXT
    assert "Directorate of Information Systems &amp; Digital Governance" in ABOUT_TEXT
    assert "Hellenic Police Headquarters" in ABOUT_TEXT
    assert "n.christou@police.gr" in ABOUT_TEXT
    assert "10/06/2026" in ABOUT_TEXT


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
