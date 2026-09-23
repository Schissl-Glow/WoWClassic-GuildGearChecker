# -*- coding: utf-8 -*-
"""Focused tests for stable gravestone manifests, occupancy, migration and text geometry."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


g = None
gt = None
REPO_ROOT = None


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TemplateFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-grave-template-")
        self.root = Path(self.temp.name)
        self.folder = self.root / "assets" / "graveyard"
        self.folder.mkdir(parents=True)
        self.manifest = self.folder / gt.MANIFEST_FILENAME

    def tearDown(self):
        self.temp.cleanup()

    def image(self, filename: str, color: str) -> Path:
        path = self.folder / filename
        mode = "RGB" if path.suffix.casefold() in {".jpg", ".jpeg"} else "RGBA"
        g.Image.new(mode, (64, 80), color).save(path)
        return path

    def generate(self):
        return gt.generate_gravestone_manifest(
            self.folder, self.manifest, generated_at="2026-09-12T12:00:00+02:00",
        )

    def checker_paths(self):
        return patch.multiple(
            g,
            gravestone_template_folder=lambda: self.folder,
            gravestone_manifest_path=lambda: self.manifest,
        )


class ManifestTests(TemplateFixture):
    def test_manifest_generation_has_stable_ids_and_reproducible_hashes(self):
        first = self.image("gravestone_alpha.png", "red")
        second = self.image("gravestone_beta.webp", "blue")
        result = self.generate()
        self.assertEqual(result.template_count, 2)
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(payload["format"], gt.MANIFEST_FORMAT)
        self.assertEqual(
            [item["graveTemplateId"] for item in payload["templates"]],
            ["grave-template-0001", "grave-template-0002"],
        )
        self.assertEqual(payload["templates"][0]["sha256"], gt.sha256_file(first))
        before = self.manifest.read_bytes()
        inventory = gt.load_gravestone_inventory(self.folder, self.manifest, logger=None)
        self.assertEqual(inventory.manifest_status, "ok")
        self.assertEqual(len(inventory.templates), 2)
        self.assertEqual(self.manifest.read_bytes(), before)
        self.generate()
        again = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(
            [(item["graveTemplateId"], item["sha256"]) for item in again["templates"]],
            [(item["graveTemplateId"], item["sha256"]) for item in payload["templates"]],
        )
        self.assertTrue(second.is_file())

    def test_new_corrupt_unsupported_and_duplicate_files_are_classified(self):
        original = self.image("gravestone_001.png", "red")
        self.generate()
        self.image("gravestone_new.jpg", "blue")
        shutil.copy2(original, self.folder / "gravestone_duplicate.png")
        (self.folder / "gravestone_broken.png").write_bytes(b"not an image")
        (self.folder / "gravestone_note.txt").write_text("ignored", encoding="utf-8")
        inventory = gt.load_gravestone_inventory(self.folder, self.manifest, logger=None)
        self.assertEqual([path.name for path in inventory.unregistered], ["gravestone_new.jpg"])
        self.assertEqual([path.name for path in inventory.duplicate_files], ["gravestone_duplicate.png"])
        self.assertTrue(any("Beschädigte" in issue for issue in inventory.issues))
        self.assertFalse(any("note.txt" in issue for issue in inventory.issues))
        self.assertEqual(len(inventory.templates), 1)

    def test_rename_is_matched_by_hash_without_manifest_rewrite(self):
        old = self.image("gravestone_old.png", "green")
        self.generate()
        before = self.manifest.read_bytes()
        renamed = old.with_name("gravestone_renamed.png")
        old.rename(renamed)
        inventory = gt.load_gravestone_inventory(self.folder, self.manifest, logger=None)
        self.assertEqual(len(inventory.templates), 1)
        self.assertEqual(inventory.templates[0].state, "renamed")
        self.assertEqual(inventory.templates[0].path.name, renamed.name)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_changed_and_missing_known_files_are_not_accepted(self):
        changed = self.image("gravestone_changed.png", "red")
        missing = self.image("gravestone_missing.png", "blue")
        self.generate()
        ids = {
            item["filename"]: item["graveTemplateId"]
            for item in json.loads(self.manifest.read_text(encoding="utf-8"))["templates"]
        }
        self.image(changed.name, "yellow")
        missing.unlink()
        inventory = gt.load_gravestone_inventory(self.folder, self.manifest, logger=None)
        self.assertIn(ids[changed.name], inventory.changed_template_ids)
        self.assertIn(ids[missing.name], inventory.missing_template_ids)
        self.assertEqual(inventory.templates, ())

    def test_missing_invalid_and_unknown_manifest_entries_are_safe(self):
        self.image("gravestone_001.png", "red")
        missing = gt.load_gravestone_inventory(self.folder, self.manifest, logger=None)
        self.assertEqual(missing.manifest_status, "missing")
        self.assertEqual(len(missing.unregistered), 1)
        self.manifest.write_text("{broken", encoding="utf-8")
        invalid = gt.load_gravestone_inventory(self.folder, self.manifest, logger=None)
        self.assertEqual(invalid.manifest_status, "invalid")
        self.manifest.write_text(json.dumps({
            "format": gt.MANIFEST_FORMAT, "formatVersion": gt.MANIFEST_VERSION,
            "templates": [{"graveTemplateId": "bad/path", "filename": "../bad.png", "sha256": "x"}],
        }), encoding="utf-8")
        unknown = gt.load_gravestone_inventory(self.folder, self.manifest, logger=None)
        self.assertEqual(unknown.templates, ())
        self.assertTrue(any("Ungültiger Manifest-Eintrag" in issue for issue in unknown.issues))

    def test_relative_inventory_survives_project_folder_move(self):
        self.image("gravestone_001.png", "red")
        self.generate()
        destination = self.root / "moved" / "assets" / "graveyard"
        destination.parent.mkdir(parents=True)
        shutil.copytree(self.folder, destination)
        inventory = gt.load_gravestone_inventory(destination, destination / gt.MANIFEST_FILENAME, logger=None)
        self.assertEqual(len(inventory.templates), 1)
        self.assertEqual(inventory.templates[0].path.parent, destination)
        manifest_text = (destination / gt.MANIFEST_FILENAME).read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), manifest_text)


class OccupancyAndMigrationTests(TemplateFixture):
    def setUp(self):
        super().setUp()
        for index, color in enumerate(("red", "green", "blue"), 1):
            self.image(f"gravestone_{index:03d}.png", color)
        self.generate()

    def test_assignments_are_unique_and_exhaustion_is_explicit(self):
        with self.checker_paths():
            model = g.GuildModel()
            model.new_empty()
            dead = []
            for index in range(4):
                member = model.add_member(f"Dead{index}")
                model.set_member_life_status(member.id, "dead")
                dead.append(member)
        assigned = [member.graveTemplateId for member in dead]
        self.assertEqual(len(set(assigned[:3])), 3)
        self.assertTrue(all(assigned[:3]))
        self.assertEqual(assigned[3], "")

    def test_occupied_templates_are_hidden_but_own_template_remains(self):
        with self.checker_paths():
            model = g.GuildModel()
            model.new_empty()
            first = model.add_member("First")
            second = model.add_member("Second")
            model.set_member_life_status(first.id, "dead")
            model.set_member_life_status(second.id, "dead")
            _inventory, first_choices = model.available_gravestone_templates(first.id)
            choice_ids = {item.grave_template_id for item in first_choices}
        self.assertIn(first.graveTemplateId, choice_ids)
        self.assertNotIn(second.graveTemplateId, choice_ids)

    def test_apply_switches_atomically_cancel_draft_has_no_effect(self):
        with self.checker_paths():
            model = g.GuildModel()
            model.new_empty()
            member = model.add_member("First")
            model.set_member_life_status(member.id, "dead")
            original = member.graveTemplateId
            _inventory, choices = model.available_gravestone_templates(member.id)
            replacement = next(item for item in choices if item.grave_template_id != original)
            draft_only = replacement.grave_template_id
            self.assertEqual(member.graveTemplateId, original)
            model.set_gravestone_adjustment(
                member.id, draft_only, .2, -.3, 1.4, .4, -.5, 1.2, "12.09.2025",
            )
            self.assertEqual(member.graveTemplateId, draft_only)
            self.assertNotIn(original, model.occupied_grave_template_ids(member.id))
            other = model.add_member("Other")
            model.set_member_life_status(other.id, "dead")
            with self.assertRaises(ValueError):
                model.set_gravestone_adjustment(
                    member.id, other.graveTemplateId, 0, 0, 1, 0, 0, 1,
                )
            self.assertEqual(member.graveTemplateId, draft_only)

    def test_emergency_reanimation_keeps_template_reserved_and_remove_releases(self):
        with self.checker_paths():
            model = g.GuildModel()
            model.new_empty()
            first = model.add_member("First")
            model.set_member_life_status(first.id, "dead")
            reserved = first.graveTemplateId
            self.assertTrue(reserved)
            with self.assertRaises(ValueError):
                model.set_member_life_status(first.id, "active")
            model.set_member_life_status(
                first.id, "active", allow_dead_reanimation=True,
            )
            self.assertEqual(first.graveTemplateId, reserved)
            self.assertIn(reserved, model.occupied_grave_template_ids())

            second = model.add_member("Second")
            model.set_member_life_status(second.id, "dead")
            self.assertNotEqual(second.graveTemplateId, reserved)
            occupied = second.graveTemplateId
            model.remove_member(second.id)
            self.assertNotIn(occupied, model.occupied_grave_template_ids())
            self.assertIn(reserved, model.occupied_grave_template_ids())

            model.set_member_life_status(first.id, "dead")
            self.assertEqual(first.graveTemplateId, reserved)

    def test_reanimated_template_reservation_survives_project_roundtrip(self):
        with self.checker_paths():
            model = g.GuildModel()
            model.new_empty()
            member = model.add_member("First")
            model.set_member_life_status(member.id, "dead")
            reserved = member.graveTemplateId
            member.deathDate = "2026-09-12"
            model.set_member_life_status(
                member.id, "active", allow_dead_reanimation=True,
            )
            payload = model.to_payload()
            loaded = g.GuildModel()
            loaded.load_payload(payload)
            restored = loaded.find_by_id(member.id)
            self.assertIsNotNone(restored)
            self.assertEqual(restored.lifeStatus, "active")
            self.assertEqual(restored.graveTemplateId, reserved)
            self.assertEqual(restored.deathDate, "2026-09-12")
            self.assertIn(reserved, loaded.occupied_grave_template_ids())

    def test_legacy_filename_migrates_only_when_unambiguous(self):
        with self.checker_paths():
            model = g.GuildModel()
            model.load_payload({"members": [
                {"id": "m1", "name": "One", "lifeStatus": "dead",
                 "gravestoneTemplate": "gravestone_001.png"},
                {"id": "m2", "name": "Duplicate", "lifeStatus": "dead",
                 "gravestoneTemplate": "gravestone_001.png"},
                {"id": "m3", "name": "Missing", "lifeStatus": "dead",
                 "gravestoneTemplate": "gravestone_absent.png"},
            ]})
        self.assertTrue(model.members[0].graveTemplateId)
        self.assertEqual(model.members[1].graveTemplateId, "")
        self.assertEqual(model.members[2].graveTemplateId, "")
        self.assertEqual(model.members[2].gravestoneTemplate, "gravestone_absent.png")


class TextGeometryTests(TemplateFixture):
    def setUp(self):
        super().setUp()
        self.image("gravestone_001.png", "#00000000")
        self.generate()

    def test_text_geometry_normalizes_and_roundtrips_for_multiple_members(self):
        with self.checker_paths():
            model = g.GuildModel()
            model.new_empty()
            first = g.Member("m1", "First", lifeStatus="dead")
            second = g.Member("m2", "Second", lifeStatus="dead")
            model.members = [first, second]
            model.set_gravestone_adjustment("m1", "", 0, 0, 1, 4, -4, 9, "2025-01-02")
            second.textOffsetX, second.textOffsetY, second.textScale = -.25, .5, .8
            payload = model.to_payload()
            loaded = g.GuildModel()
            loaded.load_payload(payload)
        self.assertEqual((loaded.members[0].textOffsetX, loaded.members[0].textOffsetY,
                          loaded.members[0].textScale), (1.0, -1.0, 1.5))
        self.assertEqual((loaded.members[1].textOffsetX, loaded.members[1].textOffsetY,
                          loaded.members[1].textScale), (-.25, .5, .8))

    def test_old_projects_default_text_geometry_without_failure(self):
        with self.checker_paths():
            model = g.GuildModel()
            model.load_payload({"formatVersion": 1, "members": [
                {"id": "m1", "name": "Legacy", "lifeStatus": "dead"},
            ]})
        member = model.members[0]
        self.assertEqual((member.textOffsetX, member.textOffsetY, member.textScale), (0.0, 0.0, 1.0))
        self.assertEqual((member.graveTemplateId, member.gravestoneTemplate), ("", ""))
        self.assertFalse(model.dirty)

    def test_inventory_is_verified_only_once_per_model_session(self):
        with self.checker_paths(), patch.object(
                g, "load_gravestone_inventory", wraps=g.load_gravestone_inventory) as loader:
            model = g.GuildModel()
            first = model.gravestone_inventory()
            second = model.gravestone_inventory()
        self.assertIs(first, second)
        self.assertEqual(loader.call_count, 1)

    def test_text_block_moves_scales_and_never_clips_card(self):
        member = g.Member(
            "m1", "VeryLongÄUnicodeCharacterName", className="Warrior",
            lifeStatus="dead", deathDate="2026-09-12",
            textOffsetX=1, textOffsetY=-1, textScale=1.5,
        )
        layout = g.gravestone_text_layout(member, g.GRAVESTONE_EDITOR_SIZE)
        for line in layout.values():
            left, top, right, bottom = line["bbox"]
            self.assertGreaterEqual(left, 0)
            self.assertGreaterEqual(top, 0)
            self.assertLessEqual(right, g.GRAVESTONE_EDITOR_SIZE[0])
            self.assertLessEqual(bottom, g.GRAVESTONE_EDITOR_SIZE[1])
        reset = g.Member("m2", "Name", lifeStatus="dead")
        default_positions = {
            key: line["position"] for key, line in g.gravestone_text_layout(reset).items()
        }
        moved_positions = {
            key: line["position"] for key, line in g.gravestone_text_layout(member).items()
        }
        self.assertNotEqual(default_positions, moved_positions)
        horizontal_shifts = {
            moved_positions[key][0] - default_positions[key][0]
            for key in default_positions
        }
        self.assertEqual(len(horizontal_shifts), 1)

    def test_text_drag_updates_both_offsets(self):
        x, y = g.shifted_text_offsets(0, 0, 20, -10, g.GRAVESTONE_EDITOR_SIZE)
        self.assertGreater(x, 0)
        self.assertLess(y, 0)


def main() -> int:
    global g, gt, REPO_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    REPO_ROOT = args.repo_root.resolve()
    sys.path.insert(0, str(REPO_ROOT))
    gt = load_module("ggc_gravestone_manifest_tests", REPO_ROOT / "app" / "gravestone_templates.py")
    g = load_module("ggc_gravestone_system_checker", REPO_ROOT / "app" / "GuildGearChecker.py")
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
