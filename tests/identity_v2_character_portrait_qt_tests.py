"""Project-scoped ID portrait resolution in the V2 character detail."""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

from app.identity_v2 import IdentityV2Store, Member
from app.identity_v2_character_data_qt import IdentityV2CharacterDataPage


class IdentityV2CharacterPortraitQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_living_and_dead_same_names_resolve_only_project_member_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "Portraits_V2.ggc"
            portraits = root / "portraits"
            portraits.mkdir()
            for filename in ("m1000.png", "m1002.png", "Sorap.png"):
                Image.new("RGB", (48, 64), "#705746").save(portraits / filename)
            store = IdentityV2Store(members=[
                Member("m1000", "Sorap", "Mage"),
                Member("m1001", "Sorap", "Mage"),
                Member("m1002", "Sorap", "Mage", lifeStatus="dead",
                       burialType="individual", deathDate="2026-03-01"),
            ])
            page = IdentityV2CharacterDataPage()
            self.addCleanup(page.close)
            page.set_project_path(project)
            page.set_store(store)
            self.assertEqual(page._portrait_path(page.rows_by_id["m1000"]),
                             portraits / "m1000.png")
            self.assertIsNone(page._portrait_path(page.rows_by_id["m1001"]))
            self.assertEqual(page._portrait_path(page.rows_by_id["m1002"]),
                             portraits / "m1002.png")
            self.assertTrue((portraits / "Sorap.png").is_file())
            page.set_project_path(None)
            self.assertIsNone(page._portrait_path(page.rows_by_id["m1000"]))


if __name__ == "__main__":
    unittest.main()
