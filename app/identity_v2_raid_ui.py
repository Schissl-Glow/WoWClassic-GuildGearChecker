"""Small Identity V2 bridge for the existing Qt raid dialog and actions."""

from __future__ import annotations

import copy
from dataclasses import replace
from types import SimpleNamespace

from .identity_v2 import Attendance, IdentityV2Store, Raid
from .raid_attendance import (
    RAID_TYPES, new_attendance_id, new_raid_id, normalize_iso_date,
    validate_logs_url,
)


def raid_view(raid: Raid):
    report_url = (next(iter(raid.csvReportUrls), "")
                  or next((source.reportUrl for source in raid.csvSources
                           if source.reportUrl), ""))
    try:
        report_url = validate_logs_url(report_url)
    except ValueError:
        report_url = ""
    return SimpleNamespace(
        id=raid.raidId, date=raid.date, raidType=raid.raidType,
        name=raid.name, status="recorded",
        warcraftLogsUrl=report_url,
    )


class V2RaidDialogModel:
    """Expose only the old dialog's read-only player and bench inputs."""

    def __init__(self, store: IdentityV2Store, raid_id: str | None = None) -> None:
        self.store = store
        self.raid_id = raid_id
        self.players = {player.playerId: player for player in store.players}
        self.members = {member.memberId: member for member in store.members}

    def active_point_mode(self) -> str:
        return self.store.pointMode

    def attendance_for_raid(self, raid_id: str):
        return [SimpleNamespace(
            id=entry.attendanceId, playerId=entry.playerId,
            memberId=entry.memberId, status=entry.status)
            for entry in self.store.attendance if entry.raidId == raid_id]

    def bench_candidates_for_date(self, _date: str, present: set[str]):
        entries = [entry for entry in self.store.attendance
                   if entry.raidId == self.raid_id]
        occupied = {entry.playerId for entry in entries if entry.playerId}
        occupied_members = {entry.memberId for entry in entries}
        result = []
        for player in self.store.players:
            if player.playerId in present:
                continue
            existing = next((entry for entry in entries
                             if entry.playerId == player.playerId
                             and entry.status == "bench"), None)
            member = (self.members.get(existing.memberId) if existing else
                      self.members.get(player.mainMemberId))
            if (member is None or (not existing and
                    (player.playerId in occupied or member.memberId in occupied_members
                     or member.lifeStatus != "active"))):
                continue
            result.append((player, member))
        return sorted(result, key=lambda pair: (
            pair[0].displayName.casefold(), pair[1].memberId))


def _valid_fields(date: str, name: str, url: str, raid_type: str):
    day = normalize_iso_date(date)
    if not name.strip() or raid_type not in RAID_TYPES:
        raise ValueError("Raidname und gültiger Raidtyp sind erforderlich.")
    return day, name.strip(), validate_logs_url(url), raid_type


def _drop_attendance(store: IdentityV2Store, attendance_ids: set[str]) -> None:
    if not attendance_ids:
        return
    removed = {entry.attendanceId: entry for entry in store.attendance
               if entry.attendanceId in attendance_ids}
    store.attendance = [entry for entry in store.attendance
                        if entry.attendanceId not in attendance_ids]
    store.raidPoints.adjustments = {
        key: value for key, value in store.raidPoints.adjustments.items()
        if key not in attendance_ids}
    store.raidPoints.excluded_attendance_ids.difference_update(attendance_ids)
    removed_pairs = {(entry.raidId, entry.memberId) for entry in removed.values()}
    store.raidCreditResolutions = [
        item for item in store.raidCreditResolutions
        if (item.raidId, item.creditedMemberId) not in removed_pairs]


def apply_raid_dialog(
    store: IdentityV2Store, raid_id: str | None,
    values: tuple[str, str, str, str], bench_player_ids: set[str],
) -> tuple[IdentityV2Store, str]:
    """Apply the existing dialog's accepted values to a validated V2 copy."""
    day, name, url, raid_type = _valid_fields(*values)
    changed = copy.deepcopy(store)
    if raid_id is None:
        raid_id = new_raid_id()
        changed.raids.append(Raid(
            raid_id, day, raid_type, name,
            csvReportUrls=(url,) if url else ()))
    else:
        index = next((index for index, raid in enumerate(changed.raids)
                      if raid.raidId == raid_id), None)
        if index is None:
            raise ValueError("Unbekannte Raid-ID.")
        original = changed.raids[index]
        remaining_urls = original.csvReportUrls[1:]
        changed.raids[index] = replace(
            original, date=day, name=name, raidType=raid_type,
            csvReportUrls=((url,) if url else ()) + remaining_urls)
    existing = [entry for entry in changed.attendance if entry.raidId == raid_id]
    remove_ids = {entry.attendanceId for entry in existing
                  if entry.status == "bench" and entry.playerId
                  and entry.playerId not in bench_player_ids}
    _drop_attendance(changed, remove_ids)
    occupied = {entry.playerId for entry in changed.attendance
                if entry.raidId == raid_id and entry.playerId}
    players = {player.playerId: player for player in changed.players}
    members = {member.memberId: member for member in changed.members}
    for player_id in sorted(bench_player_ids - occupied):
        player = players.get(player_id)
        member = members.get(player.mainMemberId) if player else None
        if member is None or member.lifeStatus != "active":
            raise ValueError("Bench benötigt einen aktiven Main desselben Spielers.")
        if any(entry.raidId == raid_id and entry.memberId == member.memberId
               for entry in changed.attendance):
            raise ValueError("Attendance für diesen Member existiert bereits.")
        changed.attendance.append(Attendance(
            new_attendance_id(), raid_id, member.memberId, "main",
            status="bench", playerId=player_id))
    changed.validate()
    return changed, raid_id


def toggle_attendance(store: IdentityV2Store, attendance_id: str) -> IdentityV2Store:
    changed = copy.deepcopy(store)
    for index, entry in enumerate(changed.attendance):
        if entry.attendanceId == attendance_id:
            changed.attendance[index] = replace(
                entry, status="present" if entry.status == "bench" else "bench")
            changed.validate()
            return changed
    raise ValueError("Unbekannte Attendance-ID.")


def reset_raid_attendance(store: IdentityV2Store, raid_id: str) -> IdentityV2Store:
    changed = copy.deepcopy(store)
    ids = {entry.attendanceId for entry in changed.attendance
           if entry.raidId == raid_id}
    _drop_attendance(changed, ids)
    changed.validate()
    return changed


def delete_raid(store: IdentityV2Store, raid_id: str) -> IdentityV2Store:
    changed = reset_raid_attendance(store, raid_id)
    before = len(changed.raids)
    changed.raids = [raid for raid in changed.raids if raid.raidId != raid_id]
    if len(changed.raids) == before:
        raise ValueError("Unbekannte Raid-ID.")
    changed.raidPoints.included_raid_ids.discard(raid_id)
    changed.raidPoints.pending_raid_ids.discard(raid_id)
    changed.validate()
    return changed
