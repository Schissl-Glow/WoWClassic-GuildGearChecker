"""Qt workflow for creating a separate new Identity V2 guild from CLM Lua."""

from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog,
    QLabel, QMessageBox, QProgressDialog, QPushButton, QTabBar, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .clm_identity_v2_dialog import collect_clm_identity_decisions
from .clm_v2_classification_ui import collect_clm_character_classifications
from .clm_detection import identity_key, select_database
from .clm_models import ClmIntegrationError
from .clm_v2_initialization import (
    ClmV2SourceInspection, analyze_clm_v2_selection, build_clm_v2_characters,
    inspect_clm_v2_source, verify_existing_clm_characters,
)
from .i18n import tr
from .identity_v2 import IdentityV2Store, POINT_MODE_ETERNAL
from .clm_raid_v2_materialization import (
    clm_raid_attendance_difference, correct_clm_raid_attendance,
    materialize_clm_raids_into_identity_v2, review_clm_raids,
)
from .raid_attendance import RAID_TYPES
from .qt_row_hover import install_row_hover


def _busy(parent: QWidget, label: str) -> QProgressDialog:
    progress = QProgressDialog(parent)
    progress.setWindowTitle(tr("clm_v2_init.summary_title"))
    progress.setLabelText(label)
    progress.setRange(0, 0)
    progress.setCancelButton(None)
    progress.setMinimumDuration(0)
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.show()
    QApplication.processEvents()
    return progress


def _database_choice(parent: QWidget, inspection: ClmV2SourceInspection) -> str | None:
    if len(inspection.databases) == 1:
        return inspection.databases[0].database_id
    labels = [f"{item.guild_name} · {item.realm} · {item.database_id}"
              for item in inspection.databases]
    chosen, accepted = QInputDialog.getItem(
        parent, tr("clm_v2_init.database_title"), tr("clm_v2_init.database_prompt"),
        labels, 0, False,
    )
    if not accepted:
        return None
    return inspection.databases[labels.index(chosen)].database_id


def _project_database_choice(parent: QWidget, inspection: ClmV2SourceInspection,
                             store: IdentityV2Store) -> str | None:
    """Use the saved guild identity; review only ambiguous matching databases."""
    try:
        return select_database(
            inspection.databases, store.guildName, store.realm).database_id
    except ClmIntegrationError:
        matches = tuple(item for item in inspection.databases
                        if item.active
                        and identity_key(item.guild_name) == identity_key(store.guildName)
                        and identity_key(item.realm) == identity_key(store.realm))
        if not matches:
            raise
        return _database_choice(parent, replace(inspection, databases=matches))


def _roster_choice(parent: QWidget, inspection: ClmV2SourceInspection,
                   database_id: str, project_roster_name: str | None = None) -> str | None:
    rosters = inspection.eligible_rosters(database_id)
    if not rosters:
        raise ClmIntegrationError("Die gewählte CLM-Datenbank hat keinen aktiven DKP-Roster.")
    if len(rosters) == 1:
        return rosters[0].roster_id
    if project_roster_name:
        matching = [item for item in rosters
                    if identity_key(item.name) == identity_key(project_roster_name)]
        if len(matching) == 1:
            return matching[0].roster_id
    labels = [f"{item.name} · {item.roster_id}" for item in rosters]
    chosen, accepted = QInputDialog.getItem(
        parent, tr("clm_v2_init.roster_title"), tr("clm_v2_init.roster_prompt"),
        labels, 0, False,
    )
    if not accepted:
        return None
    return rosters[labels.index(chosen)].roster_id


class ClmRaidReviewDialog(QDialog):
    def __init__(
        self, store: IdentityV2Store, analysis, parent: QWidget,
        *, selection_only: bool = False,
        initial_selected_ids: set[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.working_store = store
        self.analysis = analysis
        self.selection_only = selection_only
        self.setWindowTitle("CLM-Raids prüfen")
        self.resize(1050, 560)
        self.rows = review_clm_raids(store, analysis)
        self._imported_raid_ids = {raid.clmRaidId for raid in store.raids
                                   if raid.clmRaidId}
        layout = QVBoxLayout(self)
        explanation = (
            "Zuerst gewünschte Raids auswählen. Abgewählte Raids lösen keine "
            "GUID-Klärung aus. Danach folgt der Raid-Review."
            if selection_only else
            "Raid-Typen prüfen. Haken bei Testeinträgen oder anderen nicht gewünschten "
            "Raids entfernen; sie bleiben unverändert."
        )
        layout.addWidget(QLabel(explanation))
        self.tabs = QTabBar(self)
        self.tabs.addTab("Neu")
        self.tabs.addTab("Bereits Importiert")
        layout.addWidget(self.tabs)
        self.table = QTableWidget(len(self.rows), 7, self)
        self.table.row_hover = install_row_hover(self.table)
        self.table.setHorizontalHeaderLabels(
            ("Datum", "CLM-Raid / Titel", "Teilnehmer", "Raid-Typ", "Status",
             "CLM-Raid-ID", "Importieren"))
        self.table.setMinimumWidth(800)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setColumnWidth(1, 270)
        self.table.setColumnWidth(5, 260)
        self.table.setColumnWidth(6, 95)
        self.table.horizontalHeader().moveSection(6, 0)
        row_height = max(38, self.table.fontMetrics().height() + 20)
        self.table.verticalHeader().setMinimumSectionSize(row_height)
        self.table.verticalHeader().setDefaultSectionSize(row_height)
        self.combos: dict[str, QComboBox] = {}
        self.import_items: dict[str, QTableWidgetItem] = {}
        for index, row in enumerate(self.rows):
            import_item = QTableWidgetItem()
            import_item.setFlags(
                (import_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                & ~Qt.ItemFlag.ItemIsEditable)
            import_item.setCheckState(
                Qt.CheckState.Checked if initial_selected_ids is None
                or row.clm_raid_id in initial_selected_ids else Qt.CheckState.Unchecked)
            import_item.setToolTip("Diesen Raid beim Refresh berücksichtigen")
            self.table.setItem(index, 6, import_item)
            self.import_items[row.clm_raid_id] = import_item
            for column, value in enumerate((row.date, row.name, str(row.participants),
                                            "", row.status, row.clm_raid_id)):
                if column != 3:
                    item = QTableWidgetItem(value)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(index, column, item)
            combo = QComboBox(self.table)
            combo.setMinimumHeight(max(34, combo.fontMetrics().height() + 16))
            combo.addItem("--", "")
            for raid_type in RAID_TYPES:
                combo.addItem(raid_type, raid_type)
            if row.raid_type in RAID_TYPES:
                combo.setCurrentIndex(combo.findData(row.raid_type))
            if (selection_only or row.status in ("bereits importiert", "Teilnehmer abweichend")
                    or import_item.checkState() != Qt.CheckState.Checked):
                combo.setEnabled(False)
            self.table.setCellWidget(index, 3, combo)
            self.table.setRowHeight(index, row_height)
            self.combos[row.clm_raid_id] = combo
            combo.currentIndexChanged.connect(
                lambda _index, row_index=index, review_row=row:
                self._update_status(row_index, review_row))
            self._show_raid_type_status(index, suggested=True)
        self.table.itemChanged.connect(self._import_choice_changed)
        layout.addWidget(self.table)
        self.message = QLabel("")
        layout.addWidget(self.message)
        buttons = QHBoxLayout()
        buttons.addStretch()
        import_button = QPushButton(
            "Auswahl fortsetzen" if selection_only else "Ausgewählte Raids übernehmen")
        import_button.clicked.connect(self._accept_if_complete)
        buttons.addWidget(import_button)
        self.correction_button = None
        if not selection_only and any(
                row.status == "Teilnehmer abweichend" for row in self.rows):
            self.correction_button = QPushButton("Raid-/Attendance-Korrektur öffnen")
            self.correction_button.clicked.connect(self._open_existing_correction)
            self.correction_button.setEnabled(any(
                row.status == "Teilnehmer abweichend"
                and self._raid_selected(row.clm_raid_id) for row in self.rows))
            buttons.addWidget(self.correction_button)
        later_button = QPushButton("Später / Abbrechen")
        later_button.clicked.connect(self.reject)
        buttons.addWidget(later_button)
        layout.addLayout(buttons)
        self.tabs.currentChanged.connect(self._show_tab)
        self._show_tab(0)

    def _tab_for_raid(self, clm_raid_id: str) -> int:
        return int(clm_raid_id in self._imported_raid_ids)

    def _show_tab(self, tab_index: int) -> None:
        for index, row in enumerate(self.rows):
            self.table.setRowHidden(
                index, self._tab_for_raid(row.clm_raid_id) != tab_index)

    def _open_existing_correction(self) -> None:
        selected = {index.row() for index in self.table.selectionModel().selectedRows()
                    if not self.table.isRowHidden(index.row())}
        conflicts = [(index, row) for index, row in enumerate(self.rows)
                     if row.status == "Teilnehmer abweichend"
                     and self._raid_selected(row.clm_raid_id)]
        target = next(((index, row) for index, row in conflicts if index in selected),
                      conflicts[0] if conflicts else None)
        if target is None:
            return
        index, row = target
        self.tabs.setCurrentIndex(self._tab_for_raid(row.clm_raid_id))
        try:
            added, removed = clm_raid_attendance_difference(
                self.working_store, self.analysis, row.clm_raid_id)
            members = {member.memberId: member.name
                       for member in self.working_store.members}
            owners = {member.clmGuid.casefold(): member.memberId
                      for member in self.working_store.members if member.clmGuid}
            owners.update((guid.casefold(), member_id)
                          for guid, member_id in
                          self.working_store.legacyClmGuidMemberMap.items())

            def describe(guids: tuple[str, ...]) -> str:
                return "\n".join(
                    f"• {members.get(owners.get(guid.casefold(), ''), '?')} ({guid})"
                    for guid in guids) or "–"

            message = (
                f"{row.date} · {row.name}\n\n"
                f"Neu laut CLM:\n{describe(added)}\n\n"
                f"Nicht mehr in CLM:\n{describe(removed)}\n\n"
                "CLM-Teilnehmer für diesen Raid übernehmen? "
                "Die Änderung wird erst mit dem gesamten Refresh gespeichert."
            )
            answer = QMessageBox.question(
                self, "CLM-Raidteilnehmer korrigieren", message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.working_store = correct_clm_raid_attendance(
                self.working_store, self.analysis, row.clm_raid_id)
        except ValueError as exc:
            QMessageBox.warning(self, "CLM-Raidteilnehmer korrigieren", str(exc))
            return
        self.rows = review_clm_raids(self.working_store, self.analysis)
        updated = self.rows[index]
        combo = self.combos[row.clm_raid_id]
        combo.setEnabled(updated.status != "bereits importiert")
        if updated.raid_type in RAID_TYPES and not combo.currentData():
            combo.setCurrentIndex(combo.findData(updated.raid_type))
        self._show_raid_type_status(index, suggested=True)
        if self.correction_button is not None:
            self.correction_button.setEnabled(any(
                item.status == "Teilnehmer abweichend"
                and self._raid_selected(item.clm_raid_id) for item in self.rows))
        self.message.setText("CLM-Teilnehmer für diesen Raid im Arbeitsstand korrigiert.")

    def _update_status(self, index: int, row) -> None:
        self._show_raid_type_status(index)
        self.message.setText("")

    def _raid_selected(self, clm_raid_id: str) -> bool:
        return self.import_items[clm_raid_id].checkState() == Qt.CheckState.Checked

    def selected_raid_ids(self) -> set[str]:
        return {row.clm_raid_id for row in self.rows
                if self._raid_selected(row.clm_raid_id)}

    def _import_choice_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 6:
            return
        row = self.rows[item.row()]
        self.combos[row.clm_raid_id].setEnabled(
            not self.selection_only and self._raid_selected(row.clm_raid_id)
            and row.status not in ("bereits importiert", "Teilnehmer abweichend"))
        self._show_raid_type_status(item.row(), suggested=True)
        if self.correction_button is not None:
            self.correction_button.setEnabled(any(
                row.status == "Teilnehmer abweichend"
                and self._raid_selected(row.clm_raid_id) for row in self.rows))
        self.message.setText("")

    def _show_raid_type_status(self, index: int, *, suggested: bool = False) -> None:
        row = self.rows[index]
        selected = self.combos[row.clm_raid_id].currentData()
        if not self._raid_selected(row.clm_raid_id):
            status = "Übersprungen"
        elif row.status in ("bereits importiert", "Teilnehmer abweichend"):
            status = row.status
        elif selected not in RAID_TYPES:
            status = "Typ fehlt"
        elif row.status == "Typ fehlt":
            status = "Typ vorgeschlagen" if suggested else "Typ gewählt"
        else:
            status = row.status
        self.table.item(index, 4).setText(status)

    def _accept_if_complete(self) -> None:
        if self.selection_only:
            self.accept()
            return
        conflicts = [row.clm_raid_id for row in self.rows
                     if row.status == "Teilnehmer abweichend"
                     and self._raid_selected(row.clm_raid_id)]
        if conflicts:
            first = next(index for index, row in enumerate(self.rows)
                         if row.clm_raid_id == conflicts[0])
            self.tabs.setCurrentIndex(self._tab_for_raid(conflicts[0]))
            self.table.setCurrentCell(first, 4)
            self.table.scrollToItem(
                self.table.item(first, 1),
                QAbstractItemView.ScrollHint.PositionAtCenter)
            self.message.setText(
                "Teilnehmer weichen ab. Bitte bestehende Raid-/Attendance-Korrektur "
                f"für Zeile {first + 1} verwenden ({len(conflicts)} offen).")
            return
        missing = [row.clm_raid_id for row in self.rows
                   if self._raid_selected(row.clm_raid_id)
                   and row.status != "bereits importiert"
                   and self.combos[row.clm_raid_id].currentData() not in RAID_TYPES]
        if missing:
            first = next(index for index, row in enumerate(self.rows)
                         if row.clm_raid_id == missing[0])
            row = self.rows[first]
            label = row.name or "ohne Titel"
            count_label = "Raid-Typ" if len(missing) == 1 else "Raid-Typen"
            self.message.setText(
                f"Noch {len(missing)} {count_label} offen. "
                f"Bitte Zeile {first + 1} wählen: {row.date} · {label}.")
            self.tabs.setCurrentIndex(self._tab_for_raid(row.clm_raid_id))
            self.table.setCurrentCell(first, 3)
            self.table.scrollToItem(
                self.table.item(first, 1),
                QAbstractItemView.ScrollHint.PositionAtCenter)
            self.combos[missing[0]].setFocus()
            return
        self.accept()

    def selected_types(self) -> dict[str, str]:
        return {row.clm_raid_id: self.combos[row.clm_raid_id].currentData()
                for row in self.rows if self._raid_selected(row.clm_raid_id)
                and row.status != "bereits importiert"}


def run_clm_v2_initialization(
    parent: QWidget, *, target_store: IdentityV2Store | None = None,
    on_characters_imported: Callable[[IdentityV2Store], None] | None = None,
    initial_store: IdentityV2Store | None = None,
    source_path: Path | str | None = None,
) -> IdentityV2Store | None:
    """Import characters first, then offer the same Lua's raids for separate review."""
    if initial_store is not None:
        initial_store.validate()
        if target_store is not None or initial_store.pointMode != POINT_MODE_ETERNAL:
            raise ValueError("Der CLM-Erstimport benötigt eine neue Eternal-DKP-Gilde.")
    if source_path is None:
        source_text, _filter = QFileDialog.getOpenFileName(
            parent, tr("clm_v2_init.source_title"), "",
            "ClassicLootManager.lua (*.lua);;Lua (*.lua)",
        )
    else:
        source_text = str(source_path)
    if not source_text:
        return None
    try:
        progress = _busy(parent, tr("clm_v2_init.busy_read"))
        try:
            inspection = inspect_clm_v2_source(Path(source_text))
        finally:
            progress.close()
        project_store = initial_store if initial_store is not None else target_store
        if project_store is not None and project_store.guildName and project_store.realm:
            database_id = _project_database_choice(parent, inspection, project_store)
        else:
            database_id = _database_choice(parent, inspection)
        if database_id is None:
            return None
        preferred_roster = None
        if project_store is not None:
            preferred_roster = project_store.clmRosterName or project_store.guildName
        roster_id = _roster_choice(parent, inspection, database_id, preferred_roster)
        if roster_id is None:
            return None

        progress = _busy(parent, tr("clm_v2_init.busy_analyze"))
        try:
            analysis = analyze_clm_v2_selection(inspection, database_id, roster_id)
        finally:
            progress.close()
        if target_store is None:
            decisions = collect_clm_identity_decisions(analysis.identity_analysis, parent)
            if decisions is None:
                return None
            classifications = collect_clm_character_classifications(
                analysis.identity_analysis, decisions, parent)
            if classifications is None:
                return None
            progress = _busy(parent, tr("clm_v2_init.busy_build"))
            try:
                characters = build_clm_v2_characters(
                    analysis, decisions, target_store=initial_store,
                    classifications=classifications,
                    require_classifications=True)
            finally:
                progress.close()
            if initial_store is not None:
                characters.guildName = initial_store.guildName
                characters.realm = initial_store.realm
                characters.pointMode = initial_store.pointMode
            database = inspection.database(database_id)
            selected = next(item for item in inspection.eligible_rosters(database_id)
                            if item.roster_id == roster_id)
            if not characters.guildName:
                characters.guildName = database.guild_name
            if not characters.realm:
                characters.realm = database.realm
            characters.clmLuaPath = str(Path(source_text).resolve())
            characters.clmDatabaseId = database_id
            characters.clmRosterId = roster_id
            characters.clmRosterName = selected.name
            characters.validate()
            if on_characters_imported is not None:
                on_characters_imported(characters)
        else:
            verify_existing_clm_characters(target_store, analysis)
            characters = copy.deepcopy(target_store)
            selected = next(item for item in inspection.eligible_rosters(database_id)
                            if item.roster_id == roster_id)
            characters.clmLuaPath = str(Path(source_text).resolve())
            characters.clmDatabaseId = database_id
            characters.clmRosterId = roster_id
            characters.clmRosterName = selected.name
            characters.validate()
        dialog = ClmRaidReviewDialog(characters, analysis, parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        progress = _busy(parent, tr("clm_v2_init.busy_raids"))
        try:
            return materialize_clm_raids_into_identity_v2(
                dialog.working_store, analysis, dialog.selected_types(),
                selected_raid_ids=dialog.selected_raid_ids())
        finally:
            progress.close()
    except (OSError, ValueError, TypeError, KeyError) as exc:
        QMessageBox.critical(parent, tr("clm_v2_init.error_title"), str(exc))
        return None
