# -*- coding: utf-8 -*-
"""Regression tests for empty projects, simplified Main/Twink, and Armory data."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


checker = None
grabber = None
REPO_ROOT = None


class EmptyProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-v061-empty-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = checker.GuildModel()

    def test_new_empty_project_has_no_members_players_or_path(self):
        self.model.new_seed()
        self.model.project_path = self.root / "old.ggc"
        self.model.new_empty()
        self.assertEqual(self.model.members, [])
        self.assertEqual(self.model.players, [])
        self.assertIsNone(self.model.project_path)
        self.assertFalse(self.model.dirty)

    def test_empty_project_roundtrip_stays_empty_without_seed_fallback(self):
        self.model.new_empty()
        path = self.root / "empty.ggc"
        self.model.save(path)
        loaded = checker.GuildModel()
        loaded.load(path)
        self.assertEqual((loaded.members, loaded.players), ([], []))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["members"], [])

    def test_explicit_empty_arrays_stay_empty(self):
        self.model.load_payload({"formatVersion": 2, "members": [], "players": []})
        self.assertEqual((self.model.members, self.model.players), ([], []))

    def test_clear_project_removes_all_model_entries_and_resets_ids(self):
        player = self.model.add_player("Historisch")
        active = self.model.add_member("Janos")
        dead = self.model.add_member("Schneeflocke")
        dead.lifeStatus = "dead"
        active.playerId = player.playerId
        self.model.clear_project()
        self.assertEqual((self.model.members, self.model.players), ([], []))
        self.assertTrue(self.model.dirty)
        self.assertEqual(self.model.add_member("Neu").id, "m1000")
        self.assertEqual(self.model.add_player("Neu").playerId, "p0001")

    def test_clear_project_never_deletes_portraits_history_or_missing_markers(self):
        paths = [
            self.root / "portraits" / "Janos.png",
            self.root / "portraits" / "history" / "m0042.png",
            self.root / "portraits" / "history" / "m0087.missing",
        ]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"keep")
        self.model.new_seed()
        self.model.clear_project()
        self.assertTrue(all(path.read_bytes() == b"keep" for path in paths))

    def test_remove_all_cancel_does_not_change_model(self):
        self.model.new_seed()
        before = copy.deepcopy(self.model.to_payload())
        view = SimpleNamespace(model=self.model)
        with patch.object(checker.messagebox, "askyesno", return_value=False):
            checker.GuildGearCheckerApp.remove_all_characters(view)
        self.assertEqual(self.model.to_payload(), before)

    def test_remove_all_confirm_refreshes_empty_ui_and_marks_dirty(self):
        self.model.new_seed()
        view = SimpleNamespace(
            model=self.model, selected_member_id=self.model.members[0].id,
            _invalidate_armory_session=Mock(), clear_detail=Mock(), reset_filters=Mock(),
            _update_tab_styles=Mock(), refresh_all=Mock(), autosave=Mock(),
            status_var=SimpleNamespace(set=Mock()), current_tab="Friedhof",
        )
        with patch.object(checker.messagebox, "askyesno", return_value=True):
            checker.GuildGearCheckerApp.remove_all_characters(view)
        self.assertEqual((self.model.members, self.model.players), ([], []))
        self.assertIsNone(view.selected_member_id)
        self.assertTrue(self.model.dirty)
        view.clear_detail.assert_called_once()
        view.refresh_all.assert_called_once_with(select_first=False)

    def test_empty_project_clears_tables_roster_graveyard_and_selection(self):
        with patch.object(checker, "app_base_dir", return_value=self.root), \
             patch.dict(os.environ, {"GGC_DISABLE_ICON_DOWNLOAD": "1"}):
            try:
                app = checker.GuildGearCheckerApp()
            except checker.tk.TclError as exc:
                self.skipTest(f"Tk not available: {exc}")
            try:
                app.model.new_empty()
                app.selected_member_id = None
                app.refresh_all(select_first=False)
                self.assertEqual(app.tree.get_children(), ())
                self.assertEqual([app.stat_active.get(), app.stat_dead.get()], ["0", "0"])
                self.assertEqual(sum(len(group) for group in checker.group_roster_members(app.model.members).values()), 0)
                self.assertEqual(app.filtered_members("Friedhof"), [])
                self.assertTrue(app.race_combo.winfo_exists())
                self.assertTrue(app.associated_main_combo.winfo_exists())
            finally:
                app.destroy()


class MainTwinkTests(unittest.TestCase):
    def setUp(self):
        self.model = checker.GuildModel()
        self.main = self.model.add_member("Schneeflocke")
        self.twink = self.model.add_member("Tazgø")

    def test_main_gets_player_id_and_twink_inherits_it(self):
        self.model.assign_character_type(self.main.id, "main", None, "healer")
        self.model.assign_character_type(self.twink.id, "twink", self.main.id, "dps")
        self.assertRegex(self.main.playerId or "", r"^p\d{4}$")
        self.assertEqual(self.twink.playerId, self.main.playerId)
        self.assertIs(self.model.associated_main(self.twink), self.main)

    def test_twink_requires_selected_active_main_and_rejects_self(self):
        with self.assertRaises(ValueError):
            self.model.assign_character_type(self.twink.id, "twink", None, "dps")
        with self.assertRaises(ValueError):
            self.model.assign_character_type(self.twink.id, "twink", self.twink.id, "dps")
        self.main.lifeStatus = "dead"
        with self.assertRaises(ValueError):
            self.model.assign_character_type(self.twink.id, "twink", self.main.id, "dps")

    def test_one_main_can_have_multiple_twinks(self):
        other = self.model.add_member("Bífi")
        self.model.assign_character_type(self.main.id, "main", None, "healer")
        for member in (self.twink, other):
            self.model.assign_character_type(member.id, "twink", self.main.id, "dps")
        self.assertEqual({self.twink.playerId, other.playerId}, {self.main.playerId})

    def test_main_switch_preserves_group_and_updates_associated_main(self):
        other = self.model.add_member("Bífi")
        self.model.assign_character_type(self.main.id, "main", None, "healer")
        self.model.assign_character_type(self.twink.id, "twink", self.main.id, "dps")
        group_id = self.main.playerId
        self.model.assign_character_type(other.id, "twink", self.main.id, "dps")
        self.model.assign_character_type(other.id, "main", None, "dps", replace_existing_main=True)
        self.assertEqual((self.main.characterType, other.characterType), ("twink", "main"))
        self.assertEqual(other.playerId, group_id)
        self.assertIs(self.model.associated_main(self.twink), other)

    def test_main_death_keeps_twinks_and_new_main_restores_relation(self):
        self.model.assign_character_type(self.main.id, "main", None, "healer")
        self.model.assign_character_type(self.twink.id, "twink", self.main.id, "dps")
        group_id = self.main.playerId
        self.model.mark_main_dead_with_successor(self.main.id, self.twink.id)
        self.assertEqual(self.twink.playerId, group_id)
        self.assertIsNone(self.model.associated_main(self.twink))
        self.assertEqual(self.twink.characterType, "main")
        self.assertEqual(self.twink.playerId, group_id)

    def test_legacy_player_name_is_preserved(self):
        self.model.load_payload({
            "formatVersion": 2,
            "players": [{"playerId": "p0042", "playerName": "Historischer Spieler"}],
            "members": [{"id": "m0042", "name": "Janos", "playerId": "p0042", "characterType": "main"}],
        })
        self.assertEqual(self.model.players[0].playerName, "Historischer Spieler")

    def test_race_roundtrip_and_legacy_missing_race(self):
        self.main.race = "Night Elf"
        with tempfile.TemporaryDirectory(prefix="ggc-v061-race-") as temp:
            path = Path(temp) / "race.ggc"
            self.model.save(path)
            loaded = checker.GuildModel(); loaded.load(path)
            self.assertEqual(loaded.find_by_id(self.main.id).race, "Night Elf")
        legacy = checker.GuildModel()
        legacy.load_payload({"formatVersion": 2, "members": [{"id": "m0042", "name": "Legacy"}]})
        self.assertIsNone(legacy.members[0].race)

    def test_roster_twink_card_shows_associated_main_not_player_name(self):
        with tempfile.TemporaryDirectory(prefix="ggc-v061-roster-") as temp, \
             patch.object(checker, "app_base_dir", return_value=Path(temp)), \
             patch.dict(os.environ, {"GGC_DISABLE_ICON_DOWNLOAD": "1"}):
            try:
                app = checker.GuildGearCheckerApp()
            except checker.tk.TclError as exc:
                self.skipTest(f"Tk not available: {exc}")
            try:
                app.model.new_empty()
                main = app.model.add_member("Schneeflocke")
                twink = app.model.add_member("Tazgø")
                app.model.assign_character_type(main.id, "main", None, "healer")
                app.model.find_player_by_id(main.playerId).playerName = "Interner Spieler"
                app.model.assign_character_type(twink.id, "twink", main.id, "dps")
                app.refresh_all(); app.switch_tab("Roster"); app.update_idletasks(); app.render_roster()
                texts = []
                def collect(widget):
                    try:
                        if widget.cget("text"):
                            texts.append(str(widget.cget("text")))
                    except checker.tk.TclError:
                        pass
                    for child in widget.winfo_children():
                        collect(child)
                collect(app.roster_inner)
                joined = "\n".join(texts)
                self.assertIn("TWINK", joined)
                self.assertIn("Main: Schneeflocke", joined)
                twink_section = joined[joined.find("Tazgø"):]
                self.assertNotIn("Interner Spieler", twink_section)
            finally:
                app.destroy()


class CheckerImportManagementTests(unittest.TestCase):
    def setUp(self):
        self.model = checker.GuildModel()
        self.model.new_empty()

    def test_new_csv_name_gets_new_active_member_id(self):
        created = self.model.import_active_members(["Janos"], "Warcraft Logs CSV")
        self.assertEqual(len(created), 1)
        self.assertRegex(created[0].id, r"^m\d{4}$")
        self.assertEqual((created[0].name, created[0].lifeStatus, created[0].source),
                         ("Janos", "active", "Warcraft Logs CSV"))

    def test_existing_active_incarnation_and_manual_fields_are_unchanged(self):
        player = self.model.add_player("Spieler")
        member = self.model.add_member("Janos")
        member.playerId = player.playerId
        member.characterType = "main"
        member.raidRole = "main_tank"
        member.race = "Night Elf"
        member.className = "Warrior"
        member.spec = "Fury"
        member.classSpec = "Warrior / Fury"
        before = copy.deepcopy(member.to_dict())

        created = self.model.import_active_members(["JANOS"], "Warcraft Logs CSV")

        self.assertEqual(created, [])
        self.assertEqual(member.to_dict(), before)
        self.assertIs(self.model.find_active_by_name("janos"), member)

    def test_only_dead_same_names_create_one_new_incarnation_without_reactivation(self):
        self.model.load_payload({
            "formatVersion": 2,
            "members": [
                {"id": "m0042", "name": "Janos", "lifeStatus": "dead", "deathDate": "2026-01-01"},
                {"id": "m0087", "name": "JANOS", "lifeStatus": "dead", "deathDate": "2026-02-02"},
            ],
        })
        dead_before = {member.id: copy.deepcopy(member.to_dict()) for member in self.model.members}

        created = self.model.import_active_members(["Janos", "JANOS"], "Warcraft Logs CSV")

        self.assertEqual(len(created), 1)
        self.assertNotIn(created[0].id, dead_before)
        self.assertEqual(created[0].lifeStatus, "active")
        for member_id, before in dead_before.items():
            self.assertEqual(self.model.find_by_id(member_id).to_dict(), before)

    def test_import_uses_casefold_only_and_preserves_special_characters(self):
        names = ["Janos", "JANOS", "jános", "Bífi", "Bifibifi", "Soregdrei", "Soregzwei"]
        created = self.model.import_active_members(names, "Warcraft Logs CSV")
        self.assertEqual([member.name for member in created],
                         ["Janos", "jános", "Bífi", "Bifibifi", "Soregdrei", "Soregzwei"])

    def test_import_conflict_is_transactional_and_reports_project_context(self):
        self.model.region = "US"
        self.model.realm = "defias-pillager"
        self.model.members = [
            checker.Member("m0042", "Janos", lifeStatus="active"),
            checker.Member("m0113", "JANOS", lifeStatus="active"),
        ]
        self.model.next_id = 2000
        self.model.dirty = False
        before = [copy.deepcopy(member.to_dict()) for member in self.model.members]

        with self.assertRaisesRegex(ValueError, "US/defias-pillager"):
            self.model.import_active_members(["Neuefigur"], "Warcraft Logs CSV")

        self.assertEqual([member.to_dict() for member in self.model.members], before)
        self.assertEqual(self.model.next_id, 2000)
        self.assertFalse(self.model.dirty)

    def test_checker_has_no_generic_list_or_txt_import_path(self):
        source = (REPO_ROOT / "app" / "GuildGearChecker.py").read_text(encoding="utf-8")
        self.assertNotIn("import_list", source)
        self.assertNotIn("*.txt", source)
        self.assertIn("self.import_csv", source)

    def test_grabber_import_sources_remain_available(self):
        source = (REPO_ROOT / "app" / "GuildPortraitGrabber.py").read_text(encoding="utf-8")
        for token in ("def parse_txt_names", "def parse_csv_names", "def parse_ggc_names",
                      "def _import_names", "def _import_wcl_csv"):
            self.assertIn(token, source)

    def test_de_and_en_checker_ui_exposes_only_requested_character_actions(self):
        translator = checker.tr.__globals__["_translator"]
        old_language = translator.language
        try:
            for language, expected in (
                ("de", {"Warcraft-Logs-CSV importieren", "Charakter hinzufügen",
                        "Charakter entfernen", "Alle Charaktere entfernen"}),
                ("en", {"Import Warcraft Logs CSV", "Add Character",
                        "Remove Character", "Remove All Characters"}),
            ):
                with self.subTest(language=language), \
                     tempfile.TemporaryDirectory(prefix=f"ggc-ui-{language}-") as temp, \
                     patch.object(checker, "app_base_dir", return_value=Path(temp)), \
                     patch.dict(os.environ, {"GGC_DISABLE_ICON_DOWNLOAD": "1"}):
                    translator.language = language
                    try:
                        app = checker.GuildGearCheckerApp()
                    except checker.tk.TclError as exc:
                        self.skipTest(f"Tk not available: {exc}")
                    try:
                        texts = set()
                        def collect(widget):
                            try:
                                text = str(widget.cget("text"))
                                if text:
                                    texts.add(text)
                            except checker.tk.TclError:
                                pass
                            for child in widget.winfo_children():
                                collect(child)
                        collect(app)
                        self.assertTrue(expected.issubset(texts))
                        self.assertNotIn("Liste importieren", texts)
                        self.assertNotIn("Import List", texts)
                    finally:
                        app.destroy()
        finally:
            translator.language = old_language


class ManualCharacterManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-manual-members-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = checker.GuildModel()
        self.model.new_empty()

    def test_manual_add_allows_dead_name_but_blocks_active_duplicate(self):
        dead = self.model.add_member("Janos")
        dead.lifeStatus = "dead"
        dead.deathDate = "2026-01-01"
        active = self.model.add_member("JANOS")
        self.assertNotEqual(active.id, dead.id)
        self.assertEqual(dead.lifeStatus, "dead")
        with self.assertRaises(ValueError):
            self.model.add_member("janos")

    def test_manual_add_preserves_unicode_and_project_context(self):
        self.model.region = "EU"
        self.model.realm = "stitches"
        members = [self.model.add_member(name) for name in ("Bífi", "Bifibifi", "Soregdrei", "Soregzwei")]
        self.assertEqual([member.name for member in members], ["Bífi", "Bifibifi", "Soregdrei", "Soregzwei"])
        self.assertEqual((self.model.region, self.model.realm), ("EU", "stitches"))

    def test_remove_member_uses_exact_id_and_never_touches_portrait_files(self):
        dead = self.model.add_member("Janos")
        dead.lifeStatus = "dead"
        active = self.model.add_member("JANOS")
        paths = [
            self.root / "portraits" / "Janos.png",
            self.root / "portraits" / "history" / f"{dead.id}.png",
            self.root / "portraits" / "history" / f"{dead.id}.missing",
        ]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"keep")

        removed = self.model.remove_member(active.id)

        self.assertEqual(removed.id, active.id)
        self.assertIs(self.model.find_by_id(dead.id), dead)
        self.assertIsNone(self.model.find_by_id(active.id))
        self.assertTrue(all(path.read_bytes() == b"keep" for path in paths))
        self.assertTrue(self.model.dirty)

    def test_remove_selected_refreshes_all_views_and_clears_selection(self):
        dead = self.model.add_member("Janos")
        dead.lifeStatus = "dead"
        active = self.model.add_member("JANOS")
        view = SimpleNamespace(
            model=self.model, selected_member_id=active.id,
            clear_detail=Mock(), refresh_all=Mock(), autosave=Mock(),
            status_var=SimpleNamespace(set=Mock()),
        )
        with patch.object(checker.messagebox, "askyesno", return_value=True):
            checker.GuildGearCheckerApp.remove_selected_member(view)
        self.assertIsNone(view.selected_member_id)
        self.assertIs(self.model.find_by_id(dead.id), dead)
        view.clear_detail.assert_called_once_with()
        view.refresh_all.assert_called_once_with(select_first=False)
        view.autosave.assert_called_once_with()

    def test_remove_selected_cancel_changes_nothing(self):
        member = self.model.add_member("Janos")
        self.model.dirty = False
        before = copy.deepcopy(member.to_dict())
        view = SimpleNamespace(model=self.model, selected_member_id=member.id)
        with patch.object(checker.messagebox, "askyesno", return_value=False):
            checker.GuildGearCheckerApp.remove_selected_member(view)
        self.assertEqual(self.model.find_by_id(member.id).to_dict(), before)
        self.assertFalse(self.model.dirty)

    def test_removing_member_in_one_context_does_not_touch_other_context(self):
        other = checker.GuildModel()
        other.new_empty()
        other.region = "US"
        other.realm = "defias-pillager"
        other_member = other.add_member("Janos")
        member = self.model.add_member("Janos")
        self.model.remove_member(member.id)
        self.assertIs(other.find_by_id(other_member.id), other_member)


class ArmoryExtractionTests(unittest.TestCase):
    def fixture(self, name):
        return (REPO_ROOT / "tests" / "fixtures" / "armory" / name).read_text(encoding="utf-8")

    def test_night_elf_warrior_fixture(self):
        self.assertEqual(grabber.extract_armory_character_data(self.fixture("night-elf-warrior.html")),
                         {"race": "Night Elf", "className": "Warrior"})

    def test_human_priest_fixture(self):
        self.assertEqual(grabber.extract_armory_character_data(self.fixture("human-priest.html")),
                         {"race": "Human", "className": "Priest"})

    def test_orc_shaman_fixture(self):
        self.assertEqual(grabber.extract_armory_character_data(self.fixture("orc-shaman.html")),
                         {"race": "Orc", "className": "Shaman"})

    def test_partial_missing_and_invalid_pages_do_not_invent_values(self):
        self.assertEqual(grabber.extract_armory_character_data("Race: Human"), {"race": "Human", "className": None})
        self.assertEqual(grabber.extract_armory_character_data("Class: Mage"), {"race": None, "className": "Mage"})
        self.assertEqual(grabber.extract_armory_character_data("maintenance"), {"race": None, "className": None})

    def test_ambiguous_page_returns_no_values(self):
        self.assertEqual(grabber.extract_armory_character_data(self.fixture("ambiguous.html")),
                         {"race": None, "className": None})

    def test_missing_data_batch_skips_complete_records(self):
        records = [
            {"characterName": "A", "race": "Human", "className": "Priest"},
            {"characterName": "B", "race": None, "className": "Mage"},
            {"characterName": "C", "race": "Orc", "className": None},
        ]
        self.assertEqual([r["characterName"] for r in grabber.records_missing_armory_data(records)], ["B", "C"])

    def test_existing_values_survive_failed_extraction(self):
        record = {"characterName": "Janos", "race": "Night Elf", "className": "Warrior"}
        grabber.merge_armory_data(record, {"race": None, "className": None})
        self.assertEqual((record["race"], record["className"]), ("Night Elf", "Warrior"))

    def test_read_reuses_already_open_page_without_navigation(self):
        worker = grabber.BrowserWorker(queue.Queue())
        worker._page = SimpleNamespace(url=grabber.build_armory_url("Ánníe"), is_closed=lambda: False)
        worker._ensure_browser = Mock()
        worker._goto = Mock()
        worker._extract_armory_character_data = Mock(return_value={"race": "Human", "className": "Mage"})
        worker._read_character_data("Ánníe", "EU", "stitches", "classic1x", "msedge", 0, member_id="m0042")
        worker._goto.assert_not_called()

    def test_portrait_and_data_failures_are_reported_independently(self):
        worker = grabber.BrowserWorker(queue.Queue())
        worker._extract_armory_character_data = Mock(side_effect=ValueError("no data"))
        worker._page = object()
        worker._attempt_armory_extraction("Janos", "m0113", "portrait")
        event = worker.events.get_nowait()
        self.assertEqual(event["type"], "armory_data_error")

    def test_successful_data_survives_portrait_failure(self):
        worker = grabber.BrowserWorker(queue.Queue())
        worker._page = SimpleNamespace(url=grabber.build_armory_url("Janos"), is_closed=lambda: False)
        worker._ensure_browser = Mock(); worker._goto = Mock()
        worker._extract_armory_character_data = Mock(return_value={"race": "Night Elf", "className": "Warrior"})
        worker._raw_screenshot = Mock(side_effect=RuntimeError("portrait failed"))
        with self.assertRaises(RuntimeError):
            worker._capture_character("Janos", "EU", "stitches", "classic1x", "msedge", 0,
                                      str(REPO_ROOT / "data" / "temp"), {}, member_id="m0113")
        self.assertEqual(worker.events.get_nowait()["type"], "armory_data")
        worker._goto.assert_not_called()

    def test_successful_portrait_survives_data_failure(self):
        worker = grabber.BrowserWorker(queue.Queue())
        worker._page = SimpleNamespace(url=grabber.build_armory_url("Janos"), is_closed=lambda: False)
        worker._ensure_browser = Mock(); worker._goto = Mock()
        worker._attempt_armory_extraction = Mock(return_value=None)
        worker._raw_screenshot = Mock(return_value=(Path("source.png"), "mock"))
        with patch.object(grabber, "crop_portrait"):
            worker._capture_character("Janos", "EU", "stitches", "classic1x", "msedge", 0,
                                      str(REPO_ROOT / "data" / "temp"), {}, member_id="m0113")
        self.assertEqual(worker.events.get_nowait()["type"], "portrait_saved")

    def test_data_batch_honors_stop(self):
        worker = grabber.BrowserWorker(queue.Queue())
        def first_only(*_args, **_kwargs):
            worker.request_batch_cancel()
            return {"race": "Human", "className": "Mage"}
        worker._read_character_data = Mock(side_effect=first_only)
        worker._read_data_all(
            [{"characterName": "A", "memberId": "m1"}, {"characterName": "B", "memberId": "m2"}],
            "EU", "stitches", "classic1x", "msedge", 0,
        )
        events = []
        while not worker.events.empty():
            events.append(worker.events.get_nowait())
        self.assertTrue(events[-1]["cancelled"])
        self.assertEqual(events[-1]["processed"], 1)

    def test_ggc_records_keep_member_id_and_ignore_dead_incarnation(self):
        with tempfile.TemporaryDirectory(prefix="ggc-v061-records-") as temp:
            path = Path(temp) / "roster.ggc"
            path.write_text(json.dumps({
                "armorySessionId": "s1", "members": [
                    {"id": "m0042", "name": "Janos", "lifeStatus": "dead"},
                    {"id": "m0113", "name": "Janos", "lifeStatus": "active"},
                ],
            }), encoding="utf-8")
            records, context = grabber.parse_ggc_characters(path)
        self.assertEqual([(r["memberId"], r["characterName"]) for r in records], [("m0113", "Janos")])
        self.assertEqual(context["sessionId"], "s1")


class ArmoryTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-v061-armory-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = checker.GuildModel()
        self.member = self.model.add_member("Janos")
        self.session = "session-current"

    def payload(self, **result_updates):
        result = {
            "memberId": self.member.id, "characterName": self.member.name,
            "race": "Night Elf", "className": "Warrior",
            "source": "classicwowarmory", "retrievedAt": "2026-09-11T10:00:00",
        }
        result.update(result_updates)
        return {
            "format": "GuildGearCheckerArmoryData", "formatVersion": 1,
            "sessionId": self.session, "region": self.model.region,
            "realm": self.model.realm, "gameVersion": self.model.game_version,
            "results": [result],
        }

    def test_grabber_writes_atomic_result_with_identity_and_metadata(self):
        path = self.root / "armory_character_data.json"
        grabber.write_armory_results(path, self.payload())
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["results"][0]["memberId"], self.member.id)
        self.assertEqual(loaded["results"][0]["source"], "classicwowarmory")
        self.assertIn("retrievedAt", loaded["results"][0])
        self.assertFalse(path.with_suffix(".tmp").exists())

    def test_checker_applies_only_matching_active_member_id(self):
        summary = self.model.apply_armory_results(self.payload(), self.session)
        self.assertEqual((self.member.race, self.member.className), ("Night Elf", "Warrior"))
        self.assertEqual(summary["updated"], 1)

    def test_unknown_id_and_dead_same_name_are_not_changed(self):
        dead = checker.Member("m0042", "Janos", lifeStatus="dead")
        self.model.members.insert(0, dead)
        summary = self.model.apply_armory_results(self.payload(memberId="m9999"), self.session)
        self.assertEqual(summary["ignored"], 1)
        self.assertIsNone(dead.race)
        self.assertEqual(self.member.className, "")

    def test_two_same_name_incarnations_update_only_active_member_id(self):
        dead = checker.Member("m0042", "Janos", lifeStatus="dead", race="Human", className="Mage")
        self.model.members.insert(0, dead)
        self.model.apply_armory_results(self.payload(memberId=self.member.id), self.session)
        self.assertEqual((dead.race, dead.className), ("Human", "Mage"))
        self.assertEqual((self.member.race, self.member.className), ("Night Elf", "Warrior"))

    def test_checker_contains_no_playwright_scraping(self):
        source = (REPO_ROOT / "app" / "GuildGearChecker.py").read_text(encoding="utf-8").casefold()
        self.assertNotIn("from playwright", source)
        self.assertNotIn("import playwright", source)

    def test_stale_session_or_other_context_is_ignored(self):
        self.assertTrue(self.model.apply_armory_results(self.payload(), "other-session")["stale"])
        other = self.payload()
        other["realm"] = "other"
        self.assertTrue(self.model.apply_armory_results(other, self.session)["stale"])

    def test_batch_only_fills_missing_and_reports_conflict(self):
        self.member.className = "Priest"
        summary = self.model.apply_armory_results(self.payload(), self.session)
        self.assertEqual(self.member.className, "Priest")
        self.assertEqual(self.member.race, "Night Elf")
        self.assertEqual(summary["conflicts"][0]["field"], "className")

    def test_failed_result_never_clears_existing_values(self):
        self.member.race = "Human"
        self.member.className = "Mage"
        self.model.apply_armory_results(self.payload(race=None, className=None), self.session)
        self.assertEqual((self.member.race, self.member.className), ("Human", "Mage"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    global checker, grabber, REPO_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    REPO_ROOT = args.repo_root.resolve()
    checker = load_module("ggc_v061_checker", REPO_ROOT / "app" / "GuildGearChecker.py")
    grabber = load_module("ggc_v061_grabber", REPO_ROOT / "app" / "GuildPortraitGrabber.py")
    suite = unittest.TestSuite()
    for case in (EmptyProjectTests, MainTwinkTests, CheckerImportManagementTests,
                 ManualCharacterManagementTests, ArmoryExtractionTests, ArmoryTransferTests):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
