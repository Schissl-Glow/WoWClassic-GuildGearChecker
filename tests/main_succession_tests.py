from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.GuildGearChecker import GuildModel


class MainSuccessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = GuildModel()
        self.model.new_empty()

    def add_main(self, name: str = "Main"):
        member = self.model.add_member(name, "Test")
        self.model.assign_character_type(member.id, "main", None, "not_set")
        return member, self.model.find_player_by_id(member.playerId)

    def add_twink(self, main, name: str = "Twink"):
        member = self.model.add_member(name, "Test")
        self.model.assign_character_type(member.id, "twink", main.id, "not_set")
        return member

    @staticmethod
    def identity_state(*members) -> tuple[tuple[str, str | None, str, str], ...]:
        return tuple(
            (member.id, member.playerId, member.characterType, member.lifeStatus)
            for member in members
        )

    def test_main_death_promotes_explicit_twink_and_preserves_history(self) -> None:
        main, player = self.add_main()
        twink = self.add_twink(main)
        raid = self.model.create_raid("2026-09-01", "Raid", raid_type="ZG")
        self.model.import_raid_attendance(raid.id, [main.name])
        self.model.activate_raid_points(include_existing=True)

        dead, successor = self.model.mark_main_dead_with_successor(
            main.id, twink.id, "2026-09-02",
        )

        self.assertIs(dead, main)
        self.assertIs(successor, twink)
        self.assertEqual(
            (main.lifeStatus, main.characterType, main.playerId, main.deathDate),
            ("dead", "main", player.playerId, "2026-09-02"),
        )
        self.assertEqual(
            (twink.lifeStatus, twink.characterType, twink.playerId),
            ("active", "main", player.playerId),
        )
        attendance = self.model.attendance_for_raid(raid.id)
        self.assertEqual([(entry.memberId, entry.playerId) for entry in attendance], [
            (main.id, player.playerId),
        ])
        self.assertEqual(
            [(entry.member_id, entry.player_id) for entry in self.model.raid_point_history()],
            [(main.id, player.playerId)],
        )

    def test_main_with_candidate_requires_successor_without_partial_change(self) -> None:
        main, _player = self.add_main()
        twink = self.add_twink(main)
        before = self.identity_state(main, twink)

        with self.assertRaises(ValueError):
            self.model.mark_main_dead_with_successor(main.id)
        self.assertEqual(self.identity_state(main, twink), before)
        with self.assertRaises(ValueError):
            self.model.set_member_life_status(main.id, "dead")
        self.assertEqual(self.identity_state(main, twink), before)

    def test_main_without_living_candidate_may_die_without_successor(self) -> None:
        main, player = self.add_main()

        dead, successor = self.model.mark_main_dead_with_successor(main.id)

        self.assertIsNone(successor)
        self.assertEqual(
            (dead.lifeStatus, dead.characterType, dead.playerId),
            ("dead", "main", player.playerId),
        )

    def test_successor_from_other_player_is_rejected_atomically(self) -> None:
        main, _player = self.add_main("Main A")
        own_twink = self.add_twink(main, "Twink A")
        other_main, _other_player = self.add_main("Main B")
        other_twink = self.add_twink(other_main, "Twink B")
        before = self.identity_state(main, own_twink, other_main, other_twink)

        with self.assertRaises(ValueError):
            self.model.mark_main_dead_with_successor(main.id, other_twink.id)

        self.assertEqual(self.identity_state(main, own_twink, other_main, other_twink), before)

    def test_dead_or_same_character_cannot_be_successor(self) -> None:
        main, _player = self.add_main()
        dead_twink = self.add_twink(main)
        self.model.set_member_life_status(dead_twink.id, "dead")
        before = self.identity_state(main, dead_twink)

        with self.assertRaises(ValueError):
            self.model.mark_main_dead_with_successor(main.id, dead_twink.id)
        self.assertEqual(self.identity_state(main, dead_twink), before)
        with self.assertRaises(ValueError):
            self.model.mark_main_dead_with_successor(main.id, main.id)
        self.assertEqual(self.identity_state(main, dead_twink), before)

    def test_dead_main_role_and_player_are_protected(self) -> None:
        main, player = self.add_main()
        self.model.mark_main_dead_with_successor(main.id)

        for character_type in ("twink", "not_set"):
            with self.subTest(api="update", character_type=character_type):
                with self.assertRaises(ValueError):
                    self.model.update_member_assignment(
                        main.id,
                        player.playerId if character_type == "twink" else None,
                        character_type,
                        "not_set",
                    )
            with self.subTest(api="assign", character_type=character_type):
                with self.assertRaises(ValueError):
                    self.model.assign_character_type(
                        main.id, character_type, None, "not_set",
                    )
        self.assertEqual(
            (main.lifeStatus, main.characterType, main.playerId),
            ("dead", "main", player.playerId),
        )

    def test_living_twink_can_still_become_main(self) -> None:
        main, player = self.add_main()
        twink = self.add_twink(main)

        self.model.assign_character_type(
            twink.id, "main", None, "not_set", replace_existing_main=True,
        )

        self.assertEqual((main.characterType, twink.characterType), ("twink", "main"))
        self.assertEqual(twink.playerId, player.playerId)

    def test_same_name_incarnations_keep_distinct_member_ids_and_one_player(self) -> None:
        historical, player = self.add_main("NameX")
        self.model.mark_main_dead_with_successor(historical.id)
        current = self.model.add_member("NameX", "Test")
        self.model.update_member_assignment(
            current.id, player.playerId, "main", "not_set",
        )

        self.assertNotEqual(historical.id, current.id)
        self.assertEqual(historical.playerId, current.playerId)
        self.assertEqual(
            (historical.lifeStatus, historical.characterType,
             current.lifeStatus, current.characterType),
            ("dead", "main", "active", "main"),
        )

    def test_multiple_dead_historical_mains_and_one_active_main_are_valid(self) -> None:
        first, player = self.add_main("First")
        second = self.add_twink(first, "Second")
        third = self.add_twink(first, "Third")

        self.model.mark_main_dead_with_successor(first.id, second.id)
        self.model.mark_main_dead_with_successor(second.id, third.id)

        self.assertEqual(
            [(member.lifeStatus, member.characterType, member.playerId)
             for member in (first, second, third)],
            [
                ("dead", "main", player.playerId),
                ("dead", "main", player.playerId),
                ("active", "main", player.playerId),
            ],
        )
        restored = GuildModel()
        restored.load_payload(self.model.to_payload())
        self.assertEqual(
            sum(member.lifeStatus == "active" and member.characterType == "main"
                for member in restored.members),
            1,
        )


if __name__ == "__main__":
    unittest.main()
