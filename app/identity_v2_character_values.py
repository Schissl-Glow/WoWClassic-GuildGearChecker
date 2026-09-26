"""Canonical character choices shared by the V2 model and character edits.

These are the persisted v0.11.3 choices, kept independent of the legacy GUI.
"""

from __future__ import annotations


CLASS_SPECS: dict[str, tuple[str, ...]] = {
    "Druid": ("Balance", "Feral", "Restoration"),
    "Hunter": ("Beast Mastery", "Marksmanship", "Survival"),
    "Mage": ("Arcane", "Fire", "Frost"),
    "Paladin": ("Holy", "Protection", "Retribution"),
    "Priest": ("Discipline", "Holy", "Shadow"),
    "Rogue": ("Assassination", "Combat", "Subtlety"),
    "Shaman": ("Elemental", "Enhancement", "Restoration"),
    "Warlock": ("Affliction", "Demonology", "Destruction"),
    "Warrior": ("Arms", "Fury", "Protection"),
}
RACES = ("Human", "Dwarf", "Night Elf", "Gnome", "Orc", "Undead", "Tauren", "Troll")
RAID_ROLES = ("not_set", "tank", "healer", "dps")
GEAR_STATUSES = ("Level", "Pre-BiS", "BiS", "S+")
RAID_STATUSES = ("", "Bereit", "Nicht bereit")


def canonical_choice(value: str, choices: tuple[str, ...]) -> str | None:
    """Accept a UI spelling case-insensitively; return the stored spelling."""
    if not isinstance(value, str):
        return None
    text = value.strip().casefold()
    return next((choice for choice in choices if choice.casefold() == text), None)
