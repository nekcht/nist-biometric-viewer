# ruff: noqa: I001

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QSettings, Qt, QTimeZone, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolBar,
)

from nist_fingerprint_comparator import __version__
from nist_fingerprint_comparator.core.models import BiometricImage
from nist_fingerprint_comparator.core.models import NistTransaction
from nist_fingerprint_comparator.core.archive import ArchiveComparisonSelection, ArchiveContents
from nist_fingerprint_comparator.core.pairing import build_cross_file_comparison, finger_details
from nist_fingerprint_comparator.core.review import DecisionHistoryStore
from nist_fingerprint_comparator.ui.about_dialog import ABOUT_TEXT, AboutDialog
from nist_fingerprint_comparator.ui.archive_reference_dialog import (
    ArchiveReferenceDialog,
    ReferenceRecordList,
)
from nist_fingerprint_comparator.ui.comparison_grid import ComparisonGrid
from nist_fingerprint_comparator.ui.export_dialog import ExportHistoryDialog
from nist_fingerprint_comparator.ui.history_dialog import DecisionHistoryDialog
from nist_fingerprint_comparator.ui.image_viewer import ImageViewer
from nist_fingerprint_comparator.ui.main_window import MainWindow
from nist_fingerprint_comparator.ui.resources import application_icon_path
from nist_fingerprint_comparator.ui.settings import AppSettings
from nist_fingerprint_comparator.ui.settings_dialog import SettingsDialog
from nist_fingerprint_comparator.ui.setup_dialog import ComparisonSetupDialog
from nist_fingerprint_comparator.ui.styles import APP_STYLESHEET


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
    session.file_a = NistTransaction(
        source_path=Path("reference.nist"),
        descriptive_metadata={"MN1": "REFERENCE-123"},
    )
    session.file_b = NistTransaction(
        source_path=Path("comparison.nist"),
        descriptive_metadata={"MN1": "COMPARISON-456"},
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
    assert not grid.findChildren(QLabel, "disclaimer")
    assert not grid.findChildren(QLabel, "sectionTitle")
    assert not grid.findChildren(QLabel, "pairTitle")
    assert [label.text() for label in grid.findChildren(QLabel, "recordHeaderTitle")] == [
        "Reference Record",
        "Comparison Record",
    ]
    assert [
        label.text()
        for label in grid.findChildren(QLabel, "recordHeaderReferenceNumber")
    ] == [
        "Reference number: REFERENCE-123",
        "Reference number: COMPARISON-456",
    ]
    assert all(
        "Reference Record" not in label.text() and "Comparison Record" not in label.text()
        for label in grid.findChildren(QLabel, "cardTitle")
    )
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
    window._settings.set_offer_session_export(False)

    window._record_decision("NO_MATCH")

    assert window._history_store.count() == 1
    assert window._history_store.query()[0]["timezone"] == window._settings.history_timezone_id()
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
    window._first_pair_ready = True
    window.page_stack.setCurrentWidget(window.workspace_page)
    requested: list[tuple[Path, str]] = []
    window._start_processing = lambda path, target: requested.append((path, target))

    window._record_decision("MATCH")

    assert requested == [(file_b2_path, "b")]
    assert window._review_queue.current_path == file_b2_path
    assert window._file_a is file_a
    assert window._file_b is None
    assert window.page_stack.currentWidget() is window.workspace_page
    assert window._workspace_loading
    assert not window.workspace_page.isEnabled()
    assert window._workspace_loading_effect.isEnabled()
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
    window._file_a = file_a
    window._file_b = file_b
    window._review_queue.start(file_a, [file_b_path])

    window._record_decision("PASS")

    assert window._history_store.count() == 0
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
    assert window._start_candidate_after_thread
    window.close()
    application.processEvents()


def test_main_window_has_professional_menus_without_toolbars(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    window = _window(tmp_path)
    assert [action.text() for action in window.menuBar().actions()] == [
        "&File",
        "&Edit",
        "&View",
        "&Help",
    ]
    assert window.windowTitle() == "Nist Biometric Viewer"
    assert window.size().width() == 1100
    assert window.size().height() == 720
    assert window.findChildren(QToolBar) == []
    assert not hasattr(window, "export_history_action")
    assert window.match_button.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert window.no_match_button.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert window.pass_button.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert window.pass_button.text() == "PASS"
    assert window.view_history_action.text() == "View Comparison History..."
    assert window.end_session_action.text() == "End Current Session"
    assert window.settings_action.text() == "Settings..."
    file_actions = [
        action.text()
        for action in window.file_menu.actions()
        if not action.isSeparator()
    ]
    assert file_actions[-2:] == ["Settings...", "Exit"]
    assert [action.text() for action in window.file_menu.actions()][-2:] == [
        "Settings...",
        "Exit",
    ]
    assert window.settings_action not in window.edit_menu.actions()
    assert window.previous_button.parentWidget() is window.status_navigation_bar
    assert window.end_session_button.parentWidget() is window.status_navigation_bar
    assert not window.previous_button.icon().isNull()
    assert not window.end_session_button.icon().isNull()
    assert window.match_button.parentWidget() is window.bottom_decision_bar
    assert window.no_match_button.parentWidget() is window.bottom_decision_bar
    assert window.pass_button.parentWidget() is window.bottom_decision_bar
    decision_layout = window.bottom_decision_bar.layout()
    assert decision_layout.indexOf(window.pass_button) < decision_layout.indexOf(
        window.no_match_button
    )
    assert decision_layout.indexOf(window.no_match_button) < decision_layout.indexOf(
        window.match_button
    )
    assert not any(group.title() == "Review queue" for group in window.findChildren(QGroupBox))
    assert window.file_a_widgets["metadata"].isHidden()
    assert window.file_b_widgets["metadata"].isHidden()
    assert "#69737d" in APP_STYLESHEET
    assert application_icon_path().is_file()
    assert not window.windowIcon().isNull()
    assert window.add_comparison_button.text() == ""
    assert not window.add_comparison_button.icon().isNull()
    assert "ZIP/RAR" in window.add_comparison_button.toolTip()
    assert window.page_stack.currentWidget() is window.setup_page
    window.close()
    application.processEvents()


def test_record_details_are_collapsed_until_requested(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    window = _window(tmp_path)
    details = window.file_a_widgets["details"]
    metadata = window.file_a_widgets["metadata"]
    assert isinstance(details, QGroupBox)

    assert not details.isChecked()
    assert metadata.isHidden()
    details.setChecked(True)

    assert not metadata.isHidden()
    window.close()
    application.processEvents()


def test_new_comparison_pair_resets_grid_scroll_to_top() -> None:
    application = QApplication.instance() or QApplication([])
    session = build_cross_file_comparison([_image("1")], [_image("1")])
    grid = ComparisonGrid()
    grid.verticalScrollBar().setRange(0, 100)
    grid.verticalScrollBar().setValue(80)

    grid.set_session(session)

    assert grid.verticalScrollBar().value() == 0
    grid.close()
    application.processEvents()


def test_workspace_appears_only_after_first_complete_pair(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    file_a_path = tmp_path / "a.nist"
    file_b_path = tmp_path / "b.nist"
    file_a_path.write_bytes(b"a")
    file_b_path.write_bytes(b"b")
    window = _window(tmp_path)
    maximized: list[bool] = []
    window.showMaximized = lambda: maximized.append(True)
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
    assert not window._workspace_loading
    assert window.workspace_page.isEnabled()
    assert not window._workspace_loading_effect.isEnabled()
    assert window.review_progress_label.text() == "Comparison 1 of 1: b.nist"
    assert maximized == [True]
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
    assert "PASS is not saved to history" in session.warnings[0]
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
    assert dialog.record_list.count() == 3
    assert dialog.record_list.item(0).text().startswith("ANSI/NIST Record:")
    assert isinstance(dialog.reference_list, ReferenceRecordList)
    assert dialog.reference_list.item(0).text() == "a.nist"
    dialog.close()
    application.processEvents()


def test_setup_dialog_appoints_reference_from_one_unified_record_group(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    paths = [tmp_path / name for name in ("one.nist", "two.an2", "three.eft")]
    dialog = ComparisonSetupDialog(tmp_path)

    dialog.set_record_selection(paths)

    assert dialog.file_a_path is None
    assert dialog.candidate_paths == []
    dialog.reference_list.select_reference(paths[1])

    assert dialog.file_a_path == paths[1]
    assert dialog.candidate_paths == [paths[0], paths[2]]
    assert dialog.reference_list.currentItem().text() == "two.an2"
    dialog.close()
    application.processEvents()


def test_setup_dialog_adds_individual_record_selections_incrementally(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    paths = [tmp_path / name for name in ("one.nist", "two.nist", "three.nist")]
    dialog = ComparisonSetupDialog(tmp_path)

    dialog.set_source_selection(paths[:2])
    dialog.set_source_selection(paths[1:])

    assert dialog.record_list.count() == 3
    assert dialog._record_paths == paths
    dialog.close()
    application.processEvents()


def test_setup_dialog_accepts_dragged_record_group_and_zip(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    records = [tmp_path / "one.nist", tmp_path / "two.dat"]
    archive = tmp_path / "records.zip"
    dialog = ComparisonSetupDialog(tmp_path)

    record_drop = _drop_event(records)
    dialog.source_list.dropEvent(record_drop)

    assert record_drop.accepted
    assert dialog.record_list.count() == 2
    assert dialog.file_a_path is None
    assert not hasattr(dialog, "source_tabs")

    archive_drop = _drop_event([archive])
    dialog.source_list.dropEvent(archive_drop)

    assert archive_drop.accepted
    assert dialog.archive_path == archive
    assert dialog.source_list.count() == 1
    assert dialog.source_list.item(0).text() == f"ZIP Archive: {archive}"
    assert not hasattr(dialog, "archive_edit")
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


def test_setup_dialog_accepts_rar_archive_as_alternative(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    archive_path = tmp_path / "records.rar"
    dialog = ComparisonSetupDialog(tmp_path)

    dialog.set_archive_selection(archive_path)

    assert dialog.archive_path == archive_path
    assert dialog.source_list.item(0).text() == f"RAR Archive: {archive_path}"
    assert "extract" in dialog.source_status.text()
    dialog.close()
    application.processEvents()


def test_setup_dialog_uses_source_then_reference_phases(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    paths = [tmp_path / "one.nist", tmp_path / "two.nist"]
    dialog = ComparisonSetupDialog(tmp_path)
    dialog.set_record_selection(paths)

    assert dialog.phase_stack.currentIndex() == 0
    assert not hasattr(dialog, "back_button")
    dialog._go_next()

    assert dialog.phase_stack.currentIndex() == 1
    assert dialog.file_a_path is None
    dialog.reference_list.select_reference(paths[0])
    assert dialog.file_a_path == paths[0]
    dialog.close()
    application.processEvents()


def test_initial_screen_accepts_supported_drop_and_opens_setup(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    paths = [tmp_path / "one.nist", tmp_path / "two.nist"]
    window = _window(tmp_path)
    opened: list[list[Path]] = []
    window._open_comparison_setup = lambda initial_paths=None: opened.append(initial_paths)
    event = _drop_event(paths)

    window.dropEvent(event)

    assert event.accepted
    assert opened == [paths]
    window.close()
    application.processEvents()


def test_image_viewer_uses_explicit_zoom_controls_and_ignores_wheel_zoom() -> None:
    application = QApplication.instance() or QApplication([])
    viewer = ImageViewer()
    viewer.set_pixmap(QPixmap(200, 200))
    initial_scale = viewer.transform().m11()

    viewer.zoom_in()
    zoomed_scale = viewer.transform().m11()
    viewer.zoom_out()
    wheel_event = _IgnoredWheelEvent()
    viewer.wheelEvent(wheel_event)  # type: ignore[arg-type]

    assert zoomed_scale > initial_scale
    assert viewer.transform().m11() == initial_scale
    assert wheel_event.ignored
    assert not viewer._tool_overlay.isHidden()
    assert all(
        not button.icon().isNull()
        for button in (viewer.zoom_out_button, viewer.fit_button, viewer.zoom_in_button)
    )
    viewer.close()
    application.processEvents()


def test_fingerprint_cards_expose_per_image_controls() -> None:
    application = QApplication.instance() or QApplication([])
    session = build_cross_file_comparison([_image("1")], [_image("1")])
    grid = ComparisonGrid()

    grid.set_session(session)

    assert len(grid._cards) == 2
    for card in grid._cards:
        assert card.zoom_in_button.toolTip() == "Zoom In"
        assert card.zoom_out_button.toolTip() == "Zoom Out"
        assert card.fit_button.toolTip() == "Fit Image"
        assert card.zoom_in_button.parentWidget() is card.viewer._tool_overlay
        assert card.zoom_out_button.parentWidget() is card.viewer._tool_overlay
        assert card.fit_button.parentWidget() is card.viewer._tool_overlay
        assert not card.zoom_in_button.icon().isNull()
        assert not card.zoom_out_button.icon().isNull()
        assert not card.fit_button.icon().isNull()
    grid.close()
    application.processEvents()


def test_archive_reference_dialog_selects_reference_record(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    paths = [tmp_path / "first" / "record.nist", tmp_path / "second" / "record.nist"]
    dialog = ArchiveReferenceDialog(paths)

    assert dialog.reference_path is None
    dialog.select_reference(paths[1])

    assert dialog.reference_path == paths[1]
    assert isinstance(dialog.record_list, ReferenceRecordList)
    assert dialog.record_list.item(0).text() == str(Path("first") / "record.nist")
    assert dialog.record_list.item(1).text() == str(Path("second") / "record.nist")
    assert dialog.windowTitle() == "Select Reference Record"
    assert any(button.text() == "Next" for button in dialog.findChildren(QPushButton))
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
    window._select_archive_reference = lambda contents: ArchiveComparisonSelection(
        file_a_path=file_a,
        candidate_paths=[file_b],
    )
    window._archive_processing_finished(ArchiveContents([file_a, file_b]))
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


def test_completed_session_offers_to_export_only_its_saved_results(
    tmp_path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    output = tmp_path / "session-results.xlsx"
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b = NistTransaction(source_path=tmp_path / "b.nist")
    file_a.source_path.write_bytes(b"a")
    file_b.source_path.write_bytes(b"b")
    window = _window(tmp_path)
    window._file_a = file_a
    window._file_b = file_b
    window._review_queue.start(file_a, [file_b.source_path])
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args: (str(output), "Excel workbooks (*.xlsx)"),
    )

    window._record_decision("MATCH")

    assert output.exists()
    assert "Session results exported" in window.statusBar().currentMessage()
    window.close()
    application.processEvents()


def test_ended_session_offers_to_export_its_completed_results(
    tmp_path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    output = tmp_path / "ended-session-results.xlsx"
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b1 = NistTransaction(source_path=tmp_path / "b1.nist")
    file_b2 = NistTransaction(source_path=tmp_path / "b2.nist")
    window = _window(tmp_path)
    window._file_a = file_a
    window._file_b = file_b2
    window._review_queue.start(file_a, [file_b1.source_path, file_b2.source_path])
    decision = window._review_queue.record("NO_MATCH", file_b1)
    window._history_store.append(decision)
    window._candidate_ready = True
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args: (str(output), "Excel workbooks (*.xlsx)"),
    )

    window._end_current_session()

    assert output.exists()
    assert "Session results exported" in window.statusBar().currentMessage()
    window.close()
    application.processEvents()


def test_session_export_prompt_can_be_disabled(tmp_path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b = NistTransaction(source_path=tmp_path / "b.nist")
    window = _window(tmp_path)
    window._settings.set_offer_session_export(False)
    window._review_queue.start(file_a, [file_b.source_path])
    decision = window._review_queue.record("MATCH", file_b)
    decision.history_id = 1
    prompted: list[bool] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: prompted.append(True) or QMessageBox.StandardButton.Yes,
    )

    window._finish_review()

    assert "Review complete" in window.statusBar().currentMessage()
    assert prompted == []
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
    assert dialog.table.item(0, 1).text() == "UTC"
    assert dialog.table.item(0, 2).text() == "NO_MATCH"
    assert dialog.summary_label.text() == "1 decision record(s)"
    assert dialog.export_history_button.text() == "Export History..."
    assert not dialog.export_history_button.isEnabled()
    assert dialog.delete_selected_button.text() == "Delete Selected Row..."
    assert not dialog.delete_selected_button.isEnabled()
    assert dialog.delete_history_button.text() == "Delete All History..."
    assert not dialog.delete_history_button.isEnabled()
    dialog.close()
    window.close()
    application.processEvents()


def test_history_dialog_exports_only_through_its_export_button(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    window = _window(tmp_path)
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b = NistTransaction(source_path=tmp_path / "b.nist")
    window._review_queue.start(file_a, [file_b.source_path])
    decision = window._review_queue.record("MATCH", file_b)
    window._history_store.append(decision)
    exported: list[bool] = []
    dialog = DecisionHistoryDialog(
        window._history_store.query(),
        export_history=lambda: exported.append(True),
    )

    assert not hasattr(window, "export_history_action")
    assert dialog.export_history_button.isEnabled()
    dialog.export_history_button.click()

    assert exported == [True]
    dialog.close()
    window.close()
    application.processEvents()


def test_history_dialog_can_delete_selected_row_and_detach_active_decision(
    tmp_path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b1 = NistTransaction(source_path=tmp_path / "b1.nist")
    file_b2 = NistTransaction(source_path=tmp_path / "b2.nist")
    window = _window(tmp_path)
    window._review_queue.start(file_a, [file_b1.source_path, file_b2.source_path])
    first = window._review_queue.record("MATCH", file_b1)
    second = window._review_queue.record("NO_MATCH", file_b2)
    window._history_store.append(first)
    window._history_store.append(second)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    dialog = DecisionHistoryDialog(
        window._history_store.query(),
        delete_record=window._delete_history_record,
    )

    dialog.table.selectRow(0)
    assert dialog.delete_selected_button.isEnabled()
    dialog.delete_selected_button.click()

    assert dialog.table.rowCount() == 1
    assert dialog.summary_label.text() == "1 decision record(s)"
    assert window._history_store.count() == 1
    assert first.history_id is None
    assert second.history_id is not None
    assert "Deleted selected decision-history record" in window.statusBar().currentMessage()
    dialog.close()
    window.close()
    application.processEvents()


def test_history_dialog_can_delete_all_history_and_detach_active_decisions(
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
    dialog = DecisionHistoryDialog(
        window._history_store.query(),
        clear_history=window._delete_all_history_records,
    )

    assert dialog.delete_history_button.isEnabled()
    dialog.delete_history_button.click()

    assert window._history_store.count() == 0
    assert decision.history_id is None
    assert "Deleted 1 decision-history record(s)" in window.statusBar().currentMessage()
    assert dialog.table.rowCount() == 0
    assert not dialog.export_history_button.isEnabled()
    assert not dialog.delete_history_button.isEnabled()
    assert not hasattr(window, "clear_history_action")
    dialog.close()
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
    assert __version__ in ABOUT_TEXT


def test_about_dialog_uses_clickable_professional_contact_details() -> None:
    application = QApplication.instance() or QApplication([])
    dialog = AboutDialog()

    assert dialog.details_label.openExternalLinks()
    assert "Visual review only" in dialog.details_label.text()
    assert "github.com/nekcht" in dialog.details_label.text()
    assert dialog.windowTitle() == "About Nist Biometric Viewer"
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


def test_settings_dialog_lists_and_selects_history_timezone() -> None:
    application = QApplication.instance() or QApplication([])
    dialog = SettingsDialog("UTC", False)

    assert dialog.history_timezone_id == "UTC"
    assert dialog.timezone_combo.count() > 1
    assert dialog.windowTitle() == "Settings"
    assert not dialog.offer_session_export
    dialog.offer_session_export_checkbox.setChecked(True)
    assert dialog.offer_session_export
    dialog.close()
    application.processEvents()


def _drop_event(paths: list[Path]):
    return _DropEvent(paths)


class _DropEvent:
    def __init__(self, paths: list[Path]) -> None:
        self._mime_data = QMimeData()
        self._mime_data.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        self.accepted = False

    def mimeData(self) -> QMimeData:  # noqa: N802
        return self._mime_data

    def acceptProposedAction(self) -> None:  # noqa: N802
        self.accepted = True

    def ignore(self) -> None:
        self.accepted = False


class _IgnoredWheelEvent:
    def __init__(self) -> None:
        self.ignored = False

    def ignore(self) -> None:
        self.ignored = True
