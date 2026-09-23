from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtWidgets import QInputDialog, QMessageBox

from app.GuildGearChecker import GuildModel
from app.GuildGearCheckerQt import GuildGearCheckerQt


class DeathWorkflowHarness:
    _choose_main_successor = GuildGearCheckerQt._choose_main_successor
    _collect_main_succession_decisions = GuildGearCheckerQt._collect_main_succession_decisions
    _mark_members_dead = GuildGearCheckerQt._mark_members_dead
    mark_dead_selected = GuildGearCheckerQt.mark_dead_selected

    def __init__(self) -> None:
        self.model = GuildModel()
        self.model.new_empty()
        self.selected_member_id: str | None = None
        self.autosave_calls = 0
        self.status = ""

    def autosave(self) -> None:
        self.autosave_calls += 1

    def refresh_all(self, *args, **kwargs) -> None:
        return

    def _filtered_members(self):
        return list(self.model.members)

    def _select_member_in_table(self, _member_id: str) -> None:
        return

    def show_member(self, _member_id: str) -> None:
        return

    def clear_detail(self) -> None:
        return

    def set_status(self, text: str) -> None:
        self.status = text


class MainSuccessionUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.window = DeathWorkflowHarness()

    def add_main(self, name: str):
        member = self.window.model.add_member(name, "Test")
        self.window.model.assign_character_type(member.id, "main", None, "not_set")
        return member

    def add_twink(self, main, name: str):
        member = self.window.model.add_member(name, "Test")
        self.window.model.assign_character_type(member.id, "twink", main.id, "not_set")
        return member

    @staticmethod
    def choose_first(_parent, _title, _prompt, labels, *_args):
        return labels[0], True

    def test_single_main_death_promotes_selected_twink(self) -> None:
        main = self.add_main("Main")
        twink = self.add_twink(main, "Twink")
        self.window.selected_member_id = main.id

        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes,
        ), patch.object(QInputDialog, "getItem", side_effect=self.choose_first):
            self.window.mark_dead_selected()

        self.assertEqual((main.lifeStatus, main.characterType), ("dead", "main"))
        self.assertEqual((twink.lifeStatus, twink.characterType), ("active", "main"))
        self.assertEqual(self.window.autosave_calls, 1)

    def test_single_successor_dialog_cancel_changes_nothing(self) -> None:
        main = self.add_main("Main")
        twink = self.add_twink(main, "Twink")
        self.window.selected_member_id = main.id
        before = [(member.id, member.lifeStatus, member.characterType)
                  for member in self.window.model.members]

        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes,
        ), patch.object(QInputDialog, "getItem", return_value=("", False)):
            self.window.mark_dead_selected()

        self.assertEqual(
            [(member.id, member.lifeStatus, member.characterType)
             for member in self.window.model.members],
            before,
        )
        self.assertEqual(self.window.autosave_calls, 0)
        self.assertTrue(self.window.status)

    def test_single_main_without_candidate_dies_without_dialog(self) -> None:
        main = self.add_main("Main")
        self.window.selected_member_id = main.id

        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes,
        ), patch.object(QInputDialog, "getItem") as dialog:
            self.window.mark_dead_selected()

        dialog.assert_not_called()
        self.assertEqual((main.lifeStatus, main.characterType), ("dead", "main"))
        self.assertEqual(self.window.autosave_calls, 1)

    def test_wipe_without_main_keeps_previous_multi_death_behavior(self) -> None:
        first = self.window.model.add_member("First", "Test")
        second = self.window.model.add_member("Second", "Test")
        selected_ids = [first.id, second.id]

        decisions = self.window._collect_main_succession_decisions(selected_ids)
        changed = self.window._mark_members_dead(selected_ids, decisions)

        self.assertEqual([member.id for member in changed], selected_ids)
        self.assertTrue(all(member.lifeStatus == "dead" for member in changed))

    def test_wipe_promotes_surviving_twink(self) -> None:
        main = self.add_main("Main")
        survivor = self.add_twink(main, "Survivor")

        with patch.object(QInputDialog, "getItem", side_effect=self.choose_first):
            decisions = self.window._collect_main_succession_decisions([main.id])
        self.window._mark_members_dead([main.id], decisions)

        self.assertEqual(main.lifeStatus, "dead")
        self.assertEqual((survivor.lifeStatus, survivor.characterType), ("active", "main"))

    def test_wipe_excludes_twink_that_also_dies(self) -> None:
        main = self.add_main("Main")
        twink = self.add_twink(main, "Twink")
        selected_ids = [main.id, twink.id]

        with patch.object(QInputDialog, "getItem") as dialog:
            decisions = self.window._collect_main_succession_decisions(selected_ids)
        changed = self.window._mark_members_dead(selected_ids, decisions)

        dialog.assert_not_called()
        self.assertEqual([member.id for member in changed], selected_ids)
        self.assertEqual(
            [(member.lifeStatus, member.characterType) for member in (main, twink)],
            [("dead", "main"), ("dead", "twink")],
        )

    def test_wipe_resolves_multiple_players_before_mutation(self) -> None:
        first_main = self.add_main("First Main")
        first_twink = self.add_twink(first_main, "First Twink")
        second_main = self.add_main("Second Main")
        second_twink = self.add_twink(second_main, "Second Twink")
        selected_ids = [first_main.id, second_main.id]

        with patch.object(QInputDialog, "getItem", side_effect=self.choose_first):
            decisions = self.window._collect_main_succession_decisions(selected_ids)
        self.window._mark_members_dead(selected_ids, decisions)

        self.assertEqual(set(decisions.values()), {first_twink.id, second_twink.id})
        self.assertEqual((first_twink.characterType, second_twink.characterType), ("main", "main"))

    def test_cancelling_second_wipe_dialog_leaves_entire_wipe_unchanged(self) -> None:
        first_main = self.add_main("First Main")
        self.add_twink(first_main, "First Twink")
        second_main = self.add_main("Second Main")
        self.add_twink(second_main, "Second Twink")
        selected_ids = [first_main.id, second_main.id]
        before = [(member.id, member.lifeStatus, member.characterType)
                  for member in self.window.model.members]
        answers = iter((True, False))

        def choose_then_cancel(_parent, _title, _prompt, labels, *_args):
            accepted = next(answers)
            return (labels[0], True) if accepted else ("", False)

        with patch.object(QInputDialog, "getItem", side_effect=choose_then_cancel):
            decisions = self.window._collect_main_succession_decisions(selected_ids)

        self.assertIsNone(decisions)
        self.assertEqual(
            [(member.id, member.lifeStatus, member.characterType)
             for member in self.window.model.members],
            before,
        )

    def test_same_name_candidates_remain_member_id_distinct(self) -> None:
        main = self.add_main("Main")
        first = self.add_twink(main, "SameName A")
        second = self.add_twink(main, "SameName B")
        second.name = first.name

        def choose_second(_parent, _title, _prompt, labels, *_args):
            return next(label for label in labels if second.id in label), True

        with patch.object(QInputDialog, "getItem", side_effect=choose_second):
            decisions = self.window._collect_main_succession_decisions([main.id])

        self.assertEqual(decisions, {main.id: second.id})

    def test_new_texts_exist_in_both_locales(self) -> None:
        for language in ("de", "en"):
            payload = json.loads(
                (REPO_ROOT / "app" / "locales" / f"{language}.json").read_text(
                    encoding="utf-8",
                )
            )
            checker = payload["checker"]
            for key in (
                "main_succession_title", "main_succession_prompt",
                "main_succession_cancelled",
            ):
                self.assertTrue(checker[key])
            model = payload["model"]
            for key in (
                "historical_role_protected", "historical_assignment_protected",
                "main_succession_requires_active_main",
                "main_death_requires_active_main", "main_successor_required",
                "invalid_main_successor",
            ):
                self.assertTrue(model[key])


if __name__ == "__main__":
    unittest.main()
