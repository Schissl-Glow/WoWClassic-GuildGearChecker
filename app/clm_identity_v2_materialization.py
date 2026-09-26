"""Build a new, in-memory Identity V2 store from reviewed CLM identities."""

from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Mapping

from .clm_identity_v2_analysis import ClmGuidHistory, ClmIdentityAnalysis
from .clm_identity_v2_decisions import (
    CONTINUE, NEW_CHARACTER, ClmIdentityDecisionDraft, ClmIdentityDecisionError,
    ClmIdentityDecisionSet, ClmNameDecision,
)
from .identity_v2 import (
    FIRST_MEMBER_NUMBER, EternalDkpRecord, IdentityV2Store,
    IdentityV2ValidationError, Member, member_id_from_number,
)
from .identity_v2_import_choices import CharacterImportChoice


class ClmMaterializationError(ValueError):
    """The CLM input cannot be materialized without a complete safe decision."""


def _name_key(value: str) -> str:
    return unicodedata.normalize("NFC", str(value).strip()).casefold()


def _empty_target(target: IdentityV2Store | None) -> None:
    if target is None:
        return
    if (target.members or target.players or target.raids or target.attendance
            or target.raidCreditResolutions or target.eternalDkpRecords
            or target.legacyClmGuidMemberMap or target.ignoredCsvCharacterNames
            or target.ignoredClmCharacterGroups):
        raise ClmMaterializationError("LUA-Erstinitialisierung erfordert einen leeren Identity-V2-Store.")
    target.validate()


def _reviewed_chains(
    analysis: ClmIdentityAnalysis, decisions: ClmIdentityDecisionSet | None,
) -> list[tuple[str, tuple[str, ...]]]:
    groups = {_name_key(group.normalized_name): group for group in analysis.multi_guid_groups}
    if len(groups) != len(analysis.multi_guid_groups):
        raise ClmMaterializationError("Analyse enthält doppelte Multi-GUID-Namensgruppen.")
    if decisions is None:
        if groups:
            names = ", ".join(group.normalized_name for group in analysis.multi_guid_groups)
            raise ClmMaterializationError(f"Multi-GUID-Entscheidungen fehlen: {names}.")
        decisions = ClmIdentityDecisionSet(analysis.database_id, analysis.roster_id, ())
    if decisions.database_id != analysis.database_id or decisions.roster_id != analysis.roster_id:
        raise ClmMaterializationError("DecisionSet gehört zu einer anderen CLM-Datenbank oder einem anderen Roster.")

    by_name: dict[str, ClmNameDecision] = {}
    for decision in decisions.decisions:
        key = _name_key(decision.normalized_name)
        if key in by_name:
            raise ClmMaterializationError(f"Doppelte Entscheidung für {decision.normalized_name}.")
        if key not in groups:
            raise ClmMaterializationError(f"Unbekannte Multi-GUID-Gruppe: {decision.normalized_name}.")
        by_name[key] = decision
    missing = groups.keys() - by_name.keys()
    if missing:
        names = ", ".join(groups[key].normalized_name for key in sorted(missing))
        raise ClmMaterializationError(f"Multi-GUID-Entscheidungen fehlen: {names}.")

    all_guids = {history.guid for history in analysis.guid_histories}
    draft = ClmIdentityDecisionDraft(analysis)
    chains: list[tuple[str, tuple[str, ...]]] = []
    for key, group in groups.items():
        decision = by_name[key]
        expected = group.chronological_order
        if decision.ordered_guids != expected:
            unknown = set(decision.ordered_guids) - all_guids
            if unknown:
                raise ClmMaterializationError(f"Unbekannte GUID im DecisionSet: {sorted(unknown)}.")
            raise ClmMaterializationError(f"GUID-Reihenfolge für {group.normalized_name} stimmt nicht mit der Analyse überein.")
        if not decision.character_groups or any(not chain for chain in decision.character_groups):
            raise ClmMaterializationError(f"Leere Charaktergruppe bei {group.normalized_name}.")
        flattened = tuple(guid for chain in decision.character_groups for guid in chain)
        unknown = set(flattened) - all_guids
        if unknown:
            raise ClmMaterializationError(f"Unbekannte GUID im DecisionSet: {sorted(unknown)}.")
        if len(set(flattened)) != len(flattened):
            raise ClmMaterializationError(f"Doppelte GUID in Charaktergruppen von {group.normalized_name}.")
        if flattened != expected:
            raise ClmMaterializationError(f"GUID-Abdeckung oder Reihenfolge bei {group.normalized_name} ist ungültig.")

        for chain in decision.character_groups:
            for evidence in analysis.raid_coexistence:
                if all(guid in chain for guid in evidence.guids):
                    raise ClmMaterializationError(
                        f"SAME_RAID_COEXISTENCE bei {group.normalized_name}: "
                        f"{evidence.guids[0]} und {evidence.guids[1]} in Raid {evidence.raid_id}."
                    )
            for guid in chain:
                if guid == expected[0]:
                    continue
                action = CONTINUE if guid != chain[0] else NEW_CHARACTER
                try:
                    draft.set_choice(group.normalized_name, guid, action)
                except ClmIdentityDecisionError as exc:
                    raise ClmMaterializationError(
                        f"Ungültige Fortsetzung bei {group.normalized_name} / {guid}: {exc}"
                    ) from exc
            chains.append((group.normalized_name, chain))
    try:
        draft.to_decision_set()
    except ClmIdentityDecisionError as exc:
        raise ClmMaterializationError(str(exc)) from exc
    return chains


def _member_class(histories: tuple[ClmGuidHistory, ...], name: str) -> str:
    classes = {history.character_class for history in histories}
    if len(classes) != 1 or any(not class_name for class_name in classes):
        raise ClmMaterializationError(f"Klasse fehlt oder widerspricht sich bei {name}.")
    for history in histories:
        if history.p0_count == 0:
            raise ClmMaterializationError(f"P0-Klasse fehlt bei GUID {history.guid}.")
        if any(warning.startswith(("P0_CLASS_CONFLICT:", "P0_NAME_CONFLICT:"))
               for warning in history.warnings):
            raise ClmMaterializationError(f"Widersprüchliche P0-Daten bei GUID {history.guid}.")
    return next(iter(classes))


def _raw_record(record, member_id: str) -> EternalDkpRecord:
    suffix = f":{record.character_guid}:{record.kind}"
    source_event_id = record.event_id.removesuffix(suffix)
    occurred_at = (
        datetime.fromtimestamp(record.timestamp, timezone.utc).isoformat()
        if record.timestamp > 0 else ""
    )
    return EternalDkpRecord(
        recordId=record.event_id,
        eventId=source_event_id,
        memberId=member_id,
        clmGuid=record.character_guid,
        eventType=record.kind,
        value=float(record.value),
        occurredAt=occurred_at,
        clmRaidId=record.clm_raid_id or None,
        description=record.description or None,
    )


def finalized_clm_character_groups(
    analysis: ClmIdentityAnalysis,
    decisions: ClmIdentityDecisionSet | None,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Expose final character groups only after all GUID continuation choices."""
    chains = _reviewed_chains(analysis, decisions)
    all_histories: dict[str, ClmGuidHistory] = {}
    by_name: dict[str, list[ClmGuidHistory]] = {}
    for history in analysis.guid_histories:
        if not history.guid or not history.guid.strip():
            raise ClmMaterializationError("Leere analysierte CLM-GUID.")
        if history.guid in all_histories:
            raise ClmMaterializationError(f"Doppelte analysierte GUID: {history.guid}.")
        all_histories[history.guid] = history
        if not history.normalized_name or not history.normalized_name.strip():
            if history.p0_count and history.incomplete_p0_count == history.p0_count:
                raise ClmMaterializationError(
                    f"Verwertbare P0-Identität (Name/Klasse) fehlt bei GUID {history.guid}.")
            raise ClmMaterializationError(f"Charaktername fehlt bei GUID {history.guid}.")
        by_name.setdefault(_name_key(history.normalized_name), []).append(history)

    multi_names = {_name_key(group.normalized_name)
                   for group in analysis.multi_guid_groups}
    if multi_names != {key for key, items in by_name.items() if len(items) > 1}:
        raise ClmMaterializationError(
            "Multi-GUID-Gruppen stimmen nicht mit den GUID-Historien überein.")
    chains.extend((items[0].normalized_name, (items[0].guid,))
                  for key, items in by_name.items() if key not in multi_names)
    used_guids = [guid for _name, chain in chains for guid in chain]
    if len(used_guids) != len(set(used_guids)) or set(used_guids) != set(all_histories):
        raise ClmMaterializationError(
            "Nicht jede analysierte GUID ist genau einer Charaktergruppe zugeordnet.")
    chains.sort(key=lambda item: (_name_key(item[0]),
                                  all_histories[item[1][0]].first_seen or -1,
                                  item[1][0]))
    return tuple(chains)


def build_identity_v2_store_from_clm(
    analysis: ClmIdentityAnalysis,
    decisions: ClmIdentityDecisionSet | None = None,
    *,
    target_store: IdentityV2Store | None = None,
    classifications: Mapping[tuple[str, ...], CharacterImportChoice] | None = None,
    require_classifications: bool = False,
) -> IdentityV2Store:
    """Materialize only a reviewed first import; never mutate the supplied store."""
    _empty_target(target_store)
    chains = finalized_clm_character_groups(analysis, decisions)
    all_histories = {history.guid: history for history in analysis.guid_histories}
    if classifications is None and require_classifications:
        raise ClmMaterializationError(
            "CLM-Character-Groups benötigen bestätigte Importklassifikationen.")
    reviewed = dict(classifications or {})
    if classifications is not None and set(reviewed) != {
        chain for _name, chain in chains
    }:
        raise ClmMaterializationError(
            "Importklassifikationen müssen jede endgültige CLM-Character-Group genau einmal abdecken.")

    new_store = IdentityV2Store()
    raw_by_id: dict[str, EternalDkpRecord] = {}
    for index, (name, chain) in enumerate(chains):
        choice = reviewed.get(chain, CharacterImportChoice())
        if choice.relevance not in {"relevant", "irrelevant"}:
            raise ClmMaterializationError(f"Ungültige Relevanz bei {name}.")
        if choice.activity_status not in {"active", "inactive"}:
            raise ClmMaterializationError(f"Ungültiger Aktivitätsstatus bei {name}.")
        if (choice.player_id is not None or choice.current_role is not None
                or choice.member_id is not None):
            raise ClmMaterializationError(
                "LUA-Neugildenimport besitzt noch keine bestehenden Player.")
        if choice.relevance == "irrelevant":
            new_store.ignore_clm_character_group(name, chain)
            continue
        histories = tuple(all_histories[guid] for guid in chain)
        class_name = _member_class(histories, name)
        if choice.class_name is not None and choice.class_name != class_name:
            raise ClmMaterializationError(
                f"CLM-P0-Klasse bei {name} darf nicht durch {choice.class_name} ersetzt werden.")
        member_id = member_id_from_number(FIRST_MEMBER_NUMBER + index)
        new_store.members.append(Member(
            memberId=member_id,
            name=name,
            className=class_name,
            clmGuid=chain[-1],
            playerId=None,
            currentRole=None,
            lifeStatus=choice.activity_status,
            continuationOfMemberId=None,
            raidStartDate=None,
        ))
        for guid in chain[:-1]:
            new_store.legacyClmGuidMemberMap[guid] = member_id
        for history in histories:
            for earning in history.eternal_dkp_records:
                if earning.character_guid != history.guid:
                    raise ClmMaterializationError(
                        f"DKP-Rohbuchung {earning.event_id} gehört zu einer anderen GUID.")
                raw_record = _raw_record(earning, member_id)
                previous = raw_by_id.get(raw_record.recordId)
                if previous is not None and previous != raw_record:
                    raise ClmMaterializationError(
                        f"Widersprüchliche DKP-Rohbuchung {raw_record.recordId}.")
                raw_by_id[raw_record.recordId] = raw_record
    new_store.eternalDkpRecords = list(raw_by_id.values())
    try:
        new_store.validate()
    except IdentityV2ValidationError as exc:
        raise ClmMaterializationError(f"V2-Invariante verletzt: {exc}") from exc
    return new_store
