"""Focused atomic materialization of confirmed Lua-first CSV bulk plans."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.csv_import import exact_name_key
from app.csv_v2_analysis import analyze_csv_raids_for_v2
from app.csv_v2_materialization import (
    CsvImportDecisions, CsvMemberImportChoice, CsvRaidDecision,
    CsvV2MaterializationError,
    materialize_csv_raid_import,
)
from app.identity_v2 import Attendance, IdentityV2Store, Member, Raid
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2


class CsvV2MaterializationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = IdentityV2Store(
            members=[
                Member("m1000", "Annî", "Priest", clmGuid="1:1",
                       raidStartDate="2026-08-21"),
                Member("m1001", "Veniell", "Mage", clmGuid="1:2",
                       raidStartDate="2026-08-21"),
                Member("m1002", "Veniell", "Warrior", clmGuid="1:3"),
                Member("m1003", "Jêmma", "Druid", clmGuid="1:4"),
            ],
            raids=[Raid("r_clm", "2026-08-21", name="MC", clmRaidId="clm-1")],
            attendance=[
                Attendance("a_main", "r_clm", "m1000", "main", clmGuid="1:1"),
                Attendance("a_twink", "r_clm", "m1001", "twink", clmGuid="1:2"),
            ],
            legacyClmGuidMemberMap={"1:0": "m1000"},
        )

    def write(self, filename, names, *, title=None, url=None):
        path = self.root / filename
        meta = ""
        if title:
            meta += f'"META_RAID_TYPE","{title}"\n'
        if url:
            meta += f'"META_REPORT_URL","{url}"\n'
        rows = '"Name","Amount"\n' + "".join(
            f'"{name}","1"\n' for name in names
        )
        path.write_text(meta + rows, encoding="utf-8")
        return path

    def test_new_raid_source_title_url_unknown_attendance_and_earlier_start(self):
        source = self.write("2026-07-01_ZulGurub_Casts.csv", ["Annî"],
                            title="ZulGurub", url="https://vanilla.warcraftlogs.com/reports/a")
        plan = analyze_csv_raids_for_v2(self.store, [source])
        before = self.store.to_payload()
        result, summary = materialize_csv_raid_import(
            self.store, plan, CsvImportDecisions(),
        )
        self.assertEqual((summary.new_raids, summary.new_attendance,
                          summary.raid_start_shifts), (1, 1, 1))
        raid = next(item for item in result.raids if item.raidId != "r_clm")
        self.assertEqual((raid.date, raid.raidType, raid.name, raid.clmRaidId),
                         ("2026-07-01", "ZG", "ZulGurub", None))
        self.assertEqual(raid.csvSourceFiles, (source.name,))
        self.assertEqual(raid.csvReportUrls,
                         ("https://vanilla.warcraftlogs.com/reports/a",))
        entry = next(item for item in result.attendance if item.raidId == raid.raidId)
        self.assertEqual((entry.memberId, entry.attendanceType,
                          entry.playerId, entry.clmGuid),
                         ("m1000", "unknown", None, None))
        self.assertEqual(next(item.raidStartDate for item in result.members
                              if item.memberId == "m1000"), "2026-07-01")
        self.assertEqual(result.legacyClmGuidMemberMap,
                         self.store.legacyClmGuidMemberMap)
        self.assertEqual(self.store.to_payload(), before)

        target = self.root / "temp_v2.ggc"
        save_new_identity_v2(result, target)
        self.assertEqual(load_identity_v2(target).to_payload(), result.to_payload())

    def test_known_raid_skips_existing_main_and_twink(self):
        source = self.write("2026-08-21_MC_Casts.csv", ["Annî", "Veniell-Stitches"])
        # Two Veniell incarnations remain ambiguous, so use only Annî for a known raid.
        source.write_text('"Name","Amount"\n"Annî","1"\n', encoding="utf-8")
        plan = analyze_csv_raids_for_v2(self.store, [source])
        self.assertEqual(plan.raid_candidates[0].status, "KNOWN_RAID")
        result, summary = materialize_csv_raid_import(
            self.store, plan, CsvImportDecisions(),
        )
        self.assertEqual((summary.new_raids, summary.new_attendance,
                          summary.existing_attendance_skipped), (0, 0, 1))
        self.assertEqual([(item.attendanceType, item.clmGuid)
                          for item in result.attendance],
                         [("main", "1:1"), ("twink", "1:2")])
        self.assertEqual(result.raids[0].clmRaidId, "clm-1")
        self.assertEqual(result.raids[0].name, "MC")

    def test_possible_duplicate_merge_or_separate_and_unresolved_block(self):
        self.store.raids.append(Raid("r_other", "2026-08-21", name="MC",
                                     clmRaidId="clm-2"))
        source = self.write("2026-08-21_MC_Casts.csv", ["Annî", "Jêmma"])
        plan = analyze_csv_raids_for_v2(self.store, [source])
        self.assertEqual(plan.raid_candidates[0].status, "POSSIBLE_DUPLICATE")
        before = self.store.to_payload()
        with self.assertRaises(CsvV2MaterializationError):
            materialize_csv_raid_import(self.store, plan, CsvImportDecisions())
        self.assertEqual(self.store.to_payload(), before)

        merge = CsvImportDecisions(raid_decisions={
            source: CsvRaidDecision("MERGE_EXISTING", "r_clm"),
        })
        merged, summary = materialize_csv_raid_import(self.store, plan, merge)
        self.assertEqual((summary.new_raids, summary.merged_existing_raids,
                          summary.existing_attendance_skipped,
                          summary.new_attendance), (0, 1, 1, 0))
        self.assertEqual(merged.raids[0].csvSourceFiles, (source.name,))
        self.assertEqual({(a.memberId, a.attendanceType) for a in merged.attendance},
                         {("m1000", "main"), ("m1001", "twink")})

        separate = CsvImportDecisions(raid_decisions={
            source: CsvRaidDecision("CREATE_NEW"),
        })
        created, summary = materialize_csv_raid_import(self.store, plan, separate)
        self.assertEqual((summary.new_raids, summary.separate_duplicate_raids), (1, 1))
        self.assertEqual(len(created.raids), 3)
        self.assertEqual(len(created.attendance), 4)
        self.assertEqual(self.store.to_payload(), before)

    def test_ambiguous_choices_are_per_file_and_same_name_members_can_share_raid(self):
        first = self.write("2026-07-01_BWL_Casts.csv", ["Veniell"])
        second = self.write("2026-07-02_BWL_Casts.csv", ["Veniell"])
        plan = analyze_csv_raids_for_v2(self.store, [first, second])
        choices = CsvImportDecisions(member_selections={
            (first, exact_name_key("Veniell")): "m1001",
            (second, exact_name_key("Veniell")): "m1002",
        })
        result, _summary = materialize_csv_raid_import(self.store, plan, choices)
        by_date = {raid.date: raid.raidId for raid in result.raids}
        self.assertEqual({a.memberId for a in result.attendance
                          if a.raidId == by_date["2026-07-01"]}, {"m1001"})
        self.assertEqual({a.memberId for a in result.attendance
                          if a.raidId == by_date["2026-07-02"]}, {"m1002"})

    def test_two_reports_link_one_clm_raid_without_csv_attendance(self):
        self.store.raids.append(Raid("r_bwl", "2026-07-01", name="BWL",
                                     clmRaidId="clm-bwl"))
        self.store.raids.append(Raid("r_other_bwl", "2026-07-01", name="BWL",
                                     clmRaidId="clm-other-bwl"))
        first = self.write("2026-07-01_BWL_Casts.csv", ["Veniell"],
                           url="https://vanilla.warcraftlogs.com/reports/one")
        second = self.root / "zweiter_report.csv"
        second.write_text(
            '"META_RAID_DATE","2026-07-01"\n'
            '"META_RAID_TYPE","BWL"\n'
            '"META_REPORT_URL","https://vanilla.warcraftlogs.com/reports/two"\n'
            '"Name","Amount"\n"Veniell","1"\n', encoding="utf-8",
        )
        plan = analyze_csv_raids_for_v2(self.store, [first, second])
        decisions = CsvImportDecisions(
            raid_decisions={
                first: CsvRaidDecision("LINK_CLM_RAIDS",
                                       existing_raid_ids=("r_bwl",)),
                second: CsvRaidDecision("LINK_CLM_RAIDS",
                                        existing_raid_ids=("r_bwl",)),
            },
            member_selections={
                (first, exact_name_key("Veniell")): "m1001",
                (second, exact_name_key("Veniell")): "m1002",
            },
        )
        result, _summary = materialize_csv_raid_import(self.store, plan, decisions)
        self.assertEqual(sum(item.raidId == "r_bwl" for item in result.attendance), 0)
        raid = next(item for item in result.raids if item.raidId == "r_bwl")
        self.assertEqual(set(raid.csvSourceFiles), {first.name, second.name})
        self.assertEqual(set(raid.csvReportUrls), {
            "https://vanilla.warcraftlogs.com/reports/one",
            "https://vanilla.warcraftlogs.com/reports/two",
        })

    def test_new_member_requires_classification_but_class_is_optional(self):
        source = self.write("2026-07-01_BWL_Casts.csv", ["Neu"])
        plan = analyze_csv_raids_for_v2(self.store, [source])
        before = self.store.to_payload()
        with self.assertRaisesRegex(CsvV2MaterializationError, "Importklassifikation"):
            materialize_csv_raid_import(self.store, plan, CsvImportDecisions())
        result_unknown_class, summary_unknown_class = materialize_csv_raid_import(
            self.store, plan, CsvImportDecisions(create_new_members=True))
        self.assertEqual(summary_unknown_class.new_members, 1)
        unknown_class_member = next(item for item in result_unknown_class.members
                                    if item.name == "Neu")
        self.assertIsNone(unknown_class_member.className)
        result, summary = materialize_csv_raid_import(self.store, plan,
                                                       CsvImportDecisions(create_new_members=True,
                                                                          new_member_classes={"neu": "Mage"}))
        self.assertEqual(summary.new_members, 1)
        member = next(item for item in result.members if item.name == "Neu")
        self.assertEqual((member.memberId, member.className, member.playerId,
                          member.clmGuid, member.raidStartDate),
                         ("m1004", "Mage", None, None, "2026-07-01"))
        self.assertEqual(result.attendance[-1].memberId, member.memberId)
        self.assertEqual(result.players, [])
        self.assertEqual(self.store.to_payload(), before)

    def test_later_attendance_does_not_move_start_backwards(self):
        source = self.write("2026-09-01_BWL_Casts.csv", ["Annî"])
        plan = analyze_csv_raids_for_v2(self.store, [source])
        result, summary = materialize_csv_raid_import(
            self.store, plan, CsvImportDecisions(),
        )
        self.assertEqual(summary.raid_start_shifts, 0)
        self.assertEqual(next(item.raidStartDate for item in result.members
                              if item.memberId == "m1000"), "2026-08-21")

    def test_death_day_is_allowed_and_invalid_member_choice_is_rejected(self):
        self.store.members[3].deathDate = "2026-07-01"
        source = self.write("2026-07-01_BWL_Casts.csv", ["Jêmma"])
        plan = analyze_csv_raids_for_v2(self.store, [source])
        result, _summary = materialize_csv_raid_import(
            self.store, plan, CsvImportDecisions(),
        )
        self.assertEqual(result.attendance[-1].memberId, "m1003")

        ambiguous_source = self.write("2026-07-02_BWL_Casts.csv", ["Veniell"])
        ambiguous_plan = analyze_csv_raids_for_v2(self.store, [ambiguous_source])
        with self.assertRaisesRegex(CsvV2MaterializationError, "nicht zulässig"):
            materialize_csv_raid_import(self.store, ambiguous_plan,
                CsvImportDecisions(member_selections={
                    (ambiguous_source, exact_name_key("Veniell")): "m9999",
                }))

    def test_death_date_rechecked_in_materializer_and_existing_conflict_blocks(self):
        source = self.write("2026-07-01_BWL_Casts.csv", ["Annî"])
        plan = analyze_csv_raids_for_v2(self.store, [source])
        self.store.members[0].deathDate = "2026-06-30"
        with self.assertRaises(CsvV2MaterializationError):
            materialize_csv_raid_import(self.store, plan, CsvImportDecisions())
        self.store.members[0].deathDate = None
        self.store.members[0].deathDate = "2026-08-20"
        existing_plan = analyze_csv_raids_for_v2(self.store, [source])
        with self.assertRaisesRegex(CsvV2MaterializationError, "bestehende"):
            materialize_csv_raid_import(self.store, existing_plan,
                                        CsvImportDecisions())
        self.assertEqual(len(self.store.attendance), 2)

    def test_failure_after_partial_copy_leaves_original_unchanged(self):
        source = self.write("2026-07-01_BWL_Casts.csv", ["Annî", "Jêmma"])
        plan = analyze_csv_raids_for_v2(self.store, [source])
        before = self.store.to_payload()
        with patch("app.csv_v2_materialization.new_v2_attendance_id",
                   return_value="same_id"):
            with self.assertRaises(ValueError):
                materialize_csv_raid_import(self.store, plan, CsvImportDecisions())
        self.assertEqual(self.store.to_payload(), before)

    def test_disabled_raid_has_no_import_effect_or_unique_member_blocker(self):
        active = self.write("2026-07-01_BWL_Casts.csv", ["Annî"])
        excluded = self.write("2026-07-02_BWL_Casts.csv", ["NurAbgewählt", "Jêmma"])
        linked = self.write("2026-08-21_MC_Casts.csv", ["Annî"])
        self.store.members[3].deathDate = "2026-07-01"
        plan = analyze_csv_raids_for_v2(self.store, [active, excluded, linked])
        self.assertEqual(len(plan.raid_candidates), 3)
        self.assertTrue(any(item.source_path == excluded
                            for item in plan.blocked_member_matches))
        before = self.store.to_payload()
        excluded.write_text("Beschädigte, abgewählte CSV", encoding="utf-8")
        result, summary = materialize_csv_raid_import(
            self.store, plan, CsvImportDecisions(
                active_raid_paths=frozenset({active}),
                new_member_choices={"nurabgewählt": CsvMemberImportChoice()},
            ),
        )
        self.assertEqual((summary.new_raids, summary.new_attendance,
                          summary.new_members), (1, 1, 0))
        self.assertEqual(len(result.raids), len(self.store.raids) + 1)
        self.assertFalse(any(item.name == "NurAbgewählt" for item in result.members))
        self.assertFalse(any(excluded.name in raid.csvSourceFiles for raid in result.raids))
        self.assertEqual(result.raids[0].csvSourceFiles, ())
        self.assertEqual(result.raids[0].csvReportUrls, ())
        self.assertEqual(self.store.to_payload(), before)
        none, empty_summary = materialize_csv_raid_import(
            self.store, plan,
            CsvImportDecisions(active_raid_paths=frozenset()),
        )
        self.assertEqual(none.to_payload(), before)
        self.assertEqual(empty_summary.new_raids, 0)

    def test_type_override_rechecks_clm_match_and_changes_new_raid_type(self):
        source = self.write("2026-08-21_MC_Casts.csv", ["Annî"])
        original_csv = source.read_bytes()
        plan = analyze_csv_raids_for_v2(self.store, [source])
        self.assertEqual(plan.raid_candidates[0].status, "KNOWN_RAID")
        changed_analysis = analyze_csv_raids_for_v2(
            self.store, [source], raid_type_overrides={source: "BWL"})
        self.assertEqual(changed_analysis.raid_candidates[0].status,
                         "POSSIBLE_DUPLICATE")
        self.assertEqual(changed_analysis.raid_candidates[0].automatic_clm_raid_ids, ())
        with self.assertRaises(CsvV2MaterializationError):
            materialize_csv_raid_import(
                self.store, plan,
                CsvImportDecisions(raid_type_overrides={source: "BWL"}),
            )
        result, summary = materialize_csv_raid_import(
            self.store, plan, CsvImportDecisions(
                raid_type_overrides={source: "BWL"},
                raid_decisions={source: CsvRaidDecision("CREATE_NEW")},
            ),
        )
        self.assertEqual(summary.new_raids, 1)
        self.assertEqual(result.raids[0].raidType, self.store.raids[0].raidType)
        imported = next(raid for raid in result.raids if raid.raidId != "r_clm")
        self.assertEqual(imported.raidType, "BWL")
        self.assertEqual(imported.name, "BWL")
        self.assertEqual(self.store.raids[0].csvSourceFiles, ())
        self.assertEqual(source.read_bytes(), original_csv)

    def test_active_csv_change_invalidates_review(self):
        source = self.write("2026-07-01_BWL_Casts.csv", ["Annî"])
        plan = analyze_csv_raids_for_v2(self.store, [source])
        source.write_text('"Name","Amount"\n"Annî","1"\n"Jêmma","1"\n',
                          encoding="utf-8")
        with self.assertRaisesRegex(CsvV2MaterializationError,
                                    "Aktive CSV-Quelle hat sich"):
            materialize_csv_raid_import(self.store, plan, CsvImportDecisions())

    def test_csv_only_reimport_by_url_or_source_adds_only_missing_attendance(self):
        source = self.write("2026-07-01_BWL_Casts.csv", ["Annî"],
                            url="https://vanilla.warcraftlogs.com/reports/reimport")
        first_plan = analyze_csv_raids_for_v2(self.store, [source])
        first, first_summary = materialize_csv_raid_import(
            self.store, first_plan, CsvImportDecisions())
        self.assertEqual(first_summary.new_raids, 1)
        csv_raid = next(raid for raid in first.raids if not raid.clmRaidId)
        again_plan = analyze_csv_raids_for_v2(first, [source])
        self.assertEqual(again_plan.raid_candidates[0].automatic_csv_raid_id,
                         csv_raid.raidId)
        again, again_summary = materialize_csv_raid_import(
            first, again_plan, CsvImportDecisions())
        self.assertEqual((again_summary.new_raids, again_summary.new_attendance), (0, 0))
        self.assertEqual(len(again.raids), len(first.raids))
        self.assertEqual(len(again.attendance), len(first.attendance))
        self.assertEqual(again.raids[-1].csvSourceFiles, (source.name,))

        source.write_text(
            '"META_REPORT_URL","https://vanilla.warcraftlogs.com/reports/reimport"\n'
            '"Name","Amount"\n"Annî","1"\n"Jêmma","1"\n',
            encoding="utf-8",
        )
        extra_plan = analyze_csv_raids_for_v2(again, [source])
        self.assertEqual(extra_plan.raid_candidates[0].automatic_csv_raid_id,
                         csv_raid.raidId)
        expanded, summary = materialize_csv_raid_import(
            again, extra_plan, CsvImportDecisions())
        self.assertEqual((summary.new_raids, summary.new_attendance), (0, 1))
        self.assertEqual(len(expanded.raids), len(first.raids))
        self.assertEqual({item.memberId for item in expanded.attendance
                          if item.raidId == csv_raid.raidId}, {"m1000", "m1003"})

        source.write_text(
            '"META_REPORT_URL","https://vanilla.warcraftlogs.com/reports/reimport"\n'
            '"Name","Amount"\n"Annî","1"\n"Jêmma","1"\n"Neu","1"\n',
            encoding="utf-8",
        )
        new_member_plan = analyze_csv_raids_for_v2(expanded, [source])
        with_member, member_summary = materialize_csv_raid_import(
            expanded, new_member_plan,
            CsvImportDecisions(new_member_choices={"neu": CsvMemberImportChoice()}),
        )
        self.assertEqual((member_summary.new_raids, member_summary.new_members,
                          member_summary.new_attendance), (0, 1, 1))
        self.assertEqual(len(with_member.raids), len(first.raids))
        self.assertTrue(any(item.name == "Neu" for item in with_member.members))

        no_url = self.write("2026-07-02_BWL_Casts.csv", ["Annî"])
        no_url_first, _ = materialize_csv_raid_import(
            with_member, analyze_csv_raids_for_v2(with_member, [no_url]),
            CsvImportDecisions())
        fallback = analyze_csv_raids_for_v2(no_url_first, [no_url])
        self.assertIsNotNone(fallback.raid_candidates[0].automatic_csv_raid_id)
        no_url_again, fallback_summary = materialize_csv_raid_import(
            no_url_first, fallback, CsvImportDecisions())
        self.assertEqual(fallback_summary.new_raids, 0)
        self.assertEqual(len(no_url_again.raids), len(no_url_first.raids))

    def test_report_url_recognizes_renamed_csv_and_possible_match_can_merge(self):
        first = self.write("2026-07-01_BWL_Casts.csv", ["Annî"],
                           url="https://vanilla.warcraftlogs.com/reports/shared")
        original, _ = materialize_csv_raid_import(
            self.store, analyze_csv_raids_for_v2(self.store, [first]),
            CsvImportDecisions())
        csv_raid = next(item for item in original.raids if not item.clmRaidId)
        renamed = self.root / "renamed.csv"
        renamed.write_text(
            '"META_RAID_DATE","2026-07-01"\n'
            '"META_RAID_TYPE","BWL"\n'
            '"META_REPORT_URL","https://vanilla.warcraftlogs.com/reports/shared"\n'
            '"Name","Amount"\n"Jêmma","1"\n', encoding="utf-8")
        recognized = analyze_csv_raids_for_v2(original, [renamed])
        self.assertEqual(recognized.raid_candidates[0].automatic_csv_raid_id,
                         csv_raid.raidId)
        linked, summary = materialize_csv_raid_import(
            original, recognized, CsvImportDecisions())
        self.assertEqual((summary.new_raids, summary.new_attendance), (0, 1))
        self.assertEqual({item.memberId for item in linked.attendance
                          if item.raidId == csv_raid.raidId}, {"m1000", "m1003"})
        self.assertEqual(set(linked.raids[-1].csvSourceFiles),
                         {first.name, renamed.name})

        different = self.root / "other.csv"
        different.write_text(
            '"META_RAID_DATE","2026-07-01"\n'
            '"META_RAID_TYPE","BWL"\n'
            '"META_REPORT_URL","https://vanilla.warcraftlogs.com/reports/other"\n'
            '"Name","Amount"\n"Annî","1"\n', encoding="utf-8")
        possible = analyze_csv_raids_for_v2(linked, [different])
        self.assertEqual(possible.raid_candidates[0].status, "POSSIBLE_DUPLICATE")
        self.assertIsNone(possible.raid_candidates[0].automatic_csv_raid_id)
        merged, summary = materialize_csv_raid_import(
            linked, possible, CsvImportDecisions(raid_decisions={
                different: CsvRaidDecision("MERGE_EXISTING", csv_raid.raidId),
            }),
        )
        self.assertEqual((summary.new_raids, summary.new_attendance), (0, 0))
        self.assertEqual(len(merged.raids), len(linked.raids))
        self.assertIn(different.name, merged.raids[-1].csvSourceFiles)

    def test_type_override_updates_safely_recognized_csv_only_target(self):
        source = self.write("2026-07-01_MC_Casts.csv", ["Annî"],
                            url="https://vanilla.warcraftlogs.com/reports/typed")
        first, _ = materialize_csv_raid_import(
            self.store, analyze_csv_raids_for_v2(self.store, [source]),
            CsvImportDecisions())
        csv_raid = next(item for item in first.raids if not item.clmRaidId)
        plan = analyze_csv_raids_for_v2(first, [source])
        changed, summary = materialize_csv_raid_import(
            first, plan, CsvImportDecisions(raid_type_overrides={source: "BWL"}),
        )
        self.assertEqual(summary.new_raids, 0)
        self.assertEqual(len(changed.raids), len(first.raids))
        self.assertEqual(next(item.raidType for item in changed.raids
                              if item.raidId == csv_raid.raidId), "BWL")

    def test_same_report_url_on_clm_and_csv_only_requires_review(self):
        url = "https://vanilla.warcraftlogs.com/reports/sharedmixed"
        self.store.raids[0].csvReportUrls = (url,)
        self.store.raids.append(Raid(
            "r_csv", "2026-08-21", "MC", "MC", csvSourceFiles=("old.csv",),
            csvReportUrls=(url,)))
        source = self.write("2026-08-21_MC_Casts.csv", ["Annî"], url=url)
        candidate = analyze_csv_raids_for_v2(self.store, [source]).raid_candidates[0]
        self.assertEqual(candidate.status, "POSSIBLE_DUPLICATE")
        self.assertEqual(candidate.automatic_clm_raid_ids, ())
        self.assertIsNone(candidate.automatic_csv_raid_id)


if __name__ == "__main__":
    unittest.main()
