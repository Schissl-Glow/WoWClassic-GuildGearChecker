"""GUI-unabhängige Auflösung technischer Raidpunkte-Belohnungen."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


RANK_MATERIALS = ("Holz", "Eisen", "Bronze", "Silber", "Gold", "Platin", "Diamant")
RANK_ASSET_IDS = tuple(
    f"{material}_{stage}"
    for material in RANK_MATERIALS
    for stage in range(1, 6)
)
# Compatibility name for the existing reward-assignment API. The old honor_*
# assets are no longer part of the productive character progression.
BADGE_ASSET_IDS = RANK_ASSET_IDS
FRAME_ASSET_IDS = tuple(f"frame_{index:02d}" for index in range(1, 8))


@dataclass(frozen=True)
class FrameOpeningRect:
    """Transparente Innenöffnung eines Portraitrahmens in Quellpixeln."""

    x: int
    y: int
    width: int
    height: int


# Einmalig aus dem Alpha-Kanal der finalen PNGs bestimmt. Die Öffnung ist die
# zentrale transparente Komponente, nicht die zum Bildrand verbundene Fläche.
FRAME_OPENING_RECTS: Mapping[str, FrameOpeningRect] = {
    "frame_01": FrameOpeningRect(138, 192, 667, 1297),
    "frame_02": FrameOpeningRect(172, 228, 598, 1174),
    "frame_03": FrameOpeningRect(158, 199, 624, 1237),
    "frame_04": FrameOpeningRect(149, 177, 650, 1286),
    "frame_05": FrameOpeningRect(143, 175, 662, 1281),
    "frame_06": FrameOpeningRect(142, 195, 655, 1256),
    "frame_07": FrameOpeningRect(160, 239, 621, 1162),
}


@dataclass(frozen=True)
class RewardAsset:
    """Ein unveränderliches Asset mit seiner später konfigurierbaren Schwelle."""

    asset_id: str
    path: Path
    threshold: int


@dataclass(frozen=True)
class RewardThresholds:
    """Zentrale Schwellenkonfiguration für die unveränderte Resolver-Logik."""

    badge_thresholds: Mapping[str, int] = field(default_factory=dict)
    frame_thresholds: Mapping[str, int] = field(default_factory=dict)


def _thresholds_for_steps(badge_step: int, frame_step: int) -> RewardThresholds:
    return RewardThresholds(
        badge_thresholds={
            asset_id: (index + 1) * badge_step
            for index, asset_id in enumerate(BADGE_ASSET_IDS)
        },
        frame_thresholds={
            asset_id: (index + 1) * frame_step
            for index, asset_id in enumerate(FRAME_ASSET_IDS)
        },
    )


PRODUCTION_REWARD_THRESHOLDS = RewardThresholds(
    badge_thresholds={
        asset_id: (index + 1) * 80
        for index, asset_id in enumerate(RANK_ASSET_IDS)
    },
    frame_thresholds={
        "frame_01": 250,
        "frame_02": 500,
        "frame_03": 750,
        "frame_04": 1500,
        "frame_05": 2000,
        "frame_06": 3000,
        "frame_07": 5000,
    },
)
TEST_REWARD_THRESHOLDS = _thresholds_for_steps(badge_step=10, frame_step=20)

# Eternal-DKP nutzt dieselben 35 Rang-Symbole, aber eine eigene Progression:
# eine Rangstufe je 100 DKP. Die Rahmen bleiben davon unabhängig.
ETERNAL_DKP_REWARD_THRESHOLDS = RewardThresholds(
    badge_thresholds={
        asset_id: (index + 1) * 100
        for index, asset_id in enumerate(RANK_ASSET_IDS)
    },
    frame_thresholds={
        "frame_01": 500,
        "frame_02": 1000,
        "frame_03": 1750,
        "frame_04": 2500,
        "frame_05": 3500,
        "frame_06": 5000,
        "frame_07": 7000,
    },
)

# Niedrige Testschwellen bleiben ausschließlich für gezielte Tests verfügbar
# und sind niemals das produktive Standardprofil.
ACTIVE_REWARD_PROFILE = "production"


def active_reward_thresholds() -> RewardThresholds:
    if ACTIVE_REWARD_PROFILE == "test":
        return TEST_REWARD_THRESHOLDS
    return PRODUCTION_REWARD_THRESHOLDS


def eternal_dkp_reward_thresholds() -> RewardThresholds:
    """Return the fixed production thresholds for Eternal-DKP frames."""
    return ETERNAL_DKP_REWARD_THRESHOLDS


@dataclass(frozen=True)
class RewardAssignments:
    """Read-only Snapshot, abgeleitet aus der bereits bestehenden Punkteprojektion."""

    character_badges: Mapping[str, RewardAsset] = field(default_factory=dict)
    main_frames: Mapping[str, RewardAsset] = field(default_factory=dict)

    def badge_for_member(self, member_id: str) -> RewardAsset | None:
        return self.character_badges.get(member_id)

    def frame_for_main(self, member_id: str) -> RewardAsset | None:
        return self.main_frames.get(member_id)


class RewardRegistry:
    """Datei-Registry ohne fachliche Schwellenwerte oder Punkteberechnung."""

    def __init__(self, asset_root: Path | None = None, rank_root: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "assets"
        self.asset_root = asset_root or base / "rewards"
        self.rank_root = rank_root or base / "ranks"
        self._path_cache: dict[tuple[str, str, str], Path | None] = {}

    def _cached_file(self, key: tuple[str, str, str], path: Path) -> Path | None:
        if key not in self._path_cache:
            self._path_cache[key] = path if path.is_file() else None
        return self._path_cache[key]

    def rank_path(self, asset_id: str, size: int = 256) -> Path | None:
        if asset_id not in RANK_ASSET_IDS:
            return None
        directory = "master" if size == 256 else str(size)
        if directory not in {"master", "48", "96"}:
            return None
        path = self.rank_root / directory / f"{asset_id}.png"
        return self._cached_file(("rank", directory, asset_id), path)

    def badge_path(self, asset_id: str) -> Path | None:
        """Return the standard 48 px rank asset used by compact UI surfaces."""
        return self.rank_path(asset_id, 48)

    def frame_path(self, asset_id: str) -> Path | None:
        return self._asset_path("portrait_frames", asset_id, FRAME_ASSET_IDS)

    def frame_opening(self, asset_id: str) -> FrameOpeningRect | None:
        return FRAME_OPENING_RECTS.get(asset_id)

    def _asset_path(self, directory: str, asset_id: str, valid_ids: tuple[str, ...]) -> Path | None:
        if asset_id not in valid_ids:
            return None
        path = self.asset_root / directory / f"{asset_id}.png"
        return self._cached_file(("asset", directory, asset_id), path)

    def resolve_badge(self, points: int, thresholds: Mapping[str, int]) -> RewardAsset | None:
        return self._resolve(points, thresholds, self.badge_path)

    def resolve_frame(self, points: int, thresholds: Mapping[str, int]) -> RewardAsset | None:
        return self._resolve(points, thresholds, self.frame_path)

    @staticmethod
    def _valid_threshold(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

    def _resolve(self, points: int, thresholds: Mapping[str, int], path_for_id) -> RewardAsset | None:
        candidates: list[RewardAsset] = []
        for asset_id, raw_threshold in thresholds.items():
            threshold = self._valid_threshold(raw_threshold)
            path = path_for_id(asset_id)
            if threshold is not None and path is not None and points >= threshold:
                candidates.append(RewardAsset(asset_id, path, threshold))
        return max(candidates, key=lambda asset: (asset.threshold, asset.asset_id), default=None)


def build_reward_assignments(
    *,
    enabled: bool,
    character_points: Mapping[str, int],
    player_points: Mapping[str, int],
    active_main_ids: Mapping[str, str],
    registry: RewardRegistry,
    thresholds: RewardThresholds,
) -> RewardAssignments:
    """Leitet Auszeichnungen aus Summen ab, ohne Raidpunkte neu zu berechnen."""
    if not enabled:
        return RewardAssignments()
    character_badges = {
        member_id: badge
        for member_id, points in character_points.items()
        if (badge := registry.resolve_badge(points, thresholds.badge_thresholds)) is not None
    }
    main_frames = {
        main_id: frame
        for player_id, main_id in active_main_ids.items()
        if (frame := registry.resolve_frame(
            player_points.get(player_id, 0), thresholds.frame_thresholds,
        )) is not None
    }
    return RewardAssignments(character_badges, main_frames)
