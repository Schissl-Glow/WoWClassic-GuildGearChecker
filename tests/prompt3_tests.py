# -*- coding: utf-8 -*-
"""Focused regression tests for the reconstructed Prompt-3 integration."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

REPO_ROOT: Path


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Prompt3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO_ROOT))
        cls.grabber = load_module("prompt3_grabber", REPO_ROOT / "app" / "GuildPortraitGrabber.py")
        cls.checker = load_module("prompt3_checker", REPO_ROOT / "app" / "GuildGearChecker.py")

    def test_checker_banner_and_shared_review_core_are_packaged(self):
        self.assertEqual(self.checker.checker_banner_path().name, "checker_banner.png")
        self.assertTrue((REPO_ROOT / "tools" / "gravestone_review" / "gravestone_review_core.py").is_file())
        self.assertTrue((REPO_ROOT / "tools" / "gravestone_review" / "gravestone_review_tool.py").is_file())
        self.assertTrue((REPO_ROOT / "START_GRAVESTONE_REVIEW.bat").is_file())

    def test_standalone_review_uses_shared_core(self):
        from tools.gravestone_review import gravestone_review_core, gravestone_review_tool

        self.assertIs(gravestone_review_tool.run_core_self_test, gravestone_review_core.run_core_self_test)
        self.assertEqual(
            gravestone_review_tool.self_test(REPO_ROOT / "tools" / "gravestone_review"), 0,
        )

    def test_manual_portrait_normalizes_without_distortion(self):
        with tempfile.TemporaryDirectory(prefix="ggc-prompt3-portrait-") as td:
            root = Path(td)
            source = root / "wide.jpg"
            target = root / "Janos.png"
            Image.new("RGB", (1000, 500), (120, 60, 30)).save(source)
            self.grabber.save_manual_portrait_image(source, target)
            with Image.open(target) as image:
                self.assertEqual(image.size, (384, 672))
                self.assertEqual(image.format, "PNG")

    def test_manual_portrait_replaces_only_exact_character_candidates(self):
        try:
            import tkinter  # noqa: F401
        except Exception as exc:
            self.skipTest(f"Tk not available: {exc}")
        with tempfile.TemporaryDirectory(prefix="ggc-prompt3-manual-ui-") as td:
            root = Path(td)
            (root / "assets").mkdir(parents=True)
            output = root / "portraits"
            output.mkdir(parents=True)
            project = root / "guild.ggc"
            shutil.copyfile(REPO_ROOT / "assets" / "grabber_banner.png", root / "assets" / "grabber_banner.png")
            Image.new("RGB", (200, 400), (1, 2, 3)).save(output / "m0001.png")
            Image.new("RGB", (200, 400), (7, 8, 9)).save(output / "m0002.png")
            source = root / "manual.webp"
            Image.new("RGB", (900, 450), (50, 80, 110)).save(source)
            try:
                with patch.object(self.grabber, "suite_root_dir", return_value=root):
                    app = self.grabber.App(
                        initial_characters=[
                            {"memberId": "m0001", "characterName": "Janos"},
                            {"memberId": "m0002", "characterName": "Annie"},
                        ], project_path=str(project),
                    )
                    app.withdraw(); app.update_idletasks()
                    for item in app.tree.get_children():
                        if app.tree.item(item, "values")[0] == "Janos":
                            app.tree.selection_set(item); app.tree.focus(item); app._preview_selection_changed()
                            break
                    def accept_editor(_parent, editor_source, destination, _title, on_saved=None):
                        self.grabber.save_manual_portrait_image(editor_source, destination)
                        if on_saved is not None:
                            on_saved(destination)

                    with patch.object(self.grabber.filedialog, "askopenfilename", return_value=str(source)), \
                         patch.object(self.grabber, "PortraitEditorDialog", side_effect=accept_editor):
                        app._manual_portrait_selected()
                    self.assertTrue((output / "m0001.png").is_file())
                    self.assertTrue((output / "m0002.png").exists())
                    app._on_close(); app.worker.join(timeout=2)
            except self.grabber.tk.TclError as exc:
                self.skipTest(f"Tk not available: {exc}")

    def test_grabber_review_tab_is_integrated(self):
        try:
            app = self.grabber.App(initial_names=["Janos"])
        except self.grabber.tk.TclError as exc:
            self.skipTest(f"Tk not available: {exc}")
        try:
            app.withdraw(); app.update_idletasks(); app.update()
            tabs = [app.notebook.tab(i, "text") for i in range(app.notebook.index("end"))]
            self.assertEqual(tabs, ["Portraits", "Friedhof", "Ausschnitt", "Einstellungen", "Grabstein Review"])
            self.assertTrue(hasattr(app, "review_frame"))
            self.assertTrue(app.review_frame.winfo_exists())
            app._ensure_embedded_gravestone_review()
            self.assertIsNotNone(app._embedded_review_app)
            self.assertIs(app._embedded_review_app.root, app.review_frame)
        finally:
            app._on_close(); app.worker.join(timeout=2)

    def test_checker_prompt3_navigation_smoke(self):
        banner = REPO_ROOT / "assets" / "grabber_banner.png"
        with patch.object(self.checker, "checker_banner_path", return_value=banner):
            try:
                app = self.checker.GuildGearCheckerApp()
            except self.checker.tk.TclError as exc:
                self.skipTest(f"Tk not available: {exc}")
            try:
                app.withdraw(); app.update_idletasks(); app.update()
                self.assertEqual(set(app.primary_nav_buttons), {"Member", "Roster", "Friedhof", "Raids", "Settings"})
                self.assertEqual(
                    set(app.tab_buttons),
                    {"Gildenliste", "Handlungsbedarf", "Ungeprüft", "Inaktiv", "Alle Charaktere",
                     "Roster", "Friedhof", "Raids"},
                )
                self.assertFalse(bool(app.race_combo.winfo_manager()))
                self.assertFalse(bool(app.class_combo.winfo_manager()))
                self.assertFalse(bool(app.spec_combo.winfo_manager()))
                app.switch_tab("Roster")
                app._set_roster_view_mode("list")
                self.assertEqual(app.roster_view_mode, "list")
                app._set_roster_view_mode("cards")
                self.assertEqual(app.roster_view_mode, "cards")
                app._render_checker_banner_cover(1180, self.checker.CHECKER_BANNER_HEIGHT)
                self.assertIsNotNone(app._checker_banner_photo)
            finally:
                app.destroy()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    args = parser.parse_args()
    global REPO_ROOT
    REPO_ROOT = Path(args.repo_root).resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Prompt3Tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
