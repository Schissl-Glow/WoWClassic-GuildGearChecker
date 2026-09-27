"""Offscreen checks for the read-only V2 character-data page."""

import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (QApplication, QAbstractItemView, QDialog,
                                   QLabel, QMessageBox, QWidget)
    from app.identity_v2_character_data_qt import (
        COLUMN_ORDER_SETTING, COLUMN_WIDTHS_SETTING, COLUMNS, DETAIL_VISIBLE_SETTING,
        SPLITTER_SIZES_SETTING, AddCharacterDialog, IdentityV2CharacterDataPage,
    )
except ImportError:
    Qt = QApplication = QAbstractItemView = IdentityV2CharacterDataPage = None

from app.identity_v2 import Attendance, EternalDkpRecord, IdentityV2Store, Member, Player, Raid
from app.identity_v2_dkp import IdentityV2DkpProjection
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from app.project_storage import member_portrait_path
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

    def test_raid_column_reuses_detail_count_and_sorts_numerically(self):
        changed = copy.deepcopy(self.store)
        for number in range(3, 13):
            changed.raids.append(Raid(f"r{number}", "2026-04-01"))
            changed.attendance.append(Attendance(
                f"a{number}", f"r{number}", "m2", "main", playerId="p1"))
        changed.validate()
        self.page.set_store(changed)
        column = COLUMNS.index("raid_count")
        self.assertEqual(column, COLUMNS.index("last_raid") + 1)
        self.assertEqual(self.page.table.horizontalHeaderItem(column).text(),
                         tr("identity_v2_character_data.column_raid_count"))
        self.assertEqual(self.page.table.item(self.row_for("m1"), column).text(), "2")
        self.assertEqual(self.page.detail_values["raid_count"].text(), "2")
        self.page.table.setCurrentCell(self.row_for("m2"), 0)
        self.assertEqual(self.page.table.item(self.row_for("m2"), column).text(), "10")
        self.assertEqual(self.page.detail_values["raid_count"].text(), "10")
        self.page._sort_by_column(column)
        self.assertLess(self.row_for("m1"), self.row_for("m2"))
        self.page._sort_by_column(column)
        self.assertLess(self.row_for("m2"), self.row_for("m1"))

    def test_irrelevant_filter_and_restore_keep_character_editable(self):
        changed = copy.deepcopy(self.store)
        changed.members[2].irrelevant = True
        changed.validate()
        self.page.set_store(changed)
        self.page.status_filter.setCurrentIndex(
            self.page.status_filter.findData("irrelevant"))
        self.assertEqual(self.page.visible_member_ids, ("m3",))
        self.assertIn(tr("identity_v2_character_data.filter_irrelevant"),
                      self.page.detail_status.text())
        self.assertFalse(self.page.restore_relevant_button.isHidden())
        self.assertTrue(self.page._run_single("m3", 4, "Mage"))
        self.assertEqual(self.page.rows_by_id["m3"].className, "Mage")
        self.page._restore_relevant()
        self.assertFalse(self.page.store.members[2].irrelevant)
        self.assertEqual(self.page.visible_member_ids, ())
        self.page.status_filter.setCurrentIndex(
            self.page.status_filter.findData("active"))
        self.assertIn("m3", self.page.visible_member_ids)
        self.page.status_filter.setCurrentIndex(
            self.page.status_filter.findData("inactive"))
        self.assertEqual(self.page.visible_member_ids, ("m4",))
        self.page.status_filter.setCurrentIndex(
            self.page.status_filter.findData("graveyard"))
        self.assertEqual(self.page.visible_member_ids, ("m5",))

    def test_compact_summary_keeps_navigation_outside_scroll(self):
        self.page.resize(1040, 620)
        self.page.show()
        self.app.processEvents()
        nav = self.page.detail_panel.findChild(QWidget, "characterDetailNavigation")
        self.assertIsNotNone(nav)
        self.assertLessEqual(nav.y() + nav.height(),
                             self.page.detail_panel.height())
        self.assertGreater(self.page.detail_scroll.verticalScrollBar().maximum(), 0)
        original_y = nav.y()
        self.page.detail_scroll.verticalScrollBar().setValue(
            self.page.detail_scroll.verticalScrollBar().maximum())
        self.app.processEvents()
        self.assertEqual(nav.y(), original_y)
        self.assertTrue(self.page.detail_values["dkp_rank"].isHidden())
        for key in ("last_checked", "last_raid", "raid_count", "death_date",
                    "available_dkp", "eternal_dkp"):
            self.assertFalse(self.page.detail_values[key].isHidden())
            self.assertEqual(self.page.overview_form.getWidgetPosition(
                self.page.detail_values[key])[0], -1)
        self.page.set_active_point_system("eternal_dkp")
        self.assertTrue(self.page.detail_values["dkp_rank"].isHidden())
        for key in ("available_dkp", "eternal_dkp"):
            self.assertFalse(self.page.detail_values[key].isHidden())

    def test_add_dialog_offers_unknown_player_and_existing_main_twink(self):
        dialog = AddCharacterDialog(self.store, self.page)
        self.addCleanup(dialog.close)
        self.assertIsNone(dialog.player_choice.currentData())
        self.assertFalse(dialog.role_choice.isEnabled())
        dialog.player_choice.setCurrentIndex(dialog.player_choice.findData("p1"))
        self.assertTrue(dialog.role_choice.isEnabled())
        self.assertEqual(dialog.role_choice.currentData(), "twink")
        dialog.name_edit.setText("Neue Figur")
        dialog.class_choice.setCurrentIndex(dialog.class_choice.findData("Mage"))
        self.assertEqual(dialog.values(), ("Neue Figur", "Mage", "p1", "twink"))
        dialog.player_choice.setCurrentIndex(0)
        self.assertEqual(dialog.values()[2:], (None, None))

    def test_manual_add_selects_new_member_without_raid_side_effects(self):
        changes = []
        self.page.storeChanged.connect(changes.append)
        with patch("app.identity_v2_character_data_qt.AddCharacterDialog") as factory:
            dialog = factory.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.values.return_value = ("Neu", "Mage", "p1", "twink")
            self.assertTrue(self.page._add_character())
        self.assertEqual(len(changes), 1)
        self.assertEqual(self.page.selected_member_id, "m1000")
        self.assertEqual(self.page.detail_name.text(), "Neu")
        self.assertEqual(self.page.table.item(
            self.page.table.currentRow(), 0).data(Qt.ItemDataRole.UserRole), "m1000")
        self.assertEqual(self.page.store.members[-1].playerId, "p1")
        self.assertEqual(self.page.store.attendance, self.store.attendance)
        self.assertEqual(self.page.store.eternalDkpRecords, self.store.eternalDkpRecords)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "manual.ggc"
            save_new_identity_v2(self.page.store, target)
            self.assertEqual(load_identity_v2(target).members[-1].name, "Neu")

        with patch("app.identity_v2_character_data_qt.AddCharacterDialog") as factory:
            dialog = factory.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.values.return_value = ("Ohne Spieler", None, None, None)
            self.assertTrue(self.page._add_character())
        self.assertEqual(self.page.selected_member_id, "m1001")
        self.assertIsNone(self.page.store.members[-1].playerId)

        before = self.page.store.to_payload()
        with (patch("app.identity_v2_character_data_qt.AddCharacterDialog") as factory,
              patch("app.identity_v2_character_data_qt.QMessageBox.warning")):
            dialog = factory.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.values.return_value = ("ALPHA", "Mage", None, None)
            self.assertFalse(self.page._add_character())
        self.assertEqual(self.page.store.to_payload(), before)

    def test_manual_main_selection_respects_confirmation(self):
        before = self.page.store.to_payload()
        with (patch("app.identity_v2_character_data_qt.AddCharacterDialog") as factory,
              patch("app.identity_v2_character_data_qt.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.No)):
            dialog = factory.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.values.return_value = ("Neuer Main", "Priest", "p1", "main")
            self.assertFalse(self.page._add_character())
        self.assertEqual(self.page.store.to_payload(), before)
        with (patch("app.identity_v2_character_data_qt.AddCharacterDialog") as factory,
              patch("app.identity_v2_character_data_qt.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.Yes)):
            dialog = factory.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.values.return_value = ("Neuer Main", "Priest", "p1", "main")
            self.assertTrue(self.page._add_character())
        self.assertEqual(self.page.store.players[0].mainMemberId,
                         self.page.selected_member_id)
        self.assertEqual(len(self.page.store.players[0].mainHistory), 1)

    def test_management_portrait_fills_plain_square_without_rank_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "portraits.ggc"
            save_new_identity_v2(self.store, target)
            portrait = member_portrait_path(target, "m1")
            portrait.parent.mkdir(parents=True, exist_ok=True)
            image = QPixmap(80, 160)
            image.fill(Qt.GlobalColor.red)
            self.assertTrue(image.save(str(portrait)))
            source_bytes = portrait.read_bytes()
            self.page.set_project_path(target)
            self.assertEqual(portrait.read_bytes(), source_bytes)
            self.assertIs(type(self.page.portrait), QLabel)
            self.assertEqual(self.page.portrait.pixmap().size().width(), 220)
            self.assertEqual(self.page.portrait.pixmap().size().height(), 220)
            self.assertFalse(self.page.portrait.hasScaledContents())

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
        self.assertEqual(table.columnCount(), 13)
        self.assertEqual(table.horizontalHeaderItem(12).text(),
                         tr("identity_v2_character_data.column_dead"))
        for column in (0, 1, 2, 9, 10, 11, 12):
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
        self.assertEqual(table.item(self.row_for("m5"), 12).text(),
                         tr("identity_v2_character_data.dead"))
        self.assertEqual(table.item(self.row_for("m4"), 12).text(), "☠")
        self.assertIn(table.item(self.row_for("m1"), 10).text(),
                      ("01.02.2026", "2026-02-01"))
        before = self.store.to_payload()
        self.page._sort_by_column(12)
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
        header.moveSection(header.visualIndex(12), 0)
        self.assertEqual(header.visualIndex(12), 12)
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
        self.assertEqual(page.table.columnWidth(11), 75)
        self.assertLessEqual(page.table.columnWidth(12), 90)
        old_order = [key for key in COLUMNS if key not in {"raid_count", "dead"}]
        old_order.remove("last_raid")
        old_order.insert(0, "last_raid")
        reordered = IdentityV2CharacterDataPage({
            COLUMN_ORDER_SETTING: [*old_order, "dead"],
        })
        self.addCleanup(reordered.close)
        reordered.set_store(self.store)
        self.assertEqual(
            reordered.layout_settings()[COLUMN_ORDER_SETTING][:2],
            ["last_raid", "raid_count"])


if __name__ == "__main__":
    unittest.main()
