"""UI-independent raid-attendance models, matching, validation and statistics."""

from __future__ import annotations

import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Callable, Iterable, Mapping
from urllib.parse import urlparse


RAID_STATUSES = ("draft", "recorded")
ATTENDANCE_TYPES = ("main", "twink")
ATTENDANCE_STATUSES = ("present", "bench")
RAID_TYPES = ("ZG", "AQ20", "MC", "BWL", "AQ40", "Naxx", "Onyxia", "World Boss")
RAID_CATEGORIES = ("20er", "40er", "Onyxia", "World Boss")


def raid_category(raid_type: object) -> str:
    value = _text(raid_type)
    if value in {"ZG", "AQ20"}:
        return "20er"
    if value in {"MC", "BWL", "AQ40", "Naxx"}:
        return "40er"
    if value == "Onyxia":
        return "Onyxia"
    if value == "World Boss":
        return "World Boss"
    return ""


class RaidValidationError(ValueError):
    def __init__(self, code: str, **values: object) -> None:
        super().__init__(code)
        self.code = code
        self.values = values


def _text(value: object) -> str:
    return unicodedata.normalize("NFC", str(value or "").strip())


def exact_name_key(value: object) -> str:
    return _text(value).casefold()


def normalize_iso_date(value: object, *, optional: bool = False) -> str | None:
    text = _text(value)
    if not text and optional:
        return None
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise RaidValidationError("invalid_date", value=text or "–") from exc
    return parsed.isoformat()


def normalize_optional_date(value: object) -> str | None:
    return normalize_iso_date(value, optional=True)


def validate_membership_dates(start: object, end: object) -> tuple[str | None, str | None]:
    normalized_start = normalize_optional_date(start)
    normalized_end = normalize_optional_date(end)
    if normalized_start and normalized_end and normalized_end < normalized_start:
        raise RaidValidationError("membership_order")
    return normalized_start, normalized_end


def validate_logs_url(value: object) -> str:
    text = _text(value)
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RaidValidationError("invalid_url")
    return text


def new_raid_id() -> str:
    return f"r_{uuid.uuid4().hex}"


def new_attendance_id() -> str:
    return f"a_{uuid.uuid4().hex}"


@dataclass
class Raid:
    id: str
    date: str
    name: str
    warcraftLogsUrl: str = ""
    status: str = "draft"
    raidType: str = ""
    clmRaidIds: list[str] = field(default_factory=list)
    raidStart: int | None = None
    raidEnd: int | None = None
    raidDuration: int | None = None
    sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.id = _text(self.id)
        self.date = str(normalize_iso_date(self.date))
        self.name = _text(self.name)
        self.warcraftLogsUrl = validate_logs_url(self.warcraftLogsUrl)
        self.raidType = _text(self.raidType)
        self.clmRaidIds = list(dict.fromkeys(_text(value) for value in self.clmRaidIds if _text(value)))
        self.sources = tuple(dict.fromkeys(_text(value) for value in self.sources if _text(value)))
        if not self.id:
            raise RaidValidationError("missing_raid_id")
        if not self.name:
            raise RaidValidationError("empty_name")
        if self.status not in RAID_STATUSES:
            raise RaidValidationError("invalid_status")
        if self.raidType and self.raidType not in RAID_TYPES:
            raise RaidValidationError("invalid_raid_type")

    @property
    def category(self) -> str:
        return raid_category(self.raidType)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Raid":
        return cls(
            id=data.get("id") or "",
            date=data.get("date") or "",
            name=data.get("name") or "",
            warcraftLogsUrl=data.get("warcraftLogsUrl") or "",
            status=data.get("status") or "draft",
            raidType=data.get("raidType") or "",
            clmRaidIds=list(data.get("clmRaidIds") or []),
            raidStart=(int(data["raidStart"]) if data.get("raidStart") is not None else None),
            raidEnd=(int(data["raidEnd"]) if data.get("raidEnd") is not None else None),
            raidDuration=(int(data["raidDuration"]) if data.get("raidDuration") is not None else None),
            sources=tuple(data.get("sources") or ()),
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        if not self.warcraftLogsUrl:
            data.pop("warcraftLogsUrl")
        if not self.raidType:
            data.pop("raidType")
        for key in ("clmRaidIds", "raidStart", "raidEnd", "raidDuration", "sources"):
            if data.get(key) in (None, [], (), ""):
                data.pop(key, None)
        return data


@dataclass
class RaidAttendance:
    id: str
    raidId: str
    playerId: str
    memberId: str
    attendanceType: str
    playerNameSnapshot: str
    characterNameSnapshot: str
    status: str = "present"

    def __post_init__(self) -> None:
        self.id = _text(self.id)
        self.raidId = _text(self.raidId)
        self.playerId = _text(self.playerId)
        self.memberId = _text(self.memberId)
        self.playerNameSnapshot = _text(self.playerNameSnapshot)
        self.characterNameSnapshot = _text(self.characterNameSnapshot)
        self.status = _text(self.status) or "present"
        if not all((self.id, self.raidId, self.playerId, self.memberId)):
            raise RaidValidationError("incomplete_attendance_ids")
        if self.attendanceType not in ATTENDANCE_TYPES:
            raise RaidValidationError("invalid_attendance_type")
        if self.status not in ATTENDANCE_STATUSES:
            raise RaidValidationError("invalid_attendance_status")
        if not self.playerNameSnapshot or not self.characterNameSnapshot:
            raise RaidValidationError("empty_snapshots")

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "RaidAttendance":
        return cls(
            id=data.get("id") or "",
            raidId=data.get("raidId") or "",
            playerId=data.get("playerId") or "",
            memberId=data.get("memberId") or "",
            attendanceType=data.get("attendanceType") or "",
            playerNameSnapshot=data.get("playerNameSnapshot") or "",
            characterNameSnapshot=data.get("characterNameSnapshot") or "",
            status=data.get("status") or "present",
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AttendanceCandidate:
    player_id: str
    member_id: str
    attendance_type: str
    player_name: str
    character_name: str


@dataclass(frozen=True)
class UnassignedCharacter:
    member_id: str
    character_name: str


@dataclass(frozen=True)
class AttendanceResolution:
    candidates: tuple[AttendanceCandidate, ...]
    unknown_names: tuple[str, ...]
    ambiguous_names: tuple[str, ...]
    unassigned_characters: tuple[UnassignedCharacter, ...]
    merged_characters: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class AttendanceStatistics:
    player_id: str
    eligible_raids: int
    main_attendances: int
    twink_attendances: int
    total_attendances: int
    bench_attendances: int
    absences: int
    attendance_percent: int
    twink_percent: int
    last_attendance: str | None
    current_streak: int
    longest_streak: int


def attendance_index(
    attendance: Iterable[RaidAttendance],
) -> dict[str, dict[str, RaidAttendance]]:
    """Build the shared raid/player lookup used by statistics and matrix views."""
    result: dict[str, dict[str, RaidAttendance]] = {}
    for entry in attendance:
        result.setdefault(entry.raidId, {})[entry.playerId] = entry
    return result


def player_is_relevant(
    raid: Raid,
    tracking_start_date: object,
    membership_start_date: object = None,
    membership_end_date: object = None,
) -> bool:
    if raid.status != "recorded":
        return False
    tracking_start = normalize_optional_date(tracking_start_date)
    member_start, member_end = validate_membership_dates(
        membership_start_date, membership_end_date,
    )
    relevant_start = max(
        (value for value in (tracking_start, member_start) if value is not None),
        default=None,
    )
    return bool(
        relevant_start is not None
        and raid.date >= relevant_start
        and (member_end is None or raid.date <= member_end)
    )


def resolve_attendance(
    names: Iterable[str], members: Iterable[object], players: Iterable[object],
) -> AttendanceResolution:
    """Resolve known characters and deduplicate them by stable player ID.

    Historical imports must retain an exact match to a deceased character.  If
    several incarnations have the same name, the existing ambiguity handling
    deliberately requires an explicit decision instead of guessing.
    """
    members_by_name: dict[str, list[object]] = {}
    for member in members:
        members_by_name.setdefault(
            exact_name_key(getattr(member, "name", "")), [],
        ).append(member)
    players_by_id = {
        str(getattr(player, "playerId", "")): player
        for player in players if getattr(player, "playerId", None)
    }

    unknown: list[str] = []
    ambiguous: list[str] = []
    unassigned: list[UnassignedCharacter] = []
    grouped: dict[str, list[AttendanceCandidate]] = {}
    player_order: list[str] = []
    for raw_name in names:
        name = _text(raw_name)
        matches = members_by_name.get(exact_name_key(name), [])
        if not matches:
            unknown.append(name)
            continue
        if len(matches) != 1:
            ambiguous.append(name)
            continue
        member = matches[0]
        player_id = _text(getattr(member, "playerId", ""))
        attendance_type = str(getattr(member, "characterType", ""))
        player = players_by_id.get(player_id)
        if not player_id and attendance_type in {"", "not_set", "main"}:
            unassigned.append(UnassignedCharacter(
                member_id=_text(getattr(member, "id", "")),
                character_name=_text(getattr(member, "name", name)),
            ))
            continue
        if not player_id or player is None or attendance_type not in ATTENDANCE_TYPES:
            ambiguous.append(name)
            continue
        candidate = AttendanceCandidate(
            player_id=player_id,
            member_id=_text(getattr(member, "id", "")),
            attendance_type=attendance_type,
            player_name=_text(getattr(player, "playerName", "")),
            character_name=_text(getattr(member, "name", name)),
        )
        if player_id not in grouped:
            grouped[player_id] = []
            player_order.append(player_id)
        grouped[player_id].append(candidate)

    selected: list[AttendanceCandidate] = []
    merged: list[tuple[str, ...]] = []
    for player_id in player_order:
        group = grouped[player_id]
        main = next((candidate for candidate in group if candidate.attendance_type == "main"), None)
        selected.append(main or group[0])
        if len(group) > 1:
            merged.append(tuple(candidate.character_name for candidate in group))
    return AttendanceResolution(
        candidates=tuple(selected),
        unknown_names=tuple(unknown),
        ambiguous_names=tuple(ambiguous),
        unassigned_characters=tuple(unassigned),
        merged_characters=tuple(merged),
    )


def attendance_records(
    raid_id: str, candidates: Iterable[AttendanceCandidate],
    id_factory: Callable[[], str] = new_attendance_id,
    status: str = "present",
) -> list[RaidAttendance]:
    if status not in ATTENDANCE_STATUSES:
        raise RaidValidationError("invalid_attendance_status")
    records: list[RaidAttendance] = []
    seen_players: set[str] = set()
    for candidate in candidates:
        if candidate.player_id in seen_players:
            raise RaidValidationError("duplicate_player", id=candidate.player_id)
        seen_players.add(candidate.player_id)
        records.append(RaidAttendance(
            id=id_factory(), raidId=raid_id, playerId=candidate.player_id,
            memberId=candidate.member_id, attendanceType=candidate.attendance_type,
            playerNameSnapshot=candidate.player_name,
            characterNameSnapshot=candidate.character_name,
            status=status,
        ))
    return records


def calculate_statistics(
    player_id: str, raids: Iterable[Raid], attendance: Iterable[RaidAttendance],
    tracking_start_date: object, membership_start_date: object = None,
    membership_end_date: object = None,
    *, start_date: object = None, end_date: object = None,
    category: str = "", raid_type: str = "",
    member_assignments: Mapping[str, tuple[str, str]] | None = None,
    member_id: str | None = None,
    eligible_raid_ids: Iterable[str] | None = None,
) -> AttendanceStatistics:
    # Kept for call-site compatibility only. Historical statistics are always
    # attributed through the playerId/memberId/attendanceType stored on each
    # attendance record, never through today's character assignment.
    del member_assignments
    normalized_start = normalize_optional_date(start_date)
    normalized_end = normalize_optional_date(end_date)
    if normalized_start and normalized_end and normalized_end < normalized_start:
        raise RaidValidationError("invalid_period")
    scoped_raids = [
        raid for raid in raids
        if (normalized_start is None or raid.date >= normalized_start)
        and (normalized_end is None or raid.date <= normalized_end)
        and (not category or raid.category == category)
        and (not raid_type or raid.raidType == raid_type)
    ]
    if eligible_raid_ids is None:
        eligible_ids = {
            raid.id for raid in scoped_raids
            if player_is_relevant(
                raid, tracking_start_date, membership_start_date, membership_end_date,
            )
        }
    else:
        scoped_ids = {raid.id for raid in scoped_raids}
        eligible_ids = scoped_ids.intersection(eligible_raid_ids)
    by_raid: dict[str, tuple[RaidAttendance, str]] = {}
    for entry in attendance:
        matches_subject = (
            entry.memberId == member_id if member_id is not None
            else entry.playerId == player_id
        )
        if matches_subject and entry.raidId in eligible_ids:
            by_raid[entry.raidId] = (entry, entry.attendanceType)
    attended_entries = [
        entry for entry, _type in by_raid.values()
        if entry.status in {"present", "bench"}
    ]
    main_count = sum(
        character_type == "main"
        for entry, character_type in by_raid.values()
        if entry.status == "present"
    )
    twink_count = sum(
        character_type == "twink"
        for entry, character_type in by_raid.values()
        if entry.status == "present"
    )
    bench_count = sum(entry.status == "bench" for entry, _type in by_raid.values())
    eligible_count = len(eligible_ids)
    total = len(attended_entries)
    attendance_percent = round(total * 100 / eligible_count) if eligible_count else 0
    twink_percent = round(twink_count * 100 / eligible_count) if eligible_count else 0
    raid_dates = {raid.id: raid.date for raid in scoped_raids}
    last_attendance = max(
        (raid_dates[entry.raidId] for entry in attended_entries if entry.raidId in raid_dates),
        default=None,
    )
    current_streak = 0
    longest_streak = 0
    for raid in sorted(
            (raid for raid in scoped_raids if raid.id in eligible_ids),
            key=lambda item: (item.date, item.id)):
        entry = by_raid.get(raid.id, (None, ""))[0]
        if entry is not None and entry.status in {"present", "bench"}:
            current_streak += 1
            longest_streak = max(longest_streak, current_streak)
        else:
            current_streak = 0
    return AttendanceStatistics(
        player_id=member_id if member_id is not None else player_id,
        eligible_raids=eligible_count,
        main_attendances=main_count,
        twink_attendances=twink_count,
        total_attendances=total,
        bench_attendances=bench_count,
        absences=max(0, eligible_count - total),
        attendance_percent=attendance_percent,
        twink_percent=twink_percent,
        last_attendance=last_attendance,
        current_streak=current_streak,
        longest_streak=longest_streak,
    )
