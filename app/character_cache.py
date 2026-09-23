# -*- coding: utf-8 -*-
"""Persistent, membership-neutral Armory character metadata cache."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import unicodedata
from typing import Callable


CACHE_FORMAT = "GuildGearCheckerCharacterCache"
CACHE_FORMAT_VERSION = 1
CACHE_RELATIVE_PATH = Path("data") / "cache" / "armory_character_cache.json"

LOGGER = logging.getLogger(__name__)


class CharacterCacheError(ValueError):
    pass


def character_cache_path(project_root: Path) -> Path:
    return Path(project_root) / CACHE_RELATIVE_PATH


def empty_character_cache() -> dict:
    return {
        "format": CACHE_FORMAT,
        "formatVersion": CACHE_FORMAT_VERSION,
        "characters": [],
    }


def _text(value: object) -> str:
    return unicodedata.normalize("NFC", str(value or "").strip())


def _key(value: object) -> str:
    return _text(value).casefold()


def _normalize_entry(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = _text(raw.get("characterName"))
    region = _text(raw.get("region"))
    realm = _text(raw.get("realm"))
    if not name or not region or not realm:
        return None
    return {
        "memberId": _text(raw.get("memberId")) or None,
        "characterName": name,
        "region": region,
        "realm": realm,
        "gameVersion": _text(raw.get("gameVersion")) or None,
        "race": _text(raw.get("race")) or None,
        "className": _text(raw.get("className")) or None,
        "timestamp": _text(raw.get("timestamp")) or None,
    }


def _read_character_cache(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        return empty_character_cache()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise CharacterCacheError(f"Character Cache ist kein gültiges JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CharacterCacheError("Character Cache muss ein JSON-Objekt sein.")
    if (payload.get("format") != CACHE_FORMAT
            or payload.get("formatVersion") != CACHE_FORMAT_VERSION):
        raise CharacterCacheError("Character Cache hat ein nicht unterstütztes Format.")
    raw_characters = payload.get("characters")
    if not isinstance(raw_characters, list):
        raise CharacterCacheError("Character Cache enthält keine gültige characters-Liste.")
    normalized_characters = []
    for index, raw in enumerate(raw_characters, start=1):
        entry = _normalize_entry(raw)
        if entry is None:
            raise CharacterCacheError(
                f"Character Cache enthält einen ungültigen Eintrag an Position {index}."
            )
        normalized_characters.append(entry)
    result = empty_character_cache()
    result["characters"] = normalized_characters
    return result


def load_character_cache(path: Path, on_error: Callable[[str], None] | None = None) -> dict:
    """Load safely; a missing or broken cache must never block application startup."""
    try:
        return _read_character_cache(path)
    except CharacterCacheError as exc:
        LOGGER.warning("Character Cache konnte nicht geladen werden: %s", exc)
        if on_error is not None:
            on_error(str(exc))
        return empty_character_cache()


def write_character_cache_atomic(path: Path, payload: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return path


def _context_matches(entry: dict, region: object, realm: object, game_version: object) -> bool:
    if _key(entry.get("region")) != _key(region) or _key(entry.get("realm")) != _key(realm):
        return False
    cached_game = _key(entry.get("gameVersion"))
    requested_game = _key(game_version)
    return not cached_game or not requested_game or cached_game == requested_game


def _matching_entries(payload: dict, character_name: object, region: object,
                      realm: object, game_version: object) -> list[dict]:
    name_key = _key(character_name)
    return [
        entry for entry in payload.get("characters", [])
        if isinstance(entry, dict)
        and _key(entry.get("characterName")) == name_key
        and _context_matches(entry, region, realm, game_version)
    ]


def find_character_cache_record(payload: dict, *, member_id: object,
                                character_name: object, region: object,
                                realm: object, game_version: object) -> dict | None:
    """Return one unambiguous compatible record, preferring a matching member ID."""
    entries = payload.get("characters") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return None
    wanted_id = _key(member_id)
    compatible = [
        entry for entry in entries
        if isinstance(entry, dict) and _context_matches(entry, region, realm, game_version)
    ]
    if wanted_id:
        id_matches = [entry for entry in compatible if _key(entry.get("memberId")) == wanted_id]
        named_id_matches = [
            entry for entry in id_matches
            if _key(entry.get("characterName")) == _key(character_name)
        ]
        if len(named_id_matches) == 1:
            return named_id_matches[0]
        if id_matches:
            return None
    name_matches = [
        entry for entry in compatible
        if _key(entry.get("characterName")) == _key(character_name)
        and (not wanted_id or not _key(entry.get("memberId")))
    ]
    return name_matches[0] if len(name_matches) == 1 else None


def update_character_cache(path: Path, *, member_id: object, character_name: object,
                           region: object, realm: object, game_version: object,
                           race: object, class_name: object,
                           updated_at: object = None) -> dict:
    """Atomically insert or update exactly one character while preserving all others."""
    name = _text(character_name)
    clean_region = _text(region)
    clean_realm = _text(realm)
    clean_game = _text(game_version) or None
    clean_member_id = _text(member_id) or None
    clean_race = _text(race) or None
    clean_class = _text(class_name) or None
    if not name or not clean_region or not clean_realm:
        raise CharacterCacheError("Character Cache benötigt characterName, region und realm.")
    if not clean_race and not clean_class:
        raise CharacterCacheError("Character Cache benötigt Race oder Class.")

    # Strict loading is intentional here: a corrupt cache is never silently overwritten.
    payload = _read_character_cache(path)
    characters = payload["characters"]
    matches = _matching_entries(payload, name, clean_region, clean_realm, clean_game)
    target = None
    if clean_member_id:
        id_matches = [entry for entry in characters if (
            _key(entry.get("memberId")) == _key(clean_member_id)
            and _context_matches(entry, clean_region, clean_realm, clean_game)
        )]
        incompatible = [entry for entry in id_matches if _key(entry.get("characterName")) != _key(name)]
        if incompatible:
            raise CharacterCacheError("Member-ID ist im Character Cache einem anderen Namen zugeordnet.")
        if len(id_matches) > 1:
            raise CharacterCacheError("Member-ID ist im Character Cache nicht eindeutig.")
        target = id_matches[0] if id_matches else None
    if target is None:
        if len(matches) > 1:
            raise CharacterCacheError("Character Cache enthält mehrere passende Namenseinträge.")
        target = matches[0] if matches else None
        if (target is not None and clean_member_id and target.get("memberId")
                and _key(target.get("memberId")) != _key(clean_member_id)):
            raise CharacterCacheError(
                "Der passende Name ist im Character Cache einer anderen Member-ID zugeordnet."
            )
    if target is None:
        target = {
            "memberId": clean_member_id,
            "characterName": name,
            "region": clean_region,
            "realm": clean_realm,
            "gameVersion": clean_game,
            "race": None,
            "className": None,
            "timestamp": None,
        }
        characters.append(target)

    target["memberId"] = clean_member_id or target.get("memberId")
    target["characterName"] = name
    target["region"] = clean_region
    target["realm"] = clean_realm
    target["gameVersion"] = clean_game or target.get("gameVersion")
    if clean_race:
        target["race"] = clean_race
    if clean_class:
        target["className"] = clean_class
    target["timestamp"] = _text(updated_at) or datetime.now(timezone.utc).isoformat()
    write_character_cache_atomic(path, payload)
    return dict(target)


__all__ = [
    "CACHE_FORMAT", "CACHE_FORMAT_VERSION", "CACHE_RELATIVE_PATH",
    "CharacterCacheError", "character_cache_path", "empty_character_cache",
    "find_character_cache_record", "load_character_cache",
    "update_character_cache", "write_character_cache_atomic",
]
