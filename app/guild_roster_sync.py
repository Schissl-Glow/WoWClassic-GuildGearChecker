# -*- coding: utf-8 -*-
"""Guild roster snapshot fetching, parsing and comparison helpers.

The module is deliberately UI-agnostic so the current local JSON handoff can later
be replaced by an API-backed implementation without changing the comparison rules.
"""
from __future__ import annotations

import html as html_module
import json
import os
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

GUILD_ROSTER_FORMAT = "GuildGearCheckerGuildRosterSnapshot"
GUILD_ROSTER_VERSION = 1
GUILD_ROSTER_SOURCE = "classicwowarmory"
# BEGIN LEGACY_ARMORY_GUILD_ROSTER_FETCH
# UI access is disabled because the public Armory guild list also contains
# low-level characters. Keep this fetch/parser block isolated for later removal.
MAX_GUILD_PAGES = 250

_CHARACTER_LINK_RE = re.compile(
    r'''href\s*=\s*["'](?:https?://[^/]+)?/character/([^/"'?&#]+)/([^/"'?&#]+)/([^"'?#/]+)(?:\?[^"']*)?["']''',
    re.IGNORECASE,
)
_PAGE_LINK_RE = re.compile(r'''[?&]page=(\d+)''', re.IGNORECASE)


def norm_name(value: object) -> str:
    return unicodedata.normalize("NFC", str(value or "").strip()).casefold()


def _canonical_optional(value: object) -> str | None:
    text = unicodedata.normalize("NFC", str(value or "").strip())
    return text or None


def build_guild_url(realm: str, guild_name: str, page: int = 1,
                    game_version: str = "classic1x", legacy: bool = False) -> str:
    """Build the public ClassicWoWArmory guild URL without guessing a region path."""
    guild = urllib.parse.quote(unicodedata.normalize("NFC", guild_name.strip()), safe="")
    realm_part = urllib.parse.quote(str(realm or "").strip(), safe="")
    if not guild:
        raise ValueError("Guild name is required.")
    if legacy:
        base = f"https://classicwowarmory.com/guild/{guild}"
    else:
        if not realm_part:
            raise ValueError("Realm is required.")
        base = f"https://classicwowarmory.com/guild/{realm_part}/{guild}"
    query = urllib.parse.urlencode({"page": max(1, int(page)), "game_version": game_version or "classic1x"})
    return f"{base}?{query}"


def parse_guild_roster_html(content: str, expected_region: str, expected_realm: str) -> list[str]:
    """Extract exact character names from guild-page character links.

    Only links for the configured region and realm are accepted. The original name
    spelling is preserved and duplicates are removed case-insensitively.
    """
    expected_region_key = str(expected_region or "").strip().casefold()
    expected_realm_key = str(expected_realm or "").strip().casefold()
    names: list[str] = []
    seen: set[str] = set()
    for region_raw, realm_raw, name_raw in _CHARACTER_LINK_RE.findall(str(content or "")):
        region = urllib.parse.unquote(html_module.unescape(region_raw)).strip()
        realm = urllib.parse.unquote(html_module.unescape(realm_raw)).strip()
        if region.casefold() != expected_region_key or realm.casefold() != expected_realm_key:
            continue
        name = unicodedata.normalize(
            "NFC", urllib.parse.unquote(html_module.unescape(name_raw)).strip()
        )
        key = norm_name(name)
        if key and key not in seen:
            seen.add(key)
            names.append(name)
    return names


def parse_guild_page_numbers(content: str) -> tuple[int, ...]:
    pages = {1}
    for raw in _PAGE_LINK_RE.findall(str(content or "")):
        try:
            page = int(raw)
        except (TypeError, ValueError):
            continue
        if 1 <= page <= MAX_GUILD_PAGES:
            pages.add(page)
    return tuple(sorted(pages))


def _default_fetch(url: str, timeout: float = 25.0) -> str:
    import urllib.request

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GuildGearChecker/0.7",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"
    return raw.decode(encoding, errors="replace")


def fetch_guild_roster(guild_name: str, region: str, realm: str,
                       game_version: str = "classic1x",
                       fetcher: Callable[[str], str] | None = None,
                       progress: Callable[[int, int], None] | None = None) -> tuple[list[str], str]:
    """Fetch all pages of a guild roster and return names plus the working base URL.

    Current realm-qualified and legacy URL shapes are both supported. Fetching is
    intentionally sequential and user-triggered.
    """
    guild_name = unicodedata.normalize("NFC", str(guild_name or "").strip())
    region = str(region or "").strip()
    realm = str(realm or "").strip()
    if not guild_name:
        raise ValueError("Guild name is required.")
    if not region or not realm:
        raise ValueError("Region and realm are required.")
    fetch = fetcher or _default_fetch

    last_error: Exception | None = None
    for legacy in (False, True):
        first_url = build_guild_url(realm, guild_name, 1, game_version, legacy=legacy)
        try:
            first_html = fetch(first_url)
            names = parse_guild_roster_html(first_html, region, realm)
            pages = parse_guild_page_numbers(first_html)
            if not names and len(pages) == 1:
                raise ValueError("No matching guild members found on the page.")
            seen = {norm_name(name) for name in names}
            all_names = list(names)
            total = max(pages)
            if progress:
                progress(1, total)
            for page in range(2, total + 1):
                page_html = fetch(build_guild_url(realm, guild_name, page, game_version, legacy=legacy))
                for name in parse_guild_roster_html(page_html, region, realm):
                    key = norm_name(name)
                    if key and key not in seen:
                        seen.add(key)
                        all_names.append(name)
                if progress:
                    progress(page, total)
            if not all_names:
                raise ValueError("No matching guild members found.")
            return all_names, first_url
        except Exception as exc:  # try legacy route before surfacing the error
            last_error = exc
    raise RuntimeError(str(last_error or "Guild roster could not be fetched."))
# END LEGACY_ARMORY_GUILD_ROSTER_FETCH


def build_snapshot(guild_name: str, region: str, realm: str, game_version: str,
                   source_url: str, names: Iterable[str],
                   records: dict[str, dict] | None = None) -> dict:
    records = records or {}
    members = []
    seen: set[str] = set()
    for raw_name in names:
        name = unicodedata.normalize("NFC", str(raw_name or "").strip())
        key = norm_name(name)
        if not key or key in seen:
            continue
        seen.add(key)
        record = records.get(key) or {}
        members.append({
            "characterName": name,
            "race": _canonical_optional(record.get("race")),
            "className": _canonical_optional(record.get("className")),
        })
    return {
        "format": GUILD_ROSTER_FORMAT,
        "formatVersion": GUILD_ROSTER_VERSION,
        "fetchedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "region": str(region or "").strip(),
        "realm": str(realm or "").strip(),
        "gameVersion": str(game_version or "").strip(),
        "guild": unicodedata.normalize("NFC", str(guild_name or "").strip()),
        "source": GUILD_ROSTER_SOURCE,
        "sourceUrl": str(source_url or "").strip(),
        "members": members,
    }


def write_snapshot_atomic(path: Path, payload: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def merge_snapshot_member_data(path: Path, character_name: str, race: object = None,
                               class_name: object = None) -> bool:
    """Enrich an existing snapshot after later per-character Armory extraction."""
    path = Path(path)
    if not path.is_file():
        return False
    payload = load_snapshot(path)
    key = norm_name(character_name)
    changed = False
    for member in payload["members"]:
        if norm_name(member.get("characterName")) != key:
            continue
        normalized_race = _canonical_optional(race)
        normalized_class = _canonical_optional(class_name)
        if normalized_race and member.get("race") != normalized_race:
            member["race"] = normalized_race
            changed = True
        if normalized_class and member.get("className") != normalized_class:
            member["className"] = normalized_class
            changed = True
        break
    if changed:
        write_snapshot_atomic(path, payload)
    return changed


def load_snapshot(path: Path, expected_region: str | None = None,
                  expected_realm: str | None = None,
                  expected_game_version: str | None = None) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Guild roster snapshot must be a JSON object.")
    if payload.get("format") != GUILD_ROSTER_FORMAT or payload.get("formatVersion") != GUILD_ROSTER_VERSION:
        raise ValueError("Unsupported guild roster snapshot format.")
    for field, expected in (
        ("region", expected_region), ("realm", expected_realm), ("gameVersion", expected_game_version),
    ):
        if expected is not None and str(payload.get(field) or "").casefold() != str(expected).casefold():
            raise ValueError(f"Guild roster snapshot {field} does not match the project context.")
    raw_members = payload.get("members")
    if not isinstance(raw_members, list):
        raise ValueError("Guild roster snapshot has no valid members list.")
    normalized = []
    seen: set[str] = set()
    for item in raw_members:
        if not isinstance(item, dict):
            raise ValueError("Guild roster snapshot contains an invalid member entry.")
        name = unicodedata.normalize("NFC", str(item.get("characterName") or "").strip())
        key = norm_name(name)
        if not key:
            raise ValueError("Guild roster snapshot contains an empty character name.")
        if key in seen:
            raise ValueError(f"Guild roster snapshot contains duplicate character name: {name}")
        seen.add(key)
        normalized.append({
            "characterName": name,
            "race": _canonical_optional(item.get("race")),
            "className": _canonical_optional(item.get("className")),
        })
    result = dict(payload)
    result["members"] = normalized
    return result


@dataclass(frozen=True)
class RosterComparisonItem:
    key: str
    name: str
    category: str
    member_id: str | None
    life_status: str | None
    current_race: str | None
    incoming_race: str | None
    current_class: str | None
    incoming_class: str | None


def compare_snapshot(existing_members: Iterable[dict], snapshot: dict) -> list[RosterComparisonItem]:
    """Classify roster differences using exact normalized names and current life status."""
    by_name: dict[str, list[dict]] = {}
    for member in existing_members:
        key = norm_name(member.get("name"))
        if key:
            by_name.setdefault(key, []).append(member)

    results: list[RosterComparisonItem] = []
    snapshot_keys: set[str] = set()
    for entry in snapshot.get("members", []):
        name = entry["characterName"]
        key = norm_name(name)
        snapshot_keys.add(key)
        matches = by_name.get(key, [])
        current = [m for m in matches if m.get("lifeStatus") in {"active", "inactive"}]
        if len(current) > 1:
            category = "conflict"
            member = current[0]
        elif current:
            member = current[0]
            category = "known" if member.get("lifeStatus") == "active" else "inactive_found"
        else:
            dead = [m for m in matches if m.get("lifeStatus") == "dead"]
            member = dead[-1] if dead else None
            category = "new_incarnation" if dead else "new"
        results.append(RosterComparisonItem(
            key=key,
            name=name,
            category=category,
            member_id=str(member.get("id") or "") or None if member else None,
            life_status=str(member.get("lifeStatus") or "") or None if member else None,
            current_race=_canonical_optional(member.get("race")) if member else None,
            incoming_race=_canonical_optional(entry.get("race")),
            current_class=_canonical_optional(member.get("className")) if member else None,
            incoming_class=_canonical_optional(entry.get("className")),
        ))

    for member in existing_members:
        if member.get("lifeStatus") != "active":
            continue
        key = norm_name(member.get("name"))
        if not key or key in snapshot_keys:
            continue
        results.append(RosterComparisonItem(
            key=key,
            name=str(member.get("name") or ""),
            category="missing_active",
            member_id=str(member.get("id") or "") or None,
            life_status="active",
            current_race=_canonical_optional(member.get("race")),
            incoming_race=None,
            current_class=_canonical_optional(member.get("className")),
            incoming_class=None,
        ))
    order = {"new": 0, "new_incarnation": 1, "inactive_found": 2, "missing_active": 3, "known": 4, "conflict": 5}
    return sorted(results, key=lambda item: (order.get(item.category, 99), item.name.casefold(), item.name))
