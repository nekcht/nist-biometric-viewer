"""Main application window."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QSize, Qt, QThread, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsOpacityEffect,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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
from nist_fingerprint_comparator.core.loading import (
    LoadingError,
    loading_error_from_exception,
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
from nist_fingerprint_comparator.user_data import create_archive_temp_directory

from .about_dialog import AboutDialog
from .archive_reference_dialog import ArchiveReferenceDialog
from .comparison_grid import ComparisonGrid
from .export_dialog import ExportHistoryDialog
from .history_dialog import HISTORY_PAGE_SIZE, DecisionHistoryDialog
from .metadata_panel import MetadataPanel
from .resources import application_icon
from .settings import AppSettings
from .settings_dialog import SettingsDialog
from .setup_dialog import ComparisonSetupDialog, local_source_paths, valid_source_paths
from .worker import ArchiveWorker, ParseWorker

LOGGER = logging.getLogger(__name__)


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
        self._history_store = history_store
        self._history_startup_error = False
        if self._history_store is None:
            try:
                self._history_store = DecisionHistoryStore(
                    self._settings.history_database_path()
                )
            except (OSError, sqlite3.Error) as exc:
                self._history_startup_error = True
                LOGGER.error("History initialization failed: %s", type(exc).__name__)
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
        if self._history_startup_error:
            QTimer.singleShot(0, self._warn_history_unavailable)

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
        self.view_history_action.setEnabled(self._history_store is not None)

        self.previous_comparison_action = self._create_action(
            "Previous Comparison",
            QStyle.StandardPixmap.SP_ArrowBack,
            "Review previous comparison",
            self._go_to_previous_comparison,
        )
        self.previous_comparison_action.setEnabled(False)

        self.next_comparison_action = self._create_action(
            "Next Comparison",
            QStyle.StandardPixmap.SP_ArrowForward,
            "Go to the next comparison without a decision",
            self._go_to_next_comparison,
        )
        self.next_comparison_action.setEnabled(False)

        self.end_session_action = self._create_action(
            "End Session",
            QStyle.StandardPixmap.SP_MediaStop,
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
        self.edit_menu.addAction(self.next_comparison_action)
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
        self.review_progress_label.setVisible(False)
        self.review_progress_bar = QProgressBar()
        self.review_progress_bar.setObjectName("reviewProgressBar")
        self.review_progress_bar.setProperty("complete", False)
        self.review_progress_bar.setTextVisible(False)
        self.review_progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.end_session_button = QToolButton()
        self.end_session_button.setDefaultAction(self.end_session_action)
        self.end_session_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.end_session_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_button = QToolButton()
        self.next_button.setDefaultAction(self.next_comparison_action)
        self.next_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.previous_button)
        layout.addWidget(self.review_progress_bar, 1)
        layout.addWidget(self.next_button)
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

        navigation_group = QGroupBox("Navigation Panel")
        navigation_layout = QVBoxLayout(navigation_group)
        self.pair_navigation_list = QListWidget()
        self.pair_navigation_list.setObjectName("pairNavigationList")
        self.pair_navigation_list.setMinimumHeight(150)
        self.pair_navigation_list.setUniformItemSizes(True)
        self.pair_navigation_list.currentRowChanged.connect(self._navigate_to_pair)
        self._pair_navigation_rows: list[tuple[QLabel, QLabel]] = []
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
        try:
            initial_directory = self._file_a.source_path.parent if self._file_a else Path.home()
            dialog = ComparisonSetupDialog(initial_directory, self, initial_paths)
            if not dialog.exec():
                return
            if dialog.archive_path is not None:
                self.start_archive_comparison(dialog.archive_path)
            elif dialog.file_a_path is not None:
                self.start_comparison(dialog.file_a_path, dialog.candidate_paths)
        except Exception as exc:
            self.handle_loading_error(
                loading_error_from_exception(
                    exc,
                    title="Files could not be selected",
                    user_message="The selected sources could not be prepared.",
                    stage="file_selection",
                    source=initial_paths[0] if initial_paths else None,
                )
            )

    def start_comparison(self, file_a_path: Path, candidate_paths: list[Path]) -> None:
        """Start processing a complete one-to-many selection."""
        if not candidate_paths:
            return
        try:
            self._reset_to_initial_screen()
            self._begin_comparison(file_a_path, candidate_paths)
        except Exception as exc:
            self.handle_loading_error(
                loading_error_from_exception(
                    exc,
                    title="Records could not be loaded",
                    user_message="The selected NIST records could not be prepared.",
                    stage="ui_transition",
                    source=file_a_path,
                )
            )

    def start_archive_comparison(self, archive_path: Path) -> None:
        """Extract a complete one-to-many archive selection for user classification."""
        self._reset_to_initial_screen()
        try:
            self._archive_temp_directory = create_archive_temp_directory()
        except OSError as exc:
            self.handle_loading_error(
                loading_error_from_exception(
                    exc,
                    title="Temporary folder unavailable",
                    user_message="A secure temporary folder could not be created.",
                    stage="temp_directory",
                    source=archive_path,
                )
            )
            return
        self.review_progress_label.setText(f"Preparing archive: {archive_path.name}")
        self._show_loading(f"Extracting archive: {archive_path.name}")
        try:
            self._start_archive_processing(
                archive_path,
                Path(self._archive_temp_directory.name) / "contents",
            )
        except Exception as exc:
            self.handle_loading_error(
                loading_error_from_exception(
                    exc,
                    title="Archive could not be opened",
                    user_message="The selected archive could not be prepared.",
                    stage="ui_transition",
                    source=archive_path,
                )
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
        self._worker.finished.connect(self._archive_processing_finished_safely)
        self._worker.failed.connect(self.handle_loading_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread_finished_safely)
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
        self._worker.finished.connect(self._processing_finished_safely)
        self._worker.failed.connect(self.handle_loading_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread_finished_safely)
        self._thread.start()

    def _archive_processing_finished(self, contents: ArchiveContents) -> None:
        self._archive_contents_after_thread = contents

    def _archive_processing_finished_safely(self, contents: ArchiveContents) -> None:
        try:
            self._archive_processing_finished(contents)
        except Exception as exc:
            self.handle_loading_error(
                loading_error_from_exception(
                    exc,
                    title="Archive could not be opened",
                    user_message="The extracted records could not be prepared.",
                    stage="ui_transition",
                )
            )

    def _processing_finished_safely(self, transaction: NistTransaction) -> None:
        try:
            self._processing_finished(transaction)
        except Exception as exc:
            self.handle_loading_error(
                loading_error_from_exception(
                    exc,
                    title="Record could not be loaded",
                    user_message="The selected record could not be displayed.",
                    stage="ui_transition",
                    source=transaction.source_path,
                )
            )

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
            QTimer.singleShot(0, self._fit_comparison_after_workspace_resize)
            QTimer.singleShot(100, self._fit_comparison_after_workspace_resize)
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

    def handle_loading_error(self, error: LoadingError | str) -> None:
        """Recover the application from any fatal loading-pipeline failure."""
        if not isinstance(error, LoadingError):
            error = LoadingError(
                "Loading failed",
                "The selected source could not be loaded.",
                stage="unknown",
                technical_message=error,
            )
        LOGGER.error("Loading failed: %s", error.log_details)
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
            thread.quit()
        self._set_workspace_loading(False)
        self._set_decision_buttons_enabled(False)
        self.new_comparison_action.setEnabled(True)
        try:
            self._reset_to_initial_screen()
        except Exception as cleanup_error:
            LOGGER.warning(
                "Loading recovery cleanup failed: %s",
                type(cleanup_error).__name__,
            )
            self.page_stack.setCurrentWidget(self.setup_page)
        self.statusBar().showMessage("Loading failed | Ready for a new comparison")
        dialog = QMessageBox(
            QMessageBox.Icon.Critical,
            error.title,
            error.user_message,
            parent=self,
        )
        dialog.setDetailedText(error.technical_details)
        try:
            dialog.exec()
        except Exception as dialog_error:
            LOGGER.error(
                "Loading error dialog failed: %s",
                type(dialog_error).__name__,
            )

    def _processing_failed(self, message: str) -> None:
        """Compatibility entry point for older callers and tests."""
        self.handle_loading_error(message)

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

    def _thread_finished_safely(self) -> None:
        try:
            self._thread_finished()
        except Exception as exc:
            self.handle_loading_error(
                loading_error_from_exception(
                    exc,
                    title="Loading failed",
                    user_message="The selected source could not be prepared.",
                    stage="ui_transition",
                )
            )

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
        if self._history_store is None:
            QMessageBox.critical(
                self,
                "Decision not saved",
                "History is unavailable. The decision was not saved.",
            )
            return
        candidate_index = self._review_queue.current_index
        was_complete = self._review_queue.is_complete
        previous = self._review_queue.decision_for_index(candidate_index)
        if previous is not None and previous.decision == decision:
            self._update_decision_highlight()
            return
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
            LOGGER.error("Decision history write failed: %s", type(exc).__name__)
            QMessageBox.critical(
                self,
                "Decision not saved",
                "History is unavailable. The decision was not saved.",
            )
            self._update_decision_highlight()
            return
        self._update_pair_navigation()
        self._update_review_status()
        self._update_decision_highlight()
        if self._review_queue.is_complete:
            if not was_complete and self._settings.auto_end_session():
                self._finish_current_session(automatic=True)
                return
            self.statusBar().showMessage(
                "All comparison pairs decided | Use End Session when review is complete"
            )
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

    def _go_to_next_comparison(self) -> None:
        if not self._candidate_ready:
            return
        next_index = self._review_queue.next_undecided_index(
            self._review_queue.current_index
        )
        if next_index is not None:
            self._select_pair(next_index)

    def _end_current_session(self) -> None:
        if not self._candidate_ready:
            return
        undecided_count = self._review_queue.candidate_total - len(
            self._review_queue.decisions
        )
        if undecided_count:
            pair_word = "pair has" if undecided_count == 1 else "pairs have"
            message = (
                f"{undecided_count} comparison {pair_word} no decision. "
                "End the session anyway? Completed decisions remain in History."
            )
        else:
            message = "End the current session? Completed decisions remain in History."
        response = QMessageBox.question(
            self,
            "End session",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        self._finish_current_session()

    def _finish_current_session(self, *, automatic: bool = False) -> None:
        """End a session after confirmation or configured automatic completion."""
        decision_count = sum(
            decision.history_id is not None for decision in self._review_queue.decisions
        )
        completed_decisions = self._completed_session_decisions()
        self._reset_to_initial_screen()
        self.statusBar().showMessage(f"Session ended | Decisions saved: {decision_count}")
        if automatic:
            QMessageBox.information(
                self,
                "Session completed",
                "All comparison pairs have a decision. The session ended automatically.",
            )
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
        except (OSError, ValueError, RuntimeError) as exc:
            LOGGER.error("Session export failed: %s", type(exc).__name__)
            QMessageBox.critical(
                self,
                "Export failed",
                "The export could not be written. Check the selected folder and file.",
            )
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
        self.review_progress_bar.setRange(0, 1)
        self.review_progress_bar.setValue(0)
        self._set_review_progress_complete(False)
        self.reset_zoom_action.setEnabled(False)
        self.metadata_action.setEnabled(False)
        self.page_stack.setCurrentWidget(self.setup_page)
        self._cleanup_archive_temp()

    def _cleanup_archive_temp(self) -> None:
        if self._archive_temp_directory is None:
            return
        temporary_directory = self._archive_temp_directory
        self._archive_temp_directory = None
        try:
            temporary_directory.cleanup()
        except Exception as exc:
            LOGGER.warning(
                "Temporary archive cleanup failed: %s",
                type(exc).__name__,
            )
            self.statusBar().showMessage(
                "Temporary files could not be removed. Cleanup will retry on next startup."
            )

    def _update_review_status(self) -> None:
        total = self._review_queue.candidate_total
        current = self._review_queue.current_path
        if current is None:
            self.review_progress_label.setText("No comparison selected")
            self.review_progress_bar.setRange(0, 1)
            self.review_progress_bar.setValue(0)
            self._set_review_progress_complete(False)
            return
        decided = len(self._review_queue.decisions)
        self.review_progress_label.setText(current.name)
        self.review_progress_bar.setRange(0, total)
        self.review_progress_bar.setValue(min(decided, total))
        self._set_review_progress_complete(self._review_queue.is_complete)

    def _set_review_progress_complete(self, complete: bool) -> None:
        if self.review_progress_bar.property("complete") == complete:
            return
        self.review_progress_bar.setProperty("complete", complete)
        self.review_progress_bar.style().unpolish(self.review_progress_bar)
        self.review_progress_bar.style().polish(self.review_progress_bar)

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
        next_enabled = enabled and self._review_queue.next_undecided_index(
            self._review_queue.current_index
        ) is not None
        self.next_button.setEnabled(next_enabled)
        self.next_comparison_action.setEnabled(next_enabled)
        self._update_decision_highlight()

    def _populate_pair_navigation(self) -> None:
        self.pair_navigation_list.blockSignals(True)
        self.pair_navigation_list.clear()
        self._pair_navigation_rows.clear()
        for _ in self._review_queue.candidate_paths:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 28))
            self.pair_navigation_list.addItem(item)

            row = QWidget()
            row.setObjectName("navigationPairRow")
            row.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(5, 0, 5, 0)
            row_layout.setSpacing(6)
            name_label = QLabel()
            name_label.setObjectName("navigationPairName")
            status_label = QLabel()
            status_label.setObjectName("navigationPairDecision")
            status_label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            row_layout.addWidget(name_label, 1)
            row_layout.addWidget(status_label)
            self.pair_navigation_list.setItemWidget(item, row)
            self._pair_navigation_rows.append((name_label, status_label))
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
            item.setData(
                Qt.ItemDataRole.AccessibleTextRole,
                f"{index + 1}. {path.name} | {status}",
            )
            item.setToolTip(str(path))
            if index < len(self._pair_navigation_rows):
                name_label, status_label = self._pair_navigation_rows[index]
                name_label.setText(f"{index + 1}. {path.name}")
                status_label.setText(status)
                status_label.setProperty(
                    "decision",
                    decision.decision if decision is not None else "UNDECIDED",
                )
                status_label.style().unpolish(status_label)
                status_label.style().polish(status_label)
        current_index = self._review_queue.current_index
        if 0 <= current_index < self.pair_navigation_list.count():
            self.pair_navigation_list.setCurrentRow(current_index)
        self.pair_navigation_list.blockSignals(False)
        next_enabled = self._candidate_ready and self._review_queue.next_undecided_index(
            current_index
        ) is not None
        self.next_button.setEnabled(next_enabled)
        self.next_comparison_action.setEnabled(next_enabled)
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
        try:
            self._review_queue.set_current_index(index)
            self._start_current_candidate()
        except Exception as exc:
            self.handle_loading_error(
                loading_error_from_exception(
                    exc,
                    title="Comparison could not be loaded",
                    user_message="The selected comparison pair could not be loaded.",
                    stage="comparison_loading",
                    source=self._review_queue.current_path,
                )
            )

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

    def _fit_comparison_after_workspace_resize(self) -> None:
        if self.page_stack.currentWidget() is not self.workspace_page:
            return
        workspace_layout = self.fingerprint_workspace.layout()
        if workspace_layout is not None:
            workspace_layout.activate()
        self.comparison_grid.updateGeometry()
        self.comparison_grid.fit_after_resize()

    def _toggle_metadata(self, visible: bool) -> None:
        self.comparison_grid.set_metadata_visible(visible)
        self.statusBar().showMessage(
            "Sensitive metadata visible" if visible else "Metadata hidden"
        )

    def _export_history(self) -> None:
        dialog = ExportHistoryDialog(self._settings.history_timezone_id(), self)
        if not dialog.exec():
            return
        start_utc, end_utc = dialog.selected_range_utc()
        if self._history_store is None:
            self._warn_history_unavailable()
            return
        try:
            rows = self._history_store.query(start_utc, end_utc)
        except (OSError, sqlite3.Error) as exc:
            LOGGER.error("History query failed: %s", type(exc).__name__)
            self._warn_history_unavailable()
            return
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
        except (OSError, ValueError, RuntimeError) as exc:
            LOGGER.error("History export failed: %s", type(exc).__name__)
            QMessageBox.critical(
                self,
                "Export failed",
                "The export could not be written. Check the selected folder and file.",
            )
            return
        self.statusBar().showMessage(f"Export complete: {output_path}")

    def _show_history(self) -> None:
        if self._history_store is None:
            self._warn_history_unavailable()
            return
        history_store = self._history_store
        try:
            total_count = history_store.count()
            rows = history_store.query(limit=HISTORY_PAGE_SIZE)
        except (OSError, sqlite3.Error) as exc:
            LOGGER.error("History query failed: %s", type(exc).__name__)
            self._warn_history_unavailable()
            return
        DecisionHistoryDialog(
            rows,
            clear_history=self._delete_all_history_records,
            delete_record=self._delete_history_record,
            export_history=self._export_history,
            total_count=total_count,
            load_page=lambda offset, limit: history_store.query(
                limit=limit,
                offset=offset,
            ),
            parent=self,
        ).exec()

    def _delete_history_record(self, history_id: int) -> None:
        if self._history_store is None:
            raise OSError("History is unavailable.")
        self._history_store.delete_by_id(history_id)
        for decision in self._review_queue.decisions:
            if decision.history_id == history_id:
                decision.history_id = None
        self.statusBar().showMessage("History record deleted")

    def _delete_all_history_records(self) -> int:
        if self._history_store is None:
            raise OSError("History is unavailable.")
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
            self._settings.auto_end_session(),
            self,
        )
        if not dialog.exec():
            return
        try:
            self._settings.set_history_timezone_id(dialog.history_timezone_id)
            self._settings.set_offer_session_export(dialog.offer_session_export)
            self._settings.set_auto_end_session(dialog.auto_end_session)
        except (OSError, ValueError) as exc:
            LOGGER.error("Settings write failed: %s", type(exc).__name__)
            QMessageBox.critical(
                self,
                "Settings not saved",
                "The settings file could not be written.",
            )
            return
        self.statusBar().showMessage("Settings saved")

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._thread is not None and self._thread.isRunning():
            self._thread.requestInterruption()
            self._thread.quit()
            self._thread.wait()
        self._cleanup_archive_temp()
        super().closeEvent(event)

    def _warn_history_unavailable(self) -> None:
        QMessageBox.critical(
            self,
            "History unavailable",
            "History storage is unavailable. Decisions cannot be saved.",
        )

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
        if self.page_stack.currentWidget() is self.setup_page and paths:
            event.acceptProposedAction()
            QMessageBox.information(
                self,
                "Unsupported selection",
                "Select NIST records, a ZIP archive, or a RAR archive.",
            )
            return
        event.ignore()
