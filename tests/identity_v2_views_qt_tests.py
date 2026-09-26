"""Offscreen table interaction checks for the V2 roster and raid views."""

import os
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from app.identity_v2_views_qt import IdentityV2RaidPage, IdentityV2RosterPage
except ImportError:
    Qt = QApplication = IdentityV2RaidPage = IdentityV2RosterPage = None

from app.identity_v2_views import IdentityV2ViewData
from app.identity_v2 import (Attendance, EternalDkpRecord, IdentityV2Store,
                             Member, Raid)
from app.identity_v2_dkp import IdentityV2DkpProjection
from app.identity_v2_attendance_adapter import V2AttendanceAdapter
from app.identity_v2_roster import build_v2_roster_items
from app.rewards import RewardRegistry
from tests.identity_v2_views_tests import view_fixture


@unittest.skipIf(QApplication is None, "PySide6 ist lokal nicht verfügbar.")
class IdentityV2ViewsQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.store = view_fixture()
        self.before = self.store.to_payload()
        self.data = IdentityV2ViewData.from_store(self.store)

    def test_roster_search_class_filter_and_explicit_header_sort(self):
        page = IdentityV2RosterPage()
        self.addCleanup(page.close)
        page.set_view_data(self.data)
        self.assertEqual(page.table.rowCount(), 4)
        self.assertEqual(page.table.item(0, 0).text(), "Dritt")
        self.assertEqual(page.HEADERS[:9], (
            "character", "class", "rank", "role", "character_type",
            "gear_status", "raid_status", "raid_count", "raid_days"))
        self.assertEqual(page.table.item(3, 7).text(), "0")
        page.search.setText("Gleich")
        self.assertEqual(page.table.rowCount(), 2)
        page.class_filter.setCurrentIndex(page.class_filter.findData("Mage"))
        self.assertEqual(page.table.rowCount(), 1)
        self.assertEqual(page.table.item(0, 0).data(Qt.ItemDataRole.UserRole), "m2")
        page.class_filter.setCurrentIndex(0)
        page.search.clear()
        page.table.horizontalHeader().sectionClicked.emit(7)
        order = [row.member_id for row in page._rows]
        self.assertEqual(page.table.item(0, 7).text(), "0")
        page.search.setText("Gleich")
        page.search.clear()
        self.assertEqual([row.member_id for row in page._rows], order)
        self.assertFalse(page.table.isSortingEnabled())
        self.assertEqual(self.store.to_payload(), self.before)

    def test_roster_shows_only_active_rank_and_point_columns(self):
        self.store.eternalDkpRecords.append(
            EternalDkpRecord("d3", "e3", "m1", "1:1", "DM", 100))
        points = SimpleNamespace(
            character_points=lambda member_id: 80 if member_id == "m1" else 0,
            eternal_character_points=lambda member_id: 80 if member_id == "m1" else 0,
        )
        projection = IdentityV2DkpProjection(
            self.store, available_by_member={"m1": 999}, raid_points_projection=points)
        page = IdentityV2RosterPage()
        self.addCleanup(page.close)
        page.set_view_data(IdentityV2ViewData.from_store(self.store))
        page.set_dkp_projection(projection)
        row = next(index for index in range(page.table.rowCount())
                   if page.table.item(index, 0).data(Qt.ItemDataRole.UserRole) == "m1")
        self.assertEqual(page.table.columnCount(), 16)
        self.assertEqual(page.table.item(row, 12).text(), "80")
        self.assertEqual(page.table.item(row, 13).text(), "80")
        self.assertEqual(page.table.item(row, 2).text(), "Holz 1")
        self.assertFalse(page.table.item(row, 2).icon().isNull())
        self.assertTrue(all(page.table.isColumnHidden(column) for column in (9, 10, 11)))
        self.assertTrue(all(not page.table.isColumnHidden(column)
                            for column in (12, 13, 14)))
        self.assertEqual(tuple(key for index, key in enumerate(page.HEADERS)
                               if not page.table.isColumnHidden(index)),
                         ("character", "class", "rank", "role", "character_type",
                          "gear_status", "raid_status", "raid_count", "raid_days",
                          "raid_points", "eternal_raid_points", "player_raid_points",
                          "armory"))
        page.set_active_point_system("eternal_dkp")
        self.assertEqual(page.table.item(row, 9).text(), "999")
        self.assertEqual(page.table.item(row, 2).text(), "Holz 1")
        self.assertFalse(page.table.item(row, 2).icon().isNull())
        self.assertTrue(all(not page.table.isColumnHidden(column)
                            for column in (9, 10, 11)))
        self.assertTrue(all(page.table.isColumnHidden(column) for column in (12, 13, 14)))
        self.assertEqual(tuple(key for index, key in enumerate(page.HEADERS)
                               if not page.table.isColumnHidden(index)),
                         ("character", "class", "rank", "role", "character_type",
                          "gear_status", "raid_status", "raid_count", "raid_days",
                          "available_dkp", "eternal_dkp_character",
                          "eternal_dkp_player", "armory"))
        page.table.horizontalHeader().sectionClicked.emit(9)

    def test_roster_matrix_counts_class_and_armory_use_member_identity(self):
        self.store.raids.append(Raid("r3", "2025-01-01", name="Ony"))
        self.store.attendance.append(
            Attendance("a5", "r3", "m1", "main", status="bench"))
        self.store.members[0] = replace(
            self.store.members[0], region="US", realm="other-realm",
            gameVersion="classic-era-test", raidRole="healer")
        before = self.store.to_payload()
        adapter = V2AttendanceAdapter(self.store)
        projection = IdentityV2DkpProjection(self.store)
        items = build_v2_roster_items(
            self.store, None, None, projection, RewardRegistry(), adapter)
        page = IdentityV2RosterPage(embedded=True)
        self.addCleanup(page.close)
        page.set_roster_items(items)
        row = next(index for index in range(page.table.rowCount())
                   if page.table.item(index, 0).data(Qt.ItemDataRole.UserRole) == "m1")
        self.assertEqual(page.table.item(row, 7).text(), "3")
        self.assertEqual(page.table.item(row, 8).text(), "2")
        self.assertEqual(page.table.item(row, 3).text(), "Heiler")
        self.assertEqual(page.table.item(row, 1).text(), "Priest")
        self.assertFalse(page.table.item(row, 1).icon().isNull())
        self.assertTrue(page.table.item(row, 1).foreground().color().isValid())
        self.assertNotEqual(page.table.item(row, 1).foreground().color().name(), "#000000")
        self.assertEqual(page.table.item(row, 15).text(), "Armory")
        self.assertIn("/US/other-realm/Gleich?game_version=classic-era-test",
                      page.table.item(row, 15).toolTip())
        other = next(index for index in range(page.table.rowCount())
                     if page.table.item(index, 0).data(Qt.ItemDataRole.UserRole) == "m2")
        self.assertEqual(page.table.item(other, 15).text(), "Armory")
        self.assertIn("/EU/stitches/Gleich?game_version=classic1x",
                      page.table.item(other, 15).toolTip())
        with patch("app.identity_v2_views_qt.QDesktopServices.openUrl") as open_url:
            page._cell_clicked(row, 15)
            page._cell_clicked(other, 15)
            self.assertEqual(open_url.call_count, 2)
            self.assertNotEqual(open_url.call_args_list[0].args[0].toString(),
                                open_url.call_args_list[1].args[0].toString())
        page.set_roster_items(tuple(replace(item, armoryUrl=None)
                                    if item.memberId == "m2" else item for item in items))
        other = next(index for index in range(page.table.rowCount())
                     if page.table.item(index, 0).data(Qt.ItemDataRole.UserRole) == "m2")
        self.assertEqual(page.table.item(other, 15).text(), "")
        with patch("app.identity_v2_views_qt.QDesktopServices.openUrl") as open_url:
            page._cell_clicked(other, 15)
            open_url.assert_not_called()
        page.select_member("m1")
        page.set_roster_items(tuple(replace(item, matrixRaidCount=10)
                                    if item.memberId == "m1" else item for item in items))
        page.table.horizontalHeader().sectionClicked.emit(7)
        self.assertEqual(page._rows[-1].memberId, "m1")
        self.assertEqual(page.selected_member_id(), "m1")
        self.assertEqual(self.store.to_payload(), before)

    def test_roster_armory_uses_v2_project_realm_before_app_default(self):
        self.store.realm = "project-realm"
        items = build_v2_roster_items(
            self.store, None, None, None, RewardRegistry())
        self.assertTrue(all("/EU/project-realm/" in item.armoryUrl
                            for item in items))

    def test_raid_selection_detail_filter_and_historical_role_display(self):
        page = IdentityV2RaidPage()
        self.addCleanup(page.close)
        page.set_view_data(self.data)
        self.assertEqual(page.raid_table.rowCount(), 2)
        self.assertEqual(page.raid_table.item(0, 0).text(), "2025-01-01")
        self.assertEqual(page.raid_table.item(0, 3).text(), "3")
        self.assertEqual(page.detail_table.rowCount(), 3)
        roles = {page.detail_table.item(row, 3).text()
                 for row in range(page.detail_table.rowCount())}
        self.assertEqual(roles, {"Main", "Twink", "Unbekannt"})
        guids = {page.detail_table.item(row, 4).text()
                 for row in range(page.detail_table.rowCount())}
        self.assertIn("1:0", guids)
        page.detail_search.setText("Gleich")
        self.assertEqual(page.detail_table.rowCount(), 2)
        self.assertEqual({page.detail_table.item(row, 2).text() for row in range(2)},
                         {"m1", "m2"})
        page.raid_search.setText("BWL")
        self.assertEqual(page.raid_table.rowCount(), 1)
        self.assertEqual(page.raid_table.item(0, 1).text(), "BWL")
        page.detail_search.clear()
        self.assertEqual(page.detail_table.rowCount(), 1)
        page.raid_table.horizontalHeader().sectionClicked.emit(2)
        order = [row.raid_id for row in page._raids]
        page.raid_search.clear()
        self.assertEqual([row.raid_id for row in page._raids], order)
        self.assertEqual(page.raid_table.item(page.raid_table.currentRow(), 1).text(),
                         "BWL")
        self.assertEqual(page.detail_table.rowCount(), 1)
        self.assertFalse(page.raid_table.isSortingEnabled())
        self.assertEqual(self.store.to_payload(), self.before)

    def test_unknown_class_is_visible_and_filterable(self):
        store = IdentityV2Store(members=[
            Member("m1000", "CSV-Neuling", None),
            Member("m1001", "CLM-Member", "Priest", clmGuid="1:1"),
        ])
        page = IdentityV2RosterPage()
        self.addCleanup(page.close)
        page.set_view_data(IdentityV2ViewData.from_store(store))
        index = page.class_filter.findData("__unknown__")
        self.assertGreaterEqual(index, 0)
        page.class_filter.setCurrentIndex(index)
        self.assertEqual(page.table.rowCount(), 1)
        self.assertEqual(page.table.item(0, 0).text(), "CSV-Neuling")
        self.assertIn("unbekannt", page.table.item(0, 1).text().casefold())

    def test_raid_report_urls_are_individual_safe_desktop_links(self):
        first, second = self.data.raids
        urls = (
            "https://vanilla.warcraftlogs.com/reports/AAA",
            "https://vanilla.warcraftlogs.com/reports/BBB",
            "http://vanilla.warcraftlogs.com/reports/CCC",
            "javascript:alert(1)",
        )
        data = replace(self.data, raids=(
            replace(first, csv_report_urls=urls),
            replace(second, csv_report_urls=()),
        ))
        page = IdentityV2RaidPage()
        self.addCleanup(page.close)
        page.set_view_data(data)
        first_row = next(
            index for index in range(page.raid_table.rowCount())
            if page.raid_table.item(index, 0).data(Qt.ItemDataRole.UserRole)
            == first.raid_id
        )
        links = page.raid_table.cellWidget(first_row, 6)
        self.assertEqual(links.text().count("<a "), 3)
        self.assertIn("javascript:alert(1)", links.text())
        self.assertIn("reports/AAA", links.toolTip())
        self.assertEqual(links.cursor().shape(), Qt.CursorShape.PointingHandCursor)

        with patch("app.identity_v2_views_qt.QDesktopServices.openUrl") as open_url:
            for url in urls:
                links.linkActivated.emit(url)
            self.assertEqual(open_url.call_count, 3)
            self.assertEqual([call.args[0].toString() for call in open_url.call_args_list],
                             list(urls[:3]))

        second_row = next(
            index for index in range(page.raid_table.rowCount())
            if page.raid_table.item(index, 0).data(Qt.ItemDataRole.UserRole)
            == second.raid_id
        )
        self.assertEqual(page.raid_table.cellWidget(second_row, 6).text(), "–")


if __name__ == "__main__":
    unittest.main()
