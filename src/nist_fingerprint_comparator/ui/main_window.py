"""Main application window."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QSize, Qt, QThread, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nist_fingerprint_comparator.core.archive import ArchiveComparisonSelection
from nist_fingerprint_comparator.core.models import NistTransaction
from nist_fingerprint_comparator.core.pairing import (
    build_cross_file_comparison,
    files_have_same_content,
)
from nist_fingerprint_comparator.core.review import (
    DecisionHistoryStore,
    DecisionXlsxExporter,
    ReviewDecision,
    ReviewDecisionValue,
    ReviewQueue,
    available_export_path,
    decision_record,
)

from .about_dialog import AboutDialog
from .comparison_grid import ComparisonGrid
from .export_dialog import ExportHistoryDialog
from .history_dialog import DecisionHistoryDialog
from .metadata_panel import MetadataPanel
from .resources import application_icon
from .settings import AppSettings
from .setup_dialog import ComparisonSetupDialog
from .worker import ArchiveWorker, ParseWorker


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: AppSettings | None = None,
        history_store: DecisionHistoryStore | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("NIST Fingerprint Comparator")
        self.setWindowIcon(application_icon())
        self.resize(1440, 900)
        self._thread: QThread | None = None
        self._worker: ArchiveWorker | ParseWorker | None = None
        self._processing_target: str | None = None
        self._file_a: NistTransaction | None = None
        self._file_b: NistTransaction | None = None
        self._review_queue = ReviewQueue()
        self._candidate_ready = False
        self._settings = settings or AppSettings()
        self._history_store = history_store or DecisionHistoryStore(
            self._settings.history_database_path()
        )
        self._xlsx_exporter = DecisionXlsxExporter()
        self._pending_candidate_paths: list[Path] = []
        self._archive_temp_directory: TemporaryDirectory | None = None
        self._archive_selection_after_thread: ArchiveComparisonSelection | None = None
        self._first_pair_ready = False
        self._start_candidate_after_thread = False

        self._create_actions()
        self._create_toolbar()
        self._create_menus()
        self._create_content()
        self.statusBar().showMessage("Ready")

    def _create_actions(self) -> None:
        self.new_comparison_action = self._create_action(
            "New Comparison...",
            QStyle.StandardPixmap.SP_DialogOpenButton,
            "Select a comparison ZIP or File A and all File B candidates",
            self.new_comparison,
            shortcut="Ctrl+N",
        )

        self.export_history_action = self._create_action(
            "Export Decision History...",
            QStyle.StandardPixmap.SP_DialogSaveButton,
            "Export all or a UTC time range of internal decision history to XLSX",
            self._export_history,
        )

        self.view_history_action = self._create_action(
            "View Decision History...",
            QStyle.StandardPixmap.SP_FileDialogContentsView,
            "Display all records in the internal decision history",
            self._show_history,
        )

        self.clear_history_action = self._create_action(
            "Delete All Decision History...",
            QStyle.StandardPixmap.SP_TrashIcon,
            "Permanently delete every record from internal decision history",
            self._clear_history,
        )

        self.previous_comparison_action = self._create_action(
            "Previous Comparison",
            QStyle.StandardPixmap.SP_ArrowBack,
            "Undo the previous result and review that candidate again",
            self._go_to_previous_comparison,
        )
        self.previous_comparison_action.setEnabled(False)

        self.end_session_action = self._create_action(
            "End Current Session",
            QStyle.StandardPixmap.SP_DialogCloseButton,
            "End the active review session and keep decisions already completed",
            self._end_current_session,
        )
        self.end_session_action.setEnabled(False)

        self.reset_zoom_action = self._create_action(
            "Reset Zoom",
            QStyle.StandardPixmap.SP_BrowserReload,
            "Fit every biometric image to its viewer",
            self._reset_zoom,
            shortcut="Ctrl+0",
        )

        self.metadata_action = self._create_action(
            "Toggle Metadata",
            QStyle.StandardPixmap.SP_FileDialogInfoView,
            "Show or hide image metadata tables",
            self._toggle_metadata,
            checkable=True,
            checked=True,
        )

        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.triggered.connect(self.close)

        self.about_action = QAction("About NIST Fingerprint Comparator", self)
        self.about_action.triggered.connect(self._show_about)

    def _create_action(
        self,
        text: str,
        standard_icon: QStyle.StandardPixmap,
        status_tip: str,
        callback,
        *,
        shortcut: str | None = None,
        checkable: bool = False,
        checked: bool = False,
    ) -> QAction:
        action = QAction(text, self)
        action.setIcon(self.style().standardIcon(standard_icon))
        action.setStatusTip(status_tip)
        action.setToolTip(status_tip)
        action.setCheckable(checkable)
        action.setChecked(checked)
        if shortcut is not None:
            action.setShortcut(shortcut)
        if checkable:
            action.toggled.connect(callback)
        else:
            action.triggered.connect(callback)
        return action

    def _create_toolbar(self) -> None:
        self.main_toolbar = self.addToolBar("Review Tools")
        self.main_toolbar.setObjectName("reviewToolsToolbar")
        self.main_toolbar.setMovable(False)
        self.main_toolbar.setIconSize(QSize(20, 20))
        self.main_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.main_toolbar.addAction(self.new_comparison_action)
        self.main_toolbar.addSeparator()
        self.main_toolbar.addAction(self.export_history_action)
        self.main_toolbar.addAction(self.view_history_action)
        self.main_toolbar.addAction(self.clear_history_action)
        self.main_toolbar.addSeparator()
        self.main_toolbar.addAction(self.previous_comparison_action)
        self.main_toolbar.addAction(self.end_session_action)
        self.main_toolbar.addSeparator()
        self.main_toolbar.addAction(self.reset_zoom_action)
        self.main_toolbar.addAction(self.metadata_action)
        for button in self.main_toolbar.findChildren(QToolButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)

    def _create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.new_comparison_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_history_action)
        file_menu.addAction(self.view_history_action)
        file_menu.addAction(self.clear_history_action)
        file_menu.addSeparator()
        file_menu.addAction(self.end_session_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.previous_comparison_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.reset_zoom_action)

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.metadata_action)
        view_menu.addAction(self.main_toolbar.toggleViewAction())

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.about_action)

    def _create_content(self) -> None:
        self.page_stack = QStackedWidget()
        self.setup_page = self._build_setup_page()
        self.loading_page = self._build_loading_page()
        self.workspace_page = self._build_workspace_page()
        self.page_stack.addWidget(self.setup_page)
        self.page_stack.addWidget(self.loading_page)
        self.page_stack.addWidget(self.workspace_page)
        self.setCentralWidget(self.page_stack)
        self.page_stack.setCurrentWidget(self.setup_page)
        self.reset_zoom_action.setEnabled(False)
        self.metadata_action.setEnabled(False)

    def _build_setup_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("setupPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(80, 80, 80, 80)
        layout.addStretch(1)
        title = QLabel("Start a one-to-many fingerprint comparison")
        title.setObjectName("setupTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = QLabel(
            "Select a comparison ZIP archive, or select the reference File A and the "
            "complete File B candidate group individually. The visual comparison workspace "
            "opens when the first pair is ready."
        )
        text.setObjectName("setupText")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setWordWrap(True)
        start_button = QPushButton("New Comparison...")
        start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        start_button.clicked.connect(self.new_comparison)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(start_button)
        button_row.addStretch(1)
        layout.addWidget(title)
        layout.addSpacing(12)
        layout.addWidget(text)
        layout.addSpacing(20)
        layout.addLayout(button_row)
        layout.addStretch(2)
        return page

    def _build_loading_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("loadingPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(120, 80, 120, 80)
        layout.addStretch(1)
        title = QLabel("Loading biometric transactions")
        title.setObjectName("loadingTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_message = QLabel("Preparing comparison...")
        self.loading_message.setObjectName("loadingMessage")
        self.loading_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_message.setWordWrap(True)
        self.loading_progress = QProgressBar()
        self.loading_progress.setObjectName("loadingProgress")
        self.loading_progress.setRange(0, 0)
        self.loading_progress.setTextVisible(False)
        layout.addWidget(title)
        layout.addSpacing(14)
        layout.addWidget(self.loading_message)
        layout.addSpacing(18)
        layout.addWidget(self.loading_progress)
        layout.addStretch(2)
        return page

    def _build_workspace_page(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_sidebar())
        self.comparison_grid = ComparisonGrid()
        splitter.addWidget(self.comparison_grid)
        splitter.setSizes([330, 1110])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        workspace = QWidget()
        workspace.setObjectName("workspacePage")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_decision_bar())
        layout.addWidget(splitter, 1)
        return workspace

    def _build_decision_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("decisionBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        self.review_progress_label = QLabel(
            "Review decisions become available when a complete comparison pair is ready."
        )
        self.review_progress_label.setObjectName("reviewProgress")
        self.match_button = QPushButton("MATCH")
        self.match_button.setObjectName("matchButton")
        self.match_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.match_button.clicked.connect(lambda: self._record_decision("MATCH"))
        self.no_match_button = QPushButton("NO MATCH")
        self.no_match_button.setObjectName("noMatchButton")
        self.no_match_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.no_match_button.clicked.connect(lambda: self._record_decision("NO_MATCH"))
        self.pass_button = QPushButton("PASS")
        self.pass_button.setObjectName("passButton")
        self.pass_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pass_button.clicked.connect(lambda: self._record_decision("PASS"))
        self.previous_button = QPushButton("Previous Comparison")
        self.previous_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.previous_button.clicked.connect(self._go_to_previous_comparison)
        self.end_session_button = QPushButton("End Session")
        self.end_session_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.end_session_button.clicked.connect(self._end_current_session)
        layout.addWidget(self.review_progress_label, 1)
        layout.addWidget(self.previous_button)
        layout.addWidget(self.end_session_button)
        layout.addWidget(self.match_button)
        layout.addWidget(self.no_match_button)
        layout.addWidget(self.pass_button)
        self._set_decision_buttons_enabled(False)
        return bar

    def _build_sidebar(self) -> QWidget:
        sidebar_content = QWidget()
        layout = QVBoxLayout(sidebar_content)
        layout.setContentsMargins(10, 10, 10, 10)

        review_group = QGroupBox("Review queue")
        review_layout = QVBoxLayout(review_group)
        self.queue_label = QLabel("No B candidates selected")
        self.queue_label.setWordWrap(True)
        self.results_label = QLabel(self._history_summary())
        self.results_label.setWordWrap(True)
        review_layout.addWidget(self.queue_label)
        review_layout.addWidget(self.results_label)

        file_a_group, self.file_a_widgets = self._build_file_sidebar_group("Reference File A")
        file_b_group, self.file_b_widgets = self._build_file_sidebar_group(
            "Current File B Candidate"
        )
        layout.addWidget(review_group)
        layout.addWidget(file_a_group)
        layout.addWidget(file_b_group)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(sidebar_content)
        scroll.setMinimumWidth(300)
        return scroll

    def _build_file_sidebar_group(self, title: str) -> tuple[QGroupBox, dict[str, QWidget]]:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        file_label = QLabel("Not loaded")
        file_label.setWordWrap(True)
        summary_label = QLabel("Records: 0\nBiometric images: 0\nWarnings: 0")
        metadata = MetadataPanel()
        metadata.setMaximumHeight(190)
        warnings = QPlainTextEdit()
        warnings.setReadOnly(True)
        warnings.setMaximumHeight(110)
        warnings.setPlaceholderText("No parser warnings.")
        layout.addWidget(file_label)
        layout.addWidget(summary_label)
        layout.addWidget(metadata)
        layout.addWidget(warnings)
        return group, {
            "file": file_label,
            "summary": summary_label,
            "metadata": metadata,
            "warnings": warnings,
        }

    def new_comparison(self) -> None:
        initial_directory = self._file_a.source_path.parent if self._file_a else Path.home()
        dialog = ComparisonSetupDialog(initial_directory, self)
        if not dialog.exec():
            return
        if dialog.archive_path is not None:
            self.start_archive_comparison(dialog.archive_path)
        elif dialog.file_a_path is not None:
            self.start_comparison(dialog.file_a_path, dialog.candidate_paths)

    def start_comparison(self, file_a_path: Path, candidate_paths: list[Path]) -> None:
        """Start processing a complete one-to-many selection."""
        if not candidate_paths:
            return
        self._reset_to_initial_screen()
        self._begin_comparison(file_a_path, candidate_paths)

    def start_archive_comparison(self, archive_path: Path) -> None:
        """Extract and classify a complete one-to-many ZIP selection."""
        self._reset_to_initial_screen()
        self._archive_temp_directory = TemporaryDirectory(
            prefix="nist-fingerprint-comparator-",
            ignore_cleanup_errors=True,
        )
        self.queue_label.setText(f"Preparing comparison archive: {archive_path.name}")
        self._show_loading(f"Extracting comparison archive: {archive_path.name}")
        self._start_archive_processing(
            archive_path,
            Path(self._archive_temp_directory.name),
        )

    def _begin_comparison(self, file_a_path: Path, candidate_paths: list[Path]) -> None:
        self._file_a = None
        self._file_b = None
        self._review_queue = ReviewQueue()
        self._pending_candidate_paths = list(dict.fromkeys(candidate_paths))
        self._first_pair_ready = False
        self._candidate_ready = False
        self._start_candidate_after_thread = False
        self._set_decision_buttons_enabled(False)
        self.comparison_grid.show_empty()
        self._clear_file_sidebar(self.file_a_widgets)
        self._clear_file_sidebar(self.file_b_widgets)
        self.queue_label.setText(
            f"Preparing 1 reference against {len(self._pending_candidate_paths)} candidate(s)"
        )
        self.results_label.setText(self._history_summary())
        self._show_loading(f"Loading reference File A: {file_a_path.name}")
        self._start_processing(file_a_path, "a")

    def _start_archive_processing(self, archive_path: Path, destination: Path) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self._processing_target = "archive"
        self.new_comparison_action.setEnabled(False)
        self._set_decision_buttons_enabled(False)

        self._thread = QThread(self)
        self._worker = ArchiveWorker(archive_path, destination)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._loading_progress_changed)
        self._worker.finished.connect(self._archive_processing_finished)
        self._worker.failed.connect(self._processing_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        self._thread.start()

    def _start_processing(self, path: Path, target: str) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self._processing_target = target
        self._candidate_ready = False
        self.new_comparison_action.setEnabled(False)
        self._set_decision_buttons_enabled(False)
        source_label = "reference File A" if target == "a" else "File B candidate"
        self._show_loading(f"Loading {source_label}: {path.name}")

        self._thread = QThread(self)
        self._worker = ParseWorker(path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._loading_progress_changed)
        self._worker.finished.connect(self._processing_finished)
        self._worker.failed.connect(self._processing_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        self._thread.start()

    def _archive_processing_finished(self, selection: ArchiveComparisonSelection) -> None:
        self._archive_selection_after_thread = selection

    def _processing_finished(self, transaction: NistTransaction) -> None:
        target = self._processing_target or "a"
        if target == "a":
            self._file_a = transaction
            self._file_b = None
            widgets = self.file_a_widgets
            self._clear_file_sidebar(self.file_b_widgets)
            self.results_label.setText(self._history_summary())
            self._review_queue.start(
                transaction,
                self._pending_candidate_paths,
            )
            self._update_file_sidebar(widgets, transaction)
            self._start_candidate_after_thread = True
            return
        else:
            self._file_b = transaction
            widgets = self.file_b_widgets
        self._update_file_sidebar(widgets, transaction)
        session = self._refresh_comparison()
        total_warnings = sum(
            len(item.warnings) for item in (self._file_a, self._file_b) if item is not None
        ) + len(session.warnings)
        if target == "b" and self._review_queue.current_path is not None:
            self._candidate_ready = True
            self._first_pair_ready = True
            self._update_queue_labels()
            self.page_stack.setCurrentWidget(self.workspace_page)
            self.reset_zoom_action.setEnabled(True)
            self.metadata_action.setEnabled(True)
            self.statusBar().showMessage(
                f"Candidate ready for decision; {total_warnings} parser/comparison warning(s)"
            )

    def _refresh_comparison(self):
        session = build_cross_file_comparison(
            self._file_a.biometric_images if self._file_a else [],
            self._file_b.biometric_images if self._file_b else [],
        )
        session.file_a = self._file_a
        session.file_b = self._file_b
        if (
            self._file_a is not None
            and self._file_b is not None
            and files_have_same_content(self._file_a.source_path, self._file_b.source_path)
        ):
            session.warnings.insert(
                0,
                "Warning: File A and File B are the same file. Select PASS to ignore this "
                "comparison; PASS is not saved to decision history.",
            )
        self.comparison_grid.set_session(session)
        self.comparison_grid.set_metadata_visible(self.metadata_action.isChecked())
        return session

    @staticmethod
    def _update_file_sidebar(widgets: dict[str, QWidget], transaction: NistTransaction) -> None:
        file_label = widgets["file"]
        summary_label = widgets["summary"]
        metadata = widgets["metadata"]
        warnings = widgets["warnings"]
        assert isinstance(file_label, QLabel)
        assert isinstance(summary_label, QLabel)
        assert isinstance(metadata, MetadataPanel)
        assert isinstance(warnings, QPlainTextEdit)
        file_label.setText(transaction.source_path.name)
        summary_label.setText(
            f"Records: {len(transaction.records)}\n"
            f"Biometric images: {len(transaction.biometric_images)}\n"
            f"Warnings: {len(transaction.warnings)}"
        )
        rows = [
            ("Version", transaction.version),
            ("Transaction type", transaction.transaction_type),
            *sorted(transaction.transaction_metadata.items()),
        ]
        metadata.set_rows(rows)
        warnings.setPlainText("\n".join(transaction.warnings))

    def _processing_failed(self, message: str) -> None:
        target = self._processing_target
        self._set_decision_buttons_enabled(False)
        self.statusBar().showMessage("Processing failed")
        title = (
            "Unable to prepare comparison archive"
            if target == "archive"
            else "Unable to open transaction"
        )
        QMessageBox.critical(self, title, message)
        if self._first_pair_ready and target != "archive":
            self.page_stack.setCurrentWidget(self.workspace_page)
        else:
            self._reset_to_initial_screen()
            self.statusBar().showMessage("Processing failed")

    def _thread_finished(self) -> None:
        self.new_comparison_action.setEnabled(True)
        if self._candidate_ready:
            self._set_decision_buttons_enabled(True)
        self._thread = None
        self._worker = None
        self._processing_target = None
        archive_selection = self._archive_selection_after_thread
        self._archive_selection_after_thread = None
        if archive_selection is not None:
            self._begin_comparison(
                archive_selection.file_a_path,
                archive_selection.candidate_paths,
            )
            return
        if self._start_candidate_after_thread:
            self._start_candidate_after_thread = False
            self._start_current_candidate()

    def _start_current_candidate(self) -> None:
        path = self._review_queue.current_path
        if path is None:
            self._finish_review()
            return
        self._file_b = None
        self._clear_file_sidebar(self.file_b_widgets)
        self._update_queue_labels()
        self._show_loading(
            f"Loading candidate {self._review_queue.candidate_number} of "
            f"{self._review_queue.candidate_total}: {path.name}"
        )
        self._start_processing(path, "b")

    def _record_decision(self, decision: ReviewDecisionValue) -> None:
        if self._file_b is None:
            return
        record = None
        try:
            record = self._review_queue.record(decision, self._file_b)
            if decision != "PASS":
                self._history_store.append(record)
        except (OSError, ValueError, sqlite3.Error) as exc:
            if record is not None:
                self._review_queue.rollback_last()
            QMessageBox.critical(self, "Could not record decision", str(exc))
            return
        self._candidate_ready = False
        self._set_decision_buttons_enabled(False)
        self._start_current_candidate()

    def _go_to_previous_comparison(self) -> None:
        if not self._review_queue.decisions or not self._candidate_ready:
            return
        response = QMessageBox.warning(
            self,
            "Return to previous comparison?",
            "The previous comparison result will be undone. That comparison will then "
            "start again.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        previous_decision = self._review_queue.decisions[-1]
        try:
            if previous_decision.history_id is not None:
                self._history_store.delete(previous_decision)
        except (OSError, ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "Could not erase previous decision", str(exc))
            return
        self._review_queue.rollback_last()
        self.results_label.setText(self._history_summary())
        self._candidate_ready = False
        self._set_decision_buttons_enabled(False)
        self._start_current_candidate()

    def _end_current_session(self) -> None:
        if not self._candidate_ready:
            return
        response = QMessageBox.question(
            self,
            "End current session?",
            "Completed decisions will remain in decision history. The current comparison "
            "and all remaining candidates will not be reviewed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        decisions = list(self._review_queue.decisions)
        decision_count = sum(decision.history_id is not None for decision in decisions)
        exported_path = self._offer_session_export(decisions)
        self._reset_to_initial_screen()
        message = f"Session ended; {decision_count} completed decision(s) kept in internal history"
        if exported_path is not None:
            message += f"; session XLSX exported to {exported_path}"
        self.statusBar().showMessage(message)

    def _finish_review(self) -> None:
        decisions = list(self._review_queue.decisions)
        decision_count = sum(decision.history_id is not None for decision in decisions)
        exported_path = self._offer_session_export(decisions)
        self._reset_to_initial_screen()
        message = f"Review complete; {decision_count} decision(s) saved to internal history"
        if exported_path is not None:
            message += f"; session XLSX exported to {exported_path}"
        self.statusBar().showMessage(message)

    def _offer_session_export(self, decisions: list[ReviewDecision]) -> Path | None:
        decisions = [decision for decision in decisions if decision.history_id is not None]
        if not decisions:
            return None
        output_path = self._settings.default_session_export_path()
        response = QMessageBox.question(
            self,
            "Export completed session?",
            f"Create an XLSX workbook containing the {len(decisions)} decision(s) from "
            f"this session in the default output folder?\n\n{output_path.parent}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if response != QMessageBox.StandardButton.Yes:
            return None
        if output_path.exists():
            output_path = self._resolve_existing_session_export(output_path)
            if output_path is None:
                return None
        rows = [decision_record(decision) for decision in decisions]
        try:
            self._xlsx_exporter.export(output_path, rows)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not export completed session", str(exc))
            return None
        self._open_export_folder(output_path.parent)
        return output_path

    def _resolve_existing_session_export(self, output_path: Path) -> Path | None:
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Warning)
        message.setWindowTitle("Session export already exists")
        message.setText(f"An XLSX workbook already exists at:\n\n{output_path}")
        message.setInformativeText(
            "Overwrite it, or create a new workbook with an alternative numbered name?"
        )
        overwrite_button = message.addButton("Overwrite", QMessageBox.ButtonRole.AcceptRole)
        alternative_button = message.addButton(
            "Create New Name",
            QMessageBox.ButtonRole.ActionRole,
        )
        message.addButton(QMessageBox.StandardButton.Cancel)
        message.exec()
        if message.clickedButton() is overwrite_button:
            return output_path
        if message.clickedButton() is alternative_button:
            return available_export_path(output_path)
        return None

    def _open_export_folder(self, folder: Path) -> None:
        try:
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Could not open export folder",
                f"The XLSX workbook was created, but the output folder could not be opened: {exc}",
            )
            return
        if not opened:
            QMessageBox.warning(
                self,
                "Could not open export folder",
                "The XLSX workbook was created, but the system file browser could not open "
                f"the output folder:\n\n{folder}",
            )

    def _reset_to_initial_screen(self) -> None:
        """Clear the completed session and return to the initial setup screen."""
        self._set_decision_buttons_enabled(False)
        self._file_a = None
        self._file_b = None
        self._review_queue = ReviewQueue()
        self._pending_candidate_paths.clear()
        self._archive_selection_after_thread = None
        self._first_pair_ready = False
        self._candidate_ready = False
        self._start_candidate_after_thread = False
        self.comparison_grid.show_empty()
        self._clear_file_sidebar(self.file_a_widgets)
        self._clear_file_sidebar(self.file_b_widgets)
        self.queue_label.setText("No B candidates selected")
        self.results_label.setText(self._history_summary())
        self.review_progress_label.setText(
            "Review decisions become available when a complete comparison pair is ready."
        )
        self.reset_zoom_action.setEnabled(False)
        self.metadata_action.setEnabled(False)
        self.page_stack.setCurrentWidget(self.setup_page)
        self._cleanup_archive_temp()

    def _cleanup_archive_temp(self) -> None:
        if self._archive_temp_directory is None:
            return
        temporary_directory = self._archive_temp_directory
        self._archive_temp_directory = None
        temporary_directory.cleanup()

    def _update_queue_labels(self) -> None:
        total = self._review_queue.candidate_total
        current = self._review_queue.current_path
        if self._review_queue.is_complete:
            self.queue_label.setText(
                f"Complete: {len(self._review_queue.decisions)} of {total} candidate(s) reviewed"
            )
            return
        if current is None:
            self.queue_label.setText("No B candidates selected")
            return
        position = self._review_queue.candidate_number
        self.queue_label.setText(f"Candidate {position} of {total}: {current.name}")
        self.review_progress_label.setText(
            f"Comparing File A with candidate {position} of {total}: {current.name}"
        )

    def _set_decision_buttons_enabled(self, enabled: bool) -> None:
        self.match_button.setEnabled(enabled)
        self.no_match_button.setEnabled(enabled)
        self.pass_button.setEnabled(enabled)
        self.end_session_button.setEnabled(enabled)
        self.end_session_action.setEnabled(enabled)
        previous_enabled = enabled and bool(self._review_queue.decisions)
        self.previous_button.setEnabled(previous_enabled)
        self.previous_comparison_action.setEnabled(previous_enabled)

    @staticmethod
    def _clear_file_sidebar(widgets: dict[str, QWidget]) -> None:
        file_label = widgets["file"]
        summary_label = widgets["summary"]
        metadata = widgets["metadata"]
        warnings = widgets["warnings"]
        assert isinstance(file_label, QLabel)
        assert isinstance(summary_label, QLabel)
        assert isinstance(metadata, MetadataPanel)
        assert isinstance(warnings, QPlainTextEdit)
        file_label.setText("Not loaded")
        summary_label.setText("Records: 0\nBiometric images: 0\nWarnings: 0")
        metadata.set_rows([])
        warnings.clear()

    def _show_loading(self, message: str) -> None:
        self.loading_message.setText(message)
        self.page_stack.setCurrentWidget(self.loading_page)
        self.statusBar().showMessage(message)

    def _loading_progress_changed(self, message: str) -> None:
        self.loading_message.setText(message)
        self.statusBar().showMessage(message)

    def _reset_zoom(self) -> None:
        self.comparison_grid.reset_zoom()

    def _toggle_metadata(self, visible: bool) -> None:
        self.comparison_grid.set_metadata_visible(visible)

    def _export_history(self) -> None:
        dialog = ExportHistoryDialog(self)
        if not dialog.exec():
            return
        start_utc, end_utc = dialog.selected_range_utc()
        rows = self._history_store.query(start_utc, end_utc)
        if not rows:
            QMessageBox.information(
                self,
                "No decisions to export",
                "No decision-history records match the selected time range.",
            )
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export Decision History",
            str(self._settings.default_export_path()),
            "Excel workbooks (*.xlsx)",
        )
        if not selected:
            return
        output_path = Path(selected)
        if output_path.suffix.lower() != ".xlsx":
            output_path = output_path.with_suffix(".xlsx")
        try:
            self._xlsx_exporter.export(output_path, rows)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not export decision history", str(exc))
            return
        self.statusBar().showMessage(f"Decision history exported to {output_path}")

    def _show_history(self) -> None:
        try:
            rows = self._history_store.query()
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "Could not display decision history", str(exc))
            return
        DecisionHistoryDialog(rows, self).exec()

    def _clear_history(self) -> None:
        record_count = self._history_store.count()
        if record_count == 0:
            QMessageBox.information(
                self,
                "Decision history is empty",
                "There are no decision-history records to delete.",
            )
            return
        response = QMessageBox.warning(
            self,
            "Delete all decision history?",
            f"This will permanently delete all {record_count} decision-history record(s). "
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            deleted = self._history_store.clear()
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "Could not delete decision history", str(exc))
            return
        for decision in self._review_queue.decisions:
            decision.history_id = None
        self.results_label.setText(self._history_summary())
        self.statusBar().showMessage(f"Deleted {deleted} decision-history record(s)")

    def _history_summary(self) -> str:
        return f"Internal decision history: {self._history_store.count()} record(s)"

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
        self._cleanup_archive_temp()
        super().closeEvent(event)
