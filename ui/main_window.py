"""
Main application window.

Layout:
  [toolbar: search | New Account | Lock | Settings]
  [account list (left, ~280px) | account detail panel (right, expanding)]

The account list is a simple QListWidget with one row per account.
Each row stores the account id as UserRole data.
Live search filters the list as you type.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.models import Account
from core.vault import Vault
from ui.account_detail import AccountDetail
from ui.account_form import AccountForm

class MainWindow(QMainWindow):
    def __init__(self, vault: Vault) -> None:
        super().__init__()
        self._vault = vault
        self._accounts: List[Account] = []
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)  # debounce ms
        self._search_timer.timeout.connect(self._run_search)
        self._setup_ui()
        self._refresh_list()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowTitle("EQ-Creds")
        self.setMinimumSize(820, 560)
        self.resize(1020, 680)

        # --- Toolbar ---
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)

        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(4, 0, 4, 0)
        search_layout.setSpacing(4)

        search_icon = QLabel("🔍")
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search accounts, characters, tags…")
        self._search_edit.setMinimumWidth(260)
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search_changed)

        search_layout.addWidget(search_icon)
        search_layout.addWidget(self._search_edit)
        toolbar.addWidget(search_container)

        toolbar.addSeparator()

        new_btn = QPushButton("+ New Account")
        new_btn.clicked.connect(self._on_new_account)
        toolbar.addWidget(new_btn)

        toolbar.addSeparator()

        lock_btn = QPushButton("🔒 Lock")
        lock_btn.clicked.connect(self._on_lock)
        toolbar.addWidget(lock_btn)

        settings_btn = QPushButton("⚙ Settings")
        settings_btn.clicked.connect(self._on_settings)
        toolbar.addWidget(settings_btn)

        # --- Central widget: splitter ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left: account list
        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)

        self._count_label = QLabel("0 accounts")
        self._count_label.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        list_layout.addWidget(self._count_label)

        self._list_widget = QListWidget()
        self._list_widget.setAlternatingRowColors(False)
        self._list_widget.currentItemChanged.connect(self._on_selection_changed)
        list_layout.addWidget(self._list_widget, 1)

        splitter.addWidget(list_panel)

        # Right: detail panel
        self._detail = AccountDetail(self._vault)
        self._detail.edit_requested.connect(self._on_edit_account)
        self._detail.delete_requested.connect(self._on_account_deleted)
        splitter.addWidget(self._detail)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 740])

        self.setCentralWidget(splitter)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

    # ------------------------------------------------------------------
    # Account list population
    # ------------------------------------------------------------------

    def _refresh_list(self, query: str = "") -> None:
        self._accounts = self._vault.list_accounts(query)
        self._list_widget.clear()

        for account in self._accounts:
            display = account.label

            # Build subtitle: first character names
            char_names = [ch.name for ch in account.characters]
            if char_names:
                chars_str = ", ".join(char_names[:3])
                if len(char_names) > 3:
                    chars_str += f" +{len(char_names) - 3}"
                display = f"{account.label}\n{chars_str}"

            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, account.id)

            # Dim archived accounts
            if account.status == "archived":
                item.setForeground(QColor("#999"))

            # Tooltip: tags + owner
            tooltip_parts = []
            if account.owner:
                tooltip_parts.append(f"Owner: {account.owner}")
            if account.shared_by:
                tooltip_parts.append(f"Shared by: {account.shared_by}")
            if account.role_flag:
                tooltip_parts.append(f"Role: {account.role_flag.capitalize()}")
            if account.tags:
                tooltip_parts.append("Tags: " + ", ".join(account.tags))
            if tooltip_parts:
                item.setToolTip("\n".join(tooltip_parts))

            self._list_widget.addItem(item)

        count = len(self._accounts)
        self._count_label.setText(f"{count} account{'s' if count != 1 else ''}")

    def _select_account(self, account_id: str) -> None:
        """Re-select a list item after a refresh."""
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == account_id:
                self._list_widget.setCurrentItem(item)
                return

    # ------------------------------------------------------------------
    # Signals / slots
    # ------------------------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        self._search_timer.start()

    def _run_search(self) -> None:
        query = self._search_edit.text().strip()
        self._refresh_list(query)
        self._detail.clear()

    def _on_selection_changed(self, current: QListWidgetItem, _previous) -> None:
        if current is None:
            self._detail.clear()
            return
        account_id = current.data(Qt.ItemDataRole.UserRole)
        if account_id:
            self._detail.show_account(account_id)

    def _on_new_account(self) -> None:
        form = AccountForm(self._vault, parent=self)
        form.saved.connect(self._on_account_saved)
        form.exec()

    def _on_edit_account(self, account_id: str) -> None:
        try:
            account = self._vault.load_account(account_id)
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            return
        form = AccountForm(self._vault, account=account, parent=self)
        form.saved.connect(self._on_account_saved)
        form.exec()

    def _on_account_saved(self, account: Account) -> None:
        query = self._search_edit.text().strip()
        self._refresh_list(query)
        self._select_account(account.id)
        self._detail.show_account(account.id)
        self._status_bar.showMessage(f"Saved: {account.label}", 3000)

    def _on_account_deleted(self, account_id: str) -> None:
        query = self._search_edit.text().strip()
        self._refresh_list(query)
        self._status_bar.showMessage("Account deleted.", 3000)

    def _on_lock(self) -> None:
        self._detail.force_mask()
        self._vault.lock()
        self.close()
        # main.py will detect the locked state and show unlock window again
        QApplication.instance().show_unlock_window()  # type: ignore[attr-defined]

    def _on_settings(self) -> None:
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self._vault, parent=self)
        dlg.exec()

    def closeEvent(self, event) -> None:
        self._detail.force_mask()
        self._vault.lock()
        event.accept()
