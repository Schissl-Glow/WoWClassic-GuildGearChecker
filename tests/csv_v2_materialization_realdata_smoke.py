"""Optional end-to-end CSV materialization on temporary copies with TESTONLY choices."""

import shutil
import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path

from app.csv_import import exact_name_key
from app.csv_v2_analysis import analyze_csv_raids_for_v2
from app.csv_v2_materialization import (
    CsvImportDecisions, CsvMemberImportChoice, CsvRaidDecision,
    materialize_csv_raid_import,
)
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2


class CsvV2MaterializationRealDataSmoke(unittest.TestCase):
    def test_all_csvs_on_temporary_copies_with_testonly_decisions(self):
        save = Path.home() / "Desktop" / "Neuer Ordner" / "BS_Neu.ggc"
        folder = Path.home() / "Downloads" / "WarcraftLogs_Casts" / "Bierstube"
        sources = sorted(folder.glob("*_Casts.csv")) if folder.is_dir() else []
        if not save.is_file() or not sources:
            self.skipTest("Der optionale V2-Save oder die Casts-CSVs fehlen lokal.")
        save_before = save.read_bytes()
        source_before = {path: path.read_bytes() for path in sources}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_save = root / "BS_Neu.ggc"
            shutil.copy2(save, copy_save)
            copied_sources = []
            for source in sources:
                target = root / source.name
                shutil.copy2(source, target)
                copied_sources.append(target)
            store = load_identity_v2(copy_save)
            before_payload = store.to_payload()
            before_roles = Counter(item.attendanceType for item in store.attendance)
            plan = analyze_csv_raids_for_v2(store, copied_sources)

            # TESTONLY: deterministic choices exercise the complete path. None of
            # these choices is a product default or a saved identity decision.
            raid_decisions = {}
            multi_report_count = 0
            for index, raid in enumerate(plan.possible_duplicates):
                clm_options = [item for item in raid.existing_raid_options
                               if item.clm_raid_id]
                if index < 3:
                    # TESTONLY: exercise explicit separation on a few duplicates.
                    raid_decisions[raid.source_path] = CsvRaidDecision("CREATE_NEW")
                elif len(clm_options) > 1 and multi_report_count < 3:
                    raid_decisions[raid.source_path] = CsvRaidDecision(
                        "LINK_CLM_RAIDS",
                        existing_raid_ids=tuple(item.raid_id for item in clm_options),
                    )
                    multi_report_count += 1
                elif clm_options:
                    best = max(clm_options,
                               key=lambda item: (item.overlap_count, item.raid_id))
                    raid_decisions[raid.source_path] = CsvRaidDecision(
                        "LINK_CLM_RAIDS", existing_raid_ids=(best.raid_id,),
                    )
                else:
                    raid_decisions[raid.source_path] = CsvRaidDecision("CREATE_NEW")
            csv_only_paths = {
                candidate.source_path for candidate in plan.raid_candidates
                if candidate.status == "NEW_RAID"
                or (candidate.status == "POSSIBLE_DUPLICATE"
                    and raid_decisions[candidate.source_path].action == "CREATE_NEW")
            }
            active_new = [
                item for item in plan.new_member_candidates
                if any(source in csv_only_paths for source in item.source_paths)
            ]
            ignored_testonly = active_new[:2]
            used_by_source = defaultdict(set)
            for item in plan.resolved_member_matches:
                used_by_source[item.source_path].add(item.member_id)
            member_selections = {}
            for item in plan.ambiguous_member_matches:
                available = [option.member_id for option in item.options
                             if option.member_id not in used_by_source[item.source_path]]
                member_id = (available or [option.member_id for option in item.options])[0]
                member_selections[(item.source_path, exact_name_key(item.csv_name))] = member_id
                used_by_source[item.source_path].add(member_id)
            decisions = CsvImportDecisions(
                raid_decisions=raid_decisions,
                member_selections=member_selections,
                new_member_choices={
                    exact_name_key(item.name):
                    CsvMemberImportChoice(relevance="irrelevant")
                    for item in ignored_testonly
                },
                create_new_members=bool(active_new),
            )
            result, summary = materialize_csv_raid_import(store, plan, decisions)
            self.assertEqual(store.to_payload(), before_payload)
            self.assertEqual(len(result.raids), len(store.raids) + summary.new_raids)
            self.assertEqual(len(result.attendance),
                             len(store.attendance) + summary.new_attendance)
            self.assertEqual(len(result.members), len(store.members) + summary.new_members)
            new_member_ids = {item.memberId for item in result.members} - {
                item.memberId for item in store.members
            }
            unknown_class_count = sum(
                item.className is None for item in result.members
                if item.memberId in new_member_ids
            )
            self.assertEqual(result.players, store.players)
            after_roles = Counter(item.attendanceType for item in result.attendance)
            self.assertEqual(after_roles["main"], before_roles["main"])
            self.assertEqual(after_roles["twink"], before_roles["twink"])
            self.assertEqual(after_roles["unknown"],
                             before_roles["unknown"] + summary.new_attendance)
            target = root / "materialized_v2.ggc"
            save_new_identity_v2(result, target)
            self.assertEqual(load_identity_v2(target).to_payload(), result.to_payload())
            print("REALDATA_3B", {
                "starting_raids": len(store.raids),
                "plan_new_raids": sum(item.status == "NEW_RAID"
                                      for item in plan.raid_candidates),
                "clm_bracket_matches": len(plan.clm_bracket_matches),
                "testonly_multi_clm_reports": multi_report_count,
                "clm_metadata_reports": summary.clm_metadata_reports,
                "merged_existing_raids": summary.merged_existing_raids,
                "separate_duplicate_raids": summary.separate_duplicate_raids,
                "total_raids": len(result.raids),
                "starting_attendance": len(store.attendance),
                "new_attendance": summary.new_attendance,
                "existing_skipped": summary.existing_attendance_skipped,
                "new_members": summary.new_members,
                "new_members_class_unknown": unknown_class_count,
                "testonly_ignored_csv_names": summary.ignored_members,
                "csv_names_not_attended_to_clm": summary.csv_names_not_attended_to_clm,
                "csv_extra_names_against_clm": summary.csv_extra_names_against_clm,
                "remaining_blockers": 0,
                "raid_start_shifts": summary.raid_start_shifts,
                "death_conflicts": summary.death_conflicts,
                "roles_before": dict(before_roles),
                "roles_after": dict(after_roles),
            })
        self.assertEqual(save.read_bytes(), save_before)
        self.assertEqual({path: path.read_bytes() for path in sources}, source_before)


if __name__ == "__main__":
    unittest.main()
