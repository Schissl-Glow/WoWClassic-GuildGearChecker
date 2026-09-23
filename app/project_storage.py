# -*- coding: utf-8 -*-
"""Gemeinsame, projektbezogene Speicherpfade für Checker und Portrait Grabber."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ProjectPaths:
    project: Path
    root: Path
    portraits: Path
    history: Path
    autosave_dir: Path
    autosave: Path
    backups: Path
    runtime: Path
    handoff: Path


@dataclass(frozen=True)
class PortraitMigrationSummary:
    migrated_member_ids: tuple[str, ...] = ()
    ambiguous_names: tuple[str, ...] = ()
    skipped_member_ids: tuple[str, ...] = ()


@lru_cache(maxsize=32)
def _cached_project_paths(expanded_path: str, relative_root: str) -> ProjectPaths:
    source = Path(relative_root, expanded_path) if relative_root else Path(expanded_path)
    project = source.resolve()
    if project.suffix.casefold() != ".ggc":
        raise ValueError("Projektdateien müssen die Endung .ggc verwenden.")
    root = project.parent
    portraits = root / "portraits"
    return ProjectPaths(
        project=project,
        root=root,
        portraits=portraits,
        history=portraits / "history",
        autosave_dir=root / "autosave",
        autosave=root / "autosave" / f"{project.stem}_autosave.ggc",
        backups=root / "backups",
        runtime=root / "runtime",
        handoff=root / "runtime" / f"{project.stem}_handoff",
    )


def project_paths(project_path: Path | str) -> ProjectPaths:
    expanded = Path(project_path).expanduser()
    relative_root = str(Path.cwd()) if not expanded.is_absolute() else ""
    return _cached_project_paths(str(expanded), relative_root)


def portrait_root(project_path: Path | str | None) -> Path | None:
    return project_paths(project_path).portraits if project_path else None


def member_portrait_path(project_path: Path | str, member_id: object) -> Path:
    """Return the one productive portrait path for a concrete character instance."""
    stable_id = str(member_id or "").strip()
    if (not stable_id or Path(stable_id).name != stable_id
            or stable_id in {".", ".."} or re.search(r'[<>:"/\\|?*]', stable_id)):
        raise ValueError("Für den Portraitpfad fehlt eine gültige Member-ID.")
    return project_paths(project_path).portraits / f"{stable_id}.png"


def _legacy_portrait_name(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value or "").strip())
    return re.sub(r'[<>:"/\\|?*]+', "_", text).rstrip(" .") or "character"


def migrate_legacy_portraits(project_path: Path | str,
                             members: Iterable[object]) -> PortraitMigrationSummary:
    """Move only unambiguous legacy portraits to ``portraits/<memberId>.png``."""
    paths = project_paths(project_path)
    member_list = list(members)
    by_name: dict[str, list[object]] = {}
    for member in member_list:
        key = unicodedata.normalize("NFC", str(getattr(member, "name", ""))).casefold()
        by_name.setdefault(key, []).append(member)
    migrated: list[str] = []
    ambiguous: set[str] = set()
    skipped: list[str] = []
    for member in member_list:
        member_id = str(getattr(member, "id", "") or "").strip()
        if not member_id:
            continue
        target = member_portrait_path(paths.project, member_id)
        if target.is_file():
            continue
        historical = paths.history / f"{member_id}.png"
        source: Path | None = historical if historical.is_file() else None
        key = unicodedata.normalize("NFC", str(getattr(member, "name", ""))).casefold()
        if source is None:
            if len(by_name.get(key, ())) != 1:
                if any((paths.portraits / f"{candidate}.png").is_file() for candidate in (
                        str(getattr(member, "name", "")),
                        _legacy_portrait_name(getattr(member, "name", "")))):
                    ambiguous.add(str(getattr(member, "name", "")))
                continue
            for candidate in (
                    paths.portraits / f"{getattr(member, 'name', '')}.png",
                    paths.portraits / f"{_legacy_portrait_name(getattr(member, 'name', ''))}.png"):
                if candidate.is_file():
                    source = candidate
                    break
        if source is None:
            skipped.append(member_id)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, target)
        marker = paths.history / f"{member_id}.missing"
        marker.unlink(missing_ok=True)
        migrated.append(member_id)
    try:
        if paths.history.is_dir() and not any(paths.history.iterdir()):
            paths.history.rmdir()
    except OSError:
        pass
    return PortraitMigrationSummary(
        tuple(sorted(migrated)), tuple(sorted(ambiguous, key=str.casefold)),
        tuple(sorted(skipped)),
    )


def autosave_path(project_path: Path | str | None) -> Path | None:
    return project_paths(project_path).autosave if project_path else None


def newer_autosave(project_path: Path | str) -> Path | None:
    paths = project_paths(project_path)
    try:
        if paths.autosave.is_file() and (
            not paths.project.is_file()
            or paths.autosave.stat().st_mtime_ns > paths.project.stat().st_mtime_ns
        ):
            return paths.autosave
    except OSError:
        return None
    return None


def atomic_write_bytes(path: Path | str, data: bytes) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            Path(temporary_name).unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return target


def atomic_write_json(path: Path | str, payload: Mapping | dict) -> Path:
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return atomic_write_bytes(path, data)


def backup_project_file(project_path: Path | str) -> Path | None:
    paths = project_paths(project_path)
    if not paths.project.is_file():
        return None
    paths.backups.mkdir(parents=True, exist_ok=True)
    backup = paths.backups / f"{paths.project.stem}_backup.ggc"
    temporary = backup.with_suffix(backup.suffix + ".tmp")
    shutil.copy2(paths.project, temporary)
    os.replace(temporary, backup)
    return backup


def copy_project_portraits(source_project: Path | str | None,
                           target_project: Path | str) -> int:
    if not source_project:
        return 0
    source = project_paths(source_project).portraits
    target = project_paths(target_project).portraits
    if source.resolve() == target.resolve() or not source.is_dir():
        return 0
    copied = 0
    for item in source.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        copied += 1
    return copied


def load_project_payload(project_path: Path | str) -> dict:
    path = project_paths(project_path).project
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or not isinstance(payload.get("members"), list):
        raise ValueError("Projektdatei enthält keine gültige Mitgliederliste.")
    return payload


def patch_project_member(project_path: Path | str, member_id: str,
                         updates: Mapping[str, object], *,
                         allowed_fields: Iterable[str]) -> dict:
    """Liest frisch, patcht genau einen Member per stabiler ID und speichert atomar."""
    paths = project_paths(project_path)
    payload = load_project_payload(paths.project)
    stable_id = str(member_id or "").strip()
    if not stable_id:
        raise ValueError("Für die Projektaktualisierung fehlt die Member-ID.")
    member = next((item for item in payload["members"]
                   if isinstance(item, dict) and str(item.get("id") or "") == stable_id), None)
    if member is None:
        raise ValueError(f"Member-ID {stable_id} wurde im Projekt nicht gefunden.")
    allowed = set(allowed_fields)
    for key, value in updates.items():
        if key in allowed:
            member[key] = value
    backup_project_file(paths.project)
    atomic_write_json(paths.project, payload)
    return member
