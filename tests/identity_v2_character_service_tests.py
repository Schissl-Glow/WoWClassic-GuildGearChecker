"""Focused model and service checks for V2 character data."""

import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.identity_v2 import (  # noqa: E402
    Attendance, CsvRaidSource, IdentityV2Store, IdentityV2ValidationError,
    Member, Player, Raid, RaidCreditResolution, portrait_eligible_members,
)
from app.identity_v2_character_rows import character_table_rows  # noqa: E402
from app.identity_v2_character_service import (  # noqa: E402
    CharacterDataError, DeathAttendanceConflict, MemberEdit, apply_member_edits,
    create_manual_character,
    clear_member_death_marking, confirm_member_check, correct_member_death_date,
    mark_member_dead, set_member_class, set_member_gear_status, set_member_note,
    set_member_race, set_member_raid_role, set_member_raid_status, set_member_spec,
    set_member_burial_type, set_members_irrelevant,
)
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2  # noqa: E402
from app.gravestone_templates import GravestoneTemplate  # noqa: E402
from app.raid_points import ManualRaidPointAdjustment  # noqa: E402


def sample_store() -> IdentityV2Store:
    return IdentityV2Store(
        players=[Player("p1", "Spieler", "m1")],
        members=[
            Member("m1", "Ânní", "Mage", playerId="p1", clmGuid="G-MAIN",
                   currentRole="twink"),
            Member("m2", "Bífi", "Hunter", playerId="p1", clmGuid="G-TWINK",
                   currentRole="main"),
            Member("m3", "Unbekannt", None),
        ],
        raids=[Raid("r1", "2026-03-15", name="MC"),
               Raid("r2", "2026-03-16", name="BWL")],
        attendance=[
            Attendance("a1", "r1", "m1", "unknown", playerId="p1", clmGuid="G-MAIN"),
            Attendance("a2", "r2", "m1", "twink", playerId="p1", clmGuid="G-MAIN"),
            Attendance("a3", "r1", "m2", "main", playerId="p1", clmGuid="G-TWINK"),
        ],
        legacyClmGuidMemberMap={"G-OLD": "m1"},
    )


class IdentityV2CharacterServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = sample_store()
        self.store.validate()
        self.templates = tuple(GravestoneTemplate(
            f"grave-{index}", f"grave-{index}.png", f"hash-{index}",
            Path(f"grave-{index}.png"), category="Menschen",
            default_portrait_offset_x=0.2,
            default_portrait_offset_y=-0.1,
            default_portrait_zoom=1.4,
        ) for index in range(1, 4))

    def test_old_payload_defaults_and_temp_save_reload(self):
        old = self.store.to_payload()
        for member in old["members"]:
            for key in ("race", "spec", "raidRole", "gearStatus", "raidStatus",
                        "note", "lastChecked"):
                member.pop(key, None)
        loaded = IdentityV2Store.from_payload(old)
        self.assertEqual((loaded.members[0].race, loaded.members[0].spec,
                          loaded.members[0].raidRole, loaded.members[0].gearStatus,
                          loaded.members[0].raidStatus, loaded.members[0].note,
                          loaded.members[0].lastChecked),
                         (None, None, "not_set", "Level", "", "", None))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "character-v2.ggc"
            save_new_identity_v2(loaded, target)
            restored = load_identity_v2(target)
        self.assertEqual(restored.to_payload(), loaded.to_payload())
        for key in ("players", "raids", "attendance", "legacyClmGuidMemberMap"):
            self.assertEqual(restored.to_payload()[key], old[key])

    def test_manual_character_uses_v2_identity_and_existing_player_services(self):
        before = self.store.to_payload()
        changed, member_id = create_manual_character(
            self.store, "  Neu  ", "Mage", "p1", "twink")
        self.assertEqual(member_id, "m1000")
        created = next(member for member in changed.members
                       if member.memberId == member_id)
        self.assertEqual((created.name, created.className, created.playerId,
                          created.lifeStatus, created.gearStatus, created.raidRole),
                         ("Neu", "Mage", "p1", "active", "Level", "not_set"))
        self.assertEqual(changed.players[0].mainMemberId, "m1")
        self.assertEqual(changed.attendance, self.store.attendance)
        self.assertEqual(changed.eternalDkpRecords, self.store.eternalDkpRecords)
        self.assertEqual(changed.currentDkpByMemberId, self.store.currentDkpByMemberId)
        self.assertEqual(self.store.to_payload(), before)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "manual.ggc"
            save_new_identity_v2(changed, target)
            restored = load_identity_v2(target)
        self.assertEqual(restored.to_payload(), changed.to_payload())

        unknown, unknown_id = create_manual_character(self.store, "Ohne Spieler", None)
        self.assertEqual(unknown_id, "m1000")
        self.assertIsNone(unknown.members[-1].playerId)
        promoted, main_id = create_manual_character(
            self.store, "Neuer Main", "Priest", "p1", "main")
        self.assertEqual(promoted.players[0].mainMemberId, main_id)
        self.assertEqual(len(promoted.players[0].mainHistory), 1)
        self.assertEqual(promoted.attendance, self.store.attendance)

    def test_manual_character_blocks_live_duplicate_and_preserves_dead_incarnation(self):
        with self.assertRaises(CharacterDataError):
            create_manual_character(self.store, "B\u00cdFI", "Hunter")
        with self.assertRaises(CharacterDataError):
            create_manual_character(self.store, "", "Mage")
        self.assertEqual(len(self.store.members), 3)
        historical = IdentityV2Store(members=[
            Member("m1000", "Soregdrei", "Mage", lifeStatus="dead",
                   deathDate="2026-02-01", burialType="collective"),
        ])
        reincarnated, member_id = create_manual_character(
            historical, "Soregdrei", "Mage")
        self.assertEqual(member_id, "m1001")
        self.assertEqual(reincarnated.members[0].lifeStatus, "dead")
        self.assertEqual(reincarnated.members[1].lifeStatus, "active")

    def test_irrelevant_member_roundtrip_and_attendance_invariant(self):
        unknown = next(item for item in self.store.members if item.memberId == "m3")
        self.assertFalse(unknown.irrelevant)
        unknown.irrelevant = True
        payload = self.store.to_payload()
        self.assertTrue(next(item for item in payload["members"]
                             if item["memberId"] == "m3")["irrelevant"])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "irrelevant-v2.ggc"
            save_new_identity_v2(self.store, target)
            restored = load_identity_v2(target)
        self.assertTrue(next(item for item in restored.members
                             if item.memberId == "m3").irrelevant)
        self.assertIsNone(next(item for item in restored.members
                               if item.memberId == "m3").playerId)
        restored.attendance.append(Attendance("a4", "r1", "m3", "unknown"))
        with self.assertRaisesRegex(IdentityV2ValidationError, "keine Attendance"):
            restored.validate()

    def test_irrelevant_never_enters_portrait_candidates_even_with_full_metadata(self):
        self.store.members[2].irrelevant = True
        self.store.members[2].className = "Mage"
        self.store.members[2].race = "Human"
        self.assertEqual({item.memberId for item in portrait_eligible_members(
            self.store.members)}, {"m1", "m2"})

    def test_mark_many_irrelevant_cleans_attendance_and_restore_does_not_recreate_it(self):
        self.store.members.append(Member("m4", "Portchar", "Mage"))
        self.store.raids[0].csvSources = (CsvRaidSource("raid-source.csv"),)
        self.store.raids.append(Raid("r3", "2026-03-17", name="Onyxia"))
        self.store.attendance.extend((
            Attendance("a4", "r1", "m3", "unknown", playerId="p1"),
            Attendance("a5", "r2", "m3", "unknown", status="bench"),
            Attendance("a6", "r1", "m4", "unknown"),
            Attendance("a7", "r3", "m3", "unknown"),
        ))
        self.store.raidCreditResolutions.append(
            RaidCreditResolution("r1", "p1", "m3"))
        self.store.raidPoints.adjustments["a4"] = ManualRaidPointAdjustment(
            "a4", 5, "Historische Korrektur")
        self.store.validate()
        before = self.store.to_payload()
        changed = set_members_irrelevant(self.store, ("m3", "m4"), True)
        self.assertEqual(self.store.to_payload(), before)
        self.assertEqual({item.memberId for item in changed.members if item.irrelevant},
                         {"m3", "m4"})
        self.assertEqual(len(changed.players), len(self.store.players))
        self.assertEqual({item.memberId: item.lifeStatus for item in changed.members
                          if item.irrelevant}, {"m3": "active", "m4": "active"})
        self.assertEqual({item.attendanceId for item in changed.attendance},
                         {"a1", "a2", "a3"})
        self.assertEqual(changed.raidPoints.adjustments, {})
        self.assertEqual(changed.raidCreditResolutions, [])
        self.assertEqual(changed.raids[0].csvSources,
                         (CsvRaidSource("raid-source.csv"),))
        self.assertEqual({item.memberId: item.playerId for item in changed.members
                          if item.irrelevant}, {"m3": None, "m4": None})
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "irrelevant-batch.ggc"
            save_new_identity_v2(changed, target)
            restored = load_identity_v2(target)
        reopened = set_members_irrelevant(restored, ("m3", "m4"), False)
        self.assertFalse(any(item.irrelevant for item in reopened.members))
        self.assertEqual({item.attendanceId for item in reopened.attendance},
                         {"a1", "a2", "a3"})
        with self.assertRaises(CharacterDataError):
            set_members_irrelevant(self.store, ("m3", "missing"), True)
        self.assertEqual(self.store.to_payload(), before)

    def test_character_fields_and_class_spec_rules_are_atomic(self):
        before = self.store.to_payload()
        edited = set_member_race(self.store, "m1", "hUmAn")
        edited = set_member_spec(edited, "m1", "fRoSt")
        edited = set_member_raid_role(edited, "m1", "main_tank")
        edited = set_member_gear_status(edited, "m1", "BiS")
        edited = set_member_raid_status(edited, "m1", "ready")
        edited = set_member_note(edited, "m1", "  Prüfung offen  ")
        member = edited.members[0]
        self.assertEqual((member.race, member.spec, member.raidRole, member.gearStatus,
                          member.raidStatus, member.note),
                         ("Human", "Frost", "tank", "BiS", "Bereit", "Prüfung offen"))
        self.assertEqual(self.store.to_payload(), before)
        self.assertIsNone(member.lastChecked)
        for operation in (
            lambda: set_member_spec(edited, "m1", "Holy"),
            lambda: set_member_race(edited, "m1", "Trollkin"),
            lambda: set_member_gear_status(edited, "m1", "Mythic"),
            lambda: set_member_class(edited, "m1", "Evoker"),
        ):
            snapshot = edited.to_payload()
            with self.assertRaises(CharacterDataError):
                operation()
            self.assertEqual(edited.to_payload(), snapshot)
        switched = set_member_class(edited, "m1", "Priest")
        self.assertEqual((switched.members[0].className, switched.members[0].spec),
                         ("Priest", None))
        cleared = set_member_class(switched, "m1", None)
        self.assertEqual((cleared.members[0].className, cleared.members[0].spec),
                         (None, None))
        self.assertIsNone(set_member_race(edited, "m1", None).members[0].race)
        with self.assertRaises(CharacterDataError):
            set_member_spec(cleared, "m1", "Frost")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "all-character-fields.ggc"
            save_new_identity_v2(edited, target)
            self.assertEqual(load_identity_v2(target).members[0].to_dict(),
                             edited.members[0].to_dict())

    def test_last_checked_changes_only_on_explicit_confirmation(self):
        original = confirm_member_check(self.store, "m1", "2026-03-15")
        for edit in (
            lambda store: set_member_gear_status(store, "m1", "S+"),
            lambda store: set_member_raid_status(store, "m1", "Nicht bereit"),
            lambda store: set_member_class(store, "m1", "Priest"),
            lambda store: set_member_raid_role(store, "m1", "healer"),
        ):
            original = edit(original)
            self.assertEqual(original.members[0].lastChecked, "2026-03-15")
        checked = confirm_member_check(original, "m1", "2026-04-01")
        self.assertEqual(checked.members[0].lastChecked, "2026-04-01")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "checked.ggc"
            save_new_identity_v2(checked, target)
            self.assertEqual(load_identity_v2(target).members[0].lastChecked,
                             "2026-04-01")
        with self.assertRaises(CharacterDataError):
            confirm_member_check(self.store, "m1", "2026-02-30")

    def test_death_conflict_reports_count_and_first_raid_without_mutation(self):
        before = self.store.to_payload()
        with self.assertRaises(DeathAttendanceConflict) as caught:
            mark_member_dead(self.store, "m1", "2026-03-14", "individual",
                             gravestone_templates=self.templates)
        error = caught.exception
        self.assertEqual((error.conflict_count, error.first_raid_date,
                          error.first_raid_id), (2, "2026-03-15", "r1"))
        self.assertEqual(self.store.to_payload(), before)
        with self.assertRaises(DeathAttendanceConflict) as caught:
            mark_member_dead(self.store, "m1", "2026-03-15", "individual",
                             gravestone_templates=self.templates)
        self.assertEqual(caught.exception.conflict_count, 1)
        self.assertEqual(caught.exception.first_raid_date, "2026-03-16")
        self.assertEqual(self.store.to_payload(), before)

    def test_death_on_same_raid_day_auto_promotes_only_valid_successor(self):
        before = self.store.to_payload()
        dead = mark_member_dead(self.store, "m1", "2026-03-16", "individual",
                                gravestone_templates=self.templates)
        self.assertEqual((dead.members[0].lifeStatus, dead.members[0].deathDate,
                          dead.members[0].playerId), ("dead", "2026-03-16", "p1"))
        self.assertEqual(dead.players[0].mainMemberId, "m2")
        self.assertEqual(dead.players[0].mainSinceDate, "2026-03-16")
        self.assertEqual([(item.memberId, item.toDate, item.reason)
                          for item in dead.players[0].mainHistory],
                         [("m1", "2026-03-16", "death")])
        self.assertEqual(dead.players[0].displayName, "Spieler")
        self.assertEqual(dead.members[1].to_dict(), self.store.members[1].to_dict())
        for key in ("raids", "attendance", "legacyClmGuidMemberMap", "eternalDkpRecords"):
            self.assertEqual(dead.to_payload()[key], before[key])
        self.assertEqual(dead.attendance[1].attendanceType, "twink")
        self.assertEqual(dead.members[0].clmGuid, "G-MAIN")
        self.assertEqual(self.store.to_payload(), before)
        with self.assertRaises(CharacterDataError):
            mark_member_dead(dead, "m1", "2026-03-16", "individual",
                             gravestone_templates=self.templates)
        with self.assertRaises(CharacterDataError):
            mark_member_dead(self.store, "m1", "2026-02-30", "individual",
                             gravestone_templates=self.templates)

    def test_twink_death_keeps_main_and_member_ownership(self):
        dead = mark_member_dead(self.store, "m2", "2026-03-15", "individual",
                                gravestone_templates=self.templates)
        self.assertEqual(dead.players[0].mainMemberId, "m1")
        self.assertEqual((dead.members[1].lifeStatus, dead.members[1].playerId),
                         ("dead", "p1"))
        self.assertEqual(dead.attendance, self.store.attendance)
        self.assertEqual(dead.legacyClmGuidMemberMap, self.store.legacyClmGuidMemberMap)

    def test_burial_required_and_switch_preserves_all_other_data(self):
        self.store.members[1].graveTemplateId = "grave-7"
        before = self.store.to_payload()
        with self.assertRaises(CharacterDataError):
            mark_member_dead(self.store, "m2", "2026-03-15")
        with self.assertRaises(CharacterDataError):
            mark_member_dead(self.store, "m2", "2026-03-15", "pending")
        self.assertEqual(self.store.to_payload(), before)
        dead = mark_member_dead(self.store, "m2", "2026-03-15", "collective")
        self.assertEqual(dead.members[1].burialType, "collective")
        self.assertEqual(dead.players[0].mainMemberId, "m1")
        for burial_type in ("individual", "collective"):
            previous = dead.to_payload()
            dead = set_member_burial_type(dead, "m2", burial_type)
            self.assertEqual(dead.members[1].burialType, burial_type)
            previous["members"][1]["burialType"] = burial_type
            self.assertEqual(dead.to_payload(), previous)
        with self.assertRaises(CharacterDataError):
            set_member_burial_type(self.store, "m1", "individual")
        with self.assertRaises(CharacterDataError):
            set_member_burial_type(dead, "m2", "unknown")

    def test_collective_main_death_promotes_successor_and_roundtrips(self):
        dead = mark_member_dead(self.store, "m1", "2026-03-16", "collective")
        self.assertEqual(dead.players[0].mainMemberId, "m2")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "burial-v2.ggc"
            save_new_identity_v2(dead, target)
            restored = load_identity_v2(target)
        self.assertEqual(restored.to_payload(), dead.to_payload())
        self.assertEqual(restored.members[0].burialType, "collective")

    def test_correct_death_date_preserves_every_other_field_and_history(self):
        dead = mark_member_dead(self.store, "m1", "2026-03-16", "collective")
        dead.members[0].graveTemplateId = "grave-7"
        dead.members[0].portraitOffsetX = 0.25
        dead.members.append(Member("m4", "Ânní", "Mage", lifeStatus="dead",
                                   deathDate="2026-03-10", burialType="individual"))
        dead.validate()
        before = dead.to_payload()
        corrected = correct_member_death_date(dead, "m1", "2026-03-17")
        expected = copy.deepcopy(before)
        expected["members"][0]["deathDate"] = "2026-03-17"
        self.assertEqual(corrected.to_payload(), expected)
        self.assertEqual(dead.to_payload(), before)
        self.assertIs(correct_member_death_date(corrected, "m1", "2026-03-17"), corrected)
        self.assertEqual(corrected.players[0].mainMemberId, "m2")
        self.assertEqual(corrected.members[-1].to_dict(), dead.members[-1].to_dict())
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "corrected.ggc"
            save_new_identity_v2(corrected, target)
            self.assertEqual(load_identity_v2(target).to_payload(), expected)

    def test_undated_old_death_and_attendance_conflict(self):
        dead = copy.deepcopy(self.store)
        dead.members[0].lifeStatus = "dead"
        dead.members[0].burialType = "individual"
        dead.players[0].mainMemberId = "m2"
        dead.validate()
        original = dead.to_payload()
        corrected = correct_member_death_date(dead, "m1", "2026-03-16")
        self.assertEqual(corrected.members[0].deathDate, "2026-03-16")
        with self.assertRaises(DeathAttendanceConflict) as caught:
            correct_member_death_date(dead, "m1", "2026-03-15")
        self.assertEqual((caught.exception.conflict_count,
                          caught.exception.first_raid_date,
                          caught.exception.first_raid_id), (1, "2026-03-16", "r2"))
        self.assertEqual(dead.to_payload(), original)
        for invalid in ("2026-02-30", "March 16", None):
            with self.assertRaises(CharacterDataError):
                correct_member_death_date(dead, "m1", invalid)
        with self.assertRaises(CharacterDataError):
            correct_member_death_date(self.store, "m1", "2026-03-16")

    def test_clear_death_marking_preserves_identity_raids_grave_and_main(self):
        for burial in ("individual", "collective"):
            for target_status in ("active", "inactive"):
                with self.subTest(burial=burial, status=target_status):
                    dead = mark_member_dead(
                        self.store, "m1", "2026-03-16", burial,
                        gravestone_templates=self.templates)
                    dead.members[0].graveTemplateId = "grave-7"
                    dead.members[0].portraitOffsetX = 0.4
                    dead.members[0].textScale = 1.2
                    dead.members[0].lastChecked = "2026-03-14"
                    dead.members.append(Member("m4", "Ânní", "Mage", playerId="p1"))
                    dead.validate()
                    before = dead.to_payload()
                    cleared = clear_member_death_marking(dead, "m1", target_status)
                    expected = copy.deepcopy(before)
                    expected["members"][0].update(
                        lifeStatus=target_status, burialType=None)
                    expected["members"][0].pop("deathDate")
                    self.assertEqual(cleared.to_payload(), expected)
                    self.assertEqual(dead.to_payload(), before)
                    self.assertEqual(cleared.players[0].mainMemberId, "m2")
                    self.assertEqual(cleared.players[0].mainHistory,
                                     dead.players[0].mainHistory)
                    self.assertEqual(cleared.members[-1].to_dict(), dead.members[-1].to_dict())
                    with tempfile.TemporaryDirectory() as directory:
                        target = Path(directory) / "cleared.ggc"
                        save_new_identity_v2(cleared, target)
                        self.assertEqual(load_identity_v2(target).to_payload(), expected)

        no_main = copy.deepcopy(dead)
        no_main.players[0].mainMemberId = None
        no_main.players[0].mainSinceDate = None
        no_main.validate()
        self.assertIsNone(clear_member_death_marking(
            no_main, "m1", "active").players[0].mainMemberId)
        for invalid in ("dead", "", None):
            with self.assertRaises(CharacterDataError):
                clear_member_death_marking(dead, "m1", invalid)
        with self.assertRaises(CharacterDataError):
            clear_member_death_marking(self.store, "m1", "active")

    def test_all_ordinary_edits_leave_player_main_and_raid_history_untouched(self):
        before = self.store.to_payload()
        edits = (
            lambda value: set_member_class(value, "m1", "Priest"),
            lambda value: set_member_race(value, "m1", "Gnome"),
            lambda value: set_member_spec(value, "m1", "Holy"),
            lambda value: set_member_raid_role(value, "m1", "healer"),
            lambda value: set_member_gear_status(value, "m1", "Pre-BiS"),
            lambda value: set_member_raid_status(value, "m1", "Bereit"),
            lambda value: set_member_note(value, "m1", "Notiz"),
            lambda value: confirm_member_check(value, "m1", "2026-04-01"),
        )
        changed = self.store
        for edit in edits:
            changed = edit(changed)
            payload = changed.to_payload()
            for key in ("players", "raids", "attendance", "legacyClmGuidMemberMap"):
                self.assertEqual(payload[key], before[key])
            self.assertEqual(payload["members"][0]["playerId"], "p1")
            self.assertEqual(payload["members"][0]["currentRole"], "twink")

    def test_validator_rejects_invalid_new_fields_without_repair(self):
        variants = (
            ("className", "Evoker"), ("race", "Void Elf"),
            ("spec", "Holy"), ("raidRole", "main_tank"),
            ("gearStatus", "Mythic"), ("raidStatus", "Vielleicht"),
            ("lastChecked", "2026-02-30"), ("deathDate", "gestern"),
        )
        for field_name, value in variants:
            invalid = copy.deepcopy(self.store)
            setattr(invalid.members[0], field_name, value)
            with self.subTest(field_name=field_name), self.assertRaises(
                    IdentityV2ValidationError):
                invalid.validate()

    def test_read_only_rows_derive_player_role_and_actual_last_raid(self):
        before = self.store.to_payload()
        rows = {row.memberId: row for row in character_table_rows(self.store)}
        self.assertEqual((rows["m1"].playerName, rows["m1"].playerRole),
                         ("Spieler", "main"))
        self.assertEqual((rows["m2"].playerName, rows["m2"].playerRole),
                         ("Spieler", "twink"))
        self.assertEqual((rows["m1"].raidCount, rows["m1"].lastRaidDate),
                         (2, "2026-03-16"))
        self.assertEqual((rows["m3"].raidCount, rows["m3"].lastRaidDate,
                          rows["m3"].playerName), (0, None, None))
        self.assertFalse(rows["m1"].isDead)
        edited = set_member_race(self.store, "m1", "Human")
        edited = set_member_spec(edited, "m1", "Frost")
        edited_row = {row.memberId: row for row in character_table_rows(edited)}["m1"]
        self.assertEqual((edited_row.race, edited_row.className, edited_row.spec),
                         ("Human", "Mage", "Frost"))
        dead = mark_member_dead(self.store, "m2", "2026-03-15", "individual",
                                gravestone_templates=self.templates)
        dead_row = {row.memberId: row for row in character_table_rows(dead)}["m2"]
        self.assertEqual((dead_row.isDead, dead_row.deathDate),
                         (True, "2026-03-15"))
        self.assertEqual(self.store.to_payload(), before)

    def test_batch_combines_class_and_spec_and_validates_once(self):
        before = self.store.to_payload()
        edits = (
            MemberEdit("m3", "spec", "Frost"),
            MemberEdit("m3", "className", "Mage"),
            MemberEdit("m3", "race", "Human"),
            MemberEdit("m3", "raidRole", "dps"),
            MemberEdit("m3", "gearStatus", "BiS"),
            MemberEdit("m3", "raidStatus", "Bereit"),
            MemberEdit("m3", "note", "Mehrzeilig\nnotiert"),
            MemberEdit("m1", "className", "Priest"),
            MemberEdit("m1", "spec", "Holy"),
            MemberEdit("m1", "race", "Gnome"),
            MemberEdit("m1", "raidRole", "healer"),
            MemberEdit("m1", "gearStatus", "Pre-BiS"),
            MemberEdit("m1", "raidStatus", "Nicht bereit"),
            MemberEdit("m1", "note", "Andere Notiz"),
            MemberEdit("m2", "className", "Warrior"),
            MemberEdit("m2", "spec", "Fury"),
            MemberEdit("m2", "race", "Dwarf"),
            MemberEdit("m2", "raidRole", "tank"),
            MemberEdit("m2", "gearStatus", "S+"),
            MemberEdit("m2", "raidStatus", "Bereit"),
        )
        self.assertEqual(len(edits), 20)
        from unittest.mock import patch
        from app import identity_v2_character_service as service
        original_validate = IdentityV2Store.validate
        with (patch.object(service.copy, "deepcopy", wraps=copy.deepcopy) as deepcopy,
              patch.object(IdentityV2Store, "validate", autospec=True,
                           side_effect=original_validate) as validate):
            changed = apply_member_edits(self.store, edits)
        self.assertEqual(deepcopy.call_count, 1)
        self.assertEqual(validate.call_count, 1)
        self.assertEqual((changed.members[2].className, changed.members[2].spec),
                         ("Mage", "Frost"))
        self.assertEqual((changed.members[0].className, changed.members[0].spec),
                         ("Priest", "Holy"))
        self.assertEqual((changed.members[1].className, changed.members[1].spec),
                         ("Warrior", "Fury"))
        self.assertIsNone(changed.members[0].lastChecked)
        for key in ("players", "raids", "attendance", "legacyClmGuidMemberMap"):
            self.assertEqual(changed.to_payload()[key], before[key])
        self.assertEqual(self.store.to_payload(), before)

    def test_invalid_twentieth_batch_edit_rolls_back_all_and_reports_context(self):
        before = self.store.to_payload()
        valid_fields = {
            "m1": {"className": "Priest", "spec": "Holy", "race": "Gnome",
                   "raidRole": "healer", "gearStatus": "Pre-BiS",
                   "raidStatus": "Nicht bereit", "note": "A"},
            "m2": {"className": "Warrior", "spec": "Fury", "race": "Human",
                   "raidRole": "tank", "gearStatus": "BiS",
                   "raidStatus": "Bereit", "note": "B"},
            "m3": {"className": "Mage", "spec": "Frost", "race": "Human",
                   "raidRole": "dps", "note": "C"},
        }
        edits = [MemberEdit(member_id, field, value)
                 for member_id, fields in valid_fields.items()
                 for field, value in fields.items()]
        self.assertEqual(len(edits), 19)
        edits.append(MemberEdit("m3", "gearStatus", "Mythic"))
        with self.assertRaises(CharacterDataError) as caught:
            apply_member_edits(self.store, edits)
        self.assertIn("Unbekannt (m3)", str(caught.exception))
        self.assertIn("gearStatus", str(caught.exception))
        self.assertIn("Mythic", str(caught.exception))
        self.assertEqual(self.store.to_payload(), before)
        for field_name in ("name", "playerId", "lastChecked", "deathDate"):
            with self.assertRaises(CharacterDataError):
                apply_member_edits(self.store, [MemberEdit("m1", field_name, "x")])
        self.assertIs(apply_member_edits(self.store, []), self.store)


if __name__ == "__main__":
    unittest.main()
