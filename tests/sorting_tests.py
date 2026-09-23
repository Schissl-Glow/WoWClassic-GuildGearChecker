# -*- coding: utf-8 -*-
"""Regression tests for language-independent, view-only member sorting."""
from __future__ import annotations

import argparse
import copy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


g = None


class SortingTests(unittest.TestCase):
    def setUp(self):
        self.members = [
            g.Member("m0001", "Ánna", className="Priest", spec="Holy", gearStatus="BiS", lastChecked="2025-12-01"),
            g.Member("m0002", "bert", className="Warrior", spec="Fury", gearStatus="Pre-BiS", lastChecked="2026-01-05"),
            g.Member("m0003", "anna", className="Mage", spec="Frost", gearStatus="S+", lastChecked=""),
            g.Member("m0004", "Janos", className="Druid", spec="Balance", gearStatus="Level", lastChecked="31.01.2026"),
            g.Member("m0005", "Janos", className="Rogue", spec="Combat", gearStatus="Level", lastChecked="invalid"),
        ]

    def ids(self, column, descending=False):
        return [m.id for m in g.sort_members(self.members, column, descending)]

    def test_name_up_and_down_are_unicode_and_case_insensitive(self):
        ascending = self.ids("name")
        descending = self.ids("name", True)
        self.assertEqual(set(ascending), {m.id for m in self.members})
        self.assertEqual(descending, list(reversed(ascending)))
        self.assertEqual([m.name for m in self.members], ["Ánna", "bert", "anna", "Janos", "Janos"])

    def test_class_and_spec_up_and_down(self):
        self.assertEqual([g.sort_members(self.members, "class")[0].className,
                          g.sort_members(self.members, "class", True)[0].className],
                         ["Druid", "Warrior"])
        self.assertEqual([g.sort_members(self.members, "spec")[0].spec,
                          g.sort_members(self.members, "spec", True)[0].spec],
                         ["Balance", "Holy"])

    def test_gear_uses_internal_order(self):
        self.assertEqual([g.gear_status_key(m.gearStatus) for m in g.sort_members(self.members, "gear")],
                         ["s_plus", "bis", "pre_bis", "level", "level"])

    def test_last_checked_is_a_date_and_missing_or_invalid_are_always_last(self):
        self.assertEqual(self.ids("checked"), ["m0001", "m0002", "m0004", "m0003", "m0005"])
        self.assertEqual(self.ids("checked", True), ["m0004", "m0002", "m0001", "m0003", "m0005"])

    def test_sort_is_view_only_and_keeps_duplicate_incarnations(self):
        before = copy.deepcopy([m.to_dict() for m in self.members])
        visible = g.sort_members(self.members, "name")
        self.assertEqual([m.to_dict() for m in self.members], before)
        self.assertEqual([m.id for m in visible if m.name == "Janos"], ["m0004", "m0005"])

    def test_filter_then_sort_keeps_all_matching_rows(self):
        visible = g.filter_and_sort_members(
            self.members, "Alle Charaktere", "jan", None, None, "class", True,
        )
        self.assertEqual([m.id for m in visible], ["m0005", "m0004"])

    def test_header_click_toggles_direction_and_indicator(self):
        view = SimpleNamespace(
            current_tab="Gildenliste", sort_state={},
            _update_sort_headings=Mock(), refresh_center=Mock(),
        )
        g.GuildGearCheckerApp._sort_by(view, "gear")
        self.assertEqual(view.sort_state["Gildenliste"], ("gear", False))
        g.GuildGearCheckerApp._sort_by(view, "gear")
        self.assertEqual(view.sort_state["Gildenliste"], ("gear", True))
        tree = Mock()
        heading_view = SimpleNamespace(
            current_tab="Gildenliste", sort_state={"Gildenliste": ("gear", False)},
            _table_headings={"name": ("Character", 1), "gear": ("Gear", 1)}, tree=tree,
        )
        g.GuildGearCheckerApp._update_sort_headings(heading_view)
        self.assertIn("▲", tree.heading.call_args_list[-1].kwargs["text"])


def main() -> int:
    global g
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    path = args.repo_root.resolve() / "app" / "GuildGearChecker.py"
    spec = importlib.util.spec_from_file_location("ggc_sort_target", path)
    g = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = g
    spec.loader.exec_module(g)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SortingTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
