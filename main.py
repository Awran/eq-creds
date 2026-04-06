"""
EQ-Creds entry point.

Application flow:
1. Locate vault db at %APPDATA%\\EQCreds\\vault.db
2. Open the Unlock / Create-Vault dialog
3. On success, show MainWindow
4. Locking from MainWindow shows Unlock dialog again
5. Closing MainWindow exits the app
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from core.vault import Vault
from ui.unlock_window import UnlockWindow
from ui.main_window import MainWindow
from ui.theme import THEME_DARK, normalize_theme, stylesheet_for


def _resource_path(relative_path: str) -> Path:
    """
    Resolve a bundled asset path for both source runs and PyInstaller onefile.
    """
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


def _icon_path() -> Optional[Path]:
    for candidate in ("assets/icon.ico", "assets/EQ-Creds.png", "assets/icon.png"):
        p = _resource_path(candidate)
        if p.exists():
            return p
    return None


def _set_windows_app_id() -> None:
    """Set an explicit AppUserModelID so Windows taskbar/title icon resolves correctly."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("EQCreds.App")
    except Exception:
        # Non-fatal: app still runs if this call fails.
        pass


def _vault_path() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "EQCreds" / "vault.db"


class EQCredsApp(QApplication):
    def __init__(self, argv) -> None:
        super().__init__(argv)
        _set_windows_app_id()
        self.setOrganizationName("EQCreds")
        self.setApplicationName("EQ-Creds")
        self.setApplicationVersion("1.0.1")
        icon_file = _icon_path()
        if icon_file is not None:
            self.setWindowIcon(QIcon(str(icon_file)))
        self._settings = QSettings()
        self._theme = THEME_DARK
        saved_theme = self._settings.value("ui/theme", THEME_DARK)
        self.set_theme(str(saved_theme), persist=False)
        self._vault: Vault | None = None
        self._main_window: MainWindow | None = None

    def current_theme(self) -> str:
        return self._theme

    def set_theme(self, theme: str, persist: bool = True) -> None:
        normalized = normalize_theme(theme)
        self._theme = normalized
        self.setStyleSheet(stylesheet_for(normalized))
        if persist:
            self._settings.setValue("ui/theme", normalized)

    def start(self) -> None:
        db_path = _vault_path()
        try:
            self._vault = Vault(db_path)
        except Exception as exc:
            QMessageBox.critical(None, "Startup Error", f"Could not open vault:\n{exc}")
            sys.exit(1)
        self.show_unlock_window()

    def show_unlock_window(self) -> None:
        if self._main_window:
            self._main_window.hide()

        unlock = UnlockWindow(self._vault)
        unlock.setWindowIcon(self.windowIcon())
        unlock.unlocked.connect(self._on_unlocked)
        # If user closes the unlock dialog, quit the app
        unlock.finished.connect(self._on_unlock_finished)
        unlock.exec()

    def _on_unlocked(self, vault: Vault) -> None:
        if self._main_window is None:
            self._main_window = MainWindow(vault)
        else:
            # Re-use the window but refresh the list after re-unlock
            self._main_window._vault = vault
            self._main_window._refresh_list()
        self._main_window.setWindowIcon(self.windowIcon())
        self._main_window.show()
        self._main_window.raise_()
        self._main_window.activateWindow()

    def _on_unlock_finished(self, result: int) -> None:
        # QDialog.DialogCode.Rejected (0) means closed without unlocking
        if not self._vault.is_unlocked:
            sys.exit(0)


def main() -> None:
    app = EQCredsApp(sys.argv)
    app.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
