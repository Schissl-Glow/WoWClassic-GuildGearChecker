# -*- coding: utf-8 -*-
"""Small shared translation service for the Guild Gear Checker suite."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

SUPPORTED_LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "de"

GRAVESTONE_CATEGORY_KEYS = {
    "Menschen": "humans",
    "Zwerge": "dwarves",
    "Elfen": "elves",
    "Gnome": "gnomes",
    "Zauberer": "mage",
    "Spezial": "special",
}

RACE_KEYS = {
    "Human": "human",
    "Dwarf": "dwarf",
    "Night Elf": "night_elf",
    "Gnome": "gnome",
    "Orc": "orc",
    "Undead": "undead",
    "Tauren": "tauren",
    "Troll": "troll",
}


def suite_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    here = Path(__file__).resolve().parent
    return here.parent if here.name.casefold() == "app" else here


def default_settings_path() -> Path:
    return suite_root() / "config" / "suite_settings.json"


def default_locales_dir() -> Path:
    return Path(__file__).resolve().parent / "locales"


class Translator:
    def __init__(self, settings_path: Path | None = None,
                 locales_dir: Path | None = None) -> None:
        self.settings_path = Path(settings_path) if settings_path else default_settings_path()
        self.locales_dir = Path(locales_dir) if locales_dir else default_locales_dir()
        self._catalogs: dict[str, dict[str, Any]] = {}
        self.language = self._load_language()

    def _load_language(self) -> str:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            language = str(data.get("language") or "").strip().casefold()
            if language in SUPPORTED_LANGUAGES:
                return language
        except (OSError, ValueError, TypeError):
            pass
        return DEFAULT_LANGUAGE

    def _catalog(self, language: str) -> dict[str, Any]:
        if language not in self._catalogs:
            path = self.locales_dir / f"{language}.json"
            self._catalogs[language] = json.loads(path.read_text(encoding="utf-8"))
        return self._catalogs[language]

    def keys(self, language: str) -> set[str]:
        result: set[str] = set()

        def visit(value: Any, prefix: str = "") -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    visit(child, f"{prefix}.{key}" if prefix else key)
            else:
                result.add(prefix)

        visit(self._catalog(language))
        return result

    def translate(self, key: str, **values: object) -> str:
        current: Any = self._catalog(self.language)
        try:
            for part in key.split("."):
                current = current[part]
            text = str(current)
        except (KeyError, TypeError):
            text = key
        if not values:
            return text
        try:
            return text.format(**values)
        except (KeyError, ValueError):
            return text

    def set_language(self, language: str) -> None:
        language = str(language or "").strip().casefold()
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")
        data: dict[str, Any] = {}
        try:
            loaded = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except (OSError, ValueError, TypeError):
            pass
        data["language"] = language
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.settings_path.with_suffix(self.settings_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_path, self.settings_path)
        self.language = language


_translator = Translator()


def tr(key: str, **values: object) -> str:
    return _translator.translate(key, **values)


def get_language() -> str:
    return _translator.language


def set_language(language: str) -> None:
    _translator.set_language(language)


def language_display_values() -> tuple[str, str]:
    return (tr("language.german"), tr("language.english"))


def language_from_display(value: str) -> str:
    folded = str(value or "").casefold()
    for language, key in (("de", "language.german"), ("en", "language.english")):
        for catalog_language in SUPPORTED_LANGUAGES:
            old_language = _translator.language
            try:
                _translator.language = catalog_language
                if tr(key).casefold() == folded:
                    return language
            finally:
                _translator.language = old_language
    return get_language()


def race_display(value: str | None) -> str:
    canonical = next(
        (race for race in RACE_KEYS if race.casefold() == str(value or "").strip().casefold()),
        None,
    )
    return tr(f"race.{RACE_KEYS[canonical]}") if canonical else tr("common.not_set")


def race_display_values() -> tuple[str, ...]:
    return tuple(race_display(race) for race in RACE_KEYS)


def race_from_display(value: str) -> str | None:
    folded = str(value or "").strip().casefold()
    for canonical, key in RACE_KEYS.items():
        if folded == canonical.casefold():
            return canonical
        for language in SUPPORTED_LANGUAGES:
            old_language = _translator.language
            try:
                _translator.language = language
                if tr(f"race.{key}").casefold() == folded:
                    return canonical
            finally:
                _translator.language = old_language
    return None

def gravestone_category_display(value: str | None) -> str:
    canonical = next(
        (category for category in GRAVESTONE_CATEGORY_KEYS
         if category.casefold() == str(value or "").strip().casefold()),
        None,
    )
    if canonical is None:
        return tr("gravestone_category.none")
    return tr(f"gravestone_category.{GRAVESTONE_CATEGORY_KEYS[canonical]}")


def gravestone_category_display_values() -> tuple[str, ...]:
    return tuple(gravestone_category_display(category) for category in GRAVESTONE_CATEGORY_KEYS)


def gravestone_category_from_display(value: str | None) -> str | None:
    folded = str(value or "").strip().casefold()
    if not folded:
        return None
    for canonical, key in GRAVESTONE_CATEGORY_KEYS.items():
        if folded == canonical.casefold():
            return canonical
        for language in SUPPORTED_LANGUAGES:
            old_language = _translator.language
            try:
                _translator.language = language
                if tr(f"gravestone_category.{key}").casefold() == folded:
                    return canonical
            finally:
                _translator.language = old_language
    return None
