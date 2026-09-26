"""Read-only UI and timing smoke against a local Identity V2 reference."""

import os
import sys
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from PySide6.QtWidgets import QApplication
    from app.identity_v2_character_data_qt import (
        COLUMN_WIDTHS_SETTING, IdentityV2CharacterDataPage,
    )
except ImportError:
    QApplication = IdentityV2CharacterDataPage = None

from app.identity_v2 import IdentityV2ValidationError  # noqa: E402
from app.identity_v2_storage import load_identity_v2  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 ist nicht verfügbar.")
class IdentityV2CharacterDataRealDataSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_reference_ui_is_read_only_and_responsive(self):
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
        page = IdentityV2CharacterDataPage()
        self.addCleanup(page.close)
        page.resize(1600, 900)
        started = time.perf_counter()
        page.set_store(store)
        page.show()
        self.app.processEvents()
        open_seconds = time.perf_counter() - started
        self.assertEqual(len(page.visible_member_ids), len(store.members))

        filter_started = time.perf_counter()
        for status, expected in (
            ("active", sum(item.lifeStatus == "active" for item in store.members)),
            ("inactive", sum(item.lifeStatus == "inactive" for item in store.members)),
            ("graveyard", sum(item.lifeStatus == "dead" for item in store.members)),
            ("all", len(store.members)),
        ):
            page.status_filter.setCurrentIndex(page.status_filter.findData(status))
            self.assertEqual(len(page.visible_member_ids), expected)
        filter_seconds = time.perf_counter() - filter_started

        search_started = time.perf_counter()
        chosen = store.members[0]
        page.search.setText(chosen.name)
        self.assertIn(chosen.memberId, page.visible_member_ids)
        page.search.clear()
        search_seconds = time.perf_counter() - search_started

        sort_started = time.perf_counter()
        for column in (0, 1, 10):
            page._sort_by_column(column)
            self.assertEqual(len(page.visible_member_ids), len(store.members))
        sort_seconds = time.perf_counter() - sort_started

        detail_started = time.perf_counter()
        page.table.setCurrentCell(0, 0)
        selected = page.selected_member_id
        page.details_button.setChecked(False)
        self.assertFalse(page.detail_panel.isVisible())
        page.details_button.setChecked(True)
        self.assertEqual(page.selected_member_id, selected)
        if len(page.visible_member_ids) > 1:
            page.next_button.click()
            self.assertEqual(page.selected_member_id, page.visible_member_ids[1])
            page.previous_button.click()
            self.assertEqual(page.selected_member_id, selected)
        detail_seconds = time.perf_counter() - detail_started

        page.table.setColumnWidth(0, 222)
        page.splitter.setSizes([1100, 400])
        settings = page.layout_settings()
        restored = IdentityV2CharacterDataPage(settings)
        restored.resize(1600, 900)
        restored.set_store(store)
        restored.show()
        self.app.processEvents()
        try:
            self.assertEqual(restored.table.columnWidth(0),
                             settings[COLUMN_WIDTHS_SETTING][0])
            self.assertEqual(len(restored.visible_member_ids), len(store.members))
        finally:
            restored.close()
        self.assertEqual(store.to_payload(), original_payload)
        self.assertEqual(source.read_bytes(), original_bytes)
        print(f"CharacterData UI real data: {len(store.members)} Members; "
              f"open {open_seconds:.3f}s, filters {filter_seconds:.3f}s, "
              f"search {search_seconds:.3f}s, sorts {sort_seconds:.3f}s, "
              f"detail {detail_seconds:.3f}s")


if __name__ == "__main__":
    unittest.main()
