"""Hard CLM attendance bracket for otherwise ambiguous same-name CSV occurrences."""

import tempfile
import unittest
from pathlib import Path

from app.csv_v2_analysis import analyze_csv_raids_for_v2
from app.csv_v2_materialization import CsvImportDecisions, materialize_csv_raid_import
from app.identity_v2 import Attendance, IdentityV2Store, Member, Raid


class CsvV2ClmBracketTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = IdentityV2Store(members=[
            Member("m1000", "Annî", "Priest", clmGuid="1:1"),
            Member("m1001", "Annî", "Mage", clmGuid="1:2"),
        ])

    def clm(self, raid_id: str, day: str, member_id: str,
            *, source_guid: str | None = None) -> None:
        self.store.raids.append(Raid(raid_id, day, name="MC", clmRaidId=raid_id))
        guid = source_guid if source_guid is not None else (
            "1:1" if member_id == "m1000" else "1:2"
        )
        self.store.attendance.append(Attendance(
            f"a_{raid_id}", raid_id, member_id, "unknown", clmGuid=guid,
        ))

    def csv(self, day: str, *, name: str = "Annî") -> Path:
        path = self.root / f"{day}_BWL_Casts.csv"
        path.write_text(f'"Name","Amount"\n"{name}","1"\n', encoding="utf-8")
        return path

    def test_same_member_on_both_sides_is_auto_resolved_and_materializes(self):
        self.clm("r_before", "2026-04-10", "m1000")
        self.clm("r_after", "2026-04-13", "m1000")
        source = self.csv("2026-04-12")
        before = self.store.to_payload()
        plan = analyze_csv_raids_for_v2(self.store, [source])
        self.assertEqual(plan.ambiguous_member_matches, ())
        self.assertEqual(len(plan.clm_bracket_matches), 1)
        match = plan.clm_bracket_matches[0]
        self.assertEqual((match.member_id, match.match_reason),
                         ("m1000", "CLM_BRACKET"))
        self.assertEqual((match.clm_bracket.before_date,
                          match.clm_bracket.after_date),
                         ("2026-04-10", "2026-04-13"))
        result, summary = materialize_csv_raid_import(
            self.store, plan, CsvImportDecisions(),
        )
        self.assertEqual(summary.new_attendance, 1)
        self.assertEqual(result.attendance[-1].memberId, "m1000")
        self.assertEqual(self.store.to_payload(), before)

    def test_different_members_on_two_sides_stay_manual_with_context(self):
        self.clm("r_before", "2026-04-10", "m1000")
        self.clm("r_after", "2026-04-13", "m1001")
        plan = analyze_csv_raids_for_v2(self.store, [self.csv("2026-04-12")])
        self.assertEqual(plan.clm_bracket_matches, ())
        self.assertEqual(len(plan.ambiguous_member_matches), 1)
        evidence = plan.ambiguous_member_matches[0].clm_bracket
        self.assertEqual(evidence.before_member_ids, ("m1000",))
        self.assertEqual(evidence.after_member_ids, ("m1001",))

    def test_one_sided_clm_attendance_is_only_temporal_context(self):
        self.clm("r_before", "2026-04-10", "m1000")
        plan = analyze_csv_raids_for_v2(self.store, [self.csv("2026-04-12")])
        self.assertEqual(plan.clm_bracket_matches, ())
        match = plan.ambiguous_member_matches[0]
        self.assertEqual(match.clm_bracket.before_member_ids, ("m1000",))
        self.assertIsNone(match.clm_bracket.after_date)

    def test_only_later_clm_attendance_does_not_auto_resolve(self):
        self.clm("r_after", "2026-04-13", "m1000")
        plan = analyze_csv_raids_for_v2(self.store, [self.csv("2026-04-12")])
        self.assertEqual(plan.clm_bracket_matches, ())
        match = plan.ambiguous_member_matches[0]
        self.assertIsNone(match.clm_bracket.before_date)
        self.assertEqual(match.clm_bracket.after_member_ids, ("m1000",))

    def test_nearest_clm_attendance_controls_bracket_not_older_match(self):
        self.clm("r_old", "2026-04-01", "m1000")
        self.clm("r_near", "2026-04-10", "m1001")
        self.clm("r_after", "2026-04-13", "m1000")
        plan = analyze_csv_raids_for_v2(self.store, [self.csv("2026-04-12")])
        self.assertEqual(plan.clm_bracket_matches, ())
        bracket = plan.ambiguous_member_matches[0].clm_bracket
        self.assertEqual(bracket.before_date, "2026-04-10")
        self.assertEqual(bracket.before_member_ids, ("m1001",))
        self.assertEqual(bracket.after_member_ids, ("m1000",))

    def test_multiple_csv_raids_inside_one_clm_bracket_all_resolve(self):
        self.clm("r_before", "2026-04-10", "m1000")
        self.clm("r_after", "2026-04-15", "m1000")
        sources = [self.csv(f"2026-04-{day:02d}") for day in (11, 12, 13, 14)]
        plan = analyze_csv_raids_for_v2(self.store, sources)
        self.assertEqual(len(plan.clm_bracket_matches), 4)
        self.assertEqual({item.member_id for item in plan.clm_bracket_matches},
                         {"m1000"})
        self.assertEqual(plan.ambiguous_member_matches, ())

    def test_profiles_bank_only_and_csv_supplements_do_not_close_bracket(self):
        # A CLM raid without Attendance can represent bank-only evidence.
        self.store.raids.append(Raid("r_bank", "2026-04-10", name="MC",
                                     clmRaidId="clm-bank"))
        # An Attendance with no CLM source GUID came from CSV, even on a CLM raid.
        self.store.attendance.append(Attendance(
            "a_csv", "r_bank", "m1000", "unknown", clmGuid=None,
        ))
        self.clm("r_after", "2026-04-13", "m1000")
        plan = analyze_csv_raids_for_v2(self.store, [self.csv("2026-04-12")])
        self.assertEqual(plan.clm_bracket_matches, ())
        self.assertEqual(len(plan.ambiguous_member_matches), 1)
        self.assertIsNone(plan.ambiguous_member_matches[0].clm_bracket.before_date)

    def test_same_day_clm_evidence_has_no_known_order(self):
        self.clm("r_same", "2026-04-12", "m1000")
        self.clm("r_after", "2026-04-13", "m1000")
        plan = analyze_csv_raids_for_v2(self.store, [self.csv("2026-04-12")])
        self.assertEqual(plan.clm_bracket_matches, ())
        self.assertEqual(len(plan.ambiguous_member_matches), 1)

    def test_multiple_same_name_members_on_nearest_clm_day_do_not_auto_resolve(self):
        self.clm("r_first", "2026-04-10", "m1000")
        self.clm("r_second", "2026-04-10", "m1001")
        self.clm("r_after", "2026-04-13", "m1000")
        plan = analyze_csv_raids_for_v2(self.store, [self.csv("2026-04-12")])
        self.assertEqual(plan.clm_bracket_matches, ())
        self.assertEqual(plan.ambiguous_member_matches[0].clm_bracket.before_member_ids,
                         ("m1000", "m1001"))

    def test_death_date_exclusion_beats_same_member_clm_bracket(self):
        self.clm("r_before", "2026-04-10", "m1000")
        self.clm("r_after", "2026-04-13", "m1000")
        self.store.members[0].deathDate = "2026-04-11"
        plan = analyze_csv_raids_for_v2(self.store, [self.csv("2026-04-12")])
        self.assertEqual(plan.clm_bracket_matches, ())
        self.assertEqual(plan.resolved_member_matches[0].member_id, "m1001")
        self.assertEqual(plan.resolved_member_matches[0].match_reason, "DEATH_FILTER")
        self.assertEqual(len(plan.existing_death_conflicts), 1)

    def test_accents_must_match_exactly_for_clm_bracket(self):
        self.clm("r_before", "2026-04-10", "m1000")
        self.clm("r_after", "2026-04-13", "m1000")
        plan = analyze_csv_raids_for_v2(
            self.store, [self.csv("2026-04-12", name="Ânní")],
        )
        self.assertEqual(plan.clm_bracket_matches, ())
        self.assertEqual(plan.new_member_candidates[0].name, "Ânní")


if __name__ == "__main__":
    unittest.main()
