"""Focused offscreen tests for the visible guild launcher."""

from __future__ import annotations

import os
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

from app import i18n
from app.clm_identity_v2_decisions import CONTINUE, ClmIdentityDecisionDraft
from app.clm_identity_v2_materialization import finalized_clm_character_groups
from app.guild_projects import create_guild
from app.identity_v2 import (
    IdentityV2Store, Member, Raid, POINT_MODE_ETERNAL, POINT_MODE_RAID,
)
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from app.launcher_qt import BannerHeader, LauncherWindow, NewGuildDialog
from app.project_catalog import ProjectCatalog
from app.identity_v2_import_choices import CharacterImportChoice
from tests.clm_v2_initialization_tests import synthetic_lua


class LauncherUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings = self.root / "config" / "suite_settings.json"
        self.catalog = ProjectCatalog(self.settings)
        self.opened: list[tuple[IdentityV2Store, Path]] = []
        self.main_windows: list[QMainWindow] = []
        self.old_language = i18n._translator.language
        self.old_settings_path = i18n._translator.settings_path
        i18n._translator.language = "de"
        i18n._translator.settings_path = self.settings
        self.addCleanup(self._restore_language)

    def _restore_language(self):
        for window in self.main_windows:
            window.hide()
            window.deleteLater()
        i18n._translator.language = self.old_language
        i18n._translator.settings_path = self.old_settings_path

    def _factory(self, store: IdentityV2Store, path: Path) -> QMainWindow:
        self.opened.append((store, path))
        window = QMainWindow()
        self.main_windows.append(window)
        return window

    def _launcher(self, *, guild_factory=None) -> LauncherWindow:
        kwargs = {"catalog": self.catalog, "window_factory": self._factory}
        if guild_factory is not None:
            kwargs["guild_factory"] = guild_factory
        window = LauncherWindow(**kwargs)
        self.addCleanup(window.deleteLater)
        return window

    def _project(self, name: str, mode: str = POINT_MODE_RAID) -> Path:
        target = self.root / f"{name}.ggc"
        save_new_identity_v2(
            IdentityV2Store(guildName=name, realm="Stitches", pointMode=mode),
            target)
        return target

    def test_launcher_is_first_window_with_fixed_centered_size_and_empty_state(self):
        with (patch("app.launcher_qt.load_identity_v2",
                    side_effect=AssertionError("Projektload beim Start")),
              patch("app.project_catalog.load_identity_v2",
                    side_effect=AssertionError("Katalogload beim Start")),
              patch("app.guild_projects.inspect_clm_v2_source",
                    side_effect=AssertionError("CLM beim Start"))):
            window = self._launcher()
            window.show()
            self.app.processEvents()
        self.assertTrue(window.isVisible())
        self.assertIsNone(window.main_window)
        self.assertEqual((window.width(), window.height()), (900, 580))
        self.assertEqual(window.minimumSize(), window.maximumSize())
        self.assertFalse(window.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint)
        window.resize(1200, 800)
        self.assertEqual((window.width(), window.height()), (900, 580))
        self.assertEqual(window.recent_layout.itemAt(0).widget().text(),
                         "Noch keine Gilde eingerichtet.")
        self.assertEqual(window.new_button.text(), "+ Neue Gilde")
        self.assertEqual(len(self.opened), 0)
        self.assertIsInstance(window.header, BannerHeader)
        self.assertFalse(window.header._image.isNull())

    def test_last_project_is_separate_and_others_are_sorted(self):
        paths = [self._project(name) for name in ("Erste", "Zweite", "Dritte")]
        times = iter(datetime(2026, 9, day, tzinfo=timezone.utc)
                     for day in (20, 22, 24))
        self.catalog._clock = lambda: next(times)
        for path in paths:
            self.catalog.mark_opened(path, IdentityV2Store(
                guildName=path.stem, realm="Stitches"))
        with (patch("app.project_catalog.load_identity_v2",
                    side_effect=AssertionError("Kein Laden bekannter Projekte")),
              patch("app.launcher_qt.load_identity_v2",
                    side_effect=AssertionError("Kein Öffnen beim Launcherstart"))):
            window = self._launcher()
        self.assertEqual(window.recent_layout.itemAt(0).widget().entry.path,
                         paths[2].resolve())
        self.assertEqual([card.entry.path for card in window._cards[1:]],
                         [paths[1].resolve(), paths[0].resolve()])
        self.assertEqual(window._cards[0].mode_label.text(), "Raidpunkte")
        self.assertIn("24.09.2026", window._cards[0].date_label.text())

    def test_many_guilds_scroll_only_in_other_area_and_long_name_is_elided(self):
        long_name = "Gilde" * 35
        first = self._project(long_name)
        self.catalog.mark_opened(first, IdentityV2Store(
            guildName=long_name, realm="SehrLangerRealmname" * 12))
        for index in range(12):
            path = self._project(f"Gilde{index:02d}")
            self.catalog.add_project(path)
        window = self._launcher()
        window.show()
        self.app.processEvents()
        self.assertGreater(window.other_scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(window._cards[0].name_label.toolTip(), long_name)
        self.assertNotEqual(window._cards[0].name_label.text(), long_name)
        self.assertTrue(window.exit_button.isVisible())
        window.header.en_button.click()
        self.app.processEvents()
        positions = [card.y() for card in window._cards[1:]]
        self.assertTrue(all(right - left >= 76 for left, right in
                            zip(positions, positions[1:])))
        self.assertEqual(window.other_scroll.verticalScrollBar().value(), 0)

    def test_card_single_click_opens_once_and_passes_selected_store(self):
        path = self._project("Bierstube")
        self.catalog.add_project(path)
        window = self._launcher()
        window.show()
        self.app.processEvents()
        card = window._cards[0]
        selected_store = IdentityV2Store(guildName="Bierstube", realm="Stitches")
        with patch("app.launcher_qt.load_identity_v2",
                   return_value=selected_store) as load:
            QTest.mouseClick(card, Qt.MouseButton.LeftButton,
                             pos=card.rect().center())
            card.clicked.emit(str(path))
        load.assert_called_once_with(path.resolve())
        self.assertEqual(len(self.opened), 1)
        self.assertIs(self.opened[0][0], selected_store)
        self.assertIs(window.main_window, self.main_windows[-1])
        self.assertEqual(self.catalog.last_project().path, path.resolve())
        self.assertFalse(window.isVisible())

    def test_card_menu_is_separate_from_open_and_translates_de_en(self):
        path = self._project("Menü")
        self.catalog.add_project(path)
        window = self._launcher()
        window.show()
        self.app.processEvents()
        card = window._cards[0]
        self.assertEqual(card.menu_button.text(), "⋯")
        self.assertEqual(card.remove_menu_action.text(), "Aus Liste entfernen")
        self.assertEqual(card.height(), 76)
        with patch.object(card.card_menu, "popup") as popup:
            QTest.mouseClick(card.menu_button, Qt.MouseButton.LeftButton)
        popup.assert_called_once()
        self.assertEqual(self.opened, [])
        self.assertIsNone(window.main_window)
        self.assertIsNone(self.catalog.last_project())
        dialog, remove = window._remove_dialog()
        self.assertEqual(dialog.text(), "Gilde aus dem Startmenü entfernen?")
        self.assertEqual(dialog.informativeText(),
                         "Die Projektdateien werden nicht gelöscht.")
        self.assertEqual(remove.text(), "Entfernen")
        self.assertIn("Abbrechen", [button.text() for button in dialog.buttons()])
        dialog.deleteLater()

        window.header.en_button.click()
        self.assertEqual(window._cards[0].remove_menu_action.text(), "Remove from list")
        dialog, remove = window._remove_dialog()
        self.assertEqual(dialog.text(), "Remove this guild from the start menu?")
        self.assertEqual(dialog.informativeText(),
                         "The project files will not be deleted.")
        self.assertEqual(remove.text(), "Remove")
        self.assertIn("Cancel", [button.text() for button in dialog.buttons()])
        dialog.deleteLater()

    def test_card_menu_cancel_and_confirm_preserve_all_project_files(self):
        project_dir = self.root / "retained_guild"
        project = project_dir / "project.ggc"
        save_new_identity_v2(IdentityV2Store(guildName="Retained", realm="Stitches"),
                             project)
        portrait = project_dir / "portraits" / "m1000.png"
        portrait.parent.mkdir(parents=True)
        portrait.write_bytes(b"portrait marker")
        before_project = project.read_bytes()
        self.catalog.add_project(project)
        window = self._launcher()
        with patch.object(window, "_ask_remove", return_value=False) as ask:
            window._cards[0].remove_menu_action.trigger()
        ask.assert_called_once()
        self.assertEqual(len(self.catalog.entries()), 1)
        self.assertEqual(project.read_bytes(), before_project)
        with patch.object(window, "_ask_remove", return_value=True):
            window._cards[0].remove_menu_action.trigger()
        self.assertEqual(self.catalog.entries(), ())
        self.assertTrue(project_dir.is_dir())
        self.assertEqual(project.read_bytes(), before_project)
        self.assertEqual(portrait.read_bytes(), b"portrait marker")
        self.assertEqual(window.recent_layout.itemAt(0).widget().text(),
                         "Noch keine Gilde eingerichtet.")

    def test_removing_recent_card_promotes_next_used_guild(self):
        paths = [self._project(name) for name in ("Erste", "Zweite", "Dritte")]
        times = iter(datetime(2026, 9, day, tzinfo=timezone.utc)
                     for day in (20, 22, 24))
        self.catalog._clock = lambda: next(times)
        for path in paths:
            self.catalog.mark_opened(path, IdentityV2Store(
                guildName=path.stem, realm="Stitches"))
        window = self._launcher()
        self.assertEqual(window._cards[0].entry.path, paths[2].resolve())
        with patch.object(window, "_ask_remove", return_value=True):
            window._cards[0].remove_menu_action.trigger()
        self.assertTrue(paths[2].is_file())
        self.assertIsNone(self.catalog.last_project())
        self.assertIsNone(json.loads(self.settings.read_text(encoding="utf-8"))[
            "last_project_path"])
        self.assertEqual(window._cards[0].entry.path, paths[1].resolve())
        self.assertEqual([card.entry.path for card in window._cards[1:]],
                         [paths[0].resolve()])
        with patch.object(window, "_ask_remove", return_value=True):
            window._cards[0].remove_menu_action.trigger()
            self.assertEqual(window._cards[0].entry.path, paths[0].resolve())
            window._cards[0].remove_menu_action.trigger()
        self.assertEqual(window.recent_layout.itemAt(0).widget().text(),
                         "Noch keine Gilde eingerichtet.")
        self.assertEqual(self.catalog.entries(), ())
        self.assertTrue(all(path.is_file() for path in paths))

    def test_load_failure_keeps_launcher_and_last_used_unchanged(self):
        path = self._project("Fehler")
        self.catalog.add_project(path)
        path.write_text("kaputt", encoding="utf-8")
        window = self._launcher()
        window.show()
        with patch("app.launcher_qt.QMessageBox.critical") as error:
            window._cards[0].clicked.emit(str(path))
        error.assert_called_once()
        self.assertTrue(window.isVisible())
        self.assertFalse(window._busy)
        self.assertTrue(window._cards[0].isEnabled())
        self.assertIsNone(self.catalog.last_project())
        self.assertEqual(self.opened, [])

    def test_missing_card_relocates_or_removes_reference_only(self):
        path = self._project("Verschoben")
        self.catalog.mark_opened(path, IdentityV2Store(
            guildName="Verschoben", realm="Stitches"))
        relocated = self.root / "neuer_Ort.ggc"
        path.rename(relocated)
        window = self._launcher()
        card = window._cards[0]
        self.assertTrue(card.entry.missing)
        self.assertEqual(card.date_label.text(), "Projektdatei fehlt")
        self.assertFalse(card.focusPolicy() == Qt.FocusPolicy.StrongFocus)
        with patch("app.launcher_qt.QFileDialog.getOpenFileName",
                   return_value=(str(relocated), "")):
            card.relocate_button.click()
        self.assertEqual(self.catalog.last_project().path, relocated.resolve())
        self.assertFalse(self.catalog.last_project().missing)
        relocated.rename(path)
        window.refresh_cards()
        self.assertTrue(window._cards[0].entry.missing)
        window._cards[0].remove_button.click()
        self.assertIsNone(self.catalog.last_project())
        self.assertTrue(path.is_file())

    def test_add_existing_validates_without_opening_or_duplicate(self):
        path = self._project("Hinzu")
        window = self._launcher()
        with patch("app.launcher_qt.QFileDialog.getOpenFileName",
                   return_value=(str(path), "")):
            window.add_button.click()
            window.add_button.click()
        self.assertEqual(len(self.catalog.entries()), 1)
        self.assertIsNone(self.catalog.last_project())
        self.assertEqual(self.opened, [])
        self.assertEqual(window._cards[0].name_label.text(), "Hinzu")

    def test_new_raid_guild_opens_and_clm_import_precedes_main_window(self):
        def create(name, realm, mode, *, clm_lua_path, catalog):
            return create_guild(name, realm, mode, clm_lua_path=clm_lua_path,
                                catalog=catalog, projects_root=self.root / "projects")

        window = self._launcher(guild_factory=create)
        with patch("app.launcher_qt.NewGuildDialog") as dialog_type:
            dialog_type.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog_type.return_value.values.return_value = (
                "Neue Gilde", "Stitches", POINT_MODE_RAID, None)
            window.new_button.click()
        self.assertEqual(len(self.opened), 1)
        raid_path = self.opened[0][1]
        self.assertTrue(raid_path.is_file())
        self.assertEqual(self.catalog.last_project().path, raid_path.resolve())
        self.assertEqual(self.opened[0][0].pointMode, POINT_MODE_RAID)

        next_window = self._launcher(guild_factory=create)
        with (patch("app.launcher_qt.NewGuildDialog") as dialog_type,
              patch("app.launcher_qt.QMessageBox.critical") as error):
            dialog_type.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog_type.return_value.values.return_value = (
                "Bierstube", "Stitches", POINT_MODE_ETERNAL, None)
            next_window.new_button.click()
        error.assert_called_once()
        self.assertEqual(len(self.opened), 1)
        self.assertFalse(next_window._busy)

        lua = self.root / "ClassicLootManager.lua"
        lua.write_text(synthetic_lua(), encoding="utf-8")
        imported_store = None

        def import_clm(_parent, *, initial_store, source_path):
            nonlocal imported_store
            self.assertEqual((initial_store.guildName, initial_store.realm,
                              initial_store.pointMode),
                             ("Bierstube", "Stitches", POINT_MODE_ETERNAL))
            self.assertEqual(Path(source_path), lua)
            self.assertEqual(len(self.opened), 1)
            imported_store = IdentityV2Store.from_payload(initial_store.to_payload())
            imported_store.members.append(Member("m1000", "Annî", "Priest"))
            imported_store.raids.append(Raid("r1", "2026-09-26", raidType="MC"))
            imported_store.clmRosterName = "Bierstube"
            imported_store.validate()
            return imported_store

        with (patch("app.launcher_qt.NewGuildDialog") as dialog_type,
              patch("app.clm_v2_initialization_ui.run_clm_v2_initialization",
                    side_effect=import_clm) as workflow):
            dialog_type.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog_type.return_value.values.return_value = (
                "Bierstube", "Stitches", POINT_MODE_ETERNAL, str(lua))
            next_window.new_button.click()
        workflow.assert_called_once()
        self.assertEqual(len(self.opened), 2)
        self.assertIs(self.opened[1][0], imported_store)
        self.assertEqual(len(load_identity_v2(self.opened[1][1]).members), 1)
        self.assertEqual(len(load_identity_v2(self.opened[1][1]).raids), 1)
        self.assertEqual(self.catalog.get_clm_path(self.opened[1][1]), lua.resolve())

    def test_new_guild_dialog_shows_lua_only_for_eternal_mode(self):
        window = self._launcher()
        dialog = NewGuildDialog(window)
        self.addCleanup(dialog.deleteLater)
        self.assertTrue(dialog.lua_row.isHidden())
        dialog.eternal_radio.setChecked(True)
        self.assertFalse(dialog.lua_row.isHidden())
        dialog.name_edit.setText("Bierstube")
        dialog.realm_edit.setText("Stitches")
        with patch("app.launcher_qt.QMessageBox.warning") as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        dialog.raid_radio.setChecked(True)
        self.assertTrue(dialog.lua_row.isHidden())

    def test_real_clm_first_import_saves_characters_then_raids_before_opening(self):
        lua = self.root / "ClassicLootManager.lua"
        lua.write_text(synthetic_lua(), encoding="utf-8")

        def create(name, realm, mode, *, clm_lua_path, catalog):
            return create_guild(name, realm, mode, clm_lua_path=clm_lua_path,
                                catalog=catalog, projects_root=self.root / "projects")

        def decisions(analysis, _parent):
            draft = ClmIdentityDecisionDraft(analysis)
            draft.set_choice("Annî", "1:102", CONTINUE)
            return draft.to_decision_set()

        def classifications(analysis, choices, _parent):
            return {chain: CharacterImportChoice() for _name, chain
                    in finalized_clm_character_groups(analysis, choices)}

        window = self._launcher(guild_factory=create)

        def checked_factory(store, path):
            saved = load_identity_v2(path)
            self.assertEqual(saved.to_payload(), store.to_payload())
            self.assertEqual((len(saved.members), len(saved.raids),
                              saved.guildName, saved.realm, saved.pointMode),
                             (2, 1, "Bierstube", "Stitches", POINT_MODE_ETERNAL))
            return self._factory(store, path)

        window._window_factory = checked_factory
        with (patch("app.launcher_qt.NewGuildDialog") as dialog_type,
              patch("app.clm_v2_initialization_ui.QFileDialog.getOpenFileName",
                    side_effect=AssertionError("Lua wurde bereits ausgewählt")),
              patch("app.clm_v2_initialization_ui.QInputDialog.getItem",
                    side_effect=AssertionError("Eindeutiger Roster braucht keine Abfrage")),
              patch("app.clm_v2_initialization_ui.collect_clm_identity_decisions",
                    side_effect=decisions),
              patch("app.clm_v2_initialization_ui.collect_clm_character_classifications",
                    side_effect=classifications),
              patch("app.clm_v2_initialization_ui.ClmRaidReviewDialog.exec",
                    return_value=QDialog.DialogCode.Accepted)):
            dialog_type.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog_type.return_value.values.return_value = (
                "Bierstube", "Stitches", POINT_MODE_ETERNAL, str(lua))
            window.new_button.click()
        self.assertEqual(len(self.opened), 1)
        self.assertEqual(self.catalog.last_project().path, self.opened[0][1])

    def test_cancelled_clm_review_keeps_launcher_open_without_last_used(self):
        lua = self.root / "ClassicLootManager.lua"
        lua.write_text(synthetic_lua(), encoding="utf-8")

        def create(name, realm, mode, *, clm_lua_path, catalog):
            return create_guild(name, realm, mode, clm_lua_path=clm_lua_path,
                                catalog=catalog, projects_root=self.root / "projects")

        window = self._launcher(guild_factory=create)
        window.show()
        with (patch("app.launcher_qt.NewGuildDialog") as dialog_type,
              patch("app.clm_v2_initialization_ui.run_clm_v2_initialization",
                    return_value=None)):
            dialog_type.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog_type.return_value.values.return_value = (
                "Bierstube", "Stitches", POINT_MODE_ETERNAL, str(lua))
            window.new_button.click()
        self.assertTrue(window.isVisible())
        self.assertFalse(window._busy)
        self.assertEqual(self.opened, [])
        self.assertIsNone(self.catalog.last_project())
        self.assertEqual(len(self.catalog.entries()), 1)
        self.assertEqual(load_identity_v2(self.catalog.entries()[0].path).members, [])

    def test_de_en_retranslates_launcher_and_checker_inherits_language(self):
        path = self._project("Sprache")
        self.catalog.add_project(path)
        window = self._launcher()
        window.header.en_button.click()
        self.assertEqual(i18n.get_language(), "en")
        self.assertEqual(window.recent_title.text(), "Recently used")
        self.assertEqual(window.add_button.text(), "Add existing guild")
        self.assertEqual(window._cards[0].mode_label.text(), "Raid Points")
        self.assertEqual(window.header.en_button.property("active"), True)
        window.header.de_button.click()
        self.assertEqual(i18n.get_language(), "de")
        self.assertEqual(window.add_button.text(), "Vorhandene Gilde hinzufügen")
        window.header.en_button.click()
        from app.GuildGearCheckerQt import GuildGearCheckerQt

        def real_checker(store, selected):
            checker = GuildGearCheckerQt(store, selected, settings_path=self.settings)
            self.main_windows.append(checker)
            return checker

        window._window_factory = real_checker
        window._cards[0].clicked.emit(str(path))
        self.assertEqual(i18n.get_language(), "en")
        self.assertEqual(window.main_window._nav_buttons["rooster"].text(), "Roster")


if __name__ == "__main__":
    unittest.main()
