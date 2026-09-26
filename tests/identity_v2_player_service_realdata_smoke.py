"""Optional Player-service smoke using a read-only V2 save and temporary output."""

import tempfile
import unittest
from pathlib import Path

from app.identity_v2 import IdentityV2ValidationError
from app.identity_v2_main_history import remove_main_history_entry
from app.identity_v2_player_service import (
    PlayerMembershipError, assign_member, create_player_from_member, reassign_member, set_main,
    unassign_member,
)
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2


class IdentityV2PlayerServiceRealDataSmoke(unittest.TestCase):
    def test_read_only_v2_source_survives_owner_corrections_and_temp_roundtrip(self):
        root = Path(__file__).resolve().parents[1]
        candidates = [
            *sorted((root / "testdata").glob("*.ggc")),
            Path.home() / "Desktop" / "BS_Neu" / "BS_V2.ggc",
        ]
        source = None
        store = None
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                store = load_identity_v2(candidate)
            except IdentityV2ValidationError:
                continue
            source = candidate
            break
        if source is None or store is None:
            self.skipTest("Keine lokale Identity-V2-Referenzdatei verfügbar.")

        original = source.read_bytes()
        credited = {item.creditedMemberId for item in store.raidCreditResolutions}
        attended = {item.memberId for item in store.attendance}
        members = [item for item in store.members
                   if item.playerId is None and item.lifeStatus == "active"
                   and item.memberId in attended and item.memberId not in credited]
        if len(members) < 2:
            self.skipTest("Die V2-Referenz hat weniger als zwei passende Member.")
        first, second = members[:2]

        def without_owner(record):
            data = record.to_dict()
            data.pop("playerId", None)
            return data

        before_raids = [item.to_dict() for item in store.raids]
        before_members = [without_owner(item) for item in store.members]
        before_attendance = [without_owner(item) for item in store.attendance]
        before_guids = dict(store.legacyClmGuidMemberMap)

        result = create_player_from_member(store, first.memberId)
        player_a = next(item.playerId for item in result.members
                        if item.memberId == first.memberId)
        result = assign_member(result, second.memberId, player_a)
        result = set_main(result, player_a, second.memberId)
        player_b = result.create_player("Temporärer Player B")
        with self.assertRaises(PlayerMembershipError):
            reassign_member(result, first.memberId, player_b.playerId)
        player = next(item for item in result.players if item.playerId == player_a)
        result = remove_main_history_entry(result, player.mainHistory[0].historyId)
        result = reassign_member(result, first.memberId, player_b.playerId)
        result = unassign_member(result, second.memberId)

        self.assertEqual([item.to_dict() for item in result.raids], before_raids)
        self.assertEqual([without_owner(item) for item in result.members], before_members)
        self.assertEqual([without_owner(item) for item in result.attendance],
                         before_attendance)
        self.assertEqual(result.legacyClmGuidMemberMap, before_guids)
        self.assertEqual((len(result.raids), len(result.attendance)),
                         (len(store.raids), len(store.attendance)))
        self.assertEqual({item.playerId for item in result.attendance
                          if item.memberId == first.memberId}, {player_b.playerId})
        self.assertEqual({item.playerId for item in result.attendance
                          if item.memberId == second.memberId}, {None})

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "player-service-smoke.ggc"
            save_new_identity_v2(result, target)
            restored = load_identity_v2(target)
        self.assertEqual(restored.to_payload(), result.to_payload())
        self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
