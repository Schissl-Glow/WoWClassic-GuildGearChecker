"""Shared checker colors, controls and decorative font for Qt windows."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QFontDatabase


BG = "#0c1015"
PANEL = "#141a21"
PANEL_ALT = "#1a222c"
PANEL_RAISED = "#202a35"
BORDER = "#303b48"
BORDER_SOFT = "#252f3a"
TEXT = "#eef2f5"
MUTED = "#9aa7b4"
GOLD = "#c8a35a"
GOLD_BRIGHT = "#e0bd73"
GREEN = "#477a61"
RED = "#7a4347"
BLUE = "#3d5f7a"


@lru_cache(maxsize=1)
def decorative_font_family() -> str:
    """Register the same LifeCraft font used by the checker header."""
    font_path = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "LifeCraft_Font.ttf"
    if font_path.is_file():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        if families:
            return families[0]
    return "Segoe UI"


LAUNCHER_STYLE_SHEET = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-family: "Segoe UI"; font-size: 10pt; }}
QMainWindow, QDialog {{ background: {BG}; }}
QFrame[card="true"] {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 7px; }}
QFrame[innerCard="true"] {{ background: {PANEL_ALT}; border: 1px solid {BORDER_SOFT}; border-radius: 6px; }}
QPushButton {{
    background: {PANEL_RAISED}; color: {TEXT}; border: 1px solid #394654;
    border-radius: 5px; padding: 7px 12px; font-weight: 600;
}}
QPushButton:hover {{ border-color: #6d7d8e; background: #26323e; }}
QPushButton:pressed {{ background: #111820; }}
QPushButton:disabled {{ color: #68727c; background: #151b22; border-color: #252d35; }}
QPushButton:focus {{ border-color: #c7a265; }}
QPushButton[primary="true"] {{ background: #344e42; border-color: #547762; }}
QPushButton[primary="true"]:hover {{ background: #3c5a4b; border-color: #6e987d; }}
QPushButton[primary="true"]:pressed {{ background: #263b31; border-color: #6e987d; }}
QPushButton[primary="true"]:disabled {{ color: #68727c; background: #151b22; border-color: #252d35; }}
QPushButton[danger="true"] {{ background: #4a2b2e; border-color: #74464a; }}
QPushButton[danger="true"]:hover {{ background: #5a3236; border-color: #9b5b60; }}
QPushButton[danger="true"]:pressed {{ background: #3a2225; border-color: #9b5b60; }}
QLineEdit, QComboBox {{
    background: #10161d; color: {TEXT}; border: 1px solid #35414d;
    border-radius: 5px; padding: 6px; selection-background-color: #302b22;
    selection-color: #f5dfb1;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {GOLD}; }}
QLineEdit:hover, QComboBox:hover {{ border-color: #6b7885; }}
QLineEdit:disabled, QComboBox:disabled {{ color: #68727c; background: #151b22; border-color: #252d35; }}
QComboBox QAbstractItemView {{ background: #171e26; color: {TEXT}; border: 1px solid #3c4855; selection-background-color: #302b22; selection-color: #f5dfb1; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: #10151b; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #3a4652; min-height: 28px; border-radius: 5px; }}
QScrollBar::handle:vertical:hover {{ background: #52606d; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QLabel#launcherTitle {{ color: #f3ead7; background: transparent; }}
QLabel#launcherVersion {{ color: #d0d5da; background: transparent; }}
QLabel#launcherSection {{ color: #f2ede3; background: transparent; font-size: 12pt; font-weight: 600; }}
QLabel#launcherMuted {{ color: {MUTED}; background: transparent; }}
QFrame#guildCard {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 7px; }}
QFrame#guildCard:hover {{ background: #202a35; border-color: #ae8245; }}
QFrame#guildCard[recent="true"] {{ border-color: #80643f; background: #19222c; }}
QFrame#guildCard[recent="true"]:hover {{ border-color: #c7a265; background: #202b36; }}
QFrame#guildCard[missing="true"] {{ border-color: #584238; background: #211d20; }}
QFrame#guildCard[missing="true"]:hover {{ border-color: #80604b; background: #282125; }}
QFrame#guildCard[pressed="true"] {{ background: #111820; border-color: #c7a265; }}
QFrame#guildCard QLabel {{ background: transparent; border: none; }}
QPushButton#cardMenuButton {{
    background: transparent; border: 1px solid transparent; color: {MUTED};
    border-radius: 4px; padding: 0; font-size: 16pt;
}}
QPushButton#cardMenuButton:hover {{ background: #302b22; border-color: #a8884f; color: #f5dfb1; }}
QPushButton#cardMenuButton:pressed {{ background: #1a1e23; border-color: #c7a265; }}
QMenu {{ background: #161d25; color: #e8edf1; border: 1px solid #394450; }}
QMenu::item:selected {{ background: #302b22; color: #f5dfb1; }}
QPushButton#languageButton {{ background: rgba(16,22,29,205); border-color: #394654; padding: 3px 9px; }}
QPushButton#languageButton[active="true"] {{ background: #18212a; border-color: {GOLD}; color: #f3e3c2; }}
QFrame#launcherFooter {{ background: #10161d; border-top: 1px solid {BORDER}; }}
"""
