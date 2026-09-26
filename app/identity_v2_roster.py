"""Read-only Identity V2 values for the existing Qt roster widgets."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .i18n import tr
from .identity_v2 import IdentityV2Store
from .identity_v2_character_rows import character_table_rows
from .project_storage import member_portrait_path
from .rewards import (FrameOpeningRect, RewardRegistry, active_reward_thresholds,
                      eternal_dkp_reward_thresholds)
from .identity_v2_point_presentation import ActivePointPresentation
from .GuildGearChecker import GAME_VERSION, REALM, REGION, build_armory_url


@dataclass(frozen=True)
class V2RosterItem:
    memberId: str
    playerId: str | None
    playerName: str | None
    name: str
    className: str | None
    race: str | None
    spec: str | None
    raidRole: str
    gearStatus: str
    raidStatus: str
    note: str
    lastChecked: str | None
    lastRaid: str | None
    raidCount: int
    matrixRaidCount: int
    raidDays: int
    isMain: bool
    portraitPath: Path | None
    availableDkp: int | float | None
    eternalDkp: int | float
    playerEternalDkp: int | float | None
    dkpRank: str | None
    dkpRankPath: Path | None
    raidPoints: int | None
    eternalRaidPoints: int | None
    playerRaidPoints: int | None
    raidRank: str | None
    raidRankPath: Path | None
    activePointSystem: str
    rankPath: Path | None
    framePath: Path | None
    frameAssetId: str | None
    frameOpening: FrameOpeningRect | None
    raidStartDate: str | None
    primaryGuid: str | None
    legacyGuidCount: int
    armoryUrl: str | None

    @property
    def role(self) -> str:
        return "main" if self.isMain else "twink" if self.playerId else "not_set"

    # The existing V2 table consumes these read-only field names.
    @property
    def member_id(self) -> str:
        return self.memberId

    @property
    def class_name(self) -> str | None:
        return self.className

    @property
    def raid_start_date(self) -> str | None:
        return self.raidStartDate

    @property
    def raid_count(self) -> int:
        return self.raidCount

    @property
    def eternal_dkp(self) -> int | float:
        return self.eternalDkp

    @property
    def primary_guid(self) -> str | None:
        return self.primaryGuid

    @property
    def legacy_guid_count(self) -> int:
        return self.legacyGuidCount


def build_v2_roster_items(
    store: IdentityV2Store,
    project_path: Path | None,
    raid_points_projection,
    dkp_projection,
    registry: RewardRegistry,
    attendance_adapter=None,
) -> tuple[V2RosterItem, ...]:
    """Read existing V2 projections once; never inspect names for identity."""
    store.validate()
    presentation = ActivePointPresentation(store.pointMode)
    members = {member.memberId: member for member in store.members}
    legacy_counts = Counter(store.legacyClmGuidMemberMap.values())
    eternal_totals = (dkp_projection.eternal_by_member if dkp_projection is not None
                      else store.eternal_dkp_by_member())
    thresholds = (eternal_dkp_reward_thresholds()
                  if presentation.shows("dkp_rank") else active_reward_thresholds())
    attendance_counts = {}
    if attendance_adapter is not None:
        attendance_counts = {
            subject.identifier: (
                sum(cell.visited_raids for cell in subject.cells),
                sum(cell.status in ("present", "bench") for cell in subject.cells),
            )
            for subject in attendance_adapter.subjects(
                attendance_adapter.raids, "character", "day")
        }
    result: list[V2RosterItem] = []
    for row in character_table_rows(store):
        if row.lifeStatus != "active":
            continue
        member = members[row.memberId]
        player_points = (
            raid_points_projection.player_points(member.playerId)
            if raid_points_projection is not None and member.playerId else None
        )
        dkp_player_points = (
            dkp_projection.eternal_for_player(member.playerId)
            if dkp_projection is not None and member.playerId else None
        )
        frame_points = presentation.player_frame_points(
            dkp_player_points, player_points)
        frame = (
            registry.resolve_frame(
                frame_points, thresholds.frame_thresholds)
            if row.playerRole == "main" and frame_points is not None else None
        )
        dkp_rank = (dkp_projection.dkp_rank_for_member(row.memberId)
                    if dkp_projection is not None else None)
        raid_rank = (dkp_projection.raid_rank_for_member(row.memberId)
                     if dkp_projection is not None else None)
        active_rank = presentation.rank(dkp_rank, raid_rank)
        matrix_raids, raid_days = attendance_counts.get(row.memberId, (0, 0))
        armory_url = build_armory_url(
            row.name, member.region or REGION,
            member.realm or store.realm or REALM,
            member.gameVersion or GAME_VERSION)
        result.append(V2RosterItem(
            memberId=row.memberId, playerId=member.playerId,
            playerName=row.playerName, name=row.name,
            className=row.className, race=row.race, spec=row.spec,
            raidRole=row.raidRole, gearStatus=row.gearStatus,
            raidStatus=row.raidStatus, note=row.note,
            lastChecked=row.lastChecked, lastRaid=row.lastRaidDate,
            raidCount=row.raidCount, matrixRaidCount=matrix_raids,
            raidDays=raid_days, isMain=row.playerRole == "main",
            portraitPath=(member_portrait_path(project_path, row.memberId)
                          if project_path is not None else None),
            availableDkp=(dkp_projection.available_for_member(row.memberId)
                          if dkp_projection is not None else None),
            eternalDkp=eternal_totals[row.memberId],
            playerEternalDkp=dkp_player_points,
            dkpRank=dkp_rank,
            dkpRankPath=registry.rank_path(dkp_rank, 96) if dkp_rank else None,
            raidPoints=(raid_points_projection.character_points(row.memberId)
                        if raid_points_projection is not None else None),
            eternalRaidPoints=(raid_points_projection.eternal_character_points(row.memberId)
                               if raid_points_projection is not None else None),
            playerRaidPoints=player_points,
            raidRank=raid_rank,
            raidRankPath=registry.rank_path(raid_rank, 96) if raid_rank else None,
            activePointSystem=presentation.mode,
            rankPath=registry.rank_path(active_rank, 96) if active_rank else None,
            framePath=frame.path if frame is not None else None,
            frameAssetId=frame.asset_id if frame is not None else None,
            frameOpening=(registry.frame_opening(frame.asset_id)
                          if frame is not None else None),
            raidStartDate=member.raidStartDate,
            primaryGuid=member.clmGuid,
            legacyGuidCount=legacy_counts[row.memberId],
            armoryUrl=armory_url,
        ))
    return tuple(result)


def filter_sort_v2_roster(
    items: Iterable[V2RosterItem], *, query: str = "", class_name: str | None = None,
    sort_key: str = "name", descending: bool = False,
) -> tuple[V2RosterItem, ...]:
    needle = query.strip().casefold()
    visible = [item for item in items
               if (not class_name or
                   (item.className is None if class_name == "__unknown__"
                    else item.className == class_name))
               and (not needle or any(needle in str(value or "").casefold() for value in (
                   item.name, item.playerName, item.className, item.spec,
                   item.raidRole, tr(f"raid_role.{item.raidRole}"),
                   item.gearStatus, item.raidStatus,
               )))]
    keys = {
        "name": lambda item: item.name.casefold(),
        "class": lambda item: (item.className or "").casefold(),
        "raid_role": lambda item: item.raidRole,
        "gear": lambda item: item.gearStatus.casefold(),
        "raid_rank": lambda item: item.eternalRaidPoints or 0,
        "dkp_rank": lambda item: item.eternalDkp,
    }
    key = keys.get(sort_key, keys["name"])
    visible.sort(key=lambda item: item.memberId)
    visible.sort(key=key, reverse=descending)
    return tuple(visible)
