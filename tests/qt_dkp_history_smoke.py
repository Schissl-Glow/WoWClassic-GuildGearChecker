# -*- coding: utf-8 -*-
"""Focused read-only DKP history checks."""
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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHeaderView

from app.GuildGearCheckerQt import GuildGearCheckerQt, get_language, set_language, tr
from app.clm_history import EternalDkpRecord


class DkpHistorySmokeWindow(GuildGearCheckerQt):
    def _load_autosave_or_seed(self) -> None:
        self.model.new_empty()
        self.model.dkp_enabled = True
        self.player = self.model.add_player("Raidspieler")
        self.other_player = self.model.add_player("Anderer Spieler")
        self.main = self.model.add_member("Janos", "Smoke")
        self.twink = self.model.add_member("Janosz", "Smoke")
        self.other = self.model.add_member("Bifi", "Smoke")
        for member, player, character_type in (
            (self.main, self.player, "main"),
            (self.twink, self.player, "twink"),
            (self.other, self.other_player, "main"),
        ):
            member.className = "Warrior"
            self.model.update_member_assignment(
                member.id, player.playerId, character_type, "dps",
            )
        self.raid = self.model.create_raid("2026-09-18", "Blackwing Lair", "", "BWL")
        self.model.eternal_dkp.records = [
            EternalDkpRecord("old", self.main.id, "Janos", 8, "EARNED_RAID",
                             raid_id=self.raid.id, timestamp=1789730000),
            EternalDkpRecord("new", self.twink.id, "Janosz", -5, "CORRECTION",
                             clm_raid_id="clm-42", timestamp=1789810000),
            EternalDkpRecord("other", self.other.id, "Bifi", 22, "EARNED_OTHER",
                             timestamp=1789890000),
        ]

    def _apply_character_cache_once(self) -> None:
        return

    def autosave(self) -> None:
        return


def run() -> None:
    app = QApplication.instance() or QApplication([])
    language = get_language()
    with (
        patch("app.GuildGearCheckerQt.read_suite_settings", return_value={}),
        patch("app.GuildGearCheckerQt.update_suite_settings"),
    ):
        window = DkpHistorySmokeWindow()
    window._portrait_timer.stop()
    window._grabber_actions_timer.stop()
    try:
        window.show()
        app.processEvents()
        window.switch_page("raid")
        window.raid_subtabs.setCurrentWidget(window.dkp_history_page)
        app.processEvents()
        assert window.raid_subtabs.indexOf(window.dkp_history_page) >= 0
        assert window.dkp_history_table.columnCount() == 6
        window.dkp_history_subject.setCurrentIndex(
            window.dkp_history_subject.findData(window.player.playerId)
        )
        assert window.dkp_history_subject.currentData() == window.player.playerId
        table = window.dkp_history_table
        assert table.rowCount() == 2
        assert table.item(0, 4).text() == "-5"
        assert table.item(1, 4).text() == "+8"
        assert table.item(0, 1).text() == "CLM-Raid clm-42"
        assert "Blackwing Lair" in table.item(1, 1).text()
        assert all(
            table.horizontalHeader().sectionResizeMode(column) == QHeaderView.ResizeMode.Interactive
            for column in range(table.columnCount())
        )
        table.setColumnWidth(5, 385)
        window.refresh_dkp_history()
        assert table.columnWidth(5) == 385
        table.sortItems(4, Qt.SortOrder.AscendingOrder)
        assert table.item(0, 4).text() == "-5"
        table.sortItems(0, Qt.SortOrder.DescendingOrder)
        window._open_dkp_history_raid(1)
        assert window.raid_subtabs.currentWidget() is window.raids_page
        assert window._selected_raid().id == window.raid.id

        window.raid_subtabs.setCurrentWidget(window.dkp_history_page)
        window.dkp_history_mode.setCurrentIndex(window.dkp_history_mode.findData("character"))
        window.dkp_history_subject.setCurrentIndex(
            window.dkp_history_subject.findData(window.twink.id)
        )
        assert table.rowCount() == 1 and table.item(0, 4).text() == "-5"
        window.dkp_history_subject.setCurrentIndex(
            window.dkp_history_subject.findData(window.main.id)
        )
        assert table.rowCount() == 1 and table.item(0, 4).text() == "+8"
        window.dkp_history_mode.setCurrentIndex(window.dkp_history_mode.findData("player"))
        window.dkp_history_subject.setCurrentIndex(
            window.dkp_history_subject.findData(window.other_player.playerId)
        )
        assert table.rowCount() == 1 and table.item(0, 1).text() == "–"

        set_language("de")
        assert tr("dkp_history.tab") == "DKP-Historie"
        set_language("en")
        assert tr("dkp_history.tab") == "DKP History"
        print("Qt DKP History Smoke: OK")
    finally:
        set_language(language)
        window._graveyard_zoom_timer.stop()
        window._graveyard_zoom_save_timer.stop()
        window.hide()
        window.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    run()
