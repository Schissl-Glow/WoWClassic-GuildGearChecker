"""Identity-V2 Player/character relationships, backed only by validated services."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QFrame, QGroupBox, QHeaderView,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QPushButton, QScrollArea, QSplitter, QTableWidget,
    QTableWidgetItem, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from .i18n import get_language, tr
from .identity_v2 import IdentityV2Store, Member, Player
from .identity_v2_point_presentation import ActivePointPresentation, POINT_MODE_RAID
from .qt_row_hover import install_row_hover
from .identity_v2_main_history_qt import HISTORY_COLUMN_WIDTHS, MainHistoryDialog
from .identity_v2_player_service import (
    assign_member, bulk_assign_members, bulk_create_players_from_members,
    clear_main, create_player_from_member, delete_player, reassign_member,
    rename_player, set_main, set_player_activity, unassign_member,
)


_KEEP = object()
PLAYER_COLUMN_WIDTHS_SETTING = "identity_v2_player_table_column_widths"
UNKNOWN_COLUMN_WIDTHS_SETTING = "identity_v2_unknown_table_column_widths"
PLAYER_SPLITTER_SIZES_SETTING = "identity_v2_players_splitter_sizes"
MAIN_HISTORY_COLUMN_WIDTHS_SETTING = "identity_v2_main_history_column_widths"


def _restore_widths(value, defaults: list[int]) -> list[int]:
    if not isinstance(value, (list, tuple)):
        return defaults.copy()
    result = defaults.copy()
    for index, width in enumerate(value[:len(defaults)]):
        if isinstance(width, int) and not isinstance(width, bool) and 32 <= width <= 2400:
            result[index] = width
    return result


def _format_date(value: date | None) -> str:
    if value is None:
        return "–"
    return value.strftime("%d.%m.%Y") if get_language() == "de" else value.isoformat()


class _CheckboxCharacterTable(QTableWidget):
    """Toggle the check column without changing the independent row selection."""

    def mousePressEvent(self, event):  # noqa: N802
        index = self.indexAt(event.position().toPoint())
        if (event.button() == Qt.MouseButton.LeftButton and index.isValid()
                and index.column() == 0):
            item = self.item(index.row(), index.column())
            if item is not None and item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(
                    Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked
                    else Qt.CheckState.Checked
                )
                event.accept()
                return
        super().mousePressEvent(event)


def _is_graveyard(member: Member) -> bool:
    return member.deathDate is not None or member.lifeStatus == "dead"


def _member_status(member: Member) -> str:
    if _is_graveyard(member):
        return tr("identity_v2_players.graveyard")
    return tr("identity_v2_players.inactive") if member.lifeStatus == "inactive" else tr(
        "identity_v2_players.active")


class IdentityV2PlayersPage(QWidget):
    storeChanged = Signal(object)
    pointHistoryRequested = Signal(str)
    profileRequested = Signal(str)

    def __init__(self, layout_settings: dict | None = None):
        super().__init__()
        self.store: IdentityV2Store | None = None
        self.point_projection = None
        self.point_error: str | None = None
        self.dkp_projection = None
        self.point_presentation = ActivePointPresentation(POINT_MODE_RAID)
        settings = layout_settings if isinstance(layout_settings, dict) else {}
        self._visible_members: dict[str | None, tuple[Member, ...]] = {}
        self.group_rows: dict[str, tuple[str, ...]] = {}
        self.member_rows: dict[str, QWidget] = {}
        self._player_order: list[str] | None = None
        self._player_sort: tuple[int, bool] | None = None
        self._unknown_order: list[str] | None = None
        self._unknown_sort: tuple[int, bool] | None = None
        self._raid_info: dict[str, tuple[int, date | None, date | None]] = {}
        self._player_main_names: dict[str, str | None] = {}
        self._player_character_counts: Counter[str] = Counter()
        self._members_by_id: dict[str, Member] = {}
        self._player_column_widths = _restore_widths(
            settings.get(PLAYER_COLUMN_WIDTHS_SETTING), [118, 82, 54])
        self._unknown_column_widths = _restore_widths(
            settings.get(UNKNOWN_COLUMN_WIDTHS_SETTING),
            [36, 190, 100, 84, 55, 100, 100],
        )
        self._main_history_column_widths = _restore_widths(
            settings.get(MAIN_HISTORY_COLUMN_WIDTHS_SETTING),
            list(HISTORY_COLUMN_WIDTHS),
        )
        raw_splitter_sizes = settings.get(PLAYER_SPLITTER_SIZES_SETTING)
        self._splitter_sizes = ([int(value) for value in raw_splitter_sizes]
                                if isinstance(raw_splitter_sizes, (list, tuple))
                                and len(raw_splitter_sizes) == 2
                                and all(isinstance(value, int) and not isinstance(value, bool)
                                        and value > 0 for value in raw_splitter_sizes)
                                else [255, 757])
        self.unassigned_table: _CheckboxCharacterTable | None = None
        self._checked_unassigned_ids: set[str] = set()
        self._unknown_current_member_id: str | None = None
        self.setObjectName("identityV2PlayersPage")
        self.setStyleSheet("""
            QWidget#identityV2PlayersPage {background:#11181f;}
            QWidget#identityV2DetailHost,
            QScrollArea#identityV2DetailScroll {background:#11181f; border:none;}
            QWidget#identityV2PlayersPage QGroupBox {
                color:#e1c183; border:1px solid #584832; margin-top:10px;
                padding-top:8px; font-weight:600;
            }
            QWidget#identityV2PlayersPage QGroupBox::title {
                subcontrol-origin:margin; left:10px; padding:0 5px;
            }
            QWidget#identityV2PlayersPage QListWidget {
                background:#141c23; alternate-background-color:#19242d;
                border:1px solid #584832;
            }
            QWidget#identityV2PlayersPage QListWidget::item:selected {
                background:#302b22; color:#f5dfb1;
            }
            QWidget#identityV2PlayersPage QTableWidget {
                background:#11181f; alternate-background-color:#17212a;
                border:1px solid #584832; gridline-color:#29333c;
                selection-background-color:#302b22; selection-color:#f5dfb1;
            }
            QWidget#identityV2PlayersPage QTableWidget::item:selected {
                background:#302b22; color:#f5dfb1;
            }
            QWidget#identityV2PlayersPage QHeaderView::section {
                background:#202830; color:#e1c183;
                border-right:1px solid #584832; border-bottom:1px solid #80643f;
                padding:4px;
            }
            QWidget#identityV2PlayersPage QFrame#characterRow {
                background:#19242d; border:1px solid #394650; border-radius:4px;
            }
            QWidget#identityV2PlayersPage QFrame#characterRow:hover {
                background:#222a2d; border-color:#80643f;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        top = QHBoxLayout()
        title = QLabel(tr("identity_v2_players.title"))
        title.setObjectName("sectionTitle")
        top.addWidget(title)
        top.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("identity_v2_players.search"))
        self.search.textChanged.connect(self._refresh_master)
        top.addWidget(self.search, 2)
        self.status_filter = QComboBox()
        for key in ("all", "active", "inactive", "graveyard"):
            self.status_filter.addItem(tr(f"identity_v2_players.filter_{key}"), key)
        self.status_filter.currentIndexChanged.connect(self._refresh_master)
        top.addWidget(self.status_filter)
        layout.addLayout(top)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.player_table = QTableWidget(0, 3)
        self.player_row_hover = install_row_hover(self.player_table)
        self.player_table.setHorizontalHeaderLabels((
            tr("identity_v2_players.player_column"),
            tr("identity_v2_players.main_column"),
            tr("identity_v2_players.chars_column"),
        ))
        self.player_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.player_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.player_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.player_table.setSortingEnabled(False)
        self.player_table.setAlternatingRowColors(True)
        self.player_table.verticalHeader().setVisible(False)
        self.player_table.horizontalHeader().setSectionsClickable(True)
        self.player_table.horizontalHeader().setStretchLastSection(False)
        self.player_table.horizontalHeader().setMinimumSectionSize(32)
        for index in range(self.player_table.columnCount()):
            self.player_table.horizontalHeader().setSectionResizeMode(
                index, QHeaderView.ResizeMode.Interactive)
        for index, width in enumerate(self._player_column_widths):
            self.player_table.setColumnWidth(index, width)
        self.player_table.horizontalHeader().sectionClicked.connect(self._sort_players)
        self.player_table.horizontalHeader().sectionResized.connect(
            self._player_width_changed)
        self.player_table.itemSelectionChanged.connect(self._render_detail)
        self.splitter.addWidget(self.player_table)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName("identityV2DetailScroll")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_host = QWidget()
        self.detail_host.setObjectName("identityV2DetailHost")
        self.detail_layout = QVBoxLayout(self.detail_host)
        self.detail_layout.setContentsMargins(8, 4, 8, 8)
        self.detail_scroll.setWidget(self.detail_host)
        self.splitter.addWidget(self.detail_scroll)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes(self._splitter_sizes)
        self.splitter.splitterMoved.connect(self._splitter_moved)
        layout.addWidget(self.splitter, 1)

    def set_store(
        self, store: IdentityV2Store | None, *, preferred_player_id: object = _KEEP,
        reset_filters: bool = False,
    ) -> None:
        self.store = store
        if reset_filters:
            self._checked_unassigned_ids.clear()
            self._unknown_current_member_id = None
            self._unknown_sort = None
            self._player_sort = None
            self._player_order = None
            self._unknown_order = None
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
            self.status_filter.blockSignals(True)
            self.status_filter.setCurrentIndex(0)
            self.status_filter.blockSignals(False)
        if store is None:
            self._checked_unassigned_ids.clear()
            self._members_by_id = {}
            self._player_main_names = {}
            self._player_character_counts = Counter()
            self._raid_info = {}
            self._player_order = []
            self._unknown_order = []
        else:
            self._index_store(store)
            player_ids = {player.playerId for player in store.players}
            if self._player_order is None:
                self._player_order = [player.playerId for player in sorted(
                    store.players, key=lambda player: (player.displayName.casefold(),
                                                       player.playerId))]
            else:
                self._player_order = [player_id for player_id in self._player_order
                                      if player_id in player_ids]
                self._player_order.extend(
                    player.playerId for player in store.players
                    if player.playerId not in self._player_order)
            unassigned = {member.memberId for member in store.members
                          if member.playerId is None}
            self._checked_unassigned_ids.intersection_update(unassigned)
            if self._unknown_current_member_id not in unassigned:
                self._unknown_current_member_id = None
            if self._unknown_order is None:
                self._unknown_order = [member.memberId for member in sorted(
                    (member for member in store.members if member.playerId is None),
                    key=lambda member: (member.name.casefold(), member.memberId))]
            else:
                self._unknown_order = [member_id for member_id in self._unknown_order
                                       if member_id in unassigned]
                self._unknown_order.extend(
                    member.memberId for member in store.members
                    if member.playerId is None and member.memberId not in self._unknown_order)
        self._refresh_master(preferred_player_id=preferred_player_id)

    def set_point_projection(self, projection, error: str | None = None) -> None:
        self.point_projection = projection
        self.point_error = error
        self._render_detail()

    def show_player_id(self, player_id: str) -> bool:
        if self.store is None or not any(
                player.playerId == player_id for player in self.store.players):
            return False
        blocked = self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(blocked)
        blocked = self.status_filter.blockSignals(True)
        self.status_filter.setCurrentIndex(0)
        self.status_filter.blockSignals(blocked)
        self._refresh_master(preferred_player_id=player_id)
        return self._current_player_id() == player_id

    def set_dkp_projection(self, projection) -> None:
        self.dkp_projection = projection
        self._render_detail()

    def set_active_point_system(self, mode: str) -> None:
        self.point_presentation = ActivePointPresentation(mode)
        self._render_detail()

    def _index_store(self, store: IdentityV2Store) -> None:
        self._members_by_id = {member.memberId: member for member in store.members}
        self._player_character_counts = Counter(
            member.playerId for member in store.members if member.playerId is not None)
        self._player_main_names = {
            player.playerId: self._members_by_id[player.mainMemberId].name
            if player.mainMemberId in self._members_by_id else None
            for player in store.players
        }
        raid_dates: dict[str, date] = {}
        for raid in store.raids:
            try:
                raid_dates[raid.raidId] = date.fromisoformat(raid.date)
            except (TypeError, ValueError):
                continue
        aggregate: dict[str, list] = {}
        for entry in store.attendance:
            record = aggregate.setdefault(entry.memberId, [0, None, None])
            record[0] += 1
            raid_date = raid_dates.get(entry.raidId)
            if raid_date is not None:
                record[1] = raid_date if record[1] is None else min(record[1], raid_date)
                record[2] = raid_date if record[2] is None else max(record[2], raid_date)
        self._raid_info = {
            member_id: (count, first_date, last_date)
            for member_id, (count, first_date, last_date) in aggregate.items()
        }

    def _player_width_changed(self, column: int, _old: int, new: int) -> None:
        if 0 <= column < len(self._player_column_widths):
            self._player_column_widths[column] = new

    def _unknown_width_changed(self, column: int, _old: int, new: int) -> None:
        if 0 <= column < len(self._unknown_column_widths):
            self._unknown_column_widths[column] = new

    def _splitter_moved(self, _position: int, _index: int) -> None:
        sizes = self.splitter.sizes()
        if len(sizes) == 2 and all(size > 0 for size in sizes):
            self._splitter_sizes = sizes

    def layout_settings(self) -> dict[str, list[int]]:
        player_widths = [self.player_table.columnWidth(index)
                         for index in range(self.player_table.columnCount())]
        unknown_widths = self._unknown_column_widths.copy()
        if self.unassigned_table is not None:
            unknown_widths = [self.unassigned_table.columnWidth(index)
                              for index in range(self.unassigned_table.columnCount())]
        sizes = self.splitter.sizes()
        if len(sizes) != 2 or not all(size > 0 for size in sizes):
            sizes = self._splitter_sizes
        return {
            PLAYER_COLUMN_WIDTHS_SETTING: player_widths,
            UNKNOWN_COLUMN_WIDTHS_SETTING: unknown_widths,
            PLAYER_SPLITTER_SIZES_SETTING: list(sizes),
            MAIN_HISTORY_COLUMN_WIDTHS_SETTING: self._main_history_column_widths.copy(),
        }

    def _matching_members(self, player: Player | None, query: str) -> tuple[Member, ...]:
        if self.store is None:
            return ()
        status = self.status_filter.currentData()
        player_matches = bool(player and query in player.displayName.casefold()) if query else False
        unknown_matches = player is None and query in tr(
            "identity_v2_players.unknown").casefold() if query else False
        members = []
        for member in self.store.members:
            if member.playerId != (player.playerId if player else None):
                continue
            grave = _is_graveyard(member)
            if status == "active" and (grave or member.lifeStatus != "active"):
                continue
            if status == "inactive" and (grave or member.lifeStatus != "inactive"):
                continue
            if status == "graveyard" and not grave:
                continue
            if query and not (player_matches or unknown_matches
                              or query in member.name.casefold()):
                continue
            members.append(member)
        return tuple(sorted(members, key=lambda item: (item.name.casefold(), item.memberId)))

    def _refresh_master(self, *_args, preferred_player_id: object = _KEEP) -> None:
        if preferred_player_id is _KEEP:
            preferred_player_id = self._current_player_id()
        scroll = self.player_table.verticalScrollBar().value()
        self.player_table.blockSignals(True)
        self._visible_members = {}
        visible_players: list[Player] = []
        self.player_table.setRowCount(0)
        if self.store is not None:
            query = self.search.text().strip().casefold()
            status = self.status_filter.currentData()
            unknown = self._matching_members(None, query)
            item = QTableWidgetItem(tr("identity_v2_players.unknown_count",
                                       count=len(unknown)))
            item.setData(Qt.ItemDataRole.UserRole, None)
            self.player_table.setRowCount(1)
            self.player_table.setItem(0, 0, item)
            self.player_table.setItem(0, 1, QTableWidgetItem("–"))
            unknown_count = QTableWidgetItem(str(len(unknown)))
            unknown_count.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                                           Qt.AlignmentFlag.AlignVCenter)
            unknown_count.setData(Qt.ItemDataRole.UserRole, len(unknown))
            self.player_table.setItem(0, 2, unknown_count)
            self._visible_members[None] = unknown
            ordered_ids = self._player_order or []
            visible_by_player_id: dict[str, tuple[Member, ...]] = {}
            for player_id in ordered_ids:
                player = next((item for item in self.store.players
                               if item.playerId == player_id), None)
                if player is None:
                    continue
                visible = self._matching_members(player, query)
                if status != "all" and not visible:
                    continue
                if query and query not in player.displayName.casefold() and not visible:
                    continue
                visible_players.append(player)
                visible_by_player_id[player.playerId] = visible
            self.player_table.setRowCount(1 + len(visible_players))
            for row, player in enumerate(visible_players, start=1):
                name = QTableWidgetItem(player.displayName)
                name.setData(Qt.ItemDataRole.UserRole, player.playerId)
                name.setToolTip(f"{player.displayName}\n{player.playerId}")
                main_name = self._player_main_names.get(player.playerId)
                main = QTableWidgetItem(main_name or "–")
                main.setToolTip(main_name or tr("identity_v2_players.no_main"))
                count = self._player_character_counts.get(player.playerId, 0)
                chars = QTableWidgetItem(str(count))
                chars.setData(Qt.ItemDataRole.UserRole, count)
                chars.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                                       Qt.AlignmentFlag.AlignVCenter)
                self.player_table.setItem(row, 0, name)
                self.player_table.setItem(row, 1, main)
                self.player_table.setItem(row, 2, chars)
                self._visible_members[player.playerId] = visible_by_player_id.get(
                    player.playerId, ())
        row = 0 if self.player_table.rowCount() else -1
        if preferred_player_id is not _KEEP:
            row = next((index for index in range(self.player_table.rowCount())
                        if self.player_table.item(index, 0).data(Qt.ItemDataRole.UserRole)
                        == preferred_player_id), -1)
            if row < 0 and self.player_table.rowCount():
                row = 0
        self.player_table.blockSignals(False)
        if row >= 0:
            self.player_table.setCurrentCell(row, 0)
        self._render_detail()
        self.player_table.verticalScrollBar().setValue(scroll)

    def _current_player_id(self) -> str | None | object:
        row = self.player_table.currentRow()
        item = self.player_table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else _KEEP

    def _sort_players(self, column: int) -> None:
        if self.store is None or column not in (0, 1, 2):
            return
        descending = self._player_sort == (column, False)
        self._player_sort = (column, descending)
        by_id = {player.playerId: player for player in self.store.players}

        def sort_key(player_id: str):
            player = by_id[player_id]
            if column == 0:
                value = player.displayName.casefold()
                return (0, value, player_id)
            if column == 1:
                main_name = self._player_main_names.get(player_id)
                return (main_name is None, (main_name or "").casefold(), player_id)
            return (self._player_character_counts.get(player_id, 0), player_id)

        self._player_order = sorted(self._player_order or by_id, key=sort_key,
                                    reverse=descending)
        self._refresh_master(preferred_player_id=self._current_player_id())

    def _clear_detail(self) -> None:
        self._clear_layout(self.detail_layout)
        self.group_rows = {}
        self.member_rows = {}
        self.unassigned_table = None

    @classmethod
    def _clear_layout(cls, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child is not None:
                cls._clear_layout(child)
                child.deleteLater()

    def _render_detail(self, *_args) -> None:
        self._clear_detail()
        if self.store is None:
            self.detail_layout.addWidget(QLabel(tr("identity_v2_players.no_players")))
            return
        player_id = self._current_player_id()
        if player_id is _KEEP:
            self.detail_layout.addWidget(QLabel(
                tr("identity_v2_players.graveyard_empty")
                if self.status_filter.currentData() == "graveyard"
                else tr("identity_v2_players.no_matches")))
            return
        if player_id is None:
            self._render_unknown(self._visible_members.get(None, ()))
        else:
            player = next(item for item in self.store.players if item.playerId == player_id)
            self._render_player(player, self._visible_members.get(player_id, ()))
            self.detail_layout.addStretch(1)

    def _render_unknown(self, members: tuple[Member, ...]) -> None:
        self.detail_layout.addWidget(QLabel(tr("identity_v2_players.unknown")))
        if not self.store.players:
            self.detail_layout.addWidget(QLabel(tr("identity_v2_players.no_players")))
        toolbar = QVBoxLayout()
        single_actions = QHBoxLayout()
        self.create_button = QPushButton(tr("identity_v2_players.create_player_short"))
        self.assign_button = QPushButton(tr("identity_v2_players.assign_existing"))
        self.bulk_create_button = QPushButton(tr("identity_v2_players.bulk_create_short"))
        self.selection_count_label = QLabel("")
        single_actions.addWidget(self.create_button)
        single_actions.addWidget(self.assign_button)
        single_actions.addWidget(self.bulk_create_button)
        single_actions.addStretch(1)
        single_actions.addWidget(self.selection_count_label)
        bulk_actions = QHBoxLayout()
        self.bulk_active_button = QPushButton(tr("identity_v2_players.bulk_active"))
        self.bulk_inactive_button = QPushButton(tr("identity_v2_players.bulk_inactive"))
        self.select_all_button = QPushButton(tr("identity_v2_players.select_all"))
        self.clear_selection_button = QPushButton(
            tr("identity_v2_players.clear_selection"))
        for button in (self.bulk_active_button, self.bulk_inactive_button,
                       self.select_all_button, self.clear_selection_button):
            bulk_actions.addWidget(button)
        bulk_actions.addStretch(1)
        toolbar.addLayout(single_actions)
        toolbar.addLayout(bulk_actions)
        self.bulk_active_button.hide()
        self.bulk_inactive_button.hide()
        self.detail_layout.addLayout(toolbar)

        self.unassigned_table = _CheckboxCharacterTable(0, 7)
        self.unknown_row_hover = install_row_hover(self.unassigned_table)
        self.unassigned_table.setHorizontalHeaderLabels((
            "", tr("identity_v2_players.character"),
            tr("identity_v2_players.class"), tr("identity_v2_players.status"),
            tr("identity_v2_players.raids"),
            tr("identity_v2_players.first_raid"),
            tr("identity_v2_players.last_raid"),
        ))
        self.unassigned_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.unassigned_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.unassigned_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.unassigned_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.unassigned_table.setSortingEnabled(False)
        self.unassigned_table.setAlternatingRowColors(True)
        self.unassigned_table.verticalHeader().setVisible(False)
        self.unassigned_table.horizontalHeader().setSectionsClickable(True)
        self.unassigned_table.horizontalHeader().setStretchLastSection(False)
        self.unassigned_table.horizontalHeader().setMinimumSectionSize(32)
        for index in range(self.unassigned_table.columnCount()):
            self.unassigned_table.horizontalHeader().setSectionResizeMode(
                index, QHeaderView.ResizeMode.Interactive)
        self.unassigned_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        for index, width in enumerate(self._unknown_column_widths):
            self.unassigned_table.setColumnWidth(index, width)
        self.unassigned_table.horizontalHeader().sectionClicked.connect(
            self._sort_unknown)
        self.unassigned_table.horizontalHeader().sectionResized.connect(
            self._unknown_width_changed)
        self.unassigned_table.itemChanged.connect(self._unknown_item_changed)
        self.unassigned_table.currentCellChanged.connect(
            self._unknown_current_changed)
        self.unassigned_table.itemSelectionChanged.connect(
            self._update_unknown_actions)
        self.create_button.clicked.connect(self._create_player)
        self.assign_button.clicked.connect(self._assign_selected)
        self.bulk_create_button.clicked.connect(self._create_many_players)
        self.select_all_button.clicked.connect(self._select_all_visible)
        self.clear_selection_button.clicked.connect(self._clear_visible_selection)
        self.empty_unknown_label = QLabel("")
        self.detail_layout.addWidget(self.unassigned_table, 1)
        self.detail_layout.addWidget(self.empty_unknown_label)
        self._populate_unknown_table(members)
        if self._unknown_current_member_id:
            self._select_unknown_row(self._unknown_current_member_id)
        if self.unassigned_table.currentRow() < 0 and members:
            self._select_unknown_row(members[0].memberId)
        self._update_unknown_actions()

    def _populate_unknown_table(self, members: tuple[Member, ...]) -> None:
        table = self.unassigned_table
        if table is None:
            return
        selected_member_id = self._single_unknown_id() or self._unknown_current_member_id
        order = {member_id: index for index, member_id in
                 enumerate(self._unknown_order or ())}
        members = tuple(sorted(members, key=lambda member: (
            order.get(member.memberId, len(order)), member.name.casefold(),
            member.memberId,
        )))
        table.blockSignals(True)
        table.setRowCount(len(members))
        for row, member in enumerate(members):
            checkbox = QTableWidgetItem("")
            checkbox.setFlags((checkbox.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                              & ~Qt.ItemFlag.ItemIsEditable)
            checkbox.setCheckState(
                Qt.CheckState.Checked if member.memberId in self._checked_unassigned_ids
                else Qt.CheckState.Unchecked)
            checkbox.setData(Qt.ItemDataRole.UserRole, member.memberId)
            name = QTableWidgetItem(member.name)
            name.setData(Qt.ItemDataRole.UserRole, member.memberId)
            name.setToolTip(member.memberId)
            class_name = QTableWidgetItem(
                member.className or tr("identity_v2_players.table_unknown_class"))
            status = QTableWidgetItem(_member_status(member))
            raids, first_date, last_date = self._raid_info.get(
                member.memberId, (0, None, None))
            raid_count = QTableWidgetItem(str(raids))
            raid_count.setData(Qt.ItemDataRole.UserRole, raids)
            raid_count.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                                        Qt.AlignmentFlag.AlignVCenter)
            first_raid = QTableWidgetItem(_format_date(first_date))
            first_raid.setData(Qt.ItemDataRole.UserRole, first_date)
            last_raid = QTableWidgetItem(_format_date(last_date))
            last_raid.setData(Qt.ItemDataRole.UserRole, last_date)
            for column, item in ((0, checkbox), (1, name), (2, class_name),
                                 (3, status), (4, raid_count), (5, first_raid),
                                 (6, last_raid)):
                table.setItem(row, column, item)
        table.blockSignals(False)
        if selected_member_id is not None:
            self._select_unknown_row(selected_member_id)
        self.empty_unknown_label.setText(
            tr("identity_v2_players.graveyard_empty")
            if self.status_filter.currentData() == "graveyard"
            else tr("identity_v2_players.unknown_empty"))
        self.empty_unknown_label.setVisible(not members)

    def _select_unknown_row(self, member_id: str) -> bool:
        table = self.unassigned_table
        if table is None:
            return False
        for row in range(table.rowCount()):
            item = table.item(row, 1)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == member_id:
                table.setCurrentCell(row, 1)
                return True
        return False

    def _unknown_current_changed(self, row: int, column: int, *_args) -> None:
        if self.unassigned_table is None or row < 0:
            self._unknown_current_member_id = None
        else:
            item = self.unassigned_table.item(row, 1)
            self._unknown_current_member_id = (
                item.data(Qt.ItemDataRole.UserRole) if item is not None else None)
        self._update_unknown_actions()

    def _unknown_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        member_id = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self._checked_unassigned_ids.add(member_id)
        else:
            self._checked_unassigned_ids.discard(member_id)
        self._update_unknown_actions()

    def _sort_unknown(self, column: int) -> None:
        if column == 0:
            return
        descending = self._unknown_sort == (column, False)
        self._unknown_sort = (column, descending)
        self._unknown_current_member_id = self._single_unknown_id()
        if self.store is None:
            return

        def sort_key(member: Member):
            raid_count, first_date, last_date = self._raid_info.get(
                member.memberId, (0, None, None))
            if column == 1:
                return member.name.casefold(), member.memberId
            if column == 2:
                return (member.className or tr(
                    "identity_v2_players.table_unknown_class")).casefold(), member.memberId
            if column == 3:
                status_order = (2 if _is_graveyard(member) else
                                1 if member.lifeStatus == "inactive" else 0)
                return status_order, member.memberId
            if column == 4:
                return raid_count, member.memberId
            if column == 5:
                return first_date is None, first_date or date.max, member.memberId
            return last_date is None, last_date or date.max, member.memberId

        all_unassigned = {member.memberId: member for member in self.store.members
                          if member.playerId is None}
        visible_ids = {member.memberId for member in self._visible_members.get(None, ())}
        sorted_visible = sorted(
            (member for member_id, member in all_unassigned.items()
             if member_id in visible_ids),
            key=sort_key, reverse=descending,
        )
        hidden_ids = [member_id for member_id in self._unknown_order or ()
                      if member_id not in visible_ids and member_id in all_unassigned]
        self._unknown_order = [member.memberId for member in sorted_visible] + hidden_ids
        self._populate_unknown_table(self._visible_members.get(None, ()))
        if self._unknown_current_member_id:
            self._select_unknown_row(self._unknown_current_member_id)

    def _visible_unknown_ids(self) -> tuple[str, ...]:
        if self.unassigned_table is None:
            return ()
        return tuple(self.unassigned_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                     for row in range(self.unassigned_table.rowCount()))

    def _select_all_visible(self) -> None:
        self._checked_unassigned_ids.update(self._visible_unknown_ids())
        self._populate_unknown_table(self._visible_members.get(None, ()))
        if self._unknown_current_member_id:
            self._select_unknown_row(self._unknown_current_member_id)
        self._update_unknown_actions()

    def _clear_visible_selection(self) -> None:
        self._checked_unassigned_ids.clear()
        self._populate_unknown_table(self._visible_members.get(None, ()))
        if self._unknown_current_member_id:
            self._select_unknown_row(self._unknown_current_member_id)
        self._update_unknown_actions()

    def _selected_unknown_ids(self) -> tuple[str, ...]:
        if self.store is None:
            return ()
        return tuple(member.memberId for member in self.store.members
                     if member.memberId in self._checked_unassigned_ids
                     and member.playerId is None)

    def _single_unknown_id(self) -> str | None:
        if self.unassigned_table is None:
            return None
        row = self.unassigned_table.currentRow()
        item = self.unassigned_table.item(row, 1) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _unknown_action_ids(self) -> tuple[str, ...]:
        checked = self._selected_unknown_ids()
        if checked:
            return checked
        current = self._single_unknown_id()
        return (current,) if current is not None else ()

    def _update_unknown_actions(self) -> None:
        if self.store is None or self.unassigned_table is None:
            return
        selected = self._selected_unknown_ids()
        action_ids = self._unknown_action_ids()
        multi_count = len(selected)
        by_id = {member.memberId: member for member in self.store.members}
        all_living = bool(action_ids) and all(
            item in by_id and not _is_graveyard(by_id[item]) for item in action_ids)
        all_active = all_living and all(
            by_id[item].lifeStatus == "active" for item in action_ids)
        self.create_button.setVisible(multi_count < 2)
        self.bulk_create_button.setVisible(multi_count >= 2)
        self.create_button.setEnabled(all_active)
        self.assign_button.setEnabled(bool(action_ids) and bool(self.store.players))
        self.bulk_active_button.setEnabled(False)
        self.bulk_inactive_button.setEnabled(False)
        self.bulk_active_button.hide()
        self.bulk_inactive_button.hide()
        self.bulk_create_button.setEnabled(all_active and multi_count >= 2)
        for button, key in (
            (self.assign_button, "assign_existing"),
            (self.bulk_create_button, "bulk_create_short"),
            (self.bulk_active_button, "bulk_active"),
            (self.bulk_inactive_button, "bulk_inactive"),
        ):
            button.setText(f"{tr(f'identity_v2_players.{key}')} ({multi_count})"
                           if multi_count >= 2 else tr(f"identity_v2_players.{key}"))
            selected_style = multi_count >= 2
            if button.property("multiSelected") != selected_style:
                button.setProperty("multiSelected", selected_style)
                button.style().unpolish(button)
                button.style().polish(button)
        self.select_all_button.setEnabled(bool(self._visible_unknown_ids()))
        self.clear_selection_button.setEnabled(bool(self._checked_unassigned_ids))
        self.selection_count_label.setText(tr(
            "identity_v2_players.selected_count", count=len(self._checked_unassigned_ids)))

    def _render_player(self, player: Player, members: tuple[Member, ...]) -> None:
        header = QHBoxLayout()
        header.addWidget(QLabel(player.displayName))
        is_active = self.store.player_is_active(player.playerId)
        header.addWidget(QLabel(tr("identity_v2_players.player_active")
                                if is_active
                                else tr("identity_v2_players.player_inactive")))
        header.addStretch(1)
        profile_button = QPushButton(tr("player_profile.open_profile"))
        profile_button.setObjectName("openPlayerProfileButton")
        profile_button.clicked.connect(
            lambda: self.profileRequested.emit(player.playerId))
        header.addWidget(profile_button)
        activity_button = QPushButton(tr(
            "identity_v2_players.deactivate_player" if is_active
            else "identity_v2_players.reactivate_player"))
        activity_button.setObjectName("playerActivityButton")
        activity_button.clicked.connect(
            lambda: self._change_player_activity(
                player.playerId, "inactive" if is_active else "active"))
        header.addWidget(activity_button)
        rename = QPushButton(tr("identity_v2_players.rename"))
        rename.clicked.connect(lambda: self._rename_player(player.playerId))
        header.addWidget(rename)
        history_button = QPushButton(tr("identity_v2_main_history.title_short"))
        history_button.setObjectName("mainHistoryButton")
        history_button.clicked.connect(
            lambda: self._open_main_history(player.playerId))
        header.addWidget(history_button)
        menu_button = QToolButton()
        menu_button.setText(tr("identity_v2_players.more"))
        menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(menu_button)
        if player.mainMemberId is not None:
            menu.addAction(tr("identity_v2_players.clear_main"),
                           lambda: self._run(lambda store: clear_main(store, player.playerId)))
        delete_action = menu.addAction(tr("identity_v2_players.delete_player"),
                                       lambda: self._delete_player(player.playerId))
        delete_action.setEnabled(not any(item.playerId == player.playerId
                                         for item in self.store.members))
        menu_button.setMenu(menu)
        header.addWidget(menu_button)
        self.detail_layout.addLayout(header)
        points_form = QFormLayout()
        points_form.setContentsMargins(0, 0, 0, 0)
        points_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        points = QLabel(str(self.point_projection.player_points(player.playerId))
                        if self.point_projection is not None else "–")
        points.setObjectName("v2PlayerRaidPoints")
        points.setMinimumWidth(45)
        points.setStyleSheet("color:#f5dfb1;font-weight:600;")
        points.setToolTip(self.point_error or "")
        points_form.addRow(tr("raid_points.player_total"), points)
        points_form.setRowVisible(points, self.point_presentation.shows("raid_points"))
        eternal = QLabel(str(self.point_projection.eternal_player_points(player.playerId))
                         if self.point_projection is not None else "–")
        eternal.setObjectName("v2PlayerEternalPoints")
        eternal.setMinimumWidth(45)
        eternal.setStyleSheet("color:#f5dfb1;font-weight:600;")
        eternal.setToolTip(self.point_error or "")
        points_form.addRow(tr("identity_v2_raid_points.eternal_player"), eternal)
        points_form.setRowVisible(
            eternal, self.point_presentation.shows("eternal_raid_points"))
        available_value = (self.dkp_projection.available_for_member(player.mainMemberId)
                           if self.dkp_projection is not None and player.mainMemberId
                           else None)
        available_dkp = QLabel(f"{available_value:g}" if available_value is not None
                               else "–")
        available_dkp.setObjectName("v2PlayerAvailableDkp")
        points_form.addRow(tr("raid_clm_admin.current_dkp"), available_dkp)
        points_form.setRowVisible(
            available_dkp, self.point_presentation.shows("available_dkp"))
        dkp_eternal = QLabel(
            f"{self.dkp_projection.eternal_for_player(player.playerId):g}"
            if self.dkp_projection is not None else "–")
        dkp_eternal.setObjectName("v2PlayerEternalDkp")
        points_form.addRow(tr("identity_v2_views.eternal_dkp"), dkp_eternal)
        points_form.setRowVisible(
            dkp_eternal, self.point_presentation.shows("eternal_dkp"))
        dkp_rank = self.dkp_projection.dkp_rank_for_player(player.playerId) \
            if self.dkp_projection is not None else None
        dkp_rank_label = QLabel(dkp_rank.replace("_", " ") if dkp_rank else "–")
        dkp_rank_label.setObjectName("v2PlayerDkpRank")
        points_form.addRow(tr("identity_v2_views.dkp_rank"), dkp_rank_label)
        points_form.setRowVisible(
            dkp_rank_label, self.point_presentation.shows("dkp_rank"))
        raid_rank = self.dkp_projection.raid_rank_for_player(player.playerId) \
            if self.dkp_projection is not None else None
        raid_rank_label = QLabel(raid_rank.replace("_", " ") if raid_rank else "–")
        raid_rank_label.setObjectName("v2PlayerRaidRank")
        points_form.addRow(tr("identity_v2_views.raid_rank"), raid_rank_label)
        points_form.setRowVisible(
            raid_rank_label, self.point_presentation.shows("raid_rank"))
        self.detail_layout.addLayout(points_form)
        points_history = QPushButton(tr("raid_points.player_history"))
        points_history.setObjectName("v2PlayerPointHistoryButton")
        points_history.setEnabled(self.point_projection is not None)
        points_history.setVisible(
            self.point_presentation.shows("raid_point_history"))
        points_history.clicked.connect(
            lambda: self.pointHistoryRequested.emit(player.playerId))
        self.detail_layout.addWidget(points_history, alignment=Qt.AlignmentFlag.AlignLeft)
        main = next((member for member in self.store.members
                     if member.memberId == player.mainMemberId), None)
        self.detail_layout.addWidget(QLabel(
            tr("identity_v2_players.main_label", name=main.name)
            if main else tr("identity_v2_players.no_main")))

        groups: dict[str, list[Member]] = {
            "main": [], "active": [], "inactive": [], "graveyard": [],
        }
        for member in members:
            if _is_graveyard(member):
                groups["graveyard"].append(member)
            elif member.memberId == player.mainMemberId:
                groups["main"].append(member)
            elif member.lifeStatus == "inactive":
                groups["inactive"].append(member)
            else:
                groups["active"].append(member)
        self.group_rows = {key: tuple(item.memberId for item in group)
                           for key, group in groups.items()}
        active_label = "twinks" if main else "active_characters"
        for key, label_key in (("main", "main"), ("active", active_label),
                               ("inactive", "inactive"), ("graveyard", "graveyard")):
            if not groups[key]:
                continue
            group_box = QGroupBox(tr(f"identity_v2_players.{label_key}"))
            group_layout = QVBoxLayout(group_box)
            for member in groups[key]:
                group_layout.addWidget(self._member_row(member, player))
            self.detail_layout.addWidget(group_box)
        if not members:
            self.detail_layout.addWidget(QLabel(
                tr("identity_v2_players.graveyard_empty")
                if self.status_filter.currentData() == "graveyard"
                else tr("identity_v2_players.no_matches")))

    def _member_row(self, member: Member, player: Player) -> QWidget:
        row = QFrame()
        row.setObjectName("characterRow")
        row.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        layout = QHBoxLayout(row)
        label = QLabel(f"{member.name} · "
                       f"{member.className or tr('identity_v2_players.unknown_class')}"
                       f" · {_member_status(member)}")
        role = (tr("identity_v2_views.role_main")
                if player.mainMemberId == member.memberId
                else tr("identity_v2_views.role_twink")
                if member.lifeStatus != "dead" else _member_status(member))
        status = _member_status(member)
        label.setToolTip(f"{role} · {status}" if role != status else status)
        layout.addWidget(label, 1)
        if not _is_graveyard(member) and member.lifeStatus == "active" \
                and player.mainMemberId != member.memberId:
            main_button = QPushButton(tr("identity_v2_players.set_main"))
            main_button.clicked.connect(
                lambda: self._run(lambda store: set_main(store, player.playerId,
                                                           member.memberId)))
            layout.addWidget(main_button)
        menu_button = QToolButton()
        menu_button.setText(tr("identity_v2_players.more"))
        menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(menu_button)
        menu.addAction(tr("identity_v2_players.reassign"),
                       lambda: self._reassign_member(member.memberId))
        menu.addAction(tr("identity_v2_players.unassign"),
                       lambda: self._unassign_member(member.memberId))
        menu_button.setMenu(menu)
        layout.addWidget(menu_button)
        self.member_rows[member.memberId] = row
        return row

    def _choose_player(self, *, exclude: str | None = None) -> str | None:
        if self.store is None:
            return None
        players = sorted((item for item in self.store.players if item.playerId != exclude),
                         key=lambda item: (item.displayName.casefold(), item.playerId))
        if not players:
            QMessageBox.information(self, tr("identity_v2_players.title"),
                                    tr("identity_v2_players.no_players"))
            return None
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("identity_v2_players.select_player"))
        layout = QVBoxLayout(dialog)
        choices = QListWidget()
        for player in players:
            main = next((member.name for member in self.store.members
                         if member.memberId == player.mainMemberId), None)
            label = (tr("identity_v2_players.main_label", name=main)
                     if main else tr("identity_v2_players.no_main"))
            item = QListWidgetItem(f"{player.displayName} · {label}")
            item.setData(Qt.ItemDataRole.UserRole, player.playerId)
            item.setToolTip(player.playerId)
            choices.addItem(item)
        choices.setCurrentRow(0)
        choices.itemDoubleClicked.connect(lambda _item: dialog.accept())
        layout.addWidget(choices)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        item = choices.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _confirm(self, message: str) -> bool:
        return QMessageBox.question(
            self, tr("identity_v2_players.title"), message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def _run(
        self, operation: Callable[[IdentityV2Store], IdentityV2Store],
        *, select_player: object = _KEEP,
    ) -> bool:
        if self.store is None:
            return False
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                result = operation(self.store)
            finally:
                QApplication.restoreOverrideCursor()
        except Exception as exc:
            QMessageBox.warning(self, tr("identity_v2_players.title"), str(exc))
            return False
        if result is self.store:
            return False
        self.set_store(result, preferred_player_id=select_player)
        self.storeChanged.emit(result)
        return True

    def _create_player(self) -> None:
        ids = self._unknown_action_ids()
        if not ids or self.store is None:
            return
        if len(ids) > 1:
            self._create_many_players()
            return
        member_id = ids[0]
        def create(store: IdentityV2Store) -> IdentityV2Store:
            result = create_player_from_member(store, member_id)
            self._created_player_id = next(member.playerId for member in result.members
                                           if member.memberId == member_id)
            return result
        self._created_player_id = None
        if self._run(create, select_player=_KEEP) and self._created_player_id:
            self._refresh_master(preferred_player_id=self._created_player_id)

    def _assign_selected(self) -> None:
        ids = self._unknown_action_ids()
        if not ids:
            return
        player_id = self._choose_player()
        if player_id is None:
            return
        if len(ids) > 1:
            if not self._confirm(tr("identity_v2_players.confirm_bulk_assign",
                                    count=len(ids))):
                return
            self._run(lambda store: bulk_assign_members(store, ids, player_id),
                      select_player=player_id)
        else:
            self._run(lambda store: assign_member(store, ids[0], player_id),
                      select_player=player_id)

    def _create_many_players(self) -> None:
        ids = self._unknown_action_ids()
        if not ids or self.store is None:
            return
        by_id = {item.memberId: item for item in self.store.members}
        if any(item not in by_id or by_id[item].playerId is not None
               or by_id[item].lifeStatus != "active" or _is_graveyard(by_id[item])
               for item in ids):
            QMessageBox.warning(self, tr("identity_v2_players.title"),
                                tr("identity_v2_players.invalid_bulk_create"))
            return
        if not self._confirm(tr("identity_v2_players.confirm_bulk_create",
                                count=len(ids))):
            return
        self._run(lambda store: bulk_create_players_from_members(store, ids))

    def _change_player_activity(self, player_id: str, status: str) -> None:
        if self.store is None:
            return
        player = self.store.get_player(player_id)
        if player is None:
            return
        key = ("identity_v2_players.confirm_deactivate_player"
               if status == "inactive" else
               "identity_v2_players.confirm_reactivate_player")
        if not self._confirm(tr(key, name=player.displayName)):
            return
        self._run(lambda store: set_player_activity(store, player_id, status),
                  select_player=player_id)

    def _rename_player(self, player_id: str) -> None:
        if self.store is None:
            return
        player = next(item for item in self.store.players if item.playerId == player_id)
        name, accepted = QInputDialog.getText(
            self, tr("identity_v2_players.rename"),
            tr("identity_v2_players.player_name"), text=player.displayName,
        )
        if accepted and name != player.displayName:
            self._run(lambda store: rename_player(store, player_id, name))

    def _delete_player(self, player_id: str) -> None:
        if self.store is None:
            return
        player = next(item for item in self.store.players if item.playerId == player_id)
        if not self._confirm(tr("identity_v2_players.confirm_delete",
                                name=player.displayName)):
            return
        self._run(lambda store: delete_player(store, player_id), select_player=None)

    def _open_main_history(self, player_id: str) -> bool:
        if self.store is None or not any(
                item.playerId == player_id for item in self.store.players):
            return False
        dialog = MainHistoryDialog(
            self.store, player_id, lambda: self.store,
            self._main_history_column_widths, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self._main_history_column_widths = dialog.column_widths()
        if not accepted or dialog.result_store is None:
            return False
        if (self.store is not dialog.source_store
                or self.store.to_payload() != dialog.source_payload):
            QMessageBox.warning(
                self, tr("identity_v2_main_history.title_short"),
                tr("identity_v2_main_history.stale_project"))
            return False
        if dialog.result_store.to_payload() == self.store.to_payload():
            return False
        return self._run(lambda _store: dialog.result_store,
                         select_player=player_id)

    def _history_blocks_ownership_change(self, member: Member) -> bool:
        if self.store is None or member.playerId is None:
            return False
        player = next(item for item in self.store.players
                      if item.playerId == member.playerId)
        entries = [item for item in player.mainHistory
                   if item.memberId == member.memberId]
        if not entries:
            return False
        def boundary(value: str | None) -> str:
            return (_format_date(date.fromisoformat(value)) if value
                    else tr("identity_v2_main_history.unknown"))
        periods = "; ".join(
            f"{item.historyId}: {boundary(item.fromDate)}–{boundary(item.toDate)}"
            for item in entries)
        QMessageBox.warning(
            self, tr("identity_v2_main_history.title_short"),
            tr("identity_v2_main_history.ownership_blocked",
               character=member.name, count=len(entries), entries=periods))
        self._refresh_master(preferred_player_id=player.playerId)
        return True

    def _reassign_member(self, member_id: str) -> None:
        if self.store is None:
            return
        member = next(item for item in self.store.members if item.memberId == member_id)
        if self._history_blocks_ownership_change(member):
            return
        player_id = self._choose_player(exclude=member.playerId)
        if player_id is None:
            return
        player = next(item for item in self.store.players if item.playerId == player_id)
        if not self._confirm(tr("identity_v2_players.confirm_reassign",
                                character=member.name, player=player.displayName)):
            return
        self._run(lambda store: reassign_member(store, member_id, player_id),
                  select_player=player_id)

    def _unassign_member(self, member_id: str) -> None:
        if self.store is None:
            return
        member = next(item for item in self.store.members if item.memberId == member_id)
        if self._history_blocks_ownership_change(member):
            return
        if not self._confirm(tr("identity_v2_players.confirm_unassign",
                                character=member.name)):
            return
        self._run(lambda store: unassign_member(store, member_id), select_player=None)
