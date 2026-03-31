"""
Unlock / first-launch window.

Shows either:
  - "Create Vault" flow (first launch, no vault_meta in DB yet)
  - "Unlock Vault" flow (subsequent launches)

Emits the `unlocked` signal with the Vault instance when done.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.vault import Vault, WrongPasswordError


class UnlockWindow(QDialog):
    unlocked = Signal(object)  # emits the Vault instance

    def __init__(self, vault: Vault, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vault = vault
        self._is_new = not vault.is_initialized
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowTitle("EQ-Creds")
        self.setFixedWidth(340)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.MSWindowsFixedSizeDialogHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(32, 32, 32, 32)

        title = QLabel("EQ-Creds")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        if self._is_new:
            subtitle = QLabel("Create your vault master password.\nThis password encrypts all stored credentials.")
        else:
            subtitle = QLabel("Enter your master password to unlock the vault.")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_input.setPlaceholderText("Master password")
        self._password_input.returnPressed.connect(self._on_submit)
        layout.addWidget(self._password_input)

        if self._is_new:
            self._confirm_input = QLineEdit()
            self._confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
            self._confirm_input.setPlaceholderText("Confirm master password")
            self._confirm_input.returnPressed.connect(self._on_submit)
            layout.addWidget(self._confirm_input)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #c0392b;")
        self._error_label.setWordWrap(True)
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        btn_text = "Create Vault" if self._is_new else "Unlock"
        self._submit_btn = QPushButton(btn_text)
        self._submit_btn.setDefault(True)
        self._submit_btn.clicked.connect(self._on_submit)
        layout.addWidget(self._submit_btn)

    # ------------------------------------------------------------------
    # Logic
    # ------------------------------------------------------------------

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.show()

    def _clear_error(self) -> None:
        self._error_label.hide()
        self._error_label.setText("")

    def _on_submit(self) -> None:
        self._clear_error()
        password = self._password_input.text()

        if not password:
            self._show_error("Password cannot be empty.")
            return

        if self._is_new:
            confirm = self._confirm_input.text()
            if password != confirm:
                self._show_error("Passwords do not match.")
                self._confirm_input.clear()
                self._confirm_input.setFocus()
                return
            if len(password) < 4:
                self._show_error("Please choose a password of at least 4 characters.")
                return
            self._submit_btn.setEnabled(False)
            self._submit_btn.setText("Creating vault…")
            try:
                self._vault.initialize(password)
            except Exception as exc:
                self._submit_btn.setEnabled(True)
                self._submit_btn.setText("Create Vault")
                self._show_error(f"Failed to create vault: {exc}")
                return
        else:
            self._submit_btn.setEnabled(False)
            self._submit_btn.setText("Unlocking…")
            try:
                self._vault.unlock(password)
            except WrongPasswordError:
                self._submit_btn.setEnabled(True)
                self._submit_btn.setText("Unlock")
                self._show_error("Incorrect password. Please try again.")
                self._password_input.clear()
                self._password_input.setFocus()
                return
            except Exception as exc:
                self._submit_btn.setEnabled(True)
                self._submit_btn.setText("Unlock")
                self._show_error(f"Unlock failed: {exc}")
                return

        # Clear the password from the widget immediately
        self._password_input.clear()
        if self._is_new:
            self._confirm_input.clear()

        self.unlocked.emit(self._vault)
        self.accept()
