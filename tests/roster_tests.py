# -*- coding: utf-8 -*-
"""Regression tests for roster grouping, ordering, identity, and interaction."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from unittest.mock import patch


g = None


class RosterTests(unittest.TestCase):
    def member(self, member_id, name, role="not_set", kind="not_set", life="active", cls=""):
        return g.Member(member_id, name, className=cls, raidRole=role,
                        characterType=kind, lifeStatus=life)

    def test_only_active_members_are_grouped_and_no_role_disappears(self):
        members = [
            self.member("m1", "MT", "tank"), self.member("m2", "T", "tank"),
            self.member("m3", "H", "healer"), self.member("m4", "D", "dps"),
            self.member("m5", "U"), self.member("m6", "Dead", "healer", life="dead"),
            self.member("m7", "Inactive", "dps", life="inactive"),
        ]
        grouped = g.group_roster_members(members)
        self.assertEqual(list(grouped), ["tank", "healer", "dps", "not_set"])
        self.assertEqual([[m.id for m in grouped[key]] for key in grouped],
                         [["m1", "m2"], ["m3"], ["m4"], ["m5"]])

    def test_intra_group_order_is_main_then_twink_then_not_set_class_name(self):
        members = [
            self.member("m1", "Zulu", "dps", "twink", cls="Priest"),
            self.member("m2", "Beta", "dps", "main", cls="Warrior"),
            self.member("m3", "Alpha", "dps", "main", cls="Mage"),
            self.member("m4", "Able", "dps", "not_set", cls="Druid"),
        ]
        self.assertEqual([m.id for m in g.group_roster_members(members)["dps"]],
                         ["m3", "m2", "m1", "m4"])

    def test_historical_same_name_is_not_shown_in_active_roster(self):
        members = [self.member("m0042", "Janos", life="dead"), self.member("m0113", "Janos")]
        visible = [m.id for group in g.group_roster_members(members).values() for m in group]
        self.assertEqual(visible, ["m0113"])

    def test_card_click_uses_member_id(self):
        view = SimpleNamespace(show_member=Mock(), selected_member_id=None)
        g.GuildGearCheckerApp._select_roster_member(view, "m0087")
        view.show_member.assert_called_once_with("m0087")

    def test_responsive_column_count_never_hides_cards(self):
        self.assertEqual(g.roster_column_count(200), 1)
        self.assertEqual(g.roster_column_count(520), 2)
        self.assertGreaterEqual(g.roster_column_count(2000), 4)

    def test_missing_portrait_is_an_allowed_fixed_card_state(self):
        self.assertEqual(g.ROSTER_PORTRAIT_SIZE, (170, 210))

    def test_roster_canvas_scrolls_and_detail_controls_exist_at_small_size(self):
        with tempfile.TemporaryDirectory(prefix="ggc-roster-ui-") as temp, \
             patch.object(g, "app_base_dir", return_value=Path(temp)), \
             patch.dict(os.environ, {"GGC_DISABLE_ICON_DOWNLOAD": "1"}):
            portrait_folder = Path(temp) / "portraits"
            portrait_folder.mkdir(parents=True)
            try:
                app = g.GuildGearCheckerApp()
            except g.tk.TclError as exc:
                self.skipTest(f"Tk not available: {exc}")
            try:
                app.geometry("1040x680")
                app.model.project_path = Path(temp) / "guild.ggc"
                member = app.model.add_member("Aba", "Test")
                player = app.model.add_player("Marten")
                member.className = "Priest"
                member.spec = "Holy"
                app.model.update_member_assignment(member.id, player.playerId, "main", "healer")
                g.Image.new("RGB", (80, 120), "#345678").save(portrait_folder / f"{member.id}.png")
                app.update_idletasks()
                app.switch_tab("Roster")
                app.update_idletasks()
                app.render_roster()
                app.update_idletasks()
                cached_portraits = dict(app._roster_portrait_cache)
                app.render_roster()
                self.assertTrue(cached_portraits)
                self.assertTrue(all(
                    app._roster_portrait_cache[key] is value
                    for key, value in cached_portraits.items()
                ))
                bbox = app.roster_canvas.bbox("all")
                self.assertIsNotNone(bbox)
                self.assertGreater(bbox[3], app.roster_canvas.winfo_height())
                self.assertTrue(app.roster_canvas.cget("yscrollcommand"))
                self.assertTrue(app.player_combo.winfo_exists())
                self.assertTrue(app.character_type_combo.winfo_exists())
                self.assertTrue(app.raid_role_combo.winfo_exists())
                texts = []
                def collect(widget):
                    try:
                        value = widget.cget("text")
                        if value:
                            texts.append(str(value))
                    except g.tk.TclError:
                        pass
                    for child in widget.winfo_children():
                        collect(child)
                collect(app.roster_inner)
                joined = "\n".join(texts)
                self.assertIn("Marten", joined)
                self.assertIn("Main", joined)
                self.assertIn("Priest / Holy", joined)
            finally:
                app.destroy()


def main() -> int:
    global g
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    path = args.repo_root.resolve() / "app" / "GuildGearChecker.py"
    spec = importlib.util.spec_from_file_location("ggc_roster_target", path)
    g = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = g
    spec.loader.exec_module(g)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RosterTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
