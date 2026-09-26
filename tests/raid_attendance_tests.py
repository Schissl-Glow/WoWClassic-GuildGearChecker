"""Focused model, persistence, CSV, statistics and UI tests for raid attendance."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]


class RaidAttendanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO_ROOT))
        global csv_import, g, raid_domain
        from app import GuildGearChecker as g
        from app import csv_import, raid_attendance as raid_domain

    def setUp(self):
        self.model = g.GuildModel()
        self.model.new_empty()

    def add_main(self, name="Main", player_name="Player"):
        member = self.model.add_member(name, "Test")
        self.model.assign_character_type(member.id, "main", None, "not_set")
        player = self.model.find_player_by_id(member.playerId)
        player.playerName = player_name
        return member, player

    def add_twink(self, main, name="Twink"):
        member = self.model.add_member(name, "Test")
        self.model.assign_character_type(member.id, "twink", main.id, "not_set")
        return member

    def test_raid_create_edit_delete_multiple_and_stable_ids(self):
        first = self.model.create_raid("2026-09-01", "Molten Core")
        second = self.model.create_raid(
            "2026-09-08", "Blackwing Lair", "https://classic.warcraftlogs.com/reports/abc",
        )
        self.assertNotEqual(first.id, second.id)
        self.assertRegex(first.id, r"^r_[0-9a-f]{32}$")
        self.assertEqual(self.model.attendance_tracking_start_date, "2026-09-01")
        self.model.update_raid(first.id, "2026-09-02", "MC", "https://warcraftlogs.com/reports/xyz")
        self.assertEqual((first.date, first.name), ("2026-09-02", "MC"))
        main, _player = self.add_main()
        self.model.import_raid_attendance(first.id, [main.name])
        attendance_id = self.model.attendance_for_raid(first.id)[0].id
        self.assertRegex(attendance_id, r"^a_[0-9a-f]{32}$")
        self.model.delete_raid(first.id)
        self.assertEqual([raid.id for raid in self.model.raids], [second.id])
        self.assertEqual(self.model.attendance_for_raid(first.id), [])

    def test_tracking_start_initializes_and_only_moves_to_earlier_raid(self):
        self.model.create_raid("2026-09-12", "First")
        self.assertEqual(self.model.attendance_tracking_start_date, "2026-09-12")

        self.model.create_raid("2026-09-19", "Later")
        self.assertEqual(self.model.attendance_tracking_start_date, "2026-09-12")

        self.model.create_raid("2026-09-05", "Backfilled")
        self.assertEqual(self.model.attendance_tracking_start_date, "2026-09-05")

    def test_backfilled_raid_is_relevant_without_membership_start(self):
        main, player = self.add_main()
        first = self.model.create_raid("2026-09-12", "First")
        self.model.import_raid_attendance(first.id, [main.name])
        existing_attendance = self.model.attendance_for_raid(first.id)[0].to_dict()

        backfilled = self.model.create_raid("2026-09-05", "Backfilled")
        self.model.import_raid_attendance(backfilled.id, [main.name])

        stats = self.model.attendance_statistics_for_player(player.playerId)
        self.assertIsNone(player.membershipStartDate)
        self.assertIsNone(player.membershipEndDate)
        self.assertEqual(self.model.attendance_tracking_start_date, "2026-09-05")
        self.assertEqual((stats.eligible_raids, stats.total_attendances), (2, 2))
        self.assertEqual(self.model.attendance_for_raid(first.id)[0].to_dict(), existing_attendance)

    def test_membership_start_still_limits_backfilled_raid(self):
        main, player = self.add_main()
        self.model.set_player_membership(player.playerId, "2026-09-10", None)
        first = self.model.create_raid("2026-09-12", "First")
        self.model.import_raid_attendance(first.id, [main.name])
        backfilled = self.model.create_raid("2026-09-05", "Backfilled")
        self.model.import_raid_attendance(backfilled.id, [main.name])

        stats = self.model.attendance_statistics_for_player(player.playerId)
        self.assertEqual(player.membershipStartDate, "2026-09-10")
        self.assertIsNone(player.membershipEndDate)
        self.assertEqual(self.model.attendance_tracking_start_date, "2026-09-05")
        self.assertEqual((stats.eligible_raids, stats.total_attendances), (1, 1))

    def test_raid_date_edit_keeps_attendance_and_recalculates_statistics(self):
        main, player = self.add_main()
        self.model.set_player_membership(player.playerId, "2026-09-05", None)
        raid = self.model.create_raid("2026-09-10", "MC")
        self.model.attendance_tracking_start_date = "2026-09-01"
        self.model.import_raid_attendance(raid.id, [main.name])
        entry_id = self.model.attendance_for_raid(raid.id)[0].id
        self.assertEqual(self.model.attendance_statistics_for_player(player.playerId).eligible_raids, 1)
        self.model.update_raid(raid.id, "2026-09-02", "MC edited")
        self.assertEqual(self.model.attendance_for_raid(raid.id)[0].id, entry_id)
        self.assertEqual(self.model.attendance_statistics_for_player(player.playerId).eligible_raids, 0)

    def test_draft_does_not_count_recorded_does_and_zero_is_safe(self):
        main, player = self.add_main()
        raid = self.model.create_raid("2026-09-01", "MC")
        empty = self.model.attendance_statistics_for_player(player.playerId)
        self.assertEqual((empty.eligible_raids, empty.attendance_percent), (0, 0))
        self.model.import_raid_attendance(raid.id, [main.name])
        stats = self.model.attendance_statistics_for_player(player.playerId)
        self.assertEqual(
            (stats.eligible_raids, stats.main_attendances, stats.total_attendances,
             stats.absences, stats.attendance_percent),
            (1, 1, 1, 0, 100),
        )

    def test_shared_csv_parser_and_existing_member_import(self):
        text = 'Name;Amount\nBífi;1\n"Ánníe";2\nBÍFI;3\n'
        self.assertEqual(g.detect_csv_names(text), ["Bífi", "Ánníe"])
        self.assertIs(g.detect_csv_names, csv_import.detect_csv_names)
        self.assertEqual(csv_import.decode_csv_bytes(text.encode("cp1252")), text)
        created = self.model.import_active_members(g.detect_csv_names(text), "Warcraft Logs CSV")
        self.assertEqual([member.name for member in created], ["Bífi", "Ánníe"])

    def test_main_twink_and_duplicate_player_resolution_prefers_main(self):
        main, player = self.add_main("Waltordin", "Walt")
        first_twink = self.add_twink(main, "Waltmage")
        second_twink = self.add_twink(main, "Waltrogue")
        raid = self.model.create_raid("2026-09-01", "MC")
        summary = self.model.import_raid_attendance(
            raid.id, [first_twink.name, main.name, second_twink.name, main.name],
        )
        entries = self.model.attendance_for_raid(raid.id)
        self.assertEqual(len(entries), 1)
        self.assertEqual(
            (entries[0].playerId, entries[0].memberId, entries[0].attendanceType,
             entries[0].playerNameSnapshot, entries[0].characterNameSnapshot),
            (player.playerId, main.id, "main", "Walt", "Waltordin"),
        )
        self.assertTrue(summary["merged"])

    def test_multiple_twinks_count_once_as_twink(self):
        main, player = self.add_main()
        first = self.add_twink(main, "TwinkOne")
        second = self.add_twink(main, "TwinkTwo")
        raid = self.model.create_raid("2026-09-01", "MC")
        self.model.import_raid_attendance(raid.id, [first.name, second.name])
        entries = self.model.attendance_for_raid(raid.id)
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0].playerId, entries[0].attendanceType), (player.playerId, "twink"))

    def test_unknown_add_sets_membership_to_raid_date_and_discard_is_ignored(self):
        raid = self.model.create_raid("2025-04-03", "Historic")
        summary = self.model.import_raid_attendance(
            raid.id, ["Neumitglied", "Verworfen"],
            unknown_decisions={
                "Neumitglied": ("main", None),
                "Verworfen": ("discard", None),
            },
        )
        member = self.model.find_active_by_name("Neumitglied")
        player = self.model.find_player_by_id(member.playerId)
        self.assertEqual(member.characterType, "main")
        self.assertEqual(player.membershipStartDate, "2025-04-03")
        self.assertIsNone(self.model.find_active_by_name("Verworfen"))
        self.assertEqual((summary["added"], summary["discarded"], summary["participants"]), (1, 1, 1))

    def test_dead_same_name_is_not_reactivated_when_unknown_is_added(self):
        dead = self.model.add_member("Janos")
        dead.lifeStatus = "dead"
        created = self.model.import_active_members(["JANOS"], "Raid Attendance CSV")
        active = self.model.find_active_by_name("Janos")
        self.assertEqual([member.id for member in created], [active.id])
        self.assertNotEqual(active.id, dead.id)
        self.assertEqual(dead.lifeStatus, "dead")

    def test_unassigned_known_character_is_initialized_as_main(self):
        member = self.model.add_member("Unassigned")
        raid = self.model.create_raid("2026-09-01", "MC")
        resolution = self.model.resolve_raid_attendance([member.name])
        self.assertEqual(
            [(item.member_id, item.character_name) for item in resolution.unassigned_characters],
            [(member.id, member.name)],
        )
        summary = self.model.import_raid_attendance(raid.id, [member.name])
        migrated = self.model.find_by_id(member.id)
        entries = self.model.attendance_for_raid(raid.id)
        self.assertEqual(len(self.model.members), 1)
        self.assertEqual(migrated.characterType, "main")
        self.assertIsNotNone(migrated.playerId)
        self.assertEqual(len(self.model.players), 1)
        self.assertEqual((entries[0].memberId, entries[0].attendanceType), (member.id, "main"))
        self.assertEqual(summary["auto_initialized"], 1)
        self.assertEqual(raid.status, "recorded")

    def test_multiple_unassigned_members_are_initialized_atomically(self):
        first = self.model.add_member("First")
        second = self.model.add_member("Second")
        raid = self.model.create_raid("2026-09-01", "MC")
        summary = self.model.import_raid_attendance(raid.id, [first.name, second.name])
        self.assertEqual(summary["auto_initialized"], 2)
        self.assertEqual(len(self.model.members), 2)
        self.assertEqual(len(self.model.players), 2)
        self.assertTrue(all(member.characterType == "main" for member in self.model.members))
        self.assertEqual(len(self.model.attendance_for_raid(raid.id)), 2)

    def test_existing_main_and_twink_assignments_remain_unchanged(self):
        main, player = self.add_main("Main", "Player")
        twink = self.add_twink(main, "Twink")
        original = (main.playerId, main.characterType, twink.playerId, twink.characterType)
        raid = self.model.create_raid("2026-09-01", "MC")
        self.model.import_raid_attendance(raid.id, [main.name, twink.name])
        self.assertEqual(
            (main.playerId, main.characterType, twink.playerId, twink.characterType), original,
        )
        entry = self.model.attendance_for_raid(raid.id)[0]
        self.assertEqual((entry.playerId, entry.attendanceType), (player.playerId, "main"))

    def test_conflicting_assignment_is_not_overwritten(self):
        member = self.model.add_member("Conflict")
        unrelated = self.model.add_player("Unrelated")
        member.playerId = unrelated.playerId
        member.characterType = "not_set"
        raid = self.model.create_raid("2026-09-01", "MC")
        resolution = self.model.resolve_raid_attendance([member.name])
        self.assertEqual(resolution.ambiguous_names, (member.name,))
        with self.assertRaises(ValueError):
            self.model.import_raid_attendance(raid.id, [member.name])
        unchanged = self.model.find_by_id(member.id)
        self.assertEqual((unchanged.playerId, unchanged.characterType), (unrelated.playerId, "not_set"))
        self.assertEqual(self.model.attendance_for_raid(raid.id), [])

    def test_failed_import_rolls_back_automatic_main_initialization(self):
        member = self.model.add_member("Legacy")
        raid = self.model.create_raid("2026-09-01", "MC")
        with self.assertRaises(ValueError):
            self.model.import_raid_attendance(
                raid.id, [member.name, "Unknown"],
                unknown_decisions={"Unknown": ("twink", "missing-main")},
            )
        restored = self.model.find_by_id(member.id)
        self.assertEqual((restored.playerId, restored.characterType), (None, "not_set"))
        self.assertEqual((len(self.model.members), len(self.model.players)), (1, 0))
        self.assertEqual(self.model.attendance_for_raid(raid.id), [])
        self.assertEqual(raid.status, "draft")

    def test_unknown_character_can_be_added_as_twink(self):
        main, player = self.add_main("ExistingMain", "Existing Player")
        raid = self.model.create_raid("2026-09-01", "MC")
        summary = self.model.import_raid_attendance(
            raid.id, ["NewTwink"],
            unknown_decisions={"NewTwink": ("twink", main.id)},
        )
        twink = self.model.find_active_by_name("NewTwink")
        entry = self.model.attendance_for_raid(raid.id)[0]
        self.assertEqual((twink.playerId, twink.characterType), (player.playerId, "twink"))
        self.assertEqual(
            (entry.playerId, entry.memberId, entry.attendanceType, entry.characterNameSnapshot),
            (player.playerId, twink.id, "twink", "NewTwink"),
        )
        self.assertEqual((summary["added_twink"], summary["added_main"]), (1, 0))

    def test_unknown_character_can_be_discarded(self):
        raid = self.model.create_raid("2026-09-01", "MC")
        summary = self.model.import_raid_attendance(
            raid.id, ["Discarded"],
            unknown_decisions={"Discarded": ("discard", None)},
        )
        self.assertIsNone(self.model.find_active_by_name("Discarded"))
        self.assertEqual(self.model.players, [])
        self.assertEqual(self.model.attendance_for_raid(raid.id), [])
        self.assertEqual((summary["discarded"], summary["participants"]), (1, 0))

    def test_reimport_replaces_atomically_and_failure_keeps_previous(self):
        main, _player = self.add_main("First")
        other, _other_player = self.add_main("Second", "Other")
        raid = self.model.create_raid("2026-09-01", "MC")
        self.model.import_raid_attendance(raid.id, [main.name])
        self.model.import_raid_attendance(raid.id, [other.name])
        self.assertEqual(
            [entry.characterNameSnapshot for entry in self.model.attendance_for_raid(raid.id)],
            ["Second"],
        )
        before = [entry.to_dict() for entry in self.model.attendance_for_raid(raid.id)]
        with self.assertRaises(ValueError):
            self.model.import_raid_attendance(raid.id, ["Unknown"], ["NotInImport"])
        self.assertEqual(
            [entry.to_dict() for entry in self.model.attendance_for_raid(raid.id)], before,
        )
        with self.assertRaises(ValueError):
            csv_import.detect_csv_names("Amount\n1\n")
        self.assertEqual(
            [entry.to_dict() for entry in self.model.attendance_for_raid(raid.id)], before,
        )

    def test_reset_attendance_only_resets_selected_raid(self):
        first_main, player = self.add_main("First")
        second_main, _other = self.add_main("Second", "Other")
        first = self.model.create_raid("2026-09-01", "First Raid")
        second = self.model.create_raid("2026-09-08", "Second Raid")
        self.model.import_raid_attendance(first.id, [first_main.name])
        self.model.import_raid_attendance(second.id, [second_main.name])
        second_before = [
            entry.to_dict() for entry in self.model.attendance_for_raid(second.id)
        ]

        removed = self.model.reset_raid_attendance(first.id)

        self.assertEqual(removed, 1)
        self.assertEqual(self.model.attendance_for_raid(first.id), [])
        self.assertEqual(first.status, "draft")
        self.assertEqual(second.status, "recorded")
        self.assertEqual(
            [entry.to_dict() for entry in self.model.attendance_for_raid(second.id)],
            second_before,
        )
        self.assertEqual((first.name, first.date, first.warcraftLogsUrl),
                         ("First Raid", "2026-09-01", ""))
        stats = self.model.attendance_statistics_for_player(player.playerId)
        self.assertEqual(stats.eligible_raids, 1)

    def test_tracking_and_membership_bounds_are_inclusive(self):
        main, player = self.add_main()
        early = self.model.create_raid("2026-01-01", "Early")
        middle = self.model.create_raid("2026-01-02", "Middle")
        late = self.model.create_raid("2026-01-03", "Late")
        self.model.attendance_tracking_start_date = "2026-01-01"
        for raid in (early, middle, late):
            self.model.import_raid_attendance(raid.id, [main.name] if raid is not middle else [])
        self.model.set_player_membership(player.playerId, "2026-01-01", "2026-01-03")
        stats = self.model.attendance_statistics_for_player(player.playerId)
        self.assertEqual((stats.eligible_raids, stats.total_attendances, stats.absences), (3, 2, 1))
        self.model.set_player_membership(player.playerId, "2026-01-02", "2026-01-02")
        bounded = self.model.attendance_statistics_for_player(player.playerId)
        self.assertEqual((bounded.eligible_raids, bounded.total_attendances, bounded.absences), (1, 0, 1))

    def test_existing_player_without_membership_start_uses_tracking_start(self):
        main, player = self.add_main()
        before = self.model.create_raid("2026-01-01", "Before")
        after = self.model.create_raid("2026-02-01", "After")
        self.model.attendance_tracking_start_date = "2026-02-01"
        self.model.import_raid_attendance(before.id, [main.name])
        self.model.import_raid_attendance(after.id, [main.name])
        stats = self.model.attendance_statistics_for_player(player.playerId)
        self.assertEqual((stats.eligible_raids, stats.total_attendances), (1, 1))

    def test_total_and_twink_percent_share_same_denominator(self):
        main, player = self.add_main()
        twink = self.add_twink(main)
        self.model.attendance_tracking_start_date = "2026-01-01"
        for index in range(20):
            raid = self.model.create_raid(f"2026-01-{index + 1:02d}", f"Raid {index}")
            names = [main.name] if index < 14 else [twink.name] if index < 17 else []
            self.model.import_raid_attendance(raid.id, names)
        stats = self.model.attendance_statistics_for_player(player.playerId)
        self.assertEqual(
            (stats.main_attendances, stats.twink_attendances, stats.absences,
             stats.attendance_percent, stats.twink_percent),
            (14, 3, 3, 85, 15),
        )

    def test_statistics_keep_stored_assignment_for_existing_attendance(self):
        main, player = self.add_main("Main", "Player One")
        former_main, former_player = self.add_main("FormerMain", "Player Two")
        self.model.attendance_tracking_start_date = "2026-01-01"
        raid = self.model.create_raid("2026-01-02", "Raid")
        self.model.import_raid_attendance(raid.id, [former_main.name])

        self.model.update_member_assignment(
            former_main.id, player.playerId, "twink", "not_set",
        )
        stored = next(entry for entry in self.model.raid_attendance
                      if entry.memberId == former_main.id)
        self.assertEqual((stored.playerId, stored.attendanceType),
                         (former_player.playerId, "main"))

        stats = self.model.attendance_statistics_for_player(player.playerId)
        former_stats = self.model.attendance_statistics_for_player(former_player.playerId)
        character_stats = raid_domain.calculate_statistics(
            former_main.playerId or "", self.model.raids, self.model.raid_attendance,
            self.model.attendance_tracking_start_date,
            member_assignments={former_main.id: (player.playerId, "twink")},
            member_id=former_main.id,
        )
        self.assertEqual(stats.total_attendances, 0)
        self.assertEqual(
            (former_stats.main_attendances, former_stats.twink_attendances,
             former_stats.total_attendances),
            (1, 0, 1),
        )
        self.assertEqual(
            (character_stats.main_attendances, character_stats.twink_attendances,
             character_stats.total_attendances),
            (1, 0, 1),
        )

    def test_historical_dead_twink_stays_in_player_and_point_projections(self):
        from app.raid_points import build_point_history, character_points, player_points

        main, player_one = self.add_main("Main A", "Player A")
        twink = self.add_twink(main, "Twink B")
        other_main, player_two = self.add_main("Main C", "Player C")
        first = self.model.create_raid("2026-01-01", "Raid 1")
        second = self.model.create_raid("2026-01-08", "Raid 2")
        self.model.import_raid_attendance(first.id, [main.name, other_main.name])
        twink.lifeStatus = "dead"
        self.model.import_raid_attendance(second.id, [twink.name])

        self.model.raid_points.activate(
            [first.id, second.id], include_existing=True,
        )
        player_stats = self.model.attendance_statistics_for_player(player_one.playerId)
        twink_stats = raid_domain.calculate_statistics(
            player_one.playerId, self.model.raids, self.model.raid_attendance,
            self.model.attendance_tracking_start_date,
            player_one.membershipStartDate, player_one.membershipEndDate,
            member_id=twink.id,
        )
        history = build_point_history(
            self.model.raid_points, self.model.raids, self.model.raid_attendance,
        )

        self.assertEqual(len(self.model.players), 2)
        self.assertEqual(player_stats.total_attendances, 2)
        self.assertEqual(twink_stats.total_attendances, 1)
        self.assertEqual(character_points(
            self.model.raid_points, self.model.raids, self.model.raid_attendance, twink.id,
        ), 10)
        self.assertEqual(player_points(
            self.model.raid_points, self.model.raids, self.model.raid_attendance,
            player_one.playerId,
        ), 20)
        self.assertEqual(len(history), 3)

    def test_raid_type_derives_category_and_legacy_raid_stays_untyped(self):
        expected = {
            "ZG": "20er", "AQ20": "20er", "MC": "40er", "BWL": "40er",
            "AQ40": "40er", "Naxx": "40er", "Onyxia": "Onyxia",
            "World Boss": "World Boss",
        }
        for raid_type, category in expected.items():
            with self.subTest(raid_type=raid_type):
                raid = self.model.create_raid("2026-09-01", raid_type, raid_type=raid_type)
                self.assertEqual((raid.raidType, raid.category), (raid_type, category))
        legacy = raid_domain.Raid.from_dict({
            "id": "legacy", "date": "2026-09-01", "name": "Legacy",
        })
        self.assertEqual((legacy.raidType, legacy.category), ("", ""))
        self.assertNotIn("raidType", legacy.to_dict())

    def test_legacy_attendance_defaults_to_present_and_bench_is_separate(self):
        main, player = self.add_main()
        first = self.model.create_raid("2026-09-01", "MC", raid_type="MC")
        second = self.model.create_raid("2026-09-08", "BWL", raid_type="BWL")
        third = self.model.create_raid("2026-09-15", "Naxx", raid_type="Naxx")
        self.model.import_raid_attendance(first.id, [main.name])
        self.model.import_raid_attendance(second.id, [main.name])
        self.model.import_raid_attendance(third.id, [])
        self.model.set_raid_attendance_status(second.id, player.playerId, "bench")

        legacy = dict(self.model.attendance_for_raid(first.id)[0].to_dict())
        legacy.pop("status")
        self.assertEqual(raid_domain.RaidAttendance.from_dict(legacy).status, "present")
        stats = self.model.attendance_statistics_for_player(player.playerId)
        self.assertEqual(
            (stats.total_attendances, stats.bench_attendances, stats.absences,
             stats.attendance_percent, stats.last_attendance),
            (2, 1, 1, 67, "2026-09-08"),
        )

    def test_present_bench_and_absent_share_one_attendance_definition(self):
        main, player = self.add_main()
        raids = [
            self.model.create_raid(f"2026-10-{index:02d}", f"Raid {index}")
            for index in range(1, 11)
        ]
        for raid in raids[:8]:
            self.model.import_raid_attendance(raid.id, [main.name])
        for raid in raids[8:]:
            self.model.import_raid_attendance(raid.id, [])
        for raid in raids[6:8]:
            self.model.set_raid_attendance_status(raid.id, player.playerId, "bench")

        stats = self.model.attendance_statistics_for_player(player.playerId)

        self.assertEqual(stats.main_attendances, 6)
        self.assertEqual(stats.bench_attendances, 2)
        self.assertEqual(stats.total_attendances, 8)
        self.assertEqual(stats.absences, 2)
        self.assertEqual(stats.attendance_percent, 80)
        self.assertEqual(stats.last_attendance, "2026-10-08")

    def test_current_life_status_does_not_change_historical_attendance(self):
        inactive, inactive_player = self.add_main("Inactive", "Inactive Player")
        dead, dead_player = self.add_main("Dead", "Dead Player")
        raid = self.model.create_raid("2026-11-01", "Raid")
        self.model.import_raid_attendance(raid.id, [inactive.name, dead.name])

        self.model.set_member_life_status(inactive.id, "inactive")
        self.model.set_member_life_status(dead.id, "dead")

        self.assertEqual(
            self.model.attendance_statistics_for_player(
                inactive_player.playerId,
            ).total_attendances,
            1,
        )
        self.assertEqual(
            self.model.attendance_statistics_for_player(
                dead_player.playerId,
            ).total_attendances,
            1,
        )

    def test_former_main_keeps_historical_member_and_type(self):
        former_main, player = self.add_main("Former Main", "Player")
        replacement = self.add_twink(former_main, "New Main")
        raid = self.model.create_raid("2026-11-02", "Raid")
        self.model.import_raid_attendance(raid.id, [former_main.name])

        self.model.update_member_assignment(
            replacement.id, player.playerId, "main", "not_set",
            replace_existing_main=True,
        )

        entry = self.model.attendance_for_raid(raid.id)[0]
        former_stats = raid_domain.calculate_statistics(
            player.playerId, self.model.raids, self.model.raid_attendance,
            self.model.attendance_tracking_start_date, member_id=former_main.id,
        )
        replacement_stats = raid_domain.calculate_statistics(
            player.playerId, self.model.raids, self.model.raid_attendance,
            self.model.attendance_tracking_start_date, member_id=replacement.id,
        )
        self.assertEqual((entry.memberId, entry.attendanceType), (former_main.id, "main"))
        self.assertEqual(
            (former_stats.main_attendances, former_stats.twink_attendances,
             former_stats.total_attendances),
            (1, 0, 1),
        )
        self.assertEqual(replacement_stats.total_attendances, 0)

    def test_player_aggregation_deduplicates_same_raid_but_keeps_characters(self):
        main, player = self.add_main()
        twink = self.add_twink(main)
        raid = self.model.create_raid("2026-11-03", "Raid")
        raid.status = "recorded"
        entries = [
            raid_domain.RaidAttendance(
                "a-main", raid.id, player.playerId, main.id, "main",
                player.playerName, main.name, "present",
            ),
            raid_domain.RaidAttendance(
                "a-twink", raid.id, player.playerId, twink.id, "twink",
                player.playerName, twink.name, "present",
            ),
        ]

        player_stats = raid_domain.calculate_statistics(
            player.playerId, [raid], entries, raid.date,
        )
        main_stats = raid_domain.calculate_statistics(
            player.playerId, [raid], entries, raid.date, member_id=main.id,
        )
        twink_stats = raid_domain.calculate_statistics(
            player.playerId, [raid], entries, raid.date, member_id=twink.id,
        )

        self.assertEqual(player_stats.total_attendances, 1)
        self.assertEqual(main_stats.total_attendances, 1)
        self.assertEqual(twink_stats.total_attendances, 1)

    def test_reloaded_statistics_match_live_statistics(self):
        main, player = self.add_main()
        first = self.model.create_raid("2026-11-04", "Raid 1")
        second = self.model.create_raid("2026-11-05", "Raid 2")
        self.model.import_raid_attendance(first.id, [main.name])
        self.model.import_raid_attendance(second.id, [main.name])
        self.model.set_raid_attendance_status(second.id, player.playerId, "bench")
        live = self.model.attendance_statistics_for_player(player.playerId)

        rebuilt = g.GuildModel()
        rebuilt.load_payload(self.model.to_payload())
        restored = rebuilt.attendance_statistics_for_player(player.playerId)

        self.assertEqual(restored, live)

    def test_manual_bench_is_relevant_unique_and_never_replaces_present(self):
        present_member, present_player = self.add_main("Present", "Present Player")
        bench_member, bench_player = self.add_main("Bench", "Bench Player")
        self.model.set_player_membership(
            bench_player.playerId, "2026-09-01", "2026-09-30",
        )
        raid, summary = self.model.create_raid_with_attendance(
            "2026-09-15", "MC", "", "MC", [present_member.name],
            bench_player_ids=[bench_player.playerId],
        )
        entries = {entry.playerId: entry for entry in self.model.attendance_for_raid(raid.id)}
        self.assertEqual(summary["bench"], 1)
        self.assertEqual(entries[present_player.playerId].status, "present")
        self.assertEqual(entries[bench_player.playerId].status, "bench")
        with self.assertRaises(ValueError):
            self.model.set_raid_bench_players(raid.id, [present_player.playerId])
        self.assertEqual(
            self.model.attendance_lookup()[raid.id][present_player.playerId].status,
            "present",
        )
        self.model.set_raid_bench_players(raid.id, [])
        self.assertEqual(
            [entry.playerId for entry in self.model.attendance_for_raid(raid.id)],
            [present_player.playerId],
        )
        self.assertEqual(bench_member.playerId, bench_player.playerId)
        self.assertNotIn(
            bench_player.playerId,
            {player.playerId for player, _member in self.model.bench_candidates_for_date(
                "2026-10-01", {present_player.playerId},
            )},
        )

    def test_attendance_filters_combine_period_category_and_raid_type(self):
        main, player = self.add_main()
        for raid_date, raid_type in (
            ("2026-09-01", "ZG"), ("2026-09-08", "MC"), ("2026-09-15", "BWL"),
        ):
            raid = self.model.create_raid(raid_date, raid_type, raid_type=raid_type)
            self.model.import_raid_attendance(raid.id, [main.name])
        category = self.model.attendance_statistics_for_player(player.playerId, category="40er")
        specific = self.model.attendance_statistics_for_player(player.playerId, raid_type="MC")
        period = self.model.attendance_statistics_for_player(
            player.playerId, start_date="2026-09-10", end_date="2026-09-30",
        )
        self.assertEqual(category.total_attendances, 2)
        self.assertEqual(specific.total_attendances, 1)
        self.assertEqual(period.total_attendances, 1)

    def test_create_raid_with_attendance_is_atomic_on_import_failure(self):
        before = (
            list(self.model.members), list(self.model.players), list(self.model.raids),
            list(self.model.raid_attendance), self.model.attendance_tracking_start_date,
            self.model.next_id, self.model.next_player_id, self.model.dirty,
        )
        with self.assertRaises(ValueError):
            self.model.create_raid_with_attendance(
                "2026-09-01", "MC", "", "MC", ["Unknown"],
                unknown_decisions={"NotInCsv": ("main", None)},
            )
        self.assertEqual(
            (
                self.model.members, self.model.players, self.model.raids,
                self.model.raid_attendance, self.model.attendance_tracking_start_date,
                self.model.next_id, self.model.next_player_id, self.model.dirty,
            ),
            before,
        )

    def test_csv_duplicate_rows_are_reported_but_unique_names_are_preserved(self):
        names, duplicates = csv_import.detect_csv_name_details(
            "Name;Amount\nBífi;1\nBÍFI;2\nÁnníe;1\n",
        )
        self.assertEqual(names, ["Bífi", "Ánníe"])
        self.assertEqual(duplicates, ["BÍFI"])

    def test_raid_csv_metadata_is_split_before_name_table(self):
        parsed = csv_import.detect_raid_csv(
            '"META_RAID_TYPE","ZulGurub"\n'
            '"META_RAID_DATE","2026-09-08"\n'
            '"META_REPORT_URL","https://vanilla.warcraftlogs.com/reports/abc"\n'
            '"Name","Amount","Ilvl","Active","CPM",""\n'
            '"Bífi","12","60","1","3",""\n'
            '"META_UNKNOWN","must-not-be-a-name"\n'
            '"Ánníe","9","60","1","2",""\n'
        )
        self.assertEqual(parsed.names, ("Bífi", "Ánníe"))
        self.assertEqual(parsed.duplicates, ())
        self.assertEqual(parsed.metadata.raid_type, "ZulGurub")
        self.assertEqual(parsed.metadata.raid_date, "2026-09-08")
        self.assertEqual(
            parsed.metadata.report_url,
            "https://vanilla.warcraftlogs.com/reports/abc",
        )
        self.assertFalse(any(name.startswith("META_") for name in parsed.names))

    def test_raid_csv_partial_metadata_and_legacy_csv_remain_distinct(self):
        partial = csv_import.detect_raid_csv(
            '"META_RAID_DATE","2026-09-08"\n"Name","Amount"\n"Bífi","1"\n',
        )
        self.assertIsNone(partial.metadata.raid_type)
        self.assertEqual(partial.metadata.raid_date, "2026-09-08")
        self.assertIsNone(partial.metadata.report_url)
        self.assertEqual(partial.names, ("Bífi",))

        legacy = csv_import.detect_raid_csv('"Name","Amount"\n"Bífi","1"\n')
        self.assertEqual(legacy.metadata, csv_import.RaidCsvMetadata())
        self.assertEqual(legacy.names, ("Bífi",))

        invalid_value = csv_import.detect_raid_csv(
            '"META_RAID_DATE","not-a-date"\n"META_UNKNOWN","ignored"\n'
            '"Name","Amount"\n"Bífi","1"\n',
        )
        self.assertEqual(invalid_value.names, ("Bífi",))
        self.assertEqual(invalid_value.metadata.raid_date, "not-a-date")

    def test_csv_raid_type_aliases_resolve_only_to_existing_types(self):
        expected = {
            "MC": "MC",
            " BWL ": "BWL",
            "aq20": "AQ20",
            "Onyxia": "Onyxia",
            "ZulGurub": "ZG",
            "ZG": "ZG",
            "World Boss": "World Boss",
            "worldboss": "World Boss",
            "Azuregos": "World Boss",
            "Lord Kazzak": "World Boss",
            "Kazzak": "World Boss",
            "Emeriss": "World Boss",
            "Lethon": "World Boss",
            "Taerar": "World Boss",
            "Ysondre": "World Boss",
        }
        for external, canonical in expected.items():
            with self.subTest(external=external):
                self.assertEqual(
                    csv_import.normalize_csv_raid_type(external, raid_domain.RAID_TYPES),
                    canonical,
                )
        self.assertIsNone(
            csv_import.normalize_csv_raid_type("Unknown Future Raid", raid_domain.RAID_TYPES),
        )
        self.assertEqual(
            raid_domain.RAID_TYPES,
            ("ZG", "AQ20", "MC", "BWL", "AQ40", "Naxx", "Onyxia", "World Boss"),
        )

    def test_shared_raid_type_aliases_and_title_order(self):
        from app.raid_type_detection import detect_raid_type

        expected = {
            "Naxxramas": "Naxx", "nAxXrAmAs": "Naxx", "Naxx 40": "Naxx",
            "Molten Core": "MC", "Blackwing Lair": "BWL",
            "Zul Gurub": "ZG", "Zul'Gurub": "ZG", "Zul-Gurub": "ZG",
            "ZulGurub": "ZG",
            "AQ": "AQ20", "AQ20": "AQ20", "AQ 20": "AQ20",
            "Ruins of Ahn'Qiraj": "AQ20",
            "Ruins of AhnQiraj": "AQ20", "AQ40": "AQ40", "AQ 40": "AQ40",
            "Temple of Ahn'Qiraj": "AQ40", "Temple of AhnQiraj": "AQ40",
            "Ony": "Onyxia", "Onyxia's Lair": "Onyxia",
            "Onyxias Lair": "Onyxia",
            "Worldboss": "World Boss", "Azu": "World Boss",
            "Azzuregos": "World Boss", "Azuregos": "World Boss",
            "Lord Kazzak": "World Boss", "Kazzak": "World Boss",
            "Emeriss": "World Boss", "Lethon": "World Boss",
            "Taerar": "World Boss", "Ysondre": "World Boss",
            "Dragons of Nightmare": "World Boss",
            "Teremus": "World Boss", "Teremus the Devourer": "World Boss",
            "Ony / MC": "MC", "Ony_MC": "MC", "ZG nach Ony/MC": "ZG",
            "Ony / ZG / AQ20": "ZG", "Azuregos + MC": "MC",
            "AQ40 & ZG": "AQ40", "AQ40 + ZG": "AQ40",
            "Kazzak / Naxxramas": "Naxx", "Kazzak + Naxxramas": "Naxx",
            "MC / ZG": "MC", "ZG / MC": "ZG",
            "AQ + ZG": "AQ20", "ZG + AQ": "ZG",
            "AQ & MC": "AQ20", "MC / AQ": "MC",
            "Ony / AQ": "AQ20", "Azu + ZG": "ZG",
            "Azu, AQ, ZG": "AQ20", "Azu, ZG, AQ": "ZG",
            "Azu + Ony": "World Boss", "ZG + AQ40": "ZG",
            "17.10 AQ+ZG": "AQ20",
            "AQ & ZG 31.10.2025": "AQ20",
            "Azu, AQ, ZG 14.11.": "AQ20",
            "Azu 28.11.2025": "World Boss",
            "2026-01-30 AQ20": "AQ20", "2026-01-30 ZG": "ZG",
        }
        for title, canonical in expected.items():
            with self.subTest(title=title):
                self.assertEqual(detect_raid_type(title), canonical)
                self.assertEqual(
                    csv_import.normalize_csv_raid_type(title, raid_domain.RAID_TYPES),
                    canonical)
        for title in ("Unknown Future Raid", "Naxxish", "AQish"):
            with self.subTest(title=title):
                self.assertIsNone(detect_raid_type(title))
                self.assertIsNone(csv_import.normalize_csv_raid_type(
                    title, raid_domain.RAID_TYPES))
        self.assertEqual(raid_domain.raid_category("Naxxramas"), "40er")
        self.assertEqual(raid_domain.raid_category("Zul'Gurub"), "20er")
        self.assertEqual(raid_domain.raid_category("AQ"), "20er")
        self.assertEqual(raid_domain.raid_category("Azu"), "World Boss")

    def test_bulk_csv_import_adds_two_and_skips_existing_without_mutation(self):
        main, _player = self.add_main("Bífi")
        existing, _summary = self.model.create_raid_with_attendance(
            "2026-06-13", "ZG", "https://vanilla.warcraftlogs.com/reports/existing",
            "ZG", [main.name],
        )
        existing_snapshot = existing.to_dict()
        attendance_snapshot = [
            entry.to_dict() for entry in self.model.attendance_for_raid(existing.id)
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            existing_csv = folder / "2026-06-13_ZulGurub_Casts.csv"
            metadata_csv = folder / "2026-06-16_UnknownZone_Casts.csv"
            fallback_csv = folder / "2026-06-26_MC_Casts.csv"
            assignment_csv = folder / "2026-06-30_BWL_Casts.csv"
            existing_csv.write_text('"Name","Amount"\n"Bífi","1"\n', encoding="utf-8")
            metadata_csv.write_text(
                '"META_RAID_TYPE","AQ20"\n'
                '"META_RAID_DATE","2026-06-16"\n'
                '"META_REPORT_URL","https://vanilla.warcraftlogs.com/reports/new-aq"\n'
                '"Name","Amount"\n"Bífi","1"\n',
                encoding="utf-8",
            )
            fallback_csv.write_text('"Name","Amount"\n"Bífi","1"\n', encoding="utf-8")
            assignment_csv.write_text('"Name","Amount"\n"NeuImRaid","1"\n', encoding="utf-8")

            plans = self.model.analyze_bulk_raid_csv_files(
                [fallback_csv, existing_csv, metadata_csv, assignment_csv],
            )
            self.assertEqual(
                [(plan.raid_date, plan.raid_type, plan.status) for plan in plans],
                [
                    ("2026-06-13", "ZG", "existing"),
                    ("2026-06-16", "AQ20", "new"),
                    ("2026-06-26", "MC", "new"),
                    ("2026-06-30", "BWL", "needs_assignment"),
                ],
            )
            self.assertEqual(plans[-1].unknown_names, ("NeuImRaid",))
            result = self.model.import_bulk_raid_csv_plans(
                plans,
                {assignment_csv: {"NeuImRaid": ("main", None)}},
            )
            self.assertEqual((result.imported, result.skipped, result.failed), (3, 1, 0))
            self.assertEqual([raid.date for raid in self.model.raids], [
                "2026-06-13", "2026-06-16", "2026-06-26", "2026-06-30",
            ])
            self.assertIsNotNone(self.model.find_by_name("NeuImRaid"))
            self.assertEqual(existing.to_dict(), existing_snapshot)
            self.assertEqual(
                [entry.to_dict() for entry in self.model.attendance_for_raid(existing.id)],
                attendance_snapshot,
            )

            repeated = self.model.import_bulk_raid_csv_plans(
                self.model.analyze_bulk_raid_csv_files(
                    [fallback_csv, existing_csv, metadata_csv, assignment_csv],
                ),
            )
            self.assertEqual((repeated.imported, repeated.skipped, repeated.failed), (0, 4, 0))
            self.assertEqual(len(self.model.raids), 4)

    def test_bulk_preview_plans_keep_participants_and_import_only_selected_new_raid(self):
        first, _first_player = self.add_main("Bulk A")
        second, _second_player = self.add_main("Bulk B")
        third, _third_player = self.add_main("Bulk C")
        existing, _summary = self.model.create_raid_with_attendance(
            "2026-07-15", "ZG", "", "ZG", [first.name],
        )
        existing_attendance = [
            entry.to_dict() for entry in self.model.attendance_for_raid(existing.id)
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            raid_a = folder / "2026-07-01_MC_Casts.csv"
            raid_b = folder / "2026-07-08_BWL_Casts.csv"
            raid_c = folder / "2026-07-15_ZG_Casts.csv"
            names = '"Bulk A","1"\n"Bulk B","1"\n"Bulk C","1"\n'
            for path in (raid_a, raid_b, raid_c):
                path.write_text('"Name","Amount"\n' + names, encoding="utf-8")

            plans = self.model.analyze_bulk_raid_csv_files((raid_a, raid_b, raid_c))
            by_path = {plan.source_path: plan for plan in plans}
            self.assertEqual(by_path[raid_a].names, ("Bulk A", "Bulk B", "Bulk C"))
            self.assertEqual(by_path[raid_b].status, "new")
            self.assertEqual(by_path[raid_c].status, "existing")

            result = self.model.import_bulk_raid_csv_plans((by_path[raid_a],))
            self.assertEqual((result.imported, result.skipped, result.failed), (1, 0, 0))
            self.assertIsNotNone(next((
                raid for raid in self.model.raids if raid.date == "2026-07-01"
            ), None))
            self.assertIsNone(next((
                raid for raid in self.model.raids if raid.date == "2026-07-08"
            ), None))
            self.assertEqual(
                [entry.to_dict() for entry in self.model.attendance_for_raid(existing.id)],
                existing_attendance,
            )

    def test_legacy_format_migration_and_current_roundtrip(self):
        for version in (1, 2):
            legacy = g.GuildModel()
            legacy.load_payload({
                "formatVersion": version,
                "players": [{"playerId": "p0001", "playerName": "Legacy"}],
                "members": [{
                    "id": "m0001", "name": "Legacy", "playerId": "p0001",
                    "characterType": "main",
                }],
            })
            self.assertEqual((legacy.raids, legacy.raid_attendance), ([], []))
            self.assertIsNone(legacy.attendance_tracking_start_date)
            self.assertIsNone(legacy.players[0].membershipStartDate)
            self.assertIsNone(legacy.players[0].membershipEndDate)

        main, player = self.add_main()
        self.model.set_player_membership(player.playerId, "2026-01-01", None)
        raid = self.model.create_raid("2026-02-01", "MC", "https://warcraftlogs.com/reports/a")
        self.model.import_raid_attendance(raid.id, [main.name])
        with tempfile.TemporaryDirectory(prefix="ggc-raids-") as temp:
            path = Path(temp) / "raids.ggc"
            self.model.save(path)
            loaded = g.GuildModel()
            loaded.load(path)
        payload = loaded.to_payload()
        self.assertEqual(payload["formatVersion"], g.PROJECT_FORMAT_VERSION)
        self.assertEqual(payload["attendanceTrackingStartDate"], "2026-02-01")
        self.assertEqual(payload["players"][0]["membershipStartDate"], "2026-01-01")
        self.assertEqual(payload["raids"][0]["name"], "MC")
        self.assertEqual(payload["raidAttendance"][0]["attendanceType"], "main")

    def test_csv_input_path_raw_text_and_original_columns_are_not_serialized(self):
        raid = self.model.create_raid("2026-09-01", "MC")
        marker_name = "NeverPersistThisRawMarker"
        self.model.import_raid_attendance(raid.id, [marker_name], [marker_name])
        encoded = json.dumps(self.model.to_payload(), ensure_ascii=False)
        self.assertNotIn("csvPath", encoded)
        self.assertNotIn("rawCsv", encoded)
        self.assertNotIn("Amount", encoded)
        self.assertNotIn("C:\\\\private\\\\attendance.csv", encoded)

    def test_autosave_contains_complete_attendance(self):
        main, _player = self.add_main()
        raid = self.model.create_raid("2026-09-01", "MC")
        self.model.import_raid_attendance(raid.id, [main.name])
        with tempfile.TemporaryDirectory(prefix="ggc-raid-autosave-") as temp:
            self.model.project_path = Path(temp) / "guild.ggc"
            path = Path(temp) / "autosave" / "guild_autosave.ggc"
            view = SimpleNamespace(
                model=self.model, status_var=SimpleNamespace(set=Mock()),
            )
            g.GuildGearCheckerApp.autosave(view)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["raids"][0]["id"], raid.id)
        self.assertEqual(payload["raidAttendance"][0]["raidId"], raid.id)

    def test_project_package_contains_complete_raid_data(self):
        main, _player = self.add_main()
        raid = self.model.create_raid("2026-09-01", "MC")
        self.model.import_raid_attendance(raid.id, [main.name])
        with tempfile.TemporaryDirectory(prefix="ggc-raid-package-") as temp:
            root = Path(temp)
            portraits = root / "portraits"
            portraits.mkdir()
            target = root / "project.zip"
            g.create_project_package(self.model, target, portraits)
            with zipfile.ZipFile(target) as archive:
                payload = json.loads(archive.read("project.ggc").decode("utf-8"))
        self.assertEqual(payload["raids"][0]["id"], raid.id)
        self.assertEqual(payload["raidAttendance"][0]["raidId"], raid.id)

    def test_character_cleanup_preserves_raids_but_new_project_resets_all(self):
        main, _player = self.add_main()
        raid = self.model.create_raid("2026-09-01", "MC")
        self.model.import_raid_attendance(raid.id, [main.name])
        self.model.clear_project()
        self.assertEqual((self.model.members, self.model.players), ([], []))
        self.assertEqual(len(self.model.raids), 1)
        self.assertEqual(len(self.model.raid_attendance), 1)
        replacement = self.model.add_member("Replacement")
        self.model.assign_character_type(replacement.id, "main", None, "not_set")
        historical = self.model.raid_attendance[0]
        self.assertNotEqual(replacement.id, historical.memberId)
        self.assertNotEqual(replacement.playerId, historical.playerId)
        self.model.new_empty()
        self.assertEqual((self.model.raids, self.model.raid_attendance), ([], []))
        self.assertIsNone(self.model.attendance_tracking_start_date)

    def test_project_payload_rejects_duplicate_player_per_raid(self):
        payload = {
            "formatVersion": 3,
            "members": [],
            "players": [],
            "raids": [{"id": "r1", "date": "2026-09-01", "name": "MC", "status": "recorded"}],
            "raidAttendance": [
                {"id": "a1", "raidId": "r1", "playerId": "p1", "memberId": "m1",
                 "attendanceType": "main", "playerNameSnapshot": "P", "characterNameSnapshot": "M"},
                {"id": "a2", "raidId": "r1", "playerId": "p1", "memberId": "m2",
                 "attendanceType": "twink", "playerNameSnapshot": "P", "characterNameSnapshot": "T"},
            ],
        }
        with self.assertRaises(ValueError):
            self.model.load_payload(payload)

    def test_raid_status_labels_are_localized_without_changing_internal_values(self):
        original_language = g.get_language()
        try:
            g.set_language("de")
            self.assertEqual((g.tr("raids.status_draft"), g.tr("raids.status_recorded")),
                             ("Offen", "Erfasst"))
            self.assertEqual(
                (g.tr("raids.add_as_main"), g.tr("raids.assign_as_twink"),
                 g.tr("raids.discard")),
                ("Als Main hinzufügen", "Als Twink zuordnen", "Verwerfen"),
            )
            self.assertEqual(
                (g.tr("raids.import_attendance"), g.tr("raids.reset_attendance"),
                 g.tr("raids.eligible")),
                ("Teilnahme importieren", "Teilnahme zurücksetzen", "Gewertet"),
            )
            g.set_language("en")
            self.assertEqual((g.tr("raids.status_draft"), g.tr("raids.status_recorded")),
                             ("Open", "Recorded"))
            self.assertEqual(
                (g.tr("raids.add_as_main"), g.tr("raids.assign_as_twink"),
                 g.tr("raids.discard")),
                ("Add as Main", "Assign as Twink", "Discard"),
            )
            self.assertEqual(
                (g.tr("raids.import_attendance"), g.tr("raids.reset_attendance"),
                 g.tr("raids.eligible")),
                ("Import Attendance", "Reset Attendance", "Counted"),
            )
            raid = raid_domain.Raid("r1", "2026-09-01", "MC")
            self.assertEqual(raid.status, "draft")
            raid.status = "recorded"
            self.assertEqual(raid.status, "recorded")
        finally:
            g.set_language(original_language)

    def test_raid_sort_values_are_typed_and_do_not_mutate_project_data(self):
        first = self.model.create_raid("2026-09-12", "zeta")
        second = self.model.create_raid("2026-09-05", "Alpha")
        before = self.model.to_payload()
        by_date = sorted(
            self.model.raids,
            key=lambda raid: g.raid_table_sort_value(raid, "date", 0, "Offen"),
        )
        self.assertEqual([raid.id for raid in by_date], [second.id, first.id])
        by_name = sorted(
            self.model.raids,
            key=lambda raid: g.raid_table_sort_value(raid, "name", 0, "Offen"),
        )
        self.assertEqual([raid.id for raid in by_name], [second.id, first.id])
        self.assertLess(
            g.raid_table_sort_value(first, "participants", 2, "Offen"),
            g.raid_table_sort_value(second, "participants", 10, "Offen"),
        )
        low = SimpleNamespace(attendance_percent=9, eligible_raids=10,
                              main_attendances=0, twink_attendances=0, absences=10)
        high = SimpleNamespace(attendance_percent=100, eligible_raids=10,
                               main_attendances=10, twink_attendances=0, absences=0)
        player = g.Player("p1", "Player")
        self.assertLess(
            g.raid_statistics_sort_value(player, low, "attendance"),
            g.raid_statistics_sort_value(player, high, "attendance"),
        )
        self.assertEqual(self.model.to_payload(), before)

    def test_import_ui_binds_target_confirms_reimport_and_can_reset(self):
        with tempfile.TemporaryDirectory(prefix="ggc-raid-import-ui-") as temp, \
             patch.object(g, "app_base_dir", return_value=Path(temp)), \
             patch.dict(os.environ, {"GGC_DISABLE_ICON_DOWNLOAD": "1"}):
            try:
                app = g.GuildGearCheckerApp()
            except g.tk.TclError as exc:
                self.skipTest(f"Tk not available: {exc}")
            try:
                app.model.new_empty()
                first = app.model.add_member("First")
                app.model.assign_character_type(first.id, "main", None, "not_set")
                second = app.model.add_member("Second")
                app.model.assign_character_type(second.id, "main", None, "not_set")
                raid = app.model.create_raid("2026-09-12", "MC")
                app.model.import_raid_attendance(raid.id, [first.name])
                app.switch_tab("Raids")

                app.raid_tree.selection_remove(app.raid_tree.selection())
                app._update_raid_action_states()
                self.assertEqual(str(app.raid_import_button.cget("state")), "disabled")
                with patch.object(g.filedialog, "askopenfilename") as chooser, \
                     patch.object(g.messagebox, "showinfo") as info:
                    app.import_raid_attendance_csv()
                chooser.assert_not_called()
                info.assert_called_once()

                target = g.attendance_target_text(raid, 1)
                self.assertIn("MC", target)
                self.assertIn("12.09.2026" if g.get_language() == "de" else "2026-09-12", target)
                self.assertIn(g.tr("raids.status_recorded"), target)
                self.assertIn("1", target)

                app.raid_tree.selection_set(raid.id)
                old_attendance = [
                    entry.to_dict() for entry in app.model.attendance_for_raid(raid.id)
                ]
                with patch.object(g.filedialog, "askopenfilename", return_value="attendance.csv"), \
                     patch.object(app, "_confirm_attendance_target", return_value=True) as target_confirm, \
                     patch.object(g, "read_csv_names", return_value=[second.name]), \
                     patch.object(app, "_confirm_raid_action", return_value=False):
                    app.import_raid_attendance_csv()
                target_confirm.assert_called_once_with(raid)
                self.assertEqual(
                    [entry.to_dict() for entry in app.model.attendance_for_raid(raid.id)],
                    old_attendance,
                )

                with patch.object(g.filedialog, "askopenfilename", return_value="attendance.csv"), \
                     patch.object(app, "_confirm_attendance_target", return_value=True), \
                     patch.object(g, "read_csv_names", return_value=[second.name]), \
                     patch.object(app, "_decide_unknown_attendance", return_value={}), \
                     patch.object(app, "_confirm_raid_action", side_effect=[True, True]), \
                     patch.object(g.messagebox, "showinfo"):
                    app.import_raid_attendance_csv()
                replacement = app.model.attendance_for_raid(raid.id)
                self.assertEqual([entry.characterNameSnapshot for entry in replacement], ["Second"])
                self.assertEqual(raid.status, "recorded")

                with patch.object(app, "_confirm_raid_action", return_value=True):
                    app.reset_selected_raid_attendance()
                self.assertEqual(app.model.attendance_for_raid(raid.id), [])
                self.assertEqual(raid.status, "draft")
                self.assertEqual(str(app.raid_reset_button.cget("state")), "disabled")
            finally:
                app.destroy()

    def test_raid_ui_smoke(self):
        with tempfile.TemporaryDirectory(prefix="ggc-raid-ui-") as temp, \
             patch.object(g, "app_base_dir", return_value=Path(temp)), \
             patch.dict(os.environ, {"GGC_DISABLE_ICON_DOWNLOAD": "1"}):
            try:
                app = g.GuildGearCheckerApp()
            except g.tk.TclError as exc:
                self.skipTest(f"Tk not available: {exc}")
            try:
                app.model.new_empty()
                later = app.model.create_raid(
                    "2026-09-12", "Later", "https://warcraftlogs.com/reports/test",
                )
                earlier = app.model.create_raid("2026-09-05", "Earlier")
                attending = app.model.add_member("Attending")
                app.model.assign_character_type(attending.id, "main", None, "not_set")
                absent = app.model.add_member("Absent")
                app.model.assign_character_type(absent.id, "main", None, "not_set")
                participant_names = [attending.name]
                for index in range(39):
                    member = app.model.add_member(f"Participant{index:02d}")
                    app.model.assign_character_type(member.id, "main", None, "not_set")
                    participant_names.append(member.name)
                app.model.import_raid_attendance(later.id, participant_names)
                project_before_sorting = app.model.to_payload()
                app.switch_tab("Raids")
                app.update_idletasks()
                self.assertEqual(app.current_tab, "Raids")
                self.assertTrue(app.raid_view.grid_info())
                self.assertTrue(app.raid_tree.exists(later.id))
                self.assertEqual(
                    app.raid_tree["columns"],
                    ("date", "name", "participants", "status", "logs"),
                )
                self.assertEqual(
                    app.raid_statistics_tree["columns"],
                    ("player", "attendance", "eligible", "main", "twink"),
                )
                self.assertNotIn("absent", app.raid_statistics_tree["columns"])
                self.assertIn("Raids", app.tab_buttons)
                self.assertFalse(app.sidebar_member_panel.winfo_manager())
                self.assertEqual(app.sidebar_raid_panel.winfo_manager(), "pack")
                self.assertEqual(len(app.raid_paned.panes()), 2)
                self.assertIsNot(app.raid_scrollbar, app.raid_statistics_scrollbar)
                self.assertNotEqual(
                    str(app.raid_tree.cget("yscrollcommand")),
                    str(app.raid_statistics_tree.cget("yscrollcommand")),
                )
                self.assertGreaterEqual(
                    int(app.raid_paned.panecget(app.raid_paned.panes()[0], "minsize")), 120,
                )
                self.assertGreaterEqual(
                    int(app.raid_paned.panecget(app.raid_paned.panes()[1], "minsize")), 180,
                )
                initial_sash = app.raid_paned.sash_coord(0)[1]
                movable_sash = min(
                    app.raid_paned.winfo_height() - 180,
                    max(120, initial_sash + 20),
                )
                if movable_sash != initial_sash:
                    app.raid_paned.sash_place(0, 0, movable_sash)
                    app.update_idletasks()
                    self.assertNotEqual(app.raid_paned.sash_coord(0)[1], initial_sash)
                self.assertEqual(app.raid_tree.get_children(), (later.id, earlier.id))
                self.assertEqual(
                    app.raid_tree.item(later.id, "values")[2:5],
                    ("40", g.tr("raids.status_recorded"), g.tr("raids.open_logs_short")),
                )
                self.assertTrue(app.raid_tree.heading("date", "command"))
                self.assertTrue(app.raid_statistics_tree.heading("attendance", "command"))

                app.raid_status_filter.set(g.tr("raids.status_draft"))
                app.refresh_raids()
                self.assertEqual(app.raid_tree.get_children(), (earlier.id,))
                app.raid_status_filter.set(g.tr("common.all"))
                app.refresh_raids()

                app._sort_raids_by("date")
                self.assertEqual(app.raid_tree.get_children(), (earlier.id, later.id))
                app._sort_raids_by("date")
                self.assertEqual(app.raid_tree.get_children(), (later.id, earlier.id))
                app._sort_raids_by("participants")
                self.assertEqual(app.raid_tree.get_children(), (earlier.id, later.id))
                app._sort_raids_by("participants")
                self.assertEqual(app.raid_tree.get_children(), (later.id, earlier.id))

                absent_player = app.model.find_player_by_id(absent.playerId)
                attending_player = app.model.find_player_by_id(attending.playerId)
                app._sort_raid_statistics_by("attendance")
                ascending_statistics = app.raid_statistics_tree.get_children()
                self.assertEqual(ascending_statistics[0], absent_player.playerId)
                self.assertIn(attending_player.playerId, ascending_statistics[1:])
                app._sort_raid_statistics_by("attendance")
                descending_statistics = app.raid_statistics_tree.get_children()
                self.assertEqual(descending_statistics[-1], absent_player.playerId)
                self.assertIn(attending_player.playerId, descending_statistics[:-1])
                attendance_display = app.raid_statistics_tree.item(
                    attending_player.playerId, "values",
                )[1]
                self.assertNotIn("+0", attendance_display)
                project_after_sorting = app.model.to_payload()
                project_after_sorting["savedAt"] = project_before_sorting["savedAt"]
                self.assertEqual(project_after_sorting, project_before_sorting)

                app.raid_tree.selection_set(later.id)
                app.open_selected_raid()
                app.update_idletasks()
                raid_dialog = next(
                    child for child in app.winfo_children() if isinstance(child, g.tk.Toplevel)
                )
                def descendants(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from descendants(child)

                attendance_tree = next(
                    child for child in descendants(raid_dialog)
                    if isinstance(child, g.ttk.Treeview)
                )
                self.assertTrue(attendance_tree.heading("player", "command"))
                self.assertTrue(attendance_tree.heading("character", "command"))
                self.assertTrue(attendance_tree.heading("type", "command"))
                self.assertTrue(attendance_tree.cget("yscrollcommand"))
                self.assertEqual(len(attendance_tree.get_children()), 40)
                self.assertLessEqual(int(g.ttk.Style(raid_dialog).lookup(
                    "RaidDetail.Treeview", "rowheight",
                )), 24)
                raid_dialog.destroy()

                self.assertFalse(hasattr(app, "raid_detail_toggle"))
                self.assertFalse(app.detail_outer.grid_info())
                app.switch_tab("Gildenliste")
                self.assertTrue(app.detail_outer.grid_info())
            finally:
                app.destroy()


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RaidAttendanceTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    REPO_ROOT = args.repo_root.resolve()
    raise SystemExit(main())
