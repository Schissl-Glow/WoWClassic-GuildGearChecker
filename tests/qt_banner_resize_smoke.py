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

from PySide6.QtCore import QSize, Qt
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
            for width in (1000, 1400, 1800, 2200):
                window.resize(width, 850)
                app.processEvents()
                header._resize_timer.stop()
                header._render_cover()
                assert header.height() == CHECKER_BANNER_HEIGHT
                assert header._rendered_size == header.size()
                assert not header._rendered.isNull()
                cover_size = QSize(
                    min(header.width(), CHECKER_BANNER_MAX_COVER_WIDTH), header.height(),
                )
                scaled = header._source.scaled(
                    cover_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                assert abs(scaled.width() * source.height() - scaled.height() * source.width()) <= source.width()
                assert header._rendered.toImage().pixelColor(1, header.height() // 2).name() != BG

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
