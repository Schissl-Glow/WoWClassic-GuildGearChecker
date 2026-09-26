"""Read-only V2 cemetery smoke using a copied real project."""

import os
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app import GuildGearCheckerQt as checker_qt
from app.identity_v2 import IdentityV2ValidationError
from app.identity_v2_character_service import mark_member_dead, set_member_burial_type
from app.identity_v2_graveyard import repair_missing_individual_gravestones
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from app.gravestone_templates import load_gravestone_inventory


class IdentityV2GraveyardRealDataSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_reference_is_byte_equal_after_v2_cemetery_and_refresh(self):
        root = Path(__file__).resolve().parents[1]
        candidates = [*sorted((root / "testdata").glob("*.ggc")),
                      root / "BS_Neu.ggc",
                      Path.home() / "Desktop" / "BS_Neu" / "BS_V2.ggc"]
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
        if source is None:
            self.skipTest("Keine lesbare V2-Referenzdatei verfügbar.")
        source_bytes = source.read_bytes()
        original = store.to_payload()
        raids = {raid.raidId: raid.date for raid in store.raids}
        attendance_by_member: dict[str, list[str]] = {}
        for item in store.attendance:
            attendance_by_member.setdefault(item.memberId, []).append(raids[item.raidId])
        eligible = [item for item in store.members if item.lifeStatus == "active"][:2]
        if len(eligible) != 2:
            self.skipTest("Keine zwei aktiven V2-Member für temporäre Bestattungen.")
        assets = root / "assets" / "graveyard"
        templates = load_gravestone_inventory(
            assets, assets / "gravestones_manifest.json").templates
        changed = store
        for member, burial in zip(eligible, ("individual", "collective")):
            raid_days = [date.fromisoformat(value)
                         for value in attendance_by_member.get(member.memberId, ())]
            death_day = max([date.today(), *raid_days])
            changed = mark_member_dead(
                changed, member.memberId, death_day, burial,
                gravestone_templates=templates)
        changed = repair_missing_individual_gravestones(changed, templates)
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory) / "graveyard-realdata.ggc"
            save_new_identity_v2(changed, temporary)
            temp_bytes = temporary.read_bytes()
            with patch.object(checker_qt, "read_suite_settings", return_value={}):
                window = checker_qt.GuildGearCheckerQt()
            try:
                with (patch.object(checker_qt.QFileDialog, "getOpenFileName",
                                   return_value=(str(temporary), "")),
                      patch.object(checker_qt.QMessageBox, "critical") as error):
                    window.open_project()
                self.assertFalse(error.called)
                start = time.perf_counter()
                window.switch_page("graveyard")
                self.app.processEvents()
                render_seconds = time.perf_counter() - start
                individual, collective = window.v2_grave_entries
                self.assertIn(eligible[0].memberId,
                              {item.memberId for item in individual})
                self.assertIn(eligible[1].memberId,
                              {item.memberId for item in collective})
                self.assertFalse(window.identity_v2_dirty)
                self.assertEqual(temporary.read_bytes(), temp_bytes)
                switched = set_member_burial_type(
                    window.identity_v2_store, eligible[1].memberId, "individual",
                    gravestone_templates=templates)
                window._apply_v2_character_store(switched)
                window.refresh_graveyard()
                self.assertIn(eligible[1].memberId,
                              {item.memberId for item in window.v2_grave_entries[0]})
                self.assertEqual(temporary.read_bytes(), temp_bytes)
                self.assertEqual(len(switched.raids), len(store.raids))
                self.assertEqual(switched.attendance, store.attendance)
                self.assertEqual(
                    {item.memberId: (item.playerId, item.clmGuid)
                     for item in switched.members},
                    {item.memberId: (item.playerId, item.clmGuid)
                     for item in store.members})
                print(f"V2 graveyard real data ({source.name}): "
                      f"{len(individual)} individual, {len(collective)} collective, "
                      f"render {render_seconds:.3f}s")
            finally:
                with (patch.object(checker_qt, "update_suite_settings"),
                      patch.object(checker_qt.QMessageBox, "question",
                                   return_value=checker_qt.QMessageBox.StandardButton.Yes)):
                    window.close()
            self.assertEqual(load_identity_v2(temporary).to_payload(),
                             changed.to_payload())
        self.assertEqual(store.to_payload(), original)
        self.assertEqual(source.read_bytes(), source_bytes)


if __name__ == "__main__":
    unittest.main()
