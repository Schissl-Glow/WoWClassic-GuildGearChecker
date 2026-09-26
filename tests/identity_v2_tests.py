import json
import sys
import tempfile
import unittest
import shutil
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.identity_v2 import (  # noqa: E402
    Attendance,
    CsvRaidSource,
    EternalDkpRecord,
    IdentityV2Store,
    IdentityV2ValidationError,
    Member,
    Player,
    Raid,
    RaidCreditResolution,
)
from app.identity_v2_storage import load_identity_v2, save_identity_v2  # noqa: E402
from app.clm_models import ClmCharacterBalance  # noqa: E402
from app.identity_v2_dkp import (  # noqa: E402
    IdentityV2DkpProjection, available_dkp_by_member,
)


class IdentityV2ModelTests(unittest.TestCase):
    def setUp(self):
        self.store = IdentityV2Store(
            players=[Player("p-1", "Spieler")],
            members=[
                Member("m-old", "Janos", "Warrior", "dead", "p-1", "ex_main", "Player-1-OLD", burialType="individual"),
                Member("m-new", "Janos", "Warrior", "active", "p-1", "main", "Player-1-NEW", "m-old"),
            ],
            raids=[Raid("r-1", "2026-09-24", "Naxx")],
            attendance=[Attendance("a-1", "r-1", "m-new", "main", playerId="p-1")],
            raidCreditResolutions=[RaidCreditResolution("r-1", "p-1", "m-new")],
            eternalDkpRecords=[
                EternalDkpRecord("e-old", "event-old", "m-old", "Player-1-OLD", "award", 10),
                EternalDkpRecord("e-new", "event-new", "m-new", "Player-1-NEW", "award", 5),
            ],
        )

    def test_same_name_different_guid_stays_two_members_with_same_player(self):
        self.store.validate()
        self.assertEqual(len(self.store.members), 2)
        self.assertNotEqual(self.store.members[0].memberId, self.store.members[1].memberId)
        self.assertEqual(self.store.members[0].name, self.store.members[1].name)
        self.assertNotEqual(self.store.members[0].clmGuid, self.store.members[1].clmGuid)
        self.assertEqual(self.store.members[0].playerId, self.store.members[1].playerId)

    def test_burial_validation_and_old_dead_payload_default(self):
        self.store.validate()
        old_payload = self.store.to_payload()
        old_payload["members"][0].pop("burialType")
        loaded = IdentityV2Store.from_payload(old_payload)
        self.assertEqual(loaded.members[0].burialType, "individual")
        self.assertIsNone(loaded.members[1].burialType)
        for status, burial_type in (("dead", "collective"),
                                    ("active", "individual"),
                                    ("dead", None), ("dead", "pending")):
            candidate = IdentityV2Store.from_payload(self.store.to_payload())
            candidate.members[1].lifeStatus = status
            candidate.members[1].burialType = burial_type
            if status == "dead" and burial_type == "collective":
                candidate.validate()
            else:
                with self.assertRaises(IdentityV2ValidationError):
                    candidate.validate()
        invalid = self.store.to_payload()
        invalid["members"][0]["burialType"] = "pending"
        with self.assertRaises(IdentityV2ValidationError):
            IdentityV2Store.from_payload(invalid)

    def test_continuation_is_a_reference_and_preserves_both_members(self):
        self.assertEqual(self.store.continuation_component("m-new"), {"m-old", "m-new"})
        payload = self.store.to_payload()
        self.assertEqual([item["memberId"] for item in payload["members"]], ["m-old", "m-new"])
        self.assertEqual(payload["members"][0]["lifeStatus"], "dead")

    def test_dkp_projections_keep_raw_member_rows_and_sum_continuation_once(self):
        self.assertEqual(self.store.eternal_dkp_for_member("m-old"), 10)
        self.assertEqual(self.store.eternal_dkp_for_continuation("m-new"), 15)
        self.assertEqual(self.store.eternal_dkp_for_player("p-1"), 15)

    def test_roundtrip_preserves_identity_and_relations(self):
        self.store.legacyClmGuidMemberMap = {"Player-1-HISTORIC": "m-new"}
        with tempfile.TemporaryDirectory() as temp_dir:
            save_path = Path(temp_dir) / "identity-v2.json"
            save_identity_v2(self.store, save_path)
            restored = load_identity_v2(save_path)
        payload = self.store.to_payload()
        self.assertEqual(restored.to_payload(), payload)

    def test_point_mode_roundtrip_and_old_v2_default_preserve_both_systems(self):
        original = self.store.to_payload()
        for mode in ("eternal_dkp", "raid_points"):
            self.store.pointMode = mode
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "mode-v2.ggc"
                save_identity_v2(self.store, path)
                restored = load_identity_v2(path)
            self.assertEqual(restored.pointMode, mode)
            self.assertEqual(restored.eternalDkpRecords, self.store.eternalDkpRecords)
            self.assertEqual(restored.raidPoints, self.store.raidPoints)
        old_payload = dict(original)
        old_payload.pop("pointMode")
        self.assertEqual(IdentityV2Store.from_payload(old_payload).pointMode,
                         "raid_points")
        old_payload["pointMode"] = "invalid"
        with self.assertRaises(IdentityV2ValidationError):
            IdentityV2Store.from_payload(old_payload)

    def test_clm_roster_name_roundtrip_and_optional_old_v2_field(self):
        old_payload = self.store.to_payload()
        self.assertNotIn("clmRosterName", old_payload)
        self.assertIsNone(IdentityV2Store.from_payload(old_payload).clmRosterName)
        self.store.clmRosterName = "Bierstube DKP"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roster-v2.ggc"
            save_identity_v2(self.store, path)
            restored = load_identity_v2(path)
        self.assertEqual(restored.clmRosterName, "Bierstube DKP")
        old_payload["clmRosterName"] = ""
        with self.assertRaises(IdentityV2ValidationError):
            IdentityV2Store.from_payload(old_payload)

    def test_v2_guild_identity_roundtrips_without_legacy_model(self):
        self.store.guildName = "Bierstube"
        self.store.realm = "Stitches"
        restored = IdentityV2Store.from_payload(self.store.to_payload())
        self.assertEqual((restored.guildName, restored.realm),
                         ("Bierstube", "Stitches"))
        older = self.store.to_payload()
        older.pop("guildName")
        older.pop("realm")
        self.assertEqual((IdentityV2Store.from_payload(older).guildName,
                          IdentityV2Store.from_payload(older).realm), ("", ""))

    def test_primary_and_historical_guid_can_resolve_to_one_member(self):
        self.store.legacyClmGuidMemberMap = {"Player-1-HISTORIC": "m-new"}
        self.store.eternalDkpRecords.append(
            EternalDkpRecord("e-historic", "event-historic", "m-new", "Player-1-HISTORIC", "award", 2))
        self.store.validate()
        self.assertEqual(self.store.member_id_for_clm_guid("Player-1-HISTORIC"), "m-new")
        self.assertEqual(self.store.eternal_dkp_for_member("m-new"), 7)

    def test_phase_6c_dkp_uses_guid_member_player_and_eternal_rank_projection(self):
        self.store.legacyClmGuidMemberMap = {"Player-1-HISTORIC": "m-new"}
        self.store.members.append(Member(
            "m-other", "Janos", "Mage", "active", "p-2", "main", "Player-2-NEW",
        ))
        self.store.players.append(Player("p-2", "Anderer Spieler"))
        self.store.eternalDkpRecords.extend((
            EternalDkpRecord("e-historic", "event-historic", "m-new",
                             "Player-1-HISTORIC", "award", 110),
            EternalDkpRecord("e-other", "event-other", "m-other",
                             "Player-2-NEW", "award", 250),
        ))
        balances = (
            ClmCharacterBalance("Janos", 9000, "Player-1-OLD"),
            ClmCharacterBalance("Janos", 12, "Player-1-NEW"),
            ClmCharacterBalance("Janos", 8, "Player-1-HISTORIC"),
            ClmCharacterBalance("Janos", 9000, "Player-2-NEW"),
            ClmCharacterBalance("Janos", 7000, "unmapped-guid"),
        )
        available = available_dkp_by_member(self.store, balances)
        self.assertEqual(available, {"m-old": 9000, "m-new": 20, "m-other": 9000})
        projection = IdentityV2DkpProjection(self.store, available_by_member=available)
        self.assertEqual(projection.eternal_for_member("m-new"), 115)
        self.assertEqual(projection.eternal_for_player("p-1"), 125)
        self.assertEqual(projection.eternal_for_player("p-2"), 250)
        self.assertEqual(projection.dkp_rank_for_member("m-new"), "Holz_1")
        self.assertEqual(projection.dkp_rank_for_player("p-2"), "Holz_2")
        self.assertEqual(projection.available_for_member("m-new"), 20)
        self.assertNotEqual(projection.dkp_rank_for_member("m-new"),
                            projection.dkp_rank_asset(9000))
        raw_records = list(self.store.eternalDkpRecords)
        self.store.members[-1].playerId = "p-1"
        self.store.members[-1].currentRole = "twink"
        reassigned = IdentityV2DkpProjection(self.store, available_by_member=available)
        self.assertEqual(reassigned.eternal_for_member("m-other"), 250)
        self.assertEqual(reassigned.eternal_for_player("p-1"), 375)
        self.assertEqual(reassigned.eternal_for_player("p-2"), 0)
        self.assertEqual(self.store.eternalDkpRecords, raw_records)

    def test_phase_6c_raid_rank_uses_existing_eternal_raid_projection(self):
        points = SimpleNamespace(
            character_points=lambda member_id: 9000,
            eternal_character_points=lambda member_id: 80,
            player_points=lambda player_id: 9000,
            eternal_player_points=lambda player_id: 160,
        )
        projection = IdentityV2DkpProjection(
            self.store, raid_points_projection=points,
        )
        self.assertEqual(projection.raid_points_for_member("m-new"), 9000)
        self.assertEqual(projection.eternal_raid_points_for_member("m-new"), 80)
        self.assertEqual(projection.raid_rank_for_member("m-new"), "Holz_1")
        self.assertEqual(projection.raid_rank_for_player("p-1"), "Holz_2")

    def test_historical_guid_cannot_be_assigned_to_two_members(self):
        self.store.legacyClmGuidMemberMap = {
            "Player-1-HISTORIC": "m-old",
            "player-1-historic": "m-new",
        }
        with self.assertRaisesRegex(IdentityV2ValidationError, "Historische clmGuid"):
            self.store.validate()

    def test_primary_guid_cannot_be_historical_guid_of_another_member(self):
        self.store.legacyClmGuidMemberMap = {"Player-1-OLD": "m-new"}
        with self.assertRaisesRegex(IdentityV2ValidationError, "primär"):
            self.store.validate()

    def test_missing_optional_v2_fields_load_safely(self):
        restored = IdentityV2Store.from_payload({
            "identityFormat": "identity-v2",
            "players": [],
            "members": [{"memberId": "m1", "name": "Ohne Player", "className": "Mage"}],
        })
        self.assertIsNone(restored.members[0].playerId)
        self.assertIsNone(restored.members[0].clmGuid)
        self.assertEqual(restored.attendance, [])

    def test_non_v2_payload_is_not_implicitly_interpreted(self):
        with self.assertRaises(IdentityV2ValidationError):
            IdentityV2Store.from_payload({"members": [{"id": "m1", "name": "Janos"}]})

    def test_legacy_reference_save_is_read_only_and_not_treated_as_v2(self):
        source = ROOT / "testdata" / "output" / "Bierstube_PlayerIdentity_migriert.ggc"
        if not source.is_file():
            self.skipTest("Die optionale lokale Referenzdatei testdata/... fehlt.")
        original_bytes = source.read_bytes()
        try:
            legacy_payload = json.loads(original_bytes.decode("utf-8-sig"))
            self.assertIsInstance(legacy_payload, dict)
            self.assertNotEqual(legacy_payload.get("identityFormat"), "identity-v2")
            with tempfile.TemporaryDirectory() as temp_dir:
                copied_save = Path(temp_dir) / source.name
                shutil.copy2(source, copied_save)
                copied_payload = json.loads(copied_save.read_text(encoding="utf-8-sig"))
                with self.assertRaises(IdentityV2ValidationError):
                    IdentityV2Store.from_payload(copied_payload)
                with self.assertRaisesRegex(IdentityV2ValidationError, "nicht überschrieben"):
                    save_identity_v2(self.store, copied_save)
                self.assertEqual(copied_save.read_bytes(), original_bytes)
            self.assertEqual(source.read_bytes(), original_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.fail(f"Die lokale Referenzdatei ist kein lesbarer JSON-Save: {exc}")

    def test_duplicate_guid_cannot_belong_to_two_members(self):
        self.store.members[1].clmGuid = self.store.members[0].clmGuid
        with self.assertRaisesRegex(IdentityV2ValidationError, "clmGuid"):
            self.store.validate()

    def test_duplicate_member_id_is_rejected(self):
        self.store.members[1].memberId = self.store.members[0].memberId
        with self.assertRaisesRegex(IdentityV2ValidationError, "memberId"):
            self.store.validate()

    def test_self_reference_and_cycles_are_rejected(self):
        self.store.members[0].continuationOfMemberId = "m-old"
        with self.assertRaisesRegex(IdentityV2ValidationError, "sich selbst"):
            self.store.validate()
        self.store.members[0].continuationOfMemberId = "m-new"
        with self.assertRaisesRegex(IdentityV2ValidationError, "Zyklus"):
            self.store.validate()

    def test_unknown_predecessor_and_conflicting_player_are_rejected(self):
        self.store.members[1].continuationOfMemberId = "missing"
        with self.assertRaisesRegex(IdentityV2ValidationError, "Unbekannter Vorgänger"):
            self.store.validate()
        self.store.members[1].continuationOfMemberId = "m-old"
        self.store.players.append(Player("p-2", "Andere Person"))
        self.store.members[1].playerId = "p-2"
        with self.assertRaisesRegex(IdentityV2ValidationError, "widersprüchliche playerId"):
            self.store.validate()

    def test_transitive_player_conflict_across_continuation_is_rejected(self):
        self.store.players.append(Player("p-2", "Andere Person"))
        self.store.members = [
            Member("m-old", "Janos", "Warrior", playerId="p-1", clmGuid="g-old"),
            Member("m-mid", "Janos", "Warrior", continuationOfMemberId="m-old", clmGuid="g-mid"),
            Member("m-new", "Janos", "Warrior", playerId="p-2", clmGuid="g-new", continuationOfMemberId="m-mid"),
        ]
        with self.assertRaisesRegex(IdentityV2ValidationError, "Fortsetzungskomponente"):
            self.store.validate()

    def test_legacy_current_roles_do_not_define_or_limit_player_main(self):
        self.store.members.append(Member("m-third", "Janos", "Mage", playerId="p-1", currentRole="main", clmGuid="Player-1-THIRD"))
        self.store.validate()
        self.assertIsNone(self.store.get_main_member("p-1"))
        self.store.players[0].mainMemberId = "m-new"
        self.store.validate()
        self.assertEqual(self.store.get_main_member("p-1").memberId, "m-new")

    def test_raid_credit_is_unique_per_player_and_raid(self):
        self.store.raidCreditResolutions.append(RaidCreditResolution("r-1", "p-1", "m-old"))
        with self.assertRaisesRegex(IdentityV2ValidationError, "RaidCreditResolution"):
            self.store.validate()

    def test_attendance_type_accepts_only_main_twink_and_unknown(self):
        for role in ("main", "twink", "unknown"):
            with self.subTest(role=role):
                self.store.attendance[0].attendanceType = role
                self.store.validate()
                self.assertEqual(self.store.to_payload()["attendance"][0]["attendanceType"], role)
        self.store.attendance[0].attendanceType = "bench"
        with self.assertRaisesRegex(IdentityV2ValidationError, "attendanceType"):
            self.store.validate()

    def test_unknown_attendance_roundtrip_and_player_assignment_preserve_role(self):
        self.store.attendance[0].attendanceType = "unknown"
        self.store.attendance[0].playerId = None
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "identity-v2.json"
            save_identity_v2(self.store, path)
            restored = load_identity_v2(path)
        self.assertEqual(restored.attendance[0].attendanceType, "unknown")
        self.assertIsNone(restored.attendance[0].playerId)
        restored.attendance[0].playerId = "p-1"
        restored.validate()
        self.assertEqual(restored.attendance[0].attendanceType, "unknown")

    def test_attendance_source_guid_must_resolve_to_its_member(self):
        self.store.attendance[0].clmGuid = "Player-1-OLD"
        self.store.attendance[0].memberId = "m-new"
        with self.assertRaisesRegex(IdentityV2ValidationError, "CLM-GUID"):
            self.store.validate()

    def test_clm_raid_source_id_is_unique(self):
        self.store.raids[0].clmRaidId = "clm-raid-1"
        self.store.raids.append(Raid("r-2", "2026-09-25", "", "Weiterer Raid", "clm-raid-1"))
        with self.assertRaisesRegex(IdentityV2ValidationError, "Raid.clmRaidId"):
            self.store.validate()

    def test_older_v2_raid_without_optional_source_fields_still_roundtrips(self):
        payload = {"identityFormat": "identity-v2", "raids": [
            {"raidId": "r-old", "date": "2026-09-24", "raidType": ""},
        ]}
        restored = IdentityV2Store.from_payload(payload)
        self.assertIsNone(restored.raids[0].clmRaidId)
        self.assertEqual(restored.to_payload()["raids"], payload["raids"])


class IdentityV2PlayerTests(unittest.TestCase):
    def setUp(self):
        self.store = IdentityV2Store(
            players=[Player("p0001", "Gleicher Name"),
                     Player("p0002", "Gleicher Name")],
            members=[
                Member("m1000", "Main", "Mage", playerId="p0001"),
                Member("m1001", "Inaktiv", None, lifeStatus="inactive",
                       playerId="p0001"),
                Member("m1002", "Andere", "Priest", playerId="p0002"),
                Member("m1003", "Unzugeordnet", "Warrior"),
            ],
        )

    def test_empty_players_unassigned_members_and_duplicate_display_names_are_valid(self):
        empty = IdentityV2Store(members=[Member("m1000", "Frei", None)])
        empty.validate()
        self.assertEqual(empty.players, [])
        self.assertIsNone(empty.members[0].playerId)
        self.store.validate()
        self.assertEqual([player.displayName for player in self.store.players],
                         ["Gleicher Name", "Gleicher Name"])
        self.assertTrue(all(player.mainMemberId is None for player in self.store.players))
        self.assertEqual(set(self.store.players[0].to_dict()),
                         {"playerId", "displayName", "mainMemberId",
                          "mainSinceDate", "mainHistory"})

    def test_duplicate_player_id_and_empty_display_name_are_rejected(self):
        self.store.players[1].playerId = "p0001"
        with self.assertRaisesRegex(IdentityV2ValidationError, "playerId"):
            self.store.validate()
        self.store.players[1].playerId = "p0002"
        for invalid in ("", " \t ", None):
            with self.subTest(display_name=invalid):
                self.store.players[1].displayName = invalid
                with self.assertRaisesRegex(IdentityV2ValidationError, "displayName"):
                    self.store.validate()

    def test_main_reference_requires_existing_assigned_living_member(self):
        player = self.store.players[0]
        player.mainMemberId = "missing"
        with self.assertRaisesRegex(IdentityV2ValidationError, "Unbekannte mainMemberId"):
            self.store.validate()
        player.mainMemberId = "m1002"
        with self.assertRaisesRegex(IdentityV2ValidationError, "gehört nicht"):
            self.store.validate()
        player.mainMemberId = "m1001"
        self.store.validate()
        self.assertEqual(self.store.get_main_member("p0001").memberId, "m1001")
        self.store.members[1].lifeStatus = "inactive"
        self.store.validate()
        self.assertEqual(self.store.get_main_member("p0001").memberId, "m1001")
        self.store.members[1].lifeStatus = "dead"
        self.store.members[1].deathDate = "2026-09-26"
        self.store.members[1].burialType = "collective"
        with self.assertRaisesRegex(IdentityV2ValidationError, "tot"):
            self.store.validate()
        self.store.members[1].lifeStatus = "inactive"
        self.store.members[1].deathDate = None
        self.store.members[1].burialType = None
        player.mainMemberId = "m1000"
        self.store.validate()
        self.assertEqual(self.store.get_main_member("p0001").memberId, "m1000")
        self.assertIsNone(self.store.get_main_member("p0002"))

    def test_older_player_payload_without_inactive_snapshot_stays_loadable(self):
        payload = self.store.to_payload()
        self.assertNotIn("inactiveRestoreStates", payload["players"][0])
        restored = IdentityV2Store.from_payload(payload)
        self.assertIsNone(restored.players[0].inactiveRestoreStates)
        self.assertTrue(restored.player_is_active("p0001"))

    def test_member_player_reference_and_read_only_queries(self):
        self.store.validate()
        self.assertEqual(self.store.get_player("p0001"), self.store.players[0])
        self.assertIsNone(self.store.get_player("missing"))
        self.assertEqual(self.store.get_players(), tuple(self.store.players))
        self.assertEqual(tuple(member.memberId for member in
                               self.store.get_members_for_player("p0001")),
                         ("m1000", "m1001"))
        self.assertEqual(tuple(member.memberId for member in
                               self.store.get_unassigned_members()), ("m1003",))
        self.assertEqual(self.store.get_player_for_member("m1000"), self.store.players[0])
        self.assertIsNone(self.store.get_player_for_member("m1003"))
        self.store.members[3].playerId = "missing"
        with self.assertRaisesRegex(IdentityV2ValidationError, "Unbekannte playerId"):
            self.store.validate()

    def test_legacy_member_role_does_not_determine_player_main(self):
        self.store.members[0].currentRole = "main"
        self.store.validate()
        self.assertIsNone(self.store.get_main_member("p0001"))

    def test_player_ids_are_monotonic_across_save_and_deleted_player(self):
        store = IdentityV2Store()
        first = store.create_player("Gleicher Name")
        removed = store.create_player("Gleicher Name")
        self.assertEqual((first.playerId, removed.playerId), ("p0001", "p0002"))
        store.players.remove(removed)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "players.ggc"
            save_identity_v2(store, path)
            restored = load_identity_v2(path)
        third = restored.create_player("Dritter")
        self.assertEqual(third.playerId, "p0003")
        self.assertIsNone(third.mainMemberId)

    def test_players_and_phase_three_records_survive_save_load(self):
        self.store.players[0].mainMemberId = "m1000"
        self.store.members[0].clmGuid = "1:101"
        self.store.members[0].raidStartDate = "2026-04-21"
        self.store.members[2].lifeStatus = "dead"
        self.store.members[2].deathDate = "2026-05-01"
        self.store.members[2].burialType = "individual"
        self.store.legacyClmGuidMemberMap = {"1:100": "m1000"}
        self.store.raids = [Raid(
            "r1", "2026-04-21", "AQ20", "AQ20", "clm-1",
            ("2026-04-21_AQ20_Casts.csv",),
            ("https://vanilla.warcraftlogs.com/reports/AAA",),
            (CsvRaidSource("2026-04-21_AQ20_Casts.csv",
                           "https://vanilla.warcraftlogs.com/reports/AAA"),),
        )]
        self.store.attendance = [Attendance(
            "a1", "r1", "m1000", "unknown", clmGuid="1:101",
        )]
        self.store.ignoredCsvCharacterNames = ["Ignoriert"]
        expected = self.store.to_payload()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "phase4.ggc"
            save_identity_v2(self.store, path)
            restored = load_identity_v2(path)
        self.assertEqual(restored.to_payload(), expected)
        self.assertEqual(restored.players[0].mainMemberId, "m1000")
        self.assertIsNone(restored.players[1].mainMemberId)
        self.assertEqual(restored.members[3].playerId, None)
        self.assertEqual(restored.attendance[0].attendanceType, "unknown")

    def test_phase_three_v2_without_players_loads_without_assignment(self):
        source = IdentityV2Store(
            members=[Member("m1000", "Unbekannt", None, clmGuid="1:101")],
            raids=[Raid("r1", "2026-04-21", name="AQ20", clmRaidId="clm-1")],
            attendance=[Attendance("a1", "r1", "m1000", "unknown",
                                   clmGuid="1:101")],
        ).to_payload()
        source.pop("players")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "phase3.ggc"
            path.write_text(json.dumps(source), encoding="utf-8")
            restored = load_identity_v2(path)
        self.assertEqual(restored.players, [])
        self.assertIsNone(restored.members[0].playerId)
        self.assertEqual((len(restored.members), len(restored.raids),
                          len(restored.attendance)), (1, 1, 1))
        self.assertEqual(restored.attendance[0].attendanceType, "unknown")

    def test_phase_three_player_name_loads_without_losing_identity(self):
        payload = {"identityFormat": "identity-v2",
                   "players": [{"playerId": "p-1", "playerName": "Historisch"}],
                   "members": [{"memberId": "m1000", "name": "Charakter",
                                "className": "Mage", "playerId": "p-1"}]}
        restored = IdentityV2Store.from_payload(payload)
        self.assertEqual((restored.players[0].displayName,
                          restored.players[0].mainMemberId), ("Historisch", None))
        self.assertEqual(restored.members[0].playerId, "p-1")
        self.assertEqual(restored.to_payload()["players"][0]["displayName"],
                         "Historisch")
        payload["players"][0]["displayName"] = "Widerspruch"
        with self.assertRaisesRegex(IdentityV2ValidationError, "widersprüchliche"):
            IdentityV2Store.from_payload(payload)


if __name__ == "__main__":
    unittest.main()
