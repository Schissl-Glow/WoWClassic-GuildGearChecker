"""Focused format and lossless V2 project persistence checks."""

import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from app.clm_identity_v2_decisions import CONTINUE, ClmIdentityDecisionDraft
from app.clm_v2_initialization import (
    analyze_clm_v2_selection, build_new_clm_v2_guild, inspect_clm_v2_source,
)
from app.identity_v2 import IdentityV2Store, IdentityV2ValidationError
from app.identity_v2_storage import load_identity_v2, save_identity_v2, save_new_identity_v2
from tests.clm_v2_initialization_tests import synthetic_lua


class IdentityV2ProjectTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        source = self.root / "ClassicLootManager.lua"
        source.write_text(synthetic_lua(), encoding="utf-8")
        inspection = inspect_clm_v2_source(source)
        analysis = analyze_clm_v2_selection(
            inspection, "exp0 alliance stitches bierstube", "10",
        )
        draft = ClmIdentityDecisionDraft(analysis.identity_analysis)
        draft.set_choice("Annî", "1:102", CONTINUE)
        self.store = build_new_clm_v2_guild(
            analysis, draft.to_decision_set(),
            raid_types={raid.raid_id: "MC" for raid in analysis.raids})

    def test_full_v2_load_save_load_roundtrip_preserves_free_text_and_all_records(self):
        self.store.raids[0].name = "MC mit Leerzeichen  "
        self.store.eternalDkpRecords[0].description = "Bonus  "
        expected = self.store.to_payload()
        target = self.root / "Neu_V2.ggc"
        save_new_identity_v2(self.store, target)
        first = load_identity_v2(target)
        self.assertEqual(first.to_payload(), expected)
        save_identity_v2(first, target)
        self.assertEqual(load_identity_v2(target).to_payload(), expected)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), expected)

    def test_save_as_creates_another_v2_without_changing_original(self):
        original = self.root / "Original.ggc"
        save_new_identity_v2(self.store, original)
        before = original.read_bytes()
        copy = self.root / "Kopie.ggc"
        save_identity_v2(load_identity_v2(original), copy)
        self.assertEqual(load_identity_v2(copy).to_payload(), self.store.to_payload())
        self.assertEqual(original.read_bytes(), before)

    def test_clm_configuration_is_project_data_and_missing_lua_is_allowed(self):
        self.store.clmLuaPath = str(self.root / "missing" / "ClassicLootManager.lua")
        self.store.clmDatabaseId = "database-42"
        self.store.clmRosterId = "roster-7"
        self.store.clmRosterName = "Raidgruppe"
        target = self.root / "Gilde.ggc"
        save_new_identity_v2(self.store, target)
        with patch("app.clm_savedvariables.load_saved_variables",
                   side_effect=AssertionError("Lua beim Projektöffnen gelesen")):
            loaded = load_identity_v2(target)
        self.assertEqual((loaded.clmLuaPath, loaded.clmDatabaseId,
                          loaded.clmRosterId, loaded.clmRosterName),
                         (self.store.clmLuaPath, "database-42", "roster-7", "Raidgruppe"))
        another = IdentityV2Store.from_payload(self.store.to_payload())
        another.guildName = "Andere Gilde"
        another.clmLuaPath = str(self.root / "other" / "ClassicLootManager.lua")
        another.clmDatabaseId = "database-99"
        another.clmRosterId = "roster-9"
        second_target = self.root / "Andere.ggc"
        save_new_identity_v2(another, second_target)
        self.assertEqual(load_identity_v2(target).clmDatabaseId, "database-42")
        self.assertEqual(load_identity_v2(second_target).clmDatabaseId, "database-99")
        old_payload = self.store.to_payload()
        for field_name in ("clmLuaPath", "clmDatabaseId", "clmRosterId"):
            old_payload.pop(field_name)
        target.write_text(json.dumps(old_payload), encoding="utf-8")
        older = load_identity_v2(target)
        self.assertIsNone(older.clmLuaPath)
        self.assertIsNone(older.clmDatabaseId)
        self.assertIsNone(older.clmRosterId)

    def test_legacy_file_is_never_replaced_by_v2_save(self):
        legacy = self.root / "Legacy.ggc"
        legacy.write_text('{"members": []}', encoding="utf-8")
        before = legacy.read_bytes()
        with self.assertRaises(IdentityV2ValidationError):
            save_identity_v2(self.store, legacy)
        self.assertEqual(legacy.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
