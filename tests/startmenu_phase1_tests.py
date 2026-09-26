"""Focused checks for the start menu's Phase 1 backend."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.guild_projects import create_guild
from app.identity_v2 import (
    IdentityV2Store, Member, Player, POINT_MODE_ETERNAL, POINT_MODE_RAID,
)
from app.identity_v2_character_service import mark_member_dead
from app.identity_v2_player_service import (
    bulk_set_member_activity, set_member_activity,
)
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from app.identity_v2_raid_points import (
    V2RaidPointProjection, apply_v2_raid_point_adjustments,
    apply_v2_member_special_points,
)
from app.project_catalog import ProjectCatalog
from app.raid_points import RaidPointsError
from tests.clm_v2_initialization_tests import synthetic_lua

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class ProjectCatalogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings = self.root / "suite_settings.json"
        self.settings.write_text('{"language":"en"}', encoding="utf-8")
        self.catalog = ProjectCatalog(
            self.settings, clock=lambda: datetime(2026, 9, 26, tzinfo=timezone.utc))
        self.first = self.root / "first.ggc"
        self.second = self.root / "second.ggc"
        self.first_store = IdentityV2Store(
            guildName="Bierstube", realm="Stitches", pointMode=POINT_MODE_RAID)
        self.second_store = IdentityV2Store(
            guildName="Andere", realm="Stitches", pointMode=POINT_MODE_ETERNAL)
        save_new_identity_v2(self.first_store, self.first)
        save_new_identity_v2(self.second_store, self.second)

    def test_catalog_lifecycle_keeps_project_files_and_other_settings(self):
        self.catalog.add_project(self.first)
        self.catalog.add_project(self.first.parent / self.first.name.upper())
        self.catalog.add_project(self.second)
        self.assertEqual(len(self.catalog.entries()), 2)
        self.assertIsNone(self.catalog.last_project())
        self.catalog.mark_opened(self.first, self.first_store)
        self.assertEqual(self.catalog.last_project().path, self.first.resolve())
        self.assertEqual(self.catalog.sorted_entries()[0].path, self.first.resolve())
        self.first.rename(self.root / "moved.ggc")
        self.assertTrue(self.catalog.entries()[0].missing)
        self.catalog.relocate_project(self.first, self.root / "moved.ggc")
        self.assertFalse(self.catalog.last_project().missing)
        self.catalog.remove_project(self.root / "moved.ggc")
        self.assertTrue((self.root / "moved.ggc").is_file())
        self.assertIsNone(self.catalog.last_project())
        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8"))["language"], "en")

    def test_catalog_listing_does_not_load_saves(self):
        self.catalog.add_project(self.first)
        with patch("app.project_catalog.load_identity_v2",
                   side_effect=AssertionError("kein Projektladen")):
            self.assertEqual(self.catalog.entries()[0].guild_name, "Bierstube")
            self.assertEqual(len(self.catalog.sorted_entries()), 1)

    def test_clm_path_is_project_specific(self):
        self.catalog.add_project(self.first)
        self.catalog.add_project(self.second)
        lua = self.root / "ClassicLootManager.lua"
        lua.write_text(synthetic_lua(), encoding="utf-8")
        self.catalog.set_clm_path(self.second, lua)
        self.assertIsNone(self.catalog.get_clm_path(self.first))
        self.assertEqual(self.catalog.get_clm_path(self.second), lua.resolve())


class GuildCreationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.catalog = ProjectCatalog(self.root / "config" / "suite_settings.json")

    def test_raid_guild_uses_v2_storage_and_separate_folders(self):
        first = create_guild("Bierstube", "Stitches", POINT_MODE_RAID,
                             projects_root=self.root / "projects", catalog=self.catalog)
        second = create_guild("Andere", "Stitches", POINT_MODE_RAID,
                              projects_root=self.root / "projects", catalog=self.catalog)
        self.assertNotEqual(first.path.parent, second.path.parent)
        self.assertEqual(load_identity_v2(first.path).to_payload(), first.store.to_payload())
        self.assertEqual(first.store.members, [])
        self.assertIsNone(self.catalog.get_clm_path(first.path))

    def test_eternal_guild_requires_matching_lua_and_stores_path_locally(self):
        with self.assertRaises(ValueError):
            create_guild("Bierstube", "Stitches", POINT_MODE_ETERNAL,
                         projects_root=self.root, catalog=self.catalog)
        lua = self.root / "ClassicLootManager.lua"
        lua.write_text(synthetic_lua(), encoding="utf-8")
        with self.assertRaises(ValueError):
            create_guild("Falsche Gilde", "Stitches", POINT_MODE_ETERNAL,
                         clm_lua_path=lua, projects_root=self.root,
                         catalog=self.catalog)
        created = create_guild("Bierstube", "Stitches", POINT_MODE_ETERNAL,
                               clm_lua_path=lua, projects_root=self.root,
                               catalog=self.catalog)
        self.assertEqual(load_identity_v2(created.path).pointMode, POINT_MODE_ETERNAL)
        self.assertEqual((created.store.players, created.store.members,
                          created.store.raids), ([], [], []))
        self.assertEqual(self.catalog.get_clm_path(created.path), lua.resolve())
        self.assertNotIn(str(lua.resolve()), created.path.read_text(encoding="utf-8"))

    def test_new_guild_never_overwrites_an_existing_project(self):
        fixed_id = type("FixedId", (), {"hex": "a" * 32})()
        with patch("app.guild_projects.uuid.uuid4", return_value=fixed_id):
            first = create_guild("Bierstube", "Stitches", POINT_MODE_RAID,
                                 projects_root=self.root, catalog=self.catalog)
            before = first.path.read_bytes()
            with self.assertRaises(ValueError):
                create_guild("Andere", "Stitches", POINT_MODE_RAID,
                             projects_root=self.root, catalog=self.catalog)
        self.assertEqual(first.path.read_bytes(), before)

    def test_clm_new_guild_can_defer_ambiguous_matching_database_to_review(self):
        lua = self.root / "ClassicLootManager.lua"
        lua.write_text(synthetic_lua().replace(
            '["exp0 alliance stitches triumph"] = { ledger = {',
            '["exp0 alliance stitches second"] = { guildName="Bierstube", '
            'realm="Stitches", ledger = {'), encoding="utf-8")
        created = create_guild("Bierstube", "Stitches", POINT_MODE_ETERNAL,
                               clm_lua_path=lua, projects_root=self.root / "projects",
                               catalog=self.catalog)
        self.assertTrue(created.path.is_file())
        self.assertEqual(created.store.members, [])


class MainActivityTests(unittest.TestCase):
    def test_single_and_bulk_activity_keep_main_until_death(self):
        store = IdentityV2Store(
            players=[Player("p0001", "Spieler", "m1000")],
            members=[Member("m1000", "Main", "Mage", playerId="p0001"),
                     Member("m1001", "Twink", "Priest", playerId="p0001")],
        )
        inactive = set_member_activity(store, "m1000", "inactive")
        self.assertEqual(inactive.players[0].mainMemberId, "m1000")
        self.assertEqual(inactive.players[0].mainHistory, [])
        active = set_member_activity(inactive, "m1000", "active")
        self.assertEqual(active.players[0].mainMemberId, "m1000")
        bulk = bulk_set_member_activity(active, ("m1000", "m1001"), "inactive")
        self.assertEqual(bulk.players[0].mainMemberId, "m1000")
        self.assertEqual(bulk.members[1].playerId, "p0001")
        self.assertEqual(bulk.players[0].mainHistory, [])
        dead = mark_member_dead(bulk, "m1000", "2026-09-26", "collective")
        self.assertIsNone(dead.players[0].mainMemberId)
        self.assertEqual(dead.players[0].mainHistory[0].reason, "death")


class PointModeTests(unittest.TestCase):
    def test_raid_point_services_reject_eternal_mode(self):
        store = IdentityV2Store(pointMode=POINT_MODE_ETERNAL)
        with self.assertRaises(RaidPointsError):
            V2RaidPointProjection(store)
        with self.assertRaises(RaidPointsError):
            apply_v2_raid_point_adjustments(store, ())
        with self.assertRaises(RaidPointsError):
            apply_v2_member_special_points(store, "m1000", 1, "Test")


try:
    from PySide6.QtWidgets import QApplication
    from app import GuildGearCheckerQt as checker_qt
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 fehlt")
class QtStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings = self.root / "suite_settings.json"

    def _window(self, store, path=None):
        window = checker_qt.GuildGearCheckerQt(
            store, path, settings_path=self.settings)
        self.addCleanup(self._close, window)
        return window

    @staticmethod
    def _close(window):
        with (patch.object(checker_qt, "update_suite_settings"),
              patch.object(checker_qt.QMessageBox, "question",
                           return_value=checker_qt.QMessageBox.StandardButton.Yes)):
            window.close()

    def test_preloaded_store_survives_startup_without_project_reload(self):
        store = IdentityV2Store(guildName="Direkt", realm="Stitches")
        with patch("app.identity_v2_storage.load_identity_v2",
                   side_effect=AssertionError("doppeltes Laden")):
            window = self._window(store)
        self.assertIs(window.identity_v2_store, store)
        self.assertEqual(window.project_mode, "identity_v2")
        window._load_autosave_or_seed()
        self.assertIs(window.identity_v2_store, store)

    def test_point_modes_gate_projection_and_actions(self):
        eternal = IdentityV2Store(guildName="DKP", realm="Stitches",
                                  pointMode=POINT_MODE_ETERNAL)
        with patch("app.identity_v2_raid_points.V2RaidPointProjection",
                   side_effect=AssertionError("Raidpunkte im DKP-Modus")):
            window = self._window(eternal)
            self.assertFalse(window._rebuild_v2_raid_points())
            self.assertFalse(window._adjust_v2_raid_points())
        self.assertIsNone(window._v2_raid_point_projection)
        self.assertTrue(window.set_v2_active_point_system(POINT_MODE_RAID))
        self.assertIsNotNone(window._v2_raid_point_projection)
        with (patch.object(checker_qt.QFileDialog, "getOpenFileName",
                           return_value=("", "")) as choose_file,
              patch.object(window._clm_refresh_service, "refresh_for_project",
                           side_effect=AssertionError("Kein CLM-Refresh ohne Datei"))):
            window.refresh_dkp()
        choose_file.assert_called_once()
        with patch.object(checker_qt.QFileDialog, "getOpenFileName",
                          return_value=("", "")) as choose_file:
            window.choose_clm_path()
        choose_file.assert_called_once()
        with patch("app.clm_v2_initialization_ui.run_clm_v2_initialization",
                   side_effect=AssertionError("Kein CLM-Import")):
            window.initialize_v2_from_clm()

    def test_project_switch_clears_caches_and_project_lua_path(self):
        first = self.root / "first.ggc"
        second = self.root / "second.ggc"
        store_a = IdentityV2Store(guildName="A", realm="Stitches",
                                  pointMode=POINT_MODE_ETERNAL)
        store_b = IdentityV2Store(guildName="B", realm="Stitches",
                                  pointMode=POINT_MODE_RAID)
        save_new_identity_v2(store_a, first)
        save_new_identity_v2(store_b, second)
        refs = ProjectCatalog(self.settings)
        refs.add_project(first, store=store_a)
        refs.add_project(second, store=store_b)
        lua = self.root / "ClassicLootManager.lua"
        lua.write_text(synthetic_lua(), encoding="utf-8")
        refs.set_clm_path(first, lua)
        window = self._window(store_a, first)
        self.assertEqual(window.clm_path_edit.text(), str(lua.resolve()))
        window._v2_dkp_snapshot = object()
        window._v2_matrix_cache["old"] = object()
        window.adopt_identity_v2_project(store_b, second)
        self.assertEqual(window.clm_path_edit.text(), "")
        self.assertIsNone(window._v2_dkp_snapshot)
        self.assertEqual(window._v2_matrix_cache, {})
        self.assertEqual(window.identity_v2_project_path, second.resolve())


if __name__ == "__main__":
    unittest.main()
