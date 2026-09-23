from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.gravestone_review.gravestone_alpha_editor import AlphaMaskSession, save_alpha_edit_atomic
from app.gravestone_portrait import detect_portrait_opening
from tools.gravestone_review.gravestone_review_core import (
    AssetValidator,
    GeometryConfig,
    OpeningAnalysis,
    opening_transparency_metrics,
)
from tools.gravestone_review.gravestone_review_tool import GraveyardRenderer


class GravestoneReviewAlphaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.geometry = GeometryConfig.load(
            REPO_ROOT / "tools" / "gravestone_review" / "master_geometry.json"
        )

    def test_diagnostics_find_opaque_island_inside_detected_opening(self) -> None:
        size = (160, 200)
        image = Image.new("RGBA", size, (70, 70, 70, 255))
        alpha = image.getchannel("A")
        draw = ImageDraw.Draw(alpha)
        draw.ellipse((35, 35, 125, 145), fill=0)
        draw.ellipse((73, 78, 87, 92), fill=255)
        image.putalpha(alpha)
        component = Image.new("L", size, 0)
        cdraw = ImageDraw.Draw(component)
        cdraw.ellipse((35, 35, 125, 145), fill=255)
        cdraw.ellipse((73, 78, 87, 92), fill=0)
        analysis = OpeningAnalysis(True, (80, 80), component, (35, 35, 126, 146))

        metrics = opening_transparency_metrics(image, analysis)

        self.assertTrue(metrics.found)
        self.assertGreater(metrics.transparent_pixels, 0)
        self.assertGreater(metrics.nontransparent_pixels, 0)
        self.assertNotEqual(metrics.problem_mask.getbbox(), None)

    def test_alpha_session_ellipse_brush_restore_and_undo(self) -> None:
        image = Image.new("RGBA", (120, 160), (80, 80, 80, 255))
        session = AlphaMaskSession(image, (30, 35, 90, 105), (20, 115, 100, 145))
        session.apply_ellipse((25, 30, 95, 110), feather=0)
        self.assertEqual(session.image.getpixel((60, 70))[3], 0)
        session.checkpoint()
        session.brush(60, 70, 12, restore=True, feather=0)
        self.assertEqual(session.image.getpixel((60, 70))[3], 255)
        self.assertTrue(session.undo())
        self.assertEqual(session.image.getpixel((60, 70))[3], 0)
        session.checkpoint()
        session.brush(10, 10, 6, restore=False, feather=0)
        self.assertEqual(session.image.getpixel((10, 10))[3], 0)

    def test_moving_ellipse_closes_old_opening_and_moves_render_target(self) -> None:
        image = Image.new("RGBA", (180, 220), (80, 80, 80, 255))
        alpha = image.getchannel("A")
        ImageDraw.Draw(alpha).ellipse((45, 45, 105, 125), fill=0)
        image.putalpha(alpha)
        session = AlphaMaskSession(image, (45, 45, 105, 125), (25, 150, 155, 195))

        session.move_ellipse(40, 20, feather=0)

        # The former opening must no longer remain transparent, otherwise the
        # review renderer's alpha detector keeps rendering the portrait there.
        self.assertEqual(session.image.getpixel((60, 80))[3], 255)
        self.assertEqual(session.image.getpixel((100, 100))[3], 0)
        detected = detect_portrait_opening(session.image, (45, 45, 105, 125))
        self.assertTrue(detected.adaptive)
        self.assertGreaterEqual(detected.box[0], 80)

    def test_text_safe_area_can_move_resize_and_undo(self) -> None:
        session = AlphaMaskSession(
            Image.new("RGBA", (160, 200), (80, 80, 80, 255)),
            (30, 35, 90, 105), (25, 120, 130, 170),
        )
        session.move_text_safe_area(12, -10)
        self.assertEqual(session.text_safe_area, (37, 110, 142, 160))
        session.set_text_safe_area((40, 100, 150, 180))
        self.assertEqual(session.text_safe_area, (40, 100, 150, 180))
        self.assertTrue(session.undo())
        self.assertEqual(session.text_safe_area, (37, 110, 142, 160))

    def test_outer_border_cleanup_changes_only_border_alpha_and_is_undoable(self) -> None:
        image = Image.new("RGBA", (80, 100), (12, 34, 56, 255))
        session = AlphaMaskSession(image, (20, 20, 60, 70), (10, 75, 70, 95))

        session.clear_outer_border(8)

        self.assertEqual(session.image.getpixel((79, 50)), (12, 34, 56, 0))
        self.assertEqual(session.image.getpixel((40, 50)), (12, 34, 56, 255))
        self.assertTrue(session.undo())
        self.assertEqual(session.image.getpixel((79, 50)), (12, 34, 56, 255))

    def test_validator_accepts_and_analyzes_non_master_canvas_size(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "wide_by_one.png"
            size = (self.geometry.canvas_size[0] + 1, self.geometry.canvas_size[1])
            image = Image.new("RGBA", size, (80, 80, 80, 255))
            alpha = image.getchannel("A")
            ImageDraw.Draw(alpha).ellipse(
                self.geometry.scale_box(self.geometry.portrait_bbox, size), fill=0
            )
            image.putalpha(alpha)
            image.save(path)

            validator = AssetValidator(self.geometry)
            checks = validator.validate(path)

            canvas_check = next(item for item in checks if item.label == "Flexible Canvas-Größe")
            self.assertTrue(canvas_check.ok)
            self.assertFalse(canvas_check.critical)
            self.assertIsNotNone(validator.last_analysis)
            self.assertTrue(validator.last_analysis.found)
            self.assertEqual(validator.last_analysis.mask.size, self.geometry.canvas_size)

    def test_atomic_save_keeps_backup_and_replaces_review_png(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "candidate.png"
            Image.new("RGBA", (20, 20), (1, 2, 3, 255)).save(target)
            original = target.read_bytes()
            edited = Image.new("RGBA", (20, 20), (4, 5, 6, 0))

            backup = save_alpha_edit_atomic(edited, target, root / "logs" / "alpha_backups")

            self.assertTrue(backup.exists())
            self.assertEqual(backup.read_bytes(), original)
            self.assertEqual(Image.open(target).getpixel((10, 10)), (4, 5, 6, 0))

    def test_atomic_save_backup_failure_leaves_original_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "candidate.png"
            Image.new("RGBA", (20, 20), (1, 2, 3, 255)).save(target)
            original = target.read_bytes()
            blocked_backup_dir = root / "blocked"
            blocked_backup_dir.write_text("not a directory", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                save_alpha_edit_atomic(
                    Image.new("RGBA", (20, 20), (4, 5, 6, 0)),
                    target,
                    blocked_backup_dir,
                )

            self.assertEqual(target.read_bytes(), original)
            self.assertFalse(target.with_name(".candidate.alpha-edit.tmp.png").exists())

    def test_atomic_save_replace_failure_leaves_original_and_removes_temporary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "candidate.png"
            Image.new("RGBA", (20, 20), (1, 2, 3, 255)).save(target)
            original = target.read_bytes()
            backup_dir = root / "logs" / "alpha_backups"

            with patch(
                "tools.gravestone_review.gravestone_alpha_editor.os.replace",
                side_effect=OSError("forced replace failure"),
            ):
                with self.assertRaisesRegex(OSError, "forced replace failure"):
                    save_alpha_edit_atomic(
                        Image.new("RGBA", (20, 20), (4, 5, 6, 0)),
                        target,
                        backup_dir,
                    )

            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(len(list(backup_dir.glob("candidate_*.png"))), 1)
            self.assertFalse(target.with_name(".candidate.alpha-edit.tmp.png").exists())

    def test_demo_portrait_pan_and_zoom_change_composite_and_reset_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stone_path = root / "stone.png"
            portrait_path = root / "portrait.png"
            size = self.geometry.canvas_size
            stone = Image.new("RGBA", size, (80, 80, 80, 255))
            alpha = stone.getchannel("A")
            ImageDraw.Draw(alpha).ellipse(self.geometry.portrait_bbox, fill=0)
            stone.putalpha(alpha)
            stone.save(stone_path)
            portrait = Image.new("RGBA", (500, 350), (15, 30, 200, 255))
            ImageDraw.Draw(portrait).rectangle((0, 0, 160, 350), fill=(240, 30, 20, 255))
            portrait.save(portrait_path)
            validator = AssetValidator(self.geometry)
            validator.validate(stone_path)
            renderer = GraveyardRenderer(self.geometry, root, root)
            renderer.set_portrait(portrait_path)

            renderer.set_portrait_transform(0.0, 0.0, 1.0)
            first = renderer.render(
                stone_path, view="Dunkel", composite=True,
                show_portrait_overlay=False, show_text_overlay=False,
                show_diagnostic_overlay=False, name="", class_name="", death_date="",
                analysis=validator.last_analysis,
            )
            renderer.set_portrait_transform(0.8, -0.5, 1.8)
            changed = renderer.render(
                stone_path, view="Dunkel", composite=True,
                show_portrait_overlay=False, show_text_overlay=False,
                show_diagnostic_overlay=False, name="", class_name="", death_date="",
                analysis=validator.last_analysis,
            )
            renderer.set_portrait_transform(0.0, 0.0, 1.0)
            reset = renderer.render(
                stone_path, view="Dunkel", composite=True,
                show_portrait_overlay=False, show_text_overlay=False,
                show_diagnostic_overlay=False, name="", class_name="", death_date="",
                analysis=validator.last_analysis,
            )

            self.assertIsNotNone(
                ImageChops.difference(first.convert("RGB"), changed.convert("RGB")).getbbox()
            )
            self.assertIsNone(
                ImageChops.difference(first.convert("RGB"), reset.convert("RGB")).getbbox()
            )


if __name__ == "__main__":
    unittest.main()
