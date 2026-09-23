from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.rewards import (
    ETERNAL_DKP_REWARD_THRESHOLDS,
    FRAME_ASSET_IDS,
    FRAME_OPENING_RECTS,
    PRODUCTION_REWARD_THRESHOLDS,
    RANK_ASSET_IDS,
    RANK_MATERIALS,
    FrameOpeningRect,
    RewardRegistry,
)


class RankRewardTests(unittest.TestCase):
    def test_rank_ids_cover_seven_materials_with_five_stages(self) -> None:
        self.assertEqual(
            RANK_MATERIALS,
            ("Holz", "Eisen", "Bronze", "Silber", "Gold", "Platin", "Diamant"),
        )
        self.assertEqual(len(RANK_ASSET_IDS), 35)
        self.assertEqual(RANK_ASSET_IDS[0], "Holz_1")
        self.assertEqual(RANK_ASSET_IDS[-1], "Diamant_5")
        self.assertEqual(len(set(RANK_ASSET_IDS)), 35)

    def test_raid_point_thresholds_use_80_point_steps(self) -> None:
        thresholds = PRODUCTION_REWARD_THRESHOLDS.badge_thresholds
        self.assertEqual(thresholds["Holz_1"], 80)
        self.assertEqual(thresholds["Holz_5"], 400)
        self.assertEqual(thresholds["Gold_5"], 2000)
        self.assertEqual(thresholds["Platin_1"], 2080)
        self.assertEqual(thresholds["Diamant_5"], 2800)

    def test_eternal_dkp_thresholds_use_100_point_steps(self) -> None:
        thresholds = ETERNAL_DKP_REWARD_THRESHOLDS.badge_thresholds
        self.assertEqual(thresholds["Holz_1"], 100)
        self.assertEqual(thresholds["Holz_5"], 500)
        self.assertEqual(thresholds["Gold_5"], 2500)
        self.assertEqual(thresholds["Platin_1"], 2600)
        self.assertEqual(thresholds["Diamant_5"], 3500)

    def test_new_frame_openings_match_final_assets(self) -> None:
        self.assertEqual(len(FRAME_ASSET_IDS), 7)
        self.assertEqual(
            FRAME_OPENING_RECTS,
            {
                "frame_01": FrameOpeningRect(138, 192, 667, 1297),
                "frame_02": FrameOpeningRect(172, 228, 598, 1174),
                "frame_03": FrameOpeningRect(158, 199, 624, 1237),
                "frame_04": FrameOpeningRect(149, 177, 650, 1286),
                "frame_05": FrameOpeningRect(143, 175, 662, 1281),
                "frame_06": FrameOpeningRect(142, 195, 655, 1256),
                "frame_07": FrameOpeningRect(160, 239, 621, 1162),
            },
        )

    def test_final_frame_files_have_expected_sizes_and_rgba(self) -> None:
        frame_root = REPO_ROOT / "assets" / "rewards" / "portrait_frames"
        expected_sizes = {
            "frame_01": (941, 1672),
            "frame_02": (941, 1672),
            "frame_03": (941, 1672),
            "frame_04": (948, 1659),
            "frame_05": (948, 1659),
            "frame_06": (941, 1672),
            "frame_07": (941, 1672),
        }
        for asset_id, expected_size in expected_sizes.items():
            path = frame_root / f"{asset_id}.png"
            self.assertTrue(path.is_file(), f"Fehlender Rahmen: {path}")
            with Image.open(path) as image:
                self.assertEqual(image.size, expected_size, asset_id)
                self.assertEqual(image.mode, "RGBA", asset_id)

    def test_registry_uses_only_documented_rank_sizes_and_no_fallback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ggc-ranks-") as temp:
            root = Path(temp)
            for directory in ("master", "48", "96"):
                (root / directory).mkdir(parents=True)
            (root / "48" / "Holz_1.png").write_bytes(b"48")
            (root / "96" / "Holz_1.png").write_bytes(b"96")
            (root / "master" / "Holz_1.png").write_bytes(b"256")

            registry = RewardRegistry(rank_root=root)
            self.assertEqual(registry.badge_path("Holz_1"), root / "48" / "Holz_1.png")
            self.assertEqual(registry.rank_path("Holz_1", 96), root / "96" / "Holz_1.png")
            self.assertEqual(registry.rank_path("Holz_1", 256), root / "master" / "Holz_1.png")
            self.assertIsNone(registry.rank_path("Holz_1", 24))
            self.assertIsNone(registry.rank_path("Diamant_5", 96))
            self.assertIsNone(registry.rank_path("unknown", 48))


if __name__ == "__main__":
    unittest.main()
