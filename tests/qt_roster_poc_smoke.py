# -*- coding: utf-8 -*-
"""Focused offscreen Qt roster smoke; no other page workflows or real projects."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["GGC_DISABLE_ICON_DOWNLOAD"] = "1"

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFormLayout, QFrame
from app import GuildGearCheckerQt as qt
from app import i18n
from app.rewards import RewardAsset, RewardAssignments


class RosterSmokeWindow(qt.GuildGearCheckerQt):
    # Same isolation pattern as qt_checker_smoke.py, without executing its
    # unrelated management, raid, graveyard and persistence assertions.
    def _load_autosave_or_seed(self) -> None:
        self.model.new_empty()
        for index, role in enumerate(("tank", "healer", "dps", "not_set", "dps", "healer")):
            name = "RosterBífiMitLangemNamen" if index == 0 else f"RosterBífi{index}"
            member = self.model.add_member(name, "Smoke")
            member.className = "Priest" if role == "healer" else "Warrior"
            member.spec = "Holy" if role == "healer" else ""
            player = self.model.add_player(f"RosterPlayer{index}")
            self.model.update_member_assignment(member.id, player.playerId, "main", role)
            member.raidStatus = ("Bereit", "Nicht bereit", "")[index % 3]
        dead = self.model.add_member("Historical", "Smoke")
        dead.lifeStatus = "dead"
        dead.deathDate = "2026-09-01"
        inactive = self.model.add_member("Inactive", "Smoke")
        inactive.lifeStatus = "inactive"

    def _apply_character_cache_once(self) -> None:
        return

    def autosave(self) -> None:
        return


def run() -> None:
    app = QApplication.instance() or QApplication([])
    old_language = i18n._translator.language

    # Framed detail portraits fill their complete opening instead of leaving
    # letterbox strips when source and target aspect ratios differ.
    framed_portrait = qt.RosterPortraitLabel("missing")
    framed_portrait.setFixedSize(120, 220)
    narrow_source = qt.QPixmap(60, 220)
    narrow_source.fill(qt.QColor("#b63f45"))
    framed_portrait.set_pixmap_source(narrow_source)
    rendered_portrait = qt.QPixmap(framed_portrait.size())
    rendered_portrait.fill(Qt.GlobalColor.transparent)
    framed_portrait.render(rendered_portrait)
    assert rendered_portrait.toImage().pixelColor(1, 110).name() == "#b63f45"

    with tempfile.TemporaryDirectory(prefix="ggc-roster-poc-") as directory, \
            patch("app.GuildGearChecker.now_iso", return_value="2026-09-22T12:00:00"):
        # Freeze the serialization timestamp so payload equality measures UI mutations.
        temp = Path(directory)
        for language in ("de", "en"):
            i18n._translator.language = language
            with patch.object(qt, "read_suite_settings", return_value={}), \
                    patch.object(qt, "app_base_dir", return_value=temp):
                window = RosterSmokeWindow()
            window._portrait_timer.stop()
            window._grabber_actions_timer.stop()
            window.show()
            app.processEvents()
            try:
                assert window.stack.currentWidget() is window._pages["rooster"]
                assert window._roster_presentation == "draft"
                assert window.roster_variant_buttons["draft"].isChecked()
                assert window.roster_variant_buttons["draft"].text() == ("Neu" if language == "de" else "New")
                assert window.roster_variant_buttons["classic"].text() == "Legacy"
                assert len(window.roster_content.findChildren(QFrame, "rosterDraftSection")) == 4
                assert len(window._roster_cards) == 6
                profile_page = window.player_profile_page
                assert profile_page.variant_stack.currentIndex() == 1
                assert profile_page.variant_buttons.button(1).isChecked()
                assert profile_page.variant_buttons.button(1).text() == ("Neu" if language == "de" else "New")
                assert profile_page.variant_buttons.button(0).text() == "Legacy"
                members = list(window.model.members)
                selected = members[0]
                selected.spec = "Protection"
                selected.lastChecked = "2026-09-20"
                window._clm_dkp_by_member_id[selected.id] = 123
                frame_path = window._reward_registry.frame_path("frame_01")
                rank_path = window._reward_registry.rank_path("Bronze_1", 96)
                assert frame_path and rank_path
                window._reward_assignments = RewardAssignments(
                    character_badges={selected.id: RewardAsset("Bronze_1", rank_path, 80)},
                    main_frames={selected.id: RewardAsset("frame_01", frame_path, 0)},
                )
                window.refresh_roster()
                window._roster_cards[0].clicked.emit(selected.id)
                window._refresh_visible_dkp_details()
                original_rank = window.roster_detail_rank.text()
                original_identity = window.roster_detail_class.text()
                window.roster_search_edit.setText("RosterBífi")
                window.roster_zoom_slider.setValue(60)
                window._roster_zoom_timer.stop()
                window._apply_roster_zoom()
                expected_ids = [card.member_id for card in window._roster_cards]
                before = copy.deepcopy(window.model.to_payload())
                list_widget = window.roster_list
                list_headers = [list_widget.horizontalHeaderItem(i).text() for i in range(10)]
                list_header = list_widget.horizontalHeader()
                assert all(
                    list_header.sectionResizeMode(column).name == "Interactive"
                    for column in range(list_widget.columnCount())
                )
                window.roster_list_button.click()
                app.processEvents()
                list_widget.setColumnWidth(0, 247)
                window.refresh_roster()
                assert list_widget.columnWidth(0) == 247
                window.roster_cards_button.click()
                app.processEvents()
                assert window.roster_selected_member_id == selected.id

                for variant in ("draft", "classic", "draft"):
                    window.roster_variant_buttons[variant].click()
                    app.processEvents()
                    window._reflow_roster_grids()
                    assert window.roster_zoom_slider.minimum() == (40 if variant == "draft" else 60)
                    assert window.roster_selected_member_id == selected.id
                    assert window._roster_zoom_percent == 60
                    assert window.roster_search_edit.text() == "RosterBífi"
                    assert [card.member_id for card in window._roster_cards] == expected_ids
                    assert window.model.to_payload() == before
                    assert window.roster_detail_panel.isVisible()
                    assert window.roster_detail_rank.text() == original_rank
                    assert window.roster_detail_class.text() == original_identity
                    assert window.roster_detail_checked.text() == selected.lastChecked
                    assert window.roster_current_dkp.text() == "123"
                    if variant == "draft":
                        detail_content = window.roster_detail_scroll.widget()
                        portrait_y = window.roster_reward_portrait.mapTo(detail_content, QPoint(0, 0)).y()
                        rank_y = window.roster_rank_slot.mapTo(detail_content, QPoint(0, 0)).y()
                        checked_y = window.roster_detail_checked.mapTo(detail_content, QPoint(0, 0)).y()
                        points_y = window.roster_points_section.mapTo(detail_content, QPoint(0, 0)).y()
                        assert window.roster_detail_name.alignment() & Qt.AlignmentFlag.AlignHCenter
                        assert window.roster_detail_rank.alignment() & Qt.AlignmentFlag.AlignHCenter
                        assert abs(portrait_y - rank_y) <= 24
                        assert portrait_y < checked_y
                        if window.roster_points_section.isVisible():
                            assert checked_y < points_y
                        assert window.roster_points_form.rowWrapPolicy() == QFormLayout.RowWrapPolicy.DontWrapRows
                        assert not window.roster_content.findChildren(QFrame, "rosterSection")
                        assert len(window.roster_content.findChildren(QFrame, "rosterDraftSection")) == 4
                        cards = {card.member_id: card for card in window._roster_cards}
                        card = cards[selected.id]
                        assert card.property("selected") is True
                        assert sum(bool(c.property("selected")) for c in cards.values()) == 1
                        assert type(card.portrait) is qt.CoverImageLabel
                        assert not window.roster_reward_portrait._frame_source.isNull()
                        assert not card.rank_icon.pixmap().isNull()
                        assert card.rank_icon.parentWidget() is card.name_label.parentWidget()
                        name_gap = card.name_label.x() - card.rank_icon.geometry().right() - 1
                        assert 0 <= name_gap <= 8
                        assert cards[members[2].id].status_badge.property("rosterStatus") == "neutral"
                        assert window.roster_detail_life.property("rosterStatus") == "positive"
                        assert window.roster_detail_raid.property("rosterStatus") == "positive"
                        QTest.qWait(220)  # Let the existing delayed grid reflows settle.
                        size = card.size()
                        QApplication.sendEvent(card, QEvent(QEvent.Type.Enter))
                        card.set_selected(False)
                        card.set_selected(True)
                        QApplication.sendEvent(card, QEvent(QEvent.Type.Leave))
                        app.processEvents()
                        assert card.size() == size, (size, card.size())  # No hover/selection geometry change.
                        assert card.name_label.font().pointSize() >= 10
                        assert card.name_label.alignment() & Qt.AlignmentFlag.AlignHCenter
                        assert card.status_badge.font().pointSize() >= 9
                        assert card.name_label.geometry().right() < card.name_label.parentWidget().width()
                        assert all(c.status_badge.width() <= c.card_width - 16 for c in cards.values())

                # Same selection and table survive switching between list/cards.
                window.roster_list_button.click()
                app.processEvents()
                assert window.roster_list is list_widget
                assert not window.roster_variant_controls.isVisible()
                assert window.roster_list.rowCount() == 6
                assert [list_widget.horizontalHeaderItem(i).text() for i in range(10)] == list_headers
                assert not window.roster_detail_panel.property("rosterDraft")
                window._roster_list_clicked(1)
                selected_id = window.roster_selected_member_id
                window.roster_cards_button.click()
                app.processEvents()
                assert window._roster_presentation == "draft"
                assert window.roster_selected_member_id == selected_id
                assert window.roster_detail_panel.property("rosterDraft")

                # Actual mouse selection routes the member ID through the card.
                card = next(c for c in window._roster_cards if c.member_id == selected.id)
                QTest.mouseClick(card.portrait, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
                assert window.roster_selected_member_id == selected.id
                with patch.object(window, "open_player_profile_for_member") as profile:
                    window.roster_profile_button.click()
                    profile.assert_called_once_with(selected.id)

                draft_card_objects = tuple(window._roster_cards)
                previous_columns = None
                for zoom in (140, 100, 40):
                    window.roster_zoom_slider.setValue(zoom)
                    window._roster_zoom_timer.stop()
                    window._apply_roster_zoom()
                    app.processEvents()
                    assert window._roster_zoom_percent == zoom
                    assert tuple(window._roster_cards) == draft_card_objects
                    assert window.roster_selected_member_id == selected.id
                    selected_card = next(
                        card for card in window._roster_cards if card.member_id == selected.id
                    )
                    assert selected_card.property("selected") is True
                    if zoom == 100:
                        assert selected_card.card_width == 194
                        assert selected_card.portrait.width() == 160
                        assert selected_card.portrait.height() == 216
                    if zoom == 40:
                        assert window.roster_zoom_slider.minimum() == 40
                        assert selected_card.card_width == 166
                        assert selected_card.portrait.width() == 108
                        assert selected_card.portrait.height() == 112
                        assert selected_card.name_label.wordWrap()
                        assert selected_card.details_label.wordWrap()
                        assert selected_card.status_badge.wordWrap()
                        assert selected_card.name_label.width() >= 110
                        assert selected_card.details_label.width() >= 100
                    for width, height in ((1040, 680), (1500, 920)):
                        window.resize(width, height)
                        app.processEvents()
                        window._reflow_roster_grids()
                        assert window.width() == width
                        assert window.roster_content.maximumWidth() == window.roster_scroll.viewport().width()
                        assert all(grid.width() >= grid.card_width for grid in window._roster_grids)
                        assert window.roster_detail_scroll.widget().minimumSizeHint().width() <= window.roster_detail_scroll.viewport().width(), (
                            window.roster_detail_scroll.widget().minimumSizeHint(),
                            window.roster_detail_scroll.viewport().size(),
                        )
                        assert window.roster_detail_scroll.verticalScrollBar().maximum() > 0
                        columns = max(grid._last_columns for grid in window._roster_grids)
                        if width == 1040:
                            narrow_columns = columns
                        else:
                            assert columns >= narrow_columns
                    current_columns = max(grid._last_columns for grid in window._roster_grids)
                    if previous_columns is not None:
                        assert current_columns >= previous_columns
                    previous_columns = current_columns

                # Opening and closing the existing detail only changes available
                # grid geometry; it does not rebuild cards or reload roster data.
                window.resize(1040, 680)
                app.processEvents()
                window._reflow_roster_grids()
                open_columns = max(grid._last_columns for grid in window._roster_grids)
                window._close_roster_detail()
                QTest.qWait(220)
                window._reflow_roster_grids()
                closed_columns = max(grid._last_columns for grid in window._roster_grids)
                assert closed_columns >= open_columns
                assert tuple(window._roster_cards) == draft_card_objects
                window._roster_card_clicked(selected.id)
                app.processEvents()
                window._reflow_roster_grids()
                assert window.roster_selected_member_id == selected.id
                assert tuple(window._roster_cards) == draft_card_objects

                # Empty filters preserve the selected character; closing clears
                # its highlight, and returning to classic restores its containers.
                window.roster_search_edit.setText("NothingMatches")
                app.processEvents()
                assert not window._roster_cards
                assert window.roster_selected_member_id == selected.id
                window.roster_search_edit.clear()
                window._close_roster_detail()
                assert not any(c.property("selected") for c in window._roster_cards)
                window._set_roster_presentation("classic")
                app.processEvents()
                assert len(window.roster_content.findChildren(QFrame, "rosterSection")) == 4
                assert not window.roster_detail_panel.isVisible()
                assert window.model.to_payload() == before
                with patch.object(qt.QFileDialog, "getSaveFileName", return_value=(str(temp / "roster.png"), "PNG")), \
                        patch.object(qt, "render_roster_png", return_value={"size": (100, 100)}) as renderer:
                    window.export_roster_png()
                    renderer.assert_called_once_with(window.model, temp / "roster.png")
                print(f"Qt Roster PoC Smoke ({language}): OK")
            finally:
                # Do not invoke closeEvent, which persists real window settings.
                window.hide()
                window.deleteLater()
                QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                app.processEvents()
    i18n._translator.language = old_language


if __name__ == "__main__":
    run()
