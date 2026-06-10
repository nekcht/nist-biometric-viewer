"""Main application window."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread
from PySide6.QtGui import QAction
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
    QVBoxLayout,
    QWidget,
)

from nist_fingerprint_comparator.core.models import NistTransaction
from nist_fingerprint_comparator.core.pairing import build_cross_file_comparison
from nist_fingerprint_comparator.core.review import (
    DecisionHistoryStore,
    DecisionXlsxExporter,
    ReviewDecisionValue,
    ReviewQueue,
)

from .comparison_grid import ComparisonGrid
from .export_dialog import ExportHistoryDialog
from .metadata_panel import MetadataPanel
from .settings import AppSettings
from .setup_dialog import ComparisonSetupDialog
from .worker import ParseWorker

ABOUT_TEXT = (
    "<b>NIST Fingerprint Comparator</b><br><br>"
    "A visual-review application for comparing ANSI/NIST biometric transactions. "
    "It does not perform automated biometric matching or identity verification.<br><br>"
    "<b>Developed by</b><br>"
    "Nektarios Christou<br>"
    "Hellenic Police<br>"
    "Office of European Interoperability Applications<br>"
    "European Information Systems Support Department<br>"
    "Directorate of Information Systems &amp; Digital Governance<br>"
    "Hellenic Police Headquarters<br><br>"
    "<b>Email:</b> n.christou@police.gr<br>"
    "<b>Date:</b> 10/06/2026"
)


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: AppSettings | None = None,
        history_store: DecisionHistoryStore | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("NIST Fingerprint Comparator")
        self.resize(1440, 900)
        self._thread: QThread | None = None
        self._worker: ParseWorker | None = None
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
        self._first_pair_ready = False
        self._start_candidate_after_thread = False

        self._create_actions()
        self._create_toolbar()
        self._create_menus()
        self._create_content()
        self.statusBar().showMessage("Ready")

    def _create_actions(self) -> None:
        self.new_comparison_action = QAction("New Comparison...", self)
        self.new_comparison_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        self.new_comparison_action.setShortcut("Ctrl+N")
        self.new_comparison_action.setStatusTip(
            "Select File A and all File B candidates in one setup step"
        )
        self.new_comparison_action.triggered.connect(self.new_comparison)

        self.export_history_action = QAction("Export Decision History...", self)
        self.export_history_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self.export_history_action.setStatusTip(
            "Export all or a UTC time range of internal decision history to XLSX"
        )
        self.export_history_action.triggered.connect(self._export_history)

        self.reset_zoom_action = QAction("Reset Zoom", self)
        self.reset_zoom_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.reset_zoom_action.setShortcut("Ctrl+0")
        self.reset_zoom_action.setStatusTip("Fit every biometric image to its viewer")
        self.reset_zoom_action.triggered.connect(self._reset_zoom)

        self.metadata_action = QAction("Toggle Metadata", self)
        self.metadata_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        )
        self.metadata_action.setCheckable(True)
        self.metadata_action.setChecked(True)
        self.metadata_action.setStatusTip("Show or hide image metadata tables")
        self.metadata_action.toggled.connect(self._toggle_metadata)

        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.triggered.connect(self.close)

        self.about_action = QAction("About NIST Fingerprint Comparator", self)
        self.about_action.triggered.connect(self._show_about)

    def _create_toolbar(self) -> None:
        self.main_toolbar = self.addToolBar("Review Tools")
        self.main_toolbar.setObjectName("reviewToolsToolbar")
        self.main_toolbar.setMovable(False)
        self.main_toolbar.setIconSize(QSize(18, 18))
        self.main_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.main_toolbar.addAction(self.new_comparison_action)
        self.main_toolbar.addSeparator()
        self.main_toolbar.addAction(self.export_history_action)
        self.main_toolbar.addSeparator()
        self.main_toolbar.addAction(self.reset_zoom_action)
        self.main_toolbar.addAction(self.metadata_action)

    def _create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.new_comparison_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_history_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
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
            "Select the reference File A and the complete File B candidate group in one "
            "setup step. The visual comparison workspace opens when the first pair is ready."
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
        layout.addWidget(self.review_progress_label, 1)
        layout.addWidget(self.match_button)
        layout.addWidget(self.no_match_button)
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
        if dialog.exec() and dialog.file_a_path is not None:
            self.start_comparison(dialog.file_a_path, dialog.candidate_paths)

    def start_comparison(self, file_a_path: Path, candidate_paths: list[Path]) -> None:
        """Start processing a complete one-to-many selection."""
        if not candidate_paths:
            return
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
        self._set_decision_buttons_enabled(False)
        self.statusBar().showMessage("Processing failed")
        QMessageBox.critical(self, "Unable to open transaction", message)
        if self._first_pair_ready:
            self.page_stack.setCurrentWidget(self.workspace_page)
        else:
            self.page_stack.setCurrentWidget(self.setup_page)

    def _thread_finished(self) -> None:
        self.new_comparison_action.setEnabled(True)
        if self._candidate_ready:
            self._set_decision_buttons_enabled(True)
        self._thread = None
        self._worker = None
        self._processing_target = None
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
            self._history_store.append(record)
        except (OSError, ValueError, sqlite3.Error) as exc:
            if record is not None:
                self._review_queue.rollback_last()
            QMessageBox.critical(self, "Could not record decision", str(exc))
            return
        self._candidate_ready = False
        self._set_decision_buttons_enabled(False)
        self._start_current_candidate()

    def _finish_review(self) -> None:
        decision_count = len(self._review_queue.decisions)
        self._reset_to_initial_screen()
        self.statusBar().showMessage(
            f"Review complete; {decision_count} decision(s) saved to internal history"
        )

    def _reset_to_initial_screen(self) -> None:
        """Clear the completed session and return to the initial setup screen."""
        self._set_decision_buttons_enabled(False)
        self._file_a = None
        self._file_b = None
        self._review_queue = ReviewQueue()
        self._pending_candidate_paths.clear()
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

    def _history_summary(self) -> str:
        return f"Internal decision history: {self._history_store.count()} record(s)"

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About NIST Fingerprint Comparator",
            ABOUT_TEXT,
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        super().closeEvent(event)
