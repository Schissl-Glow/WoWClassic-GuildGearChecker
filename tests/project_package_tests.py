# -*- coding: utf-8 -*-
"""Focused tests for the portable project-with-portraits ZIP export."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile


g = None


class ProjectPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-project-package-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.portraits = self.root / "portraits"
        self.portraits.mkdir()
        self.model = g.GuildModel()
        self.model.members = []
        self.model.players = []

    def member(self, member_id: str, name: str, status: str = "active"):
        member = g.Member(id=member_id, name=name, lifeStatus=status)
        self.model.members.append(member)
        return member

    def write(self, relative: str, data: bytes) -> Path:
        path = self.portraits / Path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def export(self, name: str = "package.zip"):
        target = self.root / name
        summary = g.create_project_package(self.model, target, self.portraits)
        return target, summary

    def read_package(self, target: Path):
        with zipfile.ZipFile(target, "r") as archive:
            return archive.namelist(), {
                name: archive.read(name) for name in archive.namelist()
            }

    def assert_no_temp(self, target: Path):
        self.assertEqual(list(target.parent.glob(f".{target.name}.*.tmp")), [])

    def test_current_unsaved_project_and_manifest_are_valid(self):
        member = self.member("m0001", "Äon")
        member.note = "noch nicht normal gespeichert"
        self.model.players = [g.Player("p0001", "Müller")]
        member.playerId = "p0001"
        self.model.project_path = None
        self.model.dirty = True
        self.write("m0001.png", b"portrait-aeon")
        before_members = copy.deepcopy(self.model.members)
        before_players = copy.deepcopy(self.model.players)

        target, summary = self.export()
        names, content = self.read_package(target)
        project = json.loads(content["project.ggc"].decode("utf-8"))
        manifest = json.loads(content["manifest.json"].decode("utf-8"))

        self.assertEqual(names, ["project.ggc", "manifest.json", "portraits/m0001.png"])
        self.assertEqual(project["format"], g.PROJECT_FORMAT)
        self.assertEqual(project["formatVersion"], g.PROJECT_FORMAT_VERSION)
        self.assertEqual(project["members"][0]["note"], "noch nicht normal gespeichert")
        self.assertEqual(project["players"][0]["playerName"], "Müller")
        self.assertEqual(manifest["packageFormatVersion"], 1)
        self.assertEqual(manifest["projectFile"], "project.ggc")
        self.assertEqual(manifest["projectFormatVersion"], g.PROJECT_FORMAT_VERSION)
        self.assertEqual(manifest["suiteVersion"], g.APP_VERSION)
        datetime.fromisoformat(manifest["createdAt"])
        self.assertEqual(manifest["portraitCount"], 1)
        self.assertEqual(summary.portrait_count, 1)
        self.assertIsNone(self.model.project_path)
        self.assertTrue(self.model.dirty)
        self.assertEqual(self.model.members, before_members)
        self.assertEqual(self.model.players, before_players)

    def test_dirty_and_project_path_are_unchanged_for_both_states(self):
        project_path = self.root / "Original.ggc"
        for dirty in (False, True):
            with self.subTest(dirty=dirty):
                self.model.project_path = project_path
                self.model.dirty = dirty
                target = self.root / f"state-{dirty}.zip"
                g.create_project_package(self.model, target, self.portraits)
                self.assertEqual(self.model.project_path, project_path)
                self.assertEqual(self.model.dirty, dirty)

    def test_existing_project_file_is_not_copied_over_current_model(self):
        member = self.member("m0001", "Janos")
        member.note = "current in-memory value"
        project_path = self.root / "SavedProject.ggc"
        project_path.write_text('{"stale": true}', encoding="utf-8")
        self.model.project_path = project_path

        target, _summary = self.export()
        _names, content = self.read_package(target)
        project = json.loads(content["project.ggc"].decode("utf-8"))

        self.assertNotIn("stale", project)
        self.assertEqual(project["members"][0]["note"], "current in-memory value")
        self.assertEqual(project_path.read_text(encoding="utf-8"), '{"stale": true}')

    def test_only_project_portraits_and_dead_history_are_included(self):
        self.member("m0042", "Janos", "dead")
        self.member("m0113", "Janos", "active")
        self.member("m0087", "Janos", "dead")
        self.member("m0200", "Schneeflocke", "active")
        self.write("Janos.png", b"janos")
        self.write("Schneeflocke.png", b"snow")
        self.write("AndererChar.png", b"foreign")
        self.write("history/m0042.png", b"old-one")
        self.write("history/m0042.missing", b"")
        self.write("history/m0087.png", b"old-two")
        self.write("history/m9999.png", b"foreign-history")
        self.write("history/m9999.missing", b"foreign-marker")

        target, summary = self.export()
        names, _content = self.read_package(target)

        self.assertEqual(names, [
            "project.ggc", "manifest.json",
            "portraits/m0042.png", "portraits/m0087.png", "portraits/m0200.png",
        ])
        self.assertEqual(summary.portrait_count, 3)
        self.assertEqual(summary.historical_portrait_count, 0)
        self.assertEqual(summary.missing_marker_count, 0)

    def test_both_history_png_and_marker_are_exported_without_repair(self):
        self.member("m0042", "Janos", "dead")
        png = self.write("history/m0042.png", b"history")
        marker = self.write("history/m0042.missing", b"marker")
        target, _summary = self.export()
        names, _content = self.read_package(target)

        self.assertIn("portraits/m0042.png", names)
        self.assertFalse(png.exists())
        self.assertFalse(marker.exists())

    def test_reanimated_member_keeps_historical_files_in_portable_package(self):
        member = self.member("m0042", "Janos", "active")
        member.deathDate = "2026-09-12"
        member.graveTemplateId = "grave-0001"
        self.write("Janos.png", b"current")
        self.write("history/m0042.png", b"historical")
        self.write("history/m0042.missing", b"")

        target, summary = self.export()
        names, _content = self.read_package(target)

        self.assertIn("portraits/m0042.png", names)
        self.assertEqual(summary.historical_portrait_count, 0)
        self.assertEqual(summary.missing_marker_count, 0)

    def test_missing_portraits_are_nonfatal_and_no_fake_files_are_created(self):
        self.member("m0001", "OhneBild", "active")
        self.member("m0002", "OhneHistorie", "dead")

        target, summary = self.export()
        names, content = self.read_package(target)

        self.assertEqual(names, ["project.ggc", "manifest.json"])
        self.assertEqual(summary.missing_portrait_count, 2)
        self.assertEqual(summary.historical_portrait_count, 0)
        self.assertEqual(summary.missing_marker_count, 0)
        self.assertEqual(json.loads(content["manifest.json"])["missingPortraitCount"], 2)
        self.assertFalse((self.portraits / "OhneBild.png").exists())
        self.assertFalse((self.portraits / "history" / "m0002.png").exists())

    def test_disappearing_planned_file_warns_and_export_continues(self):
        self.member("m0001", "Janos")
        self.write("m0001.png", b"portrait")
        original_read = g._read_project_package_file

        def disappear(item):
            if item.archive_name == "portraits/m0001.png":
                raise FileNotFoundError(item.source)
            return original_read(item)

        with patch.object(g, "_read_project_package_file", side_effect=disappear):
            target, summary = self.export()

        names, _content = self.read_package(target)
        self.assertEqual(names, ["project.ggc", "manifest.json"])
        self.assertEqual(summary.portrait_count, 0)
        self.assertEqual(summary.missing_portrait_count, 1)
        self.assertEqual(len(summary.warnings), 1)
        self.assertIn(str(self.portraits / "m0001.png"), summary.warnings[0])

    def test_paths_are_safe_unique_unicode_and_deterministic(self):
        for number, name in enumerate(("Søre", "Éowyn", "Müller", "A:B", "A?B"), 1):
            member = self.member(f"m{number:04d}", name)
            self.write(f"{member.id}.png", name.encode("utf-8"))

        first, first_summary = self.export("first.zip")
        second, second_summary = self.export("second.zip")
        first_names, _content = self.read_package(first)

        self.assertEqual(first_summary.entries, second_summary.entries)
        self.assertEqual(first_names, list(first_summary.entries))
        self.assertEqual(len(first_names), len(set(first_names)))
        self.assertIn("portraits/m0001.png", first_names)
        self.assertIn("portraits/m0003.png", first_names)
        self.assertIn("portraits/m0004.png", first_names)
        for name in first_names:
            path = PurePosixPath(name)
            self.assertFalse(path.is_absolute())
            self.assertNotIn("\\", name)
            self.assertNotIn(":", name)
            self.assertNotIn("..", path.parts)

    def test_original_files_and_unrelated_data_stay_unchanged_and_excluded(self):
        self.member("m0001", "Janos")
        portrait = self.write("m0001.png", b"original-portrait")
        unrelated = {
            self.root / "data" / "logs" / "run.log": b"log",
            self.root / "data" / "backups" / "old.ggc": b"backup",
            self.root / "data" / "runtime" / "state.json": b"runtime",
            self.root / "data" / "browser_profiles" / "profile": b"profile",
            self.root / "config" / "suite_settings.json": b"settings",
            self.root / "assets" / "font.ttf": b"font",
            self.root / "tests" / "test.py": b"test",
            self.root / "START.bat": b"bat",
        }
        for path, data in unrelated.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        before = {path: path.read_bytes() for path in (portrait, *unrelated)}

        target, _summary = self.export()
        names, _content = self.read_package(target)

        self.assertEqual(names, ["project.ggc", "manifest.json", "portraits/m0001.png"])
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_serializer_and_manifest_failures_leave_no_target_or_temp(self):
        for helper, stage in (("_project_package_project_bytes", "project"),
                              ("_project_package_manifest_bytes", "manifest")):
            with self.subTest(stage=stage):
                target = self.root / f"{stage}.zip"
                with patch.object(g, helper, side_effect=g.ProjectPackageError(stage, "boom")):
                    with self.assertRaises(g.ProjectPackageError) as raised:
                        g.create_project_package(self.model, target, self.portraits)
                self.assertEqual(raised.exception.stage, stage)
                self.assertFalse(target.exists())
                self.assert_no_temp(target)

    def test_zip_write_and_integrity_failures_leave_no_target_or_temp(self):
        cases = (
            ("write", patch.object(g.zipfile.ZipFile, "writestr", side_effect=OSError("disk full"))),
            ("integrity", patch.object(g.zipfile.ZipFile, "testzip",
                                       return_value="project.ggc")),
        )
        for label, failure_patch in cases:
            with self.subTest(label=label):
                target = self.root / f"{label}.zip"
                with failure_patch:
                    with self.assertRaises(g.ProjectPackageError) as raised:
                        g.create_project_package(self.model, target, self.portraits)
                self.assertEqual(raised.exception.stage, "zip")
                self.assertFalse(target.exists())
                self.assert_no_temp(target)

    def test_failed_atomic_handoff_keeps_existing_target_intact(self):
        target = self.root / "locked.zip"
        target.write_bytes(b"existing target")
        with patch.object(g.os, "replace", side_effect=PermissionError("locked")):
            with self.assertRaises(g.ProjectPackageError):
                g.create_project_package(self.model, target, self.portraits)
        self.assertEqual(target.read_bytes(), b"existing target")
        self.assert_no_temp(target)

    def test_existing_target_is_atomically_replaced_not_appended(self):
        self.member("m0001", "Janos")
        self.write("m0001.png", b"new")
        target = self.root / "existing.zip"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("obsolete.txt", b"old")

        summary = g.create_project_package(self.model, target, self.portraits)
        names, _content = self.read_package(target)

        self.assertNotIn("obsolete.txt", names)
        self.assertEqual(names, list(summary.entries))
        with zipfile.ZipFile(target, "r") as archive:
            self.assertIsNone(archive.testzip())
        self.assert_no_temp(target)

    def test_dialog_cancel_has_no_side_effect(self):
        self.model.project_path = self.root / "Original.ggc"
        self.model.dirty = True
        view = SimpleNamespace(model=self.model)
        before_files = set(self.root.rglob("*"))

        with patch.object(g.filedialog, "asksaveasfilename", return_value=""), \
             patch.object(g, "create_project_package") as create:
            g.GuildGearCheckerApp.export_project_with_portraits(view)

        create.assert_not_called()
        self.assertEqual(self.model.project_path, self.root / "Original.ggc")
        self.assertTrue(self.model.dirty)
        self.assertEqual(set(self.root.rglob("*")), before_files)

    def test_default_filename_is_safe_and_has_fallback(self):
        stamp = g.today_iso()
        self.assertEqual(
            g.project_package_default_filename(None),
            f"GuildProject_mit_Portraits_{stamp}.zip",
        )
        filename = g.project_package_default_filename(Path('Äon:Team?.ggc'))
        self.assertEqual(filename, f"Äon_Team_mit_Portraits_{stamp}.zip")
        self.assertNotRegex(filename, r'[<>:"/\\|?*]')
        self.assertEqual(
            g.project_package_default_filename(Path("CON.ggc")),
            f"GuildProject_mit_Portraits_{stamp}.zip",
        )

    def test_import_restores_project_portraits_and_history(self):
        self.member("m0001", "Äon")
        self.member("m0002", "Janos", "dead")
        self.write("m0001.png", b"current")
        self.write("history/m0002.png", b"history")
        self.write("history/m0002.missing", b"")
        package, _summary = self.export("portable.zip")
        target = self.root / "restored" / "Bierstuben.ggc"

        summary = g.import_project_package(package, target)

        self.assertEqual(summary.project_path, target.resolve())
        self.assertEqual(summary.portrait_count, 2)
        self.assertEqual(summary.historical_portrait_count, 0)
        self.assertEqual(summary.missing_marker_count, 0)
        self.assertTrue(target.is_file())
        self.assertEqual((target.parent / "portraits" / "m0001.png").read_bytes(), b"current")
        self.assertEqual((target.parent / "portraits" / "m0002.png").read_bytes(), b"history")
        restored = g.GuildModel()
        restored.load(target)
        self.assertEqual([member.name for member in restored.members], ["Äon", "Janos"])

    def test_import_rejects_unsafe_paths_without_partial_project(self):
        package = self.root / "unsafe.zip"
        manifest = {
            "packageFormatVersion": g.PROJECT_PACKAGE_FORMAT_VERSION,
            "projectFile": "project.ggc",
            "portraitCount": 0,
            "historicalPortraitCount": 0,
            "missingMarkerCount": 0,
        }
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("project.ggc", json.dumps({"members": []}))
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("../escape.txt", "bad")
        target = self.root / "unsafe-target" / "Guild.ggc"

        with self.assertRaises(g.ProjectPackageError):
            g.import_project_package(package, target)

        self.assertFalse(target.exists())
        self.assertFalse((self.root / "escape.txt").exists())

    def test_import_never_overwrites_existing_project_or_portraits(self):
        self.member("m0001", "Janos")
        package, _summary = self.export("existing-target.zip")
        target = self.root / "existing" / "Guild.ggc"
        target.parent.mkdir()
        target.write_bytes(b"keep-project")
        portraits = target.parent / "portraits"
        portraits.mkdir()
        (portraits / "keep.png").write_bytes(b"keep-portrait")

        with self.assertRaises(g.ProjectPackageError):
            g.import_project_package(package, target)

        self.assertEqual(target.read_bytes(), b"keep-project")
        self.assertEqual((portraits / "keep.png").read_bytes(), b"keep-portrait")


class IdentityV2PackageTests(unittest.TestCase):
    def setUp(self):
        from app.identity_v2 import IdentityV2Store, Member
        from app.identity_v2_storage import save_new_identity_v2

        directory = tempfile.TemporaryDirectory(prefix="ggc-v2-package-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.project = self.root / "Original.ggc"
        self.store = IdentityV2Store(
            members=[Member("m1", "Sorap", "Mage"),
                     Member("m2", "Sorap", "Mage")],
            pointMode="eternal_dkp",
        )
        save_new_identity_v2(self.store, self.project)
        portraits = self.root / "portraits"
        portraits.mkdir()
        (portraits / "m1.png").write_bytes(b"portrait-one")
        (portraits / "m2.png").write_bytes(b"portrait-two")

    def test_v2_package_roundtrip_keeps_ids_assets_and_original_file(self):
        from app.identity_v2_package import (
            create_v2_project_package, import_v2_project_package,
        )
        from app.identity_v2_storage import load_identity_v2

        before = self.project.read_bytes()
        self.store.members[0].note = "Nur im Paket"
        package = self.root / "v2.zip"
        summary = create_v2_project_package(self.store, self.project, package)
        self.assertEqual(summary.portrait_count, 2)
        with zipfile.ZipFile(package) as archive:
            self.assertEqual(set(archive.namelist()), {
                "project.ggc", "manifest.json", "portraits/m1.png",
                "portraits/m2.png"})
            self.assertEqual(json.loads(archive.read("project.ggc"))["identityFormat"],
                             "identity-v2")
        target = self.root / "imported" / "Restored.ggc"
        imported = import_v2_project_package(package, target)
        self.assertEqual(imported.project_path, target.resolve())
        self.assertEqual(load_identity_v2(target).to_payload(),
                         self.store.to_payload())
        self.assertEqual((target.parent / "portraits" / "m1.png").read_bytes(),
                         b"portrait-one")
        self.assertEqual((target.parent / "portraits" / "m2.png").read_bytes(),
                         b"portrait-two")
        self.assertEqual(self.project.read_bytes(), before)

    def test_v2_import_refuses_existing_target_and_legacy_payload(self):
        from app.GuildGearChecker import ProjectPackageError
        from app.identity_v2_package import (
            create_v2_project_package, import_v2_project_package,
        )

        package = self.root / "v2.zip"
        create_v2_project_package(self.store, self.project, package)
        target = self.root / "existing" / "Target.ggc"
        target.parent.mkdir()
        target.write_bytes(b"keep")
        with self.assertRaises(ProjectPackageError):
            import_v2_project_package(package, target)
        self.assertEqual(target.read_bytes(), b"keep")
        legacy_package = self.root / "legacy-payload.zip"
        with (zipfile.ZipFile(package) as source,
              zipfile.ZipFile(legacy_package, "w") as archive):
            for name in source.namelist():
                archive.writestr(
                    name, json.dumps({"members": []}) if name == "project.ggc"
                    else source.read(name))
        fresh = self.root / "fresh" / "Target.ggc"
        with self.assertRaises(ValueError):
            import_v2_project_package(legacy_package, fresh)
        self.assertFalse(fresh.exists())

    def test_v2_import_rejects_paths_outside_member_portraits(self):
        from app.identity_v2_package import (
            create_v2_project_package, import_v2_project_package,
        )

        package = self.root / "v2.zip"
        create_v2_project_package(self.store, self.project, package)
        with zipfile.ZipFile(package, "a") as archive:
            archive.writestr("portraits/../escape.png", b"escape")
        target = self.root / "unsafe" / "Target.ggc"
        with self.assertRaises(ValueError):
            import_v2_project_package(package, target)
        self.assertFalse(target.exists())
        self.assertFalse((self.root / "escape.png").exists())


def main():
    global g
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    sys.path.insert(0, str(args.repo_root.resolve()))
    module_path = args.repo_root.resolve() / "app" / "GuildGearChecker.py"
    spec = importlib.util.spec_from_file_location("ggc_project_package_target", module_path)
    g = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = g
    spec.loader.exec_module(g)
    suite = unittest.TestSuite((
        unittest.defaultTestLoader.loadTestsFromTestCase(ProjectPackageTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(IdentityV2PackageTests),
    ))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
