"""Identity V2 adapter and atomic edits for the shared raid-points engine."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, replace
from typing import Iterable

from .identity_v2 import IdentityV2Store, POINT_MODE_RAID
from .raid_points import (
    RaidPointEntry, RaidPointsError, build_point_history,
)


@dataclass(frozen=True)
class PointRaid:
    id: str
    date: str
    name: str
    raidType: str
    status: str = "recorded"


@dataclass(frozen=True)
class PointAttendance:
    id: str
    raidId: str
    playerId: str
    memberId: str
    attendanceType: str
    playerNameSnapshot: str
    characterNameSnapshot: str
    status: str


def point_source_signature(store: IdentityV2Store) -> tuple:
    """Detect only changes that can affect totals or the point-history display."""
    return (
        tuple((raid.raidId, raid.date, raid.name, raid.raidType)
              for raid in store.raids),
        tuple((entry.attendanceId, entry.raidId, entry.memberId,
               entry.playerId, entry.attendanceType, entry.status)
              for entry in store.attendance),
        tuple((member.memberId, member.name, member.playerId)
              for member in store.members),
        tuple((item.attendance_id, item.value, item.reason)
              for item in store.raidPoints.adjustments.values()),
        tuple((item.adjustment_id, item.member_id, item.value, item.reason)
              for item in store.raidPoints.member_adjustments.values()),
    )


class V2RaidPointProjection:
    """One reproducible snapshot for member and current-owner player totals."""

    def __init__(self, store: IdentityV2Store) -> None:
        if store.pointMode != POINT_MODE_RAID:
            raise RaidPointsError("Raidpunkte sind für dieses Projekt nicht aktiv.")
        store.validate()
        self.source_signature = point_source_signature(store)
        member_by_id = {member.memberId: member for member in store.members}
        player_by_id = {player.playerId: player for player in store.players}
        raids = tuple(PointRaid(
            raid.raidId, raid.date, raid.name or raid.raidType or raid.raidId,
            raid.raidType) for raid in store.raids)
        attendance = tuple(PointAttendance(
            entry.attendanceId, entry.raidId, entry.playerId or "",
            entry.memberId, entry.attendanceType,
            player_by_id[entry.playerId].displayName if entry.playerId else "–",
            member_by_id[entry.memberId].name, entry.status)
            for entry in store.attendance)
        self.raids = raids
        self.attendance = attendance
        state = copy.deepcopy(store.raidPoints)
        state.rebuild_scope(raids)
        try:
            history = build_point_history(state, raids, attendance, rules="v2")
        except RaidPointsError as exc:
            raise RaidPointsError(f"V2-Raidpunkte konnten nicht berechnet werden: {exc}") from exc
        self.history = tuple(replace(
            entry, character_name=member_by_id[entry.member_id].name)
            if entry.entry_kind == "special" else entry for entry in history)
        self.by_member: dict[str, tuple[RaidPointEntry, ...]] = {}
        grouped: dict[str, list[RaidPointEntry]] = {}
        for entry in self.history:
            grouped.setdefault(entry.member_id, []).append(entry)
        self.by_member = {member_id: tuple(entries)
                          for member_id, entries in grouped.items()}
        self.member_totals = {member.memberId: sum(
            entry.total_points for entry in self.by_member.get(member.memberId, ()))
            for member in store.members}
        members_by_player: dict[str, list[str]] = {}
        for member in store.members:
            if member.playerId is not None:
                members_by_player.setdefault(member.playerId, []).append(member.memberId)
        self.members_by_player = {player_id: tuple(ids)
                                  for player_id, ids in members_by_player.items()}
        self.player_totals = {player.playerId: sum(
            self.member_totals[member_id]
            for member_id in self.members_by_player.get(player.playerId, ()))
            for player in store.players}

    def character_points(self, member_id: str) -> int:
        return self.member_totals.get(member_id, 0)

    def player_points(self, player_id: str) -> int:
        return self.player_totals.get(player_id, 0)

    def eternal_character_points(self, member_id: str) -> int:
        return self.character_points(member_id)

    def eternal_player_points(self, player_id: str) -> int:
        return self.player_points(player_id)

    def history_for_member(self, member_id: str) -> tuple[RaidPointEntry, ...]:
        return self.by_member.get(member_id, ())

    def history_for_player(self, player_id: str) -> tuple[RaidPointEntry, ...]:
        member_ids = set(self.members_by_player.get(player_id, ()))
        return tuple(entry for entry in self.history if entry.member_id in member_ids)


class V2PointDialogModel:
    """Small read-only facade for the existing RaidPointAdjustmentDialog."""

    v2_raid_point_rules = True

    def __init__(self, store: IdentityV2Store,
                 projection: V2RaidPointProjection) -> None:
        self.raid_points = store.raidPoints
        self._attendance = projection.attendance

    def attendance_for_raid(self, raid_id: str) -> list[PointAttendance]:
        return [entry for entry in self._attendance if entry.raidId == raid_id]


def apply_v2_raid_point_adjustments(
    store: IdentityV2Store, changes: Iterable[tuple[str, int, str]],
) -> IdentityV2Store:
    """Commit raid-bound manual points on a validated copy, or return a no-op."""
    if store.pointMode != POINT_MODE_RAID:
        raise RaidPointsError("Raidpunkte sind für dieses Projekt nicht aktiv.")
    proposed = tuple(changes)
    if not proposed:
        return store
    store.validate()
    valid_ids = {entry.attendanceId for entry in store.attendance}
    result = copy.deepcopy(store)
    for attendance_id, value, reason in proposed:
        if attendance_id not in valid_ids:
            raise RaidPointsError(f"Unbekannte Attendance-ID: {attendance_id}.")
        result.raidPoints.set_adjustment(attendance_id, value, reason)
    if result.raidPoints.adjustments == store.raidPoints.adjustments:
        return store
    result.validate()
    return result


def apply_v2_member_special_points(
    store: IdentityV2Store, member_id: str, value: int, reason: str,
    adjustment_id: str | None = None,
) -> IdentityV2Store:
    """Add, update or remove one member-owned special-point record atomically."""
    return apply_v2_member_special_edits(
        store, member_id, ((adjustment_id, value, reason),))


def apply_v2_member_special_edits(
    store: IdentityV2Store, member_id: str,
    edits: Iterable[tuple[str | None, int, str]],
) -> IdentityV2Store:
    """Apply one dialog's special-point edits in one copy and validation."""
    if store.pointMode != POINT_MODE_RAID:
        raise RaidPointsError("Raidpunkte sind für dieses Projekt nicht aktiv.")
    proposed = tuple(edits)
    if not proposed:
        return store
    store.validate()
    if member_id not in {member.memberId for member in store.members}:
        raise RaidPointsError(f"Unbekannte memberId: {member_id}.")
    result = copy.deepcopy(store)
    for adjustment_id, value, reason in proposed:
        if value == 0 and adjustment_id is None:
            continue
        point_id = adjustment_id or f"rp_{uuid.uuid4().hex}"
        existing = result.raidPoints.member_adjustments.get(point_id)
        if adjustment_id is not None and existing is None:
            raise RaidPointsError(f"Unbekannte Sonderpunkte-ID: {adjustment_id}.")
        result.raidPoints.set_member_adjustment(point_id, member_id, value, reason)
    if result.raidPoints.member_adjustments == store.raidPoints.member_adjustments:
        return store
    result.validate()
    return result
