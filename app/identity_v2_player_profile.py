"""Read-only Identity V2 values for the existing Qt player profile."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .identity_v2 import IdentityV2Store
from .identity_v2_point_presentation import ActivePointPresentation, POINT_MODE_RAID
from .player_profile import CharacterProfile, PlayerProfileViewModel
from .project_storage import member_portrait_path
from .raid_attendance import AttendanceStatistics


def _empty_stats(identifier: str) -> AttendanceStatistics:
    return AttendanceStatistics(
        player_id=identifier, eligible_raids=0, main_attendances=0,
        twink_attendances=0, total_attendances=0, bench_attendances=0,
        absences=0, attendance_percent=0, twink_percent=0,
        last_attendance=None, current_streak=0, longest_streak=0,
    )


def _counts(subject) -> tuple[int, int]:
    if subject is None:
        return 0, 0
    return (sum(cell.visited_raids for cell in subject.cells),
            sum(cell.status in ("present", "bench") for cell in subject.cells))


def build_v2_player_profile(
    store: IdentityV2Store, player_id: str, *, project_path: Path | None,
    attendance_adapter, dkp_projection, raid_points_projection, registry,
    roster_by_id: Mapping[str, object], selected_member_id: str | None = None,
) -> PlayerProfileViewModel | None:
    """Reuse the 6A/6B/6C snapshots without rebuilding domain state."""
    player = next((item for item in store.players if item.playerId == player_id), None)
    if player is None:
        return None
    presentation = ActivePointPresentation(store.pointMode)
    members = [member for member in store.members if member.playerId == player_id]
    members.sort(key=lambda member: (
        0 if member.memberId == player.mainMemberId else
        1 if member.lifeStatus == "active" else
        2 if member.lifeStatus == "inactive" else 3,
        member.name.casefold(), member.memberId,
    ))
    member_by_id = {member.memberId: member for member in members}
    family_ids = set(member_by_id)
    chosen = (selected_member_id if selected_member_id in member_by_id else
              player.mainMemberId if player.mainMemberId in member_by_id else
              members[0].memberId if members else None)

    raids = attendance_adapter.raids
    player_subjects = {subject.identifier: subject for subject in
                       attendance_adapter.subjects(
                           raids, "player", "day", include_inactive_players=True,
                           identifiers={player_id})}
    day_subjects = {subject.identifier: subject for subject in
                    attendance_adapter.subjects(
                        raids, "character", "day", identifiers=family_ids)}
    raid_subjects = {subject.identifier: subject for subject in
                     attendance_adapter.subjects(
                         raids, "character", "raid", identifiers=family_ids)}
    point_by_raid: dict[tuple[str, str], int] = {}
    if raid_points_projection is not None:
        for entry in raid_points_projection.history:
            if entry.entry_kind == "attendance" and entry.member_id in family_ids:
                key = (entry.member_id, entry.raid_id)
                point_by_raid[key] = point_by_raid.get(key, 0) + entry.total_points
    dkp_by_clm_raid: dict[tuple[str, str], float] = {}
    for record in store.eternalDkpRecords:
        if record.clmRaidId and record.memberId in family_ids:
            key = (record.memberId, record.clmRaidId)
            dkp_by_clm_raid[key] = dkp_by_clm_raid.get(key, 0.0) + record.value
    source_raids = {raid.raidId: raid for raid in store.raids}
    eternal_fallback = (store.eternal_dkp_by_member()
                        if dkp_projection is None else None)

    characters: list[CharacterProfile] = []
    known_available: list[int | float] = []
    for member in members:
        member_id = member.memberId
        day_subject = day_subjects.get(member_id)
        raid_subject = raid_subjects.get(member_id)
        raid_count, raid_days = _counts(day_subject)
        attended = attendance_adapter.by_member.get(member_id, {})
        attended_ids = tuple(sorted(attended, key=lambda raid_id: (
            attendance_adapter.raid_by_id[raid_id].date, raid_id)))
        portrait = (member_portrait_path(project_path, member_id)
                    if project_path is not None else None)
        if portrait is not None and not portrait.is_file():
            portrait = None
        available = (dkp_projection.available_for_member(member_id)
                     if dkp_projection is not None else None)
        if available is not None:
            known_available.append(available)
        dkp_rank = (dkp_projection.dkp_rank_for_member(member_id)
                    if dkp_projection is not None else None)
        raid_rank = (dkp_projection.raid_rank_for_member(member_id)
                     if dkp_projection is not None else None)
        rank = presentation.rank(dkp_rank, raid_rank)
        rows = []
        if raid_subject is not None:
            for raid, cell in zip(raids, raid_subject.cells):
                source = source_raids[raid.id]
                value = None
                if cell.status in ("present", "bench"):
                    value = (point_by_raid.get((member_id, raid.id))
                             if presentation.mode == POINT_MODE_RAID else
                             dkp_by_clm_raid.get((member_id, source.clmRaidId))
                             if source.clmRaidId else None)
                rows.append((raid.date, raid.name, cell.status, value, raid.id))
        rows.sort(key=lambda row: (row[0], row[4]), reverse=True)
        characters.append(CharacterProfile(
            member_id=member_id, player_id=player_id, name=member.name,
            race=member.race, class_name=member.className or "",
            spec=member.spec or "",
            character_type="main" if member_id == player.mainMemberId else "twink",
            life_status=member.lifeStatus, is_active=member.lifeStatus == "active",
            portrait_path=portrait, grave_template_id=member.graveTemplateId or "",
            attendance=day_subject.stat if day_subject is not None else _empty_stats(player_id),
            raid_count=raid_count, attended_raid_ids=attended_ids,
            raid_points=(raid_points_projection.character_points(member_id)
                         if raid_points_projection is not None else None),
            eternal_dkp=(dkp_projection.eternal_for_member(member_id)
                         if dkp_projection is not None else
                         eternal_fallback.get(member_id, 0)),
            current_dkp=available, rank_asset_id=rank,
            raid_role=member.raidRole, gear_status=member.gearStatus,
            raid_status=member.raidStatus, raid_days=raid_days,
            rank_path=registry.rank_path(rank, 96) if rank else None,
            raid_rows=tuple(rows),
            main_periods=tuple((entry.fromDate, entry.toDate)
                               for entry in player.mainHistory
                               if entry.memberId == member_id),
        ))
    player_subject = player_subjects.get(player_id)
    player_raids, player_days = _counts(player_subject)
    main = member_by_id.get(player.mainMemberId)
    main_roster = roster_by_id.get(player.mainMemberId or "")
    player_dkp_rank = (dkp_projection.dkp_rank_for_player(player_id)
                       if dkp_projection is not None else None)
    player_raid_rank = (dkp_projection.raid_rank_for_player(player_id)
                        if dkp_projection is not None else None)
    return PlayerProfileViewModel(
        player_id=player_id,
        player_status="active" if store.player_is_active(player_id) else "inactive",
        profile_name=main.name if main is not None else None,
        dropdown_name=main.name if main is not None else player.displayName,
        membership_start_date=None, current_main_member_id=player.mainMemberId,
        selected_member_id=chosen,
        attendance=(player_subject.stat if player_subject is not None
                    else _empty_stats(player_id)),
        raid_count=player_raids,
        raid_points=(raid_points_projection.player_points(player_id)
                     if raid_points_projection is not None else None),
        eternal_dkp=(dkp_projection.eternal_for_player(player_id)
                     if dkp_projection is not None else
                     sum(character.eternal_dkp for character in characters)),
        current_dkp=sum(known_available) if known_available else None,
        current_streak=(player_subject.stat.current_streak if player_subject else 0),
        longest_streak=(player_subject.stat.longest_streak if player_subject else 0),
        frame_asset_id=(main_roster.frameAssetId if main_roster is not None else None),
        characters=tuple(characters), raid_days=player_days,
        player_rank_asset_id=presentation.rank(player_dkp_rank, player_raid_rank),
    )
