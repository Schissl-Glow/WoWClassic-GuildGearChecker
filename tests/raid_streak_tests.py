from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.GuildGearChecker import GuildModel
from app.raid_attendance import Raid, RaidAttendance, calculate_statistics


class RaidStreakTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = GuildModel()
        self.model.new_empty()
        self.main = self.model.add_member("Main", "Test")
        self.model.assign_character_type(self.main.id, "main", None, "not_set")
        self.player = self.model.find_player_by_id(self.main.playerId)

    def raid(self, raid_date: str, status: str | None, *, raid_type: str = "ZG"):
        raid = self.model.create_raid(raid_date, raid_type, raid_type=raid_type)
        self.model.import_raid_attendance(
            raid.id, [self.main.name] if status is not None else [],
        )
        if status == "bench":
            self.model.set_raid_attendance_status(raid.id, self.player.playerId, "bench")
        return raid

    def character_stats(self, member_id: str, **filters):
        return calculate_statistics(
            self.player.playerId, self.model.raids, self.model.raid_attendance,
            self.model.attendance_tracking_start_date,
            self.player.membershipStartDate, self.player.membershipEndDate,
            member_id=member_id, **filters,
        )

    def test_present_bench_and_missing_entries_define_both_streaks(self) -> None:
        for day, status in enumerate(
                ("present", "bench", "present", None, "present", "bench"), 1):
            self.raid(f"2026-09-{day:02d}", status)

        player = self.model.attendance_statistics_for_player(self.player.playerId)
        character = self.character_stats(self.main.id)

        self.assertEqual((player.current_streak, player.longest_streak), (2, 3))
        self.assertEqual((character.current_streak, character.longest_streak), (2, 3))
        self.assertEqual((player.total_attendances, player.bench_attendances), (5, 2))

    def test_last_absence_and_no_eligible_raids_produce_zero_current(self) -> None:
        self.raid("2026-09-01", "present")
        self.raid("2026-09-02", "bench")
        self.raid("2026-09-03", None)

        stats = self.model.attendance_statistics_for_player(self.player.playerId)
        empty = self.model.attendance_statistics_for_player(
            self.player.playerId, start_date="2027-01-01",
        )

        self.assertEqual((stats.current_streak, stats.longest_streak), (0, 2))
        self.assertEqual((empty.current_streak, empty.longest_streak), (0, 0))

    def test_life_status_does_not_change_historical_character_streak(self) -> None:
        self.raid("2026-09-01", "present")
        self.raid("2026-09-02", "bench")
        before = self.character_stats(self.main.id)
        self.model.set_member_life_status(self.main.id, "inactive")
        inactive = self.character_stats(self.main.id)
        self.model.set_member_life_status(self.main.id, "dead")
        dead = self.character_stats(self.main.id)

        self.assertEqual((before.current_streak, before.longest_streak), (2, 2))
        self.assertEqual((inactive.current_streak, inactive.longest_streak), (2, 2))
        self.assertEqual((dead.current_streak, dead.longest_streak), (2, 2))

    def test_player_streak_continues_across_member_ids_but_character_does_not(self) -> None:
        twink = self.model.add_member("New Main", "Test")
        self.model.assign_character_type(twink.id, "twink", self.main.id, "not_set")
        self.raid("2026-09-01", "present")
        self.raid("2026-09-02", "bench")
        self.model.mark_main_dead_with_successor(self.main.id, twink.id)
        third = self.model.create_raid("2026-09-03", "ZG", raid_type="ZG")
        self.model.import_raid_attendance(third.id, [twink.name])

        player = self.model.attendance_statistics_for_player(self.player.playerId)
        old_character = self.character_stats(self.main.id)
        new_character = self.character_stats(twink.id)

        self.assertEqual((player.current_streak, player.longest_streak), (3, 3))
        self.assertEqual((old_character.current_streak, old_character.longest_streak), (0, 2))
        self.assertEqual((new_character.current_streak, new_character.longest_streak), (1, 1))

    def test_same_name_member_ids_and_duplicate_player_entries_remain_distinct(self) -> None:
        old = self.main
        old.name = "Same"
        current = self.model.add_member("Other", "Test")
        self.model.assign_character_type(current.id, "twink", old.id, "not_set")
        current.name = "Same"
        raid = Raid("r1", "2026-09-01", "ZG", status="recorded", raidType="ZG")
        entries = [
            RaidAttendance("a1", raid.id, self.player.playerId, old.id, "main",
                           self.player.playerName, old.name, "present"),
            RaidAttendance("a2", raid.id, self.player.playerId, current.id, "twink",
                           self.player.playerName, current.name, "bench"),
        ]

        player = calculate_statistics(self.player.playerId, [raid], entries, raid.date)
        old_stats = calculate_statistics(
            self.player.playerId, [raid], entries, raid.date, member_id=old.id,
        )
        current_stats = calculate_statistics(
            self.player.playerId, [raid], entries, raid.date, member_id=current.id,
        )

        self.assertEqual((player.current_streak, player.longest_streak), (1, 1))
        self.assertEqual((old_stats.current_streak, current_stats.current_streak), (1, 1))

    def test_period_type_and_category_filters_scope_streaks(self) -> None:
        self.raid("2026-09-01", "present", raid_type="ZG")
        self.raid("2026-09-02", None, raid_type="MC")
        self.raid("2026-09-03", "bench", raid_type="ZG")
        self.raid("2026-09-04", "present", raid_type="BWL")

        period = self.model.attendance_statistics_for_player(
            self.player.playerId, start_date="2026-09-03",
        )
        raid_type = self.model.attendance_statistics_for_player(
            self.player.playerId, raid_type="ZG",
        )
        category = self.model.attendance_statistics_for_player(
            self.player.playerId, category="40er",
        )

        self.assertEqual((period.current_streak, period.longest_streak), (2, 2))
        self.assertEqual((raid_type.current_streak, raid_type.longest_streak), (2, 2))
        self.assertEqual((category.current_streak, category.longest_streak), (1, 1))

    def test_same_date_order_is_deterministic(self) -> None:
        present = Raid("r-a", "2026-09-01", "A", status="recorded", raidType="ZG")
        absent = Raid("r-b", "2026-09-01", "B", status="recorded", raidType="ZG")
        entry = RaidAttendance(
            "a1", present.id, self.player.playerId, self.main.id, "main",
            self.player.playerName, self.main.name, "present",
        )
        first = calculate_statistics(
            self.player.playerId, [absent, present], [entry], present.date,
        )
        second = calculate_statistics(
            self.player.playerId, [present, absent], [entry], present.date,
        )
        self.assertEqual(
            (first.current_streak, first.longest_streak),
            (second.current_streak, second.longest_streak),
        )
        self.assertEqual((first.current_streak, first.longest_streak), (0, 1))

    def test_save_load_keeps_streaks_and_does_not_mutate_attendance(self) -> None:
        self.raid("2026-09-01", "present")
        self.raid("2026-09-02", "bench")
        attendance_before = [entry.to_dict() for entry in self.model.raid_attendance]
        before = self.model.attendance_statistics_for_player(self.player.playerId)
        with tempfile.TemporaryDirectory(prefix="ggc-streak-") as folder:
            path = Path(folder) / "project.ggc"
            self.model.save(path, backup=False)
            restored = GuildModel()
            restored.load(path)
        after = restored.attendance_statistics_for_player(self.player.playerId)

        self.assertEqual((after.current_streak, after.longest_streak),
                         (before.current_streak, before.longest_streak))
        self.assertEqual([entry.to_dict() for entry in self.model.raid_attendance],
                         attendance_before)


if __name__ == "__main__":
    unittest.main()
