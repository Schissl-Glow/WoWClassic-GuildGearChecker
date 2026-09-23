# -*- coding: utf-8 -*-
"""Regression tests for the shared German/English translation service."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest


repo_root = None
i18n = None
checker = None
grabber = None


class I18nTests(unittest.TestCase):
    def test_german_and_english_catalogs_are_available_and_complete(self):
        service = i18n.Translator()
        de_keys = service.keys("de")
        en_keys = service.keys("en")
        self.assertTrue(de_keys)
        self.assertEqual(de_keys, en_keys)
        self.assertEqual(service._catalog("de")["tabs"]["graveyard"], "Friedhof")
        self.assertEqual(service._catalog("en")["tabs"]["graveyard"], "Graveyard")
        self.assertEqual(service._catalog("de")["tabs"]["roster"], "Roster")
        self.assertEqual(service._catalog("en")["tabs"]["roster"], "Roster")
        self.assertEqual(service._catalog("de")["tabs"]["management"], "Verwaltung")
        self.assertEqual(service._catalog("en")["tabs"]["management"], "Management")
        self.assertEqual(service._catalog("de")["gravestone_category"]["mage"], "Zauberer")
        self.assertEqual(service._catalog("en")["gravestone_category"]["mage"], "Mage")
        self.assertEqual(service._catalog("de")["common"]["spec"], "Spec")
        self.assertEqual(service._catalog("en")["common"]["spec"], "Spec")
        self.assertEqual(service._catalog("de")["character_type"]["twink"], "Twink")
        self.assertEqual(service._catalog("en")["character_type"]["twink"], "Twink")
        self.assertEqual(service._catalog("de")["raids"]["attendance"], "Teilnahme")
        self.assertEqual(service._catalog("en")["raids"]["attendance"], "Attendance")

    def test_every_literal_translation_key_used_by_apps_exists(self):
        service = i18n.Translator()
        used = set()
        for filename in ("GuildGearChecker.py", "GuildGearCheckerQt.py", "GuildPortraitGrabber.py"):
            source = (repo_root / "app" / filename).read_text(encoding="utf-8")
            literal_keys = re.findall(r"\btr\([\"']([^\"']+)[\"']", source)
            # A key ending in a dot is a dynamic prefix, e.g. tr("life." + status).
            used.update(key for key in literal_keys if not key.endswith("."))
        for relative in (
            "tools/gravestone_review/gravestone_review_tool.py",
            "tools/gravestone_review/gravestone_alpha_editor.py",
        ):
            source = (repo_root / relative).read_text(encoding="utf-8")
            literal_keys = re.findall(r"\btr\([\"']([^\"']+)[\"']", source)
            used.update(key for key in literal_keys if not key.endswith("."))
        de_missing = used - service.keys("de")
        en_missing = used - service.keys("en")
        self.assertFalse(de_missing, f"Fehlende DE-Schlüssel: {sorted(de_missing)}")
        self.assertFalse(en_missing, f"Fehlende EN-Schlüssel: {sorted(en_missing)}")

    def test_v088_project_handoff_and_editor_terms_are_bilingual(self):
        service = i18n.Translator()
        de = service._catalog("de")
        en = service._catalog("en")
        self.assertEqual(de["checker"]["package_import"], "Projekt-ZIP importieren")
        self.assertEqual(en["checker"]["package_import"], "Import Project ZIP")
        self.assertEqual(de["grabber"]["save_guild_list"], "Gildenliste speichern")
        self.assertEqual(en["grabber"]["save_guild_list"], "Save Guild Roster")
        self.assertEqual(de["raids"]["open_warcraft_logs"], "Warcraft Logs öffnen")
        self.assertEqual(en["raids"]["open_warcraft_logs"], "Open Warcraft Logs")
        self.assertEqual(de["alpha_editor"]["apply_save"], "Anwenden / Speichern")
        self.assertEqual(en["alpha_editor"]["apply_save"], "Apply / Save")

    def test_language_setting_survives_new_service_instance(self):
        with tempfile.TemporaryDirectory(prefix="ggc-i18n-") as temp:
            settings = Path(temp) / "config" / "suite_settings.json"
            first = i18n.Translator(settings_path=settings)
            first.set_language("en")
            second = i18n.Translator(settings_path=settings)
            self.assertEqual(second.language, "en")
            self.assertEqual(second.translate("common.save"), "Save")
            second.set_language("de")
            self.assertEqual(i18n.Translator(settings_path=settings).language, "de")

    def test_project_payload_is_independent_from_language(self):
        model = checker.GuildModel()
        model.new_seed()
        before = model.to_payload()
        with tempfile.TemporaryDirectory(prefix="ggc-i18n-") as temp:
            service = i18n.Translator(settings_path=Path(temp) / "suite_settings.json")
            service.set_language("en")
            after = model.to_payload()
        for volatile in ("savedAt",):
            before.pop(volatile, None)
            after.pop(volatile, None)
        self.assertEqual(before, after)

    def test_legacy_german_project_loads_while_english_is_selected(self):
        with tempfile.TemporaryDirectory(prefix="ggc-i18n-") as temp:
            service = i18n.Translator(settings_path=Path(temp) / "suite_settings.json")
            service.set_language("en")
            model = checker.GuildModel()
            model.load_payload({"formatVersion": 1, "members": [{
                "id": "m0042", "name": "Janos", "gearStatus": "Pre-BiS",
                "enchants": "Fehlt", "raidStatus": "Bereit", "lifeStatus": "active"
            }]})
        self.assertEqual(checker.gear_status_key(model.members[0].gearStatus), "pre_bis")
        self.assertEqual(checker.enchant_status_key(model.members[0].enchants), "not_checked")
        self.assertEqual(model.members[0].raidStatus, "Bereit")

    def test_legacy_statuses_display_in_english_without_changing_storage(self):
        service = i18n.Translator()
        service.language = "en"
        original_tr = checker.tr
        checker.tr = service.translate
        try:
            self.assertEqual(checker.gear_status_display("Pre-BiS"), "Pre-BiS")
            self.assertEqual(checker.enchant_status_display("Fehlt"), "Missing")
            self.assertEqual(checker.gear_status_from_display("Pre-BiS"), "Pre-BiS")
            self.assertEqual(checker.enchant_status_from_display("Missing"), "Fehlt")
            self.assertEqual(checker.raid_status_display("Bereit"), "Ready")
            self.assertEqual(checker.raid_status_from_display("Ready"), "Bereit")
        finally:
            checker.tr = original_tr


    def test_placeholders_match_between_catalogs(self):
        service = i18n.Translator()
        de = service._catalog("de")
        en = service._catalog("en")

        def flatten(value, prefix=""):
            result = {}
            if isinstance(value, dict):
                for key, child in value.items():
                    result.update(flatten(child, f"{prefix}.{key}" if prefix else key))
            else:
                result[prefix] = str(value)
            return result

        placeholder_re = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?:[^}]*)\}")
        de_flat = flatten(de)
        en_flat = flatten(en)
        for key in sorted(de_flat):
            self.assertEqual(
                set(placeholder_re.findall(de_flat[key])),
                set(placeholder_re.findall(en_flat[key])),
                key,
            )

    def test_gravestone_category_display_is_localized_without_changing_storage(self):
        service = i18n.Translator()
        service.language = "en"
        original = i18n._translator.language
        try:
            i18n._translator.language = "en"
            self.assertEqual(i18n.gravestone_category_display("Zauberer"), "Mage")
            self.assertEqual(i18n.gravestone_category_from_display("Mage"), "Zauberer")
        finally:
            i18n._translator.language = original

    def test_protected_grabber_messages_are_localized_at_ui_boundary(self):
        service = i18n.Translator()
        service.language = "en"
        original_tr = grabber.tr
        grabber.tr = service.translate
        try:
            self.assertEqual(grabber.localize_worker_message("Oeffne Janos …"), "Opening Janos …")
            self.assertEqual(
                grabber.localize_worker_message("Viewer-Screenshot war leer; nutze Viewport-Fallback …"),
                "Viewer screenshot was empty; using viewport fallback …",
            )
        finally:
            grabber.tr = original_tr


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    global repo_root, i18n, checker, grabber
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    i18n = load_module("ggc_i18n_target", repo_root / "app" / "i18n.py")
    checker = load_module("ggc_i18n_checker", repo_root / "app" / "GuildGearChecker.py")
    grabber = load_module("ggc_i18n_grabber", repo_root / "app" / "GuildPortraitGrabber.py")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(I18nTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
