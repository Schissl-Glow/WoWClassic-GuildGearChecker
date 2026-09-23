from __future__ import annotations

import queue
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import GuildPortraitGrabber as grabber
from app.GuildGearChecker import GuildModel, _project_package_files
from app.GuildGearCheckerQt import (
    archive_portrait, graveyard_member_portrait_path, member_portrait_path,
)
from app.project_storage import member_portrait_path as stored_portrait_path
from app.project_storage import migrate_legacy_portraits


class MemberIdPortraitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ggc-member-portraits-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "guild.ggc"
        self.project.write_text('{"members": []}', encoding="utf-8")
        self.portraits = self.root / "portraits"
        self.portraits.mkdir()
        self.model = GuildModel()
        self.model.new_empty()
        self.model.project_path = self.project

    def add_member(self, name: str, life_status: str = "active"):
        member = self.model.add_member(name, "Test")
        member.lifeStatus = life_status
        return member

    def test_all_life_statuses_use_the_same_member_id_schema(self) -> None:
        for status in ("active", "inactive", "dead"):
            member = self.add_member(f"Character {status}", status)
            path = stored_portrait_path(self.project, member.id)
            path.write_bytes(status.encode("utf-8"))
            with self.subTest(status=status):
                self.assertEqual(path, self.portraits / f"{member.id}.png")
                self.assertEqual(member_portrait_path(self.model, member), path)

    def test_death_keeps_the_same_file_and_graveyard_uses_it(self) -> None:
        member = self.add_member("Main")
        path = stored_portrait_path(self.project, member.id)
        path.write_bytes(b"portrait")
        before = path.read_bytes()

        self.model.set_member_life_status(member.id, "dead")

        self.assertEqual(archive_portrait(self.model, member), path)
        self.assertEqual(graveyard_member_portrait_path(self.model, member), path)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.portraits / "history").exists())

    def test_same_name_incarnations_have_distinct_portraits(self) -> None:
        historical = self.add_member("NameX", "dead")
        current = self.add_member("NameX", "active")
        historical_path = stored_portrait_path(self.project, historical.id)
        current_path = stored_portrait_path(self.project, current.id)
        historical_path.write_bytes(b"old")
        current_path.write_bytes(b"new")

        self.assertNotEqual(historical_path, current_path)
        self.assertEqual(member_portrait_path(self.model, historical).read_bytes(), b"old")
        self.assertEqual(member_portrait_path(self.model, current).read_bytes(), b"new")

    def test_browser_worker_writes_the_member_id_filename(self) -> None:
        raw = self.root / "raw.png"
        raw.write_bytes(b"raw")
        worker = grabber.BrowserWorker(queue.Queue())
        worker._current_page_is_character = Mock(return_value=True)
        worker._attempt_armory_extraction = Mock()
        worker._raw_screenshot = Mock(return_value=(raw, "test"))
        worker._run_with_browser_recovery = lambda operation, *_args: operation()

        def save_crop(_source, destination, _crop):
            Path(destination).write_bytes(b"portrait")

        with patch.object(grabber, "crop_portrait", side_effect=save_crop):
            worker._capture_character(
                "NameX", "EU", "Stitches", "classic1x", "", 0,
                str(self.portraits), {}, member_id="m0042",
            )

        self.assertTrue((self.portraits / "m0042.png").is_file())
        self.assertFalse((self.portraits / "NameX.png").exists())

    def test_unique_name_and_history_portraits_migrate_by_member_id(self) -> None:
        unique = SimpleNamespace(id="m0001", name="Unique")
        historical = SimpleNamespace(id="m0002", name="Historical")
        (self.portraits / "Unique.png").write_bytes(b"unique")
        history = self.portraits / "history"
        history.mkdir()
        (history / "m0002.png").write_bytes(b"history")
        (history / "m0002.missing").write_text("", encoding="utf-8")

        summary = migrate_legacy_portraits(self.project, [unique, historical])

        self.assertEqual(set(summary.migrated_member_ids), {"m0001", "m0002"})
        self.assertEqual((self.portraits / "m0001.png").read_bytes(), b"unique")
        self.assertEqual((self.portraits / "m0002.png").read_bytes(), b"history")
        self.assertFalse((self.portraits / "Unique.png").exists())
        self.assertFalse((history / "m0002.png").exists())

    def test_ambiguous_legacy_name_is_not_guessed(self) -> None:
        first = SimpleNamespace(id="m0001", name="Same")
        second = SimpleNamespace(id="m0002", name="Same")
        legacy = self.portraits / "Same.png"
        legacy.write_bytes(b"ambiguous")

        summary = migrate_legacy_portraits(self.project, [first, second])

        self.assertEqual(summary.ambiguous_names, ("Same",))
        self.assertTrue(legacy.is_file())
        self.assertFalse((self.portraits / "m0001.png").exists())
        self.assertFalse((self.portraits / "m0002.png").exists())

    def test_project_package_uses_only_member_id_portraits(self) -> None:
        first = self.add_member("Same", "dead")
        second = self.add_member("Same", "active")
        stored_portrait_path(self.project, first.id).write_bytes(b"first")
        stored_portrait_path(self.project, second.id).write_bytes(b"second")

        files, missing, warnings = _project_package_files(self.model, self.portraits)

        self.assertEqual(missing, 0)
        self.assertEqual(warnings, [])
        self.assertEqual(
            [item.archive_name for item in files],
            [f"portraits/{first.id}.png", f"portraits/{second.id}.png"],
        )


if __name__ == "__main__":
    unittest.main()
