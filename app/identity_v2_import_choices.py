"""Shared import classification of finalized V2 character identities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterImportChoice:
    activity_status: str = "active"
    relevance: str = "relevant"
    player_id: str | None = None
    current_role: str | None = None
    class_name: str | None = None
    member_id: str | None = None
