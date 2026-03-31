from __future__ import annotations

THEME_DARK = "dark"
THEME_LIGHT = "light"


def normalize_theme(value: str | None) -> str:
    if value == THEME_LIGHT:
        return THEME_LIGHT
    return THEME_DARK


def stylesheet_for(theme: str) -> str:
    """Return stylesheet text for the selected app theme."""
    theme = normalize_theme(theme)
    if theme == THEME_LIGHT:
        return _light_stylesheet()
    return _dark_stylesheet()


def _dark_stylesheet() -> str:
    return """
QWidget {
    background-color: #181a1f;
    color: #e9edf3;
    selection-background-color: #1f4f78;
    selection-color: #ffffff;
    font-size: 10.5pt;
}

QMainWindow, QDialog {
    background-color: #181a1f;
}

QToolBar {
    background-color: #20242b;
    border: 1px solid #2b313a;
    spacing: 6px;
}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {
    background-color: #232831;
    color: #f2f6fb;
    border: 1px solid #3a4351;
    border-radius: 4px;
    padding: 4px 6px;
}

QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #3a84c9;
}

QPushButton {
    background-color: #2a313c;
    color: #f2f6fb;
    border: 1px solid #3c4a5c;
    border-radius: 4px;
    padding: 4px 10px;
}

QPushButton:hover {
    background-color: #323b47;
}

QPushButton:pressed {
    background-color: #25303b;
}

QPushButton:disabled {
    color: #8c96a8;
    background-color: #222730;
}

QListWidget {
    background-color: #20242b;
    border: 1px solid #2f3642;
    outline: 0;
}

QListWidget::item {
    padding: 6px;
    border-bottom: 1px solid #2a3038;
    background-color: #20242b;
    color: #dde3ee;
}

QListWidget::item:hover {
    background: #28303a;
}

QListWidget::item:selected {
    background: #1f4f78;
    color: #ffffff;
}

QTableWidget {
    background-color: #20242b;
    alternate-background-color: #252b35;
    gridline-color: #353d49;
    border: 1px solid #2f3642;
    color: #e9edf3;
}

QHeaderView::section {
    background-color: #2b313a;
    color: #f2f6fb;
    border: 0;
    border-right: 1px solid #39414d;
    border-bottom: 1px solid #39414d;
    padding: 4px;
}

QStatusBar {
    background-color: #20242b;
    color: #cfd7e4;
    border-top: 1px solid #2f3642;
}

QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: #39414d;
}
"""


def _light_stylesheet() -> str:
    return """
QWidget {
    background-color: #f3f5f8;
    color: #1f2530;
    selection-background-color: #2d6ea3;
    selection-color: #ffffff;
    font-size: 10.5pt;
}

QMainWindow, QDialog {
    background-color: #f3f5f8;
}

QToolBar {
    background-color: #e8ecf1;
    border: 1px solid #c8d1dc;
    spacing: 6px;
}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {
    background-color: #ffffff;
    color: #1f2530;
    border: 1px solid #b7c3d1;
    border-radius: 4px;
    padding: 4px 6px;
}

QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #2d6ea3;
}

QPushButton {
    background-color: #f8fafc;
    color: #1f2530;
    border: 1px solid #b7c3d1;
    border-radius: 4px;
    padding: 4px 10px;
}

QPushButton:hover {
    background-color: #edf2f7;
}

QPushButton:pressed {
    background-color: #dde6ef;
}

QPushButton:disabled {
    color: #8a94a3;
    background-color: #eef2f7;
}

QListWidget {
    background-color: #ffffff;
    border: 1px solid #c3ccd8;
    outline: 0;
}

QListWidget::item {
    padding: 6px;
    border-bottom: 1px solid #e3e8ef;
    background-color: #ffffff;
    color: #1f2530;
}

QListWidget::item:hover {
    background: #e8f0f8;
}

QListWidget::item:selected {
    background: #2d6ea3;
    color: #ffffff;
}

QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f7f9fc;
    gridline-color: #d5dde8;
    border: 1px solid #c3ccd8;
    color: #1f2530;
}

QHeaderView::section {
    background-color: #e8ecf1;
    color: #1f2530;
    border: 0;
    border-right: 1px solid #cfd8e3;
    border-bottom: 1px solid #cfd8e3;
    padding: 4px;
}

QStatusBar {
    background-color: #e8ecf1;
    color: #3b4655;
    border-top: 1px solid #c8d1dc;
}

QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: #c9d2de;
}
"""
