"""Optional read-only raid preflight for the unversioned CLM reference."""

import unittest
from pathlib import Path

from app.clm_identity_v2_decisions import CONTINUE, NEW_CHARACTER, ClmIdentityDecisionDraft
from app.clm_raid_v2_analysis import analyze_clm_raid_file


class ClmRaidV2RealDataSmoke(unittest.TestCase):
    def test_reference_raid_analysis_is_consistent_and_read_only(self):
        source = Path(__file__).resolve().parents[1] / "testdata" / "ClassicLootManager.lua"
        if not source.is_file():
            self.skipTest("Die optionale lokale ClassicLootManager.lua fehlt.")
        before = source.read_bytes()
        result = analyze_clm_raid_file(source)
        summary = result.summary
        self.assertGreater(summary["raids"], 0)
        self.assertEqual(summary["technicalIgnoredGuidReferences"],
                         len(result.identity_analysis.ignored_technical_guids))
        self.assertEqual(summary["sameRaidCoexistencePairs"],
                         len(result.identity_analysis.raid_coexistence))
        self.assertGreater(summary["benchOnlyGuidRaidReferences"], 0)
        self.assertLessEqual(summary["participantGuidsWithoutValidP0"],
                             summary["participatingGuids"])
        self.assertEqual(summary["uniqueGuidAttendances"],
                         sum(len(raid.participants) for raid in result.raids))
        self.assertEqual(summary["uniqueGuidAttendances"],
                         sum(summary[key] for key in (
                             "p2MainAttendances", "p2TwinkAttendances",
                             "p2UnknownAttendances",
                         )))
        self.assertEqual(result.old_identity_event_count - result.current_identity_event_count,
                         sum(item.count for item in result.old_only_events)
                         - result.current_only_event_count)
        self.assertTrue(all(item.opcode not in {"AC", "AS", "AU", "AE", "DR"}
                            for item in result.old_only_events))
        self.assertTrue(all(len({item.guid for item in raid.participants})
                            == len(raid.participants) for raid in result.raids))
        for name in ("Annî", "Bämäräng"):
            self.assertTrue(result.identity_analysis.histories_for_name(name))
        draft = ClmIdentityDecisionDraft(result.identity_analysis)
        collision = next(item for item in result.identity_analysis.raid_coexistence
                         if item.normalized_name == "Veniell")
        self.assertEqual(collision.guids,
                         ("5220:64163203", "5220:74395471"))
        self.assertEqual(draft.allowed_actions("Veniell", collision.guids[1]),
                         (NEW_CHARACTER,))
        self.assertIn("SAME_RAID_COEXISTENCE",
                      result.identity_analysis.group_for_name("Veniell").conflicts)
        self.assertIn("Gleichzeitig im selben Raid",
                      draft.rows_for("Veniell")[1].analysis)
        self.assertEqual(draft.allowed_actions("Annî", "5220:71819705"),
                         (CONTINUE, NEW_CHARACTER))
        self.assertEqual(draft.allowed_actions("Bämäräng", "5220:75232381"),
                         (NEW_CHARACTER,))
        self.assertFalse(any(item.normalized_name in {"Annî", "Bämäräng"}
                             for item in result.identity_analysis.raid_coexistence))
        self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
