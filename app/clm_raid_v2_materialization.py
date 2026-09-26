"""Atomically add reviewed CLM raids and present attendance to a new V2 store."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from typing import Mapping

from .clm_history import local_raid_date
from .clm_raid_v2_analysis import ClmRaidV2Analysis
from .identity_v2 import (
    Attendance, IdentityV2Store, IdentityV2ValidationError, Raid,
)
from .raid_attendance import RAID_TYPES
from .raid_type_detection import detect_raid_type


class ClmRaidMaterializationError(ValueError):
    """A CLM raid cannot be materialized without losing identity evidence."""


@dataclass(frozen=True)
class ClmRaidReviewRow:
    clm_raid_id: str
    date: str
    name: str
    participants: int
    raid_type: str
    status: str


def suggest_clm_raid_type(title: str) -> str:
    """Use the same explicit aliases and title order as CSV and raid points."""
    return detect_raid_type(title) or ""


def review_clm_raids(store: IdentityV2Store, analysis: ClmRaidV2Analysis) -> tuple[ClmRaidReviewRow, ...]:
    existing = {raid.clmRaidId: raid for raid in store.raids if raid.clmRaidId}
    rows = []
    for source in analysis.raids:
        current = existing.get(source.raid_id)
        raid_type = ((detect_raid_type(current.raidType)
                      or suggest_clm_raid_type(source.name)
                      or current.raidType)
                     if current else suggest_clm_raid_type(source.name))
        conflict = current is not None and _clm_attendance_conflict(store, current, source)
        rows.append(ClmRaidReviewRow(
            source.raid_id, local_raid_date(source.start_timestamp) or "",
            source.name, len(source.participants), raid_type,
            "Teilnehmer abweichend" if conflict else
            "Typ fehlt" if current and detect_raid_type(current.raidType) is None else
            "bereits importiert" if current else "neu" if raid_type else "Typ fehlt",
        ))
    return tuple(rows)


def _clm_attendance_conflict(store, raid, source) -> bool:
    ignored = {guid.casefold() for group in store.ignoredClmCharacterGroups
               for guid in group.clmGuids}
    source_guids = {item.guid.casefold() for item in source.participants
                    if item.guid.casefold() not in ignored}
    stored_guids = {item.clmGuid.casefold() for item in store.attendance
                    if item.raidId == raid.raidId and item.clmGuid}
    return source_guids != stored_guids


def clm_raid_attendance_difference(
    store: IdentityV2Store, raid_analysis: ClmRaidV2Analysis, clm_raid_id: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return CLM GUIDs to add and remove for one already imported raid."""
    raid = next((item for item in store.raids if item.clmRaidId == clm_raid_id), None)
    source = next((item for item in raid_analysis.raids
                   if item.raid_id == clm_raid_id), None)
    if raid is None or source is None:
        raise ClmRaidMaterializationError("CLM-Raid für Korrektur nicht gefunden.")
    ignored = {guid.casefold() for group in store.ignoredClmCharacterGroups
               for guid in group.clmGuids}
    source_guids = {item.guid.casefold(): item.guid for item in source.participants
                    if item.guid.casefold() not in ignored}
    stored_guids = {item.clmGuid.casefold(): item.clmGuid
                    for item in store.attendance
                    if item.raidId == raid.raidId and item.clmGuid}
    added = tuple(source_guids[key] for key in sorted(source_guids.keys() - stored_guids.keys()))
    removed = tuple(stored_guids[key] for key in sorted(stored_guids.keys() - source_guids.keys()))
    return added, removed


def correct_clm_raid_attendance(
    store: IdentityV2Store, raid_analysis: ClmRaidV2Analysis, clm_raid_id: str,
) -> IdentityV2Store:
    """Apply an explicitly approved CLM participant correction to a copy."""
    store.validate()
    result = copy.deepcopy(store)
    raid = next((item for item in result.raids if item.clmRaidId == clm_raid_id), None)
    source = next((item for item in raid_analysis.raids
                   if item.raid_id == clm_raid_id), None)
    if raid is None or source is None:
        raise ClmRaidMaterializationError("CLM-Raid für Korrektur nicht gefunden.")
    owners = _guid_owners(result)
    ignored = {guid.casefold() for group in result.ignoredClmCharacterGroups
               for guid in group.clmGuids}
    participants: dict[str, tuple[str, str]] = {}
    for participant in source.participants:
        key = participant.guid.casefold()
        if participant.guid_status != "VALID_CHARACTER_GUID":
            raise ClmRaidMaterializationError(
                f"Ungültige Teilnehmer-GUID {participant.guid} in Raid {clm_raid_id}.")
        if key in ignored:
            continue
        member_id = owners.get(key)
        if member_id is None:
            raise ClmRaidMaterializationError(
                f"Teilnehmer-GUID {participant.guid} ist keinem Member zugeordnet.")
        if member_id in participants:
            raise ClmRaidMaterializationError(
                f"Zwei CLM-GUIDs desselben Members {member_id} in Raid {clm_raid_id}.")
        attendance_date = local_raid_date(participant.first_seen_in_raid)
        if not attendance_date:
            raise ClmRaidMaterializationError(
                f"Teilnahme {participant.guid} hat keinen gültigen Zeitpunkt.")
        participants[member_id] = (participant.guid, attendance_date)

    existing = {item.memberId: item for item in result.attendance
                if item.raidId == raid.raidId}
    removed_ids = {
        item.attendanceId for member_id, item in existing.items()
        if item.clmGuid and member_id not in participants
    }
    if removed_ids:
        result.attendance = [item for item in result.attendance
                             if item.attendanceId not in removed_ids]
        result.raidPoints.adjustments = {
            key: value for key, value in result.raidPoints.adjustments.items()
            if key not in removed_ids}
        result.raidPoints.excluded_attendance_ids.difference_update(removed_ids)
        removed_pairs = {(raid.raidId, member_id) for member_id, item in existing.items()
                         if item.attendanceId in removed_ids}
        result.raidCreditResolutions = [
            item for item in result.raidCreditResolutions
            if (item.raidId, item.creditedMemberId) not in removed_pairs]
    member_by_id = {member.memberId: member for member in result.members}
    for member_id, (guid, attendance_date) in participants.items():
        item = existing.get(member_id)
        if item is not None:
            item.clmGuid = guid
            item.status = "present"
        else:
            result.attendance.append(Attendance(
                attendanceId=_stable_id(
                    "attendance", raid_analysis.database_id,
                    raid_analysis.roster_id, clm_raid_id, member_id),
                raidId=raid.raidId, memberId=member_id,
                attendanceType="unknown", playerId=None, clmGuid=guid,
            ))
        member = member_by_id[member_id]
        if member.raidStartDate is None or attendance_date < member.raidStartDate:
            member.raidStartDate = attendance_date
    result.validate()
    return result


def _stable_id(kind: str, *parts: str) -> str:
    identity = "/".join(("ggc", "identity-v2", "clm", kind, *parts))
    prefix = "r" if kind == "raid" else "a"
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, identity).hex}"


def _guid_owners(store: IdentityV2Store) -> dict[str, str]:
    owners = {
        member.clmGuid.casefold(): member.memberId
        for member in store.members if member.clmGuid is not None
    }
    owners.update((guid.casefold(), member_id)
                  for guid, member_id in store.legacyClmGuidMemberMap.items())
    return owners


def materialize_clm_raids_into_identity_v2(
    store: IdentityV2Store, raid_analysis: ClmRaidV2Analysis,
    raid_types: Mapping[str, str] | None = None,
    *, selected_raid_ids: set[str] | None = None,
) -> IdentityV2Store:
    """Return a validated copy; the supplied identity store is never changed."""
    try:
        store.validate()
    except IdentityV2ValidationError as exc:
        raise ClmRaidMaterializationError(f"Eingangsstore ist ungültig: {exc}") from exc
    available = {source.raid_id for source in raid_analysis.raids}
    selected = available if selected_raid_ids is None else set(selected_raid_ids)
    unknown = selected - available
    if unknown:
        raise ClmRaidMaterializationError(
            "Unbekannte ausgewählte CLM-Raid-IDs: " + ", ".join(sorted(unknown)))
    if not selected:
        return copy.deepcopy(store)
    if not store.members and not store.ignoredClmCharacterGroups:
        raise ClmRaidMaterializationError("CLM-Raids benötigen einen materialisierten V2-Charakterbestand.")
    existing = {raid.clmRaidId: raid for raid in store.raids if raid.clmRaidId}
    choices = dict(raid_types or {})
    needed = {source.raid_id for source in raid_analysis.raids
              if source.raid_id in selected and (source.raid_id not in existing
              or detect_raid_type(existing[source.raid_id].raidType) is None)}
    if any(choices.get(raid_id) not in RAID_TYPES for raid_id in needed):
        raise ClmRaidMaterializationError("Jeder neue CLM-Raid benötigt einen gültigen Raid-Typ.")

    owners = _guid_owners(store)
    ignored_guids = {
        guid.casefold()
        for group in store.ignoredClmCharacterGroups
        for guid in group.clmGuids
    }
    for evidence in raid_analysis.identity_analysis.raid_coexistence:
        if evidence.raid_id not in selected:
            continue
        left = owners.get(evidence.guids[0].casefold())
        right = owners.get(evidence.guids[1].casefold())
        if left is not None and left == right:
            raise ClmRaidMaterializationError(
                f"SAME_RAID_COEXISTENCE in Raid {evidence.raid_id}: "
                f"{evidence.guids[0]} und {evidence.guids[1]} gehören beide zu {left}.")

    result = copy.deepcopy(store)
    existing_result = {raid.clmRaidId: raid for raid in result.raids if raid.clmRaidId}
    member_by_id = {member.memberId: member for member in result.members}
    first_attendance: dict[str, str] = {}
    seen_source_raids: set[str] = set()
    for source_raid in raid_analysis.raids:
        if source_raid.raid_id not in selected:
            continue
        if not source_raid.raid_id or source_raid.raid_id in seen_source_raids:
            raise ClmRaidMaterializationError(
                f"Doppelte oder leere CLM-Raid-ID: {source_raid.raid_id!r}.")
        seen_source_raids.add(source_raid.raid_id)
        previous_raid = existing_result.get(source_raid.raid_id)
        if previous_raid is not None:
            if _clm_attendance_conflict(result, previous_raid, source_raid):
                raise ClmRaidMaterializationError(
                    f"Teilnehmer von CLM-Raid {source_raid.raid_id} weichen ab; "
                    "bitte die bestehende Raid-/Attendance-Korrektur verwenden.")
            if detect_raid_type(previous_raid.raidType) is None:
                previous_raid.raidType = choices[source_raid.raid_id]
            continue
        raid_date = local_raid_date(source_raid.start_timestamp)
        if not raid_date:
            raise ClmRaidMaterializationError(
                f"Raid {source_raid.raid_id} hat keinen gültigen CLM-Startzeitstempel.")
        raid_id = _stable_id(
            "raid", raid_analysis.database_id, raid_analysis.roster_id, source_raid.raid_id,
        )
        result.raids.append(Raid(
            raidId=raid_id, date=raid_date, name=source_raid.name,
            clmRaidId=source_raid.raid_id, raidType=choices[source_raid.raid_id],
        ))
        seen_members: dict[str, str] = {}
        for participant in source_raid.participants:
            if participant.guid_status != "VALID_CHARACTER_GUID":
                raise ClmRaidMaterializationError(
                    f"Teilnehmer-GUID {participant.guid} in Raid {source_raid.raid_id} "
                    f"ist {participant.guid_status}; Quellen: "
                    f"{', '.join(participant.source_event_ids)}.")
            if participant.guid.casefold() in ignored_guids:
                continue
            member_id = owners.get(participant.guid.casefold())
            if member_id is None:
                raise ClmRaidMaterializationError(
                    f"Teilnehmer-GUID {participant.guid} in Raid {source_raid.raid_id} "
                    f"ist keinem Member zugeordnet; Quellen: "
                    f"{', '.join(participant.source_event_ids)}.")
            earlier_guid = seen_members.get(member_id)
            if earlier_guid is not None:
                raise ClmRaidMaterializationError(
                    f"Zwei GUIDs desselben Members {member_id} in Raid "
                    f"{source_raid.raid_id}: {earlier_guid}, {participant.guid}.")
            seen_members[member_id] = participant.guid
            attendance_date = local_raid_date(participant.first_seen_in_raid)
            if not attendance_date:
                raise ClmRaidMaterializationError(
                    f"Teilnahme {participant.guid} in Raid {source_raid.raid_id} "
                    "hat keinen gültigen Zeitpunkt.")
            result.attendance.append(Attendance(
                attendanceId=_stable_id(
                    "attendance", raid_analysis.database_id,
                    raid_analysis.roster_id, source_raid.raid_id, member_id,
                ),
                raidId=raid_id,
                memberId=member_id,
                # P2 is audit evidence, not a valid historical role source.
                attendanceType="unknown",
                playerId=None,
                clmGuid=participant.guid,
            ))
            previous = first_attendance.get(member_id)
            if previous is None or attendance_date < previous:
                first_attendance[member_id] = attendance_date

    for member_id, first_date in first_attendance.items():
        previous_start = member_by_id[member_id].raidStartDate
        member_by_id[member_id].raidStartDate = min(previous_start, first_date) if previous_start else first_date
    try:
        result.validate()
    except IdentityV2ValidationError as exc:
        raise ClmRaidMaterializationError(f"V2-Invariante nach CLM-Raid-Import verletzt: {exc}") from exc
    return result
