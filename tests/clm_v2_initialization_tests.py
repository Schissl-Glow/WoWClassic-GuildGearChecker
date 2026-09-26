"""Focused end-to-end tests for creating a new V2 guild from Lua."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.clm_identity_v2_decisions import CONTINUE, ClmIdentityDecisionDraft
from app.clm_v2_initialization import (
    analyze_clm_v2_selection, build_clm_v2_characters,
    build_new_clm_v2_guild as build_reviewed_guild, inspect_clm_v2_source,
    summarize_clm_v2_initialization, verify_existing_clm_characters,
)
from app.clm_raid_v2_materialization import materialize_clm_raids_into_identity_v2
from app.identity_v2_raid_points import V2RaidPointProjection
from app.identity_v2 import IdentityV2Store, IdentityV2ValidationError, Member
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2


def build_new_clm_v2_guild(analysis, decisions, **kwargs):
    return build_reviewed_guild(
        analysis, decisions, raid_types={raid.raid_id: "MC" for raid in analysis.raids},
        **kwargs)


def stamp(day: int, hour: int = 12) -> int:
    return int(datetime(2025, 1, day, hour, tzinfo=timezone.utc).timestamp())


def synthetic_lua() -> str:
    raid_time = stamp(5)
    raid_id = f"{raid_time}-0-1-10"
    return f'''CLM2_DB = {{
      ["exp0 alliance stitches bierstube"] = {{ ledger = {{
        {{ _a=1, _b=0, _c={stamp(1)}, _d="R0", _e=1, r=10, n="Bierstube", p=0 }},
        {{ _a=2, _b=0, _c={stamp(1, 9)}, _d="P0", _e=1,
           g={{1,101}}, n="Annî-Stitches", c=5 }},
        {{ _a=3, _b=0, _c={stamp(1, 10)}, _d="R9", _e=1, r=10, p={{{{1,101}}}} }},
        {{ _a=4, _b=0, _c={stamp(2)}, _d="DM", _e=1,
           r=10, p={{{{1,101}}}}, v=10, t="Bonus", n=false }},
        {{ _a=5, _b=0, _c={stamp(3)}, _d="P1", _e=1, g={{1,101}} }},
        {{ _a=6, _b=0, _c={stamp(4, 9)}, _d="P0", _e=1,
           g={{1,102}}, n="Annî-Stitches", c=5 }},
        {{ _a=7, _b=0, _c={stamp(4, 10)}, _d="R9", _e=1, r=10, p={{{{1,102}}}} }},
        {{ _a=8, _b=0, _c={stamp(1, 11)}, _d="P0", _e=1,
           g={{1,201}}, n="Jêmma-Stitches", c=8 }},
        {{ _a=9, _b=0, _c={stamp(1, 12)}, _d="R9", _e=1, r=10, p={{{{1,201}}}} }},
        {{ _a=10, _b=0, _c={raid_time}, _d="AC", _e=1, r=10, n="MC", c={{}} }},
        {{ _a=11, _b=0, _c={stamp(5, 13)}, _d="AS", _e=1,
           r="{raid_id}", p={{{{1,102}},{{1,201}}}}, s={{}} }},
        {{ _a=12, _b=0, _c={stamp(5, 14)}, _d="AE", _e=1, r="{raid_id}" }},
      }} }},
      ["exp0 alliance stitches triumph"] = {{ ledger = {{
        {{ _a=1, _b=0, _c={stamp(1)}, _d="R0", _e=2, r=20, n="Triumph", p=0 }},
      }} }},
    }}'''


class ClmV2InitializationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / "ClassicLootManager.lua"
        self.source.write_text(synthetic_lua(), encoding="utf-8")

    def analyzed(self):
        inspection = inspect_clm_v2_source(self.source)
        analysis = analyze_clm_v2_selection(
            inspection, "exp0 alliance stitches bierstube", "10",
        )
        return inspection, analysis

    def reviewed(self, analysis):
        draft = ClmIdentityDecisionDraft(analysis.identity_analysis)
        draft.set_choice("Annî", "1:102", CONTINUE)
        return draft.to_decision_set()

    def test_explicit_database_roster_selection_and_full_new_store(self):
        source_before = self.source.read_bytes()
        inspection, analysis = self.analyzed()
        self.assertEqual(len(inspection.databases), 2)
        self.assertEqual([item.roster_id for item in inspection.eligible_rosters(
            "exp0 alliance stitches bierstube")], ["10"])
        self.assertEqual(analysis.database_id, "exp0 alliance stitches bierstube")
        self.assertEqual(analysis.identity_analysis.database_id, analysis.database_id)
        decisions = self.reviewed(analysis)
        store = build_new_clm_v2_guild(analysis, decisions)
        self.assertEqual(len(store.members), 2)
        annie = next(item for item in store.members if item.name == "Annî")
        self.assertEqual((annie.className, annie.clmGuid), ("Priest", "1:102"))
        self.assertEqual(store.legacyClmGuidMemberMap, {"1:101": annie.memberId})
        self.assertEqual(store.eternal_dkp_for_member(annie.memberId), 10)
        self.assertEqual(len(store.raids), 1)
        self.assertEqual(len(store.attendance), 2)
        self.assertEqual({item.attendanceType for item in store.attendance}, {"unknown"})
        self.assertEqual(annie.raidStartDate, "2025-01-05")
        self.assertEqual(store.players, [])
        self.assertTrue(all(item.playerId is None and item.currentRole is None
                            and item.lifeStatus == "active" for item in store.members))
        self.assertEqual(self.source.read_bytes(), source_before)

    def test_summary_and_cancel_before_save_create_no_file(self):
        _inspection, analysis = self.analyzed()
        decisions = self.reviewed(analysis)
        store = build_new_clm_v2_guild(analysis, decisions)
        summary = summarize_clm_v2_initialization(store, analysis, decisions)
        self.assertEqual((summary.members, summary.primary_guids,
                          summary.legacy_guid_mappings, summary.multi_guid_decisions),
                         (2, 2, 1, 1))
        self.assertEqual((summary.raids, summary.attendance, summary.unknown), (1, 2, 2))
        self.assertEqual((summary.members_with_raid_start, summary.members_without_raid_start),
                         (2, 0))
        self.assertEqual(list(self.root.glob("*.ggc")), [])

    def test_missing_decision_or_nonempty_target_leaves_target_unchanged(self):
        _inspection, analysis = self.analyzed()
        empty = IdentityV2Store()
        before = empty.to_payload()
        with self.assertRaisesRegex(ValueError, "Annî"):
            build_new_clm_v2_guild(analysis, None, target_store=empty)
        self.assertEqual(empty.to_payload(), before)
        nonempty = IdentityV2Store(members=[Member("m1000", "Bestehend", "Mage")])
        before = nonempty.to_payload()
        with self.assertRaisesRegex(ValueError, "leeren"):
            build_new_clm_v2_guild(analysis, self.reviewed(analysis), target_store=nonempty)
        self.assertEqual(nonempty.to_payload(), before)

    def test_invalid_lua_creates_no_partial_guild(self):
        self.source.write_text("this is not CLM2_DB", encoding="utf-8")
        with self.assertRaises(ValueError):
            inspect_clm_v2_source(self.source)
        self.assertEqual(list(self.root.glob("*.ggc")), [])

    def test_new_file_save_load_and_exclusive_existing_file_protection(self):
        _inspection, analysis = self.analyzed()
        store = build_new_clm_v2_guild(analysis, self.reviewed(analysis))
        target = self.root / "Neue_Gilde_V2.ggc"
        save_new_identity_v2(store, target)
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(payload["identityFormat"], "identity-v2")
        restored = load_identity_v2(target)
        self.assertEqual(restored.to_payload(), store.to_payload())
        before = target.read_bytes()
        with self.assertRaises(IdentityV2ValidationError):
            save_new_identity_v2(store, target)
        self.assertEqual(target.read_bytes(), before)

        legacy = self.root / "Alte_Gilde.ggc"
        legacy.write_text('{"members": [{"id": "m1", "name": "Alt"}]}', encoding="utf-8")
        before = legacy.read_bytes()
        with self.assertRaises(IdentityV2ValidationError):
            save_new_identity_v2(store, legacy)
        self.assertEqual(legacy.read_bytes(), before)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_character_only_save_then_same_lua_resume_without_duplicates(self):
        _inspection, analysis = self.analyzed()
        characters = build_clm_v2_characters(analysis, self.reviewed(analysis))
        self.assertEqual((len(characters.members), len(characters.raids),
                          len(characters.attendance)), (2, 0, 0))
        target = self.root / "character_only.ggc"
        save_new_identity_v2(characters, target)
        reopened = load_identity_v2(target)
        _inspection, repeated_analysis = self.analyzed()
        verify_existing_clm_characters(reopened, repeated_analysis)
        self.assertEqual([member.memberId for member in reopened.members],
                         [member.memberId for member in characters.members])
        choice = {raid.raid_id: "MC" for raid in repeated_analysis.raids}
        imported = materialize_clm_raids_into_identity_v2(reopened, repeated_analysis, choice)
        again = materialize_clm_raids_into_identity_v2(imported, repeated_analysis)
        self.assertEqual(again.to_payload(), imported.to_payload())
        self.assertEqual((len(again.members), len(again.raids), len(again.attendance)),
                         (2, 1, 2))
        self.assertIsNotNone(V2RaidPointProjection(again))


if __name__ == "__main__":
    unittest.main()
