"""CLM attendance priority and report-to-many-CLM metadata links."""

import tempfile
import unittest
from pathlib import Path

from app.csv_v2_analysis import analyze_csv_raids_for_v2
from app.csv_v2_materialization import (
    CsvImportDecisions, CsvMemberImportChoice, CsvRaidDecision,
    materialize_csv_raid_import,
)
from app.identity_v2 import (
    Attendance, CsvRaidSource, IdentityV2Store, Member, Player, Raid,
)
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from app.identity_v2_views import IdentityV2ViewData


class CsvV2SourcePriorityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = IdentityV2Store(
            members=[
                Member("m1000", "Annî", "Priest", clmGuid="1:1"),
                Member("m1001", "Jêmma", "Mage", clmGuid="1:2"),
            ],
            raids=[
                Raid("r_aq", "2026-04-21", name="AQ20", clmRaidId="clm-aq"),
                Raid("r_ony", "2026-04-21", name="Onyxia", clmRaidId="clm-ony"),
                Raid("r_mc", "2026-04-21", name="MC", clmRaidId="clm-mc"),
            ],
            attendance=[
                Attendance("a_aq", "r_aq", "m1000", "main", clmGuid="1:1"),
                Attendance("a_ony", "r_ony", "m1001", "twink", clmGuid="1:2"),
                Attendance("a_mc", "r_mc", "m1000", "unknown", clmGuid="1:1"),
            ],
        )

    def csv(self, name="2026-04-21_AQ20_Casts.csv", names=("Annî", "Jêmma", "Neuling")):
        path = self.root / name
        path.write_text(
            '"META_RAID_TYPE","AQ20"\n'
            '"META_RAID_DATE","2026-04-21"\n'
            '"META_REPORT_URL","https://vanilla.warcraftlogs.com/reports/shared"\n'
            '"Name","Amount"\n'
            + "".join(f'"{item}","1"\n' for item in names),
            encoding="utf-8",
        )
        return path

    def test_one_report_can_link_three_clm_raids_without_csv_attendance(self):
        source = self.csv()
        plan = analyze_csv_raids_for_v2(self.store, [source])
        self.assertEqual(plan.raid_candidates[0].status, "POSSIBLE_DUPLICATE")
        self.assertEqual(set(plan.raid_candidates[0].matching_raid_ids),
                         {"r_aq", "r_ony", "r_mc"})
        before = self.store.to_payload()
        result, summary = materialize_csv_raid_import(
            self.store, plan,
            CsvImportDecisions(raid_decisions={
                source: CsvRaidDecision(
                    "LINK_CLM_RAIDS",
                    existing_raid_ids=("r_aq", "r_ony", "r_mc"),
                ),
            }),
        )
        self.assertEqual((len(result.raids), len(result.attendance), len(result.members)),
                         (3, 3, 2))
        self.assertEqual((summary.clm_metadata_reports,
                          summary.csv_names_not_attended_to_clm,
                          summary.csv_extra_names_against_clm), (1, 3, 1))
        self.assertEqual(summary.new_attendance, 0)
        self.assertEqual(summary.new_members, 0)
        self.assertEqual([item.attendanceType for item in result.attendance],
                         ["main", "twink", "unknown"])
        for raid in result.raids:
            self.assertEqual(raid.csvSourceFiles, (source.name,))
            self.assertEqual(raid.csvReportUrls,
                             ("https://vanilla.warcraftlogs.com/reports/shared",))
            self.assertEqual(raid.csvSources, (CsvRaidSource(
                source.name, "https://vanilla.warcraftlogs.com/reports/shared"),))
        self.assertEqual({row.source for row in IdentityV2ViewData.from_store(result).raids},
                         {"CLM + CSV"})
        self.assertEqual(self.store.to_payload(), before)
        target = self.root / "roundtrip.ggc"
        save_new_identity_v2(result, target)
        self.assertEqual(load_identity_v2(target).to_payload(), result.to_payload())
        again = analyze_csv_raids_for_v2(result, [source])
        self.assertEqual(again.raid_candidates[0].status, "KNOWN_RAID")
        self.assertEqual(set(again.raid_candidates[0].automatic_clm_raid_ids),
                         {"r_aq", "r_ony", "r_mc"})

    def test_unique_exact_clm_raid_auto_links_metadata_only(self):
        self.store.raids = self.store.raids[:1]
        self.store.attendance = self.store.attendance[:1]
        source = self.csv(names=("Annî", "Neuling"))
        plan = analyze_csv_raids_for_v2(self.store, [source])
        self.assertEqual(plan.raid_candidates[0].status, "KNOWN_RAID")
        self.assertEqual(plan.raid_candidates[0].automatic_clm_raid_ids, ("r_aq",))
        result, summary = materialize_csv_raid_import(
            self.store, plan, CsvImportDecisions(),
        )
        self.assertEqual((len(result.members), len(result.attendance), len(result.raids)),
                         (2, 1, 1))
        self.assertEqual(summary.csv_extra_names_against_clm, 1)
        self.assertEqual(result.raids[0].csvSourceFiles, (source.name,))

    def test_second_import_enriches_same_csv_source_with_report_url(self):
        self.store.raids = self.store.raids[:1]
        self.store.attendance = self.store.attendance[:1]
        source = self.root / "2026-04-21_AQ20_Casts.csv"
        source.write_text(
            '"META_RAID_TYPE","AQ20"\n"META_RAID_DATE","2026-04-21"\n'
            '"Name","Amount"\n"Annî","1"\n',
            encoding="utf-8",
        )
        first_plan = analyze_csv_raids_for_v2(self.store, [source])
        first, _ = materialize_csv_raid_import(
            self.store, first_plan, CsvImportDecisions(),
        )
        self.assertEqual(first.raids[0].csvSources,
                         (CsvRaidSource(source.name, None),))
        source.write_text(
            '"META_RAID_TYPE","AQ20"\n"META_RAID_DATE","2026-04-21"\n'
            '"META_REPORT_URL","https://vanilla.warcraftlogs.com/reports/second"\n'
            '"Name","Amount"\n"Annî","1"\n',
            encoding="utf-8",
        )
        second_plan = analyze_csv_raids_for_v2(first, [source])
        second, _ = materialize_csv_raid_import(
            first, second_plan, CsvImportDecisions(),
        )
        self.assertEqual(second.raids[0].csvSources, (CsvRaidSource(
            source.name, "https://vanilla.warcraftlogs.com/reports/second"),))

    def test_same_date_and_type_without_participant_overlap_requires_review(self):
        self.store.raids = self.store.raids[:1]
        self.store.attendance = self.store.attendance[:1]
        source = self.csv(names=("Neuling",))
        candidate = analyze_csv_raids_for_v2(self.store, [source]).raid_candidates[0]
        self.assertEqual(candidate.status, "POSSIBLE_DUPLICATE")
        self.assertEqual(candidate.automatic_clm_raid_ids, ())

    def test_csv_only_raid_may_create_member_without_class_or_guid(self):
        self.store.raids.clear()
        self.store.attendance.clear()
        source = self.csv(name="2026-04-21_AQ20_Casts.csv", names=("Neuling",))
        plan = analyze_csv_raids_for_v2(self.store, [source])
        self.assertEqual(plan.raid_candidates[0].status, "NEW_RAID")
        result, summary = materialize_csv_raid_import(
            self.store, plan,
            CsvImportDecisions(new_member_choices={
                "neuling": CsvMemberImportChoice(),
            }),
        )
        self.assertEqual(summary.new_members, 1)
        member = next(item for item in result.members if item.name == "Neuling")
        self.assertIsNone(member.className)
        self.assertIsNone(member.playerId)
        self.assertIsNone(member.clmGuid)
        self.assertEqual(member.raidStartDate, "2026-04-21")
        entry = result.attendance[-1]
        self.assertEqual((entry.attendanceType, entry.clmGuid, entry.playerId),
                         ("unknown", None, None))
        self.assertEqual(IdentityV2ViewData.from_store(result).raids[0].source, "CSV")

    def test_name_from_linked_report_can_be_created_by_later_csv_only_raid(self):
        linked = self.csv(names=("Annî", "Neuling"))
        later = self.root / "2026-04-22_BWL_Casts.csv"
        later.write_text(
            '"META_RAID_TYPE","BWL"\n"META_RAID_DATE","2026-04-22"\n'
            '"Name","Amount"\n"Neuling","1"\n',
            encoding="utf-8",
        )
        plan = analyze_csv_raids_for_v2(self.store, [linked, later])
        linked_candidate = next(item for item in plan.raid_candidates
                                if item.source_path == linked)
        self.assertEqual(linked_candidate.status, "POSSIBLE_DUPLICATE")
        result, summary = materialize_csv_raid_import(
            self.store, plan,
            CsvImportDecisions(
                raid_decisions={linked: CsvRaidDecision(
                    "LINK_CLM_RAIDS", existing_raid_ids=("r_aq", "r_mc"))},
                new_member_choices={"neuling": CsvMemberImportChoice()},
            ),
        )
        new_member = next(item for item in result.members if item.name == "Neuling")
        self.assertEqual(summary.new_members, 1)
        self.assertEqual(sum(item.memberId == new_member.memberId
                             for item in result.attendance), 1)
        self.assertEqual(summary.csv_names_not_attended_to_clm, 2)

    def test_irrelevant_csv_name_is_exact_persistent_and_revocable(self):
        self.store.raids.clear()
        self.store.attendance.clear()
        source = self.csv(names=("Bífi", "Bifibifi"))
        plan = analyze_csv_raids_for_v2(self.store, [source])
        result, summary = materialize_csv_raid_import(
            self.store, plan,
            CsvImportDecisions(new_member_choices={
                "bífi": CsvMemberImportChoice(relevance="irrelevant"),
                "bifibifi": CsvMemberImportChoice(),
            }),
        )
        self.assertEqual(summary.ignored_members, 1)
        self.assertEqual({item.name for item in result.members},
                         {"Annî", "Jêmma", "Bifibifi"})
        self.assertTrue(result.is_csv_character_ignored("BÍFI"))
        self.assertFalse(result.is_csv_character_ignored("Bifibifi"))
        target = self.root / "ignored.ggc"
        save_new_identity_v2(result, target)
        restored = load_identity_v2(target)
        self.assertTrue(restored.is_csv_character_ignored("Bífi"))
        second_source = self.root / "2026-04-22_BWL_Casts.csv"
        second_source.write_text(
            '"META_RAID_TYPE","BWL"\n"META_RAID_DATE","2026-04-22"\n'
            '"Name","Amount"\n"BÍFI","1"\n"Bifibifi","1"\n',
            encoding="utf-8",
        )
        repeat = analyze_csv_raids_for_v2(restored, [second_source])
        self.assertEqual(len(repeat.ignored_occurrences), 1)
        self.assertEqual(repeat.ignored_occurrences[0].name, "BÍFI")
        self.assertEqual(repeat.attendance_candidates[0].status, "IGNORED")
        restored.unignore_csv_character("Bífi")
        self.assertFalse(restored.is_csv_character_ignored("Bífi"))

    def test_inactive_and_existing_player_options_preserve_history(self):
        self.store.raids.clear()
        self.store.attendance.clear()
        self.store.players.append(Player("p1", "Spieler"))
        source = self.csv(names=("Inaktiv", "Twink", "InaktivBekannt"))
        plan = analyze_csv_raids_for_v2(self.store, [source])
        result, _summary = materialize_csv_raid_import(
            self.store, plan,
            CsvImportDecisions(new_member_choices={
                "inaktiv": CsvMemberImportChoice(activity_status="inactive"),
                "twink": CsvMemberImportChoice(player_id="p1", current_role="twink"),
                "inaktivbekannt": CsvMemberImportChoice(
                    activity_status="inactive", player_id="p1"),
            }),
        )
        inactive = next(item for item in result.members if item.name == "Inaktiv")
        twink = next(item for item in result.members if item.name == "Twink")
        inactive_known = next(item for item in result.members
                              if item.name == "InaktivBekannt")
        self.assertEqual((inactive.lifeStatus, inactive.playerId, inactive.deathDate),
                         ("inactive", None, None))
        self.assertEqual((twink.lifeStatus, twink.playerId, twink.currentRole),
                         ("active", "p1", None))
        self.assertEqual((inactive_known.lifeStatus, inactive_known.playerId,
                          inactive_known.currentRole), ("inactive", "p1", None))
        self.assertIsNone(result.players[0].mainMemberId)
        self.assertEqual({entry.memberId: (entry.playerId, entry.attendanceType)
                          for entry in result.attendance},
                         {inactive.memberId: (None, "unknown"),
                          twink.memberId: ("p1", "unknown"),
                          inactive_known.memberId: ("p1", "unknown")})
        self.assertEqual(len(result.players), 1)

    def test_player_known_requires_existing_player(self):
        self.store.raids.clear()
        self.store.attendance.clear()
        source = self.csv(names=("Twink",))
        plan = analyze_csv_raids_for_v2(self.store, [source])
        with self.assertRaisesRegex(ValueError, "existiert nicht"):
            materialize_csv_raid_import(
                self.store, plan,
                CsvImportDecisions(new_member_choices={
                    "twink": CsvMemberImportChoice(
                        player_id="p-fake", current_role="twink"),
                }),
            )


if __name__ == "__main__":
    unittest.main()
