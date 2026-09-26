"""Offscreen review decisions and atomic apply in the active V2 checker."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.csv_v2_analysis_ui import CsvV2AnalysisDialog, temporal_indicator_text
    from app import GuildGearCheckerQt as checker_qt
except ImportError:
    Qt = QApplication = QMessageBox = CsvV2AnalysisDialog = checker_qt = None

from app.csv_v2_analysis import analyze_csv_raids_for_v2, temporal_match_indicator
from app.csv_import import exact_name_key
from app.identity_v2 import Attendance, IdentityV2Store, Member, Player, Raid
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from app.raid_attendance import RAID_TYPES


@unittest.skipIf(QApplication is None, "PySide6 ist lokal nicht verfügbar.")
class CsvV2MaterializationQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_duplicate_and_class_choices_survive_explicit_sort(self):
        store = IdentityV2Store(
            members=[Member("m1000", "Annî", "Priest", clmGuid="1:1")],
            raids=[Raid("r1", "2026-07-01", name="MC", clmRaidId="clm1"),
                   Raid("r2", "2026-07-01", name="MC", clmRaidId="clm2")],
            attendance=[Attendance("a1", "r1", "m1000", "main", clmGuid="1:1")],
        )
        source = self.root / "2026-07-01_MC_Casts.csv"
        source.write_text('"Name","Amount"\n"Annî","1"\n"Neu","1"\n',
                          encoding="utf-8")
        plan = analyze_csv_raids_for_v2(store, [source])
        dialog = CsvV2AnalysisDialog(plan, store=store)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.duplicate_table.rowCount(), 1)
        header = dialog.duplicate_table.horizontalHeader()
        self.assertGreaterEqual(dialog.duplicate_table.columnWidth(3), 280)
        self.assertGreaterEqual(dialog.duplicate_table.columnWidth(4), 300)
        self.assertEqual(header.sectionResizeMode(4),
                         checker_qt.QHeaderView.ResizeMode.Stretch)
        self.assertEqual(dialog.duplicate_table.horizontalScrollBarPolicy(),
                         checker_qt.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.assertGreaterEqual(dialog.duplicate_table.verticalHeader()
                                .defaultSectionSize(), 36)
        for table in (dialog.raid_table, dialog.duplicate_table,
                      dialog.conflict_table, dialog.new_table):
            self.assertEqual(table.horizontalScrollBarPolicy(),
                             checker_qt.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.assertGreaterEqual(table.verticalHeader().defaultSectionSize(), 36)
            self.assertFalse(table.isSortingEnabled())
        self.assertGreaterEqual(dialog.conflict_table.columnWidth(3), 430)
        self.assertGreaterEqual(dialog.conflict_table.columnWidth(4), 250)
        self.assertGreaterEqual(dialog.new_table.columnWidth(4), 300)
        decision_list = dialog.duplicate_table.cellWidget(0, 3)
        self.assertGreaterEqual(decision_list.minimumWidth(), 270)
        self.assertGreaterEqual(dialog.duplicate_table.rowHeight(0), 74)
        self.assertIn("01.07.2026", decision_list.item(1).text())
        self.assertIn("MC", decision_list.item(1).text())
        self.assertIn("Teilnehmer", decision_list.item(1).text())
        self.assertNotIn("r1", decision_list.item(1).text())
        self.assertIn("raidId=r1", decision_list.item(1).toolTip())
        self.assertEqual(decision_list.item(0).checkState(), Qt.CheckState.Unchecked)
        self.assertEqual({decision_list.item(index).checkState() for index in (1, 2)},
                         {Qt.CheckState.Unchecked})
        decision_list.item(1).setCheckState(Qt.CheckState.Checked)
        decision_list.item(2).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(set(dialog.raid_decisions[source].existing_raid_ids),
                         {"r1", "r2"})
        decision_list.item(1).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(dialog.raid_decisions[source].existing_raid_ids, ("r2",))
        decision_list.item(1).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(set(dialog.raid_decisions[source].existing_raid_ids),
                         {"r1", "r2"})
        dialog.duplicate_table.horizontalHeader().sectionClicked.emit(0)
        self.assertEqual(set(dialog.raid_decisions[source].existing_raid_ids),
                         {"r1", "r2"})
        dialog.raid_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        self.assertFalse(dialog.apply_button.isEnabled())
        dialog.raid_table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(set(dialog.raid_decisions[source].existing_raid_ids),
                         {"r1", "r2"})
        decision_list = dialog.duplicate_table.cellWidget(0, 3)
        decision_list.item(0).setCheckState(Qt.CheckState.Checked)
        dialog.duplicate_table.horizontalHeader().sectionClicked.emit(0)
        self.assertEqual(dialog.raid_decisions[source].action, "CREATE_NEW")
        self.assertFalse(dialog.duplicate_table.isSortingEnabled())
        class_combo = dialog.new_table.cellWidget(0, 2)
        self.assertIsNone(class_combo.currentData())
        class_combo.setCurrentIndex(class_combo.findData("Mage"))
        dialog.new_table.horizontalHeader().sectionClicked.emit(0)
        self.assertEqual(dialog.new_member_classes["neu"], "Mage")
        classification = dialog.new_table.cellWidget(0, 3)
        classification.setCurrentIndex(classification.findData("ACTIVE_UNKNOWN"))
        with (patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.Yes),
              patch.object(QMessageBox, "warning",
                           side_effect=AssertionError("Unexpected review warning"))):
            dialog._apply_clicked()
        self.assertIsNotNone(dialog.result_store)
        self.assertEqual(dialog.result_summary.new_members, 1)
        self.assertEqual(len(store.members), 1)

    def test_player_choices_only_exist_when_store_has_players(self):
        source = self.root / "2026-07-01_BWL_Casts.csv"
        source.write_text('"Name","Amount"\n"Neuling","1"\n', encoding="utf-8")
        empty_players = IdentityV2Store()
        plan = analyze_csv_raids_for_v2(empty_players, [source])
        without = CsvV2AnalysisDialog(plan, store=empty_players)
        self.addCleanup(without.close)
        combo = without.new_table.cellWidget(0, 3)
        self.assertEqual(combo.findData("ACTIVE_PLAYER:p1"), -1)
        with_player = IdentityV2Store(players=[Player("p1", "Spieler")])
        plan_with_player = analyze_csv_raids_for_v2(with_player, [source])
        dialog = CsvV2AnalysisDialog(plan_with_player, store=with_player)
        self.addCleanup(dialog.close)
        combo = dialog.new_table.cellWidget(0, 3)
        self.assertGreaterEqual(combo.findData("ACTIVE_PLAYER:p1"), 0)
        self.assertGreaterEqual(combo.findData("INACTIVE_PLAYER:p1"), 0)

    def test_bulk_inactive_and_selected_ignore_keep_unknown_class(self):
        source = self.root / "2026-07-01_BWL_Casts.csv"
        source.write_text(
            '"Name","Amount"\n"Portal","1"\n"Anderer","1"\n',
            encoding="utf-8",
        )
        store = IdentityV2Store()
        plan = analyze_csv_raids_for_v2(store, [source])
        dialog = CsvV2AnalysisDialog(plan, store=store)
        self.addCleanup(dialog.close)
        first_name = dialog.new_table.item(0, 0).text()
        dialog.new_table.selectRow(0)
        dialog.selected_irrelevant_button.click()
        dialog.bulk_inactive_button.click()
        self.assertEqual(dialog.new_member_choices[
            exact_name_key(first_name)].relevance, "irrelevant")
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            dialog._apply_clicked()
        self.assertIsNotNone(dialog.result_store)
        self.assertEqual(dialog.result_summary.ignored_members, 1)
        self.assertEqual(len(dialog.result_store.members), 1)
        self.assertEqual(dialog.result_store.members[0].lifeStatus, "inactive")
        self.assertIsNone(dialog.result_store.members[0].className)
        self.assertTrue(dialog.result_store.is_csv_character_ignored(first_name))

    def test_temporal_text_names_direction_without_auto_choice(self):
        before = temporal_match_indicator("2026-04-15", "2027-04-20", "2027-05-01")
        after = temporal_match_indicator("2026-04-15", "2026-02-01", "2026-03-30")
        self.assertIn("370", temporal_indicator_text(before))
        self.assertIn("vor", temporal_indicator_text(before).casefold())
        self.assertIn("16", temporal_indicator_text(after))
        self.assertIn("nach", temporal_indicator_text(after).casefold())
        self.assertNotEqual(temporal_indicator_text(before), "-370")

    def test_each_same_name_candidate_shows_distance_and_stays_selectable(self):
        store = IdentityV2Store(
            members=[
                Member("m1000", "Annî", "Priest", clmGuid="1:1"),
                Member("m1001", "Annî", "Mage", clmGuid="1:2"),
            ],
            raids=[
                Raid("r_old", "2026-03-30", name="MC"),
                Raid("r_new", "2027-04-20", name="MC"),
            ],
            attendance=[
                Attendance("a_old", "r_old", "m1000", "unknown", clmGuid="1:1"),
                Attendance("a_new", "r_new", "m1001", "unknown", clmGuid="1:2"),
            ],
        )
        source = self.root / "2026-04-15_MC_Casts.csv"
        source.write_text('"Name","Amount"\n"Annî","1"\n', encoding="utf-8")
        plan = analyze_csv_raids_for_v2(store, [source])
        dialog = CsvV2AnalysisDialog(plan, store=store)
        self.addCleanup(dialog.close)
        details = dialog.conflict_table.item(0, 3).text().casefold()
        self.assertIn("16 tage nach", details)
        self.assertIn("370 tage vor", details)
        combo = dialog.conflict_table.cellWidget(0, 4)
        self.assertIsNone(combo.currentData())
        self.assertGreaterEqual(combo.findData("m1000"), 0)
        self.assertGreaterEqual(combo.findData("m1001"), 0)

    def test_raid_overview_toggle_and_participant_detail_exclude_one_file(self):
        store = IdentityV2Store(members=[Member("m1000", "Annî", "Priest")])
        first = self.root / "2026-07-01_BWL_Casts.csv"
        second = self.root / "2026-07-02_AQ20_Casts.csv"
        first.write_text('"Name","Amount"\n"Annî","1"\n', encoding="utf-8")
        second.write_text('"Name","Amount"\n"NurHier","1"\n', encoding="utf-8")
        plan = analyze_csv_raids_for_v2(store, [first, second])
        dialog = CsvV2AnalysisDialog(plan, store=store)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.raid_table.rowCount(), 2)
        self.assertEqual([dialog.raid_table.item(row, 0).checkState()
                          for row in range(2)], [Qt.CheckState.Checked] * 2)
        self.assertEqual({dialog.raid_table.cellWidget(0, 2).itemText(index)
                          for index in range(dialog.raid_table.cellWidget(0, 2).count())},
                         set(RAID_TYPES))
        dialog.raid_table.selectRow(1)
        self.assertEqual(dialog.participant_table.rowCount(), 1)
        self.assertEqual(dialog.participant_table.item(0, 0).text(), "NurHier")
        self.assertIn("Neu", dialog.participant_table.item(0, 3).text())
        dialog.raid_table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(dialog.new_table.rowCount(), 0)
        self.assertIn("2/1", dialog.summary_label.text())
        self.assertIn("Abgewählt", dialog.raid_table.item(1, 5).text())
        self.assertEqual(dialog.participant_table.item(0, 0).text(), "NurHier")
        with (patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.Yes),
              patch.object(QMessageBox, "warning",
                           side_effect=AssertionError("Unexpected import warning"))):
            dialog._apply_clicked()
        self.assertEqual(dialog.result_summary.new_raids, 1)
        self.assertEqual(len(dialog.result_store.raids), 1)
        self.assertFalse(any(item.name == "NurHier"
                             for item in dialog.result_store.members))
        self.assertFalse(any(second.name in raid.csvSourceFiles
                             for raid in dialog.result_store.raids))

    def test_all_raids_excluded_cannot_apply(self):
        store = IdentityV2Store(members=[Member("m1000", "Annî", "Priest")])
        source = self.root / "2026-07-01_BWL_Casts.csv"
        source.write_text('"Name","Amount"\n"Annî","1"\n', encoding="utf-8")
        dialog = CsvV2AnalysisDialog(analyze_csv_raids_for_v2(store, [source]),
                                     store=store)
        self.addCleanup(dialog.close)
        before = store.to_payload()
        dialog.raid_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
        self.assertFalse(dialog.apply_button.isEnabled())
        dialog._apply_clicked()
        self.assertIsNone(dialog.result_store)
        self.assertEqual(store.to_payload(), before)

    def test_type_override_rebuilds_clm_review_and_persists_csv_type(self):
        store = IdentityV2Store(
            members=[Member("m1000", "Annî", "Priest", clmGuid="1:1")],
            raids=[Raid("r_clm", "2026-07-01", name="MC", clmRaidId="clm1")],
            attendance=[Attendance("a1", "r_clm", "m1000", "unknown",
                                   clmGuid="1:1")],
        )
        source = self.root / "2026-07-01_MC_Casts.csv"
        source.write_text('"Name","Amount"\n"Annî","1"\n', encoding="utf-8")
        plan = analyze_csv_raids_for_v2(store, [source])
        self.assertEqual(plan.raid_candidates[0].status, "KNOWN_RAID")
        dialog = CsvV2AnalysisDialog(plan, store=store)
        self.addCleanup(dialog.close)
        combo = dialog.raid_table.cellWidget(0, 2)
        combo.setCurrentIndex(combo.findData("BWL"))
        self.assertEqual(dialog.raid_type_overrides[source], "BWL")
        self.assertEqual(dialog.plan.raid_candidates[0].status,
                         "POSSIBLE_DUPLICATE")
        self.assertEqual(dialog.duplicate_table.rowCount(), 1)
        self.assertNotIn(source, dialog.raid_decisions)
        self.assertFalse(dialog.apply_button.isEnabled())
        dialog.duplicate_table.cellWidget(0, 3).item(0).setCheckState(
            Qt.CheckState.Checked)
        self.assertEqual(dialog.raid_decisions[source].action, "CREATE_NEW")
        self.assertTrue(dialog.apply_button.isEnabled())
        with (patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.Yes),
              patch.object(QMessageBox, "warning",
                           side_effect=AssertionError("Unexpected import warning"))):
            dialog._apply_clicked()
        self.assertEqual(dialog.result_summary.new_raids, 1)
        self.assertEqual(store.raids[0].csvSourceFiles, ())
        self.assertEqual(next(item.raidType for item in dialog.result_store.raids
                              if not item.clmRaidId), "BWL")

    def test_type_change_clears_previous_manual_clm_target(self):
        store = IdentityV2Store(
            members=[Member("m1000", "Annî", "Priest", clmGuid="1:1")],
            raids=[Raid("r1", "2026-07-01", name="MC", clmRaidId="clm1"),
                   Raid("r2", "2026-07-01", name="MC", clmRaidId="clm2")],
            attendance=[Attendance("a1", "r1", "m1000", "unknown",
                                   clmGuid="1:1")],
        )
        source = self.root / "2026-07-01_MC_Casts.csv"
        source.write_text('"Name","Amount"\n"Annî","1"\n', encoding="utf-8")
        dialog = CsvV2AnalysisDialog(analyze_csv_raids_for_v2(store, [source]),
                                     store=store)
        self.addCleanup(dialog.close)
        choices = dialog.duplicate_table.cellWidget(0, 3)
        choices.item(1).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(dialog.raid_decisions[source].action, "LINK_CLM_RAIDS")
        combo = dialog.raid_table.cellWidget(0, 2)
        combo.setCurrentIndex(combo.findData("BWL"))
        self.assertNotIn(source, dialog.raid_decisions)
        self.assertFalse(dialog.apply_button.isEnabled())

    def test_same_day_clm_options_are_unchecked_but_strong_match_keeps_csv_names(self):
        store = IdentityV2Store(
            members=[Member("m1000", "Annî", "Priest", clmGuid="1:1")],
            raids=[Raid("r_clm", "2026-07-01", name="MC", clmRaidId="clm1")],
        )
        source = self.root / "2026-07-01_MC_Casts.csv"
        source.write_text('"Name","Amount"\n"NurCSV","1"\n', encoding="utf-8")
        plan = analyze_csv_raids_for_v2(store, [source])
        self.assertEqual(plan.raid_candidates[0].status, "POSSIBLE_DUPLICATE")
        dialog = CsvV2AnalysisDialog(plan, store=store)
        self.addCleanup(dialog.close)
        choices = dialog.duplicate_table.cellWidget(0, 3)
        self.assertEqual(choices.item(0).checkState(), Qt.CheckState.Unchecked)
        self.assertEqual(choices.item(1).checkState(), Qt.CheckState.Unchecked)
        self.assertEqual(dialog.participant_table.item(0, 0).text(), "NurCSV")

        store.attendance.append(Attendance("a1", "r_clm", "m1000", "unknown",
                                           clmGuid="1:1"))
        source.write_text('"Name","Amount"\n"Annî","1"\n"NurCSV","1"\n',
                          encoding="utf-8")
        strong = analyze_csv_raids_for_v2(store, [source])
        self.assertEqual(strong.raid_candidates[0].automatic_clm_raid_ids, ("r_clm",))
        linked = CsvV2AnalysisDialog(strong, store=store)
        self.addCleanup(linked.close)
        self.assertEqual(linked.participant_table.rowCount(), 2)
        self.assertEqual({linked.participant_table.item(row, 0).text()
                          for row in range(2)}, {"Annî", "NurCSV"})
        extra_row = next(row for row in range(2)
                         if linked.participant_table.item(row, 0).text() == "NurCSV")
        self.assertIn("CLM-Attendance", linked.participant_table.item(
            extra_row, 3).text())
        with (patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.Yes),
              patch.object(QMessageBox, "warning",
                           side_effect=AssertionError("Unexpected import warning"))):
            linked._apply_clicked()
        self.assertEqual(linked.result_summary.new_attendance, 0)
        self.assertEqual(linked.result_summary.new_members, 0)
        self.assertEqual(len(linked.result_store.attendance), 1)

    def test_checker_apply_refreshes_v2_views_and_dirty_without_saving(self):
        store = IdentityV2Store(
            members=[Member("m1000", "Annî", "Priest", clmGuid="1:1",
                            raidStartDate="2026-08-21")],
            raids=[Raid("r1", "2026-08-21", name="MC")],
            attendance=[Attendance("a1", "r1", "m1000", "main", clmGuid="1:1")],
        )
        target = self.root / "Aktiv_V2.ggc"
        save_new_identity_v2(store, target)
        source = self.root / "2026-07-01_BWL_Casts.csv"
        source.write_text('"Name","Amount"\n"Annî","1"\n', encoding="utf-8")
        window = checker_qt.GuildGearCheckerQt()
        self.addCleanup(lambda: self._close_window(window))
        with patch.object(checker_qt.QFileDialog, "getOpenFileName",
                          return_value=(str(target), "")):
            window.open_project()
        original_store = window.identity_v2_store
        original_bytes = target.read_bytes()

        def apply_instead_of_exec(dialog):
            dialog._apply_clicked()
            return dialog.result()

        with (patch.object(checker_qt.QFileDialog, "getOpenFileNames",
                           return_value=([str(source)], "")),
              patch.object(CsvV2AnalysisDialog, "exec",
                           new=apply_instead_of_exec),
              patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.Yes),
              patch.object(QMessageBox, "warning",
                           side_effect=AssertionError("Unexpected import warning")),
              patch.object(QMessageBox, "critical",
                           side_effect=AssertionError("Unexpected import error"))):
            window.analyze_v2_csv_files()
        self.assertIsNot(window.identity_v2_store, original_store)
        self.assertEqual(len(window.identity_v2_store.raids), 2)
        self.assertEqual(window.v2_raid_page.raid_table.rowCount(), 2)
        self.assertTrue(any(
            source.name in window.v2_raid_page.raid_table.item(row, 5).text()
            for row in range(window.v2_raid_page.raid_table.rowCount())
        ))
        self.assertEqual(window.v2_roster_page.table.rowCount(), 1)
        self.assertEqual(window.identity_v2_store.members[0].raidStartDate,
                         "2026-07-01")
        self.assertTrue(window.identity_v2_dirty)
        self.assertEqual(target.read_bytes(), original_bytes)
        self.assertEqual(len(original_store.raids), 1)
        window.save_project()
        self.assertFalse(window.identity_v2_dirty)
        self.assertEqual(load_identity_v2(target).to_payload(),
                         window.identity_v2_store.to_payload())
        saved_bytes = target.read_bytes()
        saved_store = window.identity_v2_store
        with (patch.object(checker_qt.QFileDialog, "getOpenFileNames",
                           return_value=([str(source)], "")),
              patch.object(CsvV2AnalysisDialog, "exec",
                           new=apply_instead_of_exec),
              patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.Yes),
              patch.object(QMessageBox, "warning",
                           side_effect=AssertionError("Unexpected reimport warning"))):
            window.analyze_v2_csv_files()
        self.assertIs(window.identity_v2_store, saved_store)
        self.assertFalse(window.identity_v2_dirty)
        self.assertEqual(target.read_bytes(), saved_bytes)

    def test_checker_cancel_csv_review_keeps_store_and_project_clean(self):
        store = IdentityV2Store(members=[Member("m1000", "Annî", "Priest")])
        target = self.root / "Abbruch_V2.ggc"
        save_new_identity_v2(store, target)
        source = self.root / "2026-07-01_BWL_Casts.csv"
        source.write_text('"Name","Amount"\n"Annî","1"\n', encoding="utf-8")
        window = checker_qt.GuildGearCheckerQt()
        self.addCleanup(lambda: self._close_window(window))
        with patch.object(checker_qt.QFileDialog, "getOpenFileName",
                          return_value=(str(target), "")):
            window.open_project()
        original_store = window.identity_v2_store
        original_bytes = target.read_bytes()
        with (patch.object(checker_qt.QFileDialog, "getOpenFileNames",
                           return_value=([str(source)], "")),
              patch.object(CsvV2AnalysisDialog, "exec", return_value=0)):
            window.analyze_v2_csv_files()
        self.assertIs(window.identity_v2_store, original_store)
        self.assertFalse(window.identity_v2_dirty)
        self.assertEqual(target.read_bytes(), original_bytes)

    @staticmethod
    def _close_window(window):
        with (patch.object(checker_qt, "update_suite_settings"),
              patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.Yes)):
            window.close()


if __name__ == "__main__":
    unittest.main()
