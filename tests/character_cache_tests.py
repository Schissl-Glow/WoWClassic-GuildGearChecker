"""Focused offline tests for the persistent, membership-neutral Armory cache."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import Mock


cache = None
checker = None
grabber = None


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Value:
    def __init__(self, value: str):
        self.value = value

    def get(self) -> str:
        return self.value


class CharacterCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-character-cache-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache_path = cache.character_cache_path(self.root)
        self.snapshot_path = self.root / "data" / "runtime" / "guild_roster_snapshot.json"

    def store_result(self, name: str, member_id: str | None = None,
                     race: str = "Human", class_name: str = "Mage"):
        view = SimpleNamespace(
            character_records={
                name.casefold(): {
                    "memberId": member_id, "characterName": name,
                    "race": None, "className": None,
                }
            },
            armory_results={},
            project_path=None,
            region_var=Value("EU"), realm_var=Value("stitches"),
            game_var=Value("classic1x"),
            _persist_armory_results=Mock(),
            _character_cache_path=lambda: self.cache_path,
            _guild_snapshot_path=lambda: self.snapshot_path,
            _log=Mock(),
        )
        view._record_for_name = MethodType(grabber.App._record_for_name, view)
        result = {
            "memberId": member_id,
            "characterName": name,
            "race": race,
            "className": class_name,
            "source": "classicwowarmory",
            "retrievedAt": "2026-09-13T12:00:00+00:00",
        }
        grabber.App._store_armory_result(view, result)
        return view

    def test_a_all_supported_import_origins_use_the_common_cache_writer(self):
        txt = self.root / "names.txt"
        txt.write_text("Textheld\n", encoding="utf-8")
        csv_path = self.root / "logs.csv"
        csv_path.write_text("Name,Amount\nCSVheld,1\n", encoding="utf-8")
        project = self.root / "roster.ggc"
        project.write_text(json.dumps({
            "members": [{"id": "m0042", "name": "Projektheld", "lifeStatus": "active"}],
            "region": "EU", "realm": "stitches", "gameVersion": "classic1x",
        }), encoding="utf-8")

        txt_names = grabber.parse_txt_names(txt)
        csv_names = grabber.parse_csv_names(csv_path)
        ggc_records, _context = grabber.parse_ggc_characters(project)
        sources = [
            ("TXT", txt_names[0], None),
            ("CSV", csv_names[0], None),
            ("GGC", ggc_records[0]["characterName"], ggc_records[0]["memberId"]),
            ("Gildenliste", "Gildenheld", None),
            ("manuelle Liste", "Listenheld", None),
        ]
        for label, name, member_id in sources:
            with self.subTest(source=label):
                self.store_result(name, member_id)

        payload = cache.load_character_cache(self.cache_path)
        self.assertEqual(
            {entry["characterName"] for entry in payload["characters"]},
            {item[1] for item in sources},
        )
        self.assertEqual(
            next(entry for entry in payload["characters"] if entry["characterName"] == "Projektheld")["memberId"],
            "m0042",
        )

    def test_b_cache_is_persistent_atomic_and_preserves_other_entries(self):
        self.store_result("Ánníe", "m0001", "Human", "Priest")
        self.store_result("Bífi", "m0002", "Dwarf", "Warrior")
        payload = cache.load_character_cache(self.cache_path)
        self.assertEqual(len(payload["characters"]), 2)
        self.assertEqual(payload["characters"][0]["timestamp"], "2026-09-13T12:00:00+00:00")
        self.assertFalse(self.cache_path.with_suffix(".json.tmp").exists())

        cache.update_character_cache(
            self.cache_path, member_id="m0001", character_name="Ánníe",
            region="EU", realm="stitches", game_version="classic1x",
            race="Human", class_name="Mage",
        )
        reopened = cache.load_character_cache(self.cache_path)
        self.assertEqual(len(reopened["characters"]), 2)
        self.assertEqual(
            next(item for item in reopened["characters"] if item["memberId"] == "m0001")["className"],
            "Mage",
        )

    def test_c_checker_enriches_only_known_members(self):
        model = checker.GuildModel()
        known = model.add_member("Known", "Test")
        model.dirty = False
        payload = cache.empty_character_cache()
        payload["characters"] = [
            {"memberId": known.id, "characterName": "Known", "region": "EU",
             "realm": "stitches", "gameVersion": "classic1x", "race": "Human",
             "className": "Mage", "timestamp": "2026-09-13T12:00:00+00:00"},
            {"memberId": None, "characterName": "Unknown", "region": "EU",
             "realm": "stitches", "gameVersion": "classic1x", "race": "Dwarf",
             "className": "Priest", "timestamp": None},
        ]
        before_ids = [member.id for member in model.members]
        summary = model.apply_character_cache(payload)
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(summary["ignored"], 1)
        self.assertEqual([member.id for member in model.members], before_ids)
        self.assertIsNone(model.find_current_by_name("Unknown"))
        self.assertEqual((known.race, known.className), ("Human", "Mage"))

    def test_d_id_is_preferred_and_name_fallback_must_be_unambiguous(self):
        model = checker.GuildModel()
        current = model.add_member("Same", "Test")
        inactive = model.add_member("Other", "Test")
        inactive.lifeStatus = "inactive"
        payload = cache.empty_character_cache()
        payload["characters"] = [
            {"memberId": current.id, "characterName": "Same", "region": "EU",
             "realm": "stitches", "gameVersion": "classic1x", "race": "Human",
             "className": "Mage", "timestamp": None},
            {"memberId": None, "characterName": "Other", "region": "EU",
             "realm": "stitches", "gameVersion": "classic1x", "race": "Dwarf",
             "className": "Priest", "timestamp": None},
        ]
        summary = model.apply_character_cache(payload)
        self.assertEqual(summary["updated"], 2)
        self.assertEqual(current.className, "Mage")
        self.assertEqual(inactive.className, "Priest")

        inactive.className = ""
        payload["characters"].append(dict(payload["characters"][1]))
        summary = model.apply_character_cache(payload)
        self.assertEqual(inactive.className, "")
        self.assertGreaterEqual(summary["ignored"], 1)

    def test_e_file_import_and_cache_write_never_create_guild_snapshot(self):
        self.store_result("Standalone")
        self.assertTrue(self.cache_path.is_file())
        self.assertFalse(self.snapshot_path.exists())

    def test_f_corrupt_cache_is_reported_and_never_silently_overwritten(self):
        self.cache_path.parent.mkdir(parents=True)
        original = b"{not-json"
        self.cache_path.write_bytes(original)
        errors = []
        self.assertEqual(cache.load_character_cache(self.cache_path, errors.append)["characters"], [])
        self.assertEqual(len(errors), 1)
        with self.assertRaises(cache.CharacterCacheError):
            cache.update_character_cache(
                self.cache_path, member_id=None, character_name="Safe",
                region="EU", realm="stitches", game_version="classic1x",
                race="Human", class_name="Mage",
            )
        self.assertEqual(self.cache_path.read_bytes(), original)

    def test_g_existing_checker_values_become_conflicts_not_overwrites(self):
        model = checker.GuildModel()
        member = model.add_member("Conflict", "Test")
        member.race = "Human"
        member.className = "Mage"
        model.dirty = False
        payload = cache.empty_character_cache()
        payload["characters"] = [{
            "memberId": member.id, "characterName": member.name,
            "region": "EU", "realm": "stitches", "gameVersion": "classic1x",
            "race": "Dwarf", "className": "Priest", "timestamp": None,
        }]
        summary = model.apply_character_cache(payload)
        self.assertEqual(summary["updated"], 0)
        self.assertEqual(len(summary["conflicts"]), 2)
        self.assertEqual((member.race, member.className), ("Human", "Mage"))
        self.assertFalse(model.dirty)


def main() -> int:
    global cache, checker, grabber
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.repo_root.resolve()
    sys.path.insert(0, str(root))
    cache = load_module("ggc_character_cache", root / "app" / "character_cache.py")
    checker = load_module("ggc_character_cache_checker", root / "app" / "GuildGearChecker.py")
    grabber = load_module("ggc_character_cache_grabber", root / "app" / "GuildPortraitGrabber.py")
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(CharacterCacheTests)
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
