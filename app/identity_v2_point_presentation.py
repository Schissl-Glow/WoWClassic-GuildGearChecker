"""One visibility policy for the active V2 project point system."""

from __future__ import annotations

from dataclasses import dataclass

from .identity_v2 import POINT_MODE_ETERNAL, POINT_MODE_RAID, POINT_MODES

_RAID_FIELDS = frozenset({
    "raid_points", "eternal_raid_points", "raid_rank", "player_raid_points",
    "raid_point_history", "raid_point_adjustment",
})
_DKP_FIELDS = frozenset({
    "available_dkp", "eternal_dkp", "dkp_rank",
    "eternal_dkp_character", "eternal_dkp_player",
})


@dataclass(frozen=True)
class ActivePointPresentation:
    mode: str

    def __post_init__(self) -> None:
        if self.mode not in POINT_MODES:
            raise ValueError(f"Ungültiges aktives Punktesystem: {self.mode!r}.")

    def shows(self, key: str) -> bool:
        if key in _RAID_FIELDS:
            return self.mode == POINT_MODE_RAID
        if key in _DKP_FIELDS:
            return self.mode == POINT_MODE_ETERNAL
        return True

    def rank(self, dkp_rank: str | None,
             raid_rank: str | None) -> str | None:
        return dkp_rank if self.mode == POINT_MODE_ETERNAL else raid_rank

    def player_frame_points(
        self, eternal_dkp: int | float | None,
        raid_points: int | float | None,
    ) -> int | float | None:
        return eternal_dkp if self.mode == POINT_MODE_ETERNAL else raid_points
