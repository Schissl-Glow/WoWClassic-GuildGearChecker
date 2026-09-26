"""Read-only CLM raid, participation, and historical P2 role analysis."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from itertools import combinations
from pathlib import Path
from typing import Mapping

from .clm_detection import describe_databases, describe_rosters, select_database, select_dkp_roster
from .clm_history import _guids, _roster_scoped_entries, guid_key, replay_clm_history
from .clm_identity_v2_analysis import (
    ClmIdentityAnalysis, ClmRaidCoexistence, _event_guid_keys,
    analyze_clm_ledger, display_date,
)
from .clm_models import ClmIntegrationError
from .clm_replay import _entry_sort_key, _entry_uuid, _guid, _sequence
from .clm_savedvariables import load_saved_variables


RAID_EVENT_MEANINGS = {
    "AC": "Raid angelegt; r ist die Roster-ID, die Ereignis-ID wird Raid-ID",
    "AS": "Raidstart/Snapshot; p anwesend, s Bank, r Raid-ID",
    "AU": "Raidänderung; j beigetreten, l verlassen, s Bank, e entfernt, r Raid-ID",
    "AE": "Raidende; r Raid-ID",
    "DR": "Raid-DKP-Ereignis; r Raid-ID, keine eigene Teilnahme",
}
PROFILE_EVENT_MEANINGS = {
    "P0": "Profilereignis; g ist die Charakter-GUID",
    "P1": "Profilentfernung; g ist die Charakter-GUID",
    "P2": "historischer Alt/Main-Link; g Alt, m Main",
    "P3": "Profil-Sperre; p enthält GUID-Referenzen",
}


@dataclass(frozen=True)
class ClmRaidParticipant:
    raid_id: str
    guid: str
    first_seen_in_raid: int
    last_seen_in_raid: int
    occurrence_count: int
    source_event_ids: tuple[str, ...]
    guid_status: str
    historical_role: str
    role_source_event_ids: tuple[str, ...]


@dataclass(frozen=True)
class ClmRaidSnapshot:
    raid_id: str
    name: str
    start_timestamp: int
    end_timestamp: int | None
    participants: tuple[ClmRaidParticipant, ...]
    bench_guids: tuple[str, ...]
    source_event_ids: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ClmAttributionDelta:
    opcode: str
    count: int
    meaning: str
    reference_fields: tuple[tuple[str, int], ...] = ()
    matched_guids: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class ClmMultiGuidRaidCollision:
    raid_id: str
    normalized_name: str
    guids: tuple[str, ...]
    includes_suggested_chain: bool


@dataclass(frozen=True)
class ClmRaidV2Analysis:
    database_id: str
    roster_id: str
    raids: tuple[ClmRaidSnapshot, ...]
    identity_analysis: ClmIdentityAnalysis
    raid_event_counts: tuple[tuple[str, int], ...]
    old_identity_event_count: int
    current_identity_event_count: int
    old_only_events: tuple[ClmAttributionDelta, ...]
    current_only_event_count: int
    invalid_reference_count: int

    @property
    def multi_guid_collisions(self) -> tuple[ClmMultiGuidRaidCollision, ...]:
        return _same_name_raid_collisions(self.raids, self.identity_analysis)

    @property
    def summary(self) -> dict[str, int | str]:
        participants = [participant for raid in self.raids for participant in raid.participants]
        actual_times = [participant.first_seen_in_raid for participant in participants]
        statuses = Counter(participant.guid_status for participant in participants)
        roles = Counter(participant.historical_role for participant in participants)
        collisions = self.multi_guid_collisions
        raid_starts = [raid.start_timestamp for raid in self.raids]
        return {
            "raids": len(self.raids),
            "firstRaidDate": display_date(min(raid_starts)) if raid_starts else "–",
            "lastRaidDate": display_date(max(raid_starts)) if raid_starts else "–",
            "firstActualRaidDate": display_date(min(actual_times)) if actual_times else "–",
            "lastActualRaidDate": display_date(max(actual_times)) if actual_times else "–",
            "uniqueGuidAttendances": len(participants),
            "benchOnlyGuidRaidReferences": sum(
                len(set(raid.bench_guids) - {item.guid for item in raid.participants})
                for raid in self.raids
            ),
            "participatingGuids": len({item.guid for item in participants}),
            "participantGuidsWithoutValidP0": len({
                item.guid for item in participants
                if item.guid_status != "VALID_CHARACTER_GUID"
            }),
            "unknownGuidAttendances": statuses["UNKNOWN_GUID"],
            "technicalGuidAttendances": statuses["TECHNICAL_GUID"],
            "invalidGuidAttendances": statuses["INVALID_REFERENCE"],
            "invalidRawReferences": self.invalid_reference_count,
            "technicalIgnoredGuidReferences": len(
                self.identity_analysis.ignored_technical_guids
            ),
            "duplicateParticipantOccurrences": sum(
                max(0, item.occurrence_count - 1) for item in participants
            ),
            "sameNameMultiGuidRaidCollisions": len(collisions),
            "sameRaidCoexistencePairs": len(self.identity_analysis.raid_coexistence),
            "suggestedChainRaidCollisions": sum(
                item.includes_suggested_chain for item in collisions
            ),
            "p2MainAttendances": roles["main"],
            "p2TwinkAttendances": roles["twink"],
            "p2UnknownAttendances": roles["unknown"],
        }

    def raids_for_guid(self, guid: str) -> tuple[ClmRaidSnapshot, ...]:
        return tuple(raid for raid in self.raids
                     if any(item.guid == guid for item in raid.participants))

    def first_actual_raid_date(self, guid: str) -> str | None:
        times = [item.first_seen_in_raid for raid in self.raids
                 for item in raid.participants if item.guid == guid]
        return display_date(min(times)) if times else None


@dataclass
class _ParticipantState:
    first_seen: int
    last_seen: int
    occurrence_count: int = 0
    source_event_ids: list[str] = field(default_factory=list)
    observed_roles: list[str] = field(default_factory=list)
    role_source_event_ids: set[str] = field(default_factory=set)

    def observe(self, timestamp: int, event_id: str, role: str,
                role_source: str | None, *, occurrence: bool) -> None:
        self.first_seen = min(self.first_seen, timestamp)
        self.last_seen = max(self.last_seen, timestamp)
        if event_id not in self.source_event_ids:
            self.source_event_ids.append(event_id)
        if occurrence:
            self.occurrence_count += 1
            self.observed_roles.append(role)
            if role_source:
                self.role_source_event_ids.add(role_source)


class _P2RoleState:
    """Mirror the profile-link semantics relevant to a raid-time role snapshot."""

    def __init__(self) -> None:
        self.profiles: set[tuple[object, ...]] = set()
        self.alt_to_main: dict[tuple[object, ...], tuple[tuple[object, ...], str]] = {}
        self.main_to_alts: dict[tuple[object, ...], set[tuple[object, ...]]] = defaultdict(set)

    def _unlink(self, alt: tuple[object, ...]) -> None:
        previous = self.alt_to_main.pop(alt, None)
        if previous is not None:
            self.main_to_alts[previous[0]].discard(alt)

    def apply(self, entry: Mapping[object, object]) -> None:
        opcode = str(entry.get("_d") or "")
        guid = _guid(entry.get("g"))
        if guid is None:
            return
        if opcode == "P0":
            self.profiles.add(guid)
        elif opcode == "P1":
            self.profiles.discard(guid)
            self._unlink(guid)
            for alt in tuple(self.main_to_alts.pop(guid, ())):
                self.alt_to_main.pop(alt, None)
        elif opcode == "P2" and guid in self.profiles:
            main = _guid(entry.get("m"))
            if main is None or main not in self.profiles:
                self._unlink(guid)
            elif (main != guid and not self.main_to_alts.get(guid)
                  and main not in self.alt_to_main
                  and self.alt_to_main.get(guid, (None,))[0] != main):
                self._unlink(guid)
                self.alt_to_main[guid] = (main, _entry_uuid(entry))
                self.main_to_alts[main].add(guid)

    def role_for(self, guid: tuple[object, ...]) -> tuple[str, str | None]:
        linked = self.alt_to_main.get(guid)
        if linked is not None and linked[0] in self.profiles:
            return "twink", linked[1]
        alts = self.main_to_alts.get(guid, set()) & self.profiles
        if alts:
            sources = [self.alt_to_main[alt][1] for alt in alts if alt in self.alt_to_main]
            return "main", min(sources) if sources else None
        return "unknown", None


def _guid_status(guid: str, identity: ClmIdentityAnalysis) -> str:
    valid = next((history for history in identity.guid_histories if history.guid == guid), None)
    if (valid is not None and valid.normalized_name and valid.character_class
            and "DATA_CONFLICT" not in valid.warnings):
        return "VALID_CHARACTER_GUID"
    if any(item.guid == guid for item in identity.ignored_technical_guids):
        return "TECHNICAL_GUID"
    parts = guid.split(":")
    if len(parts) < 2 or any(not part.isdigit() for part in parts):
        return "INVALID_REFERENCE"
    if int(parts[-1]) == 0:
        return "TECHNICAL_GUID"
    return "UNKNOWN_GUID"


def _same_name_raid_collisions(
    raids: tuple[ClmRaidSnapshot, ...], identity: ClmIdentityAnalysis,
) -> tuple[ClmMultiGuidRaidCollision, ...]:
    collisions: list[ClmMultiGuidRaidCollision] = []
    for raid in raids:
        present = {item.guid for item in raid.participants}
        for group in identity.multi_guid_groups:
            overlap = present & set(group.chronological_order)
            if len(overlap) > 1:
                collisions.append(ClmMultiGuidRaidCollision(
                    raid_id=raid.raid_id,
                    normalized_name=group.normalized_name,
                    guids=tuple(guid for guid in group.chronological_order if guid in overlap),
                    includes_suggested_chain=any(
                        pair.older_guid in overlap and pair.newer_guid in overlap
                        for pair in group.continuation_suggestions
                    ),
                ))
    return tuple(collisions)


def apply_raid_identity_evidence(
    identity: ClmIdentityAnalysis,
    collisions: tuple[ClmMultiGuidRaidCollision, ...],
) -> ClmIdentityAnalysis:
    """Attach hard same-raid exclusions without changing the original analysis."""
    coexistence = tuple(
        ClmRaidCoexistence(collision.raid_id, collision.normalized_name, pair)
        for collision in collisions
        for pair in combinations(collision.guids, 2)
    )
    blocked_pairs = {frozenset(item.guids) for item in coexistence}
    updated_groups = []
    for group in identity.multi_guid_groups:
        updated_pairs = tuple(
            replace(pair,
                    conflicts=tuple(sorted((*pair.conflicts, "SAME_RAID_COEXISTENCE"))),
                    continuation_plausible=False)
            if frozenset((pair.older_guid, pair.newer_guid)) in blocked_pairs
            and "SAME_RAID_COEXISTENCE" not in pair.conflicts else pair
            for pair in group.pairwise
        )
        by_key = {(pair.older_guid, pair.newer_guid): pair for pair in updated_pairs}
        updated_groups.append(replace(
            group,
            pairwise=updated_pairs,
            continuation_suggestions=tuple(
                by_key[(pair.older_guid, pair.newer_guid)]
                for pair in group.continuation_suggestions
                if by_key[(pair.older_guid, pair.newer_guid)].continuation_plausible
            ),
            conflicts=tuple(sorted({*group.conflicts,
                                    *(code for pair in updated_pairs for code in pair.conflicts)})),
        ))
    return replace(identity, multi_guid_groups=tuple(updated_groups),
                   raid_coexistence=coexistence)


def _identity_attribution_delta(
    ledger: object, roster_id: str,
) -> tuple[int, int, tuple[ClmAttributionDelta, ...], int]:
    all_entries = sorted((item for item in _sequence(ledger) if isinstance(item, Mapping)),
                         key=_entry_sort_key)
    ignored = {str(item.get("ref") or "") for item in all_entries if item.get("_d") == "IGN"}
    scoped = [item for item in _roster_scoped_entries(ledger, roster_id)
              if item.get("_d") != "IGN" and _entry_uuid(item) not in ignored]
    base_ids = {_entry_uuid(item) for item in scoped}
    old_guids = {guid_key(guid) for item in scoped for field in ("g", "p", "s", "j", "l")
                 for guid in _guids(item.get(field))}
    current_guids: set[str] = set()
    for item in scoped:
        current_guids.update(_event_guid_keys(item))
    old_ids, current_ids = set(base_ids), set(base_ids)
    by_id = {_entry_uuid(item): item for item in all_entries}
    for entry in all_entries:
        event_id = _entry_uuid(entry)
        if (entry.get("_d") not in {"P0", "P1", "P2", "P3"}
                or event_id in ignored or event_id in base_ids):
            continue
        old_refs = {guid_key(guid) for field in ("g", "p", "s", "j", "l", "m")
                    for guid in _guids(entry.get(field))}
        if old_refs & old_guids:
            old_ids.add(event_id)
        if _event_guid_keys(entry) & current_guids:
            current_ids.add(event_id)
    counts: Counter[str] = Counter()
    field_counts: Counter[tuple[str, str]] = Counter()
    guid_counts: Counter[tuple[str, str]] = Counter()
    for event_id in old_ids - current_ids:
        entry = by_id[event_id]
        opcode = str(entry.get("_d") or "")
        counts[opcode] += 1
        for field_name in ("g", "p", "s", "j", "l", "m"):
            matches = {guid_key(guid) for guid in _guids(entry.get(field_name))} & old_guids
            if matches:
                field_counts[(opcode, field_name)] += 1
                for guid in matches:
                    guid_counts[(opcode, guid)] += 1
    delta = tuple(ClmAttributionDelta(
        opcode=opcode,
        count=count,
        meaning=PROFILE_EVENT_MEANINGS.get(opcode, "sonstiges CLM-Ereignis"),
        reference_fields=tuple(sorted((field_name, number)
                                      for (kind, field_name), number in field_counts.items()
                                      if kind == opcode)),
        matched_guids=tuple(sorted((guid, number)
                                 for (kind, guid), number in guid_counts.items()
                                 if kind == opcode)),
    ) for opcode, count in sorted(counts.items()))
    return len(old_ids), len(current_ids), delta, len(current_ids - old_ids)


def analyze_clm_raid_file(
    source_path: Path | str, *, guild_name: str = "bierstube", realm: str = "stitches",
    roster_id: str | None = None,
) -> ClmRaidV2Analysis:
    document = load_saved_variables(source_path)
    database = select_database(describe_databases(document.data), guild_name, realm)
    raw_database = document.data.get(database.database_id)
    if not isinstance(raw_database, Mapping):
        raise ClmIntegrationError("Die ausgewählte CLM-Datenbank fehlt.")
    roster = select_dkp_roster(describe_rosters(database.database_id, raw_database),
                               database_id=database.database_id, requested_roster_id=roster_id)
    analysis = analyze_clm_raid_ledger(raw_database.get("ledger"), roster.roster_id)
    return ClmRaidV2Analysis(
        database.database_id, roster.roster_id, analysis.raids,
        replace(analysis.identity_analysis, database_id=database.database_id,
                roster_id=roster.roster_id),
        analysis.raid_event_counts,
        analysis.old_identity_event_count, analysis.current_identity_event_count,
        analysis.old_only_events, analysis.current_only_event_count,
        analysis.invalid_reference_count,
    )


def analyze_clm_raid_ledger(ledger: object, roster_id: str) -> ClmRaidV2Analysis:
    identity = analyze_clm_ledger(ledger, roster_id)
    projection = replay_clm_history(ledger, roster_id)
    all_entries = sorted((item for item in _sequence(ledger) if isinstance(item, Mapping)),
                         key=_entry_sort_key)
    scoped = _roster_scoped_entries(ledger, roster_id)
    ignored = {str(item.get("ref") or "") for item in all_entries if item.get("_d") == "IGN"}
    scoped_ids = {_entry_uuid(item) for item in scoped
                  if item.get("_d") != "IGN" and _entry_uuid(item) not in ignored}
    raid_history = {raid.clm_raid_id: raid for raid in projection.raids}
    participation: dict[str, dict[str, _ParticipantState]] = defaultdict(dict)
    source_events: dict[str, list[str]] = defaultdict(list)
    invalid_references = 0
    event_counts: Counter[str] = Counter()
    role_state = _P2RoleState()

    def note(raid_id: str, guid: tuple[object, ...], entry: Mapping[object, object],
             *, occurrence: bool) -> None:
        key = guid_key(guid)
        timestamp = int(entry.get("_c") or 0)
        event_id = _entry_uuid(entry)
        state = participation[raid_id].setdefault(key, _ParticipantState(timestamp, timestamp))
        role, role_source = role_state.role_for(guid)
        state.observe(timestamp, event_id, role, role_source, occurrence=occurrence)

    for entry in all_entries:
        event_id = _entry_uuid(entry)
        if entry.get("_d") == "IGN" or event_id in ignored:
            continue
        opcode = str(entry.get("_d") or "")
        if opcode in {"P0", "P1", "P2"}:
            role_state.apply(entry)
        if event_id not in scoped_ids or opcode not in RAID_EVENT_MEANINGS:
            continue
        raid_id = event_id if opcode == "AC" else str(entry.get("r") or "")
        if raid_id not in raid_history:
            continue
        event_counts[opcode] += 1
        source_events[raid_id].append(event_id)
        for field_name in (("p", "s") if opcode == "AS" else
                           ("j", "l", "s", "e") if opcode == "AU" else ()):
            value = entry.get(field_name)
            if value and not _guids(value):
                invalid_references += 1
        if opcode == "AS":
            for guid in _guids(entry.get("p")):
                note(raid_id, guid, entry, occurrence=True)
            for guid in _guids(entry.get("s")):
                if guid_key(guid) in participation[raid_id]:
                    note(raid_id, guid, entry, occurrence=False)
        elif opcode == "AU":
            for guid in _guids(entry.get("j")):
                note(raid_id, guid, entry, occurrence=True)
            for field_name in ("l", "s", "e"):
                for guid in _guids(entry.get(field_name)):
                    if guid_key(guid) in participation[raid_id]:
                        note(raid_id, guid, entry, occurrence=False)

    raids: list[ClmRaidSnapshot] = []
    for history in projection.raids:
        states = participation[history.clm_raid_id]
        participant_items: list[ClmRaidParticipant] = []
        for guid, state in sorted(states.items()):
            status = _guid_status(guid, identity)
            role = (state.observed_roles[0]
                    if status == "VALID_CHARACTER_GUID"
                    and len(set(state.observed_roles)) == 1 else "unknown")
            participant_items.append(ClmRaidParticipant(
                raid_id=history.clm_raid_id,
                guid=guid,
                first_seen_in_raid=state.first_seen,
                last_seen_in_raid=state.last_seen,
                occurrence_count=state.occurrence_count,
                source_event_ids=tuple(state.source_event_ids),
                guid_status=status,
                historical_role=role,
                role_source_event_ids=tuple(sorted(state.role_source_event_ids)),
            ))
        participants = tuple(participant_items)
        warnings = set(history.warnings)
        if {item.guid for item in participants} != history.participant_guids:
            warnings.add("PARTICIPANT_REPLAY_MISMATCH")
        raids.append(ClmRaidSnapshot(
            raid_id=history.clm_raid_id, name=history.name,
            start_timestamp=history.start_timestamp,
            end_timestamp=history.end_timestamp,
            participants=participants,
            bench_guids=tuple(sorted(history.bench_guids)),
            source_event_ids=tuple(source_events[history.clm_raid_id]),
            warnings=tuple(sorted(warnings)),
        ))
    old_count, current_count, delta, current_only = _identity_attribution_delta(ledger, roster_id)
    result = ClmRaidV2Analysis(
        "", str(roster_id), tuple(raids), identity,
        tuple(sorted(event_counts.items())), old_count, current_count, delta,
        current_only, invalid_references,
    )
    return replace(result, identity_analysis=apply_raid_identity_evidence(
        identity, result.multi_guid_collisions,
    ))


def format_raid_report(analysis: ClmRaidV2Analysis) -> str:
    lines = [f"CLM-Datenbank: {analysis.database_id}", f"DKP-Roster: {analysis.roster_id}"]
    lines.extend(f"{key}: {value}" for key, value in analysis.summary.items())
    lines.append(f"Identitätsereignisse alt/aktuell: {analysis.old_identity_event_count}/"
                 f"{analysis.current_identity_event_count}; nur aktuell: {analysis.current_only_event_count}")
    for item in analysis.old_only_events:
        fields = ", ".join(f"{field}={count}" for field, count in item.reference_fields)
        guids = ", ".join(f"{guid}={count}" for guid, count in item.matched_guids)
        lines.append(f"Delta {item.opcode}: {item.count} | {item.meaning} | "
                     f"alte Feldtreffer: {fields or '–'} | GUIDs: {guids or '–'}")
    for opcode, count in analysis.raid_event_counts:
        lines.append(f"Raid-Event {opcode}: {count} | {RAID_EVENT_MEANINGS[opcode]}")
    for collision in analysis.multi_guid_collisions:
        lines.append(
            f"Mehrfach-GUID im Raid {collision.raid_id}: {collision.normalized_name} | "
            f"{', '.join(collision.guids)} | "
            f"Vorschlagskette={'ja' if collision.includes_suggested_chain else 'nein'}"
        )
    for name in ("Annî", "Bämäräng"):
        lines.append(f"\n{name}:")
        histories = analysis.identity_analysis.histories_for_name(name)
        if not histories:
            lines.append("  nicht gefunden")
        for history in histories:
            raids = analysis.raids_for_guid(history.guid)
            roles = Counter(item.historical_role for raid in raids for item in raid.participants
                            if item.guid == history.guid)
            dates = [item.first_seen_in_raid for raid in raids for item in raid.participants
                     if item.guid == history.guid]
            lines.append(
                f"  {history.guid} | {history.character_class or 'unbekannt'} | "
                f"Raids={len(raids)} | erster={display_date(min(dates)) if dates else '–'} | "
                f"letzter={display_date(max(dates)) if dates else '–'} | "
                f"P2-Rolle main/twink/unknown={roles['main']}/{roles['twink']}/{roles['unknown']}"
            )
        guids = {history.guid for history in histories}
        coattendance = sum(len(guids & {item.guid for item in raid.participants}) > 1
                           for raid in analysis.raids)
        lines.append(f"  gemeinsame Raids mehrerer GUIDs: {coattendance}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only CLM Raid V2 analysis")
    parser.add_argument("source", type=Path)
    parser.add_argument("--guild", default="bierstube")
    parser.add_argument("--realm", default="stitches")
    parser.add_argument("--roster-id")
    args = parser.parse_args()
    print(format_raid_report(analyze_clm_raid_file(
        args.source, guild_name=args.guild, realm=args.realm, roster_id=args.roster_id,
    )))


if __name__ == "__main__":
    main()
