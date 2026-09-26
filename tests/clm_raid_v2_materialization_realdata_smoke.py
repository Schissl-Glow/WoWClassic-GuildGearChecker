"""Optional read-only Lua smoke with explicit test-only identity decisions."""

import unittest
from pathlib import Path

from app.clm_identity_v2_decisions import NEW_CHARACTER, ClmIdentityDecisionDraft
from app.clm_identity_v2_materialization import build_identity_v2_store_from_clm
from app.clm_raid_v2_analysis import analyze_clm_raid_file
from app.clm_raid_v2_materialization import (
    materialize_clm_raids_into_identity_v2, suggest_clm_raid_type,
)


class ClmRaidV2MaterializationRealDataSmoke(unittest.TestCase):
    def test_reference_materializes_only_in_memory_with_test_separation(self):
        source = Path(__file__).resolve().parents[1] / "testdata" / "ClassicLootManager.lua"
        if not source.is_file():
            self.skipTest("Die optionale lokale ClassicLootManager.lua fehlt.")
        before = source.read_bytes()
        analysis = analyze_clm_raid_file(source)

        # Test strategy only: keep every multi-GUID incarnation separate.
        # These are no saved or production identity decisions.
        draft = ClmIdentityDecisionDraft(analysis.identity_analysis)
        for group in analysis.identity_analysis.multi_guid_groups:
            for history in group.guid_histories[1:]:
                draft.set_choice(group.normalized_name, history.guid, NEW_CHARACTER)
        identity_store = build_identity_v2_store_from_clm(
            analysis.identity_analysis, draft.to_decision_set(),
        )
        identity_before = identity_store.to_payload()
        result = materialize_clm_raids_into_identity_v2(
            identity_store, analysis,
            {raid.raid_id: suggest_clm_raid_type(raid.name) or "MC"
             for raid in analysis.raids})

        self.assertEqual(identity_store.to_payload(), identity_before)
        self.assertEqual(len(result.members), len(analysis.identity_analysis.guid_histories))
        self.assertEqual(len(result.raids), len(analysis.raids))
        self.assertEqual(len(result.attendance), analysis.summary["uniqueGuidAttendances"])
        self.assertTrue(all(item.attendanceType == "unknown" for item in result.attendance))
        self.assertEqual(
            {member.memberId: (member.clmGuid, member.className) for member in result.members},
            {member.memberId: (member.clmGuid, member.className)
             for member in identity_store.members},
        )
        self.assertEqual(result.legacyClmGuidMemberMap,
                         identity_store.legacyClmGuidMemberMap)
        self.assertEqual({item.clmGuid for item in result.attendance},
                         {participant.guid for raid in analysis.raids
                          for participant in raid.participants})
        attended_ids = {item.memberId for item in result.attendance}
        self.assertEqual(len(attended_ids), analysis.summary["participatingGuids"])
        self.assertEqual(attended_ids,
                         {member.memberId for member in result.members if member.raidStartDate})
        self.assertEqual(sum(member.raidStartDate is None for member in result.members),
                         len(result.members) - len(attended_ids))
        self.assertEqual(min(raid.date for raid in result.raids), "2024-11-15")
        self.assertEqual(max(raid.date for raid in result.raids), "2026-09-22")
        self.assertEqual(result.players, [])

        owners = {member.clmGuid: member for member in result.members}
        old_annie = owners["5220:31982722"]
        new_annie = owners["5220:71819705"]
        self.assertNotEqual(old_annie.memberId, new_annie.memberId)
        self.assertEqual(sum(item.memberId == old_annie.memberId for item in result.attendance), 6)
        self.assertEqual(sum(item.memberId == new_annie.memberId for item in result.attendance), 0)
        self.assertEqual(old_annie.raidStartDate, "2025-07-29")
        self.assertIsNone(new_annie.raidStartDate)

        druid = owners["5220:71544211"]
        paladin = owners["5220:75232381"]
        self.assertNotEqual(druid.memberId, paladin.memberId)
        self.assertEqual(sum(item.memberId == druid.memberId for item in result.attendance), 11)
        self.assertEqual(sum(item.memberId == paladin.memberId for item in result.attendance), 5)

        collision = analysis.identity_analysis.raid_coexistence[0]
        raid = next(item for item in result.raids if item.clmRaidId == collision.raid_id)
        in_raid = [item for item in result.attendance if item.raidId == raid.raidId
                   and item.clmGuid in collision.guids]
        self.assertEqual(len(in_raid), 2)
        self.assertEqual(len({item.memberId for item in in_raid}), 2)
        self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
