"""Explicit, in-memory CLM character updates for an existing Identity V2 guild."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import replace

from .clm_identity_v2_analysis import (
    ClmIdentityAnalysis, _multi_guid_group,
)
from .clm_identity_v2_decisions import (
    CONTINUE, NEW_CHARACTER, ClmIdentityDecisionDraft, ClmIdentityDecisionSet,
)
from .clm_identity_v2_materialization import (
    _member_class, finalized_clm_character_groups,
)
from .clm_matching import character_key
from .clm_raid_v2_analysis import ClmRaidV2Analysis
from .identity_v2 import FIRST_MEMBER_NUMBER, IdentityV2Store, Member, member_id_from_number
from .identity_v2_import_choices import CharacterImportChoice


def prepare_clm_identity_refresh_review(
    store: IdentityV2Store, analysis: ClmIdentityAnalysis,
) -> tuple[ClmIdentityDecisionDraft, set[str], set[tuple[str, str]]]:
    """Reuse persisted GUID ownership and review only groups with new GUIDs."""
    store.validate()
    known: dict[str, tuple[str, str | int]] = {
        guid: ("member", member_id) for guid, member_id in _owners(store).items()
    }
    for index, group in enumerate(store.ignoredClmCharacterGroups):
        for guid in group.clmGuids:
            known[guid.casefold()] = ("ignored", index)
    draft = ClmIdentityDecisionDraft(analysis)
    review_groups: set[str] = set()
    locked: set[tuple[str, str]] = set()
    for group in analysis.multi_guid_groups:
        name_key = character_key(group.normalized_name)
        histories = group.guid_histories
        if any(history.guid.casefold() not in known for history in histories):
            review_groups.add(name_key)
        for older, newer in zip(histories, histories[1:]):
            old_owner = known.get(older.guid.casefold())
            new_owner = known.get(newer.guid.casefold())
            if old_owner is None or new_owner is None:
                continue
            action = CONTINUE if old_owner == new_owner else NEW_CHARACTER
            draft.set_choice(group.normalized_name, newer.guid, action)
            locked.add((name_key, newer.guid))
    return draft, review_groups, locked


def unresolved_raid_participant_guids(
    store: IdentityV2Store, analysis: ClmRaidV2Analysis,
) -> tuple[str, ...]:
    """Return only valid raid-participant GUIDs without an owner or Ignore record."""
    store.validate()
    resolved = set(_owners(store))
    resolved.update(guid.casefold() for group in store.ignoredClmCharacterGroups
                    for guid in group.clmGuids)
    return tuple(sorted({participant.guid for raid in analysis.raids
                         for participant in raid.participants
                         if participant.guid_status == "VALID_CHARACTER_GUID"
                         and participant.guid.casefold() not in resolved}))


def raid_participant_identity_analysis(
    analysis: ClmRaidV2Analysis, required_guids: tuple[str, ...],
) -> ClmIdentityAnalysis:
    """Scope existing V2 review dialogs to the still-open raid identities."""
    required = {guid.casefold() for guid in required_guids}
    identity = analysis.identity_analysis
    histories = tuple(history for history in identity.guid_histories
                      if history.guid.casefold() in required)
    absent = required - {history.guid.casefold() for history in histories}
    if absent:
        raise ValueError("Für Raidteilnehmer fehlt eine verwertbare CLM-P0-Identität: "
                         + ", ".join(sorted(absent)))
    grouped: dict[str, list] = {}
    for history in histories:
        grouped.setdefault(character_key(history.normalized_name), []).append(history)
    groups = tuple(_multi_guid_group(items) for items in grouped.values()
                   if len(items) > 1)
    coexistence = tuple(item for item in identity.raid_coexistence
                        if all(guid.casefold() in required for guid in item.guids))
    return replace(identity, guid_histories=histories,
                   multi_guid_groups=groups, raid_coexistence=coexistence,
                   ignored_technical_guids=())


def pending_clm_character_groups(
    store: IdentityV2Store, analysis: ClmIdentityAnalysis,
    decisions: ClmIdentityDecisionSet,
) -> set[tuple[str, ...]]:
    """Only groups not completely assigned or ignored need a user decision."""
    owners = _owners(store)
    ignored = {guid.casefold() for group in store.ignoredClmCharacterGroups
               for guid in group.clmGuids}
    members = {member.memberId: member for member in store.members}
    histories = {history.guid: history for history in analysis.guid_histories}
    pending = set()
    for _name, chain in finalized_clm_character_groups(analysis, decisions):
        assigned = {owners[guid.casefold()] for guid in chain
                    if guid.casefold() in owners}
        if len(assigned) > 1 or (assigned and any(g.casefold() in ignored for g in chain)):
            raise ValueError("CLM-GUID-Gruppe widerspricht bestehenden Member-/Ignore-Zuordnungen.")
        if (len(assigned) == 1 and all(g.casefold() in owners for g in chain)):
            member = members[next(iter(assigned))]
            source_class = _member_class(tuple(histories[g] for g in chain), _name)
            if (character_key(member.name) != character_key(_name)
                    or (member.className and member.className != source_class)):
                raise ValueError(
                    f"Gespeicherte CLM-GUID bei {_name} widerspricht Name oder Klasse.")
            continue
        if all(g.casefold() in ignored for g in chain):
            continue
        pending.add(chain)
    return pending


def _owners(store: IdentityV2Store) -> dict[str, str]:
    owners = {member.clmGuid.casefold(): member.memberId
              for member in store.members if member.clmGuid}
    owners.update((guid.casefold(), member_id)
                  for guid, member_id in store.legacyClmGuidMemberMap.items())
    return owners


def refresh_clm_v2_characters(
    store: IdentityV2Store, analysis: ClmIdentityAnalysis,
    decisions: ClmIdentityDecisionSet,
    classifications: Mapping[tuple[str, ...], CharacterImportChoice],
) -> IdentityV2Store:
    """Return a validated copy; preserve existing IDs, status and player history."""
    store.validate()
    pending = pending_clm_character_groups(store, analysis, decisions)
    if set(classifications) != pending:
        raise ValueError("Jede offene CLM-Charaktergruppe benötigt genau eine Entscheidung.")
    result = copy.deepcopy(store)
    owners = _owners(result)
    ignored = {guid.casefold() for group in result.ignoredClmCharacterGroups
               for guid in group.clmGuids}
    histories = {history.guid: history for history in analysis.guid_histories}
    next_number = max(
        FIRST_MEMBER_NUMBER,
        max((int(match.group(1)) for member in result.members
             if (match := re.fullmatch(r"m(\d+)", member.memberId))),
            default=FIRST_MEMBER_NUMBER - 1) + 1,
    )
    member_by_id = {member.memberId: member for member in result.members}
    assigned_existing_members: set[str] = set()
    for name, chain in finalized_clm_character_groups(analysis, decisions):
        if chain not in pending:
            continue
        choice = classifications[chain]
        mapped = {owners[guid.casefold()] for guid in chain
                  if guid.casefold() in owners}
        if len(mapped) > 1:
            raise ValueError(f"Widersprüchliche GUID-Eigentümer bei {name}.")
        if any(guid.casefold() in ignored for guid in chain) and choice.relevance != "irrelevant":
            raise ValueError(f"Ignorierte GUID bei {name} darf nicht still importiert werden.")
        if choice.relevance == "irrelevant":
            if mapped or choice.member_id:
                raise ValueError(f"Bereits zugeordneter Charakter {name} darf nicht ignoriert werden.")
            result.ignoredClmCharacterGroups = [
                group for group in result.ignoredClmCharacterGroups
                if not any(g.casefold() in {item.casefold() for item in chain}
                           for g in group.clmGuids)
            ]
            result.ignore_clm_character_group(name, chain)
            ignored.update(g.casefold() for g in chain)
            continue
        if choice.relevance != "relevant":
            raise ValueError(f"Ungültige CLM-Klassifizierung bei {name}.")
        class_name = _member_class(tuple(histories[guid] for guid in chain), name)
        if choice.current_role is not None or (choice.class_name is not None
                                               and choice.class_name != class_name):
            raise ValueError(f"CLM darf Main-Rolle oder P0-Klasse bei {name} nicht erraten.")
        if choice.member_id:
            member = member_by_id.get(choice.member_id)
            if (member is None or member.lifeStatus == "dead"
                    or character_key(member.name) != character_key(name)
                    or (member.className and member.className != class_name)
                    or (mapped and mapped != {member.memberId})
                    or (choice.player_id is not None
                        and choice.player_id != member.playerId)):
                raise ValueError(f"Bestehender Member für {name} passt nicht zur CLM-Identität.")
            if member.memberId in assigned_existing_members:
                raise ValueError(
                    f"Member {member.memberId} wurde mehreren getrennten CLM-Gruppen zugeordnet.")
            assigned_existing_members.add(member.memberId)
            if member.clmGuid and member.clmGuid.casefold() != chain[-1].casefold():
                result.legacyClmGuidMemberMap[member.clmGuid] = member.memberId
            for old_guid in list(result.legacyClmGuidMemberMap):
                if old_guid.casefold() == chain[-1].casefold():
                    del result.legacyClmGuidMemberMap[old_guid]
            member.clmGuid = chain[-1]
            if not member.className:
                member.className = class_name
        else:
            if mapped or any(g.casefold() in ignored for g in chain):
                raise ValueError(f"CLM-GUID von {name} ist bereits zugeordnet oder ignoriert.")
            if choice.activity_status not in {"active", "inactive"}:
                raise ValueError(f"Ungültiger Lebensstatus bei {name}.")
            if choice.player_id is not None and choice.player_id not in {
                    player.playerId for player in result.players}:
                raise ValueError(f"Unbekannter Spieler bei {name}.")
            while member_id_from_number(next_number) in member_by_id:
                next_number += 1
            member = Member(memberId=member_id_from_number(next_number),
                            name=name, className=class_name,
                            lifeStatus=choice.activity_status, clmGuid=chain[-1],
                            playerId=choice.player_id)
            next_number += 1
            result.members.append(member)
            member_by_id[member.memberId] = member
        owners[chain[-1].casefold()] = member.memberId
        for guid in chain[:-1]:
            if guid.casefold() != member.clmGuid.casefold():
                result.legacyClmGuidMemberMap[guid] = member.memberId
            owners[guid.casefold()] = member.memberId
    result.validate()
    return result
