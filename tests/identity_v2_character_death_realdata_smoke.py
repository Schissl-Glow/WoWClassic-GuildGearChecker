"""Temporary V2 death UI smoke; never writes the source project."""

import os
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from PySide6.QtWidgets import QApplication
    from app.identity_v2_character_data_qt import IdentityV2CharacterDataPage
except ImportError:
    QApplication = IdentityV2CharacterDataPage = None

from app.identity_v2 import IdentityV2ValidationError  # noqa: E402
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 ist nicht verfügbar.")
class IdentityV2CharacterDeathRealDataSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_death_on_in_memory_reference_and_temp_save(self):
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
            self.skipTest("Keine lokale V2-Referenzdatei verfügbar.")
        original_bytes = source.read_bytes()
        original_payload = store.to_payload()
        raids_by_id = {raid.raidId: raid for raid in store.raids}
        attendance_by_member: dict[str, list] = {}
        for entry in store.attendance:
            attendance_by_member.setdefault(entry.memberId, []).append(entry)
        selected = None
        dates = []
        active = sorted((member for member in store.members if member.lifeStatus == "active"),
                        key=lambda member: -len(attendance_by_member.get(member.memberId, ())))
        for member in active:
            try:
                candidate_dates = [date.fromisoformat(raids_by_id[entry.raidId].date)
                                   for entry in attendance_by_member.get(member.memberId, ())]
            except (KeyError, TypeError, ValueError):
                continue
            selected, dates = member, candidate_dates
            break
        if selected is None:
            self.skipTest("Kein geeigneter aktiver Member für den Todes-Smoke.")
        death_day = max(dates) if dates else date.today()
        page = IdentityV2CharacterDataPage()
        self.addCleanup(page.close)
        page.set_store(store)
        page.status_filter.setCurrentIndex(page.status_filter.findData("active"))
        page.table.setCurrentCell(page.visible_member_ids.index(selected.memberId), 0)
        changed_stores = []
        page.storeChanged.connect(changed_stores.append)
        if dates:
            before = page.store.to_payload()
            with (patch.object(page, "_choose_death_details",
                               return_value=(min(dates) - timedelta(days=1), "individual")),
                  patch("app.identity_v2_character_data_qt.QMessageBox.warning") as warning):
                self.assertFalse(page._request_death_for_member(selected.memberId))
                self.assertTrue(warning.called)
            self.assertEqual(page.store.to_payload(), before)
            self.assertEqual(changed_stores, [])

        started = time.perf_counter()
        with patch.object(page, "_choose_death_details", return_value=(death_day, "collective")):
            page.mark_dead_button.click()
        elapsed = time.perf_counter() - started
        self.assertEqual(len(changed_stores), 1)
        self.assertNotIn(selected.memberId, page.visible_member_ids)
        page.status_filter.setCurrentIndex(page.status_filter.findData("graveyard"))
        self.assertIn(selected.memberId, page.visible_member_ids)
        changed_member = next(member for member in page.store.members
                              if member.memberId == selected.memberId)
        self.assertEqual((changed_member.lifeStatus, changed_member.deathDate,
                          changed_member.playerId),
                         ("dead", death_day.isoformat(), selected.playerId))
        changed = page.store.to_payload()
        for key in ("raids", "attendance", "raidCreditResolutions",
                    "eternalDkpRecords", "legacyClmGuidMemberMap"):
            self.assertEqual(changed[key], original_payload[key])
        old_mains = {player["playerId"]: player["mainMemberId"]
                     for player in original_payload["players"]}
        for player in changed["players"]:
            expected = (None if old_mains[player["playerId"]] == selected.memberId
                        else old_mains[player["playerId"]])
            self.assertEqual(player["mainMemberId"], expected)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "death-ui-smoke.ggc"
            save_new_identity_v2(page.store, target)
            self.assertEqual(load_identity_v2(target).to_payload(), changed)
        self.assertEqual(store.to_payload(), original_payload)
        self.assertEqual(source.read_bytes(), original_bytes)
        print(f"CharacterData death real data ({source.name}): {len(store.members)} Members, "
              f"{len(store.attendance)} Attendance; UI death {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
