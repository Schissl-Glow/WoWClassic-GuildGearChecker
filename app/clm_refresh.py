"""Explizite, transaktionale Aktualisierung des read-only CLM-DKP-Caches.

Dieses Modul enthält absichtlich weder Polling noch Timer oder UI-Hooks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Callable, Mapping

try:
    from .clm_models import (
        ClmDkpCacheSnapshot, ClmDkpRefreshState, ClmIntegrationError,
        ClmRosterSelectionRequired,
    )
    from .clm_detection import (
        describe_databases, describe_rosters, select_database, select_dkp_roster,
        validate_guild_realm,
    )
    from .clm_replay import ClmLedgerReplayer, LedgerReplayRequest
    from .clm_savedvariables import load_saved_variables
except ImportError:
    from clm_models import (  # type: ignore
        ClmDkpCacheSnapshot, ClmDkpRefreshState, ClmIntegrationError,
        ClmRosterSelectionRequired,
    )
    from clm_detection import (  # type: ignore
        describe_databases, describe_rosters, select_database, select_dkp_roster,
        validate_guild_realm,
    )
    from clm_replay import ClmLedgerReplayer, LedgerReplayRequest  # type: ignore
    from clm_savedvariables import load_saved_variables  # type: ignore


class ClmDkpRefreshService:
    """Liest und replayt CLM-Daten nur durch einen expliziten ``refresh``-Aufruf."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._state = ClmDkpRefreshState()
        self._lock = RLock()

    @property
    def state(self) -> ClmDkpRefreshState:
        with self._lock:
            return self._state

    @property
    def cached_snapshot(self) -> ClmDkpCacheSnapshot | None:
        return self.state.cache

    def refresh(
        self,
        source_path: Path | str,
        *,
        database_id: str,
        roster_id: str,
    ) -> ClmDkpCacheSnapshot:
        """Erzeugt atomar einen neuen Cache oder behält den letzten gültigen bei."""

        attempted_at = self._clock()
        with self._lock:
            previous_cache = self._state.cache
            try:
                document = load_saved_variables(source_path)
                database = document.data.get(database_id)
                if not isinstance(database, Mapping):
                    raise ClmIntegrationError(
                        f"CLM-Datenbank {database_id!r} wurde nicht gefunden."
                    )
                ledger = database.get("ledger")
                if not isinstance(ledger, Mapping):
                    raise ClmIntegrationError(
                        f"CLM-Datenbank {database_id!r} enthält kein Ledger."
                    )
                result = ClmLedgerReplayer().replay(LedgerReplayRequest(
                    database_id=database_id,
                    roster_id=roster_id,
                    ledger=ledger,
                ))
                descriptor = next((
                    item for item in describe_databases(document.data)
                    if item.database_id == database_id
                ), None)
                snapshot = ClmDkpCacheSnapshot(
                    source_path=document.source_path or Path(source_path),
                    source_modified_at=document.modified_at,
                    refreshed_at=attempted_at,
                    database_id=database_id,
                    guild_name=descriptor.guild_name if descriptor else "",
                    realm=descriptor.realm if descriptor else "",
                    roster_id=result.roster_id,
                    roster_name=result.roster_name,
                    point_type=result.point_type,
                    balances=result.balances,
                    processed_entries=result.processed_entries,
                )
            except Exception as error:
                self._state = ClmDkpRefreshState(
                    cache=previous_cache,
                    last_attempt_at=attempted_at,
                    last_error=str(error),
                )
                raise
            self._state = ClmDkpRefreshState(
                cache=snapshot,
                last_attempt_at=attempted_at,
                last_error=None,
            )
            return snapshot

    def refresh_from_document(
        self, document, *, database_id: str, roster_id: str,
    ) -> ClmDkpCacheSnapshot:
        """Replay an already parsed Lua document for a confirmed combined V2 action."""
        attempted_at = self._clock()
        with self._lock:
            previous_cache = self._state.cache
            try:
                database = document.data.get(database_id)
                if not isinstance(database, Mapping):
                    raise ClmIntegrationError(f"CLM-Datenbank {database_id!r} wurde nicht gefunden.")
                ledger = database.get("ledger")
                if not isinstance(ledger, Mapping):
                    raise ClmIntegrationError(f"CLM-Datenbank {database_id!r} enthält kein Ledger.")
                result = ClmLedgerReplayer().replay(LedgerReplayRequest(
                    database_id=database_id, roster_id=roster_id, ledger=ledger))
                descriptor = next((item for item in describe_databases(document.data)
                                   if item.database_id == database_id), None)
                snapshot = ClmDkpCacheSnapshot(
                    source_path=document.source_path,
                    source_modified_at=document.modified_at,
                    refreshed_at=attempted_at,
                    database_id=database_id,
                    guild_name=descriptor.guild_name if descriptor else "",
                    realm=descriptor.realm if descriptor else "",
                    roster_id=result.roster_id,
                    roster_name=result.roster_name,
                    point_type=result.point_type,
                    balances=result.balances,
                    processed_entries=result.processed_entries,
                )
            except Exception as error:
                self._state = ClmDkpRefreshState(
                    cache=previous_cache, last_attempt_at=attempted_at,
                    last_error=str(error))
                raise
            self._state = ClmDkpRefreshState(
                cache=snapshot, last_attempt_at=attempted_at, last_error=None)
            return snapshot

    def refresh_for_project(
        self,
        source_path: Path | str,
        *,
        project_guild_name: str,
        project_realm: str,
        requested_database_id: str | None = None,
        requested_roster_id: str | None = None,
        requested_roster_name: str | None = None,
    ) -> ClmDkpCacheSnapshot:
        """Validiert Projektidentität und Roster bei einem expliziten Refresh."""
        attempted_at = self._clock()
        with self._lock:
            previous_cache = self._state.cache
            try:
                document = load_saved_variables(source_path)
                databases = describe_databases(document.data)
                if requested_database_id:
                    database = next((item for item in databases
                                     if item.database_id == requested_database_id), None)
                    if database is None:
                        raise ClmIntegrationError("Die gespeicherte CLM-Datenbank fehlt.")
                    validate_guild_realm(project_guild_name, project_realm, database)
                else:
                    database = select_database(
                        databases, project_guild_name, project_realm,
                    )
                raw_database = document.data.get(database.database_id)
                if not isinstance(raw_database, Mapping):
                    raise ClmIntegrationError(
                        f"CLM-Datenbank {database.database_id!r} wurde nicht gefunden."
                    )
                rosters = describe_rosters(database.database_id, raw_database)
                eligible = tuple(
                    roster for roster in rosters
                    if roster.active and roster.point_type == 0 and not roster.is_test
                )
                if requested_roster_name and not requested_roster_id and eligible:
                    matches = [roster for roster in eligible
                               if roster.name.casefold() == requested_roster_name.casefold()]
                    if len(matches) != 1:
                        raise ClmRosterSelectionRequired(eligible)
                    requested_roster_id = matches[0].roster_id
                if not requested_roster_id and len(eligible) > 1:
                    raise ClmRosterSelectionRequired(eligible)
                if requested_roster_id and eligible and not any(
                        item.roster_id == requested_roster_id for item in eligible):
                    raise ClmRosterSelectionRequired(eligible)
                roster = select_dkp_roster(
                    rosters,
                    database_id=database.database_id,
                    requested_roster_id=requested_roster_id,
                )
                ledger = raw_database.get("ledger")
                if not isinstance(ledger, Mapping):
                    raise ClmIntegrationError(
                        f"CLM-Datenbank {database.database_id!r} enthält kein Ledger."
                    )
                result = ClmLedgerReplayer().replay(LedgerReplayRequest(
                    database_id=database.database_id,
                    roster_id=roster.roster_id,
                    ledger=ledger,
                ))
                snapshot = ClmDkpCacheSnapshot(
                    source_path=document.source_path or Path(source_path),
                    source_modified_at=document.modified_at,
                    refreshed_at=attempted_at,
                    database_id=database.database_id,
                    guild_name=database.guild_name,
                    realm=database.realm,
                    roster_id=result.roster_id,
                    roster_name=result.roster_name,
                    point_type=result.point_type,
                    balances=result.balances,
                    processed_entries=result.processed_entries,
                )
            except Exception as error:
                self._state = ClmDkpRefreshState(
                    cache=previous_cache,
                    last_attempt_at=attempted_at,
                    last_error=str(error),
                )
                raise
            self._state = ClmDkpRefreshState(
                cache=snapshot,
                last_attempt_at=attempted_at,
                last_error=None,
            )
            return snapshot
