"""Focused V2 bridge checks for the existing Qt raid actions."""

import unittest

from app.identity_v2 import Attendance, IdentityV2Store, Member, Player, Raid
from app.identity_v2_raid_ui import (
    V2RaidDialogModel, apply_raid_dialog, delete_raid, raid_view,
    reset_raid_attendance, toggle_attendance,
)


class IdentityV2RaidUiTests(unittest.TestCase):
    def setUp(self):
        self.store = IdentityV2Store(
            players=[Player("p1", "Eins", "m1"), Player("p2", "Zwei", "m2")],
            members=[Member("m1", "Gleich", "Mage", playerId="p1"),
                     Member("m2", "Gleich", "Priest", playerId="p2")],
            raids=[Raid("r1", "2026-01-01", "MC", "MC Abend",
                        clmRaidId="clm-1",
                        csvSourceFiles=("MC.csv",),
                        csvReportUrls=("https://vanilla.warcraftlogs.com/reports/AAA",))],
            attendance=[Attendance("a1", "r1", "m1", "main", playerId="p1")],
        )
        self.store.validate()
        self.before = self.store.to_payload()

    def test_clm_present_and_manual_bench_stay_distinct(self):
        model = V2RaidDialogModel(self.store, "r1")
        self.assertEqual([player.playerId for player, _ in
                          model.bench_candidates_for_date("2026-01-01", {"p1"})],
                         ["p2"])
        changed, raid_id = apply_raid_dialog(
            self.store, "r1",
            ("2026-01-01", "MC Abend", "https://vanilla.warcraftlogs.com/reports/AAA", "MC"),
            {"p2"})
        self.assertEqual(raid_id, "r1")
        self.assertEqual([(entry.memberId, entry.status) for entry in changed.attendance],
                         [("m1", "present"), ("m2", "bench")])
        self.assertEqual(changed.attendance[0].attendanceId, "a1")
        self.assertEqual((changed.raids[0].clmRaidId,
                          changed.raids[0].csvSourceFiles),
                         ("clm-1", ("MC.csv",)))
        again, _ = apply_raid_dialog(
            changed, "r1", ("2026-01-01", "MC Abend",
                            "https://vanilla.warcraftlogs.com/reports/AAA", "MC"),
            {"p2"})
        self.assertEqual(len(again.attendance), 2)
        bench_id = again.attendance[1].attendanceId
        self.assertEqual(toggle_attendance(again, bench_id).attendance[1].status,
                         "present")
        self.assertEqual(toggle_attendance(
            toggle_attendance(again, bench_id), bench_id).attendance[1].status,
            "bench")
        self.assertEqual(self.store.to_payload(), self.before)

    def test_create_edit_reset_delete_preserve_v2_references(self):
        created, raid_id = apply_raid_dialog(
            self.store, None, ("2026-01-02", "BWL", "", "BWL"), {"p2"})
        self.assertTrue(any(raid.raidId == raid_id for raid in created.raids))
        self.assertEqual(next(entry.status for entry in created.attendance
                              if entry.raidId == raid_id), "bench")
        edited, _ = apply_raid_dialog(
            created, raid_id,
            ("2026-01-03", "BWL neu", "https://vanilla.warcraftlogs.com/reports/BBB", "BWL"),
            {"p2"})
        raid = next(item for item in edited.raids if item.raidId == raid_id)
        self.assertEqual((raid.date, raid.name), ("2026-01-03", "BWL neu"))
        self.assertEqual(raid_view(raid).warcraftLogsUrl,
                         "https://vanilla.warcraftlogs.com/reports/BBB")
        attendance_id = next(entry.attendanceId for entry in edited.attendance
                             if entry.raidId == raid_id)
        edited.raidPoints.set_adjustment(attendance_id, 3, "Test")
        reset = reset_raid_attendance(edited, raid_id)
        self.assertFalse(any(entry.raidId == raid_id for entry in reset.attendance))
        self.assertNotIn(attendance_id, reset.raidPoints.adjustments)
        self.assertTrue(any(item.raidId == raid_id for item in reset.raids))
        deleted = delete_raid(reset, raid_id)
        self.assertFalse(any(item.raidId == raid_id for item in deleted.raids))
        self.assertEqual([(entry.raidId, entry.memberId)
                          for entry in deleted.attendance], [("r1", "m1")])
        self.assertEqual(self.store.to_payload(), self.before)


if __name__ == "__main__":
    unittest.main()
