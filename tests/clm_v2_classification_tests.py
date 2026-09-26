"""Final CLM group classification after GUID continuation review."""

import tempfile
import unittest
from pathlib import Path

from app.clm_identity_v2_decisions import CONTINUE, ClmIdentityDecisionDraft
from app.clm_identity_v2_materialization import (
    ClmMaterializationError, finalized_clm_character_groups,
)
from app.clm_v2_initialization import (
    analyze_clm_v2_selection, build_new_clm_v2_guild, inspect_clm_v2_source,
)
from app.identity_v2_import_choices import CharacterImportChoice
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from tests.clm_v2_initialization_tests import synthetic_lua


class ClmV2ClassificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = self.root / "ClassicLootManager.lua"
        source.write_text(synthetic_lua(), encoding="utf-8")
        self.analysis = analyze_clm_v2_selection(
            inspect_clm_v2_source(source),
            "exp0 alliance stitches bierstube", "10",
        )
        draft = ClmIdentityDecisionDraft(self.analysis.identity_analysis)
        draft.set_choice("Annî", "1:102", CONTINUE)
        self.decisions = draft.to_decision_set()
        self.groups = finalized_clm_character_groups(
            self.analysis.identity_analysis, self.decisions,
        )

    def test_ignore_final_continuation_group_keeps_raid_and_other_attendance(self):
        choices = {
            chain: (CharacterImportChoice(relevance="irrelevant")
                    if name == "Annî"
                    else CharacterImportChoice(activity_status="inactive"))
            for name, chain in self.groups
        }
        result = build_new_clm_v2_guild(
            self.analysis, self.decisions,
            classifications=choices, require_classifications=True,
            raid_types={raid.raid_id: "MC" for raid in self.analysis.raids},
        )
        self.assertEqual([item.name for item in result.members], ["Jêmma"])
        self.assertEqual(result.members[0].lifeStatus, "inactive")
        self.assertIsNone(result.members[0].deathDate)
        self.assertEqual(len(result.raids), 1)
        self.assertEqual(len(result.attendance), 1)
        self.assertEqual(result.attendance[0].memberId, result.members[0].memberId)
        self.assertEqual(len(result.ignoredClmCharacterGroups), 1)
        self.assertEqual(set(result.ignoredClmCharacterGroups[0].clmGuids),
                         {"1:101", "1:102"})
        self.assertEqual(result.eternalDkpRecords, [])
        self.assertTrue(result.is_clm_character_group_ignored(["1:101", "1:102"]))
        self.assertFalse(result.is_clm_character_group_ignored(["1:201"]))
        before = result.to_payload()
        result.members[0].lifeStatus = "active"
        result.validate()
        self.assertEqual(result.members[0].raidStartDate,
                         before["members"][0]["raidStartDate"])
        target = self.root / "ignored.ggc"
        save_new_identity_v2(result, target)
        self.assertEqual(load_identity_v2(target).to_payload(), result.to_payload())

    def test_classification_must_cover_every_final_group_when_required(self):
        with self.assertRaisesRegex(ClmMaterializationError, "Importklassifikationen"):
            build_new_clm_v2_guild(
                self.analysis, self.decisions,
                classifications={}, require_classifications=True,
                raid_types={raid.raid_id: "MC" for raid in self.analysis.raids},
            )

    def test_ignore_registry_is_guid_group_scoped_and_revocable(self):
        choices = {
            chain: CharacterImportChoice()
            for _name, chain in self.groups
        }
        result = build_new_clm_v2_guild(
            self.analysis, self.decisions,
            classifications=choices, require_classifications=True,
            raid_types={raid.raid_id: "MC" for raid in self.analysis.raids},
        )
        self.assertEqual(
            {item.name: item.className for item in result.members},
            {"Annî": "Priest", "Jêmma": "Mage"},
        )
        result.ignore_clm_character_group("Anderer Annî", ["1:999"])
        self.assertTrue(result.is_clm_character_group_ignored(["1:999"]))
        self.assertFalse(result.is_clm_character_group_ignored(["1:101", "1:102"]))
        result.unignore_clm_character_group(["1:999"])
        self.assertFalse(result.is_clm_character_group_ignored(["1:999"]))

    def test_all_groups_irrelevant_keep_clm_raid_without_attendance(self):
        choices = {
            chain: CharacterImportChoice(relevance="irrelevant")
            for _name, chain in self.groups
        }
        result = build_new_clm_v2_guild(
            self.analysis, self.decisions,
            classifications=choices, require_classifications=True,
            raid_types={raid.raid_id: "MC" for raid in self.analysis.raids},
        )
        self.assertEqual(result.members, [])
        self.assertEqual(len(result.raids), 1)
        self.assertEqual(result.attendance, [])
        self.assertEqual(result.eternalDkpRecords, [])
        self.assertEqual(len(result.ignoredClmCharacterGroups), 2)


if __name__ == "__main__":
    unittest.main()
