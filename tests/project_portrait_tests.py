# -*- coding: utf-8 -*-
"""Focused regression tests for project migration and historical portraits."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


g = None


class PortraitHarness:
    _historical_portrait_path = lambda self, member: g.GuildGearCheckerApp._historical_portrait_path(self, member)
    _historical_portrait_missing_path = lambda self, member: g.GuildGearCheckerApp._historical_portrait_missing_path(self, member)
    portrait_candidates = lambda self, member: g.GuildGearCheckerApp.portrait_candidates(self, member)
    _archive_portrait = lambda self, member: g.GuildGearCheckerApp._archive_portrait(self, member)

    def __init__(self, model):
        self.model = model


class ProjectAndPortraitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-project-portraits-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.portraits = self.root / "portraits"
        self.model = g.GuildModel()
        self.model.project_path = self.root / "guild.ggc"
        self.view = PortraitHarness(self.model)

    def member(self, member_id="m0042", name="Janos", status="active"):
        member = g.Member(id=member_id, name=name, lifeStatus=status)
        self.model.members.append(member)
        return member

    def write_portrait(self, color, member_id="m0042"):
        self.portraits.mkdir(parents=True, exist_ok=True)
        path = self.portraits / f"{member_id}.png"
        g.Image.new("RGB", (12, 18), color).save(path)
        return path

    def mark_dead(self, member):
        self.view.selected_member_id = member.id
        self.view.autosave = Mock()
        self.view.current_tab = "Gildenliste"
        self.view._sync_detail_panel_visibility = Mock()
        self.view._update_tab_styles = Mock()
        self.view.refresh_all = Mock()
        self.view.show_member = Mock()
        self.view.render_graveyard = Mock()
        with patch.object(g.messagebox, "askyesno", return_value=True):
            g.GuildGearCheckerApp.toggle_life_selected(self.view)

    def test_project_metadata_and_legacy_class_spec_are_preserved(self):
        payload = {
            "formatVersion": 1,
            "region": "US",
            "realm": "defias-pillager",
            "gameVersion": "classic-era-test",
            "members": [{
                "id": "m0042", "name": "Legacy", "className": "Warrior",
                "classSpec": "Warrior / Fury",
            }],
        }
        self.model.load_payload(payload)
        saved = self.model.to_payload()
        self.assertEqual((saved["region"], saved["realm"], saved["gameVersion"]),
                         ("US", "defias-pillager", "classic-era-test"))
        self.assertEqual(self.model.members[0].spec, "Fury")

    def test_future_project_version_is_rejected_transactionally(self):
        original = self.member("m0001", "Bestand")
        self.model.region = "EU"
        with self.assertRaises(ValueError):
            self.model.load_payload({
                "formatVersion": g.PROJECT_FORMAT_VERSION + 1,
                "region": "US", "members": [{"id": "m9999", "name": "Neu"}],
            })
        self.assertEqual(self.model.members, [original])
        self.assertEqual(self.model.region, "EU")

    def test_next_id_and_manual_name_reuse_follow_incarnation_identity(self):
        self.model.load_payload({
            "nextId": 1,
            "members": [{"id": "m1001", "name": "Janos", "lifeStatus": "dead"}],
        })
        self.assertGreater(self.model.next_id, 1001)
        active = self.model.add_member("JANOS")
        self.assertNotEqual(active.id, "m1001")
        self.assertEqual(active.lifeStatus, "active")
        with self.assertRaises(ValueError):
            self.model.add_member("janos")

    def test_death_keeps_member_id_portrait_unchanged(self):
        member = self.member()
        named = self.write_portrait((180, 20, 20))
        original = named.read_bytes()
        self.mark_dead(member)
        historical = self.portraits / "m0042.png"
        self.assertEqual(historical.read_bytes(), original)
        selected = next(path for path in self.view.portrait_candidates(member) if path.exists())
        self.assertEqual(selected, historical)
        self.assertEqual(historical.read_bytes(), original)

    def test_two_dead_same_name_keep_distinct_historical_portraits(self):
        first = self.member("m0042")
        self.write_portrait((180, 20, 20), first.id)
        self.mark_dead(first)
        first_path = self.portraits / "m0042.png"
        first_bytes = first_path.read_bytes()

        second = self.member("m0087")
        self.write_portrait((20, 20, 180), second.id)
        self.mark_dead(second)
        second_path = self.portraits / "m0087.png"

        self.assertNotEqual(first_path, second_path)
        self.assertNotEqual(first_path.read_bytes(), second_path.read_bytes())
        self.assertEqual(first_path.read_bytes(), first_bytes)

    def test_missing_portrait_at_death_never_links_later_same_name(self):
        member = self.member()
        self.mark_dead(member)
        self.write_portrait((20, 180, 20), "m0087")
        existing = [path for path in self.view.portrait_candidates(member) if path.exists()]
        self.assertEqual(existing, [])
        self.assertFalse((self.portraits / "history").exists())

    def test_emergency_reanimation_preserves_history_and_uses_explicit_confirmation(self):
        dead = self.member("m0042", status="dead")
        dead.deathDate = "2026-09-12"
        dead.graveTemplateId = "grave-0001"
        history = self.portraits / "m0042.png"
        history.parent.mkdir(parents=True, exist_ok=True)
        history.write_bytes(b"history")
        view = SimpleNamespace(
            model=self.model, selected_member_id=dead.id, autosave=Mock(),
            current_tab="Friedhof", _sync_detail_panel_visibility=Mock(),
            _update_tab_styles=Mock(), refresh_all=Mock(), show_member=Mock(),
        )
        with patch.object(g.messagebox, "askyesno", return_value=True) as confirm:
            g.GuildGearCheckerApp.toggle_activity_selected(view)
        self.assertTrue(confirm.called)
        self.assertEqual(dead.lifeStatus, "active")
        self.assertEqual(dead.graveTemplateId, "grave-0001")
        self.assertEqual(dead.deathDate, "2026-09-12")
        self.assertEqual(history.read_bytes(), b"history")
        self.assertFalse((self.portraits / "history").exists())

    def test_reactivation_cannot_create_second_active_same_name(self):
        dead = self.member("m0042", status="dead")
        self.member("m0087", status="active")
        view = SimpleNamespace(model=self.model, selected_member_id=dead.id)
        with patch.object(g.messagebox, "showwarning") as warning:
            g.GuildGearCheckerApp.toggle_life_selected(view)
        self.assertEqual(dead.lifeStatus, "dead")
        self.assertTrue(warning.called)


def main():
    global g
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    module_path = args.repo_root.resolve() / "app" / "GuildGearChecker.py"
    spec = importlib.util.spec_from_file_location("ggc_project_portrait_target", module_path)
    g = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = g
    spec.loader.exec_module(g)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProjectAndPortraitTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
