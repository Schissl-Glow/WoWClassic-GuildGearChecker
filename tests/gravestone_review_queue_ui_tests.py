# -*- coding: utf-8 -*-
"""Focused UI regression tests for the visible gravestone review queues."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.gravestone_review.gravestone_review_core import ensure_workspace
from tools.gravestone_review.gravestone_review_tool import ReviewApp
from app.gravestone_categories import (
    GRAVESTONE_CATEGORIES,
    load_gravestone_category,
    load_gravestone_portrait_preset,
    save_gravestone_category,
    save_gravestone_portrait_preset,
)


TOOL_DIR = REPO_ROOT / "tools" / "gravestone_review"
MASTER_REFERENCE = TOOL_DIR / "reference" / "master_reference.png"


class GravestoneReviewQueueUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="ggc-review-ui-")
        self.project_root = Path(self.temp_dir.name)
        self.workspace = ensure_workspace(self.project_root)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app: ReviewApp | None = None

    def tearDown(self) -> None:
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self.temp_dir.cleanup()

    def _seed(self, folder: Path, name: str) -> Path:
        target = folder / name
        shutil.copyfile(MASTER_REFERENCE, target)
        return target

    def _seed_productive(self, name: str = "gravestone_001.png") -> Path:
        target = self._seed(self.workspace.graveyard, name)
        manifest = {
            "format": "GuildGearCheckerGravestoneManifest",
            "formatVersion": 1,
            "generatedAt": "2026-09-15T12:00:00+02:00",
            "templates": [{
                "graveTemplateId": "grave-template-0001",
                "filename": name,
                "sha256": "0" * 64,
                "category": "Elfen",
                "defaultPortraitOffsetX": 0.25,
                "defaultPortraitOffsetY": -0.35,
                "defaultPortraitZoom": 1.8,
            }],
        }
        (self.workspace.graveyard / "gravestones_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return target

    def _make_app(self) -> ReviewApp:
        self.app = ReviewApp(self.root, self.project_root, TOOL_DIR)
        self.root.update_idletasks()
        return self.app

    def test_all_review_states_are_always_visible_with_counts(self) -> None:
        self._seed(self.workspace.candidates, "candidate.png")
        self._seed(self.workspace.accepted, "accepted.png")
        self._seed(self.workspace.rejected, "rejected.png")
        self._seed(self.workspace.approved, "approved.png")
        self._seed_productive()

        app = self._make_app()

        self.assertEqual(
            tuple(app.queue_buttons),
            ("Kandidaten", "Akzeptiert", "Abgelehnt", "Freigegeben", "Produktiv"),
        )
        self.assertEqual(app.queue_button_text_vars["Kandidaten"].get(), "Kandidaten (1)")
        self.assertEqual(app.queue_button_text_vars["Akzeptiert"].get(), "Akzeptiert (1)")
        self.assertEqual(app.queue_button_text_vars["Abgelehnt"].get(), "Abgelehnt (1)")
        self.assertEqual(app.queue_button_text_vars["Freigegeben"].get(), "Freigegeben (1)")
        self.assertEqual(app.queue_button_text_vars["Produktiv"].get(), "Produktiv (1)")
        for button in app.queue_buttons.values():
            self.assertEqual(button.winfo_manager(), "pack")

    def test_all_six_gravestone_categories_are_selectable_and_persisted(self) -> None:
        candidate = self._seed(self.workspace.candidates, "candidate.png")
        app = self._make_app()

        self.assertEqual(tuple(app.category_buttons), GRAVESTONE_CATEGORIES)
        self.assertEqual(
            tuple(button.cget("text") for button in app.category_buttons.values()),
            GRAVESTONE_CATEGORIES,
        )
        app.category_buttons["Elfen"].invoke()
        self.assertEqual(app.category_var.get(), "Elfen")
        self.assertIn("Elfen", app.status_var.get())

        self.assertEqual(load_gravestone_category(candidate), "Elfen")

    def test_category_buttons_are_single_row(self) -> None:
        app = self._make_app()
        self.root.update_idletasks()
        rows = {button.winfo_y() for button in app.category_buttons.values()}
        self.assertEqual(len(rows), 1)
        frame = next(iter(app.category_buttons.values())).master
        self.assertLessEqual(
            max(button.winfo_x() + button.winfo_width() for button in app.category_buttons.values()),
            frame.winfo_width(),
        )

    def test_opening_check_and_alpha_editor_controls_are_available(self) -> None:
        self._seed(self.workspace.candidates, "candidate.png")
        app = self._make_app()

        self.assertIn("Öffnung prüfen", app.mode_buttons)
        self.assertEqual(app.alpha_editor_button.cget("text"), "Öffnung/Alpha anpassen")
        self.assertFalse(app.alpha_editor_button.instate(["disabled"]))
        before = (app.demo_offset_x_var.get(), app.demo_offset_y_var.get(), app.demo_zoom_var.get())
        app.demo_offset_x_var.set(0.6)
        app.demo_offset_y_var.set(-0.4)
        app.demo_zoom_var.set(2.0)
        app._reset_demo_portrait()
        self.assertEqual(
            (app.demo_offset_x_var.get(), app.demo_offset_y_var.get(), app.demo_zoom_var.get()),
            before,
        )

    def test_demo_portrait_preset_is_saved_and_reloaded_per_gravestone(self) -> None:
        first = self._seed(self.workspace.candidates, "candidate_1.png")
        second = self._seed(self.workspace.candidates, "candidate_2.png")
        save_gravestone_portrait_preset(second, -0.6, 0.4, 2.5)
        app = self._make_app()

        self.assertEqual(app.save_preset_button.cget("text"),
                         "Als Grabstein-Voreinstellung speichern")
        app.demo_offset_x_var.set(0.35)
        app.demo_offset_y_var.set(-0.2)
        app.demo_zoom_var.set(1.75)
        app.save_preset_button.invoke()
        self.assertEqual(load_gravestone_portrait_preset(first), (0.35, -0.2, 1.75))

        app.next()
        self.assertEqual(
            (app.demo_offset_x_var.get(), app.demo_offset_y_var.get(), app.demo_zoom_var.get()),
            (-0.6, 0.4, 2.5),
        )
        app.previous()
        self.assertEqual(
            (app.demo_offset_x_var.get(), app.demo_offset_y_var.get(), app.demo_zoom_var.get()),
            (0.35, -0.2, 1.75),
        )

    def test_saved_category_selects_one_button_and_controls_approval(self) -> None:
        accepted = self._seed(self.workspace.accepted, "accepted.png")
        save_gravestone_category(accepted, "Zwerge")
        app = self._make_app()
        app.queue_var.set("Akzeptiert")
        app._switch_queue()

        self.assertEqual(app.category_var.get(), "Zwerge")
        self.assertEqual(app.category_buttons["Zwerge"].cget("relief"), "sunken")
        self.assertEqual(
            sum(button.cget("relief") == "sunken" for button in app.category_buttons.values()),
            1,
        )
        app.category_var.set("")
        app._update_action_states()
        self.assertTrue(app.approve_button.instate(["disabled"]))
        app.category_buttons["Spezial"].invoke()
        self.assertEqual(app.category_var.get(), "Spezial")
        self.assertEqual(app.category_buttons["Spezial"].cget("relief"), "sunken")
        self.assertFalse(app.approve_button.instate(["disabled"]))
        self.assertEqual(
            sum(button.cget("relief") == "sunken" for button in app.category_buttons.values()),
            1,
        )

    def test_switching_states_loads_the_correct_files_and_actions(self) -> None:
        self._seed(self.workspace.candidates, "candidate.png")
        self._seed(self.workspace.accepted, "accepted.png")
        self._seed(self.workspace.rejected, "rejected.png")
        self._seed(self.workspace.approved, "approved.png")
        self._seed_productive()
        app = self._make_app()

        expectations = {
            "Kandidaten": (self.workspace.candidates, "AKZEPTIEREN", "Kandidat"),
            "Akzeptiert": (self.workspace.accepted, "ENTFERNEN", "Akzeptiert"),
            "Abgelehnt": (self.workspace.rejected, "PNG LÖSCHEN", "Abgelehnt"),
            "Freigegeben": (self.workspace.approved, None, "Freigegeben"),
            "Produktiv": (self.workspace.graveyard, None, "Produktiv"),
        }
        for queue_name, (expected_parent, expected_action, expected_title) in expectations.items():
            with self.subTest(queue=queue_name):
                app.queue_var.set(queue_name)
                app._switch_queue()
                self.root.update_idletasks()
                self.assertIsNotNone(app.current_path())
                self.assertEqual(app.current_path().parent.resolve(), expected_parent.resolve())
                self.assertEqual(app.filebox.cget("text"), expected_title)
                if expected_action is None:
                    self.assertEqual(app.readonly_action_label.winfo_manager(), "pack")
                else:
                    visible_texts = {
                        widget.cget("text")
                        for widget in (
                            app.accept_button,
                            app.reject_button,
                            app.remove_accepted_button,
                            app.approve_button,
                            app.approve_all_button,
                            app.delete_rejected_button,
                        )
                        if widget.winfo_manager() == "pack"
                    }
                    self.assertIn(expected_action, visible_texts)

    def test_productive_inventory_is_readonly_and_uses_manifest_metadata(self) -> None:
        productive = self._seed_productive()
        app = self._make_app()
        app.queue_var.set("Produktiv")
        app._switch_queue()

        self.assertEqual(app.current_path(), productive)
        self.assertEqual(app.category_var.get(), "Elfen")
        self.assertEqual(
            (app.demo_offset_x_var.get(), app.demo_offset_y_var.get(), app.demo_zoom_var.get()),
            (0.25, -0.35, 1.8),
        )
        self.assertEqual(app.readonly_action_label.winfo_manager(), "pack")
        self.assertTrue(app.alpha_editor_button.instate(["disabled"]))
        self.assertTrue(app.save_preset_button.instate(["disabled"]))
        self.assertTrue(all(button.cget("state") == "disabled" for button in app.category_buttons.values()))

    def test_three_presentation_modes_are_visible_and_keep_queue_data(self) -> None:
        self._seed(self.workspace.accepted, "accepted_1.png")
        self._seed(self.workspace.accepted, "accepted_2.png")
        app = self._make_app()
        app.queue_var.set("Akzeptiert")
        app._switch_queue()

        self.assertEqual(
            tuple(app.browser_view_buttons),
            ("Einzelansicht", "Galerie", "Listenansicht"),
        )
        self.assertEqual(len(app.candidates), 2)

        app.browser_view_var.set("Galerie")
        app._switch_browser_view()
        self.root.update_idletasks()
        self.assertEqual(app.gallery_view_frame.winfo_manager(), "pack")
        self.assertEqual(len(app.gallery_item_buttons), 2)
        self.assertEqual(len(app.candidates), 2)
        self.assertTrue(app.remove_accepted_button.instate(["disabled"]))
        self.assertTrue(app.approve_button.instate(["disabled"]))
        self.assertFalse(app.approve_all_button.instate(["disabled"]))

        app.browser_view_var.set("Listenansicht")
        app._switch_browser_view()
        self.root.update_idletasks()
        self.assertEqual(app.list_view_frame.winfo_manager(), "pack")
        self.assertEqual(len(app.list_tree.get_children()), 2)
        self.assertEqual(len(app.candidates), 2)
        self.assertTrue(app.remove_accepted_button.instate(["disabled"]))
        self.assertTrue(app.approve_button.instate(["disabled"]))
        self.assertFalse(app.approve_all_button.instate(["disabled"]))

    def test_gallery_and_list_selection_open_the_item_in_single_view(self) -> None:
        self._seed(self.workspace.rejected, "rejected_a.png")
        self._seed(self.workspace.rejected, "rejected_b.png")
        app = self._make_app()
        app.queue_var.set("Abgelehnt")
        app._switch_queue()

        app.browser_view_var.set("Galerie")
        app._switch_browser_view()
        app._open_browser_index(1)
        self.root.update_idletasks()
        self.assertEqual(app.browser_view_var.get(), "Einzelansicht")
        self.assertEqual(app.single_view_frame.winfo_manager(), "pack")
        self.assertEqual(app.current_path().name, "rejected_b.png")
        self.assertEqual(app.queue_var.get(), "Abgelehnt")
        self.assertEqual(app.delete_rejected_button.winfo_manager(), "pack")

        app.browser_view_var.set("Listenansicht")
        app._switch_browser_view()
        app._open_browser_index(0)
        self.root.update_idletasks()
        self.assertEqual(app.browser_view_var.get(), "Einzelansicht")
        self.assertEqual(app.current_path().name, "rejected_a.png")
        self.assertEqual(app.queue_var.get(), "Abgelehnt")

    def test_empty_gallery_and_list_views_are_safe(self) -> None:
        app = self._make_app()
        for display_name in ("Galerie", "Listenansicht"):
            with self.subTest(display=display_name):
                app.browser_view_var.set(display_name)
                app._switch_browser_view()
                self.root.update_idletasks()
                self.assertIsNone(app.current_path())
                self.assertEqual(len(app.list_tree.get_children()), 0)

    def test_gallery_reuses_cached_thumbnails_and_tiles_when_unchanged(self) -> None:
        self._seed(self.workspace.accepted, "accepted_1.png")
        self._seed(self.workspace.accepted, "accepted_2.png")
        app = self._make_app()
        app.queue_var.set("Akzeptiert")
        app._switch_queue()
        app.browser_view_var.set("Galerie")
        app._switch_browser_view()
        self.root.update_idletasks()

        first_buttons = list(app.gallery_item_buttons)
        first_photos = list(app.gallery_photos)
        first_cache_size = len(app._gallery_thumbnail_cache)

        app._refresh_gallery()
        self.root.update_idletasks()

        self.assertEqual(len(first_buttons), 2)
        self.assertIs(app.gallery_item_buttons[0], first_buttons[0])
        self.assertIs(app.gallery_item_buttons[1], first_buttons[1])
        self.assertIs(app.gallery_photos[0], first_photos[0])
        self.assertIs(app.gallery_photos[1], first_photos[1])
        self.assertEqual(len(app._gallery_thumbnail_cache), first_cache_size)

        app.browser_view_var.set("Listenansicht")
        app._switch_browser_view()
        app.browser_view_var.set("Galerie")
        app._switch_browser_view()
        self.root.update_idletasks()

        self.assertIs(app.gallery_item_buttons[0], first_buttons[0])
        self.assertIs(app.gallery_photos[0], first_photos[0])

    def test_thumbnail_cache_refreshes_when_png_signature_changes(self) -> None:
        path = self._seed(self.workspace.accepted, "accepted.png")
        app = self._make_app()

        first = app._gallery_thumbnail(path)
        self.assertIs(app._gallery_thumbnail(path), first)

        stat = path.stat()
        # Change only the timestamp; path and file size stay stable.  The cache
        # must still detect that the backing PNG may have changed.
        path.touch()
        if path.stat().st_mtime_ns == stat.st_mtime_ns:
            import os
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

        second = app._gallery_thumbnail(path)
        self.assertIsNot(second, first)
        self.assertEqual(len(app._gallery_thumbnail_cache), 1)

    def test_navigation_works_in_accepted_and_rejected_views(self) -> None:
        self._seed(self.workspace.accepted, "accepted_1.png")
        self._seed(self.workspace.accepted, "accepted_2.png")
        self._seed(self.workspace.rejected, "rejected_1.png")
        self._seed(self.workspace.rejected, "rejected_2.png")
        app = self._make_app()

        for queue_name, expected_parent in (
            ("Akzeptiert", self.workspace.accepted),
            ("Abgelehnt", self.workspace.rejected),
        ):
            with self.subTest(queue=queue_name):
                app.queue_var.set(queue_name)
                app._switch_queue()
                first = app.current_path()
                app.next()
                second = app.current_path()
                self.assertNotEqual(first, second)
                self.assertEqual(second.parent.resolve(), expected_parent.resolve())
                app.previous()
                self.assertEqual(app.current_path(), first)

    def test_gallery_first_open_uses_available_container_width(self) -> None:
        for idx in range(12):
            self._seed(self.workspace.candidates, f"candidate_{idx:02d}.png")
        app = self._make_app()

        # Reproduce the original first-open condition: the not-yet-mapped canvas
        # can still report one pixel while its already laid-out parent knows the
        # real available width.  Gallery layout must use that parent width.
        original_canvas_width = app.gallery_canvas.winfo_width
        original_frame_width = app.gallery_view_frame.winfo_width
        original_container_width = app.browser_container.winfo_width
        try:
            app.gallery_canvas.winfo_width = lambda: 1
            app.gallery_view_frame.winfo_width = lambda: 1
            app.browser_container.winfo_width = lambda: 1080
            self.assertEqual(app._gallery_column_count(), 6)
        finally:
            app.gallery_canvas.winfo_width = original_canvas_width
            app.gallery_view_frame.winfo_width = original_frame_width
            app.browser_container.winfo_width = original_container_width

    def test_legacy_gallery_name_is_still_accepted_internally(self) -> None:
        self._seed(self.workspace.candidates, "candidate.png")
        app = self._make_app()
        app.browser_view_var.set("Abbildungsansicht")
        app._switch_browser_view()
        self.root.update_idletasks()
        self.assertEqual(app.gallery_view_frame.winfo_manager(), "pack")
        self.assertEqual(len(app.gallery_item_buttons), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
