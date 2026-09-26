"""Read-only CLM GUID history and continuation analysis for Identity V2."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from .clm_detection import describe_databases, describe_rosters, select_database, select_dkp_roster
from .clm_history import ClmEarning, _guids, _roster_scoped_entries, guid_key, replay_clm_history
from .clm_matching import character_key, strip_realm_suffix
from .clm_models import ClmIntegrationError
from .clm_replay import _entry_sort_key, _entry_uuid, _sequence
from .clm_savedvariables import load_saved_variables


_CLASS_BY_ID = {
    1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest",
    7: "Shaman", 8: "Mage", 9: "Warlock", 11: "Druid",
}
_GUID_FIELDS = ("g", "p", "s", "j", "l")
_PROFILE_OPCODES = frozenset({"P0", "P1", "P2", "P3"})


def canonical_clm_class(value: object) -> str | None:
    """Map P0.c to the same nine canonical class names used by GGC."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return _CLASS_BY_ID.get(value)
    text = str(value or "").strip()
    if text.isdigit():
        return _CLASS_BY_ID.get(int(text))
    return next((name for name in _CLASS_BY_ID.values() if name.casefold() == text.casefold()), None)


@dataclass(frozen=True)
class ClmIncompleteP0:
    event_id: str
    original_name: str
    class_value: int | str | None
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class ClmGuidHistory:
    guid: str
    original_name: str
    normalized_name: str
    p0_class_value: int | str | None
    character_class: str | None
    first_seen: int | None
    last_seen: int | None
    active_at_end: bool
    p0_count: int
    p1_count: int
    eternal_dkp_records: tuple[ClmEarning, ...]
    warnings: tuple[str, ...]
    incomplete_p0_events: tuple[ClmIncompleteP0, ...] = ()

    @property
    def eternal_dkp_total(self) -> int | float:
        return sum(record.value for record in self.eternal_dkp_records)

    @property
    def incomplete_p0_count(self) -> int:
        return len(self.incomplete_p0_events)


@dataclass(frozen=True)
class ClmGuidPair:
    older_guid: str
    newer_guid: str
    gap_days: float | None
    overlap_days: float | None
    conflicts: tuple[str, ...]
    continuation_plausible: bool


@dataclass(frozen=True)
class ClmRaidCoexistence:
    raid_id: str
    normalized_name: str
    guids: tuple[str, str]


@dataclass(frozen=True)
class ClmIgnoredTechnicalGuid:
    guid: str
    warning: str
    source_references: tuple[str, ...]


@dataclass(frozen=True)
class ClmMultiGuidGroup:
    normalized_name: str
    guid_histories: tuple[ClmGuidHistory, ...]
    chronological_order: tuple[str, ...]
    pairwise: tuple[ClmGuidPair, ...]
    continuation_suggestions: tuple[ClmGuidPair, ...]
    conflicts: tuple[str, ...]


@dataclass(frozen=True)
class ClmIdentityAnalysis:
    database_id: str
    roster_id: str
    relevant_ledger_entries: int
    guid_histories: tuple[ClmGuidHistory, ...]
    multi_guid_groups: tuple[ClmMultiGuidGroup, ...]
    ignored_technical_guids: tuple[ClmIgnoredTechnicalGuid, ...] = ()
    raid_coexistence: tuple[ClmRaidCoexistence, ...] = ()

    @property
    def summary(self) -> dict[str, int]:
        named = [history for history in self.guid_histories if history.normalized_name]
        counts: dict[str, int] = {}
        for history in named:
            key = character_key(history.normalized_name)
            counts[key] = counts.get(key, 0) + 1
        return {
            "ledgerEntries": self.relevant_ledger_entries,
            "guids": len(self.guid_histories),
            "names": len(counts),
            "singleGuidNames": sum(value == 1 for value in counts.values()),
            "multiGuidNames": sum(value > 1 for value in counts.values()),
            "sameClassMultiGuidGroups": sum(
                len({history.character_class for history in group.guid_histories}) == 1
                and all(history.character_class for history in group.guid_histories)
                for group in self.multi_guid_groups
            ),
            "classConflictGroups": sum(
                "CLASS_CONFLICT" in group.conflicts for group in self.multi_guid_groups
            ),
            "timeOverlapPairs": sum(
                "TIME_OVERLAP" in pair.conflicts
                for group in self.multi_guid_groups for pair in group.pairwise
            ),
            "continuationSuggestions": sum(
                len(group.continuation_suggestions) for group in self.multi_guid_groups
            ),
            "dataConflictGuids": sum(
                "DATA_CONFLICT" in history.warnings for history in self.guid_histories
            ),
            "incompleteP0Ignored": sum(
                history.incomplete_p0_count for history in self.guid_histories
            ),
            "technicalGuidsIgnored": len(self.ignored_technical_guids),
            "sameRaidCoexistencePairs": len(self.raid_coexistence),
        }

    def histories_for_name(self, name: str) -> tuple[ClmGuidHistory, ...]:
        key = character_key(name)
        return tuple(history for history in self.guid_histories
                     if character_key(history.normalized_name) == key)

    def group_for_name(self, name: str) -> ClmMultiGuidGroup | None:
        key = character_key(name)
        return next((group for group in self.multi_guid_groups
                     if character_key(group.normalized_name) == key), None)


def analyze_clm_file(
    source_path: Path | str, *, guild_name: str = "bierstube", realm: str = "stitches",
    roster_id: str | None = None,
) -> ClmIdentityAnalysis:
    """Read the selected guild and DKP roster without changing the Lua file."""
    document = load_saved_variables(source_path)
    database = select_database(describe_databases(document.data), guild_name, realm)
    raw_database = document.data.get(database.database_id)
    if not isinstance(raw_database, Mapping):
        raise ClmIntegrationError("Die ausgewählte CLM-Datenbank fehlt.")
    roster = select_dkp_roster(
        describe_rosters(database.database_id, raw_database),
        database_id=database.database_id, requested_roster_id=roster_id,
    )
    analysis = analyze_clm_ledger(raw_database.get("ledger"), roster.roster_id)
    return ClmIdentityAnalysis(
        database.database_id, roster.roster_id, analysis.relevant_ledger_entries,
        analysis.guid_histories, analysis.multi_guid_groups, analysis.ignored_technical_guids,
    )


def _event_guid_keys(entry: Mapping[object, object]) -> set[str]:
    """Read character GUIDs only from fields with that meaning for the opcode."""
    opcode = str(entry.get("_d") or "")
    if opcode in {"P0", "P1"}:
        fields = ("g",)
    elif opcode == "P2":
        fields = ("g", "m")
    elif opcode == "P3":
        fields = ("p",)
    else:
        fields = _GUID_FIELDS
    return {guid_key(guid) for field in fields for guid in _guids(entry.get(field))}


def _technical_profile_guid_audit(
    selected: list[Mapping[object, object]],
    all_entries: list[Mapping[object, object]],
    relevant_guids: set[str],
) -> tuple[ClmIgnoredTechnicalGuid, ...]:
    primary_guids = {
        guid_key(guid)
        for entry in all_entries if entry.get("_d") == "P0"
        for guid in _guids(entry.get("g"))
    }
    references: dict[str, set[str]] = {}
    for entry in selected:
        if entry.get("_d") != "P0":
            continue
        for guid in _guids(entry.get("s")):
            key = guid_key(guid)
            # A zero character component in P0.s is a technical reference,
            # provided no P0.g or roster event establishes it as a character.
            if (len(guid) < 2 or str(guid[-1]) != "0"
                    or key in primary_guids or key in relevant_guids):
                continue
            references.setdefault(key, set()).add(f"P0.s:{_entry_uuid(entry)}")
    return tuple(
        ClmIgnoredTechnicalGuid(guid, "TECHNICAL_GUID_IGNORED", tuple(sorted(sources)))
        for guid, sources in sorted(references.items())
    )


def analyze_clm_ledger(ledger: object, roster_id: str) -> ClmIdentityAnalysis:
    """Replay the selected roster's GUID history and propose only plausible links."""
    all_entries = sorted(
        (entry for entry in _sequence(ledger) if isinstance(entry, Mapping)),
        key=_entry_sort_key,
    )
    scoped = _roster_scoped_entries(ledger, roster_id)
    ignored = {str(entry.get("ref") or "") for entry in all_entries
               if entry.get("_d") == "IGN"}
    selected = [entry for entry in scoped
                if entry.get("_d") != "IGN" and _entry_uuid(entry) not in ignored]
    relevant_guids: set[str] = set()
    for entry in selected:
        relevant_guids.update(_event_guid_keys(entry))
    technical_guids = _technical_profile_guid_audit(selected, all_entries, relevant_guids)
    if not relevant_guids:
        return ClmIdentityAnalysis("", str(roster_id), len(selected), (), (), technical_guids)

    selected_ids = {_entry_uuid(entry) for entry in selected}
    for entry in all_entries:
        if (entry.get("_d") not in _PROFILE_OPCODES
                or _entry_uuid(entry) in ignored or _entry_uuid(entry) in selected_ids):
            continue
        if _event_guid_keys(entry) & relevant_guids:
            selected.append(entry)
            selected_ids.add(_entry_uuid(entry))
    selected.sort(key=_entry_sort_key)

    events_by_guid: dict[str, list[Mapping[object, object]]] = {
        guid: [] for guid in relevant_guids
    }
    for entry in selected:
        for guid in _event_guid_keys(entry):
            if guid in events_by_guid:
                events_by_guid[guid].append(entry)

    earnings = replay_clm_history(ledger, roster_id)
    earnings_by_guid: dict[str, list[ClmEarning]] = {guid: [] for guid in relevant_guids}
    raw_earnings = list(earnings.standalone_earnings)
    for raid in earnings.raids:
        raw_earnings.extend(raid.earnings)
    for record in raw_earnings:
        if record.character_guid in earnings_by_guid:
            earnings_by_guid[record.character_guid].append(record)

    histories: list[ClmGuidHistory] = []
    for guid in sorted(relevant_guids):
        related = events_by_guid[guid]
        profile_events = [entry for entry in related if entry.get("_d") in {"P0", "P1"}
                          and any(guid_key(candidate) == guid for candidate in _guids(entry.get("g")))]
        timestamps = [_timestamp(entry) for entry in related]
        timestamps.extend(record.timestamp for record in earnings_by_guid[guid])
        known_times = [timestamp for timestamp in timestamps if timestamp is not None]
        original_name = ""
        normalized_name = ""
        p0_class_value: int | str | None = None
        character_class: str | None = None
        warnings: set[str] = set()
        active = False
        p0_count = p1_count = 0
        incomplete_p0_events: list[ClmIncompleteP0] = []
        for entry in profile_events:
            if entry.get("_d") == "P0":
                p0_count += 1
                raw_name = str(entry.get("n") or "").strip()
                clean_name = strip_realm_suffix(raw_name)
                raw_class = entry.get("c")
                new_class = canonical_clm_class(raw_class)
                active = True
                if not clean_name or not new_class:
                    incomplete_p0_events.append(ClmIncompleteP0(
                        event_id=_entry_uuid(entry), original_name=raw_name,
                        class_value=(raw_class if isinstance(raw_class, (int, str))
                                     and not isinstance(raw_class, bool) else None),
                        missing_fields=tuple(field for field, missing in (
                            ("name", not clean_name), ("class", not new_class),
                        ) if missing),
                    ))
                    warnings.add("INCOMPLETE_P0_IGNORED")
                    continue
                if normalized_name and character_key(clean_name) != character_key(normalized_name):
                    warnings.add("DATA_CONFLICT")
                    warnings.add(f"P0_NAME_CONFLICT:{normalized_name}/{clean_name}")
                if not normalized_name:
                    original_name, normalized_name = raw_name, clean_name
                if new_class and character_class and new_class != character_class:
                    warnings.add("DATA_CONFLICT")
                    warnings.add(f"P0_CLASS_CONFLICT:{character_class}/{new_class}")
                else:
                    if character_class is None:
                        p0_class_value = raw_class
                    character_class = new_class
            else:
                p1_count += 1
                if not active:
                    warnings.add("DATA_CONFLICT")
                active = False
        if not p0_count:
            warnings.add("P0_MISSING")
        elif not normalized_name:
            warnings.add("P0_IDENTITY_MISSING")
        histories.append(ClmGuidHistory(
            guid=guid, original_name=original_name, normalized_name=normalized_name,
            p0_class_value=p0_class_value, character_class=character_class,
            first_seen=min(known_times) if known_times else None,
            last_seen=max(known_times) if known_times else None,
            active_at_end=active, p0_count=p0_count, p1_count=p1_count,
            eternal_dkp_records=tuple(earnings_by_guid[guid]),
            warnings=tuple(sorted(warnings)),
            incomplete_p0_events=tuple(incomplete_p0_events),
        ))

    by_name: dict[str, list[ClmGuidHistory]] = {}
    for history in histories:
        if history.normalized_name:
            by_name.setdefault(character_key(history.normalized_name), []).append(history)
    groups = tuple(_multi_guid_group(items) for items in by_name.values() if len(items) > 1)
    return ClmIdentityAnalysis(
        "", str(roster_id), len(selected), tuple(histories),
        tuple(sorted(groups, key=lambda group: character_key(group.normalized_name))),
        technical_guids,
    )


def _multi_guid_group(histories: list[ClmGuidHistory]) -> ClmMultiGuidGroup:
    ordered = tuple(sorted(histories, key=lambda item: (
        item.first_seen if item.first_seen is not None else float("inf"), item.guid,
    )))
    pairwise: list[ClmGuidPair] = []
    suggestions: list[ClmGuidPair] = []
    conflicts: set[str] = set()
    for index, older in enumerate(ordered):
        for later_index in range(index + 1, len(ordered)):
            newer = ordered[later_index]
            pair = _compare_guid_histories(older, newer)
            pairwise.append(pair)
            conflicts.update(pair.conflicts)
            if later_index == index + 1 and pair.continuation_plausible:
                suggestions.append(pair)
    return ClmMultiGuidGroup(
        normalized_name=ordered[0].normalized_name,
        guid_histories=ordered,
        chronological_order=tuple(item.guid for item in ordered),
        pairwise=tuple(pairwise), continuation_suggestions=tuple(suggestions),
        conflicts=tuple(sorted(conflicts)),
    )


def _compare_guid_histories(older: ClmGuidHistory, newer: ClmGuidHistory) -> ClmGuidPair:
    conflicts: set[str] = set()
    if "DATA_CONFLICT" in older.warnings or "DATA_CONFLICT" in newer.warnings:
        conflicts.add("DATA_CONFLICT")
    if older.character_class and newer.character_class:
        if older.character_class != newer.character_class:
            conflicts.add("CLASS_CONFLICT")
    else:
        conflicts.add("CLASS_UNKNOWN")
    gap_days = overlap_days = None
    if (older.first_seen is None or older.last_seen is None
            or newer.first_seen is None or newer.last_seen is None):
        conflicts.add("TIME_UNKNOWN")
    elif older.last_seen >= newer.first_seen:
        conflicts.add("TIME_OVERLAP")
        overlap_days = max(0, min(older.last_seen, newer.last_seen) - newer.first_seen) / 86400
    else:
        gap_days = (newer.first_seen - older.last_seen) / 86400
    return ClmGuidPair(
        older.guid, newer.guid, gap_days, overlap_days, tuple(sorted(conflicts)),
        not conflicts,
    )


def _timestamp(entry: Mapping[object, object]) -> int | None:
    """CLM's _c is the Unix event time; _b, _e and _a break ties."""
    raw = entry.get("_c")
    if isinstance(raw, bool):
        return None
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def display_date(timestamp: int | None) -> str:
    if timestamp is None or timestamp <= 100000000:
        return "–"
    return datetime.fromtimestamp(timestamp).astimezone().strftime("%d.%m.%Y")


def _display_days(days: float | None) -> str:
    return "–" if days is None else f"{days:.6f}"


def format_analysis_report(analysis: ClmIdentityAnalysis) -> str:
    summary = analysis.summary
    lines = [
        f"CLM-Datenbank: {analysis.database_id}",
        f"DKP-Roster: {analysis.roster_id}",
        *(f"{key}: {value}" for key, value in summary.items()),
    ]
    for history in analysis.guid_histories:
        if history.incomplete_p0_count:
            for incomplete in history.incomplete_p0_events:
                lines.append(
                    f"Unvollständige P0 ignoriert: {history.guid} | "
                    f"Ereignis={incomplete.event_id} | "
                    f"Name={incomplete.original_name or '–'} | "
                    f"c={incomplete.class_value if incomplete.class_value not in (None, '') else '–'} | "
                    f"Fehlt={','.join(incomplete.missing_fields)}"
                )
    for ignored in analysis.ignored_technical_guids:
        lines.append(
            f"Technische GUID ignoriert: {ignored.guid} | "
            f"{ignored.warning} | Quellen={','.join(ignored.source_references)}"
        )
    for name in ("Annî", "Bämäräng"):
        lines.append(f"\n{name}:")
        histories = analysis.histories_for_name(name)
        if not histories:
            lines.append("  nicht gefunden")
            continue
        for history in histories:
            lines.append(
                f"  {history.guid} | {history.character_class or 'unbekannt'} | "
                f"P0.c={history.p0_class_value if history.p0_class_value is not None else '–'} | "
                f"{display_date(history.first_seen)} – {display_date(history.last_seen)} | "
                f"{'aktiv' if history.active_at_end else 'historisch'} | "
                f"P0={history.p0_count} P1={history.p1_count} | "
                f"DKP={history.eternal_dkp_total} | "
                f"Warnungen={','.join(history.warnings) or 'keine'}"
            )
        group = analysis.group_for_name(name)
        if group is not None:
            for pair in group.pairwise:
                lines.append(
                    f"  {pair.older_guid} -> {pair.newer_guid} | "
                    f"Gap={_display_days(pair.gap_days)} Tage | "
                    f"Overlap={_display_days(pair.overlap_days)} Tage | "
                    f"{'Fortsetzung plausibel' if pair.continuation_plausible else ','.join(pair.conflicts)}"
                )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only CLM Identity V2 analysis")
    parser.add_argument("source", type=Path)
    parser.add_argument("--guild", default="bierstube")
    parser.add_argument("--realm", default="stitches")
    parser.add_argument("--roster-id")
    args = parser.parse_args()
    print(format_analysis_report(analyze_clm_file(
        args.source, guild_name=args.guild, realm=args.realm, roster_id=args.roster_id,
    )))


if __name__ == "__main__":
    main()
