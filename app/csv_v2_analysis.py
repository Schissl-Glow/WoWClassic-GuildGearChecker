"""Read-only bulk analysis of Warcraft Logs Casts CSVs against a Lua-first V2 store."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping

from .csv_import import (
    exact_name_key, normalize_csv_raid_type, raid_csv_filename_metadata, read_raid_csv,
)
from .identity_v2 import IdentityV2Store, member_attendance_after_death
from .raid_attendance import RAID_TYPES, normalize_iso_date, validate_logs_url


class CsvV2AnalysisError(ValueError):
    """One selected CSV cannot be analyzed; no partial plan is returned."""


@dataclass(frozen=True)
class TemporalMatchIndicator:
    relation: str
    distance_days: int | None
    first_attendance_date: str | None
    last_attendance_date: str | None


def temporal_match_indicator(
    raid_date: str, first_attendance_date: str | None,
    last_attendance_date: str | None,
) -> TemporalMatchIndicator:
    """Explain temporal distance using attendance evidence only, never as a rule."""
    if not first_attendance_date or not last_attendance_date:
        return TemporalMatchIndicator(
            "NO_ATTENDANCE_DATA", None, first_attendance_date, last_attendance_date,
        )
    raid_day = date.fromisoformat(raid_date)
    first_day = date.fromisoformat(first_attendance_date)
    last_day = date.fromisoformat(last_attendance_date)
    if raid_day < first_day:
        return TemporalMatchIndicator(
            "BEFORE_FIRST_ATTENDANCE", (first_day - raid_day).days,
            first_attendance_date, last_attendance_date,
        )
    if raid_day > last_day:
        return TemporalMatchIndicator(
            "AFTER_LAST_ATTENDANCE", (raid_day - last_day).days,
            first_attendance_date, last_attendance_date,
        )
    return TemporalMatchIndicator(
        "WITHIN_KNOWN_RANGE", 0, first_attendance_date, last_attendance_date,
    )


@dataclass(frozen=True)
class CsvMemberOption:
    member_id: str
    name: str
    class_name: str
    raid_start_date: str | None
    death_date: str | None
    first_attendance: str | None
    last_attendance: str | None
    temporal: TemporalMatchIndicator | None = None


@dataclass(frozen=True)
class ClmBracketEvidence:
    before_date: str | None
    before_member_ids: tuple[str, ...]
    after_date: str | None
    after_member_ids: tuple[str, ...]

    @property
    def enclosed_member_id(self) -> str | None:
        if (self.before_date and self.after_date
                and len(self.before_member_ids) == len(self.after_member_ids) == 1
                and self.before_member_ids == self.after_member_ids):
            return self.before_member_ids[0]
        return None


@dataclass(frozen=True)
class CsvAmbiguousMemberMatch:
    source_path: Path
    raid_date: str
    raid_name: str
    csv_name: str
    options: tuple[CsvMemberOption, ...]
    excluded_options: tuple[CsvMemberOption, ...] = ()
    suggested_member_id: str | None = None
    clm_bracket: ClmBracketEvidence | None = None


@dataclass(frozen=True)
class CsvBlockedMemberMatch:
    source_path: Path
    raid_date: str
    raid_name: str
    csv_name: str
    excluded_options: tuple[CsvMemberOption, ...]
    reason: str = "Alle gleichnamigen Member sind nach ihrem Todesdatum unzulässig."
    options: tuple[CsvMemberOption, ...] = ()
    suggested_member_id: str | None = None


@dataclass(frozen=True)
class CsvExistingDeathConflict:
    member_id: str
    raid_id: str
    raid_date: str
    death_date: str


@dataclass(frozen=True)
class CsvNewMemberCandidate:
    name: str
    source_paths: tuple[Path, ...]
    class_name: str | None = None
    blocker: str = ""


@dataclass(frozen=True)
class CsvIgnoredOccurrence:
    source_path: Path
    raid_date: str
    name: str


@dataclass(frozen=True)
class CsvAttendanceCandidate:
    source_path: Path
    raid_date: str
    csv_name: str
    status: str  # RESOLVED, AMBIGUOUS, NEW_MEMBER_CANDIDATE, NO_ELIGIBLE_MEMBER
    member_id: str | None = None
    matching_raid_id: str | None = None
    existing_attendance: bool = False
    planned_attendance_type: str = "unknown"
    earlier_raid_start: bool = False
    match_reason: str | None = None
    clm_bracket: ClmBracketEvidence | None = None


@dataclass(frozen=True)
class CsvExistingRaidOption:
    raid_id: str
    raid_date: str
    raid_name: str
    participant_count: int
    overlap_count: int
    clm_raid_id: str | None = None


@dataclass(frozen=True)
class CsvRaidCandidate:
    source_path: Path
    raid_date: str
    raid_type: str
    raid_name: str
    report_url: str | None
    participant_names: tuple[str, ...]
    status: str  # NEW_RAID, POSSIBLE_DUPLICATE, KNOWN_RAID
    matching_raid_ids: tuple[str, ...] = ()
    existing_attendance_count: int = 0
    additional_attendance_count: int = 0
    existing_raid_options: tuple[CsvExistingRaidOption, ...] = ()
    automatic_clm_raid_ids: tuple[str, ...] = ()
    automatic_csv_raid_id: str | None = None


@dataclass(frozen=True)
class CsvRaidImportPlan:
    raid_candidates: tuple[CsvRaidCandidate, ...]
    attendance_candidates: tuple[CsvAttendanceCandidate, ...]
    resolved_member_matches: tuple[CsvAttendanceCandidate, ...]
    ambiguous_member_matches: tuple[CsvAmbiguousMemberMatch, ...]
    blocked_member_matches: tuple[CsvBlockedMemberMatch, ...]
    new_member_candidates: tuple[CsvNewMemberCandidate, ...]
    existing_death_conflicts: tuple[CsvExistingDeathConflict, ...]
    known_raids: tuple[CsvRaidCandidate, ...]
    possible_duplicates: tuple[CsvRaidCandidate, ...]
    warnings: tuple[str, ...]
    clm_bracket_matches: tuple[CsvAttendanceCandidate, ...] = ()
    ignored_occurrences: tuple[CsvIgnoredOccurrence, ...] = ()
    store_fingerprint: str | None = None
    source_fingerprints: tuple[tuple[Path, str], ...] = ()


def v2_store_fingerprint(store: IdentityV2Store) -> str:
    payload = json.dumps(store.to_payload(), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _character_name(raw: str) -> str:
    """Remove only a realm suffix; preserve every accent and the original base spelling."""
    return unicodedata.normalize("NFC", raw.strip().split("-", 1)[0].strip())


def _raid_type(value: str | None) -> str | None:
    return normalize_csv_raid_type(value, RAID_TYPES) if value else None


def _nearest_clm_evidence(
    name_key: str, raid_date: str,
    by_name: dict[str, dict[str, set[str]]],
    dates_by_name: dict[str, tuple[str, ...]],
) -> ClmBracketEvidence | None:
    """Use only GUID-backed Attendance of an actual CLM raid, never CSV evidence."""
    dates = dates_by_name.get(name_key, ())
    before_index = bisect_left(dates, raid_date) - 1
    after_index = bisect_right(dates, raid_date)
    before = dates[before_index] if before_index >= 0 else None
    after = dates[after_index] if after_index < len(dates) else None
    if before is None and after is None:
        return None
    evidence = by_name[name_key]
    return ClmBracketEvidence(
        before, tuple(sorted(evidence[before])) if before else (),
        after, tuple(sorted(evidence[after])) if after else (),
    )


def analyze_csv_raids_for_v2(
    store: IdentityV2Store, paths: Iterable[Path | str],
    *, raid_type_overrides: Mapping[Path, str] | None = None,
) -> CsvRaidImportPlan:
    """Analyze all selected files before returning one immutable, unapplied plan."""
    store.validate()
    sources = tuple(sorted({Path(path).resolve() for path in paths},
                           key=lambda path: (path.name.casefold(), str(path).casefold())))
    if not sources:
        raise CsvV2AnalysisError("Keine CSV-Dateien ausgewählt.")
    try:
        source_fingerprints = tuple(
            (source, hashlib.sha256(source.read_bytes()).hexdigest())
            for source in sources)
    except OSError as exc:
        raise CsvV2AnalysisError(f"CSV-Datei kann nicht gelesen werden: {exc}") from exc
    store_fingerprint = v2_store_fingerprint(store)
    overrides = {Path(path).resolve(): raid_type
                 for path, raid_type in (raid_type_overrides or {}).items()}
    if set(overrides) - set(sources) or any(
            raid_type not in RAID_TYPES for raid_type in overrides.values()):
        raise CsvV2AnalysisError("Ungültiger Raid-Typ-Override oder unbekannte CSV-Quelle.")

    members_by_name: dict[str, list] = defaultdict(list)
    for member in store.members:
        members_by_name[exact_name_key(member.name)].append(member)
    raids_by_date: dict[str, list] = defaultdict(list)
    for raid in store.raids:
        raids_by_date[raid.date].append(raid)
    attendance_by_raid: dict[str, set[str]] = defaultdict(set)
    attendance_dates: dict[str, list[str]] = defaultdict(list)
    raid_by_id = {raid.raidId: raid for raid in store.raids}
    raid_dates = {raid.raidId: raid.date for raid in store.raids}
    member_by_id = {member.memberId: member for member in store.members}
    clm_by_name: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    existing_death_conflicts: list[CsvExistingDeathConflict] = []
    for entry in store.attendance:
        attendance_by_raid[entry.raidId].add(entry.memberId)
        attendance_dates[entry.memberId].append(raid_dates[entry.raidId])
        member = member_by_id[entry.memberId]
        if raid_by_id[entry.raidId].clmRaidId and entry.clmGuid:
            clm_by_name[exact_name_key(member.name)][raid_dates[entry.raidId]].add(
                member.memberId
            )
        if member_attendance_after_death(member, raid_dates[entry.raidId]):
            existing_death_conflicts.append(CsvExistingDeathConflict(
                member.memberId, entry.raidId, raid_dates[entry.raidId],
                member.deathDate,
            ))
    clm_dates_by_name = {
        key: tuple(sorted(dates)) for key, dates in clm_by_name.items()
    }
    options_by_id = {
        member.memberId: CsvMemberOption(
            member.memberId, member.name, member.className, member.raidStartDate,
            member.deathDate,
            min(attendance_dates[member.memberId]) if attendance_dates[member.memberId] else None,
            max(attendance_dates[member.memberId]) if attendance_dates[member.memberId] else None,
        ) for member in store.members
    }

    raids: list[CsvRaidCandidate] = []
    attendance: list[CsvAttendanceCandidate] = []
    ambiguities: list[CsvAmbiguousMemberMatch] = []
    blocked_matches: list[CsvBlockedMemberMatch] = []
    ignored_occurrences: list[CsvIgnoredOccurrence] = []
    new_names: dict[str, tuple[str, set[Path]]] = {}
    new_classes: dict[str, set[str]] = defaultdict(set)
    warnings: list[str] = []
    for conflict in existing_death_conflicts:
        warnings.append(
            f"Bestehende Attendance: {conflict.member_id} in Raid {conflict.raid_id} "
            f"am {conflict.raid_date} liegt nach Todesdatum {conflict.death_date}."
        )
    earlier_csv: list[CsvRaidCandidate] = []

    for source in sources:
        try:
            parsed = read_raid_csv(source)
            filename = raid_csv_filename_metadata(source)
            raw_date = parsed.metadata.raid_date or filename.raid_date
            if not raw_date:
                raise ValueError("Raid-Datum fehlt in Metadaten und Dateiname.")
            raid_date = str(normalize_iso_date(raw_date))
            if (parsed.metadata.raid_date and filename.raid_date
                    and str(normalize_iso_date(filename.raid_date)) != raid_date):
                warnings.append(f"{source.name}: Metadatum weicht vom Dateinamen ab.")
            raw_type = parsed.metadata.raid_type or filename.raid_type
            if not raw_type:
                raise ValueError("Raid-Typ fehlt in Metadaten und Dateiname.")
            raid_name = unicodedata.normalize("NFC", raw_type.strip())
            detected_type = _raid_type(raw_type)
            raid_type = detected_type or raid_name
            if source in overrides:
                raid_type = raid_name = overrides[source]
            if detected_type is None:
                warnings.append(f"{source.name}: unbekannter Raid-Typ {raid_type!r}.")
            if (parsed.metadata.raid_type and filename.raid_type
                    and detected_type != _raid_type(filename.raid_type)):
                warnings.append(f"{source.name}: Raid-Typ weicht vom Dateinamen ab.")
            report_url = validate_logs_url(parsed.metadata.report_url or "") or None
            if not parsed.names:
                raise ValueError("CSV enthält keine Teilnehmernamen.")
        except (OSError, UnicodeError, ValueError) as exc:
            raise CsvV2AnalysisError(f"{source}: {exc}") from exc

        if parsed.duplicates:
            warnings.append(f"{source.name}: {len(parsed.duplicates)} doppelte Namenszeilen ignoriert.")
        names: list[str] = []
        classes_by_raw_name = dict(parsed.classes_by_name)
        classes_by_normalized_name: dict[str, set[str]] = defaultdict(set)
        seen_names: set[str] = set()
        for raw_name in parsed.names:
            name = _character_name(raw_name)
            key = exact_name_key(name)
            csv_class = classes_by_raw_name.get(exact_name_key(raw_name))
            if csv_class:
                classes_by_normalized_name[key].add(csv_class)
            if not key or key in seen_names:
                if key in seen_names:
                    warnings.append(f"{source.name}: mehrfacher Charaktername {name!r} ignoriert.")
                continue
            seen_names.add(key)
            names.append(name)
        if not names:
            raise CsvV2AnalysisError(f"{source}: keine gültigen Charakternamen.")

        occurrences: list[CsvAttendanceCandidate] = []
        for name in names:
            if store.is_csv_character_ignored(name):
                ignored_occurrences.append(CsvIgnoredOccurrence(source, raid_date, name))
                occurrences.append(CsvAttendanceCandidate(
                    source, raid_date, name, "IGNORED",
                ))
                continue
            matches = members_by_name.get(exact_name_key(name), [])
            allowed, excluded = [], []
            for member in matches:
                (excluded if member_attendance_after_death(member, raid_date)
                 else allowed).append(member)
            for member in excluded:
                warnings.append(
                    f"{source.name}: {member.memberId} ({name}) wegen Todesdatum "
                    f"{member.deathDate} für Raid {raid_date} unzulässig."
                )
            if len(allowed) == 1:
                member = allowed[0]
                csv_classes = classes_by_normalized_name[exact_name_key(name)]
                if csv_classes and member.className not in csv_classes:
                    warnings.append(
                        f"{source.name}: CSV-Klasse für {name!r} widerspricht "
                        f"V2-Klasse {member.className!r}."
                    )
                occurrences.append(CsvAttendanceCandidate(
                    source, raid_date, name, "RESOLVED", member.memberId,
                    earlier_raid_start=(member.raidStartDate is not None
                                        and raid_date < member.raidStartDate),
                    match_reason=("EXACT_NAME" if len(matches) == 1
                                  else "DEATH_FILTER"),
                ))
            elif len(allowed) > 1:
                bracket = _nearest_clm_evidence(
                    exact_name_key(name), raid_date,
                    clm_by_name, clm_dates_by_name,
                )
                enclosed = bracket.enclosed_member_id if bracket else None
                if enclosed in {member.memberId for member in allowed}:
                    member = member_by_id[enclosed]
                    occurrences.append(CsvAttendanceCandidate(
                        source, raid_date, name, "RESOLVED", enclosed,
                        earlier_raid_start=(member.raidStartDate is not None
                                            and raid_date < member.raidStartDate),
                        match_reason="CLM_BRACKET", clm_bracket=bracket,
                    ))
                    continue
                options = tuple(replace(
                    options_by_id[member.memberId],
                    temporal=temporal_match_indicator(
                        raid_date, options_by_id[member.memberId].first_attendance,
                        options_by_id[member.memberId].last_attendance,
                    ),
                ) for member in allowed)
                excluded_options = tuple(options_by_id[member.memberId]
                                         for member in excluded)
                distances = [(option.temporal.distance_days, option.member_id)
                             for option in options if option.temporal.distance_days is not None]
                minimum = min((distance for distance, _member_id in distances),
                              default=None)
                plausible = [member_id for distance, member_id in distances
                             if distance == minimum]
                ambiguities.append(CsvAmbiguousMemberMatch(
                    source, raid_date, raid_name, name, options,
                    excluded_options, plausible[0] if len(plausible) == 1 else None,
                    bracket,
                ))
                occurrences.append(CsvAttendanceCandidate(
                    source, raid_date, name, "AMBIGUOUS",
                    earlier_raid_start=any(
                        option.raid_start_date is not None
                        and raid_date < option.raid_start_date for option in options
                    ),
                ))
            elif matches:
                blocked_matches.append(CsvBlockedMemberMatch(
                    source, raid_date, raid_name, name,
                    tuple(options_by_id[member.memberId] for member in excluded),
                ))
                occurrences.append(CsvAttendanceCandidate(
                    source, raid_date, name, "NO_ELIGIBLE_MEMBER",
                ))
            else:
                key = exact_name_key(name)
                if key not in new_names:
                    new_names[key] = (name, set())
                new_names[key][1].add(source)
                new_classes[key].update(classes_by_normalized_name[key])
                occurrences.append(CsvAttendanceCandidate(
                    source, raid_date, name, "NEW_MEMBER_CANDIDATE",
                ))

        resolved_ids = {item.member_id for item in occurrences if item.member_id}
        matches: list[tuple[object, bool, int]] = []
        for existing in raids_by_date[raid_date]:
            existing_type = _raid_type(existing.raidType or existing.name)
            same_type = (existing_type == _raid_type(raid_type)
                         if existing_type and _raid_type(raid_type) else
                         exact_name_key(existing.name) == exact_name_key(raid_type))
            overlap = len(resolved_ids & attendance_by_raid[existing.raidId])
            source_match = (source.name in existing.csvSourceFiles
                            or any(item.sourceFileName == source.name
                                   for item in existing.csvSources))
            if (same_type or overlap or existing.clmRaidId
                    or source_match
                    or (report_url and report_url in existing.csvReportUrls)):
                matches.append((existing, same_type, overlap))
        matching_ids = tuple(raid.raidId for raid, _same_type, _overlap in matches)
        best = max(matches, key=lambda item: (item[1], item[2]), default=None)
        existing_ids = attendance_by_raid[best[0].raidId] if best else set()
        existing_count = sum(item.member_id in existing_ids for item in occurrences
                             if item.member_id is not None)
        additional_count = len(occurrences) - existing_count
        clm_matches = [(raid, same_type, overlap)
                       for raid, same_type, overlap in matches if raid.clmRaidId]
        url_matches = [raid.raidId for raid, _same_type, _overlap in clm_matches
                       if report_url and report_url in raid.csvReportUrls
                       and (source not in overrides or _same_type)]
        if url_matches:
            automatic_clm_ids = tuple(url_matches)
        else:
            strong_clm = [raid.raidId for raid, same_type, overlap in clm_matches
                          if same_type and overlap > 0]
            automatic_clm_ids = (tuple(strong_clm)
                                 if len(clm_matches) == len(strong_clm) == 1 else ())
        csv_matches = [raid for raid, _same_type, _overlap in matches
                       if not raid.clmRaidId and (raid.csvSourceFiles or raid.csvSources)]
        csv_url_matches = [raid for raid in csv_matches
                           if report_url and report_url in raid.csvReportUrls]
        if csv_url_matches:
            automatic_csv_id = (csv_url_matches[0].raidId
                                if len(csv_url_matches) == 1 else None)
        else:
            csv_source_matches = [
                raid for raid in csv_matches
                if (source.name in raid.csvSourceFiles
                    or any(item.sourceFileName == source.name for item in raid.csvSources))
                and _raid_type(raid.raidType or raid.name) == _raid_type(raid_type)
                and (not report_url or not raid.csvReportUrls)
            ]
            automatic_csv_id = (csv_source_matches[0].raidId
                                if len(csv_source_matches) == 1 else None)
        if csv_url_matches and automatic_clm_ids:
            automatic_clm_ids = ()
            automatic_csv_id = None
        cross_source = any(
            earlier.raid_date == raid_date
            and (earlier.raid_type == raid_type
                 or (report_url and earlier.report_url == report_url))
            for earlier in earlier_csv
        )
        status = ("KNOWN_RAID" if automatic_clm_ids or automatic_csv_id else
                  "POSSIBLE_DUPLICATE" if matches or cross_source else "NEW_RAID")
        raid_candidate = CsvRaidCandidate(
            source, raid_date, raid_type, raid_name, report_url, tuple(names), status,
            matching_ids, existing_count, additional_count,
            tuple(CsvExistingRaidOption(
                raid.raidId, raid.date, raid.name,
                len(attendance_by_raid[raid.raidId]), overlap, raid.clmRaidId,
            ) for raid, _same_type, overlap in matches),
            automatic_clm_ids, automatic_csv_id,
        )
        raids.append(raid_candidate)
        earlier_csv.append(raid_candidate)
        for item in occurrences:
            related_raid = best[0].raidId if best else None
            exists = bool(related_raid and item.member_id in existing_ids)
            attendance.append(replace(
                item, matching_raid_id=related_raid, existing_attendance=exists,
                earlier_raid_start=item.earlier_raid_start and not exists,
            ))

    new_members_list: list[CsvNewMemberCandidate] = []
    for key in sorted(new_names):
        name, paths = new_names[key]
        classes = new_classes[key]
        if len(classes) > 1:
            warnings.append(f"{name}: widersprüchliche CSV-Klassen; Neuanlage blockiert.")
        class_name = next(iter(classes)) if len(classes) == 1 else None
        blocker = ("Widersprüchliche CSV-Klassen müssen manuell geklärt werden."
                   if len(classes) > 1 else "")
        new_members_list.append(CsvNewMemberCandidate(
            name, tuple(sorted(paths)), class_name, blocker,
        ))
    new_members = tuple(new_members_list)
    return CsvRaidImportPlan(
        tuple(raids), tuple(attendance),
        tuple(item for item in attendance if item.status == "RESOLVED"),
        tuple(ambiguities), tuple(blocked_matches), new_members,
        tuple(existing_death_conflicts),
        tuple(item for item in raids if item.status == "KNOWN_RAID"),
        tuple(item for item in raids if item.status == "POSSIBLE_DUPLICATE"),
        tuple(warnings),
        tuple(item for item in attendance if item.match_reason == "CLM_BRACKET"),
        tuple(ignored_occurrences),
        store_fingerprint, source_fingerprints,
    )
