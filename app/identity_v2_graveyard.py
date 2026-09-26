"""Read-only cemetery projection and atomic V2 gravestone edits by memberId."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from math import isfinite
from typing import Iterable, Mapping

from .identity_v2 import IdentityV2Store, IdentityV2ValidationError, Member
from .gravestone_categories import normalize_gravestone_category
from .gravestone_templates import GravestoneTemplate, choose_gravestone_template


class GravestoneUnavailableError(IdentityV2ValidationError):
    """No unreserved, usable template exists for an individual grave."""


def reserve_individual_gravestone(
    store: IdentityV2Store, member: Member,
    templates: Iterable[GravestoneTemplate],
) -> None:
    """Reserve one existing template on a working store copy, without I/O."""
    if member.graveTemplateId is not None:
        return
    occupied = {item.graveTemplateId for item in store.members
                if item.graveTemplateId is not None}
    available = [template for template in templates
                 if template.grave_template_id not in occupied
                 and normalize_gravestone_category(template.category) is not None]
    selected_id = choose_gravestone_template(
        (template.grave_template_id for template in available), member.memberId)
    if not selected_id:
        raise GravestoneUnavailableError("Kein freier Grabstein verfügbar.")
    template = next(item for item in available
                    if item.grave_template_id == selected_id)
    member.graveTemplateId = selected_id
    member.portraitOffsetX = template.default_portrait_offset_x
    member.portraitOffsetY = template.default_portrait_offset_y
    member.portraitZoom = template.default_portrait_zoom
    # Text geometry remains at the Member's existing defaults/values; the
    # template's text-safe-area is consumed by the shared card renderer.


def repair_missing_individual_gravestones(
    store: IdentityV2Store, templates: Iterable[GravestoneTemplate],
) -> IdentityV2Store:
    """Return an all-or-nothing upgrade copy of old individual graves."""
    store.validate()
    missing_ids = sorted(member.memberId for member in store.members
                         if member.lifeStatus == "dead"
                         and member.burialType == "individual"
                         and member.graveTemplateId is None)
    if not missing_ids:
        return store
    result = copy.deepcopy(store)
    by_id = {member.memberId: member for member in result.members}
    ordered_templates = tuple(templates)
    for member_id in missing_ids:
        reserve_individual_gravestone(
            result, by_id[member_id], ordered_templates)
    result.validate()
    return result


@dataclass(frozen=True)
class GraveyardEntry:
    memberId: str
    name: str
    className: str | None
    race: str | None
    deathDate: str | None
    playerName: str | None
    burialType: str
    graveTemplateId: str | None


def graveyard_entries(store: IdentityV2Store) -> tuple[tuple[GraveyardEntry, ...],
                                                       tuple[GraveyardEntry, ...]]:
    """Project dead characters without changing the store or merging names."""
    player_names = {player.playerId: player.displayName for player in store.players}
    individual: list[GraveyardEntry] = []
    collective: list[GraveyardEntry] = []
    for member in store.members:
        if member.lifeStatus != "dead":
            continue
        entry = GraveyardEntry(
            member.memberId, member.name, member.className, member.race,
            member.deathDate, player_names.get(member.playerId),
            member.burialType, member.graveTemplateId,
        )
        (individual if member.burialType == "individual" else collective).append(entry)
    order = lambda item: (item.deathDate or "", item.name.casefold(), item.memberId)
    return (tuple(sorted(individual, key=order, reverse=True)),
            tuple(sorted(collective, key=order, reverse=True)))


def _geometry(value: object, field_name: str, low: float, high: float) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not isfinite(value) or not low <= value <= high):
        raise IdentityV2ValidationError(f"Invalid {field_name}: {value!r}.")
    return float(value)


def set_member_gravestone_adjustment(
    store: IdentityV2Store, member_id: str, template_id: str,
    portrait_offset_x: object, portrait_offset_y: object, portrait_zoom: object,
    text_offset_x: object, text_offset_y: object, text_scale: object,
    templates_by_id: Mapping[str, object],
) -> IdentityV2Store:
    """Persist one editor draft after validating inventory, category and ownership."""
    store.validate()
    source = next((member for member in store.members if member.memberId == member_id), None)
    if source is None or source.lifeStatus != "dead":
        raise IdentityV2ValidationError("Gravestone target must be a dead memberId.")
    if not isinstance(template_id, str):
        raise IdentityV2ValidationError("Gravestone template ID must be text.")
    template = templates_by_id.get(template_id)
    if template is None or normalize_gravestone_category(
            getattr(template, "category", None)) is None:
        raise IdentityV2ValidationError("Gravestone template must have a known category.")
    if any(member.memberId != member_id and member.graveTemplateId == template_id
           for member in store.members):
        raise IdentityV2ValidationError("Gravestone template is already assigned.")
    geometry = {
        "portraitOffsetX": _geometry(portrait_offset_x, "portraitOffsetX", -1.0, 1.0),
        "portraitOffsetY": _geometry(portrait_offset_y, "portraitOffsetY", -1.0, 1.0),
        "portraitZoom": _geometry(portrait_zoom, "portraitZoom", 1.0, 2.0),
        "textOffsetX": _geometry(text_offset_x, "textOffsetX", -1.0, 1.0),
        "textOffsetY": _geometry(text_offset_y, "textOffsetY", -1.0, 1.0),
        "textScale": _geometry(text_scale, "textScale", 0.65, 1.5),
    }
    result = copy.deepcopy(store)
    target = next(member for member in result.members if member.memberId == member_id)
    target.graveTemplateId = template_id
    for name, value in geometry.items():
        setattr(target, name, value)
    result.validate()
    return result


def gravestone_visual_fields(member: Member) -> dict[str, object]:
    """Fields consumed by the existing card renderer and Qt editor."""
    return {
        "id": member.memberId,
        "name": member.name,
        "className": member.className or "",
        "deathDate": member.deathDate or "",
        "graveTemplateId": member.graveTemplateId or "",
        "portraitOffsetX": member.portraitOffsetX,
        "portraitOffsetY": member.portraitOffsetY,
        "portraitZoom": member.portraitZoom,
        "textOffsetX": member.textOffsetX,
        "textOffsetY": member.textOffsetY,
        "textScale": member.textScale,
    }
