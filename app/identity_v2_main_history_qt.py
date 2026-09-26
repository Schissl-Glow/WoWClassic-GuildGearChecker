"""Draft-only Main history editor for one Identity V2 Player."""

from __future__ import annotations

import copy
from collections import Counter
from datetime import date
from typing import Callable

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog,
    QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .i18n import get_language, tr
from .identity_v2 import IdentityV2Store, MainHistoryEntry, Member
from .identity_v2_main_history import (
    add_main_history_entry, find_main_history_conflicts,
    reconcile_draft_history_sequence, remove_main_history_entry,
    set_main_since_date, update_main_history_entry,
)


HISTORY_COLUMN_WIDTHS = (205, 110, 110, 95, 105, 145)


def _display_date(value: str | None) -> str:
    if value is None:
        return tr("identity_v2_main_history.unknown")
    day = date.fromisoformat(value)
    return day.strftime("%d.%m.%Y") if get_language() == "de" else value


class OptionalDateField(QWidget):
    """A real calendar date or an explicit unknown boundary."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.unknown = QCheckBox(tr("identity_v2_main_history.unknown"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat(
            "dd.MM.yyyy" if get_language() == "de" else "yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())
        self.unknown.toggled.connect(
            lambda checked: self.date_edit.setEnabled(not checked))
        layout.addWidget(self.unknown)
        layout.addWidget(self.date_edit, 1)
        self.set_value(None)

    def set_value(self, value: str | None) -> None:
        if value is not None:
            self.date_edit.setDate(QDate.fromString(value, "yyyy-MM-dd"))
        self.unknown.setChecked(value is None)
        self.date_edit.setEnabled(value is not None)

    def value(self) -> str | None:
        return None if self.unknown.isChecked() else self.date_edit.date().toPython().isoformat()


class MainHistoryDialog(QDialog):
    """Edit a detached Store copy and offer one final validated result."""

    def __init__(
        self, store: IdentityV2Store, player_id: str,
        current_store: Callable[[], IdentityV2Store | None],
        column_widths: tuple[int, ...] | list[int] = HISTORY_COLUMN_WIDTHS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        store.validate()
        self.source_store = store
        self.source_payload = store.to_payload()
        self.draft_store = copy.deepcopy(store)
        self.current_store = current_store
        self.player_id = player_id
        self.result_store: IdentityV2Store | None = None
        self._selected_history_id: str | None = None
        self._new_mode = False
        self._rendering = False
        self._sort_state: tuple[int, bool] | None = None
        self._history_order = [item.historyId for item in self._player().mainHistory]
        self._member_labels = self._build_member_labels()
        player = self._player()
        self.setObjectName("identityV2MainHistoryDialog")
        self.setWindowTitle(tr("identity_v2_main_history.title", player=player.displayName))
        self.resize(850, 700)
        layout = QVBoxLayout(self)

        self.current_main_label = QLabel()
        self.current_main_label.setWordWrap(True)
        layout.addWidget(self.current_main_label)
        since_row = QHBoxLayout()
        since_row.addWidget(QLabel(tr("identity_v2_main_history.current_since")))
        self.main_since = OptionalDateField()
        since_row.addWidget(self.main_since, 1)
        self.since_button = QPushButton(tr("identity_v2_main_history.update_current_since"))
        self.since_button.clicked.connect(lambda: self._stage_main_since())
        since_row.addWidget(self.since_button)
        layout.addLayout(since_row)

        self.table = QTableWidget(0, 6)
        self.table.setObjectName("mainHistoryTable")
        self.table.setHorizontalHeaderLabels(tuple(tr(
            f"identity_v2_main_history.column_{key}") for key in (
                "character", "from", "to", "source", "reason", "conflict")))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().sectionClicked.connect(self._sort_rows)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        for index, width in enumerate(column_widths[:6]):
            if isinstance(width, int) and not isinstance(width, bool) and 50 <= width <= 2400:
                self.table.setColumnWidth(index, width)
        self.conflict_list = QListWidget()
        self.conflict_list.setObjectName("mainHistoryConflicts")
        self.conflict_list.itemClicked.connect(self._conflict_clicked)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        conflict_panel = QWidget()
        conflict_layout = QVBoxLayout(conflict_panel)
        conflict_layout.setContentsMargins(0, 0, 0, 0)
        conflict_layout.addWidget(QLabel(tr("identity_v2_main_history.conflicts")))
        conflict_layout.addWidget(self.conflict_list)
        splitter.addWidget(conflict_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        edit_group = QGroupBox(tr("identity_v2_main_history.edit_entry"))
        form = QFormLayout(edit_group)
        self.member_combo = QComboBox()
        for member in self._members():
            self.member_combo.addItem(self._member_labels[member.memberId], member.memberId)
        form.addRow(tr("identity_v2_main_history.character"), self.member_combo)
        self.from_date = OptionalDateField()
        self.to_date = OptionalDateField()
        form.addRow(tr("identity_v2_main_history.from_date"), self.from_date)
        form.addRow(tr("identity_v2_main_history.to_date"), self.to_date)
        self.origin_label = QLabel()
        form.addRow(tr("identity_v2_main_history.origin"), self.origin_label)
        layout.addWidget(edit_group)

        actions = QHBoxLayout()
        self.new_button = QPushButton(tr("identity_v2_main_history.new_entry"))
        self.new_button.setEnabled(bool(self._members()))
        self.new_button.clicked.connect(self._start_new)
        actions.addWidget(self.new_button)
        self.stage_button = QPushButton()
        self.stage_button.clicked.connect(self._stage_entry)
        actions.addWidget(self.stage_button)
        self.remove_button = QPushButton(tr("identity_v2_main_history.remove_entry"))
        self.remove_button.clicked.connect(self._remove_entry)
        actions.addWidget(self.remove_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            tr("identity_v2_main_history.apply"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("common.cancel"))
        buttons.accepted.connect(self._apply_draft)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_views(preferred_id=self._history_order[0] if self._history_order else None)
        self.main_since.set_value(player.mainSinceDate)

    def _player(self):
        return next(item for item in self.draft_store.players
                    if item.playerId == self.player_id)

    def _members(self) -> tuple[Member, ...]:
        return tuple(sorted(
            (item for item in self.draft_store.members if item.playerId == self.player_id),
            key=lambda item: (item.name.casefold(), item.memberId)))

    def _build_member_labels(self) -> dict[str, str]:
        members = self._members()
        names = Counter(item.name.casefold() for item in members)
        labels = {}
        for member in members:
            status = tr(f"life.{member.lifeStatus}")
            label = (f"{member.name} · "
                     f"{member.className or tr('identity_v2_players.unknown_class')} · "
                     f"{status}")
            if member.deathDate:
                label += f" · {_display_date(member.deathDate)}"
            if names[member.name.casefold()] > 1:
                label += f" · {member.memberId}"
            labels[member.memberId] = label
        return labels

    def column_widths(self) -> list[int]:
        return [self.table.columnWidth(index) for index in range(6)]

    def _history(self) -> dict[str, MainHistoryEntry]:
        return {item.historyId: item for item in self._player().mainHistory}

    def _select_history(self, history_id: str | None) -> None:
        self._rendering = True
        try:
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == history_id:
                    self.table.setCurrentCell(row, 0)
                    self.table.scrollToItem(self.table.item(row, 0))
                    return
            self.table.clearSelection()
        finally:
            self._rendering = False

    def _refresh_views(self, preferred_id: str | None = None) -> None:
        player = self._player()
        current = next((item for item in self.draft_store.members
                        if item.memberId == player.mainMemberId), None)
        self.current_main_label.setText(tr(
            "identity_v2_main_history.current_main",
            member=self._member_labels[current.memberId] if current is not None
                   else tr("identity_v2_players.no_main")))
        self.main_since.setEnabled(current is not None)
        self.since_button.setEnabled(current is not None)
        conflicts = find_main_history_conflicts(self.draft_store, self.player_id)
        conflicted_ids = {history_id for conflict in conflicts
                          for history_id in conflict.historyIds if history_id != "current"}
        history = self._history()
        self._history_order = [item for item in self._history_order if item in history]
        self._history_order.extend(item for item in history if item not in self._history_order)
        self._rendering = True
        try:
            self.table.setRowCount(len(self._history_order))
            for row, history_id in enumerate(self._history_order):
                item = history[history_id]
                values = (
                    self._member_labels[item.memberId],
                    _display_date(item.fromDate), _display_date(item.toDate),
                    tr(f"identity_v2_main_history.source_{item.source}"),
                    tr(f"identity_v2_main_history.reason_{item.reason or 'unknown'}"),
                    tr("identity_v2_main_history.overlap")
                    if history_id in conflicted_ids else "–",
                )
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    cell.setData(Qt.ItemDataRole.UserRole, history_id)
                    if history_id in conflicted_ids:
                        cell.setForeground(QColor("#ff8787"))
                        cell.setToolTip(tr("identity_v2_main_history.overlap_tooltip"))
                    self.table.setItem(row, column, cell)
        finally:
            self._rendering = False
        self.conflict_list.clear()
        for conflict in conflicts:
            first, second = conflict.periods
            def describe(period):
                label = self._member_labels[period.memberId]
                end = (tr("identity_v2_main_history.current_open")
                       if period.historyId == "current"
                       else _display_date(period.toDate))
                return (f"{label}: {_display_date(period.fromDate)} – "
                        f"{end}")
            text = f"{describe(first)}  ↔  {describe(second)}"
            list_item = QListWidgetItem(text)
            list_item.setForeground(QColor("#ff8787"))
            list_item.setData(Qt.ItemDataRole.UserRole, conflict.historyIds)
            self.conflict_list.addItem(list_item)
        self._selected_history_id = preferred_id if preferred_id in history else None
        self._select_history(self._selected_history_id)
        self._load_editor(self._selected_history_id)

    def _load_editor(self, history_id: str | None) -> None:
        self._rendering = True
        try:
            item = self._history().get(history_id)
            if item is None:
                self.member_combo.setCurrentIndex(0 if self.member_combo.count() else -1)
                self.from_date.set_value(None)
                self.to_date.set_value(None)
                self.origin_label.setText(tr("identity_v2_main_history.source_manual"))
                self.stage_button.setText(tr("identity_v2_main_history.add_entry"))
            else:
                self.member_combo.setCurrentIndex(self.member_combo.findData(item.memberId))
                self.from_date.set_value(item.fromDate)
                self.to_date.set_value(item.toDate)
                source_text = tr(f"identity_v2_main_history.source_{item.source}")
                reason_text = tr(
                    f"identity_v2_main_history.reason_{item.reason or 'unknown'}")
                self.origin_label.setText(f"{source_text} · {reason_text}")
                self.stage_button.setText(tr("identity_v2_main_history.update_entry"))
            self.stage_button.setEnabled(self._new_mode or item is not None)
            self.remove_button.setEnabled(item is not None)
            self.member_combo.setEnabled(self._new_mode or item is not None)
            self.from_date.setEnabled(self._new_mode or item is not None)
            self.to_date.setEnabled(self._new_mode or item is not None)
        finally:
            self._rendering = False

    def _error_text(self, error: Exception) -> str:
        detail = str(error)
        if "starts after it ends" in detail or "fromDate" in detail or "toDate" in detail:
            return tr("identity_v2_main_history.invalid_range")
        if "outside its Player" in detail or "must belong" in detail:
            return tr("identity_v2_main_history.foreign_member")
        if "requires a current Main" in detail:
            return tr("identity_v2_main_history.no_current_main")
        return tr("identity_v2_main_history.invalid_change")

    def _show_error(self, error: Exception) -> None:
        QMessageBox.warning(self, tr("identity_v2_main_history.title_short"),
                            self._error_text(error))

    def _form_values(self) -> tuple[str | None, str | None, str | None]:
        return self.member_combo.currentData(), self.from_date.value(), self.to_date.value()

    def _stage_selected(self) -> bool:
        history_id = self._selected_history_id
        if history_id is None:
            return True
        member_id, from_date, to_date = self._form_values()
        item = self._history()[history_id]
        if (member_id, from_date, to_date) == (item.memberId, item.fromDate, item.toDate):
            return True
        try:
            self.draft_store = update_main_history_entry(
                self.draft_store, history_id, member_id=member_id,
                from_date=from_date, to_date=to_date)
        except (TypeError, ValueError) as exc:
            self._show_error(exc)
            return False
        return True

    def _selection_changed(self) -> None:
        if self._rendering:
            return
        row = self.table.currentRow()
        cell = self.table.item(row, 0) if row >= 0 else None
        new_id = cell.data(Qt.ItemDataRole.UserRole) if cell is not None else None
        if new_id == self._selected_history_id:
            return
        previous = self._selected_history_id
        if previous is not None and not self._stage_selected():
            self._select_history(previous)
            return
        self._new_mode = False
        self._refresh_views(preferred_id=new_id)

    def _sort_rows(self, column: int) -> None:
        if column not in range(6):
            return
        if not self._stage_selected():
            return
        descending = self._sort_state == (column, False)
        self._sort_state = (column, descending)
        history = self._history()
        conflicted = {entry for conflict in find_main_history_conflicts(
            self.draft_store, self.player_id) for entry in conflict.historyIds}
        def key(history_id: str):
            item = history[history_id]
            fields = (self._member_labels[item.memberId].casefold(),
                      item.fromDate or "", item.toDate or "", item.source,
                      item.reason or "", history_id in conflicted)
            return fields[column], history_id
        self._history_order.sort(key=key, reverse=descending)
        self._refresh_views(preferred_id=self._selected_history_id)

    def _conflict_clicked(self, item: QListWidgetItem) -> None:
        history_ids = item.data(Qt.ItemDataRole.UserRole)
        target = next((history_id for history_id in history_ids
                       if history_id != "current"), None)
        if target is not None:
            self._select_history(target)
            self._selection_changed()

    def _start_new(self) -> None:
        if not self._stage_selected():
            return
        self._new_mode = True
        self._selected_history_id = None
        self._refresh_views()

    def _stage_entry(self) -> None:
        member_id, from_date, to_date = self._form_values()
        try:
            if self._new_mode:
                self.draft_store = add_main_history_entry(
                    self.draft_store, self.player_id, member_id, from_date, to_date)
                history_id = self._player().mainHistory[-1].historyId
                self._new_mode = False
            elif self._selected_history_id is not None:
                if not self._stage_selected():
                    return
                history_id = self._selected_history_id
            else:
                return
        except (TypeError, ValueError) as exc:
            self._show_error(exc)
            return
        self._refresh_views(preferred_id=history_id)

    def _remove_entry(self) -> None:
        history_id = self._selected_history_id
        if history_id is None:
            return
        if QMessageBox.question(
            self, tr("identity_v2_main_history.title_short"),
            tr("identity_v2_main_history.confirm_remove"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.draft_store = remove_main_history_entry(self.draft_store, history_id)
        except (TypeError, ValueError) as exc:
            self._show_error(exc)
            return
        self._history_order.remove(history_id)
        self._refresh_views()

    def _still_current(self) -> bool:
        current = self.current_store()
        if current is not self.source_store or current.to_payload() != self.source_payload:
            QMessageBox.warning(self, tr("identity_v2_main_history.title_short"),
                                tr("identity_v2_main_history.stale_project"))
            return False
        return True

    def _stage_main_since(self, *, refresh: bool = True) -> bool:
        value = self.main_since.value() if self._player().mainMemberId else None
        if value == self._player().mainSinceDate:
            return True
        try:
            self.draft_store = set_main_since_date(
                self.draft_store, self.player_id, value)
        except (TypeError, ValueError) as exc:
            self._show_error(exc)
            return False
        if refresh:
            self._refresh_views(preferred_id=self._selected_history_id)
        return True

    def _apply_draft(self) -> None:
        if self._new_mode:
            QMessageBox.warning(self, tr("identity_v2_main_history.title_short"),
                                tr("identity_v2_main_history.finish_new_entry"))
            return
        if not self._stage_selected():
            return
        self._refresh_views(preferred_id=self._selected_history_id)
        if not self._still_current():
            return
        try:
            if not self._stage_main_since(refresh=False):
                return
            self.draft_store = reconcile_draft_history_sequence(
                self.draft_store, self.source_store)
            self.draft_store.validate()
            if self.draft_store.to_payload() == self.source_payload:
                self.result_store = None
                self.accept()
                return
            conflicts = find_main_history_conflicts(self.draft_store, self.player_id)
        except (TypeError, ValueError) as exc:
            self._show_error(exc)
            return
        if conflicts and QMessageBox.question(
            self, tr("identity_v2_main_history.title_short"),
            tr("identity_v2_main_history.confirm_overlap", count=len(conflicts)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        if not self._still_current():
            return
        self.result_store = self.draft_store
        self.accept()
