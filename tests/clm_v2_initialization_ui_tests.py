"""Focused Qt workflow checks using an offscreen application and explicit choices."""

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QWidget
    from app import clm_v2_initialization_ui as ui
except ImportError:
    QApplication = QWidget = ui = None

from app.clm_identity_v2_decisions import CONTINUE, ClmIdentityDecisionDraft
from app.clm_identity_v2_materialization import finalized_clm_character_groups
from app.identity_v2_import_choices import CharacterImportChoice
from app.identity_v2 import IdentityV2Store, POINT_MODE_ETERNAL
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from tests.clm_v2_initialization_tests import synthetic_lua
from tests.clm_raid_v2_materialization_tests import analysis_for, first_import_store
from app.clm_raid_v2_materialization import materialize_clm_raids_into_identity_v2


@unittest.skipIf(ui is None, "PySide6 ist in dieser Python-Umgebung nicht installiert.")
class ClmV2InitializationUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / "ClassicLootManager.lua"
        self.source.write_text(synthetic_lua(), encoding="utf-8")
        self.parent = QWidget()
        self.addCleanup(self.parent.close)
        chooser = patch.object(
            ui.QInputDialog, "getItem",
            side_effect=lambda _parent, _title, _prompt, labels, *_args: (labels[0], True),
        )
        chooser.start()
        self.addCleanup(chooser.stop)

    @staticmethod
    def decisions(analysis, _parent):
        draft = ClmIdentityDecisionDraft(analysis)
        draft.set_choice("Annî", "1:102", CONTINUE)
        return draft.to_decision_set()

    @staticmethod
    def classifications(analysis, decisions, _parent):
        return {chain: CharacterImportChoice() for _name, chain
                in finalized_clm_character_groups(analysis, decisions)}

    def test_cancel_before_decisions_changes_no_file(self):
        with (patch.object(ui.QFileDialog, "getOpenFileName", return_value=(str(self.source), "")),
              patch.object(ui, "collect_clm_identity_decisions", return_value=None),
              patch.object(ui, "ClmRaidReviewDialog") as review):
            self.assertIsNone(ui.run_clm_v2_initialization(self.parent))
        review.assert_not_called()
        self.assertEqual(list(self.root.glob("*.ggc")), [])

    def test_raid_type_editor_has_room_for_scaled_font_and_arrow(self):
        inspection = ui.inspect_clm_v2_source(self.source)
        analysis = ui.analyze_clm_v2_selection(
            inspection, "exp0 alliance stitches bierstube", "10")
        dialog = ui.ClmRaidReviewDialog(IdentityV2Store(), analysis, self.parent)
        self.addCleanup(dialog.close)
        for row_index, row in enumerate(dialog.rows):
            combo = dialog.combos[row.clm_raid_id]
            self.assertGreaterEqual(
                combo.minimumHeight(), combo.fontMetrics().height() + 16)
            self.assertGreaterEqual(dialog.table.rowHeight(row_index),
                                    combo.minimumHeight())

    def test_correction_stays_in_review_and_commits_only_after_acceptance(self):
        analysis = analysis_for(
            (((1, 101), "Main", 5, 1, None),),
            ((3, "MC", ((1, 101),), (), ()),))
        original = materialize_clm_raids_into_identity_v2(
            first_import_store(analysis), analysis,
            {analysis.raids[0].raid_id: "MC"})
        changed = replace(analysis, raids=(
            replace(analysis.raids[0], participants=()),))
        before = original.to_payload()
        dialog = ui.ClmRaidReviewDialog(original, changed, self.parent)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.rows[0].status, "Teilnehmer abweichend")
        with patch.object(ui.QMessageBox, "question",
                          return_value=ui.QMessageBox.StandardButton.No):
            dialog._open_existing_correction()
        self.assertEqual(dialog.working_store.to_payload(), before)
        with patch.object(ui.QMessageBox, "question",
                          return_value=ui.QMessageBox.StandardButton.Yes):
            dialog._open_existing_correction()
        self.assertEqual(dialog.rows[0].status, "bereits importiert")
        self.assertEqual(dialog.working_store.attendance, [])
        self.assertEqual(original.to_payload(), before)
        dialog._accept_if_complete()
        self.assertEqual(dialog.result(), ui.QDialog.DialogCode.Accepted)

    def test_missing_stored_type_shows_selected_suggestion_after_correction(self):
        analysis = analysis_for(
            (((1, 101), "Main", 5, 1, None),),
            ((3, "MC", ((1, 101),), (), ()),))
        original = materialize_clm_raids_into_identity_v2(
            first_import_store(analysis), analysis,
            {analysis.raids[0].raid_id: "MC"})
        original.raids[0].raidType = ""
        changed = replace(analysis, raids=(
            replace(analysis.raids[0], participants=()),))
        dialog = ui.ClmRaidReviewDialog(original, changed, self.parent)
        self.addCleanup(dialog.close)
        with patch.object(ui.QMessageBox, "question",
                          return_value=ui.QMessageBox.StandardButton.Yes):
            dialog._open_existing_correction()
        self.assertEqual(dialog.table.item(0, 4).text(), "Typ vorgeschlagen")
        self.assertEqual(dialog.combos[changed.raids[0].raid_id].currentData(), "MC")
        dialog._accept_if_complete()
        self.assertEqual(dialog.result(), ui.QDialog.DialogCode.Accepted)

    def test_import_jumps_to_first_truly_missing_type_without_id_list(self):
        analysis = analysis_for(
            (((1, 101), "Main", 5, 1, None),),
            ((3, "MC", ((1, 101),), (), ()),))
        store = materialize_clm_raids_into_identity_v2(
            first_import_store(analysis), analysis,
            {analysis.raids[0].raid_id: "MC"})
        store.raids[0].raidType = ""
        blank = replace(analysis.raids[0], raid_id="open-raid", name="")
        review_analysis = replace(analysis, raids=(*analysis.raids, blank))
        dialog = ui.ClmRaidReviewDialog(store, review_analysis, self.parent)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.table.item(0, 4).text(), "Typ vorgeschlagen")
        self.assertEqual(dialog.table.item(1, 4).text(), "Typ fehlt")
        dialog._accept_if_complete()
        self.assertEqual(dialog.result(), ui.QDialog.DialogCode.Rejected)
        self.assertEqual(dialog.table.currentRow(), 1)
        self.assertIn("Noch 1 Raid-Typ offen", dialog.message.text())
        self.assertNotIn("open-raid", dialog.message.text())
        dialog.combos["open-raid"].setCurrentIndex(
            dialog.combos["open-raid"].findData("ZG"))
        self.assertEqual(dialog.table.item(1, 4).text(), "Typ gewählt")
        dialog._accept_if_complete()
        self.assertEqual(dialog.result(), ui.QDialog.DialogCode.Accepted)

    def test_unchecked_test_raid_needs_no_type_or_correction(self):
        analysis = analysis_for(
            (((1, 101), "Main", 5, 1, None),),
            ((3, "Testeintrag", ((1, 101),), (), ()),))
        dialog = ui.ClmRaidReviewDialog(
            IdentityV2Store(), analysis, self.parent)
        self.addCleanup(dialog.close)
        raid_id = analysis.raids[0].raid_id
        self.assertEqual(dialog.selected_raid_ids(), {raid_id})
        dialog.import_items[raid_id].setCheckState(ui.Qt.CheckState.Unchecked)
        self.assertEqual(dialog.table.item(0, 4).text(), "Übersprungen")
        self.assertEqual(dialog.selected_raid_ids(), set())
        self.assertEqual(dialog.selected_types(), {})
        dialog._accept_if_complete()
        self.assertEqual(dialog.result(), ui.QDialog.DialogCode.Accepted)

    def test_preselection_can_skip_unknown_guid_raid(self):
        analysis = analysis_for(
            (((1, 101), "Main", 5, 1, None),),
            ((3, "Testeintrag", ((1, 101),), (), ()),))
        dialog = ui.ClmRaidReviewDialog(
            IdentityV2Store(), analysis, self.parent, selection_only=True)
        self.addCleanup(dialog.close)
        raid_id = analysis.raids[0].raid_id
        dialog.import_items[raid_id].setCheckState(ui.Qt.CheckState.Unchecked)
        dialog._accept_if_complete()
        self.assertEqual(dialog.result(), ui.QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.selected_raid_ids(), set())

    def test_new_and_imported_tabs_keep_each_raid_choice(self):
        analysis = analysis_for(
            (((1, 101), "Main", 5, 1, None),),
            ((3, "MC", ((1, 101),), (), ()),
             (4, "Testeintrag", ((1, 101),), (), ())))
        imported_id, new_id = (raid.raid_id for raid in analysis.raids)
        store = materialize_clm_raids_into_identity_v2(
            first_import_store(analysis), analysis, {imported_id: "MC"},
            selected_raid_ids={imported_id})
        dialog = ui.ClmRaidReviewDialog(store, analysis, self.parent)
        self.addCleanup(dialog.close)
        self.assertEqual([dialog.tabs.tabText(index) for index in range(2)],
                         ["Neu", "Bereits Importiert"])
        self.assertTrue(dialog.table.isRowHidden(0))
        self.assertFalse(dialog.table.isRowHidden(1))
        dialog.import_items[new_id].setCheckState(ui.Qt.CheckState.Unchecked)
        dialog.tabs.setCurrentIndex(1)
        self.assertFalse(dialog.table.isRowHidden(0))
        self.assertTrue(dialog.table.isRowHidden(1))
        self.assertEqual(dialog.selected_raid_ids(), {imported_id})
        self.assertEqual(dialog.table.item(1, 4).text(), "Übersprungen")

    def test_missing_imported_type_switches_to_imported_tab(self):
        analysis = analysis_for(
            (((1, 101), "Main", 5, 1, None),),
            ((3, "MC", ((1, 101),), (), ()),))
        store = materialize_clm_raids_into_identity_v2(
            first_import_store(analysis), analysis,
            {analysis.raids[0].raid_id: "MC"})
        store.raids[0].raidType = ""
        unknown_title = replace(analysis.raids[0], name="")
        changed = replace(analysis, raids=(unknown_title,))
        dialog = ui.ClmRaidReviewDialog(store, changed, self.parent)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.tabs.currentIndex(), 0)
        dialog._accept_if_complete()
        self.assertEqual(dialog.tabs.currentIndex(), 1)
        self.assertFalse(dialog.table.isRowHidden(0))
        self.assertEqual(dialog.table.currentRow(), 0)

    def test_raid_cancel_keeps_committed_characters(self):
        committed = []
        with (patch.object(ui.QFileDialog, "getOpenFileName", return_value=(str(self.source), "")),
              patch.object(ui, "collect_clm_identity_decisions", side_effect=self.decisions),
              patch.object(ui, "collect_clm_character_classifications",
                           side_effect=self.classifications),
              patch.object(ui.ClmRaidReviewDialog, "exec",
                           return_value=ui.QDialog.DialogCode.Rejected)):
            self.assertIsNone(ui.run_clm_v2_initialization(
                self.parent, on_characters_imported=committed.append))
        self.assertEqual((len(committed[0].members), len(committed[0].raids),
                          len(committed[0].attendance)), (2, 0, 0))
        self.assertEqual(list(self.root.glob("*.ggc")), [])

    def test_cancel_at_final_group_classification_creates_no_file(self):
        with (patch.object(ui.QFileDialog, "getOpenFileName",
                           return_value=(str(self.source), "")),
              patch.object(ui, "collect_clm_identity_decisions",
                           side_effect=self.decisions),
              patch.object(ui, "collect_clm_character_classifications",
                           return_value=None),
              patch.object(ui, "ClmRaidReviewDialog") as review):
            self.assertIsNone(ui.run_clm_v2_initialization(self.parent))
        review.assert_not_called()
        self.assertEqual(list(self.root.glob("*.ggc")), [])

    def test_full_qt_workflow_imports_in_memory_and_can_resume(self):
        source_before = self.source.read_bytes()
        committed = []
        with (patch.object(ui.QFileDialog, "getOpenFileName", return_value=(str(self.source), "")),
              patch.object(ui, "collect_clm_identity_decisions", side_effect=self.decisions),
              patch.object(ui, "collect_clm_character_classifications",
                           side_effect=self.classifications),
              patch.object(ui.ClmRaidReviewDialog, "exec",
                           return_value=ui.QDialog.DialogCode.Accepted)):
            store = ui.run_clm_v2_initialization(
                self.parent, on_characters_imported=committed.append)
        self.assertEqual((len(committed[0].members), len(committed[0].raids)), (2, 0))
        self.assertEqual((len(store.members), len(store.raids), len(store.attendance)), (2, 1, 2))
        self.assertEqual(store.raids[0].raidType, "MC")
        self.assertEqual((committed[0].clmLuaPath, committed[0].clmDatabaseId,
                          committed[0].clmRosterId, committed[0].clmRosterName),
                         (str(self.source.resolve()),
                          "exp0 alliance stitches bierstube", "10", "Bierstube"))
        target = self.root / "character_only.ggc"
        save_new_identity_v2(committed[0], target)
        with (patch.object(ui.QFileDialog, "getOpenFileName", return_value=(str(self.source), "")),
              patch.object(ui.ClmRaidReviewDialog, "exec",
                           return_value=ui.QDialog.DialogCode.Accepted)):
            resumed = ui.run_clm_v2_initialization(self.parent, target_store=load_identity_v2(target))
        self.assertEqual((len(resumed.members), len(resumed.raids), len(resumed.attendance)),
                         (2, 1, 2))
        self.assertEqual(resumed.clmLuaPath, str(self.source.resolve()))
        self.assertEqual(self.source.read_bytes(), source_before)

    def test_new_project_uses_saved_guild_and_realm_without_source_or_roster_prompt(self):
        initial = IdentityV2Store(
            guildName="Bierstube", realm="Stitches", pointMode=POINT_MODE_ETERNAL)
        before = initial.to_payload()
        with (patch.object(ui.QFileDialog, "getOpenFileName",
                           side_effect=AssertionError("Lua wurde bereits ausgewählt")),
              patch.object(ui.QInputDialog, "getItem",
                           side_effect=AssertionError("Eindeutiger Roster braucht keine Abfrage")),
              patch.object(ui, "collect_clm_identity_decisions", side_effect=self.decisions),
              patch.object(ui, "collect_clm_character_classifications",
                           side_effect=self.classifications),
              patch.object(ui.ClmRaidReviewDialog, "exec",
                           return_value=ui.QDialog.DialogCode.Accepted)):
            imported = ui.run_clm_v2_initialization(
                self.parent, initial_store=initial, source_path=self.source)
        self.assertIsNotNone(imported)
        self.assertEqual((imported.guildName, imported.realm, imported.pointMode,
                          imported.clmRosterName),
                         ("Bierstube", "Stitches", POINT_MODE_ETERNAL, "Bierstube"))
        self.assertEqual((len(imported.members), len(imported.raids),
                          len(imported.attendance)), (2, 1, 2))
        self.assertEqual(initial.to_payload(), before)

    def test_multiple_rosters_use_exact_project_name_or_existing_choice(self):
        source = self.root / "two_rosters.lua"
        source.write_text('''CLM2_DB = {
          ["exp0 alliance stitches bierstube"] = { ledger = {
            { _a=1, _b=0, _c=1735732800, _d="R0", _e=1,
              r=10, n="Bierstube", p=0 },
            { _a=2, _b=0, _c=1735732801, _d="R0", _e=1,
              r=11, n="Nebenliste", p=0 },
          } },
        }''', encoding="utf-8")
        inspection = ui.inspect_clm_v2_source(source)
        database_id = ui._project_database_choice(
            self.parent, inspection, IdentityV2Store(
                guildName="Bierstube", realm="Stitches", pointMode=POINT_MODE_ETERNAL))
        with patch.object(ui.QInputDialog, "getItem",
                          side_effect=AssertionError("Exakter Rostername ist eindeutig")):
            self.assertEqual(ui._roster_choice(
                self.parent, inspection, database_id, "Bierstube"), "10")
        with patch.object(ui.QInputDialog, "getItem",
                          return_value=("Nebenliste · 11", True)) as choice:
            self.assertEqual(ui._roster_choice(
                self.parent, inspection, database_id, "Unbekannt"), "11")
        choice.assert_called_once()

    def test_ambiguous_matching_databases_use_only_matching_existing_choices(self):
        inspection = ui.inspect_clm_v2_source(self.source)
        bierstube = next(item for item in inspection.databases
                         if item.guild_name.casefold() == "bierstube")
        duplicate = replace(bierstube, database_id="zweite passende Datenbank")
        ambiguous = replace(inspection, databases=(
            *inspection.databases, duplicate))
        store = IdentityV2Store(guildName="Bierstube", realm="Stitches",
                                pointMode=POINT_MODE_ETERNAL)

        def choose(_parent, _title, _prompt, labels, *_args):
            self.assertEqual(len(labels), 2)
            self.assertTrue(all("bierstube" in label.casefold() for label in labels))
            return labels[-1], True

        with patch.object(ui.QInputDialog, "getItem", side_effect=choose) as prompt:
            self.assertEqual(ui._project_database_choice(
                self.parent, ambiguous, store), duplicate.database_id)
        prompt.assert_called_once()

        wrong = IdentityV2Store(guildName="Fremde Gilde", realm="Stitches",
                                pointMode=POINT_MODE_ETERNAL)
        with patch.object(ui.QInputDialog, "getItem",
                          side_effect=AssertionError("Fremde Gilde darf nicht gewählt werden")):
            with self.assertRaises(ui.ClmIntegrationError):
                ui._project_database_choice(self.parent, inspection, wrong)


if __name__ == "__main__":
    unittest.main()
