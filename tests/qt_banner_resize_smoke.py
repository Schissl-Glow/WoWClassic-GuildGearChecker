# -*- coding: utf-8 -*-
"""Focused offscreen checks for the responsive checker banner."""
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
if os.name == "nt" and "SystemRoot" in os.environ:
    os.environ.setdefault("QT_QPA_FONTDIR", str(Path(os.environ["SystemRoot"]) / "Fonts"))

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtWidgets import QApplication

from app.GuildGearCheckerQt import (
    BG, CHECKER_BANNER_HEIGHT, CHECKER_BANNER_MAX_COVER_WIDTH,
    GuildGearCheckerQt, HeaderWidget,
)


class BannerSmokeWindow(GuildGearCheckerQt):
    def _load_autosave_or_seed(self) -> None:
        self.model.new_empty()

    def _apply_character_cache_once(self) -> None:
        return

    def autosave(self) -> None:
        return

    def open_portrait_grabber(self) -> None:
        self.grabber_click_count = getattr(self, "grabber_click_count", 0) + 1


def run() -> None:
    app = QApplication.instance() or QApplication([])
    with (
        patch("app.GuildGearCheckerQt.read_suite_settings", return_value={}),
        patch("app.GuildGearCheckerQt.update_suite_settings"),
    ):
        window = BannerSmokeWindow()
        try:
            window.show()
            app.processEvents()
            header = window.findChild(HeaderWidget)
            assert header is not None and not header._source.isNull()
            source = header._source.size()
            assert window.grabber_button.objectName() == "headerGrabberButton"
            assert list(window._nav_buttons) == [
                "rooster", "graveyard", "management", "raid", "settings"]
            assert window.roster_export_button.objectName() == "rosterExportButton"
            window.identity_v2_store.guildName = "Bierstuben"
            window.refresh_project_label()
            assert window.banner_title.toolTip() == "Bierstuben"
            long_name = "Bierstuben " * 20
            window._set_banner_title(long_name)
            assert window.banner_title.toolTip() == long_name
            assert window.banner_title.text() != long_name
            window._set_banner_title("Bierstuben")
            window.grabber_button.setEnabled(True)
            window.grabber_button.click()
            assert window.grabber_click_count == 1
            for width in (1000, 1400, 1800, 2200):
                window.resize(width, 850)
                app.processEvents()
                header._resize_timer.stop()
                header._render_cover()
                assert header.height() == CHECKER_BANNER_HEIGHT
                assert header._rendered_size == header.size()
                assert not header._rendered.isNull()
                image_size = QSize(
                    min(round(header.width() * 0.78), CHECKER_BANNER_MAX_COVER_WIDTH),
                    header.height(),
                )
                scaled = header._source.scaled(
                    image_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                assert abs(scaled.width() * source.height() - scaled.height() * source.width()) <= source.width()
                assert header._rendered_image_left == max(0, header.width() - scaled.width())
                assert header._rendered_image_left > 0
                image = header._rendered.toImage()
                assert image.pixelColor(1, header.height() // 2).name() == BG
                assert image.pixelColor(header.width() - 2, header.height() // 2).name() != BG
                title_right = window.banner_title.mapTo(
                    header, QPoint(window.banner_title.width(), 0)).x()
                grabber_left = window.grabber_button.mapTo(header, QPoint(0, 0)).x()
                assert title_right < grabber_left
                assert window.roster_search_edit.width() >= 190

            for page in ("rooster", "graveyard", "management", "raid", "settings"):
                window.switch_page(page, refresh=False)
                assert window._nav_buttons[page].isChecked()
            window.switch_page("rooster", refresh=False)
            window.roster_list_button.click()
            assert window._roster_view_mode == "list"
            window.roster_cards_button.click()
            assert window._roster_view_mode == "cards"

            window.showMaximized()
            app.processEvents()
            header._resize_timer.stop()
            header._render_cover()
            assert header._rendered_size == header.size()
            window.showNormal()
            app.processEvents()
            header._resize_timer.stop()
            header._render_cover()
            assert header._rendered_size == header.size()
            print("Qt Banner Resize Smoke: OK")
        finally:
            header = window.findChild(HeaderWidget)
            if header is not None:
                header._resize_timer.stop()
            window.hide()
            window.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    run()
