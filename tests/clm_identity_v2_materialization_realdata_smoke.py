"""Optional read-only preflight for the local CLM reference file."""

import unittest
from dataclasses import replace
from pathlib import Path

from app.clm_identity_v2_analysis import analyze_clm_file
from app.clm_identity_v2_decisions import (
    CONTINUE, NEW_CHARACTER, ClmIdentityDecisionDraft,
)
from app.clm_identity_v2_materialization import (
    ClmMaterializationError, build_identity_v2_store_from_clm,
)
from app.clm_matching import character_key


class ClmIdentityV2MaterializationRealDataSmoke(unittest.TestCase):
    def test_current_reference_has_only_open_multi_guid_decisions(self):
        source = Path(__file__).resolve().parents[1] / "testdata" / "ClassicLootManager.lua"
        if not source.is_file():
            self.skipTest("Die optionale lokale ClassicLootManager.lua fehlt.")
        before = source.read_bytes()
        analysis = analyze_clm_file(source)
        self.assertEqual(analysis.summary["guids"], 289)
        self.assertEqual(analysis.summary["incompleteP0Ignored"], 1)
        self.assertEqual(analysis.summary["technicalGuidsIgnored"], 1)
        self.assertEqual(analysis.summary["dataConflictGuids"], 0)
        ignored = analysis.ignored_technical_guids[0]
        self.assertEqual((ignored.guid, ignored.warning),
                         ("5220:0", "TECHNICAL_GUID_IGNORED"))
        self.assertEqual(ignored.source_references,
                         ("P0.s:1786132643-0-5220-28316593",))
        self.assertNotIn("5220:0", {history.guid for history in analysis.guid_histories})
        repaired = next(history for history in analysis.guid_histories
                        if history.guid == "5220:79773579")
        self.assertEqual((repaired.normalized_name, repaired.character_class),
                         ("Ânní", "Priest"))
        self.assertEqual(repaired.incomplete_p0_count, 1)
        self.assertEqual(repaired.incomplete_p0_events[0].original_name,
                         "Unbekannt-Stitches")
        self.assertEqual(repaired.incomplete_p0_events[0].missing_fields, ("class",))
        self.assertIn("INCOMPLETE_P0_IGNORED", repaired.warnings)
        self.assertNotIn("DATA_CONFLICT", repaired.warnings)
        by_guid = {history.guid: history for history in analysis.guid_histories}
        self.assertEqual(by_guid["5220:31982722"].eternal_dkp_total, 119)
        self.assertEqual(by_guid["5220:71544211"].eternal_dkp_total, 150)
        draft = ClmIdentityDecisionDraft(analysis)
        self.assertEqual(len(draft.group_order), len(analysis.multi_guid_groups))
        self.assertIsNone(draft.choice("Annî", "5220:71819705"))
        self.assertEqual(draft.allowed_actions("Annî", "5220:71819705"),
                         (CONTINUE, NEW_CHARACTER))
        self.assertEqual(draft.allowed_actions("Bämäräng", "5220:75232381"),
                         (NEW_CHARACTER,))
        with self.assertRaisesRegex(ClmMaterializationError, "Annî"):
            build_identity_v2_store_from_clm(analysis)

        multi_names = {character_key(group.normalized_name) for group in analysis.multi_guid_groups}
        singles = replace(
            analysis,
            guid_histories=tuple(history for history in analysis.guid_histories
                                 if history.normalized_name
                                 and character_key(history.normalized_name) not in multi_names),
            multi_guid_groups=(),
        )
        store = build_identity_v2_store_from_clm(singles)
        self.assertEqual(len(store.members), analysis.summary["singleGuidNames"])
        self.assertEqual(len(store.players), 0)
        self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
