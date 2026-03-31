"""
Account detail panel — read-only view of a single account.

Credentials are shown masked by default.  A "Reveal" button decrypts and
displays the plaintext for REVEAL_SECONDS seconds, then re-masks.

Emits:
  edit_requested(account_id: str)   — when the Edit button is clicked
  delete_requested(account_id: str) — when Delete is confirmed
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import Account
from core.vault import Vault

REVEAL_SECONDS = 15
MASK = "•" * 10


class _CredentialRow(QWidget):
    """
    A self-contained credential row: [Label:]  ••••••••••  [Reveal]

    Using a QWidget (not a bare QHBoxLayout) means _clear_body can call
    deleteLater() on it directly, preventing ghost widgets on re-render.
    """

    def __init__(self, label: str, plaintext: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plaintext = plaintext
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._mask)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        name_lbl = QLabel(f"{label}:")
        name_lbl.setFixedWidth(76)

        self._val_lbl = QLabel(MASK if plaintext else "(not set)")
        self._val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._val_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._btn = QPushButton("Reveal")
        self._btn.setFixedWidth(74)
        self._btn.clicked.connect(self._toggle)

        layout.addWidget(name_lbl)
        layout.addWidget(self._val_lbl, 1)
        layout.addWidget(self._btn)

    def _toggle(self) -> None:
        if self._timer.isActive():
            self._mask()
        else:
            self._reveal()

    def _reveal(self) -> None:
        self._val_lbl.setText(self._plaintext or "(empty)")
        self._btn.setText("Hide")
        if self._plaintext:
            self._timer.start(REVEAL_SECONDS * 1000)

    def _mask(self) -> None:
        self._timer.stop()
        self._val_lbl.setText(MASK if self._plaintext else "(not set)")
        self._btn.setText("Reveal")

    def force_mask(self) -> None:
        self._mask()


def _purge_layout(layout) -> None:
    """Recursively remove and delete all items from a layout."""
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            _purge_layout(item.layout())


class AccountDetail(QWidget):
    edit_requested = Signal(str)    # account_id
    delete_requested = Signal(str)  # account_id

    def __init__(self, vault: Vault, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vault = vault
        self._account: Optional[Account] = None
        self._cred_rows: List[_CredentialRow] = []
        self._setup_ui()
        self._show_empty()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(20, 20, 20, 20)
        self._body_layout.setSpacing(12)
        scroll.setWidget(self._body)
        outer.addWidget(scroll)

    def _clear_body(self) -> None:
        self._cred_rows = []
        _purge_layout(self._body_layout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_account(self, account_id: str) -> None:
        try:
            account = self._vault.load_account(account_id)
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            return
        self._account = account
        self._render(account)

    def clear(self) -> None:
        self._account = None
        self._show_empty()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _show_empty(self) -> None:
        self._clear_body()
        placeholder = QLabel("Select an account to view details.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: gray;")
        self._body_layout.addWidget(placeholder)
        self._body_layout.addStretch()

    def _render(self, account: Account) -> None:
        self._clear_body()
        L = self._body_layout

        # Title + action buttons
        title_row = QHBoxLayout()
        title_lbl = QLabel(account.label)
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        title_lbl.setWordWrap(True)
        title_row.addWidget(title_lbl, 1)

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedWidth(60)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(account.id))

        del_btn = QPushButton("Delete")
        del_btn.setFixedWidth(64)
        del_btn.setStyleSheet("color: #c0392b;")
        del_btn.clicked.connect(self._on_delete)

        title_row.addWidget(edit_btn)
        title_row.addWidget(del_btn)
        L.addLayout(title_row)

        L.addWidget(_divider())

        # Flags row
        flags = []
        if account.status == "archived":
            flags.append(("Archived", "#7f8c8d"))
        if account.role_flag:
            colors = {"main": "#2f89c7", "banker": "#2c9b99", "mule": "#4ea660", "utility": "#d58f37"}
            flags.append((account.role_flag.capitalize(), colors.get(account.role_flag, "#555")))
        if account.rotate_flag:
            rc = {"rotate": "#c0392b", "no_rotate": "#27ae60", "shared": "#e67e22"}
            flags.append((account.rotate_flag.replace("_", " ").capitalize(), rc.get(account.rotate_flag, "#555")))

        if flags:
            flag_row = QHBoxLayout()
            flag_row.setSpacing(6)
            for text, color in flags:
                badge = QLabel(text)
                badge.setStyleSheet(
                    f"background-color: {color}; color: white; border-radius: 4px;"
                    " padding: 2px 8px; font-size: 11px;"
                )
                flag_row.addWidget(badge)
            flag_row.addStretch()
            L.addLayout(flag_row)

        # Meta fields
        meta_grid = QVBoxLayout()
        meta_grid.setSpacing(6)
        for field_label, value in (
            ("Owner", account.owner),
            ("Shared by", account.shared_by),
        ):
            if value:
                row = QHBoxLayout()
                lbl = QLabel(f"<b>{field_label}:</b>")
                lbl.setFixedWidth(76)
                val = QLabel(value)
                val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                row.addWidget(lbl)
                row.addWidget(val, 1)
                meta_grid.addLayout(row)
        L.addLayout(meta_grid)

        L.addWidget(_divider())

        # Credentials
        cred_label = QLabel("Credentials")
        cred_label.setStyleSheet("font-weight: bold;")
        L.addWidget(cred_label)

        username_row = QHBoxLayout()
        username_lbl = QLabel("Username:")
        username_lbl.setFixedWidth(76)
        username_val = QLabel(account.username or "(not set)")
        username_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        username_row.addWidget(username_lbl)
        username_row.addWidget(username_val, 1)
        L.addLayout(username_row)

        password_row = _CredentialRow("Password", account.password or "")
        L.addWidget(password_row)
        self._cred_rows.append(password_row)

        # Notes
        if account.notes:
            L.addWidget(_divider())
            notes_title = QLabel("Notes")
            notes_title.setStyleSheet("font-weight: bold;")
            L.addWidget(notes_title)
            notes_lbl = QLabel(account.notes)
            notes_lbl.setWordWrap(True)
            notes_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            notes_lbl.setMaximumHeight(72)
            notes_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            L.addWidget(notes_lbl)

        # Characters
        if account.characters:
            L.addWidget(_divider())
            char_label = QLabel("Characters")
            char_label.setStyleSheet("font-weight: bold;")
            L.addWidget(char_label)

            table = QTableWidget(len(account.characters), 4)
            table.setHorizontalHeaderLabels(["Name", "Class", "Level", "Notes"])
            table.horizontalHeader().setStretchLastSection(True)
            table.verticalHeader().setVisible(False)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
            table.setAlternatingRowColors(True)
            table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            visible_rows = max(len(account.characters), 6)
            visible_rows = min(visible_rows, 8)
            header_height = table.horizontalHeader().height() or 26
            table.setMinimumHeight(header_height + (visible_rows * 26) + 8)
            table.setMaximumHeight(header_height + (8 * 26) + 8)

            for i, ch in enumerate(account.characters):
                table.setItem(i, 0, QTableWidgetItem(ch.name))
                table.setItem(i, 1, QTableWidgetItem(ch.char_class or ""))
                table.setItem(i, 2, QTableWidgetItem(str(ch.level) if ch.level else ""))
                table.setItem(i, 3, QTableWidgetItem(ch.notes or ""))
                table.setRowHeight(i, 24)

            L.addWidget(table)

        # Tags
        if account.tags:
            L.addWidget(_divider())
            tag_row = QHBoxLayout()
            tag_row.setSpacing(6)
            for tag in account.tags:
                badge = QLabel(tag)
                badge.setStyleSheet(
                    "background-color: #34495e; color: white; border-radius: 4px;"
                    " padding: 2px 8px; font-size: 11px;"
                )
                tag_row.addWidget(badge)
            tag_row.addStretch()
            L.addLayout(tag_row)
        L.addStretch()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _on_delete(self) -> None:
        if not self._account:
            return
        reply = QMessageBox.question(
            self,
            "Delete Account",
            f'Delete account "{self._account.label}"?\n\nThis cannot be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._vault.delete_account(self._account.id)
            except Exception as exc:
                QMessageBox.critical(self, "Delete Failed", str(exc))
                return
            self.delete_requested.emit(self._account.id)
            self.clear()

    def force_mask(self) -> None:
        """Called when the panel loses focus or vault locks."""
        for row in self._cred_rows:
            row.force_mask()


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line
