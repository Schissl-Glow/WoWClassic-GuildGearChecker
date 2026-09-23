from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.GuildGearCheckerQt import GuildGearCheckerQt, tr


class StreakWindow(GuildGearCheckerQt):
    def _load_autosave_or_seed(self) -> None:
        self.model.new_empty()

    def autosave(self) -> None:
        return


class RaidStreakUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_player_and_character_views_show_both_streak_columns(self) -> None:
        with patch("app.GuildGearCheckerQt.read_suite_settings", return_value={}):
            window = StreakWindow()
        self.addCleanup(window.deleteLater)
        member = window.model.add_member("Streaker", "Test")
        window.model.assign_character_type(member.id, "main", None, "not_set")
        player = window.model.find_player_by_id(member.playerId)
        for day, status in ((1, "present"), (2, "bench")):
            raid = window.model.create_raid(f"2026-09-{day:02d}", "ZG", raid_type="ZG")
            window.model.import_raid_attendance(raid.id, [member.name])
            if status == "bench":
                window.model.set_raid_attendance_status(raid.id, player.playerId, "bench")

        headers = [window.raid_stats_table.horizontalHeaderItem(column).text()
                   for column in range(window.raid_stats_table.columnCount())]
        self.assertEqual(window.raid_stats_table.columnCount(), 10)
        self.assertIn(tr("raids.current_streak"), headers)
        self.assertIn(tr("raids.longest_streak"), headers)

        for mode, identifier in (("player", player.playerId), ("character", member.id)):
            index = window.attendance_view_mode.findData(mode)
            window.attendance_view_mode.setCurrentIndex(index)
            window.refresh_raid_statistics(force=True)
            row = next(
                row for row in range(window.raid_stats_table.rowCount())
                if str(window.raid_stats_table.item(row, 0).data(Qt.ItemDataRole.UserRole))
                == identifier
            )
            self.assertEqual(window.raid_stats_table.item(row, 7).text(), "2")
            self.assertEqual(window.raid_stats_table.item(row, 8).text(), "2")


if __name__ == "__main__":
    unittest.main()
