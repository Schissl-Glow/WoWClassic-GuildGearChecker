"""Pure orchestration for creating a new Identity V2 guild from CLM."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Mapping

from .clm_detection import describe_databases, describe_rosters, select_dkp_roster
from .clm_identity_v2_decisions import ClmIdentityDecisionSet
from .clm_identity_v2_materialization import build_identity_v2_store_from_clm
from .clm_models import ClmDatabaseDescriptor, ClmIntegrationError, ClmRosterDescriptor
from .clm_raid_v2_analysis import ClmRaidV2Analysis, analyze_clm_raid_ledger
from .clm_raid_v2_materialization import materialize_clm_raids_into_identity_v2
from .clm_savedvariables import SavedVariablesDocument, load_saved_variables
from .identity_v2 import IdentityV2Store
from .identity_v2_import_choices import CharacterImportChoice


@dataclass(frozen=True)
class ClmV2SourceInspection:
    document: SavedVariablesDocument
    databases: tuple[ClmDatabaseDescriptor, ...]

    def database(self, database_id: str) -> ClmDatabaseDescriptor:
        matches = [item for item in self.databases
                   if item.database_id == database_id and item.active]
        if len(matches) != 1:
            raise ClmIntegrationError(f"CLM-Datenbank {database_id!r} ist nicht gültig oder nicht aktiv.")
        return matches[0]

    def eligible_rosters(self, database_id: str) -> tuple[ClmRosterDescriptor, ...]:
        self.database(database_id)
        raw_database = self.document.data.get(database_id)
        if not isinstance(raw_database, Mapping):
            raise ClmIntegrationError("Die gewählte CLM-Datenbank fehlt.")
        return tuple(item for item in describe_rosters(database_id, raw_database)
                     if item.active and item.point_type == 0 and not item.is_test)


def inspect_clm_v2_source(path: Path | str) -> ClmV2SourceInspection:
    document = load_saved_variables(path)
    databases = tuple(item for item in describe_databases(document.data) if item.active)
    if not databases:
        raise ClmIntegrationError("Die Lua enthält keine aktive CLM-Datenbank.")
    return ClmV2SourceInspection(document, databases)


def analyze_clm_v2_selection(
    inspection: ClmV2SourceInspection, database_id: str,
    roster_id: str | None = None,
) -> ClmRaidV2Analysis:
    inspection.database(database_id)
    raw_database = inspection.document.data.get(database_id)
    if not isinstance(raw_database, Mapping) or not isinstance(raw_database.get("ledger"), Mapping):
        raise ClmIntegrationError("Die gewählte CLM-Datenbank hat kein gültiges Ledger.")
    roster = select_dkp_roster(
        describe_rosters(database_id, raw_database),
        database_id=database_id, requested_roster_id=roster_id,
    )
    analysis = analyze_clm_raid_ledger(raw_database["ledger"], roster.roster_id)
    return replace(
        analysis, database_id=database_id, roster_id=roster.roster_id,
        identity_analysis=replace(analysis.identity_analysis,
                                  database_id=database_id, roster_id=roster.roster_id),
    )


def build_new_clm_v2_guild(
    analysis: ClmRaidV2Analysis,
    decisions: ClmIdentityDecisionSet | None,
    *, target_store: IdentityV2Store | None = None,
    phase_callback: Callable[[str], None] | None = None,
    classifications: Mapping[tuple[str, ...], CharacterImportChoice] | None = None,
    require_classifications: bool = False,
    raid_types: Mapping[str, str] | None = None,
) -> IdentityV2Store:
    """Build a complete in-memory V2 guild; never change a supplied target."""
    if phase_callback:
        phase_callback("members")
    identity = build_clm_v2_characters(
        analysis, decisions, target_store=target_store,
        classifications=classifications,
        require_classifications=require_classifications,
    )
    if phase_callback:
        phase_callback("raids")
    completed = materialize_clm_raids_into_identity_v2(identity, analysis, raid_types)
    completed.validate()
    return completed


def build_clm_v2_characters(
    analysis: ClmRaidV2Analysis,
    decisions: ClmIdentityDecisionSet | None,
    *, target_store: IdentityV2Store | None = None,
    classifications: Mapping[tuple[str, ...], CharacterImportChoice] | None = None,
    require_classifications: bool = False,
) -> IdentityV2Store:
    """Complete the character transaction independently of raid review."""
    return build_identity_v2_store_from_clm(
        analysis.identity_analysis, decisions,
        target_store=target_store if target_store is not None else IdentityV2Store(),
        classifications=classifications,
        require_classifications=require_classifications,
    )


def verify_existing_clm_characters(store: IdentityV2Store, analysis: ClmRaidV2Analysis) -> None:
    """Permit a later raid pass only for GUIDs already assigned or explicitly ignored."""
    store.validate()
    owners = {member.clmGuid.casefold() for member in store.members if member.clmGuid}
    owners.update(guid.casefold() for guid in store.legacyClmGuidMemberMap)
    owners.update(guid.casefold() for group in store.ignoredClmCharacterGroups
                  for guid in group.clmGuids)
    missing = {history.guid for history in analysis.identity_analysis.guid_histories
               if history.guid.casefold() not in owners}
    if missing:
        raise ClmIntegrationError(
            "Die LUA enthält noch nicht zugeordnete Charakter-GUIDs: "
            + ", ".join(sorted(missing)))


@dataclass(frozen=True)
class ClmV2InitializationSummary:
    database_id: str
    roster_id: str
    members: int
    primary_guids: int
    legacy_guid_mappings: int
    multi_guid_decisions: int
    raids: int
    attendance: int
    main: int
    twink: int
    unknown: int
    members_with_raid_start: int
    members_without_raid_start: int
    incomplete_p0_ignored: int
    technical_guids_ignored: int
    ignored_character_groups: int = 0


def summarize_clm_v2_initialization(
    store: IdentityV2Store, analysis: ClmRaidV2Analysis,
    decisions: ClmIdentityDecisionSet | None,
) -> ClmV2InitializationSummary:
    store.validate()
    roles = Counter(item.attendanceType for item in store.attendance)
    with_start = sum(member.raidStartDate is not None for member in store.members)
    return ClmV2InitializationSummary(
        database_id=analysis.database_id,
        roster_id=analysis.roster_id,
        members=len(store.members),
        primary_guids=sum(member.clmGuid is not None for member in store.members),
        legacy_guid_mappings=len(store.legacyClmGuidMemberMap),
        multi_guid_decisions=len(decisions.decisions) if decisions else 0,
        raids=len(store.raids), attendance=len(store.attendance),
        main=roles["main"], twink=roles["twink"], unknown=roles["unknown"],
        members_with_raid_start=with_start,
        members_without_raid_start=len(store.members) - with_start,
        incomplete_p0_ignored=analysis.identity_analysis.summary["incompleteP0Ignored"],
        technical_guids_ignored=analysis.identity_analysis.summary["technicalGuidsIgnored"],
        ignored_character_groups=len(store.ignoredClmCharacterGroups),
    )
