"""Focused V2 checks using the shared raid-points engine and temporary saves."""

import copy
import tempfile
import unittest
from pathlib import Path

from app.identity_v2 import Attendance, IdentityV2Store, Member, Player, Raid
from app.identity_v2_raid_points import (
    V2RaidPointProjection, apply_v2_member_special_points,
    apply_v2_raid_point_adjustments, point_source_signature,
)
from app.identity_v2_attendance_adapter import V2AttendanceAdapter
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from app.raid_points import RaidPointsError, base_points_for_status


def point_store() -> IdentityV2Store:
    store = IdentityV2Store(
        players=[Player("p1", "Besitzer", "m1"), Player("p2", "Zweiter", "m4")],
        members=[
            Member("m1", "Gleich", "Mage", playerId="p1"),
            Member("m2", "Gleich", "Priest", playerId="p1", lifeStatus="dead",
                   deathDate="2026-01-05", burialType="individual"),
            Member("m3", "Twink", "Warrior", playerId="p1", lifeStatus="inactive"),
            Member("m4", "Anderer", "Druid", playerId="p2"),
        ],
        raids=[
            Raid("r20", "2026-01-01", "ZG", "ZG"),
            Raid("r40", "2026-01-02", "MC", "MC"),
            Raid("rony", "2026-01-03", "Onyxia", "Ony"),
            Raid("rwb", "2026-01-04", "World Boss", "Weltboss"),
        ],
        attendance=[
            Attendance("a1", "r20", "m1", "unknown", "present", playerId="p1"),
            Attendance("a2", "r20", "m2", "unknown", "bench", playerId="p1"),
            Attendance("a3", "r40", "m2", "unknown", "present", playerId="p1"),
            Attendance("a4", "r40", "m3", "unknown", "bench", playerId="p1"),
            Attendance("a5", "rony", "m1", "unknown", "present", playerId="p1"),
            Attendance("a6", "rony", "m3", "unknown", "bench", playerId="p1"),
            Attendance("a7", "rwb", "m2", "unknown", "present", playerId="p1"),
            Attendance("a8", "rwb", "m1", "unknown", "bench", playerId="p1"),
        ],
    )
    store.validate()
    return store


class IdentityV2RaidPointsTests(unittest.TestCase):
    def setUp(self):
        self.store = point_store()
        self.before = self.store.to_payload()

    def test_category_rules_and_absence_use_existing_normalization(self):
        for raid_type in ("ZG", "AQ20", "MC", "BWL", "AQ40", "Naxx"):
            self.assertEqual(base_points_for_status("present", raid_type), 10)
            self.assertEqual(base_points_for_status("bench", raid_type), 5)
        for raid_type in ("Onyxia", "World Boss"):
            self.assertEqual(base_points_for_status("present", raid_type), 5)
            self.assertEqual(base_points_for_status("bench", raid_type), 0)
        with self.assertRaises(RaidPointsError):
            base_points_for_status("present", "Unbekannt")
        projection = V2RaidPointProjection(self.store)
        self.assertEqual((projection.character_points("m1"),
                          projection.character_points("m2"),
                          projection.character_points("m3"),
                          projection.character_points("m4")), (15, 20, 5, 0))
        self.assertEqual(projection.player_points("p1"), 40)
        self.assertEqual(projection.player_points("p2"), 0)
        self.assertEqual(len(projection.history), len(self.store.attendance))
        self.assertEqual(self.store.to_payload(), self.before)

    def test_old_v2_naxxramas_value_projects_without_rewriting_file(self):
        changed = copy.deepcopy(self.store)
        changed.raids[0].raidType = "AQ"
        changed.raids[1].raidType = "Naxxramas"
        changed.validate()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "old-naxx-v2.ggc"
            save_new_identity_v2(changed, target)
            original_bytes = target.read_bytes()
            restored = load_identity_v2(target)
            self.assertEqual(restored.raids[0].raidType, "AQ")
            self.assertEqual(restored.raids[1].raidType, "Naxxramas")
            projection = V2RaidPointProjection(restored)
            self.assertEqual(projection.member_totals,
                             V2RaidPointProjection(self.store).member_totals)
            self.assertEqual(target.read_bytes(), original_bytes)
            self.assertEqual(restored.raids[1].raidType, "Naxxramas")

    def test_special_points_are_member_owned_signed_and_reproducible(self):
        changed = apply_v2_member_special_points(self.store, "m2", 7, "Ersatz")
        point_id = next(iter(changed.raidPoints.member_adjustments))
        changed = apply_v2_member_special_points(changed, "m1", -4, "Abzug")
        changed = apply_v2_raid_point_adjustments(changed, (("a1", -2, "Verspätet"),))
        first = V2RaidPointProjection(changed)
        rebuilt = V2RaidPointProjection(changed)
        self.assertEqual(first.history, rebuilt.history)
        self.assertEqual(first.member_totals, rebuilt.member_totals)
        self.assertEqual((first.character_points("m1"), first.character_points("m2"),
                          first.player_points("p1")), (9, 27, 41))
        self.assertEqual(first.eternal_character_points("m2"), 27)
        self.assertEqual(first.eternal_player_points("p1"), 41)
        self.assertEqual({entry.entry_kind for entry in first.history_for_member("m2")},
                         {"attendance", "special"})
        self.assertEqual(self.store.to_payload(), self.before)
        attendance_before = V2AttendanceAdapter(self.store)
        attendance_after = V2AttendanceAdapter(changed)
        self.assertEqual(
            attendance_before.subjects(attendance_before.scoped_raids(), "player", "day"),
            attendance_after.subjects(attendance_after.scoped_raids(), "player", "day"))
        self.assertIs(apply_v2_raid_point_adjustments(changed, (("a1", -2, "Verspätet"),)),
                      changed)
        self.assertIs(apply_v2_member_special_points(changed, "m2", 7, "Ersatz", point_id),
                      changed)
        removed = apply_v2_member_special_points(changed, "m2", 0, "", point_id)
        self.assertNotIn(point_id, removed.raidPoints.member_adjustments)
        self.assertEqual(V2RaidPointProjection(removed).character_points("m2"), 20)

    def test_negative_special_can_make_a_character_total_negative(self):
        changed = apply_v2_member_special_points(self.store, "m3", -10, "Strafe")
        projection = V2RaidPointProjection(changed)
        self.assertEqual(projection.character_points("m3"), -5)
        self.assertEqual(projection.player_points("p1"), 30)

    def test_main_switch_and_current_owner_change_do_not_rewrite_history(self):
        changed = copy.deepcopy(self.store)
        changed.players[0].mainMemberId = None
        changed.validate()
        self.assertEqual(V2RaidPointProjection(changed).player_points("p1"), 40)
        changed.members[2].lifeStatus = "active"
        changed.players[0].mainMemberId = "m3"
        changed.validate()
        self.assertEqual(V2RaidPointProjection(changed).player_points("p1"), 40)
        changed.members[1].playerId = "p2"
        changed.validate()
        projection = V2RaidPointProjection(changed)
        self.assertEqual((projection.player_points("p1"), projection.player_points("p2")),
                         (20, 20))
        self.assertEqual(projection.character_points("m2"), 20)
        self.assertEqual(changed.attendance[1].playerId, "p1")
        self.assertEqual(projection.history_for_player("p2")[0].member_id, "m2")

    def test_save_load_keeps_adjustments_and_all_source_data(self):
        changed = apply_v2_member_special_points(self.store, "m2", 7, "Ersatz")
        changed = apply_v2_raid_point_adjustments(changed, (("a1", -2, "Verspätet"),))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "points-v2.ggc"
            save_new_identity_v2(changed, target)
            restored = load_identity_v2(target)
        self.assertEqual(restored.to_payload(), changed.to_payload())
        self.assertEqual(restored.to_payload()["attendance"], self.before["attendance"])
        self.assertEqual(restored.to_payload()["raids"], self.before["raids"])
        self.assertEqual(V2RaidPointProjection(restored).player_points("p1"), 45)

    def test_invalid_type_and_edits_are_atomic(self):
        changed = copy.deepcopy(self.store)
        changed.raids[0].raidType = "Unbekannt"
        changed.validate()
        with self.assertRaises(RaidPointsError):
            V2RaidPointProjection(changed)
        for edit in (
            lambda: apply_v2_raid_point_adjustments(self.store, (("missing", 4, "X"),)),
            lambda: apply_v2_member_special_points(self.store, "missing", 4, "X"),
            lambda: apply_v2_member_special_points(self.store, "m1", 4, ""),
        ):
            with self.assertRaises(RaidPointsError):
                edit()
        self.assertEqual(self.store.to_payload(), self.before)

    def test_unrelated_character_note_does_not_invalidate_point_projection(self):
        changed = copy.deepcopy(self.store)
        changed.members[0].note = "Neue Notiz"
        changed.validate()
        self.assertEqual(point_source_signature(changed),
                         point_source_signature(self.store))


if __name__ == "__main__":
    unittest.main()
