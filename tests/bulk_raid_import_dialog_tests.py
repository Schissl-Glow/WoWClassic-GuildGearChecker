from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.GuildGearChecker import GuildModel, RAID_TYPES
from app.GuildGearCheckerQt import BulkRaidImportDialog
from app.window_geometry import read_suite_settings


class BulkRaidImportDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-bulk-dialog-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "csv"
        self.folder.mkdir()
        self.settings_path = self.root / "config" / "suite_settings.json"
        self.model = GuildModel(); self.model.new_empty()
        self.member = self.model.add_member("Bulk Tester", "Test")
        self.model.assign_character_type(self.member.id, "main", None, "not_set")

    def _write_csv(self, filename: str, raid_type: str, raid_date: str,
                   report: str = "") -> Path:
        path = self.folder / filename
        metadata = (
            f'"META_RAID_TYPE","{raid_type}"\n'
            f'"META_RAID_DATE","{raid_date}"\n'
        )
        if report:
            metadata += f'"META_REPORT_URL","{report}"\n'
        path.write_text(
            metadata + '"Name","Amount"\n"Bulk Tester","1"\n',
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _row_for_path(dialog: BulkRaidImportDialog, path: Path) -> int:
        key = dialog._source_path_key(path)
        for row in range(dialog.table.rowCount()):
            item = dialog.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == key:
                return row
        raise AssertionError(f"CSV-Zeile nicht gefunden: {path}")

    def test_sorting_uses_stable_path_identity_and_persists_deselection(self) -> None:
        deselected = self._write_csv(
            "2026-09-08_ZulGurub_Casts.csv", "ZulGurub", "2026-09-08",
            "https://vanilla.warcraftlogs.com/reports/zg",
        )
        sortable = self._write_csv(
            "2026-09-10_BWL_Casts.csv", "BWL", "2026-09-10",
            "https://vanilla.warcraftlogs.com/reports/bwl",
        )
        existing = self._write_csv(
            "2026-09-09_AQ20_Casts.csv", "AQ20", "2026-09-09",
        )
        self.model.create_raid_with_attendance(
            "2026-09-09", "AQ20", "", "AQ20", [self.member.name],
        )

        dialog = BulkRaidImportDialog(None, self.model, self.folder, self.settings_path)
        self.addCleanup(dialog.deleteLater)
        deselected_row = self._row_for_path(dialog, deselected)
        checkbox = dialog.table.item(deselected_row, 0)
        checkbox.setCheckState(Qt.CheckState.Unchecked)
        self.application.processEvents()
        deselected_key = dialog._source_path_key(deselected)
        self.assertNotIn(deselected_key, dialog.selected_paths)
        self.assertIn(
            deselected_key,
            read_suite_settings(dialog._selection_settings_path)[
                dialog.DESELECTED_PATHS_SETTING
            ],
        )

        for column in (1, 2, 3, 5, 6):
            dialog.table.sortItems(column, Qt.SortOrder.AscendingOrder)
            values = [dialog.table.item(row, column).text()
                      for row in range(dialog.table.rowCount())]
            if column == 6:
                dialog.table.sortItems(column, Qt.SortOrder.DescendingOrder)
                descending = [dialog.table.item(row, column).text()
                              for row in range(dialog.table.rowCount())]
                self.assertEqual(descending, list(reversed(values)))
                dialog.table.sortItems(column, Qt.SortOrder.AscendingOrder)
            else:
                self.assertEqual(values, sorted(values))
            row = self._row_for_path(dialog, deselected)
            self.assertEqual(
                dialog.table.item(row, 0).checkState(), Qt.CheckState.Unchecked,
            )
            dialog.table.selectRow(row)
            self.assertEqual(dialog._selected_plan().source_path, deselected)

        dialog.table.sortItems(3, Qt.SortOrder.DescendingOrder)
        link_row = self._row_for_path(dialog, sortable)
        with patch("app.GuildGearCheckerQt.webbrowser.open_new_tab") as opened:
            dialog._table_clicked(link_row, 6)
        opened.assert_called_once_with("https://vanilla.warcraftlogs.com/reports/bwl")
        self.assertEqual(dialog._plan_for_row(link_row).source_path, sortable)
        existing_row = self._row_for_path(dialog, existing)
        self.assertFalse(dialog.table.item(existing_row, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable)

        reopened = BulkRaidImportDialog(None, self.model, self.folder, self.settings_path)
        self.addCleanup(reopened.deleteLater)
        reopened_row = self._row_for_path(reopened, deselected)
        self.assertEqual(
            reopened.table.item(reopened_row, 0).checkState(), Qt.CheckState.Unchecked,
        )
        reopened.table.sortItems(1, Qt.SortOrder.DescendingOrder)
        self.assertNotIn(deselected_key, reopened.selected_paths)

    def test_unknown_type_can_be_overridden_and_becomes_importable(self) -> None:
        source = self._write_csv(
            "2026-09-16_Naxxramas_Casts.csv", "", "2026-09-16",
        )
        original = source.read_bytes()
        dialog = BulkRaidImportDialog(None, self.model, self.folder, self.settings_path)
        self.addCleanup(dialog.deleteLater)
        row = self._row_for_path(dialog, source)
        combo = dialog.table.cellWidget(row, 2)
        self.assertIsNotNone(combo)
        combo.setCurrentIndex(combo.findData(RAID_TYPES[0]))
        self.application.processEvents()
        plan = dialog._plan_for_row(dialog._row_for_source_path(dialog._source_path_key(source)))
        self.assertIn(plan.status, dialog.IMPORTABLE_STATUSES)
        self.assertEqual(plan.raid_type, RAID_TYPES[0])
        self.assertIn(dialog._source_path_key(source), dialog.selected_paths)
        self.assertEqual(source.read_bytes(), original)

    def test_recognized_type_can_be_manually_corrected(self) -> None:
        source = self._write_csv("2026-09-17_BWL_Casts.csv", "BWL", "2026-09-17")
        dialog = BulkRaidImportDialog(None, self.model, self.folder, self.settings_path)
        self.addCleanup(dialog.deleteLater)
        row = self._row_for_path(dialog, source)
        combo = dialog.table.cellWidget(row, 2)
        replacement = next(value for value in RAID_TYPES if value != "BWL")
        combo.setCurrentIndex(combo.findData(replacement))
        self.application.processEvents()
        plan = dialog._plans_by_source_path[dialog._source_path_key(source)]
        self.assertEqual(plan.raid_type, replacement)

    def test_raid_type_override_survives_table_sorting_by_source_identity(self) -> None:
        first = self._write_csv("2026-09-18_BWL_Casts.csv", "BWL", "2026-09-18")
        second = self._write_csv("2026-09-19_MC_Casts.csv", "MC", "2026-09-19")
        dialog = BulkRaidImportDialog(None, self.model, self.folder, self.settings_path)
        self.addCleanup(dialog.deleteLater)
        row = self._row_for_path(dialog, first)
        combo = dialog.table.cellWidget(row, 2)
        combo.setCurrentIndex(combo.findData("MC"))
        self.application.processEvents()
        dialog.table.sortItems(1, Qt.SortOrder.DescendingOrder)
        sorted_row = self._row_for_path(dialog, first)
        self.assertEqual(dialog.table.cellWidget(sorted_row, 2).currentData(), "MC")
        self.assertEqual(dialog._plan_for_row(sorted_row).raid_type, "MC")
        self.assertEqual(dialog._plan_for_row(self._row_for_path(dialog, second)).raid_type, "MC")


if __name__ == "__main__":
    unittest.main()
