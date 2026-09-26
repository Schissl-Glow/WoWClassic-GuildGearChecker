"""Offscreen checks for the V2 Players & Characters management page."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication, QGroupBox, QLabel, QMessageBox, QPushButton, QToolButton,
    )
    from app.identity_v2_players_qt import IdentityV2PlayersPage
except ImportError:
    Qt = QTest = QApplication = QGroupBox = QLabel = QMessageBox = QPushButton = QToolButton = IdentityV2PlayersPage = None

from app.identity_v2 import Attendance, EternalDkpRecord, IdentityV2Store, Member, Player, Raid
from app.identity_v2_dkp import IdentityV2DkpProjection
from app.i18n import tr
from app.identity_v2_players_qt import (
    PLAYER_COLUMN_WIDTHS_SETTING, PLAYER_SPLITTER_SIZES_SETTING,
    UNKNOWN_COLUMN_WIDTHS_SETTING,
)
from app.identity_v2_player_service import set_member_activity


def player_page_store() -> IdentityV2Store:
    return IdentityV2Store(
        players=[Player("p0001", "Schneeflocke", "m1000"),
                 Player("p0002", "Marten"), Player("p0003", "Leer")],
        members=[
            Member("m1000", "Schneeflocke", "Mage", playerId="p0001"),
            Member("m1001", "Frostgnom", "Mage", playerId="p0001"),
            Member("m1002", "Altergnom", "Priest", lifeStatus="inactive",
                   playerId="p0001"),
            Member("m1003", "Toterchar", "Warrior", lifeStatus="dead",
                   playerId="p0001", deathDate="2026-02-01", burialType="individual"),
            Member("m1004", "Martenchar", "Rogue", playerId="p0002",
                   currentRole="main"),
            Member("m1005", "Bierbart", None, raidStartDate="2026-01-08"),
            Member("m1006", "Inaktivfrei", "Druid", lifeStatus="inactive"),
            Member("m1007", "Friedhoffrei", "Priest", lifeStatus="dead",
                   deathDate="2026-02-02", burialType="individual"),
            Member("m1008", "Zweitfrei", "Mage"),
        ],
        raids=[Raid("r1", "2026-01-01", name="MC"),
               Raid("r2", "2026-01-08", name="BWL"),
               Raid("r3", "2026-02-01", name="Onyxia")],
        attendance=[
            Attendance("a1", "r1", "m1000", "unknown", playerId="p0001"),
            Attendance("a2", "r1", "m1001", "twink", playerId="p0001"),
            Attendance("a3", "r2", "m1004", "main", playerId="p0002"),
            Attendance("a4", "r1", "m1005", "unknown"),
            Attendance("a5", "r2", "m1005", "unknown"),
            Attendance("a6", "r1", "m1006", "unknown"),
            Attendance("a7", "r2", "m1008", "unknown"),
            Attendance("a8", "r3", "m1005", "unknown"),
        ],
    )


@unittest.skipIf(QApplication is None, "PySide6 ist lokal nicht verfügbar.")
class IdentityV2PlayersQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.store = player_page_store()
        self.store.validate()
        self.page = IdentityV2PlayersPage()
        self.addCleanup(self.page.close)
        self.changed = []
        self.page.storeChanged.connect(self.changed.append)
        self.page.set_store(self.store)

    def test_player_detail_shows_eternal_dkp_and_independent_ranks(self):
        for member_id, guid in (("m1000", "1:1"), ("m1002", "1:2"),
                                ("m1003", "1:3")):
            next(member for member in self.store.members
                 if member.memberId == member_id).clmGuid = guid
        self.store.eternalDkpRecords = [
            EternalDkpRecord(f"d{index}", f"e{index}", member_id, guid,
                             "award", value)
            for index, (member_id, guid, value) in enumerate((
                ("m1000", "1:1", 100), ("m1002", "1:2", 200),
                ("m1003", "1:3", 300)), start=1)
        ]
        points = SimpleNamespace(
            character_points=lambda member_id: 80,
            eternal_character_points=lambda member_id: 80,
            player_points=lambda player_id: 160,
            eternal_player_points=lambda player_id: 160,
        )
        projection = IdentityV2DkpProjection(
            self.store, raid_points_projection=points)
        self.select_player("p0001")
        self.page.set_dkp_projection(projection)
        def detail_text(name):
            return self.page.detail_host.findChildren(QLabel, name)[-1].text()
        self.assertEqual(detail_text("v2PlayerEternalDkp"), "600")
        self.assertEqual(detail_text("v2PlayerDkpRank"), "Eisen 1")
        self.assertEqual(detail_text("v2PlayerRaidRank"), "Holz 2")

    def select_player(self, player_id):
        for index in range(self.page.player_table.rowCount()):
            item = self.page.player_table.item(index, 0)
            if item.data(Qt.ItemDataRole.UserRole) == player_id:
                self.page.player_table.setCurrentItem(item)
                self.page._render_detail()
                return
        self.fail(f"Player {player_id!r} ist nicht sichtbar")

    def select_unknown(self, *member_ids):
        self.select_player(None)
        table = self.page.unassigned_table
        for row in range(table.rowCount()):
            checkbox = table.item(row, 0)
            member_id = checkbox.data(Qt.ItemDataRole.UserRole)
            checkbox.setCheckState(
                Qt.CheckState.Checked if member_id in member_ids
                else Qt.CheckState.Unchecked)
        self.assertEqual(set(self.page._selected_unknown_ids()), set(member_ids))

    def select_unknown_row(self, member_id):
        self.select_player(None)
        table = self.page.unassigned_table
        for row in range(table.rowCount()):
            if table.item(row, 1).data(Qt.ItemDataRole.UserRole) == member_id:
                table.setCurrentCell(row, 1)
                self.assertNotIn(member_id, self.page._selected_unknown_ids())
                return
        self.fail(f"Member {member_id!r} ist nicht sichtbar")

    def test_checkbox_and_single_row_selection_are_independent_and_stable(self):
        self.select_unknown_row("m1005")
        table = self.page.unassigned_table
        checkbox_row = next(row for row in range(table.rowCount())
                            if table.item(row, 0).data(Qt.ItemDataRole.UserRole) == "m1008")
        rect = table.visualItemRect(table.item(checkbox_row, 0))
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
        self.assertEqual(self.page._single_unknown_id(), "m1005")
        self.assertEqual(self.page._selected_unknown_ids(), ("m1008",))
        table.horizontalHeader().sectionClicked.emit(1)
        self.assertEqual(self.page._single_unknown_id(), "m1005")
        self.assertEqual(self.page._selected_unknown_ids(), ("m1008",))
        self.page.search.setText("Zweitfrei")
        self.assertEqual(self.page.unassigned_table.rowCount(), 1)
        self.assertEqual(self.page._selected_unknown_ids(), ("m1008",))
        self.page.search.clear()
        self.assertEqual(self.page._selected_unknown_ids(), ("m1008",))

    def test_action_selection_and_multi_buttons_follow_checkbox_count(self):
        self.select_unknown_row("m1007")
        self.assertEqual(self.page._unknown_action_ids(), ("m1007",))
        self.assertEqual(self.page.assign_button.styleSheet(), "")
        self.select_unknown("m1005", "m1006", "m1008")
        self.page._select_unknown_row("m1007")
        self.assertEqual(set(self.page._unknown_action_ids()),
                         {"m1005", "m1006", "m1008"})
        self.assertTrue(self.page.create_button.isHidden())
        self.assertFalse(self.page.bulk_create_button.isHidden())
        for button in (self.page.assign_button, self.page.bulk_create_button):
            self.assertIn("(3)", button.text())
            self.assertTrue(button.property("multiSelected"))
        for button in (self.page.bulk_active_button,
                       self.page.bulk_inactive_button):
            self.assertTrue(button.isHidden())
            self.assertFalse(button.isEnabled())
        self.select_unknown("m1005")
        self.assertEqual(self.page._unknown_action_ids(), ("m1005",))
        self.assertFalse(self.page.create_button.isHidden())
        self.assertTrue(self.page.bulk_create_button.isHidden())
        self.assertNotIn("(3)", self.page.assign_button.text())
        self.assertFalse(self.page.assign_button.property("multiSelected"))
        self.assertEqual(self.page.assign_button.styleSheet(), "")
        self.select_unknown()
        self.assertEqual(self.page._unknown_action_ids(), ("m1007",))
        self.assertEqual(self.page.bulk_inactive_button.styleSheet(), "")

    def test_select_all_uses_visible_rows_and_clear_removes_every_checkbox(self):
        self.select_unknown("m1005", "m1008")
        self.page.search.setText("Bierbart")
        self.assertEqual(self.page.unassigned_table.rowCount(), 1)
        self.page.clear_selection_button.click()
        self.assertEqual(self.page._selected_unknown_ids(), ())
        self.assertEqual(self.page._unknown_action_ids(), ("m1005",))
        self.page.select_all_button.click()
        self.assertEqual(self.page._selected_unknown_ids(), ("m1005",))
        self.page.search.clear()
        self.assertEqual(self.page._selected_unknown_ids(), ("m1005",))

    def test_empty_store_unknown_entry_and_stable_non_prominent_ids(self):
        self.page.set_store(IdentityV2Store(), reset_filters=True)
        self.assertEqual(self.page.player_table.rowCount(), 1)
        self.assertIn(tr("identity_v2_players.unknown_count", count=0),
                      self.page.player_table.item(0, 0).text())
        self.assertTrue(any(tr("identity_v2_players.no_players") in label.text()
                            for label in self.page.detail_host.findChildren(QLabel)))
        self.page.status_filter.setCurrentIndex(
            self.page.status_filter.findData("graveyard"))
        self.assertTrue(any(tr("identity_v2_players.graveyard_empty") in label.text()
                            for label in self.page.detail_host.findChildren(QLabel)))
        self.page.set_store(self.store, reset_filters=True)
        self.assertEqual(self.page.player_table.rowCount(), 4)
        self.assertIn("(4)", self.page.player_table.item(0, 0).text())
        self.assertEqual(self.page.player_table.item(1, 0).text(), "Leer")
        self.assertEqual(self.page.player_table.item(1, 1).text(), "–")
        self.assertEqual(self.page.player_table.item(1, 2).text(), "0")
        for index in range(1, self.page.player_table.rowCount()):
            item = self.page.player_table.item(index, 0)
            self.assertNotIn("p000", item.text())
            self.assertIn("p000", item.toolTip())

    def test_main_active_inactive_and_graveyard_groups_ignore_legacy_roles(self):
        self.select_player("p0001")
        self.assertEqual(self.page.group_rows["main"], ("m1000",))
        self.assertEqual(self.page.group_rows["active"], ("m1001",))
        self.assertEqual(self.page.group_rows["inactive"], ("m1002",))
        self.assertEqual(self.page.group_rows["graveyard"], ("m1003",))
        self.select_player("p0002")
        self.assertEqual(self.page.group_rows["main"], ())
        self.assertEqual(self.page.group_rows["active"], ("m1004",))
        self.assertTrue(any(tr("identity_v2_players.active_characters") in group.title()
                            for group in self.page.detail_host.findChildren(QGroupBox)))

    def test_search_and_combined_status_filters_keep_unknown_count(self):
        self.page.status_filter.setCurrentIndex(
            self.page.status_filter.findData("active"))
        self.assertIn("(2)", self.page.player_table.item(0, 0).text())
        self.assertTrue(all("Leer" not in self.page.player_table.item(i, 0).text()
                            for i in range(1, self.page.player_table.rowCount())))
        self.page.status_filter.setCurrentIndex(
            self.page.status_filter.findData("inactive"))
        self.assertIn("(1)", self.page.player_table.item(0, 0).text())
        self.select_player("p0001")
        self.assertEqual(self.page.group_rows["inactive"], ("m1002",))
        self.assertEqual(self.page.group_rows["graveyard"], ())
        self.page.status_filter.setCurrentIndex(
            self.page.status_filter.findData("graveyard"))
        self.assertIn("(1)", self.page.player_table.item(0, 0).text())
        self.select_player("p0001")
        self.assertEqual(self.page.group_rows["graveyard"], ("m1003",))
        self.assertEqual(self.page.group_rows["inactive"], ())
        self.page.search.setText("Toterchar")
        self.assertEqual(self.page.group_rows["graveyard"], ("m1003",))
        self.page.status_filter.setCurrentIndex(0)
        self.page.search.setText("Marten")
        self.select_player("p0002")
        self.assertEqual(self.page.group_rows["active"], ("m1004",))

    def test_create_and_assign_unknown_character_use_services(self):
        before = self.store.to_payload()
        self.select_unknown_row("m1005")
        self.page.create_button.click()
        self.assertEqual(len(self.changed), 1)
        self.assertEqual(self.store.to_payload(), before)
        created = next(item for item in self.page.store.members
                       if item.memberId == "m1005")
        player = self.page.store.get_player(created.playerId)
        self.assertEqual((player.displayName, player.mainMemberId),
                         ("Bierbart", "m1005"))
        self.assertEqual({item.playerId for item in self.page.store.attendance
                          if item.memberId == "m1005"}, {player.playerId})
        self.select_unknown_row("m1006")
        with patch.object(self.page, "_choose_player", return_value="p0002"):
            self.page.assign_button.click()
        self.assertEqual(self.page.store.get_player_for_member("m1006").playerId,
                         "p0002")
        self.assertIsNone(self.page.store.get_main_member("p0002"))
        self.assertEqual({item.playerId for item in self.page.store.attendance
                          if item.memberId == "m1006"}, {"p0002"})

    def test_existing_player_assignment_uses_checkbox_instead_of_focused_row(self):
        self.select_unknown_row("m1005")
        table = self.page.unassigned_table
        checkbox_row = next(row for row in range(table.rowCount())
                            if table.item(row, 0).data(Qt.ItemDataRole.UserRole) == "m1008")
        table.item(checkbox_row, 0).setCheckState(Qt.CheckState.Checked)
        with patch.object(self.page, "_choose_player", return_value="p0002"):
            self.page.assign_button.click()
        self.assertIsNone(self.page.store.get_player_for_member("m1005"))
        self.assertEqual(self.page.store.get_player_for_member("m1008").playerId,
                         "p0002")
        self.assertIsNone(self.page.store.get_main_member("p0002"))
        self.assertNotIn("m1008", self.page._checked_unassigned_ids)

    def test_three_checked_members_assign_to_one_player_without_focused_row(self):
        self.select_unknown("m1005", "m1006", "m1008")
        self.page._select_unknown_row("m1007")
        with (patch.object(self.page, "_choose_player", return_value="p0002"),
              patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.Yes)):
            self.page.assign_button.click()
        self.assertEqual(len(self.changed), 1)
        self.assertEqual({self.page.store.get_player_for_member(member_id).playerId
                          for member_id in ("m1005", "m1006", "m1008")}, {"p0002"})
        self.assertIsNone(self.page.store.get_player_for_member("m1007"))

    def test_selected_members_have_no_accessible_activity_action(self):
        self.select_unknown("m1005", "m1006", "m1008")
        self.page._select_unknown_row("m1007")
        before = self.page.store.to_payload()
        self.assertTrue(self.page.bulk_inactive_button.isHidden())
        self.assertTrue(self.page.bulk_active_button.isHidden())
        self.assertFalse(self.page.bulk_inactive_button.isEnabled())
        self.assertFalse(self.page.bulk_active_button.isEnabled())
        self.page.bulk_inactive_button.click()
        self.page.bulk_active_button.click()
        self.assertEqual(self.page.store.to_payload(), before)
        self.assertEqual(self.changed, [])
        self.assertEqual(next(member.lifeStatus for member in self.page.store.members
                              if member.memberId == "m1007"), "dead")

    def test_three_checked_members_create_separate_players_without_focused_row(self):
        self.page.set_store(set_member_activity(self.page.store, "m1006", "active"))
        self.select_unknown("m1005", "m1006", "m1008")
        self.page._select_unknown_row("m1007")
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            self.page.bulk_create_button.click()
        created = {member.memberId: self.page.store.get_player(member.playerId)
                   for member in self.page.store.members
                   if member.memberId in {"m1005", "m1006", "m1008"}}
        self.assertEqual(len({player.playerId for player in created.values()}), 3)
        for member_id, player in created.items():
            member = next(item for item in self.page.store.members
                          if item.memberId == member_id)
            self.assertEqual((player.displayName, player.mainMemberId),
                             (member.name, member_id))
        self.assertIsNone(self.page.store.get_player_for_member("m1007"))

    def test_single_checkbox_create_and_last_uncheck_restore_row_actions(self):
        self.select_unknown_row("m1008")
        self.select_unknown("m1005")
        self.assertEqual(self.page._unknown_action_ids(), ("m1005",))
        self.page.create_button.click()
        self.assertIsNotNone(self.page.store.get_player_for_member("m1005"))
        self.assertIsNone(self.page.store.get_player_for_member("m1008"))
        self.select_unknown("m1008")
        self.assertEqual(self.page._unknown_action_ids(), ("m1008",))
        self.select_unknown()
        self.page._select_unknown_row("m1008")
        self.assertEqual(self.page._unknown_action_ids(), ("m1008",))
        self.assertTrue(self.page.bulk_inactive_button.isHidden())
        self.assertFalse(self.page.bulk_inactive_button.isEnabled())
        self.assertEqual(next(member.lifeStatus for member in self.page.store.members
                              if member.memberId == "m1008"), "active")

    def test_main_activity_reassign_and_unassign_keep_historical_roles(self):
        self.select_player("p0001")
        row = self.page.member_rows["m1001"]
        next(button for button in row.findChildren(QPushButton)
             if button.text() == tr("identity_v2_players.set_main")).click()
        self.assertEqual(self.page.store.get_main_member("p0001").memberId, "m1001")
        self.assertEqual(self.page.group_rows["active"], ("m1000",))
        history = [item.to_dict() for item in self.page.store.get_player("p0001").mainHistory]
        attendance = [item.to_dict() for item in self.page.store.attendance]
        row = self.page.member_rows["m1001"]
        menu = row.findChild(QToolButton).menu()
        self.assertNotIn(tr("identity_v2_players.set_inactive"),
                         [action.text() for action in menu.actions()])
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            self.page.detail_host.findChildren(QPushButton, "playerActivityButton")[-1].click()
        self.assertEqual(self.page.store.get_main_member("p0001").memberId, "m1001")
        self.assertFalse(self.page.store.player_is_active("p0001"))
        self.assertEqual(self.page.group_rows["main"], ("m1001",))
        self.assertEqual(set(self.page.group_rows["inactive"]), {"m1000", "m1002"})
        self.assertIn(tr("identity_v2_views.role_main"),
                      self.page.member_rows["m1001"].findChild(QLabel).toolTip())
        self.assertEqual([item.to_dict() for item in self.page.store.get_player(
            "p0001").mainHistory], history)
        row = self.page.member_rows["m1001"]
        self.assertNotIn(tr("identity_v2_players.reactivate"),
                         [button.text() for button in row.findChildren(QPushButton)])
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            self.page.detail_host.findChildren(QPushButton, "playerActivityButton")[-1].click()
        self.assertEqual(self.page.store.get_main_member("p0001").memberId, "m1001")
        self.assertEqual(self.page.group_rows["main"], ("m1001",))
        self.assertEqual(self.page.group_rows["active"], ("m1000",))
        self.assertEqual(self.page.group_rows["inactive"], ("m1002",))
        self.assertEqual([item.to_dict() for item in self.page.store.get_player(
            "p0001").mainHistory], history)
        self.assertEqual([item.to_dict() for item in self.page.store.attendance],
                         attendance)
        with (patch.object(self.page, "_choose_player", return_value="p0002"),
              patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.Yes),
              patch.object(QMessageBox, "warning") as warning):
            self.page._reassign_member("m1000")
        self.assertTrue(warning.called)
        self.assertEqual(self.page.store.get_player_for_member("m1000").playerId,
                         "p0001")
        self.assertEqual({item.attendanceType for item in self.page.store.attendance
                          if item.memberId == "m1001"}, {"twink"})
        with (patch.object(self.page, "_choose_player", return_value="p0002"),
              patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.Yes)):
            self.page._reassign_member("m1002")
        self.assertEqual(self.page.store.get_player_for_member("m1002").playerId,
                         "p0002")
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            self.page._unassign_member("m1002")
        self.assertIsNone(self.page.store.get_player_for_member("m1002"))
        self.assertIsNone(self.page._current_player_id())

    def test_single_assign_and_bulk_create_are_all_or_nothing(self):
        self.select_unknown_row("m1005")
        with patch.object(self.page, "_choose_player", return_value="p0002"):
            self.page.assign_button.click()
        self.assertEqual(len(self.changed), 1)
        self.assertEqual(self.page.store.get_player_for_member("m1005").playerId,
                         "p0002")
        self.assertIsNone(self.page.store.get_player_for_member("m1008"))
        self.assertIsNone(self.page.store.get_main_member("p0002"))

        self.select_unknown("m1006", "m1007")
        before = self.page.store.to_payload()
        with patch.object(QMessageBox, "warning") as warning:
            self.page._create_many_players()
        self.assertTrue(warning.called)
        self.assertEqual(self.page.store.to_payload(), before)
        self.assertEqual(len(self.changed), 1)

        self.assertTrue(self.page.bulk_active_button.isHidden())
        self.assertTrue(self.page.bulk_inactive_button.isHidden())
        self.select_unknown("m1006", "m1007")
        self.assertFalse(self.page.bulk_create_button.isEnabled())

    def test_bulk_separate_players_cancel_and_success(self):
        self.select_unknown("m1005", "m1008")
        before = self.page.store.to_payload()
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.No):
            self.page.bulk_create_button.click()
        self.assertEqual(self.page.store.to_payload(), before)
        self.assertEqual(self.changed, [])
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            self.page.bulk_create_button.click()
        self.assertEqual(len(self.changed), 1)
        players = {member.memberId: self.page.store.get_player(member.playerId)
                   for member in self.page.store.members
                   if member.memberId in {"m1005", "m1008"}}
        self.assertEqual(len({item.playerId for item in players.values()}), 2)
        self.assertEqual({item.mainMemberId for item in players.values()},
                         {"m1005", "m1008"})
        self.assertEqual({item.displayName for item in players.values()},
                         {"Bierbart", "Zweitfrei"})
        self.assertTrue(all(entry.playerId == self.page.store.get_player_for_member(
            entry.memberId).playerId for entry in self.page.store.attendance
            if entry.memberId in players))

    def test_player_activity_cancel_and_restore_all_living_members_once(self):
        self.select_player("p0001")
        self.assertEqual(
            self.page.detail_host.findChildren(QPushButton, "playerActivityButton")[-1].text(),
            tr("identity_v2_players.deactivate_player"))
        before = self.page.store.to_payload()
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.No):
            self.page.detail_host.findChildren(QPushButton, "playerActivityButton")[-1].click()
        self.assertEqual(self.page.store.to_payload(), before)
        self.assertEqual(self.changed, [])
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            self.page.detail_host.findChildren(QPushButton, "playerActivityButton")[-1].click()
        self.assertEqual(len(self.changed), 1)
        self.assertEqual(self.page.store.get_main_member("p0001").memberId, "m1000")
        self.assertEqual(self.page.group_rows["main"], ("m1000",))
        self.assertEqual(set(self.page.group_rows["inactive"]), {"m1001", "m1002"})
        self.assertEqual(self.page.group_rows["graveyard"], ("m1003",))
        self.assertEqual(
            self.page.detail_host.findChildren(QPushButton, "playerActivityButton")[-1].text(),
            tr("identity_v2_players.reactivate_player"))
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            self.page.detail_host.findChildren(QPushButton, "playerActivityButton")[-1].click()
        self.assertEqual(len(self.changed), 2)
        self.assertEqual({member.memberId: member.lifeStatus
                          for member in self.page.store.members
                          if member.playerId == "p0001"},
                         {"m1000": "active", "m1001": "active",
                          "m1002": "inactive", "m1003": "dead"})
        self.assertEqual(self.page.store.get_main_member("p0001").memberId, "m1000")

    def test_graveyard_character_can_be_reassigned_without_death_changes(self):
        self.select_player("p0001")
        self.assertEqual(self.page.group_rows["graveyard"], ("m1003",))
        with (patch.object(self.page, "_choose_player", return_value="p0002"),
              patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.Yes)):
            self.page._reassign_member("m1003")
        moved = next(item for item in self.page.store.members
                     if item.memberId == "m1003")
        self.assertEqual((moved.playerId, moved.lifeStatus, moved.deathDate),
                         ("p0002", "dead", "2026-02-01"))
        self.assertEqual(self.page.group_rows["graveyard"], ("m1003",))
        self.select_unknown_row("m1007")
        self.assertTrue(self.page.assign_button.isEnabled())
        self.assertFalse(self.page.bulk_active_button.isEnabled())

    def test_rename_delete_and_cancel_keep_store_consistent(self):
        self.select_player("p0003")
        with patch("app.identity_v2_players_qt.QInputDialog.getText",
                   return_value=("Schneeflocke", True)):
            self.page._rename_player("p0003")
        self.assertEqual(self.page.store.get_player("p0003").displayName,
                         "Schneeflocke")
        before = self.page.store.to_payload()
        changed_count = len(self.changed)
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.No):
            self.page._delete_player("p0003")
        self.assertEqual(self.page.store.to_payload(), before)
        self.assertEqual(len(self.changed), changed_count)
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            self.page._delete_player("p0003")
        self.assertIsNone(self.page.store.get_player("p0003"))

    def test_player_table_columns_and_explicit_sorts_keep_unknown_pinned(self):
        table = self.page.player_table
        self.assertEqual(table.columnCount(), 3)
        self.assertEqual(table.item(0, 0).data(Qt.ItemDataRole.UserRole), None)
        self.assertEqual(table.item(0, 0).text(),
                         tr("identity_v2_players.unknown_count", count=4))
        rows = {table.item(row, 0).data(Qt.ItemDataRole.UserRole): row
                for row in range(1, table.rowCount())}
        self.assertEqual(table.item(rows["p0001"], 1).text(), "Schneeflocke")
        self.assertEqual(table.item(rows["p0001"], 2).text(), "4")
        self.assertEqual(table.item(rows["p0002"], 1).text(), "–")
        self.assertEqual(table.item(rows["p0002"], 2).text(), "1")
        self.assertEqual(table.item(rows["p0003"], 1).text(), "–")
        self.assertEqual(table.item(rows["p0003"], 2).text(), "0")

        self.page._sort_players(2)
        ids = [table.item(row, 0).data(Qt.ItemDataRole.UserRole)
               for row in range(1, table.rowCount())]
        self.assertEqual(ids, ["p0003", "p0002", "p0001"])
        self.assertIsNone(table.item(0, 0).data(Qt.ItemDataRole.UserRole))
        self.page._sort_players(1)
        self.assertEqual(table.item(0, 0).data(Qt.ItemDataRole.UserRole), None)
        self.assertEqual(table.item(1, 0).data(Qt.ItemDataRole.UserRole), "p0001")
        self.select_player("p0002")
        self.page._sort_players(0)
        self.assertEqual(self.page._current_player_id(), "p0002")

    def test_unknown_raid_columns_use_attendance_and_sort_by_typed_values(self):
        table = self.page.unassigned_table
        row = next(index for index in range(table.rowCount())
                   if table.item(index, 1).data(Qt.ItemDataRole.UserRole) == "m1005")
        self.assertEqual(table.columnCount(), 7)
        self.assertEqual(table.item(row, 4).data(Qt.ItemDataRole.UserRole), 3)
        self.assertEqual(table.item(row, 5).data(Qt.ItemDataRole.UserRole).isoformat(),
                         "2026-01-01")
        self.assertEqual(table.item(row, 6).data(Qt.ItemDataRole.UserRole).isoformat(),
                         "2026-02-01")
        no_attendance_row = next(index for index in range(table.rowCount())
                                 if table.item(index, 1).data(
                                     Qt.ItemDataRole.UserRole) == "m1007")
        self.assertEqual(table.item(no_attendance_row, 4).data(Qt.ItemDataRole.UserRole), 0)
        self.assertEqual(table.item(no_attendance_row, 5).text(), "–")
        self.assertEqual(table.item(no_attendance_row, 6).text(), "–")

        self.page._select_unknown_row("m1005")
        table.item(row, 0).setCheckState(Qt.CheckState.Checked)
        self.page._sort_unknown(5)
        self.assertEqual(self.page._single_unknown_id(), "m1005")
        self.assertEqual(self.page._selected_unknown_ids(), ("m1005",))
        self.assertEqual(table.item(table.rowCount() - 1, 1).data(
            Qt.ItemDataRole.UserRole), "m1007")
        self.page._sort_unknown(4)
        self.assertEqual(table.item(0, 4).data(Qt.ItemDataRole.UserRole), 0)
        expected_first_ids = {
            1: "m1005", 2: "m1006", 3: "m1005", 4: "m1007",
            5: "m1005", 6: "m1006",
        }
        for column, first_id in expected_first_ids.items():
            self.page._sort_unknown(column)
            self.assertEqual(table.item(0, 1).data(Qt.ItemDataRole.UserRole),
                             first_id, f"Sortierung Spalte {column}")

    def test_store_refresh_does_not_resort_until_header_click(self):
        self.page._sort_unknown(3)
        before = self.page._visible_unknown_ids()
        changed = set_member_activity(self.page.store, "m1005", "inactive")
        self.page.set_store(changed)
        self.assertEqual(self.page._visible_unknown_ids(), before)
        self.page._sort_unknown(3)
        after = self.page._visible_unknown_ids()
        self.assertNotEqual(after, before)

    def test_table_widths_and_splitter_settings_restore_independently(self):
        settings = {
            PLAYER_COLUMN_WIDTHS_SETTING: [177, 92, 63],
            UNKNOWN_COLUMN_WIDTHS_SETTING: [38, 205, 111, 87, 61, 123, 124],
            PLAYER_SPLITTER_SIZES_SETTING: [310, 900],
        }
        page = IdentityV2PlayersPage(layout_settings=settings)
        page.resize(1400, 800)
        page.set_store(self.store)
        page.show()
        self.app.processEvents()
        try:
            self.assertEqual([page.player_table.columnWidth(i) for i in range(3)],
                             settings[PLAYER_COLUMN_WIDTHS_SETTING])
            self.select_player(None)
            self.assertEqual([page.unassigned_table.columnWidth(i) for i in range(7)],
                             settings[UNKNOWN_COLUMN_WIDTHS_SETTING])
            page.player_table.setColumnWidth(0, 181)
            page.unassigned_table.setColumnWidth(1, 220)
            page.splitter.setSizes([400, 900])
            self.app.processEvents()
            saved = page.layout_settings()
            self.assertEqual(saved[PLAYER_COLUMN_WIDTHS_SETTING][0], 181)
            self.assertEqual(saved[UNKNOWN_COLUMN_WIDTHS_SETTING][1], 220)
            expected_ratio = 400 / 1300
            actual_ratio = saved[PLAYER_SPLITTER_SIZES_SETTING][0] / sum(
                saved[PLAYER_SPLITTER_SIZES_SETTING])
            self.assertAlmostEqual(actual_ratio, expected_ratio, places=2)
            restored = IdentityV2PlayersPage(layout_settings=saved)
            restored.resize(1400, 800)
            restored.set_store(self.store)
            restored.show()
            self.app.processEvents()
            try:
                self.assertEqual(restored.player_table.columnWidth(0), 181)
                self.assertEqual(restored.unassigned_table.columnWidth(1), 220)
            finally:
                restored.close()
        finally:
            page.close()


    def test_row_hover_keeps_multiselect_and_gold_button_state(self):
        self.page.resize(1300, 800)
        self.page.show()
        self.select_unknown("m1005", "m1006")
        self.app.processEvents()
        table = self.page.unassigned_table
        before_store = self.page.store.to_payload()
        before_checked = set(self.page._checked_unassigned_ids)
        before_counter = self.page.selection_count_label.text()
        button = self.page.assign_button
        self.assertTrue(button.property("multiSelected"))
        self.assertEqual(button.styleSheet(), "")
        QTest.mouseMove(table.viewport(),
                        table.visualItemRect(table.item(0, 1)).center())
        self.app.processEvents()
        self.assertEqual(self.page.unknown_row_hover.row, 0)
        self.assertEqual(set(self.page._checked_unassigned_ids), before_checked)
        self.assertEqual(self.page.selection_count_label.text(), before_counter)
        self.assertEqual(self.page.store.to_payload(), before_store)
        before_size = button.size()
        QTest.mouseMove(button, button.rect().center())
        self.app.processEvents()
        self.assertEqual(button.size(), before_size)
        self.assertTrue(button.property("multiSelected"))


if __name__ == "__main__":
    unittest.main()
