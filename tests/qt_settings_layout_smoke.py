# -*- coding: utf-8 -*-
"""Focused offscreen smoke test for the responsive settings layout."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.GuildGearCheckerQt import GuildGearCheckerQt, ResponsiveSettingsGrid


class SettingsSmokeWindow(GuildGearCheckerQt):
    def _load_autosave_or_seed(self) -> None:
        self.model.new_empty()

    def _apply_character_cache_once(self) -> None:
        return

    def autosave(self) -> None:
        return


def run() -> None:
    app = QApplication.instance() or QApplication([])
    with (
        patch("app.GuildGearCheckerQt.read_suite_settings", return_value={}),
        patch("app.GuildGearCheckerQt.update_suite_settings"),
    ):
        window = SettingsSmokeWindow()
    try:
        window.show()
        window.switch_page("settings")
        app.processEvents()
        grid = window._pages["settings"].findChild(ResponsiveSettingsGrid)
        assert grid is not None
        assert window.guild_name_edit is not None and window.guild_realm_edit is not None
        assert window.points_enabled_check is not None and window.dkp_enabled_check is not None
        assert window.raid_scope_all is not None and window.raid_scope_from is not None
        assert window.clm_path_edit is not None and window.clm_roster_combo is not None
        assert window.points_rebuild_button is not None
        assert window.raid_points_only_rebuild_button is not None
        assert window.outdated_check is not None and window.outdated_days_spin is not None
        assert window.language_combo is not None
        assert window.clm_status_label.wordWrap() and window.points_status_label.wordWrap()

        guild_card = window.guild_name_edit.parentWidget()
        assert guild_card is not None
        for width, wide in ((1500, True), (1080, False)):
            window.resize(width, 900)
            app.processEvents()
            assert grid.is_wide_layout is wide
            guild_position = grid._grid.getItemPosition(grid._grid.indexOf(guild_card))
            clm_position = grid._grid.getItemPosition(grid._grid.indexOf(window.clm_group))
            assert guild_position[1] == 0
            assert clm_position[1] == (1 if wide else 0)
            if wide:
                assert guild_card.width() > grid.width() * 0.4
                assert window.clm_group.width() > grid.width() * 0.4
                assert abs(guild_card.width() - window.clm_group.width()) < 40
            else:
                assert guild_card.width() > grid.width() * 0.8, (
                    grid.width(), guild_card.width(), window.clm_group.width(),
                )
                assert window.clm_group.width() > grid.width() * 0.8
        assert "#5b4930" in window._pages["settings"].styleSheet()
        print("Qt Settings Layout Smoke: OK")
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    run()
