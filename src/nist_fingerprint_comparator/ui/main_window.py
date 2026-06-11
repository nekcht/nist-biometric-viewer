"""Main application window."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QSize, Qt, QThread
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsOpacityEffect,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
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

from nist_fingerprint_comparator.core.archive import (
    ArchiveComparisonSelection,
    ArchiveContents,
    build_archive_comparison_selection,
)
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
    decision_record,
)

from .about_dialog import AboutDialog
from .archive_reference_dialog import ArchiveReferenceDialog
from .comparison_grid import ComparisonGrid
from .export_dialog import ExportHistoryDialog
from .history_dialog import DecisionHistoryDialog
from .metadata_panel import MetadataPanel
from .resources import application_icon
from .settings import AppSettings
from .settings_dialog import SettingsDialog
from .setup_dialog import ComparisonSetupDialog, local_source_paths, valid_source_paths
from .worker import ArchiveWorker, ParseWorker


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: AppSettings | None = None,
        history_store: DecisionHistoryStore | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Nist Biometric Viewer")
        self.setWindowIcon(application_icon())
        self.resize(1100, 720)
        self.setAcceptDrops(True)
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
        self._candidate_transactions: dict[Path, NistTransaction] = {}
        self._archive_temp_directory: TemporaryDirectory | None = None
        self._archive_contents_after_thread: ArchiveContents | None = None
        self._first_pair_ready = False
        self._start_candidate_after_thread = False
        self._workspace_loading = False

        self._create_actions()
        self._create_menus()
        self._create_content()
        self.statusBar().showMessage("Ready")

    def _create_actions(self) -> None:
        self.new_comparison_action = self._create_action(
            "New Comparison...",
            QStyle.StandardPixmap.SP_FileDialogNewFolder,
            "Select comparison records",
            self.new_comparison,
            shortcut="Ctrl+N",
        )

        self.view_history_action = self._create_action(
            "Open History...",
            QStyle.StandardPixmap.SP_FileDialogContentsView,
            "Open history",
            self._show_history,
        )

        self.previous_comparison_action = self._create_action(
            "Previous Comparison",
            QStyle.StandardPixmap.SP_ArrowBack,
            "Review previous comparison",
            self._go_to_previous_comparison,
        )
        self.previous_comparison_action.setEnabled(False)

        self.end_session_action = self._create_action(
            "End Session",
            QStyle.StandardPixmap.SP_DialogCloseButton,
            "End session",
            self._end_current_session,
        )
        self.end_session_action.setEnabled(False)

        self.reset_zoom_action = self._create_action(
            "Fit Images",
            QStyle.StandardPixmap.SP_BrowserReload,
            "Fit images to view",
            self._reset_zoom,
            shortcut="Ctrl+0",
        )

        self.metadata_action = self._create_action(
            "Show Metadata",
            QStyle.StandardPixmap.SP_FileDialogInfoView,
            "Show metadata",
            self._toggle_metadata,
            checkable=True,
            checked=True,
        )

        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.triggered.connect(self.close)

        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self._show_about)

        self.settings_action = QAction("Settings...", self)
        self.settings_action.triggered.connect(self._show_settings)

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

    def _create_menus(self) -> None:
        self.file_menu = self.menuBar().addMenu("&File")
        self.file_menu.addAction(self.new_comparison_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.view_history_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.end_session_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.settings_action)
        self.file_menu.addAction(self.exit_action)

        self.edit_menu = self.menuBar().addMenu("&Edit")
        self.edit_menu.addAction(self.previous_comparison_action)
        self.edit_menu.addSeparator()
        self.edit_menu.addAction(self.reset_zoom_action)

        self.view_menu = self.menuBar().addMenu("&View")
        self.view_menu.addAction(self.metadata_action)

        self.help_menu = self.menuBar().addMenu("&Help")
        self.help_menu.addAction(self.about_action)

    def _create_content(self) -> None:
        self.page_stack = QStackedWidget()
        self.setup_page = self._build_setup_page()
        self.loading_page = self._build_loading_page()
        self.workspace_page = self._build_workspace_page()
        self.page_stack.addWidget(self.setup_page)
        self.page_stack.addWidget(self.loading_page)
        self.page_stack.addWidget(self.workspace_page)
        self._workspace_loading_effect = QGraphicsOpacityEffect(self.workspace_page)
        self._workspace_loading_effect.setOpacity(0.45)
        self._workspace_loading_effect.setEnabled(False)
        self.workspace_page.setGraphicsEffect(self._workspace_loading_effect)
        self.setCentralWidget(self.page_stack)
        self.page_stack.setCurrentWidget(self.setup_page)
        self._set_decision_buttons_enabled(False)
        self.reset_zoom_action.setEnabled(False)
        self.metadata_action.setEnabled(False)

    def _build_setup_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("setupPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(80, 80, 80, 80)
        layout.addStretch(1)
        title = QLabel("New fingerprint comparison")
        title.setObjectName("setupTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = QLabel("Add at least two ANSI/NIST records, or one ZIP/RAR archive.")
        text.setObjectName("setupText")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setWordWrap(True)
        self.add_comparison_button = QToolButton()
        self.add_comparison_button.setObjectName("addComparisonButton")
        self.add_comparison_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder)
        )
        self.add_comparison_button.setIconSize(QSize(48, 48))
        self.add_comparison_button.setFixedSize(76, 76)
        self.add_comparison_button.setToolTip(
            "Select comparison records"
        )
        self.add_comparison_button.setAccessibleName("Add comparison sources")
        self.add_comparison_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_comparison_button.clicked.connect(self.new_comparison)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.add_comparison_button)
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
        title = QLabel("Preparing comparison")
        title.setObjectName("loadingTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_message = QLabel("Loading...")
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
        splitter.addWidget(self._build_fingerprint_workspace())
        splitter.setSizes([330, 1110])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        workspace = QWidget()
        workspace.setObjectName("workspacePage")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_status_navigation_bar())
        layout.addWidget(splitter, 1)
        return workspace

    def _build_status_navigation_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("statusNavigationBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 6)
        self.previous_button = QToolButton()
        self.previous_button.setDefaultAction(self.previous_comparison_action)
        self.previous_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.previous_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.review_progress_label = QLabel("No comparison selected")
        self.review_progress_label.setObjectName("reviewProgress")
        self.review_progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.end_session_button = QToolButton()
        self.end_session_button.setDefaultAction(self.end_session_action)
        self.end_session_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.end_session_button.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.previous_button)
        layout.addWidget(self.review_progress_label, 1)
        layout.addWidget(self.end_session_button)
        self.status_navigation_bar = bar
        return bar

    def _build_fingerprint_workspace(self) -> QWidget:
        workspace = QWidget()
        workspace.setObjectName("fingerprintWorkspace")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.comparison_grid = ComparisonGrid()
        layout.addWidget(self.comparison_grid, 1)
        layout.addWidget(self._build_decision_bar())
        self.fingerprint_workspace = workspace
        return workspace

    def _build_decision_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("bottomDecisionBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 6)
        self.match_button = QPushButton("MATCH")
        self.match_button.setObjectName("matchButton")
        self.match_button.setCheckable(True)
        self.match_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.match_button.clicked.connect(lambda: self._record_decision("MATCH"))
        self.no_match_button = QPushButton("NO MATCH")
        self.no_match_button.setObjectName("noMatchButton")
        self.no_match_button.setCheckable(True)
        self.no_match_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.no_match_button.clicked.connect(lambda: self._record_decision("NO_MATCH"))
        self.pass_button = QPushButton("PASS")
        self.pass_button.setObjectName("passButton")
        self.pass_button.setCheckable(True)
        self.pass_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pass_button.clicked.connect(lambda: self._record_decision("PASS"))
        layout.addStretch(1)
        layout.addWidget(self.pass_button)
        layout.addWidget(self.no_match_button)
        layout.addWidget(self.match_button)
        self.bottom_decision_bar = bar
        return bar

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        sidebar_layout.setSpacing(8)

        navigation_group = QGroupBox("Comparison Pairs")
        navigation_layout = QVBoxLayout(navigation_group)
        self.pair_navigation_list = QListWidget()
        self.pair_navigation_list.setObjectName("pairNavigationList")
        self.pair_navigation_list.setMinimumHeight(150)
        self.pair_navigation_list.currentRowChanged.connect(self._navigate_to_pair)
        navigation_layout.addWidget(self.pair_navigation_list)
        sidebar_layout.addWidget(navigation_group)

        sidebar_content = QWidget()
        layout = QVBoxLayout(sidebar_content)
        layout.setContentsMargins(0, 0, 0, 0)

        file_a_group, self.file_a_widgets = self._build_file_sidebar_group("Reference Record")
        file_b_group, self.file_b_widgets = self._build_file_sidebar_group(
            "Comparison Record"
        )
        layout.addWidget(file_a_group)
        layout.addWidget(file_b_group)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(sidebar_content)
        sidebar_layout.addWidget(scroll, 1)
        sidebar.setMinimumWidth(300)
        return sidebar

    def _build_file_sidebar_group(self, title: str) -> tuple[QGroupBox, dict[str, QWidget]]:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        file_label = QLabel("Not loaded")
        file_label.setWordWrap(True)
        summary_label = QLabel("Records: 0\nBiometric images: 0\nWarnings: 0")
        metadata = MetadataPanel()
        metadata.setMaximumHeight(190)
        metadata.hide()
        details_group = QGroupBox("Record Details")
        details_group.setCheckable(True)
        details_group.setChecked(False)
        details_layout = QVBoxLayout(details_group)
        details_layout.setContentsMargins(6, 8, 6, 6)
        details_layout.addWidget(metadata)
        details_group.toggled.connect(metadata.setVisible)
        warnings = QPlainTextEdit()
        warnings.setReadOnly(True)
        warnings.setMaximumHeight(110)
        warnings.setPlaceholderText("No warnings")
        layout.addWidget(file_label)
        layout.addWidget(summary_label)
        layout.addWidget(details_group)
        layout.addWidget(warnings)
        return group, {
            "file": file_label,
            "summary": summary_label,
            "metadata": metadata,
            "details": details_group,
            "warnings": warnings,
        }

    def new_comparison(self) -> None:
        self._open_comparison_setup()

    def _open_comparison_setup(self, initial_paths: list[Path] | None = None) -> None:
        initial_directory = self._file_a.source_path.parent if self._file_a else Path.home()
        dialog = ComparisonSetupDialog(initial_directory, self, initial_paths)
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
        """Extract a complete one-to-many archive selection for user classification."""
        self._reset_to_initial_screen()
        self._archive_temp_directory = TemporaryDirectory(
            prefix="nist-biometric-viewer-",
            ignore_cleanup_errors=True,
        )
        self.review_progress_label.setText(f"Preparing archive: {archive_path.name}")
        self._show_loading(f"Extracting archive: {archive_path.name}")
        self._start_archive_processing(
            archive_path,
            Path(self._archive_temp_directory.name),
        )

    def _begin_comparison(self, file_a_path: Path, candidate_paths: list[Path]) -> None:
        self._file_a = None
        self._file_b = None
        self._review_queue = ReviewQueue()
        self._pending_candidate_paths = list(dict.fromkeys(candidate_paths))
        self._candidate_transactions.clear()
        self._first_pair_ready = False
        self._candidate_ready = False
        self._start_candidate_after_thread = False
        self._set_decision_buttons_enabled(False)
        self.comparison_grid.show_empty()
        self._clear_file_sidebar(self.file_a_widgets)
        self._clear_file_sidebar(self.file_b_widgets)
        self.review_progress_label.setText(
            f"Comparison Records: {len(self._pending_candidate_paths)}"
        )
        self._show_loading(f"Loading Reference Record: {file_a_path.name}")
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
        source_label = "Reference Record" if target == "a" else "Comparison Record"
        self._show_loading(
            f"Loading {source_label}: {path.name}",
            preserve_workspace=target == "b" and self._first_pair_ready,
        )

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

    def _archive_processing_finished(self, contents: ArchiveContents) -> None:
        self._archive_contents_after_thread = contents

    def _processing_finished(self, transaction: NistTransaction) -> None:
        target = self._processing_target or "a"
        if target == "a":
            self._file_a = transaction
            self._file_b = None
            widgets = self.file_a_widgets
            self._clear_file_sidebar(self.file_b_widgets)
            self._review_queue.start(
                transaction,
                self._pending_candidate_paths,
            )
            self._populate_pair_navigation()
            self._update_file_sidebar(widgets, transaction)
            self._start_candidate_after_thread = True
            return
        current_path = self._review_queue.current_path
        if current_path is not None:
            self._candidate_transactions[current_path] = transaction
        self._activate_candidate(transaction)

    def _activate_candidate(self, transaction: NistTransaction) -> None:
        self._file_b = transaction
        self._update_file_sidebar(self.file_b_widgets, transaction)
        session = self._refresh_comparison()
        total_warnings = sum(
            len(item.warnings) for item in (self._file_a, self._file_b) if item is not None
        ) + len(session.warnings)
        if self._review_queue.current_path is None:
            return
        first_pair_ready = not self._first_pair_ready
        self._candidate_ready = True
        self._first_pair_ready = True
        self._set_workspace_loading(False)
        self._update_review_status()
        self._update_pair_navigation()
        if self._thread is None or not self._thread.isRunning():
            self._set_decision_buttons_enabled(True)
        self.page_stack.setCurrentWidget(self.workspace_page)
        if first_pair_ready:
            self.showMaximized()
        self.reset_zoom_action.setEnabled(True)
        self.metadata_action.setEnabled(True)
        self.statusBar().showMessage(f"Comparison ready | Warnings: {total_warnings}")

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
                "Reference Record and Comparison Record are identical. "
                "Use PASS to skip without saving.",
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
        self._set_workspace_loading(False)
        self._set_decision_buttons_enabled(False)
        self.statusBar().showMessage("Processing failed")
        title = (
            "Archive unavailable"
            if target == "archive"
            else "Record unavailable"
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
        archive_contents = self._archive_contents_after_thread
        self._archive_contents_after_thread = None
        if archive_contents is not None:
            archive_selection = self._select_archive_reference(archive_contents)
            if archive_selection is None:
                self._reset_to_initial_screen()
                self.statusBar().showMessage("Comparison cancelled")
                return
            self._begin_comparison(
                archive_selection.file_a_path,
                archive_selection.candidate_paths,
            )
            return
        if self._start_candidate_after_thread:
            self._start_candidate_after_thread = False
            self._start_current_candidate()

    def _select_archive_reference(
        self,
        contents: ArchiveContents,
    ) -> ArchiveComparisonSelection | None:
        dialog = ArchiveReferenceDialog(contents.nist_paths, self)
        if not dialog.exec() or dialog.reference_path is None:
            return None
        return build_archive_comparison_selection(contents, dialog.reference_path)

    def _start_current_candidate(self) -> None:
        path = self._review_queue.current_path
        if path is None:
            return
        self._candidate_ready = False
        self._set_decision_buttons_enabled(False)
        self._file_b = None
        self._clear_file_sidebar(self.file_b_widgets)
        self._update_review_status()
        self._update_pair_navigation()
        cached = self._candidate_transactions.get(path)
        if cached is not None:
            self._activate_candidate(cached)
            return
        self._show_loading(
            f"Loading Comparison Record {self._review_queue.candidate_number} of "
            f"{self._review_queue.candidate_total}: {path.name}",
            preserve_workspace=self._first_pair_ready,
        )
        self._start_processing(path, "b")

    def _record_decision(self, decision: ReviewDecisionValue) -> None:
        if self._file_b is None:
            return
        candidate_index = self._review_queue.current_index
        previous = self._review_queue.decision_for_index(candidate_index)
        if previous is not None and previous.decision == decision:
            self._update_decision_highlight()
            return
        was_complete = self._review_queue.is_complete
        record = None
        try:
            record, previous = self._review_queue.set_decision(decision, self._file_b)
            (
                record.timestamp_utc,
                record.timestamp,
                record.timezone,
            ) = self._settings.history_timestamp_values()
            self._history_store.replace(previous, record)
        except (OSError, ValueError, sqlite3.Error) as exc:
            if record is not None:
                self._review_queue.restore_decision(candidate_index, previous)
            QMessageBox.critical(self, "Decision not saved", str(exc))
            self._update_decision_highlight()
            return
        self._update_pair_navigation()
        self._update_review_status()
        self._update_decision_highlight()
        if self._review_queue.is_complete and not was_complete:
            self._confirm_completed_session()
            return
        if previous is not None:
            self.statusBar().showMessage(f"Decision updated: {decision}")
            return
        next_index = self._review_queue.next_undecided_index(candidate_index)
        if next_index is not None:
            self._select_pair(next_index)

    def _go_to_previous_comparison(self) -> None:
        if not self._candidate_ready or self._review_queue.current_index <= 0:
            return
        self._select_pair(self._review_queue.current_index - 1)

    def _confirm_completed_session(self) -> None:
        response = QMessageBox.question(
            self,
            "Review complete",
            "All comparison pairs have a decision. End the session now? "
            "Select No to stay and review your decisions.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response == QMessageBox.StandardButton.Yes:
            self._finish_review()
            return
        self.statusBar().showMessage("All comparison pairs decided | Session remains open")

    def _end_current_session(self) -> None:
        if not self._candidate_ready:
            return
        response = QMessageBox.question(
            self,
            "End session",
            "End the current session? Completed decisions remain in History.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        decision_count = sum(
            decision.history_id is not None for decision in self._review_queue.decisions
        )
        completed_decisions = self._completed_session_decisions()
        self._reset_to_initial_screen()
        self.statusBar().showMessage(f"Session ended | Decisions saved: {decision_count}")
        self._offer_session_export(completed_decisions)

    def _finish_review(self) -> None:
        decision_count = sum(
            decision.history_id is not None for decision in self._review_queue.decisions
        )
        completed_decisions = self._completed_session_decisions()
        self._reset_to_initial_screen()
        self.statusBar().showMessage(f"Review complete | Decisions saved: {decision_count}")
        self._offer_session_export(completed_decisions)

    def _completed_session_decisions(self) -> list[ReviewDecision]:
        return [
            decision
            for decision in self._review_queue.decisions
            if decision.history_id is not None
        ]

    def _offer_session_export(self, decisions: list[ReviewDecision]) -> Path | None:
        if not decisions or not self._settings.offer_session_export():
            return None
        response = QMessageBox.question(
            self,
            "Export session results",
            "Export completed results to XLSX?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if response != QMessageBox.StandardButton.Yes:
            return None
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export Session Results",
            str(self._settings.default_session_export_path()),
            "Excel workbooks (*.xlsx)",
        )
        if not selected:
            return None
        output_path = Path(selected)
        if output_path.suffix.lower() != ".xlsx":
            output_path = output_path.with_suffix(".xlsx")
        try:
            self._xlsx_exporter.export(
                output_path,
                [decision_record(decision) for decision in decisions],
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return None
        self.statusBar().showMessage(f"Export complete: {output_path}")
        return output_path

    def _reset_to_initial_screen(self) -> None:
        """Clear the completed session and return to the initial setup screen."""
        self._set_workspace_loading(False)
        self._set_decision_buttons_enabled(False)
        self._file_a = None
        self._file_b = None
        self._review_queue = ReviewQueue()
        self._pending_candidate_paths.clear()
        self._candidate_transactions.clear()
        self._archive_contents_after_thread = None
        self._first_pair_ready = False
        self._candidate_ready = False
        self._start_candidate_after_thread = False
        self.comparison_grid.show_empty()
        self.pair_navigation_list.clear()
        self._clear_file_sidebar(self.file_a_widgets)
        self._clear_file_sidebar(self.file_b_widgets)
        self.review_progress_label.setText("No comparison selected")
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

    def _update_review_status(self) -> None:
        total = self._review_queue.candidate_total
        current = self._review_queue.current_path
        if current is None:
            self.review_progress_label.setText("No comparison selected")
            return
        position = self._review_queue.candidate_number
        decision = self._review_queue.decision_for_index(
            self._review_queue.current_index
        )
        decision_text = (
            f" | Decision: {decision.decision.replace('_', ' ')}"
            if decision is not None
            else ""
        )
        self.review_progress_label.setText(
            f"Comparison {position} of {total}: {current.name}{decision_text}"
        )

    def _set_decision_buttons_enabled(self, enabled: bool) -> None:
        self.match_button.setEnabled(enabled)
        self.no_match_button.setEnabled(enabled)
        self.pass_button.setEnabled(enabled)
        self.end_session_button.setEnabled(enabled)
        self.end_session_action.setEnabled(enabled)
        self.pair_navigation_list.setEnabled(enabled)
        previous_enabled = enabled and self._review_queue.current_index > 0
        self.previous_button.setEnabled(previous_enabled)
        self.previous_comparison_action.setEnabled(previous_enabled)
        self._update_decision_highlight()

    def _populate_pair_navigation(self) -> None:
        self.pair_navigation_list.blockSignals(True)
        self.pair_navigation_list.clear()
        for path in self._review_queue.candidate_paths:
            self.pair_navigation_list.addItem(path.name)
        self.pair_navigation_list.blockSignals(False)
        self._update_pair_navigation()

    def _update_pair_navigation(self) -> None:
        self.pair_navigation_list.blockSignals(True)
        for index, path in enumerate(self._review_queue.candidate_paths):
            item = self.pair_navigation_list.item(index)
            if item is None:
                continue
            decision = self._review_queue.decision_for_index(index)
            status = (
                decision.decision.replace("_", " ")
                if decision is not None
                else "Not decided"
            )
            item.setText(f"{index + 1}. {path.name}\n{status}")
            item.setToolTip(str(path))
        current_index = self._review_queue.current_index
        if 0 <= current_index < self.pair_navigation_list.count():
            self.pair_navigation_list.setCurrentRow(current_index)
        self.pair_navigation_list.blockSignals(False)
        self._update_decision_highlight()

    def _update_decision_highlight(self) -> None:
        decision = self._review_queue.decision_for_index(
            self._review_queue.current_index
        )
        selected = decision.decision if decision is not None else None
        self.match_button.setChecked(selected == "MATCH")
        self.no_match_button.setChecked(selected == "NO_MATCH")
        self.pass_button.setChecked(selected == "PASS")

    def _navigate_to_pair(self, index: int) -> None:
        if (
            not self._candidate_ready
            or index < 0
            or index == self._review_queue.current_index
        ):
            return
        self._select_pair(index)

    def _select_pair(self, index: int) -> None:
        self._review_queue.set_current_index(index)
        self._start_current_candidate()

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

    def _show_loading(self, message: str, *, preserve_workspace: bool = False) -> None:
        self.loading_message.setText(message)
        if preserve_workspace and self._first_pair_ready:
            self.page_stack.setCurrentWidget(self.workspace_page)
            self._set_workspace_loading(True, message)
        else:
            self._set_workspace_loading(False)
            self.page_stack.setCurrentWidget(self.loading_page)
        self.statusBar().showMessage(message)

    def _loading_progress_changed(self, message: str) -> None:
        self.loading_message.setText(message)
        if self._workspace_loading:
            self.review_progress_label.setText(message)
        self.statusBar().showMessage(message)

    def _set_workspace_loading(self, loading: bool, message: str | None = None) -> None:
        self._workspace_loading = loading
        self._workspace_loading_effect.setEnabled(loading)
        self.workspace_page.setEnabled(not loading)
        if loading and message is not None:
            self.review_progress_label.setText(message)

    def _reset_zoom(self) -> None:
        self.comparison_grid.reset_zoom()

    def _toggle_metadata(self, visible: bool) -> None:
        self.comparison_grid.set_metadata_visible(visible)
        self.statusBar().showMessage(
            "Sensitive metadata visible" if visible else "Metadata hidden"
        )

    def _export_history(self) -> None:
        dialog = ExportHistoryDialog(self)
        if not dialog.exec():
            return
        start_utc, end_utc = dialog.selected_range_utc()
        rows = self._history_store.query(start_utc, end_utc)
        if not rows:
            QMessageBox.information(
                self,
                "No history to export",
                "No history matches the selected range.",
            )
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export Comparison History",
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
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.statusBar().showMessage(f"Export complete: {output_path}")

    def _show_history(self) -> None:
        try:
            rows = self._history_store.query()
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "History unavailable", str(exc))
            return
        DecisionHistoryDialog(
            rows,
            clear_history=self._delete_all_history_records,
            delete_record=self._delete_history_record,
            export_history=self._export_history,
            parent=self,
        ).exec()

    def _delete_history_record(self, history_id: int) -> None:
        self._history_store.delete_by_id(history_id)
        for decision in self._review_queue.decisions:
            if decision.history_id == history_id:
                decision.history_id = None
        self.statusBar().showMessage("History record deleted")

    def _delete_all_history_records(self) -> int:
        deleted = self._history_store.clear()
        for decision in self._review_queue.decisions:
            decision.history_id = None
        self.statusBar().showMessage(f"History deleted | Records: {deleted}")
        return deleted

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    def _show_settings(self) -> None:
        dialog = SettingsDialog(
            self._settings.history_timezone_id(),
            self._settings.offer_session_export(),
            self,
        )
        if not dialog.exec():
            return
        try:
            self._settings.set_history_timezone_id(dialog.history_timezone_id)
            self._settings.set_offer_session_export(dialog.offer_session_export)
        except ValueError as exc:
            QMessageBox.critical(self, "Settings not saved", str(exc))
            return
        self.statusBar().showMessage("Settings saved")

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
        self._cleanup_archive_temp()
        super().closeEvent(event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if (
            self.page_stack.currentWidget() is self.setup_page
            and valid_source_paths(local_source_paths(event))
        ):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = local_source_paths(event)
        if self.page_stack.currentWidget() is self.setup_page and valid_source_paths(paths):
            event.acceptProposedAction()
            self._open_comparison_setup(paths)
            return
        event.ignore()
