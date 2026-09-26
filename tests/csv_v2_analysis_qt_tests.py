"""Offscreen checks for the single read-only V2 CSV bulk review."""

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from app.csv_v2_analysis_ui import CsvV2AnalysisDialog
except ImportError:
    Qt = QApplication = CsvV2AnalysisDialog = None

from app.csv_v2_analysis import analyze_csv_raids_for_v2
from app.identity_v2 import IdentityV2Store, Member
from app.csv_v2_analysis import CsvExistingRaidOption


@unittest.skipIf(QApplication is None, "PySide6 ist lokal nicht verfügbar.")
class CsvV2AnalysisQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = IdentityV2Store(members=[
            Member("m2", "Veniell", "Mage", clmGuid="1:2"),
            Member("m3", "Veniell", "Warrior", clmGuid="1:3"),
        ])
        first = self.root / "2026-07-01_MC_Casts.csv"
        second = self.root / "2026-09-08_ZulGurub_Casts.csv"
        first.write_text('"Name","Amount"\n"Veniell","1"\n"Neu","1"\n',
                         encoding="utf-8")
        second.write_text('"Name","Amount"\n"Veniell","1"\n',
                          encoding="utf-8")
        self.plan = analyze_csv_raids_for_v2(self.store, [second, first])

    def test_one_conflict_table_keeps_occurrence_choices_when_sorted(self):
        before = self.store.to_payload()
        dialog = CsvV2AnalysisDialog(self.plan)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.raid_table.rowCount(), 2)
        dialog.raid_table.selectRow(0)
        selected_raid = dialog.raid_table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        dialog.raid_table.horizontalHeader().sectionClicked.emit(0)
        dialog.raid_table.horizontalHeader().sectionClicked.emit(0)
        self.assertEqual(dialog.raid_table.item(
            dialog.raid_table.currentRow(), 0,
        ).data(Qt.ItemDataRole.UserRole), selected_raid)
        expected_names = set(next(item.participant_names for item in self.plan.raid_candidates
                                  if str(item.source_path) == selected_raid))
        self.assertEqual({dialog.participant_table.item(row, 0).text()
                          for row in range(dialog.participant_table.rowCount())},
                         expected_names)
        self.assertEqual(dialog.conflict_table.rowCount(), 2)
        self.assertEqual(dialog.new_table.rowCount(), 1)
        self.assertTrue(dialog.bulk_active_button.isEnabled())
        first_combo = dialog.conflict_table.cellWidget(0, 4)
        dialog.conflict_table.selectRow(0)
        selected_key = dialog.conflict_table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        first_combo.setCurrentIndex(first_combo.findData("m2"))
        self.assertEqual(len(dialog.selections), 1)
        order = [item.source_path for item in dialog._conflict_rows]
        first_combo.setCurrentIndex(first_combo.findData("m3"))
        self.assertEqual([item.source_path for item in dialog._conflict_rows], order)
        dialog.conflict_table.horizontalHeader().sectionClicked.emit(0)
        dialog.conflict_table.horizontalHeader().sectionClicked.emit(0)
        self.assertEqual(len(dialog.selections), 1)
        self.assertIn("m3", dialog.selections.values())
        self.assertEqual(dialog.conflict_table.item(
            dialog.conflict_table.currentRow(), 0,
        ).data(Qt.ItemDataRole.UserRole),
            selected_key)
        other_combo = dialog.conflict_table.cellWidget(
            1 - dialog.conflict_table.currentRow(), 4,
        )
        other_combo.setCurrentIndex(other_combo.findData("m2"))
        self.assertEqual(set(dialog.selections.values()), {"m2", "m3"})
        self.assertFalse(dialog.conflict_table.isSortingEnabled())
        self.assertEqual(self.store.to_payload(), before)

    def test_all_dead_candidates_are_visible_but_cannot_be_selected(self):
        self.store.members[0].deathDate = "2026-03-15"
        self.store.members[1].deathDate = "2026-03-20"
        plan = analyze_csv_raids_for_v2(
            self.store, [item.source_path for item in self.plan.raid_candidates],
        )
        dialog = CsvV2AnalysisDialog(plan)
        self.addCleanup(dialog.close)
        self.assertEqual(len(plan.blocked_member_matches), 2)
        self.assertEqual(dialog.conflict_table.rowCount(), 2)
        self.assertIn("2026-03-15", dialog.conflict_table.item(0, 3).text())
        self.assertFalse(dialog.conflict_table.cellWidget(0, 4).isEnabled())
        self.assertEqual(dialog.selections, {})

    def test_duplicate_defaults_use_only_safe_clm_match_and_allow_manual_many(self):
        first, second = self.plan.raid_candidates
        single_option = CsvExistingRaidOption(
            "v2-raid-1", "2026-07-01", "MC", 18, 8, "clm-raid-1",
        )
        multi_options = (
            CsvExistingRaidOption("v2-raid-2", "2026-09-08", "AQ20", 20, 8,
                                  "clm-raid-2"),
            CsvExistingRaidOption("v2-raid-3", "2026-09-08", "Onyxia", 18, 7,
                                  "clm-raid-3"),
            CsvExistingRaidOption("v2-raid-4", "2026-09-08", "Zul'Gurub", 19, 9,
                                  "clm-raid-4"),
        )
        single = replace(
            first, status="POSSIBLE_DUPLICATE",
            existing_raid_options=(single_option,),
            automatic_clm_raid_ids=(single_option.raid_id,),
        )
        multi = replace(
            second, status="POSSIBLE_DUPLICATE",
            existing_raid_options=multi_options,
            automatic_clm_raid_ids=(),
        )
        plan = replace(self.plan, raid_candidates=(single, multi),
                       possible_duplicates=(single, multi))
        dialog = CsvV2AnalysisDialog(plan)
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.raid_decisions[single.source_path].existing_raid_ids,
                         ("v2-raid-1",))
        self.assertNotIn(multi.source_path, dialog.raid_decisions)
        multi_choices = dialog.duplicate_table.cellWidget(1, 3)
        self.assertEqual(multi_choices.count(), 4)
        self.assertEqual([multi_choices.item(index).checkState()
                          for index in range(1, 4)],
                         [Qt.CheckState.Unchecked] * 3)
        self.assertEqual(multi_choices.item(0).checkState(), Qt.CheckState.Unchecked)

        multi_choices.item(1).setCheckState(Qt.CheckState.Checked)
        multi_choices.item(3).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(dialog.raid_decisions[multi.source_path].existing_raid_ids,
                         ("v2-raid-2", "v2-raid-4"))
        dialog.duplicate_table.horizontalHeader().sectionClicked.emit(0)
        dialog.duplicate_table.horizontalHeader().sectionClicked.emit(0)
        sorted_multi_row = next(
            index for index in range(dialog.duplicate_table.rowCount())
            if dialog.duplicate_table.item(index, 0).data(Qt.ItemDataRole.UserRole)
            == str(multi.source_path)
        )
        sorted_choices = dialog.duplicate_table.cellWidget(sorted_multi_row, 3)
        self.assertEqual(dialog.raid_decisions[multi.source_path].existing_raid_ids,
                         ("v2-raid-2", "v2-raid-4"))
        self.assertEqual(sorted_choices.item(2).checkState(), Qt.CheckState.Unchecked)

    def test_duplicate_without_safe_target_requires_explicit_choice(self):
        candidate = replace(
            self.plan.raid_candidates[0], status="POSSIBLE_DUPLICATE",
            existing_raid_options=(CsvExistingRaidOption(
                "legacy-raid", "2026-07-01", "MC", 18, 8, None,
            ),),
            automatic_clm_raid_ids=(),
        )
        plan = replace(self.plan, raid_candidates=(candidate,),
                       possible_duplicates=(candidate,))
        dialog = CsvV2AnalysisDialog(plan)
        self.addCleanup(dialog.close)
        self.assertNotIn(candidate.source_path, dialog.raid_decisions)
        choices = dialog.duplicate_table.cellWidget(0, 3)
        self.assertEqual(choices.item(0).checkState(), Qt.CheckState.Unchecked)
        self.assertEqual(choices.count(), 2)
        choices.item(1).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(dialog.raid_decisions[candidate.source_path].action,
                         "MERGE_EXISTING")
        self.assertEqual(dialog.raid_decisions[candidate.source_path].existing_raid_id,
                         "legacy-raid")
        choices.item(0).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(dialog.raid_decisions[candidate.source_path].action,
                         "CREATE_NEW")


if __name__ == "__main__":
    unittest.main()
