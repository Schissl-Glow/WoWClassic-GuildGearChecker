"""Lightweight local project references for the future start menu.

The .ggc file remains authoritative. Listing entries never opens a project.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import os

from .i18n import default_settings_path
from .identity_v2 import IdentityV2Store
from .identity_v2_storage import load_identity_v2
from .window_geometry import read_suite_settings, update_suite_settings


CATALOG_KEY = "known_projects"
LAST_PROJECT_KEY = "last_project_path"


def normalized_project_path(path: Path | str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if resolved.suffix.casefold() != ".ggc":
        raise ValueError("Projektdateien müssen die Endung .ggc verwenden.")
    return resolved


def _path_key(path: Path | str) -> str:
    return os.path.normcase(str(normalized_project_path(path))).casefold()


@dataclass(frozen=True)
class ProjectEntry:
    path: Path
    guild_name: str
    realm: str
    point_mode: str
    last_opened_at: str | None
    clm_lua_path: Path | None

    @property
    def missing(self) -> bool:
        return not self.path.is_file()


class ProjectCatalog:
    def __init__(
        self, settings_path: Path | str | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings_path = Path(settings_path) if settings_path else default_settings_path()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _records(self) -> list[dict]:
        raw = read_suite_settings(self.settings_path).get(CATALOG_KEY, [])
        result: list[dict] = []
        for item in raw if isinstance(raw, list) else ():
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            try:
                normalized_project_path(item["path"])
            except (OSError, ValueError):
                continue
            result.append(dict(item))
        return result

    def _save(self, records: list[dict], last_path: str | None) -> None:
        update_suite_settings(
            self.settings_path, **{CATALOG_KEY: records, LAST_PROJECT_KEY: last_path})

    @staticmethod
    def _record(path: Path, store: IdentityV2Store) -> dict:
        return {
            "path": str(path), "guildName": store.guildName,
            "realm": store.realm, "pointMode": store.pointMode,
            "lastOpenedAt": None, "clmLuaPath": None,
        }

    def entries(self) -> tuple[ProjectEntry, ...]:
        """Read only settings; file availability is checked on demand."""
        result: list[ProjectEntry] = []
        seen: set[str] = set()
        for record in self._records():
            try:
                path = normalized_project_path(record["path"])
                key = _path_key(path)
            except (OSError, ValueError):
                continue
            if key in seen:
                continue
            seen.add(key)
            lua = record.get("clmLuaPath")
            result.append(ProjectEntry(
                path, str(record.get("guildName") or ""),
                str(record.get("realm") or ""),
                str(record.get("pointMode") or ""),
                str(record.get("lastOpenedAt")) if record.get("lastOpenedAt") else None,
                Path(lua) if isinstance(lua, str) and lua else None,
            ))
        return tuple(result)

    def sorted_entries(self) -> tuple[ProjectEntry, ...]:
        return tuple(sorted(self.entries(), key=lambda item: (
            item.last_opened_at or "", str(item.path).casefold()), reverse=True))

    def last_project(self) -> ProjectEntry | None:
        raw = read_suite_settings(self.settings_path).get(LAST_PROJECT_KEY)
        if not isinstance(raw, str) or not raw:
            return None
        try:
            key = _path_key(raw)
        except (OSError, ValueError):
            return None
        return next((item for item in self.entries() if _path_key(item.path) == key), None)

    def add_project(
        self, path: Path | str, *, store: IdentityV2Store | None = None,
    ) -> ProjectEntry:
        project = normalized_project_path(path)
        if not project.is_file():
            raise FileNotFoundError(project)
        actual = store if store is not None else load_identity_v2(project)
        actual.validate()
        records = self._records()
        key = _path_key(project)
        existing = next((item for item in records
                         if _path_key(item["path"]) == key), None)
        updated = self._record(project, actual)
        if existing is None:
            records.append(updated)
        else:
            updated["lastOpenedAt"] = existing.get("lastOpenedAt")
            updated["clmLuaPath"] = existing.get("clmLuaPath")
            existing.clear()
            existing.update(updated)
        self._save(records, read_suite_settings(self.settings_path).get(LAST_PROJECT_KEY))
        return next(item for item in self.entries() if _path_key(item.path) == key)

    def remove_project(self, path: Path | str) -> None:
        key = _path_key(path)
        records = [item for item in self._records()
                   if _path_key(item["path"]) != key]
        last = read_suite_settings(self.settings_path).get(LAST_PROJECT_KEY)
        if isinstance(last, str) and _path_key(last) == key:
            last = None
        self._save(records, last)

    def relocate_project(self, old_path: Path | str, new_path: Path | str) -> ProjectEntry:
        old_key = _path_key(old_path)
        project = normalized_project_path(new_path)
        actual = load_identity_v2(project)
        records = self._records()
        old = next((item for item in records
                    if _path_key(item["path"]) == old_key), None)
        if old is None:
            raise KeyError(str(old_path))
        if any(item is not old and _path_key(item["path"]) == _path_key(project)
               for item in records):
            raise ValueError("Projekt ist bereits in der Liste bekannt.")
        replacement = self._record(project, actual)
        replacement["lastOpenedAt"] = old.get("lastOpenedAt")
        if (old.get("guildName"), old.get("realm"), old.get("pointMode")) == (
                actual.guildName, actual.realm, actual.pointMode):
            replacement["clmLuaPath"] = old.get("clmLuaPath")
        old.clear()
        old.update(replacement)
        last = read_suite_settings(self.settings_path).get(LAST_PROJECT_KEY)
        if isinstance(last, str) and _path_key(last) == old_key:
            last = str(project)
        self._save(records, last)
        return next(item for item in self.entries()
                    if _path_key(item.path) == _path_key(project))

    def mark_opened(self, path: Path | str, store: IdentityV2Store) -> ProjectEntry:
        self.add_project(path, store=store)
        project = normalized_project_path(path)
        records = self._records()
        record = next(item for item in records
                      if _path_key(item["path"]) == _path_key(project))
        record["lastOpenedAt"] = self._clock().astimezone(timezone.utc).isoformat()
        self._save(records, str(project))
        return next(item for item in self.entries()
                    if _path_key(item.path) == _path_key(project))

    def set_clm_path(self, project_path: Path | str, lua_path: Path | str) -> None:
        key = _path_key(project_path)
        lua = Path(lua_path).expanduser().resolve()
        if lua.name.casefold() != "classiclootmanager.lua" or not lua.is_file():
            raise ValueError("Eine gültige ClassicLootManager.lua ist erforderlich.")
        records = self._records()
        record = next((item for item in records
                       if _path_key(item["path"]) == key), None)
        if record is None:
            raise KeyError(str(project_path))
        record["clmLuaPath"] = str(lua)
        self._save(records, read_suite_settings(self.settings_path).get(LAST_PROJECT_KEY))

    def get_clm_path(self, project_path: Path | str) -> Path | None:
        key = _path_key(project_path)
        entry = next((item for item in self.entries()
                      if _path_key(item.path) == key), None)
        return entry.clm_lua_path if entry else None
