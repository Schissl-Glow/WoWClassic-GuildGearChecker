# -*- coding: utf-8 -*-
"""Focused smoke checks for the Raid > Teilnahme toolbar and matrix UI."""
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
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.GuildGearCheckerQt import CLASS_COLORS, GuildGearCheckerQt
from app.raid_attendance import RaidAttendance


class AttendanceSmokeWindow(GuildGearCheckerQt):
    def _load_autosave_or_seed(self) -> None:
        self.model.new_empty()
        self.members = []
        self.players = []
        for index in range(24):
            player = self.model.add_player(
                "Focus Player" if index == 0 else f"Player {index:02d}"
            )
            member = self.model.add_member(f"Character {index:02d}", "Smoke")
            member.className = "Warrior" if index == 0 else ""
            self.model.update_member_assignment(
                member.id, player.playerId, "main", "dps",
            )
            self.players.append(player)
            self.members.append(member)

        self.model.attendance_tracking_start_date = "2026-09-01"
        self.raid_with_logs = self.model.create_raid(
            "2026-09-10", "Blackwing Lair Full Name", "https://example.invalid/logs", "BWL",
        )
        self.raid_with_logs.status = "recorded"
        self.raid_second = self.model.create_raid(
            "2026-09-03", "Molten Core", "", "MC",
        )
        self.raid_second.status = "recorded"

        for index, (player, member) in enumerate(zip(self.players, self.members)):
            if index < 2:
                self.model.raid_attendance.append(RaidAttendance(
                    id=f"matrix-first-{index}",
                    raidId=self.raid_with_logs.id,
                    playerId=player.playerId,
                    memberId=member.id,
                    attendanceType="main",
                    playerNameSnapshot=player.playerName,
                    characterNameSnapshot=member.name,
                    status="present" if index == 0 else "bench",
                ))
            self.model.raid_attendance.append(RaidAttendance(
                id=f"matrix-second-{index}",
                raidId=self.raid_second.id,
                playerId=player.playerId,
                memberId=member.id,
                attendanceType="main",
                playerNameSnapshot=player.playerName,
                characterNameSnapshot=member.name,
                status="present",
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
        window = AttendanceSmokeWindow()
    window._portrait_timer.stop()
    window._grabber_actions_timer.stop()
    try:
        window.resize(1200, 760)
        window.show()
        window.switch_page("raid")
        window.raid_subtabs.setCurrentWidget(window.attendance_page)
        window.refresh_raid_matrix(force=True)
        app.processEvents()

        assert window.matrix_view_player_button.isChecked()
        assert window.raid_stats_table.rowCount() == 24
        assert window.raid_matrix_table.rowCount() == 24
        assert window.raid_matrix_table.columnCount() == 2
        assert window.raid_matrix_table.horizontalHeaderItem(0).toolTip().find(
            "Blackwing Lair Full Name"
        ) >= 0
        assert "2026-09-10" in window.raid_matrix_table.horizontalHeaderItem(0).toolTip()
        assert "Warcraft Logs" in window.raid_matrix_table.horizontalHeaderItem(0).toolTip()

        def stats_row_for(player_id: str) -> int:
            return next(
                row for row in range(window.raid_stats_table.rowCount())
                if window.raid_stats_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == player_id
            )

        present_row = stats_row_for(window.players[0].playerId)
        bench_row = stats_row_for(window.players[1].playerId)
        absent_row = stats_row_for(window.players[2].playerId)
        assert window.raid_stats_table.item(present_row, 0).foreground().color().name() == CLASS_COLORS["Warrior"].lower()
        assert window.raid_matrix_table.item(present_row, 0).background().color().name() == "#248447"
        assert window.raid_matrix_table.item(bench_row, 0).background().color().name() == "#b18420"
        assert window.raid_matrix_table.item(absent_row, 0).background().color().name() == "#11161d"

        assert window.attendance_matrix_split.objectName() == "attendanceMatrixSplit"
        assert window.matrix_toggle_button.objectName() == "matrixToggleButton"
        stats_header = window.raid_stats_table.horizontalHeader()
        assert all(
            stats_header.sectionResizeMode(column).name == "Interactive"
            for column in range(window.raid_stats_table.columnCount())
        )
        chosen_widths = {0: 205, 1: 135, 8: 155, 9: 185}
        for column, width in chosen_widths.items():
            window.raid_stats_table.setColumnWidth(column, width)
        app.processEvents()
        window.refresh_raid_matrix(force=True)
        assert all(
            window.raid_stats_table.columnWidth(column) == width
            for column, width in chosen_widths.items()
        )
        window.raid_matrix_table.verticalScrollBar().setValue(120)
        app.processEvents()
        assert window.raid_stats_table.verticalScrollBar().value() == 120

        assert window.matrix_view_character_button.isVisible()
        window.matrix_view_character_button.click()
        app.processEvents()
        assert window.matrix_view_character_button.isChecked()
        assert window.matrix_subject.currentData() == ""
        assert window.raid_stats_table.rowCount() == 24
        window.matrix_view_player_button.click()
        app.processEvents()

        search = window.matrix_player_search
        with patch.object(window, "refresh_raid_matrix", wraps=window.refresh_raid_matrix) as refresh:
            search.setText("Focus")
            assert refresh.call_count == 0
            QTest.qWait(460)
            assert refresh.call_count == 1
        assert window.raid_stats_table.rowCount() == 1

        with patch.object(window, "refresh_raid_matrix", wraps=window.refresh_raid_matrix) as refresh:
            window.matrix_category_filter.setCurrentIndex(1)
            assert refresh.call_count == 1

        print("Qt Attendance UI Smoke: OK")
    finally:
        window._attendance_text_filter_timer.stop()
        window.hide()
        window.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    run()
