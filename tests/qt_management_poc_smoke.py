# -*- coding: utf-8 -*-
"""Focused offscreen smoke test for the Qt management PoC."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["GGC_DISABLE_ICON_DOWNLOAD"] = "1"

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QCloseEvent
from tempfile import TemporaryDirectory
from PySide6.QtWidgets import QApplication, QHeaderView

from app import i18n as suite_i18n
from app.GuildGearChecker import raid_role_display
from app.GuildGearCheckerQt import GuildGearCheckerQt, MemberTable, ManagementPortraitLabel, CLASS_COLORS
from app.rewards import FrameOpeningRect
from app.GuildGearChecker import read_suite_settings
from app.raid_attendance import Raid, RaidAttendance


class ManagementSmokeWindow(GuildGearCheckerQt):
    def __init__(self) -> None:
        self.autosave_calls = 0
        super().__init__()

    def _load_autosave_or_seed(self) -> None:
        self.model.new_empty()
        first = self.model.add_member("ManagementAlpha", "Smoke")
        second = self.model.add_member("ManagementBeta", "Smoke")
        third = self.model.add_member("ManagementNever", "Smoke")
        shared = self.model.add_player("Shared Player")
        solo = self.model.add_player("Solo Player")
        self.model.update_member_assignment(first.id, shared.playerId, "main", "dps")
        self.model.update_member_assignment(second.id, shared.playerId, "twink", "dps")
        self.model.update_member_assignment(third.id, solo.playerId, "main", "dps")
        self.first_id = first.id
        self.second_id = second.id
        self.third_id = third.id

        self.model.raids = [
            Raid("r_old", "2026-08-01", "Old", status="recorded", raidType="MC"),
            Raid("r_bench", "2026-09-10", "Bench", status="recorded", raidType="BWL"),
            Raid("r_other", "2026-09-20", "Other character", status="recorded", raidType="AQ40"),
        ]
        self.model.raid_attendance = [
            RaidAttendance(
                "a_old", "r_old", shared.playerId, first.id, "main",
                shared.playerName, first.name, "present",
            ),
            RaidAttendance(
                "a_bench", "r_bench", shared.playerId, first.id, "main",
                shared.playerName, first.name, "bench",
            ),
            RaidAttendance(
                "a_other", "r_other", shared.playerId, second.id, "twink",
                shared.playerName, second.name, "present",
            ),
        ]

    def _apply_character_cache_once(self) -> None:
        return

    def autosave(self) -> None:
        self.autosave_calls += 1


def row_for_member(window: ManagementSmokeWindow, member_id: str) -> int:
    return next(
        row for row in range(window.member_table.rowCount())
        if str(window.member_table.item(row, 0).data(Qt.ItemDataRole.UserRole)) == member_id
    )


def run() -> None:
    app = QApplication.instance() or QApplication([])
    old_language = suite_i18n._translator.language
    suite_i18n._translator.language = "de"
    stored_widths = [310, 125, 135, 155, 140, 145, 115, 135, 120, 130]
    try:
        with patch(
            "app.GuildGearCheckerQt.read_suite_settings",
            return_value={"management_member_table_column_widths": stored_widths},
        ):
            window = ManagementSmokeWindow()
        window._portrait_timer.stop()
        window._grabber_actions_timer.stop()
        window.show()
        app.processEvents()
        try:
            # Successful construction is the focused startability check.
            window.switch_page("management")
            app.processEvents()
            assert window.member_table.columnCount() == 11
            assert type(window.detail_portrait) is ManagementPortraitLabel

            # All columns are mouse-resizable and stored widths load exactly.
            header = window.member_table.horizontalHeader()
            assert all(
                header.sectionResizeMode(column) == QHeaderView.ResizeMode.Interactive
                for column in range(window.member_table.columnCount())
            )
            assert window.member_table.column_widths() == stored_widths + [170]
            window.member_table.setColumnWidth(0, 347)
            window.refresh_member_table(select_first=False)
            assert window.member_table.columnWidth(0) == 347

            assert window.member_table.column_order()[-3:] == ["last_raid", "character_type", "assigned_main"]
            assert header.sectionsMovable()
            header.moveSection(header.visualIndex(10), 0)
            order = window.member_table.column_order()
            assert order[0] == "assigned_main"
            with TemporaryDirectory() as directory:
                settings_path = Path(directory) / "suite_settings.json"
                window._suite_settings_path = settings_path
                window.closeEvent(QCloseEvent())
                saved = read_suite_settings(settings_path)
                assert saved["management_member_table_column_order"] == order
                restored = MemberTable()
                restored.apply_column_order(saved["management_member_table_column_order"])
                restored.apply_column_widths(saved["management_member_table_column_widths"])
                assert restored.column_order() == order
                assert restored.columnWidth(0) == 347
                restored.apply_column_order(["name"] * 11)
                assert restored.column_order() == list(MemberTable.DEFAULT_COLUMN_ORDER)
                restored.deleteLater()
                # Geometry is independent of image dimensions and reward frames.
                portrait = window.detail_portrait
                container = window.detail_reward_portrait
                for width, height in [(40, 80), (800, 1600), (900, 300), (500, 500)]:
                    pixmap = QPixmap(width, height)
                    pixmap.fill(Qt.GlobalColor.red)
                    portrait.set_pixmap_source(pixmap)
                    app.processEvents()
                    assert portrait.size() == QSize(220, 220)
                    assert container.size() == QSize(220, 220)
                    assert not portrait.grab().isNull()
                frame_path = Path(directory) / "frame.png"
                frame = QPixmap(300, 500)
                frame.fill(Qt.GlobalColor.transparent)
                frame.save(str(frame_path))
                container.set_reward_frame(frame_path, FrameOpeningRect(30, 50, 240, 400))
                assert container.size() == QSize(220, 220)
                assert portrait.size() == QSize(220, 220)
                assert not portrait.grab().isNull()
                container.clear_reward_frame()
                portrait.clear_source()
                assert container.size() == QSize(220, 220)
            window.autosave_calls = 0
            assert window._pages["settings"].isAncestorOf(window.guild_name_edit)
            assert not window._pages["management"].isAncestorOf(window.guild_name_edit)

            # Class colors follow the selected member, including blocked load signals.
            first = window.model.find_by_id(window.first_id)
            for class_name in ("Warrior", "Warlock", "Mage"):
                first.className = class_name
                window.show_member(first.id)
                assert CLASS_COLORS[class_name] in window.detail_class.styleSheet()
                assert CLASS_COLORS[class_name] in window.class_combo.styleSheet()
            assert "border:none" in window.detail_portrait.styleSheet()
            assert "background:transparent" in window.detail_portrait.styleSheet()
            first.className = ""
            window.show_member(first.id)

            # Latest raid uses the exact memberId: present and bench both count;
            # another character with the same playerId cannot affect the value.
            first_row = row_for_member(window, window.first_id)
            second_row = row_for_member(window, window.second_id)
            third_row = row_for_member(window, window.third_id)
            assert window.member_table.item(first_row, 9).text() == "2026-09-10"
            assert window.member_table.item(second_row, 9).text() == "2026-09-20"
            assert window.member_table.item(third_row, 9).text() == "–"
            assert not (
                window.member_table.item(first_row, 9).flags() & Qt.ItemFlag.ItemIsEditable
            )

            assert window.member_table.item(first_row, 4).text() == "Main"
            assert window.member_table.item(second_row, 4).text() == "Twink"
            assert window.member_table.item(first_row, 10).text() == "–"
            assert window.member_table.item(second_row, 10).text() == "ManagementAlpha"
            assert not window.member_table.item(second_row, 10).flags() & Qt.ItemFlag.ItemIsEditable
            # Sorting and inline edits use logical indices after header movement.
            for column in (4, 10):
                window.member_table.sortItems(column, Qt.SortOrder.AscendingOrder)
            second = window.model.find_by_id(window.second_id)
            second.playerId = "missing-player"
            window.refresh_member_table()
            assert window.member_table.item(row_for_member(window, second.id), 10).text() == "–"
            second.playerId = window.model.find_by_id(window.first_id).playerId
            window.refresh_member_table()
            row = row_for_member(window, window.first_id)
            window.member_table.item(row, 5).setText(raid_role_display("healer"))
            assert window.model.find_by_id(window.first_id).raidRole == "healer"
            window.autosave_calls = 0

            # A discrete user choice saves immediately through the existing path.
            window._select_member_in_table(window.first_id)
            window.show_member(window.first_id)
            assert window.autosave_calls == 0
            window.raid_role_combo.setCurrentText(raid_role_display("tank"))
            app.processEvents()
            assert window.model.find_by_id(window.first_id).raidRole == "tank"
            assert window.autosave_calls == 1

            # Text is debounced, then flushed synchronously before character switch.
            window.notes_edit.setPlainText("Pending management note")
            assert window._detail_autosave_dirty
            assert window._detail_autosave_timer.isActive()
            assert window.autosave_calls == 1
            second_row = row_for_member(window, window.second_id)
            window.member_table.setCurrentCell(second_row, 0)
            app.processEvents()
            assert window.model.find_by_id(window.first_id).note == "Pending management note"
            assert window.selected_member_id == window.second_id
            assert window.autosave_calls == 2

            print("Qt Management PoC Smoke: OK")
        finally:
            window._detail_autosave_timer.stop()
            window.hide()
            window.deleteLater()
            app.processEvents()
    finally:
        suite_i18n._translator.language = old_language


if __name__ == "__main__":
    run()
