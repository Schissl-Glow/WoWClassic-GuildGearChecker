"""Offscreen checks for both V2 character death actions and conflict handling."""

import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QDate, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDateEdit, QDialog, QDialogButtonBox, QRadioButton
    from app.identity_v2_character_data_qt import (
        DEATH_ACTION_ROLE, IdentityV2CharacterDataPage,
    )
except ImportError:
    QDate = Qt = QTest = QApplication = QDateEdit = QDialog = IdentityV2CharacterDataPage = None

from tests.identity_v2_character_data_qt_tests import sample_store
from app.identity_v2 import Member, Player
from app.identity_v2_main_history import MainSuccessorCandidate
from app.gravestone_templates import load_gravestone_inventory


@unittest.skipIf(QApplication is None, "PySide6 ist nicht verfügbar.")
class IdentityV2CharacterDeathQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.original = sample_store()
        self.page = IdentityV2CharacterDataPage()
        self.addCleanup(self.page.close)
        assets = Path(__file__).resolve().parents[1] / "assets" / "graveyard"
        templates = load_gravestone_inventory(
            assets, assets / "gravestones_manifest.json").templates
        self.page.set_gravestone_templates_provider(lambda: templates)
        self.page.set_store(self.original)
        self.changed = []
        self.page.storeChanged.connect(self.changed.append)

    def row_for(self, member_id):
        return self.page.visible_member_ids.index(member_id)

    @staticmethod
    def multiple_successors_store():
        store = sample_store()
        store.members[2].playerId = "p1"
        store.members[2].name = store.members[1].name
        store.members[2].className = store.members[1].className
        store.members[3].playerId = "p1"  # inactive
        store.members[4].playerId = "p1"  # dead
        store.players.append(Player("p2", "Andere"))
        store.members.append(Member("m6", "Fremd", "Warrior", playerId="p2"))
        store.validate()
        return store

    def test_live_cell_click_opens_cancelable_dialog_with_editable_today(self):
        page = self.page
        page.resize(1700, 850)
        page.show()
        self.app.processEvents()
        item = page.table.item(self.row_for("m3"), 11)
        self.assertEqual(item.text(), "☠")
        self.assertTrue(item.data(DEATH_ACTION_ROLE))
        self.assertIn("tot", item.toolTip().casefold())
        before = page.store.to_payload()
        captured = {}

        def cancel_dialog(dialog):
            captured["title"] = dialog.windowTitle()
            captured["date"] = dialog.findChild(QDateEdit).date().toPython()
            captured["description"] = [child.text() for child in dialog.findChildren(
                type(page.detail_name)) if "Charlie" in child.text()]
            captured["options"] = [child.text() for child in dialog.findChildren(QRadioButton)]
            captured["confirm_enabled"] = dialog.findChild(QDialogButtonBox).button(
                QDialogButtonBox.StandardButton.Ok).isEnabled()
            return QDialog.DialogCode.Rejected

        page.table.scrollToItem(item)
        self.app.processEvents()
        rect = page.table.visualItemRect(item)
        with patch.object(QDialog, "exec", new=cancel_dialog):
            QTest.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton,
                             pos=rect.center())
        self.assertIn("tot", captured["title"].casefold())
        self.assertEqual(captured["date"], date.today())
        self.assertTrue(captured["description"])
        self.assertEqual(len(captured["options"]), 2)
        self.assertFalse(captured["confirm_enabled"])
        self.assertEqual(page.store.to_payload(), before)
        self.assertEqual(self.changed, [])

        def accept_changed_date(dialog):
            dialog.findChild(QDateEdit).setDate(QDate(2026, 3, 12))
            dialog.findChild(QRadioButton, "death_burial_collective").setChecked(True)
            return QDialog.DialogCode.Accepted

        with patch.object(QDialog, "exec", new=accept_changed_date):
            chosen = page._choose_death_details(page.rows_by_id["m3"])
        self.assertEqual(chosen, (date(2026, 3, 12), "collective"))
        self.assertEqual(page.store.to_payload(), before)

    def test_table_death_on_raid_day_updates_main_row_detail_without_resort(self):
        page = self.page
        before = page.store.to_payload()
        page._sort_by_column(2)
        order_before = page.visible_member_ids
        page.table.setCurrentCell(self.row_for("m1"), 11)
        with (patch.object(page, "_choose_death_details",
                           return_value=(date(2026, 2, 1), "individual")),
              patch.object(page, "_choose_main_successor",
                           side_effect=AssertionError("No successor dialog expected"))):
            page._table_cell_clicked(self.row_for("m1"), 11)
        self.assertEqual(len(self.changed), 1)
        member = next(item for item in page.store.members if item.memberId == "m1")
        self.assertEqual((member.lifeStatus, member.deathDate, member.playerId),
                         ("dead", "2026-02-01", "p1"))
        self.assertEqual(page.store.players[0].mainMemberId, "m2")
        self.assertEqual(page.store.players[0].mainSinceDate, "2026-02-01")
        self.assertEqual(page.rows_by_id["m2"].playerRole, "main")
        self.assertEqual(page.store.players[0].displayName, "Besitzer")
        self.assertEqual(page.store.members[1].to_dict(), self.original.members[1].to_dict())
        self.assertEqual(page.store.to_payload()["attendance"], before["attendance"])
        self.assertEqual(page.visible_member_ids, order_before)
        self.assertEqual(page.selected_member_id, "m1")
        self.assertEqual(page.table.item(self.row_for("m1"), 11).text(), "Tot")
        self.assertFalse(page.table.item(self.row_for("m1"), 11).data(DEATH_ACTION_ROLE))
        self.assertIn("2026-02-01", page.table.item(self.row_for("m1"), 11).toolTip())
        self.assertEqual(page.detail_status.text(), "Tot")
        self.assertTrue(page.mark_dead_button.isHidden())
        self.assertIn(page.detail_values["death_date"].text(),
                      ("01.02.2026", "2026-02-01"))

    def test_main_death_without_successor_needs_no_selection_dialog(self):
        page = self.page
        store = sample_store()
        store.members[1].lifeStatus = "inactive"
        store.validate()
        page.set_store(store)
        with (patch.object(page, "_choose_death_details",
                           return_value=(date(2026, 2, 1), "individual")),
              patch.object(page, "_choose_main_successor",
                           side_effect=AssertionError("No successor dialog expected"))):
            self.assertTrue(page._request_death_for_member("m1"))
        self.assertIsNone(page.store.players[0].mainMemberId)
        self.assertIsNone(page.store.players[0].mainSinceDate)
        self.assertEqual(page.store.members[0].playerId, "p1")
        self.assertEqual(page.store.players[0].mainHistory[0].reason, "death")
        self.assertEqual(len(self.changed), 1)

    def test_conflict_reports_raid_and_keeps_store_untouched(self):
        page = self.page
        before = page.store.to_payload()
        with (patch.object(page, "_choose_death_details", return_value=(date(2026, 1, 31), "collective")),
              patch("app.identity_v2_character_data_qt.QMessageBox.warning") as warning):
            self.assertFalse(page._request_death_for_member("m1"))
        self.assertEqual(page.store.to_payload(), before)
        self.assertEqual(self.changed, [])
        message = warning.call_args.args[2]
        self.assertIn("1", message)
        self.assertIn("r2", message)
        self.assertTrue("01.02.2026" in message or "2026-02-01" in message)

    def test_no_free_gravestone_reports_error_without_changing_store(self):
        page = self.page
        page.set_gravestone_templates_provider(lambda: ())
        before = page.store.to_payload()
        with (patch.object(page, "_choose_death_details",
                           return_value=(date(2026, 3, 12), "individual")),
              patch("app.identity_v2_character_data_qt.QMessageBox.warning") as warning):
            self.assertFalse(page._request_death_for_member("m3"))
        self.assertIn("kein freier grabstein", warning.call_args.args[2].casefold())
        self.assertEqual(page.store.to_payload(), before)
        self.assertEqual(self.changed, [])

    def test_active_and_inactive_filters_drop_dead_and_graveyard_shows_them(self):
        page = self.page
        page.status_filter.setCurrentIndex(page.status_filter.findData("active"))
        page.table.setCurrentCell(self.row_for("m3"), 0)
        with patch.object(page, "_choose_death_details", return_value=(date(2026, 3, 15), "individual")):
            page._request_death_for_member("m3")
        self.assertNotIn("m3", page.visible_member_ids)
        self.assertNotEqual(page.selected_member_id, "m3")
        page.status_filter.setCurrentIndex(page.status_filter.findData("inactive"))
        self.assertIn("m4", page.visible_member_ids)
        with patch.object(page, "_choose_death_details", return_value=(date(2026, 3, 15), "collective")):
            page._request_death_for_member("m4")
        self.assertNotIn("m4", page.visible_member_ids)
        page.status_filter.setCurrentIndex(page.status_filter.findData("graveyard"))
        self.assertEqual(set(page.visible_member_ids), {"m3", "m4", "m5"})
        self.assertEqual(len(self.changed), 2)

    def test_detail_button_uses_same_service_and_dead_member_has_no_action(self):
        page = self.page
        page.table.setCurrentCell(self.row_for("m2"), 0)
        self.assertFalse(page.mark_dead_button.isHidden())
        with patch.object(page, "_choose_death_details", return_value=(date(2026, 3, 15), "collective")):
            page.mark_dead_button.click()
        self.assertEqual(len(self.changed), 1)
        self.assertEqual(page.store.members[1].lifeStatus, "dead")
        self.assertEqual(page.store.players[0].mainMemberId, "m1")
        self.assertTrue(page.mark_dead_button.isHidden())
        self.assertFalse(page.table.item(self.row_for("m2"), 11).data(DEATH_ACTION_ROLE))
        with patch.object(page, "_choose_death_details") as choose:
            page._table_cell_clicked(self.row_for("m2"), 11)
            page._request_death_for_member("m5")
        self.assertFalse(choose.called)
        self.assertEqual(len(self.changed), 1)

    def test_dialog_requires_choice_and_accepts_both_burial_types(self):
        page = self.page
        row = page.rows_by_id["m3"]
        with patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            self.assertIsNone(page._choose_death_details(row))

        def choose(burial_type):
            def accept(dialog):
                radio = dialog.findChild(QRadioButton, f"death_burial_{burial_type}")
                radio.setChecked(True)
                self.assertTrue(dialog.findChild(QDialogButtonBox).button(
                    QDialogButtonBox.StandardButton.Ok).isEnabled())
                return QDialog.DialogCode.Accepted
            with patch.object(QDialog, "exec", new=accept):
                return page._choose_death_details(row)

        self.assertEqual(choose("individual"), (date.today(), "individual"))
        self.assertEqual(choose("collective"), (date.today(), "collective"))

    def test_burial_change_uses_service_and_keeps_history(self):
        page = self.page
        page.table.setCurrentCell(self.row_for("m5"), 0)
        self.assertFalse(page.burial_row.isHidden())
        self.assertEqual(page.burial_choice.currentData(), "individual")
        original = page.store.to_payload()
        index = page.burial_choice.findData("collective")
        page.burial_choice.setCurrentIndex(index)
        page.burial_choice.activated.emit(index)
        self.assertEqual(len(self.changed), 1)
        self.assertEqual(page.store.members[4].burialType, "collective")
        expected = original.copy()
        expected["members"] = [item.copy() for item in original["members"]]
        expected["members"][4]["burialType"] = "collective"
        self.assertEqual(page.store.to_payload(), expected)
        self.assertEqual(self.original.to_payload(), original)
        index = page.burial_choice.findData("individual")
        page.burial_choice.setCurrentIndex(index)
        page.burial_choice.activated.emit(index)
        assigned = page.store.members[4]
        template = next(item for item in page.gravestone_templates_provider()
                        if item.grave_template_id == assigned.graveTemplateId)
        self.assertEqual(assigned.burialType, "individual")
        self.assertEqual(assigned.portraitOffsetX, template.default_portrait_offset_x)
        self.assertEqual(assigned.portraitOffsetY, template.default_portrait_offset_y)
        self.assertEqual(assigned.portraitZoom, template.default_portrait_zoom)
        expected = original.copy()
        expected["members"] = [item.copy() for item in original["members"]]
        expected["members"][4].update(
            graveTemplateId=assigned.graveTemplateId,
            portraitOffsetX=template.default_portrait_offset_x,
            portraitOffsetY=template.default_portrait_offset_y,
            portraitZoom=template.default_portrait_zoom,
        )
        self.assertEqual(page.store.to_payload(), expected)
        self.assertEqual(self.original.to_payload(), original)
        self.assertEqual(len(self.changed), 2)

    def test_correction_dialogs_are_dead_only_and_show_required_information(self):
        page = self.page
        page.table.setCurrentCell(self.row_for("m1"), 0)
        self.assertTrue(page.correct_death_date_button.isHidden())
        self.assertTrue(page.clear_death_button.isHidden())
        page.table.setCurrentCell(self.row_for("m5"), 0)
        self.assertFalse(page.correct_death_date_button.isHidden())
        self.assertFalse(page.clear_death_button.isHidden())
        seen = {}

        def inspect_date(dialog):
            seen["date_text"] = " ".join(label.text() for label in dialog.findChildren(
                type(page.detail_name)))
            seen["initial_date"] = dialog.findChild(QDateEdit).date().toPython()
            return QDialog.DialogCode.Rejected

        with patch.object(QDialog, "exec", new=inspect_date):
            self.assertIsNone(page._choose_corrected_death_date(page.rows_by_id["m5"]))
        self.assertIn("Echo", seen["date_text"])
        self.assertEqual(seen["initial_date"], date(2026, 3, 15))
        old = self.original.__class__.from_payload(page.store.to_payload())
        old.members[4].deathDate = None
        old.validate()
        page.set_store(old)
        with patch.object(QDialog, "exec", new=inspect_date):
            self.assertIsNone(page._choose_corrected_death_date(page.rows_by_id["m5"]))
        self.assertIn("Unbekannt", seen["date_text"])

        def inspect_clear(dialog):
            label = " ".join(item.text() for item in dialog.findChildren(
                type(page.detail_name)))
            self.assertIn("Echo", label)
            self.assertIn("Main", label)
            buttons = dialog.findChild(QDialogButtonBox)
            self.assertFalse(buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
            dialog.findChild(QRadioButton, "clear_death_inactive").setChecked(True)
            self.assertTrue(buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
            return QDialog.DialogCode.Accepted

        with patch.object(QDialog, "exec", new=inspect_clear):
            self.assertEqual(page._choose_clear_death_status(page.rows_by_id["m5"]),
                             "inactive")

    def test_corrections_refresh_filter_and_do_not_resort(self):
        page = self.page
        page._sort_by_column(0)
        order_before = page.visible_member_ids
        page.table.setCurrentCell(self.row_for("m5"), 0)
        with patch.object(page, "_choose_corrected_death_date",
                          return_value=date(2026, 3, 17)):
            self.assertTrue(page._request_death_date_correction("m5"))
        self.assertEqual(len(self.changed), 1)
        self.assertEqual(page.visible_member_ids, order_before)
        self.assertEqual(page.selected_member_id, "m5")
        self.assertEqual(page.store.members[4].deathDate, "2026-03-17")
        with patch.object(page, "_choose_corrected_death_date",
                          return_value=date(2026, 3, 17)):
            self.assertFalse(page._request_death_date_correction("m5"))
        self.assertEqual(len(self.changed), 1)

        page.status_filter.setCurrentIndex(page.status_filter.findData("graveyard"))
        with patch.object(page, "_choose_clear_death_status", return_value="active"):
            self.assertTrue(page._request_clear_death_marking("m5"))
        self.assertEqual(page.visible_member_ids, ())
        self.assertIsNone(page.selected_member_id)
        self.assertEqual(page.store.members[4].lifeStatus, "active")
        self.assertEqual(page.store.members[4].burialType, None)
        self.assertEqual(len(self.changed), 2)
        page.status_filter.setCurrentIndex(0)
        self.assertEqual(page.visible_member_ids, order_before)
        self.assertTrue(page.correct_death_date_button.isHidden())

    def test_correction_conflict_cancel_and_stale_dialog_leave_store_untouched(self):
        page = self.page
        page.table.setCurrentCell(self.row_for("m5"), 0)
        before = page.store.to_payload()
        with patch.object(page, "_choose_corrected_death_date", return_value=None):
            self.assertFalse(page._request_death_date_correction("m5"))
        with patch.object(page, "_choose_clear_death_status", return_value=None):
            self.assertFalse(page._request_clear_death_marking("m5"))
        self.assertEqual(page.store.to_payload(), before)
        self.assertEqual(self.changed, [])

        def switch_store(_row):
            page.set_store(self.original.__class__.from_payload(before))
            return date(2026, 3, 16)

        with (patch.object(page, "_choose_corrected_death_date", side_effect=switch_store),
              patch("app.identity_v2_character_data_qt.QMessageBox.warning") as warning):
            self.assertFalse(page._request_death_date_correction("m5"))
        self.assertTrue(warning.called)
        self.assertEqual(page.store.to_payload(), before)
        self.assertEqual(self.changed, [])

        page.set_project_path("other-v2.ggc")
        def switch_project(_row):
            page.set_project_path("different-v2.ggc")
            return "active"

        with (patch.object(page, "_choose_clear_death_status", side_effect=switch_project),
              patch("app.identity_v2_character_data_qt.QMessageBox.warning") as warning):
            self.assertFalse(page._request_clear_death_marking("m5"))
        self.assertTrue(warning.called)
        self.assertEqual(page.store.to_payload(), before)
        self.assertEqual(self.changed, [])

        conflicting = self.original.__class__.from_payload(before)
        conflicting.members[0].lifeStatus = "dead"
        conflicting.members[0].burialType = "individual"
        conflicting.members[0].deathDate = "2026-02-01"
        conflicting.players[0].mainMemberId = "m2"
        conflicting.validate()
        page.set_store(conflicting)
        conflict_before = page.store.to_payload()
        with (patch.object(page, "_choose_corrected_death_date",
                           return_value=date(2026, 1, 31)),
              patch("app.identity_v2_character_data_qt.QMessageBox.warning") as warning):
            self.assertFalse(page._request_death_date_correction("m1"))
        self.assertIn("r2", warning.call_args.args[2])
        self.assertEqual(page.store.to_payload(), conflict_before)
        self.assertEqual(self.changed, [])

    def test_correction_preserves_successor_and_shows_history_hint(self):
        page = self.page
        with patch.object(page, "_choose_death_details",
                          return_value=(date(2026, 2, 1), "individual")):
            self.assertTrue(page._request_death_for_member("m1"))
        player_before = page.store.players[0].to_dict()
        with (patch.object(page, "_choose_corrected_death_date",
                           return_value=date(2026, 2, 2)),
              patch("app.identity_v2_character_data_qt.QMessageBox.information") as info):
            self.assertTrue(page._request_death_date_correction("m1"))
        self.assertEqual(page.store.players[0].to_dict(), player_before)
        self.assertIn("Main-Historie", info.call_args.args[2])
        with (patch.object(page, "_choose_clear_death_status", return_value="inactive"),
              patch("app.identity_v2_character_data_qt.QMessageBox.information")):
            self.assertTrue(page._request_clear_death_marking("m1"))
        self.assertEqual(page.store.players[0].to_dict(), player_before)
        self.assertEqual(page.store.members[0].lifeStatus, "inactive")
        self.assertEqual(len(self.changed), 3)

    def test_successor_dialog_has_no_default_and_uses_member_ids(self):
        candidates = (
            MainSuccessorCandidate("m2", "Sorap", "Priest"),
            MainSuccessorCandidate("m3", "Sorap", "Priest"),
        )

        def inspect(dialog):
            radios = dialog.findChildren(QRadioButton)
            self.assertEqual(len(radios), 2)
            self.assertEqual(radios[0].text(), radios[1].text())
            self.assertEqual({radio.objectName() for radio in radios},
                             {"successor_option_m2", "successor_option_m3"})
            self.assertNotEqual(radios[0].toolTip(), radios[1].toolTip())
            self.assertFalse(dialog.findChild(QDialogButtonBox).button(
                QDialogButtonBox.StandardButton.Ok).isEnabled())
            dialog.findChild(QRadioButton, "successor_option_m3").setChecked(True)
            self.assertTrue(dialog.findChild(QDialogButtonBox).button(
                QDialogButtonBox.StandardButton.Ok).isEnabled())
            return QDialog.DialogCode.Accepted

        with patch.object(QDialog, "exec", new=inspect):
            self.assertEqual(self.page._choose_main_successor(candidates), "m3")
        with patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            self.assertIsNone(self.page._choose_main_successor(candidates))

    def test_multiple_successors_cancel_keeps_store_unchanged(self):
        page = self.page
        page.set_store(self.multiple_successors_store())
        before = page.store.to_payload()
        with (patch.object(page, "_choose_death_details",
                           return_value=(date(2026, 2, 1), "individual")),
              patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Rejected)):
            self.assertFalse(page._request_death_for_member("m1"))
        self.assertEqual(page.store.to_payload(), before)
        self.assertEqual(self.changed, [])

    def test_multiple_successors_table_action_commits_selected_member_id(self):
        page = self.page
        page.set_store(self.multiple_successors_store())
        before = page.store.to_payload()
        page.table.setCurrentCell(self.row_for("m1"), 11)

        def choose(dialog):
            radios = dialog.findChildren(QRadioButton)
            self.assertEqual({radio.objectName() for radio in radios},
                             {"successor_option_m2", "successor_option_m3"})
            dialog.findChild(QRadioButton, "successor_option_m3").setChecked(True)
            return QDialog.DialogCode.Accepted

        with (patch.object(page, "_choose_death_details",
                           return_value=(date(2026, 2, 1), "collective")),
              patch.object(QDialog, "exec", new=choose)):
            page._table_cell_clicked(self.row_for("m1"), 11)
        self.assertEqual(len(self.changed), 1)
        self.assertEqual(page.store.players[0].mainMemberId, "m3")
        self.assertEqual(page.store.players[0].mainSinceDate, "2026-02-01")
        self.assertEqual(page.rows_by_id["m3"].playerRole, "main")
        self.assertEqual(page.store.members[0].burialType, "collective")
        self.assertEqual([(item.memberId, item.toDate, item.reason)
                          for item in page.store.players[0].mainHistory],
                         [("m1", "2026-02-01", "death")])
        self.assertEqual(page.store.to_payload()["attendance"], before["attendance"])
        self.assertEqual(page.store.to_payload()["legacyClmGuidMemberMap"],
                         before["legacyClmGuidMemberMap"])
        self.assertEqual(page.store.members[1].to_dict(), before["members"][1])
        self.assertEqual(page.store.members[2].to_dict(), before["members"][2])

    def test_multiple_successors_detail_button_uses_same_workflow(self):
        page = self.page
        page.set_store(self.multiple_successors_store())
        page.table.setCurrentCell(self.row_for("m1"), 0)
        with (patch.object(page, "_choose_death_details",
                           return_value=(date(2026, 2, 1), "individual")),
              patch.object(page, "_choose_main_successor", return_value="m2") as choose):
            page.mark_dead_button.click()
        choose.assert_called_once()
        self.assertEqual(page.store.players[0].mainMemberId, "m2")
        self.assertEqual(page.store.members[0].lifeStatus, "dead")
        self.assertEqual(len(self.changed), 1)


if __name__ == "__main__":
    unittest.main()
