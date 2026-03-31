"""
Settings dialog.

V1 scope: change master password (re-key operation).
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.vault import Vault, WrongPasswordError
from ui.theme import THEME_DARK, THEME_LIGHT


class SettingsDialog(QDialog):
    def __init__(self, vault: Vault, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vault = vault
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Settings")
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 16)

        heading = QLabel("Change Master Password")
        heading.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(8)

        self._old_pw = QLineEdit()
        self._old_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._old_pw.setPlaceholderText("Current password")
        form.addRow("Current password", self._old_pw)

        self._new_pw = QLineEdit()
        self._new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_pw.setPlaceholderText("New password")
        form.addRow("New password", self._new_pw)

        self._confirm_pw = QLineEdit()
        self._confirm_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_pw.setPlaceholderText("Confirm new password")
        self._confirm_pw.returnPressed.connect(self._on_change)
        form.addRow("Confirm new", self._confirm_pw)

        layout.addLayout(form)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #c0392b;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        appearance_heading = QLabel("Appearance")
        appearance_heading.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(appearance_heading)

        appearance_row = QHBoxLayout()
        appearance_row.setSpacing(8)
        self._theme_combo = QComboBox()
        self._theme_combo.addItem("Dark", THEME_DARK)
        self._theme_combo.addItem("Light", THEME_LIGHT)
        current = THEME_DARK
        app = QApplication.instance()
        if app is not None and hasattr(app, "current_theme"):
            current = app.current_theme()  # type: ignore[attr-defined]
        idx = self._theme_combo.findData(current)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)

        self._apply_theme_btn = QPushButton("Apply Theme")
        self._apply_theme_btn.clicked.connect(self._apply_theme)
        appearance_row.addWidget(self._theme_combo, 1)
        appearance_row.addWidget(self._apply_theme_btn)
        layout.addLayout(appearance_row)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("Change Password")
        btn_box.accepted.connect(self._on_change)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_change(self) -> None:
        self._error_label.hide()

        old_pw = self._old_pw.text()
        new_pw = self._new_pw.text()
        confirm = self._confirm_pw.text()

        if not old_pw or not new_pw:
            self._show_error("All fields are required.")
            return
        if new_pw != confirm:
            self._show_error("New passwords do not match.")
            self._confirm_pw.clear()
            self._confirm_pw.setFocus()
            return
        if len(new_pw) < 4:
            self._show_error("New password must be at least 4 characters.")
            return

        try:
            self._vault.change_password(old_pw, new_pw)
        except WrongPasswordError:
            self._show_error("Current password is incorrect.")
            self._old_pw.clear()
            self._old_pw.setFocus()
            return
        except Exception as exc:
            self._show_error(f"Failed: {exc}")
            return
        finally:
            self._old_pw.clear()
            self._new_pw.clear()
            self._confirm_pw.clear()

        QMessageBox.information(self, "Success", "Master password changed successfully.")
        self.accept()

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        if app is None or not hasattr(app, "set_theme"):
            QMessageBox.warning(self, "Theme", "Theme manager unavailable.")
            return
        theme = self._theme_combo.currentData()
        app.set_theme(str(theme), persist=True)  # type: ignore[attr-defined]

    def _show_error(self, msg: str) -> None:
        self._error_label.setText(msg)
        self._error_label.show()
