"""Gezielte Backend-Tests für Raidpunkte und projektbezogene Persistenz."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.GuildGearChecker import GuildModel
from app.raid_attendance import Raid, RaidAttendance
from app.raid_points import (
    RaidPointConflictError, RaidPointState, RaidPointsError,
    base_points_for_status, build_point_history, character_points, player_points,
)


def attendance(
    attendance_id: str, raid_id: str, player_id: str, member_id: str,
    status: str = "present", character: str = "Character",
) -> RaidAttendance:
    return RaidAttendance(
        attendance_id, raid_id, player_id, member_id, "main",
        f"Player {player_id}", character, status,
    )


class RaidPointTests(unittest.TestCase):
    def test_present_and_bench_base_points(self):
        self.assertEqual(base_points_for_status("present"), 10)
        self.assertEqual(base_points_for_status("bench"), 5)

    def test_positive_negative_adjustments_and_zero_clamp(self):
        raids = [
            Raid("r1", "2026-01-01", "First", status="recorded"),
            Raid("r2", "2026-01-02", "Second", status="recorded"),
            Raid("r3", "2026-01-03", "Third", status="recorded"),
        ]
        records = [
            attendance("a1", "r1", "p1", "m1"),
            attendance("a2", "r2", "p1", "m1", "bench"),
            attendance("a3", "r3", "p1", "m1", "bench"),
        ]
        state = RaidPointState()
        state.activate((raid.id for raid in raids), include_existing=True)
        state.set_adjustment("a1", 1, "Kurzfristig eingesprungen")
        state.set_adjustment("a2", -1, "Buff fehlt")
        state.set_adjustment("a3", -8, "Starke Kürzung")
        history = build_point_history(state, raids, records, player_id="p1")
        self.assertEqual([entry.total_points for entry in history], [11, 4, 0])
        with self.assertRaises(RaidPointsError):
            state.set_adjustment("a1", 2, "")

    def test_player_aggregation_uses_main_and_twink_without_double_counting(self):
        raids = [
            Raid("r1", "2026-01-01", "Main raid", status="recorded"),
            Raid("r2", "2026-01-02", "Twink raid", status="recorded"),
        ]
        records = [
            attendance("a1", "r1", "p1", "m-main", character="Main"),
            attendance("a2", "r2", "p1", "m-twink", character="Twink"),
        ]
        state = RaidPointState()
        state.activate((raid.id for raid in raids), include_existing=True)
        self.assertEqual(player_points(state, raids, records, "p1"), 20)
        self.assertEqual(character_points(state, raids, records, "m-main"), 10)
        self.assertEqual(character_points(state, raids, records, "m-twink"), 10)
        self.assertEqual(
            [entry.member_id for entry in build_point_history(
                state, raids, records, player_id="p1",
            )],
            ["m-main", "m-twink"],
        )

    def test_main_twink_conflict_is_explicit_and_never_counted(self):
        raids = [Raid("r1", "2026-01-01", "Conflict", status="recorded")]
        records = [
            attendance("a1", "r1", "p1", "m-main", character="Main"),
            attendance("a2", "r1", "p1", "m-twink", character="Twink"),
        ]
        state = RaidPointState()
        state.activate(["r1"], include_existing=True)
        with self.assertRaises(RaidPointConflictError) as raised:
            player_points(state, raids, records, "p1")
        self.assertEqual(raised.exception.conflicts[0].member_ids, ("m-main", "m-twink"))

    def test_activation_from_now_and_reactivation_track_only_paused_raids(self):
        state = RaidPointState()
        state.register_raid("old")
        state.activate(["old"], include_existing=False)
        self.assertNotIn("old", state.included_raid_ids)
        state.register_raid("new")
        self.assertIn("new", state.included_raid_ids)
        state.deactivate()
        state.register_raid("paused")
        self.assertIn("paused", state.pending_raid_ids)
        state.activate(["old", "new", "paused"], include_existing=True)
        self.assertIn("paused", state.included_raid_ids)
        self.assertNotIn("old", state.included_raid_ids)

    def test_retrospective_activation_adds_only_base_points(self):
        raid = Raid("r1", "2026-01-01", "Historic", status="recorded")
        record = attendance("a1", "r1", "p1", "m1", "bench")
        state = RaidPointState()
        state.activate([raid.id], include_existing=True)
        history = build_point_history(state, [raid], [record])
        self.assertEqual((history[0].base_points, history[0].adjustment, history[0].reason),
                         (5, 0, ""))

    def test_deactivation_preserves_adjustments_but_blocks_new_changes(self):
        state = RaidPointState()
        state.activate(["r1"], include_existing=True)
        state.set_adjustment("a1", -1, "Buff fehlt")
        state.deactivate()
        restored = RaidPointState.from_dict(state.to_dict())
        self.assertFalse(restored.enabled)
        self.assertEqual(restored.adjustments["a1"].value, -1)
        with self.assertRaises(RaidPointsError):
            restored.set_adjustment("a2", 1, "Eingesprungen")

    def test_project_roundtrip_keeps_guild_and_non_derivable_point_state(self):
        model = GuildModel()
        model.new_empty()
        model.guild_name = "Bierstube"
        model.dkp_enabled = True
        model.clm_roster_id = "1730228604"
        raid = model.create_raid("2026-01-01", "MC")
        model.activate_raid_points(include_existing=True)
        model.raid_points.exclude_attendance(["a-merge-loser"])
        payload = model.to_payload()
        self.assertEqual(payload["formatVersion"], 4)
        self.assertEqual(payload["guildName"], "Bierstube")
        self.assertTrue(payload["dkpModeEnabled"])
        self.assertEqual(payload["clmRosterId"], "1730228604")
        loaded = GuildModel()
        loaded.load_payload(payload)
        self.assertEqual(loaded.guild_name, "Bierstube")
        self.assertTrue(loaded.dkp_enabled)
        self.assertEqual(loaded.clm_roster_id, "1730228604")
        self.assertIn(raid.id, loaded.raid_points.included_raid_ids)
        self.assertIn("a-merge-loser", loaded.raid_points.excluded_attendance_ids)

    def test_scope_rebuild_recovers_empty_legacy_cache_for_all_raids(self):
        raids = [
            Raid("r1", "2026-05-31", "Before", status="recorded"),
            Raid("r2", "2026-06-01", "At", status="recorded"),
            Raid("r3", "2026-06-02", "After", status="recorded"),
        ]
        state = RaidPointState(enabled=True, ever_enabled=True)
        state.set_calculation_scope("all")
        state.rebuild_scope(raids)
        self.assertEqual(state.included_raid_ids, {"r1", "r2", "r3"})

    def test_scope_rebuild_from_date_uses_raid_date_inclusively(self):
        raids = [
            Raid("r1", "2026-05-31", "Before", status="recorded"),
            Raid("r2", "2026-06-01", "At", status="recorded"),
            Raid("r3", "2026-06-02", "After", status="recorded"),
        ]
        state = RaidPointState(enabled=True, ever_enabled=True)
        state.set_calculation_scope("from_date", "2026-06-01")
        state.rebuild_scope(raids)
        self.assertEqual(state.included_raid_ids, {"r2", "r3"})

    def test_raw_legacy_payload_keeps_scope_migration_required(self):
        model = GuildModel()
        model.load_payload({
            "formatVersion": 4,
            "pointMode": "raid_points",
            "raidPoints": {"enabled": True, "everEnabled": True, "includedRaidIds": []},
            "members": [], "players": [], "raids": [], "raidAttendance": [],
        })
        self.assertTrue(model.raid_points_legacy_scope_required)
        self.assertIsNone(model.raid_points.calculation_mode)


if __name__ == "__main__":
    unittest.main()
