"""Offscreen classification review after finalized CLM GUID decisions."""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from app.clm_v2_classification_ui import ClmV2ClassificationDialog
except ImportError:
    QApplication = ClmV2ClassificationDialog = None

from app.clm_identity_v2_decisions import CONTINUE, ClmIdentityDecisionDraft
from app.clm_v2_initialization import analyze_clm_v2_selection, inspect_clm_v2_source
from app.i18n import tr
from app.identity_v2 import IdentityV2Store, Member, Player
from tests.clm_v2_initialization_tests import synthetic_lua


@unittest.skipIf(QApplication is None, "PySide6 ist lokal nicht verfügbar.")
class ClmV2ClassificationQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_one_row_per_final_group_and_explicit_bulk_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ClassicLootManager.lua"
            source.write_text(synthetic_lua(), encoding="utf-8")
            analysis = analyze_clm_v2_selection(
                inspect_clm_v2_source(source),
                "exp0 alliance stitches bierstube", "10",
            )
            draft = ClmIdentityDecisionDraft(analysis.identity_analysis)
            draft.set_choice("Annî", "1:102", CONTINUE)
            decisions = draft.to_decision_set()
            dialog = ClmV2ClassificationDialog(
                analysis.identity_analysis, decisions,
            )
            self.addCleanup(dialog.close)
            self.assertEqual(dialog.table.rowCount(), 2)
            self.assertEqual(dialog.table.columnCount(), 4)
            self.assertEqual(dialog.choices, {})
            annie = next(chain for name, chain in dialog._rows if name == "Annî")
            self.assertEqual(annie, ("1:101", "1:102"))
            dialog._classify_open("ACTIVE_UNKNOWN")
            self.assertEqual(len(dialog.choices), 2)
            self.assertTrue(all(choice.activity_status == "active"
                                for choice in dialog.choices.values()))
            dialog.table.horizontalHeader().sectionClicked.emit(0)
            self.assertIn(annie, dialog.choices)
            row = next(index for index, (_name, chain) in enumerate(dialog._rows)
                       if chain == annie)
            dialog.table.selectRow(row)
            dialog._ignore_selected()
            self.assertEqual(dialog.choices[annie].relevance, "irrelevant")
            dialog._confirm()
            self.assertEqual(dialog.result_value, dialog.choices)

    def test_activity_player_and_existing_member_are_separate_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ClassicLootManager.lua"
            source.write_text(synthetic_lua(), encoding="utf-8")
            analysis = analyze_clm_v2_selection(
                inspect_clm_v2_source(source),
                "exp0 alliance stitches bierstube", "10",
            )
            draft = ClmIdentityDecisionDraft(analysis.identity_analysis)
            draft.set_choice("Annî", "1:102", CONTINUE)
            store = IdentityV2Store(
                players=[Player("p0001", "Aba")],
                members=[Member("m1000", "Annî", "Priest", playerId="p0001")],
            )
            dialog = ClmV2ClassificationDialog(
                analysis.identity_analysis, draft.to_decision_set(),
                target_store=store,
            )
            self.addCleanup(dialog.close)
            self.assertEqual(dialog.table.columnCount(), 6)
            chain = next(group for name, group in dialog._rows if name == "Annî")
            row = next(index for index, (_name, group) in enumerate(dialog._rows)
                       if group == chain)

            def controls():
                return (dialog.table.cellWidget(row, 3),
                        dialog.table.cellWidget(row, 4),
                        dialog.table.cellWidget(row, 5))

            activity, player, member = controls()
            self.assertEqual(
                [activity.itemText(index) for index in range(1, 4)],
                [tr("clm_v2_classification.active"),
                 tr("clm_v2_classification.inactive"),
                 tr("clm_v2_classification.irrelevant")])
            self.assertEqual([activity.itemData(index) for index in range(1, 4)],
                             ["ACTIVE_UNKNOWN", "INACTIVE_UNKNOWN", "IRRELEVANT"])
            self.assertEqual(player.itemData(0), None)
            self.assertEqual(member.itemData(0), None)

            activity.setCurrentIndex(activity.findData("ACTIVE_UNKNOWN"))
            self.assertEqual((dialog.choices[chain].activity_status,
                              dialog.choices[chain].player_id), ("active", None))
            _activity, player, _member = controls()
            player.setCurrentIndex(player.findData("p0001"))
            self.assertEqual((dialog.choices[chain].activity_status,
                              dialog.choices[chain].player_id), ("active", "p0001"))
            player.setCurrentIndex(player.findData(None))
            self.assertIsNone(dialog.choices[chain].player_id)

            activity, _player, _member = controls()
            activity.setCurrentIndex(activity.findData("INACTIVE_UNKNOWN"))
            _activity, player, _member = controls()
            player.setCurrentIndex(player.findData("p0001"))
            self.assertEqual((dialog.choices[chain].activity_status,
                              dialog.choices[chain].player_id), ("inactive", "p0001"))

            activity, _player, _member = controls()
            activity.setCurrentIndex(activity.findData("IRRELEVANT"))
            self.assertEqual(dialog.choices[chain].relevance, "irrelevant")
            self.assertIsNone(dialog.choices[chain].player_id)
            self.assertFalse(controls()[1].isEnabled())

            activity, _player, _member = controls()
            activity.setCurrentIndex(activity.findData("ACTIVE_UNKNOWN"))
            _activity, player, member = controls()
            self.assertEqual(dialog.choices[chain].player_id, "p0001")
            member.setCurrentIndex(member.findData("m1000"))
            self.assertEqual(dialog.choices[chain].member_id, "m1000")
            self.assertEqual(dialog.choices[chain].activity_status, "active")
            self.assertFalse(controls()[0].isEnabled())
            self.assertEqual(controls()[1].currentData(), "p0001")
            self.assertFalse(controls()[1].isEnabled())
            controls()[2].setCurrentIndex(0)
            self.assertIsNone(dialog.choices[chain].member_id)
            self.assertEqual(dialog.choices[chain].player_id, "p0001")

    def test_columns_use_available_space_and_scroll_in_small_window(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ClassicLootManager.lua"
            source.write_text(synthetic_lua(), encoding="utf-8")
            analysis = analyze_clm_v2_selection(
                inspect_clm_v2_source(source),
                "exp0 alliance stitches bierstube", "10",
            )
            draft = ClmIdentityDecisionDraft(analysis.identity_analysis)
            draft.set_choice("Annî", "1:102", CONTINUE)
            long_name = "Aba mit einem sehr langen Spielernamen"
            store = IdentityV2Store(
                players=[Player("p0001", long_name)],
                members=[Member("m1000", "Annî", "Priest", playerId="p0001")],
            )
            dialog = ClmV2ClassificationDialog(
                analysis.identity_analysis, draft.to_decision_set(),
                target_store=store,
            )
            self.addCleanup(dialog.close)
            table = dialog.table
            self.assertGreater(table.columnWidth(4), table.columnWidth(1))
            self.assertGreaterEqual(
                table.columnWidth(4),
                table.fontMetrics().horizontalAdvance(f"{long_name} · p0001"),
            )
            self.assertGreaterEqual(
                table.columnWidth(3),
                table.fontMetrics().horizontalAdvance(
                    tr("clm_v2_classification.irrelevant")),
            )
            self.assertTrue(table.horizontalHeader().stretchLastSection())

            dialog.resize(720, 520)
            dialog.show()
            self.app.processEvents()
            self.assertGreater(table.horizontalScrollBar().maximum(), 0)


if __name__ == "__main__":
    unittest.main()
