# -*- coding: utf-8 -*-
"""Focused offline tests for manual gear recheck and optional outdated warnings."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


g = None


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class GearRecheckTests(unittest.TestCase):
    def setUp(self):
        self.model = g.GuildModel()
        self.member = self.model.add_member("Tester", "Test")
        self.model.dirty = False

    def test_tracking_defaults_are_off_and_120_days(self):
        self.assertFalse(g.normalize_bool_setting(None))
        self.assertFalse(g.normalize_bool_setting("false"))
        self.assertFalse(g.normalize_bool_setting(0))
        self.assertTrue(g.normalize_bool_setting(True))
        self.assertEqual(g.GEAR_OUTDATED_DEFAULT_DAYS, 120)
        self.assertEqual(g.normalize_outdated_days(None), 120)
        self.assertEqual(g.normalize_outdated_days("abc"), 120)
        self.assertEqual(g.normalize_outdated_days(0), 120)
        self.assertEqual(g.normalize_outdated_days(3651), 120)
        self.assertEqual(g.normalize_outdated_days(90), 90)

    def test_age_threshold_is_inclusive_and_never_applies_without_date(self):
        today = date(2026, 9, 13)
        self.member.lastChecked = (today - timedelta(days=119)).isoformat()
        self.assertFalse(g.member_check_is_outdated(self.member, True, 120, today))
        self.member.lastChecked = (today - timedelta(days=120)).isoformat()
        self.assertTrue(g.member_check_is_outdated(self.member, True, 120, today))
        self.assertFalse(g.member_check_is_outdated(self.member, False, 120, today))
        self.member.lastChecked = ""
        self.assertIsNone(g.last_checked_age_days(self.member.lastChecked, today))
        self.assertFalse(g.member_check_is_outdated(self.member, True, 120, today))

    def test_outdated_warning_only_for_active_characters(self):
        today = date(2026, 9, 13)
        self.member.lastChecked = (today - timedelta(days=300)).isoformat()
        self.member.lifeStatus = "inactive"
        self.assertFalse(g.member_check_is_outdated(self.member, True, 120, today))
        self.member.lifeStatus = "dead"
        self.assertFalse(g.member_check_is_outdated(self.member, True, 120, today))

    def make_view(self):
        return SimpleNamespace(
            model=self.model,
            selected_member_id=self.member.id,
            autosave=Mock(), refresh_all=Mock(), show_member=Mock(),
            status_var=SimpleNamespace(set=Mock()),
        )

    def test_manual_recheck_updates_date_even_if_statuses_are_unchanged(self):
        self.member.gearStatus = "Gut"
        self.member.enchants = "OK"
        self.member.lastChecked = "2026-01-01"
        before = (self.member.gearStatus, self.member.enchants)
        view = self.make_view()
        g.GuildGearCheckerApp.confirm_gear_recheck_selected(view)
        self.assertEqual((self.member.gearStatus, self.member.enchants), before)
        self.assertEqual(self.member.lastChecked, g.today_iso())
        self.assertTrue(self.model.dirty)
        view.autosave.assert_called_once()
        view.refresh_all.assert_called_once_with(select_first=False)
        view.show_member.assert_called_once_with(self.member.id)

    def test_manual_recheck_does_not_change_identity_or_assignments(self):
        player = self.model.add_player("Player")
        self.model.update_member_assignment(self.member.id, player.playerId, "main", "tank")
        self.model.dirty = False
        before = (self.member.id, self.member.playerId, self.member.characterType, self.member.raidRole)
        g.GuildGearCheckerApp.confirm_gear_recheck_selected(self.make_view())
        self.assertEqual(
            (self.member.id, self.member.playerId, self.member.characterType, self.member.raidRole), before,
        )

    def test_manual_recheck_is_blocked_for_inactive_and_dead(self):
        for status in ("inactive", "dead"):
            with self.subTest(status=status):
                self.member.lifeStatus = status
                self.member.lastChecked = "2026-01-01"
                self.model.dirty = False
                view = self.make_view()
                with patch.object(g.messagebox, "showwarning") as warning:
                    g.GuildGearCheckerApp.confirm_gear_recheck_selected(view)
                self.assertEqual(self.member.lastChecked, "2026-01-01")
                self.assertFalse(self.model.dirty)
                view.autosave.assert_not_called()
                warning.assert_called_once()

    def test_tracking_adds_outdated_active_member_to_action_required(self):
        today = date(2026, 9, 13)
        self.member.gearStatus = "BiS"
        self.member.lastChecked = (today - timedelta(days=120)).isoformat()
        self.assertFalse(g.member_matches_tab(self.member, "Handlungsbedarf"))
        self.assertTrue(g.member_matches_tab(
            self.member, "Handlungsbedarf", True, 120, today,
        ))
        self.member.lastChecked = ""
        self.assertFalse(g.member_matches_tab(
            self.member, "Handlungsbedarf", True, 120, today,
        ))

    def test_display_adds_warning_only_when_tracking_enabled(self):
        self.member.lastChecked = (date.today() - timedelta(days=120)).isoformat()
        view = SimpleNamespace(gear_outdated_tracking=False, gear_outdated_days=120)
        plain = g.GuildGearCheckerApp._member_last_checked_value(view, self.member)
        self.assertEqual(plain, self.member.lastChecked)
        view.gear_outdated_tracking = True
        warned = g.GuildGearCheckerApp._member_last_checked_value(view, self.member)
        self.assertIn(self.member.lastChecked, warned)
        self.assertIn(g.tr("checker.check_outdated"), warned)


def main() -> int:
    global g
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    g = load_module("ggc_gear_recheck", args.repo_root.resolve() / "app" / "GuildGearChecker.py")
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(GearRecheckTests)
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
