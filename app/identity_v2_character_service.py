"""Atomic edits for Identity V2 character data, independent of Qt and files."""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .identity_v2 import BURIAL_TYPES, IdentityV2Store, IdentityV2ValidationError, Member
from .identity_v2_graveyard import reserve_individual_gravestone
from .gravestone_templates import GravestoneTemplate
from .identity_v2_main_history import (
    MainSuccessorSelectionRequired, close_current_main,
    get_main_successor_candidates,
)
from .identity_v2_character_values import (
    CLASS_SPECS, GEAR_STATUSES, RACES, RAID_ROLES, RAID_STATUSES,
    canonical_choice,
)


class CharacterDataError(IdentityV2ValidationError):
    """A requested character edit is invalid."""


class DeathAttendanceConflict(CharacterDataError):
    """A proposed death date precedes stored attendance of this Member."""

    def __init__(self, member_id: str, death_date: str,
                 conflicts: tuple[tuple[str, str], ...]) -> None:
        self.member_id = member_id
        self.death_date = death_date
        self.conflict_count = len(conflicts)
        self.first_raid_date, self.first_raid_id = conflicts[0]
        self.conflicts = conflicts
        super().__init__(
            f"Member {member_id}: {self.conflict_count} Attendance-Einträge nach "
            f"Todesdatum {death_date}; erster Konflikt: Raid {self.first_raid_id} "
            f"am {self.first_raid_date}.")


class BurialTypeError(CharacterDataError):
    """A burial choice is missing, invalid, or applied to a living Member."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"burial_type_{reason}")


class DeathCorrectionError(CharacterDataError):
    """A death correction rejected for a reason the UI can translate."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"death_correction_{reason}")


@dataclass(frozen=True)
class MemberEdit:
    """One proposed V2 character-field change, identified by stable member ID."""

    memberId: str
    field: str
    value: str | None


EDITABLE_FIELDS = frozenset({
    "race", "className", "spec", "raidRole", "gearStatus", "raidStatus", "note",
})


def _apply(store: IdentityV2Store, change: Callable[[IdentityV2Store], None]) -> IdentityV2Store:
    store.validate()
    result = copy.deepcopy(store)
    change(result)
    result.validate()
    return result


def _member(store: IdentityV2Store, member_id: str) -> Member:
    member = next((item for item in store.members if item.memberId == member_id), None)
    if member is None:
        raise CharacterDataError(f"Unbekannter Member: {member_id!r}.")
    return member


def _optional_choice(value: str | None, choices: tuple[str, ...], field_name: str) -> str | None:
    if value is None or value == "":
        return None
    result = canonical_choice(value, choices)
    if result is None:
        raise CharacterDataError(f"Ungültiger Wert für {field_name}: {value!r}.")
    return result


def _required_choice(value: str, choices: tuple[str, ...], field_name: str) -> str:
    result = canonical_choice(value, choices)
    if result is None:
        raise CharacterDataError(f"Ungültiger Wert für {field_name}: {value!r}.")
    return result


def _raid_role_value(value: str | None) -> str:
    aliases = {"main_tank": "tank", "main tank": "tank", "main tanks": "tank"}
    normalized = aliases.get(value.strip().casefold(), value) if isinstance(value, str) else value
    return "not_set" if normalized is None or normalized == "" else _required_choice(
        normalized, RAID_ROLES, "Raid-Rolle")


def _raid_status_value(value: str | None) -> str:
    aliases = {"ready": "Bereit", "not_ready": "Nicht bereit", "not ready": "Nicht bereit"}
    normalized = aliases.get(value.strip().casefold(), value) if isinstance(value, str) else value
    return "" if normalized is None or normalized == "" else _required_choice(
        normalized, RAID_STATUSES, "Raidstatus")


def _iso_day(value: str | date, field_name: str) -> str:
    if type(value) is date:
        return value.isoformat()
    if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise CharacterDataError(f"{field_name} benötigt ein Datum im Format JJJJ-MM-TT.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CharacterDataError(f"Ungültiges {field_name}: {value!r}.") from exc
    if parsed.isoformat() != value:
        raise CharacterDataError(f"{field_name} benötigt ein Datum im Format JJJJ-MM-TT.")
    return value


def set_member_class(store: IdentityV2Store, member_id: str,
                     class_name: str | None) -> IdentityV2Store:
    new_class = _optional_choice(class_name, tuple(CLASS_SPECS), "Klasse")

    def change(result: IdentityV2Store) -> None:
        member = _member(result, member_id)
        member.className = new_class
        if member.spec is not None and (
                new_class is None or member.spec not in CLASS_SPECS[new_class]):
            member.spec = None

    return _apply(store, change)


def set_member_race(store: IdentityV2Store, member_id: str,
                    race: str | None) -> IdentityV2Store:
    new_race = _optional_choice(race, RACES, "Rasse")
    return _apply(store, lambda result: setattr(_member(result, member_id), "race", new_race))


def set_member_spec(store: IdentityV2Store, member_id: str,
                    spec: str | None) -> IdentityV2Store:
    def change(result: IdentityV2Store) -> None:
        member = _member(result, member_id)
        if spec is None or spec == "":
            member.spec = None
            return
        if member.className is None:
            raise CharacterDataError("Spec benötigt eine bekannte Klasse.")
        member.spec = _required_choice(spec, CLASS_SPECS[member.className], "Spec")

    return _apply(store, change)


def set_member_raid_role(store: IdentityV2Store, member_id: str,
                         raid_role: str | None) -> IdentityV2Store:
    role = _raid_role_value(raid_role)
    return _apply(store, lambda result: setattr(_member(result, member_id), "raidRole", role))


def set_member_gear_status(store: IdentityV2Store, member_id: str,
                           gear_status: str) -> IdentityV2Store:
    status = _required_choice(gear_status, GEAR_STATUSES, "Gear")
    return _apply(store, lambda result: setattr(_member(result, member_id), "gearStatus", status))


def set_member_raid_status(store: IdentityV2Store, member_id: str,
                           raid_status: str | None) -> IdentityV2Store:
    status = _raid_status_value(raid_status)
    return _apply(store, lambda result: setattr(_member(result, member_id), "raidStatus", status))


def set_member_note(store: IdentityV2Store, member_id: str, note: str) -> IdentityV2Store:
    if not isinstance(note, str):
        raise CharacterDataError("Notiz muss Text sein.")
    return _apply(store, lambda result: setattr(_member(result, member_id), "note", note.strip()))


def apply_member_edits(
    store: IdentityV2Store, edits: Iterable[MemberEdit],
) -> IdentityV2Store:
    """Apply a rectangular edit batch with one copy and one full validation."""
    proposed = tuple(edits)
    if not proposed:
        return store
    by_member: dict[str, dict[str, str | None]] = {}
    for edit in proposed:
        if not isinstance(edit, MemberEdit):
            raise CharacterDataError("Batch-Edit benötigt MemberEdit-Einträge.")
        if edit.field not in EDITABLE_FIELDS:
            raise CharacterDataError(
                f"Member {edit.memberId}: Feld {edit.field!r} darf hier nicht bearbeitet werden.")
        by_member.setdefault(edit.memberId, {})[edit.field] = edit.value
    result = copy.deepcopy(store)
    members = {member.memberId: member for member in result.members}
    changed = False
    for member_id, fields in by_member.items():
        member = members.get(member_id)
        if member is None:
            raise CharacterDataError(f"Unbekannter Member im Batch: {member_id!r}.")
        before = {field: getattr(member, field) for field in EDITABLE_FIELDS}

        def apply(field: str, operation: Callable[[], object]) -> object:
            try:
                return operation()
            except CharacterDataError as exc:
                raise CharacterDataError(
                    f"{member.name} ({member_id}), {field}={fields[field]!r}: {exc}") from exc

        if "className" in fields:
            member.className = apply("className", lambda: _optional_choice(
                fields["className"], tuple(CLASS_SPECS), "Klasse"))
        if "spec" in fields:
            spec = fields["spec"]
            if spec is None or spec == "":
                member.spec = None
            elif member.className is None:
                raise CharacterDataError(
                    f"{member.name} ({member_id}), spec={spec!r}: Spec benötigt eine bekannte Klasse.")
            else:
                member.spec = apply("spec", lambda: _required_choice(
                    spec, CLASS_SPECS[member.className], "Spec"))
        elif "className" in fields and member.spec is not None and (
                member.className is None or member.spec not in CLASS_SPECS[member.className]):
            member.spec = None
        if "race" in fields:
            member.race = apply("race", lambda: _optional_choice(
                fields["race"], RACES, "Rasse"))
        if "raidRole" in fields:
            member.raidRole = apply("raidRole", lambda: _raid_role_value(fields["raidRole"]))
        if "gearStatus" in fields:
            member.gearStatus = apply("gearStatus", lambda: _required_choice(
                fields["gearStatus"], GEAR_STATUSES, "Gear"))
        if "raidStatus" in fields:
            member.raidStatus = apply("raidStatus", lambda: _raid_status_value(
                fields["raidStatus"]))
        if "note" in fields:
            note = fields["note"]
            if not isinstance(note, str):
                raise CharacterDataError(
                    f"{member.name} ({member_id}), note={note!r}: Notiz muss Text sein.")
            member.note = note.strip()
        changed = changed or any(getattr(member, field) != value
                                 for field, value in before.items())
    if not changed:
        return store
    result.validate()
    return result


def confirm_member_check(store: IdentityV2Store, member_id: str,
                         checked_date: str | date) -> IdentityV2Store:
    checked = _iso_day(checked_date, "Prüfdatum")

    def change(result: IdentityV2Store) -> None:
        member = _member(result, member_id)
        if member.lifeStatus != "active":
            raise CharacterDataError("Nur aktive Charaktere können erneut geprüft werden.")
        member.lastChecked = checked

    return _apply(store, change)


def _check_attendance_before_death(store: IdentityV2Store, member_id: str,
                                   dead_on: str) -> None:
    death_day = date.fromisoformat(dead_on)
    raid_dates = {raid.raidId: raid.date for raid in store.raids}
    conflicts: list[tuple[str, str]] = []
    for entry in store.attendance:
        if entry.memberId != member_id:
            continue
        raid_date = raid_dates.get(entry.raidId)
        try:
            raid_day = date.fromisoformat(raid_date) if raid_date is not None else None
        except (TypeError, ValueError) as exc:
            raise CharacterDataError(
                f"Raid {entry.raidId} hat kein gültiges Datum; Tod kann nicht geprüft werden.") from exc
        if raid_day is None:
            raise CharacterDataError(
                f"Raid {entry.raidId} hat kein Datum; Tod kann nicht geprüft werden.")
        if raid_day > death_day:
            conflicts.append((raid_day.isoformat(), entry.raidId))
    if conflicts:
        raise DeathAttendanceConflict(member_id, dead_on, tuple(sorted(conflicts)))


def mark_member_dead(store: IdentityV2Store, member_id: str,
                     death_date: str | date,
                     burial_type: str | None = None,
                     successor_member_id: str | None = None,
                     *, gravestone_templates: Iterable[GravestoneTemplate] = (),
                     ) -> IdentityV2Store:
    """Mark one incarnation dead without rewriting any historical records."""
    dead_on = _iso_day(death_date, "Todesdatum")
    if not isinstance(burial_type, str) or burial_type not in BURIAL_TYPES:
        raise BurialTypeError("required")
    def change(result: IdentityV2Store) -> None:
        member = _member(result, member_id)
        if member.lifeStatus == "dead":
            raise CharacterDataError(f"Member {member_id} ist bereits tot.")
        _check_attendance_before_death(result, member_id, dead_on)
        player = (next(item for item in result.players if item.playerId == member.playerId)
                  if member.playerId is not None else None)
        successor = None
        if player is not None and player.mainMemberId == member_id:
            candidates = get_main_successor_candidates(
                result, player.playerId, member_id)
            candidate_ids = {item.memberId for item in candidates}
            if not candidates:
                if successor_member_id is not None:
                    raise CharacterDataError("No valid Main successor exists.")
            elif len(candidates) == 1:
                successor = candidates[0].memberId
                if successor_member_id not in (None, successor):
                    raise CharacterDataError("Selected Main successor is not a candidate.")
            else:
                if successor_member_id is None:
                    raise MainSuccessorSelectionRequired(
                        player.playerId, member_id, candidates)
                if successor_member_id not in candidate_ids:
                    raise CharacterDataError("Selected Main successor is not a candidate.")
                successor = successor_member_id
        elif successor_member_id is not None:
            raise CharacterDataError("A successor is only valid for the current Main.")
        if burial_type == "individual":
            reserve_individual_gravestone(result, member, gravestone_templates)
        member.lifeStatus = "dead"
        member.deathDate = dead_on
        member.burialType = burial_type
        if player is not None and player.mainMemberId == member_id:
            close_current_main(result, player, dead_on, "death")
            player.mainMemberId = successor
            player.mainSinceDate = dead_on if successor is not None else None

    return _apply(store, change)


def correct_member_death_date(store: IdentityV2Store, member_id: str,
                              new_date: str | date) -> IdentityV2Store:
    """Correct one dead Member's date without repeating succession or historization."""
    try:
        dead_on = _iso_day(new_date, "Todesdatum")
    except CharacterDataError as exc:
        raise DeathCorrectionError("invalid_date") from exc
    member = _member(store, member_id)
    if member.lifeStatus != "dead":
        raise DeathCorrectionError("living_date")
    if member.deathDate == dead_on:
        return store

    def change(result: IdentityV2Store) -> None:
        _check_attendance_before_death(result, member_id, dead_on)
        _member(result, member_id).deathDate = dead_on

    return _apply(store, change)


def clear_member_death_marking(store: IdentityV2Store, member_id: str,
                               target_life_status: str) -> IdentityV2Store:
    """Undo an accidental death without touching identity, raids, Main or grave assets."""
    if target_life_status not in ("active", "inactive"):
        raise DeathCorrectionError("invalid_target")

    def change(result: IdentityV2Store) -> None:
        member = _member(result, member_id)
        if member.lifeStatus != "dead":
            raise DeathCorrectionError("living_marking")
        member.lifeStatus = target_life_status
        member.deathDate = None
        member.burialType = None

    return _apply(store, change)


def set_member_burial_type(store: IdentityV2Store, member_id: str,
                           burial_type: str, *,
                           gravestone_templates: Iterable[GravestoneTemplate] = (),
                           ) -> IdentityV2Store:
    """Change only the burial decision of an already dead character."""
    if not isinstance(burial_type, str) or burial_type not in BURIAL_TYPES:
        raise BurialTypeError("invalid")

    def change(result: IdentityV2Store) -> None:
        member = _member(result, member_id)
        if member.lifeStatus != "dead":
            raise BurialTypeError("living")
        if burial_type == "individual":
            reserve_individual_gravestone(result, member, gravestone_templates)
        member.burialType = burial_type

    return _apply(store, change)
