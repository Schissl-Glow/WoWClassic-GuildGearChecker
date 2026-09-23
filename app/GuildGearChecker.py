# -*- coding: utf-8 -*-
"""
Guild Gear Checker - Python Suite v0.6.0
EU / Stitches / Classic Era

Stand v0.5.0:
- Reiter: Gildenliste, Handlungsbedarf, Ungeprueft, Friedhof, Alle Charaktere
- Friedhof mit Graveyard.jpg als Hintergrund
- komplette rechte Charakterspalte vertikal scrollbar (Mausrad + Scrollbar)
- projektgebundener Portraitordner neben der aktiven .ggc-Datei
- aktiver Portraitordner wird waehrend des Betriebs automatisch ueberwacht
- integrierter Start des mitgelieferten Guild Portrait Grabbers (zentral, nicht im Charakterbereich)
- aufgeraeumte Suite-Struktur: app/assets/data/config/docs/tests/tools
- Grabber erhaelt automatisch die aktuelle Gildenliste als Snapshot
- strukturierte Class/Spec-Auswahl mit englischen WoW-Begriffen
- lokale Class-Icons mit Wowhead/Zamimg-Cache und Offline-Fallback
- feste Portraitflaeche rechts: 220x220, auch ohne Bild
- Portraits werden proportional eingepasst, nicht zusaetzlich beschnitten

Projektformat bleibt kompatibel zur bisherigen .ggc-Struktur.
"""
from __future__ import annotations

import copy
import functools
import hashlib
import importlib.util
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
import urllib.parse
import uuid
import webbrowser
import zipfile
from dataclasses import dataclass, asdict, replace
from datetime import datetime, date
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    from app.project_storage import (
        atomic_write_bytes, backup_project_file, copy_project_portraits,
        member_portrait_path as stored_member_portrait_path, migrate_legacy_portraits,
        newer_autosave, portrait_root as project_portrait_root, project_paths,
    )
except ImportError:
    _storage_spec = importlib.util.spec_from_file_location(
        "guild_suite_project_storage", Path(__file__).resolve().with_name("project_storage.py")
    )
    _storage_module = importlib.util.module_from_spec(_storage_spec)
    sys.modules.setdefault(_storage_spec.name, _storage_module)
    _storage_spec.loader.exec_module(_storage_module)
    atomic_write_bytes = _storage_module.atomic_write_bytes
    backup_project_file = _storage_module.backup_project_file
    copy_project_portraits = _storage_module.copy_project_portraits
    stored_member_portrait_path = _storage_module.member_portrait_path
    migrate_legacy_portraits = _storage_module.migrate_legacy_portraits
    newer_autosave = _storage_module.newer_autosave
    project_portrait_root = _storage_module.portrait_root
    project_paths = _storage_module.project_paths

try:
    from app.csv_import import (
        decode_csv_bytes, detect_csv_name_details, detect_csv_names, normalize_csv_raid_type,
        raid_csv_filename_metadata, read_csv_name_details, read_csv_names, read_raid_csv,
    )
    from app.gravestone_templates import (
        MANIFEST_FILENAME as GRAVESTONE_MANIFEST_FILENAME,
        SUPPORTED_IMAGE_EXTENSIONS as GRAVESTONE_SUPPORTED_IMAGE_EXTENSIONS,
        GravestoneInventory, generate_gravestone_manifest, load_gravestone_inventory,
    )
    from app.raid_attendance import (
        ATTENDANCE_STATUSES, RAID_CATEGORIES, RAID_TYPES,
        AttendanceResolution, Raid, RaidAttendance, RaidValidationError, attendance_index,
        attendance_records, calculate_statistics, new_attendance_id, new_raid_id, normalize_iso_date,
        exact_name_key, normalize_optional_date,
        player_is_relevant, raid_category, resolve_attendance, validate_logs_url,
        validate_membership_dates,
    )
except ImportError:
    _csv_spec = importlib.util.spec_from_file_location(
        "guild_suite_csv_import", Path(__file__).resolve().with_name("csv_import.py")
    )
    _csv_module = importlib.util.module_from_spec(_csv_spec)
    sys.modules.setdefault(_csv_spec.name, _csv_module)
    _csv_spec.loader.exec_module(_csv_module)
    decode_csv_bytes = _csv_module.decode_csv_bytes
    detect_csv_name_details = _csv_module.detect_csv_name_details
    detect_csv_names = _csv_module.detect_csv_names
    normalize_csv_raid_type = _csv_module.normalize_csv_raid_type
    raid_csv_filename_metadata = _csv_module.raid_csv_filename_metadata
    read_csv_name_details = _csv_module.read_csv_name_details
    read_csv_names = _csv_module.read_csv_names
    read_raid_csv = _csv_module.read_raid_csv

    _grave_spec = importlib.util.spec_from_file_location(
        "guild_suite_gravestone_templates",
        Path(__file__).resolve().with_name("gravestone_templates.py"),
    )
    _grave_module = importlib.util.module_from_spec(_grave_spec)
    sys.modules.setdefault(_grave_spec.name, _grave_module)
    _grave_spec.loader.exec_module(_grave_module)
    GRAVESTONE_MANIFEST_FILENAME = _grave_module.MANIFEST_FILENAME
    GRAVESTONE_SUPPORTED_IMAGE_EXTENSIONS = _grave_module.SUPPORTED_IMAGE_EXTENSIONS
    GravestoneInventory = _grave_module.GravestoneInventory
    generate_gravestone_manifest = _grave_module.generate_gravestone_manifest
    load_gravestone_inventory = _grave_module.load_gravestone_inventory

    _raid_spec = importlib.util.spec_from_file_location(
        "guild_suite_raid_attendance", Path(__file__).resolve().with_name("raid_attendance.py")
    )
    _raid_module = importlib.util.module_from_spec(_raid_spec)
    sys.modules.setdefault(_raid_spec.name, _raid_module)
    _raid_spec.loader.exec_module(_raid_module)
    AttendanceResolution = _raid_module.AttendanceResolution
    ATTENDANCE_STATUSES = _raid_module.ATTENDANCE_STATUSES
    RAID_CATEGORIES = _raid_module.RAID_CATEGORIES
    RAID_TYPES = _raid_module.RAID_TYPES
    Raid = _raid_module.Raid
    RaidAttendance = _raid_module.RaidAttendance
    RaidValidationError = _raid_module.RaidValidationError
    attendance_index = _raid_module.attendance_index
    attendance_records = _raid_module.attendance_records
    calculate_statistics = _raid_module.calculate_statistics
    new_attendance_id = _raid_module.new_attendance_id
    new_raid_id = _raid_module.new_raid_id
    normalize_iso_date = _raid_module.normalize_iso_date
    exact_name_key = _raid_module.exact_name_key
    normalize_optional_date = _raid_module.normalize_optional_date
    player_is_relevant = _raid_module.player_is_relevant
    raid_category = _raid_module.raid_category
    resolve_attendance = _raid_module.resolve_attendance
    validate_logs_url = _raid_module.validate_logs_url
    validate_membership_dates = _raid_module.validate_membership_dates

try:
    from app.raid_points import RaidPointState, build_point_history
except ImportError:
    _raid_points_spec = importlib.util.spec_from_file_location(
        "guild_suite_raid_points", Path(__file__).resolve().with_name("raid_points.py")
    )
    _raid_points_module = importlib.util.module_from_spec(_raid_points_spec)
    sys.modules.setdefault(_raid_points_spec.name, _raid_points_module)
    _raid_points_spec.loader.exec_module(_raid_points_module)
    RaidPointState = _raid_points_module.RaidPointState
    build_point_history = _raid_points_module.build_point_history

try:
    from app.clm_history import EternalDkpState
except ImportError:
    _app_module_dir = str(Path(__file__).resolve().parent)
    if _app_module_dir not in sys.path:
        sys.path.insert(0, _app_module_dir)
    from clm_history import EternalDkpState  # type: ignore

try:
    from app.i18n import (
        get_language, language_display_values, language_from_display,
        race_display, race_display_values, race_from_display, set_language, tr,
    )
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
    race_display = _i18n_module.race_display
    race_display_values = _i18n_module.race_display_values
    race_from_display = _i18n_module.race_from_display
    set_language = _i18n_module.set_language
    tr = _i18n_module.tr

try:
    from app.gravestone_portrait import (
        GRAVESTONE_RENDER_ANALYSIS_SIZE,
        PortraitOpening as GravestonePortraitOpening,
        detect_portrait_opening as _detect_shared_gravestone_portrait_opening,
        fallback_portrait_opening as _fallback_shared_gravestone_portrait_opening,
        fit_portrait as _fit_shared_gravestone_portrait,
    )
except ImportError:
    _portrait_spec = importlib.util.spec_from_file_location(
        "guild_suite_gravestone_portrait", Path(__file__).resolve().with_name("gravestone_portrait.py")
    )
    _portrait_module = importlib.util.module_from_spec(_portrait_spec)
    sys.modules.setdefault(_portrait_spec.name, _portrait_module)
    _portrait_spec.loader.exec_module(_portrait_module)
    GRAVESTONE_RENDER_ANALYSIS_SIZE = _portrait_module.GRAVESTONE_RENDER_ANALYSIS_SIZE
    GravestonePortraitOpening = _portrait_module.PortraitOpening
    _detect_shared_gravestone_portrait_opening = _portrait_module.detect_portrait_opening
    _fallback_shared_gravestone_portrait_opening = _portrait_module.fallback_portrait_opening
    _fit_shared_gravestone_portrait = _portrait_module.fit_portrait

try:
    from app.font_utils import load_lifecraft_font
except ImportError:
    _font_spec = importlib.util.spec_from_file_location(
        "guild_suite_font_utils", Path(__file__).resolve().with_name("font_utils.py")
    )
    _font_module = importlib.util.module_from_spec(_font_spec)
    sys.modules.setdefault(_font_spec.name, _font_module)
    _font_spec.loader.exec_module(_font_module)
    load_lifecraft_font = _font_module.load_lifecraft_font

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

try:
    from app.guild_roster_sync import (
        compare_snapshot, load_snapshot, RosterComparisonItem,
    )
except ImportError:
    _guild_sync_spec = importlib.util.spec_from_file_location(
        "guild_suite_roster_sync", Path(__file__).resolve().with_name("guild_roster_sync.py")
    )
    _guild_sync_module = importlib.util.module_from_spec(_guild_sync_spec)
    sys.modules.setdefault(_guild_sync_spec.name, _guild_sync_module)
    _guild_sync_spec.loader.exec_module(_guild_sync_module)
    compare_snapshot = _guild_sync_module.compare_snapshot
    load_snapshot = _guild_sync_module.load_snapshot
    RosterComparisonItem = _guild_sync_module.RosterComparisonItem

try:
    from app.character_cache import (
        character_cache_path, find_character_cache_record, load_character_cache,
    )
except ImportError:
    _character_cache_spec = importlib.util.spec_from_file_location(
        "guild_suite_character_cache", Path(__file__).resolve().with_name("character_cache.py")
    )
    _character_cache_module = importlib.util.module_from_spec(_character_cache_spec)
    sys.modules.setdefault(_character_cache_spec.name, _character_cache_module)
    _character_cache_spec.loader.exec_module(_character_cache_module)
    character_cache_path = _character_cache_module.character_cache_path
    find_character_cache_record = _character_cache_module.find_character_cache_record
    load_character_cache = _character_cache_module.load_character_cache

APP_NAME = "Guild Gear Checker"
APP_VERSION = "0.11.3"
PROJECT_FORMAT = "GuildGearCheckerProject"
PROJECT_FORMAT_VERSION = 4
PROJECT_PACKAGE_FORMAT_VERSION = 1
ARMORY_RESULT_FORMAT = "GuildGearCheckerArmoryData"
ARMORY_RESULT_VERSION = 1
REGION = "EU"
REALM = "stitches"
GAME_VERSION = "classic1x"
POINT_MODE_RAID = "raid_points"
POINT_MODE_ETERNAL = "eternal_dkp"
POINT_MODES = (POINT_MODE_RAID, POINT_MODE_ETERNAL)
GUILD_ROSTER_SNAPSHOT_FILE = "guild_roster_snapshot.json"
GEAR_OUTDATED_DEFAULT_DAYS = 120

LOGGER = logging.getLogger(__name__)
RIGHT_PORTRAIT_SIZE = 220
CHECKER_BANNER_HEIGHT = 145
CHECKER_BANNER_FOCAL_POINT = (0.55, 0.46)
GRAVESTONE_TEMPLATE_FOLDER = Path("assets") / "graveyard"
GRAVESTONE_BACKGROUND_PATH = GRAVESTONE_TEMPLATE_FOLDER / "Background_001.png"
GRAVESTONE_MASTER_SIZE = (1074, 1464)
GRAVESTONE_CARD_SIZE = GRAVESTONE_RENDER_ANALYSIS_SIZE
GRAVESTONE_PORTRAIT_BOX = (304, 304, 770, 770)
GRAVESTONE_TEXT_SAFE_AREA = (250, 905, 824, 1090)
GRAVESTONE_TEXT_POSITIONS = {
    "name": (537, 940),
    "class": (537, 995),
    "death_date": (537, 1050),
}
GRAVESTONE_TEXT_FONT_SIZES = {"name": 62, "class": 46, "death_date": 46}
GRAVESTONE_TEXT_MIN_FONT_SIZES = {"name": 42, "class": 38, "death_date": 38}
GRAVESTONE_PORTRAIT_OFFSET_RANGE = (-1.0, 1.0)
GRAVESTONE_PORTRAIT_ZOOM_RANGE = (1.0, 2.0)
GRAVESTONE_TEXT_OFFSET_RANGE = (-1.0, 1.0)
GRAVESTONE_TEXT_SCALE_RANGE = (0.65, 1.5)
GRAVESTONE_TEXT_OFFSET_FACTOR = (0.28, 0.40)
GRAVESTONE_EDITOR_SIZE = (330, 450)
GRAVESTONE_GRID_PADDING = 24
GRAVESTONE_GRID_GAP = (16, 18)
GRAVESTONE_HEADER_BOTTOM = 118
ROSTER_PORTRAIT_SIZE = (170, 210)
ROSTER_CARD_WIDTH = 220
ROSTER_CARD_HEIGHT = 430
ROSTER_ZOOM_MIN = 60
ROSTER_ZOOM_MAX = 140
ROSTER_ZOOM_STEP = 10
ROSTER_EXPORT_CARD_SIZE = (450, 650)
ROSTER_EXPORT_COLUMNS_MIN = 5
ROSTER_EXPORT_COLUMNS_MAX = 6

SEED_NAMES = [
    "Aba", "Albinoanton", "Burgûs", "Bífi", "Dirksson", "Gigagenossin",
    "Gullinborsti", "Janos", "Kolben", "Opine", "Schlübbeer", "Schneeflocke",
    "Soregdrei", "Sysem", "Tiberior", "Varnika", "Venog", "Wariwariluke",
    "Zwirrlin", "Ánníe",
]
GEAR_VALUES = ["Level", "Pre-BiS", "BiS", "S+"]
RAID_STATUS_VALUES = ["", "Bereit", "Nicht bereit"]
RAID_STATUS_KEYS = {
    "ready": "Bereit",
    "not_ready": "Nicht bereit",
}
ENCHANT_VALUES = ["Nicht geprüft", "OK", "Fehlt"]
GEAR_STATUS_KEYS = {
    "level": "Level",
    "pre_bis": "Pre-BiS",
    "bis": "BiS",
    "s_plus": "S+",
}
ENCHANT_STATUS_KEYS = {
    "not_checked": "Nicht geprüft",
    "okay": "OK",
    "missing": "Fehlt",
}
LIFE_STATUSES = ("active", "inactive", "dead")
CHARACTER_TYPES = ("not_set", "main", "twink")
# "main_tank" war eine frühere, rein darstellerische Unterteilung.  Der
# produktive Rollenkanon kennt nur noch Tank, Heiler und DPS.
RAID_ROLES = ("not_set", "tank", "healer", "dps")
LEGACY_TANK_ROLES = {"main_tank", "main tank", "main tanks"}
RACE_NAMES = ("Human", "Dwarf", "Night Elf", "Gnome", "Orc", "Undead", "Tauren", "Troll")
TAB_ORDER = ["Gildenliste", "Handlungsbedarf", "Ungeprüft", "Inaktiv", "Friedhof", "Alle Charaktere", "Roster", "Raids"]
TAB_TRANSLATION_KEYS = {
    "Gildenliste": "tabs.guild",
    "Handlungsbedarf": "tabs.action",
    "Ungeprüft": "tabs.unchecked",
    "Inaktiv": "tabs.inactive",
    "Friedhof": "tabs.graveyard",
    "Alle Charaktere": "tabs.all_characters",
    "Roster": "tabs.roster",
    "Raids": "tabs.raids",
}


def _status_key(value: str, values: dict[str, str], fallback: str = "not_checked") -> str:
    normalized = str(value or "").strip().casefold()
    for key, legacy_value in values.items():
        if normalized in {key.casefold(), legacy_value.casefold()}:
            return key
    return fallback


def gear_status_key(value: str) -> str:
    """Return a language-independent key without rewriting legacy project data."""
    key = _status_key(value, GEAR_STATUS_KEYS, fallback="level")
    return key if key in GEAR_STATUS_KEYS else "level"


def raid_status_key(value: str) -> str | None:
    folded = str(value or "").strip().casefold()
    aliases = {
        "ready": {"ready", "bereit"},
        "not_ready": {"not_ready", "not ready", "nicht bereit"},
    }
    for key, accepted in aliases.items():
        if folded in accepted:
            return key
    return None


def raid_status_display(value: str) -> str:
    key = raid_status_key(value)
    return tr(f"raid_status.{key}") if key else tr("raid_status.not_set")


def raid_status_from_display(value: str) -> str:
    key = raid_status_key(value)
    return RAID_STATUS_KEYS.get(key, "") if key else ""


def enchant_status_key(value: str) -> str:
    """Return a language-independent key without rewriting legacy project data."""
    return _status_key(value, ENCHANT_STATUS_KEYS)


def gear_status_display(value: str) -> str:
    return tr(f"gear.{gear_status_key(value)}")


def enchant_status_display(value: str) -> str:
    return tr(f"enchants.{enchant_status_key(value)}")


def gear_status_from_display(value: str) -> str:
    folded = str(value or "").strip().casefold()
    for key, stored in GEAR_STATUS_KEYS.items():
        if folded in {stored.casefold(), tr(f"gear.{key}").casefold(), key.casefold()}:
            return stored
    return GEAR_VALUES[0]


def enchant_status_from_display(value: str) -> str:
    folded = str(value or "").strip().casefold()
    for key, stored in ENCHANT_STATUS_KEYS.items():
        if folded in {stored.casefold(), tr(f"enchants.{key}").casefold(), key.casefold()}:
            return stored
    return ENCHANT_VALUES[0]


def character_type_display(value: str) -> str:
    key = value if value in CHARACTER_TYPES else "not_set"
    return tr(f"character_type.{key}")


def character_type_from_display(value: str) -> str:
    folded = str(value or "").strip().casefold()
    return next((key for key in CHARACTER_TYPES
                 if folded in {key.casefold(), tr(f"character_type.{key}").casefold()}), "not_set")


def raid_role_display(value: str) -> str:
    key = normalize_raid_role(value)
    return tr(f"raid_role.{key}")


def raid_role_from_display(value: str) -> str:
    folded = str(value or "").strip().casefold()
    if folded in LEGACY_TANK_ROLES:
        return "tank"
    return next((key for key in RAID_ROLES
                 if folded in {key.casefold(), tr(f"raid_role.{key}").casefold()}), "not_set")


def normalize_raid_role(value: object) -> str:
    """Map legacy Main-Tank spellings to the single persisted tank role."""
    normalized = str(value or "").strip().casefold()
    if normalized in LEGACY_TANK_ROLES:
        return "tank"
    return normalized if normalized in RAID_ROLES else "not_set"


def raid_error_text(error: Exception) -> str:
    if isinstance(error, RaidValidationError):
        return tr(f"raids.{error.code}", **error.values)
    return str(error)

CLASS_SPECS = {
    "Druid": ["Balance", "Feral", "Restoration"],
    "Hunter": ["Beast Mastery", "Marksmanship", "Survival"],
    "Mage": ["Arcane", "Fire", "Frost"],
    "Paladin": ["Holy", "Protection", "Retribution"],
    "Priest": ["Discipline", "Holy", "Shadow"],
    "Rogue": ["Assassination", "Combat", "Subtlety"],
    "Shaman": ["Elemental", "Enhancement", "Restoration"],
    "Warlock": ["Affliction", "Demonology", "Destruction"],
    "Warrior": ["Arms", "Fury", "Protection"],
}
CLASS_NAMES = list(CLASS_SPECS.keys())
CLASS_ICON_URLS = {
    cls: f"https://wow.zamimg.com/images/wow/icons/large/classicon_{cls.lower()}.jpg"
    for cls in CLASS_NAMES
}
CLASS_COLORS = {
    "Druid": "#FF7C0A", "Hunter": "#AAD372", "Mage": "#3FC7EB",
    "Paladin": "#F48CBA", "Priest": "#FFFFFF", "Rogue": "#FFF468",
    "Shaman": "#0070DD", "Warlock": "#8788EE", "Warrior": "#C69B6D",
}

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageTk  # type: ignore
except Exception:
    Image = ImageChops = ImageDraw = ImageFilter = ImageFont = ImageOps = ImageTk = None


def today_iso() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_outdated_days(value: object, default: int = GEAR_OUTDATED_DEFAULT_DAYS) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        return default
    return days if 1 <= days <= 3650 else default


def normalize_bool_setting(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def last_checked_age_days(value: object, today: date | None = None) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        checked = date.fromisoformat(text[:10])
    except ValueError:
        return None
    return max(0, ((today or date.today()) - checked).days)


def member_check_is_outdated(member: "Member", enabled: bool, threshold_days: int,
                             today: date | None = None) -> bool:
    if not enabled or member.lifeStatus != "active":
        return False
    age = last_checked_age_days(member.lastChecked, today=today)
    return age is not None and age >= normalize_outdated_days(threshold_days)


@functools.lru_cache(maxsize=1)
def app_base_dir() -> Path:
    """Return suite root. Since v0.5.0 Python sources live in the app folder.

    Das Ergebnis haengt ausschliesslich von processkonstanten Werten ab
    (``sys.frozen``/``sys.executable`` beziehungsweise ``__file__``) und aendert
    sich innerhalb einer Session nicht. Es wird deshalb einmal ermittelt und
    danach wiederverwendet, weil diese Funktion pro Tabellenzeile und pro
    Asset-Zugriff aufgerufen wird.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    here = Path(__file__).resolve().parent
    return here.parent if here.name.casefold() == "app" else here


def shared_portrait_folder(project_path: Path | str | None = None) -> Path:
    """Compatibility name for the now strictly project-local portrait folder."""
    folder = project_portrait_root(project_path)
    if folder is None:
        raise ValueError("Ohne aktives .ggc-Projekt gibt es keinen Portraitordner.")
    return folder


def checker_banner_path() -> Path:
    return app_base_dir() / "assets" / "checker_banner.png"


def gravestone_template_folder() -> Path:
    return app_base_dir() / GRAVESTONE_TEMPLATE_FOLDER


def gravestone_background_path() -> Path:
    return app_base_dir() / GRAVESTONE_BACKGROUND_PATH


def gravestone_manifest_path() -> Path:
    return gravestone_template_folder() / GRAVESTONE_MANIFEST_FILENAME


def gravestone_placeholder_path() -> Path:
    return gravestone_template_folder() / "gravestone_placeholder.png"


def prepare_graveyard_background(path: Path, size: tuple[int, int]):
    """Return a non-distorted cover crop for the visible graveyard area."""
    width, height = max(1, int(size[0])), max(1, int(size[1]))
    with Image.open(path) as raw:
        source = ImageOps.exif_transpose(raw).convert("RGB") if ImageOps else raw.convert("RGB")
        if ImageOps:
            return ImageOps.fit(
                source, (width, height), method=Image.Resampling.LANCZOS,
            )
        return source.resize((width, height), Image.Resampling.LANCZOS)


def discover_gravestone_templates(folder: Path | None = None) -> tuple[Path, ...]:
    """Return only readable, manifest-confirmed, content-unique templates."""
    root = Path(folder) if folder is not None else gravestone_template_folder()
    inventory = load_gravestone_inventory(root, root / GRAVESTONE_MANIFEST_FILENAME)
    return tuple(item.path for item in inventory.templates)


def valid_gravestone_template_id(value: str | None) -> bool:
    name = str(value or "").strip()
    return bool(name and Path(name).name == name and re.fullmatch(
        r"gravestone_[^/\\]+\.[A-Za-z0-9]+", name, flags=re.IGNORECASE,
    ) and Path(name).suffix.casefold() in GRAVESTONE_SUPPORTED_IMAGE_EXTENSIONS)


def valid_grave_template_id(value: str | None) -> bool:
    template_id = str(value or "").strip()
    return bool(template_id and len(template_id) <= 120 and re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]*", template_id,
    ))


def normalize_text_offset(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:
        return 0.0
    return max(GRAVESTONE_TEXT_OFFSET_RANGE[0],
               min(GRAVESTONE_TEXT_OFFSET_RANGE[1], number))


def normalize_text_scale(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 1.0
    if number != number:
        return 1.0
    return max(GRAVESTONE_TEXT_SCALE_RANGE[0],
               min(GRAVESTONE_TEXT_SCALE_RANGE[1], number))


def shifted_text_offsets(offset_x: object, offset_y: object, delta_x: float,
                         delta_y: float, size: tuple[int, int]) -> tuple[float, float]:
    safe = _scaled_gravestone_box(GRAVESTONE_TEXT_SAFE_AREA, size)
    range_x = max(1.0, (safe[2] - safe[0]) * GRAVESTONE_TEXT_OFFSET_FACTOR[0])
    range_y = max(1.0, (safe[3] - safe[1]) * GRAVESTONE_TEXT_OFFSET_FACTOR[1])
    return (
        normalize_text_offset(normalize_text_offset(offset_x) + delta_x / range_x),
        normalize_text_offset(normalize_text_offset(offset_y) + delta_y / range_y),
    )


def normalize_portrait_offset(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:
        return 0.0
    return max(GRAVESTONE_PORTRAIT_OFFSET_RANGE[0],
               min(GRAVESTONE_PORTRAIT_OFFSET_RANGE[1], number))


def normalize_portrait_zoom(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 1.0
    if number != number:
        return 1.0
    return max(GRAVESTONE_PORTRAIT_ZOOM_RANGE[0],
               min(GRAVESTONE_PORTRAIT_ZOOM_RANGE[1], number))


def shifted_portrait_offsets(offset_x: object, offset_y: object, delta_x: float,
                             delta_y: float, portrait_size: tuple[int, int]) -> tuple[float, float]:
    width = max(1, int(portrait_size[0]))
    height = max(1, int(portrait_size[1]))
    return (
        normalize_portrait_offset(normalize_portrait_offset(offset_x) + 2.0 * delta_x / width),
        normalize_portrait_offset(normalize_portrait_offset(offset_y) + 2.0 * delta_y / height),
    )


def choose_gravestone_template(template_ids: Iterable[str], member_id: str,
                               previous_template: str | None = None) -> str:
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


def graveyard_grid_layout(canvas_width: int, item_count: int) -> dict:
    card_width, card_height = GRAVESTONE_CARD_SIZE
    gap_x, gap_y = GRAVESTONE_GRID_GAP
    usable_width = max(card_width, int(canvas_width) - (2 * GRAVESTONE_GRID_PADDING))
    columns = max(1, (usable_width + gap_x) // (card_width + gap_x))
    grid_width = columns * card_width + (columns - 1) * gap_x
    start_x = max(GRAVESTONE_GRID_PADDING, (int(canvas_width) - grid_width) // 2)
    rows = (max(0, int(item_count)) + columns - 1) // columns
    positions = tuple(
        (
            start_x + (index % columns) * (card_width + gap_x),
            GRAVESTONE_HEADER_BOTTOM + (index // columns) * (card_height + gap_y),
        )
        for index in range(max(0, int(item_count)))
    )
    content_height = (
        GRAVESTONE_HEADER_BOTTOM + rows * card_height
        + max(0, rows - 1) * gap_y + GRAVESTONE_GRID_PADDING
    )
    return {
        "columns": columns,
        "rows": rows,
        "positions": positions,
        "content_height": content_height,
    }


def class_icon_folder() -> Path:
    return app_base_dir() / "assets" / "classes"


def fallback_class_icon_folder() -> Path:
    return class_icon_folder() / "fallback"


def class_icon_path(class_name: str) -> Path:
    return class_icon_folder() / f"{class_name.lower()}.jpg"


def fallback_class_icon_path(class_name: str) -> Path:
    return fallback_class_icon_folder() / f"{class_name.lower()}.png"


def normalize_class_name(value: str) -> str:
    text = str(value or "").strip()
    return next((c for c in CLASS_NAMES if c.casefold() == text.casefold()), "")


def normalize_race(value: str | None) -> str | None:
    text = str(value or "").strip()
    return next((race for race in RACE_NAMES if race.casefold() == text.casefold()), None)


def normalize_spec(class_name: str, value: str) -> str:
    cls = normalize_class_name(class_name)
    text = str(value or "").strip()
    if not cls:
        return ""
    return next((spec for spec in CLASS_SPECS[cls] if spec.casefold() == text.casefold()), "")


def combine_class_spec(class_name: str, spec: str) -> str:
    cls = normalize_class_name(class_name)
    sp = normalize_spec(cls, spec)
    if cls and sp:
        return f"{cls} / {sp}"
    return cls or ""


def parse_legacy_class_spec(value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", ""
    folded = text.casefold()
    for cls in CLASS_NAMES:
        cf = cls.casefold()
        if folded == cf:
            return cls, ""
        if folded.startswith(cf):
            rest = text[len(cls):].strip(" \t/-|·:>")
            spec = normalize_spec(cls, rest)
            if spec:
                return cls, spec
    return "", ""


def valid_class_icon_bytes(data: bytes) -> bool:
    if len(data) < 300 or not data.startswith(b"\xff\xd8"):
        return False
    if Image is not None:
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
            with Image.open(io.BytesIO(data)) as im:
                return im.width >= 32 and im.height >= 32
        except Exception:
            return False
    return True


def valid_class_icon_file(path: Path) -> bool:
    try:
        return valid_class_icon_bytes(path.read_bytes())
    except OSError:
        return False


def download_class_icons(force: bool = False, timeout: int = 10) -> dict[str, str]:
    """Download/cache the nine class icons. Returns per-class status.

    Existing valid-looking local files are kept unless force=True. The function
    is deliberately independent from Tk so it can be tested and used by setup.
    """
    import urllib.request

    folder = class_icon_folder()
    folder.mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}
    for cls, url in CLASS_ICON_URLS.items():
        target = class_icon_path(cls)
        if not force and valid_class_icon_file(target):
            result[cls] = "cached"
            continue
        tmp = target.with_suffix(".jpg.tmp")
        last_exc = None
        for attempt in range(1, 4):
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 GuildGearChecker/0.4",
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    "Cache-Control": "no-cache",
                })
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = resp.read(1024 * 1024)
                if not valid_class_icon_bytes(data):
                    raise ValueError("Antwort ist kein gueltiges Class-Icon-JPEG")
                tmp.write_bytes(data)
                os.replace(tmp, target)
                result[cls] = "downloaded" if attempt == 1 else f"downloaded retry {attempt}"
                break
            except Exception as exc:
                last_exc = exc
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
                if attempt < 3:
                    import time as _time
                    _time.sleep(0.6 * attempt)
        else:
            result[cls] = f"error: {last_exc}"
    return result


def norm_name(value: str) -> str:
    return unicodedata.normalize("NFC", str(value or "").strip()).casefold()


def sanitize_filename(value: str) -> str:
    value = unicodedata.normalize("NFC", str(value or "").strip())
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = value.rstrip(" .")
    return value or "Unbekannt"


def build_armory_url(name: str, region: str = REGION, realm: str = REALM,
                     game_version: str = GAME_VERSION) -> str:
    encoded = urllib.parse.quote(unicodedata.normalize("NFC", str(name).strip()), safe="")
    encoded_region = urllib.parse.quote(str(region), safe="")
    encoded_realm = urllib.parse.quote(str(realm), safe="")
    encoded_game_version = urllib.parse.quote(str(game_version), safe="")
    return (f"https://classicwowarmory.com/character/{encoded_region}/{encoded_realm}/"
            f"{encoded}?game_version={encoded_game_version}")


def member_matches_tab(member: "Member", tab_name: str, outdated_tracking: bool = False,
                       outdated_days: int = GEAR_OUTDATED_DEFAULT_DAYS,
                       today: date | None = None) -> bool:
    if tab_name == "Gildenliste":
        return member.lifeStatus == "active"
    if tab_name == "Handlungsbedarf":
        return member.lifeStatus == "active" and (
            gear_status_key(member.gearStatus) in {"level", "pre_bis"}
            or member_check_is_outdated(member, outdated_tracking, outdated_days, today)
        )
    if tab_name == "Ungeprüft":
        return member.lifeStatus == "active" and gear_status_key(member.gearStatus) == "level"
    if tab_name == "Inaktiv":
        return member.lifeStatus == "inactive"
    if tab_name in {"Friedhof", "Tot"}:
        return member.lifeStatus == "dead"
    if tab_name == "Alle Charaktere":
        return True
    if tab_name == "Roster":
        return member.lifeStatus == "active"
    return member.lifeStatus == "active"


GEAR_SORT_ORDER = {"s_plus": 0, "bis": 1, "pre_bis": 2, "level": 3}
ENCHANT_SORT_ORDER = {"okay": 0, "missing": 1, "not_checked": 2}


def _text_sort_key(value: str) -> str:
    return unicodedata.normalize("NFKD", str(value or "")).casefold()


def parse_member_date(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for pattern in ("%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def normalize_death_date(value: object) -> str:
    """Normalize supported user date formats to the project's ISO date form."""
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = parse_member_date(text)
    if parsed is None:
        raise ValueError(tr("graveyard.invalid_death_date"))
    return parsed.date().isoformat()


def default_sort_for_tab(tab_name: str) -> tuple[str, bool]:
    if tab_name in {"Friedhof", "Tot"}:
        return "death_date", True
    return "name", False


def sort_members(members: Iterable["Member"], column: str = "name",
                 descending: bool = False) -> list["Member"]:
    """Return a sorted copy. Missing values remain at the end in both directions."""
    members = list(members)

    def value(member: "Member"):
        if column == "name":
            return _text_sort_key(member.name)
        if column == "class":
            return _text_sort_key(member.className)
        if column == "spec":
            return _text_sort_key(member.spec)
        if column == "gear":
            return GEAR_SORT_ORDER.get(gear_status_key(member.gearStatus), 99)
        if column == "checked":
            return parse_member_date(member.lastChecked)
        if column == "death_date":
            return parse_member_date(member.deathDate)
        if column == "character_type":
            return {"main": 0, "twink": 1, "not_set": 2}.get(member.characterType, 3)
        if column == "raid_role":
            return {"tank": 0, "healer": 1, "dps": 2, "not_set": 3}.get(member.raidRole, 4)
        return _text_sort_key(member.name)

    present: list["Member"] = []
    missing: list["Member"] = []
    for member in members:
        raw = value(member)
        if raw is None or (isinstance(raw, str) and not raw):
            missing.append(member)
        else:
            present.append(member)
    present.sort(key=lambda member: (value(member), member.id), reverse=descending)
    return present + missing


def raid_table_sort_value(raid: Raid, column: str, participants: int,
                          status_text: str) -> object:
    if column == "date":
        return raid.date
    if column == "type":
        return _text_sort_key(raid.raidType)
    if column == "participants":
        return int(participants)
    if column == "status":
        return _text_sort_key(status_text)
    if column == "logs":
        return _text_sort_key(raid.warcraftLogsUrl)
    return _text_sort_key(raid.name)


def raid_statistics_sort_value(player: "Player", stats, column: str) -> object:
    if column == "player":
        return _text_sort_key(player.playerName)
    if column == "attendance":
        return stats.attendance_percent
    values = {
        "eligible": stats.eligible_raids,
        "main": stats.main_attendances,
        "twink": stats.twink_attendances,
        "absent": stats.absences,
    }
    return values.get(column, 0)


def raid_attendance_sort_value(entry: RaidAttendance, column: str,
                               type_text: str) -> object:
    if column == "character":
        return _text_sort_key(entry.characterNameSnapshot)
    if column == "type":
        return _text_sort_key(type_text)
    return _text_sort_key(entry.playerNameSnapshot)


def raid_date_display(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value).date()
    except (TypeError, ValueError):
        return str(value or "")
    return parsed.strftime("%d.%m.%Y") if get_language() == "de" else parsed.isoformat()


def attendance_target_text(raid: Raid, participants: int) -> str:
    return tr(
        "raids.import_target", name=raid.name, date=raid_date_display(raid.date),
        status=tr(f"raids.status_{raid.status}"), participants=participants,
    )


def filter_and_sort_members(members: Iterable["Member"], tab_name: str,
                            query: str = "", gear_filter_key: str | None = None,
                            enchant_filter_key: str | None = None,
                            sort_column: str = "name",
                            descending: bool = False,
                            outdated_tracking: bool = False,
                            outdated_days: int = GEAR_OUTDATED_DEFAULT_DAYS) -> list["Member"]:
    folded_query = str(query or "").strip().casefold()
    result: list["Member"] = []
    for member in members:
        if not member_matches_tab(
                member, tab_name, outdated_tracking=outdated_tracking,
                outdated_days=outdated_days):
            continue
        if gear_filter_key and gear_status_key(member.gearStatus) != gear_filter_key:
            continue
        haystack = (
            f"{member.name}\n{member.className}\n{member.spec}\n"
            f"{member.classSpec}\n{member.note}"
        ).casefold()
        if folded_query and folded_query not in haystack:
            continue
        result.append(member)
    return sort_members(result, sort_column, descending)


ROSTER_ROLE_ORDER = ("tank", "healer", "dps", "not_set")


def clamp_roster_zoom(value: object) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = 100
    numeric = round(numeric / ROSTER_ZOOM_STEP) * ROSTER_ZOOM_STEP
    return max(ROSTER_ZOOM_MIN, min(ROSTER_ZOOM_MAX, numeric))


def scaled_roster_value(value: int, zoom_percent: int) -> int:
    return max(1, round(value * clamp_roster_zoom(zoom_percent) / 100))


def roster_card_size(zoom_percent: int) -> tuple[int, int]:
    return (
        scaled_roster_value(ROSTER_CARD_WIDTH, zoom_percent),
        scaled_roster_value(ROSTER_CARD_HEIGHT, zoom_percent),
    )


def roster_portrait_size(zoom_percent: int) -> tuple[int, int]:
    return tuple(scaled_roster_value(value, zoom_percent) for value in ROSTER_PORTRAIT_SIZE)


def roster_column_count(available_width: int, zoom_percent: int = 100) -> int:
    card_width, _height = roster_card_size(zoom_percent)
    gap = scaled_roster_value(20, zoom_percent)
    return max(1, int(available_width) // (card_width + gap))


def fit_roster_zoom(available_width: int, active_count: int) -> int:
    target_columns = max(1, min(active_count or 1, 6))
    for zoom in range(ROSTER_ZOOM_MAX, ROSTER_ZOOM_MIN - 1, -ROSTER_ZOOM_STEP):
        if roster_column_count(available_width, zoom) >= target_columns:
            return zoom
    return ROSTER_ZOOM_MIN


def group_roster_members(members: Iterable["Member"]) -> dict[str, list["Member"]]:
    groups = {role: [] for role in ROSTER_ROLE_ORDER}
    type_order = {"main": 0, "twink": 1, "not_set": 2}
    for member in members:
        if member.lifeStatus != "active":
            continue
        role = member.raidRole if member.raidRole in groups else "not_set"
        groups[role].append(member)
    for group in groups.values():
        group.sort(key=lambda member: (
            type_order.get(member.characterType, 3),
            _text_sort_key(member.className),
            _text_sort_key(member.name),
            member.id,
        ))
    return groups


@dataclass
class Player:
    playerId: str
    playerName: str
    membershipStartDate: str | None = None
    membershipEndDate: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        membership_start, membership_end = validate_membership_dates(
            data.get("membershipStartDate"), data.get("membershipEndDate"),
        )
        return cls(
            playerId=str(data.get("playerId") or "").strip(),
            playerName=unicodedata.normalize("NFC", str(data.get("playerName") or "").strip()),
            membershipStartDate=membership_start,
            membershipEndDate=membership_end,
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        if self.membershipStartDate is None:
            data.pop("membershipStartDate")
        if self.membershipEndDate is None:
            data.pop("membershipEndDate")
        return data


class MainConflictError(ValueError):
    def __init__(self, existing_main: "Member") -> None:
        super().__init__(tr("model.active_main_exists", name=existing_main.name))
        self.existing_main = existing_main


def normalize_project_life_status(value: object, format_version: int) -> str:
    """Normalize persisted life status without hiding invalid format-4 values."""
    text = str(value or "").strip()
    if format_version >= 4:
        if text not in LIFE_STATUSES:
            raise ValueError(tr("model.invalid_life_status"))
        return text
    if text == "inactive":
        raise ValueError(tr("model.inactive_requires_format_four"))
    return "dead" if text == "dead" else "active"


@dataclass
class Member:
    id: str
    name: str
    race: str | None = None
    className: str = ""
    spec: str = ""
    classSpec: str = ""  # legacy field kept for backwards compatibility
    lifeStatus: str = "active"
    gearStatus: str = "Level"
    enchants: str = "Nicht geprüft"
    raidStatus: str = ""
    note: str = ""
    lastChecked: str = ""
    deathDate: str = ""
    addedDate: str = ""
    source: str = "Manuell"
    playerId: str | None = None
    characterType: str = "not_set"
    raidRole: str = "not_set"
    graveTemplateId: str = ""
    gravestoneTemplate: str = ""
    portraitOffsetX: float = 0.0
    portraitOffsetY: float = 0.0
    portraitZoom: float = 1.0
    textOffsetX: float = 0.0
    textOffsetY: float = 0.0
    textScale: float = 1.0

    @classmethod
    def from_dict(cls, data: dict, fallback_id: str,
                  format_version: int = PROJECT_FORMAT_VERSION) -> "Member":
        legacy = str(data.get("classSpec") or "").strip()
        class_name = normalize_class_name(str(data.get("className") or data.get("class") or ""))
        spec = normalize_spec(class_name, str(data.get("spec") or ""))
        if legacy and (not class_name or not spec):
            legacy_class, legacy_spec = parse_legacy_class_spec(legacy)
            if not class_name:
                class_name = legacy_class
            if not spec and class_name == legacy_class:
                spec = legacy_spec
        canonical_legacy = combine_class_spec(class_name, spec)
        return cls(
            id=str(data.get("id") or fallback_id).strip(),
            name=unicodedata.normalize("NFC", str(data.get("name") or "").strip()),
            race=normalize_race(data.get("race")),
            className=class_name,
            spec=spec,
            classSpec=canonical_legacy or legacy,
            lifeStatus=normalize_project_life_status(data.get("lifeStatus") or "active", format_version),
            gearStatus=(data.get("gearStatus") if data.get("gearStatus") in GEAR_VALUES else "Level"),
            raidStatus=raid_status_from_display(data.get("raidStatus")),
            note=str(data.get("note") or ""),
            lastChecked=str(data.get("lastChecked") or ""),
            deathDate=str(data.get("deathDate") or ""),
            addedDate=str(data.get("addedDate") or today_iso()),
            source=str(data.get("source") or "Projektdatei"),
            playerId=(str(data.get("playerId")).strip() if data.get("playerId") else None),
            characterType=(data.get("characterType") if data.get("characterType") in CHARACTER_TYPES else "not_set"),
            raidRole=normalize_raid_role(data.get("raidRole")),
            graveTemplateId=(
                str(data.get("graveTemplateId") or "").strip()
                if valid_grave_template_id(data.get("graveTemplateId")) else ""
            ),
            gravestoneTemplate=(
                str(data.get("gravestoneTemplate") or "").strip()
                if valid_gravestone_template_id(data.get("gravestoneTemplate")) else ""
            ),
            portraitOffsetX=normalize_portrait_offset(data.get("portraitOffsetX")),
            portraitOffsetY=normalize_portrait_offset(data.get("portraitOffsetY")),
            portraitZoom=normalize_portrait_zoom(data.get("portraitZoom")),
            textOffsetX=normalize_text_offset(data.get("textOffsetX")),
            textOffsetY=normalize_text_offset(data.get("textOffsetY")),
            textScale=normalize_text_scale(data.get("textScale")),
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        # Enchants are no longer part of the project format.
        data.pop("enchants", None)
        if self.race is None:
            data.pop("race")
        if self.playerId is None:
            data.pop("playerId")
        if self.characterType == "not_set":
            data.pop("characterType")
        if self.raidRole == "not_set":
            data.pop("raidRole")
        if not self.graveTemplateId:
            data.pop("graveTemplateId")
        if not self.gravestoneTemplate:
            data.pop("gravestoneTemplate")
        if self.portraitOffsetX == 0.0:
            data.pop("portraitOffsetX")
        if self.portraitOffsetY == 0.0:
            data.pop("portraitOffsetY")
        if self.portraitZoom == 1.0:
            data.pop("portraitZoom")
        if self.textOffsetX == 0.0:
            data.pop("textOffsetX")
        if self.textOffsetY == 0.0:
            data.pop("textOffsetY")
        if self.textScale == 1.0:
            data.pop("textScale")
        return data


class _GuildModelState:
    def __init__(self) -> None:
        self.members: list[Member] = []
        self.players: list[Player] = []
        self.raids: list[Raid] = []
        self.raid_attendance: list[RaidAttendance] = []
        self.raid_points = RaidPointState()
        self.raid_points_legacy_scope_required = False
        self.eternal_dkp = EternalDkpState()
        self.point_mode = ""
        self.attendance_tracking_start_date: str | None = None
        self.next_id = 1000
        self.next_player_id = 1
        self.region = REGION
        self.realm = REALM
        self.guild_name = ""
        self.dkp_enabled = False
        self.clm_roster_id = ""
        self.game_version = GAME_VERSION
        self.project_path: Path | None = None
        self.dirty = False
        self.wcl_member_aliases: dict[str, str] = {}
        self._gravestone_inventory_cache: GravestoneInventory | None = None


@functools.lru_cache(maxsize=256)
def _export_font(size: int, bold: bool = False, decorative: bool = False):
    """Return a reusable export font for one (size, bold, decorative) combination.

    Das Ergebnis haengt ausschliesslich von den drei Parametern und von
    processkonstanten Fontdateipfaden ab. Keine Aufrufstelle veraendert das
    zurueckgegebene Fontobjekt, deshalb ist die Wiederverwendung innerhalb einer
    Session sicher. Der Cache ist bewusst begrenzt, damit eine laenger laufende
    Sitzung mit vielen Zoom-/Textskalierungsstufen nicht unbegrenzt Fontobjekte
    ansammelt.
    """
    if ImageFont is None:
        return None
    candidates = []
    if decorative:
        candidates.append(app_base_dir() / "assets" / "fonts" / "LifeCraft_Font.ttf")
    candidates.extend([
        Path("C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ])
    for path in candidates:
        try:
            if path.is_file():
                return ImageFont.truetype(str(path), size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _fit_export_text(draw, text: str, font, max_width: int) -> str:
    value = str(text or "")
    if draw.textbbox((0, 0), value, font=font)[2] <= max_width:
        return value
    suffix = "…"
    while value and draw.textbbox((0, 0), value + suffix, font=font)[2] > max_width:
        value = value[:-1]
    return value + suffix


def _scaled_gravestone_point(point: tuple[int, int], size: tuple[int, int]) -> tuple[int, int]:
    return (
        round(point[0] * size[0] / GRAVESTONE_MASTER_SIZE[0]),
        round(point[1] * size[1] / GRAVESTONE_MASTER_SIZE[1]),
    )


def _scaled_gravestone_box(box: tuple[int, int, int, int],
                           size: tuple[int, int]) -> tuple[int, int, int, int]:
    left, top = _scaled_gravestone_point((box[0], box[1]), size)
    right, bottom = _scaled_gravestone_point((box[2], box[3]), size)
    return left, top, right, bottom


def prepare_gravestone_template(path: Path,
                                size: tuple[int, int] = GRAVESTONE_CARD_SIZE):
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow ist für Grabsteinkarten erforderlich.")
    with Image.open(path) as raw:
        frame = ImageOps.exif_transpose(raw).convert("RGBA")
        return frame.resize(size, Image.Resampling.LANCZOS)


def _fallback_gravestone_portrait_opening(size: tuple[int, int]) -> GravestonePortraitOpening:
    box = _scaled_gravestone_box(GRAVESTONE_PORTRAIT_BOX, size)
    return _fallback_shared_gravestone_portrait_opening(size, box)


def detect_gravestone_portrait_opening(template_image) -> GravestonePortraitOpening:
    """Return the shared adaptive portrait opening for one gravestone frame."""
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow ist für Grabsteinkarten erforderlich.")

    cached = getattr(template_image, "_ggc_portrait_opening", None)
    if isinstance(cached, GravestonePortraitOpening):
        return cached

    frame = (
        template_image
        if getattr(template_image, "mode", None) == "RGBA"
        else template_image.convert("RGBA")
    )
    legacy_box = _scaled_gravestone_box(GRAVESTONE_PORTRAIT_BOX, frame.size)
    opening = _detect_shared_gravestone_portrait_opening(frame, legacy_box, analysis_size=GRAVESTONE_CARD_SIZE)
    try:
        template_image._ggc_portrait_opening = opening
    except Exception:
        pass
    return opening


def fit_gravestone_portrait(source, size: tuple[int, int], offset_x: float = 0.0,
                            offset_y: float = 0.0, zoom: float = 1.0):
    """Use the shared cover-fit implementation after project-value normalization."""
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow ist für Grabsteinkarten erforderlich.")
    return _fit_shared_gravestone_portrait(
        source,
        size,
        normalize_portrait_offset(offset_x),
        normalize_portrait_offset(offset_y),
        normalize_portrait_zoom(zoom),
    )


def graveyard_placeholder_variation(member: Member, portrait_path: Path | None) -> tuple[float, float, float]:
    """Return stable per-character crop offsets and zoom for the placeholder only."""
    if portrait_path is None or portrait_path.name.casefold() != "portrait_placeholder.png":
        return 0.0, 0.0, 1.0
    seed = f"{member.id}|{member.name}".encode("utf-8", "surrogatepass")
    digest = hashlib.sha256(seed).digest()
    offset_x = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    offset_y = int.from_bytes(digest[4:8], "big") / 0xFFFFFFFF
    zoom = 1.3 + (int.from_bytes(digest[8:12], "big") / 0xFFFFFFFF) * 0.3
    return offset_x, offset_y, zoom


def render_gravestone_card(member: Member, template_image, portrait_path: Path | None,
                           size: tuple[int, int] = GRAVESTONE_CARD_SIZE,
                           text_safe_area_master: tuple[int, int, int, int] | None = None,
                           portrait_image=None):
    """Compose portrait, immutable frame and programmatic text in separate layers."""
    if Image is None or ImageDraw is None or ImageFont is None or ImageOps is None:
        raise RuntimeError("Pillow ist für Grabsteinkarten erforderlich.")
    card = Image.new("RGBA", size, (0, 0, 0, 0))
    frame = (
        template_image
        if getattr(template_image, "mode", None) == "RGBA"
        else template_image.convert("RGBA")
    )
    if frame.size != size:
        frame = frame.resize(size, Image.Resampling.LANCZOS)
    opening = detect_gravestone_portrait_opening(frame)
    portrait_box = opening.box
    portrait_size = (portrait_box[2] - portrait_box[0], portrait_box[3] - portrait_box[1])
    portrait_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    portrait = Image.new("RGB", portrait_size, "#15191d")
    placeholder_offset_x, placeholder_offset_y, placeholder_zoom = graveyard_placeholder_variation(member, portrait_path)
    if portrait_image is not None:
        try:
            is_placeholder = (
                portrait_path is not None
                and portrait_path.name.casefold() == "portrait_placeholder.png"
            )
            portrait = fit_gravestone_portrait(
                portrait_image,
                portrait_size,
                placeholder_offset_x if is_placeholder else member.portraitOffsetX,
                placeholder_offset_y if is_placeholder else member.portraitOffsetY,
                placeholder_zoom if is_placeholder else member.portraitZoom,
            )
        except (OSError, ValueError):
            pass
    elif portrait_path is not None:
        try:
            with Image.open(portrait_path) as raw:
                is_placeholder = portrait_path.name.casefold() == "portrait_placeholder.png"
                portrait = fit_gravestone_portrait(
                    raw,
                    portrait_size,
                    placeholder_offset_x if is_placeholder else member.portraitOffsetX,
                    placeholder_offset_y if is_placeholder else member.portraitOffsetY,
                    placeholder_zoom if is_placeholder else member.portraitZoom,
                )
        except (OSError, ValueError):
            pass
    mask = opening.mask
    if getattr(mask, "size", None) != portrait_size:
        mask = mask.resize(portrait_size, Image.Resampling.LANCZOS)
    portrait_layer.paste(portrait, portrait_box[:2], mask)
    card.alpha_composite(portrait_layer)

    card.alpha_composite(frame)

    draw = ImageDraw.Draw(card)
    colors = {"name": "#f6ead0", "class": "#e2d3b8", "death_date": "#d8c9ad"}
    for key, line in gravestone_text_layout(member, size, text_safe_area_master).items():
        draw.text(
            line["position"], line["text"], anchor="mm", align="center",
            font=line["font"], fill=colors[key],
            stroke_width=1, stroke_fill="#17130f",
        )
    return card


def gravestone_text_layout(member: Member,
                           size: tuple[int, int] = GRAVESTONE_CARD_SIZE,
                           text_safe_area_master: tuple[int, int, int, int] | None = None) -> dict[str, dict]:
    """Fit and move the three lines as one persistent, safely clipped text block."""
    if Image is None or ImageDraw is None or ImageFont is None:
        raise RuntimeError("Pillow ist für Grabsteinkarten erforderlich.")
    measuring = Image.new("L", size, 0)
    draw = ImageDraw.Draw(measuring)
    safe_area = _scaled_gravestone_box(text_safe_area_master or GRAVESTONE_TEXT_SAFE_AREA, size)
    max_width = safe_area[2] - safe_area[0]
    scale = size[1] / GRAVESTONE_MASTER_SIZE[1]
    text_scale = normalize_text_scale(member.textScale)
    offset_x = normalize_text_offset(member.textOffsetX)
    offset_y = normalize_text_offset(member.textOffsetY)
    delta_x = round((safe_area[2] - safe_area[0]) * GRAVESTONE_TEXT_OFFSET_FACTOR[0] * offset_x)
    delta_y = round((safe_area[3] - safe_area[1]) * GRAVESTONE_TEXT_OFFSET_FACTOR[1] * offset_y)
    values = {
        "name": member.name,
        "class": member.className or "–",
        "death_date": member.deathDate or "–",
    }
    result = {}
    for key, value in values.items():
        initial = max(1, round(GRAVESTONE_TEXT_FONT_SIZES[key] * scale * text_scale))
        minimum = max(1, round(GRAVESTONE_TEXT_MIN_FONT_SIZES[key] * scale * text_scale))
        font = _export_font(initial, bold=True)
        for font_size in range(initial, minimum - 1, -1):
            candidate = _export_font(font_size, bold=True)
            if draw.textbbox((0, 0), value, font=candidate, stroke_width=1)[2] <= max_width:
                font = candidate
                break
            font = candidate
        fitted = _fit_export_text(draw, value, font, max_width - 2)
        base_position = _scaled_gravestone_point(GRAVESTONE_TEXT_POSITIONS[key], size)
        position = (base_position[0] + delta_x, base_position[1] + delta_y)
        result[key] = {
            "text": fitted,
            "font": font,
            "position": position,
            "bbox": draw.textbbox(
                position, fitted, font=font, anchor="mm", stroke_width=1,
            ),
        }
    block_left = min(line["bbox"][0] for line in result.values())
    block_top = min(line["bbox"][1] for line in result.values())
    block_right = max(line["bbox"][2] for line in result.values())
    block_bottom = max(line["bbox"][3] for line in result.values())
    shift_x = max(2 - block_left, min(0, size[0] - 2 - block_right))
    shift_y = max(2 - block_top, min(0, size[1] - 2 - block_bottom))
    if shift_x or shift_y:
        for line in result.values():
            position = line["position"]
            line["position"] = (position[0] + shift_x, position[1] + shift_y)
            line["bbox"] = draw.textbbox(
                line["position"], line["text"], font=line["font"],
                anchor="mm", stroke_width=1,
            )
    return result


def _export_normal_portrait_path(member: Member, portrait_root: Path) -> Path | None:
    path = portrait_root / f"{member.id}.png"
    return path if path.is_file() else None


def _export_class_icon_path(member: Member, icon_root: Path) -> Path | None:
    class_name = normalize_class_name(member.className)
    for path in (
        icon_root / f"{class_name.lower()}.jpg",
        icon_root / "fallback" / f"{class_name.lower()}.png",
    ):
        if class_name and path.is_file():
            return path
    return None


def render_roster_png(model: "GuildModel", destination: Path,
                      portrait_root: Path | None = None,
                      icon_root: Path | None = None) -> dict:
    """Render the complete active roster offscreen at stable high resolution."""
    if Image is None or ImageDraw is None or ImageFont is None or ImageOps is None:
        raise RuntimeError("Pillow")
    active = [member for member in model.members if member.lifeStatus == "active"]
    if not active:
        raise ValueError(tr("roster.export_empty"))
    resolved_portraits = Path(portrait_root) if portrait_root is not None else project_portrait_root(model.project_path)
    if resolved_portraits is None:
        raise ValueError("Roster-Export benötigt ein gespeichertes .ggc-Projekt.")
    portrait_root = resolved_portraits
    icon_root = Path(icon_root or class_icon_folder())
    groups = group_roster_members(active)
    total = len(active)
    columns = ROSTER_EXPORT_COLUMNS_MAX if total >= 24 else ROSTER_EXPORT_COLUMNS_MIN
    card_width, card_height = ROSTER_EXPORT_CARD_SIZE
    outer = 80
    gap = 20
    title_height = 125
    group_heading_height = 72
    group_padding = 28
    group_gap = 26
    role_keys = {
        "tank": "roster.tanks",
        "healer": "roster.healers", "dps": "roster.dps",
        "not_set": "roster.unassigned",
    }
    group_layout = []
    y = title_height
    for role in ROSTER_ROLE_ORDER:
        count = len(groups[role])
        rows = (count + columns - 1) // columns
        cards_height = rows * card_height + max(0, rows - 1) * gap if rows else 48
        section_height = group_heading_height + cards_height + group_padding * 2
        group_layout.append((role, y, section_height, rows))
        y += section_height + group_gap
    width = outer * 2 + columns * card_width + (columns - 1) * gap
    height = y + outer - group_gap
    image = Image.new("RGB", (width, height), "#0d1117")
    draw = ImageDraw.Draw(image)
    title_font = _export_font(58, decorative=True)
    group_font = _export_font(38, bold=True, decorative=True)
    name_font = _export_font(31, bold=True)
    badge_font = _export_font(21, bold=True)
    detail_font = _export_font(25)
    small_font = _export_font(22)
    draw.text((outer, 34), tr("roster.title"), fill="#d7b56d", font=title_font)
    manifest = {
        "size": (width, height), "columns": columns,
        "groups": [], "cards": [], "active_ids": [member.id for member in active],
    }
    for role, section_y, section_height, _rows in group_layout:
        section_rect = (outer, section_y, width - outer, section_y + section_height)
        draw.rounded_rectangle(section_rect, radius=16, fill="#131922", outline="#5b4930", width=3)
        heading = tr(role_keys[role])
        draw.text((outer + group_padding, section_y + 16), heading,
                  fill="#b8a47b" if role == "not_set" else "#e0bd72", font=group_font)
        manifest["groups"].append({"role": role, "heading": heading, "count": len(groups[role])})
        if not groups[role]:
            draw.text((outer + group_padding, section_y + group_heading_height + 8),
                      tr("roster.empty"), fill="#9aa8b8", font=small_font)
            continue
        card_y = section_y + group_heading_height + group_padding
        for index, member in enumerate(groups[role]):
            column = index % columns
            row = index // columns
            x = outer + group_padding + column * (card_width + gap)
            y_card = card_y + row * (card_height + gap)
            rect = (x, y_card, x + card_width, y_card + card_height)
            draw.rounded_rectangle(
                rect, radius=14, fill="#202832",
                outline=CLASS_COLORS.get(member.className, "#46515e"), width=4,
            )
            portrait_rect = (x + 25, y_card + 24, x + card_width - 25, y_card + 404)
            draw.rectangle(portrait_rect, fill="#0b0f14", outline="#3c4652", width=3)
            portrait_path = _export_normal_portrait_path(member, portrait_root)
            portrait_used = False
            if portrait_path:
                try:
                    with Image.open(portrait_path) as raw:
                        portrait = ImageOps.contain(
                            ImageOps.exif_transpose(raw).convert("RGB"),
                            (portrait_rect[2] - portrait_rect[0], portrait_rect[3] - portrait_rect[1]),
                            Image.Resampling.LANCZOS,
                        )
                    image.paste(portrait, (
                        portrait_rect[0] + (portrait_rect[2] - portrait_rect[0] - portrait.width) // 2,
                        portrait_rect[1] + (portrait_rect[3] - portrait_rect[1] - portrait.height) // 2,
                    ))
                    portrait_used = True
                except Exception:
                    portrait_used = False
            if not portrait_used:
                placeholder = tr("checker.missing_portrait")
                placeholder_width = draw.textbbox((0, 0), placeholder, font=small_font)[2]
                draw.text((x + (card_width - placeholder_width) // 2, y_card + 205),
                          placeholder, fill="#9aa8b8", font=small_font)
            icon_path = _export_class_icon_path(member, icon_root)
            icon_used = False
            if icon_path:
                try:
                    with Image.open(icon_path) as raw:
                        icon = ImageOps.fit(raw.convert("RGB"), (52, 52), Image.Resampling.LANCZOS)
                    image.paste(icon, (x + 25, y_card + 424))
                    icon_used = True
                except Exception:
                    icon_used = False
            if not icon_used:
                draw.ellipse((x + 25, y_card + 424, x + 77, y_card + 476),
                             fill="#46515e", outline="#9aa8b8", width=2)
            badge = character_type_display(member.characterType)
            badge_box = draw.textbbox((0, 0), badge, font=badge_font)
            badge_width = badge_box[2] - badge_box[0] + 24
            draw.rounded_rectangle(
                (x + card_width - badge_width - 24, y_card + 430,
                 x + card_width - 24, y_card + 466),
                radius=8, fill="#8b6728" if member.characterType == "main" else "#3f5369",
            )
            draw.text((x + card_width - badge_width - 12, y_card + 435), badge,
                      fill="#ffffff", font=badge_font)
            name_width = card_width - badge_width - 120
            display_name = _fit_export_text(draw, member.name, name_font, name_width)
            draw.text((x + 90, y_card + 430), display_name, fill="#ffffff", font=name_font)
            class_text = member.className or tr("common.not_set")
            spec_text = member.spec or tr("common.not_set")
            type_text = character_type_display(member.characterType)
            main = model.associated_main(member)
            main_text = ""
            if member.characterType == "twink":
                main_text = f"Main: {main.name if main else tr('checker.no_active_main')}"
            detail_lines = [
                f"{tr('common.class')}: {class_text}",
                f"{tr('common.spec')}: {spec_text}",
                f"{tr('character_type.label')}: {type_text}",
            ]
            if main_text:
                detail_lines.append(main_text)
            detail_lines.extend([
                f"{tr('gear.label')}: {gear_status_display(member.gearStatus)}",
                f"{tr('enchants.label')}: {enchant_status_display(member.enchants)}",
            ])
            detail_y = y_card + 482
            line_height = 27 if len(detail_lines) > 5 else 32
            for line in detail_lines:
                draw.text((x + 25, detail_y), _fit_export_text(draw, line, detail_font, card_width - 50),
                          fill="#cbd4df", font=detail_font)
                detail_y += line_height
            manifest["cards"].append({
                "member_id": member.id, "name": member.name, "role": role,
                "rect": rect, "portrait_used": portrait_used, "icon_used": icon_used,
                "class": class_text, "spec": spec_text, "character_type": type_text,
                "associated_main": main_text,
                "gear": gear_status_display(member.gearStatus),
                "enchants": enchant_status_display(member.enchants),
            })
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)
    return manifest

@dataclass(frozen=True)
class BulkRaidCsvPlan:
    source_path: Path
    raid_date: str = ""
    raid_type: str = ""
    report_url: str = ""
    names: tuple[str, ...] = ()
    duplicates: tuple[str, ...] = ()
    unknown_names: tuple[str, ...] = ()
    status: str = "invalid"
    detail: str = ""


@dataclass(frozen=True)
class BulkRaidCsvResult:
    plans: tuple[BulkRaidCsvPlan, ...]
    imported: int
    skipped: int
    failed: int


class GuildModel(_GuildModelState):
    def gravestone_inventory(self) -> GravestoneInventory:
        """Load and verify the immutable template inventory at most once per session."""
        if self._gravestone_inventory_cache is None:
            self._gravestone_inventory_cache = load_gravestone_inventory(
                gravestone_template_folder(), gravestone_manifest_path(),
            )
        return self._gravestone_inventory_cache

    def new_seed(self) -> None:
        self.new_empty()
        for name in SEED_NAMES:
            self.members.append(self.make_member(name, "Startliste"))
        self.dirty = False

    def new_empty(self) -> None:
        self.members = []
        self.players = []
        self.wcl_member_aliases = {}
        self.raids = []
        self.raid_attendance = []
        self.raid_points = RaidPointState()
        self.raid_points_legacy_scope_required = False
        self.eternal_dkp = EternalDkpState()
        self.point_mode = ""
        self.attendance_tracking_start_date = None
        self.next_id = 1000
        self.next_player_id = 1
        self.region = REGION
        self.realm = REALM
        self.guild_name = ""
        self.dkp_enabled = False
        self.clm_roster_id = ""
        self.game_version = GAME_VERSION
        self.project_path = None
        self.dirty = False

    def active_point_mode(self) -> str:
        if self.point_mode in POINT_MODES:
            return self.point_mode
        if self.dkp_enabled:
            return POINT_MODE_ETERNAL
        if self.raid_points.enabled:
            return POINT_MODE_RAID
        return ""

    def eternal_character_totals(self) -> dict[str, tuple[int | float, int | float]]:
        return self.eternal_dkp.character_totals()

    def eternal_player_totals(self) -> dict[str, tuple[int | float, int | float]]:
        return self.eternal_dkp.player_totals(self.members)

    def clear_project(self) -> None:
        """Clear characters while preserving historical raid records and files."""
        self.members = []
        self.players = []
        self.wcl_member_aliases = {}
        self.next_id = 1000
        self.next_player_id = 1
        self.dirty = True

    def ensure_gravestone_templates(self) -> bool:
        """Migrate legacy references while preserving reserved template ownership."""
        if not any(
                member.graveTemplateId
                or (member.lifeStatus == "dead" and member.gravestoneTemplate)
                for member in self.members):
            return False
        inventory = self.gravestone_inventory()
        templates = inventory.by_id()
        changed = False
        occupied: set[str] = set()

        # A template stays reserved for a member after emergency reanimation.
        # Therefore every valid graveTemplateId participates in uniqueness, not only
        # IDs currently shown in the Graveyard.
        for member in self.members:
            if not member.graveTemplateId:
                continue
            if member.graveTemplateId in occupied:
                member.graveTemplateId = ""
                changed = True
                continue
            occupied.add(member.graveTemplateId)
            template = templates.get(member.graveTemplateId)
            if template is not None and not member.gravestoneTemplate:
                member.gravestoneTemplate = template.filename
                changed = True

        # Legacy filename-only references are meaningful for dead members.
        # Reanimated members created by format 4 already retain graveTemplateId.
        for member in self.members:
            if member.lifeStatus != "dead" or member.graveTemplateId:
                continue
            if member.gravestoneTemplate:
                legacy_id = inventory.id_for_filename(member.gravestoneTemplate)
                if legacy_id and legacy_id not in occupied:
                    member.graveTemplateId = legacy_id
                    occupied.add(legacy_id)
                    changed = True
        return changed

    def occupied_grave_template_ids(self, exclude_member_id: str | None = None) -> set[str]:
        return {
            member.graveTemplateId for member in self.members
            if member.id != exclude_member_id
            and valid_grave_template_id(member.graveTemplateId)
        }

    def available_gravestone_templates(self, member_id: str | None = None):
        inventory = self.gravestone_inventory()
        occupied = self.occupied_grave_template_ids(member_id)
        return inventory, tuple(
            template for template in inventory.templates
            if template.grave_template_id not in occupied
        )

    def _assign_gravestone_template(self, member: Member) -> None:
        if valid_grave_template_id(member.graveTemplateId):
            return
        inventory, available = self.available_gravestone_templates(member.id)
        templates = {template.grave_template_id: template for template in available}
        legacy_id = inventory.id_for_filename(member.gravestoneTemplate)
        selected_id = legacy_id if legacy_id in templates else choose_gravestone_template(
            tuple(templates), member.id,
        )
        if selected_id:
            member.graveTemplateId = selected_id
            member.gravestoneTemplate = templates[selected_id].filename

    def set_gravestone_adjustment(
            self, member_id: str, grave_template_id: str | None,
            offset_x: object, offset_y: object, zoom: object,
            text_offset_x: object, text_offset_y: object, text_scale: object,
            death_date: object | None = None) -> Member:
        """Validate the complete editor draft before atomically applying it."""
        member = self.find_by_id(member_id)
        if member is None:
            raise ValueError(tr("model.character_not_found"))
        if member.lifeStatus != "dead":
            raise ValueError(tr("graveyard.not_dead"))
        normalized_death_date = (
            normalize_death_date(death_date) if death_date is not None else None
        )
        normalized_portrait_x = normalize_portrait_offset(offset_x)
        normalized_portrait_y = normalize_portrait_offset(offset_y)
        normalized_zoom = normalize_portrait_zoom(zoom)
        normalized_text_x = normalize_text_offset(text_offset_x)
        normalized_text_y = normalize_text_offset(text_offset_y)
        normalized_text_scale = normalize_text_scale(text_scale)
        requested_id = str(grave_template_id or "").strip()
        new_filename = member.gravestoneTemplate
        if requested_id != member.graveTemplateId:
            inventory = self.gravestone_inventory()
            template = inventory.by_id().get(requested_id)
            if template is None:
                raise ValueError(tr("graveyard.template_unavailable"))
            if requested_id in self.occupied_grave_template_ids(member.id):
                raise ValueError(tr("graveyard.template_occupied"))
            new_filename = template.filename

        member.graveTemplateId = requested_id
        member.gravestoneTemplate = new_filename if requested_id else ""
        member.portraitOffsetX = normalized_portrait_x
        member.portraitOffsetY = normalized_portrait_y
        member.portraitZoom = normalized_zoom
        member.textOffsetX = normalized_text_x
        member.textOffsetY = normalized_text_y
        member.textScale = normalized_text_scale
        if normalized_death_date is not None:
            member.deathDate = normalized_death_date
        self.dirty = True
        return member

    def set_gravestone_portrait_adjustment(self, member_id: str, offset_x: object,
                                           offset_y: object, zoom: object,
                                           death_date: object | None = None) -> Member:
        member = self.find_by_id(member_id)
        if member is None:
            raise ValueError(tr("model.character_not_found"))
        return self.set_gravestone_adjustment(
            member_id, member.graveTemplateId, offset_x, offset_y, zoom,
            member.textOffsetX, member.textOffsetY, member.textScale, death_date,
        )

    def make_member(self, name: str, source: str) -> Member:
        try:
            candidate = max(1000, int(self.next_id))
        except (TypeError, ValueError):
            candidate = 1000
        used_ids = {m.id for m in self.members}
        used_ids.update(entry.memberId for entry in self.raid_attendance)
        while f"m{candidate:04d}" in used_ids:
            candidate += 1
        member = Member(id=f"m{candidate:04d}", name=unicodedata.normalize("NFC", name.strip()), addedDate=today_iso(), source=source)
        self.next_id = candidate + 1
        return member

    def find_by_id(self, member_id: str) -> Member | None:
        return next((m for m in self.members if m.id == member_id), None)

    def find_by_name(self, name: str) -> Member | None:
        matches = self.find_all_by_name(name)
        active = next((m for m in matches if m.lifeStatus == "active"), None)
        if active is not None:
            return active
        inactive = next((m for m in matches if m.lifeStatus == "inactive"), None)
        return inactive if inactive is not None else (matches[0] if matches else None)

    def find_all_by_name(self, name: str) -> list[Member]:
        key = norm_name(name)
        return [m for m in self.members if norm_name(m.name) == key]

    def find_active_by_name(self, name: str) -> Member | None:
        return next((m for m in self.find_all_by_name(name) if m.lifeStatus == "active"), None)

    def find_current_by_name(self, name: str) -> Member | None:
        return next((
            m for m in self.find_all_by_name(name) if m.lifeStatus in {"active", "inactive"}
        ), None)

    def find_player_by_id(self, player_id: str | None) -> Player | None:
        if not player_id:
            return None
        return next((p for p in self.players if p.playerId == player_id), None)

    def make_player(self, player_name: str) -> Player:
        try:
            candidate = max(1, int(self.next_player_id))
        except (TypeError, ValueError):
            candidate = 1
        used_ids = {p.playerId for p in self.players}
        used_ids.update(entry.playerId for entry in self.raid_attendance)
        while f"p{candidate:04d}" in used_ids:
            candidate += 1
        player = Player(f"p{candidate:04d}", unicodedata.normalize("NFC", player_name.strip()))
        self.next_player_id = candidate + 1
        return player

    def add_player(self, player_name: str) -> Player:
        player_name = unicodedata.normalize("NFC", str(player_name or "").strip())
        if not player_name:
            raise ValueError(tr("model.enter_player"))
        player = self.make_player(player_name)
        self.players.append(player)
        self.dirty = True
        return player

    def rename_player(self, player_id: str, player_name: str) -> Player:
        player = self.find_player_by_id(player_id)
        if player is None:
            raise ValueError(tr("model.player_not_found"))
        player_name = unicodedata.normalize("NFC", str(player_name or "").strip())
        if not player_name:
            raise ValueError(tr("model.enter_player"))
        player.playerName = player_name
        self.dirty = True
        return player

    def set_player_membership(self, player_id: str, start_date: object = None,
                              end_date: object = None) -> Player:
        player = self.find_player_by_id(player_id)
        if player is None:
            raise ValueError(tr("model.player_not_found"))
        start, end = validate_membership_dates(start_date, end_date)
        player.membershipStartDate = start
        player.membershipEndDate = end
        self.dirty = True
        return player

    def find_raid_by_id(self, raid_id: str) -> Raid | None:
        return next((raid for raid in self.raids if raid.id == raid_id), None)

    def create_raid(self, raid_date: object, name: object,
                    warcraft_logs_url: object = "", raid_type: object = "") -> Raid:
        raid = Raid(
            id=new_raid_id(), date=str(raid_date or ""), name=str(name or ""),
            warcraftLogsUrl=str(warcraft_logs_url or ""), status="draft",
            raidType=str(raid_type or ""),
        )
        self.raids.append(raid)
        self.raid_points.register_raid(raid.id)
        if self.raid_points.enabled and self.raid_points.calculation_mode is not None:
            self.raid_points.rebuild_scope(self.raids)
        if (self.attendance_tracking_start_date is None
                or raid.date < self.attendance_tracking_start_date):
            self.attendance_tracking_start_date = raid.date
        self.dirty = True
        return raid

    def update_raid(self, raid_id: str, raid_date: object, name: object,
                    warcraft_logs_url: object = "", raid_type: object = None) -> Raid:
        raid = self.find_raid_by_id(raid_id)
        if raid is None:
            raise ValueError(tr("raids.not_found"))
        validated = Raid(
            id=raid.id, date=str(raid_date or ""), name=str(name or ""),
            warcraftLogsUrl=str(warcraft_logs_url or ""), status=raid.status,
            raidType=raid.raidType if raid_type is None else str(raid_type or ""),
        )
        raid.date = validated.date
        raid.name = validated.name
        raid.warcraftLogsUrl = validated.warcraftLogsUrl
        raid.raidType = validated.raidType
        if self.raid_points.enabled and self.raid_points.calculation_mode is not None:
            self.raid_points.rebuild_scope(self.raids)
        self.dirty = True
        return raid

    def delete_raid(self, raid_id: str) -> Raid:
        raid = self.find_raid_by_id(raid_id)
        if raid is None:
            raise ValueError(tr("raids.not_found"))
        remaining = [entry for entry in self.raid_attendance if entry.raidId != raid_id]
        removed_attendance_ids = [
            entry.id for entry in self.raid_attendance if entry.raidId == raid_id
        ]
        self.raid_points.remove_raid(raid_id, removed_attendance_ids)
        self.raids.remove(raid)
        self.raid_attendance = remaining
        self.dirty = True
        return raid

    def attendance_for_raid(self, raid_id: str) -> list[RaidAttendance]:
        return [entry for entry in self.raid_attendance if entry.raidId == raid_id]

    def attendance_lookup(self) -> dict[str, dict[str, RaidAttendance]]:
        return attendance_index(self.raid_attendance)

    def activate_raid_points(self, *, include_existing: bool) -> None:
        self.raid_points.activate(
            (raid.id for raid in self.raids), include_existing=include_existing,
        )
        self.dirty = True

    def set_raid_point_calculation_scope(self, mode: str, start_date: str | None = None) -> None:
        self.raid_points.set_calculation_scope(mode, start_date)
        self.raid_points.rebuild_scope(self.raids)
        self.dirty = True

    def deactivate_raid_points(self) -> None:
        self.raid_points.deactivate()
        self.dirty = True

    def set_raid_point_adjustment(
        self, attendance_id: str, value: int, reason: str = "",
    ) -> None:
        entry = next((
            record for record in self.raid_attendance if record.id == attendance_id
        ), None)
        if entry is None:
            raise ValueError("Attendance-Eintrag wurde nicht gefunden.")
        if entry.raidId not in self.raid_points.included_raid_ids:
            raise ValueError("Der Raid ist nicht für die Punktewertung berücksichtigt.")
        self.raid_points.set_adjustment(attendance_id, value, reason)
        self.dirty = True

    def raid_point_history(
        self, *, player_id: str | None = None, member_id: str | None = None,
    ):
        return build_point_history(
            self.raid_points, self.raids, self.raid_attendance,
            player_id=player_id, member_id=member_id,
        )

    def set_raid_attendance_status(self, raid_id: str, player_id: str, status: str) -> RaidAttendance:
        if status not in ATTENDANCE_STATUSES:
            raise ValueError(tr("raids.invalid_attendance_status"))
        entry = self.attendance_lookup().get(raid_id, {}).get(player_id)
        if entry is None:
            raise ValueError(tr("raids.attendance_not_found"))
        entry.status = status
        self.dirty = True
        return entry

    def bench_candidates_for_date(
        self, raid_date: object, excluded_player_ids: Iterable[str] = (),
    ) -> list[tuple[Player, Member]]:
        """Return relevant players with a main character for manual bench selection."""
        preview = Raid("bench_preview", str(raid_date or ""), "Bench preview", status="recorded")
        tracking_start = min(
            value for value in (self.attendance_tracking_start_date, preview.date) if value
        )
        excluded = {str(player_id) for player_id in excluded_player_ids}
        candidates: list[tuple[Player, Member]] = []
        for player in self.players:
            if player.playerId in excluded:
                continue
            active_mains = [
                member for member in self.members
                if member.playerId == player.playerId and member.characterType == "main"
                and member.lifeStatus == "active"
            ]
            if len(active_mains) != 1:
                continue
            main = active_mains[0]
            if player_is_relevant(
                preview, tracking_start, player.membershipStartDate, player.membershipEndDate,
            ):
                candidates.append((player, main))
        return sorted(candidates, key=lambda item: item[0].playerName.casefold())

    def set_raid_bench_players(self, raid_id: str, player_ids: Iterable[str]) -> int:
        """Replace only manual bench entries; recorded present entries remain immutable."""
        raid = self.find_raid_by_id(raid_id)
        if raid is None:
            raise ValueError(tr("raids.not_found"))
        if raid.status != "recorded":
            raise ValueError(tr("raids.bench_requires_recorded"))
        desired = list(dict.fromkeys(str(player_id or "").strip() for player_id in player_ids))
        if not all(desired):
            raise ValueError(tr("raids.bench_player_not_relevant"))
        existing = self.attendance_lookup().get(raid_id, {})
        present_ids = {
            player_id for player_id, entry in existing.items() if entry.status == "present"
        }
        if present_ids.intersection(desired):
            raise ValueError(tr("raids.bench_present_conflict"))
        available = {
            player.playerId: (player, member)
            for player, member in self.bench_candidates_for_date(raid.date, present_ids)
        }
        additions: list[RaidAttendance] = []
        for player_id in desired:
            entry = existing.get(player_id)
            if entry is not None and entry.status == "bench":
                continue
            player_member = available.get(player_id)
            if player_member is None:
                raise ValueError(tr("raids.bench_player_not_relevant"))
            player, member = player_member
            additions.append(RaidAttendance(
                id=new_attendance_id(), raidId=raid.id, playerId=player.playerId,
                memberId=member.id, attendanceType=member.characterType,
                playerNameSnapshot=player.playerName, characterNameSnapshot=member.name,
                status="bench",
            ))
        removed_bench_ids = [
            entry.id for entry in self.raid_attendance
            if entry.raidId == raid_id and entry.status == "bench"
            and entry.playerId not in desired
        ]
        self.raid_points.remove_adjustments(removed_bench_ids)
        self.raid_attendance = [
            entry for entry in self.raid_attendance
            if entry.raidId != raid_id or entry.status != "bench" or entry.playerId in desired
        ] + additions
        self.dirty = True
        return len(desired)

    def set_historical_raid_bench_members(self, raid_id: str, member_ids: Iterable[str]) -> int:
        """Persist explicit historical bench data without relaxing manual eligibility.

        This path is intentionally limited to imported source data.  It keeps
        the regular editor's date/membership validation in
        :meth:`set_raid_bench_players` unchanged.
        """
        raid = self.find_raid_by_id(raid_id)
        if raid is None:
            raise ValueError(tr("raids.not_found"))
        if raid.status != "recorded":
            raise ValueError(tr("raids.bench_requires_recorded"))

        selected: dict[str, Member] = {}
        for member_id in dict.fromkeys(str(value or "").strip() for value in member_ids):
            member = self.find_by_id(member_id)
            player = self.find_player_by_id(member.playerId) if member is not None else None
            if (member is None or player is None
                    or member.characterType not in {"main", "twink"}):
                raise ValueError(tr("raids.bench_player_not_relevant"))
            current = selected.get(player.playerId)
            if current is None or (member.characterType == "main" and current.characterType != "main"):
                selected[player.playerId] = member

        existing = self.attendance_lookup().get(raid_id, {})
        present_ids = {
            player_id for player_id, entry in existing.items() if entry.status == "present"
        }
        if present_ids.intersection(selected):
            raise ValueError(tr("raids.bench_present_conflict"))

        removed_bench_ids = [
            entry.id for entry in self.raid_attendance
            if entry.raidId == raid_id and entry.status == "bench"
        ]
        self.raid_points.remove_adjustments(removed_bench_ids)
        self.raid_attendance = [
            entry for entry in self.raid_attendance
            if entry.raidId != raid_id or entry.status != "bench"
        ]
        self.raid_attendance.extend(
            RaidAttendance(
                id=new_attendance_id(), raidId=raid.id, playerId=player_id,
                memberId=member.id, attendanceType=member.characterType,
                playerNameSnapshot=self.find_player_by_id(player_id).playerName,
                characterNameSnapshot=member.name, status="bench",
            )
            for player_id, member in selected.items()
        )
        self.dirty = True
        return len(selected)

    def reset_raid_attendance(self, raid_id: str) -> int:
        raid = self.find_raid_by_id(raid_id)
        if raid is None:
            raise ValueError(tr("raids.not_found"))
        previous_entries = self.attendance_for_raid(raid_id)
        previous_count = len(previous_entries)
        self.raid_points.remove_adjustments(entry.id for entry in previous_entries)
        self.raid_attendance = [
            entry for entry in self.raid_attendance if entry.raidId != raid_id
        ]
        raid.status = "draft"
        self.dirty = True
        return previous_count

    def resolve_raid_attendance(self, names: Iterable[str]) -> AttendanceResolution:
        return resolve_attendance(
            names, self.members, self.players, self.wcl_member_aliases,
        )

    def set_wcl_member_alias(self, wcl_name: object, member_id: object) -> str:
        """Persist one exact normalized WarcraftLogs name to an existing member ID."""
        name_key = exact_name_key(wcl_name)
        member_key = str(member_id or "").strip()
        if not name_key:
            raise ValueError(tr("model.enter_character"))
        if self.find_by_id(member_key) is None:
            raise ValueError(tr("model.character_not_found"))
        exact_matches = [
            member for member in self.members
            if exact_name_key(member.name) == name_key
        ]
        if len(exact_matches) == 1 and exact_matches[0].id != member_key:
            raise ValueError(tr("raids.wcl_alias_exact_conflict", name=exact_matches[0].name))
        self.wcl_member_aliases[name_key] = member_key
        self.dirty = True
        return member_key

    def import_raid_attendance(self, raid_id: str, names: Iterable[str],
                               add_unknown_names: Iterable[str] = (),
                               unknown_decisions: dict[str, tuple[str, str | None]] | None = None) -> dict:
        """Atomically migrate assignments, apply unknown decisions and replace attendance."""
        raid = self.find_raid_by_id(raid_id)
        if raid is None:
            raise ValueError(tr("raids.not_found"))
        ordered_names = [
            unicodedata.normalize("NFC", str(name or "").strip())
            for name in names if str(name or "").strip()
        ]
        initial = self.resolve_raid_attendance(ordered_names)
        if initial.ambiguous_names:
            raise ValueError(tr(
                "raids.ambiguous_characters",
                names=", ".join(initial.ambiguous_names),
            ))
        unknown_by_key = {norm_name(name): name for name in initial.unknown_names}
        add_keys = {norm_name(name) for name in add_unknown_names}
        if not add_keys.issubset(unknown_by_key):
            raise ValueError(tr("raids.invalid_unknown_selection"))
        decisions = {
            norm_name(name): (str(action), main_id)
            for name, (action, main_id) in (unknown_decisions or {}).items()
        }
        if not set(decisions).issubset(unknown_by_key):
            raise ValueError(tr("raids.invalid_unknown_selection"))
        for key in add_keys:
            decisions.setdefault(key, ("main", None))
        for key in unknown_by_key:
            decisions.setdefault(key, ("discard", None))
        if any(action not in {"main", "twink", "discard"} for action, _main_id in decisions.values()):
            raise ValueError(tr("raids.invalid_unknown_selection"))

        snapshot = (
            copy.deepcopy(self.members), copy.deepcopy(self.players),
            copy.deepcopy(self.raid_attendance), copy.deepcopy(self.raid_points), self.next_id,
            self.next_player_id, raid.status, self.dirty,
        )
        try:
            for unassigned in initial.unassigned_characters:
                member = self.find_by_id(unassigned.member_id)
                if (member is None or member.lifeStatus != "active" or member.playerId
                        or member.characterType not in {"", "not_set", "main"}):
                    raise ValueError(tr(
                        "raids.ambiguous_characters", names=unassigned.character_name,
                    ))
                self.assign_character_type(member.id, "main", None, member.raidRole)

            added_main = 0
            added_twink = 0
            for key, (action, main_id) in decisions.items():
                if action == "discard":
                    continue
                if action == "twink":
                    main = self.find_by_id(main_id or "")
                    if (main is None or main.lifeStatus != "active"
                            or main.characterType != "main" or not main.playerId
                            or self.find_player_by_id(main.playerId) is None):
                        raise ValueError(tr("model.active_main_required"))
                member = self.add_member(unknown_by_key[key], "Raid Attendance CSV")
                if action == "main":
                    self.assign_character_type(member.id, "main", None, "not_set")
                    player = self.find_player_by_id(member.playerId)
                    if player is None:
                        raise ValueError(tr("model.player_not_found"))
                    player.membershipStartDate = raid.date
                    added_main += 1
                else:
                    self.assign_character_type(member.id, "twink", main_id, "not_set")
                    added_twink += 1

            included_names = [
                name for name in ordered_names
                if (norm_name(name) not in unknown_by_key
                    or decisions[norm_name(name)][0] != "discard")
            ]
            resolved = self.resolve_raid_attendance(included_names)
            if resolved.unknown_names or resolved.ambiguous_names or resolved.unassigned_characters:
                names_text = ", ".join((
                    *resolved.unknown_names, *resolved.ambiguous_names,
                    *(item.character_name for item in resolved.unassigned_characters),
                ))
                raise ValueError(tr("raids.unresolved_characters", names=names_text))
            replacement = attendance_records(raid.id, resolved.candidates)
            replaced_attendance_ids = [
                entry.id for entry in self.raid_attendance if entry.raidId == raid.id
            ]
            self.raid_points.remove_adjustments(replaced_attendance_ids)
            self.raid_attendance = [
                entry for entry in self.raid_attendance if entry.raidId != raid.id
            ] + replacement
            raid.status = "recorded"
            self.dirty = True
            return {
                "participants": len(replacement),
                "added": added_main + added_twink,
                "added_main": added_main,
                "added_twink": added_twink,
                "auto_initialized": len(initial.unassigned_characters),
                "discarded": sum(action == "discard" for action, _main_id in decisions.values()),
                "merged": resolved.merged_characters,
            }
        except Exception:
            (self.members, self.players, self.raid_attendance, self.raid_points, self.next_id,
             self.next_player_id, raid.status, self.dirty) = snapshot
            raise

    def create_raid_with_attendance(
        self, raid_date: object, name: object, warcraft_logs_url: object,
        raid_type: object, names: Iterable[str],
        unknown_decisions: dict[str, tuple[str, str | None]] | None = None,
        bench_player_ids: Iterable[str] = (),
    ) -> tuple[Raid, dict]:
        """Create raid and attendance as one rollback-safe project operation."""
        if str(raid_type or "").strip() not in RAID_TYPES:
            raise ValueError(tr("raids.raid_type_required"))
        snapshot = (
            copy.deepcopy(self.members), copy.deepcopy(self.players),
            copy.deepcopy(self.raids), copy.deepcopy(self.raid_attendance),
            copy.deepcopy(self.raid_points),
            self.next_id, self.next_player_id, self.attendance_tracking_start_date,
            self.dirty,
        )
        try:
            raid = self.create_raid(
                raid_date, name, warcraft_logs_url, raid_type,
            )
            summary = self.import_raid_attendance(
                raid.id, names, unknown_decisions=unknown_decisions,
            )
            summary["bench"] = self.set_raid_bench_players(raid.id, bench_player_ids)
            return raid, summary
        except Exception:
            (
                self.members, self.players, self.raids, self.raid_attendance,
                self.raid_points,
                self.next_id, self.next_player_id, self.attendance_tracking_start_date,
                self.dirty,
            ) = snapshot
            raise

    @staticmethod
    def _bulk_report_url_key(value: object) -> str:
        return str(value or "").strip().rstrip("/").casefold()

    def _bulk_raid_exists(
        self, raid_date: str, raid_type: str, report_url: str,
    ) -> bool:
        return self._matching_raid(raid_date, raid_type) is not None

    def _matching_raid(self, raid_date: str, raid_type: str) -> Raid | None:
        """Match one instance inside a raid evening by date and normalized type."""
        return next((
            raid for raid in self.raids
            if raid.date == raid_date
            and normalize_csv_raid_type(raid.raidType, RAID_TYPES) == raid_type
        ), None)

    def analyze_bulk_raid_csv_files(
        self, paths: Iterable[Path | str],
    ) -> tuple[BulkRaidCsvPlan, ...]:
        """Analyze Casts CSV files without modifying the project."""
        plans: list[BulkRaidCsvPlan] = []
        seen_identities = {
            (raid.date, raid_type)
            for raid in self.raids
            if (raid_type := normalize_csv_raid_type(raid.raidType, RAID_TYPES))
        }
        ordered_paths = sorted(
            (Path(path) for path in paths),
            key=lambda path: (path.name.casefold(), str(path).casefold()),
        )
        for source_path in ordered_paths:
            try:
                parsed = read_raid_csv(source_path)
                filename_metadata = raid_csv_filename_metadata(source_path)

                header_date = (
                    str(normalize_iso_date(parsed.metadata.raid_date))
                    if parsed.metadata.raid_date else ""
                )
                filename_date = (
                    str(normalize_iso_date(filename_metadata.raid_date))
                    if filename_metadata.raid_date else ""
                )
                if header_date and filename_date and header_date != filename_date:
                    plans.append(BulkRaidCsvPlan(
                        source_path=source_path, status="invalid",
                        detail=tr("raids.bulk_conflict", field=tr("common.date")),
                    ))
                    continue
                raid_date = header_date or filename_date
                if not raid_date:
                    plans.append(BulkRaidCsvPlan(
                        source_path=source_path, status="invalid",
                        detail=tr("raids.bulk_missing_date"),
                    ))
                    continue

                header_type = (
                    normalize_csv_raid_type(parsed.metadata.raid_type, RAID_TYPES)
                    if parsed.metadata.raid_type else None
                )
                filename_type = (
                    normalize_csv_raid_type(filename_metadata.raid_type, RAID_TYPES)
                    if filename_metadata.raid_type else None
                )
                if parsed.metadata.raid_type and header_type is None:
                    plans.append(BulkRaidCsvPlan(
                        source_path=source_path, raid_date=raid_date,
                        report_url=validate_logs_url(parsed.metadata.report_url or ""),
                        names=tuple(parsed.names), duplicates=tuple(parsed.duplicates),
                        status="unknown_type", detail=tr("raids.bulk_type_unknown"),
                    ))
                    continue
                if header_type and filename_type and header_type != filename_type:
                    plans.append(BulkRaidCsvPlan(
                        source_path=source_path, raid_date=raid_date,
                        status="invalid",
                        detail=tr("raids.bulk_conflict", field=tr("raids.raid_type")),
                    ))
                    continue
                raid_type = header_type or filename_type
                if raid_type is None:
                    plans.append(BulkRaidCsvPlan(
                        source_path=source_path, raid_date=raid_date,
                        report_url=validate_logs_url(parsed.metadata.report_url or ""),
                        names=tuple(parsed.names), duplicates=tuple(parsed.duplicates),
                        status="unknown_type", detail=tr("raids.bulk_type_unknown"),
                    ))
                    continue

                report_url = validate_logs_url(parsed.metadata.report_url or "")
                names = tuple(parsed.names)
                if not names:
                    plans.append(BulkRaidCsvPlan(
                        source_path=source_path, raid_date=raid_date,
                        raid_type=raid_type, report_url=report_url,
                        status="invalid", detail=tr("raids.bulk_no_participants"),
                    ))
                    continue
                resolution = self.resolve_raid_attendance(names)
                unresolved_names = tuple(dict.fromkeys((
                    *resolution.unknown_names, *resolution.ambiguous_names,
                )))

                identity = (raid_date, raid_type)
                existing_raid = self._matching_raid(raid_date, raid_type)
                if existing_raid is not None:
                    status = (
                        "merge" if report_url and not existing_raid.warcraftLogsUrl
                        else "existing"
                    )
                else:
                    status = "existing" if identity in seen_identities else "new"
                unknown_names = unresolved_names
                if status == "new" and unknown_names:
                    status = "needs_assignment"
                plans.append(BulkRaidCsvPlan(
                    source_path=source_path, raid_date=raid_date,
                    raid_type=raid_type, report_url=report_url,
                    names=names, duplicates=tuple(parsed.duplicates),
                    unknown_names=unknown_names, status=status,
                    detail=(
                        tr("raids.bulk_existing_detail") if status == "existing"
                        else tr("raids.bulk_unresolved", names=", ".join(unknown_names))
                        if status == "needs_assignment" else ""
                    ),
                ))
                if status in {"new", "needs_assignment"}:
                    seen_identities.add(identity)
            except Exception as exc:
                plans.append(BulkRaidCsvPlan(
                    source_path=source_path, status="invalid",
                    detail=tr("raids.bulk_invalid_file", error=exc),
                ))
        return tuple(plans)

    def import_bulk_raid_csv_plans(
        self, plans: Iterable[BulkRaidCsvPlan],
        unknown_decisions_by_path: Mapping[
            Path | str, Mapping[str, tuple[str, str | None]],
        ] | None = None,
    ) -> BulkRaidCsvResult:
        """Add each new raid independently; existing project data is never replaced."""
        original = tuple(plans)
        updated = list(original)
        decisions_by_path = {
            str(Path(path)): dict(decisions)
            for path, decisions in (unknown_decisions_by_path or {}).items()
        }
        ordered = sorted(
            (
                (index, plan) for index, plan in enumerate(original)
                if plan.status in {"new", "needs_assignment", "merge"}
            ),
            key=lambda item: (item[1].raid_date, item[0]),
        )
        imported = 0
        for index, plan in ordered:
            existing_raid = self._matching_raid(plan.raid_date, plan.raid_type)
            if existing_raid is not None and plan.status == "merge":
                existing_raid.warcraftLogsUrl = plan.report_url
                existing_raid.sources = tuple(dict.fromkeys((*existing_raid.sources, "warcraftlogs")))
                self.dirty = True
                updated[index] = replace(plan, status="imported", detail="")
                imported += 1
                continue
            if existing_raid is not None:
                updated[index] = replace(
                    plan, status="existing", detail=tr("raids.bulk_existing_detail"),
                )
                continue
            try:
                resolution = self.resolve_raid_attendance(plan.names)
                if resolution.ambiguous_names:
                    raise ValueError(tr(
                        "raids.bulk_unresolved", names=", ".join(resolution.ambiguous_names),
                    ))
                unknown_by_key = {
                    norm_name(name): name for name in resolution.unknown_names
                }
                decisions = {
                    name: decision
                    for name, decision in decisions_by_path.get(str(plan.source_path), {}).items()
                    if norm_name(name) in unknown_by_key
                }
                if unknown_by_key and not all(
                    key in {norm_name(name) for name in decisions}
                    for key in unknown_by_key
                ):
                    raise ValueError(tr(
                        "raids.bulk_unresolved",
                        names=", ".join(unknown_by_key.values()),
                    ))
                raid, _summary = self.create_raid_with_attendance(
                    plan.raid_date, plan.raid_type, plan.report_url,
                    plan.raid_type, plan.names, unknown_decisions=decisions,
                )
                raid.sources = tuple(dict.fromkeys((*raid.sources, "warcraftlogs")))
                updated[index] = replace(plan, status="imported", detail="")
                imported += 1
            except Exception as exc:
                updated[index] = replace(
                    plan, status="import_error",
                    detail=tr("raids.bulk_import_error", error=exc),
                )
        skipped = sum(plan.status == "existing" for plan in updated)
        failed = sum(
            plan.status in {"invalid", "unknown_type", "import_error"}
            for plan in updated
        )
        return BulkRaidCsvResult(tuple(updated), imported, skipped, failed)

    def attendance_statistics_for_player(
        self, player_id: str, *, start_date: object = None, end_date: object = None,
        category: str = "", raid_type: str = "",
    ):
        player = self.find_player_by_id(player_id)
        if player is None:
            raise ValueError(tr("model.player_not_found"))
        return calculate_statistics(
            player.playerId, self.raids, self.raid_attendance,
            self.attendance_tracking_start_date,
            player.membershipStartDate, player.membershipEndDate,
            start_date=start_date, end_date=end_date,
            category=category, raid_type=raid_type,
        )

    def attendance_statistics_for_member(
        self, member_id: str, *, start_date: object = None, end_date: object = None,
        category: str = "", raid_type: str = "",
    ):
        """Reuse the shared attendance projection for one stable member ID."""
        member = self.find_by_id(member_id)
        if member is None:
            raise ValueError(tr("model.character_not_found"))
        player = self.find_player_by_id(member.playerId)
        return calculate_statistics(
            member.playerId or "", self.raids, self.raid_attendance,
            self.attendance_tracking_start_date,
            player.membershipStartDate if player is not None else None,
            player.membershipEndDate if player is not None else None,
            start_date=start_date, end_date=end_date,
            category=category, raid_type=raid_type, member_id=member.id,
        )

    def player_is_active(self, player_id: str) -> bool:
        """A player is active while at least one assigned character is active."""
        return self.find_player_by_id(player_id) is not None and any(
            member.playerId == player_id and member.lifeStatus == "active"
            for member in self.members
        )

    def current_attendance_assignments(self) -> dict[str, tuple[str, str]]:
        """Return current assignments for UI labels, never historical attribution."""
        return {
            member.id: (member.playerId, member.characterType)
            for member in self.members
            if member.playerId and member.characterType in {"main", "twink"}
        }

    def active_main_for_player(self, player_id: str, exclude_member_id: str | None = None) -> Member | None:
        return next((
            member for member in self.members
            if member.id != exclude_member_id
            and member.lifeStatus == "active"
            and member.playerId == player_id
            and member.characterType == "main"
        ), None)

    def associated_main(self, member: Member | str) -> Member | None:
        value = self.find_by_id(member) if isinstance(member, str) else member
        if value is None or value.characterType != "twink" or not value.playerId:
            return None
        return self.active_main_for_player(value.playerId, exclude_member_id=value.id)

    def _ensure_player_for_main(self, member: Member) -> str:
        if member.playerId and self.find_player_by_id(member.playerId):
            return member.playerId
        player = self.make_player(member.name)
        self.players.append(player)
        member.playerId = player.playerId
        return player.playerId

    def assign_character_type(self, member_id: str, character_type: str,
                              associated_main_id: str | None, raid_role: str,
                              replace_existing_main: bool = False) -> Member:
        member = self.find_by_id(member_id)
        if member is None:
            raise ValueError(tr("model.character_not_found"))
        if character_type not in CHARACTER_TYPES:
            raise ValueError(tr("model.invalid_character_type"))
        if raid_role not in RAID_ROLES:
            raise ValueError(tr("model.invalid_raid_role"))

        if member.lifeStatus == "dead":
            if character_type != member.characterType:
                raise ValueError(tr("model.historical_role_protected"))
            if character_type == "twink":
                main = self.find_by_id(associated_main_id or "")
                if main is None or not member.playerId or main.playerId != member.playerId:
                    raise ValueError(tr("model.historical_assignment_protected"))
            member.raidRole = raid_role
            self.dirty = True
            return member

        if character_type == "twink":
            if not associated_main_id:
                raise ValueError(tr("model.active_main_required"))
            if associated_main_id == member.id:
                raise ValueError(tr("model.self_main_forbidden"))
            main = self.find_by_id(associated_main_id)
            if main is None or main.lifeStatus != "active" or main.characterType != "main":
                raise ValueError(tr("model.active_main_required"))
            member.playerId = self._ensure_player_for_main(main)
            member.characterType = "twink"
            member.raidRole = raid_role
            self.dirty = True
            return member

        if character_type == "main":
            player_id = self._ensure_player_for_main(member)
            existing_main = self.active_main_for_player(player_id, exclude_member_id=member.id)
            if existing_main is not None and not replace_existing_main:
                raise MainConflictError(existing_main)
            if existing_main is not None:
                existing_main.characterType = "twink"
            member.characterType = "main"
            member.raidRole = raid_role
            self.dirty = True
            return member

        member.characterType = "not_set"
        member.playerId = None
        member.raidRole = raid_role
        self.dirty = True
        return member

    def update_member_assignment(self, member_id: str, player_id: str | None,
                                 character_type: str, raid_role: str,
                                 replace_existing_main: bool = False) -> Member:
        member = self.find_by_id(member_id)
        if member is None:
            raise ValueError(tr("model.character_not_found"))
        if player_id is not None and self.find_player_by_id(player_id) is None:
            raise ValueError(tr("model.player_not_found"))
        if character_type not in CHARACTER_TYPES:
            raise ValueError(tr("model.invalid_character_type"))
        if raid_role not in RAID_ROLES:
            raise ValueError(tr("model.invalid_raid_role"))
        if player_id is None and character_type != "not_set":
            raise ValueError(tr("model.player_required"))
        if (member.lifeStatus == "dead"
                and (player_id != member.playerId or character_type != member.characterType)):
            raise ValueError(tr("model.historical_assignment_protected"))

        existing_main = None
        if member.lifeStatus == "active" and player_id and character_type == "main":
            existing_main = self.active_main_for_player(player_id, exclude_member_id=member.id)
            if existing_main is not None and not replace_existing_main:
                raise MainConflictError(existing_main)

        if existing_main is not None:
            existing_main.characterType = "twink"
        member.playerId = player_id
        member.characterType = character_type
        member.raidRole = raid_role
        self.dirty = True
        return member

    def main_successor_candidates(
            self, main_member_id: str,
            excluded_member_ids: Iterable[str] = ()) -> list[Member]:
        """Return active twinks eligible to succeed one current main."""
        main = self.find_by_id(main_member_id)
        if main is None:
            raise ValueError(tr("model.character_not_found"))
        if main.lifeStatus != "active" or main.characterType != "main":
            raise ValueError(tr("model.main_succession_requires_active_main"))
        if not main.playerId:
            return []
        excluded = {str(member_id or "").strip() for member_id in excluded_member_ids}
        return sorted((
            member for member in self.members
            if member.id != main.id
            and member.id not in excluded
            and member.playerId == main.playerId
            and member.lifeStatus == "active"
            and member.characterType == "twink"
        ), key=lambda member: (norm_name(member.name), member.id))

    def mark_main_dead_with_successor(
            self, main_member_id: str, successor_member_id: str | None = None,
            death_date: object | None = None,
            excluded_member_ids: Iterable[str] = ()) -> tuple[Member, Member | None]:
        """Atomically mark a current main dead and promote an explicit successor."""
        main = self.find_by_id(main_member_id)
        if main is None:
            raise ValueError(tr("model.character_not_found"))
        if main.lifeStatus != "active" or main.characterType != "main":
            raise ValueError(tr("model.main_death_requires_active_main"))
        successor = self.validate_main_successor(
            main.id, successor_member_id, excluded_member_ids,
        )

        normalized_death_date = normalize_death_date(
            today_iso() if death_date is None else death_date,
        )
        main_state = copy.deepcopy(main.__dict__)
        successor_state = copy.deepcopy(successor.__dict__) if successor is not None else None
        previous_dirty = self.dirty
        try:
            self.set_member_life_status(
                main.id, "dead", _validated_main_succession=True,
            )
            main.deathDate = normalized_death_date
            if successor is not None:
                self.update_member_assignment(
                    successor.id, main.playerId, "main", successor.raidRole,
                )
        except Exception:
            main.__dict__.clear()
            main.__dict__.update(main_state)
            if successor is not None and successor_state is not None:
                successor.__dict__.clear()
                successor.__dict__.update(successor_state)
            self.dirty = previous_dirty
            raise
        return main, successor

    def validate_main_successor(
            self, main_member_id: str, successor_member_id: str | None,
            excluded_member_ids: Iterable[str] = ()) -> Member | None:
        """Validate one explicit succession choice without mutating project state."""
        candidates = self.main_successor_candidates(main_member_id, excluded_member_ids)
        candidate_by_id = {member.id: member for member in candidates}
        successor_id = str(successor_member_id or "").strip()
        successor = candidate_by_id.get(successor_id) if successor_id else None
        if candidates and successor is None:
            if not successor_id:
                raise ValueError(tr("model.main_successor_required"))
            raise ValueError(tr("model.invalid_main_successor"))
        if not candidates and successor_id:
            raise ValueError(tr("model.invalid_main_successor"))
        return successor

    def _merge_armory_metadata(self, member: Member, result: dict, summary: dict,
                               changed_members: set[str]) -> None:
        incoming = {
            "race": normalize_race(result.get("race")),
            "className": normalize_class_name(str(result.get("className") or "")) or None,
        }
        for field, value in incoming.items():
            if not value:
                continue
            current = getattr(member, field)
            if not current:
                setattr(member, field, value)
                if field == "className":
                    member.spec = normalize_spec(value, member.spec)
                    member.classSpec = combine_class_spec(value, member.spec)
                changed_members.add(member.id)
            elif current != value:
                summary["conflicts"].append({
                    "memberId": member.id,
                    "characterName": member.name,
                    "field": field,
                    "current": current,
                    "incoming": value,
                })

    def apply_armory_results(self, payload: dict, expected_session_id: str | None) -> dict:
        summary = {"updated": 0, "ignored": 0, "conflicts": [], "stale": False}
        if (not isinstance(payload, dict) or payload.get("format") != ARMORY_RESULT_FORMAT
                or payload.get("formatVersion") != ARMORY_RESULT_VERSION
                or not expected_session_id or payload.get("sessionId") != expected_session_id):
            summary["stale"] = True
            return summary
        context = (
            str(payload.get("region") or "").casefold(),
            str(payload.get("realm") or "").casefold(),
            str(payload.get("gameVersion") or "").casefold(),
        )
        expected = (self.region.casefold(), self.realm.casefold(), self.game_version.casefold())
        if context != expected:
            summary["stale"] = True
            return summary
        results = payload.get("results")
        if not isinstance(results, list):
            summary["stale"] = True
            return summary

        changed_members: set[str] = set()
        for result in results:
            if not isinstance(result, dict):
                summary["ignored"] += 1
                continue
            member_id = str(result.get("memberId") or "").strip()
            member = self.find_by_id(member_id)
            if (member is None or member.lifeStatus != "active" or
                    norm_name(result.get("characterName")) != norm_name(member.name)
                    or result.get("source") != "classicwowarmory"):
                summary["ignored"] += 1
                continue
            self._merge_armory_metadata(member, result, summary, changed_members)
        if changed_members:
            self.dirty = True
        summary["updated"] = len(changed_members)
        return summary

    def apply_character_cache(self, payload: dict) -> dict:
        """Enrich known non-dead members without treating the cache as a roster source."""
        summary = {"updated": 0, "ignored": 0, "conflicts": [], "stale": False}
        records = payload.get("characters") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            summary["stale"] = True
            return summary

        eligible = [member for member in self.members if member.lifeStatus != "dead"]
        name_counts: dict[str, int] = {}
        for member in eligible:
            key = norm_name(member.name)
            name_counts[key] = name_counts.get(key, 0) + 1

        changed_members: set[str] = set()
        matched_records: set[int] = set()
        for member in eligible:
            record = find_character_cache_record(
                payload,
                member_id=member.id,
                character_name=member.name,
                region=self.region,
                realm=self.realm,
                game_version=self.game_version,
            )
            if record is None:
                continue
            if not record.get("memberId") and name_counts.get(norm_name(member.name), 0) != 1:
                continue
            record_identity = id(record)
            if record_identity in matched_records:
                continue
            matched_records.add(record_identity)
            self._merge_armory_metadata(member, record, summary, changed_members)

        if changed_members:
            self.dirty = True
        summary["updated"] = len(changed_members)
        summary["ignored"] = sum(isinstance(record, dict) for record in records) - len(matched_records)
        return summary

    def apply_armory_conflict(self, conflict: dict) -> bool:
        member = self.find_by_id(str(conflict.get("memberId") or ""))
        field = conflict.get("field")
        if member is None or member.lifeStatus == "dead" or field not in {"race", "className"}:
            return False
        value = (normalize_race(conflict.get("incoming")) if field == "race" else
                 normalize_class_name(str(conflict.get("incoming") or "")))
        if not value:
            return False
        setattr(member, field, value)
        if field == "className":
            member.spec = normalize_spec(value, member.spec)
            member.classSpec = combine_class_spec(value, member.spec)
        self.dirty = True
        return True

    def set_member_life_status(
            self, member_id: str, life_status: str,
            replace_existing_main: bool = False,
            allow_dead_reanimation: bool = False,
            _validated_main_succession: bool = False) -> Member:
        member = self.find_by_id(member_id)
        if member is None:
            raise ValueError(tr("model.character_not_found"))
        if life_status not in LIFE_STATUSES:
            raise ValueError(tr("model.invalid_life_status"))

        previous_status = member.lifeStatus
        if previous_status == life_status:
            return member
        if previous_status == "dead" and life_status == "inactive":
            raise ValueError(tr("model.dead_to_inactive_forbidden"))
        if previous_status == "dead" and life_status == "active" and not allow_dead_reanimation:
            raise ValueError(tr("model.dead_reanimation_requires_confirmation"))
        if (previous_status == "active" and life_status == "dead"
                and member.characterType == "main"
                and not _validated_main_succession
                and self.main_successor_candidates(member.id)):
            raise ValueError(tr("model.main_successor_required"))

        existing_main = None
        if life_status == "active":
            current_same_name = self.find_current_by_name(member.name)
            if current_same_name is not None and current_same_name.id != member.id:
                raise ValueError(tr("model.current_name_exists", name=current_same_name.name))
            if member.characterType == "main" and member.playerId:
                existing_main = self.active_main_for_player(
                    member.playerId, exclude_member_id=member.id,
                )
                if existing_main is not None and not replace_existing_main:
                    raise MainConflictError(existing_main)

        if existing_main is not None:
            existing_main.characterType = "twink"

        member.lifeStatus = life_status
        if life_status == "dead":
            self._assign_gravestone_template(member)
        # inactive -> active is a normal reversible status change. Emergency
        # dead -> active intentionally retains deathDate, graveTemplateId,
        # gravestoneTemplate and historical portrait artifacts.
        self.dirty = True
        return member

    def add_member(self, name: str, source: str = "Manuell") -> Member:
        name = unicodedata.normalize("NFC", name.strip())
        if not name:
            raise ValueError(tr("model.enter_character"))
        existing = self.find_current_by_name(name)
        if existing:
            raise ValueError(tr("model.current_name_exists", name=existing.name))
        member = self.make_member(name, source)
        self.members.append(member)
        self.dirty = True
        return member

    def import_grabber_members(self, records: Iterable[Mapping[str, object]],
                               source: str = "Portrait Grabber") -> dict[str, object]:
        """Übernimmt eine Grabber-Liste ohne aktuelle Charaktere zu reaktivieren."""
        added = 0
        existing = 0
        new_incarnations = 0
        created: list[dict[str, object]] = []
        seen: set[str] = set()
        for record in records:
            name = unicodedata.normalize(
                "NFC", str(record.get("characterName") or "").strip(),
            )
            key = norm_name(name)
            if not key or key in seen:
                continue
            seen.add(key)
            if self.find_current_by_name(name) is not None:
                existing += 1
                continue
            had_dead = any(member.lifeStatus == "dead" for member in self.find_all_by_name(name))
            member = self.add_member(name, source)
            race = normalize_race(record.get("race"))
            class_name = normalize_class_name(str(record.get("className") or ""))
            if race:
                member.race = race
            if class_name:
                member.className = class_name
                member.classSpec = class_name
            added += 1
            new_incarnations += int(had_dead)
            created.append({
                "memberId": member.id, "characterName": member.name,
                "race": member.race, "className": member.className,
                "newIncarnation": had_dead,
            })
        return {
            "added": added,
            "existing": existing,
            "newIncarnations": new_incarnations,
            "created": created,
        }

    def update_member_metadata(self, member_id: str, race: object = None,
                               class_name: object = None) -> bool:
        """Ergänzt bestätigte Race/Class-Daten per stabiler ID ohne Konflikt-Overwrite."""
        member = self.find_by_id(str(member_id or "").strip())
        if member is None:
            raise ValueError(tr("model.character_not_found"))
        if member.lifeStatus == "dead":
            return False
        incoming_race = normalize_race(race)
        incoming_class = normalize_class_name(str(class_name or ""))
        changed = False
        if incoming_race and not member.race:
            member.race = incoming_race
            changed = True
        if incoming_class and not member.className:
            member.className = incoming_class
            member.classSpec = combine_class_spec(incoming_class, member.spec)
            changed = True
        self.dirty = self.dirty or changed
        return changed

    def reset_gravestone_adjustment(self, member_id: str) -> Member:
        member = self.find_by_id(str(member_id or "").strip())
        if member is None:
            raise ValueError(tr("model.character_not_found"))
        if member.lifeStatus != "dead":
            raise ValueError(tr("graveyard.not_dead"))
        member.graveTemplateId = ""
        member.gravestoneTemplate = ""
        member.portraitOffsetX = 0.0
        member.portraitOffsetY = 0.0
        member.portraitZoom = 1.0
        member.textOffsetX = 0.0
        member.textOffsetY = 0.0
        member.textScale = 1.0
        self.dirty = True
        return member

    def classify_member_import(self, names: Iterable[str]) -> tuple[list[Member], list[str], list[str]]:
        current_by_name: dict[str, Member] = {}
        for member in self.members:
            if member.lifeStatus not in {"active", "inactive"}:
                continue
            key = norm_name(member.name)
            if key in current_by_name:
                raise ValueError(tr(
                    "model.multiple_current_names",
                    region=self.region, realm=self.realm, name=member.name,
                ))
            current_by_name[key] = member

        existing: list[Member] = []
        new_names: list[str] = []
        dead_existing: list[str] = []
        seen: set[str] = set()
        for raw_name in names:
            name = unicodedata.normalize("NFC", str(raw_name or "").strip())
            key = norm_name(name)
            if not key or key in seen:
                continue
            seen.add(key)
            current = current_by_name.get(key)
            if current is not None:
                existing.append(current)
                continue
            new_names.append(name)
            if any(member.lifeStatus == "dead" for member in self.find_all_by_name(name)):
                dead_existing.append(name)
        return existing, new_names, dead_existing

    def import_active_members(self, names: Iterable[str], source: str) -> list[Member]:
        _existing, new_names, _dead_existing = self.classify_member_import(names)
        original_length = len(self.members)
        original_next_id = self.next_id
        original_dirty = self.dirty
        created: list[Member] = []
        try:
            for name in new_names:
                created.append(self.add_member(name, source))
        except Exception:
            del self.members[original_length:]
            self.next_id = original_next_id
            self.dirty = original_dirty
            raise
        return created

    def remove_member(self, member_id: str) -> Member:
        member = self.find_by_id(member_id)
        if member is None:
            raise ValueError(tr("model.character_not_found"))
        self.members.remove(member)
        self.dirty = True
        return member

    def to_payload(self) -> dict:
        payload = {
            "format": PROJECT_FORMAT,
            "formatVersion": PROJECT_FORMAT_VERSION,
            "appVersion": f"Python {APP_VERSION}",
            "savedAt": now_iso(),
            "region": self.region,
            "realm": self.realm,
            "guildName": self.guild_name,
            "pointMode": self.active_point_mode(),
            "dkpModeEnabled": self.dkp_enabled,
            "clmRosterId": self.clm_roster_id,
            "gameVersion": self.game_version,
            "nextId": self.next_id,
            "nextPlayerId": self.next_player_id,
            "attendanceTrackingStartDate": self.attendance_tracking_start_date,
            "players": [player.to_dict() for player in self.players],
            "members": [member.to_dict() for member in self.members],
            "raids": [raid.to_dict() for raid in self.raids],
            "raidAttendance": [entry.to_dict() for entry in self.raid_attendance],
            "raidPoints": self.raid_points.to_dict(),
            "eternalDkp": self.eternal_dkp.to_dict(),
        }
        if self.wcl_member_aliases:
            payload["wclMemberAliases"] = dict(sorted(self.wcl_member_aliases.items()))
        return payload

    def load_payload(self, payload: dict, path: Path | None = None) -> None:
        raw_version = payload.get("formatVersion")
        format_version = 1
        if raw_version is not None:
            if isinstance(raw_version, bool):
                raise ValueError("Ungültige formatVersion in der Projektdatei.")
            if isinstance(raw_version, int):
                format_version = raw_version
            elif isinstance(raw_version, str) and raw_version.strip().isdigit():
                format_version = int(raw_version.strip())
            else:
                raise ValueError("Ungültige formatVersion in der Projektdatei.")
            if format_version > PROJECT_FORMAT_VERSION:
                raise ValueError(
                    f"Projektformat {format_version} ist neuer als die unterstützte Version "
                    f"{PROJECT_FORMAT_VERSION}."
                )
        raw_members = payload.get("members")
        if not isinstance(raw_members, list):
            raise ValueError("Keine gültige Guild-Gear-Checker-Projektdatei: 'members' fehlt.")
        raw_players = payload.get("players", [])
        if not isinstance(raw_players, list):
            raise ValueError("Ungültige Spielerliste in der Projektdatei.")
        try:
            tracking_start = normalize_optional_date(payload.get("attendanceTrackingStartDate"))
        except RaidValidationError as exc:
            raise ValueError(raid_error_text(exc)) from exc
        raw_raid_points = payload.get("raidPoints", {})
        try:
            loaded_raid_points = RaidPointState.from_dict(raw_raid_points)
        except ValueError as exc:
            raise ValueError(f"Ungültige Raidpunkte-Daten: {exc}") from exc
        try:
            loaded_eternal_dkp = EternalDkpState.from_dict(payload.get("eternalDkp", {}))
        except ValueError as exc:
            raise ValueError(f"Ungültige Eternal-DKP-Daten: {exc}") from exc
        loaded_guild_name = unicodedata.normalize(
            "NFC", str(payload.get("guildName") or "").strip(),
        )
        loaded_dkp_enabled = payload.get("dkpModeEnabled", False)
        if not isinstance(loaded_dkp_enabled, bool):
            raise ValueError("Ungültiger Aktivierungszustand des DKP-Modus.")
        raw_point_mode = str(payload.get("pointMode") or "").strip()
        if raw_point_mode and raw_point_mode not in POINT_MODES:
            raise ValueError("Ungültiger Punktmodus in der Projektdatei.")
        loaded_point_mode = raw_point_mode or (
            POINT_MODE_ETERNAL if loaded_dkp_enabled
            else POINT_MODE_RAID if loaded_raid_points.enabled else ""
        )
        loaded_clm_roster_id = str(payload.get("clmRosterId") or "").strip()
        loaded_players: list[Player] = []
        player_ids: set[str] = set()
        for item in raw_players:
            if not isinstance(item, dict):
                continue
            try:
                player = Player.from_dict(item)
            except RaidValidationError as exc:
                raise ValueError(raid_error_text(exc)) from exc
            if not player.playerId or not player.playerName:
                continue
            if player.playerId in player_ids:
                raise ValueError(tr("model.duplicate_player_id", id=player.playerId))
            player_ids.add(player.playerId)
            loaded_players.append(player)
        member_items = [
            item for item in raw_members
            if isinstance(item, dict) and norm_name(item.get("name"))
        ]
        explicit_ids: set[str] = set()
        for item in member_items:
            member_id = str(item.get("id") or "").strip()
            if not member_id:
                continue
            if member_id in explicit_ids:
                raise ValueError(tr("model.duplicate_member_id", id=member_id))
            explicit_ids.add(member_id)

        loaded: list[Member] = []
        next_fallback = 1000
        used_ids: set[str] = set()
        current_names: set[str] = set()
        for item in member_items:
            while f"m{next_fallback:04d}" in explicit_ids or f"m{next_fallback:04d}" in used_ids:
                next_fallback += 1
            member = Member.from_dict(
                item, f"m{next_fallback:04d}", format_version=format_version,
            )
            if not str(item.get("id") or "").strip():
                member.id = f"m{next_fallback:04d}"
                next_fallback += 1
            if member.id in used_ids:
                raise ValueError(tr("model.duplicate_member_id", id=member.id))
            used_ids.add(member.id)
            if member.lifeStatus in {"active", "inactive"}:
                key = norm_name(member.name)
                if key in current_names:
                    raise ValueError(tr(
                        "model.multiple_current_names",
                        region=payload.get("region") or REGION,
                        realm=payload.get("realm") or REALM,
                        name=member.name,
                    ))
                current_names.add(key)
            loaded.append(member)

        active_main_players: set[str] = set()
        for member in loaded:
            if member.playerId is not None and member.playerId not in player_ids:
                raise ValueError(tr("model.unknown_player_id", name=member.name, id=member.playerId))
            if member.lifeStatus == "active" and member.playerId and member.characterType == "main":
                if member.playerId in active_main_players:
                    raise ValueError(tr("model.multiple_active_mains", id=member.playerId))
                active_main_players.add(member.playerId)

        raw_wcl_aliases = payload.get("wclMemberAliases", {})
        loaded_wcl_aliases: dict[str, str] = {}
        conflicting_aliases: set[str] = set()
        if isinstance(raw_wcl_aliases, dict):
            loaded_member_ids = {member.id for member in loaded}
            for raw_name, raw_member_id in raw_wcl_aliases.items():
                if not isinstance(raw_name, str) or not isinstance(raw_member_id, str):
                    continue
                name_key = exact_name_key(raw_name)
                member_id = raw_member_id.strip()
                if not name_key or member_id not in loaded_member_ids:
                    continue
                previous = loaded_wcl_aliases.get(name_key)
                if previous is not None and previous != member_id:
                    conflicting_aliases.add(name_key)
                else:
                    loaded_wcl_aliases[name_key] = member_id
        for name_key in conflicting_aliases:
            loaded_wcl_aliases.pop(name_key, None)

        raw_raids = payload.get("raids", [])
        raw_attendance = payload.get("raidAttendance", [])
        if not isinstance(raw_raids, list):
            raise ValueError(tr("raids.invalid_list"))
        if not isinstance(raw_attendance, list):
            raise ValueError(tr("raids.invalid_attendance_list"))
        loaded_raids: list[Raid] = []
        raid_ids: set[str] = set()
        for item in raw_raids:
            if not isinstance(item, dict):
                raise ValueError(tr("raids.invalid_list"))
            try:
                raid = Raid.from_dict(item)
            except RaidValidationError as exc:
                raise ValueError(raid_error_text(exc)) from exc
            if raid.id in raid_ids:
                raise ValueError(tr("raids.duplicate_id", id=raid.id))
            raid_ids.add(raid.id)
            loaded_raids.append(raid)
        loaded_attendance: list[RaidAttendance] = []
        attendance_ids: set[str] = set()
        raid_player_pairs: set[tuple[str, str]] = set()
        for item in raw_attendance:
            if not isinstance(item, dict):
                raise ValueError(tr("raids.invalid_attendance_list"))
            try:
                entry = RaidAttendance.from_dict(item)
            except RaidValidationError as exc:
                raise ValueError(raid_error_text(exc)) from exc
            if entry.id in attendance_ids:
                raise ValueError(tr("raids.duplicate_attendance_id", id=entry.id))
            if entry.raidId not in raid_ids:
                raise ValueError(tr("raids.unknown_raid_id", id=entry.raidId))
            pair = (entry.raidId, entry.playerId)
            if pair in raid_player_pairs:
                raise ValueError(tr("raids.duplicate_player", id=entry.playerId))
            attendance_ids.add(entry.id)
            raid_player_pairs.add(pair)
            loaded_attendance.append(entry)

        numeric_ids = [
            int(match.group(1)) for member in loaded
            if (match := re.fullmatch(r"m(\d+)", member.id))
        ]
        numeric_ids.extend(
            int(match.group(1)) for entry in loaded_attendance
            if (match := re.fullmatch(r"m(\d+)", entry.memberId))
        )
        try:
            stored_next_id = int(payload.get("nextId") or 1000)
        except (TypeError, ValueError):
            stored_next_id = 1000
        computed_next_id = max(numeric_ids, default=999) + 1
        numeric_player_ids = [
            int(match.group(1)) for player in loaded_players
            if (match := re.fullmatch(r"p(\d+)", player.playerId))
        ]
        numeric_player_ids.extend(
            int(match.group(1)) for entry in loaded_attendance
            if (match := re.fullmatch(r"p(\d+)", entry.playerId))
        )
        try:
            stored_next_player_id = int(payload.get("nextPlayerId") or 1)
        except (TypeError, ValueError):
            stored_next_player_id = 1

        self.members = loaded
        self.players = loaded_players
        self.wcl_member_aliases = loaded_wcl_aliases
        self.raids = loaded_raids
        self.raid_attendance = loaded_attendance
        self.raid_points = loaded_raid_points
        self.raid_points_legacy_scope_required = bool(
            isinstance(raw_raid_points, dict)
            and (loaded_raid_points.enabled or loaded_raid_points.ever_enabled)
            and "calculationMode" not in raw_raid_points
        )
        self.eternal_dkp = loaded_eternal_dkp
        self.point_mode = loaded_point_mode
        self.attendance_tracking_start_date = tracking_start
        self.next_id = max(1000, stored_next_id, next_fallback, computed_next_id)
        self.next_player_id = max(1, stored_next_player_id, max(numeric_player_ids, default=0) + 1)
        self.region = str(payload.get("region") or REGION)
        self.realm = str(payload.get("realm") or REALM)
        self.guild_name = loaded_guild_name
        self.dkp_enabled = loaded_dkp_enabled
        self.clm_roster_id = loaded_clm_roster_id
        self.game_version = str(payload.get("gameVersion") or GAME_VERSION)
        self.project_path = path
        self.dirty = self.ensure_gravestone_templates()

    def save(self, path: Path, backup: bool = True) -> None:
        paths = project_paths(path)
        paths.root.mkdir(parents=True, exist_ok=True)
        if backup:
            backup_project_file(paths.project)
        atomic_write_bytes(
            paths.project,
            (json.dumps(self.to_payload(), ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        self.project_path = paths.project
        self.dirty = False

    def load(self, path: Path) -> None:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("Projektdatei enthält kein gültiges JSON-Objekt.")
        self.load_payload(payload, Path(path))
        self.portrait_migration_summary = migrate_legacy_portraits(path, self.members)


class ProjectPackageError(RuntimeError):
    """Critical package export error with a UI-localizable stage."""

    def __init__(self, stage: str, detail: str) -> None:
        super().__init__(detail)
        self.stage = stage


@dataclass(frozen=True)
class ProjectPackageSummary:
    target: Path
    portrait_count: int
    historical_portrait_count: int
    missing_marker_count: int
    missing_portrait_count: int
    warnings: tuple[str, ...]
    entries: tuple[str, ...]


@dataclass(frozen=True)
class _ProjectPackageFile:
    source: Path
    archive_name: str
    kind: str


def project_package_default_filename(project_path: Path | None) -> str:
    raw_name = project_path.stem.strip() if project_path else ""
    base = sanitize_filename(raw_name).strip(" ._") if raw_name else ""
    if not base or base.upper() in {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
    }:
        base = "GuildProject"
    return f"{base}_mit_Portraits_{today_iso()}.zip"


def _validate_package_archive_name(archive_name: str) -> str:
    path = PurePosixPath(archive_name)
    if (
        not archive_name
        or "\\" in archive_name
        or ":" in archive_name
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ProjectPackageError("zip", tr("checker.package_unsafe_path", path=archive_name))
    return path.as_posix()


def _project_package_project_bytes(model: GuildModel) -> bytes:
    try:
        return (json.dumps(model.to_payload(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    except Exception as exc:
        raise ProjectPackageError("project", str(exc)) from exc


def _project_package_manifest_bytes(manifest: dict) -> bytes:
    try:
        return (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    except Exception as exc:
        raise ProjectPackageError("manifest", str(exc)) from exc


def _project_package_files(model: GuildModel, portrait_root: Path) -> tuple[list[_ProjectPackageFile], int, list[str]]:
    files: list[_ProjectPackageFile] = []
    warnings: list[str] = []
    missing_portraits = 0
    used_entries = {"project.ggc", "manifest.json"}
    migrate_legacy_portraits(portrait_root.parent / "portrait-migration.ggc", model.members)

    for member in sorted(model.members, key=lambda value: (value.id.casefold(), value.id)):
        archive_name = _validate_package_archive_name(f"portraits/{member.id}.png")
        entry_key = archive_name.casefold()
        if entry_key in used_entries:
            warning = tr("checker.package_duplicate_path", path=archive_name)
            warnings.append(warning)
            LOGGER.warning(warning)
            continue
        used_entries.add(entry_key)
        source = portrait_root / f"{member.id}.png"
        try:
            present = source.is_file()
        except OSError:
            present = False
        if present:
            files.append(_ProjectPackageFile(source, archive_name, "portrait"))
        else:
            missing_portraits += 1
            warning = tr("checker.package_portrait_missing", path=source)
            warnings.append(warning)
            LOGGER.warning(warning)
    files.sort(key=lambda item: (item.archive_name.casefold(), item.archive_name))
    return files, missing_portraits, warnings


def _read_project_package_file(item: _ProjectPackageFile) -> bytes:
    return item.source.read_bytes()


def _validate_project_package(path: Path, expected_entries: tuple[str, ...]) -> None:
    with zipfile.ZipFile(path, "r") as archive:
        names = tuple(archive.namelist())
        if names != expected_entries or len(names) != len(set(names)):
            raise ProjectPackageError("zip", tr("checker.package_invalid_entries"))
        damaged = archive.testzip()
        if damaged is not None:
            raise ProjectPackageError("zip", tr("checker.package_damaged_entry", name=damaged))


def create_project_package(model: GuildModel, target: Path,
                           portrait_root: Path | None = None) -> ProjectPackageSummary:
    """Atomically export the current model and only its related portrait files."""
    target = Path(target)
    resolved_portraits = Path(portrait_root) if portrait_root is not None else project_portrait_root(model.project_path)
    if resolved_portraits is None:
        raise ProjectPackageError("project", tr("checker.package_export_requires_saved_project"))
    portrait_root = resolved_portraits
    project_bytes = _project_package_project_bytes(model)
    planned, missing_portraits, warning_list = _project_package_files(model, portrait_root)

    readable: list[tuple[_ProjectPackageFile, bytes]] = []
    for item in planned:
        try:
            readable.append((item, _read_project_package_file(item)))
        except OSError as exc:
            missing_portraits += 1
            warning = tr("checker.package_file_unavailable", path=item.source, error=exc)
            warning_list.append(warning)
            LOGGER.warning(warning)

    portrait_count = sum(item.kind == "portrait" for item, _data in readable)
    historical_count = sum(item.kind == "history" for item, _data in readable)
    marker_count = sum(item.kind == "missing" for item, _data in readable)
    manifest = {
        "packageFormatVersion": PROJECT_PACKAGE_FORMAT_VERSION,
        "createdAt": now_iso(),
        "suiteVersion": APP_VERSION,
        "projectFile": "project.ggc",
        "projectFormatVersion": PROJECT_FORMAT_VERSION,
        "portraitCount": portrait_count,
        "historicalPortraitCount": historical_count,
        "missingMarkerCount": marker_count,
        "missingPortraitCount": missing_portraits,
    }
    manifest_bytes = _project_package_manifest_bytes(manifest)
    expected_entries = ("project.ggc", "manifest.json", *(item.archive_name for item, _data in readable))

    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project.ggc", project_bytes)
            archive.writestr("manifest.json", manifest_bytes)
            for item, data in readable:
                archive.writestr(item.archive_name, data)
        _validate_project_package(temporary_path, expected_entries)
        os.replace(temporary_path, target)
        temporary_path = None
    except ProjectPackageError:
        raise
    except Exception as exc:
        raise ProjectPackageError("zip", str(exc)) from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning(tr("checker.package_temp_cleanup_failed", path=temporary_path))

    return ProjectPackageSummary(
        target=target,
        portrait_count=portrait_count,
        historical_portrait_count=historical_count,
        missing_marker_count=marker_count,
        missing_portrait_count=missing_portraits,
        warnings=tuple(warning_list),
        entries=expected_entries,
    )


@dataclass(frozen=True)
class ProjectPackageImportSummary:
    source: Path
    project_path: Path
    portrait_count: int
    historical_portrait_count: int
    missing_marker_count: int


def import_project_package(source: Path, target_project: Path) -> ProjectPackageImportSummary:
    """Validiert und importiert ein Projektpaket ohne gemeinsame Software-Assets."""
    source = Path(source)
    paths = project_paths(target_project)
    try:
        with zipfile.ZipFile(source, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len({name.casefold() for name in names}):
                raise ProjectPackageError("zip", tr("checker.package_import_duplicate_paths"))
            for info in infos:
                safe_name = _validate_package_archive_name(info.filename)
                if safe_name not in {"project.ggc", "manifest.json"} and not safe_name.startswith("portraits/"):
                    raise ProjectPackageError("zip", tr("checker.package_import_unsafe_entry", name=safe_name))
                if safe_name.startswith("portraits/") and Path(safe_name).suffix.casefold() not in {".png", ".missing"}:
                    raise ProjectPackageError("zip", tr("checker.package_import_unsafe_portrait", name=safe_name))
                if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                    raise ProjectPackageError("zip", tr("checker.package_import_symlink", name=safe_name))
            if "project.ggc" not in names or "manifest.json" not in names:
                raise ProjectPackageError("manifest", tr("checker.package_import_required_files"))
            damaged = archive.testzip()
            if damaged is not None:
                raise ProjectPackageError("zip", tr("checker.package_import_damaged", name=damaged))
            manifest = json.loads(archive.read("manifest.json").decode("utf-8-sig"))
            project_payload = json.loads(archive.read("project.ggc").decode("utf-8-sig"))
            if not isinstance(manifest, dict) or manifest.get("projectFile") != "project.ggc":
                raise ProjectPackageError("manifest", tr("checker.package_import_invalid_manifest"))
            if int(manifest.get("packageFormatVersion", -1)) != PROJECT_PACKAGE_FORMAT_VERSION:
                raise ProjectPackageError("manifest", tr("checker.package_import_unsupported_version"))
            if not isinstance(project_payload, dict) or not isinstance(project_payload.get("members"), list):
                raise ProjectPackageError("project", tr("checker.package_import_invalid_members"))
            portrait_infos = [info for info in infos if info.filename.startswith("portraits/")]
            portrait_count = sum(
                info.filename.count("/") == 1 and info.filename.casefold().endswith(".png")
                for info in portrait_infos
            )
            historical_count = sum(
                info.filename.startswith("portraits/history/") and info.filename.casefold().endswith(".png")
                for info in portrait_infos
            )
            marker_count = sum(info.filename.casefold().endswith(".missing") for info in portrait_infos)
            for key, actual in (
                ("portraitCount", portrait_count),
                ("historicalPortraitCount", historical_count),
                ("missingMarkerCount", marker_count),
            ):
                if int(manifest.get(key, -1)) != actual:
                    raise ProjectPackageError("manifest", tr("checker.package_import_counter_mismatch", name=key))
            if paths.project.exists() or paths.portraits.exists():
                raise ProjectPackageError("project", tr("checker.package_import_target_exists"))
            paths.root.mkdir(parents=True, exist_ok=True)
            staged = Path(tempfile.mkdtemp(prefix=".ggc_import_", dir=paths.root))
            try:
                (staged / "project.ggc").write_bytes(archive.read("project.ggc"))
                for info in portrait_infos:
                    destination = staged / Path(*PurePosixPath(info.filename).parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(archive.read(info))
                os.replace(staged / "project.ggc", paths.project)
                staged_portraits = staged / "portraits"
                if staged_portraits.exists():
                    os.replace(staged_portraits, paths.portraits)
            finally:
                shutil.rmtree(staged, ignore_errors=True)
    except ProjectPackageError:
        raise
    except Exception as exc:
        raise ProjectPackageError("zip", str(exc)) from exc
    return ProjectPackageImportSummary(source, paths.project, portrait_count, historical_count, marker_count)


class GuildGearCheckerApp(tk.Tk):
    BG = "#101419"
    PANEL = "#171d25"
    PANEL_2 = "#202833"
    BORDER = "#2d3744"
    TEXT = "#eef3f8"
    MUTED = "#9aa8b8"
    GREEN = "#2f6e4f"
    RED = "#75343a"
    BLUE = "#3b526d"
    TAB_ACTIVE = "#344d66"

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} · Python Suite v{APP_VERSION}")
        self._suite_settings_path = app_base_dir() / "config" / "suite_settings.json"
        self._suite_settings = read_suite_settings(self._suite_settings_path)
        saved_geometry = self._suite_settings.get("checker_geometry")
        self._work_area = work_area_for_geometry(self, saved_geometry)
        minimum = dynamic_minimum(self._work_area, (1040, 680), (760, 520))
        self.minsize(*minimum)
        self.geometry(resolve_geometry(
            saved_geometry, self._work_area, minimum,
        ).as_tk())
        self.roster_zoom_percent = clamp_roster_zoom(self._suite_settings.get("roster_zoom", 100))
        self.roster_fit_mode = bool(self._suite_settings.get("roster_fit", False))
        self.roster_view_mode = "cards"
        self.gear_outdated_tracking = normalize_bool_setting(
            self._suite_settings.get("gear_outdated_tracking", False), default=False,
        )
        self.gear_outdated_days = normalize_outdated_days(
            self._suite_settings.get("gear_outdated_days", GEAR_OUTDATED_DEFAULT_DAYS)
        )
        saved_roster_details = self._suite_settings.get("roster_details_visible", True)
        self.roster_details_visible = (
            saved_roster_details if isinstance(saved_roster_details, bool) else True
        )
        self.configure(bg=self.BG)
        self.header_font_family = load_lifecraft_font(
            app_base_dir() / "assets" / "fonts" / "LifeCraft_Font.ttf"
        )

        self.model = GuildModel()
        self.model.new_empty()
        self._gravestone_inventory = self.model.gravestone_inventory()
        self.selected_member_id: str | None = None
        self.current_tab = "Gildenliste"
        self.sort_state: dict[str, tuple[str, bool]] = {}
        self.raid_sort_state = ("date", True)
        self.raid_statistics_sort_state = ("player", False)
        self._portrait_ref = None
        self._portrait_watch_signature = None
        self._checker_banner_photo = None
        self._checker_banner_image = None
        self._checker_banner_resize_job = None
        self._graveyard_bg_ref = None
        self._graveyard_portrait_refs: list = []
        self._graveyard_card_refs: list = []
        self._graveyard_render_manifest: list[dict] = []
        self._active_gravestone_editor = None
        self._graveyard_resize_job = None
        self._graveyard_background_cache: dict[tuple, object] = {}
        self._graveyard_template_cache: dict[tuple, object] = {}
        self._graveyard_card_cache: dict[tuple, object] = {}
        self._roster_resize_job = None
        self._roster_portrait_refs: list = []
        self._roster_icon_refs: list = []
        self._roster_portrait_cache: dict[tuple, object] = {}
        self._roster_icon_cache: dict[tuple, object] = {}
        self._class_icon_refs: dict[str, object] = {}
        self._class_icon_small_refs: dict[str, object] = {}
        self._class_icon_detail_ref = None
        self._icon_download_thread: threading.Thread | None = None
        self._detail_window_id = None
        self._armory_session_id: str | None = None
        self._armory_result_signature = None
        self._armory_processed_tokens: set[tuple[str, str, str]] = set()

        self._configure_styles()
        self._build_ui()
        self._load_class_icons()
        self._load_autosave_or_seed()
        self.refresh_all(select_first=False)
        self.after(350, self._start_missing_icon_download)
        self.after(1200, self._watch_portrait_folder)
        self.after(1400, self._watch_armory_results)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", background=self.PANEL, fieldbackground=self.PANEL, foreground=self.TEXT, rowheight=38, borderwidth=0)
        style.configure("Treeview.Heading", background=self.PANEL_2, foreground=self.TEXT, relief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", self.BLUE)], foreground=[("selected", "white")])
        style.configure("TCombobox", fieldbackground=self.PANEL_2, background=self.PANEL_2, foreground=self.TEXT, arrowcolor=self.TEXT)
        style.map("TCombobox", fieldbackground=[("readonly", self.PANEL_2)], foreground=[("readonly", self.TEXT)], selectbackground=[("readonly", self.PANEL_2)], selectforeground=[("readonly", self.TEXT)])
        style.configure("Vertical.TScrollbar", background=self.PANEL_2, troughcolor=self.PANEL)

    def _button(self, parent, text, command, kind="normal", **kwargs):
        bg = self.PANEL_2
        active = "#344153"
        if kind == "primary":
            bg, active = self.GREEN, "#397e5d"
        elif kind == "danger":
            bg, active = self.RED, "#873c43"
        return tk.Button(parent, text=text, command=command, bg=bg, fg="white", activebackground=active, activeforeground="white", relief="flat", bd=0, padx=12, pady=7, font=("Segoe UI", 9, "bold"), cursor="hand2", **kwargs)

    def _label(self, parent, text="", muted=False, **kwargs):
        return tk.Label(parent, text=text, bg=kwargs.pop("bg", self.PANEL), fg=self.MUTED if muted else self.TEXT, font=kwargs.pop("font", ("Segoe UI", 10)), **kwargs)

    def _build_ui(self) -> None:
        self.checker_banner_canvas = tk.Canvas(
            self, height=CHECKER_BANNER_HEIGHT, bg=self.PANEL,
            highlightthickness=0, borderwidth=0,
        )
        self.checker_banner_canvas.pack(fill="x")
        self._checker_banner_item = self.checker_banner_canvas.create_image(
            0, 0, anchor="nw", state="hidden",
        )
        self._checker_title_item = self.checker_banner_canvas.create_text(
            18, CHECKER_BANNER_HEIGHT // 2, anchor="w", text=tr("checker.title"),
            font=(self.header_font_family, 27), fill="#ffffff",
        )
        self._checker_version_item = self.checker_banner_canvas.create_text(
            1180, CHECKER_BANNER_HEIGHT // 2, anchor="e",
            text=f"Python Suite v{APP_VERSION} · EU · Stitches · Classic Era",
            font=("Segoe UI", 10, "bold"), fill="#ffffff",
        )
        self.checker_banner_canvas.bind("<Configure>", self._checker_banner_resize_requested)
        self._load_checker_banner()

        actions = tk.Frame(self, bg=self.PANEL)
        actions.pack(fill="x", padx=17, pady=(6, 7))
        self._button(actions, tr("checker.new_empty"), self.new_project).pack(side="left", padx=3)
        self._button(actions, tr("checker.remove_all"), self.remove_all_characters, kind="danger").pack(side="left", padx=3)
        self._button(actions, tr("checker.open"), self.open_project).pack(side="left", padx=3)
        self._button(actions, tr("common.save"), self.save_project).pack(side="left", padx=3)
        self._button(actions, tr("checker.save_as"), self.save_project_as).pack(side="left", padx=3)
        self._button(actions, tr("checker.export"), self.export_project, kind="primary").pack(side="left", padx=3)
        self._button(actions, tr("checker.export_with_portraits"), self.export_project_with_portraits).pack(side="left", padx=3)
        self._button(actions, tr("checker.package_import"), self.import_project_with_portraits).pack(side="left", padx=3)
        self._button(actions, tr("checker.portrait_grabber"), self.open_portrait_grabber, kind="primary").pack(side="right", padx=3)
        self._button(actions, tr("checker.add_member"), self.add_member_dialog).pack(side="right", padx=3)
        self._button(actions, tr("checker.raid_csv"), self.import_csv).pack(side="right", padx=3)
        self.language_var = tk.StringVar(value=language_display_values()[0 if get_language() == "de" else 1])
        language_combo = ttk.Combobox(actions, textvariable=self.language_var,
                                      values=language_display_values(), state="readonly", width=9)
        language_combo.pack(side="right", padx=5)
        language_combo.bind("<<ComboboxSelected>>", self._language_changed)
        self._button(actions, tr("checker.guild_sync"), self.open_guild_roster_review).pack(side="right", padx=3)

        body = tk.Frame(self, bg=self.BG)
        body.pack(fill="both", expand=True, padx=14, pady=14)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_sidebar(body)
        self._build_center(body)
        self._build_detail_panel(body)

        footer = tk.Frame(self, bg=self.PANEL, height=30)
        footer.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value=tr("common.ready"))
        self.project_var = tk.StringVar(value=tr("checker.no_external_project"))
        self._label(footer, textvariable=self.status_var, muted=True, bg=self.PANEL).pack(side="left", padx=14)
        self._label(footer, textvariable=self.project_var, muted=True, bg=self.PANEL).pack(side="right", padx=14)

    def _load_checker_banner(self) -> None:
        self._checker_banner_photo = None
        self._checker_banner_image = None
        if Image is None or ImageTk is None or ImageOps is None:
            self.checker_banner_canvas.itemconfigure(self._checker_banner_item, image="", state="hidden")
            return
        try:
            with Image.open(checker_banner_path()) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB")
                self._checker_banner_image = image.copy()
            self.after_idle(self._render_checker_banner_cover)
        except Exception:
            self._checker_banner_image = None
            self.checker_banner_canvas.itemconfigure(self._checker_banner_item, image="", state="hidden")

    def _checker_banner_resize_requested(self, event) -> None:
        if self._checker_banner_resize_job is not None:
            try:
                self.after_cancel(self._checker_banner_resize_job)
            except Exception:
                pass
        self._checker_banner_resize_job = self.after(
            60, lambda width=event.width, height=event.height:
            self._render_checker_banner_cover(width, height),
        )

    def _render_checker_banner_cover(self, width: int | None = None, height: int | None = None) -> None:
        self._checker_banner_resize_job = None
        width = int(width or self.checker_banner_canvas.winfo_width())
        height = int(height or self.checker_banner_canvas.winfo_height())
        if width <= 1 or height <= 1:
            return
        self.checker_banner_canvas.coords(self._checker_title_item, 18, height // 2)
        self.checker_banner_canvas.coords(self._checker_version_item, width - 18, height // 2)
        if self._checker_banner_image is None or Image is None or ImageTk is None or ImageOps is None:
            return
        rendered = ImageOps.fit(
            self._checker_banner_image, (width, height),
            method=Image.Resampling.LANCZOS, centering=CHECKER_BANNER_FOCAL_POINT,
        )
        overlay = Image.new("RGB", rendered.size, "#101419")
        rendered = Image.blend(rendered, overlay, 0.22)
        self._checker_banner_photo = ImageTk.PhotoImage(rendered, master=self)
        self.checker_banner_canvas.itemconfigure(
            self._checker_banner_item, image=self._checker_banner_photo, state="normal",
        )
        self.checker_banner_canvas.coords(self._checker_banner_item, 0, 0)
        self.checker_banner_canvas.tag_raise(self._checker_title_item)
        self.checker_banner_canvas.tag_raise(self._checker_version_item)

    def _build_sidebar(self, parent) -> None:
        side = tk.Frame(parent, bg=self.PANEL, width=220, highlightbackground=self.BORDER, highlightthickness=1)
        side.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        side.pack_propagate(False)
        self.sidebar = side
        self._label(side, tr("checker.filter"), font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=14, pady=(14, 4))
        self._label(side, tr("checker.current_tab_filter"), muted=True).pack(anchor="w", padx=14, pady=(0, 8))

        self.search_var = tk.StringVar()
        e = tk.Entry(side, textvariable=self.search_var, bg=self.PANEL_2, fg=self.TEXT, insertbackground=self.TEXT, relief="flat", font=("Segoe UI", 10))
        e.pack(fill="x", padx=14, pady=(0, 10), ipady=7)
        e.bind("<KeyRelease>", lambda _e: self.refresh_center())

        member_panel = tk.Frame(side, bg=self.PANEL)
        self.sidebar_member_panel = member_panel
        member_panel.pack(fill="both", expand=True)
        self.gear_filter = tk.StringVar(value=tr("common.all"))
        self.enchant_filter = tk.StringVar(value=tr("common.all"))
        self._combo_block(member_panel, tr("gear.label"), self.gear_filter,
                          [tr("common.all")] + [gear_status_display(v) for v in GEAR_VALUES])
        self._combo_block(member_panel, tr("enchants.label"), self.enchant_filter,
                          [tr("common.all")] + [enchant_status_display(v) for v in ENCHANT_VALUES])
        self._button(member_panel, tr("checker.reset_filters"), self.reset_filters).pack(fill="x", padx=14, pady=(4, 10))

        tk.Frame(member_panel, bg=self.BORDER, height=1).pack(fill="x", padx=14, pady=4)
        self._label(member_panel, tr("checker.overview"), font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=14, pady=(10, 8))
        self.stat_active = tk.StringVar(value="0")
        self.stat_inactive = tk.StringVar(value="0")
        self.stat_dead = tk.StringVar(value="0")
        self.stat_needs = tk.StringVar(value="0")
        self.stat_unchecked = tk.StringVar(value="0")
        self._stat_row(member_panel, tr("life.active"), self.stat_active)
        self._stat_row(member_panel, tr("life.inactive"), self.stat_inactive)
        self._stat_row(member_panel, tr("tabs.graveyard"), self.stat_dead)
        self._stat_row(member_panel, tr("tabs.action"), self.stat_needs)
        self._stat_row(member_panel, tr("tabs.unchecked"), self.stat_unchecked)

        tk.Frame(member_panel, bg=self.BORDER, height=1).pack(fill="x", padx=14, pady=(14, 8))
        self._label(member_panel, tr("checker.portraits"), font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=14, pady=(4, 4))
        self._label(member_panel, tr("checker.portrait_info"), muted=True, justify="left").pack(anchor="w", padx=14)
        self._button(member_panel, tr("checker.open_portrait_folder"), self.open_portrait_folder).pack(fill="x", padx=14, pady=(10, 4))
        self._button(member_panel, tr("checker.reload_portraits"), self.reload_selected_portrait).pack(fill="x", padx=14, pady=(0, 12))

        raid_panel = tk.Frame(side, bg=self.PANEL)
        self.sidebar_raid_panel = raid_panel
        self.raid_status_filter = tk.StringVar(value=tr("common.all"))
        self._combo_block(
            raid_panel, tr("common.status"), self.raid_status_filter,
            [tr("common.all"), tr("raids.status_draft"), tr("raids.status_recorded")],
        )
        self.raid_stat_total = tk.StringVar(value="0")
        self.raid_stat_recorded = tk.StringVar(value="0")
        self.raid_stat_open = tk.StringVar(value="0")
        tk.Frame(raid_panel, bg=self.BORDER, height=1).pack(fill="x", padx=14, pady=4)
        self._label(
            raid_panel, tr("raids.summary"), font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=14, pady=(10, 8))
        self._stat_row(raid_panel, tr("raids.total"), self.raid_stat_total)
        self._stat_row(raid_panel, tr("raids.status_recorded"), self.raid_stat_recorded)
        self._stat_row(raid_panel, tr("raids.status_draft"), self.raid_stat_open)

    def _combo_block(self, parent, label, variable, values) -> None:
        self._label(parent, label, muted=True).pack(anchor="w", padx=14, pady=(3, 2))
        c = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        c.pack(fill="x", padx=14, pady=(0, 8))
        c.bind("<<ComboboxSelected>>", lambda _e: self.refresh_center())

    def _stat_row(self, parent, label, variable) -> None:
        row = tk.Frame(parent, bg=self.PANEL)
        row.pack(fill="x", padx=14, pady=3)
        self._label(row, label, muted=True).pack(side="left")
        self._label(row, textvariable=variable, font=("Segoe UI", 12, "bold")).pack(side="right")

    def _build_center(self, parent) -> None:
        center = tk.Frame(parent, bg=self.PANEL, highlightbackground=self.BORDER, highlightthickness=1)
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        center.grid_rowconfigure(2, weight=1)
        center.grid_columnconfigure(0, weight=1)
        self.center = center

        primary = tk.Frame(center, bg=self.PANEL)
        primary.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 3))
        for column in range(5):
            primary.grid_columnconfigure(column, weight=1, uniform="primary_nav")
        self.primary_nav_buttons: dict[str, tk.Button] = {}
        primary_items = (
            ("Member", tr("tabs.member"), lambda: self.switch_tab("Gildenliste")),
            ("Roster", tr("tabs.roster"), lambda: self.switch_tab("Roster")),
            ("Friedhof", tr("tabs.graveyard"), lambda: self.switch_tab("Friedhof")),
            ("Raids", tr("tabs.raids"), lambda: self.switch_tab("Raids")),
            ("Settings", tr("tabs.settings"), self.open_settings_dialog),
        )
        for column, (key, label, command) in enumerate(primary_items):
            button = tk.Button(
                primary, text=label, command=command, bg=self.PANEL_2, fg=self.TEXT,
                activebackground=self.TAB_ACTIVE, activeforeground="white", relief="flat", bd=0,
                padx=8, pady=7, font=("Segoe UI", 10, "bold"), cursor="hand2",
            )
            button.grid(row=0, column=column, sticky="ew", padx=2)
            self.primary_nav_buttons[key] = button

        self.member_subnav = tk.Frame(center, bg=self.PANEL)
        self.member_subnav.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))
        member_tabs = ("Gildenliste", "Handlungsbedarf", "Ungeprüft", "Inaktiv", "Alle Charaktere")
        for column in range(len(member_tabs) + 1):
            self.member_subnav.grid_columnconfigure(column, weight=1 if column < len(member_tabs) else 0)
        self.tab_buttons: dict[str, tk.Button] = {}
        for column, tab in enumerate(member_tabs):
            button = tk.Button(
                self.member_subnav, text=tr(TAB_TRANSLATION_KEYS[tab]),
                command=lambda t=tab: self.switch_tab(t), bg=self.PANEL_2, fg=self.TEXT,
                activebackground=self.TAB_ACTIVE, activeforeground="white", relief="flat", bd=0,
                padx=5, pady=4, font=("Segoe UI", 8, "bold"), cursor="hand2",
            )
            button.grid(row=0, column=column, sticky="ew", padx=2)
            self.tab_buttons[tab] = button
        self.tab_buttons["Roster"] = self.primary_nav_buttons["Roster"]
        self.tab_buttons["Friedhof"] = self.primary_nav_buttons["Friedhof"]
        self.tab_buttons["Raids"] = self.primary_nav_buttons["Raids"]
        self.visible_count_var = tk.StringVar(value="")
        self._label(self.member_subnav, textvariable=self.visible_count_var, muted=True).grid(
            row=0, column=len(member_tabs), sticky="e", padx=(8, 2),
        )

        self.roster_mode_controls = tk.Frame(center, bg=self.PANEL)
        self.roster_mode_buttons: dict[str, tk.Button] = {}
        self._label(self.roster_mode_controls, tr("tabs.roster"), muted=True).pack(side="left", padx=(2, 8))
        for mode, key in (("cards", "roster.cards_view"), ("list", "roster.list_view")):
            button = tk.Button(
                self.roster_mode_controls, text=tr(key),
                command=lambda value=mode: self._set_roster_view_mode(value),
                bg=self.PANEL_2, fg=self.TEXT, activebackground=self.TAB_ACTIVE,
                activeforeground="white", relief="flat", bd=0, padx=10, pady=4,
                font=("Segoe UI", 9, "bold"), cursor="hand2",
            )
            button.pack(side="left", padx=2)
            self.roster_mode_buttons[mode] = button
        self._label(self.roster_mode_controls, textvariable=self.visible_count_var, muted=True).pack(side="right", padx=4)

        self.center_stack = tk.Frame(center, bg=self.PANEL)
        self.center_stack.grid(row=2, column=0, sticky="nsew")
        self.center_stack.grid_rowconfigure(0, weight=1)
        self.center_stack.grid_columnconfigure(0, weight=1)
        self._build_table_view()
        self._build_graveyard_view()
        self._build_roster_view()
        self._build_raid_view()
        self._update_tab_styles()

    def _build_table_view(self) -> None:
        self.table_view = tk.Frame(self.center_stack, bg=self.PANEL)
        self.table_view.grid(row=0, column=0, sticky="nsew")
        self.table_view.grid_rowconfigure(0, weight=1)
        self.table_view.grid_columnconfigure(0, weight=1)
        columns = ("name", "class", "spec", "gear", "ench", "checked")
        self.tree = ttk.Treeview(self.table_view, columns=columns, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=42, minwidth=42, stretch=False, anchor="center")
        self._table_headings = {
            "name": (tr("common.character"), 135),
            "class": (tr("common.class"), 90),
            "spec": (tr("common.spec"), 105),
            "gear": (tr("gear.label"), 105),
            "ench": (tr("enchants.label"), 90),
            "checked": (tr("checker.last_checked"), 105),
        }
        for key, (title, width) in self._table_headings.items():
            self.tree.heading(key, text=title, command=lambda column=key: self._sort_by(column))
            self.tree.column(key, width=width, minwidth=70, stretch=(key in {"name", "spec"}))
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=(6, 0))
        sb = ttk.Scrollbar(self.table_view, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=(6, 0))
        hsb = ttk.Scrollbar(self.table_view, orient="horizontal", command=self.tree.xview)
        hsb.grid(row=1, column=0, sticky="ew", padx=(12, 0), pady=(0, 12))
        self.tree.configure(yscrollcommand=sb.set, xscrollcommand=hsb.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", lambda _e: self.open_armory_selected())

    def _build_graveyard_view(self) -> None:
        self.graveyard_view = tk.Frame(self.center_stack, bg="#11171e")
        self.graveyard_view.grid(row=0, column=0, sticky="nsew")
        self.graveyard_view.grid_rowconfigure(0, weight=1)
        self.graveyard_view.grid_columnconfigure(0, weight=1)
        self.graveyard_canvas = tk.Canvas(self.graveyard_view, bg="#101820", highlightthickness=0)
        gy_scroll = ttk.Scrollbar(self.graveyard_view, orient="vertical", command=self._graveyard_yview)
        self.graveyard_canvas.configure(yscrollcommand=gy_scroll.set)
        self.graveyard_canvas.grid(row=0, column=0, sticky="nsew")
        gy_scroll.grid(row=0, column=1, sticky="ns")
        self.graveyard_canvas.bind("<Configure>", self._schedule_graveyard_render)
        self.graveyard_canvas.bind("<MouseWheel>", self._graveyard_mousewheel)

    def _build_roster_view(self) -> None:
        self.roster_view = tk.Frame(self.center_stack, bg="#0d1117")
        self.roster_view.grid(row=0, column=0, sticky="nsew")
        self.roster_view.grid_rowconfigure(1, weight=1)
        self.roster_view.grid_columnconfigure(0, weight=1)
        controls = tk.Frame(self.roster_view, bg="#131922")
        controls.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._label(controls, tr("roster.zoom"), bg="#131922", muted=True).pack(side="left", padx=(12, 5), pady=7)
        self._button(controls, "−", self._roster_zoom_out).pack(side="left", padx=2, pady=5)
        self.roster_zoom_var = tk.StringVar(value=f"{self.roster_zoom_percent} %")
        self._label(
            controls, textvariable=self.roster_zoom_var, bg="#131922",
            font=("Segoe UI", 10, "bold"), width=7,
        ).pack(side="left", padx=2)
        self._button(controls, "+", self._roster_zoom_in).pack(side="left", padx=2, pady=5)
        self._button(controls, "100 %", lambda: self._set_roster_zoom(100)).pack(side="left", padx=2, pady=5)
        self._button(controls, tr("roster.fit_window"), self._activate_roster_fit).pack(side="left", padx=6, pady=5)
        self.roster_details_button = self._button(
            controls, "", self._toggle_roster_details,
        )
        self.roster_details_button.pack(side="left", padx=6, pady=5)
        self._update_roster_details_button()
        self._button(
            controls, tr("roster.export_png"), self.export_roster_png, kind="primary",
        ).pack(side="right", padx=10, pady=5)
        self.roster_canvas = tk.Canvas(self.roster_view, bg="#0d1117", highlightthickness=0)
        roster_scroll = ttk.Scrollbar(self.roster_view, orient="vertical", command=self.roster_canvas.yview)
        self.roster_canvas.configure(yscrollcommand=roster_scroll.set)
        self.roster_canvas.grid(row=1, column=0, sticky="nsew")
        roster_scroll.grid(row=1, column=1, sticky="ns")
        self.roster_inner = tk.Frame(self.roster_canvas, bg="#0d1117")
        self._roster_window_id = self.roster_canvas.create_window(
            (0, 0), window=self.roster_inner, anchor="nw",
        )
        self.roster_inner.bind(
            "<Configure>",
            lambda _event: self.roster_canvas.configure(scrollregion=self.roster_canvas.bbox("all")),
        )
        self.roster_canvas.bind("<Configure>", self._schedule_roster_render)
        self.roster_canvas.bind("<MouseWheel>", self._roster_mousewheel)

    def _build_raid_view(self) -> None:
        self.raid_view = tk.Frame(self.center_stack, bg=self.PANEL)
        self.raid_view.grid(row=0, column=0, sticky="nsew")
        self.raid_view.grid_rowconfigure(1, weight=1)
        self.raid_view.grid_columnconfigure(0, weight=1)

        controls = tk.Frame(self.raid_view, bg=self.PANEL)
        controls.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        self._button(controls, tr("raids.create"), self.create_raid_dialog, kind="primary").pack(side="left", padx=2)
        self._button(controls, tr("raids.edit"), self.edit_selected_raid).pack(side="left", padx=2)
        self._button(controls, tr("raids.delete"), self.delete_selected_raid, kind="danger").pack(side="left", padx=2)
        self.raid_import_button = self._button(
            controls, tr("raids.import_attendance"), self.import_raid_attendance_csv,
        )
        self.raid_import_button.pack(side="left", padx=2)
        self.raid_reset_button = self._button(
            controls, tr("raids.reset_attendance"), self.reset_selected_raid_attendance,
        )
        self.raid_reset_button.pack(side="left", padx=2)
        self.raid_open_button = self._button(
            controls, tr("raids.open"), self.open_selected_raid,
        )
        self.raid_open_button.pack(side="right", padx=2)

        self.raid_paned = tk.PanedWindow(
            self.raid_view, orient=tk.VERTICAL, bg=self.BORDER, bd=0,
            sashwidth=7, sashrelief="flat", showhandle=False,
        )
        self.raid_paned.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        raid_list_panel = tk.Frame(self.raid_paned, bg=self.PANEL)
        raid_list_panel.grid_rowconfigure(0, weight=1)
        raid_list_panel.grid_columnconfigure(0, weight=1)
        statistic_panel = tk.Frame(self.raid_paned, bg=self.PANEL)
        statistic_panel.grid_rowconfigure(1, weight=1)
        statistic_panel.grid_columnconfigure(0, weight=1)
        self.raid_paned.add(raid_list_panel, minsize=120, stretch="always")
        self.raid_paned.add(statistic_panel, minsize=180, stretch="always")
        self._raid_sash_initialized = False

        raid_columns = ("date", "name", "participants", "status", "logs")
        self.raid_tree = ttk.Treeview(
            raid_list_panel, columns=raid_columns, show="headings", selectmode="browse",
        )
        raid_headings = {
            "date": (tr("common.date"), 95),
            "name": (tr("raids.raid"), 230),
            "participants": (tr("raids.participants"), 85),
            "status": (tr("common.status"), 85),
            "logs": (tr("raids.warcraft_logs"), 105),
        }
        for key, (title, width) in raid_headings.items():
            self.raid_tree.heading(
                key, text=title, command=lambda column=key: self._sort_raids_by(column),
            )
            self.raid_tree.column(key, width=width, minwidth=65, stretch=key == "name")
        self._raid_headings = raid_headings
        self.raid_tree.grid(row=0, column=0, sticky="nsew")
        self.raid_scrollbar = ttk.Scrollbar(
            raid_list_panel, orient="vertical", command=self.raid_tree.yview,
        )
        self.raid_scrollbar.grid(row=0, column=1, sticky="ns")
        self.raid_tree.configure(yscrollcommand=self.raid_scrollbar.set)
        self.raid_tree.bind("<Double-1>", lambda _event: self.open_selected_raid())
        self.raid_tree.bind("<<TreeviewSelect>>", lambda _event: self._update_raid_action_states())

        self._label(
            statistic_panel, tr("raids.statistics"), font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(5, 3))
        statistic_columns = ("player", "attendance", "eligible", "main", "twink")
        self.raid_statistics_tree = ttk.Treeview(
            statistic_panel, columns=statistic_columns, show="headings", selectmode="none",
        )
        statistic_headings = {
            "player": (tr("raids.member"), 190),
            "attendance": (tr("raids.attendance"), 175),
            "eligible": (tr("raids.eligible"), 85),
            "main": (tr("raids.main_count"), 65),
            "twink": (tr("raids.twink_count"), 65),
        }
        for key, (title, width) in statistic_headings.items():
            self.raid_statistics_tree.heading(
                key, text=title,
                command=lambda column=key: self._sort_raid_statistics_by(column),
            )
            self.raid_statistics_tree.column(
                key, width=width, minwidth=55, stretch=key in {"player", "attendance"},
            )
        self._raid_statistics_headings = statistic_headings
        self.raid_statistics_tree.grid(row=1, column=0, sticky="nsew")
        self.raid_statistics_scrollbar = ttk.Scrollbar(
            statistic_panel, orient="vertical", command=self.raid_statistics_tree.yview,
        )
        self.raid_statistics_scrollbar.grid(row=1, column=1, sticky="ns")
        self.raid_statistics_tree.configure(yscrollcommand=self.raid_statistics_scrollbar.set)
        self._update_raid_action_states()

    def _initialize_raid_sash(self) -> None:
        if self._raid_sash_initialized or not hasattr(self, "raid_paned"):
            return
        height = self.raid_paned.winfo_height()
        if height <= 1:
            return
        self.raid_paned.sash_place(0, 0, max(120, int(height * 0.34)))
        self._raid_sash_initialized = True

    def _set_roster_view_mode(self, mode: str) -> None:
        if mode not in {"cards", "list"}:
            return
        self.roster_view_mode = mode
        self._update_tab_styles()
        if self.current_tab == "Roster":
            self.refresh_center(select_first=False)

    def _roster_mousewheel(self, event) -> None:
        self.roster_canvas.yview_scroll(int(-1 * (event.delta / 120)) * 3, "units")

    def _persist_roster_settings(self) -> None:
        update_suite_settings(
            self._suite_settings_path, roster_zoom=self.roster_zoom_percent,
            roster_fit=self.roster_fit_mode,
            roster_details_visible=self.roster_details_visible,
        )

    def _update_roster_details_button(self) -> None:
        if not hasattr(self, "roster_details_button"):
            return
        key = "roster.hide_details" if self.roster_details_visible else "roster.show_details"
        self.roster_details_button.configure(text=tr(key))

    def _detail_panel_should_be_visible(self) -> bool:
        if self.current_tab in {"Friedhof", "Raids"}:
            return False
        if self.current_tab == "Roster":
            return self.roster_details_visible
        return True

    def _sync_detail_panel_visibility(self) -> None:
        if self._detail_panel_should_be_visible():
            self.detail_outer.grid()
        else:
            self.detail_outer.grid_remove()

    def _toggle_roster_details(self) -> None:
        self.roster_details_visible = not self.roster_details_visible
        self._update_roster_details_button()
        self._persist_roster_settings()
        if self.current_tab != "Roster":
            return
        self._sync_detail_panel_visibility()
        self.update_idletasks()
        if self.roster_fit_mode:
            self._recalculate_roster_fit()
        self._schedule_roster_render()

    def _set_roster_zoom(self, value: int, manual: bool = True) -> None:
        self.roster_zoom_percent = clamp_roster_zoom(value)
        if manual:
            self.roster_fit_mode = False
        self.roster_zoom_var.set(f"{self.roster_zoom_percent} %")
        self._persist_roster_settings()
        if self.current_tab == "Roster":
            self.render_roster()

    def _roster_zoom_out(self) -> None:
        self._set_roster_zoom(self.roster_zoom_percent - ROSTER_ZOOM_STEP)

    def _roster_zoom_in(self) -> None:
        self._set_roster_zoom(self.roster_zoom_percent + ROSTER_ZOOM_STEP)

    def _activate_roster_fit(self) -> None:
        self.roster_fit_mode = True
        self._recalculate_roster_fit()
        self._persist_roster_settings()
        if self.current_tab == "Roster":
            self.render_roster()

    def _recalculate_roster_fit(self, available_width: int | None = None) -> None:
        if not self.roster_fit_mode:
            return
        width = int(available_width or self.roster_canvas.winfo_width()) - 60
        active_count = sum(member.lifeStatus == "active" for member in self.model.members)
        self.roster_zoom_percent = fit_roster_zoom(max(1, width), active_count)
        self.roster_zoom_var.set(f"{self.roster_zoom_percent} %")

    def _bind_roster_wheel(self, widget) -> None:
        widget.bind("<MouseWheel>", self._roster_mousewheel)
        for child in widget.winfo_children():
            self._bind_roster_wheel(child)

    def _schedule_roster_render(self, event=None) -> None:
        if event is not None and hasattr(self, "_roster_window_id"):
            self.roster_canvas.itemconfigure(self._roster_window_id, width=max(1, event.width))
        if self.current_tab != "Roster":
            return
        if self.roster_fit_mode:
            self._recalculate_roster_fit(event.width if event is not None else None)
        if self._roster_resize_job:
            try:
                self.after_cancel(self._roster_resize_job)
            except Exception:
                pass
        self._roster_resize_job = self.after(90, self.render_roster)

    def _graveyard_yview(self, *args) -> None:
        self.graveyard_canvas.yview(*args)

    def _graveyard_mousewheel(self, event) -> None:
        delta = -1 if event.delta > 0 else 1
        self.graveyard_canvas.yview_scroll(delta * 3, "units")

    def _schedule_graveyard_render(self, _event=None) -> None:
        if self.current_tab != "Friedhof":
            return
        if self._graveyard_resize_job:
            try:
                self.after_cancel(self._graveyard_resize_job)
            except Exception:
                pass
        self._graveyard_resize_job = self.after(90, self.render_graveyard)

    def _build_detail_panel(self, parent) -> None:
        outer = tk.Frame(parent, bg=self.PANEL, width=330, highlightbackground=self.BORDER, highlightthickness=1)
        outer.grid(row=0, column=2, sticky="nse")
        self.detail_outer = outer
        outer.grid_propagate(False)
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        self.detail_canvas = tk.Canvas(outer, bg=self.PANEL, highlightthickness=0, bd=0)
        self.detail_scrollbar = ttk.Scrollbar(outer, orient="vertical", command=self.detail_canvas.yview)
        self.detail_canvas.configure(yscrollcommand=self.detail_scrollbar.set)
        self.detail_canvas.grid(row=0, column=0, sticky="nsew")
        self.detail_scrollbar.grid(row=0, column=1, sticky="ns")

        detail = tk.Frame(self.detail_canvas, bg=self.PANEL)
        self.detail_inner = detail
        self._detail_window_id = self.detail_canvas.create_window((0, 0), window=detail, anchor="nw")
        detail.bind("<Configure>", self._detail_configure)
        self.detail_canvas.bind("<Configure>", self._detail_canvas_configure)
        self.detail_canvas.bind("<Enter>", lambda _e: self._bind_detail_wheel())
        self.detail_canvas.bind("<Leave>", lambda _e: self._unbind_detail_wheel())
        detail.bind("<Enter>", lambda _e: self._bind_detail_wheel())
        detail.bind("<Leave>", lambda _e: self._unbind_detail_wheel())

        self._label(detail, tr("checker.member_details"), font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        self._label(detail, tr("checker.detail_scroll"), muted=True).pack(anchor="w", padx=16, pady=(0, 8))

        self.portrait_frame = tk.Frame(detail, bg="#0c1015", width=RIGHT_PORTRAIT_SIZE, height=RIGHT_PORTRAIT_SIZE, highlightthickness=1, highlightbackground="#27313c")
        self.portrait_frame.pack(padx=16, pady=(0, 10))
        self.portrait_frame.pack_propagate(False)
        self.portrait_label = tk.Label(
            self.portrait_frame,
            text=tr("checker.missing_portrait").replace(" ", "\n"),
            bg="#0c1015",
            fg=self.MUTED,
            font=("Segoe UI", 11),
            anchor="center",
            justify="center",
        )
        self.portrait_label.pack(fill="both", expand=True)

        self.detail_name_var = tk.StringVar(value="–")
        self._label(detail, textvariable=self.detail_name_var, font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=16)
        self.detail_meta_var = tk.StringVar(value=tr("checker.choose_character"))
        self._label(detail, textvariable=self.detail_meta_var, muted=True, wraplength=285, justify="left").pack(anchor="w", padx=16, pady=(0, 10))
        self.detail_death_var = tk.StringVar(value="")
        self.detail_death_label = self._label(detail, textvariable=self.detail_death_var, muted=True)
        self.detail_death_label.pack(anchor="w", padx=16, pady=(0, 4))

        self.race_var = tk.StringVar(value=tr("common.not_set"))
        self.class_var = tk.StringVar(value=tr("common.not_set"))
        self.spec_var = tk.StringVar(value=tr("common.not_set"))
        self.gear_var = tk.StringVar(value=gear_status_display(GEAR_VALUES[0]))
        self.enchant_var = tk.StringVar(value=enchant_status_display(ENCHANT_VALUES[0]))
        self.player_var = tk.StringVar(value=tr("common.unassigned"))
        self.associated_main_var = tk.StringVar(value=tr("checker.no_active_main"))
        self._main_choice_ids: dict[str, str] = {}
        self.character_type_var = tk.StringVar(value=character_type_display("not_set"))
        self.raid_role_var = tk.StringVar(value=raid_role_display("not_set"))

        self.race_combo = ttk.Combobox(
            detail, textvariable=self.race_var,
            values=[tr("common.not_set"), *race_display_values()], state="readonly",
        )
        class_row = tk.Frame(detail, bg=self.PANEL)
        self.class_icon_label = tk.Label(class_row, bg="#0c1015", fg=self.MUTED, width=4, height=2, text="–")
        self.class_combo = ttk.Combobox(class_row, textvariable=self.class_var, values=[tr("common.not_set")] + CLASS_NAMES, state="readonly")
        self.class_combo.bind("<<ComboboxSelected>>", self._on_class_changed)
        self.spec_combo = ttk.Combobox(detail, textvariable=self.spec_var, values=[tr("common.not_set")], state="readonly")

        self._label(
            detail, tr("checker.detail_overview"), font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=16, pady=(4, 6))

        # Kept as hidden compatibility widgets for legacy Player administration.
        self.player_combo = ttk.Combobox(detail, textvariable=self.player_var, state="readonly")
        player_actions = tk.Frame(detail, bg=self.PANEL)
        self._button(player_actions, tr("checker.create_player"), self.create_player_dialog).pack(side="left", fill="x", expand=True, padx=(0, 2))
        self._button(player_actions, tr("checker.rename_player"), self.rename_player_dialog).pack(side="left", fill="x", expand=True, padx=(2, 0))

        self._field_label(detail, tr("character_type.label"))
        self.character_type_combo = ttk.Combobox(
            detail, textvariable=self.character_type_var,
            values=[character_type_display(value) for value in CHARACTER_TYPES], state="readonly",
        )
        self.character_type_combo.pack(fill="x", padx=16, pady=(0, 8))
        self.character_type_combo.bind("<<ComboboxSelected>>", self._character_type_changed)
        self._field_label(detail, tr("checker.associated_main"))
        self.associated_main_combo = ttk.Combobox(
            detail, textvariable=self.associated_main_var, state="readonly",
        )
        self.associated_main_combo.pack(fill="x", padx=16, pady=(0, 8))
        self._field_label(detail, tr("raid_role.label"))
        self.raid_role_combo = ttk.Combobox(
            detail, textvariable=self.raid_role_var,
            values=[raid_role_display(value) for value in RAID_ROLES], state="readonly",
        )
        self.raid_role_combo.pack(fill="x", padx=16, pady=(0, 8))

        self._label(
            detail, tr("checker.detail_gear"), font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=16, pady=(8, 4))
        self._field_label(detail, tr("gear.label"))
        self.gear_combo = ttk.Combobox(detail, textvariable=self.gear_var,
                                       values=[gear_status_display(v) for v in GEAR_VALUES], state="readonly")
        self.gear_combo.pack(fill="x", padx=16, pady=(0, 8))
        self._field_label(detail, tr("enchants.label"))
        self.enchant_combo = ttk.Combobox(detail, textvariable=self.enchant_var,
                                          values=[enchant_status_display(v) for v in ENCHANT_VALUES], state="readonly")
        self.enchant_combo.pack(fill="x", padx=16, pady=(0, 8))

        self._label(
            detail, tr("checker.detail_note"), font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=16, pady=(8, 4))
        self._field_label(detail, tr("checker.note"))
        self.note_text = tk.Text(detail, height=5, bg=self.PANEL_2, fg=self.TEXT, insertbackground=self.TEXT, relief="flat", wrap="word", font=("Segoe UI", 10))
        self.note_text.pack(fill="x", padx=16, pady=(0, 10))

        self.detail_checked_var = tk.StringVar(value=f"{tr('checker.last_checked')}: –")
        self._label(detail, textvariable=self.detail_checked_var, muted=True).pack(anchor="w", padx=16)
        self.recheck_gear_button = self._button(
            detail, tr("checker.confirm_gear_recheck"), self.confirm_gear_recheck_selected,
        )
        self.recheck_gear_button.configure(state="disabled")
        self.recheck_gear_button.pack(fill="x", padx=16, pady=(10, 3))
        self._button(detail, tr("checker.apply_changes"), self.save_selected_member, kind="primary").pack(fill="x", padx=16, pady=(5, 5))
        self._button(detail, tr("checker.open_armory"), self.open_armory_selected).pack(fill="x", padx=16, pady=3)
        self._button(detail, tr("checker.remove_member"), self.remove_selected_member, kind="danger").pack(fill="x", padx=16, pady=3)
        self.activity_button = self._button(
            detail, tr("checker.mark_inactive"), self.toggle_activity_selected,
        )
        self.activity_button.pack(fill="x", padx=16, pady=3)
        self.life_button = self._button(detail, tr("checker.mark_dead"), self.toggle_life_selected, kind="danger")
        self.life_button.pack(fill="x", padx=16, pady=(3, 18))

    def _detail_configure(self, _event=None) -> None:
        self.detail_canvas.configure(scrollregion=self.detail_canvas.bbox("all"))

    def _detail_canvas_configure(self, event) -> None:
        if self._detail_window_id is not None:
            self.detail_canvas.itemconfigure(self._detail_window_id, width=max(1, event.width))

    def _bind_detail_wheel(self) -> None:
        self.bind_all("<MouseWheel>", self._detail_mousewheel)

    def _unbind_detail_wheel(self) -> None:
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass

    def _detail_mousewheel(self, event) -> None:
        self.detail_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _field_label(self, parent, text) -> None:
        self._label(parent, text, muted=True).pack(anchor="w", padx=16, pady=(4, 2))

    def _entry(self, parent, variable):
        e = tk.Entry(parent, textvariable=variable, bg=self.PANEL_2, fg=self.TEXT, insertbackground=self.TEXT, relief="flat", font=("Segoe UI", 10))
        e.pack(fill="x", padx=16, pady=(0, 8), ipady=6)
        return e

    def _language_changed(self, _event=None) -> None:
        language = language_from_display(self.language_var.get())
        if language == get_language():
            return
        set_language(language)
        messagebox.showinfo(tr("language.restart_title"), tr("language.restart_message"), parent=self)

    def _member_last_checked_value(self, member: Member) -> str:
        value = member.lastChecked or "–"
        if member_check_is_outdated(
                member, self.gear_outdated_tracking, self.gear_outdated_days):
            return f"{value} · {tr('checker.check_outdated')}"
        return value

    def _member_last_checked_display(self, member: Member) -> str:
        return f"{tr('checker.last_checked')}: {self._member_last_checked_value(member)}"

    def open_settings_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(tr("common.settings"))
        dialog.geometry("500x290")
        dialog.minsize(430, 250)
        dialog.transient(self)
        dialog.grab_set()

        outer = tk.Frame(dialog, bg=self.BG)
        outer.pack(fill="both", expand=True, padx=14, pady=14)
        panel = tk.Frame(outer, bg=self.PANEL, highlightbackground=self.BORDER, highlightthickness=1)
        panel.pack(fill="both", expand=True)
        self._label(panel, tr("checker.gear_check_settings"), font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=16, pady=(16, 5),
        )
        self._label(panel, tr("checker.gear_check_settings_help"), muted=True, wraplength=440,
                    justify="left").pack(anchor="w", padx=16, pady=(0, 12))

        enabled_var = tk.BooleanVar(value=self.gear_outdated_tracking)
        days_var = tk.StringVar(value=str(self.gear_outdated_days))
        enabled = ttk.Checkbutton(
            panel, text=tr("checker.track_outdated_checks"), variable=enabled_var,
        )
        enabled.pack(anchor="w", padx=16, pady=5)
        row = tk.Frame(panel, bg=self.PANEL)
        row.pack(fill="x", padx=16, pady=5)
        self._label(row, tr("checker.warn_after_days")).pack(side="left")
        days_spin = ttk.Spinbox(row, from_=1, to=3650, textvariable=days_var, width=8)
        days_spin.pack(side="left", padx=(10, 5))
        self._label(row, tr("checker.days"), muted=True).pack(side="left")

        def update_state(*_args) -> None:
            days_spin.configure(state="normal" if enabled_var.get() else "disabled")

        enabled_var.trace_add("write", update_state)
        update_state()

        buttons = tk.Frame(panel, bg=self.PANEL)
        buttons.pack(fill="x", padx=16, pady=(14, 16))

        def save_settings() -> None:
            raw = days_var.get().strip()
            try:
                parsed = int(raw)
            except ValueError:
                parsed = 0
            if not 1 <= parsed <= 3650:
                messagebox.showwarning(
                    tr("common.settings"), tr("checker.invalid_outdated_days"), parent=dialog,
                )
                return
            self.gear_outdated_tracking = bool(enabled_var.get())
            self.gear_outdated_days = parsed
            self._suite_settings["gear_outdated_tracking"] = self.gear_outdated_tracking
            self._suite_settings["gear_outdated_days"] = self.gear_outdated_days
            update_suite_settings(
                self._suite_settings_path,
                gear_outdated_tracking=self.gear_outdated_tracking,
                gear_outdated_days=self.gear_outdated_days,
            )
            self.refresh_all(select_first=False)
            if self.selected_member_id:
                self.show_member(self.selected_member_id)
            self.status_var.set(tr("checker.settings_saved"))
            dialog.destroy()

        self._button(buttons, tr("common.save"), save_settings, kind="primary").pack(side="right")
        self._button(buttons, tr("common.cancel"), dialog.destroy).pack(side="right", padx=(0, 8))

    def confirm_gear_recheck_selected(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if member is None:
            messagebox.showinfo(APP_NAME, tr("checker.select_character"), parent=self)
            return
        if member.lifeStatus != "active":
            messagebox.showwarning(APP_NAME, tr("checker.recheck_active_only"), parent=self)
            return
        member.lastChecked = today_iso()
        self.model.dirty = True
        self.autosave()
        self.refresh_all(select_first=False)
        self.show_member(member.id)
        self.status_var.set(tr("checker.gear_rechecked", name=member.name, date=member.lastChecked))

    def _guild_snapshot_path(self) -> Path:
        return app_base_dir() / "data" / "runtime" / GUILD_ROSTER_SNAPSHOT_FILE

    def _guild_sync_category_text(self, category: str) -> str:
        return tr(f"guild_sync.category_{category}")

    def _guild_sync_action_text(self, action: str) -> str:
        return tr(f"guild_sync.action_{action}")

    @staticmethod
    def _guild_sync_allowed_actions(category: str) -> tuple[str, ...]:
        return {
            "new": ("add", "keep"),
            "new_incarnation": ("add", "keep"),
            "known": ("keep",),
            "inactive_found": ("keep", "reactivate"),
            "missing_active": ("keep", "inactive", "dead", "delete"),
            "conflict": ("keep",),
        }.get(category, ("keep",))

    @staticmethod
    def _guild_sync_default_action(category: str) -> str:
        return "add" if category in {"new", "new_incarnation"} else "keep"

    @staticmethod
    def _guild_sync_member_dict(member: Member) -> dict:
        return member.to_dict()

    def open_guild_roster_review(self) -> None:
        path = self._guild_snapshot_path()
        if not path.is_file():
            messagebox.showinfo(
                tr("guild_sync.title"), tr("guild_sync.snapshot_missing", path=path), parent=self,
            )
            return
        try:
            snapshot = load_snapshot(
                path, expected_region=self.model.region, expected_realm=self.model.realm,
                expected_game_version=self.model.game_version,
            )
            items = compare_snapshot(
                [self._guild_sync_member_dict(member) for member in self.model.members], snapshot,
            )
        except Exception as exc:
            messagebox.showerror(
                tr("guild_sync.title"), tr("guild_sync.snapshot_error", error=exc), parent=self,
            )
            return

        dialog = tk.Toplevel(self)
        dialog.title(tr("guild_sync.title"))
        dialog.geometry("1050x650")
        dialog.minsize(820, 520)
        dialog.transient(self)
        dialog.grab_set()

        top = tk.Frame(dialog, bg=self.BG)
        top.pack(fill="both", expand=True, padx=12, pady=12)
        heading = tr(
            "guild_sync.snapshot_summary", guild=snapshot.get("guild") or "–",
            count=len(snapshot.get("members", [])), fetched=snapshot.get("fetchedAt") or "–",
        )
        self._label(top, heading, font=("Segoe UI", 11, "bold"), wraplength=980,
                    justify="left", bg=self.BG).pack(anchor="w", pady=(0, 5))
        self._label(top, tr("guild_sync.review_help"), muted=True, wraplength=980,
                    justify="left", bg=self.BG).pack(anchor="w", pady=(0, 8))

        table_frame = tk.Frame(top, bg=self.BG)
        table_frame.pack(fill="both", expand=True)
        columns = ("name", "category", "race", "class", "action")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "name": (tr("common.character"), 180),
            "category": (tr("guild_sync.status"), 210),
            "race": (tr("checker.race"), 170),
            "class": (tr("common.class"), 170),
            "action": (tr("guild_sync.action"), 190),
        }
        for key, (title, width) in headings.items():
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=90, stretch=key in {"name", "category"})
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=yscroll.set)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        item_by_iid: dict[str, RosterComparisonItem] = {}
        actions: dict[str, str] = {}

        def metadata_text(current: str | None, incoming: str | None) -> str:
            if incoming and current and incoming != current:
                return f"{current} → {incoming}"
            return incoming or current or "–"

        for index, item in enumerate(items):
            iid = f"sync{index:04d}"
            item_by_iid[iid] = item
            action = self._guild_sync_default_action(item.category)
            actions[item.key] = action
            tree.insert("", "end", iid=iid, values=(
                item.name, self._guild_sync_category_text(item.category),
                metadata_text(item.current_race, item.incoming_race),
                metadata_text(item.current_class, item.incoming_class),
                self._guild_sync_action_text(action),
            ))

        controls = tk.Frame(top, bg=self.BG)
        controls.pack(fill="x", pady=(10, 0))
        self._label(controls, tr("guild_sync.action_for_selection"), bg=self.BG).pack(side="left")
        action_var = tk.StringVar(value="")
        action_combo = ttk.Combobox(controls, textvariable=action_var, state="readonly", width=28)
        action_combo.pack(side="left", padx=(8, 12))
        action_lookup: dict[str, str] = {}

        def selection_changed(_event=None) -> None:
            nonlocal action_lookup
            selection = tree.selection()
            if not selection:
                action_combo.configure(values=())
                action_var.set("")
                return
            item = item_by_iid[selection[0]]
            allowed = self._guild_sync_allowed_actions(item.category)
            action_lookup = {self._guild_sync_action_text(action): action for action in allowed}
            action_combo.configure(values=list(action_lookup))
            action_var.set(self._guild_sync_action_text(actions[item.key]))

        def action_changed(_event=None) -> None:
            selection = tree.selection()
            if not selection:
                return
            item = item_by_iid[selection[0]]
            action = action_lookup.get(action_var.get())
            if not action:
                return
            actions[item.key] = action
            values = list(tree.item(selection[0], "values"))
            values[4] = self._guild_sync_action_text(action)
            tree.item(selection[0], values=values)

        tree.bind("<<TreeviewSelect>>", selection_changed)
        action_combo.bind("<<ComboboxSelected>>", action_changed)
        first = tree.get_children()
        if first:
            tree.selection_set(first[0])
            selection_changed()

        self._button(
            controls, tr("guild_sync.apply"),
            lambda: self._apply_guild_roster_review(dialog, snapshot, items, actions),
            kind="primary",
        ).pack(side="right")
        self._button(controls, tr("common.cancel"), dialog.destroy).pack(side="right", padx=(0, 8))

    def _validate_guild_roster_review_actions(
            self, items: list[RosterComparisonItem], selected_actions: dict[str, str]) -> None:
        action_by_member = {
            item.member_id: selected_actions.get(item.key, "keep")
            for item in items if item.member_id
        }
        removing_actions = {"inactive", "dead", "delete"}
        for item in items:
            action = selected_actions.get(item.key, "keep")
            if action not in GuildGearCheckerApp._guild_sync_allowed_actions(item.category):
                raise ValueError(tr("guild_sync.apply_invalid", name=item.name))
            member = self.model.find_by_id(item.member_id or "") if item.member_id else None
            if action == "keep":
                continue
            if action == "add":
                if item.category not in {"new", "new_incarnation"}:
                    raise ValueError(tr("guild_sync.apply_invalid", name=item.name))
                if self.model.find_current_by_name(item.name) is not None:
                    raise ValueError(tr("guild_sync.apply_invalid", name=item.name))
                continue
            if action == "reactivate":
                if member is None or member.lifeStatus != "inactive":
                    raise ValueError(tr("guild_sync.apply_invalid", name=item.name))
                for same_name in self.model.find_all_by_name(member.name):
                    if same_name.id == member.id or same_name.lifeStatus not in {"active", "inactive"}:
                        continue
                    if action_by_member.get(same_name.id, "keep") not in removing_actions:
                        raise ValueError(tr("guild_sync.apply_invalid", name=item.name))
                if member.characterType == "main" and member.playerId:
                    existing_main = self.model.active_main_for_player(
                        member.playerId, exclude_member_id=member.id,
                    )
                    if (existing_main is not None
                            and action_by_member.get(existing_main.id, "keep") not in removing_actions):
                        raise ValueError(tr("guild_sync.apply_invalid", name=item.name))
                continue
            if action in removing_actions:
                if member is None or member.lifeStatus != "active":
                    raise ValueError(tr("guild_sync.apply_invalid", name=item.name))
                continue
            raise ValueError(tr("guild_sync.apply_invalid", name=item.name))

    def _apply_guild_roster_review(self, dialog, snapshot: dict,
                                   items: list[RosterComparisonItem],
                                   actions: dict[str, str]) -> None:
        selected_actions = {item.key: actions.get(item.key, "keep") for item in items}
        change_count = sum(action != "keep" for action in selected_actions.values())
        if not messagebox.askyesno(
                tr("guild_sync.title"),
                tr("guild_sync.apply_question", count=change_count), parent=dialog):
            return

        try:
            GuildGearCheckerApp._validate_guild_roster_review_actions(
                self, items, selected_actions,
            )
        except Exception as exc:
            messagebox.showerror(tr("guild_sync.title"), str(exc), parent=dialog)
            return

        metadata_overrides: set[tuple[str, str]] = set()
        for item in items:
            if item.category not in {"known", "inactive_found"}:
                continue
            for field, current, incoming in (
                ("race", item.current_race, item.incoming_race),
                ("className", item.current_class, item.incoming_class),
            ):
                if incoming and current and incoming != current:
                    label = tr("checker.race") if field == "race" else tr("common.class")
                    if messagebox.askyesno(
                            tr("guild_sync.metadata_conflict_title"),
                            tr("guild_sync.metadata_conflict", name=item.name, field=label,
                               current=current, incoming=incoming), parent=dialog):
                        metadata_overrides.add((item.key, field))

        death_members = [
            self.model.find_by_id(item.member_id or "")
            for item in items if selected_actions[item.key] == "dead"
        ]
        try:
            for member in death_members:
                if member is not None:
                    self._archive_portrait(member)
        except Exception as exc:
            messagebox.showerror(
                tr("guild_sync.title"), tr("checker.portrait_archive_error", error=exc),
                parent=dialog,
            )
            return

        state = (
            copy.deepcopy(self.model.members), copy.deepcopy(self.model.players),
            self.model.next_id, self.model.next_player_id, self.model.dirty,
        )
        affected = 0
        targets: dict[str, Member | None] = {
            item.key: self.model.find_by_id(item.member_id or "") if item.member_id else None
            for item in items
        }
        try:
            # First remove active-state conflicts. This makes a deliberate Main swap
            # possible in one reviewed transaction without silently demoting anybody.
            for item in items:
                action = selected_actions[item.key]
                member = targets[item.key]
                if action == "inactive":
                    self.model.set_member_life_status(member.id, "inactive")
                    affected += 1
                elif action == "dead":
                    self.model.set_member_life_status(member.id, "dead")
                    member.deathDate = today_iso()
                    affected += 1
                elif action == "delete":
                    self.model.remove_member(member.id)
                    targets[item.key] = None
                    affected += 1

            # Then create/reactivate characters after all reviewed removals are in place.
            for item in items:
                action = selected_actions[item.key]
                if action == "add":
                    targets[item.key] = self.model.add_member(item.name, "Guild Roster Sync")
                    affected += 1
                elif action == "reactivate":
                    member = targets[item.key]
                    self.model.set_member_life_status(member.id, "active")
                    affected += 1
                elif action not in {"keep", "inactive", "dead", "delete"}:
                    raise ValueError(tr("guild_sync.apply_invalid", name=item.name))

            for item in items:
                target = targets[item.key]
                if target is None or target.lifeStatus == "dead":
                    continue
                for field, incoming in (("race", item.incoming_race), ("className", item.incoming_class)):
                    if not incoming:
                        continue
                    current = getattr(target, field)
                    should_apply = not current or (item.key, field) in metadata_overrides
                    if not should_apply or current == incoming:
                        continue
                    if field == "race":
                        value = normalize_race(incoming)
                    else:
                        value = normalize_class_name(incoming)
                    if not value:
                        continue
                    setattr(target, field, value)
                    if field == "className":
                        target.spec = normalize_spec(value, target.spec)
                        target.classSpec = combine_class_spec(value, target.spec)
                    self.model.dirty = True
            if self.model.dirty:
                self.autosave()
            self.current_tab = "Gildenliste"
            self._sync_detail_panel_visibility()
            self._update_tab_styles()
            self.refresh_all(select_first=True)
            dialog.destroy()
            self.status_var.set(tr("guild_sync.applied", count=affected))
        except Exception as exc:
            (self.model.members, self.model.players, self.model.next_id,
             self.model.next_player_id, self.model.dirty) = state
            messagebox.showerror(
                tr("guild_sync.title"), tr("guild_sync.apply_failed", error=exc), parent=dialog,
            )

    def _player_display(self, player: Player) -> str:
        return f"{player.playerName} [{player.playerId}]"

    def _refresh_player_values(self, selected_id: str | None = None) -> None:
        values = [tr("common.unassigned")] + [
            self._player_display(player)
            for player in sorted(self.model.players, key=lambda value: value.playerName.casefold())
        ]
        self.player_combo.configure(values=values)
        player = self.model.find_player_by_id(selected_id)
        self.player_var.set(self._player_display(player) if player else tr("common.unassigned"))

    def _selected_player_id(self) -> str | None:
        match = re.search(r"\[([^\[\]]+)\]\s*$", self.player_var.get())
        player_id = match.group(1) if match else None
        return player_id if self.model.find_player_by_id(player_id) else None

    def _refresh_main_values(self, member: Member | None = None) -> None:
        mains = sorted((
            value for value in self.model.members
            if value.lifeStatus == "active" and value.characterType == "main"
            and (member is None or value.id != member.id)
        ), key=lambda value: (value.name.casefold(), value.id))
        self._main_choice_ids = {value.name: value.id for value in mains}
        values = [tr("checker.no_active_main"), *self._main_choice_ids]
        self.associated_main_combo.configure(values=values)
        selected = self.model.associated_main(member) if member else None
        self.associated_main_var.set(selected.name if selected else tr("checker.no_active_main"))

    def _selected_main_id(self) -> str | None:
        return self._main_choice_ids.get(self.associated_main_var.get())

    def _character_type_changed(self, _event=None) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        self._refresh_main_values(member)

    def create_player_dialog(self) -> None:
        player_name = simpledialog.askstring(
            tr("checker.create_player"), tr("checker.player_name"), parent=self,
        )
        if player_name is None:
            return
        try:
            player = self.model.add_player(player_name)
            self._refresh_player_values(player.playerId)
            self.autosave()
            self.refresh_center()
        except ValueError as exc:
            messagebox.showwarning(APP_NAME, str(exc), parent=self)

    def rename_player_dialog(self) -> None:
        player = self.model.find_player_by_id(self._selected_player_id())
        if player is None:
            messagebox.showinfo(APP_NAME, tr("checker.select_player"), parent=self)
            return
        player_name = simpledialog.askstring(
            tr("checker.rename_player"), tr("checker.player_name"),
            initialvalue=player.playerName, parent=self,
        )
        if player_name is None:
            return
        try:
            self.model.rename_player(player.playerId, player_name)
            self._refresh_player_values(player.playerId)
            self.autosave()
            self.refresh_center()
        except ValueError as exc:
            messagebox.showwarning(APP_NAME, str(exc), parent=self)

    # ---------- Laden / Autosave ----------
    def _load_autosave_or_seed(self) -> None:
        # Global vorhandene Autosaves und Seed-Daten bleiben unangetastet, werden
        # beim Programmstart aber bewusst nicht mehr als Projektquelle verwendet.
        self.model.new_empty()
        self._refresh_project_label()

    def autosave(self) -> None:
        if not self.model.project_path or not self.model.dirty:
            return
        try:
            target = project_paths(self.model.project_path).autosave
            atomic_write_bytes(
                target,
                json.dumps(self.model.to_payload(), ensure_ascii=False, indent=2).encode("utf-8"),
            )
        except Exception as exc:
            self.status_var.set(tr("checker.autosave_failed", error=exc))

    # ---------- Tabs / Filter ----------
    def switch_tab(self, tab_name: str) -> None:
        if tab_name not in TAB_ORDER:
            return
        self.current_tab = tab_name
        self._update_sidebar_mode()
        self._sync_detail_panel_visibility()
        self._update_tab_styles()
        self.refresh_center(select_first=True)

    def _update_sidebar_mode(self) -> None:
        if not hasattr(self, "sidebar_member_panel"):
            return
        self.sidebar_member_panel.pack_forget()
        self.sidebar_raid_panel.pack_forget()
        panel = self.sidebar_raid_panel if self.current_tab == "Raids" else self.sidebar_member_panel
        panel.pack(fill="both", expand=True)

    def _update_tab_styles(self) -> None:
        member_tabs = {"Gildenliste", "Handlungsbedarf", "Ungeprüft", "Inaktiv", "Alle Charaktere"}
        primary_key = (
            "Member" if self.current_tab in member_tabs else
            "Roster" if self.current_tab == "Roster" else
            "Friedhof" if self.current_tab == "Friedhof" else
            "Raids" if self.current_tab == "Raids" else None
        )
        for name, btn in getattr(self, "primary_nav_buttons", {}).items():
            active = name == primary_key
            btn.configure(
                bg=self.TAB_ACTIVE if active else self.PANEL_2,
                activebackground=self.TAB_ACTIVE if active else "#344153",
            )
        for name, btn in self.tab_buttons.items():
            active = name == self.current_tab
            btn.configure(
                bg=self.TAB_ACTIVE if active else self.PANEL_2,
                activebackground=self.TAB_ACTIVE if active else "#344153",
            )
        if hasattr(self, "member_subnav"):
            if self.current_tab in member_tabs:
                self.member_subnav.grid()
            else:
                self.member_subnav.grid_remove()
        if hasattr(self, "roster_mode_controls"):
            if self.current_tab == "Roster":
                self.roster_mode_controls.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))
            else:
                self.roster_mode_controls.grid_remove()
        for mode, btn in getattr(self, "roster_mode_buttons", {}).items():
            active = mode == self.roster_view_mode
            btn.configure(
                bg=self.TAB_ACTIVE if active else self.PANEL_2,
                activebackground=self.TAB_ACTIVE if active else "#344153",
            )

    def _update_tab_labels(self) -> None:
        counts = {
            "Gildenliste": sum(member_matches_tab(m, "Gildenliste") for m in self.model.members),
            "Handlungsbedarf": sum(
                member_matches_tab(
                    m, "Handlungsbedarf", self.gear_outdated_tracking, self.gear_outdated_days,
                )
                for m in self.model.members
            ),
            "Ungeprüft": sum(member_matches_tab(m, "Ungeprüft") for m in self.model.members),
            "Inaktiv": sum(member_matches_tab(m, "Inaktiv") for m in self.model.members),
            "Friedhof": sum(member_matches_tab(m, "Friedhof") for m in self.model.members),
            "Alle Charaktere": len(self.model.members),
            "Roster": sum(member_matches_tab(m, "Roster") for m in self.model.members),
            "Raids": len(self.model.raids),
        }
        for name, btn in self.tab_buttons.items():
            btn.configure(text=f"{tr(TAB_TRANSLATION_KEYS[name])} ({counts[name]})")
        primary = getattr(self, "primary_nav_buttons", {})
        if "Member" in primary:
            primary["Member"].configure(text=f"{tr('tabs.member')} ({len(self.model.members)})")
        if "Roster" in primary:
            primary["Roster"].configure(text=f"{tr('tabs.roster')} ({counts['Roster']})")
        if "Friedhof" in primary:
            primary["Friedhof"].configure(text=f"{tr('tabs.graveyard')} ({counts['Friedhof']})")
        if "Raids" in primary:
            primary["Raids"].configure(text=f"{tr('tabs.raids')} ({counts['Raids']})")

    def reset_filters(self) -> None:
        self.search_var.set("")
        self.gear_filter.set(tr("common.all"))
        self.enchant_filter.set(tr("common.all"))
        self.refresh_center(select_first=True)

    def _sort_by(self, column: str) -> None:
        current_column, current_descending = self.sort_state.get(
            self.current_tab, default_sort_for_tab(self.current_tab),
        )
        descending = not current_descending if current_column == column else False
        self.sort_state[self.current_tab] = (column, descending)
        self._update_sort_headings()
        self.refresh_center()

    def _update_sort_headings(self) -> None:
        column, descending = self.sort_state.get(
            self.current_tab, default_sort_for_tab(self.current_tab),
        )
        for key, (title, _width) in self._table_headings.items():
            marker = (" ▼" if descending else " ▲") if key == column else ""
            self.tree.heading(key, text=title + marker)

    def filtered_members(self, tab_name: str | None = None) -> list[Member]:
        tab_name = tab_name or self.current_tab
        gear_filter = None if self.gear_filter.get() == tr("common.all") else gear_status_key(gear_status_from_display(self.gear_filter.get()))
        enchant_filter = None if self.enchant_filter.get() == tr("common.all") else enchant_status_key(enchant_status_from_display(self.enchant_filter.get()))
        sort_column, descending = self.sort_state.get(tab_name, default_sort_for_tab(tab_name))
        return filter_and_sort_members(
            self.model.members, tab_name, self.search_var.get(), gear_filter,
            enchant_filter, sort_column, descending,
            outdated_tracking=self.gear_outdated_tracking,
            outdated_days=self.gear_outdated_days,
        )

    def refresh_all(self, select_first=False) -> None:
        selected = self.model.find_by_id(self.selected_member_id or "")
        self._refresh_player_values(selected.playerId if selected else None)
        self._refresh_main_values(selected)
        self.refresh_stats()
        self._update_tab_labels()
        self.refresh_center(select_first=select_first)
        self._refresh_project_label()

    def refresh_stats(self) -> None:
        active = sum(m.lifeStatus == "active" for m in self.model.members)
        inactive = sum(m.lifeStatus == "inactive" for m in self.model.members)
        dead = sum(m.lifeStatus == "dead" for m in self.model.members)
        needs = sum(
            member_matches_tab(
                m, "Handlungsbedarf", self.gear_outdated_tracking, self.gear_outdated_days,
            )
            for m in self.model.members
        )
        unchecked = sum(member_matches_tab(m, "Ungeprüft") for m in self.model.members)
        self.stat_active.set(str(active))
        self.stat_inactive.set(str(inactive))
        self.stat_dead.set(str(dead))
        self.stat_needs.set(str(needs))
        self.stat_unchecked.set(str(unchecked))
        if hasattr(self, "raid_stat_total"):
            recorded = sum(raid.status == "recorded" for raid in self.model.raids)
            self.raid_stat_total.set(str(len(self.model.raids)))
            self.raid_stat_recorded.set(str(recorded))
            self.raid_stat_open.set(str(len(self.model.raids) - recorded))

    def refresh_center(self, select_first=False) -> None:
        if self.current_tab == "Raids":
            self.visible_count_var.set(tr("raids.raid_count", count=len(self.model.raids)))
            self.raid_view.tkraise()
            if not self._raid_sash_initialized:
                self.raid_view.update_idletasks()
                self._initialize_raid_sash()
            self.refresh_raids(select_first=select_first)
            return
        visible = self.filtered_members()
        self.visible_count_var.set(f"{len(visible)} von {len(self.model.members)}")
        if self.current_tab == "Roster":
            if self.roster_view_mode == "list":
                self.table_view.tkraise()
                self._update_sort_headings()
                self.refresh_table(visible, select_first=select_first)
            else:
                self.roster_view.tkraise()
                self.render_roster()
            if self.selected_member_id not in {member.id for member in visible}:
                if visible and select_first:
                    self.show_member(visible[0].id)
                elif not visible:
                    self.selected_member_id = None
                    self.clear_detail()
        elif self.current_tab == "Friedhof":
            self.graveyard_view.tkraise()
            # A previously covered stacked frame receives its final size only after
            # it has been raised and the optional detail column has been removed.
            # Resolve that geometry before the first synchronous background render;
            # later Configure events continue to use the existing debounce path.
            self.update_idletasks()
            self.render_graveyard()
            if self.selected_member_id not in {m.id for m in visible}:
                if visible and select_first:
                    self.show_member(visible[0].id)
                elif not visible:
                    self.selected_member_id = None
                    self.clear_detail()
        else:
            self.table_view.tkraise()
            self._update_sort_headings()
            self.refresh_table(visible, select_first=select_first)

    def refresh_table(self, visible: list[Member] | None = None, select_first=False) -> None:
        old_selection = self.selected_member_id
        for item in self.tree.get_children():
            self.tree.delete(item)
        if visible is None:
            visible = self.filtered_members()
        for m in visible:
            icon = self._class_icon_small_refs.get(m.className) if m.className else None
            self.tree.insert("", "end", iid=m.id, image=icon or "", values=(
                m.name, m.className or "–", m.spec or "–", gear_status_display(m.gearStatus),
                enchant_status_display(m.enchants), self._member_last_checked_value(m),
            ))
        target = None
        if old_selection and self.tree.exists(old_selection):
            target = old_selection
        elif select_first and visible:
            target = visible[0].id
        elif self.selected_member_id and self.tree.exists(self.selected_member_id):
            target = self.selected_member_id
        if target:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
            self.show_member(target)
        elif not visible:
            self.selected_member_id = None
            self.clear_detail()

    @staticmethod
    def _image_signature(path: Path | None):
        if path is None:
            return None
        try:
            stat = path.stat()
            return (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        except OSError:
            return (str(path), 0, 0)

    @staticmethod
    def _trim_image_cache(cache: dict, limit: int) -> None:
        while len(cache) > limit:
            cache.pop(next(iter(cache)))

    def _cached_gravestone_template(self, template, size: tuple[int, int]):
        key = (template.grave_template_id, template.sha256, size)
        image = self._graveyard_template_cache.get(key)
        if image is None:
            image = prepare_gravestone_template(template.path, size)
            self._graveyard_template_cache[key] = image
            self._trim_image_cache(self._graveyard_template_cache, 128)
        return image

    def _cached_graveyard_background(self, path: Path, size: tuple[int, int]):
        key = (self._image_signature(path), size)
        photo = self._graveyard_background_cache.get(key)
        if photo is None:
            photo = ImageTk.PhotoImage(prepare_graveyard_background(path, size), master=self)
            self._graveyard_background_cache[key] = photo
            self._trim_image_cache(self._graveyard_background_cache, 8)
        return photo

    def _cached_graveyard_card(self, member: Member, template, portrait_path: Path | None):
        template_key = (
            template.grave_template_id, template.sha256, template.default_text_safe_area,
        ) if template is not None else (member.graveTemplateId, "missing")
        key = (
            member.id, member.name, member.className, member.deathDate,
            member.portraitOffsetX, member.portraitOffsetY, member.portraitZoom,
            member.textOffsetX, member.textOffsetY, member.textScale,
            template_key, self._image_signature(portrait_path),
            self._image_signature(gravestone_placeholder_path()) if template is None else None,
            get_language(),
        )
        photo = self._graveyard_card_cache.get(key)
        if photo is not None:
            return photo
        stale = [cache_key for cache_key in self._graveyard_card_cache if cache_key[0] == member.id]
        for cache_key in stale:
            self._graveyard_card_cache.pop(cache_key, None)
        if template is not None:
            frame = self._cached_gravestone_template(template, GRAVESTONE_CARD_SIZE)
            card = render_gravestone_card(
                member, frame, portrait_path,
                text_safe_area_master=template.default_text_safe_area,
            )
        else:
            try:
                frame = prepare_gravestone_template(gravestone_placeholder_path(), GRAVESTONE_CARD_SIZE)
            except (OSError, ValueError):
                frame = Image.new("RGBA", GRAVESTONE_CARD_SIZE, (0, 0, 0, 0))
            card = render_gravestone_card(member, frame, None)
        if template is None:
            label = tr(
                "graveyard.template_missing" if member.graveTemplateId
                else "graveyard.no_free_template",
            )
            draw = ImageDraw.Draw(card)
            draw.rounded_rectangle(
                (12, 110, GRAVESTONE_CARD_SIZE[0] - 12, 160),
                radius=8, fill="#241d1dcc", outline="#a46b61",
            )
            draw.multiline_text(
                (GRAVESTONE_CARD_SIZE[0] // 2, 135), label,
                anchor="mm", align="center", fill="#f3d9d3",
                font=_export_font(12, bold=True),
            )
        photo = ImageTk.PhotoImage(card, master=self)
        self._graveyard_card_cache[key] = photo
        self._trim_image_cache(self._graveyard_card_cache, 256)
        return photo

    def render_graveyard(self) -> None:
        if self.current_tab != "Friedhof":
            return
        c = self.graveyard_canvas
        try:
            frac = c.yview()[0]
        except Exception:
            frac = 0.0
        c.delete("all")
        self._graveyard_portrait_refs = []
        self._graveyard_card_refs = []
        self._graveyard_render_manifest = []
        visible = self.filtered_members("Friedhof")
        cw = max(260, c.winfo_width())
        vh = max(420, c.winfo_height())
        layout = graveyard_grid_layout(cw, len(visible))
        content_h = max(vh, layout["content_height"] if visible else 222)

        bg_path = gravestone_background_path()
        self._graveyard_bg_ref = None
        if Image and ImageTk and bg_path.exists():
            try:
                self._graveyard_bg_ref = self._cached_graveyard_background(bg_path, (cw, vh))
                y = 0
                while y < content_h:
                    c.create_image(0, y, anchor="nw", image=self._graveyard_bg_ref, tags=("background",))
                    y += vh
            except Exception:
                c.configure(bg="#15212b")
        else:
            c.configure(bg="#15212b")

        c.create_rectangle(18, 18, cw - 18, 102, fill="#101820", outline="#475c6f", width=1, stipple="gray50")
        c.create_text(38, 42, anchor="w", text=tr("graveyard.title"), fill="#f2f7fb", font=(self.header_font_family, 25))
        summary = tr("checker.graveyard_summary", count=len(visible))
        if visible:
            summary += f" · {tr('graveyard.adjust_hint')}"
        c.create_text(38, 76, anchor="w", width=max(200, cw - 76), text=summary, fill="#c2d3df", font=("Segoe UI", 10))

        if not visible:
            y = GRAVESTONE_HEADER_BOTTOM
            c.create_rectangle(30, y, cw - 30, y + 84, fill="#101820", outline="#475c6f", stipple="gray50")
            c.create_text(cw / 2, y + 42, text=tr("checker.graveyard_empty"), fill="#eaf4fb", font=("Segoe UI", 12, "bold"))
        else:
            inventory = self._gravestone_inventory
            template_by_id = inventory.by_id()
            for index, (m, position) in enumerate(zip(visible, layout["positions"])):
                template_id = m.graveTemplateId
                template = template_by_id.get(template_id)
                portrait_path = self.graveyard_portrait_path(m)
                try:
                    photo = self._cached_graveyard_card(m, template, portrait_path)
                except Exception:
                    continue
                self._graveyard_card_refs.append(photo)
                tag = f"member::{m.id}"
                c.create_image(
                    position[0], position[1], anchor="nw", image=photo,
                    tags=(tag, "gravestone-card"),
                )
                c.tag_bind(
                    tag, "<Button-1>",
                    lambda _event, member_id=m.id: self.open_gravestone_portrait_editor(member_id),
                )
                self._graveyard_render_manifest.append({
                    "member_id": m.id,
                    "template_id": template_id,
                    "template_state": (
                        template_by_id[template_id].state
                        if template_id in template_by_id else "missing"
                    ),
                    "position": position,
                    "portrait_path": str(portrait_path) if portrait_path else None,
                    "index": index,
                })
        c.configure(scrollregion=(0, 0, cw, content_h))
        try:
            c.yview_moveto(frac)
        except Exception:
            pass

    def open_gravestone_portrait_editor(self, member_id: str):
        member = self.model.find_by_id(member_id)
        if member is None or member.lifeStatus != "dead":
            return None
        if self._active_gravestone_editor is not None:
            try:
                if self._active_gravestone_editor.winfo_exists():
                    self._active_gravestone_editor.destroy()
            except tk.TclError:
                pass

        inventory, available_templates = self.model.available_gravestone_templates(member.id)
        templates = inventory.by_id()
        candidate_ids = [template.grave_template_id for template in available_templates]
        if member.graveTemplateId and member.graveTemplateId not in candidate_ids:
            candidate_ids.insert(0, member.graveTemplateId)
        initial_template_id = member.graveTemplateId or (candidate_ids[0] if candidate_ids else "")
        portrait_path = self.graveyard_portrait_path(member)

        window = tk.Toplevel(self)
        self._active_gravestone_editor = window
        window.title(f"{tr('graveyard.adjust_portrait')} · {member.name}")
        window.configure(bg=self.PANEL)
        window.transient(self)
        window.resizable(False, False)
        window.grab_set()
        tk.Label(
            window, text=tr("graveyard.adjust_help"), bg=self.PANEL, fg=self.MUTED,
            font=("Segoe UI", 9),
        ).pack(padx=14, pady=(12, 6))
        template_row = tk.Frame(window, bg=self.PANEL)
        template_row.pack(fill="x", padx=14, pady=(0, 6))
        template_id = tk.StringVar(value=initial_template_id)
        template_text = tk.StringVar()
        preview = tk.Canvas(
            window, width=GRAVESTONE_EDITOR_SIZE[0], height=GRAVESTONE_EDITOR_SIZE[1],
            bg="#101820", highlightthickness=0, cursor="fleur",
        )
        preview.pack(padx=14)
        offset_x = tk.DoubleVar(value=member.portraitOffsetX)
        offset_y = tk.DoubleVar(value=member.portraitOffsetY)
        zoom = tk.DoubleVar(value=member.portraitZoom)
        text_offset_x = tk.DoubleVar(value=member.textOffsetX)
        text_offset_y = tk.DoubleVar(value=member.textOffsetY)
        text_scale = tk.DoubleVar(value=member.textScale)
        death_date = tk.StringVar(value=member.deathDate)
        zoom_text = tk.StringVar()
        text_scale_text = tk.StringVar()
        edit_target = tk.StringVar(value="portrait")
        drag_origin = {
            "x": 0, "y": 0, "offset_x": 0.0, "offset_y": 0.0,
            "text_offset_x": 0.0, "text_offset_y": 0.0,
        }

        def selected_frame():
            selected = templates.get(template_id.get())
            if selected is None:
                return Image.new("RGBA", GRAVESTONE_EDITOR_SIZE, (0, 0, 0, 0))
            try:
                return self._cached_gravestone_template(selected, GRAVESTONE_EDITOR_SIZE)
            except (OSError, ValueError):
                return Image.new("RGBA", GRAVESTONE_EDITOR_SIZE, (0, 0, 0, 0))

        def redraw(_value=None) -> None:
            adjusted = Member.from_dict(member.to_dict(), member.id)
            adjusted.portraitOffsetX = normalize_portrait_offset(offset_x.get())
            adjusted.portraitOffsetY = normalize_portrait_offset(offset_y.get())
            adjusted.portraitZoom = normalize_portrait_zoom(zoom.get())
            adjusted.textOffsetX = normalize_text_offset(text_offset_x.get())
            adjusted.textOffsetY = normalize_text_offset(text_offset_y.get())
            adjusted.textScale = normalize_text_scale(text_scale.get())
            adjusted.deathDate = death_date.get().strip()
            card = render_gravestone_card(
                adjusted, selected_frame(), portrait_path, GRAVESTONE_EDITOR_SIZE,
                templates.get(template_id.get()).default_text_safe_area
                if templates.get(template_id.get()) else None,
            )
            selected = templates.get(template_id.get())
            if selected is None:
                draw = ImageDraw.Draw(card)
                label = tr(
                    "graveyard.template_missing" if template_id.get()
                    else "graveyard.no_free_template",
                )
                draw.rounded_rectangle((18, 165, 312, 240), radius=10,
                                       fill="#241d1dcc", outline="#a46b61")
                draw.multiline_text((165, 202), label, anchor="mm", align="center",
                                    fill="#f3d9d3", font=_export_font(16, bold=True))
            photo = ImageTk.PhotoImage(card, master=window)
            preview.delete("all")
            preview.create_image(0, 0, anchor="nw", image=photo)
            preview.image = photo
            zoom_text.set(f"{adjusted.portraitZoom:.2f}×")
            text_scale_text.set(f"{adjusted.textScale:.2f}×")
            if selected is None:
                template_text.set(tr(
                    "graveyard.template_missing" if template_id.get()
                    else "graveyard.no_free_template",
                ))
            else:
                index = candidate_ids.index(template_id.get()) + 1
                template_text.set(tr(
                    "graveyard.template_position", current=index,
                    total=len(candidate_ids), filename=selected.path.name,
                ))

        def change_template(step: int) -> None:
            if not candidate_ids:
                return
            try:
                index = candidate_ids.index(template_id.get())
            except ValueError:
                index = 0
            template_id.set(candidate_ids[(index + step) % len(candidate_ids)])
            redraw()

        self._button(template_row, "◀", lambda: change_template(-1)).pack(side="left")
        tk.Label(
            template_row, textvariable=template_text, bg=self.PANEL, fg=self.TEXT,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", fill="x", expand=True, padx=8)
        self._button(template_row, "▶", lambda: change_template(1)).pack(side="right")

        def begin_drag(event) -> None:
            drag_origin.update({
                "x": event.x, "y": event.y,
                "offset_x": offset_x.get(), "offset_y": offset_y.get(),
                "text_offset_x": text_offset_x.get(),
                "text_offset_y": text_offset_y.get(),
            })

        def drag(event) -> None:
            if edit_target.get() == "text":
                adjusted_x, adjusted_y = shifted_text_offsets(
                    drag_origin["text_offset_x"], drag_origin["text_offset_y"],
                    event.x - drag_origin["x"], event.y - drag_origin["y"],
                    GRAVESTONE_EDITOR_SIZE,
                )
                text_offset_x.set(adjusted_x)
                text_offset_y.set(adjusted_y)
            else:
                portrait_box = detect_gravestone_portrait_opening(selected_frame()).box
                adjusted_x, adjusted_y = shifted_portrait_offsets(
                    drag_origin["offset_x"], drag_origin["offset_y"],
                    event.x - drag_origin["x"], event.y - drag_origin["y"],
                    (portrait_box[2] - portrait_box[0], portrait_box[3] - portrait_box[1]),
                )
                offset_x.set(adjusted_x)
                offset_y.set(adjusted_y)
            redraw()

        preview.bind("<ButtonPress-1>", begin_drag)
        preview.bind("<B1-Motion>", drag)
        target_row = tk.Frame(window, bg=self.PANEL)
        target_row.pack(fill="x", padx=14, pady=(7, 0))
        for value, key in (("portrait", "graveyard.move_portrait"), ("text", "graveyard.move_text")):
            tk.Radiobutton(
                target_row, text=tr(key), variable=edit_target, value=value,
                bg=self.PANEL, fg=self.TEXT, selectcolor=self.PANEL_2,
                activebackground=self.PANEL, activeforeground=self.TEXT,
                font=("Segoe UI", 9),
            ).pack(side="left", padx=(0, 12))
        controls = tk.Frame(window, bg=self.PANEL)
        controls.pack(fill="x", padx=14, pady=(8, 4))
        tk.Label(
            controls, text=tr("graveyard.zoom"), bg=self.PANEL, fg=self.TEXT,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
        tk.Scale(
            controls, from_=GRAVESTONE_PORTRAIT_ZOOM_RANGE[0],
            to=GRAVESTONE_PORTRAIT_ZOOM_RANGE[1], resolution=0.01,
            orient="horizontal", variable=zoom, command=redraw,
            showvalue=False, bg=self.PANEL, fg=self.TEXT,
            troughcolor=self.PANEL_2, highlightthickness=0, length=220,
        ).pack(side="left", padx=8)
        tk.Label(
            controls, textvariable=zoom_text, width=5, bg=self.PANEL, fg=self.TEXT,
            font=("Segoe UI", 9),
        ).pack(side="right")

        text_controls = tk.Frame(window, bg=self.PANEL)
        text_controls.pack(fill="x", padx=14, pady=(0, 4))
        tk.Label(
            text_controls, text=tr("graveyard.text_scale"), bg=self.PANEL,
            fg=self.TEXT, font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
        tk.Scale(
            text_controls, from_=GRAVESTONE_TEXT_SCALE_RANGE[0],
            to=GRAVESTONE_TEXT_SCALE_RANGE[1], resolution=0.01,
            orient="horizontal", variable=text_scale, command=redraw,
            showvalue=False, bg=self.PANEL, fg=self.TEXT,
            troughcolor=self.PANEL_2, highlightthickness=0, length=190,
        ).pack(side="left", padx=8)
        tk.Label(
            text_controls, textvariable=text_scale_text, width=5,
            bg=self.PANEL, fg=self.TEXT, font=("Segoe UI", 9),
        ).pack(side="right")

        date_row = tk.Frame(window, bg=self.PANEL)
        date_row.pack(fill="x", padx=14, pady=(2, 6))
        tk.Label(
            date_row, text=tr("graveyard.death_date_label"), bg=self.PANEL,
            fg=self.TEXT, font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
        death_date_entry = tk.Entry(
            date_row, textvariable=death_date, width=14, bg=self.PANEL_2,
            fg=self.TEXT, insertbackground=self.TEXT, relief="flat",
            font=("Segoe UI", 9),
        )
        death_date_entry.pack(side="right", ipady=4)
        death_date_entry.bind("<KeyRelease>", redraw)
        tk.Label(
            date_row, text=tr("graveyard.death_date_format"), bg=self.PANEL,
            fg=self.MUTED, font=("Segoe UI", 8),
        ).pack(side="right", padx=(0, 8))

        buttons = tk.Frame(window, bg=self.PANEL)
        buttons.pack(fill="x", padx=14, pady=(4, 12))

        def reset() -> None:
            text_offset_x.set(0.0)
            text_offset_y.set(0.0)
            text_scale.set(1.0)
            redraw()

        def apply() -> None:
            try:
                self.model.set_gravestone_adjustment(
                    member.id, template_id.get(),
                    offset_x.get(), offset_y.get(), zoom.get(),
                    text_offset_x.get(), text_offset_y.get(), text_scale.get(),
                    death_date.get(),
                )
            except ValueError as exc:
                messagebox.showwarning(APP_NAME, str(exc), parent=window)
                return
            self.autosave()
            self.render_graveyard()
            self.status_var.set(tr("graveyard.adjust_saved", name=member.name))
            window.destroy()

        self._button(buttons, tr("graveyard.reset"), reset).pack(side="left")
        self._button(buttons, tr("graveyard.cancel"), window.destroy).pack(side="right", padx=(6, 0))
        self._button(buttons, tr("graveyard.apply"), apply, kind="primary").pack(side="right")
        redraw()
        return window

    def render_roster(self) -> None:
        if self.current_tab != "Roster":
            return
        if self.roster_fit_mode:
            self._recalculate_roster_fit()
        try:
            fraction = self.roster_canvas.yview()[0]
        except Exception:
            fraction = 0.0
        for child in self.roster_inner.winfo_children():
            child.destroy()
        self._roster_portrait_refs = []
        self._roster_icon_refs = []
        width = max(260, self.roster_canvas.winfo_width() - 24)
        zoom = self.roster_zoom_percent
        columns = roster_column_count(width - scaled_roster_value(36, zoom), zoom)

        title = tk.Label(
            self.roster_inner, text=tr("roster.title"), bg="#0d1117", fg="#d7b56d",
            font=(self.header_font_family, scaled_roster_value(30, zoom)), anchor="w",
        )
        title.pack(
            fill="x", padx=scaled_roster_value(18, zoom),
            pady=(scaled_roster_value(16, zoom), scaled_roster_value(8, zoom)),
        )
        groups = group_roster_members(self.filtered_members("Roster"))
        role_keys = {
            "tank": "roster.tanks",
            "healer": "roster.healers", "dps": "roster.dps",
            "not_set": "roster.unassigned",
        }
        for role in ROSTER_ROLE_ORDER:
            section = tk.Frame(
                self.roster_inner, bg="#131922", highlightthickness=1,
                highlightbackground="#5b4930",
            )
            section.pack(
                fill="x", padx=scaled_roster_value(16, zoom),
                pady=scaled_roster_value(8, zoom),
            )
            heading_color = "#b8a47b" if role == "not_set" else "#e0bd72"
            tk.Label(
                section, text=tr(role_keys[role]), bg="#131922", fg=heading_color,
                font=(self.header_font_family, scaled_roster_value(20, zoom)), anchor="w",
            ).pack(
                fill="x", padx=scaled_roster_value(14, zoom),
                pady=(scaled_roster_value(10, zoom), scaled_roster_value(5, zoom)),
            )
            cards = tk.Frame(section, bg="#131922")
            cards.pack(
                fill="x", padx=scaled_roster_value(8, zoom),
                pady=(0, scaled_roster_value(10, zoom)),
            )
            for column in range(columns):
                cards.grid_columnconfigure(column, weight=1, uniform="roster")
            if not groups[role]:
                tk.Label(
                    cards, text=tr("roster.empty"), bg="#131922", fg=self.MUTED,
                    font=("Segoe UI", scaled_roster_value(10, zoom)), anchor="w",
                ).grid(
                    row=0, column=0, columnspan=columns, sticky="ew",
                    padx=scaled_roster_value(8, zoom), pady=scaled_roster_value(10, zoom),
                )
            for index, member in enumerate(groups[role]):
                card = self._create_roster_card(cards, member)
                card.grid(
                    row=index // columns, column=index % columns,
                    sticky="n", padx=scaled_roster_value(7, zoom),
                    pady=scaled_roster_value(7, zoom),
                )
        self._bind_roster_wheel(self.roster_inner)
        self.roster_inner.update_idletasks()
        self.roster_canvas.configure(scrollregion=self.roster_canvas.bbox("all"))
        try:
            self.roster_canvas.yview_moveto(fraction)
        except Exception:
            pass

    def _create_roster_card(self, parent, member: Member):
        zoom = self.roster_zoom_percent
        card_width, card_height = roster_card_size(zoom)
        portrait_size = roster_portrait_size(zoom)
        selected = member.id == self.selected_member_id
        card = tk.Frame(
            parent, bg="#202832", width=card_width, height=card_height,
            highlightthickness=2 if selected else 1,
            highlightbackground="#d0aa61" if selected else CLASS_COLORS.get(member.className, "#46515e"),
            cursor="hand2",
        )
        card.grid_propagate(False)
        portrait_box = tk.Frame(
            card, width=portrait_size[0], height=portrait_size[1],
            bg="#0b0f14", highlightthickness=1, highlightbackground="#3c4652",
        )
        portrait_box.pack(
            padx=scaled_roster_value(12, zoom),
            pady=(scaled_roster_value(12, zoom), scaled_roster_value(7, zoom)),
        )
        portrait_box.pack_propagate(False)
        portrait_label = tk.Label(
            portrait_box, text=tr("checker.missing_portrait"), bg="#0b0f14",
            fg=self.MUTED, font=("Segoe UI", scaled_roster_value(10, zoom)), justify="center",
        )
        portrait_label.pack(fill="both", expand=True)
        portrait_path = self.graveyard_portrait_path(member)
        if portrait_path and Image and ImageTk:
            try:
                signature = self._image_signature(portrait_path)
                cache_key = (signature, portrait_size)
                photo = self._roster_portrait_cache.get(cache_key)
                if photo is None:
                    with Image.open(portrait_path) as raw:
                        image = ImageOps.exif_transpose(raw).convert("RGB") if ImageOps else raw.convert("RGB")
                        if ImageOps:
                            canvas = ImageOps.fit(
                                image, portrait_size, method=Image.Resampling.LANCZOS,
                                centering=(0.5, 0.40),
                            )
                        else:
                            scale = max(portrait_size[0] / image.width, portrait_size[1] / image.height)
                            resized = image.resize(
                                (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                                Image.Resampling.LANCZOS,
                            )
                            left = max(0, (resized.width - portrait_size[0]) // 2)
                            top = max(0, int((resized.height - portrait_size[1]) * 0.35))
                            canvas = resized.crop((left, top, left + portrait_size[0], top + portrait_size[1]))
                        photo = ImageTk.PhotoImage(canvas, master=self)
                    stale = [
                        key for key in self._roster_portrait_cache
                        if key[0] and signature and key[0][0] == signature[0]
                        and key[0] != signature
                    ]
                    for key in stale:
                        self._roster_portrait_cache.pop(key, None)
                    self._roster_portrait_cache[cache_key] = photo
                    self._trim_image_cache(self._roster_portrait_cache, 256)
                self._roster_portrait_refs.append(photo)
                portrait_label.configure(image=photo, text="")
            except Exception:
                pass

        identity_height = scaled_roster_value(48, zoom)
        identity = tk.Frame(card, bg="#202832", height=identity_height)
        identity.pack(fill="x", padx=scaled_roster_value(12, zoom))
        identity.pack_propagate(False)
        icon = self._load_roster_class_icon(member.className, scaled_roster_value(28, zoom))
        icon_label = tk.Label(identity, bg="#202832", image=icon or "", text="" if icon else "•")
        icon_label.pack(side="left", padx=(0, scaled_roster_value(6, zoom)))
        name_size = 12 if len(member.name) <= 14 else 11 if len(member.name) <= 20 else 10
        tk.Label(
            identity, text=member.name, bg="#202832", fg="#ffffff",
            font=("Segoe UI", scaled_roster_value(name_size, zoom), "bold"),
            anchor="w", justify="left", wraplength=scaled_roster_value(104, zoom),
        ).pack(side="left", fill="x", expand=True)
        badge_color = "#8b6728" if member.characterType == "main" else "#3f5369"
        badge_text = character_type_display(member.characterType)
        if member.characterType == "twink":
            badge_text = badge_text.upper()
        tk.Label(
            identity, text=badge_text,
            bg=badge_color, fg="#ffffff",
            font=("Segoe UI", scaled_roster_value(8, zoom), "bold"),
            padx=scaled_roster_value(5, zoom), pady=scaled_roster_value(2, zoom),
        ).pack(side="right")
        class_spec = combine_class_spec(member.className, member.spec) or tr("common.not_set")
        player = self.model.find_player_by_id(member.playerId)
        player_name = player.playerName if player else tr("common.unassigned")
        main = self.model.associated_main(member)
        twink_line = ""
        player_line = f"\n{tr('common.player')}: {player_name}"
        if member.characterType == "twink":
            twink_line = f"\nMain: {main.name if main else tr('checker.no_active_main')}"
            player_line = ""
        details = (
            f"{class_spec}{twink_line}{player_line}\n"
            f"{tr('gear.label')}: {gear_status_display(member.gearStatus)}\n"
            f"{tr('enchants.label')}: {enchant_status_display(member.enchants)}"
        )
        tk.Label(
            card, text=details, bg="#202832", fg="#cbd4df", justify="left",
            anchor="nw", font=("Segoe UI", scaled_roster_value(9, zoom)),
            wraplength=scaled_roster_value(190, zoom),
        ).pack(
            fill="x", padx=scaled_roster_value(12, zoom),
            pady=(scaled_roster_value(7, zoom), scaled_roster_value(10, zoom)),
        )

        def bind_click(widget) -> None:
            widget.bind("<Button-1>", lambda _event, member_id=member.id: self._select_roster_member(member_id))
            for child in widget.winfo_children():
                bind_click(child)

        bind_click(card)
        return card

    def _load_roster_class_icon(self, class_name: str, size: int):
        if Image is None or ImageTk is None or ImageOps is None:
            return None
        source = class_icon_path(class_name)
        if not source.is_file():
            source = fallback_class_icon_path(class_name)
        if not source.is_file():
            return None
        try:
            signature = self._image_signature(source)
            cache_key = (signature, size)
            photo = self._roster_icon_cache.get(cache_key)
            if photo is None:
                with Image.open(source) as raw:
                    icon = ImageOps.fit(raw.convert("RGB"), (size, size), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(icon, master=self)
                stale = [
                    key for key in self._roster_icon_cache
                    if key[0] and signature and key[0][0] == signature[0]
                    and key[0] != signature
                ]
                for key in stale:
                    self._roster_icon_cache.pop(key, None)
                self._roster_icon_cache[cache_key] = photo
                self._trim_image_cache(self._roster_icon_cache, 64)
            self._roster_icon_refs.append(photo)
            return photo
        except Exception:
            return None

    def export_roster_png(self) -> None:
        if not any(member.lifeStatus == "active" for member in self.model.members):
            messagebox.showinfo(APP_NAME, tr("roster.export_empty"), parent=self)
            return
        project_name = ""
        if self.model.project_path:
            project_name = sanitize_filename(self.model.project_path.stem).strip(" ._")
        filename = f"{project_name + '_' if project_name else ''}Roster_{today_iso()}.png"
        destination = filedialog.asksaveasfilename(
            parent=self, title=tr("roster.export_png"), defaultextension=".png",
            initialfile=filename, filetypes=[("PNG", "*.png")],
        )
        if not destination:
            return
        project_path = self.model.project_path
        dirty = self.model.dirty
        try:
            manifest = render_roster_png(self.model, Path(destination))
            self.status_var.set(tr(
                "roster.export_success", path=destination,
                count=len(manifest["cards"]),
            ))
        except Exception as exc:
            messagebox.showerror(
                APP_NAME, tr("roster.export_failed", error=exc), parent=self,
            )
        finally:
            self.model.project_path = project_path
            self.model.dirty = dirty

    def _selected_raid(self) -> Raid | None:
        selection = self.raid_tree.selection() if hasattr(self, "raid_tree") else ()
        return self.model.find_raid_by_id(selection[0]) if len(selection) == 1 else None

    def _sort_raids_by(self, column: str) -> None:
        current_column, current_descending = self.raid_sort_state
        descending = not current_descending if current_column == column else False
        self.raid_sort_state = (column, descending)
        self.refresh_raids()

    def _sort_raid_statistics_by(self, column: str) -> None:
        current_column, current_descending = self.raid_statistics_sort_state
        descending = not current_descending if current_column == column else False
        self.raid_statistics_sort_state = (column, descending)
        self.refresh_raid_statistics()

    def _update_raid_action_states(self) -> None:
        raid = self._selected_raid() if hasattr(self, "raid_tree") else None
        state = "normal" if raid is not None else "disabled"
        if hasattr(self, "raid_import_button"):
            self.raid_import_button.configure(state=state)
            self.raid_open_button.configure(state=state)
            reset_state = (
                "normal" if raid is not None and self.model.attendance_for_raid(raid.id)
                else "disabled"
            )
            self.raid_reset_button.configure(state=reset_state)

    @staticmethod
    def _update_tree_sort_headings(tree, headings: dict, state: tuple[str, bool]) -> None:
        selected_column, descending = state
        for key, (title, _width) in headings.items():
            marker = (" ▼" if descending else " ▲") if key == selected_column else ""
            tree.heading(key, text=title + marker)

    def refresh_raids(self, select_first: bool = False) -> None:
        if not hasattr(self, "raid_tree"):
            return
        old_selection = self._selected_raid()
        old_id = old_selection.id if old_selection else None
        for item in self.raid_tree.get_children():
            self.raid_tree.delete(item)
        query = self.search_var.get().strip().casefold()
        selected_status = self.raid_status_filter.get()
        status_filter = next((
            status for status in ("draft", "recorded")
            if selected_status == tr(f"raids.status_{status}")
        ), None)
        visible_raids = [
            raid for raid in self.model.raids
            if (status_filter is None or raid.status == status_filter)
            and (not query or query in (
                f"{raid.date}\n{raid.name}\n{raid.warcraftLogsUrl}\n"
                f"{tr(f'raids.status_{raid.status}')}"
            ).casefold())
        ]
        column, descending = self.raid_sort_state
        ordered = sorted(
            visible_raids,
            key=lambda raid: (
                raid_table_sort_value(
                    raid, column, len(self.model.attendance_for_raid(raid.id)),
                    tr(f"raids.status_{raid.status}"),
                ),
                raid.id,
            ),
            reverse=descending,
        )
        self._update_tree_sort_headings(
            self.raid_tree, self._raid_headings, self.raid_sort_state,
        )
        for raid in ordered:
            entries = self.model.attendance_for_raid(raid.id)
            self.raid_tree.insert("", "end", iid=raid.id, values=(
                raid_date_display(raid.date),
                raid.name,
                len(entries),
                tr(f"raids.status_{raid.status}"),
                tr("raids.open_logs_short") if raid.warcraftLogsUrl else "–",
            ))
        target = old_id if old_id and self.raid_tree.exists(old_id) else None
        if target is None and select_first and ordered:
            target = ordered[0].id
        if target:
            self.raid_tree.selection_set(target)
            self.raid_tree.focus(target)
            self.raid_tree.see(target)
        self.visible_count_var.set(tr(
            "raids.raid_count_filtered", visible=len(ordered), total=len(self.model.raids),
        ))
        self._update_raid_action_states()
        self.refresh_raid_statistics()

    def refresh_raid_statistics(self) -> None:
        if not hasattr(self, "raid_statistics_tree"):
            return
        for item in self.raid_statistics_tree.get_children():
            self.raid_statistics_tree.delete(item)
        rows = [
            (player, self.model.attendance_statistics_for_player(player.playerId))
            for player in self.model.players
        ]
        column, descending = self.raid_statistics_sort_state
        rows.sort(
            key=lambda row: (
                raid_statistics_sort_value(row[0], row[1], column), row[0].playerId,
            ),
            reverse=descending,
        )
        self._update_tree_sort_headings(
            self.raid_statistics_tree, self._raid_statistics_headings,
            self.raid_statistics_sort_state,
        )
        for player, stats in rows:
            compact = tr(
                "raids.percentage_with_twink" if stats.twink_percent else "raids.percentage",
                total=stats.attendance_percent, twink=stats.twink_percent,
            )
            self.raid_statistics_tree.insert("", "end", iid=player.playerId, values=(
                player.playerName, compact, stats.eligible_raids,
                stats.main_attendances, stats.twink_attendances,
            ))

    def _raid_editor_values(self, raid: Raid | None = None) -> tuple[str, str, str] | None:
        dialog = tk.Toplevel(self)
        dialog.title(tr("raids.edit_title") if raid else tr("raids.create_title"))
        dialog.configure(bg=self.PANEL)
        dialog.transient(self)
        dialog.resizable(False, False)
        date_var = tk.StringVar(value=raid.date if raid else today_iso())
        name_var = tk.StringVar(value=raid.name if raid else "")
        link_var = tk.StringVar(value=raid.warcraftLogsUrl if raid else "")
        result: list[tuple[str, str, str]] = []

        for row, (label, variable) in enumerate((
            (tr("common.date"), date_var),
            (tr("raids.raid_name"), name_var),
            (tr("raids.warcraft_logs"), link_var),
        )):
            self._label(dialog, label, muted=True).grid(
                row=row, column=0, sticky="w", padx=14, pady=(10 if row == 0 else 4, 4),
            )
            entry = tk.Entry(
                dialog, textvariable=variable, width=46, bg=self.PANEL_2,
                fg=self.TEXT, insertbackground=self.TEXT, relief="flat",
            )
            entry.grid(row=row, column=1, sticky="ew", padx=(0, 14), pady=(10 if row == 0 else 4, 4), ipady=5)
            if row == 1:
                entry.focus_set()

        buttons = tk.Frame(dialog, bg=self.PANEL)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", padx=12, pady=12)

        def apply_values() -> None:
            try:
                validated = Raid(
                    id=raid.id if raid else "validation", date=date_var.get(),
                    name=name_var.get(), warcraftLogsUrl=link_var.get(),
                    status=raid.status if raid else "draft",
                )
            except ValueError as exc:
                messagebox.showerror(tr("common.error"), raid_error_text(exc), parent=dialog)
                return
            result.append((validated.date, validated.name, validated.warcraftLogsUrl))
            dialog.destroy()

        self._button(buttons, tr("common.cancel"), dialog.destroy).pack(side="right", padx=3)
        self._button(buttons, tr("common.save"), apply_values, kind="primary").pack(side="right", padx=3)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.grab_set()
        self.wait_window(dialog)
        return result[0] if result else None

    def create_raid_dialog(self) -> None:
        values = self._raid_editor_values()
        if values is None:
            return
        try:
            raid = self.model.create_raid(*values)
            self.autosave()
            self.refresh_all()
            self.raid_tree.selection_set(raid.id)
            self.raid_tree.focus(raid.id)
            self.status_var.set(tr("raids.created", name=raid.name))
        except Exception as exc:
            messagebox.showerror(tr("common.error"), tr("raids.save_failed", error=raid_error_text(exc)), parent=self)

    def edit_selected_raid(self) -> None:
        raid = self._selected_raid()
        if raid is None:
            messagebox.showinfo(APP_NAME, tr("raids.select_first"), parent=self)
            return
        values = self._raid_editor_values(raid)
        if values is None:
            return
        try:
            self.model.update_raid(raid.id, *values)
            self.autosave()
            self.refresh_all()
            self.status_var.set(tr("raids.updated", name=raid.name))
        except Exception as exc:
            messagebox.showerror(tr("common.error"), tr("raids.save_failed", error=raid_error_text(exc)), parent=self)

    def delete_selected_raid(self) -> None:
        raid = self._selected_raid()
        if raid is None:
            messagebox.showinfo(APP_NAME, tr("raids.select_first"), parent=self)
            return
        if not messagebox.askyesno(
            tr("raids.delete_title"), tr("raids.delete_question", name=raid.name), parent=self,
        ):
            return
        self.model.delete_raid(raid.id)
        self.autosave()
        self.refresh_all(select_first=True)
        self.status_var.set(tr("raids.deleted", name=raid.name))

    def _confirm_raid_action(self, title: str, message: str,
                             confirm_text: str, kind: str = "primary") -> bool:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.configure(bg=self.PANEL)
        dialog.transient(self)
        dialog.resizable(False, False)
        result: list[bool] = []
        self._label(dialog, message, justify="left", wraplength=470).pack(
            fill="x", padx=18, pady=(18, 14),
        )
        buttons = tk.Frame(dialog, bg=self.PANEL)
        buttons.pack(fill="x", padx=16, pady=(0, 16))

        def finish(value: bool) -> None:
            result.append(value)
            dialog.destroy()

        self._button(
            buttons, tr("common.cancel"), lambda: finish(False),
        ).pack(side="right", padx=3)
        self._button(
            buttons, confirm_text, lambda: finish(True), kind=kind,
        ).pack(side="right", padx=3)
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        dialog.grab_set()
        self.wait_window(dialog)
        return bool(result and result[0])

    def _confirm_attendance_target(self, raid: Raid) -> bool:
        return self._confirm_raid_action(
            tr("raids.import_target_title"),
            attendance_target_text(raid, len(self.model.attendance_for_raid(raid.id))),
            tr("raids.continue_import"),
        )

    def reset_selected_raid_attendance(self) -> None:
        raid = self._selected_raid()
        if raid is None:
            messagebox.showinfo(APP_NAME, tr("raids.select_first"), parent=self)
            return
        entries = self.model.attendance_for_raid(raid.id)
        if not entries:
            return
        if not self._confirm_raid_action(
            tr("raids.reset_attendance"),
            tr(
                "raids.reset_question", name=raid.name,
                date=raid_date_display(raid.date), participants=len(entries),
            ),
            tr("raids.reset_attendance"), kind="danger",
        ):
            return
        self.model.reset_raid_attendance(raid.id)
        self.autosave()
        self.refresh_all()
        self.status_var.set(tr("raids.reset_complete", name=raid.name))

    def _decide_unknown_attendance(
            self, names: Iterable[str], raid: Raid | None = None,
    ) -> dict[str, tuple[str, str | None]] | None:
        decisions: dict[str, tuple[str, str | None]] = {}
        main_choices = []
        for member in self.model.members:
            if member.lifeStatus != "active" or member.characterType != "main" or not member.playerId:
                continue
            player = self.model.find_player_by_id(member.playerId)
            if player is not None:
                main_choices.append((f"{player.playerName} · {member.name}", member.id))
        main_choices.sort(key=lambda item: _text_sort_key(item[0]))

        for name in names:
            dialog = tk.Toplevel(self)
            dialog.title(tr("raids.unknown_title"))
            dialog.configure(bg=self.PANEL)
            dialog.transient(self)
            dialog.resizable(False, False)
            selected: list[tuple[str, str | None]] = []
            question = tr("raids.unknown_question", name=name)
            if raid is not None:
                question = tr(
                    "raids.unknown_for_raid", name=raid.name,
                    date=raid_date_display(raid.date), question=question,
                )
            self._label(
                dialog, question,
                justify="left", wraplength=430,
            ).pack(fill="x", padx=16, pady=(16, 10))
            main_var = tk.StringVar(value=main_choices[0][0] if main_choices else "")
            main_lookup = dict(main_choices)
            self._label(dialog, tr("raids.twink_player"), muted=True).pack(
                anchor="w", padx=16,
            )
            main_combo = ttk.Combobox(
                dialog, textvariable=main_var,
                values=[label for label, _member_id in main_choices],
                state="readonly", width=48,
            )
            main_combo.pack(fill="x", padx=16, pady=(3, 12))

            def finish(action: str) -> None:
                main_id = main_lookup.get(main_var.get()) if action == "twink" else None
                if action == "twink" and main_id is None:
                    messagebox.showwarning(
                        tr("raids.unknown_title"), tr("raids.no_main_available"), parent=dialog,
                    )
                    return
                selected.append((action, main_id))
                dialog.destroy()

            buttons = tk.Frame(dialog, bg=self.PANEL)
            buttons.pack(fill="x", padx=14, pady=(0, 14))
            self._button(
                buttons, tr("raids.add_as_main"), lambda: finish("main"), kind="primary",
            ).pack(side="left", padx=2)
            twink_button = self._button(
                buttons, tr("raids.assign_as_twink"), lambda: finish("twink"),
            )
            twink_button.pack(side="left", padx=2)
            if not main_choices:
                twink_button.configure(state="disabled")
            self._button(
                buttons, tr("raids.discard"), lambda: finish("discard"), kind="danger",
            ).pack(side="right", padx=2)
            dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
            dialog.grab_set()
            self.wait_window(dialog)
            if not selected:
                return None
            decisions[name] = selected[0]
        return decisions

    def import_raid_attendance_csv(self) -> None:
        raid = self._selected_raid()
        if raid is None:
            messagebox.showinfo(APP_NAME, tr("raids.select_first"), parent=self)
            return
        path = filedialog.askopenfilename(
            parent=self, title=tr("raids.select_csv"),
            filetypes=[(tr("common.csv_files"), "*.csv"), (tr("common.all_files"), "*.*")],
        )
        if not path:
            return
        try:
            if not self._confirm_attendance_target(raid):
                return
            names = read_csv_names(Path(path))
            resolution = self.model.resolve_raid_attendance(names)
            if resolution.ambiguous_names:
                messagebox.showerror(
                    tr("raids.ambiguous_title"),
                    tr("raids.ambiguous_characters", names=", ".join(resolution.ambiguous_names)),
                    parent=self,
                )
                return
            existing_entries = self.model.attendance_for_raid(raid.id)
            if existing_entries and not self._confirm_raid_action(
                tr("raids.existing_attendance_title"),
                tr(
                    "raids.existing_attendance", name=raid.name,
                    date=raid_date_display(raid.date), participants=len(existing_entries),
                ),
                tr("raids.replace"), kind="danger",
            ):
                return
            decisions = self._decide_unknown_attendance(resolution.unknown_names, raid)
            if decisions is None:
                return
            added = sum(action != "discard" for action, _main_id in decisions.values())
            discarded = sum(action == "discard" for action, _main_id in decisions.values())
            if not self._confirm_raid_action(
                tr("raids.import_summary_title"),
                tr(
                    "raids.import_summary", name=raid.name,
                    date=raid_date_display(raid.date), recognized=len(names),
                    known=len(names) - len(resolution.unknown_names),
                    added=added, discarded=discarded,
                ),
                tr("raids.import"),
            ):
                return
            summary = self.model.import_raid_attendance(
                raid.id, names, unknown_decisions=decisions,
            )
            self.autosave()
            self.refresh_all()
            merged = ""
            if summary["merged"]:
                groups = "; ".join(" + ".join(group) for group in summary["merged"])
                merged = "\n" + tr("raids.merged", groups=groups)
            initialized = ""
            if summary["auto_initialized"]:
                initialized = "\n" + tr(
                    "raids.auto_initialized", count=summary["auto_initialized"],
                )
            messagebox.showinfo(
                tr("raids.import_complete_title"),
                tr(
                    "raids.import_complete", participants=summary["participants"],
                    added=summary["added"], discarded=summary["discarded"],
                    initialized=initialized, merged=merged,
                ),
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror(
                tr("common.error"), tr("raids.import_failed", error=raid_error_text(exc)), parent=self,
            )

    def open_selected_raid(self) -> None:
        raid = self._selected_raid()
        if raid is None:
            messagebox.showinfo(APP_NAME, tr("raids.select_first"), parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title(tr("raids.details_title", name=raid.name))
        dialog.configure(bg=self.PANEL)
        dialog.transient(self)
        dialog_height = min(960, max(520, self.winfo_screenheight() - 120))
        dialog.geometry(f"740x{dialog_height}")
        dialog.minsize(620, 420)
        entries = self.model.attendance_for_raid(raid.id)
        summary = tk.Frame(dialog, bg=self.PANEL)
        summary.pack(fill="x", padx=12, pady=(8, 6))
        self._label(
            summary,
            tr(
                "raids.details_summary", date=raid.date, name=raid.name,
                participants=len(entries), status=tr(f"raids.status_{raid.status}"),
            ),
            justify="left",
        ).pack(side="left", anchor="w")
        if raid.warcraftLogsUrl:
            self._button(
                summary, tr("raids.open_logs"),
                lambda: webbrowser.open(raid.warcraftLogsUrl),
            ).pack(side="right")
        columns = ("player", "character", "type")
        detail_style = ttk.Style(dialog)
        detail_style.configure("RaidDetail.Treeview", rowheight=22)
        table_frame = tk.Frame(dialog, bg=self.PANEL)
        table_frame.pack(fill="both", expand=True, padx=12, pady=(0, 5))
        tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", style="RaidDetail.Treeview",
        )
        headings = {
            key: (title, width) for key, title, width in (
            ("player", tr("common.player"), 220),
            ("character", tr("raids.used_character"), 220),
            ("type", tr("raids.type"), 100),
        )}
        sort_state = ["player", False]

        def render_entries() -> None:
            for item in tree.get_children():
                tree.delete(item)
            column, descending = sort_state
            ordered = sorted(
                entries,
                key=lambda entry: (
                    raid_attendance_sort_value(
                        entry, column, tr(f"character_type.{entry.attendanceType}"),
                    ),
                    entry.id,
                ),
                reverse=descending,
            )
            self._update_tree_sort_headings(tree, headings, (column, descending))
            for entry in ordered:
                tree.insert("", "end", iid=entry.id, values=(
                    entry.playerNameSnapshot, entry.characterNameSnapshot,
                    tr(f"character_type.{entry.attendanceType}"),
                ))

        def sort_entries(column: str) -> None:
            current_column, current_descending = sort_state
            sort_state[:] = [
                column,
                not current_descending if current_column == column else False,
            ]
            render_entries()

        for key, (title, width) in headings.items():
            tree.heading(key, text=title, command=lambda column=key: sort_entries(column))
            tree.column(key, width=width, stretch=key != "type")
        render_entries()
        tree.pack(side="left", fill="both", expand=True)
        detail_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        detail_scroll.pack(side="right", fill="y")
        tree.configure(yscrollcommand=detail_scroll.set)
        self._button(dialog, tr("common.close"), dialog.destroy).pack(
            side="right", padx=12, pady=(0, 7),
        )

    def _select_roster_member(self, member_id: str) -> None:
        self.show_member(member_id)
        if hasattr(self, "roster_inner"):
            self.render_roster()

    def _select_graveyard_member(self, member_id: str) -> None:
        self.show_member(member_id)
        self.render_graveyard()

    def on_tree_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if sel:
            self.show_member(sel[0])

    # ---------- Detail / Member ----------
    def show_member(self, member_id: str) -> None:
        member = self.model.find_by_id(member_id)
        if not member:
            return
        self.selected_member_id = member_id
        self.detail_name_var.set(member.name)
        life = tr(f"life.{member.lifeStatus}")
        self.detail_meta_var.set(f"{life} · {tr('checker.source')}: {member.source}")
        self.detail_death_var.set(f"{tr('checker.death_date')}: {member.deathDate or '–'}" if member.lifeStatus == "dead" else "")
        self.race_var.set(race_display(member.race))
        self.class_var.set(member.className or tr("common.not_set"))
        self._update_spec_values(member.className, selected=member.spec)
        self._update_class_icon_preview(member.className)
        self.gear_var.set(gear_status_display(member.gearStatus))
        self.enchant_var.set(enchant_status_display(member.enchants))
        self._refresh_player_values(member.playerId)
        self._refresh_main_values(member)
        self.character_type_var.set(character_type_display(member.characterType))
        self.raid_role_var.set(raid_role_display(member.raidRole))
        self.note_text.delete("1.0", "end")
        self.note_text.insert("1.0", member.note)
        self.detail_checked_var.set(self._member_last_checked_display(member))
        self.recheck_gear_button.configure(
            state="normal" if member.lifeStatus == "active" else "disabled"
        )
        if member.lifeStatus == "active":
            self.activity_button.config(
                text=tr("checker.mark_inactive"), bg=self.BLUE, activebackground="#465f7c",
            )
            if not self.life_button.winfo_manager():
                self.life_button.pack(fill="x", padx=16, pady=(3, 18))
            self.life_button.config(
                text=tr("checker.mark_dead"), bg=self.RED, activebackground="#873c43",
            )
        elif member.lifeStatus == "inactive":
            self.activity_button.config(
                text=tr("checker.reactivate"), bg=self.GREEN, activebackground="#397e5d",
            )
            if not self.life_button.winfo_manager():
                self.life_button.pack(fill="x", padx=16, pady=(3, 18))
            self.life_button.config(
                text=tr("checker.mark_dead"), bg=self.RED, activebackground="#873c43",
            )
        else:
            self.activity_button.config(
                text=tr("checker.reanimate_dead"), bg=self.RED, activebackground="#873c43",
            )
            self.life_button.pack_forget()
        self.load_portrait(member)
        self.detail_canvas.yview_moveto(0.0)

    def clear_detail(self) -> None:
        self.detail_name_var.set("–")
        self.detail_meta_var.set(tr("checker.choose_character"))
        self.detail_death_var.set("")
        self.race_var.set(tr("common.not_set"))
        self.class_var.set(tr("common.not_set"))
        self._update_spec_values("", selected="")
        self._update_class_icon_preview("")
        self.gear_var.set(gear_status_display(GEAR_VALUES[0]))
        self.enchant_var.set(enchant_status_display(ENCHANT_VALUES[0]))
        self._refresh_player_values(None)
        self._refresh_main_values(None)
        self.character_type_var.set(character_type_display("not_set"))
        self.raid_role_var.set(raid_role_display("not_set"))
        self.note_text.delete("1.0", "end")
        self.detail_checked_var.set(f"{tr('checker.last_checked')}: –")
        self.recheck_gear_button.configure(state="disabled")
        self.portrait_label.configure(image="", text=tr("checker.missing_portrait").replace(" ", "\n"))
        self._portrait_ref = None
        self._portrait_watch_signature = None

    def save_selected_member(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if not member:
            messagebox.showinfo(APP_NAME, tr("checker.select_character"))
            return
        old_gear, old_enchants = member.gearStatus, member.enchants
        class_name = normalize_class_name(self.class_var.get())
        spec = normalize_spec(class_name, self.spec_var.get())
        character_type = character_type_from_display(self.character_type_var.get())
        associated_main_id = self._selected_main_id() if character_type == "twink" else None
        raid_role = raid_role_from_display(self.raid_role_var.get())
        try:
            self.model.assign_character_type(
                member.id, character_type, associated_main_id, raid_role,
            )
        except MainConflictError as conflict:
            if not messagebox.askyesno(
                tr("checker.main_conflict_title"),
                tr("checker.main_conflict", name=conflict.existing_main.name, new_name=member.name),
                parent=self,
            ):
                return
            self.model.assign_character_type(
                member.id, character_type, associated_main_id, raid_role,
                replace_existing_main=True,
            )
        except ValueError as exc:
            messagebox.showwarning(APP_NAME, str(exc), parent=self)
            return
        member.race = race_from_display(self.race_var.get())
        member.className = class_name
        member.spec = spec
        member.classSpec = combine_class_spec(class_name, spec)
        member.gearStatus = gear_status_from_display(self.gear_var.get())
        member.enchants = enchant_status_from_display(self.enchant_var.get())
        member.note = self.note_text.get("1.0", "end-1c").strip()
        if member.gearStatus != old_gear or member.enchants != old_enchants:
            member.lastChecked = today_iso()
        self.model.dirty = True
        self.autosave()
        self.refresh_all()
        self.status_var.set(tr("checker.saved", name=member.name))

    # ---------- Class / Spec / Icons ----------
    def _on_class_changed(self, _event=None) -> None:
        cls = normalize_class_name(self.class_var.get())
        self.class_var.set(cls or tr("common.not_set"))
        self._update_spec_values(cls, selected="")
        self._update_class_icon_preview(cls)

    def _update_spec_values(self, class_name: str, selected: str = "") -> None:
        cls = normalize_class_name(class_name)
        values = [tr("common.not_set")] + (CLASS_SPECS.get(cls, []) if cls else [])
        self.spec_combo.configure(values=values)
        valid = normalize_spec(cls, selected)
        self.spec_var.set(valid or tr("common.not_set"))

    def _make_fallback_icon(self, class_name: str, size: int = 32):
        if not (Image and ImageTk):
            return None
        path = fallback_class_icon_path(class_name)
        if path.exists():
            with Image.open(path) as raw:
                img = raw.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
                return ImageTk.PhotoImage(img)
        return None

    def _load_one_class_icon(self, class_name: str, size: int):
        if not (Image and ImageTk):
            return None
        candidates = [class_icon_path(class_name), fallback_class_icon_path(class_name)]
        for path in candidates:
            if not path.exists():
                continue
            try:
                with Image.open(path) as raw:
                    img = ImageOps.exif_transpose(raw).convert("RGB") if ImageOps else raw.convert("RGB")
                    img = ImageOps.fit(img, (size, size), method=Image.Resampling.LANCZOS) if ImageOps else img.resize((size, size), Image.Resampling.LANCZOS)
                    return ImageTk.PhotoImage(img)
            except Exception:
                continue
        return None

    def _load_class_icons(self) -> None:
        self._class_icon_refs.clear()
        self._class_icon_small_refs.clear()
        for cls in CLASS_NAMES:
            large = self._load_one_class_icon(cls, 36)
            small = self._load_one_class_icon(cls, 28)
            if large is not None:
                self._class_icon_refs[cls] = large
            if small is not None:
                self._class_icon_small_refs[cls] = small
        if getattr(self, "selected_member_id", None):
            member = self.model.find_by_id(self.selected_member_id or "")
            if member:
                self._update_class_icon_preview(member.className)

    def _update_class_icon_preview(self, class_name: str) -> None:
        cls = normalize_class_name(class_name)
        icon = self._class_icon_refs.get(cls)
        self._class_icon_detail_ref = icon
        if icon:
            self.class_icon_label.configure(image=icon, text="", width=36, height=36, highlightthickness=1, highlightbackground=CLASS_COLORS.get(cls, self.BORDER))
        else:
            self.class_icon_label.configure(image="", text="–", width=4, height=2, highlightthickness=0)

    def _start_missing_icon_download(self) -> None:
        if os.environ.get("GGC_DISABLE_ICON_DOWNLOAD") == "1":
            return
        if self._icon_download_thread and self._icon_download_thread.is_alive():
            return
        missing = [cls for cls in CLASS_NAMES if not class_icon_path(cls).exists()]
        if not missing:
            return
        def worker():
            result = download_class_icons(force=False, timeout=8)
            ok = sum(1 for v in result.values() if v in {"cached", "downloaded"})
            downloaded = sum(1 for v in result.values() if v == "downloaded")
            try:
                self.after(0, lambda: self._class_icon_download_finished(ok, downloaded))
            except Exception:
                pass
        self._icon_download_thread = threading.Thread(target=worker, name="ClassIconDownload", daemon=True)
        self._icon_download_thread.start()

    def _class_icon_download_finished(self, ok: int, downloaded: int) -> None:
        self._load_class_icons()
        self.refresh_center()
        if downloaded:
            self.status_var.set(tr("checker.icons_saved", count=downloaded))

    # ---------- Portraits / Grabber ----------
    def _historical_portrait_path(self, member: Member) -> Path:
        return stored_member_portrait_path(self.model.project_path, member.id)

    def _historical_portrait_missing_path(self, member: Member) -> Path:
        return stored_member_portrait_path(self.model.project_path, member.id).with_suffix(".missing")

    def portrait_candidates(self, member: Member) -> Iterable[Path]:
        if self.model.project_path is None:
            return
        yield stored_member_portrait_path(self.model.project_path, member.id)

    def graveyard_portrait_path(self, member: Member) -> Path | None:
        """Resolve a graveyard portrait, falling back to the oval placeholder."""
        for path in self.portrait_candidates(member):
            if path.is_file():
                return path
        if member.lifeStatus == "dead":
            placeholder = app_base_dir() / "assets" / "graveyard" / "portrait_placeholder.png"
            if placeholder.is_file():
                return placeholder
        return None

    def _archive_portrait(self, member: Member) -> Path | None:
        destination = self._historical_portrait_path(member)
        return destination if destination.is_file() else None

    def _portrait_signature(self, member: Member):
        p = next((p for p in self.portrait_candidates(member) if p.exists()), None)
        if not p:
            return None
        try:
            st = p.stat()
            return (str(p.resolve()), st.st_mtime_ns, st.st_size)
        except OSError:
            return (str(p), 0, 0)

    def load_portrait(self, member: Member) -> None:
        path = next((p for p in self.portrait_candidates(member) if p.exists()), None)
        self._portrait_watch_signature = self._portrait_signature(member)
        if not path:
            self.portrait_label.configure(image="", text=tr("checker.portrait_not_found"))
            self._portrait_ref = None
            return
        try:
            if Image and ImageTk:
                with Image.open(path) as raw:
                    img = ImageOps.exif_transpose(raw).convert("RGB") if ImageOps else raw.convert("RGB")
                    if ImageOps:
                        fitted = ImageOps.contain(img, (RIGHT_PORTRAIT_SIZE, RIGHT_PORTRAIT_SIZE), method=Image.Resampling.LANCZOS)
                    else:
                        fitted = img.copy()
                        fitted.thumbnail((RIGHT_PORTRAIT_SIZE, RIGHT_PORTRAIT_SIZE), Image.Resampling.LANCZOS)
                    # Keep a fixed 220x220 display area without cropping non-square source images.
                    canvas = Image.new("RGB", (RIGHT_PORTRAIT_SIZE, RIGHT_PORTRAIT_SIZE), "#0c1015")
                    x = (RIGHT_PORTRAIT_SIZE - fitted.width) // 2
                    y = (RIGHT_PORTRAIT_SIZE - fitted.height) // 2
                    canvas.paste(fitted, (x, y))
                    photo = ImageTk.PhotoImage(canvas)
            else:
                photo = tk.PhotoImage(file=str(path))
                max_dim = max(photo.width(), photo.height())
                if max_dim > RIGHT_PORTRAIT_SIZE:
                    factor = max(1, (max_dim + RIGHT_PORTRAIT_SIZE - 1) // RIGHT_PORTRAIT_SIZE)
                    photo = photo.subsample(factor, factor)
            self._portrait_ref = photo
            self.portrait_label.configure(image=photo, text="")
        except Exception as exc:
            self._portrait_ref = None
            self.portrait_label.configure(image="", text=tr("checker.portrait_load_error", error=exc))

    def _watch_portrait_folder(self) -> None:
        try:
            member = self.model.find_by_id(self.selected_member_id or "")
            if member:
                sig = self._portrait_signature(member)
                if sig != self._portrait_watch_signature:
                    self.load_portrait(member)
                    if self.current_tab == "Friedhof":
                        self.render_graveyard()
                    self.status_var.set(tr("checker.portrait_updated", name=member.name))
        finally:
            self.after(1200, self._watch_portrait_folder)

    def reload_selected_portrait(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if member:
            self._portrait_watch_signature = None
            self.load_portrait(member)
            if self.current_tab == "Friedhof":
                self.render_graveyard()
            self.status_var.set(tr("checker.portrait_reloaded", name=member.name))
        else:
            self.status_var.set(tr("checker.no_character_selected"))

    def open_portrait_folder(self) -> None:
        folder = project_portrait_root(self.model.project_path)
        if folder is None:
            messagebox.showinfo(APP_NAME, tr("checker.project_required"))
            return
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(folder))  # type: ignore[attr-defined]
        except Exception:
            try:
                webbrowser.open(folder.as_uri())
            except Exception as exc:
                messagebox.showerror(APP_NAME, tr("checker.portrait_folder_error", error=exc))

    def _invalidate_armory_session(self) -> None:
        self._armory_session_id = None
        self._armory_result_signature = None
        self._armory_processed_tokens.clear()

    def _armory_results_path(self) -> Path:
        return app_base_dir() / "data" / "runtime" / "armory_character_data.json"

    def _character_cache_path(self) -> Path:
        return character_cache_path(app_base_dir())

    def _apply_character_cache(self) -> dict:
        errors: list[str] = []
        payload = load_character_cache(self._character_cache_path(), on_error=errors.append)
        if errors:
            return {"updated": 0, "ignored": 0, "conflicts": [], "error": errors[0]}
        summary = self.model.apply_character_cache(payload)
        changed = summary["updated"] > 0
        for conflict in summary["conflicts"]:
            field_label = tr("checker.race") if conflict["field"] == "race" else tr("common.class")
            if messagebox.askyesno(
                tr("checker.armory_conflict_title"),
                tr(
                    "checker.armory_conflict",
                    name=conflict["characterName"], field=field_label,
                    current=conflict["current"], incoming=conflict["incoming"],
                ), parent=self,
            ):
                changed = self.model.apply_armory_conflict(conflict) or changed
        if changed:
            self.autosave()
        return summary

    def _watch_armory_results(self) -> None:
        try:
            path = self._armory_results_path()
            if self._armory_session_id and path.exists():
                stat = path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                if signature != self._armory_result_signature:
                    self._armory_result_signature = signature
                    payload = json.loads(path.read_text(encoding="utf-8-sig"))
                    results = payload.get("results") if isinstance(payload, dict) else None
                    if isinstance(results, list):
                        fresh_results = []
                        for result in results:
                            if not isinstance(result, dict):
                                continue
                            token = (
                                str(payload.get("sessionId") or ""),
                                str(result.get("memberId") or result.get("characterName") or ""),
                                str(result.get("retrievedAt") or ""),
                            )
                            if token in self._armory_processed_tokens:
                                continue
                            self._armory_processed_tokens.add(token)
                            fresh_results.append(result)
                        payload = dict(payload)
                        payload["results"] = fresh_results
                    summary = self.model.apply_armory_results(payload, self._armory_session_id)
                    changed = summary["updated"] > 0
                    for conflict in summary["conflicts"]:
                        field_label = tr("checker.race") if conflict["field"] == "race" else tr("common.class")
                        if messagebox.askyesno(
                            tr("checker.armory_conflict_title"),
                            tr(
                                "checker.armory_conflict",
                                name=conflict["characterName"], field=field_label,
                                current=conflict["current"], incoming=conflict["incoming"],
                            ), parent=self,
                        ):
                            changed = self.model.apply_armory_conflict(conflict) or changed
                    if changed:
                        self.autosave()
                        self.refresh_all()
                        self.status_var.set(tr("checker.armory_data_applied", count=summary["updated"]))
        except Exception as exc:
            self.status_var.set(tr("checker.armory_data_error", error=exc))
        finally:
            try:
                self.after(1400, self._watch_armory_results)
            except tk.TclError:
                pass

    def open_portrait_grabber(self) -> None:
        grabber = app_base_dir() / "app" / "GuildPortraitGrabber.py"
        if Image is None:
            messagebox.showerror(APP_NAME, tr("checker.pillow_missing"))
            return
        if not grabber.exists():
            messagebox.showerror(APP_NAME, tr("checker.grabber_missing", path=grabber))
            return
        try:
            if self.model.project_path and self.model.dirty:
                self.model.save(self.model.project_path, backup=True)
            exe = Path(sys.executable)
            if os.name == "nt" and exe.name.casefold() == "python.exe":
                pythonw = exe.with_name("pythonw.exe")
                if pythonw.exists():
                    exe = pythonw
            command = [str(exe), str(grabber)]
            if self.model.project_path:
                command.extend(["--project", str(self.model.project_path.resolve())])
            subprocess.Popen(command, cwd=str(app_base_dir()))
            self.status_var.set(tr("checker.grabber_started"))
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("checker.grabber_error", error=exc))

    # ---------- Aktionen ----------
    def open_armory_selected(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if not member:
            messagebox.showinfo(APP_NAME, tr("checker.select_character"))
            return
        webbrowser.open(build_armory_url(
            member.name, self.model.region, self.model.realm, self.model.game_version
        ))
        self.status_var.set(tr("checker.armory_opened", name=member.name))

    def toggle_activity_selected(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if not member:
            return
        if member.lifeStatus == "dead":
            current_same_name = self.model.find_current_by_name(member.name)
            if current_same_name is not None and current_same_name.id != member.id:
                messagebox.showwarning(
                    APP_NAME,
                    tr("checker.current_incarnation_blocks", name=current_same_name.name),
                )
                return
            if not messagebox.askyesno(
                    tr("checker.reanimate_dead_title"),
                    tr("checker.reanimate_dead_question", name=member.name),
                    parent=self):
                return
            try:
                self.model.set_member_life_status(
                    member.id, "active", allow_dead_reanimation=True,
                )
            except MainConflictError as conflict:
                if not messagebox.askyesno(
                    tr("checker.main_conflict_title"),
                    tr("checker.main_conflict", name=conflict.existing_main.name, new_name=member.name),
                    parent=self,
                ):
                    return
                self.model.set_member_life_status(
                    member.id, "active", replace_existing_main=True,
                    allow_dead_reanimation=True,
                )
            except ValueError as exc:
                messagebox.showwarning(APP_NAME, str(exc), parent=self)
                return
            target_tab = "Gildenliste"
        elif member.lifeStatus == "inactive":
            try:
                self.model.set_member_life_status(member.id, "active")
            except MainConflictError as conflict:
                if not messagebox.askyesno(
                    tr("checker.main_conflict_title"),
                    tr("checker.main_conflict", name=conflict.existing_main.name, new_name=member.name),
                    parent=self,
                ):
                    return
                self.model.set_member_life_status(
                    member.id, "active", replace_existing_main=True,
                )
            except ValueError as exc:
                messagebox.showwarning(APP_NAME, str(exc), parent=self)
                return
            target_tab = "Gildenliste"
        else:
            if not messagebox.askyesno(
                    APP_NAME, tr("checker.mark_inactive_question", name=member.name),
                    parent=self):
                return
            self.model.set_member_life_status(member.id, "inactive")
            target_tab = "Inaktiv"

        self.autosave()
        self.current_tab = target_tab
        self._sync_detail_panel_visibility()
        self._update_tab_styles()
        self.refresh_all(select_first=False)
        self.show_member(member.id)

    def toggle_life_selected(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if not member:
            return
        if member.lifeStatus == "dead":
            # Compatibility entry point for older callers/tests. The actual UI exposes
            # this as the explicitly labelled emergency reanimation action.
            GuildGearCheckerApp.toggle_activity_selected(self)
            return
        if not messagebox.askyesno(
                APP_NAME, tr("checker.mark_dead_question", name=member.name), parent=self):
            return
        try:
            self._archive_portrait(member)
        except Exception as exc:
            messagebox.showerror(
                APP_NAME,
                tr("checker.portrait_archive_error", error=exc),
            )
            return
        self.model.set_member_life_status(member.id, "dead")
        member.deathDate = today_iso()
        target_tab = "Friedhof"
        self.autosave()
        self.current_tab = target_tab
        self._sync_detail_panel_visibility()
        self._update_tab_styles()
        self.refresh_all(select_first=False)
        self.show_member(member.id)
        self.render_graveyard()

    def remove_selected_member(self) -> None:
        member = self.model.find_by_id(self.selected_member_id or "")
        if member is None:
            messagebox.showinfo(APP_NAME, tr("checker.select_character"), parent=self)
            return
        if not messagebox.askyesno(
            tr("checker.remove_member_title"),
            tr("checker.remove_member_question", name=member.name),
            parent=self,
        ):
            return
        removed = self.model.remove_member(member.id)
        self.selected_member_id = None
        self.clear_detail()
        self.refresh_all(select_first=False)
        self.autosave()
        self.status_var.set(tr("checker.member_removed", name=removed.name))

    def add_member_dialog(self) -> None:
        win = tk.Toplevel(self)
        win.title(tr("checker.member_add_title"))
        win.configure(bg=self.PANEL)
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)
        tk.Label(win, text=tr("checker.exact_character_name"), bg=self.PANEL, fg=self.TEXT, font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=(16, 4))
        name_var = tk.StringVar()
        e = tk.Entry(win, textvariable=name_var, bg=self.PANEL_2, fg=self.TEXT, insertbackground=self.TEXT, relief="flat", width=38)
        e.pack(padx=16, ipady=6)
        e.focus_set()
        def add():
            try:
                member = self.model.add_member(name_var.get(), "Manuell")
                self.autosave()
                self.current_tab = "Gildenliste"
                self._update_tab_styles()
                self.refresh_all()
                self.show_member(member.id)
                if self.tree.exists(member.id):
                    self.tree.selection_set(member.id)
                    self.tree.focus(member.id)
                    self.tree.see(member.id)
                win.destroy()
                self.status_var.set(tr("checker.added", name=member.name))
            except ValueError as exc:
                messagebox.showwarning(APP_NAME, str(exc), parent=win)
        self._button(win, tr("checker.add"), add, kind="primary").pack(fill="x", padx=16, pady=16)
        win.bind("<Return>", lambda _e: add())

    def import_csv(self) -> None:
        path = filedialog.askopenfilename(title=tr("checker.select_raid_csv"), filetypes=[(tr("common.csv_files"), "*.csv"), (tr("common.all_files"), "*.*")])
        if not path:
            return
        try:
            names = read_csv_names(Path(path))
            existing_members, new_names, dead_existing = self.model.classify_member_import(names)
            if not new_names:
                msg = tr("checker.import_all_present", count=len(names))
                if dead_existing:
                    msg += "\n\n" + tr("checker.import_dead_remain", count=len(dead_existing))
                messagebox.showinfo(APP_NAME, msg)
                return
            preview = "\n".join(new_names[:18])
            extra = "" if len(new_names) <= 18 else "\n" + tr("checker.import_more", count=len(new_names)-18)
            dead_line = "\n" + tr("checker.import_dead_line", count=len(dead_existing)) if dead_existing else ""
            if not messagebox.askyesno(APP_NAME, tr(
                "checker.import_prompt", total=len(names), existing=len(existing_members),
                dead_line=dead_line, new_count=len(new_names), preview=preview, extra=extra,
            )):
                return
            created = self.model.import_active_members(names, "Warcraft Logs CSV")
            self.autosave()
            self.current_tab = "Gildenliste"
            self._update_tab_styles()
            self.refresh_all(select_first=True)
            self.status_var.set(tr("checker.csv_imported", count=len(created)))
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("checker.import_failed", error=exc))

    # ---------- Projekte ----------
    def _confirm_discard(self) -> bool:
        if not self.model.dirty:
            return True
        return messagebox.askyesno(APP_NAME, tr("checker.discard_changes"))

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self.model.new_empty()
        self._invalidate_armory_session()
        self.selected_member_id = None
        self.current_tab = "Gildenliste"
        self.reset_filters()
        self._update_tab_styles()
        self.clear_detail()
        self.refresh_all(select_first=False)
        path = filedialog.asksaveasfilename(
            title=tr("checker.save_project_title"), defaultextension=".ggc",
            initialfile="Stitches_Gilde.ggc",
            filetypes=[("Guild Gear Checker", "*.ggc")],
        )
        if not path:
            self._refresh_project_label()
            self.status_var.set(tr("checker.new_project_done"))
            return
        try:
            self.model.save(Path(path), backup=False)
            self._refresh_project_label()
            self.status_var.set(tr("checker.project_saved", name=Path(path).name))
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("checker.project_save_error", error=exc))

    def remove_all_characters(self) -> None:
        if not messagebox.askyesno(
            tr("checker.remove_all_title"), tr("checker.remove_all_question"), parent=self,
        ):
            return
        self.model.clear_project()
        self._invalidate_armory_session()
        self.selected_member_id = None
        self.current_tab = "Gildenliste"
        self.reset_filters()
        self._update_tab_styles()
        self.clear_detail()
        self.refresh_all(select_first=False)
        self.autosave()
        self.status_var.set(tr("checker.remove_all_done"))

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        path = filedialog.askopenfilename(title=tr("checker.open_project_title"), filetypes=[("Guild Gear Checker", "*.ggc")])
        if not path:
            return
        try:
            project = Path(path)
            recovery = newer_autosave(project)
            if recovery is not None and messagebox.askyesno(
                    APP_NAME,
                    tr("checker.autosave_recovery_question", name=project.name),
                    parent=self):
                payload = json.loads(recovery.read_text(encoding="utf-8-sig"))
                self.model.load_payload(payload, project)
                self.model.dirty = True
            else:
                self.model.load(project)
            self._invalidate_armory_session()
            cache_summary = self._apply_character_cache()
            self.autosave()
            self.selected_member_id = None
            self.current_tab = "Gildenliste"
            self.reset_filters()
            self._update_tab_styles()
            self.refresh_all(select_first=True)
            if cache_summary.get("error"):
                self.status_var.set(tr("checker.character_cache_error", error=cache_summary["error"]))
            elif cache_summary.get("updated"):
                self.status_var.set(tr(
                    "checker.project_loaded_with_cache",
                    name=Path(path).name, count=cache_summary["updated"],
                ))
            else:
                self.status_var.set(tr("checker.project_loaded", name=Path(path).name))
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("checker.project_load_error", error=exc))

    def save_project(self) -> None:
        if not self.model.project_path:
            self.save_project_as()
            return
        try:
            self.model.save(self.model.project_path, backup=True)
            self.autosave()
            self._refresh_project_label()
            self.status_var.set(tr("checker.project_saved", name=self.model.project_path.name))
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("checker.project_save_error", error=exc))

    def save_project_as(self) -> None:
        initial = self.model.project_path.name if self.model.project_path else "Stitches_Gilde.ggc"
        path = filedialog.asksaveasfilename(title=tr("checker.save_project_title"), defaultextension=".ggc", initialfile=initial, filetypes=[("Guild Gear Checker", "*.ggc")])
        if not path:
            return
        try:
            old_path = self.model.project_path
            target = Path(path)
            if old_path is not None and old_path.resolve() != target.resolve():
                copy_project_portraits(old_path, target)
            self.model.save(target, backup=True)
            self.autosave()
            self._refresh_project_label()
            self.status_var.set(tr("checker.project_saved", name=Path(path).name))
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("checker.project_save_error", error=exc))

    def export_project(self) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        base = self.model.project_path.stem if self.model.project_path else "Stitches_Gilde"
        suggested = f"{base}_Export_{stamp}.ggc"
        path = filedialog.asksaveasfilename(title=tr("checker.export_project_title"), defaultextension=".ggc", initialfile=suggested, filetypes=[("Guild Gear Checker", "*.ggc")])
        if not path:
            return
        old_path = self.model.project_path
        old_dirty = self.model.dirty
        try:
            target = Path(path)
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_text(json.dumps(self.model.to_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, target)
            self.status_var.set(tr("checker.export_created", name=target.name))
            messagebox.showinfo(APP_NAME, tr("checker.export_success"))
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("checker.export_error", error=exc))
        finally:
            self.model.project_path = old_path
            self.model.dirty = old_dirty

    def import_project_with_portraits(self) -> None:
        source = filedialog.askopenfilename(
            title=tr("checker.package_import"), filetypes=[(tr("checker.package_files"), "*.zip")],
        )
        if not source:
            return
        target = filedialog.asksaveasfilename(
            title=tr("checker.save_project_title"), defaultextension=".ggc",
            initialfile=f"{Path(source).stem}.ggc",
            filetypes=[("Guild Gear Checker", "*.ggc")],
        )
        if not target:
            return
        try:
            summary = import_project_package(Path(source), Path(target))
            self.model.load(summary.project_path)
            self._invalidate_armory_session()
            self.selected_member_id = None
            self.current_tab = "Gildenliste"
            self.reset_filters()
            self._update_tab_styles()
            self.refresh_all(select_first=True)
            self._refresh_project_label()
            self.status_var.set(tr("checker.package_imported", name=summary.project_path.name))
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("checker.package_import_failed", error=exc))

    def export_project_with_portraits(self) -> None:
        suggested = project_package_default_filename(self.model.project_path)
        path = filedialog.asksaveasfilename(
            title=tr("checker.package_export_title"),
            defaultextension=".zip",
            initialfile=suggested,
            filetypes=[(tr("checker.package_files"), "*.zip")],
        )
        if not path:
            return
        old_path = self.model.project_path
        old_dirty = self.model.dirty
        try:
            summary = create_project_package(self.model, Path(path))
            self.status_var.set(tr("checker.package_exported", path=summary.target))
            messagebox.showinfo(
                tr("checker.package_export_title"),
                tr(
                    "checker.package_export_success",
                    path=summary.target,
                    portraits=summary.portrait_count,
                    historical=summary.historical_portrait_count,
                    markers=summary.missing_marker_count,
                    missing=summary.missing_portrait_count,
                ),
                parent=self,
            )
        except Exception as exc:
            stage = exc.stage if isinstance(exc, ProjectPackageError) else "zip"
            detail_key = {
                "project": "checker.package_project_error",
                "manifest": "checker.package_manifest_error",
                "zip": "checker.package_zip_error",
            }.get(stage, "checker.package_zip_error")
            detail = tr(detail_key, error=exc)
            messagebox.showerror(
                tr("checker.package_export_title"),
                tr("checker.package_export_failed", error=detail),
                parent=self,
            )
        finally:
            self.model.project_path = old_path
            self.model.dirty = old_dirty

    def _refresh_project_label(self) -> None:
        if self.model.project_path:
            self.project_var.set(tr(
                "checker.project_label", name=self.model.project_path.name,
                dirty=tr("checker.dirty_suffix") if self.model.dirty else "",
            ))
        else:
            self.project_var.set(tr("checker.no_external_project"))

    def on_close(self) -> None:
        self.autosave()
        if self.state() == "normal":
            update_suite_settings(self._suite_settings_path, checker_geometry=self.geometry())
        self.destroy()


def run_self_tests() -> None:
    assert APP_VERSION == "0.11.3"
    assert build_armory_url("Ánníe").endswith("/%C3%81nn%C3%ADe?game_version=classic1x")
    assert build_armory_url("Schlübbeer").endswith("/Schl%C3%BCbbeer?game_version=classic1x")
    assert norm_name(" Bífi ") == norm_name("bífi")
    assert norm_name("Bífi") != norm_name("Bifibifi")
    assert sanitize_filename('A:b*?') == "A_b__"
    assert CLASS_NAMES == ["Druid", "Hunter", "Mage", "Paladin", "Priest", "Rogue", "Shaman", "Warlock", "Warrior"]
    assert CLASS_SPECS["Warrior"] == ["Arms", "Fury", "Protection"]
    assert normalize_class_name("wArRiOr") == "Warrior"
    assert normalize_spec("Warrior", "fury") == "Fury"
    assert normalize_spec("Warrior", "Holy") == ""
    assert combine_class_spec("Priest", "Holy") == "Priest / Holy"
    assert parse_legacy_class_spec("Warrior / Fury") == ("Warrior", "Fury")
    assert parse_legacy_class_spec("Mage - Frost") == ("Mage", "Frost")
    assert class_icon_folder().name == "classes"
    assert all(CLASS_ICON_URLS[c].endswith(f"classicon_{c.lower()}.jpg") for c in CLASS_NAMES)
    assert all(fallback_class_icon_path(c).exists() for c in CLASS_NAMES)

    csv_text = 'Name,Amount\nAba,1\n"Burgûs",2\nAba,3\nÁnníe,4\n'
    assert detect_csv_names(csv_text) == ["Aba", "Burgûs", "Ánníe"]
    csv_semicolon = "Name;Amount\nSchlübbeer;1\nJanos;2\n"
    assert detect_csv_names(csv_semicolon) == ["Schlübbeer", "Janos"]

    model = GuildModel()
    model.new_seed()
    assert len(model.members) == 20
    assert model.find_by_name("ÁNNÍE") is not None
    assert model.find_by_name("Bifibifi") is None
    m = model.add_member("Bifibifi", "Test")
    m.gearStatus = "Pre-BiS"
    assert member_matches_tab(m, "Handlungsbedarf")
    assert member_matches_tab(m, "Gildenliste")
    assert not member_matches_tab(m, "Friedhof")
    m.lifeStatus = "dead"
    m.deathDate = today_iso()
    assert member_matches_tab(m, "Friedhof")
    assert not member_matches_tab(m, "Gildenliste")
    assert not member_matches_tab(m, "Handlungsbedarf")

    u = model.find_by_name("Aba")
    assert u is not None and member_matches_tab(u, "Ungeprüft")
    u.className = "Warrior"; u.spec = "Fury"; u.classSpec = combine_class_spec(u.className, u.spec)
    assert u.classSpec == "Warrior / Fury"
    payload = model.to_payload()
    model2 = GuildModel(); model2.load_payload(payload)
    assert len(model2.members) == 21
    assert model2.find_by_name("Bifibifi").lifeStatus == "dead"
    assert model2.find_by_name("Aba").className == "Warrior"
    assert model2.find_by_name("Aba").spec == "Fury"
    legacy = {"members": [{"id": "x", "name": "Legacy", "classSpec": "Priest / Shadow"}]}
    legacy_model = GuildModel(); legacy_model.load_payload(legacy)
    assert legacy_model.find_by_name("Legacy").className == "Priest"
    assert legacy_model.find_by_name("Legacy").spec == "Shadow"
    legacy_with_class = {"members": [{
        "id": "m0041", "name": "Legacy2", "className": "Warrior",
        "classSpec": "Warrior / Fury",
    }]}
    legacy_model.load_payload(legacy_with_class)
    assert legacy_model.find_by_name("Legacy2").spec == "Fury"

    incarnations = GuildModel()
    incarnations.load_payload({
        "region": "US", "realm": "defias-pillager", "gameVersion": "classic-era-test",
        "members": [
            {"id": "m0042", "name": "Janos", "lifeStatus": "dead"},
            {"id": "m0087", "name": "Janos", "lifeStatus": "dead"},
            {"id": "m0113", "name": "Janos", "lifeStatus": "active"},
        ],
    })
    assert len(incarnations.members) == 3
    assert incarnations.next_id > 113
    assert incarnations.find_by_name("JANOS").id == "m0113"
    assert incarnations.to_payload()["realm"] == "defias-pillager"
    try:
        incarnations.load_payload({"formatVersion": PROJECT_FORMAT_VERSION + 1, "members": []})
        raise AssertionError("Zukünftige formatVersion wurde akzeptiert")
    except ValueError:
        pass
    assert len(incarnations.members) == 3

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "test.ggc"
        model.save(p, backup=True)
        assert p.exists()
        model.members[0].note = "Testnote"
        model.save(p, backup=True)
        assert p.parent.joinpath("backups", "test_backup.ggc").exists()
        model3 = GuildModel(); model3.load(p)
        assert model3.members[0].note == "Testnote"

        assert shared_portrait_folder(p) == p.parent / "portraits"
    assert RIGHT_PORTRAIT_SIZE == 220
    print("SELF-TEST OK")


def main() -> None:
    if "--self-test" in sys.argv:
        run_self_tests()
        return
    app = GuildGearCheckerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
