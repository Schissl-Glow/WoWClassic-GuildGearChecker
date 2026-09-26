"""Read-only Qt tables for Identity V2 roster and raids."""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, QUrl, QSize
from PySide6.QtGui import QDesktopServices, QIcon, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .i18n import tr
from .GuildGearChecker import (CLASS_COLORS, character_type_display,
                               class_icon_path, gear_status_display,
                               raid_role_display, raid_status_display)
from .identity_v2_views import IdentityV2ViewData, V2AttendanceRow, V2RaidRow, V2RosterRow
from .qt_row_hover import install_row_hover


def _table(headers: tuple[str, ...]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.row_hover = install_row_hover(table)
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setSortingEnabled(False)
    table.horizontalHeader().setSectionsClickable(True)
    table.horizontalHeader().setStretchLastSection(True)
    table.setAlternatingRowColors(True)
    return table


def _set_rows(table: QTableWidget, values: list[tuple[str, ...]], ids: list[str]) -> None:
    selected = None
    current = table.currentRow()
    if current >= 0 and table.item(current, 0) is not None:
        selected = table.item(current, 0).data(Qt.ItemDataRole.UserRole)
    scroll = table.verticalScrollBar().value()
    table.blockSignals(True)
    try:
        table.setRowCount(len(values))
        selected_row = -1
        for row_index, (cells, record_id) in enumerate(zip(values, ids)):
            for column, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, record_id)
                table.setItem(row_index, column, item)
            if record_id == selected:
                selected_row = row_index
        if selected_row >= 0:
            table.selectRow(selected_row)
        else:
            table.clearSelection()
            table.setCurrentCell(-1, -1)
        table.verticalScrollBar().setValue(scroll)
    finally:
        table.blockSignals(False)


def _is_http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value.strip())
        return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.hostname)
    except ValueError:
        return False


class IdentityV2RosterPage(QWidget):
    HEADERS = (
        "character", "class", "rank", "role", "character_type", "gear_status",
        "raid_status", "raid_count", "raid_days", "available_dkp",
        "eternal_dkp_character", "eternal_dkp_player", "raid_points",
        "eternal_raid_points", "player_raid_points", "armory",
    )

    def __init__(self, *, embedded: bool = False):
        super().__init__()
        from .identity_v2_point_presentation import (
            ActivePointPresentation, POINT_MODE_RAID,
        )

        self._point_presentation = ActivePointPresentation(POINT_MODE_RAID)
        self._embedded = embedded
        self._rows: list[V2RosterRow] = []
        self._sort: tuple[int, bool] | None = None
        self._dkp_projection = None
        layout = QVBoxLayout(self)
        title = QLabel(tr("identity_v2_views.roster_title"))
        layout.addWidget(title)
        filter_host = QWidget()
        filters = QHBoxLayout(filter_host)
        filters.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("identity_v2_views.roster_search"))
        self.search.textChanged.connect(self._populate)
        filters.addWidget(self.search)
        self.class_filter = QComboBox()
        self.class_filter.currentIndexChanged.connect(self._populate)
        filters.addWidget(self.class_filter)
        layout.addWidget(filter_host)
        self.table = _table(tuple(tr(f"identity_v2_views.{key}") for key in self.HEADERS))
        self.table.horizontalHeader().sectionClicked.connect(self._sort_by_column)
        self.table.cellClicked.connect(self._cell_clicked)
        self.table.setIconSize(QSize(20, 20))
        layout.addWidget(self.table)
        if embedded:
            title.hide()
            filter_host.hide()
        self.set_active_point_system(self._point_presentation.mode)

    def set_active_point_system(self, mode: str) -> None:
        from .identity_v2_point_presentation import ActivePointPresentation

        self._point_presentation = ActivePointPresentation(mode)
        if (self._sort is not None
                and not self._point_presentation.shows(self.HEADERS[self._sort[0]])):
            self._sort = None
        for column, key in enumerate(self.HEADERS):
            self.table.setColumnHidden(column, not self._point_presentation.shows(key))
        self._populate()

    def set_view_data(self, data: IdentityV2ViewData) -> None:
        self._rows = list(data.roster)
        self._sort = None
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.class_filter.blockSignals(True)
        self.class_filter.clear()
        self.class_filter.addItem(tr("identity_v2_views.all_classes"), "")
        self.class_filter.addItem(tr("identity_v2_views.unknown_class"), "__unknown__")
        for name in sorted({row.class_name for row in self._rows if row.class_name},
                           key=str.casefold):
            self.class_filter.addItem(name, name)
        self.class_filter.blockSignals(False)
        self._populate()

    def set_dkp_projection(self, projection) -> None:
        self._dkp_projection = projection
        self._populate()

    def set_roster_items(self, items) -> None:
        """Show one already-filtered V2 projection in the shared roster list."""
        self._rows = list(items)
        if self._sort is not None:
            column, descending = self._sort
            self._rows.sort(key=lambda row: row.member_id)
            self._rows.sort(key=lambda row: self._sort_key(column, row),
                            reverse=descending)
        self._populate()

    def select_member(self, member_id: str | None) -> None:
        if member_id is None:
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
            return
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == member_id:
                self.table.selectRow(row)
                return

    def selected_member_id(self) -> str | None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _sort_by_column(self, column: int) -> None:
        descending = self._sort == (column, False)
        self._rows.sort(key=lambda row: row.member_id)
        self._rows.sort(key=lambda row: self._sort_key(column, row),
                        reverse=descending)
        self._sort = (column, descending)
        self._populate()

    def _sort_key(self, column: int, row):
        keys = (
            lambda row: row.name.casefold(), lambda row: (row.class_name or "").casefold(),
            lambda row: (row.eternal_dkp if self._point_presentation.shows("dkp_rank")
                         else getattr(row, "eternalRaidPoints", None) or 0),
            lambda row: getattr(row, "raidRole", "").casefold(),
            lambda row: getattr(row, "role", "").casefold(),
            lambda row: getattr(row, "gearStatus", "").casefold(),
            lambda row: getattr(row, "raidStatus", "").casefold(),
            lambda row: getattr(row, "matrixRaidCount", row.raid_count),
            lambda row: getattr(row, "raidDays", 0),
            lambda row: _sort_optional(self._point_value(row, "availableDkp")),
            lambda row: row.eternal_dkp,
            lambda row: _sort_optional(getattr(row, "playerEternalDkp", None)),
            lambda row: _sort_optional(self._point_value(row, "raidPoints")),
            lambda row: _sort_optional(self._point_value(row, "eternalRaidPoints")),
            lambda row: _sort_optional(getattr(row, "playerRaidPoints", None)),
            lambda row: (getattr(row, "armoryUrl", None) or "").casefold(),
        )
        return keys[column](row)

    def _point_value(self, row, field):
        if hasattr(row, field):
            return getattr(row, field)
        if self._dkp_projection is None:
            return None
        method = {
            "availableDkp": self._dkp_projection.available_for_member,
            "raidPoints": self._dkp_projection.raid_points_for_member,
            "eternalRaidPoints": self._dkp_projection.eternal_raid_points_for_member,
        }[field]
        return method(row.member_id)

    def _active_rank(self, row):
        if hasattr(row, "dkpRank"):
            return self._point_presentation.rank(row.dkpRank, row.raidRank)
        if self._dkp_projection is None:
            return None
        return self._point_presentation.rank(
            self._dkp_projection.dkp_rank_for_member(row.member_id),
            self._dkp_projection.raid_rank_for_member(row.member_id))

    def _populate(self, *_args) -> None:
        query = self.search.text().strip().casefold()
        class_name = self.class_filter.currentData()
        rows = [row for row in self._rows
                if (not query or query in row.name.casefold()
                    or query in (row.class_name or "").casefold())
                and (not class_name or
                     (row.class_name is None if class_name == "__unknown__"
                      else row.class_name == class_name))]
        values = [(
            row.name, row.class_name or tr("identity_v2_views.unknown_class"),
            _rank_text(self._active_rank(row)),
            raid_role_display(getattr(row, "raidRole", "not_set")),
            character_type_display(getattr(row, "role", "not_set")),
            gear_status_display(getattr(row, "gearStatus", "Level")),
            raid_status_display(getattr(row, "raidStatus", "")),
            str(getattr(row, "matrixRaidCount", row.raid_count)),
            str(getattr(row, "raidDays", 0)),
            _number_or_dash(self._point_value(row, "availableDkp")),
            _number_or_dash(row.eternal_dkp),
            _number_or_dash(getattr(row, "playerEternalDkp", None)),
            _number_or_dash(self._point_value(row, "raidPoints")),
            _number_or_dash(self._point_value(row, "eternalRaidPoints")),
            _number_or_dash(getattr(row, "playerRaidPoints", None)),
            (tr("identity_v2_views.armory")
             if _is_http_url(getattr(row, "armoryUrl", None) or "") else ""),
        ) for row in rows]
        _set_rows(self.table, values, [row.member_id for row in rows])
        for table_row, row in enumerate(rows):
            class_item = self.table.item(table_row, 1)
            if row.class_name in CLASS_COLORS:
                class_item.setForeground(QColor(CLASS_COLORS[row.class_name]))
                icon_path = class_icon_path(row.class_name)
                if icon_path is not None:
                    class_item.setIcon(QIcon(str(icon_path)))
            rank = self._active_rank(row)
            path = (getattr(row, "dkpRankPath", None)
                    if self._point_presentation.shows("dkp_rank") else
                    getattr(row, "raidRankPath", None))
            if path is None and rank and self._dkp_projection is not None:
                path = self._dkp_projection.registry.rank_path(rank, 48)
            if path is not None:
                self.table.item(table_row, 2).setIcon(QIcon(str(path)))
            url = getattr(row, "armoryUrl", None)
            if url and _is_http_url(url):
                link = self.table.item(table_row, 15)
                link.setData(Qt.ItemDataRole.UserRole, url)
                link.setForeground(QColor("#8fc7ff"))
                font = link.font()
                font.setUnderline(True)
                link.setFont(font)
                link.setToolTip(url)

    def _cell_clicked(self, row: int, column: int) -> None:
        if column != 15:
            return
        item = self.table.item(row, column)
        url = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if url and _is_http_url(url):
            QDesktopServices.openUrl(QUrl(url))


def _number_or_dash(value) -> str:
    if value is None:
        return "–"
    return f"{value:g}" if isinstance(value, float) else str(value)


def _rank_text(asset_id: str | None) -> str:
    return asset_id.replace("_", " ") if asset_id else "–"


def _sort_optional(value):
    return value is None, value if value is not None else 0


class IdentityV2RaidPage(QWidget):
    RAID_HEADERS = ("date", "raid_name", "source", "participants",
                    "clm_raid_id", "csv_sources", "report_urls")
    DETAIL_HEADERS = ("character", "class", "member_id", "historical_role", "source_guid")

    def __init__(self):
        super().__init__()
        self._data: IdentityV2ViewData | None = None
        self._raids: list[V2RaidRow] = []
        self._details: list[V2AttendanceRow] = []
        self._raid_sort: tuple[int, bool] | None = None
        self._detail_sort: tuple[int, bool] | None = None
        layout = QVBoxLayout(self)
        self.show_matrix_button = QPushButton(tr("identity_v2_matrix.open"))
        layout.addWidget(self.show_matrix_button)
        self.adjust_points_button = QPushButton(tr("raid_points.adjust"))
        layout.addWidget(self.adjust_points_button)
        self.show_points_button = QPushButton(tr("raid_points.point_history"))
        layout.addWidget(self.show_points_button)
        self.rebuild_points_button = QPushButton(tr("raid_points.rebuild_only"))
        layout.addWidget(self.rebuild_points_button)
        self.points_status_label = QLabel("")
        self.points_status_label.setWordWrap(True)
        layout.addWidget(self.points_status_label)
        self.analyze_csv_button = QPushButton(tr("csv_v2_analysis.action"))
        layout.addWidget(self.analyze_csv_button)
        self.raid_search = QLineEdit()
        self.raid_search.setPlaceholderText(tr("identity_v2_views.raid_search"))
        self.raid_search.textChanged.connect(self._populate_raids)
        layout.addWidget(self.raid_search)
        split = QSplitter(Qt.Orientation.Vertical)
        upper = QWidget()
        upper_layout = QVBoxLayout(upper)
        upper_layout.addWidget(QLabel(tr("identity_v2_views.raids_title")))
        self.raid_table = _table(tuple(tr(f"identity_v2_views.{key}")
                                       for key in self.RAID_HEADERS))
        self.raid_table.horizontalHeader().sectionClicked.connect(self._sort_raids)
        self.raid_table.itemSelectionChanged.connect(self._selection_changed)
        upper_layout.addWidget(self.raid_table)
        split.addWidget(upper)
        lower = QWidget()
        lower_layout = QVBoxLayout(lower)
        lower_layout.addWidget(QLabel(tr("identity_v2_views.attendance_title")))
        self.detail_search = QLineEdit()
        self.detail_search.setPlaceholderText(tr("identity_v2_views.attendance_search"))
        self.detail_search.textChanged.connect(self._populate_details)
        lower_layout.addWidget(self.detail_search)
        self.detail_table = _table(tuple(tr(f"identity_v2_views.{key}")
                                         for key in self.DETAIL_HEADERS))
        self.detail_table.horizontalHeader().sectionClicked.connect(self._sort_details)
        lower_layout.addWidget(self.detail_table)
        split.addWidget(lower)
        layout.addWidget(split)

    def set_view_data(self, data: IdentityV2ViewData) -> None:
        self._data = data
        self._raids = list(data.raids)
        self._raid_sort = None
        self._detail_sort = None
        self.raid_search.blockSignals(True)
        self.raid_search.clear()
        self.raid_search.blockSignals(False)
        self.detail_search.blockSignals(True)
        self.detail_search.clear()
        self.detail_search.blockSignals(False)
        self._populate_raids()

    def _sort_raids(self, column: int) -> None:
        descending = self._raid_sort == (column, False)
        keys = (lambda row: row.date, lambda row: row.name.casefold(),
                lambda row: row.source, lambda row: row.participant_count,
                lambda row: row.clm_raid_id or "",
                lambda row: ", ".join(row.csv_source_files),
                lambda row: ", ".join(row.csv_report_urls))
        self._raids.sort(key=lambda row: (keys[column](row), row.raid_id),
                         reverse=descending)
        self._raid_sort = (column, descending)
        self._populate_raids()

    def _populate_raids(self, *_args) -> None:
        query = self.raid_search.text().strip().casefold()
        rows = [row for row in self._raids
                if not query or query in row.date.casefold() or query in row.name.casefold()]
        _set_rows(self.raid_table, [(
            row.date, row.name or "–", row.source, str(row.participant_count),
            row.clm_raid_id or "–",
            ", ".join(row.csv_source_files) or "–",
            "",
        ) for row in rows], [row.raid_id for row in rows])
        for index, row in enumerate(rows):
            self.raid_table.setCellWidget(
                index, 6, self._report_urls_widget(row.csv_report_urls),
            )
        if self.raid_table.currentRow() < 0 and rows:
            self.raid_table.selectRow(0)
        self._selection_changed()

    def _report_urls_widget(self, report_urls: tuple[str, ...]) -> QLabel:
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        label.setOpenExternalLinks(False)
        rendered: list[str] = []
        for raw_url in report_urls:
            value = str(raw_url)
            url = value.strip()
            if _is_http_url(url):
                rendered.append(f'<a href="{escape(url, quote=True)}">{escape(value)}</a>')
            else:
                rendered.append(escape(value))
        label.setText(" · ".join(rendered) if rendered else "–")
        label.setToolTip("\n".join(str(url) for url in report_urls))
        if any(_is_http_url(str(url)) for url in report_urls):
            label.setCursor(Qt.CursorShape.PointingHandCursor)
        label.linkActivated.connect(self._open_report_url)
        return label

    @staticmethod
    def _open_report_url(value: str) -> None:
        url = value.strip()
        if _is_http_url(url):
            QDesktopServices.openUrl(QUrl(url))

    def _selection_changed(self) -> None:
        current = self.raid_table.currentRow()
        item = self.raid_table.item(current, 0) if current >= 0 else None
        raid_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        self._details = list(self._data.attendance_by_raid.get(raid_id, ())) if self._data else []
        self._detail_sort = None
        self._populate_details()

    def selected_raid_id(self) -> str | None:
        current = self.raid_table.currentRow()
        item = self.raid_table.item(current, 0) if current >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _sort_details(self, column: int) -> None:
        descending = self._detail_sort == (column, False)
        keys = (lambda row: row.name.casefold(),
                lambda row: (row.class_name or "").casefold(),
                lambda row: row.member_id, lambda row: row.historical_role,
                lambda row: row.source_guid or "")
        self._details.sort(key=lambda row: (keys[column](row), row.member_id),
                           reverse=descending)
        self._detail_sort = (column, descending)
        self._populate_details()

    def _populate_details(self, *_args) -> None:
        query = self.detail_search.text().strip().casefold()
        rows = [row for row in self._details if not query or query in row.name.casefold()]
        roles = {"main": tr("identity_v2_views.role_main"),
                 "twink": tr("identity_v2_views.role_twink"),
                 "unknown": tr("identity_v2_views.role_unknown")}
        _set_rows(self.detail_table, [(
            row.name, row.class_name or tr("identity_v2_views.unknown_class"),
            row.member_id,
            roles[row.historical_role], row.source_guid or "–",
        ) for row in rows], [row.attendance_id for row in rows])
