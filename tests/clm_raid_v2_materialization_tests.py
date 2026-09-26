"""Focused CLM raid-to-V2 materialization tests using temporary stores only."""

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from app.clm_identity_v2_decisions import (
    CONTINUE, NEW_CHARACTER, ClmIdentityDecisionDraft,
)
from app.clm_identity_v2_materialization import build_identity_v2_store_from_clm
from app.clm_raid_v2_analysis import analyze_clm_raid_ledger
from app.clm_raid_v2_materialization import (
    ClmRaidMaterializationError, materialize_clm_raids_into_identity_v2 as import_raids,
    clm_raid_attendance_difference, correct_clm_raid_attendance,
    review_clm_raids, suggest_clm_raid_type,
)
from app.clm_replay import _entry_uuid
from app.clm_v2_refresh import (
    pending_clm_character_groups, raid_participant_identity_analysis,
    refresh_clm_v2_characters, unresolved_raid_participant_guids,
)
from app.identity_v2 import IdentityV2Store, Member
from app.identity_v2_import_choices import CharacterImportChoice
from app.identity_v2_storage import load_identity_v2, save_identity_v2
from app.raid_attendance import raid_category


def stamp(day: int, hour: int = 12) -> int:
    return int(datetime(2025, 1, day, hour, tzinfo=timezone.utc).timestamp())


def event(timestamp, opcode, sequence, **fields):
    return {"_c": timestamp, "_b": 0, "_e": 1, "_a": sequence,
            "_d": opcode, **fields}


def analysis_for(profiles, raids, p2_links=()):
    """Profiles: (guid, name, class ID, P0 day, optional P1 day)."""
    roster = "roster-1"
    events = [event(stamp(1), "R0", 1, r=roster, n="Bierstube", p=0)]
    sequence = 2
    for guid, name, class_id, first_day, removed_day in profiles:
        events.append(event(stamp(first_day, 9), "P0", sequence,
                            g=list(guid), n=f"{name}-Stitches", c=class_id))
        sequence += 1
        events.append(event(stamp(first_day, 9) + 1, "R9", sequence,
                            r=roster, p=[list(guid)]))
        sequence += 1
        if removed_day is not None:
            events.append(event(stamp(removed_day, 18), "P1", sequence, g=list(guid)))
            sequence += 1
    for day, alt, main in p2_links:
        events.append(event(stamp(day, 10), "P2", sequence,
                            g=list(alt), m=list(main)))
        sequence += 1
    for day, name, present, bench, updates in raids:
        start = stamp(day)
        created = event(start, "AC", sequence, r=roster, n=name, c={})
        sequence += 1
        raid_id = _entry_uuid(created)
        events.append(created)
        events.append(event(start + 3600, "AS", sequence, r=raid_id,
                            p=[list(guid) for guid in present],
                            s=[list(guid) for guid in bench]))
        sequence += 1
        for number, update in enumerate(updates):
            events.append(event(start + 7200 + number, "AU", sequence, r=raid_id,
                                j=[list(guid) for guid in update.get("j", ())],
                                l=[list(guid) for guid in update.get("l", ())],
                                s=[list(guid) for guid in update.get("s", ())],
                                e=[list(guid) for guid in update.get("e", ())]))
            sequence += 1
        events.append(event(start + 10800, "AE", sequence, r=raid_id))
        sequence += 1
    return analyze_clm_raid_ledger(events, roster)


def first_import_store(analysis, continuations=()):
    """Test-only decisions; production must obtain them from the user."""
    draft = ClmIdentityDecisionDraft(analysis.identity_analysis)
    for group in analysis.identity_analysis.multi_guid_groups:
        for history in group.guid_histories[1:]:
            action = (CONTINUE if (group.normalized_name, history.guid) in continuations
                      else NEW_CHARACTER)
            draft.set_choice(group.normalized_name, history.guid, action)
    decisions = draft.to_decision_set()
    return build_identity_v2_store_from_clm(analysis.identity_analysis, decisions)


def materialize_clm_raids_into_identity_v2(store, analysis):
    """Supply explicit review choices for existing attendance-focused assertions."""
    return import_raids(store, analysis, {raid.raid_id: "MC" for raid in analysis.raids})


class ClmRaidV2MaterializationTests(unittest.TestCase):
    MAIN = ((1, 101), "Main", 5, 1, None)

    def single_raid(self, *, present=((1, 101),), bench=(), updates=()):
        return analysis_for((self.MAIN,), ((3, "MC", present, bench, updates),))

    def test_raid_identity_scope_excludes_resolved_and_nonparticipant_guids(self):
        analysis = analysis_for((
            self.MAIN, ((1, 102), "Neu", 5, 2, None),
            ((1, 103), "Ohne Raid", 5, 2, None),
        ), ((3, "MC", ((1, 101), (1, 102)), (), ()),))
        store = IdentityV2Store(members=[
            Member("m1000", "Main", "Priest", clmGuid="1:101")])
        self.assertEqual(unresolved_raid_participant_guids(store, analysis),
                         ("1:102",))
        scoped = raid_participant_identity_analysis(analysis, ("1:102",))
        self.assertEqual([item.guid for item in scoped.guid_histories], ["1:102"])
        self.assertEqual(scoped.multi_guid_groups, ())
        decisions = ClmIdentityDecisionDraft(scoped).to_decision_set()
        self.assertEqual(pending_clm_character_groups(store, scoped, decisions),
                         {("1:102",)})
        known = IdentityV2Store(members=[
            Member("m1000", "Main", "Priest", clmGuid="1:101"),
            Member("m1001", "Neu", "Priest", clmGuid="1:102")])
        self.assertEqual(unresolved_raid_participant_guids(known, analysis), ())

    def test_raid_required_guid_can_attach_to_existing_member_without_full_sync(self):
        analysis = analysis_for((
            self.MAIN, ((1, 102), "Main", 5, 2, None),
            ((1, 103), "Ohne Raid", 5, 2, None),
        ), ((3, "MC", ((1, 102),), (), ()),))
        original = IdentityV2Store(members=[
            Member("m1000", "Main", "Priest", clmGuid="1:101")])
        scoped = raid_participant_identity_analysis(
            analysis, unresolved_raid_participant_guids(original, analysis))
        self.assertEqual([item.guid for item in scoped.guid_histories], ["1:102"])
        decisions = ClmIdentityDecisionDraft(scoped).to_decision_set()
        working = refresh_clm_v2_characters(
            original, scoped, decisions,
            {("1:102",): CharacterImportChoice(member_id="m1000")})
        self.assertEqual(working.members[0].clmGuid, "1:102")
        self.assertEqual(working.legacyClmGuidMemberMap["1:101"], "m1000")
        self.assertEqual(unresolved_raid_participant_guids(working, analysis), ())
        filled = import_raids(working, analysis, {analysis.raids[0].raid_id: "MC"})
        self.assertEqual(filled.attendance[0].memberId, "m1000")
        self.assertEqual(len(filled.members), 1)
        self.assertEqual(original.members[0].clmGuid, "1:101")

    def test_raid_required_guid_can_create_new_incarnation(self):
        analysis = analysis_for((
            self.MAIN, ((1, 102), "Main", 5, 2, None),
        ), ((3, "MC", ((1, 102),), (), ()),))
        original = IdentityV2Store(members=[
            Member("m1000", "Main", "Priest", lifeStatus="dead",
                   deathDate="2025-01-02", burialType="collective", clmGuid="1:101")])
        scoped = raid_participant_identity_analysis(
            analysis, unresolved_raid_participant_guids(original, analysis))
        decisions = ClmIdentityDecisionDraft(scoped).to_decision_set()
        working = refresh_clm_v2_characters(
            original, scoped, decisions, {("1:102",): CharacterImportChoice()})
        self.assertEqual([(item.memberId, item.lifeStatus) for item in working.members],
                         [("m1000", "dead"), ("m1001", "active")])
        filled = import_raids(working, analysis, {analysis.raids[0].raid_id: "MC"})
        self.assertEqual(filled.attendance[0].memberId, "m1001")

    def test_one_clm_raid_creates_one_v2_raid_with_source_title_and_date(self):
        analysis = self.single_raid()
        store = materialize_clm_raids_into_identity_v2(first_import_store(analysis), analysis)
        self.assertEqual(len(store.raids), 1)
        raid = store.raids[0]
        self.assertTrue(raid.raidId.startswith("r_"))
        self.assertEqual((raid.clmRaidId, raid.name, raid.date, raid.raidType),
                         (analysis.raids[0].raid_id, "MC", "2025-01-03", "MC"))
        self.assertEqual(raid_category(raid.raidType), "40er")
        self.assertEqual(len(store.attendance), 1)

    def test_multiple_raids_have_distinct_stable_ids(self):
        analysis = analysis_for((self.MAIN,), (
            (3, "MC", ((1, 101),), (), ()),
            (5, "BWL", ((1, 101),), (), ()),
        ))
        base = first_import_store(analysis)
        first = materialize_clm_raids_into_identity_v2(base, analysis)
        second = materialize_clm_raids_into_identity_v2(base, analysis)
        self.assertEqual(len({raid.raidId for raid in first.raids}), 2)
        self.assertEqual(first.to_payload(), second.to_payload())
        self.assertEqual(len({raid.clmRaidId for raid in first.raids}), 2)

    def test_primary_guid_resolves_to_member_and_unknown_role(self):
        analysis = self.single_raid()
        base = first_import_store(analysis)
        store = materialize_clm_raids_into_identity_v2(base, analysis)
        item = store.attendance[0]
        self.assertEqual((item.memberId, item.clmGuid, item.attendanceType),
                         (base.members[0].memberId, "1:101", "unknown"))
        self.assertIsNone(item.playerId)
        self.assertEqual(item.raidId, store.raids[0].raidId)

    def test_legacy_and_primary_guids_resolve_to_one_member_without_double_count(self):
        analysis = analysis_for((
            ((1, 101), "Annî", 5, 1, 2),
            ((1, 102), "Annî", 5, 3, None),
        ), (
            (2, "MC", ((1, 101),), (), ()),
            (4, "BWL", ((1, 102),), (), ()),
        ))
        base = first_import_store(analysis, continuations=(("Annî", "1:102"),))
        self.assertEqual(len(base.members), 1)
        store = materialize_clm_raids_into_identity_v2(base, analysis)
        self.assertEqual(len(store.attendance), 2)
        self.assertEqual({item.memberId for item in store.attendance},
                         {base.members[0].memberId})
        self.assertEqual({item.clmGuid for item in store.attendance}, {"1:101", "1:102"})
        self.assertEqual(store.members[0].raidStartDate, "2025-01-02")

    def test_repeated_source_events_make_one_attendance(self):
        analysis = self.single_raid(updates=({"j": ((1, 101),)},))
        self.assertEqual(analysis.raids[0].participants[0].occurrence_count, 2)
        store = materialize_clm_raids_into_identity_v2(first_import_store(analysis), analysis)
        self.assertEqual(len(store.attendance), 1)

    def test_bank_only_has_no_attendance_and_no_raid_start(self):
        analysis = self.single_raid(present=(), bench=((1, 101),))
        store = materialize_clm_raids_into_identity_v2(first_import_store(analysis), analysis)
        self.assertEqual(len(store.raids), 1)
        self.assertEqual(store.attendance, [])
        self.assertIsNone(store.members[0].raidStartDate)

    def test_bank_then_present_creates_one_attendance(self):
        analysis = self.single_raid(
            present=(), bench=((1, 101),), updates=({"j": ((1, 101),)},),
        )
        store = materialize_clm_raids_into_identity_v2(first_import_store(analysis), analysis)
        self.assertEqual(len(store.attendance), 1)
        self.assertEqual(store.members[0].raidStartDate, "2025-01-03")

    def test_p2_main_twink_and_unlink_never_set_imported_attendance_roles(self):
        analysis = analysis_for((
            ((1, 101), "Main", 5, 1, None),
            ((1, 102), "Alt", 8, 1, None),
        ), (
            (3, "MC", ((1, 101), (1, 102)), (), ()),
            (5, "BWL", ((1, 102),), (), ()),
        ), p2_links=(
            (2, (1, 102), (1, 101)),
            (4, (1, 102), (1, 0)),
        ))
        self.assertEqual({item.guid: item.historical_role
                          for item in analysis.raids[0].participants},
                         {"1:101": "main", "1:102": "twink"})
        self.assertEqual(analysis.raids[1].participants[0].historical_role, "unknown")
        store = materialize_clm_raids_into_identity_v2(first_import_store(analysis), analysis)
        self.assertEqual((len(store.raids), len(store.attendance)), (2, 3))
        self.assertEqual({item.attendanceType for item in store.attendance}, {"unknown"})
        self.assertEqual([item.clmGuid for item in store.attendance],
                         ["1:101", "1:102", "1:102"])
        self.assertEqual({member.clmGuid: member.className for member in store.members},
                         {"1:101": "Priest", "1:102": "Mage"})
        self.assertEqual({member.raidStartDate for member in store.members},
                         {"2025-01-03"})
        self.assertEqual(store.players, [])
        self.assertTrue(all(member.playerId is None and member.currentRole is None
                            for member in store.members))

    def test_member_without_actual_raid_keeps_no_start_date(self):
        analysis = analysis_for((self.MAIN, ((1, 102), "NoRaid", 8, 1, None)),
                                ((3, "MC", ((1, 101),), (), ()),))
        store = materialize_clm_raids_into_identity_v2(first_import_store(analysis), analysis)
        by_name = {member.name: member for member in store.members}
        self.assertEqual(by_name["Main"].raidStartDate, "2025-01-03")
        self.assertIsNone(by_name["NoRaid"].raidStartDate)

    def test_two_same_name_members_can_attend_same_raid_separately(self):
        analysis = analysis_for((
            ((1, 101), "Veniell", 5, 1, None),
            ((1, 102), "Veniell", 5, 1, None),
        ), ((3, "MC", ((1, 101), (1, 102)), (), ()),))
        base = first_import_store(analysis)
        self.assertEqual(len(base.members), 2)
        store = materialize_clm_raids_into_identity_v2(base, analysis)
        self.assertEqual(len(store.raids), 1)
        self.assertEqual(len(store.attendance), 2)
        self.assertEqual(len({item.memberId for item in store.attendance}), 2)

    def test_unresolved_real_participant_aborts_without_mutating_input(self):
        analysis = self.single_raid(present=((1, 101), (1, 999)))
        base = IdentityV2Store(members=[Member("m1000", "Main", "Priest", clmGuid="1:101")])
        before = base.to_payload()
        with self.assertRaisesRegex(ClmRaidMaterializationError, "1:999") as failure:
            materialize_clm_raids_into_identity_v2(base, analysis)
        self.assertIn(analysis.raids[0].raid_id, str(failure.exception))
        unknown = next(item for item in analysis.raids[0].participants
                       if item.guid == "1:999")
        self.assertIn(unknown.source_event_ids[0], str(failure.exception))
        self.assertEqual(base.to_payload(), before)

    def test_same_member_two_guids_in_one_raid_is_rejected(self):
        analysis = analysis_for((
            ((1, 101), "Veniell", 5, 1, None),
            ((1, 102), "Veniell", 5, 1, None),
        ), ((3, "MC", ((1, 101), (1, 102)), (), ()),))
        base = IdentityV2Store(
            members=[Member("m1000", "Veniell", "Priest", clmGuid="1:102")],
            legacyClmGuidMemberMap={"1:101": "m1000"},
        )
        with self.assertRaisesRegex(ClmRaidMaterializationError, "SAME_RAID_COEXISTENCE"):
            materialize_clm_raids_into_identity_v2(base, analysis)

    def test_duplicate_member_in_one_raid_is_rejected_even_without_prior_evidence(self):
        analysis = analysis_for((
            ((1, 101), "Veniell", 5, 1, None),
            ((1, 102), "Veniell", 5, 1, None),
        ), ((3, "MC", ((1, 101), (1, 102)), (), ()),))
        analysis = replace(analysis, identity_analysis=replace(
            analysis.identity_analysis, raid_coexistence=(),
        ))
        base = IdentityV2Store(
            members=[Member("m1000", "Veniell", "Priest", clmGuid="1:102")],
            legacyClmGuidMemberMap={"1:101": "m1000"},
        )
        before = base.to_payload()
        with self.assertRaisesRegex(ClmRaidMaterializationError, "Zwei GUIDs desselben Members"):
            materialize_clm_raids_into_identity_v2(base, analysis)
        self.assertEqual(base.to_payload(), before)

    def test_save_load_keeps_raids_attendance_source_and_start_dates(self):
        analysis = self.single_raid()
        built = materialize_clm_raids_into_identity_v2(first_import_store(analysis), analysis)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "identity-v2.json"
            save_identity_v2(built, path)
            restored = load_identity_v2(path)
        self.assertEqual(restored.to_payload(), built.to_payload())
        self.assertEqual(restored.raids[0].clmRaidId, analysis.raids[0].raid_id)
        self.assertEqual(restored.attendance[0].clmGuid, "1:101")
        self.assertEqual(restored.attendance[0].attendanceType, "unknown")
        self.assertEqual(restored.members[0].raidStartDate, "2025-01-03")

    def test_second_raid_materialization_is_idempotent(self):
        analysis = self.single_raid()
        filled = materialize_clm_raids_into_identity_v2(first_import_store(analysis), analysis)
        before = filled.to_payload()
        repeated = import_raids(filled, analysis)
        self.assertEqual(repeated.to_payload(), before)
        self.assertEqual(filled.to_payload(), before)

    def test_changed_existing_clm_participants_require_review(self):
        analysis = self.single_raid()
        filled = materialize_clm_raids_into_identity_v2(first_import_store(analysis), analysis)
        changed_raid = replace(analysis.raids[0], participants=())
        changed = replace(analysis, raids=(changed_raid,))
        before = filled.to_payload()
        self.assertEqual(review_clm_raids(filled, changed)[0].status,
                         "Teilnehmer abweichend")
        with self.assertRaisesRegex(ClmRaidMaterializationError, "Teilnehmer"):
            import_raids(filled, changed)
        self.assertEqual(filled.to_payload(), before)
        self.assertEqual(clm_raid_attendance_difference(
            filled, changed, changed_raid.raid_id), ((), ("1:101",)))
        corrected = correct_clm_raid_attendance(
            filled, changed, changed_raid.raid_id)
        self.assertEqual(corrected.attendance, [])
        self.assertEqual(review_clm_raids(corrected, changed)[0].status,
                         "bereits importiert")
        self.assertEqual(import_raids(corrected, changed).to_payload(),
                         corrected.to_payload())
        self.assertEqual(filled.to_payload(), before)

    def test_skipped_clm_raid_needs_no_type_and_changes_nothing(self):
        analysis = analysis_for((self.MAIN,), (
            (3, "MC", ((1, 101),), (), ()),
            (4, "Testeintrag", ((1, 101),), (), ()),
        ))
        source = first_import_store(analysis)
        selected = {analysis.raids[0].raid_id}
        filled = import_raids(
            source, analysis, {analysis.raids[0].raid_id: "MC"},
            selected_raid_ids=selected)
        self.assertEqual([raid.clmRaidId for raid in filled.raids],
                         [analysis.raids[0].raid_id])
        self.assertEqual(len(filled.attendance), 1)
        before = filled.to_payload()
        changed_source = replace(analysis.raids[0], participants=())
        changed = replace(analysis, raids=(changed_source,))
        skipped = import_raids(filled, changed, selected_raid_ids=set())
        self.assertEqual(skipped.to_payload(), before)
        self.assertEqual(filled.to_payload(), before)
        with self.assertRaisesRegex(ClmRaidMaterializationError, "Unbekannte"):
            import_raids(filled, analysis, selected_raid_ids={"unknown"})

    def test_explicit_clm_correction_adds_member_without_changing_original(self):
        analysis = analysis_for((self.MAIN, ((1, 102), "Neu", 5, 2, None)), (
            (3, "MC", ((1, 101),), (), ()),
        ))
        filled = materialize_clm_raids_into_identity_v2(first_import_store(analysis), analysis)
        changed_source = replace(analysis.raids[0], participants=(
            *analysis.raids[0].participants,
            replace(analysis.raids[0].participants[0], guid="1:102"),
        ))
        changed = replace(analysis, raids=(changed_source,))
        before = filled.to_payload()
        self.assertEqual(clm_raid_attendance_difference(
            filled, changed, changed_source.raid_id), (("1:102",), ()))
        corrected = correct_clm_raid_attendance(
            filled, changed, changed_source.raid_id)
        self.assertEqual({item.clmGuid for item in corrected.attendance},
                         {"1:101", "1:102"})
        self.assertEqual(len({item.memberId for item in corrected.attendance}), 2)
        self.assertEqual(filled.to_payload(), before)

    def test_review_requires_type_for_truly_unknown_title(self):
        analysis = analysis_for((self.MAIN,), (
            (3, "Unbekannter Raid", ((1, 101),), (), ()),
            (5, "BWL", ((1, 101),), (), ()),
        ))
        base = first_import_store(analysis)
        rows = review_clm_raids(base, analysis)
        self.assertEqual([row.raid_type for row in rows], ["", "BWL"])
        self.assertEqual(suggest_clm_raid_type("Molten Core"), "MC")
        self.assertEqual(suggest_clm_raid_type("Onyxia / Molten Core"), "MC")
        before = base.to_payload()
        with self.assertRaisesRegex(ClmRaidMaterializationError, "Raid-Typ"):
            import_raids(base, analysis, {rows[1].clm_raid_id: "BWL"})
        self.assertEqual(base.to_payload(), before)
        filled = import_raids(base, analysis, {rows[0].clm_raid_id: "MC",
                                               rows[1].clm_raid_id: "BWL"})
        self.assertEqual([raid.raidType for raid in filled.raids], ["MC", "BWL"])
        self.assertEqual([raid_category(raid.raidType) for raid in filled.raids],
                         ["40er", "40er"])

    def test_shared_title_priority_and_existing_alias_are_not_rewritten(self):
        from app.csv_import import normalize_csv_raid_type
        from app.raid_attendance import RAID_TYPES

        expected = {
            "Ony / MC": "MC", "ZG nach Ony/MC": "ZG",
            "Ony / ZG / AQ20": "ZG", "Azuregos + MC": "MC",
            "AQ40 & ZG": "AQ40", "Kazzak / Naxxramas": "Naxx",
            "Ony": "Onyxia", "Ysondre": "World Boss",
            "AQ": "AQ20", "AQ + ZG": "AQ20", "ZG + AQ": "ZG",
            "Ony / AQ": "AQ20", "Azu": "World Boss",
            "Azzuregos": "World Boss", "Azu + ZG": "ZG",
            "Azu, AQ, ZG": "AQ20", "Azu, ZG, AQ": "ZG",
            "17.10 AQ+ZG": "AQ20", "AQ & ZG 31.10.2025": "AQ20",
            "Azu, AQ, ZG 14.11.": "AQ20", "Azu 28.11.2025": "World Boss",
        }
        for title, canonical in expected.items():
            with self.subTest(title=title):
                self.assertEqual(suggest_clm_raid_type(title), canonical)
                self.assertEqual(suggest_clm_raid_type(title),
                                 normalize_csv_raid_type(title, RAID_TYPES))
        self.assertEqual(suggest_clm_raid_type("AQ"), "AQ20")
        analysis = self.single_raid()
        filled = materialize_clm_raids_into_identity_v2(first_import_store(analysis), analysis)
        filled.raids[0].raidType = "Naxxramas"
        before = filled.to_payload()
        row = review_clm_raids(filled, analysis)[0]
        self.assertEqual((row.raid_type, row.status), ("Naxx", "bereits importiert"))
        repeated = import_raids(filled, analysis)
        self.assertEqual(repeated.to_payload(), before)

    def test_existing_aq_alias_is_aq20_without_rewriting_project(self):
        analysis = analysis_for((self.MAIN,), (
            (3, "AQ", ((1, 101),), (), ()),
        ))
        filled = import_raids(first_import_store(analysis), analysis,
                              {analysis.raids[0].raid_id: "AQ20"})
        filled.raids[0].raidType = "AQ"
        before = filled.to_payload()
        row = review_clm_raids(filled, analysis)[0]
        self.assertEqual((row.raid_type, row.status), ("AQ20", "bereits importiert"))
        self.assertEqual(filled.to_payload(), before)
        repeated = import_raids(filled, analysis)
        self.assertEqual(repeated.to_payload(), before)

    def test_existing_missing_type_uses_review_without_attendance_duplication(self):
        analysis = self.single_raid()
        filled = materialize_clm_raids_into_identity_v2(first_import_store(analysis), analysis)
        filled.raids[0].raidType = ""
        rows = review_clm_raids(filled, analysis)
        self.assertEqual(rows[0].status, "Typ fehlt")
        repaired = import_raids(filled, analysis, {rows[0].clm_raid_id: "MC"})
        self.assertEqual(repaired.raids[0].raidType, "MC")
        self.assertEqual(len(repaired.attendance), 1)
        self.assertEqual(filled.raids[0].raidType, "")

    def test_only_missing_raid_is_added_after_partial_import(self):
        analysis = analysis_for((self.MAIN,), (
            (3, "MC", ((1, 101),), (), ()),
            (5, "BWL", ((1, 101),), (), ()),
        ))
        base = first_import_store(analysis)
        first = import_raids(base, replace(analysis, raids=analysis.raids[:1]),
                             {analysis.raids[0].raid_id: "MC"})
        completed = import_raids(first, analysis, {analysis.raids[1].raid_id: "BWL"})
        self.assertEqual((len(completed.raids), len(completed.attendance)), (2, 2))
        self.assertEqual([raid.raidType for raid in completed.raids], ["MC", "BWL"])
        self.assertEqual(completed.members[0].raidStartDate, "2025-01-03")
        self.assertEqual(len({item.attendanceId for item in completed.attendance}), 2)


if __name__ == "__main__":
    unittest.main()
