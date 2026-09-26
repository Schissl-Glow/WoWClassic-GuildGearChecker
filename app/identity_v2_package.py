"""Identity V2 adapter for the existing project.ggc/manifest/portraits ZIP format."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .GuildGearChecker import (
    APP_VERSION, PROJECT_PACKAGE_FORMAT_VERSION, ProjectPackageImportSummary,
    ProjectPackageSummary, _validate_package_archive_name,
    _validate_project_package, import_project_package,
)
from .identity_v2 import IDENTITY_FORMAT, IdentityV2Store
from .project_storage import member_portrait_path, project_paths


def create_v2_project_package(
    store: IdentityV2Store, project_path: Path | str, target: Path | str,
) -> ProjectPackageSummary:
    """Archive the current V2 store and its ID-based portraits without saving it."""
    store.validate()
    project = project_paths(project_path).project
    if not project.is_file():
        raise ValueError("Für ein V2-Projektpaket muss das Projekt gespeichert sein.")
    destination = Path(target)
    if destination.suffix.casefold() != ".zip" or destination.exists():
        raise ValueError("ZIP-Ziel ist ungültig oder existiert bereits.")
    portrait_files: list[tuple[str, bytes]] = []
    missing = 0
    for member in sorted(store.members, key=lambda item: item.memberId):
        portrait = member_portrait_path(project, member.memberId)
        if portrait.is_file():
            name = _validate_package_archive_name(
                f"portraits/{member.memberId}.png")
            portrait_files.append((name, portrait.read_bytes()))
        else:
            missing += 1
    manifest = {
        "packageFormatVersion": PROJECT_PACKAGE_FORMAT_VERSION,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "suiteVersion": APP_VERSION,
        "projectFile": "project.ggc",
        "identityFormat": IDENTITY_FORMAT,
        "portraitCount": len(portrait_files),
        "historicalPortraitCount": 0,
        "missingMarkerCount": 0,
        "missingPortraitCount": missing,
    }
    entries = ("project.ggc", "manifest.json",
               *(name for name, _content in portrait_files))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp",
            dir=destination.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project.ggc", json.dumps(
                store.to_payload(), ensure_ascii=False, indent=2) + "\n")
            archive.writestr("manifest.json", json.dumps(
                manifest, ensure_ascii=False, indent=2) + "\n")
            for name, content in portrait_files:
                archive.writestr(name, content)
        _validate_project_package(temporary, entries)
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return ProjectPackageSummary(
        destination, len(portrait_files), 0, 0, missing, (), entries)


def import_v2_project_package(
    source: Path | str, target_project: Path | str,
) -> ProjectPackageImportSummary:
    """Validate a frozen V2 archive, then reuse the existing safe importer."""
    original = Path(source)
    target = project_paths(target_project).project
    with tempfile.TemporaryDirectory(prefix="ggc-v2-package-") as directory:
        snapshot = Path(directory) / "package.zip"
        shutil.copyfile(original, snapshot)
        with zipfile.ZipFile(snapshot) as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8-sig"))
            payload = json.loads(archive.read("project.ggc").decode("utf-8-sig"))
            if (not isinstance(manifest, dict)
                    or manifest.get("identityFormat") != IDENTITY_FORMAT):
                raise ValueError("Das Paket ist kein Identity-V2-Projektpaket.")
            store = IdentityV2Store.from_payload(payload)
            member_ids = {member.memberId for member in store.members}
            for name in archive.namelist():
                if name in {"project.ggc", "manifest.json"}:
                    continue
                path = PurePosixPath(name)
                if (len(path.parts) != 2 or path.parts[0] != "portraits"
                        or path.suffix.casefold() != ".png"
                        or path.stem not in member_ids):
                    raise ValueError(f"Ungültiger V2-Portraitpfad im Paket: {name}")
        summary = import_project_package(snapshot, target)
    return replace(summary, source=original)
