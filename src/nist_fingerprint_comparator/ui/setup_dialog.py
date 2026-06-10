"""Single-step individual-file or ZIP archive selection dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

NIST_FILE_FILTER = "ANSI/NIST files (*.nist *.an2 *.eft *.dat);;All files (*)"
ZIP_FILE_FILTER = "Comparison ZIP archives (*_files.zip *.zip);;All files (*)"


class ComparisonSetupDialog(QDialog):
    """Collect an archive or File A and its File B candidate group."""

    def __init__(self, initial_directory: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New One-to-Many Comparison")
        self.resize(720, 520)
        self._initial_directory = initial_directory or Path.home()
        self._file_a_path: Path | None = None
        self._candidate_paths: list[Path] = []
        self._archive_path: Path | None = None

        layout = QVBoxLayout(self)
        introduction = QLabel(
            "Select File A and the File B candidates individually, or select one ZIP "
            "archive that contains the complete comparison group. The workspace opens "
            "after the first pair is ready."
        )
        introduction.setWordWrap(True)
        layout.addWidget(introduction)

        self.source_tabs = QTabWidget()
        self.source_tabs.addTab(self._build_individual_files_tab(), "Individual Files")
        self.source_tabs.addTab(self._build_archive_tab(), "ZIP Archive")
        layout.addWidget(self.source_tabs, 1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Start Comparison")
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    @property
    def file_a_path(self) -> Path | None:
        return self._file_a_path if self.source_tabs.currentIndex() == 0 else None

    @property
    def candidate_paths(self) -> list[Path]:
        return list(self._candidate_paths) if self.source_tabs.currentIndex() == 0 else []

    @property
    def archive_path(self) -> Path | None:
        return self._archive_path if self.source_tabs.currentIndex() == 1 else None

    def set_selection(self, file_a_path: Path, candidate_paths: list[Path]) -> None:
        """Populate the individual-file tab, primarily for repeatable UI testing."""
        self.source_tabs.setCurrentIndex(0)
        self._file_a_path = file_a_path
        self.file_a_edit.setText(str(file_a_path))
        self._candidate_paths = list(dict.fromkeys(candidate_paths))
        self._refresh_candidates()

    def set_archive_selection(self, archive_path: Path) -> None:
        """Populate the ZIP archive tab, primarily for repeatable UI testing."""
        self.source_tabs.setCurrentIndex(1)
        self._archive_path = archive_path
        self.archive_edit.setText(str(archive_path))

    def _build_individual_files_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        file_a_row = QHBoxLayout()
        self.file_a_edit = QLineEdit()
        self.file_a_edit.setReadOnly(True)
        file_a_button = QPushButton("Browse...")
        file_a_button.setCursor(Qt.CursorShape.PointingHandCursor)
        file_a_button.clicked.connect(self._choose_file_a)
        file_a_row.addWidget(self.file_a_edit, 1)
        file_a_row.addWidget(file_a_button)
        form.addRow("Reference File A", file_a_row)
        layout.addLayout(form)

        candidates_label = QLabel("File B candidates")
        candidates_label.setObjectName("sourceTitle")
        layout.addWidget(candidates_label)
        self.candidate_list = QListWidget()
        layout.addWidget(self.candidate_list, 1)

        candidate_buttons = QHBoxLayout()
        select_candidates = QPushButton("Select Candidate Files...")
        select_candidates.setCursor(Qt.CursorShape.PointingHandCursor)
        select_candidates.clicked.connect(self._choose_candidates)
        clear_candidates = QPushButton("Clear")
        clear_candidates.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_candidates.clicked.connect(self._clear_candidates)
        candidate_buttons.addWidget(select_candidates)
        candidate_buttons.addWidget(clear_candidates)
        candidate_buttons.addStretch(1)
        layout.addLayout(candidate_buttons)
        return tab

    def _build_archive_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        guidance = QLabel(
            "The ZIP filename must be <File A reference>_files.zip. Its .nist files must "
            "be named <reference>-fp.nist, <reference>_fp.nist, <reference>-fi.nist, or "
            "<reference>_fi.nist. The matching reference becomes File A."
        )
        guidance.setWordWrap(True)
        layout.addWidget(guidance)
        archive_row = QHBoxLayout()
        self.archive_edit = QLineEdit()
        self.archive_edit.setReadOnly(True)
        archive_button = QPushButton("Select ZIP Archive...")
        archive_button.setCursor(Qt.CursorShape.PointingHandCursor)
        archive_button.clicked.connect(self._choose_archive)
        archive_row.addWidget(self.archive_edit, 1)
        archive_row.addWidget(archive_button)
        layout.addLayout(archive_row)
        layout.addStretch(1)
        return tab

    def _choose_file_a(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select Reference ANSI/NIST File A",
            str(self._selection_directory()),
            NIST_FILE_FILTER,
        )
        if selected:
            self._file_a_path = Path(selected)
            self.file_a_edit.setText(selected)

    def _choose_candidates(self) -> None:
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Select ANSI/NIST File B Candidates",
            str(self._selection_directory()),
            NIST_FILE_FILTER,
        )
        if selected:
            self._candidate_paths = list(dict.fromkeys(Path(path) for path in selected))
            self._refresh_candidates()

    def _choose_archive(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select One-to-Many Comparison ZIP Archive",
            str(self._selection_directory()),
            ZIP_FILE_FILTER,
        )
        if selected:
            self._archive_path = Path(selected)
            self.archive_edit.setText(selected)

    def _clear_candidates(self) -> None:
        self._candidate_paths.clear()
        self._refresh_candidates()

    def _refresh_candidates(self) -> None:
        self.candidate_list.clear()
        for index, path in enumerate(self._candidate_paths, start=1):
            self.candidate_list.addItem(f"{index}. {path}")

    def _selection_directory(self) -> Path:
        if self._archive_path is not None:
            return self._archive_path.parent
        if self._file_a_path is not None:
            return self._file_a_path.parent
        return self._initial_directory

    def _validate_and_accept(self) -> None:
        if self.source_tabs.currentIndex() == 1:
            if self._archive_path is None:
                QMessageBox.information(
                    self,
                    "ZIP archive required",
                    "Select a comparison ZIP archive.",
                )
                return
            self.accept()
            return
        if self._file_a_path is None:
            QMessageBox.information(self, "Reference required", "Select reference File A.")
            return
        if not self._candidate_paths:
            QMessageBox.information(
                self,
                "Candidates required",
                "Select at least one File B candidate.",
            )
            return
        self.accept()
