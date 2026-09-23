# -*- coding: utf-8 -*-
"""Focused offscreen checks for the Qt graveyard zoom and responsive grid."""
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
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from app.GuildGearCheckerQt import GraveyardCanvas, GuildGearCheckerQt


class GraveyardSmokeWindow(GuildGearCheckerQt):
    def _load_autosave_or_seed(self) -> None:
        self.model.new_empty()
        member = self.model.add_member("GraveyardSmoke", "Smoke")
        member.lifeStatus = "dead"
        member.deathDate = "2026-09-23"

    def _apply_character_cache_once(self) -> None:
        return

    def autosave(self) -> None:
        return


def run() -> None:
    app = QApplication.instance() or QApplication([])
    with patch("app.GuildGearCheckerQt.read_suite_settings", return_value={}):
        window = GraveyardSmokeWindow()
    window._portrait_timer.stop()
    window._grabber_actions_timer.stop()
    try:
        window.switch_page("graveyard")
        app.processEvents()
        assert window.grave_view.slider.minimum() == 40
        assert "#80643f" in window.grave_view.zoom_bar.styleSheet()

        inventory_calls = 0
        original_inventory = window.model.gravestone_inventory

        def counted_inventory():
            nonlocal inventory_calls
            inventory_calls += 1
            return original_inventory()

        window.model.gravestone_inventory = counted_inventory
        with patch.object(
            window, "refresh_graveyard",
            side_effect=AssertionError("Zoom must not trigger a data refresh"),
        ), patch("app.GuildGearCheckerQt.update_suite_settings") as save_settings:
            window._schedule_graveyard_zoom(40)
            assert save_settings.call_count == 0
            window._graveyard_zoom_timer.stop()
            window._apply_graveyard_zoom()
            assert window.grave_canvas.zoom_percent == 40
            assert window.grave_canvas._display_card_size() == (88, 120)
            assert inventory_calls == 0
            window._graveyard_zoom_save_timer.stop()
            window._persist_graveyard_zoom()
            save_settings.assert_called_once_with(
                window._suite_settings_path, graveyard_zoom_percent=40,
            )

        canvas = GraveyardCanvas()
        pixmap = QPixmap(220, 300)
        pixmap.fill(Qt.GlobalColor.transparent)
        canvas.set_scene(
            [(f"m{index}", pixmap) for index in range(8)],
            zoom_percent=40, summary="8", empty_text="",
        )
        canvas.resize(420, 520)
        narrow_rects, narrow_height = canvas._layout_data()
        canvas.resize(900, 520)
        wide_rects, wide_height = canvas._layout_data()
        assert len({rect.y() for _member_id, rect in wide_rects}) < len({rect.y() for _member_id, rect in narrow_rects})
        assert wide_height <= narrow_height
        assert min(rect.x() for _member_id, rect in wide_rects) >= 14
        assert not window.grave_canvas.activation_enabled

        print("Qt Graveyard Zoom Smoke: OK")
    finally:
        window._graveyard_zoom_timer.stop()
        window._graveyard_zoom_save_timer.stop()
        window.hide()
        window.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    run()
