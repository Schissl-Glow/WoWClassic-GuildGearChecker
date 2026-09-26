"""Focused V2 Main history, successor and timeline conflict tests."""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.identity_v2 import (
    Attendance, IdentityV2Store, IdentityV2ValidationError, MainHistoryEntry,
    Member, Player, Raid,
)
from app.identity_v2_character_service import (
    DeathAttendanceConflict, mark_member_dead,
)
from app.identity_v2_main_history import (
    MainSuccessorSelectionRequired, add_main_history_entry,
    find_main_history_conflicts, get_main_successor_candidates,
    reconcile_draft_history_sequence, remove_main_history_entry,
    set_main_since_date, update_main_history_entry,
)
from app.identity_v2_player_service import (
    PlayerMembershipError, clear_main, reassign_member, set_main,
    set_player_activity, unassign_member,
)
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from app.gravestone_templates import GravestoneTemplate


GRAVESTONE_TEMPLATES = (
    GravestoneTemplate("main-history-stone", "stone.png", "hash",
                       Path("stone.png"), category="Menschen"),
)


def sample_store(*, candidates: int = 2) -> IdentityV2Store:
    members = [
        Member("m1000", "Alpha", "Mage", playerId="p1", clmGuid="G-A"),
        Member("m1001", "Beta", "Priest", playerId="p1", clmGuid="G-B",
               lifeStatus="active" if candidates >= 1 else "inactive"),
        Member("m1002", "Charlie", "Warrior", playerId="p1", clmGuid="G-C",
               lifeStatus="active" if candidates >= 2 else "inactive"),
        Member("m1003", "Delta", "Hunter", playerId="p1", clmGuid="G-D",
               lifeStatus="active" if candidates >= 3 else "inactive"),
        Member("m1004", "Fremd", "Druid", playerId="p2"),
        Member("m1005", "Frei", "Rogue"),
        Member("m1006", "Tot", "Paladin", playerId="p1", lifeStatus="dead",
               burialType="individual", deathDate="2026-01-01"),
    ]
    store = IdentityV2Store(
        players=[Player("p1", "Spieler", "m1000", "2026-01-01"),
                 Player("p2", "Anderer", "m1004")],
        members=members,
        raids=[Raid("r1", "2026-03-15", name="MC")],
        attendance=[Attendance("a1", "r1", "m1000", "main", playerId="p1",
                               clmGuid="G-A")],
    )
    store.validate()
    return store


class IdentityV2MainHistoryTests(unittest.TestCase):
    def test_old_player_defaults_and_full_roundtrip(self):
        old = sample_store().to_payload()
        for player in old["players"]:
            player.pop("mainHistory")
            player.pop("mainSinceDate")
        loaded = IdentityV2Store.from_payload(old)
        self.assertEqual(loaded.players[0].mainHistory, [])
        self.assertIsNone(loaded.players[0].mainSinceDate)
        with_dates = add_main_history_entry(loaded, "p1", "m1001",
                                            None, "2025-12-31")
        with_dates = add_main_history_entry(with_dates, "p1", "m1001",
                                            "2024-01-01", None)
        with_dates = add_main_history_entry(with_dates, "p1", "m1001")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.ggc"
            save_new_identity_v2(with_dates, path)
            restored = load_identity_v2(path)
        self.assertEqual(restored.to_payload(), with_dates.to_payload())
        self.assertEqual({(item.fromDate, item.toDate)
                          for item in restored.players[0].mainHistory},
                         {(None, "2025-12-31"), ("2024-01-01", None), (None, None)})

    def test_manual_add_update_remove_and_stable_ids(self):
        store = sample_store()
        added = add_main_history_entry(store, "p1", "m1001")
        first = added.players[0].mainHistory[0]
        self.assertEqual((first.historyId, first.source, first.fromDate, first.toDate),
                         ("mh0001", "manual", None, None))
        changed = update_main_history_entry(
            added, first.historyId, from_date="2025-01-01", to_date="2025-06-01")
        self.assertEqual((changed.players[0].mainHistory[0].fromDate,
                          changed.players[0].mainHistory[0].toDate),
                         ("2025-01-01", "2025-06-01"))
        cleared = update_main_history_entry(changed, first.historyId, from_date=None)
        self.assertIsNone(cleared.players[0].mainHistory[0].fromDate)
        moved_reference = update_main_history_entry(cleared, first.historyId,
                                                    member_id="m1002")
        self.assertEqual(moved_reference.players[0].mainHistory[0].memberId, "m1002")
        with self.assertRaises(IdentityV2ValidationError):
            update_main_history_entry(cleared, first.historyId, member_id="m1004")
        removed = remove_main_history_entry(cleared, first.historyId)
        self.assertEqual(removed.players[0].mainHistory, [])
        again = add_main_history_entry(removed, "p1", "m1001")
        self.assertEqual(again.players[0].mainHistory[0].historyId, "mh0002")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "counter.ggc"
            save_new_identity_v2(again, path)
            reloaded = load_identity_v2(path)
        reloaded = remove_main_history_entry(reloaded, "mh0002")
        third = add_main_history_entry(reloaded, "p1", "m1001")
        self.assertEqual(third.players[0].mainHistory[0].historyId, "mh0003")
        imported = again.to_payload()
        imported.pop("nextMainHistoryNumber")
        imported["players"][0]["mainHistory"][0]["historyId"] = "mh0042"
        loaded_without_counter = IdentityV2Store.from_payload(imported)
        self.assertEqual(loaded_without_counter.nextMainHistoryNumber, 43)
        self.assertEqual(store.players[0].mainHistory, [])

    def test_current_main_since_correction_is_independent_and_atomic(self):
        store = sample_store()
        before = store.to_payload()
        unknown = set_main_since_date(store, "p1", None)
        self.assertEqual(unknown.players[0].mainMemberId, "m1000")
        self.assertIsNone(unknown.players[0].mainSinceDate)
        self.assertEqual(unknown.players[0].mainHistory, [])
        known = set_main_since_date(unknown, "p1", "2026-02-01")
        self.assertEqual(known.players[0].mainSinceDate, "2026-02-01")
        self.assertEqual(known.attendance, store.attendance)
        self.assertEqual(store.to_payload(), before)
        with self.assertRaises(IdentityV2ValidationError):
            set_main_since_date(known, "p1", "2026-02-30")
        without_main = clear_main(store, "p1")
        with self.assertRaises(IdentityV2ValidationError):
            set_main_since_date(without_main, "p1", "2026-02-01")

    def test_entry_date_bounds_update_together_without_invalid_intermediate(self):
        store = add_main_history_entry(sample_store(), "p1", "m1001",
                                       "2025-01-01", "2025-06-01")
        history_id = store.players[0].mainHistory[0].historyId
        moved = update_main_history_entry(
            store, history_id, from_date="2026-01-01", to_date="2026-06-01")
        self.assertEqual((moved.players[0].mainHistory[0].fromDate,
                          moved.players[0].mainHistory[0].toDate),
                         ("2026-01-01", "2026-06-01"))
        self.assertEqual(store.players[0].mainHistory[0].fromDate, "2025-01-01")

    def test_draft_only_history_id_is_released_without_losing_since_edit(self):
        baseline = sample_store()
        draft = add_main_history_entry(baseline, "p1", "m1001")
        draft = remove_main_history_entry(
            draft, draft.players[0].mainHistory[0].historyId)
        self.assertGreater(draft.nextMainHistoryNumber,
                           baseline.nextMainHistoryNumber)
        draft = set_main_since_date(draft, "p1", "2026-02-01")
        final = reconcile_draft_history_sequence(draft, baseline)
        self.assertEqual(final.nextMainHistoryNumber,
                         baseline.nextMainHistoryNumber)
        self.assertEqual(final.players[0].mainSinceDate, "2026-02-01")
        self.assertEqual(final.players[0].mainHistory, [])
        self.assertEqual(baseline.players[0].mainSinceDate, "2026-01-01")

    def test_manual_history_requires_owned_member_and_valid_dates(self):
        store = sample_store()
        for member_id in ("missing", "m1004", "m1005"):
            with self.assertRaises(IdentityV2ValidationError):
                add_main_history_entry(store, "p1", member_id)
        with self.assertRaises(IdentityV2ValidationError):
            add_main_history_entry(store, "p1", "m1001",
                                   "2026-04-01", "2026-03-01")
        for member_id in ("m1001", "m1006"):
            self.assertEqual(
                add_main_history_entry(store, "p1", member_id)
                .players[0].mainHistory[0].memberId, member_id)
        inactive = sample_store(candidates=0)
        self.assertEqual(add_main_history_entry(inactive, "p1", "m1001")
                         .players[0].mainHistory[0].memberId, "m1001")
        self.assertEqual(store.players[0].mainHistory, [])

    def test_main_change_and_clear_record_only_observed_periods(self):
        store = sample_store()
        before_attendance = store.to_payload()["attendance"]
        switched = set_main(store, "p1", "m1001", "2026-03-15")
        player = switched.players[0]
        self.assertEqual((player.mainMemberId, player.mainSinceDate),
                         ("m1001", "2026-03-15"))
        self.assertEqual((player.mainHistory[0].memberId,
                          player.mainHistory[0].fromDate,
                          player.mainHistory[0].toDate,
                          player.mainHistory[0].source,
                          player.mainHistory[0].reason),
                         ("m1000", "2026-01-01", "2026-03-15",
                          "automatic", "main_change"))
        self.assertEqual(player.displayName, "Spieler")
        self.assertEqual(switched.to_payload()["attendance"], before_attendance)
        repeated = set_main(switched, "p1", "m1001")
        self.assertEqual(repeated.to_payload(), switched.to_payload())
        cleared = clear_main(switched, "p1", "2026-04-01")
        self.assertIsNone(cleared.players[0].mainMemberId)
        self.assertIsNone(cleared.players[0].mainSinceDate)
        self.assertEqual(cleared.players[0].mainHistory[1].reason, "cleared")
        self.assertEqual(cleared.players[0].mainHistory[1].memberId, "m1001")

    def test_undated_main_change_and_inactivity_do_not_invent_dates(self):
        store = sample_store()
        switched = set_main(store, "p1", "m1001")
        self.assertIsNone(switched.players[0].mainHistory[0].toDate)
        self.assertIsNone(switched.players[0].mainSinceDate)
        history = [item.to_dict() for item in switched.players[0].mainHistory]
        inactive = set_player_activity(switched, "p1", "inactive")
        self.assertEqual([item.to_dict() for item in inactive.players[0].mainHistory],
                         history)
        self.assertEqual(inactive.players[0].mainMemberId, "m1001")
        self.assertIsNone(inactive.players[0].mainSinceDate)
        cleared = clear_main(store, "p1")
        self.assertIsNone(cleared.players[0].mainHistory[0].toDate)
        first_inactive = set_player_activity(store, "p1", "inactive")
        self.assertEqual(first_inactive.players[0].mainHistory, [])
        self.assertEqual(first_inactive.players[0].mainMemberId, "m1000")

    def test_administrative_ownership_correction_creates_no_history(self):
        store = sample_store()
        unassigned = unassign_member(store, "m1000")
        self.assertIsNone(unassigned.players[0].mainMemberId)
        self.assertIsNone(unassigned.players[0].mainSinceDate)
        self.assertEqual(unassigned.players[0].mainHistory, [])
        reassigned = reassign_member(store, "m1000", "p2")
        self.assertEqual(reassigned.players[0].mainHistory, [])
        with_history = set_main(store, "p1", "m1001")
        with self.assertRaises(PlayerMembershipError):
            reassign_member(with_history, "m1000", "p2")

    def test_death_zero_one_and_many_successors_are_atomic(self):
        for count in (0, 1, 3):
            store = sample_store(candidates=count)
            before = store.to_payload()
            if count == 3:
                with self.assertRaises(MainSuccessorSelectionRequired) as caught:
                    mark_member_dead(store, "m1000", "2026-03-15", "individual")
                self.assertEqual(caught.exception.candidateMemberIds,
                                 ("m1001", "m1002", "m1003"))
                self.assertEqual(store.to_payload(), before)
                with self.assertRaises(IdentityV2ValidationError):
                    mark_member_dead(store, "m1000", "2026-03-15", "individual",
                                     "m1004")
                self.assertEqual(store.to_payload(), before)
                successor = "m1002"
                dead = mark_member_dead(store, "m1000", "2026-03-15",
                                        "individual", successor,
                                        gravestone_templates=GRAVESTONE_TEMPLATES)
            else:
                successor = "m1001" if count == 1 else None
                if count == 0:
                    with self.assertRaises(IdentityV2ValidationError):
                        mark_member_dead(store, "m1000", "2026-03-15",
                                         "individual", "m1001")
                if count == 1:
                    with self.assertRaises(IdentityV2ValidationError):
                        mark_member_dead(store, "m1000", "2026-03-15",
                                         "individual", "m1002")
                dead = mark_member_dead(
                    store, "m1000", "2026-03-15", "individual",
                    gravestone_templates=GRAVESTONE_TEMPLATES)
            player = dead.players[0]
            self.assertEqual(player.mainMemberId, successor)
            self.assertEqual(player.mainSinceDate,
                             "2026-03-15" if successor else None)
            self.assertEqual([(item.memberId, item.toDate, item.reason)
                              for item in player.mainHistory],
                             [("m1000", "2026-03-15", "death")])
            self.assertEqual(dead.members[0].lifeStatus, "dead")
            self.assertEqual(dead.members[0].graveTemplateId, "main-history-stone")
            self.assertEqual(dead.members[0].playerId, "p1")
            self.assertEqual(dead.to_payload()["attendance"], before["attendance"])
            self.assertEqual(store.to_payload(), before)

    def test_death_conflict_precedes_successor_and_preserves_store(self):
        store = sample_store(candidates=3)
        before = store.to_payload()
        with self.assertRaises(DeathAttendanceConflict):
            mark_member_dead(store, "m1000", "2026-03-14", "collective")
        self.assertEqual(store.to_payload(), before)

    def test_candidate_filter_is_id_safe(self):
        store = sample_store(candidates=1)
        candidates = get_main_successor_candidates(store, "p1", "m1000")
        self.assertEqual([item.memberId for item in candidates], ["m1001"])

    def test_non_main_death_and_legacy_roles_do_not_create_history(self):
        store = sample_store()
        store.members[1].currentRole = "main"
        store.members[0].currentRole = "twink"
        store.validate()
        self.assertEqual(store.players[0].mainHistory, [])
        dead = mark_member_dead(store, "m1001", "2026-03-15", "collective")
        self.assertEqual(dead.players[0].mainMemberId, "m1000")
        self.assertEqual(dead.players[0].mainHistory, [])
        self.assertEqual(dead.attendance[0].attendanceType, "main")
        with self.assertRaises(IdentityV2ValidationError):
            mark_member_dead(store, "m1001", "2026-03-15",
                             "collective", "m1002")

    def test_same_name_new_member_is_not_old_dead_main(self):
        store = IdentityV2Store(
            players=[Player("p1", "Sorap-Spieler")],
            members=[
                Member("m1000", "Sorap", "Warrior", lifeStatus="dead",
                       burialType="individual", deathDate="2026-03-01", playerId="p1"),
                Member("m1001", "Sorap", "Warrior", playerId="p1"),
            ],
        )
        store = add_main_history_entry(store, "p1", "m1000", None, "2026-03-01")
        store = set_main(store, "p1", "m1001", "2026-03-01")
        self.assertEqual(store.players[0].mainHistory[0].memberId, "m1000")
        self.assertEqual(store.players[0].mainMemberId, "m1001")
        self.assertEqual(store.members[0].lifeStatus, "dead")

    def test_overlap_conflicts_are_reported_not_repaired(self):
        store = sample_store()
        store = add_main_history_entry(store, "p1", "m1001",
                                       "2025-01-01", "2025-08-01")
        store = add_main_history_entry(store, "p1", "m1002",
                                       "2025-06-01", "2025-09-01")
        before = store.to_payload()
        conflicts = find_main_history_conflicts(store, "p1")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].historyIds, ("mh0001", "mh0002"))
        self.assertEqual(conflicts[0].memberIds, ("m1001", "m1002"))
        self.assertEqual(store.to_payload(), before)
        touched = update_main_history_entry(store, "mh0002",
                                            from_date="2025-08-01")
        self.assertEqual(find_main_history_conflicts(touched, "p1"), ())
        unknown = update_main_history_entry(store, "mh0002", from_date=None)
        self.assertEqual(find_main_history_conflicts(unknown, "p1"), ())
        current_overlap = add_main_history_entry(
            store, "p1", "m1002", "2026-02-01", "2026-04-01")
        self.assertTrue(any("current" in item.historyIds
                            for item in find_main_history_conflicts(current_overlap, "p1")))
        duplicate_period = add_main_history_entry(
            store, "p1", "m1001", "2025-02-01", "2025-03-01")
        self.assertTrue(any(item.memberIds == ("m1001", "m1001")
                            for item in find_main_history_conflicts(duplicate_period, "p1")))
        future = add_main_history_entry(
            store, "p1", "m1001",
            date(date.today().year + 1, 1, 1).isoformat(),
            date(date.today().year + 1, 6, 1).isoformat())
        self.assertEqual(len(find_main_history_conflicts(future, "p1")), 1)

    def test_validator_rejects_broken_history_but_not_overlap(self):
        store = sample_store()
        store.players[0].mainHistory = [
            MainHistoryEntry("mh0001", "m1001", "2025-01-01", "2025-09-01",
                             "manual"),
            MainHistoryEntry("mh0002", "m1002", "2025-06-01", "2025-12-01",
                             "manual"),
        ]
        store.validate()
        variants = (
            ("historyId", "mh0001"), ("historyId", "current"),
            ("memberId", "m1004"),
            ("fromDate", "2025-13-01"), ("fromDate", "2026-01-01"),
            ("source", "P2"), ("reason", "death"),
        )
        for field_name, value in variants:
            changed = IdentityV2Store.from_payload(store.to_payload())
            setattr(changed.players[0].mainHistory[1], field_name, value)
            with self.subTest(field_name=field_name, value=value), self.assertRaises(
                    IdentityV2ValidationError):
                changed.validate()
        empty_main = sample_store()
        empty_main.players[0].mainMemberId = None
        with self.assertRaises(IdentityV2ValidationError):
            empty_main.validate()


if __name__ == "__main__":
    unittest.main()
