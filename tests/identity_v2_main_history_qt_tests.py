"""Offscreen Main history draft editor and Player-management integration."""

import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from app.identity_v2_main_history import (
    add_main_history_entry, find_main_history_conflicts,
)
from app.identity_v2_player_service import set_main
from app.identity_v2_main_history_qt import MainHistoryDialog
from app.identity_v2_players_qt import (
    MAIN_HISTORY_COLUMN_WIDTHS_SETTING, IdentityV2PlayersPage,
)
from tests.identity_v2_main_history_tests import sample_store


class IdentityV2MainHistoryQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def dialog(self, store=None):
        source = store or sample_store()
        current = [source]
        dialog = MainHistoryDialog(source, "p1", lambda: current[0])
        self.addCleanup(dialog.close)
        return source, current, dialog

    @staticmethod
    def select_history(dialog, history_id):
        row = next(index for index in range(dialog.table.rowCount())
                   if dialog.table.item(index, 0).data(Qt.ItemDataRole.UserRole)
                   == history_id)
        dialog.table.setCurrentCell(row, 0)

    def test_open_without_history_is_read_only_and_unchanged_apply_is_noop(self):
        source, _current, dialog = self.dialog()
        before = source.to_payload()
        self.assertEqual(dialog.table.rowCount(), 0)
        self.assertIn("Alpha", dialog.current_main_label.text())
        self.assertFalse(dialog.main_since.unknown.isChecked())
        self.assertIsNone(dialog.result_store)
        dialog._apply_draft()
        self.assertIsNone(dialog.result_store)
        self.assertEqual(source.to_payload(), before)

    def test_add_update_remove_unknown_dates_and_stable_selection(self):
        source, _current, dialog = self.dialog()
        before = source.to_payload()
        dialog.new_button.click()
        dialog.member_combo.setCurrentIndex(dialog.member_combo.findData("m1006"))
        self.assertTrue(dialog.from_date.unknown.isChecked())
        self.assertTrue(dialog.to_date.unknown.isChecked())
        dialog.stage_button.click()
        first = dialog.draft_store.players[0].mainHistory[0]
        self.assertEqual((first.memberId, first.fromDate, first.toDate, first.source),
                         ("m1006", None, None, "manual"))
        dialog.new_button.click()
        dialog.member_combo.setCurrentIndex(dialog.member_combo.findData("m1001"))
        dialog.from_date.unknown.setChecked(False)
        dialog.from_date.date_edit.setDate(QDate(2025, 1, 1))
        dialog.to_date.unknown.setChecked(False)
        dialog.to_date.date_edit.setDate(QDate(2025, 6, 1))
        dialog.stage_button.click()
        second_id = dialog.draft_store.players[0].mainHistory[-1].historyId
        dialog.table.horizontalHeader().sectionClicked.emit(1)
        self.assertEqual(dialog._selected_history_id, second_id)
        order = dialog._history_order.copy()
        dialog.from_date.date_edit.setDate(QDate(2025, 2, 1))
        dialog.stage_button.click()
        self.assertEqual(dialog._history_order, order)
        self.assertEqual(dialog._history()[second_id].fromDate, "2025-02-01")
        self.select_history(dialog, first.historyId)
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            dialog.remove_button.click()
        self.assertEqual([item.historyId for item in dialog._player().mainHistory],
                         [second_id])
        self.assertEqual(source.to_payload(), before)

    def test_same_names_use_distinct_ids_and_repeated_member_periods(self):
        store = sample_store()
        store.members[2].name = store.members[1].name
        store.members[2].className = store.members[1].className
        store.validate()
        _source, _current, dialog = self.dialog(store)
        labels = {dialog.member_combo.itemData(index): dialog.member_combo.itemText(index)
                  for index in range(dialog.member_combo.count())}
        self.assertIn("m1001", labels["m1001"])
        self.assertIn("m1002", labels["m1002"])
        for member_id in ("m1001", "m1002", "m1001"):
            dialog.new_button.click()
            dialog.member_combo.setCurrentIndex(dialog.member_combo.findData(member_id))
            dialog.stage_button.click()
        entries = dialog._player().mainHistory
        self.assertEqual([item.memberId for item in entries],
                         ["m1001", "m1002", "m1001"])
        self.assertEqual(len({item.historyId for item in entries}), 3)

    def test_conflict_is_marked_then_manual_touching_boundary_resolves_it(self):
        store = sample_store()
        store = add_main_history_entry(store, "p1", "m1001",
                                       "2025-01-01", "2025-08-01")
        store = add_main_history_entry(store, "p1", "m1002",
                                       "2025-06-01", "2025-09-01")
        source, _current, dialog = self.dialog(store)
        self.assertEqual(dialog.conflict_list.count(), 1)
        self.assertTrue(all(dialog.table.item(row, 5).text() == "Überschneidung"
                            for row in range(2)))
        dialog.conflict_list.itemClicked.emit(dialog.conflict_list.item(0))
        self.assertIn(dialog._selected_history_id, {"mh0001", "mh0002"})
        self.select_history(dialog, "mh0002")
        dialog.from_date.date_edit.setDate(QDate(2025, 8, 1))
        dialog.stage_button.click()
        self.assertEqual(dialog.conflict_list.count(), 0)
        self.assertEqual(find_main_history_conflicts(dialog.draft_store, "p1"), ())
        dialog._apply_draft()
        self.assertIsNotNone(dialog.result_store)
        self.assertEqual(find_main_history_conflicts(dialog.result_store, "p1"), ())
        self.assertEqual(source.players[0].mainHistory[1].fromDate, "2025-06-01")

    def test_remaining_overlap_requires_conscious_apply(self):
        store = sample_store()
        store = add_main_history_entry(store, "p1", "m1001",
                                       "2025-01-01", "2025-08-01")
        store = add_main_history_entry(store, "p1", "m1002",
                                       "2025-06-01", "2025-09-01")
        source, _current, dialog = self.dialog(store)
        dialog.main_since.date_edit.setDate(QDate(2026, 2, 1))
        dialog.since_button.click()
        self.assertEqual(dialog.draft_store.players[0].mainSinceDate, "2026-02-01")
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.No):
            dialog._apply_draft()
        self.assertIsNone(dialog.result_store)
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            dialog._apply_draft()
        self.assertIsNotNone(dialog.result_store)
        self.assertEqual(len(find_main_history_conflicts(dialog.result_store, "p1")), 1)
        self.assertEqual(source.players[0].mainSinceDate, "2026-01-01")

    def test_main_since_unknown_keeps_current_main_and_history(self):
        source, _current, dialog = self.dialog()
        dialog.main_since.unknown.setChecked(True)
        dialog.since_button.click()
        self.assertIsNone(dialog.draft_store.players[0].mainSinceDate)
        self.assertEqual(dialog.draft_store.players[0].mainMemberId, "m1000")
        dialog._apply_draft()
        self.assertIsNotNone(dialog.result_store)
        self.assertEqual(dialog.result_store.players[0].mainHistory, [])
        self.assertEqual(source.players[0].mainSinceDate, "2026-01-01")

    def test_automatic_entry_can_be_corrected_without_changing_origin(self):
        store = set_main(sample_store(), "p1", "m1001", "2026-02-01")
        source, _current, dialog = self.dialog(store)
        dialog.to_date.date_edit.setDate(QDate(2026, 1, 31))
        dialog.stage_button.click()
        item = dialog.draft_store.players[0].mainHistory[0]
        self.assertEqual((item.toDate, item.source, item.reason),
                         ("2026-01-31", "automatic", "main_change"))
        self.assertEqual(dialog.draft_store.players[0].mainMemberId, "m1001")
        dialog._apply_draft()
        self.assertEqual(dialog.result_store.players[0].mainHistory[0].source,
                         "automatic")
        self.assertEqual(source.players[0].mainHistory[0].toDate, "2026-02-01")

    def test_cancel_discards_draft_and_keeps_page_store(self):
        source = sample_store()
        page = IdentityV2PlayersPage()
        self.addCleanup(page.close)
        page.set_store(source)
        before = source.to_payload()
        changed = []
        page.storeChanged.connect(changed.append)
        def cancel(dialog):
            dialog.new_button.click()
            dialog.stage_button.click()
            dialog.reject()
            return dialog.result()
        with patch.object(MainHistoryDialog, "exec", new=cancel):
            self.assertFalse(page._open_main_history("p1"))
        self.assertIs(page.store, source)
        self.assertEqual(source.to_payload(), before)
        self.assertEqual(changed, [])

    def test_cancel_stale_invalid_and_add_then_remove_never_commit(self):
        source, current, dialog = self.dialog()
        before = source.to_payload()
        dialog.new_button.click()
        dialog.from_date.unknown.setChecked(False)
        dialog.from_date.date_edit.setDate(QDate(2026, 4, 1))
        dialog.to_date.unknown.setChecked(False)
        dialog.to_date.date_edit.setDate(QDate(2026, 3, 1))
        with patch.object(QMessageBox, "warning") as warning:
            dialog.stage_button.click()
        self.assertTrue(warning.called)
        self.assertIn("Main von", warning.call_args.args[2])
        self.assertEqual(dialog.draft_store.players[0].mainHistory, [])
        dialog.from_date.date_edit.setDate(QDate(2026, 2, 1))
        dialog.stage_button.click()
        history_id = dialog._player().mainHistory[0].historyId
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            dialog.remove_button.click()
        dialog._apply_draft()
        self.assertIsNone(dialog.result_store)
        self.assertEqual(source.to_payload(), before)

        other_source, other_current, other_dialog = self.dialog()
        other_dialog.new_button.click()
        other_dialog.stage_button.click()
        other_current[0] = copy.deepcopy(other_source)
        with patch.object(QMessageBox, "warning") as stale_warning:
            other_dialog._apply_draft()
        self.assertTrue(stale_warning.called)
        self.assertIsNone(other_dialog.result_store)
        self.assertEqual(other_source.nextMainHistoryNumber, 1)
        self.assertEqual(history_id, "mh0001")

    def test_player_page_action_and_ownership_protection(self):
        source = sample_store()
        page = IdentityV2PlayersPage()
        self.addCleanup(page.close)
        page.set_store(source)
        self.assertIsNone(page.findChild(QPushButton, "mainHistoryButton"))
        player_row = next(index for index in range(page.player_table.rowCount())
                          if page.player_table.item(index, 0).data(Qt.ItemDataRole.UserRole)
                          == "p1")
        page.player_table.setCurrentCell(player_row, 0)
        button = page.findChild(QPushButton, "mainHistoryButton")
        self.assertIsNotNone(button)
        changed = []
        page.storeChanged.connect(changed.append)

        def apply(dialog):
            dialog.table.setColumnWidth(0, 333)
            dialog.new_button.click()
            dialog.member_combo.setCurrentIndex(dialog.member_combo.findData("m1000"))
            dialog.stage_button.click()
            dialog._apply_draft()
            return dialog.result()

        with patch.object(MainHistoryDialog, "exec", new=apply):
            button.click()
        self.assertEqual(len(changed), 1)
        self.assertEqual(page.store.players[0].mainHistory[0].memberId, "m1000")
        self.assertEqual(page.layout_settings()[MAIN_HISTORY_COLUMN_WIDTHS_SETTING][0], 333)
        restored = IdentityV2PlayersPage(layout_settings=page.layout_settings())
        self.addCleanup(restored.close)
        restored.set_store(page.store)
        def inspect(dialog):
            self.assertEqual(dialog.table.columnWidth(0), 333)
            return QDialog.DialogCode.Rejected
        with patch.object(MainHistoryDialog, "exec", new=inspect):
            self.assertFalse(restored._open_main_history("p1"))
        self.assertEqual(source.players[0].mainHistory, [])
        with (patch.object(QMessageBox, "warning") as warning,
              patch.object(page, "_choose_player",
                           side_effect=AssertionError("Ownership dialog must not open"))):
            page._reassign_member("m1000")
        self.assertIn("Main-Historie", warning.call_args.args[2])
        self.assertIn("mh0001", warning.call_args.args[2])
        self.assertEqual(page._current_player_id(), "p1")
        self.assertIsNotNone(page.findChild(QPushButton, "mainHistoryButton"))


if __name__ == "__main__":
    unittest.main()
