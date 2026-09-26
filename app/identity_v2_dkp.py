"""Read-only DKP and rank projections for Identity V2."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable

from .identity_v2 import IdentityV2Store
from .rewards import (
    RewardRegistry,
    active_reward_thresholds,
    eternal_dkp_reward_thresholds,
)


def available_dkp_by_member(
    store: IdentityV2Store, balances: Iterable[object],
) -> dict[str, int | float]:
    """Resolve cached CLM balances only through primary or confirmed GUIDs."""
    store.validate()
    result: dict[str, int | float] = defaultdict(int)
    for balance in balances:
        guid = getattr(balance, "clm_guid", None)
        if not isinstance(guid, str) or not guid.strip():
            continue
        # The store has already been validated; avoid validating it per balance.
        member_id = store._resolved_member_id_for_clm_guid(guid)
        if member_id is not None:
            result[member_id] += getattr(balance, "points", 0)
    return dict(result)


class IdentityV2DkpProjection:
    """Cached display values derived from existing CLM, V2, and raid projections."""

    def __init__(
        self,
        store: IdentityV2Store,
        *,
        available_by_member: dict[str, int | float] | None = None,
        raid_points_projection=None,
        refreshed_at: datetime | None = None,
        registry: RewardRegistry | None = None,
    ) -> None:
        store.validate()
        self.store = store
        self.available_by_member = dict(available_by_member or {})
        self.refreshed_at = refreshed_at
        self.raid_points_projection = raid_points_projection
        self.registry = registry or RewardRegistry()
        self.eternal_by_member = store.eternal_dkp_by_member()
        members_by_player: dict[str, list[str]] = defaultdict(list)
        for member in store.members:
            if member.playerId is not None:
                members_by_player[member.playerId].append(member.memberId)
        self.members_by_player = {
            player_id: tuple(member_ids)
            for player_id, member_ids in members_by_player.items()
        }
        self.eternal_by_player = {
            player.playerId: sum(
                self.eternal_by_member.get(member_id, 0)
                for member_id in self.members_by_player.get(player.playerId, ())
            )
            for player in store.players
        }

    def available_for_member(self, member_id: str) -> int | float | None:
        return self.available_by_member.get(member_id)

    def eternal_for_member(self, member_id: str) -> int | float:
        return self.eternal_by_member.get(member_id, 0)

    def eternal_for_player(self, player_id: str) -> int | float:
        return self.eternal_by_player.get(player_id, 0)

    def dkp_rank_asset(self, points: int | float) -> str | None:
        badge = self.registry.resolve_badge(
            points, eternal_dkp_reward_thresholds().badge_thresholds,
        )
        return badge.asset_id if badge is not None else None

    def dkp_rank_for_member(self, member_id: str) -> str | None:
        return self.dkp_rank_asset(self.eternal_for_member(member_id))

    def dkp_rank_for_player(self, player_id: str) -> str | None:
        return self.dkp_rank_asset(self.eternal_for_player(player_id))

    def raid_points_for_member(self, member_id: str) -> int | None:
        if self.raid_points_projection is None:
            return None
        return self.raid_points_projection.character_points(member_id)

    def eternal_raid_points_for_member(self, member_id: str) -> int | None:
        if self.raid_points_projection is None:
            return None
        return self.raid_points_projection.eternal_character_points(member_id)

    def raid_points_for_player(self, player_id: str) -> int | None:
        if self.raid_points_projection is None:
            return None
        return self.raid_points_projection.player_points(player_id)

    def eternal_raid_points_for_player(self, player_id: str) -> int | None:
        if self.raid_points_projection is None:
            return None
        return self.raid_points_projection.eternal_player_points(player_id)

    def raid_rank_asset(self, points: int | None) -> str | None:
        if points is None:
            return None
        badge = self.registry.resolve_badge(
            points, active_reward_thresholds().badge_thresholds,
        )
        return badge.asset_id if badge is not None else None

    def raid_rank_for_member(self, member_id: str) -> str | None:
        return self.raid_rank_asset(self.eternal_raid_points_for_member(member_id))

    def raid_rank_for_player(self, player_id: str) -> str | None:
        return self.raid_rank_asset(self.eternal_raid_points_for_player(player_id))
