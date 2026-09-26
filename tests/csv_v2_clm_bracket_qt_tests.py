"""Offscreen display of hard CLM bracket evidence in the shared CSV review."""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from app.csv_v2_analysis_ui import CsvV2AnalysisDialog
except ImportError:
    QApplication = CsvV2AnalysisDialog = None

from app.csv_v2_analysis import analyze_csv_raids_for_v2
from app.identity_v2 import Attendance, IdentityV2Store, Member, Raid


@unittest.skipIf(QApplication is None, "PySide6 ist lokal nicht verfügbar.")
class CsvV2ClmBracketQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "2026-04-12_BWL_Casts.csv"
        self.source.write_text('"Name","Amount"\n"Annî","1"\n',
                               encoding="utf-8")
        self.store = IdentityV2Store(
            members=[
                Member("m1000", "Annî", "Priest", clmGuid="1:1"),
                Member("m1001", "Annî", "Mage", clmGuid="1:2"),
            ],
            raids=[
                Raid("r_before", "2026-04-10", name="MC", clmRaidId="c1"),
                Raid("r_after", "2026-04-13", name="MC", clmRaidId="c2"),
            ],
            attendance=[
                Attendance("a_before", "r_before", "m1000", "unknown",
                           clmGuid="1:1"),
                Attendance("a_after", "r_after", "m1001", "unknown",
                           clmGuid="1:2"),
            ],
        )

    def test_different_endpoint_members_remain_open_and_both_visible(self):
        plan = analyze_csv_raids_for_v2(self.store, [self.source])
        dialog = CsvV2AnalysisDialog(plan)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.conflict_table.rowCount(), 1)
        context = dialog.conflict_table.item(0, 3).text()
        self.assertIn("2026-04-10: m1000", context)
        self.assertIn("2026-04-13: m1001", context)
        combo = dialog.conflict_table.cellWidget(0, 4)
        self.assertIsNone(combo.currentData())
        self.assertGreaterEqual(combo.findData("m1000"), 0)
        self.assertGreaterEqual(combo.findData("m1001"), 0)

    def test_closed_same_member_bracket_is_counted_without_dialog_choice(self):
        self.store.attendance[1].memberId = "m1000"
        self.store.attendance[1].clmGuid = "1:1"
        plan = analyze_csv_raids_for_v2(self.store, [self.source])
        dialog = CsvV2AnalysisDialog(plan)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.conflict_table.rowCount(), 0)
        self.assertEqual(len(plan.clm_bracket_matches), 1)


if __name__ == "__main__":
    unittest.main()
