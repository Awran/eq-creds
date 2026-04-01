"""
Account add/edit dialog.

Handles both creating a new account and editing an existing one.
Character list is inline: add row / remove row, no upper limit.
Emits `saved` with the Account model when the user saves.
"""

from __future__ import annotations

from typing import List, Optional
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.models import Account, Character, RoleFlag, RotateFlag, StatusFlag
from core.vault import Vault


class _CharacterRow(QWidget):
    remove_requested = Signal(object)  # emits self

    def __init__(self, character: Optional[Character] = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._character = character
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Character name *")
        self.name_edit.setMinimumWidth(120)

        self.class_edit = QLineEdit()
        self.class_edit.setPlaceholderText("Class")
        self.class_edit.setMinimumWidth(90)

        self.level_spin = QSpinBox()
        self.level_spin.setRange(1, 60)
        self.level_spin.setValue(1)
        self.level_spin.setFixedWidth(84)
        self.level_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.level_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.level_spin.setAccelerated(True)
        self.level_spin.setKeyboardTracking(False)
        self.level_spin.setToolTip("Level (type a number or use arrows)")

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Notes")

        remove_btn = QPushButton("×")
        remove_btn.setFixedWidth(28)
        remove_btn.setToolTip("Remove character")
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))

        layout.addWidget(self.name_edit, 2)
        layout.addWidget(self.class_edit, 1)
        layout.addWidget(self.level_spin)
        layout.addWidget(self.notes_edit, 2)
        layout.addWidget(remove_btn)

        if character:
            self.name_edit.setText(character.name or "")
            self.class_edit.setText(character.char_class or "")
            self.level_spin.setValue(character.level or 1)
            self.notes_edit.setText(character.notes or "")

    def to_character(self, account_id: str) -> Optional[Character]:
        name = self.name_edit.text().strip()
        if not name:
            return None
        return Character(
            id=self._character.id if self._character else str(uuid4()),
            account_id=account_id,
            name=name,
            char_class=self.class_edit.text().strip() or None,
            level=self.level_spin.value(),
            notes=self.notes_edit.text().strip() or None,
        )


class AccountForm(QDialog):
    saved = Signal(object)  # emits Account

    def __init__(
        self,
        vault: Vault,
        account: Optional[Account] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vault = vault
        self._account = account
        self._is_edit = account is not None
        self._char_rows: List[_CharacterRow] = []
        self._setup_ui()
        if self._is_edit:
            self._populate(account)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        title = "Edit Account" if self._is_edit else "New Account"
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.setMinimumHeight(560)

        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setSpacing(16)
        body_layout.setContentsMargins(24, 20, 24, 20)
        scroll.setWidget(body_widget)
        outer.addWidget(scroll, 1)

        # --- Credentials section ---
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("e.g. GuildBank1 *")
        form.addRow("Label *", self._label_edit)

        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText("Login username")
        form.addRow("Username", self._username_edit)

        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setPlaceholderText("Password")

        pwd_row = QWidget()
        pwd_hl = QHBoxLayout(pwd_row)
        pwd_hl.setContentsMargins(0, 0, 0, 0)
        pwd_hl.setSpacing(4)
        self._show_pwd_btn = QPushButton("Show")
        self._show_pwd_btn.setFixedWidth(65)
        self._show_pwd_btn.setCheckable(True)
        self._show_pwd_btn.toggled.connect(self._toggle_password_visibility)
        pwd_hl.addWidget(self._password_edit)
        pwd_hl.addWidget(self._show_pwd_btn)
        form.addRow("Password", pwd_row)

        self._owner_edit = QLineEdit()
        self._owner_edit.setPlaceholderText("Account owner")
        form.addRow("Owner", self._owner_edit)

        self._shared_by_edit = QLineEdit()
        self._shared_by_edit.setPlaceholderText("Who shared this with you?")
        form.addRow("Shared by", self._shared_by_edit)

        body_layout.addLayout(form)

        # --- Flags row ---
        flags_row = QHBoxLayout()
        flags_row.setSpacing(12)

        self._status_combo = QComboBox()
        for v in ("active", "archived"):
            self._status_combo.addItem(v.capitalize(), v)

        self._role_combo = QComboBox()
        self._role_combo.addItem("— role —", None)
        for v in ("main", "banker", "mule", "utility"):
            self._role_combo.addItem(v.capitalize(), v)

        self._rotate_combo = QComboBox()
        self._rotate_combo.addItem("— rotate —", None)
        for label, v in (("Rotate", "rotate"), ("No Rotate", "no_rotate"), ("Shared", "shared")):
            self._rotate_combo.addItem(label, v)

        flags_row.addWidget(QLabel("Status:"))
        flags_row.addWidget(self._status_combo)
        flags_row.addSpacing(8)
        flags_row.addWidget(QLabel("Role:"))
        flags_row.addWidget(self._role_combo)
        flags_row.addSpacing(8)
        flags_row.addWidget(QLabel("Rotate:"))
        flags_row.addWidget(self._rotate_combo)
        flags_row.addStretch()
        body_layout.addLayout(flags_row)

        # --- Tags ---
        tag_label = QLabel("Tags")
        tag_label.setStyleSheet("font-weight: bold;")
        body_layout.addWidget(tag_label)

        self._tags_edit = QLineEdit()
        self._tags_edit.setPlaceholderText("Comma-separated tags, e.g. guild, raider, banker")
        all_tags = self._vault.all_tag_names()
        if all_tags:
            completer = QCompleter(all_tags)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            self._tags_edit.setCompleter(completer)
        body_layout.addWidget(self._tags_edit)

        # --- Notes ---
        notes_label = QLabel("Notes")
        notes_label.setStyleSheet("font-weight: bold;")
        body_layout.addWidget(notes_label)

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Any context, login quirks, alt info…")
        self._notes_edit.setMaximumHeight(90)
        body_layout.addWidget(self._notes_edit)

        # --- Characters ---
        char_header = QHBoxLayout()
        char_title = QLabel("Characters")
        char_title.setStyleSheet("font-weight: bold;")
        add_char_btn = QPushButton("+ Add Character")
        add_char_btn.clicked.connect(lambda: self._add_char_row())
        char_header.addWidget(char_title)
        char_header.addStretch()
        char_header.addWidget(add_char_btn)
        body_layout.addLayout(char_header)

        # Column headers
        col_header = QWidget()
        col_hl = QHBoxLayout(col_header)
        col_hl.setContentsMargins(0, 0, 0, 0)
        col_hl.setSpacing(6)
        for text, stretch in (("Name", 2), ("Class", 1), ("Lvl", 0), ("Notes", 2), ("", 0)):
            lbl = QLabel(text)
            lbl.setStyleSheet("color: gray; font-size: 11px;")
            if stretch:
                col_hl.addWidget(lbl, stretch)
            elif text == "Lvl":
                lbl.setFixedWidth(54)
                col_hl.addWidget(lbl)
            else:
                lbl.setFixedWidth(28)
                col_hl.addWidget(lbl)
        body_layout.addWidget(col_header)

        self._char_container = QVBoxLayout()
        self._char_container.setSpacing(4)
        body_layout.addLayout(self._char_container)

        body_layout.addStretch()

        # --- Button box ---
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        outer.addWidget(btn_box)
        outer_margins = btn_box.contentsMargins()
        btn_box.setContentsMargins(24, 8, 24, 12)

    # ------------------------------------------------------------------
    # Character rows
    # ------------------------------------------------------------------

    def _add_char_row(self, character: Optional[Character] = None) -> None:
        row = _CharacterRow(character, self)
        row.remove_requested.connect(self._remove_char_row)
        self._char_rows.append(row)
        self._char_container.addWidget(row)

    def _remove_char_row(self, row: _CharacterRow) -> None:
        self._char_rows.remove(row)
        self._char_container.removeWidget(row)
        row.deleteLater()

    # ------------------------------------------------------------------
    # Populate (edit mode)
    # ------------------------------------------------------------------

    def _populate(self, account: Account) -> None:
        self._label_edit.setText(account.label or "")
        self._username_edit.setText(account.username or "")
        self._password_edit.setText(account.password or "")
        self._owner_edit.setText(account.owner or "")
        self._shared_by_edit.setText(account.shared_by or "")
        self._notes_edit.setPlainText(account.notes or "")
        self._tags_edit.setText(", ".join(account.tags))

        idx = self._status_combo.findData(account.status)
        if idx >= 0:
            self._status_combo.setCurrentIndex(idx)

        idx = self._role_combo.findData(account.role_flag)
        if idx >= 0:
            self._role_combo.setCurrentIndex(idx)

        idx = self._rotate_combo.findData(account.rotate_flag)
        if idx >= 0:
            self._rotate_combo.setCurrentIndex(idx)

        for ch in account.characters:
            self._add_char_row(ch)

    # ------------------------------------------------------------------
    # Visibility toggle
    # ------------------------------------------------------------------

    def _toggle_password_visibility(self, checked: bool) -> None:
        if checked:
            self._password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._show_pwd_btn.setText("Hide")
        else:
            self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._show_pwd_btn.setText("Show")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        label = self._label_edit.text().strip()
        if not label:
            QMessageBox.warning(self, "Validation", "Label is required.")
            self._label_edit.setFocus()
            return

        account_id = self._account.id if self._is_edit else str(uuid4())

        tags_raw = self._tags_edit.text()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

        characters: List[Character] = []
        for row in self._char_rows:
            ch = row.to_character(account_id)
            if ch:
                characters.append(ch)

        account = Account(
            id=account_id,
            label=label,
            username=self._username_edit.text(),
            password=self._password_edit.text(),
            owner=self._owner_edit.text().strip() or None,
            shared_by=self._shared_by_edit.text().strip() or None,
            status=self._status_combo.currentData(),
            role_flag=self._role_combo.currentData(),
            rotate_flag=self._rotate_combo.currentData(),
            notes=self._notes_edit.toPlainText().strip() or None,
            characters=characters,
            tags=tags,
        )

        try:
            self._vault.save_account(account)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return

        # Clear sensitive fields immediately
        self._password_edit.clear()
        self._username_edit.clear()

        self.saved.emit(account)
        self.accept()
