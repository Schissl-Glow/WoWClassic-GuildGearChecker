# -*- coding: utf-8 -*-
"""Regression tests for players, Main/Twink, raid roles, and project migration."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


g = None


class PlayerModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-players-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = g.GuildModel()

    def add_character(self, name, status="active"):
        member = self.model.add_member(name, "Test")
        member.lifeStatus = status
        return member

    def import_csv(self, names):
        csv_path = self.root / "raid.csv"
        csv_path.write_text("Name;Amount\n" + "".join(f"{name};1\n" for name in names),
                            encoding="utf-8-sig")
        view = SimpleNamespace(
            model=self.model, autosave=Mock(), current_tab="Gildenliste",
            _update_tab_styles=Mock(), refresh_all=Mock(),
            status_var=SimpleNamespace(set=Mock()),
        )
        with patch.object(g.filedialog, "askopenfilename", return_value=str(csv_path)), \
             patch.object(g.messagebox, "askyesno", return_value=True), \
             patch.object(g.messagebox, "showinfo"), \
             patch.object(g.messagebox, "showerror") as error:
            g.GuildGearCheckerApp.import_csv(view)
            self.assertFalse(error.called, error.call_args)

    def test_player_create_rename_and_multiple_characters(self):
        player = self.model.add_player("Marten")
        first = self.add_character("Schneeflocke")
        second = self.add_character("Tazgø")
        self.model.update_member_assignment(first.id, player.playerId, "main", "healer")
        self.model.update_member_assignment(second.id, player.playerId, "twink", "dps")
        ids_before = [first.id, second.id]
        self.model.rename_player(player.playerId, "Marten HC")
        self.assertEqual(self.model.find_player_by_id(player.playerId).playerName, "Marten HC")
        self.assertEqual([first.playerId, second.playerId], [player.playerId, player.playerId])
        self.assertEqual([first.id, second.id], ids_before)

    def test_new_player_id_never_reuses_loaded_id(self):
        self.model.load_payload({
            "formatVersion": 2,
            "nextPlayerId": 1,
            "players": [{"playerId": "p0042", "playerName": "Historisch"}],
            "members": [],
        })
        created = self.model.add_player("Neu")
        self.assertEqual(created.playerId, "p0043")

    def test_character_without_player_and_no_main_are_allowed(self):
        member = self.add_character("OhneSpieler")
        self.assertIsNone(member.playerId)
        self.assertEqual(member.characterType, "not_set")
        self.assertEqual(member.raidRole, "not_set")
        player = self.model.add_player("Marten")
        self.model.update_member_assignment(member.id, player.playerId, "twink", "tank")
        self.assertEqual(self.model.active_main_for_player(player.playerId), None)

    def test_second_active_main_requires_explicit_replacement(self):
        player = self.model.add_player("Marten")
        first = self.add_character("Schneeflocke")
        second = self.add_character("Tazgø")
        self.model.update_member_assignment(first.id, player.playerId, "main", "healer")
        with self.assertRaises(g.MainConflictError):
            self.model.update_member_assignment(second.id, player.playerId, "main", "dps")
        self.assertEqual((first.characterType, second.characterType), ("main", "not_set"))
        self.model.update_member_assignment(
            second.id, player.playerId, "main", "dps", replace_existing_main=True
        )
        self.assertEqual((first.characterType, second.characterType), ("twink", "main"))

    def test_dead_main_does_not_block_new_active_main(self):
        player = self.model.add_player("Marten")
        historical = self.add_character("Schneeflocke", status="dead")
        historical.playerId = player.playerId
        historical.characterType = "main"
        historical.raidRole = "healer"
        current = self.add_character("Tazgø")
        self.model.update_member_assignment(current.id, player.playerId, "main", "tank")
        self.assertEqual(historical.characterType, "main")
        self.assertEqual(current.characterType, "main")

    def test_emergency_reanimation_requires_explicit_flag_and_main_resolution(self):
        player = self.model.add_player("Marten")
        historical = self.add_character("Schneeflocke", status="dead")
        historical.playerId = player.playerId
        historical.characterType = "main"
        current = self.add_character("Tazgø")
        self.model.update_member_assignment(current.id, player.playerId, "main", "healer")
        with self.assertRaises(ValueError):
            self.model.set_member_life_status(historical.id, "active")
        with self.assertRaises(g.MainConflictError):
            self.model.set_member_life_status(
                historical.id, "active", allow_dead_reanimation=True,
            )
        self.assertEqual((historical.lifeStatus, current.characterType), ("dead", "main"))
        self.model.set_member_life_status(
            historical.id, "active", replace_existing_main=True,
            allow_dead_reanimation=True,
        )
        self.assertEqual((historical.lifeStatus, historical.characterType), ("active", "main"))
        self.assertEqual(current.characterType, "twink")

    def test_inactive_main_keeps_assignment_but_is_not_active_main(self):
        player = self.model.add_player("Marten")
        main = self.add_character("Schneeflocke")
        twink = self.add_character("Tazgø")
        self.model.update_member_assignment(main.id, player.playerId, "main", "healer")
        self.model.update_member_assignment(twink.id, player.playerId, "twink", "dps")
        original = (main.id, main.playerId, main.characterType, twink.playerId)
        self.model.set_member_life_status(main.id, "inactive")
        self.assertEqual(
            (main.id, main.playerId, main.characterType, twink.playerId), original,
        )
        self.assertIsNone(self.model.active_main_for_player(player.playerId))
        self.assertIsNone(self.model.associated_main(twink))
        self.model.set_member_life_status(main.id, "active")
        self.assertEqual(self.model.active_main_for_player(player.playerId), main)
        self.assertEqual(self.model.associated_main(twink), main)

    def test_inactive_twink_keeps_group_and_identity_on_reactivation(self):
        player = self.model.add_player("Marten")
        main = self.add_character("Schneeflocke")
        twink = self.add_character("Tazgø")
        self.model.update_member_assignment(main.id, player.playerId, "main", "healer")
        self.model.update_member_assignment(twink.id, player.playerId, "twink", "dps")
        before = (twink.id, twink.playerId, twink.characterType, twink.raidRole)
        self.model.set_member_life_status(twink.id, "inactive")
        self.model.set_member_life_status(twink.id, "active")
        self.assertEqual(
            (twink.id, twink.playerId, twink.characterType, twink.raidRole), before,
        )

    def test_inactive_status_preserves_member_data_and_forbids_dead_to_inactive(self):
        member = self.add_character("Keeper")
        member.race = "Human"
        member.className = "Warrior"
        member.spec = "Protection"
        member.classSpec = "Warrior - Protection"
        member.gearStatus = "Gut"
        member.enchants = "OK"
        member.note = "keep"
        member.lastChecked = "2026-09-12"
        player = self.model.add_player("Owner")
        self.model.update_member_assignment(member.id, player.playerId, "main", "tank")
        before = copy.deepcopy(member.to_dict())
        self.model.set_member_life_status(member.id, "inactive")
        after = member.to_dict()
        self.assertEqual(after["lifeStatus"], "inactive")
        self.assertEqual(
            {key: value for key, value in after.items() if key != "lifeStatus"},
            {key: value for key, value in before.items() if key != "lifeStatus"},
        )
        self.assertFalse(member.deathDate)
        self.assertFalse(member.graveTemplateId)
        self.assertFalse(member.gravestoneTemplate)
        self.model.set_member_life_status(member.id, "dead")
        with self.assertRaises(ValueError):
            self.model.set_member_life_status(member.id, "inactive")

    def test_roundtrip_players_assignments_roles_and_dead_history(self):
        player = self.model.add_player("Marten")
        roles = ["tank", "tank", "healer", "dps", "not_set"]
        for index, role in enumerate(roles):
            member = self.add_character(f"Figur{index}")
            self.model.update_member_assignment(member.id, player.playerId, "twink", role)
            if index == 2:
                self.model.set_member_life_status(member.id, "dead")
        path = self.root / "players.ggc"
        self.model.save(path)
        loaded = g.GuildModel()
        loaded.load(path)
        self.assertEqual(loaded.to_payload()["players"], self.model.to_payload()["players"])
        self.assertEqual(
            [(m.id, m.playerId, m.characterType, m.raidRole, m.lifeStatus) for m in loaded.members],
            [(m.id, m.playerId, m.characterType, m.raidRole, m.lifeStatus) for m in self.model.members],
        )

    def test_legacy_project_migrates_without_player_guessing(self):
        self.model.load_payload({
            "formatVersion": 1,
            "members": [{
                "id": "m0042", "name": "Schneeflocke", "lifeStatus": "active",
                "gearStatus": "Nachbessern", "enchants": "Fehlt",
            }],
        })
        member = self.model.members[0]
        self.assertEqual(self.model.players, [])
        self.assertIsNone(member.playerId)
        self.assertEqual(member.characterType, "not_set")
        self.assertEqual(member.raidRole, "not_set")
        self.assertEqual(member.gearStatus, "Level")
        payload = self.model.to_payload()
        self.assertNotIn("enchants", payload["members"][0])
        self.assertEqual(payload["formatVersion"], g.PROJECT_FORMAT_VERSION)

    def test_project_format_four_roundtrip_and_format_three_migration(self):
        legacy = g.GuildModel()
        legacy.load_payload({
            "formatVersion": 3,
            "members": [
                {"id": "m0001", "name": "Alive", "lifeStatus": "active"},
                {"id": "m0002", "name": "Dead", "lifeStatus": "dead"},
            ],
        })
        self.assertEqual([member.lifeStatus for member in legacy.members], ["active", "dead"])
        self.assertEqual(legacy.to_payload()["formatVersion"], 4)

        inactive = g.GuildModel()
        inactive.load_payload({
            "formatVersion": 4,
            "members": [{"id": "m0003", "name": "Paused", "lifeStatus": "inactive"}],
        })
        self.assertEqual(inactive.members[0].lifeStatus, "inactive")
        self.assertEqual(inactive.to_payload()["members"][0]["lifeStatus"], "inactive")

        with self.assertRaises(ValueError):
            g.GuildModel().load_payload({
                "formatVersion": 4,
                "members": [{"id": "m0004", "name": "Broken", "lifeStatus": "unknown"}],
            })
        with self.assertRaises(ValueError):
            g.GuildModel().load_payload({
                "formatVersion": 3,
                "members": [{"id": "m0005", "name": "TooNew", "lifeStatus": "inactive"}],
            })

    def test_inactive_member_tab_visibility(self):
        member = self.add_character("Inactive")
        member.gearStatus = "Nachbessern"
        member.enchants = "Fehlt"
        self.model.set_member_life_status(member.id, "inactive")
        self.assertTrue(g.member_matches_tab(member, "Inaktiv"))
        self.assertTrue(g.member_matches_tab(member, "Alle Charaktere"))
        for tab in ("Gildenliste", "Handlungsbedarf", "Ungeprüft", "Friedhof", "Roster"):
            self.assertFalse(g.member_matches_tab(member, tab), tab)

    def test_current_name_identity_includes_inactive_without_auto_reactivation(self):
        inactive = self.add_character("Janos")
        self.model.set_member_life_status(inactive.id, "inactive")
        with self.assertRaises(ValueError):
            self.model.add_member("JANOS")
        existing, new_names, dead_existing = self.model.classify_member_import(["janos"])
        self.assertEqual(existing, [inactive])
        self.assertEqual(new_names, [])
        self.assertEqual(dead_existing, [])
        self.assertEqual(inactive.lifeStatus, "inactive")

    def test_import_preserves_existing_assignment(self):
        player = self.model.add_player("Marten")
        member = self.add_character("Schneeflocke")
        self.model.update_member_assignment(member.id, player.playerId, "main", "healer")
        before = copy.deepcopy(self.model.to_payload()["members"])
        self.import_csv(["SCHNEEFLOCKE"])
        self.assertEqual(self.model.to_payload()["members"], before)

    def test_duplicate_player_ids_and_two_loaded_active_mains_are_conflicts(self):
        player = {"playerId": "p0001", "playerName": "Marten"}
        with self.assertRaises(ValueError):
            self.model.load_payload({"formatVersion": 2, "players": [player, dict(player)], "members": []})
        payload = {
            "formatVersion": 2,
            "players": [player],
            "members": [
                {"id": "m0001", "name": "Eins", "playerId": "p0001", "characterType": "main"},
                {"id": "m0002", "name": "Zwei", "playerId": "p0001", "characterType": "main"},
            ],
        }
        with self.assertRaises(ValueError):
            self.model.load_payload(payload)


def main():
    global g
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    module_path = args.repo_root.resolve() / "app" / "GuildGearChecker.py"
    spec = importlib.util.spec_from_file_location("ggc_player_model_target", module_path)
    g = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = g
    spec.loader.exec_module(g)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PlayerModelTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
