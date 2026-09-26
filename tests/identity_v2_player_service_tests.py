"""Focused ownership, Main, activity, and atomicity checks for Identity V2."""

import copy
import tempfile
import unittest
from pathlib import Path

from app.identity_v2 import (
    Attendance, CsvRaidSource, EternalDkpRecord, IdentityV2Store, Member, Player, Raid,
)
from app.identity_v2_player_service import (
    PlayerMembershipError, assign_member, bulk_assign_members,
    bulk_create_players_from_members, clear_main,
    create_player_from_member, delete_player, reassign_member, rename_player,
    set_main, set_member_activity, set_player_activity, unassign_member,
)
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from app.identity_v2_attendance_adapter import V2AttendanceAdapter
from app.identity_v2_player_profile import build_v2_player_profile


class IdentityV2PlayerServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = IdentityV2Store(
            players=[Player("p0001", "Player A", "m1000"),
                     Player("p0002", "Player B", "m1004")],
            members=[
                Member("m1000", "Main A", "Mage", playerId="p0001",
                       clmGuid="1:100", raidStartDate="2026-01-01"),
                Member("m1001", "Weitere A", "Priest", playerId="p0001",
                       clmGuid="1:101", raidStartDate="2026-01-01"),
                Member("m1002", "Ohne Player", None, clmGuid="1:102",
                       raidStartDate="2026-01-01"),
                Member("m1003", "Inaktiv", "Warrior", lifeStatus="inactive",
                       clmGuid="1:103", raidStartDate="2026-01-01"),
                Member("m1004", "Main B", "Rogue", playerId="p0002",
                       clmGuid="1:104", raidStartDate="2026-01-08"),
            ],
            raids=[
                Raid("r1", "2026-01-01", name="MC", clmRaidId="clm-1"),
                Raid("r2", "2026-01-08", name="BWL",
                     csvSourceFiles=("2026-01-08_BWL_Casts.csv",),
                     csvReportUrls=("https://vanilla.warcraftlogs.com/reports/AAA",),
                     csvSources=(CsvRaidSource(
                         "2026-01-08_BWL_Casts.csv",
                         "https://vanilla.warcraftlogs.com/reports/AAA"),)),
            ],
            attendance=[
                Attendance("a1", "r1", "m1000", "main", playerId="p0001",
                           clmGuid="1:100"),
                Attendance("a2", "r2", "m1000", "unknown", playerId="p0001",
                           clmGuid="1:100"),
                Attendance("a3", "r1", "m1001", "twink", playerId="p0001",
                           clmGuid="1:101"),
                Attendance("a4", "r2", "m1002", "unknown", clmGuid="1:102"),
                Attendance("a7", "r1", "m1002", "unknown", clmGuid="1:102"),
                Attendance("a5", "r1", "m1003", "unknown", clmGuid="1:103"),
                Attendance("a6", "r2", "m1004", "unknown", playerId="p0002",
                           clmGuid="1:104"),
            ],
            eternalDkpRecords=[
                EternalDkpRecord("e1", "event-1", "m1000", "1:100", "award", 10),
            ],
            legacyClmGuidMemberMap={"1:099": "m1000"},
        )
        self.store.validate()

    def assert_failure_keeps_store(self, store, action, message):
        before = store.to_payload()
        with self.assertRaisesRegex(PlayerMembershipError, message):
            action()
        self.assertEqual(store.to_payload(), before)

    def test_create_player_from_active_unassigned_member_updates_all_attendance(self):
        before = self.store.to_payload()
        result = create_player_from_member(self.store, "m1002")
        self.assertEqual(self.store.to_payload(), before)
        member = next(item for item in result.members if item.memberId == "m1002")
        player = next(item for item in result.players if item.playerId == member.playerId)
        self.assertEqual((player.playerId, player.displayName, player.mainMemberId),
                         ("p0003", member.name, member.memberId))
        self.assertEqual([(item.playerId, item.attendanceType)
                          for item in result.attendance if item.memberId == "m1002"],
                         [("p0003", "unknown"), ("p0003", "unknown")])
        self.assertEqual(result.nextPlayerNumber, 4)
        self.assertIsNone(member.currentRole)

    def test_create_player_from_member_rejects_assigned_or_inactive_atomically(self):
        self.assert_failure_keeps_store(
            self.store, lambda: create_player_from_member(self.store, "m1000"),
            "bereits zugeordnet",
        )
        self.assert_failure_keeps_store(
            self.store, lambda: create_player_from_member(self.store, "m1003"),
            "nicht aktiv",
        )

    def test_assign_inactive_member_syncs_history_without_main_or_role_change(self):
        result = assign_member(self.store, "m1003", "p0001")
        self.assertEqual(result.get_player_for_member("m1003").playerId, "p0001")
        self.assertEqual(result.get_main_member("p0001").memberId, "m1000")
        self.assertEqual(next(item for item in result.members
                              if item.memberId == "m1003").lifeStatus, "inactive")
        self.assertEqual([(item.playerId, item.attendanceType)
                          for item in result.attendance if item.memberId == "m1003"],
                         [("p0001", "unknown")])
        self.assert_failure_keeps_store(
            self.store, lambda: assign_member(self.store, "m1000", "p0002"),
            "bereits zugeordnet",
        )
        self.assert_failure_keeps_store(
            self.store, lambda: assign_member(self.store, "m1002", "missing"),
            "Unbekannter Player",
        )

    def test_unassign_main_clears_only_its_player_main_and_full_history(self):
        before = self.store.to_payload()
        result = unassign_member(self.store, "m1000")
        self.assertEqual(self.store.to_payload(), before)
        self.assertIsNone(result.get_player_for_member("m1000"))
        self.assertIsNone(result.get_main_member("p0001"))
        self.assertEqual(result.get_player_for_member("m1001").playerId, "p0001")
        self.assertEqual([(item.playerId, item.attendanceType)
                          for item in result.attendance if item.memberId == "m1000"],
                         [(None, "main"), (None, "unknown")])

    def test_reassign_main_corrects_owner_history_and_preserves_other_data(self):
        before = self.store.to_payload()
        result = reassign_member(self.store, "m1000", "p0002")
        self.assertEqual(self.store.to_payload(), before)
        self.assertIsNone(result.get_main_member("p0001"))
        self.assertEqual(result.get_main_member("p0002").memberId, "m1004")
        self.assertEqual(result.get_player_for_member("m1000").playerId, "p0002")
        self.assertEqual([(item.playerId, item.attendanceType)
                          for item in result.attendance if item.memberId == "m1000"],
                         [("p0002", "main"), ("p0002", "unknown")])
        for key in ("raids", "eternalDkpRecords", "legacyClmGuidMemberMap"):
            self.assertEqual(result.to_payload()[key], before[key])
        moved = next(item for item in result.members if item.memberId == "m1000")
        self.assertEqual((moved.className, moved.clmGuid, moved.raidStartDate,
                          moved.lifeStatus),
                         ("Mage", "1:100", "2026-01-01", "active"))
        self.assert_failure_keeps_store(
            self.store, lambda: reassign_member(self.store, "m1000", "missing"),
            "Unbekannter Player",
        )

    def test_technical_member_change_does_not_reinterpret_stored_attendance(self):
        changed = copy.deepcopy(self.store)
        changed.players[0].mainMemberId = None
        changed.members[0].playerId = "p0002"
        changed.validate()
        self.assertEqual(changed.attendance[0].playerId, "p0001")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "historisch.ggc"
            save_new_identity_v2(changed, target)
            restored = load_identity_v2(target)
        self.assertEqual(restored.members[0].playerId, "p0002")
        self.assertEqual(restored.attendance[0].playerId, "p0001")
        corrected = reassign_member(restored, "m1000", "p0002")
        self.assertEqual({item.playerId for item in corrected.attendance
                          if item.memberId == "m1000"}, {"p0002"})

    def test_set_switch_and_clear_main_do_not_touch_history_or_legacy_role(self):
        self.store.members[1].currentRole = "twink"
        before_attendance = [item.to_dict() for item in self.store.attendance]
        switched = set_main(self.store, "p0001", "m1001")
        self.assertEqual(switched.get_main_member("p0001").memberId, "m1001")
        self.assertEqual(switched.get_player_for_member("m1000").playerId, "p0001")
        self.assertEqual([item.to_dict() for item in switched.attendance], before_attendance)
        self.assertEqual(switched.members[1].currentRole, "twink")
        cleared = clear_main(switched, "p0001")
        self.assertIsNone(cleared.get_main_member("p0001"))
        self.assertEqual([item.playerId for item in cleared.members[:2]],
                         ["p0001", "p0001"])
        self.assert_failure_keeps_store(
            self.store, lambda: set_main(self.store, "p0001", "m1004"),
            "gehört nicht",
        )
        self.assert_failure_keeps_store(
            self.store, lambda: set_main(self.store, "p0001", "m1002"),
            "gehört nicht",
        )
        inactive = assign_member(self.store, "m1003", "p0001")
        self.assert_failure_keeps_store(
            inactive, lambda: set_main(inactive, "p0001", "m1003"),
            "nicht aktiv",
        )

    def test_inactive_and_reactivation_keep_ownership_and_main(self):
        with_history = set_main(self.store, "p0001", "m1001", "2026-02-01")
        with_history = set_main(with_history, "p0001", "m1000", "2026-03-01")
        original = set_member_activity(with_history, "m1001", "inactive")
        original.members.append(Member(
            "m1005", "Historisch", "Mage", lifeStatus="dead",
            deathDate="2026-01-10", burialType="collective", playerId="p0001"))
        original.validate()
        before = original.to_payload()
        self.assertTrue(before["players"][0]["mainHistory"])
        inactive = set_player_activity(original, "p0001", "inactive")
        self.assertEqual({member.memberId: member.lifeStatus for member in inactive.members
                          if member.playerId == "p0001"},
                         {"m1000": "inactive", "m1001": "inactive", "m1005": "dead"})
        self.assertEqual(inactive.players[0].mainMemberId, "m1000")
        self.assertEqual([(item.memberId, item.playerId) for item in inactive.members],
                         [(item.memberId, item.playerId) for item in original.members])
        self.assertFalse(inactive.player_is_active("p0001"))
        self.assertEqual(inactive.players[0].inactiveRestoreStates,
                         {"m1000": "active", "m1001": "inactive"})
        self.assertIn("inactiveRestoreStates", inactive.to_payload()["players"][0])
        self.assertEqual(inactive.to_payload()["players"][0]["mainHistory"],
                         before["players"][0]["mainHistory"])
        for field_name in ("raids", "attendance", "eternalDkpRecords",
                           "legacyClmGuidMemberMap", "pointMode"):
            self.assertEqual(inactive.to_payload()[field_name], before[field_name])
        broken = copy.deepcopy(inactive)
        next(member for member in broken.members
             if member.memberId == "m1000").lifeStatus = "active"
        with self.assertRaisesRegex(ValueError, "aktiven Charakter"):
            broken.validate()
        profile = build_v2_player_profile(
            inactive, "p0001", project_path=None,
            attendance_adapter=V2AttendanceAdapter(inactive),
            dkp_projection=None, raid_points_projection=None,
            registry=None, roster_by_id={})
        self.assertEqual((profile.player_status, profile.profile_name,
                          profile.current_main_member_id),
                         ("inactive", "Main A", "m1000"))
        self.assertIs(set_player_activity(inactive, "p0001", "inactive"), inactive)
        self.assertEqual(original.to_payload(), before)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "inactive.ggc"
            save_new_identity_v2(inactive, target)
            reloaded = load_identity_v2(target)
        self.assertEqual(reloaded.players[0].inactiveRestoreStates,
                         inactive.players[0].inactiveRestoreStates)
        revived = set_player_activity(reloaded, "p0001", "active")
        self.assertEqual(revived.get_main_member("p0001").memberId, "m1000")
        self.assertEqual([(item.memberId, item.playerId) for item in revived.members],
                         [(item.memberId, item.playerId) for item in original.members])
        self.assertTrue(revived.player_is_active("p0001"))
        self.assertIsNone(revived.players[0].inactiveRestoreStates)
        self.assertNotIn("inactiveRestoreStates", revived.to_payload()["players"][0])
        self.assertEqual({member.memberId: member.lifeStatus for member in revived.members
                          if member.playerId == "p0001"},
                         {"m1000": "active", "m1001": "inactive", "m1005": "dead"})
        self.assertEqual(revived.players[0].mainHistory, original.players[0].mainHistory)
        self.assertEqual(revived.to_payload()["players"][0]["mainHistory"],
                         before["players"][0]["mainHistory"])
        self.assertEqual([item.to_dict() for item in revived.attendance],
                         [item.to_dict() for item in original.attendance])
        self.assertEqual(revived.eternalDkpRecords, original.eternalDkpRecords)
        self.assert_failure_keeps_store(
            self.store, lambda: set_member_activity(self.store, "m1000", "dead"),
            "active oder inactive",
        )

    def test_new_member_during_inactivity_needs_explicit_restore_decision(self):
        inactive = set_player_activity(self.store, "p0001", "inactive")
        changed = copy.deepcopy(inactive)
        changed.members.append(Member(
            "m1005", "Neu", "Mage", lifeStatus="inactive", playerId="p0001"))
        changed.validate()
        self.assert_failure_keeps_store(
            changed, lambda: set_player_activity(changed, "p0001", "active"),
            "Vorzustand")

    def test_rename_and_delete_require_valid_player_without_references(self):
        before = self.store.to_payload()
        renamed = rename_player(self.store, "p0001", "Player B")
        self.assertEqual(renamed.players[0].displayName, "Player B")
        self.assertEqual(renamed.to_payload()["members"], before["members"])
        self.assertEqual(renamed.to_payload()["attendance"], before["attendance"])
        self.assertEqual(renamed.players[0].mainMemberId, "m1000")
        self.assert_failure_keeps_store(
            self.store, lambda: rename_player(self.store, "p0001", "  "),
            "displayName",
        )
        self.assert_failure_keeps_store(
            self.store, lambda: delete_player(self.store, "p0001"),
            "besitzt noch Member",
        )
        with_empty = copy.deepcopy(self.store)
        empty = with_empty.create_player("Leer")
        deleted = delete_player(with_empty, empty.playerId)
        self.assertNotIn(empty.playerId, {item.playerId for item in deleted.players})
        self.assertEqual(deleted.nextPlayerNumber, with_empty.nextPlayerNumber)
        historical = copy.deepcopy(with_empty)
        historical.attendance[0].playerId = empty.playerId
        historical.validate()
        self.assert_failure_keeps_store(
            historical, lambda: delete_player(historical, empty.playerId),
            "historische Raid-Referenzen",
        )

    def test_multiple_operations_roundtrip_without_changing_attendance_roles(self):
        source = self.store.to_payload()
        result = create_player_from_member(self.store, "m1002")
        result = assign_member(result, "m1003", "p0003")
        result = set_member_activity(result, "m1003", "active")
        result = set_main(result, "p0003", "m1003")
        result = set_member_activity(result, "m1003", "inactive")
        player_b = result.create_player("Neuer Player")
        with self.assertRaises(PlayerMembershipError):
            reassign_member(result, "m1002", player_b.playerId)
        result = unassign_member(result, "m1003")
        self.assertIsNone(result.get_main_member("p0003"))
        self.assertIsNone(result.get_player_for_member("m1003"))
        result = reassign_member(result, "m1001", player_b.playerId)
        result = unassign_member(result, "m1001")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "phase4a2.ggc"
            save_new_identity_v2(result, target)
            restored = load_identity_v2(target)
        self.assertEqual(restored.to_payload(), result.to_payload())
        self.assertEqual(self.store.to_payload(), source)
        self.assertEqual([item.attendanceType for item in restored.attendance],
                         [item["attendanceType"] for item in source["attendance"]])
        self.assertEqual(len(restored.raids), len(self.store.raids))
        self.assertEqual(len(restored.attendance), len(self.store.attendance))

    def test_bulk_operations_commit_one_valid_copy_or_leave_source_unchanged(self):
        original = self.store.to_payload()
        self.assert_failure_keeps_store(
            self.store,
            lambda: bulk_create_players_from_members(self.store, ("m1002", "m1003")),
            "nicht aktiv",
        )
        assigned = bulk_assign_members(self.store, ("m1002", "m1003"), "p0001")
        self.assertEqual({assigned.get_player_for_member(member_id).playerId
                          for member_id in ("m1002", "m1003")}, {"p0001"})
        self.assertEqual(assigned.get_main_member("p0001").memberId, "m1000")
        self.assertEqual({item.playerId for item in assigned.attendance
                          if item.memberId in {"m1002", "m1003"}}, {"p0001"})
        inactive = set_player_activity(assigned, "p0001", "inactive")
        self.assertEqual(inactive.get_main_member("p0001").memberId, "m1000")
        self.assertFalse(inactive.player_is_active("p0001"))
        self.assertEqual(inactive.players[0].mainHistory, [])
        ready = set_member_activity(self.store, "m1003", "active")
        created = bulk_create_players_from_members(ready, ("m1002", "m1003"))
        players = {member.memberId: created.get_player_for_member(member.memberId)
                   for member in created.members if member.memberId in {"m1002", "m1003"}}
        self.assertEqual(len({player.playerId for player in players.values()}), 2)
        self.assertEqual({player.mainMemberId for player in players.values()},
                         {"m1002", "m1003"})
        self.assertEqual(self.store.to_payload(), original)


if __name__ == "__main__":
    unittest.main()
