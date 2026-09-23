# -*- coding: utf-8 -*-
"""Regression tests for localized Armory extraction and browser stability."""
from __future__ import annotations

import argparse
import ast
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


grabber = None
checker = None
i18n = None
REPO_ROOT = None
RUN_PLAYWRIGHT_PERSISTENCE = False


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class LocalizedExtractionTests(unittest.TestCase):
    def fixture(self, name: str) -> str:
        return (REPO_ROOT / "tests" / "fixtures" / "armory" / name).read_text(encoding="utf-8")

    def assert_extracted(self, text: str, race: str | None, class_name: str | None) -> None:
        self.assertEqual(
            grabber.extract_armory_character_data(text),
            {"race": race, "className": class_name},
        )

    def test_janos_english_and_german(self):
        for fixture in ("janos-en.html", "janos-de.html"):
            with self.subTest(fixture=fixture):
                self.assert_extracted(self.fixture(fixture), "Night Elf", "Warrior")

    def test_level_header_human_warrior_is_authoritative(self):
        self.assert_extracted(
            "Level 60 Human Warrior from <Bierstube> Mensch Magier navigation",
            "Human",
            "Warrior",
        )

    def test_german_race_aliases_are_canonical(self):
        expected = {
            "Mensch": "Human", "Zwerg": "Dwarf", "Nachtelf": "Night Elf",
            "Nachtelfe": "Night Elf", "Gnom": "Gnome", "Orc": "Orc",
            "Ork": "Orc", "Untoter": "Undead", "Untote": "Undead",
            "Tauren": "Tauren", "Troll": "Troll",
        }
        for visible, canonical in expected.items():
            with self.subTest(visible=visible):
                self.assert_extracted(f"Rasse: {visible}", canonical, None)

    def test_german_class_aliases_are_canonical(self):
        expected = {
            "Druide": "Druid", "Jäger": "Hunter", "Jaeger": "Hunter",
            "Magier": "Mage", "Paladin": "Paladin", "Priester": "Priest",
            "Schurke": "Rogue", "Schamane": "Shaman",
            "Hexenmeister": "Warlock", "Krieger": "Warrior",
        }
        for visible, canonical in expected.items():
            with self.subTest(visible=visible):
                self.assert_extracted(f"Klasse: {visible}", None, canonical)

    def test_separate_partial_and_mixed_values(self):
        self.assert_extracted(self.fixture("separate-fields-de.html"), "Night Elf", "Priest")
        self.assert_extracted(self.fixture("race-only-de.html"), "Human", None)
        self.assert_extracted(self.fixture("class-only-de.html"), None, "Warlock")
        self.assert_extracted("Level 60 Nachtelf Warrior", "Night Elf", "Warrior")
        self.assert_extracted("Level 60 Night Elf Krieger", "Night Elf", "Warrior")

    def test_structured_values_are_normalized_recursively(self):
        content = {"props": {"character": {"race": "Nachtelf", "className": "Krieger"}}}
        self.assert_extracted(content, "Night Elf", "Warrior")
        content["navigation"] = {"race": "Zwerg", "className": "Magier"}
        self.assert_extracted(content, None, None)

    def test_explicit_structured_field_wins_over_unrelated_visible_navigation(self):
        content = {"race": "Nachtelf", "className": "Krieger", "navigation": "Mensch Magier"}
        self.assert_extracted(content, "Night Elf", "Warrior")

    def test_exact_matching_and_ambiguity(self):
        self.assert_extracted("An orchestra and a magical rogueish tale", None, None)
        self.assert_extracted("Mensch Zwerg Krieger Magier", None, None)

    def test_partial_merge_preserves_existing_values(self):
        record = {"race": "Night Elf", "className": None}
        grabber.merge_armory_data(record, {"race": None, "className": "Krieger"})
        self.assertEqual(record, {"race": "Night Elf", "className": "Warrior"})
        grabber.merge_armory_data(record, {"race": None, "className": None})
        self.assertEqual(record, {"race": "Night Elf", "className": "Warrior"})


class RaceI18nTests(unittest.TestCase):
    def set_language_for_test(self, language: str) -> None:
        i18n._translator.language = language

    def test_internal_value_and_localized_display(self):
        self.set_language_for_test("de")
        expected_de = {
            "Human": "Mensch", "Dwarf": "Zwerg", "Night Elf": "Nachtelf",
            "Gnome": "Gnom", "Orc": "Orc", "Undead": "Untoter",
            "Tauren": "Tauren", "Troll": "Troll",
        }
        for canonical, visible in expected_de.items():
            with self.subTest(canonical=canonical):
                self.assertEqual(i18n.race_display(canonical), visible)
                self.assertEqual(i18n.race_from_display(visible), canonical)
        self.set_language_for_test("en")
        for canonical in expected_de:
            self.assertEqual(i18n.race_display(canonical), canonical)

    def test_language_switch_does_not_change_project_data(self):
        model = checker.GuildModel()
        member = model.add_member("Janos")
        member.race = "Night Elf"
        before = model.to_payload()
        self.set_language_for_test("de")
        self.assertEqual(i18n.race_display(member.race), "Nachtelf")
        self.set_language_for_test("en")
        self.assertEqual(i18n.race_display(member.race), "Night Elf")
        self.assertEqual(model.to_payload(), before)

    def test_save_in_each_language_loads_canonical_value_in_the_other(self):
        for save_language, load_language in (("de", "en"), ("en", "de")):
            with self.subTest(save=save_language, load=load_language), \
                 tempfile.TemporaryDirectory(prefix="ggc-race-i18n-") as temp:
                self.set_language_for_test(save_language)
                model = checker.GuildModel()
                member = model.add_member("Janos")
                member.race = "Night Elf"
                path = Path(temp) / "race.ggc"
                model.save(path)
                self.set_language_for_test(load_language)
                loaded = checker.GuildModel()
                loaded.load(path)
                self.assertEqual(loaded.members[0].race, "Night Elf")
                self.assertEqual(i18n.race_display(loaded.members[0].race),
                                 "Night Elf" if load_language == "en" else "Nachtelf")


class CharacterReadyTests(unittest.TestCase):
    def test_protection_fixture_is_not_character_content(self):
        text = (REPO_ROOT / "tests" / "fixtures" / "armory" / "protection-401.html").read_text(encoding="utf-8")
        self.assertTrue(grabber.is_armory_protection_content(
            "https://classicwowarmory.com/character/EU/stitches/Janos", "401 Unauthorized", text,
        ))

    def test_character_url_requires_exact_name(self):
        base = "https://classicwowarmory.com/character/EU/stitches/"
        self.assertTrue(grabber.url_matches_character_name(base + "Janos?game_version=classic1x", "Janos"))
        self.assertFalse(grabber.url_matches_character_name(base + "Janosz", "Janos"))

    def test_protection_page_can_transition_to_ready(self):
        worker = grabber.BrowserWorker(__import__("queue").Queue())
        worker._page = SimpleNamespace(is_closed=lambda: False, wait_for_timeout=lambda _ms: None)
        worker._page_character_ready = Mock(side_effect=[(False, True), (True, False)])
        worker._wait_for_character_content("Janos", timeout_seconds=1)
        self.assertEqual(worker._page_character_ready.call_count, 2)

    def test_protection_timeout_has_dedicated_event_not_false_extraction_error(self):
        worker = grabber.BrowserWorker(__import__("queue").Queue())
        worker._page = SimpleNamespace(locator=lambda *_args: object())
        worker._wait_for_character_content = Mock(
            side_effect=grabber.ArmoryProtectionTimeout("protection timeout")
        )
        self.assertIsNone(worker._attempt_armory_extraction("Janos", "m0113", "single"))
        event = worker.events.get_nowait()
        self.assertEqual(event["type"], "armory_data_wait_timeout")
        self.assertTrue(worker.events.empty())

    def test_ready_check_uses_supported_page_title_signature(self):
        body = SimpleNamespace(inner_text=lambda timeout=None: "Janos Level 60 Nachtelf Krieger")
        semantic = SimpleNamespace(count=lambda: 1)
        page = SimpleNamespace(
            url="https://classicwowarmory.com/character/EU/stitches/Janos?game_version=classic1x",
            is_closed=lambda: False,
            title=lambda: "Janos - Stitches",
            locator=lambda selector: body if selector == "body" else semantic,
        )
        worker = grabber.BrowserWorker(__import__("queue").Queue())
        worker._page = page
        worker._extract_armory_character_data = Mock(
            return_value={"race": "Night Elf", "className": "Warrior"}
        )
        self.assertEqual(worker._page_character_ready("Janos"), (True, False))


class BrowserRecoveryTests(unittest.TestCase):
    def test_worker_emit_preserves_event_type_and_payload(self):
        events = __import__("queue").Queue()
        worker = grabber.BrowserWorker(events)

        worker.emit(
            "portrait_saved",
            name="Janos",
            path="portraits/Janos.png",
            method="playwright",
        )

        self.assertEqual(
            events.get_nowait(),
            {
                "type": "portrait_saved",
                "name": "Janos",
                "path": "portraits/Janos.png",
                "method": "playwright",
            },
        )

    def worker(self):
        worker = grabber.BrowserWorker(__import__("queue").Queue())
        worker._ensure_capture_browser = Mock()
        worker._close_browser = Mock()
        return worker

    def test_target_closed_retries_exactly_once(self):
        worker = self.worker()
        operation = Mock(side_effect=[RuntimeError("TargetClosedError: page closed"), "ok"])
        self.assertEqual(worker._run_with_browser_recovery(operation, "playwright", "msedge"), "ok")
        self.assertEqual(operation.call_count, 2)
        worker._close_browser.assert_called_once()

    def test_second_target_closed_error_is_not_retried_again(self):
        worker = self.worker()
        operation = Mock(side_effect=RuntimeError("TargetClosedError: page closed"))
        with self.assertRaises(RuntimeError):
            worker._run_with_browser_recovery(operation, "playwright", "msedge")
        self.assertEqual(operation.call_count, 2)
        self.assertEqual(worker._close_browser.call_count, 2)

    def test_aborted_and_detached_frame_are_recoverable(self):
        for message in ("net::ERR_ABORTED", "maybe frame was detached"):
            with self.subTest(message=message):
                worker = self.worker()
                operation = Mock(side_effect=[RuntimeError(message), "ok"])
                self.assertEqual(worker._run_with_browser_recovery(operation, "playwright", "msedge"), "ok")
                self.assertEqual(operation.call_count, 2)

    def test_stop_prevents_start_and_retry(self):
        worker = self.worker()
        worker.request_batch_cancel()
        operation = Mock()
        with self.assertRaises(grabber.BrowserBatchStopped):
            worker._run_with_browser_recovery(operation, "playwright", "msedge")
        operation.assert_not_called()
        worker._ensure_capture_browser.assert_not_called()

        worker._batch_cancel.clear()
        operation = Mock(side_effect=RuntimeError("TargetClosedError"))
        worker._close_browser.side_effect = lambda: worker.request_batch_cancel()
        with self.assertRaises(RuntimeError):
            worker._run_with_browser_recovery(operation, "playwright", "msedge")
        self.assertEqual(operation.call_count, 1)

    def test_next_character_can_start_after_exhausted_retry(self):
        worker = self.worker()
        failing = Mock(side_effect=RuntimeError("net::ERR_ABORTED"))
        with self.assertRaises(RuntimeError):
            worker._run_with_browser_recovery(failing, "playwright", "msedge")
        succeeding = Mock(return_value="next-ok")
        self.assertEqual(worker._run_with_browser_recovery(succeeding, "playwright", "msedge"), "next-ok")

    def test_closed_page_and_disconnected_browser_are_unhealthy(self):
        worker = grabber.BrowserWorker(__import__("queue").Queue())
        worker._browser = SimpleNamespace(is_connected=lambda: False)
        self.assertFalse(worker._browser_is_healthy())

    def test_portrait_batch_recovers_per_character_without_error_storm(self):
        worker = self.worker()
        worker._current_page_is_character = Mock(return_value=True)
        worker._attempt_armory_extraction = Mock(return_value=None)
        worker._raw_screenshot = Mock(side_effect=[
            RuntimeError("net::ERR_ABORTED"), RuntimeError("maybe frame was detached"),
            (Path("source.png"), "mock"),
        ])
        with tempfile.TemporaryDirectory(prefix="ggc-recovery-batch-") as temp, \
             patch.object(grabber, "crop_portrait"):
            worker._capture_all(
                ["First", "Second"], "EU", "stitches", "classic1x", "msedge", 0,
                temp, {}, capture_mode="playwright",
                character_records=[
                    {"characterName": "First", "memberId": "m1"},
                    {"characterName": "Second", "memberId": "m2"},
                ],
            )
        events = []
        while not worker.events.empty():
            events.append(worker.events.get_nowait())
        done = next(event for event in events if event["type"] == "batch_done")
        self.assertEqual((done["successes"], done["failures"], done["processed"]), (1, 1, 2))

    def test_data_batch_recovers_closed_browser_and_continues(self):
        worker = self.worker()
        worker._current_page_is_character = Mock(return_value=True)
        worker._attempt_armory_extraction = Mock(side_effect=[
            RuntimeError("TargetClosedError"),
            {"race": "Night Elf", "className": "Warrior"},
            {"race": "Human", "className": "Priest"},
        ])
        worker._read_data_all(
            [{"characterName": "Janos", "memberId": "m1"},
             {"characterName": "Other", "memberId": "m2"}],
            "EU", "stitches", "classic1x", "msedge", 0, capture_mode="playwright",
        )
        events = []
        while not worker.events.empty():
            events.append(worker.events.get_nowait())
        done = next(event for event in events if event["type"] == "batch_done")
        self.assertEqual((done["successes"], done["failures"], done["processed"]), (2, 0, 2))
        worker._browser = SimpleNamespace(is_connected=lambda: True)
        worker._context = SimpleNamespace(pages=[], new_page=Mock(side_effect=RuntimeError("context closed")))
        worker._page = SimpleNamespace(is_closed=lambda: True)
        self.assertFalse(worker._browser_is_healthy())


class StandardModeProductTests(unittest.TestCase):
    def test_persistent_mode_is_absent_from_product_code_and_bilingual_ui(self):
        source = (REPO_ROOT / "app" / "GuildPortraitGrabber.py").read_text(encoding="utf-8")
        de = (REPO_ROOT / "app" / "locales" / "de.json").read_text(encoding="utf-8")
        en = (REPO_ROOT / "app" / "locales" / "en.json").read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertFalse(any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "launch_persistent_context"
            for node in ast.walk(tree)
        ))
        self.assertNotIn("playwright_persistent", source)
        self.assertNotIn("CAPTURE_MODE_PERSISTENT", source)
        self.assertNotIn("Playwright / Persistentes Profil", de)
        self.assertNotIn("Playwright / Persistent Profile", en)
        self.assertIn("values=(CAPTURE_MODE_PLAYWRIGHT, CAPTURE_MODE_STANDARD)", source)

    def test_default_and_display_mode_remain_v012(self):
        self.assertEqual(grabber.load_config()["capture_mode"], "playwright")
        self.assertEqual(grabber.capture_mode_display("playwright"), grabber.CAPTURE_MODE_PLAYWRIGHT)
        self.assertEqual(grabber.capture_mode_from_display(grabber.CAPTURE_MODE_PLAYWRIGHT), "playwright")
        self.assertIn("v0.1.2", grabber.CAPTURE_MODE_PLAYWRIGHT)

    def test_legacy_persistent_settings_fall_back_to_v012(self):
        with tempfile.TemporaryDirectory(prefix="ggc-legacy-mode-") as temp:
            root = Path(temp)
            config = root / "portrait_grabber.json"
            for legacy_value in ("persistent", "playwright_persistent"):
                with self.subTest(value=legacy_value):
                    config.write_text(
                        '{"capture_mode": "' + legacy_value + '", "output_dir": "' +
                        str(root).replace("\\", "\\\\") + '"}', encoding="utf-8",
                    )
                    with patch.object(grabber, "config_path", return_value=config), \
                         patch.object(grabber, "legacy_config_path", return_value=root / "missing.json"):
                        self.assertEqual(grabber.load_config()["capture_mode"], "playwright")
        self.assertEqual(grabber.capture_mode_from_display("playwright_persistent"), "playwright")

    def test_existing_edge_grabber_data_is_not_touched(self):
        with tempfile.TemporaryDirectory(prefix="ggc-unused-profile-") as temp:
            root = Path(temp)
            profile = root / "data" / "browser_profiles" / "edge_grabber"
            profile.mkdir(parents=True)
            marker = profile / "keep.dat"
            marker.write_bytes(b"keep-profile-data")
            before = marker.read_bytes()
            worker = grabber.BrowserWorker(__import__("queue").Queue())
            worker._ensure_browser = Mock()
            worker._ensure_capture_browser("playwright", "msedge")
            self.assertEqual(marker.read_bytes(), before)
            self.assertTrue(profile.is_dir())

    def test_only_v012_is_accepted_by_playwright_runtime_router(self):
        worker = grabber.BrowserWorker(__import__("queue").Queue())
        worker._ensure_browser = Mock()
        worker._ensure_capture_browser("playwright", "msedge")
        worker._ensure_browser.assert_called_once_with("msedge")
        self.assertEqual(worker._active_browser_mode, "playwright")
        worker._ensure_browser.reset_mock()
        with self.assertRaises(RuntimeError):
            worker._ensure_capture_browser("playwright_persistent", "msedge")
        worker._ensure_browser.assert_not_called()

    def test_portrait_and_race_class_single_paths_use_v012(self):
        worker = grabber.BrowserWorker(__import__("queue").Queue())
        worker._ensure_capture_browser = Mock()
        worker._current_page_is_character = Mock(return_value=True)
        worker._attempt_armory_extraction = Mock(return_value={"race": "Night Elf", "className": "Warrior"})
        worker._raw_screenshot = Mock(return_value=(Path("source.png"), "mock"))
        with tempfile.TemporaryDirectory(prefix="ggc-v012-portrait-") as temp, \
             patch.object(grabber, "crop_portrait") as crop:
            worker._capture_character(
                "Janos", "EU", "stitches", "classic1x", "msedge", 0,
                temp, {}, capture_mode="playwright", member_id="m0113",
            )
        worker._ensure_capture_browser.assert_called_with("playwright", "msedge")
        worker._attempt_armory_extraction.assert_called_once_with("Janos", "m0113", "portrait")
        crop.assert_called_once()

        worker._ensure_capture_browser.reset_mock()
        worker._attempt_armory_extraction.reset_mock()
        worker._attempt_armory_extraction.return_value = {"race": "Night Elf", "className": "Warrior"}
        result = worker._read_character_data(
            "Janos", "EU", "stitches", "classic1x", "msedge", 0,
            member_id="m0113", capture_mode="playwright",
        )
        self.assertEqual(result, {"race": "Night Elf", "className": "Warrior"})
        worker._ensure_capture_browser.assert_called_with("playwright", "msedge")


def main() -> int:
    global grabber, checker, i18n, REPO_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    REPO_ROOT = args.repo_root.resolve()
    i18n = load_module("ggc_armory_stability_i18n", REPO_ROOT / "app" / "i18n.py")
    grabber = load_module("ggc_armory_stability_grabber", REPO_ROOT / "app" / "GuildPortraitGrabber.py")
    checker = load_module("ggc_armory_stability_checker", REPO_ROOT / "app" / "GuildGearChecker.py")
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
