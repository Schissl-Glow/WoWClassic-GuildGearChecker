"""Deterministisches, read-only Replay des ClassicLootManager-Ledgers."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Protocol

try:
    from .clm_models import ClmCharacterBalance, ClmIntegrationError
except ImportError:
    from clm_models import ClmCharacterBalance, ClmIntegrationError  # type: ignore


class LedgerFixtureRequiredError(ClmIntegrationError):
    """Kompatibilitätsfehler des früheren, fixturelosen Platzhalters."""


@dataclass(frozen=True)
class LedgerReplayRequest:
    database_id: str
    roster_id: str
    ledger: object


@dataclass(frozen=True)
class LedgerReplayResult:
    balances: tuple[ClmCharacterBalance, ...]
    processed_entries: int
    roster_name: str = ""
    roster_id: str = ""
    point_type: int = -1
    active: bool = False
    ignored_entries: int = 0


class LedgerReplayer(Protocol):
    def replay(self, request: LedgerReplayRequest) -> LedgerReplayResult:
        ...


Guid = tuple[object, ...]


def _sequence(value: object) -> list[object]:
    if isinstance(value, Mapping):
        keys = sorted(key for key in value if isinstance(key, int))
        return [value[key] for key in keys]
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _guid(value: object) -> Guid | None:
    parts = _sequence(value)
    if not parts:
        return None
    normalized = tuple(
        tuple(_sequence(part)) if isinstance(part, Mapping) else part
        for part in parts
    )
    if not any(normalized):
        return None
    return normalized


def _guid_list(value: object) -> list[Guid]:
    result: list[Guid] = []
    for item in _sequence(value):
        guid = _guid(item)
        if guid is not None:
            result.append(guid)
    return result


def _entry_uuid(entry: Mapping[object, object]) -> str:
    return "-".join(str(entry.get(key, 0)) for key in ("_c", "_b", "_e", "_a"))


def _entry_sort_key(entry: Mapping[object, object]) -> tuple[object, ...]:
    return tuple(entry.get(key, 0) for key in ("_c", "_b", "_e", "_a"))


def _lua_round(value: float, decimals: int) -> float:
    factor = 10 ** decimals
    return math.floor(value * factor + 0.5) / factor


def _display_number(value: float) -> int | float:
    if math.isclose(value, round(value), abs_tol=1e-9):
        return int(round(value))
    return value


_CONFIG_FIELDS = (
    "auctionType", "itemValueMode", "zeroSumBank", "zeroSumBankInflation",
    "auctionTime", "antiSnipe", "allowBelowMinStandings", "bossKillBonus",
    "bossKillBonusValue", "onTimeBonus", "onTimeBonusValue",
    "raidCompletionBonus", "raidCompletionBonusValue", "intervalBonus",
    "intervalBonusTime", "intervalBonusValue", "hardCap", "weeklyCap",
    "weeklyReset", "roundDecimals", "minimalIncrement", "autoBenchLeavers",
    "autoAwardIncludeBench", "autoAwardOnlineOnly", "autoAwardSameZoneOnly",
    "selfBenchSubscribe", "tax", "minimumPoints", "minGP", "namedButtons",
    "dynamicValue", "benchMultiplier", "useOS", "roundPR", "baseAlways",
    "allInAlways", "allowEqualMax", "allowCancelPass", "rollTime",
    "multiplyTime", "basePoints", "baseSpent", "always0",
)


def _default_config() -> dict[str, object]:
    return {
        "zeroSumBank": False,
        "zeroSumBankInflation": 0.0,
        "hardCap": 0.0,
        "weeklyCap": 0.0,
        "weeklyReset": 0,
        "roundDecimals": 10,
        "autoBenchLeavers": False,
        "autoAwardIncludeBench": True,
        "benchMultiplier": 1.0,
        "minGP": 1.0,
        "basePoints": 0.0,
        "baseSpent": 0.0,
    }


def _inflate_config(value: object) -> dict[str, object]:
    config = _default_config()
    for key, item in zip(_CONFIG_FIELDS, _sequence(value)):
        config[key] = item
    return config


@dataclass
class _Profile:
    name: str
    main: Guid | None = None
    alts: set[Guid] = field(default_factory=set)
    locked: bool = False


@dataclass
class _Roster:
    uid: object
    name: str
    point_type: int
    config: dict[str, object] = field(default_factory=_default_config)
    standings: dict[Guid, float] = field(default_factory=dict)
    in_roster: set[Guid] = field(default_factory=set)
    weekly_gains: dict[Guid, dict[int, float]] = field(default_factory=dict)

    def add(self, guid: Guid) -> None:
        if guid in self.in_roster:
            return
        self.standings[guid] = 0.0
        self.weekly_gains[guid] = {}
        self.in_roster.add(guid)

    def remove(self, guid: Guid) -> None:
        self.standings.pop(guid, None)
        self.weekly_gains.pop(guid, None)
        self.in_roster.discard(guid)

    def round(self, value: float) -> float:
        return _lua_round(value, int(self.config.get("roundDecimals", 10)))

    def update(self, guid: Guid, value: float, timestamp: int) -> None:
        standings = self.standings.get(guid, 0.0)
        if value > 0:
            hard_cap = float(self.config.get("hardCap", 0) or 0)
            if hard_cap > 0:
                if standings >= hard_cap:
                    return
                value = min(value, hard_cap - standings)
            weekly_cap = float(self.config.get("weeklyCap", 0) or 0)
            reset = int(self.config.get("weeklyReset", 0) or 0)
            offset = 543600 if reset == 0 else 486000
            week = max(1, 1 + math.floor((timestamp - offset) / 604800))
            if weekly_cap > 0:
                current = self.weekly_gains.setdefault(guid, {}).get(week, 0.0)
                maximum = weekly_cap - current
                if maximum < 0:
                    return
                value = min(value, maximum)
            value = self.round(value)
            gains = self.weekly_gains.setdefault(guid, {})
            gains[week] = gains.get(week, 0.0) + value
        else:
            value = self.round(value)
        self.standings[guid] = standings + value

    def set(self, guid: Guid, value: float) -> None:
        self.standings[guid] = self.round(value)

    def decay(self, guid: Guid, percent: float) -> None:
        current = self.standings.get(guid, 0.0)
        self.standings[guid] = self.round(current * (100 - percent) / 100)


@dataclass
class _Raid:
    uid: str
    roster: _Roster
    config: dict[str, object]
    players: set[Guid] = field(default_factory=set)
    standby: set[Guid] = field(default_factory=set)
    active: bool = True


class ClmLedgerReplayer:
    """Rekonstruiert den aktuellen CLM-DKP-Stand aus dem Event-Ledger."""

    _NO_POINT_EFFECT = {"R6", "R7", "R8", "RR", "RB", "RF", "RM",
                        "VE", "VX", "VM", "VS", "VT", "ID", "IE"}

    def __init__(self) -> None:
        self.profiles: dict[Guid, _Profile] = {}
        self.rosters: dict[object, _Roster] = {}
        self.raids: dict[str, _Raid] = {}
        self.current_raid: dict[Guid, _Raid] = {}
        self.current_standby: dict[Guid, _Raid] = {}

    def replay(self, request: LedgerReplayRequest) -> LedgerReplayResult:
        self.__init__()
        entries = [entry for entry in _sequence(request.ledger)
                   if isinstance(entry, Mapping)]
        entries.sort(key=_entry_sort_key)
        ignored: set[str] = set()
        processed = 0
        ignored_entries = 0
        for entry in entries:
            uid = _entry_uuid(entry)
            if uid in ignored:
                ignored.remove(uid)
                ignored_entries += 1
                continue
            opcode = str(entry.get("_d") or "")
            if opcode == "IGN":
                ignored.add(str(entry.get("ref") or ""))
                continue
            self._apply(opcode, entry)
            processed += 1
        if ignored:
            raise ClmIntegrationError(
                f"{len(ignored)} CLM-Ignore-Referenzen konnten nicht aufgelöst werden."
            )
        roster = next((item for key, item in self.rosters.items()
                       if str(key) == str(request.roster_id)), None)
        if roster is None:
            raise ClmIntegrationError(
                f"CLM-Roster {request.roster_id!r} ist nach dem Replay nicht aktiv."
            )
        if roster.point_type != 0:
            raise ClmIntegrationError(
                f"CLM-Roster {request.roster_id!r} ist kein DKP-Roster."
            )
        balances = []
        for guid in roster.in_roster:
            profile = self.profiles.get(guid)
            if profile is not None:
                balances.append(ClmCharacterBalance(
                    profile.name, _display_number(roster.standings.get(guid, 0.0)),
                ))
        balances.sort(key=lambda item: item.name.casefold())
        return LedgerReplayResult(
            balances=tuple(balances), processed_entries=processed,
            roster_name=roster.name, roster_id=str(roster.uid),
            point_type=roster.point_type, active=True,
            ignored_entries=ignored_entries,
        )

    def _apply(self, opcode: str, entry: Mapping[object, object]) -> None:
        if opcode == "P0":
            self._profile_update(entry)
        elif opcode == "P1":
            self._profile_remove(entry)
        elif opcode == "P2":
            self._profile_link(entry)
        elif opcode == "P3":
            self._profile_lock(entry)
        elif opcode == "R0":
            uid = entry.get("r")
            self.rosters[uid] = _Roster(
                uid, str(entry.get("n") or ""), int(entry.get("p") or 0),
            )
        elif opcode == "R1":
            self.rosters.pop(entry.get("r"), None)
        elif opcode == "R2":
            roster = self.rosters.get(entry.get("r"))
            if roster is not None:
                roster.name = str(entry.get("n") or "")
        elif opcode == "R3":
            roster = self.rosters.get(entry.get("r"))
            if roster is not None:
                roster.config = _inflate_config(entry.get("c"))
        elif opcode == "R4":
            roster = self.rosters.get(entry.get("r"))
            key = entry.get("c")
            if roster is not None and isinstance(key, str):
                roster.config[key] = entry.get("v")
        elif opcode == "R9":
            self._roster_profiles(entry)
        elif opcode == "RC":
            self._roster_copy(entry)
        elif opcode == "AC":
            self._raid_create(entry)
        elif opcode == "AS":
            self._raid_start(entry)
        elif opcode == "AU":
            self._raid_update(entry)
        elif opcode == "AE":
            self._raid_end(entry)
        elif opcode in {"DM", "DS", "DD"}:
            self._points_profiles(opcode, entry)
        elif opcode in {"DO", "DT"}:
            self._points_roster(opcode, entry)
        elif opcode == "DR":
            self._points_raid(entry)
        elif opcode in {"IA", "II"}:
            self._loot(entry)
        elif opcode in self._NO_POINT_EFFECT:
            return
        else:
            raise ClmIntegrationError(f"Nicht unterstützter CLM-Ledger-Opcode: {opcode!r}.")

    def _profile_update(self, entry: Mapping[object, object]) -> None:
        guid = _guid(entry.get("g"))
        if guid is None:
            return
        name = str(entry.get("n") or "")
        profile = self.profiles.get(guid)
        if profile is None:
            profile = _Profile(name)
            self.profiles[guid] = profile
            for roster in self.rosters.values():
                if guid in roster.standings and guid not in roster.in_roster:
                    roster.in_roster.add(guid)
        else:
            profile.name = name

    def _profile_remove(self, entry: Mapping[object, object]) -> None:
        guid = _guid(entry.get("g"))
        if guid is None:
            return
        profile = self.profiles.pop(guid, None)
        if profile is None:
            return
        if profile.alts:
            for alt in tuple(profile.alts):
                alt_profile = self.profiles.get(alt)
                if alt_profile is not None:
                    alt_profile.main = None
        elif profile.main is not None:
            main = self.profiles.get(profile.main)
            if main is not None:
                main.alts.discard(guid)
        for roster in self.rosters.values():
            roster.in_roster.discard(guid)

    def _profile_link(self, entry: Mapping[object, object]) -> None:
        alt_guid = _guid(entry.get("g"))
        main_guid = _guid(entry.get("m"))
        if alt_guid is None:
            return
        alt = self.profiles.get(alt_guid)
        if alt is None:
            return
        main = self.profiles.get(main_guid) if main_guid is not None else None
        if main is None:
            old_main = self.profiles.get(alt.main) if alt.main is not None else None
            if old_main is not None:
                old_main.alts.discard(alt_guid)
                alt.main = None
            return
        if alt_guid == main_guid or alt.main == main_guid or main.main is not None or alt.alts:
            return
        old_main = self.profiles.get(alt.main) if alt.main is not None else None
        if old_main is not None:
            old_main.alts.discard(alt_guid)
        alt.main = main_guid
        main.alts.add(alt_guid)
        for roster in self.rosters.values():
            if alt_guid not in roster.in_roster:
                continue
            roster.add(main_guid)
            roster.set(main_guid, roster.standings.get(main_guid, 0.0)
                       + roster.standings.get(alt_guid, 0.0))
            self._mirror(roster, main_guid, main.alts)

    def _profile_lock(self, entry: Mapping[object, object]) -> None:
        locked = bool(entry.get("l"))
        for guid in _guid_list(entry.get("p")):
            profile = self.profiles.get(guid)
            if profile is None:
                continue
            targets = {guid}
            if profile.alts:
                targets.update(profile.alts)
            elif profile.main is not None:
                targets.add(profile.main)
                main = self.profiles.get(profile.main)
                if main is not None:
                    targets.update(main.alts)
            for target in targets:
                if target in self.profiles:
                    self.profiles[target].locked = locked

    def _roster_profiles(self, entry: Mapping[object, object]) -> None:
        roster = self.rosters.get(entry.get("r"))
        if roster is None:
            return
        for guid in _guid_list(entry.get("p")):
            if bool(entry.get("e")):
                profile = self.profiles.get(guid)
                if profile is not None:
                    roster.remove(guid)
                    for alt in profile.alts:
                        roster.remove(alt)
                continue
            initialize = guid not in roster.in_roster
            roster.add(guid)
            profile = self.profiles.get(guid)
            if profile is None:
                continue
            if profile.main is not None:
                if profile.main not in roster.in_roster:
                    roster.add(profile.main)
                    base = float(roster.config.get("basePoints", 0) or 0)
                    if base > 0:
                        roster.set(profile.main, base)
                if profile.main in roster.standings:
                    roster.standings[guid] = roster.standings[profile.main]
            elif initialize:
                base = float(roster.config.get("basePoints", 0) or 0)
                if base > 0:
                    roster.set(guid, base)

    def _roster_copy(self, entry: Mapping[object, object]) -> None:
        source = self.rosters.get(entry.get("r"))
        target = self.rosters.get(entry.get("a"))
        if source is None or target is None:
            return
        if bool(entry.get("c")):
            target.config = dict(source.config)
        if bool(entry.get("p")):
            for guid in source.in_roster:
                target.add(guid)

    def _raid_create(self, entry: Mapping[object, object]) -> None:
        roster = self.rosters.get(entry.get("r"))
        if roster is None:
            return
        uid = _entry_uuid(entry)
        raid = _Raid(uid, roster, _inflate_config(entry.get("c")))
        self.raids[uid] = raid
        creator = (entry.get("_e"), entry.get("_a"))
        if creator in self.profiles:
            self._move_to_raid(creator, raid)

    def _move_to_raid(self, guid: Guid, raid: _Raid) -> None:
        current = self.current_raid.get(guid)
        if current is not None and current.active:
            current.players.discard(guid)
        standby = self.current_standby.pop(guid, None)
        if standby is not None:
            standby.standby.discard(guid)
        raid.players.add(guid)
        raid.standby.discard(guid)
        self.current_raid[guid] = raid

    def _move_to_standby(self, guid: Guid, raid: _Raid) -> None:
        current = self.current_raid.pop(guid, None)
        if current is not None and current.active:
            current.players.discard(guid)
        old = self.current_standby.get(guid)
        if old is not None:
            old.standby.discard(guid)
        raid.players.discard(guid)
        raid.standby.add(guid)
        self.current_standby[guid] = raid

    def _remove_from_raids(self, guid: Guid) -> None:
        current = self.current_raid.pop(guid, None)
        if current is not None:
            current.players.discard(guid)
        standby = self.current_standby.pop(guid, None)
        if standby is not None:
            standby.standby.discard(guid)

    def _remove_from_current_raid(self, guid: Guid) -> None:
        current = self.current_raid.pop(guid, None)
        if current is not None and current.active:
            current.players.discard(guid)

    def _raid_start(self, entry: Mapping[object, object]) -> None:
        raid = self.raids.get(str(entry.get("r") or ""))
        if raid is None:
            return
        for guid in _guid_list(entry.get("s")):
            if guid in self.profiles:
                self._move_to_standby(guid, raid)
        for guid in _guid_list(entry.get("p")):
            if guid in self.profiles:
                self._move_to_raid(guid, raid)

    def _raid_update(self, entry: Mapping[object, object]) -> None:
        raid = self.raids.get(str(entry.get("r") or ""))
        if raid is None:
            return
        for guid in _guid_list(entry.get("s")):
            if guid in self.profiles and guid not in raid.players:
                self._move_to_standby(guid, raid)
        for guid in _guid_list(entry.get("j")):
            if guid in self.profiles:
                self._move_to_raid(guid, raid)
        for guid in _guid_list(entry.get("l")):
            if guid in self.profiles:
                if bool(raid.config.get("autoBenchLeavers")):
                    self._move_to_standby(guid, raid)
                else:
                    self._remove_from_current_raid(guid)
        for guid in _guid_list(entry.get("e")):
            if guid in self.profiles:
                self._remove_from_raids(guid)

    def _raid_end(self, entry: Mapping[object, object]) -> None:
        raid = self.raids.get(str(entry.get("r") or ""))
        if raid is None:
            return
        raid.active = False
        for guid in tuple(raid.players | raid.standby):
            if self.current_raid.get(guid) is raid:
                self.current_raid.pop(guid, None)
            if self.current_standby.get(guid) is raid:
                self.current_standby.pop(guid, None)

    def _resolved_target(self, roster: _Roster, guid: Guid) -> tuple[Guid, _Profile] | None:
        if guid not in roster.in_roster:
            return None
        profile = self.profiles.get(guid)
        if profile is None or profile.locked:
            return None
        if profile.main is not None:
            main = self.profiles.get(profile.main)
            if main is None or profile.main not in roster.in_roster:
                return None
            return profile.main, main
        return guid, profile

    def _mirror(self, roster: _Roster, source: Guid, targets: set[Guid]) -> None:
        for target in targets:
            if target in roster.standings and target != source:
                roster.standings[target] = roster.standings[source]

    def _mutate_targets(self, roster: _Roster, targets: list[Guid], value: float,
                        timestamp: int, action: str) -> None:
        applied: set[Guid] = set()
        for original in targets:
            resolved = self._resolved_target(roster, original)
            if resolved is None:
                continue
            guid, profile = resolved
            if guid in applied:
                continue
            if action == "modify":
                roster.update(guid, value, timestamp)
            elif action == "set":
                roster.set(guid, value)
            elif action == "decay":
                roster.decay(guid, value)
            applied.add(guid)
            if profile.alts:
                self._mirror(roster, guid, profile.alts)

    def _points_profiles(self, opcode: str, entry: Mapping[object, object]) -> None:
        roster = self.rosters.get(entry.get("r"))
        if roster is None or bool(entry.get("n")):
            return
        point_type = int(entry.get("i") or 0)
        if opcode == "DD" and point_type not in {0, 1}:
            return
        action = {"DM": "modify", "DS": "set", "DD": "decay"}[opcode]
        self._mutate_targets(
            roster, _guid_list(entry.get("p")), float(entry.get("v") or 0),
            int(entry.get("_c") or 0), action,
        )

    def _points_roster(self, opcode: str, entry: Mapping[object, object]) -> None:
        roster = self.rosters.get(entry.get("r"))
        if roster is None or bool(entry.get("n")) and opcode == "DO":
            return
        targets = list(roster.in_roster)
        if opcode == "DT" and bool(entry.get("n")):
            targets = [guid for guid in targets if roster.standings.get(guid, 0) >= 0]
        action = "modify" if opcode == "DO" else "decay"
        self._mutate_targets(
            roster, targets, float(entry.get("v") or 0),
            int(entry.get("_c") or 0), action,
        )

    def _points_raid(self, entry: Mapping[object, object]) -> None:
        raid = self.raids.get(str(entry.get("r") or ""))
        if raid is None or bool(entry.get("n")):
            return
        value = float(entry.get("v") or 0)
        timestamp = int(entry.get("_c") or 0)
        applied: set[Guid] = set()
        self._mutate_targets_with_applied(
            raid.roster, list(raid.players), value, timestamp, applied,
        )
        if bool(entry.get("s")) and raid.standby:
            bench = _lua_round(
                float(raid.config.get("benchMultiplier", 1) or 0) * value,
                int(raid.config.get("roundDecimals", 10)),
            )
            self._mutate_targets_with_applied(
                raid.roster, list(raid.standby), bench, timestamp, applied,
            )

    def _mutate_targets_with_applied(self, roster: _Roster, targets: list[Guid],
                                     value: float, timestamp: int,
                                     applied: set[Guid]) -> None:
        for original in targets:
            resolved = self._resolved_target(roster, original)
            if resolved is None:
                continue
            guid, profile = resolved
            if guid in applied:
                continue
            roster.update(guid, value, timestamp)
            applied.add(guid)
            if profile.alts:
                self._mirror(roster, guid, profile.alts)

    def _loot(self, entry: Mapping[object, object]) -> None:
        raid = None
        if str(entry.get("_d")) == "II":
            raid = self.raids.get(str(entry.get("r") or ""))
            roster = raid.roster if raid is not None else None
        else:
            roster = self.rosters.get(entry.get("r"))
        guid = _guid(entry.get("p"))
        if roster is None or guid is None or guid not in roster.in_roster:
            return
        profile = self.profiles.get(guid)
        if profile is None or profile.locked:
            return
        value = float(entry.get("v") or 0)
        timestamp = int(entry.get("_c") or 0)
        if roster.point_type == 0:
            roster.update(guid, -value, timestamp)
            if profile.main is not None:
                main = self.profiles.get(profile.main)
                if main is not None:
                    self._mirror(roster, guid, main.alts | {profile.main})
            elif profile.alts:
                self._mirror(roster, guid, profile.alts)
        if (raid is not None and bool(raid.config.get("zeroSumBank"))
                and (raid.players or raid.standby)):
            players = set(raid.players)
            if bool(raid.config.get("autoAwardIncludeBench")):
                players.update(raid.standby)
            if players:
                award = value / len(players) + float(
                    roster.config.get("zeroSumBankInflation", 0) or 0
                )
                award = _lua_round(award, int(raid.config.get("roundDecimals", 10)))
                self._mutate_targets(
                    roster, list(players), award, timestamp, "modify",
                )


class FixtureRequiredLedgerReplayer(ClmLedgerReplayer):
    """Kompatibler Name für den nun fixture-verifizierten Replayer."""
