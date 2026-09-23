# -*- coding: utf-8 -*-
"""Guild Gear Checker - PySide6 migration preview.

This module deliberately reuses the established domain/data logic from
``GuildGearChecker.py`` and replaces only the desktop UI layer.  The legacy
Tkinter checker remains included as a fallback while the Qt migration is
validated locally.

Version: 0.8.0-qt-preview.14
"""
from __future__ import annotations

import copy
import html
import json
import os
import shutil
import subprocess
import sys
import unicodedata
import webbrowser
from dataclasses import replace
from datetime import datetime
from math import sqrt
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from app.GuildGearChecker import (
        APP_NAME,
        APP_VERSION,
        RAID_CATEGORIES,
        RAID_TYPES,
        CHARACTER_TYPES,
        CLASS_COLORS,
        CLASS_NAMES,
        CLASS_SPECS,
        RAID_STATUS_VALUES,
        GEAR_OUTDATED_DEFAULT_DAYS,
        GEAR_VALUES,
        GRAVESTONE_CARD_SIZE,
        GRAVESTONE_EDITOR_SIZE,
        GRAVESTONE_GRID_GAP,
        GRAVESTONE_GRID_PADDING,
        GRAVESTONE_HEADER_BOTTOM,
        GRAVESTONE_PORTRAIT_ZOOM_RANGE,
        GRAVESTONE_TEXT_SCALE_RANGE,
        RAID_ROLES,
        ROSTER_ROLE_ORDER,
        GuildModel,
        MainConflictError,
        Member,
        ProjectPackageError,
        app_base_dir,
        build_armory_url,
        calculate_statistics,
        character_type_display,
        character_type_from_display,
        class_icon_path,
        create_project_package,
        import_project_package,
        default_sort_for_tab,
        enchant_status_display,
        enchant_status_from_display,
        enchant_status_key,
        filter_and_sort_members,
        gear_status_display,
        gear_status_from_display,
        gear_status_key,
        get_language,
        gravestone_background_path,
        gravestone_placeholder_path,
        gravestone_template_folder,
        group_roster_members,
        language_display_values,
        language_from_display,
        member_check_is_outdated,
        normalize_class_name,
        normalize_csv_raid_type,
        normalize_iso_date,
        normalize_outdated_days,
        normalize_portrait_offset,
        normalize_portrait_zoom,
        normalize_spec,
        normalize_text_offset,
        normalize_text_scale,
        shifted_portrait_offsets,
        shifted_text_offsets,
        detect_gravestone_portrait_opening,
        prepare_gravestone_template,
        project_package_default_filename,
        player_is_relevant,
        race_display,
        race_display_values,
        race_from_display,
        raid_error_text,
        raid_role_display,
        raid_role_from_display,
        raid_status_display,
        raid_status_from_display,
        read_csv_names,
        read_raid_csv,
        render_gravestone_card,
        render_roster_png,
        sanitize_filename,
        set_language,
        shared_portrait_folder,
        today_iso,
        tr,
        update_suite_settings,
        validate_logs_url,
        read_suite_settings,
        raid_table_sort_value,
        POINT_MODE_ETERNAL,
        POINT_MODE_RAID,
    )
except ImportError:
    from GuildGearChecker import (  # type: ignore
        APP_NAME,
        APP_VERSION,
        RAID_CATEGORIES,
        RAID_TYPES,
        CHARACTER_TYPES,
        CLASS_COLORS,
        CLASS_NAMES,
        CLASS_SPECS,
        RAID_STATUS_VALUES,
        GEAR_OUTDATED_DEFAULT_DAYS,
        GEAR_VALUES,
        GRAVESTONE_CARD_SIZE,
        GRAVESTONE_EDITOR_SIZE,
        GRAVESTONE_GRID_GAP,
        GRAVESTONE_GRID_PADDING,
        GRAVESTONE_HEADER_BOTTOM,
        GRAVESTONE_PORTRAIT_ZOOM_RANGE,
        GRAVESTONE_TEXT_SCALE_RANGE,
        RAID_ROLES,
        ROSTER_ROLE_ORDER,
        GuildModel,
        MainConflictError,
        Member,
        ProjectPackageError,
        app_base_dir,
        build_armory_url,
        calculate_statistics,
        character_type_display,
        character_type_from_display,
        class_icon_path,
        create_project_package,
        import_project_package,
        default_sort_for_tab,
        enchant_status_display,
        enchant_status_from_display,
        enchant_status_key,
        filter_and_sort_members,
        gear_status_display,
        gear_status_from_display,
        gear_status_key,
        get_language,
        gravestone_background_path,
        gravestone_placeholder_path,
        gravestone_template_folder,
        group_roster_members,
        language_display_values,
        language_from_display,
        member_check_is_outdated,
        normalize_class_name,
        normalize_csv_raid_type,
        normalize_iso_date,
        normalize_outdated_days,
        normalize_portrait_offset,
        normalize_portrait_zoom,
        normalize_spec,
        normalize_text_offset,
        normalize_text_scale,
        shifted_portrait_offsets,
        shifted_text_offsets,
        detect_gravestone_portrait_opening,
        prepare_gravestone_template,
        project_package_default_filename,
        player_is_relevant,
        race_display,
        race_display_values,
        race_from_display,
        raid_error_text,
        raid_role_display,
        raid_role_from_display,
        raid_status_display,
        raid_status_from_display,
        read_csv_names,
        read_raid_csv,
        render_gravestone_card,
        render_roster_png,
        sanitize_filename,
        set_language,
        shared_portrait_folder,
        today_iso,
        tr,
        update_suite_settings,
        validate_logs_url,
        read_suite_settings,
        raid_table_sort_value,
        POINT_MODE_ETERNAL,
        POINT_MODE_RAID,
    )

try:
    from app.project_storage import (
        atomic_write_bytes, autosave_path, copy_project_portraits,
        member_portrait_path as stored_member_portrait_path,
        migrate_legacy_portraits,
        newer_autosave, portrait_root as project_portrait_root,
    )
except ImportError:
    from project_storage import (  # type: ignore
        atomic_write_bytes, autosave_path, copy_project_portraits,
        member_portrait_path as stored_member_portrait_path,
        migrate_legacy_portraits,
        newer_autosave, portrait_root as project_portrait_root,
    )

try:
    from app.project_handoff import (
        apply_actions, new_session_id, pending_actions, write_receipt,
    )
except ImportError:
    from project_handoff import (  # type: ignore
        apply_actions, new_session_id, pending_actions, write_receipt,
    )

try:
    from app.clm_models import ClmRosterSelectionRequired
    from app.clm_matching import character_key, match_characters
    from app.clm_refresh import ClmDkpRefreshService
    from app.clm_history_sync import analyze_clm_raid_history, apply_clm_raid_history
    from app.player_merge import (
        PlayerMergeConflictError, apply_player_merge, plan_player_merge,
    )
    from app.raid_points import base_points_for_status, build_point_history
    from app.raid_attendance import exact_name_key
    from app.rewards import (
        FrameOpeningRect, RewardAssignments, RewardRegistry, active_reward_thresholds,
        eternal_dkp_reward_thresholds,
        build_reward_assignments,
    )
    from app.player_profile import (
        PlayerProfileViewModel, active_player_options, build_player_profile,
    )
except ImportError:
    from clm_models import ClmRosterSelectionRequired  # type: ignore
    from clm_matching import character_key, match_characters  # type: ignore
    from clm_refresh import ClmDkpRefreshService  # type: ignore
    from clm_history_sync import analyze_clm_raid_history, apply_clm_raid_history  # type: ignore
    from player_merge import (  # type: ignore
        PlayerMergeConflictError, apply_player_merge, plan_player_merge,
    )
    from raid_points import base_points_for_status, build_point_history  # type: ignore
    from raid_attendance import exact_name_key  # type: ignore
    from rewards import (  # type: ignore
        FrameOpeningRect, RewardAssignments, RewardRegistry, active_reward_thresholds,
        eternal_dkp_reward_thresholds,
        build_reward_assignments,
    )
    from player_profile import (  # type: ignore
        PlayerProfileViewModel, active_player_options, build_player_profile,
    )

QT_PREVIEW_VERSION = "0.11.3-test3"
CHECKER_BANNER_HEIGHT = 200
CHECKER_BANNER_FOCAL_POINT = (0.55, 0.0)
CHECKER_BANNER_OVERLAY_ALPHA = 56  # ~22 %, matching the legacy banner darkening
MEMBER_DETAIL_PORTRAIT_SIZE = 124
MEMBER_DETAIL_TABS_MIN_HEIGHT = 205
MEMBER_DETAIL_SCROLL_HEIGHT_TOLERANCE = 64
RAID_MATRIX_HEADER_HEIGHT = 48
RAID_MATRIX_ROW_HEIGHT = 32
RAID_MATRIX_BACKGROUND_ROLE = int(Qt.ItemDataRole.UserRole) + 101
RAID_ATTENDANCE_FIXED_COLUMNS = 10

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

CLASS_DISPLAY_KEYS = {
    "Druid": "druid", "Hunter": "hunter", "Mage": "mage",
    "Paladin": "paladin", "Priest": "priest", "Rogue": "rogue",
    "Shaman": "shaman", "Warlock": "warlock", "Warrior": "warrior",
}


def profile_class_display(value: object) -> str:
    normalized = normalize_class_name(str(value or ""))
    key = CLASS_DISPLAY_KEYS.get(normalized)
    return tr(f"classes.{key}") if key else normalized


STYLE_SHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI";
    font-size: 10pt;
}}
QMainWindow {{ background: {BG}; }}
QWidget#header {{
    background: transparent;
    border-bottom: 1px solid #6d5934;
}}
QFrame#navBar {{
    background: #10161d;
    border-bottom: 1px solid {BORDER};
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
QLabel#rosterSectionTitle {{
    color: #e0bd72;
    background: transparent;
    border: none;
    font-weight: 700;
}}
QLabel#appTitle {{ color: #f3ead7; font-size: 24pt; font-weight: 600; background: transparent; }}
QLabel#appMeta {{ color: #d0d5da; font-size: 9pt; background: transparent; }}
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
QPushButton[primary="true"] {{ background: #344e42; border-color: #547762; }}
QPushButton[primary="true"]:hover {{ background: #3c5a4b; border-color: #6e987d; }}
QPushButton[danger="true"] {{ background: #4a2b2e; border-color: #74464a; }}
QPushButton[danger="true"]:hover {{ background: #5a3236; border-color: #9b5b60; }}
QPushButton#viewSwitchButton {{
    min-height: 25px;
    padding: 3px 10px;
    border-radius: 3px;
}}
QPushButton#viewSwitchButton:checked {{
    background: #4b6177;
    border-color: #7b94ad;
    color: #ffffff;
    font-weight: 700;
}}
QPushButton#navButton {{
    background: transparent;
    border: none;
    border-bottom: 3px solid transparent;
    border-radius: 0px;
    padding: 11px 18px 9px 18px;
    color: #aeb8c2;
    font-size: 10pt;
}}
QPushButton#navButton:hover {{ color: #f0e5cf; background: #151d26; }}
QPushButton#navButton:checked {{
    color: #f3e3c2;
    border-bottom-color: {GOLD};
    background: #18212a;
}}
QPushButton#subnavButton {{
    background: #171f28;
    border: 1px solid #2d3844;
    color: #aeb8c2;
    padding: 5px 10px;
}}
QPushButton#subnavButton:checked {{
    color: #f2e6cf;
    border-color: #806a3d;
    background: #25271f;
}}
QFrame#graveZoomBar {{
    background: rgba(12, 20, 28, 220);
    border: 1px solid #475c6f;
    border-radius: 5px;
}}
QSlider::groove:horizontal {{
    height: 5px; background: #26313c; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: #8e7442; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: #d4b36b; border: 1px solid #6f5a34; width: 14px; margin: -5px 0; border-radius: 7px;
}}
QLineEdit, QComboBox, QSpinBox, QTextEdit {{
    background: #10161d;
    color: {TEXT};
    border: 1px solid #35414d;
    border-radius: 5px;
    padding: 6px;
    selection-background-color: #496681;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {{ border-color: {GOLD}; }}
QComboBox QAbstractItemView {{
    background: #171e26;
    color: {TEXT};
    border: 1px solid #3c4855;
    selection-background-color: #354b61;
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
QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QTableWidget {{
    background: #11171e;
    alternate-background-color: #141b23;
    border: 1px solid {BORDER};
    gridline-color: #202a34;
    selection-background-color: #31485e;
    selection-color: white;
    outline: 0;
}}
QTableWidget::item {{ padding: 6px; border-bottom: 1px solid #202a34; }}
QHeaderView::section {{
    background: #1d2630;
    color: #dce3e9;
    border: none;
    border-right: 1px solid #303b47;
    border-bottom: 1px solid #424d59;
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
    border-bottom: none;
    padding: 8px 13px;
    color: #aeb8c2;
}}
QTabBar::tab:selected {{
    color: #f3e6cd;
    background: #202932;
    border-top: 2px solid {GOLD};
}}
QSplitter::handle {{ background: #26313c; width: 2px; }}
QStatusBar {{ background: #10161d; color: {MUTED}; border-top: 1px solid #29333e; }}
QMenuBar {{ background: #10161d; color: #dce3e9; }}
QMenuBar::item:selected {{ background: #25313d; }}
QMenu {{ background: #161d25; color: #e8edf1; border: 1px solid #394450; }}
QMenu::item:selected {{ background: #304559; }}
"""


def set_button_role(button: QPushButton, *, primary: bool = False, danger: bool = False) -> QPushButton:
    if primary:
        button.setProperty("primary", True)
    if danger:
        button.setProperty("danger", True)
    return button


def pil_to_pixmap(image) -> QPixmap:
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QImage(data, rgba.width, rgba.height, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimage)


def safe_open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        os.system(f'open "{path}"')
    else:
        os.system(f'xdg-open "{path}" >/dev/null 2>&1 &')


def member_portrait_candidates(model: GuildModel, member: Member) -> Iterable[Path]:
    if model.project_path is None:
        return
    yield stored_member_portrait_path(model.project_path, member.id)


def member_portrait_path(model: GuildModel, member: Member) -> Path | None:
    return next((path for path in member_portrait_candidates(model, member) if path.is_file()), None)


def graveyard_member_portrait_path(model: GuildModel, member: Member) -> Path | None:
    """Use the current graveyard-only placeholder after real portrait lookup."""
    portrait = member_portrait_path(model, member)
    if portrait is not None:
        return portrait
    if member.lifeStatus == "dead":
        placeholder = app_base_dir() / "assets" / "graveyard" / "portrait_placeholder.png"
        if placeholder.is_file():
            return placeholder
    return None


def archive_portrait(model: GuildModel, member: Member) -> Path | None:
    if model.project_path is None:
        return None
    portrait = stored_member_portrait_path(model.project_path, member.id)
    return portrait if portrait.is_file() else None


class HeaderWidget(QWidget):
    """Fokussiertes, entprelltes Banner-Cover wie im Qt-Portrait-Grabber."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("header")
        self._source = QPixmap(str(app_base_dir() / "assets" / "checker_banner.png"))
        self.setMinimumHeight(150)
        self.setFixedHeight(CHECKER_BANNER_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._rendered = QPixmap()
        self._rendered_size = QSize()
        self._pending_size = QSize()
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(60)
        self._resize_timer.timeout.connect(self._render_cover)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._pending_size = event.size()
        self._resize_timer.start()

    def _render_cover(self) -> None:
        target = self._pending_size
        if target.width() < 2 or target.height() < 2 or self._source.isNull():
            return
        if target == self._rendered_size:
            return
        source_size = self._source.size()
        scale = max(
            target.width() / source_size.width(),
            target.height() / source_size.height(),
        )
        scaled_size = QSize(
            max(1, round(source_size.width() * scale)),
            max(1, round(source_size.height() * scale)),
        )
        scaled = self._source.scaled(
            scaled_size,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        left = -round((scaled.width() - target.width()) * CHECKER_BANNER_FOCAL_POINT[0])
        top = -round((scaled.height() - target.height()) * CHECKER_BANNER_FOCAL_POINT[1])
        rendered = QPixmap(target)
        rendered.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rendered)
        painter.drawPixmap(left, top, scaled)
        painter.end()
        self._rendered = rendered
        self._rendered_size = target
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()
        if not self._rendered.isNull():
            # Zwischen Resize-Events bleibt das zuletzt passende, unverzerrte
            # Cover sichtbar, bis der entprellte Cache ersetzt wird.
            painter.drawPixmap(0, 0, self._rendered)
            # Keep text readable without changing the source image itself.
            painter.fillRect(rect, QColor(16, 20, 25, CHECKER_BANNER_OVERLAY_ALPHA))
        else:
            # Graceful fallback if the optional banner asset is missing.
            from PySide6.QtGui import QLinearGradient
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.0, QColor("#111922"))
            gradient.setColorAt(0.55, QColor("#17212b"))
            gradient.setColorAt(1.0, QColor("#0d1218"))
            painter.fillRect(rect, gradient)
        painter.setPen(QPen(QColor("#715d39"), 1))
        painter.drawLine(0, rect.height() - 1, rect.width(), rect.height() - 1)
        painter.end()


class CoverImageLabel(QLabel):
    """QLabel-like image surface that always uses cover cropping."""

    clicked = Signal()

    def __init__(self, placeholder: str = "No portrait", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source = QPixmap()
        self._placeholder = placeholder
        self.setMinimumSize(120, 120)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(
            "background:#0e1319; border:1px solid #4a5662; border-radius:5px; color:#6f7b86;"
        )

    def set_source(self, path: Path | None) -> None:
        pixmap = QPixmap(str(path)) if path and path.is_file() else QPixmap()
        self._source = pixmap
        self.update()

    def set_pixmap_source(self, pixmap: QPixmap) -> None:
        self._source = QPixmap(pixmap)
        self.update()

    def clear_source(self) -> None:
        self._source = QPixmap()
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.contentsRect()
        painter.fillRect(rect, QColor("#0e1319"))
        if not self._source.isNull() and rect.width() > 0 and rect.height() > 0:
            scaled = self._source.scaled(
                rect.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = max(0, (scaled.width() - rect.width()) // 2)
            y = max(0, (scaled.height() - rect.height()) // 2)
            source_rect = QRect(x, y, rect.width(), rect.height())
            painter.drawPixmap(rect, scaled, source_rect)
        else:
            painter.setPen(QColor("#6f7b86"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._placeholder)
        painter.setPen(QPen(QColor("#4a5662"), 1))
        painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 5, 5)
        painter.end()


class RewardPortraitContainer(QWidget):
    """Separates Innenportrait mit äußerem Reward-Rahmen und Innen-Badge."""

    def __init__(
        self,
        portrait: CoverImageLabel,
        portrait_size: QSize,
        *,
        rank_asset_size: int = 48,
    ) -> None:
        super().__init__()
        self.portrait = portrait
        self.rank_asset_size = 96 if rank_asset_size == 96 else 48
        self.portrait.setParent(self)
        self._plain_portrait_size = QSize(portrait_size)
        self._frame_source = QPixmap()
        self._frame_opening: FrameOpeningRect | None = None
        self._badge_source = QPixmap()
        self._frame = QLabel(self)
        self._badge = QLabel(self)
        for overlay in (self._frame, self._badge):
            overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            overlay.setStyleSheet("background:transparent; border:none;")
            overlay.hide()
        self._apply_geometry()

    def set_reward_frame(
        self,
        path: Path | None,
        opening: FrameOpeningRect | None = None,
    ) -> None:
        self._frame_source = QPixmap(str(path)) if path and path.is_file() else QPixmap()
        self._frame_opening = opening if not self._frame_source.isNull() else None
        self._apply_geometry()

    def clear_reward_frame(self) -> None:
        self.set_reward_frame(None)

    def set_reward_badge(self, path: Path | None) -> None:
        self._badge_source = QPixmap(str(path)) if path and path.is_file() else QPixmap()
        self._apply_geometry()

    def clear_reward_badge(self) -> None:
        self.set_reward_badge(None)

    def _apply_geometry(self) -> None:
        opening = self._frame_opening
        if not self._frame_source.isNull() and opening is not None:
            source_size = self._frame_source.size()
            # Alle Varianten teilen dieselbe sichtbare Portraitfläche. Die
            # unterschiedlichen, unverzerrten Rahmenöffnungen bestimmen nur
            # deren leicht abweichendes Seitenverhältnis.
            target_area = (
                self._plain_portrait_size.width()
                * self._plain_portrait_size.height()
            )
            scale = sqrt(target_area / (opening.width * opening.height))
            max_frame_size = QSize(
                round(source_size.width() * scale),
                round(source_size.height() * scale),
            )
            scaled_frame = self._frame_source.scaled(
                max_frame_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            actual_scale = scaled_frame.width() / source_size.width()
            outer_width, outer_height = scaled_frame.width(), scaled_frame.height()
            portrait_x = round(opening.x * actual_scale)
            portrait_y = round(opening.y * actual_scale)
            inner_width = round(opening.width * actual_scale)
            inner_height = round(opening.height * actual_scale)
            self.setFixedSize(outer_width, outer_height)
            self.portrait.setGeometry(portrait_x, portrait_y, inner_width, inner_height)
            self.portrait.setFixedSize(inner_width, inner_height)
            self._frame.setGeometry(self.rect())
            self._frame.setPixmap(scaled_frame)
            self._frame.show()
            self._frame.raise_()
        else:
            inner_width = self._plain_portrait_size.width()
            inner_height = self._plain_portrait_size.height()
            self.setFixedSize(inner_width, inner_height)
            self.portrait.setGeometry(0, 0, inner_width, inner_height)
            self.portrait.setFixedSize(inner_width, inner_height)
            self._frame.clear()
            self._frame.hide()
        self._apply_badge_geometry()
        self.updateGeometry()

    def _apply_badge_geometry(self) -> None:
        if self._badge_source.isNull():
            self._badge.clear()
            self._badge.hide()
            return
        portrait_rect = self.portrait.geometry()
        portrait_edge = min(portrait_rect.width(), portrait_rect.height())
        badge_size = max(24, min(64, round(portrait_edge * 0.28)))
        margin = max(3, round(portrait_edge * 0.04))
        self._badge.setGeometry(
            portrait_rect.right() - margin - badge_size + 1,
            portrait_rect.top() + margin,
            badge_size,
            badge_size,
        )
        self._badge.setPixmap(self._badge_source.scaled(
            self._badge.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        self._badge.show()
        self._badge.raise_()


class ClickableFrame(QFrame):
    clicked = Signal(str)

    def __init__(self, member_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.member_id = member_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.member_id)
        super().mousePressEvent(event)


class ResponsiveCardGrid(QWidget):
    """Simple responsive card grid used by roster and graveyard."""

    def __init__(self, card_width: int, gap: int = 14, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.card_width = card_width
        self.gap = gap
        self._items: list[QWidget] = []
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(gap)
        self._layout.setVerticalSpacing(gap)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._last_columns = 0
        self._pending = QTimer(self)
        self._pending.setSingleShot(True)
        self._pending.timeout.connect(self.reflow)

    def set_items(self, widgets: Iterable[QWidget]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
        self._items = list(widgets)
        self._last_columns = 0
        self.reflow()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._pending.start(40)

    def reflow(self) -> None:
        width = max(1, self.width())
        columns = max(1, (width + self.gap) // (self.card_width + self.gap))
        if columns == self._last_columns and self._layout.count() == len(self._items):
            return
        self._last_columns = columns
        while self._layout.count():
            self._layout.takeAt(0)
        for index, widget in enumerate(self._items):
            self._layout.addWidget(widget, index // columns, index % columns)
        self._layout.setColumnStretch(columns, 1)


class GraveyardCanvas(QWidget):
    """Paint the cemetery as one scene, matching the legacy canvas concept."""

    memberActivated = Signal(str)

    def __init__(self, title_font_family: str = "Segoe UI", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title_font_family = title_font_family
        self._zoom_percent = 100
        self._cards: list[tuple[str, QPixmap]] = []
        self._card_rects: list[tuple[str, QRect]] = []
        self._hover_member_id: str | None = None
        self._activation_enabled = True
        self._summary = ""
        self._empty_text = ""
        self._background = QPixmap()
        self._background_loaded = False
        self._background_cache: dict[tuple[int, int], QPixmap] = {}
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        self.setMinimumHeight(520)

    @property
    def item_count(self) -> int:
        return len(self._cards)

    @property
    def zoom_percent(self) -> int:
        return self._zoom_percent

    @property
    def activation_enabled(self) -> bool:
        return self._activation_enabled

    def set_activation_enabled(self, enabled: bool) -> None:
        self._activation_enabled = bool(enabled)
        if not self._activation_enabled:
            self._hover_member_id = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def _load_background(self) -> None:
        if self._background_loaded:
            return
        self._background_loaded = True
        # Use the same dedicated cemetery background as the legacy checker whenever
        # it is present.  Graveyard.jpg is only a compatibility fallback.
        graveyard_dir = app_base_dir() / "assets" / "graveyard"
        candidates = [
            graveyard_dir / "Background_001.png",
            graveyard_dir / "Background_001.jpg",
            graveyard_dir / "Graveyard.jpg",
            gravestone_background_path(),
            app_base_dir() / "assets" / "Graveyard_legacy.jpg",
            app_base_dir() / "assets" / "Graveyard.jpg",
        ]
        seen: set[Path] = set()
        for path in candidates:
            path = Path(path)
            if path in seen:
                continue
            seen.add(path)
            if path.is_file():
                pixmap = QPixmap(str(path))
                if not pixmap.isNull():
                    self._background = pixmap
                    self._background_cache.clear()
                    return

    def set_scene(self, cards: Iterable[tuple[str, QPixmap]], *, zoom_percent: int,
                  summary: str, empty_text: str) -> None:
        self._cards = list(cards)
        self._zoom_percent = max(60, min(140, int(zoom_percent)))
        self._summary = str(summary)
        self._empty_text = str(empty_text)
        self._recalculate_height()
        self.update()

    def _display_card_size(self) -> tuple[int, int]:
        factor = self._zoom_percent / 100.0
        return (
            max(96, round(GRAVESTONE_CARD_SIZE[0] * factor)),
            max(132, round(GRAVESTONE_CARD_SIZE[1] * factor)),
        )

    def _layout_data(self) -> tuple[list[tuple[str, QRect]], int]:
        card_w, card_h = self._display_card_size()
        factor = self._zoom_percent / 100.0
        gap_x = max(8, round(GRAVESTONE_GRID_GAP[0] * factor))
        gap_y = max(10, round(GRAVESTONE_GRID_GAP[1] * factor))
        padding = max(14, round(GRAVESTONE_GRID_PADDING * min(1.0, factor)))
        usable_width = max(card_w, self.width() - (2 * padding))
        columns = max(1, (usable_width + gap_x) // (card_w + gap_x))
        grid_width = columns * card_w + max(0, columns - 1) * gap_x
        start_x = max(padding, (self.width() - grid_width) // 2)
        rects: list[tuple[str, QRect]] = []
        for index, (member_id, _pixmap) in enumerate(self._cards):
            row, col = divmod(index, columns)
            rects.append((
                member_id,
                QRect(
                    start_x + col * (card_w + gap_x),
                    GRAVESTONE_HEADER_BOTTOM + row * (card_h + gap_y),
                    card_w,
                    card_h,
                ),
            ))
        rows = (len(self._cards) + columns - 1) // columns if self._cards else 0
        content_height = GRAVESTONE_HEADER_BOTTOM + rows * card_h + max(0, rows - 1) * gap_y + padding
        return rects, max(520, content_height)

    def _recalculate_height(self) -> None:
        rects, height = self._layout_data()
        self._card_rects = rects
        self.setMinimumHeight(height)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._recalculate_height()

    def _background_tile(self, width: int, height: int) -> QPixmap:
        key = (max(1, width), max(1, height))
        cached = self._background_cache.get(key)
        if cached is not None:
            return cached
        if self._background.isNull():
            return QPixmap()
        scaled = self._background.scaled(
            QSize(*key),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - key[0]) // 2)
        y = max(0, (scaled.height() - key[1]) // 2)
        tile = scaled.copy(x, y, key[0], key[1])
        if len(self._background_cache) > 8:
            self._background_cache.clear()
        self._background_cache[key] = tile
        return tile

    def paintEvent(self, event) -> None:  # noqa: N802
        self._load_background()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        viewport_height = 620
        if self.parentWidget() is not None:
            viewport_height = max(420, self.parentWidget().height())
        tile = self._background_tile(max(1, self.width()), viewport_height)
        if tile.isNull():
            painter.fillRect(self.rect(), QColor("#15212b"))
        else:
            y = 0
            while y < self.height():
                painter.drawPixmap(0, y, tile)
                y += tile.height()
            painter.fillRect(self.rect(), QColor(3, 8, 12, 42))

        header_rect = QRect(18, 18, max(120, self.width() - 36), 84)
        painter.setPen(QPen(QColor("#475c6f"), 1))
        painter.setBrush(QColor(10, 18, 26, 190))
        painter.drawRoundedRect(header_rect, 3, 3)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        title_font = QFont(self._title_font_family, 22)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor("#f2f7fb"))
        painter.drawText(QRect(38, 28, max(120, self.width() - 360), 34),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         tr("graveyard.title"))
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor("#c2d3df"))
        painter.drawText(QRect(38, 66, max(160, self.width() - 360), 25),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         self._summary)

        self._card_rects, _content_height = self._layout_data()
        if not self._cards:
            empty_rect = QRect(30, GRAVESTONE_HEADER_BOTTOM, max(120, self.width() - 60), 84)
            painter.fillRect(empty_rect, QColor(10, 18, 26, 180))
            painter.setPen(QPen(QColor("#475c6f"), 1))
            painter.drawRect(empty_rect)
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
            painter.setPen(QColor("#eaf4fb"))
            painter.drawText(empty_rect, Qt.AlignmentFlag.AlignCenter, self._empty_text)
        else:
            card_w, card_h = self._display_card_size()
            pixmaps = dict(self._cards)
            for member_id, rect in self._card_rects:
                pixmap = pixmaps.get(member_id)
                if pixmap is None or pixmap.isNull():
                    continue
                if pixmap.width() == card_w and pixmap.height() == card_h:
                    painter.drawPixmap(rect.topLeft(), pixmap)
                else:
                    painter.drawPixmap(
                        rect,
                        pixmap.scaled(
                            rect.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        ),
                    )
                if member_id == self._hover_member_id:
                    painter.setPen(QPen(QColor(216, 181, 105, 185), 1))
                    painter.drawRoundedRect(rect.adjusted(1, 1, -2, -2), 4, 4)
        painter.end()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._activation_enabled:
            if self._hover_member_id is not None:
                self._hover_member_id = None
                self.update()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            super().mouseMoveEvent(event)
            return
        member_id = next((mid for mid, rect in self._card_rects if rect.contains(event.position().toPoint())), None)
        if member_id != self._hover_member_id:
            self._hover_member_id = member_id
            self.setCursor(Qt.CursorShape.PointingHandCursor if member_id else Qt.CursorShape.ArrowCursor)
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_member_id is not None:
            self._hover_member_id = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._activation_enabled and event.button() == Qt.MouseButton.LeftButton:
            point = event.position().toPoint()
            for member_id, rect in self._card_rects:
                if rect.contains(point):
                    self.memberActivated.emit(member_id)
                    event.accept()
                    return
        super().mousePressEvent(event)


class GravestoneEditorPreview(QLabel):
    """Fixed-size preview surface that reports drag deltas for the Qt editor."""

    dragged = Signal(float, float)
    dragFinished = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_origin: QPoint | None = None
        self.setFixedSize(*GRAVESTONE_EDITOR_SIZE)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setStyleSheet("background:#101820;border:1px solid #344353;")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            point = event.position().toPoint()
            delta = point - self._drag_origin
            self._drag_origin = point
            self.dragged.emit(float(delta.x()), float(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            was_dragging = self._drag_origin is not None
            self._drag_origin = None
            if was_dragging:
                self.dragFinished.emit()
        super().mouseReleaseEvent(event)


class GraveyardView(QWidget):
    """Cemetery scene plus a small floating overview-zoom control."""

    zoomChanged = Signal(int)

    def __init__(self, title_font_family: str, zoom_percent: int = 100,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.canvas = GraveyardCanvas(title_font_family)
        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll, 1)

        self.zoom_bar = QFrame(self)
        self.zoom_bar.setObjectName("graveZoomBar")
        self.zoom_bar.setFixedSize(300, 46)
        row = QHBoxLayout(self.zoom_bar)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(6)
        label = QLabel(tr("graveyard.view"))
        label.setObjectName("subtle")
        row.addWidget(label)
        minus = QPushButton("−")
        plus = QPushButton("+")
        minus.setFixedSize(30, 30)
        plus.setFixedSize(30, 30)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(60, 140)
        self.slider.setSingleStep(5)
        self.slider.setPageStep(10)
        self.slider.setValue(max(60, min(140, int(zoom_percent))))
        self.slider.setToolTip(tr("graveyard.view_tooltip"))
        self.value_label = QLabel(f"{self.slider.value()} %")
        self.value_label.setMinimumWidth(48)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(minus)
        row.addWidget(self.slider, 1)
        row.addWidget(plus)
        row.addWidget(self.value_label)
        minus.clicked.connect(lambda: self.slider.setValue(max(self.slider.minimum(), self.slider.value() - 10)))
        plus.clicked.connect(lambda: self.slider.setValue(min(self.slider.maximum(), self.slider.value() + 10)))
        self.slider.valueChanged.connect(self._zoom_changed)
        self.zoom_bar.raise_()

    def _zoom_changed(self, value: int) -> None:
        self.value_label.setText(f"{int(value)} %")
        self.zoomChanged.emit(int(value))

    def set_zoom_percent(self, value: int) -> None:
        self.slider.setValue(max(self.slider.minimum(), min(self.slider.maximum(), int(value))))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        x = max(18, self.width() - self.zoom_bar.width() - 28)
        self.zoom_bar.move(x, 32)
        self.zoom_bar.raise_()



class MemberEditDelegate(QStyledItemDelegate):
    """Excel-like editors for the editable member table columns."""

    EDITOR_MIN_WIDTHS = {
        1: 180,  # race
        2: 165,  # class
        3: 200,  # spec
        4: 180,  # main/twink
        5: 185,  # raid role
        6: 165,  # gear
        7: 165,  # raid status
    }

    def createEditor(self, parent, option, index):  # noqa: N802
        column = index.column()
        if column == 0:
            editor = QLineEdit(parent)
            editor.setClearButtonEnabled(True)
            editor.setMinimumHeight(32)
            return editor
        if column in {1, 2, 3, 4, 5, 6, 7}:
            combo = QComboBox(parent)
            combo.setMinimumHeight(32)
            if column == 1:
                combo.addItems([tr("common.not_set"), *race_display_values()])
            elif column == 2:
                combo.addItems([tr("common.not_set"), *CLASS_NAMES])
            elif column == 3:
                class_text = str(index.model().index(index.row(), 2).data() or "")
                cls = normalize_class_name(class_text)
                combo.addItems([tr("common.not_set"), *CLASS_SPECS.get(cls, [])])
            elif column == 4:
                combo.addItems([character_type_display(value) for value in CHARACTER_TYPES])
            elif column == 5:
                combo.addItems([raid_role_display(value) for value in RAID_ROLES])
            elif column == 6:
                combo.addItems([gear_status_display(value) for value in GEAR_VALUES])
            elif column == 7:
                combo.addItems([raid_status_display(value) for value in RAID_STATUS_VALUES])
            longest_text = max(
                (combo.fontMetrics().horizontalAdvance(combo.itemText(i)) for i in range(combo.count())),
                default=0,
            )
            popup_width = max(
                self.EDITOR_MIN_WIDTHS.get(column, option.rect.width()),
                option.rect.width(),
                longest_text + 58,
                combo.sizeHint().width() + 28,
            )
            combo.setMinimumWidth(self.EDITOR_MIN_WIDTHS.get(column, option.rect.width()))
            combo.setMinimumContentsLength(16)
            combo.view().setMinimumWidth(popup_width)
            combo.view().setMinimumHeight(min(340, max(96, combo.count() * 30)))
            return combo
        return None

    def updateEditorGeometry(self, editor, option, index):  # noqa: N802
        rect = option.rect
        minimum_width = self.EDITOR_MIN_WIDTHS.get(index.column(), rect.width())
        if minimum_width > rect.width():
            rect.setWidth(minimum_width)
            viewport_width = editor.parentWidget().width() if editor.parentWidget() else rect.right() + 1
            if rect.right() >= viewport_width:
                rect.moveRight(max(rect.width(), viewport_width) - 1)
        rect.setHeight(max(32, rect.height()))
        editor.setGeometry(rect)

    def setEditorData(self, editor, index):  # noqa: N802
        value = str(index.data(Qt.ItemDataRole.EditRole) or "")
        if isinstance(editor, QLineEdit):
            editor.setText(value)
            editor.selectAll()
        elif isinstance(editor, QComboBox):
            pos = editor.findText(value)
            editor.setCurrentIndex(pos if pos >= 0 else 0)

    def setModelData(self, editor, model, index):  # noqa: N802
        if isinstance(editor, QLineEdit):
            model.setData(index, editor.text().strip(), Qt.ItemDataRole.EditRole)
        elif isinstance(editor, QComboBox):
            model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)


class RaidMatrixStatusDelegate(QStyledItemDelegate):
    """Paint matrix status cells independently from the global table stylesheet."""

    def paint(self, painter, option, index):  # noqa: N802
        background = index.data(RAID_MATRIX_BACKGROUND_ROLE)
        if not background:
            super().paint(painter, option, index)
            return
        painter.save()
        painter.fillRect(option.rect, QColor(str(background)))
        painter.setFont(option.font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            option.rect,
            Qt.AlignmentFlag.AlignCenter,
            str(index.data(Qt.ItemDataRole.DisplayRole) or ""),
        )
        if option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_HasFocus):
            painter.setPen(QPen(QColor("#d9e8f5"), 2))
            painter.drawRect(option.rect.adjusted(1, 1, -2, -2))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(QPen(QColor("#9fb1c2"), 1))
            painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
        painter.restore()


class MemberTable(QTableWidget):
    """Editable member grid. The data model remains the single source of truth."""

    COLUMNS = (
        "name", "race", "class", "spec", "character_type", "raid_role",
        "gear", "raid_status", "last_checked",
    )
    paste_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, len(self.COLUMNS), parent)
        self.setHorizontalHeaderLabels([
            tr("common.character"), tr("checker.race"), tr("common.class"), tr("common.spec"),
            tr("checker.table_main_twink"), tr("checker.table_raid_role"), tr("gear.label"), tr("raid_status.label"),
            tr("checker.last_checked"),
        ])
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.setItemDelegate(MemberEditDelegate(self))
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(self.COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(110)
        self.setColumnWidth(1, 170)
        self.setColumnWidth(2, 150)
        self.setColumnWidth(3, 185)
        self.setColumnWidth(4, 165)
        self.setColumnWidth(5, 170)
        self.setColumnWidth(6, 150)
        self.setColumnWidth(7, 155)
        self.setColumnWidth(8, 125)
        self.verticalHeader().setDefaultSectionSize(40)
        self.setSortingEnabled(True)
        self.setToolTip(tr("checker.table_help"))

    def keyPressEvent(self, event):  # noqa: N802
        if event.matches(QKeySequence.StandardKey.Copy):
            indexes = self.selectedIndexes()
            if indexes:
                rows = range(min(index.row() for index in indexes), max(index.row() for index in indexes) + 1)
                columns = range(min(index.column() for index in indexes), max(index.column() for index in indexes) + 1)
                QApplication.clipboard().setText("\n".join(
                    "\t".join(self.item(row, col).text() if self.item(row, col) else "" for col in columns)
                    for row in rows
                ))
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_requested.emit(QApplication.clipboard().text())
            event.accept()
            return
        super().keyPressEvent(event)


class CopyableReadOnlyTable(QTableWidget):
    """Read-only table with deliberate clipboard export, never paste/edit."""

    def keyPressEvent(self, event):  # noqa: N802
        if event.matches(QKeySequence.StandardKey.Copy):
            rows = sorted({index.row() for index in self.selectedIndexes()})
            text = "\n".join(
                "\t".join(
                    self.item(row, column).text() if self.item(row, column) else ""
                    for column in range(self.columnCount())
                )
                for row in rows
            )
            QApplication.clipboard().setText(text)
            event.accept()
            return
        super().keyPressEvent(event)


class NumericSortItem(QTableWidgetItem):
    """Keep displayed DKP values human-readable while sorting numerically."""

    def __lt__(self, other):
        if isinstance(other, QTableWidgetItem):
            numeric_role = int(Qt.ItemDataRole.UserRole) + 1
            mine = self.data(numeric_role)
            theirs = other.data(numeric_role)
            if mine is not None and theirs is not None:
                return float(mine) < float(theirs)
        return super().__lt__(other)



class RosterCard(ClickableFrame):
    BASE_CARD_WIDTH = 205
    BASE_PORTRAIT_HEIGHT = 210

    def __init__(
        self,
        model: GuildModel,
        member: Member,
        zoom_percent: int = 100,
        rank_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(member.id, parent)
        self.setProperty("innerCard", True)
        factor = max(0.60, min(1.40, int(zoom_percent) / 100.0))
        card_width = max(122, round(self.BASE_CARD_WIDTH * factor))
        portrait_width = max(104, card_width - max(10, round(18 * factor)))
        portrait_height = max(126, round(self.BASE_PORTRAIT_HEIGHT * factor))
        margin = max(5, round(8 * factor))
        spacing = max(4, round(7 * factor))
        self.card_width = card_width
        self.setFixedWidth(card_width)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, max(6, round(10 * factor)))
        layout.setSpacing(spacing)

        portrait_surface = QWidget(self)
        portrait_surface.setFixedSize(portrait_width, portrait_height)
        portrait_surface.setStyleSheet("background:transparent;border:none;")
        self.portrait = CoverImageLabel(tr("checker.missing_portrait"), portrait_surface)
        self.portrait.setGeometry(0, 0, portrait_width, portrait_height)
        self.portrait.setFixedSize(portrait_width, portrait_height)
        self.portrait.set_source(member_portrait_path(model, member))
        self.portrait.clicked.connect(lambda: self.clicked.emit(member.id))

        self.rank_icon = QLabel(portrait_surface)
        self.rank_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.rank_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rank_icon.setStyleSheet("background:transparent;border:none;")
        # Rangsymbol auf kompakten Portraitkarten bewusst ca. 20 % größer
        # und etwas weiter vom Rand eingerückt, damit breite Symbole nicht clippen.
        rank_display_size = max(29, min(58, round(41 * factor)))
        rank_margin = max(5, round(7 * factor))
        self.rank_icon.setGeometry(
            portrait_width - rank_margin - rank_display_size,
            rank_margin,
            rank_display_size,
            rank_display_size,
        )
        rank_pixmap = QPixmap(str(rank_path)) if rank_path and rank_path.is_file() else QPixmap()
        if rank_pixmap.isNull():
            self.rank_icon.hide()
        else:
            self.rank_icon.setPixmap(rank_pixmap.scaled(
                rank_display_size,
                rank_display_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            self.rank_icon.show()
            self.rank_icon.raise_()
        layout.addWidget(portrait_surface, 0, Qt.AlignmentFlag.AlignHCenter)

        name = QLabel(member.name)
        name_size = max(8, round(11 * min(1.0, factor)))
        name.setStyleSheet(
            f"font-size:{name_size}pt;font-weight:700;color:#f3ead7;background:transparent;border:none;"
        )
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)
        layout.addWidget(name)

        details = QLabel(" · ".join(value for value in (
            member.className or "–", member.spec or "",
        ) if value))
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details.setWordWrap(True)
        class_color = CLASS_COLORS.get(member.className, MUTED)
        detail_size = max(8, round(9 * min(1.0, factor)))
        details.setStyleSheet(
            f"color:{class_color};background:transparent;border:none;font-weight:600;font-size:{detail_size}pt;"
        )
        layout.addWidget(details)

        badges = QLabel(f"{character_type_display(member.characterType)}  ·  {raid_role_display(member.raidRole)}")
        badges.setWordWrap(True)
        badges.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_size = max(7, round(8 * min(1.0, factor)))
        badges.setStyleSheet(
            f"color:#9aa7b4;background:transparent;border:none;font-size:{badge_size}pt;"
        )
        layout.addWidget(badges)



class BenchPlayersDialog(QDialog):
    """Small, shared picker for manual bench players of one raid."""
    def __init__(
        self, parent: QWidget, candidates: list[tuple[object, Member]],
        selected_player_ids: set[str],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("raids.edit_bench"))
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        hint = QLabel(tr("raids.bench_picker_hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.player_list = QListWidget()
        for player, member in candidates:
            item = QListWidgetItem(f"{player.playerName} · {member.name}")
            item.setData(Qt.ItemDataRole.UserRole, player.playerId)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if player.playerId in selected_player_ids
                else Qt.CheckState.Unchecked
            )
            self.player_list.addItem(item)
        layout.addWidget(self.player_list)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_player_ids(self) -> set[str]:
        return {
            str(self.player_list.item(row).data(Qt.ItemDataRole.UserRole) or "")
            for row in range(self.player_list.count())
            if self.player_list.item(row).checkState() == Qt.CheckState.Checked
        }


class RaidPointAdjustmentDialog(QDialog):
    """Edit only raid-bound adjustments; base and final points stay derived."""

    def __init__(self, parent: QWidget, model: GuildModel, raid) -> None:
        super().__init__(parent)
        self.model = model
        self.raid = raid
        self.entries = sorted(
            model.attendance_for_raid(raid.id),
            key=lambda entry: (
                entry.playerNameSnapshot.casefold(), entry.characterNameSnapshot.casefold(),
            ),
        )
        self._editors: list[tuple[object, QSpinBox, QLineEdit, QLabel]] = []
        self.setWindowTitle(tr("raid_points.adjust_title", raid=raid.name))
        screen = (
            parent.windowHandle().screen()
            if parent is not None and parent.windowHandle() is not None
            else QApplication.primaryScreen()
        )
        available = screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 800)
        width = max(1, min(1080, available.width() - 40))
        height = max(1, min(680, available.height() - 56))
        self.setMinimumSize(min(600, width), min(320, height))
        self.resize(width, height)
        layout = QVBoxLayout(self)
        help_label = QLabel(tr("raid_points.adjust_help"))
        help_label.setObjectName("subtle")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        self.table = QTableWidget(len(self.entries), 7)
        self.table.setHorizontalHeaderLabels([
            tr("raids.player"), tr("raids.character"), tr("common.status"),
            tr("raid_points.base"), tr("raid_points.adjustment"),
            tr("raid_points.reason"), tr("raid_points.total"),
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setMinimumSectionSize(38)
        self.table.verticalHeader().setDefaultSectionSize(38)
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(72)
        for column in (0, 1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(4, 116)
        self.table.setColumnWidth(6, 92)
        for row, entry in enumerate(self.entries):
            base = base_points_for_status(entry.status)
            current = model.raid_points.adjustments.get(entry.id)
            for column, value in enumerate((
                entry.playerNameSnapshot,
                entry.characterNameSnapshot,
                tr(f"raids.attendance_status_{entry.status}"),
                base,
            )):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
            adjustment = QSpinBox()
            adjustment.setRange(-9999, 9999)
            adjustment.setMinimumWidth(104)
            adjustment.setValue(current.value if current else 0)
            adjustment.setPrefix("+" if adjustment.value() > 0 else "")
            reason = QLineEdit(current.reason if current else "")
            reason.setMinimumWidth(180)
            reason.setMinimumHeight(30)
            reason.setPlaceholderText(tr("raid_points.reason_required"))
            total = QLabel(str(max(0, base + adjustment.value())))
            total.setAlignment(Qt.AlignmentFlag.AlignCenter)
            adjustment.valueChanged.connect(
                lambda value, spin=adjustment, label=total, points=base:
                self._update_adjustment_preview(spin, label, points, value)
            )
            self.table.setCellWidget(row, 4, adjustment)
            self.table.setCellWidget(row, 5, reason)
            self.table.setCellWidget(row, 6, total)
            adjustment.setMinimumHeight(30)
            total.setMinimumWidth(72)
            self._editors.append((entry, adjustment, reason, total))
        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _update_adjustment_preview(
        adjustment: QSpinBox, total: QLabel, base: int, value: int,
    ) -> None:
        adjustment.setPrefix("+" if value > 0 else "")
        total.setText(str(max(0, base + value)))

    def _accept_if_valid(self) -> None:
        for _entry, adjustment, reason, _total in self._editors:
            if adjustment.value() and not reason.text().strip():
                reason.setFocus()
                QMessageBox.warning(
                    self, APP_NAME, tr("raid_points.reason_required_error"),
                )
                return
        self.accept()

    def adjustment_values(self) -> list[tuple[str, int, str]]:
        return [
            (entry.id, adjustment.value(), reason.text().strip())
            for entry, adjustment, reason, _total in self._editors
        ]


class RaidEditorDialog(QDialog):
    def __init__(self, parent: QWidget, raid=None, model: GuildModel | None = None) -> None:
        super().__init__(parent)
        self.raid = raid
        self.model = model
        self.csv_names: list[str] = []
        self.csv_duplicates: list[str] = []
        self.unknown_decisions: dict[str, tuple[str, str | None]] = {}
        self.csv_resolution = None
        self.csv_open_names: list[str] = []
        self.csv_ready = False
        self.bench_player_ids: set[str] = set()
        self.adjust_points_after_save = False
        if model is not None and raid is not None:
            self.bench_player_ids = {
                entry.playerId for entry in model.attendance_for_raid(raid.id)
                if entry.status == "bench"
            }
        self.setWindowTitle(tr("raids.edit_title") if raid else tr("raids.create_title"))
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.date_edit = QLineEdit(raid.date if raid else today_iso())
        self.name_edit = QLineEdit(raid.name if raid else "")
        self.url_edit = QLineEdit(raid.warcraftLogsUrl if raid else "")
        self.raid_type_combo = QComboBox()
        self.raid_type_combo.addItem(tr("common.not_set"), "")
        for raid_type in RAID_TYPES:
            self.raid_type_combo.addItem(raid_type, raid_type)
        current_type = getattr(raid, "raidType", "") if raid else ""
        self.raid_type_combo.setCurrentIndex(max(0, self.raid_type_combo.findData(current_type)))
        form.addRow(tr("common.date"), self.date_edit)
        form.addRow(tr("raids.raid_type"), self.raid_type_combo)
        form.addRow(tr("raids.raid_name"), self.name_edit)
        form.addRow(tr("raids.warcraft_logs"), self.url_edit)
        layout.addLayout(form)

        if raid is None:
            csv_row = QHBoxLayout()
            self.csv_path_label = QLineEdit()
            self.csv_path_label.setReadOnly(True)
            self.csv_path_label.setPlaceholderText(tr("raids.csv_required"))
            csv_button = QPushButton(tr("raids.select_csv"))
            csv_button.clicked.connect(self._choose_csv)
            csv_row.addWidget(self.csv_path_label, 1)
            csv_row.addWidget(csv_button)
            layout.addWidget(QLabel(tr("raids.csv_for_creation")))
            layout.addLayout(csv_row)
            self.csv_summary = QLabel(tr("raids.csv_not_loaded"))
            self.csv_summary.setWordWrap(True)
            self.csv_summary.setObjectName("subtle")
            layout.addWidget(self.csv_summary)

        bench_row = QHBoxLayout()
        self.bench_button = QPushButton(tr("raids.edit_bench"))
        self.bench_button.clicked.connect(self._edit_bench_players)
        bench_row.addWidget(QLabel(tr("raids.bench")))
        bench_row.addStretch(1)
        bench_row.addWidget(self.bench_button)
        layout.addLayout(bench_row)
        self.bench_summary = QLabel()
        self.bench_summary.setObjectName("subtle")
        layout.addWidget(self.bench_summary)

        self.points_button = QPushButton(tr("raid_points.adjust"))
        self.points_button.setVisible(bool(
            model and model.active_point_mode() == POINT_MODE_RAID
        ))
        self.points_button.clicked.connect(self._accept_for_points)
        layout.addWidget(self.points_button, 0, Qt.AlignmentFlag.AlignLeft)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self._accept_if_ready)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.date_edit.textChanged.connect(self._refresh_save_state)
        self.date_edit.textChanged.connect(self._refresh_bench_state)
        self.name_edit.textChanged.connect(self._refresh_save_state)
        self.raid_type_combo.currentIndexChanged.connect(self._raid_type_changed)
        self.name_edit.setFocus()
        self._refresh_save_state()
        self._refresh_bench_state()

    def _raid_type_changed(self) -> None:
        raid_type = str(self.raid_type_combo.currentData() or "")
        if self.raid is None and raid_type and not self.name_edit.text().strip():
            self.name_edit.setText(raid_type)
        self._refresh_save_state()

    def _active_mains(self) -> list[tuple[str, str]]:
        if self.model is None:
            return []
        mains: list[tuple[str, str]] = []
        for member in self.model.members:
            if member.lifeStatus != "active" or member.characterType != "main" or not member.playerId:
                continue
            player = self.model.find_player_by_id(member.playerId)
            if player:
                mains.append((f"{player.playerName} · {member.name}", member.id))
        return sorted(mains, key=lambda item: item[0].casefold())

    def _apply_csv_metadata(self, metadata) -> list[str]:
        """Apply independently validated metadata once when the CSV is selected."""
        warnings: list[str] = []
        if metadata.raid_type:
            raid_type = normalize_csv_raid_type(metadata.raid_type, RAID_TYPES)
            index = self.raid_type_combo.findData(raid_type) if raid_type else -1
            if index >= 0:
                self.raid_type_combo.setCurrentIndex(index)
            else:
                warnings.append(tr(
                    "raids.csv_metadata_ignored",
                    field=tr("raids.raid_type"), error=tr("raids.invalid_raid_type"),
                ))
        if metadata.raid_date:
            try:
                normalized_date = normalize_iso_date(metadata.raid_date)
                if normalized_date:
                    self.date_edit.setText(normalized_date)
            except Exception as exc:
                warnings.append(tr(
                    "raids.csv_metadata_ignored",
                    field=tr("common.date"), error=raid_error_text(exc),
                ))
        if metadata.report_url:
            try:
                self.url_edit.setText(validate_logs_url(metadata.report_url))
            except Exception as exc:
                warnings.append(tr(
                    "raids.csv_metadata_ignored",
                    field=tr("raids.warcraft_logs"), error=raid_error_text(exc),
                ))
        return warnings

    def _choose_csv(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, tr("raids.select_csv"), "", f"CSV (*.csv);;{tr('common.all_files')} (*.*)",
        )
        if not path or self.model is None:
            return
        self.csv_ready = False
        self.csv_names = []
        self.csv_duplicates = []
        self.unknown_decisions = {}
        self.csv_resolution = None
        self.csv_open_names = []
        self.bench_player_ids.clear()
        try:
            parsed_csv = read_raid_csv(Path(path))
            names = list(parsed_csv.names)
            duplicates = list(parsed_csv.duplicates)
            metadata_warnings = self._apply_csv_metadata(parsed_csv.metadata)
            resolution = self.model.resolve_raid_attendance(names)
            self.csv_names = names
            self.csv_duplicates = duplicates
            self.csv_resolution = resolution
            mains = self._active_mains()
            for name in resolution.unknown_names:
                dialog = UnknownRaidMemberDialog(self, name, mains)
                if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_value is None:
                    break
                self.unknown_decisions[name] = dialog.result_value
            self.csv_open_names = [
                *resolution.ambiguous_names,
                *(name for name in resolution.unknown_names if name not in self.unknown_decisions),
            ]
            self.csv_ready = bool(names) and not self.csv_open_names
            self.csv_path_label.setText(path)
            summary = tr(
                "raids.csv_summary",
                recognized=len(names),
                known=(
                    len(names)
                    - len(resolution.unknown_names)
                    - len(resolution.ambiguous_names)
                ),
                open=len(self.csv_open_names),
                duplicates=len(duplicates),
                merged=len(resolution.merged_characters),
            )
            if self.csv_open_names:
                summary += "\n" + tr(
                    "raids.csv_unresolved", names=", ".join(self.csv_open_names),
                )
            if metadata_warnings:
                summary += "\n" + "\n".join(metadata_warnings)
            self.csv_summary.setText(summary)
        except Exception as exc:
            self.csv_summary.setText(tr("raids.import_failed", error=raid_error_text(exc)))
        self._refresh_save_state()
        self._refresh_bench_state()

    def _current_csv_resolution(self):
        if self.csv_resolution is not None:
            return self.csv_resolution
        if self.model is None:
            return None
        return self.model.resolve_raid_attendance(self.csv_names)

    def _csv_present_player_ids(self) -> set[str]:
        resolution = self._current_csv_resolution()
        if resolution is None or self.model is None:
            return set()
        player_ids = {candidate.player_id for candidate in resolution.candidates}
        for action, main_id in self.unknown_decisions.values():
            if action != "twink" or not main_id:
                continue
            main = self.model.find_by_id(main_id)
            if main is not None and main.playerId:
                player_ids.add(main.playerId)
        return player_ids

    def _csv_present_count(self) -> int:
        resolution = self._current_csv_resolution()
        if resolution is None or self.model is None:
            return 0
        participant_keys = {
            ("player", player_id) for player_id in self._csv_present_player_ids()
        }
        participant_keys.update(
            ("member", item.member_id) for item in resolution.unassigned_characters
        )
        for name, (action, main_id) in self.unknown_decisions.items():
            if action == "main":
                participant_keys.add(("new", name.casefold()))
            elif action == "twink" and main_id:
                main = self.model.find_by_id(main_id)
                if main is None or not main.playerId:
                    participant_keys.add(("member", main_id))
        return len(participant_keys)

    def _bench_candidates(self) -> list[tuple[object, Member]]:
        if self.model is None:
            return []
        try:
            if self.raid is None:
                if not self.csv_ready:
                    return []
                present = self._csv_present_player_ids()
            else:
                present = {
                    entry.playerId for entry in self.model.attendance_for_raid(self.raid.id)
                    if entry.status == "present"
                }
            return self.model.bench_candidates_for_date(self.date_edit.text().strip(), present)
        except Exception:
            return []

    def _refresh_bench_state(self) -> None:
        candidates = self._bench_candidates()
        candidate_ids = {player.playerId for player, _member in candidates}
        self.bench_player_ids.intersection_update(candidate_ids)
        enabled = bool(candidates) and (self.raid is not None or self.csv_ready)
        self.bench_button.setEnabled(enabled)
        if not candidates and (self.raid is not None or self.csv_ready):
            self.bench_button.setToolTip(tr("raids.no_bench_available"))
        else:
            self.bench_button.setToolTip("")
        present_count = 0
        open_count = 0
        if self.model is not None:
            if self.raid is None and self.csv_names:
                present_count = self._csv_present_count()
                open_count = len(self.csv_open_names)
            elif self.raid is not None:
                present_count = sum(
                    entry.status == "present"
                    for entry in self.model.attendance_for_raid(self.raid.id)
                )
        self.bench_summary.setText(tr(
            "raids.bench_summary", present=present_count, bench=len(self.bench_player_ids),
            open=open_count,
        ))

    def _edit_bench_players(self) -> None:
        candidates = self._bench_candidates()
        if not candidates:
            return
        dialog = BenchPlayersDialog(self, candidates, self.bench_player_ids)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.bench_player_ids = dialog.selected_player_ids()
            self._refresh_bench_state()

    def _refresh_save_state(self) -> None:
        ready = bool(
            self.date_edit.text().strip()
            and self.name_edit.text().strip()
            and self.raid_type_combo.currentData()
        )
        if self.raid is None:
            ready = ready and self.csv_ready
        self.save_button.setEnabled(ready)

    def _accept_if_ready(self) -> None:
        self._refresh_save_state()
        if self.save_button.isEnabled():
            self.accept()

    def _accept_for_points(self) -> None:
        self._refresh_save_state()
        if self.save_button.isEnabled():
            self.adjust_points_after_save = True
            self.accept()

    def values(self) -> tuple[str, str, str, str]:
        return (
            self.date_edit.text().strip(), self.name_edit.text().strip(),
            self.url_edit.text().strip(), str(self.raid_type_combo.currentData() or ""),
        )

    def creation_values(
        self,
    ) -> tuple[str, str, str, str, list[str], dict[str, tuple[str, str | None]], list[str]]:
        date, name, url, raid_type = self.values()
        return (
            date, name, url, raid_type, list(self.csv_names), dict(self.unknown_decisions),
            sorted(self.bench_player_ids),
        )

    def bench_values(self) -> list[str]:
        return sorted(self.bench_player_ids)


class BulkRaidImportDialog(QDialog):
    """Preview and execute an additive folder import without replacing raids."""

    IMPORTABLE_STATUSES = {"new", "needs_assignment", "merge"}
    DESELECTED_PATHS_SETTING = "bulk_raid_deselected_paths"

    def __init__(self, parent: QWidget, model: GuildModel, folder: Path,
                 settings_path: Path | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.folder = folder
        self._selection_settings_path = Path(settings_path) if settings_path else None
        self._persisted_deselected_paths = self._load_deselected_paths()
        self.result_value = None
        paths = tuple(
            path for path in folder.iterdir()
            if path.is_file() and path.suffix.casefold() == ".csv"
        )
        self.plans = list(model.analyze_bulk_raid_csv_files(paths))
        self._plans_by_source_path = {
            self._source_path_key(plan.source_path): plan for plan in self.plans
        }
        self._participant_preview = {
            self._source_path_key(plan.source_path): self._build_participant_preview(plan)
            for plan in self.plans
        }
        self.selected_paths = {
            self._source_path_key(plan.source_path) for plan in self.plans
            if (plan.status in self.IMPORTABLE_STATUSES
                and self._source_path_key(plan.source_path)
                not in self._persisted_deselected_paths)
        }
        self._refreshing_table = False
        self.setWindowTitle(tr("raids.bulk_title"))
        self.setMinimumSize(900, 620)
        layout = QVBoxLayout(self)
        intro = QLabel(tr("raids.bulk_preview_help", folder=str(folder)))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            tr("raids.bulk_selected"), tr("common.date"), tr("raids.raid_type"),
            tr("raids.bulk_file"), tr("raids.bulk_participant_count"),
            tr("common.status"), tr("raids.warcraft_logs"),
        ])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for column in (1, 4, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(120)
        self.table.setColumnWidth(2, 190)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemChanged.connect(self._selection_changed)
        self.table.cellClicked.connect(self._table_clicked)
        self.table.cellChanged.connect(self._cell_changed)
        self.table.itemSelectionChanged.connect(self._show_selected_participants)
        layout.addWidget(self.table, 1)

        self.participant_title = QLabel()
        layout.addWidget(self.participant_title)
        self.participant_list = QListWidget()
        self.participant_list.setMaximumHeight(180)
        layout.addWidget(self.participant_list)

        selection_actions = QHBoxLayout()
        select_all_button = QPushButton(tr("raids.bulk_select_all_new"))
        clear_button = QPushButton(tr("raids.bulk_clear_selection"))
        select_all_button.clicked.connect(self._select_all_new)
        clear_button.clicked.connect(self._clear_selection)
        selection_actions.addWidget(select_all_button)
        selection_actions.addWidget(clear_button)
        selection_actions.addStretch(1)
        layout.addLayout(selection_actions)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setObjectName("subtle")
        layout.addWidget(self.summary)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.import_button = buttons.addButton(
            tr("raids.bulk_import_new"), QDialogButtonBox.ButtonRole.ActionRole,
        )
        set_button_role(self.import_button, primary=True)
        self.import_button.clicked.connect(self._import_new)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh_view()

    @staticmethod
    def _source_path_key(path: Path | str) -> str:
        try:
            return str(Path(path).resolve())
        except OSError:
            return str(Path(path))

    def _load_deselected_paths(self) -> set[str]:
        if self._selection_settings_path is None:
            return set()
        stored = read_suite_settings(self._selection_settings_path).get(
            self.DESELECTED_PATHS_SETTING, (),
        )
        if not isinstance(stored, list):
            return set()
        return {
            self._source_path_key(path)
            for path in stored if isinstance(path, str) and path.strip()
        }

    def _persist_deselected_paths(self) -> None:
        if self._selection_settings_path is None:
            return
        importable_paths = {
            self._source_path_key(plan.source_path) for plan in self.plans
            if plan.status in self.IMPORTABLE_STATUSES
        }
        self._persisted_deselected_paths.difference_update(importable_paths)
        self._persisted_deselected_paths.update(importable_paths - self.selected_paths)
        update_suite_settings(
            self._selection_settings_path,
            **{self.DESELECTED_PATHS_SETTING: sorted(self._persisted_deselected_paths)},
        )

    def _status_text(self, status: str) -> str:
        return tr(f"raids.bulk_status_{status}")

    def _build_participant_preview(
        self, plan: BulkRaidCsvPlan,
    ) -> tuple[tuple[str, bool], ...]:
        """Use the cached plan names and existing exact attendance matching."""
        if not plan.names:
            return ()
        resolution = self.model.resolve_raid_attendance(plan.names)
        unmatched = {
            exact_name_key(name)
            for name in (*resolution.unknown_names, *resolution.ambiguous_names)
        }
        return tuple(
            (name, exact_name_key(name) not in unmatched)
            for name in plan.names
        )

    def _selected_plan(self) -> BulkRaidCsvPlan | None:
        return self._plan_for_row(self.table.currentRow())

    def _plan_for_row(self, row: int) -> BulkRaidCsvPlan | None:
        item = self.table.item(row, 0)
        source_path = str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""
        return self._plans_by_source_path.get(source_path)

    def _row_for_source_path(self, source_path: str) -> int:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == source_path:
                return row
        return -1

    def _show_selected_participants(self) -> None:
        plan = self._selected_plan()
        self.participant_list.clear()
        if plan is None:
            self.participant_title.setText(tr("raids.bulk_participants_none"))
            return
        participants = self._participant_preview.get(self._source_path_key(plan.source_path), ())
        recognized = sum(known for _name, known in participants)
        self.participant_title.setText(tr(
            "raids.bulk_participants_summary", total=len(participants),
            recognized=recognized, unrecognized=len(participants) - recognized,
        ))
        for name, known in participants:
            item = QListWidgetItem(name)
            item.setToolTip(
                tr("raids.bulk_participant_recognized") if known
                else tr("raids.bulk_participant_unrecognized")
            )
            item.setForeground(QColor("#a7d8aa") if known else QColor("#e2b66d"))
            self.participant_list.addItem(item)

    def _selection_changed(self, item: QTableWidgetItem) -> None:
        if self._refreshing_table or item.column() != 0:
            return
        source_path = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not source_path:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self.selected_paths.add(source_path)
        else:
            self.selected_paths.discard(source_path)
        self._persist_deselected_paths()
        self._refresh_summary()

    def _cell_changed(self, row: int, column: int) -> None:
        if self._refreshing_table or column != 2:
            return
        combo = self.table.cellWidget(row, column)
        if not isinstance(combo, QComboBox):
            return
        source_item = self.table.item(row, 0)
        source_path = str(source_item.data(Qt.ItemDataRole.UserRole) or "") if source_item else ""
        raid_type = str(combo.currentData() or "")
        if source_path and raid_type:
            self._override_raid_type(source_path, raid_type)

    def _override_raid_type(self, source_path: str, raid_type: str) -> None:
        if self._refreshing_table or not raid_type:
            return
        index = next((
            position for position, plan in enumerate(self.plans)
            if self._source_path_key(plan.source_path) == source_path
        ), None)
        if index is None:
            return
        plan = self.plans[index]
        existing = self.model._matching_raid(plan.raid_date, raid_type)
        resolution = self.model.resolve_raid_attendance(plan.names)
        if resolution.ambiguous_names:
            status, detail = "invalid", tr("raids.bulk_unresolved", names=", ".join(resolution.ambiguous_names))
        elif existing is not None:
            status = "merge" if plan.report_url and not existing.warcraftLogsUrl else "existing"
            detail = tr("raids.bulk_existing_detail") if status == "existing" else ""
        else:
            status = "needs_assignment" if resolution.unknown_names else "new"
            detail = (
                tr("raids.bulk_unresolved", names=", ".join(resolution.unknown_names))
                if status == "needs_assignment" else ""
            )
        self.plans[index] = replace(plan, raid_type=raid_type, status=status, detail=detail)
        self._plans_by_source_path[source_path] = self.plans[index]
        if status in self.IMPORTABLE_STATUSES and source_path not in self._persisted_deselected_paths:
            self.selected_paths.add(source_path)
        else:
            self.selected_paths.discard(source_path)
        self._refresh_view()

    def _table_clicked(self, row: int, column: int) -> None:
        if column != 6:
            return
        plan = self._plan_for_row(row)
        report_url = plan.report_url if plan is not None else ""
        if report_url:
            webbrowser.open_new_tab(report_url)

    def _select_all_new(self) -> None:
        self.selected_paths = {
            self._source_path_key(plan.source_path) for plan in self.plans
            if plan.status in self.IMPORTABLE_STATUSES
        }
        self._persist_deselected_paths()
        self._refresh_view()

    def _clear_selection(self) -> None:
        self.selected_paths.clear()
        self._persist_deselected_paths()
        self._refresh_view()

    def _refresh_summary(self) -> None:
        selected_count = sum(
            plan.status in self.IMPORTABLE_STATUSES
            and self._source_path_key(plan.source_path) in self.selected_paths
            for plan in self.plans
        )
        existing_count = sum(plan.status == "existing" for plan in self.plans)
        failed_count = sum(
            plan.status in {"invalid", "unknown_type", "import_error"}
            for plan in self.plans
        )
        deselected_count = sum(
            plan.status in self.IMPORTABLE_STATUSES
            and self._source_path_key(plan.source_path) not in self.selected_paths
            for plan in self.plans
        )
        if self.result_value is None:
            self.summary.setText(tr(
                "raids.bulk_preview_summary", selected=selected_count,
                existing=existing_count, deselected=deselected_count, failed=failed_count,
            ))
        else:
            self.summary.setText(tr(
                "raids.bulk_result_summary",
                imported=self.result_value.imported,
                skipped=self.result_value.skipped,
                deselected=deselected_count,
                failed=self.result_value.failed,
            ))
        self.import_button.setEnabled(selected_count > 0 and self.result_value is None)

    def _refresh_view(self) -> None:
        selected_plan = self._selected_plan()
        selected_path = (
            self._source_path_key(selected_plan.source_path)
            if selected_plan is not None else ""
        )
        header = self.table.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        self._refreshing_table = True
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.plans))
        for row, plan in enumerate(self.plans):
            source_path = self._source_path_key(plan.source_path)
            selectable = plan.status in self.IMPORTABLE_STATUSES
            selection_item = QTableWidgetItem()
            selection_item.setData(Qt.ItemDataRole.UserRole, source_path)
            selection_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                if selectable else Qt.ItemFlag.NoItemFlags
            )
            selection_item.setCheckState(
                Qt.CheckState.Checked
                if selectable and source_path in self.selected_paths
                else Qt.CheckState.Unchecked
            )
            self.table.setItem(row, 0, selection_item)
            values = (
                plan.raid_date or "–",
                plan.raid_type or "–",
                plan.source_path.name,
                str(len(self._participant_preview.get(source_path, ()))),
                self._status_text(plan.status),
                "Link" if plan.report_url else "–",
            )
            for column, value in enumerate(values, start=1):
                item = QTableWidgetItem(str(value))
                if plan.detail:
                    item.setToolTip(plan.detail)
                if column == 6 and plan.report_url:
                    item.setToolTip(plan.report_url)
                self.table.setItem(row, column, item)
            combo = QComboBox(self.table)
            combo.setMinimumWidth(178)
            combo.setMinimumHeight(29)
            combo.setStyleSheet(
                "QComboBox { padding: 4px 8px; }"
                "QComboBox QAbstractItemView { padding: 4px 8px; min-width: 190px; }"
            )
            combo.addItem(tr("common.not_set"), "")
            for raid_type in RAID_TYPES:
                combo.addItem(raid_type, raid_type)
            combo.setCurrentIndex(max(0, combo.findData(plan.raid_type)))
            combo.view().setMinimumWidth(190)
            combo.view().setMinimumHeight(30)
            combo.currentIndexChanged.connect(
                lambda _index, path=source_path, control=combo: self._override_raid_type(
                    path, str(control.currentData() or "")
                )
            )
            self.table.setCellWidget(row, 2, combo)
        self._refreshing_table = False
        self.table.setSortingEnabled(True)
        if 1 <= sort_column < self.table.columnCount():
            self.table.sortItems(sort_column, sort_order)
        self._refresh_summary()
        if selected_path:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == selected_path:
                    self.table.selectRow(row)
                    break
        elif self.table.rowCount() and self.table.currentRow() < 0:
            self.table.selectRow(0)
        self._show_selected_participants()

    def _active_mains(self) -> list[tuple[str, str]]:
        mains: list[tuple[str, str]] = []
        for member in self.model.members:
            if member.lifeStatus != "active" or member.characterType != "main" or not member.playerId:
                continue
            player = self.model.find_player_by_id(member.playerId)
            if player is not None:
                mains.append((f"{player.playerName} · {member.name}", member.id))
        return sorted(mains, key=lambda item: item[0].casefold())

    def _unknown_decisions_for(
        self, plans: list[BulkRaidCsvPlan],
    ) -> dict[str, tuple[str, str | None]] | None:
        decisions: dict[str, tuple[str, str | None]] = {}
        mains = self._active_mains()
        for plan in plans:
            for name in plan.unknown_names:
                if name in decisions:
                    continue
                dialog = UnknownRaidMemberDialog(self, name, mains)
                if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_value is None:
                    return None
                decisions[name] = dialog.result_value
        return decisions

    def _import_new(self) -> None:
        selected = [
            plan for plan in self.plans
            if plan.status in self.IMPORTABLE_STATUSES
            and self._source_path_key(plan.source_path) in self.selected_paths
        ]
        decisions = self._unknown_decisions_for(selected)
        if decisions is None:
            return
        decisions_by_path = {
            plan.source_path: decisions for plan in selected
        }
        self.result_value = self.model.import_bulk_raid_csv_plans(
            selected, decisions_by_path,
        )
        updated_by_path = {
            self._source_path_key(plan.source_path): plan for plan in self.result_value.plans
        }
        self.plans = [
            updated_by_path.get(self._source_path_key(plan.source_path), plan)
            for plan in self.plans
        ]
        self._plans_by_source_path = {
            self._source_path_key(plan.source_path): plan for plan in self.plans
        }
        self._refresh_view()


class ClmRaidHistoryPreviewDialog(QDialog):
    def __init__(self, parent: QWidget, model: GuildModel, preview: object) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("raid_clm_admin.history_title"))
        self.resize(980, 560)
        layout = QVBoxLayout(self)
        intro = QLabel(tr(
            "raid_clm_admin.history_preview_help",
            raids=len(preview.projection.raids),
            unresolved=len(preview.projection.unresolved_events),
            unknown=len(preview.unknown_names) + len(preview.ambiguous_names),
        ))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        table = QTableWidget(0, 9)
        table.setHorizontalHeaderLabels([
            tr("common.date"), tr("raids.raid_name"), tr("raids.raid_type"),
            tr("raid_clm_admin.history_status"), tr("raid_clm_admin.clm_raid_id"),
            tr("raids.participants"), tr("raid_clm_admin.eternal_dkp"),
            tr("raid_clm_admin.bench_share"), tr("common.status"),
        ])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for history in preview.projection.raids:
            matched = next((
                raid for raid in model.raids
                if history.clm_raid_id in raid.clmRaidIds
                or (raid.date == history.date and raid.raidType in history.raid_types)
            ), None)
            raid_dkp = sum(
                float(entry.value) for entry in history.earnings
                if entry.kind == "EARNED_RAID"
            )
            bench_dkp = sum(
                float(entry.value) for entry in history.earnings
                if entry.kind in {"EARNED_BENCH", "CORRECTION"}
            )
            flags = []
            if history.combined:
                flags.append(tr("raid_clm_admin.combined"))
            if history.warnings:
                flags.append(tr("raid_clm_admin.review_needed"))
            row = table.rowCount()
            table.insertRow(row)
            values = (
                history.date or "–", history.name or "–",
                " + ".join(history.raid_types) or tr("raid_clm_admin.combined"),
                tr("raid_clm_admin.history_enrich") if matched else tr("raid_clm_admin.history_new"),
                history.clm_raid_id, len(history.participant_guids | history.bench_guids),
                f"{raid_dkp:g}", f"{bench_dkp:g}", ", ".join(flags) or "–",
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(str(value)))
        layout.addWidget(table, 1)
        if preview.unknown_names or preview.ambiguous_names:
            names = ", ".join((*preview.unknown_names, *preview.ambiguous_names))
            warning = QLabel(tr("raid_clm_admin.history_assignment_needed", names=names))
            warning.setWordWrap(True)
            warning.setObjectName("subtle")
            layout.addWidget(warning)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            tr("raid_clm_admin.history_apply"),
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class UnknownRaidMemberDialog(QDialog):
    def __init__(self, parent: QWidget, name: str, mains: list[tuple[str, str]]) -> None:
        super().__init__(parent)
        self.name = name
        self.result_value: tuple[str, str | None] | None = None
        self.setWindowTitle(tr("raid_clm_admin.history_assignment_title"))
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        text = QLabel(tr("raid_clm_admin.history_unknown_question", name=name))
        text.setWordWrap(True)
        layout.addWidget(text)
        self.main_combo = QComboBox()
        for label, member_id in mains:
            self.main_combo.addItem(label, member_id)
        layout.addWidget(QLabel(tr("raids.twink_player")))
        layout.addWidget(self.main_combo)
        row = QHBoxLayout()
        main_button = set_button_role(QPushButton(tr("raids.add_as_main")), primary=True)
        twink_button = QPushButton(tr("raids.assign_as_twink"))
        inactive_button = QPushButton(tr("raid_clm_admin.history_action_inactive"))
        dead_button = QPushButton(tr("raid_clm_admin.history_action_dead"))
        dead_twink_button = QPushButton(tr("raid_clm_admin.history_action_dead_twink"))
        discard_button = set_button_role(QPushButton(tr("raid_clm_admin.history_action_irrelevant")), danger=True)
        twink_button.setEnabled(bool(mains))
        dead_twink_button.setEnabled(bool(mains))
        main_button.clicked.connect(lambda: self._finish("main", None))
        twink_button.clicked.connect(lambda: self._finish("twink", self.main_combo.currentData()))
        inactive_button.clicked.connect(lambda: self._finish("inactive", None))
        dead_button.clicked.connect(lambda: self._finish("dead", None))
        dead_twink_button.clicked.connect(lambda: self._finish("dead_twink", self.main_combo.currentData()))
        discard_button.clicked.connect(lambda: self._finish("irrelevant", None))
        row.addWidget(main_button)
        row.addWidget(twink_button)
        row.addWidget(inactive_button)
        row.addWidget(dead_button)
        row.addWidget(dead_twink_button)
        row.addWidget(discard_button)
        layout.addLayout(row)

    def _finish(self, action: str, member_id: str | None) -> None:
        self.result_value = (action, str(member_id) if member_id else None)
        self.accept()


class PlayerProfilePage(QWidget):
    """Contextual playerId page; all domain values are supplied read-only."""

    playerSelected = Signal(str)
    characterSelected = Signal(str)
    previousCharacterRequested = Signal()
    nextCharacterRequested = Signal()
    backRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 14, 18, 20)
        layout.setSpacing(14)

        top = QHBoxLayout()
        self.back_button = QPushButton(tr("player_profile.back_to_roster"))
        self.back_button.clicked.connect(self.backRequested.emit)
        top.addWidget(self.back_button)
        self.title = QLabel(tr("player_profile.title", name=tr("player_profile.no_active_main")))
        self.title.setObjectName("sectionTitle")
        top.addWidget(self.title, 1)
        top.addWidget(QLabel(tr("player_profile.select_player")))
        self.player_combo = QComboBox()
        self.player_combo.setMinimumWidth(240)
        self.player_combo.currentIndexChanged.connect(self._player_changed)
        top.addWidget(self.player_combo)
        layout.addLayout(top)

        self.player_summary = QFrame()
        self.player_summary.setProperty("card", True)
        summary_layout = QHBoxLayout(self.player_summary)
        summary_layout.setContentsMargins(16, 9, 16, 9)
        summary_layout.setSpacing(16)
        self.player_metrics, self.player_metric_labels = self._build_metrics(
            ("player_rank", "eternal_dkp", "raids", "attendance"),
            columns=4,
        )
        self.player_metrics.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed,
        )
        summary_layout.addWidget(self.player_metrics)
        summary_layout.addStretch(1)
        summary_layout.addWidget(QLabel(tr("player_profile.select_character")))
        self.character_previous_button = QPushButton("◀")
        self.character_previous_button.setObjectName("detailAction")
        self.character_previous_button.setToolTip(tr("player_profile.previous_character"))
        self.character_previous_button.clicked.connect(self.previousCharacterRequested.emit)
        summary_layout.addWidget(self.character_previous_button)
        self.character_combo = QComboBox()
        self.character_combo.setMinimumWidth(260)
        self.character_combo.currentIndexChanged.connect(self._character_changed)
        summary_layout.addWidget(self.character_combo)
        self.character_next_button = QPushButton("▶")
        self.character_next_button.setObjectName("detailAction")
        self.character_next_button.setToolTip(tr("player_profile.next_character"))
        self.character_next_button.clicked.connect(self.nextCharacterRequested.emit)
        summary_layout.addWidget(self.character_next_button)
        layout.addWidget(self.player_summary)

        self.player_card = QFrame()
        self.player_card.setProperty("card", True)
        card_layout = QVBoxLayout(self.player_card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(12)

        player_layout = QHBoxLayout()
        player_layout.setSpacing(18)
        self.player_portrait = CoverImageLabel(tr("checker.missing_portrait"))
        self.player_reward_portrait = RewardPortraitContainer(
            self.player_portrait, QSize(150, 210), rank_asset_size=96,
        )
        player_visual = QHBoxLayout()
        player_visual.setSpacing(6)
        player_visual.addWidget(self.player_reward_portrait, 0, Qt.AlignmentFlag.AlignTop)
        self.player_rank_icon = QLabel()
        self.player_rank_icon.setFixedSize(96, 96)
        self.player_rank_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.player_rank_icon.setStyleSheet("background:transparent;border:none;")
        player_visual.addWidget(self.player_rank_icon, 0, Qt.AlignmentFlag.AlignTop)
        player_layout.addLayout(player_visual, 0)

        player_info = QVBoxLayout()
        character_details = QFormLayout()
        character_details.setHorizontalSpacing(14)
        self.character_name = QLabel("–")
        self.character_name.setObjectName("memberName")
        self.character_identity_line = QLabel("–")
        self.character_identity_line.setObjectName("subtle")
        self.character_spec = QLabel("–")
        self.character_type = QLabel("–")
        self.character_life = QLabel("–")
        self.character_rank = QLabel("–")
        self.character_details_form = character_details
        character_details.addRow(tr("common.name"), self.character_name)
        character_details.addRow("", self.character_identity_line)
        character_details.addRow(tr("common.spec"), self.character_spec)
        character_details.addRow(tr("checker.character_type"), self.character_type)
        character_details.addRow(tr("common.status"), self.character_life)
        character_details.addRow(tr("player_profile.rank"), self.character_rank)
        self.character_metric_labels: dict[str, QLabel] = {}
        for key, title in (
            ("attendance", tr("player_profile.attendance")),
            ("raids", tr("player_profile.raids")),
            ("points", tr("raid_points.title")),
            ("eternal_dkp", tr("raid_clm_admin.eternal_dkp")),
            ("streak", tr("player_profile.streak")),
        ):
            value = QLabel("–")
            value.setStyleSheet("font-size:10pt;font-weight:700;")
            character_details.addRow(QLabel(title), value)
            self.character_metric_labels[key] = value
        self.character_raid_title = QLabel(tr("player_profile.raid_list"))
        self.character_raid_title.setObjectName("subtle")
        self.character_raid_title.setStyleSheet("font-weight:700;")
        self.character_raid_table = QTableWidget(0, 4)
        self.character_raid_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.character_raid_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.character_raid_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection,
        )
        self.character_raid_table.setAlternatingRowColors(True)
        self.character_raid_table.verticalHeader().setVisible(False)
        self.character_raid_table.verticalHeader().setDefaultSectionSize(26)
        self.character_raid_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch,
        )
        self.character_raid_table.setMaximumHeight(280)
        self.character_raid_table.setMinimumHeight(180)
        character_info = QHBoxLayout()
        character_info.setSpacing(12)
        character_left = QVBoxLayout()
        character_left.setSpacing(6)
        character_left.addLayout(character_details)
        character_info.addLayout(character_left, 1)
        character_activity = QVBoxLayout()
        character_activity.setSpacing(6)
        character_activity.addWidget(self.character_raid_title)
        character_activity.addWidget(self.character_raid_table)
        character_info.addLayout(character_activity, 2)
        player_info.addLayout(character_info)
        player_layout.addLayout(player_info, 1)
        card_layout.addLayout(player_layout)
        layout.addWidget(self.player_card)
        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    @staticmethod
    def _build_metrics(
            keys: tuple[str, ...] = ("attendance", "raids", "points", "eternal_dkp", "streak"),
            *, columns: int = 2, list_mode: bool = False,
    ) -> tuple[QWidget, dict[str, QLabel]]:
        container = QWidget()
        labels: dict[str, QLabel] = {}
        titles = {
            "player_rank": tr("player_profile.player_rank"),
            "attendance": tr("player_profile.attendance"),
            "raids": tr("player_profile.raids"),
            "points": tr("raid_points.title"),
            "eternal_dkp": tr("raid_clm_admin.eternal_dkp"),
            "streak": tr("player_profile.streak"),
        }
        if list_mode:
            form = QFormLayout(container)
            form.setContentsMargins(0, 0, 0, 0)
            form.setHorizontalSpacing(14)
            form.setVerticalSpacing(2)
            for key in keys:
                value = QLabel("–")
                value.setStyleSheet("font-size:10pt;font-weight:700;")
                form.addRow(QLabel(titles[key]), value)
                labels[key] = value
            return container, labels
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)
        for index, key in enumerate(keys):
            title = titles[key]
            card = QFrame()
            card.setProperty("innerCard", True)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(7, 4, 7, 4)
            heading = QLabel(title)
            heading.setObjectName("subtle")
            value = QLabel("–")
            value.setStyleSheet("font-size:10pt;font-weight:700;")
            value.setWordWrap(True)
            card.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            card_layout.addWidget(heading)
            card_layout.addWidget(value)
            grid.addWidget(card, index // max(1, columns), index % max(1, columns))
            labels[key] = value
        return container, labels

    def set_point_system(self, mode: str) -> None:
        title = (
            tr("raid_points.title") if mode == POINT_MODE_RAID
            else tr("player_profile.dkp") if mode == POINT_MODE_ETERNAL
            else tr("raid_points.title")
        )
        self.character_details_form.setRowVisible(
            self.character_metric_labels["points"],
            mode in {POINT_MODE_RAID, POINT_MODE_ETERNAL},
        )
        heading = self.character_details_form.labelForField(
            self.character_metric_labels["points"],
        )
        if heading is not None:
            heading.setText(title)

    def set_character_navigation(self, *, has_previous: bool, has_next: bool) -> None:
        self.character_previous_button.setEnabled(has_previous)
        self.character_next_button.setEnabled(has_next)

    def set_character_selection(self, member_id: str | None) -> None:
        self.character_combo.blockSignals(True)
        index = self.character_combo.findData(member_id)
        self.character_combo.setCurrentIndex(index if index >= 0 else -1)
        self.character_combo.blockSignals(False)

    def _player_changed(self, _index: int) -> None:
        player_id = str(self.player_combo.currentData() or "")
        if player_id:
            self.playerSelected.emit(player_id)

    def _character_changed(self, _index: int) -> None:
        member_id = str(self.character_combo.currentData() or "")
        if member_id:
            self.characterSelected.emit(member_id)

    def set_player_options(self, options: Iterable[tuple[str, str]], current: str) -> None:
        self.player_combo.blockSignals(True)
        self.player_combo.clear()
        for label, player_id in options:
            self.player_combo.addItem(label, player_id)
        index = self.player_combo.findData(current)
        self.player_combo.setCurrentIndex(index if index >= 0 else -1)
        self.player_combo.blockSignals(False)

    def set_character_options(self, options: Iterable[tuple[str, str]], current: str | None) -> None:
        self.character_combo.blockSignals(True)
        self.character_combo.clear()
        for label, member_id in options:
            self.character_combo.addItem(label, member_id)
        index = self.character_combo.findData(current)
        self.character_combo.setCurrentIndex(index if index >= 0 else -1)
        self.character_combo.blockSignals(False)


class GuildGearCheckerQt(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} · Qt Preview {QT_PREVIEW_VERSION}")
        self.setMinimumSize(1040, 680)
        self.model = GuildModel()
        self.model.new_empty()
        self.selected_member_id: str | None = None
        self.member_tab = "Gildenliste"
        self.sort_state: dict[str, tuple[str, bool]] = {}
        self._suite_settings_path = app_base_dir() / "config" / "suite_settings.json"
        self._suite_settings = read_suite_settings(self._suite_settings_path)
        self._clm_refresh_service = ClmDkpRefreshService()
        self._clm_dkp_by_member_id: dict[str, int | float] = {}
        self._raid_point_projection: tuple[object, ...] | None = None
        self._raid_view_dirty = {
            "raids": True, "attendance": True, "matrix": True, "history": True,
        }
        self._reward_registry = RewardRegistry()
        self._reward_assignments = RewardAssignments()
        self.gear_outdated_tracking = bool(self._suite_settings.get("gear_outdated_tracking", False))
        self.gear_outdated_days = normalize_outdated_days(
            self._suite_settings.get("gear_outdated_days", GEAR_OUTDATED_DEFAULT_DAYS)
        )
        self._grave_pixmaps: dict[str, QPixmap] = {}
        self._graveyard_template_cache: dict[tuple, object] = {}
        self._graveyard_card_cache: dict[tuple, QPixmap] = {}
        try:
            self._graveyard_zoom_percent = max(60, min(140, int(self._suite_settings.get("graveyard_zoom_percent", 100))))
        except (TypeError, ValueError):
            self._graveyard_zoom_percent = 100
        self._graveyard_zoom_pending = self._graveyard_zoom_percent
        self._graveyard_zoom_timer = QTimer(self)
        self._graveyard_zoom_timer.setSingleShot(True)
        self._graveyard_zoom_timer.setInterval(110)
        self._graveyard_zoom_timer.timeout.connect(self._apply_graveyard_zoom)
        try:
            self._roster_zoom_percent = max(60, min(140, int(self._suite_settings.get("roster_zoom_percent", 100))))
        except (TypeError, ValueError):
            self._roster_zoom_percent = 100
        self._roster_zoom_pending = self._roster_zoom_percent
        self._roster_zoom_timer = QTimer(self)
        self._roster_zoom_timer.setSingleShot(True)
        self._roster_zoom_timer.setInterval(90)
        self._roster_zoom_timer.timeout.connect(self._apply_roster_zoom)
        self._roster_cards: list[QWidget] = []
        self._roster_view_mode = "cards"
        self._roster_cards_dirty = True
        self._roster_list_dirty = True
        self._roster_list_sort_column = 0
        self._roster_list_sort_order = Qt.SortOrder.AscendingOrder
        self._member_table_refreshing = False
        self._project_handoff_session_id: str | None = None
        self._project_handoff_processed_tokens: set[str] = set()
        self._project_handoff_file_signatures: set[tuple[str, int, int]] = set()
        self._nav_buttons: dict[str, QPushButton] = {}
        self._member_subnav_buttons: dict[str, QPushButton] = {}
        self._pages: dict[str, QWidget] = {}
        self._player_profile_return_page = "rooster"
        self._player_profile: PlayerProfileViewModel | None = None

        self._load_qt_font()
        self.setStyleSheet(STYLE_SHEET)
        self._build_menu()
        self._build_ui()
        self._restore_geometry()
        self._load_autosave_or_seed()
        self.refresh_all(select_first=False)

        self._portrait_timer = QTimer(self)
        self._portrait_timer.setInterval(1600)
        self._portrait_timer.timeout.connect(self._refresh_selected_portrait_only)
        self._portrait_timer.start()

        self._grabber_actions_timer = QTimer(self)
        self._grabber_actions_timer.setInterval(500)
        self._grabber_actions_timer.timeout.connect(self._poll_project_handoff)
        self._grabber_actions_timer.start()

    # ---------- setup ----------
    def _load_qt_font(self) -> None:
        font_path = app_base_dir() / "assets" / "fonts" / "LifeCraft_Font.ttf"
        self.decorative_font_family = "Segoe UI"
        if font_path.is_file():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
            if families:
                self.decorative_font_family = families[0]

    def _restore_geometry(self) -> None:
        raw = str(self._suite_settings.get("checker_qt_geometry") or "")
        import re
        match = re.fullmatch(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", raw)
        if match:
            width, height, x, y = map(int, match.groups())
            screen = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else QRect(0, 0, 1440, 900)
            width = min(max(1040, width), screen.width())
            height = min(max(680, height), screen.height())
            if screen.adjusted(-200, -100, 200, 100).contains(QPoint(x, y)):
                self.setGeometry(x, y, width, height)
                return
        screen = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else QRect(0, 0, 1440, 900)
        width = min(1500, max(1040, int(screen.width() * 0.88)))
        height = min(920, max(680, int(screen.height() * 0.90)))
        x = screen.x() + max(0, (screen.width() - width) // 2)
        y = screen.y() + max(0, (screen.height() - height) // 2)
        self.setGeometry(x, y, width, height)

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu(tr("common.file"))
        actions = (
            (tr("checker.new_empty"), self.new_project),
            (tr("checker.open"), self.open_project),
            (tr("common.save"), self.save_project),
            (tr("checker.save_as"), self.save_project_as),
        )
        for text, callback in actions:
            action = QAction(text, self)
            action.triggered.connect(callback)
            menu.addAction(action)
        menu.addSeparator()
        export = QAction(tr("checker.export"), self)
        export.triggered.connect(self.export_project)
        menu.addAction(export)
        package = QAction(tr("checker.export_with_portraits"), self)
        package.triggered.connect(self.export_project_with_portraits)
        menu.addAction(package)
        package_import = QAction(tr("checker.package_import"), self)
        package_import.triggered.connect(self.import_project_with_portraits)
        menu.addAction(package_import)
        menu.addSeparator()
        quit_action = QAction(tr("common.quit"), self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

        tools = self.menuBar().addMenu(tr("common.tools"))
        grabber = QAction(tr("checker.launch_grabber"), self)
        grabber.triggered.connect(self.open_portrait_grabber)
        tools.addAction(grabber)
        portrait_folder = QAction(tr("checker.open_portrait_folder"), self)
        portrait_folder.triggered.connect(self.open_active_portrait_folder)
        tools.addAction(portrait_folder)
        roster_export = QAction(tr("roster.export_png"), self)
        roster_export.triggered.connect(self.export_roster_png)
        tools.addAction(roster_export)
        legacy = QAction(tr("checker.launch_legacy"), self)
        legacy.triggered.connect(self.launch_legacy_checker)
        tools.addAction(legacy)

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setCentralWidget(root)

        header = HeaderWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 14, 18, 12)
        title_box = QVBoxLayout()
        self.banner_title = QLabel(tr("checker.title"))
        self.banner_title.setObjectName("appTitle")
        font = QFont(self.decorative_font_family, 24)
        self.banner_title.setFont(font)
        title_box.addWidget(self.banner_title)
        self.project_label = QLabel("")
        self.project_label.setObjectName("appMeta")
        title_box.addWidget(self.project_label)
        header_layout.addLayout(title_box)
        header_layout.addStretch(1)
        grabber_button = QPushButton(tr("checker.portrait_grabber"))
        grabber_button.setToolTip(tr("checker.grabber_handoff"))
        grabber_button.clicked.connect(self.open_portrait_grabber)
        header_layout.addWidget(grabber_button)
        version = QLabel(f"Qt · {QT_PREVIEW_VERSION}\nEU · Stitches · Classic Era")
        version.setObjectName("appMeta")
        version.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(version)
        outer.addWidget(header)

        nav = QFrame()
        nav.setObjectName("navBar")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(14, 0, 14, 0)
        nav_layout.setSpacing(2)
        for key, label in (
            ("rooster", tr("tabs.roster")),
            ("graveyard", tr("tabs.graveyard")),
            ("management", tr("tabs.management")),
            ("raid", tr("tabs.raid")),
            ("settings", tr("tabs.settings")),
        ):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, page=key: self.switch_page(page))
            nav_layout.addWidget(button)
            self._nav_buttons[key] = button
        nav_layout.addStretch(1)
        outer.addWidget(nav)

        self.stack = QStackedWidget()
        self._pages["rooster"] = self._build_roster_page()
        self.player_profile_page = PlayerProfilePage()
        self.player_profile_page.playerSelected.connect(self.open_player_profile)
        self.player_profile_page.characterSelected.connect(self._select_profile_character)
        self.player_profile_page.previousCharacterRequested.connect(self._select_previous_profile_character)
        self.player_profile_page.nextCharacterRequested.connect(self._select_next_profile_character)
        self.player_profile_page.backRequested.connect(self.close_player_profile)
        self._pages["player_profile"] = self.player_profile_page
        self._pages["graveyard"] = self._build_graveyard_page()
        self._pages["management"] = self._build_member_page()
        self._pages["raid"] = self._build_raid_page()
        self._pages["settings"] = self._build_settings_page()
        for page in self._pages.values():
            self.stack.addWidget(page)
        outer.addWidget(self.stack, 1)

        status = QStatusBar()
        self.setStatusBar(status)
        self.status_label = QLabel(tr("common.ready"))
        self.status_label.setObjectName("subtle")
        status.addWidget(self.status_label, 1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("subtle")
        status.addPermanentWidget(self.count_label)

        self.switch_page("rooster", refresh=False)

    # ---------- Verwaltung (interne member_* Namen bleiben für Kompatibilität bestehen) ----------
    def _build_member_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(9)

        top = QHBoxLayout()
        title = QLabel(tr("checker.management_title"))
        title.setObjectName("sectionTitle")
        top.addWidget(title)
        top.addStretch(1)
        self.member_count = QLabel("")
        self.member_count.setObjectName("subtle")
        top.addWidget(self.member_count)
        layout.addLayout(top)

        guild_card = QFrame()
        guild_card.setProperty("card", True)
        guild_layout = QHBoxLayout(guild_card)
        guild_layout.setContentsMargins(12, 8, 12, 8)
        guild_layout.addWidget(QLabel(tr("raid_clm_admin.guild_master_data")))
        self.guild_name_edit = QLineEdit()
        self.guild_name_edit.setPlaceholderText(tr("raid_clm_admin.guild_name"))
        self.guild_name_edit.setMaximumWidth(220)
        guild_layout.addWidget(self.guild_name_edit)
        self.guild_realm_edit = QLineEdit()
        self.guild_realm_edit.setPlaceholderText(tr("raid_clm_admin.realm"))
        self.guild_realm_edit.setMaximumWidth(180)
        guild_layout.addWidget(self.guild_realm_edit)
        save_guild = set_button_role(
            QPushButton(tr("raid_clm_admin.save_guild_master_data")), primary=True,
        )
        save_guild.clicked.connect(self.save_guild_master_data)
        guild_layout.addWidget(save_guild)
        assignments = QPushButton(tr("raid_clm_admin.player_assignments"))
        assignments.clicked.connect(self.open_player_assignments)
        guild_layout.addWidget(assignments)
        guild_layout.addStretch(1)
        layout.addWidget(guild_card)

        actions = QHBoxLayout()
        add_button = set_button_role(QPushButton(tr("checker.new_player")), primary=True)
        remove_button = set_button_role(QPushButton(tr("common.remove")), danger=True)
        wipe_button = set_button_role(QPushButton(tr("checker.wipe")), danger=True)
        csv_button = QPushButton(tr("checker.load_csv"))
        save_button = QPushButton(tr("common.save"))
        add_button.clicked.connect(self.add_member_dialog)
        remove_button.clicked.connect(self.remove_selected_member)
        wipe_button.clicked.connect(self.open_wipe_dialog)
        csv_button.clicked.connect(self.import_csv)
        save_button.clicked.connect(self.save_selected_member)
        self.member_remove_button = remove_button
        self.member_wipe_button = wipe_button
        for button in (add_button, remove_button, wipe_button, csv_button, save_button):
            actions.addWidget(button)
        actions.addStretch(1)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("checker.search_placeholder"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMaximumWidth(260)
        self.search_edit.textChanged.connect(lambda _text: self.refresh_member_table())
        actions.addWidget(self.search_edit)
        layout.addLayout(actions)

        filters = QHBoxLayout()
        filters.setSpacing(6)
        for tab_name, text in (
            ("Gildenliste", tr("tabs.guild")),
            ("Handlungsbedarf", tr("tabs.action")),
            ("Ungeprüft", tr("tabs.unchecked")),
            ("Inaktiv", tr("tabs.inactive")),
            ("Tot", tr("life.dead")),
            ("Alle Charaktere", tr("tabs.all_characters")),
        ):
            button = QPushButton(text)
            button.setObjectName("subnavButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, tab=tab_name: self.set_member_tab(tab))
            filters.addWidget(button)
            self._member_subnav_buttons[tab_name] = button
        filters.addStretch(1)
        self.gear_filter_combo = QComboBox()
        self.gear_filter_combo.addItems([tr("common.all")] + [gear_status_display(value) for value in GEAR_VALUES])
        self.gear_filter_combo.currentIndexChanged.connect(lambda _index: self.refresh_member_table())
        self.gear_filter_combo.setMinimumWidth(150)
        filters.addWidget(self.gear_filter_combo)
        layout.addLayout(filters)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.member_table = MemberTable()
        self.member_table.currentItemChanged.connect(self._member_current_item_changed)
        self.member_table.itemChanged.connect(self._member_table_item_changed)
        self.member_table.paste_requested.connect(self._paste_member_table)
        splitter.addWidget(self.member_table)
        self.detail_panel = self._build_detail_panel()
        splitter.addWidget(self.detail_panel)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 4)
        splitter.setCollapsible(1, False)
        splitter.setSizes([920, 460])
        layout.addWidget(splitter, 1)

        self.set_member_tab("Gildenliste", refresh=False)
        return page

    def _build_detail_panel(self) -> QWidget:
        panel = QFrame()
        panel.setProperty("card", True)
        panel.setMinimumWidth(360)
        panel.setMinimumHeight(260)
        panel.setMaximumWidth(470)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.detail_content = QWidget(panel)
        content_layout = QVBoxLayout(self.detail_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        hero = QHBoxLayout()
        hero.setSpacing(8)
        self.detail_portrait = CoverImageLabel(tr("checker.missing_portrait"))
        self.detail_reward_portrait = RewardPortraitContainer(
            self.detail_portrait,
            QSize(MEMBER_DETAIL_PORTRAIT_SIZE, MEMBER_DETAIL_PORTRAIT_SIZE),
            rank_asset_size=96,
        )
        self.detail_portrait.clicked.connect(self.open_active_portrait_folder)
        hero.addWidget(self.detail_reward_portrait)
        self.detail_rank_icon = QLabel()
        self.detail_rank_icon.setFixedSize(96, 96)
        self.detail_rank_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_rank_icon.setStyleSheet("background:transparent;border:none;")
        self.detail_rank_icon.hide()
        hero.addWidget(self.detail_rank_icon, 0, Qt.AlignmentFlag.AlignTop)
        identity = QVBoxLayout()
        identity.setContentsMargins(0, 0, 0, 0)
        identity.setSpacing(2)
        self.detail_name = QLabel("–")
        self.detail_name.setObjectName("memberName")
        self.detail_name.setWordWrap(True)
        identity.addWidget(self.detail_name)
        self.detail_class = QLabel("–")
        self.detail_class.setObjectName("subtle")
        identity.addWidget(self.detail_class)
        self.detail_life = QLabel("–")
        self.detail_life.setObjectName("statusPill")
        self.detail_life.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        identity.addWidget(self.detail_life)
        identity.addStretch(1)
        hero.addLayout(identity, 1)
        content_layout.addLayout(hero)

        self.detail_sections = QWidget(self.detail_content)
        sections_layout = QVBoxLayout(self.detail_sections)
        sections_layout.setContentsMargins(0, 0, 0, 0)
        sections_layout.setSpacing(5)
        for title, widget in (
            (tr("checker.overview_tab"), self._build_detail_overview()),
            (tr("checker.gear_tab"), self._build_detail_gear()),
            (tr("checker.notes_tab"), self._build_detail_notes()),
        ):
            heading = QLabel(title)
            heading.setObjectName("subtle")
            heading.setStyleSheet("font-weight:700;")
            sections_layout.addWidget(heading)
            sections_layout.addWidget(widget)
        self.detail_points_section = self._build_detail_points()
        sections_layout.addWidget(self.detail_points_section)
        self.detail_dkp_section = self._build_detail_dkp()
        sections_layout.addWidget(self.detail_dkp_section)
        self.detail_sections.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        content_layout.addWidget(self.detail_sections)

        self.detail_scroll = QScrollArea(panel)
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_scroll.setMinimumHeight(120)
        self.detail_scroll.setWidget(self.detail_content)
        self.detail_scroll.setMaximumHeight(
            self.detail_content.sizeHint().height() + MEMBER_DETAIL_SCROLL_HEIGHT_TOLERANCE
        )
        layout.addWidget(self.detail_scroll)

        self.detail_action_box = QWidget(panel)
        self.detail_action_box.setObjectName("detailActions")
        self.detail_action_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        buttons = QGridLayout(self.detail_action_box)
        buttons.setContentsMargins(0, 2, 0, 2)
        buttons.setHorizontalSpacing(6)
        buttons.setVerticalSpacing(6)
        self.detail_save_button = set_button_role(QPushButton(tr("common.save")), primary=True)
        self.armory_button = QPushButton(tr("checker.open_armory"))
        self.activity_button = QPushButton("")
        self.life_button = set_button_role(QPushButton(""), danger=True)
        for button in (self.detail_save_button, self.armory_button, self.activity_button, self.life_button):
            button.setObjectName("detailAction")
            button.setMinimumHeight(30)
        self.detail_save_button.clicked.connect(self.save_selected_member)
        self.armory_button.clicked.connect(self.open_armory_selected)
        self.activity_button.clicked.connect(self.toggle_activity_selected)
        self.life_button.clicked.connect(self.mark_dead_selected)
        buttons.addWidget(self.detail_save_button, 0, 0)
        buttons.addWidget(self.armory_button, 0, 1)
        buttons.addWidget(self.activity_button, 1, 0)
        buttons.addWidget(self.life_button, 1, 1)
        layout.addWidget(self.detail_action_box)
        return panel

    def _build_detail_overview(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        form.setContentsMargins(4, 3, 4, 3)
        form.setHorizontalSpacing(7)
        form.setVerticalSpacing(1)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.detail_overview_form = form
        self.race_combo = QComboBox()
        self.race_combo.addItems([tr("common.not_set"), *race_display_values()])
        self.class_combo = QComboBox()
        self.class_combo.addItems([tr("common.not_set"), *CLASS_NAMES])
        self.class_combo.currentTextChanged.connect(self._class_changed)
        self.spec_combo = QComboBox()
        self.character_type_combo = QComboBox()
        self.character_type_combo.addItems([character_type_display(value) for value in CHARACTER_TYPES])
        self.character_type_combo.currentTextChanged.connect(self._detail_character_type_changed)
        self.associated_main_combo = QComboBox()
        self.raid_role_combo = QComboBox()
        self.raid_role_combo.addItems([raid_role_display(value) for value in RAID_ROLES])
        for combo in (
            self.race_combo, self.class_combo, self.spec_combo,
            self.character_type_combo, self.associated_main_combo, self.raid_role_combo,
        ):
            combo.setMinimumHeight(26)
        form.addRow(tr("checker.race"), self.race_combo)
        form.addRow(tr("common.class"), self.class_combo)
        form.addRow(tr("common.spec"), self.spec_combo)
        form.addRow(tr("checker.character_type"), self.character_type_combo)
        form.addRow(tr("checker.associated_main"), self.associated_main_combo)
        form.addRow(tr("checker.raid_role"), self.raid_role_combo)
        form.setRowVisible(self.associated_main_combo, False)
        return widget


    def _build_detail_gear(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        form.setContentsMargins(6, 5, 6, 5)
        form.setHorizontalSpacing(7)
        form.setVerticalSpacing(2)
        self.gear_combo = QComboBox()
        self.gear_combo.addItems([gear_status_display(value) for value in GEAR_VALUES])
        self.raid_status_combo = QComboBox()
        self.raid_status_combo.addItems([raid_status_display(value) for value in RAID_STATUS_VALUES])
        self.gear_combo.setMinimumHeight(28)
        self.raid_status_combo.setMinimumHeight(28)
        self.last_checked_value = QLabel("–")
        self.recheck_button = QPushButton(tr("checker.confirm_gear_recheck"))
        self.recheck_button.clicked.connect(self.confirm_recheck_selected)
        form.addRow(tr("gear.label"), self.gear_combo)
        form.addRow(tr("raid_status.label"), self.raid_status_combo)
        form.addRow(tr("checker.last_checked"), self.last_checked_value)
        form.addRow("", self.recheck_button)
        return widget

    def _build_detail_notes(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 5, 6, 5)
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText(tr("checker.detail_note"))
        self.notes_edit.setMinimumHeight(100)
        layout.addWidget(self.notes_edit)
        return widget

    def _build_detail_points(self) -> QWidget:
        section = QFrame()
        section.setProperty("innerCard", True)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(4)
        self.detail_points_title = QLabel(tr("raid_points.title"))
        self.detail_points_title.setStyleSheet("font-weight:700;")
        layout.addWidget(self.detail_points_title)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        self.detail_points_form = form
        self.detail_current_dkp = QLabel("—")
        self.detail_character_points = QLabel("0")
        self.detail_player_points = QLabel("0")
        form.addRow(tr("raid_clm_admin.current_dkp"), self.detail_current_dkp)
        form.addRow(tr("raid_points.character_points"), self.detail_character_points)
        form.addRow(tr("raid_points.player_total"), self.detail_player_points)
        form.setRowVisible(self.detail_current_dkp, False)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.detail_character_history = QPushButton(tr("raid_points.point_history"))
        self.detail_character_history.clicked.connect(
            lambda: self.open_point_history_for_member(self.selected_member_id or "")
        )
        self.detail_player_history = QPushButton(tr("raid_points.player_history"))
        self.detail_player_history.clicked.connect(
            lambda: self.open_point_history_for_player(
                getattr(self.model.find_by_id(self.selected_member_id or ""), "playerId", "")
            )
        )
        actions.addWidget(self.detail_character_history)
        actions.addWidget(self.detail_player_history)
        layout.addLayout(actions)
        section.setVisible(self.model.raid_points.enabled)
        return section

    def _build_detail_dkp(self) -> QWidget:
        section = QFrame()
        section.setProperty("innerCard", True)
        layout = QFormLayout(section)
        layout.setContentsMargins(8, 7, 8, 7)
        self.detail_dkp_value = QLabel("—")
        layout.addRow(tr("raid_clm_admin.character_dkp"), self.detail_dkp_value)
        section.setVisible(self.model.dkp_enabled)
        return section

    # ---------- Roster ----------
    def _build_roster_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)
        top = QHBoxLayout()
        title = QLabel(tr("roster.title"))
        title.setObjectName("sectionTitle")
        top.addWidget(title)
        self.roster_search_edit = QLineEdit()
        self.roster_search_edit.setPlaceholderText(tr("roster.search_placeholder"))
        self.roster_search_edit.setClearButtonEnabled(True)
        self.roster_search_edit.setMaximumWidth(260)
        self.roster_search_edit.textChanged.connect(self.refresh_roster)
        top.addWidget(self.roster_search_edit)
        top.addStretch(1)

        self.roster_cards_button = QPushButton(tr("roster.cards_view"))
        self.roster_cards_button.setCheckable(True)
        self.roster_cards_button.setChecked(True)
        self.roster_cards_button.setObjectName("subnavButton")
        self.roster_cards_button.clicked.connect(lambda: self._set_roster_view("cards"))
        self.roster_list_button = QPushButton(tr("roster.list_view"))
        self.roster_list_button.setCheckable(True)
        self.roster_list_button.setObjectName("subnavButton")
        self.roster_list_button.clicked.connect(lambda: self._set_roster_view("list"))
        top.addWidget(self.roster_cards_button)
        top.addWidget(self.roster_list_button)

        zoom_frame = QFrame()
        zoom_frame.setObjectName("graveZoomBar")
        zoom_row = QHBoxLayout(zoom_frame)
        zoom_row.setContentsMargins(8, 4, 8, 4)
        zoom_row.setSpacing(6)
        zoom_row.addWidget(QLabel(tr("roster.view")))
        roster_minus = QPushButton("−")
        roster_plus = QPushButton("+")
        roster_minus.setFixedSize(30, 30)
        roster_plus.setFixedSize(30, 30)
        self.roster_zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.roster_zoom_slider.setRange(60, 140)
        self.roster_zoom_slider.setSingleStep(10)
        self.roster_zoom_slider.setPageStep(10)
        self.roster_zoom_slider.setValue(self._roster_zoom_percent)
        self.roster_zoom_slider.setFixedWidth(150)
        self.roster_zoom_value = QLabel(f"{self._roster_zoom_percent} %")
        self.roster_zoom_value.setMinimumWidth(48)
        self.roster_zoom_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        roster_minus.clicked.connect(
            lambda: self.roster_zoom_slider.setValue(max(60, self.roster_zoom_slider.value() - 10))
        )
        roster_plus.clicked.connect(
            lambda: self.roster_zoom_slider.setValue(min(140, self.roster_zoom_slider.value() + 10))
        )
        self.roster_zoom_slider.valueChanged.connect(self._schedule_roster_zoom)
        zoom_row.addWidget(roster_minus)
        zoom_row.addWidget(self.roster_zoom_slider)
        zoom_row.addWidget(roster_plus)
        zoom_row.addWidget(self.roster_zoom_value)
        top.addWidget(zoom_frame)

        export_button = QPushButton(tr("roster.export_png"))
        export_button.clicked.connect(self.export_roster_png)
        top.addWidget(export_button)
        layout.addLayout(top)

        self.roster_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.roster_scroll = QScrollArea()
        self.roster_scroll.setWidgetResizable(True)
        self.roster_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.roster_content = QWidget()
        self.roster_content.setMinimumWidth(0)
        self.roster_layout = QVBoxLayout(self.roster_content)
        self.roster_layout.setContentsMargins(4, 4, 4, 8)
        self.roster_layout.setSpacing(18)
        self.roster_scroll.setWidget(self.roster_content)
        self.roster_content_stack = QStackedWidget()
        self.roster_content_stack.addWidget(self.roster_scroll)
        self.roster_list = CopyableReadOnlyTable(0, 10)
        self.roster_list.setHorizontalHeaderLabels([
            tr("roster.column_name"), tr("roster.column_class"), tr("roster.column_role"),
            tr("roster.column_character_type"), tr("roster.column_gear"),
            tr("roster.column_raid_status"), tr("roster.column_life_status"),
            tr("roster.column_current_dkp"), tr("roster.column_eternal_character"),
            tr("roster.column_eternal_player"),
        ])
        self.roster_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.roster_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.roster_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.roster_list.setAlternatingRowColors(True)
        self.roster_list.verticalHeader().setVisible(False)
        self.roster_list.horizontalHeader().setStretchLastSection(True)
        self.roster_list.cellClicked.connect(lambda row, _column: self._roster_list_clicked(row))
        self.roster_list.cellDoubleClicked.connect(self._roster_list_profile_requested)
        self.roster_list.horizontalHeader().sortIndicatorChanged.connect(self._roster_list_sort_changed)
        self.roster_content_stack.addWidget(self.roster_list)
        self.roster_splitter.addWidget(self.roster_content_stack)
        self.roster_detail_panel = self._build_roster_detail_panel()
        self.roster_splitter.addWidget(self.roster_detail_panel)
        self.roster_detail_panel.hide()
        self.roster_splitter.setStretchFactor(0, 1)
        self.roster_splitter.setCollapsible(0, False)
        self.roster_splitter.setCollapsible(1, True)
        self.roster_splitter.splitterMoved.connect(
            lambda _pos, _index: self._schedule_roster_reflow()
        )
        layout.addWidget(self.roster_splitter, 1)
        return page

    def _build_roster_detail_panel(self) -> QWidget:
        panel = QFrame()
        panel.setProperty("card", True)
        panel.setMinimumWidth(360)
        panel.setMaximumWidth(480)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        self.roster_detail_scroll = QScrollArea(panel)
        self.roster_detail_scroll.setWidgetResizable(True)
        self.roster_detail_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.roster_detail_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.roster_detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        panel_layout.addWidget(self.roster_detail_scroll)
        roster_detail_content = QWidget()
        roster_detail_content.setStyleSheet("background:transparent;")
        self.roster_detail_scroll.setWidget(roster_detail_content)

        layout = QVBoxLayout(roster_detail_content)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        self.roster_detail_name = QLabel("–")
        self.roster_detail_name.setObjectName("memberName")
        self.roster_detail_name.setWordWrap(True)
        self.roster_detail_name.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self.roster_detail_name, 1)
        close = QPushButton("×")
        close.setToolTip(tr("roster.close_detail"))
        close.setFixedSize(28, 28)
        close.clicked.connect(self._close_roster_detail)
        title_row.addWidget(close, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        layout.addLayout(title_row)

        hero = QVBoxLayout()
        hero.setSpacing(3)
        self.roster_detail_portrait = CoverImageLabel(tr("checker.missing_portrait"))
        # Der kleinere Gesamtblock lässt dem Informationsbereich mehr Höhe;
        # die tatsächliche Portraithöhe folgt weiterhin der Rahmenöffnung.
        self.roster_reward_portrait = RewardPortraitContainer(
            self.roster_detail_portrait,
            QSize(120, 220),
            rank_asset_size=96,
        )
        identity = QVBoxLayout()
        identity.setContentsMargins(0, 0, 0, 0)
        identity.setSpacing(3)
        self.roster_detail_class = QLabel("–")
        self.roster_detail_class.setObjectName("subtle")
        self.roster_detail_class.setTextFormat(Qt.TextFormat.RichText)
        self.roster_detail_class.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        identity.addWidget(self.roster_detail_class)
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(4)
        status_row.addStretch(1)
        self.roster_detail_life = QLabel("–")
        self.roster_detail_life.setObjectName("statusPill")
        self.roster_detail_life.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        status_row.addWidget(self.roster_detail_life)
        self.roster_detail_raid = QLabel("")
        self.roster_detail_raid.setObjectName("statusPill")
        self.roster_detail_raid.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        status_row.addWidget(self.roster_detail_raid)
        status_row.addStretch(1)
        identity.addLayout(status_row)
        hero.addLayout(identity)
        portrait_rank_row = QHBoxLayout()
        portrait_rank_row.setContentsMargins(0, 0, 0, 0)
        portrait_rank_row.setSpacing(28)
        portrait_rank_row.addStretch(1)
        portrait_rank_row.addWidget(
            self.roster_reward_portrait,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        self.roster_rank_slot = QWidget()
        self.roster_rank_slot.setFixedSize(116, 108)
        rank_slot_layout = QHBoxLayout(self.roster_rank_slot)
        rank_slot_layout.setContentsMargins(12, 0, 0, 0)
        rank_slot_layout.setSpacing(0)
        self.roster_rank_icon = QLabel()
        self.roster_rank_icon.setFixedSize(96, 96)
        self.roster_rank_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.roster_rank_icon.setStyleSheet("background:transparent;border:none;")
        self.roster_rank_icon.hide()
        rank_slot_layout.addWidget(
            self.roster_rank_icon,
            0,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
        )
        portrait_rank_row.addWidget(
            self.roster_rank_slot,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        portrait_rank_row.addStretch(1)
        hero.addLayout(portrait_rank_row)
        layout.addLayout(hero)

        overview = QWidget()
        overview_form = QFormLayout(overview)
        overview_form.setContentsMargins(10, 8, 10, 8)
        self.roster_detail_type = QLabel("–")
        self.roster_detail_role = QLabel("–")
        self.roster_detail_rank = QLabel("–")
        self.roster_detail_checked = QLabel("–")
        overview_form.addRow(tr("checker.character_type"), self.roster_detail_type)
        overview_form.addRow(tr("checker.raid_role"), self.roster_detail_role)
        overview_form.addRow(tr("roster.character_rank"), self.roster_detail_rank)
        overview_form.addRow(tr("checker.last_checked"), self.roster_detail_checked)
        layout.addWidget(overview)

        self.roster_points_section = QFrame()
        self.roster_points_section.setProperty("innerCard", True)
        roster_points_layout = QVBoxLayout(self.roster_points_section)
        roster_points_layout.setContentsMargins(10, 8, 10, 8)
        self.roster_points_title = QLabel(tr("raid_points.title"))
        self.roster_points_title.setStyleSheet("font-weight:700;")
        roster_points_layout.addWidget(self.roster_points_title)
        roster_points_form = QFormLayout()
        roster_points_form.setContentsMargins(0, 0, 0, 0)
        self.roster_points_form = roster_points_form
        self.roster_current_dkp = QLabel("—")
        self.roster_character_points = QLabel("0")
        self.roster_player_points = QLabel("0")
        roster_points_form.addRow(tr("raid_clm_admin.current_dkp"), self.roster_current_dkp)
        roster_points_form.addRow(tr("raid_points.character_points"), self.roster_character_points)
        roster_points_form.addRow(tr("raid_points.player_total"), self.roster_player_points)
        roster_points_form.setRowVisible(self.roster_current_dkp, False)
        roster_points_layout.addLayout(roster_points_form)
        roster_points_actions = QHBoxLayout()
        self.roster_character_history = QPushButton(tr("raid_points.point_history"))
        self.roster_character_history.clicked.connect(
            lambda: self.open_point_history_for_member(
                getattr(self, "roster_selected_member_id", "")
            )
        )
        self.roster_player_history = QPushButton(tr("raid_points.player_history"))
        self.roster_player_history.clicked.connect(
            lambda: self.open_point_history_for_player(
                getattr(
                    self.model.find_by_id(getattr(self, "roster_selected_member_id", "")),
                    "playerId", "",
                )
            )
        )
        roster_points_actions.addWidget(self.roster_character_history)
        roster_points_actions.addWidget(self.roster_player_history)
        roster_points_layout.addLayout(roster_points_actions)
        self.roster_points_section.setVisible(self.model.raid_points.enabled)
        layout.addWidget(self.roster_points_section)

        self.roster_dkp_section = QFrame()
        self.roster_dkp_section.setProperty("innerCard", True)
        roster_dkp_layout = QFormLayout(self.roster_dkp_section)
        roster_dkp_layout.setContentsMargins(10, 8, 10, 8)
        self.roster_dkp_value = QLabel("—")
        roster_dkp_layout.addRow(tr("raid_clm_admin.character_dkp"), self.roster_dkp_value)
        self.roster_dkp_section.setVisible(self.model.dkp_enabled)
        layout.addWidget(self.roster_dkp_section)

        notes_title = QLabel(tr("roster.notes"))
        notes_title.setObjectName("subtle")
        layout.addWidget(notes_title)
        self.roster_detail_notes = QTextEdit()
        self.roster_detail_notes.setReadOnly(False)
        self.roster_detail_notes.textChanged.connect(self._roster_notes_changed)
        self.roster_detail_notes.setMinimumHeight(100)
        self.roster_detail_notes.setStyleSheet("background:#10161d;border:1px solid #35414d;color:#eef2f5;")
        layout.addWidget(self.roster_detail_notes, 1)

        armory = QPushButton(tr("checker.open_armory"))
        armory.clicked.connect(lambda: self._open_armory_for_id(getattr(self, "roster_selected_member_id", "")))
        layout.addWidget(armory)
        self.roster_profile_button = QPushButton(tr("player_profile.open_profile"))
        self.roster_profile_button.clicked.connect(
            lambda: self.open_player_profile_for_member(
                getattr(self, "roster_selected_member_id", "")
            )
        )
        layout.addWidget(self.roster_profile_button)
        return panel

    def _close_roster_detail(self) -> None:
        self.roster_selected_member_id = None
        self.roster_reward_portrait.clear_reward_badge()
        self.roster_reward_portrait.clear_reward_frame()
        self.roster_rank_icon.clear()
        self.roster_rank_icon.hide()
        self.roster_detail_panel.hide()
        self._schedule_roster_reflow()

    def _roster_notes_changed(self) -> None:
        member = self.model.find_by_id(getattr(self, "roster_selected_member_id", ""))
        if member is not None and self.roster_detail_notes.hasFocus():
            member.note = self.roster_detail_notes.toPlainText()
            self.model.dirty = True

    def _schedule_roster_reflow(self) -> None:
        if not hasattr(self, "roster_scroll"):
            return
        # Programmatic splitter changes do not reliably emit splitterMoved on
        # every Qt/Windows build. Reflow once immediately and again after the
        # detail pane has finished changing the viewport geometry.
        QTimer.singleShot(0, self._reflow_roster_grids)
        QTimer.singleShot(60, self._reflow_roster_grids)
        QTimer.singleShot(180, self._reflow_roster_grids)

    def _reflow_roster_grids(self) -> None:
        if not hasattr(self, "roster_scroll") or not hasattr(self, "roster_content"):
            return
        viewport_width = self.roster_scroll.viewport().width()
        if viewport_width <= 0:
            return

        # The scroll viewport is the authoritative width. Using the section's
        # previous contentsRect creates a circular size-hint dependency and is
        # why the cards only reflowed after leaving and re-entering the page.
        self.roster_content.setMinimumWidth(0)
        self.roster_content.setMaximumWidth(viewport_width)
        self.roster_content.resize(viewport_width, self.roster_content.height())

        outer_margins = self.roster_layout.contentsMargins()
        section_width = max(
            1,
            viewport_width - outer_margins.left() - outer_margins.right(),
        )
        grids = getattr(self, "_roster_grids", ())
        for grid in grids:
            section = grid.parentWidget()
            if section is None:
                continue
            section.setMinimumWidth(0)
            section.setMaximumWidth(section_width)
            section.resize(section_width, section.height())
            section_layout = section.layout()
            margins = section_layout.contentsMargins() if section_layout is not None else None
            horizontal_margins = (
                margins.left() + margins.right() if margins is not None else 0
            )
            available = max(
                grid.card_width,
                section_width - horizontal_margins,
            )
            grid.setMinimumWidth(0)
            grid.setMaximumWidth(available)
            grid.resize(available, grid.height())
            grid.updateGeometry()
            grid.reflow()

    def _set_roster_view(self, mode: str) -> None:
        self._roster_view_mode = "list" if mode == "list" else "cards"
        self.roster_cards_button.setChecked(self._roster_view_mode == "cards")
        self.roster_list_button.setChecked(self._roster_view_mode == "list")
        self.roster_content_stack.setCurrentWidget(
            self.roster_list if self._roster_view_mode == "list" else self.roster_scroll
        )
        self._refresh_current_roster_view()

    def _roster_list_sort_changed(self, column: int, order: Qt.SortOrder) -> None:
        self._roster_list_sort_column = int(column)
        self._roster_list_sort_order = order

    def _roster_list_clicked(self, row: int) -> None:
        item = self.roster_list.item(row, 0)
        if item is not None:
            self._show_roster_detail(str(item.data(Qt.ItemDataRole.UserRole) or ""))

    def _roster_list_profile_requested(self, row: int, column: int) -> None:
        if column != 0:
            return
        item = self.roster_list.item(row, 0)
        if item is not None:
            self.open_player_profile_for_member(
                str(item.data(Qt.ItemDataRole.UserRole) or "")
            )

    def _roster_search_matches(self, member: Member) -> bool:
        query = self.roster_search_edit.text().strip().casefold()
        if not query:
            return True
        values = (
            member.name, member.className, member.spec,
            raid_role_display(member.raidRole), gear_status_display(member.gearStatus),
        )
        return any(query in str(value or "").casefold() for value in values)


    # ---------- Graveyard ----------
    def _build_graveyard_page(self) -> QWidget:
        page = GraveyardView(self.decorative_font_family, self._graveyard_zoom_percent)
        self.grave_view = page
        self.grave_scroll = page.scroll
        self.grave_canvas = page.canvas
        # v0.8.3: Friedhof ist im Checker eine reine Ansicht. Die charakterbezogene
        # Grabsteinbearbeitung liegt im Portrait Grabber; der Qt-Editor bleibt nur
        # als Legacy-Implementierung im Code erhalten und ist hier nicht erreichbar.
        self.grave_canvas.set_activation_enabled(False)
        page.zoomChanged.connect(self._schedule_graveyard_zoom)
        return page

    # ---------- Raid ----------
    def _build_raid_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 14)
        title = QLabel(tr("tabs.raid"))
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.raid_subtabs = QTabWidget()
        layout.addWidget(self.raid_subtabs, 1)

        raids_page = QWidget()
        raids_layout = QVBoxLayout(raids_page)
        actions = QHBoxLayout()
        for text, callback, role in (
            (tr("raids.create"), self.create_raid_dialog, "primary"),
            (tr("raids.bulk_action"), self.bulk_import_raid_csvs, "normal"),
            (tr("raids.edit"), self.edit_selected_raid, "normal"),
            (tr("raids.delete"), self.delete_selected_raid, "danger"),
            (tr("raids.reset_attendance"), self.reset_selected_raid_attendance, "normal"),
        ):
            button = QPushButton(text)
            set_button_role(button, primary=role == "primary", danger=role == "danger")
            button.clicked.connect(callback)
            actions.addWidget(button)
        self.raid_points_button = QPushButton(tr("raid_points.adjust"))
        self.raid_points_button.clicked.connect(self.adjust_selected_raid_points)
        self.raid_points_button.setVisible(self.model.raid_points.enabled)
        actions.addWidget(self.raid_points_button)
        actions.addStretch(1)
        raids_layout.addLayout(actions)

        split = QSplitter(Qt.Orientation.Vertical)
        self.raid_table = QTableWidget(0, 6)
        self.raid_table.setHorizontalHeaderLabels([
            tr("common.date"), tr("raids.raid_type"), tr("raids.raid"),
            tr("raids.participants"), tr("common.status"), tr("raids.warcraft_logs"),
        ])
        self.raid_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.raid_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.raid_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.raid_table.verticalHeader().setVisible(False)
        raid_header = self.raid_table.horizontalHeader()
        raid_header.setSectionsClickable(True)
        raid_header.setSortIndicatorShown(True)
        self._raid_sort_column = 0
        self._raid_sort_ascending = False
        raid_header.setSortIndicator(
            self._raid_sort_column, Qt.SortOrder.DescendingOrder,
        )
        for column in (0, 1, 3, 4, 5):
            raid_header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        raid_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.raid_table.itemSelectionChanged.connect(self.refresh_raid_participants)
        self.raid_table.cellClicked.connect(self._raid_table_clicked)
        raid_header.sectionClicked.connect(self._raid_table_sort_clicked)
        split.addWidget(self.raid_table)

        participants_frame = QFrame()
        participants_frame.setProperty("card", True)
        participants_layout = QVBoxLayout(participants_frame)
        participants_top = QHBoxLayout()
        participants_title = QLabel(tr("raids.raid_participants"))
        participants_title.setStyleSheet("font-size:12pt;font-weight:700;background:transparent;border:none;")
        participants_top.addWidget(participants_title)
        participants_top.addStretch(1)
        self.raid_toggle_bench_button = QPushButton(tr("raids.toggle_bench"))
        self.raid_toggle_bench_button.clicked.connect(self.toggle_selected_attendance_status)
        participants_top.addWidget(self.raid_toggle_bench_button)
        participants_layout.addLayout(participants_top)
        self.raid_participants_table = QTableWidget(0, 4)
        self.raid_participants_table.setHorizontalHeaderLabels([
            tr("raids.player"), tr("raids.character"), tr("raids.type"), tr("common.status"),
        ])
        self.raid_participants_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.raid_participants_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.raid_participants_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.raid_participants_table.verticalHeader().setVisible(False)
        participants_header = self.raid_participants_table.horizontalHeader()
        participants_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        participants_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        participants_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        participants_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.raid_participants_table.setColumnWidth(0, 180)
        participants_layout.addWidget(self.raid_participants_table)
        split.addWidget(participants_frame)
        split.setSizes([330, 290])
        raids_layout.addWidget(split, 1)
        self.raid_subtabs.addTab(raids_page, tr("raids.page_raids"))

        attendance_page = QWidget()
        attendance_layout = QVBoxLayout(attendance_page)
        self._build_raid_filters(attendance_layout, "matrix", include_limit=True)

        matrix_toolbar = QHBoxLayout()
        legend = QLabel(tr("raids.matrix_legend"))
        legend.setObjectName("subtle")
        matrix_toolbar.addWidget(legend)
        matrix_toolbar.addStretch(1)
        self.matrix_toggle_button = QPushButton(tr("raids.matrix_hide"))
        self.matrix_toggle_button.setCheckable(True)
        self.matrix_toggle_button.clicked.connect(self._toggle_attendance_matrix)
        matrix_toolbar.addWidget(self.matrix_toggle_button)
        attendance_layout.addLayout(matrix_toolbar)

        self._matrix_sort_key = "name"
        self._matrix_sort_ascending = True
        self._matrix_last_header_column: int | None = None
        self._matrix_raids = []
        self._matrix_players = []
        self._matrix_syncing_scroll = False
        self._attendance_refresh_pending = False
        self._attendance_sort_pending = False
        self._attendance_matrix_last_width = 860

        self.attendance_matrix_split = QSplitter(Qt.Orientation.Horizontal)

        self.raid_stats_table = QTableWidget(0, RAID_ATTENDANCE_FIXED_COLUMNS)
        self.raid_stats_table.setHorizontalHeaderLabels([
            tr("raids.player"), tr("raids.attendance_percent"), tr("raids.present"),
            tr("raids.bench"), tr("raids.relevant_raids"), tr("raids.main_count"),
            tr("raids.twink_count"), tr("raids.current_streak"),
            tr("raids.longest_streak"), tr("raids.last_attendance"),
        ])
        self.raid_stats_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.raid_stats_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.raid_stats_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.raid_stats_table.verticalHeader().setVisible(False)
        self.raid_stats_table.verticalHeader().setMinimumSectionSize(RAID_MATRIX_ROW_HEIGHT)
        self.raid_stats_table.verticalHeader().setDefaultSectionSize(RAID_MATRIX_ROW_HEIGHT)
        self.raid_stats_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.raid_stats_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.raid_stats_table.cellClicked.connect(self._attendance_table_cell_clicked)
        stats_header = self.raid_stats_table.horizontalHeader()
        stats_header.setSectionsClickable(True)
        stats_header.setSortIndicatorShown(True)
        stats_header.setFixedHeight(RAID_MATRIX_HEADER_HEIGHT)
        stats_header.sectionClicked.connect(self._attendance_table_header_clicked)
        stats_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        for column in range(1, RAID_ATTENDANCE_FIXED_COLUMNS):
            stats_header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.raid_stats_table.setColumnWidth(0, 185)

        self.raid_matrix_table = QTableWidget(0, 0)
        self.raid_matrix_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.raid_matrix_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.raid_matrix_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.raid_matrix_table.verticalHeader().setVisible(False)
        self.raid_matrix_table.verticalHeader().setMinimumSectionSize(RAID_MATRIX_ROW_HEIGHT)
        self.raid_matrix_table.verticalHeader().setDefaultSectionSize(RAID_MATRIX_ROW_HEIGHT)
        self.raid_matrix_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.raid_matrix_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.raid_matrix_table.setItemDelegate(RaidMatrixStatusDelegate(self.raid_matrix_table))
        self.raid_matrix_table.cellClicked.connect(self._matrix_cell_clicked)
        matrix_header = self.raid_matrix_table.horizontalHeader()
        matrix_header.setSectionsClickable(True)
        matrix_header.setFixedHeight(RAID_MATRIX_HEADER_HEIGHT)
        matrix_header.sectionClicked.connect(self._matrix_raid_clicked)
        matrix_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        self.raid_stats_table.verticalScrollBar().valueChanged.connect(
            lambda value: self._sync_matrix_vertical_scroll(self.raid_matrix_table, value)
        )
        self.raid_matrix_table.verticalScrollBar().valueChanged.connect(
            lambda value: self._sync_matrix_vertical_scroll(self.raid_stats_table, value)
        )

        self.attendance_matrix_split.addWidget(self.raid_stats_table)
        self.attendance_matrix_split.addWidget(self.raid_matrix_table)
        self.attendance_matrix_split.setCollapsible(0, False)
        self.attendance_matrix_split.setCollapsible(1, True)
        self.attendance_matrix_split.setStretchFactor(0, 0)
        self.attendance_matrix_split.setStretchFactor(1, 1)
        self.attendance_matrix_split.setSizes([1080, self._attendance_matrix_last_width])
        attendance_layout.addWidget(self.attendance_matrix_split, 1)
        self.raid_subtabs.addTab(attendance_page, tr("raids.page_attendance"))

        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        filters = QHBoxLayout()
        filters.addWidget(QLabel(tr("raid_points.filter_mode")))
        self.point_history_mode = QComboBox()
        self.point_history_mode.addItem(tr("raid_points.filter_player"), "player")
        self.point_history_mode.addItem(tr("raid_points.filter_character"), "character")
        filters.addWidget(self.point_history_mode)
        self.point_history_subject = QComboBox()
        self.point_history_subject.setMinimumWidth(300)
        filters.addWidget(self.point_history_subject)
        filters.addStretch(1)
        history_layout.addLayout(filters)
        self.point_history_table = QTableWidget(0, 8)
        self.point_history_table.setHorizontalHeaderLabels([
            tr("common.date"), tr("raids.raid"), tr("raids.character"),
            tr("common.status"), tr("raid_points.base"),
            tr("raid_points.adjustment"), tr("raid_points.reason"),
            tr("raid_points.total"),
        ])
        self.point_history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.point_history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.point_history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.point_history_table.verticalHeader().setVisible(False)
        history_header = self.point_history_table.horizontalHeader()
        for column in (0, 2, 3, 4, 5, 7):
            history_header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        history_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        history_header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.point_history_table.cellDoubleClicked.connect(
            lambda row, _column: self._open_history_raid(row)
        )
        history_layout.addWidget(self.point_history_table, 1)
        self.point_history_page = history_page
        self.point_history_tab_index = -1
        if self.model.raid_points.enabled:
            self.point_history_tab_index = self.raid_subtabs.addTab(
                history_page, tr("raid_points.history_tab"),
            )
        self.point_history_mode.currentIndexChanged.connect(
            lambda _index: self._populate_point_history_subjects()
        )
        self.point_history_subject.currentIndexChanged.connect(
            lambda _index: self.refresh_point_history()
        )
        self.raids_page = raids_page
        self.attendance_page = attendance_page
        self.raid_subtabs.currentChanged.connect(self._raid_subtab_changed)
        return page

    def _build_raid_filters(self, layout: QVBoxLayout, prefix: str, include_limit: bool = False) -> None:
        row = QHBoxLayout()

        row.addWidget(QLabel(tr("raids.view_mode")))
        view_switch = QFrame()
        view_switch.setProperty("innerCard", True)
        view_switch_layout = QHBoxLayout(view_switch)
        view_switch_layout.setContentsMargins(2, 2, 2, 2)
        view_switch_layout.setSpacing(0)
        player_button = QPushButton(tr("raid_points.filter_player"))
        character_button = QPushButton(tr("raid_points.filter_character"))
        self.matrix_view_group = QButtonGroup(self)
        self.matrix_view_group.setExclusive(True)
        for button, mode in ((player_button, "player"), (character_button, "character")):
            button.setObjectName("viewSwitchButton")
            button.setCheckable(True)
            button.setMinimumWidth(92)
            button.setProperty("viewMode", mode)
            self.matrix_view_group.addButton(button)
            view_switch_layout.addWidget(button)
        player_button.setChecked(True)
        row.addWidget(view_switch)

        self.matrix_subject_label = QLabel(tr("raids.player_filter"))
        row.addWidget(self.matrix_subject_label)
        subject = QComboBox()
        subject.setMinimumWidth(210)
        row.addWidget(subject)

        start = QLineEdit()
        start.setPlaceholderText(tr("raids.date_from"))
        start.setMaximumWidth(125)
        end = QLineEdit()
        end.setPlaceholderText(tr("raids.date_to"))
        end.setMaximumWidth(125)
        category = QComboBox()
        category.addItem(tr("common.all"), "")
        for value in RAID_CATEGORIES:
            category.addItem(value, value)
        raid_type = QComboBox()
        raid_type.addItem(tr("common.all"), "")
        for value in RAID_TYPES:
            raid_type.addItem(value, value)
        for widget in (start, end, category, raid_type):
            row.addWidget(widget)

        search = QLineEdit()
        search.setPlaceholderText(tr("raids.player_search"))
        row.addWidget(search)
        active = QCheckBox(tr("raids.active_only"))
        active.setChecked(True)
        active.setVisible(False)

        sort_combo = None
        limit = None
        if include_limit:
            limit = QComboBox()
            for text, value in ((tr("raids.last_10"), 10), (tr("raids.last_20"), 20),
                                (tr("raids.last_50"), 50), (tr("common.all"), 0)):
                limit.addItem(text, value)
            sort_combo = QComboBox()
            for key, text in (
                ("name", tr("raids.sort_name")),
                ("percent", tr("raids.sort_percent")),
                ("present", tr("raids.sort_present")),
                ("bench", tr("raids.sort_bench")),
                ("eligible", tr("raids.sort_eligible")),
                ("main", tr("raids.sort_main_count")),
                ("twink", tr("raids.sort_twink_count")),
                ("current_streak", tr("raids.sort_current_streak")),
                ("longest_streak", tr("raids.sort_longest_streak")),
                ("last_attendance", tr("raids.sort_last_attendance")),
            ):
                sort_combo.addItem(text, key)
            row.addWidget(limit)
            row.addWidget(sort_combo)

        row.addStretch(1)
        layout.addLayout(row)
        setattr(self, f"{prefix}_date_from", start)
        setattr(self, f"{prefix}_date_to", end)
        setattr(self, f"{prefix}_category_filter", category)
        setattr(self, f"{prefix}_type_filter", raid_type)
        setattr(self, f"{prefix}_player_search", search)
        setattr(self, f"{prefix}_active_only", active)
        setattr(self, f"{prefix}_subject", subject)
        setattr(self, f"{prefix}_view_player_button", player_button)
        setattr(self, f"{prefix}_view_character_button", character_button)
        if limit is not None:
            setattr(self, f"{prefix}_raid_limit", limit)
        if sort_combo is not None:
            setattr(self, f"{prefix}_sort", sort_combo)

        callback = self._refresh_attendance_combined
        start.textChanged.connect(lambda _text: callback())
        end.textChanged.connect(lambda _text: callback())
        category.currentIndexChanged.connect(lambda _index: callback())
        raid_type.currentIndexChanged.connect(lambda _index: callback())
        search.textChanged.connect(lambda _text: callback())
        active.toggled.connect(lambda _checked: callback())
        subject.currentIndexChanged.connect(lambda _index: callback())
        self.matrix_view_group.buttonClicked.connect(
            lambda _button: self._matrix_view_mode_changed()
        )
        if limit is not None:
            limit.currentIndexChanged.connect(lambda _index: callback())
        if sort_combo is not None:
            sort_combo.currentIndexChanged.connect(self._matrix_sort_dropdown_changed)
        self._populate_matrix_subjects()

    # ---------- Settings ----------
    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 14)
        title = QLabel(tr("tabs.settings"))
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(10)

        feature_card = QFrame()
        feature_card.setProperty("card", True)
        feature_card.setMaximumWidth(860)
        feature_layout = QVBoxLayout(feature_card)
        feature_layout.addWidget(QLabel(tr("raid_clm_admin.optional_systems")))
        self.points_enabled_check = QCheckBox(tr("raid_clm_admin.points_system"))
        self.dkp_enabled_check = QCheckBox(tr("raid_clm_admin.dkp_mode"))
        self.points_enabled_check.toggled.connect(self._points_system_toggled)
        self.dkp_enabled_check.toggled.connect(self._dkp_mode_toggled)
        feature_layout.addWidget(self.points_enabled_check)
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel(tr("raid_points.calculation_label")))
        self.raid_scope_all = QRadioButton(tr("raid_points.calculation_all"))
        self.raid_scope_from = QRadioButton(tr("raid_points.calculation_from"))
        self.raid_scope_start = QLineEdit()
        self.raid_scope_start.setPlaceholderText("YYYY-MM-DD")
        self.raid_scope_start.setMaximumWidth(130)
        scope_group = QButtonGroup(self)
        scope_group.addButton(self.raid_scope_all)
        scope_group.addButton(self.raid_scope_from)
        self.raid_scope_all.toggled.connect(self._raid_point_scope_changed)
        self.raid_scope_from.toggled.connect(self._raid_point_scope_changed)
        self.raid_scope_start.editingFinished.connect(self._raid_point_scope_changed)
        scope_row.addWidget(self.raid_scope_all)
        scope_row.addWidget(self.raid_scope_from)
        scope_row.addWidget(self.raid_scope_start)
        scope_row.addStretch(1)
        feature_layout.addLayout(scope_row)
        feature_layout.addWidget(self.dkp_enabled_check)
        content_layout.addWidget(feature_card)

        self.clm_group = QFrame()
        self.clm_group.setProperty("card", True)
        self.clm_group.setMaximumWidth(860)
        clm_layout = QVBoxLayout(self.clm_group)
        clm_title = QLabel(tr("raid_clm_admin.clm_title"))
        clm_title.setStyleSheet("font-size:12pt;font-weight:700;background:transparent;border:none;")
        clm_layout.addWidget(clm_title)
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel(tr("raid_clm_admin.clm_file")))
        self.clm_path_edit = QLineEdit(str(self._suite_settings.get("clm_saved_variables_path") or ""))
        self.clm_path_edit.setReadOnly(True)
        path_row.addWidget(self.clm_path_edit, 1)
        browse = QPushButton(tr("raid_clm_admin.browse"))
        browse.clicked.connect(self.choose_clm_path)
        path_row.addWidget(browse)
        clm_layout.addLayout(path_row)
        roster_row = QHBoxLayout()
        roster_row.addWidget(QLabel(tr("raid_clm_admin.roster")))
        self.clm_roster_combo = QComboBox()
        self.clm_roster_combo.setMinimumWidth(300)
        roster_row.addWidget(self.clm_roster_combo)
        roster_row.addStretch(1)
        clm_layout.addLayout(roster_row)
        refresh = set_button_role(QPushButton(tr("raid_clm_admin.refresh_dkp")), primary=True)
        refresh.clicked.connect(self.refresh_dkp)
        clm_layout.addWidget(refresh, 0, Qt.AlignmentFlag.AlignLeft)
        history_sync = set_button_role(
            QPushButton(tr("raid_clm_admin.sync_history")), primary=True,
        )
        history_sync.clicked.connect(self.sync_clm_raid_history)
        clm_layout.addWidget(history_sync, 0, Qt.AlignmentFlag.AlignLeft)
        self.clm_status_label = QLabel(tr("raid_clm_admin.clm_not_refreshed"))
        self.clm_status_label.setObjectName("subtle")
        self.clm_status_label.setWordWrap(True)
        clm_layout.addWidget(self.clm_status_label)
        content_layout.addWidget(self.clm_group)

        self.points_group = QFrame()
        self.points_group.setProperty("card", True)
        self.points_group.setMaximumWidth(860)
        points_layout = QVBoxLayout(self.points_group)
        points_title = QLabel(tr("raid_clm_admin.points_rebuild_title"))
        points_title.setStyleSheet("font-size:12pt;font-weight:700;background:transparent;border:none;")
        points_layout.addWidget(points_title)
        self.points_rebuild_button = set_button_role(
            QPushButton(tr("raid_clm_admin.rebuild_raid_statistics")), primary=True,
        )
        self.points_rebuild_button.clicked.connect(self.rebuild_raid_statistics)
        points_layout.addWidget(self.points_rebuild_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.raid_points_only_rebuild_button = QPushButton(tr("raid_points.rebuild_only"))
        self.raid_points_only_rebuild_button.clicked.connect(self.rebuild_raid_points)
        points_layout.addWidget(self.raid_points_only_rebuild_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.points_status_label = QLabel(tr("raid_clm_admin.raid_statistics_not_rebuilt"))
        self.points_status_label.setObjectName("subtle")
        points_layout.addWidget(self.points_status_label)
        content_layout.addWidget(self.points_group)

        card = QFrame()
        card.setProperty("card", True)
        card.setMaximumWidth(760)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(12)

        gear_title = QLabel(tr("checker.gear_check_settings"))
        gear_title.setStyleSheet("font-size:12pt;font-weight:700;background:transparent;border:none;")
        card_layout.addWidget(gear_title)
        help_label = QLabel(tr("checker.gear_check_settings_help"))
        help_label.setObjectName("subtle")
        help_label.setWordWrap(True)
        card_layout.addWidget(help_label)
        self.outdated_check = QCheckBox(tr("checker.track_outdated_checks"))
        self.outdated_check.setChecked(self.gear_outdated_tracking)
        card_layout.addWidget(self.outdated_check)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("checker.warn_after_days")))
        self.outdated_days_spin = QSpinBox()
        self.outdated_days_spin.setRange(1, 3650)
        self.outdated_days_spin.setValue(self.gear_outdated_days)
        row.addWidget(self.outdated_days_spin)
        row.addWidget(QLabel(tr("checker.days")))
        row.addStretch(1)
        card_layout.addLayout(row)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(tr("language.label")))
        self.language_combo = QComboBox()
        self.language_combo.addItems(language_display_values())
        self.language_combo.setCurrentIndex(0 if get_language() == "de" else 1)
        lang_row.addWidget(self.language_combo)
        lang_row.addStretch(1)
        card_layout.addLayout(lang_row)

        save = set_button_role(QPushButton(tr("common.save")), primary=True)
        save.clicked.connect(self.save_settings)
        card_layout.addWidget(save, 0, Qt.AlignmentFlag.AlignLeft)
        content_layout.addWidget(card, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        migration = QFrame()
        migration.setProperty("card", True)
        migration.setMaximumWidth(760)
        mig_layout = QVBoxLayout(migration)
        mig_title = QLabel(tr("checker.qt_migration"))
        mig_title.setStyleSheet("font-size:12pt;font-weight:700;background:transparent;border:none;")
        mig_layout.addWidget(mig_title)
        info = QLabel(tr("checker.qt_migration_help"))
        info.setObjectName("subtle")
        info.setWordWrap(True)
        mig_layout.addWidget(info)
        legacy = QPushButton(tr("checker.launch_legacy"))
        legacy.clicked.connect(self.launch_legacy_checker)
        mig_layout.addWidget(legacy, 0, Qt.AlignmentFlag.AlignLeft)
        content_layout.addWidget(migration, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return page

    # ---------- Navigation / refresh ----------
    def switch_page(self, page: str, *, refresh: bool = True) -> None:
        widget = self._pages.get(page)
        if widget is None:
            return
        self.stack.setCurrentWidget(widget)
        for key, button in self._nav_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == page)
            button.blockSignals(False)
        if not refresh:
            return
        if page == "management":
            self.refresh_member_table(select_first=False)
        elif page == "rooster":
            self.refresh_roster()
        elif page == "graveyard":
            self.refresh_graveyard()
        elif page == "raid":
            self._refresh_current_raid_tab()

    def open_player_profile_for_member(self, member_id: str) -> bool:
        member = self.model.find_by_id(str(member_id or ""))
        if member is None or not member.playerId:
            return False
        return self.open_player_profile(member.playerId)

    def open_player_profile(self, player_id: str) -> bool:
        """Open one active player by ID without name fallback or data refresh."""
        player_id = str(player_id or "").strip()
        if not player_id or not self.model.player_is_active(player_id):
            return False
        profile = self._build_player_profile(player_id)
        if profile is None:
            return False
        if self.stack.currentWidget() is not self.player_profile_page:
            self._player_profile_return_page = next((
                key for key, page in self._pages.items()
                if page is self.stack.currentWidget() and key != "player_profile"
            ), "rooster")
        self._player_profile = profile
        self._render_player_profile(profile)
        self.switch_page("player_profile")
        return True

    def close_player_profile(self) -> None:
        target = self._player_profile_return_page
        self.switch_page(target if target in self._pages else "rooster")

    def _build_player_profile(
            self, player_id: str, selected_member_id: str | None = None,
    ) -> PlayerProfileViewModel | None:
        current_dkp = (
            self._clm_dkp_by_member_id
            if self._clm_refresh_service.cached_snapshot is not None else None
        )
        return build_player_profile(
            self.model,
            player_id,
            selected_member_id=selected_member_id,
            raid_point_entries=self._raid_point_projection,
            current_dkp_by_member_id=current_dkp,
            reward_assignments=self._reward_assignments,
        )

    def _select_profile_character(self, member_id: str) -> None:
        current = self._player_profile
        if current is None:
            return
        profile = current.with_selected_character(member_id)
        if profile is None:
            return
        self._player_profile = profile
        self._render_profile_character(profile)

    def _select_previous_profile_character(self) -> None:
        self._select_adjacent_profile_character(-1)

    def _select_next_profile_character(self) -> None:
        self._select_adjacent_profile_character(1)

    def _select_adjacent_profile_character(self, offset: int) -> None:
        profile = self._player_profile
        if profile is None:
            return
        current_index = next((
            index for index, character in enumerate(profile.characters)
            if character.member_id == profile.selected_member_id
        ), -1)
        target_index = current_index + offset
        if current_index < 0 or not 0 <= target_index < len(profile.characters):
            return
        self._select_profile_character(profile.characters[target_index].member_id)

    @staticmethod
    def _profile_number(value: int | float | None) -> str:
        return "–" if value is None else GuildGearCheckerQt._format_dkp_value(value)

    @staticmethod
    def _frame_stage_text(asset_id: str | None) -> str:
        stages = {
            "frame_01": "wood", "frame_02": "iron", "frame_03": "bronze",
            "frame_04": "silver", "frame_05": "gold", "frame_06": "platinum",
            "frame_07": "diamond",
        }
        return tr(f"materials.{stages[asset_id]}") if asset_id in stages else "–"

    @staticmethod
    def _profile_attendance_text(stat: object) -> str:
        total = int(getattr(stat, "total_attendances", 0))
        bench = int(getattr(stat, "bench_attendances", 0))
        return tr(
            "player_profile.attendance_value",
            percent=int(getattr(stat, "attendance_percent", 0)),
            present=max(0, total - bench),
            eligible=int(getattr(stat, "eligible_raids", 0)),
            bench=bench,
        )

    @staticmethod
    def _profile_raid_count(stat: object) -> str:
        return str(int(getattr(stat, "total_attendances", 0)))

    @staticmethod
    def _profile_streak_text(stat: object) -> str:
        return tr(
            "player_profile.streak_value",
            current=int(getattr(stat, "current_streak", 0)),
            longest=int(getattr(stat, "longest_streak", 0)),
        )

    def _set_profile_metrics(
            self, labels: dict[str, QLabel], *, attendance: object,
            raid_count: int,
            raid_points: int | None, eternal_dkp: int | float,
            current_dkp: int | float | None, point_mode: str,
    ) -> None:
        labels["attendance"].setText(self._profile_attendance_text(attendance))
        labels["raids"].setText(str(int(raid_count)))
        if "points" in labels:
            labels["points"].setText(
                self._profile_number(raid_points if point_mode == POINT_MODE_RAID else current_dkp)
            )
        if "eternal_dkp" in labels:
            labels["eternal_dkp"].setText(self._profile_number(eternal_dkp))
        if "streak" in labels:
            labels["streak"].setText(self._profile_streak_text(attendance))

    def _refresh_profile_raid_list(self, character: object) -> None:
        """Show existing attendance and point projections for one member only."""
        page = self.player_profile_page
        member_id = str(getattr(character, "member_id", ""))
        attended_raid_ids = set(getattr(character, "attended_raid_ids", ()))
        point_mode = self.model.active_point_mode()
        point_title = (
            tr("raid_points.title") if point_mode == POINT_MODE_RAID
            else tr("player_profile.dkp")
        )
        page.character_raid_table.setHorizontalHeaderLabels((
            tr("common.date"), tr("common.name"), tr("common.status"), point_title,
        ))
        page.character_raid_table.setColumnHidden(3, point_mode not in {
            POINT_MODE_RAID, POINT_MODE_ETERNAL,
        })
        points_by_attendance = {
            entry.attendance_id: entry
            for entry in self._point_entries()
            if entry.member_id == member_id
        }
        eternal_by_raid: dict[str, float] = {}
        if point_mode == POINT_MODE_ETERNAL:
            for record in self.model.eternal_dkp.records:
                if record.member_id == member_id and record.raid_id:
                    eternal_by_raid[record.raid_id] = (
                        eternal_by_raid.get(record.raid_id, 0.0) + float(record.value)
                    )
        attended_by_raid: dict[str, object] = {}
        for attendance in self.model.raid_attendance:
            if (attendance.memberId != member_id
                    or attendance.raidId not in attended_raid_ids):
                continue
            raid = self.model.find_raid_by_id(attendance.raidId)
            if raid is None or attendance.status not in {"present", "bench"}:
                continue
            # Matches calculate_statistics(): one stable raid ID contributes once.
            attended_by_raid[raid.id] = attendance
        rows = []
        for raid_id, attendance in attended_by_raid.items():
            raid = self.model.find_raid_by_id(raid_id)
            if raid is None:
                continue
            if point_mode == POINT_MODE_RAID:
                point = points_by_attendance.get(attendance.id)
                value = str(point.total_points) if point is not None else "–"
            elif point_mode == POINT_MODE_ETERNAL:
                value = self._format_dkp_value(eternal_by_raid.get(raid.id, 0.0))
            else:
                value = "–"
            rows.append((
                raid.date, raid.name,
                tr(f"raids.attendance_status_{attendance.status}"), value, raid.id,
            ))
        rows.sort(key=lambda row: (row[0], row[4]), reverse=True)
        page.character_raid_table.setUpdatesEnabled(False)
        try:
            page.character_raid_table.setRowCount(len(rows))
            for row_index, (date, name, status, value, raid_id) in enumerate(rows):
                for column, text in enumerate((date, name, status, value)):
                    item = QTableWidgetItem(str(text))
                    item.setData(Qt.ItemDataRole.UserRole, raid_id)
                    page.character_raid_table.setItem(row_index, column, item)
        finally:
            page.character_raid_table.setUpdatesEnabled(True)

    def _render_player_profile(self, profile: PlayerProfileViewModel) -> None:
        page = self.player_profile_page
        point_mode = self.model.active_point_mode()
        page.set_point_system(point_mode)
        heading_name = profile.profile_name or tr("player_profile.no_active_main")
        page.title.setText(tr("player_profile.title", name=heading_name))
        options: list[tuple[str, str]] = []
        for label, player_id in active_player_options(self.model):
            if self.model.active_main_for_player(player_id) is None:
                label = tr("player_profile.no_main_option", player=label)
            options.append((label, player_id))
        page.set_player_options(options, profile.player_id)

        page.player_metric_labels["player_rank"].setText(
            self._frame_stage_text(profile.frame_asset_id)
        )
        self._set_profile_metrics(
            page.player_metric_labels,
            attendance=profile.attendance,
            raid_count=profile.raid_count,
            raid_points=profile.raid_points,
            eternal_dkp=profile.eternal_dkp,
            current_dkp=profile.current_dkp,
            point_mode=point_mode,
        )
        self._render_profile_character(profile, refresh_options=True)

    def _render_profile_character(
            self, profile: PlayerProfileViewModel, *, refresh_options: bool = False,
    ) -> None:
        page = self.player_profile_page
        if refresh_options:
            page.set_character_options((
                (
                    tr(
                        "player_profile.character_option",
                        name=character.name,
                        character_type=character_type_display(character.character_type),
                        status=tr(f"life.{character.life_status}"),
                    ),
                    character.member_id,
                )
                for character in profile.characters
            ), profile.selected_member_id)
        character_index = next((
            index for index, item in enumerate(profile.characters)
            if item.member_id == profile.selected_member_id
        ), -1)
        page.set_character_selection(profile.selected_member_id)
        page.set_character_navigation(
            has_previous=character_index > 0,
            has_next=0 <= character_index < len(profile.characters) - 1,
        )
        character = profile.selected_character
        if character is None:
            self._clear_profile_character()
            return
        member = self.model.find_by_id(character.member_id)
        if member is None:
            self._clear_profile_character()
            return
        page.character_name.setText(character.name)
        race_text = race_display(character.race) if character.race else tr("common.not_set")
        class_text = profile_class_display(character.class_name) or tr("common.not_set")
        page.character_identity_line.setText(f"{race_text} – {class_text}")
        page.character_spec.setText(character.spec or tr("common.not_set"))
        page.character_type.setText(character_type_display(character.character_type))
        page.character_life.setText(tr(f"life.{character.life_status}"))
        page.character_rank.setText(self._rank_text_for_member(member))
        self._set_external_rank_icon(
            page.player_rank_icon, self._rank_path_for_member(member, 96), 96,
        )
        if character.life_status == "dead":
            try:
                template = self.model.gravestone_inventory().by_id().get(
                    character.grave_template_id
                )
            except Exception:
                template = None
            page.player_portrait.set_pixmap_source(
                self._grave_pixmap_for_member(member, template, (180, 240))
            )
            page.player_reward_portrait.clear_reward_badge()
            page.player_reward_portrait.clear_reward_frame()
        else:
            page.player_portrait.set_source(character.portrait_path)
            frame = self._reward_assignments.frame_for_main(
                profile.current_main_member_id or ""
            )
            page.player_reward_portrait.clear_reward_badge()
            page.player_reward_portrait.set_reward_frame(
                frame.path if frame is not None else None,
                self._reward_registry.frame_opening(frame.asset_id) if frame is not None else None,
            )
        self._set_profile_metrics(
            page.character_metric_labels,
            attendance=character.attendance,
            raid_count=character.raid_count,
            raid_points=character.raid_points,
            eternal_dkp=character.eternal_dkp,
            current_dkp=character.current_dkp,
            point_mode=self.model.active_point_mode(),
        )
        self._refresh_profile_raid_list(character)

    def _clear_profile_character(self) -> None:
        page = self.player_profile_page
        page.player_portrait.clear_source()
        page.character_name.setText(tr("player_profile.no_character"))
        for label in (
            page.character_spec,
            page.character_type, page.character_life, page.character_rank,
        ):
            label.setText("–")
        page.character_identity_line.setText("–")
        page.player_rank_icon.clear()
        page.player_rank_icon.hide()
        page.player_reward_portrait.clear_reward_badge()
        page.player_reward_portrait.clear_reward_frame()
        for label in page.character_metric_labels.values():
            label.setText("–")
        page.character_raid_table.setRowCount(0)

    def set_member_tab(self, tab_name: str, refresh: bool = True) -> None:
        self.member_tab = tab_name
        for key, button in self._member_subnav_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == tab_name)
            button.blockSignals(False)
        if refresh:
            self.refresh_member_table(select_first=True)

    def _filtered_members(self) -> list[Member]:
        gear_text = self.gear_filter_combo.currentText() if hasattr(self, "gear_filter_combo") else tr("common.all")
        ench_text = self.enchant_filter_combo.currentText() if hasattr(self, "enchant_filter_combo") else tr("common.all")
        gear_filter = None if gear_text == tr("common.all") else gear_status_key(gear_status_from_display(gear_text))
        enchant_filter = None if ench_text == tr("common.all") else enchant_status_key(enchant_status_from_display(ench_text))
        sort_column, descending = self.sort_state.get(self.member_tab, default_sort_for_tab(self.member_tab))
        return filter_and_sort_members(
            self.model.members,
            self.member_tab,
            self.search_edit.text() if hasattr(self, "search_edit") else "",
            gear_filter,
            enchant_filter,
            sort_column,
            descending,
            outdated_tracking=self.gear_outdated_tracking,
            outdated_days=self.gear_outdated_days,
        )

    def refresh_all(self, select_first: bool = False) -> None:
        self.refresh_project_label()
        self._sync_admin_controls()
        self.refresh_member_table(select_first=select_first)
        if self.stack.currentWidget() is self._pages.get("rooster"):
            self.refresh_roster()
        if self.stack.currentWidget() is self._pages.get("graveyard"):
            self.refresh_graveyard()
        if self.stack.currentWidget() is self._pages.get("raid"):
            self._refresh_current_raid_tab()

    def refresh_member_table(self, select_first: bool = False) -> None:
        if not hasattr(self, "member_table"):
            return
        visible = self._filtered_members()
        old_id = self.selected_member_id
        self._member_table_refreshing = True
        self.member_table.blockSignals(True)
        self.member_table.setSortingEnabled(False)
        self.member_table.setRowCount(len(visible))
        try:
            for row, member in enumerate(visible):
                values = (
                    member.name,
                    race_display(member.race) if member.race else tr("common.not_set"),
                    member.className or tr("common.not_set"),
                    member.spec or tr("common.not_set"),
                    character_type_display(member.characterType),
                    raid_role_display(member.raidRole),
                    gear_status_display(member.gearStatus),
                    raid_status_display(member.raidStatus),
                    member.lastChecked or "–",
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setData(Qt.ItemDataRole.UserRole, member.id)
                    if column == 2 and member.className in CLASS_COLORS:
                        item.setForeground(QColor(CLASS_COLORS[member.className]))
                        icon_path = class_icon_path(member.className)
                        if icon_path.is_file():
                            item.setIcon(QIcon(str(icon_path)))
                    if column == 8:
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.member_table.setItem(row, column, item)
        finally:
            self.member_table.setSortingEnabled(True)
            self.member_table.blockSignals(False)
            self._member_table_refreshing = False
        self.member_count.setText(f"{len(visible)} / {len(self.model.members)}")
        self.count_label.setText(
            "   ·   ".join((
                tr("checker.active_count", count=sum(m.lifeStatus == "active" for m in self.model.members)),
                tr("checker.inactive_count", count=sum(m.lifeStatus == "inactive" for m in self.model.members)),
                tr("checker.dead_count", count=sum(m.lifeStatus == "dead" for m in self.model.members)),
            ))
        )
        target = old_id if old_id in {member.id for member in visible} else (visible[0].id if visible and select_first else None)
        if target:
            self._select_member_in_table(target)
            self.show_member(target)
        elif not visible:
            self.clear_detail()

    def _member_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._member_table_refreshing:
            return
        member_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        member = self.model.find_by_id(member_id)
        if member is None:
            return
        try:
            changed = self._apply_member_inline_edit(member, item.column(), item.text())
        except ValueError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            changed = False
        if changed:
            self.autosave()
            if item.column() == 4:
                self._rebuild_raid_derived_state()
            self.set_status(tr("checker.saved", name=member.name))
        self.refresh_member_table(select_first=False)
        current_item = self.member_table.currentItem()
        current_id = str(current_item.data(Qt.ItemDataRole.UserRole) or "") if current_item else ""
        if current_id != member.id:
            self._select_member_in_table(member.id)
            self.show_member(member.id)

    def _paste_member_table(self, text: str) -> None:
        """Apply a rectangular clipboard block atomically to ordinary member fields.

        Player identity/type assignments deliberately remain excluded: those use the
        existing protected assignment dialog rather than accepting raw IDs.
        """
        current = self.member_table.currentIndex()
        if not current.isValid() or not text.strip():
            return
        rows = [line.split("\t") for line in text.replace("\r\n", "\n").split("\n") if line]
        if not rows:
            return
        start_row, start_column = current.row(), current.column()
        protected = {4, 8}
        edits: list[tuple[Member, int, str]] = []
        for row_offset, values in enumerate(rows):
            table_row = start_row + row_offset
            if table_row >= self.member_table.rowCount():
                QMessageBox.warning(self, APP_NAME, tr("checker.paste_out_of_range"))
                return
            member_item = self.member_table.item(table_row, 0)
            member = self.model.find_by_id(str(member_item.data(Qt.ItemDataRole.UserRole) or "")) if member_item else None
            if member is None:
                QMessageBox.warning(self, APP_NAME, tr("checker.paste_out_of_range"))
                return
            for column_offset, value in enumerate(values):
                column = start_column + column_offset
                if column >= len(MemberTable.COLUMNS) or column in protected:
                    QMessageBox.warning(self, APP_NAME, tr("checker.paste_protected"))
                    return
                edits.append((member, column, value))
        snapshots = {member.id: member.__dict__.copy() for member, _column, _value in edits}
        try:
            for member, column, value in edits:
                self._apply_member_inline_edit(member, column, value)
        except (ValueError, MainConflictError) as exc:
            for member_id, state in snapshots.items():
                member = self.model.find_by_id(member_id)
                if member is not None:
                    member.__dict__.update(state)
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.autosave()
        self.refresh_member_table(select_first=False)

    def _choose_associated_main(self, member: Member) -> tuple[str | None, bool]:
        mains = sorted((
            value for value in self.model.members
            if value.lifeStatus == "active" and value.characterType == "main" and value.id != member.id
        ), key=lambda value: (value.name.casefold(), value.id))
        if not mains:
            QMessageBox.warning(self, APP_NAME, tr("model.active_main_required"))
            return None, False
        current = self.model.associated_main(member)
        labels = [value.name for value in mains]
        current_index = labels.index(current.name) if current and current.name in labels else 0
        label, ok = QInputDialog.getItem(
            self,
            tr("checker.select_main_title"),
            tr("checker.associated_main"),
            labels,
            current_index,
            False,
        )
        if not ok:
            return None, False
        for value in mains:
            if value.name == label:
                return value.id, True
        return None, False

    def _apply_member_inline_edit(self, member: Member, column: int, value: str) -> bool:
        if column == 0:
            name = unicodedata.normalize("NFC", str(value or "").strip())
            if not name:
                raise ValueError(tr("model.enter_character"))
            existing = self.model.find_current_by_name(name)
            if existing is not None and existing.id != member.id:
                raise ValueError(tr("model.current_name_exists", name=existing.name))
            if member.name == name:
                return False
            member.name = name
        elif column == 1:
            new_value = race_from_display(value)
            if member.race == new_value:
                return False
            member.race = new_value
        elif column == 2:
            class_name = normalize_class_name(value)
            if member.className == class_name:
                return False
            member.className = class_name
            member.spec = normalize_spec(class_name, member.spec)
            member.classSpec = f"{class_name} / {member.spec}" if class_name and member.spec else class_name
        elif column == 3:
            spec = normalize_spec(member.className, value)
            if member.spec == spec:
                return False
            member.spec = spec
            member.classSpec = f"{member.className} / {spec}" if member.className and spec else member.className
        elif column == 4:
            character_type = character_type_from_display(value)
            if character_type == member.characterType:
                return False
            associated_main_id = None
            if character_type == "twink":
                associated_main_id, ok = self._choose_associated_main(member)
                if not ok:
                    return False
            try:
                self.model.assign_character_type(
                    member.id, character_type, associated_main_id, member.raidRole,
                )
            except MainConflictError as conflict:
                answer = QMessageBox.question(
                    self, tr("checker.main_conflict_title"),
                    tr("checker.main_conflict", name=conflict.existing_main.name, new_name=member.name),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return False
                self.model.assign_character_type(
                    member.id, character_type, associated_main_id, member.raidRole,
                    replace_existing_main=True,
                )
        elif column == 5:
            raid_role = raid_role_from_display(value)
            if member.raidRole == raid_role:
                return False
            member.raidRole = raid_role
        elif column == 6:
            gear = gear_status_from_display(value)
            if member.gearStatus == gear:
                return False
            member.gearStatus = gear
            member.lastChecked = today_iso()
        elif column == 7:
            raid_status = raid_status_from_display(value)
            if member.raidStatus == raid_status:
                return False
            member.raidStatus = raid_status
        else:
            return False
        self.model.dirty = True
        return True


    def _select_member_in_table(self, member_id: str) -> None:
        for row in range(self.member_table.rowCount()):
            item = self.member_table.item(row, 0)
            if item and str(item.data(Qt.ItemDataRole.UserRole)) == member_id:
                signals_were_blocked = self.member_table.blockSignals(True)
                try:
                    self.member_table.selectRow(row)
                    self.member_table.scrollToItem(item)
                finally:
                    self.member_table.blockSignals(signals_were_blocked)
                return

    def _member_current_item_changed(
        self,
        current: QTableWidgetItem | None,
        _previous: QTableWidgetItem | None,
    ) -> None:
        self._show_member_for_table_item(current)

    def _show_member_for_table_item(self, item: QTableWidgetItem | None) -> None:
        member_id = str(item.data(Qt.ItemDataRole.UserRole) or "") if item is not None else ""
        if member_id and self.model.find_by_id(member_id) is not None:
            self.show_member(member_id)

    def _point_totals_for_member(self, member: Member) -> tuple[int | float, int | float | None]:
        if self.model.active_point_mode() == POINT_MODE_ETERNAL:
            character_total = self.model.eternal_character_totals().get(member.id, (0, 0))[0]
            player_total = (
                self.model.eternal_player_totals().get(member.playerId, (0, 0))[0]
                if member.playerId else None
            )
            return character_total, player_total
        entries = self._point_entries()
        character_total = sum(
            entry.total_points for entry in entries if entry.member_id == member.id
        )
        active_main = (
            self.model.active_main_for_player(member.playerId)
            if member.playerId else None
        )
        player_total = None
        if active_main is not None and active_main.id == member.id:
            player_total = sum(
                entry.total_points for entry in entries if entry.player_id == member.playerId
            )
        return character_total, player_total

    def _set_member_point_labels(
        self, member: Member, character_label: QLabel, player_label: QLabel,
        player_button: QPushButton,
    ) -> None:
        character_total, player_total = self._point_totals_for_member(member)
        eternal = self.model.active_point_mode() == POINT_MODE_ETERNAL
        character_label.setText(
            self._format_dkp_value(character_total) if eternal else str(character_total)
        )
        player_label.setText(
            self._format_dkp_value(player_total) if eternal and player_total is not None
            else str(player_total) if player_total is not None else "–"
        )
        if player_label is self.detail_player_points:
            self.detail_points_form.setRowVisible(player_label, player_total is not None)
        elif player_label is self.roster_player_points:
            self.roster_points_form.setRowVisible(player_label, player_total is not None)
        player_button.setVisible(not eternal and player_total is not None)

    def _refresh_visible_point_details(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if member is not None and hasattr(self, "detail_character_points"):
            self._set_member_point_labels(
                member, self.detail_character_points, self.detail_player_points,
                self.detail_player_history,
            )
        roster_member = self.model.find_by_id(
            getattr(self, "roster_selected_member_id", "")
        )
        if roster_member is not None and hasattr(self, "roster_character_points"):
            self._set_member_point_labels(
                roster_member, self.roster_character_points, self.roster_player_points,
                self.roster_player_history,
            )

    def _rebuild_reward_assignments(self) -> None:
        """Refresh the reward snapshot only after an existing point-domain event."""
        mode = self.model.active_point_mode()
        if mode == POINT_MODE_ETERNAL:
            character_points = {
                member_id: int(total) for member_id, (total, _bench)
                in self.model.eternal_character_totals().items()
            }
            player_points = {
                player_id: int(total) for player_id, (total, _bench)
                in self.model.eternal_player_totals().items()
            }
        else:
            entries = self._point_entries()
            character_points: dict[str, int] = {}
            player_points: dict[str, int] = {}
            for entry in entries:
                character_points[entry.member_id] = character_points.get(entry.member_id, 0) + entry.total_points
                player_points[entry.player_id] = player_points.get(entry.player_id, 0) + entry.total_points
        active_main_ids = {
            player_id: main.id
            for player_id in {member.playerId for member in self.model.members if member.playerId}
            if (main := self.model.active_main_for_player(player_id)) is not None
        }
        self._reward_assignments = build_reward_assignments(
            enabled=bool(mode),
            character_points=character_points,
            player_points=player_points,
            active_main_ids=active_main_ids,
            registry=self._reward_registry,
            thresholds=(
                eternal_dkp_reward_thresholds()
                if mode == POINT_MODE_ETERNAL else active_reward_thresholds()
            ),
        )

    def _rank_path_for_member(self, member: Member, size: int) -> Path | None:
        badge = self._reward_assignments.badge_for_member(member.id)
        if badge is None:
            return None
        return self._reward_registry.rank_path(badge.asset_id, size)

    def _rank_text_for_member(self, member: Member) -> str:
        badge = self._reward_assignments.badge_for_member(member.id)
        if badge is None:
            return "–"
        material, separator, stage = badge.asset_id.rpartition("_")
        if not separator or not material or not stage:
            return badge.asset_id.replace("_", " ")
        return f"{material} {stage}"

    @staticmethod
    def _set_external_rank_icon(
        label: QLabel,
        path: Path | None,
        display_size: int = 96,
    ) -> None:
        label.clear()
        if path is None or not path.is_file():
            label.hide()
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            label.hide()
            return
        label.setPixmap(pixmap.scaled(
            display_size,
            display_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        label.show()

    def _set_member_reward_visuals(
        self,
        member: Member,
        portrait: RewardPortraitContainer,
        *,
        external_rank_label: QLabel | None = None,
    ) -> None:
        frame = self._reward_assignments.frame_for_main(member.id)
        if external_rank_label is None:
            portrait.set_reward_badge(
                self._rank_path_for_member(member, portrait.rank_asset_size)
            )
        else:
            # Detailansichten zeigen den Rang bewusst separat neben dem Portrait.
            portrait.clear_reward_badge()
            self._set_external_rank_icon(
                external_rank_label,
                self._rank_path_for_member(member, 96),
                96,
            )
        portrait.set_reward_frame(
            frame.path if frame is not None else None,
            self._reward_registry.frame_opening(frame.asset_id) if frame is not None else None,
        )

    def _refresh_visible_reward_details(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if member is not None:
            self._set_member_reward_visuals(
                member,
                self.detail_reward_portrait,
                external_rank_label=self.detail_rank_icon,
            )
        roster_member = self.model.find_by_id(
            getattr(self, "roster_selected_member_id", "")
        )
        if roster_member is not None:
            self._set_member_reward_visuals(
                roster_member,
                self.roster_reward_portrait,
                external_rank_label=self.roster_rank_icon,
            )

    @staticmethod
    def _format_dkp_value(value: int | float | None) -> str:
        if value is None:
            return "—"
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    def _dkp_text_for_member(self, member: Member) -> str:
        return self._format_dkp_value(self._clm_dkp_by_member_id.get(member.id))

    def _refresh_visible_dkp_details(self) -> None:
        if hasattr(self, "detail_dkp_section"):
            self.detail_dkp_section.setVisible(False)
            member = self.model.find_by_id(self.selected_member_id or "")
            self.detail_dkp_value.setText(
                self._dkp_text_for_member(member) if member is not None else "—"
            )
            if hasattr(self, "detail_current_dkp"):
                self.detail_current_dkp.setText(
                    self._dkp_text_for_member(member) if member is not None else "—"
                )
        if hasattr(self, "roster_dkp_section"):
            self.roster_dkp_section.setVisible(False)
            roster_member = self.model.find_by_id(
                getattr(self, "roster_selected_member_id", "")
            )
            self.roster_dkp_value.setText(
                self._dkp_text_for_member(roster_member)
                if roster_member is not None else "—"
            )
            if hasattr(self, "roster_current_dkp"):
                self.roster_current_dkp.setText(
                    self._dkp_text_for_member(roster_member)
                    if roster_member is not None else "—"
                )

    def show_member(self, member_id: str) -> None:
        member = self.model.find_by_id(member_id)
        if member is None:
            return
        self.selected_member_id = member.id
        self.detail_name.setText(member.name)
        class_line = " · ".join(value for value in (member.className, member.spec) if value) or "–"
        self.detail_class.setText(class_line)
        self.detail_life.setText(tr(f"life.{member.lifeStatus}"))
        portrait = member_portrait_path(self.model, member)
        self.detail_portrait.set_source(portrait)
        self._set_member_reward_visuals(
            member,
            self.detail_reward_portrait,
            external_rank_label=self.detail_rank_icon,
        )

        race_text = race_display(member.race)
        self.race_combo.setCurrentText(
            race_text if race_text in [self.race_combo.itemText(i) for i in range(self.race_combo.count())]
            else tr("common.not_set")
        )
        self.class_combo.blockSignals(True)
        self.class_combo.setCurrentText(member.className or tr("common.not_set"))
        self.class_combo.blockSignals(False)
        self._update_spec_combo(member.className, member.spec)
        self.character_type_combo.blockSignals(True)
        self.character_type_combo.setCurrentText(character_type_display(member.characterType))
        self.character_type_combo.blockSignals(False)
        self.raid_role_combo.setCurrentText(raid_role_display(member.raidRole))
        self._refresh_associated_main_combo(member)
        self.gear_combo.setCurrentText(gear_status_display(member.gearStatus))
        self.raid_status_combo.setCurrentText(raid_status_display(member.raidStatus))
        self.last_checked_value.setText(member.lastChecked or "–")
        self.notes_edit.setPlainText(member.note or "")
        self.recheck_button.setEnabled(member.lifeStatus == "active")
        self.member_remove_button.setEnabled(member.lifeStatus != "dead")
        points_visible = bool(self.model.active_point_mode())
        self.detail_points_section.setVisible(points_visible)
        if points_visible:
            self._set_member_point_labels(
                member, self.detail_character_points, self.detail_player_points,
                self.detail_player_history,
            )
        self._refresh_visible_dkp_details()

        if member.lifeStatus == "active":
            self.activity_button.setText(tr("checker.mark_inactive"))
            self.activity_button.setEnabled(True)
            self.life_button.setText(tr("checker.mark_dead"))
            self.life_button.setVisible(True)
        elif member.lifeStatus == "inactive":
            self.activity_button.setText(tr("checker.reactivate"))
            self.activity_button.setEnabled(True)
            self.life_button.setText(tr("checker.mark_dead"))
            self.life_button.setVisible(True)
        else:
            self.activity_button.setText(tr("checker.reanimate_dead"))
            self.activity_button.setEnabled(True)
            self.life_button.setVisible(False)

    def clear_detail(self) -> None:
        self.selected_member_id = None
        if not hasattr(self, "detail_name"):
            return
        self.detail_name.setText("–")
        self.detail_class.setText("–")
        self.detail_life.setText("–")
        self.detail_portrait.clear_source()
        self.detail_reward_portrait.clear_reward_badge()
        self.detail_reward_portrait.clear_reward_frame()
        self.detail_rank_icon.clear()
        self.detail_rank_icon.hide()
        self.race_combo.setCurrentIndex(0)
        self.class_combo.blockSignals(True)
        self.class_combo.setCurrentIndex(0)
        self.class_combo.blockSignals(False)
        self._update_spec_combo("", "")
        self.character_type_combo.setCurrentIndex(0)
        self.associated_main_combo.clear()
        self.associated_main_combo.addItem(tr("checker.no_active_main"), None)
        self.associated_main_combo.setEnabled(False)
        self.raid_role_combo.setCurrentIndex(0)
        self.notes_edit.clear()
        self.last_checked_value.setText("–")
        self.member_remove_button.setEnabled(False)
        self.detail_character_points.setText("0")
        self.detail_player_points.setText("–")
        self.detail_points_form.setRowVisible(self.detail_player_points, False)
        self.detail_player_history.setVisible(False)
        self.detail_dkp_value.setText("—")

    def _class_changed(self, value: str) -> None:
        self._update_spec_combo(normalize_class_name(value), "")

    def _detail_character_type_changed(self, _value: str) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        self._refresh_associated_main_combo(member)

    def _refresh_associated_main_combo(self, member: Member | None) -> None:
        if not hasattr(self, "associated_main_combo"):
            return
        self.associated_main_combo.blockSignals(True)
        self.associated_main_combo.clear()
        self.associated_main_combo.addItem(tr("checker.no_active_main"), None)
        mains = sorted((
            value for value in self.model.members
            if value.lifeStatus == "active" and value.characterType == "main"
            and (member is None or value.id != member.id)
        ), key=lambda value: (value.name.casefold(), value.id))
        for value in mains:
            self.associated_main_combo.addItem(value.name, value.id)
        selected = self.model.associated_main(member) if member is not None else None
        if selected is not None:
            index = self.associated_main_combo.findData(selected.id)
            if index >= 0:
                self.associated_main_combo.setCurrentIndex(index)
        character_type = character_type_from_display(self.character_type_combo.currentText())
        is_twink = character_type == "twink"
        self.associated_main_combo.setEnabled(is_twink)
        if hasattr(self, "detail_overview_form"):
            self.detail_overview_form.setRowVisible(self.associated_main_combo, is_twink)
        self.associated_main_combo.blockSignals(False)

    def _update_spec_combo(self, class_name: str, selected: str = "") -> None:
        cls = normalize_class_name(class_name)
        self.spec_combo.clear()
        self.spec_combo.addItem(tr("common.not_set"))
        for spec in CLASS_SPECS.get(cls, []):
            self.spec_combo.addItem(spec)
        valid = normalize_spec(cls, selected)
        self.spec_combo.setCurrentText(valid or tr("common.not_set"))

    def save_selected_member(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if member is None:
            return
        class_name = normalize_class_name(self.class_combo.currentText())
        spec = normalize_spec(class_name, self.spec_combo.currentText())
        character_type = character_type_from_display(self.character_type_combo.currentText())
        raid_role = raid_role_from_display(self.raid_role_combo.currentText())
        associated_main_id = self.associated_main_combo.currentData() if character_type == "twink" else None
        old_assignment = (member.playerId, member.characterType)
        try:
            self.model.assign_character_type(
                member.id, character_type, associated_main_id, raid_role,
            )
        except MainConflictError as conflict:
            answer = QMessageBox.question(
                self, tr("checker.main_conflict_title"),
                tr("checker.main_conflict", name=conflict.existing_main.name, new_name=member.name),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.model.assign_character_type(
                member.id, character_type, associated_main_id, raid_role,
                replace_existing_main=True,
            )
        except ValueError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return

        old_gear, old_raid = member.gearStatus, member.raidStatus
        member.race = race_from_display(self.race_combo.currentText())
        member.className = class_name
        member.spec = spec
        member.classSpec = f"{class_name} / {spec}" if class_name and spec else class_name
        member.gearStatus = gear_status_from_display(self.gear_combo.currentText())
        member.raidStatus = raid_status_from_display(self.raid_status_combo.currentText())
        member.note = self.notes_edit.toPlainText().strip()
        if member.gearStatus != old_gear or member.raidStatus != old_raid:
            member.lastChecked = today_iso()
        self.model.dirty = True
        self.autosave()
        if old_assignment != (member.playerId, member.characterType):
            self._rebuild_raid_derived_state()
        self.refresh_all(select_first=False)
        current_item = self.member_table.currentItem()
        current_id = str(current_item.data(Qt.ItemDataRole.UserRole) or "") if current_item else ""
        if current_id != member.id:
            self._select_member_in_table(member.id)
            self.show_member(member.id)
        self.set_status(tr("checker.saved", name=member.name))


    def confirm_recheck_selected(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if member is None or member.lifeStatus != "active":
            return
        answer = QMessageBox.question(
            self, APP_NAME, tr("checker.confirm_recheck_question", name=member.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        member.lastChecked = today_iso()
        self.model.dirty = True
        self.autosave()
        self.refresh_all(select_first=False)
        self.show_member(member.id)

    # ---------- member actions ----------
    def add_member_dialog(self) -> None:
        name, ok = QInputDialog.getText(self, tr("checker.member_add_title"), tr("checker.exact_character_name"))
        if not ok:
            return
        try:
            member = self.model.add_member(name, "Manuell")
        except ValueError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.autosave()
        self.set_member_tab("Gildenliste", refresh=False)
        if hasattr(self, "search_edit"):
            self.search_edit.blockSignals(True)
            self.search_edit.clear()
            self.search_edit.blockSignals(False)
        if hasattr(self, "gear_filter_combo"):
            self.gear_filter_combo.blockSignals(True)
            self.gear_filter_combo.setCurrentIndex(0)
            self.gear_filter_combo.blockSignals(False)
        if hasattr(self, "enchant_filter_combo"):
            self.enchant_filter_combo.blockSignals(True)
            self.enchant_filter_combo.setCurrentIndex(0)
            self.enchant_filter_combo.blockSignals(False)
        self.refresh_member_table()
        self.show_member(member.id)
        self._select_member_in_table(member.id)
        self.set_status(tr("checker.added", name=member.name))

    def remove_selected_member(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if member is None:
            QMessageBox.information(self, APP_NAME, tr("checker.select_character"))
            return
        if member.lifeStatus == "dead":
            QMessageBox.warning(self, APP_NAME, tr("checker.dead_cannot_delete"))
            return
        answer = QMessageBox.question(
            self, tr("checker.remove_member_title"), tr("checker.remove_member_question", name=member.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.model.remove_member(member.id)
        self.selected_member_id = None
        self.autosave()
        self.refresh_all(select_first=True)
        self.set_status(tr("checker.member_removed", name=member.name))

    def import_csv(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, tr("checker.select_raid_csv"), "", f"CSV (*.csv);;{tr('common.all_files')} (*.*)")
        if not path:
            return
        try:
            names = read_csv_names(Path(path))
            existing, new_names, dead_existing = self.model.classify_member_import(names)
            if not new_names:
                text = tr("checker.import_all_present", count=len(names))
                if dead_existing:
                    text += "\n\n" + tr("checker.import_dead_remain", count=len(dead_existing))
                QMessageBox.information(self, APP_NAME, text)
                return
            preview = "\n".join(new_names[:18])
            extra = "" if len(new_names) <= 18 else "\n" + tr("checker.import_more", count=len(new_names) - 18)
            dead_line = "\n" + tr("checker.import_dead_line", count=len(dead_existing)) if dead_existing else ""
            question = tr(
                "checker.import_prompt", total=len(names), existing=len(existing), dead_line=dead_line,
                new_count=len(new_names), preview=preview, extra=extra,
            )
            answer = QMessageBox.question(
                self, APP_NAME, question,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            created = self.model.import_active_members(names, "Warcraft Logs CSV")
            self.autosave()
            self.set_member_tab("Gildenliste", refresh=False)
            self.refresh_all(select_first=True)
            self.set_status(tr("checker.csv_imported", count=len(created)))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, tr("checker.import_failed", error=exc))

    def open_armory_selected(self) -> None:
        self._open_armory_for_id(self.selected_member_id or "")

    def _open_armory_for_id(self, member_id: str) -> None:
        member = self.model.find_by_id(member_id)
        if member is None:
            return
        webbrowser.open(build_armory_url(member.name, self.model.region, self.model.realm, self.model.game_version))
        self.set_status(tr("checker.armory_opened", name=member.name))

    def toggle_activity_selected(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if member is None:
            return
        try:
            if member.lifeStatus == "active":
                answer = QMessageBox.question(
                    self, APP_NAME, tr("checker.mark_inactive_question", name=member.name),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
                self.model.set_member_life_status(member.id, "inactive")
                target_tab = "Inaktiv"
            elif member.lifeStatus == "inactive":
                self.model.set_member_life_status(member.id, "active")
                target_tab = "Gildenliste"
            else:
                current = self.model.find_current_by_name(member.name)
                if current is not None and current.id != member.id:
                    QMessageBox.warning(self, APP_NAME, tr("checker.current_incarnation_blocks", name=current.name))
                    return
                answer = QMessageBox.question(
                    self, tr("checker.reanimate_dead_title"), tr("checker.reanimate_dead_question", name=member.name),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
                try:
                    self.model.set_member_life_status(member.id, "active", allow_dead_reanimation=True)
                except MainConflictError as conflict:
                    replace = QMessageBox.question(
                        self, tr("checker.main_conflict_title"),
                        tr("checker.main_conflict", name=conflict.existing_main.name, new_name=member.name),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    if replace != QMessageBox.StandardButton.Yes:
                        return
                    self.model.set_member_life_status(
                        member.id, "active", replace_existing_main=True, allow_dead_reanimation=True,
                    )
                target_tab = "Gildenliste"
        except MainConflictError as conflict:
            replace = QMessageBox.question(
                self, tr("checker.main_conflict_title"),
                tr("checker.main_conflict", name=conflict.existing_main.name, new_name=member.name),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if replace != QMessageBox.StandardButton.Yes:
                return
            self.model.set_member_life_status(member.id, "active", replace_existing_main=True)
            target_tab = "Gildenliste"
        except ValueError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.autosave()
        self.set_member_tab(target_tab, refresh=False)
        self.refresh_all(select_first=False)
        self.show_member(member.id)
        self._select_member_in_table(member.id)

    def _choose_main_successor(
            self, main: Member, excluded_member_ids: Iterable[str],
    ) -> tuple[bool, str | None]:
        candidates = self.model.main_successor_candidates(main.id, excluded_member_ids)
        if not candidates:
            return True, None
        labels = [
            f"{member.name} · {character_type_display(member.characterType)} · "
            f"{tr(f'life.{member.lifeStatus}')} · {member.id}"
            for member in candidates
        ]
        selected, accepted = QInputDialog.getItem(
            self,
            tr("checker.main_succession_title"),
            tr("checker.main_succession_prompt", name=main.name),
            labels, 0, False,
        )
        if not accepted or selected not in labels:
            return False, None
        return True, candidates[labels.index(selected)].id

    def _collect_main_succession_decisions(
            self, member_ids: Iterable[str],
    ) -> dict[str, str | None] | None:
        selected_ids = {str(member_id or "").strip() for member_id in member_ids}
        decisions: dict[str, str | None] = {}
        mains = sorted((
            member for member in self.model.members
            if member.id in selected_ids
            and member.lifeStatus == "active"
            and member.characterType == "main"
        ), key=lambda member: (member.name.casefold(), member.name, member.id))
        for main in mains:
            accepted, successor_id = self._choose_main_successor(main, selected_ids)
            if not accepted:
                return None
            decisions[main.id] = successor_id
        return decisions

    def _mark_members_dead(
            self, member_ids: Iterable[str],
            succession_decisions: dict[str, str | None] | None = None,
    ) -> list[Member]:
        """Mark the selected living members dead as one management action."""
        selected: list[Member] = []
        seen: set[str] = set()
        for member_id in member_ids:
            key = str(member_id or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            member = self.model.find_by_id(key)
            if member is not None and member.lifeStatus != "dead":
                selected.append(member)
        if not selected:
            return []

        selected_ids = {member.id for member in selected}
        decisions = dict(succession_decisions or {})
        affected_ids = selected_ids | {
            successor_id for successor_id in decisions.values() if successor_id
        }
        affected = {
            member.id: member for member in self.model.members if member.id in affected_ids
        }
        member_states = {
            member_id: copy.deepcopy(member.__dict__)
            for member_id, member in affected.items()
        }
        previous_dirty = self.model.dirty

        for member in selected:
            if member.lifeStatus == "active" and member.characterType == "main":
                self.model.validate_main_successor(
                    member.id, decisions.get(member.id), selected_ids,
                )

        # Archive every currently available portrait first. If archiving fails, no
        # life status has been changed yet.
        for member in selected:
            archive_portrait(self.model, member)
        death_date = today_iso()
        try:
            for member in selected:
                if member.lifeStatus == "active" and member.characterType == "main":
                    self.model.mark_main_dead_with_successor(
                        member.id, decisions.get(member.id), death_date,
                        excluded_member_ids=selected_ids,
                    )
                else:
                    self.model.set_member_life_status(member.id, "dead")
                    member.deathDate = death_date
        except Exception:
            for member_id, state in member_states.items():
                affected[member_id].__dict__.clear()
                affected[member_id].__dict__.update(state)
            self.model.dirty = previous_dirty
            raise
        return selected

    def open_wipe_dialog(self) -> None:
        living = sorted(
            (member for member in self.model.members if member.lifeStatus != "dead"),
            key=lambda member: (member.name.casefold(), member.name, member.id),
        )
        if not living:
            QMessageBox.information(self, tr("checker.wipe_title"), tr("checker.wipe_none_selected"))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("checker.wipe_title"))
        dialog.resize(460, 560)
        layout = QVBoxLayout(dialog)
        help_label = QLabel(tr("checker.wipe_help"))
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget(scroll)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(6, 6, 6, 6)
        checkboxes: list[tuple[QCheckBox, str]] = []
        for member in living:
            details = " · ".join(
                value for value in (
                    member.className,
                    tr(f"life.{member.lifeStatus}"),
                ) if value
            )
            label = member.name if not details else f"{member.name} · {details}"
            checkbox = QCheckBox(label)
            content_layout.addWidget(checkbox)
            checkboxes.append((checkbox, member.id))
        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("checker.mark_dead"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_ids = [member_id for checkbox, member_id in checkboxes if checkbox.isChecked()]
        if not selected_ids:
            QMessageBox.information(self, tr("checker.wipe_title"), tr("checker.wipe_none_selected"))
            return
        answer = QMessageBox.question(
            self, tr("checker.wipe_title"), tr("checker.wipe_confirm", count=len(selected_ids)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        succession_decisions = self._collect_main_succession_decisions(selected_ids)
        if succession_decisions is None:
            self.set_status(tr("checker.main_succession_cancelled"))
            return
        try:
            changed = self._mark_members_dead(selected_ids, succession_decisions)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        if not changed:
            return
        self.autosave()
        self.clear_detail()
        self.refresh_all(select_first=False)
        self.set_status(tr("checker.wipe_done", count=len(changed)))

    def mark_dead_selected(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if member is None or member.lifeStatus == "dead":
            return
        answer = QMessageBox.question(
            self, APP_NAME, tr("checker.mark_dead_question", name=member.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        succession_decisions = self._collect_main_succession_decisions([member.id])
        if succession_decisions is None:
            self.set_status(tr("checker.main_succession_cancelled"))
            return
        try:
            changed = self._mark_members_dead([member.id], succession_decisions)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return
        if not changed:
            return
        self.autosave()
        self.refresh_all(select_first=False)
        if member.id in {visible.id for visible in self._filtered_members()}:
            self._select_member_in_table(member.id)
            self.show_member(member.id)
        else:
            self.clear_detail()
        self.set_status(tr("checker.marked_dead", name=member.name))

    # ---------- roster ----------
    def _schedule_roster_zoom(self, value: int) -> None:
        self._roster_zoom_pending = max(60, min(140, int(value)))
        if hasattr(self, "roster_zoom_value"):
            self.roster_zoom_value.setText(f"{self._roster_zoom_pending} %")
        self._roster_zoom_timer.start()

    def _apply_roster_zoom(self) -> None:
        value = max(60, min(140, int(self._roster_zoom_pending)))
        if value == self._roster_zoom_percent:
            return
        self._roster_zoom_percent = value
        self._roster_cards_dirty = True
        if self._roster_view_mode == "cards":
            self._refresh_current_roster_view()

    def refresh_roster(self) -> None:
        self._roster_cards_dirty = True
        self._roster_list_dirty = True
        self._refresh_current_roster_view()

    def _roster_groups(self) -> dict[str, list[Member]]:
        groups = group_roster_members(self.model.members)
        if self.roster_search_edit.text().strip():
            groups = {
                role: [member for member in members if self._roster_search_matches(member)]
                for role, members in groups.items()
            }
        return groups

    def _rebuild_roster_cards(self, groups: dict[str, list[Member]]) -> None:
        while self.roster_layout.count():
            item = self.roster_layout.takeAt(0)
            widget = item.widget()
            if widget:
                # Roster ist ab v0.8.3 die Startseite. Beim sofortigen erneuten
                # Rendern dürfen alte Abschnitts-Widgets nicht bis zum nächsten
                # Deferred-Delete als Kinder der Ansicht erhalten bleiben.
                widget.setParent(None)
                widget.deleteLater()
        self._roster_cards = []
        self._roster_grids = []
        role_labels = {
            "tank": tr("roster.tanks"),
            "healer": tr("roster.healers"),
            "dps": tr("roster.dps"),
            "not_set": tr("roster.unassigned"),
        }
        factor = self._roster_zoom_percent / 100.0
        gap = max(8, round(14 * factor))
        card_width = max(122, round(RosterCard.BASE_CARD_WIDTH * factor))
        for role in ROSTER_ROLE_ORDER:
            members = groups.get(role, [])
            section = QFrame()
            section.setObjectName("rosterSection")
            section_layout = QVBoxLayout(section)
            section_margin = max(7, round(12 * min(1.0, factor)))
            section_layout.setContentsMargins(section_margin, section_margin, section_margin, section_margin)
            section_layout.setSpacing(max(5, round(8 * factor)))

            heading = QLabel(f"{role_labels[role]}   {len(members)}")
            heading.setObjectName("rosterSectionTitle")
            heading_size = max(10, round(12 * min(1.0, factor)))
            heading_color = "#b8a47b" if role == "not_set" else "#e0bd72"
            heading.setStyleSheet(
                f"font-size:{heading_size}pt;font-weight:700;color:{heading_color};"
                "background:transparent;border:none;"
            )
            section_layout.addWidget(heading)

            if members:
                grid = ResponsiveCardGrid(card_width, gap=gap)
                cards: list[QWidget] = []
                for member in members:
                    card = RosterCard(
                        self.model,
                        member,
                        self._roster_zoom_percent,
                        rank_path=self._rank_path_for_member(member, 96),
                    )
                    card.clicked.connect(self._roster_card_clicked)
                    cards.append(card)
                    self._roster_cards.append(card)
                grid.set_items(cards)
                self._roster_grids.append(grid)
                section_layout.addWidget(grid)
            else:
                empty = QLabel(tr("roster.empty"))
                empty.setObjectName("subtle")
                empty.setStyleSheet("background:transparent;border:none;")
                empty.setMinimumHeight(max(28, round(38 * factor)))
                section_layout.addWidget(empty)

            self.roster_layout.addWidget(section)
        self.roster_layout.addStretch(1)

    def _rebuild_roster_list(self, groups: dict[str, list[Member]]) -> None:
        visible_members = [member for role in ROSTER_ROLE_ORDER for member in groups[role]]
        self.roster_list.setSortingEnabled(False)
        self.roster_list.setRowCount(len(visible_members))
        # Beide DKP-Aggregationen sind reine Funktionen des aktuellen Modellzustands;
        # die nachfolgende Zeilenschleife verändert das Modell nicht. Sie werden
        # deshalb genau einmal je Refresh ermittelt und in der Schleife nur noch
        # nachgeschlagen, statt pro Zeile vollständig neu aggregiert zu werden.
        eternal_character_by_member_id = (
            self.model.eternal_character_totals() if visible_members else {}
        )
        eternal_player_by_player_id = (
            self.model.eternal_player_totals() if visible_members else {}
        )
        for row, member in enumerate(visible_members):
            current_dkp = self._dkp_text_for_member(member)
            eternal_character = self._format_dkp_value(
                eternal_character_by_member_id.get(member.id, (0, 0))[0]
            )
            eternal_player = self._format_dkp_value(
                eternal_player_by_player_id.get(member.playerId, (0, 0))[0]
                if member.playerId else None
            )
            values = (
                member.name,
                member.className or tr("common.not_set"),
                raid_role_display(member.raidRole),
                character_type_display(member.characterType),
                gear_status_display(member.gearStatus),
                raid_status_display(member.raidStatus),
                tr(f"life.{member.lifeStatus}"),
                current_dkp,
                eternal_character,
                eternal_player,
            )
            for column, value in enumerate(values):
                item = NumericSortItem(str(value)) if column >= 7 else QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, member.id)
                if column >= 7:
                    item.setData(int(Qt.ItemDataRole.UserRole) + 1, float(value) if value != "—" else float("-inf"))
                if column == 1 and member.className:
                    icon_path = class_icon_path(member.className)
                    if icon_path.is_file():
                        item.setIcon(QIcon(str(icon_path)))
                    item.setForeground(QColor(CLASS_COLORS.get(member.className, "#d0d0d0")))
                self.roster_list.setItem(row, column, item)
        self.roster_list.setSortingEnabled(True)
        self.roster_list.sortItems(self._roster_list_sort_column, self._roster_list_sort_order)

    def _refresh_current_roster_view(self) -> None:
        if self._roster_view_mode == "list":
            if self._roster_list_dirty:
                self._rebuild_roster_list(self._roster_groups())
                self._roster_list_dirty = False
        elif self._roster_cards_dirty:
            self._rebuild_roster_cards(self._roster_groups())
            self._roster_cards_dirty = False
        self.roster_content_stack.setCurrentWidget(
            self.roster_list if self._roster_view_mode == "list" else self.roster_scroll
        )
        selected = self.model.find_by_id(getattr(self, "roster_selected_member_id", ""))
        if selected is not None and selected.lifeStatus == "active":
            self._show_roster_detail(selected.id)
        else:
            self.roster_selected_member_id = None
            self.roster_detail_panel.hide()
        self._schedule_roster_reflow()

    def _roster_card_clicked(self, member_id: str) -> None:
        self._show_roster_detail(member_id)

    def _show_roster_detail(self, member_id: str) -> None:
        member = self.model.find_by_id(member_id)
        if member is None or member.lifeStatus != "active":
            return
        self.roster_selected_member_id = member.id
        self.roster_detail_name.setText(member.name)
        race_text = race_display(member.race) if member.race else tr("common.not_set")
        class_text = member.className or tr("common.not_set")
        class_color = CLASS_COLORS.get(member.className, "#d0d0d0")
        identity_parts = [
            html.escape(race_text),
            (
                f'<span style="color:{class_color};font-weight:600;">'
                f'{html.escape(class_text)}</span>'
            ),
        ]
        if member.spec:
            identity_parts.append(html.escape(member.spec))
        self.roster_detail_class.setText(" · ".join(identity_parts))
        self.roster_detail_life.setText(tr(f"life.{member.lifeStatus}"))
        raid_status = member.raidStatus or ""
        self.roster_detail_raid.setText(raid_status_display(raid_status))
        self.roster_detail_raid.setStyleSheet(
            "background:#355f45;" if raid_status == "Bereit" else
            ("background:#633b40;" if raid_status == "Nicht bereit" else "")
        )
        self.roster_detail_portrait.set_source(member_portrait_path(self.model, member))
        self._set_member_reward_visuals(
            member,
            self.roster_reward_portrait,
            external_rank_label=self.roster_rank_icon,
        )
        self.roster_detail_type.setText(character_type_display(member.characterType))
        self.roster_detail_role.setText(raid_role_display(member.raidRole))
        self.roster_detail_rank.setText(self._rank_text_for_member(member))
        self.roster_detail_checked.setText(member.lastChecked or "–")
        self.roster_detail_notes.setPlainText(member.note or "")
        points_visible = bool(self.model.active_point_mode())
        self.roster_points_section.setVisible(points_visible)
        if points_visible:
            self._set_member_point_labels(
                member, self.roster_character_points, self.roster_player_points,
                self.roster_player_history,
            )
        self.roster_dkp_section.setVisible(False)
        self.roster_profile_button.setVisible(bool(
            member.playerId and self.model.player_is_active(member.playerId)
        ))
        self.roster_detail_panel.show()
        total = max(900, self.roster_splitter.width())
        self.roster_splitter.setSizes([max(520, total - 400), 400])
        self._schedule_roster_reflow()

    def export_roster_png(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, tr("roster.export_png"), "Roster.png", "PNG (*.png)")
        if not path:
            return
        try:
            summary = render_roster_png(self.model, Path(path))
            self.set_status(tr("roster.export_png_done", width=summary["size"][0], height=summary["size"][1]))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))

    # ---------- graveyard ----------
    def _schedule_graveyard_zoom(self, value: int) -> None:
        self._graveyard_zoom_pending = max(60, min(140, int(value)))
        self._graveyard_zoom_timer.start()

    def _apply_graveyard_zoom(self) -> None:
        value = max(60, min(140, int(self._graveyard_zoom_pending)))
        if value == self._graveyard_zoom_percent:
            return
        self._graveyard_zoom_percent = value
        self.refresh_graveyard()

    def refresh_graveyard(self) -> None:
        dead = [member for member in self.model.members if member.lifeStatus == "dead"]
        dead.sort(key=lambda m: (m.deathDate or "", m.name.casefold()), reverse=True)
        inventory = None
        by_id = {}
        try:
            inventory = self.model.gravestone_inventory()
            by_id = inventory.by_id()
        except Exception:
            by_id = {}

        factor = self._graveyard_zoom_percent / 100.0
        render_size = (
            max(96, round(GRAVESTONE_CARD_SIZE[0] * factor)),
            max(132, round(GRAVESTONE_CARD_SIZE[1] * factor)),
        )
        self._grave_pixmaps.clear()
        cards: list[tuple[str, QPixmap]] = []
        for member in dead:
            template = by_id.get(member.graveTemplateId)
            pixmap = self._grave_pixmap_for_member(member, template, render_size)
            cards.append((member.id, pixmap))

        summary = tr("checker.graveyard_summary", count=len(dead))
        self.grave_canvas.set_scene(
            cards,
            zoom_percent=self._graveyard_zoom_percent,
            summary=summary,
            empty_text=tr("checker.graveyard_empty"),
        )

    @staticmethod
    def _image_signature(path: Path | None) -> tuple[str, int, int] | None:
        if path is None:
            return None
        try:
            resolved = str(path.resolve())
        except OSError:
            resolved = str(path.absolute())
        try:
            stat = path.stat()
            return resolved, int(stat.st_mtime_ns), int(stat.st_size)
        except OSError:
            return resolved, 0, 0

    @staticmethod
    def _trim_image_cache(cache: dict, limit: int) -> None:
        while len(cache) > limit:
            cache.pop(next(iter(cache)))

    def _cached_graveyard_template(self, template,
                                   size: tuple[int, int]):
        if template is not None:
            path = template.path
            key = (
                template.grave_template_id,
                template.sha256,
                self._image_signature(path),
                size,
            )
        else:
            path = gravestone_placeholder_path()
            key = ("placeholder", self._image_signature(path), size)
        frame = self._graveyard_template_cache.get(key)
        if frame is None:
            frame = prepare_gravestone_template(path, size)
            self._graveyard_template_cache[key] = frame
            self._trim_image_cache(self._graveyard_template_cache, 64)
        return frame

    def _graveyard_card_key(self, member: Member, template, portrait_path: Path | None,
                            size: tuple[int, int]) -> tuple:
        template_key = (
            template.grave_template_id,
            template.sha256,
            self._image_signature(template.path),
            template.category,
            template.default_text_safe_area,
        ) if template is not None else (
            member.graveTemplateId,
            "missing",
            self._image_signature(gravestone_placeholder_path()),
        )
        return (
            member.id,
            member.name,
            member.className,
            member.deathDate,
            member.portraitOffsetX,
            member.portraitOffsetY,
            member.portraitZoom,
            member.textOffsetX,
            member.textOffsetY,
            member.textScale,
            template_key,
            self._image_signature(portrait_path),
            size,
            get_language(),
        )

    def _grave_pixmap_for_member(self, member: Member, template,
                                 size: tuple[int, int] = GRAVESTONE_CARD_SIZE) -> QPixmap:
        from PIL import Image, ImageDraw
        portrait = graveyard_member_portrait_path(self.model, member) if template is not None else None
        cache_key = self._graveyard_card_key(member, template, portrait, size)
        pixmap = self._graveyard_card_cache.get(cache_key)
        if pixmap is not None:
            self._grave_pixmaps[member.id] = pixmap
            return pixmap
        stale = [
            key for key in self._graveyard_card_cache
            if key[0] == member.id and key != cache_key
        ]
        for key in stale:
            self._graveyard_card_cache.pop(key, None)
        if template is not None:
            try:
                frame = self._cached_graveyard_template(template, size)
            except Exception:
                frame = Image.new("RGBA", size, (0, 0, 0, 0))
        else:
            try:
                frame = self._cached_graveyard_template(None, size)
            except Exception:
                frame = Image.new("RGBA", size, (0, 0, 0, 0))
        image = render_gravestone_card(member, frame, portrait, size)
        if template is None:
            scale_x = size[0] / max(1, GRAVESTONE_CARD_SIZE[0])
            scale_y = size[1] / max(1, GRAVESTONE_CARD_SIZE[1])
            draw = ImageDraw.Draw(image)
            left = round(12 * scale_x)
            top = round(112 * scale_y)
            right = size[0] - left
            bottom = round(164 * scale_y)
            draw.rounded_rectangle(
                (left, top, right, bottom),
                radius=max(4, round(8 * min(scale_x, scale_y))),
                fill="#241d1dcc", outline="#7b625c",
            )
            draw.multiline_text(
                (size[0] // 2, round(138 * scale_y)),
                tr("graveyard.not_available_card"),
                anchor="mm", align="center", fill="#e2d0c9",
            )
        pixmap = pil_to_pixmap(image)
        self._graveyard_card_cache[cache_key] = pixmap
        self._trim_image_cache(self._graveyard_card_cache, 128)
        self._grave_pixmaps[member.id] = pixmap
        return pixmap

    def _grave_card_clicked(self, member_id: str) -> None:
        """Open the gravestone adjustment dialog, matching the legacy cemetery."""
        self.open_gravestone_editor(member_id)

    def open_gravestone_editor(self, member_id: str) -> QDialog | None:
        member = self.model.find_by_id(member_id)
        if member is None or member.lifeStatus != "dead":
            return None

        try:
            inventory, available_templates = self.model.available_gravestone_templates(member.id)
            templates = inventory.by_id()
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return None

        candidate_ids = [template.grave_template_id for template in available_templates]
        if member.graveTemplateId and member.graveTemplateId not in candidate_ids:
            candidate_ids.insert(0, member.graveTemplateId)
        initial_template_id = member.graveTemplateId or (candidate_ids[0] if candidate_ids else "")
        portrait_path = member_portrait_path(self.model, member)
        portrait_image = None
        if portrait_path is not None:
            try:
                from PIL import Image, ImageOps
                with Image.open(portrait_path) as raw:
                    portrait_image = ImageOps.exif_transpose(raw).convert("RGBA").copy()
            except (OSError, ValueError):
                pass

        dialog = QDialog(self)
        dialog.setWindowTitle(f"{tr('graveyard.adjust_portrait')} · {member.name}")
        dialog.setModal(True)
        dialog.setMinimumWidth(390)
        dialog.setMaximumWidth(430)
        root = QVBoxLayout(dialog)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        help_label = QLabel(tr("graveyard.adjust_help"))
        help_label.setObjectName("subtle")
        help_label.setWordWrap(True)
        root.addWidget(help_label)

        template_row = QHBoxLayout()
        previous_button = QPushButton("◀")
        next_button = QPushButton("▶")
        previous_button.setFixedWidth(42)
        next_button.setFixedWidth(42)
        template_label = QLabel()
        template_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        template_label.setWordWrap(True)
        template_row.addWidget(previous_button)
        template_row.addWidget(template_label, 1)
        template_row.addWidget(next_button)
        root.addLayout(template_row)

        preview = GravestoneEditorPreview(dialog)
        root.addWidget(preview, 0, Qt.AlignmentFlag.AlignHCenter)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel(tr("common.edit")))
        target_combo = QComboBox()
        target_combo.addItem(tr("graveyard.move_portrait"), "portrait")
        target_combo.addItem(tr("graveyard.move_text"), "text")
        target_row.addWidget(target_combo, 1)
        root.addLayout(target_row)

        portrait_zoom = float(member.portraitZoom)
        text_scale = float(member.textScale)
        portrait_offset_x = float(member.portraitOffsetX)
        portrait_offset_y = float(member.portraitOffsetY)
        text_offset_x = float(member.textOffsetX)
        text_offset_y = float(member.textOffsetY)
        selected_template_id = initial_template_id

        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel(tr("graveyard.zoom")))
        zoom_slider = QSlider(Qt.Orientation.Horizontal)
        zoom_slider.setRange(
            round(GRAVESTONE_PORTRAIT_ZOOM_RANGE[0] * 100),
            round(GRAVESTONE_PORTRAIT_ZOOM_RANGE[1] * 100),
        )
        zoom_slider.setValue(round(portrait_zoom * 100))
        zoom_label = QLabel(f"{portrait_zoom:.2f}×")
        zoom_label.setMinimumWidth(50)
        zoom_row.addWidget(zoom_slider, 1)
        zoom_row.addWidget(zoom_label)
        root.addLayout(zoom_row)

        text_scale_row = QHBoxLayout()
        text_scale_row.addWidget(QLabel(tr("graveyard.text_scale")))
        text_scale_slider = QSlider(Qt.Orientation.Horizontal)
        text_scale_slider.setRange(
            round(GRAVESTONE_TEXT_SCALE_RANGE[0] * 100),
            round(GRAVESTONE_TEXT_SCALE_RANGE[1] * 100),
        )
        text_scale_slider.setValue(round(text_scale * 100))
        text_scale_label = QLabel(f"{text_scale:.2f}×")
        text_scale_label.setMinimumWidth(50)
        text_scale_row.addWidget(text_scale_slider, 1)
        text_scale_row.addWidget(text_scale_label)
        root.addLayout(text_scale_row)

        date_row = QHBoxLayout()
        date_row.addWidget(QLabel(tr("graveyard.death_date_label")))
        death_date_edit = QLineEdit(member.deathDate)
        death_date_edit.setMaximumWidth(145)
        date_row.addStretch(1)
        format_label = QLabel(tr("graveyard.death_date_format"))
        format_label.setObjectName("subtle")
        date_row.addWidget(format_label)
        date_row.addWidget(death_date_edit)
        root.addLayout(date_row)

        button_row = QHBoxLayout()
        reset_button = QPushButton(tr("graveyard.reset"))
        cancel_button = QPushButton(tr("graveyard.cancel"))
        apply_button = QPushButton(tr("graveyard.apply"))
        set_button_role(apply_button, primary=True)
        button_row.addWidget(reset_button)
        button_row.addStretch(1)
        button_row.addWidget(cancel_button)
        button_row.addWidget(apply_button)
        root.addLayout(button_row)

        redraw_timer = QTimer(dialog)
        redraw_timer.setSingleShot(True)
        redraw_timer.setInterval(90)

        def selected_frame():
            from PIL import Image
            selected = templates.get(selected_template_id)
            if selected is None:
                return Image.new("RGBA", GRAVESTONE_EDITOR_SIZE, (0, 0, 0, 0))
            try:
                return self._cached_graveyard_template(selected, GRAVESTONE_EDITOR_SIZE)
            except (OSError, ValueError):
                return Image.new("RGBA", GRAVESTONE_EDITOR_SIZE, (0, 0, 0, 0))

        def redraw() -> None:
            from PIL import ImageDraw
            adjusted = Member.from_dict(member.to_dict(), member.id)
            adjusted.portraitOffsetX = normalize_portrait_offset(portrait_offset_x)
            adjusted.portraitOffsetY = normalize_portrait_offset(portrait_offset_y)
            adjusted.portraitZoom = normalize_portrait_zoom(zoom_slider.value() / 100.0)
            adjusted.textOffsetX = normalize_text_offset(text_offset_x)
            adjusted.textOffsetY = normalize_text_offset(text_offset_y)
            adjusted.textScale = normalize_text_scale(text_scale_slider.value() / 100.0)
            adjusted.deathDate = death_date_edit.text().strip()
            card = render_gravestone_card(
                adjusted, selected_frame(), portrait_path, GRAVESTONE_EDITOR_SIZE,
                portrait_image=portrait_image,
            )
            selected = templates.get(selected_template_id)
            if selected is None:
                draw = ImageDraw.Draw(card)
                label = tr(
                    "graveyard.template_missing" if selected_template_id
                    else "graveyard.no_free_template",
                )
                draw.rounded_rectangle((18, 165, 312, 240), radius=10,
                                       fill="#241d1dcc", outline="#a46b61")
                draw.multiline_text((165, 202), label, anchor="mm", align="center",
                                    fill="#f3d9d3")
            preview.setPixmap(pil_to_pixmap(card))
            zoom_label.setText(f"{adjusted.portraitZoom:.2f}×")
            text_scale_label.setText(f"{adjusted.textScale:.2f}×")
            if selected is None:
                template_label.setText(tr(
                    "graveyard.template_missing" if selected_template_id
                    else "graveyard.no_free_template",
                ))
            else:
                try:
                    index = candidate_ids.index(selected_template_id) + 1
                except ValueError:
                    index = 1
                template_label.setText(tr(
                    "graveyard.template_position", current=index,
                    total=max(1, len(candidate_ids)), filename=selected.path.name,
                ))

        def schedule_redraw(*_args) -> None:
            redraw_timer.start()

        def redraw_now() -> None:
            redraw_timer.stop()
            redraw()

        def flush_scheduled_redraw() -> None:
            if redraw_timer.isActive():
                redraw_now()

        redraw_timer.timeout.connect(redraw)

        def change_template(step: int) -> None:
            nonlocal selected_template_id
            if not candidate_ids:
                return
            try:
                index = candidate_ids.index(selected_template_id)
            except ValueError:
                index = 0
            selected_template_id = candidate_ids[(index + step) % len(candidate_ids)]
            redraw_now()

        def move_preview(dx: float, dy: float) -> None:
            nonlocal portrait_offset_x, portrait_offset_y, text_offset_x, text_offset_y
            if target_combo.currentData() == "text":
                text_offset_x, text_offset_y = shifted_text_offsets(
                    text_offset_x, text_offset_y, dx, dy, GRAVESTONE_EDITOR_SIZE,
                )
            else:
                portrait_box = detect_gravestone_portrait_opening(selected_frame()).box
                portrait_offset_x, portrait_offset_y = shifted_portrait_offsets(
                    portrait_offset_x, portrait_offset_y, dx, dy,
                    (portrait_box[2] - portrait_box[0], portrait_box[3] - portrait_box[1]),
                )
            schedule_redraw()

        def reset_text() -> None:
            nonlocal text_offset_x, text_offset_y
            text_offset_x = 0.0
            text_offset_y = 0.0
            text_scale_slider.setValue(100)
            redraw_now()

        def apply_changes() -> None:
            redraw_timer.stop()
            try:
                self.model.set_gravestone_adjustment(
                    member.id, selected_template_id,
                    portrait_offset_x, portrait_offset_y, zoom_slider.value() / 100.0,
                    text_offset_x, text_offset_y, text_scale_slider.value() / 100.0,
                    death_date_edit.text(),
                )
            except ValueError as exc:
                QMessageBox.warning(dialog, APP_NAME, str(exc))
                return
            self.autosave()
            self.refresh_graveyard()
            self.set_status(tr("graveyard.adjust_saved", name=member.name))
            dialog.accept()

        def cancel_changes() -> None:
            redraw_timer.stop()
            dialog.reject()

        previous_button.clicked.connect(lambda: change_template(-1))
        next_button.clicked.connect(lambda: change_template(1))
        preview.dragged.connect(move_preview)
        preview.dragFinished.connect(flush_scheduled_redraw)
        zoom_slider.valueChanged.connect(schedule_redraw)
        zoom_slider.sliderReleased.connect(flush_scheduled_redraw)
        text_scale_slider.valueChanged.connect(schedule_redraw)
        text_scale_slider.sliderReleased.connect(flush_scheduled_redraw)
        death_date_edit.textChanged.connect(schedule_redraw)
        death_date_edit.editingFinished.connect(flush_scheduled_redraw)
        reset_button.clicked.connect(reset_text)
        cancel_button.clicked.connect(cancel_changes)
        apply_button.clicked.connect(apply_changes)
        dialog.accepted.connect(redraw_timer.stop)
        dialog.rejected.connect(redraw_timer.stop)
        redraw_now()
        dialog.exec()
        return dialog

    # ---------- raids ----------
    def _selected_raid(self):
        rows = self.raid_table.selectionModel().selectedRows() if self.raid_table.selectionModel() else []
        if not rows:
            return None
        item = self.raid_table.item(rows[0].row(), 0)
        raid_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        return self.model.find_raid_by_id(str(raid_id)) if raid_id else None

    def _raid_table_clicked(self, row: int, column: int) -> None:
        if column != 5:
            return
        item = self.raid_table.item(row, 0)
        raid_id = str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""
        raid = self.model.find_raid_by_id(raid_id)
        if raid is not None and raid.warcraftLogsUrl:
            webbrowser.open_new_tab(raid.warcraftLogsUrl)

    def _point_entries(self) -> tuple[object, ...]:
        if not self.model.raid_points.enabled:
            return ()
        return tuple(self._raid_point_projection or ())

    def _rebuild_raid_derived_state(self, *, show_errors: bool = True) -> bool:
        """Refresh derived attendance views and the point cache after domain events."""
        try:
            if self.model.raid_points.enabled:
                # includedRaidIds is a persisted projection, never the source of
                # truth. Legacy saves without a mode use the visible all-raids
                # default when an explicit rebuild is requested.
                if self.model.raid_points_legacy_scope_required:
                    return False
                if self.model.raid_points.calculation_mode is None:
                    return False
                self.model.raid_points.rebuild_scope(self.model.raids)
            self._raid_point_projection = (
                build_point_history(
                    self.model.raid_points, self.model.raids, self.model.raid_attendance,
                )
                if self.model.raid_points.enabled else None
            )
        except Exception as exc:
            if show_errors:
                QMessageBox.warning(self, APP_NAME, str(exc))
            return False
        self._sync_points_ui_visibility()
        self._rebuild_reward_assignments()
        self._invalidate_raid_views()
        if self.stack.currentWidget() is self._pages.get("raid"):
            self._refresh_current_raid_tab()
        self._refresh_visible_point_details()
        self._refresh_visible_reward_details()
        return True

    def _sync_points_ui_visibility(self) -> None:
        mode = self.model.active_point_mode()
        enabled = bool(mode)
        raid_mode = mode == POINT_MODE_RAID
        if hasattr(self, "raid_points_button"):
            self.raid_points_button.setVisible(raid_mode)
            history_index = self.raid_subtabs.indexOf(self.point_history_page)
            if raid_mode and history_index < 0:
                history_index = self.raid_subtabs.addTab(
                    self.point_history_page, tr("raid_points.history_tab"),
                )
            elif not raid_mode and history_index >= 0:
                if self.raid_subtabs.currentIndex() == history_index:
                    self.raid_subtabs.setCurrentIndex(0)
                self.raid_subtabs.removeTab(history_index)
                history_index = -1
            self.point_history_tab_index = history_index
        if hasattr(self, "detail_points_section"):
            self.detail_points_section.setVisible(enabled)
        if hasattr(self, "roster_points_section"):
            self.roster_points_section.setVisible(enabled)
        eternal = mode == POINT_MODE_ETERNAL
        if hasattr(self, "detail_points_title"):
            title = tr("raid_clm_admin.eternal_dkp") if eternal else tr("raid_points.title")
            self.detail_points_title.setText(title)
            self.roster_points_title.setText(title)
            for form, character_label, player_label in (
                (self.detail_points_form, self.detail_character_points, self.detail_player_points),
                (self.roster_points_form, self.roster_character_points, self.roster_player_points),
            ):
                form_label = form.labelForField(character_label)
                if form_label is not None:
                    form_label.setText(tr(
                        "raid_clm_admin.eternal_character"
                        if eternal else "raid_points.character_points",
                    ))
                form_label = form.labelForField(player_label)
                if form_label is not None:
                    form_label.setText(tr(
                        "raid_clm_admin.eternal_player"
                        if eternal else "raid_points.player_total",
                    ))
            self.detail_points_form.setRowVisible(self.detail_current_dkp, eternal)
            self.roster_points_form.setRowVisible(self.roster_current_dkp, eternal)
            self.detail_character_history.setVisible(not eternal)
            self.roster_character_history.setVisible(not eternal)
            self.detail_player_history.setVisible(not eternal)
            self.roster_player_history.setVisible(not eternal)
        if hasattr(self, "detail_dkp_section"):
            self.detail_dkp_section.setVisible(False)
            self.roster_dkp_section.setVisible(False)

    def _populate_point_history_subjects(self, *, force: bool = True) -> None:
        if not hasattr(self, "point_history_subject"):
            return
        if not force and not self._raid_view_dirty["history"]:
            return
        current = self.point_history_subject.currentData()
        mode = str(self.point_history_mode.currentData() or "player")
        entries = self._point_entries()
        options: list[tuple[str, str]] = []
        if mode == "player":
            players = {player.playerId: player for player in self.model.players}
            player_ids = {
                member.playerId for member in self.model.members
                if member.playerId
                and member.characterType == "main"
                and member.lifeStatus == "active"
            }
            options = [
                (
                    players[player_id].playerName if player_id in players else player_id,
                    player_id,
                )
                for player_id in player_ids
            ]
        else:
            names = {entry.member_id: entry.character_name for entry in entries}
            names.update({member.id: member.name for member in self.model.members})
            options = [(names[member_id], member_id) for member_id in names if member_id]
        options.sort(key=lambda item: (item[0].casefold(), item[1]))
        self.point_history_subject.blockSignals(True)
        self.point_history_subject.clear()
        for label, identifier in options:
            self.point_history_subject.addItem(label, identifier)
        index = self.point_history_subject.findData(current)
        if index >= 0:
            self.point_history_subject.setCurrentIndex(index)
        self.point_history_subject.blockSignals(False)
        self.refresh_point_history(force=force)

    def _matrix_subject_options(self, mode: str) -> list[tuple[str, str]]:
        if mode == "player":
            players = {player.playerId: player for player in self.model.players}
            player_ids = {
                member.playerId for member in self.model.members
                if member.playerId and member.characterType == "main"
            }
            options = [
                (players[player_id].playerName, player_id)
                for player_id in player_ids if player_id in players
            ]
        else:
            options = [
                (member.name, member.id)
                for member in self.model.members
                if member.lifeStatus == "active"
            ]
        return sorted(options, key=lambda item: (item[0].casefold(), item[1]))

    def _populate_matrix_subjects(self, *, reset: bool = False) -> None:
        if not hasattr(self, "matrix_subject"):
            return
        current = "" if reset else str(self.matrix_subject.currentData() or "")
        mode = self._raid_view_mode("matrix")
        self.matrix_subject.blockSignals(True)
        self.matrix_subject.clear()
        self.matrix_subject.addItem(tr("common.all"), "")
        for label, identifier in self._matrix_subject_options(mode):
            self.matrix_subject.addItem(label, identifier)
        index = self.matrix_subject.findData(current)
        self.matrix_subject.setCurrentIndex(index if index >= 0 else 0)
        self.matrix_subject.blockSignals(False)

    def _matrix_view_mode_changed(self) -> None:
        mode = self._raid_view_mode("matrix")
        self.matrix_subject_label.setText(
            tr("raids.player_filter") if mode == "player" else tr("raids.character_filter")
        )
        self.matrix_player_search.setPlaceholderText(
            tr("raids.player_search") if mode == "player" else tr("raids.character_search")
        )
        self.matrix_active_only.setText(
            tr("raids.active_only") if mode == "player" else tr("raids.active_characters_only")
        )
        # A filter from the other view must never remain active invisibly.
        self._populate_matrix_subjects(reset=True)
        self._refresh_attendance_combined()

    def _refresh_attendance_combined(self) -> None:
        self.refresh_raid_matrix()

    def _toggle_attendance_matrix(self, collapsed: bool) -> None:
        sizes = self.attendance_matrix_split.sizes()
        if collapsed:
            if len(sizes) > 1 and sizes[1] > 0:
                self._attendance_matrix_last_width = sizes[1]
            self.attendance_matrix_split.setSizes([max(sum(sizes), 1), 0])
            self.matrix_toggle_button.setText(tr("raids.matrix_show"))
        else:
            total = max(sum(sizes), 1200)
            right = min(max(self._attendance_matrix_last_width, 480), max(total - 620, 480))
            self.attendance_matrix_split.setSizes([max(total - right, 620), right])
            self.matrix_toggle_button.setText(tr("raids.matrix_hide"))


    def refresh_point_history(self, *, force: bool = True) -> None:
        if not hasattr(self, "point_history_table"):
            return
        if not force and not self._raid_view_dirty["history"]:
            return
        mode = str(self.point_history_mode.currentData() or "player")
        subject_id = str(self.point_history_subject.currentData() or "")
        entries = [
            entry for entry in self._point_entries()
            if subject_id and (
                entry.player_id == subject_id if mode == "player"
                else entry.member_id == subject_id
            )
        ]
        entries.sort(key=lambda entry: (entry.date, entry.raid_id), reverse=True)
        self.point_history_table.setColumnHidden(2, mode != "player")
        self.point_history_table.setUpdatesEnabled(False)
        try:
            self.point_history_table.setRowCount(len(entries))
            for row, entry in enumerate(entries):
                values = (
                    entry.date, entry.raid_name, entry.character_name,
                    tr(f"raids.attendance_status_{entry.attendance_status}"),
                    entry.base_points,
                    f"{entry.adjustment:+d}" if entry.adjustment else "0",
                    entry.reason or "–", entry.total_points,
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setData(Qt.ItemDataRole.UserRole, entry.raid_id)
                    self.point_history_table.setItem(row, column, item)
        finally:
            self.point_history_table.setUpdatesEnabled(True)
        self._raid_view_dirty["history"] = False

    def _open_history_raid(self, row: int) -> None:
        item = self.point_history_table.item(row, 0)
        raid_id = str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""
        if not raid_id:
            return
        self.raid_subtabs.setCurrentIndex(0)
        for raid_row in range(self.raid_table.rowCount()):
            raid_item = self.raid_table.item(raid_row, 0)
            if raid_item and raid_item.data(Qt.ItemDataRole.UserRole) == raid_id:
                self.raid_table.selectRow(raid_row)
                self.raid_table.scrollToItem(raid_item)
                return

    def open_point_history_for_member(self, member_id: str) -> None:
        if not self.model.raid_points.enabled or not member_id:
            return
        self.switch_page("raid")
        index = self.point_history_mode.findData("character")
        self.point_history_mode.setCurrentIndex(index)
        self._populate_point_history_subjects()
        subject = self.point_history_subject.findData(member_id)
        if subject >= 0:
            self.point_history_subject.setCurrentIndex(subject)
        self.raid_subtabs.setCurrentWidget(self.point_history_page)

    def open_point_history_for_player(self, player_id: str) -> None:
        if not self.model.raid_points.enabled or not player_id:
            return
        self.switch_page("raid")
        index = self.point_history_mode.findData("player")
        self.point_history_mode.setCurrentIndex(index)
        self._populate_point_history_subjects()
        subject = self.point_history_subject.findData(player_id)
        if subject >= 0:
            self.point_history_subject.setCurrentIndex(subject)
        self.raid_subtabs.setCurrentWidget(self.point_history_page)

    def _invalidate_raid_views(self) -> None:
        """Keep expensive raid views lazy until their tab is actually visible."""
        self._raid_view_dirty.update({
            "raids": True, "attendance": True, "matrix": True, "history": True,
        })

    def _raid_subtab_changed(self, _index: int) -> None:
        page = self.raid_subtabs.currentWidget()
        if page is self.raids_page:
            self.refresh_raids(force=False)
        elif page is self.attendance_page:
            self.refresh_raid_matrix(force=False)
        elif page is self.point_history_page:
            self._populate_point_history_subjects(force=False)

    def _refresh_current_raid_tab(self) -> None:
        self._raid_subtab_changed(self.raid_subtabs.currentIndex())

    def refresh_raids(self, *, force: bool = True) -> None:
        if not force and not self._raid_view_dirty["raids"]:
            return
        self._sync_points_ui_visibility()
        selected = self._selected_raid()
        selected_id = selected.id if selected else None
        columns = ("date", "type", "name", "participants", "status", "logs")
        sort_column = columns[self._raid_sort_column]
        raid_rows = []
        # Der vorhandene Attendance-Index ersetzt den linearen Scan ueber die
        # gesamte Attendance-Liste pro Raid. Fachlich wird hier ausschliesslich
        # die Teilnehmerzahl verwendet; pro Raid und Spieler existiert genau ein
        # Eintrag (attendance_records() lehnt duplicate_player ab).
        attendance_by_raid = self.model.attendance_lookup()
        for raid in self.model.raids:
            attendance = attendance_by_raid.get(raid.id, {})
            status_text = (
                tr("raids.status_recorded") if raid.status == "recorded"
                else tr("raids.status_draft")
            )
            raid_rows.append((raid, attendance, status_text))
        raid_rows.sort(
            key=lambda row: (
                raid_table_sort_value(row[0], sort_column, len(row[1]), row[2]), row[0].id,
            ),
            reverse=not self._raid_sort_ascending,
        )
        self.raid_table.setUpdatesEnabled(False)
        self.raid_table.blockSignals(True)
        try:
            self.raid_table.setRowCount(len(raid_rows))
            for row, (raid, attendance, status_text) in enumerate(raid_rows):
                values = (
                    raid.date,
                    raid.raidType or "–",
                    raid.name,
                    str(len(attendance)),
                    status_text,
                    "Link" if raid.warcraftLogsUrl else "–",
                )
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if col == 0:
                        item.setData(Qt.ItemDataRole.UserRole, raid.id)
                    if col == 5 and raid.warcraftLogsUrl:
                        item.setToolTip(raid.warcraftLogsUrl)
                        item.setForeground(QColor("#7fb7ff"))
                    self.raid_table.setItem(row, col, item)
                if raid.id == selected_id:
                    self.raid_table.selectRow(row)
            if self.raid_table.rowCount() and not self.raid_table.selectionModel().hasSelection():
                self.raid_table.selectRow(0)
        finally:
            self.raid_table.blockSignals(False)
            self.raid_table.setUpdatesEnabled(True)
        self._raid_view_dirty["raids"] = False
        self.refresh_raid_participants()

    def _raid_table_sort_clicked(self, column: int) -> None:
        if column == self._raid_sort_column:
            self._raid_sort_ascending = not self._raid_sort_ascending
        else:
            self._raid_sort_column = column
            self._raid_sort_ascending = True
        self.raid_table.horizontalHeader().setSortIndicator(
            column,
            Qt.SortOrder.AscendingOrder if self._raid_sort_ascending
            else Qt.SortOrder.DescendingOrder,
        )
        self.refresh_raids()

    def refresh_raid_participants(self) -> None:
        if not hasattr(self, "raid_participants_table"):
            return
        raid = self._selected_raid()
        entries = sorted(
            self.model.attendance_for_raid(raid.id) if raid else [],
            key=lambda entry: (entry.playerNameSnapshot.casefold(), entry.characterNameSnapshot.casefold()),
        )
        self.raid_participants_table.setSortingEnabled(False)
        point_mode = self.model.active_point_mode()
        points_enabled = point_mode == POINT_MODE_RAID
        eternal_enabled = point_mode == POINT_MODE_ETERNAL
        self.raid_participants_table.setColumnCount(
            7 if points_enabled else 6 if eternal_enabled else 4
        )
        headers = [
            tr("raids.player"), tr("raids.character"), tr("raids.type"), tr("common.status"),
        ]
        if points_enabled:
            headers.extend((
                tr("raid_points.base"), tr("raid_points.adjustment"), tr("raid_points.total"),
            ))
        elif eternal_enabled:
            headers.extend((
                tr("raid_clm_admin.eternal_dkp"), tr("raid_clm_admin.bench_share"),
            ))
        self.raid_participants_table.setHorizontalHeaderLabels(headers)
        point_entries = {entry.attendance_id: entry for entry in self._point_entries()}
        members_by_id = {member.id: member for member in self.model.members}
        eternal_records_by_member: dict[str, list[object]] = {}
        if eternal_enabled and raid is not None:
            for record in self.model.eternal_dkp.records:
                if record.raid_id == raid.id:
                    eternal_records_by_member.setdefault(record.member_id, []).append(record)
        self.raid_participants_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            character = members_by_id.get(entry.memberId)
            point_entry = point_entries.get(entry.id)
            values = [
                entry.playerNameSnapshot,
                entry.characterNameSnapshot,
                tr(f"raids.attendance_type_{entry.attendanceType}"),
                tr(f"raids.attendance_status_{entry.status}"),
            ]
            if points_enabled:
                values.extend((
                    point_entry.base_points if point_entry else base_points_for_status(entry.status),
                    (f"{point_entry.adjustment:+d}" if point_entry and point_entry.adjustment else "0"),
                    point_entry.total_points if point_entry else base_points_for_status(entry.status),
                ))
            elif eternal_enabled:
                records = eternal_records_by_member.get(entry.memberId, ())
                total = sum(float(record.value) for record in records)
                bench = sum(
                    float(record.value) for record in records
                    if record.kind in {"EARNED_BENCH", "CORRECTION"}
                )
                values.extend((f"{total:g}", f"{bench:g}"))
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column >= 4:
                    try:
                        item.setData(Qt.ItemDataRole.DisplayRole, float(str(value).replace("+", "")))
                    except ValueError:
                        pass
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, entry.playerId)
                elif column == 1:
                    self._apply_character_presentation(item, character)
                elif column == 3 and entry.status == "bench":
                    item.setBackground(QColor("#6d5418"))
                    item.setForeground(QColor("#ffffff"))
                self.raid_participants_table.setItem(row, column, item)
        self.raid_participants_table.setSortingEnabled(True)
        self.raid_toggle_bench_button.setEnabled(bool(entries))
        self.raid_points_button.setEnabled(bool(entries))

    @staticmethod
    def _apply_character_presentation(item: QTableWidgetItem, member) -> None:
        """Apply the existing class icon and colour to a character-name item."""
        if member is None or not member.className:
            return
        icon_path = class_icon_path(member.className)
        if icon_path.is_file():
            item.setIcon(QIcon(str(icon_path)))

    def _sync_matrix_vertical_scroll(self, target: QTableWidget, value: int) -> None:
        if self._matrix_syncing_scroll:
            return
        self._matrix_syncing_scroll = True
        try:
            target.verticalScrollBar().setValue(value)
        finally:
            self._matrix_syncing_scroll = False

    def toggle_selected_attendance_status(self) -> None:
        raid = self._selected_raid()
        rows = self.raid_participants_table.selectionModel().selectedRows()
        if raid is None or not rows:
            return
        if self.model.raid_points.enabled and not self._ensure_raid_point_scope():
            return
        item = self.raid_participants_table.item(rows[0].row(), 0)
        player_id = str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""
        entry = self.model.attendance_lookup().get(raid.id, {}).get(player_id)
        if entry is None:
            return
        self.model.set_raid_attendance_status(
            raid.id, player_id, "present" if entry.status == "bench" else "bench",
        )
        self.autosave()
        if not self._rebuild_raid_derived_state():
            return
        self.refresh_raid_participants()

    def _player_main_member(self, player_id: str):
        """Return a read-only display character without creating a Main assignment."""
        return self._preferred_player_member(
            member for member in self.model.members if member.playerId == player_id
        )

    @staticmethod
    def _preferred_player_member(members: Iterable[Member]):
        members = list(members)
        for life_status in ("active", "inactive", "dead"):
            current = [member for member in members if member.lifeStatus == life_status]
            if not current:
                continue
            mains = [member for member in current if member.characterType == "main"]
            pool = mains or current
            return max(pool, key=lambda member: (
                member.deathDate or "", member.addedDate or "", member.id,
            ))
        return None

    def _player_is_active(self, player_id: str) -> bool:
        return self.model.player_is_active(player_id)

    def _raid_view_mode(self, prefix: str) -> str:
        if prefix == "matrix" and hasattr(self, "matrix_view_group"):
            button = self.matrix_view_group.checkedButton()
            return str(button.property("viewMode") or "player") if button is not None else "player"
        control = getattr(self, f"{prefix}_view_mode", None)
        return str(control.currentData() or "player") if control is not None else "player"

    def _member_attendance_statistics(self, member: Member, *, start: str = "",
                                      end: str = "", category: str = "",
                                      raid_type: str = "", raids: Iterable | None = None,
                                      player_by_id: dict[str, object] | None = None,
                                      eligible_raid_ids: Iterable[str] | None = None):
        player = (
            player_by_id.get(member.playerId) if player_by_id is not None and member.playerId
            else self.model.find_player_by_id(member.playerId) if member.playerId else None
        )
        return calculate_statistics(
            member.playerId or "", raids if raids is not None else self.model.raids,
            self.model.raid_attendance,
            self.model.attendance_tracking_start_date,
            player.membershipStartDate if player is not None else None,
            player.membershipEndDate if player is not None else None,
            start_date=start, end_date=end, category=category, raid_type=raid_type,
            member_id=member.id,
            eligible_raid_ids=eligible_raid_ids,
        )

    def _raid_filter_values(self, prefix: str) -> tuple[str, str, str, str, bool]:
        return (
            getattr(self, f"{prefix}_date_from").text().strip(),
            getattr(self, f"{prefix}_date_to").text().strip(),
            str(getattr(self, f"{prefix}_category_filter").currentData() or ""),
            str(getattr(self, f"{prefix}_type_filter").currentData() or ""),
            getattr(self, f"{prefix}_active_only").isChecked(),
        )

    def _scoped_raids(self, prefix: str) -> list:
        start, end, category, raid_type, _active_only = self._raid_filter_values(prefix)
        raids = [
            raid for raid in self.model.raids
            if raid.status == "recorded"
            and (not start or raid.date >= start)
            and (not end or raid.date <= end)
            and (not category or raid.category == category)
            and (not raid_type or raid.raidType == raid_type)
        ]
        raids.sort(key=lambda raid: (raid.date, raid.name.casefold()), reverse=True)
        if prefix == "matrix":
            limit = int(self.matrix_raid_limit.currentData() or 0)
            if limit:
                raids = raids[:limit]
        return raids

    def refresh_raid_statistics(self, *, force: bool = True) -> None:
        # Compatibility entry point: attendance and matrix now share one table/data scope.
        self.refresh_raid_matrix(force=force)

    def _queue_attendance_refresh(self) -> None:
        if self._attendance_refresh_pending:
            return
        self._attendance_refresh_pending = True
        QTimer.singleShot(0, self._run_queued_attendance_refresh)

    def _run_queued_attendance_refresh(self) -> None:
        self._attendance_refresh_pending = False
        self.refresh_raid_matrix()

    def _queue_attendance_sort(self) -> None:
        if self._attendance_sort_pending:
            return
        self._attendance_sort_pending = True
        QTimer.singleShot(0, self._run_queued_attendance_sort)

    def _run_queued_attendance_sort(self) -> None:
        self._attendance_sort_pending = False
        if not self._matrix_players:
            self._queue_attendance_refresh()
            return
        previous_rows = self._matrix_players
        sorted_rows = self._sort_attendance_rows(previous_rows)
        self._reorder_attendance_matrix_rows(previous_rows, sorted_rows)
        self._matrix_players = sorted_rows

    def _matrix_sort_dropdown_changed(self, _index: int) -> None:
        key = str(self.matrix_sort.currentData() or "name")
        if key != self._matrix_sort_key:
            self._matrix_sort_key = key
            self._matrix_sort_ascending = True
        self._matrix_last_header_column = None
        self._queue_attendance_sort()

    def _matrix_fixed_column_clicked(self, column: int) -> None:
        key_by_column = {
            0: "name",
            1: "percent",
            2: "present",
            3: "bench",
            4: "eligible",
            5: "main",
            6: "twink",
            7: "current_streak",
            8: "longest_streak",
            9: "last_attendance",
        }
        key = key_by_column.get(column)
        if key is None:
            return
        if column == self._matrix_last_header_column and key == self._matrix_sort_key:
            self._matrix_sort_ascending = not self._matrix_sort_ascending
        else:
            self._matrix_sort_key = key
            self._matrix_sort_ascending = True
        self._matrix_last_header_column = column
        index = self.matrix_sort.findData(key)
        if index >= 0:
            self.matrix_sort.blockSignals(True)
            self.matrix_sort.setCurrentIndex(index)
            self.matrix_sort.blockSignals(False)
        # Moving existing rows must wait until QHeaderView has returned on Windows.
        self._queue_attendance_sort()

    def _sync_matrix_sort_indicator(self) -> None:
        column_by_key = {
            "name": 0,
            "percent": 1,
            "present": 2,
            "bench": 3,
            "eligible": 4,
            "main": 5,
            "twink": 6,
            "current_streak": 7,
            "longest_streak": 8,
            "last_attendance": 9,
        }
        header = self.raid_stats_table.horizontalHeader()
        column = column_by_key.get(self._matrix_sort_key)
        header.setSortIndicatorShown(column is not None)
        if column is not None:
            header.setSortIndicator(
                column,
                Qt.SortOrder.AscendingOrder if self._matrix_sort_ascending
                else Qt.SortOrder.DescendingOrder,
            )

    def _sort_attendance_rows(self, rows: list[dict]) -> list[dict]:
        sort_key = self._matrix_sort_key
        key_functions = {
            "name": lambda row: row["label"].casefold(),
            "percent": lambda row: row["stat"].attendance_percent,
            "present": lambda row: row["stat"].total_attendances,
            "bench": lambda row: row["stat"].bench_attendances,
            "eligible": lambda row: row["stat"].eligible_raids,
            "main": lambda row: row["stat"].main_attendances,
            "twink": lambda row: row["stat"].twink_attendances,
            "current_streak": lambda row: row["stat"].current_streak,
            "longest_streak": lambda row: row["stat"].longest_streak,
            "last_attendance": lambda row: row["stat"].last_attendance or "",
        }
        return sorted(
            rows,
            key=lambda row: (key_functions[sort_key](row), row["label"].casefold()),
            reverse=not self._matrix_sort_ascending,
        )

    def _reorder_attendance_matrix_rows(
            self, previous_rows: list[dict], sorted_rows: list[dict],
    ) -> None:
        """Reorder existing table items without recalculating statistics or cells."""
        stats_table = self.raid_stats_table
        matrix_table = self.raid_matrix_table
        current = stats_table.currentItem()
        selected_item = stats_table.item(current.row(), 0) if current is not None else None
        selected_id = str(
            selected_item.data(Qt.ItemDataRole.UserRole) or ""
        ) if selected_item is not None else ""
        stats_scroll_x = stats_table.horizontalScrollBar().value()
        matrix_scroll_x = matrix_table.horizontalScrollBar().value()
        scroll_y = stats_table.verticalScrollBar().value()
        stats_rows: dict[str, list[QTableWidgetItem | None]] = {}
        matrix_rows: dict[str, list[QTableWidgetItem | None]] = {}
        stats_table.setUpdatesEnabled(False)
        matrix_table.setUpdatesEnabled(False)
        stats_table.blockSignals(True)
        matrix_table.blockSignals(True)
        try:
            for row, info in enumerate(previous_rows):
                # Capture uses the pre-sort identity order; items stay intact via takeItem.
                identifier = str(info["identifier"])
                stats_rows[identifier] = [
                    stats_table.takeItem(row, column)
                    for column in range(stats_table.columnCount())
                ]
                matrix_rows[identifier] = [
                    matrix_table.takeItem(row, column)
                    for column in range(matrix_table.columnCount())
                ]
            stats_table.setRowCount(len(sorted_rows))
            matrix_table.setRowCount(len(sorted_rows))
            for row, info in enumerate(sorted_rows):
                identifier = str(info["identifier"])
                for column, item in enumerate(stats_rows[identifier]):
                    if item is not None:
                        stats_table.setItem(row, column, item)
                for column, item in enumerate(matrix_rows[identifier]):
                    if item is not None:
                        matrix_table.setItem(row, column, item)
                stats_table.setRowHeight(row, RAID_MATRIX_ROW_HEIGHT)
                matrix_table.setRowHeight(row, RAID_MATRIX_ROW_HEIGHT)
                if identifier == selected_id:
                    stats_table.selectRow(row)
        finally:
            stats_table.blockSignals(False)
            matrix_table.blockSignals(False)
            stats_table.setUpdatesEnabled(True)
            matrix_table.setUpdatesEnabled(True)
        stats_table.horizontalScrollBar().setValue(stats_scroll_x)
        matrix_table.horizontalScrollBar().setValue(matrix_scroll_x)
        stats_table.verticalScrollBar().setValue(scroll_y)
        matrix_table.verticalScrollBar().setValue(scroll_y)
        self._sync_matrix_sort_indicator()


    def _attendance_rows_for_scope(self, raids: list) -> list[dict]:
        _start, _end, _category, _raid_type, _active_only = self._raid_filter_values("matrix")
        query = self.matrix_player_search.text().strip().casefold()
        view_mode = self._raid_view_mode("matrix")
        subject_id = str(self.matrix_subject.currentData() or "")
        player_by_id = {player.playerId: player for player in self.model.players}
        members_by_player: dict[str, list[Member]] = {}
        for member in self.model.members:
            if member.playerId:
                members_by_player.setdefault(member.playerId, []).append(member)
        main_by_player = {
            player_id: display_member
            for player_id, members in members_by_player.items()
            if (display_member := self._preferred_player_member(members)) is not None
        }

        rows: list[dict] = []
        if view_mode == "player":
            for player in self.model.players:
                main = main_by_player.get(player.playerId)
                if main is None or main.lifeStatus != "active":
                    continue
                player_members = members_by_player.get(player.playerId, ())
                character_names = [member.name for member in player_members]
                if subject_id and player.playerId != subject_id:
                    continue
                if query and (
                    query not in player.playerName.casefold()
                    and not any(query in name.casefold() for name in character_names)
                ):
                    continue
                relevant_raid_ids = {
                    raid.id for raid in raids
                    if player_is_relevant(
                        raid, self.model.attendance_tracking_start_date,
                        player.membershipStartDate, player.membershipEndDate,
                    )
                }
                try:
                    stat = calculate_statistics(
                        player.playerId, raids, self.model.raid_attendance,
                        self.model.attendance_tracking_start_date,
                        player.membershipStartDate, player.membershipEndDate,
                        eligible_raid_ids=relevant_raid_ids,
                    )
                except Exception:
                    continue
                if stat.total_attendances <= 0:
                    continue
                rows.append({
                    "identifier": player.playerId,
                    "label": main.name,
                    "stat": stat,
                    "member": main,
                    "player": player,
                    "relevant_raid_ids": relevant_raid_ids,
                })
        else:
            for member in self.model.members:
                if member.lifeStatus != "active":
                    continue
                if subject_id and member.id != subject_id:
                    continue
                if query and query not in member.name.casefold():
                    continue
                player = player_by_id.get(member.playerId) if member.playerId else None
                relevant_raid_ids = {
                    raid.id for raid in raids
                    if player_is_relevant(
                        raid, self.model.attendance_tracking_start_date,
                        player.membershipStartDate if player is not None else None,
                        player.membershipEndDate if player is not None else None,
                    )
                }
                try:
                    stat = self._member_attendance_statistics(
                        member,
                        raids=raids,
                        player_by_id=player_by_id,
                        eligible_raid_ids=relevant_raid_ids,
                    )
                except Exception:
                    continue
                if stat.total_attendances <= 0:
                    continue
                rows.append({
                    "identifier": member.id,
                    "label": member.name,
                    "stat": stat,
                    "member": member,
                    "player": player,
                    "relevant_raid_ids": relevant_raid_ids,
                })

        return self._sort_attendance_rows(rows)

    def refresh_raid_matrix(self, *, force: bool = True) -> None:
        if not hasattr(self, "raid_stats_table") or not hasattr(self, "raid_matrix_table"):
            return
        if not force and not (
            self._raid_view_dirty["matrix"] or self._raid_view_dirty["attendance"]
        ):
            return

        raids = self._scoped_raids("matrix")
        rows = self._attendance_rows_for_scope(raids)
        self._matrix_raids = raids
        self._matrix_players = rows
        view_mode = self._raid_view_mode("matrix")

        fixed_headers = [
            tr("raids.player") if view_mode == "player" else tr("common.character"),
            tr("raids.attendance_percent"),
            tr("raids.present"),
            tr("raids.bench"),
            tr("raids.relevant_raids"),
            tr("raids.main_count"),
            tr("raids.twink_count"),
            tr("raids.current_streak"),
            tr("raids.longest_streak"),
            tr("raids.last_attendance"),
        ]
        raid_headers = [
            f"{raid.raidType or '–'}\n{raid.date[5:]}{' · ↗' if raid.warcraftLogsUrl else ''}"
            for raid in raids
        ]

        stats_table = self.raid_stats_table
        matrix_table = self.raid_matrix_table
        stats_header = stats_table.horizontalHeader()
        matrix_header = matrix_table.horizontalHeader()

        stats_table.setUpdatesEnabled(False)
        matrix_table.setUpdatesEnabled(False)
        stats_table.blockSignals(True)
        matrix_table.blockSignals(True)
        stats_header.blockSignals(True)
        matrix_header.blockSignals(True)
        try:
            stats_table.setRowCount(len(rows))
            stats_table.setColumnCount(RAID_ATTENDANCE_FIXED_COLUMNS)
            stats_table.setHorizontalHeaderLabels(fixed_headers)
            stats_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
            for column in range(1, RAID_ATTENDANCE_FIXED_COLUMNS):
                stats_header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

            matrix_table.setRowCount(len(rows))
            matrix_table.setColumnCount(len(raids))
            matrix_table.setHorizontalHeaderLabels(raid_headers)
            matrix_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            for column in range(len(raids)):
                matrix_table.setColumnWidth(column, 74)

            lookup = self.model.attendance_lookup()
            member_lookup = {
                (entry.raidId, entry.memberId): entry
                for entry in self.model.raid_attendance
            }
            for row, info in enumerate(rows):
                player = info["player"]
                member = info["member"]
                stat = info["stat"]
                values = (
                    info["label"],
                    stat.attendance_percent,
                    stat.total_attendances,
                    stat.bench_attendances,
                    stat.eligible_raids,
                    stat.main_attendances,
                    stat.twink_attendances,
                    stat.current_streak,
                    stat.longest_streak,
                    stat.last_attendance or "–",
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem()
                    item.setData(Qt.ItemDataRole.DisplayRole, value)
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, info["identifier"])
                        self._apply_character_presentation(item, member)
                    stats_table.setItem(row, column, item)

                stats_table.setRowHeight(row, RAID_MATRIX_ROW_HEIGHT)
                matrix_table.setRowHeight(row, RAID_MATRIX_ROW_HEIGHT)
                for column, raid in enumerate(raids):
                    relevant = raid.id in info["relevant_raid_ids"]
                    entry = (
                        lookup.get(raid.id, {}).get(player.playerId)
                        if view_mode == "player" and player is not None
                        else member_lookup.get((raid.id, member.id)) if member is not None else None
                    )
                    if not relevant:
                        text_value, color, tooltip = "–", QColor("#59616a"), tr("raids.not_relevant")
                    elif entry is None:
                        text_value, color, tooltip = "", QColor("#11161d"), tr("raids.absent")
                    elif entry.status == "bench":
                        text_value, color, tooltip = (
                            tr("raids.bench_short"), QColor("#b18420"),
                            tr("raids.attendance_status_bench"),
                        )
                    else:
                        text_value, color, tooltip = (
                            "✓", QColor("#248447"), tr("raids.attendance_status_present"),
                        )
                    item = QTableWidgetItem(text_value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setBackground(color)
                    item.setData(RAID_MATRIX_BACKGROUND_ROLE, color.name())
                    item.setForeground(QColor("#ffffff"))
                    item.setToolTip(tooltip)
                    matrix_table.setItem(row, column, item)
        finally:
            stats_header.blockSignals(False)
            matrix_header.blockSignals(False)
            stats_table.blockSignals(False)
            matrix_table.blockSignals(False)
            stats_table.setUpdatesEnabled(True)
            matrix_table.setUpdatesEnabled(True)

        self._sync_matrix_sort_indicator()
        self._raid_view_dirty["attendance"] = False
        self._raid_view_dirty["matrix"] = False


    def _attendance_table_header_clicked(self, column: int) -> None:
        self._matrix_fixed_column_clicked(column)

    def _attendance_table_cell_clicked(self, row: int, column: int) -> None:
        if column != 0:
            return
        item = self.raid_stats_table.item(row, 0)
        identifier = str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""
        index = self.matrix_subject.findData(identifier)
        if index >= 0:
            self.matrix_subject.setCurrentIndex(index)

    def _matrix_raid_clicked(self, column: int) -> None:
        if not (0 <= column < len(getattr(self, "_matrix_raids", []))):
            return
        raid = self._matrix_raids[column]
        self.raid_subtabs.setCurrentIndex(0)
        for row in range(self.raid_table.rowCount()):
            item = self.raid_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == raid.id:
                self.raid_table.selectRow(row)
                self.raid_table.scrollToItem(item)
                break

    def _matrix_cell_clicked(self, row: int, column: int) -> None:
        if not (0 <= row < len(getattr(self, "_matrix_players", []))
                and 0 <= column < len(getattr(self, "_matrix_raids", []))):
            return
        info = self._matrix_players[row]
        player = info["player"]
        member = info["member"]
        view_mode = self._raid_view_mode("matrix")
        raid = self._matrix_raids[column]
        entry = (
            self.model.attendance_lookup().get(raid.id, {}).get(player.playerId)
            if view_mode == "player" and player is not None
            else next((
                value for value in self.model.attendance_for_raid(raid.id)
                if member is not None and value.memberId == member.id
            ), None)
        )
        status = tr("raids.not_relevant")
        character = "–"
        attendance_type = "–"
        relevant = player_is_relevant(
            raid, self.model.attendance_tracking_start_date,
            player.membershipStartDate if player is not None else None,
            player.membershipEndDate if player is not None else None,
        )
        if relevant and entry is None:
            status = tr("raids.absent")
        elif entry is not None:
            status = tr(f"raids.attendance_status_{entry.status}")
            character = entry.characterNameSnapshot
            attendance_type = tr(f"raids.attendance_type_{entry.attendanceType}")
        QMessageBox.information(
            self, tr("raids.matrix_detail_title"),
            tr(
                "raids.matrix_detail", raid=raid.raidType or raid.name, date=raid.date,
                player=player.playerName if player is not None else info["label"],
                character=character, status=status,
                attendance_type=attendance_type,
            ),
        )

    def create_raid_dialog(self) -> None:
        dialog = RaidEditorDialog(self, model=self.model)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            raid, summary = self.model.create_raid_with_attendance(*dialog.creation_values())
            self.autosave()
            if not self._rebuild_raid_derived_state():
                self.refresh_raids()
            if dialog.adjust_points_after_save:
                self._adjust_raid_points(raid)
            QMessageBox.information(
                self, tr("raids.import_complete_title"),
                tr(
                    "raids.created_with_attendance", name=raid.name,
                    participants=summary["participants"], bench=summary["bench"],
                ),
            )
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, raid_error_text(exc))

    def bulk_import_raid_csvs(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("raids.bulk_select_folder"))
        if not folder:
            return
        dialog = BulkRaidImportDialog(
            self, self.model, Path(folder), self._suite_settings_path,
        )
        dialog.exec()
        result = dialog.result_value
        if result is None or result.imported <= 0:
            return
        self.autosave()
        if not self._rebuild_raid_derived_state():
            self.refresh_raids()
        self.set_status(tr(
            "raids.bulk_result_summary", imported=result.imported,
            skipped=result.skipped, failed=result.failed,
        ))

    def edit_selected_raid(self) -> None:
        raid = self._selected_raid()
        if raid is None:
            QMessageBox.information(self, APP_NAME, tr("raids.select_first"))
            return
        dialog = RaidEditorDialog(self, raid=raid, model=self.model)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.model.update_raid(raid.id, *dialog.values())
            self.model.set_raid_bench_players(raid.id, dialog.bench_values())
            self.autosave()
            if not self._rebuild_raid_derived_state():
                self.refresh_raids()
            if dialog.adjust_points_after_save:
                self._adjust_raid_points(raid)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, raid_error_text(exc))

    def adjust_selected_raid_points(self) -> None:
        raid = self._selected_raid()
        if raid is None:
            QMessageBox.information(self, APP_NAME, tr("raids.select_first"))
            return
        self._adjust_raid_points(raid)

    def _adjust_raid_points(self, raid) -> None:
        if not self.model.raid_points.enabled:
            return
        if not self._ensure_raid_point_scope():
            return
        entries = self.model.attendance_for_raid(raid.id)
        if not entries:
            QMessageBox.information(self, APP_NAME, tr("raid_points.no_entries"))
            return
        dialog = RaidPointAdjustmentDialog(self, self.model, raid)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            for attendance_id, value, reason in dialog.adjustment_values():
                self.model.set_raid_point_adjustment(attendance_id, value, reason)
            self.autosave()
            if not self._rebuild_raid_derived_state():
                return
            self.refresh_raid_participants()
            self.set_status(tr("raid_points.adjustments_saved", raid=raid.name))
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))

    def delete_selected_raid(self) -> None:
        raid = self._selected_raid()
        if raid is None:
            QMessageBox.information(self, APP_NAME, tr("raids.select_first"))
            return
        answer = QMessageBox.question(
            self, tr("raids.delete"), tr("raids.delete_question", name=raid.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.model.delete_raid(raid.id)
        self.autosave()
        if not self._rebuild_raid_derived_state():
            self.refresh_raids()

    def reset_selected_raid_attendance(self) -> None:
        raid = self._selected_raid()
        if raid is None:
            QMessageBox.information(self, APP_NAME, tr("raids.select_first"))
            return
        entries = self.model.attendance_for_raid(raid.id)
        if not entries:
            return
        answer = QMessageBox.question(
            self, tr("raids.reset_attendance"),
            tr("raids.reset_question", name=raid.name, date=raid.date, participants=len(entries)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.model.reset_raid_attendance(raid.id)
        self.autosave()
        if not self._rebuild_raid_derived_state():
            self.refresh_raids()

    # ---------- administration / settings ----------
    def _sync_admin_controls(self) -> None:
        if hasattr(self, "guild_name_edit"):
            self.guild_name_edit.setText(self.model.guild_name)
            self.guild_realm_edit.setText(self.model.realm)
        if hasattr(self, "points_enabled_check"):
            active_mode = self.model.active_point_mode()
            for checkbox, checked in (
                (self.points_enabled_check, active_mode == POINT_MODE_RAID),
                (self.dkp_enabled_check, active_mode == POINT_MODE_ETERNAL),
            ):
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)
        if hasattr(self, "raid_scope_all"):
            state = self.model.raid_points
            self.raid_scope_all.blockSignals(True)
            self.raid_scope_from.blockSignals(True)
            self.raid_scope_all.setChecked(state.calculation_mode != "from_date")
            self.raid_scope_from.setChecked(state.calculation_mode == "from_date")
            self.raid_scope_start.setText(state.calculation_start_date or "")
            self.raid_scope_start.setEnabled(state.calculation_mode == "from_date")
            self.raid_scope_all.blockSignals(False)
            self.raid_scope_from.blockSignals(False)
            if self.clm_roster_combo.count() == 0 and self.model.clm_roster_id:
                self.clm_roster_combo.addItem(self.model.clm_roster_id, self.model.clm_roster_id)
            self._update_feature_controls()
        self._sync_points_ui_visibility()
        self._refresh_visible_dkp_details()

    def _update_feature_controls(self, _checked: bool | None = None) -> None:
        if hasattr(self, "clm_group"):
            self.clm_group.setEnabled(self.dkp_enabled_check.isChecked())
        if hasattr(self, "points_group"):
            self.points_group.setVisible(True)

    def save_guild_master_data(self) -> None:
        guild_name = unicodedata.normalize("NFC", self.guild_name_edit.text().strip())
        realm = unicodedata.normalize("NFC", self.guild_realm_edit.text().strip())
        if not realm:
            QMessageBox.warning(self, APP_NAME, tr("raid_clm_admin.realm_required"))
            return
        if (guild_name, realm) != (self.model.guild_name, self.model.realm):
            self.model.guild_name = guild_name
            self.model.realm = realm
            self.model.dirty = True
            self.autosave()
        self.refresh_project_label()
        self.set_status(tr("raid_clm_admin.guild_master_data_saved"))

    def choose_clm_path(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            tr("raid_clm_admin.choose_clm_file"),
            self.clm_path_edit.text(),
            "ClassicLootManager.lua (ClassicLootManager.lua);;Lua (*.lua)",
        )
        if not path:
            return
        selected = Path(path)
        if selected.name.casefold() != "classiclootmanager.lua" or not selected.is_file():
            QMessageBox.warning(self, APP_NAME, tr("raid_clm_admin.invalid_clm_file"))
            return
        self.clm_path_edit.setText(str(selected.resolve()))
        self.clm_roster_combo.clear()
        self._suite_settings["clm_saved_variables_path"] = str(selected.resolve())
        update_suite_settings(
            self._suite_settings_path,
            clm_saved_variables_path=str(selected.resolve()),
        )
        self.clm_status_label.setText(tr("raid_clm_admin.clm_path_saved"))

    def refresh_dkp(self) -> None:
        if not self.model.dkp_enabled:
            QMessageBox.information(self, APP_NAME, tr("raid_clm_admin.enable_dkp_first"))
            return
        source = Path(self.clm_path_edit.text().strip())
        if source.name.casefold() != "classiclootmanager.lua" or not source.is_file():
            self.clm_status_label.setText(tr("raid_clm_admin.clm_file_missing"))
            QMessageBox.warning(self, APP_NAME, tr("raid_clm_admin.clm_file_missing"))
            return
        requested_roster_id = self.clm_roster_combo.currentData()
        if requested_roster_id is None and self.model.clm_roster_id:
            requested_roster_id = self.model.clm_roster_id
        try:
            snapshot = self._clm_refresh_service.refresh_for_project(
                source,
                project_guild_name=self.model.guild_name,
                project_realm=self.model.realm,
                requested_roster_id=str(requested_roster_id) if requested_roster_id else None,
            )
        except ClmRosterSelectionRequired as exc:
            self.clm_roster_combo.clear()
            for roster in exc.rosters:
                self.clm_roster_combo.addItem(
                    f"{roster.name} · {roster.roster_id}", roster.roster_id,
                )
            self.clm_status_label.setText(tr("raid_clm_admin.choose_roster_status"))
            return
        except Exception as exc:
            retained = self._clm_refresh_service.cached_snapshot is not None
            self.clm_status_label.setText(tr(
                "raid_clm_admin.clm_refresh_failed",
                error=exc,
                retained=tr("raid_clm_admin.cache_retained") if retained else tr("raid_clm_admin.no_cache"),
            ))
            return
        self.clm_roster_combo.clear()
        self.clm_roster_combo.addItem(
            f"{snapshot.roster_name} · {snapshot.roster_id}", snapshot.roster_id,
        )
        matching = match_characters(snapshot.balances, self.model.members)
        self._clm_dkp_by_member_id = {
            match.member_id: match.points for match in matching.matches
        }
        self._refresh_visible_dkp_details()
        if self.model.clm_roster_id != snapshot.roster_id:
            self.model.clm_roster_id = snapshot.roster_id
            self.model.dirty = True
            self.autosave()
        modified = (
            datetime.fromtimestamp(snapshot.source_modified_at).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            if snapshot.source_modified_at is not None else "–"
        )
        refreshed = snapshot.refreshed_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        self.clm_status_label.setText(tr(
            "raid_clm_admin.clm_refresh_ok",
            guild=snapshot.guild_name,
            realm=snapshot.realm,
            roster=snapshot.roster_name,
            roster_id=snapshot.roster_id,
            count=len(snapshot.balances),
            modified=modified,
            refreshed=refreshed,
        ))

    def sync_clm_raid_history(self) -> None:
        """Replay and persist CLM history only after an explicit preview confirmation."""
        if self.model.active_point_mode() != POINT_MODE_ETERNAL:
            QMessageBox.information(self, APP_NAME, tr("raid_clm_admin.enable_dkp_first"))
            return
        source = Path(self.clm_path_edit.text().strip())
        if source.name.casefold() != "classiclootmanager.lua" or not source.is_file():
            QMessageBox.warning(self, APP_NAME, tr("raid_clm_admin.clm_file_missing"))
            return
        requested_roster_id = self.clm_roster_combo.currentData() or self.model.clm_roster_id or None
        try:
            preview = analyze_clm_raid_history(
                source, guild_name=self.model.guild_name, realm=self.model.realm,
                requested_roster_id=str(requested_roster_id) if requested_roster_id else None,
                members=self.model.members,
                ignored_character_guids=self.model.eternal_dkp.ignored_character_guids,
            )
        except ClmRosterSelectionRequired as exc:
            self.clm_roster_combo.clear()
            for roster in exc.rosters:
                self.clm_roster_combo.addItem(
                    f"{roster.name} · {roster.roster_id}", roster.roster_id,
                )
            self.clm_status_label.setText(tr("raid_clm_admin.choose_roster_status"))
            return
        except Exception as exc:
            QMessageBox.warning(
                self, APP_NAME, tr("raid_clm_admin.history_failed", error=exc),
            )
            return
        if ClmRaidHistoryPreviewDialog(self, self.model, preview).exec() != QDialog.DialogCode.Accepted:
            return
        mains = sorted((
            (member.name, member.id) for member in self.model.members
            if member.lifeStatus == "active" and member.characterType == "main" and member.playerId
        ), key=lambda item: item[0].casefold())
        decisions: dict[str, tuple[str, str | None]] = {}
        for name in preview.ambiguous_names:
            candidate_ids = preview.ambiguous_member_ids.get(character_key(name), ())
            candidates = [
                member for member_id in candidate_ids
                if (member := self.model.find_by_id(member_id)) is not None
            ]
            labels = [
                f"{member.name} · {member.id} · {tr(f'life.{member.lifeStatus}')}"
                for member in candidates
            ]
            selected, accepted = QInputDialog.getItem(
                self, tr("raid_clm_admin.history_assignment_title"),
                tr("raid_clm_admin.history_choose_existing", name=name),
                labels, 0, False,
            )
            if not accepted or selected not in labels:
                return
            decisions[name] = ("existing", candidates[labels.index(selected)].id)
        for name in preview.unknown_names:
            dialog = UnknownRaidMemberDialog(self, name, mains)
            if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_value is None:
                return
            decisions[name] = dialog.result_value
        try:
            result = apply_clm_raid_history(self.model, preview, decisions)
            self._rebuild_raid_derived_state(show_errors=False)
            self.autosave()
            self.refresh_all(select_first=False)
            self.clm_status_label.setText(tr(
                "raid_clm_admin.history_complete", created=result.created_raids,
                enriched=result.enriched_raids, records=result.records,
                combined=result.combined_sessions,
            ))
        except Exception as exc:
            QMessageBox.warning(
                self, APP_NAME, tr("raid_clm_admin.history_failed", error=exc),
            )

    def rebuild_raid_statistics(self) -> None:
        if not self._ensure_raid_point_scope():
            return
        if not self._rebuild_raid_derived_state():
            return
        eternal = self.model.active_point_mode() == POINT_MODE_ETERNAL
        self.points_status_label.setText(tr(
            "raid_clm_admin.raid_statistics_rebuilt_eternal"
            if eternal else "raid_clm_admin.raid_statistics_rebuilt",
            players=len(self.model.players),
            points=(len(self.model.eternal_dkp.records) if eternal else len(self._point_entries())),
            refreshed=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        ))

    def rebuild_raid_points(self) -> None:
        if not self.model.raid_points.enabled:
            return
        if not self._ensure_raid_point_scope():
            return
        self._rebuild_raid_derived_state()

    def _ensure_raid_point_scope(self) -> bool:
        if not self.model.raid_points.enabled:
            return True
        if self.model.raid_points_legacy_scope_required:
            choice, accepted = QInputDialog.getItem(
                self, tr("raid_points.legacy_title"), tr("raid_points.legacy_prompt"),
                [tr("raid_points.calculation_all"), tr("raid_points.calculation_from")], 0, False,
            )
            if not accepted:
                return False
            start = None
            if choice == tr("raid_points.calculation_from"):
                start, accepted = QInputDialog.getText(
                    self, tr("raid_points.legacy_title"), "YYYY-MM-DD",
                )
                if not accepted:
                    return False
            try:
                self.model.set_raid_point_calculation_scope(
                    "from_date" if start else "all", start or None,
                )
            except ValueError as exc:
                QMessageBox.warning(self, APP_NAME, str(exc))
                return False
            self.model.raid_points_legacy_scope_required = False
            self.autosave()
        elif self.model.raid_points.calculation_mode is None:
            return False
        previous_scope = set(self.model.raid_points.included_raid_ids)
        self.model.raid_points.rebuild_scope(self.model.raids)
        if previous_scope != self.model.raid_points.included_raid_ids:
            self.model.dirty = True
            self.autosave()
        return True

    def _raid_point_scope_changed(self, _checked: bool | None = None) -> None:
        if not hasattr(self, "raid_scope_all") or not self.model.raid_points.enabled:
            return
        mode = "all" if self.raid_scope_all.isChecked() else "from_date"
        start = self.raid_scope_start.text().strip() if mode == "from_date" else None
        try:
            self.model.set_raid_point_calculation_scope(mode, start)
        except ValueError:
            return
        self.raid_scope_start.setEnabled(mode == "from_date")
        self.autosave()
        self._rebuild_raid_derived_state()
        self.refresh_all(select_first=False)

    def _reset_project_services(self) -> None:
        self._clm_refresh_service = ClmDkpRefreshService()
        self._clm_dkp_by_member_id = {}
        try:
            self._raid_point_projection = (
                build_point_history(
                    self.model.raid_points, self.model.raids, self.model.raid_attendance,
                )
                if self.model.raid_points.enabled else None
            )
        except Exception:
            self._raid_point_projection = None
        self._rebuild_reward_assignments()
        if hasattr(self, "raid_stats_table"):
            self._invalidate_raid_views()
            self._refresh_visible_point_details()
            self._refresh_visible_reward_details()
            self._refresh_visible_dkp_details()
        if hasattr(self, "clm_roster_combo"):
            self.clm_roster_combo.clear()
            self.clm_status_label.setText(tr("raid_clm_admin.clm_not_refreshed"))
            self.points_status_label.setText(tr("raid_clm_admin.raid_statistics_not_rebuilt"))

    def open_player_assignments(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("raid_clm_admin.player_assignments"))
        dialog.resize(900, 520)
        layout = QVBoxLayout(dialog)
        help_label = QLabel(tr("raid_clm_admin.assignments_help"))
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        table = CopyableReadOnlyTable(0, 5)
        table.setHorizontalHeaderLabels([
            tr("raid_clm_admin.player_id"), tr("raid_clm_admin.main"),
            tr("raid_clm_admin.character_count"), tr("raid_clm_admin.eternal_player"),
            tr("raid_clm_admin.members"),
        ])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table, 1)

        def populate() -> None:
            players = {player.playerId: player for player in self.model.players}
            player_ids = set(players)
            player_ids.update(member.playerId for member in self.model.members if member.playerId)
            player_ids.update(
                entry.playerId for entry in self.model.raid_attendance if entry.playerId
            )
            table.setRowCount(0)
            for player_id in sorted(player_ids):
                members = [member for member in self.model.members if member.playerId == player_id]
                mains = [member for member in members if member.characterType == "main"]
                current_main = next((member for member in mains if member.lifeStatus == "active"), None)
                if current_main is None and mains:
                    current_main = mains[0]
                member_lines = "\n".join(
                    " · ".join((
                        member.name, member.id, character_type_display(member.characterType),
                        tr(f"life.{member.lifeStatus}"), member.className or tr("common.not_set"),
                        raid_role_display(member.raidRole),
                        self._format_dkp_value(
                            self.model.eternal_character_totals().get(member.id, (0, 0))[0]
                        ),
                    ))
                    for member in sorted(members, key=lambda value: (value.name.casefold(), value.id))
                ) or "–"
                row = table.rowCount()
                table.insertRow(row)
                values = (
                    player_id,
                    current_main.name if current_main is not None else "–",
                    len(members),
                    self._format_dkp_value(self.model.eternal_player_totals().get(player_id, (0, 0))[0]),
                    member_lines,
                )
                for column, value in enumerate(values):
                    table.setItem(row, column, QTableWidgetItem(str(value)))
                table.resizeRowToContents(row)

        def assign_twink() -> None:
            members = sorted(self.model.members, key=lambda member: member.name.casefold())
            mains = sorted((
                member for member in self.model.members
                if member.lifeStatus == "active" and member.characterType == "main"
            ), key=lambda member: member.name.casefold())
            if not members or not mains:
                QMessageBox.information(dialog, APP_NAME, tr("raid_clm_admin.assignment_not_possible"))
                return
            member_labels = [f"{member.name} · {member.id}" for member in members]
            member_label, ok = QInputDialog.getItem(
                dialog, tr("raid_clm_admin.assign_twink"),
                tr("raid_clm_admin.choose_character"), member_labels, 0, False,
            )
            if not ok:
                return
            member = members[member_labels.index(member_label)]
            main_options = [main for main in mains if main.id != member.id]
            if not main_options:
                QMessageBox.information(dialog, APP_NAME, tr("raid_clm_admin.assignment_not_possible"))
                return
            main_labels = [f"{main.name} · {main.id}" for main in main_options]
            main_label, ok = QInputDialog.getItem(
                dialog, tr("raid_clm_admin.assign_twink"),
                tr("raid_clm_admin.choose_main"), main_labels, 0, False,
            )
            if not ok:
                return
            main = main_options[main_labels.index(main_label)]
            try:
                self.model.assign_character_type(
                    member.id, "twink", main.id, member.raidRole,
                )
                self.autosave()
                self._rebuild_raid_derived_state()
                populate()
                self.refresh_all(select_first=False)
            except Exception as exc:
                QMessageBox.warning(dialog, APP_NAME, str(exc))

        def merge_players() -> None:
            players = sorted(self.model.players, key=lambda player: player.playerName.casefold())
            if len(players) < 2:
                QMessageBox.information(dialog, APP_NAME, tr("raid_clm_admin.merge_not_possible"))
                return
            labels = [f"{player.playerName} · {player.playerId}" for player in players]
            source_label, ok = QInputDialog.getItem(
                dialog, tr("raid_clm_admin.merge_players"),
                tr("raid_clm_admin.source_player"), labels, 0, False,
            )
            if not ok:
                return
            source = players[labels.index(source_label)]
            target_options = [player for player in players if player.playerId != source.playerId]
            target_labels = [f"{player.playerName} · {player.playerId}" for player in target_options]
            target_label, ok = QInputDialog.getItem(
                dialog, tr("raid_clm_admin.merge_players"),
                tr("raid_clm_admin.target_player"), target_labels, 0, False,
            )
            if not ok:
                return
            target = target_options[target_labels.index(target_label)]
            plan = plan_player_merge(
                source.playerId, target.playerId, self.model.members, self.model.raid_attendance,
            )
            resolutions: dict[str, str] = {}
            for conflict in plan.conflicts:
                options = [
                    f"{entry.character_name} · {entry.attendance_id}"
                    for entry in conflict.entries
                ]
                selected, accepted = QInputDialog.getItem(
                    dialog,
                    tr("raid_clm_admin.merge_conflict_title"),
                    tr("raid_clm_admin.merge_conflict_prompt", raid_id=conflict.raid_id),
                    options, 0, False,
                )
                if not accepted:
                    return
                resolutions[conflict.raid_id] = conflict.entries[options.index(selected)].attendance_id
            try:
                result = apply_player_merge(
                    source.playerId, target.playerId,
                    self.model.players, self.model.members, self.model.raid_attendance,
                    conflict_resolutions=resolutions,
                )
            except PlayerMergeConflictError:
                QMessageBox.warning(dialog, APP_NAME, tr("raid_clm_admin.merge_decisions_missing"))
                return
            except Exception as exc:
                QMessageBox.warning(dialog, APP_NAME, str(exc))
                return
            self.model.players = list(result.players)
            self.model.members = list(result.members)
            self.model.raid_attendance = list(result.attendance)
            self.model.raid_points.exclude_attendance(result.excluded_attendance_ids)
            self.model.dirty = True
            self.autosave()
            self._rebuild_raid_derived_state()
            populate()
            self.refresh_all(select_first=False)
            self.set_status(tr("raid_clm_admin.merge_complete"))

        actions = QHBoxLayout()
        assign_button = QPushButton(tr("raid_clm_admin.assign_twink"))
        assign_button.clicked.connect(assign_twink)
        actions.addWidget(assign_button)
        merge_button = set_button_role(QPushButton(tr("raid_clm_admin.merge_players")), primary=True)
        merge_button.clicked.connect(merge_players)
        actions.addWidget(merge_button)
        actions.addStretch(1)
        close_button = QPushButton(tr("common.close"))
        close_button.clicked.connect(dialog.accept)
        actions.addWidget(close_button)
        layout.addLayout(actions)
        populate()
        dialog.exec()

    def _project_feature_state_changed(self) -> None:
        self.model.dirty = True
        self.autosave()
        self._rebuild_raid_derived_state()
        self.refresh_all(select_first=False)

    def _points_system_toggled(self, enabled: bool) -> None:
        if enabled == (self.model.active_point_mode() == POINT_MODE_RAID):
            return
        if enabled:
            if not self.model.raid_points.enabled:
                relevant_raids = (
                    self.model.raid_points.pending_raid_ids
                    if self.model.raid_points.ever_enabled
                    else {raid.id for raid in self.model.raids}
                )
                include_existing = False
                if relevant_raids:
                    include_existing = QMessageBox.question(
                        self,
                        tr("raid_clm_admin.activate_points_title"),
                        tr("raid_clm_admin.activate_points_question", count=len(relevant_raids)),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    ) == QMessageBox.StandardButton.Yes
                self.model.raid_points.activate(
                    (raid.id for raid in self.model.raids), include_existing=include_existing,
                )
                if self.model.raid_points.calculation_mode is None:
                    self.model.set_raid_point_calculation_scope("all")
            self.model.point_mode = POINT_MODE_RAID
            self.model.dkp_enabled = False
        else:
            self.model.raid_points.deactivate()
            self.model.point_mode = ""
        self._project_feature_state_changed()

    def _dkp_mode_toggled(self, enabled: bool) -> None:
        self._update_feature_controls(enabled)
        if enabled == (self.model.active_point_mode() == POINT_MODE_ETERNAL):
            return
        self.model.dkp_enabled = enabled
        self.model.point_mode = POINT_MODE_ETERNAL if enabled else ""
        self._project_feature_state_changed()

    def save_settings(self) -> None:
        self.gear_outdated_tracking = self.outdated_check.isChecked()
        self.gear_outdated_days = self.outdated_days_spin.value()
        update_suite_settings(
            self._suite_settings_path,
            gear_outdated_tracking=self.gear_outdated_tracking,
            gear_outdated_days=self.gear_outdated_days,
        )
        requested = language_from_display(self.language_combo.currentText())
        if requested != get_language():
            set_language(requested)
            QMessageBox.information(self, tr("language.restart_title"), tr("language.restart_message"))
        self.refresh_all(select_first=False)
        self.set_status(tr("checker.settings_saved"))

    # ---------- projects ----------
    def _confirm_discard(self) -> bool:
        if not self.model.dirty:
            return True
        answer = QMessageBox.question(
            self, APP_NAME, tr("checker.discard_changes"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self.model.new_empty()
        self._reset_project_services()
        self._invalidate_project_handoff()
        self.selected_member_id = None
        self.autosave()
        self.set_member_tab("Gildenliste", refresh=False)
        self.refresh_all(select_first=False)
        self.clear_detail()
        path, _filter = QFileDialog.getSaveFileName(
            self, tr("checker.save_project_title"), "Neue_Gilde.ggc",
            "Guild Gear Checker (*.ggc)",
        )
        if not path:
            self.set_status(tr("checker.new_project_done"))
            return
        if not Path(path).suffix:
            path += ".ggc"
        try:
            self.model.save(Path(path), backup=False)
            self.refresh_project_label()
            self.set_status(tr("checker.project_saved", name=Path(path).name))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, tr("checker.project_save_error", error=exc))

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        path, _filter = QFileDialog.getOpenFileName(self, tr("checker.open_project_title"), "", "Guild Gear Checker (*.ggc)")
        if not path:
            return
        try:
            project = Path(path)
            recovery = newer_autosave(project)
            if recovery is not None and QMessageBox.question(
                self, APP_NAME,
                tr("checker.autosave_recovery_question", name=project.name),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes:
                payload = json.loads(recovery.read_text(encoding="utf-8-sig"))
                self.model.load_payload(payload, project.resolve())
                self.model.dirty = True
            else:
                self.model.load(project)
            migration = migrate_legacy_portraits(project, self.model.members)
            self.model.portrait_migration_summary = migration
            if migration.ambiguous_names:
                QMessageBox.warning(
                    self, APP_NAME,
                    tr(
                        "checker.portrait_migration_ambiguous",
                        names=", ".join(migration.ambiguous_names),
                    ),
                )
            self._reset_project_services()
            self._invalidate_project_handoff()
            self._apply_character_cache_once()
            self.autosave()
            self.selected_member_id = None
            self.set_member_tab("Gildenliste", refresh=False)
            self.switch_page("rooster", refresh=False)
            self.refresh_all(select_first=True)
            self.set_status(tr("checker.project_loaded", name=Path(path).name))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, tr("checker.project_load_error", error=exc))

    def save_project(self) -> None:
        if not self.model.project_path:
            self.save_project_as()
            return
        try:
            self.model.save(self.model.project_path, backup=True)
            self.autosave()
            self.refresh_project_label()
            self.set_status(tr("checker.project_saved", name=self.model.project_path.name))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, tr("checker.project_save_error", error=exc))

    def save_project_as(self) -> None:
        initial = self.model.project_path.name if self.model.project_path else "Stitches_Gilde.ggc"
        path, _filter = QFileDialog.getSaveFileName(self, tr("checker.save_project_title"), initial, "Guild Gear Checker (*.ggc)")
        if not path:
            return
        if not Path(path).suffix:
            path += ".ggc"
        try:
            target = Path(path)
            old_project = self.model.project_path
            copy_project_portraits(old_project, target)
            self.model.save(target, backup=True)
            if old_project is None or old_project.resolve() != target.resolve():
                self._invalidate_project_handoff()
            self.autosave()
            self.refresh_project_label()
            self.set_status(tr("checker.project_saved", name=Path(path).name))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, tr("checker.project_save_error", error=exc))

    def export_project(self) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        base = self.model.project_path.stem if self.model.project_path else "Stitches_Gilde"
        path, _filter = QFileDialog.getSaveFileName(
            self, tr("checker.export_project_title"), f"{base}_Export_{stamp}.ggc", "Guild Gear Checker (*.ggc)"
        )
        if not path:
            return
        old_path, old_dirty = self.model.project_path, self.model.dirty
        try:
            target = Path(path if Path(path).suffix else path + ".ggc")
            temp = target.with_suffix(target.suffix + ".tmp")
            temp.write_text(json.dumps(self.model.to_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, target)
            QMessageBox.information(self, APP_NAME, tr("checker.export_success"))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, tr("checker.export_error", error=exc))
        finally:
            self.model.project_path, self.model.dirty = old_path, old_dirty

    def export_project_with_portraits(self) -> None:
        suggested = project_package_default_filename(self.model.project_path)
        path, _filter = QFileDialog.getSaveFileName(self, tr("checker.package_export_title"), suggested, "ZIP (*.zip)")
        if not path:
            return
        if not Path(path).suffix:
            path += ".zip"
        old_path, old_dirty = self.model.project_path, self.model.dirty
        try:
            summary = create_project_package(self.model, Path(path))
            QMessageBox.information(
                self, tr("checker.package_export_title"),
                tr(
                    "checker.package_export_success", path=summary.target,
                    portraits=summary.portrait_count, historical=summary.historical_portrait_count,
                    markers=summary.missing_marker_count, missing=summary.missing_portrait_count,
                ),
            )
        except Exception as exc:
            stage = exc.stage if isinstance(exc, ProjectPackageError) else "zip"
            detail_key = {
                "project": "checker.package_project_error",
                "manifest": "checker.package_manifest_error",
                "zip": "checker.package_zip_error",
            }.get(stage, "checker.package_zip_error")
            QMessageBox.critical(
                self, tr("checker.package_export_title"),
                tr("checker.package_export_failed", error=tr(detail_key, error=exc)),
            )
        finally:
            self.model.project_path, self.model.dirty = old_path, old_dirty

    def import_project_with_portraits(self) -> None:
        if not self._confirm_discard():
            return
        source, _filter = QFileDialog.getOpenFileName(
            self, tr("checker.package_import"), "", "ZIP (*.zip)",
        )
        if not source:
            return
        suggested = Path(source).stem.replace("_mit_Portraits", "") + ".ggc"
        target, _filter = QFileDialog.getSaveFileName(
            self, tr("checker.package_import_save_title"), suggested, "Guild Gear Checker (*.ggc)",
        )
        if not target:
            return
        if not Path(target).suffix:
            target += ".ggc"
        try:
            summary = import_project_package(Path(source), Path(target))
            self.model.load(summary.project_path)
            self._reset_project_services()
            self._invalidate_project_handoff()
            self.selected_member_id = None
            self.set_member_tab("Gildenliste", refresh=False)
            self.switch_page("rooster")
            self.refresh_all(select_first=True)
            self.set_status(tr("checker.package_imported", name=summary.project_path.name))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, tr("checker.package_import_failed", error=exc))

    def open_active_portrait_folder(self) -> None:
        folder = project_portrait_root(self.model.project_path)
        if folder is None:
            QMessageBox.information(self, APP_NAME, tr("checker.project_required"))
            return
        safe_open_folder(folder)

    def refresh_project_label(self) -> None:
        if hasattr(self, "banner_title"):
            self.banner_title.setText(self.model.guild_name or tr("checker.title"))
        if self.model.project_path:
            suffix = tr("checker.dirty_suffix") if self.model.dirty else ""
            self.project_label.setText(tr("checker.project_label", name=self.model.project_path.name, dirty=suffix))
            self.project_label.setToolTip(str(self.model.project_path.resolve()))
        else:
            self.project_label.setText(tr("checker.no_project_loaded"))
            self.project_label.setToolTip("")

    # ---------- persistence / compatibility ----------
    def _load_autosave_or_seed(self) -> None:
        # Autosaves remain untouched recovery files. Startup itself is always empty.
        self.model.new_empty()

    def autosave(self) -> None:
        target = autosave_path(self.model.project_path)
        if target is None or not self.model.dirty:
            return
        try:
            atomic_write_bytes(
                target,
                (json.dumps(self.model.to_payload(), ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
        except Exception as exc:
            self.set_status(tr("checker.autosave_failed", error=exc))

    def _apply_character_cache_once(self) -> None:
        try:
            try:
                from app.character_cache import character_cache_path, load_character_cache
            except ImportError:
                from character_cache import character_cache_path, load_character_cache  # type: ignore
            payload = load_character_cache(character_cache_path(app_base_dir()))
            summary = self.model.apply_character_cache(payload)
            if summary.get("updated"):
                self.autosave()
        except Exception:
            return

    def _refresh_selected_portrait_only(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if member is not None and self.stack.currentWidget() is self._pages.get("management"):
            self.detail_portrait.set_source(member_portrait_path(self.model, member))
        roster_member = self.model.find_by_id(getattr(self, "roster_selected_member_id", ""))
        if roster_member is not None and self.stack.currentWidget() is self._pages.get("rooster"):
            self.roster_detail_portrait.set_source(member_portrait_path(self.model, roster_member))

    def _invalidate_project_handoff(self) -> None:
        self._project_handoff_session_id = None
        self._project_handoff_processed_tokens.clear()
        self._project_handoff_file_signatures.clear()

    def _poll_project_handoff(self) -> None:
        """Apply project-scoped entity actions emitted by the Portrait Grabber."""
        try:
            project = self.model.project_path
            session_id = self._project_handoff_session_id
            if project is None or not session_id:
                return
            file_signatures = getattr(self, "_project_handoff_file_signatures", None)
            if file_signatures is None:
                file_signatures = set()
                self._project_handoff_file_signatures = file_signatures
            actions = pending_actions(
                project, session_id, self._project_handoff_processed_tokens,
                file_signatures,
            )
            if not actions:
                return
            processed_now = set(self._project_handoff_processed_tokens)
            result = apply_actions(self.model, actions, processed_now)
            if result["changed"] or self.model.dirty:
                self.model.save(project, backup=True)
            for receipt in result["receipts"]:
                write_receipt(project, session_id, receipt["token"], receipt)
            self._project_handoff_processed_tokens.update(
                receipt["token"] for receipt in result["receipts"]
            )
            if result["changed"]:
                if result["graveyardChanged"]:
                    self._grave_pixmaps.clear()
                self.refresh_all()
                added = sum(
                    int(receipt.get("summary", {}).get("added", 0))
                    for receipt in result["receipts"] if receipt.get("ok")
                )
                if added:
                    self.set_status(tr("checker.grabber_members_applied", count=added))
                else:
                    self.set_status(tr("checker.grabber_changes_applied"))
        except Exception as exc:
            self.set_status(tr("checker.grabber_handoff_failed", error=exc))

    def open_portrait_grabber(self) -> None:
        grabber = app_base_dir() / "app" / "GuildPortraitGrabberQt.py"
        if not grabber.is_file():
            QMessageBox.critical(self, APP_NAME, tr("checker.grabber_missing", path=grabber))
            return
        try:
            if self.model.project_path and self.model.dirty:
                self.model.save(self.model.project_path, backup=True)
            executable = Path(sys.executable)
            if sys.platform.startswith("win") and executable.name.casefold() == "python.exe":
                pythonw = executable.with_name("pythonw.exe")
                if pythonw.is_file():
                    executable = pythonw
            command = [str(executable), str(grabber)]
            if self.model.project_path:
                self._project_handoff_session_id = new_session_id()
                self._project_handoff_processed_tokens.clear()
                self._project_handoff_file_signatures.clear()
                command.extend([
                    "--project", str(self.model.project_path.resolve()),
                    "--session-id", self._project_handoff_session_id,
                ])
            subprocess.Popen(command, cwd=str(app_base_dir()))
            self.set_status(tr("checker.grabber_started"))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, tr("checker.grabber_error", error=exc))

    def launch_legacy_checker(self) -> None:
        script = app_base_dir() / "app" / "GuildGearChecker.py"
        try:
            import subprocess
            executable = Path(sys.executable)
            pythonw = executable.with_name("pythonw.exe") if sys.platform.startswith("win") else executable
            subprocess.Popen([str(pythonw if pythonw.exists() else executable), str(script)], cwd=str(app_base_dir()))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, tr("checker.legacy_start_error", error=exc))

    def set_status(self, text: str) -> None:
        self.status_label.setText(str(text))

    def closeEvent(self, event) -> None:  # noqa: N802
        self.autosave()
        geometry = self.geometry()
        update_suite_settings(
            self._suite_settings_path,
            checker_qt_geometry=f"{geometry.width()}x{geometry.height()}{geometry.x():+d}{geometry.y():+d}",
            graveyard_zoom_percent=self._graveyard_zoom_percent,
            roster_zoom_percent=self._roster_zoom_percent,
        )
        event.accept()


def _write_startup_error(trace_text: str) -> Path | None:
    try:
        log_dir = app_base_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        target = log_dir / "qt_startup_error.log"
        target.write_text(trace_text, encoding="utf-8")
        return target
    except Exception:
        return None


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(QT_PREVIEW_VERSION)
    app.setStyle("Fusion")
    try:
        window = GuildGearCheckerQt()
        window.show()
        return app.exec()
    except Exception:
        import traceback
        trace_text = traceback.format_exc()
        log_path = _write_startup_error(trace_text)
        print(trace_text, file=sys.stderr, flush=True)
        detail = tr("checker.qt_start_error") + "\n\n" + trace_text
        if log_path is not None:
            detail += "\n" + tr("checker.error_log", path=log_path)
        try:
            QMessageBox.critical(None, f"{APP_NAME} - {tr('checker.startup_error_title')}", detail)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
