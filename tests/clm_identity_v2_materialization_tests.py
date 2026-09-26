"""Focused first-import materialization tests; all saves are temporary."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from app.clm_identity_v2_analysis import ClmIncompleteP0, analyze_clm_ledger
from app.clm_identity_v2_decisions import (
    CONTINUE, NEW_CHARACTER, ClmIdentityDecisionDraft,
    ClmIdentityDecisionSet, ClmNameDecision,
)
from app.clm_identity_v2_materialization import (
    ClmMaterializationError, build_identity_v2_store_from_clm,
)
from app.clm_v2_refresh import (
    pending_clm_character_groups, prepare_clm_identity_refresh_review,
    refresh_clm_v2_characters,
)
from app.clm_raid_v2_analysis import (
    ClmMultiGuidRaidCollision, apply_raid_identity_evidence,
)
from app.identity_v2 import IdentityV2Store, Member, Player
from app.identity_v2_import_choices import CharacterImportChoice
from app.identity_v2_storage import load_identity_v2, save_identity_v2


def analysis_for(*profiles, earnings=None):
    """Profiles are (GUID tuple, name, P0 class, first time, P1 time or None)."""
    roster = "roster-1"
    events = [{"_c": 1, "_b": 0, "_e": 1, "_a": 1,
               "_d": "R0", "r": roster, "n": "Bierstube", "p": 0}]
    sequence = 2
    for guid, name, class_id, first, last in profiles:
        raw = [
            (first, "P0", {"g": list(guid), "n": f"{name}-Stitches", "c": class_id}),
            (first + 1, "R9", {"r": roster, "p": [list(guid)]}),
        ]
        if earnings and guid in earnings:
            raw.append((first + 2, "DM", {
                "r": roster, "p": [list(guid)], "v": earnings[guid],
                "t": "Bonus", "n": False,
            }))
        if last is not None:
            raw.append((last, "P1", {"g": list(guid)}))
        for timestamp, opcode, fields in raw:
            events.append({"_c": timestamp, "_b": 0, "_e": 1,
                           "_a": sequence, "_d": opcode, **fields})
            sequence += 1
    return analyze_clm_ledger(events, roster)


def reviewed(analysis, *choices):
    draft = ClmIdentityDecisionDraft(analysis)
    for name, guid, action in choices:
        draft.set_choice(name, guid, action)
    return draft.to_decision_set()


class ClmIdentityV2MaterializationTests(unittest.TestCase):
    def two(self, *, class_b=5, earnings=None):
        return analysis_for(
            ((1, 101), "Annî", 5, 100, 200),
            ((1, 102), "Annî", class_b, 300, None),
            earnings=earnings,
        )

    def test_single_guid_automatically_creates_one_member_with_p0_class(self):
        analysis = analysis_for(((1, 101), "Jêmma", 5, 100, 200))
        store = build_identity_v2_store_from_clm(analysis)
        self.assertEqual(len(store.members), 1)
        member = store.members[0]
        self.assertEqual((member.name, member.className, member.clmGuid),
                         ("Jêmma", "Priest", "1:101"))
        self.assertEqual(member.playerId, None)
        self.assertEqual(store.players, [])

    def test_single_guid_names_are_included_alongside_reviewed_multi_guids(self):
        analysis = analysis_for(
            ((1, 101), "Annî", 5, 100, 200),
            ((1, 102), "Annî", 5, 300, None),
            ((1, 201), "Jêmma", 8, 100, None),
        )
        decisions = reviewed(analysis, ("Annî", "1:102", CONTINUE))
        self.assertEqual(len(decisions.decisions), 1)
        store = build_identity_v2_store_from_clm(analysis, decisions)
        self.assertEqual({member.name for member in store.members}, {"Annî", "Jêmma"})
        self.assertEqual(len(store.members), 2)

    def test_confirmed_two_guid_continuation_has_one_primary_and_one_legacy_guid(self):
        analysis = self.two()
        decisions = reviewed(analysis, ("Annî", "1:102", CONTINUE))
        store = build_identity_v2_store_from_clm(analysis, decisions)
        self.assertEqual(len(store.members), 1)
        member = store.members[0]
        self.assertEqual(member.className, "Priest")
        self.assertEqual(member.clmGuid, "1:102")
        self.assertEqual(store.legacyClmGuidMemberMap, {"1:101": member.memberId})
        self.assertEqual(store.member_id_for_clm_guid("1:101"), member.memberId)
        self.assertIsNone(member.continuationOfMemberId)

    def test_separate_two_guids_create_two_members_with_distinct_ids(self):
        analysis = self.two()
        store = build_identity_v2_store_from_clm(
            analysis, reviewed(analysis, ("Annî", "1:102", NEW_CHARACTER)))
        self.assertEqual(len(store.members), 2)
        self.assertEqual({member.name for member in store.members}, {"Annî"})
        self.assertEqual(len({member.memberId for member in store.members}), 2)
        self.assertEqual(store.legacyClmGuidMemberMap, {})

    def test_three_guids_allow_one_two_guid_chain_and_one_separate_member(self):
        analysis = analysis_for(
            ((1, 101), "Annî", 5, 100, 200),
            ((1, 102), "Annî", 5, 300, 400),
            ((1, 103), "Annî", 8, 500, None),
        )
        decisions = reviewed(analysis, ("Annî", "1:102", CONTINUE))
        store = build_identity_v2_store_from_clm(analysis, decisions)
        self.assertEqual(len(store.members), 2)
        old_chain = next(member for member in store.members if member.clmGuid == "1:102")
        mage = next(member for member in store.members if member.clmGuid == "1:103")
        self.assertEqual(old_chain.className, "Priest")
        self.assertEqual(mage.className, "Mage")
        self.assertEqual(store.legacyClmGuidMemberMap, {"1:101": old_chain.memberId})

    def test_manipulated_class_conflict_chain_is_rejected(self):
        analysis = self.two(class_b=11)
        decision = ClmNameDecision("Annî", ("1:101", "1:102"), (("1:101", "1:102"),))
        decisions = ClmIdentityDecisionSet("", analysis.roster_id, (decision,))
        with self.assertRaisesRegex(ClmMaterializationError, "Ungültige Fortsetzung"):
            build_identity_v2_store_from_clm(analysis, decisions)

    def test_manipulated_same_raid_chain_is_rejected_independently_of_ui(self):
        analysis = apply_raid_identity_evidence(self.two(), (
            ClmMultiGuidRaidCollision("raid-1", "Annî", ("1:101", "1:102"), False),
        ))
        merged = ClmNameDecision("Annî", ("1:101", "1:102"), (("1:101", "1:102"),))
        decisions = ClmIdentityDecisionSet("", analysis.roster_id, (merged,))
        with self.assertRaisesRegex(ClmMaterializationError, "SAME_RAID_COEXISTENCE"):
            build_identity_v2_store_from_clm(analysis, decisions)
        separated = ClmNameDecision("Annî", ("1:101", "1:102"),
                                    (("1:101",), ("1:102",)))
        store = build_identity_v2_store_from_clm(
            analysis, ClmIdentityDecisionSet("", analysis.roster_id, (separated,)))
        self.assertEqual(len(store.members), 2)

    def test_unknown_guid_in_decision_set_is_rejected(self):
        analysis = self.two()
        decision = ClmNameDecision("Annî", ("1:101", "1:999"), (("1:101", "1:999"),))
        with self.assertRaisesRegex(ClmMaterializationError, "Unbekannte GUID"):
            build_identity_v2_store_from_clm(
                analysis, ClmIdentityDecisionSet("", analysis.roster_id, (decision,)))

    def test_duplicate_guid_in_character_groups_is_rejected(self):
        analysis = self.two()
        decision = ClmNameDecision(
            "Annî", ("1:101", "1:102"), (("1:101", "1:102"), ("1:102",)),
        )
        with self.assertRaisesRegex(ClmMaterializationError, "Doppelte GUID"):
            build_identity_v2_store_from_clm(
                analysis, ClmIdentityDecisionSet("", analysis.roster_id, (decision,)))

    def test_missing_guid_in_character_groups_is_rejected(self):
        analysis = self.two()
        decision = ClmNameDecision("Annî", ("1:101", "1:102"), (("1:101",),))
        with self.assertRaisesRegex(ClmMaterializationError, "Abdeckung"):
            build_identity_v2_store_from_clm(
                analysis, ClmIdentityDecisionSet("", analysis.roster_id, (decision,)))

    def test_missing_multi_guid_decisions_are_rejected_without_partial_store(self):
        analysis = self.two()
        empty_target = IdentityV2Store()
        before = empty_target.to_payload()
        with self.assertRaisesRegex(ClmMaterializationError, "Annî"):
            build_identity_v2_store_from_clm(analysis, target_store=empty_target)
        self.assertEqual(empty_target.to_payload(), before)

    def test_partial_decision_set_names_the_remaining_group(self):
        analysis = analysis_for(
            ((1, 101), "Annî", 5, 100, 200),
            ((1, 102), "Annî", 5, 300, None),
            ((1, 201), "Bämäräng", 11, 100, 200),
            ((1, 202), "Bämäräng", 2, 300, None),
        )
        partial = ClmIdentityDecisionSet(
            "", analysis.roster_id,
            (ClmNameDecision("Annî", ("1:101", "1:102"), (("1:101",), ("1:102",))),),
        )
        with self.assertRaisesRegex(ClmMaterializationError, "Bämäräng"):
            build_identity_v2_store_from_clm(analysis, partial)

    def test_player_roles_death_and_raid_start_are_not_inferred(self):
        analysis = self.two()
        store = build_identity_v2_store_from_clm(
            analysis, reviewed(analysis, ("Annî", "1:102", CONTINUE)))
        self.assertEqual(store.players, [])
        self.assertEqual(store.raids, [])
        self.assertEqual(store.attendance, [])
        member = store.members[0]
        self.assertIsNone(member.playerId)
        self.assertIsNone(member.currentRole)
        self.assertEqual(member.lifeStatus, "active")
        self.assertIsNone(member.deathDate)
        self.assertIsNone(member.graveTemplateId)
        self.assertIsNone(member.raidStartDate)
        self.assertNotIn("raidStartDate", member.to_dict())

    def test_dkp_rows_keep_each_guid_and_aggregate_once_through_legacy_mapping(self):
        analysis = self.two(earnings={(1, 101): 850, (1, 102): 320})
        store = build_identity_v2_store_from_clm(
            analysis, reviewed(analysis, ("Annî", "1:102", CONTINUE)))
        self.assertEqual(len(store.eternalDkpRecords), 2)
        self.assertEqual({item.clmGuid for item in store.eternalDkpRecords}, {"1:101", "1:102"})
        self.assertEqual({item.memberId for item in store.eternalDkpRecords},
                         {store.members[0].memberId})
        self.assertEqual(store.eternal_dkp_for_member(store.members[0].memberId), 1170)
        self.assertEqual(store.eternal_dkp_for_continuation(store.members[0].memberId), 1170)

    def test_duplicate_identical_raw_booking_is_only_materialized_once(self):
        analysis = analysis_for(((1, 101), "Annî", 5, 100, None), earnings={(1, 101): 10})
        history = analysis.guid_histories[0]
        duplicated = replace(history, eternal_dkp_records=(
            history.eternal_dkp_records[0], history.eternal_dkp_records[0],
        ))
        analysis = replace(analysis, guid_histories=(duplicated,))
        store = build_identity_v2_store_from_clm(analysis)
        self.assertEqual(len(store.eternalDkpRecords), 1)
        self.assertEqual(store.eternal_dkp_for_member(store.members[0].memberId), 10)

    def test_late_raw_booking_conflict_leaves_target_store_empty(self):
        analysis = analysis_for(((1, 101), "Annî", 5, 100, None), earnings={(1, 101): 10})
        history = analysis.guid_histories[0]
        original = history.eternal_dkp_records[0]
        changed = replace(original, value=11)
        analysis = replace(analysis, guid_histories=(replace(
            history, eternal_dkp_records=(original, changed),
        ),))
        target = IdentityV2Store()
        with self.assertRaisesRegex(ClmMaterializationError, "Widersprüchliche DKP"):
            build_identity_v2_store_from_clm(analysis, target_store=target)
        self.assertEqual(target.members, [])
        self.assertEqual(target.eternalDkpRecords, [])

    def test_roundtrip_preserves_primary_legacy_class_and_raw_dkp(self):
        analysis = self.two(earnings={(1, 101): 850, (1, 102): 320})
        built = build_identity_v2_store_from_clm(
            analysis, reviewed(analysis, ("Annî", "1:102", CONTINUE)))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "identity-v2.json"
            save_identity_v2(built, path)
            loaded = load_identity_v2(path)
        self.assertEqual(loaded.to_payload(), built.to_payload())
        self.assertEqual(loaded.legacyClmGuidMemberMap, {"1:101": built.members[0].memberId})

    def test_same_input_and_decisions_generate_reproducible_ids(self):
        analysis = self.two()
        decisions = reviewed(analysis, ("Annî", "1:102", NEW_CHARACTER))
        first = build_identity_v2_store_from_clm(analysis, decisions)
        second = build_identity_v2_store_from_clm(analysis, decisions)
        self.assertEqual(first.to_payload(), second.to_payload())
        self.assertTrue(all(member.memberId.startswith("m") for member in first.members))

    def test_nonempty_target_store_is_rejected_and_unchanged(self):
        target = IdentityV2Store(members=[Member("m9999", "Bestehend", "Mage")])
        before = target.to_payload()
        with self.assertRaisesRegex(ClmMaterializationError, "leeren"):
            build_identity_v2_store_from_clm(
                analysis_for(((1, 101), "Annî", 5, 100, None)), target_store=target)
        self.assertEqual(target.to_payload(), before)

    def test_empty_target_store_remains_empty_after_success(self):
        target = IdentityV2Store()
        analysis = analysis_for(((1, 101), "Annî", 5, 100, None))
        result = build_identity_v2_store_from_clm(analysis, target_store=target)
        self.assertIsNot(result, target)
        self.assertEqual(target.members, [])
        self.assertEqual(len(result.members), 1)

    def test_invalid_p0_class_is_rejected_before_any_store_is_returned(self):
        analysis = analysis_for(((1, 101), "Annî", 999, 100, None))
        with self.assertRaisesRegex(ClmMaterializationError, "Klasse"):
            build_identity_v2_store_from_clm(analysis)

    def test_audited_incomplete_p0_keeps_valid_member_and_dkp(self):
        analysis = analysis_for(
            ((1, 101), "Ânní", 5, 100, None), earnings={(1, 101): 10},
        )
        history = analysis.guid_histories[0]
        audited = replace(
            history, p0_count=2,
            incomplete_p0_events=(ClmIncompleteP0(
                "synthetic", "Unbekannt-Stitches", "", ("class",),
            ),),
            warnings=("INCOMPLETE_P0_IGNORED",),
        )
        analysis = replace(analysis, guid_histories=(audited,))
        store = build_identity_v2_store_from_clm(analysis)
        self.assertEqual((store.members[0].name, store.members[0].className),
                         ("Ânní", "Priest"))
        self.assertEqual(store.eternal_dkp_for_member(store.members[0].memberId), 10)


class ClmIdentityV2RefreshTests(unittest.TestCase):
    def test_resolved_multi_guid_group_reuses_owner_without_reopening_review(self):
        analysis = analysis_for(
            ((1, 101), "Anni", 5, 100, 200),
            ((1, 102), "Anni", 5, 300, None),
        )
        store = IdentityV2Store(
            members=[Member("m1000", "Anni", "Priest", clmGuid="1:102")],
            legacyClmGuidMemberMap={"1:101": "m1000"},
        )
        before = store.to_payload()
        draft, groups, locked = prepare_clm_identity_refresh_review(store, analysis)
        self.assertEqual(groups, set())
        self.assertEqual(locked, {("anni", "1:102")})
        self.assertEqual(draft.choice("Anni", "1:102"), CONTINUE)
        decisions = draft.to_decision_set()
        self.assertEqual(decisions.decisions[0].character_groups,
                         (("1:101", "1:102"),))
        self.assertEqual(refresh_clm_v2_characters(
            store, analysis, decisions, {}).to_payload(), before)

    def test_only_new_guid_in_known_group_needs_review(self):
        analysis = analysis_for(
            ((1, 101), "Anni", 5, 100, 200),
            ((1, 102), "Anni", 5, 300, 400),
            ((1, 103), "Anni", 5, 500, None),
        )
        store = IdentityV2Store(
            members=[Member("m1000", "Anni", "Priest", clmGuid="1:102")],
            legacyClmGuidMemberMap={"1:101": "m1000"},
        )
        draft, groups, locked = prepare_clm_identity_refresh_review(store, analysis)
        self.assertEqual(groups, {"anni"})
        self.assertEqual(locked, {("anni", "1:102")})
        self.assertEqual(draft.choice("Anni", "1:102"), CONTINUE)
        self.assertIsNone(draft.choice("Anni", "1:103"))

    def test_resolved_distinct_and_ignored_guids_retain_saved_boundaries(self):
        analysis = analysis_for(
            ((1, 101), "Anni", 5, 100, 200),
            ((1, 102), "Anni", 5, 300, None),
        )
        store = IdentityV2Store(members=[
            Member("m1000", "Anni", "Priest", lifeStatus="dead",
                   deathDate="2025-01-01", burialType="collective", clmGuid="1:101"),
            Member("m1001", "Anni", "Priest", clmGuid="1:102"),
        ])
        draft, groups, _locked = prepare_clm_identity_refresh_review(store, analysis)
        self.assertEqual(groups, set())
        self.assertEqual(draft.choice("Anni", "1:102"), NEW_CHARACTER)
        ignored = IdentityV2Store()
        ignored.ignore_clm_character_group("Anni", ("1:101", "1:102"))
        draft, groups, _locked = prepare_clm_identity_refresh_review(ignored, analysis)
        self.assertEqual(groups, set())
        self.assertEqual(draft.choice("Anni", "1:102"), CONTINUE)

    def test_new_guid_creates_new_incarnation_without_reanimating_dead_member(self):
        analysis = analysis_for(
            ((1, 101), "Jêmma", 5, 100, 200),
            ((1, 102), "Jêmma", 5, 300, None),
        )
        decisions = reviewed(analysis, ("Jêmma", "1:102", NEW_CHARACTER))
        original = IdentityV2Store(members=[
            Member(memberId="m1000", name="Jêmma", className="Priest",
                   lifeStatus="dead", deathDate="2025-01-01",
                   burialType="individual", clmGuid="1:101"),
        ])
        pending = pending_clm_character_groups(original, analysis, decisions)
        self.assertEqual(pending, {("1:102",)})
        updated = refresh_clm_v2_characters(
            original, analysis, decisions,
            {("1:102",): CharacterImportChoice()})
        self.assertEqual([(m.memberId, m.lifeStatus, m.clmGuid)
                          for m in updated.members],
                         [("m1000", "dead", "1:101"), ("m1001", "active", "1:102")])
        self.assertEqual(original.to_payload()["members"][0]["lifeStatus"], "dead")
        repeated = refresh_clm_v2_characters(updated, analysis, decisions, {})
        self.assertEqual(repeated.to_payload(), updated.to_payload())

    def test_existing_inactive_member_keeps_status_when_guid_is_assigned(self):
        analysis = analysis_for(((1, 101), "Jêmma", 5, 100, None))
        decisions = reviewed(analysis)
        original = IdentityV2Store(members=[
            Member(memberId="m1000", name="Jêmma", className="Priest",
                   lifeStatus="inactive"),
        ])
        updated = refresh_clm_v2_characters(
            original, analysis, decisions,
            {("1:101",): CharacterImportChoice(member_id="m1000")})
        self.assertEqual((updated.members[0].memberId,
                          updated.members[0].lifeStatus, updated.members[0].clmGuid),
                         ("m1000", "inactive", "1:101"))

    def test_new_character_can_use_reviewed_existing_player_without_main_change(self):
        analysis = analysis_for(((1, 101), "Jêmma", 5, 100, None))
        decisions = reviewed(analysis)
        original = IdentityV2Store(players=[Player("p1", "Spieler")])
        updated = refresh_clm_v2_characters(
            original, analysis, decisions,
            {("1:101",): CharacterImportChoice(player_id="p1")})
        self.assertEqual(updated.members[0].playerId, "p1")
        self.assertEqual(updated.players, original.players)

    def test_new_inactive_character_can_use_reviewed_existing_player(self):
        analysis = analysis_for(((1, 101), "Jêmma", 5, 100, None))
        decisions = reviewed(analysis)
        original = IdentityV2Store(players=[Player("p1", "Spieler")])
        updated = refresh_clm_v2_characters(
            original, analysis, decisions,
            {("1:101",): CharacterImportChoice(
                activity_status="inactive", player_id="p1")})
        self.assertEqual((updated.members[0].lifeStatus,
                          updated.members[0].playerId), ("inactive", "p1"))
        self.assertEqual(original.members, [])

    def test_ignored_group_stays_ignored_on_repeated_refresh(self):
        analysis = analysis_for(((1, 101), "Jêmma", 5, 100, None))
        decisions = reviewed(analysis)
        original = IdentityV2Store()
        original.ignore_clm_character_group("Jêmma", ("1:101",))
        self.assertEqual(pending_clm_character_groups(original, analysis, decisions), set())
        updated = refresh_clm_v2_characters(original, analysis, decisions, {})
        self.assertEqual(updated.to_payload(), original.to_payload())


if __name__ == "__main__":
    unittest.main()
