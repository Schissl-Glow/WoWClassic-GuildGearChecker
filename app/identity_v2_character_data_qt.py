"""Identity V2 character table and detail view with explicit edits."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDateEdit, QDialog,
    QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QRadioButton, QScrollArea, QSplitter,
    QSpinBox, QStyle, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
    QWidget,
)

from .i18n import get_language, tr
from .identity_v2 import IdentityV2Store
from .identity_v2_point_presentation import ActivePointPresentation, POINT_MODE_RAID
from .qt_row_hover import install_row_hover
from .identity_v2_character_rows import CharacterTableRow, character_table_rows
from .identity_v2_graveyard import GravestoneUnavailableError
from .identity_v2_character_service import (
    BurialTypeError, DeathAttendanceConflict, DeathCorrectionError, MemberEdit,
    apply_member_edits,
    clear_member_death_marking, confirm_member_check, correct_member_death_date,
    mark_member_dead, set_member_class, set_member_gear_status, set_member_note, set_member_race,
    set_member_raid_role, set_member_raid_status, set_member_spec, set_member_burial_type,
)
from .identity_v2_main_history import (
    MainSuccessorCandidate, MainSuccessorSelectionRequired,
)
from .identity_v2_character_values import (
    CLASS_SPECS, GEAR_STATUSES, RACES, RAID_ROLES, RAID_STATUSES,
)
from .project_storage import member_portrait_path
from .identity_v2_raid_points import apply_v2_member_special_edits


DETAIL_VISIBLE_SETTING = "identity_v2_character_detail_visible"
SPLITTER_SIZES_SETTING = "identity_v2_character_splitter_sizes"
COLUMN_WIDTHS_SETTING = "identity_v2_character_column_widths"
COLUMN_ORDER_SETTING = "identity_v2_character_column_order"

COLUMNS = (
    "name", "player", "role", "race", "class", "spec", "raid_role", "gear",
    "raid_status", "last_checked", "last_raid", "dead",
)
DEFAULT_WIDTHS = (180, 160, 105, 110, 115, 140, 115, 100, 120, 125, 120, 70)
EDITABLE_COLUMNS = frozenset({3, 4, 5, 6, 7, 8})
FIELD_BY_COLUMN = {
    3: "race", 4: "className", 5: "spec", 6: "raidRole",
    7: "gearStatus", 8: "raidStatus",
}
RAW_ROLE = int(Qt.ItemDataRole.UserRole) + 1
DEATH_ACTION_ROLE = RAW_ROLE + 1


def _widths(value: object) -> list[int]:
    result = list(DEFAULT_WIDTHS)
    if isinstance(value, (list, tuple)):
        for index, width in enumerate(value[:len(result)]):
            if isinstance(width, int) and not isinstance(width, bool) and 60 <= width <= 2400:
                result[index] = width
    result[-1] = min(result[-1], 90)
    return result


def _order(value: object) -> list[str]:
    data_columns = COLUMNS[:-1]
    result = [key for key in value if key in data_columns] if isinstance(value, list) else []
    result = list(dict.fromkeys(result))
    result.extend(key for key in data_columns if key not in result)
    return [*result, "dead"]


def _splitter_sizes(value: object) -> list[int]:
    if (isinstance(value, (list, tuple)) and len(value) == 2
            and all(isinstance(size, int) and not isinstance(size, bool) and size > 0
                    for size in value)):
        return list(value)
    return [800, 420]


def _date_text(value: str | None) -> str:
    if value is None:
        return "–"
    try:
        day = date.fromisoformat(value)
    except ValueError:
        return value
    return day.strftime("%d.%m.%Y") if get_language() == "de" else day.isoformat()


def _role_text(value: str | None) -> str:
    if value is None:
        return "–"
    return tr(f"identity_v2_character_data.{value}")


def _raid_role_text(value: str) -> str:
    return tr(f"raid_role.{value}")


def _gear_text(value: str) -> str:
    return tr(f"gear.{dict(zip(GEAR_STATUSES, ('level', 'pre_bis', 'bis', 's_plus')))[value]}")


def _raid_status_text(value: str) -> str:
    return tr(f"raid_status.{dict(zip(RAID_STATUSES, ('not_set', 'ready', 'not_ready')))[value]}")


def _number_or_dash(value) -> str:
    if value is None:
        return "–"
    return f"{value:g}" if isinstance(value, float) else str(value)


def _rank_text(asset_id: str | None) -> str:
    return asset_id.replace("_", " ") if asset_id else "–"


class CharacterDataTable(QTableWidget):
    """Keep clipboard and keyboard navigation inside editable V2 fields."""

    def __init__(self, page: "IdentityV2CharacterDataPage") -> None:
        super().__init__(0, len(COLUMNS))
        self.page = page

    def keyPressEvent(self, event):  # noqa: N802
        if event.matches(QKeySequence.StandardKey.Copy):
            self.page.copy_selection()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.page.paste_text(QApplication.clipboard().text())
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.currentItem()
            if item is not None and item.column() == len(COLUMNS) - 1:
                self.page._request_death_for_member(item.data(Qt.ItemDataRole.UserRole))
                event.accept()
                return
            if item is not None and item.column() in EDITABLE_COLUMNS:
                self.editItem(item)
                event.accept()
                return
        if event.key() == Qt.Key.Key_Space:
            item = self.currentItem()
            if item is not None and item.column() == len(COLUMNS) - 1:
                self.page._request_death_for_member(item.data(Qt.ItemDataRole.UserRole))
                event.accept()
                return
        super().keyPressEvent(event)

    def moveCursor(self, action, modifiers):  # noqa: N802
        if (action in (QAbstractItemView.CursorAction.MoveNext,
                       QAbstractItemView.CursorAction.MovePrevious)
                and self.rowCount() and self.currentRow() >= 0):
            header = self.horizontalHeader()
            offset = 1 if action == QAbstractItemView.CursorAction.MoveNext else -1
            visual = header.visualIndex(self.currentColumn())
            row = self.currentRow()
            for _ in range(self.rowCount() * self.columnCount()):
                visual += offset
                if visual >= self.columnCount():
                    visual, row = 0, (row + 1) % self.rowCount()
                elif visual < 0:
                    visual, row = self.columnCount() - 1, (row - 1) % self.rowCount()
                column = header.logicalIndex(visual)
                if column in EDITABLE_COLUMNS:
                    return self.model().index(row, column)
        return super().moveCursor(action, modifiers)


class CharacterDataDelegate(QStyledItemDelegate):
    """Create a choice editor only while an editable table cell is active."""

    def __init__(self, page: "IdentityV2CharacterDataPage") -> None:
        super().__init__(page.table)
        self.page = page

    def paint(self, painter, option, index):  # noqa: N802
        option = self.page.table_row_hover.paint_option(option, index)
        if index.column() != len(COLUMNS) - 1 or not index.data(DEATH_ACTION_ROLE):
            super().paint(painter, option, index)
            return
        painter.save()
        painter.fillRect(
            option.rect,
            QColor("#302b22") if option.state & QStyle.StateFlag.State_Selected
            else option.backgroundBrush,
        )
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(6, 5, -6, -5)
        painter.setBrush(QColor("#8b2d35"))
        painter.setPen(QPen(QColor("#c9757b"), 1))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "☠")
        painter.restore()

    def createEditor(self, parent, option, index):  # noqa: N802
        if index.column() not in EDITABLE_COLUMNS:
            return None
        member_id = index.model().index(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        row = self.page.rows_by_id.get(member_id)
        if row is None:
            return None
        combo = QComboBox(parent)
        combo.setMinimumHeight(30)
        for label, value in self.page._field_options(index.column(), row):
            combo.addItem(label, value)
        combo.view().setMinimumWidth(max(option.rect.width(), 185))
        return combo

    def setEditorData(self, editor, index):  # noqa: N802
        current = index.data(RAW_ROLE)
        found = editor.findData(current)
        editor.setCurrentIndex(found if found >= 0 else 0)

    def setModelData(self, editor, model, index):  # noqa: N802
        model.setData(index, editor.currentData(), Qt.ItemDataRole.EditRole)


class DetailChoiceComboBox(QComboBox):
    """Open choices on arrow keys; only an activated choice commits an edit."""

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down) and not self.view().isVisible():
            self.showPopup()
            event.accept()
            return
        super().keyPressEvent(event)


class MemberSpecialPointsDialog(QDialog):
    """Edit member-owned special points as one cancelable draft."""

    def __init__(self, member_name: str, adjustments: tuple, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("identity_v2_raid_points.special_title",
                               character=member_name))
        self.setMinimumWidth(550)
        layout = QVBoxLayout(self)
        help_label = QLabel(tr("identity_v2_raid_points.special_help"))
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels((
            tr("raid_points.adjustment"), tr("raid_points.reason")))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        self._editors: list[tuple[str | None, QSpinBox, QLineEdit]] = []
        for adjustment in adjustments:
            self._add_row(adjustment.adjustment_id,
                          adjustment.value, adjustment.reason)
        add_button = QPushButton(tr("identity_v2_raid_points.add_special"))
        add_button.clicked.connect(lambda: self._add_row(None, 0, ""))
        layout.addWidget(add_button)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_row(self, adjustment_id: str | None, value: int, reason: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        spin = QSpinBox()
        spin.setRange(-9999, 9999)
        spin.setValue(value)
        spin.setObjectName(f"special_value_{adjustment_id or row}")
        explanation = QLineEdit(reason)
        explanation.setPlaceholderText(tr("raid_points.reason_required"))
        self.table.setCellWidget(row, 0, spin)
        self.table.setCellWidget(row, 1, explanation)
        self._editors.append((adjustment_id, spin, explanation))

    def _accept_if_valid(self) -> None:
        for _point_id, spin, reason in self._editors:
            if spin.value() and not reason.text().strip():
                reason.setFocus()
                QMessageBox.warning(
                    self, tr("identity_v2_raid_points.title"),
                    tr("raid_points.reason_required_error"))
                return
        self.accept()

    def edits(self) -> tuple[tuple[str | None, int, str], ...]:
        return tuple((point_id, spin.value(), reason.text().strip())
                     for point_id, spin, reason in self._editors)


class IdentityV2CharacterDataPage(QWidget):
    """A filtered character grid sharing one member order with details."""

    storeChanged = Signal(object)
    pointHistoryRequested = Signal(str)

    def __init__(self, layout_settings: dict | None = None) -> None:
        super().__init__()
        settings = layout_settings if isinstance(layout_settings, dict) else {}
        self.store: IdentityV2Store | None = None
        self.point_projection = None
        self.dkp_projection = None
        self.point_presentation = ActivePointPresentation(POINT_MODE_RAID)
        self.gravestone_templates_provider = lambda: ()
        self.point_error: str | None = None
        self.project_path: Path | None = None
        self.rows_by_id: dict[str, CharacterTableRow] = {}
        self._order_ids: list[str] | None = None
        self._sort_state: tuple[int, bool] | None = None
        self.visible_member_ids: tuple[str, ...] = ()
        self.selected_member_id: str | None = None
        self._detail_loading = False
        self._detail_note_member_id: str | None = None
        self._widths = _widths(settings.get(COLUMN_WIDTHS_SETTING))
        self._splitter_sizes = _splitter_sizes(settings.get(SPLITTER_SIZES_SETTING))
        self._details_visible = settings.get(DETAIL_VISIBLE_SETTING, True)
        if not isinstance(self._details_visible, bool):
            self._details_visible = True
        self.setObjectName("identityV2CharacterDataPage")
        self.setStyleSheet("""
            QWidget#identityV2CharacterDataPage {background:#11181f;}
            QWidget#identityV2CharacterDataPage QTableWidget {
                background:#11181f;alternate-background-color:#17212a;
                border:1px solid #584832;gridline-color:#29333c;
                selection-background-color:#302b22;selection-color:#f5dfb1;
            }
            QWidget#identityV2CharacterDataPage QHeaderView::section {
                background:#202830;color:#e1c183;
                border-right:1px solid #584832;border-bottom:1px solid #80643f;
                padding:4px;
            }
            QWidget#identityV2CharacterDataPage QFrame#characterDetail {
                background:#17212a;border:1px solid #80643f;border-radius:6px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(9)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel(tr("identity_v2_character_data.title")))
        self.count_label = QLabel("")
        toolbar.addWidget(self.count_label)
        toolbar.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("identity_v2_character_data.search"))
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(250)
        self.search.textChanged.connect(self._refresh_table)
        toolbar.addWidget(self.search)
        self.status_filter = QComboBox()
        for status in ("all", "active", "inactive", "graveyard"):
            self.status_filter.addItem(tr(f"identity_v2_character_data.filter_{status}"), status)
        self.status_filter.currentIndexChanged.connect(self._refresh_table)
        toolbar.addWidget(self.status_filter)
        self.gear_filter = QComboBox()
        self.gear_filter.addItem(tr("identity_v2_character_data.filter_all_gear"), None)
        for value in GEAR_STATUSES:
            self.gear_filter.addItem(_gear_text(value), value)
        self.gear_filter.currentIndexChanged.connect(self._refresh_table)
        toolbar.addWidget(self.gear_filter)
        self.details_button = QPushButton(tr("identity_v2_character_data.show_details"))
        self.details_button.setCheckable(True)
        toolbar.addWidget(self.details_button)
        layout.addLayout(toolbar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = CharacterDataTable(self)
        self.table.setHorizontalHeaderLabels([
            tr(f"identity_v2_character_data.column_{key}") for key in COLUMNS
        ])
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table_row_hover = install_row_hover(self.table, custom_delegate=True)
        self.table.setItemDelegate(CharacterDataDelegate(self))
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSectionsMovable(True)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(60)
        for column, width in enumerate(self._widths):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(column, width)
        header.sectionClicked.connect(self._sort_by_column)
        header.sectionMoved.connect(self._keep_dead_last)
        header.sectionResized.connect(self._column_resized)
        self.table.currentCellChanged.connect(self._table_current_changed)
        self.table.cellClicked.connect(self._table_cell_clicked)
        self.table.itemChanged.connect(self._table_item_changed)
        self.splitter.addWidget(self.table)

        self.detail_panel = QFrame()
        self.detail_panel.setObjectName("characterDetail")
        self.detail_panel.setMinimumWidth(310)
        self.detail_panel.setMaximumWidth(470)
        detail_layout = QVBoxLayout(self.detail_panel)
        detail_layout.setContentsMargins(8, 8, 8, 10)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        detail_content = QWidget()
        content_layout = QVBoxLayout(detail_content)
        hero = QHBoxLayout()
        self.portrait = QLabel()
        self.portrait.setFixedSize(220, 220)
        self.portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.portrait.setStyleSheet("border:1px solid #584832;background:#11181f;")
        hero.addWidget(self.portrait)
        heading = QVBoxLayout()
        self.detail_name = QLabel("–")
        self.detail_name.setWordWrap(True)
        self.detail_name.setStyleSheet("color:#f5dfb1;font-weight:700;")
        self.detail_status = QLabel("–")
        self.detail_player = QLabel("–")
        self.detail_role = QLabel("–")
        for widget in (self.detail_name, self.detail_status, self.detail_player,
                       self.detail_role):
            widget.setTextFormat(Qt.TextFormat.PlainText)
            widget.setWordWrap(True)
            heading.addWidget(widget)
        heading.addStretch(1)
        hero.addLayout(heading, 1)
        content_layout.addLayout(hero)
        self.overview_form = QFormLayout()
        self.detail_values: dict[str, QWidget] = {}
        self.detail_editors: dict[str, QComboBox] = {}
        detail_columns = {
            "race": 3, "class": 4, "spec": 5, "raid_role": 6,
            "gear": 7, "raid_status": 8,
        }
        for key in ("race", "class", "spec", "raid_role", "gear", "raid_status",
                    "last_checked", "last_raid", "raid_count", "death_date",
                    "raid_points", "eternal_raid_points", "available_dkp",
                    "eternal_dkp", "dkp_rank", "raid_rank"):
            if key in detail_columns:
                value = DetailChoiceComboBox()
                value.setMinimumHeight(28)
                value.activated.connect(
                    lambda _index, column=detail_columns[key]:
                    self._detail_combo_changed(column))
                self.detail_editors[key] = value
            else:
                value = QLabel("–")
                value.setTextFormat(Qt.TextFormat.PlainText)
                value.setWordWrap(True)
            self.detail_values[key] = value
            self.overview_form.addRow(tr(f"identity_v2_character_data.detail_{key}"), value)
            self.overview_form.setRowVisible(
                value, self.point_presentation.shows(key))
        content_layout.addLayout(self.overview_form)
        self.burial_row = QWidget()
        burial_layout = QHBoxLayout(self.burial_row)
        burial_layout.setContentsMargins(0, 0, 0, 0)
        burial_layout.addWidget(QLabel(tr("identity_v2_character_data.burial")))
        self.burial_choice = QComboBox()
        self.burial_choice.setObjectName("burial_choice")
        self.burial_choice.setToolTip(tr("identity_v2_character_data.change_burial"))
        self.burial_choice.addItem(tr("identity_v2_character_data.burial_individual"),
                                   "individual")
        self.burial_choice.addItem(tr("identity_v2_character_data.burial_collective"),
                                   "collective")
        self.burial_choice.activated.connect(self._burial_changed)
        burial_layout.addWidget(self.burial_choice, 1)
        content_layout.addWidget(self.burial_row)
        content_layout.addWidget(QLabel(tr("identity_v2_character_data.notes")))
        self.detail_note = QTextEdit()
        self.detail_note.setMinimumHeight(95)
        self.detail_note.textChanged.connect(self._note_draft_changed)
        content_layout.addWidget(self.detail_note)
        self.note_save_button = QPushButton(tr("identity_v2_character_data.save_note"))
        self.note_save_button.clicked.connect(self._save_note)
        content_layout.addWidget(self.note_save_button)
        self.confirm_check_button = QPushButton(
            tr("identity_v2_character_data.confirm_check"))
        self.confirm_check_button.clicked.connect(self._confirm_check)
        content_layout.addWidget(self.confirm_check_button)
        self.special_points_button = QPushButton(
            tr("identity_v2_raid_points.special_action"))
        self.special_points_button.clicked.connect(self._edit_special_points)
        content_layout.addWidget(self.special_points_button)
        self.point_history_button = QPushButton(tr("raid_points.point_history"))
        self.point_history_button.clicked.connect(
            lambda: self.pointHistoryRequested.emit(self.selected_member_id)
            if self.selected_member_id else None)
        content_layout.addWidget(self.point_history_button)
        self.mark_dead_button = QPushButton(
            f"☠ {tr('identity_v2_character_data.mark_dead')}")
        self.mark_dead_button.setStyleSheet("""
            QPushButton {background:#8b2d35;color:#ffffff;border:1px solid #c9757b;
                         border-radius:4px;padding:6px;font-weight:600;}
            QPushButton:hover {background:#a83a43;}
            QPushButton:pressed {background:#74252c;}
            QPushButton:focus {border-color:#f0a2a7;}
            QPushButton:disabled {background:#292025;color:#86777a;border-color:#544044;}
        """)
        self.mark_dead_button.clicked.connect(
            lambda: self._request_death_for_member(self.selected_member_id))
        content_layout.addWidget(self.mark_dead_button)
        self.correct_death_date_button = QPushButton(
            tr("identity_v2_character_data.correct_death_date"))
        self.correct_death_date_button.clicked.connect(
            lambda: self._request_death_date_correction(self.selected_member_id))
        content_layout.addWidget(self.correct_death_date_button)
        self.clear_death_button = QPushButton(
            tr("identity_v2_character_data.clear_death_marking"))
        self.clear_death_button.clicked.connect(
            lambda: self._request_clear_death_marking(self.selected_member_id))
        content_layout.addWidget(self.clear_death_button)
        content_layout.addStretch(1)
        self.detail_scroll.setWidget(detail_content)
        detail_layout.addWidget(self.detail_scroll, 1)
        navigation = QHBoxLayout()
        self.previous_button = QPushButton(tr("identity_v2_character_data.previous"))
        self.next_button = QPushButton(tr("identity_v2_character_data.next"))
        self.position_label = QLabel("")
        self.previous_button.clicked.connect(lambda: self._step(-1))
        self.next_button.clicked.connect(lambda: self._step(1))
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.position_label)
        navigation.addWidget(self.next_button)
        detail_layout.addLayout(navigation)
        self.splitter.addWidget(self.detail_panel)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes(self._splitter_sizes)
        self.splitter.splitterMoved.connect(self._splitter_moved)
        layout.addWidget(self.splitter, 1)
        self._apply_order(_order(settings.get(COLUMN_ORDER_SETTING)))
        self.details_button.toggled.connect(self._toggle_details)
        self.details_button.setChecked(self._details_visible)
        self._toggle_details(self._details_visible)
        self._render_detail()

    def _apply_order(self, keys: list[str]) -> None:
        header = self.table.horizontalHeader()
        blocked = header.blockSignals(True)
        try:
            for visual, key in enumerate(keys):
                header.moveSection(header.visualIndex(COLUMNS.index(key)), visual)
        finally:
            header.blockSignals(blocked)

    def _keep_dead_last(self, *_args) -> None:
        header = self.table.horizontalHeader()
        if header.visualIndex(len(COLUMNS) - 1) != len(COLUMNS) - 1:
            blocked = header.blockSignals(True)
            try:
                header.moveSection(header.visualIndex(len(COLUMNS) - 1), len(COLUMNS) - 1)
            finally:
                header.blockSignals(blocked)

    def _column_resized(self, column: int, _old: int, new: int) -> None:
        if 0 <= column < len(self._widths):
            if column == len(COLUMNS) - 1 and new > 90:
                self.table.setColumnWidth(column, 90)
                return
            self._widths[column] = new

    def _splitter_moved(self, _position: int, _index: int) -> None:
        sizes = self.splitter.sizes()
        if len(sizes) == 2 and all(size > 0 for size in sizes):
            self._splitter_sizes = sizes

    def _toggle_details(self, visible: bool) -> None:
        self._details_visible = visible
        self.detail_panel.setVisible(visible)
        if visible:
            self.splitter.setSizes(self._splitter_sizes)
        self._render_detail()

    def layout_settings(self) -> dict[str, object]:
        header = self.table.horizontalHeader()
        sizes = self.splitter.sizes()
        if self._details_visible and len(sizes) == 2 and all(size > 0 for size in sizes):
            self._splitter_sizes = sizes
        return {
            DETAIL_VISIBLE_SETTING: self._details_visible,
            SPLITTER_SIZES_SETTING: self._splitter_sizes.copy(),
            COLUMN_WIDTHS_SETTING: [self.table.columnWidth(i) for i in range(len(COLUMNS))],
            COLUMN_ORDER_SETTING: [COLUMNS[header.logicalIndex(i)]
                                   for i in range(len(COLUMNS))],
        }

    def set_project_path(self, path: Path | str | None) -> None:
        self.project_path = Path(path).resolve() if path is not None else None
        if self.store is not None:
            self._render_detail()

    def set_store(self, store: IdentityV2Store | None, *, reset_filters: bool = False) -> None:
        self.store = store
        if reset_filters:
            self._order_ids = None
            self._sort_state = None
            for widget, index in ((self.status_filter, 0), (self.gear_filter, 0)):
                blocked = widget.blockSignals(True)
                widget.setCurrentIndex(index)
                widget.blockSignals(blocked)
            blocked = self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(blocked)
            self.selected_member_id = None
        rows = character_table_rows(store) if store is not None else ()
        self.rows_by_id = {row.memberId: row for row in rows}
        if self._order_ids is None:
            self._order_ids = [row.memberId for row in sorted(
                rows, key=lambda row: (row.name.casefold(), row.memberId))]
        else:
            self._order_ids = [member_id for member_id in self._order_ids
                               if member_id in self.rows_by_id]
            self._order_ids.extend(row.memberId for row in sorted(
                rows, key=lambda row: (row.name.casefold(), row.memberId))
                if row.memberId not in self._order_ids)
        self._refresh_table()

    def set_point_projection(self, projection, error: str | None = None) -> None:
        self.point_projection = projection
        self.point_error = error
        self._render_detail()

    def set_dkp_projection(self, projection) -> None:
        self.dkp_projection = projection
        self._render_detail()

    def set_active_point_system(self, mode: str) -> None:
        self.point_presentation = ActivePointPresentation(mode)
        for key, value in self.detail_values.items():
            self.overview_form.setRowVisible(
                value, self.point_presentation.shows(key))
        self.special_points_button.setVisible(
            self.point_presentation.shows("raid_point_adjustment"))
        self.point_history_button.setVisible(
            self.point_presentation.shows("raid_point_history"))
        self._render_detail()

    def set_gravestone_templates_provider(self, provider) -> None:
        self.gravestone_templates_provider = provider

    def _edit_special_points(self) -> bool:
        member_id = self.selected_member_id
        if (member_id is None or self.store is None
                or self.point_projection is None):
            return False
        member = next((item for item in self.store.members
                       if item.memberId == member_id), None)
        if member is None:
            return False
        source, payload, project_path = self.store, self.store.to_payload(), self.project_path
        adjustments = tuple(item for item in source.raidPoints.member_adjustments.values()
                            if item.member_id == member_id)
        dialog = MemberSpecialPointsDialog(member.name, adjustments, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        if not self._correction_context_is_current(source, payload, project_path):
            return False
        return self._execute((member_id,), lambda store: apply_v2_member_special_edits(
            store, member_id, dialog.edits()))

    def _sort_by_column(self, column: int) -> None:
        if column == len(COLUMNS) - 1 or column < 0 or not self.rows_by_id:
            return
        descending = self._sort_state == (column, False)
        self._sort_state = (column, descending)
        role_order = {value: index for index, value in enumerate(RAID_ROLES)}
        gear_order = {value: index for index, value in enumerate(GEAR_STATUSES)}
        raid_status_order = {value: index for index, value in enumerate(RAID_STATUSES)}

        def key(member_id: str):
            row = self.rows_by_id[member_id]
            value = (
                row.name, row.playerName, row.playerRole, row.race, row.className,
                row.spec, role_order[row.raidRole], gear_order[row.gearStatus],
                raid_status_order[row.raidStatus], row.lastChecked, row.lastRaidDate,
            )[column]
            if isinstance(value, str):
                value = value.casefold()
            return value is None, value if value is not None else "", member_id

        self._order_ids.sort(key=key, reverse=descending)
        self._refresh_table()

    def _matches(self, row: CharacterTableRow, query: str, status: str,
                 gear: str | None) -> bool:
        if status == "active" and row.lifeStatus != "active":
            return False
        if status == "inactive" and row.lifeStatus != "inactive":
            return False
        if status == "graveyard" and row.lifeStatus != "dead":
            return False
        if gear is not None and row.gearStatus != gear:
            return False
        searchable = (
            row.name, row.playerName or tr("identity_v2_character_data.unknown_player"),
            row.race or "", row.className or "", row.spec or "", row.raidRole,
            _raid_role_text(row.raidRole), row.note,
        )
        return not query or any(query in value.casefold() for value in searchable)

    def _field_options(self, column: int, row: CharacterTableRow) -> list[tuple[str, str | None]]:
        neutral = tr("common.not_set")
        if column == 3:
            return [(neutral, None), *((value, value) for value in RACES)]
        if column == 4:
            return [(tr("identity_v2_character_data.unknown_class"), None),
                    *((value, value) for value in CLASS_SPECS)]
        if column == 5:
            return [(neutral, None),
                    *((value, value) for value in CLASS_SPECS.get(row.className, ()))]
        if column == 6:
            return [(_raid_role_text(value), value) for value in RAID_ROLES]
        if column == 7:
            return [(_gear_text(value), value) for value in GEAR_STATUSES]
        if column == 8:
            return [(_raid_status_text(value), value) for value in RAID_STATUSES]
        return []

    @staticmethod
    def _raw_value(row: CharacterTableRow, column: int) -> str | None:
        return getattr(row, FIELD_BY_COLUMN[column]) if column in FIELD_BY_COLUMN else None

    def _set_table_row(self, row_index: int, row: CharacterTableRow) -> None:
        values = (
            row.name,
            row.playerName or tr("identity_v2_character_data.unknown_player"),
            _role_text(row.playerRole), row.race or "–",
            row.className or tr("identity_v2_character_data.unknown_class"),
            row.spec or "–", _raid_role_text(row.raidRole),
            _gear_text(row.gearStatus), _raid_status_text(row.raidStatus),
            _date_text(row.lastChecked), _date_text(row.lastRaidDate),
            tr("identity_v2_character_data.dead") if row.isDead else "☠",
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, row.memberId)
            if column in EDITABLE_COLUMNS:
                item.setData(RAW_ROLE, self._raw_value(row, column))
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if column == len(COLUMNS) - 1:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setData(DEATH_ACTION_ROLE, not row.isDead)
                item.setToolTip(
                    tr("identity_v2_character_data.dead_since", date=row.deathDate)
                    if row.isDead and row.deathDate else
                    tr("identity_v2_character_data.mark_dead_tooltip")
                    if not row.isDead else tr("identity_v2_character_data.dead"))
            self.table.setItem(row_index, column, item)

    def _refresh_table(self, *_args) -> None:
        query = self.search.text().strip().casefold()
        status = self.status_filter.currentData()
        gear = self.gear_filter.currentData()
        self.visible_member_ids = tuple(member_id for member_id in self._order_ids or ()
                                        if self._matches(self.rows_by_id[member_id], query,
                                                         status, gear))
        if self.selected_member_id not in self.visible_member_ids:
            self.selected_member_id = self.visible_member_ids[0] if self.visible_member_ids else None
        blocked = self.table.blockSignals(True)
        self.table.setRowCount(len(self.visible_member_ids))
        try:
            for row_index, member_id in enumerate(self.visible_member_ids):
                self._set_table_row(row_index, self.rows_by_id[member_id])
            if self.selected_member_id is not None:
                index = self.visible_member_ids.index(self.selected_member_id)
                self.table.setCurrentCell(index, 0)
                self.table.scrollToItem(self.table.item(index, 0))
            else:
                self.table.clearSelection()
        finally:
            self.table.blockSignals(blocked)
        self.count_label.setText(f"{len(self.visible_member_ids)} / {len(self.rows_by_id)}")
        self._render_detail()

    def _reset_table_row(self, member_id: str) -> None:
        if member_id not in self.visible_member_ids:
            return
        blocked = self.table.blockSignals(True)
        try:
            self._set_table_row(self.visible_member_ids.index(member_id),
                                self.rows_by_id[member_id])
        finally:
            self.table.blockSignals(blocked)

    def _accept_result(self, result: IdentityV2Store,
                       member_ids: tuple[str, ...]) -> bool:
        if self.store is None or result is self.store:
            return False
        new_members = {member.memberId: member for member in result.members}
        new_players = {player.playerId: player for player in result.players}
        old_mains = {player.playerId: player.mainMemberId for player in self.store.players}
        affected_ids = set(member_ids)
        for player_id, player in new_players.items():
            previous_main = old_mains.get(player_id)
            if previous_main != player.mainMemberId:
                affected_ids.update(item for item in (previous_main, player.mainMemberId)
                                    if item in self.rows_by_id)
        updated: dict[str, CharacterTableRow] = {}
        for member_id in sorted(affected_ids):
            old = self.rows_by_id[member_id]
            member = new_members[member_id]
            player = new_players.get(member.playerId)
            player_role = (None if player is None else
                           "main" if player.mainMemberId == member_id else "twink")
            row = replace(
                old, race=member.race, className=member.className,
                spec=member.spec, raidRole=member.raidRole,
                gearStatus=member.gearStatus, raidStatus=member.raidStatus,
                note=member.note, lastChecked=member.lastChecked,
                playerRole=player_role, lifeStatus=member.lifeStatus,
                isDead=member.lifeStatus == "dead", deathDate=member.deathDate,
            )
            if row != old:
                updated[member_id] = row
        if not updated:
            old_members = {member.memberId: member for member in self.store.members}
            if (not any(new_members[member_id].burialType != old_members[member_id].burialType
                        for member_id in member_ids)
                    and result.raidPoints.to_dict() == self.store.raidPoints.to_dict()):
                return False
            self.store = result
            self._render_detail()
            self.storeChanged.emit(result)
            return True
        query = self.search.text().strip().casefold()
        status = self.status_filter.currentData()
        gear = self.gear_filter.currentData()
        membership_changed = any(
            (member_id in self.visible_member_ids)
            != self._matches(row, query, status, gear)
            for member_id, row in updated.items()
        )
        self.store = result
        self.rows_by_id.update(updated)
        if membership_changed:
            if self.selected_member_id not in self.visible_member_ids or not self._matches(
                    self.rows_by_id[self.selected_member_id], query, status, gear):
                previous = self.visible_member_ids
                position = (previous.index(self.selected_member_id)
                            if self.selected_member_id in previous else 0)
                remaining = tuple(member_id for member_id in previous
                                  if self._matches(self.rows_by_id[member_id], query, status, gear))
                self.selected_member_id = next(
                    (member_id for member_id in previous[position + 1:]
                     if member_id in remaining),
                    remaining[-1] if remaining else None)
            self._refresh_table()
        else:
            blocked = self.table.blockSignals(True)
            try:
                for member_id, row in updated.items():
                    if member_id in self.visible_member_ids:
                        self._set_table_row(self.visible_member_ids.index(member_id), row)
            finally:
                self.table.blockSignals(blocked)
            self._render_detail()
        self.storeChanged.emit(result)
        return True

    def _execute(self, member_ids: tuple[str, ...], operation,
                 *, on_successor_required=None) -> bool:
        if self.store is None:
            return False
        error = None
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = operation(self.store)
        except Exception as exc:
            error = exc
            result = None
        finally:
            QApplication.restoreOverrideCursor()
        if error is not None:
            if (isinstance(error, MainSuccessorSelectionRequired)
                    and on_successor_required is not None):
                successor_id = self._choose_main_successor(error.candidates)
                if successor_id is None:
                    return False
                return self._execute(
                    member_ids,
                    lambda store: on_successor_required(store, successor_id),
                )
            if isinstance(error, DeathAttendanceConflict):
                QMessageBox.warning(
                    self, tr("identity_v2_character_data.death_conflict_title"),
                    tr("identity_v2_character_data.death_conflict",
                       count=error.conflict_count,
                       date=_date_text(error.first_raid_date), raid=error.first_raid_id))
            elif isinstance(error, MainSuccessorSelectionRequired):
                candidates = ", ".join(
                    f"{item.name} ({item.memberId})" for item in error.candidates)
                QMessageBox.warning(
                    self, tr("identity_v2_character_data.successor_required_title"),
                    tr("identity_v2_character_data.successor_required",
                       candidates=candidates))
            elif isinstance(error, BurialTypeError):
                QMessageBox.warning(
                    self, tr("identity_v2_character_data.edit_error_title"),
                    tr(f"identity_v2_character_data.burial_error_{error.reason}"))
            elif isinstance(error, GravestoneUnavailableError):
                QMessageBox.warning(
                    self, tr("identity_v2_character_data.edit_error_title"),
                    tr("identity_v2_character_data.no_free_gravestone"))
            elif isinstance(error, DeathCorrectionError):
                QMessageBox.warning(
                    self, tr("identity_v2_character_data.edit_error_title"),
                    tr(f"identity_v2_character_data.correction_error_{error.reason}"))
            else:
                QMessageBox.warning(
                    self, tr("identity_v2_character_data.edit_error_title"),
                    tr("identity_v2_character_data.edit_failed", error=error))
            return False
        return self._accept_result(result, member_ids)

    def _run_single(self, member_id: str, column: int,
                    value: str | None) -> bool:
        services = {
            3: set_member_race, 4: set_member_class, 5: set_member_spec,
            6: set_member_raid_role, 7: set_member_gear_status,
            8: set_member_raid_status,
        }
        if column not in services:
            return False
        return self._execute(
            (member_id,), lambda store: services[column](store, member_id, value))

    def _table_item_changed(self, item: QTableWidgetItem) -> None:
        member_id = item.data(Qt.ItemDataRole.UserRole)
        if member_id not in self.rows_by_id:
            return
        if item.column() in EDITABLE_COLUMNS:
            self._run_single(member_id, item.column(),
                             item.data(Qt.ItemDataRole.EditRole))
        self._reset_table_row(member_id)

    def _detail_combo_changed(self, column: int) -> None:
        if self._detail_loading or self.selected_member_id not in self.rows_by_id:
            return
        detail_key = {
            3: "race", 4: "class", 5: "spec", 6: "raid_role",
            7: "gear", 8: "raid_status",
        }[column]
        value = self.detail_editors[detail_key].currentData()
        self._run_single(self.selected_member_id, column, value)
        self._render_detail()

    def _note_draft_changed(self) -> None:
        row = self.rows_by_id.get(self.selected_member_id)
        self.note_save_button.setEnabled(
            not self._detail_loading and row is not None
            and self.detail_note.toPlainText().strip() != row.note)

    def _save_note(self) -> None:
        member_id = self.selected_member_id
        if member_id is None:
            return
        value = self.detail_note.toPlainText()
        self._execute((member_id,), lambda store: set_member_note(store, member_id, value))
        self._render_detail()

    def _confirm_check(self) -> None:
        member_id = self.selected_member_id
        if member_id is None:
            return
        today = date.today()
        self._execute((member_id,), lambda store: confirm_member_check(
            store, member_id, today))

    def _burial_changed(self, _index: int) -> None:
        member_id = self.selected_member_id
        if self._detail_loading or member_id is None or self.store is None:
            return
        burial_type = self.burial_choice.currentData()
        templates = (tuple(self.gravestone_templates_provider())
                     if burial_type == "individual" else ())
        self._execute((member_id,), lambda store: set_member_burial_type(
            store, member_id, burial_type, gravestone_templates=templates))
        self._render_detail()

    def _table_cell_clicked(self, table_row: int, column: int) -> None:
        if column != len(COLUMNS) - 1 or table_row < 0:
            return
        item = self.table.item(table_row, 0)
        if item is not None:
            self._request_death_for_member(item.data(Qt.ItemDataRole.UserRole))

    def _choose_death_details(self, row: CharacterTableRow) -> tuple[date, str] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("identity_v2_character_data.death_dialog_title"))
        dialog.setMinimumWidth(320)
        layout = QVBoxLayout(dialog)
        description = QLabel(tr(
            "identity_v2_character_data.death_dialog_message",
            character=row.name,
            class_name=row.className or tr("identity_v2_character_data.unknown_class")))
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        date_input = QDateEdit()
        date_input.setCalendarPopup(True)
        date_input.setDate(QDate.currentDate())
        date_input.setDisplayFormat("dd.MM.yyyy" if get_language() == "de" else "yyyy-MM-dd")
        form.addRow(tr("identity_v2_character_data.death_date"), date_input)
        burial_choices = QWidget()
        choice_layout = QVBoxLayout(burial_choices)
        choice_layout.setContentsMargins(0, 0, 0, 0)
        individual = QRadioButton(tr("identity_v2_character_data.burial_individual"))
        individual.setObjectName("death_burial_individual")
        collective = QRadioButton(tr("identity_v2_character_data.burial_collective"))
        collective.setObjectName("death_burial_collective")
        choice_layout.addWidget(individual)
        choice_layout.addWidget(collective)
        form.addRow(tr("identity_v2_character_data.burial_type"), burial_choices)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            tr("identity_v2_character_data.confirm_death"))
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        individual.toggled.connect(
            lambda _checked: buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
                individual.isChecked() or collective.isChecked()))
        collective.toggled.connect(
            lambda _checked: buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
                individual.isChecked() or collective.isChecked()))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            tr("identity_v2_character_data.cancel_death"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        if not (individual.isChecked() or collective.isChecked()):
            return None
        return (date_input.date().toPython(),
                "individual" if individual.isChecked() else "collective")

    def _choose_main_successor(
        self, candidates: tuple[MainSuccessorCandidate, ...],
    ) -> str | None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("identity_v2_character_data.choose_successor_title"))
        dialog.setMinimumWidth(340)
        layout = QVBoxLayout(dialog)
        label = QLabel(tr("identity_v2_character_data.choose_successor_message"))
        label.setWordWrap(True)
        layout.addWidget(label)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(240)
        choices = QWidget()
        choice_layout = QVBoxLayout(choices)
        choice_layout.setContentsMargins(8, 4, 8, 4)
        radios: list[tuple[str, QRadioButton]] = []
        for candidate in candidates:
            class_name = candidate.className or tr(
                "identity_v2_character_data.unknown_class")
            radio = QRadioButton(f"{candidate.name} — {class_name}", choices)
            radio.setObjectName(f"successor_option_{candidate.memberId}")
            radio.setToolTip(tr("identity_v2_character_data.successor_member_id",
                                member_id=candidate.memberId))
            choice_layout.addWidget(radio)
            radios.append((candidate.memberId, radio))
        choice_layout.addStretch(1)
        scroll.setWidget(choices)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        confirm = buttons.button(QDialogButtonBox.StandardButton.Ok)
        confirm.setText(tr("identity_v2_character_data.apply_successor"))
        confirm.setEnabled(False)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            tr("identity_v2_character_data.cancel_death"))
        for _member_id, radio in radios:
            radio.toggled.connect(lambda _checked: confirm.setEnabled(
                any(option.isChecked() for _, option in radios)))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return next((member_id for member_id, radio in radios if radio.isChecked()), None)

    def _request_death_for_member(self, member_id: str | None) -> bool:
        row = self.rows_by_id.get(member_id)
        if row is None or row.isDead or self.store is None:
            return False
        details = self._choose_death_details(row)
        if details is None:
            return False
        templates = (tuple(self.gravestone_templates_provider())
                     if details[1] == "individual" else ())
        return self._execute(
            (row.memberId,),
            lambda store: mark_member_dead(
                store, row.memberId, *details, gravestone_templates=templates),
            on_successor_required=lambda store, successor_id: mark_member_dead(
                store, row.memberId, *details, successor_id,
                gravestone_templates=templates),
        )

    def _has_member_main_history(self, member_id: str) -> bool:
        return self.store is not None and any(
            entry.memberId == member_id
            for player in self.store.players for entry in player.mainHistory)

    def _correction_context_is_current(
        self, source: IdentityV2Store, payload: dict, project_path: Path | None,
    ) -> bool:
        if (self.store is source and self.project_path == project_path
                and self.store.to_payload() == payload):
            return True
        QMessageBox.warning(
            self, tr("identity_v2_character_data.edit_error_title"),
            tr("identity_v2_character_data.correction_stale"))
        return False

    def _show_main_history_hint(self, member_id: str) -> None:
        if self._has_member_main_history(member_id):
            QMessageBox.information(
                self, tr("identity_v2_character_data.main_history_hint_title"),
                tr("identity_v2_character_data.main_history_hint"))

    def _choose_corrected_death_date(self, row: CharacterTableRow) -> date | None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("identity_v2_character_data.correct_death_date"))
        layout = QVBoxLayout(dialog)
        description = QLabel(tr(
            "identity_v2_character_data.correct_death_date_message",
            character=row.name,
            previous=_date_text(row.deathDate) if row.deathDate else tr(
                "identity_v2_character_data.unknown_death_date")))
        description.setWordWrap(True)
        layout.addWidget(description)
        date_input = QDateEdit()
        date_input.setObjectName("corrected_death_date")
        date_input.setCalendarPopup(True)
        date_input.setDisplayFormat("dd.MM.yyyy" if get_language() == "de" else "yyyy-MM-dd")
        date_input.setDate(QDate.fromString(row.deathDate, "yyyy-MM-dd")
                           if row.deathDate else QDate.currentDate())
        layout.addWidget(date_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            tr("identity_v2_character_data.confirm_correction"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return (date_input.date().toPython()
                if dialog.exec() == QDialog.DialogCode.Accepted else None)

    def _choose_clear_death_status(self, row: CharacterTableRow) -> str | None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("identity_v2_character_data.clear_death_marking"))
        layout = QVBoxLayout(dialog)
        label = QLabel(tr("identity_v2_character_data.clear_death_message",
                          character=row.name))
        label.setWordWrap(True)
        layout.addWidget(label)
        active = QRadioButton(tr("life.active"))
        active.setObjectName("clear_death_active")
        inactive = QRadioButton(tr("life.inactive"))
        inactive.setObjectName("clear_death_inactive")
        layout.addWidget(active)
        layout.addWidget(inactive)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        confirm = buttons.button(QDialogButtonBox.StandardButton.Ok)
        confirm.setText(tr("identity_v2_character_data.confirm_correction"))
        confirm.setEnabled(False)
        active.toggled.connect(lambda _checked: confirm.setEnabled(
            active.isChecked() or inactive.isChecked()))
        inactive.toggled.connect(lambda _checked: confirm.setEnabled(
            active.isChecked() or inactive.isChecked()))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return "active" if active.isChecked() else "inactive" if inactive.isChecked() else None

    def _request_death_date_correction(self, member_id: str | None) -> bool:
        row = self.rows_by_id.get(member_id)
        if row is None or not row.isDead or self.store is None:
            return False
        source, payload, project_path = self.store, self.store.to_payload(), self.project_path
        new_date = self._choose_corrected_death_date(row)
        if new_date is None or not self._correction_context_is_current(
                source, payload, project_path):
            return False
        changed = self._execute(
            (row.memberId,), lambda store: correct_member_death_date(
                store, row.memberId, new_date))
        if changed:
            self._show_main_history_hint(row.memberId)
        return changed

    def _request_clear_death_marking(self, member_id: str | None) -> bool:
        row = self.rows_by_id.get(member_id)
        if row is None or not row.isDead or self.store is None:
            return False
        source, payload, project_path = self.store, self.store.to_payload(), self.project_path
        target = self._choose_clear_death_status(row)
        if target is None or not self._correction_context_is_current(
                source, payload, project_path):
            return False
        changed = self._execute(
            (row.memberId,), lambda store: clear_member_death_marking(
                store, row.memberId, target))
        if changed:
            self._show_main_history_hint(row.memberId)
        return changed

    def copy_selection(self) -> str:
        indexes = self.table.selectedIndexes()
        if not indexes:
            return ""
        header = self.table.horizontalHeader()
        first_row = min(index.row() for index in indexes)
        last_row = max(index.row() for index in indexes)
        visual_columns = [header.visualIndex(index.column()) for index in indexes]
        columns = [header.logicalIndex(visual) for visual in
                   range(min(visual_columns), max(visual_columns) + 1)]
        copied = "\n".join(
            "\t".join(self.table.item(row, column).text() if self.table.item(row, column)
                      else "" for column in columns)
            for row in range(first_row, last_row + 1)
        )
        QApplication.clipboard().setText(copied)
        return copied

    def _pasted_value(self, column: int, row: CharacterTableRow,
                      text: str) -> str | None:
        value = text.strip()
        neutral = {"", "–", tr("common.not_set").casefold()}
        if column in (3, 4, 5) and value.casefold() in neutral:
            return None
        for label, stored in self._field_options(column, row):
            if value.casefold() in {label.casefold(), str(stored or "").casefold()}:
                return stored
        return value

    def paste_text(self, text: str) -> bool:
        current = self.table.currentIndex()
        if not current.isValid() or not text:
            return False
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        while lines and lines[-1] == "":
            lines.pop()
        if not lines:
            return False
        header = self.table.horizontalHeader()
        first_visual = header.visualIndex(current.column())
        proposed: list[MemberEdit] = []
        for row_offset, line in enumerate(lines):
            target_row = current.row() + row_offset
            if target_row >= len(self.visible_member_ids):
                QMessageBox.warning(self, tr("identity_v2_character_data.paste_error_title"),
                                    tr("identity_v2_character_data.paste_out_of_range"))
                return False
            member_id = self.visible_member_ids[target_row]
            row = self.rows_by_id[member_id]
            for column_offset, cell in enumerate(line.split("\t")):
                visual = first_visual + column_offset
                column = header.logicalIndex(visual) if visual < len(COLUMNS) else -1
                if column not in EDITABLE_COLUMNS:
                    QMessageBox.warning(self, tr("identity_v2_character_data.paste_error_title"),
                                        tr("identity_v2_character_data.paste_protected"))
                    return False
                proposed.append(MemberEdit(member_id, FIELD_BY_COLUMN[column],
                                           self._pasted_value(column, row, cell)))
        member_ids = tuple(dict.fromkeys(edit.memberId for edit in proposed))
        return self._execute(member_ids, lambda store: apply_member_edits(store, proposed))

    def _table_current_changed(self, current_row: int, _column: int, *_args) -> None:
        item = self.table.item(current_row, 0) if current_row >= 0 else None
        member_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if member_id in self.visible_member_ids:
            self.selected_member_id = member_id
            self._render_detail()

    def _step(self, direction: int) -> None:
        if self.selected_member_id not in self.visible_member_ids:
            return
        position = self.visible_member_ids.index(self.selected_member_id)
        target = position + direction
        if 0 <= target < len(self.visible_member_ids):
            self.selected_member_id = self.visible_member_ids[target]
            self.table.setCurrentCell(target, 0)
            self.table.scrollToItem(self.table.item(target, 0))
            self._render_detail()

    def _portrait_path(self, row: CharacterTableRow) -> Path | None:
        if self.project_path is None:
            return None
        try:
            candidate = member_portrait_path(self.project_path, row.memberId)
            return candidate if candidate.is_file() else None
        except (OSError, ValueError):
            return None

    def _render_detail(self) -> None:
        row = self.rows_by_id.get(self.selected_member_id)
        note_draft = self.detail_note.toPlainText()
        keep_note_draft = (
            row is not None and self._detail_note_member_id == row.memberId
            and note_draft.strip() != row.note)
        self._detail_loading = True
        if row is None or self.selected_member_id not in self.visible_member_ids:
            self._detail_note_member_id = None
            self.detail_name.setText(tr("identity_v2_character_data.empty"))
            self.detail_status.setText("–")
            self.detail_player.setText("–")
            self.detail_role.setText("–")
            self.detail_note.setPlainText("")
            self.detail_note.setEnabled(False)
            self.note_save_button.setEnabled(False)
            self.confirm_check_button.setEnabled(False)
            self.special_points_button.setEnabled(False)
            self.point_history_button.setEnabled(False)
            self.mark_dead_button.hide()
            self.correct_death_date_button.hide()
            self.clear_death_button.hide()
            self.burial_row.hide()
            self.portrait.setPixmap(QPixmap())
            self.portrait.setText(tr("identity_v2_character_data.no_portrait"))
            for value in self.detail_values.values():
                if isinstance(value, QComboBox):
                    value.clear()
                    value.setEnabled(False)
                else:
                    value.setText("–")
            self.position_label.setText("")
            self.previous_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self._detail_loading = False
            return
        position = self.visible_member_ids.index(row.memberId)
        self.detail_name.setText(row.name)
        self.detail_status.setText(tr(f"life.{row.lifeStatus}"))
        self.detail_player.setText(
            row.playerName or tr("identity_v2_character_data.unknown_player"))
        self.detail_role.setText(_role_text(row.playerRole))
        values = {
            "race": row.race or "–",
            "class": row.className or tr("identity_v2_character_data.unknown_class"),
            "spec": row.spec or "–", "raid_role": _raid_role_text(row.raidRole),
            "gear": _gear_text(row.gearStatus), "raid_status": _raid_status_text(row.raidStatus),
            "last_checked": _date_text(row.lastChecked),
            "last_raid": _date_text(row.lastRaidDate), "raid_count": str(row.raidCount),
            "death_date": _date_text(row.deathDate) if row.isDead else "–",
            "raid_points": (str(self.point_projection.character_points(row.memberId))
                            if self.point_projection is not None else "–"),
            "eternal_raid_points": (
                str(self.point_projection.eternal_character_points(row.memberId))
                if self.point_projection is not None else "–"),
            "available_dkp": _number_or_dash(
                self.dkp_projection.available_for_member(row.memberId)
                if self.dkp_projection is not None else None),
            "eternal_dkp": _number_or_dash(
                self.dkp_projection.eternal_for_member(row.memberId)
                if self.dkp_projection is not None else None),
            "dkp_rank": _rank_text(
                self.dkp_projection.dkp_rank_for_member(row.memberId)
                if self.dkp_projection is not None else None),
            "raid_rank": _rank_text(
                self.dkp_projection.raid_rank_for_member(row.memberId)
                if self.dkp_projection is not None else None),
        }
        for key, value in values.items():
            widget = self.detail_values[key]
            if isinstance(widget, QComboBox):
                column = {
                    "race": 3, "class": 4, "spec": 5, "raid_role": 6,
                    "gear": 7, "raid_status": 8,
                }[key]
                widget.clear()
                for label, stored in self._field_options(column, row):
                    widget.addItem(label, stored)
                chosen = widget.findData(self._raw_value(row, column))
                widget.setCurrentIndex(chosen if chosen >= 0 else 0)
                widget.setEnabled(True)
            else:
                widget.setText(value)
                if key in ("raid_points", "eternal_raid_points"):
                    widget.setToolTip(self.point_error or "")
        self.detail_note.setEnabled(True)
        self.detail_note.setPlainText(note_draft if keep_note_draft else row.note)
        self._detail_note_member_id = row.memberId
        self.note_save_button.setEnabled(keep_note_draft)
        self.confirm_check_button.setEnabled(row.lifeStatus == "active")
        self.special_points_button.setEnabled(self.point_projection is not None)
        self.point_history_button.setEnabled(self.point_projection is not None)
        self.mark_dead_button.setVisible(not row.isDead)
        self.correct_death_date_button.setVisible(row.isDead)
        self.clear_death_button.setVisible(row.isDead)
        self.burial_row.setVisible(row.isDead)
        if row.isDead and self.store is not None:
            member = next(item for item in self.store.members if item.memberId == row.memberId)
            self.burial_choice.setCurrentIndex(
                self.burial_choice.findData(member.burialType))
        portrait_path = self._portrait_path(row)
        picture = QPixmap(str(portrait_path)) if portrait_path is not None else QPixmap()
        if picture.isNull():
            self.portrait.setPixmap(QPixmap())
            self.portrait.setText(tr("identity_v2_character_data.no_portrait"))
        else:
            self.portrait.setText("")
            self.portrait.setPixmap(picture.scaled(
                self.portrait.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        self.position_label.setText(f"{position + 1} / {len(self.visible_member_ids)}")
        self.previous_button.setEnabled(position > 0)
        self.next_button.setEnabled(position + 1 < len(self.visible_member_ids))
        self._detail_loading = False
