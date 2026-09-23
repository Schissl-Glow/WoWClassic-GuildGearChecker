# -*- coding: utf-8 -*-
"""
Guild Portrait Grabber v0.2.0
---------------------------
Separate helper tool for creating character portraits from ClassicWoWArmory.
Designed for Windows + Miniforge/Python 3.12.

Key design goals:
- v0.2.0 Cleanup-UI with Portraits / Ausschnitt / Einstellungen / Grabstein Review tabs.
- "Alle fehlenden" creates only missing portraits.
- No Blizzard or Warcraft Logs API key required.
- Uses a real browser session (Microsoft Edge preferred) via Playwright.
- Supports visible/manual positioning of the 3D model before capture.
- Tries to find the 3D viewer/canvas automatically.
- One-time crop calibration can be reused for all portraits.
- Imports names from TXT, Warcraft Logs CSV, and Guild Gear Checker .ggc files.
- Patches active .ggc project members by stable ID for confirmed project changes.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
from datetime import datetime, timezone
import html
import importlib.util
import io
import json
import math
import os
import queue
import re
import shutil
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import webbrowser
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Iterable, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from app.project_storage import (
        member_portrait_path as stored_member_portrait_path,
        migrate_legacy_portraits,
        portrait_root as project_portrait_root,
    )
except ImportError:
    _storage_spec = importlib.util.spec_from_file_location(
        "guild_suite_project_storage", Path(__file__).resolve().with_name("project_storage.py")
    )
    _storage_module = importlib.util.module_from_spec(_storage_spec)
    sys.modules.setdefault(_storage_spec.name, _storage_module)
    _storage_spec.loader.exec_module(_storage_module)
    project_portrait_root = _storage_module.portrait_root
    stored_member_portrait_path = _storage_module.member_portrait_path
    migrate_legacy_portraits = _storage_module.migrate_legacy_portraits

try:
    from app.project_handoff import (
        apply_actions_to_project, make_action, queue_action, read_receipt,
    )
except ImportError:
    _handoff_spec = importlib.util.spec_from_file_location(
        "guild_suite_project_handoff", Path(__file__).resolve().with_name("project_handoff.py")
    )
    _handoff_module = importlib.util.module_from_spec(_handoff_spec)
    sys.modules.setdefault(_handoff_spec.name, _handoff_module)
    _handoff_spec.loader.exec_module(_handoff_module)
    apply_actions_to_project = _handoff_module.apply_actions_to_project
    make_action = _handoff_module.make_action
    queue_action = _handoff_module.queue_action
    read_receipt = _handoff_module.read_receipt

try:
    from app.i18n import (
        get_language, language_display_values, language_from_display,
        gravestone_category_display, gravestone_category_display_values, gravestone_category_from_display,
        race_display, set_language, tr,
    )
    from app.font_utils import load_lifecraft_font
except ImportError:
    _i18n_spec = importlib.util.spec_from_file_location(
        "guild_suite_i18n", Path(__file__).resolve().with_name("i18n.py")
    )
    _i18n_module = importlib.util.module_from_spec(_i18n_spec)
    sys.modules.setdefault(_i18n_spec.name, _i18n_module)
    _i18n_spec.loader.exec_module(_i18n_module)
    get_language = _i18n_module.get_language
    language_display_values = _i18n_module.language_display_values
    language_from_display = _i18n_module.language_from_display
    gravestone_category_display = _i18n_module.gravestone_category_display
    gravestone_category_display_values = _i18n_module.gravestone_category_display_values
    gravestone_category_from_display = _i18n_module.gravestone_category_from_display
    race_display = _i18n_module.race_display
    set_language = _i18n_module.set_language
    tr = _i18n_module.tr
    _font_spec = importlib.util.spec_from_file_location(
        "guild_suite_font_utils", Path(__file__).resolve().with_name("font_utils.py")
    )
    _font_module = importlib.util.module_from_spec(_font_spec)
    sys.modules.setdefault(_font_spec.name, _font_module)
    _font_spec.loader.exec_module(_font_module)
    load_lifecraft_font = _font_module.load_lifecraft_font

try:
    from PIL import Image, ImageTk, ImageGrab, ImageOps, ImageStat, ImageDraw
except Exception:  # pragma: no cover - handled by startup checks
    Image = None
    ImageTk = None
    ImageGrab = None
    ImageOps = None
    ImageStat = None
    ImageDraw = None

try:
    from app.window_geometry import (
        dynamic_minimum, primary_work_area, read_suite_settings,
        resolve_geometry, update_suite_settings, work_area_for_geometry,
    )
except ImportError:
    _geometry_spec = importlib.util.spec_from_file_location(
        "guild_suite_window_geometry", Path(__file__).resolve().with_name("window_geometry.py")
    )
    _geometry_module = importlib.util.module_from_spec(_geometry_spec)
    sys.modules.setdefault(_geometry_spec.name, _geometry_module)
    _geometry_spec.loader.exec_module(_geometry_module)
    dynamic_minimum = _geometry_module.dynamic_minimum
    primary_work_area = _geometry_module.primary_work_area
    read_suite_settings = _geometry_module.read_suite_settings
    resolve_geometry = _geometry_module.resolve_geometry
    update_suite_settings = _geometry_module.update_suite_settings
    work_area_for_geometry = _geometry_module.work_area_for_geometry

# BEGIN LEGACY_GUILD_ROSTER_FETCH_IMPORTS
# Disabled in v0.8.2. This block exists only for the old Armory guild-roster
# fetch/snapshot workflow and is intentionally kept together for later removal.
try:
    from app.guild_roster_sync import (
        build_snapshot as build_guild_snapshot, fetch_guild_roster, merge_snapshot_member_data,
        write_snapshot_atomic,
    )
except ImportError:
    _guild_sync_spec = importlib.util.spec_from_file_location(
        "guild_suite_roster_sync", Path(__file__).resolve().with_name("guild_roster_sync.py")
    )
    _guild_sync_module = importlib.util.module_from_spec(_guild_sync_spec)
    sys.modules.setdefault(_guild_sync_spec.name, _guild_sync_module)
    _guild_sync_spec.loader.exec_module(_guild_sync_module)
    build_guild_snapshot = _guild_sync_module.build_snapshot
    fetch_guild_roster = _guild_sync_module.fetch_guild_roster
    merge_snapshot_member_data = _guild_sync_module.merge_snapshot_member_data
    write_snapshot_atomic = _guild_sync_module.write_snapshot_atomic
# END LEGACY_GUILD_ROSTER_FETCH_IMPORTS

try:
    from app.character_cache import character_cache_path, update_character_cache
except ImportError:
    _character_cache_spec = importlib.util.spec_from_file_location(
        "guild_suite_character_cache", Path(__file__).resolve().with_name("character_cache.py")
    )
    _character_cache_module = importlib.util.module_from_spec(_character_cache_spec)
    sys.modules.setdefault(_character_cache_spec.name, _character_cache_module)
    _character_cache_spec.loader.exec_module(_character_cache_module)
    character_cache_path = _character_cache_module.character_cache_path
    update_character_cache = _character_cache_module.update_character_cache

try:
    from app.gravestone_categories import (
        GRAVESTONE_CATEGORIES,
        GRAVESTONE_CATEGORY_LABEL,
        normalize_gravestone_category,
        update_manifest_gravestone_category,
    )
except ImportError:
    _grave_category_spec = importlib.util.spec_from_file_location(
        "guild_suite_gravestone_categories",
        Path(__file__).resolve().with_name("gravestone_categories.py"),
    )
    _grave_category_module = importlib.util.module_from_spec(_grave_category_spec)
    sys.modules.setdefault(_grave_category_spec.name, _grave_category_module)
    _grave_category_spec.loader.exec_module(_grave_category_module)
    GRAVESTONE_CATEGORIES = _grave_category_module.GRAVESTONE_CATEGORIES
    GRAVESTONE_CATEGORY_LABEL = _grave_category_module.GRAVESTONE_CATEGORY_LABEL
    normalize_gravestone_category = _grave_category_module.normalize_gravestone_category
    update_manifest_gravestone_category = _grave_category_module.update_manifest_gravestone_category

APP_NAME = "Guild Portrait Grabber"
APP_VERSION = "0.11.3-test3"
DEFAULT_REGION = "EU"
DEFAULT_REALM = "stitches"
DEFAULT_GAME_VERSION = "classic1x"
PORTRAIT_SOURCE_ARMORY = "armory"
PORTRAIT_SOURCE_IDS = (PORTRAIT_SOURCE_ARMORY,)
PORTRAIT_SOURCE_CONFIG_KEYS = (
    "region",
    "realm",
    "game_version",
    "browser_channel",
    "wait_after_load",
    "capture_mode",
    "standard_wait_after_open",
    "screen_region",
    "crop",
)
PORTRAIT_WIDTH = 384
PORTRAIT_HEIGHT = 672
BANNER_HEADER_HEIGHT = 230
BANNER_FOCAL_POINT = (0.33, 0.46)
CLASS_NAMES = ("Druid", "Hunter", "Mage", "Paladin", "Priest", "Rogue", "Shaman", "Warlock", "Warrior")
RACE_NAMES = ("Human", "Dwarf", "Night Elf", "Gnome", "Orc", "Undead", "Tauren", "Troll")
RACE_ALIASES = {
    "Human": ("Human", "Mensch"),
    "Dwarf": ("Dwarf", "Zwerg"),
    "Night Elf": ("Night Elf", "Nachtelf", "Nachtelfe"),
    "Gnome": ("Gnome", "Gnom"),
    "Orc": ("Orc", "Ork"),
    "Undead": ("Undead", "Untoter", "Untote"),
    "Tauren": ("Tauren",),
    "Troll": ("Troll",),
}
CLASS_ALIASES = {
    "Druid": ("Druid", "Druide"),
    "Hunter": ("Hunter", "Jäger", "Jaeger"),
    "Mage": ("Mage", "Magier"),
    "Paladin": ("Paladin",),
    "Priest": ("Priest", "Priester"),
    "Rogue": ("Rogue", "Schurke"),
    "Shaman": ("Shaman", "Schamane"),
    "Warlock": ("Warlock", "Hexenmeister"),
    "Warrior": ("Warrior", "Krieger"),
}
ARMORY_RESULT_FORMAT = "GuildGearCheckerArmoryData"
ARMORY_RESULT_VERSION = 1
CHARACTER_READY_TIMEOUT_SECONDS = 20.0

# BEGIN LEGACY_GUILD_ROSTER_FETCH_CONFIG
# Keep False. The Armory guild list contains low-level characters and is not used
# for the current level-60-only roster workflow.
LEGACY_GUILD_ROSTER_FETCH_ENABLED = False
# END LEGACY_GUILD_ROSTER_FETCH_CONFIG

SEED_NAMES = [
    "Aba", "Albinoanton", "Burgûs", "Bífi", "Dirksson", "Gigagenossin",
    "Gullinborsti", "Janos", "Kolben", "Opine", "Schlübbeer", "Schneeflocke",
    "Soregdrei", "Sysem", "Tiberior", "Varnika", "Venog", "Wariwariluke",
    "Zwirrlin", "Ánníe",
]

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

GRAVESTONE_CATEGORY_FILTER_ALL = "__all__"
GRAVESTONE_CATEGORY_FILTER_UNCATEGORIZED = "__uncategorized__"

def filter_gravestone_template_ids(templates, template_ids, current_template_id: str, category_filter: str) -> list[str]:
    """Filter selectable gravestones by category while always keeping the current stone reachable."""
    result: list[str] = []
    canonical_filter = normalize_gravestone_category(category_filter)
    for template_id in template_ids:
        template = templates.get(template_id)
        if template is None:
            continue
        category = normalize_gravestone_category(getattr(template, "category", None))
        if (
            category_filter == GRAVESTONE_CATEGORY_FILTER_ALL
            or (category_filter == GRAVESTONE_CATEGORY_FILTER_UNCATEGORIZED and category is None)
            or (canonical_filter is not None and category == canonical_filter)
        ):
            result.append(template_id)
    if current_template_id and current_template_id in templates and current_template_id in template_ids:
        if current_template_id not in result:
            result.insert(0, current_template_id)
    return result


def suite_root_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    here = Path(__file__).resolve().parent
    return here.parent if here.name.casefold() == "app" else here


def legacy_app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "GuildPortraitGrabber"
    return Path.home() / ".guild_portrait_grabber"


def app_data_dir() -> Path:
    return suite_root_dir() / "data" / "temp" / "grabber"


def default_output_dir(project_path: Path | str | None = None) -> Path:
    output = project_portrait_root(project_path)
    if output is None:
        raise RuntimeError(tr("grabber.project_required"))
    return output


def grabber_banner_path() -> Path:
    return suite_root_dir() / "assets" / "grabber_banner.png"


def normal_portrait_path(member_id: str, project_path: Path | str) -> Path:
    return stored_member_portrait_path(project_path, member_id)


def portrait_candidates_for_name(name: str, project_path: Path | str | None):
    """Yield the legacy active-portrait candidates without any UI dependency."""
    output = project_portrait_root(project_path)
    if output is None:
        return
    bases = dedupe_names([name, safe_filename(name)])
    seen = set()
    for base in bases:
        for extension in (".png", ".jpg", ".jpeg", ".webp"):
            candidate = output / f"{base}{extension}"
            key = str(candidate).casefold()
            if key not in seen:
                seen.add(key)
                yield candidate


def existing_portrait_for_member(member_id: str,
                                 project_path: Path | str | None) -> Optional[Path]:
    if project_path is None or not str(member_id or "").strip():
        return None
    path = normal_portrait_path(member_id, project_path)
    return path if path.is_file() else None


def graveyard_history_paths(member_id: str | None, character_name: str | None,
                            project_path: Path | str | None) -> tuple[Path, Path]:
    """Compatibility helper returning the unified member-ID path."""
    if project_path is None or not member_id:
        raise ValueError("Für Friedhofsportraits muss ein Projekt geöffnet sein.")
    portrait = normal_portrait_path(str(member_id), project_path)
    return portrait, portrait.with_suffix(".missing")


def graveyard_portrait_for_member(member_id: str | None, character_name: str | None,
                                  project_path: Path | str | None) -> Optional[Path]:
    """Resolve a read-only graveyard portrait with the v0.9.1 history priority."""
    if project_path is None or not member_id:
        return None
    return existing_portrait_for_member(str(member_id), project_path)


def graveyard_portrait_placeholder_path() -> Path:
    """Return the existing visual-only portrait placeholder asset."""
    return suite_root_dir() / "assets" / "graveyard" / "portrait_placeholder.png"


def graveyard_preview_portrait_for_member(member_id: str | None, character_name: str | None,
                                          project_path: Path | str | None) -> Optional[Path]:
    """Resolve a persisted graveyard portrait or the visual-only placeholder."""
    portrait = graveyard_portrait_for_member(member_id, character_name, project_path)
    if portrait is not None:
        return portrait
    placeholder = graveyard_portrait_placeholder_path()
    return placeholder if placeholder.is_file() else None


@dataclass(frozen=True)
class GravestoneEditorTemplatePreset:
    """UI-neutral template identity and its initial portrait geometry."""

    template_id: str
    filename: str
    category: str | None
    portrait_offset_x: float = 0.0
    portrait_offset_y: float = 0.0
    portrait_zoom: float = 1.0


@dataclass(frozen=True)
class GravestoneEditorValues:
    """One complete saved or draft value set used by the unified editor."""

    template_id: str
    template_filename: str
    category: str | None
    portrait_offset_x: float = 0.0
    portrait_offset_y: float = 0.0
    portrait_zoom: float = 1.0
    text_offset_x: float = 0.0
    text_offset_y: float = 0.0
    text_scale: float = 1.0
    death_date: str = ""


@dataclass(frozen=True)
class GravestoneEditorState:
    """Separate saved snapshot and volatile editor draft without UI dependencies."""

    member_id: str
    character_name: str
    portrait_path: Path | None
    templates: tuple[GravestoneEditorTemplatePreset, ...]
    saved: GravestoneEditorValues
    draft: GravestoneEditorValues

    def _template(self, template_id: str) -> GravestoneEditorTemplatePreset:
        template = next((
            item for item in self.templates if item.template_id == str(template_id)
        ), None)
        if template is None:
            raise ValueError(f"Unbekannter Grabstein: {template_id}")
        return template

    def _initial_values_for(self, template_id: str) -> GravestoneEditorValues:
        template = self._template(template_id)
        if template.template_id == self.saved.template_id:
            return self.saved
        return GravestoneEditorValues(
            template_id=template.template_id,
            template_filename=template.filename,
            category=template.category,
            portrait_offset_x=template.portrait_offset_x,
            portrait_offset_y=template.portrait_offset_y,
            portrait_zoom=template.portrait_zoom,
            death_date=self.saved.death_date,
        )

    def select_template(self, template_id: str) -> "GravestoneEditorState":
        """Switch only the draft and start the target template from its own values."""
        return replace(self, draft=self._initial_values_for(template_id))

    def reset(self) -> "GravestoneEditorState":
        """Reset the active draft template without switching back to the saved one."""
        return replace(self, draft=self._initial_values_for(self.draft.template_id))

    def member_for_render(self, member):
        """Materialize a temporary Member-like dataclass for the shared renderer."""
        if str(getattr(member, "id", "")) != self.member_id:
            raise ValueError("Der Editorzustand gehört zu einem anderen Charakter.")
        return replace(
            member,
            graveTemplateId=self.draft.template_id,
            gravestoneTemplate=self.draft.template_filename,
            portraitOffsetX=self.draft.portrait_offset_x,
            portraitOffsetY=self.draft.portrait_offset_y,
            portraitZoom=self.draft.portrait_zoom,
            textOffsetX=self.draft.text_offset_x,
            textOffsetY=self.draft.text_offset_y,
            textScale=self.draft.text_scale,
            deathDate=self.draft.death_date,
        )


def build_gravestone_editor_state(member, templates: Iterable[object],
                                   portrait_path: Path | str | None,
                                   initial_template_id: str | None = None,
                                   saved_template_id: str | None = None,
                                   ) -> GravestoneEditorState:
    """Create a draft from persisted member values and verified template presets."""
    presets = tuple(
        GravestoneEditorTemplatePreset(
            template_id=str(template.grave_template_id),
            filename=str(template.filename),
            category=getattr(template, "category", None),
            portrait_offset_x=float(getattr(template, "default_portrait_offset_x", 0.0)),
            portrait_offset_y=float(getattr(template, "default_portrait_offset_y", 0.0)),
            portrait_zoom=float(getattr(template, "default_portrait_zoom", 1.0)),
        )
        for template in templates
    )
    if not presets:
        raise ValueError("Kein verfügbarer Grabstein.")
    by_id = {item.template_id: item for item in presets}
    persisted_id = str(saved_template_id or getattr(member, "graveTemplateId", "") or "")
    persisted_template = by_id.get(persisted_id)
    saved = GravestoneEditorValues(
        template_id=persisted_id,
        template_filename=(
            persisted_template.filename if persisted_template is not None
            else str(getattr(member, "gravestoneTemplate", "") or "")
        ),
        category=persisted_template.category if persisted_template is not None else None,
        portrait_offset_x=float(getattr(member, "portraitOffsetX", 0.0)),
        portrait_offset_y=float(getattr(member, "portraitOffsetY", 0.0)),
        portrait_zoom=float(getattr(member, "portraitZoom", 1.0)),
        text_offset_x=float(getattr(member, "textOffsetX", 0.0)),
        text_offset_y=float(getattr(member, "textOffsetY", 0.0)),
        text_scale=float(getattr(member, "textScale", 1.0)),
        death_date=str(getattr(member, "deathDate", "") or ""),
    )
    selected_id = str(initial_template_id or persisted_id or presets[0].template_id)
    if selected_id not in by_id:
        selected_id = persisted_id if persisted_id in by_id else presets[0].template_id
    state = GravestoneEditorState(
        member_id=str(getattr(member, "id", "")),
        character_name=str(getattr(member, "name", "")),
        portrait_path=Path(portrait_path) if portrait_path is not None else None,
        templates=presets,
        saved=saved,
        draft=saved,
    )
    return state.select_template(selected_id) if selected_id != persisted_id else state


@dataclass(frozen=True)
class PortraitEditorState:
    """UI-neutraler Ausgangszustand einer Portraiteditor-Sitzung."""

    source_path: Path
    source_size: tuple[int, int]
    zoom: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    initial_zoom: float = 1.0
    initial_offset_x: float = 0.0
    initial_offset_y: float = 0.0

    def reset(self) -> "PortraitEditorState":
        return portrait_editor_transform(
            PortraitEditorState(
                source_path=self.source_path,
                source_size=self.source_size,
                zoom=self.initial_zoom,
                offset_x=self.initial_offset_x,
                offset_y=self.initial_offset_y,
                initial_zoom=self.initial_zoom,
                initial_offset_x=self.initial_offset_x,
                initial_offset_y=self.initial_offset_y,
            )
        )


PORTRAIT_EDITOR_PREVIEW_SIZE = (320, 560)
PORTRAIT_EDITOR_ZOOM_RANGE = (1.0, 4.0)
PORTRAIT_EDITOR_ZOOM_STEP = 0.12


def portrait_editor_geometry(state: PortraitEditorState,
                             viewport_size: tuple[int, int] = PORTRAIT_EDITOR_PREVIEW_SIZE,
                             ) -> tuple[float, float, float, float, float]:
    """Return scale, rendered size and legal offsets in reference coordinates."""
    source_width, source_height = state.source_size
    viewport_width, viewport_height = viewport_size
    if min(source_width, source_height, viewport_width, viewport_height) <= 0:
        raise ValueError("Portrait- und Vorschaugröße müssen positiv sein.")
    base_scale = max(viewport_width / source_width, viewport_height / source_height)
    scale = base_scale * state.zoom
    rendered_width = source_width * scale
    rendered_height = source_height * scale
    max_offset_x = max(0.0, (rendered_width - viewport_width) / 2.0)
    max_offset_y = max(0.0, (rendered_height - viewport_height) / 2.0)
    return scale, rendered_width, rendered_height, max_offset_x, max_offset_y


def portrait_editor_transform(state: PortraitEditorState, *, zoom: float | None = None,
                              offset_x: float | None = None,
                              offset_y: float | None = None) -> PortraitEditorState:
    """Normalize fachliche Zoom-/Offsetwerte unabhängig von einem UI-Toolkit."""
    minimum_zoom, maximum_zoom = PORTRAIT_EDITOR_ZOOM_RANGE
    normalized_zoom = max(minimum_zoom, min(maximum_zoom, float(
        state.zoom if zoom is None else zoom
    )))
    candidate = PortraitEditorState(
        source_path=state.source_path,
        source_size=state.source_size,
        zoom=normalized_zoom,
        offset_x=float(state.offset_x if offset_x is None else offset_x),
        offset_y=float(state.offset_y if offset_y is None else offset_y),
        initial_zoom=state.initial_zoom,
        initial_offset_x=state.initial_offset_x,
        initial_offset_y=state.initial_offset_y,
    )
    _scale, _width, _height, max_x, max_y = portrait_editor_geometry(candidate)
    normalized_offset_x = 0.0 if max_x == 0.0 else max(-max_x, min(max_x, candidate.offset_x))
    normalized_offset_y = 0.0 if max_y == 0.0 else max(-max_y, min(max_y, candidate.offset_y))
    return PortraitEditorState(
        source_path=candidate.source_path,
        source_size=candidate.source_size,
        zoom=candidate.zoom,
        offset_x=normalized_offset_x,
        offset_y=normalized_offset_y,
        initial_zoom=candidate.initial_zoom,
        initial_offset_x=candidate.initial_offset_x,
        initial_offset_y=candidate.initial_offset_y,
    )


def portrait_editor_pan(state: PortraitEditorState, delta_x: float,
                        delta_y: float) -> PortraitEditorState:
    """Apply a drag measured in the fixed editor reference coordinate system."""
    return portrait_editor_transform(
        state,
        offset_x=state.offset_x + float(delta_x),
        offset_y=state.offset_y + float(delta_y),
    )


def portrait_editor_zoom(state: PortraitEditorState, delta: float) -> PortraitEditorState:
    """Apply Tk-compatible center-based zoom while retaining legal offsets."""
    return portrait_editor_transform(state, zoom=state.zoom + float(delta))


def load_portrait_editor_state(source: Path | str) -> PortraitEditorState:
    """Validiert ein Quellbild ohne Mutation und erzeugt den Editor-State."""
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow ist nicht installiert.")
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    try:
        with Image.open(source_path) as raw:
            source_size = ImageOps.exif_transpose(raw).size
    except (OSError, ValueError) as exc:
        raise ValueError(f"Ungültiges Portrait: {source_path}") from exc
    if source_size[0] <= 0 or source_size[1] <= 0:
        raise ValueError(f"Ungültige Portraitgröße: {source_path}")
    return PortraitEditorState(source_path=source_path, source_size=source_size)


def render_portrait_editor_image(source_image, zoom: float = 1.0,
                                 offset_x: float = 0.0, offset_y: float = 0.0):
    """Render the v0.9.1 editor crop without depending on Tk or Qt state."""
    if Image is None:
        raise RuntimeError("Pillow ist nicht installiert.")
    if source_image is None or not hasattr(source_image, "size"):
        raise ValueError("Ungültiges Portraitbild.")
    source_width, source_height = source_image.size
    if source_width <= 0 or source_height <= 0:
        raise ValueError("Ungültige Portraitgröße.")

    minimum_zoom, maximum_zoom = PORTRAIT_EDITOR_ZOOM_RANGE
    normalized_zoom = max(minimum_zoom, min(maximum_zoom, float(zoom)))
    preview_width, preview_height = PORTRAIT_EDITOR_PREVIEW_SIZE
    base_scale = max(preview_width / source_width, preview_height / source_height)
    scale = base_scale * normalized_zoom
    scaled_size = (
        max(1, round(source_width * scale)),
        max(1, round(source_height * scale)),
    )
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    scaled = source_image.convert("RGB").resize(scaled_size, resampling)
    max_offset_x = max(0.0, (scaled.width - preview_width) / 2.0)
    max_offset_y = max(0.0, (scaled.height - preview_height) / 2.0)
    normalized_offset_x = max(-max_offset_x, min(max_offset_x, float(offset_x)))
    normalized_offset_y = max(-max_offset_y, min(max_offset_y, float(offset_y)))
    left = round((scaled.width - preview_width) / 2.0 - normalized_offset_x)
    top = round((scaled.height - preview_height) / 2.0 - normalized_offset_y)
    left = max(0, min(max(0, scaled.width - preview_width), left))
    top = max(0, min(max(0, scaled.height - preview_height), top))
    preview = scaled.crop((
        left, top, left + preview_width, top + preview_height,
    ))
    return preview.resize((PORTRAIT_WIDTH, PORTRAIT_HEIGHT), resampling)


def render_portrait_editor_state(state: PortraitEditorState):
    """Render a final portrait solely from the persisted editor state."""
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow ist nicht installiert.")
    normalized = portrait_editor_transform(state)
    if not normalized.source_path.is_file():
        raise FileNotFoundError(normalized.source_path)
    try:
        with Image.open(normalized.source_path) as raw:
            source_image = ImageOps.exif_transpose(raw).convert("RGB").copy()
    except (OSError, ValueError) as exc:
        raise ValueError(f"Ungültiges Portrait: {normalized.source_path}") from exc
    if source_image.size != normalized.source_size:
        raise ValueError(f"Portraitgröße wurde geändert: {normalized.source_path}")
    return render_portrait_editor_image(
        source_image, normalized.zoom, normalized.offset_x, normalized.offset_y,
    )


def save_portrait_editor_image(source_image, destination: Path | str,
                               zoom: float = 1.0, offset_x: float = 0.0,
                               offset_y: float = 0.0) -> Path:
    """Render and atomically replace a portrait using the v0.9.1 PNG contract."""
    destination_path = Path(destination)
    final = render_portrait_editor_image(source_image, zoom, offset_x, offset_y)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.with_suffix(destination_path.suffix + ".edit.tmp")
    try:
        final.save(temporary_path, format="PNG", optimize=True)
        os.replace(temporary_path, destination_path)
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
    return destination_path


def save_portrait_editor_state(state: PortraitEditorState,
                               destination: Path | str) -> Path:
    """Save a Qt/Tk-neutral editor state without mutating the source on failure."""
    final = render_portrait_editor_state(state)
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.with_suffix(destination_path.suffix + ".edit.tmp")
    try:
        final.save(temporary_path, format="PNG", optimize=True)
        os.replace(temporary_path, destination_path)
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
    return destination_path


def missing_portrait_names(names: Iterable[str],
                           project_path: Path | str | None,
                           member_ids: dict[str, str | None] | None = None) -> list[str]:
    """Return names without an active portrait while preserving input order."""
    return [
        name for name in names
        if existing_portrait_for_member(
            str((member_ids or {}).get(name.casefold()) or ""), project_path,
        ) is None
    ]


def proportional_fit_size(source_size: tuple[int, int], bounds: tuple[int, int]) -> tuple[int, int]:
    width, height = source_size
    max_width, max_height = bounds
    if min(width, height, max_width, max_height) <= 0:
        return (1, 1)
    scale = min(max_width / width, max_height / height)
    return (max(1, round(width * scale)), max(1, round(height * scale)))


def cover_scale_size(source_size: tuple[int, int], target_size: tuple[int, int]) -> tuple[int, int]:
    width, height = source_size
    target_width, target_height = target_size
    if min(width, height, target_width, target_height) <= 0:
        return (1, 1)
    scale = max(target_width / width, target_height / height)
    return (max(1, math.ceil(width * scale)), max(1, math.ceil(height * scale)))


def save_manual_portrait_image(source: Path, destination: Path,
                               size: tuple[int, int] = (PORTRAIT_WIDTH, PORTRAIT_HEIGHT)) -> None:
    """Normalize a selected image to the grabber's canonical portrait PNG."""
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow ist nicht installiert.")
    source = Path(source)
    destination = Path(destination)
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".manual.tmp")
    try:
        with Image.open(source) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            fitted = ImageOps.fit(image, size, method=resampling, centering=(0.5, 0.42))
            fitted.save(temp, format="PNG", optimize=True)
        os.replace(temp, destination)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass


def cleanup_active_portrait_variants(name: str, kept_path: Path,
                                     project_path: Path | str | None) -> None:
    """Remove stale active-portrait variants while leaving history untouched."""
    kept = Path(kept_path).resolve()
    for candidate in portrait_candidates_for_name(name, project_path):
        try:
            if candidate.exists() and candidate.resolve() != kept:
                candidate.unlink()
        except OSError:
            # This matches the legacy post-save cleanup: the successfully saved
            # canonical portrait remains authoritative even if a stale variant
            # is temporarily locked.
            pass


def import_active_portrait_image(source: Path, member_id: str,
                                 project_path: Path | str) -> Path:
    """Normalize and atomically replace one member-ID portrait."""
    destination = normal_portrait_path(member_id, project_path)
    save_manual_portrait_image(source, destination)
    return destination


def remove_active_portrait_files(member_id: str,
                                 project_path: Path | str | None) -> list[Path]:
    """Delete only the one productive member-ID portrait."""
    existing = []
    portrait = existing_portrait_for_member(member_id, project_path)
    if portrait is not None:
        existing.append(portrait)
    for path in existing:
        path.unlink()
    return existing


def build_armory_url(name: str, region: str = DEFAULT_REGION,
                     realm: str = DEFAULT_REALM,
                     game_version: str = DEFAULT_GAME_VERSION) -> str:
    name = name.strip()
    if not name:
        raise ValueError(tr("grabber.character_empty"))
    return (
        "https://classicwowarmory.com/character/"
        f"{urllib.parse.quote(region.strip(), safe='')}/"
        f"{urllib.parse.quote(realm.strip(), safe='')}/"
        f"{urllib.parse.quote(name, safe='')}"
        f"?game_version={urllib.parse.quote(game_version.strip(), safe='')}"
    )


def build_portrait_source_url(name: str, settings: dict) -> str:
    """Build a character URL through the active source boundary."""
    source_id = normalize_portrait_source_id(settings.get("source_id"))
    if source_id == PORTRAIT_SOURCE_ARMORY:
        return build_armory_url(
            name,
            str(settings.get("region") or DEFAULT_REGION),
            str(settings.get("realm") or DEFAULT_REALM),
            str(settings.get("game_version") or DEFAULT_GAME_VERSION),
        )
    raise ValueError(f"Nicht unterstützte Portraitquelle: {source_id}")


def safe_filename(name: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", name.strip()).rstrip(". ")
    return cleaned or "character"


def read_text_flexible(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def dedupe_names(names: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = str(raw).strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(name)
    return result


def parse_txt_names(path: Path) -> list[str]:
    text = read_text_flexible(path)
    return dedupe_names(line.strip() for line in text.splitlines())


def _sniff_dialect(text: str):
    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def parse_csv_names(path: Path) -> list[str]:
    text = read_text_flexible(path)
    dialect = _sniff_dialect(text)
    stream = io.StringIO(text)
    reader = csv.reader(stream, dialect)
    rows = list(reader)
    if not rows:
        return []

    header = [c.strip().lstrip("\ufeff") for c in rows[0]]
    name_col: Optional[int] = None
    for i, col in enumerate(header):
        if col.casefold() == "name":
            name_col = i
            break

    start = 1 if name_col is not None else 0
    if name_col is None:
        name_col = 0

    names: list[str] = []
    for row in rows[start:]:
        if name_col < len(row):
            value = row[name_col].strip()
            if value:
                names.append(value)
    return dedupe_names(names)


def parse_ggc_names(path: Path, active_only: bool = True) -> list[str]:
    text = read_text_flexible(path)
    obj = json.loads(text)
    members = obj.get("members") if isinstance(obj, dict) else None
    if not isinstance(members, list):
        raise ValueError(tr("grabber.invalid_project"))

    names: list[str] = []
    for member in members:
        if not isinstance(member, dict):
            continue
        if active_only and str(member.get("lifeStatus", "active")).casefold() != "active":
            continue
        name = str(member.get("name", "")).strip()
        if name:
            names.append(name)
    return dedupe_names(names)


def _canonical_value(value, allowed: Iterable[str]) -> str | None:
    text = str(value or "").strip()
    return next((item for item in allowed if item.casefold() == text.casefold()), None)


def _canonical_alias(value, aliases: dict[str, tuple[str, ...]]) -> str | None:
    text = re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip().casefold()
    if not text:
        return None
    return next(
        (canonical for canonical, values in aliases.items()
         if any(text == alias.casefold() for alias in values)),
        None,
    )


def normalize_armory_race(value) -> str | None:
    return _canonical_alias(value, RACE_ALIASES)


def normalize_armory_class(value) -> str | None:
    return _canonical_alias(value, CLASS_ALIASES)


def parse_ggc_characters(path: Path, active_only: bool = True) -> tuple[list[dict], dict]:
    obj = json.loads(read_text_flexible(path))
    members = obj.get("members") if isinstance(obj, dict) else None
    if not isinstance(members, list):
        raise ValueError(tr("grabber.invalid_project"))
    records: list[dict] = []
    seen: set[str] = set()
    for member in members:
        if not isinstance(member, dict):
            continue
        if active_only and str(member.get("lifeStatus", "active")).casefold() != "active":
            continue
        name = str(member.get("name") or "").strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        records.append({
            "memberId": str(member.get("id") or "").strip() or None,
            "characterName": name,
            "race": _canonical_value(member.get("race"), RACE_NAMES),
            "className": _canonical_value(member.get("className") or member.get("class"), CLASS_NAMES),
            "lifeStatus": str(member.get("lifeStatus") or "active").strip().casefold(),
            "deathDate": str(member.get("deathDate") or "").strip(),
            "graveTemplateId": str(member.get("graveTemplateId") or "").strip(),
            "gravestoneTemplate": str(member.get("gravestoneTemplate") or "").strip(),
            "gravestoneCategory": normalize_gravestone_category(
                member.get("gravestoneCategory")
            ) or "",
            "portraitOffsetX": member.get("portraitOffsetX", 0.0),
            "portraitOffsetY": member.get("portraitOffsetY", 0.0),
            "portraitZoom": member.get("portraitZoom", 1.0),
            "textOffsetX": member.get("textOffsetX", 0.0),
            "textOffsetY": member.get("textOffsetY", 0.0),
            "textScale": member.get("textScale", 1.0),
        })
    context = {
        "sessionId": str(obj.get("armorySessionId") or "").strip() or None,
        "region": str(obj.get("region") or DEFAULT_REGION),
        "realm": str(obj.get("realm") or DEFAULT_REALM),
        "gameVersion": str(obj.get("gameVersion") or DEFAULT_GAME_VERSION),
    }
    return records, context


def _alias_pattern(aliases: dict[str, tuple[str, ...]]) -> str:
    values = {alias for choices in aliases.values() for alias in choices}
    return "|".join(re.escape(value) for value in sorted(values, key=len, reverse=True))


def _unique_alias_matches(text: str, aliases: dict[str, tuple[str, ...]]) -> list[str]:
    pattern = _alias_pattern(aliases)
    matches = {
        _canonical_alias(match, aliases)
        for match in re.findall(rf"(?<![\w])({pattern})(?![\w])", text, re.IGNORECASE)
    }
    matches.discard(None)
    return [canonical for canonical in aliases if canonical in matches]


def _structured_armory_values(content) -> dict[str, str | None]:
    races: set[str] = set()
    classes: set[str] = set()

    def visit(value, key: str = "") -> None:
        folded_key = re.sub(r"[^a-z]", "", key.casefold())
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, str(child_key))
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child, key)
        elif folded_key in {"race", "characterrace", "playerrace"}:
            if canonical := normalize_armory_race(value):
                races.add(canonical)
        elif folded_key in {"class", "classname", "characterclass", "playerclass"}:
            if canonical := normalize_armory_class(value):
                classes.add(canonical)

    visit(content)
    return {
        "race": next(iter(races)) if len(races) == 1 else None,
        "className": next(iter(classes)) if len(classes) == 1 else None,
    }


def extract_armory_character_data(content) -> dict[str, str | None]:
    """Extract canonical Race/Class values without relying on one CSS selector."""
    structured = _structured_armory_values(content)
    if structured["race"] and structured["className"]:
        return structured
    if isinstance(content, dict):
        content = json.dumps(content, ensure_ascii=False)
    if isinstance(content, (list, tuple)):
        content = "\n".join(str(item) for item in content if item is not None)
    raw = html.unescape(str(content or ""))
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()

    race_pattern = _alias_pattern(RACE_ALIASES)
    class_pattern = _alias_pattern(CLASS_ALIASES)

    def labeled(label: str, pattern: str, aliases: dict[str, tuple[str, ...]]) -> str | None:
        values = {
            _canonical_alias(match, aliases)
            for match in re.findall(rf"(?<![\w])(?:{label})(?![\w])\s*[:=-]?\s*({pattern})(?![\w])", text, re.IGNORECASE)
        }
        values.discard(None)
        return next(iter(values)) if len(values) == 1 else None

    race = structured["race"] or labeled("Race|Rasse", race_pattern, RACE_ALIASES)
    class_name = structured["className"] or labeled("Class|Klasse", class_pattern, CLASS_ALIASES)
    level_pairs = re.findall(
        rf"(?<![\w])(?:Level|Stufe)\s+\d+\s+({race_pattern})\s+({class_pattern})(?![\w])",
        text, re.IGNORECASE,
    )
    canonical_pairs = {
        (normalize_armory_race(pair[0]), normalize_armory_class(pair[1]))
        for pair in level_pairs
    }
    level_pair_found = len(canonical_pairs) == 1
    if level_pair_found:
        pair_race, pair_class = next(iter(canonical_pairs))
        race = race or pair_race
        class_name = class_name or pair_class

    race_matches = _unique_alias_matches(text, RACE_ALIASES)
    class_matches = _unique_alias_matches(text, CLASS_ALIASES)
    if race is None and len(race_matches) == 1:
        race = race_matches[0]
    if class_name is None and len(class_matches) == 1:
        class_name = class_matches[0]
    if (len(race_matches) > 1 and not structured["race"] and not level_pair_found
            and not labeled("Race|Rasse", race_pattern, RACE_ALIASES)):
        race = None
    if (len(class_matches) > 1 and not structured["className"] and not level_pair_found
            and not labeled("Class|Klasse", class_pattern, CLASS_ALIASES)):
        class_name = None
    return {"race": race, "className": class_name}


def merge_armory_data(record: dict, data: dict) -> dict:
    race = normalize_armory_race(data.get("race"))
    class_name = normalize_armory_class(data.get("className"))
    if race and not _canonical_value(record.get("race"), RACE_NAMES):
        record["race"] = race
    if class_name and not _canonical_value(record.get("className"), CLASS_NAMES):
        record["className"] = class_name
    return record


def records_missing_armory_data(records: Iterable[dict]) -> list[dict]:
    return [
        record for record in records
        if not _canonical_value(record.get("race"), RACE_NAMES)
        or not _canonical_value(record.get("className"), CLASS_NAMES)
    ]


def is_armory_protection_content(url: str, title: str, text: str) -> bool:
    combined = "\n".join((str(url or ""), str(title or ""), str(text or ""))).casefold()
    signals = (
        "http 401", "401 unauthorized", "unauthorized", "access denied",
        "checking your browser", "verify you are human", "just a moment",
        "schutzseite", "zugriff verweigert",
    )
    return any(signal in combined for signal in signals)


def url_matches_character_name(url: str, name: str) -> bool:
    try:
        path = urllib.parse.unquote(urllib.parse.urlparse(str(url or "")).path).rstrip("/")
        return bool(path) and path.rsplit("/", 1)[-1].casefold() == str(name or "").strip().casefold()
    except Exception:
        return False


class ArmoryProtectionTimeout(RuntimeError):
    pass


class BrowserBatchStopped(RuntimeError):
    pass


def write_armory_results(path: Path, payload: dict) -> None:
    data = dict(payload)
    data.setdefault("format", ARMORY_RESULT_FORMAT)
    data.setdefault("formatVersion", ARMORY_RESULT_VERSION)
    results = []
    for item in data.get("results", []):
        if not isinstance(item, dict):
            continue
        result = dict(item)
        result.setdefault("source", "classicwowarmory")
        result.setdefault("retrievedAt", datetime.now(timezone.utc).isoformat())
        results.append(result)
    data["results"] = results
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def load_names_from_file(path: Path, active_only: bool = True) -> list[str]:
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        return parse_csv_names(path)
    if suffix == ".ggc":
        return parse_ggc_names(path, active_only=active_only)
    return parse_txt_names(path)


def clamp_crop(crop: dict) -> dict:
    # Default crop tuned for a taller in-game portrait similar to the user's example:
    # full head, shoulders, torso and upper legs with little empty side margin.
    defaults = {"x1": 0.30, "y1": 0.05, "x2": 0.70, "y2": 0.86}
    out = {}
    for key, default in defaults.items():
        try:
            out[key] = min(1.0, max(0.0, float(crop.get(key, default))))
        except Exception:
            out[key] = default
    if out["x2"] <= out["x1"] + 0.02 or out["y2"] <= out["y1"] + 0.02:
        return defaults.copy()
    return out


def crop_portrait(source: Path, destination: Path, crop: dict,
                  width: int = PORTRAIT_WIDTH, height: int = PORTRAIT_HEIGHT) -> None:
    if Image is None:
        raise RuntimeError("Pillow ist nicht installiert.")
    crop = clamp_crop(crop)
    with Image.open(source) as im:
        im = im.convert("RGB")
        w, h = im.size
        x1 = int(round(crop["x1"] * w))
        y1 = int(round(crop["y1"] * h))
        x2 = int(round(crop["x2"] * w))
        y2 = int(round(crop["y2"] * h))
        x1, y1 = max(0, min(w - 1, x1)), max(0, min(h - 1, y1))
        x2, y2 = max(x1 + 1, min(w, x2)), max(y1 + 1, min(h, y2))
        cut = im.crop((x1, y1, x2, y2))

        # Fit the chosen crop to the target portrait ratio without distortion.
        target_ratio = width / height
        cw, ch = cut.size
        current_ratio = cw / ch if ch else target_ratio
        if current_ratio > target_ratio:
            new_w = max(1, int(round(ch * target_ratio)))
            left = max(0, (cw - new_w) // 2)
            cut = cut.crop((left, 0, left + new_w, ch))
        elif current_ratio < target_ratio:
            new_h = max(1, int(round(cw / target_ratio)))
            top = max(0, (ch - new_h) // 2)
            cut = cut.crop((0, top, cw, top + new_h))

        resampling = getattr(Image, "Resampling", Image).LANCZOS
        cut = cut.resize((width, height), resampling)
        destination.parent.mkdir(parents=True, exist_ok=True)
        cut.save(destination, format="PNG", optimize=True)


def image_has_detail(path: Path) -> bool:
    """Reject obviously blank/solid screenshots (e.g. failed WebGL canvas capture)."""
    if Image is None:
        return True
    try:
        with Image.open(path) as im:
            gray = im.convert("L").resize((64, 64))
            lo, hi = gray.getextrema()
            return (hi - lo) >= 8
    except Exception:
        return False


def config_path() -> Path:
    return suite_root_dir() / "config" / "portrait_grabber.json"


def legacy_config_path() -> Path:
    return legacy_app_data_dir() / "config.json"


def load_config() -> dict:
    defaults = {
        "portrait_source": PORTRAIT_SOURCE_ARMORY,
        "portrait_sources": {},
        "region": DEFAULT_REGION,
        "realm": DEFAULT_REALM,
        "game_version": DEFAULT_GAME_VERSION,
        "crop": clamp_crop({}),
        # Keep the original v0.1.2 Playwright workflow as the default.
        "browser_channel": "msedge",
        "wait_after_load": 3.0,
        # Optional additions. They do not change the v0.1.2 workflow.
        "capture_mode": "playwright",
        "standard_wait_after_open": 6.0,
        "screen_region": {"x": 0, "y": 0, "width": 0, "height": 0},
    }
    path = config_path()
    source = path
    if not path.exists() and legacy_config_path().exists():
        source = legacy_config_path()
    try:
        obj = json.loads(read_text_flexible(source))
        if isinstance(obj, dict):
            defaults.update(obj)
    except Exception:
        pass
    # Alte globale Ausgabeordner bleiben in vorhandenen Settings unangetastet,
    # werden aber nicht mehr als Portraitquelle oder -ziel verwendet.
    defaults.pop("output_dir", None)
    defaults["crop"] = clamp_crop(defaults.get("crop", {}))
    region = defaults.get("screen_region")
    if not isinstance(region, dict):
        region = {}
    defaults["screen_region"] = {
        "x": int(region.get("x", 0) or 0),
        "y": int(region.get("y", 0) or 0),
        "width": int(region.get("width", 0) or 0),
        "height": int(region.get("height", 0) or 0),
    }
    if defaults.get("capture_mode") not in {"playwright", "standard_browser_region"}:
        defaults["capture_mode"] = "playwright"
    defaults["portrait_source"] = normalize_portrait_source_id(defaults.get("portrait_source"))
    source_configs = defaults.get("portrait_sources")
    defaults["portrait_sources"] = {
        str(source_id): dict(source_config)
        for source_id, source_config in (source_configs.items() if isinstance(source_configs, dict) else ())
        if isinstance(source_config, dict)
    }
    return defaults


def save_config(config: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


CAPTURE_MODE_PLAYWRIGHT = tr("grabber.mode_playwright")
CAPTURE_MODE_STANDARD = tr("grabber.mode_standard")


def capture_mode_display(value: str) -> str:
    return {
        "playwright": CAPTURE_MODE_PLAYWRIGHT,
        "standard_browser_region": CAPTURE_MODE_STANDARD,
    }.get(value, CAPTURE_MODE_PLAYWRIGHT)


def capture_mode_from_display(value: str) -> str:
    folded = str(value or "").casefold()
    for stored, displayed in (
        ("playwright", CAPTURE_MODE_PLAYWRIGHT),
        ("standard_browser_region", CAPTURE_MODE_STANDARD),
    ):
        if folded in {stored.casefold(), displayed.casefold()}:
            return stored
    return "playwright"


def normalize_portrait_source_id(value: object) -> str:
    """Return the only currently implemented portrait source identifier.

    Unknown or legacy values deliberately fall back to the established Armory
    workflow. A later source can be added here without changing either GUI's
    worker contract.
    """
    source_id = str(value or "").strip().casefold()
    return source_id if source_id in PORTRAIT_SOURCE_IDS else PORTRAIT_SOURCE_ARMORY


def portrait_source_settings(config: dict, source_id: object | None = None) -> dict:
    """Merge legacy settings with optional settings of one portrait source.

    Existing settings remain the compatibility baseline. Per-source values are
    intentionally an overlay so future URL/browser/capture calibration stays
    outside the Qt and Tk workflow code.
    """
    source_id = normalize_portrait_source_id(
        config.get("portrait_source") if source_id is None else source_id
    )
    settings = dict(config)
    source_configs = config.get("portrait_sources")
    source_config = (
        source_configs.get(source_id)
        if isinstance(source_configs, dict) else None
    )
    if isinstance(source_config, dict):
        settings.update(source_config)
    settings["source_id"] = source_id
    return settings


def build_saved_grabber_config(
    current_config: dict,
    *,
    region: str,
    realm: str,
    game_version: str,
    guild_name: str,
    crop: dict,
    capture_mode: str,
    standard_wait_after_open: float | str | None,
    screen_region: tuple[int, int, int, int],
) -> dict:
    """Return the existing persisted config using only plain Python inputs."""
    config = dict(current_config)
    config["region"] = region.strip() or DEFAULT_REGION
    config["realm"] = realm.strip() or DEFAULT_REALM
    config["game_version"] = game_version.strip() or DEFAULT_GAME_VERSION
    config["guild_name"] = guild_name.strip()
    config.pop("output_dir", None)
    config["crop"] = clamp_crop(crop)
    config["capture_mode"] = capture_mode_from_display(capture_mode)
    try:
        wait = float(standard_wait_after_open)
    except Exception:
        wait = 6.0
    config["standard_wait_after_open"] = max(1.0, min(60.0, wait))
    x, y, width, height = screen_region
    config["screen_region"] = {"x": x, "y": y, "width": width, "height": height}
    source_id = normalize_portrait_source_id(config.get("portrait_source"))
    source_configs = config.get("portrait_sources")
    source_configs = dict(source_configs) if isinstance(source_configs, dict) else {}
    source_config = source_configs.get(source_id)
    source_config = dict(source_config) if isinstance(source_config, dict) else {}
    for key in PORTRAIT_SOURCE_CONFIG_KEYS:
        source_config[key] = config.get(key)
    source_configs[source_id] = source_config
    config["portrait_source"] = source_id
    config["portrait_sources"] = source_configs
    return config


def build_worker_payload(
    *,
    region: str,
    realm: str,
    game_version: str,
    preferred_channel: str,
    wait_after_load: float | str,
    capture_mode: str,
    screen_region: tuple[int, int, int, int],
    standard_wait_after_open: float | str,
    source_id: object = PORTRAIT_SOURCE_ARMORY,
) -> dict:
    """Build the existing worker contract from plain Python values."""
    return {
        "source_id": normalize_portrait_source_id(source_id),
        "region": region.strip() or DEFAULT_REGION,
        "realm": realm.strip() or DEFAULT_REALM,
        "game_version": game_version.strip() or DEFAULT_GAME_VERSION,
        "preferred_channel": preferred_channel,
        "wait_after_load": float(wait_after_load),
        "capture_mode": capture_mode,
        "screen_region": screen_region,
        "standard_wait_after_open": float(standard_wait_after_open),
    }


def build_portrait_source_output(
    source_id: object,
    *,
    portrait_path: Path | str | None = None,
    race: str | None = None,
    class_name: str | None = None,
) -> dict:
    """Return the source-neutral portrait, race and class result fields.

    Existing events retain their established names and compatibility fields.
    Source implementations only add these common fields, so a later source
    does not need to know about either the Tk or Qt presentation layer.
    """
    return {
        "sourceId": normalize_portrait_source_id(source_id),
        "portraitPath": str(portrait_path) if portrait_path is not None else None,
        "race": race,
        "className": class_name,
    }


def localize_worker_message(message: str) -> str:
    """Translate stable worker messages without modifying the protected v0.1.2 core."""
    text = str(message or "")
    exact = {
        "Teste Microsoft Edge / Browsersteuerung …": tr("grabber.worker_test"),
        "Viewer-Screenshot war leer; nutze Viewport-Fallback …": tr("grabber.worker_viewer_fallback"),
    }
    if text in exact:
        return exact[text]
    match = re.fullmatch(r"Oeffne (.+) …", text)
    if match:
        return tr("grabber.worker_opening", name=match.group(1))
    match = re.fullmatch(r"HTTP (\d+): Browser offen lassen; ggf\. Schutzseite manuell bestaetigen\.", text)
    if match:
        return tr("grabber.worker_http", status=match.group(1))
    match = re.fullmatch(r"Standardbrowser geoeffnet: (.+)", text)
    if match:
        return tr("grabber.worker_standard_opened", name=match.group(1))
    return text


def interpret_worker_event(event: dict) -> dict:
    """Interpret a worker event without accessing Tk widgets or dialogs."""
    kind = event.get("type")
    name = event.get("name", "")
    semantic = {"kind": kind, "name": name}
    if kind == "browser_ready":
        message = tr("grabber.browser_ready", browser=event.get("browser"))
        semantic.update(status=message, log=message)
    elif kind == "browser_test_ok":
        browser = event.get("browser", "Browser")
        message = tr("grabber.browser_test_ok", browser=browser)
        semantic.update(
            status=message,
            log=message,
            dialog={
                "type": "info",
                "title": tr("grabber.browser_test_title"),
                "message": tr("grabber.browser_test_message", browser=browser),
            },
        )
    elif kind == "progress":
        message = localize_worker_message(event.get("message", ""))
        semantic.update(status=message, log=message, refresh_tree=True)
        if name:
            semantic["name_status"] = message
    elif kind == "opened":
        method = event.get("method", "")
        semantic.update(
            name_status=f"{tr('grabber.opened')} ({method})" if method else tr("grabber.opened"),
            status=tr("grabber.opened_help", name=name),
            log=tr("grabber.opened_log", name=name, method=method).strip(),
            refresh_tree=True,
        )
    elif kind == "portrait_saved":
        semantic.update(
            name_status=f"{tr('grabber.portrait_saved')} ({event.get('method', '')})",
            status=tr("grabber.saved", path=event.get("path")),
            log=tr("grabber.saved_for_name_log", name=name, path=event.get("path")),
            refresh_tree=True,
            action={"type": "refresh_portrait", "name": name},
        )
    elif kind == "armory_data":
        result = event.get("result") or {}
        race = race_display(result.get("race")) if result.get("race") else tr("grabber.not_recognized")
        class_name = result.get("className") or tr("grabber.not_recognized")
        message = tr("grabber.data_read", name=name, race=race, class_name=class_name)
        semantic.update(
            model_action={"type": "store_armory_result", "result": result},
            name_status=message,
            status=message,
            log=message,
            refresh_tree=True,
        )
    elif kind == "armory_data_error":
        message = tr("grabber.data_not_recognized", name=name, error=event.get("message") or "")
        semantic.update(name_status=message, status=message, log=message, refresh_tree=True)
    elif kind == "armory_data_wait_timeout":
        message = event.get("message") or tr("grabber.protection_timeout", name=name)
        semantic.update(name_status=message, status=message, log=message, refresh_tree=True)
    elif kind == "raw_capture":
        semantic.update(
            name_status=tr("grabber.calibration_ready", method=event.get("method", "")),
            refresh_tree=True,
            action={"type": "open_crop_dialog", "path": event.get("path"), "name": name},
        )
    elif kind == "batch_progress":
        semantic.update(
            status=f"{event.get('index')}/{event.get('total')}: {name}",
            action={
                "type": "batch_progress",
                "maximum": max(1, int(event.get("total", 1))),
                "value": max(0, int(event.get("index", 1)) - 1),
            },
        )
    elif kind == "item_error":
        message = event.get("message", "")
        semantic.update(
            name_status=tr("grabber.item_error", message=message[:180]),
            log=f"{name}: {tr('grabber.item_error', message=message)}",
            refresh_tree=True,
        )
    elif kind == "guild_roster_progress":
        page = int(event.get("page", 1))
        total = max(1, int(event.get("total", 1)))
        message = tr("grabber.guild_roster_progress", page=page, total=total)
        semantic.update(status=message, log=message)
    elif kind == "guild_roster_ready":
        semantic["action"] = {"type": "store_guild_roster_snapshot", "event": event}
    elif kind == "guild_roster_error":
        message = tr("grabber.guild_roster_error", error=event.get("message") or "")
        semantic.update(
            status=message,
            log=message,
            action={"type": "finish_guild_roster"},
            dialog={"type": "error", "title": tr("grabber.guild_roster_title"), "message": message},
        )
    elif kind == "batch_done":
        processed = int(event.get("processed", event.get("total", 0)))
        failures = int(event.get("failures", 0))
        successes = int(event.get("successes", max(0, processed - failures)))
        cancelled = bool(event.get("cancelled"))
        message = (
            tr(
                "grabber.batch_cancelled",
                processed=processed,
                total=event.get("total", 0),
                successes=successes,
                failures=failures,
            )
            if cancelled
            else tr("grabber.batch_done", successes=successes, failures=failures)
        )
        semantic.update(
            status=message,
            log=message,
            refresh_tree=True,
            action={"type": "batch_done", "processed": processed},
        )
    elif kind == "error":
        message = (event.get("message") or tr("grabber.screenshot_error")).strip()
        log_path = event.get("log_path") or str(suite_root_dir() / "data" / "logs" / "portrait_grabber.log")
        status = tr("grabber.error_prefix", message=message)
        semantic.update(
            status=status,
            log=status,
            dialog={
                "type": "text",
                "title": tr("grabber.screenshot_error"),
                "message": message
                + "\n\n"
                + tr("grabber.technical_details")
                + "\n"
                + (event.get("detail") or "")
                + "\n\n"
                + tr("grabber.error_log")
                + "\n"
                + log_path,
            },
        )
    return semantic


def virtual_screen_bounds() -> tuple[int, int, int, int]:
    """Return virtual desktop bounds as x, y, width, height."""
    if os.name == "nt":
        try:
            user32 = ctypes.windll.user32
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
            x = int(user32.GetSystemMetrics(76))
            y = int(user32.GetSystemMetrics(77))
            w = int(user32.GetSystemMetrics(78))
            h = int(user32.GetSystemMetrics(79))
            if w > 0 and h > 0:
                return x, y, w, h
        except Exception:
            pass
    return (0, 0, 1920, 1080)


def normalize_screen_region(region) -> tuple[int, int, int, int]:
    if isinstance(region, dict):
        return (
            int(region.get("x", 0) or 0), int(region.get("y", 0) or 0),
            int(region.get("width", 0) or 0), int(region.get("height", 0) or 0),
        )
    try:
        x, y, w, h = region
        return int(x), int(y), int(w), int(h)
    except Exception:
        return (0, 0, 0, 0)


def validate_screen_region(region, bounds: Optional[tuple[int, int, int, int]] = None) -> tuple[bool, str]:
    x, y, w, h = normalize_screen_region(region)
    if w < 64 or h < 64:
        return False, tr("grabber.region_too_small")
    bx, by, bw, bh = bounds or virtual_screen_bounds()
    if bw <= 0 or bh <= 0:
        return False, tr("grabber.screen_unknown")
    if x < bx or y < by or x + w > bx + bw or y + h > by + bh:
        return False, tr("grabber.region_outside")
    return True, "OK"


def capture_screen_region(region) -> "Image.Image":
    if ImageGrab is None:
        raise RuntimeError("Pillow ImageGrab ist nicht verfuegbar.")
    x, y, w, h = normalize_screen_region(region)
    ok, msg = validate_screen_region((x, y, w, h))
    if not ok:
        raise ValueError(msg)
    image = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
    if image.size != (w, h):
        raise RuntimeError(f"Bildschirmaufnahme hat {image.width}x{image.height}px; erwartet {w}x{h}px.")
    return image


def image_object_has_detail(image: "Image.Image") -> bool:
    if ImageStat is None:
        return True
    if image.width < 32 or image.height < 32:
        return False
    probe = image.convert("RGB").resize((64, 64))
    stat = ImageStat.Stat(probe)
    return sum(float(v) for v in stat.var[:3]) >= 3.0


def save_screen_region_portrait(image: "Image.Image", destination: Path) -> None:
    """Preserve the selected screen region, fitting it into the v0.1.2 portrait size."""
    if ImageOps is None:
        raise RuntimeError("Pillow ist nicht installiert.")
    image = image.convert("RGB")
    fitted = ImageOps.contain(image, (PORTRAIT_WIDTH, PORTRAIT_HEIGHT))
    canvas = Image.new("RGB", (PORTRAIT_WIDTH, PORTRAIT_HEIGHT), "black")
    canvas.paste(fitted, ((PORTRAIT_WIDTH - fitted.width)//2, (PORTRAIT_HEIGHT - fitted.height)//2))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".tmp")
    canvas.save(temp, format="PNG", optimize=True)
    os.replace(temp, destination)


class ScrollableFrame(ttk.Frame):
    """Frame with vertical and horizontal scrolling for small windows."""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.content = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._sync_scrollregion)
        self.canvas.bind("<Configure>", self._canvas_resize)
        self.canvas.bind("<Enter>", lambda _e: self._bind_wheel())
        self.canvas.bind("<Leave>", lambda _e: self._unbind_wheel())

    def _sync_scrollregion(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _canvas_resize(self, event):
        # Fill the complete viewport while preserving scrollability for oversized content.
        req_width = max(1, self.content.winfo_reqwidth())
        req_height = max(1, self.content.winfo_reqheight())
        self.canvas.itemconfigure(
            self.window_id,
            width=max(event.width, req_width),
            height=max(event.height, req_height),
        )
        self._sync_scrollregion()

    def _bind_wheel(self):
        self.bind_all("<MouseWheel>", self._wheel)
        self.bind_all("<Shift-MouseWheel>", self._shift_wheel)

    def _unbind_wheel(self):
        try:
            self.unbind_all("<MouseWheel>")
            self.unbind_all("<Shift-MouseWheel>")
        except Exception:
            pass

    def _wheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def _shift_wheel(self, event):
        if event.delta:
            self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"


class ScrollableTextDialog(tk.Toplevel):
    def __init__(self, parent, title: str, text: str):
        super().__init__(parent)
        self.title(title)
        self.geometry("760x460")
        self.minsize(460, 300)
        self.transient(parent)
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        txt = tk.Text(outer, wrap="none")
        vy = ttk.Scrollbar(outer, orient="vertical", command=txt.yview)
        hx = ttk.Scrollbar(outer, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=vy.set, xscrollcommand=hx.set)
        txt.grid(row=0, column=0, sticky="nsew")
        vy.grid(row=0, column=1, sticky="ns")
        hx.grid(row=1, column=0, sticky="ew")
        outer.rowconfigure(0, weight=1); outer.columnconfigure(0, weight=1)
        txt.insert("1.0", text)
        txt.configure(state="disabled")
        ttk.Button(outer, text=tr("common.close"), command=self.destroy).grid(row=2, column=0, columnspan=2, sticky="e", pady=(8,0))
        self.bind("<Escape>", lambda _e: self.destroy())


class ScreenRegionSelector(tk.Toplevel):
    """Select a reusable portrait-ratio region from a virtual-desktop screenshot."""
    def __init__(self, parent, screenshot: "Image.Image", bounds: tuple[int,int,int,int], on_accept: Callable[[tuple[int,int,int,int]], None]):
        super().__init__(parent)
        self.title(tr("grabber.set_region"))
        self.geometry("1000x760")
        self.minsize(560, 420)
        self.transient(parent)
        self.grab_set()
        self.original = screenshot.convert("RGB")
        self.bounds = bounds
        self.on_accept = on_accept
        self.scale = 1.0
        self.photo = None
        self.start = None
        self.selection = None
        self.rect_id = None

        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=tr("grabber.selector_help", width=PORTRAIT_WIDTH, height=PORTRAIT_HEIGHT), wraplength=900).grid(row=0,column=0,columnspan=2,sticky="ew",pady=(0,6))
        cf = ttk.Frame(outer)
        cf.grid(row=1,column=0,columnspan=2,sticky="nsew")
        canvas = tk.Canvas(cf, background="#202020", highlightthickness=0, cursor="crosshair")
        vy = ttk.Scrollbar(cf, orient="vertical", command=canvas.yview)
        hx = ttk.Scrollbar(cf, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=vy.set, xscrollcommand=hx.set)
        canvas.grid(row=0,column=0,sticky="nsew"); vy.grid(row=0,column=1,sticky="ns"); hx.grid(row=1,column=0,sticky="ew")
        cf.rowconfigure(0,weight=1); cf.columnconfigure(0,weight=1)
        self.canvas = canvas

        # Keep enough detail while allowing scrollbars on small screens.
        sw = max(640, parent.winfo_screenwidth()); sh = max(480, parent.winfo_screenheight())
        self.scale = min(max(640, sw-140)/self.original.width, max(420, sh-220)/self.original.height, 1.0)
        disp = self.original.resize((max(1,int(self.original.width*self.scale)), max(1,int(self.original.height*self.scale)))) if self.scale < 1 else self.original
        self.photo = ImageTk.PhotoImage(disp)
        canvas.configure(scrollregion=(0,0,disp.width,disp.height))
        canvas.create_image(0,0,anchor="nw",image=self.photo)
        canvas.bind("<ButtonPress-1>", self._press)
        canvas.bind("<B1-Motion>", self._drag)
        canvas.bind("<ButtonRelease-1>", self._release)

        self.info_var = tk.StringVar(value=tr("grabber.no_region"))
        ttk.Label(outer, textvariable=self.info_var).grid(row=2,column=0,sticky="w",pady=(6,0))
        row = ttk.Frame(outer); row.grid(row=2,column=1,sticky="e",pady=(6,0))
        ttk.Button(row,text=tr("common.cancel"),command=self.destroy).pack(side="right")
        self.accept_btn = ttk.Button(row,text=tr("grabber.apply_region"),command=self._accept,state="disabled")
        self.accept_btn.pack(side="right",padx=(0,6))
        outer.rowconfigure(1,weight=1); outer.columnconfigure(0,weight=1)
        self.bind("<Escape>", lambda _e: self.destroy())

    def _canvas_xy(self, event):
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def _constrained_end(self, x, y):
        if self.start is None:
            return x, y
        sx, sy = self.start
        dx, dy = x-sx, y-sy
        ratio = PORTRAIT_WIDTH / PORTRAIT_HEIGHT
        if abs(dy) < 1 and abs(dx) < 1:
            return x,y
        if abs(dx) / max(1,abs(dy)) > ratio:
            h = abs(dx) / ratio
            dy = h if dy >= 0 else -h
        else:
            w = abs(dy) * ratio
            dx = w if dx >= 0 else -w
        maxx = self.original.width*self.scale; maxy = self.original.height*self.scale
        ex=max(0,min(maxx,sx+dx)); ey=max(0,min(maxy,sy+dy))
        # Recompute after clamping to stay in ratio.
        dx=ex-sx; dy=ey-sy
        if abs(dx)/max(1,abs(dy)) > ratio:
            dx=(abs(dy)*ratio)*(1 if dx>=0 else -1)
        else:
            dy=(abs(dx)/ratio)*(1 if dy>=0 else -1)
        return sx+dx, sy+dy

    def _press(self,event):
        self.start=self._canvas_xy(event); self.selection=None; self.accept_btn.configure(state="disabled")
        if self.rect_id is not None: self.canvas.delete(self.rect_id)
        x,y=self.start; self.rect_id=self.canvas.create_rectangle(x,y,x,y,outline="yellow",width=3)

    def _drag(self,event):
        if self.start is None or self.rect_id is None: return
        x,y=self._canvas_xy(event); ex,ey=self._constrained_end(x,y); sx,sy=self.start
        self.canvas.coords(self.rect_id,sx,sy,ex,ey)
        self.info_var.set(f"{int(abs(ex-sx)/self.scale)} x {int(abs(ey-sy)/self.scale)} px")

    def _release(self,event):
        if self.start is None: return
        x,y=self._canvas_xy(event); ex,ey=self._constrained_end(x,y); sx,sy=self.start
        left,top=min(sx,ex),min(sy,ey); w,h=abs(ex-sx),abs(ey-sy)
        if w/self.scale < 64 or h/self.scale < 64:
            self.info_var.set(tr("grabber.region_too_small")); self.start=None; return
        bx,by,_,_=self.bounds
        self.selection=(bx+int(round(left/self.scale)), by+int(round(top/self.scale)),
                        int(round(w/self.scale)), int(round(h/self.scale)))
        ok,msg=validate_screen_region(self.selection,self.bounds)
        if ok:
            self.accept_btn.configure(state="normal")
        else:
            self.info_var.set(msg)
        self.start=None

    def _accept(self):
        if not self.selection: return
        ok,msg=validate_screen_region(self.selection,self.bounds)
        if not ok:
            messagebox.showerror(tr("grabber.region_title"),msg,parent=self); return
        self.on_accept(self.selection); self.destroy()


class ImagePreviewDialog(tk.Toplevel):
    def __init__(self,parent,image:"Image.Image",title=None):
        super().__init__(parent)
        self.title(title or tr("grabber.test_region")); self.geometry("900x700"); self.minsize(480,320); self.transient(parent)
        self.image=image.convert("RGB"); self.photo=ImageTk.PhotoImage(self.image)
        outer=ttk.Frame(self,padding=8); outer.pack(fill="both",expand=True)
        ttk.Label(outer,text=tr("grabber.capture_area", width=self.image.width, height=self.image.height)).grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,5))
        c=tk.Canvas(outer,highlightthickness=0); vy=ttk.Scrollbar(outer,orient="vertical",command=c.yview); hx=ttk.Scrollbar(outer,orient="horizontal",command=c.xview)
        c.configure(yscrollcommand=vy.set,xscrollcommand=hx.set,scrollregion=(0,0,self.image.width,self.image.height))
        c.grid(row=1,column=0,sticky="nsew"); vy.grid(row=1,column=1,sticky="ns"); hx.grid(row=2,column=0,sticky="ew")
        c.create_image(0,0,anchor="nw",image=self.photo)
        ttk.Button(outer,text=tr("common.close"),command=self.destroy).grid(row=3,column=0,columnspan=2,sticky="e",pady=(8,0))
        outer.rowconfigure(1,weight=1); outer.columnconfigure(0,weight=1)
        self.bind("<Escape>",lambda _e:self.destroy())


@dataclass
class BrowserCommand:
    action: str
    payload: dict


class BrowserWorker(threading.Thread):
    """ClassicWoWArmory-specific browser, URL and capture implementation."""

    def __init__(self, event_queue: queue.Queue):
        super().__init__(daemon=True)
        self.commands: queue.Queue[BrowserCommand] = queue.Queue()
        self.events = event_queue
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._running = True
        self._browser_name = ""
        self._active_browser_mode = None
        self._batch_cancel = threading.Event()

    def request_batch_cancel(self) -> None:
        """Thread-safe STOP request; checked between characters."""
        self._batch_cancel.set()

    def emit(self, kind: str, **payload) -> None:
        self.events.put({"type": kind, **payload})

    def submit(self, action: str, **payload) -> None:
        self.commands.put(BrowserCommand(action, payload))

    def _format_error(self, exc: BaseException) -> str:
        text = str(exc).strip()
        if text:
            return f"{type(exc).__name__}: {text}"
        return type(exc).__name__ or "Unbekannter Fehler"

    def _write_error_log(self, context: str, exc: BaseException) -> Path:
        path = suite_root_dir() / "data" / "logs" / "portrait_grabber.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        detail = traceback.format_exc()
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(f"\n===== {stamp} | {context} =====\n")
                f.write(self._format_error(exc) + "\n")
                f.write(detail + "\n")
        except Exception:
            pass
        return path

    def run(self) -> None:  # pragma: no cover - browser thread needs GUI/browser
        while self._running:
            try:
                cmd = self.commands.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                if cmd.action == "stop":
                    self._running = False
                    self._close_browser()
                    break
                if cmd.action in {"test_browser", "open", "capture", "capture_raw", "read_data"}:
                    self._batch_cancel.clear()
                if cmd.action == "test_browser":
                    self._test_browser(**cmd.payload)
                elif cmd.action == "open":
                    self._open_character(**cmd.payload)
                elif cmd.action == "capture":
                    self._capture_character(**cmd.payload)
                elif cmd.action == "capture_raw":
                    self._capture_raw_character(**cmd.payload)
                elif cmd.action == "capture_all":
                    self._capture_all(**cmd.payload)
                elif cmd.action == "read_data":
                    self._read_character_data(**cmd.payload)
                elif cmd.action == "read_data_all":
                    self._read_data_all(**cmd.payload)
            except Exception as exc:
                log_path = self._write_error_log(cmd.action, exc)
                self.emit(
                    "error",
                    message=self._format_error(exc),
                    detail=traceback.format_exc(),
                    log_path=str(log_path),
                )

    def _browser_is_healthy(self) -> bool:
        try:
            if self._browser is None or not self._browser.is_connected():
                return False
            if self._context is None:
                return False
            if self._page is not None and not self._page.is_closed():
                return True
            pages = [p for p in self._context.pages if not p.is_closed()]
            if pages:
                self._page = pages[0]
                self._page.set_default_timeout(12_000)
                return True
            self._page = self._context.new_page()
            self._page.set_default_timeout(12_000)
            return True
        except Exception:
            return False

    @staticmethod
    def _is_recoverable_browser_error(exc: BaseException) -> bool:
        text = f"{type(exc).__name__}: {exc}".casefold()
        return any(signal in text for signal in (
            "targetclosed", "target page, context or browser has been closed",
            "err_aborted", "frame was detached", "detached frame",
            "browser has been closed", "context has been closed", "page has been closed",
        ))

    def _ensure_capture_browser(self, capture_mode: str, preferred_channel: str) -> None:
        if capture_mode != "playwright":
            raise RuntimeError(f"Unbekannter Playwright-Modus: {capture_mode}")
        self._ensure_browser(preferred_channel)
        self._active_browser_mode = "playwright"

    def _run_with_browser_recovery(self, operation: Callable[[], object],
                                   capture_mode: str, preferred_channel: str):
        last_error = None
        for attempt in range(2):
            if self._batch_cancel.is_set():
                raise BrowserBatchStopped(tr("grabber.stop_requested_short"))
            try:
                self._ensure_capture_browser(capture_mode, preferred_channel)
                return operation()
            except Exception as exc:
                last_error = exc
                if not self._is_recoverable_browser_error(exc):
                    raise
                self._close_browser()
                if attempt or self._batch_cancel.is_set():
                    raise
                self.emit("progress", message=tr("grabber.browser_recovery"))
        raise last_error

    def _ensure_browser(self, preferred_channel: str = "msedge") -> None:
        # v0.1.1 intentionally uses a normal Playwright browser/context instead of
        # launch_persistent_context. This avoids stale profile locks and makes
        # recovery after manually closing Edge much more reliable.
        if self._browser_is_healthy():
            return

        self._close_browser()
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError(
                "Playwright ist nicht installiert. Bitte INSTALLIEREN.bat ausfuehren."
            ) from exc

        self._playwright = sync_playwright().start()
        attempts = []
        # Fixed robust order requested for this project: Edge -> Chrome -> bundled Chromium.
        candidates = [
            ("msedge", "Microsoft Edge"),
            ("chrome", "Google Chrome"),
            (None, "Playwright Chromium"),
        ]

        for channel, label in candidates:
            browser = None
            try:
                kwargs = {"headless": False}
                if channel:
                    kwargs["channel"] = channel
                browser = self._playwright.chromium.launch(**kwargs)
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = context.new_page()
                page.set_default_timeout(12_000)
                # Local smoke test: proves that the browser/context/page are really usable.
                page.set_content("<html><body><h1>Guild Portrait Grabber</h1></body></html>")
                if "Guild Portrait Grabber" not in page.locator("body").inner_text(timeout=3_000):
                    raise RuntimeError("Browser-Seite konnte nicht initialisiert werden.")

                self._browser = browser
                self._context = context
                self._page = page
                self._browser_name = label
                self.emit("browser_ready", browser=label)
                return
            except Exception as exc:
                attempts.append(f"{label}: {self._format_error(exc)}")
                try:
                    if browser is not None:
                        browser.close()
                except Exception:
                    pass
                self._browser = None
                self._context = None
                self._page = None

        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = None
        raise RuntimeError(
            "Kein nutzbarer Browser konnte gestartet werden. "
            "Reihenfolge: Microsoft Edge, Google Chrome, Playwright Chromium.\n\n"
            + "\n\n".join(attempts)
        )

    def _test_browser(self, preferred_channel: str = "msedge",
                      capture_mode: str = "playwright", **_unused) -> None:
        self.emit("progress", message="Teste Microsoft Edge / Browsersteuerung …")
        def operation():
            if self._page is None or self._page.is_closed():
                raise RuntimeError("Browser wurde gestartet, ist aber nicht steuerbar.")
            self._page.set_content(
                "<html><body style='font-family:sans-serif'><h1>Browser-Test OK</h1>"
                "<p>Playwright kann diesen Browser steuern.</p></body></html>"
            )
            text = self._page.locator("body").inner_text(timeout=3_000)
            if "Browser-Test OK" not in text:
                raise RuntimeError("Lokaler Browser-Funktionstest fehlgeschlagen.")
            self.emit("browser_test_ok", browser=self._browser_name)
        self._run_with_browser_recovery(operation, capture_mode, preferred_channel)

    def _close_browser(self) -> None:
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._context = None
        self._browser = None
        self._playwright = None
        self._page = None
        self._browser_name = ""
        self._active_browser_mode = None

    def _require_page(self):
        if not self._browser_is_healthy() or self._page is None:
            raise RuntimeError("Browser-Seite ist nicht verfügbar. Der Browser wird neu gestartet.")
        return self._page

    def _goto(self, name: str, region: str, realm: str, game_version: str,
              preferred_channel: str, wait_after_load: float) -> str:
        self._ensure_browser(preferred_channel)
        page = self._require_page()
        url = build_armory_url(name, region, realm, game_version)
        self.emit("progress", name=name, message=f"Oeffne {name} …")
        response = page.goto(url, wait_until="domcontentloaded", timeout=35_000)
        status = response.status if response is not None else None
        if status in (401, 403, 429):
            self.emit(
                "progress", name=name,
                message=f"HTTP {status}: Browser offen lassen; ggf. Schutzseite manuell bestaetigen."
            )
        try:
            page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass
        time.sleep(max(0.0, min(15.0, float(wait_after_load))))
        return url

    def _unlock_viewer(self) -> bool:
        page = self._require_page()
        candidates = [
            re.compile(r"click\s+to\s+unlock\s+the\s+3d\s+viewer", re.I),
            re.compile(r"unlock.*3d.*viewer", re.I),
            re.compile(r"3d\s+viewer", re.I),
        ]
        for rx in candidates:
            try:
                loc = page.get_by_text(rx).first
                if loc.count() and loc.is_visible():
                    loc.scroll_into_view_if_needed()
                    loc.click(timeout=5_000)
                    time.sleep(2.5)
                    return True
            except Exception:
                continue
        return False

    def _mark_best_viewer(self) -> bool:
        """Mark the most plausible visible viewer element with data-gpg-target=1."""
        page = self._require_page()
        script = r"""
        () => {
          document.querySelectorAll('[data-gpg-target="1"]').forEach(e => e.removeAttribute('data-gpg-target'));
          const selectors = [
            'canvas',
            '[class*="viewer" i]', '[id*="viewer" i]',
            '[class*="model" i]', '[id*="model" i]',
            '[class*="character" i] canvas', '[id*="character" i] canvas'
          ];
          const set = new Set();
          selectors.forEach(s => { try { document.querySelectorAll(s).forEach(e => set.add(e)); } catch (_) {} });
          let best = null, bestScore = 0;
          for (const e of set) {
            const r = e.getBoundingClientRect();
            const st = getComputedStyle(e);
            if (r.width < 180 || r.height < 220 || st.display === 'none' || st.visibility === 'hidden') continue;
            let score = r.width * r.height;
            if (e.tagName === 'CANVAS') score *= 4;
            const hint = ((e.id || '') + ' ' + (e.className || '')).toLowerCase();
            if (hint.includes('viewer') || hint.includes('model') || hint.includes('character')) score *= 1.7;
            if (score > bestScore) { best = e; bestScore = score; }
          }
          if (best) {
            best.setAttribute('data-gpg-target', '1');
            best.scrollIntoView({block:'center', inline:'center'});
            return {ok:true, tag:best.tagName, score:bestScore};
          }
          return {ok:false};
        }
        """
        try:
            result = page.evaluate(script)
            return bool(result and result.get("ok"))
        except Exception:
            return False

    def _raw_screenshot(self, name: str) -> tuple[Path, str]:
        page = self._require_page()
        self._unlock_viewer()
        time.sleep(1.5)
        found = self._mark_best_viewer()
        tmp_dir = app_data_dir() / "temp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        raw_path = tmp_dir / f"{safe_filename(name)}_raw.png"

        method = "viewport"
        if found:
            try:
                loc = page.locator('[data-gpg-target="1"]').first
                loc.scroll_into_view_if_needed()
                time.sleep(0.5)
                page.bring_to_front()
                loc.screenshot(path=str(raw_path), animations="disabled", timeout=15_000)
                if image_has_detail(raw_path):
                    method = "3D-Viewer/Canvas"
                    return raw_path, method
                self.emit("progress", name=name, message="Viewer-Screenshot war leer; nutze Viewport-Fallback …")
            except Exception:
                pass

        # Fallback: current viewport. This is intentionally still useful, because
        # the user can place/zoom the model manually in the visible browser.
        page.screenshot(path=str(raw_path), full_page=False, animations="disabled")
        return raw_path, method

    def _open_character(self, name: str, region: str, realm: str, game_version: str,
                        preferred_channel: str, wait_after_load: float,
                        capture_mode: str = "playwright", screen_region=None,
                        standard_wait_after_open: float = 6.0,
                        member_id: str | None = None, **_unused) -> None:
        if capture_mode == "standard_browser_region":
            url = build_armory_url(name, region, realm, game_version)
            ok = bool(webbrowser.open(url, new=0, autoraise=True))
            if not ok:
                raise RuntimeError("Windows konnte den Standardbrowser nicht oeffnen.")
            self.emit("armory_data_error", name=name, member_id=member_id,
                      message="DOM-Daten sind im Standardbrowser-Modus nicht verfügbar.", request_type="open")
            self.emit("opened", name=name, url=url, method="Windows-Standardbrowser")
            return
        def operation():
            url = self._goto(name, region, realm, game_version, preferred_channel, wait_after_load)
            self._unlock_viewer()
            self._attempt_armory_extraction(name, member_id, "open")
            self.emit("opened", name=name, url=url, method=self._browser_name)
        self._run_with_browser_recovery(operation, capture_mode, preferred_channel)

    def _current_page_is_character(self, name: str, region: str, realm: str, game_version: str) -> bool:
        if self._page is None:
            return False
        try:
            is_closed = getattr(self._page, "is_closed", None)
            if callable(is_closed) and is_closed():
                return False
            expected = urllib.parse.urlparse(build_armory_url(name, region, realm, game_version))
            current = urllib.parse.urlparse(self._page.url)
            return urllib.parse.unquote(current.path).casefold().rstrip("/") == urllib.parse.unquote(expected.path).casefold().rstrip("/")
        except Exception:
            return False

    def _extract_armory_character_data(self, page=None) -> dict[str, str | None]:
        page = page or self._page
        if page is None:
            raise RuntimeError("Keine geöffnete Armory-Seite verfügbar.")
        structured: dict[str, str | None] = {"race": None, "className": None}
        for selector, field, attribute in (
            ("[data-race]", "race", "data-race"),
            ("[data-character-race]", "race", "data-character-race"),
            ("[data-class]", "className", "data-class"),
            ("[data-character-class]", "className", "data-character-class"),
        ):
            try:
                value = page.locator(selector).first.get_attribute(attribute, timeout=1500)
                if value:
                    structured[field] = value
            except Exception:
                pass
        sources: list[str] = []
        for selector in ("script[type='application/ld+json']", "script#__NEXT_DATA__"):
            try:
                sources.extend(page.locator(selector).all_text_contents())
            except Exception:
                pass
        for selector in ("[aria-label*='Race' i]", "[aria-label*='Rasse' i]",
                         "[aria-label*='Class' i]", "[aria-label*='Klasse' i]",
                         "[title*='Race' i]", "[title*='Rasse' i]",
                         "[title*='Class' i]", "[title*='Klasse' i]"):
            try:
                locator = page.locator(selector)
                sources.extend(locator.all_text_contents())
                for element in locator.all()[:20]:
                    for attribute in ("aria-label", "title"):
                        value = element.get_attribute(attribute, timeout=1000)
                        if value:
                            sources.append(value)
            except Exception:
                pass
        try:
            sources.append(page.locator("body").inner_text(timeout=3000))
        except Exception:
            pass
        result = extract_armory_character_data(structured)
        fallback = extract_armory_character_data(sources)
        return {
            "race": result["race"] or fallback["race"],
            "className": result["className"] or fallback["className"],
        }

    def _page_character_ready(self, name: str) -> tuple[bool, bool]:
        page = self._page
        if page is None or page.is_closed():
            return False, False
        try:
            url = str(page.url or "")
            title = page.title()
            body = page.locator("body").inner_text(timeout=2000)[:12000]
        except Exception:
            return False, False
        protected = is_armory_protection_content(url, title, body)
        if protected or not url_matches_character_name(url, name):
            return False, protected
        data = self._extract_armory_character_data(page)
        exact_name = bool(re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", f"{title}\n{body}", re.IGNORECASE))
        structural = False
        for selector in ("[data-character-name]", "[data-race]", "[data-class]", "main h1"):
            try:
                if page.locator(selector).count() > 0:
                    structural = True
                    break
            except Exception:
                pass
        return bool(data.get("race") or data.get("className") or (exact_name and structural)), False

    def _wait_for_character_content(self, name: str,
                                    timeout_seconds: float = CHARACTER_READY_TIMEOUT_SECONDS) -> None:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        waiting_emitted = False
        protected_seen = False
        while True:
            if self._batch_cancel.is_set():
                raise RuntimeError(tr("grabber.stop_requested_short"))
            ready, protected = self._page_character_ready(name)
            protected_seen = protected_seen or protected
            if ready:
                return
            if not waiting_emitted:
                self.emit("progress", name=name, message=tr("grabber.waiting_character_content", name=name))
                waiting_emitted = True
            if time.monotonic() >= deadline:
                if protected_seen:
                    raise ArmoryProtectionTimeout(tr("grabber.protection_timeout", name=name))
                raise RuntimeError(tr("grabber.character_content_timeout", name=name))
            page = self._page
            if page is None or page.is_closed():
                raise RuntimeError("TargetClosedError: Browser page was closed")
            try:
                page.wait_for_timeout(500)
            except Exception as exc:
                raise RuntimeError(self._format_error(exc)) from exc

    def _write_armory_diagnostic(self, name: str) -> Path | None:
        page = self._page
        if page is None:
            return None
        path = suite_root_dir() / "data" / "logs" / "armory_dom_diagnostic.log"
        try:
            url = str(page.url or "")
            title = page.title()
            fragments: list[str] = []
            selectors = (
                "[data-race]", "[data-character-race]", "[data-class]", "[data-character-class]",
                "[aria-label*='race' i]", "[aria-label*='rasse' i]",
                "[aria-label*='class' i]", "[aria-label*='klasse' i]",
                "script[type='application/ld+json']", "script#__NEXT_DATA__",
            )
            for selector in selectors:
                try:
                    for item in page.locator(selector).all()[:20]:
                        text = item.inner_text(timeout=1000)[:1000]
                        attrs = [item.get_attribute(key, timeout=500) for key in (
                            "data-race", "data-character-race", "data-class", "data-character-class",
                            "aria-label", "title",
                        )]
                        fragments.append(f"{selector}: {text!r} attrs={attrs!r}")
                except Exception:
                    pass
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} | {name} =====\n")
                handle.write(f"URL: {url[:1000]}\nTitle: {title[:500]}\n")
                handle.write("\n".join(fragments[:80]) + "\n")
            return path
        except Exception:
            return None

    def _attempt_armory_extraction(self, name: str, member_id: str | None,
                                    request_type: str) -> dict | None:
        try:
            if callable(getattr(self._page, "locator", None)):
                self._wait_for_character_content(name)
            data = self._extract_armory_character_data()
            if not data.get("race") and not data.get("className"):
                self._write_armory_diagnostic(name)
                raise ValueError("Race und Class wurden nicht eindeutig erkannt.")
            result = build_portrait_source_output(
                PORTRAIT_SOURCE_ARMORY,
                race=data.get("race"),
                class_name=data.get("className"),
            )
            result.update({
                "memberId": member_id,
                "characterName": name,
                "source": "classicwowarmory",
                "retrievedAt": datetime.now(timezone.utc).isoformat(),
                "requestType": request_type,
            })
            self.emit("armory_data", name=name, result=result)
            return result
        except ArmoryProtectionTimeout as exc:
            self.emit("armory_data_wait_timeout", name=name, member_id=member_id,
                      message=str(exc), request_type=request_type)
            return None
        except Exception as exc:
            self.emit("armory_data_error", name=name, member_id=member_id,
                      message=self._format_error(exc), request_type=request_type)
            return None

    def _read_character_data(self, name: str, region: str, realm: str, game_version: str,
                             preferred_channel: str, wait_after_load: float,
                             member_id: str | None = None, request_type: str = "single",
                             **_unused) -> dict | None:
        capture_mode = str(_unused.get("capture_mode") or "playwright")
        def operation():
            if not self._current_page_is_character(name, region, realm, game_version):
                self._goto(name, region, realm, game_version, preferred_channel, wait_after_load)
            return self._attempt_armory_extraction(name, member_id, request_type)
        return self._run_with_browser_recovery(operation, capture_mode, preferred_channel)

    def _read_data_all(self, records: list[dict], region: str, realm: str,
                       game_version: str, preferred_channel: str,
                       wait_after_load: float, **_unused) -> None:
        self._batch_cancel.clear()
        capture_mode = str(_unused.get("capture_mode") or "playwright")
        total = len(records)
        successes = failures = processed = 0
        cancelled = False
        for index, record in enumerate(records, 1):
            if self._batch_cancel.is_set():
                cancelled = True
                break
            name = str(record.get("characterName") or "")
            self.emit("batch_progress", index=index, total=total, name=name)
            try:
                result = self._read_character_data(
                    name, region, realm, game_version, preferred_channel,
                    wait_after_load, member_id=record.get("memberId"), request_type="batch",
                    capture_mode=capture_mode,
                )
                successes += int(result is not None)
                failures += int(result is None)
            except BrowserBatchStopped:
                cancelled = True
                break
            except Exception as exc:
                failures += 1
                self.emit("armory_data_error", name=name, member_id=record.get("memberId"),
                          message=self._format_error(exc), request_type="batch")
            processed += 1
            if self._batch_cancel.is_set():
                cancelled = True
                break
        self.emit("batch_done", total=total, processed=processed, successes=successes,
                  failures=failures, cancelled=cancelled)

    def _capture_standard_character(self, name: str, region: str, realm: str, game_version: str,
                                    output_dir: str, screen_region, standard_wait_after_open: float,
                                    member_id: str | None = None) -> None:
        reg = normalize_screen_region(screen_region)
        ok, msg = validate_screen_region(reg)
        if not ok:
            raise RuntimeError(msg)
        url = build_armory_url(name, region, realm, game_version)
        if not webbrowser.open(url, new=0, autoraise=True):
            raise RuntimeError("Windows konnte den Standardbrowser nicht oeffnen.")
        self.emit("armory_data_error", name=name, member_id=member_id,
                  message="DOM-Daten sind im Standardbrowser-Modus nicht verfügbar.", request_type="portrait")
        self.emit("progress", name=name, message=f"Standardbrowser geoeffnet: {name}")
        time.sleep(max(1.0, min(60.0, float(standard_wait_after_open))))
        image = capture_screen_region(reg)
        out = Path(output_dir)
        source_dir = app_data_dir() / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        raw_path = source_dir / f"{safe_filename(name)}_source.png"
        try:
            image.save(raw_path, "PNG", optimize=True)
        except PermissionError:
            # A stale/locked diagnostic artifact must not fail an otherwise
            # valid capture; the final portrait is written below.
            raw_path = None
        if not image_object_has_detail(image):
            raise RuntimeError("Der Standardbereich wirkt leer/einfarbig. Ein vorhandenes Portrait wurde nicht ueberschrieben.")
        if not member_id:
            raise RuntimeError("Für die Portraitspeicherung fehlt die Member-ID.")
        dest = out / f"{safe_filename(str(member_id))}.png"
        save_screen_region_portrait(image, dest)
        self.emit(
            "portrait_saved",
            name=name,
            path=str(dest),
            method="Standardbrowser + Standardbereich",
            source_id=PORTRAIT_SOURCE_ARMORY,
            **build_portrait_source_output(
                PORTRAIT_SOURCE_ARMORY, portrait_path=dest,
            ),
        )

    def _capture_character(self, name: str, region: str, realm: str, game_version: str,
                           preferred_channel: str, wait_after_load: float,
                           output_dir: str, crop: dict, navigate: bool = True,
                           capture_mode: str = "playwright", screen_region=None,
                           standard_wait_after_open: float = 6.0,
                           member_id: str | None = None, **_unused) -> None:
        if capture_mode == "standard_browser_region":
            return self._capture_standard_character(
                name, region, realm, game_version, output_dir,
                screen_region, standard_wait_after_open, member_id,
            )
        def operation():
            if navigate and not self._current_page_is_character(name, region, realm, game_version):
                self._goto(name, region, realm, game_version, preferred_channel, wait_after_load)
            self._attempt_armory_extraction(name, member_id, "portrait")
            raw_path, method = self._raw_screenshot(name)
            if not member_id:
                raise RuntimeError("Für die Portraitspeicherung fehlt die Member-ID.")
            dest = Path(output_dir) / f"{safe_filename(str(member_id))}.png"
            crop_portrait(raw_path, dest, crop)
            self.emit(
                "portrait_saved",
                name=name,
                path=str(dest),
                method=method,
                source_id=PORTRAIT_SOURCE_ARMORY,
                **build_portrait_source_output(
                    PORTRAIT_SOURCE_ARMORY, portrait_path=dest,
                ),
            )
        return self._run_with_browser_recovery(operation, capture_mode, preferred_channel)

    def _capture_raw_character(self, name: str, region: str, realm: str, game_version: str,
                               preferred_channel: str, wait_after_load: float,
                               navigate: bool = True, member_id: str | None = None,
                               **_unused) -> None:
        capture_mode = str(_unused.get("capture_mode") or "playwright")
        def operation():
            if navigate and not self._current_page_is_character(name, region, realm, game_version):
                self._goto(name, region, realm, game_version, preferred_channel, wait_after_load)
            self._attempt_armory_extraction(name, member_id, "portrait")
            raw_path, method = self._raw_screenshot(name)
            self.emit("raw_capture", name=name, path=str(raw_path), method=method)
        return self._run_with_browser_recovery(operation, capture_mode, preferred_channel)

    def _capture_all(self, names: list[str], region: str, realm: str, game_version: str,
                     preferred_channel: str, wait_after_load: float,
                     output_dir: str, crop: dict, capture_mode: str = "playwright",
                     screen_region=None, standard_wait_after_open: float = 6.0,
                     character_records: list[dict] | None = None, **_unused) -> None:
        self._batch_cancel.clear()
        total = len(names)
        failures = 0
        successes = 0
        processed = 0
        cancelled = False
        member_ids = {
            str(record.get("characterName") or "").casefold(): record.get("memberId")
            for record in (character_records or [])
        }
        for idx, name in enumerate(names, 1):
            if self._batch_cancel.is_set():
                cancelled = True
                break
            self.emit("batch_progress", index=idx, total=total, name=name)
            try:
                self._capture_character(
                    name=name, region=region, realm=realm, game_version=game_version,
                    preferred_channel=preferred_channel, wait_after_load=wait_after_load,
                    output_dir=output_dir, crop=crop, navigate=True,
                    capture_mode=capture_mode, screen_region=screen_region,
                    standard_wait_after_open=standard_wait_after_open,
                    member_id=member_ids.get(name.casefold()),
                )
                successes += 1
            except BrowserBatchStopped:
                cancelled = True
                break
            except Exception as exc:
                failures += 1
                self.emit("item_error", name=name, message=str(exc))
            processed += 1
            if self._batch_cancel.is_set():
                cancelled = True
                break
        self.emit("batch_done", total=total, processed=processed, successes=successes,
                  failures=failures, cancelled=cancelled)


# The historic class name remains the canonical implementation because the
# protected v0.1.2 browser contract is statically verified by suite_tests.
ArmoryBrowserWorker = BrowserWorker


def create_portrait_source_worker(source_id: object, event_queue: queue.Queue) -> BrowserWorker:
    """Create the browser implementation for the configured portrait source.

    Only the established Armory source exists today. Keeping this tiny factory
    at the source boundary avoids coupling a future source to either GUI.
    """
    normalized_source_id = normalize_portrait_source_id(source_id)
    if normalized_source_id == PORTRAIT_SOURCE_ARMORY:
        return ArmoryBrowserWorker(event_queue)
    raise ValueError(f"Nicht unterstützte Portraitquelle: {normalized_source_id}")


class CropDialog(tk.Toplevel):
    """Original v0.1.2 crop calibration, now with scrollbars for small screens."""
    def __init__(self, parent, image_path: Path, initial_crop: dict,
                 on_accept: Callable[[dict], None]):
        super().__init__(parent)
        self.title(tr("grabber.crop_title"))
        self.geometry("1000x760")
        self.minsize(560, 420)
        self.transient(parent)
        self.grab_set()
        self.on_accept = on_accept
        self.original = Image.open(image_path).convert("RGB")
        self.initial_crop = clamp_crop(initial_crop)
        self.selection = None
        self.start = None
        self.rect_id = None

        max_w, max_h = 1000, 700
        w, h = self.original.size
        scale = min(max_w / w, max_h / h, 1.0)
        self.display_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        self.display = self.original.resize(self.display_size)
        self.photo = ImageTk.PhotoImage(self.display)

        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)
        msg = tr("grabber.crop_help")
        ttk.Label(outer, text=msg, wraplength=900).grid(row=0,column=0,columnspan=2,sticky="ew",pady=(0,6))
        cf = ttk.Frame(outer); cf.grid(row=1,column=0,columnspan=2,sticky="nsew")
        self.canvas = tk.Canvas(cf, width=self.display_size[0], height=self.display_size[1],
                                highlightthickness=1, highlightbackground="#555")
        vy=ttk.Scrollbar(cf,orient="vertical",command=self.canvas.yview)
        hx=ttk.Scrollbar(cf,orient="horizontal",command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vy.set,xscrollcommand=hx.set,
                              scrollregion=(0,0,self.display_size[0],self.display_size[1]))
        self.canvas.grid(row=0,column=0,sticky="nsew"); vy.grid(row=0,column=1,sticky="ns"); hx.grid(row=1,column=0,sticky="ew")
        cf.rowconfigure(0,weight=1); cf.columnconfigure(0,weight=1)
        self.canvas.create_image(0,0,anchor="nw",image=self.photo)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self._draw_initial()

        row=ttk.Frame(outer); row.grid(row=2,column=0,columnspan=2,sticky="ew",pady=(8,0))
        ttk.Button(row,text=tr("grabber.default"),command=self._reset).pack(side="left")
        ttk.Button(row,text=tr("common.cancel"),command=self.destroy).pack(side="right",padx=(5,0))
        ttk.Button(row,text=tr("grabber.apply_crop"),command=self._accept).pack(side="right")
        outer.rowconfigure(1,weight=1); outer.columnconfigure(0,weight=1)

    def _xy(self,event):
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def _coords_from_crop(self,crop):
        w,h=self.display_size
        return (crop["x1"]*w,crop["y1"]*h,crop["x2"]*w,crop["y2"]*h)
    def _draw_initial(self): self.selection=self._coords_from_crop(self.initial_crop); self._draw_rect()
    def _draw_rect(self):
        if self.rect_id is not None: self.canvas.delete(self.rect_id)
        if self.selection:
            self.rect_id=self.canvas.create_rectangle(*self.selection,outline="yellow",width=3)
    def _press(self,event):
        x,y=self._xy(event); self.start=(x,y); self.selection=(x,y,x,y); self._draw_rect()
    def _drag(self,event):
        if not self.start: return
        w,h=self.display_size; x,y=self._xy(event); x=max(0,min(w,x)); y=max(0,min(h,y))
        self.selection=(self.start[0],self.start[1],x,y); self._draw_rect()
    def _release(self,event): self._drag(event); self.start=None
    def _reset(self): self.selection=self._coords_from_crop(clamp_crop({})); self._draw_rect()
    def _accept(self):
        if not self.selection: return
        x1,y1,x2,y2=self.selection; x1,x2=sorted((x1,x2)); y1,y2=sorted((y1,y2)); w,h=self.display_size
        if x2-x1<10 or y2-y1<10:
            messagebox.showwarning(tr("grabber.crop"),tr("grabber.crop_too_small"),parent=self); return
        crop=clamp_crop({"x1":x1/w,"y1":y1/h,"x2":x2/w,"y2":y2/h})
        self.on_accept(crop); self.destroy()


def portrait_selection_rect(start_x: float, start_y: float, current_x: float, current_y: float,
                            bounds_width: int, bounds_height: int,
                            aspect: float = PORTRAIT_WIDTH / PORTRAIT_HEIGHT) -> tuple[float, float, float, float]:
    """Return a drag rectangle clamped to the canvas and locked to portrait aspect ratio."""
    bw = max(1.0, float(bounds_width))
    bh = max(1.0, float(bounds_height))
    sx = max(0.0, min(bw, float(start_x)))
    sy = max(0.0, min(bh, float(start_y)))
    cx = max(0.0, min(bw, float(current_x)))
    cy = max(0.0, min(bh, float(current_y)))
    dx = cx - sx
    dy = cy - sy
    raw_w = abs(dx)
    raw_h = abs(dy)
    if raw_w <= 0.0 or raw_h <= 0.0:
        return (sx, sy, sx, sy)
    aspect = max(0.01, float(aspect))
    if raw_w / raw_h > aspect:
        height = raw_h
        width = height * aspect
    else:
        width = raw_w
        height = width / aspect
    ex = sx + (width if dx >= 0 else -width)
    ey = sy + (height if dy >= 0 else -height)
    return (min(sx, ex), min(sy, ey), max(sx, ex), max(sy, ey))


def portrait_source_crop_box(selection: tuple[float, float, float, float], source_size: tuple[int, int],
                             scale: float, viewport_left: int, viewport_top: int) -> tuple[int, int, int, int]:
    """Map a selection in preview pixels back to the current high-resolution source image."""
    if scale <= 0:
        raise ValueError("scale must be positive")
    sw, sh = source_size
    x1, y1, x2, y2 = selection
    left_f = (float(viewport_left) + x1) / scale
    top_f = (float(viewport_top) + y1) / scale
    right_f = (float(viewport_left) + x2) / scale
    bottom_f = (float(viewport_top) + y2) / scale
    left = max(0, min(sw - 1, int(round(left_f))))
    top = max(0, min(sh - 1, int(round(top_f))))
    right = max(left + 1, min(sw, int(round(right_f))))
    bottom = max(top + 1, min(sh, int(round(bottom_f))))
    return (left, top, right, bottom)


def portrait_editor_crop_box(
        state: PortraitEditorState,
        selection: tuple[float, float, float, float],
        viewport_size: tuple[int, int] = PORTRAIT_EDITOR_PREVIEW_SIZE,
) -> tuple[int, int, int, int]:
    """Map a fixed editor-scene selection to the current source image."""
    source_width, source_height = state.source_size
    viewport_width, viewport_height = viewport_size
    if min(source_width, source_height, viewport_width, viewport_height) <= 0:
        raise ValueError("Portrait- und Vorschaugröße müssen positiv sein.")
    minimum_zoom, maximum_zoom = PORTRAIT_EDITOR_ZOOM_RANGE
    zoom = max(minimum_zoom, min(maximum_zoom, float(state.zoom)))
    scale = max(viewport_width / source_width, viewport_height / source_height) * zoom
    scaled_width = max(1, round(source_width * scale))
    scaled_height = max(1, round(source_height * scale))
    max_offset_x = max(0.0, (scaled_width - viewport_width) / 2.0)
    max_offset_y = max(0.0, (scaled_height - viewport_height) / 2.0)
    offset_x = max(-max_offset_x, min(max_offset_x, float(state.offset_x)))
    offset_y = max(-max_offset_y, min(max_offset_y, float(state.offset_y)))
    viewport_left = round((scaled_width - viewport_width) / 2.0 - offset_x)
    viewport_top = round((scaled_height - viewport_height) / 2.0 - offset_y)
    viewport_left = max(0, min(max(0, scaled_width - viewport_width), viewport_left))
    viewport_top = max(0, min(max(0, scaled_height - viewport_height), viewport_top))
    return portrait_source_crop_box(
        selection, state.source_size, scale, viewport_left, viewport_top,
    )


class PortraitEditorDialog(tk.Toplevel):
    """Destructive portrait editor: zoom, pan and fixed-aspect drag crop."""
    PREVIEW_SIZE = (320, 560)
    MODE_PAN = "pan"
    MODE_CROP = "crop"

    def __init__(self, parent, source: Path, destination: Path, title: str,
                 on_saved=None):
        super().__init__(parent)
        self.source = Path(source)
        self.destination = Path(destination)
        self.on_saved = on_saved
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self._photo = None
        self._drag = None
        self._crop_drag_start = None
        self._crop_selection = None
        if Image is None or ImageTk is None or ImageOps is None:
            raise RuntimeError("Pillow ist nicht installiert.")
        with Image.open(self.source) as raw:
            self.initial_original = ImageOps.exif_transpose(raw).convert("RGB").copy()
        self.original = self.initial_original.copy()
        self.zoom = tk.DoubleVar(value=1.0)
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.mode = tk.StringVar(value=self.MODE_PAN)
        self.help_var = tk.StringVar()

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, textvariable=self.help_var, wraplength=470, justify="left").pack(anchor="w", pady=(0, 6))
        self.canvas = tk.Canvas(frame, width=self.PREVIEW_SIZE[0], height=self.PREVIEW_SIZE[1],
                                bg="#0e1116", highlightthickness=1, highlightbackground="#596574",
                                cursor="fleur")
        self.canvas.pack()

        mode_row = ttk.Frame(frame)
        mode_row.pack(fill="x", pady=(8, 2))
        ttk.Label(mode_row, text=tr("grabber.portrait_editor_tool")).pack(side="left")
        ttk.Radiobutton(
            mode_row, text=tr("grabber.portrait_editor_pan_zoom"), variable=self.mode, value=self.MODE_PAN,
            command=self._mode_changed,
        ).pack(side="left", padx=(10, 4))
        ttk.Radiobutton(
            mode_row, text=tr("grabber.portrait_editor_crop"), variable=self.mode, value=self.MODE_CROP,
            command=self._mode_changed,
        ).pack(side="left", padx=4)

        zoom_row = ttk.Frame(frame)
        zoom_row.pack(fill="x", pady=(4, 4))
        ttk.Label(zoom_row, text=tr("common.zoom")).pack(side="left")
        ttk.Scale(zoom_row, from_=1.0, to=4.0, variable=self.zoom,
                  command=lambda _v: self._redraw()).pack(side="left", fill="x", expand=True, padx=8)
        self.zoom_label = ttk.Label(zoom_row, width=6)
        self.zoom_label.pack(side="right")
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text=tr("common.reset"), command=self._reset).pack(side="left")
        ttk.Button(buttons, text=tr("common.cancel"), command=self.destroy).pack(side="right")
        ttk.Button(buttons, text=tr("common.apply"), command=self._save).pack(side="right", padx=(0, 6))
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)
        self.canvas.bind("<MouseWheel>", self._mousewheel)
        self.canvas.bind("<Button-4>", lambda _e: self._zoom_step(0.12))
        self.canvas.bind("<Button-5>", lambda _e: self._zoom_step(-0.12))
        self._reset()

    def _base_scale(self):
        ow, oh = self.original.size
        pw, ph = self.PREVIEW_SIZE
        return max(pw / ow, ph / oh)

    def _scaled_image(self):
        scale = self._base_scale() * max(1.0, float(self.zoom.get()))
        size = (max(1, round(self.original.width * scale)), max(1, round(self.original.height * scale)))
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        return self.original.resize(size, resampling), scale

    def _clamp_offsets(self, scaled):
        pw, ph = self.PREVIEW_SIZE
        max_x = max(0.0, (scaled.width - pw) / 2)
        max_y = max(0.0, (scaled.height - ph) / 2)
        self.offset_x = max(-max_x, min(max_x, self.offset_x))
        self.offset_y = max(-max_y, min(max_y, self.offset_y))

    def _render_geometry(self):
        scaled, scale = self._scaled_image()
        self._clamp_offsets(scaled)
        pw, ph = self.PREVIEW_SIZE
        left = int(round((scaled.width - pw) / 2 - self.offset_x))
        top = int(round((scaled.height - ph) / 2 - self.offset_y))
        left = max(0, min(max(0, scaled.width - pw), left))
        top = max(0, min(max(0, scaled.height - ph), top))
        return scaled, scale, left, top

    def _render_preview(self):
        scaled, _scale, left, top = self._render_geometry()
        pw, ph = self.PREVIEW_SIZE
        return scaled.crop((left, top, left + pw, top + ph))

    def _redraw(self):
        preview = self._render_preview()
        self._photo = ImageTk.PhotoImage(preview, master=self)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self.canvas.create_rectangle(1, 1, self.PREVIEW_SIZE[0]-2, self.PREVIEW_SIZE[1]-2,
                                     outline="#d7b56d", width=2)
        if self._crop_selection:
            x1, y1, x2, y2 = self._crop_selection
            self.canvas.create_rectangle(x1, y1, x2, y2, outline="#ffffff", width=3)
            self.canvas.create_rectangle(x1 + 3, y1 + 3, x2 - 3, y2 - 3, outline="#d7b56d", width=1)
        self.zoom_label.configure(text=f"{float(self.zoom.get()):.2f}×")

    def _mode_changed(self):
        self._drag = None
        self._crop_drag_start = None
        self._crop_selection = None
        if self.mode.get() == self.MODE_CROP:
            self.canvas.configure(cursor="crosshair")
            self.help_var.set(tr("grabber.portrait_editor_crop_help"))
        else:
            self.canvas.configure(cursor="fleur")
            self.help_var.set(tr("grabber.portrait_editor_pan_help"))
        self._redraw()

    def _reset(self):
        self.original = self.initial_original.copy()
        self.zoom.set(1.0)
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.mode.set(self.MODE_PAN)
        self._drag = None
        self._crop_drag_start = None
        self._crop_selection = None
        self._mode_changed()

    def _drag_start(self, event):
        if self.mode.get() == self.MODE_CROP:
            self._crop_drag_start = (event.x, event.y)
            self._crop_selection = None
            self._redraw()
            return
        self._drag = (event.x, event.y, self.offset_x, self.offset_y)

    def _drag_move(self, event):
        if self.mode.get() == self.MODE_CROP:
            if not self._crop_drag_start:
                return
            sx, sy = self._crop_drag_start
            self._crop_selection = portrait_selection_rect(
                sx, sy, event.x, event.y, self.PREVIEW_SIZE[0], self.PREVIEW_SIZE[1]
            )
            self._redraw()
            return
        if not self._drag:
            return
        x, y, ox, oy = self._drag
        self.offset_x = ox + (event.x - x)
        self.offset_y = oy + (event.y - y)
        self._redraw()

    def _drag_end(self, event):
        if self.mode.get() != self.MODE_CROP:
            self._drag = None
            return
        if not self._crop_drag_start:
            return
        sx, sy = self._crop_drag_start
        self._crop_selection = portrait_selection_rect(
            sx, sy, event.x, event.y, self.PREVIEW_SIZE[0], self.PREVIEW_SIZE[1]
        )
        self._crop_drag_start = None
        x1, y1, x2, y2 = self._crop_selection
        if x2 - x1 < 20 or y2 - y1 < 35:
            self._crop_selection = None
            self._redraw()
            return
        self._apply_crop_selection()

    def _apply_crop_selection(self):
        if not self._crop_selection:
            return
        _scaled, scale, left, top = self._render_geometry()
        box = portrait_source_crop_box(self._crop_selection, self.original.size, scale, left, top)
        self.original = self.original.crop(box).copy()
        self.zoom.set(1.0)
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._crop_selection = None
        self.mode.set(self.MODE_PAN)
        self._mode_changed()
        self.help_var.set(tr("grabber.portrait_editor_crop_applied"))

    def _zoom_step(self, delta):
        self.zoom.set(max(1.0, min(4.0, float(self.zoom.get()) + delta)))
        self._redraw()

    def _mousewheel(self, event):
        self._zoom_step(0.12 if event.delta > 0 else -0.12)

    def _save(self):
        save_portrait_editor_image(
            self.original,
            self.destination,
            float(self.zoom.get()),
            self.offset_x,
            self.offset_y,
        )
        if callable(self.on_saved):
            self.on_saved(self.destination)
        self.destroy()


class App(tk.Tk):
    """v0.1.2 capture core with a cleaned, tabbed v0.2.0 interface."""
    def __init__(self, initial_names: Optional[list[str]] = None,
                 output_override: Optional[str] = None,
                 initial_characters: Optional[list[dict]] = None,
                 armory_context: Optional[dict] = None,
                 roster_json_path: Optional[str] = None,
                 project_path: Optional[str] = None,
                 session_id: Optional[str] = None):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self._suite_settings_path = suite_root_dir() / "config" / "suite_settings.json"
        self._suite_settings = read_suite_settings(self._suite_settings_path)
        saved_geometry = self._suite_settings.get("grabber_geometry")
        self._work_area = work_area_for_geometry(self, saved_geometry)
        minimum = dynamic_minimum(self._work_area, (760, 520), (640, 480))
        self.minsize(*minimum)
        self.geometry(resolve_geometry(
            saved_geometry, self._work_area, minimum,
        ).as_tk())
        self.header_font_family = load_lifecraft_font(
            suite_root_dir() / "assets" / "fonts" / "LifeCraft_Font.ttf"
        )
        self.config_data = load_config()
        self.project_path = Path(project_path).resolve() if project_path else None
        self.session_id = str(session_id or "").strip() or None
        self._session_project_path = self.project_path if self.session_id else None
        self._pending_roster_save_token: str | None = None
        self._pending_roster_save_started = 0.0
        if initial_characters is not None:
            source_records = initial_characters
        else:
            source_records = [
                {"memberId": None, "characterName": name, "race": None, "className": None}
                for name in (initial_names if initial_names is not None else [])
            ]
        self.character_records: dict[str, dict] = {}
        for source in source_records:
            name = str(source.get("characterName") or "").strip()
            if not name or name.casefold() in self.character_records:
                continue
            self.character_records[name.casefold()] = {
                "memberId": str(source.get("memberId") or "").strip() or None,
                "characterName": name,
                "race": _canonical_value(source.get("race"), RACE_NAMES),
                "className": _canonical_value(source.get("className"), CLASS_NAMES),
                "lifeStatus": str(source.get("lifeStatus") or "active").strip().casefold(),
                "deathDate": str(source.get("deathDate") or "").strip(),
                "graveTemplateId": str(source.get("graveTemplateId") or "").strip(),
                "gravestoneTemplate": str(source.get("gravestoneTemplate") or "").strip(),
                "gravestoneCategory": normalize_gravestone_category(
                    source.get("gravestoneCategory")
                ) or "",
                "portraitOffsetX": source.get("portraitOffsetX", 0.0),
                "portraitOffsetY": source.get("portraitOffsetY", 0.0),
                "portraitZoom": source.get("portraitZoom", 1.0),
                "textOffsetX": source.get("textOffsetX", 0.0),
                "textOffsetY": source.get("textOffsetY", 0.0),
                "textScale": source.get("textScale", 1.0),
                "graveyardReset": False,
            }
        if self.project_path is not None:
            migrate_legacy_portraits(
                self.project_path,
                [SimpleNamespace(id=record.get("memberId"), name=record.get("characterName"))
                 for record in self.character_records.values()],
            )
        self.names = [record["characterName"] for record in self.character_records.values()
                      if record.get("lifeStatus") != "dead"]
        self.dead_names = [record["characterName"] for record in self.character_records.values()
                           if record.get("lifeStatus") == "dead"]
        self.roster_json_path = self.project_path or (
            Path(roster_json_path).resolve() if roster_json_path else None
        )
        self.armory_context = dict(armory_context or {})
        self.armory_context["sessionId"] = self.session_id
        self.armory_context.setdefault("region", self.config_data.get("region", DEFAULT_REGION))
        self.armory_context.setdefault("realm", self.config_data.get("realm", DEFAULT_REALM))
        self.armory_context.setdefault("gameVersion", self.config_data.get("game_version", DEFAULT_GAME_VERSION))
        self.armory_results: dict[str, dict] = {}
        self.events: queue.Queue = queue.Queue()
        self.worker = create_portrait_source_worker(
            self.config_data.get("portrait_source"), self.events,
        )
        self.worker.start()
        self.status_by_name: dict[str, str] = {}
        # Friedhof edits are kept as local drafts until the user explicitly saves.
        self._graveyard_edit_sessions: dict[str, dict] = {}
        self.batch_running = False
        # BEGIN LEGACY_GUILD_ROSTER_FETCH_STATE
        self.guild_fetch_running = False
        # END LEGACY_GUILD_ROSTER_FETCH_STATE
        self._build_ui()
        self._update_project_controls()
        self._populate_tree()
        self.after(100, self._poll_events)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._log(tr("grabber.app_ready", app=APP_NAME, version=APP_VERSION))

    def _record_for_name(self, name: str) -> dict:
        key = name.casefold()
        if key not in self.character_records:
            self.character_records[key] = {
                "memberId": None, "characterName": name, "race": None, "className": None,
                "lifeStatus": "active", "deathDate": "", "graveTemplateId": "",
                "gravestoneTemplate": "", "portraitOffsetX": 0.0, "portraitOffsetY": 0.0,
                "portraitZoom": 1.0, "textOffsetX": 0.0, "textOffsetY": 0.0,
                "textScale": 1.0, "graveyardReset": False,
            }
        return self.character_records[key]

    def _records_for_names(self, names: Iterable[str]) -> list[dict]:
        return [self._record_for_name(name) for name in names]

    def _build_ui(self):
        # v0.2.0 cleanup: the daily workflow is separated from crop and technical settings.
        # Every content-heavy tab has its own vertical + horizontal scrolling container.
        self._banner_photo = None
        self._banner_image = None
        self._banner_source_size = None
        self._banner_rendered_size = None
        self._banner_scaled_size = None
        self._banner_resize_job = None
        self.banner_canvas = tk.Canvas(
            self, height=BANNER_HEADER_HEIGHT, bg="#78151b",
            highlightthickness=0, borderwidth=0,
        )
        self.banner_canvas.pack(fill="x")
        self._banner_item = self.banner_canvas.create_image(0, 0, anchor="nw", state="hidden")
        self._header_title_item = self.banner_canvas.create_text(
            10, BANNER_HEADER_HEIGHT // 2, anchor="w",
            text=f"{tr('grabber.title')} v{APP_VERSION}",
            font=(self.header_font_family, 22), fill="#ffffff",
        )
        self.header_summary_var = tk.StringVar(value="")
        self._header_summary_item = self.banner_canvas.create_text(
            1170, BANNER_HEADER_HEIGHT // 2, anchor="e", text="",
            font=("Segoe UI", 10), fill="#ffffff",
        )
        self.header_summary_var.trace_add(
            "write", lambda *_args: self.banner_canvas.itemconfigure(
                self._header_summary_item, text=self.header_summary_var.get(),
            )
        )
        self.banner_canvas.bind("<Configure>", self._banner_resize_requested)
        self._load_banner()

        project_status = ttk.Frame(self, padding=(10, 3))
        project_status.pack(fill="x")
        self.project_status_var = tk.StringVar(value="")
        self.project_status_label = ttk.Label(
            project_status, textvariable=self.project_status_var, anchor="w",
        )
        self.project_status_label.pack(fill="x")
        self._project_tooltip_window = None
        self._project_tooltip_text = ""
        self.project_status_label.bind("<Enter>", self._show_project_tooltip)
        self.project_status_label.bind("<Leave>", self._hide_project_tooltip)
        self._refresh_project_status()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # ---------- Portraits: normal daily workflow ----------
        self.portrait_scroll = ScrollableFrame(self.notebook)
        self.notebook.add(self.portrait_scroll, text=tr("grabber.overview"))
        proot = self.portrait_scroll.content

        overview = ttk.LabelFrame(proot, text=tr("grabber.overview"), padding=8)
        overview.pack(fill="x", padx=8, pady=(8, 5))
        self.summary_var = tk.StringVar(value="")
        ttk.Label(overview, textvariable=self.summary_var, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.output_folder_btn = ttk.Button(
            overview, text=tr("grabber.output_folder"), command=self._open_output_folder,
        )
        self.output_folder_btn.pack(side="right")

        primary = ttk.LabelFrame(proot, text=tr("grabber.create_section"), padding=8)
        primary.pack(fill="x", padx=8, pady=5)
        self.open_btn = ttk.Button(primary, text=tr("grabber.open_browser"), command=self._open_selected)
        self.open_btn.grid(row=0, column=0, sticky="ew", padx=3, pady=3)
        self.single_btn = ttk.Button(primary, text=tr("grabber.create_portrait"), command=self._capture_selected)
        self.single_btn.grid(row=0, column=1, sticky="ew", padx=3, pady=3)
        self.missing_btn = ttk.Button(primary, text=tr("grabber.create_missing"), command=self._capture_missing)
        self.missing_btn.grid(row=0, column=2, sticky="ew", padx=3, pady=3)
        self.all_btn = ttk.Button(primary, text=tr("grabber.create_all"), command=self._capture_all)
        self.all_btn.grid(row=0, column=3, sticky="ew", padx=3, pady=3)
        self.stop_btn = ttk.Button(primary, text=tr("grabber.stop"), command=self._request_stop, state="disabled")
        self.stop_btn.grid(row=0, column=4, sticky="ew", padx=3, pady=3)
        self.read_data_btn = ttk.Button(primary, text=tr("grabber.read_data"), command=self._read_selected_data)
        self.read_data_btn.grid(row=1, column=0, columnspan=2, sticky="ew", padx=3, pady=3)
        self.read_missing_data_btn = ttk.Button(primary, text=tr("grabber.read_missing_data"), command=self._read_missing_data)
        self.read_missing_data_btn.grid(row=1, column=2, columnspan=2, sticky="ew", padx=3, pady=3)
        for c in range(5):
            primary.columnconfigure(c, weight=1)

        roster = ttk.LabelFrame(proot, text=tr("grabber.character_list"), padding=8)
        roster.pack(fill="x", padx=8, pady=5)
        roster_actions = [
            (tr("grabber.open_project"), self._open_project),
            (tr("grabber.import_list"), self._import_names),
            (tr("grabber.import_wcl"), self._import_wcl_csv),
            (tr("grabber.add_name"), self._add_name),
            (tr("grabber.remove"), self._remove_selected),
            (tr("grabber.save_guild_list"), self._save_guild_list),
        ]
        self.roster_action_buttons = []
        for i, (text, cmd) in enumerate(roster_actions):
            button = ttk.Button(roster, text=text, command=cmd)
            button.grid(row=0, column=i, sticky="ew", padx=3, pady=3)
            self.roster_action_buttons.append(button)
            roster.columnconfigure(i, weight=1)
        self.save_guild_list_btn = self.roster_action_buttons[-1]
        # BEGIN LEGACY_GUILD_ROSTER_FETCH_UI
        # Intentionally disabled: Armory guild lists also contain low-level characters.
        self.guild_fetch_btn = ttk.Button(
            roster, text=f"{tr('grabber.fetch_guild_roster')} ({tr('grabber.disabled_suffix')})",
            command=self._fetch_guild_roster, state="disabled",
        )
        self.guild_fetch_btn.grid(row=1, column=0, columnspan=6, sticky="ew", padx=3, pady=(6, 3))
        ttk.Label(
            roster,
            text=tr("grabber.guild_fetch_disabled_help"),
            wraplength=900, justify="left",
        ).grid(row=2, column=0, columnspan=6, sticky="w", padx=3, pady=(0, 3))
        # END LEGACY_GUILD_ROSTER_FETCH_UI

        body = ttk.LabelFrame(proot, text=tr("grabber.characters"), padding=6)
        body.pack(fill="both", expand=True, padx=8, pady=5)
        columns = ("name", "race", "class", "status", "portrait")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse", height=13)
        self.tree.heading("name", text=tr("common.character"))
        self.tree.heading("race", text=tr("checker.race"))
        self.tree.heading("class", text=tr("common.class"))
        self.tree.heading("status", text=tr("common.status"))
        self.tree.heading("portrait", text=tr("grabber.portrait_file"))
        self.tree.column("name", width=190, minwidth=120, anchor="w")
        self.tree.column("race", width=120, minwidth=90, anchor="w")
        self.tree.column("class", width=110, minwidth=90, anchor="w")
        self.tree.column("status", width=260, minwidth=170, anchor="w")
        self.tree.column("portrait", width=360, minwidth=220, anchor="w")
        tree_v = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        tree_h = ttk.Scrollbar(body, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_v.set, xscrollcommand=tree_h.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_v.grid(row=0, column=1, sticky="ns")
        tree_h.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1); body.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _e: self._open_selected())
        self.tree.bind("<<TreeviewSelect>>", self._preview_selection_changed)

        preview = ttk.LabelFrame(body, text=tr("grabber.preview"), padding=8)
        preview.grid(row=0, column=2, rowspan=2, sticky="ns", padx=(10, 0))
        self.preview_name_var = tk.StringVar(value="–")
        ttk.Label(preview, textvariable=self.preview_name_var,
                  font=("Segoe UI", 11, "bold"), anchor="center").pack(fill="x", pady=(0, 6))
        self.preview_image_frame = tk.Frame(preview, width=250, height=250, bg="#111820")
        self.preview_image_frame.pack()
        self.preview_image_frame.pack_propagate(False)
        self.preview_image_label = tk.Label(
            self.preview_image_frame, bg="#111820", fg="#c7d0d9",
            text=tr("grabber.no_portrait_available"), justify="center",
        )
        self.preview_image_label.pack(fill="both", expand=True)
        self.preview_status_var = tk.StringVar(value=tr("grabber.no_portrait_available"))
        ttk.Label(preview, textvariable=self.preview_status_var, anchor="center").pack(fill="x", pady=(6, 4))
        self.manual_portrait_btn = ttk.Button(
            preview, text=tr("grabber.manual_portrait"), command=self._manual_portrait_selected,
        )
        self.manual_portrait_btn.pack(fill="x", pady=(4, 0))
        self.edit_portrait_btn = ttk.Button(
            preview, text=tr("grabber.edit_portrait"), command=self._edit_selected_portrait,
        )
        self.edit_portrait_btn.pack(fill="x", pady=(4, 0))
        self.remove_portrait_btn = ttk.Button(
            preview, text=tr("grabber.remove_portrait"), command=self._remove_selected_portrait,
        )
        self.remove_portrait_btn.pack(fill="x", pady=(4, 0))
        self._preview_photo = None
        self._preview_rendered_size = None

        status = ttk.LabelFrame(proot, text=tr("common.status"), padding=6)
        status.pack(fill="x", padx=8, pady=(5, 8))
        self.progress = ttk.Progressbar(status, mode="determinate")
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        self.status_var = tk.StringVar(value=tr("grabber.ready_playwright"))
        ttk.Label(status, textvariable=self.status_var, anchor="w", wraplength=1000).grid(row=1, column=0, sticky="ew")
        self.show_log_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(status, text=tr("grabber.show_log"), variable=self.show_log_var, command=self._toggle_log).grid(row=1, column=1, sticky="e", padx=(8,0))
        self.log_frame = ttk.Frame(status)
        self.log_text = tk.Text(self.log_frame, height=7, wrap="none", state="disabled")
        log_v = ttk.Scrollbar(self.log_frame, orient="vertical", command=self.log_text.yview)
        log_h = ttk.Scrollbar(self.log_frame, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=log_v.set, xscrollcommand=log_h.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_v.grid(row=0, column=1, sticky="ns")
        log_h.grid(row=1, column=0, sticky="ew")
        self.log_frame.rowconfigure(0, weight=1); self.log_frame.columnconfigure(0, weight=1)
        status.columnconfigure(0, weight=1)

        # ---------- Friedhof: locked by default, explicit reset workflow ----------
        self.graveyard_scroll = ScrollableFrame(self.notebook)
        self.notebook.add(self.graveyard_scroll, text=tr("grabber.graveyard_tab"))
        groot = self.graveyard_scroll.content
        gy_info = ttk.LabelFrame(groot, text=tr("grabber.graveyard_tab"), padding=10)
        gy_info.pack(fill="x", padx=8, pady=(8, 5))
        ttk.Label(gy_info, text=tr("grabber.graveyard_help"), wraplength=980, justify="left").pack(anchor="w", fill="x")

        # v0.8.4 local test: the graveyard keeps the character list on the left and
        # centralizes all selected-character editing on a fixed detail panel on the right.
        gy_main = ttk.Frame(groot)
        gy_main.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        gy_main.rowconfigure(0, weight=1)
        gy_main.columnconfigure(0, weight=1)

        gy_body = ttk.LabelFrame(gy_main, text=tr("grabber.graveyard_characters"), padding=8)
        gy_body.grid(row=0, column=0, sticky="nsew")
        self.graveyard_tree = ttk.Treeview(gy_body, columns=("name","status","portrait","stone"),
                                            show="headings", selectmode="browse", height=12)
        for key, text, width in (("name",tr("common.character"),170),("status",tr("common.status"),150),
                                 ("portrait",tr("common.portrait"),235),("stone",tr("common.gravestone"),210)):
            self.graveyard_tree.heading(key, text=text); self.graveyard_tree.column(key,width=width,anchor="w")
        gy_v = ttk.Scrollbar(gy_body, orient="vertical", command=self.graveyard_tree.yview)
        gy_h = ttk.Scrollbar(gy_body, orient="horizontal", command=self.graveyard_tree.xview)
        self.graveyard_tree.configure(yscrollcommand=gy_v.set, xscrollcommand=gy_h.set)
        self.graveyard_tree.grid(row=0,column=0,sticky="nsew"); gy_v.grid(row=0,column=1,sticky="ns"); gy_h.grid(row=1,column=0,sticky="ew")
        gy_body.rowconfigure(0,weight=1); gy_body.columnconfigure(0,weight=1)

        # Right-hand graveyard detail area. Keep it intentionally simple: the user
        # sees the final/current gravestone and enters one dedicated editor for every
        # visual change (portrait, template and text positioning). The whole pane is
        # independently scrollable so the large preview remains usable on smaller screens.
        gy_main.columnconfigure(1, minsize=520)
        self.gy_detail_scroll = ScrollableFrame(gy_main)
        self.gy_detail_scroll.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.gy_detail_scroll.configure(width=520)
        gy_detail = ttk.LabelFrame(self.gy_detail_scroll.content, text=tr("grabber.graveyard_editor"), padding=10)
        gy_detail.pack(fill="both", expand=True)
        gy_detail.columnconfigure(0, weight=1)
        self.gy_detail_frame = gy_detail

        self.gy_detail_name_var = tk.StringVar(value=tr("grabber.graveyard_no_character"))
        ttk.Label(gy_detail, textvariable=self.gy_detail_name_var,
                  font=("Segoe UI", 12, "bold"), anchor="center").grid(
            row=0, column=0, sticky="ew", pady=(0, 4),
        )
        self.gy_detail_status_var = tk.StringVar(value="–")
        ttk.Label(gy_detail, textvariable=self.gy_detail_status_var, anchor="center").grid(
            row=1, column=0, sticky="ew", pady=(0, 6),
        )
        self.gy_open_btn = ttk.Button(
            gy_detail, text=tr("grabber.graveyard_open_edit"), command=self._graveyard_begin_edit_selected,
        )
        self.gy_open_btn.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        stone_box = ttk.LabelFrame(gy_detail, text=tr("grabber.graveyard_current_stone"), padding=6)
        stone_box.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.gy_stone_preview = tk.Canvas(
            stone_box, width=450, height=613, bg="#111820",
            highlightthickness=0, bd=0, relief="flat",
        )
        self.gy_stone_preview.pack(anchor="center")
        self.gy_stone_info_var = tk.StringVar(value="–")
        ttk.Label(stone_box, textvariable=self.gy_stone_info_var, justify="center", anchor="center",
                  wraplength=470).pack(fill="x", pady=(6, 4))
        self.gy_adjust_btn = ttk.Button(stone_box, text=tr("grabber.graveyard_edit_stone"), command=self._graveyard_adjust_selected)
        self.gy_adjust_btn.pack(fill="x")

        action_box = ttk.Frame(gy_detail)
        action_box.grid(row=4, column=0, sticky="ew", pady=(2, 0))
        action_box.columnconfigure(0, weight=1)
        action_box.columnconfigure(1, weight=1)
        self.gy_discard_btn = ttk.Button(action_box, text=tr("grabber.graveyard_discard"), command=self._graveyard_discard_edit_selected)
        self.gy_discard_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3), pady=(0, 5))
        self.gy_save_btn = ttk.Button(action_box, text=tr("grabber.graveyard_save_lock"), command=self._graveyard_save_selected)
        self.gy_save_btn.grid(row=0, column=1, sticky="ew", padx=(3, 0), pady=(0, 5))
        self.gy_reset_btn = ttk.Button(action_box, text=tr("grabber.graveyard_full_reset"), command=self._graveyard_reset_selected)
        self.gy_reset_btn.grid(row=1, column=0, columnspan=2, sticky="ew")

        self._gy_stone_photo = None
        self.graveyard_tree.bind("<<TreeviewSelect>>", lambda _e: self._update_graveyard_buttons())
        self._populate_graveyard_tree()

        # ---------- Ausschnitt: both calibration systems ----------
        self.crop_scroll = ScrollableFrame(self.notebook)
        self.notebook.add(self.crop_scroll, text=tr("grabber.crop"))
        croot = self.crop_scroll.content
        classic = ttk.LabelFrame(croot, text=tr("grabber.playwright_crop"), padding=10)
        classic.pack(fill="x", padx=8, pady=(8,5))
        ttk.Label(classic, text=tr("grabber.playwright_crop_help"),
                  wraplength=920, justify="left").pack(anchor="w", fill="x", pady=(0,8))
        ttk.Button(classic, text=tr("grabber.calibrate"), command=self._calibrate_selected).pack(anchor="w")

        standard = ttk.LabelFrame(croot, text=tr("grabber.standard_crop"), padding=10)
        standard.pack(fill="x", padx=8, pady=5)
        ttk.Label(standard, text=tr("grabber.standard_crop_help"), wraplength=920, justify="left").pack(anchor="w", fill="x", pady=(0,8))
        reg = normalize_screen_region(self.config_data.get("screen_region", {}))
        self.screen_x_var = tk.IntVar(value=reg[0]); self.screen_y_var = tk.IntVar(value=reg[1])
        self.screen_w_var = tk.IntVar(value=reg[2]); self.screen_h_var = tk.IntVar(value=reg[3])
        self.region_text_var = tk.StringVar(); self._refresh_region_text()
        region_controls = ttk.Frame(standard)
        region_controls.pack(fill="x")
        ttk.Label(region_controls, text=tr("grabber.saved_region")).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Label(region_controls, textvariable=self.region_text_var).grid(row=0, column=1, columnspan=2, sticky="w", padx=(8,0), pady=3)
        ttk.Button(region_controls, text=tr("grabber.set_region"), command=self._set_default_region).grid(row=1, column=0, sticky="ew", padx=(0,4), pady=4)
        ttk.Button(region_controls, text=tr("grabber.test_region"), command=self._test_default_region).grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(region_controls, text=tr("grabber.reset"), command=self._reset_default_region).grid(row=1, column=2, sticky="ew", padx=(4,0), pady=4)
        for c in range(3): region_controls.columnconfigure(c, weight=1)

        # ---------- Einstellungen: technical/rare options ----------
        self.settings_scroll = ScrollableFrame(self.notebook)
        self.notebook.add(self.settings_scroll, text=tr("grabber.settings"))
        sroot = self.settings_scroll.content
        general = ttk.LabelFrame(sroot, text=tr("grabber.armory_output"), padding=10)
        general.pack(fill="x", padx=8, pady=(8,5))
        ttk.Label(general, text="Region").grid(row=0, column=0, sticky="w")
        self.region_var = tk.StringVar(value=self.config_data.get("region", DEFAULT_REGION))
        ttk.Entry(general, textvariable=self.region_var, width=10).grid(row=1, column=0, sticky="ew", padx=(0,6), pady=4)
        ttk.Label(general, text="Realm").grid(row=0, column=1, sticky="w")
        self.realm_var = tk.StringVar(value=self.config_data.get("realm", DEFAULT_REALM))
        ttk.Entry(general, textvariable=self.realm_var, width=20).grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        ttk.Label(general, text=tr("grabber.game_version")).grid(row=0, column=2, sticky="w")
        self.game_var = tk.StringVar(value=self.config_data.get("game_version", DEFAULT_GAME_VERSION))
        ttk.Entry(general, textvariable=self.game_var, width=16).grid(row=1, column=2, sticky="ew", padx=6, pady=4)
        # BEGIN LEGACY_GUILD_ROSTER_FETCH_SETTINGS_UI
        ttk.Label(general, text=f"{tr('grabber.guild_name')} ({tr('grabber.disabled_suffix')})").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(8,0)
        )
        self.guild_var = tk.StringVar(value=self.config_data.get("guild_name", ""))
        self.guild_entry = ttk.Entry(general, textvariable=self.guild_var, state="disabled")
        self.guild_entry.grid(row=3, column=0, columnspan=3, sticky="ew", pady=4)
        # END LEGACY_GUILD_ROSTER_FETCH_SETTINGS_UI
        ttk.Label(general, text=tr("grabber.output_folder")).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8,0))
        project_output = project_portrait_root(self.project_path)
        self.output_var = tk.StringVar(value=str(project_output) if project_output else "")
        ttk.Entry(general, textvariable=self.output_var, state="readonly").grid(row=5, column=0, columnspan=2, sticky="ew", padx=(0,6), pady=4)
        ttk.Button(general, text=tr("grabber.open_project"), command=self._open_project).grid(row=5, column=2, sticky="ew", padx=(6,0), pady=4)
        for c in range(3): general.columnconfigure(c, weight=1)

        modebox = ttk.LabelFrame(sroot, text=tr("grabber.capture_mode"), padding=10)
        modebox.pack(fill="x", padx=8, pady=5)
        mode_value = capture_mode_display(self.config_data.get("capture_mode", "playwright"))
        self.capture_mode_var = tk.StringVar(value=mode_value)
        self.mode_combo = ttk.Combobox(modebox, textvariable=self.capture_mode_var, state="readonly", width=40,
                                       values=(CAPTURE_MODE_PLAYWRIGHT, CAPTURE_MODE_STANDARD))
        self.mode_combo.grid(row=0, column=0, sticky="ew", padx=(0,8), pady=4)
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._mode_changed())
        ttk.Label(modebox, text=tr("grabber.wait_seconds")).grid(row=0, column=1, sticky="e", padx=(8,4))
        self.standard_wait_var = tk.DoubleVar(value=float(self.config_data.get("standard_wait_after_open", 6.0)))
        ttk.Spinbox(modebox, from_=1, to=60, increment=0.5, textvariable=self.standard_wait_var, width=8).grid(row=0, column=2, sticky="w", pady=4)
        modebox.columnconfigure(0, weight=1)

        language_box = ttk.LabelFrame(sroot, text=tr("language.label"), padding=10)
        language_box.pack(fill="x", padx=8, pady=5)
        self.language_var = tk.StringVar(value=language_display_values()[0 if get_language() == "de" else 1])
        language_combo = ttk.Combobox(language_box, textvariable=self.language_var,
                                      values=language_display_values(), state="readonly")
        language_combo.pack(anchor="w")
        language_combo.bind("<<ComboboxSelected>>", self._language_changed)

        diag = ttk.LabelFrame(sroot, text=tr("grabber.diagnostics"), padding=10)
        diag.pack(fill="x", padx=8, pady=5)
        ttk.Button(diag, text=tr("grabber.browser_test"), command=self._test_browser).pack(side="left")
        ttk.Label(diag, text="  " + tr("grabber.browser_order"), wraplength=760).pack(side="left", padx=(8,0))

        note = ttk.LabelFrame(sroot, text=tr("grabber.notes"), padding=10)
        note.pack(fill="x", padx=8, pady=(5,8))
        info = tr("grabber.settings_help")
        info_text = tk.Text(note, height=5, wrap="word")
        info_v = ttk.Scrollbar(note, orient="vertical", command=info_text.yview)
        info_text.configure(yscrollcommand=info_v.set)
        info_text.grid(row=0, column=0, sticky="nsew"); info_v.grid(row=0, column=1, sticky="ns")
        note.rowconfigure(0, weight=1); note.columnconfigure(0, weight=1)
        info_text.insert("1.0", info); info_text.configure(state="disabled")

        self.review_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.review_frame, text=tr("grabber.gravestone_review"))
        self._embedded_review_app = None
        self.review_placeholder = ttk.Frame(self.review_frame, padding=14)
        self.review_placeholder.pack(fill="both", expand=True)
        ttk.Label(
            self.review_placeholder, text=tr("grabber.gravestone_review_help"),
            wraplength=980, justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 10))
        self.review_candidates_var = tk.StringVar(value=tr("grabber.gravestone_candidates", count=0))
        self.review_accepted_var = tk.StringVar(value=tr("grabber.gravestone_accepted", count=0))
        self.review_approved_var = tk.StringVar(value=tr("grabber.gravestone_approved", count=0))
        self.review_rejected_var = tk.StringVar(value=tr("grabber.gravestone_rejected", count=0))
        ttk.Label(self.review_placeholder, textvariable=self.review_candidates_var).pack(anchor="w")
        ttk.Label(self.review_placeholder, textvariable=self.review_accepted_var).pack(anchor="w")
        ttk.Label(self.review_placeholder, textvariable=self.review_approved_var).pack(anchor="w")
        ttk.Label(self.review_placeholder, textvariable=self.review_rejected_var).pack(anchor="w")
        review_actions = ttk.Frame(self.review_placeholder)
        review_actions.pack(fill="x", pady=(12, 0))
        ttk.Button(
            review_actions, text=tr("grabber.gravestone_review_open"),
            command=self._ensure_embedded_gravestone_review,
        ).pack(side="left")
        ttk.Button(
            review_actions, text=tr("grabber.gravestone_candidates_open"),
            command=self._open_gravestone_candidates,
        ).pack(side="left", padx=6)
        ttk.Button(
            review_actions, text=tr("grabber.gravestone_review_refresh"),
            command=self._refresh_gravestone_review_counts,
        ).pack(side="left")
        self.notebook.bind("<<NotebookTabChanged>>", self._notebook_tab_changed, add="+")
        self._refresh_gravestone_review_counts()

        self._mode_changed(save=False)

    def _language_changed(self, _event=None):
        language = language_from_display(self.language_var.get())
        if language == get_language():
            return
        set_language(language)
        messagebox.showinfo(tr("language.restart_title"), tr("language.restart_message"), parent=self)

    def _toggle_log(self):
        if self.show_log_var.get():
            self.log_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(6,0))
        else:
            self.log_frame.grid_remove()

    def _log(self, message: str) -> None:
        if not hasattr(self, "log_text"):
            return
        stamp = time.strftime("%H:%M:%S")
        try:
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"[{stamp}] {message}\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        except tk.TclError:
            pass

    def _load_banner(self) -> None:
        self._banner_photo = None
        self._banner_image = None
        self._banner_source_size = None
        self._banner_rendered_size = None
        self._banner_scaled_size = None
        if Image is None or ImageTk is None or ImageOps is None:
            self.banner_canvas.itemconfigure(self._banner_item, image="", state="hidden")
            return
        try:
            with Image.open(grabber_banner_path()) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB") if ImageOps else raw.convert("RGB")
                self._banner_source_size = image.size
                self._banner_image = image.copy()
            self.after_idle(self._render_banner_cover)
        except Exception:
            self._banner_image = None
            self.banner_canvas.itemconfigure(self._banner_item, image="", state="hidden")

    def _banner_resize_requested(self, event) -> None:
        if self._banner_resize_job is not None:
            self.after_cancel(self._banner_resize_job)
        self._banner_resize_job = self.after(
            60, lambda width=event.width, height=event.height:
            self._render_banner_cover(width, height),
        )

    def _render_banner_cover(self, width: int | None = None, height: int | None = None) -> None:
        self._banner_resize_job = None
        width = int(width or self.banner_canvas.winfo_width())
        height = int(height or self.banner_canvas.winfo_height())
        if width <= 1 or height <= 1:
            return
        self.banner_canvas.coords(self._header_title_item, 10, height // 2)
        self.banner_canvas.coords(self._header_summary_item, width - 10, height // 2)
        if self._banner_image is None or Image is None or ImageTk is None or ImageOps is None:
            self.banner_canvas.itemconfigure(self._banner_item, image="", state="hidden")
            return
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        rendered = ImageOps.fit(
            self._banner_image, (width, height), method=resampling,
            centering=BANNER_FOCAL_POINT,
        )
        self._banner_photo = ImageTk.PhotoImage(rendered, master=self)
        self._banner_rendered_size = (width, height)
        self._banner_scaled_size = cover_scale_size(self._banner_source_size, (width, height))
        self.banner_canvas.itemconfigure(
            self._banner_item, image=self._banner_photo, state="normal",
        )
        self.banner_canvas.coords(self._banner_item, 0, 0)
        self.banner_canvas.tag_raise(self._header_title_item)
        self.banner_canvas.tag_raise(self._header_summary_item)

    def _show_portrait_preview(self, name: str | None) -> None:
        self._preview_photo = None
        self._preview_rendered_size = None
        self.preview_name_var.set(name or "–")
        portrait = self._existing_portrait(name) if name else None
        if Image is None or ImageTk is None or portrait is None or not portrait.is_file():
            self.preview_status_var.set(tr("grabber.no_portrait_available"))
            self.preview_image_label.configure(
                image="", text=tr("grabber.no_portrait_available"),
            )
            return
        try:
            with Image.open(portrait) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB") if ImageOps else raw.convert("RGB")
                size = proportional_fit_size(image.size, (250, 250))
                resampling = getattr(Image, "Resampling", Image).LANCZOS
                rendered = image.resize(size, resampling)
            self._preview_photo = ImageTk.PhotoImage(rendered, master=self)
            self._preview_rendered_size = size
            self.preview_image_label.configure(image=self._preview_photo, text="")
            self.preview_status_var.set(tr("grabber.portrait_available"))
        except Exception:
            self._preview_photo = None
            self.preview_status_var.set(tr("grabber.no_portrait_available"))
            self.preview_image_label.configure(
                image="", text=tr("grabber.no_portrait_available"),
            )

    def _preview_selection_changed(self, _event=None) -> None:
        self._show_portrait_preview(self._selected_tree_name_no_dialog())

    def _mode_changed(self, save: bool = True):
        if save:
            self._save_settings()
        mode_text = capture_mode_display(capture_mode_from_display(self.capture_mode_var.get()))
        if hasattr(self, "status_var"):
            self.status_var.set(tr("grabber.mode_status", mode=mode_text))
        if hasattr(self, "summary_var"):
            self._refresh_summary()
        if save:
            self._log(tr("grabber.mode_status", mode=mode_text))

    def _refresh_region_text(self):
        reg = (int(self.screen_x_var.get()), int(self.screen_y_var.get()), int(self.screen_w_var.get()), int(self.screen_h_var.get()))
        ok, _ = validate_screen_region(reg)
        self.region_text_var.set(f"X={reg[0]}, Y={reg[1]}, {reg[2]}x{reg[3]} px" if ok else tr("grabber.not_configured"))

    def _current_screen_region(self):
        return (int(self.screen_x_var.get()), int(self.screen_y_var.get()), int(self.screen_w_var.get()), int(self.screen_h_var.get()))

    def _selected_name(self) -> Optional[str]:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(tr("grabber.selection"), tr("grabber.select_first"))
            return None
        return self.tree.item(sel[0], "values")[0]

    def _common_payload(self) -> dict:
        self._save_settings()
        return build_worker_payload(
            region=self.region_var.get(),
            realm=self.realm_var.get(),
            game_version=self.game_var.get(),
            preferred_channel=self.config_data.get("browser_channel", "msedge"),
            wait_after_load=self.config_data.get("wait_after_load", 3.0),
            capture_mode=self.config_data.get("capture_mode", "playwright"),
            screen_region=self._current_screen_region(),
            standard_wait_after_open=self.standard_wait_var.get(),
            source_id=self.config_data.get("portrait_source"),
        )

    def _save_settings(self):
        # BEGIN LEGACY_GUILD_ROSTER_FETCH_SETTINGS_SAVE
        guild_name = self.guild_var.get() if hasattr(self, "guild_var") else self.config_data.get("guild_name", "")
        # END LEGACY_GUILD_ROSTER_FETCH_SETTINGS_SAVE
        try:
            standard_wait_after_open = self.standard_wait_var.get()
        except Exception:
            standard_wait_after_open = None
        config = build_saved_grabber_config(
            self.config_data,
            region=self.region_var.get(),
            realm=self.realm_var.get(),
            game_version=self.game_var.get(),
            guild_name=guild_name,
            crop=self.config_data.get("crop", {}),
            capture_mode=self.capture_mode_var.get(),
            standard_wait_after_open=standard_wait_after_open,
            screen_region=self._current_screen_region(),
        )
        self.config_data.clear()
        self.config_data.update(config)
        save_config(self.config_data)
        if hasattr(self, "summary_var"):
            self._refresh_summary()

    def _portrait_candidates_for_name(self, name: str):
        record = self._record_for_name(name)
        member_id = str(record.get("memberId") or "")
        if member_id and self.project_path is not None:
            yield normal_portrait_path(member_id, self.project_path)

    def _existing_portrait(self, name: str) -> Optional[Path]:
        member_id = str(self._record_for_name(name).get("memberId") or "")
        return existing_portrait_for_member(member_id, self.project_path)

    def _missing_names(self) -> list[str]:
        member_ids = {
            name.casefold(): self._record_for_name(name).get("memberId")
            for name in self.names
        }
        return missing_portrait_names(self.names, self.project_path, member_ids)

    def _refresh_summary(self):
        if not hasattr(self, "summary_var"):
            return
        total = len(self.names)
        missing = len(self._missing_names())
        existing = total - missing
        mode = capture_mode_display(self.config_data.get("capture_mode", "playwright"))
        self.summary_var.set(tr("grabber.summary", total=total, existing=existing, missing=missing))
        if hasattr(self, "header_summary_var"):
            region = self.region_var.get().strip() if hasattr(self, "region_var") else DEFAULT_REGION
            realm = self.realm_var.get().strip() if hasattr(self, "realm_var") else DEFAULT_REALM
            self.header_summary_var.set(f"{region or DEFAULT_REGION} / {realm or DEFAULT_REALM} / Classic Era  ·  {mode}")

    def _populate_tree(self):
        existing_selection = self._selected_tree_name_no_dialog()
        for item in self.tree.get_children(): self.tree.delete(item)
        for name in sorted(self.names, key=str.casefold):
            record = self._record_for_name(name)
            portrait = self._existing_portrait(name)
            status = self.status_by_name.get(name) or (
                tr("grabber.portrait_exists") if portrait else tr("grabber.no_portrait")
            )
            item = self.tree.insert("", "end", values=(
                name, race_display(record.get("race")),
                record.get("className") or tr("common.not_set"), status,
                str(portrait) if portrait else "",
            ))
            if name == existing_selection: self.tree.selection_set(item)
        self._refresh_summary()
        self._show_portrait_preview(existing_selection if existing_selection in self.names else None)

    def _selected_tree_name_no_dialog(self):
        sel = self.tree.selection() if hasattr(self, "tree") else ()
        return self.tree.item(sel[0], "values")[0] if sel else None

    def _choose_output(self):
        self._open_output_folder()

    def _active_output_dir(self) -> Optional[Path]:
        return project_portrait_root(self.project_path)

    def _require_project(self) -> Optional[Path]:
        output = self._active_output_dir()
        if output is None:
            messagebox.showinfo(APP_NAME, tr("grabber.project_required"), parent=self)
        return output

    def _update_project_controls(self) -> None:
        enabled = self.project_path is not None
        for button in (
            self.open_btn, self.single_btn, self.missing_btn, self.all_btn,
            self.read_data_btn, self.read_missing_data_btn, self.output_folder_btn,
        ):
            button.configure(state="normal" if enabled else "disabled")
        for index, button in enumerate(getattr(self, "roster_action_buttons", [])):
            button.configure(state="normal" if index == 0 or enabled else "disabled")
        if hasattr(self, "save_guild_list_btn") and self._pending_roster_save_token:
            self.save_guild_list_btn.configure(state="disabled")

    def _refresh_project_status(self) -> None:
        self._hide_project_tooltip()
        project = self.project_path
        if project is None:
            self.project_status_var.set(tr("grabber.no_project_loaded"))
            self._project_tooltip_text = ""
            return
        resolved = project.resolve()
        self.project_status_var.set(tr("grabber.project_label", name=resolved.name))
        self._project_tooltip_text = str(resolved)

    def _show_project_tooltip(self, _event=None) -> None:
        if not self._project_tooltip_text or self._project_tooltip_window is not None:
            return
        tooltip = tk.Toplevel(self)
        tooltip.wm_overrideredirect(True)
        ttk.Label(tooltip, text=self._project_tooltip_text, padding=(6, 3)).pack()
        tooltip.geometry(f"+{self.winfo_pointerx() + 12}+{self.winfo_pointery() + 12}")
        self._project_tooltip_window = tooltip

    def _hide_project_tooltip(self, _event=None) -> None:
        tooltip = self._project_tooltip_window
        self._project_tooltip_window = None
        if tooltip is not None:
            try:
                tooltip.destroy()
            except tk.TclError:
                pass

    def _load_project(self, path: Path | str) -> None:
        project = Path(path).resolve()
        if self._session_project_path is not None and project != self._session_project_path:
            self.session_id = None
            self._session_project_path = None
            self.armory_context["sessionId"] = None
        records, context = parse_ggc_characters(project, active_only=False)
        migrate_legacy_portraits(
            project,
            [SimpleNamespace(id=record.get("memberId"), name=record.get("characterName"))
             for record in records],
        )
        self.project_path = project
        self.roster_json_path = project
        self.character_records.clear()
        for record in records:
            current = self._record_for_name(record["characterName"])
            current.update(record)
            current["graveyardReset"] = False
        self.names = dedupe_names([
            record["characterName"] for record in self.character_records.values()
            if record.get("lifeStatus") != "dead"
        ])
        self.dead_names = dedupe_names([
            record["characterName"] for record in self.character_records.values()
            if record.get("lifeStatus") == "dead"
        ])
        self.armory_context = dict(context)
        self.armory_context["sessionId"] = self.session_id
        self.output_var.set(str(project_portrait_root(project)))
        self._refresh_project_status()
        self._graveyard_cleanup_all_sessions()
        self._update_project_controls()
        self._populate_tree()
        self._populate_graveyard_tree()
        self.status_var.set(tr("grabber.project_opened", name=project.name))
        self._log(tr("grabber.project_opened_log", path=project))

    def _open_project(self) -> None:
        path = filedialog.askopenfilename(
            title=tr("grabber.open_project_title"),
            filetypes=[("Guild Gear Checker", "*.ggc")], parent=self,
        )
        if not path:
            return
        try:
            self._load_project(path)
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("grabber.project_open_failed", error=exc), parent=self)

    def _import_specific(self, title: str, filetypes, active_only: bool = True):
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        if not path: return
        try:
            import_path = Path(path)
            imported_records = None
            if import_path.suffix.casefold() == ".ggc":
                self._load_project(import_path)
                return
            else:
                names = load_names_from_file(import_path, active_only=active_only)
            before = len(self.names); self.names = dedupe_names([*self.names, *names]); added = len(self.names)-before
            for record in imported_records or []:
                current = self._record_for_name(record["characterName"])
                if not current.get("memberId"):
                    current["memberId"] = record.get("memberId")
                merge_armory_data(current, record)
                for field in ("lifeStatus", "deathDate", "graveTemplateId", "gravestoneTemplate",
                              "portraitOffsetX", "portraitOffsetY", "portraitZoom",
                              "textOffsetX", "textOffsetY", "textScale"):
                    if field in record:
                        current[field] = record[field]
            if imported_records is not None:
                self.names = dedupe_names(
                    [r["characterName"] for r in self.character_records.values() if r.get("lifeStatus") != "dead"]
                )
                self.dead_names = dedupe_names(
                    [r["characterName"] for r in self.character_records.values() if r.get("lifeStatus") == "dead"]
                )
            for name in self.names:
                self._record_for_name(name)
            msg=tr("grabber.import_summary", recognized=len(names), added=added)
            self.status_var.set(msg); self._log(msg); self._populate_tree(); self._populate_graveyard_tree()
        except Exception as exc:
            ScrollableTextDialog(self, tr("grabber.import_failed_title"), str(exc))

    # BEGIN LEGACY_GUILD_ROSTER_FETCH_WORKFLOW
    def _guild_snapshot_path(self) -> Path:
        return suite_root_dir() / "data" / "runtime" / "guild_roster_snapshot.json"

    def _fetch_guild_roster(self) -> None:
        if not LEGACY_GUILD_ROSTER_FETCH_ENABLED:
            messagebox.showinfo(
                APP_NAME,
                tr("grabber.guild_fetch_disabled"),
                parent=self,
            )
            return
        if self.guild_fetch_running:
            return
        self._save_settings()
        guild_name = self.guild_var.get().strip() if hasattr(self, "guild_var") else ""
        if not guild_name:
            messagebox.showwarning(tr("grabber.guild_roster_title"), tr("grabber.guild_name_required"), parent=self)
            if hasattr(self, "notebook") and hasattr(self, "settings_scroll"):
                try:
                    self.notebook.select(self.settings_scroll)
                except tk.TclError:
                    pass
            return
        region = self.region_var.get().strip() or DEFAULT_REGION
        realm = self.realm_var.get().strip() or DEFAULT_REALM
        game_version = self.game_var.get().strip() or DEFAULT_GAME_VERSION
        self.guild_fetch_running = True
        self.guild_fetch_btn.configure(state="disabled")
        self.status_var.set(tr("grabber.guild_roster_fetching", guild=guild_name))
        self._log(tr("grabber.guild_roster_fetching", guild=guild_name))

        def worker() -> None:
            try:
                names, source_url = fetch_guild_roster(
                    guild_name, region, realm, game_version,
                    progress=lambda page, total: self.events.put({
                        "type": "guild_roster_progress", "page": page, "total": total,
                    }),
                )
                self.events.put({
                    "type": "guild_roster_ready", "names": names, "guild": guild_name,
                    "region": region, "realm": realm, "gameVersion": game_version,
                    "sourceUrl": source_url,
                })
            except Exception as exc:
                self.events.put({
                    "type": "guild_roster_error", "message": str(exc),
                    "guild": guild_name,
                })

        threading.Thread(target=worker, name="GuildRosterFetch", daemon=True).start()

    def _store_guild_roster_snapshot(self, event: dict) -> Path:
        names = [str(name).strip() for name in event.get("names", []) if str(name).strip()]
        for name in names:
            self._record_for_name(name)
        # The current guild roster replaces the visible working list. Existing records
        # are kept in memory so already-read race/class values can enrich the snapshot.
        self.names = dedupe_names(names)
        payload = build_guild_snapshot(
            event.get("guild") or "", event.get("region") or DEFAULT_REGION,
            event.get("realm") or DEFAULT_REALM,
            event.get("gameVersion") or DEFAULT_GAME_VERSION, event.get("sourceUrl") or "",
            self.names, self.character_records,
        )
        return write_snapshot_atomic(self._guild_snapshot_path(), payload)
    # END LEGACY_GUILD_ROSTER_FETCH_WORKFLOW

    def _import_wcl_csv(self):
        self._import_specific(tr("grabber.import_wcl_title"), [("Warcraft Logs CSV","*.csv"),(tr("common.all_files"),"*.*")])

    def _import_names(self):
        self._import_specific(tr("grabber.import_list_title"), [(tr("common.supported_files"),"*.txt *.csv *.ggc"),("Guild Gear Checker","*.ggc"),("Warcraft Logs CSV","*.csv"),(tr("common.text_files"),"*.txt"),(tr("common.all_files"),"*.*")], active_only=True)

    def _current_guild_records(self) -> list[dict]:
        return [
            {
                "characterName": name,
                "race": self._record_for_name(name).get("race"),
                "className": self._record_for_name(name).get("className"),
            }
            for name in self.names
        ]

    def _apply_saved_member_summary(self, summary: dict) -> None:
        for created in summary.get("created", []):
            if not isinstance(created, dict):
                continue
            name = str(created.get("characterName") or "").strip()
            if not name:
                continue
            record = self._record_for_name(name)
            record.update({
                "memberId": str(created.get("memberId") or "") or None,
                "characterName": name,
                "lifeStatus": "active",
                "race": created.get("race"),
                "className": created.get("className"),
            })
        self._populate_tree()
        self._populate_graveyard_tree()

    @staticmethod
    def _guild_save_summary_text(summary: dict) -> str:
        added = int(summary.get("added", 0))
        existing = int(summary.get("existing", 0))
        incarnations = int(summary.get("newIncarnations", 0))
        if not added:
            return tr("grabber.guild_save_none")
        lines = [tr("grabber.guild_save_added", count=added), tr("grabber.guild_save_existing", count=existing)]
        if incarnations:
            lines.append(tr("grabber.guild_save_incarnations", count=incarnations))
        return "\n".join(lines)

    def _dispatch_project_action(self, action_type: str, data: dict) -> tuple[str, dict | None]:
        if self.project_path is None:
            raise ValueError(tr("grabber.project_required"))
        if self.session_id:
            token = queue_action(self.project_path, self.session_id, action_type, data)
            return token, None
        action = make_action(action_type, data)
        result = apply_actions_to_project(self.project_path, [action])
        receipt = next(iter(result.get("receipts", [])), None)
        if not receipt or not receipt.get("ok"):
            raise ValueError(str((receipt or {}).get("error") or tr("grabber.project_action_failed")))
        return str(action["token"]), receipt

    def _save_guild_list(self) -> None:
        if self.project_path is None:
            messagebox.showinfo(APP_NAME, tr("grabber.project_required"), parent=self)
            return
        try:
            token, receipt = self._dispatch_project_action(
                "add_members", {"members": self._current_guild_records()},
            )
            if receipt is None:
                self._pending_roster_save_token = token
                self._pending_roster_save_started = time.monotonic()
                self._update_project_controls()
                self.status_var.set(tr("grabber.guild_save_handoff"))
                self.after(100, self._poll_guild_save_receipt)
                return
            summary = dict(receipt.get("summary") or {})
            self._apply_saved_member_summary(summary)
            message = self._guild_save_summary_text(summary)
            self.status_var.set(message.replace("\n", " · "))
            self._log(message.replace("\n", " | "))
            messagebox.showinfo(APP_NAME, message, parent=self)
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("grabber.guild_save_failed", error=exc), parent=self)

    def _poll_guild_save_receipt(self) -> None:
        token = self._pending_roster_save_token
        if not token or self.project_path is None or not self.session_id:
            return
        receipt = read_receipt(self.project_path, self.session_id, token)
        if receipt is None:
            if time.monotonic() - self._pending_roster_save_started > 20.0:
                self._pending_roster_save_token = None
                self._update_project_controls()
                messagebox.showerror(
                    APP_NAME,
                    tr("grabber.guild_save_timeout"),
                    parent=self,
                )
                return
            self.after(150, self._poll_guild_save_receipt)
            return
        self._pending_roster_save_token = None
        self._update_project_controls()
        if not receipt.get("ok"):
            messagebox.showerror(
                APP_NAME,
                tr("grabber.guild_save_failed", error=receipt.get("error") or tr("common.unknown_error")),
                parent=self,
            )
            return
        summary = dict(receipt.get("summary") or {})
        self._apply_saved_member_summary(summary)
        message = self._guild_save_summary_text(summary)
        self.status_var.set(message.replace("\n", " · "))
        self._log(message.replace("\n", " | "))
        messagebox.showinfo(APP_NAME, message, parent=self)

    def _add_name(self):
        dlg=tk.Toplevel(self); dlg.title(tr("grabber.add_character")); dlg.geometry("420x180"); dlg.minsize(320,150); dlg.transient(self); dlg.grab_set()
        scroll=ScrollableFrame(dlg); scroll.pack(fill="both",expand=True); frm=scroll.content
        ttk.Label(frm,text=tr("grabber.add_character_name")).pack(anchor="w",padx=12,pady=(12,4))
        var=tk.StringVar(); ent=ttk.Entry(frm,textvariable=var,width=35); ent.pack(fill="x",padx=12); ent.focus_set()
        def add():
            name=var.get().strip()
            if not name: return
            self.names=dedupe_names([*self.names,name]); self._record_for_name(name); self._populate_tree(); self._log(f"Hinzugefuegt: {name}"); dlg.destroy()
        ttk.Button(frm,text=tr("grabber.add"),command=add).pack(pady=12); ent.bind("<Return>",lambda _e:add())

    def _remove_selected(self):
        name=self._selected_name()
        if not name: return
        if messagebox.askyesno(tr("grabber.remove"), tr("grabber.remove_question", name=name)):
            self.names=[n for n in self.names if n.casefold()!=name.casefold()]
            self.character_records.pop(name.casefold(), None)
            self._populate_tree(); self._log(f"Aus Liste entfernt: {name}")

    def _remove_selected_portrait(self):
        name = self._selected_name()
        if not name:
            return
        existing = [path for path in self._portrait_candidates_for_name(name) if path.is_file()]
        if not existing:
            self.status_by_name.pop(name, None)
            self.status_var.set(tr("grabber.portrait_not_available", name=name))
            self._populate_tree()
            self._show_portrait_preview(name)
            return
        if not messagebox.askyesno(
            tr("grabber.remove_portrait"),
            tr("grabber.remove_portrait_question", name=name),
            parent=self,
        ):
            return
        try:
            member_id = str(self._record_for_name(name).get("memberId") or "")
            remove_active_portrait_files(member_id, self.project_path)
        except OSError as exc:
            messagebox.showerror(
                tr("grabber.remove_portrait"),
                tr("grabber.remove_portrait_error", name=name, error=exc),
                parent=self,
            )
            return
        self.status_by_name.pop(name, None)
        self.status_var.set(tr("grabber.portrait_removed", name=name))
        self._populate_tree()
        self._show_portrait_preview(name)
        self._log(tr("grabber.portrait_removed", name=name))

    def _manual_portrait_selected(self):
        """Load a local image and open the shared zoom/pan/crop editor."""
        name = self._selected_name()
        if not name:
            return
        source = filedialog.askopenfilename(
            title=tr("grabber.manual_portrait_title"),
            filetypes=[
                (tr("grabber.images"), "*.png *.jpg *.jpeg *.webp *.bmp"),
                ("PNG", "*.png"), ("JPEG", "*.jpg *.jpeg"),
                ("WebP", "*.webp"), ("Bitmap", "*.bmp"),
            ], parent=self,
        )
        if not source:
            return
        output = self._require_project()
        if output is None:
            return
        member_id = str(self._record_for_name(name).get("memberId") or "")
        destination = normal_portrait_path(member_id, self.project_path)
        try:
            PortraitEditorDialog(
                self, Path(source), destination, tr("grabber.edit_portrait_for_name", name=name),
                on_saved=lambda saved, n=name: self._portrait_editor_saved(n, saved),
            )
        except Exception as exc:
            messagebox.showerror(
                tr("grabber.manual_portrait"),
                tr("grabber.manual_portrait_error", error=exc), parent=self,
            )
            self._log(tr("grabber.manual_portrait_error", error=exc))


    def _portrait_editor_saved(self, name: str, path: Path) -> None:
        path = Path(path)
        self.status_by_name[name] = tr("grabber.edit_portrait")
        self.status_var.set(tr("grabber.portrait_edited", name=name))
        self._populate_tree()
        self._show_portrait_preview(name)
        self._populate_graveyard_tree()
        self._log(tr("grabber.portrait_edited_log", name=name, path=path))

    def _edit_selected_portrait(self):
        name = self._selected_tree_name_no_dialog()
        if not name:
            messagebox.showinfo(APP_NAME, tr("grabber.select_character"), parent=self)
            return
        path = self._existing_portrait(name)
        if path is None:
            messagebox.showinfo(APP_NAME, tr("grabber.no_portrait_for_character"), parent=self)
            return
        output = self._require_project()
        if output is None:
            return
        member_id = str(self._record_for_name(name).get("memberId") or "")
        destination = normal_portrait_path(member_id, self.project_path)
        PortraitEditorDialog(
            self, path, destination, tr("grabber.edit_portrait_for_name", name=name),
            on_saved=lambda saved, n=name: self._portrait_editor_saved(n, saved),
        )

    def _graveyard_history_paths(self, record: dict) -> tuple[Path, Path]:
        try:
            return graveyard_history_paths(
                record.get("memberId"), record.get("characterName"), self.project_path,
            )
        except ValueError as exc:
            raise RuntimeError(tr("grabber.graveyard_project_required")) from exc

    def _graveyard_session_key(self, record: dict) -> str:
        return str(record.get("memberId") or record.get("characterName") or "").strip().casefold()

    def _graveyard_session(self, record: Optional[dict]) -> Optional[dict]:
        if not record:
            return None
        return self._graveyard_edit_sessions.get(self._graveyard_session_key(record))

    def _graveyard_is_editable(self, record: Optional[dict]) -> bool:
        return bool(record and (record.get("graveyardReset") or self._graveyard_session(record) is not None))

    def _graveyard_portrait_for_record(self, record: dict) -> Optional[Path]:
        """Return the persisted portrait used by the graveyard, never a temporary draft."""
        return graveyard_portrait_for_member(
            record.get("memberId"), record.get("characterName"), self.project_path,
        )

    def _graveyard_preview_portrait_for_record(self, record: dict) -> Optional[Path]:
        """Return the local edit draft when present, otherwise the persisted portrait."""
        session = self._graveyard_session(record)
        if session:
            draft = session.get("draftPortrait")
            if draft and Path(draft).is_file():
                return Path(draft)
        return self._graveyard_portrait_for_record(record)

    def _graveyard_new_draft_path(self, record: dict) -> Path:
        root = Path(tempfile.gettempdir()) / "GuildGearChecker" / "graveyard_drafts"
        root.mkdir(parents=True, exist_ok=True)
        base = safe_filename(str(record.get("memberId") or record.get("characterName") or "character"))
        return root / f"{base}_{os.getpid()}_{time.time_ns()}.png"

    def _graveyard_cleanup_session(self, record: dict) -> None:
        session = self._graveyard_edit_sessions.pop(self._graveyard_session_key(record), None)
        if not session:
            return
        draft = session.get("draftPortrait")
        if draft:
            try:
                Path(draft).unlink(missing_ok=True)
            except OSError:
                pass

    def _graveyard_cleanup_all_sessions(self) -> None:
        for session in list(self._graveyard_edit_sessions.values()):
            draft = session.get("draftPortrait")
            if draft:
                try:
                    Path(draft).unlink(missing_ok=True)
                except OSError:
                    pass
        self._graveyard_edit_sessions.clear()

    def _selected_graveyard_name(self) -> str | None:
        if not hasattr(self, "graveyard_tree"):
            return None
        selected = self.graveyard_tree.selection()
        if not selected:
            return None
        values = self.graveyard_tree.item(selected[0], "values")
        return str(values[0]) if values else None

    def _populate_graveyard_tree(self) -> None:
        if not hasattr(self, "graveyard_tree"):
            return
        selected_name = self._selected_graveyard_name()
        self.graveyard_tree.delete(*self.graveyard_tree.get_children())
        first_item = None
        selected_item = None
        for name in self.dead_names:
            record = self._record_for_name(name)
            portrait = self._graveyard_preview_portrait_for_record(record)
            reset = bool(record.get("graveyardReset"))
            editing = self._graveyard_session(record) is not None
            status = tr("grabber.graveyard_status_rebuild") if reset else (tr("grabber.graveyard_status_editing") if editing else tr("grabber.graveyard_status_locked"))
            stone = record.get("graveTemplateId") or record.get("gravestoneTemplate") or tr("grabber.graveyard_no_stone")
            if reset and not record.get("graveTemplateId"):
                stone = tr("grabber.graveyard_choose_new_stone")
            portrait_text = str(portrait) if portrait else tr("grabber.graveyard_no_portrait_placeholder")
            if editing and self._graveyard_session(record).get("draftPortrait"):
                portrait_text = f"Entwurf: {Path(portrait).name}" if portrait else "Entwurf"
            item = self.graveyard_tree.insert("", "end", values=(name, status, portrait_text, stone))
            if first_item is None:
                first_item = item
            if name == selected_name:
                selected_item = item
        target = selected_item or first_item
        if target is not None:
            self.graveyard_tree.selection_set(target)
            self.graveyard_tree.focus(target)
            self.graveyard_tree.see(target)
        self._update_graveyard_buttons()

    def _graveyard_preview_photo(self, image, size: tuple[int, int], master) -> Optional["ImageTk.PhotoImage"]:
        if Image is None or ImageTk is None or image is None:
            return None
        try:
            prepared = image.convert("RGBA")
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            prepared.thumbnail(size, resampling)
            canvas = Image.new("RGBA", size, (17, 24, 32, 255))
            x = (size[0] - prepared.width) // 2
            y = (size[1] - prepared.height) // 2
            canvas.alpha_composite(prepared, (x, y))
            return ImageTk.PhotoImage(canvas, master=master)
        except Exception:
            return None

    def _update_graveyard_detail(self, record: Optional[dict]) -> None:
        if not hasattr(self, "gy_detail_name_var"):
            return
        self._gy_stone_photo = None
        if not record:
            self.gy_detail_name_var.set(tr("grabber.graveyard_no_character"))
            self.gy_detail_status_var.set("–")
            self.gy_stone_preview.delete("all")
            self.gy_stone_preview.create_text(225, 306, text=tr("grabber.graveyard_no_stone"), fill="#c7d0d9")
            self.gy_stone_info_var.set("–")
            return

        name = str(record.get("characterName") or "–")
        reset = bool(record.get("graveyardReset"))
        editing = self._graveyard_session(record) is not None
        self.gy_detail_name_var.set(name)
        self.gy_detail_status_var.set(tr("grabber.graveyard_status_rebuild") if reset else (tr("grabber.graveyard_status_editing") if editing else tr("grabber.graveyard_status_locked")))

        stone_id = str(record.get("graveTemplateId") or "")
        stone_file = str(record.get("gravestoneTemplate") or "")
        stone_photo = None
        stone_error = ""
        if stone_id:
            try:
                checker = self._checker_graveyard_support()
                inventory = checker.load_gravestone_inventory(
                    checker.gravestone_template_folder(), checker.gravestone_manifest_path(),
                )
                template = inventory.by_id().get(stone_id)
                if template is not None:
                    draft_data = {
                        "id": str(record.get("memberId") or safe_filename(name)),
                        "name": name, "lifeStatus": "dead",
                        "deathDate": str(record.get("deathDate") or ""),
                        "graveTemplateId": stone_id, "gravestoneTemplate": template.filename,
                        "portraitOffsetX": float(record.get("portraitOffsetX") or 0.0),
                        "portraitOffsetY": float(record.get("portraitOffsetY") or 0.0),
                        "portraitZoom": float(record.get("portraitZoom") or 1.0),
                        "textOffsetX": float(record.get("textOffsetX") or 0.0),
                        "textOffsetY": float(record.get("textOffsetY") or 0.0),
                        "textScale": float(record.get("textScale") or 1.0),
                    }
                    draft = checker.Member.from_dict(draft_data, draft_data["id"])
                    frame = checker.prepare_gravestone_template(template.path, checker.GRAVESTONE_EDITOR_SIZE)
                    render_portrait = self._graveyard_preview_portrait_for_record(record)
                    if render_portrait is None:
                        placeholder = suite_root_dir() / "assets" / "graveyard" / "portrait_placeholder.png"
                        render_portrait = placeholder if placeholder.is_file() else None
                    card = checker.render_gravestone_card(
                        draft, frame, render_portrait, checker.GRAVESTONE_EDITOR_SIZE,
                    )
                    stone_photo = self._graveyard_preview_photo(card, (450, 613), self.gy_stone_preview)
                    stone_file = template.filename
                else:
                    stone_error = tr("grabber.graveyard_stone_not_manifest")
            except Exception as exc:
                stone_error = tr("grabber.preview_unavailable", error=exc)

        self.gy_stone_preview.delete("all")
        if stone_photo is not None:
            self._gy_stone_photo = stone_photo
            self.gy_stone_preview.create_image(0, 0, anchor="nw", image=stone_photo)
        else:
            self.gy_stone_preview.create_text(
                225, 306, text=(stone_error or tr("grabber.graveyard_no_stone_selected")),
                fill="#c7d0d9", width=410,
            )

        if stone_id and stone_file:
            self.gy_stone_info_var.set(f"{stone_file}")
        elif stone_file:
            self.gy_stone_info_var.set(stone_file)
        else:
            self.gy_stone_info_var.set(tr("grabber.graveyard_no_stone_yet"))

    def _update_graveyard_buttons(self) -> None:
        name = self._selected_graveyard_name()
        record = self._record_for_name(name) if name else None
        reset = bool(record and record.get("graveyardReset"))
        editing = bool(record and self._graveyard_session(record) is not None)
        editable = bool(record and (reset or editing))
        if hasattr(self, "gy_reset_btn"):
            if record and not editable:
                self.gy_open_btn.grid()
                self.gy_open_btn.configure(state="normal")
            else:
                self.gy_open_btn.grid_remove()
            self.gy_discard_btn.configure(state="normal" if editing and not reset else "disabled")
            self.gy_reset_btn.configure(state="normal" if record and not editable else "disabled")
            self.gy_adjust_btn.configure(state="normal" if editable else "disabled")
            self.gy_save_btn.configure(state="normal" if editable and record.get("graveTemplateId") else "disabled")
        self._update_graveyard_detail(record)

    def _write_graveyard_action(self, record: dict, action: str) -> None:
        data = {
            "memberId": str(record.get("memberId") or ""),
            "graveTemplateId": str(record.get("graveTemplateId") or ""),
            "gravestoneTemplate": str(record.get("gravestoneTemplate") or ""),
            "portraitOffsetX": float(record.get("portraitOffsetX") or 0.0),
            "portraitOffsetY": float(record.get("portraitOffsetY") or 0.0),
            "portraitZoom": float(record.get("portraitZoom") or 1.0),
            "textOffsetX": float(record.get("textOffsetX") or 0.0),
            "textOffsetY": float(record.get("textOffsetY") or 0.0),
            "textScale": float(record.get("textScale") or 1.0),
            "deathDate": str(record.get("deathDate") or ""),
        }
        action_type = "graveyard_reset" if action == "reset" else "graveyard_save"
        self._dispatch_project_action(action_type, data)

    def _graveyard_begin_edit_selected(self):
        name = self._selected_graveyard_name()
        if not name:
            return
        record = self._record_for_name(name)
        if record.get("graveyardReset") or self._graveyard_session(record) is not None:
            return
        fields = (
            "graveTemplateId", "gravestoneTemplate", "portraitOffsetX", "portraitOffsetY",
            "portraitZoom", "textOffsetX", "textOffsetY", "textScale", "deathDate",
            "gravestoneCategory",
        )
        self._graveyard_edit_sessions[self._graveyard_session_key(record)] = {
            "snapshot": {field: record.get(field) for field in fields},
            "draftPortrait": None,
        }
        self.status_var.set(tr("grabber.graveyard_edit_opened", name=name))
        self._log(tr("grabber.graveyard_edit_opened", name=name))
        self._populate_graveyard_tree()

    def _graveyard_discard_edit_selected(self):
        name = self._selected_graveyard_name()
        if not name:
            return
        record = self._record_for_name(name)
        session = self._graveyard_session(record)
        if not session:
            return
        snapshot = session.get("snapshot") or {}
        record.update(snapshot)
        self._graveyard_cleanup_session(record)
        self.status_var.set(tr("grabber.graveyard_edit_discarded", name=name))
        self._log(tr("grabber.graveyard_edit_discarded", name=name))
        self._populate_graveyard_tree()

    def _graveyard_reset_selected(self):
        name = self._selected_graveyard_name()
        if not name:
            return
        record = self._record_for_name(name)
        if not messagebox.askyesno(
            tr("grabber.graveyard_full_reset"),
            tr("grabber.graveyard_reset_question", name=name) + "\n\n" +
            tr("grabber.irreversible_warning"), parent=self,
        ):
            return
        try:
            self._graveyard_cleanup_session(record)
            for candidate in self._portrait_candidates_for_name(name):
                if candidate.is_file():
                    candidate.unlink()
            historical, missing = self._graveyard_history_paths(record)
            historical.unlink(missing_ok=True)
            missing.unlink(missing_ok=True)
            record.update({
                "graveTemplateId": "", "gravestoneTemplate": "",
                "gravestoneCategory": "",
                "portraitOffsetX": 0.0, "portraitOffsetY": 0.0, "portraitZoom": 1.0,
                "textOffsetX": 0.0, "textOffsetY": 0.0, "textScale": 1.0,
                "graveyardReset": True,
            })
            self._write_graveyard_action(record, "reset")
            self.status_var.set(tr("grabber.graveyard_reset_done", name=name))
            self._log(tr("grabber.graveyard_reset_log", name=name))
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("grabber.graveyard_reset_failed", error=exc), parent=self)
        self._populate_graveyard_tree()

    def _graveyard_draft_portrait_saved(self, record: dict, saved: Path) -> None:
        session = self._graveyard_session(record)
        if session is None:
            # Reset workflow is already destructive by design; keep the historical target semantics.
            self._populate_graveyard_tree()
            return
        previous = session.get("draftPortrait")
        session["draftPortrait"] = str(Path(saved))
        if previous and Path(previous) != Path(saved):
            try:
                Path(previous).unlink(missing_ok=True)
            except OSError:
                pass
        name = str(record.get("characterName") or "")
        self.status_var.set(tr("grabber.graveyard_draft_portrait_updated", name=name))
        self._populate_graveyard_tree()

    def _graveyard_load_portrait_selected(self):
        name = self._selected_graveyard_name()
        if not name:
            return
        record = self._record_for_name(name)
        if not self._graveyard_is_editable(record):
            return
        source = filedialog.askopenfilename(
            title=tr("grabber.new_portrait_for_name", name=name),
            filetypes=[(tr("grabber.images"), "*.png *.jpg *.jpeg *.webp *.bmp"), (tr("common.all_files"), "*.*")],
            parent=self,
        )
        if not source:
            return
        if record.get("graveyardReset"):
            destination, missing = self._graveyard_history_paths(record)
            missing.unlink(missing_ok=True)
            callback = lambda saved, n=name: self._portrait_editor_saved(n, saved)
        else:
            destination = self._graveyard_new_draft_path(record)
            callback = lambda saved, r=record: self._graveyard_draft_portrait_saved(r, saved)
        PortraitEditorDialog(
            self, Path(source), destination, tr("grabber.edit_portrait_for_name", name=name), on_saved=callback,
        )

    def _graveyard_edit_portrait_selected(self):
        name = self._selected_graveyard_name()
        if not name:
            return
        record = self._record_for_name(name)
        portrait = self._graveyard_preview_portrait_for_record(record)
        if not self._graveyard_is_editable(record) or portrait is None:
            return
        if record.get("graveyardReset"):
            destination, missing = self._graveyard_history_paths(record)
            missing.unlink(missing_ok=True)
            callback = lambda saved, n=name: self._portrait_editor_saved(n, saved)
        else:
            destination = self._graveyard_new_draft_path(record)
            callback = lambda saved, r=record: self._graveyard_draft_portrait_saved(r, saved)
        PortraitEditorDialog(
            self, portrait, destination, tr("grabber.edit_portrait_for_name", name=name), on_saved=callback,
        )

    def _checker_graveyard_support(self):
        root_text = str(suite_root_dir())
        if root_text not in sys.path:
            sys.path.insert(0, root_text)
        try:
            from app import GuildGearChecker as checker
        except ImportError:
            import GuildGearChecker as checker
        return checker

    def _graveyard_adjust_selected(self):
        """Open the single visual editor for portrait, gravestone and text layout."""
        name = self._selected_graveyard_name()
        if not name:
            return
        record = self._record_for_name(name)
        if not self._graveyard_is_editable(record):
            return
        try:
            checker = self._checker_graveyard_support()
            if self.roster_json_path is None or not self.roster_json_path.is_file():
                raise RuntimeError(tr("grabber.graveyard_data_unavailable"))
            payload = json.loads(self.roster_json_path.read_text(encoding="utf-8-sig"))

            # Reuse the verified template inventory between editor sessions. Verifying
            # all productive PNGs (readability + SHA-256) is intentionally strict but
            # expensive; file/manifest signatures keep this cache safe and self-invalidating.
            template_folder = checker.gravestone_template_folder()
            manifest_path = checker.gravestone_manifest_path()
            try:
                manifest_stat = manifest_path.stat()
                manifest_sig = (int(manifest_stat.st_mtime_ns), int(manifest_stat.st_size))
            except OSError:
                manifest_sig = (None, None)
            template_stats = []
            try:
                for path in sorted(template_folder.glob("gravestone_*"), key=lambda item: item.name.casefold()):
                    if not path.is_file() or path.name.casefold() == "gravestone_placeholder.png":
                        continue
                    try:
                        stat = path.stat()
                        template_stats.append((path.name, int(stat.st_mtime_ns), int(stat.st_size)))
                    except OSError:
                        template_stats.append((path.name, None, None))
            except OSError:
                template_stats = []
            inventory_key = (str(template_folder.resolve()), manifest_sig, tuple(template_stats))
            cached_inventory = getattr(self, "_graveyard_editor_inventory_cache", None)

            model = checker.GuildModel()
            if cached_inventory and cached_inventory.get("key") == inventory_key:
                model._gravestone_inventory_cache = cached_inventory.get("inventory")
            model.load_payload(payload)
            if model._gravestone_inventory_cache is not None:
                self._graveyard_editor_inventory_cache = {
                    "key": inventory_key, "inventory": model._gravestone_inventory_cache,
                }

            member = model.find_by_id(record.get("memberId") or "")
            if member is None:
                raise RuntimeError(tr("grabber.graveyard_character_missing"))

            # Mirror the current local draft into a temporary Member. Nothing in the
            # project data is persisted until the outer 'Speichern und sperren' action.
            member.graveTemplateId = str(record.get("graveTemplateId") or "")
            member.gravestoneTemplate = str(record.get("gravestoneTemplate") or "")
            member.portraitOffsetX = float(record.get("portraitOffsetX") or 0.0)
            member.portraitOffsetY = float(record.get("portraitOffsetY") or 0.0)
            member.portraitZoom = float(record.get("portraitZoom") or 1.0)
            member.textOffsetX = float(record.get("textOffsetX") or 0.0)
            member.textOffsetY = float(record.get("textOffsetY") or 0.0)
            member.textScale = float(record.get("textScale") or 1.0)
            member.deathDate = str(record.get("deathDate") or "")

            inventory, available = model.available_gravestone_templates(member.id)
            templates = inventory.by_id()
            all_candidate_ids = [t.grave_template_id for t in available if t.grave_template_id in templates]
            if member.graveTemplateId and member.graveTemplateId not in all_candidate_ids and member.graveTemplateId in templates:
                all_candidate_ids.insert(0, member.graveTemplateId)
            if not all_candidate_ids:
                raise RuntimeError(tr("grabber.graveyard_no_free_stone"))

            initial_id = member.graveTemplateId if member.graveTemplateId in all_candidate_ids else all_candidate_ids[0]
            selected_id = tk.StringVar(value=initial_id)
            filter_all_label = tr("common.all")
            filter_none_label = gravestone_category_display(None)
            category_filter_values = [
                filter_all_label,
                *gravestone_category_display_values(),
                filter_none_label,
            ]
            category_filter_key_by_label = {
                filter_all_label: GRAVESTONE_CATEGORY_FILTER_ALL,
                filter_none_label: GRAVESTONE_CATEGORY_FILTER_UNCATEGORIZED,
            }
            category_filter_key_by_label.update({
                gravestone_category_display(category): category for category in GRAVESTONE_CATEGORIES
            })
            initial_category = normalize_gravestone_category(templates[initial_id].category)
            selected_category_filter = tk.StringVar(
                value=gravestone_category_display(initial_category) if initial_category else filter_none_label
            )
            candidate_ids = filter_gravestone_template_ids(
                templates, all_candidate_ids, member.graveTemplateId,
                category_filter_key_by_label[selected_category_filter.get()],
            )
            ox = tk.DoubleVar(value=member.portraitOffsetX)
            oy = tk.DoubleVar(value=member.portraitOffsetY)
            zoom = tk.DoubleVar(value=member.portraitZoom)
            tx = tk.DoubleVar(value=member.textOffsetX)
            ty = tk.DoubleVar(value=member.textOffsetY)
            ts = tk.DoubleVar(value=member.textScale)
            death_date = tk.StringVar(value=member.deathDate)
            edit_target = tk.StringVar(value="portrait")
            zoom_text = tk.StringVar()
            text_scale_text = tk.StringVar()
            portrait_name = tk.StringVar(value="")

            win = tk.Toplevel(self)
            win.title(tr("grabber.gravestone_editor_title", name=name))
            win.transient(self)

            # Keep every editor action visible on first open. On shorter work areas
            # the preview is scaled down instead of pushing the buttons off-screen.
            work_area = primary_work_area(win)
            editor_margin = 20
            available_width = max(1, work_area.width - editor_margin * 2)
            available_height = max(1, work_area.height - editor_margin * 2)
            # Two-column editor: large final preview on the left, all controls on the right.
            # This keeps the action buttons visible without shrinking the gravestone excessively.
            preview_height = max(360, min(654, available_height - 90))
            preview_width = max(264, round(preview_height * 537 / 732))
            preview_size = (preview_width, preview_height)
            initial_width = min(max(920, preview_width + 500), available_width)
            initial_height = min(max(620, preview_height + 90), available_height)
            initial_x = work_area.x + max(0, (work_area.width - initial_width) // 2)
            initial_y = work_area.y + max(0, (work_area.height - initial_height) // 2)
            win.geometry(f"{initial_width}x{initial_height}+{initial_x}+{initial_y}")
            win.minsize(min(620, available_width), min(650, available_height))
            win.resizable(True, True)
            win.grab_set()

            editor_scroll = ScrollableFrame(win)
            editor_scroll.pack(fill="both", expand=True)
            root = editor_scroll.content
            root.columnconfigure(0, weight=1)
            root.columnconfigure(1, weight=1)

            ttk.Label(
                root,
                text=tr("grabber.gravestone_editor_help"),
                wraplength=700, justify="left",
            ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 6))

            template_row = ttk.LabelFrame(root, text=tr("grabber.gravestone_group"), padding=6)
            template_row.grid(row=1, column=1, sticky="ew", padx=(6, 12), pady=(0, 6))
            template_row.columnconfigure(1, weight=1)

            template_names = [templates[template_id].filename for template_id in candidate_ids]
            id_by_name = {templates[template_id].filename: template_id for template_id in candidate_ids}
            selected_template_name = tk.StringVar(value=templates[selected_id.get()].filename)

            ttk.Button(template_row, text="◀", width=4, command=lambda: change_template(-1)).grid(row=0, column=0, padx=(0, 5))
            template_combo = ttk.Combobox(
                template_row, textvariable=selected_template_name, values=template_names,
                state="readonly",
            )
            template_combo.grid(row=0, column=1, sticky="ew")
            ttk.Button(template_row, text="▶", width=4, command=lambda: change_template(1)).grid(row=0, column=2, padx=(5, 0))
            ttk.Label(template_row, text=f"{tr('grabber.gravestone_category_filter')}:").grid(
                row=1, column=0, sticky="w", pady=(6, 0),
            )
            category_combo = ttk.Combobox(
                template_row, textvariable=selected_category_filter,
                values=category_filter_values, state="readonly",
            )
            category_combo.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(6, 0))

            canvas = tk.Canvas(
                root, width=preview_size[0], height=preview_size[1],
                bg="#101820", highlightthickness=0, cursor="fleur",
            )
            canvas.grid(row=1, column=0, rowspan=6, sticky="n", padx=(12, 6), pady=(0, 10))
            photo_ref = {"photo": None, "item": None}
            drag = {"x": 0, "y": 0, "ox": 0.0, "oy": 0.0, "tx": 0.0, "ty": 0.0}

            portrait_path = self._graveyard_preview_portrait_for_record(record)
            if portrait_path is None:
                placeholder = suite_root_dir() / "assets" / "graveyard" / "portrait_placeholder.png"
                portrait_path = placeholder if placeholder.is_file() else None
            portrait_ref = {"path": Path(portrait_path) if portrait_path is not None else None}
            portrait_changed = {"value": False}
            editor_portrait_temp = {"path": None}

            # Editor-local caches only. The shared GuildGearChecker renderer stays untouched.
            # The preview mirrors the production composition while reusing expensive inputs.
            frame_cache: dict[str, Image.Image] = {}
            opening_cache = {}
            portrait_source_cache = {"signature": None, "image": None}
            render_state = {"after": None, "signature": None, "closed": False}

            def selected_frame():
                template_id = selected_id.get()
                cached = frame_cache.get(template_id)
                if cached is not None:
                    return cached
                selected = templates.get(template_id)
                if selected is None:
                    frame = Image.new("RGBA", preview_size, (0, 0, 0, 0))
                else:
                    frame = checker.prepare_gravestone_template(selected.path, preview_size)
                frame_cache[template_id] = frame
                return frame

            def selected_opening():
                template_id = selected_id.get()
                opening = opening_cache.get(template_id)
                if opening is None:
                    opening = checker.detect_gravestone_portrait_opening(selected_frame())
                    opening_cache[template_id] = opening
                return opening

            def portrait_signature():
                path = portrait_ref["path"]
                if path is None:
                    return None
                try:
                    stat = Path(path).stat()
                    return (str(Path(path).resolve()), int(stat.st_mtime_ns), int(stat.st_size))
                except OSError:
                    return (str(path), None, None)

            def portrait_source():
                signature = portrait_signature()
                if signature is None:
                    portrait_source_cache["signature"] = None
                    portrait_source_cache["image"] = None
                    return None
                if portrait_source_cache["signature"] != signature:
                    try:
                        with Image.open(portrait_ref["path"]) as raw:
                            portrait_source_cache["image"] = raw.copy()
                    except (OSError, ValueError):
                        portrait_source_cache["image"] = None
                    portrait_source_cache["signature"] = signature
                return portrait_source_cache["image"]

            def adjusted_member():
                adjusted = checker.Member.from_dict(member.to_dict(), member.id)
                adjusted.graveTemplateId = selected_id.get()
                selected = templates.get(selected_id.get())
                adjusted.gravestoneTemplate = selected.filename if selected else ""
                adjusted.portraitOffsetX = checker.normalize_portrait_offset(ox.get())
                adjusted.portraitOffsetY = checker.normalize_portrait_offset(oy.get())
                adjusted.portraitZoom = checker.normalize_portrait_zoom(zoom.get())
                adjusted.textOffsetX = checker.normalize_text_offset(tx.get())
                adjusted.textOffsetY = checker.normalize_text_offset(ty.get())
                adjusted.textScale = checker.normalize_text_scale(ts.get())
                adjusted.deathDate = death_date.get().strip()
                return adjusted

            def render_editor_preview(adjusted):
                """Render the interactive preview from cached editor inputs only."""
                frame = selected_frame()
                opening = selected_opening()
                card = Image.new("RGBA", preview_size, (0, 0, 0, 0))
                portrait_box = opening.box
                portrait_size = (
                    max(1, portrait_box[2] - portrait_box[0]),
                    max(1, portrait_box[3] - portrait_box[1]),
                )
                fitted = Image.new("RGB", portrait_size, "#15191d")
                source = portrait_source()
                current_portrait = portrait_ref["path"]
                placeholder_x, placeholder_y, placeholder_zoom = checker.graveyard_placeholder_variation(
                    adjusted, current_portrait,
                )
                if source is not None:
                    is_placeholder = bool(
                        current_portrait and current_portrait.name.casefold() == "portrait_placeholder.png"
                    )
                    fitted = checker.fit_gravestone_portrait(
                        source, portrait_size,
                        placeholder_x if is_placeholder else adjusted.portraitOffsetX,
                        placeholder_y if is_placeholder else adjusted.portraitOffsetY,
                        placeholder_zoom if is_placeholder else adjusted.portraitZoom,
                    )
                portrait_layer = Image.new("RGBA", preview_size, (0, 0, 0, 0))
                mask = opening.mask
                if getattr(mask, "size", None) != portrait_size:
                    mask = mask.resize(portrait_size, Image.Resampling.LANCZOS)
                portrait_layer.paste(fitted, portrait_box[:2], mask)
                card.alpha_composite(portrait_layer)
                card.alpha_composite(frame)

                draw = ImageDraw.Draw(card)
                colors = {"name": "#f6ead0", "class": "#e2d3b8", "death_date": "#d8c9ad"}
                selected_template = templates.get(selected_id.get())
                for key, line in checker.gravestone_text_layout(
                    adjusted, preview_size,
                    selected_template.default_text_safe_area if selected_template else None,
                ).items():
                    draw.text(
                        line["position"], line["text"], anchor="mm", align="center",
                        font=line["font"], fill=colors[key], stroke_width=1, stroke_fill="#17130f",
                    )
                return card

            def redraw_now():
                render_state["after"] = None
                if render_state["closed"] or not win.winfo_exists():
                    return
                adjusted = adjusted_member()
                signature = (
                    adjusted.graveTemplateId, portrait_signature(),
                    adjusted.portraitOffsetX, adjusted.portraitOffsetY, adjusted.portraitZoom,
                    adjusted.textOffsetX, adjusted.textOffsetY, adjusted.textScale,
                    adjusted.deathDate, preview_size,
                )
                zoom_text.set(f"{adjusted.portraitZoom:.2f}×")
                text_scale_text.set(f"{adjusted.textScale:.2f}×")
                current_portrait = portrait_ref["path"]
                portrait_name.set(current_portrait.name if current_portrait else tr("grabber.no_portrait"))
                if signature == render_state["signature"]:
                    return
                card = render_editor_preview(adjusted)
                photo_ref["photo"] = ImageTk.PhotoImage(card, master=win)
                if photo_ref["item"] is None:
                    photo_ref["item"] = canvas.create_image(0, 0, anchor="nw", image=photo_ref["photo"])
                else:
                    canvas.itemconfigure(photo_ref["item"], image=photo_ref["photo"])
                render_state["signature"] = signature

            def request_redraw(*_, delay=16):
                if render_state["closed"] or not win.winfo_exists():
                    return
                if render_state["after"] is None:
                    render_state["after"] = win.after(delay, redraw_now)

            def flush_redraw(_event=None):
                pending = render_state.get("after")
                if pending is not None:
                    try:
                        win.after_cancel(pending)
                    except tk.TclError:
                        pass
                    render_state["after"] = None
                redraw_now()

            def apply_template_portrait_preset(template_id):
                template = templates[template_id]
                ox.set(template.default_portrait_offset_x)
                oy.set(template.default_portrait_offset_y)
                zoom.set(template.default_portrait_zoom)

            def set_template_from_combo(_event=None):
                template_id = id_by_name.get(selected_template_name.get())
                if template_id:
                    selected_id.set(template_id)
                    apply_template_portrait_preset(template_id)
                    flush_redraw()

            def refresh_category_filter(_event=None):
                filter_key = category_filter_key_by_label.get(
                    selected_category_filter.get(), GRAVESTONE_CATEGORY_FILTER_ALL
                )
                filtered = filter_gravestone_template_ids(
                    templates, all_candidate_ids, member.graveTemplateId, filter_key,
                )
                candidate_ids[:] = filtered
                names = [templates[template_id].filename for template_id in candidate_ids]
                id_by_name.clear()
                id_by_name.update({templates[template_id].filename: template_id for template_id in candidate_ids})
                template_combo.configure(values=names)
                if not candidate_ids:
                    return
                if selected_id.get() not in candidate_ids:
                    template_id = candidate_ids[0]
                    selected_id.set(template_id)
                    selected_template_name.set(templates[template_id].filename)
                    apply_template_portrait_preset(template_id)
                    flush_redraw()
                else:
                    selected_template_name.set(templates[selected_id.get()].filename)

            def change_template(step):
                if not candidate_ids:
                    return
                try:
                    index = candidate_ids.index(selected_id.get())
                except ValueError:
                    index = -1 if step > 0 else 0
                template_id = candidate_ids[(index + step) % len(candidate_ids)]
                selected_id.set(template_id)
                selected_template_name.set(templates[template_id].filename)
                apply_template_portrait_preset(template_id)
                flush_redraw()

            template_combo.bind("<<ComboboxSelected>>", set_template_from_combo)
            category_combo.bind("<<ComboboxSelected>>", refresh_category_filter)

            portrait_box = ttk.LabelFrame(root, text=tr("grabber.portrait_group"), padding=6)
            portrait_box.grid(row=2, column=1, sticky="ew", padx=(6, 12), pady=(0, 6))
            portrait_box.columnconfigure(0, weight=1)
            portrait_box.columnconfigure(1, weight=1)
            ttk.Label(portrait_box, textvariable=portrait_name, anchor="center").grid(
                row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5),
            )

            def portrait_saved_local(saved: Path):
                saved = Path(saved)
                editor_portrait_temp["path"] = saved
                portrait_ref["path"] = saved
                portrait_changed["value"] = True
                flush_redraw()

            def open_portrait_editor(source: Path):
                if source is None or not Path(source).is_file():
                    messagebox.showinfo(APP_NAME, tr("grabber.no_portrait_to_edit"), parent=win)
                    return
                destination = editor_portrait_temp.get("path") or self._graveyard_new_draft_path(record)
                editor_portrait_temp["path"] = Path(destination)
                dialog = PortraitEditorDialog(
                    win, Path(source), Path(destination), tr("grabber.edit_portrait_for_name", name=name),
                    on_saved=portrait_saved_local,
                )
                win.wait_window(dialog)
                if win.winfo_exists():
                    try:
                        win.grab_set()
                    except tk.TclError:
                        pass

            def choose_portrait():
                source = filedialog.askopenfilename(
                    title=tr("grabber.portrait_for_name", name=name),
                    filetypes=[(tr("grabber.images"), "*.png *.jpg *.jpeg *.webp *.bmp"), (tr("common.all_files"), "*.*")],
                    parent=win,
                )
                if source:
                    open_portrait_editor(Path(source))

            ttk.Button(portrait_box, text=tr("grabber.change_portrait"), command=choose_portrait).grid(
                row=1, column=0, sticky="ew", padx=(0, 3),
            )
            ttk.Button(
                portrait_box, text=tr("grabber.edit_portrait"),
                command=lambda: open_portrait_editor(portrait_ref["path"]),
            ).grid(row=1, column=1, sticky="ew", padx=(3, 0))

            target_row = ttk.Frame(root)
            target_row.grid(row=3, column=1, sticky="ew", padx=(6, 12), pady=(2, 2))
            ttk.Label(target_row, text=tr("grabber.drag_moves")).pack(side="left", padx=(0, 8))
            ttk.Radiobutton(target_row, text=tr("common.portrait"), variable=edit_target, value="portrait").pack(side="left", padx=(0, 12))
            ttk.Radiobutton(target_row, text=tr("grabber.text_field"), variable=edit_target, value="text").pack(side="left")

            def start_drag(event):
                drag.update(x=event.x, y=event.y, ox=ox.get(), oy=oy.get(), tx=tx.get(), ty=ty.get())

            def move_drag(event):
                dx, dy = event.x - drag["x"], event.y - drag["y"]
                if edit_target.get() == "text":
                    nx, ny = checker.shifted_text_offsets(drag["tx"], drag["ty"], dx, dy, preview_size)
                    tx.set(nx); ty.set(ny)
                else:
                    opening = selected_opening().box
                    opening_size = (max(1, opening[2]-opening[0]), max(1, opening[3]-opening[1]))
                    nx, ny = checker.shifted_portrait_offsets(drag["ox"], drag["oy"], dx, dy, opening_size)
                    ox.set(nx); oy.set(ny)
                request_redraw()

            canvas.bind("<ButtonPress-1>", start_drag)
            canvas.bind("<B1-Motion>", move_drag)
            canvas.bind("<ButtonRelease-1>", flush_redraw)

            controls = ttk.LabelFrame(root, text=tr("grabber.positioning"), padding=6)
            controls.grid(row=4, column=1, sticky="ew", padx=(6, 12), pady=(2, 6))
            controls.columnconfigure(1, weight=1)
            ttk.Label(controls, text=tr("grabber.portrait_zoom")).grid(row=0, column=0, sticky="w")
            zoom_scale = ttk.Scale(
                controls, from_=checker.GRAVESTONE_PORTRAIT_ZOOM_RANGE[0],
                to=checker.GRAVESTONE_PORTRAIT_ZOOM_RANGE[1], variable=zoom,
                command=request_redraw,
            )
            zoom_scale.grid(row=0, column=1, sticky="ew", padx=8)
            zoom_scale.bind("<ButtonRelease-1>", flush_redraw)
            ttk.Label(controls, textvariable=zoom_text, width=6).grid(row=0, column=2, sticky="e")
            ttk.Label(controls, text=tr("grabber.text_size")).grid(row=1, column=0, sticky="w")
            text_scale_widget = ttk.Scale(
                controls, from_=checker.GRAVESTONE_TEXT_SCALE_RANGE[0],
                to=checker.GRAVESTONE_TEXT_SCALE_RANGE[1], variable=ts,
                command=request_redraw,
            )
            text_scale_widget.grid(row=1, column=1, sticky="ew", padx=8)
            text_scale_widget.bind("<ButtonRelease-1>", flush_redraw)
            ttk.Label(controls, textvariable=text_scale_text, width=6).grid(row=1, column=2, sticky="e")

            date_row = ttk.Frame(controls)
            date_row.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(5, 0))
            ttk.Label(date_row, text=tr("grabber.death_date")).pack(side="left")
            date_entry = ttk.Entry(date_row, textvariable=death_date, width=14)
            date_entry.pack(side="right")
            date_entry.bind("<KeyRelease>", request_redraw)

            ttk.Label(
                root,
                text=tr("grabber.gravestone_editor_tip"),
                wraplength=430, justify="left",
            ).grid(row=5, column=1, sticky="ew", padx=(6, 12), pady=(0, 5))

            buttons = ttk.Frame(root)
            buttons.grid(row=6, column=1, sticky="ew", padx=(6, 12), pady=(4, 12))

            def reset_positions():
                ox.set(0.0); oy.set(0.0); zoom.set(1.0)
                tx.set(0.0); ty.set(0.0); ts.set(1.0)
                flush_redraw()

            def cleanup_editor_portrait():
                path = editor_portrait_temp.get("path")
                if path:
                    try:
                        Path(path).unlink(missing_ok=True)
                    except OSError:
                        pass
                    editor_portrait_temp["path"] = None

            def cancel():
                render_state["closed"] = True
                pending = render_state.get("after")
                if pending is not None:
                    try:
                        win.after_cancel(pending)
                    except tk.TclError:
                        pass
                    render_state["after"] = None
                cleanup_editor_portrait()
                win.destroy()

            def accept():
                template = templates.get(selected_id.get())
                if template is None:
                    messagebox.showwarning(APP_NAME, tr("grabber.stone_unavailable"), parent=win)
                    return

                # Promote a portrait changed inside this dialog into the outer edit draft.
                if portrait_changed["value"] and portrait_ref["path"] and Path(portrait_ref["path"]).is_file():
                    if record.get("graveyardReset"):
                        historical, missing = self._graveyard_history_paths(record)
                        historical.parent.mkdir(parents=True, exist_ok=True)
                        staged = historical.with_suffix(historical.suffix + ".editor.tmp")
                        shutil.copy2(Path(portrait_ref["path"]), staged)
                        os.replace(staged, historical)
                        missing.unlink(missing_ok=True)
                        portrait_ref["path"] = historical
                        cleanup_editor_portrait()
                    else:
                        self._graveyard_draft_portrait_saved(record, Path(portrait_ref["path"]))
                        # The session now owns this temp file and will clean it on discard/save.
                        editor_portrait_temp["path"] = None

                record.update({
                    "graveTemplateId": template.grave_template_id,
                    "gravestoneTemplate": template.filename,
                    "gravestoneCategory": normalize_gravestone_category(template.category) or "",
                    "portraitOffsetX": float(checker.normalize_portrait_offset(ox.get())),
                    "portraitOffsetY": float(checker.normalize_portrait_offset(oy.get())),
                    "portraitZoom": float(checker.normalize_portrait_zoom(zoom.get())),
                    "textOffsetX": float(checker.normalize_text_offset(tx.get())),
                    "textOffsetY": float(checker.normalize_text_offset(ty.get())),
                    "textScale": float(checker.normalize_text_scale(ts.get())),
                    "deathDate": death_date.get().strip(),
                })
                render_state["closed"] = True
                pending = render_state.get("after")
                if pending is not None:
                    try:
                        win.after_cancel(pending)
                    except tk.TclError:
                        pass
                    render_state["after"] = None
                win.destroy()
                self._populate_graveyard_tree()
                self.status_var.set(tr("grabber.gravestone_draft_updated", name=name))

            ttk.Button(buttons, text=tr("grabber.positions_reset"), command=reset_positions).pack(side="left")
            ttk.Button(buttons, text=tr("common.cancel"), command=cancel).pack(side="right")
            ttk.Button(buttons, text=tr("common.apply"), command=accept).pack(side="right", padx=(0, 6))
            def fit_editor_window_to_content():
                if not win.winfo_exists():
                    return
                win.update_idletasks()
                requested_width = max(620, root.winfo_reqwidth() + 28)
                requested_height = max(650, root.winfo_reqheight() + 28)
                final_width = min(requested_width, available_width)
                final_height = min(requested_height, available_height)
                final_x = work_area.x + max(0, (work_area.width - final_width) // 2)
                final_y = work_area.y + max(0, (work_area.height - final_height) // 2)
                win.geometry(f"{final_width}x{final_height}+{final_x}+{final_y}")
                editor_scroll.canvas.yview_moveto(0.0)

            win.protocol("WM_DELETE_WINDOW", cancel)
            flush_redraw()
            win.after_idle(fit_editor_window_to_content)
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("grabber.gravestone_editor_open_failed", error=exc), parent=self)

    def _graveyard_save_selected(self):
        name = self._selected_graveyard_name()
        if not name:
            return
        record = self._record_for_name(name)
        session = self._graveyard_session(record)
        reset = bool(record.get("graveyardReset"))
        if not (reset or session) or not record.get("graveTemplateId"):
            return
        try:
            historical, missing = self._graveyard_history_paths(record)
            if session:
                draft = session.get("draftPortrait")
                if draft and Path(draft).is_file():
                    historical.parent.mkdir(parents=True, exist_ok=True)
                    staged = historical.with_suffix(historical.suffix + ".tmp")
                    shutil.copy2(Path(draft), staged)
                    os.replace(staged, historical)
                    missing.unlink(missing_ok=True)
            elif reset:
                if historical.is_file():
                    missing.unlink(missing_ok=True)
                else:
                    missing.parent.mkdir(parents=True, exist_ok=True)
                    missing.touch(exist_ok=True)
            self._write_graveyard_action(record, "save")
            category = normalize_gravestone_category(record.get("gravestoneCategory"))
            if category is not None:
                checker = self._checker_graveyard_support()
                update_manifest_gravestone_category(
                    checker.gravestone_manifest_path(),
                    str(record.get("graveTemplateId") or ""),
                    category,
                )
                self._graveyard_editor_inventory_cache = None
            if session:
                self._graveyard_cleanup_session(record)
            record["graveyardReset"] = False
            self.status_var.set(tr("grabber.graveyard_saved_locked", name=name))
            self._log(tr("grabber.graveyard_saved_log", name=name))
            self._populate_graveyard_tree()
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("grabber.graveyard_save_failed", error=exc), parent=self)

    def _review_imports(self):
        root_text = str(suite_root_dir())
        if root_text not in sys.path:
            sys.path.insert(0, root_text)
        from tools.gravestone_review.gravestone_review_core import (
            ensure_workspace, review_counts, setup_review_logging,
        )
        return ensure_workspace, review_counts, setup_review_logging

    def _refresh_gravestone_review_counts(self):
        try:
            ensure_workspace, review_counts, _setup = self._review_imports()
            workspace = ensure_workspace(suite_root_dir())
            counts = review_counts(workspace)
            self.review_candidates_var.set(tr("grabber.gravestone_candidates", count=counts.candidates))
            self.review_accepted_var.set(tr("grabber.gravestone_accepted", count=counts.accepted))
            self.review_approved_var.set(tr("grabber.gravestone_approved", count=counts.approved))
            self.review_rejected_var.set(tr("grabber.gravestone_rejected", count=counts.rejected))
        except Exception as exc:
            if hasattr(self, "status_var"):
                self.status_var.set(tr("grabber.gravestone_review_unavailable", error=exc))

    def _notebook_tab_changed(self, _event=None):
        try:
            current = self.notebook.select()
            if current and self.notebook.tab(current, "text") == tr("grabber.gravestone_review"):
                self._refresh_gravestone_review_counts()
                self._ensure_embedded_gravestone_review()
        except Exception as exc:
            self._log(tr("grabber.gravestone_review_unavailable", error=exc))

    def _open_gravestone_candidates(self):
        try:
            ensure_workspace, _review_counts, _setup = self._review_imports()
            workspace = ensure_workspace(suite_root_dir())
            workspace.candidates.mkdir(parents=True, exist_ok=True)
            if hasattr(os, "startfile"):
                os.startfile(str(workspace.candidates))  # type: ignore[attr-defined]
            else:
                webbrowser.open(workspace.candidates.resolve().as_uri())
        except Exception as exc:
            messagebox.showerror(
                tr("grabber.gravestone_review"),
                tr("grabber.gravestone_review_unavailable", error=exc), parent=self,
            )

    def _ensure_embedded_gravestone_review(self):
        if self._embedded_review_app is not None:
            try:
                self._embedded_review_app.reload_candidates()
            except Exception:
                pass
            return
        try:
            ensure_workspace, _review_counts, setup_review_logging = self._review_imports()
            from tools.gravestone_review.gravestone_review_tool import ReviewApp
            workspace = ensure_workspace(suite_root_dir())
            setup_review_logging(workspace.logs)
            if hasattr(self, "review_placeholder") and self.review_placeholder.winfo_exists():
                self.review_placeholder.destroy()
            self._embedded_review_app = ReviewApp(
                self.review_frame, suite_root_dir(), suite_root_dir() / "tools" / "gravestone_review",
            )
        except Exception as exc:
            messagebox.showerror(
                tr("grabber.gravestone_review"),
                tr("grabber.gravestone_review_unavailable", error=exc), parent=self,
            )
            self._log(tr("grabber.gravestone_review_unavailable", error=exc))

    def _open_gravestone_review(self):
        self._ensure_embedded_gravestone_review()

    def _test_browser(self):
        self.status_var.set(tr("grabber.test_browser_running")); self._log(tr("grabber.test_browser_running"))
        self.worker.submit("test_browser", **self._common_payload())

    def _open_selected(self):
        name=self._selected_name()
        if not name: return
        mode=self.config_data.get("capture_mode","playwright")
        self.status_by_name[name]=tr("grabber.worker_opening", name=name); self._populate_tree()
        self.worker.submit("open", name=name, member_id=self._record_for_name(name).get("memberId"), **self._common_payload())
        self._log(tr("grabber.open_log", name=name, method=capture_mode_display(mode)))

    def _validate_region_for_standard(self) -> bool:
        if self.capture_mode_var.get()!=CAPTURE_MODE_STANDARD: return True
        ok,msg=validate_screen_region(self._current_screen_region())
        if not ok:
            messagebox.showinfo(tr("grabber.region_title"), msg+"\n\n"+tr("grabber.set_region_first"))
            return False
        return True

    def _capture_selected(self):
        name=self._selected_name()
        output = self._require_project()
        if not name or output is None or not self._validate_region_for_standard(): return
        self.status_by_name[name]=tr("grabber.creating_portrait"); self._populate_tree()
        payload=self._common_payload(); payload.update(output_dir=str(output), crop=self.config_data.get("crop",clamp_crop({})), navigate=True)
        self.worker.submit("capture", name=name, member_id=self._record_for_name(name).get("memberId"), **payload); self._log(tr("grabber.portrait_started", name=name))

    def _calibrate_selected(self):
        name=self._selected_name()
        if not name: return
        # This is deliberately the exact v0.1.2 raw-viewer calibration path.
        self.status_by_name[name]=tr("grabber.loading_calibration"); self._populate_tree()
        payload=self._common_payload(); payload["capture_mode"]="playwright"
        self.worker.submit("capture_raw", name=name, member_id=self._record_for_name(name).get("memberId"), navigate=True, **payload)
        self._log(tr("grabber.calibration_started", name=name))

    def _start_batch(self, names: list[str], title: str, overwrite_existing: bool):
        names = dedupe_names(names)
        output = self._require_project()
        if not names or self.batch_running or output is None:
            return
        if not self._validate_region_for_standard():
            return
        mode = capture_mode_display(capture_mode_from_display(self.capture_mode_var.get()))
        overwrite_text = tr("grabber.overwrite_yes") if overwrite_existing else tr("grabber.overwrite_no")
        if not messagebox.askyesno(title, tr("grabber.batch_question", count=len(names), mode=mode, overwrite=overwrite_text)):
            return
        self.batch_running = True
        for btn in (self.open_btn, self.single_btn, self.missing_btn, self.all_btn,
                    self.read_data_btn, self.read_missing_data_btn):
            btn.configure(state="disabled")
        self.stop_btn.configure(state="normal", text=tr("grabber.stop"))
        self.progress["maximum"] = max(1, len(names)); self.progress["value"] = 0
        payload = self._common_payload(); payload.update(
            output_dir=str(output), crop=self.config_data.get("crop", clamp_crop({})),
            character_records=self._records_for_names(names),
        )
        self.worker.submit("capture_all", names=list(names), **payload)
        self._log(tr("grabber.batch_started", title=title, count=len(names), mode=mode))

    def _capture_missing(self):
        missing = self._missing_names()
        if not missing:
            self.status_var.set(tr("grabber.nothing_missing"))
            self._log(tr("grabber.nothing_missing_log"))
            self._refresh_summary()
            return
        self._start_batch(missing, tr("grabber.create_missing"), overwrite_existing=False)

    def _capture_all(self):
        self._start_batch(list(self.names), tr("grabber.create_all"), overwrite_existing=True)

    def _read_selected_data(self):
        name = self._selected_name()
        if not name:
            return
        if self.batch_running:
            return
        record = self._record_for_name(name)
        self.status_by_name[name] = tr("grabber.reading_data")
        self._populate_tree()
        self.worker.submit(
            "read_data", name=name, member_id=record.get("memberId"),
            **self._common_payload(),
        )
        self._log(tr("grabber.reading_data_for", name=name))

    def _read_missing_data(self):
        records = records_missing_armory_data(self._records_for_names(self.names))
        if not records or self.batch_running:
            self.status_var.set(tr("grabber.no_missing_data"))
            return
        if not messagebox.askyesno(
            tr("grabber.read_missing_data"),
            tr("grabber.read_data_batch_question", count=len(records)), parent=self,
        ):
            return
        self.batch_running = True
        for btn in (self.open_btn, self.single_btn, self.missing_btn, self.all_btn,
                    self.read_data_btn, self.read_missing_data_btn):
            btn.configure(state="disabled")
        self.stop_btn.configure(state="normal", text=tr("grabber.stop"))
        self.progress["maximum"] = max(1, len(records)); self.progress["value"] = 0
        self.worker.submit("read_data_all", records=records, **self._common_payload())
        self._log(tr("grabber.read_data_batch_started", count=len(records)))

    def _request_stop(self):
        if not self.batch_running: return
        self.worker.request_batch_cancel(); self.stop_btn.configure(state="disabled",text=tr("grabber.stop_requested_short"))
        self.status_var.set(tr("grabber.stop_requested"))
        self._log("STOPP angefordert.")

    def _set_default_region(self):
        if self.batch_running:
            messagebox.showinfo(tr("grabber.region_title"),tr("grabber.stop_batch_first")); return
        self._save_settings(); self.status_var.set(tr("grabber.region_capture_start")); self._log(tr("grabber.region_capture_start"))
        self.withdraw()
        def grab():
            try:
                bounds=virtual_screen_bounds(); bx,by,bw,bh=bounds
                shot=ImageGrab.grab(bbox=(bx,by,bx+bw,by+bh),all_screens=True).convert("RGB")
                self.deiconify(); self.lift()
                ScreenRegionSelector(self,shot,bounds,self._accept_default_region)
            except Exception as exc:
                self.deiconify(); ScrollableTextDialog(self, tr("grabber.region_title"), tr("grabber.region_capture_failed", error=exc))
        self.after(350,grab)

    def _accept_default_region(self,region):
        x,y,w,h=normalize_screen_region(region); self.screen_x_var.set(x); self.screen_y_var.set(y); self.screen_w_var.set(w); self.screen_h_var.set(h)
        self._refresh_region_text(); self._save_settings(); self._log(tr("grabber.region_saved_log", x=x, y=y, width=w, height=h))
        self.status_var.set(tr("grabber.region_saved"))

    def _test_default_region(self):
        reg=self._current_screen_region(); ok,msg=validate_screen_region(reg)
        if not ok:
            messagebox.showinfo(tr("grabber.region_title"),msg+"\n\n"+tr("grabber.set_region_first")); return
        try:
            image=capture_screen_region(reg); ImagePreviewDialog(self,image,tr("grabber.test_region"))
            self._log(tr("grabber.region_tested_log", width=reg[2], height=reg[3]))
        except Exception as exc:
            ScrollableTextDialog(self, tr("grabber.test_region"), str(exc))

    def _reset_default_region(self):
        if validate_screen_region(self._current_screen_region())[0] and not messagebox.askyesno(tr("grabber.region_title"),tr("grabber.reset_region_question")):
            return
        self.screen_x_var.set(0); self.screen_y_var.set(0); self.screen_w_var.set(0); self.screen_h_var.set(0)
        self._refresh_region_text(); self._save_settings(); self._log(tr("grabber.region_reset_log"))

    def _open_output_folder(self):
        p=self._require_project()
        if p is None: return
        p.mkdir(parents=True,exist_ok=True)
        try: os.startfile(str(p))  # type: ignore[attr-defined]
        except Exception: ScrollableTextDialog(self, tr("grabber.output_folder"), str(p))

    def _poll_events(self):
        try:
            while True: self._handle_event(self.events.get_nowait())
        except queue.Empty: pass
        self.after(100,self._poll_events)

    def _persist_armory_results(self) -> None:
        payload = {
            "format": ARMORY_RESULT_FORMAT,
            "formatVersion": ARMORY_RESULT_VERSION,
            "sessionId": self.armory_context.get("sessionId"),
            "region": self.region_var.get().strip() or DEFAULT_REGION,
            "realm": self.realm_var.get().strip() or DEFAULT_REALM,
            "gameVersion": self.game_var.get().strip() or DEFAULT_GAME_VERSION,
            "results": list(self.armory_results.values()),
        }
        write_armory_results(
            suite_root_dir() / "data" / "runtime" / "armory_character_data.json",
            payload,
        )

    def _character_cache_path(self) -> Path:
        return character_cache_path(suite_root_dir())

    def _store_armory_result(self, result: dict) -> None:
        name = str(result.get("characterName") or "").strip()
        if not name:
            return
        record = self._record_for_name(name)
        expected_id = record.get("memberId")
        incoming_id = str(result.get("memberId") or "").strip() or None
        if expected_id and incoming_id != expected_id:
            return
        merge_armory_data(record, result)
        key = incoming_id or name.casefold()
        self.armory_results[key] = dict(result)
        self._persist_armory_results()
        if self.project_path is not None and (incoming_id or expected_id):
            try:
                self._dispatch_project_action(
                    "update_member_metadata",
                    {
                        "memberId": incoming_id or expected_id,
                        "race": result.get("race"),
                        "className": result.get("className"),
                    },
                )
            except Exception as exc:
                self._log(tr("grabber.project_metadata_save_failed", error=exc))
        try:
            update_character_cache(
                self._character_cache_path(),
                member_id=incoming_id or expected_id,
                character_name=name,
                region=self.region_var.get().strip() or DEFAULT_REGION,
                realm=self.realm_var.get().strip() or DEFAULT_REALM,
                game_version=self.game_var.get().strip() or DEFAULT_GAME_VERSION,
                race=result.get("race"),
                class_name=result.get("className"),
                updated_at=result.get("retrievedAt"),
            )
        except Exception as exc:
            self._log(tr("grabber.character_cache_error", error=exc))
        # BEGIN LEGACY_GUILD_ROSTER_FETCH_SNAPSHOT_ENRICHMENT
        try:
            merge_snapshot_member_data(
                self._guild_snapshot_path(), name, result.get("race"), result.get("className"),
            )
        except Exception as exc:
            self._log(tr("grabber.guild_snapshot_metadata_error", error=exc))
        # END LEGACY_GUILD_ROSTER_FETCH_SNAPSHOT_ENRICHMENT

    def _handle_event(self, event: dict):
        semantic = interpret_worker_event(event)
        name = semantic.get("name", "")
        action = semantic.get("action") or {}

        # BEGIN LEGACY_GUILD_ROSTER_FETCH_EVENTS
        if action.get("type") == "store_guild_roster_snapshot":
            try:
                path = self._store_guild_roster_snapshot(action["event"])
                count = len(event.get("names") or [])
                message = tr("grabber.guild_roster_ready", count=count, path=path)
                self.status_var.set(message)
                self._log(message)
                self._populate_tree()
            except Exception as exc:
                message = tr("grabber.guild_roster_error", error=exc)
                self.status_var.set(message)
                self._log(message)
                messagebox.showerror(tr("grabber.guild_roster_title"), message, parent=self)
            finally:
                self.guild_fetch_running = False
                self.guild_fetch_btn.configure(
                    state="normal" if LEGACY_GUILD_ROSTER_FETCH_ENABLED else "disabled"
                )
            return
        if action.get("type") == "finish_guild_roster":
            self.guild_fetch_running = False
            self.guild_fetch_btn.configure(
                state="normal" if LEGACY_GUILD_ROSTER_FETCH_ENABLED else "disabled"
            )
        # END LEGACY_GUILD_ROSTER_FETCH_EVENTS

        model_action = semantic.get("model_action") or {}
        if model_action.get("type") == "store_armory_result":
            self._store_armory_result(model_action["result"])

        if action.get("type") == "batch_progress":
            self.progress["maximum"] = action["maximum"]
            self.progress["value"] = action["value"]
        elif action.get("type") == "batch_done":
            self.batch_running = False
            for button in (
                self.open_btn,
                self.single_btn,
                self.missing_btn,
                self.all_btn,
                self.read_data_btn,
                self.read_missing_data_btn,
            ):
                button.configure(state="normal")
            self._update_project_controls()
            self.stop_btn.configure(state="disabled", text=tr("grabber.stop"))
            self.progress["value"] = action["processed"]

        if "name_status" in semantic:
            self.status_by_name[name] = semantic["name_status"]
        if "status" in semantic:
            self.status_var.set(semantic["status"])
        if "log" in semantic:
            self._log(semantic["log"])
        if semantic.get("refresh_tree"):
            self._populate_tree()

        if action.get("type") == "refresh_portrait":
            self._show_portrait_preview(action["name"])
        elif action.get("type") == "open_crop_dialog":
            path = Path(action["path"])
            CropDialog(
                self,
                path,
                self.config_data.get("crop", clamp_crop({})),
                lambda crop, n=action["name"], p=path: self._apply_calibration(crop, n, p),
            )

        dialog = semantic.get("dialog") or {}
        if dialog.get("type") == "info":
            messagebox.showinfo(dialog["title"], dialog["message"])
        elif dialog.get("type") == "error":
            messagebox.showerror(dialog["title"], dialog["message"], parent=self)
        elif dialog.get("type") == "text":
            ScrollableTextDialog(self, dialog["title"], dialog["message"])

    def _apply_calibration(self,crop:dict,name:str,raw_path:Path):
        self.config_data["crop"]=clamp_crop(crop); self._save_settings()
        try:
            output = self._require_project()
            if output is None: return
            member_id = str(self._record_for_name(name).get("memberId") or "")
            dest=normal_portrait_path(member_id, self.project_path); crop_portrait(raw_path,dest,crop)
            self.status_by_name[name]=tr("grabber.portrait_saved"); self.status_var.set(tr("grabber.crop_saved"))
            self._log(tr("grabber.crop_calibrated", name=name)); self._populate_tree(); self._show_portrait_preview(name)
        except Exception as exc:
            ScrollableTextDialog(self, tr("common.portrait"), str(exc))

    def _on_close(self):
        try:
            if self.state() == "normal":
                update_suite_settings(self._suite_settings_path, grabber_geometry=self.geometry())
            self._graveyard_cleanup_all_sessions()
            self._save_settings(); self.worker.request_batch_cancel(); self.worker.submit("stop")
        finally:
            self.destroy()

def run_self_test() -> int:
    """Fast offline checks. No live website/browser is required."""
    print(f"{APP_NAME} v{APP_VERSION} - Selbsttest")
    failures = []

    def check(name, fn):
        try:
            fn()
            print(f"[OK] {name}")
        except Exception as exc:
            failures.append((name, exc))
            print(f"[FEHLER] {name}: {exc}")

    check("Version", lambda: (_ for _ in ()).throw(AssertionError(APP_VERSION)) if APP_VERSION != "0.11.3-test3" else None)
    check("Armory-Gildenabruf deaktiviert", lambda: (_ for _ in ()).throw(AssertionError()) if LEGACY_GUILD_ROSTER_FETCH_ENABLED else None)
    check("URL + Unicode", lambda: (_ for _ in ()).throw(AssertionError("URL falsch")) if "%C3%81nn%C3%ADe" not in build_armory_url("Ánníe") else None)
    check("Dateiname Sonderzeichen", lambda: (_ for _ in ()).throw(AssertionError("Dateiname falsch")) if safe_filename('A:b?c*') != "A_b_c_" else None)

    def test_current_page_matching():
        worker = BrowserWorker(queue.Queue())
        worker._page = type("FakePage", (), {"url": build_armory_url("Bífi") + "&foo=bar"})()
        assert worker._current_page_is_character("Bífi", "EU", "stitches", "classic1x")
        assert not worker._current_page_is_character("Sorap", "EU", "stitches", "classic1x")
    check("v0.1.2 manuelle Browserposition bleibt erhalten", test_current_page_matching)

    def test_empty_error_message():
        worker = BrowserWorker(queue.Queue())
        assert worker._format_error(AssertionError()) == "AssertionError"
    check("Leere Exceptions werden sichtbar", test_empty_error_message)

    def test_browser_fallback_order():
        src = Path(__file__).read_text(encoding="utf-8")
        edge_pos = src.find('(\"msedge\", \"Microsoft Edge\")')
        chrome_pos = src.find('(\"chrome\", \"Google Chrome\")')
        assert edge_pos >= 0 and chrome_pos > edge_pos
    check("v0.1.2 Browser-Reihenfolge Edge vor Chrome", test_browser_fallback_order)

    check("Standardbereich innerhalb Desktop", lambda: (_ for _ in ()).throw(AssertionError()) if not validate_screen_region((100,100,300,525),(0,0,1920,1080))[0] else None)
    check("Standardbereich Multi-Monitor negativ", lambda: (_ for _ in ()).throw(AssertionError()) if not validate_screen_region((-1200,100,300,525),(-1280,0,3200,1080))[0] else None)
    check("Zu kleiner Standardbereich abgelehnt", lambda: (_ for _ in ()).throw(AssertionError()) if validate_screen_region((0,0,20,20),(0,0,1920,1080))[0] else None)

    def test_stop_flag():
        worker=BrowserWorker(queue.Queue())
        worker._batch_cancel.clear(); assert not worker._batch_cancel.is_set()
        worker.request_batch_cancel(); assert worker._batch_cancel.is_set()
    check("STOPP-Flag thread-safe", test_stop_flag)

    with tempfile.TemporaryDirectory() as td_raw:
        td = Path(td_raw)

        def test_txt():
            q = td / "names.txt"; q.write_text("Bífi\nSorap\nBífi\nÁnníe\n", encoding="utf-8")
            assert parse_txt_names(q) == ["Bífi", "Sorap", "Ánníe"]
        check("TXT-Import", test_txt)

        def test_csv():
            q = td / "raid.csv"; q.write_text("Name;Amount;Active Time\nBämäräng;1;2\nTazgø;3;4\n", encoding="utf-8-sig")
            assert parse_csv_names(q) == ["Bämäräng", "Tazgø"]
        check("CSV-Import Name-Spalte", test_csv)

        def test_ggc():
            q = td / "guild.ggc"
            q.write_text(json.dumps({"members":[
                {"name":"Aktivchar","lifeStatus":"active"},
                {"name":"Inaktivchar","lifeStatus":"inactive"},
                {"name":"Totchar","lifeStatus":"dead"}
            ]},ensure_ascii=False),encoding="utf-8")
            assert parse_ggc_names(q, True) == ["Aktivchar"]
            assert parse_ggc_names(q, False) == ["Aktivchar","Inaktivchar","Totchar"]
        check("GGC-Import Aktiv/Inaktiv/Tot", test_ggc)

        def test_crop():
            src=td/"raw.png"; dst=td/"portrait.png"
            Image.new("RGB",(800,1000),(120,50,20)).save(src)
            crop_portrait(src,dst,{"x1":.2,"y1":.1,"x2":.8,"y2":.7})
            with Image.open(dst) as im:
                assert im.size==(384,672) and im.mode=="RGB"
        check("v0.1.2 Bildcrop 384x672", test_crop)

        def test_portrait_drag_crop_ratio():
            x1, y1, x2, y2 = portrait_selection_rect(20, 30, 270, 500, 320, 560)
            width = x2 - x1; height = y2 - y1
            assert width > 0 and height > 0
            assert abs((width / height) - (PORTRAIT_WIDTH / PORTRAIT_HEIGHT)) < 1e-9
            assert 0 <= x1 < x2 <= 320 and 0 <= y1 < y2 <= 560
        check("Portrait-Editor Ziehausschnitt 4:7", test_portrait_drag_crop_ratio)

        def test_portrait_drag_crop_maps_to_source():
            selection = (80.0, 140.0, 240.0, 420.0)
            box = portrait_source_crop_box(selection, (800, 1400), 0.4, 0, 0)
            assert box == (200, 350, 600, 1050)
            reversed_selection = portrait_selection_rect(
                240, 420, 80, 140, 320, 560,
            )
            assert reversed_selection == selection
            bounded_selection = portrait_selection_rect(
                300, 540, 500, 900, 320, 560,
            )
            assert 0 <= bounded_selection[0] <= bounded_selection[2] <= 320
            assert 0 <= bounded_selection[1] <= bounded_selection[3] <= 560
            state = PortraitEditorState(
                source_path=td / "unused.png",
                source_size=(800, 1400),
            )
            assert portrait_editor_crop_box(state, selection) == (200, 350, 600, 1050)
        check("Portrait-Editor Ziehausschnitt bleibt hochaufloesend", test_portrait_drag_crop_maps_to_source)

        def test_portrait_editor_state():
            source = td / "editor_state.png"
            Image.new("RGB", (384, 672), (30, 60, 90)).save(source)
            state = load_portrait_editor_state(source)
            assert state.source_path == source
            assert state.source_size == (384, 672)
            assert (state.zoom, state.offset_x, state.offset_y) == (1.0, 0.0, 0.0)
            assert state.reset() == state
            assert portrait_editor_pan(state, 30.0, -30.0) == state
            zoomed = portrait_editor_zoom(state, 1.0)
            assert zoomed.zoom == 2.0
            moved = portrait_editor_pan(zoomed, 30.0, -25.0)
            assert (moved.offset_x, moved.offset_y) == (30.0, -25.0)
            assert portrait_editor_zoom(state, -10.0).zoom == 1.0
            assert portrait_editor_zoom(state, 10.0).zoom == 4.0
        check("Portrait-Editor UI-neutraler Ausgangszustand", test_portrait_editor_state)

        def test_portrait_editor_final_output():
            source = td / "editor_output.png"
            pattern = Image.new("RGB", (640, 900))
            for x in range(pattern.width):
                for y in range(pattern.height):
                    pattern.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
            pattern.save(source)
            base_state = load_portrait_editor_state(source)
            adjusted_state = portrait_editor_transform(
                base_state, zoom=1.75, offset_x=45.0, offset_y=-30.0,
            )
            first = render_portrait_editor_state(adjusted_state)
            second = render_portrait_editor_state(adjusted_state)
            assert first.size == (PORTRAIT_WIDTH, PORTRAIT_HEIGHT)
            assert first.mode == "RGB"
            assert first.tobytes() == second.tobytes()
            assert first.tobytes() != render_portrait_editor_state(base_state).tobytes()
            destination = td / "editor_saved.png"
            assert save_portrait_editor_state(adjusted_state, destination) == destination
            with Image.open(destination) as saved:
                assert saved.size == (PORTRAIT_WIDTH, PORTRAIT_HEIGHT)
                assert saved.convert("RGB").tobytes() == first.tobytes()
        check("Portrait-Editor finaler Crop deterministisch", test_portrait_editor_final_output)

        def test_portrait_editor_atomic_failure():
            source = td / "editor_failure_source.png"
            destination = td / "editor_failure_destination.png"
            Image.new("RGB", (500, 800), (20, 40, 60)).save(source)
            destination.write_bytes(b"bestehendes Portrait")
            original_replace = os.replace
            try:
                os.replace = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    PermissionError("gesperrt")
                )
                try:
                    save_portrait_editor_state(load_portrait_editor_state(source), destination)
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Schreibfehler wurde nicht weitergegeben")
            finally:
                os.replace = original_replace
            assert destination.read_bytes() == b"bestehendes Portrait"
            assert not destination.with_suffix(destination.suffix + ".edit.tmp").exists()
        check("Portrait-Editor Fehler erhaelt bestehende Datei", test_portrait_editor_atomic_failure)

        def test_screen_region_save():
            im=Image.new("RGB",(300,525),(20,20,20))
            for x in range(80,220):
                for y in range(100,420):
                    im.putpixel((x,y),(180,90,40))
            assert image_object_has_detail(im)
            dst=td/"region_portrait.png"; save_screen_region_portrait(im,dst)
            with Image.open(dst) as out:
                assert out.size==(384,672)
        check("Standardbereich -> 384x672 ohne Verzerrung", test_screen_region_save)

        def test_blank_detection():
            blank=td/"blank.png"; detailed=td/"detailed.png"
            Image.new("RGB",(100,100),(0,0,0)).save(blank)
            im=Image.new("RGB",(100,100),(0,0,0))
            for x in range(30,70):
                for y in range(30,70): im.putpixel((x,y),(255,255,255))
            im.save(detailed)
            assert not image_has_detail(blank) and image_has_detail(detailed)
            assert not image_object_has_detail(Image.new("RGB",(100,100),(0,0,0)))
            assert image_object_has_detail(im)
        check("Leere Screenshots werden erkannt", test_blank_detection)

        def test_standard_capture_without_network():
            worker=BrowserWorker(queue.Queue())
            original_open=webbrowser.open; original_capture=globals()["capture_screen_region"]; original_sleep=time.sleep
            out=td/"portraits"
            pattern=Image.new("RGB",(300,525),(10,10,10))
            for x in range(60,240):
                for y in range(70,470): pattern.putpixel((x,y),(160,80,30))
            try:
                webbrowser.open=lambda *a,**k: True
                globals()["capture_screen_region"]=lambda region: pattern.copy()
                time.sleep=lambda _s: None
                worker._capture_standard_character("Tazgø","EU","stitches","classic1x",str(out),(10,20,300,525),1, "m0001")
                assert (out/"m0001.png").exists()
                assert (app_data_dir()/"source"/"Tazgø_source.png").exists()
            finally:
                webbrowser.open=original_open; globals()["capture_screen_region"]=original_capture; time.sleep=original_sleep
        check("Standardbrowser-Aufnahme mock", test_standard_capture_without_network)

    try:
        import playwright  # noqa: F401
        print("[OK] Playwright-Pythonmodul vorhanden")
    except Exception as exc:
        failures.append(("Playwright-Pythonmodul", exc)); print("[FEHLER] Playwright-Pythonmodul fehlt")

    print()
    if failures:
        print(f"Selbsttest beendet: {len(failures)} Fehler")
        return 1
    print("Selbsttest beendet: alle Offline-Tests erfolgreich")
    print("Hinweis: Der Live-3D-Viewer kann nur auf einem PC mit Browser und Internet vollstaendig end-to-end getestet werden.")
    return 0


def parse_cli(argv=None):
    parser=argparse.ArgumentParser(add_help=True)
    parser.add_argument("--project",default="",help="Aktives GuildGearChecker-.ggc-Projekt")
    parser.add_argument("--session-id",default="",help="Session des laufenden Qt-Checkers")
    parser.add_argument("--roster-json",default="",help=argparse.SUPPRESS)
    parser.add_argument("--output-dir",default="",help=argparse.SUPPRESS)
    parser.add_argument("--self-test",action="store_true")
    return parser.parse_args(argv)


def main():
    args=parse_cli()
    if args.self_test:
        raise SystemExit(run_self_test())
    missing=[]
    if Image is None: missing.append("Pillow")
    try:
        import playwright  # noqa: F401
    except Exception:
        missing.append("Playwright")
    if missing:
        root=tk.Tk(); root.withdraw(); messagebox.showerror(APP_NAME,tr("grabber.missing_packages", packages=", ".join(missing))); root.destroy(); return
    initial_names=None
    initial_characters=None
    armory_context=None
    project_argument = args.project or ""
    if project_argument:
        try:
            initial_characters,armory_context=parse_ggc_characters(Path(project_argument),active_only=False)
        except Exception as exc:
            initial_names=None
            project_argument = ""
            print(f"Projekt konnte nicht gelesen werden: {exc}",file=sys.stderr)
    App(initial_names=initial_names,output_override=None,
        initial_characters=initial_characters,armory_context=armory_context,
        roster_json_path=None, project_path=project_argument or None,
        session_id=args.session_id or None).mainloop()


if __name__ == "__main__":
    main()
