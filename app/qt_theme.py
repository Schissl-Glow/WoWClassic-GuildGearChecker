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
TABLE_ROW_HOVER = "#332b20"
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


GLOBAL_STYLE_SHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI";
    font-size: 10pt;
}}
QMainWindow, QDialog {{ background: {BG}; }}
QLabel, QFrame {{ color: {TEXT}; }}
QWidget#header {{
    background: transparent;
    border: none;
}}
QWidget#headerIdentity {{ background: transparent; }}
QFrame#navBar {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #26221d, stop:1 #141b22);
    border-top: 1px solid #806744;
    border-bottom: 1px solid #5d4c36;
}}
QPushButton#headerGrabberButton {{
    background: rgba(17, 24, 31, 220);
    color: #eee8dc;
    border: 1px solid #8a7352;
    border-radius: 5px;
    padding: 7px 14px;
}}
QPushButton#headerGrabberButton:hover {{
    background: rgba(32, 39, 42, 235);
    border-color: #c0a06a;
    color: #fff1d6;
}}
QPushButton#headerGrabberButton:pressed {{ background: #151b20; }}
QPushButton#headerGrabberButton:disabled {{
    background: rgba(20, 25, 30, 180);
    color: #89939b;
    border-color: #49535a;
}}
QWidget#rosterToolbarContent {{
    background: #111b25;
    border-top: 1px solid #3d342a;
    border-bottom: 1px solid #34414c;
}}
QScrollArea#rosterToolbarScroll {{ background: #111b25; border: none; }}
QLabel#rosterPageTitle {{
    color: #f2e8d7;
    background: transparent;
    font-size: 15pt;
    font-weight: 600;
}}
QFrame#rosterToolbarDivider {{
    background: #514b43;
    border: none;
}}
QWidget#rosterToolbarContent QLineEdit,
QWidget#rosterToolbarContent QComboBox {{
    background: #0e1821;
    border-color: #45515c;
}}
QWidget#rosterToolbarContent QPushButton#subnavButton[toolbarView="true"] {{
    background: #172431;
    border-color: #3f5060;
    color: #d3dbe0;
}}
QWidget#rosterToolbarContent QPushButton#subnavButton[toolbarView="true"]:hover {{
    background: #26313a;
    border-color: #9e8359;
    color: #f2e6d2;
}}
QWidget#rosterToolbarContent QPushButton#subnavButton[toolbarView="true"]:checked,
QWidget#rosterToolbarContent QPushButton#subnavButton[toolbarView="true"]:checked:hover {{
    background: #1c456a;
    border-color: #a88a59;
    color: #f3ead8;
}}
QWidget#rosterToolbarContent QFrame#rosterZoomBar {{
    background: #13202a;
    border-color: #65573f;
}}
QPushButton#rosterExportButton {{
    background: #1c2934;
    border-color: #746046;
    color: #e9e4d8;
}}
QPushButton#rosterExportButton:hover {{
    background: #293440;
    border-color: #b99b69;
    color: #fff1d8;
}}
QFrame[card="true"] {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 7px;
}}
QFrame[innerCard="true"] {{
    background: {PANEL_ALT};
    border: 1px solid {BORDER_SOFT};
    border-radius: 6px;
}}
QFrame#rosterSection {{
    background: #131922;
    border: 1px solid #5b4930;
    border-radius: 3px;
}}
QFrame#rosterDraftSection {{ background: transparent; border: none; }}
QLabel#rosterSectionTitle {{
    color: #e0bd72;
    background: transparent;
    border: none;
    font-weight: 700;
}}
QLabel#appTitle {{ color: #f2e2bf; font-size: 21pt; font-weight: 600; background: transparent; }}
QLabel#appMeta {{ color: #e0ddd3; font-size: 9pt; background: transparent; }}
QLabel#headerVersion {{ color: #aeb9c1; font-size: 8pt; background: transparent; }}
QLabel#sectionTitle {{ color: #f2ede3; font-size: 15pt; font-weight: 600; }}
QLabel#subtle {{ color: {MUTED}; }}
QLabel#memberName {{ color: #f5ead2; font-size: 18pt; font-weight: 600; }}
QLabel#statusPill {{
    background: #202a34;
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 3px 8px;
    color: #d8e0e7;
}}
QPushButton {{
    background: {PANEL_RAISED};
    color: {TEXT};
    border: 1px solid #394654;
    border-radius: 5px;
    padding: 7px 12px;
    font-weight: 600;
}}
QPushButton:hover {{ border-color: #6d7d8e; background: #26323e; }}
QPushButton:pressed {{ background: #111820; }}
QPushButton:disabled {{ color: #68727c; background: #151b22; border-color: #252d35; }}
QPushButton:focus {{ border-color: #c7a265; }}
QToolButton {{
    background: {PANEL_RAISED}; color: {TEXT}; border: 1px solid #394654;
    border-radius: 5px; padding: 4px 8px; font-weight: 600;
}}
QToolButton:hover {{ background: #26323e; border-color: #6d7d8e; }}
QToolButton:pressed {{ background: #111820; }}
QToolButton:disabled {{ color: #68727c; background: #151b22; border-color: #252d35; }}
QToolButton:focus {{ border-color: #c7a265; }}
QToolButton:checked {{ background: #302b22; border-color: #80643f; color: #f5dfb1; }}
QPushButton[primary="true"] {{ background: #344e42; border-color: #547762; }}
QPushButton[primary="true"]:hover {{ background: #3c5a4b; border-color: #6e987d; }}
QPushButton[primary="true"]:pressed {{ background: #263b31; border-color: #6e987d; }}
QPushButton[primary="true"]:disabled {{ color: #68727c; background: #151b22; border-color: #252d35; }}
QPushButton[danger="true"] {{ background: #4a2b2e; border-color: #74464a; }}
QPushButton[danger="true"]:hover {{ background: #5a3236; border-color: #9b5b60; }}
QPushButton[danger="true"]:pressed {{ background: #3a2225; border-color: #9b5b60; }}
QPushButton[danger="true"]:disabled {{ color: #68727c; background: #151b22; border-color: #252d35; }}
QPushButton[multiSelected="true"] {{ background: #8a5a20; color: #fff0cc; border-color: #e2a340; }}
QPushButton[multiSelected="true"]:hover {{ background: #a06b29; border-color: #f0bc64; }}
QPushButton[multiSelected="true"]:pressed {{ background: #704719; border-color: #f0bc64; }}
QPushButton[multiSelected="true"]:disabled {{ background: #30291f; color: #817a6d; border-color: #544532; }}
QPushButton#viewSwitchButton {{
    min-height: 25px;
    padding: 3px 10px;
    border-radius: 3px;
}}
QPushButton#viewSwitchButton:checked {{
    background: #302b22;
    border-color: #80643f;
    color: #f5dfb1;
    font-weight: 700;
}}
QPushButton#viewSwitchButton:hover {{ background: #292a29; border-color: #9a7a49; }}
QPushButton#viewSwitchButton:checked:hover {{ background: #302b22; border-color: #b9955b; }}
QPushButton#viewSwitchButton:pressed {{ background: #1a1e23; }}
QPushButton#viewSwitchButton:disabled {{ background: #151b22; color: #68727c; border-color: #252d35; }}
QPushButton#navButton {{
    background: transparent;
    border: none;
    border-top: 2px solid transparent;
    border-bottom: 2px solid transparent;
    border-radius: 0px;
    padding: 10px 20px;
    color: #c6c2b8;
    font-family: "Segoe UI";
    font-size: 10pt;
}}
QPushButton#navButton:hover {{ color: #f1dfbd; background: #283039; }}
QPushButton#navButton:checked {{
    color: #f5e7ce;
    border-top-color: #b09462;
    border-bottom-color: #c7a464;
    background: #1c456a;
}}
QPushButton#navButton:checked:hover {{ background: #225073; color: #fff0d3; }}
QPushButton#navButton:focus {{ border-bottom-color: #d4b57a; }}
QPushButton#navButton:disabled {{ color: #737d84; background: transparent; }}
QPushButton#subnavButton {{
    background: #171f28;
    border: 1px solid #2d3844;
    color: #aeb8c2;
    padding: 5px 10px;
}}
QPushButton#subnavButton[v2ManagementTab="true"] {{ padding: 7px 18px; }}
QPushButton#subnavButton:checked {{
    color: #f2e6cf;
    border-color: #806a3d;
    background: #25271f;
}}
QPushButton#subnavButton:hover {{ background: #202d3b; border-color: #536779; color: #e0e9ef; }}
QPushButton#subnavButton:checked:hover {{ background: #25271f; border-color: #a8884f; color: #f2e6cf; }}
QPushButton#subnavButton:pressed {{ background: #151c24; }}
QPushButton#subnavButton:disabled {{ background: #151b22; border-color: #252d35; color: #68727c; }}
QPushButton#subnavButton:focus {{ border-color: #c7a265; }}
QFrame#rosterZoomBar {{
    background: rgba(12, 20, 28, 220);
    border: 1px solid #475c6f;
    border-radius: 5px;
}}
QFrame#rosterZoomBar[modernView="true"] {{ border-color:#80643f; }}
QSlider::groove:horizontal {{
    height: 5px; background: #26313c; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: #8e7442; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: #d4b36b; border: 1px solid #6f5a34; width: 14px; margin: -5px 0; border-radius: 7px;
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
    background: #10161d;
    color: {TEXT};
    border: 1px solid #35414d;
    border-radius: 5px;
    padding: 6px;
    selection-background-color: #302b22;
    selection-color: #f5dfb1;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {GOLD}; }}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QTextEdit:hover, QPlainTextEdit:hover {{ border-color: #6b7885; }}
QLineEdit:focus:hover, QComboBox:focus:hover, QSpinBox:focus:hover, QDoubleSpinBox:focus:hover, QTextEdit:focus:hover, QPlainTextEdit:focus:hover {{ border-color: {GOLD}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{ color: #68727c; background: #151b22; border-color: #252d35; }}
QComboBox QAbstractItemView {{
    background: #171e26;
    color: {TEXT};
    border: 1px solid #3c4855;
    selection-background-color: #302b22;
    selection-color: #f5dfb1;
    padding: 4px;
}}
QComboBox QAbstractItemView::item {{
    min-height: 26px;
    padding: 4px 8px;
}}
QPushButton#detailAction {{
    padding: 4px 8px;
    min-height: 24px;
}}
QCheckBox, QRadioButton {{ spacing: 7px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border: 1px solid #c7a265; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: #80643f; border: 1px solid #c7a265;
}}
QTableWidget::indicator {{ width: 16px; height: 16px; border: 1px solid #59636c; background: #17212a; }}
QTableWidget::indicator:checked {{ background: #80643f; border-color: #c7a265; }}
QTableWidget, QTableView, QTreeView, QListView {{
    background: #11171e;
    alternate-background-color: #141b23;
    border: 1px solid {BORDER};
    gridline-color: #202a34;
    selection-background-color: #302b22;
    selection-color: #f5dfb1;
    outline: 0;
}}
QTableWidget::item, QTableView::item, QTreeView::item, QListView::item {{ padding: 6px; border-bottom: 1px solid #202a34; }}
QTableWidget::item:selected, QTableView::item:selected, QTreeView::item:selected, QListView::item:selected {{ background:#302b22;color:#f5dfb1; }}
QHeaderView::section:hover {{ background: #293542; color: #f1d79f; }}
QHeaderView::section {{
    background: #202830;
    color: #e1c183;
    border: none;
    border-right: 1px solid #584832;
    border-bottom: 1px solid #80643f;
    padding: 7px;
    font-weight: 600;
}}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: #10151b; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #3a4652; min-height: 28px; border-radius: 5px; }}
QScrollBar::handle:vertical:hover {{ background: #52606d; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar:horizontal {{ background: #10151b; height: 12px; }}
QScrollBar::handle:horizontal {{ background: #3a4652; min-width: 28px; border-radius: 5px; }}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background: {PANEL};
    top: -1px;
}}
QTabBar::tab {{
    background: #171f28;
    border: 1px solid #303b47;
    border-top: 2px solid transparent;
    border-bottom: none;
    padding: 8px 13px;
    color: #aeb8c2;
}}
QTabBar::tab:selected {{
    color: #f3e6cd;
    background: #202932;
    border-top-color: {GOLD};
}}
QTabBar::tab:hover {{ background: #202d3b; color: #e0e9ef; }}
QTabBar::tab:selected:hover {{ background: #202932; color: #f3e6cd; }}
QTabBar::tab:disabled {{ background: #151b22; color: #68727c; }}
QSplitter::handle {{ background: #26313c; width: 2px; }}
QStatusBar {{ background: #10161d; color: {MUTED}; border-top: 1px solid #29333e; }}
QMenuBar {{ background: #10161d; color: #dce3e9; }}
QMenuBar::item:selected {{ background: #302b22; color:#f5dfb1; }}
QMenu {{ background: #161d25; color: #e8edf1; border: 1px solid #394450; }}
QMenu::item:selected {{ background: #302b22; color:#f5dfb1; }}
QToolTip {{
    background-color:#171e26;
    color:#e8edf1;
    border:1px solid #80643f;
    padding:4px 6px;
}}

QGroupBox {{
    background: #141a21; color: #eef2f5;
    border: 1px solid #303b48; border-radius: 6px;
    margin-top: 10px; padding-top: 6px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 9px; padding: 0 5px; }}

/* Scoped surfaces kept visually identical to v0.12.1. */
/* QFrame#graveZoomBar */
QFrame#graveZoomBar {{
                background:#151e25;border:1px solid #80643f;border-radius:6px;
            }}
            QFrame#graveZoomBar QLabel {{background:transparent;border:none;color:#e1c183;}}
            QFrame#graveZoomBar QPushButton {{
                background:#202a33;color:#f0dfbf;border:1px solid #584832;
                border-radius:4px;padding:0;font-weight:700;
            }}
            QFrame#graveZoomBar QPushButton:hover {{background:#302b22;border-color:#c7a265;}}
            QFrame#graveZoomBar QPushButton:pressed {{background:#584832;}}
            QFrame#graveZoomBar QPushButton:disabled {{background:#151b22;color:#68727c;border-color:#252d35;}}
            QFrame#graveZoomBar QPushButton:focus {{border-color:#e0bd72;}}
            QFrame#graveZoomBar QSlider::groove:horizontal {{
                height:5px;background:#28323b;border:1px solid #584832;border-radius:2px;
            }}
            QFrame#graveZoomBar QSlider::sub-page:horizontal {{
                background:#80643f;border-radius:2px;
            }}
            QFrame#graveZoomBar QSlider::handle:horizontal {{
                width:14px;margin:-5px 0;background:#e1c183;
                border:1px solid #c7a265;border-radius:7px;
            }}
            QFrame#graveZoomBar QSlider::handle:horizontal:hover {{
                background:#f5dfb1;border-color:#e1c183;
            }}
/* QFrame#rosterClassicCard */
QFrame#rosterClassicCard {{border:1px solid #394654;border-radius:5px;}}
            QFrame#rosterClassicCard:hover {{border-color:#ae8245;}}
            QFrame#rosterClassicCard[selected="true"] {{border-color:#e8c37c;}}
            QFrame#rosterClassicCard[selected="true"]:hover {{border-color:#ffe0a0;}}
            QFrame#rosterClassicCard[pressed="true"] {{border-color:#c99c59;background:#202a34;}}
            QFrame#rosterClassicCard[selected="true"][pressed="true"] {{border-color:#ffe0a0;background:#2d271e;}}
/* QFrame#rosterDraftCard */
QFrame#rosterDraftCard {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1c2831,stop:1 #131a20);
                border:2px solid #514736;border-radius:5px;
            }}
            QFrame#rosterDraftCard:hover {{border-color:#ae8245;background:#263038;}}
            QFrame#rosterDraftCard[selected="true"] {{border-color:#e8c37c;background:#352c20;}}
            QFrame#rosterDraftCard[selected="true"]:hover {{border-color:#ffe0a0;}}
            QFrame#rosterDraftCard[pressed="true"] {{border-color:#c99c59;background:#1d272e;}}
            QFrame#rosterDraftCard[selected="true"][pressed="true"] {{border-color:#ffe0a0;background:#2d271e;}}
            QFrame#rosterDraftCard QLabel {{background:transparent;border:none;}}
/* QDialog#bulkRaidImportDialog */
QDialog#bulkRaidImportDialog QTableWidget::item:selected {{
                background:#302b22;color:#f5dfb1;
            }}
            QDialog#bulkRaidImportDialog QHeaderView::section {{
                background:#202830;color:#e1c183;
                border-right:1px solid #584832;border-bottom:1px solid #80643f;
            }}
            QDialog#bulkRaidImportDialog QListWidget#bulkParticipantList {{
                background:#11171e;alternate-background-color:#141b23;
                border:1px solid #394654;selection-background-color:#302b22;
            }}
            QDialog#bulkRaidImportDialog QListWidget#bulkParticipantList::item {{
                padding:4px 7px;border-bottom:1px solid #202a34;
            }}
            QDialog#bulkRaidImportDialog QCheckBox::indicator:checked {{
                background:#80643f;border:1px solid #c7a265;
            }}
            QDialog#bulkRaidImportDialog QTableWidget QComboBox {{
                background:#10161d;color:#e6e2d8;border:1px solid #584832;
                border-radius:4px;padding:4px 7px;
            }}
            QDialog#bulkRaidImportDialog QTableWidget QComboBox:focus {{
                border-color:#c7a265;
            }}
            QDialog#bulkRaidImportDialog QComboBox QAbstractItemView {{
                background:#171e26;selection-background-color:#302b22;
                selection-color:#f5dfb1;border:1px solid #584832;
            }}
            QDialog#bulkRaidImportDialog QLineEdit:focus,
            QDialog#bulkRaidImportDialog QComboBox:focus {{border-color:#c7a265;}}
/* QWidget#profileLegacy */
QWidget#profileLegacy QTableWidget {{
                selection-background-color:#31485e;selection-color:white;
            }}
            QWidget#profileLegacy QTableWidget::item:selected {{background:#31485e;color:white;}}
            QWidget#profileLegacy QHeaderView::section {{
                background:#1d2630;color:#dce3e9;
                border-right:1px solid #303b47;border-bottom:1px solid #424d59;
            }}
            QWidget#profileLegacy QComboBox QAbstractItemView {{
                selection-background-color:#354b61;selection-color:white;
            }}
/* QWidget#profileDraft */
QWidget#profileDraft {{background:#11181f;}}
            QWidget#profileDraft QWidget {{background:transparent;}}
            QWidget#profileDraft QFrame[card="true"] {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #17212a,stop:1 #11181f);
                border:1px solid #80643f;border-radius:6px;
            }}
            QWidget#profileDraft QLabel {{border:none;}}
            QWidget#profileDraft QLabel#sectionTitle {{color:#e1c183;font-size:13pt;}}
            QWidget#profileDraft QLabel#memberName {{color:#f5dfb1;font-size:23pt;font-weight:700;}}
            QWidget#profileDraft QComboBox {{background:#11181f;border:1px solid #584832;}}
            QWidget#profileDraft QComboBox QAbstractItemView {{background:#17212a;}}
            QWidget#profileDraft QPushButton[family="true"] {{
                background:#151e25;border:1px solid #584832;text-align:left;
                padding:12px 16px;min-width:160px;
            }}
            QWidget#profileDraft QPushButton[family="true"]:hover {{background:#202a33;border-color:#c7a265;}}
            QWidget#profileDraft QPushButton[family="true"]:checked {{background:#302b22;border:2px solid #c7a265;}}
            QWidget#profileDraft QTableWidget {{
                background:#11181f;alternate-background-color:#17212a;border:1px solid #584832;
                selection-background-color:#302b22;selection-color:#f5dfb1;
            }}
            QWidget#profileDraft QTableWidget::item:selected {{background:#302b22;color:#f5dfb1;}}
            QWidget#profileDraft QHeaderView::section {{background:#202830;color:#e1c183;border-color:#584832;}}
/* QFrame#profileCharacterNavigation */
QFrame#profileCharacterNavigation {{
                background:#151e25;border:1px solid #584832;border-radius:5px;
            }}
            QFrame#profileCharacterNavigation QPushButton {{
                background:transparent;color:#e1c183;border:none;border-radius:3px;padding:0;
            }}
            QFrame#profileCharacterNavigation QPushButton:hover {{background:#302b22;color:#f5dfb1;}}
            QFrame#profileCharacterNavigation QPushButton:pressed {{background:#584832;}}
            QFrame#profileCharacterNavigation QPushButton:disabled {{color:#59636c;background:transparent;}}
            QFrame#profileCharacterNavigation QComboBox {{
                background:transparent;color:#f0dfbf;border:none;
                border-left:1px solid #584832;border-right:1px solid #584832;
                border-radius:0;padding:0 10px;
            }}
/* QWidget#managementPage */
QWidget#managementPage {{background:#11181f;}}
            QWidget#managementPage QLabel#sectionTitle {{color:#f5dfb1;background:transparent;}}
            QWidget#managementPage QTableWidget {{
                background:#11181f;alternate-background-color:#17212a;
                border:1px solid #584832;gridline-color:#29333c;
                selection-background-color:#302b22;selection-color:#f5dfb1;
            }}
            QWidget#managementPage QTableWidget::item:selected {{background:#302b22;color:#f5dfb1;}}
            QWidget#managementPage QHeaderView::section {{
                background:#202830;color:#e1c183;
                border-right:1px solid #584832;border-bottom:1px solid #80643f;
            }}
            QWidget#managementPage QPushButton#subnavButton:checked {{
                background:#302b22;border-color:#80643f;color:#f5dfb1;
            }}
/* QFrame#managementCharacterSheet */
QFrame#managementCharacterSheet {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #17212a,stop:1 #11181f);
                border:1px solid #80643f;border-radius:6px;
            }}
            QFrame#managementCharacterSheet QWidget {{background:transparent;}}
            QFrame#managementCharacterSheet QLabel {{border:none;}}
            QFrame#managementCharacterSheet QLabel#memberName {{color:#f5dfb1;font-weight:700;}}
            QFrame#managementCharacterSheet QLabel#subtle {{color:#e1c183;}}
            QFrame#managementCharacterSheet QComboBox,
            QFrame#managementCharacterSheet QTextEdit {{background:#11181f;border:1px solid #584832;}}
            QFrame#managementCharacterSheet QComboBox QAbstractItemView {{background:#17212a;}}
            QFrame#managementCharacterSheet QPushButton {{background:#202a33;border-color:#665338;color:#f0dfbf;}}
            QFrame#managementCharacterSheet QPushButton[primary="true"] {{background:#344e42;border-color:#547762;}}
            QFrame#managementCharacterSheet QPushButton[danger="true"] {{background:#4a2b2e;border-color:#74464a;}}
/* QTableWidget#rosterListTable */
QTableWidget#rosterListTable {{
                selection-background-color:#302b22;selection-color:#f5dfb1;
            }}
            QTableWidget#rosterListTable::item:selected {{
                background:#302b22;color:#f5dfb1;
            }}
/* QFrame#rosterCharacterSheet */
QFrame#rosterCharacterSheet {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #17212a,stop:1 #11181f);
                border:1px solid #80643f;border-radius:6px;
            }}
            QFrame#rosterCharacterSheet QLabel {{background:transparent;border:none;}}
/* QWidget#raidPage */
QWidget#raidPage QTableWidget::item:selected {{
                background:#3b3426;color:#f5dfb1;
            }}
            QWidget#raidPage QHeaderView::section {{
                background:#202830;color:#e1c183;
                border-right:1px solid #584832;border-bottom:1px solid #80643f;
            }}
            QWidget#raidPage QTableWidget {{
                background:#11181f;alternate-background-color:#17212a;
                selection-background-color:#3b3426;selection-color:#f5dfb1;
                gridline-color:#29333c;
            }}
            QWidget#raidPage QFrame#selectedRaidHeader {{
                background:#151e25;border:1px solid #584832;border-radius:5px;
            }}
            QWidget#raidPage QLabel#raidHeaderDate {{color:#aeb8c2;}}
            QWidget#raidPage QLabel#raidHeaderType {{
                color:#e1c183;font-weight:700;padding:3px 8px;
                background:#302b22;border:1px solid #80643f;border-radius:4px;
            }}
            QWidget#raidPage QLabel#raidHeaderName {{
                color:#f5dfb1;font-size:13pt;font-weight:700;
            }}
            QWidget#raidPage QLabel#raidHeaderMeta {{color:#aeb8c2;}}
            QWidget#raidPage QPushButton#raidLogsLink {{
                background:transparent;color:#e1c183;border:1px solid #584832;
                padding:4px 9px;
            }}
            QWidget#raidPage QPushButton#raidLogsLink:hover {{
                background:#302b22;border-color:#c7a265;
            }}
/* QWidget#attendancePage */
QWidget#attendancePage QPushButton#matrixToggleButton {{
                background:#202a33;color:#f0dfbf;border:1px solid #584832;
            }}
            QWidget#attendancePage QPushButton#matrixToggleButton:hover {{
                background:#302b22;border-color:#c7a265;
            }}
            QWidget#attendancePage QPushButton#matrixToggleButton:checked {{
                background:#302b22;border-color:#80643f;color:#f5dfb1;
            }}
            QWidget#attendancePage QSplitter#attendanceMatrixSplit::handle {{
                background:#80643f;width:2px;
            }}
/* QFrame#attendanceViewSwitch */
QFrame#attendanceViewSwitch QPushButton#viewSwitchButton:checked {{
                background:#302b22;border-color:#80643f;color:#f5dfb1;
            }}
            QFrame#attendanceViewSwitch QPushButton#viewSwitchButton:hover {{
                border-color:#c7a265;
            }}
/* QWidget#settingsPage */
QWidget#settingsPage {{ background:#0d1219; }}
            QWidget#settingsPage QLabel {{ background:transparent; border:none; }}
            QWidget#settingsPage QFrame[card="true"] {{
                background:#131922; border:1px solid #5b4930; border-radius:3px;
            }}
            QWidget#settingsPage QPushButton[primary="true"] {{
                background:#302b22; border:1px solid #80643f; color:#f5dfb1;
            }}
            QWidget#settingsPage QPushButton[primary="true"]:hover {{
                background:#3a3325; border-color:#c7a265;
            }}
            QWidget#settingsPage QPushButton[primary="true"]:pressed {{
                background:#211e1a; border-color:#c7a265;
            }}
            QWidget#settingsPage QPushButton[primary="true"]:disabled {{
                background:#151b22; color:#68727c; border-color:#252d35;
            }}
            QWidget#settingsPage QPushButton[primary="true"]:focus {{
                border-color:#e0bd72;
            }}

/* Identity V2 pages and semantic controls. */
/* QWidget#identityV2PlayersPage */
QWidget#identityV2PlayersPage {{background:#11181f;}}
            QWidget#identityV2DetailHost,
            QScrollArea#identityV2DetailScroll {{background:#11181f; border:none;}}
            QWidget#identityV2PlayersPage QGroupBox {{
                color:#e1c183; border:1px solid #584832; margin-top:10px;
                padding-top:8px; font-weight:600;
            }}
            QWidget#identityV2PlayersPage QGroupBox::title {{
                subcontrol-origin:margin; left:10px; padding:0 5px;
            }}
            QWidget#identityV2PlayersPage QListWidget {{
                background:#141c23; alternate-background-color:#19242d;
                border:1px solid #584832;
            }}
            QWidget#identityV2PlayersPage QListWidget::item:selected {{
                background:#302b22; color:#f5dfb1;
            }}
            QWidget#identityV2PlayersPage QTableWidget {{
                background:#11181f; alternate-background-color:#17212a;
                border:1px solid #584832; gridline-color:#29333c;
                selection-background-color:#302b22; selection-color:#f5dfb1;
            }}
            QWidget#identityV2PlayersPage QTableWidget::item:selected {{
                background:#302b22; color:#f5dfb1;
            }}
            QWidget#identityV2PlayersPage QHeaderView::section {{
                background:#202830; color:#e1c183;
                border-right:1px solid #584832; border-bottom:1px solid #80643f;
                padding:4px;
            }}
            QWidget#identityV2PlayersPage QFrame#characterRow {{
                background:#19242d; border:1px solid #394650; border-radius:4px;
            }}
            QWidget#identityV2PlayersPage QFrame#characterRow:hover {{
                background:#222a2d; border-color:#80643f;
            }}
QLabel#v2PlayerRaidPoints, QLabel#v2PlayerEternalPoints {{color:#f5dfb1;font-weight:600;}}
/* QWidget#identityV2CharacterDataPage */
QWidget#identityV2CharacterDataPage {{background:#11181f;}}
            QWidget#identityV2CharacterDataPage QTableWidget {{
                background:#11181f;alternate-background-color:#17212a;
                border:1px solid #584832;gridline-color:#29333c;
                selection-background-color:#302b22;selection-color:#f5dfb1;
            }}
            QWidget#identityV2CharacterDataPage QHeaderView::section {{
                background:#202830;color:#e1c183;
                border-right:1px solid #584832;border-bottom:1px solid #80643f;
                padding:4px;
            }}
            QWidget#identityV2CharacterDataPage QFrame#characterDetail {{
                background:#17212a;border:1px solid #80643f;border-radius:6px;
            }}
/* Destructive character action keeps its existing strong warning. */
QPushButton#markDeadButton {{background:#8b2d35;color:#ffffff;border:1px solid #c9757b;
                         border-radius:4px;padding:6px;font-weight:600;}}
            QPushButton#markDeadButton:hover {{background:#a83a43;}}
            QPushButton#markDeadButton:pressed {{background:#74252c;}}
            QPushButton#markDeadButton:focus {{border-color:#f0a2a7;}}
            QPushButton#markDeadButton:disabled {{background:#292025;color:#86777a;border-color:#544044;}}
QLabel#characterDetailPortrait {{border:1px solid #584832;background:#11181f;}}
QLabel#characterDetailName {{color:#f5dfb1;font-weight:700;}}

/* Status roles preserve the existing Roster and Raid meanings. */
QLabel[rosterStatus="positive"], QLabel#statusPill[rosterStatus="positive"] {{background:#203d2c;color:#e0eee1;border:1px solid #6e9c78;border-radius:7px;padding:3px 7px;font-size:9pt;}}
QLabel[rosterStatus="negative"], QLabel#statusPill[rosterStatus="negative"] {{background:#45292e;color:#f0d9dc;border:1px solid #aa6b70;border-radius:7px;padding:3px 7px;font-size:9pt;}}
QLabel[rosterStatus="warning"], QLabel#statusPill[rosterStatus="warning"] {{background:#46371f;color:#f4e3bc;border:1px solid #af8c50;border-radius:7px;padding:3px 7px;font-size:9pt;}}
QLabel[rosterStatus="neutral"], QLabel#statusPill[rosterStatus="neutral"] {{background:#202a33;color:#ccd2d7;border:1px solid #59636c;border-radius:7px;padding:3px 7px;font-size:9pt;}}
QLabel#statusPill[classicRaidStatus="positive"] {{background:#355f45;}}
QLabel#statusPill[classicRaidStatus="negative"] {{background:#633b40;}}
QLabel#raidHeaderMeta[raidRecordStatus="recorded"] {{color:#8ec79a;}}
QLabel#raidHeaderMeta[raidRecordStatus="draft"] {{color:#e1c183;}}

/* Roster components. */

QWidget#rosterNameplate {{background:#211c17;border:none;}}
QLabel#rosterDraftName {{color:#f5e2ba;font-size:11pt;font-weight:700;}}
QLabel#rosterDraftSecondary {{color:#a9b1b9;font-size:9pt;}}
QTextEdit#rosterDetailNotes {{background:#10161d;border:1px solid #35414d;color:#eef2f5;}}
QFrame#rosterCharacterSheet QLabel#memberName {{font-size:20pt;font-weight:700;color:#f5dfb1;}}
QFrame#rosterPointsSection {{background:#151e25;border:1px solid #584832;border-radius:5px;}}
QLabel#rosterDetailRank {{font-size:12pt;color:#e1c183;font-weight:600;}}
QPushButton#rosterProfileButton {{background:#594322;border:1px solid #bc9455;color:#ffedca;padding:7px;}}
QPushButton#rosterProfileButton:disabled,QPushButton#rosterProfileButton:disabled:hover {{background:#151b22;border:1px solid #252d35;color:#68727c;}}
"""

# The launcher adds only its own named surfaces and controls.
LAUNCHER_STYLE_SHEET = GLOBAL_STYLE_SHEET + f"""
QLabel#launcherSeparator {{ background:transparent;color:#d0d5da; }}
QLabel#launcherMode {{ color:#e1c183;background:transparent; }}
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
