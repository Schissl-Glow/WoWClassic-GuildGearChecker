"""Optional read-only display smoke against the user's new V2 guild save."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from app.identity_v2_views_qt import IdentityV2RaidPage, IdentityV2RosterPage
except ImportError:
    QApplication = IdentityV2RaidPage = IdentityV2RosterPage = None

from app.identity_v2_storage import load_identity_v2, save_identity_v2
from app.identity_v2_views import IdentityV2ViewData


@unittest.skipIf(QApplication is None, "PySide6 ist lokal nicht verfügbar.")
class IdentityV2ViewsRealDataSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_real_v2_save_is_displayed_without_changes(self):
        source = Path.home() / "Desktop" / "BS_Neu" / "BS_V2.ggc"
        if not source.is_file():
            self.skipTest("Der optionale lokale BS_V2.ggc-Save fehlt.")
        before = source.read_bytes()
        store = load_identity_v2(source)
        data = IdentityV2ViewData.from_store(store)
        roster = IdentityV2RosterPage()
        raids = IdentityV2RaidPage()
        self.addCleanup(roster.close)
        self.addCleanup(raids.close)
        roster.set_view_data(data)
        raids.set_view_data(data)

        self.assertEqual(roster.table.rowCount(), len(store.members))
        self.assertEqual(raids.raid_table.rowCount(), len(store.raids))
        self.assertEqual(sum(row.participant_count for row in data.raids),
                         len(store.attendance))
        self.assertEqual(sum(row.raid_start_date is not None for row in data.roster),
                         sum(member.raidStartDate is not None for member in store.members))
        names = [row.name for row in data.roster]
        self.assertIn("\u00c2nn\u00ed", names)
        self.assertEqual(names.count("B\u00e4m\u00e4r\u00e4ng"), 2)
        self.assertEqual(names.count("Veniell"), 2)
        expected = store.to_payload()
        with tempfile.TemporaryDirectory() as directory:
            copied_save = Path(directory) / source.name
            shutil.copy2(source, copied_save)
            save_identity_v2(store, copied_save)
            restored = load_identity_v2(copied_save)
        self.assertEqual(restored.to_payload(), expected)
        self.assertEqual((len(restored.players), len(restored.members),
                          len(restored.raids), len(restored.attendance)),
                         (len(store.players), len(store.members),
                          len(store.raids), len(store.attendance)))
        self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
