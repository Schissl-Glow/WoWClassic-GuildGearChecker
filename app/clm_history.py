"""Read-only CLM raid-history replay and persisted Eternal-DKP projection."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Iterable, Mapping

try:
    from .clm_matching import strip_realm_suffix
    from .clm_models import ClmIntegrationError
    from .clm_replay import (
        _display_number, _entry_sort_key, _entry_uuid, _guid, _guid_list,
        _inflate_config, _sequence, guid_key,
    )
    from .raid_type_detection import detect_raid_type, raid_type_mentions
except ImportError:
    from clm_matching import strip_realm_suffix  # type: ignore
    from clm_models import ClmIntegrationError  # type: ignore
    from clm_replay import (  # type: ignore
        _display_number, _entry_sort_key, _entry_uuid, _guid, _guid_list,
        _inflate_config, _sequence, guid_key,
    )
    from raid_type_detection import detect_raid_type, raid_type_mentions  # type: ignore


Guid = tuple[object, ...]
EARNING_KINDS = {"EARNED_RAID", "EARNED_BENCH", "EARNED_OTHER", "CORRECTION"}


def _guids(value: object) -> list[Guid]:
    """Accept both CLM's single-GUID and list-of-GUID encodings."""
    values = _guid_list(value)
    if values:
        return values
    single = _guid(value)
    return [single] if single is not None else []


def local_raid_date(timestamp: int) -> str:
    if timestamp <= 100000000:
        return ""
    return datetime.fromtimestamp(timestamp).astimezone().date().isoformat()


def classify_manual_dkp(text: object, value: float) -> str:
    label = str(text or "").strip().casefold()
    if "dkp switch" in label or "transfer" in label:
        return "TRANSFER"
    if "bench" in label or "bank" in label:
        return "EARNED_BENCH" if value > 0 else "CORRECTION"
    if value < 0:
        return "PENALTY"
    if value > 0 and any(token in label for token in ("bonus", "award", "earned")):
        return "EARNED_OTHER"
    return "IGNORED" if math.isclose(value, 0.0) else "UNRESOLVED"


def detected_raid_types(name: object) -> tuple[str, ...]:
    if detect_raid_type(name) is None:
        return ()
    return tuple(raid_type for _position, raid_type in raid_type_mentions(name))


def _roster_scoped_entries(ledger: object, roster_id: str) -> list[Mapping[object, object]]:
    """Keep only the selected roster's events and the profiles they reference.

    CLM stores session-followup events under the session event ID, while the
    session-creation event itself references the roster ID.  Resolve that
    boundary before replaying events so another roster cannot contribute a
    session, participant, or unresolved character to the preview.
    """
    all_entries = [entry for entry in _sequence(ledger) if isinstance(entry, Mapping)]
    all_entries.sort(key=_entry_sort_key)
    selected_roster = str(roster_id)
    session_ids = {
        _entry_uuid(entry)
        for entry in all_entries
        if str(entry.get("_d") or "") == "AC"
        and str(entry.get("r") or "") == selected_roster
    }
    scoped = [
        entry for entry in all_entries
        if str(entry.get("_d") or "") != "P0"
        and (
            _entry_uuid(entry) in session_ids
            or str(entry.get("r") or "") == selected_roster
            or str(entry.get("r") or "") in session_ids
        )
    ]
    scoped_ids = {_entry_uuid(entry) for entry in scoped}
    scoped.extend(
        entry for entry in all_entries
        if str(entry.get("_d") or "") == "IGN"
        and str(entry.get("ref") or "") in scoped_ids
    )

    referenced_guids = {
        guid
        for entry in scoped
        for field in ("g", "p", "s", "j", "l")
        for guid in _guids(entry.get(field))
    }
    scoped.extend(
        entry for entry in all_entries
        if str(entry.get("_d") or "") == "P0"
        and (guid := _guid(entry.get("g"))) in referenced_guids
    )
    scoped.sort(key=_entry_sort_key)
    return scoped


@dataclass(frozen=True)
class ClmEarning:
    event_id: str
    clm_raid_id: str
    character_guid: str
    character_name: str
    value: int | float
    kind: str
    timestamp: int
    description: str = ""


@dataclass
class ClmRaidHistory:
    clm_raid_id: str
    roster_id: str
    name: str
    start_timestamp: int
    date: str
    raid_types: tuple[str, ...]
    end_timestamp: int | None = None
    participant_guids: set[str] = field(default_factory=set)
    bench_guids: set[str] = field(default_factory=set)
    earnings: list[ClmEarning] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> int | None:
        if self.end_timestamp is None or self.end_timestamp < self.start_timestamp:
            return None
        return self.end_timestamp - self.start_timestamp

    @property
    def combined(self) -> bool:
        return len(self.raid_types) != 1


@dataclass(frozen=True)
class ClmHistoryProjection:
    characters: Mapping[str, str]
    character_classes: Mapping[str, int | str]
    raids: tuple[ClmRaidHistory, ...]
    standalone_earnings: tuple[ClmEarning, ...]
    unresolved_events: tuple[str, ...]
    ignored_event_ids: tuple[str, ...]

    @property
    def earnings(self) -> tuple[ClmEarning, ...]:
        return tuple(
            earning for raid in self.raids for earning in raid.earnings
        ) + self.standalone_earnings


@dataclass(frozen=True)
class EternalDkpRecord:
    event_id: str
    member_id: str
    character_name: str
    value: int | float
    kind: str
    clm_raid_id: str = ""
    raid_id: str = ""
    timestamp: int = 0
    description: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "EternalDkpRecord":
        kind = str(data.get("kind") or "")
        if kind not in EARNING_KINDS:
            raise ValueError(f"Ungültige Eternal-DKP-Klassifikation: {kind}")
        return cls(
            event_id=str(data.get("eventId") or ""),
            member_id=str(data.get("memberId") or ""),
            character_name=str(data.get("characterName") or ""),
            value=float(data.get("value") or 0), kind=kind,
            clm_raid_id=str(data.get("clmRaidId") or ""),
            raid_id=str(data.get("raidId") or ""),
            timestamp=int(data.get("timestamp") or 0),
            description=str(data.get("description") or ""),
        )

    def to_dict(self) -> dict[str, object]:
        data = {
            "eventId": self.event_id, "memberId": self.member_id,
            "characterName": self.character_name, "value": self.value,
            "kind": self.kind, "clmRaidId": self.clm_raid_id,
            "raidId": self.raid_id, "timestamp": self.timestamp,
            "description": self.description,
        }
        return {key: value for key, value in data.items() if value not in {"", 0}}


@dataclass
class EternalDkpState:
    records: list[EternalDkpRecord] = field(default_factory=list)
    database_id: str = ""
    roster_id: str = ""
    ignored_character_guids: set[str] = field(default_factory=set)
    source_modified_at: float | None = None
    synced_at: str = ""

    @classmethod
    def from_dict(cls, data: object) -> "EternalDkpState":
        if not isinstance(data, Mapping):
            return cls()
        raw_records = data.get("records", [])
        if not isinstance(raw_records, list):
            raise ValueError("Ungültige Eternal-DKP-Datensätze.")
        records = [EternalDkpRecord.from_dict(item) for item in raw_records if isinstance(item, Mapping)]
        if len({record.event_id for record in records}) != len(records):
            raise ValueError("Doppelte Eternal-DKP-Ereignis-ID.")
        return cls(
            records=records, database_id=str(data.get("databaseId") or ""),
            roster_id=str(data.get("rosterId") or ""),
            ignored_character_guids={
                str(value) for value in data.get("ignoredCharacterGuids", [])
                if str(value)
            } if isinstance(data.get("ignoredCharacterGuids"), list) else set(),
            source_modified_at=(float(data["sourceModifiedAt"])
                                if data.get("sourceModifiedAt") is not None else None),
            synced_at=str(data.get("syncedAt") or ""),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "records": [record.to_dict() for record in self.records],
            "databaseId": self.database_id, "rosterId": self.roster_id,
            "ignoredCharacterGuids": sorted(self.ignored_character_guids),
            "sourceModifiedAt": self.source_modified_at, "syncedAt": self.synced_at,
        }

    def replace_records(self, records: Iterable[EternalDkpRecord], **metadata: object) -> None:
        unique = {record.event_id: record for record in records}
        self.records = list(unique.values())
        self.database_id = str(metadata.get("database_id") or self.database_id)
        self.roster_id = str(metadata.get("roster_id") or self.roster_id)
        self.source_modified_at = metadata.get("source_modified_at")  # type: ignore[assignment]
        self.synced_at = str(metadata.get("synced_at") or self.synced_at)

    def character_totals(self) -> dict[str, tuple[int | float, int | float]]:
        totals: dict[str, list[float]] = {}
        for record in self.records:
            values = totals.setdefault(record.member_id, [0.0, 0.0])
            values[0] += float(record.value)
            if record.kind in {"EARNED_BENCH", "CORRECTION"}:
                values[1] += float(record.value)
        return {
            member_id: (_display_number(values[0]), _display_number(values[1]))
            for member_id, values in totals.items()
        }

    def player_totals(self, members: Iterable[object]) -> dict[str, tuple[int | float, int | float]]:
        member_to_player = {
            str(getattr(member, "id", "")): str(getattr(member, "playerId", "") or "")
            for member in members
        }
        totals: dict[str, list[float]] = {}
        for member_id, (eternal, bench) in self.character_totals().items():
            player_id = member_to_player.get(member_id, "")
            if not player_id:
                continue
            values = totals.setdefault(player_id, [0.0, 0.0])
            values[0] += float(eternal)
            values[1] += float(bench)
        return {
            player_id: (_display_number(values[0]), _display_number(values[1]))
            for player_id, values in totals.items()
        }


def replay_clm_history(ledger: object, roster_id: str) -> ClmHistoryProjection:
    entries = _roster_scoped_entries(ledger, roster_id)
    ignored = {str(entry.get("ref") or "") for entry in entries if entry.get("_d") == "IGN"}
    profiles: dict[Guid, str] = {}
    profile_classes: dict[Guid, int | str] = {}
    raids: dict[str, ClmRaidHistory] = {}
    active: dict[str, set[Guid]] = {}
    standby: dict[str, set[Guid]] = {}
    standalone: list[ClmEarning] = []
    unresolved: list[str] = []
    bench_balance: dict[tuple[str, Guid], float] = {}

    def name_for(guid: Guid) -> str:
        return strip_realm_suffix(profiles.get(guid, guid_key(guid)))

    def earning(entry: Mapping[object, object], raid_id: str, guid: Guid,
                value: float, kind: str) -> ClmEarning:
        return ClmEarning(
            event_id=f"{_entry_uuid(entry)}:{guid_key(guid)}:{kind}",
            clm_raid_id=raid_id, character_guid=guid_key(guid),
            character_name=name_for(guid), value=_display_number(value), kind=kind,
            timestamp=int(entry.get("_c") or 0), description=str(entry.get("t") or ""),
        )

    for entry in entries:
        event_id = _entry_uuid(entry)
        opcode = str(entry.get("_d") or "")
        if opcode == "IGN" or event_id in ignored:
            continue
        if opcode == "P0":
            guid = _guid(entry.get("g"))
            if guid is not None:
                profiles[guid] = str(entry.get("n") or "")
                class_value = entry.get("c")
                if isinstance(class_value, (int, str)):
                    profile_classes[guid] = class_value
            continue
        if opcode == "AC" and str(entry.get("r") or "") == str(roster_id):
            raid_id = event_id
            timestamp = int(entry.get("_c") or 0)
            name = str(entry.get("n") or "")
            raids[raid_id] = ClmRaidHistory(
                raid_id, str(roster_id), name, timestamp, local_raid_date(timestamp),
                detected_raid_types(name),
            )
            active[raid_id] = set()
            standby[raid_id] = set()
            continue
        raid_id = str(entry.get("r") or "")
        raid = raids.get(raid_id)
        if opcode == "AS" and raid is not None:
            active[raid_id] = set(_guids(entry.get("p")))
            standby[raid_id] = set(_guids(entry.get("s")))
            raid.participant_guids.update(guid_key(guid) for guid in active[raid_id])
            raid.bench_guids.update(guid_key(guid) for guid in standby[raid_id])
        elif opcode == "AU" and raid is not None:
            for guid in _guids(entry.get("j")):
                active[raid_id].add(guid); standby[raid_id].discard(guid)
                raid.participant_guids.add(guid_key(guid))
            for guid in _guids(entry.get("l")):
                active[raid_id].discard(guid)
            for guid in _guids(entry.get("s")):
                standby[raid_id].add(guid); active[raid_id].discard(guid)
                raid.bench_guids.add(guid_key(guid))
        elif opcode == "AE" and raid is not None:
            raid.end_timestamp = int(entry.get("_c") or 0)
        elif opcode == "DR" and raid is not None and not bool(entry.get("n")):
            value = float(entry.get("v") or 0)
            if value <= 0:
                unresolved.append(event_id)
                continue
            for guid in active.get(raid_id, set()):
                raid.earnings.append(earning(entry, raid_id, guid, value, "EARNED_RAID"))
            if bool(entry.get("s")):
                config = _inflate_config(entry.get("c")) if entry.get("c") else {}
                multiplier = float(config.get("benchMultiplier", 1) or 1)
                for guid in standby.get(raid_id, set()):
                    raid.earnings.append(earning(
                        entry, raid_id, guid, value * multiplier, "EARNED_BENCH",
                    ))
        elif opcode == "DM" and str(entry.get("r") or "") == str(roster_id) and not bool(entry.get("n")):
            value = float(entry.get("v") or 0)
            kind = classify_manual_dkp(entry.get("t"), value)
            dm_types = set(detected_raid_types(entry.get("t")))
            dm_date = local_raid_date(int(entry.get("_c") or 0))
            candidates = [
                item for item in raids.values()
                if item.date == dm_date and (not dm_types or dm_types.intersection(item.raid_types))
            ]
            target_raid = candidates[0] if len(candidates) == 1 else None
            for guid in _guids(entry.get("p")):
                if kind == "EARNED_BENCH":
                    bench_balance[(str(entry.get("t") or "").casefold(), guid)] = (
                        bench_balance.get((str(entry.get("t") or "").casefold(), guid), 0.0) + value
                    )
                    record = earning(
                        entry, target_raid.clm_raid_id if target_raid else "", guid, value, kind,
                    )
                    (target_raid.earnings if target_raid else standalone).append(record)
                    if target_raid and guid_key(guid) not in target_raid.participant_guids:
                        target_raid.bench_guids.add(guid_key(guid))
                elif kind == "CORRECTION":
                    key = (str(entry.get("t") or "").casefold(), guid)
                    if bench_balance.get(key, 0.0) >= abs(value):
                        bench_balance[key] += value
                        record = earning(
                            entry, target_raid.clm_raid_id if target_raid else "", guid,
                            value, kind,
                        )
                        (target_raid.earnings if target_raid else standalone).append(record)
                    else:
                        unresolved.append(event_id)
                elif kind == "EARNED_OTHER":
                    standalone.append(earning(entry, "", guid, value, kind))
                elif kind == "UNRESOLVED":
                    unresolved.append(event_id)
        # II/IE and all current-balance-only operations intentionally have no effect.

    characters = {guid_key(guid): strip_realm_suffix(name) for guid, name in profiles.items()}
    for raid in raids.values():
        if raid.combined:
            raid.warnings.append("combined")
    return ClmHistoryProjection(
        characters=characters,
        character_classes={guid_key(guid): value for guid, value in profile_classes.items()},
        raids=tuple(sorted(raids.values(), key=lambda item: (item.start_timestamp, item.clm_raid_id))),
        standalone_earnings=tuple(standalone), unresolved_events=tuple(dict.fromkeys(unresolved)),
        ignored_event_ids=tuple(sorted(ignored)),
    )
