# -*- coding: utf-8 -*-
"""Focused regression tests for the responsive gravestone-card graveyard."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile


g = None
REPO_ROOT = None


def load_checker(path: Path):
    spec = importlib.util.spec_from_file_location("ggc_graveyard_cards", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GravestoneTemplateTests(unittest.TestCase):
    def setUp(self):
        self.templates = REPO_ROOT / "assets" / "graveyard"

    def test_dynamic_discovery_finds_all_manifest_templates(self):
        paths = g.discover_gravestone_templates(self.templates)
        manifest = json.loads((self.templates / g.GRAVESTONE_MANIFEST_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(len(paths), len(manifest["templates"]))
        self.assertGreaterEqual(len(paths), 3)
        self.assertEqual(len({hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}), len(paths))
        supported_sizes = {
            g.GRAVESTONE_MASTER_SIZE,
            tuple(dimension // 2 for dimension in g.GRAVESTONE_MASTER_SIZE),
        }
        for path in paths:
            with g.Image.open(path) as image:
                self.assertIn(image.size, supported_sizes)

    def test_discovery_scales_beyond_three_without_hardcoded_ids(self):
        with tempfile.TemporaryDirectory(prefix="ggc-gravestone-discovery-") as temp:
            root = Path(temp)
            for number in (1, 2, 3, 4, 10):
                g.Image.new("RGBA", (32, 40), (number, 20, 30, 255)).save(
                    root / f"gravestone_{number:03d}.png"
                )
            (root / "other.png").write_bytes(b"test")
            g.generate_gravestone_manifest(root, generated_at="2026-09-12T12:00:00+02:00")
            self.assertEqual(len(g.discover_gravestone_templates(root)), 5)

    def test_render_all_templates_wide_tall_missing_and_corrupt_portraits(self):
        before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in g.discover_gravestone_templates(self.templates)}
        member = g.Member("m1", "Äon", className="Mage", lifeStatus="dead", deathDate="2026-09-12")
        with tempfile.TemporaryDirectory(prefix="ggc-gravestone-portraits-") as temp:
            root = Path(temp)
            g.Image.new("RGB", (900, 240), "#a03020").save(root / "wide.png")
            g.Image.new("RGB", (240, 900), "#2050a0").save(root / "tall.png")
            (root / "corrupt.png").write_bytes(b"not an image")
            portraits = (root / "wide.png", root / "tall.png", None, root / "corrupt.png")
            for path in g.discover_gravestone_templates(self.templates):
                frame = g.prepare_gravestone_template(path)
                for portrait in portraits:
                    card = g.render_gravestone_card(member, frame, portrait)
                    self.assertEqual(card.size, g.GRAVESTONE_CARD_SIZE)
                    self.assertEqual(card.mode, "RGBA")
            frame = g.prepare_gravestone_template(
                g.discover_gravestone_templates(self.templates)[0]
            )
            with g.Image.open(root / "wide.png") as source:
                cached_portrait = g.ImageOps.exif_transpose(source).convert("RGBA").copy()
            disk_card = g.render_gravestone_card(member, frame, root / "wide.png")
            cached_card = g.render_gravestone_card(
                member,
                frame,
                root / "wide.png",
                portrait_image=cached_portrait,
            )
            self.assertEqual(cached_card.tobytes(), disk_card.tobytes())
        after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in g.discover_gravestone_templates(self.templates)}
        self.assertEqual(after, before)

    def test_shared_geometry_and_short_long_text_stay_inside_safe_area(self):
        self.assertEqual(g.GRAVESTONE_CARD_SIZE, (220, 300))
        self.assertEqual(g.GRAVESTONE_PORTRAIT_BOX, (304, 304, 770, 770))
        self.assertEqual(g.GRAVESTONE_TEXT_SAFE_AREA, (250, 905, 824, 1090))
        safe = g._scaled_gravestone_box(g.GRAVESTONE_TEXT_SAFE_AREA, g.GRAVESTONE_CARD_SIZE)
        for name in ("Bífi", "ÄußerstlangerUnicodecharakternameOhneRandClipping"):
            member = g.Member(
                "m1", name, className="Warrior", lifeStatus="dead", deathDate="2026-09-12",
            )
            layout = g.gravestone_text_layout(member)
            self.assertEqual(set(layout), {"name", "class", "death_date"})
            for line in layout.values():
                left, top, right, bottom = line["bbox"]
                self.assertGreaterEqual(left, safe[0])
                self.assertGreaterEqual(top, safe[1])
                self.assertLessEqual(right, safe[2])
                self.assertLessEqual(bottom, safe[3])
            self.assertLessEqual(
                layout["name"]["font"].size,
                round(g.GRAVESTONE_TEXT_FONT_SIZES["name"] * g.GRAVESTONE_CARD_SIZE[1]
                      / g.GRAVESTONE_MASTER_SIZE[1]),
            )

    def test_new_background_uses_undistorted_cover_and_is_not_modified(self):
        path = self.templates / "Background_001.png"
        self.assertEqual(g.GRAVESTONE_BACKGROUND_PATH.as_posix(),
                         "assets/graveyard/Background_001.png")
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        with g.Image.open(path) as source:
            source = g.ImageOps.exif_transpose(source).convert("RGB")
            for size in ((480, 720), (1400, 480)):
                expected = g.ImageOps.fit(
                    source, size, method=g.Image.Resampling.LANCZOS,
                )
                actual = g.prepare_graveyard_background(path, size)
                self.assertEqual(actual.size, size)
                self.assertEqual(actual.tobytes(), expected.tobytes())
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)


class GravestoneAssignmentTests(unittest.TestCase):
    def test_legacy_project_gets_assignment_and_save_reload_keeps_it(self):
        model = g.GuildModel()
        model.load_payload({"formatVersion": 2, "members": [
            {"id": "m0042", "name": "Janos", "lifeStatus": "dead", "className": "Warrior",
             "gravestoneTemplate": "gravestone_001.png"},
        ]})
        member = model.members[0]
        self.assertTrue(member.gravestoneTemplate)
        self.assertTrue(member.graveTemplateId)
        self.assertTrue(model.dirty)
        with tempfile.TemporaryDirectory(prefix="ggc-gravestone-project-") as temp:
            project = Path(temp) / "legacy.ggc"
            model.save(project)
            stored = json.loads(project.read_text(encoding="utf-8"))
            self.assertEqual(stored["formatVersion"], g.PROJECT_FORMAT_VERSION)
            self.assertEqual(stored["members"][0]["gravestoneTemplate"], member.gravestoneTemplate)
            self.assertEqual(stored["members"][0]["graveTemplateId"], member.graveTemplateId)
            loaded = g.GuildModel()
            loaded.load(project)
            self.assertEqual(loaded.members[0].gravestoneTemplate, member.gravestoneTemplate)
            self.assertEqual(loaded.members[0].graveTemplateId, member.graveTemplateId)
            self.assertFalse(loaded.dirty)

    def test_existing_assignment_and_member_data_remain_unchanged(self):
        payload = {"members": [{
            "id": "m7", "name": "Bífi", "lifeStatus": "dead", "deathDate": "2025-01-02",
            "className": "Rogue", "spec": "Combat", "note": "Unverändert",
            "gravestoneTemplate": "gravestone_003.png",
        }]}
        model = g.GuildModel()
        model.load_payload(payload)
        self.assertEqual(model.members[0].gravestoneTemplate, "gravestone_003.png")
        self.assertEqual(model.members[0].note, "Unverändert")
        self.assertEqual(model.members[0].spec, "Combat")
        self.assertTrue(model.members[0].graveTemplateId)
        self.assertTrue(model.dirty)

    def test_new_deaths_get_templates_without_immediate_repeats(self):
        model = g.GuildModel()
        model.new_empty()
        for index in range(12):
            member = model.add_member(f"Char{index}")
            model.set_member_life_status(member.id, "dead")
        assignments = [member.gravestoneTemplate for member in model.members]
        assignment_ids = [member.graveTemplateId for member in model.members]
        self.assertTrue(all(assignments))
        self.assertEqual(len(set(assignment_ids)), len(assignment_ids))

    def test_old_project_defaults_and_multiple_adjustments_roundtrip(self):
        model = g.GuildModel()
        model.load_payload({"members": [
            {"id": "m1", "name": "Alt", "lifeStatus": "dead"},
            {"id": "m2", "name": "Neu", "lifeStatus": "dead",
             "portraitOffsetX": -0.35, "portraitOffsetY": 0.6, "portraitZoom": 1.45},
        ]})
        self.assertEqual(
            (model.members[0].portraitOffsetX, model.members[0].portraitOffsetY,
             model.members[0].portraitZoom),
            (0.0, 0.0, 1.0),
        )
        model.set_gravestone_portrait_adjustment(
            "m1", 0.4, -0.25, 1.2, "12.09.2024",
        )
        with tempfile.TemporaryDirectory(prefix="ggc-gravestone-adjustments-") as temp:
            path = Path(temp) / "adjustments.ggc"
            model.save(path)
            loaded = g.GuildModel()
            loaded.load(path)
        self.assertEqual(
            [(m.portraitOffsetX, m.portraitOffsetY, m.portraitZoom) for m in loaded.members],
            [(0.4, -0.25, 1.2), (-0.35, 0.6, 1.45)],
        )
        self.assertEqual(loaded.members[0].deathDate, "2024-09-12")

    def test_invalid_death_date_does_not_partially_change_adjustment(self):
        model = g.GuildModel()
        member = g.Member(
            "m1", "Tot", lifeStatus="dead", deathDate="2024-01-02",
            portraitOffsetX=0.2, portraitOffsetY=-0.3, portraitZoom=1.4,
        )
        model.members = [member]
        with self.assertRaises(ValueError):
            model.set_gravestone_portrait_adjustment("m1", 0.9, 0.8, 1.9, "kein Datum")
        self.assertEqual(
            (member.portraitOffsetX, member.portraitOffsetY, member.portraitZoom,
             member.deathDate),
            (0.2, -0.3, 1.4, "2024-01-02"),
        )

    def test_adjustment_ranges_and_reset_defaults(self):
        model = g.GuildModel()
        model.new_empty()
        member = g.Member("m1", "Tot", lifeStatus="dead")
        model.members.append(member)
        model.set_gravestone_portrait_adjustment("m1", 8, -9, 7)
        self.assertEqual(
            (member.portraitOffsetX, member.portraitOffsetY, member.portraitZoom),
            (1.0, -1.0, 2.0),
        )
        model.set_gravestone_portrait_adjustment("m1", 0, 0, 1)
        payload = member.to_dict()
        self.assertNotIn("portraitOffsetX", payload)
        self.assertNotIn("portraitOffsetY", payload)
        self.assertNotIn("portraitZoom", payload)


class PortraitAdjustmentTests(unittest.TestCase):
    def test_automatic_mode_is_the_existing_centered_cover(self):
        source = g.Image.new("RGB", (301, 101))
        for x in range(source.width):
            for y in range(source.height):
                source.putpixel((x, y), (x % 256, y % 256, 30))
        expected = g.ImageOps.fit(source, (100, 100), method=g.Image.Resampling.LANCZOS)
        actual = g.fit_gravestone_portrait(source, (100, 100), 0, 0, 1)
        self.assertEqual(actual.tobytes(), expected.tobytes())

    def test_horizontal_vertical_pan_zoom_and_combination(self):
        horizontal = g.Image.new("RGB", (300, 100))
        vertical = g.Image.new("RGB", (100, 300))
        for x in range(300):
            color = (220, 30, 30) if x < 100 else ((30, 220, 30) if x < 200 else (30, 30, 220))
            for y in range(100):
                horizontal.putpixel((x, y), color)
                vertical.putpixel((y, x), color)
        left = g.fit_gravestone_portrait(horizontal, (100, 100), 1, 0, 1)
        right = g.fit_gravestone_portrait(horizontal, (100, 100), -1, 0, 1)
        top = g.fit_gravestone_portrait(vertical, (100, 100), 0, 1, 1)
        bottom = g.fit_gravestone_portrait(vertical, (100, 100), 0, -1, 1)
        zoomed = g.fit_gravestone_portrait(horizontal, (100, 100), 0.45, -0.5, 1.6)
        self.assertGreater(left.getpixel((50, 50))[0], left.getpixel((50, 50))[2])
        self.assertGreater(right.getpixel((50, 50))[2], right.getpixel((50, 50))[0])
        self.assertGreater(top.getpixel((50, 50))[0], top.getpixel((50, 50))[2])
        self.assertGreater(bottom.getpixel((50, 50))[2], bottom.getpixel((50, 50))[0])
        self.assertEqual(zoomed.size, (100, 100))

    def test_mouse_drag_delta_changes_both_normalized_offsets(self):
        self.assertEqual(g.shifted_portrait_offsets(0, 0, 25, -50, (100, 200)), (0.5, -0.5))
        self.assertEqual(g.shifted_portrait_offsets(0.8, -0.8, 100, -100, (100, 100)), (1.0, -1.0))


class GraveyardLayoutTests(unittest.TestCase):
    def test_empty_one_multiple_and_many_layouts(self):
        self.assertEqual(g.graveyard_grid_layout(1200, 0)["positions"], ())
        self.assertEqual(len(g.graveyard_grid_layout(1200, 1)["positions"]), 1)
        self.assertEqual(len(g.graveyard_grid_layout(1200, 7)["positions"]), 7)
        self.assertEqual(len(g.graveyard_grid_layout(1200, 50)["positions"]), 50)

    def test_columns_respond_to_window_width_and_cards_do_not_overlap(self):
        narrow = g.graveyard_grid_layout(520, 20)
        desktop = g.graveyard_grid_layout(1220, 20)
        wide = g.graveyard_grid_layout(1800, 20)
        self.assertLess(narrow["columns"], desktop["columns"])
        self.assertLess(desktop["columns"], wide["columns"])
        self.assertEqual(desktop["columns"], 5)
        self.assertGreater(wide["content_height"], g.GRAVESTONE_CARD_SIZE[1])

    def test_existing_search_filter_and_sort_contract_is_preserved(self):
        members = [
            g.Member("m1", "Zeta", className="Mage", lifeStatus="dead"),
            g.Member("m2", "Alpha", className="Warrior", lifeStatus="dead"),
            g.Member("m3", "Active", className="Mage", lifeStatus="active"),
        ]
        self.assertEqual(
            [member.id for member in g.filter_and_sort_members(members, "Friedhof", "a")],
            ["m2", "m1"],
        )

    def test_default_sort_is_newest_death_first_and_date_change_reorders(self):
        members = [
            g.Member("m1", "Alt", lifeStatus="dead", deathDate="2024-01-02"),
            g.Member("m2", "Neu", lifeStatus="dead", deathDate="2026-03-04"),
            g.Member("m3", "Ohne", lifeStatus="dead", deathDate=""),
        ]
        column, descending = g.default_sort_for_tab("Friedhof")
        self.assertEqual((column, descending), ("death_date", True))
        self.assertEqual(
            [member.id for member in g.sort_members(members, column, descending)],
            ["m2", "m1", "m3"],
        )
        model = g.GuildModel()
        model.members = members
        model.set_gravestone_portrait_adjustment("m1", 0, 0, 1, "2027-05-06")
        self.assertEqual(
            [member.id for member in g.sort_members(model.members, column, descending)],
            ["m1", "m2", "m3"],
        )


class GraveyardExportTests(unittest.TestCase):
    def make_model(self):
        model = g.GuildModel()
        model.new_empty()
        model.members = [g.Member(
            "m0042", "Bífi", className="Rogue", lifeStatus="dead",
            deathDate="2025-04-03", gravestoneTemplate="gravestone_002.png",
            portraitOffsetX=0.35, portraitOffsetY=-0.2, portraitZoom=1.55,
        )]
        return model

    def assert_graveyard_roundtrip(self, payload):
        loaded = g.GuildModel()
        loaded.load_payload(payload)
        member = loaded.members[0]
        self.assertEqual(member.lifeStatus, "dead")
        self.assertEqual(member.deathDate, "2025-04-03")
        self.assertEqual(member.gravestoneTemplate, "gravestone_002.png")
        self.assertEqual(
            (member.portraitOffsetX, member.portraitOffsetY, member.portraitZoom),
            (0.35, -0.2, 1.55),
        )

    def test_normal_export_contains_and_restores_all_graveyard_fields(self):
        model = self.make_model()
        with tempfile.TemporaryDirectory(prefix="ggc-graveyard-export-") as temp:
            target = Path(temp) / "export.ggc"
            fake_app = SimpleNamespace(
                model=model, status_var=SimpleNamespace(set=lambda _value: None),
            )
            with patch.object(g.filedialog, "asksaveasfilename", return_value=str(target)), \
                 patch.object(g.messagebox, "showinfo"), \
                 patch.object(g.messagebox, "showerror"):
                g.GuildGearCheckerApp.export_project(fake_app)
            self.assertTrue(target.is_file())
            self.assert_graveyard_roundtrip(json.loads(target.read_text(encoding="utf-8")))

    def test_portrait_package_contains_dead_portraits_and_restores_graveyard_fields(self):
        model = self.make_model()
        with tempfile.TemporaryDirectory(prefix="ggc-graveyard-package-") as temp:
            root = Path(temp)
            portraits = root / "portraits"
            portraits.mkdir(parents=True)
            (portraits / "m0042.png").write_bytes(b"historical portrait")
            target = root / "project.zip"
            summary = g.create_project_package(model, target, portraits)
            self.assertEqual(summary.portrait_count, 1)
            self.assertEqual(summary.historical_portrait_count, 0)
            with zipfile.ZipFile(target) as archive:
                self.assertIn("portraits/m0042.png", archive.namelist())
                payload = json.loads(archive.read("project.ggc").decode("utf-8"))
            self.assert_graveyard_roundtrip(payload)


class GraveyardTkTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="ggc-graveyard-ui-")
        self.root = Path(self.temp_dir.name)
        (self.root / "assets" / "graveyard").mkdir(parents=True)
        for source in g.discover_gravestone_templates(REPO_ROOT / "assets" / "graveyard"):
            shutil.copy2(source, self.root / "assets" / "graveyard" / source.name)
        shutil.copy2(
            REPO_ROOT / "assets" / "graveyard" / g.GRAVESTONE_MANIFEST_FILENAME,
            self.root / "assets" / "graveyard" / g.GRAVESTONE_MANIFEST_FILENAME,
        )
        shutil.copy2(
            REPO_ROOT / "assets" / "graveyard" / "Background_001.png",
            self.root / "assets" / "graveyard" / "Background_001.png",
        )
        self.app = None

    def tearDown(self):
        if self.app is not None:
            try:
                self.app.destroy()
            except Exception:
                pass
        self.temp_dir.cleanup()

    def test_canvas_renders_cards_with_adjustment_action_and_without_legacy_rows(self):
        with patch.object(g, "app_base_dir", return_value=self.root), \
             patch.dict(os.environ, {"GGC_DISABLE_ICON_DOWNLOAD": "1"}):
            try:
                self.app = g.GuildGearCheckerApp()
            except g.tk.TclError as exc:
                self.skipTest(f"Tk unavailable: {exc}")
            self.app.model.new_empty()
            self.app.model.members = [
                g.Member(f"m{index}", f"Tot{index}", className="Mage", lifeStatus="dead",
                         deathDate="2026-09-12")
                for index in range(8)
            ]
            for member, template in zip(
                    self.app.model.members, self.app.model.gravestone_inventory().templates):
                member.graveTemplateId = template.grave_template_id
                member.gravestoneTemplate = template.filename
            self.app.switch_tab("Friedhof")
            self.app.update_idletasks()
            self.assertIsNotNone(self.app._graveyard_bg_ref)
            self.assertEqual(len(self.app._graveyard_render_manifest), 8)
            self.assertEqual(len(self.app.graveyard_canvas.find_withtag("gravestone-card")), 8)
            self.assertEqual(self.app.graveyard_canvas.find_withtag("memberrow"), ())
            self.assertTrue(self.app.graveyard_canvas.tag_bind("member::m0", "<Button-1>"))
            self.assertEqual(self.app.detail_outer.winfo_manager(), "")
            self.assertGreaterEqual(
                self.app.graveyard_canvas.bbox("background")[2],
                self.app.graveyard_canvas.winfo_width(),
            )
            first_cards = tuple(self.app._graveyard_card_refs)
            self.app.render_graveyard()
            self.assertEqual(
                [first is second for first, second in zip(first_cards, self.app._graveyard_card_refs)],
                [True] * len(first_cards),
            )
            self.app.switch_tab("Gildenliste")
            self.assertEqual(self.app.detail_outer.winfo_manager(), "grid")

    def test_editor_drag_zoom_apply_and_reset(self):
        with patch.object(g, "app_base_dir", return_value=self.root), \
             patch.dict(os.environ, {"GGC_DISABLE_ICON_DOWNLOAD": "1"}):
            try:
                self.app = g.GuildGearCheckerApp()
            except g.tk.TclError as exc:
                self.skipTest(f"Tk unavailable: {exc}")
            self.app.model.new_empty()
            member = g.Member(
                "m1", "Tot", className="Mage", lifeStatus="dead",
                deathDate="2023-01-01",
            )
            other = g.Member(
                "m2", "Andere", className="Mage", lifeStatus="dead",
                deathDate="2024-01-01",
            )
            self.app.model.members = [member, other]
            for target, template in zip(
                    self.app.model.members, self.app.model.gravestone_inventory().templates):
                target.graveTemplateId = template.grave_template_id
                target.gravestoneTemplate = template.filename
            self.app.current_tab = "Friedhof"

            def descendants(widget):
                result = []
                for child in widget.winfo_children():
                    result.append(child)
                    result.extend(descendants(child))
                return result

            original_template_id = member.graveTemplateId
            editor = self.app.open_gravestone_portrait_editor(member.id)
            widgets = descendants(editor)
            buttons = {widget.cget("text"): widget for widget in widgets if isinstance(widget, g.tk.Button)}
            buttons["▶"].invoke()
            buttons[g.tr("graveyard.cancel")].invoke()
            self.assertEqual(member.graveTemplateId, original_template_id)

            editor = self.app.open_gravestone_portrait_editor(member.id)
            widgets = descendants(editor)
            canvas = next(widget for widget in widgets if isinstance(widget, g.tk.Canvas))
            scale = next(widget for widget in widgets if isinstance(widget, g.tk.Scale))
            date_entry = next(widget for widget in widgets if isinstance(widget, g.tk.Entry))
            buttons = {widget.cget("text"): widget for widget in widgets if isinstance(widget, g.tk.Button)}
            buttons["▶"].invoke()
            self.assertTrue(canvas.bind("<ButtonPress-1>"))
            self.assertTrue(canvas.bind("<B1-Motion>"))
            scale.set(1.5)
            date_entry.delete(0, "end")
            date_entry.insert(0, "02.02.2025")
            buttons[g.tr("graveyard.apply")].invoke()
            self.assertEqual(member.portraitZoom, 1.5)
            self.assertEqual(member.deathDate, "2025-02-02")
            self.assertEqual(self.app.filtered_members("Friedhof")[0].id, member.id)
            self.assertTrue(self.app.model.dirty)

            editor = self.app.open_gravestone_portrait_editor(member.id)
            widgets = descendants(editor)
            buttons = {widget.cget("text"): widget for widget in widgets if isinstance(widget, g.tk.Button)}
            scales = [widget for widget in widgets if isinstance(widget, g.tk.Scale)]
            scales[1].set(1.35)
            buttons[g.tr("graveyard.reset")].invoke()
            buttons[g.tr("graveyard.apply")].invoke()
            self.assertNotEqual(member.graveTemplateId, original_template_id)
            self.assertEqual(
                (member.portraitOffsetX, member.portraitOffsetY, member.portraitZoom),
                (0.0, 0.0, 1.5),
            )
            self.assertEqual(
                (member.textOffsetX, member.textOffsetY, member.textScale),
                (0.0, 0.0, 1.0),
            )


def main() -> int:
    global g, REPO_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    REPO_ROOT = args.repo_root.resolve()
    g = load_checker(REPO_ROOT / "app" / "GuildGearChecker.py")
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
