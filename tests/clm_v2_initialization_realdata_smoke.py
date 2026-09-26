"""Optional full initialization smoke; all separation decisions are TEST ONLY."""

import json
import tempfile
import unittest
from pathlib import Path

from app.clm_identity_v2_decisions import NEW_CHARACTER, ClmIdentityDecisionDraft
from app.clm_identity_v2_materialization import finalized_clm_character_groups
from app.clm_v2_initialization import (
    analyze_clm_v2_selection, build_new_clm_v2_guild, inspect_clm_v2_source,
    summarize_clm_v2_initialization,
)
from app.identity_v2_storage import load_identity_v2, save_identity_v2, save_new_identity_v2
from app.identity_v2_import_choices import CharacterImportChoice
from app.clm_raid_v2_materialization import suggest_clm_raid_type


class ClmV2InitializationRealDataSmoke(unittest.TestCase):
    def test_reference_lua_end_to_end_with_test_only_decisions(self):
        source = Path(__file__).resolve().parents[1] / "testdata" / "ClassicLootManager.lua"
        if not source.is_file():
            self.skipTest("Die optionale lokale ClassicLootManager.lua fehlt.")
        original = source.read_bytes()
        inspection = inspect_clm_v2_source(source)
        analysis = analyze_clm_v2_selection(
            inspection, "exp0 alliance stitches bierstube", "1730228604",
        )

        # TEST ONLY: Separate every successor GUID. The Qt workflow never makes
        # these choices and always requires the user's confirmed decision set.
        draft = ClmIdentityDecisionDraft(analysis.identity_analysis)
        for group in analysis.identity_analysis.multi_guid_groups:
            for history in group.guid_histories[1:]:
                draft.set_choice(group.normalized_name, history.guid, NEW_CHARACTER)
        decisions = draft.to_decision_set()
        # TESTONLY: all finalized groups are classified active, player unknown.
        classifications = {
            chain: CharacterImportChoice()
            for _name, chain in finalized_clm_character_groups(
                analysis.identity_analysis, decisions,
            )
        }
        store = build_new_clm_v2_guild(
            analysis, decisions, classifications=classifications,
            require_classifications=True,
            raid_types={raid.raid_id: suggest_clm_raid_type(raid.name) or "MC"
                        for raid in analysis.raids},
        )
        summary = summarize_clm_v2_initialization(store, analysis, decisions)

        self.assertEqual(summary.members, len(analysis.identity_analysis.guid_histories))
        self.assertEqual((summary.raids, summary.attendance), (251, 6324))
        self.assertEqual((summary.main, summary.twink, summary.unknown),
                         (0, 0, summary.attendance))
        self.assertEqual(summary.members_with_raid_start, 273)
        self.assertEqual(summary.members_without_raid_start, summary.members - 273)
        self.assertEqual(len(store.players), 0)
        self.assertTrue(all(member.playerId is None and member.currentRole is None
                            and member.lifeStatus == "active" for member in store.members))
        self.assertTrue(all(item.playerId is None for item in store.attendance))
        self.assertTrue(all(item.attendanceType == "unknown" for item in store.attendance))

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "Neu_V2.ggc"
            save_new_identity_v2(store, target)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), store.to_payload())
            restored = load_identity_v2(target)
            self.assertEqual((len(restored.members), len(restored.raids),
                              len(restored.attendance), len(restored.eternalDkpRecords)),
                             (len(store.members), len(store.raids),
                              len(store.attendance), len(store.eternalDkpRecords)))
            self.assertEqual({item.memberId: item.raidStartDate for item in restored.members},
                             {item.memberId: item.raidStartDate for item in store.members})
            self.assertEqual(restored.legacyClmGuidMemberMap, store.legacyClmGuidMemberMap)
            self.assertTrue(all(item.attendanceType == "unknown"
                                for item in restored.attendance))
            save_identity_v2(restored, target)
            self.assertEqual(load_identity_v2(target).to_payload(), store.to_payload())
        self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
