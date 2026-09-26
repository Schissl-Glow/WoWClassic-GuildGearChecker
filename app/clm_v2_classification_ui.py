"""One classification review for finalized CLM character groups."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHeaderView, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .clm_identity_v2_analysis import ClmIdentityAnalysis
from .clm_identity_v2_decisions import ClmIdentityDecisionSet
from .clm_identity_v2_materialization import finalized_clm_character_groups
from .clm_matching import character_key
from .i18n import tr
from .identity_v2 import IdentityV2Store
from .identity_v2_import_choices import CharacterImportChoice
from .qt_row_hover import install_row_hover


class ClmV2ClassificationDialog(QDialog):
    def __init__(
        self, analysis: ClmIdentityAnalysis, decisions: ClmIdentityDecisionSet,
        parent: QWidget | None = None,
        *, target_store: IdentityV2Store | None = None,
        include_chains: set[tuple[str, ...]] | None = None,
    ):
        super().__init__(parent)
        self._rows = list(finalized_clm_character_groups(analysis, decisions))
        if include_chains is not None:
            self._rows = [row for row in self._rows if row[1] in include_chains]
        self._target_store = target_store
        self._player_choice: dict[tuple[str, ...], str | None] = {}
        self._member_choice: dict[tuple[str, ...], str | None] = {}
        self._target_members_by_id = {
            member.memberId: member for member in
            (target_store.members if target_store is not None else ())
        }
        histories = {history.guid: history for history in analysis.guid_histories}
        self._class_by_chain = {
            chain: histories[chain[-1]].character_class or ""
            for _name, chain in self._rows
        }
        self._existing_options = {
            chain: [member for member in (target_store.members if target_store else ())
                    if member.lifeStatus != "dead"
                    and character_key(member.name) == character_key(name)
                    and (not member.className or not self._class_by_chain[chain]
                         or member.className == self._class_by_chain[chain])]
            for name, chain in self._rows
        }
        self._show_member_column = any(self._existing_options.values())
        self.choices: dict[tuple[str, ...], CharacterImportChoice] = {}
        self.result_value: dict[tuple[str, ...], CharacterImportChoice] | None = None
        self._sort: tuple[int, bool] | None = None
        self.setWindowTitle(tr("clm_v2_classification.title"))
        layout = QVBoxLayout(self)
        label = QLabel(tr("clm_v2_classification.explanation"))
        label.setWordWrap(True)
        layout.addWidget(label)
        self.table = QTableWidget(
            0, 4 + int(target_store is not None) + int(self._show_member_column))
        self.table.row_hover = install_row_hover(self.table)
        headers = [
            tr("identity_v2_views.character"),
            tr("identity_v2_views.class"),
            tr("clm_v2_classification.guid_group"),
            tr("csv_v2_analysis.import_classification"),
        ]
        if target_store is not None:
            headers.append(tr("raid_clm_admin.clm_player"))
        if self._show_member_column:
            headers.append(tr("clm_v2_classification.existing_member"))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setSortingEnabled(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self._size_columns(headers)
        self.table.horizontalHeader().sectionClicked.connect(self._sort_rows)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        active = QPushButton(tr("csv_v2_analysis.bulk_active"))
        active.clicked.connect(lambda: self._classify_open("ACTIVE_UNKNOWN"))
        buttons.addWidget(active)
        inactive = QPushButton(tr("csv_v2_analysis.bulk_inactive"))
        inactive.clicked.connect(lambda: self._classify_open("INACTIVE_UNKNOWN"))
        buttons.addWidget(inactive)
        irrelevant = QPushButton(tr("csv_v2_analysis.selected_irrelevant"))
        irrelevant.clicked.connect(self._ignore_selected)
        buttons.addWidget(irrelevant)
        buttons.addStretch(1)
        cancel = QPushButton(tr("common.cancel"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        confirm = QPushButton(tr("clm_v2_classification.confirm"))
        confirm.clicked.connect(self._confirm)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)
        self._populate()

    def _size_columns(self, headers: list[str]) -> None:
        table = self.table
        metrics = table.fontMetrics()
        padding = metrics.horizontalAdvance("MMMM")

        def preferred(
            column: int, values: list[str], minimum: int, maximum: int | None,
        ) -> int:
            content = max((metrics.horizontalAdvance(value) for value in
                           [headers[column], *values]), default=0)
            width = max(minimum, content + padding)
            return min(maximum, width) if maximum is not None else width

        widths = [
            preferred(0, [name for name, _chain in self._rows], 160, 300),
            preferred(1, list(self._class_by_chain.values()), 100, 160),
            preferred(2, [", ".join(chain) for _name, chain in self._rows], 240, 380),
            preferred(3, [tr("csv_v2_analysis.open_classification"),
                          tr("clm_v2_classification.active"),
                          tr("clm_v2_classification.inactive"),
                          tr("clm_v2_classification.irrelevant")], 220, None),
        ]
        if self._target_store is not None:
            widths.append(preferred(
                4, [tr("common.not_set"), *(
                    f"{player.displayName} · {player.playerId}"
                    for player in self._target_store.players)], 320, None))
        if self._show_member_column:
            widths.append(preferred(
                5, [tr("common.not_set"), *(
                    tr("raid_clm_admin.clm_existing_member",
                       name=member.name, member_id=member.memberId)
                    for options in self._existing_options.values()
                    for member in options)], 280, 480))

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(max(70, metrics.height() * 3))
        for column, width in enumerate(widths):
            table.setColumnWidth(column, width)
        header.setStretchLastSection(True)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        screen = self.screen()
        margins = self.layout().contentsMargins()
        preferred_width = (
            sum(widths) + table.verticalHeader().width() + table.frameWidth() * 2
            + margins.left() + margins.right() + metrics.horizontalAdvance("MMMM")
        )
        available_width = screen.availableGeometry().width() if screen else preferred_width
        self.resize(min(preferred_width, int(available_width * 0.9)), 690)

    @staticmethod
    def _token(choice: CharacterImportChoice | None) -> str:
        if choice is None:
            return ""
        if choice.relevance == "irrelevant":
            return "IRRELEVANT"
        return ("ACTIVE_UNKNOWN" if choice.activity_status == "active"
                else "INACTIVE_UNKNOWN")

    def _set_choice(self, chain: tuple[str, ...], token: str | None) -> None:
        if token is None:
            self.choices.pop(chain, None)
        elif token == "IRRELEVANT":
            self.choices[chain] = CharacterImportChoice(relevance="irrelevant")
            self._member_choice.pop(chain, None)
        elif token in {"ACTIVE_UNKNOWN", "INACTIVE_UNKNOWN", "ACTIVE", "INACTIVE"}:
            member_id = self._member_choice.get(chain)
            if member_id:
                member = self._target_members_by_id[member_id]
                self.choices[chain] = CharacterImportChoice(
                    activity_status=member.lifeStatus, member_id=member_id)
            else:
                self.choices[chain] = CharacterImportChoice(
                    activity_status=("inactive" if token in
                                     {"INACTIVE_UNKNOWN", "INACTIVE"} else "active"),
                    player_id=self._player_choice.get(chain))

    def _set_member(self, chain: tuple[str, ...], member_id: str | None) -> None:
        if member_id is None:
            self._member_choice.pop(chain, None)
        else:
            self._member_choice[chain] = member_id
        choice = self.choices.get(chain)
        if member_id:
            member = self._target_members_by_id[member_id]
            self.choices[chain] = CharacterImportChoice(
                activity_status=member.lifeStatus, member_id=member_id)
        elif choice is not None and choice.relevance == "relevant":
            self.choices[chain] = replace(
                choice, member_id=None, player_id=self._player_choice.get(chain))

    def _set_player(self, chain: tuple[str, ...], player_id: str | None) -> None:
        self._player_choice[chain] = player_id
        choice = self.choices.get(chain)
        if choice is not None and choice.relevance == "relevant" and not choice.member_id:
            self.choices[chain] = replace(choice, player_id=player_id)

    @staticmethod
    def _select_without_signal(combo: QComboBox, value: str | None) -> None:
        blocked = combo.blockSignals(True)
        try:
            combo.setCurrentIndex(combo.findData(value))
        finally:
            combo.blockSignals(blocked)

    def _classification_changed(
        self, chain: tuple[str, ...], token: str | None, row: int,
    ) -> None:
        self._set_choice(chain, token)
        if self._target_store is None:
            return
        ignored = token == "IRRELEVANT"
        player_combo = self.table.cellWidget(row, 4)
        if player_combo is not None:
            self._select_without_signal(
                player_combo, None if ignored else self._player_choice.get(chain))
            player_combo.setEnabled(not ignored and not self._member_choice.get(chain))
        if self._show_member_column:
            member_combo = self.table.cellWidget(row, 5)
            if member_combo is not None:
                self._select_without_signal(
                    member_combo, self._member_choice.get(chain))
                member_combo.setEnabled(not ignored)

    def _member_selection_changed(
        self, chain: tuple[str, ...], member_id: str | None, row: int,
    ) -> None:
        self._set_member(chain, member_id)
        status_combo = self.table.cellWidget(row, 3)
        self._select_without_signal(
            status_combo, self._token(self.choices.get(chain)))
        status_combo.setEnabled(member_id is None)
        player_combo = self.table.cellWidget(row, 4)
        displayed_player = (self._target_members_by_id[member_id].playerId
                            if member_id else self._player_choice.get(chain))
        self._select_without_signal(player_combo, displayed_player)
        player_combo.setEnabled(member_id is None)

    def _sort_rows(self, column: int) -> None:
        descending = self._sort == (column, False)
        keys = (
            lambda row: row[0].casefold(),
            lambda row: self._class_by_chain[row[1]].casefold(),
            lambda row: ",".join(row[1]),
            lambda row: self._token(self.choices.get(row[1])),
            lambda row: self._player_choice.get(row[1]) or "",
            lambda row: self._member_choice.get(row[1]) or "",
        )
        self._rows.sort(key=lambda row: (keys[column](row), row[1]),
                        reverse=descending)
        self._sort = (column, descending)
        self._populate()

    def _populate(self) -> None:
        table = self.table
        selected = {
            tuple(table.item(index.row(), 2).data(Qt.ItemDataRole.UserRole))
            for index in table.selectionModel().selectedRows()
            if table.item(index.row(), 2)
        }
        scroll = table.verticalScrollBar().value()
        table.setRowCount(len(self._rows))
        table.clearSelection()
        for row_index, (name, chain) in enumerate(self._rows):
            table.setItem(row_index, 0, QTableWidgetItem(name))
            table.setItem(row_index, 1, QTableWidgetItem(self._class_by_chain[chain]))
            guids = QTableWidgetItem(", ".join(chain))
            guids.setData(Qt.ItemDataRole.UserRole, list(chain))
            guids.setToolTip(", ".join(chain))
            table.setItem(row_index, 2, guids)
            combo = QComboBox()
            combo.setMinimumWidth(200)
            combo.setMinimumHeight(30)
            combo.addItem(tr("csv_v2_analysis.open_classification"), None)
            combo.addItem(tr("clm_v2_classification.active"), "ACTIVE_UNKNOWN")
            combo.addItem(tr("clm_v2_classification.inactive"), "INACTIVE_UNKNOWN")
            combo.addItem(tr("clm_v2_classification.irrelevant"), "IRRELEVANT")
            token = self._token(self.choices.get(chain))
            if token:
                combo.setCurrentIndex(combo.findData(token))
            member_id = self._member_choice.get(chain)
            ignored = token == "IRRELEVANT"
            combo.setEnabled(not member_id)
            combo.currentIndexChanged.connect(
                lambda _index, group=chain, control=combo, row=row_index:
                self._classification_changed(group, control.currentData(), row)
            )
            table.setCellWidget(row_index, 3, combo)
            if self._target_store is not None:
                player_combo = QComboBox()
                player_combo.setMinimumWidth(220)
                player_combo.addItem(tr("common.not_set"), None)
                for player in self._target_store.players:
                    player_combo.addItem(
                        f"{player.displayName} · {player.playerId}", player.playerId)
                if ignored:
                    displayed_player = None
                elif member_id:
                    displayed_player = self._target_members_by_id[member_id].playerId
                else:
                    displayed_player = self._player_choice.get(chain)
                player_combo.setCurrentIndex(
                    player_combo.findData(displayed_player))
                player_combo.setEnabled(not member_id and not ignored)
                player_combo.currentIndexChanged.connect(
                    lambda _index, group=chain, control=player_combo:
                    self._set_player(group, control.currentData()))
                table.setCellWidget(row_index, 4, player_combo)
            if self._show_member_column:
                member_combo = QComboBox()
                member_combo.setMinimumWidth(250)
                member_combo.addItem(tr("common.not_set"), None)
                for member in self._existing_options[chain]:
                    member_combo.addItem(
                        tr("raid_clm_admin.clm_existing_member",
                           name=member.name, member_id=member.memberId),
                        member.memberId)
                member_combo.setCurrentIndex(
                    member_combo.findData(member_id))
                member_combo.setEnabled(not ignored)
                member_combo.currentIndexChanged.connect(
                    lambda _index, group=chain, control=member_combo, row=row_index:
                    self._member_selection_changed(group, control.currentData(), row))
                table.setCellWidget(row_index, 5, member_combo)
            if chain in selected:
                table.selectRow(row_index)
        table.verticalScrollBar().setValue(scroll)

    def _classify_open(self, token: str) -> None:
        for _name, chain in self._rows:
            if chain not in self.choices:
                self._set_choice(chain, token)
        self._populate()

    def _ignore_selected(self) -> None:
        for index in self.table.selectionModel().selectedRows():
            cell = self.table.item(index.row(), 2)
            if cell is not None:
                self._set_choice(
                    tuple(cell.data(Qt.ItemDataRole.UserRole)), "IRRELEVANT",
                )
        self._populate()

    def _confirm(self) -> None:
        if set(self.choices) != {chain for _name, chain in self._rows}:
            QMessageBox.warning(
                self, tr("clm_v2_classification.title"),
                tr("clm_v2_classification.incomplete"),
            )
            return
        self.result_value = dict(self.choices)
        self.accept()


def collect_clm_character_classifications(
    analysis: ClmIdentityAnalysis, decisions: ClmIdentityDecisionSet,
    parent: QWidget,
    *, target_store: IdentityV2Store | None = None,
    include_chains: set[tuple[str, ...]] | None = None,
) -> Mapping[tuple[str, ...], CharacterImportChoice] | None:
    dialog = ClmV2ClassificationDialog(
        analysis, decisions, parent, target_store=target_store,
        include_chains=include_chains)
    return dialog.result_value if dialog.exec() == QDialog.DialogCode.Accepted else None
