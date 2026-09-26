"""Atomically materialize a fully reviewed CSV bulk plan into a V2 store copy."""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .csv_import import CANONICAL_CLASSES, exact_name_key
from .csv_v2_analysis import (
    CsvRaidImportPlan, analyze_csv_raids_for_v2, v2_store_fingerprint,
)
from .identity_v2 import (
    Attendance, CsvRaidSource, IdentityV2Store, Member, Raid, member_id_from_number,
    new_v2_attendance_id, new_v2_raid_id, require_member_attendance_date,
)
from .identity_v2_import_choices import CharacterImportChoice


class CsvV2MaterializationError(ValueError):
    """The reviewed plan cannot be applied without losing V2 identity evidence."""


@dataclass(frozen=True)
class CsvRaidDecision:
    action: str  # LINK_CLM_RAIDS, MERGE_EXISTING, or CREATE_NEW
    existing_raid_id: str | None = None
    existing_raid_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CsvImportDecisions:
    raid_decisions: Mapping[Path, CsvRaidDecision] = field(default_factory=dict)
    member_selections: Mapping[tuple[Path, str], str] = field(default_factory=dict)
    new_member_classes: Mapping[str, str] = field(default_factory=dict)
    new_member_choices: Mapping[str, "CsvMemberImportChoice"] = field(default_factory=dict)
    create_new_members: bool = False
    active_raid_paths: frozenset[Path] | None = None
    raid_type_overrides: Mapping[Path, str] = field(default_factory=dict)


CsvMemberImportChoice = CharacterImportChoice


@dataclass(frozen=True)
class CsvImportSummary:
    new_raids: int
    merged_existing_raids: int
    separate_duplicate_raids: int
    existing_attendance_skipped: int
    new_attendance: int
    new_members: int
    ignored_members: int
    raid_start_shifts: int
    new_raid_starts: int
    death_conflicts: int = 0
    clm_metadata_reports: int = 0
    csv_names_not_attended_to_clm: int = 0
    csv_extra_names_against_clm: int = 0


def _next_member_number(store: IdentityV2Store) -> int:
    numbers = [int(match.group(1)) for member in store.members
               if (match := re.fullmatch(r"m(\d+)", member.memberId))]
    return max((999, *numbers)) + 1


def _append_csv_source(raid: Raid, source: Path, report_url: str | None) -> None:
    filename = source.name
    record = CsvRaidSource(filename, report_url)
    if record not in raid.csvSources:
        records = list(raid.csvSources)
        unknown_url = CsvRaidSource(filename, None)
        if report_url and unknown_url in records:
            records[records.index(unknown_url)] = record
        else:
            records.append(record)
        raid.csvSources = tuple(records)
    if filename not in raid.csvSourceFiles:
        raid.csvSourceFiles = (*raid.csvSourceFiles, filename)
    if report_url and report_url not in raid.csvReportUrls:
        raid.csvReportUrls = (*raid.csvReportUrls, report_url)


def _review_raid_targets(
    store: IdentityV2Store, plan: CsvRaidImportPlan, decisions: CsvImportDecisions,
) -> dict[Path, tuple[str, ...] | None]:
    required = {item.source_path: item for item in plan.possible_duplicates}
    if set(decisions.raid_decisions) != set(required):
        raise CsvV2MaterializationError(
            "Für jeden möglichen Duplicate-Raid ist eine explizite Entscheidung erforderlich."
        )
    raid_by_id = {raid.raidId: raid for raid in store.raids}
    targets: dict[Path, tuple[str, ...] | None] = {}
    for candidate in plan.raid_candidates:
        if candidate.status == "NEW_RAID":
            targets[candidate.source_path] = None
            continue
        if candidate.status == "KNOWN_RAID":
            chosen = ((candidate.automatic_csv_raid_id,)
                      if candidate.automatic_csv_raid_id
                      else candidate.automatic_clm_raid_ids)
        else:
            decision = decisions.raid_decisions[candidate.source_path]
            if decision.action == "CREATE_NEW":
                if decision.existing_raid_id or decision.existing_raid_ids:
                    raise CsvV2MaterializationError(
                        f"CSV-only Raid {candidate.source_path.name} darf kein CLM-Ziel haben."
                    )
                targets[candidate.source_path] = None
                continue
            if decision.action == "MERGE_EXISTING":
                chosen = (decision.existing_raid_id,) if decision.existing_raid_id else ()
            elif decision.action == "LINK_CLM_RAIDS":
                chosen = decision.existing_raid_ids
            else:
                raise CsvV2MaterializationError(
                    f"Ungültige Raidentscheidung für {candidate.source_path.name}."
                )
        if not chosen or len(set(chosen)) != len(chosen):
            raise CsvV2MaterializationError(
                f"CLM-Zuordnung für {candidate.source_path.name} ist leer oder doppelt."
            )
        for raid_id in chosen:
            raid = raid_by_id.get(raid_id)
            if (raid_id not in candidate.matching_raid_ids or raid is None
                    or raid.date != candidate.raid_date
                    or (not raid.clmRaidId
                        and not (raid.csvSourceFiles or raid.csvSources))):
                raise CsvV2MaterializationError(
                    f"Raid {raid_id!r} ist kein zulässiges Ziel für "
                    f"{candidate.source_path.name}."
                )
        if len(chosen) > 1 and any(not raid_by_id[raid_id].clmRaidId for raid_id in chosen):
            raise CsvV2MaterializationError(
                f"CSV-only Ziel für {candidate.source_path.name} muss eindeutig sein."
            )
        if candidate.status != "KNOWN_RAID" and decision.action == "LINK_CLM_RAIDS" \
                and any(not raid_by_id[raid_id].clmRaidId for raid_id in chosen):
            raise CsvV2MaterializationError(
                f"CSV-only Ziel für {candidate.source_path.name} benötigt MERGE_EXISTING."
            )
        targets[candidate.source_path] = tuple(chosen)
    return targets


def _validate_review(
    store: IdentityV2Store, plan: CsvRaidImportPlan, decisions: CsvImportDecisions,
    targets: Mapping[Path, tuple[str, ...] | None],
) -> tuple[dict[str, str | None], dict[str, CsvMemberImportChoice]]:
    raids = {raid.raidId: raid for raid in store.raids}
    csv_only_paths = {
        source for source, raid_ids in targets.items()
        if raid_ids is None or all(not raids[raid_id].clmRaidId for raid_id in raid_ids)
    }
    blocked = [item for item in plan.blocked_member_matches
               if item.source_path in csv_only_paths]
    if blocked:
        raise CsvV2MaterializationError(
            f"{len(blocked)} CSV-Vorkommen haben keinen "
            "zulässigen gleichnamigen Member."
        )
    if plan.existing_death_conflicts:
        raise CsvV2MaterializationError(
            f"{len(plan.existing_death_conflicts)} bestehende Attendances liegen nach "
            "einem bekannten Todesdatum; bewusste Korrektur erforderlich."
        )
    all_occurrences = {
        (item.source_path, exact_name_key(item.csv_name)): item
        for item in plan.ambiguous_member_matches
    }
    required_occurrences = {key for key in all_occurrences
                            if key[0] in csv_only_paths}
    if (not required_occurrences <= set(decisions.member_selections)
            or set(decisions.member_selections) - set(all_occurrences)):
        raise CsvV2MaterializationError(
            "Alle mehrdeutigen CSV-only Vorkommen benötigen eine eigene Memberentscheidung."
        )
    for key, member_id in decisions.member_selections.items():
        if member_id not in {option.member_id for option in all_occurrences[key].options}:
            raise CsvV2MaterializationError(
                f"Member {member_id!r} ist für {key[0].name} nicht zulässig."
            )

    all_new = {exact_name_key(item.name): item for item in plan.new_member_candidates}
    required_new = {key: item for key, item in all_new.items()
                    if any(source in csv_only_paths for source in item.source_paths)}
    if set(decisions.new_member_classes) - set(all_new):
        raise CsvV2MaterializationError("Klassenentscheidung für unbekannten CSV-Namen.")
    if set(decisions.new_member_choices) - set(all_new):
        raise CsvV2MaterializationError("Klassifikationsentscheidung für unbekannten CSV-Namen.")
    players = {player.playerId for player in store.players}
    chosen_classes: dict[str, str | None] = {}
    chosen_members: dict[str, CsvMemberImportChoice] = {}
    for key, candidate in required_new.items():
        choice = decisions.new_member_choices.get(key)
        if choice is None:
            if not decisions.create_new_members:
                raise CsvV2MaterializationError(
                    f"Charakter {candidate.name!r} benötigt eine Importklassifikation "
                    "(aktiv, inaktiv oder irrelevant)."
                )
            choice = CsvMemberImportChoice()
        if choice.activity_status not in {"active", "inactive"}:
            raise CsvV2MaterializationError(
                f"Ungültiger Aktivitätsstatus für {candidate.name!r}."
            )
        if choice.relevance not in {"relevant", "irrelevant"}:
            raise CsvV2MaterializationError(
                f"Ungültige Relevanzentscheidung für {candidate.name!r}."
            )
        if choice.player_id is not None:
            if choice.player_id not in players:
                raise CsvV2MaterializationError(
                    f"Player {choice.player_id!r} für {candidate.name!r} existiert nicht."
                )
            if choice.current_role not in {None, "twink"}:
                raise CsvV2MaterializationError(
                    "CSV-Import darf keinen Main oder Ex-Main setzen."
                )
            if choice.activity_status == "active" and choice.current_role != "twink":
                raise CsvV2MaterializationError(
                    "Aktiver Import mit bestehendem Player benötigt die bestätigte Twink-Rolle."
                )
            if choice.activity_status == "inactive" and choice.current_role is not None:
                raise CsvV2MaterializationError(
                    "Inaktive Member erhalten beim Import keine aktuelle Main-/Twink-Rolle."
                )
        elif choice.current_role is not None:
            raise CsvV2MaterializationError(
                "Eine aktuelle Rolle benötigt eine existierende Player-Zuordnung."
            )
        if choice.relevance == "irrelevant" and choice.player_id is not None:
            raise CsvV2MaterializationError(
                f"Irrelevanter Charakter {candidate.name!r} darf keinen Player erhalten."
            )
        class_name = (choice.class_name or decisions.new_member_classes.get(key)
                      or candidate.class_name)
        if class_name is not None and class_name not in CANONICAL_CLASSES:
            raise CsvV2MaterializationError(
                f"Ungültige Klasse {class_name!r} für {candidate.name!r}."
            )
        chosen_classes[key] = class_name
        chosen_members[key] = choice
    return chosen_classes, chosen_members


def materialize_csv_raid_import(
    store: IdentityV2Store, plan: CsvRaidImportPlan, decisions: CsvImportDecisions,
) -> tuple[IdentityV2Store, CsvImportSummary]:
    """Return a fully validated copy and summary; never mutate the input store."""
    store.validate()
    sources = [candidate.source_path for candidate in plan.raid_candidates]
    known_paths = set(sources)
    active_paths = (known_paths if decisions.active_raid_paths is None
                    else set(decisions.active_raid_paths))
    if (active_paths - known_paths or set(decisions.raid_type_overrides) - known_paths
            or set(decisions.raid_decisions) - known_paths):
        raise CsvV2MaterializationError("Unbekannte CSV-Quelle in Raidentscheidungen.")
    if not active_paths:
        return copy.deepcopy(store), CsvImportSummary(0, 0, 0, 0, 0, 0, 0, 0, 0)
    if plan.store_fingerprint != v2_store_fingerprint(store):
        raise CsvV2MaterializationError(
            "Der V2-Store hat sich seit der CSV-Analyse geändert."
        )
    fingerprints = dict(plan.source_fingerprints)
    for source in active_paths:
        try:
            current = hashlib.sha256(source.read_bytes()).hexdigest()
        except OSError as exc:
            raise CsvV2MaterializationError(
                f"Aktive CSV-Quelle kann nicht gelesen werden: {source}") from exc
        if current != fingerprints.get(source):
            raise CsvV2MaterializationError(
                f"Aktive CSV-Quelle hat sich seit der Analyse geändert: {source.name}"
            )
    active_sources = [source for source in sources if source in active_paths]
    active_overrides = {source: raid_type for source, raid_type
                        in decisions.raid_type_overrides.items()
                        if source in active_paths}
    try:
        effective_plan = analyze_csv_raids_for_v2(
            store, active_sources, raid_type_overrides=active_overrides)
    except (OSError, ValueError) as exc:
        raise CsvV2MaterializationError(
            f"CSV-Analyse mit Raidentscheidungen ist ungültig: {exc}") from exc
    base_new_keys = {exact_name_key(item.name) for item in plan.new_member_candidates}
    effective_new_keys = {exact_name_key(item.name)
                          for item in effective_plan.new_member_candidates}
    effective_duplicate_paths = {item.source_path
                                 for item in effective_plan.possible_duplicates}
    effective_decisions = CsvImportDecisions(
        raid_decisions={path: choice for path, choice in decisions.raid_decisions.items()
                        if path in effective_duplicate_paths},
        member_selections={key: value for key, value in decisions.member_selections.items()
                           if key[0] in active_paths or key[0] not in known_paths},
        new_member_classes={key: value for key, value in decisions.new_member_classes.items()
                            if key in effective_new_keys or key not in base_new_keys},
        new_member_choices={key: value for key, value in decisions.new_member_choices.items()
                            if key in effective_new_keys or key not in base_new_keys},
        create_new_members=decisions.create_new_members,
    )
    targets = _review_raid_targets(store, effective_plan, effective_decisions)
    chosen_classes, chosen_members = _validate_review(
        store, effective_plan, effective_decisions, targets)

    result = copy.deepcopy(store)
    members = {member.memberId: member for member in result.members}
    raids = {raid.raidId: raid for raid in result.raids}
    existing_attendance = {(item.raidId, item.memberId) for item in result.attendance}
    old_raid_starts = {member.memberId: member.raidStartDate for member in result.members}

    next_number = _next_member_number(result)
    new_member_ids: dict[str, str | None] = {}
    ignored_members = 0
    for candidate in effective_plan.new_member_candidates:
        key = exact_name_key(candidate.name)
        if key not in chosen_members:
            continue
        choice = chosen_members[key]
        if choice.relevance == "irrelevant":
            result.ignore_csv_character(candidate.name)
            new_member_ids[key] = None
            ignored_members += 1
            continue
        member_id = member_id_from_number(next_number)
        while member_id in members:
            next_number += 1
            member_id = member_id_from_number(next_number)
        next_number += 1
        member = Member(
            memberId=member_id, name=candidate.name,
            className=chosen_classes[key], lifeStatus=choice.activity_status,
            playerId=choice.player_id,
        )
        result.members.append(member)
        members[member_id] = member
        new_member_ids[key] = member_id

    attendance_by_source: dict[Path, list] = {}
    for item in effective_plan.attendance_candidates:
        attendance_by_source.setdefault(item.source_path, []).append(item)
    new_raids = separate_duplicates = skipped = added = 0
    metadata_reports = csv_names_not_attended = csv_extra_names = 0
    merged_ids: set[str] = set()
    for candidate in effective_plan.raid_candidates:
        linked_clm_ids = targets[candidate.source_path]
        if (linked_clm_ids is not None
                and all(raids[raid_id].clmRaidId for raid_id in linked_clm_ids)):
            metadata_reports += 1
            clm_name_keys = {
                exact_name_key(members[entry.memberId].name)
                for entry in result.attendance if entry.raidId in linked_clm_ids
            }
            csv_names_not_attended += len(candidate.participant_names)
            csv_extra_names += sum(
                exact_name_key(name) not in clm_name_keys
                for name in candidate.participant_names
            )
            skipped += sum(
                exact_name_key(name) in clm_name_keys
                for name in candidate.participant_names
            )
            for raid_id in linked_clm_ids:
                _append_csv_source(
                    raids[raid_id], candidate.source_path, candidate.report_url,
                )
                merged_ids.add(raid_id)
            continue
        if linked_clm_ids is not None:
            raid = raids[linked_clm_ids[0]]
            raid.raidType = candidate.raid_type
            merged_ids.add(raid.raidId)
        else:
            raid_id = new_v2_raid_id()
            while raid_id in raids:
                raid_id = new_v2_raid_id()
            raid = Raid(raid_id, candidate.raid_date, candidate.raid_type,
                        candidate.raid_name)
            result.raids.append(raid)
            raids[raid_id] = raid
            new_raids += 1
            if candidate.status == "POSSIBLE_DUPLICATE":
                separate_duplicates += 1
        _append_csv_source(raid, candidate.source_path, candidate.report_url)
        seen_members_in_file: set[str] = set()
        for occurrence in attendance_by_source.get(candidate.source_path, ()):
            if occurrence.status == "RESOLVED":
                member_id = occurrence.member_id
            elif occurrence.status == "AMBIGUOUS":
                member_id = effective_decisions.member_selections[
                    (candidate.source_path, exact_name_key(occurrence.csv_name))
                ]
            elif occurrence.status == "NEW_MEMBER_CANDIDATE":
                member_id = new_member_ids[exact_name_key(occurrence.csv_name)]
                if member_id is None:
                    continue
            elif occurrence.status == "IGNORED":
                continue
            else:
                raise CsvV2MaterializationError(
                    f"Unaufgelöste Attendance {occurrence.csv_name!r} in "
                    f"{candidate.source_path.name}."
                )
            if member_id not in members:
                raise CsvV2MaterializationError(f"Unbekannte memberId {member_id!r}.")
            require_member_attendance_date(members[member_id], candidate.raid_date)
            if member_id in seen_members_in_file:
                raise CsvV2MaterializationError(
                    f"Member {member_id} ist in {candidate.source_path.name} mehrfach zugeordnet."
                )
            seen_members_in_file.add(member_id)
            identity = (raid.raidId, member_id)
            if identity in existing_attendance:
                skipped += 1
                continue
            attendance_id = new_v2_attendance_id()
            result.attendance.append(Attendance(
                attendance_id, raid.raidId, member_id, "unknown",
                playerId=members[member_id].playerId, clmGuid=None,
            ))
            existing_attendance.add(identity)
            added += 1

    dates_by_member: dict[str, list[str]] = {}
    raid_dates = {raid.raidId: raid.date for raid in result.raids}
    for entry in result.attendance:
        dates_by_member.setdefault(entry.memberId, []).append(raid_dates[entry.raidId])
    shifts = new_starts = 0
    if added:
        for member in result.members:
            derived = (min(dates_by_member[member.memberId])
                       if member.memberId in dates_by_member else None)
            previous = old_raid_starts.get(member.memberId)
            if previous and derived and derived < previous:
                shifts += 1
            if previous is None and derived is not None:
                new_starts += 1
            member.raidStartDate = derived
    result.validate()
    return result, CsvImportSummary(
        new_raids, len(merged_ids), separate_duplicates, skipped,
        added, len(new_member_ids) - ignored_members, ignored_members,
        shifts, new_starts, 0, metadata_reports,
        csv_names_not_attended, csv_extra_names,
    )
