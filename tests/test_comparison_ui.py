# ruff: noqa: I001

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QSettings, Qt, QTimeZone, QUrl
from PySide6.QtGui import QAction, QPixmap
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
from nist_fingerprint_comparator.ui.fingerprint_card import FingerprintCard
from nist_fingerprint_comparator.ui.history_dialog import (
    HISTORY_PAGE_SIZE,
    DecisionHistoryDialog,
)
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


def _history_row(index: int) -> dict[str, str]:
    return {
        "history_id": str(index),
        "timestamp_utc": f"2026-06-10T12:{index:02}:00+00:00",
        "timestamp": f"12:{index:02} 10-06-2026",
        "timezone": "UTC",
        "decision": "MATCH",
        "file_a_name": "reference.nist",
        "file_b_name": f"comparison-{index}.nist",
        "file_a_reference_number": "REF",
        "file_b_reference_number": f"CMP-{index}",
    }


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
    pair_titles = [label.text() for label in grid.findChildren(QLabel, "pairTitle")]
    assert len(pair_titles) == 4
    assert pair_titles.count("Right Thumb") == 1
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
    assert not grid.findChildren(QLabel, "cardTitle")
    assert len(grid._cards) == 8
    grid.close()
    application.processEvents()


def test_main_window_records_final_queue_decision_without_ending_session(tmp_path) -> None:
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
    assert window._history_store.query()[0]["timezone"] == window._settings.history_timezone_id()
    assert window._file_a is file_a
    assert window._file_b is file_b
    assert window._review_queue.is_complete
    assert "Use End Session" in window.statusBar().currentMessage()
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


def test_main_window_pass_completes_without_saving_or_ending_session(tmp_path) -> None:
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
    assert window._review_queue.is_complete
    assert window._file_a is file_a
    assert window._file_b is file_b
    assert window.review_progress_bar.value() == 1
    assert window.review_progress_bar.property("complete") is True
    assert "Use End Session" in window.statusBar().currentMessage()
    window.close()
    application.processEvents()


def test_pass_counts_toward_incomplete_session_progress(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b1 = NistTransaction(source_path=tmp_path / "b1.nist")
    file_b2 = NistTransaction(source_path=tmp_path / "b2.nist")
    window = _window(tmp_path)
    window._file_a = file_a
    window._file_b = file_b1
    window._review_queue.start(file_a, [file_b1.source_path, file_b2.source_path])
    window._start_processing = lambda *_args: None

    window._record_decision("PASS")

    assert window.review_progress_bar.maximum() == 2
    assert window.review_progress_bar.value() == 1
    assert window.review_progress_bar.property("complete") is False
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
    assert window.view_history_action.text() == "Open History..."
    assert window.end_session_action.text() == "End Session"
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
    assert window.next_button.parentWidget() is window.status_navigation_bar
    assert window.end_session_button.parentWidget() is window.status_navigation_bar
    assert not window.previous_button.icon().isNull()
    assert not window.next_button.icon().isNull()
    assert not window.end_session_button.icon().isNull()
    status_layout = window.status_navigation_bar.layout()
    assert status_layout.indexOf(window.previous_button) < status_layout.indexOf(
        window.review_progress_bar
    )
    assert status_layout.indexOf(window.review_progress_bar) < status_layout.indexOf(
        window.next_button
    )
    assert status_layout.indexOf(window.next_button) < status_layout.indexOf(
        window.end_session_button
    )
    assert not window.review_progress_label.isVisible()
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
    assert any(
        group.title() == "Navigation Panel" for group in window.findChildren(QGroupBox)
    )
    assert window.file_a_widgets["metadata"].isHidden()
    assert window.file_b_widgets["metadata"].isHidden()
    assert "#69737d" in APP_STYLESHEET
    assert application_icon_path().is_file()
    assert not window.windowIcon().isNull()
    assert window.add_comparison_button.text() == ""
    assert not window.add_comparison_button.icon().isNull()
    assert window.add_comparison_button.toolTip() == "Select comparison records"
    assert window.page_stack.currentWidget() is window.setup_page
    window.close()
    application.processEvents()


def test_main_workflow_copy_is_concise_and_forensic_neutral(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    window = _window(tmp_path)
    copy = "\n".join(
        [
            *(label.text() for label in window.findChildren(QLabel)),
            *(button.text() for button in window.findChildren(QPushButton)),
            *(group.title() for group in window.findChildren(QGroupBox)),
            *(
                f"{action.text()} {action.toolTip()}"
                for action in window.findChildren(QAction)
            ),
        ]
    )

    assert "File A" not in copy
    assert "File B" not in copy
    assert "Visual comparison only" not in copy
    assert "does not perform biometric matching" not in copy
    assert "identity verification" not in copy
    assert window.findChild(QLabel, "setupText").text() == (
        "Add at least two ANSI/NIST records, or one ZIP/RAR archive."
    )

    window._toggle_metadata(True)
    assert window.statusBar().currentMessage() == "Sensitive metadata visible"
    window.close()
    application.processEvents()


def test_empty_states_use_short_wording() -> None:
    application = QApplication.instance() or QApplication([])
    grid = ComparisonGrid()
    missing = FingerprintCard("Right Index")
    undecoded = FingerprintCard("Right Index", _image("2"))

    assert grid.findChild(QLabel, "placeholder").text() == "No comparison selected"
    assert missing.placeholder.text() == "No image available"
    assert missing.image_stack.currentWidget() is missing.placeholder
    assert missing.image_stack.minimumHeight() == missing.viewer.minimumHeight()
    assert undecoded.placeholder.text() == "Image not decoded"

    grid.set_session(build_cross_file_comparison([], []))
    assert "No comparable impressions found" in [
        label.text() for label in grid.findChildren(QLabel, "placeholder")
    ]

    grid.close()
    missing.close()
    undecoded.close()
    application.processEvents()


def test_destructive_confirmations_remain_concise(tmp_path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    window = _window(tmp_path)
    window._candidate_ready = True
    end_prompt: list[tuple[str, str]] = []
    delete_prompt: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: end_prompt.append((args[1], args[2]))
        or QMessageBox.StandardButton.Cancel,
    )
    window._end_current_session()

    dialog = DecisionHistoryDialog([], clear_history=lambda: 0)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: delete_prompt.append((args[1], args[2]))
        or QMessageBox.StandardButton.Cancel,
    )
    dialog._confirm_delete_history()

    assert end_prompt == [
        ("End session", "End the current session? Completed decisions remain in History.")
    ]
    assert delete_prompt == [
        ("Delete history", "Delete all history? This cannot be undone.")
    ]
    dialog.close()
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


def test_record_headers_remain_outside_the_fingerprint_scroll_content() -> None:
    application = QApplication.instance() or QApplication([])
    session = build_cross_file_comparison([_image("1")], [_image("1")])
    grid = ComparisonGrid()

    grid.set_session(session)

    headers = grid.findChildren(QLabel, "recordHeaderTitle")
    assert [header.text() for header in headers] == [
        "Reference Record",
        "Comparison Record",
    ]
    assert all(
        header.parentWidget().parentWidget() is grid._header_container
        for header in headers
    )
    assert not grid._header_container.isHidden()
    assert grid.viewport().y() > grid._header_container.y()
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
    fitted: list[bool] = []
    window.comparison_grid.reset_zoom = lambda: fitted.append(True)
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
    assert window.review_progress_bar.maximum() == 1
    assert window.review_progress_bar.value() == 0
    assert not window.review_progress_label.isVisible()
    assert maximized == [True]
    application.processEvents()
    assert fitted
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

    assert "identical" in session.warnings[0]
    assert "without saving" in session.warnings[0]
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
    for path in paths:
        path.write_bytes(path.name.encode())
    dialog = ComparisonSetupDialog(tmp_path)

    dialog.set_source_selection(paths[:2])
    dialog.set_source_selection(paths[1:])

    assert dialog.record_list.count() == 3
    assert dialog._record_paths == paths
    dialog.close()
    application.processEvents()


def test_setup_dialog_accepts_dragged_record_group_and_zip(tmp_path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    records = [tmp_path / "one.nist", tmp_path / "two.dat"]
    archive = tmp_path / "records.zip"
    for path in [*records, archive]:
        path.write_bytes(path.name.encode())
    dialog = ComparisonSetupDialog(tmp_path)
    callbacks: list[object] = []
    monkeypatch.setattr(
        "nist_fingerprint_comparator.ui.setup_dialog.QTimer.singleShot",
        lambda _delay, callback: callbacks.append(callback),
    )

    record_drop = _drop_event(records)
    dialog.source_list.dropEvent(record_drop)

    assert record_drop.accepted
    assert dialog.record_list.count() == 0
    callbacks.pop(0)()
    assert dialog.record_list.count() == 2
    assert dialog.file_a_path is None
    assert not hasattr(dialog, "source_tabs")

    archive_drop = _drop_event([archive])
    dialog.source_list.dropEvent(archive_drop)

    assert archive_drop.accepted
    assert dialog.archive_path is None
    callbacks.pop(0)()
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
    assert dialog.source_status.text() == "RAR archive selected"
    dialog.close()
    application.processEvents()


def test_setup_dialog_uses_source_then_reference_phases(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    paths = [tmp_path / "one.nist", tmp_path / "two.nist"]
    dialog = ComparisonSetupDialog(tmp_path)
    dialog.set_record_selection(paths)

    assert dialog.phase_stack.currentIndex() == 0
    assert not hasattr(dialog, "back_button")
    assert not hasattr(dialog, "cancel_button")
    assert not dialog.clear_sources_button.icon().isNull()
    assert not dialog.next_button.icon().isNull()
    assert not dialog.reference_next_button.icon().isNull()
    assert not dialog.reference_back_button.icon().isNull()
    assert dialog.source_buttons_layout.indexOf(dialog.add_sources_button) >= 0
    assert dialog.source_buttons_layout.indexOf(dialog.clear_sources_button) >= 0
    assert dialog.source_buttons_layout.indexOf(dialog.next_button) == (
        dialog.source_buttons_layout.count() - 1
    )
    dialog._go_next()

    assert dialog.phase_stack.currentIndex() == 1
    assert dialog.file_a_path is None
    assert not dialog.reference_next_button.isEnabled()
    assert dialog.findChild(QLabel, "referenceGuidance").text() == (
        "Select the Reference Record. All other records will be compared against it."
    )
    assert all(button.text() != "Cancel" for button in dialog.findChildren(QPushButton))
    dialog.reference_list.select_reference(paths[0])
    assert dialog.file_a_path == paths[0]
    assert dialog.reference_next_button.isEnabled()
    dialog._go_back()
    assert dialog.phase_stack.currentIndex() == 0
    dialog.close()
    application.processEvents()


def test_setup_dialog_requires_explicit_reference_appointment(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    paths = [tmp_path / "one.nist", tmp_path / "two.nist"]
    dialog = ComparisonSetupDialog(tmp_path)
    dialog.set_record_selection(paths)
    dialog._go_next()

    dialog.reference_list.setCurrentRow(0)

    assert dialog.reference_list.currentRow() == 0
    assert dialog.file_a_path is None
    assert not dialog.reference_next_button.isEnabled()

    dialog.reference_list.itemClicked.emit(dialog.reference_list.item(0))

    assert dialog.file_a_path == paths[0]
    assert dialog.reference_next_button.isEnabled()
    dialog.close()
    application.processEvents()


def test_initial_screen_accepts_supported_drop_and_opens_setup(tmp_path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    paths = [tmp_path / "one.nist", tmp_path / "two.nist"]
    window = _window(tmp_path)
    opened: list[list[Path]] = []
    callbacks: list[object] = []
    window._open_comparison_setup = lambda initial_paths=None: opened.append(initial_paths)
    monkeypatch.setattr(
        "nist_fingerprint_comparator.ui.main_window.QTimer.singleShot",
        lambda _delay, callback: callbacks.append(callback),
    )
    event = _drop_event(paths)

    window.dropEvent(event)

    assert event.accepted
    assert opened == []
    callbacks.pop(0)()
    assert opened == [paths]
    window.close()
    application.processEvents()


def test_image_viewer_requires_ctrl_for_wheel_zoom_and_double_click_fits() -> None:
    application = QApplication.instance() or QApplication([])
    viewer = ImageViewer()
    viewer.set_pixmap(QPixmap(200, 200))
    initial_scale = viewer.transform().m11()

    scroll_event = _WheelEvent(120)
    viewer.wheelEvent(scroll_event)  # type: ignore[arg-type]

    assert viewer.transform().m11() == initial_scale
    assert scroll_event.ignored

    zoom_event = _WheelEvent(120, Qt.KeyboardModifier.ControlModifier)
    viewer.wheelEvent(zoom_event)  # type: ignore[arg-type]

    assert viewer.transform().m11() > initial_scale
    assert zoom_event.accepted

    double_click = _AcceptedEvent()
    viewer.mouseDoubleClickEvent(double_click)  # type: ignore[arg-type]

    assert viewer.transform().m11() == initial_scale
    assert double_click.accepted
    assert viewer.toolTip() == (
        "Ctrl + wheel to zoom\nDrag to pan\nDouble-click to fit"
    )
    assert not hasattr(viewer, "_tool_overlay")
    assert not hasattr(viewer, "zoom_in_button")
    viewer.close()
    application.processEvents()


def test_fingerprint_cards_do_not_expose_per_image_controls() -> None:
    application = QApplication.instance() or QApplication([])
    session = build_cross_file_comparison([_image("1")], [_image("1")])
    grid = ComparisonGrid()

    grid.set_session(session)

    assert len(grid._cards) == 2
    for card in grid._cards:
        assert not hasattr(card, "zoom_in_button")
        assert not hasattr(card, "zoom_out_button")
        assert not hasattr(card, "fit_button")
        assert card.metadata.minimumHeight() >= 180
        assert card.metadata.maximumHeight() > 100_000
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
    assert all(
        not button.icon().isNull()
        for button in dialog.findChildren(QPushButton)
        if button.text() == "Next"
    )
    assert all(button.text() != "Cancel" for button in dialog.findChildren(QPushButton))
    assert dialog.findChild(QLabel, "referenceGuidance").text() == (
        "Select the Reference Record. All other records will be compared against it."
    )
    dialog.close()
    application.processEvents()


def test_archive_reference_dialog_requires_explicit_reference_appointment(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    paths = [tmp_path / "first.nist", tmp_path / "second.nist"]
    dialog = ArchiveReferenceDialog(paths)
    next_button = next(
        button for button in dialog.findChildren(QPushButton) if button.text() == "Next"
    )

    dialog.record_list.setCurrentRow(0)

    assert dialog.record_list.currentRow() == 0
    assert dialog.reference_path is None
    assert not next_button.isEnabled()

    dialog.record_list.itemClicked.emit(dialog.record_list.item(0))

    assert dialog.reference_path == paths[0]
    assert next_button.isEnabled()
    dialog.close()
    application.processEvents()


def test_archive_selection_loads_extracted_files_then_cleans_temporary_directory(
    tmp_path,
    monkeypatch,
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
    window._candidate_ready = True
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    window._end_current_session()
    assert not extraction_directory.exists()
    assert window.page_stack.currentWidget() is window.setup_page
    assert "Session ended" in window.statusBar().currentMessage()
    window.close()
    application.processEvents()


def test_previous_comparison_navigates_without_erasing_decision(tmp_path) -> None:
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
    window._go_to_previous_comparison()

    assert window._history_store.count() == 1
    assert window._review_queue.decisions == [decision]
    assert window._review_queue.current_path == file_b1_path
    assert requested == [(file_b1_path, "b")]
    window.close()
    application.processEvents()


def test_next_comparison_navigates_to_next_undecided_pair_with_wraparound(
    tmp_path,
) -> None:
    application = QApplication.instance() or QApplication([])
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    candidates = [
        NistTransaction(source_path=tmp_path / f"b{index}.nist")
        for index in range(1, 5)
    ]
    window = _window(tmp_path)
    window._file_a = file_a
    window._review_queue.start(
        file_a,
        [candidate.source_path for candidate in candidates],
    )
    window._review_queue.set_current_index(1)
    window._review_queue.set_decision("MATCH", candidates[1])
    window._review_queue.set_current_index(3)
    window._candidate_ready = True
    requested: list[tuple[Path, str]] = []
    window._start_processing = lambda path, target: requested.append((path, target))
    window._set_decision_buttons_enabled(True)

    window.next_button.click()

    assert window._review_queue.current_path == candidates[0].source_path
    assert requested == [(candidates[0].source_path, "b")]
    window.close()
    application.processEvents()


def test_pair_navigation_shows_and_allows_changing_decisions(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b1 = NistTransaction(source_path=tmp_path / "b1.nist")
    file_b2 = NistTransaction(source_path=tmp_path / "b2.nist")
    window = _window(tmp_path)
    window._file_a = file_a
    window._review_queue.start(file_a, [file_b1.source_path, file_b2.source_path])
    window._candidate_transactions = {
        file_b1.source_path: file_b1,
        file_b2.source_path: file_b2,
    }
    window._populate_pair_navigation()
    window._activate_candidate(file_b1)

    window._record_decision("MATCH")

    assert window._review_queue.current_path == file_b2.source_path
    assert window.pair_navigation_list.item(0).text() == ""
    assert window.pair_navigation_list.item(0).sizeHint().height() == 28
    assert (
        window.pair_navigation_list.item(0).data(Qt.ItemDataRole.AccessibleTextRole)
        == "1. b1.nist | MATCH"
    )
    assert window._pair_navigation_rows[0][0].text() == "1. b1.nist"
    assert window._pair_navigation_rows[0][1].text() == "MATCH"
    assert window._pair_navigation_rows[0][1].property("decision") == "MATCH"
    assert window._pair_navigation_rows[1][1].property("decision") == "UNDECIDED"
    assert not window.match_button.isChecked()

    window.pair_navigation_list.setCurrentRow(0)
    assert window._file_b is file_b1
    assert window.match_button.isChecked()

    window._record_decision("NO_MATCH")

    assert window._history_store.count() == 1
    assert window._history_store.query()[0]["decision"] == "NO_MATCH"
    assert window.no_match_button.isChecked()
    assert not window.match_button.isChecked()
    assert window.pair_navigation_list.item(0).text() == ""
    assert window._pair_navigation_rows[0][1].text() == "NO MATCH"
    assert window._pair_navigation_rows[0][1].property("decision") == "NO_MATCH"
    window.close()
    application.processEvents()


def test_decision_button_selection_uses_clean_filled_highlight() -> None:
    assert "QPushButton#matchButton:checked" in APP_STYLESHEET
    assert "QPushButton#noMatchButton:checked" in APP_STYLESHEET
    assert "QPushButton#passButton:checked" in APP_STYLESHEET
    assert 'QProgressBar#reviewProgressBar[complete="true"]::chunk' in APP_STYLESHEET
    assert "border: 3px solid" not in APP_STYLESHEET


def test_all_decisions_keep_session_open_without_prompt(tmp_path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b = NistTransaction(source_path=tmp_path / "b.nist")
    window = _window(tmp_path)
    window._file_a = file_a
    window._file_b = file_b
    window._review_queue.start(file_a, [file_b.source_path])
    prompts: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: prompts.append((args[1], args[2]))
        or QMessageBox.StandardButton.Yes,
    )

    window._record_decision("MATCH")

    assert prompts == []
    assert window._review_queue.is_complete
    assert window._file_a is file_a
    assert window._file_b is file_b
    assert window.match_button.isChecked()
    assert "Use End Session" in window.statusBar().currentMessage()
    window.close()
    application.processEvents()


def test_auto_end_session_after_last_pending_pair_is_decided(tmp_path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    candidates = [
        NistTransaction(source_path=tmp_path / f"b{index}.nist")
        for index in range(1, 4)
    ]
    window = _window(tmp_path)
    window._settings.set_auto_end_session(True)
    window._settings.set_offer_session_export(False)
    window._file_a = file_a
    window._review_queue.start(
        file_a,
        [candidate.source_path for candidate in candidates],
    )
    for index in (0, 2):
        window._review_queue.set_current_index(index)
        prior, _ = window._review_queue.set_decision("MATCH", candidates[index])
        window._history_store.append(prior)
    window._review_queue.set_current_index(1)
    window._file_b = candidates[1]
    window._candidate_ready = True
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window._record_decision("NO_MATCH")

    assert messages == [
        (
            "Session completed",
            "All comparison pairs have a decision. The session ended automatically.",
        )
    ]
    assert window._history_store.count() == 3
    assert window.page_stack.currentWidget() is window.setup_page
    assert window._review_queue.candidate_paths == []
    assert "Session ended" in window.statusBar().currentMessage()
    window.close()
    application.processEvents()


def test_auto_end_notice_appears_before_export_prompt(tmp_path, monkeypatch) -> None:
    application = QApplication.instance() or QApplication([])
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b = NistTransaction(source_path=tmp_path / "b.nist")
    window = _window(tmp_path)
    window._settings.set_auto_end_session(True)
    window._file_a = file_a
    window._file_b = file_b
    window._review_queue.start(file_a, [file_b.source_path])
    window._candidate_ready = True
    prompts: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, title, message: prompts.append((title, message)),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda _parent, title, message, *_args: prompts.append((title, message))
        or QMessageBox.StandardButton.No,
    )

    window._record_decision("MATCH")

    assert prompts == [
        (
            "Session completed",
            "All comparison pairs have a decision. The session ended automatically.",
        ),
        ("Export session results", "Export completed results to XLSX?"),
    ]
    window.close()
    application.processEvents()


def test_completed_session_stays_open_after_navigation_decision_change(
    tmp_path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    file_a = NistTransaction(source_path=tmp_path / "a.nist")
    file_b1 = NistTransaction(source_path=tmp_path / "b1.nist")
    file_b2 = NistTransaction(source_path=tmp_path / "b2.nist")
    window = _window(tmp_path)
    window._file_a = file_a
    window._review_queue.start(file_a, [file_b1.source_path, file_b2.source_path])
    window._candidate_transactions = {
        file_b1.source_path: file_b1,
        file_b2.source_path: file_b2,
    }
    window._populate_pair_navigation()
    window._activate_candidate(file_b1)
    prompts: list[bool] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: prompts.append(True) or QMessageBox.StandardButton.Yes,
    )
    export_pages: list[object] = []
    window._offer_session_export = lambda decisions: export_pages.append(
        window.page_stack.currentWidget()
    )

    window._record_decision("MATCH")
    window._record_decision("NO_MATCH")
    assert window.page_stack.currentWidget() is window.workspace_page

    window.pair_navigation_list.setCurrentRow(0)
    window._record_decision("NO_MATCH")

    assert window.page_stack.currentWidget() is window.workspace_page
    assert window._review_queue.is_complete
    assert window._review_queue.candidate_paths == [
        file_b1.source_path,
        file_b2.source_path,
    ]
    assert prompts == []
    assert export_pages == []
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
    prompts: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: prompts.append((args[1], args[2]))
        or QMessageBox.StandardButton.Yes,
    )

    window._end_current_session()

    assert window._history_store.count() == 0
    assert window.page_stack.currentWidget() is window.setup_page
    assert "Session ended" in window.statusBar().currentMessage()
    assert prompts == [
        (
            "End session",
            "1 comparison pair has no decision. End the session anyway? "
            "Completed decisions remain in History.",
        )
    ]
    window.close()
    application.processEvents()


def test_completed_session_exports_only_after_user_ends_it(
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

    window._record_decision("MATCH")
    assert not output.exists()
    window._end_current_session()

    assert output.exists()
    assert "Export complete" in window.statusBar().currentMessage()
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
    assert "Export complete" in window.statusBar().currentMessage()
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
    window._candidate_ready = True
    prompts: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: prompts.append((args[1], args[2]))
        or QMessageBox.StandardButton.Yes,
    )

    window._end_current_session()

    assert "Session ended" in window.statusBar().currentMessage()
    assert prompts == [
        ("End session", "End the current session? Completed decisions remain in History.")
    ]
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
    assert dialog.summary_label.text() == "1 decision"
    assert dialog.export_history_button.text() == "Export..."
    assert not dialog.export_history_button.isEnabled()
    assert dialog.delete_selected_button.text() == "Delete Selected..."
    assert not dialog.delete_selected_button.isEnabled()
    assert dialog.delete_history_button.text() == "Delete History..."
    assert not dialog.delete_history_button.isEnabled()
    dialog.close()
    window.close()
    application.processEvents()


def test_history_dialog_paginates_only_when_more_than_fifty_records_exist() -> None:
    application = QApplication.instance() or QApplication([])
    rows = [_history_row(index) for index in range(HISTORY_PAGE_SIZE + 1)]
    page_requests: list[tuple[int, int]] = []

    def load_page(offset: int, limit: int) -> list[dict[str, str]]:
        page_requests.append((offset, limit))
        return rows[offset : offset + limit]

    dialog = DecisionHistoryDialog(
        rows[:HISTORY_PAGE_SIZE],
        total_count=len(rows),
        load_page=load_page,
    )

    assert dialog.table.rowCount() == HISTORY_PAGE_SIZE
    assert dialog.table.item(0, 4).text() == "comparison-0.nist"
    assert not dialog.previous_page_button.isHidden()
    assert not dialog.next_page_button.isHidden()
    assert dialog.page_label.text() == "Page 1 of 2"
    assert page_requests == []

    dialog.next_page_button.click()

    assert page_requests == [(HISTORY_PAGE_SIZE, HISTORY_PAGE_SIZE)]
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 4).text() == f"comparison-{HISTORY_PAGE_SIZE}.nist"
    assert dialog.page_label.text() == "Page 2 of 2"
    assert not dialog.next_page_button.isEnabled()
    dialog.close()

    one_page_dialog = DecisionHistoryDialog(rows[:HISTORY_PAGE_SIZE])
    assert one_page_dialog.previous_page_button.isHidden()
    assert one_page_dialog.next_page_button.isHidden()
    assert one_page_dialog.page_label.isHidden()
    one_page_dialog.close()
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
    assert dialog.summary_label.text() == "1 decision"
    assert window._history_store.count() == 1
    assert first.history_id is not None
    assert second.history_id is None
    assert window.statusBar().currentMessage() == "History record deleted"
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
    assert window.statusBar().currentMessage() == "History deleted | Records: 1"
    assert dialog.table.rowCount() == 0
    assert dialog.summary_label.text() == "0 decisions"
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
    assert dialog.findChild(QLabel, "aboutHeading").text() == "About"
    assert (
        dialog.findChild(QLabel, "aboutHeading").alignment()
        & Qt.AlignmentFlag.AlignCenter
    )
    dialog.close()
    application.processEvents()


def test_export_dialog_uses_settings_timezone_and_returns_utc_range() -> None:
    application = QApplication.instance() or QApplication([])
    timezone = QTimeZone(b"Europe/Athens")
    dialog = ExportHistoryDialog("Europe/Athens")

    assert dialog.selected_range_utc() == (None, None)
    assert dialog.start_edit.timeZone() == timezone
    assert dialog.end_edit.timeZone() == timezone
    assert dialog.start_edit.displayFormat() == "HH:mm dd-MM-yyyy"
    assert "Europe/Athens" in dialog.filter_checkbox.text()
    dialog.filter_checkbox.setChecked(True)
    start, end = dialog.selected_range_utc()
    assert start is not None and end is not None
    assert start.tzinfo is not None and end.tzinfo is not None
    dialog.close()
    application.processEvents()


def test_settings_dialog_lists_and_selects_history_timezone() -> None:
    application = QApplication.instance() or QApplication([])
    dialog = SettingsDialog("UTC", False, True)

    assert dialog.history_timezone_id == "UTC"
    assert dialog.timezone_combo.count() > 1
    assert dialog.windowTitle() == "Settings"
    assert not dialog.offer_session_export
    assert dialog.auto_end_session
    dialog.offer_session_export_checkbox.setChecked(True)
    dialog.auto_end_session_checkbox.setChecked(False)
    assert dialog.offer_session_export
    assert not dialog.auto_end_session
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


class _WheelDelta:
    def __init__(self, delta: int) -> None:
        self._delta = delta

    def y(self) -> int:
        return self._delta


class _WheelEvent:
    def __init__(
        self,
        delta: int,
        modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    ) -> None:
        self._delta = _WheelDelta(delta)
        self._modifiers = modifiers
        self.accepted = False
        self.ignored = False

    def angleDelta(self):  # noqa: N802
        return self._delta

    def pixelDelta(self):  # noqa: N802
        return _WheelDelta(0)

    def modifiers(self):
        return self._modifiers

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


class _AcceptedEvent:
    def __init__(self) -> None:
        self.accepted = False

    def accept(self) -> None:
        self.accepted = True
