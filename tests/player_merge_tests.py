"""Gezielte Tests der fachlichen Player-Merge-Logik."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.player_merge import (
    PlayerMergeConflictError, apply_player_merge, plan_player_merge,
)


class PlayerMergeTests(unittest.TestCase):
    def test_conflict_is_returned_for_two_characters_in_same_raid(self):
        members = [
            SimpleNamespace(id="m1", playerId="p-source"),
            SimpleNamespace(id="m2", playerId="p-target"),
        ]
        records = [
            SimpleNamespace(id="a1", raidId="r1", playerId="p-source",
                            memberId="m1", characterNameSnapshot="Twink"),
            SimpleNamespace(id="a2", raidId="r1", playerId="p-target",
                            memberId="m2", characterNameSnapshot="Main"),
        ]
        plan = plan_player_merge("p-source", "p-target", members, records)
        self.assertFalse(plan.can_apply)
        self.assertEqual(plan.conflicts[0].raid_id, "r1")
        with self.assertRaises(PlayerMergeConflictError):
            apply_player_merge(
                "p-source", "p-target",
                [SimpleNamespace(playerId="p-source"), SimpleNamespace(playerId="p-target")],
                members, records,
            )
        resolved = apply_player_merge(
            "p-source", "p-target",
            [SimpleNamespace(playerId="p-source"), SimpleNamespace(playerId="p-target")],
            members, records, conflict_resolutions={"r1": "a2"},
        )
        self.assertEqual(resolved.excluded_attendance_ids, ("a1",))
        self.assertEqual(
            [entry.playerId for entry in resolved.attendance],
            ["p-target", "p-target"],
        )
        self.assertEqual(records[0].playerId, "p-source")

    def test_conflict_free_merge_keeps_target_and_member_ids(self):
        players = [
            SimpleNamespace(playerId="p-source", playerName="Alt"),
            SimpleNamespace(playerId="p-target", playerName="Main"),
        ]
        members = [SimpleNamespace(id="m1", playerId="p-source")]
        records = [
            SimpleNamespace(id="a1", raidId="r1", playerId="p-source",
                            memberId="m1", characterNameSnapshot="Twink"),
        ]
        result = apply_player_merge(
            "p-source", "p-target", players, members, records,
        )
        self.assertEqual([player.playerId for player in result.players], ["p-target"])
        self.assertEqual((result.members[0].id, result.members[0].playerId),
                         ("m1", "p-target"))
        self.assertEqual((result.attendance[0].memberId, result.attendance[0].playerId),
                         ("m1", "p-target"))
        self.assertEqual((members[0].playerId, records[0].playerId),
                         ("p-source", "p-source"))


if __name__ == "__main__":
    unittest.main()
