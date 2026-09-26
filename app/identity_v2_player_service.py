"""Atomic, UI-independent Player and Member ownership operations for Identity V2."""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable
from datetime import date

from .identity_v2 import (
    IdentityV2Store, IdentityV2ValidationError, Member, Player,
)
from .identity_v2_main_history import _day, close_current_main


class PlayerMembershipError(IdentityV2ValidationError):
    """A requested Player or Member change would violate V2 ownership rules."""


def _apply(
    store: IdentityV2Store, change: Callable[[IdentityV2Store], None],
) -> IdentityV2Store:
    store.validate()
    result = copy.deepcopy(store)
    change(result)
    result.validate()
    return result


def _member(store: IdentityV2Store, member_id: str) -> Member:
    member = next((item for item in store.members if item.memberId == member_id), None)
    if member is None:
        raise PlayerMembershipError(f"Unbekannter Member: {member_id!r}.")
    return member


def _player(store: IdentityV2Store, player_id: str) -> Player:
    player = next((item for item in store.players if item.playerId == player_id), None)
    if player is None:
        raise PlayerMembershipError(f"Unbekannter Player: {player_id!r}.")
    return player


def _set_attendance_owner(
    store: IdentityV2Store, member_id: str, player_id: str | None,
) -> None:
    for entry in store.attendance:
        if entry.memberId == member_id:
            entry.playerId = player_id


def _clear_old_main(store: IdentityV2Store, member: Member) -> None:
    if member.playerId is not None:
        player = _player(store, member.playerId)
        if player.mainMemberId == member.memberId:
            player.mainMemberId = None
            player.mainSinceDate = None


def _require_no_history_for_ownership_change(store: IdentityV2Store,
                                             member: Member) -> None:
    if member.playerId is None:
        return
    player = _player(store, member.playerId)
    if any(item.memberId == member.memberId for item in player.mainHistory):
        raise PlayerMembershipError(
            "Correct historical Main entries before changing Member ownership.")


def create_player_from_member(
    store: IdentityV2Store, member_id: str,
) -> IdentityV2Store:
    """Create a Player and make one active unassigned Member its Main."""
    def change(result: IdentityV2Store) -> None:
        member = _member(result, member_id)
        if member.playerId is not None:
            raise PlayerMembershipError(f"Member {member_id} ist bereits zugeordnet.")
        if member.lifeStatus != "active":
            raise PlayerMembershipError(f"Member {member_id} ist nicht aktiv.")
        player = result.create_player(member.name)
        member.playerId = player.playerId
        player.mainMemberId = member_id
        _set_attendance_owner(result, member_id, player.playerId)

    return _apply(store, change)


def rename_player(
    store: IdentityV2Store, player_id: str, display_name: str,
) -> IdentityV2Store:
    def change(result: IdentityV2Store) -> None:
        player = _player(result, player_id)
        if not isinstance(display_name, str) or not display_name.strip():
            raise PlayerMembershipError("Player benötigt einen nichtleeren displayName.")
        player.displayName = display_name

    return _apply(store, change)


def delete_player(store: IdentityV2Store, player_id: str) -> IdentityV2Store:
    def change(result: IdentityV2Store) -> None:
        player = _player(result, player_id)
        if any(member.playerId == player_id for member in result.members):
            raise PlayerMembershipError(f"Player {player_id} besitzt noch Member.")
        if player.mainHistory:
            raise PlayerMembershipError("Player still owns MainHistory entries.")
        if (any(entry.playerId == player_id for entry in result.attendance)
                or any(item.playerId == player_id for item in result.raidCreditResolutions)):
            raise PlayerMembershipError(
                f"Player {player_id} besitzt noch historische Raid-Referenzen.")
        result.players.remove(player)

    return _apply(store, change)


def assign_member(
    store: IdentityV2Store, member_id: str, player_id: str,
) -> IdentityV2Store:
    def change(result: IdentityV2Store) -> None:
        member = _member(result, member_id)
        _player(result, player_id)
        if member.playerId is not None:
            raise PlayerMembershipError(f"Member {member_id} ist bereits zugeordnet.")
        member.playerId = player_id
        _set_attendance_owner(result, member_id, player_id)

    return _apply(store, change)


def unassign_member(store: IdentityV2Store, member_id: str) -> IdentityV2Store:
    def change(result: IdentityV2Store) -> None:
        member = _member(result, member_id)
        _require_no_history_for_ownership_change(result, member)
        _clear_old_main(result, member)
        member.playerId = None
        _set_attendance_owner(result, member_id, None)

    return _apply(store, change)


def reassign_member(
    store: IdentityV2Store, member_id: str, new_player_id: str,
) -> IdentityV2Store:
    def change(result: IdentityV2Store) -> None:
        member = _member(result, member_id)
        _player(result, new_player_id)
        if member.playerId is None:
            raise PlayerMembershipError(f"Member {member_id} ist nicht zugeordnet.")
        if member.playerId != new_player_id:
            _require_no_history_for_ownership_change(result, member)
            _clear_old_main(result, member)
        member.playerId = new_player_id
        _set_attendance_owner(result, member_id, new_player_id)

    return _apply(store, change)


def set_main(
    store: IdentityV2Store, player_id: str, member_id: str,
    effective_date: str | date | None = None,
) -> IdentityV2Store:
    effective = _day(effective_date, "effectiveDate")

    def change(result: IdentityV2Store) -> None:
        player = _player(result, player_id)
        member = _member(result, member_id)
        if member.playerId != player_id:
            raise PlayerMembershipError(
                f"Member {member_id} gehört nicht zu Player {player_id}.")
        if member.lifeStatus != "active":
            raise PlayerMembershipError(f"Member {member_id} ist nicht aktiv.")
        if player.mainMemberId == member_id:
            return
        close_current_main(result, player, effective, "main_change")
        player.mainMemberId = member_id
        player.mainSinceDate = effective

    return _apply(store, change)


def clear_main(store: IdentityV2Store, player_id: str,
               effective_date: str | date | None = None) -> IdentityV2Store:
    effective = _day(effective_date, "effectiveDate")

    def change(result: IdentityV2Store) -> None:
        close_current_main(result, _player(result, player_id), effective, "cleared")

    return _apply(store, change)


def set_member_activity(
    store: IdentityV2Store, member_id: str, status: str,
) -> IdentityV2Store:
    def change(result: IdentityV2Store) -> None:
        member = _member(result, member_id)
        if status not in {"active", "inactive"}:
            raise PlayerMembershipError("Aktivität muss active oder inactive sein.")
        if member.lifeStatus == "dead":
            raise PlayerMembershipError("Tote Member werden hier nicht reaktiviert.")
        member.lifeStatus = status

    return _apply(store, change)


def set_player_activity(
    store: IdentityV2Store, player_id: str, status: str,
) -> IdentityV2Store:
    """Change one Player and all living characters in one validated copy."""
    if status not in {"active", "inactive"}:
        raise PlayerMembershipError("Spieleraktivität muss active oder inactive sein.")
    store.validate()
    player = _player(store, player_id)
    if ((status == "inactive" and player.inactiveRestoreStates is not None)
            or (status == "active" and player.inactiveRestoreStates is None)):
        return store

    def change(result: IdentityV2Store) -> None:
        selected = _player(result, player_id)
        living = [member for member in result.members
                  if member.playerId == player_id and member.lifeStatus != "dead"]
        if status == "inactive":
            selected.inactiveRestoreStates = {
                member.memberId: member.lifeStatus for member in living}
            for member in living:
                member.lifeStatus = "inactive"
        else:
            previous = selected.inactiveRestoreStates
            if previous is None:
                raise PlayerMembershipError("Wiederherstellungszustand fehlt.")
            missing = [member.memberId for member in living
                       if member.memberId not in previous]
            if missing:
                raise PlayerMembershipError(
                    "Für neu zugeordnete Charaktere fehlt ein Vorzustand: "
                    + ", ".join(missing))
            for member in living:
                member.lifeStatus = previous[member.memberId]
            selected.inactiveRestoreStates = None

    return _apply(store, change)


def _batch_ids(member_ids: Iterable[str]) -> tuple[str, ...]:
    ids = tuple(member_ids)
    if not ids or len(ids) != len(set(ids)):
        raise PlayerMembershipError("Die Charakterauswahl ist leer oder enthält Duplikate.")
    return ids


def bulk_assign_members(
    store: IdentityV2Store, member_ids: Iterable[str], player_id: str,
) -> IdentityV2Store:
    ids = _batch_ids(member_ids)

    def change(result: IdentityV2Store) -> None:
        _player(result, player_id)
        for member_id in ids:
            member = _member(result, member_id)
            if member.playerId is not None:
                raise PlayerMembershipError(f"Member {member_id} ist bereits zugeordnet.")
            member.playerId = player_id
            _set_attendance_owner(result, member_id, player_id)

    return _apply(store, change)


def bulk_create_players_from_members(
    store: IdentityV2Store, member_ids: Iterable[str],
) -> IdentityV2Store:
    ids = _batch_ids(member_ids)
    result = store
    for member_id in ids:
        result = create_player_from_member(result, member_id)
    return result


def bulk_set_member_activity(
    store: IdentityV2Store, member_ids: Iterable[str], status: str,
) -> IdentityV2Store:
    ids = _batch_ids(member_ids)

    def change(result: IdentityV2Store) -> None:
        if status not in {"active", "inactive"}:
            raise PlayerMembershipError("Aktivität muss active oder inactive sein.")
        for member_id in ids:
            member = _member(result, member_id)
            if member.lifeStatus == "dead" or member.deathDate is not None:
                raise PlayerMembershipError("Friedhofscharaktere bleiben unverändert.")
            member.lifeStatus = status

    return _apply(store, change)
