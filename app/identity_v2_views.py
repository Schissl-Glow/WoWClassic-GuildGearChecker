"""Read-only projections for the first Identity V2 roster and raid views."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .identity_v2 import IdentityV2Store


@dataclass(frozen=True)
class V2RosterRow:
    member_id: str
    name: str
    class_name: str | None
    raid_start_date: str | None
    raid_count: int
    eternal_dkp: float
    primary_guid: str | None
    legacy_guid_count: int


@dataclass(frozen=True)
class V2RaidRow:
    raid_id: str
    date: str
    name: str
    participant_count: int
    clm_raid_id: str | None
    csv_source_files: tuple[str, ...] = ()
    csv_report_urls: tuple[str, ...] = ()

    @property
    def source(self) -> str:
        if self.clm_raid_id and self.csv_source_files:
            return "CLM + CSV"
        if self.clm_raid_id:
            return "CLM"
        if self.csv_source_files:
            return "CSV"
        return "–"


@dataclass(frozen=True)
class V2AttendanceRow:
    attendance_id: str
    member_id: str
    name: str
    class_name: str | None
    historical_role: str
    source_guid: str | None


@dataclass(frozen=True)
class IdentityV2ViewData:
    roster: tuple[V2RosterRow, ...]
    raids: tuple[V2RaidRow, ...]
    attendance_by_raid: dict[str, tuple[V2AttendanceRow, ...]]

    @classmethod
    def from_store(cls, store: IdentityV2Store) -> "IdentityV2ViewData":
        store.validate()
        member_by_id = {member.memberId: member for member in store.members}
        raid_ids_by_member: dict[str, set[str]] = defaultdict(set)
        attendance_by_raid: dict[str, list[V2AttendanceRow]] = defaultdict(list)
        for entry in store.attendance:
            member = member_by_id[entry.memberId]
            raid_ids_by_member[entry.memberId].add(entry.raidId)
            attendance_by_raid[entry.raidId].append(V2AttendanceRow(
                entry.attendanceId, entry.memberId, member.name, member.className,
                entry.attendanceType, entry.clmGuid,
            ))
        legacy_counts = Counter(store.legacyClmGuidMemberMap.values())
        dkp = store.eternal_dkp_by_member()
        roster = tuple(sorted((
            V2RosterRow(
                member.memberId, member.name, member.className,
                member.raidStartDate, len(raid_ids_by_member[member.memberId]),
                dkp[member.memberId], member.clmGuid, legacy_counts[member.memberId],
            ) for member in store.members
        ), key=lambda row: (row.name.casefold(), row.member_id)))
        raids = tuple(sorted((
            V2RaidRow(raid.raidId, raid.date, raid.name,
                      len(attendance_by_raid[raid.raidId]), raid.clmRaidId,
                      raid.csvSourceFiles or tuple(
                          source.sourceFileName for source in raid.csvSources),
                      raid.csvReportUrls or tuple(
                          source.reportUrl for source in raid.csvSources
                          if source.reportUrl))
            for raid in store.raids
        ), key=lambda row: (row.date, row.raid_id)))
        details = {
            raid_id: tuple(sorted(rows, key=lambda row: (row.name.casefold(), row.member_id)))
            for raid_id, rows in attendance_by_raid.items()
        }
        return cls(roster, raids, details)
