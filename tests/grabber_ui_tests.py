# -*- coding: utf-8 -*-
"""Focused offline tests for the Grabber banner and portrait preview UI."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass, replace
import gc
import hashlib
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch


grabber = None
REPO_ROOT = None


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class GrabberUiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="ggc-grabber-ui-")
        self.root = Path(self.temp_dir.name)
        (self.root / "assets").mkdir(parents=True)
        self.project_path = self.root / "guild.ggc"
        self.portraits = self.root / "portraits"
        self.portraits.mkdir(parents=True)
        self.banner_source = REPO_ROOT / "assets" / "grabber_banner.png"
        self.banner_hash = hashlib.sha256(self.banner_source.read_bytes()).hexdigest()
        self.apps = []
        self.old_language = grabber.tr.__globals__["_translator"].language

    def tearDown(self):
        for app in reversed(self.apps):
            try:
                app._on_close()
            except Exception:
                try:
                    app.destroy()
                except Exception:
                    pass
            app.worker.join(timeout=2)
        grabber.tr.__globals__["_translator"].language = self.old_language
        self.assertEqual(
            hashlib.sha256(self.banner_source.read_bytes()).hexdigest(),
            self.banner_hash,
            "Das vorhandene Banner darf durch UI oder Tests nicht verändert werden.",
        )
        self.temp_dir.cleanup()

    def make_image(self, path: Path, size=(120, 240), color=(90, 130, 180)) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        grabber.Image.new("RGB", size, color).save(path)

    def make_app(self, names=("Janos", "Ánníe"), banner=True, language="de", project=True):
        if banner:
            shutil.copyfile(self.banner_source, self.root / "assets" / "grabber_banner.png")
        grabber.tr.__globals__["_translator"].language = language
        suite_patch = patch.object(grabber, "suite_root_dir", return_value=self.root)
        suite_patch.start()
        self.addCleanup(suite_patch.stop)
        app = grabber.App(
            initial_characters=[
                {"memberId": f"m{index:04d}", "characterName": name}
                for index, name in enumerate(names, 1)
            ],
            project_path=str(self.project_path) if project else None,
        )
        app.withdraw()
        app.update_idletasks()
        self.apps.append(app)
        return app

    def test_guild_list_save_button_requires_project(self):
        without_project = self.make_app(project=False)
        with_project = self.make_app()
        english_without_project = self.make_app(project=False, language="en")
        self.assertEqual(without_project.save_guild_list_btn.cget("text"), "Gildenliste speichern")
        self.assertEqual(english_without_project.save_guild_list_btn.cget("text"), "Save Guild Roster")
        self.assertIn("disabled", without_project.save_guild_list_btn.state())
        self.assertIn("disabled", english_without_project.save_guild_list_btn.state())
        self.assertNotIn("disabled", with_project.save_guild_list_btn.state())

    def test_gravestone_editor_state_keeps_saved_and_draft_values_separate(self):
        @dataclass(frozen=True)
        class MemberFixture:
            id: str = "m-dead"
            name: str = "Altgrab"
            graveTemplateId: str = "saved"
            gravestoneTemplate: str = "gravestone_saved.png"
            portraitOffsetX: float = 0.25
            portraitOffsetY: float = -0.20
            portraitZoom: float = 1.35
            textOffsetX: float = 0.15
            textOffsetY: float = -0.10
            textScale: float = 1.10
            deathDate: str = "2026-09-01"

        class TemplateFixture:
            def __init__(self, template_id, filename, category, x, y, zoom):
                self.grave_template_id = template_id
                self.filename = filename
                self.category = category
                self.default_portrait_offset_x = x
                self.default_portrait_offset_y = y
                self.default_portrait_zoom = zoom

        member = MemberFixture()
        templates = (
            TemplateFixture("saved", "gravestone_saved.png", "Menschen", 0, 0, 1),
            TemplateFixture("candidate", "gravestone_candidate.png", "Elfen", -.4, .3, 1.6),
            TemplateFixture("other", "gravestone_other.png", "Gnome", .2, -.1, 1.2),
        )
        state = grabber.build_gravestone_editor_state(
            member, templates, self.root / "history.png", initial_template_id="candidate",
        )
        self.assertEqual(state.saved.template_id, "saved")
        self.assertEqual(
            (state.saved.portrait_offset_x, state.saved.portrait_offset_y,
             state.saved.portrait_zoom, state.saved.text_offset_x,
             state.saved.text_offset_y, state.saved.text_scale),
            (0.25, -0.20, 1.35, 0.15, -0.10, 1.10),
        )
        self.assertEqual(state.draft.template_id, "candidate")
        self.assertEqual(
            (state.draft.portrait_offset_x, state.draft.portrait_offset_y,
             state.draft.portrait_zoom),
            (-.4, .3, 1.6),
        )
        self.assertEqual(
            (state.draft.text_offset_x, state.draft.text_offset_y, state.draft.text_scale),
            (0.0, 0.0, 1.0),
        )
        self.assertEqual(member.graveTemplateId, "saved")

        changed_candidate = replace(
            state,
            draft=replace(
                state.draft, portrait_offset_x=.9, text_offset_y=.8, text_scale=1.4,
            ),
        )
        candidate_reset = changed_candidate.reset()
        self.assertEqual(candidate_reset.draft.template_id, "candidate")
        self.assertEqual(candidate_reset.draft.portrait_offset_x, -.4)
        self.assertEqual(candidate_reset.draft.text_offset_y, 0.0)
        self.assertEqual(candidate_reset.draft.text_scale, 1.0)

        saved_again = candidate_reset.select_template("saved")
        self.assertEqual(saved_again.draft, saved_again.saved)
        changed_saved = replace(
            saved_again,
            draft=replace(saved_again.draft, portrait_zoom=2.0, text_offset_x=-.7),
        )
        self.assertEqual(changed_saved.reset().draft, changed_saved.saved)
        other = changed_saved.select_template("other")
        self.assertEqual(other.draft.template_id, "other")
        self.assertEqual(
            (other.draft.portrait_offset_x, other.draft.portrait_offset_y,
             other.draft.portrait_zoom),
            (.2, -.1, 1.2),
        )
        rendered_member = other.member_for_render(member)
        self.assertEqual(member.graveTemplateId, "saved")
        self.assertEqual(rendered_member.graveTemplateId, "other")
        self.assertEqual(rendered_member.portraitZoom, 1.2)
        self.assertEqual(rendered_member.textOffsetX, 0.0)

    def test_project_status_is_visible_and_updates_for_loaded_project(self):
        app = self.make_app(project=False)
        self.assertEqual(app.project_status_var.get(), "Kein Projekt geladen")
        self.assertEqual(app._project_tooltip_text, "")

        self.project_path.write_text('{"members": []}', encoding="utf-8")
        app._load_project(self.project_path)
        self.assertEqual(app.project_status_var.get(), "Projekt: guild.ggc")
        self.assertEqual(app._project_tooltip_text, str(self.project_path.resolve()))
        app._show_project_tooltip()
        self.assertIsNotNone(app._project_tooltip_window)
        self.assertEqual(
            app._project_tooltip_window.winfo_children()[0].cget("text"),
            str(self.project_path.resolve()),
        )
        app._hide_project_tooltip()

        other_project = self.root / "andere.ggc"
        other_project.write_text('{"members": []}', encoding="utf-8")
        app._load_project(other_project)
        self.assertEqual(app.project_status_var.get(), "Projekt: andere.ggc")
        self.assertEqual(app._project_tooltip_text, str(other_project.resolve()))

    def test_project_status_is_localized_in_english(self):
        app = self.make_app(project=False, language="en")
        self.assertEqual(app.project_status_var.get(), "No project loaded")
        self.project_path.write_text('{"members": []}', encoding="utf-8")
        app._load_project(self.project_path)
        self.assertEqual(app.project_status_var.get(), "Project: guild.ggc")
        self.assertEqual(app.status_var.get(), "Project opened: guild.ggc")

    def test_guild_list_save_dispatches_current_records(self):
        app = self.make_app(names=("Janos", "Bífi"))
        app._record_for_name("Bífi").update({"race": "Human", "className": "Warrior"})
        app._dispatch_project_action = Mock(return_value=(
            "save-token",
            {"ok": True, "summary": {"added": 1, "existing": 1, "newIncarnations": 0}},
        ))
        with patch.object(grabber.messagebox, "showinfo") as info:
            app._save_guild_list()
        action_type, data = app._dispatch_project_action.call_args.args
        self.assertEqual(action_type, "add_members")
        self.assertEqual([item["characterName"] for item in data["members"]], ["Janos", "Bífi"])
        self.assertEqual(data["members"][1]["className"], "Warrior")
        info.assert_called_once()

    @staticmethod
    def select(app, name: str) -> None:
        for item in app.tree.get_children():
            if app.tree.item(item, "values")[0] == name:
                app.tree.selection_set(item)
                app.tree.focus(item)
                app._preview_selection_changed()
                return
        raise AssertionError(f"Tree-Eintrag fehlt: {name}")

    def test_banner_covers_complete_header_and_keeps_original_unchanged(self):
        app = self.make_app()
        app._render_banner_cover(1180, 150)
        self.assertIsNotNone(app._banner_photo)
        self.assertEqual(app._banner_source_size, (2172, 724))
        self.assertEqual(app._banner_rendered_size, (1180, 150))
        self.assertEqual((app._banner_photo.width(), app._banner_photo.height()), (1180, 150))
        self.assertEqual(app.banner_canvas.itemcget(app._banner_item, "state"), "normal")
        self.assertEqual(
            (self.root / "assets" / "grabber_banner.png").read_bytes(),
            self.banner_source.read_bytes(),
        )

    def test_banner_uses_the_named_fixed_focal_point(self):
        self.assertEqual(grabber.BANNER_FOCAL_POINT, (0.33, 0.46))
        source = (REPO_ROOT / "app" / "GuildPortraitGrabber.py").read_text(encoding="utf-8")
        self.assertIn("centering=BANNER_FOCAL_POINT", source)
        self.assertNotIn("centering=(0.5, 0.5)", source)

    def test_banner_header_height_is_visibly_higher_than_before(self):
        app = self.make_app()
        self.assertEqual(grabber.BANNER_HEADER_HEIGHT, 230)
        self.assertGreater(grabber.BANNER_HEADER_HEIGHT, 195)
        self.assertIn(grabber.BANNER_HEADER_HEIGHT, range(220, 241))
        self.assertEqual(int(app.banner_canvas.cget("height")), 230)
        app._render_banner_cover(1180, grabber.BANNER_HEADER_HEIGHT)
        self.assertEqual(app._banner_rendered_size, (1180, 230))
        self.assertEqual(
            tuple(map(float, app.banner_canvas.coords(app._header_title_item))),
            (10.0, 115.0),
        )

    def test_scrollable_content_fills_viewport_without_exposed_canvas_area(self):
        app = self.make_app()
        scroll = app.portrait_scroll
        scroll.update_idletasks()
        requested_width = scroll.content.winfo_reqwidth()
        requested_height = scroll.content.winfo_reqheight()
        viewport_width = requested_width + 80
        viewport_height = requested_height + 120
        event = type("ResizeEvent", (), {
            "width": viewport_width,
            "height": viewport_height,
        })()

        scroll._canvas_resize(event)

        self.assertEqual(float(scroll.canvas.itemcget(scroll.window_id, "width")), viewport_width)
        self.assertEqual(float(scroll.canvas.itemcget(scroll.window_id, "height")), viewport_height)
        self.assertEqual(scroll.canvas.bbox("all"), (0, 0, viewport_width, viewport_height))

    def test_missing_banner_does_not_prevent_the_ui_from_starting(self):
        app = self.make_app(banner=False)
        app._render_banner_cover(1180, 150)
        self.assertIsNone(app._banner_photo)
        self.assertEqual(app.banner_canvas.itemcget(app._banner_item, "state"), "hidden")
        self.assertEqual(app.banner_canvas.cget("background"), "#78151b")
        self.assertNotEqual(app.banner_canvas.itemcget(app._header_title_item, "state"), "hidden")
        self.assertTrue(app.tree.winfo_exists())

    def test_cover_scaling_fills_wide_and_narrow_headers_without_distortion(self):
        app = self.make_app()
        source_ratio = 2172 / 724
        for target in ((1800, 150), (360, 150)):
            with self.subTest(target=target):
                app._render_banner_cover(*target)
                self.assertEqual(app._banner_rendered_size, target)
                self.assertEqual((app._banner_photo.width(), app._banner_photo.height()), target)
                scaled_width, scaled_height = app._banner_scaled_size
                self.assertGreaterEqual(scaled_width, target[0])
                self.assertGreaterEqual(scaled_height, target[1])
                self.assertAlmostEqual(scaled_width / scaled_height, source_ratio, places=2)
                self.assertTrue(scaled_width > target[0] or scaled_height > target[1])

    def test_header_texts_stay_above_the_banner(self):
        app = self.make_app()
        app._render_banner_cover(1180, 150)
        self.assertEqual(
            app.banner_canvas.itemcget(app._header_title_item, "text"),
            f"Guild Portrait Grabber v{grabber.APP_VERSION}",
        )
        self.assertIn("EU / stitches / Classic Era", app.banner_canvas.itemcget(app._header_summary_item, "text"))
        stacking = app.banner_canvas.find_all()
        self.assertGreater(stacking.index(app._header_title_item), stacking.index(app._banner_item))
        self.assertGreater(stacking.index(app._header_summary_item), stacking.index(app._banner_item))

    def test_repeated_banner_resize_keeps_only_one_photo_reference(self):
        app = self.make_app()
        app._render_banner_cover(900, 150)
        before = set(app.tk.call("image", "names"))
        first_name = str(app._banner_photo)
        for width in range(910, 1110, 10):
            app._render_banner_cover(width, 150)
        self.assertNotEqual(first_name, str(app._banner_photo))
        gc.collect()
        after = set(app.tk.call("image", "names"))
        self.assertLessEqual(len(after), len(before))
        self.assertFalse(hasattr(app, "_banner_photos"))

    def test_preview_uses_only_normal_portrait_and_preserves_aspect_ratio(self):
        portrait = self.portraits / "m0001.png"
        self.make_image(portrait, size=(120, 240))
        app = self.make_app()
        self.select(app, "Janos")
        self.assertIsNotNone(app._preview_photo)
        self.assertEqual(app._preview_rendered_size, (125, 250))
        self.assertEqual(app.preview_name_var.get(), "Janos")
        self.assertEqual(app.preview_status_var.get(), "Portrait vorhanden")

        portrait.unlink()
        app._show_portrait_preview("Janos")
        self.assertIsNone(app._preview_photo)
        self.assertEqual(app.preview_status_var.get(), "Kein Portrait vorhanden")

    def test_ui_free_portrait_inventory_keeps_v091_lookup_and_missing_rules(self):
        names = ["Janos", "A:b", "Fehlt"]
        self.make_image(self.portraits / "m0001.png")
        self.make_image(self.portraits / "m0002.png")
        self.assertEqual(
            grabber.existing_portrait_for_member("m0001", self.project_path),
            self.portraits / "m0001.png",
        )
        self.assertEqual(
            grabber.missing_portrait_names(
                names, self.project_path,
                {"janos": "m0001", "a:b": "m0002", "fehlt": "m0003"},
            ), ["Fehlt"],
        )

        app = self.make_app(names=names)
        self.assertEqual(app._missing_names(), ["Fehlt"])

    def test_switching_selection_replaces_the_single_preview_reference(self):
        self.make_image(self.portraits / "m0001.png", color=(1, 2, 3))
        self.make_image(self.portraits / "m0002.png", color=(4, 5, 6))
        app = self.make_app()
        self.select(app, "Janos")
        first = app._preview_photo
        self.select(app, "Ánníe")
        self.assertIsNot(first, app._preview_photo)
        self.assertEqual(app.preview_name_var.get(), "Ánníe")
        self.assertFalse(hasattr(app, "_preview_photos"))

    def test_saved_events_refresh_preview_without_browser_action(self):
        app = self.make_app()
        self.make_image(self.portraits / "m0001.png")
        submitted = []
        app.worker.submit = lambda action, **payload: submitted.append((action, payload))
        with patch.object(app.worker, "_goto") as navigate, \
             patch.object(app.worker, "_raw_screenshot") as screenshot:
            app._handle_event({
                "type": "portrait_saved", "name": "Janos",
                "path": str(self.root / "somewhere-else" / "Janos.png"), "method": "test",
            })
            navigate.assert_not_called()
            screenshot.assert_not_called()
        self.assertIsNotNone(app._preview_photo)
        self.assertEqual(app.preview_name_var.get(), "Janos")
        self.assertEqual(submitted, [])

    def test_csv_import_refreshes_visible_character_list(self):
        app = self.make_app(names=("Janos",))
        csv_path = self.root / "names.csv"
        csv_path.write_text("Name;Amount\nNeuefigur;1\nZweitefigur;2\n", encoding="utf-8-sig")
        with patch.object(grabber.filedialog, "askopenfilename", return_value=str(csv_path)):
            app._import_specific("CSV", [("CSV", "*.csv")], active_only=True)
        visible = {
            app.tree.item(item, "values")[0]
            for item in app.tree.get_children()
        }
        self.assertIn("Neuefigur", visible)
        self.assertIn("Zweitefigur", visible)
        self.assertEqual(len(visible), 3)

    def test_batch_saved_events_keep_only_the_latest_preview(self):
        for name, color in (("Janos", (1, 2, 3)), ("Ánníe", (4, 5, 6))):
            member_id = "m0001" if name == "Janos" else "m0002"
            self.make_image(self.portraits / f"{member_id}.png", color=color)
        app = self.make_app()
        app.batch_running = True
        app._handle_event({"type": "portrait_saved", "name": "Janos", "path": "ignored", "method": "test"})
        first = app._preview_photo
        app._handle_event({"type": "portrait_saved", "name": "Ánníe", "path": "ignored", "method": "test"})
        self.assertIsNot(first, app._preview_photo)
        self.assertEqual(app.preview_name_var.get(), "Ánníe")

    def test_worker_queue_is_processed_on_the_tk_main_thread(self):
        self.make_image(self.portraits / "m0001.png")
        app = self.make_app()
        calls = []
        original = app._handle_event

        def recording_handler(event):
            calls.append(threading.current_thread())
            original(event)

        app._handle_event = recording_handler
        app.events.put({"type": "portrait_saved", "name": "Janos", "path": "ignored", "method": "test"})
        app._poll_events()
        self.assertEqual(calls, [threading.main_thread()])

    def test_worker_event_interpretation_returns_ui_neutral_actions(self):
        armory_result = {"characterName": "Janos", "race": "Human", "className": "Warrior"}
        semantics = {
            "browser": grabber.interpret_worker_event(
                {"type": "browser_ready", "browser": "msedge"}
            ),
            "progress": grabber.interpret_worker_event(
                {"type": "progress", "name": "Janos", "message": "Oeffne Janos …"}
            ),
            "armory": grabber.interpret_worker_event(
                {"type": "armory_data", "name": "Janos", "result": armory_result}
            ),
            "portrait": grabber.interpret_worker_event(
                {"type": "portrait_saved", "name": "Janos", "path": "Janos.png", "method": "playwright"}
            ),
            "raw": grabber.interpret_worker_event(
                {"type": "raw_capture", "name": "Janos", "path": "raw.png", "method": "playwright"}
            ),
            "batch": grabber.interpret_worker_event(
                {
                    "type": "batch_done",
                    "total": 5,
                    "processed": 2,
                    "successes": 1,
                    "failures": 1,
                    "cancelled": True,
                }
            ),
            "error": grabber.interpret_worker_event(
                {"type": "error", "message": "Browserfehler", "detail": "Details", "log_path": "grabber.log"}
            ),
            "unknown": grabber.interpret_worker_event({"type": "future_event"}),
        }

        self.assertEqual(
            semantics["armory"]["model_action"],
            {"type": "store_armory_result", "result": armory_result},
        )
        self.assertEqual(
            semantics["portrait"]["action"],
            {"type": "refresh_portrait", "name": "Janos"},
        )
        self.assertEqual(semantics["raw"]["action"]["type"], "open_crop_dialog")
        self.assertEqual(semantics["batch"]["action"], {"type": "batch_done", "processed": 2})
        self.assertEqual(semantics["error"]["dialog"]["type"], "text")
        self.assertEqual(semantics["progress"]["name_status"], grabber.tr("grabber.worker_opening", name="Janos"))
        self.assertEqual(semantics["unknown"], {"kind": "future_event", "name": ""})

        def assert_ui_neutral(value):
            self.assertNotIsInstance(value, grabber.tk.Variable)
            if isinstance(value, dict):
                for nested in value.values():
                    assert_ui_neutral(nested)
            elif isinstance(value, (list, tuple)):
                for nested in value:
                    assert_ui_neutral(nested)

        for semantic in semantics.values():
            assert_ui_neutral(semantic)

    def test_common_worker_payload_contract_normalizes_values_and_types(self):
        app = self.make_app()
        app.region_var.set("   ")
        app.realm_var.set("  custom realm  ")
        app.game_var.set("")
        app.capture_mode_var.set(grabber.CAPTURE_MODE_STANDARD)
        app.standard_wait_var.set(7.5)
        app.screen_x_var.set(-1200)
        app.screen_y_var.set(100)
        app.screen_w_var.set(300)
        app.screen_h_var.set(525)
        app.config_data.update(
            {
                "browser_channel": "chrome",
                "wait_after_load": "4.25",
                "output_dir": "legacy-output",
                "crop": {"x1": -1, "y1": 0.2, "x2": 2, "y2": 0.8},
            }
        )

        payload = app._common_payload()

        self.assertEqual(
            payload,
            {
                "source_id": grabber.PORTRAIT_SOURCE_ARMORY,
                "region": grabber.DEFAULT_REGION,
                "realm": "custom realm",
                "game_version": grabber.DEFAULT_GAME_VERSION,
                "preferred_channel": "chrome",
                "wait_after_load": 4.25,
                "capture_mode": "standard_browser_region",
                "screen_region": (-1200, 100, 300, 525),
                "standard_wait_after_open": 7.5,
            },
        )
        self.assertIsInstance(payload["wait_after_load"], float)
        self.assertIsInstance(payload["standard_wait_after_open"], float)
        self.assertIsInstance(payload["screen_region"], tuple)
        self.assertTrue(all(isinstance(value, int) for value in payload["screen_region"]))
        self.assertNotIn("output_dir", app.config_data)
        self.assertEqual(app.config_data["crop"], {"x1": 0.0, "y1": 0.2, "x2": 1.0, "y2": 0.8})
        self.assertEqual(app.config_data["capture_mode"], "standard_browser_region")
        self.assertEqual(
            app.config_data["screen_region"],
            {"x": -1200, "y": 100, "width": 300, "height": 525},
        )
        self.assertEqual(
            payload,
            grabber.build_worker_payload(
                region="   ",
                realm="  custom realm  ",
                game_version="",
                preferred_channel="chrome",
                wait_after_load="4.25",
                capture_mode="standard_browser_region",
                screen_region=(-1200, 100, 300, 525),
                standard_wait_after_open=7.5,
            ),
        )
        normalized_config = grabber.build_saved_grabber_config(
            {
                "browser_channel": "chrome",
                "output_dir": "legacy-output",
                "crop": {"x1": -1, "y1": 0.2, "x2": 2, "y2": 0.8},
            },
            region="   ",
            realm="  custom realm  ",
            game_version="",
            guild_name="  Test Guild  ",
            crop={"x1": -1, "y1": 0.2, "x2": 2, "y2": 0.8},
            capture_mode=grabber.CAPTURE_MODE_STANDARD,
            standard_wait_after_open=99.0,
            screen_region=(-1200, 100, 300, 525),
        )
        self.assertNotIn("output_dir", normalized_config)
        self.assertEqual(normalized_config["region"], grabber.DEFAULT_REGION)
        self.assertEqual(normalized_config["realm"], "custom realm")
        self.assertEqual(normalized_config["game_version"], grabber.DEFAULT_GAME_VERSION)
        self.assertEqual(normalized_config["guild_name"], "Test Guild")
        self.assertEqual(normalized_config["capture_mode"], "standard_browser_region")
        self.assertEqual(normalized_config["standard_wait_after_open"], 60.0)
        self.assertEqual(
            normalized_config["screen_region"],
            {"x": -1200, "y": 100, "width": 300, "height": 525},
        )
        self.assertEqual(normalized_config["portrait_source"], grabber.PORTRAIT_SOURCE_ARMORY)
        self.assertEqual(
            normalized_config["portrait_sources"][grabber.PORTRAIT_SOURCE_ARMORY]["crop"],
            {"x1": 0.0, "y1": 0.2, "x2": 1.0, "y2": 0.8},
        )

        source_settings = grabber.portrait_source_settings({
            "portrait_source": "armory",
            "region": "legacy-realm",
            "portrait_sources": {"armory": {"realm": "source-realm"}},
        })
        self.assertEqual(source_settings["source_id"], grabber.PORTRAIT_SOURCE_ARMORY)
        self.assertEqual(source_settings["realm"], "source-realm")
        self.assertEqual(
            grabber.build_portrait_source_url("Janos", source_settings),
            grabber.build_armory_url("Janos", "legacy-realm", "source-realm", grabber.DEFAULT_GAME_VERSION),
        )
        self.assertEqual(
            grabber.build_portrait_source_output("armory", portrait_path="Janos.png", race="Human", class_name="Warrior"),
            {"sourceId": "armory", "portraitPath": "Janos.png", "race": "Human", "className": "Warrior"},
        )

        app.standard_wait_var.set("invalid")
        app._save_settings()
        self.assertEqual(app.config_data["standard_wait_after_open"], 6.0)
        app.standard_wait_var.set(99.0)
        app._save_settings()
        self.assertEqual(app.config_data["standard_wait_after_open"], 60.0)

        app.capture_mode_var.set(grabber.CAPTURE_MODE_PLAYWRIGHT)
        app.standard_wait_var.set(6.0)
        playwright_payload = app._common_payload()
        self.assertEqual(playwright_payload["capture_mode"], "playwright")
        self.assertEqual(playwright_payload["screen_region"], (-1200, 100, 300, 525))

    def test_capture_submit_contract_adds_identity_paths_crop_and_navigation(self):
        app = self.make_app()
        self.select(app, "Janos")
        record = app._record_for_name("Janos")
        record["memberId"] = "member-janos"
        app.config_data["crop"] = {"x1": 0.1, "y1": 0.2, "x2": 0.8, "y2": 0.9}
        expected_output_dir = str(app._active_output_dir())

        with patch.object(app.worker, "submit") as submit:
            app._capture_selected()

        submit.assert_called_once()
        args, payload = submit.call_args
        self.assertEqual(args, ("capture",))
        self.assertEqual(
            set(payload),
            {
                "name",
                "member_id",
                "source_id",
                "region",
                "realm",
                "game_version",
                "preferred_channel",
                "wait_after_load",
                "capture_mode",
                "screen_region",
                "standard_wait_after_open",
                "output_dir",
                "crop",
                "navigate",
            },
        )
        self.assertEqual(payload["name"], "Janos")
        self.assertEqual(payload["member_id"], "member-janos")
        self.assertEqual(payload["source_id"], grabber.PORTRAIT_SOURCE_ARMORY)
        self.assertEqual(payload["output_dir"], expected_output_dir)
        self.assertEqual(payload["crop"], {"x1": 0.1, "y1": 0.2, "x2": 0.8, "y2": 0.9})
        self.assertIs(payload["navigate"], True)

    def test_worker_lifecycle_and_per_character_events_keep_semantic_state(self):
        app = self.make_app()
        app._populate_tree = Mock()
        app._log = Mock()

        app._handle_event({"type": "browser_ready", "browser": "msedge"})
        self.assertIn("msedge", app.status_var.get())

        with patch.object(grabber.messagebox, "showinfo") as showinfo:
            app._handle_event({"type": "browser_test_ok", "browser": "msedge"})
        showinfo.assert_called_once()

        progress_message = "Öffne Janos im Browser ..."
        app._handle_event({"type": "progress", "name": "Janos", "message": progress_message})
        expected_progress = grabber.localize_worker_message(progress_message)
        self.assertEqual(app.status_by_name["Janos"], expected_progress)
        self.assertEqual(app.status_var.get(), expected_progress)

        app._handle_event({"type": "opened", "name": "Janos", "method": "playwright"})
        self.assertEqual(
            app.status_by_name["Janos"],
            f"{grabber.tr('grabber.opened')} (playwright)",
        )
        opened_status = grabber.tr("grabber.opened_help", name="Janos")
        self.assertEqual(app.status_var.get(), opened_status)

        long_message = "X" * 220
        app._handle_event({"type": "item_error", "name": "Janos", "message": long_message})
        self.assertEqual(
            app.status_by_name["Janos"],
            grabber.tr("grabber.item_error", message=long_message[:180]),
        )
        self.assertEqual(app.status_var.get(), opened_status)
        app._populate_tree.assert_called()

    def test_armory_result_error_and_timeout_events_have_distinct_semantics(self):
        app = self.make_app()
        app._populate_tree = Mock()
        app._log = Mock()
        app._store_armory_result = Mock()
        result = {
            "characterName": "Janos",
            "memberId": "member-janos",
            "className": "Warrior",
            "race": "Human",
        }

        app._handle_event({"type": "armory_data", "name": "Janos", "result": result})
        app._store_armory_result.assert_called_once_with(result)
        self.assertEqual(
            app.status_var.get(),
            grabber.tr(
                "grabber.data_read",
                name="Janos",
                race=grabber.race_display("Human"),
                class_name="Warrior",
            ),
        )

        app._handle_event({"type": "armory_data_error", "name": "Janos", "message": "kaputt"})
        self.assertEqual(
            app.status_var.get(),
            grabber.tr("grabber.data_not_recognized", name="Janos", error="kaputt"),
        )
        app._store_armory_result.assert_called_once()

        app._handle_event({"type": "armory_data_wait_timeout", "name": "Janos"})
        self.assertEqual(
            app.status_var.get(),
            grabber.tr("grabber.protection_timeout", name="Janos"),
        )
        app._store_armory_result.assert_called_once()

    def test_batch_progress_and_cancelled_done_keep_partial_result_contract(self):
        app = self.make_app()
        app._populate_tree = Mock()
        app._log = Mock()
        app._update_project_controls = Mock()
        app.batch_running = True

        app._handle_event(
            {
                "type": "batch_progress",
                "index": 3,
                "total": 5,
                "name": "Janos",
                "message": "Verarbeite Janos",
            }
        )
        self.assertEqual(float(app.progress.cget("maximum")), 5.0)
        self.assertEqual(float(app.progress["value"]), 2.0)
        self.assertEqual(app.status_var.get(), "3/5: Janos")

        app._handle_event(
            {
                "type": "batch_done",
                "total": 5,
                "processed": 2,
                "successes": 1,
                "failures": 1,
                "cancelled": True,
            }
        )
        self.assertFalse(app.batch_running)
        self.assertEqual(float(app.progress["value"]), 2.0)
        self.assertEqual(str(app.stop_btn.cget("state")), "disabled")
        self.assertEqual(
            app.status_var.get(),
            grabber.tr(
                "grabber.batch_cancelled",
                processed=2,
                total=5,
                successes=1,
                failures=1,
            ),
        )
        app._update_project_controls.assert_called_once()

    def test_raw_capture_event_opens_crop_dialog_with_callback_contract(self):
        app = self.make_app()
        app._populate_tree = Mock()
        crop = {"x1": 0.1, "y1": 0.2, "x2": 0.8, "y2": 0.9}
        app.config_data["crop"] = crop
        raw_path = self.root / "raw.png"

        with patch.object(grabber, "CropDialog") as crop_dialog:
            app._handle_event(
                {
                    "type": "raw_capture",
                    "name": "Janos",
                    "path": str(raw_path),
                    "crop": crop,
                }
            )

        crop_dialog.assert_called_once()
        args = crop_dialog.call_args.args
        self.assertIs(args[0], app)
        self.assertEqual(args[1], raw_path)
        self.assertEqual(args[2], crop)
        self.assertTrue(callable(args[3]))
        self.assertEqual(
            app.status_by_name["Janos"],
            grabber.tr("grabber.calibration_ready", method=""),
        )

    def test_error_event_opens_details_without_mutating_records(self):
        app = self.make_app()
        records_before = deepcopy(app.character_records)
        log_path = self.root / "grabber.log"

        with patch.object(grabber, "ScrollableTextDialog") as dialog:
            app._handle_event(
                {
                    "type": "error",
                    "message": "Browserfehler",
                    "detail": "Technisches Detail",
                    "log_path": str(log_path),
                }
            )

        self.assertEqual(
            app.status_var.get(),
            grabber.tr("grabber.error_prefix", message="Browserfehler"),
        )
        dialog.assert_called_once()
        args = dialog.call_args.args
        self.assertIs(args[0], app)
        self.assertEqual(args[1], grabber.tr("grabber.screenshot_error"))
        self.assertIn("Browserfehler", args[2])
        self.assertIn("Technisches Detail", args[2])
        self.assertIn(str(log_path), args[2])
        self.assertEqual(app.character_records, records_before)

    def test_remove_cancel_and_confirm_are_strictly_file_scoped(self):
        portraits = self.portraits
        normal = portraits / "m0001.png"
        self.make_image(normal)
        preserved = {
            portraits / "history" / "m0001.png": b"historic portrait",
            portraits / "history" / "m0001.missing": b"historic missing marker",
            portraits / "m0002.png": b"other portrait",
            self.root / "data" / "projects" / "guild.ggc": b"project model",
            self.root / "data" / "browser_profiles" / "edge_grabber" / "marker": b"profile",
            self.root / "data" / "temp" / "grabber" / "armory_results.json": b"sidecar",
        }
        for path, content in preserved.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        app = self.make_app()
        self.select(app, "Janos")
        model_before = deepcopy((app.names, app.character_records, app.armory_context))

        with patch.object(grabber.messagebox, "askyesno", return_value=False):
            app._remove_selected_portrait()
        self.assertTrue(normal.is_file())

        with patch.object(grabber.messagebox, "askyesno", return_value=True):
            app._remove_selected_portrait()
        self.assertFalse(normal.exists())
        for path, content in preserved.items():
            self.assertEqual(path.read_bytes(), content, f"Unzulässig verändert: {path}")
        self.assertEqual((app.names, app.character_records, app.armory_context), model_before)
        self.assertEqual(app._selected_tree_name_no_dialog(), "Janos")
        self.assertIn("Janos", app._missing_names())
        self.assertIsNone(app._preview_photo)

    def test_remove_missing_portrait_is_safe_and_localized(self):
        app = self.make_app(language="de")
        self.select(app, "Janos")
        with patch.object(grabber.messagebox, "askyesno") as confirm:
            app._remove_selected_portrait()
        confirm.assert_not_called()
        self.assertEqual(app.status_var.get(), "Für Janos ist kein Portrait vorhanden.")

    def test_gravestone_category_filter_keeps_current_and_filters_free_templates(self):
        templates = {
            "current": type("Template", (), {"category": "Menschen"})(),
            "elf": type("Template", (), {"category": "Elfen"})(),
            "gnome": type("Template", (), {"category": "Gnome"})(),
            "none": type("Template", (), {"category": None})(),
        }
        ids = ["current", "elf", "gnome", "none"]
        self.assertEqual(
            grabber.filter_gravestone_template_ids(templates, ids, "current", "Elfen"),
            ["current", "elf"],
        )
        self.assertEqual(
            grabber.filter_gravestone_template_ids(
                templates, ids, "current", grabber.GRAVESTONE_CATEGORY_FILTER_UNCATEGORIZED,
            ),
            ["current", "none"],
        )
        self.assertEqual(
            grabber.filter_gravestone_template_ids(
                templates, ids, "current", grabber.GRAVESTONE_CATEGORY_FILTER_ALL,
            ),
            ids,
        )

    def test_new_ui_texts_are_complete_in_de_and_en(self):
        expected = {
            "de": ("Portrait-Vorschau", "Portrait entfernen", "Kein Portrait vorhanden"),
            "en": ("Portrait Preview", "Remove Portrait", "No portrait available"),
        }
        translator = grabber.tr.__globals__["_translator"]
        for language, texts in expected.items():
            with self.subTest(language=language):
                translator.language = language
                self.assertEqual(
                    tuple(grabber.tr(key) for key in (
                        "grabber.preview", "grabber.remove_portrait", "grabber.no_portrait_available",
                    )),
                    texts,
                )
                app = self.make_app(language=language)
                self.assertEqual(app.remove_portrait_btn.cget("text"), texts[1])
                self.assertEqual(
                    grabber.tr("grabber.no_project_loaded"),
                    "Kein Projekt geladen" if language == "de" else "No project loaded",
                )


def main() -> int:
    global grabber, REPO_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    REPO_ROOT = args.repo_root.resolve()
    grabber = load_module("ggc_grabber_ui", REPO_ROOT / "app" / "GuildPortraitGrabber.py")
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
