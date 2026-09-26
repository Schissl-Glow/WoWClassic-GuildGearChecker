"""Datenmodelle der read-only ClassicLootManager-Integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class ClmIntegrationError(ValueError):
    """CLM-Daten sind ungültig, unvollständig oder nicht eindeutig."""


class ClmRosterSelectionRequired(ClmIntegrationError):
    """Mehrere gültige DKP-Roster benötigen eine explizite Benutzerauswahl."""

    def __init__(self, rosters: tuple["ClmRosterDescriptor", ...]) -> None:
        self.rosters = rosters
        super().__init__("Mehrere aktive DKP-Roster erfordern eine Auswahl.")


@dataclass(frozen=True)
class ClmDatabaseDescriptor:
    database_id: str
    guild_name: str
    realm: str
    active: bool = True


@dataclass(frozen=True)
class ClmRosterDescriptor:
    roster_id: str
    name: str
    database_id: str
    point_type: int
    active: bool
    is_test: bool = False


@dataclass(frozen=True)
class ClmCharacterBalance:
    name: str
    points: int | float
    clm_guid: str | None = None


@dataclass(frozen=True)
class ClmCharacterMatch:
    clm_name: str
    member_id: str
    character_name: str
    points: int | float


@dataclass(frozen=True)
class ClmMatchingResult:
    matches: tuple[ClmCharacterMatch, ...]
    unknown_names: tuple[str, ...]
    ambiguous_names: tuple[str, ...]


@dataclass(frozen=True)
class ClmSourceStatus:
    source_path: Path
    source_modified_at: float | None
    file_found: bool
    variable_found: bool
    database_id: str | None = None
    roster_id: str | None = None
    character_count: int = 0
    messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClmDkpCacheSnapshot:
    """Letzter vollständig und erfolgreich erzeugter read-only DKP-Stand."""

    source_path: Path
    source_modified_at: float | None
    refreshed_at: datetime
    database_id: str
    guild_name: str
    realm: str
    roster_id: str
    roster_name: str
    point_type: int
    balances: tuple[ClmCharacterBalance, ...]
    processed_entries: int


@dataclass(frozen=True)
class ClmDkpRefreshState:
    """Beobachtbarer Zustand der ausschließlich expliziten Aktualisierung."""

    cache: ClmDkpCacheSnapshot | None = None
    last_attempt_at: datetime | None = None
    last_error: str | None = None
