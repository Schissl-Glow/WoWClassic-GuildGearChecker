"""Read-only Identity V2 input for the existing Qt attendance matrix."""

from __future__ import annotations

from dataclasses import dataclass

from .identity_v2 import IdentityV2Store, Member
from .raid_attendance import (
    AttendanceStatistics, calculate_statistics, preferred_attendance, raid_category,
)


@dataclass(frozen=True)
class MatrixRaid:
    id: str
    date: str
    name: str
    raidType: str
    warcraftLogsUrl: str
    order: int
    status: str = "recorded"

    @property
    def category(self) -> str:
        return raid_category(self.raidType)


@dataclass(frozen=True)
class MatrixEntry:
    raidId: str
    playerId: str
    memberId: str
    attendanceType: str
    status: str
    name: str
    class_name: str | None


@dataclass(frozen=True)
class MatrixCell:
    status: str
    class_name: str | None = None
    entries: tuple[MatrixEntry, ...] = ()
    visited_raids: int = 0
    relevant_raids: int = 0


@dataclass(frozen=True)
class MatrixColumn:
    id: str
    date: str
    label: str
    raids: tuple[MatrixRaid, ...]


@dataclass(frozen=True)
class MatrixSubject:
    identifier: str
    label: str
    player_name: str | None
    main_name: str | None
    current_role: str | None
    is_dead: bool
    stat: AttendanceStatistics
    cells: tuple[MatrixCell, ...]


class V2AttendanceAdapter:
    """Index a V2 store once; reuse shared statistics for each matrix scope."""

    def __init__(self, store: IdentityV2Store) -> None:
        store.validate()
        self.store = store
        self.members = {member.memberId: member for member in store.members}
        self.players = {player.playerId: player for player in store.players}
        self.raids = tuple(MatrixRaid(
            raid.raidId, raid.date, raid.name or raid.raidType or raid.raidId,
            raid.raidType, next(iter(raid.csvReportUrls), ""), index)
            for index, raid in enumerate(store.raids))
        self.raid_by_id = {raid.id: raid for raid in self.raids}
        self.chronological = tuple(sorted(self.raids, key=lambda raid: (raid.date, raid.order)))
        self.raid_position = {raid.id: index for index, raid in enumerate(self.chronological)}
        self.by_player: dict[str, dict[str, tuple[MatrixEntry, ...]]] = {}
        self.by_member: dict[str, dict[str, tuple[MatrixEntry, ...]]] = {}
        player_lists: dict[str, dict[str, list[MatrixEntry]]] = {}
        member_lists: dict[str, dict[str, list[MatrixEntry]]] = {}
        for entry in store.attendance:
            if entry.status not in ("present", "bench"):
                continue
            member = self.members[entry.memberId]
            projected = MatrixEntry(
                entry.raidId, entry.playerId or "", entry.memberId,
                entry.attendanceType, entry.status, member.name, member.className)
            member_lists.setdefault(entry.memberId, {}).setdefault(entry.raidId, []).append(projected)
            if entry.playerId is not None:
                player_lists.setdefault(entry.playerId, {}).setdefault(entry.raidId, []).append(projected)
        self.by_player = {identifier: {raid_id: tuple(entries)
                                       for raid_id, entries in raids.items()}
                          for identifier, raids in player_lists.items()}
        self.by_member = {identifier: {raid_id: tuple(entries)
                                       for raid_id, entries in raids.items()}
                          for identifier, raids in member_lists.items()}
        self.first_player = {identifier: min(self.raid_position[raid_id]
                                             for raid_id in raids)
                             for identifier, raids in self.by_player.items()}
        self.first_member = {identifier: min(self.raid_position[raid_id]
                                             for raid_id in raids)
                             for identifier, raids in self.by_member.items()}
        self.active_players = {member.playerId for member in store.members
                               if member.playerId is not None and member.lifeStatus == "active"}

    def scoped_raids(self, *, start: str = "", end: str = "", category: str = "",
                     raid_type: str = "", limit: int = 0,
                     complete_days: bool = False) -> tuple[MatrixRaid, ...]:
        raids = tuple(sorted((raid for raid in self.raids
                              if (not start or raid.date >= start)
                              and (not end or raid.date <= end)
                              and (not category or raid.category == category)
                              and (not raid_type or raid.raidType == raid_type)),
                             key=lambda raid: (raid.date, raid.order), reverse=True))
        if not limit or len(raids) <= limit:
            return raids
        if complete_days:
            cutoff = raids[limit - 1].date
            return tuple(raid for raid in raids if raid.date >= cutoff)
        return raids[:limit]

    def eligible_ids(self, identifier: str, level: str) -> set[str]:
        first = (self.first_player if level == "player" else self.first_member).get(identifier)
        if first is None:
            return set()
        member = self.members.get(identifier) if level == "character" else None
        return {raid.id for raid in self.chronological
                if self.raid_position[raid.id] >= first
                and (member is None or member.deathDate is None
                     or raid.date <= member.deathDate)}

    def _raid_cell(self, raid: MatrixRaid, identifier: str, level: str,
                   eligible: set[str]) -> MatrixCell:
        if raid.id not in eligible:
            return MatrixCell("irrelevant")
        by_subject = self.by_player if level == "player" else self.by_member
        entries = by_subject.get(identifier, {}).get(raid.id, ())
        selected = None
        for entry in entries:
            selected = preferred_attendance(selected, entry)
        if selected is not None and selected.status == "present":
            return MatrixCell("present", selected.class_name, entries, 1, 1)
        if selected is not None:
            return MatrixCell("bench", None, entries, 1, 1)
        return MatrixCell("absent", None, (), 0, 1)

    def columns(self, raids: tuple[MatrixRaid, ...], grouping: str) -> tuple[MatrixColumn, ...]:
        if grouping == "raid":
            return tuple(MatrixColumn(raid.id, raid.date,
                                      raid.raidType or raid.name, (raid,))
                         for raid in raids)
        by_day: dict[str, list[MatrixRaid]] = {}
        for raid in raids:
            by_day.setdefault(raid.date, []).append(raid)
        return tuple(MatrixColumn(day, day, day,
                                  tuple(sorted(day_raids, key=lambda raid: raid.order)))
                     for day, day_raids in by_day.items())

    def _day_cell(self, column: MatrixColumn, identifier: str, level: str,
                  eligible: set[str]) -> MatrixCell:
        cells = tuple(self._raid_cell(raid, identifier, level, eligible)
                      for raid in column.raids)
        relevant = tuple(cell for cell in cells if cell.status != "irrelevant")
        if not relevant:
            return MatrixCell("irrelevant")
        first_present = next((cell for cell in cells if cell.status == "present"), None)
        status = ("present" if first_present is not None else
                  "bench" if any(cell.status == "bench" for cell in cells) else "absent")
        return MatrixCell(
            status, first_present.class_name if first_present is not None else None,
            tuple(entry for cell in cells for entry in cell.entries),
            sum(cell.status in ("present", "bench") for cell in cells), len(relevant))

    def subjects(self, raids: tuple[MatrixRaid, ...], level: str,
                 grouping: str, *,
                 include_inactive_players: bool = False,
                 identifiers: set[str] | None = None) -> tuple[MatrixSubject, ...]:
        if level not in ("player", "character") or grouping not in ("raid", "day"):
            raise ValueError("Invalid attendance matrix level or grouping.")
        columns = self.columns(raids, grouping)
        subjects = self.store.players if level == "player" else self.store.members
        result: list[MatrixSubject] = []
        for subject in subjects:
            identifier = subject.playerId if level == "player" else subject.memberId
            if identifiers is not None and identifier not in identifiers:
                continue
            if (level == "player" and identifier not in self.active_players
                    and not include_inactive_players):
                continue
            if identifier not in (self.first_player if level == "player" else self.first_member):
                continue
            eligible = self.eligible_ids(identifier, level)
            if not eligible:
                continue
            entries = (self.by_player if level == "player" else self.by_member)[identifier]
            flat_entries = tuple(entry for raid_entries in entries.values()
                                 for entry in raid_entries)
            stat = calculate_statistics(
                identifier if level == "player" else "", raids, flat_entries,
                None, member_id=identifier if level == "character" else None,
                eligible_raid_ids=eligible, streak_by_day=True)
            cells = tuple(
                self._raid_cell(column.raids[0], identifier, level, eligible)
                if grouping == "raid" else self._day_cell(column, identifier, level, eligible)
                for column in columns)
            if level == "player":
                main = self.members.get(subject.mainMemberId)
                result.append(MatrixSubject(
                    identifier, subject.displayName, None,
                    main.name if main else None, None, False, stat, cells))
            else:
                player = self.players.get(subject.playerId)
                result.append(MatrixSubject(
                    identifier, subject.name,
                    player.displayName if player else None, None,
                    "main" if player and player.mainMemberId == identifier else
                    "twink" if player else None,
                    subject.lifeStatus == "dead", stat, cells))
        return tuple(sorted(result, key=lambda row: (row.label.casefold(), row.identifier)))
