"""Read-only, indexed table rows for the later V2 character-data page."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from .identity_v2 import IdentityV2Store


@dataclass(frozen=True)
class CharacterTableRow:
    memberId: str
    name: str
    playerName: str | None
    playerRole: str | None
    lifeStatus: str
    race: str | None
    className: str | None
    spec: str | None
    raidRole: str
    gearStatus: str
    raidStatus: str
    note: str
    lastChecked: str | None
    raidCount: int
    lastRaidDate: str | None
    isDead: bool
    deathDate: str | None


def character_table_rows(store: IdentityV2Store) -> tuple[CharacterTableRow, ...]:
    """Index Players and actual Attendance once per view refresh."""
    players = {player.playerId: player for player in store.players}
    raid_dates: dict[str, str] = {}
    for raid in store.raids:
        try:
            raid_dates[raid.raidId] = date.fromisoformat(raid.date).isoformat()
        except (TypeError, ValueError):
            continue
    counts = Counter(entry.memberId for entry in store.attendance)
    last_dates: dict[str, str] = {}
    for entry in store.attendance:
        raid_day = raid_dates.get(entry.raidId)
        if raid_day is not None and raid_day > last_dates.get(entry.memberId, ""):
            last_dates[entry.memberId] = raid_day
    rows = []
    for member in store.members:
        player = players.get(member.playerId)
        role = None
        if player is not None:
            role = "main" if player.mainMemberId == member.memberId else "twink"
        rows.append(CharacterTableRow(
            memberId=member.memberId, name=member.name,
            playerName=player.displayName if player is not None else None,
            playerRole=role, lifeStatus=member.lifeStatus,
            race=member.race, className=member.className, spec=member.spec,
            raidRole=member.raidRole, gearStatus=member.gearStatus,
            raidStatus=member.raidStatus, note=member.note,
            lastChecked=member.lastChecked, raidCount=counts[member.memberId],
            lastRaidDate=last_dates.get(member.memberId),
            isDead=member.lifeStatus == "dead", deathDate=member.deathDate,
        ))
    return tuple(rows)
