"""Gezielte Tests für die kontrollierte Übernahme freigegebener Grabsteine."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

gt = None


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PromotionFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-gravestone-promotion-")
        self.root = Path(self.temp.name)
        self.productive = self.root / "assets" / "graveyard"
        self.approved = self.productive / "_approved_new"
        self.compressed = self.approved / "compressed"
        self.productive.mkdir(parents=True)
        self.compressed.mkdir(parents=True)
        self.manifest = self.productive / gt.MANIFEST_FILENAME

    def tearDown(self):
        self.temp.cleanup()

    def image(self, folder: Path, filename: str, color: str) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / filename
        gt.Image.new("RGBA", (64, 80), color).save(path)
        return path

    def seed_productive(self, names=("gravestone_005.png",)):
        for index, name in enumerate(names, 1):
            self.image(self.productive, name, (index * 20, 20, 20, 255))
        gt.generate_gravestone_manifest(self.productive, self.manifest, generated_at="2026-09-13T10:00:00+02:00")

    def approve(self, filename: str, color: str = "blue", compressed: bool = True,
                category: str = "Menschen"):
        self.image(self.approved, filename, color)
        if filename != "gravestone_placeholder.png":
            (self.approved / f"{filename}.metadata.json").write_text(json.dumps({
                "format": "GuildGearCheckerGravestoneMetadata",
                "formatVersion": 1,
                "category": category,
            }), encoding="utf-8")
        if compressed:
            self.image(self.compressed, filename, color)


class GravestonePromotionTests(PromotionFixture):
    def test_a_currently_processed_approvals_are_idempotently_skipped(self):
        self.seed_productive(("gravestone_063.png", "gravestone_064.png"))
        self.approve("gravestone_006.png", "red")
        self.approve("gravestone_010.png", "green")
        (self.compressed / "gravestone_006.png").write_bytes((self.productive / "gravestone_063.png").read_bytes())
        (self.compressed / "gravestone_010.png").write_bytes((self.productive / "gravestone_064.png").read_bytes())
        result = gt.promote_approved_gravestones(self.productive, self.approved, self.compressed, self.manifest)
        self.assertEqual(result.promoted, ())
        self.assertEqual(set(result.already_processed), {"gravestone_006.png", "gravestone_010.png"})
        self.assertEqual(len(json.loads(self.manifest.read_text(encoding="utf-8"))["templates"]), 2)

    def test_b_new_approval_uses_next_number_and_manifest_entry(self):
        self.seed_productive()
        self.approve("gravestone_099.png")
        result = gt.promote_approved_gravestones(self.productive, self.approved, self.compressed, self.manifest)
        self.assertEqual(result.promoted, (("gravestone_099.png", "gravestone_006.png"),))
        self.assertTrue((self.productive / "gravestone_006.png").is_file())
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["templates"]), 2)
        self.assertEqual(payload["templates"][-1]["filename"], "gravestone_006.png")
        self.assertEqual(payload["templates"][-1]["category"], "Menschen")

    def test_c_existing_target_is_never_overwritten(self):
        self.seed_productive()
        existing = self.image(self.productive, "gravestone_006.png", "yellow")
        before = existing.read_bytes()
        self.approve("gravestone_100.png")
        result = gt.promote_approved_gravestones(self.productive, self.approved, self.compressed, self.manifest)
        self.assertEqual(result.promoted, (("gravestone_100.png", "gravestone_007.png"),))
        self.assertEqual(existing.read_bytes(), before)

    def test_d_placeholder_is_ignored_and_missing_compressed_is_reported(self):
        self.seed_productive()
        self.approve("gravestone_placeholder.png", "black")
        self.approve("gravestone_101.png", "white", compressed=False)
        result = gt.promote_approved_gravestones(self.productive, self.approved, self.compressed, self.manifest, dry_run=True)
        self.assertEqual(result.promoted, ())
        self.assertEqual(result.accepted_originals, 1)
        self.assertEqual(result.compressed_candidates, 0)
        self.assertEqual(result.missing_compressed, ("gravestone_101.png",))
        self.assertFalse((self.productive / "gravestone_placeholder.png").exists())

    def test_e_dry_run_does_not_write_and_f_idempotence_holds_after_promotion(self):
        self.seed_productive()
        self.approve("gravestone_102.png")
        before_manifest = self.manifest.read_bytes()
        dry = gt.promote_approved_gravestones(self.productive, self.approved, self.compressed, self.manifest, dry_run=True)
        self.assertEqual(dry.promoted, (("gravestone_102.png", "gravestone_006.png"),))
        self.assertFalse((self.productive / "gravestone_006.png").exists())
        self.assertEqual(self.manifest.read_bytes(), before_manifest)
        first = gt.promote_approved_gravestones(self.productive, self.approved, self.compressed, self.manifest)
        second = gt.promote_approved_gravestones(self.productive, self.approved, self.compressed, self.manifest)
        self.assertEqual(first.promoted, (("gravestone_102.png", "gravestone_006.png"),))
        self.assertEqual(second.promoted, ())
        self.assertEqual(second.already_processed, ("gravestone_102.png",))

    def test_manifest_replace_failure_rolls_back_new_productive_file(self):
        self.seed_productive()
        self.approve("gravestone_103.png")
        manifest_before = self.manifest.read_bytes()
        real_replace = gt.os.replace

        def replace_with_manifest_failure(source, destination):
            if Path(destination) == self.manifest:
                raise OSError("forced manifest replace failure")
            return real_replace(source, destination)

        with mock.patch.object(gt.os, "replace", side_effect=replace_with_manifest_failure):
            with self.assertRaisesRegex(OSError, "forced manifest replace failure"):
                gt.promote_approved_gravestones(
                    self.productive, self.approved, self.compressed, self.manifest,
                )

        self.assertFalse((self.productive / "gravestone_006.png").exists())
        self.assertEqual(self.manifest.read_bytes(), manifest_before)
        self.assertFalse(self.manifest.with_suffix(".json.tmp").exists())


def main() -> int:
    global gt
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    gt = load_module("ggc_gravestone_promotion", args.repo_root.resolve() / "app" / "gravestone_templates.py")
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(GravestonePromotionTests)
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
