"""Offscreen V2 cemetery and Qt grabber checks on disposable projects."""

import os
import queue
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app import GuildGearCheckerQt as checker_qt
from app.GuildPortraitGrabberQt import GuildPortraitGrabberQt
from app.GuildPortraitGrabber import BrowserWorker
from app.gravestone_templates import load_gravestone_inventory
from app.identity_v2 import IdentityV2Store, Member
from app.identity_v2_character_service import set_member_burial_type
from app.identity_v2_storage import load_identity_v2, save_identity_v2, save_new_identity_v2
from app.project_storage import member_portrait_path


class FakeWorker:
    def __init__(self, _events):
        pass

    def start(self):
        pass

    def submit(self, *_args, **_kwargs):
        pass


class IdentityV2GraveyardQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        assets = Path(__file__).resolve().parents[1] / "assets" / "graveyard"
        inventory = load_gravestone_inventory(assets, assets / "gravestones_manifest.json")
        self.inventory = inventory
        self.template = next(item for item in inventory.templates if item.category is not None)
        self.other_template = next(item for item in inventory.templates
                                   if item.category is not None
                                   and item.grave_template_id != self.template.grave_template_id)
        self.store = IdentityV2Store(members=[
            Member("m1000", "Annî", "Mage", lifeStatus="dead", burialType="individual",
                   deathDate="2026-03-15", graveTemplateId=self.template.grave_template_id),
            Member("m1001", "Ohne", "Priest", lifeStatus="dead", burialType="individual",
                   deathDate="2026-03-16",
                   graveTemplateId=self.other_template.grave_template_id),
            Member("m1002", "Annî", "Mage", lifeStatus="dead", burialType="collective",
                   deathDate="2026-04-15"),
            Member("m1003", "Lebendig", "Druid"),
        ])
        self.target = self.root / "v2-graveyard.ggc"
        save_new_identity_v2(self.store, self.target)
        portrait_dir = self.root / "portraits"
        portrait_dir.mkdir()
        Image.new("RGB", (90, 120), "#916b50").save(portrait_dir / "m1000.png")

    def _checker(self):
        with patch.object(checker_qt, "read_suite_settings", return_value={}):
            window = checker_qt.GuildGearCheckerQt()
        self.addCleanup(lambda: self._close_checker(window))
        with (patch.object(checker_qt.QFileDialog, "getOpenFileName",
                           return_value=(str(self.target), "")),
              patch.object(checker_qt.QMessageBox, "critical") as error):
            window.open_project()
        self.assertFalse(error.called)
        return window

    @staticmethod
    def _close_checker(window):
        with (patch.object(checker_qt, "update_suite_settings"),
              patch.object(checker_qt.QMessageBox, "question",
                           return_value=checker_qt.QMessageBox.StandardButton.Yes)):
            window.close()

    def test_v2_cemetery_reuses_gallery_and_is_read_only(self):
        window = self._checker()
        original = window.identity_v2_store.to_payload()
        original_bytes = self.target.read_bytes()
        self.assertTrue(window._nav_buttons["graveyard"].isEnabled())
        window._nav_buttons["rooster"].click()
        self.assertIs(window.stack.currentWidget(), window._pages["rooster"])
        window._nav_buttons["graveyard"].click()
        self.app.processEvents()
        self.assertIs(window.stack.currentWidget(), window.grave_view)
        self.assertTrue(window._nav_buttons["graveyard"].isChecked())
        self.assertFalse(window.grave_canvas.activation_enabled)
        self.assertEqual({item[0] for item in window.grave_canvas._cards},
                         {"m1000", "m1001"})
        self.assertTrue(all(not pixmap.isNull() for _, pixmap in window.grave_canvas._cards))
        self.assertIsNotNone(window._v2_grave_inventory_by_id().get(
            self.store.members[0].graveTemplateId))
        self.assertEqual(self.store.members[1].graveTemplateId,
                         self.other_template.grave_template_id)
        self.assertEqual(window.grave_view.collective_count, 1)
        self.assertFalse(hasattr(window.grave_view, "collective_table"))
        self.assertIn("Sammelgrab", window.grave_canvas._summary)
        self.assertTrue(window._v2_grave_portrait("m1000")[1])
        self.assertFalse(window._v2_grave_portrait("m1001")[1])
        self.assertEqual(window._v2_grave_portrait("m1001")[0].name,
                         "portrait_placeholder.png")
        self.assertFalse(window.identity_v2_dirty)
        with patch.object(checker_qt, "update_suite_settings"):
            window.grave_view.slider.setValue(90)
            window._graveyard_zoom_timer.stop()
            window._apply_graveyard_zoom()
            window._graveyard_zoom_save_timer.stop()
        window.refresh_graveyard()
        self.assertEqual(window.grave_canvas.zoom_percent, 90)
        with patch.object(checker_qt, "render_gravestone_card",
                          side_effect=AssertionError("unnötiger Neu-Render")):
            window._nav_buttons["raid"].click()
            window._nav_buttons["graveyard"].click()
        self.assertIs(window.stack.currentWidget(), window.grave_view)
        self.assertEqual({item[0] for item in window.grave_canvas._cards},
                         {"m1000", "m1001"})
        self.assertEqual(window.grave_view.collective_count, 1)
        self.assertEqual(window.identity_v2_store.to_payload(), original)
        self.assertEqual(self.target.read_bytes(), original_bytes)
        self.assertFalse(window.identity_v2_dirty)

    def test_missing_assets_keep_placeholders_without_hint_text(self):
        window = self._checker()
        before_store = window.identity_v2_store.to_payload()
        before_file = self.target.read_bytes()
        size = (220, 300)
        fallback_frame = window._cached_graveyard_template(None, size)
        window._cached_graveyard_template(self.other_template, size)
        member = window.identity_v2_store.members[1]
        placeholder, has_portrait = window._v2_grave_portrait(member.memberId)
        self.assertFalse(has_portrait)
        self.assertEqual(placeholder.name, "portrait_placeholder.png")
        window._graveyard_card_cache.clear()
        with (patch.object(checker_qt, "render_gravestone_card",
                           return_value=Image.new("RGBA", size)) as render,
              patch("PIL.ImageDraw.Draw") as draw_factory):
            pixmap = window._v2_grave_pixmap(member, None, size)
        self.assertFalse(pixmap.isNull())
        self.assertIs(render.call_args.args[1], fallback_frame)
        self.assertEqual(render.call_args.args[2], placeholder)
        draw_factory.assert_not_called()

        window._graveyard_card_cache.clear()
        with (patch.object(checker_qt, "render_gravestone_card",
                           return_value=Image.new("RGBA", size)) as render,
              patch("PIL.ImageDraw.Draw") as draw_factory):
            window._v2_grave_pixmap(
                window.identity_v2_store.members[0], self.template, size)
        self.assertEqual(render.call_args.args[2],
                         member_portrait_path(self.target, "m1000"))
        draw_factory.assert_not_called()

        legacy_member = SimpleNamespace(
            id="legacy-missing", name="Ohne Stein", className="Mage",
            deathDate="2026-01-01", graveTemplateId=None,
            portraitOffsetX=0, portraitOffsetY=0, portraitZoom=1,
            textOffsetX=0, textOffsetY=0, textScale=1,
        )
        with (patch.object(checker_qt, "render_gravestone_card",
                           return_value=Image.new("RGBA", size)) as render,
              patch("PIL.ImageDraw.Draw") as draw_factory):
            window._grave_pixmap_for_member(legacy_member, None, size)
        self.assertIs(render.call_args.args[1], fallback_frame)
        self.assertIsNone(render.call_args.args[2])
        draw_factory.assert_not_called()
        self.assertEqual(window.identity_v2_store.to_payload(), before_store)
        self.assertEqual(self.target.read_bytes(), before_file)
        self.assertFalse(window.identity_v2_dirty)

    def test_burial_refresh_reuses_saved_stone_without_cemetery_edits(self):
        window = self._checker()
        window.switch_page("graveyard")
        changed = set_member_burial_type(window.identity_v2_store, "m1000", "collective")
        window._apply_v2_character_store(changed)
        window.refresh_graveyard()
        self.assertEqual({item[0] for item in window.grave_canvas._cards}, {"m1001"})
        self.assertEqual(window.grave_view.collective_count, 2)
        changed = set_member_burial_type(window.identity_v2_store, "m1000", "individual")
        window._apply_v2_character_store(changed)
        window.refresh_graveyard()
        self.assertEqual({item[0] for item in window.grave_canvas._cards},
                         {"m1000", "m1001"})
        self.assertEqual(window.identity_v2_store.members[0].graveTemplateId,
                         self.template.grave_template_id)
        self.assertEqual(window.grave_view.collective_count, 1)
        changed = set_member_burial_type(
            window.identity_v2_store, "m1002", "individual",
            gravestone_templates=self.inventory.templates)
        window._apply_v2_character_store(changed)
        window.refresh_graveyard()
        self.assertEqual({item[0] for item in window.grave_canvas._cards},
                         {"m1000", "m1001", "m1002"})
        self.assertFalse(window._v2_grave_portrait("m1002")[1])
        self.assertIsNotNone(window.identity_v2_store.members[2].graveTemplateId)

    def test_old_individual_is_repaired_in_memory_until_explicit_save(self):
        self.store.members[1].graveTemplateId = None
        save_identity_v2(self.store, self.target)
        before = self.target.read_bytes()
        window = self._checker()
        repaired = window.identity_v2_store.members[1]
        self.assertTrue(window.identity_v2_dirty)
        self.assertIsNotNone(repaired.graveTemplateId)
        self.assertEqual(self.target.read_bytes(), before)
        window._nav_buttons["graveyard"].click()
        self.assertEqual({item[0] for item in window.grave_canvas._cards},
                         {"m1000", "m1001"})
        self.assertFalse(window._v2_grave_portrait("m1001")[1])
        self.assertIn(repaired.graveTemplateId, window._v2_grave_inventory_by_id())
        window.save_project()
        self.assertFalse(window.identity_v2_dirty)
        self.assertEqual(load_identity_v2(self.target).members[1].graveTemplateId,
                         repaired.graveTemplateId)

    def test_insufficient_stones_leave_old_project_unmodified(self):
        self.store.members[0].graveTemplateId = None
        self.store.members[1].graveTemplateId = None
        save_identity_v2(self.store, self.target)
        before = self.target.read_bytes()
        with (patch.object(checker_qt.GuildGearCheckerQt,
                           "_v2_grave_inventory_by_id",
                           return_value={self.template.grave_template_id: self.template}),
              patch.object(checker_qt.QMessageBox, "warning") as warning):
            window = self._checker()
        self.assertTrue(warning.called)
        self.assertFalse(window.identity_v2_dirty)
        self.assertIsNone(window.identity_v2_store.members[0].graveTemplateId)
        self.assertIsNone(window.identity_v2_store.members[1].graveTemplateId)
        self.assertEqual(self.target.read_bytes(), before)

    def test_external_grabber_change_reload_preserves_dirty_guard(self):
        window = self._checker()
        changed = set_member_burial_type(self.store, "m1001", "collective")
        save_identity_v2(changed, self.target)
        window._nav_buttons["graveyard"].click()
        self.assertFalse(window.identity_v2_dirty)
        self.assertEqual(window.grave_view.collective_count, 2)
        self.assertEqual(window.identity_v2_store.to_payload(), changed.to_payload())

    def test_checker_starts_v2_grabber_only_from_saved_state(self):
        window = self._checker()
        self.assertTrue(window.grabber_button.isEnabled())
        with patch.object(checker_qt.subprocess, "Popen") as launch:
            window.open_portrait_grabber()
        launch.assert_called_once()
        command = launch.call_args.args[0]
        self.assertIn("--project", command)
        self.assertIn(str(self.target.resolve()), command)
        self.assertNotIn("--session-id", command)
        window.identity_v2_dirty = True
        with (patch.object(checker_qt.subprocess, "Popen") as launch,
              patch.object(checker_qt.QMessageBox, "warning") as warning):
            window.open_portrait_grabber()
        self.assertFalse(launch.called)
        self.assertTrue(warning.called)

    def test_external_v2_change_blocks_stale_checker_save(self):
        window = self._checker()
        local = set_member_burial_type(window.identity_v2_store, "m1001", "collective")
        window._apply_v2_character_store(local)
        external = set_member_burial_type(self.store, "m1000", "collective")
        save_identity_v2(external, self.target)
        external_bytes = self.target.read_bytes()
        window._nav_buttons["graveyard"].click()
        self.assertEqual(window.identity_v2_store.to_payload(), local.to_payload())
        with patch.object(checker_qt.QMessageBox, "warning") as warning:
            window.save_project()
        self.assertTrue(warning.called)
        self.assertTrue(window.identity_v2_dirty)
        self.assertEqual(self.target.read_bytes(), external_bytes)

    def test_qt_grabber_loads_v2_by_member_id_without_legacy_migration(self):
        before = self.target.read_bytes()
        grabber = GuildPortraitGrabberQt(
            project_path=self.target, worker_factory=FakeWorker, config_data={})
        self.addCleanup(grabber.close)
        self.assertTrue(grabber.v2_mode)
        self.assertIs(grabber.tabs.currentWidget(), grabber.graveyard_page)
        self.assertTrue(grabber.tabs.isTabEnabled(grabber.tabs.indexOf(
            grabber.portraits_page)))
        self.assertEqual(set(grabber._graveyard_member_by_id),
                         {"m1000", "m1001", "m1002"})
        self.assertEqual(grabber._graveyard_member_by_id["m1000"].name,
                         grabber._graveyard_member_by_id["m1002"].name)
        self.assertEqual(self.target.read_bytes(), before)

    def test_qt_grabber_saves_stone_and_portrait_to_exact_v2_member(self):
        checker = self._checker()
        checker.switch_page("graveyard")
        grabber = GuildPortraitGrabberQt(
            project_path=self.target, worker_factory=FakeWorker, config_data={})
        self.addCleanup(grabber.close)
        before = load_identity_v2(self.target)
        grabber.show_graveyard_member("m1001")
        self.assertTrue(grabber.open_selected_gravestone_editor())
        dialog = grabber._gravestone_editor_dialog
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.state.member_id, "m1001")
        self.assertFalse(dialog.death_date_edit.isEnabled())
        selected_template = dialog.state.draft.template_id
        self.assertTrue(selected_template)
        self.assertTrue(grabber._save_gravestone_editor_draft())
        changed = load_identity_v2(self.target)
        self.assertEqual(changed.members[1].graveTemplateId, selected_template)
        self.assertEqual(changed.members[0].to_dict(), before.members[0].to_dict())
        self.assertEqual(changed.members[1].deathDate, before.members[1].deathDate)
        self.assertEqual(changed.members[1].burialType, "individual")
        self.assertEqual(changed.raids, before.raids)
        self.assertEqual(changed.attendance, before.attendance)
        checker.refresh_graveyard()
        self.assertEqual(checker.identity_v2_store.members[1].graveTemplateId,
                         selected_template)
        self.assertFalse(checker.identity_v2_dirty)

        grabber.show_graveyard_member("m1002")
        source = self.root / "portrait-source.png"
        Image.new("RGB", (80, 100), "#406d81").save(source)
        with patch("app.GuildPortraitGrabberQt.QFileDialog.getOpenFileName",
                   return_value=(str(source), "")):
            self.assertTrue(grabber.import_selected_graveyard_portrait())
        self.assertTrue((self.root / "portraits" / "m1002.png").is_file())
        self.assertTrue((self.root / "portraits" / "m1000.png").is_file())
        self.assertFalse((self.root / "portraits" / "Annî.png").exists())
        self.assertEqual(load_identity_v2(self.target).to_payload(), changed.to_payload())
        checker.refresh_graveyard()
        self.assertTrue(checker._v2_grave_portrait("m1002")[1])


    def test_v2_portrait_tab_edits_selected_member_id_without_project_save(self):
        self.store.members.extend((
            Member("m1004", "Lebendig", "Druid"),
            Member("m1005", "Lebendig", "Druid", lifeStatus="inactive"),
        ))
        save_identity_v2(self.store, self.target)
        before = self.target.read_bytes()
        checker = self._checker()
        checker.switch_page("rooster")
        self.assertTrue(next(card for card in checker._roster_cards
                             if card.member_id == "m1003").portrait._source.isNull())
        grabber = GuildPortraitGrabberQt(
            project_path=self.target, worker_factory=FakeWorker, config_data={})
        self.addCleanup(grabber.close)
        self.assertTrue(grabber.tabs.isTabEnabled(grabber.tabs.indexOf(
            grabber.portraits_page)))
        self.assertTrue(grabber.roster_actions_group.isHidden())
        self.assertEqual(set(grabber._member_by_id), {"m1003", "m1004", "m1005"})
        self.assertEqual({grabber.character_model.item(row, 0).toolTip()
                          for row in range(grabber.character_model.rowCount())},
                         {"m1003", "m1004"})
        grabber.show()
        grabber.tabs.setCurrentWidget(grabber.portraits_page)
        grabber.show_character("m1003")
        self.app.processEvents()
        QTest.mouseMove(grabber.character_table.viewport(),
                        grabber.character_table.visualRect(
                            grabber.character_model.index(0, 0)).center())
        self.assertEqual(grabber.character_row_hover.row, 0)
        self.assertEqual(grabber.selected_character_id, "m1003")
        source = self.root / "v2-portrait-source.png"
        Image.new("RGB", (80, 100), "#406d81").save(source)
        with patch("app.GuildPortraitGrabberQt.QFileDialog.getOpenFileName",
                   return_value=(str(source), "")):
            self.assertTrue(grabber.import_selected_portrait())
        portrait = member_portrait_path(self.target, "m1003")
        self.assertTrue(portrait.is_file())
        self.assertIsNone(grabber._portrait_file_for(grabber._member_by_id["m1004"]))
        self.assertFalse((self.root / "portraits" / "Lebendig.png").exists())
        self.assertTrue(grabber.edit_selected_portrait())
        dialog = grabber._portrait_editor_dialog
        self.assertEqual(dialog.destination, portrait)
        initial_zoom = dialog.preview.state.zoom
        dialog.preview.zoom_by_step(1)
        self.assertGreater(dialog.preview.state.zoom, initial_zoom)
        dialog.preview.pan_by_scene_delta(10, 5)
        dialog.preview.reset_editor()
        self.assertEqual(dialog.preview.state.zoom, initial_zoom)
        dialog.close()
        grabber.show_character("m1004")
        self.assertEqual(grabber.portrait_path_label.text(), "")
        with (patch("app.GuildPortraitGrabberQt.QMessageBox.question",
                    return_value=checker_qt.QMessageBox.StandardButton.Yes),
              patch.object(grabber.worker, "submit") as submit):
            self.assertTrue(grabber.capture_missing_portraits())
        self.assertEqual([record["memberId"] for record in
                          submit.call_args.kwargs["character_records"]], ["m1004"])
        grabber._set_portrait_list_mode("inactive")
        self.assertEqual(set(grabber._member_by_id), {"m1003", "m1004", "m1005"})
        self.assertEqual([member.id for member in grabber.character_members], ["m1005"])
        self.assertEqual(grabber.character_model.item(0, 0).toolTip(), "")
        self.assertFalse(grabber.save_guild_list())
        self.assertEqual(self.target.read_bytes(), before)
        checker.switch_page("settings")
        checker.switch_page("rooster")
        self.assertFalse(next(card for card in checker._roster_cards
                              if card.member_id == "m1003").portrait._source.isNull())
        self.assertFalse(checker.identity_v2_dirty)

    def test_v2_missing_batch_keeps_equal_names_and_distinct_member_ids(self):
        self.store.members.append(Member("m1004", "Lebendig", "Druid"))
        save_identity_v2(self.store, self.target)
        before = self.target.read_bytes()
        grabber = GuildPortraitGrabberQt(
            project_path=self.target, worker_factory=FakeWorker, config_data={})
        self.addCleanup(grabber.close)
        with (patch("app.GuildPortraitGrabberQt.QMessageBox.question",
                    return_value=checker_qt.QMessageBox.StandardButton.Yes),
              patch.object(grabber.worker, "submit") as submit):
            self.assertTrue(grabber.capture_missing_portraits())
        action, kwargs = submit.call_args.args[0], submit.call_args.kwargs
        self.assertEqual(action, "capture_all")
        self.assertEqual(kwargs["names"], ["Lebendig", "Lebendig"])
        self.assertEqual([record["memberId"] for record in kwargs["character_records"]],
                         ["m1003", "m1004"])
        for member_id in ("m1003", "m1004"):
            portrait = member_portrait_path(self.target, member_id)
            Image.new("RGB", (80, 100), "#406d81").save(portrait)
            self.assertTrue(grabber._refresh_saved_portrait({
                "name": "Lebendig", "path": str(portrait)}))
        self.assertEqual(self.target.read_bytes(), before)

    def test_shared_capture_worker_keeps_duplicate_name_member_ids(self):
        worker = BrowserWorker(queue.Queue())
        captured = []
        with patch.object(worker, "_capture_character",
                          side_effect=lambda **kwargs: captured.append(
                              kwargs["member_id"])):
            worker._capture_all(
                names=["Sorap", "Sorap"], region="EU", realm="stitches",
                game_version="classic1x", preferred_channel="msedge",
                wait_after_load=0, output_dir="", crop={},
                character_records=[
                    {"memberId": "m1000", "characterName": "Sorap"},
                    {"memberId": "m1001", "characterName": "Sorap"},
                ],
            )
        self.assertEqual(captured, ["m1000", "m1001"])


if __name__ == "__main__":
    unittest.main()
