# -*- coding: utf-8 -*-
"""Gezielte Tests für den projektbezogenen Checker-/Grabber-Handoff."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class ProjectHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from app import GuildGearChecker as checker
        from app import project_handoff as handoff
        from app import project_storage as storage
        cls.checker = checker
        cls.handoff = handoff
        cls.storage = storage

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-project-handoff-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "Bierstuben.ggc"

    def make_model(self):
        model = self.checker.GuildModel()
        model.load_payload({
            "format": self.checker.PROJECT_FORMAT,
            "formatVersion": self.checker.PROJECT_FORMAT_VERSION,
            "members": [
                {"id": "m1000", "name": "Janos", "lifeStatus": "active"},
                {"id": "m1001", "name": "Bifi", "lifeStatus": "inactive"},
                {"id": "m1002", "name": "Alt", "lifeStatus": "dead"},
            ],
            "players": [],
        }, self.project)
        return model

    def test_project_runtime_is_local_and_separate(self):
        paths = self.storage.project_paths(self.project)
        other = self.storage.project_paths(self.root / "Andere.ggc")
        self.assertEqual(paths.runtime, self.root / "runtime")
        self.assertEqual(paths.handoff, self.root / "runtime" / "Bierstuben_handoff")
        self.assertNotEqual(paths.handoff, other.handoff)

    def test_import_preserves_current_members_and_creates_dead_incarnation(self):
        model = self.make_model()
        records = [
            {"characterName": "Janos"},
            {"characterName": "Bifi"},
            {"characterName": "Alt", "race": "Human", "className": "Warrior"},
            {"characterName": "Neu", "race": "Dwarf", "className": "Priest"},
            {"characterName": "Bífi"},
            {"characterName": "Burgûs"},
        ]
        summary = model.import_grabber_members(records)

        self.assertEqual(summary["added"], 4)
        self.assertEqual(summary["existing"], 2)
        self.assertEqual(summary["newIncarnations"], 1)
        alt = model.find_all_by_name("Alt")
        self.assertEqual(len(alt), 2)
        self.assertEqual({member.lifeStatus for member in alt}, {"active", "dead"})
        self.assertEqual(len({member.id for member in alt}), 2)
        new_alt = next(member for member in alt if member.lifeStatus == "active")
        self.assertEqual((new_alt.race, new_alt.className), ("Human", "Warrior"))
        self.assertEqual(model.find_by_name("Bifi").lifeStatus, "inactive")
        self.assertIsNotNone(model.find_by_name("Bífi"))
        self.assertIsNotNone(model.find_by_name("Burgûs"))

        repeated = model.import_grabber_members(records)
        self.assertEqual(repeated["added"], 0)
        self.assertEqual(len(model.members), 7)

    def test_same_token_is_applied_only_once(self):
        model = self.make_model()
        action = self.handoff.make_action(
            "add_members", {"members": [{"characterName": "Neu"}]}, token="same-token",
        )
        processed: set[str] = set()
        first = self.handoff.apply_actions(model, [action], processed)
        second = self.handoff.apply_actions(model, [action], processed)
        self.assertTrue(first["changed"])
        self.assertEqual(second["receipts"], [])
        self.assertEqual(len(model.find_all_by_name("Neu")), 1)

    def test_foreign_or_malformed_session_is_not_loaded(self):
        self.handoff.queue_action(
            self.project, "session-a", "add_members",
            {"members": [{"characterName": "Neu"}]}, token="foreign-token",
        )
        folder = self.storage.project_paths(self.project).handoff
        (folder / "broken.action.json").write_text("{", encoding="utf-8")
        self.assertEqual(self.handoff.pending_actions(self.project, "session-b"), [])
        self.assertEqual(len(self.handoff.pending_actions(self.project, "session-a")), 1)

    def test_concurrent_actions_are_kept_as_separate_files(self):
        session = "parallel-session"

        def queue(index: int) -> str:
            return self.handoff.queue_action(
                self.project, session, "add_members",
                {"members": [{"characterName": f"Neu{index}"}]},
            )

        with ThreadPoolExecutor(max_workers=4) as executor:
            tokens = list(executor.map(queue, range(12)))

        actions = self.handoff.pending_actions(self.project, session)
        self.assertEqual(len(actions), 12)
        self.assertEqual({action["token"] for action in actions}, set(tokens))
        self.assertEqual(
            len(list(self.storage.project_paths(self.project).handoff.glob("*.action.json"))),
            12,
        )

    def test_standalone_reads_fresh_and_saves_atomically_with_backup(self):
        model = self.make_model()
        model.save(self.project, backup=False)
        action = self.handoff.make_action(
            "add_members", {"members": [{"characterName": "Neu"}]}, token="standalone-token",
        )
        result = self.handoff.apply_actions_to_project(self.project, [action])
        stored = self.checker.GuildModel()
        stored.load(self.project)
        self.assertTrue(result["changed"])
        self.assertIsNotNone(stored.find_by_name("Neu"))
        self.assertTrue((self.root / "backups" / "Bierstuben_backup.ggc").is_file())

    def test_metadata_updates_by_id_without_overwriting_conflicts(self):
        model = self.make_model()
        janos = model.find_by_id("m1000")
        janos.note = "bleibt"
        self.assertTrue(model.update_member_metadata("m1000", "Human", "Warrior"))
        self.assertFalse(model.update_member_metadata("m1000", "Dwarf", "Priest"))
        self.assertEqual((janos.race, janos.className, janos.note), ("Human", "Warrior", "bleibt"))

    def test_graveyard_reset_action_keeps_member_dead(self):
        model = self.make_model()
        dead = model.find_by_id("m1002")
        dead.graveTemplateId = "grave-0001"
        dead.portraitZoom = 1.2
        action = self.handoff.make_action(
            "graveyard_reset", {"memberId": dead.id}, token="grave-reset",
        )
        result = self.handoff.apply_actions(model, [action])
        self.assertTrue(result["graveyardChanged"])
        self.assertEqual(dead.lifeStatus, "dead")
        self.assertEqual((dead.graveTemplateId, dead.portraitZoom), ("", 1.0))

    def test_graveyard_save_action_uses_existing_model_validation(self):
        model = self.make_model()
        dead = model.find_by_id("m1002")
        template = model.gravestone_inventory().templates[0]
        action = self.handoff.make_action("graveyard_save", {
            "memberId": dead.id,
            "graveTemplateId": template.grave_template_id,
            "portraitOffsetX": 0.2,
            "portraitOffsetY": -0.1,
            "portraitZoom": 1.15,
            "textOffsetX": 0.05,
            "textOffsetY": 0.1,
            "textScale": 0.9,
            "deathDate": "2026-09-15",
        }, token="grave-save")
        result = self.handoff.apply_actions(model, [action])
        self.assertTrue(result["graveyardChanged"])
        self.assertEqual(dead.lifeStatus, "dead")
        self.assertEqual(dead.graveTemplateId, template.grave_template_id)
        self.assertEqual((dead.portraitOffsetX, dead.portraitOffsetY, dead.portraitZoom), (0.2, -0.1, 1.15))

    def test_qt_checker_poll_applies_saves_refreshes_and_writes_receipt(self):
        from app.GuildGearCheckerQt import GuildGearCheckerQt

        model = self.make_model()
        model.save(self.project, backup=False)
        session = "qt-session"
        token = self.handoff.queue_action(
            self.project, session, "add_members",
            {"members": [{"characterName": "Neu"}]}, token="qt-add",
        )
        fake = SimpleNamespace(
            model=model,
            project_mode="legacy",
            _project_handoff_session_id=session,
            _project_handoff_processed_tokens=set(),
            _grave_pixmaps={},
            refresh_all=Mock(),
            set_status=Mock(),
        )
        GuildGearCheckerQt._poll_project_handoff(fake)

        stored = json.loads(self.project.read_text(encoding="utf-8"))
        self.assertIn("Neu", [member["name"] for member in stored["members"]])
        fake.refresh_all.assert_called_once_with()
        self.assertIn(token, fake._project_handoff_processed_tokens)
        receipt = self.handoff.read_receipt(self.project, session, token)
        self.assertTrue(receipt["ok"])

    def test_gravestone_handoff_persists_current_adjustment(self):
        model = self.make_model()
        dead = model.find_by_id("m1002")
        template = model.gravestone_inventory().templates[0]
        model.save(self.project, backup=False)
        session = "qt-gravestone-session"
        self.handoff.queue_action(
            self.project,
            session,
            "graveyard_save",
            {
                "memberId": dead.id,
                "graveTemplateId": template.grave_template_id,
                "portraitOffsetX": 0.2,
                "portraitOffsetY": -0.1,
                "portraitZoom": 1.15,
                "textOffsetX": 0.05,
                "textOffsetY": 0.1,
                "textScale": 0.9,
                "deathDate": "2026-09-15",
            },
            token="qt-gravestone-save",
        )
        actions = self.handoff.pending_actions(self.project, session)
        result = self.handoff.apply_actions_to_project(self.project, actions)

        stored = self.checker.GuildModel()
        stored.load(self.project)
        reloaded = stored.find_by_id(dead.id)
        self.assertEqual(reloaded.graveTemplateId, template.grave_template_id)
        self.assertEqual(
            (reloaded.portraitOffsetX, reloaded.portraitOffsetY, reloaded.portraitZoom),
            (0.2, -0.1, 1.15),
        )
        self.assertEqual(
            (reloaded.textOffsetX, reloaded.textOffsetY, reloaded.textScale),
            (0.05, 0.1, 0.9),
        )
        self.assertEqual(reloaded.deathDate, "2026-09-15")
        self.assertTrue(result["graveyardChanged"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.repo_root.resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProjectHandoffTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
