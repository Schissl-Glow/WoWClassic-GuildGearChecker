from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.gravestone_categories import (  # noqa: E402
    GRAVESTONE_CATEGORIES,
    load_gravestone_category,
    load_gravestone_portrait_preset,
    save_gravestone_category,
    save_gravestone_portrait_preset,
    update_manifest_gravestone_category,
)
from app.gravestone_templates import (  # noqa: E402
    MANIFEST_FORMAT,
    MANIFEST_VERSION,
    load_gravestone_inventory,
    promote_approved_gravestones,
)
from tools.gravestone_review.gravestone_review_core import (  # noqa: E402
    COMPRESSED_SIZE,
    accept_candidate,
    approve_accepted,
    ensure_workspace,
)


class _PassingValidator:
    def validate(self, _path: Path) -> list:
        return []


def _write_png(path: Path, color: tuple[int, int, int, int], size=(1074, 1464)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", size, color)
    image.paste(
        (255, 255, 255, 0),
        (size[0] // 3, size[1] // 3, size[0] * 2 // 3, size[1] * 2 // 3),
    )
    image.save(path, format="PNG")


def _write_empty_manifest(path: Path) -> None:
    path.write_text(json.dumps({
        "format": MANIFEST_FORMAT,
        "formatVersion": MANIFEST_VERSION,
        "generatedAt": "2026-09-14T00:00:00+02:00",
        "templates": [],
    }), encoding="utf-8")


class GravestoneCategoryTests(unittest.TestCase):
    def test_exact_shared_categories(self) -> None:
        self.assertEqual(GRAVESTONE_CATEGORIES, (
            "Menschen", "Zwerge", "Elfen", "Gnome", "Zauberer", "Spezial",
        ))

    def test_approval_requires_category_and_all_categories_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ggc-category-review-") as td:
            workspace = ensure_workspace(Path(td))
            validator = _PassingValidator()

            missing = workspace.accepted / "gravestone_missing.png"
            _write_png(missing, (20, 30, 40, 255))
            with self.assertRaisesRegex(ValueError, "Grabstein-Kategorie"):
                approve_accepted(missing, workspace, validator)

            for index, category in enumerate(GRAVESTONE_CATEGORIES, start=1):
                candidate = workspace.candidates / f"gravestone_category_{index:02d}.png"
                _write_png(candidate, (20 + index, 40 + index, 60 + index, 255))
                accepted = accept_candidate(
                    candidate, workspace, validator, category=category,
                )
                self.assertEqual(load_gravestone_category(accepted.accepted_path), category)
                released = approve_accepted(accepted.accepted_path, workspace, validator)
                self.assertEqual(released.category, category)
                self.assertEqual(load_gravestone_category(released.master_path), category)
                with Image.open(released.compressed_path) as compressed:
                    self.assertEqual(compressed.size, COMPRESSED_SIZE)
                    self.assertEqual(compressed.mode, "RGBA")
                    self.assertEqual(compressed.getpixel((COMPRESSED_SIZE[0] // 2,
                                                          COMPRESSED_SIZE[1] // 2))[3], 0)
                    self.assertAlmostEqual(
                        compressed.width / compressed.height,
                        1074 / 1464,
                        places=6,
                    )

    def test_promotion_preserves_categories_and_sequential_names(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ggc-category-promotion-") as td:
            root = Path(td)
            productive = root / "graveyard"
            approved = productive / "_approved_new"
            compressed = approved / "compressed"
            productive.mkdir(parents=True)
            compressed.mkdir(parents=True)
            manifest = productive / "gravestones_manifest.json"
            _write_empty_manifest(manifest)
            _write_png(productive / "gravestone_placeholder.png", (5, 5, 5, 255))

            for index, category in enumerate(GRAVESTONE_CATEGORIES, start=1):
                name = f"gravestone_review_{index:02d}.png"
                master = approved / name
                small = compressed / name
                _write_png(master, (50 + index, 70 + index, 90 + index, 255))
                _write_png(small, (50 + index, 70 + index, 90 + index, 255), COMPRESSED_SIZE)
                save_gravestone_category(master, category)

            result = promote_approved_gravestones(
                productive, approved, compressed, manifest,
            )
            self.assertEqual(
                [target for _source, target in result.promoted],
                [f"gravestone_{index:03d}.png" for index in range(1, 7)],
            )
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(
                [entry["category"] for entry in payload["templates"]],
                list(GRAVESTONE_CATEGORIES),
            )
            self.assertFalse(any(
                entry["filename"] == "gravestone_placeholder.png"
                for entry in payload["templates"]
            ))

    def test_legacy_manifest_without_category_is_readable_and_editor_update_persists(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ggc-category-legacy-") as td:
            root = Path(td)
            image = root / "gravestone_001.png"
            _write_png(image, (80, 90, 100, 255), COMPRESSED_SIZE)
            import hashlib
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            manifest = root / "gravestones_manifest.json"
            manifest.write_text(json.dumps({
                "format": MANIFEST_FORMAT,
                "formatVersion": MANIFEST_VERSION,
                "generatedAt": "2026-09-14T00:00:00+02:00",
                "templates": [{
                    "graveTemplateId": "grave-template-0001",
                    "filename": image.name,
                    "sha256": digest,
                }],
            }), encoding="utf-8")

            inventory = load_gravestone_inventory(root, manifest, logger=None)
            self.assertEqual(inventory.manifest_status, "ok")
            self.assertIsNone(inventory.templates[0].category)

            update_manifest_gravestone_category(
                manifest, "grave-template-0001", "Zauberer",
            )
            updated = load_gravestone_inventory(root, manifest, logger=None)
            self.assertEqual(updated.templates[0].category, "Zauberer")

    def test_portrait_preset_roundtrip_is_stable_and_preserves_category(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ggc-preset-roundtrip-") as td:
            image = Path(td) / "gravestone_review.png"
            _write_png(image, (90, 100, 110, 255))
            save_gravestone_category(image, "Elfen")
            self.assertIsNone(load_gravestone_portrait_preset(image))

            save_gravestone_portrait_preset(image, 0.42, -0.31, 1.85)
            self.assertEqual(load_gravestone_category(image), "Elfen")
            self.assertEqual(load_gravestone_portrait_preset(image), (0.42, -0.31, 1.85))

            save_gravestone_category(image, "Gnome")
            self.assertEqual(load_gravestone_portrait_preset(image), (0.42, -0.31, 1.85))

    def test_review_accept_and_approval_preserve_portrait_preset(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ggc-preset-review-") as td:
            workspace = ensure_workspace(Path(td))
            candidate = workspace.candidates / "gravestone_preset.png"
            _write_png(candidate, (91, 101, 111, 255))
            save_gravestone_category(candidate, "Zwerge")
            save_gravestone_portrait_preset(candidate, 0.18, -0.44, 1.65)

            accepted = accept_candidate(candidate, workspace, _PassingValidator())
            self.assertEqual(
                load_gravestone_portrait_preset(accepted.accepted_path),
                (0.18, -0.44, 1.65),
            )
            approved = approve_accepted(accepted.accepted_path, workspace, _PassingValidator())
            self.assertEqual(
                load_gravestone_portrait_preset(approved.master_path),
                (0.18, -0.44, 1.65),
            )

    def test_promotion_carries_portrait_preset_into_manifest_and_inventory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ggc-preset-promotion-") as td:
            root = Path(td)
            productive = root / "graveyard"
            approved = productive / "_approved_new"
            compressed = approved / "compressed"
            productive.mkdir(parents=True)
            compressed.mkdir(parents=True)
            manifest = productive / "gravestones_manifest.json"
            _write_empty_manifest(manifest)

            master = approved / "gravestone_review.png"
            small = compressed / master.name
            _write_png(master, (101, 102, 103, 255))
            _write_png(small, (101, 102, 103, 255), COMPRESSED_SIZE)
            save_gravestone_category(master, "Menschen")
            save_gravestone_portrait_preset(master, -0.25, 0.5, 2.2)

            promote_approved_gravestones(productive, approved, compressed, manifest)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            entry = payload["templates"][0]
            self.assertEqual(entry["defaultPortraitOffsetX"], -0.25)
            self.assertEqual(entry["defaultPortraitOffsetY"], 0.5)
            self.assertEqual(entry["defaultPortraitZoom"], 2.2)

            template = load_gravestone_inventory(productive, manifest, logger=None).templates[0]
            self.assertEqual(template.default_portrait_offset_x, -0.25)
            self.assertEqual(template.default_portrait_offset_y, 0.5)
            self.assertEqual(template.default_portrait_zoom, 2.2)

    def test_legacy_manifest_without_portrait_preset_uses_neutral_defaults(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ggc-preset-legacy-") as td:
            root = Path(td)
            image = root / "gravestone_001.png"
            _write_png(image, (110, 120, 130, 255), COMPRESSED_SIZE)
            import hashlib
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            manifest = root / "gravestones_manifest.json"
            manifest.write_text(json.dumps({
                "format": MANIFEST_FORMAT,
                "formatVersion": MANIFEST_VERSION,
                "generatedAt": "2026-09-14T00:00:00+02:00",
                "templates": [{
                    "graveTemplateId": "grave-template-0001",
                    "filename": image.name,
                    "sha256": digest,
                }],
            }), encoding="utf-8")

            template = load_gravestone_inventory(root, manifest, logger=None).templates[0]
            self.assertEqual(
                (template.default_portrait_offset_x,
                 template.default_portrait_offset_y,
                 template.default_portrait_zoom),
                (0.0, 0.0, 1.0),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
