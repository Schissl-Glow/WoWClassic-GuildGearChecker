"""UI-unabhängige read-only Projektion für das Spielerprofil."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping

try:
    from .project_storage import member_portrait_path
    from .raid_attendance import calculate_statistics, player_is_relevant
except ImportError:
    from project_storage import member_portrait_path  # type: ignore
    from raid_attendance import calculate_statistics, player_is_relevant  # type: ignore


@dataclass(frozen=True)
class CharacterProfile:
    member_id: str
    player_id: str
    name: str
    race: str | None
    class_name: str
    spec: str
    character_type: str
    life_status: str
    is_active: bool
    portrait_path: Path | None
    grave_template_id: str
    attendance: object
    raid_count: int
    attended_raid_ids: tuple[str, ...]
    raid_points: int | None
    eternal_dkp: int | float
    current_dkp: int | float | None
    rank_asset_id: str | None


@dataclass(frozen=True)
class PlayerProfileViewModel:
    player_id: str
    player_status: str
    profile_name: str | None
    dropdown_name: str
    membership_start_date: str | None
    current_main_member_id: str | None
    selected_member_id: str | None
    attendance: object
    raid_count: int
    raid_points: int | None
    eternal_dkp: int | float
    current_dkp: int | float | None
    current_streak: int
    longest_streak: int
    frame_asset_id: str | None
    characters: tuple[CharacterProfile, ...]

    @property
    def selected_character(self) -> CharacterProfile | None:
        return next((
            character for character in self.characters
            if character.member_id == self.selected_member_id
        ), None)

    def with_selected_character(self, member_id: str) -> "PlayerProfileViewModel" | None:
        if not any(character.member_id == member_id for character in self.characters):
            return None
        return replace(self, selected_member_id=member_id)


def active_player_options(model: object) -> tuple[tuple[str, str], ...]:
    """Return one localized-display-neutral option per active player ID."""
    options: list[tuple[str, str]] = []
    for player in getattr(model, "players", ()):
        player_id = str(getattr(player, "playerId", "") or "")
        if not player_id or not model.player_is_active(player_id):
            continue
        main = model.active_main_for_player(player_id)
        label = str(
            getattr(main, "name", "")
            or getattr(player, "playerName", "")
            or player_id
        )
        options.append((label, player_id))
    return tuple(sorted(options, key=lambda item: (item[0].casefold(), item[1])))


def _fallback_member(members: list[object], active_main: object | None) -> object | None:
    if active_main is not None:
        return active_main
    active = sorted(
        (member for member in members if getattr(member, "lifeStatus", "") == "active"),
        key=lambda member: (
            0 if getattr(member, "characterType", "") == "twink" else 1,
            str(getattr(member, "name", "")).casefold(),
            str(getattr(member, "id", "")),
        ),
    )
    if active:
        return active[0]
    historical = sorted(
        members,
        key=lambda member: (
            str(getattr(member, "deathDate", "") or getattr(member, "addedDate", "")),
            str(getattr(member, "addedDate", "")),
            str(getattr(member, "id", "")),
        ),
        reverse=True,
    )
    return historical[0] if historical else None


def _member_order(member: object, current_main_id: str | None) -> tuple:
    member_id = str(getattr(member, "id", ""))
    status = str(getattr(member, "lifeStatus", ""))
    return (
        0 if member_id == current_main_id else 1 if status == "active" else 2 if status == "inactive" else 3,
        str(getattr(member, "name", "")).casefold(),
        member_id,
    )


def _recorded_raids(model: object) -> dict[str, object]:
    return {
        str(getattr(raid, "id", "")): raid
        for raid in getattr(model, "raids", ())
        if getattr(raid, "status", "") == "recorded"
    }


def _attended_raid_ids(
    model: object, *, member_id: str | None = None, player_id: str | None = None,
) -> tuple[str, ...]:
    """Return unique recorded Present/Bench raids by stable identity."""
    raids = _recorded_raids(model)
    ids = {
        str(getattr(entry, "raidId", ""))
        for entry in getattr(model, "raid_attendance", ())
        if getattr(entry, "status", "") in {"present", "bench"}
        and str(getattr(entry, "raidId", "")) in raids
        and (
            getattr(entry, "memberId", "") == member_id if member_id is not None
            else getattr(entry, "playerId", "") == player_id
        )
    }
    return tuple(sorted(
        ids,
        key=lambda raid_id: (
            str(getattr(raids[raid_id], "date", "")), raid_id,
        ),
    ))


def _historical_member_eligible_ids(
    model: object, member: object, attended_raid_ids: Iterable[str],
) -> set[str]:
    """Reconstruct one non-persisted historical membership window."""
    raids = _recorded_raids(model)
    attended = [raids[raid_id] for raid_id in attended_raid_ids if raid_id in raids]
    if not attended:
        return set()
    first_date = min(str(getattr(raid, "date", "")) for raid in attended)
    last_date = max(str(getattr(raid, "date", "")) for raid in attended)
    tracking_start = str(getattr(model, "attendance_tracking_start_date", "") or "")
    start = max(first_date, tracking_start) if tracking_start else first_date
    death_date = str(getattr(member, "deathDate", "") or "")
    end = death_date if death_date and death_date >= start else last_date
    if end < start:
        return set()
    return {
        raid_id for raid_id, raid in raids.items()
        if start <= str(getattr(raid, "date", "")) <= end
    }


def _member_profile_attendance(
    model: object, member: object, attended_raid_ids: tuple[str, ...],
) -> object:
    if getattr(member, "lifeStatus", "") == "active":
        return model.attendance_statistics_for_member(str(getattr(member, "id", "")))
    player = model.find_player_by_id(getattr(member, "playerId", None))
    eligible_ids = _historical_member_eligible_ids(model, member, attended_raid_ids)
    return calculate_statistics(
        str(getattr(member, "playerId", "") or ""),
        model.raids, model.raid_attendance, model.attendance_tracking_start_date,
        getattr(player, "membershipStartDate", None) if player is not None else None,
        getattr(player, "membershipEndDate", None) if player is not None else None,
        member_id=str(getattr(member, "id", "")),
        eligible_raid_ids=eligible_ids,
    )


def _player_profile_attendance(
    model: object, player: object, members: Iterable[object],
) -> object:
    player_id = str(getattr(player, "playerId", ""))
    eligible_ids = {
        str(getattr(raid, "id", ""))
        for raid in getattr(model, "raids", ())
        if player_is_relevant(
            raid, model.attendance_tracking_start_date,
            getattr(player, "membershipStartDate", None),
            getattr(player, "membershipEndDate", None),
        )
    }
    for member in members:
        if getattr(member, "lifeStatus", "") == "active":
            continue
        attended_ids = _attended_raid_ids(
            model, member_id=str(getattr(member, "id", "")),
        )
        eligible_ids.update(
            _historical_member_eligible_ids(model, member, attended_ids)
        )
    return calculate_statistics(
        player_id, model.raids, model.raid_attendance,
        model.attendance_tracking_start_date,
        getattr(player, "membershipStartDate", None),
        getattr(player, "membershipEndDate", None),
        eligible_raid_ids=eligible_ids,
    )


def build_player_profile(
    model: object,
    player_id: str,
    *,
    selected_member_id: str | None = None,
    raid_point_entries: Iterable[object] | None = None,
    current_dkp_by_member_id: Mapping[str, int | float] | None = None,
    reward_assignments: object | None = None,
) -> PlayerProfileViewModel | None:
    """Project existing model/snapshot data without refreshing any source."""
    player = model.find_player_by_id(player_id)
    if player is None or not model.player_is_active(player_id):
        return None

    members = [
        member for member in getattr(model, "members", ())
        if getattr(member, "playerId", None) == player_id
    ]
    active_main = model.active_main_for_player(player_id)
    current_main_id = str(getattr(active_main, "id", "")) or None
    selected = next((
        member for member in members
        if str(getattr(member, "id", "")) == str(selected_member_id or "")
    ), None)
    selected = selected or _fallback_member(members, active_main)
    selected_id = str(getattr(selected, "id", "")) or None

    entries = tuple(raid_point_entries) if raid_point_entries is not None else None
    player_raid_points = (
        sum(int(getattr(entry, "total_points", 0)) for entry in entries
            if getattr(entry, "player_id", "") == player_id)
        if entries is not None else None
    )
    eternal_character_totals = model.eternal_character_totals()
    eternal_player_total = model.eternal_player_totals().get(player_id, (0, 0))[0]
    dkp_values = current_dkp_by_member_id
    available_player_dkp = [
        dkp_values[member.id] for member in members
        if dkp_values is not None and member.id in dkp_values
    ]
    player_dkp = sum(available_player_dkp) if available_player_dkp else None

    player_attended_raid_ids = _attended_raid_ids(model, player_id=player_id)
    player_attendance = _player_profile_attendance(model, player, members)
    characters: list[CharacterProfile] = []
    for member in sorted(members, key=lambda value: _member_order(value, current_main_id)):
        member_id = str(member.id)
        attended_raid_ids = _attended_raid_ids(model, member_id=member_id)
        portrait = None
        if getattr(model, "project_path", None) is not None:
            candidate = member_portrait_path(model.project_path, member_id)
            portrait = candidate if candidate.is_file() else None
        badge = (
            reward_assignments.badge_for_member(member_id)
            if reward_assignments is not None else None
        )
        characters.append(CharacterProfile(
            member_id=member_id,
            player_id=player_id,
            name=str(member.name),
            race=getattr(member, "race", None),
            class_name=str(getattr(member, "className", "")),
            spec=str(getattr(member, "spec", "")),
            character_type=str(getattr(member, "characterType", "")),
            life_status=str(getattr(member, "lifeStatus", "")),
            is_active=getattr(member, "lifeStatus", "") == "active",
            portrait_path=portrait,
            grave_template_id=str(getattr(member, "graveTemplateId", "")),
            attendance=_member_profile_attendance(model, member, attended_raid_ids),
            raid_count=len(attended_raid_ids),
            attended_raid_ids=attended_raid_ids,
            raid_points=(
                sum(int(getattr(entry, "total_points", 0)) for entry in entries
                    if getattr(entry, "member_id", "") == member_id)
                if entries is not None else None
            ),
            eternal_dkp=eternal_character_totals.get(member_id, (0, 0))[0],
            current_dkp=(
                dkp_values.get(member_id) if dkp_values is not None else None
            ),
            rank_asset_id=str(getattr(badge, "asset_id", "")) or None,
        ))

    frame = (
        reward_assignments.frame_for_main(current_main_id)
        if reward_assignments is not None and current_main_id else None
    )
    return PlayerProfileViewModel(
        player_id=player_id,
        player_status="active",
        profile_name=str(getattr(active_main, "name", "")) or None,
        dropdown_name=str(
            getattr(active_main, "name", "")
            or getattr(player, "playerName", "")
            or player_id
        ),
        membership_start_date=getattr(player, "membershipStartDate", None),
        current_main_member_id=current_main_id,
        selected_member_id=selected_id,
        attendance=player_attendance,
        raid_count=len(player_attended_raid_ids),
        raid_points=player_raid_points,
        eternal_dkp=eternal_player_total,
        current_dkp=player_dkp,
        current_streak=int(getattr(player_attendance, "current_streak", 0)),
        longest_streak=int(getattr(player_attendance, "longest_streak", 0)),
        frame_asset_id=str(getattr(frame, "asset_id", "")) or None,
        characters=tuple(characters),
    )
