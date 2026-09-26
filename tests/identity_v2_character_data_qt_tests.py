"""Offscreen checks for the read-only V2 character-data page."""

import copy
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QAbstractItemView
    from app.identity_v2_character_data_qt import (
        COLUMN_ORDER_SETTING, COLUMN_WIDTHS_SETTING, COLUMNS, DETAIL_VISIBLE_SETTING,
        SPLITTER_SIZES_SETTING, IdentityV2CharacterDataPage,
    )
except ImportError:
    Qt = QApplication = QAbstractItemView = IdentityV2CharacterDataPage = None

from app.identity_v2 import Attendance, EternalDkpRecord, IdentityV2Store, Member, Player, Raid
from app.identity_v2_dkp import IdentityV2DkpProjection
from app.i18n import tr


def sample_store() -> IdentityV2Store:
    store = IdentityV2Store(
        players=[Player("p1", "Besitzer", "m1")],
        members=[
            Member("m1", "Alpha", "Mage", playerId="p1", currentRole="twink",
                   race="Human", spec="Frost", raidRole="dps",
                   gearStatus="BiS", raidStatus="Bereit", note="Arkan"),
            Member("m2", "Bravo", "Priest", playerId="p1", currentRole="main",
                   race="Dwarf", spec="Holy", raidRole="healer"),
            Member("m3", "Charlie", None, note="Neuer Charakter"),
            Member("m4", "Delta", "Warrior", lifeStatus="inactive",
                   gearStatus="Pre-BiS"),
            Member("m5", "Echo", "Hunter", lifeStatus="dead",
                   deathDate="2026-03-15", burialType="individual"),
        ],
        raids=[Raid("r1", "2026-01-30"), Raid("r2", "2026-02-01")],
        attendance=[Attendance("a1", "r1", "m1", "unknown", playerId="p1"),
                    Attendance("a2", "r2", "m1", "unknown", playerId="p1")],
    )
    store.validate()
    return store


@unittest.skipIf(QApplication is None, "PySide6 ist nicht verfügbar.")
class IdentityV2CharacterDataQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.store = sample_store()
        self.page = IdentityV2CharacterDataPage()
        self.addCleanup(self.page.close)
        self.page.set_store(self.store)

    def test_character_detail_shows_separate_dkp_and_raid_values(self):
        self.store.members[0].clmGuid = "1:1"
        self.store.eternalDkpRecords.append(
            EternalDkpRecord("d1", "e1", "m1", "1:1", "award", 100))
        points = SimpleNamespace(
            character_points=lambda member_id: 80,
            eternal_character_points=lambda member_id: 80,
        )
        projection = IdentityV2DkpProjection(
            self.store, available_by_member={"m1": 12},
            raid_points_projection=points)
        self.page.table.setCurrentCell(self.row_for("m1"), 0)
        self.page.set_dkp_projection(projection)
        values = self.page.detail_values
        self.assertEqual(values["available_dkp"].text(), "12")
        self.assertEqual(values["eternal_dkp"].text(), "100")
        self.assertEqual(values["dkp_rank"].text(), "Holz 1")
        self.assertEqual(values["raid_rank"].text(), "Holz 1")

    def row_for(self, member_id: str) -> int:
        return self.page.visible_member_ids.index(member_id)

    def test_read_only_columns_and_derived_identity(self):
        table = self.page.table
        self.assertEqual(table.columnCount(), 12)
        self.assertEqual(table.horizontalHeaderItem(11).text(),
                         tr("identity_v2_character_data.column_dead"))
        for column in (0, 1, 2, 9, 10, 11):
            self.assertFalse(table.item(self.row_for("m1"), column).flags()
                             & Qt.ItemFlag.ItemIsEditable)
        for column in (3, 4, 5, 6, 7, 8):
            self.assertTrue(table.item(self.row_for("m1"), column).flags()
                            & Qt.ItemFlag.ItemIsEditable)
        self.assertEqual(table.item(self.row_for("m1"), 1).text(), "Besitzer")
        self.assertEqual(table.item(self.row_for("m1"), 2).text(), "Main")
        self.assertEqual(table.item(self.row_for("m2"), 2).text(), "Twink")
        self.assertEqual(table.item(self.row_for("m3"), 1).text(),
                         tr("identity_v2_character_data.unknown_player"))
        self.assertEqual(table.item(self.row_for("m3"), 4).text(),
                         tr("identity_v2_character_data.unknown_class"))
        self.assertEqual(table.item(self.row_for("m5"), 11).text(),
                         tr("identity_v2_character_data.dead"))
        self.assertEqual(table.item(self.row_for("m4"), 11).text(), "☠")
        self.assertIn(table.item(self.row_for("m1"), 10).text(),
                      ("01.02.2026", "2026-02-01"))
        before = self.store.to_payload()
        self.page._sort_by_column(11)
        self.assertIsNone(self.page._sort_state)
        self.assertEqual(self.store.to_payload(), before)

    def test_status_search_and_gear_filter_share_one_visible_order(self):
        self.assertEqual(len(self.page.visible_member_ids), 5)
        self.page.status_filter.setCurrentIndex(self.page.status_filter.findData("active"))
        self.assertEqual(self.page.visible_member_ids, ("m1", "m2", "m3"))
        self.page.status_filter.setCurrentIndex(self.page.status_filter.findData("inactive"))
        self.assertEqual(self.page.visible_member_ids, ("m4",))
        self.page.status_filter.setCurrentIndex(self.page.status_filter.findData("graveyard"))
        self.assertEqual(self.page.visible_member_ids, ("m5",))
        self.assertNotIn("m5", ("m4",))
        self.page.status_filter.setCurrentIndex(0)
        self.page.search.setText("besitzer")
        self.assertEqual(self.page.visible_member_ids, ("m1", "m2"))
        self.page.search.setText("arkan")
        self.assertEqual(self.page.visible_member_ids, ("m1",))
        self.page.search.clear()
        self.page.gear_filter.setCurrentIndex(self.page.gear_filter.findData("Pre-BiS"))
        self.assertEqual(self.page.visible_member_ids, ("m4",))

    def test_table_detail_navigation_sort_and_filtered_fallback(self):
        self.page.table.setCurrentCell(self.row_for("m2"), 0)
        self.assertEqual((self.page.selected_member_id, self.page.detail_name.text()),
                         ("m2", "Bravo"))
        self.page.next_button.click()
        self.assertEqual(self.page.selected_member_id, "m3")
        self.assertEqual(self.page.table.currentRow(), self.row_for("m3"))
        self.page.previous_button.click()
        self.assertEqual(self.page.selected_member_id, "m2")
        self.page._sort_by_column(0)
        self.page._sort_by_column(0)
        self.assertEqual(self.page.selected_member_id, "m2")
        self.assertEqual(self.page.table.currentRow(), self.row_for("m2"))
        self.page.next_button.click()
        self.assertEqual(self.page.selected_member_id,
                         self.page.visible_member_ids[self.row_for("m2") + 1])
        self.page.status_filter.setCurrentIndex(self.page.status_filter.findData("graveyard"))
        self.assertEqual((self.page.selected_member_id, self.page.detail_name.text()),
                         ("m5", "Echo"))
        self.assertEqual(self.page.visible_member_ids, ("m5",))
        self.page.search.setText("kein treffer")
        self.assertEqual(self.page.visible_member_ids, ())
        self.assertIsNone(self.page.selected_member_id)
        self.assertEqual(self.page.detail_name.text(),
                         tr("identity_v2_character_data.empty"))
        self.assertFalse(self.page.next_button.isEnabled())

    def test_refresh_preserves_id_and_order_until_next_header_click(self):
        self.page._sort_by_column(4)
        before = self.page.visible_member_ids
        self.page.table.setCurrentCell(self.row_for("m3"), 0)
        changed = copy.deepcopy(self.store)
        changed.members[2].className = "Warlock"
        changed.validate()
        self.page.set_store(changed)
        self.assertEqual(self.page.visible_member_ids, before)
        self.assertEqual(self.page.selected_member_id, "m3")
        self.page._sort_by_column(4)
        self.assertNotEqual(self.page.visible_member_ids, before)
        self.assertEqual(self.page.selected_member_id, "m3")

    def test_date_sort_uses_iso_dates_instead_of_localized_display(self):
        changed = copy.deepcopy(self.store)
        changed.members[0].lastChecked = "2026-03-01"
        changed.members[1].lastChecked = "2026-02-10"
        changed.validate()
        self.page.set_store(changed)
        self.page._sort_by_column(9)
        self.assertLess(self.page.visible_member_ids.index("m2"),
                        self.page.visible_member_ids.index("m1"))

    def test_detail_toggle_and_settings_restore(self):
        self.page.resize(1550, 850)
        self.page.show()
        self.app.processEvents()
        self.page.table.setCurrentCell(self.row_for("m2"), 0)
        self.page.details_button.setChecked(False)
        self.app.processEvents()
        self.assertFalse(self.page.detail_panel.isVisible())
        self.assertGreater(self.page.table.width(), 1000)
        self.page.table.setColumnWidth(0, 225)
        header = self.page.table.horizontalHeader()
        header.moveSection(header.visualIndex(3), 1)
        header.moveSection(header.visualIndex(11), 0)
        self.assertEqual(header.visualIndex(11), 11)
        self.page.details_button.setChecked(True)
        self.page.splitter.setSizes([1000, 400])
        self.app.processEvents()
        self.assertEqual(self.page.detail_name.text(), "Bravo")
        saved = self.page.layout_settings()
        self.assertEqual(saved[COLUMN_WIDTHS_SETTING][0], 225)
        self.assertEqual(saved[COLUMN_ORDER_SETTING][-1], "dead")
        self.assertTrue(saved[DETAIL_VISIBLE_SETTING])
        restored = IdentityV2CharacterDataPage(saved)
        restored.resize(1550, 850)
        restored.set_store(self.store)
        restored.show()
        self.app.processEvents()
        try:
            self.assertEqual(restored.table.columnWidth(0), 225)
            self.assertEqual(restored.layout_settings()[COLUMN_ORDER_SETTING],
                             saved[COLUMN_ORDER_SETTING])
            self.assertAlmostEqual(
                restored.layout_settings()[SPLITTER_SIZES_SETTING][0] /
                sum(restored.layout_settings()[SPLITTER_SIZES_SETTING]),
                saved[SPLITTER_SIZES_SETTING][0] /
                sum(saved[SPLITTER_SIZES_SETTING]), places=2)
            restored.details_button.setChecked(False)
            hidden = restored.layout_settings()
        finally:
            restored.close()
        reopened = IdentityV2CharacterDataPage(hidden)
        reopened.set_store(self.store)
        self.addCleanup(reopened.close)
        self.assertFalse(reopened.details_button.isChecked())

    def test_old_or_partial_layout_settings_keep_dead_column_last_and_narrow(self):
        page = IdentityV2CharacterDataPage({
            COLUMN_ORDER_SETTING: ["dead", "race", "name"],
            COLUMN_WIDTHS_SETTING: [210, 150, 100, 90, 80, 90, 90, 90, 90, 90, 90, 2000],
        })
        self.addCleanup(page.close)
        page.set_store(self.store)
        settings = page.layout_settings()
        self.assertEqual(settings[COLUMN_ORDER_SETTING][:2], ["race", "name"])
        self.assertEqual(settings[COLUMN_ORDER_SETTING][-1], "dead")
        self.assertLessEqual(page.table.columnWidth(11), 90)


if __name__ == "__main__":
    unittest.main()
