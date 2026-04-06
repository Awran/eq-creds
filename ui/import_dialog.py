"""
Import dialog.

Two-phase single dialog:

Phase 1 — File + password:
  File path line edit + Browse button
  Password field
  "Preview…" button

Phase 2 — Conflict resolution (replaces phase 1 content):
  Summary label ("N accounts to import, M conflicts found")
  If conflicts exist:
    QTableWidget with per-row Merge/Skip combo
    "Merge All" / "Skip All" bulk buttons
  "Import" button

Emits `imported` with the count of accounts written.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.export_import import ConflictResolution, ImportPreview
from core.vault import Vault, WrongPasswordError


class ImportDialog(QDialog):
    imported = Signal(int)  # emits count of accounts written

    def __init__(self, vault: Vault, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vault = vault
        self._preview: Optional[ImportPreview] = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowTitle("Import Accounts")
        self.setMinimumWidth(500)

        self._outer = QVBoxLayout(self)
        self._outer.setSpacing(12)
        self._outer.setContentsMargins(20, 16, 20, 16)

        self._phase1_widget = QWidget()
        self._build_phase1(self._phase1_widget)
        self._outer.addWidget(self._phase1_widget)

        self._phase2_widget = QWidget()
        self._phase2_widget.hide()
        self._build_phase2(self._phase2_widget)
        self._outer.addWidget(self._phase2_widget, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        self._outer.addWidget(sep)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #c0392b;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self._outer.addWidget(self._error_label)

        btn_row = QHBoxLayout()
        self._action_btn = QPushButton("Preview…")
        self._action_btn.setDefault(True)
        self._action_btn.clicked.connect(self._on_action)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(self._action_btn)
        btn_row.addWidget(cancel_btn)
        self._outer.addLayout(btn_row)

    def _build_phase1(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        file_label = QLabel("Export file (.eqcx):")
        file_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(file_label)

        file_row = QHBoxLayout()
        self._file_edit = QLineEdit()
        self._file_edit.setPlaceholderText("Path to .eqcx file…")
        self._file_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(self._file_edit, 1)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        pw_label = QLabel("Export password:")
        pw_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(pw_label)

        self._pw_edit = QLineEdit()
        self._pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_edit.setPlaceholderText("Password used when the file was exported")
        self._pw_edit.returnPressed.connect(self._on_action)
        layout.addWidget(self._pw_edit)

    def _build_phase2(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._summary_label = QLabel()
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)

        self._conflict_frame = QWidget()
        conflict_layout = QVBoxLayout(self._conflict_frame)
        conflict_layout.setContentsMargins(0, 0, 0, 0)
        conflict_layout.setSpacing(6)

        conflict_title = QLabel("Conflicts — choose how to resolve each:")
        conflict_title.setStyleSheet("font-weight: bold;")
        conflict_layout.addWidget(conflict_title)

        bulk_row = QHBoxLayout()
        merge_all_btn = QPushButton("Merge All")
        merge_all_btn.clicked.connect(self._merge_all)
        skip_all_btn = QPushButton("Skip All")
        skip_all_btn.clicked.connect(self._skip_all)
        bulk_row.addWidget(merge_all_btn)
        bulk_row.addWidget(skip_all_btn)
        bulk_row.addStretch()
        conflict_layout.addLayout(bulk_row)

        self._conflict_table = QTableWidget(0, 3)
        self._conflict_table.setHorizontalHeaderLabels(["Label", "Username", "Action"])
        self._conflict_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._conflict_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._conflict_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Fixed
        )
        self._conflict_table.setColumnWidth(2, 90)
        self._conflict_table.verticalHeader().setVisible(False)
        self._conflict_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._conflict_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._conflict_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        conflict_layout.addWidget(self._conflict_table, 1)

        layout.addWidget(self._conflict_frame, 1)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Export File",
            str(Path.home()),
            "EQ-Creds Export (*.eqcx);;All Files (*)",
        )
        if path:
            self._file_edit.setText(path)

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.show()

    def _clear_error(self) -> None:
        self._error_label.hide()
        self._error_label.setText("")

    def _merge_all(self) -> None:
        self._set_all_resolutions("Merge")

    def _skip_all(self) -> None:
        self._set_all_resolutions("Skip")

    def _set_all_resolutions(self, value: str) -> None:
        for row in range(self._conflict_table.rowCount()):
            combo = self._conflict_table.cellWidget(row, 2)
            if isinstance(combo, QComboBox):
                idx = combo.findText(value)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

    def _on_action(self) -> None:
        self._clear_error()
        if self._preview is None:
            self._do_preview()
        else:
            self._do_import()

    def _do_preview(self) -> None:
        file_path = self._file_edit.text().strip()
        if not file_path:
            self._show_error("Choose a .eqcx file to import.")
            return
        export_pw = self._pw_edit.text()
        if not export_pw:
            self._show_error("Enter the export password.")
            self._pw_edit.setFocus()
            return

        try:
            data = Path(file_path).read_bytes()
        except OSError as exc:
            self._show_error(f"Could not read file: {exc}")
            return

        self._action_btn.setEnabled(False)
        self._action_btn.setText("Loading…")
        try:
            preview = self._vault.preview_import(data, export_pw)
        except WrongPasswordError:
            self._show_error("Incorrect export password or the file is corrupted.")
            self._pw_edit.clear()
            self._pw_edit.setFocus()
            return
        except ValueError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:
            self._show_error(f"Import preview failed: {exc}")
            return
        finally:
            self._pw_edit.clear()
            self._action_btn.setEnabled(True)

        self._preview = preview
        self._transition_to_phase2(preview)

    def _transition_to_phase2(self, preview: ImportPreview) -> None:
        self._phase1_widget.hide()
        self._phase2_widget.show()
        self._action_btn.setText("Import")
        self.setMinimumHeight(300)

        n_clean = len(preview.clean)
        n_conflict = len(preview.conflicts)
        total = n_clean + n_conflict

        if n_conflict == 0:
            self._summary_label.setText(
                f"{total} account{'s' if total != 1 else ''} ready to import. No conflicts."
            )
            self._conflict_frame.hide()
        else:
            self._summary_label.setText(
                f"{total} account{'s' if total != 1 else ''} to import — "
                f"{n_conflict} conflict{'s' if n_conflict != 1 else ''} found."
            )
            self._conflict_frame.show()
            self._conflict_table.setRowCount(n_conflict)
            for i, record in enumerate(preview.conflicts):
                self._conflict_table.setItem(
                    i, 0, QTableWidgetItem(record.imported.label)
                )
                self._conflict_table.setItem(
                    i, 1, QTableWidgetItem(record.imported.username or "(blank)")
                )
                combo = QComboBox()
                combo.addItem("Skip")
                combo.addItem("Merge")
                combo.setCurrentIndex(0)  # default: Skip
                self._conflict_table.setCellWidget(i, 2, combo)
                self._conflict_table.setRowHeight(i, 28)

            visible = min(max(n_conflict, 2), 8)
            header_h = self._conflict_table.horizontalHeader().height() or 26
            self._conflict_table.setMinimumHeight(header_h + visible * 30 + 8)

    def _do_import(self) -> None:
        if self._preview is None:
            return

        # Apply per-row resolution choices to the preview
        for i, record in enumerate(self._preview.conflicts):
            combo = self._conflict_table.cellWidget(i, 2)
            if isinstance(combo, QComboBox):
                if combo.currentText() == "Merge":
                    record.resolution = ConflictResolution.MERGE
                else:
                    record.resolution = ConflictResolution.SKIP

        self._action_btn.setEnabled(False)
        self._action_btn.setText("Importing…")
        try:
            count = self._vault.apply_import(self._preview)
        except Exception as exc:
            self._show_error(f"Import failed: {exc}")
            self._action_btn.setEnabled(True)
            self._action_btn.setText("Import")
            return

        self.imported.emit(count)
        QMessageBox.information(
            self,
            "Import Complete",
            f"Successfully imported {count} account{'s' if count != 1 else ''}.",
        )
        self.accept()
