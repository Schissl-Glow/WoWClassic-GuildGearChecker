"""Eindeutiges Unicode-sicheres CLM-zu-Charakter-Matching."""

from __future__ import annotations

import unicodedata
from typing import Iterable

try:
    from .clm_models import (
        ClmCharacterBalance, ClmCharacterMatch, ClmMatchingResult,
    )
except ImportError:
    from clm_models import (  # type: ignore
        ClmCharacterBalance, ClmCharacterMatch, ClmMatchingResult,
    )


def strip_realm_suffix(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value or "").strip())
    if "-" not in text:
        return text
    character, realm = text.rsplit("-", 1)
    return character if character and realm else text


def character_key(value: object) -> str:
    return strip_realm_suffix(value).casefold()


def match_characters(
    balances: Iterable[ClmCharacterBalance], members: Iterable[object],
) -> ClmMatchingResult:
    members_by_name: dict[str, list[object]] = {}
    for member in members:
        members_by_name.setdefault(character_key(getattr(member, "name", "")), []).append(member)

    matches: list[ClmCharacterMatch] = []
    unknown: list[str] = []
    ambiguous: list[str] = []
    for balance in balances:
        candidates = members_by_name.get(character_key(balance.name), [])
        if not candidates:
            unknown.append(balance.name)
            continue
        if len(candidates) != 1:
            ambiguous.append(balance.name)
            continue
        member = candidates[0]
        matches.append(ClmCharacterMatch(
            clm_name=balance.name,
            member_id=str(getattr(member, "id", "")),
            character_name=str(getattr(member, "name", "")),
            points=balance.points,
        ))
    return ClmMatchingResult(tuple(matches), tuple(unknown), tuple(ambiguous))
