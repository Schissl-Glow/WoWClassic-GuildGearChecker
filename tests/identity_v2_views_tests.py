"""Focused read-only V2 roster and raid projections."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.clm_models import ClmCharacterBalance
from app.identity_v2 import Attendance, EternalDkpRecord, IdentityV2Store, Member, Player, Raid
from app.identity_v2_dkp import IdentityV2DkpProjection, available_dkp_by_member
from app.identity_v2_raid_points import V2RaidPointProjection
from app.identity_v2_roster import build_v2_roster_items, filter_sort_v2_roster
from app.identity_v2_views import IdentityV2ViewData
from app.rewards import RewardRegistry


def view_fixture() -> IdentityV2Store:
    return IdentityV2Store(
        members=[
            Member("m1", "Gleich", "Priest", clmGuid="1:1", raidStartDate="2025-01-01"),
            Member("m2", "Gleich", "Mage", clmGuid="1:2", raidStartDate="2025-01-01"),
            Member("m3", "Dritt", "Druid", clmGuid="1:3", raidStartDate="2025-01-01"),
            Member("m4", "Ohne", "Warrior"),
        ],
        raids=[
            Raid("r1", "2025-01-01", name="MC", clmRaidId="clm-1"),
            Raid("r2", "2025-01-02", name="BWL", clmRaidId="clm-2"),
        ],
        attendance=[
            Attendance("a1", "r1", "m1", "main", clmGuid="1:0"),
            Attendance("a2", "r1", "m2", "twink", clmGuid="1:2"),
            Attendance("a3", "r1", "m3", "unknown", clmGuid="1:3"),
            Attendance("a4", "r2", "m1", "main", clmGuid="1:1"),
        ],
        eternalDkpRecords=[
            EternalDkpRecord("d1", "e1", "m1", "1:0", "DM", 3),
            EternalDkpRecord("d2", "e2", "m1", "1:1", "DM", 7),
        ],
        legacyClmGuidMemberMap={"1:0": "m1"},
    )


class IdentityV2ViewsTests(unittest.TestCase):
    def test_v2_roster_frame_follows_player_main_without_using_current_role(self):
        store = IdentityV2Store(
            players=[Player("p1", "Spieler", "m_new")],
            members=[Member("m_old", "Sorap", "Mage", playerId="p1",
                            currentRole="main", clmGuid="1:1"),
                     Member("m_new", "Sorap", "Priest", playerId="p1",
                            currentRole="twink", clmGuid="1:2")],
            eternalDkpRecords=[
                EternalDkpRecord("d1", "e1", "m_old", "1:1", "award", 100),
                EternalDkpRecord("d2", "e2", "m_new", "1:2", "award", 600),
            ],
        )
        points = SimpleNamespace(
            player_points=lambda player_id: 500,
            character_points=lambda member_id: 250,
            eternal_character_points=lambda member_id: 250,
            eternal_player_points=lambda player_id: 500,
        )
        dkp = IdentityV2DkpProjection(store, raid_points_projection=points)
        first = {item.memberId: item for item in build_v2_roster_items(
            store, None, points, dkp, RewardRegistry())}
        self.assertIsNone(first["m_old"].frameAssetId)
        self.assertEqual(first["m_new"].frameAssetId, "frame_02")
        self.assertIsNone(first["m_new"].portraitPath)
        self.assertTrue(first["m_new"].framePath.is_file())
        self.assertIsNotNone(first["m_new"].frameOpening)
        self.assertEqual(first["m_new"].dkpRank, "Eisen_1")
        self.assertEqual(first["m_new"].raidRank, "Holz_3")
        self.assertTrue(first["m_new"].dkpRankPath.is_file())
        self.assertTrue(first["m_new"].raidRankPath.is_file())
        store.players[0].mainMemberId = "m_old"
        dkp = IdentityV2DkpProjection(store, raid_points_projection=points)
        second = {item.memberId: item for item in build_v2_roster_items(
            store, None, points, dkp, RewardRegistry())}
        self.assertEqual(second["m_old"].frameAssetId, "frame_02")
        self.assertIsNone(second["m_new"].frameAssetId)

    def test_v2_roster_icons_cover_wood_stages_and_next_rank(self):
        registry = RewardRegistry()
        for stage in range(1, 7):
            with self.subTest(stage=stage):
                store = IdentityV2Store(
                    members=[Member("m1", "Solo", "Mage", clmGuid="1:1")],
                    eternalDkpRecords=[EternalDkpRecord(
                        "d1", "e1", "m1", "1:1", "award", stage * 100)],
                )
                points = SimpleNamespace(
                    character_points=lambda member_id, value=stage * 80: value,
                    eternal_character_points=lambda member_id, value=stage * 80: value,
                    player_points=lambda player_id: 0,
                )
                dkp = IdentityV2DkpProjection(
                    store, raid_points_projection=points, registry=registry)
                item = build_v2_roster_items(
                    store, None, points, dkp, registry)[0]
                expected = f"Holz_{stage}" if stage <= 5 else "Eisen_1"
                self.assertEqual((item.dkpRank, item.raidRank),
                                 (expected, expected))
                self.assertTrue(item.dkpRankPath.is_file())
                self.assertTrue(item.raidRankPath.is_file())

    def test_shared_roster_projection_keeps_ids_roles_portraits_and_existing_values(self):
        store = IdentityV2Store(
            players=[Player("p1", "Sorap-Spieler", "m_new")],
            members=[
                Member("m_old", "Sorap", "Mage", playerId="p1",
                       currentRole="main", clmGuid="1:1", spec="Frost",
                       raidRole="dps", gearStatus="BiS"),
                Member("m_new", "Sorap", "Priest", playerId="p1",
                       currentRole="twink", clmGuid="1:2", spec="Holy",
                       raidRole="healer"),
                Member("m_dead", "Tot", "Warrior", lifeStatus="dead",
                       deathDate="2026-01-01", burialType="individual"),
                Member("m_inactive", "Pause", "Rogue", lifeStatus="inactive"),
            ],
            raids=[Raid("r1", "2026-01-02", name="MC", raidType="MC")],
            attendance=[Attendance("a1", "r1", "m_old", "twink", playerId="p1"),
                        Attendance("a2", "r1", "m_new", "main", playerId="p1")],
            eternalDkpRecords=[
                EternalDkpRecord("d1", "e1", "m_old", "1:1", "award", 100),
                EternalDkpRecord("d2", "e2", "m_new", "1:2", "award", 200),
            ],
        )
        before = store.to_payload()
        points = V2RaidPointProjection(store)
        available = available_dkp_by_member(store, (
            ClmCharacterBalance("Sorap", 9, "1:1"),
            ClmCharacterBalance("Sorap", 30, "1:2"),
        ))
        dkp = IdentityV2DkpProjection(
            store, available_by_member=available, raid_points_projection=points)
        with TemporaryDirectory() as directory:
            items = build_v2_roster_items(
                store, Path(directory) / "roster.ggc", points, dkp, RewardRegistry())
        by_id = {item.memberId: item for item in items}
        self.assertEqual(set(by_id), {"m_old", "m_new"})
        self.assertEqual((by_id["m_old"].name, by_id["m_new"].name),
                         ("Sorap", "Sorap"))
        self.assertEqual((by_id["m_old"].role, by_id["m_new"].role),
                         ("twink", "main"))
        self.assertEqual((by_id["m_old"].portraitPath.name,
                          by_id["m_new"].portraitPath.name),
                         ("m_old.png", "m_new.png"))
        self.assertEqual((by_id["m_old"].availableDkp,
                          by_id["m_new"].availableDkp), (9, 30))
        self.assertEqual((by_id["m_old"].eternalDkp,
                          by_id["m_new"].eternalDkp), (100, 200))
        self.assertEqual(by_id["m_old"].raidPoints, points.character_points("m_old"))
        self.assertEqual(by_id["m_new"].raidRank, dkp.raid_rank_for_member("m_new"))
        self.assertEqual(by_id["m_new"].raidCount, 1)
        self.assertEqual(by_id["m_new"].lastRaid, "2026-01-02")
        for query, expected in (("Sorap", {"m_old", "m_new"}),
                                ("Sorap-Spieler", {"m_old", "m_new"}),
                                ("Mage", {"m_old"}), ("Frost", {"m_old"}),
                                ("Healer", {"m_new"}), ("BiS", {"m_old"})):
            self.assertEqual({item.memberId for item in
                              filter_sort_v2_roster(items, query=query)}, expected)
        self.assertEqual({item.memberId for item in
                          filter_sort_v2_roster(items, class_name="Priest")}, {"m_new"})
        self.assertEqual(tuple(item.memberId for item in
                               filter_sort_v2_roster(items, sort_key="name")),
                         ("m_new", "m_old"))
        self.assertEqual(tuple(item.memberId for item in
                               filter_sort_v2_roster(items, sort_key="name",
                                                     descending=True)),
                         ("m_new", "m_old"))
        self.assertEqual(store.to_payload(), before)

    def test_roster_rows_aggregate_attendance_and_existing_dkp_path(self):
        store = view_fixture()
        before = store.to_payload()
        data = IdentityV2ViewData.from_store(store)
        self.assertEqual(len(data.roster), 4)
        rows = {row.member_id: row for row in data.roster}
        self.assertEqual((rows["m1"].name, rows["m1"].class_name,
                          rows["m1"].raid_start_date, rows["m1"].raid_count,
                          rows["m1"].eternal_dkp, rows["m1"].primary_guid,
                          rows["m1"].legacy_guid_count),
                         ("Gleich", "Priest", "2025-01-01", 2, 10, "1:1", 1))
        self.assertIsNone(rows["m4"].raid_start_date)
        self.assertEqual(rows["m4"].raid_count, 0)
        self.assertEqual(rows["m1"].eternal_dkp, store.eternal_dkp_for_member("m1"))
        self.assertFalse(hasattr(rows["m1"], "current_role"))
        self.assertEqual(store.to_payload(), before)

    def test_raids_and_details_use_member_id_and_preserve_historical_roles(self):
        store = view_fixture()
        data = IdentityV2ViewData.from_store(store)
        raids = {row.raid_id: row for row in data.raids}
        self.assertEqual((raids["r1"].date, raids["r1"].name,
                          raids["r1"].participant_count, raids["r1"].clm_raid_id),
                         ("2025-01-01", "MC", 3, "clm-1"))
        details = data.attendance_by_raid["r1"]
        self.assertEqual(len(details), 3)
        self.assertEqual({row.historical_role for row in details},
                         {"main", "twink", "unknown"})
        same_name = [row for row in details if row.name == "Gleich"]
        self.assertEqual({row.member_id for row in same_name}, {"m1", "m2"})
        self.assertEqual({row.class_name for row in same_name}, {"Priest", "Mage"})
        self.assertEqual(next(row.source_guid for row in details if row.member_id == "m1"),
                         "1:0")
        self.assertEqual(raids["r2"].participant_count, 1)


if __name__ == "__main__":
    unittest.main()
