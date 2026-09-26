"""Gezielter Offscreen-Smoke für Qt-Projekt-, Portrait- und Worker-Grundworkflow."""
from __future__ import annotations

import json
import os
import queue
import sys
import tempfile
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHeaderView, QMessageBox
from PIL import Image

from app import i18n as suite_i18n
from app.GuildGearChecker import (
    GRAVESTONE_CARD_SIZE,
    GuildModel,
    detect_gravestone_portrait_opening,
    prepare_gravestone_template,
    render_gravestone_card,
    shifted_portrait_offsets,
    shifted_text_offsets,
)
from app.gravestone_categories import GRAVESTONE_CATEGORIES
from app.GuildPortraitGrabberQt import (
    APP_VERSION,
    GuildPortraitGrabberQt,
    create_application,
)
from app.GuildPortraitGrabber import (
    build_armory_url,
    graveyard_portrait_for_member,
    graveyard_portrait_placeholder_path,
    load_portrait_editor_state,
    normal_portrait_path,
    portrait_editor_pan,
    render_portrait_editor_image,
    portrait_editor_transform,
    portrait_editor_zoom,
)
from tools.gravestone_review.gravestone_review_qt import QtGravestoneReviewWidget


class FakeWorker:
    def __init__(self, events: queue.Queue) -> None:
        self.events = events
        self.commands: list[tuple[str, dict]] = []
        self.started = False
        self.cancel_requested = False
        self.cancel_request_count = 0

    def start(self) -> None:
        self.started = True

    def submit(self, action: str, **payload) -> None:
        self.commands.append((action, payload))

    def request_batch_cancel(self) -> None:
        self.cancel_requested = True
        self.cancel_request_count += 1


workers: list[FakeWorker] = []


def fake_worker_factory(events: queue.Queue) -> FakeWorker:
    worker = FakeWorker(events)
    workers.append(worker)
    return worker


TEST_CONFIG = {
    "region": "EU",
    "realm": "stitches",
    "game_version": "classic1x",
    "browser_channel": "msedge",
    "wait_after_load": 1.25,
    "capture_mode": "playwright",
    "standard_wait_after_open": 6.0,
    "screen_region": {"x": 10, "y": 20, "width": 300, "height": 525},
    "crop": {"x1": 0.2, "y1": 0.1, "x2": 0.8, "y2": 0.9},
}


def assert_plain_payload(value) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str)
            assert_plain_payload(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            assert_plain_payload(item)
        return
    assert value is None or isinstance(value, (str, int, float, bool))


assert APP_VERSION == "0.12.0"
application = QApplication.instance() or QApplication([])
reused_application, owns_application = create_application([])
assert reused_application is application
assert not owns_application

old_language = suite_i18n._translator.language
try:
    suite_i18n._translator.language = "de"
    empty_window = GuildPortraitGrabberQt(
        worker_factory=fake_worker_factory, config_data=TEST_CONFIG,
    )
    empty_window.show()
    application.processEvents()
    assert empty_window.project_status_label.text() == "Kein Projekt geladen"
    assert empty_window.tabs.tabText(0) == "Portraits"
    assert empty_window.tabs.tabText(1) == "Friedhof"
    assert empty_window.tabs.tabText(2) == "Einstellungen"
    assert empty_window.tabs.tabText(3) == "Grabstein Review"
    assert empty_window.tabs.widget(2).objectName() == "settingsPage"
    assert empty_window.tabs.currentWidget() is empty_window.portraits_page
    assert empty_window.crop_settings_group.title() == "Aufnahme & Ausschnitt"
    assert empty_window.playwright_crop_group.parent() is empty_window.crop_settings_group
    assert empty_window.standard_crop_group.parent() is empty_window.crop_settings_group
    assert empty_window.banner.version_text == "v0.12.0"
    assert "DEV" not in empty_window.windowTitle()
    assert not empty_window.banner._source.isNull()
    assert empty_window.checker_navigation_button.text() == "Im Gearchecker öffnen"
    with patch("app.GuildPortraitGrabberQt.subprocess.Popen") as launched, \
            patch.object(empty_window, "close") as closed:
        empty_window._navigate_to_checker()
    launched.assert_called_once()
    assert Path(launched.call_args.args[0][1]).name == "GuildGearCheckerQt.py"
    assert Path(launched.call_args.kwargs["cwd"]).resolve() == ROOT.resolve()
    closed.assert_called_once()
    assert empty_window.roster_actions_group.title() == "Gildenliste"
    assert empty_window.batch_actions_group.title() == "Batch"
    assert empty_window.character_actions_group.title() == "Charakter"
    assert empty_window.portrait_actions_group.title() == "Portraitaktionen"
    assert empty_window.roster_actions_group.parent() is empty_window.top_actions_row
    assert empty_window.batch_actions_group.parent() is empty_window.top_actions_row
    assert empty_window.roster_actions_group.y() == empty_window.batch_actions_group.y()
    assert empty_window.character_actions_group.parent() is not empty_window.top_actions_row
    assert empty_window.portrait_actions_group.parent() is not empty_window.top_actions_row
    assert empty_window.import_wcl_button.isHidden()
    assert empty_window.batch_progress_panel.isHidden()
    assert empty_window.character_splitter.sizes()[0] > empty_window.character_splitter.sizes()[1]
    assert empty_window.character_table.horizontalHeader().sectionResizeMode(0) == (
        QHeaderView.ResizeMode.Interactive
    )
    assert empty_window.character_table.horizontalHeader().sectionResizeMode(4) == (
        QHeaderView.ResizeMode.Stretch
    )
    assert empty_window.character_spec_value.parent() is None
    assert empty_window.armory_url_label.parent() is empty_window.character_detail_frame
    for button in (
        empty_window.open_browser_button,
        empty_window.read_armory_button,
        empty_window.capture_portrait_button,
        empty_window.import_portrait_button,
        empty_window.edit_portrait_button,
        empty_window.remove_portrait_button,
    ):
        assert button.width() >= button.sizeHint().width(), (
            button.objectName(), button.width(), button.sizeHint().width()
        )
    empty_window.resize(1500, 900)
    application.processEvents()
    assert empty_window.character_actions_group.y() == empty_window.portrait_actions_group.y()
    assert empty_window.character_actions_group.x() < empty_window.portrait_actions_group.x()
    empty_window.resize(1050, 760)
    application.processEvents()
    assert empty_window.region_edit.text() == "EU"
    assert empty_window.realm_edit.text() == "stitches"
    assert empty_window.game_version_edit.text() == "classic1x"
    assert empty_window.capture_mode_combo.currentText() == "Playwright / v0.1.2"
    assert empty_window.standard_wait_spin.value() == 6.0
    assert empty_window.browser_test_button.isEnabled()
    assert not empty_window.calibrate_crop_button.isEnabled()
    assert isinstance(empty_window.review_page, QtGravestoneReviewWidget)
    assert empty_window.tabs.tabText(empty_window.tabs.indexOf(empty_window.review_page)) == "Grabstein Review"
    assert empty_window.graveyard_model.rowCount() == 0
    assert empty_window.selected_graveyard_member_id is None
    assert not empty_window.open_selected_in_browser()
    assert not empty_window.read_selected_armory_data()
    assert not empty_window.capture_selected_portrait()
    empty_window.tabs.setCurrentIndex(empty_window.tabs.indexOf(empty_window.settings_page))
    assert empty_window.config_data["qt_main_tab"] == "settings"
    empty_window.statusBar().showMessage("Temporärer Status")
    assert empty_window.statusBar().isVisible()
    empty_window.statusBar().clearMessage()
    assert not empty_window.statusBar().isVisible()
    empty_window.setGeometry(42, 54, 1100, 800)
    empty_window.character_splitter.setSizes([640, 360])
    empty_window.character_table.setColumnWidth(0, 260)
    empty_window._save_window_state()
    assert empty_window.config_data["qt_window_geometry"] == {
        "x": 42, "y": 54, "width": 1100, "height": 800,
    }
    saved_splitter_sizes = empty_window.config_data["qt_portraits_splitter_sizes"]
    assert len(saved_splitter_sizes) == 2
    assert saved_splitter_sizes[0] > saved_splitter_sizes[1]
    assert empty_window.config_data["qt_portraits_column_widths"][0] == 260

    restored_config = dict(TEST_CONFIG)
    restored_config["qt_main_tab"] = "Ausschnitt"
    restored_config["qt_window_geometry"] = {
        "x": 999999, "y": 999999, "width": 1100, "height": 800,
    }
    restored_config["qt_portraits_splitter_sizes"] = saved_splitter_sizes
    restored_config["qt_portraits_column_widths"] = [260, 135, 155, 100, 135]
    restored_window = GuildPortraitGrabberQt(
        worker_factory=fake_worker_factory, config_data=restored_config,
    )
    restored_window.show()
    application.processEvents()
    assert restored_window.tabs.currentWidget() is restored_window.settings_page
    assert restored_window.geometry().intersects(
        application.primaryScreen().availableGeometry()
    )
    restored_window.tabs.setCurrentIndex(
        restored_window.tabs.indexOf(restored_window.portraits_page)
    )
    application.processEvents()
    assert restored_window.character_splitter.sizes()[0] > restored_window.character_splitter.sizes()[1]
    assert restored_window.character_table.columnWidth(0) == 260
    restored_window.close()
    restored_window.deleteLater()
    application.processEvents()
    assert not empty_window.capture_portrait_button.isEnabled()
    assert not empty_window.import_portrait_button.isEnabled()
    assert not empty_window.remove_portrait_button.isEnabled()
    assert not empty_window.edit_portrait_button.isEnabled()
    assert not [command for command in workers[-1].commands if command[0] != "stop"]
    empty_window.close()
    empty_window.deleteLater()
    application.processEvents()
    assert not empty_window.isVisible()
    assert workers[-1].cancel_requested
    assert workers[-1].commands[-1][0] == "stop"

    with tempfile.TemporaryDirectory(prefix="ggc-qt-grabber-") as temp_dir:
        temp_root = Path(temp_dir)
        project = temp_root / "Phase31.ggc"
        inventory = GuildModel().gravestone_inventory()
        assert inventory.templates
        graveyard_template = inventory.templates[0]
        occupied_graveyard_template = inventory.templates[1]
        project.write_text(
            json.dumps({
                "formatVersion": 4,
                "members": [
                    {
                        "id": "m1001", "name": "Ánníe", "race": "Human",
                        "className": "Mage", "spec": "Frost", "lifeStatus": "active",
                    },
                    {
                        "id": "m1002", "name": "Bífi", "race": "Dwarf",
                        "className": "Warrior", "spec": "Fury", "lifeStatus": "active",
                        "graveTemplateId": occupied_graveyard_template.grave_template_id,
                        "gravestoneTemplate": occupied_graveyard_template.filename,
                    },
                    {
                        "id": "m1007", "name": "Inaktiv", "race": "Human",
                        "className": "Warrior", "spec": "Arms", "lifeStatus": "inactive",
                    },
                    {
                        "id": "m1004", "name": "Ohnebild", "race": "Human",
                        "className": "Rogue", "spec": "Combat", "lifeStatus": "active",
                    },
                    {
                        "id": "m1003", "name": "Altgrab", "className": "Priest",
                        "lifeStatus": "dead", "deathDate": "2026-09-01",
                        "graveTemplateId": graveyard_template.grave_template_id,
                        "gravestoneTemplate": graveyard_template.filename,
                        "portraitOffsetX": 0.25, "portraitOffsetY": -0.20,
                        "portraitZoom": 1.35,
                        "textOffsetX": 0.15, "textOffsetY": -0.10,
                        "textScale": 1.10,
                    },
                    {
                        "id": "m1005", "name": "Fehlstein", "className": "Mage",
                        "lifeStatus": "dead", "deathDate": "2026-09-02",
                        "graveTemplateId": "grave-template-fehlt",
                        "gravestoneTemplate": "gravestone_fehlend.png",
                    },
                    {
                        "id": "m1006", "name": "Ohnegrab", "className": "Rogue",
                        "lifeStatus": "dead", "deathDate": "2026-09-03",
                    },
                ],
                "guildName": "Phase 3.2",
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        annie_portrait = normal_portrait_path("Ánníe", project)
        annie_portrait.parent.mkdir(parents=True, exist_ok=True)
        portrait_pattern = Image.new("RGB", (384, 672))
        for x in range(portrait_pattern.width):
            portrait_pattern.paste(
                (x % 256, (x * 3) % 256, (255 - x) % 256),
                (x, 0, x + 1, portrait_pattern.height),
            )
        portrait_pattern.save(annie_portrait)
        invalid_portrait = normal_portrait_path("Bífi", project)
        invalid_portrait.write_bytes(b"kein gueltiges PNG")
        history_portrait_altgrab = annie_portrait.parent / "history" / "m1003.png"
        history_portrait_altgrab.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (80, 120), (70, 40, 20)).save(history_portrait_altgrab)

        window = GuildPortraitGrabberQt(
            project,
            session_id="phase31-session",
            worker_factory=fake_worker_factory,
            config_data=TEST_CONFIG,
        )
        window.show()
        application.processEvents()
        assert window.project_path == project.resolve(), window.project_error
        assert window.project_payload is not None
        assert window.session_id == "phase31-session"
        assert window.handoff_path == (
            project.parent / "runtime" / "Phase31_handoff"
        ).resolve()
        assert window.project_status_label.text() == "Projekt: Phase31.ggc"
        assert str(project.resolve()) == window.project_detail_label.text()
        assert window.banner.project_text == "Phase31.ggc"
        assert window.banner.toolTip() == str(project.resolve())
        assert window.checker_navigation_button.text() == "Zurück zum Gearchecker"
        with patch("app.GuildPortraitGrabberQt.subprocess.Popen") as launched, \
                patch.object(window, "close") as closed:
            window._navigate_to_checker()
        launched.assert_not_called()
        closed.assert_called_once()
        assert window.open_project_button.text() == "Projekt öffnen…"
        assert window.character_model.rowCount() == 3
        assert window._portrait_list_mode == "active"
        assert window.active_portraits_button.isChecked()
        assert [member.id for member in window.character_members] == [
            "m1002", "m1004", "m1001",
        ]
        assert [member.id for member in window.inactive_character_members] == ["m1007"]
        assert "m1007" in window._member_by_id

        # Inaktive besitzen eine eigene Portraitliste mit denselben Portrait-/Batchaktionen.
        window.inactive_portraits_button.click()
        application.processEvents()
        assert window._portrait_list_mode == "inactive"
        assert window.character_model.rowCount() == 1
        assert [member.id for member in window.character_members] == ["m1007"]
        assert window.character_model.item(0, 3).text() == "Inaktiv"
        assert window.open_browser_button.isEnabled()
        assert window.capture_portrait_button.isEnabled()
        assert window.read_armory_button.isEnabled()
        assert window.capture_missing_button.isEnabled()
        assert window.capture_all_button.isEnabled()
        # Gildenlisten-Mutationen bleiben auf die aktive Arbeitsliste begrenzt.
        assert not window.add_character_button.isEnabled()
        assert not window.import_list_button.isEnabled()
        assert not window.save_guild_list_button.isEnabled()
        window.active_portraits_button.click()
        application.processEvents()
        assert window._portrait_list_mode == "active"
        assert window.character_model.rowCount() == 3
        assert [member.id for member in window.graveyard_members] == [
            "m1003", "m1005", "m1006",
        ]
        assert window.graveyard_model.rowCount() == 3
        assert window.graveyard_table.editTriggers().value == 0
        assert window.selected_graveyard_member_id in {"m1003", "m1005", "m1006"}
        altgrab_row = next(
            row for row in range(window.graveyard_model.rowCount())
            if window.graveyard_model.item(row, 0).text() == "Altgrab"
        )
        window.graveyard_table.selectRow(altgrab_row)
        application.processEvents()
        assert window.selected_graveyard_member_id == "m1003"
        assert window.graveyard_name_value.text() == "Altgrab"
        assert window.graveyard_death_value.text() == "2026-09-01"
        assert not hasattr(window, "graveyard_portrait_preview")
        assert not hasattr(window, "graveyard_stone_preview")
        with patch(
            "app.GuildPortraitGrabberQt.render_gravestone_card",
            wraps=render_gravestone_card,
        ) as shared_renderer:
            window.show_graveyard_member("m1003")
        assert shared_renderer.call_count == 1
        assert shared_renderer.call_args.args[0].portraitZoom == 1.35
        assert shared_renderer.call_args.args[0].portraitOffsetX == 0.25
        assert shared_renderer.call_args.args[0].textScale == 1.10
        assert shared_renderer.call_args.args[2] == normal_portrait_path("m1003", project)
        assert window.graveyard_preview.pixmap() is not None
        assert not window.graveyard_preview.pixmap().isNull()
        assert window.graveyard_stone_value.text() == graveyard_template.filename
        assert window.graveyard_category_value.text() != "Nicht gesetzt"
        assert window.graveyard_import_portrait_button.isEnabled()
        assert window.graveyard_edit_portrait_button.isEnabled()

        # Tote verwenden denselben Pan/Zoom/Crop-Editor, aber immer auf der stabilen
        # memberId-Datei dieser konkreten Inkarnation.
        assert window.edit_selected_graveyard_portrait()
        application.processEvents()
        dead_portrait_editor = window._portrait_editor_dialog
        assert dead_portrait_editor is not None and dead_portrait_editor.isVisible()
        assert dead_portrait_editor.character_name == "Altgrab"
        assert dead_portrait_editor.destination == normal_portrait_path("m1003", project)
        assert dead_portrait_editor.pan_mode_button.isChecked()
        assert dead_portrait_editor.crop_mode_button.isEnabled()
        dead_portrait_editor.reject()
        application.processEvents()

        # Phase 6.4b: Die normale Detailansicht ist wieder rein lesend. Sämtliche
        # Kandidatenwahl liegt ausschließlich im Unified Gravestone Editor.
        for removed_control in (
            "graveyard_category_filter_combo",
            "graveyard_template_combo",
            "graveyard_previous_stone_button",
            "graveyard_next_stone_button",
            "graveyard_apply_stone_button",
            "graveyard_preview_notice_label",
        ):
            assert not hasattr(window, removed_control)
        assert window.graveyard_edit_stone_button.isEnabled()
        _inventory, available = window.project_model.available_gravestone_templates(
            "m1003"
        )
        available_by_id = {
            template.grave_template_id: template for template in available
        }
        all_available_ids = list(available_by_id)
        assert graveyard_template.grave_template_id in all_available_ids
        assert occupied_graveyard_template.grave_template_id not in all_available_ids
        current_category = graveyard_template.category
        category_ids = [
            template_id for template_id, template in available_by_id.items()
            if template.category == current_category
        ]
        assert len(category_ids) > 2
        replacement_id = category_ids[1]
        replacement = available_by_id[replacement_id]
        old_template_id = graveyard_template.grave_template_id

        # Der Unified Editor beginnt stets beim gespeicherten Zustand. Erst seine
        # interne Auswahl wechselt den flüchtigen Draft auf einen Kandidaten.
        project_before_editor = project.read_bytes()
        with patch(
            "app.GuildPortraitGrabberQt.render_gravestone_card",
            wraps=render_gravestone_card,
        ) as shared_renderer:
            assert window.open_selected_gravestone_editor()
            application.processEvents()
        gravestone_editor = window._gravestone_editor_dialog
        assert gravestone_editor is not None and gravestone_editor.isVisible()
        assert gravestone_editor.state.saved.template_id == old_template_id
        assert gravestone_editor.state.draft.template_id == old_template_id
        assert gravestone_editor.state.saved.portrait_offset_x == 0.25
        assert gravestone_editor.state.saved.portrait_offset_y == -0.20
        assert gravestone_editor.state.saved.portrait_zoom == 1.35
        filter_values = [
            gravestone_editor.category_filter_combo.itemData(index)
            for index in range(gravestone_editor.category_filter_combo.count())
        ]
        assert filter_values == ["__all__", *GRAVESTONE_CATEGORIES]
        assert "__uncategorized__" not in filter_values
        assert gravestone_editor.candidate_ids == all_available_ids
        assert occupied_graveyard_template.grave_template_id not in (
            gravestone_editor.candidate_ids
        )
        gravestone_editor.category_filter_combo.setCurrentIndex(
            gravestone_editor.category_filter_combo.findData(current_category)
        )
        assert gravestone_editor._filtered_template_ids == category_ids
        assert gravestone_editor.template_combo.currentData() == old_template_id
        assert gravestone_editor.previous_button.isEnabled()
        assert gravestone_editor.next_button.isEnabled()
        gravestone_editor.next_button.click()
        assert gravestone_editor.template_combo.currentData() == replacement_id
        gravestone_editor.previous_button.click()
        assert gravestone_editor.template_combo.currentData() == old_template_id
        with patch(
            "app.GuildPortraitGrabberQt.render_gravestone_card",
            wraps=render_gravestone_card,
        ) as shared_renderer:
            gravestone_editor.template_combo.setCurrentIndex(
                gravestone_editor.template_combo.findData(replacement_id)
            )
        assert gravestone_editor.state.draft.template_id == replacement_id
        assert gravestone_editor.state.draft.portrait_offset_x == (
            replacement.default_portrait_offset_x
        )
        assert gravestone_editor.state.draft.portrait_offset_y == (
            replacement.default_portrait_offset_y
        )
        assert gravestone_editor.state.draft.portrait_zoom == (
            replacement.default_portrait_zoom
        )
        assert gravestone_editor.state.draft.text_offset_x == 0.0
        assert gravestone_editor.state.draft.text_offset_y == 0.0
        assert gravestone_editor.state.draft.text_scale == 1.0
        assert shared_renderer.call_args.args[0].graveTemplateId == replacement_id
        assert shared_renderer.call_args.args[2] == history_portrait_altgrab
        assert shared_renderer.call_args.kwargs["portrait_image"] is not None
        assert project.read_bytes() == project_before_editor
        assert window._graveyard_member_by_id["m1003"].graveTemplateId == old_template_id
        assert graveyard_template.filename in window.graveyard_preview_status_label.text()

        # Phase 6.4: Geometrieänderungen bleiben im Draft und verwenden feste
        # Renderkoordinaten. Die Shared-Helper liefern damit unabhängig von der
        # tatsächlichen Widgetgröße dieselben fachlichen Werte.
        replacement_frame = prepare_gravestone_template(
            replacement.path, GRAVESTONE_CARD_SIZE,
        )
        portrait_box = detect_gravestone_portrait_opening(replacement_frame).box
        portrait_size = (
            portrait_box[2] - portrait_box[0],
            portrait_box[3] - portrait_box[1],
        )
        portrait_origin = gravestone_editor.state.draft
        expected_portrait_offsets = shifted_portrait_offsets(
            portrait_origin.portrait_offset_x,
            portrait_origin.portrait_offset_y,
            12.0,
            -9.0,
            portrait_size,
        )
        preview_key_before_drag = (
            gravestone_editor.preview._pixmap_item.pixmap().cacheKey()
        )
        with patch(
            "app.GuildPortraitGrabberQt.render_gravestone_card",
            wraps=render_gravestone_card,
        ) as editor_renderer:
            gravestone_editor._begin_geometry_drag()
            gravestone_editor._drag_geometry(12.0, -9.0)
        assert gravestone_editor.state.draft.portrait_offset_x == (
            expected_portrait_offsets[0]
        )
        assert gravestone_editor.state.draft.portrait_offset_y == (
            expected_portrait_offsets[1]
        )
        assert editor_renderer.call_args.args[0].portraitOffsetX == (
            expected_portrait_offsets[0]
        )
        assert editor_renderer.call_args.args[0].portraitOffsetY == (
            expected_portrait_offsets[1]
        )
        assert gravestone_editor.preview._pixmap_item.pixmap().cacheKey() != (
            preview_key_before_drag
        )
        assert project.read_bytes() == project_before_editor

        state_before_resize = gravestone_editor.state
        gravestone_editor.preview.resize(480, 620)
        application.processEvents()
        assert gravestone_editor.state == state_before_resize

        mapped_drafts = []
        mapped_scene_deltas = []
        for view_size in ((300, 410), (600, 820)):
            gravestone_editor.reset_button.click()
            gravestone_editor.preview.resize(*view_size)
            application.processEvents()
            scene_start = QPointF(70.25, 80.5)
            scene_end = QPointF(92.75, 69.25)
            transform = gravestone_editor.preview.viewportTransform()
            mapped_start = gravestone_editor.preview._event_scene_position(
                SimpleNamespace(position=lambda: transform.map(scene_start))
            )
            mapped_end = gravestone_editor.preview._event_scene_position(
                SimpleNamespace(position=lambda: transform.map(scene_end))
            )
            mapped_scene_deltas.append(mapped_end - mapped_start)
            gravestone_editor._begin_geometry_drag()
            gravestone_editor._drag_geometry(-10.0, 8.0)
            mapped_drafts.append((
                gravestone_editor.state.draft.portrait_offset_x,
                gravestone_editor.state.draft.portrait_offset_y,
            ))
        assert mapped_drafts[0] == mapped_drafts[1]
        for mapped_delta in mapped_scene_deltas:
            assert abs(mapped_delta.x() - 22.5) < 1e-9
            assert abs(mapped_delta.y() + 11.25) < 1e-9

        gravestone_editor.reset_button.click()
        gravestone_editor._begin_geometry_drag()
        gravestone_editor._drag_geometry(-10000.0, 10000.0)
        assert gravestone_editor.state.draft.portrait_offset_x == -1.0
        assert gravestone_editor.state.draft.portrait_offset_y == 1.0

        gravestone_editor.reset_button.click()
        gravestone_editor.zoom_slider.setValue(175)
        assert gravestone_editor.state.draft.portrait_zoom == 1.75
        assert gravestone_editor.zoom_value_label.text() == "1.75×"
        gravestone_editor._begin_geometry_drag()
        gravestone_editor._drag_geometry(12.0, -9.0)
        assert gravestone_editor.state.draft.portrait_offset_x == (
            expected_portrait_offsets[0]
        )
        assert gravestone_editor.state.draft.portrait_offset_y == (
            expected_portrait_offsets[1]
        )
        gravestone_editor.zoom_slider.setValue(gravestone_editor.zoom_slider.maximum())
        assert gravestone_editor.state.draft.portrait_zoom == 2.0
        gravestone_editor.zoom_slider.setValue(gravestone_editor.zoom_slider.minimum())
        assert gravestone_editor.state.draft.portrait_zoom == 1.0

        gravestone_editor.text_target_button.setChecked(True)
        text_origin = gravestone_editor.state.draft
        expected_text_offsets = shifted_text_offsets(
            text_origin.text_offset_x,
            text_origin.text_offset_y,
            18.0,
            12.0,
            GRAVESTONE_CARD_SIZE,
        )
        gravestone_editor._begin_geometry_drag()
        gravestone_editor._drag_geometry(18.0, 12.0)
        assert gravestone_editor.state.draft.text_offset_x == expected_text_offsets[0]
        assert gravestone_editor.state.draft.text_offset_y == expected_text_offsets[1]
        gravestone_editor.text_scale_slider.setValue(140)
        assert gravestone_editor.state.draft.text_scale == 1.4
        gravestone_editor.death_date_edit.setText("2026-09-17")
        assert gravestone_editor.state.draft.death_date == "2026-09-17"
        assert project.read_bytes() == project_before_editor

        # Reset stellt bei einem Kandidaten dessen Preset sowie neutrale Textwerte
        # und das beim Öffnen gespeicherte Todesdatum wieder her.
        gravestone_editor.reset_button.click()
        assert gravestone_editor.state.draft.template_id == replacement_id
        assert gravestone_editor.state.draft.portrait_offset_x == (
            replacement.default_portrait_offset_x
        )
        assert gravestone_editor.state.draft.portrait_offset_y == (
            replacement.default_portrait_offset_y
        )
        assert gravestone_editor.state.draft.portrait_zoom == (
            replacement.default_portrait_zoom
        )
        assert gravestone_editor.state.draft.text_offset_x == 0.0
        assert gravestone_editor.state.draft.text_offset_y == 0.0
        assert gravestone_editor.state.draft.text_scale == 1.0
        assert gravestone_editor.state.draft.death_date == "2026-09-01"

        # Ein weiterer Template-Wechsel verwendet dessen eigenes Preset. Reset
        # bleibt auf dem aktiven Draft und wechselt nicht zum gespeicherten Stein.
        third_id = category_ids[2]
        third_template = available_by_id[third_id]
        gravestone_editor.template_combo.setCurrentIndex(
            gravestone_editor.template_combo.findData(third_id)
        )
        assert gravestone_editor.state.draft.template_id == third_id
        assert gravestone_editor.state.draft.portrait_offset_x == (
            third_template.default_portrait_offset_x
        )
        gravestone_editor.state = replace(
            gravestone_editor.state,
            draft=replace(
                gravestone_editor.state.draft,
                portrait_offset_x=0.91,
                portrait_offset_y=-0.82,
                portrait_zoom=2.75,
            ),
        )
        gravestone_editor.reset_button.click()
        assert gravestone_editor.state.draft.template_id == third_id
        assert gravestone_editor.state.draft.portrait_offset_x == (
            third_template.default_portrait_offset_x
        )
        assert gravestone_editor.state.draft.portrait_offset_y == (
            third_template.default_portrait_offset_y
        )
        assert gravestone_editor.state.draft.portrait_zoom == (
            third_template.default_portrait_zoom
        )

        # Beim gespeicherten Template stellt Reset die beim Öffnen geladenen
        # Sitzungswerte wieder her. Abbrechen verwirft danach den gesamten Draft.
        gravestone_editor.template_combo.setCurrentIndex(
            gravestone_editor.template_combo.findData(old_template_id)
        )
        assert gravestone_editor.state.draft.template_id == old_template_id
        gravestone_editor.state = replace(
            gravestone_editor.state,
            draft=replace(
                gravestone_editor.state.draft,
                portrait_offset_x=-0.55,
                portrait_zoom=3.10,
            ),
        )
        gravestone_editor.reset_button.click()
        assert gravestone_editor.state.draft.template_id == old_template_id
        assert gravestone_editor.state.draft.portrait_offset_x == 0.25
        assert gravestone_editor.state.draft.portrait_offset_y == -0.20
        assert gravestone_editor.state.draft.portrait_zoom == 1.35
        gravestone_editor.cancel_button.click()
        application.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        application.processEvents()
        assert window._gravestone_editor_dialog is None
        assert window._graveyard_member_by_id["m1003"].graveTemplateId == old_template_id
        assert project.read_bytes() == project_before_editor

        # Eine neue Editorsitzung beginnt erneut beim gespeicherten Zustand und
        # erbt keinen verworfenen Draft der vorigen Sitzung. Renderer- und
        # Schreibfehler dürfen dabei niemals einen Teilzustand persistieren.
        assert window.open_selected_gravestone_editor()
        application.processEvents()
        reopened_editor = window._gravestone_editor_dialog
        assert reopened_editor is not None
        assert reopened_editor.state.saved.template_id == old_template_id
        assert reopened_editor.state.draft.template_id == old_template_id
        assert reopened_editor.state.draft.portrait_offset_x == 0.25
        reopened_editor.template_combo.setCurrentIndex(
            reopened_editor.template_combo.findData(replacement_id)
        )
        assert reopened_editor.state.draft.template_id == replacement_id
        reopened_editor.state = replace(
            reopened_editor.state,
            draft=replace(
                reopened_editor.state.draft,
                portrait_offset_x=0.31,
                portrait_offset_y=-0.27,
                portrait_zoom=1.55,
                text_offset_x=0.12,
                text_offset_y=-0.08,
                text_scale=1.25,
                death_date="2026-09-17",
            ),
        )
        reopened_editor._sync_controls_from_draft()
        reopened_editor._refresh_preview()
        project_before_failed_save = project.read_bytes()
        with patch.object(
            reopened_editor, "render_draft", side_effect=ValueError("Renderfehler")
        ), patch("app.GuildPortraitGrabberQt.patch_project_member") as project_patch:
            reopened_editor.save_button.click()
        assert not project_patch.called
        assert project.read_bytes() == project_before_failed_save
        assert "Speichern fehlgeschlagen" in reopened_editor.save_status_label.text()
        with patch(
            "app.GuildPortraitGrabberQt.patch_project_member",
            side_effect=PermissionError("Schreibschutz"),
        ):
            reopened_editor.save_button.click()
        assert project.read_bytes() == project_before_failed_save
        assert reopened_editor.isVisible()
        assert window._graveyard_member_by_id["m1003"].graveTemplateId == old_template_id

        # Übernehmen persistiert Template und den vollständigen Geometriesatz in
        # einer Patch-Operation, hält die Auswahl und rendert den gespeicherten Stand.
        with patch(
            "app.GuildPortraitGrabberQt.render_gravestone_card",
            wraps=render_gravestone_card,
        ) as saved_renderer:
            reopened_editor.save_button.click()
        application.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        application.processEvents()
        assert window._gravestone_editor_dialog is None
        saved_payload = json.loads(project.read_text(encoding="utf-8"))
        saved_member = next(
            item for item in saved_payload["members"] if item["id"] == "m1003"
        )
        assert saved_member["graveTemplateId"] == replacement_id
        assert saved_member["gravestoneTemplate"] == replacement.filename
        assert saved_member["portraitOffsetX"] == 0.31
        assert saved_member["portraitOffsetY"] == -0.27
        assert saved_member["portraitZoom"] == 1.55
        assert saved_member["textOffsetX"] == 0.12
        assert saved_member["textOffsetY"] == -0.08
        assert saved_member["textScale"] == 1.25
        assert saved_member["deathDate"] == "2026-09-17"
        assert window.selected_graveyard_member_id == "m1003"
        assert window._graveyard_member_by_id["m1003"].graveTemplateId == replacement_id
        assert window.graveyard_stone_value.text() == replacement.filename
        assert replacement.filename in window.graveyard_preview_status_label.text()
        assert saved_renderer.call_args.args[0].portraitOffsetX == 0.31
        assert saved_renderer.call_args.args[0].textScale == 1.25

        # Erneutes Öffnen lädt exakt den neuen gespeicherten Zustand. Auch reine
        # Geometrieänderungen am bereits gespeicherten Template werden gemeinsam gespeichert.
        assert window.open_selected_gravestone_editor()
        application.processEvents()
        saved_editor = window._gravestone_editor_dialog
        assert saved_editor is not None
        assert saved_editor.state.saved == saved_editor.state.draft
        assert saved_editor.state.saved.template_id == replacement_id
        assert saved_editor.state.saved.portrait_offset_x == 0.31
        assert saved_editor.state.saved.text_scale == 1.25
        saved_editor.state = replace(
            saved_editor.state,
            draft=replace(
                saved_editor.state.draft,
                portrait_offset_x=0.44,
                text_offset_y=0.09,
            ),
        )
        saved_editor.save_button.click()
        application.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        application.processEvents()
        same_template_payload = json.loads(project.read_text(encoding="utf-8"))
        same_template_member = next(
            item for item in same_template_payload["members"] if item["id"] == "m1003"
        )
        assert same_template_member["graveTemplateId"] == replacement_id
        assert same_template_member["portraitOffsetX"] == 0.44
        assert same_template_member["textOffsetY"] == 0.09

        history_portrait_altgrab.unlink()
        regular_portrait_altgrab = normal_portrait_path("Altgrab", project)
        Image.new("RGB", (80, 120), (30, 50, 70)).save(regular_portrait_altgrab)
        with patch(
            "app.GuildPortraitGrabberQt.render_gravestone_card",
            wraps=render_gravestone_card,
        ) as shared_renderer:
            window.show_graveyard_member("m1003")
        assert shared_renderer.call_args.args[2] == regular_portrait_altgrab
        regular_portrait_altgrab.unlink()
        missing_marker = history_portrait_altgrab.with_suffix(".missing")
        assert not missing_marker.exists()
        assert graveyard_portrait_for_member("m1003", "Altgrab", project) is None
        with patch(
            "app.GuildPortraitGrabberQt.render_gravestone_card",
            wraps=render_gravestone_card,
        ) as shared_renderer:
            window.show_graveyard_member("m1003")
        assert shared_renderer.call_args.args[2] == graveyard_portrait_placeholder_path()
        assert not missing_marker.exists()
        assert window.graveyard_preview.pixmap() is not None
        assert not window.graveyard_preview.pixmap().isNull()
        with patch(
            "app.GuildPortraitGrabberQt.graveyard_preview_portrait_for_member",
            return_value=None,
        ):
            window.show_graveyard_member("m1003")
        assert window.graveyard_preview.pixmap() is not None
        assert not window.graveyard_preview.pixmap().isNull()

        missing_stone_row = next(
            row for row in range(window.graveyard_model.rowCount())
            if window.graveyard_model.item(row, 0).text() == "Fehlstein"
        )
        window.graveyard_table.selectRow(missing_stone_row)
        application.processEvents()
        assert window.selected_graveyard_member_id == "m1005"
        assert window.graveyard_preview_status_label.text() == (
            "Grabstein nicht im Manifest gefunden"
        )
        assert window.graveyard_category_value.text() == "Nicht gesetzt"

        no_stone_row = next(
            row for row in range(window.graveyard_model.rowCount())
            if window.graveyard_model.item(row, 0).text() == "Ohnegrab"
        )
        window.graveyard_table.selectRow(no_stone_row)
        application.processEvents()
        assert window.selected_graveyard_member_id == "m1006"
        assert window.graveyard_preview_status_label.text() == "Kein Grabstein"
        bifi_row = next(
            row for row in range(window.character_model.rowCount())
            if window.character_model.item(row, 0).text() == "Bífi"
        )
        window.character_table.selectRow(bifi_row)
        application.processEvents()
        assert window.selected_character_id == "m1002"
        assert window.character_name_value.text() == "Bífi"
        assert window.portrait_status_label.text() == "Kein Portrait vorhanden"
        assert window.portrait_preview.source_signature is None

        annie_row = next(
            row for row in range(window.character_model.rowCount())
            if window.character_model.item(row, 0).text() == "Ánníe"
        )
        window.character_table.selectRow(annie_row)
        application.processEvents()
        assert window.selected_character_id == "m1001"
        assert window.character_race_value.text() == "Mensch"
        assert window.character_class_value.text() == "Mage"
        assert window.character_spec_value.text() == "Frost"
        assert window.character_spec_value.parent() is None
        assert window.character_life_value.text() == "Am Leben"
        assert window.character_model.horizontalHeaderItem(3).text() == "Status"
        assert window.character_model.item(annie_row, 2).icon().isNull() is False
        assert window.character_model.item(annie_row, 2).foreground().color().name() == "#3fc7eb"
        assert window.character_model.item(annie_row, 0).foreground().style() == Qt.BrushStyle.NoBrush
        assert window.portrait_status_label.text() == "Portrait vorhanden"
        expected_url = build_armory_url("Ánníe", "EU", "stitches", "classic1x")
        assert window.armory_url_for_selected() == expected_url
        assert window.armory_url_label.toolTip() == expected_url
        assert window.armory_url_label.parent() is window.character_detail_frame
        assert window.armory_url_label.y() > window.portrait_preview.y()
        assert window.open_browser_button.text() == "Im Browser öffnen"
        assert window.capture_portrait_button.text() == "Portrait erstellen"
        assert window.read_armory_button.text() == "Daten auslesen"
        assert window.capture_missing_button.text() == "Alle fehlenden"
        assert window.capture_all_button.text() == "Alle Portraits"
        assert window.stop_batch_button.text() == "STOPP"
        assert window.import_portrait_button.text() == "Portrait manuell"
        assert window.remove_portrait_button.text() == "Portrait entfernen"
        assert window.edit_portrait_button.text() == "Portrait bearbeiten"
        assert window.open_browser_button.isEnabled()
        assert window.capture_portrait_button.isEnabled()
        assert window.import_portrait_button.isEnabled()
        assert window.remove_portrait_button.isEnabled()
        assert window.edit_portrait_button.isEnabled()
        assert window.portrait_preview.source_signature is not None
        assert window.portrait_preview.pixmap() is not None
        assert not window.portrait_preview.pixmap().isNull()
        assert window.portrait_preview.pixmap().height() <= window.portrait_preview.contentsRect().height()
        assert window.portrait_preview.pixmap().width() <= window.portrait_preview.contentsRect().width()
        window.resize(1050, 760)
        application.processEvents()
        assert window.portrait_preview.pixmap().height() <= window.portrait_preview.contentsRect().height()
        assert window.portrait_preview.pixmap().width() <= window.portrait_preview.contentsRect().width()

        # Phase 5.1: Der Qt-Editor öffnet nur einen nicht-destruktiven State,
        # zeigt die richtige Datei proportional und verwirft beim Schließen alles.
        neutral_state = load_portrait_editor_state(annie_portrait)
        assert neutral_state.source_path == annie_portrait
        assert neutral_state.source_size == (384, 672)
        assert neutral_state.zoom == 1.0
        assert neutral_state.offset_x == 0.0
        assert neutral_state.offset_y == 0.0
        assert portrait_editor_pan(neutral_state, 25.0, -25.0) == neutral_state
        math_state = portrait_editor_transform(neutral_state, zoom=2.0)
        assert portrait_editor_pan(math_state, 40.0, 0.0).offset_x == 40.0
        assert portrait_editor_pan(math_state, -40.0, 0.0).offset_x == -40.0
        assert portrait_editor_pan(math_state, 0.0, 35.0).offset_y == 35.0
        assert portrait_editor_pan(math_state, 0.0, -35.0).offset_y == -35.0
        assert portrait_editor_zoom(neutral_state, -100.0).zoom == 1.0
        assert portrait_editor_zoom(neutral_state, 100.0).zoom == 4.0
        portrait_before_editor = annie_portrait.read_bytes()
        for _open_index in range(2):
            assert window.edit_selected_portrait()
            application.processEvents()
            editor = window._portrait_editor_dialog
            assert editor is not None and editor.isVisible()
            assert editor.character_name == "Ánníe"
            assert editor.state.source_path == annie_portrait
            assert editor.state.zoom == 1.0
            assert editor.state.offset_x == 0.0
            assert editor.state.offset_y == 0.0
            assert editor.zoom_value.text() == "1.00×"
            assert editor.offset_x_value.text() == "0.00"
            assert editor.offset_y_value.text() == "0.00"
            assert editor.apply_button.text() == "Übernehmen"
            shown = editor.preview.source_pixmap
            assert shown is not None and not shown.isNull()
            assert abs((shown.width() / shown.height()) - (384 / 672)) < 0.01

            # Das fachliche System bleibt die feste 320x560-Scene. Reines
            # Widget-Resize verändert weder Zoom noch Offset.
            initial_state = editor.state
            for view_size in ((340, 500), (680, 900)):
                editor.preview.resize(*view_size)
                application.processEvents()
                assert editor.state == initial_state
                center = editor.preview.mapToScene(
                    editor.preview.viewport().rect().center()
                )
                assert abs(center.x() - 160.0) < 2.0, (center.x(), center.y(), view_size)
                assert abs(center.y() - 280.0) < 2.0, (center.x(), center.y(), view_size)

            # Bei Zoom 1 ist das normierte 4:7-Portrait exakt eingepasst;
            # Panning wird wie im Tk-Editor an den Bildkanten geklemmt.
            editor.preview.pan_by_scene_delta(40.0, 30.0)
            assert editor.state.offset_x == 0.0
            assert editor.state.offset_y == 0.0

            editor.preview.set_state(portrait_editor_transform(editor.state, zoom=2.0))
            assert editor.state.zoom == 2.0
            assert editor.zoom_value.text() == "2.00×"
            assert editor.zoom_slider.value() == 200

            def drag_scene(delta_x: float, delta_y: float) -> None:
                start = editor.preview.mapFromScene(QPointF(160.0, 280.0))
                end = editor.preview.mapFromScene(QPointF(
                    160.0 + delta_x, 280.0 + delta_y,
                ))
                QTest.mousePress(editor.preview.viewport(), Qt.MouseButton.LeftButton,
                                 Qt.KeyboardModifier.NoModifier, start)
                QTest.mouseMove(editor.preview.viewport(), end)
                QTest.mouseRelease(editor.preview.viewport(), Qt.MouseButton.LeftButton,
                                   Qt.KeyboardModifier.NoModifier, end)
                application.processEvents()

            editor.preview.set_state(portrait_editor_transform(
                editor.state, zoom=2.0, offset_x=0.0, offset_y=0.0,
            ))
            drag_scene(36.0, 28.0)
            assert abs(editor.state.offset_x - 36.0) < 2.0
            assert abs(editor.state.offset_y - 28.0) < 2.0
            drag_scene(-20.0, -18.0)
            assert abs(editor.state.offset_x - 16.0) < 3.0
            assert abs(editor.state.offset_y - 10.0) < 3.0

            # Dieselbe Scene-Bewegung bleibt bei anderer Widgetgröße fachlich
            # identisch; mapToScene trennt View- und Scene-Koordinaten.
            mapped_offsets = []
            for view_size in ((360, 600), (720, 960)):
                editor.preview.resize(*view_size)
                application.processEvents()
                editor.preview.set_state(portrait_editor_transform(
                    editor.state, zoom=2.0, offset_x=0.0, offset_y=0.0,
                ))
                drag_scene(42.0, -24.0)
                mapped_offsets.append((editor.state.offset_x, editor.state.offset_y))
            assert abs(mapped_offsets[0][0] - mapped_offsets[1][0]) < 2.0
            assert abs(mapped_offsets[0][1] - mapped_offsets[1][1]) < 2.0

            # Wheel und Slider aktualisieren denselben State; Grenzen bleiben
            # auch nach wiederholter Bedienung stabil.
            wheel_in = QWheelEvent(
                QPointF(10.0, 10.0), QPointF(10.0, 10.0), QPoint(), QPoint(0, 120),
                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.ScrollUpdate, False,
            )
            zoom_before_wheel = editor.state.zoom
            editor.preview.wheelEvent(wheel_in)
            assert editor.state.zoom == min(4.0, zoom_before_wheel + 0.12)
            editor.preview.zoom_by_step(-1)
            assert abs(editor.state.zoom - zoom_before_wheel) < 1e-9
            for _step in range(40):
                editor.preview.zoom_by_step(1)
            assert editor.state.zoom == 4.0
            for _step in range(40):
                editor.preview.zoom_by_step(-1)
            assert editor.state.zoom == 1.0
            editor.zoom_slider.setValue(250)
            assert editor.state.zoom == 2.5

            # Wiederholter Reset stellt exakt die Ausgangswerte her.
            editor.reset_button.click()
            editor.reset_button.click()
            assert editor.state == initial_state
            assert editor.zoom_value.text() == "1.00×"
            assert editor.offset_x_value.text() == "0.00"
            assert editor.offset_y_value.text() == "0.00"
            editor.cancel_button.click()
            application.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            application.processEvents()
            assert window._portrait_editor_dialog is None
            assert annie_portrait.read_bytes() == portrait_before_editor

        def drag_crop(editor, start_scene: QPointF, end_scene: QPointF) -> None:
            start = editor.preview.mapFromScene(start_scene)
            end = editor.preview.mapFromScene(end_scene)
            QTest.mousePress(
                editor.preview.viewport(), Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier, start,
            )
            QTest.mouseMove(editor.preview.viewport(), end)
            QTest.mouseRelease(
                editor.preview.viewport(), Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier, end,
            )
            application.processEvents()

        # Die Tk-paritätische Ausschnittwahl arbeitet in der festen Scene und
        # ergibt bei Resize sowie umgekehrter Ziehrichtung dasselbe Quellrechteck.
        crop_boxes = []
        for view_size, start_scene, end_scene in (
            ((360, 600), QPointF(80.0, 140.0), QPointF(240.0, 420.0)),
            ((720, 960), QPointF(240.0, 420.0), QPointF(80.0, 140.0)),
        ):
            assert window.edit_selected_portrait()
            application.processEvents()
            crop_editor = window._portrait_editor_dialog
            assert crop_editor is not None
            crop_editor.preview.resize(*view_size)
            application.processEvents()
            crop_editor.crop_mode_button.setChecked(True)
            assert crop_editor.preview.mode == crop_editor.preview.MODE_CROP
            assert "Ausschnitt" in crop_editor.help_label.text()
            drag_crop(crop_editor, start_scene, end_scene)
            crop_boxes.append(crop_editor.preview.last_source_crop_box)
            assert crop_editor.preview.mode == crop_editor.preview.MODE_PAN
            assert crop_editor.pan_mode_button.isChecked()
            assert crop_editor.state.source_size == (192, 336)
            assert (crop_editor.state.zoom, crop_editor.state.offset_x,
                    crop_editor.state.offset_y) == (1.0, 0.0, 0.0)
            assert "Ausschnitt übernommen" in crop_editor.help_label.text()
            crop_editor.cancel_button.click()
            application.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            application.processEvents()
            assert annie_portrait.read_bytes() == portrait_before_editor
        assert crop_boxes == [(96, 168, 288, 504), (96, 168, 288, 504)]

        # Ein Schreibfehler lässt das bestehende Portrait und den offenen
        # Editorzustand unangetastet.
        assert window.edit_selected_portrait()
        application.processEvents()
        failed_editor = window._portrait_editor_dialog
        assert failed_editor is not None
        failed_editor.preview.set_state(portrait_editor_transform(
            failed_editor.state, zoom=2.0, offset_x=35.0, offset_y=-20.0,
        ))
        with patch(
            "app.GuildPortraitGrabberQt.save_portrait_editor_image",
            side_effect=PermissionError("gesperrt"),
        ), patch("app.GuildPortraitGrabberQt.QMessageBox.critical") as save_error:
            failed_editor.apply_button.click()
            application.processEvents()
        assert save_error.call_count == 1
        assert failed_editor.isVisible()
        assert annie_portrait.read_bytes() == portrait_before_editor
        assert window.selected_character_id == "m1001"
        failed_editor.cancel_button.click()
        application.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        application.processEvents()
        assert window._portrait_editor_dialog is None

        # Anwenden rendert nur aus dem fachlichen State. Die Widgetgröße hat
        # keinen Einfluss auf den finalen 384x672-Crop.
        preview_signature_before_save = window.portrait_preview.source_signature
        assert window.edit_selected_portrait()
        application.processEvents()
        save_editor = window._portrait_editor_dialog
        assert save_editor is not None
        save_editor.crop_mode_button.setChecked(True)
        drag_crop(
            save_editor, QPointF(60.0, 105.0), QPointF(260.0, 455.0),
        )
        assert save_editor.preview.last_source_crop_box == (72, 126, 312, 546)
        assert save_editor.state.source_size == (240, 420)
        save_editor.preview.set_state(portrait_editor_transform(
            save_editor.state, zoom=2.0, offset_x=52.0, offset_y=-34.0,
        ))
        expected_output = render_portrait_editor_image(
            save_editor.preview.working_image,
            save_editor.state.zoom,
            save_editor.state.offset_x,
            save_editor.state.offset_y,
        ).tobytes()
        save_editor.preview.resize(720, 960)
        application.processEvents()
        assert render_portrait_editor_image(
            save_editor.preview.working_image,
            save_editor.state.zoom,
            save_editor.state.offset_x,
            save_editor.state.offset_y,
        ).tobytes() == expected_output
        save_editor.apply_button.click()
        application.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        application.processEvents()
        assert window._portrait_editor_dialog is None
        with Image.open(annie_portrait) as edited:
            assert edited.size == (384, 672)
            assert edited.mode == "RGB"
            assert edited.tobytes() == expected_output
        assert annie_portrait.read_bytes() != portrait_before_editor
        assert window.selected_character_id == "m1001"
        assert window.portrait_preview.source_signature != preview_signature_before_save
        assert window.portrait_status_label.text() == "Portrait vorhanden"
        assert window.worker_status_label.text() == "Portrait bearbeitet: Ánníe"

        # Ein defektes vorhandenes Bild und ein fehlendes Bild erzeugen keinen
        # halboffenen Editorzustand und verändern die Auswahl nicht.
        window.character_table.selectRow(bifi_row)
        application.processEvents()
        assert window.edit_portrait_button.isEnabled()
        with patch("app.GuildPortraitGrabberQt.QMessageBox.critical"):
            assert not window.edit_selected_portrait()
        assert window._portrait_editor_dialog is None
        assert window.selected_character_id == "m1002"
        window.character_table.selectRow(ohnebild_row := next(
            row for row in range(window.character_model.rowCount())
            if window.character_model.item(row, 0).text() == "Ohnebild"
        ))
        application.processEvents()
        assert not window.edit_portrait_button.isEnabled()
        assert not window.edit_selected_portrait()
        assert window._portrait_editor_dialog is None
        window.character_table.selectRow(annie_row)
        application.processEvents()

        worker = workers[-1]
        assert worker.started

        # Einstellungen, Diagnose, Raw-Kalibrierung und Standardregion verwenden
        # ausschließlich die bestehenden Config-, Worker- und Capture-Verträge.
        assert window.output_folder_edit.text() == str(annie_portrait.parent)
        assert "X=10, Y=20, 300x525 px" in window.screen_region_label.text()
        with patch("app.GuildPortraitGrabberQt.save_config") as persisted:
            window.standard_wait_spin.setValue(7.5)
            window.capture_mode_combo.setCurrentText("Standardbrowser + Standardbereich")
            window.save_settings()
        assert persisted.called
        assert window.config_data["capture_mode"] == "standard_browser_region"
        assert window.config_data["standard_wait_after_open"] == 7.5
        assert window.standard_wait_spin.isEnabled()
        assert window._worker_payload()["standard_wait_after_open"] == 7.5
        with patch("app.GuildPortraitGrabberQt.save_config"):
            window.standard_wait_spin.setValue(6.0)
            window.capture_mode_combo.setCurrentText("Playwright / v0.1.2")
            window.save_settings()
        assert window.config_data["capture_mode"] == "playwright"
        assert not window.standard_wait_spin.isEnabled()

        with patch("app.GuildPortraitGrabberQt.save_config"):
            assert window.test_browser()
        action, payload = worker.commands[-1]
        assert action == "test_browser"
        assert payload["preferred_channel"] == "msedge"
        assert_plain_payload(payload)
        worker.events.put({"type": "browser_test_ok", "browser": "Microsoft Edge"})
        window._poll_worker_events()
        application.processEvents()
        assert window._active_worker_action is None
        assert "Browser-Test erfolgreich" in window.worker_status_label.text()
        assert window._worker_message_box.isVisible()
        window._worker_message_box.close()
        with patch("app.GuildPortraitGrabberQt.save_config"):
            assert window.test_browser()
        worker.events.put({
            "type": "error", "message": "Browser fehlt",
            "detail": "Kein Browserkanal verfügbar", "log_path": "test.log",
        })
        window._poll_worker_events()
        application.processEvents()
        assert window._active_worker_action is None
        assert "Browser fehlt" in window.worker_error_label.text()
        window._worker_message_box.close()

        raw_capture = temp_root / "raw_capture.png"
        Image.new("RGB", (1000, 700), (45, 65, 85)).save(raw_capture)
        assert window.calibrate_selected_crop()
        action, payload = worker.commands[-1]
        assert action == "capture_raw"
        assert payload["name"] == "Ánníe"
        assert payload["member_id"] == "m1001"
        assert payload["capture_mode"] == "playwright"
        assert payload["navigate"] is True
        worker.events.put({
            "type": "raw_capture", "name": "Ánníe",
            "path": str(raw_capture), "method": "test-playwright",
        })
        window._poll_worker_events()
        application.processEvents()
        assert window._active_worker_action is None
        calibration_dialog = window._portrait_editor_dialog
        assert calibration_dialog is not None
        assert calibration_dialog.isVisible()
        with patch("app.GuildPortraitGrabberQt.save_config"):
            calibration_dialog.apply_button.click()
        application.processEvents()
        assert window.config_data["crop"] == {
            "x1": 0.34, "y1": 0.1, "x2": 0.66, "y2": 0.9,
        }
        with Image.open(annie_portrait) as calibrated:
            assert calibrated.size == (384, 672)
        window.config_data["crop"] = dict(TEST_CONFIG["crop"])

        with patch("app.GuildPortraitGrabberQt.save_config"):
            window._accept_screen_region(QRectF(10, 20, 300, 525), (0, 0, 1920, 1080))
        assert window._current_screen_region() == (10, 20, 300, 525)
        with patch("app.GuildPortraitGrabberQt.save_config"):
            window._accept_screen_region(
                QRectF(80, 100, 300, 525), (-1280, 0, 3200, 1080)
            )
        assert window._current_screen_region() == (-1200, 100, 300, 525)
        window.config_data["screen_region"] = dict(TEST_CONFIG["screen_region"])
        with patch(
            "app.GuildPortraitGrabberQt.capture_screen_region",
            return_value=Image.new("RGB", (300, 525), (10, 20, 30)),
        ):
            assert window.test_default_screen_region()
        assert window._preview_dialog.isVisible()
        window._preview_dialog.close()
        with patch(
            "app.GuildPortraitGrabberQt.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ), patch("app.GuildPortraitGrabberQt.save_config"):
            assert window.reset_default_screen_region()
        assert window._current_screen_region() == (0, 0, 0, 0)
        window.config_data["screen_region"] = dict(TEST_CONFIG["screen_region"])
        window.config_data.pop("portrait_sources", None)
        window.config_data.pop("portrait_source", None)

        # Einzelcapture verwendet unverändert den gemeinsamen Worker-/Pfadvertrag.
        first_signature = window.portrait_preview.source_signature
        first_bytes = annie_portrait.read_bytes()
        assert window.capture_selected_portrait()
        action, payload = worker.commands[-1]
        assert action == "capture"
        assert payload["name"] == "Ánníe"
        assert payload["member_id"] == "m1001"
        assert payload["output_dir"] == str(annie_portrait.parent)
        assert payload["crop"] == TEST_CONFIG["crop"]
        assert payload["navigate"] is True
        assert payload["capture_mode"] == "playwright"
        assert_plain_payload(payload)
        assert not window.capture_portrait_button.isEnabled()
        assert not window.import_portrait_button.isEnabled()
        assert not window.remove_portrait_button.isEnabled()
        Image.new("RGB", (384, 672), (180, 60, 30)).save(annie_portrait)
        worker.events.put({
            "type": "portrait_saved", "name": "Ánníe",
            "path": str(annie_portrait), "method": "test-playwright",
        })
        window._poll_worker_events()
        assert window.selected_character_id == "m1001"
        assert window.portrait_preview.source_signature != first_signature
        assert annie_portrait.read_bytes() != first_bytes
        assert window.portrait_path_label.text() == str(annie_portrait)
        assert window.capture_portrait_button.isEnabled()
        assert window.import_portrait_button.isEnabled()
        assert window.remove_portrait_button.isEnabled()
        assert "Gespeichert:" in window.worker_status_label.text()

        # Der zweite produktive Capture-Modus nutzt denselben Auftrag; ein Fehler
        # darf das bereits vorhandene Portrait und dessen Preview nicht verändern.
        successful_bytes = annie_portrait.read_bytes()
        successful_signature = window.portrait_preview.source_signature
        window.config_data["capture_mode"] = "standard_browser_region"
        with patch(
            "app.GuildPortraitGrabberQt.validate_screen_region",
            return_value=(True, "OK"),
        ):
            assert window.capture_selected_portrait()
        action, payload = worker.commands[-1]
        assert action == "capture"
        assert payload["capture_mode"] == "standard_browser_region"
        assert payload["screen_region"] == (10, 20, 300, 525)
        assert_plain_payload(payload)
        worker.events.put({
            "type": "error", "message": "Simulierter Capture-Fehler",
            "detail": "Nur Test", "log_path": "test.log",
        })
        window._poll_worker_events()
        assert annie_portrait.read_bytes() == successful_bytes
        assert window.portrait_preview.source_signature == successful_signature
        assert window.worker_error_label.isVisible()
        assert window.capture_portrait_button.isEnabled()

        # Eine ungültige Bildschirmregion und ein Ergebnis ohne Datei starten
        # beziehungsweise markieren keinen erfolgreichen Capture.
        command_count = len(worker.commands)
        window.config_data["screen_region"] = {
            "x": 0, "y": 0, "width": 0, "height": 0,
        }
        with patch(
            "app.GuildPortraitGrabberQt.validate_screen_region",
            return_value=(False, "Testregion ungültig"),
        ):
            assert not window.capture_selected_portrait()
        assert len(worker.commands) == command_count
        assert "Testregion ungültig" in window.worker_error_label.text()

        window.config_data.update(TEST_CONFIG)
        assert window.capture_selected_portrait()
        missing_result = annie_portrait.parent / "fehlt.png"
        worker.events.put({
            "type": "portrait_saved", "name": "Ánníe",
            "path": str(missing_result), "method": "test",
        })
        window._poll_worker_events()
        assert annie_portrait.read_bytes() == successful_bytes
        assert window.portrait_preview.source_signature == successful_signature
        assert window.worker_error_label.isVisible()

        window.selected_character_id = "nicht-vorhanden"
        command_count = len(worker.commands)
        assert not window.capture_selected_portrait()
        assert len(worker.commands) == command_count
        window.show_character("m1001")

        # Der manuelle Qt-Import verwendet den gemeinsamen atomaren Bildkern.
        # Dialogabbruch ändert nichts; alle bereits unterstützten Formate werden
        # auf die kanonische PNG normalisiert und ersetzen nur diesen Charakter.
        ohnebild_row = next(
            row for row in range(window.character_model.rowCount())
            if window.character_model.item(row, 0).text() == "Ohnebild"
        )
        window.character_table.selectRow(ohnebild_row)
        application.processEvents()
        assert window.selected_character_id == "m1004"
        assert window.import_portrait_button.isEnabled()
        assert not window.remove_portrait_button.isEnabled()
        with patch(
            "app.GuildPortraitGrabberQt.QFileDialog.getOpenFileName",
            return_value=("", ""),
        ):
            assert not window.import_selected_portrait()
        assert normal_portrait_path("Ohnebild", project).exists() is False
        assert window.selected_character_id == "m1004"

        history_portrait = annie_portrait.parent / "history" / "m1004.png"
        history_portrait.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (80, 120), (9, 8, 7)).save(history_portrait)
        unrelated_portrait = annie_portrait.parent / "Ohnebild_extra.png"
        Image.new("RGB", (80, 120), (7, 8, 9)).save(unrelated_portrait)
        imported_portrait = normal_portrait_path("Ohnebild", project)
        for index, extension in enumerate(("png", "jpg", "jpeg", "webp", "bmp"), 1):
            source = temp_root / f"manual_{index}.{extension}"
            Image.new("RGB", (520 + index, 280 + index), (20 * index, 50, 90)).save(source)
            if index == 2:
                Image.new("RGB", (90, 150), (1, 2, 3)).save(
                    annie_portrait.parent / "Ohnebild.jpg"
                )
            with patch(
                "app.GuildPortraitGrabberQt.QFileDialog.getOpenFileName",
                return_value=(str(source), ""),
            ):
                assert window.import_selected_portrait()
            with Image.open(imported_portrait) as imported:
                assert imported.size == (384, 672)
                assert imported.format == "PNG"
            assert not (annie_portrait.parent / "Ohnebild.jpg").exists()
            assert history_portrait.is_file()
            assert unrelated_portrait.is_file()
            assert window.selected_character_id == "m1004"
            assert window.portrait_preview.source_signature is not None
            assert window.portrait_status_label.text() == "Portrait vorhanden"
            assert window.character_model.item(ohnebild_row, 4).text() == "Portrait vorhanden"
            assert window.remove_portrait_button.isEnabled()

        # Eine beschädigte Quelle darf das zuletzt gültige Portrait nicht ersetzen.
        imported_bytes = imported_portrait.read_bytes()
        imported_signature = window.portrait_preview.source_signature
        broken_source = temp_root / "broken.png"
        broken_source.write_bytes(b"kein Bild")
        with patch(
            "app.GuildPortraitGrabberQt.QFileDialog.getOpenFileName",
            return_value=(str(broken_source), ""),
        ), patch("app.GuildPortraitGrabberQt.QMessageBox.critical"):
            assert not window.import_selected_portrait()
        assert imported_portrait.read_bytes() == imported_bytes
        assert window.portrait_preview.source_signature == imported_signature
        assert window.selected_character_id == "m1004"
        assert window.worker_error_label.isVisible()

        # Entfernen bleibt bestätigungspflichtig, löscht sämtliche aktiven
        # Namensvarianten, aber weder Historie noch ähnlich benannte Dateien.
        stale_webp = annie_portrait.parent / "Ohnebild.webp"
        Image.new("RGB", (80, 120), (4, 5, 6)).save(stale_webp)
        with patch(
            "app.GuildPortraitGrabberQt.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ):
            assert not window.remove_selected_portrait()
        assert imported_portrait.is_file()
        assert stale_webp.is_file()
        with patch(
            "app.GuildPortraitGrabberQt.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ), patch(
            "app.GuildPortraitGrabberQt.remove_active_portrait_files",
            side_effect=PermissionError("gesperrt"),
        ), patch("app.GuildPortraitGrabberQt.QMessageBox.critical"):
            assert not window.remove_selected_portrait()
        assert imported_portrait.read_bytes() == imported_bytes
        assert stale_webp.is_file()
        assert window.portrait_preview.source_signature == imported_signature
        assert window.worker_error_label.isVisible()
        with patch(
            "app.GuildPortraitGrabberQt.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            assert window.remove_selected_portrait()
        assert not imported_portrait.exists()
        assert not stale_webp.exists()
        assert history_portrait.is_file()
        assert unrelated_portrait.is_file()
        assert window.selected_character_id == "m1004"
        assert window.portrait_preview.source_signature is None
        assert window.portrait_status_label.text() == "Kein Portrait vorhanden"
        assert window.character_model.item(ohnebild_row, 4).text() == "Noch kein Portrait"
        assert not window.remove_portrait_button.isEnabled()

        window.character_table.selectRow(annie_row)
        application.processEvents()

        assert window.open_selected_in_browser()
        action, payload = worker.commands[-1]
        assert action == "open"
        assert payload["name"] == "Ánníe"
        assert payload["member_id"] == "m1001"
        assert payload["source_id"] == "armory"
        assert payload["region"] == "EU"
        assert payload["realm"] == "stitches"
        assert payload["game_version"] == "classic1x"
        assert payload["preferred_channel"] == "msedge"
        assert payload["wait_after_load"] == 1.25
        assert payload["capture_mode"] == "playwright"
        assert payload["screen_region"] == (10, 20, 300, 525)
        assert not window.open_browser_button.isEnabled()

        seen_events = []
        original_handler = window._handle_worker_event

        def recording_handler(event):
            seen_events.append(event)
            original_handler(event)

        window._handle_worker_event = recording_handler
        worker.events.put({"type": "browser_ready", "browser": "msedge"})
        window._poll_worker_events()
        window._poll_worker_events()
        assert len(seen_events) == 1
        assert window.last_event_thread_id == threading.get_ident()
        assert "Browser bereit" in window.worker_status_label.text()
        window._handle_worker_event = original_handler

        worker.events.put({
            "type": "progress",
            "name": "Ánníe",
            "message": suite_i18n.tr("grabber.browser_recovery"),
        })
        window._poll_worker_events()
        assert suite_i18n.tr("grabber.browser_recovery") in window.worker_status_label.text()

        armory_result = {
            "characterName": "Ánníe",
            "memberId": "m1001",
            "race": "Night Elf",
            "className": "Druid",
        }
        worker.events.put({
            "type": "armory_data", "name": "Ánníe", "result": armory_result,
        })
        window._poll_worker_events()
        assert window.armory_results["m1001"] == armory_result
        assert window.character_class_value.text() == "Druid"
        assert "Ánníe" in window.armory_result_label.text()
        assert not window.open_browser_button.isEnabled()
        worker.events.put({
            "type": "opened", "name": "Ánníe", "method": "Microsoft Edge",
        })
        window._poll_worker_events()
        assert window.open_browser_button.isEnabled()

        assert window.read_selected_armory_data()
        assert worker.commands[-1][0] == "read_data"
        worker.events.put({
            "type": "armory_data", "name": "Ánníe", "result": armory_result,
        })
        window._poll_worker_events()
        assert window.read_armory_button.isEnabled()

        # Nur fehlende verwendet die gemeinsame v0.9.1-Bestandsregel. Die
        # vorhandene, aber ungültige Bífi-Datei gilt dabei wie im Tk-Grabber als
        # vorhanden; nur Ohnebild wird an den bestehenden Batch-Worker gegeben.
        with patch(
            "app.GuildPortraitGrabberQt.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            assert window.capture_missing_portraits()
        action, payload = worker.commands[-1]
        assert action == "capture_all"
        assert payload["names"] == ["Ohnebild"]
        assert payload["character_records"] == [{
            "memberId": "m1004", "characterName": "Ohnebild",
        }]
        assert payload["output_dir"] == str(annie_portrait.parent)
        assert payload["crop"] == TEST_CONFIG["crop"]
        assert payload["source_id"] == "armory"
        assert_plain_payload(payload)
        assert not window.capture_all_button.isEnabled()
        assert not window.capture_missing_button.isEnabled()
        assert window.stop_batch_button.isEnabled()

        worker.events.put({
            "type": "batch_progress", "index": 1, "total": 1,
            "name": "Ohnebild",
        })
        window._poll_worker_events()
        assert window.batch_progress.maximum() == 1
        assert window.batch_progress.value() == 0
        assert window.batch_progress_panel.isVisible()
        assert "0 % · 0 von 1" in window.batch_progress_label.text()

        missing_portrait = normal_portrait_path("Ohnebild", project)
        Image.new("RGB", (384, 672), (20, 160, 80)).save(missing_portrait)
        worker.events.put({
            "type": "portrait_saved", "name": "Ohnebild",
            "path": str(missing_portrait), "method": "test-batch",
        })
        window._poll_worker_events()
        assert window.selected_character_id == "m1001"
        ohnebild_row = next(
            row for row in range(window.character_model.rowCount())
            if window.character_model.item(row, 0).text() == "Ohnebild"
        )
        assert window.character_model.item(ohnebild_row, 4).text() == "Portrait vorhanden"

        batch_done = {
            "type": "batch_done", "total": 1, "processed": 1,
            "successes": 1, "failures": 0, "cancelled": False,
        }
        with patch.object(
            window, "_refresh_character_rows", wraps=window._refresh_character_rows,
        ) as refresh_rows:
            worker.events.put(batch_done)
            window._poll_worker_events()
            worker.events.put(batch_done)
            window._poll_worker_events()
            assert refresh_rows.call_count == 1
        assert window.batch_progress.value() == 1
        assert window.capture_all_button.isEnabled()
        assert not window.stop_batch_button.isEnabled()
        assert "1 erfolgreich" in window.worker_status_label.text()

        command_count = len(worker.commands)
        assert not window.capture_missing_portraits()
        assert len(worker.commands) == command_count
        assert "Keine fehlenden Portraits" in window.worker_status_label.text()

        # STOPP wird pro Batch genau einmal an den bestehenden Worker gegeben;
        # bereits eingetroffene Teilresultate bleiben sichtbar.
        with patch(
            "app.GuildPortraitGrabberQt.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            assert window.capture_all_portraits()
        action, payload = worker.commands[-1]
        assert action == "capture_all"
        assert payload["names"] == ["Bífi", "Ohnebild", "Ánníe"]
        assert [record["memberId"] for record in payload["character_records"]] == [
            "m1002", "m1004", "m1001",
        ]
        assert_plain_payload(payload)
        Image.new("RGB", (384, 672), (120, 40, 150)).save(invalid_portrait)
        worker.events.put({
            "type": "batch_progress", "index": 1, "total": 3, "name": "Bífi",
        })
        worker.events.put({
            "type": "portrait_saved", "name": "Bífi",
            "path": str(invalid_portrait), "method": "test-batch",
        })
        window._poll_worker_events()
        cancel_count = worker.cancel_request_count
        assert window.request_batch_stop()
        assert not window.request_batch_stop()
        assert worker.cancel_request_count == cancel_count + 1
        assert not window.stop_batch_button.isEnabled()
        assert window.stop_batch_button.text() == "STOPP angefordert …"
        worker.events.put({
            "type": "batch_done", "total": 3, "processed": 1,
            "successes": 1, "failures": 0, "cancelled": True,
        })
        window._poll_worker_events()
        assert window.batch_progress.value() == 1
        assert window.stop_batch_button.text() == "STOPP"
        assert "Stapel abgebrochen" in window.worker_status_label.text()
        assert window.selected_character_id == "m1001"

        # Ein einzelner Fehler bleibt ein Teilfehler; erst batch_done beendet den
        # Batch und zeigt die vorhandene fachliche Zusammenfassung.
        with patch(
            "app.GuildPortraitGrabberQt.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            assert window.capture_all_portraits()
        worker.events.put({
            "type": "batch_progress", "index": 1, "total": 3, "name": "Bífi",
        })
        worker.events.put({
            "type": "item_error", "name": "Bífi", "message": "Einzelfehler",
        })
        window._poll_worker_events()
        assert window._active_worker_action == "capture_all"
        assert "Einzelfehler" in window.worker_status_label.text()
        worker.events.put({
            "type": "batch_done", "total": 3, "processed": 3,
            "successes": 2, "failures": 1, "cancelled": False,
        })
        window._poll_worker_events()
        assert window._active_worker_action is None
        assert "2 erfolgreich" in window.worker_status_label.text()
        assert "1 Fehler" in window.worker_status_label.text()

        assert window.read_selected_armory_data()
        worker.events.put({
            "type": "error", "message": "Testfehler", "detail": "Nur Test",
            "log_path": "test.log",
        })
        window._poll_worker_events()
        assert window.worker_error_label.isVisible()
        assert "Testfehler" in window.worker_error_label.text()
        assert window.read_armory_button.isEnabled()

        first_signature = window.portrait_preview.source_signature
        window.show_character("m1001")
        assert window.portrait_preview.source_signature == first_signature
        window.character_table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        assert window.load_project(project)
        assert window.selected_character_id == "m1001"
        assert window.selected_graveyard_member_id == "m1006"
        assert window.session_id == "phase31-session"

        suite_i18n._translator.language = "en"
        window.refresh_texts()
        assert window.project_status_label.text() == "Project: Phase31.ggc"
        assert window.tabs.tabText(1) == "Graveyard"
        assert window.graveyard_model.horizontalHeaderItem(0).text() == "Character"
        assert window.character_model.horizontalHeaderItem(0).text() == "Character"
        assert window.character_model.horizontalHeaderItem(4).text() == "Portrait"
        assert window.character_model.horizontalHeaderItem(3).text() == "Status"
        assert window.character_life_value.text() == "Alive"
        assert window.roster_actions_group.title() == "Guild Roster"
        assert window.character_actions_group.title() == "Character"
        assert window.portrait_actions_group.title() == "Portrait Actions"
        assert window.graveyard_preview_status_label.text() == "No Gravestone"
        assert window.character_race_value.text() == "Night Elf"
        assert window.portrait_status_label.text() == "Portrait available"
        assert window.open_browser_button.text() == "Open in Browser"
        assert window.capture_portrait_button.text() == "Create Portrait"
        assert window.read_armory_button.text() == "Read Character Data"
        assert window.capture_missing_button.text() == "Create Missing"
        assert window.capture_all_button.text() == "Create All Portraits"
        assert window.stop_batch_button.text() == "STOP"
        assert window.import_portrait_button.text() == "Manual Portrait"
        assert window.remove_portrait_button.text() == "Remove Portrait"
        assert window.edit_portrait_button.text() == "Edit Portrait"
        assert window.edit_selected_portrait()
        application.processEvents()
        english_editor = window._portrait_editor_dialog
        assert english_editor is not None
        assert english_editor.windowTitle() == "Edit Portrait · Ánníe"
        assert english_editor.pan_mode_button.text() == "Move / Zoom"
        assert english_editor.crop_mode_button.text() == "Select Crop"
        assert english_editor.apply_button.text() == "Apply"
        assert english_editor.cancel_button.text() == "Cancel"
        english_editor.close()
        application.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        application.processEvents()
        assert window._portrait_editor_dialog is None
        assert "Testfehler" in window.worker_error_label.text()
        assert window.tabs.tabText(2) == "Settings"
        assert window.crop_settings_group.title() == "Capture & Crop"
        assert window.general_diagnostics_group.title() == "General / Diagnostics"
        assert window.playwright_crop_group.title() == "Playwright / v0.1.2 – Portrait Crop"
        assert window.calibrate_crop_button.text() == "Calibrate Crop"
        assert window.standard_crop_group.title() == "Optional – Default Browser + Screen Region"
        assert window.armory_settings_group.title() == "Armory / Capture"
        assert window.capture_mode_combo.itemText(0) == "Playwright / v0.1.2"
        assert window.capture_mode_combo.itemData(0) == "playwright"
        assert window.capture_mode_combo.itemText(1) == "Default Browser + Screen Region"
        assert window.capture_mode_combo.itemData(1) == "standard_browser_region"
        assert window.browser_test_button.text() == "Test Browser (v0.1.2)"

        second_project = temp_root / "Second.ggc"
        second_project.write_text(json.dumps({
            "members": [{
                "id": "m2001", "name": "Second", "className": "Rogue",
                "lifeStatus": "active",
            }],
        }), encoding="utf-8")
        for _index in range(3):
            assert window.load_project(second_project)
            assert window.character_model.rowCount() == 1
            assert window.graveyard_model.rowCount() == 0
            assert len(window.character_members) == 1
            assert window.selected_character_id == "m2001"
            assert window.session_id is None
            assert window.handoff_path is None
            assert window.load_project(project)
            assert window.character_model.rowCount() == 3
            assert window.graveyard_model.rowCount() == 3
            assert len(window.character_members) == 3
        assert window.selected_character_id in {"m1001", "m1002", "m1004"}

        empty_project = temp_root / "Empty.ggc"
        empty_project.write_text(json.dumps({"members": []}), encoding="utf-8")
        with patch(
            "app.GuildPortraitGrabberQt.QFileDialog.getOpenFileName",
            return_value=(str(empty_project), ""),
        ):
            window._choose_project()
        assert window.project_path == empty_project.resolve()
        assert window.character_model.rowCount() == 0
        assert window.graveyard_model.rowCount() == 0
        assert window.selected_character_id is None
        assert window.selected_graveyard_member_id is None
        assert window.portrait_preview.source_signature is None
        assert window.character_name_value.text() == "-"
        assert window.load_project(project)
        window.config_data.update(TEST_CONFIG)
        with patch(
            "app.GuildPortraitGrabberQt.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            assert window.capture_all_portraits()
        assert window.worker_poll_timer.isActive()
        close_cancel_count = worker.cancel_request_count
        window.close()
        window.deleteLater()
        application.processEvents()
        assert worker.cancel_requested
        assert worker.cancel_request_count == close_cancel_count + 1
        assert worker.commands[-1][0] == "stop"
        assert not window.worker_poll_timer.isActive()

        invalid = temp_root / "invalid.ggc"
        invalid.write_text("{}", encoding="utf-8")
        invalid_window = GuildPortraitGrabberQt(
            invalid,
            session_id="invalid-session",
            worker_factory=fake_worker_factory,
            config_data=TEST_CONFIG,
        )
        invalid_window.show()
        application.processEvents()
        assert invalid_window.project_path is None
        assert invalid_window.project_payload is None
        assert invalid_window.project_error
        assert invalid_window.handoff_path is None
        assert invalid_window.project_status_label.text() == "No project loaded"
        assert "Could not open project" in invalid_window.statusBar().currentMessage()
        invalid_window.close()
        invalid_window.deleteLater()
        application.processEvents()

        # Nachmigration Phase 4: Charakter-/Import-/Handoff-Bedienwege verwenden
        # ausschließlich die bestehenden Parser-, Dedupe-, Projekt- und Workerpfade.
        suite_i18n._translator.language = "de"
        phase4_project = temp_root / "Phase4.ggc"
        phase4_project.write_text(json.dumps({
            "formatVersion": 4,
            "members": [
                {"id": "p4-existing", "name": "Bestehend", "lifeStatus": "active"},
                {"id": "p4-missing", "name": "Fehlend", "lifeStatus": "active"},
                {"id": "p4-dead", "name": "Wieder", "lifeStatus": "dead"},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        phase4_window = GuildPortraitGrabberQt(
            phase4_project,
            worker_factory=fake_worker_factory,
            config_data=TEST_CONFIG,
        )
        phase4_worker = workers[-1]
        phase4_window.show()
        application.processEvents()
        assert phase4_window.add_character_button.text() == "Charakter hinzufügen"
        assert phase4_window.read_missing_data_button.text() == "Alle fehlenden Daten"

        existing_row = next(
            row for row in range(phase4_window.character_model.rowCount())
            if phase4_window.character_model.item(row, 0).text() == "Bestehend"
        )
        phase4_window.character_table.selectRow(existing_row)
        application.processEvents()
        command_count = len(phase4_worker.commands)
        phase4_window.character_table.doubleClicked.emit(
            phase4_window.character_model.index(existing_row, 0)
        )
        assert len(phase4_worker.commands) == command_count + 1
        assert phase4_worker.commands[-1][0] == "open"
        phase4_worker.events.put({
            "type": "opened", "name": "Bestehend", "method": "Testbrowser",
        })
        phase4_window._poll_worker_events()

        with patch(
            "app.GuildPortraitGrabberQt.QInputDialog.getText",
            return_value=("Bífi", True),
        ):
            assert phase4_window.add_character()
        member_count = len(phase4_window.character_members)
        with patch(
            "app.GuildPortraitGrabberQt.QInputDialog.getText",
            return_value=("bífi", True),
        ):
            assert not phase4_window.add_character()
        assert len(phase4_window.character_members) == member_count
        assert [member.name for member in phase4_window.character_members].count("Bífi") == 1

        txt_import = temp_root / "phase4_names.txt"
        txt_import.write_text(
            "Bífi\nNeueins\nneueins\nÄnne\nWieder\n", encoding="utf-8"
        )
        with patch(
            "app.GuildPortraitGrabberQt.QFileDialog.getOpenFileName",
            return_value=(str(txt_import), ""),
        ):
            assert phase4_window.import_character_list()
        assert {"Bífi", "Neueins", "Änne", "Wieder"}.issubset({
            member.name for member in phase4_window.character_members
        })
        assert len([
            member for member in phase4_window.character_members
            if member.name.casefold() == "neueins"
        ]) == 1

        csv_import = temp_root / "phase4_wcl.csv"
        csv_import.write_text(
            "Name,Attendance\nWclmage,1\nwclmage,1\nNeueins,1\n", encoding="utf-8"
        )
        with patch(
            "app.GuildPortraitGrabberQt.QFileDialog.getOpenFileName",
            return_value=(str(csv_import), ""),
        ):
            assert phase4_window.import_wcl_csv()
        assert len([
            member for member in phase4_window.character_members
            if member.name.casefold() == "wclmage"
        ]) == 1

        project_before_remove = phase4_project.read_text(encoding="utf-8")
        existing_row = next(
            row for row in range(phase4_window.character_model.rowCount())
            if phase4_window.character_model.item(row, 0).text() == "Bestehend"
        )
        phase4_window.character_table.selectRow(existing_row)
        application.processEvents()
        with patch(
            "app.GuildPortraitGrabberQt.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            assert phase4_window.remove_selected_character()
        assert "Bestehend" not in {
            member.name for member in phase4_window.character_members
        }
        assert phase4_project.read_text(encoding="utf-8") == project_before_remove

        with patch("app.GuildPortraitGrabberQt.QMessageBox.information"):
            assert phase4_window.save_guild_list()
        saved_payload = json.loads(phase4_project.read_text(encoding="utf-8"))
        saved_members = saved_payload["members"]
        assert any(member["name"] == "Bestehend" for member in saved_members)
        assert any(
            member["name"] == "Wieder" and member["lifeStatus"] == "dead"
            for member in saved_members
        )
        assert any(
            member["name"] == "Wieder" and member["lifeStatus"] == "active"
            for member in saved_members
        )
        assert all(
            not member.id.startswith("working:") for member in phase4_window.character_members
        )

        assert phase4_window._add_working_names(["Handoffname"]) == 1
        handoff_member = next(
            member for member in phase4_window.character_members
            if member.name == "Handoffname"
        )
        phase4_window.session_id = "phase4-session"
        with patch(
            "app.GuildPortraitGrabberQt.queue_action",
            return_value="phase4-token",
        ) as queued_action:
            assert phase4_window.save_guild_list()
        assert queued_action.call_args.args[2] == "add_members"
        assert phase4_window._pending_roster_save_token == "phase4-token"
        assert not phase4_window.save_guild_list_button.isEnabled()
        handoff_receipt = {
            "ok": True,
            "summary": {
                "added": 1,
                "existing": len(phase4_window.character_members) - 1,
                "newIncarnations": 0,
                "created": [{
                    "memberId": "p4-handoff",
                    "characterName": "Handoffname",
                    "race": None,
                    "className": "",
                }],
            },
        }
        with patch(
            "app.GuildPortraitGrabberQt.read_receipt",
            return_value=handoff_receipt,
        ), patch("app.GuildPortraitGrabberQt.QMessageBox.information"):
            phase4_window._poll_guild_save_receipt()
        assert phase4_window._pending_roster_save_token is None
        assert handoff_member.id == "p4-handoff"
        assert phase4_window.save_guild_list_button.isEnabled()

        data_project = temp_root / "Phase4Data.ggc"
        data_project.write_text(json.dumps({
            "formatVersion": 4,
            "members": [
                {
                    "id": "data-complete", "name": "Komplett", "race": "Human",
                    "className": "Mage", "lifeStatus": "active",
                },
                {"id": "data-missing", "name": "Datenlos", "lifeStatus": "active"},
                {
                    "id": "data-partial", "name": "Teilweise", "race": "Dwarf",
                    "lifeStatus": "active",
                },
            ],
        }, ensure_ascii=False), encoding="utf-8")
        data_window = GuildPortraitGrabberQt(
            data_project,
            worker_factory=fake_worker_factory,
            config_data=TEST_CONFIG,
        )
        data_worker = workers[-1]
        data_window.show()
        application.processEvents()
        with patch(
            "app.GuildPortraitGrabberQt.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            assert data_window.read_missing_armory_data()
        action, payload = data_worker.commands[-1]
        assert action == "read_data_all"
        assert [record["memberId"] for record in payload["records"]] == [
            "data-missing", "data-partial",
        ]
        assert_plain_payload(payload)
        assert data_window.stop_batch_button.isEnabled()
        data_worker.events.put({
            "type": "batch_progress", "index": 1, "total": 2, "name": "Datenlos",
        })
        data_worker.events.put({
            "type": "armory_data",
            "name": "Datenlos",
            "result": {
                "memberId": "data-missing", "characterName": "Datenlos",
                "race": "Night Elf", "className": "Druid",
            },
        })
        data_worker.events.put({
            "type": "armory_data_error", "name": "Teilweise",
            "member_id": "data-partial", "message": "Test-Teilfehler",
            "request_type": "batch",
        })
        data_window._poll_worker_events()
        assert data_window._active_worker_action == "read_data_all"
        assert data_window.armory_results["data-missing"]["className"] == "Druid"
        data_row = next(
            row for row in range(data_window.character_model.rowCount())
            if data_window.character_model.item(row, 0).text() == "Datenlos"
        )
        assert data_window.character_model.item(data_row, 2).text() == "Druid"
        cancel_count = data_worker.cancel_request_count
        assert data_window.request_batch_stop()
        assert not data_window.request_batch_stop()
        assert data_worker.cancel_request_count == cancel_count + 1
        data_worker.events.put({
            "type": "batch_done", "total": 2, "processed": 2,
            "successes": 1, "failures": 1, "cancelled": True,
        })
        data_window._poll_worker_events()
        assert data_window._active_worker_action is None
        assert not data_window.stop_batch_button.isEnabled()
        persisted_data = json.loads(data_project.read_text(encoding="utf-8"))
        persisted_missing = next(
            member for member in persisted_data["members"]
            if member["id"] == "data-missing"
        )
        assert persisted_missing["race"] == "Night Elf"
        assert persisted_missing["className"] == "Druid"

        suite_i18n._translator.language = "en"
        phase4_window.refresh_texts()
        data_window.refresh_texts()
        assert phase4_window.add_character_button.text() == "Add Character"
        assert phase4_window.import_list_button.text() == "Import List"
        assert phase4_window.import_wcl_button.text() == "Load Warcraft Logs CSV"
        assert phase4_window.save_guild_list_button.text() == "Save Guild Roster"
        assert data_window.read_missing_data_button.text() == "Read Missing Data"
        data_window.close()
        data_window.deleteLater()
        phase4_window.close()
        phase4_window.deleteLater()
        application.processEvents()

    real_worker_window = GuildPortraitGrabberQt(config_data=TEST_CONFIG)
    real_worker_window.show()
    application.processEvents()
    assert real_worker_window.worker.is_alive()
    real_worker_window.close()
    real_worker_window.worker.join(timeout=2.0)
    assert not real_worker_window.worker.is_alive()
    real_worker_window.deleteLater()
    application.processEvents()
finally:
    suite_i18n._translator.language = old_language

# Der bisherige Tkinter-Grabber bleibt derselbe importierbare Produktivweg.
from app import GuildPortraitGrabber as legacy_grabber

assert legacy_grabber.APP_VERSION == APP_VERSION
assert callable(legacy_grabber.App)
assert legacy_grabber.parse_cli([]).project == ""

print("Qt Portrait Grabber Smoke: OK")
