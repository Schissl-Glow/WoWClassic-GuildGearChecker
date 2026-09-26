"""Optional read-only check against the local, unversioned CLM reference."""

import unittest
from pathlib import Path

from app.clm_identity_v2_analysis import analyze_clm_file
from app.clm_identity_v2_decisions import CONTINUE, NEW_CHARACTER, ClmIdentityDecisionDraft


class ClmIdentityV2RealDataSmoke(unittest.TestCase):
    def test_multi_guid_review_accepts_current_reference_without_writes(self):
        source = Path(__file__).resolve().parents[1] / "testdata" / "ClassicLootManager.lua"
        if not source.is_file():
            self.skipTest("Die optionale lokale ClassicLootManager.lua fehlt.")
        before = source.read_bytes()
        analysis = analyze_clm_file(source)
        draft = ClmIdentityDecisionDraft(analysis)
        self.assertEqual(len(draft.group_order), len(analysis.multi_guid_groups))
        self.assertEqual(len(draft.group_order), 14)  # current reference, never production logic
        names = set(draft.group_order)
        for column in range(9):
            draft.sort_groups(column)
            self.assertEqual(set(draft.group_order), names)
        self.assertEqual(draft.allowed_actions("Annî", "5220:71819705"),
                         (CONTINUE, NEW_CHARACTER))
        self.assertEqual(draft.rows_for("Annî")[1].distance, "261 Tage")
        self.assertEqual(draft.allowed_actions("Bämäräng", "5220:75232381"),
                         (NEW_CHARACTER,))
        self.assertEqual(draft.rows_for("Bämäräng")[1].distance, "22 Sekunden")
        self.assertIn("Klassenkonflikt", draft.rows_for("Bämäräng")[1].analysis)
        self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
