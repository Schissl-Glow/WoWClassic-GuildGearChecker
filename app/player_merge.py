"""Fachliche Planung und konfliktfreie Ausführung von Spieler-Merges."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


class PlayerMergeError(ValueError):
    """Der gewünschte Spieler-Merge ist ungültig."""


@dataclass(frozen=True)
class MergeAttendanceReference:
    attendance_id: str
    player_id: str
    member_id: str
    character_name: str


@dataclass(frozen=True)
class PlayerMergeConflict:
    raid_id: str
    entries: tuple[MergeAttendanceReference, ...]


@dataclass(frozen=True)
class PlayerMergePlan:
    source_player_id: str
    target_player_id: str
    affected_members: int
    affected_attendance: int
    conflicts: tuple[PlayerMergeConflict, ...]

    @property
    def can_apply(self) -> bool:
        return not self.conflicts


class PlayerMergeConflictError(PlayerMergeError):
    def __init__(self, plan: PlayerMergePlan) -> None:
        self.plan = plan
        super().__init__("Der Spieler-Merge benötigt Entscheidungen für historische Raids.")


@dataclass(frozen=True)
class PlayerMergeResult:
    players: tuple[object, ...]
    members: tuple[object, ...]
    attendance: tuple[object, ...]
    plan: PlayerMergePlan
    excluded_attendance_ids: tuple[str, ...] = ()


def _normalized_id(value: object) -> str:
    return str(value or "").strip()


def plan_player_merge(
    source_player_id: str,
    target_player_id: str,
    members: Iterable[object],
    attendance: Iterable[object],
) -> PlayerMergePlan:
    source = _normalized_id(source_player_id)
    target = _normalized_id(target_player_id)
    if not source or not target:
        raise PlayerMergeError("Quell- und Zielspieler benötigen eine playerId.")
    if source == target:
        raise PlayerMergeError("Quell- und Zielspieler müssen verschieden sein.")

    member_records = list(members)
    attendance_records = list(attendance)
    grouped: dict[str, list[object]] = {}
    for entry in attendance_records:
        player_id = _normalized_id(getattr(entry, "playerId", ""))
        if player_id in {source, target}:
            grouped.setdefault(_normalized_id(getattr(entry, "raidId", "")), []).append(entry)

    conflicts = tuple(
        PlayerMergeConflict(
            raid_id=raid_id,
            entries=tuple(
                MergeAttendanceReference(
                    attendance_id=_normalized_id(getattr(entry, "id", "")),
                    player_id=_normalized_id(getattr(entry, "playerId", "")),
                    member_id=_normalized_id(getattr(entry, "memberId", "")),
                    character_name=str(getattr(entry, "characterNameSnapshot", "")),
                )
                for entry in entries
            ),
        )
        for raid_id, entries in sorted(grouped.items())
        if len(entries) > 1
    )
    return PlayerMergePlan(
        source_player_id=source,
        target_player_id=target,
        affected_members=sum(
            _normalized_id(getattr(member, "playerId", "")) == source
            for member in member_records
        ),
        affected_attendance=sum(
            _normalized_id(getattr(entry, "playerId", "")) == source
            for entry in attendance_records
        ),
        conflicts=conflicts,
    )


def apply_player_merge(
    source_player_id: str,
    target_player_id: str,
    players: Sequence[object],
    members: Sequence[object],
    attendance: Sequence[object],
    *,
    conflict_resolutions: Mapping[str, str] | None = None,
) -> PlayerMergeResult:
    """Merge auf Kopien anwenden; Konfliktentscheidungen bleiben nachvollziehbar."""
    plan = plan_player_merge(source_player_id, target_player_id, members, attendance)
    resolutions = dict(conflict_resolutions or {})
    excluded_attendance_ids: list[str] = []
    for conflict in plan.conflicts:
        selected_id = _normalized_id(resolutions.get(conflict.raid_id))
        valid_ids = {entry.attendance_id for entry in conflict.entries}
        if selected_id not in valid_ids:
            raise PlayerMergeConflictError(plan)
        excluded_attendance_ids.extend(sorted(valid_ids - {selected_id}))

    player_ids = {_normalized_id(getattr(player, "playerId", "")) for player in players}
    if plan.source_player_id not in player_ids:
        raise PlayerMergeError("Quellspieler wurde nicht gefunden.")
    if plan.target_player_id not in player_ids:
        raise PlayerMergeError("Zielspieler wurde nicht gefunden.")

    copied_players = tuple(
        copy.copy(player) for player in players
        if _normalized_id(getattr(player, "playerId", "")) != plan.source_player_id
    )
    copied_members = tuple(copy.copy(member) for member in members)
    copied_attendance = tuple(copy.copy(entry) for entry in attendance)
    for member in copied_members:
        if _normalized_id(getattr(member, "playerId", "")) == plan.source_player_id:
            setattr(member, "playerId", plan.target_player_id)
    for entry in copied_attendance:
        if _normalized_id(getattr(entry, "playerId", "")) == plan.source_player_id:
            setattr(entry, "playerId", plan.target_player_id)
    return PlayerMergeResult(
        copied_players, copied_members, copied_attendance, plan,
        tuple(excluded_attendance_ids),
    )
