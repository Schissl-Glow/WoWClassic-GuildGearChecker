"""In-memory V2 character edits against a local reference; original stays byte-identical."""

import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.identity_v2 import IdentityV2ValidationError  # noqa: E402
from app.identity_v2_character_service import (  # noqa: E402
    confirm_member_check, mark_member_dead, set_member_gear_status,
    set_member_note, set_member_race, set_member_raid_status, set_member_burial_type,
)
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2  # noqa: E402
from app.gravestone_templates import load_gravestone_inventory  # noqa: E402


class IdentityV2CharacterRealDataSmoke(unittest.TestCase):
    def test_reference_is_read_only_and_edited_save_is_temporary(self):
        candidates = [
            *sorted((ROOT / "testdata").glob("*.ggc")),
            ROOT / "BS_Neu.ggc",
            Path.home() / "Desktop" / "BS_Neu" / "BS_V2.ggc",
        ]
        source = store = None
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                store = load_identity_v2(candidate)
            except IdentityV2ValidationError:
                continue
            source = candidate
            break
        if store is None or source is None:
            self.skipTest("Keine lesbare V2-Referenzdatei verfügbar.")
        original_bytes = source.read_bytes()
        raids_by_id = {raid.raidId: raid for raid in store.raids}
        attendance_by_member: dict[str, list] = {}
        for entry in store.attendance:
            attendance_by_member.setdefault(entry.memberId, []).append(entry)
        target = None
        target_day = None
        collective_target = None
        collective_day = None
        for member in store.members:
            if member.lifeStatus != "active" or member.deathDate is not None:
                continue
            dates = []
            try:
                for entry in attendance_by_member.get(member.memberId, []):
                    dates.append(date.fromisoformat(raids_by_id[entry.raidId].date))
            except (KeyError, TypeError, ValueError):
                continue
            if target is None:
                target, target_day = member, max([date.today(), *dates]).isoformat()
            else:
                collective_target = member
                collective_day = max([date.today(), *dates]).isoformat()
                break
        if target is None or collective_target is None:
            self.skipTest("Keine zwei für den temporären Death-Smoke geeigneten aktiven Member.")

        before = store.to_payload()
        original_main = {player.playerId: player.mainMemberId for player in store.players}
        edit_started = time.perf_counter()
        changed = set_member_race(store, target.memberId,
                                  "Human" if target.race != "Human" else "Gnome")
        first_edit_seconds = time.perf_counter() - edit_started
        changed = set_member_gear_status(
            changed, target.memberId, "BiS" if target.gearStatus != "BiS" else "Pre-BiS")
        changed = set_member_raid_status(
            changed, target.memberId,
            "Bereit" if target.raidStatus != "Bereit" else "Nicht bereit")
        changed = set_member_note(changed, target.memberId, "Temporäre Charakterdatenprüfung")
        changed = confirm_member_check(changed, target.memberId, target_day)
        assets = ROOT / "assets" / "graveyard"
        templates = load_gravestone_inventory(
            assets, assets / "gravestones_manifest.json").templates
        death_started = time.perf_counter()
        changed = mark_member_dead(
            changed, target.memberId, target_day, "individual",
            gravestone_templates=templates)
        changed = mark_member_dead(changed, collective_target.memberId,
                                   collective_day, "collective")
        changed = set_member_burial_type(
            changed, collective_target.memberId, "individual",
            gravestone_templates=templates)
        changed = set_member_burial_type(changed, target.memberId, "collective")
        death_seconds = time.perf_counter() - death_started
        print(f"CharacterData real data ({source.name}): {len(store.members)} Members, "
              f"{len(store.attendance)} Attendance; first edit "
              f"{first_edit_seconds:.3f}s, death {death_seconds:.3f}s")
        changed_member = next(item for item in changed.members if item.memberId == target.memberId)
        self.assertEqual((changed_member.lifeStatus, changed_member.deathDate,
                          changed_member.lastChecked), ("dead", target_day, target_day))
        self.assertEqual(changed_member.playerId, target.playerId)
        collective_member = next(item for item in changed.members
                                 if item.memberId == collective_target.memberId)
        self.assertEqual((changed_member.burialType, collective_member.burialType),
                         ("collective", "individual"))
        self.assertEqual(collective_member.deathDate, collective_day)
        self.assertEqual(collective_member.playerId, collective_target.playerId)
        self.assertEqual(
            {item.memberId: (item.playerId, item.clmGuid) for item in changed.members},
            {item.memberId: (item.playerId, item.clmGuid) for item in store.members})
        for key in ("raids", "attendance", "legacyClmGuidMemberMap",
                    "eternalDkpRecords", "raidCreditResolutions"):
            self.assertEqual(changed.to_payload()[key], before[key])
        for player in changed.players:
            expected = (None if original_main[player.playerId] in
                        {target.memberId, collective_target.memberId}
                        else original_main[player.playerId])
            self.assertEqual(player.mainMemberId, expected)

        with tempfile.TemporaryDirectory() as directory:
            temporary_save = Path(directory) / "character-data-smoke.ggc"
            save_new_identity_v2(changed, temporary_save)
            restored = load_identity_v2(temporary_save)
            self.assertEqual(restored.to_payload(), changed.to_payload())
        self.assertEqual(store.to_payload(), before)
        self.assertEqual(source.read_bytes(), original_bytes)


if __name__ == "__main__":
    unittest.main()
