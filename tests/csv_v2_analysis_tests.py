"""Focused Lua-first, read-only CSV bulk analysis tests."""

import tempfile
import unittest
from pathlib import Path

from app.csv_v2_analysis import (
    CsvV2AnalysisError, analyze_csv_raids_for_v2, temporal_match_indicator,
)
from app.csv_import import read_raid_csv
from app.identity_v2 import (
    Attendance, IdentityV2Store, IdentityV2ValidationError, Member, Raid,
    require_member_attendance_date,
)


class CsvV2AnalysisTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = IdentityV2Store(
            members=[
                Member("m1", "Annî", "Priest", clmGuid="1:1",
                       raidStartDate="2026-08-21"),
                Member("m2", "Veniell", "Mage", clmGuid="1:2",
                       raidStartDate="2026-01-01"),
                Member("m3", "Veniell", "Warrior", clmGuid="1:3",
                       raidStartDate="2026-09-01"),
            ],
            raids=[Raid("r1", "2026-08-21", name="MC", clmRaidId="clm-1")],
            attendance=[
                Attendance("a1", "r1", "m1", "main", clmGuid="1:1"),
                Attendance("a2", "r1", "m2", "twink", clmGuid="1:2"),
            ],
        )

    def write(self, name, rows, metadata=""):
        target = self.root / name
        target.write_text(metadata + '"Name","Amount"\n' + rows, encoding="utf-8")
        return target

    def test_metadata_preferred_exact_names_and_partial_duplicate(self):
        source = self.write(
            "2026-08-21_MC_Casts.csv",
            '"ANNÎ-Stitches","1"\n"Veniell","1"\n"Anni","1"\n',
            '"META_RAID_TYPE","MC"\n"META_RAID_DATE","2026-08-21"\n'
            '"META_REPORT_URL","https://vanilla.warcraftlogs.com/reports/abc"\n',
        )
        before = self.store.to_payload()
        plan = analyze_csv_raids_for_v2(self.store, [source])
        raid = plan.raid_candidates[0]
        self.assertEqual((raid.raid_date, raid.raid_type, raid.report_url),
                         ("2026-08-21", "MC",
                          "https://vanilla.warcraftlogs.com/reports/abc"))
        self.assertEqual(raid.status, "KNOWN_RAID")
        self.assertEqual((raid.existing_attendance_count,
                          raid.additional_attendance_count), (1, 2))
        self.assertEqual(plan.resolved_member_matches[0].member_id, "m1")
        self.assertTrue(plan.resolved_member_matches[0].existing_attendance)
        self.assertEqual(len(plan.ambiguous_member_matches), 1)
        self.assertEqual({item.member_id for item in plan.ambiguous_member_matches[0].options},
                         {"m2", "m3"})
        self.assertEqual(plan.new_member_candidates[0].name, "Anni")
        self.assertIsNone(plan.new_member_candidates[0].class_name)
        self.assertEqual(plan.new_member_candidates[0].blocker, "")
        self.assertTrue(all(item.planned_attendance_type == "unknown"
                            for item in plan.attendance_candidates))
        self.assertEqual(self.store.attendance[0].attendanceType, "main")
        self.assertEqual(self.store.to_payload(), before)

    def test_no_meta_fallback_known_new_and_earlier_start(self):
        known = self.write("2026-08-21_MC_Casts.csv", '"Annî","1"\n')
        new = self.write("2026-07-01_BWL_Casts.csv", '"Annî","1"\n')
        plan = analyze_csv_raids_for_v2(self.store, [new, known])
        by_name = {item.source_path.name: item for item in plan.raid_candidates}
        self.assertEqual(by_name[known.name].status, "KNOWN_RAID")
        self.assertEqual(by_name[new.name].status, "NEW_RAID")
        self.assertTrue(next(item.earlier_raid_start for item in plan.attendance_candidates
                             if item.source_path == new))
        self.assertFalse(next(item.earlier_raid_start for item in plan.attendance_candidates
                              if item.source_path == known))

    def test_source_raid_title_survives_type_normalization(self):
        source = self.write(
            "2026-09-08_ZulGurub_Casts.csv", '"Annî","1"\n',
            '"META_RAID_TYPE","ZulGurub"\n"META_RAID_DATE","2026-09-08"\n',
        )
        raid = analyze_csv_raids_for_v2(self.store, [source]).raid_candidates[0]
        self.assertEqual((raid.raid_type, raid.raid_name), ("ZG", "ZulGurub"))

    def test_multi_raid_csv_title_uses_shared_priority_and_aq20_alias(self):
        mixed = self.write(
            "2026-09-08_Ony_MC_Casts.csv", '"Annî","1"\n',
            '"META_RAID_TYPE","Ony / MC"\n"META_RAID_DATE","2026-09-08"\n',
        )
        candidate = analyze_csv_raids_for_v2(self.store, [mixed]).raid_candidates[0]
        self.assertEqual((candidate.raid_type, candidate.raid_name),
                         ("MC", "Ony / MC"))
        bare_aq = self.write("2026-09-09_AQ_Casts.csv", '"Annî","1"\n')
        plan = analyze_csv_raids_for_v2(self.store, [bare_aq])
        self.assertEqual((plan.raid_candidates[0].raid_type,
                          plan.raid_candidates[0].raid_name), ("AQ20", "AQ"))
        self.assertFalse(any("unbekannter Raid-Typ" in warning
                             for warning in plan.warnings))
        contextual = self.write(
            "2026-09-10_AQ20_Casts.csv", '"Annî","1"\n',
            '"META_RAID_TYPE","AQ"\n"META_RAID_DATE","2026-09-10"\n',
        )
        contextual_plan = analyze_csv_raids_for_v2(self.store, [contextual])
        self.assertEqual((contextual_plan.raid_candidates[0].raid_type,
                          contextual_plan.raid_candidates[0].raid_name),
                         ("AQ20", "AQ"))
        self.assertFalse(any("unbekannter Raid-Typ" in warning
                             for warning in contextual_plan.warnings))
        world_boss_mix = self.write(
            "2026-09-11_Azu_AQ_ZG_Casts.csv", '"Annî","1"\n',
            '"META_RAID_TYPE","Azu, AQ, ZG"\n'
            '"META_RAID_DATE","2026-09-11"\n',
        )
        self.assertEqual(
            analyze_csv_raids_for_v2(self.store, [world_boss_mix])
            .raid_candidates[0].raid_type, "AQ20")

    def test_ambiguity_is_separate_for_each_raid_occurrence(self):
        first = self.write("2026-07-01_MC_Casts.csv", '"Veniell","1"\n')
        second = self.write("2026-09-08_ZulGurub_Casts.csv", '"Veniell","1"\n')
        plan = analyze_csv_raids_for_v2(self.store, [second, first])
        self.assertEqual(len(plan.ambiguous_member_matches), 2)
        self.assertEqual({item.source_path for item in plan.ambiguous_member_matches},
                         {first, second})
        self.assertEqual({item.raid_date for item in plan.ambiguous_member_matches},
                         {"2026-07-01", "2026-09-08"})
        self.assertEqual(len(plan.ambiguous_member_matches[0].options), 2)

    def test_same_day_second_csv_is_possible_duplicate(self):
        first = self.write("2026-07-01_MC_Casts.csv", '"Annî","1"\n')
        second = self.write("2026-07-01_MC_Casts_2.csv", '"Annî","1"\n',
                            '"META_RAID_TYPE","MC"\n"META_RAID_DATE","2026-07-01"\n')
        plan = analyze_csv_raids_for_v2(self.store, [first, second])
        self.assertEqual([item.status for item in plan.raid_candidates],
                         ["NEW_RAID", "POSSIBLE_DUPLICATE"])

    def test_invalid_file_returns_no_partial_plan_and_no_mutation(self):
        valid = self.write("2026-07-01_MC_Casts.csv", '"Annî","1"\n')
        invalid = self.root / "2026-07-02_BWL_Casts.csv"
        invalid.write_text('"Wrong","Amount"\n"Annî","1"\n', encoding="utf-8")
        before = self.store.to_payload()
        with self.assertRaises(CsvV2AnalysisError):
            analyze_csv_raids_for_v2(self.store, [valid, invalid])
        self.assertEqual(self.store.to_payload(), before)

    def test_new_member_class_only_from_supported_csv_class_column(self):
        source = self.root / "2026-07-01_MC_Casts.csv"
        source.write_text('"Name","Class"\n"Bífi","Druid"\n'
                          '"Anni","unbekannt"\n', encoding="utf-8")
        self.assertEqual(read_raid_csv(source).classes_by_name,
                         (("bífi", "Druid"),))
        plan = analyze_csv_raids_for_v2(self.store, [source])
        by_name = {item.name: item for item in plan.new_member_candidates}
        self.assertEqual(by_name["Bífi"].class_name, "Druid")
        self.assertEqual(by_name["Bífi"].blocker, "")
        self.assertIsNone(by_name["Anni"].class_name)
        self.assertEqual(by_name["Anni"].blocker, "")

    def test_accents_are_never_removed_or_fuzzy_matched(self):
        source = self.write(
            "2026-07-01_MC_Casts.csv",
            '"Annî","1"\n"Ânní","1"\n"Jêmma","1"\n"Jêmmâ","1"\n',
        )
        plan = analyze_csv_raids_for_v2(self.store, [source])
        self.assertEqual([item.member_id for item in plan.resolved_member_matches],
                         ["m1"])
        self.assertEqual({item.name for item in plan.new_member_candidates},
                         {"Ânní", "Jêmma", "Jêmmâ"})

    def test_death_date_excludes_only_raids_strictly_after_that_day(self):
        self.store.members[1].deathDate = "2026-03-15"
        before = self.write("2026-03-14_MC_Casts.csv", '"Veniell","1"\n')
        on_day = self.write("2026-03-15_MC_Casts.csv", '"Veniell","1"\n')
        after = self.write("2026-03-16_MC_Casts.csv", '"Veniell","1"\n')
        plan = analyze_csv_raids_for_v2(self.store, [before, on_day, after])
        ambiguous = {item.source_path: item for item in plan.ambiguous_member_matches}
        self.assertEqual({option.member_id for option in ambiguous[before].options},
                         {"m2", "m3"})
        self.assertEqual({option.member_id for option in ambiguous[on_day].options},
                         {"m2", "m3"})
        resolved_after = next(item for item in plan.resolved_member_matches
                              if item.source_path == after)
        self.assertEqual(resolved_after.member_id, "m3")
        self.assertTrue(any("m2" in text and "Todesdatum" in text
                            for text in plan.warnings))
        self.assertEqual(len(plan.blocked_member_matches), 0)

    def test_all_same_name_members_dead_creates_open_blocked_conflict(self):
        self.store.members[1].deathDate = "2026-03-15"
        self.store.members[2].deathDate = "2026-03-20"
        source = self.write("2026-04-20_MC_Casts.csv", '"Veniell","1"\n')
        before = self.store.to_payload()
        plan = analyze_csv_raids_for_v2(self.store, [source])
        self.assertEqual(len(plan.blocked_member_matches), 1)
        blocked = plan.blocked_member_matches[0]
        self.assertEqual({option.member_id for option in blocked.excluded_options},
                         {"m2", "m3"})
        self.assertEqual(plan.attendance_candidates[0].status, "NO_ELIGIBLE_MEMBER")
        self.assertEqual(plan.resolved_member_matches, ())
        self.assertEqual(plan.new_member_candidates, ())
        self.assertEqual(self.store.to_payload(), before)

    def test_existing_post_death_attendance_is_reported_without_deletion(self):
        self.store.members[0].deathDate = "2026-08-20"
        source = self.write("2026-08-21_MC_Casts.csv", '"Annî","1"\n')
        before = self.store.to_payload()
        plan = analyze_csv_raids_for_v2(self.store, [source])
        self.assertEqual(len(plan.existing_death_conflicts), 1)
        self.assertEqual(plan.existing_death_conflicts[0].member_id, "m1")
        self.assertEqual(len(plan.blocked_member_matches), 1)
        self.assertEqual(self.store.to_payload(), before)

    def test_future_materialization_guard_rejects_after_death_only(self):
        member = self.store.members[0]
        member.deathDate = "2026-03-15"
        require_member_attendance_date(member, "2026-03-14")
        require_member_attendance_date(member, "2026-03-15")
        with self.assertRaises(IdentityV2ValidationError):
            require_member_attendance_date(member, "2026-03-16")
        member.deathDate = None
        require_member_attendance_date(member, "2026-12-31")

    def test_temporal_indicator_is_explanatory_and_never_resolves_ambiguity(self):
        within = temporal_match_indicator("2026-04-15", "2026-02-01", "2026-05-01")
        before = temporal_match_indicator("2026-04-15", "2027-04-20", "2027-05-01")
        after = temporal_match_indicator("2026-04-15", "2026-02-01", "2026-03-30")
        missing = temporal_match_indicator("2026-04-15", None, None)
        self.assertEqual((within.relation, within.distance_days),
                         ("WITHIN_KNOWN_RANGE", 0))
        self.assertEqual((before.relation, before.distance_days),
                         ("BEFORE_FIRST_ATTENDANCE", 370))
        self.assertEqual((after.relation, after.distance_days),
                         ("AFTER_LAST_ATTENDANCE", 16))
        self.assertEqual((missing.relation, missing.distance_days),
                         ("NO_ATTENDANCE_DATA", None))

        source = self.write("2026-07-01_BWL_Casts.csv", '"Veniell","1"\n')
        before_store = self.store.to_payload()
        plan = analyze_csv_raids_for_v2(self.store, [source])
        match = plan.ambiguous_member_matches[0]
        self.assertEqual({item.member_id for item in match.options}, {"m2", "m3"})
        self.assertIsNotNone(match.suggested_member_id)
        self.assertEqual(self.store.to_payload(), before_store)


if __name__ == "__main__":
    unittest.main()
