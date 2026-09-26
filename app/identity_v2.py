"""Identity V2 domain model, explicit serialization, and invariants.

This module is deliberately independent from the legacy GuildModel. It does
not read, migrate, or rewrite legacy project files.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from math import isfinite
from typing import Any, Iterable
import re
import unicodedata
import uuid

from .identity_v2_character_values import (
    CLASS_SPECS, GEAR_STATUSES, RACES, RAID_ROLES, RAID_STATUSES,
)
from .raid_points import (
    ManualRaidPointAdjustment, MemberRaidPointAdjustment, RaidPointState,
)


IDENTITY_FORMAT = "identity-v2"
POINT_MODE_RAID = "raid_points"
POINT_MODE_ETERNAL = "eternal_dkp"
POINT_MODES = (POINT_MODE_RAID, POINT_MODE_ETERNAL)
FIRST_MEMBER_NUMBER = 1000
FIRST_PLAYER_NUMBER = 1
FIRST_MAIN_HISTORY_NUMBER = 1
LIFE_STATUSES = frozenset({"active", "inactive", "dead"})
BURIAL_TYPES = frozenset({"individual", "collective"})
MAIN_HISTORY_SOURCES = frozenset({"automatic", "manual"})
MAIN_HISTORY_REASONS = frozenset({"death", "main_change", "cleared", "inactive", "manual"})
CURRENT_ROLES = frozenset({"main", "twink", "ex_main"})
ATTENDANCE_TYPES = frozenset({"main", "twink", "unknown"})


def _v2_raid_point_state() -> RaidPointState:
    return RaidPointState(enabled=True, ever_enabled=True, calculation_mode="all")


def _is_iso_day(value: object) -> bool:
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


class IdentityV2ValidationError(ValueError):
    """Raised when an Identity V2 payload violates a domain invariant."""


def member_id_from_number(number: int) -> str:
    """Use the project's stable m#### ID convention without deriving IDs from names."""
    if isinstance(number, bool) or not isinstance(number, int) or number < FIRST_MEMBER_NUMBER:
        raise IdentityV2ValidationError("Ungültige Member-ID-Sequenznummer.")
    return f"m{number:04d}"


def player_id_from_number(number: int) -> str:
    """Create a stable technical Player ID independent of names and Main roles."""
    if isinstance(number, bool) or not isinstance(number, int) or number < FIRST_PLAYER_NUMBER:
        raise IdentityV2ValidationError("Ungültige Player-ID-Sequenznummer.")
    return f"p{number:04d}"


def main_history_id_from_number(number: int) -> str:
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise IdentityV2ValidationError("Invalid MainHistory ID sequence number.")
    return f"mh{number:04d}"


def new_v2_raid_id() -> str:
    return f"r_{uuid.uuid4().hex}"


def new_v2_attendance_id() -> str:
    return f"a_{uuid.uuid4().hex}"


@dataclass
class MainHistoryEntry:
    historyId: str
    memberId: str
    fromDate: str | None = None
    toDate: str | None = None
    source: str = "manual"
    reason: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MainHistoryEntry":
        return cls(
            historyId=data.get("historyId"),
            memberId=data.get("memberId"),
            fromDate=data.get("fromDate"),
            toDate=data.get("toDate"),
            source=data.get("source"),
            reason=data.get("reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Player:
    playerId: str
    displayName: str
    mainMemberId: str | None = None
    mainSinceDate: str | None = None
    mainHistory: list[MainHistoryEntry] = field(default_factory=list)
    inactiveRestoreStates: dict[str, str] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Player":
        if ("displayName" in data and "playerName" in data
                and data["displayName"] != data["playerName"]):
            raise IdentityV2ValidationError(
                "Player enthält widersprüchliche displayName/playerName-Werte.")
        display_name = data.get("displayName", data.get("playerName"))
        history = data.get("mainHistory", [])
        if not isinstance(history, list) or any(not isinstance(item, dict) for item in history):
            raise IdentityV2ValidationError("Player.mainHistory must be a list of entries.")
        restore = data.get("inactiveRestoreStates")
        return cls(
            playerId=_required_text(data, "playerId"),
            displayName=display_name,
            mainMemberId=data.get("mainMemberId"),
            mainSinceDate=data.get("mainSinceDate"),
            mainHistory=[MainHistoryEntry.from_dict(item) for item in history],
            inactiveRestoreStates=dict(restore) if isinstance(restore, dict) else restore,
        )

    def to_dict(self) -> dict[str, Any]:
        result = {"playerId": self.playerId, "displayName": self.displayName,
                  "mainMemberId": self.mainMemberId,
                  "mainSinceDate": self.mainSinceDate,
                  "mainHistory": [item.to_dict() for item in self.mainHistory]}
        if self.inactiveRestoreStates is not None:
            result["inactiveRestoreStates"] = dict(self.inactiveRestoreStates)
        return result

    @property
    def playerName(self) -> str:
        """Read-only alias for Phase-3 V2 review code."""
        return self.displayName


@dataclass
class Member:
    """One GGC character identity, optionally spanning confirmed CLM GUIDs."""

    memberId: str
    name: str
    className: str | None
    lifeStatus: str = "active"
    playerId: str | None = None
    currentRole: str | None = None  # Phase-3 compatibility; not the current Main source.
    clmGuid: str | None = None
    continuationOfMemberId: str | None = None
    deathDate: str | None = None
    raidStartDate: str | None = None
    graveTemplateId: str | None = None
    region: str | None = None
    realm: str | None = None
    gameVersion: str | None = None
    race: str | None = None
    spec: str | None = None
    raidRole: str = "not_set"
    gearStatus: str = "Level"
    raidStatus: str = ""
    note: str = ""
    lastChecked: str | None = None
    burialType: str | None = None
    portraitOffsetX: float = 0.0
    portraitOffsetY: float = 0.0
    portraitZoom: float = 1.0
    textOffsetX: float = 0.0
    textOffsetY: float = 0.0
    textScale: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Member":
        return cls(
            memberId=_required_text(data, "memberId"),
            name=_required_literal_text(data, "name"),
            className=_optional_class_text(data.get("className")),
            lifeStatus=_text(data.get("lifeStatus")) or "active",
            playerId=_optional_text(data.get("playerId")),
            currentRole=_optional_text(data.get("currentRole")),
            clmGuid=_optional_text(data.get("clmGuid")),
            continuationOfMemberId=_optional_text(data.get("continuationOfMemberId")),
            deathDate=_optional_text(data.get("deathDate")),
            burialType=("individual" if "burialType" not in data
                        and data.get("lifeStatus") == "dead"
                        else data.get("burialType")),
            portraitOffsetX=data.get("portraitOffsetX", 0.0),
            portraitOffsetY=data.get("portraitOffsetY", 0.0),
            portraitZoom=data.get("portraitZoom", 1.0),
            textOffsetX=data.get("textOffsetX", 0.0),
            textOffsetY=data.get("textOffsetY", 0.0),
            textScale=data.get("textScale", 1.0),
            raidStartDate=_optional_text(data.get("raidStartDate")),
            graveTemplateId=_optional_text(data.get("graveTemplateId")),
            region=_optional_text(data.get("region")),
            realm=_optional_text(data.get("realm")),
            gameVersion=_optional_text(data.get("gameVersion")),
            race=data.get("race"),
            spec=data.get("spec"),
            raidRole=data.get("raidRole", "not_set"),
            gearStatus=data.get("gearStatus", "Level"),
            raidStatus=data.get("raidStatus", ""),
            note=data.get("note", ""),
            lastChecked=data.get("lastChecked"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items()
                if value is not None or key in {"className", "burialType"}}


def member_attendance_after_death(member: Member, raid_date: str) -> bool:
    """A raid strictly after a known death date cannot belong to this incarnation."""
    try:
        raid_day = date.fromisoformat(raid_date)
        death_day = date.fromisoformat(member.deathDate) if member.deathDate else None
    except (TypeError, ValueError) as exc:
        raise IdentityV2ValidationError("Ungültiges Raid- oder Todesdatum.") from exc
    return death_day is not None and raid_day > death_day


def require_member_attendance_date(member: Member, raid_date: str) -> None:
    """Shared defensive gate for a future CSV attendance materialization."""
    if member_attendance_after_death(member, raid_date):
        raise IdentityV2ValidationError(
            f"Member {member.memberId} ist seit {member.deathDate} tot; "
            f"Attendance am {raid_date} ist unzulässig."
        )


@dataclass(frozen=True)
class IgnoredClmCharacterGroup:
    """Revocable ignore record for one finalized post-GUID-decision CLM group."""

    name: str
    clmGuids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "clmGuids": list(self.clmGuids)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IgnoredClmCharacterGroup":
        name = _required_literal_text(data, "name")
        guids = _source_values(data.get("clmGuids"))
        if not guids:
            raise IdentityV2ValidationError("Ignorierte CLM-Gruppe benötigt mindestens eine GUID.")
        return cls(name, tuple(guids))


@dataclass(frozen=True)
class CsvRaidSource:
    sourceFileName: str
    reportUrl: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CsvRaidSource":
        return cls(
            sourceFileName=_required_text(data, "sourceFileName"),
            reportUrl=_optional_text(data.get("reportUrl")),
        )

    def to_dict(self) -> dict[str, Any]:
        result = {"sourceFileName": self.sourceFileName}
        if self.reportUrl is not None:
            result["reportUrl"] = self.reportUrl
        return result


@dataclass
class Raid:
    raidId: str
    date: str = ""
    raidType: str = ""
    name: str = ""
    clmRaidId: str | None = None
    csvSourceFiles: tuple[str, ...] = ()
    csvReportUrls: tuple[str, ...] = ()
    csvSources: tuple[CsvRaidSource, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Raid":
        return cls(_required_text(data, "raidId"), _text(data.get("date")),
                   _literal_text(data.get("raidType")), _literal_text(data.get("name")),
                   _optional_text(data.get("clmRaidId")),
                   _source_values(data.get("csvSourceFiles")),
                   _source_values(data.get("csvReportUrls")),
                   tuple(CsvRaidSource.from_dict(item)
                         for item in _list_of_dicts(data, "csvSources")))

    def to_dict(self) -> dict[str, Any]:
        data = {key: value for key, value in asdict(self).items() if value is not None}
        if not self.name:
            data.pop("name")
        if not self.csvSourceFiles:
            data.pop("csvSourceFiles")
        if not self.csvReportUrls:
            data.pop("csvReportUrls")
        if not self.csvSources:
            data.pop("csvSources")
        else:
            data["csvSources"] = [source.to_dict() for source in self.csvSources]
        return data


@dataclass
class Attendance:
    attendanceId: str
    raidId: str
    memberId: str
    attendanceType: str
    status: str = "present"
    playerId: str | None = None
    clmGuid: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Attendance":
        return cls(
            attendanceId=_required_text(data, "attendanceId"),
            raidId=_required_text(data, "raidId"),
            memberId=_required_text(data, "memberId"),
            attendanceType=_required_text(data, "attendanceType"),
            status=_text(data.get("status")) or "present",
            playerId=_optional_text(data.get("playerId")),
            clmGuid=_optional_text(data.get("clmGuid")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass
class RaidCreditResolution:
    raidId: str
    playerId: str
    creditedMemberId: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RaidCreditResolution":
        return cls(_required_text(data, "raidId"), _required_text(data, "playerId"),
                   _required_text(data, "creditedMemberId"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EternalDkpRecord:
    recordId: str
    eventId: str
    memberId: str
    clmGuid: str
    eventType: str
    value: float
    occurredAt: str = ""
    clmRaidId: str | None = None
    description: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EternalDkpRecord":
        try:
            value = float(data["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise IdentityV2ValidationError("EternalDkpRecord.value muss numerisch sein.") from exc
        return cls(
            recordId=_required_text(data, "recordId"),
            eventId=_required_text(data, "eventId"),
            memberId=_required_text(data, "memberId"),
            clmGuid=_required_text(data, "clmGuid"),
            eventType=_required_text(data, "eventType"),
            value=value,
            occurredAt=_text(data.get("occurredAt")),
            clmRaidId=_optional_text(data.get("clmRaidId")),
            description=_optional_literal_text(data.get("description")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass
class IdentityV2Store:
    players: list[Player] = field(default_factory=list)
    members: list[Member] = field(default_factory=list)
    raids: list[Raid] = field(default_factory=list)
    attendance: list[Attendance] = field(default_factory=list)
    raidCreditResolutions: list[RaidCreditResolution] = field(default_factory=list)
    eternalDkpRecords: list[EternalDkpRecord] = field(default_factory=list)
    legacyClmGuidMemberMap: dict[str, str] = field(default_factory=dict)
    ignoredCsvCharacterNames: list[str] = field(default_factory=list)
    ignoredClmCharacterGroups: list[IgnoredClmCharacterGroup] = field(default_factory=list)
    nextPlayerNumber: int = FIRST_PLAYER_NUMBER
    nextMainHistoryNumber: int = FIRST_MAIN_HISTORY_NUMBER
    raidPoints: RaidPointState = field(default_factory=_v2_raid_point_state)
    pointMode: str = POINT_MODE_RAID
    guildName: str = ""
    realm: str = ""
    clmRosterName: str | None = None
    clmLuaPath: str | None = None
    clmDatabaseId: str | None = None
    clmRosterId: str | None = None

    def validate(self) -> None:
        if self.pointMode not in POINT_MODES:
            raise IdentityV2ValidationError("Ungültiger Punktmodus in der V2-Projektdatei.")
        if (self.clmRosterName is not None
                and (not isinstance(self.clmRosterName, str)
                     or not self.clmRosterName.strip())):
            raise IdentityV2ValidationError("clmRosterName muss ein nichtleerer Name sein.")
        for field_name in ("clmLuaPath", "clmDatabaseId", "clmRosterId"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise IdentityV2ValidationError(f"{field_name} muss ein nichtleerer Text sein.")
        if not isinstance(self.guildName, str) or not isinstance(self.realm, str):
            raise IdentityV2ValidationError("V2-Gildenname und Realm müssen Text sein.")
        points = self.raidPoints
        if (not isinstance(points, RaidPointState)
                or not points.enabled or not points.ever_enabled
                or points.calculation_mode != "all"
                or points.calculation_start_date is not None
                or points.included_raid_ids or points.pending_raid_ids
                or points.excluded_attendance_ids):
            raise IdentityV2ValidationError("V2-Raidpunkte müssen vollständig aus den Quellen berechenbar sein.")
        if (isinstance(self.nextPlayerNumber, bool)
                or not isinstance(self.nextPlayerNumber, int)
                or self.nextPlayerNumber < FIRST_PLAYER_NUMBER):
            raise IdentityV2ValidationError("nextPlayerNumber muss eine positive Zahl sein.")
        if (isinstance(self.nextMainHistoryNumber, bool)
                or not isinstance(self.nextMainHistoryNumber, int)
                or self.nextMainHistoryNumber < FIRST_MAIN_HISTORY_NUMBER):
            raise IdentityV2ValidationError("nextMainHistoryNumber must be positive.")
        for player in self.players:
            if not isinstance(player, Player):
                raise IdentityV2ValidationError("players enthält keinen gültigen Player.")
            if not isinstance(player.playerId, str) or not player.playerId.strip():
                raise IdentityV2ValidationError("Player.playerId darf nicht leer sein.")
            if not isinstance(player.displayName, str) or not player.displayName.strip():
                raise IdentityV2ValidationError(
                    f"Player {player.playerId} benötigt einen nichtleeren displayName.")
            if (player.mainMemberId is not None
                    and (not isinstance(player.mainMemberId, str)
                         or not player.mainMemberId.strip())):
                raise IdentityV2ValidationError(
                    f"Player {player.playerId} hat eine ungültige mainMemberId.")
        _unique((p.playerId for p in self.players), "playerId")
        _unique((m.memberId for m in self.members), "memberId")
        _unique((r.raidId for r in self.raids), "raidId")
        _unique((r.clmRaidId for r in self.raids if r.clmRaidId is not None),
                "Raid.clmRaidId")
        for raid in self.raids:
            if any(not isinstance(source, CsvRaidSource)
                   for source in raid.csvSources):
                raise IdentityV2ValidationError(
                    f"CSV-Quellen bei Raid {raid.raidId} sind ungültig.")
            if len(set(raid.csvSources)) != len(raid.csvSources):
                raise IdentityV2ValidationError(
                    f"CSV-Quellen bei Raid {raid.raidId} sind doppelt.")
            for source in raid.csvSources:
                if (not isinstance(source.sourceFileName, str)
                        or not source.sourceFileName
                        or "/" in source.sourceFileName
                        or "\\" in source.sourceFileName):
                    raise IdentityV2ValidationError(
                        f"CSV-Quelle bei Raid {raid.raidId} benötigt einen Dateinamen.")
                if (source.reportUrl is not None
                        and not isinstance(source.reportUrl, str)):
                    raise IdentityV2ValidationError(
                        f"Report-URL bei Raid {raid.raidId} muss Text sein.")
        _unique((a.attendanceId for a in self.attendance), "attendanceId")
        _unique(((a.raidId, a.memberId) for a in self.attendance),
                "Attendance(raidId, memberId)")
        _unique((r.recordId for r in self.eternalDkpRecords), "EternalDkpRecord.recordId")
        attendance_ids = {entry.attendanceId for entry in self.attendance}
        member_ids = {member.memberId for member in self.members}
        for attendance_id, adjustment in points.adjustments.items():
            if (not isinstance(adjustment, ManualRaidPointAdjustment)
                    or attendance_id != adjustment.attendance_id
                    or attendance_id not in attendance_ids):
                raise IdentityV2ValidationError("Ungültige attendancebezogene Raidpunkte-Anpassung.")
        for adjustment_id, adjustment in points.member_adjustments.items():
            if (not isinstance(adjustment, MemberRaidPointAdjustment)
                    or adjustment_id != adjustment.adjustment_id
                    or adjustment.member_id not in member_ids):
                raise IdentityV2ValidationError("Ungültige memberbezogene Raidpunkte-Anpassung.")
        if any(not isinstance(name, str) for name in self.ignoredCsvCharacterNames):
            raise IdentityV2ValidationError(
                "Ignorierte CSV-Charakternamen müssen Text sein.")
        ignored_csv_keys = [_normalize_csv_ignore(name)
                            for name in self.ignoredCsvCharacterNames]
        if any(not key for key in ignored_csv_keys):
            raise IdentityV2ValidationError("Ignorierter CSV-Charaktername darf nicht leer sein.")
        _unique(ignored_csv_keys, "ignoredCsvCharacterNames")
        member_name_keys = {_normalize_csv_ignore(member.name) for member in self.members}
        if member_name_keys & set(ignored_csv_keys):
            raise IdentityV2ValidationError(
                "Ein CSV-ignorierter Name darf nicht gleichzeitig als Member geführt sein."
            )
        ignored_clm_guids: set[str] = set()
        group_keys: set[frozenset[str]] = set()
        for group in self.ignoredClmCharacterGroups:
            if (not isinstance(group, IgnoredClmCharacterGroup)
                    or not isinstance(group.name, str) or not group.name.strip()
                    or not group.clmGuids
                    or any(not isinstance(guid, str) or not guid.strip()
                           for guid in group.clmGuids)):
                raise IdentityV2ValidationError("Ignorierte CLM-Gruppe ist unvollständig.")
            group_key = frozenset(guid.casefold() for guid in group.clmGuids)
            if not group_key or len(group_key) != len(group.clmGuids):
                raise IdentityV2ValidationError("GUIDs einer ignorierten CLM-Gruppe müssen eindeutig sein.")
            if group_key in group_keys:
                raise IdentityV2ValidationError("Ignorierte CLM-Gruppe ist doppelt registriert.")
            group_keys.add(group_key)
            for guid in group.clmGuids:
                key = guid.casefold()
                if key in ignored_clm_guids:
                    raise IdentityV2ValidationError(f"CLM-GUID {guid!r} ist mehrfach ignoriert.")
                ignored_clm_guids.add(key)

        players = {p.playerId for p in self.players}
        members = {m.memberId: m for m in self.members}
        raids = {r.raidId for r in self.raids}
        guid_owner: dict[str, str] = {}
        grave_owner: dict[str, str] = {}
        for member in self.members:
            if member.className is not None and (
                    not isinstance(member.className, str)
                    or member.className not in CLASS_SPECS):
                raise IdentityV2ValidationError(
                    f"className bei {member.memberId} muss eine Klasse oder None sein.")
            if member.race is not None and member.race not in RACES:
                raise IdentityV2ValidationError(f"Ungültige race bei {member.memberId}.")
            if member.spec is not None and (
                    member.className is None
                    or member.spec not in CLASS_SPECS[member.className]):
                raise IdentityV2ValidationError(f"Ungültige spec bei {member.memberId}.")
            if member.raidRole not in RAID_ROLES:
                raise IdentityV2ValidationError(f"Ungültige raidRole bei {member.memberId}.")
            if member.gearStatus not in GEAR_STATUSES:
                raise IdentityV2ValidationError(f"Ungültige gearStatus bei {member.memberId}.")
            if member.raidStatus not in RAID_STATUSES:
                raise IdentityV2ValidationError(f"Ungültige raidStatus bei {member.memberId}.")
            if not isinstance(member.note, str):
                raise IdentityV2ValidationError(f"Ungültige note bei {member.memberId}.")
            if member.lastChecked is not None and not _is_iso_day(member.lastChecked):
                raise IdentityV2ValidationError(f"Ungültige lastChecked bei {member.memberId}.")
            if member.deathDate is not None and not _is_iso_day(member.deathDate):
                raise IdentityV2ValidationError(f"Ungültige deathDate bei {member.memberId}.")
            # Older V2 saves may already contain dead Members without a known date;
            # the explicit CharacterData death operation requires one for new deaths.
            if member.lifeStatus not in LIFE_STATUSES:
                raise IdentityV2ValidationError(
                    f"Ungültiger lifeStatus bei {member.memberId}: {member.lifeStatus!r}.")
            if (member.lifeStatus == "dead" and (
                    not isinstance(member.burialType, str)
                    or member.burialType not in BURIAL_TYPES)
                    or member.lifeStatus != "dead" and member.burialType is not None):
                raise IdentityV2ValidationError(
                    f"Invalid burialType for {member.memberId}: {member.burialType!r}.")
            for field_name, low, high in (
                    ("portraitOffsetX", -1.0, 1.0),
                    ("portraitOffsetY", -1.0, 1.0),
                    ("portraitZoom", 1.0, 2.0),
                    ("textOffsetX", -1.0, 1.0),
                    ("textOffsetY", -1.0, 1.0),
                    ("textScale", 0.65, 1.5)):
                value = getattr(member, field_name)
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or not isfinite(value) or not low <= value <= high):
                    raise IdentityV2ValidationError(
                        f"Invalid {field_name} for {member.memberId}: {value!r}.")
            if member.graveTemplateId is not None:
                template_id = member.graveTemplateId
                if (not isinstance(template_id, str) or len(template_id) > 120
                        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", template_id) is None):
                    raise IdentityV2ValidationError(
                        f"Invalid graveTemplateId for {member.memberId}.")
                previous = grave_owner.setdefault(template_id, member.memberId)
                if previous != member.memberId:
                    raise IdentityV2ValidationError(
                        f"graveTemplateId {template_id!r} already belongs to {previous}.")
            if member.currentRole is not None and member.currentRole not in CURRENT_ROLES:
                raise IdentityV2ValidationError(
                    f"Ungültige currentRole bei {member.memberId}: {member.currentRole!r}.")
            if member.playerId is not None and member.playerId not in players:
                raise IdentityV2ValidationError(
                    f"Unbekannte playerId bei {member.memberId}: {member.playerId!r}.")
            if member.clmGuid is not None:
                key = member.clmGuid.casefold()
                if key in ignored_clm_guids:
                    raise IdentityV2ValidationError(
                        f"Ignorierte CLM-GUID {member.clmGuid!r} ist einem Member zugeordnet.")
                previous = guid_owner.setdefault(key, member.memberId)
                if previous != member.memberId:
                    raise IdentityV2ValidationError(
                        f"clmGuid {member.clmGuid!r} gehört bereits zu {previous}.")
            predecessor_id = member.continuationOfMemberId
            if predecessor_id is not None:
                if predecessor_id == member.memberId:
                    raise IdentityV2ValidationError(
                        f"Member {member.memberId} darf nicht auf sich selbst verweisen.")
                if predecessor_id not in members:
                    raise IdentityV2ValidationError(
                        f"Unbekannter Vorgänger {predecessor_id!r} bei {member.memberId}.")
                predecessor_player = members[predecessor_id].playerId
                if member.playerId and predecessor_player and member.playerId != predecessor_player:
                    raise IdentityV2ValidationError(
                        f"Fortsetzung {member.memberId} -> {predecessor_id} hat widersprüchliche playerId.")

        historical_guid_owners: dict[str, str] = {}
        for guid, member_id in self.legacyClmGuidMemberMap.items():
            if not guid.strip():
                raise IdentityV2ValidationError("Historische CLM-GUID darf nicht leer sein.")
            if member_id not in members:
                raise IdentityV2ValidationError(
                    f"Unbekannter Member in legacyClmGuidMemberMap: {member_id!r}.")
            key = guid.casefold()
            if key in ignored_clm_guids:
                raise IdentityV2ValidationError(
                    f"Ignorierte CLM-GUID {guid!r} ist historisch einem Member zugeordnet.")
            previous = historical_guid_owners.get(key)
            if previous is not None:
                raise IdentityV2ValidationError(
                    f"Historische clmGuid {guid!r} ist mehrfach oder widersprüchlich zugeordnet.")
            historical_guid_owners[key] = member_id
            primary_owner = guid_owner.get(key)
            if primary_owner is not None and primary_owner != member_id:
                raise IdentityV2ValidationError(
                    f"clmGuid {guid!r} ist primär {primary_owner}, historisch aber {member_id} zugeordnet.")

        _validate_continuation_cycles(members)
        _validate_continuation_players(members)
        resolved_guid_owners = dict(historical_guid_owners)
        resolved_guid_owners.update(guid_owner)
        for player in self.players:
            if player.mainSinceDate is not None and not _is_iso_day(player.mainSinceDate):
                raise IdentityV2ValidationError(
                    f"Invalid mainSinceDate for {player.playerId}.")
            restore = player.inactiveRestoreStates
            if restore is not None:
                if not isinstance(restore, dict) or any(
                        not isinstance(member_id, str) or not member_id.strip()
                        or not isinstance(status, str)
                        or status not in {"active", "inactive"}
                        for member_id, status in restore.items()):
                    raise IdentityV2ValidationError(
                        f"Ungültiger Inaktiv-Wiederherstellungszustand bei {player.playerId}.")
                if any(members.get(member_id) is None
                       or members[member_id].playerId != player.playerId
                       for member_id in restore):
                    raise IdentityV2ValidationError(
                        f"Inaktiv-Wiederherstellungszustand gehört nicht zu {player.playerId}.")
                if any(member.playerId == player.playerId
                       and member.lifeStatus not in {"inactive", "dead"}
                       for member in self.members):
                    raise IdentityV2ValidationError(
                        f"Inaktiver Player {player.playerId} hat einen aktiven Charakter.")
            if player.mainMemberId is None and player.mainSinceDate is not None:
                raise IdentityV2ValidationError(
                    f"mainSinceDate requires a current Main for {player.playerId}.")
            if player.mainMemberId is None:
                continue
            main = members.get(player.mainMemberId)
            if main is None:
                raise IdentityV2ValidationError(
                    f"Unbekannte mainMemberId {player.mainMemberId!r} bei Player {player.playerId}.")
            if main.playerId != player.playerId:
                raise IdentityV2ValidationError(
                    f"Main-Member {main.memberId} gehört nicht zu Player {player.playerId}.")
            if main.lifeStatus not in {"active", "inactive"}:
                raise IdentityV2ValidationError(
                    f"Main-Member {main.memberId} von Player {player.playerId} ist tot.")

        history_ids: set[str] = set()
        for player in self.players:
            if not isinstance(player.mainHistory, list):
                raise IdentityV2ValidationError("Player.mainHistory must be a list.")
            for item in player.mainHistory:
                if not isinstance(item, MainHistoryEntry):
                    raise IdentityV2ValidationError("Player.mainHistory contains an invalid entry.")
                if (not isinstance(item.historyId, str)
                        or re.fullmatch(r"mh\d{4,}", item.historyId) is None
                        or item.historyId in history_ids):
                    raise IdentityV2ValidationError("MainHistory.historyId must be unique.")
                history_ids.add(item.historyId)
                if not isinstance(item.memberId, str) or not item.memberId:
                    raise IdentityV2ValidationError(
                        f"Invalid MainHistory memberId for {item.historyId}.")
                member = members.get(item.memberId)
                if member is None or member.playerId != player.playerId:
                    raise IdentityV2ValidationError(
                        f"MainHistory {item.historyId} references a member outside its Player.")
                if (item.fromDate is not None and not _is_iso_day(item.fromDate)
                        or item.toDate is not None and not _is_iso_day(item.toDate)):
                    raise IdentityV2ValidationError(
                        f"Invalid MainHistory date for {item.historyId}.")
                if (item.fromDate is not None and item.toDate is not None
                        and item.fromDate > item.toDate):
                    raise IdentityV2ValidationError(
                        f"MainHistory {item.historyId} starts after it ends.")
                if not isinstance(item.source, str) or item.source not in MAIN_HISTORY_SOURCES:
                    raise IdentityV2ValidationError(
                        f"Invalid MainHistory source for {item.historyId}.")
                if (item.reason is not None and
                        (not isinstance(item.reason, str)
                         or item.reason not in MAIN_HISTORY_REASONS)):
                    raise IdentityV2ValidationError(
                        f"Invalid MainHistory reason for {item.historyId}.")
                if (item.source == "manual" and item.reason not in (None, "manual")
                        or item.source == "automatic" and item.reason == "manual"):
                    raise IdentityV2ValidationError(
                        f"MainHistory source/reason mismatch for {item.historyId}.")

        attendance_by_raid_member: dict[tuple[str, str], Attendance] = {}
        for entry in self.attendance:
            if entry.attendanceType not in ATTENDANCE_TYPES:
                raise IdentityV2ValidationError(
                    f"Ungültiger attendanceType bei {entry.attendanceId}: "
                    f"{entry.attendanceType!r}.")
            if entry.raidId not in raids:
                raise IdentityV2ValidationError(f"Unbekannter Raid bei Attendance {entry.attendanceId}.")
            if entry.memberId not in members:
                raise IdentityV2ValidationError(f"Unbekanntes Member bei Attendance {entry.attendanceId}.")
            if (entry.clmGuid is not None
                    and (not isinstance(entry.clmGuid, str)
                         or resolved_guid_owners.get(entry.clmGuid.casefold()) != entry.memberId)):
                raise IdentityV2ValidationError(
                    f"CLM-GUID bei Attendance {entry.attendanceId} gehört nicht zu {entry.memberId}.")
            if entry.playerId is not None and entry.playerId not in players:
                raise IdentityV2ValidationError(f"Unbekannter Player bei Attendance {entry.attendanceId}.")
            attendance_by_raid_member[(entry.raidId, entry.memberId)] = entry
            # Recorded ownership may differ from the Member's current assignment.
            # Only an explicit owner correction changes historical Attendance.playerId.
        for resolution in self.raidCreditResolutions:
            if resolution.raidId not in raids:
                raise IdentityV2ValidationError(f"Unbekannter Raid in RaidCreditResolution {resolution.raidId}.")
            if resolution.playerId not in players:
                raise IdentityV2ValidationError(f"Unbekannter Player in RaidCreditResolution {resolution.playerId}.")
            if resolution.creditedMemberId not in members:
                raise IdentityV2ValidationError(
                    f"Unbekanntes Member in RaidCreditResolution {resolution.creditedMemberId}.")
            credited_member = members[resolution.creditedMemberId]
            credited_entry = attendance_by_raid_member.get(
                (resolution.raidId, resolution.creditedMemberId))
            has_attendance = (credited_entry is not None
                              and (credited_entry.playerId == resolution.playerId
                                   or credited_member.playerId == resolution.playerId))
            if not has_attendance:
                raise IdentityV2ValidationError(
                    "RaidCreditResolution muss ein teilnehmendes Member desselben Players referenzieren.")
        _unique(( (r.raidId, r.playerId) for r in self.raidCreditResolutions ),
                "RaidCreditResolution(raidId, playerId)")
        for record in self.eternalDkpRecords:
            record_guid_owner = (
                resolved_guid_owners.get(record.clmGuid.casefold())
                if isinstance(record.clmGuid, str) else None)
            if record.memberId not in members:
                raise IdentityV2ValidationError(f"Unbekanntes Member bei EternalDkpRecord {record.recordId}.")
            if record_guid_owner != record.memberId:
                raise IdentityV2ValidationError(
                    f"GUID von EternalDkpRecord {record.recordId} stimmt nicht mit dem Member überein.")

    def to_payload(self) -> dict[str, Any]:
        self.validate()
        payload = {
            "identityFormat": IDENTITY_FORMAT,
            "players": [item.to_dict() for item in self.players],
            "members": [item.to_dict() for item in self.members],
            "raids": [item.to_dict() for item in self.raids],
            "attendance": [item.to_dict() for item in self.attendance],
            "raidCreditResolutions": [item.to_dict() for item in self.raidCreditResolutions],
            "eternalDkpRecords": [item.to_dict() for item in self.eternalDkpRecords],
            "legacyClmGuidMemberMap": dict(self.legacyClmGuidMemberMap),
            "pointMode": self.pointMode,
            "guildName": self.guildName,
            "realm": self.realm,
        }
        if self.clmRosterName is not None:
            payload["clmRosterName"] = self.clmRosterName
        for field_name in ("clmLuaPath", "clmDatabaseId", "clmRosterId"):
            value = getattr(self, field_name)
            if value is not None:
                payload[field_name] = value
        if self.ignoredCsvCharacterNames:
            payload["ignoredCsvCharacterNames"] = list(self.ignoredCsvCharacterNames)
        if self.ignoredClmCharacterGroups:
            payload["ignoredClmCharacterGroups"] = [
                item.to_dict() for item in self.ignoredClmCharacterGroups
            ]
        if self.nextPlayerNumber > FIRST_PLAYER_NUMBER:
            payload["nextPlayerNumber"] = self.nextPlayerNumber
        if self.nextMainHistoryNumber > FIRST_MAIN_HISTORY_NUMBER:
            payload["nextMainHistoryNumber"] = self.nextMainHistoryNumber
        if self.raidPoints.adjustments or self.raidPoints.member_adjustments:
            payload["raidPoints"] = self.raidPoints.to_dict()
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "IdentityV2Store":
        if not isinstance(payload, dict) or payload.get("identityFormat") != IDENTITY_FORMAT:
            raise IdentityV2ValidationError("Datei ist nicht explizit als Identity V2 gekennzeichnet.")
        players = [Player.from_dict(x) for x in _list_of_dicts(payload, "players")]
        if "nextMainHistoryNumber" in payload:
            next_history_number = payload["nextMainHistoryNumber"]
        else:
            next_history_number = max([
                FIRST_MAIN_HISTORY_NUMBER,
                *(int(item.historyId[2:]) + 1
                  for player in players for item in player.mainHistory
                  if isinstance(item.historyId, str)
                  and re.fullmatch(r"mh\d{4,}", item.historyId) is not None),
            ])
        store = cls(
            players=players,
            members=[Member.from_dict(x) for x in _list_of_dicts(payload, "members")],
            raids=[Raid.from_dict(x) for x in _list_of_dicts(payload, "raids")],
            attendance=[Attendance.from_dict(x) for x in _list_of_dicts(payload, "attendance")],
            raidCreditResolutions=[
                RaidCreditResolution.from_dict(x)
                for x in _list_of_dicts(payload, "raidCreditResolutions")
            ],
            eternalDkpRecords=[
                EternalDkpRecord.from_dict(x)
                for x in _list_of_dicts(payload, "eternalDkpRecords")
            ],
            legacyClmGuidMemberMap=_guid_member_map(payload.get("legacyClmGuidMemberMap", {})),
            ignoredCsvCharacterNames=_string_list(
                payload.get("ignoredCsvCharacterNames", []), "ignoredCsvCharacterNames",
            ),
            ignoredClmCharacterGroups=[
                IgnoredClmCharacterGroup.from_dict(item)
                for item in _list_of_dicts(payload, "ignoredClmCharacterGroups")
            ],
            nextPlayerNumber=payload.get("nextPlayerNumber", FIRST_PLAYER_NUMBER),
            nextMainHistoryNumber=next_history_number,
            raidPoints=(RaidPointState.from_dict(payload["raidPoints"])
                        if "raidPoints" in payload else _v2_raid_point_state()),
            pointMode=payload.get("pointMode", POINT_MODE_RAID),
            clmRosterName=payload.get("clmRosterName"),
            clmLuaPath=payload.get("clmLuaPath"),
            clmDatabaseId=payload.get("clmDatabaseId"),
            clmRosterId=payload.get("clmRosterId"),
            guildName=payload.get("guildName", ""),
            realm=payload.get("realm", ""),
        )
        store.validate()
        return store

    def member_id_for_clm_guid(self, clm_guid: str) -> str | None:
        self.validate()
        return self._resolved_member_id_for_clm_guid(clm_guid)

    def create_player(self, display_name: str) -> Player:
        """Create an unassigned Player; membership and Main changes are separate work."""
        self.validate()
        return self._append_player(display_name)

    def _append_player(self, display_name: str) -> Player:
        """Append on a validated working copy; the caller validates its final state."""
        if not isinstance(display_name, str) or not display_name.strip():
            raise IdentityV2ValidationError("Player benötigt einen nichtleeren displayName.")
        next_number = self.nextPlayerNumber
        existing_ids = {player.playerId for player in self.players}
        for player_id in existing_ids:
            if player_id.startswith("p") and player_id[1:].isdigit():
                next_number = max(next_number, int(player_id[1:]) + 1)
        player_id = player_id_from_number(next_number)
        while player_id in existing_ids:
            next_number += 1
            player_id = player_id_from_number(next_number)
        player = Player(player_id, display_name)
        self.players.append(player)
        self.nextPlayerNumber = next_number + 1
        return player

    def _append_main_history(self, player: Player, member_id: str,
                             from_date: str | None, to_date: str | None,
                             source: str, reason: str | None) -> MainHistoryEntry:
        """Allocate a stable ID on an already validated working copy."""
        existing = {item.historyId for owner in self.players
                    for item in owner.mainHistory}
        number = self.nextMainHistoryNumber
        for history_id in existing:
            if history_id.startswith("mh") and history_id[2:].isdigit():
                number = max(number, int(history_id[2:]) + 1)
        history_id = main_history_id_from_number(number)
        while history_id in existing:
            number += 1
            history_id = main_history_id_from_number(number)
        entry = MainHistoryEntry(history_id, member_id, from_date, to_date,
                                 source, reason)
        player.mainHistory.append(entry)
        self.nextMainHistoryNumber = number + 1
        return entry

    def get_player(self, player_id: str) -> Player | None:
        self.validate()
        return next((player for player in self.players
                     if player.playerId == player_id), None)

    def get_players(self) -> tuple[Player, ...]:
        self.validate()
        return tuple(self.players)

    def get_members_for_player(self, player_id: str) -> tuple[Member, ...]:
        self.validate()
        if not any(player.playerId == player_id for player in self.players):
            raise KeyError(player_id)
        return tuple(member for member in self.members if member.playerId == player_id)

    def player_is_active(self, player_id: str) -> bool:
        player = self.get_player(player_id)
        if player is None:
            raise KeyError(player_id)
        self.validate()
        return player.inactiveRestoreStates is None

    def get_unassigned_members(self) -> tuple[Member, ...]:
        self.validate()
        return tuple(member for member in self.members if member.playerId is None)

    def get_main_member(self, player_id: str) -> Member | None:
        self.validate()
        player = next((item for item in self.players if item.playerId == player_id), None)
        if player is None:
            raise KeyError(player_id)
        if player.mainMemberId is None:
            return None
        return next((member for member in self.members
                     if member.memberId == player.mainMemberId), None)

    def get_player_for_member(self, member_id: str) -> Player | None:
        self.validate()
        member = next((item for item in self.members if item.memberId == member_id), None)
        if member is None:
            raise KeyError(member_id)
        return next((player for player in self.players
                     if player.playerId == member.playerId), None)

    def _resolved_member_id_for_clm_guid(self, clm_guid: str) -> str | None:
        key = clm_guid.casefold()
        for member in self.members:
            if member.clmGuid is not None and member.clmGuid.casefold() == key:
                return member.memberId
        for guid, member_id in self.legacyClmGuidMemberMap.items():
            if guid.casefold() == key:
                return member_id
        return None

    def continuation_component(self, member_id: str) -> frozenset[str]:
        """Return IDs connected through predecessor links; no Member is merged."""
        self.validate()
        members = {m.memberId: m for m in self.members}
        if member_id not in members:
            raise KeyError(member_id)
        edges: dict[str, set[str]] = {key: set() for key in members}
        for member in self.members:
            if member.continuationOfMemberId:
                edges[member.memberId].add(member.continuationOfMemberId)
                edges[member.continuationOfMemberId].add(member.memberId)
        component, pending = set(), [member_id]
        while pending:
            current = pending.pop()
            if current in component:
                continue
            component.add(current)
            pending.extend(edges[current] - component)
        return frozenset(component)

    def eternal_dkp_for_member(self, member_id: str) -> float:
        totals = self.eternal_dkp_by_member()
        if member_id not in totals:
            raise KeyError(member_id)
        return totals[member_id]

    def eternal_dkp_by_member(self) -> dict[str, float]:
        """Aggregate the validated CLM records for all members in one pass."""
        self.validate()
        totals = {member.memberId: 0 for member in self.members}
        for record in self.eternalDkpRecords:
            totals[record.memberId] += record.value
        return totals

    def is_csv_character_ignored(self, name: str) -> bool:
        key = _normalize_csv_ignore(name)
        return key in {_normalize_csv_ignore(item)
                       for item in self.ignoredCsvCharacterNames}

    def ignore_csv_character(self, name: str) -> None:
        key = _normalize_csv_ignore(name)
        if not key:
            raise IdentityV2ValidationError("CSV-Charaktername darf nicht leer sein.")
        existing = {_normalize_csv_ignore(item) for item in self.ignoredCsvCharacterNames}
        if key not in existing:
            self.ignoredCsvCharacterNames.append(key)

    def unignore_csv_character(self, name: str) -> None:
        key = _normalize_csv_ignore(name)
        self.ignoredCsvCharacterNames = [
            item for item in self.ignoredCsvCharacterNames
            if _normalize_csv_ignore(item) != key
        ]

    def is_clm_character_group_ignored(self, clm_guids: Iterable[str]) -> bool:
        key = frozenset(str(guid).casefold() for guid in clm_guids)
        return any(frozenset(guid.casefold() for guid in item.clmGuids) == key
                   for item in self.ignoredClmCharacterGroups)

    def ignore_clm_character_group(self, name: str, clm_guids: Iterable[str]) -> None:
        guids = tuple(dict.fromkeys(str(guid).strip() for guid in clm_guids if str(guid).strip()))
        if not guids:
            raise IdentityV2ValidationError("CLM-Ignorieren benötigt mindestens eine GUID.")
        if not self.is_clm_character_group_ignored(guids):
            self.ignoredClmCharacterGroups.append(IgnoredClmCharacterGroup(name, guids))

    def unignore_clm_character_group(self, clm_guids: Iterable[str]) -> None:
        key = frozenset(str(guid).casefold() for guid in clm_guids)
        self.ignoredClmCharacterGroups = [
            item for item in self.ignoredClmCharacterGroups
            if frozenset(guid.casefold() for guid in item.clmGuids) != key
        ]

    def eternal_dkp_for_continuation(self, member_id: str) -> float:
        component = self.continuation_component(member_id)
        return sum(record.value for record in self.eternalDkpRecords if record.memberId in component)

    def eternal_dkp_for_player(self, player_id: str) -> float:
        self.validate()
        if player_id not in {player.playerId for player in self.players}:
            raise KeyError(player_id)
        components: set[frozenset[str]] = set()
        for member in self.members:
            if member.playerId == player_id:
                components.add(self.continuation_component(member.memberId))
        return sum(
            record.value for record in self.eternalDkpRecords
            if any(record.memberId in component for component in components)
        )


def _validate_continuation_cycles(members: dict[str, Member]) -> None:
    for start in members:
        seen: set[str] = set()
        current: str | None = start
        while current is not None:
            if current in seen:
                raise IdentityV2ValidationError(f"Zyklus in Fortsetzungsbeziehungen bei {current}.")
            seen.add(current)
            current = members[current].continuationOfMemberId


def _validate_continuation_players(members: dict[str, Member]) -> None:
    links: dict[str, set[str]] = {member_id: set() for member_id in members}
    for member in members.values():
        predecessor = member.continuationOfMemberId
        if predecessor is not None:
            links[member.memberId].add(predecessor)
            links[predecessor].add(member.memberId)
    visited: set[str] = set()
    for start in members:
        if start in visited:
            continue
        component: set[str] = set()
        pending = [start]
        player_ids: set[str] = set()
        while pending:
            member_id = pending.pop()
            if member_id in component:
                continue
            component.add(member_id)
            visited.add(member_id)
            player_id = members[member_id].playerId
            if player_id is not None:
                player_ids.add(player_id)
            pending.extend(links[member_id] - component)
        if len(player_ids) > 1:
            raise IdentityV2ValidationError(
                f"Fortsetzungskomponente {sorted(component)} hat widersprüchliche playerId.")


def _unique(values: Iterable[Any], label: str) -> None:
    seen: set[Any] = set()
    for value in values:
        if value in seen:
            raise IdentityV2ValidationError(f"Doppelter Wert für {label}: {value!r}.")
        seen.add(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _literal_text(value: Any) -> str:
    return str(value) if value is not None else ""


def _required_literal_text(data: dict[str, Any], key: str) -> str:
    value = _literal_text(data.get(key))
    if not value.strip():
        raise IdentityV2ValidationError(f"Pflichtfeld {key!r} fehlt oder ist leer.")
    return value


def _optional_literal_text(value: Any) -> str | None:
    return _literal_text(value) if value is not None else None


def _optional_class_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise IdentityV2ValidationError("Member.className muss eine Klasse oder None sein.")
    return value


def _normalize_csv_ignore(value: object) -> str:
    return unicodedata.normalize("NFC", str(value or "").strip()).casefold()


def _required_text(data: dict[str, Any], key: str) -> str:
    value = _text(data.get(key))
    if not value:
        raise IdentityV2ValidationError(f"Pflichtfeld {key!r} fehlt oder ist leer.")
    return value


def _optional_text(value: Any) -> str | None:
    return _text(value) or None


def _source_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if (not isinstance(value, (list, tuple))
            or any(not isinstance(item, str) or not item for item in value)):
        raise IdentityV2ValidationError("CSV-Quellwerte müssen nichtleere Textlisten sein.")
    if len(set(value)) != len(value):
        raise IdentityV2ValidationError("CSV-Quellwerte dürfen nicht doppelt sein.")
    return tuple(value)


def _list_of_dicts(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise IdentityV2ValidationError(f"{key} muss eine Liste von Objekten sein.")
    return value


def _string_list(value: Any, key: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise IdentityV2ValidationError(f"{key} muss eine Liste von Texten sein.")
    return value


def _guid_member_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise IdentityV2ValidationError("legacyClmGuidMemberMap muss ein Objekt sein.")
    result: dict[str, str] = {}
    for guid, member_id in value.items():
        clean_guid, clean_member_id = _text(guid), _text(member_id)
        if not clean_guid or not clean_member_id:
            raise IdentityV2ValidationError("legacyClmGuidMemberMap enthält eine leere GUID oder Member-ID.")
        result[clean_guid] = clean_member_id
    return result
