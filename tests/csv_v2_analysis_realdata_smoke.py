"""Optional read-only bulk analysis of the explicitly supplied V2 save and Casts CSVs."""

import unittest
from collections import Counter
from pathlib import Path

from app.csv_v2_analysis import analyze_csv_raids_for_v2
from app.identity_v2_storage import load_identity_v2


class CsvV2AnalysisRealDataSmoke(unittest.TestCase):
    def test_all_supplied_casts_csvs_without_changing_sources(self):
        save = Path.home() / "Desktop" / "Neuer Ordner" / "BS_Neu.ggc"
        folder = Path.home() / "Downloads" / "WarcraftLogs_Casts" / "Bierstube"
        files = sorted(folder.glob("*_Casts.csv")) if folder.is_dir() else []
        if not save.is_file() or not files:
            self.skipTest("Der optionale V2-Save oder die Casts-CSVs fehlen lokal.")
        save_before = save.read_bytes()
        source_before = {path: path.read_bytes() for path in files}
        store = load_identity_v2(save)
        store_before = store.to_payload()
        plan = analyze_csv_raids_for_v2(store, files)
        statuses = Counter(raid.status for raid in plan.raid_candidates)
        self.assertEqual(len(plan.raid_candidates), len(files))
        self.assertEqual(sum(statuses.values()), len(files))
        self.assertEqual(len(plan.attendance_candidates),
                         sum(len(raid.participant_names) for raid in plan.raid_candidates))
        self.assertEqual(store.to_payload(), store_before)
        self.assertEqual(save.read_bytes(), save_before)
        self.assertEqual({path: path.read_bytes() for path in files}, source_before)
        print("REALDATA", {
            "files": len(files), "raids": len(plan.raid_candidates),
            "new": statuses["NEW_RAID"], "known": statuses["KNOWN_RAID"],
            "possible_duplicates": statuses["POSSIBLE_DUPLICATE"],
            "participants": len(plan.attendance_candidates),
            "resolved": len(plan.resolved_member_matches),
            "clm_bracket_matches": len(plan.clm_bracket_matches),
            "ambiguous": len(plan.ambiguous_member_matches),
            "blocked_after_death": len(plan.blocked_member_matches),
            "existing_death_conflicts": len(plan.existing_death_conflicts),
            "new_names": len(plan.new_member_candidates),
            "class_blockers": sum(bool(item.blocker)
                                  for item in plan.new_member_candidates),
            "existing_attendance": sum(item.existing_attendance
                                       for item in plan.attendance_candidates),
            "additional_candidates": sum(not item.existing_attendance
                                         for item in plan.attendance_candidates),
            "earlier_raid_start": sum(item.earlier_raid_start
                                      for item in plan.attendance_candidates),
        })


if __name__ == "__main__":
    unittest.main()
