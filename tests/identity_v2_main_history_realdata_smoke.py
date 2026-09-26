"""Main succession and timeline smoke on an in-memory real V2 reference."""

import copy
import tempfile
import time
import unittest
from pathlib import Path

from app.identity_v2 import (
    IdentityV2ValidationError, Member, member_id_from_number,
)
from app.identity_v2_character_service import mark_member_dead
from app.identity_v2_main_history import (
    MainSuccessorSelectionRequired, add_main_history_entry,
    find_main_history_conflicts,
)
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from app.gravestone_templates import load_gravestone_inventory


class IdentityV2MainHistoryRealDataSmoke(unittest.TestCase):
    def test_reference_stays_byte_equal_after_temp_successor_scenarios(self):
        root = Path(__file__).resolve().parents[1]
        candidates = [*sorted((root / "testdata").glob("*.ggc")),
                      root / "BS_Neu.ggc",
                      Path.home() / "Desktop" / "BS_Neu" / "BS_V2.ggc"]
        source = original = None
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                original = load_identity_v2(candidate)
            except IdentityV2ValidationError:
                continue
            source = candidate
            break
        if source is None:
            self.skipTest("Keine lesbare V2-Referenzdatei verfügbar.")
        source_bytes = source.read_bytes()
        before = original.to_payload()
        working = copy.deepcopy(original)
        existing_ids = {member.memberId for member in working.members}
        number = max([1000, *(int(item[1:]) + 1 for item in existing_ids
                              if item.startswith("m") and item[1:].isdigit())])

        def new_member(player_id: str, suffix: str) -> str:
            nonlocal number
            while member_id_from_number(number) in existing_ids:
                number += 1
            member_id = member_id_from_number(number)
            number += 1
            existing_ids.add(member_id)
            working.members.append(Member(member_id, f"Smoke-{suffix}", "Mage",
                                          playerId=player_id))
            return member_id

        scenarios = []
        for label, count in (("zero", 0), ("one", 1), ("many", 3)):
            player = working._append_player(f"Smoke-{label}-Player")
            main_id = new_member(player.playerId, f"{label}-main")
            player.mainMemberId = main_id
            player.mainSinceDate = "2026-01-01"
            successors = tuple(new_member(player.playerId, f"{label}-twink-{index}")
                               for index in range(count))
            scenarios.append((player.playerId, main_id, successors))
        working.validate()
        assets = root / "assets" / "graveyard"
        templates = load_gravestone_inventory(
            assets, assets / "gravestones_manifest.json").templates
        started = time.perf_counter()
        for player_id, main_id, successors in scenarios:
            if len(successors) > 1:
                snapshot = working.to_payload()
                with self.assertRaises(MainSuccessorSelectionRequired):
                    mark_member_dead(working, main_id, "2026-09-25", "individual")
                self.assertEqual(working.to_payload(), snapshot)
            working = mark_member_dead(
                working, main_id, "2026-09-25", "individual",
                successors[1] if len(successors) > 1 else None,
                gravestone_templates=templates)
            player = next(item for item in working.players if item.playerId == player_id)
            self.assertEqual(player.mainMemberId,
                             (successors[1] if len(successors) > 1 else
                              successors[0] if successors else None))
            self.assertEqual(player.mainHistory[-1].memberId, main_id)
        many_player, _main, many_successors = scenarios[-1]
        working = add_main_history_entry(working, many_player, many_successors[0],
                                         "2025-01-01", "2025-08-01")
        working = add_main_history_entry(working, many_player, many_successors[1],
                                         "2025-06-01", "2025-09-01")
        self.assertEqual(len(find_main_history_conflicts(working, many_player)), 1)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main-history-smoke.ggc"
            save_new_identity_v2(working, target)
            restored = load_identity_v2(target)
        self.assertEqual(restored.to_payload(), working.to_payload())
        self.assertEqual(restored.attendance, original.attendance)
        self.assertEqual(restored.raids, original.raids)
        original_members = {item.memberId: item for item in original.members}
        for member in restored.members:
            previous = original_members.get(member.memberId)
            if previous is not None:
                self.assertEqual((member.playerId, member.clmGuid,
                                  member.burialType, member.deathDate),
                                 (previous.playerId, previous.clmGuid,
                                  previous.burialType, previous.deathDate))
        self.assertEqual(original.to_payload(), before)
        self.assertEqual(source.read_bytes(), source_bytes)
        print(f"MainHistory real data ({source.name}): "
              f"{len(original.members)} source members, 0/1/N successors, "
              f"{time.perf_counter() - started:.3f}s")


if __name__ == "__main__":
    unittest.main()
