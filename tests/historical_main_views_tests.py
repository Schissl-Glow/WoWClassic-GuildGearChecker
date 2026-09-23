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

from app.GuildGearChecker import GuildModel
from app.GuildGearCheckerQt import GuildGearCheckerQt


class HistoricalMainWindow(GuildGearCheckerQt):
    def _load_autosave_or_seed(self) -> None:
        self.model.new_empty()

    def autosave(self) -> None:
        return


class HistoricalMainViewsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.model = GuildModel()
        self.model.new_empty()

    def add_main(self, name: str):
        member = self.model.add_member(name, "Test")
        self.model.assign_character_type(member.id, "main", None, "not_set")
        return member, self.model.find_player_by_id(member.playerId)

    def add_twink(self, main, name: str):
        member = self.model.add_member(name, "Test")
        self.model.assign_character_type(member.id, "twink", main.id, "not_set")
        return member

    def test_manual_bench_uses_active_main_and_keeps_historical_bench(self) -> None:
        first, player = self.add_main("First")
        second = self.add_twink(first, "Second")
        third = self.add_twink(first, "Third")
        self.model.mark_main_dead_with_successor(first.id, second.id, "2026-08-01")
        self.model.mark_main_dead_with_successor(second.id, third.id, "2026-08-02")

        historical = self.model.create_raid("2026-08-03", "Historical", raid_type="ZG")
        historical.status = "recorded"
        self.model.set_historical_raid_bench_members(historical.id, [first.id])
        historical_before = [
            entry.to_dict() for entry in self.model.attendance_for_raid(historical.id)
        ]

        candidates = self.model.bench_candidates_for_date("2026-09-01")
        self.assertEqual(
            [(candidate_player.playerId, member.id) for candidate_player, member in candidates],
            [(player.playerId, third.id)],
        )
        current = self.model.create_raid("2026-09-01", "Current", raid_type="MC")
        current.status = "recorded"
        self.model.set_raid_bench_players(current.id, [player.playerId])
        current_entry = self.model.attendance_for_raid(current.id)[0]
        self.assertEqual(
            (current_entry.playerId, current_entry.memberId, current_entry.attendanceType),
            (player.playerId, third.id, "main"),
        )
        self.assertEqual(
            [entry.to_dict() for entry in self.model.attendance_for_raid(historical.id)],
            historical_before,
        )

    def test_player_without_living_main_is_not_manual_bench_candidate(self) -> None:
        main, player = self.add_main("Historical")
        self.model.mark_main_dead_with_successor(main.id, death_date="2026-08-01")
        raid = self.model.create_raid("2026-09-01", "Current", raid_type="MC")
        raid.status = "recorded"

        self.assertNotIn(
            player.playerId,
            {candidate.playerId for candidate, _member
             in self.model.bench_candidates_for_date(raid.date)},
        )
        with self.assertRaises(ValueError):
            self.model.set_raid_bench_players(raid.id, [player.playerId])
        self.assertEqual(self.model.attendance_for_raid(raid.id), [])

    def test_dead_only_player_remains_visible_without_ui_mutation(self) -> None:
        with patch("app.GuildGearCheckerQt.read_suite_settings", return_value={}):
            window = HistoricalMainWindow()
        self.addCleanup(window.deleteLater)
        main = window.model.add_member("Historical Main", "Test")
        window.model.assign_character_type(main.id, "main", None, "not_set")
        player = window.model.find_player_by_id(main.playerId)
        raid = window.model.create_raid("2026-08-01", "Historic", raid_type="ZG")
        window.model.import_raid_attendance(raid.id, [main.name])
        window.model.mark_main_dead_with_successor(main.id, death_date="2026-08-02")
        before = (
            main.id, main.playerId, main.characterType, main.lifeStatus,
            [entry.to_dict() for entry in window.model.raid_attendance],
        )

        window.attendance_active_only.setChecked(False)
        window.matrix_active_only.setChecked(False)
        window.refresh_raid_statistics(force=True)
        window.refresh_raid_matrix(force=True)

        statistics_rows = {
            str(window.raid_stats_table.item(row, 0).data(Qt.ItemDataRole.UserRole))
            for row in range(window.raid_stats_table.rowCount())
        }
        matrix_rows = {
            str(window.raid_matrix_players.item(row, 0).data(Qt.ItemDataRole.UserRole))
            for row in range(window.raid_matrix_players.rowCount())
        }
        self.assertIn(player.playerId, statistics_rows)
        self.assertIn(player.playerId, matrix_rows)
        self.assertEqual(window._player_main_member(player.playerId).id, main.id)
        self.assertEqual(
            (
                main.id, main.playerId, main.characterType, main.lifeStatus,
                [entry.to_dict() for entry in window.model.raid_attendance],
            ),
            before,
        )


if __name__ == "__main__":
    unittest.main()
