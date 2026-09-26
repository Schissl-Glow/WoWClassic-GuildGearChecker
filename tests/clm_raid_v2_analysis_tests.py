"""Focused, UI-free tests for read-only CLM raid and P2 role analysis."""

import unittest
from datetime import datetime, timezone

from app.clm_identity_v2_analysis import analyze_clm_ledger
from app.clm_identity_v2_decisions import CONTINUE, NEW_CHARACTER, ClmIdentityDecisionDraft
from app.clm_raid_v2_analysis import analyze_clm_raid_ledger
from app.clm_replay import _entry_uuid
from app.identity_v2 import IdentityV2Store, Member


def stamp(day: int, hour: int = 12) -> int:
    return int(datetime(2025, 1, day, hour, tzinfo=timezone.utc).timestamp())


def event(timestamp: int, opcode: str, sequence: int, **fields):
    return {"_c": timestamp, "_b": 0, "_e": 1, "_a": sequence,
            "_d": opcode, **fields}


class ClmRaidV2AnalysisTests(unittest.TestCase):
    ROSTER = "roster-1"

    def base(self):
        return [
            event(stamp(1), "R0", 1, r=self.ROSTER, n="Bierstube", p=0),
            event(stamp(1, 13), "P0", 2, g=[1, 101], n="Main-Stitches", c=5),
            event(stamp(1, 14), "R9", 3, r=self.ROSTER, p=[[1, 101]]),
        ]

    def raid(self, start, sequence=10, name="MC"):
        created = event(start, "AC", sequence, r=self.ROSTER, n=name, c={})
        return created, _entry_uuid(created)

    def test_raid_start_end_and_participant_source_fields(self):
        created, raid_id = self.raid(stamp(3))
        events = self.base() + [
            created,
            event(stamp(3, 13), "AS", 11, r=raid_id, p=[[1, 101]], s=[]),
            event(stamp(3, 14), "AE", 12, r=raid_id),
        ]
        result = analyze_clm_raid_ledger(events, self.ROSTER)
        self.assertEqual(len(result.raids), 1)
        raid = result.raids[0]
        self.assertEqual((raid.raid_id, raid.name, raid.start_timestamp, raid.end_timestamp),
                         (raid_id, "MC", stamp(3), stamp(3, 14)))
        self.assertEqual([item.guid for item in raid.participants], ["1:101"])
        self.assertEqual(raid.participants[0].source_event_ids,
                         (_entry_uuid(events[-2]),))
        self.assertEqual(result.first_actual_raid_date("1:101"), "03.01.2025")
        self.assertNotEqual(result.first_actual_raid_date("1:101"), "01.01.2025")
        self.assertEqual(raid.participants[0].guid_status, "VALID_CHARACTER_GUID")

    def test_bench_only_is_not_an_actual_attendance(self):
        created, raid_id = self.raid(stamp(3))
        result = analyze_clm_raid_ledger(self.base() + [
            created,
            event(stamp(3, 13), "AS", 11, r=raid_id, p=[], s=[[1, 101]]),
        ], self.ROSTER)
        self.assertEqual(result.raids[0].participants, ())
        self.assertEqual(result.raids[0].bench_guids, ("1:101",))
        self.assertEqual(result.summary["benchOnlyGuidRaidReferences"], 1)

    def test_bench_then_present_has_one_actual_participation(self):
        created, raid_id = self.raid(stamp(3))
        result = analyze_clm_raid_ledger(self.base() + [
            created,
            event(stamp(3, 13), "AS", 11, r=raid_id, p=[], s=[[1, 101]]),
            event(stamp(3, 14), "AU", 12, r=raid_id, j=[[1, 101]], l=[], s=[]),
        ], self.ROSTER)
        self.assertEqual(result.summary["uniqueGuidAttendances"], 1)
        self.assertEqual(result.summary["benchOnlyGuidRaidReferences"], 0)
        self.assertEqual(result.raids[0].participants[0].occurrence_count, 1)

    def test_bench_only_second_guid_does_not_create_same_raid_coexistence(self):
        created, raid_id = self.raid(stamp(4))
        result = analyze_clm_raid_ledger(self.base() + [
            event(stamp(2), "P0", 4, g=[1, 102], n="Main-Stitches", c=5),
            event(stamp(2, 13), "R9", 5, r=self.ROSTER, p=[[1, 102]]),
            created,
            event(stamp(4, 13), "AS", 11, r=raid_id,
                  p=[[1, 101]], s=[[1, 102]]),
        ], self.ROSTER)
        self.assertEqual(result.summary["uniqueGuidAttendances"], 1)
        self.assertEqual(result.summary["benchOnlyGuidRaidReferences"], 1)
        self.assertEqual(result.identity_analysis.raid_coexistence, ())

    def test_repeated_participant_events_count_once_but_keep_sources(self):
        created, raid_id = self.raid(stamp(3))
        start = event(stamp(3, 13), "AS", 11, r=raid_id, p=[[1, 101]], s=[])
        update = event(stamp(3, 14), "AU", 12, r=raid_id, j=[[1, 101]], l=[], s=[])
        result = analyze_clm_raid_ledger(self.base() + [created, start, update], self.ROSTER)
        item = result.raids[0].participants[0]
        self.assertEqual(result.summary["uniqueGuidAttendances"], 1)
        self.assertEqual((item.occurrence_count, len(item.source_event_ids)), (2, 2))
        self.assertEqual(result.summary["duplicateParticipantOccurrences"], 1)
        self.assertEqual(result.identity_analysis.raid_coexistence, ())

    def test_raid_removal_keeps_one_attendance_and_last_source_event(self):
        created, raid_id = self.raid(stamp(3))
        leave = event(stamp(3, 14), "AU", 12, r=raid_id, j=[], l=[], s=[], e=[[1, 101]])
        result = analyze_clm_raid_ledger(self.base() + [
            created,
            event(stamp(3, 13), "AS", 11, r=raid_id, p=[[1, 101]], s=[]),
            leave,
        ], self.ROSTER)
        item = result.raids[0].participants[0]
        self.assertEqual(item.occurrence_count, 1)
        self.assertEqual(item.last_seen_in_raid, stamp(3, 14))
        self.assertIn(_entry_uuid(leave), item.source_event_ids)

    def test_unknown_and_technical_guids_are_not_valid_characters(self):
        created, raid_id = self.raid(stamp(3))
        result = analyze_clm_raid_ledger(self.base() + [
            created,
            event(stamp(3, 13), "AS", 11, r=raid_id,
                  p=[[1, 101], [1, 999], [1, 0]], s=[]),
        ], self.ROSTER)
        statuses = {item.guid: item.guid_status for item in result.raids[0].participants}
        self.assertEqual(statuses, {
            "1:101": "VALID_CHARACTER_GUID", "1:999": "UNKNOWN_GUID",
            "1:0": "TECHNICAL_GUID",
        })
        self.assertEqual(result.summary["unknownGuidAttendances"], 1)
        self.assertEqual(result.summary["technicalGuidAttendances"], 1)
        self.assertEqual(result.summary["participantGuidsWithoutValidP0"], 2)
        unresolved = next(item for item in result.identity_analysis.guid_histories
                          if item.guid == "1:999")
        self.assertEqual(unresolved.normalized_name, "")

    def test_malformed_participant_guid_is_reported_as_invalid_reference(self):
        created, raid_id = self.raid(stamp(3))
        result = analyze_clm_raid_ledger(self.base() + [
            created,
            event(stamp(3, 13), "AS", 11, r=raid_id,
                  p=[[1, 101], ["bad", "guid"]], s=[]),
        ], self.ROSTER)
        statuses = {item.guid: item.guid_status for item in result.raids[0].participants}
        self.assertEqual(statuses["bad:guid"], "INVALID_REFERENCE")
        self.assertEqual(result.summary["invalidGuidAttendances"], 1)

    def test_p2_role_is_snapshotted_at_raid_time_and_unlink_does_not_mean_main(self):
        first, first_id = self.raid(stamp(3), 10)
        second, second_id = self.raid(stamp(5), 20)
        events = self.base() + [
            event(stamp(2), "P0", 4, g=[1, 102], n="Alt-Stitches", c=8),
            event(stamp(2, 13), "R9", 5, r=self.ROSTER, p=[[1, 102]]),
            event(stamp(2, 14), "P2", 6, g=[1, 102], m=[1, 101]),
            first,
            event(stamp(3, 13), "AS", 11, r=first_id, p=[[1, 101], [1, 102]], s=[]),
            event(stamp(4), "P2", 12, g=[1, 102], m=[1, 0]),
            second,
            event(stamp(5, 13), "AS", 21, r=second_id, p=[[1, 102]], s=[]),
        ]
        result = analyze_clm_raid_ledger(events, self.ROSTER)
        first_roles = {item.guid: item.historical_role for item in result.raids[0].participants}
        self.assertEqual(first_roles, {"1:101": "main", "1:102": "twink"})
        p2_event_id = _entry_uuid(events[5])
        self.assertTrue(all(item.role_source_event_ids == (p2_event_id,)
                            for item in result.raids[0].participants))
        self.assertEqual(result.raids[1].participants[0].historical_role, "unknown")
        self.assertEqual(result.summary["p2MainAttendances"], 1)
        self.assertEqual(result.summary["p2TwinkAttendances"], 1)
        self.assertEqual(result.summary["p2UnknownAttendances"], 1)

    def test_role_change_within_one_raid_stays_unknown(self):
        created, raid_id = self.raid(stamp(3), 10)
        events = self.base() + [
            event(stamp(2), "P0", 4, g=[1, 102], n="Alt-Stitches", c=8),
            event(stamp(2, 13), "R9", 5, r=self.ROSTER, p=[[1, 102]]),
            event(stamp(2, 14), "P2", 6, g=[1, 102], m=[1, 101]),
            created,
            event(stamp(3, 13), "AS", 11, r=raid_id, p=[[1, 102]], s=[]),
            event(stamp(3, 14), "P2", 12, g=[1, 102], m=[1, 0]),
            event(stamp(3, 15), "AU", 13, r=raid_id, j=[[1, 102]], l=[], s=[]),
        ]
        result = analyze_clm_raid_ledger(events, self.ROSTER)
        self.assertEqual(result.raids[0].participants[0].historical_role, "unknown")

    def test_same_name_multi_guid_coattendance_is_reported_without_merge(self):
        created, raid_id = self.raid(stamp(4))
        events = self.base() + [
            event(stamp(2), "P0", 4, g=[1, 102], n="Main-Stitches", c=5),
            event(stamp(2, 13), "R9", 5, r=self.ROSTER, p=[[1, 102]]),
            created,
            event(stamp(4, 13), "AS", 11, r=raid_id, p=[[1, 101], [1, 102]], s=[]),
        ]
        raw_identity = analyze_clm_ledger(events, self.ROSTER)
        result = analyze_clm_raid_ledger(events, self.ROSTER)
        self.assertEqual(result.summary["sameNameMultiGuidRaidCollisions"], 1)
        self.assertEqual(result.summary["suggestedChainRaidCollisions"], 0)
        self.assertEqual(result.summary["uniqueGuidAttendances"], 2)
        collision = result.multi_guid_collisions[0]
        self.assertEqual((collision.normalized_name, collision.guids),
                         ("Main", ("1:101", "1:102")))
        self.assertFalse(collision.includes_suggested_chain)
        enriched = result.identity_analysis
        self.assertEqual(len(enriched.raid_coexistence), 1)
        group = enriched.group_for_name("Main")
        self.assertIn("SAME_RAID_COEXISTENCE", group.conflicts)
        self.assertIn("SAME_RAID_COEXISTENCE", group.pairwise[0].conflicts)
        self.assertNotIn("SAME_RAID_COEXISTENCE",
                         raw_identity.group_for_name("Main").conflicts)
        draft = ClmIdentityDecisionDraft(enriched)
        self.assertEqual(draft.allowed_actions("Main", "1:102"), (NEW_CHARACTER,))
        self.assertIn("Gleichzeitig im selben Raid", draft.rows_for("Main")[1].analysis)

    def test_separate_raid_periods_keep_manual_continuation_available(self):
        first, first_id = self.raid(stamp(3), 10)
        second, second_id = self.raid(stamp(7), 20)
        result = analyze_clm_raid_ledger(self.base() + [
            first,
            event(stamp(3, 13), "AS", 11, r=first_id, p=[[1, 101]], s=[]),
            event(stamp(4), "P1", 12, g=[1, 101]),
            event(stamp(5), "P0", 13, g=[1, 102], n="Main-Stitches", c=5),
            event(stamp(5, 13), "R9", 14, r=self.ROSTER, p=[[1, 102]]),
            second,
            event(stamp(7, 13), "AS", 21, r=second_id, p=[[1, 102]], s=[]),
        ], self.ROSTER)
        self.assertEqual(result.identity_analysis.raid_coexistence, ())
        draft = ClmIdentityDecisionDraft(result.identity_analysis)
        self.assertEqual(draft.allowed_actions("Main", "1:102"),
                         (CONTINUE, NEW_CHARACTER))

    def test_old_identity_delta_is_profile_field_not_raid_participation(self):
        created, raid_id = self.raid(stamp(3))
        entries = self.base()
        entries[1]["s"] = [1, 0]
        entries.extend([
            event(stamp(2), "P0", 4, g=[1, 202], n="Fremd-Stitches", c=8, m=[1, 0]),
            created,
            event(stamp(3, 13), "AS", 11, r=raid_id, p=[[1, 101]], s=[]),
        ])
        result = analyze_clm_raid_ledger(entries, self.ROSTER)
        self.assertEqual(result.old_identity_event_count - result.current_identity_event_count, 1)
        self.assertEqual([(item.opcode, item.count) for item in result.old_only_events],
                         [("P0", 1)])
        self.assertEqual(result.old_only_events[0].reference_fields, (("m", 1),))
        self.assertEqual(result.old_only_events[0].matched_guids, (("1:0", 1),))
        self.assertEqual(result.summary["uniqueGuidAttendances"], 1)

    def test_read_only_analysis_does_not_mutate_v2_store(self):
        store = IdentityV2Store(members=[Member("m1000", "Main", "Priest")])
        before = store.to_payload()
        created, raid_id = self.raid(stamp(3))
        analyze_clm_raid_ledger(self.base() + [
            created, event(stamp(3, 13), "AS", 11, r=raid_id, p=[[1, 101]], s=[]),
        ], self.ROSTER)
        self.assertEqual(store.to_payload(), before)


if __name__ == "__main__":
    unittest.main()
