# -*- coding: utf-8 -*-
"""Focused tests for dynamic windows, roster zoom, fixed cards and PNG export."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import urllib.request
from unittest.mock import Mock, patch


g = None
grabber = None
geometry = None
REPO_ROOT = None


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class GeometryTests(unittest.TestCase):
    def test_default_uses_work_area_ratios_center_and_taskbar_boundary(self):
        area = geometry.WorkArea(0, 0, 1920, 1040)
        result = geometry.default_geometry(area)
        self.assertEqual((result.width, result.height), (1632, 926))
        self.assertAlmostEqual(result.width / area.width, 0.85, places=2)
        self.assertAlmostEqual(result.height / area.height, 0.89, places=2)
        self.assertEqual(result.x, (area.width - result.width) // 2)
        self.assertEqual(result.y, (area.height - result.height) // 2)
        self.assertLessEqual(result.y + result.height, area.bottom)

    def test_larger_work_areas_use_more_space_without_1080p_cap(self):
        sizes = []
        for width, height in ((2560, 1400), (3440, 1400), (3840, 2080)):
            result = geometry.default_geometry(geometry.WorkArea(0, 0, width, height))
            sizes.append((result.width, result.height))
            self.assertEqual(result.width, round(width * 0.85))
            self.assertEqual(result.height, round(height * 0.89))
        self.assertGreater(sizes[-1][0], sizes[0][0])
        self.assertGreater(sizes[-1][1], sizes[0][1])

    def test_valid_saved_geometry_is_respected(self):
        area = geometry.WorkArea(0, 0, 1920, 1040)
        result = geometry.resolve_geometry("1200x760+220+100", area, (760, 520))
        self.assertEqual(result.as_tk(), "1200x760+220+100")

    def test_offscreen_absurd_and_malformed_geometry_fall_back_safely(self):
        area = geometry.WorkArea(0, 0, 1920, 1040)
        default = geometry.default_geometry(area)
        for saved in ("1200x700+4000+2000", "5000x3000+0+0", "broken", "500x300+1+1"):
            with self.subTest(saved=saved):
                self.assertEqual(geometry.resolve_geometry(saved, area, (760, 520)), default)

    def test_settings_update_preserves_language_and_is_atomic(self):
        with tempfile.TemporaryDirectory(prefix="ggc-block4-settings-") as temp:
            path = Path(temp) / "suite_settings.json"
            path.write_text('{"language":"en"}', encoding="utf-8")
            geometry.update_suite_settings(path, checker_geometry="1200x760+20+20")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["language"], "en")
            self.assertEqual(data["checker_geometry"], "1200x760+20+20")
            self.assertFalse(path.with_suffix(".json.tmp").exists())


class TkBlock4Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="ggc-block4-ui-")
        self.root = Path(self.temp_dir.name)
        self.apps = []

    def tearDown(self):
        for app in reversed(self.apps):
            try:
                app.destroy()
            except Exception:
                pass
        self.temp_dir.cleanup()

    def make_checker(self, settings=None, area=None):
        area = area or geometry.WorkArea(0, 0, 1920, 1040)
        patches = [
            patch.object(g, "app_base_dir", return_value=self.root),
            patch.object(g, "read_suite_settings", return_value=dict(settings or {})),
            patch.object(g, "work_area_for_geometry", return_value=area),
            patch.dict(os.environ, {"GGC_DISABLE_ICON_DOWNLOAD": "1"}),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        try:
            app = g.GuildGearCheckerApp()
        except g.tk.TclError as exc:
            self.skipTest(f"Tk unavailable: {exc}")
        app.update_idletasks()
        self.apps.append(app)
        return app

    def make_grabber(self, settings=None, area=None):
        area = area or geometry.WorkArea(0, 0, 1920, 1040)
        patches = [
            patch.object(grabber, "suite_root_dir", return_value=self.root),
            patch.object(grabber, "read_suite_settings", return_value=dict(settings or {})),
            patch.object(grabber, "work_area_for_geometry", return_value=area),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        try:
            app = grabber.App(initial_names=["Janos"])
        except grabber.tk.TclError as exc:
            self.skipTest(f"Tk unavailable: {exc}")
        app.update_idletasks()
        self.apps.append(app)
        return app

    def test_checker_and_grabber_defaults_use_fake_work_area_and_are_not_maximized(self):
        checker = self.make_checker()
        self.assertTrue(checker.geometry().startswith("1632x926+144+57"))
        self.assertEqual(checker.state(), "normal")
        self.assertTrue(checker.tab_buttons["Roster"].winfo_exists())
        self.assertTrue(checker.detail_canvas.winfo_exists())
        grabber_app = self.make_grabber()
        self.assertTrue(grabber_app.geometry().startswith("1632x926+144+57"))
        self.assertEqual(grabber_app.state(), "normal")
        self.assertTrue(grabber_app.stop_btn.winfo_exists())
        self.assertTrue(grabber_app.preview_image_label.winfo_exists())
        self.assertTrue(grabber_app.banner_canvas.winfo_exists())

    def test_valid_saved_checker_and_grabber_geometry_is_restored(self):
        checker = self.make_checker({"checker_geometry": "1200x760+200+100"})
        self.assertTrue(checker.geometry().startswith("1200x760+200+100"))
        grabber_app = self.make_grabber({"grabber_geometry": "1100x720+300+120"})
        self.assertTrue(grabber_app.geometry().startswith("1100x720+300+120"))

    def test_default_zoom_buttons_limits_and_manual_resize_behavior(self):
        app = self.make_checker()
        self.assertEqual(app.roster_zoom_percent, 100)
        app._roster_zoom_out()
        self.assertEqual((app.roster_zoom_percent, app.roster_zoom_var.get()), (90, "90 %"))
        for _ in range(10):
            app._roster_zoom_out()
        self.assertEqual(app.roster_zoom_percent, 60)
        for _ in range(20):
            app._roster_zoom_in()
        self.assertEqual(app.roster_zoom_percent, 140)
        app._set_roster_zoom(100)
        self.assertEqual(app.roster_zoom_percent, 100)
        app._set_roster_zoom(80)
        app._schedule_roster_render(SimpleNamespace(width=1500))
        self.assertEqual(app.roster_zoom_percent, 80)
        self.assertFalse(app.roster_fit_mode)
        saved = json.loads(app._suite_settings_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["roster_zoom"], 80)
        self.assertFalse(saved["roster_fit"])

    def test_fit_recalculates_and_manual_zoom_leaves_fit_mode(self):
        app = self.make_checker()
        app.model.members = [
            g.Member(f"m{index:04d}", f"Char{index:02d}", raidRole="dps")
            for index in range(12)
        ]
        app.current_tab = "Roster"
        app.roster_fit_mode = True
        app._recalculate_roster_fit(1500)
        wide_zoom = app.roster_zoom_percent
        app._recalculate_roster_fit(700)
        narrow_zoom = app.roster_zoom_percent
        self.assertIn(wide_zoom, range(60, 141, 10))
        self.assertIn(narrow_zoom, range(60, 141, 10))
        self.assertNotEqual(wide_zoom, narrow_zoom)
        app._roster_zoom_in()
        self.assertFalse(app.roster_fit_mode)

    def test_roster_details_toggle_preserves_selection_state_and_persists_setting(self):
        app = self.make_checker()
        member = app.model.add_member("Aba", "Test")
        app.switch_tab("Roster")
        app.update_idletasks()
        self.assertEqual(app.detail_outer.winfo_manager(), "grid")
        self.assertTrue(app.roster_details_visible)
        member_id = member.id
        app.selected_member_id = member_id
        app.model.dirty = False
        visible_center_width = app.center.winfo_width()

        app._toggle_roster_details()
        app.update_idletasks()
        self.assertEqual(app.detail_outer.winfo_manager(), "")
        self.assertFalse(app.roster_details_visible)
        self.assertEqual(app.selected_member_id, member_id)
        self.assertFalse(app.model.dirty)
        self.assertGreaterEqual(app.center.winfo_width(), visible_center_width)
        self.assertEqual(app.roster_details_button.cget("text"), g.tr("roster.show_details"))

        saved = json.loads(app._suite_settings_path.read_text(encoding="utf-8"))
        self.assertFalse(saved["roster_details_visible"])

        app._toggle_roster_details()
        app.update_idletasks()
        self.assertEqual(app.detail_outer.winfo_manager(), "grid")
        self.assertEqual(app.selected_member_id, member_id)
        self.assertEqual(app.roster_details_button.cget("text"), g.tr("roster.hide_details"))

    def test_roster_details_setting_defaults_safely_and_fit_recalculates_on_toggle(self):
        app = self.make_checker({"roster_details_visible": "false"})
        self.assertTrue(app.roster_details_visible)
        app.switch_tab("Roster")
        app.roster_fit_mode = True
        with patch.object(app, "_recalculate_roster_fit", wraps=app._recalculate_roster_fit) as fit:
            app._toggle_roster_details()
            self.assertTrue(fit.called)
        app.switch_tab("Friedhof")
        self.assertEqual(app.detail_outer.winfo_manager(), "")
        app.switch_tab("Gildenliste")
        self.assertEqual(app.detail_outer.winfo_manager(), "grid")
        app.switch_tab("Roster")
        self.assertEqual(app.detail_outer.winfo_manager(), "")

    def test_status_action_buttons_distinguish_inactive_and_dead(self):
        app = self.make_checker()
        app.model.new_empty()
        active = app.model.add_member("Active")
        inactive = app.model.add_member("Inactive")
        app.model.set_member_life_status(inactive.id, "inactive")
        dead = app.model.add_member("Dead")
        dead.lifeStatus = "dead"

        app.show_member(active.id)
        self.assertEqual(app.activity_button.cget("text"), g.tr("checker.mark_inactive"))
        self.assertEqual(app.life_button.cget("text"), g.tr("checker.mark_dead"))
        self.assertTrue(app.life_button.winfo_manager())

        app.show_member(inactive.id)
        self.assertEqual(app.activity_button.cget("text"), g.tr("checker.reactivate"))
        self.assertEqual(app.life_button.cget("text"), g.tr("checker.mark_dead"))
        self.assertTrue(app.life_button.winfo_manager())

        app.show_member(dead.id)
        self.assertEqual(app.activity_button.cget("text"), g.tr("checker.reanimate_dead"))
        self.assertEqual(app.life_button.winfo_manager(), "")

    def test_every_card_has_identical_size_at_each_zoom(self):
        app = self.make_checker()
        app.model.new_empty()
        player = g.Player("p0001", "Player")
        app.model.players.append(player)
        app.model.members = [
            g.Member("m1", "Aba", className="Mage", spec="", characterType="main", playerId=player.playerId, raidRole="dps"),
            g.Member("m2", "Wariwariluke", className="Priest", spec="Holy", characterType="twink", playerId=player.playerId, raidRole="dps"),
            g.Member("m3", "ÄußerstlangerUnicodecharakter", className="", characterType="not_set", raidRole="not_set"),
        ]
        app.current_tab = "Roster"
        parent = g.tk.Frame(app)
        try:
            for zoom in (60, 100, 140):
                app.roster_zoom_percent = zoom
                cards = [app._create_roster_card(parent, member) for member in app.model.members]
                sizes = {(int(card.cget("width")), int(card.cget("height"))) for card in cards}
                self.assertEqual(sizes, {g.roster_card_size(zoom)})
                for card in cards:
                    card.destroy()
        finally:
            parent.destroy()

    def test_roster_columns_are_responsive_without_global_mousewheel(self):
        self.assertGreater(g.roster_column_count(1800, 100), g.roster_column_count(700, 100))
        self.assertGreater(g.roster_column_count(1000, 60), g.roster_column_count(1000, 140))
        source = inspect.getsource(g.GuildGearCheckerApp._build_roster_view)
        source += inspect.getsource(g.GuildGearCheckerApp._bind_roster_wheel)
        self.assertNotIn("bind_all", source)

    def test_export_ui_uses_safe_default_name_and_preserves_project_state(self):
        app = self.make_checker()
        app.model.add_member("Aba", "Test")
        app.model.project_path = self.root / "My:Guild.ggc"
        app.model.dirty = True
        destination = self.root / "chosen.png"
        with patch.object(g.filedialog, "asksaveasfilename", return_value=str(destination)) as dialog, \
             patch.object(g, "render_roster_png", return_value={"cards": [{}]}) as renderer:
            app.export_roster_png()
        self.assertEqual(dialog.call_args.kwargs["initialfile"], f"My_Guild_Roster_{g.today_iso()}.png")
        renderer.assert_called_once_with(app.model, destination)
        self.assertEqual(app.model.project_path, self.root / "My:Guild.ggc")
        self.assertTrue(app.model.dirty)

    def test_empty_roster_ui_shows_message_without_save_dialog(self):
        app = self.make_checker()
        app.model.new_empty()
        with patch.object(g.messagebox, "showinfo") as info, \
             patch.object(g.filedialog, "asksaveasfilename") as dialog:
            app.export_roster_png()
        info.assert_called_once()
        dialog.assert_not_called()


class RosterExportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="ggc-block4-export-")
        self.root = Path(self.temp_dir.name)
        self.portraits = self.root / "portraits"
        self.icons = self.root / "classes"
        self.portraits.mkdir()
        (self.icons / "fallback").mkdir(parents=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def model(self):
        model = g.GuildModel()
        model.new_empty()
        model.players = [g.Player("p1", "Spieler Eins"), g.Player("p2", "Spieler Zwei")]
        model.members = [
            g.Member("m1", "MainÄon", className="Warrior", spec="Protection", playerId="p1", characterType="main", raidRole="main_tank", gearStatus="Sehr gut", enchants="OK"),
            g.Member("m2", "SøreDerSehrLangeTwinkname", className="Mage", spec="Frost", playerId="p1", characterType="twink", raidRole="dps", gearStatus="Gut", enchants="Fehlt"),
            g.Member("m3", "Müller", className="Priest", spec="Holy", characterType="not_set", raidRole="healer"),
            g.Member("m4", "Jägername", className="Hunter", spec="Marksmanship", playerId="p2", characterType="twink", raidRole="tank"),
            g.Member("m5", "Éowyn", className="Mage", spec="", raidRole="not_set"),
            g.Member("m6", "Dead", className="Rogue", lifeStatus="dead", raidRole="dps"),
        ]
        model.project_path = self.root / "Gîlde.ggc"
        model.dirty = True
        return model

    def test_high_resolution_export_contains_all_active_groups_and_uniform_cards(self):
        model = self.model()
        g.Image.new("RGB", (300, 500), (100, 40, 20)).save(self.portraits / "m5.png")
        g.Image.new("RGB", (64, 64), (20, 80, 160)).save(self.icons / "mage.jpg")
        destination = self.root / "roster.png"
        before_payload = (
            deepcopy([g.asdict(member) for member in model.members]),
            deepcopy([g.asdict(player) for player in model.players]),
            model.region, model.realm, model.game_version,
        )
        before_portrait = hashlib.sha256((self.portraits / "m5.png").read_bytes()).hexdigest()
        with patch.object(g.webbrowser, "open") as browser, patch.object(g.urllib.request, "urlopen") as network:
            manifest = g.render_roster_png(model, destination, self.portraits, self.icons)
        browser.assert_not_called()
        network.assert_not_called()
        self.assertTrue(destination.is_file())
        with g.Image.open(destination) as image:
            self.assertEqual(image.format, "PNG")
            self.assertGreaterEqual(image.width, 2400)
            self.assertEqual(image.size, tuple(manifest["size"]))
        self.assertEqual(set(manifest["active_ids"]), {"m1", "m2", "m3", "m4", "m5"})
        self.assertNotIn("m6", manifest["active_ids"])
        self.assertEqual([group["role"] for group in manifest["groups"]], list(g.ROSTER_ROLE_ORDER))
        sizes = {(card["rect"][2] - card["rect"][0], card["rect"][3] - card["rect"][1]) for card in manifest["cards"]}
        self.assertEqual(sizes, {g.ROSTER_EXPORT_CARD_SIZE})
        by_id = {card["member_id"]: card for card in manifest["cards"]}
        self.assertTrue(by_id["m5"]["portrait_used"])
        self.assertFalse(by_id["m3"]["portrait_used"])
        self.assertTrue(by_id["m5"]["icon_used"])
        self.assertFalse(by_id["m1"]["icon_used"])
        self.assertEqual(by_id["m2"]["associated_main"], "Main: MainÄon")
        self.assertIn(g.tr("checker.no_active_main"), by_id["m4"]["associated_main"])
        self.assertEqual(by_id["m2"]["class"], "Mage")
        self.assertEqual(by_id["m2"]["spec"], "Frost")
        self.assertEqual(by_id["m2"]["gear"], g.gear_status_display("Gut"))
        self.assertEqual(by_id["m2"]["enchants"], g.enchant_status_display("Fehlt"))
        self.assertIn("Éowyn", [card["name"] for card in manifest["cards"]])
        self.assertEqual((
            [g.asdict(member) for member in model.members],
            [g.asdict(player) for player in model.players],
            model.region, model.realm, model.game_version,
        ), before_payload)
        self.assertTrue(model.dirty)
        self.assertEqual(model.project_path, self.root / "Gîlde.ggc")
        self.assertEqual(hashlib.sha256((self.portraits / "m5.png").read_bytes()).hexdigest(), before_portrait)

    def test_export_is_independent_of_screen_zoom_window_scroll_and_dpi(self):
        model = self.model()
        first = g.render_roster_png(model, self.root / "first.png", self.portraits, self.icons)
        model.screen_zoom = 60
        model.window_geometry = "800x600"
        model.scroll_position = 0.75
        model.dpi = 150
        second = g.render_roster_png(model, self.root / "second.png", self.portraits, self.icons)
        self.assertEqual(first["size"], second["size"])
        self.assertEqual(first["columns"], second["columns"])
        self.assertEqual(first["cards"], second["cards"])
        self.assertEqual((self.root / "first.png").read_bytes(), (self.root / "second.png").read_bytes())

    def test_large_roster_uses_six_columns_and_dynamic_unclipped_height(self):
        model = self.model()
        model.members = [
            g.Member(f"m{i:03d}", f"Char{i:03d}", className="Mage", raidRole="dps")
            for i in range(31)
        ]
        manifest = g.render_roster_png(model, self.root / "large.png", self.portraits, self.icons)
        self.assertEqual(manifest["columns"], 6)
        self.assertGreater(manifest["size"][1], g.ROSTER_EXPORT_CARD_SIZE[1] * 5)
        self.assertEqual(len(manifest["cards"]), 31)
        self.assertTrue(all(card["rect"][3] < manifest["size"][1] for card in manifest["cards"]))

    def test_empty_roster_creates_no_png(self):
        model = g.GuildModel()
        model.new_empty()
        destination = self.root / "empty.png"
        with self.assertRaisesRegex(ValueError, g.tr("roster.export_empty")):
            g.render_roster_png(model, destination, self.portraits, self.icons)
        self.assertFalse(destination.exists())

    def test_export_filename_is_safe_and_does_not_change_project_state(self):
        model = self.model()
        filename = f"{g.sanitize_filename(model.project_path.stem).strip(' ._')}_Roster_{g.today_iso()}.png"
        self.assertEqual(filename, f"Gîlde_Roster_{g.today_iso()}.png")
        translator = g.tr.__globals__["_translator"]
        old = translator.language
        try:
            translator.language = "de"
            self.assertEqual(g.tr("roster.fit_window"), "An Fenster anpassen")
            self.assertEqual(g.tr("roster.export_png"), "Roster als PNG exportieren")
            translator.language = "en"
            self.assertEqual(g.tr("roster.fit_window"), "Fit to Window")
            self.assertEqual(g.tr("roster.export_png"), "Export Roster as PNG")
        finally:
            translator.language = old


def main() -> int:
    global g, grabber, geometry, REPO_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    REPO_ROOT = args.repo_root.resolve()
    geometry = load_module("ggc_block4_geometry", REPO_ROOT / "app" / "window_geometry.py")
    g = load_module("ggc_block4_checker", REPO_ROOT / "app" / "GuildGearChecker.py")
    grabber = load_module("ggc_block4_grabber", REPO_ROOT / "app" / "GuildPortraitGrabber.py")
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
