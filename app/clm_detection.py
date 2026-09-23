"""Exakte CLM-Datenbank-, Gilden- und Roster-Auswahl ohne Fuzzy Matching."""

from __future__ import annotations

import unicodedata
from typing import Iterable, Mapping

try:
    from .clm_models import ClmDatabaseDescriptor, ClmIntegrationError, ClmRosterDescriptor
except ImportError:
    from clm_models import (  # type: ignore
        ClmDatabaseDescriptor, ClmIntegrationError, ClmRosterDescriptor,
    )


def _sequence(value: object) -> list[object]:
    if isinstance(value, Mapping):
        return [value[key] for key in sorted(key for key in value if isinstance(key, int))]
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _database_identity(database_id: object, data: Mapping[object, object]) -> tuple[str, str]:
    guild_name = str(data.get("guildName") or data.get("guild") or "").strip()
    realm = str(data.get("realm") or data.get("server") or "").strip()
    if guild_name and realm:
        return guild_name, realm
    parts = str(database_id or "").strip().split()
    if len(parts) >= 4:
        return guild_name or " ".join(parts[3:]), realm or parts[2]
    return guild_name, realm


def describe_databases(data: Mapping[object, object]) -> tuple[ClmDatabaseDescriptor, ...]:
    """Liest die stabilen CLM-Datenbankidentitäten ohne ein Ledger-Replay."""
    result: list[ClmDatabaseDescriptor] = []
    for raw_id, raw_database in data.items():
        if not isinstance(raw_database, Mapping) or not isinstance(raw_database.get("ledger"), Mapping):
            continue
        database_id = str(raw_id)
        guild_name, realm = _database_identity(raw_id, raw_database)
        result.append(ClmDatabaseDescriptor(
            database_id=database_id,
            guild_name=guild_name,
            realm=realm,
            active=bool(raw_database.get("active", True)),
        ))
    return tuple(sorted(result, key=lambda item: item.database_id.casefold()))


def describe_rosters(
    database_id: str, database: Mapping[object, object],
) -> tuple[ClmRosterDescriptor, ...]:
    """Rekonstruiert nur die aktuelle Roster-Liste aus den Roster-Events."""
    ledger = database.get("ledger")
    if not isinstance(ledger, Mapping):
        raise ClmIntegrationError(f"CLM-Datenbank {database_id!r} enthält kein Ledger.")
    entries = [entry for entry in _sequence(ledger) if isinstance(entry, Mapping)]
    entries.sort(key=lambda entry: tuple(entry.get(key, 0) for key in ("_c", "_b", "_e", "_a")))
    ignored: set[str] = set()
    rosters: dict[str, ClmRosterDescriptor] = {}
    for entry in entries:
        uid = "-".join(str(entry.get(key, 0)) for key in ("_c", "_b", "_e", "_a"))
        if uid in ignored:
            ignored.remove(uid)
            continue
        opcode = str(entry.get("_d") or "")
        if opcode == "IGN":
            ignored.add(str(entry.get("ref") or ""))
            continue
        roster_id = str(entry.get("r") or "").strip()
        if opcode == "R0" and roster_id:
            rosters[roster_id] = ClmRosterDescriptor(
                roster_id=roster_id,
                name=str(entry.get("n") or "").strip(),
                database_id=database_id,
                point_type=int(entry.get("p") or 0),
                active=True,
                is_test=bool(entry.get("isTest", entry.get("test", False))),
            )
        elif opcode == "R1" and roster_id:
            rosters.pop(roster_id, None)
        elif opcode == "R2" and roster_id in rosters:
            previous = rosters[roster_id]
            rosters[roster_id] = ClmRosterDescriptor(
                roster_id=previous.roster_id,
                name=str(entry.get("n") or previous.name).strip(),
                database_id=previous.database_id,
                point_type=previous.point_type,
                active=previous.active,
                is_test=previous.is_test,
            )
    return tuple(sorted(rosters.values(), key=lambda item: (item.name.casefold(), item.roster_id)))


def identity_key(value: object) -> str:
    return unicodedata.normalize("NFC", str(value or "").strip()).casefold()


def validate_guild_realm(
    project_guild_name: str,
    project_realm: str,
    database: ClmDatabaseDescriptor,
) -> ClmDatabaseDescriptor:
    if not identity_key(project_guild_name) or not identity_key(project_realm):
        raise ClmIntegrationError("Gildenname und Realm müssen im Projekt gepflegt sein.")
    if identity_key(project_guild_name) != identity_key(database.guild_name):
        raise ClmIntegrationError("Die CLM-Datenbank gehört zu einer anderen Gilde.")
    if identity_key(project_realm) != identity_key(database.realm):
        raise ClmIntegrationError("Die CLM-Datenbank gehört zu einem anderen Realm.")
    if not database.active:
        raise ClmIntegrationError("Die ausgewählte CLM-Datenbank ist nicht aktiv.")
    return database


def select_database(
    databases: Iterable[ClmDatabaseDescriptor],
    project_guild_name: str,
    project_realm: str,
) -> ClmDatabaseDescriptor:
    matches = [
        database for database in databases
        if database.active
        and identity_key(database.guild_name) == identity_key(project_guild_name)
        and identity_key(database.realm) == identity_key(project_realm)
    ]
    if not matches:
        raise ClmIntegrationError("Keine passende aktive CLM-Datenbank gefunden.")
    if len(matches) > 1:
        raise ClmIntegrationError("Mehrere passende aktive CLM-Datenbanken gefunden.")
    return matches[0]


def select_dkp_roster(
    rosters: Iterable[ClmRosterDescriptor],
    *,
    database_id: str,
    requested_roster_id: str | None = None,
) -> ClmRosterDescriptor:
    eligible = [
        roster for roster in rosters
        if roster.database_id == database_id
        and roster.active
        and roster.point_type == 0
        and not roster.is_test
    ]
    if requested_roster_id:
        matches = [roster for roster in eligible if roster.roster_id == requested_roster_id]
        if len(matches) != 1:
            raise ClmIntegrationError("Die gespeicherte CLM-Roster-ID ist nicht mehr gültig.")
        return matches[0]
    if not eligible:
        raise ClmIntegrationError("Kein aktiver DKP-Roster gefunden.")
    if len(eligible) > 1:
        raise ClmIntegrationError("Mehrere aktive DKP-Roster erfordern eine Auswahl.")
    return eligible[0]
