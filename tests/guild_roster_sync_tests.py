# -*- coding: utf-8 -*-
"""Focused offline tests for guild roster snapshots and manual review/apply rules."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sync = None
g = None


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class GuildRosterSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-guild-sync-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def snapshot(self, names, **meta):
        records = {
            name.casefold(): {"race": meta.get(name, {}).get("race"),
                              "className": meta.get(name, {}).get("className")}
            for name in names
        }
        return sync.build_snapshot(
            "Bierstuben", "EU", "stitches", "classic1x",
            "https://classicwowarmory.com/guild/stitches/Bierstuben?page=1",
            names, records,
        )

    def test_build_url_supports_current_and_legacy_shapes(self):
        current = sync.build_guild_url("stitches", "Bier Stuben", 2, "classic1x")
        legacy = sync.build_guild_url("stitches", "Bier Stuben", 2, "classic1x", legacy=True)
        self.assertIn("/guild/stitches/Bier%20Stuben?", current)
        self.assertIn("page=2", current)
        self.assertIn("game_version=classic1x", current)
        self.assertIn("/guild/Bier%20Stuben?", legacy)

    def test_parser_uses_exact_region_realm_and_preserves_unicode(self):
        content = '''
        <a href="/character/EU/stitches/B%C3%ADfi?game_version=classic1x">Bífi</a>
        <a href="/character/eu/stitches/%C3%81nn%C3%ADe">Ánníe</a>
        <a href="/character/US/stitches/WrongRegion">Wrong</a>
        <a href="/character/EU/doomhowl/WrongRealm">Wrong</a>
        <a href="/character/EU/stitches/B%C3%ADfi">duplicate</a>
        <a href="?page=4">4</a><a href="?page=2">2</a>
        '''
        self.assertEqual(sync.parse_guild_roster_html(content, "EU", "stitches"), ["Bífi", "Ánníe"])
        self.assertEqual(sync.parse_guild_page_numbers(content), (1, 2, 4))

    def test_fetch_is_sequential_deduplicated_and_has_legacy_fallback(self):
        requested = []
        pages = {
            1: '<a href="/character/EU/stitches/Aba">Aba</a><a href="?page=2">2</a>',
            2: '<a href="/character/EU/stitches/Aba">Aba</a><a href="/character/EU/stitches/B%C3%ADfi">Bífi</a>',
        }
        def fetch(url):
            requested.append(url)
            if "/guild/stitches/" in url:
                raise OSError("current route unavailable")
            page = 2 if "page=2" in url else 1
            return pages[page]
        progress = []
        names, source_url = sync.fetch_guild_roster(
            "Bierstuben", "EU", "stitches", fetcher=fetch,
            progress=lambda page, total: progress.append((page, total)),
        )
        self.assertEqual(names, ["Aba", "Bífi"])
        self.assertIn("/guild/Bierstuben?", source_url)
        self.assertEqual(progress, [(1, 2), (2, 2)])
        self.assertGreaterEqual(len(requested), 3)

    def test_snapshot_atomic_roundtrip_and_context_validation(self):
        payload = self.snapshot(
            ["Bífi", "Ánníe"],
            **{"Bífi": {"race": "Dwarf", "className": "Warrior"}},
        )
        path = self.root / "data" / "runtime" / "guild_roster_snapshot.json"
        sync.write_snapshot_atomic(path, payload)
        loaded = sync.load_snapshot(path, "EU", "stitches", "classic1x")
        self.assertEqual([m["characterName"] for m in loaded["members"]], ["Bífi", "Ánníe"])
        self.assertFalse(path.with_suffix(".json.tmp").exists())
        with self.assertRaises(ValueError):
            sync.load_snapshot(path, "US", "stitches", "classic1x")

    def test_snapshot_metadata_can_be_enriched_without_clearing_existing_values(self):
        payload = self.snapshot(
            ["Bífi"], **{"Bífi": {"race": "Dwarf", "className": None}},
        )
        path = self.root / "snapshot.json"
        sync.write_snapshot_atomic(path, payload)
        self.assertTrue(sync.merge_snapshot_member_data(path, "BÍFI", None, "Warrior"))
        loaded = sync.load_snapshot(path)
        self.assertEqual(loaded["members"][0]["race"], "Dwarf")
        self.assertEqual(loaded["members"][0]["className"], "Warrior")
        self.assertFalse(sync.merge_snapshot_member_data(path, "Bífi", None, None))
        loaded_again = sync.load_snapshot(path)
        self.assertEqual(loaded_again["members"][0]["race"], "Dwarf")
        self.assertEqual(loaded_again["members"][0]["className"], "Warrior")

    def test_snapshot_rejects_duplicate_names(self):
        payload = self.snapshot(["Aba"])
        payload["members"].append(dict(payload["members"][0], characterName="ABA"))
        path = self.root / "snapshot.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ValueError):
            sync.load_snapshot(path)

    def test_comparison_classifies_new_known_inactive_dead_and_missing(self):
        existing = [
            {"id": "m0001", "name": "Known", "lifeStatus": "active", "race": "Human", "className": "Mage"},
            {"id": "m0002", "name": "Paused", "lifeStatus": "inactive", "race": None, "className": "Warrior"},
            {"id": "m0003", "name": "Return", "lifeStatus": "dead", "race": "Dwarf", "className": "Priest"},
            {"id": "m0004", "name": "Missing", "lifeStatus": "active", "race": None, "className": None},
        ]
        payload = self.snapshot(["Known", "Paused", "Return", "Brandnew"])
        categories = {item.name: item.category for item in sync.compare_snapshot(existing, payload)}
        self.assertEqual(categories, {
            "Brandnew": "new", "Return": "new_incarnation", "Paused": "inactive_found",
            "Missing": "missing_active", "Known": "known",
        })

    def make_view(self, model):
        view = SimpleNamespace(
            model=model,
            autosave=Mock(),
            current_tab="Gildenliste",
            _sync_detail_panel_visibility=Mock(),
            _update_tab_styles=Mock(),
            refresh_all=Mock(),
            status_var=SimpleNamespace(set=Mock()),
            _archive_portrait=Mock(),
        )
        return view

    def compare_model(self, model, payload):
        return sync.compare_snapshot([member.to_dict() for member in model.members], payload)

    def apply_review(self, view, payload, items, actions, confirmations=True):
        dialog = Mock()
        dialog.destroy = Mock()
        with patch.object(g.messagebox, "askyesno", return_value=confirmations), \
             patch.object(g.messagebox, "showerror") as error:
            g.GuildGearCheckerApp._apply_guild_roster_review(view, dialog, payload, items, actions)
        self.assertFalse(error.called, error.call_args)
        return dialog

    def test_new_name_after_dead_incarnation_creates_new_member_id(self):
        model = g.GuildModel()
        dead = model.add_member("Janos", "Test")
        dead.lifeStatus = "dead"
        payload = self.snapshot(["JANOS"])
        items = self.compare_model(model, payload)
        self.assertEqual(items[0].category, "new_incarnation")
        old_id = dead.id
        self.apply_review(SimpleNamespace(**vars(self.make_view(model))), payload, items, {items[0].key: "add"})
        self.assertEqual(dead.lifeStatus, "dead")
        current = model.find_current_by_name("Janos")
        self.assertIsNotNone(current)
        self.assertNotEqual(current.id, old_id)

    def test_missing_member_defaults_to_keep_and_changes_only_when_selected(self):
        model = g.GuildModel()
        member = model.add_member("Missing", "Test")
        payload = self.snapshot([])
        items = self.compare_model(model, payload)
        item = next(i for i in items if i.name == "Missing")
        view = self.make_view(model)
        self.apply_review(view, payload, items, {item.key: "keep"})
        self.assertEqual(member.lifeStatus, "active")
        self.apply_review(view, payload, items, {item.key: "inactive"})
        self.assertEqual(member.lifeStatus, "inactive")

    def test_inactive_found_is_not_auto_reactivated(self):
        model = g.GuildModel()
        member = model.add_member("Paused", "Test")
        model.set_member_life_status(member.id, "inactive")
        payload = self.snapshot(["Paused"])
        items = self.compare_model(model, payload)
        item = items[0]
        self.assertEqual(item.category, "inactive_found")
        self.apply_review(self.make_view(model), payload, items, {item.key: "keep"})
        self.assertEqual(member.lifeStatus, "inactive")
        self.apply_review(self.make_view(model), payload, items, {item.key: "reactivate"})
        self.assertEqual(member.lifeStatus, "active")

    def test_mark_dead_archives_first_and_keeps_project_identity(self):
        model = g.GuildModel()
        member = model.add_member("Gone", "Test")
        payload = self.snapshot([])
        item = self.compare_model(model, payload)[0]
        view = self.make_view(model)
        original_id = member.id
        self.apply_review(view, payload, [item], {item.key: "dead"})
        view._archive_portrait.assert_called_once_with(member)
        self.assertEqual(member.id, original_id)
        self.assertEqual(member.lifeStatus, "dead")
        self.assertTrue(member.deathDate)

    def test_metadata_fills_missing_but_conflict_needs_confirmation(self):
        model = g.GuildModel()
        member = model.add_member("Known", "Test")
        member.className = "Mage"
        payload = self.snapshot(
            ["Known"], **{"Known": {"race": "Human", "className": "Warrior"}},
        )
        items = self.compare_model(model, payload)
        view = self.make_view(model)
        dialog = Mock(); dialog.destroy = Mock()
        # First confirmation applies the review, second rejects the Class conflict.
        answers = iter([True, False])
        with patch.object(g.messagebox, "askyesno", side_effect=lambda *a, **k: next(answers)), \
             patch.object(g.messagebox, "showerror"):
            g.GuildGearCheckerApp._apply_guild_roster_review(
                view, dialog, payload, items, {items[0].key: "keep"},
            )
        self.assertEqual(member.race, "Human")
        self.assertEqual(member.className, "Mage")

    def test_invalid_reactivation_is_blocked_before_portrait_archival(self):
        model = g.GuildModel()
        active_main = model.add_member("CurrentMain", "Test")
        inactive_main = model.add_member("OldMain", "Test")
        player = model.add_player("Player")
        model.update_member_assignment(active_main.id, player.playerId, "main", "tank")
        model.update_member_assignment(inactive_main.id, player.playerId, "main", "tank",
                                       replace_existing_main=True)
        # Restore the intended conflict explicitly: current active main plus inactive main.
        active_main.characterType = "main"
        inactive_main.characterType = "main"
        inactive_main.lifeStatus = "inactive"
        model.dirty = False
        payload = self.snapshot(["OldMain", "CurrentMain"])
        items = self.compare_model(model, payload)
        old_item = next(item for item in items if item.name == "OldMain")
        view = self.make_view(model)
        dialog = Mock(); dialog.destroy = Mock()
        with patch.object(g.messagebox, "askyesno", return_value=True), \
             patch.object(g.messagebox, "showerror") as error:
            g.GuildGearCheckerApp._apply_guild_roster_review(
                view, dialog, payload, items, {old_item.key: "reactivate"},
            )
        self.assertTrue(error.called)
        view._archive_portrait.assert_not_called()
        self.assertEqual(inactive_main.lifeStatus, "inactive")
        self.assertEqual(active_main.lifeStatus, "active")

    def test_allowed_actions_keep_destructive_missing_changes_explicit(self):
        allowed = g.GuildGearCheckerApp._guild_sync_allowed_actions
        self.assertEqual(allowed("known"), ("keep",))
        self.assertEqual(allowed("inactive_found"), ("keep", "reactivate"))
        self.assertEqual(allowed("missing_active"), ("keep", "inactive", "dead", "delete"))
        self.assertEqual(g.GuildGearCheckerApp._guild_sync_default_action("missing_active"), "keep")
        self.assertEqual(g.GuildGearCheckerApp._guild_sync_default_action("new"), "add")


def main() -> int:
    global sync, g
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.repo_root.resolve()
    sync = load_module("ggc_guild_roster_sync", root / "app" / "guild_roster_sync.py")
    g = load_module("ggc_guild_sync_checker", root / "app" / "GuildGearChecker.py")
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(GuildRosterSyncTests)
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
