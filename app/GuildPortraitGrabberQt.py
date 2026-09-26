# -*- coding: utf-8 -*-
"""PySide6-Oberfläche für den Guild Portrait Grabber.

Der Standardpfad verwendet dieselben Projekt-, Worker- und Armory-Verträge wie
der weiterhin separat verfügbare Tkinter-Legacy-/Fallbackpfad.
"""
from __future__ import annotations

import argparse
import queue
import subprocess
import sys
import threading
import time
import traceback
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Callable, Sequence

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPen, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PIL import Image, ImageOps
from PIL.ImageQt import ImageQt

try:
    from app.qt_row_hover import install_row_hover
except ImportError:
    from qt_row_hover import install_row_hover  # type: ignore

try:
    from app.GuildGearChecker import (
        GRAVESTONE_CARD_SIZE,
        GRAVESTONE_PORTRAIT_ZOOM_RANGE,
        GRAVESTONE_TEXT_SCALE_RANGE,
        CLASS_COLORS,
        GuildModel,
        Member,
        class_icon_path,
        detect_gravestone_portrait_opening,
        normalize_portrait_zoom,
        normalize_text_scale,
        prepare_gravestone_template,
        render_gravestone_card,
        shifted_portrait_offsets,
        shifted_text_offsets,
    )
    from app.GuildPortraitGrabber import (
        build_portrait_source_url,
        build_saved_grabber_config,
        build_worker_payload,
        capture_mode_display,
        capture_screen_region,
        clamp_crop,
        default_output_dir,
        dedupe_names,
        existing_portrait_for_member,
        graveyard_portrait_for_member,
        graveyard_preview_portrait_for_member,
        grabber_banner_path,
        build_gravestone_editor_state,
        create_portrait_source_worker,
        import_active_portrait_image,
        interpret_worker_event,
        load_names_from_file,
        GravestoneEditorState,
        PortraitEditorState,
        PORTRAIT_EDITOR_PREVIEW_SIZE,
        PORTRAIT_EDITOR_ZOOM_RANGE,
        PORTRAIT_EDITOR_ZOOM_STEP,
        load_portrait_editor_state,
        load_config,
        missing_portrait_names,
        records_missing_armory_data,
        normal_portrait_path,
        portrait_editor_crop_box,
        portrait_editor_geometry,
        portrait_editor_pan,
        portrait_selection_rect,
        portrait_source_settings,
        portrait_editor_transform,
        portrait_editor_zoom,
        remove_active_portrait_files,
        save_config,
        save_portrait_editor_image,
        suite_root_dir,
        normalize_screen_region,
        validate_screen_region,
        virtual_screen_bounds,
    )
    from app.gravestone_categories import (
        GRAVESTONE_CATEGORIES,
        normalize_gravestone_category,
    )
    from app.i18n import (
        get_language,
        gravestone_category_display,
        language_display_values,
        language_from_display,
        race_display,
        set_language,
        tr,
    )
    from app.project_storage import (
        load_project_payload, migrate_legacy_portraits, patch_project_member, project_paths,
    )
    from app.project_handoff import (
        apply_actions_to_project,
        make_action,
        queue_action,
        read_receipt,
    )
except ImportError:  # Direkter Start über app\GuildPortraitGrabberQt.py
    from GuildGearChecker import (
        GRAVESTONE_CARD_SIZE,
        GRAVESTONE_PORTRAIT_ZOOM_RANGE,
        GRAVESTONE_TEXT_SCALE_RANGE,
        CLASS_COLORS,
        GuildModel,
        Member,
        class_icon_path,
        detect_gravestone_portrait_opening,
        normalize_portrait_zoom,
        normalize_text_scale,
        prepare_gravestone_template,
        render_gravestone_card,
        shifted_portrait_offsets,
        shifted_text_offsets,
    )
    from GuildPortraitGrabber import (
        build_portrait_source_url,
        build_saved_grabber_config,
        build_worker_payload,
        capture_mode_display,
        capture_screen_region,
        clamp_crop,
        default_output_dir,
        dedupe_names,
        existing_portrait_for_member,
        graveyard_portrait_for_member,
        graveyard_preview_portrait_for_member,
        grabber_banner_path,
        build_gravestone_editor_state,
        create_portrait_source_worker,
        import_active_portrait_image,
        interpret_worker_event,
        load_names_from_file,
        GravestoneEditorState,
        PortraitEditorState,
        PORTRAIT_EDITOR_PREVIEW_SIZE,
        PORTRAIT_EDITOR_ZOOM_RANGE,
        PORTRAIT_EDITOR_ZOOM_STEP,
        load_portrait_editor_state,
        load_config,
        missing_portrait_names,
        records_missing_armory_data,
        normal_portrait_path,
        portrait_editor_crop_box,
        portrait_editor_geometry,
        portrait_editor_pan,
        portrait_selection_rect,
        portrait_source_settings,
        portrait_editor_transform,
        portrait_editor_zoom,
        remove_active_portrait_files,
        save_config,
        save_portrait_editor_image,
        suite_root_dir,
        normalize_screen_region,
        validate_screen_region,
        virtual_screen_bounds,
    )
    from gravestone_categories import GRAVESTONE_CATEGORIES, normalize_gravestone_category
    from i18n import (
        get_language,
        gravestone_category_display,
        language_display_values,
        language_from_display,
        race_display,
        set_language,
        tr,
    )
    from project_storage import (  # type: ignore
        load_project_payload, migrate_legacy_portraits, patch_project_member, project_paths,
    )
    from project_handoff import apply_actions_to_project, make_action, queue_action, read_receipt

try:
    from tools.gravestone_review.gravestone_review_qt import QtGravestoneReviewWidget
except ImportError:  # Direkter Start über app\GuildPortraitGrabberQt.py
    _SUITE_ROOT = Path(__file__).resolve().parents[1]
    if str(_SUITE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SUITE_ROOT))
    from tools.gravestone_review.gravestone_review_qt import QtGravestoneReviewWidget


APP_NAME = "Guild Portrait Grabber"
APP_VERSION = "0.12.1"
GRABBER_INTERACTION_STYLE = """
QPushButton, QToolButton {
    background:#202a33; color:#f0dfbf; border:1px solid #4c5b68;
    border-radius:4px; padding:4px 8px;
}
QPushButton:hover, QToolButton:hover {background:#263746; border-color:#8193a2;}
QPushButton:pressed, QToolButton:pressed {background:#151f29; border-color:#8193a2;}
QPushButton:disabled, QToolButton:disabled {
    background:#171d24; color:#747e87; border-color:#2b333b;
}
QPushButton:focus, QToolButton:focus {border-color:#c7a265;}
QTabBar::tab {
    background:#171f28; color:#aeb8c2; border:1px solid #303b47;
    border-top:2px solid transparent; padding:6px 10px;
}
QTabBar::tab:hover {background:#202d3b; color:#e0e9ef;}
QTabBar::tab:selected {background:#202932; color:#f3e6cd; border-top-color:#c7a265;}
QTabBar::tab:selected:hover {background:#202932; color:#f3e6cd;}
QTabBar::tab:disabled {background:#151b22; color:#68727c;}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background:#10161d; color:#e8edf1; border:1px solid #35414d;
    border-radius:4px; padding:4px;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border-color:#6b7885;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color:#c7a265;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    background:#171d24; color:#747e87; border-color:#2b333b;
}
QTableView {selection-background-color:#302b22; selection-color:#f5dfb1; outline:0;}
QHeaderView::section:hover {background:#293542; color:#f1d79f;}
"""
GRAVESTONE_CATEGORY_FILTER_ALL = "__all__"
GRABBER_MINIMUM_SIZE = QSize(1050, 760)
GRABBER_INITIAL_RATIO = 0.75
GRABBER_BANNER_HEIGHT = 190
GRABBER_BANNER_FOCAL_POINT = (0.33, 0.46)


class GrabberBannerWidget(QWidget):
    """Qt-Gegenstück zum fokussierten, entprellten Tk-Banner-Cover."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source = QPixmap(str(grabber_banner_path()))
        self._rendered = QPixmap()
        self._rendered_size = QSize()
        self._pending_size = QSize()
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(60)
        self._resize_timer.timeout.connect(self._render_cover)
        self.guild_text = ""
        self.project_text = ""
        self.project_tooltip = ""
        self.version_text = f"v{APP_VERSION}"
        self.setMinimumHeight(150)
        self.setFixedHeight(GRABBER_BANNER_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_metadata(self, *, guild: str, project: str, project_path: str) -> None:
        self.guild_text = guild
        self.project_text = project
        self.project_tooltip = project_path
        self.setToolTip(project_path)
        self.update()

    def resizeEvent(self, event) -> None:
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
        scale = max(target.width() / source_size.width(), target.height() / source_size.height())
        scaled_size = QSize(
            max(1, round(source_size.width() * scale)),
            max(1, round(source_size.height() * scale)),
        )
        scaled = self._source.scaled(
            scaled_size,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        left = -round((scaled.width() - target.width()) * GRABBER_BANNER_FOCAL_POINT[0])
        top = -round((scaled.height() - target.height()) * GRABBER_BANNER_FOCAL_POINT[1])
        rendered = QPixmap(target)
        rendered.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rendered)
        painter.drawPixmap(left, top, scaled)
        painter.end()
        self._rendered = rendered
        self._rendered_size = target
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self._rendered.isNull():
            painter.fillRect(self.rect(), Qt.GlobalColor.darkRed)
        else:
            # Während der kurzen Resize-Entprellung bleibt das letzte Cover
            # unverzerrt; danach ersetzt es der passend zugeschnittene Cache.
            painter.drawPixmap(0, 0, self._rendered)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        margin = 16
        guild_font = painter.font()
        guild_font.setPointSize(max(10, guild_font.pointSize() + 2))
        guild_font.setBold(True)
        painter.setFont(guild_font)
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(
            QRect(margin, 12, max(1, self.width() - 2 * margin), 30),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self.guild_text,
        )
        meta_font = painter.font()
        meta_font.setPointSize(max(9, meta_font.pointSize() - 1))
        meta_font.setBold(False)
        painter.setFont(meta_font)
        bottom = QRect(margin, self.height() - 40, max(1, self.width() - 2 * margin), 28)
        painter.drawText(bottom, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.project_text)
        painter.drawText(bottom, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.version_text)


class ImageSelectionViewQt(QGraphicsView):
    """Ein gemeinsamer, skalierbarer Rechteckselektor für Bildkoordinaten."""

    selection_changed = Signal(QRectF)

    def __init__(self, image: Image.Image, initial_rect: QRectF,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selection_scene = QGraphicsScene(self)
        self.setScene(self._selection_scene)
        pixmap = QPixmap.fromImage(ImageQt(image.convert("RGBA")))
        self._pixmap_item = self._selection_scene.addPixmap(pixmap)
        self._image_rect = QRectF(0.0, 0.0, float(image.width), float(image.height))
        self._selection_scene.setSceneRect(self._image_rect)
        self._selection_item = QGraphicsRectItem()
        self._selection_item.setPen(QPen(Qt.GlobalColor.yellow, 3.0))
        self._selection_item.setZValue(1.0)
        self._selection_scene.addItem(self._selection_item)
        self._drag_start: QPointF | None = None
        self.setObjectName("imageSelectionView")
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.set_selection(initial_rect)

    def set_selection(self, rect: QRectF) -> None:
        bounded = rect.normalized().intersected(self._image_rect)
        self._selection_item.setRect(bounded)
        self.selection_changed.emit(QRectF(bounded))

    def selection(self) -> QRectF:
        return QRectF(self._selection_item.rect())

    def _scene_position(self, event) -> QPointF:
        point = self.mapToScene(event.position().toPoint())
        return QPointF(
            max(self._image_rect.left(), min(self._image_rect.right(), point.x())),
            max(self._image_rect.top(), min(self._image_rect.bottom(), point.y())),
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.fitInView(self._image_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fitInView(self._image_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = self._scene_position(event)
            self.set_selection(QRectF(self._drag_start, self._drag_start))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is not None:
            self.set_selection(QRectF(self._drag_start, self._scene_position(event)))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            self.set_selection(QRectF(self._drag_start, self._scene_position(event)))
            self._drag_start = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ImageSelectionDialogQt(QDialog):
    """Ein Dialog für Raw-Crop und Standardbrowser-Bildschirmregion."""

    def __init__(self, image: Image.Image, initial_rect: QRectF, *, title: str,
                 help_text: str, on_accept: Callable[[QRectF], None],
                 apply_text: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._initial_rect = QRectF(initial_rect)
        self._on_accept = on_accept
        self.setObjectName("imageSelectionDialog")
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(1000, 760)
        self.setMinimumSize(560, 420)
        layout = QVBoxLayout(self)
        help_label = QLabel(help_text)
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        self.selection_view = ImageSelectionViewQt(image, initial_rect, self)
        layout.addWidget(self.selection_view, 1)
        buttons = QHBoxLayout()
        reset_button = QPushButton(tr("grabber.default"))
        reset_button.clicked.connect(
            lambda: self.selection_view.set_selection(self._initial_rect)
        )
        buttons.addWidget(reset_button)
        buttons.addStretch(1)
        apply_button = QPushButton(apply_text or tr("grabber.apply_crop"))
        apply_button.clicked.connect(self._accept_selection)
        apply_button.setDefault(True)
        buttons.addWidget(apply_button)
        cancel_button = QPushButton(tr("common.cancel"))
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

    def _accept_selection(self) -> None:
        rect = self.selection_view.selection().normalized()
        if rect.width() < 10.0 or rect.height() < 10.0:
            QMessageBox.warning(self, tr("grabber.crop"), tr("grabber.crop_too_small"))
            return
        self._on_accept(rect)
        self.accept()


def parse_cli(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guild Portrait Grabber - Qt")
    parser.add_argument("--project", default="", help="Pfad zu einem .ggc-Projekt")
    parser.add_argument("--session-id", default="", help="Session-ID des Checker-Handoffs")
    return parser.parse_args(argv)


def create_application(argv: Sequence[str] | None = None) -> tuple[QApplication, bool]:
    """Erzeugt eine QApplication oder verwendet die bereits laufende Instanz."""
    existing = QApplication.instance()
    if existing is not None:
        return existing, False
    application = QApplication(list(argv or []))
    application.setApplicationName(APP_NAME)
    application.setApplicationVersion(APP_VERSION)
    application.setStyle("Fusion")
    return application, True


class PortraitPreviewLabel(QLabel):
    """Zeigt genau ein aktuelles Portrait proportional und ohne Dateicache-Wachstum."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_pixmap: QPixmap | None = None
        self._source_signature: tuple[str, int, int] | None = None
        self._empty_text = ""
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumSize(220, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    @property
    def source_signature(self) -> tuple[str, int, int] | None:
        return self._source_signature

    def set_portrait(self, path: Path | None, empty_text: str) -> bool:
        self._empty_text = empty_text
        if path is None:
            self._clear_source()
            return False
        try:
            stat = path.stat()
            signature = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        except OSError:
            self._clear_source()
            return False
        if signature != self._source_signature:
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                self._clear_source()
                return False
            self._source_pixmap = pixmap
            self._source_signature = signature
        self.setText("")
        self._render_source()
        return True

    def set_empty_text(self, text: str) -> None:
        self._empty_text = text
        if self._source_pixmap is None:
            self.setText(text)

    def set_pillow_image(self, image, empty_text: str) -> bool:
        """Show an already rendered Pillow image without writing a temporary file."""
        self._empty_text = empty_text
        if image is None:
            self._clear_source()
            return False
        try:
            pixmap = QPixmap.fromImage(ImageQt(image.convert("RGBA")))
        except (AttributeError, ValueError, TypeError):
            self._clear_source()
            return False
        if pixmap.isNull():
            self._clear_source()
            return False
        self._source_pixmap = pixmap
        self._source_signature = None
        self.setText("")
        self._render_source()
        return True

    def invalidate(self) -> None:
        """Forget the current file signature so an atomic replacement is reloaded."""
        self._clear_source()

    def _clear_source(self) -> None:
        self._source_pixmap = None
        self._source_signature = None
        self.clear()
        self.setText(self._empty_text)

    def _render_source(self) -> None:
        if self._source_pixmap is None:
            return
        available = self.contentsRect().size()
        if available.width() <= 0 or available.height() <= 0:
            return
        self.setPixmap(self._source_pixmap.scaled(
            available,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_source()


class PortraitEditorView(QGraphicsView):
    """Maps Qt view input onto the fixed 320×560 editor reference scene."""

    state_changed = Signal(object)
    crop_applied = Signal(object)
    MODE_PAN = "pan"
    MODE_CROP = "crop"

    def __init__(self, state: PortraitEditorState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor_scene = QGraphicsScene(self)
        self.setScene(self._editor_scene)
        self._initial_state = portrait_editor_transform(state)
        self.state = self._initial_state
        try:
            with Image.open(self.state.source_path) as raw:
                self._initial_image = ImageOps.exif_transpose(raw).convert("RGB").copy()
        except (OSError, ValueError) as exc:
            raise ValueError(f"Ungültiges Portrait: {self.state.source_path}") from exc
        if self._initial_image.size != self.state.source_size:
            raise ValueError(f"Portraitgröße wurde geändert: {self.state.source_path}")
        self._working_image = self._initial_image.copy()
        self._source_pixmap = self._pixmap_from_image(self._working_image)
        self._pixmap_item = QGraphicsPixmapItem(self._source_pixmap)
        self._pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._editor_scene.addItem(self._pixmap_item)
        self._selection_item = QGraphicsRectItem()
        selection_pen = QPen(Qt.GlobalColor.yellow)
        selection_pen.setWidth(2)
        self._selection_item.setPen(selection_pen)
        self._selection_item.setZValue(10.0)
        self._selection_item.hide()
        self._editor_scene.addItem(self._selection_item)
        width, height = PORTRAIT_EDITOR_PREVIEW_SIZE
        self._reference_scene_rect = QRectF(0.0, 0.0, float(width), float(height))
        self._editor_scene.setSceneRect(self._reference_scene_rect)
        self.setSceneRect(self._reference_scene_rect)
        self.setObjectName("portraitEditorView")
        self.setMinimumSize(300, 420)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self.mode = self.MODE_PAN
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start_scene: QPointF | None = None
        self._drag_start_state: PortraitEditorState | None = None
        self._crop_start_scene: QPointF | None = None
        self._crop_selection: tuple[float, float, float, float] | None = None
        self.last_source_crop_box: tuple[int, int, int, int] | None = None
        self._render_state()
        self._fit_reference_scene()

    @property
    def source_pixmap(self) -> QPixmap:
        return self._source_pixmap

    @property
    def working_image(self):
        return self._working_image

    @staticmethod
    def _pixmap_from_image(image) -> QPixmap:
        pixmap = QPixmap.fromImage(ImageQt(image))
        if pixmap.isNull():
            raise ValueError("Ungültiges Portraitbild.")
        return pixmap

    def set_state(self, state: PortraitEditorState, *, emit: bool = True) -> None:
        self.state = portrait_editor_transform(state)
        self._render_state()
        if emit:
            self.state_changed.emit(self.state)

    def set_mode(self, mode: str) -> None:
        self.mode = self.MODE_CROP if mode == self.MODE_CROP else self.MODE_PAN
        self._drag_start_scene = None
        self._drag_start_state = None
        self._crop_start_scene = None
        self._clear_crop_selection()
        self.setCursor(
            Qt.CursorShape.CrossCursor
            if self.mode == self.MODE_CROP else Qt.CursorShape.OpenHandCursor
        )

    def reset_editor(self) -> None:
        self._working_image = self._initial_image.copy()
        self._replace_source_pixmap()
        self.last_source_crop_box = None
        self.set_mode(self.MODE_PAN)
        self.set_state(self._initial_state.reset())

    def source_crop_box_for_selection(
            self, selection: tuple[float, float, float, float],
    ) -> tuple[int, int, int, int]:
        return portrait_editor_crop_box(self.state, selection)

    def _replace_source_pixmap(self) -> None:
        self._source_pixmap = self._pixmap_from_image(self._working_image)
        self._pixmap_item.setPixmap(self._source_pixmap)

    def _update_crop_selection(self, current_scene: QPointF) -> None:
        if self._crop_start_scene is None:
            return
        width, height = PORTRAIT_EDITOR_PREVIEW_SIZE
        self._crop_selection = portrait_selection_rect(
            self._crop_start_scene.x(), self._crop_start_scene.y(),
            current_scene.x(), current_scene.y(), width, height,
        )
        x1, y1, x2, y2 = self._crop_selection
        self._selection_item.setRect(QRectF(x1, y1, x2 - x1, y2 - y1))
        self._selection_item.show()

    def _clear_crop_selection(self) -> None:
        self._crop_selection = None
        self._selection_item.hide()

    def _apply_crop_selection(self) -> bool:
        if self._crop_selection is None:
            return False
        x1, y1, x2, y2 = self._crop_selection
        if x2 - x1 < 20.0 or y2 - y1 < 35.0:
            self._clear_crop_selection()
            return False
        source_box = self.source_crop_box_for_selection(self._crop_selection)
        self._working_image = self._working_image.crop(source_box).copy()
        self._replace_source_pixmap()
        self.last_source_crop_box = source_box
        self._clear_crop_selection()
        self.state = PortraitEditorState(
            source_path=self.state.source_path,
            source_size=self._working_image.size,
            zoom=1.0,
            offset_x=0.0,
            offset_y=0.0,
            initial_zoom=self._initial_state.initial_zoom,
            initial_offset_x=self._initial_state.initial_offset_x,
            initial_offset_y=self._initial_state.initial_offset_y,
        )
        self.set_mode(self.MODE_PAN)
        self.set_state(self.state)
        self.crop_applied.emit(source_box)
        return True

    def pan_by_scene_delta(self, delta_x: float, delta_y: float,
                           *, base_state: PortraitEditorState | None = None) -> None:
        """Pan in canonical scene units; useful for events and deterministic tests."""
        self.set_state(portrait_editor_pan(
            base_state or self.state, float(delta_x), float(delta_y),
        ))

    def zoom_by_step(self, direction: int) -> None:
        if direction == 0:
            return
        delta = PORTRAIT_EDITOR_ZOOM_STEP if direction > 0 else -PORTRAIT_EDITOR_ZOOM_STEP
        self.set_state(portrait_editor_zoom(self.state, delta))

    def _render_state(self) -> None:
        scale, width, height, _max_x, _max_y = portrait_editor_geometry(self.state)
        self._pixmap_item.setScale(scale)
        viewport_width, viewport_height = PORTRAIT_EDITOR_PREVIEW_SIZE
        self._pixmap_item.setPos(
            (viewport_width - width) / 2.0 + self.state.offset_x,
            (viewport_height - height) / 2.0 + self.state.offset_y,
        )

    def _fit_reference_scene(self) -> None:
        self.fitInView(self._reference_scene_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_reference_scene()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode == self.MODE_CROP:
                self._crop_start_scene = self.mapToScene(event.position().toPoint())
                self._update_crop_selection(self._crop_start_scene)
                event.accept()
                return
            self._drag_start_scene = self.mapToScene(event.position().toPoint())
            self._drag_start_state = self.state
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.mode == self.MODE_CROP and self._crop_start_scene is not None:
            self._update_crop_selection(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
        if self._drag_start_scene is not None and self._drag_start_state is not None:
            current_scene = self.mapToScene(event.position().toPoint())
            delta = current_scene - self._drag_start_scene
            self.pan_by_scene_delta(
                delta.x(), delta.y(), base_state=self._drag_start_state,
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if (event.button() == Qt.MouseButton.LeftButton
                and self.mode == self.MODE_CROP
                and self._crop_start_scene is not None):
            self._update_crop_selection(self.mapToScene(event.position().toPoint()))
            self._crop_start_scene = None
            self._apply_crop_selection()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_scene is not None:
            self.mouseMoveEvent(event)
            self._drag_start_scene = None
            self._drag_start_state = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        self.zoom_by_step(event.angleDelta().y())
        event.accept()


class PortraitEditorDialogQt(QDialog):
    """Qt portrait editor whose final output is rendered by the shared core."""

    def __init__(self, character_name: str, state: PortraitEditorState,
                 destination: Path | str,
                 on_saved: Callable[[Path], None] | None = None,
                 on_calibrated: Callable[[dict, Path], None] | None = None,
                 window_title: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.character_name = str(character_name)
        self.state = state
        self.destination = Path(destination)
        self.on_saved = on_saved
        self.on_calibrated = on_calibrated
        self._calibration_source_size = tuple(state.source_size)
        self._calibration_current_size = tuple(state.source_size)
        self._calibration_box = (
            0.0, 0.0, float(state.source_size[0]), float(state.source_size[1])
        )
        self.setObjectName("portraitEditorDialog")
        self.setWindowTitle(
            window_title or tr("grabber.edit_portrait_for_name", name=self.character_name)
        )
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(460, 650)

        layout = QVBoxLayout(self)
        character_label = QLabel(self.character_name)
        character_label.setObjectName("portraitEditorCharacterLabel")
        character_font = character_label.font()
        character_font.setBold(True)
        character_label.setFont(character_font)
        layout.addWidget(character_label)

        self.help_label = QLabel(tr("grabber.portrait_editor_pan_help"))
        self.help_label.setObjectName("portraitEditorHelpLabel")
        self.help_label.setWordWrap(True)
        layout.addWidget(self.help_label)

        self.preview = PortraitEditorView(self.state)
        self.preview.state_changed.connect(self._state_changed)
        self.preview.crop_applied.connect(self._crop_applied)
        layout.addWidget(self.preview, 1)

        tool_row = QHBoxLayout()
        tool_row.addWidget(QLabel(tr("grabber.portrait_editor_tool")))
        self.pan_mode_button = QRadioButton(tr("grabber.portrait_editor_pan_zoom"))
        self.pan_mode_button.setObjectName("portraitEditorPanModeButton")
        self.pan_mode_button.setChecked(True)
        self.pan_mode_button.toggled.connect(self._mode_changed)
        tool_row.addWidget(self.pan_mode_button)
        self.crop_mode_button = QRadioButton(tr("grabber.portrait_editor_crop"))
        self.crop_mode_button.setObjectName("portraitEditorCropModeButton")
        self.crop_mode_button.toggled.connect(self._mode_changed)
        tool_row.addWidget(self.crop_mode_button)
        tool_row.addStretch(1)
        layout.addLayout(tool_row)

        state_form = QFormLayout()
        self.zoom_value = QLabel()
        self.offset_x_value = QLabel()
        self.offset_y_value = QLabel()
        state_form.addRow(tr("common.zoom"), self.zoom_value)
        state_form.addRow(tr("grabber.portrait_editor_offset_x"), self.offset_x_value)
        state_form.addRow(tr("grabber.portrait_editor_offset_y"), self.offset_y_value)
        layout.addLayout(state_form)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setObjectName("portraitEditorZoomSlider")
        self.zoom_slider.setRange(
            round(PORTRAIT_EDITOR_ZOOM_RANGE[0] * 100),
            round(PORTRAIT_EDITOR_ZOOM_RANGE[1] * 100),
        )
        self.zoom_slider.setSingleStep(round(PORTRAIT_EDITOR_ZOOM_STEP * 100))
        self.zoom_slider.valueChanged.connect(self._slider_zoom_changed)
        layout.addWidget(self.zoom_slider)

        buttons = QHBoxLayout()
        self.reset_button = QPushButton(tr("common.reset"))
        self.reset_button.setObjectName("portraitEditorResetButton")
        self.reset_button.clicked.connect(self._reset_state)
        buttons.addWidget(self.reset_button)
        buttons.addStretch(1)
        self.apply_button = QPushButton(tr("common.apply"))
        self.apply_button.setObjectName("portraitEditorApplyButton")
        self.apply_button.clicked.connect(self._save)
        self.apply_button.setDefault(True)
        buttons.addWidget(self.apply_button)
        self.cancel_button = QPushButton(tr("common.cancel"))
        self.cancel_button.setObjectName("portraitEditorCancelButton")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self._refresh_state_values()

    def _reset_state(self) -> None:
        self.preview.reset_editor()
        self.pan_mode_button.setChecked(True)
        self.help_label.setText(tr("grabber.portrait_editor_pan_help"))

    def _mode_changed(self) -> None:
        mode = (
            PortraitEditorView.MODE_CROP
            if self.crop_mode_button.isChecked()
            else PortraitEditorView.MODE_PAN
        )
        self.preview.set_mode(mode)
        self.help_label.setText(tr(
            "grabber.portrait_editor_crop_help"
            if mode == PortraitEditorView.MODE_CROP
            else "grabber.portrait_editor_pan_help"
        ))

    def _compose_calibration_box(self, source_box) -> tuple[float, float, float, float]:
        base_left, base_top, base_right, base_bottom = self._calibration_box
        current_width, current_height = self._calibration_current_size
        left, top, right, bottom = source_box
        base_width = base_right - base_left
        base_height = base_bottom - base_top
        return (
            base_left + (left / current_width) * base_width,
            base_top + (top / current_height) * base_height,
            base_left + (right / current_width) * base_width,
            base_top + (bottom / current_height) * base_height,
        )

    def _crop_applied(self, source_box) -> None:
        if callable(self.on_calibrated):
            self._calibration_box = self._compose_calibration_box(source_box)
            self._calibration_current_size = (
                max(1, int(source_box[2] - source_box[0])),
                max(1, int(source_box[3] - source_box[1])),
            )
        self.pan_mode_button.setChecked(True)
        self.help_label.setText(tr("grabber.portrait_editor_crop_applied"))

    def _slider_zoom_changed(self, value: int) -> None:
        self.preview.set_state(portrait_editor_transform(
            self.state, zoom=float(value) / 100.0,
        ))

    def _state_changed(self, state: PortraitEditorState) -> None:
        self.state = state
        self._refresh_state_values()

    def _refresh_state_values(self) -> None:
        self.zoom_value.setText(f"{self.state.zoom:.2f}×")
        self.offset_x_value.setText(f"{self.state.offset_x:.2f}")
        self.offset_y_value.setText(f"{self.state.offset_y:.2f}")
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(round(self.state.zoom * 100))
        self.zoom_slider.blockSignals(False)

    def _save(self) -> None:
        try:
            saved_path = save_portrait_editor_image(
                self.preview.working_image,
                self.destination,
                self.state.zoom,
                self.state.offset_x,
                self.state.offset_y,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                tr("grabber.edit_portrait"),
                tr("grabber.manual_portrait_error", error=exc),
            )
            return
        if callable(self.on_saved):
            self.on_saved(saved_path)
        if callable(self.on_calibrated):
            visible_box = portrait_editor_crop_box(
                self.state,
                (0.0, 0.0, *map(float, PORTRAIT_EDITOR_PREVIEW_SIZE)),
            )
            left, top, right, bottom = self._compose_calibration_box(visible_box)
            source_width, source_height = self._calibration_source_size
            self.on_calibrated(clamp_crop({
                "x1": left / source_width,
                "y1": top / source_height,
                "x2": right / source_width,
                "y2": bottom / source_height,
            }), saved_path)
        self.accept()


class GravestoneEditorView(QGraphicsView):
    """Scalable view whose input is always reported in fixed render coordinates."""

    drag_started = Signal()
    dragged = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor_scene = QGraphicsScene(self)
        self.setScene(self._editor_scene)
        width, height = GRAVESTONE_CARD_SIZE
        self._reference_rect = QRectF(0.0, 0.0, float(width), float(height))
        self._editor_scene.setSceneRect(self._reference_rect)
        self.setSceneRect(self._reference_rect)
        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._editor_scene.addItem(self._pixmap_item)
        self._message_item = self._editor_scene.addText("")
        self._message_item.setDefaultTextColor(Qt.GlobalColor.lightGray)
        self._message_item.setZValue(1.0)
        self._message_item.hide()
        self._drag_start_scene: QPointF | None = None
        self.setObjectName("gravestoneEditorPreview")
        self.setMinimumSize(300, 410)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._fit_reference_scene()

    def set_pillow_image(self, image, empty_text: str) -> bool:
        if image is None:
            self._pixmap_item.setPixmap(QPixmap())
            self._show_message(empty_text)
            return False
        try:
            pixmap = QPixmap.fromImage(ImageQt(image.convert("RGBA")))
        except (AttributeError, TypeError, ValueError):
            self._pixmap_item.setPixmap(QPixmap())
            self._show_message(empty_text)
            return False
        if pixmap.isNull():
            self._pixmap_item.setPixmap(QPixmap())
            self._show_message(empty_text)
            return False
        self._message_item.hide()
        self._pixmap_item.setPixmap(pixmap)
        self._fit_reference_scene()
        return True

    def _show_message(self, text: str) -> None:
        self._message_item.setPlainText(str(text or ""))
        bounds = self._message_item.boundingRect()
        self._message_item.setPos(
            (self._reference_rect.width() - bounds.width()) / 2.0,
            (self._reference_rect.height() - bounds.height()) / 2.0,
        )
        self._message_item.show()

    def _fit_reference_scene(self) -> None:
        self.fitInView(self._reference_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _event_scene_position(self, event) -> QPointF:
        inverse, invertible = self.viewportTransform().inverted()
        if not invertible:
            return QPointF()
        return inverse.map(event.position())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_reference_scene()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_scene = self._event_scene_position(event)
            self.drag_started.emit()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start_scene is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            current_scene = self._event_scene_position(event)
            delta = current_scene - self._drag_start_scene
            self.dragged.emit(float(delta.x()), float(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_scene is not None:
            self.mouseMoveEvent(event)
            self._drag_start_scene = None
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        # Der Tk-Referenzeditor zoomt ausschließlich über den Regler.
        event.ignore()


class GravestoneEditorDialogQt(QDialog):
    """Unified editor with a volatile draft and one explicit persistence action."""

    save_requested = Signal()

    def __init__(self, member: Member, state: GravestoneEditorState,
                 templates_by_id: dict[str, object], candidate_ids: Sequence[str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.member = member
        self.state = state
        self.templates_by_id = dict(templates_by_id)
        self.candidate_ids = [
            str(template_id) for template_id in candidate_ids
            if str(template_id) in self.templates_by_id
        ]
        self._filtered_template_ids: list[str] = []
        self._template_frame_cache: dict[str, object] = {}
        self._template_opening_cache: dict[str, object] = {}
        self._portrait_image = None
        if self.state.portrait_path is not None:
            try:
                with Image.open(self.state.portrait_path) as raw:
                    self._portrait_image = ImageOps.exif_transpose(raw).convert("RGBA").copy()
            except (OSError, ValueError):
                pass
        self._drag_origin = self.state.draft
        self.setObjectName("gravestoneEditorDialog")
        self.setWindowTitle(tr("grabber.gravestone_editor_title", name=member.name))
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(640, 900)

        layout = QVBoxLayout(self)
        self.help_label = QLabel(tr("grabber.gravestone_editor_state_help"))
        self.help_label.setObjectName("gravestoneEditorHelpLabel")
        self.help_label.setWordWrap(True)
        layout.addWidget(self.help_label)

        state_form = QFormLayout()
        self.saved_template_value = QLabel()
        self.saved_template_value.setObjectName("gravestoneEditorSavedTemplateValue")
        self.draft_template_value = QLabel()
        self.draft_template_value.setObjectName("gravestoneEditorDraftTemplateValue")
        self.draft_category_value = QLabel()
        self.draft_category_value.setObjectName("gravestoneEditorDraftCategoryValue")
        self.draft_geometry_value = QLabel()
        self.draft_geometry_value.setObjectName("gravestoneEditorDraftGeometryValue")
        state_form.addRow(
            tr("grabber.gravestone_editor_saved_template"), self.saved_template_value,
        )
        state_form.addRow(
            tr("grabber.gravestone_editor_draft_template"), self.draft_template_value,
        )
        state_form.addRow(tr("common.category"), self.draft_category_value)
        state_form.addRow(
            tr("grabber.gravestone_editor_portrait_preset"), self.draft_geometry_value,
        )
        layout.addLayout(state_form)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(tr("grabber.gravestone_category_filter")))
        self.category_filter_combo = QComboBox()
        self.category_filter_combo.setObjectName("gravestoneEditorCategoryFilterCombo")
        self.category_filter_combo.addItem(
            tr("common.all"), GRAVESTONE_CATEGORY_FILTER_ALL,
        )
        for category in GRAVESTONE_CATEGORIES:
            self.category_filter_combo.addItem(
                gravestone_category_display(category), category,
            )
        self.category_filter_combo.currentIndexChanged.connect(
            self._category_filter_changed
        )
        filter_row.addWidget(self.category_filter_combo, 1)
        layout.addLayout(filter_row)

        template_row = QHBoxLayout()
        self.previous_button = QPushButton("◀")
        self.previous_button.setObjectName("gravestoneEditorPreviousButton")
        self.previous_button.clicked.connect(lambda: self._step_template(-1))
        template_row.addWidget(self.previous_button)
        self.template_combo = QComboBox()
        self.template_combo.setObjectName("gravestoneEditorTemplateCombo")
        self.template_combo.currentIndexChanged.connect(self._template_changed)
        template_row.addWidget(self.template_combo, 1)
        self.next_button = QPushButton("▶")
        self.next_button.setObjectName("gravestoneEditorNextButton")
        self.next_button.clicked.connect(lambda: self._step_template(1))
        template_row.addWidget(self.next_button)
        layout.addLayout(template_row)

        self.preview_status_label = QLabel()
        self.preview_status_label.setObjectName("gravestoneEditorPreviewStatusLabel")
        self.preview_status_label.setWordWrap(True)
        layout.addWidget(self.preview_status_label)
        self.preview = GravestoneEditorView()
        self.preview.drag_started.connect(self._begin_geometry_drag)
        self.preview.dragged.connect(self._drag_geometry)
        layout.addWidget(self.preview, 1)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel(tr("common.edit")))
        self.portrait_target_button = QRadioButton(tr("graveyard.move_portrait"))
        self.portrait_target_button.setObjectName("gravestoneEditorPortraitTarget")
        self.portrait_target_button.setChecked(True)
        target_row.addWidget(self.portrait_target_button)
        self.text_target_button = QRadioButton(tr("graveyard.move_text"))
        self.text_target_button.setObjectName("gravestoneEditorTextTarget")
        target_row.addWidget(self.text_target_button)
        target_row.addStretch(1)
        layout.addLayout(target_row)

        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel(tr("graveyard.zoom")))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setObjectName("gravestoneEditorZoomSlider")
        self.zoom_slider.setRange(
            round(GRAVESTONE_PORTRAIT_ZOOM_RANGE[0] * 100),
            round(GRAVESTONE_PORTRAIT_ZOOM_RANGE[1] * 100),
        )
        self.zoom_slider.valueChanged.connect(self._portrait_zoom_changed)
        zoom_row.addWidget(self.zoom_slider, 1)
        self.zoom_value_label = QLabel()
        self.zoom_value_label.setObjectName("gravestoneEditorZoomValue")
        self.zoom_value_label.setMinimumWidth(50)
        zoom_row.addWidget(self.zoom_value_label)
        layout.addLayout(zoom_row)

        text_scale_row = QHBoxLayout()
        text_scale_row.addWidget(QLabel(tr("graveyard.text_scale")))
        self.text_scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.text_scale_slider.setObjectName("gravestoneEditorTextScaleSlider")
        self.text_scale_slider.setRange(
            round(GRAVESTONE_TEXT_SCALE_RANGE[0] * 100),
            round(GRAVESTONE_TEXT_SCALE_RANGE[1] * 100),
        )
        self.text_scale_slider.valueChanged.connect(self._text_scale_changed)
        text_scale_row.addWidget(self.text_scale_slider, 1)
        self.text_scale_value_label = QLabel()
        self.text_scale_value_label.setObjectName("gravestoneEditorTextScaleValue")
        self.text_scale_value_label.setMinimumWidth(50)
        text_scale_row.addWidget(self.text_scale_value_label)
        layout.addLayout(text_scale_row)

        date_row = QHBoxLayout()
        date_row.addWidget(QLabel(tr("graveyard.death_date_label")))
        date_row.addStretch(1)
        date_format_label = QLabel(tr("graveyard.death_date_format"))
        date_row.addWidget(date_format_label)
        self.death_date_edit = QLineEdit()
        self.death_date_edit.setObjectName("gravestoneEditorDeathDateEdit")
        self.death_date_edit.setMaximumWidth(145)
        self.death_date_edit.textChanged.connect(self._death_date_changed)
        date_row.addWidget(self.death_date_edit)
        layout.addLayout(date_row)

        self.draft_notice_label = QLabel(tr("grabber.gravestone_editor_draft_notice"))
        self.draft_notice_label.setObjectName("gravestoneEditorDraftNoticeLabel")
        self.draft_notice_label.setWordWrap(True)
        layout.addWidget(self.draft_notice_label)
        self.save_status_label = QLabel()
        self.save_status_label.setObjectName("gravestoneEditorSaveStatusLabel")
        self.save_status_label.setWordWrap(True)
        layout.addWidget(self.save_status_label)

        buttons = QHBoxLayout()
        self.reset_button = QPushButton(tr("common.reset"))
        self.reset_button.setObjectName("gravestoneEditorResetButton")
        self.reset_button.clicked.connect(self._reset_draft)
        buttons.addWidget(self.reset_button)
        buttons.addStretch(1)
        self.cancel_button = QPushButton(tr("common.cancel"))
        self.cancel_button.setObjectName("gravestoneEditorCancelButton")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        self.save_button = QPushButton(tr("common.apply"))
        self.save_button.setObjectName("gravestoneEditorSaveButton")
        self.save_button.clicked.connect(self.save_requested.emit)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)

        self._refresh_template_options(self.state.draft.template_id)
        self._sync_controls_from_draft()
        self._refresh_preview()

    def _refresh_template_options(self, preferred_template_id: str | None = None) -> None:
        category_filter = self.category_filter_combo.currentData()
        self._filtered_template_ids = [
            template_id for template_id in self.candidate_ids
            if (
                category_filter == GRAVESTONE_CATEGORY_FILTER_ALL
                or normalize_gravestone_category(
                    self.templates_by_id[template_id].category
                ) == category_filter
            )
        ]
        selected_id = str(preferred_template_id or "")
        if selected_id not in self._filtered_template_ids:
            selected_id = (
                self._filtered_template_ids[0]
                if self._filtered_template_ids else ""
            )
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        for template_id in self._filtered_template_ids:
            template = self.templates_by_id[template_id]
            self.template_combo.addItem(
                f"{template.filename} · {gravestone_category_display(template.category)}",
                template_id,
            )
        self.template_combo.setCurrentIndex(self.template_combo.findData(selected_id))
        self.template_combo.blockSignals(False)
        has_navigation = len(self._filtered_template_ids) > 1
        self.template_combo.setEnabled(bool(self._filtered_template_ids))
        self.previous_button.setEnabled(has_navigation)
        self.next_button.setEnabled(has_navigation)
        if selected_id and selected_id != self.state.draft.template_id:
            self.state = self.state.select_template(selected_id)
            self._sync_controls_from_draft()

    def _category_filter_changed(self, _index: int) -> None:
        self._refresh_template_options(self.state.draft.template_id)
        self._refresh_preview()

    def _template_changed(self, _index: int) -> None:
        template_id = str(self.template_combo.currentData() or "")
        if not template_id:
            return
        try:
            self.state = self.state.select_template(template_id)
        except ValueError:
            return
        self._sync_controls_from_draft()
        self._refresh_preview()

    def _step_template(self, step: int) -> None:
        if not self._filtered_template_ids or step == 0:
            return
        current_id = str(self.template_combo.currentData() or "")
        try:
            index = self._filtered_template_ids.index(current_id)
        except ValueError:
            index = -1 if step > 0 else 0
        target_id = self._filtered_template_ids[
            (index + step) % len(self._filtered_template_ids)
        ]
        self.template_combo.setCurrentIndex(self.template_combo.findData(target_id))

    def _reset_draft(self) -> None:
        self.state = self.state.reset()
        self._sync_controls_from_draft()
        self._refresh_preview()

    def _sync_controls_from_draft(self) -> None:
        draft = self.state.draft
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(round(normalize_portrait_zoom(draft.portrait_zoom) * 100))
        self.zoom_slider.blockSignals(False)
        self.text_scale_slider.blockSignals(True)
        self.text_scale_slider.setValue(round(normalize_text_scale(draft.text_scale) * 100))
        self.text_scale_slider.blockSignals(False)
        self.death_date_edit.blockSignals(True)
        self.death_date_edit.setText(draft.death_date)
        self.death_date_edit.blockSignals(False)
        self.zoom_value_label.setText(f"{draft.portrait_zoom:.2f}×")
        self.text_scale_value_label.setText(f"{draft.text_scale:.2f}×")

    def _update_draft(self, **changes) -> None:
        self.state = replace(
            self.state,
            draft=replace(self.state.draft, **changes),
        )
        self._sync_controls_from_draft()
        self._refresh_preview()

    def _portrait_zoom_changed(self, value: int) -> None:
        self._update_draft(portrait_zoom=normalize_portrait_zoom(value / 100.0))

    def _text_scale_changed(self, value: int) -> None:
        self._update_draft(text_scale=normalize_text_scale(value / 100.0))

    def _death_date_changed(self, value: str) -> None:
        self._update_draft(death_date=str(value))

    def _begin_geometry_drag(self) -> None:
        self._drag_origin = self.state.draft

    def _frame_for_template(self, template_id: str):
        frame = self._template_frame_cache.get(template_id)
        if frame is None:
            template = self.templates_by_id.get(template_id)
            if template is None:
                raise ValueError(f"Unbekannter Grabstein: {template_id}")
            frame = prepare_gravestone_template(template.path, GRAVESTONE_CARD_SIZE)
            self._template_frame_cache[template_id] = frame
        return frame

    def _opening_for_template(self, template_id: str):
        opening = self._template_opening_cache.get(template_id)
        if opening is None:
            opening = detect_gravestone_portrait_opening(
                self._frame_for_template(template_id)
            )
            self._template_opening_cache[template_id] = opening
        return opening

    def _drag_geometry(self, delta_x: float, delta_y: float) -> None:
        """Apply scene-space deltas to the draft; widget pixels never enter state."""
        origin = self._drag_origin
        if origin.template_id != self.state.draft.template_id:
            return
        if self.text_target_button.isChecked():
            offset_x, offset_y = shifted_text_offsets(
                origin.text_offset_x,
                origin.text_offset_y,
                delta_x,
                delta_y,
                GRAVESTONE_CARD_SIZE,
            )
            self._update_draft(text_offset_x=offset_x, text_offset_y=offset_y)
            return
        try:
            left, top, right, bottom = self._opening_for_template(
                origin.template_id
            ).box
        except (OSError, RuntimeError, TypeError, ValueError):
            return
        offset_x, offset_y = shifted_portrait_offsets(
            origin.portrait_offset_x,
            origin.portrait_offset_y,
            delta_x,
            delta_y,
            (right - left, bottom - top),
        )
        self._update_draft(portrait_offset_x=offset_x, portrait_offset_y=offset_y)

    def render_draft(self):
        """Render the current draft or raise so persistence cannot accept bad output."""
        draft = self.state.draft
        template = self.templates_by_id.get(draft.template_id)
        if template is None:
            raise ValueError(tr("grabber.graveyard_stone_not_manifest"))
        frame = self._frame_for_template(draft.template_id)
        return render_gravestone_card(
            self.state.member_for_render(self.member),
            frame,
            self.state.portrait_path,
            GRAVESTONE_CARD_SIZE,
            template.default_text_safe_area,
            portrait_image=self._portrait_image,
        )

    def show_save_error(self, message: str) -> None:
        self.save_status_label.setText(str(message))

    def _refresh_preview(self) -> None:
        self.save_status_label.clear()
        draft = self.state.draft
        template = self.templates_by_id.get(draft.template_id)
        saved_name = self.state.saved.template_filename or tr("grabber.graveyard_no_stone")
        self.saved_template_value.setText(saved_name)
        self.draft_template_value.setText(
            draft.template_filename or tr("grabber.graveyard_no_stone")
        )
        self.draft_category_value.setText(
            gravestone_category_display(draft.category)
            if draft.category else tr("common.not_set")
        )
        self.draft_geometry_value.setText(
            tr(
                "grabber.gravestone_editor_preset_values",
                x=f"{draft.portrait_offset_x:.2f}",
                y=f"{draft.portrait_offset_y:.2f}",
                zoom=f"{draft.portrait_zoom:.2f}",
            )
        )
        if template is None:
            self.preview.set_pillow_image(
                None, tr("grabber.graveyard_stone_not_manifest")
            )
            self.preview_status_label.setText(
                tr("grabber.graveyard_stone_not_manifest")
            )
            return
        try:
            card = self.render_draft()
        except (OSError, RuntimeError, TypeError, ValueError):
            card = None
        rendered = self.preview.set_pillow_image(
            card, tr("grabber.preview_unavailable", error="")
        )
        self.preview_status_label.setText(
            tr(
                "grabber.graveyard_preview_candidate",
                stone=template.filename,
                category=gravestone_category_display(template.category),
            ) if rendered else tr("grabber.preview_unavailable", error="")
        )


class GuildPortraitGrabberQt(QMainWindow):
    """Qt-Grabber mit Projekt-, Charakter- und Armory-Workflow."""

    def __init__(self, project_path: str | Path | None = None,
                 session_id: str | None = None,
                 worker_factory: Callable[[queue.Queue], object] | None = None,
                 config_data: dict | None = None) -> None:
        super().__init__()
        self.setStyleSheet(GRABBER_INTERACTION_STYLE)
        self.project_path: Path | None = None
        self.project_payload: dict | None = None
        self.project_error: str | None = None
        self.session_id = str(session_id or "").strip() or None
        self.handoff_path: Path | None = None
        self._session_project_path: Path | None = None
        self.project_model: GuildModel | None = None
        self.v2_mode = False
        self.v2_store = None
        self.active_character_members: list[Member] = []
        self.inactive_character_members: list[Member] = []
        self.character_members: list[Member] = []
        self._portrait_list_mode = "active"
        self._member_by_id: dict[str, Member] = {}
        self.selected_character_id: str | None = None
        self.graveyard_members: list[Member] = []
        self._graveyard_member_by_id: dict[str, Member] = {}
        self.selected_graveyard_member_id: str | None = None
        self._graveyard_inventory = None
        self._graveyard_templates_by_id: dict[str, object] = {}
        self.config_data = dict(load_config() if config_data is None else config_data)
        self.events: queue.Queue = queue.Queue()
        self.armory_results: dict[str, dict] = {}
        self._active_worker_action: str | None = None
        self._active_worker_member_id: str | None = None
        self._active_worker_project_path: Path | None = None
        self._last_worker_event: dict | None = None
        self._worker_closed = False
        self._portrait_editor_dialog: PortraitEditorDialogQt | None = None
        self._gravestone_editor_dialog: GravestoneEditorDialogQt | None = None
        self._batch_names: list[str] = []
        self._batch_member_ids: set[str] = set()
        self._batch_stop_requested = False
        self._worker_cancel_requested = False
        self._armory_url_full = ""
        self._pending_roster_save_token: str | None = None
        self._pending_roster_save_started = 0.0
        self._pending_gravestone_save_token: str | None = None
        self._pending_gravestone_save_started = 0.0
        self._pending_gravestone_save_member_id: str | None = None
        self._pending_gravestone_save_project_path: Path | None = None
        self.last_event_thread_id: int | None = None
        self._persist_ui_state = config_data is None
        self._status_clear_timer = QTimer(self)
        self._status_clear_timer.setSingleShot(True)
        self._build_ui()
        self._restore_window_state()
        self.worker = (
            worker_factory(self.events)
            if worker_factory is not None
            else create_portrait_source_worker(
                self.config_data.get("portrait_source"), self.events,
            )
        )
        self.worker.start()
        self.worker_poll_timer = QTimer(self)
        self.worker_poll_timer.setInterval(100)
        self.worker_poll_timer.timeout.connect(self._poll_worker_events)
        self.worker_poll_timer.start()
        if project_path:
            self.load_project(project_path)
        else:
            self.refresh_texts()

    def _build_ui(self) -> None:
        self.setMinimumSize(GRABBER_MINIMUM_SIZE)

        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(8)

        self.banner = GrabberBannerWidget()
        self.banner.setObjectName("grabberBanner")
        root_layout.addWidget(self.banner)

        # Die bestehenden Labels bleiben als zugängliche Statusquelle erhalten,
        # werden aber ausschließlich im Banner dargestellt.
        self.project_status_label = QLabel()
        self.project_status_label.setObjectName("projectStatusLabel")
        self.project_status_label.hide()
        self.project_detail_label = QLabel()
        self.project_detail_label.setObjectName("projectDetailLabel")
        self.project_detail_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.project_detail_label.setWordWrap(False)
        self.project_detail_label.hide()

        self.open_project_button = QPushButton()
        self.open_project_button.setObjectName("openProjectButton")
        self.open_project_button.clicked.connect(self._choose_project)
        self.checker_navigation_button = QPushButton()
        self.checker_navigation_button.setObjectName("checkerNavigationButton")
        self.checker_navigation_button.clicked.connect(self._navigate_to_checker)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("grabberMainTabs")
        self.tabs.tabBar().setExpanding(False)
        self.portraits_page = self._build_portraits_page()
        self.tabs.addTab(self.portraits_page, "")
        self.graveyard_page = self._build_graveyard_page()
        self.tabs.addTab(self.graveyard_page, "")
        self.settings_page = self._build_settings_page()
        self.tabs.addTab(self.settings_page, "")
        self.review_page = QtGravestoneReviewWidget(
            suite_root_dir(),
            parent=self.tabs,
            splitter_sizes=self.config_data.get("qt_review_splitter_sizes"),
        )
        self.tabs.addTab(self.review_page, "")
        navigation_actions = QWidget(self.tabs)
        navigation_layout = QHBoxLayout(navigation_actions)
        navigation_layout.setContentsMargins(0, 0, 0, 0)
        navigation_layout.setSpacing(6)
        navigation_layout.addWidget(self.open_project_button)
        navigation_layout.addWidget(self.checker_navigation_button)
        self.tabs.setCornerWidget(navigation_actions, Qt.Corner.TopRightCorner)
        self.tabs.currentChanged.connect(self._main_tab_changed)
        root_layout.addWidget(self.tabs, 1)

        self.setCentralWidget(central)
        status_bar = self.statusBar()
        status_bar.setSizeGripEnabled(False)
        status_bar.hide()
        status_bar.messageChanged.connect(self._status_message_changed)

    def _available_screens(self):
        return tuple(QGuiApplication.screens())

    @staticmethod
    def _geometry_from_config(value: object) -> QRect | None:
        if not isinstance(value, dict):
            return None
        try:
            geometry = QRect(
                int(value.get("x")), int(value.get("y")),
                int(value.get("width")), int(value.get("height")),
            )
        except (TypeError, ValueError):
            return None
        return geometry if geometry.width() > 0 and geometry.height() > 0 else None

    def _default_window_geometry(self) -> QRect:
        screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else QRect(0, 0, 1440, 900)
        width = max(GRABBER_MINIMUM_SIZE.width(), round(available.width() * GRABBER_INITIAL_RATIO))
        height = max(GRABBER_MINIMUM_SIZE.height(), round(available.height() * GRABBER_INITIAL_RATIO))
        return QRect(
            available.x() + (available.width() - width) // 2,
            available.y() + (available.height() - height) // 2,
            width,
            height,
        )

    def _restore_window_state(self) -> None:
        saved = self._geometry_from_config(self.config_data.get("qt_window_geometry"))
        visible = any(
            saved is not None and saved.intersects(screen.availableGeometry())
            for screen in self._available_screens()
        )
        self.setGeometry(saved if visible else self._default_window_geometry())
        tab_key = str(self.config_data.get("qt_main_tab") or "portraits").casefold()
        if tab_key in {"crop", "ausschnitt"}:
            tab_key = "settings"
        page_by_key = {
            "portraits": self.portraits_page,
            "graveyard": self.graveyard_page,
            "review": self.review_page,
            "settings": self.settings_page,
        }
        page = page_by_key.get(tab_key, self.portraits_page)
        self.tabs.setCurrentIndex(self.tabs.indexOf(page))
        self._restore_portraits_view_state()

    def _main_tab_changed(self, _index: int) -> None:
        if not hasattr(self, "tabs"):
            return
        self.config_data["qt_main_tab"] = self._current_main_tab_key()

    def _current_main_tab_key(self) -> str:
        page = self.tabs.currentWidget()
        return {
            self.portraits_page: "portraits",
            self.graveyard_page: "graveyard",
            self.review_page: "review",
            self.settings_page: "settings",
        }.get(page, "portraits")

    def _save_window_state(self) -> None:
        geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.config_data["qt_window_geometry"] = {
            "x": geometry.x(), "y": geometry.y(),
            "width": geometry.width(), "height": geometry.height(),
        }
        self.config_data["qt_main_tab"] = self._current_main_tab_key()
        if hasattr(self, "character_splitter"):
            self.config_data["qt_portraits_splitter_sizes"] = list(
                self.character_splitter.sizes()
            )
        if hasattr(self, "character_table"):
            self.config_data["qt_portraits_column_widths"] = [
                self.character_table.columnWidth(column) for column in range(5)
            ]
        if hasattr(self, "review_page"):
            review_splitter_sizes = list(self.review_page.workspace_splitter.sizes())
            if len(review_splitter_sizes) == 2 and all(
                value > 0 for value in review_splitter_sizes
            ):
                self.config_data["qt_review_splitter_sizes"] = review_splitter_sizes
        if self._persist_ui_state:
            save_config(self.config_data)

    def _restore_portraits_view_state(self) -> None:
        splitter_sizes = self.config_data.get("qt_portraits_splitter_sizes")
        if (isinstance(splitter_sizes, list) and len(splitter_sizes) == 2
                and all(isinstance(value, int) and value > 0 for value in splitter_sizes)):
            self.character_splitter.setSizes(splitter_sizes)
        else:
            self.character_splitter.setSizes([650, 350])
        column_widths = self.config_data.get("qt_portraits_column_widths")
        if (isinstance(column_widths, list) and len(column_widths) == 5
                and all(isinstance(value, int) and value >= 80 for value in column_widths)):
            for column, width in enumerate(column_widths):
                self.character_table.setColumnWidth(column, width)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_armory_url_label()
        self._arrange_detail_actions()

    def _arrange_detail_actions(self, force: bool = False) -> None:
        if not hasattr(self, "detail_actions_layout"):
            return
        side_by_side = self.character_detail_frame.width() >= 480
        if not force and side_by_side == getattr(self, "_detail_actions_side_by_side", None):
            return
        self._detail_actions_side_by_side = side_by_side
        self.detail_actions_layout.removeWidget(self.character_actions_group)
        self.detail_actions_layout.removeWidget(self.portrait_actions_group)
        if side_by_side:
            self.detail_actions_layout.addWidget(self.character_actions_group, 0, 0)
            self.detail_actions_layout.addWidget(self.portrait_actions_group, 0, 1)
            self.detail_actions_layout.setColumnStretch(0, 1)
            self.detail_actions_layout.setColumnStretch(1, 1)
        else:
            self.detail_actions_layout.addWidget(self.character_actions_group, 0, 0)
            self.detail_actions_layout.addWidget(self.portrait_actions_group, 1, 0)
            self.detail_actions_layout.setColumnStretch(0, 1)
            self.detail_actions_layout.setColumnStretch(1, 0)

    def _status_message_changed(self, message: str) -> None:
        self._status_clear_timer.stop()
        self.statusBar().setVisible(bool(message))
        if message:
            self._status_clear_timer.singleShot(5000, self.statusBar().clearMessage)

    def _navigate_to_checker(self) -> None:
        if self._pending_gravestone_save_token:
            self.statusBar().showMessage(tr("grabber.graveyard_save_handoff"))
            return
        if self.session_id:
            self.close()
            return
        checker = suite_root_dir() / "app" / "GuildGearCheckerQt.py"
        if not checker.is_file():
            QMessageBox.critical(self, APP_NAME, f"Guild Gear Checker fehlt: {checker}")
            return
        try:
            subprocess.Popen([str(sys.executable), str(checker)], cwd=str(suite_root_dir()))
            self.close()
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"Guild Gear Checker konnte nicht gestartet werden: {exc}")

    @staticmethod
    def _scroll_page(object_name: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName(object_name)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(page)
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(10)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        return page, content_layout

    def _build_crop_controls(self) -> tuple[QGroupBox, QGroupBox]:
        """Erzeugt die unveränderten Crop-Controls für die Einstellungen."""
        self.playwright_crop_group = QGroupBox()
        playwright_layout = QVBoxLayout(self.playwright_crop_group)
        self.playwright_crop_help_label = QLabel()
        self.playwright_crop_help_label.setWordWrap(True)
        playwright_layout.addWidget(self.playwright_crop_help_label)
        self.calibrate_crop_button = QPushButton()
        self.calibrate_crop_button.setObjectName("calibrateCropButton")
        self.calibrate_crop_button.clicked.connect(self.calibrate_selected_crop)
        playwright_layout.addWidget(self.calibrate_crop_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.standard_crop_group = QGroupBox()
        standard_layout = QVBoxLayout(self.standard_crop_group)
        self.standard_crop_help_label = QLabel()
        self.standard_crop_help_label.setWordWrap(True)
        standard_layout.addWidget(self.standard_crop_help_label)
        self.screen_region_label = QLabel()
        self.screen_region_label.setObjectName("screenRegionLabel")
        standard_layout.addWidget(self.screen_region_label)
        region_actions = QHBoxLayout()
        self.set_region_button = QPushButton()
        self.set_region_button.setObjectName("setScreenRegionButton")
        self.set_region_button.clicked.connect(self.set_default_screen_region)
        region_actions.addWidget(self.set_region_button)
        self.test_region_button = QPushButton()
        self.test_region_button.setObjectName("testScreenRegionButton")
        self.test_region_button.clicked.connect(self.test_default_screen_region)
        region_actions.addWidget(self.test_region_button)
        self.reset_region_button = QPushButton()
        self.reset_region_button.setObjectName("resetScreenRegionButton")
        self.reset_region_button.clicked.connect(self.reset_default_screen_region)
        region_actions.addWidget(self.reset_region_button)
        region_actions.addStretch(1)
        standard_layout.addLayout(region_actions)
        return self.playwright_crop_group, self.standard_crop_group

    def _build_settings_page(self) -> QWidget:
        page, layout = self._scroll_page("settingsPage")
        settings = portrait_source_settings(self.config_data)

        self.crop_settings_group = QGroupBox()
        crop_layout = QVBoxLayout(self.crop_settings_group)
        playwright_crop, standard_crop = self._build_crop_controls()
        crop_layout.addWidget(playwright_crop)
        crop_layout.addWidget(standard_crop)
        layout.addWidget(self.crop_settings_group)

        self.armory_settings_group = QGroupBox()
        general_form = QFormLayout(self.armory_settings_group)
        self.region_edit = QLineEdit(str(settings.get("region") or "EU"))
        self.region_edit.setObjectName("regionEdit")
        general_form.addRow("Region", self.region_edit)
        self.realm_edit = QLineEdit(str(settings.get("realm") or "stitches"))
        self.realm_edit.setObjectName("realmEdit")
        general_form.addRow("Realm", self.realm_edit)
        self.game_version_edit = QLineEdit(
            str(settings.get("game_version") or "classic1x")
        )
        self.game_version_edit.setObjectName("gameVersionEdit")
        self.game_version_label = QLabel()
        general_form.addRow(self.game_version_label, self.game_version_edit)
        self.guild_name_edit = QLineEdit(str(settings.get("guild_name") or ""))
        self.guild_name_edit.setObjectName("guildNameEdit")
        self.guild_name_edit.setEnabled(False)
        self.guild_name_label = QLabel()
        general_form.addRow(self.guild_name_label, self.guild_name_edit)
        self.capture_mode_combo = QComboBox()
        self.capture_mode_combo.setObjectName("captureModeCombo")
        self.capture_mode_combo.addItem(tr("grabber.mode_playwright"), "playwright")
        self.capture_mode_combo.addItem(
            tr("grabber.mode_standard"), "standard_browser_region"
        )
        initial_mode = str(settings.get("capture_mode") or "playwright")
        self.capture_mode_combo.setCurrentIndex(max(
            0, self.capture_mode_combo.findData(initial_mode)
        ))
        self.capture_mode_combo.currentTextChanged.connect(self._capture_mode_changed)
        general_form.addRow(self.capture_mode_combo)
        self.standard_wait_spin = QDoubleSpinBox()
        self.standard_wait_spin.setObjectName("standardWaitSpin")
        self.standard_wait_spin.setRange(1.0, 60.0)
        self.standard_wait_spin.setSingleStep(0.5)
        try:
            standard_wait = float(settings.get("standard_wait_after_open", 6.0))
        except (TypeError, ValueError):
            standard_wait = 6.0
        self.standard_wait_spin.setValue(max(1.0, min(60.0, standard_wait)))
        self.wait_seconds_label = QLabel()
        general_form.addRow(self.wait_seconds_label, self.standard_wait_spin)
        layout.addWidget(self.armory_settings_group)

        self.general_diagnostics_group = QGroupBox()
        general_layout = QFormLayout(self.general_diagnostics_group)
        output_row = QHBoxLayout()
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setObjectName("outputFolderEdit")
        self.output_folder_edit.setReadOnly(True)
        output_row.addWidget(self.output_folder_edit, 1)
        self.settings_open_project_button = QPushButton()
        self.settings_open_project_button.setObjectName("settingsOpenProjectButton")
        self.settings_open_project_button.clicked.connect(self._choose_project)
        output_row.addWidget(self.settings_open_project_button)
        self.output_folder_label = QLabel()
        general_layout.addRow(self.output_folder_label, output_row)

        self.language_combo = QComboBox()
        self.language_combo.setObjectName("languageCombo")
        self.language_combo.addItems(language_display_values())
        self.language_combo.setCurrentIndex(0 if get_language() == "de" else 1)
        self.language_combo.currentTextChanged.connect(self._language_changed)
        self.language_label = QLabel()
        general_layout.addRow(self.language_label, self.language_combo)

        diagnostics_row = QWidget()
        diagnostics_layout = QHBoxLayout(diagnostics_row)
        diagnostics_layout.setContentsMargins(0, 0, 0, 0)
        self.browser_test_button = QPushButton()
        self.browser_test_button.setObjectName("browserTestButton")
        self.browser_test_button.clicked.connect(self.test_browser)
        diagnostics_layout.addWidget(self.browser_test_button)
        self.browser_order_label = QLabel()
        self.browser_order_label.setWordWrap(True)
        diagnostics_layout.addWidget(self.browser_order_label, 1)
        self.diagnostics_label = QLabel()
        general_layout.addRow(self.diagnostics_label, diagnostics_row)

        self.settings_help_label = QLabel()
        self.settings_help_label.setWordWrap(True)
        general_layout.addRow(self.settings_help_label)
        layout.addWidget(self.general_diagnostics_group)
        layout.addStretch(1)

        for editor in (self.region_edit, self.realm_edit, self.game_version_edit):
            editor.editingFinished.connect(self.save_settings)
        self.standard_wait_spin.editingFinished.connect(self.save_settings)
        self._refresh_screen_region_text()
        self._refresh_settings_project_path()
        self.standard_wait_spin.setEnabled(
            self.capture_mode_combo.currentData() == "standard_browser_region"
        )
        return page

    def _build_portraits_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("portraitsPage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(8, 8, 8, 8)
        self.character_summary_label = QLabel()
        self.character_summary_label.setObjectName("characterSummaryLabel")
        page_layout.addWidget(self.character_summary_label)

        portrait_list_row = QHBoxLayout()
        self.portrait_list_label = QLabel()
        portrait_list_row.addWidget(self.portrait_list_label)
        self.portrait_list_group = QButtonGroup(self)
        self.portrait_list_group.setExclusive(True)
        self.active_portraits_button = QPushButton()
        self.active_portraits_button.setCheckable(True)
        self.active_portraits_button.setProperty("portraitListMode", "active")
        self.inactive_portraits_button = QPushButton()
        self.inactive_portraits_button.setCheckable(True)
        self.inactive_portraits_button.setProperty("portraitListMode", "inactive")
        self.portrait_list_group.addButton(self.active_portraits_button)
        self.portrait_list_group.addButton(self.inactive_portraits_button)
        self.active_portraits_button.setChecked(True)
        portrait_list_row.addWidget(self.active_portraits_button)
        portrait_list_row.addWidget(self.inactive_portraits_button)
        portrait_list_row.addStretch(1)
        self.portrait_list_group.buttonClicked.connect(
            lambda button: self._set_portrait_list_mode(
                str(button.property("portraitListMode") or "active")
            )
        )
        page_layout.addLayout(portrait_list_row)

        self.roster_actions_group = QGroupBox()
        roster_controls = QHBoxLayout(self.roster_actions_group)
        roster_controls.setContentsMargins(8, 4, 8, 6)
        self.add_character_button = QPushButton()
        self.add_character_button.setObjectName("addCharacterButton")
        self.add_character_button.clicked.connect(self.add_character)
        roster_controls.addWidget(self.add_character_button)
        self.remove_character_button = QPushButton()
        self.remove_character_button.setObjectName("removeCharacterButton")
        self.remove_character_button.clicked.connect(self.remove_selected_character)
        roster_controls.addWidget(self.remove_character_button)
        self.import_list_button = QPushButton()
        self.import_list_button.setObjectName("importListButton")
        self.import_list_button.clicked.connect(self.import_character_list)
        roster_controls.addWidget(self.import_list_button)
        self.import_wcl_button = QPushButton()
        self.import_wcl_button.setObjectName("importWclButton")
        self.import_wcl_button.clicked.connect(self.import_wcl_csv)
        self.import_wcl_button.setVisible(False)
        roster_controls.addWidget(self.import_wcl_button)
        self.save_guild_list_button = QPushButton()
        self.save_guild_list_button.setObjectName("saveGuildListButton")
        self.save_guild_list_button.clicked.connect(self.save_guild_list)
        roster_controls.addWidget(self.save_guild_list_button)
        roster_controls.addStretch(1)

        self.batch_actions_group = QGroupBox()
        batch_controls = QHBoxLayout(self.batch_actions_group)
        batch_controls.setContentsMargins(8, 4, 8, 6)
        self.read_missing_data_button = QPushButton()
        self.read_missing_data_button.setObjectName("readMissingDataButton")
        self.read_missing_data_button.clicked.connect(self.read_missing_armory_data)
        batch_controls.addWidget(self.read_missing_data_button)
        self.capture_missing_button = QPushButton()
        self.capture_missing_button.setObjectName("captureMissingButton")
        self.capture_missing_button.clicked.connect(self.capture_missing_portraits)
        batch_controls.addWidget(self.capture_missing_button)
        self.capture_all_button = QPushButton()
        self.capture_all_button.setObjectName("captureAllButton")
        self.capture_all_button.clicked.connect(self.capture_all_portraits)
        batch_controls.addWidget(self.capture_all_button)
        self.stop_batch_button = QPushButton()
        self.stop_batch_button.setObjectName("stopBatchButton")
        self.stop_batch_button.clicked.connect(self.request_batch_stop)
        batch_controls.addWidget(self.stop_batch_button)
        batch_controls.addStretch(1)
        self.top_actions_row = QWidget()
        self.top_actions_row.setObjectName("portraitTopActionsRow")
        top_actions_layout = QHBoxLayout(self.top_actions_row)
        top_actions_layout.setContentsMargins(0, 0, 0, 0)
        top_actions_layout.setSpacing(8)
        self.roster_actions_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.batch_actions_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        top_actions_layout.addWidget(self.roster_actions_group, 1)
        top_actions_layout.addWidget(self.batch_actions_group, 1)
        page_layout.addWidget(self.top_actions_row)

        self.armory_url_label = QLabel()
        self.armory_url_label.setObjectName("armoryUrlLabel")
        self.armory_url_label.setTextFormat(Qt.TextFormat.PlainText)
        self.armory_url_label.setWordWrap(False)
        self.armory_url_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.armory_url_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.armory_url_label.setToolTip("")

        self.worker_status_label = QLabel()
        self.worker_status_label.setObjectName("workerStatusLabel")
        self.worker_status_label.setWordWrap(True)
        page_layout.addWidget(self.worker_status_label)
        self.worker_error_label = QLabel()
        self.worker_error_label.setObjectName("workerErrorLabel")
        self.worker_error_label.setWordWrap(True)
        self.worker_error_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.worker_error_label.hide()
        page_layout.addWidget(self.worker_error_label)

        self.batch_progress_panel = QWidget()
        self.batch_progress_panel.setObjectName("batchProgressPanel")
        batch_progress_layout = QVBoxLayout(self.batch_progress_panel)
        batch_progress_layout.setContentsMargins(0, 4, 0, 0)
        self.batch_progress_label = QLabel()
        self.batch_progress_label.setObjectName("batchProgressLabel")
        batch_progress_layout.addWidget(self.batch_progress_label)
        self.batch_progress = QProgressBar()
        self.batch_progress.setObjectName("batchProgress")
        self.batch_progress.setRange(0, 1)
        self.batch_progress.setValue(0)
        self.batch_progress.setFormat("0 %")
        batch_progress_layout.addWidget(self.batch_progress)
        self.batch_progress_panel.hide()
        self._batch_progress_title = ""

        self.character_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.character_splitter.setObjectName("characterSplitter")

        self.character_model = QStandardItemModel(0, 5, self)
        self.character_table = QTableView()
        self.character_row_hover = install_row_hover(self.character_table)
        self.character_table.setObjectName("characterTable")
        self.character_table.setModel(self.character_model)
        self.character_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.character_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.character_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.character_table.setAlternatingRowColors(True)
        self.character_table.setSortingEnabled(True)
        self.character_table.verticalHeader().setVisible(False)
        header = self.character_table.horizontalHeader()
        header.setMinimumSectionSize(80)
        for column in range(4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for column, width in enumerate((220, 135, 155, 100)):
            self.character_table.setColumnWidth(column, width)
        self.character_table.selectionModel().currentRowChanged.connect(
            self._character_row_changed
        )
        self.character_table.doubleClicked.connect(
            lambda _index: self.open_selected_in_browser()
        )
        self.character_splitter.addWidget(self.character_table)

        detail = QFrame()
        detail.setObjectName("characterDetailFrame")
        self.character_detail_frame = detail
        detail.setFrameShape(QFrame.Shape.StyledPanel)
        detail_layout = QVBoxLayout(detail)
        self.selection_heading_label = QLabel()
        heading_font = self.selection_heading_label.font()
        heading_font.setBold(True)
        self.selection_heading_label.setFont(heading_font)
        detail_layout.addWidget(self.selection_heading_label)

        form = QFormLayout()
        self._detail_form_labels: dict[str, QLabel] = {}
        self.character_name_value = QLabel("-")
        self.character_race_value = QLabel("-")
        self.character_class_icon_label = QLabel("–")
        self.character_class_icon_label.setObjectName("characterClassIcon")
        self.character_class_icon_label.setFixedSize(22, 22)
        self.character_class_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.character_class_value = QLabel("-")
        self.character_class_value.setObjectName("characterClassValue")
        self.character_class_display = QWidget()
        class_display_layout = QHBoxLayout(self.character_class_display)
        class_display_layout.setContentsMargins(0, 0, 0, 0)
        class_display_layout.setSpacing(5)
        class_display_layout.addWidget(self.character_class_icon_label)
        class_display_layout.addWidget(self.character_class_value)
        class_display_layout.addStretch(1)
        self.character_spec_value = QLabel("-")
        self.character_life_value = QLabel("-")
        for key, value in (
            ("name", self.character_name_value),
            ("race", self.character_race_value),
            ("class", self.character_class_value),
            ("life", self.character_life_value),
        ):
            label = QLabel()
            self._detail_form_labels[key] = label
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(
                label,
                self.character_class_display if key == "class" else value,
            )
        detail_layout.addLayout(form)

        self.armory_result_label = QLabel()
        self.armory_result_label.setObjectName("armoryResultLabel")
        self.armory_result_label.setWordWrap(True)
        detail_layout.addWidget(self.armory_result_label)

        self.character_actions_group = QGroupBox()
        self.character_actions_group.setObjectName("characterActionsGroup")
        self.character_actions_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        character_actions = QGridLayout(self.character_actions_group)
        character_actions.setContentsMargins(8, 5, 8, 7)
        character_actions.setHorizontalSpacing(6)
        character_actions.setVerticalSpacing(5)
        self.open_browser_button = QPushButton()
        self.open_browser_button.setObjectName("openBrowserButton")
        self.open_browser_button.clicked.connect(self.open_selected_in_browser)
        character_actions.addWidget(self.open_browser_button, 0, 0)
        self.read_armory_button = QPushButton()
        self.read_armory_button.setObjectName("readArmoryButton")
        self.read_armory_button.clicked.connect(self.read_selected_armory_data)
        character_actions.addWidget(self.read_armory_button, 1, 0)
        self.capture_portrait_button = QPushButton()
        self.capture_portrait_button.setObjectName("capturePortraitButton")
        self.capture_portrait_button.clicked.connect(self.capture_selected_portrait)
        character_actions.addWidget(self.capture_portrait_button, 2, 0)

        self.portrait_status_label = QLabel()
        self.portrait_status_label.setObjectName("portraitStatusLabel")
        detail_layout.addWidget(self.portrait_status_label)
        self.portrait_preview = PortraitPreviewLabel()
        self.portrait_preview.setObjectName("portraitPreview")
        self.portrait_preview.setMinimumSize(120, 120)
        detail_layout.addWidget(self.portrait_preview, 1)
        self.portrait_path_label = QLabel()
        self.portrait_path_label.setObjectName("portraitPathLabel")
        self.portrait_path_label.setWordWrap(True)
        self.portrait_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        detail_layout.addWidget(self.portrait_path_label)
        self.portrait_actions_group = QGroupBox()
        self.portrait_actions_group.setObjectName("portraitActionsGroup")
        self.portrait_actions_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        portrait_actions = QGridLayout(self.portrait_actions_group)
        portrait_actions.setContentsMargins(8, 5, 8, 7)
        portrait_actions.setHorizontalSpacing(6)
        portrait_actions.setVerticalSpacing(5)
        self.import_portrait_button = QPushButton()
        self.import_portrait_button.setObjectName("importPortraitButton")
        self.import_portrait_button.clicked.connect(self.import_selected_portrait)
        portrait_actions.addWidget(self.import_portrait_button, 0, 0)
        self.remove_portrait_button = QPushButton()
        self.remove_portrait_button.setObjectName("removePortraitButton")
        self.remove_portrait_button.clicked.connect(self.remove_selected_portrait)
        portrait_actions.addWidget(self.remove_portrait_button, 2, 0)
        self.edit_portrait_button = QPushButton()
        self.edit_portrait_button.setObjectName("editPortraitButton")
        self.edit_portrait_button.clicked.connect(self.edit_selected_portrait)
        portrait_actions.addWidget(self.edit_portrait_button, 1, 0)
        self.detail_actions_row = QWidget()
        self.detail_actions_layout = QGridLayout(self.detail_actions_row)
        self.detail_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_actions_layout.setHorizontalSpacing(6)
        self.detail_actions_layout.setVerticalSpacing(5)
        detail_layout.insertWidget(
            detail_layout.indexOf(self.portrait_status_label), self.detail_actions_row
        )
        detail_layout.addWidget(self.armory_url_label)
        self._arrange_detail_actions(force=True)
        self.character_splitter.addWidget(detail)
        self.character_splitter.setChildrenCollapsible(False)
        self.character_table.setMinimumWidth(420)
        detail.setMinimumWidth(360)
        self.character_splitter.setStretchFactor(0, 65)
        self.character_splitter.setStretchFactor(1, 35)
        self.character_splitter.setSizes([650, 350])
        page_layout.addWidget(self.character_splitter, 1)
        page_layout.addWidget(self.batch_progress_panel)
        return page

    def _build_graveyard_page(self) -> QWidget:
        """Build the graveyard list with ID-safe portrait and gravestone editing."""
        page = QWidget()
        page.setObjectName("graveyardPage")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(8, 8, 8, 8)

        self.graveyard_summary_label = QLabel()
        self.graveyard_summary_label.setObjectName("graveyardSummaryLabel")
        page_layout.addWidget(self.graveyard_summary_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("graveyardSplitter")
        self.graveyard_model = QStandardItemModel(0, 5, self)
        self.graveyard_table = QTableView()
        self.graveyard_row_hover = install_row_hover(self.graveyard_table)
        self.graveyard_table.setObjectName("graveyardTable")
        self.graveyard_table.setModel(self.graveyard_model)
        self.graveyard_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.graveyard_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.graveyard_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.graveyard_table.setAlternatingRowColors(True)
        self.graveyard_table.setSortingEnabled(True)
        self.graveyard_table.verticalHeader().setVisible(False)
        header = self.graveyard_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.graveyard_table.selectionModel().currentRowChanged.connect(
            self._graveyard_row_changed
        )
        splitter.addWidget(self.graveyard_table)

        detail = QFrame()
        detail.setObjectName("graveyardDetailFrame")
        detail.setFrameShape(QFrame.Shape.StyledPanel)
        detail_layout = QVBoxLayout(detail)
        self.graveyard_heading_label = QLabel()
        heading_font = self.graveyard_heading_label.font()
        heading_font.setBold(True)
        self.graveyard_heading_label.setFont(heading_font)
        detail_layout.addWidget(self.graveyard_heading_label)

        form = QFormLayout()
        self._graveyard_detail_form_labels: dict[str, QLabel] = {}
        self.graveyard_name_value = QLabel("-")
        self.graveyard_race_value = QLabel("-")
        self.graveyard_class_value = QLabel("-")
        self.graveyard_class_icon_label = QLabel("–")
        self.graveyard_class_icon_label.setFixedSize(20, 20)
        self.graveyard_class_presentation = QWidget()
        graveyard_class_layout = QHBoxLayout(self.graveyard_class_presentation)
        graveyard_class_layout.setContentsMargins(0, 0, 0, 0)
        graveyard_class_layout.setSpacing(6)
        graveyard_class_layout.addWidget(self.graveyard_class_icon_label)
        graveyard_class_layout.addWidget(self.graveyard_class_value)
        graveyard_class_layout.addStretch(1)
        self.graveyard_spec_value = QLabel("-")
        self.graveyard_life_value = QLabel("-")
        self.graveyard_death_value = QLabel("-")
        self.graveyard_stone_value = QLabel("-")
        self.graveyard_category_value = QLabel("-")
        for key, value in (
            ("name", self.graveyard_name_value),
            ("race", self.graveyard_race_value),
            ("class", self.graveyard_class_presentation),
            ("spec", self.graveyard_spec_value),
            ("life", self.graveyard_life_value),
            ("death", self.graveyard_death_value),
            ("stone", self.graveyard_stone_value),
            ("category", self.graveyard_category_value),
        ):
            label = QLabel()
            self._graveyard_detail_form_labels[key] = label
            if isinstance(value, QLabel):
                value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                value.setWordWrap(True)
            form.addRow(label, value)
        detail_layout.addLayout(form)

        assignment_frame = QFrame()
        assignment_frame.setObjectName("graveyardAssignmentFrame")
        assignment_frame.setFrameShape(QFrame.Shape.StyledPanel)
        assignment_layout = QVBoxLayout(assignment_frame)
        assignment_layout.setContentsMargins(8, 8, 8, 8)
        assignment_layout.setSpacing(6)
        self.graveyard_edit_stone_button = QPushButton()
        self.graveyard_edit_stone_button.setObjectName("graveyardEditStoneButton")
        self.graveyard_edit_stone_button.clicked.connect(
            self.open_selected_gravestone_editor
        )
        assignment_layout.addWidget(self.graveyard_edit_stone_button)
        graveyard_portrait_actions = QHBoxLayout()
        self.graveyard_import_portrait_button = QPushButton()
        self.graveyard_import_portrait_button.setObjectName("graveyardImportPortraitButton")
        self.graveyard_import_portrait_button.clicked.connect(
            self.import_selected_graveyard_portrait
        )
        graveyard_portrait_actions.addWidget(self.graveyard_import_portrait_button)
        self.graveyard_edit_portrait_button = QPushButton()
        self.graveyard_edit_portrait_button.setObjectName("graveyardEditPortraitButton")
        self.graveyard_edit_portrait_button.clicked.connect(
            self.edit_selected_graveyard_portrait
        )
        graveyard_portrait_actions.addWidget(self.graveyard_edit_portrait_button)
        assignment_layout.addLayout(graveyard_portrait_actions)
        self.graveyard_assignment_status_label = QLabel()
        self.graveyard_assignment_status_label.setObjectName(
            "graveyardAssignmentStatusLabel"
        )
        self.graveyard_assignment_status_label.setWordWrap(True)
        assignment_layout.addWidget(self.graveyard_assignment_status_label)
        detail_layout.addWidget(assignment_frame)

        self.graveyard_preview_status_label = QLabel()
        self.graveyard_preview_status_label.setObjectName("graveyardPreviewStatusLabel")
        self.graveyard_preview_status_label.setWordWrap(True)
        detail_layout.addWidget(self.graveyard_preview_status_label)
        self.graveyard_preview = PortraitPreviewLabel()
        self.graveyard_preview.setObjectName("graveyardPreview")
        detail_layout.addWidget(self.graveyard_preview, 1)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        page_layout.addWidget(splitter, 1)
        return page

    def load_project(self, project_path: str | Path) -> bool:
        """Lädt Projekt und Charaktere transaktional über das bestehende Modell."""
        try:
            paths = project_paths(project_path)
            payload = load_project_payload(paths.project)
            v2_mode = isinstance(payload, dict) and payload.get("identityFormat") == "identity-v2"
            if v2_mode:
                root = str(Path(__file__).resolve().parents[1])
                if root not in sys.path:
                    sys.path.insert(0, root)
                from app.identity_v2 import IdentityV2Store

                store = IdentityV2Store.from_payload(payload)
                model = GuildModel()
                model.new_empty()
                model.project_path = paths.project
                model.members = [Member(
                    id=item.memberId, name=item.name, race=item.race,
                    className=item.className or "", spec=item.spec or "",
                    lifeStatus=item.lifeStatus, deathDate=item.deathDate or "",
                    graveTemplateId=item.graveTemplateId or "",
                    portraitOffsetX=item.portraitOffsetX,
                    portraitOffsetY=item.portraitOffsetY,
                    portraitZoom=item.portraitZoom,
                    textOffsetX=item.textOffsetX, textOffsetY=item.textOffsetY,
                    textScale=item.textScale,
                ) for item in store.members]
            else:
                store = None
                model = GuildModel()
                model.load_payload(payload, paths.project)
                model.portrait_migration_summary = migrate_legacy_portraits(
                    paths.project, model.members,
                )
        except (OSError, TypeError, ValueError) as exc:
            self.project_error = str(exc)
            self.refresh_texts()
            return False

        project_changed = self.project_path != paths.project
        keep_selection = (
            self.selected_character_id if self.project_path == paths.project else None
        )
        keep_graveyard_selection = (
            self.selected_graveyard_member_id if self.project_path == paths.project else None
        )
        if self._session_project_path is not None and paths.project != self._session_project_path:
            self.session_id = None
            self._session_project_path = None
        self.project_path = paths.project
        self.project_payload = payload
        self.project_model = model
        self.v2_mode = v2_mode
        self.v2_store = store
        self.tabs.setTabEnabled(self.tabs.indexOf(self.portraits_page), True)
        self.roster_actions_group.setVisible(not v2_mode)
        if v2_mode:
            self.tabs.setCurrentWidget(self.graveyard_page)
        self.project_error = None
        if project_changed:
            self.armory_results.clear()
        self.handoff_path = paths.handoff if self.session_id else None
        if self.session_id and self._session_project_path is None:
            self._session_project_path = paths.project
        self.active_character_members = sorted(
            (member for member in model.members if member.lifeStatus == "active"),
            key=lambda member: (member.name.casefold(), member.name, member.id),
        )
        self.inactive_character_members = sorted(
            (member for member in model.members if member.lifeStatus == "inactive"),
            key=lambda member: (member.name.casefold(), member.name, member.id),
        )
        self.character_members = (
            self.inactive_character_members
            if self._portrait_list_mode == "inactive"
            else self.active_character_members
        )
        self._member_by_id = {
            member.id: member
            for member in (*self.active_character_members, *self.inactive_character_members)
        }
        self.graveyard_members = sorted(
            (member for member in model.members if member.lifeStatus == "dead"),
            key=lambda member: (member.name.casefold(), member.name, member.id),
        )
        self._graveyard_member_by_id = {
            member.id: member for member in self.graveyard_members
        }
        try:
            self._graveyard_inventory = model.gravestone_inventory()
            self._graveyard_templates_by_id = self._graveyard_inventory.by_id()
        except (OSError, TypeError, ValueError):
            self._graveyard_inventory = None
            self._graveyard_templates_by_id = {}
        if keep_selection not in {member.id for member in self.character_members}:
            keep_selection = None
        self._rebuild_character_model(keep_selection)
        self._rebuild_graveyard_model(keep_graveyard_selection)
        self._refresh_settings_project_path()
        self.refresh_texts()
        return True

    def _choose_project(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            tr("grabber.open_project_title"),
            str(self.project_path.parent if self.project_path else Path.cwd()),
            "Guild Gear Checker (*.ggc)",
        )
        if path:
            self.load_project(path)

    def _replace_current_character_members(self, members: list[Member]) -> None:
        if self._portrait_list_mode == "inactive":
            self.inactive_character_members = members
            self.character_members = self.inactive_character_members
        else:
            self.active_character_members = members
            self.character_members = self.active_character_members

    def _set_portrait_list_mode(self, mode: str) -> None:
        mode = "inactive" if mode == "inactive" else "active"
        if mode == self._portrait_list_mode and self.character_members:
            return
        self._portrait_list_mode = mode
        self.active_portraits_button.blockSignals(True)
        self.inactive_portraits_button.blockSignals(True)
        self.active_portraits_button.setChecked(mode == "active")
        self.inactive_portraits_button.setChecked(mode == "inactive")
        self.active_portraits_button.blockSignals(False)
        self.inactive_portraits_button.blockSignals(False)
        self.character_members = (
            self.inactive_character_members if mode == "inactive"
            else self.active_character_members
        )
        selected = (
            self.selected_character_id
            if self.selected_character_id in {member.id for member in self.character_members}
            else None
        )
        self._rebuild_character_model(selected)
        self._update_armory_controls()

    def _add_working_names(self, names: Sequence[str]) -> int:
        """Ergänzt die Arbeitsliste exakt/casefold-basiert ohne Projektmutation."""
        if self.v2_mode:
            return 0
        current_names = [member.name for member in self.character_members]
        merged_names = dedupe_names([*current_names, *names])
        existing = {name.casefold() for name in current_names}
        added_names = [name for name in merged_names if name.casefold() not in existing]
        if not added_names:
            return 0
        for name in added_names:
            member = Member(
                id=f"working:{uuid.uuid4().hex}",
                name=name,
                source="Portrait Grabber",
            )
            member.lifeStatus = (
                "inactive" if self._portrait_list_mode == "inactive" else "active"
            )
            self.character_members.append(member)
            self._member_by_id[member.id] = member
        self._rebuild_character_model(self.selected_character_id or self.character_members[-1].id)
        self._update_armory_controls()
        return len(added_names)

    def add_character(self) -> bool:
        name, accepted = QInputDialog.getText(
            self, tr("grabber.add_character"), tr("grabber.add_character_name")
        )
        if not accepted or not str(name).strip():
            return False
        added = self._add_working_names([str(name)])
        message = tr("grabber.import_summary", recognized=1, added=added)
        self.worker_status_label.setText(message)
        self.statusBar().showMessage(message)
        return bool(added)

    def remove_selected_character(self) -> bool:
        member = self._selected_member()
        if member is None:
            return False
        if QMessageBox.question(
            self,
            tr("grabber.remove"),
            tr("grabber.remove_question", name=member.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return False
        self._replace_current_character_members([
            candidate for candidate in self.character_members if candidate.id != member.id
        ])
        self._member_by_id.pop(member.id, None)
        self.armory_results.pop(member.id, None)
        self._rebuild_character_model(None)
        self._update_armory_controls()
        return True

    def _import_names_from_path(self, path: str | Path) -> tuple[int, int]:
        names = load_names_from_file(Path(path), active_only=True)
        added = self._add_working_names(names)
        message = tr("grabber.import_summary", recognized=len(names), added=added)
        self.worker_status_label.setText(message)
        self.statusBar().showMessage(message)
        return len(names), added

    def import_character_list(self) -> bool:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            tr("grabber.import_list_title"),
            str(self.project_path.parent if self.project_path else Path.cwd()),
            f"{tr('common.supported_files')} (*.txt *.csv);;"
            f"Warcraft Logs CSV (*.csv);;{tr('common.text_files')} (*.txt);;"
            f"{tr('common.all_files')} (*.*)",
        )
        if not path:
            return False
        try:
            self._import_names_from_path(path)
        except (OSError, TypeError, ValueError) as exc:
            QMessageBox.critical(self, tr("grabber.import_failed_title"), str(exc))
            return False
        return True

    def import_wcl_csv(self) -> bool:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            tr("grabber.import_wcl_title"),
            str(self.project_path.parent if self.project_path else Path.cwd()),
            f"Warcraft Logs CSV (*.csv);;{tr('common.all_files')} (*.*)",
        )
        if not path:
            return False
        try:
            self._import_names_from_path(path)
        except (OSError, TypeError, ValueError) as exc:
            QMessageBox.critical(self, tr("grabber.import_failed_title"), str(exc))
            return False
        return True

    def _current_guild_records(self) -> list[dict]:
        records: list[dict] = []
        for member in self.character_members:
            result = self.armory_results.get(member.id) or {}
            records.append({
                "characterName": member.name,
                "race": result.get("race") or member.race,
                "className": result.get("className") or member.className,
            })
        return records

    @staticmethod
    def _guild_save_summary_text(summary: dict) -> str:
        added = int(summary.get("added", 0))
        existing = int(summary.get("existing", 0))
        incarnations = int(summary.get("newIncarnations", 0))
        if not added:
            return tr("grabber.guild_save_none")
        lines = [
            tr("grabber.guild_save_added", count=added),
            tr("grabber.guild_save_existing", count=existing),
        ]
        if incarnations:
            lines.append(tr("grabber.guild_save_incarnations", count=incarnations))
        return "\n".join(lines)

    def _dispatch_project_action(self, action_type: str,
                                 data: dict) -> tuple[str, dict | None]:
        if self.v2_mode:
            raise ValueError(tr("identity_v2_project.legacy_disabled"))
        if self.project_path is None:
            raise ValueError(tr("grabber.project_required"))
        if self.session_id:
            token = queue_action(self.project_path, self.session_id, action_type, data)
            return token, None
        action = make_action(action_type, data)
        result = apply_actions_to_project(self.project_path, [action])
        receipt = next(iter(result.get("receipts", [])), None)
        if not receipt or not receipt.get("ok"):
            raise ValueError(str(
                (receipt or {}).get("error") or tr("grabber.project_action_failed")
            ))
        return str(action["token"]), receipt

    def _apply_saved_member_summary(self, summary: dict) -> None:
        selected_id = self.selected_character_id
        for created in summary.get("created", []):
            if not isinstance(created, dict):
                continue
            name = str(created.get("characterName") or "").strip()
            member_id = str(created.get("memberId") or "").strip()
            if not name or not member_id:
                continue
            member = next((
                candidate for candidate in self.character_members
                if candidate.name.casefold() == name.casefold()
                and candidate.id.startswith("working:")
            ), None)
            if member is None:
                continue
            old_id = member.id
            member.id = member_id
            member.race = created.get("race") or member.race
            member.className = str(created.get("className") or member.className or "")
            self._member_by_id.pop(old_id, None)
            self._member_by_id[member.id] = member
            if old_id in self.armory_results:
                self.armory_results[member.id] = self.armory_results.pop(old_id)
            if selected_id == old_id:
                selected_id = member.id
        self._rebuild_character_model(selected_id)

    def save_guild_list(self) -> bool:
        if self.v2_mode:
            return False
        if self.project_path is None or self._pending_roster_save_token:
            if self.project_path is None:
                QMessageBox.information(self, self.windowTitle(), tr("grabber.project_required"))
            return False
        try:
            token, receipt = self._dispatch_project_action(
                "add_members", {"members": self._current_guild_records()}
            )
            if receipt is None:
                self._pending_roster_save_token = token
                self._pending_roster_save_started = time.monotonic()
                message = tr("grabber.guild_save_handoff")
                self.worker_status_label.setText(message)
                self.statusBar().showMessage(message)
                self._update_armory_controls()
                QTimer.singleShot(100, self._poll_guild_save_receipt)
                return True
            self._finish_guild_save(receipt)
            return True
        except Exception as exc:
            QMessageBox.critical(
                self, self.windowTitle(), tr("grabber.guild_save_failed", error=exc)
            )
            return False

    def _finish_guild_save(self, receipt: dict) -> None:
        if not receipt.get("ok"):
            QMessageBox.critical(
                self,
                self.windowTitle(),
                tr(
                    "grabber.guild_save_failed",
                    error=receipt.get("error") or tr("common.unknown_error"),
                ),
            )
            return
        summary = dict(receipt.get("summary") or {})
        self._apply_saved_member_summary(summary)
        message = self._guild_save_summary_text(summary)
        self.worker_status_label.setText(message.replace("\n", " · "))
        self.statusBar().showMessage(message.replace("\n", " · "))
        QMessageBox.information(self, self.windowTitle(), message)

    def _poll_guild_save_receipt(self) -> None:
        token = self._pending_roster_save_token
        if not token or self.project_path is None or not self.session_id:
            return
        receipt = read_receipt(self.project_path, self.session_id, token)
        if receipt is None:
            if time.monotonic() - self._pending_roster_save_started > 20.0:
                self._pending_roster_save_token = None
                self._update_armory_controls()
                QMessageBox.critical(
                    self, self.windowTitle(), tr("grabber.guild_save_timeout")
                )
                return
            QTimer.singleShot(150, self._poll_guild_save_receipt)
            return
        self._pending_roster_save_token = None
        self._update_armory_controls()
        self._finish_guild_save(receipt)

    def _selected_member(self) -> Member | None:
        if not self.selected_character_id:
            return None
        return self._member_by_id.get(self.selected_character_id)

    def _current_screen_region(self) -> tuple[int, int, int, int]:
        return normalize_screen_region(self.config_data.get("screen_region", {}))

    def _refresh_screen_region_text(self) -> None:
        region = self._current_screen_region()
        valid, _message = validate_screen_region(region)
        text = (
            f"X={region[0]}, Y={region[1]}, {region[2]}x{region[3]} px"
            if valid else tr("grabber.not_configured")
        )
        self.screen_region_label.setText(
            f"{tr('grabber.saved_region')}: {text}"
        )

    def _refresh_settings_project_path(self) -> None:
        try:
            output = default_output_dir(self.project_path) if self.project_path else None
        except (OSError, TypeError, ValueError, RuntimeError):
            output = None
        self.output_folder_edit.setText(str(output) if output else "")
        self.output_folder_edit.setToolTip(str(output) if output else "")

    def save_settings(self) -> None:
        config = build_saved_grabber_config(
            self.config_data,
            region=self.region_edit.text(),
            realm=self.realm_edit.text(),
            game_version=self.game_version_edit.text(),
            guild_name=self.guild_name_edit.text(),
            crop=self.config_data.get("crop", clamp_crop({})),
            capture_mode=str(self.capture_mode_combo.currentData() or "playwright"),
            standard_wait_after_open=self.standard_wait_spin.value(),
            screen_region=self._current_screen_region(),
        )
        self.config_data.clear()
        self.config_data.update(config)
        save_config(self.config_data)
        self._refresh_screen_region_text()

    def _capture_mode_changed(self, _text: str = "") -> None:
        if hasattr(self, "standard_wait_spin"):
            self.standard_wait_spin.setEnabled(
                self.capture_mode_combo.currentData() == "standard_browser_region"
            )
            self.save_settings()
        mode = tr(
            "grabber.mode_standard"
            if self.config_data.get("capture_mode") == "standard_browser_region"
            else "grabber.mode_playwright"
        )
        message = tr("grabber.mode_status", mode=mode)
        self.worker_status_label.setText(message)
        self.statusBar().showMessage(message)

    def _language_changed(self, display: str) -> None:
        language = language_from_display(display)
        if language == get_language():
            return
        set_language(language)
        self.refresh_texts()
        QMessageBox.information(
            self, tr("language.restart_title"), tr("language.restart_message")
        )

    def test_browser(self) -> bool:
        if self._worker_closed or self._active_worker_action is not None:
            return False
        self.save_settings()
        self._active_worker_action = "test_browser"
        self._active_worker_member_id = None
        self._active_worker_project_path = self.project_path
        self._last_worker_event = None
        self.worker_error_label.clear()
        self.worker_error_label.hide()
        self.worker_status_label.setText(tr("grabber.browser_test"))
        self.statusBar().showMessage(tr("grabber.browser_test"))
        self._update_armory_controls()
        self.worker.submit("test_browser", **self._worker_payload())
        return True

    def calibrate_selected_crop(self) -> bool:
        member = self._selected_member()
        if member is None:
            self.worker_status_label.setText(tr("grabber.select_first"))
            self.statusBar().showMessage(tr("grabber.select_first"))
            return False
        payload = self._worker_payload()
        payload.update(capture_mode="playwright", navigate=True)
        return self._start_worker_action("capture_raw", member, payload)

    def _open_crop_calibration(self, path: Path, name: str) -> None:
        if self.project_path is None:
            self.worker_status_label.setText(tr("grabber.project_required"))
            return
        if self._portrait_editor_dialog is not None and self._portrait_editor_dialog.isVisible():
            self._portrait_editor_dialog.raise_()
            self._portrait_editor_dialog.activateWindow()
            return
        try:
            state = load_portrait_editor_state(path)
            crop = clamp_crop(self.config_data.get("crop", {}))
            source_width, source_height = state.source_size
            viewport_width, viewport_height = PORTRAIT_EDITOR_PREVIEW_SIZE
            crop_width = max(1.0, (crop["x2"] - crop["x1"]) * source_width)
            crop_height = max(1.0, (crop["y2"] - crop["y1"]) * source_height)
            base_scale = max(
                viewport_width / source_width,
                viewport_height / source_height,
            )
            desired_scale = max(
                viewport_width / crop_width,
                viewport_height / crop_height,
            )
            zoom = desired_scale / base_scale
            state = portrait_editor_transform(state, zoom=zoom)
            effective_scale = base_scale * state.zoom
            center_x = (crop["x1"] + crop["x2"]) * source_width / 2.0
            center_y = (crop["y1"] + crop["y2"]) * source_height / 2.0
            state = portrait_editor_transform(
                state,
                offset_x=(source_width / 2.0 - center_x) * effective_scale,
                offset_y=(source_height / 2.0 - center_y) * effective_scale,
            )
            member = self._selected_member()
            if member is None:
                raise ValueError(tr("checker.no_character_selected"))
            destination = normal_portrait_path(member.id, self.project_path)
            dialog = PortraitEditorDialogQt(
                name,
                state,
                destination,
                on_calibrated=lambda crop, saved: self._apply_crop_calibration(
                    crop, name, saved
                ),
                window_title=tr("grabber.crop_title"),
                parent=self,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(self, tr("grabber.crop"), str(exc))
            return
        dialog.finished.connect(self._clear_portrait_editor_dialog)
        self._portrait_editor_dialog = dialog
        dialog.show()

    def _apply_crop_calibration(self, crop: dict, name: str,
                                saved_path: Path) -> None:
        self.config_data["crop"] = clamp_crop(crop)
        self.save_settings()
        if self.project_path is None:
            return
        self.portrait_preview.invalidate()
        self.worker_status_label.setText(tr("grabber.crop_saved"))
        self.statusBar().showMessage(tr("grabber.crop_saved"))
        self._refresh_character_rows()
        member = self._selected_member()
        if member is not None and member.name.casefold() == name.casefold():
            self.show_character(member.id)

    def set_default_screen_region(self) -> None:
        if self._active_worker_action is not None:
            QMessageBox.information(
                self, tr("grabber.region_title"), tr("grabber.stop_batch_first")
            )
            return
        self.save_settings()
        self.worker_status_label.setText(tr("grabber.region_capture_start"))
        self.hide()
        QTimer.singleShot(350, self._capture_virtual_screen_for_region)

    def _capture_virtual_screen_for_region(self) -> None:
        try:
            bounds = virtual_screen_bounds()
            image = capture_screen_region(bounds)
        except Exception as exc:
            self.show()
            QMessageBox.critical(
                self,
                tr("grabber.region_title"),
                tr("grabber.region_capture_failed", error=exc),
            )
            return
        self.show()
        self.raise_()
        x, y, width, height = self._current_screen_region()
        bx, by, _bw, _bh = bounds
        valid, _message = validate_screen_region((x, y, width, height), bounds)
        initial = (
            QRectF(x - bx, y - by, width, height)
            if valid else QRectF(0.0, 0.0, float(image.width), float(image.height))
        )
        self._selection_dialog = ImageSelectionDialogQt(
            image,
            initial,
            title=tr("grabber.region_title"),
            help_text=tr("grabber.standard_crop_help"),
            on_accept=lambda rect: self._accept_screen_region(rect, bounds),
            apply_text=tr("grabber.set_region"),
            parent=self,
        )
        self._selection_dialog.show()

    def _accept_screen_region(self, rect: QRectF,
                              bounds: tuple[int, int, int, int]) -> None:
        bx, by, _bw, _bh = bounds
        region = normalize_screen_region((
            bx + round(rect.left()),
            by + round(rect.top()),
            round(rect.width()),
            round(rect.height()),
        ))
        valid, message = validate_screen_region(region, bounds)
        if not valid:
            QMessageBox.warning(self, tr("grabber.region_title"), message)
            return
        x, y, width, height = region
        self.config_data["screen_region"] = {
            "x": x, "y": y, "width": width, "height": height,
        }
        self.save_settings()
        self.worker_status_label.setText(tr("grabber.region_saved"))
        self.statusBar().showMessage(tr("grabber.region_saved"))

    def test_default_screen_region(self) -> bool:
        region = self._current_screen_region()
        valid, message = validate_screen_region(region)
        if not valid:
            QMessageBox.information(
                self,
                tr("grabber.region_title"),
                f"{message}\n\n{tr('grabber.set_region_first')}",
            )
            return False
        try:
            image = capture_screen_region(region)
        except Exception as exc:
            QMessageBox.critical(self, tr("grabber.test_region"), str(exc))
            return False
        self._show_image_preview(image, tr("grabber.test_region"))
        return True

    def _show_image_preview(self, image: Image.Image, title: str) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(720, 720)
        layout = QVBoxLayout(dialog)
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setPixmap(QPixmap.fromImage(ImageQt(image.convert("RGBA"))))
        scroll = QScrollArea()
        scroll.setWidget(label)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        close_button = QPushButton(tr("common.close"))
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)
        self._preview_dialog = dialog
        dialog.show()

    def reset_default_screen_region(self) -> bool:
        current_valid, _message = validate_screen_region(self._current_screen_region())
        if current_valid and QMessageBox.question(
            self,
            tr("grabber.region_title"),
            tr("grabber.reset_region_question"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return False
        self.config_data["screen_region"] = {
            "x": 0, "y": 0, "width": 0, "height": 0,
        }
        self.save_settings()
        return True

    def _worker_payload(self) -> dict:
        source_settings = portrait_source_settings(self.config_data)
        region = source_settings.get("screen_region") or {}
        screen_region = (
            int(region.get("x", 0) or 0),
            int(region.get("y", 0) or 0),
            int(region.get("width", 0) or 0),
            int(region.get("height", 0) or 0),
        )
        return build_worker_payload(
            region=str(source_settings.get("region") or ""),
            realm=str(source_settings.get("realm") or ""),
            game_version=str(source_settings.get("game_version") or ""),
            preferred_channel=str(
                source_settings.get("browser_channel") or "msedge"
            ),
            wait_after_load=source_settings.get("wait_after_load", 3.0),
            capture_mode=str(source_settings.get("capture_mode") or "playwright"),
            screen_region=screen_region,
            standard_wait_after_open=source_settings.get(
                "standard_wait_after_open", 6.0
            ),
            source_id=source_settings["source_id"],
        )

    def armory_url_for_selected(self) -> str:
        member = self._selected_member()
        if member is None:
            return ""
        payload = self._worker_payload()
        return build_portrait_source_url(member.name, payload)

    def _start_worker_action(self, action: str, member: Member,
                             worker_payload: dict | None = None) -> bool:
        if self._worker_closed or self._active_worker_action is not None:
            return False
        payload = dict(worker_payload) if worker_payload is not None else self._worker_payload()
        self._active_worker_action = action
        self._active_worker_member_id = member.id
        self._active_worker_project_path = self.project_path
        self._last_worker_event = None
        self.worker_error_label.clear()
        self.worker_error_label.hide()
        if action == "open":
            message = tr("grabber.worker_opening", name=member.name)
        elif action == "capture":
            message = tr("grabber.creating_portrait")
        elif action == "capture_raw":
            message = tr("grabber.loading_calibration")
        else:
            message = tr("grabber.reading_data_for", name=member.name)
        self.worker_status_label.setText(message)
        self.statusBar().showMessage(message)
        self._update_armory_controls()
        self.worker.submit(
            action,
            name=member.name,
            member_id=member.id,
            **payload,
        )
        return True

    def open_selected_in_browser(self) -> bool:
        member = self._selected_member()
        if member is None:
            self.worker_status_label.setText(tr("grabber.select_first"))
            self.statusBar().showMessage(tr("grabber.select_first"))
            return False
        return self._start_worker_action("open", member)

    def read_selected_armory_data(self) -> bool:
        member = self._selected_member()
        if member is None:
            self.worker_status_label.setText(tr("grabber.select_first"))
            self.statusBar().showMessage(tr("grabber.select_first"))
            return False
        return self._start_worker_action("read_data", member)

    def read_missing_armory_data(self) -> bool:
        if (self.project_path is None or self._worker_closed
                or self._active_worker_action is not None):
            if self.project_path is None:
                self.worker_status_label.setText(tr("grabber.project_required"))
                self.statusBar().showMessage(tr("grabber.project_required"))
            return False
        records = []
        for member in self.character_members:
            result = self.armory_results.get(member.id) or {}
            records.append({
                "memberId": member.id,
                "characterName": member.name,
                "race": result.get("race") or member.race,
                "className": result.get("className") or member.className,
            })
        missing = records_missing_armory_data(records)
        if not missing:
            message = tr("grabber.no_missing_data")
            self.worker_status_label.setText(message)
            self.statusBar().showMessage(message)
            return False
        if QMessageBox.question(
            self,
            tr("grabber.read_missing_data"),
            tr("grabber.read_data_batch_question", count=len(missing)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return False
        self._active_worker_action = "read_data_all"
        self._active_worker_member_id = None
        self._active_worker_project_path = self.project_path
        self._last_worker_event = None
        self._batch_names = [str(record["characterName"]) for record in missing]
        self._batch_stop_requested = False
        self._worker_cancel_requested = False
        self.worker_error_label.clear()
        self.worker_error_label.hide()
        self._show_batch_progress(0, len(missing), tr("grabber.read_missing_data"))
        message = tr("grabber.read_data_batch_started", count=len(missing))
        self.worker_status_label.setText(message)
        self.statusBar().showMessage(message)
        self._update_armory_controls()
        self.worker.submit("read_data_all", records=missing, **self._worker_payload())
        return True

    def capture_selected_portrait(self) -> bool:
        """Startet den bestehenden Single-Capture-Vertrag für die Qt-Auswahl."""
        member = self._selected_member()
        if member is None:
            self.worker_status_label.setText(tr("grabber.select_first"))
            self.statusBar().showMessage(tr("grabber.select_first"))
            return False
        payload = self._capture_worker_payload()
        if payload is None:
            return False
        payload["navigate"] = True
        return self._start_worker_action("capture", member, payload)

    def _capture_worker_payload(self) -> dict | None:
        """Ergänzt den gemeinsamen Worker-Payload um bestehende Capturewerte."""
        if self.project_path is None:
            self.worker_status_label.setText(tr("grabber.project_required"))
            self.statusBar().showMessage(tr("grabber.project_required"))
            return None
        payload = self._worker_payload()
        if payload["capture_mode"] == "standard_browser_region":
            valid, message = validate_screen_region(payload["screen_region"])
            if not valid:
                detail = f"{message}\n{tr('grabber.set_region_first')}"
                self.worker_status_label.setText(message)
                self.statusBar().showMessage(message)
                self.worker_error_label.setText(detail)
                self.worker_error_label.show()
                return None
        try:
            output_dir = default_output_dir(self.project_path)
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            message = str(exc) or tr("grabber.project_required")
            self.worker_status_label.setText(message)
            self.statusBar().showMessage(message)
            self.worker_error_label.setText(message)
            self.worker_error_label.show()
            return None
        payload.update({
            "output_dir": str(output_dir),
            "crop": self.config_data.get("crop", clamp_crop({})),
        })
        return payload

    def _batch_member_records(self, names: list[str]) -> list[dict]:
        members_by_name = {
            member.name.casefold(): member for member in self.character_members
        }
        return [
            {
                "memberId": members_by_name[name.casefold()].id,
                "characterName": members_by_name[name.casefold()].name,
            }
            for name in names
            if name.casefold() in members_by_name
        ]

    def _start_portrait_batch(self, names: list[str], title: str,
                              overwrite_existing: bool, *,
                              members: list[Member] | None = None) -> bool:
        if self._worker_closed or self._active_worker_action is not None:
            return False
        names = ([member.name for member in members] if self.v2_mode and members is not None
                 else dedupe_names(names))
        payload = self._capture_worker_payload()
        if payload is None or not names:
            return False

        mode = capture_mode_display(payload["capture_mode"])
        overwrite = tr(
            "grabber.overwrite_yes" if overwrite_existing else "grabber.overwrite_no"
        )
        question = tr(
            "grabber.batch_question", count=len(names), mode=mode, overwrite=overwrite,
        )
        if QMessageBox.question(
            self, title, question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return False

        payload.update({
            "character_records": ([
                {"memberId": member.id, "characterName": member.name}
                for member in members
            ] if self.v2_mode and members is not None else self._batch_member_records(names)),
        })
        self._active_worker_action = "capture_all"
        self._active_worker_member_id = None
        self._active_worker_project_path = self.project_path
        self._last_worker_event = None
        self._batch_names = list(names)
        self._batch_member_ids = ({member.id for member in members}
                                  if self.v2_mode and members is not None else set())
        self._batch_stop_requested = False
        self._worker_cancel_requested = False
        self.worker_error_label.clear()
        self.worker_error_label.hide()
        self._show_batch_progress(0, len(names), title)
        message = tr("grabber.batch_started", title=title, count=len(names), mode=mode)
        self.worker_status_label.setText(message)
        self.statusBar().showMessage(message)
        self._update_armory_controls()
        self.worker.submit("capture_all", names=list(names), **payload)
        return True

    def capture_all_portraits(self) -> bool:
        return self._start_portrait_batch(
            [member.name for member in self.character_members],
            tr("grabber.create_all"),
            overwrite_existing=True,
            members=list(self.character_members) if self.v2_mode else None,
        )

    def capture_missing_portraits(self) -> bool:
        if self._active_worker_action is not None:
            return False
        if self.project_path is None:
            self._capture_worker_payload()
            return False
        missing_members = ([member for member in self.character_members
                            if self._portrait_file_for(member) is None]
                           if self.v2_mode else None)
        names = ([member.name for member in missing_members]
                 if missing_members is not None else missing_portrait_names(
                     [member.name for member in self.character_members], self.project_path,
                     {member.name.casefold(): member.id for member in self.character_members},
                 ))
        if not names:
            message = tr("grabber.nothing_missing")
            self.worker_status_label.setText(message)
            self.statusBar().showMessage(message)
            self._refresh_character_rows()
            return False
        return self._start_portrait_batch(
            names, tr("grabber.create_missing"), overwrite_existing=False,
            members=missing_members,
        )

    def _request_worker_cancel_once(self) -> bool:
        if self._worker_cancel_requested:
            return False
        self._worker_cancel_requested = True
        self.worker.request_batch_cancel()
        return True

    def request_batch_stop(self) -> bool:
        if (self._active_worker_action not in {"capture_all", "read_data_all"}
                or self._batch_stop_requested):
            return False
        self._batch_stop_requested = True
        self._request_worker_cancel_once()
        message = tr("grabber.stop_requested")
        self.worker_status_label.setText(message)
        self.statusBar().showMessage(message)
        self._update_armory_controls()
        return True

    def _poll_worker_events(self) -> None:
        if self._worker_closed:
            return
        try:
            while True:
                self._handle_worker_event(self.events.get_nowait())
        except queue.Empty:
            return

    def _event_finishes_active_action(self, kind: str | None) -> bool:
        if kind == "error":
            return True
        if self._active_worker_action == "open":
            return kind == "opened"
        if self._active_worker_action == "read_data":
            return kind in {
                "armory_data", "armory_data_error", "armory_data_wait_timeout",
            }
        if self._active_worker_action == "capture":
            return kind == "portrait_saved"
        if self._active_worker_action == "capture_raw":
            return kind == "raw_capture"
        if self._active_worker_action == "test_browser":
            return kind in {"browser_test_ok", "error"}
        if self._active_worker_action in {"capture_all", "read_data_all"}:
            return kind == "batch_done"
        return False

    def _handle_worker_event(self, event: dict) -> None:
        self.last_event_thread_id = threading.get_ident()
        self._last_worker_event = dict(event)
        semantic = interpret_worker_event(event)
        if (semantic.get("kind") == "batch_done"
                and self._active_worker_action not in {"capture_all", "read_data_all"}):
            return
        model_action = semantic.get("model_action") or {}
        action = semantic.get("action") or {}
        if model_action.get("type") == "store_armory_result":
            self._store_armory_result(model_action.get("result") or {})
        if semantic.get("kind") == "portrait_saved":
            if not self._refresh_saved_portrait(event):
                message = tr("grabber.screenshot_error")
                semantic = {
                    "kind": (
                        "item_error"
                        if self._active_worker_action == "capture_all" else "error"
                    ),
                    "status": message,
                    "dialog": {"message": message},
                }
        if action.get("type") == "open_crop_dialog":
            path = Path(str(action.get("path") or ""))
            if path.is_file():
                self._open_crop_calibration(path, str(action.get("name") or ""))
        self._apply_batch_semantic(semantic)
        self._present_worker_semantic(semantic)
        if self._event_finishes_active_action(semantic.get("kind")):
            self._active_worker_action = None
            self._active_worker_member_id = None
            self._active_worker_project_path = None
        self._update_armory_controls()

    def _apply_batch_semantic(self, semantic: dict) -> None:
        action = semantic.get("action") or {}
        if self._active_worker_action not in {"capture_all", "read_data_all"}:
            return
        if action.get("type") == "batch_progress":
            maximum = max(1, int(action.get("maximum", 1)))
            value = max(0, int(action.get("value", 0)))
            self._show_batch_progress(value, maximum)
        elif action.get("type") == "batch_done":
            processed = max(0, int(action.get("processed", 0)))
            maximum = max(1, len(self._batch_names))
            self._show_batch_progress(min(processed, maximum), maximum)
            self._refresh_character_rows()
            if self.selected_character_id:
                self.show_character(self.selected_character_id)
            self._batch_stop_requested = False
            QTimer.singleShot(5000, self.batch_progress_panel.hide)

    def _show_batch_progress(self, value: int, maximum: int, title: str | None = None) -> None:
        maximum = max(1, int(maximum))
        value = max(0, min(int(value), maximum))
        if title is not None:
            self._batch_progress_title = title
        percent = round(value * 100 / maximum)
        count_word = "von" if get_language() == "de" else "of"
        self.batch_progress.setRange(0, maximum)
        self.batch_progress.setValue(value)
        self.batch_progress.setFormat(f"{percent} %")
        self.batch_progress_label.setText(
            f"{self._batch_progress_title} …    {percent} % · {value} {count_word} {maximum}"
        )
        self.batch_progress_panel.show()

    def _refresh_saved_portrait(self, event: dict) -> bool:
        """Übernimmt nur das erwartete Ergebnis des aktiven Capture-Auftrags."""
        if self._active_worker_action not in {"capture", "capture_all"}:
            return False
        if self._active_worker_project_path != self.project_path or self.project_path is None:
            return False
        event_name = str(event.get("name") or "")
        if self._active_worker_action == "capture":
            member = self._member_by_id.get(str(self._active_worker_member_id or ""))
        elif self.v2_mode:
            try:
                received_path = Path(str(event.get("path") or "")).resolve()
                candidate = self._member_by_id.get(received_path.stem)
                member = (candidate if candidate is not None
                          and candidate.id in self._batch_member_ids
                          and normal_portrait_path(candidate.id, self.project_path).resolve()
                          == received_path else None)
            except (OSError, TypeError, ValueError):
                member = None
        else:
            batch_names = {name.casefold() for name in self._batch_names}
            member = next((
                candidate for candidate in self.character_members
                if candidate.name.casefold() == event_name.casefold()
                and candidate.name.casefold() in batch_names
            ), None)
        if member is None or event_name.casefold() != member.name.casefold():
            return False
        try:
            expected = normal_portrait_path(member.id, self.project_path).resolve()
            received = Path(str(event.get("path") or "")).resolve()
        except (OSError, TypeError, ValueError):
            return False
        if received != expected or not expected.is_file():
            return False
        pixmap = QPixmap(str(expected))
        if pixmap.isNull():
            return False

        self._refresh_character_rows()
        if member.id == self.selected_character_id:
            self.show_character(member.id)
        return True

    def _present_worker_semantic(self, semantic: dict) -> None:
        message = str(semantic.get("status") or semantic.get("name_status") or "")
        if message:
            self.worker_status_label.setText(message)
            self.statusBar().showMessage(message)
        if semantic.get("kind") == "error":
            dialog = semantic.get("dialog") or {}
            error = str(dialog.get("message") or message)
            self.worker_error_label.setText(error)
            self.worker_error_label.show()
        dialog = semantic.get("dialog") or {}
        if dialog.get("type") in {"info", "error", "text"}:
            box = QMessageBox(self)
            box.setWindowTitle(str(dialog.get("title") or APP_NAME))
            box.setText(str(dialog.get("message") or message))
            box.setIcon(
                QMessageBox.Icon.Information
                if dialog.get("type") == "info"
                else QMessageBox.Icon.Critical
            )
            box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            self._worker_message_box = box
            box.show()

    def _store_armory_result(self, result: dict) -> None:
        if self._active_worker_project_path != self.project_path:
            return
        incoming_id = str(result.get("memberId") or "").strip()
        member = self._member_by_id.get(incoming_id) if incoming_id else None
        if member is None and self._active_worker_member_id:
            selected = self._member_by_id.get(self._active_worker_member_id)
            if (selected is not None and selected.name.casefold()
                    == str(result.get("characterName") or "").strip().casefold()):
                member = selected
        if member is None:
            name = str(result.get("characterName") or "").strip().casefold()
            matches = [
                candidate for candidate in self.character_members
                if candidate.name.casefold() == name
            ]
            member = matches[0] if len(matches) == 1 else None
        if member is None:
            return
        if self._active_worker_member_id and member.id != self._active_worker_member_id:
            return
        self.armory_results[member.id] = dict(result)
        if (not self.v2_mode and self.project_path is not None
                and not member.id.startswith("working:")):
            try:
                self._dispatch_project_action(
                    "update_member_metadata",
                    {
                        "memberId": member.id,
                        "race": result.get("race"),
                        "className": result.get("className"),
                    },
                )
            except Exception as exc:
                self.worker_error_label.setText(
                    tr("grabber.project_metadata_save_failed", error=exc)
                )
                self.worker_error_label.show()
        self._refresh_character_rows()
        if member.id == self.selected_character_id:
            self._refresh_selected_armory_result()

    def _refresh_selected_armory_result(self) -> None:
        member = self._selected_member()
        result = self.armory_results.get(member.id) if member else None
        if not result:
            self.armory_result_label.clear()
            return
        race = race_display(result.get("race")) if result.get("race") else tr(
            "grabber.not_recognized"
        )
        class_name = result.get("className") or tr("grabber.not_recognized")
        self.character_race_value.setText(race)
        self._set_character_class_presentation(class_name)
        self.armory_result_label.setText(tr(
            "grabber.data_read", name=member.name, race=race, class_name=class_name,
        ))

    def _update_armory_controls(self) -> None:
        enabled = (
            self._selected_member() is not None
            and self._active_worker_action is None
            and not self._worker_closed
        )
        self.open_browser_button.setEnabled(enabled)
        self.capture_portrait_button.setEnabled(enabled and self.project_path is not None)
        self.read_armory_button.setEnabled(enabled)
        pending_roster_save = self._pending_roster_save_token is not None
        roster_idle = self._active_worker_action is None and not self._worker_closed
        active_list = self._portrait_list_mode == "active"
        self.active_portraits_button.setEnabled(roster_idle)
        self.inactive_portraits_button.setEnabled(roster_idle)
        self.add_character_button.setEnabled(
            active_list and roster_idle and not pending_roster_save
        )
        self.import_list_button.setEnabled(
            active_list and roster_idle and not pending_roster_save
        )
        self.import_wcl_button.setEnabled(
            active_list and roster_idle and not pending_roster_save
        )
        self.remove_character_button.setEnabled(
            enabled and not pending_roster_save
        )
        self.save_guild_list_button.setEnabled(
            active_list
            and self.project_path is not None
            and bool(self.character_members)
            and roster_idle
            and not pending_roster_save
        )
        batch_enabled = (
            self.project_path is not None
            and bool(self.character_members)
            and self._active_worker_action is None
            and not self._worker_closed
        )
        self.capture_missing_button.setEnabled(batch_enabled)
        self.capture_all_button.setEnabled(batch_enabled)
        self.read_missing_data_button.setEnabled(batch_enabled)
        self.stop_batch_button.setEnabled(
            self._active_worker_action in {"capture_all", "read_data_all"}
            and not self._batch_stop_requested
            and not self._worker_closed
        )
        self.stop_batch_button.setText(
            tr("grabber.stop_requested_short")
            if self._batch_stop_requested else tr("grabber.stop")
        )
        self.open_project_button.setEnabled(
            self._active_worker_action is None and not self._worker_closed
        )
        self.settings_open_project_button.setEnabled(
            self._active_worker_action is None and not self._worker_closed
        )
        self.browser_test_button.setEnabled(
            self._active_worker_action is None and not self._worker_closed
        )
        self.calibrate_crop_button.setEnabled(enabled)
        region_enabled = self._active_worker_action is None and not self._worker_closed
        self.set_region_button.setEnabled(region_enabled)
        self.test_region_button.setEnabled(region_enabled)
        self.reset_region_button.setEnabled(region_enabled)
        member = self._selected_member()
        portrait_actions_enabled = (
            self.project_path is not None
            and member is not None
            and self._active_worker_action is None
            and not self._worker_closed
        )
        self.import_portrait_button.setEnabled(portrait_actions_enabled)
        self.remove_portrait_button.setEnabled(
            portrait_actions_enabled
            and member is not None
            and self._portrait_file_for(member) is not None
        )
        self.edit_portrait_button.setEnabled(
            portrait_actions_enabled
            and member is not None
            and self._portrait_file_for(member) is not None
        )

    def _portrait_file_for(self, member: Member) -> Path | None:
        if self.project_path is None:
            return None
        try:
            path = existing_portrait_for_member(member.id, self.project_path)
            return path if path is not None and path.is_file() else None
        except (OSError, TypeError, ValueError):
            return None

    def _refresh_portrait_management(self, member: Member, message: str) -> None:
        """Refresh one portrait result without rebuilding selection or project state."""
        self.worker_error_label.clear()
        self.worker_error_label.hide()
        self._refresh_character_rows()
        self.show_character(member.id)
        self.worker_status_label.setText(message)
        self.statusBar().showMessage(message)

    def _show_portrait_management_error(self, title: str, message: str) -> None:
        self.worker_status_label.setText(message)
        self.statusBar().showMessage(message)
        self.worker_error_label.setText(message)
        self.worker_error_label.show()
        QMessageBox.critical(self, title, message)

    def import_selected_portrait(self) -> bool:
        """Import one local image through the existing canonical portrait core."""
        member = self._selected_member()
        if member is None or self.project_path is None or self._active_worker_action is not None:
            return False
        source, _selected_filter = QFileDialog.getOpenFileName(
            self,
            tr("grabber.manual_portrait_title"),
            "",
            (
                f"{tr('grabber.images')} (*.png *.jpg *.jpeg *.webp *.bmp);;"
                "PNG (*.png);;JPEG (*.jpg *.jpeg);;WebP (*.webp);;Bitmap (*.bmp)"
            ),
        )
        if not source:
            return False
        try:
            import_active_portrait_image(Path(source), member.id, self.project_path)
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            message = tr("grabber.manual_portrait_error", error=exc)
            self._show_portrait_management_error(tr("grabber.manual_portrait"), message)
            return False
        self._refresh_portrait_management(
            member, tr("grabber.manual_portrait_saved", name=member.name),
        )
        return True

    def remove_selected_portrait(self) -> bool:
        """Remove only active portrait variants; project history remains untouched."""
        member = self._selected_member()
        if member is None or self.project_path is None or self._active_worker_action is not None:
            return False
        if self._portrait_file_for(member) is None:
            message = tr("grabber.portrait_not_available", name=member.name)
            self._refresh_portrait_management(member, message)
            return False
        if QMessageBox.question(
            self,
            tr("grabber.remove_portrait"),
            tr("grabber.remove_portrait_question", name=member.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return False
        try:
            remove_active_portrait_files(member.id, self.project_path)
        except OSError as exc:
            message = tr(
                "grabber.remove_portrait_error", name=member.name, error=exc,
            )
            self._show_portrait_management_error(tr("grabber.remove_portrait"), message)
            return False
        self._refresh_portrait_management(
            member, tr("grabber.portrait_removed", name=member.name),
        )
        return True

    def _clear_portrait_editor_dialog(self, *_args) -> None:
        self._portrait_editor_dialog = None

    def _portrait_editor_saved(self, member: Member, path: Path) -> None:
        """Refresh the edited active portrait without rebuilding project state."""
        if self.project_path is None:
            return
        self.portrait_preview.invalidate()
        self._refresh_portrait_management(
            member, tr("grabber.portrait_edited", name=member.name),
        )

    def edit_selected_portrait(self) -> bool:
        """Open the Qt editor for the selected portrait."""
        member = self._selected_member()
        portrait = self._portrait_file_for(member) if member is not None else None
        if member is None or portrait is None:
            message = tr("grabber.no_portrait_to_edit")
            self.worker_status_label.setText(message)
            self.statusBar().showMessage(message)
            return False
        if self._portrait_editor_dialog is not None and self._portrait_editor_dialog.isVisible():
            self._portrait_editor_dialog.raise_()
            self._portrait_editor_dialog.activateWindow()
            return True
        try:
            state = load_portrait_editor_state(portrait)
            destination = normal_portrait_path(member.id, self.project_path)
            dialog = PortraitEditorDialogQt(
                member.name,
                state,
                destination,
                on_saved=lambda saved, selected=member: self._portrait_editor_saved(
                    selected, saved,
                ),
                parent=self,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            message = tr("grabber.manual_portrait_error", error=exc)
            self._show_portrait_management_error(tr("grabber.edit_portrait"), message)
            return False
        dialog.finished.connect(self._clear_portrait_editor_dialog)
        self._portrait_editor_dialog = dialog
        dialog.show()
        return True

    def _rebuild_character_model(self, selected_id: str | None = None) -> None:
        selection = self.character_table.selectionModel()
        selection.blockSignals(True)
        sorting = self.character_table.isSortingEnabled()
        self.character_table.setSortingEnabled(False)
        self.character_model.setRowCount(0)
        name_counts: dict[str, int] = {}
        for member in self.character_members:
            key = member.name.casefold()
            name_counts[key] = name_counts.get(key, 0) + 1
        for member in self.character_members:
            name_item = QStandardItem(member.name)
            name_item.setData(member.id, Qt.ItemDataRole.UserRole)
            name_item.setToolTip(
                member.id if name_counts[member.name.casefold()] > 1 else "")
            items = [
                name_item,
                QStandardItem(),
                QStandardItem(),
                QStandardItem(),
                QStandardItem(),
            ]
            for item in items:
                item.setEditable(False)
            self.character_model.appendRow(items)
        self.character_table.setSortingEnabled(sorting)
        self._refresh_character_rows()
        selected_row = next((
            row for row in range(self.character_model.rowCount())
            if self.character_model.item(row, 0).data(Qt.ItemDataRole.UserRole) == selected_id
        ), -1)
        if selected_row < 0 and self.character_model.rowCount():
            selected_row = 0
        if selected_row >= 0:
            self.character_table.selectRow(selected_row)
            selected_member_id = self.character_model.item(selected_row, 0).data(
                Qt.ItemDataRole.UserRole
            )
        else:
            self.character_table.clearSelection()
            selected_member_id = None
        selection.blockSignals(False)
        self.show_character(selected_member_id)

    def _refresh_character_rows(self) -> None:
        headers = (
            tr("common.character"),
            tr("checker.race"),
            tr("common.class"),
            tr("grabber.status"),
            tr("common.portrait"),
        )
        self.character_model.setHorizontalHeaderLabels(headers)
        existing = 0
        for row in range(self.character_model.rowCount()):
            member_id = self.character_model.item(row, 0).data(Qt.ItemDataRole.UserRole)
            member = self._member_by_id.get(str(member_id))
            if member is None:
                continue
            portrait = self._portrait_file_for(member)
            armory_result = self.armory_results.get(member.id) or {}
            race = armory_result.get("race") or member.race
            class_name = armory_result.get("className") or member.className
            existing += int(portrait is not None)
            self.character_model.item(row, 0).setText(member.name)
            self.character_model.item(row, 1).setText(race_display(race))
            class_item = self.character_model.item(row, 2)
            display_class = class_name or tr("common.not_set")
            class_item.setText(display_class)
            class_color = CLASS_COLORS.get(str(class_name or ""))
            class_item.setForeground(QColor(class_color or "#d0d0d0"))
            icon_path = class_icon_path(str(class_name or "")) if class_name else None
            class_item.setIcon(
                QIcon(str(icon_path))
                if icon_path is not None and icon_path.is_file() else QIcon()
            )
            self.character_model.item(row, 3).setText(
                self._portrait_life_status(member.lifeStatus)
            )
            self.character_model.item(row, 4).setText(
                tr("grabber.portrait_exists") if portrait else tr("grabber.no_portrait")
            )
        total = len(self.character_members)
        self.character_summary_label.setText(tr(
            "grabber.summary", total=total, existing=existing, missing=total - existing,
        ))

    def _character_row_changed(self, current, _previous) -> None:
        if not current.isValid():
            self.show_character(None)
            return
        member_id = self.character_model.item(current.row(), 0).data(
            Qt.ItemDataRole.UserRole
        )
        self.show_character(str(member_id) if member_id else None)

    def show_character(self, member_id: str | None) -> None:
        member = self._member_by_id.get(str(member_id)) if member_id else None
        self.selected_character_id = member.id if member else None
        if member is None:
            self._clear_character_detail()
            return
        self.character_name_value.setText(member.name)
        self.character_race_value.setText(race_display(member.race))
        self._set_character_class_presentation(member.className)
        self.character_spec_value.setText(member.spec or tr("common.not_set"))
        self.character_life_value.setText(self._portrait_life_status(member.lifeStatus))
        url = self.armory_url_for_selected()
        self._armory_url_full = url
        self._refresh_armory_url_label()
        self._refresh_selected_armory_result()
        portrait = self._portrait_file_for(member)
        loaded = self.portrait_preview.set_portrait(
            portrait, tr("grabber.no_portrait_available")
        )
        self.portrait_status_label.setText(
            tr("grabber.portrait_available") if loaded
            else tr("grabber.no_portrait_available")
        )
        self.portrait_path_label.setText(str(portrait) if loaded and portrait else "")
        self.portrait_path_label.setToolTip(str(portrait) if portrait else "")
        if self.worker_status_label.text() == tr("grabber.select_character"):
            self.worker_status_label.clear()
        self._update_armory_controls()

    def _clear_character_detail(self) -> None:
        for value in (
            self.character_name_value,
            self.character_race_value,
            self.character_class_value,
            self.character_spec_value,
            self.character_life_value,
        ):
            value.setText("-")
        self.character_class_value.setStyleSheet("color: #d0d0d0;")
        self.character_class_icon_label.setPixmap(QPixmap())
        self.character_class_icon_label.setText("–")
        self.portrait_status_label.setText(tr("grabber.no_portrait_available"))
        self.portrait_preview.set_portrait(None, tr("grabber.select_character"))
        self.portrait_path_label.clear()
        self.portrait_path_label.setToolTip("")
        self.armory_result_label.clear()
        self._armory_url_full = ""
        self._refresh_armory_url_label()
        self._update_armory_controls()

    @staticmethod
    def _portrait_life_status(life_status: str) -> str:
        status = str(life_status or "").casefold()
        if status == "dead":
            return tr("grabber.status_dead")
        if status == "inactive":
            return tr("life.inactive")
        return tr("grabber.status_alive")

    def _set_character_class_presentation(self, class_name: str | None) -> None:
        class_name = str(class_name or "").strip()
        self.character_class_value.setText(class_name or tr("common.not_set"))
        self.character_class_value.setStyleSheet(
            f"color: {CLASS_COLORS.get(class_name, '#d0d0d0')};"
        )
        icon_path = class_icon_path(class_name) if class_name else None
        pixmap = (
            QPixmap(str(icon_path)).scaled(
                20, 20, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if icon_path is not None and icon_path.is_file() else QPixmap()
        )
        self.character_class_icon_label.setPixmap(pixmap)
        self.character_class_icon_label.setText("" if not pixmap.isNull() else "–")

    def _refresh_armory_url_label(self) -> None:
        url = self._armory_url_full
        if not url:
            self.armory_url_label.clear()
            self.armory_url_label.setToolTip("")
            return
        full_text = f"Armory: {url}"
        available = max(80, self.armory_url_label.width())
        self.armory_url_label.setText(
            self.armory_url_label.fontMetrics().elidedText(
                full_text, Qt.TextElideMode.ElideMiddle, available,
            )
        )
        self.armory_url_label.setToolTip(url)

    def _graveyard_template_for_member(self, member: Member):
        """Return the verified manifest entry referenced by a dead member, if any."""
        template = self._graveyard_templates_by_id.get(member.graveTemplateId)
        if template is not None:
            return template
        if self._graveyard_inventory is None or not member.gravestoneTemplate:
            return None
        template_id = self._graveyard_inventory.id_for_filename(member.gravestoneTemplate)
        return self._graveyard_templates_by_id.get(template_id) if template_id else None

    @staticmethod
    def _render_graveyard_preview(member: Member, template, portrait_path: Path | None):
        """Use the shared final-card renderer for the read-only Qt preview."""
        try:
            frame = prepare_gravestone_template(template.path, GRAVESTONE_CARD_SIZE)
            return render_gravestone_card(
                member,
                frame,
                portrait_path,
                GRAVESTONE_CARD_SIZE,
                template.default_text_safe_area,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return None

    def _refresh_graveyard_saved_preview(self, member: Member | None) -> None:
        """Render only the persisted gravestone state in the read-only detail view."""
        if member is None:
            return
        template = self._graveyard_template_for_member(member)
        if template is None:
            has_reference = bool(member.graveTemplateId or member.gravestoneTemplate)
            stone_status = (
                tr("grabber.graveyard_stone_not_manifest") if has_reference
                else tr("grabber.graveyard_no_stone")
            )
            self.graveyard_preview.set_pillow_image(None, stone_status)
            self.graveyard_preview_status_label.setText(stone_status)
            self.graveyard_preview_status_label.setToolTip("")
            return

        portrait = graveyard_preview_portrait_for_member(
            member.id, member.name, self.project_path,
        )
        card = self._render_graveyard_preview(member, template, portrait)
        rendered = self.graveyard_preview.set_pillow_image(
            card, tr("grabber.preview_unavailable", error="")
        )
        self.graveyard_preview_status_label.setText(
            tr(
                "grabber.graveyard_preview_candidate",
                stone=template.filename,
                category=(
                    gravestone_category_display(template.category)
                    if template.category else tr("common.not_set")
                ),
            ) if rendered else tr("grabber.preview_unavailable", error="")
        )
        self.graveyard_preview_status_label.setToolTip(
            str(template.path) if rendered else ""
        )

    def _clear_gravestone_editor_dialog(self, *_args) -> None:
        self._gravestone_editor_dialog = None

    def _save_gravestone_editor_draft(self) -> bool:
        """Validate and atomically persist the complete active editor draft."""
        dialog = self._gravestone_editor_dialog
        project_path = self.project_path
        if (dialog is None or project_path is None
                or self._pending_gravestone_save_token is not None):
            return False
        if self.v2_mode:
            return self._save_v2_gravestone_editor_draft(dialog, project_path)
        draft = dialog.state.draft
        try:
            # A broken template or renderer must never become the persisted state.
            dialog.render_draft()
            payload = load_project_payload(project_path)
            fresh_model = GuildModel()
            fresh_model.load_payload(payload, project_path)
            updated = fresh_model.set_gravestone_adjustment(
                dialog.state.member_id,
                draft.template_id,
                draft.portrait_offset_x,
                draft.portrait_offset_y,
                draft.portrait_zoom,
                draft.text_offset_x,
                draft.text_offset_y,
                draft.text_scale,
                draft.death_date,
            )
            updates = {
                "graveTemplateId": updated.graveTemplateId,
                "gravestoneTemplate": updated.gravestoneTemplate,
                "portraitOffsetX": updated.portraitOffsetX,
                "portraitOffsetY": updated.portraitOffsetY,
                "portraitZoom": updated.portraitZoom,
                "textOffsetX": updated.textOffsetX,
                "textOffsetY": updated.textOffsetY,
                "textScale": updated.textScale,
                "deathDate": updated.deathDate,
            }
            if self.session_id:
                token, receipt = self._dispatch_project_action(
                    "graveyard_save",
                    {"memberId": dialog.state.member_id, **updates},
                )
                if receipt is None:
                    self._pending_gravestone_save_token = token
                    self._pending_gravestone_save_started = time.monotonic()
                    self._pending_gravestone_save_member_id = dialog.state.member_id
                    self._pending_gravestone_save_project_path = project_path
                    dialog.save_button.setEnabled(False)
                    dialog.cancel_button.setEnabled(False)
                    self.checker_navigation_button.setEnabled(False)
                    message = tr("grabber.graveyard_save_handoff")
                    dialog.preview_status_label.setText(message)
                    self.statusBar().showMessage(message)
                    QTimer.singleShot(100, self._poll_gravestone_save_receipt)
                    return True
            else:
                patch_project_member(
                    project_path,
                    dialog.state.member_id,
                    updates,
                    allowed_fields=tuple(updates),
                )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            message = tr("grabber.graveyard_save_failed", error=exc)
            dialog.show_save_error(message)
            self.statusBar().showMessage(message)
            return False

        member_id = dialog.state.member_id
        if not self.load_project(project_path):
            message = tr("grabber.graveyard_save_failed", error=self.project_error or "")
            dialog.show_save_error(message)
            return False
        reloaded = self._graveyard_member_by_id.get(member_id)
        if reloaded is None:
            message = tr("grabber.graveyard_character_missing")
            dialog.show_save_error(message)
            return False
        dialog.accept()
        self.graveyard_assignment_status_label.setText(tr(
            "grabber.graveyard_stone_saved",
            name=reloaded.name,
            stone=reloaded.gravestoneTemplate,
        ))
        return True

    def _save_v2_gravestone_editor_draft(self, dialog, project_path: Path) -> bool:
        """Apply one V2 memberId edit to a freshly loaded project, atomically."""
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        from app.identity_v2_graveyard import set_member_gravestone_adjustment
        from app.identity_v2_storage import load_identity_v2, save_identity_v2

        draft = dialog.state.draft
        try:
            dialog.render_draft()
            fresh = load_identity_v2(project_path)
            inventory = self.project_model.gravestone_inventory()
            changed = set_member_gravestone_adjustment(
                fresh, dialog.state.member_id, draft.template_id,
                draft.portrait_offset_x, draft.portrait_offset_y,
                draft.portrait_zoom, draft.text_offset_x,
                draft.text_offset_y, draft.text_scale, inventory.by_id(),
            )
            save_identity_v2(changed, project_path)
            if not self.load_project(project_path):
                raise ValueError(self.project_error or "V2 reload failed")
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            message = tr("grabber.graveyard_save_failed", error=exc)
            dialog.show_save_error(message)
            self.statusBar().showMessage(message)
            return False
        member = self._graveyard_member_by_id.get(dialog.state.member_id)
        dialog.accept()
        if member is not None:
            self.graveyard_assignment_status_label.setText(tr(
                "grabber.graveyard_stone_saved",
                name=member.name, stone=member.gravestoneTemplate or member.graveTemplateId))
        return True

    def _poll_gravestone_save_receipt(self) -> None:
        token = self._pending_gravestone_save_token
        project_path = self._pending_gravestone_save_project_path
        member_id = self._pending_gravestone_save_member_id
        session_id = self.session_id
        if not token or project_path is None or not member_id or not session_id:
            return
        receipt = read_receipt(project_path, session_id, token)
        if receipt is None:
            if time.monotonic() - self._pending_gravestone_save_started <= 20.0:
                QTimer.singleShot(150, self._poll_gravestone_save_receipt)
                return
            self._finish_pending_gravestone_save(
                error=tr("grabber.graveyard_save_timeout"),
            )
            return
        if not receipt.get("ok"):
            self._finish_pending_gravestone_save(
                error=str(receipt.get("error") or tr("grabber.project_action_failed")),
            )
            return
        self._finish_pending_gravestone_save()

    def _finish_pending_gravestone_save(self, *, error: str = "") -> None:
        dialog = self._gravestone_editor_dialog
        project_path = self._pending_gravestone_save_project_path
        member_id = self._pending_gravestone_save_member_id
        self._pending_gravestone_save_token = None
        self._pending_gravestone_save_started = 0.0
        self._pending_gravestone_save_member_id = None
        self._pending_gravestone_save_project_path = None
        self.checker_navigation_button.setEnabled(True)
        if dialog is not None:
            dialog.save_button.setEnabled(True)
            dialog.cancel_button.setEnabled(True)
        if error:
            message = tr("grabber.graveyard_save_failed", error=error)
            if dialog is not None:
                dialog.show_save_error(message)
            self.statusBar().showMessage(message)
            return
        if project_path is None or member_id is None or not self.load_project(project_path):
            message = tr("grabber.graveyard_save_failed", error=self.project_error or "")
            if dialog is not None:
                dialog.show_save_error(message)
            self.statusBar().showMessage(message)
            return
        reloaded = self._graveyard_member_by_id.get(member_id)
        if reloaded is None:
            message = tr("grabber.graveyard_character_missing")
            if dialog is not None:
                dialog.show_save_error(message)
            self.statusBar().showMessage(message)
            return
        if dialog is not None:
            dialog.accept()
        self.graveyard_assignment_status_label.setText(tr(
            "grabber.graveyard_stone_saved",
            name=reloaded.name,
            stone=reloaded.gravestoneTemplate,
        ))

    def open_selected_gravestone_editor(self) -> bool:
        """Open the only volatile gravestone editor from persisted project state."""
        member = self._graveyard_member_by_id.get(
            str(self.selected_graveyard_member_id or "")
        )
        if member is None or self.project_model is None:
            return False
        if (
            self._gravestone_editor_dialog is not None
            and self._gravestone_editor_dialog.isVisible()
        ):
            self._gravestone_editor_dialog.raise_()
            self._gravestone_editor_dialog.activateWindow()
            return True
        try:
            _inventory, available = self.project_model.available_gravestone_templates(
                member.id
            )
            templates = [
                template for template in available
                if normalize_gravestone_category(template.category) is not None
            ]
            templates_by_id = {
                template.grave_template_id: template for template in templates
            }
            candidate_ids = [template.grave_template_id for template in templates]
            saved_template = self._graveyard_template_for_member(member)
            saved_template_id = (
                saved_template.grave_template_id if saved_template is not None
                else member.graveTemplateId
            )
            initial_template_id = str(
                saved_template_id
                or (candidate_ids[0] if candidate_ids else "")
            )
            portrait = graveyard_preview_portrait_for_member(
                member.id, member.name, self.project_path,
            )
            state = build_gravestone_editor_state(
                member,
                templates,
                portrait,
                initial_template_id=initial_template_id,
                saved_template_id=saved_template_id,
            )
            dialog = GravestoneEditorDialogQt(
                member,
                state,
                templates_by_id,
                candidate_ids,
                parent=self,
            )
            if self.v2_mode:
                dialog.death_date_edit.setEnabled(False)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            message = tr("grabber.gravestone_editor_open_failed", error=exc)
            self.graveyard_assignment_status_label.setText(message)
            self.statusBar().showMessage(message)
            return False
        dialog.save_requested.connect(self._save_gravestone_editor_draft)
        dialog.finished.connect(self._clear_gravestone_editor_dialog)
        self._gravestone_editor_dialog = dialog
        dialog.show()
        return True

    def _rebuild_graveyard_model(self, selected_id: str | None = None) -> None:
        selection = self.graveyard_table.selectionModel()
        selection.blockSignals(True)
        sorting = self.graveyard_table.isSortingEnabled()
        self.graveyard_table.setSortingEnabled(False)
        self.graveyard_model.setRowCount(0)
        for member in self.graveyard_members:
            name_item = QStandardItem(member.name)
            name_item.setData(member.id, Qt.ItemDataRole.UserRole)
            items = [name_item, QStandardItem(), QStandardItem(), QStandardItem(), QStandardItem()]
            for item in items:
                item.setEditable(False)
            self.graveyard_model.appendRow(items)
        self.graveyard_table.setSortingEnabled(sorting)
        self._refresh_graveyard_rows()
        selected_row = next((
            row for row in range(self.graveyard_model.rowCount())
            if self.graveyard_model.item(row, 0).data(Qt.ItemDataRole.UserRole) == selected_id
        ), -1)
        if selected_row < 0 and self.graveyard_model.rowCount():
            selected_row = 0
        if selected_row >= 0:
            self.graveyard_table.selectRow(selected_row)
            selected_member_id = self.graveyard_model.item(selected_row, 0).data(
                Qt.ItemDataRole.UserRole
            )
        else:
            self.graveyard_table.clearSelection()
            selected_member_id = None
        selection.blockSignals(False)
        self.show_graveyard_member(str(selected_member_id) if selected_member_id else None)

    def _refresh_graveyard_rows(self) -> None:
        self.graveyard_model.setHorizontalHeaderLabels((
            tr("common.character"),
            tr("checker.race"),
            tr("common.class"),
            tr("checker.death_date"),
            tr("grabber.graveyard_current_stone"),
        ))
        for row in range(self.graveyard_model.rowCount()):
            member_id = self.graveyard_model.item(row, 0).data(Qt.ItemDataRole.UserRole)
            member = self._graveyard_member_by_id.get(str(member_id))
            if member is None:
                continue
            template = self._graveyard_template_for_member(member)
            self.graveyard_model.item(row, 0).setText(member.name)
            self.graveyard_model.item(row, 1).setText(race_display(member.race))
            class_item = self.graveyard_model.item(row, 2)
            class_name = str(member.className or "")
            class_item.setText(class_name or tr("common.not_set"))
            class_item.setForeground(QColor(CLASS_COLORS.get(class_name, "#d0d0d0")))
            icon_path = class_icon_path(class_name) if class_name else None
            class_item.setIcon(
                QIcon(str(icon_path))
                if icon_path is not None and icon_path.is_file() else QIcon()
            )
            self.graveyard_model.item(row, 3).setText(
                member.deathDate or tr("common.not_set")
            )
            if template is not None:
                stone_text = template.filename
            elif member.graveTemplateId or member.gravestoneTemplate:
                stone_text = tr("grabber.graveyard_stone_not_manifest")
            else:
                stone_text = tr("grabber.graveyard_no_stone")
            self.graveyard_model.item(row, 4).setText(stone_text)
        count = len(self.graveyard_members)
        self.graveyard_summary_label.setText(
            tr("checker.graveyard_summary", count=count)
            if count else tr("checker.graveyard_empty")
        )

    def _graveyard_row_changed(self, current, _previous) -> None:
        if not current.isValid():
            self.show_graveyard_member(None)
            return
        member_id = self.graveyard_model.item(current.row(), 0).data(
            Qt.ItemDataRole.UserRole
        )
        self.show_graveyard_member(str(member_id) if member_id else None)

    def _graveyard_project_path(self) -> Path | None:
        if self.project_path is not None:
            return Path(self.project_path)
        model_path = getattr(self.project_model, "project_path", None)
        return Path(model_path) if model_path is not None else None

    def _selected_graveyard_member(self) -> Member | None:
        return self._graveyard_member_by_id.get(
            str(self.selected_graveyard_member_id or "")
        )

    def import_selected_graveyard_portrait(self) -> bool:
        member = self._selected_graveyard_member()
        project_path = self._graveyard_project_path()
        if member is None or project_path is None:
            return False
        source, _selected_filter = QFileDialog.getOpenFileName(
            self,
            tr("grabber.manual_portrait_title"),
            "",
            (
                f"{tr('grabber.images')} (*.png *.jpg *.jpeg *.webp *.bmp);;"
                "PNG (*.png);;JPEG (*.jpg *.jpeg);;WebP (*.webp);;Bitmap (*.bmp)"
            ),
        )
        if not source:
            return False
        try:
            # Stable memberId keeps a dead incarnation isolated from any later
            # character that happens to reuse the same visible name.
            import_active_portrait_image(Path(source), member.id, self.project_path)
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            message = tr("grabber.manual_portrait_error", error=exc)
            self.graveyard_assignment_status_label.setText(message)
            QMessageBox.critical(self, tr("grabber.manual_portrait"), message)
            return False
        self._refresh_graveyard_saved_preview(member)
        self.show_graveyard_member(member.id)
        self.graveyard_assignment_status_label.setText(
            tr("grabber.manual_portrait_saved", name=member.name)
        )
        return True

    def _graveyard_portrait_editor_saved(self, member: Member, _path: Path) -> None:
        self._refresh_graveyard_saved_preview(member)
        self.show_graveyard_member(member.id)
        self.graveyard_assignment_status_label.setText(
            tr("grabber.portrait_edited", name=member.name)
        )

    def edit_selected_graveyard_portrait(self) -> bool:
        member = self._selected_graveyard_member()
        project_path = self._graveyard_project_path()
        if member is None or project_path is None:
            return False
        portrait = graveyard_portrait_for_member(
            member.id, member.name, project_path
        )
        if portrait is None or not portrait.is_file():
            self.graveyard_assignment_status_label.setText(
                tr("grabber.no_portrait_to_edit")
            )
            return False
        if self._portrait_editor_dialog is not None and self._portrait_editor_dialog.isVisible():
            self._portrait_editor_dialog.raise_()
            self._portrait_editor_dialog.activateWindow()
            return True
        try:
            state = load_portrait_editor_state(portrait)
            destination = normal_portrait_path(member.id, self.project_path)
            dialog = PortraitEditorDialogQt(
                member.name,
                state,
                destination,
                on_saved=lambda saved, selected=member: self._graveyard_portrait_editor_saved(
                    selected, saved
                ),
                parent=self,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            message = tr("grabber.manual_portrait_error", error=exc)
            self.graveyard_assignment_status_label.setText(message)
            QMessageBox.critical(self, tr("grabber.edit_portrait"), message)
            return False
        dialog.finished.connect(self._clear_portrait_editor_dialog)
        self._portrait_editor_dialog = dialog
        dialog.show()
        return True

    def show_graveyard_member(self, member_id: str | None) -> None:
        """Display persisted details and enable ID-safe graveyard editing actions."""
        member = self._graveyard_member_by_id.get(str(member_id)) if member_id else None
        self.selected_graveyard_member_id = member.id if member else None
        if member is None:
            self._clear_graveyard_detail()
            return
        project_path = self._graveyard_project_path()
        self.graveyard_heading_label.setText(member.name)
        self.graveyard_name_value.setText(member.name)
        self.graveyard_race_value.setText(race_display(member.race))
        self._set_graveyard_class_presentation(member.className)
        self.graveyard_spec_value.setText(member.spec or tr("common.not_set"))
        self.graveyard_life_value.setText(tr(f"life.{member.lifeStatus}"))
        self.graveyard_death_value.setText(member.deathDate or tr("common.not_set"))

        template = self._graveyard_template_for_member(member)
        if template is None:
            has_reference = bool(member.graveTemplateId or member.gravestoneTemplate)
            stone_status = (
                tr("grabber.graveyard_stone_not_manifest") if has_reference
                else tr("grabber.graveyard_no_stone")
            )
            self.graveyard_stone_value.setText(stone_status)
            self.graveyard_category_value.setText(tr("common.not_set"))
        else:
            self.graveyard_stone_value.setText(template.filename)
            self.graveyard_category_value.setText(
                gravestone_category_display(template.category)
                if template.category else tr("common.not_set")
            )
        self.graveyard_edit_stone_button.setEnabled(bool(
            self.project_model is not None and self._graveyard_templates_by_id
        ))
        graveyard_portrait = graveyard_portrait_for_member(
            member.id, member.name, project_path
        )
        self.graveyard_import_portrait_button.setEnabled(project_path is not None)
        self.graveyard_edit_portrait_button.setEnabled(bool(
            graveyard_portrait is not None and graveyard_portrait.is_file()
        ))
        self.graveyard_assignment_status_label.clear()
        self._refresh_graveyard_saved_preview(member)

    def _set_graveyard_class_presentation(self, class_name: str | None) -> None:
        class_name = str(class_name or "").strip()
        self.graveyard_class_value.setText(class_name or tr("common.not_set"))
        self.graveyard_class_value.setStyleSheet(
            f"color: {CLASS_COLORS.get(class_name, '#d0d0d0')};"
        )
        icon_path = class_icon_path(class_name) if class_name else None
        pixmap = (
            QPixmap(str(icon_path)).scaled(
                20, 20, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if icon_path is not None and icon_path.is_file() else QPixmap()
        )
        self.graveyard_class_icon_label.setPixmap(pixmap)
        self.graveyard_class_icon_label.setText("" if not pixmap.isNull() else "–")

    def _clear_graveyard_detail(self) -> None:
        self.graveyard_heading_label.setText(tr("grabber.graveyard_no_character"))
        for value in (
            self.graveyard_name_value,
            self.graveyard_race_value,
            self.graveyard_class_value,
            self.graveyard_spec_value,
            self.graveyard_life_value,
            self.graveyard_death_value,
            self.graveyard_stone_value,
            self.graveyard_category_value,
        ):
            value.setText("-")
        self.graveyard_class_value.setStyleSheet("color: #d0d0d0;")
        self.graveyard_class_icon_label.setPixmap(QPixmap())
        self.graveyard_class_icon_label.setText("–")
        self.graveyard_preview_status_label.setText(tr("grabber.graveyard_no_stone"))
        self.graveyard_preview_status_label.setToolTip("")
        self.graveyard_preview.set_pillow_image(None, tr("grabber.graveyard_no_character"))
        self.graveyard_edit_stone_button.setEnabled(False)
        self.graveyard_import_portrait_button.setEnabled(False)
        self.graveyard_edit_portrait_button.setEnabled(False)
        self.graveyard_assignment_status_label.clear()

    def refresh_texts(self) -> None:
        """Übernimmt die aktuelle Sprache aus der gemeinsamen i18n-Instanz."""
        title = tr("grabber.title")
        self.setWindowTitle(f"{title} · Qt v{APP_VERSION}")
        self.open_project_button.setText(tr("grabber.open_project"))
        self.checker_navigation_button.setText(
            "Zurück zum Gearchecker" if self.session_id else "Im Gearchecker öffnen"
            if get_language() == "de" else
            "Back to Gear Checker" if self.session_id else "Open in Gear Checker"
        )
        self.portrait_list_label.setText(tr("grabber.portrait_list"))
        self.active_portraits_button.setText(tr("grabber.active_characters"))
        self.inactive_portraits_button.setText(tr("grabber.inactive_characters"))
        self.open_browser_button.setText(tr("grabber.open_browser"))
        self.capture_portrait_button.setText(tr("grabber.create_portrait"))
        self.read_armory_button.setText(tr("grabber.read_data"))
        self.read_missing_data_button.setText(tr("grabber.read_missing_data"))
        self.capture_missing_button.setText(tr("grabber.create_missing"))
        self.capture_all_button.setText(tr("grabber.create_all"))
        self.stop_batch_button.setText(
            tr("grabber.stop_requested_short")
            if self._batch_stop_requested else tr("grabber.stop")
        )
        self.import_portrait_button.setText(tr("grabber.manual_portrait"))
        self.remove_portrait_button.setText(tr("grabber.remove_portrait"))
        self.edit_portrait_button.setText(tr("grabber.edit_portrait"))
        self.add_character_button.setText(tr("grabber.add_character"))
        self.remove_character_button.setText(tr("grabber.remove"))
        self.import_list_button.setText(tr("grabber.import_list"))
        self.import_wcl_button.setText(tr("grabber.import_wcl"))
        self.save_guild_list_button.setText(tr("grabber.save_guild_list"))
        self.roster_actions_group.setTitle(tr("grabber.roster_actions"))
        self.batch_actions_group.setTitle(tr("grabber.batch_actions"))
        self.character_actions_group.setTitle(tr("grabber.character_actions"))
        self.portrait_actions_group.setTitle(tr("grabber.portrait_actions"))
        self.tabs.setTabText(
            self.tabs.indexOf(self.portraits_page), tr("grabber.overview")
        )
        self.tabs.setTabText(
            self.tabs.indexOf(self.graveyard_page), tr("grabber.graveyard_tab")
        )
        self.tabs.setTabText(self.tabs.indexOf(self.settings_page), tr("grabber.settings"))
        self.tabs.setTabText(self.tabs.indexOf(self.review_page), tr("qt_review.tab_title"))
        self.playwright_crop_group.setTitle(tr("grabber.playwright_crop"))
        self.playwright_crop_help_label.setText(tr("grabber.playwright_crop_help"))
        self.calibrate_crop_button.setText(tr("grabber.calibrate"))
        self.standard_crop_group.setTitle(tr("grabber.standard_crop"))
        self.standard_crop_help_label.setText(tr("grabber.standard_crop_help"))
        self.set_region_button.setText(tr("grabber.set_region"))
        self.test_region_button.setText(tr("grabber.test_region"))
        self.reset_region_button.setText(tr("grabber.reset"))
        self._refresh_screen_region_text()

        self.crop_settings_group.setTitle(
            "Aufnahme & Ausschnitt" if get_language() == "de" else "Capture & Crop"
        )
        self.armory_settings_group.setTitle(
            "Armory / Aufnahme" if get_language() == "de" else "Armory / Capture"
        )
        self.game_version_label.setText(tr("grabber.game_version"))
        self.guild_name_label.setText(
            f"{tr('grabber.guild_name')} ({tr('grabber.disabled_suffix')})"
        )
        self.output_folder_label.setText(tr("grabber.output_folder"))
        self.settings_open_project_button.setText(tr("grabber.open_project"))
        capture_mode = self.config_data.get("capture_mode", "playwright")
        self.capture_mode_combo.blockSignals(True)
        self.capture_mode_combo.clear()
        self.capture_mode_combo.addItem(tr("grabber.mode_playwright"), "playwright")
        self.capture_mode_combo.addItem(
            tr("grabber.mode_standard"), "standard_browser_region"
        )
        self.capture_mode_combo.setCurrentIndex(max(
            0, self.capture_mode_combo.findData(capture_mode)
        ))
        self.capture_mode_combo.blockSignals(False)
        self.standard_wait_spin.setEnabled(
            self.capture_mode_combo.currentData() == "standard_browser_region"
        )
        self.wait_seconds_label.setText(tr("grabber.wait_seconds"))
        self.general_diagnostics_group.setTitle(
            "Allgemein / Diagnose" if get_language() == "de" else "General / Diagnostics"
        )
        self.language_label.setText(tr("language.label"))
        current_language = get_language()
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        self.language_combo.addItems(language_display_values())
        self.language_combo.setCurrentIndex(0 if current_language == "de" else 1)
        self.language_combo.blockSignals(False)
        self.diagnostics_label.setText(tr("grabber.diagnostics"))
        self.browser_test_button.setText(tr("grabber.browser_test"))
        self.browser_order_label.setText(tr("grabber.browser_order"))
        self.settings_help_label.setText(tr("grabber.settings_help"))
        self._refresh_settings_project_path()
        self.selection_heading_label.setText(tr("grabber.selection"))
        form_texts = {
            "name": tr("common.character"),
            "race": tr("checker.race"),
            "class": tr("common.class"),
            "spec": tr("common.spec"),
            "life": tr("grabber.status"),
        }
        for key, label in self._detail_form_labels.items():
            label.setText(form_texts[key])
        self.active_portraits_button.setChecked(self._portrait_list_mode == "active")
        self.inactive_portraits_button.setChecked(self._portrait_list_mode == "inactive")
        self._refresh_character_rows()
        if self.selected_character_id:
            self.show_character(self.selected_character_id)
        else:
            self._clear_character_detail()

        self.graveyard_heading_label.setText(tr("grabber.graveyard_characters"))
        graveyard_form_texts = {
            **form_texts,
            "death": tr("checker.death_date"),
            "stone": tr("grabber.graveyard_current_stone"),
            "category": tr("common.category"),
        }
        for key, label in self._graveyard_detail_form_labels.items():
            label.setText(graveyard_form_texts[key])
        self.graveyard_edit_stone_button.setText(
            tr("grabber.graveyard_edit_stone")
        )
        self.graveyard_import_portrait_button.setText(tr("grabber.manual_portrait"))
        self.graveyard_edit_portrait_button.setText(tr("grabber.edit_portrait"))
        self._refresh_graveyard_rows()
        if self.selected_graveyard_member_id:
            self.show_graveyard_member(self.selected_graveyard_member_id)
        else:
            self._clear_graveyard_detail()

        if self.project_path is not None:
            project_text = tr("grabber.project_label", name=self.project_path.name)
            self.project_status_label.setText(project_text)
            self.project_status_label.setToolTip(str(self.project_path))
            self.project_detail_label.setText(str(self.project_path))
            self.project_detail_label.setToolTip(str(self.project_path))
            self.banner.set_metadata(
                guild=self.guild_name_edit.text().strip() or APP_NAME,
                project=self.project_path.name,
                project_path=str(self.project_path),
            )
            if self.project_error:
                self.statusBar().showMessage(
                    tr("grabber.project_open_failed", error=self.project_error)
                )
            else:
                self.statusBar().showMessage(
                    tr("grabber.project_opened", name=self.project_path.name)
                )
        else:
            self.project_status_label.setText(tr("grabber.no_project_loaded"))
            self.project_status_label.setToolTip("")
            self.project_detail_label.clear()
            self.project_detail_label.setToolTip("")
            self.banner.set_metadata(
                guild=self.guild_name_edit.text().strip() or APP_NAME,
                project=tr("grabber.no_project_loaded"), project_path="",
            )
            if self.project_error:
                self.statusBar().showMessage(
                    tr("grabber.project_open_failed", error=self.project_error)
                )
            else:
                self.statusBar().showMessage(tr("grabber.no_project_loaded"))
        if self._last_worker_event is not None:
            self._present_worker_semantic(
                interpret_worker_event(self._last_worker_event)
            )
        elif not self.worker_status_label.text():
            self.worker_status_label.setText(tr("grabber.select_character"))
        self._refresh_selected_armory_result()
        self._update_armory_controls()

    def closeEvent(self, event) -> None:
        self._save_window_state()
        if not self._worker_closed:
            self._worker_closed = True
            self.worker_poll_timer.stop()
            try:
                self._request_worker_cancel_once()
                self.worker.submit("stop")
            except Exception:
                pass
        event.accept()


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_cli(argv)
    application, owns_application = create_application(argv=[])
    window = GuildPortraitGrabberQt(
        project_path=args.project or None,
        session_id=args.session_id or None,
    )
    window.show()

    # Bei Einbettung in eine bereits laufende Qt-Anwendung darf kein zweiter
    # Eventloop gestartet werden. Die Referenz hält das Fenster dort am Leben.
    windows = getattr(application, "_ggc_portrait_grabber_windows", [])
    windows.append(window)
    application._ggc_portrait_grabber_windows = windows
    return application.exec() if owns_application else 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
