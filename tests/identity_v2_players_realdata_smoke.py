"""Optional read-only V2 UI smoke with a temporary Save/Load roundtrip."""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QToolButton
    from app.identity_v2_players_qt import IdentityV2PlayersPage
except ImportError:
    Qt = QApplication = QMessageBox = QPushButton = QToolButton = IdentityV2PlayersPage = None

from app.identity_v2 import IdentityV2ValidationError
from app.identity_v2_storage import load_identity_v2, save_new_identity_v2
from app.i18n import tr


@unittest.skipIf(QApplication is None, "PySide6 ist lokal nicht verfügbar.")
class IdentityV2PlayersRealDataSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_read_only_v2_ui_owner_actions_and_temp_reload(self):
        root = Path(__file__).resolve().parents[1]
        candidates = [
            *sorted((root / "testdata").glob("*.ggc")),
            Path.home() / "Desktop" / "BS_Neu" / "BS_V2.ggc",
        ]
        source = store = None
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                store = load_identity_v2(candidate)
            except IdentityV2ValidationError:
                continue
            source = candidate
            break
        if source is None or store is None:
            self.skipTest("Keine lokale Identity-V2-Referenzdatei verfügbar.")
        original = source.read_bytes()
        attended = {entry.memberId for entry in store.attendance}
        credited = {entry.creditedMemberId for entry in store.raidCreditResolutions}
        eligible = [member for member in store.members
                    if member.playerId is None and member.lifeStatus == "active"
                    and member.memberId in attended and member.memberId not in credited]
        if len(eligible) < 6:
            self.skipTest("Die V2-Referenz hat weniger als sechs passende Member.")
        first, second, third, fourth, fifth, sixth = eligible[:6]

        def without_owner(record):
            data = record.to_dict()
            data.pop("playerId", None)
            return data

        raids = [item.to_dict() for item in store.raids]
        members = [without_owner(item) for item in store.members]
        attendance = [without_owner(item) for item in store.attendance]
        guid_map = dict(store.legacyClmGuidMemberMap)

        page = IdentityV2PlayersPage()
        self.addCleanup(page.close)
        render_started = time.perf_counter()
        page.set_store(store)
        page.show()
        self.app.processEvents()
        self.assertGreaterEqual(page.unassigned_table.rowCount(), 6)
        unknown_count = page.unassigned_table.rowCount()
        if unknown_count >= 250:
            sort_started = time.perf_counter()
            page._sort_unknown(4)
            self.app.processEvents()
            sort_seconds = time.perf_counter() - sort_started
            self.assertEqual(page.unassigned_table.rowCount(), unknown_count)
            print(f"Real-data smoke: {unknown_count} unknown rows; "
                  f"initial view {time.perf_counter() - render_started:.3f}s; "
                  f"raid-count sort {sort_seconds:.3f}s")

        def select_unknown_row(member_id):
            for index in range(page.player_table.rowCount()):
                if page.player_table.item(index, 0).data(Qt.ItemDataRole.UserRole) is None:
                    page.player_table.setCurrentCell(index, 0)
                    break
            for row in range(page.unassigned_table.rowCount()):
                if page.unassigned_table.item(row, 1).data(Qt.ItemDataRole.UserRole) == member_id:
                    page.unassigned_table.setCurrentCell(row, 1)
                    return
            self.fail(f"Unzugeordneter Member {member_id} nicht sichtbar")

        def check_unknown(*member_ids):
            for index in range(page.player_table.rowCount()):
                if page.player_table.item(index, 0).data(Qt.ItemDataRole.UserRole) is None:
                    page.player_table.setCurrentCell(index, 0)
                    break
            selected = set(member_ids)
            for row in range(page.unassigned_table.rowCount()):
                checkbox = page.unassigned_table.item(row, 0)
                checkbox.setCheckState(
                    Qt.CheckState.Checked if checkbox.data(Qt.ItemDataRole.UserRole) in selected
                    else Qt.CheckState.Unchecked)

        check_unknown(first.memberId, second.memberId)
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            page.bulk_create_button.click()
        player_a = page.store.get_player_for_member(first.memberId).playerId
        player_b = page.store.get_player_for_member(second.memberId).playerId
        self.assertNotEqual(player_a, player_b)
        self.assertEqual(page.store.get_main_member(player_a).memberId, first.memberId)
        select_unknown_row(third.memberId)
        with patch.object(page, "_choose_player", return_value=player_a):
            page.assign_button.click()
        page.player_table.setCurrentCell(next(
            index for index in range(page.player_table.rowCount())
            if page.player_table.item(index, 0).data(Qt.ItemDataRole.UserRole) == player_a), 0)
        next(button for button in page.member_rows[third.memberId].findChildren(QPushButton)
             if button.text() == tr("identity_v2_players.set_main")).click()
        self.assertEqual(page.store.get_main_member(player_a).memberId, third.memberId)
        menu = page.member_rows[third.memberId].findChild(QToolButton).menu()
        next(action for action in menu.actions()
             if action.text() == tr("identity_v2_players.set_inactive")).trigger()
        next(button for button in page.member_rows[third.memberId].findChildren(QPushButton)
             if button.text() == tr("identity_v2_players.reactivate")).click()
        self.assertIsNone(page.store.get_main_member(player_a))

        select_unknown_row(fourth.memberId)
        page.create_button.click()
        player_c = page.store.get_player_for_member(fourth.memberId).playerId
        with (patch.object(page, "_choose_player", return_value=player_c),
              patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.Yes)):
            page._reassign_member(third.memberId)
        check_unknown(fifth.memberId, sixth.memberId)
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            page.bulk_inactive_button.click()
        check_unknown(fifth.memberId, sixth.memberId)
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            page.bulk_active_button.click()
        for status in ("active", "inactive", "graveyard", "all"):
            page.status_filter.setCurrentIndex(page.status_filter.findData(status))
        self.assertEqual(page.store.get_player_for_member(third.memberId).playerId,
                         player_c)
        self.assertEqual({item.playerId for item in page.store.attendance
                          if item.memberId == third.memberId}, {player_c})

        self.assertEqual([item.to_dict() for item in page.store.raids], raids)
        self.assertEqual([without_owner(item) for item in page.store.members], members)
        self.assertEqual([without_owner(item) for item in page.store.attendance],
                         attendance)
        self.assertEqual(page.store.legacyClmGuidMemberMap, guid_map)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "v2-player-ui-smoke.ggc"
            save_new_identity_v2(page.store, target)
            restored = load_identity_v2(target)
        page.set_store(restored, reset_filters=True)
        self.assertEqual(page.store.to_payload(), restored.to_payload())
        self.assertEqual(page.store.get_player_for_member(third.memberId).playerId,
                         player_c)
        self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
