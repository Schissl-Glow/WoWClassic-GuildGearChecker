"""Main timeline operations and successor analysis for Identity V2."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date

from .identity_v2 import (
    IdentityV2Store, IdentityV2ValidationError, MainHistoryEntry, Player,
)


class MainHistoryError(IdentityV2ValidationError):
    """A requested Main timeline edit is invalid."""


@dataclass(frozen=True)
class MainSuccessorCandidate:
    memberId: str
    name: str
    className: str | None


class MainSuccessorSelectionRequired(MainHistoryError):
    """Death cannot commit until one of several valid successors is selected."""

    def __init__(self, player_id: str, dying_member_id: str,
                 candidates: tuple[MainSuccessorCandidate, ...]) -> None:
        self.playerId = player_id
        self.dyingMemberId = dying_member_id
        self.candidates = candidates
        self.candidateMemberIds = tuple(item.memberId for item in candidates)
        super().__init__("SUCCESSOR_SELECTION_REQUIRED")


@dataclass(frozen=True)
class MainPeriod:
    historyId: str
    memberId: str
    fromDate: str | None
    toDate: str | None


@dataclass(frozen=True)
class MainHistoryConflict:
    """A proven overlap; `current` denotes the non-persisted active period."""

    playerId: str
    historyIds: tuple[str, str]
    memberIds: tuple[str, str]
    periods: tuple[MainPeriod, MainPeriod]
    conflictType: str = "overlap"


_UNSET = object()


def _player(store: IdentityV2Store, player_id: str) -> Player:
    player = next((item for item in store.players if item.playerId == player_id), None)
    if player is None:
        raise MainHistoryError(f"Unknown Player: {player_id!r}.")
    return player


def _day(value: str | date | None, field_name: str) -> str | None:
    if value is None:
        return None
    if type(value) is date:
        return value.isoformat()
    if (not isinstance(value, str) or len(value) != 10
            or value[4] != "-" or value[7] != "-"):
        raise MainHistoryError(f"{field_name} requires YYYY-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise MainHistoryError(f"Invalid {field_name}: {value!r}.") from exc
    if parsed.isoformat() != value:
        raise MainHistoryError(f"{field_name} requires YYYY-MM-DD.")
    return value


def _apply(store: IdentityV2Store, change) -> IdentityV2Store:
    store.validate()
    result = copy.deepcopy(store)
    change(result)
    result.validate()
    return result


def close_current_main(store: IdentityV2Store, player: Player,
                       to_date: str | None, reason: str) -> MainHistoryEntry | None:
    """Close an observed Main period on an already copied working store."""
    if player.mainMemberId is None:
        return None
    entry = store._append_main_history(
        player, player.mainMemberId, player.mainSinceDate, to_date,
        "automatic", reason,
    )
    player.mainMemberId = None
    player.mainSinceDate = None
    return entry


def get_main_successor_candidates(
    store: IdentityV2Store, player_id: str, excluding_member_id: str,
) -> tuple[MainSuccessorCandidate, ...]:
    store.validate()
    _player(store, player_id)
    candidates = (
        MainSuccessorCandidate(item.memberId, item.name, item.className)
        for item in store.members
        if (item.playerId == player_id and item.memberId != excluding_member_id
            and item.lifeStatus == "active" and item.deathDate is None)
    )
    return tuple(sorted(candidates,
                        key=lambda item: (item.name.casefold(), item.memberId)))


def add_main_history_entry(
    store: IdentityV2Store, player_id: str, member_id: str,
    from_date: str | date | None = None, to_date: str | date | None = None,
) -> IdentityV2Store:
    start = _day(from_date, "fromDate")
    end = _day(to_date, "toDate")

    def change(result: IdentityV2Store) -> None:
        player = _player(result, player_id)
        member = next((item for item in result.members if item.memberId == member_id), None)
        if member is None or member.playerId != player_id:
            raise MainHistoryError("Historical Main must belong to this Player.")
        result._append_main_history(player, member_id, start, end, "manual", None)

    return _apply(store, change)


def set_main_since_date(
    store: IdentityV2Store, player_id: str,
    since_date: str | date | None,
) -> IdentityV2Store:
    """Correct only the known start of the current Main period."""
    value = _day(since_date, "mainSinceDate")

    def change(result: IdentityV2Store) -> None:
        player = _player(result, player_id)
        if player.mainMemberId is None and value is not None:
            raise MainHistoryError("mainSinceDate requires a current Main.")
        player.mainSinceDate = value

    return _apply(store, change)


def reconcile_draft_history_sequence(
    draft: IdentityV2Store, baseline: IdentityV2Store,
) -> IdentityV2Store:
    """Release IDs used only by entries added and removed within one draft."""
    draft.validate()
    baseline.validate()
    original_history = {player.playerId: player.mainHistory
                        for player in baseline.players}
    if (draft.nextMainHistoryNumber == baseline.nextMainHistoryNumber
            or {player.playerId for player in draft.players} != set(original_history)
            or any(player.mainHistory != original_history.get(player.playerId)
                   for player in draft.players)):
        return draft
    result = copy.deepcopy(draft)
    result.nextMainHistoryNumber = baseline.nextMainHistoryNumber
    result.validate()
    return result


def _entry(store: IdentityV2Store, history_id: str) -> tuple[Player, MainHistoryEntry]:
    for player in store.players:
        for item in player.mainHistory:
            if item.historyId == history_id:
                return player, item
    raise MainHistoryError(f"Unknown MainHistory ID: {history_id!r}.")


def update_main_history_entry(
    store: IdentityV2Store, history_id: str, *,
    member_id: str | object = _UNSET,
    from_date: str | date | None | object = _UNSET,
    to_date: str | date | None | object = _UNSET,
    reason: str | None | object = _UNSET,
) -> IdentityV2Store:
    start = _day(from_date, "fromDate") if from_date is not _UNSET else _UNSET
    end = _day(to_date, "toDate") if to_date is not _UNSET else _UNSET

    def change(result: IdentityV2Store) -> None:
        _owner, item = _entry(result, history_id)
        if member_id is not _UNSET:
            item.memberId = member_id
        if start is not _UNSET:
            item.fromDate = start
        if end is not _UNSET:
            item.toDate = end
        if reason is not _UNSET:
            item.reason = reason

    return _apply(store, change)


def remove_main_history_entry(
    store: IdentityV2Store, history_id: str,
) -> IdentityV2Store:
    def change(result: IdentityV2Store) -> None:
        player, item = _entry(result, history_id)
        result.nextMainHistoryNumber = max(
            result.nextMainHistoryNumber, int(item.historyId[2:]) + 1)
        player.mainHistory.remove(item)

    return _apply(store, change)


def find_main_history_conflicts(
    store: IdentityV2Store, player_id: str,
) -> tuple[MainHistoryConflict, ...]:
    """Report only provable positive-duration overlaps; never repair them."""
    store.validate()
    player = _player(store, player_id)
    periods = [MainPeriod(item.historyId, item.memberId,
                          item.fromDate, item.toDate)
               for item in player.mainHistory]
    if player.mainMemberId is not None and player.mainSinceDate is not None:
        periods.append(MainPeriod("current", player.mainMemberId,
                                  player.mainSinceDate, None))
    conflicts: list[MainHistoryConflict] = []
    today = date.today().isoformat()
    for index, left in enumerate(periods):
        for right in periods[index + 1:]:
            if left.fromDate is None or right.fromDate is None:
                continue
            if left.toDate is None and left.historyId != "current":
                continue
            if right.toDate is None and right.historyId != "current":
                continue
            left_end = today if left.historyId == "current" else left.toDate
            right_end = today if right.historyId == "current" else right.toDate
            if left.fromDate < right_end and right.fromDate < left_end:
                conflicts.append(MainHistoryConflict(
                    player_id, (left.historyId, right.historyId),
                    (left.memberId, right.memberId), (left, right),
                ))
    return tuple(conflicts)
