# -*- coding: utf-8 -*-
"""Gezielte Regressionstests für strikt projektgebundene Speicherpfade."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


g = None
p = None
s = None


class ProjectStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-project-storage-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def project(self, guild: str) -> Path:
        return self.root / guild / f"{guild}.ggc"

    @staticmethod
    def payload(member_id: str = "m0001", name: str = "Janos") -> dict:
        return {
            "format": g.PROJECT_FORMAT,
            "formatVersion": g.PROJECT_FORMAT_VERSION,
            "members": [{"id": member_id, "name": name, "lifeStatus": "active"}],
            "players": [],
        }

    def write_project(self, path: Path, payload: dict | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload or self.payload()), encoding="utf-8")

    def test_checker_start_helper_ignores_global_autosave_and_seed(self):
        model = g.GuildModel()
        model.new_seed()
        fake = SimpleNamespace(model=model, _refresh_project_label=Mock())

        g.GuildGearCheckerApp._load_autosave_or_seed(fake)

        self.assertEqual(model.members, [])
        self.assertIsNone(model.project_path)
        fake._refresh_project_label.assert_called_once_with()

    def test_no_autosave_without_active_project(self):
        model = g.GuildModel()
        model.new_empty()
        model.dirty = True
        fake = SimpleNamespace(model=model)
        with patch.object(g, "atomic_write_bytes") as writer:
            g.GuildGearCheckerApp.autosave(fake)
        writer.assert_not_called()

    def test_two_projects_have_separate_portraits_history_autosaves_and_backups(self):
        a = s.project_paths(self.project("A"))
        b = s.project_paths(self.project("B"))
        for field in ("portraits", "history", "autosave", "backups"):
            self.assertNotEqual(getattr(a, field), getattr(b, field))
        self.assertEqual(a.portraits, a.project.parent / "portraits")
        self.assertEqual(a.history, a.project.parent / "portraits" / "history")
        self.assertEqual(a.autosave, a.project.parent / "autosave" / "A_autosave.ggc")
        self.assertEqual(a.backups, a.project.parent / "backups")

    def test_autosave_recovery_is_only_detected_for_matching_project(self):
        project_a = self.project("A")
        project_b = self.project("B")
        self.write_project(project_a)
        self.write_project(project_b)
        autosave_a = s.project_paths(project_a).autosave
        s.atomic_write_json(autosave_a, self.payload(name="A-neu"))
        os.utime(project_a, ns=(1_000_000_000, 1_000_000_000))
        os.utime(autosave_a, ns=(2_000_000_000, 2_000_000_000))

        self.assertEqual(s.newer_autosave(project_a), autosave_a)
        self.assertIsNone(s.newer_autosave(project_b))

    def test_save_and_save_as_keep_project_data_local(self):
        source = self.project("Quelle")
        target = self.project("Ziel")
        model = g.GuildModel()
        model.load_payload(self.payload(), source)
        model.save(source, backup=False)
        source_portraits = s.project_paths(source).portraits
        (source_portraits / "history").mkdir(parents=True)
        (source_portraits / "Janos.png").write_bytes(b"portrait")
        (source_portraits / "history" / "m0001.png").write_bytes(b"history")

        copied = s.copy_project_portraits(source, target)
        model.save(target, backup=True)
        model.members[0].note = "neu"
        model.save(target, backup=True)

        self.assertEqual(copied, 2)
        self.assertEqual((target.parent / "portraits" / "Janos.png").read_bytes(), b"portrait")
        self.assertEqual((target.parent / "portraits" / "history" / "m0001.png").read_bytes(), b"history")
        self.assertEqual(model.project_path, target.resolve())
        self.assertTrue((target.parent / "backups" / "Ziel_backup.ggc").is_file())
        self.assertFalse((source.parent / "backups" / "Ziel_backup.ggc").exists())

    def test_no_global_portrait_fallback_in_checker_or_grabber(self):
        with self.assertRaises(ValueError):
            g.shared_portrait_folder()
        with self.assertRaises(RuntimeError):
            p.default_output_dir()
        project = self.project("A")
        self.assertEqual(g.shared_portrait_folder(project), project.parent / "portraits")
        self.assertEqual(p.default_output_dir(project), project.parent / "portraits")
        self.assertNotIn("output_dir", p.load_config())

    def test_grabber_project_parser_and_cli_keep_exact_project(self):
        project = self.project("Bierstuben")
        payload = self.payload()
        payload["members"][0].update({
            "race": "Mensch", "className": "Warrior", "gravestoneCategory": "Menschen",
        })
        self.write_project(project, payload)

        records, _context = p.parse_ggc_characters(project, active_only=False)
        args = p.parse_cli(["--project", str(project), "--session-id", "session-123"])

        self.assertEqual(records[0]["memberId"], "m0001")
        self.assertEqual(records[0]["gravestoneCategory"], "Menschen")
        self.assertEqual(Path(args.project), project)
        self.assertEqual(args.session_id, "session-123")
        self.assertEqual(p.default_output_dir(args.project), project.parent / "portraits")

    def test_member_patch_reads_fresh_and_changes_only_stable_id(self):
        project = self.project("Bierstuben")
        payload = self.payload()
        payload["members"].append({"id": "m0002", "name": "Andere", "note": "unberührt"})
        payload["externalFreshValue"] = "behalten"
        self.write_project(project, payload)

        s.patch_project_member(
            project, "m0001", {"race": "Mensch", "className": "Warrior", "note": "verboten"},
            allowed_fields={"race", "className"},
        )

        stored = json.loads(project.read_text(encoding="utf-8"))
        first, second = stored["members"]
        self.assertEqual((first["race"], first["className"]), ("Mensch", "Warrior"))
        self.assertNotIn("note", first)
        self.assertEqual(second["note"], "unberührt")
        self.assertEqual(stored["externalFreshValue"], "behalten")
        self.assertTrue((project.parent / "backups" / "Bierstuben_backup.ggc").is_file())

    def test_graveyard_fields_can_be_patched_without_replacing_project(self):
        project = self.project("Bierstuben")
        self.write_project(project)
        updates = {
            "lifeStatus": "dead", "deathDate": "2026-09-15",
            "graveTemplateId": "grave-0001", "portraitOffsetX": 0.1,
            "portraitOffsetY": -0.2, "portraitZoom": 1.15,
            "textOffsetX": 0.05, "textOffsetY": 0.08, "textScale": 0.9,
        }
        s.patch_project_member(project, "m0001", updates, allowed_fields=updates)
        stored = json.loads(project.read_text(encoding="utf-8"))["members"][0]
        self.assertEqual({key: stored[key] for key in updates}, updates)


def main() -> int:
    global g, p, s
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.repo_root.resolve()
    s = load_module("ggc_project_storage_tests_storage", root / "app" / "project_storage.py")
    g = load_module("ggc_project_storage_tests_checker", root / "app" / "GuildGearChecker.py")
    p = load_module("ggc_project_storage_tests_grabber", root / "app" / "GuildPortraitGrabber.py")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProjectStorageTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
