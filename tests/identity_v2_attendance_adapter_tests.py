"""Focused checks for the V2 input of the existing attendance matrix."""

import copy
import unittest

from app.identity_v2 import Attendance, IdentityV2Store, Member, Player, Raid
from app.identity_v2_attendance_adapter import V2AttendanceAdapter
from app.raid_attendance import Raid as LegacyRaid, RaidAttendance, calculate_statistics


def sample_store() -> IdentityV2Store:
    store = IdentityV2Store(
        players=[Player("p1", "Besitzer", "m3"), Player("p2", "Zweiter", "m2"),
                 Player("p3", "Ohne Raid", "m5")],
        members=[
            Member("m1", "Gleich", "Mage", lifeStatus="dead",
                   deathDate="2026-01-02", burialType="individual", playerId="p1",
                   currentRole="main"),
            Member("m2", "Priester", "Priest", playerId="p2"),
            Member("m3", "Nachfolger", "Warlock", playerId="p1",
                   currentRole="twink"),
            Member("m4", "Gleich", "Hunter", playerId="p1"),
            Member("m5", "Leer", "Druid", playerId="p3"),
        ],
        raids=[
            Raid("r0", "2026-01-01", "ZG", "Vorher"),
            Raid("r1", "2026-01-02", "ZG", "Bank"),
            Raid("r2", "2026-01-02", "Onyxia", "Ony"),
            Raid("r3", "2026-01-03", "MC", "Fehlt"),
            Raid("r4", "2026-01-04", "BWL", "Nachfolge"),
            Raid("r5", "2026-01-05", "MC", "Weiter"),
            Raid("r6", "2026-01-06", "ZG", "Fehlt erneut"),
        ],
        attendance=[
            Attendance("a1", "r1", "m1", "unknown", "bench", playerId="p1"),
            Attendance("a2", "r2", "m1", "unknown", "bench", playerId="p1"),
            # Historical player ID remains p1 even though m2 now belongs to p2.
            Attendance("a3", "r2", "m2", "unknown", "present", playerId="p1"),
            Attendance("a4", "r4", "m3", "unknown", "present", playerId="p1"),
            Attendance("a5", "r5", "m3", "unknown", "present", playerId="p1"),
            Attendance("a6", "r5", "m4", "unknown", "bench", playerId="p1"),
        ],
    )
    store.validate()
    return store


class IdentityV2AttendanceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.store = sample_store()
        self.before = self.store.to_payload()
        self.adapter = V2AttendanceAdapter(self.store)
        self.raids = self.adapter.scoped_raids()

    def row(self, level, grouping, identifier):
        return next(row for row in self.adapter.subjects(self.raids, level, grouping)
                    if row.identifier == identifier)

    def cell(self, level, grouping, identifier, column_id):
        columns = self.adapter.columns(self.raids, grouping)
        return self.row(level, grouping, identifier).cells[
            next(index for index, column in enumerate(columns) if column.id == column_id)]

    def test_player_history_uses_stored_player_id_and_present_beats_bench(self):
        rows = self.adapter.subjects(self.raids, "player", "raid")
        self.assertEqual([row.identifier for row in rows], ["p1"])
        row = rows[0]
        self.assertEqual(row.main_name, "Nachfolger")
        self.assertEqual((row.stat.eligible_raids, row.stat.total_attendances,
                          row.stat.bench_attendances, row.stat.attendance_percent),
                         (6, 4, 1, 67))
        r2 = self.cell("player", "raid", "p1", "r2")
        self.assertEqual((r2.status, r2.class_name), ("present", "Priest"))
        self.assertEqual({entry.memberId for entry in self.store.attendance
                          if entry.raidId == "r2"}, {"m1", "m2"})
        self.assertEqual(len(r2.entries), 2)
        self.assertEqual(self.cell("player", "raid", "p1", "r0").status, "irrelevant")
        self.assertEqual(self.cell("player", "raid", "p1", "r3").status, "absent")
        self.assertEqual(self.store.to_payload(), self.before)

    def test_day_quote_and_streak_reuse_shared_statistics(self):
        row = self.row("player", "day", "p1")
        self.assertEqual((row.stat.relevant_days, row.stat.attended_days,
                          row.stat.day_percent, row.stat.current_streak,
                          row.stat.longest_streak), (5, 3, 60, 0, 2))
        day = self.cell("player", "day", "p1", "2026-01-02")
        self.assertEqual((day.status, day.class_name, day.visited_raids,
                          day.relevant_raids), ("present", "Priest", 2, 2))
        self.assertEqual(len(self.adapter.columns(self.raids, "day")), 6)
        self.assertEqual(len(self.adapter.columns(self.raids, "raid")), 7)
        self.assertEqual(self.cell("player", "day", "p1", "2026-01-03").status, "absent")

    def test_day_class_uses_first_present_raid_in_stable_order(self):
        changed = copy.deepcopy(self.store)
        changed.attendance.append(Attendance(
            "a7", "r1", "m4", "unknown", "present", playerId="p1"))
        changed.validate()
        adapter = V2AttendanceAdapter(changed)
        raids = adapter.scoped_raids()
        columns = adapter.columns(raids, "day")
        row = next(row for row in adapter.subjects(raids, "player", "day")
                   if row.identifier == "p1")
        day = row.cells[next(index for index, column in enumerate(columns)
                             if column.id == "2026-01-02")]
        self.assertEqual((day.status, day.class_name), ("present", "Hunter"))
        self.assertEqual([entry.memberId for entry in day.entries],
                         ["m1", "m4", "m1", "m2"])

    def test_character_death_same_day_and_same_name_ids(self):
        rows = self.adapter.subjects(self.raids, "character", "raid")
        self.assertEqual({row.identifier for row in rows}, {"m1", "m2", "m3", "m4"})
        m1 = self.row("character", "raid", "m1")
        m4 = self.row("character", "raid", "m4")
        self.assertTrue(m1.is_dead)
        self.assertEqual(m1.label, m4.label)
        self.assertNotEqual(m1.identifier, m4.identifier)
        self.assertEqual(m1.current_role, "twink")
        self.assertEqual((m1.stat.eligible_raids, m1.stat.total_attendances,
                          m1.stat.bench_attendances, m1.stat.attendance_percent),
                         (2, 2, 2, 100))
        self.assertEqual(self.cell("character", "raid", "m1", "r2").status, "bench")
        self.assertEqual(self.cell("character", "raid", "m1", "r4").status, "irrelevant")
        self.assertEqual(self.cell("character", "raid", "m4", "r5").status, "bench")
        self.assertEqual(self.cell("character", "raid", "m4", "r4").status, "irrelevant")
        self.assertEqual(self.row("character", "raid", "m3").current_role, "main")

    def test_inactivity_is_no_pause_but_inactive_player_is_hidden(self):
        changed = copy.deepcopy(self.store)
        changed.members[2].lifeStatus = "inactive"
        changed.players[0].mainMemberId = None
        changed.validate()
        adapter = V2AttendanceAdapter(changed)
        row = next(row for row in adapter.subjects(adapter.scoped_raids(), "player", "day")
                   if row.identifier == "p1")
        self.assertEqual((row.stat.day_percent, row.stat.current_streak), (60, 0))
        for member in changed.members:
            if member.playerId == "p1" and member.lifeStatus == "active":
                member.lifeStatus = "inactive"
        changed.validate()
        adapter = V2AttendanceAdapter(changed)
        self.assertNotIn("p1", {row.identifier for row in adapter.subjects(
            adapter.scoped_raids(), "player", "raid")})
        self.assertEqual({row.identifier for row in adapter.subjects(
            adapter.scoped_raids(), "player", "raid",
            include_inactive_players=True, identifiers={"p1"})}, {"p1"})
        self.assertIn("m1", {row.identifier for row in adapter.subjects(
            adapter.scoped_raids(), "character", "raid")})
        self.assertEqual({row.identifier for row in adapter.subjects(
            adapter.scoped_raids(), "character", "raid",
            identifiers={"m1"})}, {"m1"})

    def test_first_bench_opens_relevance_and_missing_bank_is_not_guessed(self):
        self.assertEqual(self.cell("player", "raid", "p1", "r1").status, "bench")
        self.assertEqual(self.cell("player", "raid", "p1", "r3").status, "absent")
        self.assertEqual(self.row("player", "raid", "p1").stat.bench_attendances, 1)
        self.assertNotIn("p3", {row.identifier for row in self.adapter.subjects(
            self.raids, "player", "raid")})

    def test_day_limit_keeps_every_raid_on_cutoff_day(self):
        self.assertEqual(len(self.adapter.scoped_raids(limit=6)), 6)
        full_days = self.adapter.scoped_raids(limit=6, complete_days=True)
        self.assertEqual({raid.id for raid in full_days},
                         {"r1", "r2", "r3", "r4", "r5", "r6"})

    def test_shared_legacy_statistic_default_keeps_raid_streak(self):
        raids = [LegacyRaid("r1", "2026-01-02", "ZG", status="recorded", raidType="ZG"),
                 LegacyRaid("r2", "2026-01-02", "Ony", status="recorded", raidType="Onyxia")]
        entries = [RaidAttendance("a1", "r1", "p1", "m1", "main", "P", "M"),
                   RaidAttendance("a2", "r2", "p1", "m1", "main", "P", "M")]
        raid_stat = calculate_statistics("p1", raids, entries, None,
                                         eligible_raid_ids={"r1", "r2"})
        day_stat = calculate_statistics("p1", raids, entries, None,
                                        eligible_raid_ids={"r1", "r2"},
                                        streak_by_day=True)
        self.assertEqual((raid_stat.current_streak, day_stat.current_streak,
                          day_stat.day_percent), (2, 1, 100))
