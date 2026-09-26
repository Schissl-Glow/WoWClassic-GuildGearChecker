"""Temporary V2 UI edit and paste smoke against a local reference save."""

import os
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from PySide6.QtWidgets import QApplication, QTableWidgetSelectionRange
    from app.identity_v2_character_data_qt import IdentityV2CharacterDataPage
except ImportError:
    QApplication = QTableWidgetSelectionRange = IdentityV2CharacterDataPage = None

from app.identity_v2 import IdentityV2ValidationError  # noqa: E402
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 ist nicht verfügbar.")
class IdentityV2CharacterEditRealDataSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_in_memory_edits_batch_and_temp_reload_preserve_original(self):
        candidates = [
            *sorted((ROOT / "testdata").glob("*.ggc")),
            Path.home() / "Desktop" / "BS_Neu" / "BS_V2.ggc",
        ]
        source = store = None
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                store = load_identity_v2(candidate)
            except IdentityV2ValidationError:
                continue
            source = candidate
            break
        if source is None or store is None:
            self.skipTest("Keine V2-Referenzdatei verfügbar.")
        original_bytes = source.read_bytes()
        original_payload = store.to_payload()
        page = IdentityV2CharacterDataPage()
        self.addCleanup(page.close)
        page.set_store(store)
        page.status_filter.setCurrentIndex(page.status_filter.findData("active"))
        if len(page.visible_member_ids) < 5:
            self.skipTest("Weniger als fünf aktive V2-Member für den Paste-Smoke.")
        selected = page.visible_member_ids[:5]
        first = selected[0]
        table = page.table
        table.setCurrentCell(0, 0)
        table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 2), True)
        copied = page.copy_selection()
        self.assertEqual(len(copied.splitlines()), 2)

        first_gear = page.rows_by_id[first].gearStatus
        changed_gear = "Pre-BiS" if first_gear != "Pre-BiS" else "BiS"
        single_started = time.perf_counter()
        self.assertTrue(page._run_single(first, 7, changed_gear))
        single_seconds = time.perf_counter() - single_started
        page._run_single(first, 4, "Mage")
        page._run_single(first, 5, "Frost")
        page._run_single(first, 6, "dps")
        page._run_single(first, 8, "Bereit")
        page.table.setCurrentCell(page.visible_member_ids.index(first), 0)
        page.detail_note.setPlainText("Temporäre CharacterData-Notiz")
        page.note_save_button.click()
        page.confirm_check_button.click()
        self.assertEqual(page.rows_by_id[first].lastChecked, date.today().isoformat())

        table.setCurrentCell(0, 3)
        batch10_started = time.perf_counter()
        self.assertTrue(page.paste_text("\n".join(["Human\tMage"] * 5)))
        batch10_seconds = time.perf_counter() - batch10_started
        table.setCurrentCell(0, 3)
        batch20_started = time.perf_counter()
        self.assertTrue(page.paste_text("\n".join(
            ["Human\tMage\tFrost\tDPS\tBiS"] * 4)))
        batch20_seconds = time.perf_counter() - batch20_started
        self.assertEqual(page.rows_by_id[selected[1]].spec, "Frost")

        page.gear_filter.setCurrentIndex(page.gear_filter.findData("BiS"))
        self.assertIn(first, page.visible_member_ids)
        page._run_single(first, 7, "Pre-BiS")
        self.assertNotIn(first, page.visible_member_ids)
        page.gear_filter.setCurrentIndex(0)
        modified = page.store.to_payload()
        for key in ("players", "raids", "attendance", "raidCreditResolutions",
                    "eternalDkpRecords", "legacyClmGuidMemberMap"):
            self.assertEqual(modified[key], original_payload[key])
        original_members = {item["memberId"]: item for item in original_payload["members"]}
        for member in modified["members"]:
            original = original_members[member["memberId"]]
            for key in ("playerId", "lifeStatus", "deathDate", "clmGuid",
                        "continuationOfMemberId", "raidStartDate"):
                self.assertEqual(member.get(key), original.get(key))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "character-edit-smoke.ggc"
            save_new_identity_v2(page.store, target)
            self.assertEqual(load_identity_v2(target).to_payload(), modified)
        self.assertEqual(store.to_payload(), original_payload)
        self.assertEqual(source.read_bytes(), original_bytes)
        print(f"CharacterData edit real data: {len(store.members)} Members, "
              f"{len(store.attendance)} Attendance; single {single_seconds:.3f}s, "
              f"batch10 {batch10_seconds:.3f}s, batch20 {batch20_seconds:.3f}s")


if __name__ == "__main__":
    unittest.main()
