"""Focused tests for read-only CLM Identity V2 analysis."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.clm_identity_v2_analysis import (
    analyze_clm_file, analyze_clm_ledger, canonical_clm_class, display_date,
)
from app.identity_v2 import IdentityV2Store, Member
from app.identity_v2_storage import save_identity_v2


class ClmIdentityV2AnalysisTests(unittest.TestCase):
    ROSTER = "roster-1"

    def ledger(self, profiles, extra=()):
        events = [self.event(1, "R0", r=self.ROSTER, n="Bierstube", p=0), *extra]
        for guid in profiles:
            first_p0 = min(
                (entry["_c"] for entry in extra
                 if entry["_d"] == "P0" and entry.get("g") == list(guid)),
                default=1,
            )
            events.append(self.event(first_p0 + 1, "R9", r=self.ROSTER, p=[list(guid)]))
        return events

    @staticmethod
    def event(timestamp, opcode, **fields):
        return {
            "_c": timestamp, "_b": 0, "_e": 1, "_a": timestamp,
            "_d": opcode, **fields,
        }

    def analyze(self, profiles, extra):
        return analyze_clm_ledger(self.ledger(profiles, extra), self.ROSTER)

    def test_p0_reads_name_guid_and_class(self):
        result = self.analyze([(1, 101)], [
            self.event(100, "P0", g=[1, 101], n="Annî-Stitches", c=5),
        ])
        history = result.guid_histories[0]
        self.assertEqual(history.guid, "1:101")
        self.assertEqual(history.original_name, "Annî-Stitches")
        self.assertEqual(history.normalized_name, "Annî")
        self.assertEqual(history.p0_class_value, 5)
        self.assertEqual(history.character_class, "Priest")

    def test_realm_suffix_and_accents_are_preserved_without_fuzzy_matching(self):
        result = self.analyze([(1, 101), (1, 102), (1, 103), (1, 104)], [
            self.event(100, "P0", g=[1, 101], n="Annî-Stitches", c=5),
            self.event(110, "P0", g=[1, 102], n="Anni-Stitches", c=5),
            self.event(120, "P0", g=[1, 103], n="Jêmma-Stitches", c=5),
            self.event(130, "P0", g=[1, 104], n="Jêmmâ-Stitches", c=5),
        ])
        self.assertEqual({history.normalized_name for history in result.guid_histories},
                         {"Annî", "Anni", "Jêmma", "Jêmmâ"})
        self.assertEqual(result.summary["multiGuidNames"], 0)

    def test_file_analysis_selects_only_bierstube_database(self):
        lua = '''CLM2_DB = {
            ["exp0 alliance stitches bierstube"] = { ledger = {
                { _a=1, _b=0, _c=100, _d="R0", _e=1, r=123, n="Bierstube", p=0 },
                { _a=2, _b=0, _c=200, _d="P0", _e=1, g={1,101}, n="Annî-Stitches", c=5 },
                { _a=3, _b=0, _c=201, _d="R9", _e=1, r=123, p={{1,101}} },
            } },
            ["exp0 alliance stitches triumph"] = { ledger = {
                { _a=4, _b=0, _c=100, _d="R0", _e=1, r=456, n="Triumph", p=0 },
                { _a=5, _b=0, _c=200, _d="P0", _e=1, g={1,999}, n="Fremd-Stitches", c=8 },
                { _a=6, _b=0, _c=201, _d="R9", _e=1, r=456, p={{1,999}} },
            } },
        }'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ClassicLootManager.lua"
            source.write_text(lua, encoding="utf-8")
            analysis = analyze_clm_file(source)
        self.assertEqual(analysis.database_id, "exp0 alliance stitches bierstube")
        self.assertEqual(analysis.roster_id, "123")
        self.assertEqual([item.guid for item in analysis.guid_histories], ["1:101"])

    def test_report_date_uses_german_day_month_year(self):
        timestamp = int(datetime(2025, 1, 31, 12, tzinfo=timezone.utc).timestamp())
        self.assertEqual(display_date(timestamp), "31.01.2025")

    def test_all_known_class_ids_map_to_canonical_ggc_names(self):
        expected = {
            1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest",
            7: "Shaman", 8: "Mage", 9: "Warlock", 11: "Druid",
        }
        self.assertEqual({key: canonical_clm_class(key) for key in expected}, expected)

    def test_first_and_last_seen_include_other_guid_ledger_events(self):
        result = self.analyze([(1, 101)], [
            self.event(70, "DM", r=self.ROSTER, p=[[1, 101]], v=2, t="Bonus", n=False),
            self.event(100, "P0", g=[1, 101], n="Annî-Stitches", c=5),
            self.event(150, "P1", g=[1, 101]),
        ])
        history = result.guid_histories[0]
        self.assertEqual((history.first_seen, history.last_seen), (70, 150))
        self.assertEqual(history.eternal_dkp_total, 2)

    def test_p0_then_p1_is_historical_without_death_inference(self):
        result = self.analyze([(1, 101)], [
            self.event(100, "P0", g=[1, 101], n="Annî-Stitches", c=5),
            self.event(150, "P1", g=[1, 101]),
        ])
        history = result.guid_histories[0]
        self.assertFalse(history.active_at_end)
        self.assertEqual((history.p0_count, history.p1_count), (1, 1))
        self.assertFalse(hasattr(history, "life_status"))

    def test_later_p0_reactivates_same_technical_guid(self):
        result = self.analyze([(1, 101)], [
            self.event(100, "P0", g=[1, 101], n="Annî-Stitches", c=5),
            self.event(150, "P1", g=[1, 101]),
            self.event(200, "P0", g=[1, 101], n="Annî-Stitches", c=5),
        ])
        self.assertTrue(result.guid_histories[0].active_at_end)
        self.assertEqual((result.guid_histories[0].p0_count, result.guid_histories[0].p1_count), (2, 1))
        self.assertEqual(result.summary["guids"], 1)

    def test_separated_same_name_and_class_proposes_continuation(self):
        result = self.analyze([(1, 101), (1, 102)], [
            self.event(100, "P0", g=[1, 101], n="Annî-Stitches", c=5),
            self.event(200, "P1", g=[1, 101]),
            self.event(300, "P0", g=[1, 102], n="Annî-Stitches", c=5),
        ])
        group = result.group_for_name("Annî")
        self.assertEqual(group.chronological_order, ("1:101", "1:102"))
        self.assertEqual(len(group.continuation_suggestions), 1)
        self.assertAlmostEqual(group.continuation_suggestions[0].gap_days, 100 / 86400)

    def test_different_known_classes_block_continuation(self):
        result = self.analyze([(1, 101), (1, 102)], [
            self.event(100, "P0", g=[1, 101], n="Bämäräng-Stitches", c=5),
            self.event(200, "P1", g=[1, 101]),
            self.event(300, "P0", g=[1, 102], n="Bämäräng-Stitches", c=8),
        ])
        group = result.group_for_name("Bämäräng")
        self.assertIn("CLASS_CONFLICT", group.conflicts)
        self.assertFalse(group.continuation_suggestions)

    def test_time_overlap_blocks_continuation(self):
        result = self.analyze([(1, 101), (1, 102)], [
            self.event(100, "P0", g=[1, 101], n="Annî-Stitches", c=5),
            self.event(300, "P1", g=[1, 101]),
            self.event(200, "P0", g=[1, 102], n="Annî-Stitches", c=5),
            self.event(400, "P1", g=[1, 102]),
        ])
        group = result.group_for_name("Annî")
        self.assertIn("TIME_OVERLAP", group.conflicts)
        self.assertFalse(group.continuation_suggestions)
        self.assertAlmostEqual(group.pairwise[0].overlap_days, 100 / 86400)

    def test_three_guids_allow_partial_chain_and_separate_class_conflict(self):
        result = self.analyze([(1, 101), (1, 102), (1, 103)], [
            self.event(100, "P0", g=[1, 101], n="Annî-Stitches", c=5),
            self.event(200, "P1", g=[1, 101]),
            self.event(300, "P0", g=[1, 102], n="Annî-Stitches", c=5),
            self.event(400, "P1", g=[1, 102]),
            self.event(500, "P0", g=[1, 103], n="Annî-Stitches", c=8),
        ])
        group = result.group_for_name("Annî")
        self.assertEqual(group.chronological_order, ("1:101", "1:102", "1:103"))
        self.assertEqual([(item.older_guid, item.newer_guid)
                          for item in group.continuation_suggestions], [("1:101", "1:102")])
        self.assertIn("CLASS_CONFLICT", group.conflicts)

    def test_conflicting_p0_class_for_same_guid_is_not_overwritten(self):
        result = self.analyze([(1, 101)], [
            self.event(100, "P0", g=[1, 101], n="Annî-Stitches", c=5),
            self.event(200, "P0", g=[1, 101], n="Annî-Stitches", c=8),
        ])
        history = result.guid_histories[0]
        self.assertEqual(history.character_class, "Priest")
        self.assertIn("DATA_CONFLICT", history.warnings)
        self.assertIn("P0_CLASS_CONFLICT:Priest/Mage", history.warnings)
        self.assertEqual((history.p0_count, result.summary["guids"]), (2, 1))

    def test_incomplete_p0_does_not_override_valid_identity_or_raw_dkp(self):
        result = self.analyze([(1, 101)], [
            self.event(100, "P0", g=[1, 101], n="Ânní-Stitches", c=5),
            self.event(120, "DM", r=self.ROSTER, p=[[1, 101]], v=10, t="Bonus", n=False),
            self.event(150, "P0", g=[1, 101], n="Unbekannt-Stitches", c="", s=[1, 0]),
            self.event(151, "P0", g=[1, 101], n="Ânní-Stitches", c=5),
        ])
        history = result.guid_histories[0]
        self.assertEqual((history.normalized_name, history.character_class), ("Ânní", "Priest"))
        self.assertEqual((history.p0_count, history.incomplete_p0_count), (3, 1))
        self.assertEqual(history.incomplete_p0_events[0].original_name,
                         "Unbekannt-Stitches")
        self.assertEqual(history.incomplete_p0_events[0].missing_fields, ("class",))
        self.assertIn("INCOMPLETE_P0_IGNORED", history.warnings)
        self.assertNotIn("DATA_CONFLICT", history.warnings)
        self.assertEqual(history.eternal_dkp_total, 10)

    def test_p0_nonidentity_zero_reference_is_audited_not_a_member_candidate(self):
        result = self.analyze([(1, 101)], [
            self.event(100, "P0", g=[1, 101], n="Ânní-Stitches", c=5, s=[1, 0]),
        ])
        self.assertEqual([history.guid for history in result.guid_histories], ["1:101"])
        self.assertEqual(result.summary["technicalGuidsIgnored"], 1)
        ignored = result.ignored_technical_guids[0]
        self.assertEqual((ignored.guid, ignored.warning),
                         ("1:0", "TECHNICAL_GUID_IGNORED"))
        self.assertTrue(ignored.source_references[0].startswith("P0.s:"))

    def test_unresolved_nonzero_character_guid_is_not_silently_filtered(self):
        result = self.analyze([(1, 101), (1, 102)], [
            self.event(100, "P0", g=[1, 101], n="Ânní-Stitches", c=5),
        ])
        self.assertEqual({history.guid for history in result.guid_histories},
                         {"1:101", "1:102"})
        unresolved = next(history for history in result.guid_histories
                          if history.guid == "1:102")
        self.assertIn("P0_MISSING", unresolved.warnings)
        self.assertEqual(result.ignored_technical_guids, ())

    def test_incomplete_only_p0_remains_an_unresolved_character_case(self):
        result = self.analyze([(1, 101)], [
            self.event(100, "P0", g=[1, 101], n="Unbekannt-Stitches", c=""),
        ])
        history = result.guid_histories[0]
        self.assertEqual(history.guid, "1:101")
        self.assertEqual(history.normalized_name, "")
        self.assertIn("P0_IDENTITY_MISSING", history.warnings)
        self.assertEqual(result.ignored_technical_guids, ())

    def test_conflicting_p0_name_for_same_guid_is_reported(self):
        result = self.analyze([(1, 101)], [
            self.event(100, "P0", g=[1, 101], n="Annî-Stitches", c=5),
            self.event(200, "P0", g=[1, 101], n="Anni-Stitches", c=5),
        ])
        history = result.guid_histories[0]
        self.assertEqual(history.normalized_name, "Annî")
        self.assertIn("P0_NAME_CONFLICT:Annî/Anni", history.warnings)
        self.assertIn("DATA_CONFLICT", history.warnings)

    def test_analysis_does_not_modify_identity_v2_store_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "identity-v2.json"
            save_identity_v2(IdentityV2Store(members=[Member("m1", "Annî", "Priest")]), path)
            before = path.read_bytes()
            self.analyze([(1, 101)], [
                self.event(100, "P0", g=[1, 101], n="Annî-Stitches", c=5),
            ])
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
