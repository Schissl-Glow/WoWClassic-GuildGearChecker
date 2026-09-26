"""Optional class and revocable, source-specific ignore registries."""

import json
import tempfile
import unittest
from pathlib import Path

from app.identity_v2 import IdentityV2Store, Member, Raid
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from app.identity_v2_views import IdentityV2ViewData


class IdentityV2SourcesAndIgnoreTests(unittest.TestCase):
    def test_unknown_class_and_source_labels_roundtrip(self):
        store = IdentityV2Store(
            members=[Member("m1000", "Neuling", None, lifeStatus="inactive")],
            raids=[
                Raid("r_clm", "2026-04-20", name="MC", clmRaidId="clm1"),
                Raid("r_csv", "2026-04-21", name="AQ20",
                     csvSourceFiles=("AQ20_Casts.csv",)),
                Raid("r_both", "2026-04-22", name="Onyxia", clmRaidId="clm2",
                     csvSourceFiles=("Report.csv",),
                     csvReportUrls=("https://vanilla.warcraftlogs.com/reports/a",)),
            ],
        )
        view = IdentityV2ViewData.from_store(store)
        self.assertIsNone(view.roster[0].class_name)
        self.assertEqual({row.raid_id: row.source for row in view.raids},
                         {"r_clm": "CLM", "r_csv": "CSV", "r_both": "CLM + CSV"})
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "v2.ggc"
            save_new_identity_v2(store, target)
            self.assertIsNone(json.loads(target.read_text(encoding="utf-8"))
                              ["members"][0]["className"])
            loaded = load_identity_v2(target)
            self.assertEqual(loaded.to_payload(), store.to_payload())
            self.assertIsNone(loaded.members[0].className)

    def test_csv_ignore_is_exact_and_reversible(self):
        store = IdentityV2Store()
        store.ignore_csv_character("Bífi")
        self.assertTrue(store.is_csv_character_ignored("BÍFI"))
        self.assertFalse(store.is_csv_character_ignored("Bifibifi"))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "ignore.ggc"
            save_new_identity_v2(store, target)
            loaded = load_identity_v2(target)
            self.assertTrue(loaded.is_csv_character_ignored("Bífi"))
            loaded.unignore_csv_character("Bífi")
            self.assertFalse(loaded.is_csv_character_ignored("Bífi"))

    def test_clm_ignore_is_guid_group_scoped(self):
        store = IdentityV2Store()
        store.ignore_clm_character_group("Veniell", ("1:101", "1:102"))
        self.assertTrue(store.is_clm_character_group_ignored(("1:101", "1:102")))
        self.assertFalse(store.is_clm_character_group_ignored(("1:201",)))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "groups.ggc"
            save_new_identity_v2(store, target)
            loaded = load_identity_v2(target)
            self.assertTrue(loaded.is_clm_character_group_ignored(("1:101", "1:102")))
            loaded.unignore_clm_character_group(("1:101", "1:102"))
            self.assertFalse(loaded.ignoredClmCharacterGroups)


if __name__ == "__main__":
    unittest.main()
