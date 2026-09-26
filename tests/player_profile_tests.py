# -*- coding: utf-8 -*-
"""Gezielte Tests für die read-only Spielerprofil-Grundlage."""
from __future__ import annotations

import os
import copy
from datetime import date, timedelta
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["GGC_DISABLE_ICON_DOWNLOAD"] = "1"

from app.GuildGearChecker import (
    GuildModel, POINT_MODE_ETERNAL, POINT_MODE_RAID, RaidAttendance,
)
from app.clm_history import EternalDkpRecord
from app.player_profile import active_player_options, build_player_profile


class PlayerProfileProjectionTests(unittest.TestCase):
    def setUp(self):
        self.model = GuildModel()
        self.model.new_empty()
        self.player = self.model.add_player("Technischer Spielername")
        self.main = self.model.add_member("Waltordin", "Test")
        self.twink = self.model.add_member("Tasgo", "Test")
        self.model.update_member_assignment(
            self.main.id, self.player.playerId, "main", "tank",
        )
        self.model.update_member_assignment(
            self.twink.id, self.player.playerId, "twink", "dps",
        )

    def profile(self, **kwargs):
        return build_player_profile(self.model, self.player.playerId, **kwargs)

    def test_profile_is_player_id_based_and_defaults_to_active_main(self):
        profile = self.profile()
        self.assertIsNotNone(profile)
        self.assertEqual(profile.player_id, self.player.playerId)
        self.assertEqual(profile.profile_name, self.main.name)
        self.assertEqual(profile.current_main_member_id, self.main.id)
        self.assertEqual(profile.selected_member_id, self.main.id)

    def test_character_change_keeps_player_identity(self):
        profile = self.profile(selected_member_id=self.twink.id)
        self.assertEqual(profile.player_id, self.player.playerId)
        self.assertEqual(profile.profile_name, self.main.name)
        self.assertEqual(profile.selected_member_id, self.twink.id)
        self.assertEqual(profile.selected_character.character_type, "twink")

    def test_inactive_and_missing_players_are_not_projected_or_listed(self):
        self.model.set_member_life_status(self.main.id, "inactive")
        self.model.set_member_life_status(self.twink.id, "inactive")
        self.assertIsNone(self.profile())
        self.assertNotIn(
            self.player.playerId,
            {player_id for _label, player_id in active_player_options(self.model)},
        )
        self.assertIsNone(build_player_profile(self.model, "p-does-not-exist"))

    def test_active_player_without_main_uses_active_twink_without_promoting_it(self):
        self.model.set_member_life_status(self.main.id, "inactive")
        profile = self.profile()
        self.assertIsNone(profile.current_main_member_id)
        self.assertIsNone(profile.profile_name)
        self.assertEqual(profile.selected_member_id, self.twink.id)
        self.assertEqual(profile.selected_character.character_type, "twink")

    def test_dead_and_inactive_characters_remain_selectable_by_member_id(self):
        dead = self.model.add_member("Janos", "Test")
        dead.playerId = self.player.playerId
        dead.characterType = "twink"
        dead.lifeStatus = "dead"
        dead.deathDate = "2026-09-20"
        inactive = self.model.add_member("Still", "Test")
        self.model.update_member_assignment(
            inactive.id, self.player.playerId, "twink", "dps",
        )
        self.model.set_member_life_status(inactive.id, "inactive")
        profile = self.profile(selected_member_id=dead.id)
        self.assertEqual(profile.selected_member_id, dead.id)
        self.assertEqual(
            {character.member_id for character in profile.characters},
            {self.main.id, self.twink.id, dead.id, inactive.id},
        )

    def test_player_and_character_statistics_stay_separate(self):
        first = self.model.create_raid("2026-09-01", "First")
        self.model.import_raid_attendance(first.id, [self.main.name])
        second = self.model.create_raid("2026-09-08", "Second")
        self.model.import_raid_attendance(second.id, [self.twink.name])
        points = (
            SimpleNamespace(
                player_id=self.player.playerId, member_id=self.main.id, total_points=10,
            ),
            SimpleNamespace(
                player_id=self.player.playerId, member_id=self.twink.id, total_points=20,
            ),
        )
        profile = self.profile(
            selected_member_id=self.twink.id,
            raid_point_entries=points,
            current_dkp_by_member_id={self.main.id: 12, self.twink.id: 8},
        )
        self.assertEqual(profile.attendance.total_attendances, 2)
        self.assertEqual(profile.selected_character.attendance.total_attendances, 1)
        self.assertEqual(profile.raid_points, 30)
        self.assertEqual(profile.selected_character.raid_points, 20)
        self.assertEqual(profile.current_dkp, 20)
        self.assertEqual(profile.selected_character.current_dkp, 8)

    def test_player_raid_count_deduplicates_main_and_twink_in_same_raid(self):
        raid = self.model.create_raid("2026-09-01", "Gemeinsam")
        raid.status = "recorded"
        for index, member in enumerate((self.main, self.twink)):
            self.model.raid_attendance.append(RaidAttendance(
                id=f"a_shared_{index}", raidId=raid.id,
                playerId=self.player.playerId, memberId=member.id,
                attendanceType=member.characterType,
                playerNameSnapshot=self.player.playerName,
                characterNameSnapshot=member.name, status="present",
            ))
        profile = self.profile()
        self.assertEqual(profile.raid_count, 1)
        self.assertEqual(profile.attendance.total_attendances, 1)
        self.assertEqual(
            {character.member_id: character.raid_count for character in profile.characters},
            {self.main.id: 1, self.twink.id: 1},
        )

    def test_same_name_incarnations_remain_distinct(self):
        historical = self.model.add_member("Bífi", "Test")
        historical.playerId = self.player.playerId
        historical.characterType = "twink"
        historical.lifeStatus = "dead"
        replacement = self.model.add_member("Bífi", "Test")
        self.model.update_member_assignment(
            replacement.id, self.player.playerId, "twink", "dps",
        )
        profile = self.profile(selected_member_id=historical.id)
        same_names = [
            character for character in profile.characters if character.name == "Bífi"
        ]
        self.assertEqual(len(same_names), 2)
        self.assertNotEqual(same_names[0].member_id, same_names[1].member_id)
        self.assertEqual(profile.selected_member_id, historical.id)

    def test_historical_member_uses_reconstructed_window_before_current_membership(self):
        model = GuildModel()
        model.new_empty()
        player = model.add_player("Mourdog-Spieler")
        historical = model.add_member("Mourdog", "Test")
        model.update_member_assignment(
            historical.id, player.playerId, "twink", "dps",
        )
        historical.lifeStatus = "dead"
        historical.deathDate = "2025-02-01"
        replacement = model.add_member("Mourdog", "Test")
        model.update_member_assignment(
            replacement.id, player.playerId, "main", "tank",
        )
        model.set_player_membership(player.playerId, "2026-04-24", None)
        start = date(2025, 1, 1)
        for index in range(21):
            raid = model.create_raid(
                (start + timedelta(days=index)).isoformat(), f"Historisch {index + 1}",
            )
            raid.status = "recorded"
            model.raid_attendance.append(RaidAttendance(
                id=f"a_historical_{index}", raidId=raid.id,
                playerId=player.playerId, memberId=historical.id,
                attendanceType="twink", playerNameSnapshot=player.playerName,
                characterNameSnapshot=historical.name,
                status="bench" if index == 20 else "present",
            ))
        model.eternal_dkp.records.append(EternalDkpRecord(
            event_id="mourdog-eternal", member_id=historical.id,
            character_name=historical.name, value=448, kind="EARNED_RAID",
            raid_id=model.raids[0].id,
        ))
        profile = build_player_profile(
            model, player.playerId, selected_member_id=historical.id,
        )
        character = profile.selected_character
        self.assertEqual(character.member_id, historical.id)
        self.assertEqual(character.raid_count, 21)
        self.assertEqual(len(character.attended_raid_ids), 21)
        self.assertEqual(character.attendance.total_attendances, 21)
        self.assertEqual(character.attendance.bench_attendances, 1)
        self.assertEqual(character.attendance.attendance_percent, 100)
        self.assertEqual(character.eternal_dkp, 448)
        self.assertEqual(profile.raid_count, 21)
        self.assertEqual(profile.attendance.total_attendances, 21)
        same_names = [item for item in profile.characters if item.name == "Mourdog"]
        self.assertEqual({item.member_id for item in same_names}, {
            historical.id, replacement.id,
        })


class PlayerProfileQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from app.GuildGearCheckerQt import GuildGearCheckerQt

        class Window(GuildGearCheckerQt):
            def _load_autosave_or_seed(inner_self):
                inner_self.model.new_empty()
                inner_self.player = inner_self.model.add_player("Profilspieler")
                inner_self.main = inner_self.model.add_member("Mainprofil", "Test")
                inner_self.twink = inner_self.model.add_member("Twinkprofil", "Test")
                inner_self.model.update_member_assignment(
                    inner_self.main.id, inner_self.player.playerId, "main", "tank",
                )
                inner_self.model.update_member_assignment(
                    inner_self.twink.id, inner_self.player.playerId, "twink", "dps",
                )

            def _apply_character_cache_once(inner_self):
                return

            def autosave(inner_self):
                return

        settings_write = patch("app.GuildGearCheckerQt.update_suite_settings")
        settings_write.start()
        self.addCleanup(settings_write.stop)
        with patch("app.GuildGearCheckerQt.read_suite_settings", return_value={}):
            self.window = Window()
        self.addCleanup(self.window.close)

    def test_new_profile_keeps_projection_selection_and_raid_rows(self):
        from PySide6.QtCore import Qt
        main_raid = self.window.model.create_raid("2026-09-01", "Mainraid")
        self.window.model.import_raid_attendance(main_raid.id, [self.window.main.name])
        twink_raid = self.window.model.create_raid("2026-09-08", "Twinkraid")
        self.window.model.import_raid_attendance(twink_raid.id, [self.window.twink.name])
        self.window.open_player_profile(self.window.player.playerId)
        page = self.window.player_profile_page
        draft = page.draft_page
        self.assertFalse(hasattr(page, "variant_stack"))
        self.assertFalse(hasattr(page, "variant_buttons"))
        self.assertIs(page.layout().itemAt(0).widget(), draft)
        self.window._build_player_profile = Mock(side_effect=AssertionError("No reload on character switch"))
        self.window._clm_refresh_service.refresh = Mock(side_effect=AssertionError("No CLM refresh"))
        header = draft.character_raid_table.horizontalHeader()
        self.assertTrue(all(
            header.sectionResizeMode(column).name == "Interactive"
            for column in range(draft.character_raid_table.columnCount())
        ))
        draft.character_raid_table.setColumnWidth(1, 444)
        draft.character_raid_table.setCurrentCell(0, 0)
        self.assertEqual(
            draft.character_raid_table.currentItem().data(Qt.ItemDataRole.UserRole),
            main_raid.id,
        )
        draft.family_buttons[self.window.twink.id].click()
        self.assertEqual(self.window._player_profile.player_id, self.window.player.playerId)
        self.assertEqual(self.window._player_profile.selected_member_id, self.window.twink.id)
        self.assertEqual(draft.character_combo.currentData(), self.window.twink.id)
        self.assertEqual(draft.character_raid_table.item(0, 1).text(), "Twinkraid")
        self.assertEqual(draft.character_raid_table.columnWidth(1), 444)
        self.window._build_player_profile.assert_not_called()
        self.window._clm_refresh_service.refresh.assert_not_called()
        self.window.close_player_profile()
        self.assertIs(self.window.stack.currentWidget(), self.window._pages["rooster"])

    def test_draft_raids_are_beside_details_and_portrait_fits_all_frames(self):
        from PySide6.QtCore import QPoint, QSize
        from PySide6.QtGui import QPixmap
        from app.rewards import FRAME_OPENING_RECTS
        self.window.open_player_profile(self.window.player.playerId)
        page = self.window.player_profile_page
        draft = page.draft_page
        self.window.resize(1040, 1050)
        self.window.show()
        self.app.processEvents()
        table_pos = draft.character_raid_table.mapTo(draft, QPoint(0, 0))
        info_pos = draft.character_name.mapTo(draft, QPoint(0, 0))
        self.assertGreater(table_pos.x(), info_pos.x() + draft.character_name.width())
        self.assertLess(abs(table_pos.y() - info_pos.y()), 60)
        portrait = draft.player_portrait
        for asset_id, opening in FRAME_OPENING_RECTS.items():
            path = ROOT / "assets/rewards/portrait_frames" / f"{asset_id}.png"
            self.assertTrue(path.is_file())
            draft.player_reward_portrait.set_reward_frame(path, opening)
            frame, outer, inner = portrait.frame_geometry()
            self.assertFalse(frame.isNull())
            self.assertTrue(outer.contains(inner))
            for width, height in ((400, 800), (800, 400), (500, 500), (60, 1000)):
                portrait.set_pixmap_source(QPixmap(width, height))
                target = portrait.portrait_target_rect(inner)
                self.assertTrue(inner.contains(target))
                self.assertLessEqual(abs(target.width() * height - target.height() * width), max(width, height))
                self.assertEqual(draft.player_reward_portrait.size(), QSize(180, 260))
        draft.player_reward_portrait.clear_reward_frame()
        self.assertEqual(portrait.frame_geometry()[2], portrait.contentsRect())

    def test_draft_family_includes_inactive_and_dead_without_promotion(self):
        self.window.main.className = "Warrior"
        self.window.twink.lifeStatus = "dead"
        inactive = self.window.model.add_member("Inaktiv", "Test")
        inactive.playerId = self.window.player.playerId
        inactive.characterType = "twink"
        inactive.lifeStatus = "inactive"
        self.window.open_player_profile(self.window.player.playerId)
        draft = self.window.player_profile_page.draft_page
        self.assertEqual(set(draft.family_buttons), {self.window.main.id, self.window.twink.id, inactive.id})
        draft.family_buttons[self.window.twink.id].click()
        self.assertEqual(self.window._player_profile.selected_character.life_status, "dead")
        self.assertTrue(draft.player_reward_portrait._frame_source.isNull())
        self.assertEqual(self.window._player_profile.current_main_member_id, self.window.main.id)
        self.assertIn(self.window.main.name, draft.main_caption.text())

    def test_twink_entry_opens_profile_at_current_main_without_refresh_or_rebuild(self):
        self.window._clm_refresh_service.refresh = Mock(
            side_effect=AssertionError("CLM refresh must not run"),
        )
        self.window._rebuild_raid_derived_state = Mock(
            side_effect=AssertionError("Raid-point rebuild must not run"),
        )
        self.assertTrue(self.window.open_player_profile_for_member(self.window.twink.id))
        self.assertEqual(self.window._player_profile.player_id, self.window.player.playerId)
        self.assertEqual(self.window._player_profile.selected_member_id, self.window.main.id)
        self.assertIs(
            self.window.stack.currentWidget(), self.window.player_profile_page,
        )
        self.window._clm_refresh_service.refresh.assert_not_called()
        self.window._rebuild_raid_derived_state.assert_not_called()

    def test_character_switch_keeps_player_id_and_invalid_players_do_not_open(self):
        self.assertTrue(self.window.open_player_profile(self.window.player.playerId))
        original_player_id = self.window._player_profile.player_id
        self.window._build_player_profile = Mock(
            side_effect=AssertionError("Character switch must reuse the profile projection"),
        )
        self.window._select_profile_character(self.window.twink.id)
        self.assertEqual(self.window._player_profile.player_id, original_player_id)
        self.assertEqual(self.window._player_profile.selected_member_id, self.window.twink.id)
        self.assertFalse(self.window.open_player_profile("missing"))
        self.assertEqual(self.window._player_profile.player_id, original_player_id)

    def test_active_player_without_main_opens_but_inactive_player_does_not(self):
        self.window.model.set_member_life_status(self.window.main.id, "inactive")
        self.assertTrue(self.window.open_player_profile(self.window.player.playerId))
        self.assertIsNone(self.window._player_profile.current_main_member_id)
        self.assertEqual(self.window._player_profile.selected_member_id, self.window.twink.id)
        self.assertEqual(
            self.window._player_profile.selected_character.character_type, "twink",
        )
        self.window.close_player_profile()
        self.window.model.set_member_life_status(self.window.twink.id, "inactive")
        previous = self.window.stack.currentWidget()
        self.assertFalse(self.window.open_player_profile(self.window.player.playerId))
        self.assertIs(self.window.stack.currentWidget(), previous)

    def test_profile_layout_uses_one_selected_point_system_and_no_membership_since(self):
        self.window.main.race = "Human"
        self.window.main.className = "Warrior"
        raid = self.window.model.create_raid("2026-09-01", "Testraid")
        self.window.model.import_raid_attendance(raid.id, [self.window.main.name])
        self.window.model.point_mode = POINT_MODE_RAID
        self.window.model.raid_points.enabled = True
        self.assertTrue(self.window.open_player_profile(self.window.player.playerId))
        page = self.window.player_profile_page
        self.assertNotIn("player_since", vars(page))
        self.assertNotIn("character_portrait", vars(page))
        self.assertNotIn("points", page.player_metric_labels)
        self.assertNotIn("streak", page.player_metric_labels)
        self.assertIn("player_rank", page.player_metric_labels)
        self.assertEqual(page.character_identity_line.text(), "Mensch – Krieger")
        self.assertEqual(page.player_metric_labels["raids"].text(), "1")
        self.assertEqual(page.character_raid_table.rowCount(), 1)
        self.assertEqual(page.character_raid_table.item(0, 1).text(), "Testraid")
        self.assertEqual(
            page.character_details_form.labelForField(
                page.character_metric_labels["points"]
            ).text(),
            "Raidpunkte",
        )
        self.assertEqual(page.character_raid_table.horizontalHeaderItem(3).text(), "Raidpunkte")
        self.assertFalse(page.character_metric_labels["points"].parentWidget().isHidden())
        self.window.model.point_mode = POINT_MODE_ETERNAL
        self.window.model.dkp_enabled = True
        self.window._render_player_profile(self.window._build_player_profile(self.window.player.playerId))
        self.assertEqual(
            page.character_details_form.labelForField(
                page.character_metric_labels["points"]
            ).text(),
            "DKP",
        )
        self.assertEqual(page.character_raid_table.horizontalHeaderItem(3).text(), "DKP")
        self.assertFalse(page.character_metric_labels["points"].parentWidget().isHidden())

    def test_character_navigation_is_stable_and_non_cyclic(self):
        self.assertTrue(self.window.open_player_profile(self.window.player.playerId))
        page = self.window.player_profile_page
        player_values = {
            key: label.text() for key, label in page.player_metric_labels.items()
        }
        player_rank = page.player_metric_labels["player_rank"].text()
        shared_portrait = page.player_portrait
        self.assertFalse(page.character_previous_button.isEnabled())
        self.assertTrue(page.character_next_button.isEnabled())
        self.window._select_next_profile_character()
        self.assertEqual(self.window._player_profile.selected_member_id, self.window.twink.id)
        self.assertIs(page.player_portrait, shared_portrait)
        self.assertEqual(
            {key: label.text() for key, label in page.player_metric_labels.items()},
            player_values,
        )
        self.assertEqual(page.player_metric_labels["player_rank"].text(), player_rank)
        self.assertTrue(page.character_previous_button.isEnabled())
        self.assertFalse(page.character_next_button.isEnabled())
        self.window._select_next_profile_character()
        self.assertEqual(self.window._player_profile.selected_member_id, self.window.twink.id)
        self.window._select_previous_profile_character()
        self.assertEqual(self.window._player_profile.selected_member_id, self.window.main.id)

    def test_character_raid_list_follows_selected_member_without_changing_player(self):
        main_raid = self.window.model.create_raid("2026-09-01", "Mainraid")
        self.window.model.import_raid_attendance(main_raid.id, [self.window.main.name])
        twink_raid = self.window.model.create_raid("2026-09-08", "Twinkraid")
        self.window.model.import_raid_attendance(twink_raid.id, [self.window.twink.name])
        self.assertTrue(self.window.open_player_profile(self.window.player.playerId))
        page = self.window.player_profile_page
        self.assertEqual(page.character_raid_table.item(0, 1).text(), "Mainraid")
        player_id = self.window._player_profile.player_id
        self.window._select_next_profile_character()
        self.assertEqual(self.window._player_profile.player_id, player_id)
        self.assertEqual(page.character_raid_table.item(0, 1).text(), "Twinkraid")

    def test_character_raid_count_and_table_deduplicate_one_raid_id(self):
        raid = self.window.model.create_raid("2026-09-01", "Einmal")
        self.window.model.import_raid_attendance(raid.id, [self.window.main.name])
        duplicate = copy.copy(self.window.model.raid_attendance[0])
        duplicate.id = "a_duplicate_for_profile_test"
        self.window.model.raid_attendance.append(duplicate)
        self.assertTrue(self.window.open_player_profile(self.window.player.playerId))
        page = self.window.player_profile_page
        self.assertEqual(page.character_metric_labels["raids"].text(), "1")
        self.assertEqual(page.character_raid_table.rowCount(), 1)
        self.assertEqual(page.character_raid_table.item(0, 1).text(), "Einmal")

    def test_dead_selected_character_reuses_the_shared_gravestone_surface(self):
        self.window.twink.lifeStatus = "dead"
        self.window.twink.deathDate = "2026-09-20"
        self.assertTrue(self.window.open_player_profile(self.window.player.playerId))
        page = self.window.player_profile_page
        self.window._select_next_profile_character()
        self.assertEqual(self.window._player_profile.selected_member_id, self.window.twink.id)
        self.assertEqual(self.window._player_profile.selected_character.life_status, "dead")
        self.assertTrue(page.player_reward_portrait._frame_source.isNull())


if __name__ == "__main__":
    unittest.main(verbosity=2)
