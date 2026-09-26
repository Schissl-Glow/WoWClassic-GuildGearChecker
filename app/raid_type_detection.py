"""Deterministic raid-type recognition shared by CLM, CSV and V2 projections."""

from __future__ import annotations

import re
import unicodedata


REGULAR_RAID_TYPES = frozenset({"ZG", "AQ20", "MC", "BWL", "AQ40", "Naxx"})

# These are explicit names and abbreviations, not approximate name matches.
_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ZG", (r"zg", r"zul[\s'’_-]*gurub")),
    ("AQ20", (
        r"aq[\s_-]*20", r"aq(?![\s_-]*(?:20|40))",
        r"ruins[\s_-]+of[\s_-]+ahn[\s'’_-]*qiraj",
    )),
    ("MC", (r"mc", r"molten[\s_-]+core")),
    ("BWL", (r"bwl", r"blackwing[\s_-]+lair")),
    ("AQ40", (r"aq[\s_-]*40", r"temple[\s_-]+of[\s_-]+ahn[\s'’_-]*qiraj")),
    ("Naxx", (r"naxx(?:ramas)?(?:[\s_-]*40)?",)),
    ("Onyxia", (r"ony", r"onyxia(?:['’]?s)?(?:[\s_-]+lair)?")),
    ("World Boss", (
        r"world[\s_-]*boss", r"azu", r"azzuregos", r"azuregos",
        r"lord[\s_-]+kazzak",
        r"kazzak", r"emeriss", r"lethon", r"taerar", r"ysondre",
        r"dragons[\s_-]+of[\s_-]+nightmare",
        r"teremus(?:[\s_-]+the[\s_-]+devourer)?",
    )),
)

_PATTERNS = tuple(
    (raid_type, re.compile(rf"(?<!\w)(?:{alias})(?!\w)", re.IGNORECASE))
    for raid_type, aliases in _ALIASES for alias in aliases
)


def _text(value: object) -> str:
    return unicodedata.normalize("NFC", str(value or "").strip())


def raid_type_mentions(value: object) -> tuple[tuple[int, str], ...]:
    """Return each explicitly named type at its first position in the text."""
    title = _text(value).replace("_", " ")
    positions: dict[str, int] = {}
    for raid_type, pattern in _PATTERNS:
        for match in pattern.finditer(title):
            positions[raid_type] = min(positions.get(raid_type, match.start()),
                                       match.start())
    order = {raid_type: index for index, (raid_type, _) in enumerate(_ALIASES)}
    return tuple(sorted(((position, raid_type)
                         for raid_type, position in positions.items()),
                        key=lambda item: (item[0], order[item[1]])))


def detect_raid_type(value: object) -> str | None:
    """Choose the first regular raid, then Onyxia/World Boss if none exists."""
    title = _text(value).replace("_", " ")
    mentions = raid_type_mentions(title)
    if not mentions:
        return None
    regular = [raid_type for _position, raid_type in mentions
               if raid_type in REGULAR_RAID_TYPES]
    return regular[0] if regular else mentions[0][1]
