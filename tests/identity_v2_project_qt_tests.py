"""Offscreen Qt checks for opening and saving an active Identity V2 project."""

import json
import os
import tempfile
import unittest
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (QApplication, QDialog, QFormLayout, QLabel,
                                   QPushButton, QStyle, QStyleOptionViewItem)
    from app import GuildGearCheckerQt as checker_qt
except ImportError:
    Qt = QApplication = checker_qt = None

from app.clm_identity_v2_decisions import CONTINUE, ClmIdentityDecisionDraft
from app.identity_v2_import_choices import CharacterImportChoice
from app.clm_v2_initialization import (
    analyze_clm_v2_selection, build_new_clm_v2_guild, inspect_clm_v2_source,
)
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from app.identity_v2 import (Attendance, EternalDkpRecord, IdentityV2Store,
                             MainHistoryEntry, Member, Player, Raid)
from app.project_storage import member_portrait_path, project_paths
from app.identity_v2_dkp import available_dkp_by_member
from app.identity_v2_graveyard import repair_missing_individual_gravestones
from app.identity_v2_player_service import set_main
from app.gravestone_templates import load_gravestone_inventory
from tests.clm_v2_initialization_tests import synthetic_lua
from tests.identity_v2_character_data_qt_tests import sample_store as character_sample_store
from tests.identity_v2_attendance_adapter_tests import sample_store as matrix_sample_store
from tests.identity_v2_raid_points_tests import point_store
from app.identity_v2_character_data_qt import MemberSpecialPointsDialog
from app.identity_v2_raid_points import V2RaidPointProjection
from tests.identity_v2_main_history_tests import sample_store as main_history_sample_store
from app.identity_v2_main_history_qt import MainHistoryDialog


@unittest.skipIf(checker_qt is None, "PySide6 ist in dieser Python-Umgebung nicht installiert.")
class IdentityV2ProjectQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        assets = Path(__file__).resolve().parents[1] / "assets" / "graveyard"
        self.gravestone_templates = load_gravestone_inventory(
            assets, assets / "gravestones_manifest.json").templates
        source = self.root / "ClassicLootManager.lua"
        source.write_text(synthetic_lua(), encoding="utf-8")
        analysis = analyze_clm_v2_selection(
            inspect_clm_v2_source(source), "exp0 alliance stitches bierstube", "10",
        )
        draft = ClmIdentityDecisionDraft(analysis.identity_analysis)
        draft.set_choice("Annî", "1:102", CONTINUE)
        self.store = self._prepared(build_new_clm_v2_guild(
            analysis, draft.to_decision_set(),
            raid_types={raid.raid_id: "MC" for raid in analysis.raids}))
        self.target = self.root / "Neue_Gilde_V2.ggc"
        save_new_identity_v2(self.store, self.target)
        self.window = checker_qt.GuildGearCheckerQt(
            settings_path=self.root / "suite_settings.json")
        self.addCleanup(self._close_window)

    def _prepared(self, store):
        return repair_missing_individual_gravestones(
            store, self.gravestone_templates)

    def _close_window(self):
        with (patch.object(checker_qt, "update_suite_settings"),
              patch.object(checker_qt.QMessageBox, "question",
                           return_value=checker_qt.QMessageBox.StandardButton.Yes)):
            self.window.close()

    def open_path(self, path: Path):
        with (patch.object(checker_qt.QFileDialog, "getOpenFileName",
                           return_value=(str(path), "")),
              patch.object(checker_qt.QMessageBox, "critical") as error):
            self.window.open_project()
        return error

    def test_new_project_creates_and_reopens_empty_v2_without_legacy_save(self):
        target = self.root / "Leer_V2.ggc"
        with (patch.object(checker_qt.QFileDialog, "getSaveFileName",
                           return_value=(str(target), "")),
              patch.object(self.window.model, "save",
                           side_effect=AssertionError("Legacy-Save unzulässig")),
              patch.object(self.window, "autosave",
                           side_effect=AssertionError("Kein Autosave"))):
            self.window.new_project()
        self.assertEqual(self.window.project_mode, "identity_v2")
        self.assertEqual(self.window.identity_v2_project_path, target.resolve())
        self.assertFalse(self.window.identity_v2_dirty)
        empty = load_identity_v2(target)
        self.assertEqual(empty.pointMode, "raid_points")
        self.assertEqual((len(empty.players), len(empty.members), len(empty.raids),
                          len(empty.attendance)), (0, 0, 0, 0))
        self.assertTrue(self.window.v2_raid_page.analyze_csv_button.isEnabled())
        with patch("app.clm_v2_initialization_ui.run_clm_v2_initialization",
                   return_value=None) as initialize:
            self.window.initialize_v2_from_clm()
        initialize.assert_not_called()
        self.assertFalse(self.open_path(target).called)
        self.assertEqual(self.window.identity_v2_store.to_payload(), empty.to_payload())
        from app.csv_v2_analysis_ui import CsvV2AnalysisDialog

        csv_path = self.root / "2026-07-01_MC_Casts.csv"
        csv_path.write_text('"Name","Amount"\n"Neu","1"\n', encoding="utf-8")
        with (patch.object(checker_qt.QFileDialog, "getOpenFileNames",
                           return_value=([str(csv_path)], "")),
              patch.object(CsvV2AnalysisDialog, "exec",
                           return_value=checker_qt.QDialog.DialogCode.Accepted),
              patch.object(checker_qt.QMessageBox, "critical") as error):
            self.window.analyze_v2_csv_files()
        self.assertFalse(error.called)
        self.assertIsNotNone(self.window.csv_v2_import_plan)
        self.assertEqual(load_identity_v2(target).to_payload(), empty.to_payload())
        self.assertTrue(self.window.set_v2_active_point_system("eternal_dkp"))
        self.window.save_project()
        before_import = load_identity_v2(target).to_payload()
        self.assertFalse(self.window.identity_v2_dirty)

        def apply_clm_characters(_parent, *, target_store,
                                 on_characters_imported):
            changed = IdentityV2Store.from_payload(target_store.to_payload())
            changed.members.append(Member("m1000", "Neu", "Mage"))
            changed.validate()
            on_characters_imported(changed)
            return None

        with patch("app.clm_v2_initialization_ui.run_clm_v2_initialization",
                   side_effect=apply_clm_characters):
            self.window.initialize_v2_from_clm()
        self.assertEqual(self.window.identity_v2_project_path, target.resolve())
        self.assertTrue(self.window.identity_v2_dirty)
        self.assertEqual([item.name for item in self.window.identity_v2_store.members],
                         ["Neu"])
        self.assertEqual(load_identity_v2(target).to_payload(), before_import)

    def test_v2_tool_menu_reuses_grabber_and_project_portrait_path(self):
        self.assertFalse(self.open_path(self.target).called)
        self.assertTrue(self.window.grabber_menu_action.isEnabled())
        self.assertTrue(self.window.portrait_folder_menu_action.isEnabled())
        with patch.object(checker_qt.subprocess, "Popen") as launched:
            self.window.grabber_menu_action.trigger()
        launched.assert_called_once()
        command = launched.call_args.args[0]
        self.assertEqual(command[-2:], ["--project", str(self.target.resolve())])
        with patch.object(checker_qt, "safe_open_folder") as opened:
            self.window.portrait_folder_menu_action.trigger()
        opened.assert_called_once_with(project_paths(self.target).portraits)
        self.assertFalse(self.window.identity_v2_dirty)

    def test_v2_export_and_package_actions_use_v2_store_only(self):
        self.assertFalse(self.open_path(self.target).called)
        portrait = member_portrait_path(self.target,
                                        self.window.identity_v2_store.members[0].memberId)
        portrait.parent.mkdir(parents=True, exist_ok=True)
        picture = QPixmap(12, 12)
        picture.fill(Qt.GlobalColor.cyan)
        self.assertTrue(picture.save(str(portrait)))
        before = self.target.read_bytes()
        payload = self.window.identity_v2_store.to_payload()
        plain = self.root / "Export_V2.ggc"
        package = self.root / "Paket_V2.zip"
        restored = self.root / "restored" / "Paket_V2.ggc"
        self.assertTrue(self.window.export_menu_action.isEnabled())
        self.assertTrue(self.window.package_export_menu_action.isEnabled())
        self.assertTrue(self.window.package_import_menu_action.isEnabled())
        with (patch.object(self.window.model, "to_payload",
                           side_effect=AssertionError("Kein Legacy-Modell")),
              patch.object(self.window.model, "save",
                           side_effect=AssertionError("Kein Legacy-Save")),
              patch.object(checker_qt.QMessageBox, "information"),
              patch.object(checker_qt.QMessageBox, "critical") as error):
            with patch.object(checker_qt.QFileDialog, "getSaveFileName",
                              return_value=(str(plain), "")):
                self.window.export_menu_action.trigger()
            with patch.object(checker_qt.QFileDialog, "getSaveFileName",
                              return_value=(str(package), "")):
                self.window.package_export_menu_action.trigger()
            self.assertFalse(error.called, error.call_args)
        self.assertEqual(load_identity_v2(plain).to_payload(), payload)
        self.assertTrue(package.is_file())
        self.assertEqual(self.target.read_bytes(), before)
        with (patch.object(checker_qt.QFileDialog, "getOpenFileName",
                           return_value=(str(package), "")),
              patch.object(checker_qt.QFileDialog, "getSaveFileName",
                           return_value=(str(restored), "")),
              patch.object(checker_qt.QMessageBox, "critical") as error):
            self.window.package_import_menu_action.trigger()
        self.assertFalse(error.called, error.call_args)
        self.assertEqual(self.window.identity_v2_project_path, restored.resolve())
        self.assertEqual(load_identity_v2(restored).to_payload(), payload)
        self.assertEqual(member_portrait_path(restored, payload["members"][0]["memberId"]).read_bytes(),
                         portrait.read_bytes())
        self.assertEqual(self.target.read_bytes(), before)

    def test_v2_package_import_from_startup_opens_v2_project(self):
        from app.identity_v2_package import create_v2_project_package

        package = self.root / "startup-v2.zip"
        create_v2_project_package(self.store, self.target, package)
        target = self.root / "from-package" / "Imported.ggc"
        with (patch.object(checker_qt.QFileDialog, "getOpenFileName",
                           return_value=(str(package), "")),
              patch.object(checker_qt.QFileDialog, "getSaveFileName",
                           return_value=(str(target), "")),
              patch.object(self.window.model, "load",
                           side_effect=AssertionError("Kein Legacy-Import")),
              patch.object(checker_qt.QMessageBox, "critical") as error):
            self.window.package_import_menu_action.trigger()
        self.assertFalse(error.called, error.call_args)
        self.assertEqual(self.window.project_mode, "identity_v2")
        self.assertEqual(self.window.identity_v2_project_path, target.resolve())
        self.assertEqual(load_identity_v2(target).to_payload(), self.store.to_payload())

    def test_v2_package_export_respects_external_project_change(self):
        from app.identity_v2_storage import save_identity_v2

        self.assertFalse(self.open_path(self.target).called)
        changed = load_identity_v2(self.target)
        changed.members[0].note = "Extern"
        save_identity_v2(changed, self.target)
        with (patch.object(checker_qt.QFileDialog, "getSaveFileName",
                           side_effect=AssertionError("Kein Exportdialog")),
              patch.object(checker_qt.QMessageBox, "warning") as warning):
            self.window.package_export_menu_action.trigger()
        warning.assert_called_once()
        self.assertEqual(self.window.identity_v2_store.members[0].note,
                         self.store.members[0].note)

    def test_startup_save_as_routes_to_new_v2_instead_of_legacy(self):
        target = self.root / "SaveAs_V2.ggc"
        with (patch.object(checker_qt.QFileDialog, "getSaveFileName",
                           return_value=(str(target), "")),
              patch.object(self.window.model, "save",
                           side_effect=AssertionError("Legacy-Save unzulässig"))):
            self.window.save_project_as()
        self.assertEqual(self.window.project_mode, "identity_v2")
        self.assertEqual(load_identity_v2(target).pointMode, "raid_points")

    def test_adapter_reference_save_as_still_uses_v2_store(self):
        self.window.model.project_path = self.root / "alte-referenz.ggc"
        target = self.root / "Tatsaechlich_V2.ggc"
        with (patch.object(checker_qt.QFileDialog, "getSaveFileName",
                           return_value=(str(target), "")),
              patch.object(self.window.model, "save",
                           side_effect=AssertionError("Kein Legacy-Save"))):
            self.window.save_project_as()
        self.assertEqual(load_identity_v2(target).pointMode, "raid_points")
        self.assertFalse((self.root / "alte-referenz.ggc").exists())

    def test_v2_roster_reuses_gallery_list_detail_and_member_portraits(self):
        store = IdentityV2Store(
            players=[Player("p1", "Sorap-Spieler", "m_new")],
            members=[
                Member("m_old", "Sorap", "Mage", playerId="p1",
                       currentRole="main", clmGuid="1:1", spec="Frost",
                       raidRole="dps", gearStatus="BiS"),
                Member("m_new", "Sorap", "Priest", playerId="p1",
                       currentRole="twink", clmGuid="1:2", spec="Holy",
                       raidRole="healer"),
                Member("m_empty", "Ohnebild", "Warrior"),
                Member("m_dead", "Tot", "Warrior", lifeStatus="dead",
                       deathDate="2026-01-01", burialType="collective"),
                Member("m_inactive", "Pause", "Rogue", lifeStatus="inactive"),
            ],
            raids=[Raid("r1", "2026-01-02", name="MC", raidType="MC")],
            attendance=[Attendance("a1", "r1", "m_old", "twink", playerId="p1"),
                        Attendance("a2", "r1", "m_new", "main", playerId="p1")],
            eternalDkpRecords=[
                EternalDkpRecord("d1", "e1", "m_old", "1:1", "award", 100),
                EternalDkpRecord("d2", "e2", "m_new", "1:2", "award", 200),
            ],
        )
        target = self.root / "Sorap_V2.ggc"
        save_new_identity_v2(store, target)
        before = target.read_bytes()
        for member_id in ("m_old", "m_new"):
            portrait = member_portrait_path(target, member_id)
            portrait.parent.mkdir(parents=True, exist_ok=True)
            picture = QPixmap(12, 12)
            picture.fill(Qt.GlobalColor.red if member_id == "m_old"
                         else Qt.GlobalColor.blue)
            self.assertTrue(picture.save(str(portrait)))
        self.assertFalse(self.open_path(target).called)
        self.window.switch_page("rooster")
        self.assertIs(self.window.stack.currentWidget(), self.window._pages["rooster"])
        self.assertIs(self.window.roster_content_stack.currentWidget(),
                      self.window.roster_scroll)
        cards = {card.member_id: card for card in self.window._roster_cards}
        self.assertEqual(set(cards), {"m_old", "m_new", "m_empty"})
        self.assertFalse(cards["m_old"].portrait._source.isNull())
        self.assertFalse(cards["m_new"].portrait._source.isNull())
        self.assertNotEqual(cards["m_old"].portrait._source.cacheKey(),
                            cards["m_new"].portrait._source.cacheKey())
        self.assertTrue(cards["m_empty"].portrait._source.isNull())
        self.assertIs(type(cards["m_old"].portrait), checker_qt.CoverImageLabel)
        self.assertFalse(cards["m_old"].portrait._contain_portrait)
        self.assertIsNotNone(cards["m_old"].class_icon)
        self.assertFalse(cards["m_old"].class_icon.pixmap().isNull())
        self.assertEqual(cards["m_old"].class_icon.toolTip(), "Mage")
        self.assertEqual(cards["m_old"].name_label.toolTip(), "Sorap")
        self.assertEqual(cards["m_old"].details_label.toolTip(), "Mage · Frost")
        self.assertIn(checker_qt.CLASS_COLORS["Mage"],
                      cards["m_old"].details_label.styleSheet())
        self.assertIn("Sorap-Spieler", cards["m_old"].toolTip())
        self.assertEqual([len(grid._items) for grid in self.window._roster_grids],
                         [1, 1, 1])
        cards["m_old"].clicked.emit("m_old")
        self.assertEqual(self.window.roster_selected_member_id, "m_old")
        self.assertEqual(self.window.roster_detail_name.text(), "Sorap")
        self.assertEqual(self.window.roster_detail_type.text(), "Twink")
        self.assertTrue(self.window.roster_dkp_section.isHidden())
        self.assertEqual(self.window.roster_detail_panel.objectName(),
                         "rosterCharacterSheet")
        self.assertEqual((self.window.roster_detail_panel.minimumWidth(),
                          self.window.roster_detail_panel.maximumWidth()),
                         (360, 480))
        self.assertEqual(self.window.roster_character_points.text(),
                         self.window._format_dkp_value(
                             self.window._v2_roster_by_id["m_old"].raidPoints))
        self.assertIn("Raid", self.window.roster_detail_rank.text())
        self.assertIn("<img", self.window.roster_detail_class.text())
        self.assertIn(checker_qt.CLASS_COLORS["Mage"],
                      self.window.roster_detail_class.text())
        self.assertIn("BiS", self.window.roster_detail_class.toolTip())
        self.assertFalse(self.window.roster_armory_button.isHidden())
        self.assertTrue(self.window.roster_armory_button.isEnabled())
        self.assertTrue(self.window.roster_detail_notes.isReadOnly())
        self.assertTrue(cards["m_old"].property("selected"))
        old_width = cards["m_old"].width()
        old_icon_width = cards["m_old"].class_icon.width()
        self.window.roster_zoom_slider.setValue(130)
        self.window._apply_roster_zoom()
        self.assertIs(next(card for card in self.window._roster_cards
                           if card.member_id == "m_old"), cards["m_old"])
        self.assertNotEqual(cards["m_old"].width(), old_width)
        self.assertGreater(cards["m_old"].class_icon.width(), old_icon_width)
        self.assertIn("Twink", cards["m_old"].secondary_label.text())
        self.assertIn("Heiler", cards["m_new"].secondary_label.text())
        self.window._set_roster_view("list")
        self.assertIs(self.window.roster_content_stack.currentWidget(),
                      self.window.v2_roster_page)
        self.assertEqual(self.window.v2_roster_page.table.rowCount(), 3)
        self.assertEqual(self.window.v2_roster_page.selected_member_id(), "m_old")
        self.window.v2_roster_page.table.horizontalHeader().sectionClicked.emit(1)
        sorted_ids = [row.member_id for row in self.window.v2_roster_page._rows]
        self.window._refresh_v2_roster_projection()
        self.assertEqual([row.member_id for row in self.window.v2_roster_page._rows],
                         sorted_ids)
        self.assertEqual(self.window.v2_roster_page.selected_member_id(), "m_old")
        self.window.v2_roster_page.select_member("m_new")
        self.assertEqual(self.window.roster_selected_member_id, "m_new")
        self.assertEqual(self.window.roster_detail_type.text(), "Main")
        self.assertIn(checker_qt.CLASS_COLORS["Priest"],
                      self.window.roster_detail_class.text())
        item = self.window._v2_roster_by_id["m_new"]
        self.assertEqual(self.window.roster_character_points.text(),
                         self.window._format_dkp_value(item.raidPoints))
        self.assertEqual(self.window.roster_eternal_character_points.text(),
                         self.window._format_dkp_value(item.eternalRaidPoints))
        self.assertEqual(self.window.roster_detail_rank.text().split(": ")[1],
                         item.raidRank.replace("_", " ") if item.raidRank else "–")
        with (patch.object(checker_qt.webbrowser, "open") as open_url,
              patch.object(self.window.model, "find_by_id",
                           side_effect=AssertionError("Legacy lookup in V2"))):
            self.window.roster_armory_button.click()
            open_url.assert_called_once_with(item.armoryUrl)
        self.window.v2_roster_page.select_member("m_empty")
        self.assertEqual(self.window.roster_selected_member_id, "m_empty")
        self.assertEqual(self.window.roster_detail_name.text(), "Ohnebild")
        self.assertTrue(self.window.roster_detail_portrait._source.isNull())
        self.assertIn(checker_qt.CLASS_COLORS["Warrior"],
                      self.window.roster_detail_class.text())
        self.assertIn("Level", self.window.roster_detail_class.toolTip())
        self.assertFalse(self.window.roster_profile_button.isHidden())
        self.assertFalse(self.window.roster_profile_button.isEnabled())
        self.window.roster_profile_button.click()
        self.assertIs(self.window.stack.currentWidget(), self.window._pages["rooster"])
        self.window.v2_roster_page.select_member("m_new")
        self.assertEqual(self.window.roster_selected_member_id, "m_new")
        self.window._set_roster_view("cards")
        self.assertTrue(next(card for card in self.window._roster_cards
                             if card.member_id == "m_new").property("selected"))
        self.window.roster_search_edit.setText("Frost")
        self.assertEqual({card.member_id for card in self.window._roster_cards}, {"m_old"})
        self.window.roster_search_edit.clear()
        self.window.roster_search_edit.setText("Sorap-Spieler")
        self.assertEqual({card.member_id for card in self.window._roster_cards},
                         {"m_old", "m_new"})
        self.window.roster_search_edit.clear()
        self.window.v2_roster_class_filter.setCurrentIndex(
            self.window.v2_roster_class_filter.findData("Priest"))
        self.assertEqual({card.member_id for card in self.window._roster_cards}, {"m_new"})
        self.window._set_roster_view("list")
        self.assertEqual(self.window.v2_roster_page.table.rowCount(), 1)
        self.assertEqual(self.window.v2_roster_page.selected_member_id(), "m_new")
        self.window._set_roster_view("cards")
        self.window.v2_roster_class_filter.setCurrentIndex(0)
        card = next(card for card in self.window._roster_cards
                    if card.member_id == "m_new")
        self.assertIsInstance(card, checker_qt.RosterDraftCard)
        self.assertIs(type(card.portrait), checker_qt.CoverImageLabel)
        self.assertIsNotNone(card.class_icon)
        self.assertFalse(card.class_icon.pixmap().isNull())
        self.assertIn(checker_qt.CLASS_COLORS["Priest"],
                      card.details_label.styleSheet())
        self.assertTrue(card.property("selected"))
        self.assertIn(":hover", card.styleSheet())
        card_size = card.size()
        card.set_selected(False)
        card.set_selected(True)
        self.assertEqual(card.size(), card_size)
        self.assertTrue(all(label.testAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            for label in card.findChildren(QLabel) if label is not card.portrait))
        self.assertFalse(self.window.identity_v2_dirty)
        self.assertEqual(target.read_bytes(), before)
        next(card for card in self.window._roster_cards
             if card.member_id == "m_old").clicked.emit("m_old")
        self.assertEqual(self.window.roster_selected_member_id, "m_old")
        self.assertFalse(self.window.roster_profile_button.isHidden())
        self.assertTrue(self.window.roster_profile_button.isEnabled())
        self.window.roster_profile_button.click()
        self.assertIs(self.window.stack.currentWidget(), self.window.player_profile_page)
        self.assertIs(self.window.player_profile_page.layout().itemAt(0).widget(),
                      self.window.player_profile_page.draft_page)
        self.assertEqual(self.window._player_profile.player_id, "p1")
        self.assertEqual(self.window._player_profile.selected_member_id, "m_old")
        self.assertEqual(
            self.window.player_profile_page.draft_page.character_combo.currentData(),
            "m_old")
        self.window.close_player_profile()
        self.assertIs(self.window.stack.currentWidget(), self.window._pages["rooster"])
        next(card for card in self.window._roster_cards
             if card.member_id == "m_empty").clicked.emit("m_empty")
        self.assertFalse(self.window.roster_profile_button.isEnabled())
        self.assertIn("QPushButton:disabled:hover",
                      self.window.roster_profile_button.styleSheet())
        self.assertIn("background:#151b22",
                      self.window.roster_profile_button.styleSheet())
        next(card for card in self.window._roster_cards
             if card.member_id == "m_old").clicked.emit("m_old")
        self.assertTrue(self.window.roster_profile_button.isEnabled())
        self.assertIn("background:#594322",
                      self.window.roster_profile_button.styleSheet())
        self.assertFalse(self.window.identity_v2_dirty)
        self.assertEqual(target.read_bytes(), before)

    def test_v2_roster_cards_show_only_active_rank_without_portrait_frame(self):
        raids = [Raid(f"r{index}", f"2026-04-{index:02d}",
                      name="MC", raidType="MC") for index in range(1, 31)]
        store = IdentityV2Store(
            players=[Player("p1", "Spieler", "m1")],
            members=[Member("m1", "Ohnebild", "Mage", playerId="p1",
                            clmGuid="1:1"),
                     Member("m2", "Neuer Main", "Priest", playerId="p1")],
            raids=raids,
            attendance=[Attendance(f"a{index}", f"r{index}", "m1", "main",
                                   playerId="p1") for index in range(1, 31)],
            eternalDkpRecords=[EternalDkpRecord(
                "d1", "e1", "m1", "1:1", "award", 1200)],
            pointMode="eternal_dkp",
        )
        target = self.root / "ranks-v2.ggc"
        save_new_identity_v2(store, target)
        self.assertFalse(self.open_path(target).called)
        self.assertEqual(self.window.model.active_point_mode(), "")
        self.window.switch_page("rooster")
        item = self.window._v2_roster_by_id["m1"]
        self.assertFalse(item.portraitPath.is_file())
        self.assertIsNotNone(item.framePath)
        self.assertIsNotNone(item.dkpRankPath)
        self.assertIsNone(item.raidRankPath)
        self.assertEqual(item.rankPath, item.dkpRankPath)
        self.assertEqual(item.frameAssetId, "frame_02")
        card = next(card for card in self.window._roster_cards if card.member_id == "m1")
        self.assertTrue(card.portrait._source.isNull())
        self.assertIs(type(card.portrait), checker_qt.CoverImageLabel)
        self.assertFalse(hasattr(card.portrait, "_reward_frame"))
        self.assertFalse(card.portrait._contain_portrait)
        self.assertIsNotNone(card.class_icon)
        self.assertFalse(card.class_icon.pixmap().isNull())
        self.assertFalse(card.rank_icon.pixmap().isNull())
        self.assertFalse(hasattr(card, "dkp_rank_icon"))
        self.assertIn("DKP", card.rank_icon.toolTip())
        self.window.show()
        self.app.processEvents()
        card_size = card.size()
        self.assertIn(":hover", card.styleSheet())
        QTest.mouseMove(card, card.rect().center())
        self.app.processEvents()
        self.assertEqual(card.size(), card_size)
        QTest.mousePress(card, Qt.MouseButton.LeftButton,
                         pos=card.rect().center())
        self.assertTrue(card.property("pressed"))
        self.assertEqual(card.size(), card_size)
        QTest.mouseRelease(card, Qt.MouseButton.LeftButton,
                           pos=card.rect().center())
        self.assertFalse(card.property("pressed"))
        self.assertEqual(card.size(), card_size)
        card.clicked.emit("m1")
        self.assertFalse(self.window.roster_reward_portrait._frame_source.isNull())
        dkp_frame_key = self.window.roster_reward_portrait._frame_source.cacheKey()
        self.assertTrue(self.window.roster_detail_portrait._source.isNull())
        self.assertTrue(self.window.roster_reward_portrait._badge_source.isNull())
        self.assertFalse(self.window.roster_rank_icon.pixmap().isNull())
        self.assertIn("DKP", self.window.roster_detail_rank.text())
        self.assertNotIn("Raid", self.window.roster_detail_rank.text())
        self.assertTrue(self.window.roster_points_form.isRowVisible(
            self.window.roster_current_dkp))
        self.assertFalse(self.window.roster_points_form.isRowVisible(
            self.window.roster_eternal_character_points))
        self.assertEqual(self.window.roster_points_title.text(),
                         checker_qt.tr("raid_clm_admin.eternal_dkp"))
        self.assertEqual(self.window.roster_character_points.text(), "1200")
        self.assertTrue(self.window.roster_dkp_section.isHidden())
        self.assertFalse(self.window.roster_armory_button.isHidden())
        self.assertTrue(self.window.v2_roster_page.table.isColumnHidden(12))
        self.assertFalse(self.window.v2_roster_page.table.isColumnHidden(9))
        self.assertFalse(self.window.v2_roster_page.table.isColumnHidden(2))
        self.assertEqual(self.window.v2_roster_sort.findData("raid_rank"), -1)
        self.assertGreaterEqual(self.window.v2_roster_sort.findData("dkp_rank"), 0)
        player_page = self.window.v2_players_page
        self.assertTrue(player_page.show_player_id("p1"))
        character_page = self.window.v2_character_data_page
        character_page.table.setCurrentCell(
            character_page.visible_member_ids.index("m1"), 0)

        def assert_active_views(*, dkp):
            form = next(item.layout() for item in (
                player_page.detail_layout.itemAt(index)
                for index in range(player_page.detail_layout.count()))
                if isinstance(item.layout(), QFormLayout))
            player_rows = {
                form.itemAt(index, QFormLayout.ItemRole.FieldRole).widget().objectName():
                form.itemAt(index, QFormLayout.ItemRole.FieldRole).widget()
                for index in range(form.rowCount())
            }
            for key in ("v2PlayerAvailableDkp", "v2PlayerEternalDkp",
                        "v2PlayerDkpRank"):
                self.assertEqual(form.isRowVisible(player_rows[key]), dkp)
            for key in ("v2PlayerRaidPoints", "v2PlayerEternalPoints",
                        "v2PlayerRaidRank"):
                self.assertEqual(form.isRowVisible(player_rows[key]), not dkp)
            for key in ("available_dkp", "eternal_dkp", "dkp_rank"):
                self.assertEqual(character_page.overview_form.isRowVisible(
                    character_page.detail_values[key]), dkp)
            for key in ("raid_points", "eternal_raid_points", "raid_rank"):
                self.assertEqual(character_page.overview_form.isRowVisible(
                    character_page.detail_values[key]), not dkp)
            self.assertEqual(character_page.special_points_button.isHidden(), dkp)
            self.assertEqual(character_page.point_history_button.isHidden(), dkp)

        assert_active_views(dkp=True)
        card = next(card for card in self.window._roster_cards if card.member_id == "m1")
        self.assertIsInstance(card, checker_qt.RosterDraftCard)
        self.assertIs(type(card.portrait), checker_qt.CoverImageLabel)
        self.assertFalse(hasattr(card.portrait, "_reward_frame"))
        self.assertFalse(card.portrait._contain_portrait)
        self.assertIsNotNone(card.class_icon)
        self.assertFalse(card.class_icon.pixmap().isNull())
        self.assertFalse(card.rank_icon.pixmap().isNull())
        self.assertFalse(hasattr(card, "dkp_rank_icon"))
        raid_projection = self.window._v2_raid_point_projection
        dkp_projection = self.window._v2_dkp_projection
        before = self.window.identity_v2_store.to_payload()
        before_file = target.read_bytes()
        self.assertTrue(self.window.set_v2_active_point_system("raid_points"))
        self.assertIsNone(raid_projection)
        self.assertIsNotNone(self.window._v2_raid_point_projection)
        self.assertIsNot(self.window._v2_dkp_projection, dkp_projection)
        item = self.window._v2_roster_by_id["m1"]
        self.assertEqual(item.rankPath, item.raidRankPath)
        self.assertEqual(item.frameAssetId, "frame_01")
        self.assertNotEqual(item.rankPath, item.dkpRankPath)
        self.assertFalse(self.window.roster_reward_portrait._frame_source.isNull())
        self.assertNotEqual(self.window.roster_reward_portrait._frame_source.cacheKey(),
                            dkp_frame_key)
        self.assertTrue(self.window.roster_detail_portrait._source.isNull())
        self.assertTrue(self.window.roster_reward_portrait._badge_source.isNull())
        raid_card = next(card for card in self.window._roster_cards
                         if card.member_id == "m1")
        self.assertTrue(raid_card.portrait._source.isNull())
        self.assertIs(type(raid_card.portrait), checker_qt.CoverImageLabel)
        self.assertFalse(hasattr(raid_card.portrait, "_reward_frame"))
        self.assertIsNotNone(raid_card.class_icon)
        self.assertFalse(raid_card.rank_icon.pixmap().isNull())
        self.assertFalse(hasattr(raid_card, "dkp_rank_icon"))
        self.assertIn("Raid", self.window.roster_detail_rank.text())
        self.assertNotIn("DKP", self.window.roster_detail_rank.text())
        self.assertFalse(self.window.roster_points_form.isRowVisible(
            self.window.roster_current_dkp))
        self.assertTrue(self.window.roster_points_form.isRowVisible(
            self.window.roster_eternal_character_points))
        self.assertEqual(self.window.roster_points_title.text(),
                         checker_qt.tr("raid_points.title"))
        self.assertTrue(self.window.roster_dkp_section.isHidden())
        self.assertFalse(self.window.roster_armory_button.isHidden())
        self.assertTrue(self.window.v2_roster_page.table.isColumnHidden(9))
        self.assertFalse(self.window.v2_roster_page.table.isColumnHidden(12))
        self.assertFalse(self.window.v2_roster_page.table.isColumnHidden(2))
        self.assertEqual(self.window.v2_roster_sort.findData("dkp_rank"), -1)
        self.assertGreaterEqual(self.window.v2_roster_sort.findData("raid_rank"), 0)
        assert_active_views(dkp=False)
        raid_draft = next(card for card in self.window._roster_cards
                          if card.member_id == "m1")
        self.assertIs(type(raid_draft.portrait), checker_qt.CoverImageLabel)
        self.assertFalse(hasattr(raid_draft.portrait, "_reward_frame"))
        self.assertFalse(raid_draft.portrait._contain_portrait)
        self.assertIsNotNone(raid_draft.class_icon)
        self.assertFalse(raid_draft.class_icon.pixmap().isNull())
        self.assertFalse(raid_draft.rank_icon.pixmap().isNull())
        self.assertFalse(hasattr(raid_draft, "dkp_rank_icon"))
        after = self.window.identity_v2_store.to_payload()
        self.assertEqual({key: value for key, value in after.items()
                          if key != "pointMode"},
                         {key: value for key, value in before.items()
                          if key != "pointMode"})
        self.assertEqual(after["pointMode"], "raid_points")
        self.assertEqual(target.read_bytes(), before_file)
        self.window.save_project()
        reloaded = load_identity_v2(target)
        self.assertEqual(reloaded.pointMode, "raid_points")
        self.assertEqual(reloaded.eternalDkpRecords, store.eternalDkpRecords)
        self.assertEqual(reloaded.raidPoints, store.raidPoints)
        changed = set_main(self.window.identity_v2_store, "p1", "m2")
        self.window._apply_v2_player_store(changed)
        self.assertIsNone(self.window._v2_roster_by_id["m1"].framePath)
        self.assertIsNotNone(self.window._v2_roster_by_id["m2"].framePath)

    def test_v2_roster_png_renders_shared_filtered_cards_in_both_modes(self):
        raids = [Raid(f"r{index}", f"2026-04-{index:02d}",
                      name="MC", raidType="MC") for index in range(1, 31)]
        store = IdentityV2Store(
            players=[Player("p1", "Erste", "m1"), Player("p2", "Zweite", "m2")],
            members=[Member("m1", "Sorap", "Mage", playerId="p1", clmGuid="g1"),
                     Member("m2", "Sorap", "Mage", playerId="p2", clmGuid="g2"),
                     Member("m3", "Sorap", "Mage", lifeStatus="inactive"),
                     Member("m4", "Sorap", "Mage", lifeStatus="dead",
                            burialType="collective", deathDate="2026-04-30")],
            raids=raids,
            attendance=[Attendance(f"a{index}-1", f"r{index}", "m1", "main",
                                   playerId="p1") for index in range(1, 31)]
            + [Attendance(f"a{index}-2", f"r{index}", "m2", "main",
                          playerId="p2") for index in range(1, 31)],
            eternalDkpRecords=[
                EternalDkpRecord("d1", "e1", "m1", "g1", "award", 1200),
                EternalDkpRecord("d2", "e2", "m2", "g2", "award", 1200),
            ],
        )
        target = self.root / "roster-png-v2.ggc"
        save_new_identity_v2(store, target)
        for member_id, color in (("m1", Qt.GlobalColor.red),
                                 ("m2", Qt.GlobalColor.blue)):
            portrait = member_portrait_path(target, member_id)
            portrait.parent.mkdir(parents=True, exist_ok=True)
            picture = QPixmap(12, 12)
            picture.fill(color)
            self.assertTrue(picture.save(str(portrait)))
        self.assertFalse(self.open_path(target).called)
        self.window.show()
        self.window.switch_page("rooster")
        self.window.roster_search_edit.setText("Sorap")
        self.window._set_roster_view("list")
        self.assertEqual(self.window.v2_roster_page.table.rowCount(), 2)
        source_bytes = target.read_bytes()
        for mode in ("eternal_dkp", "raid_points"):
            self.window.set_v2_active_point_system(mode)
            before_store = self.window.identity_v2_store.to_payload()
            before_dirty = self.window.identity_v2_dirty
            output = self.root / f"roster-{mode}.png"
            with patch.object(checker_qt.QFileDialog, "getSaveFileName",
                              return_value=(str(output), "")):
                self.window.export_roster_png()
            self.assertTrue(output.is_file())
            self.assertGreater(QPixmap(str(output)).width(), 300)
            self.assertEqual({card.member_id for card in self.window._roster_cards},
                             {"m1", "m2"})
            for member_id in ("m1", "m2"):
                item = self.window._v2_roster_by_id[member_id]
                self.assertEqual(
                    item.rankPath,
                    item.dkpRankPath if mode == "eternal_dkp" else item.raidRankPath)
                self.assertIsNotNone(item.framePath)
            self.assertTrue(all(not card.portrait._source.isNull()
                                for card in self.window._roster_cards))
            self.assertTrue(all(type(card.portrait) is checker_qt.CoverImageLabel
                                and not hasattr(card.portrait, "_reward_frame")
                                for card in self.window._roster_cards))
            self.assertTrue(all(not card.rank_icon.pixmap().isNull()
                                for card in self.window._roster_cards))
            self.assertTrue(all(not hasattr(card, "dkp_rank_icon")
                                for card in self.window._roster_cards))
            self.assertEqual(self.window.identity_v2_store.to_payload(), before_store)
            self.assertEqual(self.window.identity_v2_dirty, before_dirty)
            self.assertEqual(target.read_bytes(), source_bytes)

    def test_v2_player_profile_family_selection_and_raid_rows_use_ids(self):
        store = IdentityV2Store(
            players=[Player("p1", "Familie", "m_main", mainHistory=[
                MainHistoryEntry("mh0001", "m_dead", "2025-01-01", "2026-01-02")]),
                     Player("p2", "Ohne Main"), Player("p3", "Leer")],
            members=[
                Member("m_main", "Gleich", "Mage", playerId="p1",
                       currentRole="twink", spec="Frost", raidRole="dps",
                       gearStatus="BiS", raidStatus="Bereit"),
                Member("m_dead", "Gleich", "Priest", playerId="p1",
                       currentRole="main", lifeStatus="dead", deathDate="2026-01-02",
                       burialType="collective"),
                Member("m_inactive", "Pause", "Rogue", playerId="p1",
                       lifeStatus="inactive"),
                Member("m_solo", "Solo", "Warrior", playerId="p2",
                       lifeStatus="dead", deathDate="2026-01-01",
                       burialType="collective"),
            ],
            raids=[Raid("r1", "2026-01-01", name="MC", raidType="MC"),
                   Raid("r2", "2026-01-02", name="MC", raidType="MC"),
                   Raid("r3", "2026-01-02", name="Ony", raidType="Onyxia"),
                   Raid("r4", "2026-01-03", name="BWL", raidType="BWL")],
            attendance=[
                Attendance("a1", "r1", "m_main", "main", playerId="p1"),
                Attendance("a2", "r2", "m_main", "main", playerId="p1",
                           status="bench"),
                Attendance("a3", "r3", "m_main", "main", playerId="p1"),
                Attendance("a4", "r1", "m_dead", "twink", playerId="p1"),
                Attendance("a5", "r1", "m_solo", "twink", playerId="p2"),
            ],
        )
        target = self.root / "profile-v2.ggc"
        save_new_identity_v2(store, target)
        portrait = member_portrait_path(target, "m_main")
        portrait.parent.mkdir(parents=True, exist_ok=True)
        picture = QPixmap(12, 12)
        picture.fill(Qt.GlobalColor.blue)
        self.assertTrue(picture.save(str(portrait)))
        before_file = target.read_bytes()
        self.assertFalse(self.open_path(target).called)
        self.window.switch_page("rooster")
        self.assertTrue(self.window.open_player_profile_for_member("m_main"))
        self.assertIs(self.window.stack.currentWidget(), self.window.player_profile_page)
        profile = self.window._player_profile
        self.assertEqual((profile.player_id, profile.current_main_member_id),
                         ("p1", "m_main"))
        self.assertEqual({item.member_id for item in profile.characters},
                         {"m_main", "m_dead", "m_inactive"})
        self.assertEqual((profile.raid_count, profile.raid_days), (3, 2))
        page = self.window.player_profile_page.draft_page
        self.assertEqual(set(page.family_buttons),
                         {"m_main", "m_dead", "m_inactive"})
        self.assertIn("2025-01-01", page.family_buttons["m_dead"].toolTip())
        self.assertEqual(page.character_type.text(), "Main")
        self.assertFalse(page.player_portrait._source.isNull())
        self.assertIn("<img", page.character_identity_line.text())
        self.assertIn("BiS", page.character_identity_line.toolTip())
        self.assertIn("Bereit", page.character_identity_line.toolTip())
        self.assertEqual(page.character_metric_labels["raids"].text(),
                         "3 · 2 Raidtage")
        self.assertEqual(len(profile.selected_character.raid_rows), 4)
        self.assertEqual(page.character_raid_table.rowCount(), 3)
        self.assertEqual(self.window.player_profile_page.character_raid_table.rowCount(), 3)
        statuses = {page.character_raid_table.item(row, 0).data(
            Qt.ItemDataRole.UserRole): page.character_raid_table.item(row, 2).text()
            for row in range(3)}
        self.assertEqual(set(statuses), {"r1", "r2", "r3"})
        self.assertEqual(statuses["r1"], checker_qt.tr("raids.attendance_status_present"))
        self.assertEqual(statuses["r2"], checker_qt.tr("raids.attendance_status_bench"))

        page.character_combo.setCurrentIndex(page.character_combo.findData("m_dead"))
        self.assertEqual(self.window._player_profile.selected_member_id, "m_dead")
        self.assertEqual(page.character_name.text(), "Gleich")
        self.assertEqual(page.character_type.text(), "Twink")
        self.assertEqual(page.character_life.text(), "Tot")
        self.assertTrue(page.family_buttons["m_dead"].isChecked())
        self.assertFalse(page.player_portrait._source.isNull())
        dead_statuses = {page.character_raid_table.item(row, 0).data(
            Qt.ItemDataRole.UserRole): page.character_raid_table.item(row, 2).text()
            for row in range(page.character_raid_table.rowCount())}
        self.assertEqual(set(dead_statuses), {"r1"})
        page.character_combo.setCurrentIndex(page.character_combo.findData("m_inactive"))
        self.assertEqual(page.character_life.text(), "Inaktiv")
        self.assertTrue(page.player_portrait._source.isNull())
        self.assertEqual(page.character_raid_table.rowCount(), 0)
        page.family_buttons["m_dead"].click()
        self.assertEqual(self.window._player_profile.selected_member_id, "m_dead")

        page.player_combo.setCurrentIndex(page.player_combo.findData("p2"))
        self.assertEqual(self.window._player_profile.player_id, "p2")
        self.assertIsNone(self.window._player_profile.current_main_member_id)
        self.assertEqual(set(page.family_buttons), {"m_solo"})
        self.assertEqual(page.character_name.text(), "Solo")
        self.assertEqual(page.character_life.text(), "Tot")
        self.assertEqual((self.window._player_profile.raid_count,
                          self.window._player_profile.raid_days), (1, 1))
        self.assertEqual(page.character_raid_table.rowCount(), 1)
        page.player_combo.setCurrentIndex(page.player_combo.findData("p3"))
        self.assertEqual(self.window._player_profile.player_id, "p3")
        self.assertEqual(self.window._player_profile.characters, ())
        self.assertEqual(page.character_raid_table.rowCount(), 0)
        page.back_button.click()
        self.assertIs(self.window.stack.currentWidget(), self.window._pages["rooster"])
        self.window.switch_page("management")
        players_page = self.window.v2_players_page
        players_page._refresh_master(preferred_player_id="p1")
        players_page.detail_host.findChildren(
            QPushButton, "openPlayerProfileButton")[-1].click()
        self.assertIs(self.window.stack.currentWidget(), self.window.player_profile_page)
        self.assertEqual(self.window._player_profile.player_id, "p1")
        self.assertIs(self.window.player_profile_page.layout().itemAt(0).widget(),
                      self.window.player_profile_page.draft_page)
        self.window.close_player_profile()
        self.assertIs(self.window.stack.currentWidget(), players_page)
        self.assertFalse(self.window.identity_v2_dirty)
        self.assertEqual(target.read_bytes(), before_file)

    def test_v2_player_profile_point_mode_updates_existing_profile(self):
        store = IdentityV2Store(
            players=[Player("p1", "Spieler", "m1")],
            members=[Member("m1", "Held", "Mage", playerId="p1",
                            clmGuid="1:1")],
            raids=[Raid("r1", "2026-01-01", name="MC", raidType="MC",
                        clmRaidId="clm-r1")],
            attendance=[Attendance("a1", "r1", "m1", "main", playerId="p1")],
            eternalDkpRecords=[EternalDkpRecord(
                "d1", "e1", "m1", "1:1", "award", 1200,
                clmRaidId="clm-r1")],
            pointMode="eternal_dkp",
        )
        target = self.root / "profile-points-v2.ggc"
        save_new_identity_v2(store, target)
        before_file = target.read_bytes()
        self.assertFalse(self.open_path(target).called)
        self.assertTrue(self.window.open_player_profile("p1"))
        page = self.window.player_profile_page.draft_page
        self.assertEqual(page.player_metric_titles["eternal_dkp"].text(),
                         checker_qt.tr("raid_clm_admin.eternal_player"))
        self.assertEqual(page.player_metric_labels["eternal_dkp"].text(), "1200")
        self.assertEqual(page.character_metric_labels["eternal_dkp"].text(), "1200")
        dkp_rank = self.window._v2_dkp_projection.dkp_rank_for_member("m1")
        self.assertEqual(page.character_rank.text(), dkp_rank.replace("_", " "))
        self.assertFalse(page.player_rank_icon.pixmap().isNull())
        self.assertFalse(page.player_reward_portrait._frame_source.isNull())
        self.assertEqual(page.character_raid_table.item(0, 3).text(), "1200")
        before = self.window.identity_v2_store.to_payload()
        self.assertTrue(self.window.set_v2_active_point_system("raid_points"))
        self.assertIs(self.window.stack.currentWidget(), self.window.player_profile_page)
        self.assertEqual(self.window._player_profile.selected_member_id, "m1")
        self.assertEqual(page.player_metric_titles["eternal_dkp"].text(),
                         checker_qt.tr("identity_v2_raid_points.eternal_player"))
        self.assertEqual(page.character_details_form.labelForField(
            page.character_metric_labels["eternal_dkp"]).text(),
            checker_qt.tr("identity_v2_character_data.detail_eternal_raid_points"))
        raid_rank = self.window._v2_dkp_projection.raid_rank_for_member("m1")
        self.assertEqual(page.character_rank.text(),
                         raid_rank.replace("_", " ") if raid_rank else "–")
        self.assertNotEqual(page.character_rank.text(), dkp_rank.replace("_", " "))
        self.assertNotEqual(page.character_raid_table.item(0, 3).text(), "1200")
        self.assertEqual({key: value for key, value in
                          self.window.identity_v2_store.to_payload().items()
                          if key != "pointMode"},
                         {key: value for key, value in before.items()
                          if key != "pointMode"})
        self.assertEqual(target.read_bytes(), before_file)

    def test_v2_table_hover_preserves_ids_selection_and_matrix_colors(self):
        store = IdentityV2Store(
            players=[Player("p1", "Spieler", "m1")],
            members=[Member("m1", "Held", "Mage", playerId="p1"),
                     Member("m2", "Frei", "Priest")],
            raids=[Raid("r1", "2026-04-01", name="MC", raidType="MC")],
            attendance=[Attendance("a1", "r1", "m1", "main", playerId="p1")],
        )
        target = self.root / "hover-v2.ggc"
        save_new_identity_v2(store, target)
        self.assertFalse(self.open_path(target).called)
        self.window.show()
        before = self.window.identity_v2_store.to_payload()
        self.window.switch_page("identity_v2_players")
        players = self.window.v2_players_page
        player_tab = self.window._v2_management_buttons["players"]
        character_tab = self.window._v2_management_buttons["characters"]
        self.assertEqual(player_tab.text(), "Spielerdaten")
        self.assertEqual(character_tab.text(), "Charakterdaten")
        self.assertEqual(player_tab.minimumHeight(), character_tab.minimumHeight())
        self.assertGreaterEqual(player_tab.minimumHeight(), 36)
        self.assertTrue(player_tab.property("v2ManagementTab"))
        self.assertTrue(character_tab.property("v2ManagementTab"))
        self.assertTrue(players.show_player_id("p1"))
        self.app.processEvents()
        QTest.mouseMove(players.player_table.viewport(),
                        players.player_table.visualItemRect(
                            players.player_table.item(0, 0)).center())
        self.assertEqual(players.player_row_hover.row, 0)
        hover_option = QStyleOptionViewItem()
        hover_option.state = QStyle.StateFlag.State_Enabled
        for column in range(players.player_table.columnCount()):
            painted = players.player_row_hover.paint_option(
                hover_option, players.player_table.model().index(0, column))
            self.assertEqual(painted.backgroundBrush.color().name(), "#332b20")
        selected_option = QStyleOptionViewItem(hover_option)
        selected_option.state |= QStyle.StateFlag.State_Selected
        self.assertIs(players.player_row_hover.paint_option(
            selected_option, players.player_table.model().index(0, 0)),
            selected_option)
        self.assertEqual(players._current_player_id(), "p1")
        self.window.switch_page("identity_v2_character_data")
        characters = self.window.v2_character_data_page
        characters.table.setCurrentCell(characters.visible_member_ids.index("m1"), 0)
        self.app.processEvents()
        other = characters.visible_member_ids.index("m2")
        QTest.mouseMove(characters.table.viewport(),
                        characters.table.visualItemRect(
                            characters.table.item(other, 0)).center())
        self.assertEqual(characters.table_row_hover.row, other)
        self.assertEqual(characters.selected_member_id, "m1")
        for column in range(characters.table.columnCount()):
            painted = characters.table_row_hover.paint_option(
                hover_option, characters.table.model().index(other, column))
            self.assertEqual(painted.backgroundBrush.color().name(), "#332b20")
        self.window.switch_page("raid")
        raid_table = self.window.raid_table
        self.app.processEvents()
        QTest.mouseMove(raid_table.viewport(),
                        raid_table.visualItemRect(raid_table.item(0, 0)).center())
        self.assertEqual(raid_table.row_hover.row, 0)
        self.window.switch_page("identity_v2_matrix")
        fixed = self.window.raid_stats_table
        self.app.processEvents()
        colors = [item.data(Qt.ItemDataRole.BackgroundRole)
                  for row in range(self.window.raid_matrix_table.rowCount())
                  for column in range(self.window.raid_matrix_table.columnCount())
                  if (item := self.window.raid_matrix_table.item(row, column))]
        if fixed.rowCount():
            QTest.mouseMove(fixed.viewport(),
                            fixed.visualItemRect(fixed.item(0, 0)).center())
            self.assertEqual(fixed.row_hover.row, 0)
        self.assertEqual(colors, [item.data(Qt.ItemDataRole.BackgroundRole)
                                  for row in range(self.window.raid_matrix_table.rowCount())
                                  for column in range(self.window.raid_matrix_table.columnCount())
                                  if (item := self.window.raid_matrix_table.item(row, column))])
        management = checker_qt.MemberTable()
        self.addCleanup(management.close)
        management.setRowCount(1)
        management.setItem(0, 0, checker_qt.QTableWidgetItem("Test"))
        management.row_hover.row = 0
        self.assertIsInstance(management.itemDelegate(), checker_qt.MemberEditDelegate)
        painted = management.row_hover.paint_option(
            hover_option, management.model().index(0, 1))
        self.assertEqual(painted.backgroundBrush.color().name(), "#332b20")
        self.assertEqual(self.window.identity_v2_store.to_payload(), before)

    def test_manual_v2_dkp_refresh_uses_guid_cache_without_saving_project(self):
        before = self.target.read_bytes()
        self.assertFalse(self.open_path(self.target).called)
        self.window.switch_page("settings")
        self.assertIn("Punktesystem", self.window.dkp_enabled_check.toolTip())
        self.window.guild_name_edit.setText("Bierstube")
        self.window.guild_realm_edit.setText("Stitches")
        self.window.dkp_enabled_check.setChecked(True)
        self.assertEqual(self.window.guild_name_edit.text(), "Bierstube")
        self.assertEqual(self.window.guild_realm_edit.text(), "Stitches")
        self.window.save_guild_master_data()
        self.assertEqual(self.window.identity_v2_store.pointMode, "eternal_dkp")
        self.assertEqual(self.window.model.active_point_mode(), "")
        self.assertFalse(hasattr(self.window, "settings_migration_card"))
        self.assertTrue(self.window.points_group.isHidden())
        self.assertTrue(self.window.settings_raid_scope_controls.isHidden())
        self.assertTrue(self.window.clm_history_sync_button.isHidden())
        with patch.object(checker_qt.QFileDialog, "getOpenFileName",
                          return_value=(str(self.root / "ClassicLootManager.lua"), "")):
            self.window.choose_clm_path()
        self.assertTrue(self.window.clm_group.isEnabled())
        self.window.switch_page("rooster")
        self.window.clm_refresh_button.click()
        snapshot = self.window._clm_refresh_service.cached_snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual(
            self.window._v2_dkp_projection.available_by_member,
            available_dkp_by_member(self.window.identity_v2_store, snapshot.balances),
        )
        self.assertEqual(self.window._v2_dkp_projection.refreshed_at, snapshot.refreshed_at)
        self.assertIn(snapshot.refreshed_at.astimezone().strftime("%Y-%m-%d %H:%M"),
                      self.window.clm_status_label.text())
        for member_id, item in self.window._v2_roster_by_id.items():
            self.assertEqual(item.availableDkp,
                             self.window._v2_dkp_projection.available_for_member(member_id))
        with patch.object(self.window._clm_refresh_service, "refresh_for_project",
                          side_effect=AssertionError("ungebetener CLM-Replay")):
            self.window.refresh_all()
            self.window.v2_roster_page._populate()
            self.window._refresh_v2_dkp_projection()
        self.assertEqual(self.target.read_bytes(), before)
        dkp_projection = self.window._v2_dkp_projection
        raid_projection = self.window._v2_raid_point_projection
        history = list(self.window.identity_v2_store.eternalDkpRecords)
        self.window.switch_page("settings")
        self.window.points_enabled_check.setChecked(True)
        self.assertEqual(self.window.identity_v2_store.pointMode, "raid_points")
        self.assertFalse(self.window.clm_group.isHidden())
        self.window.dkp_enabled_check.setChecked(True)
        self.assertEqual(self.window.identity_v2_store.pointMode, "eternal_dkp")
        self.assertFalse(self.window.clm_group.isHidden())
        self.assertIsNot(self.window._v2_dkp_projection, dkp_projection)
        self.assertEqual(self.window._v2_dkp_projection.available_by_member,
                         dkp_projection.available_by_member)
        self.assertIsNone(self.window._v2_raid_point_projection)
        self.assertIsNone(raid_projection)
        self.assertEqual(self.window.identity_v2_store.eternalDkpRecords, history)
        self.assertEqual(self.target.read_bytes(), before)
        self.window.save_project()
        saved = load_identity_v2(self.target)
        self.assertEqual((saved.pointMode, saved.guildName, saved.realm),
                         ("eternal_dkp", "Bierstube", "Stitches"))

    def test_settings_rebuilds_v2_raid_points_only_on_click(self):
        self.assertFalse(self.open_path(self.target).called)
        self.window.switch_page("settings")
        self.assertFalse(self.window.points_group.isHidden())
        self.assertFalse(self.window.clm_group.isHidden())
        self.assertTrue(self.window.points_rebuild_button.isHidden())
        before = self.target.read_bytes()
        self.assertFalse(self.window.identity_v2_dirty)
        with (patch.object(self.window, "rebuild_raid_points",
                           side_effect=AssertionError("Legacy-Handler")),
              patch.object(self.window, "_set_v2_raid_point_store",
                           wraps=self.window._set_v2_raid_point_store) as rebuild):
            self.window.raid_points_only_rebuild_button.click()
        rebuild.assert_called_once_with(self.window.identity_v2_store, force=True)
        self.assertTrue(self.window.points_status_label.text())
        self.assertFalse(self.window.identity_v2_dirty)
        self.assertEqual(self.target.read_bytes(), before)
        with (patch.object(self.window, "_rebuild_v2_raid_points",
                           side_effect=AssertionError("ungefragter Neuaufbau")),
              patch.object(self.window._clm_refresh_service, "refresh_for_project",
                           side_effect=AssertionError("ungefragtes Lua-Replay"))):
            self.window.dkp_enabled_check.setChecked(True)
            self.window.points_enabled_check.setChecked(True)
        self.assertFalse(self.window.clm_group.isHidden())
        self.assertFalse(self.window.points_group.isHidden())

    def test_saved_clm_roster_is_restored_and_missing_name_requires_selection(self):
        self.store.pointMode = "eternal_dkp"
        self.store.clmRosterName = "Unbekanntes Roster"
        self.store.clmLuaPath = str(self.root / "ClassicLootManager.lua")
        self.store.guildName = "Bierstube"
        self.store.realm = "Stitches"
        self.target = self.root / "Rosterwahl_V2.ggc"
        save_new_identity_v2(self.store, self.target)
        with patch.object(checker_qt.ClmDkpRefreshService, "refresh_for_project",
                          side_effect=AssertionError("Lua-Replay beim Öffnen")):
            self.assertFalse(self.open_path(self.target).called)
        self.window.switch_page("settings")
        self.assertEqual(self.window.clm_roster_combo.currentText(),
                         "Unbekanntes Roster")
        self.assertFalse(self.window.identity_v2_dirty)

        self.window.clm_refresh_button.click()
        self.assertEqual(self.window.clm_roster_combo.currentIndex(), -1)
        self.assertEqual(self.window.identity_v2_store.clmRosterName,
                         "Unbekanntes Roster")
        self.assertIsNone(self.window._clm_refresh_service.cached_snapshot)
        self.assertGreater(self.window.clm_roster_combo.count(), 0)
        self.window.clm_roster_combo.setCurrentIndex(0)
        selected_name = self.window.clm_roster_combo.itemData(
            0, int(Qt.ItemDataRole.UserRole) + 1)
        self.assertEqual(self.window.identity_v2_store.clmRosterName, selected_name)
        self.assertTrue(self.window.identity_v2_dirty)
        self.assertEqual(load_identity_v2(self.target).clmRosterName,
                         "Unbekanntes Roster")
        self.window.clm_refresh_button.click()
        self.assertEqual(self.window._clm_refresh_service.cached_snapshot.roster_name,
                         selected_name)
        self.window.save_project()
        self.assertEqual(load_identity_v2(self.target).clmRosterName, selected_name)
        with patch.object(checker_qt.ClmDkpRefreshService, "refresh_for_project",
                          side_effect=AssertionError("Lua-Replay beim erneuten Öffnen")):
            self.assertFalse(self.open_path(self.target).called)
        self.assertEqual(self.window.clm_roster_combo.currentText(),
                         f"{selected_name} · {self.window.identity_v2_store.clmRosterId}")
        self.assertFalse(self.window.identity_v2_dirty)

    def _raid_refresh_with_open_guid(self):
        from tests.clm_raid_v2_materialization_tests import analysis_for

        analysis = analysis_for((
            ((1, 101), "Main", 5, 1, None),
            ((1, 102), "Main", 5, 2, None),
            ((1, 103), "Ohne Raid", 5, 2, None),
        ), ((3, "MC", ((1, 102),), (), ()),))
        store = IdentityV2Store(
            guildName="Bierstube", realm="Stitches",
            clmLuaPath=str(self.root / "ClassicLootManager.lua"),
            clmDatabaseId="exp0 alliance stitches bierstube",
            clmRosterId="10", clmRosterName="Bierstube",
            members=[Member("m1000", "Main", "Priest", clmGuid="1:101")],
        )
        target = self.root / "RaidRefresh_V2.ggc"
        save_new_identity_v2(store, target)
        self.assertFalse(self.open_path(target).called)
        return analysis, target

    def test_raid_refresh_reviews_only_open_participant_and_reanalyzes(self):
        analysis, target = self._raid_refresh_with_open_guid()
        from app.clm_v2_initialization_ui import ClmRaidReviewDialog

        def decisions(scoped, _parent):
            self.assertEqual([item.guid for item in scoped.guid_histories], ["1:102"])
            return ClmIdentityDecisionDraft(scoped).to_decision_set()

        def classifications(scoped, _decisions, _parent, *, target_store,
                            include_chains):
            self.assertEqual([item.guid for item in scoped.guid_histories], ["1:102"])
            self.assertEqual(include_chains, {("1:102",)})
            self.assertEqual(target_store.members[0].clmGuid, "1:101")
            return {("1:102",): CharacterImportChoice(member_id="m1000")}

        with (patch("app.clm_v2_initialization.analyze_clm_v2_selection",
                    side_effect=[deepcopy(analysis), deepcopy(analysis)]) as analyze,
              patch("app.clm_identity_v2_dialog.collect_clm_identity_decisions",
                    side_effect=decisions) as identity_review,
              patch("app.clm_v2_classification_ui.collect_clm_character_classifications",
                    side_effect=classifications) as character_review,
              patch.object(ClmRaidReviewDialog, "exec",
                           return_value=QDialog.DialogCode.Accepted) as raid_review,
              patch.object(ClmRaidReviewDialog, "selected_types",
                           return_value={analysis.raids[0].raid_id: "MC"}),
              patch.object(checker_qt.QMessageBox, "question",
                           return_value=checker_qt.QMessageBox.StandardButton.Yes),
              patch.object(checker_qt.QMessageBox, "warning") as warning,
              patch.object(checker_qt.ClmDkpRefreshService,
                           "refresh_from_document",
                           side_effect=AssertionError("DKP darf nicht aktualisiert werden"))):
            self.window.refresh_raids_from_clm()
        warning.assert_not_called()
        self.assertEqual(analyze.call_count, 2)
        identity_review.assert_called_once()
        character_review.assert_called_once()
        self.assertEqual(raid_review.call_count, 2)  # Auswahl vor GUID-Review, dann Raid-Review.
        refreshed = self.window.identity_v2_store
        self.assertEqual(refreshed.members[0].clmGuid, "1:102")
        self.assertEqual(refreshed.legacyClmGuidMemberMap["1:101"], "m1000")
        self.assertEqual([(entry.memberId, entry.clmGuid)
                          for entry in refreshed.attendance], [("m1000", "1:102")])
        self.assertEqual(len(refreshed.raids), 1)
        self.assertIsNone(self.window._v2_dkp_snapshot)
        self.assertEqual(load_identity_v2(target).members[0].clmGuid, "1:101")

        before = refreshed.to_payload()
        with (patch("app.clm_v2_initialization.analyze_clm_v2_selection",
                    return_value=deepcopy(analysis)) as analyze,
              patch("app.clm_identity_v2_dialog.collect_clm_identity_decisions",
                    side_effect=AssertionError("Bereits geklärte GUID erneut gefragt")),
              patch("app.clm_v2_classification_ui.collect_clm_character_classifications",
                    side_effect=AssertionError("Bereits geklärte GUID erneut klassifiziert")),
              patch.object(ClmRaidReviewDialog, "exec",
                           return_value=QDialog.DialogCode.Accepted),
              patch.object(ClmRaidReviewDialog, "selected_types", return_value={}),
              patch.object(checker_qt.QMessageBox, "question",
                           return_value=checker_qt.QMessageBox.StandardButton.Yes),
              patch.object(checker_qt.QMessageBox, "warning") as warning,
              patch.object(checker_qt.ClmDkpRefreshService,
                           "refresh_from_document",
                           side_effect=AssertionError("DKP darf nicht aktualisiert werden"))):
            self.window.refresh_raids_from_clm()
        warning.assert_not_called()
        analyze.assert_called_once()
        self.assertEqual(self.window.identity_v2_store.to_payload(), before)

    def test_raid_refresh_identity_or_raid_cancel_keeps_project_unchanged(self):
        analysis, target = self._raid_refresh_with_open_guid()
        from app.clm_v2_initialization_ui import ClmRaidReviewDialog

        before = self.window.identity_v2_store.to_payload()
        file_before = target.read_bytes()
        with (patch("app.clm_v2_initialization.analyze_clm_v2_selection",
                    return_value=deepcopy(analysis)),
              patch("app.clm_identity_v2_dialog.collect_clm_identity_decisions",
                    return_value=None),
               patch.object(checker_qt.QMessageBox, "warning") as warning,
               patch.object(ClmRaidReviewDialog, "exec",
                            return_value=QDialog.DialogCode.Accepted) as raid_review):
            self.window.refresh_raids_from_clm()
        warning.assert_not_called()
        raid_review.assert_called_once()
        self.assertEqual(self.window.identity_v2_store.to_payload(), before)

        def decisions(scoped, _parent):
            return ClmIdentityDecisionDraft(scoped).to_decision_set()

        with (patch("app.clm_v2_initialization.analyze_clm_v2_selection",
                    side_effect=[deepcopy(analysis), deepcopy(analysis)]) as analyze,
              patch("app.clm_identity_v2_dialog.collect_clm_identity_decisions",
                    side_effect=decisions),
              patch("app.clm_v2_classification_ui.collect_clm_character_classifications",
                    return_value={
                        ("1:102",): CharacterImportChoice(member_id="m1000")}),
               patch.object(ClmRaidReviewDialog, "exec",
                            side_effect=[QDialog.DialogCode.Accepted,
                                         QDialog.DialogCode.Rejected]),
              patch.object(checker_qt.QMessageBox, "question",
                           side_effect=AssertionError("Übernahme nach Abbruch")),
              patch.object(checker_qt.QMessageBox, "warning") as warning,
              patch.object(checker_qt.ClmDkpRefreshService,
                           "refresh_from_document",
                           side_effect=AssertionError("DKP darf nicht aktualisiert werden"))):
            self.window.refresh_raids_from_clm()
        warning.assert_not_called()
        self.assertEqual(analyze.call_count, 2)
        self.assertEqual(self.window.identity_v2_store.to_payload(), before)
        self.assertEqual(target.read_bytes(), file_before)
        self.assertIsNone(self.window._v2_dkp_snapshot)

    def test_raid_refresh_skips_test_raid_without_guid_review(self):
        analysis, target = self._raid_refresh_with_open_guid()
        from app.clm_v2_initialization_ui import ClmRaidReviewDialog

        before = self.window.identity_v2_store.to_payload()
        file_before = target.read_bytes()
        with (patch("app.clm_v2_initialization.analyze_clm_v2_selection",
                    return_value=deepcopy(analysis)) as analyze,
              patch("app.clm_identity_v2_dialog.collect_clm_identity_decisions",
                    side_effect=AssertionError("Übersprungene GUID gefragt")),
              patch.object(ClmRaidReviewDialog, "exec",
                           return_value=QDialog.DialogCode.Accepted) as review,
              patch.object(ClmRaidReviewDialog, "selected_raid_ids",
                           return_value=set()),
              patch.object(checker_qt.QMessageBox, "question",
                           return_value=checker_qt.QMessageBox.StandardButton.Yes),
              patch.object(checker_qt.QMessageBox, "warning") as warning,
              patch.object(checker_qt.ClmDkpRefreshService,
                           "refresh_from_document",
                           side_effect=AssertionError("DKP darf nicht aktualisiert werden"))):
            self.window.refresh_raids_from_clm()
        warning.assert_not_called()
        analyze.assert_called_once()
        review.assert_called_once()
        self.assertEqual(self.window.identity_v2_store.to_payload(), before)
        self.assertEqual(target.read_bytes(), file_before)

    def test_project_switch_restores_own_clm_config_without_reading_lua(self):
        first = IdentityV2Store.from_payload(self.store.to_payload())
        first.guildName, first.realm = "Bierstube", "Stitches"
        first.clmLuaPath = str(self.root / "ClassicLootManager.lua")
        first.clmDatabaseId = "exp0 alliance stitches bierstube"
        first.clmRosterId, first.clmRosterName = "10", "Bierstube"
        first_path = self.root / "Erste.ggc"
        save_new_identity_v2(first, first_path)
        second = IdentityV2Store.from_payload(self.store.to_payload())
        second.guildName, second.realm = "Andere Gilde", "Stitches"
        second.clmLuaPath = str(self.root / "missing" / "ClassicLootManager.lua")
        second.clmDatabaseId = "andere-datenbank"
        second.clmRosterId, second.clmRosterName = "anderes-roster", "Andere"
        second_path = self.root / "Zweite.ggc"
        save_new_identity_v2(second, second_path)
        self.assertFalse(self.open_path(first_path).called)
        self.window.refresh_dkp()
        self.assertIsNotNone(self.window._clm_refresh_service.cached_snapshot)
        with (patch("app.clm_refresh.load_saved_variables",
                    side_effect=AssertionError("Lua beim Projektwechsel gelesen")),
              patch("app.clm_v2_initialization.load_saved_variables",
                    side_effect=AssertionError("Lua beim Projektwechsel gelesen")),
              patch.object(checker_qt.QMessageBox, "question",
                           return_value=checker_qt.QMessageBox.StandardButton.Yes)):
            self.assertFalse(self.open_path(second_path).called)
        self.assertEqual(self.window.clm_path_edit.text(), second.clmLuaPath)
        self.assertEqual(self.window.clm_roster_combo.currentData(), "anderes-roster")
        self.assertIsNone(self.window._clm_refresh_service.cached_snapshot)
        self.assertIsNone(self.window._v2_dkp_snapshot)
        self.assertEqual(self.window._clm_dkp_by_member_id, {})

    def test_v2_dkp_history_reuses_table_and_separates_equal_names_by_member_id(self):
        store = IdentityV2Store(
            players=[Player("p1", "Erste"), Player("p2", "Zweite")],
            members=[Member("m1", "Sorap", "Mage", playerId="p1", clmGuid="g1"),
                     Member("m2", "Sorap", "Mage", playerId="p2", clmGuid="g2")],
            eternalDkpRecords=[
                EternalDkpRecord("d1", "e1", "m1", "g1", "award", 100,
                                 "2026-04-01T10:00:00", description="Primär"),
                EternalDkpRecord("d2", "e2", "m1", "g0", "award", 50,
                                 "2026-04-02T10:00:00", description="Historisch"),
                EternalDkpRecord("d3", "e3", "m2", "g2", "award", 80,
                                 "2026-04-03T10:00:00", description="Andere Inkarnation"),
            ],
            legacyClmGuidMemberMap={"g0": "m1"},
            pointMode="eternal_dkp",
        )
        target = self.root / "dkp-history-v2.ggc"
        save_new_identity_v2(store, target)
        with patch.object(checker_qt.ClmDkpRefreshService,
                          "refresh_for_project",
                          side_effect=AssertionError("Kein Lua-Replay beim Öffnen")):
            self.assertFalse(self.open_path(target).called)
        self.assertIsNotNone(self.window._v2_roster_by_id["m1"].dkpRank)
        self.window.switch_page("settings")
        self.assertFalse(self.window.clm_v2_history_button.isHidden())
        self.window.clm_v2_history_button.click()
        self.assertIs(self.window.raid_subtabs.currentWidget(),
                      self.window.dkp_history_page)
        self.window.dkp_history_mode.setCurrentIndex(
            self.window.dkp_history_mode.findData("character"))
        subjects = self.window.dkp_history_subject
        self.assertEqual([subjects.itemText(index) for index in range(subjects.count())],
                         ["Sorap", "Sorap"])
        self.assertEqual({subjects.itemData(index) for index in range(subjects.count())},
                         {"m1", "m2"})
        subjects.setCurrentIndex(subjects.findData("m1"))
        table = self.window.dkp_history_table
        self.assertEqual(table.rowCount(), 2)
        self.assertEqual({table.item(row, 2).data(int(Qt.ItemDataRole.UserRole) + 2)
                          for row in range(table.rowCount())}, {"m1"})
        self.assertEqual({table.item(row, 5).text() for row in range(table.rowCount())},
                         {"Primär", "Historisch"})
        subjects.setCurrentIndex(subjects.findData("m2"))
        self.assertEqual(table.rowCount(), 1)
        self.assertEqual(table.item(0, 5).text(), "Andere Inkarnation")
        self.assertTrue(self.window.set_v2_active_point_system("raid_points"))
        self.assertFalse(self.window.raid_subtabs.isTabVisible(
            self.window.raid_subtabs.indexOf(self.window.dkp_history_page)))
        self.assertFalse(self.window.clm_group.isHidden())
        self.assertEqual(self.window.identity_v2_store.eternalDkpRecords,
                         store.eternalDkpRecords)

    def test_open_v2_roster_without_technical_overview_and_exclusive_save_paths(self):
        self.assertFalse(self.open_path(self.target).called)
        self.assertEqual(self.window.project_mode, "identity_v2")
        self.assertEqual(self.window.identity_v2_project_path, self.target.resolve())
        self.assertEqual(self.window.v2_character_data_page.project_path,
                         self.target.resolve())
        self.assertEqual(self.window.identity_v2_store.to_payload(), self.store.to_payload())
        self.assertEqual(self.window.model.members, [])
        self.assertEqual(self.window.stack.currentWidget(),
                         self.window._pages["rooster"])
        self.assertNotIn("identity_v2", self.window._pages)
        self.assertFalse(hasattr(self.window, "v2_overview_button"))
        self.assertFalse(hasattr(self.window, "roster_variant_controls"))
        self.assertFalse(hasattr(self.window.player_profile_page, "variant_buttons"))
        self.assertEqual(list(self.window._nav_buttons),
                         ["rooster", "graveyard", "management", "raid", "settings"])
        tool_actions = [item.text() for heading in self.window.menuBar().actions()
                        if heading.menu() is not None
                        for item in heading.menu().actions()]
        self.assertNotIn(checker_qt.tr("checker.launch_legacy"), tool_actions)
        self.assertIn(checker_qt.tr("checker.launch_grabber"), tool_actions)
        self.assertTrue(self.window._nav_buttons["management"].isEnabled())
        before = self.window.identity_v2_store.to_payload()
        self.assertTrue(self.window.export_menu_action.isEnabled())
        self.assertTrue(self.window.package_export_menu_action.isEnabled())
        self.assertTrue(self.window.package_import_menu_action.isEnabled())
        self.assertTrue(self.window.roster_export_menu_action.isEnabled())
        self.window.switch_page("management")
        self.assertEqual(self.window.stack.currentWidget(),
                         self.window.v2_players_page)
        self.assertEqual(self.window.identity_v2_store.to_payload(), before)

        self.assertFalse(self.window.v2_management_tabs.isHidden())
        self.window.switch_page("identity_v2_character_data")
        self.assertIs(self.window.stack.currentWidget(),
                      self.window.v2_character_data_page)
        self.assertEqual(self.window.v2_character_data_page.store.to_payload(), before)
        self.assertFalse(self.window.identity_v2_dirty)
        character_page = self.window.v2_character_data_page
        character_page.search.setText("Annî")
        character_page._sort_by_column(0)
        character_page.details_button.setChecked(False)
        character_page.details_button.setChecked(True)
        self.assertFalse(self.window.identity_v2_dirty)
        self.assertEqual(self.window.identity_v2_store.to_payload(), before)
        self.window.switch_page("identity_v2_players")
        self.assertIs(self.window.stack.currentWidget(), self.window.v2_players_page)

        self.window.identity_v2_dirty = True
        self.window.refresh_project_label()
        with patch.object(checker_qt.QMessageBox, "question",
                          return_value=checker_qt.QMessageBox.StandardButton.No):
            self.assertFalse(self.window._confirm_discard())

        with patch.object(self.window.model, "save", side_effect=AssertionError("Legacy save")):
            self.window.save_project()
            copy = self.root / "Kopie_V2.ggc"
            with patch.object(checker_qt.QFileDialog, "getSaveFileName",
                              return_value=(str(copy), "")):
                self.window.save_project_as()
        self.assertEqual(self.window.identity_v2_project_path, copy.resolve())
        self.assertEqual(self.window.v2_character_data_page.project_path,
                         copy.resolve())
        self.assertEqual(load_identity_v2(copy).to_payload(), self.store.to_payload())
        self.assertFalse(self.window.identity_v2_dirty)

    def test_character_inline_edit_marks_dirty_without_autosaving_project(self):
        self.assertFalse(self.open_path(self.target).called)
        self.window.switch_page("identity_v2_character_data")
        page = self.window.v2_character_data_page
        before = self.target.read_bytes()
        member_id = page.visible_member_ids[0]
        row = page.visible_member_ids.index(member_id)
        page.table.setCurrentCell(row, 7)
        next_gear = ("Pre-BiS" if page.rows_by_id[member_id].gearStatus != "Pre-BiS"
                     else "BiS")
        with patch.object(self.window, "autosave") as autosave:
            page.table.item(row, 7).setData(Qt.ItemDataRole.EditRole, next_gear)
        self.assertFalse(autosave.called)
        self.assertTrue(self.window.identity_v2_dirty)
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(self.window.identity_v2_store.members[0].gearStatus, next_gear)
        self.window.save_project()
        self.assertEqual(load_identity_v2(self.target).members[0].gearStatus, next_gear)

    def test_character_death_marks_dirty_only_after_success_and_waits_for_save(self):
        self.assertFalse(self.open_path(self.target).called)
        self.window.switch_page("identity_v2_character_data")
        page = self.window.v2_character_data_page
        member_id = next(item.memberId for item in page.store.members
                         if item.lifeStatus == "active")
        page.table.setCurrentCell(page.visible_member_ids.index(member_id), 0)
        original_bytes = self.target.read_bytes()
        with patch.object(page, "_choose_death_details", return_value=None):
            self.assertFalse(page._request_death_for_member(member_id))
        self.assertFalse(self.window.identity_v2_dirty)
        self.assertEqual(self.target.read_bytes(), original_bytes)
        latest = max((date.fromisoformat(raid.date) for raid in page.store.raids),
                     default=date.today())
        with patch.object(page, "_choose_death_details", return_value=(latest, "individual")):
            page.mark_dead_button.click()
        self.assertTrue(self.window.identity_v2_dirty)
        self.assertEqual(self.target.read_bytes(), original_bytes)
        changed = next(item for item in self.window.identity_v2_store.members
                       if item.memberId == member_id)
        self.assertEqual((changed.lifeStatus, changed.deathDate),
                         ("dead", latest.isoformat()))
        self.assertIn(member_id, {item_id for item_id, _pixmap
                                  in self.window.grave_canvas._cards})
        self.assertIs(self.window.v2_players_page.store, self.window.identity_v2_store)
        self.window.save_project()
        saved = next(item for item in load_identity_v2(self.target).members
                     if item.memberId == member_id)
        self.assertEqual((saved.lifeStatus, saved.deathDate),
                         ("dead", latest.isoformat()))
        saved_bytes = self.target.read_bytes()
        index = page.burial_choice.findData("collective")
        page.burial_choice.setCurrentIndex(index)
        page.burial_choice.activated.emit(index)
        self.assertTrue(self.window.identity_v2_dirty)
        self.assertEqual(self.target.read_bytes(), saved_bytes)
        self.assertEqual(next(item.burialType for item in self.window.identity_v2_store.members
                              if item.memberId == member_id), "collective")
        self.window.save_project()
        self.assertEqual(next(item.burialType for item in load_identity_v2(self.target).members
                              if item.memberId == member_id), "collective")

    def test_death_corrections_refresh_cemetery_and_save_only_explicitly(self):
        self.assertFalse(self.open_path(self.target).called)
        page = self.window.v2_character_data_page
        member_id = next(item.memberId for item in page.store.members
                         if item.lifeStatus == "active")
        latest = max((date.fromisoformat(raid.date) for raid in page.store.raids),
                     default=date.today())
        with patch.object(page, "_choose_death_details", return_value=(latest, "individual")):
            self.assertTrue(page._request_death_for_member(member_id))
        self.window.save_project()
        self.assertFalse(self.window.identity_v2_dirty)
        saved_bytes = self.target.read_bytes()
        with patch.object(page, "_choose_corrected_death_date", return_value=latest):
            self.assertFalse(page._request_death_date_correction(member_id))
        with patch.object(page, "_choose_clear_death_status", return_value=None):
            self.assertFalse(page._request_clear_death_marking(member_id))
        self.assertFalse(self.window.identity_v2_dirty)
        self.assertEqual(self.target.read_bytes(), saved_bytes)
        corrected = latest + timedelta(days=1)
        with (patch.object(page, "_choose_corrected_death_date", return_value=corrected),
              patch.object(checker_qt.QMessageBox, "information")):
            self.assertTrue(page._request_death_date_correction(member_id))
        self.assertTrue(self.window.identity_v2_dirty)
        self.assertEqual(self.target.read_bytes(), saved_bytes)
        self.assertEqual(next(item.deathDate for item in self.window.identity_v2_store.members
                              if item.memberId == member_id), corrected.isoformat())
        with (patch.object(page, "_choose_clear_death_status", return_value="inactive"),
              patch.object(checker_qt.QMessageBox, "information")):
            self.assertTrue(page._request_clear_death_marking(member_id))
        self.assertTrue(self.window.identity_v2_dirty)
        self.assertEqual(self.target.read_bytes(), saved_bytes)
        self.assertNotIn(member_id, {item_id for item_id, _ in self.window.grave_canvas._cards})
        self.assertIs(page.store, self.window.identity_v2_store)
        self.assertIs(self.window.v2_players_page.store, self.window.identity_v2_store)
        self.window.save_project()
        self.assertFalse(self.window.identity_v2_dirty)
        restored = next(item for item in load_identity_v2(self.target).members
                        if item.memberId == member_id)
        self.assertEqual((restored.lifeStatus, restored.deathDate, restored.burialType),
                         ("inactive", None, None))

    def test_v2_matrix_reuses_existing_tables_and_keeps_store_read_only(self):
        target = self.root / "matrix-v2.ggc"
        source = self._prepared(matrix_sample_store())
        save_new_identity_v2(source, target)
        before = target.read_bytes()
        self.assertFalse(self.open_path(target).called)
        self.window.switch_page("raid")
        self.assertIs(self.window.stack.currentWidget(), self.window._pages["raid"])
        self.window.switch_page("identity_v2_matrix")
        self.assertIs(self.window.stack.currentWidget(), self.window._pages["raid"])
        self.assertIs(self.window.raid_matrix_table.parent(),
                      self.window.attendance_matrix_split)
        self.window.v2_matrix_raid_button.click()
        self.window.v2_matrix_status_button.click()
        self.assertEqual(self.window.raid_stats_table.columnCount(), 9)
        self.assertEqual(self.window.raid_matrix_table.columnCount(), 7)
        self.assertEqual(self.window.raid_stats_table.rowCount(), 1)
        self.assertEqual(self.window._matrix_players[0]["identifier"], "p1")
        r2 = next(index for index, column in enumerate(self.window._matrix_raids)
                  if column.id == "r2")
        item = self.window.raid_matrix_table.item(0, r2)
        self.assertEqual(item.text(), "✓")
        self.assertIn("Priester", item.toolTip())
        colors = {column.id: self.window.raid_matrix_table.item(0, index)
                  .background().color().name()
                  for index, column in enumerate(self.window._matrix_raids)}
        self.assertEqual((colors["r2"], colors["r1"], colors["r3"], colors["r0"]),
                         ("#248447", "#b18420", "#11161d", "#59616a"))
        self.window.v2_matrix_class_button.click()
        self.assertEqual(self.window.raid_matrix_table.item(0, r2).background().color().name(),
                         checker_qt.CLASS_COLORS["Priest"].lower())
        self.window.v2_matrix_day_button.click()
        self.assertEqual(self.window.raid_matrix_table.columnCount(), 6)
        day = next(index for index, column in enumerate(self.window._matrix_raids)
                   if column.id == "2026-01-02")
        self.assertIn("2 / 2", self.window.raid_matrix_table.item(0, day).toolTip())
        self.assertEqual(self.window.raid_matrix_table.item(0, day).background().color().name(),
                         checker_qt.CLASS_COLORS["Priest"].lower())
        self.window.matrix_view_character_button.click()
        self.assertEqual(self.window.raid_stats_table.columnCount(), 10)
        self.assertEqual({row["identifier"] for row in self.window._matrix_players},
                         {"m1", "m2", "m3", "m4"})
        successor_row = next(index for index, row in enumerate(self.window._matrix_players)
                             if row["identifier"] == "m3")
        successor_day = next(index for index, column in enumerate(self.window._matrix_raids)
                             if column.id == "2026-01-04")
        self.assertEqual(self.window.raid_matrix_table.item(
            successor_row, successor_day).background().color().name(),
            checker_qt.CLASS_COLORS["Warlock"].lower())
        with patch.object(self.window._v2_attendance_adapter, "subjects",
                          side_effect=AssertionError("Projection was recalculated")):
            self.window.v2_matrix_status_button.click()
            self.window.v2_matrix_class_button.click()
            self.window.refresh_raid_matrix()
        dead_row = next(index for index, row in enumerate(self.window._matrix_players)
                        if row["identifier"] == "m1")
        self.assertIn("☠", self.window.raid_stats_table.item(dead_row, 0).text())
        self.window.raid_stats_table.setColumnWidth(0, 233)
        self.window.raid_stats_table.horizontalHeader().sectionClicked.emit(0)
        self.app.processEvents()
        order_before = [row["identifier"] for row in self.window._matrix_players]
        changed = matrix_sample_store()
        changed.members[3].name = "A-Gleich"
        changed.validate()
        self.window._set_v2_attendance_store(changed)
        self.assertEqual([row["identifier"] for row in self.window._matrix_players],
                         order_before)
        self.assertEqual(self.window.raid_stats_table.columnWidth(0), 233)
        self.assertEqual(self.window._v2_matrix_fixed_widths["character:0"], 233)
        self.assertFalse(self.window.identity_v2_dirty)
        self.assertEqual(target.read_bytes(), before)
        self.window.v2_matrix_back_button.click()
        self.assertIs(self.window.stack.currentWidget(), self.window._pages["raid"])
        self.assertIs(self.window.raid_subtabs.currentWidget(), self.window.raids_page)
        self.window._set_project_mode("legacy")
        self.assertTrue(self.window.raid_subtabs.isTabVisible(0))
        self.assertTrue(self.window.raid_subtabs.isTabVisible(1))
        self.assertFalse(self.window.v2_matrix_options.isVisible())
        with (patch.object(checker_qt, "update_suite_settings") as settings,
              patch.object(checker_qt.QMessageBox, "question",
                           return_value=checker_qt.QMessageBox.StandardButton.Yes)):
            self.window.close()
        saved = settings.call_args.kwargs
        self.assertEqual((saved["identity_v2_matrix_level"],
                          saved["identity_v2_matrix_grouping"],
                          saved["identity_v2_matrix_colors"]),
                         ("character", "day", "class"))
        self.assertEqual(saved["identity_v2_matrix_fixed_widths"]["character:0"], 233)

    def test_v2_points_use_existing_adjustment_dialog_and_refresh_without_autosave(self):
        target = self.root / "points-v2.ggc"
        source = self._prepared(point_store())
        save_new_identity_v2(source, target)
        original_bytes = target.read_bytes()
        self.assertFalse(self.open_path(target).called)
        self.assertEqual(self.window._v2_raid_point_projection.player_points("p1"), 40)
        page = self.window.v2_character_data_page
        page.table.setCurrentCell(page.visible_member_ids.index("m2"), 0)
        self.assertEqual(page.detail_values["raid_points"].text(), "20")
        self.assertEqual(page.detail_values["eternal_raid_points"].text(), "20")
        with patch.object(MemberSpecialPointsDialog, "exec",
                          return_value=QDialog.DialogCode.Rejected):
            self.assertFalse(page._edit_special_points())
        with patch.object(MemberSpecialPointsDialog, "exec",
                          return_value=QDialog.DialogCode.Accepted):
            self.assertFalse(page._edit_special_points())
        self.assertFalse(self.window.identity_v2_dirty)

        def add_special(dialog):
            dialog._add_row(None, 7, "Ersatz")
            return QDialog.DialogCode.Accepted

        with patch.object(MemberSpecialPointsDialog, "exec", new=add_special):
            self.assertTrue(page._edit_special_points())
        self.assertTrue(self.window.identity_v2_dirty)
        self.assertEqual(target.read_bytes(), original_bytes)
        self.assertEqual(page.detail_values["raid_points"].text(), "27")
        self.assertEqual(self.window._v2_raid_point_projection.player_points("p1"), 47)
        self.assertEqual(self.window.identity_v2_store.attendance, source.attendance)
        self.assertEqual(self.window.identity_v2_store.raids, source.raids)
        page.point_history_button.click()
        self.assertIs(self.window.raid_subtabs.currentWidget(),
                      self.window.point_history_page)
        self.assertEqual(self.window.point_history_subject.currentData(), "m2")
        self.assertEqual(self.window.point_history_table.rowCount(), 4)
        self.assertIn("Sonderpunkte", [
            self.window.point_history_table.item(row, 1).text()
            for row in range(self.window.point_history_table.rowCount())])

        players = self.window.v2_players_page
        player_row = next(row for row in range(players.player_table.rowCount())
                          if players.player_table.item(row, 0).data(
                              Qt.ItemDataRole.UserRole) == "p1")
        players.player_table.selectRow(player_row)
        self.assertEqual(players.findChild(QLabel, "v2PlayerRaidPoints").text(), "47")
        self.assertEqual(players.findChild(QLabel, "v2PlayerEternalPoints").text(), "47")
        players.findChild(QPushButton, "v2PlayerPointHistoryButton").click()
        self.assertEqual(self.window.point_history_subject.currentData(), "p1")
        self.assertEqual(self.window.point_history_table.rowCount(), 9)
        self.window.save_project()
        self.assertFalse(self.window.identity_v2_dirty)
        saved_bytes = target.read_bytes()
        self.assertEqual(V2RaidPointProjection(load_identity_v2(target)).player_points("p1"), 47)

        self.window.switch_page("raid")
        raid_table = self.window.raid_table
        raid_row = next(row for row in range(raid_table.rowCount())
                        if raid_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == "r20")
        raid_table.selectRow(raid_row)

        def edit_raid(dialog):
            entry, spin, reason, _total = next(
                row for row in dialog._editors if row[0].id == "a1")
            spin.setValue(-2)
            reason.setText("Verspätet")
            return QDialog.DialogCode.Accepted

        with patch.object(checker_qt.RaidPointAdjustmentDialog, "exec", new=edit_raid):
            self.assertTrue(self.window._adjust_v2_raid_points())
        self.assertEqual(self.window._v2_raid_point_projection.player_points("p1"), 45)
        self.assertEqual(self.window.identity_v2_store.attendance, source.attendance)
        self.assertEqual(target.read_bytes(), saved_bytes)
        count = len(self.window._v2_raid_point_projection.history)
        self.assertTrue(self.window._rebuild_v2_raid_points())
        self.assertEqual(len(self.window._v2_raid_point_projection.history), count)
        self.assertEqual(self.window._v2_raid_point_projection.player_points("p1"), 45)
        self.assertTrue(self.window.identity_v2_dirty)
        self.assertEqual(target.read_bytes(), saved_bytes)
        self.window.save_project()
        self.assertEqual(V2RaidPointProjection(load_identity_v2(target)).player_points("p1"), 45)
        from app.identity_v2_character_service import set_member_note
        cached = self.window._v2_raid_point_projection
        unrelated = set_member_note(self.window.identity_v2_store, "m1", "Neue Notiz")
        self.window._apply_v2_character_store(unrelated)
        self.assertIs(self.window._v2_raid_point_projection, cached)

    def test_v2_unknown_raid_point_type_is_visible_without_import_or_save(self):
        target = self.root / "unknown-points-v2.ggc"
        source = self._prepared(point_store())
        source.raids[0].raidType = "Unbekannt"
        source.validate()
        save_new_identity_v2(source, target)
        original_bytes = target.read_bytes()
        self.assertFalse(self.open_path(target).called)
        self.assertIsNone(self.window._v2_raid_point_projection)
        self.assertIn("Unbekannt", self.window.v2_raid_page.points_status_label.text())
        self.assertFalse(self.window.v2_raid_page.adjust_points_button.isEnabled())
        self.assertFalse(self.window.identity_v2_dirty)
        self.assertEqual(target.read_bytes(), original_bytes)

    def test_v2_player_points_values_stay_visible_and_follow_selection(self):
        target = self.root / "player-points-v2.ggc"
        source = self._prepared(point_store())
        save_new_identity_v2(source, target)
        before = target.read_bytes()
        self.assertFalse(self.open_path(target).called)
        self.window.switch_page("identity_v2_players")
        page = self.window.v2_players_page
        projection = self.window._v2_raid_point_projection

        def select(player_id):
            row = next(row for row in range(page.player_table.rowCount())
                       if page.player_table.item(row, 0).data(
                           Qt.ItemDataRole.UserRole) == player_id)
            page.player_table.selectRow(row)
            form = next(item.layout() for item in (
                page.detail_layout.itemAt(index)
                for index in range(page.detail_layout.count()))
                if isinstance(item.layout(), QFormLayout))
            self.assertEqual(form.rowCount(), 6)
            values = tuple(form.itemAt(index, QFormLayout.ItemRole.FieldRole).widget()
                           for index in range(2))
            self.assertEqual([value.objectName() for value in values],
                             ["v2PlayerRaidPoints", "v2PlayerEternalPoints"])
            self.assertTrue(all(form.labelForField(value) is not None
                                for value in values))
            ranks = tuple(form.itemAt(index, QFormLayout.ItemRole.FieldRole).widget()
                          for index in range(2, 6))
            self.assertEqual([value.objectName() for value in ranks],
                             ["v2PlayerAvailableDkp", "v2PlayerEternalDkp",
                              "v2PlayerDkpRank",
                              "v2PlayerRaidRank"])
            self.assertTrue(all(form.labelForField(value) is not None
                                for value in ranks))
            self.assertTrue(all(form.isRowVisible(value) for value in values))
            self.assertFalse(any(form.isRowVisible(value) for value in ranks[:3]))
            self.assertTrue(form.isRowVisible(ranks[3]))
            return tuple(value.text() for value in values)

        self.assertEqual(select("p1"), ("40", "40"))
        self.assertEqual(select("p2"), ("0", "0"))
        self.assertEqual(select("p1"), ("40", "40"))
        self.assertIs(self.window._v2_raid_point_projection, projection)
        from app.identity_v2_raid_points import apply_v2_member_special_points
        changed = apply_v2_member_special_points(
            self.window.identity_v2_store, "m2", 7, "Ersatz")
        self.window._apply_v2_points_store(changed)
        self.assertEqual(select("p1"), ("47", "47"))
        self.assertEqual(select("p2"), ("0", "0"))
        self.assertEqual(target.read_bytes(), before)
        self.assertTrue(self.window.identity_v2_dirty)

    def test_successor_selection_refreshes_all_v2_views_without_autosave(self):
        multi = self._prepared(character_sample_store())
        multi.members[2].playerId = "p1"
        multi.validate()
        target = self.root / "Nachfolge_V2.ggc"
        save_new_identity_v2(multi, target)
        self.assertFalse(self.open_path(target).called)
        self.window.switch_page("identity_v2_character_data")
        page = self.window.v2_character_data_page
        page.table.setCurrentCell(page.visible_member_ids.index("m1"), 0)
        original_bytes = target.read_bytes()
        with (patch.object(page, "_choose_death_details",
                           return_value=(date(2026, 2, 1), "individual")),
              patch.object(page, "_choose_main_successor", return_value="m3") as choose):
            page.mark_dead_button.click()
        choose.assert_called_once()
        store = self.window.identity_v2_store
        self.assertEqual(store.players[0].mainMemberId, "m3")
        self.assertEqual(store.players[0].mainHistory[0].memberId, "m1")
        self.assertIs(page.store, store)
        self.assertIs(self.window.v2_players_page.store, store)
        self.assertIn("m1", {member_id for member_id, _pixmap
                              in self.window.grave_canvas._cards})
        self.assertTrue(self.window.identity_v2_dirty)
        self.assertEqual(target.read_bytes(), original_bytes)

    def test_canceled_successor_selection_keeps_project_and_views_clean(self):
        multi = self._prepared(character_sample_store())
        multi.members[2].playerId = "p1"
        multi.validate()
        target = self.root / "Abbruch_V2.ggc"
        save_new_identity_v2(multi, target)
        self.assertFalse(self.open_path(target).called)
        self.window.switch_page("identity_v2_character_data")
        page = self.window.v2_character_data_page
        page.table.setCurrentCell(page.visible_member_ids.index("m1"), 0)
        before = self.window.identity_v2_store.to_payload()
        original_bytes = target.read_bytes()
        with (patch.object(page, "_choose_death_details",
                           return_value=(date(2026, 2, 1), "collective")),
              patch.object(page, "_choose_main_successor", return_value=None) as choose):
            page.mark_dead_button.click()
        choose.assert_called_once()
        self.assertEqual(self.window.identity_v2_store.to_payload(), before)
        self.assertEqual(page.store.to_payload(), before)
        self.assertEqual(self.window.v2_players_page.store.to_payload(), before)
        self.assertFalse(self.window.identity_v2_dirty)
        self.assertEqual(target.read_bytes(), original_bytes)

    def test_main_history_apply_marks_dirty_once_and_survives_save_reload(self):
        source = self._prepared(main_history_sample_store())
        target = self.root / "Main_History_V2.ggc"
        save_new_identity_v2(source, target)
        self.assertFalse(self.open_path(target).called)
        self.window.switch_page("identity_v2_players")
        page = self.window.v2_players_page
        row = next(index for index in range(page.player_table.rowCount())
                   if page.player_table.item(index, 0).data(Qt.ItemDataRole.UserRole)
                   == "p1")
        page.player_table.setCurrentCell(row, 0)
        original_bytes = target.read_bytes()
        original_attendance = source.to_payload()["attendance"]
        original_guids = source.to_payload()["legacyClmGuidMemberMap"]

        def apply(dialog):
            dialog.new_button.click()
            dialog.member_combo.setCurrentIndex(dialog.member_combo.findData("m1001"))
            dialog.stage_button.click()
            dialog.main_since.unknown.setChecked(True)
            dialog._apply_draft()
            return dialog.result()

        with patch.object(MainHistoryDialog, "exec", new=apply):
            page.findChild(QPushButton, "mainHistoryButton").click()
        store = self.window.identity_v2_store
        self.assertTrue(self.window.identity_v2_dirty)
        self.assertEqual(target.read_bytes(), original_bytes)
        self.assertEqual(store.players[0].mainMemberId, "m1000")
        self.assertIsNone(store.players[0].mainSinceDate)
        self.assertEqual((store.players[0].mainHistory[0].memberId,
                          store.players[0].mainHistory[0].source),
                         ("m1001", "manual"))
        self.assertEqual(store.to_payload()["attendance"], original_attendance)
        self.assertEqual(store.to_payload()["legacyClmGuidMemberMap"], original_guids)
        self.window.save_project()
        restored = load_identity_v2(target)
        self.assertEqual(restored.to_payload(), store.to_payload())

    def test_invalid_or_unmarked_project_keeps_current_v2_project(self):
        self.assertFalse(self.open_path(self.target).called)
        active = self.window.identity_v2_store
        invalid = self.root / "Ungueltig_V2.ggc"
        payload = self.store.to_payload()
        payload["attendance"][0]["memberId"] = "nicht-vorhanden"
        invalid.write_text(json.dumps(payload), encoding="utf-8")
        self.assertTrue(self.open_path(invalid).called)
        self.assertIs(self.window.identity_v2_store, active)
        self.assertEqual(self.window.identity_v2_project_path, self.target.resolve())
        self.assertEqual(self.window.project_mode, "identity_v2")

        unmarked = self.root / "Unmarkiert.ggc"
        unmarked.write_text(json.dumps(self.window.model.to_payload()), encoding="utf-8")
        self.assertTrue(self.open_path(unmarked).called)
        self.assertEqual(self.window.project_mode, "identity_v2")
        self.assertIs(self.window.identity_v2_store, active)
        self.assertEqual(self.window.identity_v2_project_path, self.target.resolve())
        self.assertTrue(self.window._nav_buttons["management"].isEnabled())
        self.window.switch_page("rooster")
        self.assertIs(self.window.stack.currentWidget(), self.window._pages["rooster"])
        self.window.switch_page("raid")
        self.assertIs(self.window.stack.currentWidget(), self.window._pages["raid"])
        self.assertNotIn("identityFormat", json.loads(unmarked.read_text(encoding="utf-8")))

    def test_v2_navigation_uses_roster_players_and_raid_pages(self):
        self.assertFalse(self.open_path(self.target).called)
        self.assertTrue(self.window._nav_buttons["rooster"].isEnabled())
        self.assertTrue(self.window._nav_buttons["raid"].isEnabled())
        self.window.switch_page("rooster")
        self.assertIs(self.window.stack.currentWidget(), self.window._pages["rooster"])
        self.assertIs(self.window.roster_content_stack.currentWidget(),
                      self.window.roster_scroll)
        self.assertEqual(len(self.window._roster_cards), sum(
            member.lifeStatus == "active" for member in self.store.members))
        self.window._set_roster_view("list")
        self.assertIs(self.window.roster_content_stack.currentWidget(),
                      self.window.v2_roster_page)
        self.assertEqual(self.window.v2_roster_page.table.rowCount(), sum(
            member.lifeStatus == "active" for member in self.store.members))
        self.window.switch_page("raid")
        self.assertIs(self.window.stack.currentWidget(), self.window._pages["raid"])
        self.assertIs(self.window.raid_subtabs.currentWidget(), self.window.raids_page)
        self.assertEqual(self.window.raid_table.columnCount(), 6)
        self.assertEqual(self.window.raid_table.rowCount(), len(self.store.raids))
        self.assertEqual(self.window.raid_participants_table.columnCount(), 7)
        self.window.switch_page("management")
        self.assertIs(self.window.stack.currentWidget(), self.window.v2_players_page)
        self.window.switch_page("identity_v2")
        self.assertIs(self.window.stack.currentWidget(),
                      self.window._pages["identity_v2"])
        self.assertEqual(self.window.identity_v2_store.to_payload(), self.store.to_payload())

    def test_v2_raid_uses_old_tabs_table_wcl_and_active_point_mode(self):
        store = IdentityV2Store(
            players=[Player("p1", "Spieler", "m1")],
            members=[Member("m1", "Held", "Mage", playerId="p1")],
            raids=[Raid("r1", "2026-04-01", name="MC Abend", raidType="MC",
                        clmRaidId="clm-1", csvSourceFiles=("MC.csv",),
                        csvReportUrls=("https://vanilla.warcraftlogs.com/reports/AAA",))],
            attendance=[Attendance("a1", "r1", "m1", "main", playerId="p1")],
            pointMode="eternal_dkp",
        )
        target = self.root / "raid-layout-v2.ggc"
        save_new_identity_v2(store, target)
        before_file = target.read_bytes()
        self.assertFalse(self.open_path(target).called)
        self.window.switch_page("raid")
        self.assertIs(self.window.stack.currentWidget(), self.window._pages["raid"])
        self.assertIs(self.window.raid_subtabs.currentWidget(), self.window.raids_page)
        visible_tabs = [self.window.raid_subtabs.tabText(index)
                        for index in range(self.window.raid_subtabs.count())
                        if self.window.raid_subtabs.isTabVisible(index)]
        self.assertEqual(visible_tabs, ["Raids", "Teilnahme", "DKP-Historie"])
        self.assertEqual(self.window.raid_table.columnCount(), 6)
        self.assertEqual(self.window.raid_table.rowCount(), 1)
        self.assertEqual([self.window.raid_table.horizontalHeaderItem(index).text()
                          for index in range(6)],
                         [checker_qt.tr(key) for key in (
                             "common.date", "raids.raid_type", "raids.raid",
                             "raids.participants", "common.status",
                             "raids.warcraft_logs")])
        self.assertEqual(self.window.raid_table.item(0, 0).data(
            Qt.ItemDataRole.UserRole), "r1")
        self.assertTrue(self.window.raid_header_logs.isVisible()
                        or not self.window.isVisible())
        self.assertEqual(self.window.raid_participants_table.rowCount(), 1)
        self.assertEqual(self.window.raid_participants_table.columnCount(), 6)
        self.assertEqual(self.window.raid_participants_table.horizontalHeaderItem(4).text(),
                         checker_qt.tr("raid_clm_admin.eternal_dkp"))
        character = self.window.raid_participants_table.item(0, 1)
        self.assertEqual(character.data(Qt.ItemDataRole.UserRole), "m1")
        self.assertFalse(character.icon().isNull())
        self.assertEqual(character.foreground().color().name(),
                         checker_qt.CLASS_COLORS["Mage"].lower())
        with patch.object(checker_qt.webbrowser, "open_new_tab") as browser:
            self.window._raid_table_clicked(0, 5)
            browser.assert_called_once_with(
                "https://vanilla.warcraftlogs.com/reports/AAA")
        with patch.object(checker_qt.webbrowser, "open_new_tab") as browser:
            self.window.raid_header_logs.click()
            browser.assert_called_once_with(
                "https://vanilla.warcraftlogs.com/reports/AAA")
        with patch.object(self.window, "analyze_v2_csv_files") as import_csv:
            self.window.raid_bulk_import_button.click()
            import_csv.assert_called_once()
        self.window.switch_page("identity_v2_matrix")
        self.assertIs(self.window.raid_subtabs.currentWidget(),
                      self.window.attendance_page)
        self.window._matrix_raid_clicked(0)
        self.assertIs(self.window.raid_subtabs.currentWidget(), self.window.raids_page)
        self.assertEqual(self.window._selected_raid().id, "r1")
        self.window.switch_page("raid")
        self.assertIs(self.window.raid_subtabs.currentWidget(), self.window.raids_page)
        self.assertTrue(self.window.set_v2_active_point_system("raid_points"))
        visible_tabs = [self.window.raid_subtabs.tabText(index)
                        for index in range(self.window.raid_subtabs.count())
                        if self.window.raid_subtabs.isTabVisible(index)]
        self.assertEqual(visible_tabs,
                         ["Raids", "Teilnahme", "Raidpunkte-Historie"])
        self.assertEqual(self.window.raid_participants_table.columnCount(), 7)
        self.assertEqual(self.window.raid_participants_table.horizontalHeaderItem(4).text(),
                         checker_qt.tr("raid_points.base"))
        self.assertEqual(target.read_bytes(), before_file)

    def test_v2_old_raid_dialogs_create_edit_bench_toggle_reset_delete(self):
        store = IdentityV2Store(
            players=[Player("p1", "Eins", "m1"), Player("p2", "Zwei", "m2")],
            members=[Member("m1", "Eins", "Mage", playerId="p1"),
                     Member("m2", "Zwei", "Priest", playerId="p2")],
            raids=[Raid("r1", "2026-04-01", name="CLM", raidType="MC",
                        clmRaidId="clm-1")],
            attendance=[Attendance("a1", "r1", "m1", "main", playerId="p1")],
        )
        target = self.root / "raid-actions-v2.ggc"
        save_new_identity_v2(store, target)
        before_file = target.read_bytes()
        self.assertFalse(self.open_path(target).called)
        self.window.switch_page("raid")

        def create(dialog):
            self.assertTrue(dialog.v2_mode)
            self.assertFalse(hasattr(dialog, "csv_path_label"))
            self.assertGreaterEqual(dialog.raid_type_combo.minimumHeight(),
                                    dialog.raid_type_combo.fontMetrics().height() + 16)
            dialog.date_edit.setText("2026-04-02")
            dialog.raid_type_combo.setCurrentIndex(
                dialog.raid_type_combo.findData("BWL"))
            dialog.name_edit.setText("Neuer Raid")
            self.assertTrue(dialog.save_button.isEnabled())
            return QDialog.DialogCode.Accepted

        with patch.object(checker_qt.RaidEditorDialog, "exec", new=create):
            self.window.raid_create_button.click()
        self.assertEqual(len(self.window.identity_v2_store.raids), 2)
        created_id = self.window._selected_raid().id
        self.assertNotEqual(created_id, "r1")
        self.assertTrue(self.window.identity_v2_dirty)
        self.assertEqual(target.read_bytes(), before_file)
        self.assertTrue(self.window._select_raid_row("r1"))

        def edit(dialog):
            self.assertTrue(dialog.v2_mode)
            self.assertEqual(dialog.raid.id, "r1")
            self.assertTrue(dialog.bench_button.isEnabled())
            with (patch.object(checker_qt.BenchPlayersDialog, "exec",
                               return_value=QDialog.DialogCode.Accepted),
                  patch.object(checker_qt.BenchPlayersDialog,
                               "selected_player_ids", return_value={"p2"})):
                dialog.bench_button.click()
            self.assertEqual(dialog.bench_values(), ["p2"])
            dialog.name_edit.setText("CLM bearbeitet")
            return QDialog.DialogCode.Accepted

        with patch.object(checker_qt.RaidEditorDialog, "exec", new=edit):
            self.window.raid_edit_button.click()
        entries = [entry for entry in self.window.identity_v2_store.attendance
                   if entry.raidId == "r1"]
        self.assertEqual({(entry.memberId, entry.status) for entry in entries},
                         {("m1", "present"), ("m2", "bench")})
        self.assertEqual(len(entries), 2)
        self.assertEqual(self.window._selected_raid().name, "CLM bearbeitet")
        bench_row = next(row for row in range(
            self.window.raid_participants_table.rowCount())
            if self.window.raid_participants_table.item(row, 1).data(
                Qt.ItemDataRole.UserRole) == "m2")
        self.window.raid_participants_table.selectRow(bench_row)
        self.window.raid_toggle_bench_button.click()
        self.assertEqual(next(entry.status for entry in
                              self.window.identity_v2_store.attendance
                              if entry.memberId == "m2"), "present")
        self.window.raid_participants_table.selectRow(bench_row)
        self.window.raid_toggle_bench_button.click()
        self.assertEqual(next(entry.status for entry in
                              self.window.identity_v2_store.attendance
                              if entry.memberId == "m2"), "bench")
        self.assertEqual(len([entry for entry in
                              self.window.identity_v2_store.attendance
                              if entry.raidId == "r1"]), 2)
        with patch.object(checker_qt.QMessageBox, "question",
                          return_value=checker_qt.QMessageBox.StandardButton.Yes):
            self.window.raid_reset_button.click()
        self.assertEqual(self.window._selected_raid().id, "r1")
        self.assertFalse(any(entry.raidId == "r1"
                             for entry in self.window.identity_v2_store.attendance))
        with patch.object(checker_qt.QMessageBox, "question",
                          return_value=checker_qt.QMessageBox.StandardButton.Yes):
            self.window.raid_delete_button.click()
        self.assertFalse(any(raid.raidId == "r1"
                             for raid in self.window.identity_v2_store.raids))
        self.assertEqual(target.read_bytes(), before_file)

    def test_v2_player_action_marks_dirty_refreshes_views_and_saves_only_on_request(self):
        self.assertFalse(self.open_path(self.target).called)
        before_file = self.target.read_bytes()
        self.window.switch_page("management")
        page = self.window.v2_players_page
        self.assertEqual(page.unassigned_table.rowCount(), len(self.store.members))
        page.create_button.click()
        self.assertTrue(self.window.identity_v2_dirty)
        self.assertEqual(len(self.window.identity_v2_store.players), 1)
        self.window.switch_page("rooster")
        self.window._set_roster_view("list")
        self.assertEqual(self.window.v2_roster_page.table.rowCount(), sum(
            member.lifeStatus == "active" for member in self.store.members))
        self.assertEqual(self.window.v2_raid_page.raid_table.rowCount(), len(self.store.raids))
        self.assertEqual(self.target.read_bytes(), before_file)
        self.window.save_project()
        self.assertFalse(self.window.identity_v2_dirty)
        self.assertEqual(load_identity_v2(self.target).to_payload(),
                         self.window.identity_v2_store.to_payload())

    def test_v2_player_cancel_and_failed_service_do_not_mark_dirty(self):
        from app.identity_v2_player_service import PlayerMembershipError

        self.assertFalse(self.open_path(self.target).called)
        self.window.switch_page("management")
        page = self.window.v2_players_page
        for row in range(page.unassigned_table.rowCount()):
            page.unassigned_table.item(row, 0).setCheckState(Qt.CheckState.Checked)
        before = self.window.identity_v2_store.to_payload()
        before_file = self.target.read_bytes()
        with patch.object(checker_qt.QMessageBox, "question",
                          return_value=checker_qt.QMessageBox.StandardButton.No):
            page.bulk_create_button.click()
        self.assertEqual(self.window.identity_v2_store.to_payload(), before)
        self.assertFalse(self.window.identity_v2_dirty)
        page._clear_visible_selection()
        page.unassigned_table.setCurrentCell(0, 1)
        with (patch("app.identity_v2_players_qt.create_player_from_member",
                    side_effect=PlayerMembershipError("Testfehler")),
              patch.object(checker_qt.QMessageBox, "warning") as warning):
            page.create_button.click()
        self.assertTrue(warning.called)
        self.assertEqual(self.window.identity_v2_store.to_payload(), before)
        self.assertFalse(self.window.identity_v2_dirty)
        self.assertEqual(self.target.read_bytes(), before_file)

    def test_v2_raid_page_bulk_csv_action_keeps_store_and_save_unchanged(self):
        from app.csv_v2_analysis_ui import CsvV2AnalysisDialog

        self.assertFalse(self.open_path(self.target).called)
        first = self.root / "2026-07-01_MC_Casts.csv"
        second = self.root / "2026-07-02_BWL_Casts.csv"
        for path in (first, second):
            path.write_text('"Name","Amount"\n"Annî","1"\n', encoding="utf-8")
        before_store = self.window.identity_v2_store.to_payload()
        before_save = self.target.read_bytes()
        with (patch.object(checker_qt.QFileDialog, "getOpenFileNames",
                           return_value=([str(first), str(second)], "")),
              patch.object(CsvV2AnalysisDialog, "exec",
                           return_value=checker_qt.QDialog.DialogCode.Accepted),
              patch.object(checker_qt.QMessageBox, "critical") as error_dialog):
            self.window.v2_raid_page.analyze_csv_button.click()
        self.assertFalse(error_dialog.called, error_dialog.call_args)
        self.assertEqual(len(self.window.csv_v2_import_plan.raid_candidates), 2)
        self.assertEqual(self.window.identity_v2_store.to_payload(), before_store)
        self.assertEqual(self.target.read_bytes(), before_save)
        self.assertFalse(self.window.identity_v2_dirty)

    def test_v2_csv_review_cancel_retains_no_plan_or_changes(self):
        from app.csv_v2_analysis_ui import CsvV2AnalysisDialog

        self.assertFalse(self.open_path(self.target).called)
        source = self.root / "2026-07-01_MC_Casts.csv"
        source.write_text('"Name","Amount"\n"Annî","1"\n', encoding="utf-8")
        before_store = self.window.identity_v2_store.to_payload()
        before_save = self.target.read_bytes()
        with (patch.object(checker_qt.QFileDialog, "getOpenFileNames",
                           return_value=([str(source)], "")),
              patch.object(CsvV2AnalysisDialog, "exec",
                           return_value=checker_qt.QDialog.DialogCode.Rejected)):
            self.window.analyze_v2_csv_files()
        self.assertIsNone(self.window.csv_v2_import_plan)
        self.assertEqual(self.window.identity_v2_store.to_payload(), before_store)
        self.assertEqual(self.target.read_bytes(), before_save)


if __name__ == "__main__":
    unittest.main()
