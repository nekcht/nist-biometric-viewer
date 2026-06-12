"""Two-phase comparison-source and Reference Record selection dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nist_biometric_viewer.core.loading import (
    LoadingError,
    loading_error_from_exception,
    validate_loading_file,
)

from .archive_reference_dialog import ReferenceRecordList

NIST_SUFFIXES = {".nist", ".an2", ".an", ".eft", ".ebts", ".dat"}
ARCHIVE_SUFFIXES = {".zip", ".rar"}
SOURCE_FILE_FILTER = (
    "Comparison sources (*.nist *.an2 *.an *.eft *.ebts *.dat *.zip *.rar);;"
    "ANSI/NIST files (*.nist *.an2 *.an *.eft *.ebts *.dat);;"
    "Archives (*.zip *.rar)"
)


class ComparisonSetupDialog(QDialog):
    """Collect comparison sources, then appoint an individual-file Reference Record."""

    def __init__(
        self,
        initial_directory: Path | None = None,
        parent=None,
        initial_paths: list[Path] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Comparison")
        self.resize(720, 520)
        self._initial_directory = initial_directory or Path.home()
        self._record_paths: list[Path] = []
        self._archive_path: Path | None = None

        layout = QVBoxLayout(self)
        self.phase_stack = QStackedWidget()
        self.phase_stack.addWidget(self._build_source_phase())
        self.phase_stack.addWidget(self._build_reference_phase())
        layout.addWidget(self.phase_stack, 1)
        self._show_source_phase()

        if initial_paths:
            self.set_source_selection(initial_paths)

    def _build_source_phase(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        introduction = QLabel("Add at least two ANSI/NIST records, or one ZIP/RAR archive.")
        introduction.setWordWrap(True)
        layout.addWidget(introduction)

        self.source_list = _SmartSourceDropList()
        self.source_list.setObjectName("sourceDropList")
        self.source_list.paths_dropped.connect(self.set_source_selection)
        layout.addWidget(self.source_list, 1)
        self.record_list = self.source_list

        source_buttons = QHBoxLayout()
        self.add_sources_button = QToolButton()
        self.add_sources_button.setObjectName("addSourceButton")
        self.add_sources_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder)
        )
        self.add_sources_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.add_sources_button.setText("Add Records")
        self.add_sources_button.setToolTip("Select comparison records")
        self.add_sources_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_sources_button.clicked.connect(self._choose_sources)
        self.clear_sources_button = QPushButton("Clear")
        self.clear_sources_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogResetButton)
        )
        self.clear_sources_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_sources_button.clicked.connect(self._clear_sources)
        self.next_button = QPushButton("Next")
        self.next_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward)
        )
        self.next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_button.setDefault(True)
        self.next_button.clicked.connect(self._go_next)
        source_buttons.addWidget(self.add_sources_button)
        source_buttons.addWidget(self.clear_sources_button)
        source_buttons.addStretch(1)
        source_buttons.addWidget(self.next_button)
        self.source_buttons_layout = source_buttons
        layout.addLayout(source_buttons)

        self.source_status = QLabel("No records selected")
        self.source_status.setObjectName("sourceStatus")
        self.source_status.setWordWrap(True)
        layout.addWidget(self.source_status)
        return page

    def _build_reference_phase(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        introduction = QLabel(
            "Select the Reference Record. All other records will be compared against it."
        )
        introduction.setObjectName("referenceGuidance")
        introduction.setWordWrap(True)
        layout.addWidget(introduction)

        self.reference_list = ReferenceRecordList()
        self.reference_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reference_list.setAccessibleName("Reference Record")
        self.reference_list.referenceAppointmentChanged.connect(
            self._update_reference_navigation
        )
        layout.addWidget(self.reference_list, 1)
        reference_navigation = QHBoxLayout()
        self.reference_back_button = QPushButton("Back")
        self.reference_back_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack)
        )
        self.reference_back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reference_back_button.clicked.connect(self._go_back)
        reference_navigation.addWidget(self.reference_back_button)
        reference_navigation.addStretch(1)
        self.reference_next_button = QPushButton("Next")
        self.reference_next_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward)
        )
        self.reference_next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reference_next_button.clicked.connect(self._go_next)
        reference_navigation.addWidget(self.reference_next_button)
        layout.addLayout(reference_navigation)
        self._update_reference_navigation()
        return page

    @property
    def file_a_path(self) -> Path | None:
        if self._archive_path is not None:
            return None
        return self.reference_list.reference_path

    @property
    def candidate_paths(self) -> list[Path]:
        reference = self.file_a_path
        if reference is None:
            return []
        return [path for path in self._record_paths if path != reference]

    @property
    def archive_path(self) -> Path | None:
        return self._archive_path

    def set_selection(self, file_a_path: Path, candidate_paths: list[Path]) -> None:
        """Populate individual records, primarily for repeatable UI testing."""
        self.set_record_selection([file_a_path, *candidate_paths], file_a_path)

    def set_record_selection(
        self,
        record_paths: list[Path],
        reference_path: Path | None = None,
    ) -> None:
        """Populate one record group and optionally appoint its Reference Record."""
        self._archive_path = None
        self._record_paths = list(dict.fromkeys(record_paths))
        self._refresh_reference_choices(reference_path)
        self._refresh_source_list()

    def set_archive_selection(self, archive_path: Path) -> None:
        """Populate one ZIP or RAR archive, primarily for repeatable UI testing."""
        self._record_paths.clear()
        self._archive_path = archive_path
        self._refresh_reference_choices()
        self._refresh_source_list()

    def set_source_selection(self, paths: list[Path]) -> None:
        """Identify a dropped or selected source as an archive or ANSI/NIST record group."""
        try:
            self._set_source_selection(paths)
        except Exception as exc:
            self._show_loading_error(
                loading_error_from_exception(
                    exc,
                    title="Files could not be selected",
                    user_message="The selected sources could not be prepared.",
                    stage="file_selection",
                    source=paths[0] if paths else None,
                )
            )

    def _set_source_selection(self, paths: list[Path]) -> None:
        paths = list(dict.fromkeys(paths))
        is_archive = len(paths) == 1 and paths[0].suffix.casefold() in ARCHIVE_SUFFIXES
        is_record_group = bool(paths) and all(
            path.suffix.casefold() in NIST_SUFFIXES for path in paths
        )
        if not is_archive and not is_record_group:
            QMessageBox.information(
                self,
                "Unsupported selection",
                "Select NIST records, a ZIP archive, or a RAR archive.",
            )
            return
        try:
            for path in paths:
                validate_loading_file(path, stage="file_selection")
        except LoadingError as error:
            self._show_loading_error(error)
            return
        if is_archive:
            self.set_archive_selection(paths[0])
            return
        if is_record_group:
            existing_paths = self._record_paths if self._archive_path is None else []
            self.set_record_selection([*existing_paths, *paths], self.file_a_path)
            return

    def _show_loading_error(self, error: LoadingError) -> None:
        dialog = QMessageBox(
            QMessageBox.Icon.Warning,
            error.title,
            error.user_message,
            parent=self,
        )
        dialog.setDetailedText(error.technical_details)
        dialog.exec()

    def _choose_sources(self) -> None:
        try:
            selected, _ = QFileDialog.getOpenFileNames(
                self,
                "Add ANSI/NIST Files or Archive",
                str(self._selection_directory()),
                SOURCE_FILE_FILTER,
            )
        except Exception as exc:
            self._show_loading_error(
                loading_error_from_exception(
                    exc,
                    title="Files could not be selected",
                    user_message="The file selection dialog could not be opened.",
                    stage="file_selection",
                )
            )
            return
        if selected:
            self.set_source_selection([Path(path) for path in selected])

    def _clear_sources(self) -> None:
        self._record_paths.clear()
        self._archive_path = None
        self._refresh_reference_choices()
        self._refresh_source_list()

    def _refresh_reference_choices(self, reference_path: Path | None = None) -> None:
        previous_reference = reference_path or self.file_a_path
        self.reference_list.set_paths(self._record_paths, previous_reference)
        self.reference_list.setEnabled(bool(self._record_paths))
        self._update_reference_navigation()

    def _refresh_source_list(self) -> None:
        self.source_list.clear()
        if self._archive_path is not None:
            archive_type = self._archive_path.suffix[1:].upper()
            item = QListWidgetItem(f"{archive_type} Archive: {self._archive_path}")
            item.setToolTip(str(self._archive_path))
            self.source_list.addItem(item)
            self.source_status.setText(
                f"{archive_type} archive selected"
            )
            return
        for path in self._record_paths:
            item = QListWidgetItem(f"ANSI/NIST Record: {path}")
            item.setToolTip(str(path))
            self.source_list.addItem(item)
        if self._record_paths:
            self.source_status.setText(
                f"Records selected: {len(self._record_paths)}"
            )
        else:
            self.source_status.setText("No records selected")

    def _selection_directory(self) -> Path:
        if self._archive_path is not None:
            return self._archive_path.parent
        if self._record_paths:
            return self._record_paths[0].parent
        return self._initial_directory

    def _go_next(self) -> None:
        if self.phase_stack.currentIndex() == 0:
            if not self._validate_source_selection():
                return
            if self._archive_path is not None:
                self.accept()
                return
            self._show_reference_phase()
            return
        if self.file_a_path is None:
            QMessageBox.information(
                self,
                "Reference Record required",
                "Select a Reference Record.",
            )
            return
        self.accept()

    def _show_source_phase(self) -> None:
        self.phase_stack.setCurrentIndex(0)
        self.next_button.setText("Next")
        self.next_button.setDefault(True)
        self.reference_next_button.setDefault(False)

    def _show_reference_phase(self) -> None:
        self.phase_stack.setCurrentIndex(1)
        self.next_button.setDefault(False)
        self.reference_next_button.setDefault(True)
        self._update_reference_navigation()

    def _go_back(self) -> None:
        self._show_source_phase()

    def _update_reference_navigation(self) -> None:
        self.reference_next_button.setEnabled(self.file_a_path is not None)
        self.reference_back_button.setEnabled(True)

    def _validate_source_selection(self) -> bool:
        if self._archive_path is not None:
            return True
        if len(self._record_paths) >= 2:
            return True
        QMessageBox.information(
            self,
            "Records required",
            "Select one ZIP/RAR archive or at least two ANSI/NIST records.",
        )
        return False

    def _validate_and_accept(self) -> None:
        """Compatibility entry point for callers that previously used one-step validation."""
        self._go_next()


class _SmartSourceDropList(QListWidget):
    paths_dropped = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if local_source_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = local_source_paths(event)
        if paths:
            event.acceptProposedAction()
            QTimer.singleShot(
                0,
                lambda dropped_paths=paths: self.paths_dropped.emit(dropped_paths),
            )
        else:
            event.ignore()


def valid_source_paths(paths: list[Path]) -> bool:
    return (len(paths) == 1 and paths[0].suffix.casefold() in ARCHIVE_SUFFIXES) or (
        bool(paths) and all(path.suffix.casefold() in NIST_SUFFIXES for path in paths)
    )


def local_source_paths(event) -> list[Path]:
    if not event.mimeData().hasUrls():
        return []
    return [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
