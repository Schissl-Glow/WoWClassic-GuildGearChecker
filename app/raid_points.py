"""GUI-unabhängige Fachlogik für interne Raidpunkte.

Basispunkte werden immer aus ``RaidAttendance.status`` abgeleitet. Persistiert
werden ausschließlich der Aktivierungszustand, berücksichtigte Raid-IDs und
manuelle Anpassungen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping


BASE_POINTS_BY_STATUS = {"present": 10, "bench": 5}


class RaidPointsError(ValueError):
    """Ungültige Punktedaten oder widersprüchliche Raidereignisse."""


@dataclass(frozen=True)
class RaidPointConflict:
    raid_id: str
    player_id: str
    attendance_ids: tuple[str, ...]
    member_ids: tuple[str, ...]


class RaidPointConflictError(RaidPointsError):
    def __init__(self, conflicts: Iterable[RaidPointConflict]) -> None:
        self.conflicts = tuple(conflicts)
        super().__init__("Derselbe Spieler ist in mindestens einem Raid mehrfach enthalten.")


@dataclass(frozen=True)
class ManualRaidPointAdjustment:
    attendance_id: str
    value: int
    reason: str

    def __post_init__(self) -> None:
        attendance_id = str(self.attendance_id or "").strip()
        reason = str(self.reason or "").strip()
        if not attendance_id:
            raise RaidPointsError("Eine manuelle Anpassung benötigt eine Attendance-ID.")
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise RaidPointsError("Die manuelle Anpassung muss eine ganze Zahl sein.")
        if self.value and not reason:
            raise RaidPointsError("Eine echte manuelle Anpassung benötigt eine Begründung.")
        object.__setattr__(self, "attendance_id", attendance_id)
        object.__setattr__(self, "reason", reason)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ManualRaidPointAdjustment":
        raw_value = data.get("value", 0)
        if isinstance(raw_value, bool):
            raise RaidPointsError("Die manuelle Anpassung muss eine ganze Zahl sein.")
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise RaidPointsError("Die manuelle Anpassung muss eine ganze Zahl sein.") from exc
        return cls(
            attendance_id=str(data.get("attendanceId") or ""),
            value=value,
            reason=str(data.get("reason") or ""),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "attendanceId": self.attendance_id,
            "value": self.value,
            "reason": self.reason,
        }


@dataclass
class RaidPointState:
    enabled: bool = False
    ever_enabled: bool = False
    included_raid_ids: set[str] = field(default_factory=set)
    pending_raid_ids: set[str] = field(default_factory=set)
    adjustments: dict[str, ManualRaidPointAdjustment] = field(default_factory=dict)
    excluded_attendance_ids: set[str] = field(default_factory=set)
    calculation_mode: str | None = None
    calculation_start_date: str | None = None

    @classmethod
    def from_dict(cls, data: object) -> "RaidPointState":
        if data in (None, {}):
            return cls()
        if not isinstance(data, Mapping):
            raise RaidPointsError("Ungültige Raidpunkte-Konfiguration.")
        raw_raid_ids = data.get("includedRaidIds", [])
        raw_pending_ids = data.get("pendingRaidIds", [])
        raw_adjustments = data.get("adjustments", [])
        raw_excluded_ids = data.get("excludedAttendanceIds", [])
        if (not isinstance(raw_raid_ids, list) or not isinstance(raw_pending_ids, list)
                or not isinstance(raw_adjustments, list)
                or not isinstance(raw_excluded_ids, list)):
            raise RaidPointsError("Ungültige Raidpunkte-Konfiguration.")
        raw_enabled = data.get("enabled", False)
        raw_ever_enabled = data.get("everEnabled", False)
        if not isinstance(raw_enabled, bool) or not isinstance(raw_ever_enabled, bool):
            raise RaidPointsError("Ungültiger Aktivierungszustand des Punktesystems.")
        included = {str(raid_id).strip() for raid_id in raw_raid_ids if str(raid_id).strip()}
        pending = {str(raid_id).strip() for raid_id in raw_pending_ids if str(raid_id).strip()}
        adjustments: dict[str, ManualRaidPointAdjustment] = {}
        for raw in raw_adjustments:
            if not isinstance(raw, Mapping):
                raise RaidPointsError("Ungültige manuelle Raidpunkte-Anpassung.")
            adjustment = ManualRaidPointAdjustment.from_dict(raw)
            if adjustment.attendance_id in adjustments:
                raise RaidPointsError("Doppelte manuelle Raidpunkte-Anpassung.")
            if adjustment.value:
                adjustments[adjustment.attendance_id] = adjustment
        mode = data.get("calculationMode")
        start = data.get("calculationStartDate")
        if mode is not None and mode not in {"all", "from_date"}:
            raise RaidPointsError("Ungültiger Raidpunkte-Berechnungsmodus.")
        if mode == "from_date" and (not isinstance(start, str) or len(start) != 10):
            raise RaidPointsError("Für Raidpunkte ab Datum fehlt ein gültiges Datum.")
        return cls(
            enabled=raw_enabled,
            ever_enabled=raw_ever_enabled or raw_enabled,
            included_raid_ids=included,
            pending_raid_ids=pending - included,
            adjustments=adjustments,
            excluded_attendance_ids={
                str(attendance_id).strip() for attendance_id in raw_excluded_ids
                if str(attendance_id).strip()
            },
            calculation_mode=mode,
            calculation_start_date=start if mode == "from_date" else None,
        )

    def to_dict(self) -> dict[str, object]:
        data = {
            "enabled": self.enabled,
            "everEnabled": self.ever_enabled,
            "includedRaidIds": sorted(self.included_raid_ids),
            "pendingRaidIds": sorted(self.pending_raid_ids),
            "adjustments": [
                self.adjustments[key].to_dict() for key in sorted(self.adjustments)
            ],
            "excludedAttendanceIds": sorted(self.excluded_attendance_ids),
        }
        if self.calculation_mode is not None:
            data["calculationMode"] = self.calculation_mode
            data["calculationStartDate"] = self.calculation_start_date
        return data

    def set_calculation_scope(self, mode: str, start_date: str | None = None) -> None:
        if mode not in {"all", "from_date"}:
            raise RaidPointsError("Ungültiger Raidpunkte-Berechnungsmodus.")
        if mode == "from_date" and (not start_date or len(start_date) != 10):
            raise RaidPointsError("Für Raidpunkte ab Datum fehlt ein gültiges Datum.")
        self.calculation_mode = mode
        self.calculation_start_date = start_date if mode == "from_date" else None

    def rebuild_scope(self, raids: Iterable[object]) -> None:
        if self.calculation_mode is None:
            return
        self.included_raid_ids = {
            str(getattr(raid, "id", "")) for raid in raids
            if getattr(raid, "status", "") == "recorded"
            and (self.calculation_mode == "all" or str(getattr(raid, "date", "")) >= str(self.calculation_start_date))
        }
        self.pending_raid_ids.clear()

    def activate(self, current_raid_ids: Iterable[str], *, include_existing: bool) -> None:
        raid_ids = {str(raid_id).strip() for raid_id in current_raid_ids if str(raid_id).strip()}
        if not self.ever_enabled:
            if include_existing:
                self.included_raid_ids.update(raid_ids)
        elif include_existing:
            self.included_raid_ids.update(self.pending_raid_ids)
            self.pending_raid_ids.clear()
        self.enabled = True
        self.ever_enabled = True

    def deactivate(self) -> None:
        self.enabled = False

    def register_raid(self, raid_id: str) -> None:
        normalized = str(raid_id or "").strip()
        if not normalized:
            raise RaidPointsError("Eine Raid-ID darf nicht leer sein.")
        if self.enabled:
            self.included_raid_ids.add(normalized)
            self.pending_raid_ids.discard(normalized)
        elif self.ever_enabled and normalized not in self.included_raid_ids:
            self.pending_raid_ids.add(normalized)

    def include_raids(self, raid_ids: Iterable[str]) -> None:
        included = {str(raid_id).strip() for raid_id in raid_ids if str(raid_id).strip()}
        self.included_raid_ids.update(included)
        self.pending_raid_ids.difference_update(included)

    def remove_raid(self, raid_id: str, attendance_ids: Iterable[str] = ()) -> None:
        self.included_raid_ids.discard(str(raid_id or "").strip())
        self.pending_raid_ids.discard(str(raid_id or "").strip())
        self.remove_adjustments(attendance_ids)

    def remove_adjustments(self, attendance_ids: Iterable[str]) -> None:
        for attendance_id in attendance_ids:
            normalized = str(attendance_id or "").strip()
            self.adjustments.pop(normalized, None)
            self.excluded_attendance_ids.discard(normalized)

    def exclude_attendance(self, attendance_ids: Iterable[str]) -> None:
        self.excluded_attendance_ids.update(
            str(attendance_id).strip() for attendance_id in attendance_ids
            if str(attendance_id).strip()
        )

    def set_adjustment(self, attendance_id: str, value: int, reason: str = "") -> None:
        if not self.enabled:
            raise RaidPointsError(
                "Manuelle Anpassungen sind bei deaktiviertem Punktesystem nicht zulässig."
            )
        adjustment = ManualRaidPointAdjustment(attendance_id, value, reason)
        if value:
            self.adjustments[adjustment.attendance_id] = adjustment
        else:
            self.adjustments.pop(adjustment.attendance_id, None)


@dataclass(frozen=True)
class RaidPointEntry:
    attendance_id: str
    raid_id: str
    date: str
    raid_name: str
    player_id: str
    member_id: str
    character_name: str
    attendance_status: str
    base_points: int
    adjustment: int
    reason: str
    total_points: int


def base_points_for_status(status: object) -> int:
    normalized = str(status or "").strip()
    try:
        return BASE_POINTS_BY_STATUS[normalized]
    except KeyError as exc:
        raise RaidPointsError(f"Nicht unterstützter Attendance-Status: {normalized or '–'}") from exc


def detect_point_conflicts(
    attendance: Iterable[object], included_raid_ids: Iterable[str],
    excluded_attendance_ids: Iterable[str] = (),
) -> tuple[RaidPointConflict, ...]:
    included = set(included_raid_ids)
    excluded = set(excluded_attendance_ids)
    grouped: dict[tuple[str, str], list[object]] = {}
    for entry in attendance:
        raid_id = str(getattr(entry, "raidId", ""))
        if raid_id not in included or str(getattr(entry, "id", "")) in excluded:
            continue
        player_id = str(getattr(entry, "playerId", ""))
        grouped.setdefault((raid_id, player_id), []).append(entry)
    return tuple(
        RaidPointConflict(
            raid_id=raid_id,
            player_id=player_id,
            attendance_ids=tuple(str(getattr(entry, "id", "")) for entry in entries),
            member_ids=tuple(str(getattr(entry, "memberId", "")) for entry in entries),
        )
        for (raid_id, player_id), entries in sorted(grouped.items())
        if len(entries) > 1
    )


def build_point_history(
    state: RaidPointState,
    raids: Iterable[object],
    attendance: Iterable[object],
    *,
    player_id: str | None = None,
    member_id: str | None = None,
) -> tuple[RaidPointEntry, ...]:
    if player_id is not None and member_id is not None:
        raise RaidPointsError("Spieler- und Charakterfilter dürfen nicht kombiniert werden.")
    raids_by_id = {str(getattr(raid, "id", "")): raid for raid in raids}
    records = list(attendance)
    conflicts = detect_point_conflicts(
        records, state.included_raid_ids, state.excluded_attendance_ids,
    )
    if conflicts:
        raise RaidPointConflictError(conflicts)

    seen_attendance_ids: set[str] = set()
    result: list[RaidPointEntry] = []
    for entry in records:
        attendance_id = str(getattr(entry, "id", ""))
        raid_id = str(getattr(entry, "raidId", ""))
        entry_player_id = str(getattr(entry, "playerId", ""))
        entry_member_id = str(getattr(entry, "memberId", ""))
        if (raid_id not in state.included_raid_ids or raid_id not in raids_by_id
                or attendance_id in state.excluded_attendance_ids):
            continue
        if attendance_id in seen_attendance_ids:
            raise RaidPointsError(f"Doppelte Attendance-ID in der Punkteprojektion: {attendance_id}")
        seen_attendance_ids.add(attendance_id)
        if player_id is not None and entry_player_id != player_id:
            continue
        if member_id is not None and entry_member_id != member_id:
            continue

        raid = raids_by_id[raid_id]
        status = str(getattr(entry, "status", ""))
        base_points = base_points_for_status(status)
        adjustment = state.adjustments.get(attendance_id)
        adjustment_value = adjustment.value if adjustment else 0
        result.append(RaidPointEntry(
            attendance_id=attendance_id,
            raid_id=raid_id,
            date=str(getattr(raid, "date", "")),
            raid_name=str(getattr(raid, "name", "")),
            player_id=entry_player_id,
            member_id=entry_member_id,
            character_name=str(getattr(entry, "characterNameSnapshot", "")),
            attendance_status=status,
            base_points=base_points,
            adjustment=adjustment_value,
            reason=adjustment.reason if adjustment else "",
            total_points=max(0, base_points + adjustment_value),
        ))
    result.sort(key=lambda item: (item.date, item.raid_id, item.attendance_id))
    return tuple(result)


def player_points(
    state: RaidPointState, raids: Iterable[object], attendance: Iterable[object], player_id: str,
) -> int:
    return sum(
        entry.total_points
        for entry in build_point_history(state, raids, attendance, player_id=player_id)
    )


def character_points(
    state: RaidPointState, raids: Iterable[object], attendance: Iterable[object], member_id: str,
) -> int:
    return sum(
        entry.total_points
        for entry in build_point_history(state, raids, attendance, member_id=member_id)
    )
