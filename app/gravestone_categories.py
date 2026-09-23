"""Shared gravestone category metadata for review, editing and promotion."""

from __future__ import annotations

import json
import os
from pathlib import Path


GRAVESTONE_CATEGORIES = (
    "Menschen",
    "Zwerge",
    "Elfen",
    "Gnome",
    "Zauberer",
    "Spezial",
)
GRAVESTONE_CATEGORY_LABEL = "Grabstein-Kategorie"
GRAVESTONE_CATEGORY_FIELD = "category"
GRAVESTONE_DEFAULT_OFFSET_X_FIELD = "defaultPortraitOffsetX"
GRAVESTONE_DEFAULT_OFFSET_Y_FIELD = "defaultPortraitOffsetY"
GRAVESTONE_DEFAULT_ZOOM_FIELD = "defaultPortraitZoom"
GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD = "defaultTextSafeArea"
GRAVESTONE_METADATA_FORMAT = "GuildGearCheckerGravestoneMetadata"
GRAVESTONE_METADATA_VERSION = 1


def normalize_gravestone_category(value: object) -> str | None:
    text = str(value or "").strip()
    return text if text in GRAVESTONE_CATEGORIES else None


def require_gravestone_category(value: object) -> str:
    category = normalize_gravestone_category(value)
    if category is None:
        raise ValueError(f"{GRAVESTONE_CATEGORY_LABEL} muss gewählt sein.")
    return category


def gravestone_metadata_path(image_path: Path) -> Path:
    image_path = Path(image_path)
    return image_path.with_name(image_path.name + ".metadata.json")


def _load_metadata(image_path: Path) -> dict:
    metadata_path = gravestone_metadata_path(image_path)
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    except (OSError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_metadata(image_path: Path, payload: dict) -> Path:
    metadata_path = gravestone_metadata_path(image_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["format"] = GRAVESTONE_METADATA_FORMAT
    payload["formatVersion"] = GRAVESTONE_METADATA_VERSION
    temporary = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, metadata_path)
    finally:
        temporary.unlink(missing_ok=True)
    return metadata_path


def _bounded_float(value: object, minimum: float, maximum: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def load_gravestone_category(image_path: Path) -> str | None:
    payload = _load_metadata(image_path)
    return normalize_gravestone_category(payload.get(GRAVESTONE_CATEGORY_FIELD))


def save_gravestone_category(image_path: Path, category: object) -> Path:
    category = require_gravestone_category(category)
    payload = _load_metadata(image_path)
    payload[GRAVESTONE_CATEGORY_FIELD] = category
    return _save_metadata(image_path, payload)


def load_gravestone_portrait_preset(image_path: Path) -> tuple[float, float, float] | None:
    payload = _load_metadata(image_path)
    fields = (
        GRAVESTONE_DEFAULT_OFFSET_X_FIELD,
        GRAVESTONE_DEFAULT_OFFSET_Y_FIELD,
        GRAVESTONE_DEFAULT_ZOOM_FIELD,
    )
    if not all(field in payload for field in fields):
        return None
    return (
        _bounded_float(payload[fields[0]], -1.0, 1.0, 0.0),
        _bounded_float(payload[fields[1]], -1.0, 1.0, 0.0),
        _bounded_float(payload[fields[2]], 1.0, 3.0, 1.0),
    )


def save_gravestone_portrait_preset(
    image_path: Path, offset_x: object, offset_y: object, zoom: object,
) -> Path:
    payload = _load_metadata(image_path)
    payload[GRAVESTONE_DEFAULT_OFFSET_X_FIELD] = _bounded_float(offset_x, -1.0, 1.0, 0.0)
    payload[GRAVESTONE_DEFAULT_OFFSET_Y_FIELD] = _bounded_float(offset_y, -1.0, 1.0, 0.0)
    payload[GRAVESTONE_DEFAULT_ZOOM_FIELD] = _bounded_float(zoom, 1.0, 3.0, 1.0)
    return _save_metadata(image_path, payload)


def normalize_gravestone_text_safe_area(
    value: object, image_size: tuple[int, int], minimum_size: int = 24,
) -> tuple[int, int, int, int] | None:
    """Validate one template-local text rectangle in source-image coordinates."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x1, y1, x2, y2 = (round(float(item)) for item in value)
        width, height = (int(image_size[0]), int(image_size[1]))
    except (TypeError, ValueError, IndexError):
        return None
    if width <= 0 or height <= 0:
        return None
    x1 = max(0, min(width - 1, x1))
    y1 = max(0, min(height - 1, y1))
    x2 = max(x1 + minimum_size, min(width, x2))
    y2 = max(y1 + minimum_size, min(height, y2))
    if x2 - x1 < minimum_size or y2 - y1 < minimum_size:
        return None
    return (x1, y1, x2, y2)


def load_gravestone_text_safe_area(
    image_path: Path, image_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    return normalize_gravestone_text_safe_area(
        _load_metadata(image_path).get(GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD), image_size,
    )


def save_gravestone_text_safe_area(
    image_path: Path, value: object, image_size: tuple[int, int],
) -> Path:
    safe_area = normalize_gravestone_text_safe_area(value, image_size)
    if safe_area is None:
        raise ValueError("Text-Safe-Area ist ungültig.")
    payload = _load_metadata(image_path)
    payload[GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD] = list(safe_area)
    return _save_metadata(image_path, payload)


def move_gravestone_category(source_image: Path, target_image: Path) -> None:
    source = gravestone_metadata_path(source_image)
    if not source.is_file():
        return
    target = gravestone_metadata_path(target_image)
    if target.exists():
        raise FileExistsError(f"Grabstein-Metadaten existieren bereits: {target}")
    os.replace(source, target)


def delete_gravestone_category(image_path: Path) -> None:
    gravestone_metadata_path(image_path).unlink(missing_ok=True)


def update_manifest_gravestone_category(
    manifest_path: Path,
    grave_template_id: str,
    category: object,
) -> None:
    """Update one existing template category without rewriting other metadata."""
    category = require_gravestone_category(category)
    manifest_path = Path(manifest_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    templates = payload.get("templates") if isinstance(payload, dict) else None
    if not isinstance(templates, list):
        raise ValueError("Produktives Grabstein-Manifest ist ungültig.")
    matched = False
    for entry in templates:
        if isinstance(entry, dict) and entry.get("graveTemplateId") == grave_template_id:
            entry[GRAVESTONE_CATEGORY_FIELD] = category
            matched = True
            break
    if not matched:
        raise KeyError(f"Unbekannte Grabstein-ID: {grave_template_id}")
    temporary = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, manifest_path)
    finally:
        temporary.unlink(missing_ok=True)
