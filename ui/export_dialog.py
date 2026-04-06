"""
Export dialog.

Shows a checkable list of all accounts in the vault.
User picks which accounts to export, sets an export password,
then saves the bundle to a .eqcx file.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.vault import Vault


class ExportDialog(QDialog):
    def __init__(self, vault: Vault, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vault = vault
        self._setup_ui()
        self._populate_accounts()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowTitle("Export Accounts")
        self.setMinimumWidth(440)
        self.setMinimumHeight(480)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)

        # --- Account list ---
        list_label = QLabel("Select accounts to export:")
        list_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(list_label)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        layout.addWidget(self._list, 1)

        # Select all / deselect all
        sel_row = QHBoxLayout()
        sel_all_btn = QPushButton("Select All")
        sel_all_btn.clicked.connect(self._select_all)
        desel_btn = QPushButton("Deselect All")
        desel_btn.clicked.connect(self._deselect_all)
        sel_row.addWidget(sel_all_btn)
        sel_row.addWidget(desel_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # --- Export password ---
        pw_label = QLabel("Export password:")
        pw_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(pw_label)

        pw_hint = QLabel(
            "This password protects the exported file independently of your vault password."
        )
        pw_hint.setWordWrap(True)
        pw_hint.setStyleSheet("font-size: 10px; color: gray;")
        layout.addWidget(pw_hint)

        self._pw_edit = QLineEdit()
        self._pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_edit.setPlaceholderText("Export password")
        layout.addWidget(self._pw_edit)

        self._confirm_edit = QLineEdit()
        self._confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_edit.setPlaceholderText("Confirm export password")
        layout.addWidget(self._confirm_edit)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #c0392b;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        # --- Buttons ---
        btn_box = QDialogButtonBox()
        self._export_btn = btn_box.addButton(
            "Export…", QDialogButtonBox.ButtonRole.AcceptRole
        )
        btn_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self._on_export)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _populate_accounts(self) -> None:
        accounts = self._vault.list_accounts()
        for account in accounts:
            item = QListWidgetItem(account.label)
            item.setData(Qt.ItemDataRole.UserRole, account.id)
            item.setCheckState(Qt.CheckState.Checked)
            if account.status == "archived":
                item.setForeground(Qt.GlobalColor.gray)
            self._list.addItem(item)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _select_all(self) -> None:
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Checked)

    def _deselect_all(self) -> None:
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _selected_ids(self) -> List[str]:
        ids = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.show()

    def _clear_error(self) -> None:
        self._error_label.hide()
        self._error_label.setText("")

    def _on_export(self) -> None:
        self._clear_error()

        selected_ids = self._selected_ids()
        if not selected_ids:
            self._show_error("Select at least one account to export.")
            return

        pw = self._pw_edit.text()
        confirm = self._confirm_edit.text()
        if not pw:
            self._show_error("Export password cannot be empty.")
            self._pw_edit.setFocus()
            return
        if pw != confirm:
            self._show_error("Passwords do not match.")
            self._confirm_edit.clear()
            self._confirm_edit.setFocus()
            return
        if len(pw) < 4:
            self._show_error("Export password must be at least 4 characters.")
            return

        default_name = f"eqcreds-export-{date.today().isoformat()}.eqcx"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Export File",
            str(Path.home() / default_name),
            "EQ-Creds Export (*.eqcx);;All Files (*)",
        )
        if not save_path:
            return  # user cancelled

        self._export_btn.setEnabled(False)
        self._export_btn.setText("Exporting…")
        try:
            bundle = self._vault.export_accounts(selected_ids, pw)
        except Exception as exc:
            self._show_error(f"Export failed: {exc}")
            self._export_btn.setEnabled(True)
            self._export_btn.setText("Export…")
            return
        finally:
            self._pw_edit.clear()
            self._confirm_edit.clear()

        try:
            Path(save_path).write_bytes(bundle)
        except OSError as exc:
            self._show_error(f"Could not write file: {exc}")
            self._export_btn.setEnabled(True)
            self._export_btn.setText("Export…")
            return

        n = len(selected_ids)
        QMessageBox.information(
            self,
            "Export Complete",
            f"Successfully exported {n} account{'s' if n != 1 else ''} to:\n{save_path}",
        )
        self.accept()
