"""Manual, preview-first CLM raid-history synchronization."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

try:
    from .clm_detection import describe_databases, describe_rosters, select_database, select_dkp_roster
    from .clm_history import ClmHistoryProjection, EternalDkpRecord, replay_clm_history
    from .clm_matching import character_key
    from .clm_models import ClmIntegrationError, ClmRosterSelectionRequired
    from .clm_savedvariables import load_saved_variables
except ImportError:
    from clm_detection import describe_databases, describe_rosters, select_database, select_dkp_roster  # type: ignore
    from clm_history import ClmHistoryProjection, EternalDkpRecord, replay_clm_history  # type: ignore
    from clm_matching import character_key  # type: ignore
    from clm_models import ClmIntegrationError, ClmRosterSelectionRequired  # type: ignore
    from clm_savedvariables import load_saved_variables  # type: ignore


@dataclass(frozen=True)
class ClmRaidSyncPreview:
    source_path: Path
    source_modified_at: float | None
    database_id: str
    roster_id: str
    projection: ClmHistoryProjection
    member_by_guid: Mapping[str, str]
    unknown_names: tuple[str, ...]
    ambiguous_names: tuple[str, ...]
    ambiguous_member_ids: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class ClmRaidSyncResult:
    created_raids: int
    enriched_raids: int
    records: int
    combined_sessions: int


def analyze_clm_raid_history(
    source_path: Path | str, *, guild_name: str, realm: str,
    requested_roster_id: str | None, members: list[object],
    ignored_character_guids: set[str] | None = None,
) -> ClmRaidSyncPreview:
    document = load_saved_variables(source_path)
    database = select_database(describe_databases(document.data), guild_name, realm)
    raw_database = document.data.get(database.database_id)
    if not isinstance(raw_database, Mapping):
        raise ClmIntegrationError("Die passende CLM-Datenbank wurde nicht gefunden.")
    rosters = describe_rosters(database.database_id, raw_database)
    eligible = tuple(item for item in rosters if item.active and item.point_type == 0 and not item.is_test)
    if not requested_roster_id and len(eligible) > 1:
        raise ClmRosterSelectionRequired(eligible)
    roster = select_dkp_roster(
        rosters, database_id=database.database_id,
        requested_roster_id=requested_roster_id,
    )
    ledger = raw_database.get("ledger")
    if not isinstance(ledger, Mapping):
        raise ClmIntegrationError("Die CLM-Datenbank enthält kein Ledger.")
    projection = replay_clm_history(ledger, roster.roster_id)
    members_by_name: dict[str, list[object]] = {}
    for member in members:
        members_by_name.setdefault(character_key(getattr(member, "name", "")), []).append(member)
    member_by_guid: dict[str, str] = {}
    unknown: list[str] = []
    ambiguous: list[str] = []
    ambiguous_member_ids: dict[str, tuple[str, ...]] = {}
    ignored_guids = {str(guid) for guid in (ignored_character_guids or set())}
    for guid, name in projection.characters.items():
        if guid in ignored_guids:
            continue
        candidates = members_by_name.get(character_key(name), [])
        if len(candidates) == 1:
            member_by_guid[guid] = str(getattr(candidates[0], "id", ""))
        elif candidates:
            ambiguous.append(name)
            ambiguous_member_ids[character_key(name)] = tuple(
                str(getattr(candidate, "id", "")) for candidate in candidates
                if getattr(candidate, "id", None)
            )
        else:
            unknown.append(name)
    return ClmRaidSyncPreview(
        source_path=document.source_path or Path(source_path),
        source_modified_at=document.modified_at, database_id=database.database_id,
        roster_id=roster.roster_id, projection=projection,
        member_by_guid=member_by_guid, unknown_names=tuple(sorted(set(unknown), key=str.casefold)),
        ambiguous_names=tuple(sorted(set(ambiguous), key=str.casefold)),
        ambiguous_member_ids=ambiguous_member_ids,
    )


def apply_clm_raid_history(
    model: object, preview: ClmRaidSyncPreview,
    unknown_decisions: Mapping[str, tuple[str, str | None]] | None = None,
) -> ClmRaidSyncResult:
    snapshot = copy.deepcopy((
        model.members, model.players, model.raids, model.raid_attendance, model.raid_points,
        model.eternal_dkp, model.attendance_tracking_start_date, model.dirty,
        model.next_id, model.next_player_id,
    ))
    created = 0
    enriched = 0
    raid_by_clm_id: dict[str, str] = {}
    try:
        decisions = {
            character_key(name): (str(action), main_id)
            for name, (action, main_id) in (unknown_decisions or {}).items()
        }
        unresolved_by_key = {
            character_key(name): name
            for name in (*preview.unknown_names, *preview.ambiguous_names)
        }
        if set(decisions) != set(unresolved_by_key):
            raise ClmIntegrationError("Nicht alle CLM-Charaktere sind eindeutig zugeordnet.")
        resolved_member_by_key: dict[str, str] = {}
        for key, (action, main_id) in decisions.items():
            if action in {"discard", "irrelevant"}:
                continue
            if action == "existing":
                member = model.find_by_id(main_id or "")
                if (member is None
                        or member.id not in preview.ambiguous_member_ids.get(key, ())):
                    raise ClmIntegrationError("Ungültige vorhandene Charakterzuordnung.")
                resolved_member_by_key[key] = member.id
                continue
            if key not in {character_key(name) for name in preview.unknown_names}:
                raise ClmIntegrationError("Mehrdeutige Charaktere müssen explizit zugeordnet werden.")
            member = model.add_member(unresolved_by_key[key], "CLM Raid History")
            if action == "main":
                model.assign_character_type(member.id, "main", None, "not_set")
            elif action == "twink":
                model.assign_character_type(member.id, "twink", main_id, "not_set")
            elif action == "inactive":
                model.assign_character_type(member.id, "main", None, "not_set")
                member.lifeStatus = "inactive"
            elif action == "dead":
                model.assign_character_type(member.id, "main", None, "not_set")
                # Historical imports must not invent a death date or assign a grave.
                member.lifeStatus = "dead"
            elif action == "dead_twink":
                model.assign_character_type(member.id, "twink", main_id, "not_set")
                # Direct historical state: no active intermediate state or grave assignment.
                member.lifeStatus = "dead"
            else:
                raise ClmIntegrationError("Ungültige Charakterzuordnung.")
            resolved_member_by_key[key] = member.id

        for guid, name in preview.projection.characters.items():
            if decisions.get(character_key(name), ("", None))[0] == "irrelevant":
                model.eternal_dkp.ignored_character_guids.add(guid)

        member_by_guid = dict(preview.member_by_guid)
        for guid, name in preview.projection.characters.items():
            member_id = resolved_member_by_key.get(character_key(name))
            if member_id:
                member_by_guid[guid] = member_id

        for history in preview.projection.raids:
            if not history.date:
                continue
            raid = next((
                item for item in model.raids
                if history.clm_raid_id in item.clmRaidIds
            ), None)
            matches = [
                raid for raid in model.raids
                if raid.date == history.date
                and (not history.raid_types or raid.raidType in history.raid_types)
            ]
            if raid is None:
                raid = matches[0] if len(matches) == 1 else None
            if raid is None and len(history.raid_types) == 1:
                raid = model.create_raid(history.date, history.name or history.raid_types[0], "", history.raid_types[0])
                created += 1
            elif raid is None and history.combined:
                raid = model.create_raid(history.date, history.name or "CLM Combined")
                created += 1
            elif raid is not None:
                enriched += 1
            if raid is None:
                continue
            if history.clm_raid_id not in raid.clmRaidIds:
                raid.clmRaidIds.append(history.clm_raid_id)
            raid.raidStart = history.start_timestamp
            raid.raidEnd = history.end_timestamp
            raid.raidDuration = history.duration_seconds
            raid.sources = tuple(sorted(set(raid.sources) | {"clm"}))
            raid_by_clm_id[history.clm_raid_id] = raid.id
            if raid.status != "recorded":
                present_names = [
                    preview.projection.characters[guid]
                    for guid in sorted(history.participant_guids)
                    if guid in member_by_guid and guid in preview.projection.characters
                ]
                model.import_raid_attendance(raid.id, present_names)
                present_player_ids = {
                    entry.playerId for entry in model.attendance_for_raid(raid.id)
                    if entry.status == "present"
                }
                bench_member_ids = {
                    member_by_guid[guid]
                    for guid in history.bench_guids if guid in member_by_guid
                    and model.find_by_id(member_by_guid[guid]) is not None
                    and model.find_by_id(member_by_guid[guid]).playerId
                    and model.find_by_id(member_by_guid[guid]).playerId not in present_player_ids
                }
                if bench_member_ids:
                    model.set_historical_raid_bench_members(raid.id, bench_member_ids)

        records = []
        for item in preview.projection.earnings:
            member_id = member_by_guid.get(item.character_guid)
            if not member_id:
                continue
            records.append(EternalDkpRecord(
                event_id=item.event_id, member_id=member_id,
                character_name=item.character_name, value=item.value, kind=item.kind,
                clm_raid_id=item.clm_raid_id,
                raid_id=raid_by_clm_id.get(item.clm_raid_id, ""),
                timestamp=item.timestamp, description=item.description,
            ))
        model.eternal_dkp.replace_records(
            records, database_id=preview.database_id, roster_id=preview.roster_id,
            source_modified_at=preview.source_modified_at,
            synced_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        model.clm_roster_id = preview.roster_id
        model.dirty = True
    except Exception:
        (
            model.members, model.players, model.raids, model.raid_attendance, model.raid_points,
            model.eternal_dkp, model.attendance_tracking_start_date, model.dirty,
            model.next_id, model.next_player_id,
        ) = snapshot
        raise
    return ClmRaidSyncResult(
        created_raids=created, enriched_raids=enriched, records=len(model.eternal_dkp.records),
        combined_sessions=sum(history.combined for history in preview.projection.raids),
    )
