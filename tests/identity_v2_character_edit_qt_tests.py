"""Focused offscreen checks for V2 character inline and detail editing."""

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication, QAbstractItemView, QComboBox, QStyleOptionViewItem,
        QTableWidgetSelectionRange,
    )
    from app.identity_v2_character_data_qt import IdentityV2CharacterDataPage
except ImportError:
    Qt = QTest = QApplication = QAbstractItemView = QComboBox = None
    QStyleOptionViewItem = QTableWidgetSelectionRange = IdentityV2CharacterDataPage = None

from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from tests.identity_v2_character_data_qt_tests import sample_store


@unittest.skipIf(QApplication is None, "PySide6 ist nicht verfügbar.")
class IdentityV2CharacterEditQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.store = sample_store()
        self.page = IdentityV2CharacterDataPage()
        self.addCleanup(self.page.close)
        self.page.set_store(self.store)
        self.changed = []
        self.page.storeChanged.connect(self.changed.append)

    def row_for(self, member_id):
        return self.page.visible_member_ids.index(member_id)

    def member(self, member_id):
        return next(item for item in self.page.store.members if item.memberId == member_id)

    def commit_cell(self, member_id, column, value):
        row = self.row_for(member_id)
        table = self.page.table
        table.setCurrentCell(row, column)
        index = table.model().index(row, column)
        delegate = table.itemDelegate()
        editor = delegate.createEditor(table.viewport(), QStyleOptionViewItem(), index)
        self.assertIsInstance(editor, QComboBox)
        delegate.setEditorData(editor, index)
        target = editor.findData(value)
        self.assertGreaterEqual(target, 0)
        editor.setCurrentIndex(target)
        delegate.setModelData(editor, table.model(), index)
        editor.deleteLater()

    def choose_detail(self, key, value):
        combo = self.page.detail_editors[key]
        index = combo.findData(value)
        self.assertGreaterEqual(index, 0)
        combo.setCurrentIndex(index)
        combo.activated.emit(index)

    def test_inline_choice_editors_use_services_and_keep_check_date(self):
        from app import identity_v2_character_data_qt as module
        self.page.table.setCurrentCell(self.row_for("m1"), 3)
        with patch.object(module, "set_member_race", wraps=module.set_member_race) as service:
            self.commit_cell("m1", 3, "Gnome")
        self.assertEqual(service.call_count, 1)
        self.assertEqual(self.member("m1").race, "Gnome")
        self.commit_cell("m1", 6, "tank")
        self.commit_cell("m1", 7, "S+")
        self.commit_cell("m1", 8, "Nicht bereit")
        self.assertEqual((self.member("m1").raidRole,
                          self.member("m1").gearStatus,
                          self.member("m1").raidStatus),
                         ("tank", "S+", "Nicht bereit"))
        self.assertIsNone(self.member("m1").lastChecked)
        self.assertEqual(self.page.detail_values["race"].currentData(), "Gnome")
        self.assertEqual(len(self.changed), 4)
        self.assertEqual(self.store.members[0].race, "Human")

    def test_unknown_class_spec_and_class_change_update_only_member_row(self):
        self.commit_cell("m3", 4, "Mage")
        self.commit_cell("m3", 5, "Frost")
        self.assertEqual((self.member("m3").className, self.member("m3").spec),
                         ("Mage", "Frost"))
        self.commit_cell("m3", 4, "Warrior")
        self.assertEqual((self.member("m3").className, self.member("m3").spec),
                         ("Warrior", None))
        self.assertEqual(self.page.table.item(self.row_for("m3"), 5).text(), "–")
        self.assertIsNone(self.page.detail_editors["spec"].currentData())
        self.commit_cell("m3", 4, None)
        self.assertIsNone(self.member("m3").className)
        self.assertEqual(self.page.detail_editors["spec"].count(), 1)
        self.assertEqual(len(self.changed), 4)

    def test_detail_edit_notes_and_explicit_check_then_temp_save_load(self):
        self.page.table.setCurrentCell(self.row_for("m1"), 0)
        self.page.detail_note.setPlainText("Entwurf bleibt erhalten")
        class_combo = self.page.detail_editors["class"]
        class_combo.setCurrentIndex(class_combo.findData("Priest"))
        self.assertEqual(self.member("m1").className, "Mage")
        class_combo.activated.emit(class_combo.currentIndex())
        self.assertEqual((self.member("m1").className, self.member("m1").spec),
                         ("Priest", None))
        self.assertEqual(self.page.detail_note.toPlainText(), "Entwurf bleibt erhalten")
        self.assertEqual(self.member("m1").note, "Arkan")
        self.choose_detail("spec", "Holy")
        self.choose_detail("gear", "Pre-BiS")
        self.choose_detail("raid_status", "Nicht bereit")
        self.assertIsNone(self.member("m1").lastChecked)
        self.page.detail_note.setPlainText("Mehrzeilige\nNotiz")
        self.assertTrue(self.page.note_save_button.isEnabled())
        self.page.note_save_button.click()
        self.assertEqual(self.member("m1").note, "Mehrzeilige\nNotiz")
        self.page.confirm_check_button.click()
        self.assertEqual(self.member("m1").lastChecked, date.today().isoformat())
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "detail-edit.ggc"
            save_new_identity_v2(self.page.store, target)
            restored = load_identity_v2(target)
        member = next(item for item in restored.members if item.memberId == "m1")
        self.assertEqual((member.spec, member.note, member.lastChecked),
                         ("Holy", "Mehrzeilige\nNotiz", date.today().isoformat()))

    def test_copy_paste_multiple_rows_and_protected_columns(self):
        table = self.page.table
        table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 2), True)
        table.setFocus()
        QTest.keyClick(table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        copied = QApplication.clipboard().text()
        self.assertEqual(len(copied.splitlines()), 2)
        self.assertEqual(len(copied.splitlines()[0].split("\t")), 3)
        self.assertIn("Alpha", copied)

        table.clearSelection()
        table.setCurrentCell(self.row_for("m3"), 3)
        QApplication.clipboard().setText(
            "Human\tMage\tFrost\tDPS\tBiS\tBereit\n"
            "Dwarf\tWarrior\tFury\tTank\tPre-BiS\tNicht bereit")
        QTest.keyClick(table, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(self.changed), 1)
        self.assertEqual((self.member("m3").className, self.member("m3").spec,
                          self.member("m3").raidRole), ("Mage", "Frost", "dps"))
        self.assertEqual((self.member("m4").className, self.member("m4").spec,
                          self.member("m4").raidRole), ("Warrior", "Fury", "tank"))
        self.assertIsNone(self.member("m3").lastChecked)
        before = self.page.store.to_payload()
        with patch("app.identity_v2_character_data_qt.QMessageBox.warning") as warning:
            for column in (0, 1, 2, 9, 10, 11):
                table.setCurrentCell(0, column)
                self.assertFalse(self.page.paste_text("Geschützt"))
            self.assertEqual(warning.call_count, 6)
        self.assertEqual(self.page.store.to_payload(), before)

    def test_invalid_batch_rolls_back_and_keeps_layout_selection(self):
        page = self.page
        page.table.setColumnWidth(3, 203)
        page.table.setCurrentCell(self.row_for("m3"), 3)
        before = page.store.to_payload()
        settings = page.layout_settings()
        with patch("app.identity_v2_character_data_qt.QMessageBox.warning") as warning:
            self.assertFalse(page.paste_text("Human\tMage\tHoly\tDPS\tBiS\tBereit"))
            self.assertTrue(warning.called)
            self.assertIn("Charlie", warning.call_args.args[2])
        self.assertEqual(page.store.to_payload(), before)
        self.assertEqual(page.selected_member_id, "m3")
        self.assertEqual(page.layout_settings(), settings)
        self.assertEqual(self.changed, [])

    def test_edit_after_sort_stays_in_place_until_next_header_and_filter_reacts(self):
        page = self.page
        page._sort_by_column(7)
        before = page.visible_member_ids
        self.commit_cell("m1", 7, "Level")
        self.assertEqual(page.visible_member_ids, before)
        page._sort_by_column(7)
        self.assertNotEqual(page.visible_member_ids, before)
        page.gear_filter.setCurrentIndex(page.gear_filter.findData("Level"))
        self.assertIn("m1", page.visible_member_ids)
        self.commit_cell("m1", 7, "BiS")
        self.assertNotIn("m1", page.visible_member_ids)
        self.assertNotEqual(page.selected_member_id, "m1")

    def test_tab_skips_read_only_and_escape_aborts_editor(self):
        page = self.page
        page.show()
        self.app.processEvents()
        table = page.table
        table.setCurrentCell(self.row_for("m1"), 0)
        table.setFocus()
        QTest.keyClick(table, Qt.Key.Key_Tab)
        self.assertEqual(table.currentColumn(), 3)
        table.setCurrentCell(self.row_for("m1"), 4)
        QTest.keyClick(table, Qt.Key.Key_Backtab)
        self.assertEqual(table.currentColumn(), 3)
        before = page.store.to_payload()
        QTest.keyClick(table, Qt.Key.Key_Return)
        self.assertEqual(table.state(), QAbstractItemView.State.EditingState)
        editor = table.viewport().findChild(QComboBox)
        self.assertIsNotNone(editor)
        QTest.keyClick(editor, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertEqual(page.store.to_payload(), before)
        self.assertEqual(self.changed, [])

    def test_layout_settings_and_selection_survive_multiple_edits(self):
        page = self.page
        page.resize(1500, 850)
        page.show()
        self.app.processEvents()
        page.table.setColumnWidth(3, 207)
        header = page.table.horizontalHeader()
        header.moveSection(header.visualIndex(4), 1)
        page.splitter.setSizes([1000, 420])
        self.app.processEvents()
        page.table.setCurrentCell(self.row_for("m1"), 3)
        settings = page.layout_settings()
        self.commit_cell("m1", 3, "Gnome")
        self.commit_cell("m1", 6, "tank")
        self.assertEqual(page.layout_settings(), settings)
        self.assertEqual(page.selected_member_id, "m1")
        page.details_button.setChecked(False)
        hidden = page.layout_settings()
        self.commit_cell("m1", 8, "Nicht bereit")
        self.assertEqual(page.layout_settings(), hidden)


if __name__ == "__main__":
    unittest.main()
