"""PySide6 presentation for the existing gravestone review workflow.

The module owns presentation and delegates queue/category/release operations to
the existing review core. Manifest authority, validation and file transactions
therefore remain shared with the Tk review tool.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QFormLayout, QFrame,
    QFileDialog, QGridLayout, QHeaderView, QHBoxLayout, QLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSlider, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)
from PIL import Image, ImageFilter
from PIL.ImageQt import ImageQt

from app.gravestone_categories import (
    GRAVESTONE_CATEGORIES,
    GRAVESTONE_DEFAULT_OFFSET_X_FIELD, GRAVESTONE_DEFAULT_OFFSET_Y_FIELD,
    GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD, GRAVESTONE_DEFAULT_ZOOM_FIELD,
    load_gravestone_category,
    load_gravestone_portrait_preset, load_gravestone_text_safe_area,
    normalize_gravestone_category,
    save_gravestone_portrait_preset,
)
from app.gravestone_templates import promote_approved_gravestones
from app.gravestone_portrait import detect_portrait_opening, portrait_layer
from app.i18n import gravestone_category_display, tr
from tools.gravestone_review.gravestone_review_core import (
    AssetValidator, GeometryConfig, OpeningAnalysis, ProductiveEntry, accept_candidate,
    approve_accepted, delete_rejected, list_accepted, list_approved,
    list_candidates, list_productive, list_rejected, reject_candidate,
    opening_transparency_metrics, restore_accepted, review_counts,
    review_workspace, set_review_category,
)
from tools.gravestone_review.gravestone_review_tool import GraveyardRenderer
from tools.gravestone_review.gravestone_alpha_editor import (
    AlphaMaskSession,
    save_alpha_edit_atomic,
)


QUEUE_ORDER = ("candidates", "accepted", "rejected", "approved", "productive")
QUEUE_LABEL_KEYS = {
    "candidates": "review.queue_candidates", "accepted": "review.queue_accepted",
    "rejected": "review.queue_rejected", "approved": "review.queue_approved",
    "productive": "review.queue_productive",
}
QUEUE_STATUS_KEYS = {
    "candidates": "qt_review.status_candidates", "accepted": "qt_review.status_accepted",
    "rejected": "qt_review.status_rejected", "approved": "qt_review.status_approved",
    "productive": "qt_review.status_productive",
}
VIEW_ORDER = ("gallery", "list")
VIEW_LABEL_KEYS = {
    "gallery": "qt_review.view_gallery",
    "list": "qt_review.view_list",
}


class ReviewPreviewLabel(QLabel):
    """Preview label that reports incremental drag movement to the review widget."""

    dragged = Signal(QPoint)
    pointer_pressed = Signal(QPoint)
    pointer_moved = Signal(QPoint)
    pointer_released = Signal(QPoint)

    def __init__(self, text: str):
        super().__init__(text)
        self._drag_position: QPoint | None = None
        self._edit_ellipse: tuple[int, int, int, int] | None = None
        self._edit_source_size: tuple[int, int] | None = None

    def pixmap_display_rect(self) -> QRectF | None:
        pixmap = self.pixmap()
        if pixmap.isNull():
            return None
        contents = self.contentsRect()
        width = float(pixmap.width())
        height = float(pixmap.height())
        return QRectF(
            contents.x() + (contents.width() - width) / 2.0,
            contents.y() + (contents.height() - height) / 2.0,
            width,
            height,
        )

    def set_edit_ellipse(
        self,
        bbox: tuple[int, int, int, int] | None,
        source_size: tuple[int, int] | None = None,
    ) -> None:
        self._edit_ellipse = bbox
        self._edit_source_size = source_size
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        bbox = self._edit_ellipse
        source_size = self._edit_source_size
        display = self.pixmap_display_rect()
        if bbox is None or source_size is None or display is None:
            return
        source_width, source_height = source_size
        if source_width <= 0 or source_height <= 0:
            return
        x1, y1, x2, y2 = bbox
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        ellipse = QRectF(
            display.left() + left * display.width() / source_width,
            display.top() + top * display.height() / source_height,
            max(1.0, (right - left) * display.width() / source_width),
            max(1.0, (bottom - top) * display.height() / source_height),
        )
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QPen(QColor(255, 225, 59), 3))
            painter.drawEllipse(ellipse)
        finally:
            painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.position().toPoint()
            self.pointer_pressed.emit(self._drag_position)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._drag_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            position = event.position().toPoint()
            self.dragged.emit(position - self._drag_position)
            self.pointer_moved.emit(position)
            self._drag_position = position
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.pointer_released.emit(event.position().toPoint())
        self._drag_position = None
        super().mouseReleaseEvent(event)


class QtGravestoneReviewWidget(QWidget):
    """Reusable queue, presentation and action component for Qt surfaces."""

    def __init__(self, project_root: Path, tool_dir: Path | None = None,
                 parent: QWidget | None = None,
                 splitter_sizes: list[int] | None = None):
        super().__init__(parent)
        self.project_root = Path(project_root).expanduser().resolve()
        self.tool_dir = Path(tool_dir or Path(__file__).resolve().parent)
        self.workspace = review_workspace(self.project_root)
        self.geometry = GeometryConfig.load(self.tool_dir / "master_geometry.json")
        self.validator = AssetValidator(self.geometry)
        self.renderer = GraveyardRenderer(self.geometry, self.tool_dir, self.project_root)
        self._current_analysis = None
        self._preview_mode = "composite"
        self._demo_offset_x = 0.0
        self._demo_offset_y = 0.0
        self._demo_zoom = 1.0
        self._alpha_session: AlphaMaskSession | None = None
        self._alpha_source_path: Path | None = None
        self._alpha_source_queue: str | None = None
        self._alpha_source_signature: tuple[str, int, int] | None = None
        self._alpha_initial_ellipse: tuple[int, int, int, int] | None = None
        self._alpha_initial_text_safe_area: tuple[int, int, int, int] | None = None
        self._alpha_tool = "ellipse"
        self._alpha_preview_mode = "opening"
        self._alpha_drag_start: tuple[int, int] | None = None
        self._alpha_move_origin: tuple[int, int, int, int] | None = None
        self._alpha_guide_bbox: tuple[int, int, int, int] | None = None
        self._alpha_stroke_active = False
        self._entries: dict[str, list[tuple[Path, dict]]] = {name: [] for name in QUEUE_ORDER}
        self._lists: dict[str, QListWidget] = {}
        self._tabs: dict[str, int] = {}
        self._category_buttons: dict[str, QPushButton] = {}
        self._action_buttons: dict[str, QPushButton] = {}
        self._view_buttons: dict[str, QPushButton] = {}
        self._thumbnail_cache: dict[tuple, QPixmap] = {}
        self._preview_cache: dict[tuple, QPixmap] = {}
        self._image_metadata_cache: dict[tuple[str, int, int], tuple[str, str]] = {}
        self._sidecar_cache: dict[tuple[str, int, int], dict] = {}
        self._gallery_render_key: tuple | None = None
        self._gallery_buttons: dict[str, QPushButton] = {}
        self._productive_gallery_render_key: tuple | None = None
        self._prefetch_lock = threading.Lock()
        self._prefetch_signature: tuple[str, int, int] | None = None
        self._prefetch_result = None
        self._prefetch_running_signature: tuple[str, int, int] | None = None
        self._initial_splitter_sizes = splitter_sizes
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("gravestoneReviewQueues")
        outer.addWidget(self.tabs)
        for queue_name in QUEUE_ORDER:
            listing = QListWidget(self)
            listing.setObjectName(f"gravestoneReview{queue_name.title()}List")
            listing.hide()
            listing.currentItemChanged.connect(
                lambda current, _previous, name=queue_name: self._select_item(name, current)
            )
            self._lists[queue_name] = listing
            self._tabs[queue_name] = self.tabs.addTab(QWidget(), tr(QUEUE_LABEL_KEYS[queue_name]))
        self.tabs.setMaximumHeight(self.tabs.tabBar().sizeHint().height() + 8)

        self.view_controls = QWidget()
        view_layout = QHBoxLayout(self.view_controls)
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.addWidget(QLabel(tr("qt_review.view_label")))
        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        for index, view_name in enumerate(VIEW_ORDER):
            button = QPushButton(tr(VIEW_LABEL_KEYS[view_name]))
            button.setObjectName(f"gravestoneReview{view_name.title()}ViewButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, name=view_name: self._set_view(name))
            self.view_group.addButton(button)
            self._view_buttons[view_name] = button
            view_layout.addWidget(button)
            if index == 0:
                button.setChecked(True)
        view_layout.addStretch(1)
        outer.addWidget(self.view_controls)

        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.workspace_splitter.setObjectName("gravestoneReviewWorkspaceSplitter")
        outer.addWidget(self.workspace_splitter, 1)
        self.productive_gallery_scroll = QScrollArea()
        self.productive_gallery_scroll.setObjectName("gravestoneReviewProductiveGallery")
        self.productive_gallery_scroll.setWidgetResizable(True)
        self.productive_gallery_content = QWidget()
        self.productive_gallery_grid = QGridLayout(self.productive_gallery_content)
        self.productive_gallery_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.productive_gallery_scroll.setWidget(self.productive_gallery_content)
        self.productive_gallery_scroll.setVisible(False)
        outer.addWidget(self.productive_gallery_scroll, 1)
        self.view_stack = QStackedWidget()
        self.view_stack.setObjectName("gravestoneReviewViewStack")

        preview_frame = QFrame()
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        navigation_layout = QHBoxLayout()
        self.previous_item_button = QPushButton(tr("qt_review.previous_item"))
        self.previous_item_button.setObjectName("gravestoneReviewPreviousButton")
        self.previous_item_button.clicked.connect(lambda: self._navigate_relative(-1))
        navigation_layout.addWidget(self.previous_item_button)
        self.item_position_label = QLabel(tr("qt_review.item_position_empty"))
        self.item_position_label.setObjectName("gravestoneReviewItemPosition")
        self.item_position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        navigation_layout.addWidget(self.item_position_label, 1)
        self.next_item_button = QPushButton(tr("qt_review.next_item"))
        self.next_item_button.setObjectName("gravestoneReviewNextButton")
        self.next_item_button.clicked.connect(lambda: self._navigate_relative(1))
        navigation_layout.addWidget(self.next_item_button)
        preview_layout.addLayout(navigation_layout)
        self.preview_label = ReviewPreviewLabel(tr("qt_review.no_preview"))
        self.preview_label.setObjectName("gravestoneReviewPreview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(260, 360)
        self.preview_label.setStyleSheet("background:#171717; color:#d0d0d0;")
        self.preview_label.dragged.connect(self._move_demo_portrait)
        self.preview_label.pointer_pressed.connect(self._alpha_pointer_pressed)
        self.preview_label.pointer_moved.connect(self._alpha_pointer_moved)
        self.preview_label.pointer_released.connect(self._alpha_pointer_released)
        preview_layout.addWidget(self.preview_label)

        self.normal_preview_controls = QWidget()
        normal_preview_layout = QVBoxLayout(self.normal_preview_controls)
        normal_preview_layout.setContentsMargins(0, 0, 0, 0)
        normal_preview_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        mode_layout = QHBoxLayout()
        self.preview_mode_group = QButtonGroup(self)
        self.preview_mode_group.setExclusive(True)
        for mode, label_key in (
            ("original", "review.mode_original"),
            ("composite", "review.mode_composite"),
            ("opening", "review.mode_opening_check"),
        ):
            button = QPushButton(tr(label_key))
            button.setObjectName(f"gravestoneReview{mode.title()}ModeButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, value=mode: self._set_preview_mode(value))
            self.preview_mode_group.addButton(button)
            mode_layout.addWidget(button)
            if mode == self._preview_mode:
                button.setChecked(True)
        normal_preview_layout.addLayout(mode_layout)

        demo_layout = QGridLayout()
        self.choose_demo_button = QPushButton(tr("review.change_portrait"))
        self.choose_demo_button.setObjectName("gravestoneReviewChooseDemoButton")
        self.choose_demo_button.clicked.connect(self._choose_demo_portrait)
        demo_layout.addWidget(self.choose_demo_button, 0, 0)
        self.reset_demo_button = QPushButton(tr("review.reset_demo_portrait"))
        self.reset_demo_button.setObjectName("gravestoneReviewResetDemoButton")
        self.reset_demo_button.clicked.connect(self._reset_demo_portrait)
        demo_layout.addWidget(self.reset_demo_button, 0, 1)
        demo_layout.addWidget(QLabel(tr("review.demo_zoom")), 1, 0)
        self.demo_zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.demo_zoom_slider.setObjectName("gravestoneReviewDemoZoom")
        self.demo_zoom_slider.setRange(100, 300)
        self.demo_zoom_slider.setValue(100)
        self.demo_zoom_slider.valueChanged.connect(self._demo_zoom_changed)
        demo_layout.addWidget(self.demo_zoom_slider, 1, 1)
        self.demo_transform_label = QLabel("X 0.00 · Y 0.00 · 1.00×")
        self.demo_transform_label.setObjectName("gravestoneReviewDemoTransform")
        demo_layout.addWidget(self.demo_transform_label, 2, 0, 1, 2)
        normal_preview_layout.addLayout(demo_layout)

        preset_layout = QGridLayout()
        self.save_preset_button = QPushButton(tr("review.save_preset"))
        self.save_preset_button.setObjectName("gravestoneReviewSavePresetButton")
        self.save_preset_button.clicked.connect(self._save_demo_portrait_preset)
        preset_layout.addWidget(self.save_preset_button, 0, 0)
        self.opening_diagnostics_label = QLabel(tr("review.opening_unknown"))
        self.opening_diagnostics_label.setObjectName("gravestoneReviewOpeningDiagnostics")
        self.opening_diagnostics_label.setWordWrap(True)
        preset_layout.addWidget(self.opening_diagnostics_label, 1, 0)
        normal_preview_layout.addLayout(preset_layout)
        preview_layout.addWidget(self.normal_preview_controls)

        self.alpha_controls = QFrame()
        self.alpha_controls.setObjectName("gravestoneReviewAlphaControls")
        alpha_layout = QVBoxLayout(self.alpha_controls)
        alpha_layout.setContentsMargins(0, 0, 0, 0)
        alpha_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        alpha_tools_layout = QGridLayout()
        self.alpha_tool_group = QButtonGroup(self)
        self.alpha_tool_group.setExclusive(True)
        self._alpha_tool_buttons: dict[str, QPushButton] = {}
        for tool, label_key in (
            ("ellipse", "alpha_editor.mode_draw_ellipse"),
            ("move", "alpha_editor.mode_move_ellipse"),
            ("erase", "alpha_editor.mode_erase"),
            ("restore", "alpha_editor.mode_restore"),
        ):
            button = QPushButton(tr(label_key))
            button.setObjectName(f"gravestoneReviewAlpha{tool.title()}Tool")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, value=tool: self._set_alpha_tool(value))
            self.alpha_tool_group.addButton(button)
            self._alpha_tool_buttons[tool] = button
            row, column = divmod(len(self._alpha_tool_buttons) - 1, 2)
            alpha_tools_layout.addWidget(button, row, column)
            if tool == self._alpha_tool:
                button.setChecked(True)
        alpha_layout.addLayout(alpha_tools_layout)

        alpha_settings_layout = QGridLayout()
        alpha_settings_layout.addWidget(QLabel(tr("alpha_editor.brush")), 0, 0)
        self.alpha_brush_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_brush_slider.setObjectName("gravestoneReviewAlphaBrushSize")
        self.alpha_brush_slider.setRange(4, 80)
        self.alpha_brush_slider.setValue(24)
        alpha_settings_layout.addWidget(self.alpha_brush_slider, 0, 1)
        alpha_settings_layout.addWidget(QLabel(tr("alpha_editor.feather")), 1, 0)
        self.alpha_feather_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_feather_slider.setObjectName("gravestoneReviewAlphaFeather")
        self.alpha_feather_slider.setRange(0, 10)
        self.alpha_feather_slider.setValue(2)
        alpha_settings_layout.addWidget(self.alpha_feather_slider, 1, 1)
        self.alpha_preview_group = QButtonGroup(self)
        self.alpha_preview_group.setExclusive(True)
        for mode, label_key in (
            ("opening", "alpha_editor.opening_check"),
            ("composite", "alpha_editor.composite"),
        ):
            button = QPushButton(tr(label_key))
            button.setObjectName(f"gravestoneReviewAlpha{mode.title()}Preview")
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked=False, value=mode: self._set_alpha_preview_mode(value)
            )
            self.alpha_preview_group.addButton(button)
            alpha_settings_layout.addWidget(button, 2, len(self.alpha_preview_group.buttons()) - 1)
            if mode == self._alpha_preview_mode:
                button.setChecked(True)
        alpha_layout.addLayout(alpha_settings_layout)

        alpha_history_layout = QGridLayout()
        self.alpha_reset_button = QPushButton(tr("common.reset"))
        self.alpha_reset_button.setObjectName("gravestoneReviewAlphaResetButton")
        self.alpha_reset_button.clicked.connect(self._alpha_reset)
        alpha_history_layout.addWidget(self.alpha_reset_button, 0, 0)
        self.alpha_undo_button = QPushButton(tr("alpha_editor.undo"))
        self.alpha_undo_button.setObjectName("gravestoneReviewAlphaUndoButton")
        self.alpha_undo_button.clicked.connect(self._alpha_undo)
        alpha_history_layout.addWidget(self.alpha_undo_button, 0, 1)
        self.alpha_redo_button = QPushButton(tr("alpha_editor.redo"))
        self.alpha_redo_button.setObjectName("gravestoneReviewAlphaRedoButton")
        self.alpha_redo_button.clicked.connect(self._alpha_redo)
        alpha_history_layout.addWidget(self.alpha_redo_button, 0, 2)
        self.alpha_status_label = QLabel(tr("alpha_editor.status_initial"))
        self.alpha_status_label.setObjectName("gravestoneReviewAlphaStatus")
        self.alpha_status_label.setWordWrap(True)
        alpha_history_layout.addWidget(self.alpha_status_label, 1, 0, 1, 3)
        self.alpha_save_button = QPushButton(tr("alpha_editor.apply_save"))
        self.alpha_save_button.setObjectName("gravestoneReviewAlphaSaveButton")
        self.alpha_save_button.clicked.connect(self._save_alpha_mode)
        alpha_history_layout.addWidget(self.alpha_save_button, 2, 0, 1, 2)
        self.alpha_close_button = QPushButton(tr("qt_review.alpha_close"))
        self.alpha_close_button.setObjectName("gravestoneReviewAlphaCloseButton")
        self.alpha_close_button.clicked.connect(self._close_alpha_mode)
        alpha_history_layout.addWidget(self.alpha_close_button, 2, 2)
        alpha_layout.addLayout(alpha_history_layout)
        self.alpha_controls.setVisible(False)
        preview_layout.addWidget(self.alpha_controls)
        self.gallery_scroll = QScrollArea()
        self.gallery_scroll.setObjectName("gravestoneReviewGallery")
        self.gallery_scroll.setWidgetResizable(True)
        self.gallery_content = QWidget()
        self.gallery_grid = QGridLayout(self.gallery_content)
        self.gallery_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.gallery_scroll.setWidget(self.gallery_content)
        self.view_stack.addWidget(self.gallery_scroll)

        self.list_table = QTableWidget(0, 4)
        self.list_table.setObjectName("gravestoneReviewTable")
        self.list_table.setHorizontalHeaderLabels([
            tr("qt_review.filename_short"), tr("qt_review.dimensions"),
            tr("qt_review.file_size"), tr("qt_review.category_short"),
        ])
        self.list_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.list_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_table.verticalHeader().setVisible(False)
        self.list_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 4):
            self.list_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.list_table.itemSelectionChanged.connect(self._list_selection_changed)
        self.view_stack.addWidget(self.list_table)
        self.workspace_splitter.addWidget(self.view_stack)

        self.detail_frame = QFrame()
        self.detail_frame.setObjectName("gravestoneReviewDetail")
        detail_layout = QVBoxLayout(self.detail_frame)
        self.file_details_panel = QWidget()
        form = QFormLayout(self.file_details_panel)
        self.filename_value, self.status_value = QLabel("–"), QLabel("–")
        self.category_value, self.preset_value = QLabel("–"), QLabel("–")
        form.addRow(tr("qt_review.filename"), self.filename_value)
        form.addRow(tr("qt_review.status"), self.status_value)
        form.addRow(tr("qt_review.category"), self.category_value)
        form.addRow(tr("qt_review.preset"), self.preset_value)
        detail_layout.addWidget(preview_frame, 1)
        self.readonly_notice = QLabel(tr("qt_review.readonly_notice"))
        self.readonly_notice.setObjectName("gravestoneReviewReadonlyNotice")
        self.readonly_notice.setWordWrap(True)
        detail_layout.addWidget(self.readonly_notice)

        category_layout = QGridLayout()
        self.category_group = QButtonGroup(self)
        self.category_group.setExclusive(True)
        for category in GRAVESTONE_CATEGORIES:
            button = QPushButton(gravestone_category_display(category))
            button.setObjectName(f"gravestoneReviewCategory{category}")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, value=category: self._set_category(value))
            self.category_group.addButton(button)
            self._category_buttons[category] = button
            row, column = divmod(len(self._category_buttons) - 1, 3)
            category_layout.addWidget(button, row, column)
        detail_layout.addLayout(category_layout)

        action_layout = QGridLayout()
        action_specs = (
            ("alpha", "qt_review.alpha_edit", self._open_alpha_mode),
            ("accept", "review.accept", self._accept_current),
            ("reject", "review.reject", self._reject_current),
            ("restore", "review.remove", self._restore_current),
            ("approve", "review.approve", self._approve_current),
            ("approve_all", "review.approve_all", self._approve_all),
            ("promote", "qt_review.promote", self._promote_approved),
            ("delete", "review.delete_png", self._delete_current),
        )
        for index, (name, label_key, callback) in enumerate(action_specs):
            button = QPushButton(tr(label_key))
            button.setObjectName(f"gravestoneReview{name.title().replace('_', '')}Button")
            button.clicked.connect(callback)
            self._action_buttons[name] = button
            row, column = divmod(index, 2)
            action_layout.addWidget(button, row, column)
        detail_layout.addLayout(action_layout)
        self.feedback_label = QLabel(tr("review.ready"))
        self.feedback_label.setObjectName("gravestoneReviewFeedback")
        self.feedback_label.setWordWrap(True)
        detail_layout.addWidget(self.feedback_label)

        self.file_toggle = QPushButton(tr("qt_review.file_show"))
        self.file_toggle.setObjectName("gravestoneReviewFileToggle")
        self.file_toggle.setCheckable(True)
        detail_layout.addWidget(self.file_toggle)
        self.file_details_panel.setVisible(False)
        detail_layout.addWidget(self.file_details_panel)
        self.file_toggle.toggled.connect(
            lambda expanded: self._set_collapsible(
                self.file_toggle, self.file_details_panel, expanded,
                "qt_review.file_show", "qt_review.file_hide",
            )
        )

        self.metadata_toggle = QPushButton(tr("qt_review.metadata_show"))
        self.metadata_toggle.setObjectName("gravestoneReviewMetadataToggle")
        self.metadata_toggle.setCheckable(True)
        detail_layout.addWidget(self.metadata_toggle)
        self.metadata_text = QPlainTextEdit()
        self.metadata_text.setObjectName("gravestoneReviewMetadata")
        self.metadata_text.setReadOnly(True)
        self.metadata_text.setMaximumHeight(180)
        self.metadata_text.setVisible(False)
        detail_layout.addWidget(self.metadata_text)
        self.metadata_toggle.toggled.connect(
            lambda expanded: self._set_collapsible(
                self.metadata_toggle, self.metadata_text, expanded,
                "qt_review.metadata_show", "qt_review.metadata_hide",
            )
        )

        self.checks_toggle = QPushButton(tr("qt_review.checks_show"))
        self.checks_toggle.setObjectName("gravestoneReviewChecksToggle")
        self.checks_toggle.setCheckable(True)
        detail_layout.addWidget(self.checks_toggle)
        self.checks_text = QPlainTextEdit()
        self.checks_text.setObjectName("gravestoneReviewChecks")
        self.checks_text.setReadOnly(True)
        self.checks_text.setMaximumHeight(180)
        self.checks_text.setVisible(False)
        detail_layout.addWidget(self.checks_text)
        self.checks_toggle.toggled.connect(
            lambda expanded: self._set_collapsible(
                self.checks_toggle, self.checks_text, expanded,
                "qt_review.checks_show", "qt_review.checks_hide",
            )
        )

        self.workspace_splitter.addWidget(self.detail_frame)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setStretchFactor(0, 45)
        self.workspace_splitter.setStretchFactor(1, 55)
        splitter_sizes = self._initial_splitter_sizes
        if (
            isinstance(splitter_sizes, list)
            and len(splitter_sizes) == 2
            and all(isinstance(value, int) and value > 0 for value in splitter_sizes)
        ):
            self.workspace_splitter.setSizes(splitter_sizes)
        else:
            self.workspace_splitter.setSizes([450, 550])
        self.tabs.currentChanged.connect(self._queue_changed)

        self._gallery_reflow_timer = QTimer(self)
        self._gallery_reflow_timer.setSingleShot(True)
        self._gallery_reflow_timer.setInterval(50)
        self._gallery_reflow_timer.timeout.connect(self._finish_gallery_reflow)
        self._preview_refresh_timer = QTimer(self)
        self._preview_refresh_timer.setSingleShot(True)
        self._preview_refresh_timer.setInterval(30)
        self._preview_refresh_timer.timeout.connect(self._refresh_preview)

    @staticmethod
    def _set_collapsible(
        button: QPushButton,
        content: QWidget,
        expanded: bool,
        show_key: str,
        hide_key: str,
    ) -> None:
        content.setVisible(expanded)
        button.setText(tr(hide_key if expanded else show_key))

    def _navigate_relative(self, offset: int) -> None:
        current = self._current_entry()
        if current is None:
            return
        queue_name, row, _path, _metadata = current
        target_row = row + offset
        listing = self._lists[queue_name]
        if 0 <= target_row < listing.count():
            listing.setCurrentRow(target_row)

    def _update_navigation(self) -> None:
        current = self._current_entry()
        if current is None:
            self.item_position_label.setText(tr("qt_review.item_position_empty"))
            self.previous_item_button.setEnabled(False)
            self.next_item_button.setEnabled(False)
            return
        queue_name, row, _path, _metadata = current
        count = self._lists[queue_name].count()
        editable = self._alpha_session is None
        self.item_position_label.setText(tr(
            "qt_review.item_position", current=row + 1, total=count,
        ))
        self.previous_item_button.setEnabled(editable and row > 0)
        self.next_item_button.setEnabled(editable and row + 1 < count)

    def _sidecar_metadata(self, path: Path) -> dict:
        sidecar = path.with_name(path.name + ".metadata.json")
        signature = self._image_signature(sidecar)
        cached = self._sidecar_cache.get(signature)
        if cached is not None:
            return dict(cached)
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8-sig"))
        except (OSError, TypeError, ValueError):
            payload = {}
        result = payload if isinstance(payload, dict) else {}
        self._drop_stale_path_keys(self._sidecar_cache, signature)
        self._sidecar_cache[signature] = dict(result)
        self._trim_cache(self._sidecar_cache, 512)
        return result

    def _read_entries(self) -> dict[str, list[tuple[Path, dict]]]:
        productive: list[ProductiveEntry] = list_productive(self.workspace)
        return {
            "candidates": [(path, self._sidecar_metadata(path)) for path in list_candidates(self.workspace)],
            "accepted": [(path, self._sidecar_metadata(path)) for path in list_accepted(self.workspace)],
            "rejected": [(path, self._sidecar_metadata(path)) for path in list_rejected(self.workspace)],
            "approved": [(path, self._sidecar_metadata(path)) for path in list_approved(self.workspace)],
            "productive": [(entry.path, dict(entry.metadata)) for entry in productive],
        }

    def reload(self, queue_name: str | None = None, preferred_name: str | None = None,
               preferred_row: int | None = None) -> None:
        """Refresh queue state while preserving a useful current selection."""
        index = self.tabs.currentIndex()
        current_queue = queue_name or (QUEUE_ORDER[index] if index >= 0 else "candidates")
        self._entries = self._read_entries()
        counts = review_counts(self.workspace)
        count_map = {"candidates": counts.candidates, "accepted": counts.accepted,
                     "rejected": counts.rejected, "approved": counts.approved,
                     "productive": len(self._entries["productive"])}
        for queue_name in QUEUE_ORDER:
            listing = self._lists[queue_name]
            listing.clear()
            for path, metadata in self._entries[queue_name]:
                item = QListWidgetItem(path.name)
                item.setData(Qt.ItemDataRole.UserRole, (path, metadata))
                listing.addItem(item)
            self.tabs.setTabText(self._tabs[queue_name], tr(
                "qt_review.queue_count", label=tr(QUEUE_LABEL_KEYS[queue_name]), count=count_map[queue_name]))
        self.tabs.setCurrentIndex(self._tabs[current_queue])
        self._set_queue_presentation(current_queue)
        listing = self._lists[current_queue]
        if listing.count():
            row = -1
            if preferred_name:
                for candidate_row in range(listing.count()):
                    if listing.item(candidate_row).text() == preferred_name:
                        row = candidate_row
                        break
            if row < 0:
                row = min(preferred_row or 0, listing.count() - 1)
            listing.setCurrentRow(row)
        else:
            self._clear_detail(current_queue)
        self._refresh_current_view()

    def _current_queue_name(self) -> str:
        index = self.tabs.currentIndex()
        return QUEUE_ORDER[index] if 0 <= index < len(QUEUE_ORDER) else "candidates"

    def _set_queue_presentation(self, queue_name: str) -> None:
        productive = queue_name == "productive"
        self.view_controls.setVisible(not productive)
        self.workspace_splitter.setVisible(not productive)
        self.productive_gallery_scroll.setVisible(productive)

    def _current_view_name(self) -> str:
        index = self.view_stack.currentIndex()
        return VIEW_ORDER[index] if 0 <= index < len(VIEW_ORDER) else "gallery"

    def _set_view(self, view_name: str) -> None:
        if view_name not in VIEW_ORDER:
            return
        if self._alpha_session is not None and view_name != self._current_view_name():
            return
        self.view_stack.setCurrentIndex(VIEW_ORDER.index(view_name))
        self._view_buttons[view_name].setChecked(True)
        self._refresh_current_view()

    def _refresh_current_view(self) -> None:
        if self._current_queue_name() == "productive":
            self._refresh_productive_gallery()
            return
        view_name = self._current_view_name()
        if view_name == "gallery":
            self._refresh_gallery()
        elif view_name == "list":
            self._refresh_list()

    @staticmethod
    def _image_signature(path: Path) -> tuple[str, int, int]:
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
    def _trim_cache(cache: dict, limit: int) -> None:
        while len(cache) > limit:
            cache.pop(next(iter(cache)))

    @staticmethod
    def _drop_stale_path_keys(cache: dict, signature: tuple[str, int, int]) -> None:
        for key in list(cache):
            candidate = key[0] if isinstance(key, tuple) and key and isinstance(key[0], tuple) else key
            if isinstance(candidate, tuple) and candidate and candidate[0] == signature[0] and candidate != signature:
                cache.pop(key, None)

    @staticmethod
    def _human_file_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    def _image_metadata(self, path: Path) -> tuple[str, str]:
        signature = self._image_signature(path)
        cached = self._image_metadata_cache.get(signature)
        if cached is not None:
            return cached
        pixmap = QPixmap(str(path)) if path.is_file() else QPixmap()
        dimensions = f"{pixmap.width()} × {pixmap.height()}" if not pixmap.isNull() else tr("qt_review.metadata_error")
        result = (dimensions, self._human_file_size(signature[2]) if signature[1] or signature[2] else "–")
        self._drop_stale_path_keys(self._image_metadata_cache, signature)
        self._image_metadata_cache[signature] = result
        self._trim_cache(self._image_metadata_cache, 512)
        return result

    def _thumbnail(self, path: Path, size: QSize | None = None) -> QPixmap:
        target = size or QSize(145, 198)
        signature = self._image_signature(path)
        key = (signature, target.width(), target.height())
        cached = self._thumbnail_cache.get(key)
        if cached is not None:
            return cached
        source = QPixmap(str(path)) if path.is_file() else QPixmap()
        if source.isNull():
            result = QPixmap(target)
            result.fill(Qt.GlobalColor.transparent)
        else:
            result = source.scaled(target, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        self._drop_stale_path_keys(self._thumbnail_cache, signature)
        self._thumbnail_cache[key] = result
        self._trim_cache(self._thumbnail_cache, 192)
        return result

    def _gallery_column_count(self) -> int:
        width = max(180, self.gallery_scroll.viewport().width())
        return max(1, min(6, width // 180))

    def _clear_layout(self, layout: QGridLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_gallery(self) -> None:
        queue_name = self._current_queue_name()
        entries = self._entries[queue_name]
        columns = self._gallery_column_count()
        render_key = (queue_name, columns, tuple(self._image_signature(path) for path, _ in entries))
        if render_key == self._gallery_render_key and self.gallery_grid.count():
            self._sync_view_selection()
            return
        self._clear_layout(self.gallery_grid)
        self._gallery_buttons.clear()
        self._gallery_render_key = render_key
        if not entries:
            label = QLabel(tr("qt_review.no_items"))
            label.setObjectName("gravestoneReviewGalleryEmpty")
            self.gallery_grid.addWidget(label, 0, 0)
            return
        for index, (path, _metadata) in enumerate(entries):
            button = QPushButton()
            button.setObjectName(f"gravestoneReviewGalleryItem{index}")
            button.setCheckable(True)
            button.setToolTip(path.name)
            button.setAccessibleName(path.name)
            button.setIcon(QIcon(self._thumbnail(path)))
            button.setIconSize(QSize(145, 198))
            button.setMinimumSize(165, 210)
            button.clicked.connect(lambda _checked=False, row=index: self._activate_row(row))
            row, column = divmod(index, columns)
            self.gallery_grid.addWidget(button, row, column)
            self._gallery_buttons[path.name] = button
        self._sync_view_selection()

    def _refresh_productive_gallery(self) -> None:
        entries = self._entries["productive"]
        columns = max(1, self.productive_gallery_scroll.viewport().width() // 230)
        render_key = (columns, tuple(self._image_signature(path) for path, _ in entries))
        if render_key == self._productive_gallery_render_key and self.productive_gallery_grid.count():
            return
        self._clear_layout(self.productive_gallery_grid)
        self._productive_gallery_render_key = render_key
        if not entries:
            label = QLabel(tr("qt_review.no_items"))
            label.setObjectName("gravestoneReviewProductiveGalleryEmpty")
            self.productive_gallery_grid.addWidget(label, 0, 0)
            return
        for index, (path, metadata) in enumerate(entries):
            category = normalize_gravestone_category(metadata.get("category")) or load_gravestone_category(path)
            item = QLabel()
            item.setObjectName(f"gravestoneReviewProductiveGalleryItem{index}")
            item.setAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setPixmap(self._thumbnail(path, QSize(210, 286)))
            item.setMinimumSize(230, 300)
            item.setToolTip("\n".join(value for value in (
                path.name, gravestone_category_display(category) if category else "",
            ) if value))
            row, column = divmod(index, columns)
            self.productive_gallery_grid.addWidget(item, row, column)
            self.productive_gallery_grid.setColumnStretch(column, 1)

    def _refresh_list(self) -> None:
        queue_name = self._current_queue_name()
        entries = self._entries[queue_name]
        self.list_table.blockSignals(True)
        try:
            self.list_table.setRowCount(len(entries))
            for row, (path, metadata) in enumerate(entries):
                dimensions, file_size = self._image_metadata(path)
                category = normalize_gravestone_category(metadata.get("category")) or load_gravestone_category(path)
                values = (path.name, dimensions, file_size, gravestone_category_display(category))
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.ItemDataRole.UserRole, row)
                    self.list_table.setItem(row, column, item)
        finally:
            self.list_table.blockSignals(False)
        self._sync_view_selection()

    def _activate_row(self, row: int) -> None:
        listing = self._lists[self._current_queue_name()]
        if 0 <= row < listing.count():
            listing.setCurrentRow(row)
            self._sync_view_selection()

    def _list_selection_changed(self) -> None:
        rows = self.list_table.selectionModel().selectedRows()
        if rows:
            self._activate_row(rows[0].row())

    def _sync_view_selection(self) -> None:
        queue_name = self._current_queue_name()
        listing = self._lists[queue_name]
        row = listing.currentRow()
        current_name = listing.currentItem().text() if listing.currentItem() else None
        for name, button in self._gallery_buttons.items():
            button.setChecked(name == current_name)
        if self.list_table.rowCount():
            self.list_table.blockSignals(True)
            try:
                if 0 <= row < self.list_table.rowCount():
                    self.list_table.selectRow(row)
                else:
                    self.list_table.clearSelection()
            finally:
                self.list_table.blockSignals(False)

    def _finish_gallery_reflow(self) -> None:
        if self._current_queue_name() == "productive":
            self._refresh_productive_gallery()
            return
        view_name = self._current_view_name()
        if view_name == "gallery":
            old_columns = self._gallery_render_key[1] if self._gallery_render_key else None
            if old_columns != self._gallery_column_count():
                self._refresh_gallery()

    def _queue_changed(self, index: int) -> None:
        if index < 0 or index >= len(QUEUE_ORDER):
            return
        queue_name = QUEUE_ORDER[index]
        self._set_queue_presentation(queue_name)
        listing = self._lists[queue_name]
        if listing.count() and listing.currentItem() is None:
            listing.setCurrentRow(0)
        elif not listing.count():
            self._clear_detail(queue_name)
        self._refresh_current_view()

    def _clear_detail(self, queue_name: str) -> None:
        self.filename_value.setText("–")
        self.status_value.setText(tr(QUEUE_STATUS_KEYS[queue_name]))
        self.category_value.setText("–")
        self.preset_value.setText("–")
        self.metadata_text.clear()
        self.checks_text.setPlainText(tr("qt_review.no_items"))
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText(tr("qt_review.no_preview"))
        self.opening_diagnostics_label.setText(tr("review.opening_unknown"))
        self._current_analysis = None
        self._set_demo_transform(0.0, 0.0, 1.0, refresh=False)
        self._set_checked_category(None)
        self._update_actions(queue_name, False, None)
        self._update_navigation()
        self._sync_view_selection()

    def _select_item(self, queue_name: str, item: QListWidgetItem | None) -> None:
        if item is None:
            self._clear_detail(queue_name)
            return
        value = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(value, tuple) or len(value) != 2:
            self._clear_detail(queue_name)
            return
        path, metadata = value
        self._show_detail(queue_name, Path(path), dict(metadata or {}))
        self._sync_view_selection()
        self._schedule_next_validation_prefetch(queue_name, self._lists[queue_name].currentRow())

    def _show_detail(self, queue_name: str, path: Path, metadata: dict) -> None:
        self.filename_value.setText(path.name)
        self.status_value.setText(tr(QUEUE_STATUS_KEYS[queue_name]))
        category = normalize_gravestone_category(metadata.get("category")) or load_gravestone_category(path)
        self.category_value.setText(gravestone_category_display(category))
        preset = self._preset_for(path, metadata)
        self.preset_value.setText("X {:.2f} · Y {:.2f} · {:.2f}×".format(*preset))
        self.metadata_text.setPlainText(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) if metadata else "{}")
        self._set_demo_transform(*preset, refresh=False)
        self._set_checks(path)
        self._update_opening_diagnostics(path)
        self._set_preview(path)
        self._set_checked_category(category)
        self._update_actions(queue_name, True, category)
        self._update_navigation()

    def _invalidate_cached_path(self, path: Path) -> None:
        signature = self._image_signature(path)
        for cache in (self._thumbnail_cache, self._preview_cache,
                      self._image_metadata_cache, self._sidecar_cache):
            resolved = signature[0]
            for key in list(cache):
                candidate = key[0] if isinstance(key, tuple) and key and isinstance(key[0], tuple) else key
                if isinstance(candidate, tuple) and candidate and candidate[0] == resolved:
                    cache.pop(key, None)
        self._gallery_render_key = None
        self._productive_gallery_render_key = None
        self.validator.invalidate(path)
        with self._prefetch_lock:
            if self._prefetch_signature and self._prefetch_signature[0] == resolved:
                self._prefetch_signature = None
                self._prefetch_result = None

    def _consume_validation_prefetch(self, path: Path) -> None:
        signature = self._image_signature(path)
        with self._prefetch_lock:
            if self._prefetch_signature != signature or self._prefetch_result is None:
                return
            results, analysis = self._prefetch_result
            self._prefetch_signature = None
            self._prefetch_result = None
        self.validator.seed_cache(path, results, analysis)

    def _schedule_next_validation_prefetch(self, queue_name: str, row: int) -> None:
        entries = self._entries.get(queue_name, [])
        next_row = row + 1
        if next_row < 0 or next_row >= len(entries):
            return
        path = entries[next_row][0]
        signature = self._image_signature(path)
        with self._prefetch_lock:
            if (
                signature == self._prefetch_signature
                or self._prefetch_running_signature is not None
            ):
                return
            self._prefetch_running_signature = signature

        geometry = self.geometry

        def worker() -> None:
            try:
                validator = AssetValidator(geometry)
                results = validator.validate(path)
                analysis = validator.last_analysis
                with self._prefetch_lock:
                    if self._image_signature(path) == signature:
                        self._prefetch_signature = signature
                        self._prefetch_result = (list(results), analysis)
            except Exception:  # A failed prefetch must never affect review navigation.
                pass
            finally:
                with self._prefetch_lock:
                    if self._prefetch_running_signature == signature:
                        self._prefetch_running_signature = None

        threading.Thread(target=worker, name="qt-gravestone-validate-prefetch", daemon=True).start()

    def _current_entry(self) -> tuple[str, int, Path, dict] | None:
        index = self.tabs.currentIndex()
        if index < 0 or index >= len(QUEUE_ORDER):
            return None
        queue_name = QUEUE_ORDER[index]
        listing = self._lists[queue_name]
        item = listing.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(value, tuple) or len(value) != 2:
            return None
        path, metadata = value
        return queue_name, listing.currentRow(), Path(path), dict(metadata or {})

    def _set_checked_category(self, category: str | None) -> None:
        self.category_group.setExclusive(False)
        try:
            for value, button in self._category_buttons.items():
                button.setChecked(value == category)
        finally:
            self.category_group.setExclusive(True)

    def _update_actions(self, queue_name: str, has_item: bool,
                        category: str | None) -> None:
        visible = {
            "candidates": {"alpha", "accept", "reject"},
            "accepted": {"alpha", "restore", "approve", "approve_all"},
            "rejected": {"alpha", "delete"},
            "approved": {"promote"},
            "productive": set(),
        }[queue_name]
        for name, button in self._action_buttons.items():
            button.setVisible(name in visible)
            button.setEnabled(has_item and name in visible and self._alpha_session is None)
        if queue_name == "accepted":
            self._action_buttons["approve"].setEnabled(
                has_item and category is not None and self._alpha_session is None
            )
            self._action_buttons["approve_all"].setEnabled(
                bool(list_accepted(self.workspace)) and self._alpha_session is None
            )
        if queue_name == "approved":
            self._action_buttons["promote"].setEnabled(
                bool(list_approved(self.workspace)) and self._alpha_session is None
            )
        categories_enabled = has_item and queue_name != "productive" and self._alpha_session is None
        for button in self._category_buttons.values():
            button.setEnabled(categories_enabled)
        self.save_preset_button.setEnabled(
            has_item and queue_name != "productive" and self._alpha_session is None
        )
        self.readonly_notice.setVisible(queue_name == "productive")
        self.readonly_notice.setText(tr("review.productive_readonly"))

    def _set_category(self, category: str) -> None:
        current = self._current_entry()
        if current is None:
            return
        queue_name, row, path, _metadata = current
        if queue_name == "productive":
            return
        try:
            set_review_category(path, self.workspace, category)
        except Exception as exc:  # noqa: BLE001 - Core failure must be reflected in the UI.
            self._handle_error(tr("review.category_save_failed"), exc, queue_name, path.name, row)
            return
        self.feedback_label.setText(tr(
            "review.category_saved", label=tr("gravestone_category.label"),
            category=gravestone_category_display(category),
        ))
        self.reload(queue_name, path.name, row)

    def _handle_error(self, title: str, error: Exception, queue_name: str,
                      preferred_name: str | None, preferred_row: int) -> None:
        self.feedback_label.setText(f"{title}: {error}")
        self.reload(queue_name, preferred_name, preferred_row)
        QMessageBox.critical(self, title, str(error))

    def _accept_current(self) -> None:
        current = self._current_entry()
        if current is None or current[0] != "candidates":
            return
        queue_name, row, path, metadata = current
        category = normalize_gravestone_category(metadata.get("category")) or load_gravestone_category(path)
        try:
            result = accept_candidate(path, self.workspace, self.validator, category=category)
        except Exception as exc:  # noqa: BLE001
            self._handle_error(tr("review.accept_failed"), exc, queue_name, path.name, row)
            return
        self.validator.transfer_cache(path, result.accepted_path)
        self._invalidate_cached_path(path)
        self.feedback_label.setText(tr("review.accepted_file", name=result.accepted_path.name))
        self.reload(queue_name, preferred_row=row)

    def _reject_current(self) -> None:
        current = self._current_entry()
        if current is None or current[0] != "candidates":
            return
        queue_name, row, path, _metadata = current
        try:
            moved = reject_candidate(path, self.workspace)
        except Exception as exc:  # noqa: BLE001
            self._handle_error(tr("review.reject_failed"), exc, queue_name, path.name, row)
            return
        self.validator.transfer_cache(path, moved)
        self._invalidate_cached_path(path)
        self.feedback_label.setText(tr("review.rejected_file", name=moved.name))
        self.reload(queue_name, preferred_row=row)

    def _restore_current(self) -> None:
        current = self._current_entry()
        if current is None or current[0] != "accepted":
            return
        queue_name, row, path, _metadata = current
        try:
            restored = restore_accepted(path, self.workspace)
        except Exception as exc:  # noqa: BLE001
            self._handle_error(tr("review.remove_failed"), exc, queue_name, path.name, row)
            return
        self.validator.transfer_cache(path, restored)
        self._invalidate_cached_path(path)
        self.feedback_label.setText(tr("review.restored_file", name=restored.name))
        self.reload(queue_name, preferred_row=row)

    def _approve_current(self) -> None:
        current = self._current_entry()
        if current is None or current[0] != "accepted":
            return
        queue_name, row, path, metadata = current
        category = normalize_gravestone_category(metadata.get("category")) or load_gravestone_category(path)
        if category is None:
            title = tr("review.approve_not_possible")
            message = tr("review.category_required", label=tr("gravestone_category.label"))
            self.feedback_label.setText(message)
            QMessageBox.warning(self, title, message)
            return
        try:
            result = approve_accepted(path, self.workspace, self.validator, category=category)
        except Exception as exc:  # noqa: BLE001
            self._handle_error(tr("review.approve_failed"), exc, queue_name, path.name, row)
            return
        self.validator.transfer_cache(path, result.master_path)
        self._invalidate_cached_path(path)
        self.feedback_label.setText(tr("review.approved_file", name=result.master_path.name))
        self.reload(queue_name, preferred_row=row)

    def _approve_all(self) -> None:
        accepted = list_accepted(self.workspace)
        if not accepted:
            return
        categories = {path: load_gravestone_category(path) for path in accepted}
        missing = [path.name for path, category in categories.items() if category is None]
        if missing:
            title = tr("review.approve_not_possible")
            message = tr(
                "review.missing_categories", count=len(missing),
                label=tr("gravestone_category.label"),
                names="\n".join(f"- {name}" for name in missing),
            )
            self.feedback_label.setText(message)
            QMessageBox.warning(self, title, message)
            return
        if QMessageBox.question(
            self, tr("review.approve_all_title"),
            tr("review.approve_all_question", count=len(accepted)),
        ) != QMessageBox.StandardButton.Yes:
            return
        completed = 0
        try:
            for path in accepted:
                result = approve_accepted(path, self.workspace, self.validator, category=categories[path])
                self.validator.transfer_cache(path, result.master_path)
                self._invalidate_cached_path(path)
                completed += 1
        except Exception as exc:  # noqa: BLE001
            self.feedback_label.setText(tr("review.approve_all_error", count=completed, error=exc))
            self.reload("accepted")
            QMessageBox.critical(
                self, tr("review.approve_all_aborted"),
                tr("review.approve_all_error", count=completed, error=exc),
            )
            return
        self.feedback_label.setText(tr("review.approved_all", count=completed))
        self.reload("accepted")

    def _delete_current(self) -> None:
        current = self._current_entry()
        if current is None or current[0] != "rejected":
            return
        queue_name, row, path, _metadata = current
        if QMessageBox.question(
            self, tr("review.delete_rejected_title"),
            tr("review.delete_rejected_question", name=path.name),
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_rejected(path, self.workspace)
        except Exception as exc:  # noqa: BLE001
            self._handle_error(tr("review.delete_failed"), exc, queue_name, path.name, row)
            return
        self._invalidate_cached_path(path)
        self.feedback_label.setText(tr("review.deleted_rejected", name=path.name))
        self.reload(queue_name, preferred_row=row)

    def _promote_approved(self) -> None:
        current = self._current_entry()
        if current is None or current[0] != "approved":
            return
        queue_name, row, path, _metadata = current
        if QMessageBox.question(
            self, tr("qt_review.promote_title"),
            tr("qt_review.promote_question", count=len(list_approved(self.workspace))),
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            result = promote_approved_gravestones(
                self.workspace.graveyard,
                self.workspace.approved,
                self.workspace.approved_compressed,
                self.workspace.graveyard / "gravestones_manifest.json",
            )
        except Exception as exc:  # noqa: BLE001 - Core transaction failure belongs in the UI.
            self._handle_error(tr("qt_review.promote_failed"), exc, queue_name, path.name, row)
            return
        for _source_name, target_name in result.promoted:
            self._invalidate_cached_path(self.workspace.graveyard / target_name)
        if result.promoted:
            mappings = ", ".join(f"{source} → {target}" for source, target in result.promoted)
            self.feedback_label.setText(tr(
                "qt_review.promoted", count=len(result.promoted), mappings=mappings,
            ))
        elif result.missing_compressed:
            message = tr(
                "qt_review.promote_missing_compressed",
                names=", ".join(result.missing_compressed),
            )
            self.feedback_label.setText(message)
            QMessageBox.warning(self, tr("qt_review.promote_not_possible"), message)
        else:
            self.feedback_label.setText(tr(
                "qt_review.promote_unchanged", count=len(result.already_processed),
            ))
        self.reload(queue_name, preferred_name=path.name, preferred_row=row)

    def _open_alpha_mode(self) -> None:
        """Open a discard-only alpha draft for the selected review image."""
        current = self._current_entry()
        if current is None or current[0] not in {"candidates", "accepted", "rejected"}:
            return
        queue_name, _row, path, _metadata = current
        try:
            with Image.open(path) as source:
                source.load()
                image = source.convert("RGBA")
        except Exception as exc:  # noqa: BLE001 - A broken item must not break review navigation.
            self.feedback_label.setText(tr("review.preview_error", error=exc))
            return
        portrait_bbox = self.geometry.scale_box(self.geometry.portrait_bbox, image.size)
        opening = detect_portrait_opening(image, portrait_bbox)
        text_safe_area = (
            load_gravestone_text_safe_area(path, image.size)
            or self.geometry.scale_box(self.geometry.text_safe_area, image.size)
        )
        self._alpha_session = AlphaMaskSession(image, opening.box, text_safe_area)
        self._alpha_source_path = path
        self._alpha_source_queue = queue_name
        self._alpha_source_signature = self._image_signature(path)
        self._alpha_initial_ellipse = tuple(opening.box)
        self._alpha_initial_text_safe_area = tuple(text_safe_area)
        self._alpha_drag_start = None
        self._alpha_move_origin = None
        self._alpha_guide_bbox = None
        self._alpha_stroke_active = False
        self._alpha_previous_view = self._current_view_name()
        self.tabs.setEnabled(False)
        self.view_stack.setEnabled(False)
        for button in self._view_buttons.values():
            button.setEnabled(False)
        self.normal_preview_controls.setVisible(False)
        self.alpha_controls.setVisible(True)
        self.alpha_status_label.setText(tr("qt_review.alpha_draft_notice"))
        self._update_alpha_history_buttons()
        category = normalize_gravestone_category(current[3].get("category"))
        self._update_actions(queue_name, True, category)
        self._update_navigation()
        self._set_alpha_preview()

    def _close_alpha_mode(self) -> None:
        """Discard the in-memory draft and return to the unchanged review item."""
        previous_view = getattr(self, "_alpha_previous_view", "gallery")
        self._alpha_session = None
        self._alpha_source_path = None
        self._alpha_source_queue = None
        self._alpha_source_signature = None
        self._alpha_initial_ellipse = None
        self._alpha_initial_text_safe_area = None
        self._alpha_drag_start = None
        self._alpha_move_origin = None
        self._alpha_guide_bbox = None
        self._alpha_stroke_active = False
        self.alpha_controls.setVisible(False)
        self.normal_preview_controls.setVisible(True)
        self.preview_label.set_edit_ellipse(None)
        self.tabs.setEnabled(True)
        self.view_stack.setEnabled(True)
        for button in self._view_buttons.values():
            button.setEnabled(True)
        current = self._current_entry()
        if current is not None:
            queue_name, _row, path, metadata = current
            self._show_detail(queue_name, path, metadata)
        self._set_view(previous_view)

    def _alpha_has_unsaved_changes(self) -> bool:
        session = self._alpha_session
        if session is None:
            return False
        return (
            session.image.tobytes() != session.original.tobytes()
            or session.ellipse_bbox != self._alpha_initial_ellipse
            or session.text_safe_area != self._alpha_initial_text_safe_area
        )

    def _set_alpha_tool(self, tool: str) -> None:
        if tool not in {"ellipse", "move", "erase", "restore"}:
            return
        self._alpha_tool = tool
        self._alpha_drag_start = None
        self._alpha_move_origin = None
        self._alpha_guide_bbox = None
        self._alpha_stroke_active = False
        self._set_alpha_preview()

    def _set_alpha_preview_mode(self, mode: str) -> None:
        if mode not in {"opening", "composite"}:
            return
        self._alpha_preview_mode = mode
        self._set_alpha_preview()

    def _alpha_widget_to_image(self, point: QPoint) -> tuple[int, int] | None:
        """Map the centered, fit-scaled Qt preview back to source pixels."""
        session = self._alpha_session
        display = self.preview_label.pixmap_display_rect()
        if session is None or display is None or display.width() <= 0 or display.height() <= 0:
            return None
        local_x = point.x() - display.left()
        local_y = point.y() - display.top()
        if local_x < 0 or local_y < 0 or local_x >= display.width() or local_y >= display.height():
            return None
        x = round(local_x * session.image.width / display.width())
        y = round(local_y * session.image.height / display.height())
        return (
            max(0, min(session.image.width - 1, x)),
            max(0, min(session.image.height - 1, y)),
        )

    def _alpha_pointer_pressed(self, point: QPoint) -> None:
        mapped = self._alpha_widget_to_image(point)
        if mapped is not None:
            self._alpha_begin(mapped)

    def _alpha_pointer_moved(self, point: QPoint) -> None:
        mapped = self._alpha_widget_to_image(point)
        if mapped is not None:
            self._alpha_continue(mapped)

    def _alpha_pointer_released(self, point: QPoint) -> None:
        mapped = self._alpha_widget_to_image(point)
        if mapped is not None:
            self._alpha_finish(mapped)
        else:
            self._alpha_cancel_gesture()

    def _alpha_begin(self, point: tuple[int, int]) -> None:
        session = self._alpha_session
        if session is None:
            return
        self._alpha_drag_start = point
        if self._alpha_tool == "move":
            self._alpha_move_origin = session.ellipse_bbox
        elif self._alpha_tool in {"erase", "restore"}:
            session.checkpoint()
            self._alpha_stroke_active = True
            self._alpha_paint(point)

    def _alpha_continue(self, point: tuple[int, int]) -> None:
        session = self._alpha_session
        start = self._alpha_drag_start
        if session is None or start is None:
            return
        if self._alpha_tool in {"erase", "restore"} and self._alpha_stroke_active:
            self._alpha_paint(point)
            return
        if self._alpha_tool == "ellipse":
            self._alpha_guide_bbox = (start[0], start[1], point[0], point[1])
        elif self._alpha_tool == "move" and self._alpha_move_origin is not None:
            dx, dy = point[0] - start[0], point[1] - start[1]
            x1, y1, x2, y2 = self._alpha_move_origin
            self._alpha_guide_bbox = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
        self._update_alpha_guide()

    def _alpha_finish(self, point: tuple[int, int]) -> None:
        session = self._alpha_session
        start = self._alpha_drag_start
        if session is None or start is None:
            self._alpha_cancel_gesture()
            return
        feather = self.alpha_feather_slider.value()
        if self._alpha_tool == "ellipse":
            bbox = (start[0], start[1], point[0], point[1])
            if abs(bbox[2] - bbox[0]) >= 12 and abs(bbox[3] - bbox[1]) >= 12:
                session.apply_ellipse(bbox, feather)
        elif self._alpha_tool == "move" and self._alpha_move_origin is not None:
            dx, dy = point[0] - start[0], point[1] - start[1]
            session.move_ellipse(dx, dy, feather)
        self._alpha_cancel_gesture(refresh=False)
        self._update_alpha_history_buttons()
        self._set_alpha_preview()

    def _alpha_cancel_gesture(self, *, refresh: bool = True) -> None:
        self._alpha_drag_start = None
        self._alpha_move_origin = None
        self._alpha_guide_bbox = None
        self._alpha_stroke_active = False
        if refresh and self._alpha_session is not None:
            self._set_alpha_preview()

    def _alpha_paint(self, point: tuple[int, int]) -> None:
        session = self._alpha_session
        if session is None:
            return
        session.brush(
            point[0], point[1], max(2, self.alpha_brush_slider.value()),
            restore=self._alpha_tool == "restore",
            feather=self.alpha_feather_slider.value(),
        )
        self._update_alpha_history_buttons()
        self._schedule_preview_refresh()

    def _alpha_undo(self) -> None:
        if self._alpha_session is not None and self._alpha_session.undo():
            self._update_alpha_history_buttons()
            self._set_alpha_preview()

    def _alpha_redo(self) -> None:
        if self._alpha_session is not None and self._alpha_session.redo():
            self._update_alpha_history_buttons()
            self._set_alpha_preview()

    def _alpha_reset(self) -> None:
        session = self._alpha_session
        if (
            session is None
            or self._alpha_initial_ellipse is None
            or self._alpha_initial_text_safe_area is None
        ):
            return
        session.checkpoint()
        session.image = session.original.copy()
        session.ellipse_bbox = self._alpha_initial_ellipse
        session.text_safe_area = self._alpha_initial_text_safe_area
        self._alpha_cancel_gesture(refresh=False)
        self._update_alpha_history_buttons()
        self._set_alpha_preview()

    def _save_alpha_mode(self) -> None:
        session = self._alpha_session
        path = self._alpha_source_path
        queue_name = self._alpha_source_queue
        source_signature = self._alpha_source_signature
        if session is None or path is None or queue_name is None or source_signature is None:
            return
        if queue_name not in {"candidates", "accepted", "rejected"}:
            return
        if self._image_signature(path) != source_signature:
            message = tr("qt_review.alpha_source_changed")
            self.feedback_label.setText(message)
            QMessageBox.critical(self, tr("alpha_editor.save_failed"), message)
            return
        if QMessageBox.question(
            self,
            tr("alpha_editor.save_title"),
            tr("alpha_editor.save_question"),
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            backup = save_alpha_edit_atomic(
                session.image,
                path,
                self.workspace.logs / "alpha_backups",
            )
        except Exception as exc:  # noqa: BLE001 - Draft stays open after a failed transaction.
            self.feedback_label.setText(tr("alpha_editor.save_failed"))
            QMessageBox.critical(self, tr("alpha_editor.save_failed"), str(exc))
            return
        self._invalidate_cached_path(path)
        self.renderer.invalidate_path(path)
        self._close_alpha_mode()
        self.feedback_label.setText(tr("alpha_editor.saved_backup", name=backup.name))

    def _update_alpha_history_buttons(self) -> None:
        session = self._alpha_session
        self.alpha_undo_button.setEnabled(bool(session and session.undo_stack))
        self.alpha_redo_button.setEnabled(bool(session and session.redo_stack))

    def _update_alpha_guide(self) -> None:
        session = self._alpha_session
        if session is None:
            self.preview_label.set_edit_ellipse(None)
            return
        self.preview_label.set_edit_ellipse(
            self._alpha_guide_bbox or session.ellipse_bbox,
            session.image.size,
        )

    def _render_alpha_source(self) -> tuple[Image.Image, OpeningAnalysis]:
        session = self._alpha_session
        if session is None:
            raise RuntimeError("Alpha mode is not active")
        image = session.image
        portrait_bbox = self.geometry.scale_box(self.geometry.portrait_bbox, image.size)
        opening = detect_portrait_opening(image, portrait_bbox)
        analysis = OpeningAnalysis(
            opening.adaptive, opening.seed, opening.full_mask, opening.box,
            area=opening.area, centroid=opening.centroid, notes=[opening.reason],
        )
        checker = self.renderer._checkerboard(image.size, 28)
        portrait = self.renderer.portrait_image()
        if self._alpha_preview_mode == "composite" and portrait is not None:
            checker.alpha_composite(portrait_layer(
                image.size, portrait, opening,
                offset_x=self._demo_offset_x,
                offset_y=self._demo_offset_y,
                zoom=self._demo_zoom,
            ))
        checker.alpha_composite(image)
        metrics = opening_transparency_metrics(image, analysis)
        if self._alpha_preview_mode == "opening":
            edge = metrics.expected_mask.filter(ImageFilter.FIND_EDGES)
            green = Image.new("RGBA", image.size, (35, 255, 95, 0))
            green.putalpha(edge.point(lambda value: 220 if value else 0))
            checker.alpha_composite(green)
            magenta = Image.new("RGBA", image.size, (255, 0, 190, 0))
            magenta.putalpha(metrics.problem_mask.point(lambda value: 190 if value else 0))
            checker.alpha_composite(magenta)
        detected = tr("review.opening_yes") if metrics.found else tr("review.opening_fallback")
        self.alpha_status_label.setText(tr(
            "review.opening_diagnostics",
            detected=detected,
            transparent=metrics.transparent_pixels,
            semi=metrics.semitransparent_pixels,
            opaque=metrics.nontransparent_pixels,
            ratio=f"{metrics.transparency_ratio:.1%}",
        ))
        return checker, analysis

    def _set_alpha_preview(self) -> None:
        if self._alpha_session is None:
            return
        image, _analysis = self._render_alpha_source()
        source = QPixmap.fromImage(ImageQt(image.convert("RGBA")).copy())
        pixmap = source.scaled(
            self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setText("")
        self.preview_label.setPixmap(pixmap)
        self._update_alpha_guide()

    def _set_preview_mode(self, mode: str) -> None:
        if mode not in {"original", "composite", "opening"}:
            return
        self._preview_mode = mode
        self._schedule_preview_refresh()

    def _set_demo_transform(self, offset_x: float, offset_y: float, zoom: float,
                            *, refresh: bool = True) -> None:
        self._demo_offset_x = max(-1.0, min(1.0, float(offset_x)))
        self._demo_offset_y = max(-1.0, min(1.0, float(offset_y)))
        self._demo_zoom = max(1.0, min(3.0, float(zoom)))
        self.renderer.set_portrait_transform(
            self._demo_offset_x, self._demo_offset_y, self._demo_zoom,
        )
        self.demo_zoom_slider.blockSignals(True)
        try:
            self.demo_zoom_slider.setValue(round(self._demo_zoom * 100))
        finally:
            self.demo_zoom_slider.blockSignals(False)
        self.demo_transform_label.setText(
            f"X {self._demo_offset_x:.2f} · Y {self._demo_offset_y:.2f} · {self._demo_zoom:.2f}×"
        )
        if refresh:
            self._schedule_preview_refresh()

    def _demo_zoom_changed(self, value: int) -> None:
        self._set_demo_transform(
            self._demo_offset_x, self._demo_offset_y, value / 100.0,
        )

    def _reset_demo_portrait(self) -> None:
        # Matches the Tk reference: reset is neutral, while selecting an item
        # loads that gravestone's stored preset.
        self._set_demo_transform(0.0, 0.0, 1.0)

    def _choose_demo_portrait(self) -> None:
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self, tr("review.change_portrait"), str(self.project_root),
            "PNG/JPEG/WebP (*.png *.jpg *.jpeg *.webp)",
        )
        if filename:
            self.renderer.set_portrait(Path(filename))
            self._preview_cache.clear()
            self._schedule_preview_refresh()

    def _save_demo_portrait_preset(self) -> None:
        current = self._current_entry()
        if current is None or current[0] == "productive":
            return
        queue_name, row, path, _metadata = current
        try:
            save_gravestone_portrait_preset(
                path, self._demo_offset_x, self._demo_offset_y, self._demo_zoom,
            )
        except Exception as exc:  # noqa: BLE001
            self._handle_error(tr("review.preset_save_failed"), exc, queue_name, path.name, row)
            return
        self.feedback_label.setText(tr("review.preset_saved", name=path.name))
        self.reload(queue_name, preferred_name=path.name, preferred_row=row)

    def _move_demo_portrait(self, delta: QPoint) -> None:
        if self._alpha_session is not None:
            return
        if self._preview_mode not in {"composite", "opening"}:
            return
        pixmap = self.preview_label.pixmap()
        if pixmap.isNull():
            return
        analysis = self._current_analysis
        bbox = analysis.bbox if analysis is not None and analysis.bbox else self.geometry.portrait_bbox
        scale_x = pixmap.width() / max(1, self.geometry.canvas_size[0])
        scale_y = pixmap.height() / max(1, self.geometry.canvas_size[1])
        opening_width = max(1.0, (bbox[2] - bbox[0]) * scale_x)
        opening_height = max(1.0, (bbox[3] - bbox[1]) * scale_y)
        self._set_demo_transform(
            self._demo_offset_x + delta.x() * 2.0 / opening_width,
            self._demo_offset_y + delta.y() * 2.0 / opening_height,
            self._demo_zoom,
        )

    def _schedule_preview_refresh(self) -> None:
        self._preview_refresh_timer.start()

    def _refresh_preview(self) -> None:
        if self._alpha_session is not None:
            self._set_alpha_preview()
            return
        current = self._current_entry()
        if current is not None:
            self._set_preview(current[2])

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        if hasattr(self, "_gallery_reflow_timer"):
            self._gallery_reflow_timer.start()
        if hasattr(self, "_preview_refresh_timer"):
            self._schedule_preview_refresh()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._alpha_has_unsaved_changes() and QMessageBox.question(
            self,
            tr("qt_review.alpha_discard_title"),
            tr("qt_review.alpha_discard_question"),
        ) != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        super().closeEvent(event)

    def _update_opening_diagnostics(self, path: Path) -> None:
        try:
            stone = self.renderer._stone_image(path, self.geometry.canvas_size)  # Shared read-only renderer cache.
            metrics = opening_transparency_metrics(stone, self._current_analysis)
            detected = tr("review.opening_yes") if metrics.found else tr("review.opening_fallback")
            self.opening_diagnostics_label.setText(tr(
                "review.opening_diagnostics",
                detected=detected,
                transparent=metrics.transparent_pixels,
                semi=metrics.semitransparent_pixels,
                opaque=metrics.nontransparent_pixels,
                ratio=f"{metrics.transparency_ratio:.1%}",
            ))
        except Exception as exc:  # noqa: BLE001 - Diagnostics must remain non-fatal.
            self.opening_diagnostics_label.setText(tr(
                "review.opening_diagnostics_unavailable", error=exc,
            ))

    @staticmethod
    def _preset_for(path: Path, metadata: dict) -> tuple[float, float, float]:
        fields = (GRAVESTONE_DEFAULT_OFFSET_X_FIELD, GRAVESTONE_DEFAULT_OFFSET_Y_FIELD,
                  GRAVESTONE_DEFAULT_ZOOM_FIELD)
        if all(field in metadata for field in fields):
            try:
                return float(metadata[fields[0]]), float(metadata[fields[1]]), float(metadata[fields[2]])
            except (TypeError, ValueError):
                pass
        return load_gravestone_portrait_preset(path) or (0.0, 0.0, 1.0)

    def _set_preview(self, path: Path) -> None:
        signature = self._image_signature(path)
        size = self.preview_label.size()
        portrait_signature = (
            self._image_signature(self.renderer.portrait_path)
            if self.renderer.portrait_path is not None else None
        )
        key = (
            signature, size.width(), size.height(), self._preview_mode,
            round(self._demo_offset_x, 4), round(self._demo_offset_y, 4),
            round(self._demo_zoom, 4), portrait_signature,
        )
        pixmap = self._preview_cache.get(key)
        if pixmap is None:
            source = QPixmap()
            if path.is_file() and self._preview_mode == "original":
                source = QPixmap(str(path))
            elif path.is_file():
                try:
                    metadata = self._current_entry()[3] if self._current_entry() is not None else {}
                    raw_area = metadata.get(GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD)
                    text_safe_area = (
                        tuple(int(value) for value in raw_area)
                        if isinstance(raw_area, (list, tuple)) and len(raw_area) == 4 else None
                    )
                    image = self.renderer.render(
                        path,
                        view="Dunkel",
                        composite=self._preview_mode == "composite",
                        show_portrait_overlay=False,
                        show_text_overlay=False,
                        show_diagnostic_overlay=False,
                        name="Waltørdin",
                        class_name="Warrior",
                        death_date="2026-09-12",
                        analysis=self._current_analysis,
                        opening_check=self._preview_mode == "opening",
                        text_safe_area=text_safe_area,
                    )
                    source = QPixmap.fromImage(ImageQt(image.convert("RGBA")).copy())
                except Exception as exc:  # noqa: BLE001 - Preview failure stays non-fatal.
                    self.feedback_label.setText(tr("review.preview_error", error=exc))
            pixmap = source.scaled(
                size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ) if not source.isNull() else QPixmap()
            self._drop_stale_path_keys(self._preview_cache, signature)
            self._preview_cache[key] = pixmap
            self._trim_cache(self._preview_cache, 24)
        if pixmap.isNull():
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(tr("qt_review.preview_missing"))
            return
        self.preview_label.setText("")
        self.preview_label.setPixmap(pixmap)

    def _set_checks(self, path: Path) -> None:
        if not path.is_file():
            self._current_analysis = None
            self.checks_text.setPlainText(tr("qt_review.preview_missing"))
            return
        try:
            self._consume_validation_prefetch(path)
            results = self.validator.validate(path)
            self._current_analysis = self.validator.last_analysis
        except Exception as exc:  # Keep corrupt/missing review files viewable without a crash.
            self._current_analysis = None
            self.checks_text.setPlainText(str(exc))
            return
        lines = []
        for result in results:
            marker = "✓" if result.ok else ("✗" if result.critical else "!")
            lines.append(f"{marker} {result.label}" + (f" — {result.detail}" if result.detail else ""))
        self.checks_text.setPlainText("\n".join(lines) or tr("qt_review.no_checks"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qt Gravestone Review (read-only shell)")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv)
    widget = QtGravestoneReviewWidget(args.project_root)
    widget.setWindowTitle(tr("qt_review.title"))
    widget.resize(1040, 760)
    widget.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
