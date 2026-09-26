"""Focused tests for the multi-GUID review draft and its Qt dialog."""

import copy
import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.clm_identity_v2_analysis import analyze_clm_ledger
from app.clm_identity_v2_decisions import (
    CONTINUE, NEW_CHARACTER, ClmIdentityDecisionDraft, ClmIdentityDecisionError,
)
from app.identity_v2 import IdentityV2Store, Member
from app.identity_v2_storage import save_identity_v2

try:
    from PySide6.QtWidgets import QApplication, QComboBox
    from app import clm_identity_v2_dialog as dialog_ui
    from app.clm_identity_v2_dialog import ClmIdentityDecisionDialog
except ImportError:
    QApplication = QComboBox = ClmIdentityDecisionDialog = dialog_ui = None


def analysis_for(*characters):
    """Build a small selected-roster ledger from (GUID, name, class, P0, P1)."""
    roster_id = "roster-1"
    events = [{"_c": 1, "_b": 0, "_e": 1, "_a": 1,
               "_d": "R0", "r": roster_id, "n": "Bierstube", "p": 0}]
    sequence = 2
    for guid, name, class_id, first, last in characters:
        profile_events = [
            (first, "P0", {"g": list(guid), "n": f"{name}-Stitches", "c": class_id}),
            (first + 1, "R9", {"r": roster_id, "p": [list(guid)]}),
        ]
        if last is not None:
            profile_events.append((last, "P1", {"g": list(guid)}))
        for timestamp, opcode, fields in profile_events:
            events.append({"_c": timestamp, "_b": 0, "_e": 1, "_a": sequence,
                           "_d": opcode, **fields})
            sequence += 1
    return analyze_clm_ledger(events, roster_id)


class ClmIdentityDecisionTests(unittest.TestCase):
    def two(self, *, second_class=5, gap=100):
        return analysis_for(
            ((1, 101), "Annî", 5, 100, 200),
            ((1, 102), "Annî", second_class, 200 + gap, None),
        )

    def test_two_guids_continuation_creates_one_decision_group(self):
        draft = ClmIdentityDecisionDraft(self.two())
        with self.assertRaises(ClmIdentityDecisionError):
            draft.to_decision_set()
        self.assertEqual(draft.allowed_actions("Annî", "1:102"), (CONTINUE, NEW_CHARACTER))
        draft.set_choice("Annî", "1:102", CONTINUE)
        decision = draft.to_decision_set().decisions[0]
        self.assertEqual(decision.ordered_guids, ("1:101", "1:102"))
        self.assertEqual(decision.character_groups, (("1:101", "1:102"),))

    def test_two_guids_separation_creates_two_decision_groups(self):
        draft = ClmIdentityDecisionDraft(self.two())
        draft.set_choice("Annî", "1:102", NEW_CHARACTER)
        self.assertEqual(draft.to_decision_set().decisions[0].character_groups,
                         (("1:101",), ("1:102",)))

    def test_three_guids_can_combine_first_two_and_separate_third(self):
        analysis = analysis_for(
            ((1, 101), "Annî", 5, 100, 200),
            ((1, 102), "Annî", 5, 300, 400),
            ((1, 103), "Annî", 8, 500, None),
        )
        draft = ClmIdentityDecisionDraft(analysis)
        draft.set_choice("Annî", "1:102", CONTINUE)
        self.assertEqual(draft.choice("Annî", "1:103"), NEW_CHARACTER)
        self.assertEqual(draft.to_decision_set().decisions[0].character_groups,
                         (("1:101", "1:102"), ("1:103",)))

    def test_three_guids_can_all_be_separate(self):
        draft = ClmIdentityDecisionDraft(analysis_for(
            ((1, 101), "Annî", 5, 100, 200),
            ((1, 102), "Annî", 5, 300, 400),
            ((1, 103), "Annî", 5, 500, None),
        ))
        draft.set_choice("Annî", "1:102", NEW_CHARACTER)
        draft.set_choice("Annî", "1:103", NEW_CHARACTER)
        self.assertEqual(draft.to_decision_set().decisions[0].character_groups,
                         (("1:101",), ("1:102",), ("1:103",)))

    def test_class_conflict_forces_new_character(self):
        draft = ClmIdentityDecisionDraft(self.two(second_class=11))
        row = draft.rows_for("Annî")[1]
        self.assertTrue(row.forced_new)
        self.assertIn("Klassenkonflikt", row.analysis)
        self.assertEqual(draft.allowed_actions("Annî", "1:102"), (NEW_CHARACTER,))
        with self.assertRaises(ClmIdentityDecisionError):
            draft.set_choice("Annî", "1:102", CONTINUE)

    def test_time_overlap_forces_separation_and_explains_conflict(self):
        draft = ClmIdentityDecisionDraft(analysis_for(
            ((1, 101), "Annî", 5, 100, 300),
            ((1, 102), "Annî", 5, 200, 400),
        ))
        row = draft.rows_for("Annî")[1]
        self.assertTrue(row.forced_new)
        self.assertIn("Überlappung", row.distance)
        self.assertIn("Zeitliche Überlappung", row.analysis)

    def test_conflicting_p0_data_is_visible_and_forces_separation(self):
        roster_id = "roster-1"
        events = [
            {"_c": 1, "_b": 0, "_e": 1, "_a": 1,
             "_d": "R0", "r": roster_id, "n": "Bierstube", "p": 0},
            {"_c": 100, "_b": 0, "_e": 1, "_a": 2,
             "_d": "P0", "g": [1, 101], "n": "Annî-Stitches", "c": 5},
            {"_c": 120, "_b": 0, "_e": 1, "_a": 3,
             "_d": "P0", "g": [1, 101], "n": "Annî-Stitches", "c": 8},
            {"_c": 130, "_b": 0, "_e": 1, "_a": 4,
             "_d": "R9", "r": roster_id, "p": [[1, 101]]},
            {"_c": 200, "_b": 0, "_e": 1, "_a": 5,
             "_d": "P1", "g": [1, 101]},
            {"_c": 300, "_b": 0, "_e": 1, "_a": 6,
             "_d": "P0", "g": [1, 102], "n": "Annî-Stitches", "c": 5},
            {"_c": 301, "_b": 0, "_e": 1, "_a": 7,
             "_d": "R9", "r": roster_id, "p": [[1, 102]]},
        ]
        draft = ClmIdentityDecisionDraft(analyze_clm_ledger(events, roster_id))
        row = draft.rows_for("Annî")[1]
        self.assertTrue(row.forced_new)
        self.assertIn("Datenkonflikt", row.analysis)
        self.assertEqual(draft.allowed_actions("Annî", "1:102"), (NEW_CHARACTER,))

    def test_long_gap_remains_unselected_and_can_be_decided_both_ways(self):
        start = 1_700_000_000
        gap = 261 * 86400
        analysis = analysis_for(
            ((1, 101), "Annî", 5, start, start + 86400),
            ((1, 102), "Annî", 5, start + 86400 + gap, None),
        )
        draft = ClmIdentityDecisionDraft(analysis)
        row = draft.rows_for("Annî")[1]
        self.assertEqual(row.distance, "261 Tage")
        self.assertIsNone(row.decision)
        self.assertEqual(draft.allowed_actions("Annî", "1:102"), (CONTINUE, NEW_CHARACTER))

    def test_short_gap_is_displayed_in_seconds(self):
        draft = ClmIdentityDecisionDraft(self.two(gap=22))
        self.assertEqual(draft.rows_for("Annî")[1].distance, "22 Sekunden")

    def test_abandoning_draft_does_not_modify_store_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guild-v2.json"
            save_identity_v2(IdentityV2Store(members=[Member("m1", "Annî", "Priest")]), path)
            before = path.read_bytes()
            draft = ClmIdentityDecisionDraft(self.two())
            draft.set_choice("Annî", "1:102", CONTINUE)
            del draft
            self.assertEqual(path.read_bytes(), before)

    def test_decision_set_has_no_member_id(self):
        draft = ClmIdentityDecisionDraft(self.two())
        draft.set_choice("Annî", "1:102", CONTINUE)
        self.assertNotIn("memberId", str(asdict(draft.to_decision_set())))

    def test_first_guid_is_fixed_and_single_guid_names_need_no_review(self):
        analysis = analysis_for(
            ((1, 101), "Annî", 5, 100, 200),
            ((1, 102), "Annî", 5, 300, None),
            ((1, 201), "Einzel", 8, 100, None),
        )
        draft = ClmIdentityDecisionDraft(analysis)
        self.assertEqual(len(draft.group_order), 1)
        self.assertEqual(draft.allowed_actions("Annî", "1:101"), ())
        with self.assertRaises(ClmIdentityDecisionError):
            draft.set_choice("Annî", "1:101", CONTINUE)

    def test_sort_does_not_jump_after_choice_change(self):
        draft = ClmIdentityDecisionDraft(analysis_for(
            ((1, 101), "Annî", 5, 100, 200),
            ((1, 102), "Annî", 5, 300, None),
            ((1, 201), "Bämäräng", 11, 100, 200),
            ((1, 202), "Bämäräng", 2, 300, None),
        ))
        draft.sort_groups(0, descending=True)
        order = tuple(draft.group_order)
        draft.set_choice("Annî", "1:102", CONTINUE)
        self.assertEqual(tuple(draft.group_order), order)
        self.assertEqual(draft.group(order[0]).guid_histories[0].guid, "1:201")

    def test_distance_header_sorts_groups_numerically(self):
        draft = ClmIdentityDecisionDraft(analysis_for(
            ((1, 101), "Annî", 5, 100, 200),
            ((1, 102), "Annî", 5, 209, None),
            ((1, 201), "Bämäräng", 5, 100, 200),
            ((1, 202), "Bämäräng", 5, 300, None),
        ))
        draft.sort_groups(5)
        self.assertEqual(draft.group_order, ["annî", "bämäräng"])

    def test_unicode_names_and_analysis_remain_unchanged(self):
        analysis = analysis_for(
            ((1, 101), "Jêmma", 5, 100, 200),
            ((1, 102), "Jêmma", 5, 300, None),
            ((1, 201), "Jêmmâ", 5, 100, 200),
            ((1, 202), "Jêmmâ", 5, 300, None),
        )
        before = copy.deepcopy(analysis)
        draft = ClmIdentityDecisionDraft(analysis)
        draft.set_choice("Jêmma", "1:102", CONTINUE)
        draft.set_choice("Jêmmâ", "1:202", NEW_CHARACTER)
        self.assertEqual(analysis, before)
        self.assertEqual({item.normalized_name for item in draft.to_decision_set().decisions},
                         {"Jêmma", "Jêmmâ"})

@unittest.skipUnless(QApplication is not None, "PySide6 ist lokal nicht verfügbar")
class ClmIdentityDecisionDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_group_sort_keeps_guid_order_and_decision_does_not_resort(self):
        analysis = analysis_for(
            ((1, 101), "Annî", 5, 100, 200),
            ((1, 102), "Annî", 5, 300, None),
            ((1, 201), "Bämäräng", 11, 100, 200),
            ((1, 202), "Bämäräng", 2, 300, None),
        )
        dialog = ClmIdentityDecisionDialog(analysis)
        self.addCleanup(dialog.close)
        dialog._header_clicked(0)
        dialog._header_clicked(0)
        self.assertEqual(dialog.tree.topLevelItem(0).text(0), "Bämäräng")
        annie = dialog._group_items["annî"]
        self.assertEqual([annie.child(i).text(2) for i in range(annie.childCount())],
                         ["1:101", "1:102"])
        combo = dialog.tree.itemWidget(annie.child(1), 8)
        self.assertIsInstance(combo, QComboBox)
        combo.setCurrentIndex(1)
        self.assertEqual(dialog.tree.topLevelItem(0).text(0), "Bämäräng")
        dialog.reject()
        self.assertIsNone(dialog.result_value)

    def test_resolved_group_does_not_open_review_and_new_guid_keeps_old_choice(self):
        from app.clm_v2_refresh import prepare_clm_identity_refresh_review

        resolved = analysis_for(
            ((1, 101), "Anni", 5, 100, 200),
            ((1, 102), "Anni", 5, 300, None),
        )
        store = IdentityV2Store(
            members=[Member("m1000", "Anni", "Priest", clmGuid="1:102")],
            legacyClmGuidMemberMap={"1:101": "m1000"},
        )
        with patch.object(dialog_ui, "ClmIdentityDecisionDialog",
                          side_effect=AssertionError("Bekannte GUID erneut gefragt")):
            decisions = dialog_ui.collect_clm_identity_decisions(
                resolved, target_store=store)
        self.assertEqual(decisions.decisions[0].character_groups,
                         (("1:101", "1:102"),))

        new = analysis_for(
            ((1, 101), "Anni", 5, 100, 200),
            ((1, 102), "Anni", 5, 300, 400),
            ((1, 103), "Anni", 5, 500, None),
        )
        draft, groups, locked = prepare_clm_identity_refresh_review(store, new)
        dialog = ClmIdentityDecisionDialog(
            new, draft=draft, review_group_keys=groups, locked_choices=locked)
        self.addCleanup(dialog.close)
        item = dialog._group_items["anni"]
        self.assertEqual(dialog.tree.topLevelItemCount(), 1)
        old_combo = dialog.tree.itemWidget(item.child(1), 8)
        new_combo = dialog.tree.itemWidget(item.child(2), 8)
        self.assertEqual(old_combo.currentData(), CONTINUE)
        self.assertFalse(old_combo.isEnabled())
        self.assertIsNone(new_combo.currentData())
        self.assertTrue(new_combo.isEnabled())
        self.assertGreaterEqual(dialog.width(), 800)
        self.assertGreaterEqual(dialog.tree.columnWidth(8), 225)


if __name__ == "__main__":
    unittest.main()
