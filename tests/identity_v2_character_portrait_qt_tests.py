"""Project-scoped ID portrait resolution in the V2 character detail."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox

from app.identity_v2 import IdentityV2Store, Member
from app.identity_v2_character_data_qt import IdentityV2CharacterDataPage
from app.identity_v2_storage import save_new_identity_v2
from app.GuildPortraitGrabberQt import GuildPortraitGrabberQt


class _PortraitWorker:
    def __init__(self, _events):
        self.commands = []

    def start(self):
        pass

    def submit(self, action, **payload):
        self.commands.append((action, payload))

    def request_batch_cancel(self):
        pass


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

    def test_irrelevant_member_never_enters_grabber_or_missing_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "portrait-candidates.ggc"
            store = IdentityV2Store(members=[
                Member("m1000", "Normal", "Mage", race="Human"),
                Member("m1001", "Portchar", "Mage", race="Human",
                       irrelevant=True),
                Member("m1002", "Buffchar", "Priest", race="Human",
                       lifeStatus="inactive", irrelevant=True),
            ])
            save_new_identity_v2(store, project)
            window = GuildPortraitGrabberQt(
                project, worker_factory=_PortraitWorker,
                config_data={
                    "region": "EU", "realm": "stitches",
                    "game_version": "classic1x", "browser_channel": "msedge",
                    "capture_mode": "playwright", "wait_after_load": 1.25,
                    "standard_wait_after_open": 6.0,
                    "screen_region": {"x": 10, "y": 20, "width": 300, "height": 525},
                    "crop": {"x1": 0.2, "y1": 0.1, "x2": 0.8, "y2": 0.9},
                },
            )
            self.addCleanup(window.close)
            self.assertTrue(window.v2_mode)
            self.assertEqual([item.id for item in window.character_members], ["m1000"])
            self.assertNotIn("m1001", window._member_by_id)
            self.assertEqual(window.inactive_character_members, [])
            with patch("app.GuildPortraitGrabberQt.QMessageBox.question",
                       return_value=QMessageBox.StandardButton.Yes):
                self.assertTrue(window.capture_missing_portraits())
            action, payload = window.worker.commands[-1]
            self.assertEqual(action, "capture_all")
            self.assertEqual(payload["names"], ["Normal"])
            self.assertEqual(payload["character_records"], [
                {"memberId": "m1000", "characterName": "Normal"},
            ])


if __name__ == "__main__":
    unittest.main()
