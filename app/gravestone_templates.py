# -*- coding: utf-8 -*-
"""Portable, read-only-at-runtime gravestone manifest and asset inventory."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image

try:
    from app.gravestone_categories import (
        GRAVESTONE_CATEGORY_FIELD,
        GRAVESTONE_DEFAULT_OFFSET_X_FIELD,
        GRAVESTONE_DEFAULT_OFFSET_Y_FIELD,
        GRAVESTONE_DEFAULT_ZOOM_FIELD,
        GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD,
        load_gravestone_category,
        load_gravestone_portrait_preset,
        load_gravestone_text_safe_area,
        normalize_gravestone_category,
    )
except ImportError:  # Direct script execution from app/
    import importlib.util
    import sys

    _category_spec = importlib.util.spec_from_file_location(
        "guild_suite_gravestone_categories",
        Path(__file__).resolve().with_name("gravestone_categories.py"),
    )
    _category_module = importlib.util.module_from_spec(_category_spec)
    sys.modules.setdefault(_category_spec.name, _category_module)
    _category_spec.loader.exec_module(_category_module)
    GRAVESTONE_CATEGORY_FIELD = _category_module.GRAVESTONE_CATEGORY_FIELD
    GRAVESTONE_DEFAULT_OFFSET_X_FIELD = _category_module.GRAVESTONE_DEFAULT_OFFSET_X_FIELD
    GRAVESTONE_DEFAULT_OFFSET_Y_FIELD = _category_module.GRAVESTONE_DEFAULT_OFFSET_Y_FIELD
    GRAVESTONE_DEFAULT_ZOOM_FIELD = _category_module.GRAVESTONE_DEFAULT_ZOOM_FIELD
    GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD = _category_module.GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD
    load_gravestone_category = _category_module.load_gravestone_category
    load_gravestone_portrait_preset = _category_module.load_gravestone_portrait_preset
    load_gravestone_text_safe_area = _category_module.load_gravestone_text_safe_area
    normalize_gravestone_category = _category_module.normalize_gravestone_category

LOGGER = logging.getLogger(__name__)

MANIFEST_FORMAT = "GuildGearCheckerGravestoneManifest"
MANIFEST_VERSION = 1
MANIFEST_FILENAME = "gravestones_manifest.json"
SUPPORTED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
GRAVESTONE_FILENAME_PREFIX = "gravestone_"
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_TEMPLATE_ID_PATTERN = re.compile(r"grave-template-(\d+)")


@dataclass(frozen=True)
class GravestoneTemplate:
    grave_template_id: str
    filename: str
    sha256: str
    path: Path
    category: str | None = None
    state: str = "known"
    default_portrait_offset_x: float = 0.0
    default_portrait_offset_y: float = 0.0
    default_portrait_zoom: float = 1.0
    default_text_safe_area: tuple[int, int, int, int] | None = None


@dataclass(frozen=True)
class GravestoneInventory:
    templates: tuple[GravestoneTemplate, ...]
    issues: tuple[str, ...]
    unregistered: tuple[Path, ...] = ()
    missing_template_ids: tuple[str, ...] = ()
    changed_template_ids: tuple[str, ...] = ()
    duplicate_files: tuple[Path, ...] = ()
    manifest_status: str = "ok"

    def by_id(self) -> dict[str, GravestoneTemplate]:
        return {item.grave_template_id: item for item in self.templates}

    def id_for_filename(self, filename: str | None) -> str | None:
        name = str(filename or "").strip().casefold()
        matches = [
            item.grave_template_id for item in self.templates
            if item.filename.casefold() == name or item.path.name.casefold() == name
        ]
        return matches[0] if len(matches) == 1 else None


def choose_gravestone_template(template_ids: Iterable[str], member_id: str,
                               previous_template: str | None = None) -> str:
    """Use the established stable member-ID selection for an ordered inventory."""
    available = tuple(template_ids)
    if not available:
        return ""
    seed = sum((index + 1) * byte for index, byte in enumerate(
        str(member_id).encode("utf-8", errors="replace")
    ))
    choice_index = seed % len(available)
    if len(available) > 1 and available[choice_index] == previous_template:
        choice_index = (choice_index + 1) % len(available)
    return available[choice_index]


@dataclass(frozen=True)
class ManifestGenerationResult:
    manifest_path: Path
    template_count: int
    skipped_duplicates: tuple[Path, ...]
    skipped_invalid: tuple[Path, ...]


@dataclass(frozen=True)
class GravestonePromotionResult:
    productive_folder: Path
    manifest_path: Path
    accepted_originals: int
    compressed_candidates: int
    missing_compressed: tuple[str, ...]
    already_processed: tuple[str, ...]
    promoted: tuple[tuple[str, str], ...]
    skipped_invalid: tuple[str, ...]
    dry_run: bool = False


@dataclass(frozen=True)
class _ObservedImage:
    filename: str
    path: Path
    sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_paths(folder: Path) -> tuple[Path, ...]:
    try:
        return tuple(sorted(
            (
                path for path in Path(folder).iterdir()
                if path.is_file()
                and path.stem.casefold().startswith(GRAVESTONE_FILENAME_PREFIX)
                and path.suffix.casefold() in SUPPORTED_IMAGE_EXTENSIONS
                and path.name.casefold() != "gravestone_placeholder.png"
            ),
            key=lambda path: (path.name.casefold(), path.name),
        ))
    except OSError:
        return ()


def _readable_image(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.convert("RGBA").load()
        return True
    except (OSError, ValueError, SyntaxError):
        return False


def _observe_images(folder: Path) -> tuple[tuple[_ObservedImage, ...], tuple[Path, ...]]:
    observed: list[_ObservedImage] = []
    invalid: list[Path] = []
    for path in _candidate_paths(folder):
        if not _readable_image(path):
            invalid.append(path)
            continue
        try:
            observed.append(_ObservedImage(path.name, path, sha256_file(path)))
        except OSError:
            invalid.append(path)
    return tuple(observed), tuple(invalid)


def _load_manifest_entries(manifest_path: Path) -> tuple[list[dict], str, list[str]]:
    if not manifest_path.is_file():
        return [], "missing", [f"Manifest fehlt: {manifest_path.name}"]
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError) as exc:
        return [], "invalid", [f"Manifest ist ungültig: {exc}"]
    if (
        not isinstance(payload, dict)
        or payload.get("format") != MANIFEST_FORMAT
        or payload.get("formatVersion") != MANIFEST_VERSION
        or not isinstance(payload.get("templates"), list)
    ):
        return [], "invalid", ["Manifestformat ist ungültig."]

    entries: list[dict] = []
    issues: list[str] = []
    used_ids: set[str] = set()
    used_hashes: set[str] = set()
    for raw in payload["templates"]:
        if not isinstance(raw, dict):
            issues.append("Unbekannter Manifest-Eintrag wurde ignoriert.")
            continue
        template_id = str(raw.get("graveTemplateId") or "").strip()
        filename = str(raw.get("filename") or "").strip()
        digest = str(raw.get("sha256") or "").strip().casefold()
        if (
            not template_id or template_id in used_ids
            or not filename or Path(filename).name != filename
            or not _SHA256_PATTERN.fullmatch(digest)
            or digest in used_hashes
        ):
            issues.append(f"Ungültiger Manifest-Eintrag wurde ignoriert: {template_id or filename or '?'}")
            continue
        used_ids.add(template_id)
        used_hashes.add(digest)
        entry = {
            "graveTemplateId": template_id,
            "filename": filename,
            "sha256": digest,
        }
        category = normalize_gravestone_category(raw.get(GRAVESTONE_CATEGORY_FIELD))
        if category is not None:
            entry[GRAVESTONE_CATEGORY_FIELD] = category
        preset_fields = (
            (GRAVESTONE_DEFAULT_OFFSET_X_FIELD, -1.0, 1.0),
            (GRAVESTONE_DEFAULT_OFFSET_Y_FIELD, -1.0, 1.0),
            (GRAVESTONE_DEFAULT_ZOOM_FIELD, 1.0, 3.0),
        )
        for field, minimum, maximum in preset_fields:
            if field not in raw:
                continue
            try:
                value = float(raw[field])
            except (TypeError, ValueError):
                issues.append(f"Ungültige Portrait-Voreinstellung ignoriert: {template_id}/{field}")
                continue
            entry[field] = max(minimum, min(maximum, value))
        text_safe_area = raw.get(GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD)
        if isinstance(text_safe_area, (list, tuple)) and len(text_safe_area) == 4:
            try:
                values = tuple(round(float(value)) for value in text_safe_area)
            except (TypeError, ValueError):
                issues.append(f"Ungültige Text-Safe-Area ignoriert: {template_id}")
            else:
                if values[2] > values[0] and values[3] > values[1]:
                    entry[GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD] = list(values)
                else:
                    issues.append(f"Ungültige Text-Safe-Area ignoriert: {template_id}")
        entries.append(entry)
    return entries, "ok", issues


def load_gravestone_inventory(folder: Path, manifest_path: Path | None = None,
                              logger: logging.Logger | None = LOGGER) -> GravestoneInventory:
    """Compare files with the immutable reference manifest without modifying it."""
    folder = Path(folder)
    manifest_path = Path(manifest_path or folder / MANIFEST_FILENAME)
    observed, invalid = _observe_images(folder)
    entries, manifest_status, issues = _load_manifest_entries(manifest_path)
    issues.extend(f"Beschädigte Grabstein-Datei übersprungen: {path.name}" for path in invalid)

    by_hash: dict[str, list[_ObservedImage]] = {}
    by_name = {item.filename.casefold(): item for item in observed}
    for item in observed:
        by_hash.setdefault(item.sha256, []).append(item)

    templates: list[GravestoneTemplate] = []
    consumed: set[Path] = set()
    missing: list[str] = []
    changed: list[str] = []
    duplicate_files: list[Path] = []
    if manifest_status == "ok":
        for entry in entries:
            template_id = entry["graveTemplateId"]
            filename = entry["filename"]
            digest = entry["sha256"]
            candidates = by_hash.get(digest, [])
            exact = next((item for item in candidates if item.filename.casefold() == filename.casefold()), None)
            chosen = exact or next((item for item in candidates if item.path not in consumed), None)
            if chosen is None:
                named = by_name.get(filename.casefold())
                if named is not None:
                    changed.append(template_id)
                    issues.append(f"Grabstein-Datei verändert: {filename}")
                else:
                    missing.append(template_id)
                    issues.append(f"Grabsteinvorlage fehlt: {filename}")
                continue
            consumed.add(chosen.path)
            state = "known" if chosen.filename.casefold() == filename.casefold() else "renamed"
            if state == "renamed":
                issues.append(f"Grabstein-Datei umbenannt erkannt: {filename} -> {chosen.filename}")
            templates.append(GravestoneTemplate(
                template_id, filename, digest, chosen.path,
                category=entry.get(GRAVESTONE_CATEGORY_FIELD), state=state,
                default_portrait_offset_x=entry.get(GRAVESTONE_DEFAULT_OFFSET_X_FIELD, 0.0),
                default_portrait_offset_y=entry.get(GRAVESTONE_DEFAULT_OFFSET_Y_FIELD, 0.0),
                default_portrait_zoom=entry.get(GRAVESTONE_DEFAULT_ZOOM_FIELD, 1.0),
                default_text_safe_area=(
                    tuple(entry[GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD])
                    if GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD in entry else None
                ),
            ))

    unregistered: list[Path] = []
    known_hashes = {entry["sha256"] for entry in entries}
    for item in observed:
        if item.path in consumed:
            continue
        if item.sha256 in known_hashes or len(by_hash[item.sha256]) > 1:
            duplicate_files.append(item.path)
            issues.append(f"Doppelte Grabstein-Datei ignoriert: {item.filename}")
        else:
            unregistered.append(item.path)
            issues.append(f"Neue, nicht registrierte Grabstein-Datei: {item.filename}")

    if logger is not None:
        for issue in issues:
            logger.warning(issue)
    return GravestoneInventory(
        tuple(templates), tuple(issues), tuple(unregistered), tuple(missing),
        tuple(changed), tuple(duplicate_files), manifest_status,
    )


def generate_gravestone_manifest(folder: Path, manifest_path: Path | None = None,
                                 generated_at: str | None = None) -> ManifestGenerationResult:
    """Explicitly create/update the confirmed reference manifest atomically."""
    folder = Path(folder)
    manifest_path = Path(manifest_path or folder / MANIFEST_FILENAME)
    observed, invalid = _observe_images(folder)
    old_entries, old_status, _issues = _load_manifest_entries(manifest_path)
    old_by_hash = {
        entry["sha256"]: entry for entry in old_entries
    } if old_status == "ok" else {}
    used_ids = {entry["graveTemplateId"] for entry in old_entries}
    numeric_ids = [
        int(match.group(1)) for template_id in used_ids
        if (match := _TEMPLATE_ID_PATTERN.fullmatch(template_id))
    ]
    next_id = max(numeric_ids, default=0) + 1
    entries: list[dict] = []
    seen_hashes: set[str] = set()
    duplicates: list[Path] = []
    for item in observed:
        if item.sha256 in seen_hashes:
            duplicates.append(item.path)
            continue
        seen_hashes.add(item.sha256)
        previous = old_by_hash.get(item.sha256)
        if previous is not None:
            template_id = previous["graveTemplateId"]
        else:
            while f"grave-template-{next_id:04d}" in used_ids:
                next_id += 1
            template_id = f"grave-template-{next_id:04d}"
            used_ids.add(template_id)
            next_id += 1
        entry = {
            "graveTemplateId": template_id,
            "filename": item.filename,
            "sha256": item.sha256,
        }
        if previous is not None and previous.get(GRAVESTONE_CATEGORY_FIELD):
            entry[GRAVESTONE_CATEGORY_FIELD] = previous[GRAVESTONE_CATEGORY_FIELD]
        if previous is not None:
            for field in (
                GRAVESTONE_DEFAULT_OFFSET_X_FIELD,
                GRAVESTONE_DEFAULT_OFFSET_Y_FIELD,
                GRAVESTONE_DEFAULT_ZOOM_FIELD,
            ):
                if field in previous:
                    entry[field] = previous[field]
            if GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD in previous:
                entry[GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD] = previous[
                    GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD
                ]
        entries.append(entry)
    payload = {
        "format": MANIFEST_FORMAT,
        "formatVersion": MANIFEST_VERSION,
        "generatedAt": generated_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "templates": entries,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_path, manifest_path)
    return ManifestGenerationResult(manifest_path, len(entries), tuple(duplicates), invalid)


def _approved_gravestone_names(folder: Path) -> tuple[Path, ...]:
    try:
        return tuple(sorted(
            (
                path for path in Path(folder).iterdir()
                if path.is_file()
                and not path.name.startswith(".")
                and path.stem.casefold().startswith(GRAVESTONE_FILENAME_PREFIX)
                and path.suffix.casefold() == ".png"
                and path.name.casefold() != "gravestone_placeholder.png"
                and _readable_image(path)
            ),
            key=lambda path: (path.name.casefold(), path.name),
        ))
    except OSError:
        return ()


def promote_approved_gravestones(
        productive_folder: Path, approved_folder: Path | None = None,
        compressed_folder: Path | None = None, manifest_path: Path | None = None,
        dry_run: bool = False) -> GravestonePromotionResult:
    """Übernimmt freigegebene komprimierte Grabsteine sicher und idempotent."""
    productive_folder = Path(productive_folder)
    approved_folder = Path(approved_folder or productive_folder / "_approved_new")
    compressed_folder = Path(compressed_folder or approved_folder / "compressed")
    manifest_path = Path(manifest_path or productive_folder / MANIFEST_FILENAME)

    approved = _approved_gravestone_names(approved_folder)
    approved_by_name = {path.name.casefold(): path for path in approved}
    compressed: list[Path] = []
    invalid: list[str] = []
    try:
        compressed_paths = sorted(compressed_folder.iterdir(), key=lambda p: (p.name.casefold(), p.name))
    except OSError:
        compressed_paths = []
    for path in compressed_paths:
        if (not path.is_file() or path.name.startswith(".")
                or path.suffix.casefold() != ".png"
                or not path.stem.casefold().startswith(GRAVESTONE_FILENAME_PREFIX)
                or path.name.casefold() == "gravestone_placeholder.png"):
            continue
        if path.name.casefold() not in approved_by_name:
            invalid.append(f"{path.name}: freigegebenes Original fehlt")
            continue
        if not _readable_image(path):
            invalid.append(f"{path.name}: komprimierte Datei ist ungültig")
            continue
        compressed.append(path)

    entries, manifest_status, issues = _load_manifest_entries(manifest_path)
    if manifest_status == "invalid" or issues:
        raise ValueError("Produktives Manifest ist ungültig; Übernahme abgebrochen.")
    if manifest_status == "missing":
        entries = []
    productive_folder.mkdir(parents=True, exist_ok=True)
    inventory = load_gravestone_inventory(productive_folder, manifest_path, logger=None)
    if manifest_status == "ok" and (inventory.missing_template_ids or inventory.changed_template_ids):
        raise ValueError("Produktive Grabsteinbasis ist nicht konsistent; Übernahme abgebrochen.")

    existing_hashes = {entry["sha256"] for entry in entries}
    existing_numbers = [
        int(match.group(1)) for path in productive_folder.iterdir()
        if path.is_file() and _readable_image(path)
        and (match := re.fullmatch(r"gravestone_(\d+)\.png", path.name, re.IGNORECASE))
    ]
    next_number = max(existing_numbers, default=0) + 1
    used_ids = {entry["graveTemplateId"] for entry in entries}
    numeric_ids = [
        int(match.group(1)) for value in used_ids
        if (match := _TEMPLATE_ID_PATTERN.fullmatch(value))
    ]
    next_id = max(numeric_ids, default=0) + 1
    planned: list[tuple[Path, str, str, str, str, tuple[float, float, float] | None, tuple[int, int, int, int] | None]] = []
    seen_hashes = set(existing_hashes)
    already_processed: list[str] = []
    compressed_candidates = len(compressed)
    for source in compressed:
        digest = sha256_file(source)
        if digest in seen_hashes:
            already_processed.append(source.name)
            continue
        if digest in {item[3] for item in planned}:
            invalid.append(f"{source.name}: doppelter Inhalt in dieser Freigabe")
            continue
        category = load_gravestone_category(approved_by_name[source.name.casefold()])
        if category is None:
            invalid.append(f"{source.name}: Grabstein-Kategorie fehlt oder ist ungültig")
            continue
        target_name = f"gravestone_{next_number:03d}.png"
        target = productive_folder / target_name
        if target.exists():
            raise FileExistsError(f"Zieldatei existiert bereits: {target_name}")
        template_id = f"grave-template-{next_id:04d}"
        approved_source = approved_by_name[source.name.casefold()]
        preset = load_gravestone_portrait_preset(approved_source)
        with Image.open(approved_source) as approved_image:
            text_safe_area = load_gravestone_text_safe_area(approved_source, approved_image.size)
        planned.append((source, target_name, template_id, digest, category, preset, text_safe_area))
        seen_hashes.add(digest)
        next_number += 1
        next_id += 1

    if invalid:
        raise ValueError("Freigabeprüfung fehlgeschlagen: " + "; ".join(invalid))

    promoted = tuple(
        (source.name, target_name)
        for source, target_name, _template_id, _digest, _category, _preset, _text_safe_area in planned
    )
    if not dry_run and planned:
        temporary_targets: list[tuple[Path, Path]] = []
        committed_targets: list[Path] = []
        manifest_temp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
        manifest_rollback = manifest_path.with_suffix(manifest_path.suffix + ".rollback.tmp")
        previous_manifest = manifest_path.read_bytes() if manifest_path.is_file() else None
        manifest_replaced = False
        try:
            for source, target_name, _template_id, _digest, _category, _preset, _text_safe_area in planned:
                target = productive_folder / target_name
                temporary = target.with_suffix(target.suffix + ".tmp")
                shutil.copyfile(source, temporary)
                temporary_targets.append((temporary, target))
            output_entries = list(entries)
            for _source, target_name, template_id, digest, category, preset, text_safe_area in planned:
                entry = {
                    "graveTemplateId": template_id,
                    "filename": target_name,
                    "sha256": digest,
                    GRAVESTONE_CATEGORY_FIELD: category,
                }
                if preset is not None:
                    entry[GRAVESTONE_DEFAULT_OFFSET_X_FIELD] = preset[0]
                    entry[GRAVESTONE_DEFAULT_OFFSET_Y_FIELD] = preset[1]
                    entry[GRAVESTONE_DEFAULT_ZOOM_FIELD] = preset[2]
                if text_safe_area is not None:
                    entry[GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD] = list(text_safe_area)
                output_entries.append(entry)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_temp.write_text(json.dumps({
                "format": MANIFEST_FORMAT,
                "formatVersion": MANIFEST_VERSION,
                "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
                "templates": output_entries,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            for temporary, target in temporary_targets:
                os.replace(temporary, target)
                committed_targets.append(target)
            os.replace(manifest_temp, manifest_path)
            manifest_replaced = True
            post_inventory = load_gravestone_inventory(productive_folder, manifest_path, logger=None)
            if (post_inventory.manifest_status != "ok"
                    or post_inventory.missing_template_ids
                    or post_inventory.changed_template_ids):
                raise ValueError("Produktives Manifest konnte nach der Übernahme nicht validiert werden.")
        except Exception:
            for target in committed_targets:
                target.unlink(missing_ok=True)
            if manifest_replaced:
                if previous_manifest is None:
                    manifest_path.unlink(missing_ok=True)
                else:
                    manifest_rollback.write_bytes(previous_manifest)
                    os.replace(manifest_rollback, manifest_path)
            raise
        finally:
            for temporary, _target in temporary_targets:
                temporary.unlink(missing_ok=True)
            manifest_temp.unlink(missing_ok=True)
            manifest_rollback.unlink(missing_ok=True)

    return GravestonePromotionResult(
        productive_folder, manifest_path, len(approved), compressed_candidates,
        tuple(sorted(set(approved_by_name) - {path.name.casefold() for path in compressed})),
        tuple(already_processed), promoted, tuple(invalid), dry_run,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Grabstein-Referenzmanifest verwalten")
    parser.add_argument("--generate", action="store_true", help="bestätigten Bestand registrieren")
    parser.add_argument("--promote", action="store_true", help="freigegebene komprimierte Grabsteine übernehmen")
    parser.add_argument("--approved", type=Path)
    parser.add_argument("--compressed", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.promote:
        result = promote_approved_gravestones(
            args.folder, args.approved, args.compressed, args.manifest, args.dry_run,
        )
        print(f"Produktivordner: {result.productive_folder}")
        print(f"Akzeptierte Originale: {result.accepted_originals}")
        print(f"Komprimierte Kandidaten: {result.compressed_candidates}")
        print(f"Bereits verarbeitet: {len(result.already_processed)}")
        print(f"Übernommen: {len(result.promoted)}")
        for source, target in result.promoted:
            print(f"  {source} -> {target}")
        print(f"Dry-Run: {'ja' if result.dry_run else 'nein'}")
        return 0
    if not args.generate:
        parser.error("--generate oder --promote ist erforderlich")
    result = generate_gravestone_manifest(args.folder, args.manifest)
    print(f"Manifest: {result.manifest_path}")
    print(f"Registrierte Vorlagen: {result.template_count}")
    print(f"Übersprungene Duplikate: {len(result.skipped_duplicates)}")
    print(f"Übersprungene beschädigte Dateien: {len(result.skipped_invalid)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
