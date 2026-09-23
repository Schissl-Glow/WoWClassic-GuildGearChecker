# -*- coding: utf-8 -*-
"""Focused UI checks for the single Raid presentation PoC."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["GGC_DISABLE_ICON_DOWNLOAD"] = "1"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.GuildGearCheckerQt import GuildGearCheckerQt, RaidPointAdjustmentDialog
from app.raid_attendance import RaidAttendance


class RaidSmokeWindow(GuildGearCheckerQt):
    def _load_autosave_or_seed(self) -> None:
        self.model.new_empty()
        self.player = self.model.add_player("RaidSmoke Player")
        self.member = self.model.add_member("RaidSmoke Warrior", "Smoke")
        self.member.className = "Warrior"
        self.model.update_member_assignment(
            self.member.id, self.player.playerId, "main", "dps",
        )
        self.raid = self.model.create_raid(
            "2026-09-18", "Blackwing Lair", "https://example.invalid/logs", "BWL",
        )
        self.raid.status = "recorded"
        self.model.raid_attendance.append(RaidAttendance(
            id="raid-smoke-attendance", raidId=self.raid.id,
            playerId=self.player.playerId, memberId=self.member.id,
            attendanceType="main", playerNameSnapshot=self.player.playerName,
            characterNameSnapshot=self.member.name, status="present",
        ))

    def _apply_character_cache_once(self) -> None:
        return

    def autosave(self) -> None:
        return


def run() -> None:
    app = QApplication.instance() or QApplication([])
    with (
        patch("app.GuildGearCheckerQt.read_suite_settings", return_value={}),
        patch("app.GuildGearCheckerQt.update_suite_settings"),
    ):
        window = RaidSmokeWindow()
    window._portrait_timer.stop()
    window._grabber_actions_timer.stop()
    try:
        window.show()
        app.processEvents()
        window.switch_page("raid")
        window.raid_subtabs.setCurrentWidget(window.raids_page)
        window.refresh_raids(force=True)
        app.processEvents()

        assert not hasattr(window, "raid_presentation_group")
        assert not hasattr(window, "raid_view_stack")
        selected_id = window._selected_raid().id
        raid_table = window.raid_table
        participant_table = window.raid_participants_table
        selected_row = window.raid_table.selectionModel().selectedRows()[0].row()
        assert selected_id == window.raid.id
        assert window.raid_table.item(selected_row, 0).data(Qt.ItemDataRole.UserRole) == selected_id
        assert participant_table.rowCount() == 1
        assert window.raid_create_button.isVisible()
        assert window.raid_bulk_import_button.isVisible()
        assert window.raid_edit_button.isVisible()
        assert window.raid_reset_button.isVisible()
        assert window.raid_delete_button.isVisible()
        assert window.raid_splitter.count() == 2
        assert window.selected_raid_header.isVisible()
        assert window.raid_header_date.text() == window.raid.date
        assert window.raid_header_type.text() == window.raid.raidType
        assert window.raid_header_name.text() == window.raid.name
        assert window.raid_header_count.text() == "1 Teilnehmer"
        assert window.raid_header_status.text()
        assert not window.raid_header_logs.isHidden()
        assert window.raid_participants_table.item(0, 1).foreground().color().name() == "#c69b6d"
        assert window.raid_toggle_bench_button.isVisible()
        assert window.raid_participants_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == window.player.playerId

        for table in (window.raid_table, window.raid_participants_table):
            header = table.horizontalHeader()
            assert all(
                header.sectionResizeMode(column).name == "Interactive"
                for column in range(table.columnCount())
            )
        window.raid_table.setColumnWidth(2, 355)
        window.raid_participants_table.setColumnWidth(1, 370)
        window.refresh_raids(force=True)
        window.refresh_raid_participants()
        assert window.raid_table.columnWidth(2) == 355
        assert window.raid_participants_table.columnWidth(1) == 370
        adjustment_dialog = RaidPointAdjustmentDialog(window, window.model, window.raid)
        assert all(
            adjustment_dialog.table.horizontalHeader().sectionResizeMode(column).name == "Interactive"
            for column in range(adjustment_dialog.table.columnCount())
        )
        adjustment_dialog.close()
        adjustment_dialog.deleteLater()
        app.processEvents()

        window.raid_subtabs.setCurrentWidget(window.attendance_page)
        app.processEvents()
        assert window.raid_table is raid_table
        assert window.raid_participants_table is participant_table
        assert window._selected_raid().id == selected_id
        window.refresh_raid_matrix(force=True)
        matrix = window.raid_matrix_table
        assert matrix.horizontalHeader().sectionResizeMode(0).name == "Interactive"
        matrix.setColumnWidth(0, 131)
        app.processEvents()
        assert matrix.columnWidth(0) == 131
        later = window.model.create_raid(
            "2026-09-25", "Later Raid", "", "MC",
        )
        later.status = "recorded"
        window.refresh_raid_matrix(force=True)
        old_index = next(
            index for index, raid in enumerate(window._matrix_raids)
            if raid.id == window.raid.id
        )
        later_index = next(
            index for index, raid in enumerate(window._matrix_raids)
            if raid.id == later.id
        )
        assert old_index != 0 and later_index == 0
        assert matrix.columnWidth(old_index) == 131
        assert matrix.columnWidth(later_index) == 74

        print("Qt Raid UI PoC Smoke: OK")
    finally:
        if hasattr(window, "_attendance_text_filter_timer"):
            window._attendance_text_filter_timer.stop()
        window._graveyard_zoom_timer.stop()
        window._graveyard_zoom_save_timer.stop()
        window.hide()
        window.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    run()
