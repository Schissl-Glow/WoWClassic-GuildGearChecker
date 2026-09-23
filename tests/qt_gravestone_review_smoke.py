"""Focused offscreen smoke for the Qt gravestone review queues and actions."""
from __future__ import annotations

import json
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from PIL import Image, ImageDraw

from app import i18n as suite_i18n
from app.GuildPortraitGrabberQt import GuildPortraitGrabberQt
from app.gravestone_categories import (
    GRAVESTONE_CATEGORIES, load_gravestone_category, save_gravestone_category,
    save_gravestone_portrait_preset,
)
from tools.gravestone_review.gravestone_review_core import ensure_workspace
from tools.gravestone_review.gravestone_review_qt import QUEUE_ORDER, QtGravestoneReviewWidget


TOOL_DIR = ROOT / "tools" / "gravestone_review"
application = QApplication.instance() or QApplication([])
old_language = suite_i18n._translator.language


def seed(folder: Path, name: str) -> Path:
    path = folder / name
    image = Image.new("RGBA", (120, 160), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    color = tuple(45 + value % 150 for value in digest[:3]) + (255,)
    draw.rounded_rectangle((8, 8, 112, 152), radius=10, fill=color)
    draw.ellipse((30, 25, 90, 100), fill=(0, 0, 0, 0))
    image.save(path)
    return path


def select(widget: QtGravestoneReviewWidget, queue_name: str, filename: str) -> None:
    widget.tabs.setCurrentIndex(QUEUE_ORDER.index(queue_name))
    listing = widget._lists[queue_name]
    matches = listing.findItems(filename, Qt.MatchFlag.MatchExactly)
    assert len(matches) == 1, (queue_name, filename)
    listing.setCurrentItem(matches[0])
    application.processEvents()


try:
    with tempfile.TemporaryDirectory(prefix="ggc-qt-review-") as temp_dir:
        project_root = Path(temp_dir)
        readonly_root = project_root / "empty-readonly"
        assert not (readonly_root / "assets").exists()
        empty_widget = QtGravestoneReviewWidget(readonly_root, TOOL_DIR)
        application.processEvents()
        assert not (readonly_root / "assets").exists()
        assert empty_widget.tabs.count() == 5
        empty_widget.close()

        workspace = ensure_workspace(project_root)
        candidate_accept = seed(workspace.candidates, "candidate_accept.png")
        candidate_reject = seed(workspace.candidates, "candidate_reject.png")
        candidate_error = seed(workspace.candidates, "candidate_error.png")
        accepted_restore = seed(workspace.accepted, "accepted_restore.png")
        accepted_approve = seed(workspace.accepted, "accepted_approve.png")
        accepted_bulk_a = seed(workspace.accepted, "accepted_bulk_a.png")
        accepted_bulk_b = seed(workspace.accepted, "accepted_bulk_b.png")
        rejected_delete = seed(workspace.rejected, "rejected_delete.png")
        seed(workspace.approved, "approved_existing.png")
        approved_existing = workspace.approved / "approved_existing.png"
        save_gravestone_category(approved_existing, "Zauberer")
        save_gravestone_portrait_preset(approved_existing, -0.15, 0.30, 1.6)
        (workspace.approved_compressed / approved_existing.name).write_bytes(approved_existing.read_bytes())
        promotion_source = seed(workspace.approved, "gravestone_099.png")
        save_gravestone_category(promotion_source, "Spezial")
        save_gravestone_portrait_preset(promotion_source, 0.2, -0.1, 1.4)
        (workspace.approved_compressed / promotion_source.name).write_bytes(promotion_source.read_bytes())
        productive = seed(workspace.graveyard, "gravestone_001.png")
        save_gravestone_category(candidate_accept, "Menschen")
        save_gravestone_portrait_preset(candidate_accept, 0.25, -0.35, 1.8)
        save_gravestone_category(accepted_bulk_a, "Zwerge")
        save_gravestone_category(accepted_bulk_b, "Elfen")
        (workspace.graveyard / "gravestones_manifest.json").write_text(json.dumps({
            "format": "GuildGearCheckerGravestoneManifest", "formatVersion": 1,
            "templates": [{
                "graveTemplateId": "grave-template-0001", "filename": productive.name,
                "sha256": hashlib.sha256(productive.read_bytes()).hexdigest(), "category": "Elfen",
                "defaultPortraitOffsetX": 0.4, "defaultPortraitOffsetY": -0.2,
                "defaultPortraitZoom": 1.5,
            }],
        }), encoding="utf-8")

        suite_i18n._translator.language = "de"
        widget = QtGravestoneReviewWidget(project_root, TOOL_DIR)
        widget.resize(1100, 760)
        widget.show()
        application.processEvents()
        assert [widget.tabs.tabText(index) for index in range(5)] == [
            "Kandidaten (3)", "Akzeptiert (4)", "Abgelehnt (1)", "Freigegeben (2)", "Produktiv (1)",
        ]
        assert all(widget.tabs.widget(index) is not widget._lists[QUEUE_ORDER[index]] for index in range(5))
        assert all(listing.isHidden() for listing in widget._lists.values())
        assert widget.tabs.maximumHeight() <= widget.tabs.tabBar().sizeHint().height() + 8
        assert widget.workspace_splitter.count() == 2
        left_size, right_size = widget.workspace_splitter.sizes()
        assert left_size * 100 >= right_size * 70, (left_size, right_size)
        assert tuple(widget._view_buttons) == ("gallery", "list")
        assert widget.view_stack.count() == 2
        detail_identity = id(widget.detail_frame)
        preview_identity = id(widget.preview_label)
        assert widget.detail_frame.isAncestorOf(widget.preview_label)
        assert not widget.metadata_toggle.isChecked()
        assert not widget.metadata_text.isVisible()
        assert not widget.checks_toggle.isChecked()
        assert not widget.checks_text.isVisible()
        assert not widget.file_toggle.isChecked()
        assert not widget.file_details_panel.isVisible()
        widget.file_toggle.click()
        widget.metadata_toggle.click()
        widget.checks_toggle.click()
        application.processEvents()
        assert widget.file_details_panel.isVisible()
        assert widget.metadata_text.isVisible()
        assert widget.checks_text.isVisible()
        assert widget.file_toggle.text() == "Datei ausblenden"
        assert widget.metadata_toggle.text() == "Metadaten ausblenden"
        assert widget.checks_toggle.text() == "Technische Prüfung ausblenden"
        widget.file_toggle.click()
        widget.metadata_toggle.click()
        widget.checks_toggle.click()
        assert not widget.file_details_panel.isVisible()
        assert not widget.metadata_text.isVisible()
        assert not widget.checks_text.isVisible()
        select(widget, "candidates", candidate_accept.name)
        assert widget.category_value.text() == "Menschen"
        assert widget.preset_value.text() == "X 0.25 · Y -0.35 · 1.80×"
        assert not widget.preview_label.pixmap().isNull()
        assert widget.preview_label.pixmap().width() <= widget.preview_label.contentsRect().width()
        assert widget.preview_label.pixmap().height() <= widget.preview_label.contentsRect().height()
        assert widget.item_position_label.text() == "1 von 3"
        assert not widget.previous_item_button.isEnabled()
        assert widget.next_item_button.isEnabled()
        next_name = widget._lists["candidates"].item(1).text()
        widget.next_item_button.click()
        application.processEvents()
        assert widget.filename_value.text() == next_name
        assert widget.item_position_label.text() == "2 von 3"
        assert widget.previous_item_button.isEnabled()
        widget.previous_item_button.click()
        application.processEvents()
        assert widget.filename_value.text() == candidate_accept.name
        widget._lists["candidates"].setCurrentRow(2)
        application.processEvents()
        assert widget.item_position_label.text() == "3 von 3"
        assert not widget.next_item_button.isEnabled()
        widget._lists["candidates"].setCurrentRow(0)
        application.processEvents()
        assert "PNG" in widget.checks_text.toPlainText()
        assert widget.renderer.portrait_path and widget.renderer.portrait_path.is_file()
        assert "Transparente Pixel" in widget.opening_diagnostics_label.text()
        assert widget._action_buttons["alpha"].isVisible()

        original_bytes = candidate_accept.read_bytes()
        selected_name = widget.filename_value.text()
        widget._open_alpha_mode()
        application.processEvents()
        assert widget._alpha_session is not None
        assert widget._alpha_source_path == candidate_accept
        assert not widget._alpha_has_unsaved_changes()
        assert id(widget.detail_frame) == detail_identity
        assert id(widget.preview_label) == preview_identity
        assert widget.detail_frame.isAncestorOf(widget.preview_label)
        assert widget.alpha_controls.isVisible()
        assert widget.alpha_reset_button.text() == "Zurücksetzen"
        assert widget.alpha_save_button.text() == "Anwenden / Speichern"
        assert widget.alpha_close_button.text() == "Verwerfen / Alpha-Modus beenden"
        assert not widget.normal_preview_controls.isVisible()
        assert not widget.tabs.isEnabled()
        assert not widget.view_stack.isEnabled()
        assert not widget.previous_item_button.isEnabled()
        assert not widget.next_item_button.isEnabled()
        assert not widget.preview_label.pixmap().isNull()
        opening_preview, _opening_analysis = widget._render_alpha_source()
        assert opening_preview.getpixel((0, 0))[:3] in {(205, 205, 205), (155, 155, 155)}

        # The fit/center mapping stays in source coordinates even when the Qt
        # preview is resized, so edits do not depend on DPI or viewport size.
        pixmap = widget.preview_label.pixmap()
        center = QPoint(
            round((widget.preview_label.width() - pixmap.width()) / 2 + pixmap.width() / 2),
            round((widget.preview_label.height() - pixmap.height()) / 2 + pixmap.height() / 2),
        )
        mapped = widget._alpha_widget_to_image(center)
        assert mapped is not None and abs(mapped[0] - 60) <= 1 and abs(mapped[1] - 80) <= 1
        widget.preview_label.resize(420, 520)
        widget._set_alpha_preview()
        pixmap = widget.preview_label.pixmap()
        center = QPoint(
            round((widget.preview_label.width() - pixmap.width()) / 2 + pixmap.width() / 2),
            round((widget.preview_label.height() - pixmap.height()) / 2 + pixmap.height() / 2),
        )
        resized_mapped = widget._alpha_widget_to_image(center)
        assert resized_mapped is not None and abs(resized_mapped[0] - 60) <= 1
        assert abs(resized_mapped[1] - 80) <= 1

        session = widget._alpha_session
        original_alpha = session.image.getchannel("A").copy()
        initial_ellipse = session.ellipse_bbox
        widget._set_alpha_tool("ellipse")
        drag_pixmap_key = widget.preview_label.pixmap().cacheKey()
        with patch.object(widget, "_set_alpha_preview", wraps=widget._set_alpha_preview) as render:
            widget._alpha_begin((25, 25))
            for step in range(1, 41):
                widget._alpha_continue((25 + round(65 * step / 40), 25 + 2 * step))
            assert render.call_count == 0
            assert widget.preview_label.pixmap().cacheKey() == drag_pixmap_key
            assert widget.preview_label._edit_ellipse == (25, 25, 90, 105)
            widget._alpha_finish((90, 105))
            assert render.call_count == 1
        assert session.ellipse_bbox == (25, 25, 90, 105)
        assert widget.preview_label.pixmap().cacheKey() != drag_pixmap_key
        drawn_alpha = session.image.getchannel("A").tobytes()
        assert drawn_alpha != original_alpha.tobytes()
        assert widget._alpha_has_unsaved_changes()

        widget._set_alpha_tool("move")
        with patch.object(widget, "_set_alpha_preview", wraps=widget._set_alpha_preview) as render:
            widget._alpha_begin((40, 40))
            for step in range(1, 31):
                widget._alpha_continue((40 + round(7 * step / 30), 40 + round(9 * step / 30)))
            assert render.call_count == 0
            assert widget.preview_label._edit_ellipse == (32, 34, 97, 114)
            widget._alpha_finish((47, 49))
            assert render.call_count == 1
        assert session.ellipse_bbox == (32, 34, 97, 114)
        widget._alpha_undo()
        assert session.ellipse_bbox == (25, 25, 90, 105)
        widget._alpha_redo()
        assert session.ellipse_bbox == (32, 34, 97, 114)

        edited_before_reset = session.image.getchannel("A").tobytes()
        widget._alpha_reset()
        assert session.image.getchannel("A").tobytes() == original_alpha.tobytes()
        assert session.ellipse_bbox == initial_ellipse
        widget._alpha_undo()
        assert session.image.getchannel("A").tobytes() == edited_before_reset
        widget._alpha_redo()
        assert session.image.getchannel("A").tobytes() == original_alpha.tobytes()
        opening_bytes = widget._render_alpha_source()[0].tobytes()
        widget._set_alpha_preview_mode("composite")
        assert not widget.preview_label.pixmap().isNull()
        assert widget._render_alpha_source()[0].tobytes() != opening_bytes
        widget._set_alpha_preview_mode("opening")
        widget._close_alpha_mode()
        application.processEvents()
        assert widget._alpha_session is None
        assert widget.tabs.isEnabled()
        assert widget.view_stack.isEnabled()
        assert widget.filename_value.text() == selected_name
        assert candidate_accept.read_bytes() == original_bytes

        # A failed save keeps both the source and the editable draft intact.
        widget._open_alpha_mode()
        widget._alpha_session.apply_ellipse((20, 20, 100, 115), feather=0)
        with patch(
            "tools.gravestone_review.gravestone_review_qt.save_alpha_edit_atomic",
            side_effect=OSError("forced alpha save failure"),
        ), patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes,
        ), patch.object(QMessageBox, "critical") as critical:
            widget._save_alpha_mode()
        critical.assert_called_once()
        assert widget._alpha_session is not None
        assert candidate_accept.read_bytes() == original_bytes
        widget._close_alpha_mode()

        # An externally changed source is rejected before backup/write.
        widget._open_alpha_mode()
        previous_stat = candidate_accept.stat()
        os.utime(
            candidate_accept,
            ns=(previous_stat.st_atime_ns, previous_stat.st_mtime_ns + 1_000_000),
        )
        with patch.object(QMessageBox, "critical") as critical:
            widget._save_alpha_mode()
        critical.assert_called_once()
        assert widget._alpha_session is not None
        assert candidate_accept.read_bytes() == original_bytes
        widget._close_alpha_mode()

        # Successful save backs up the prior PNG, replaces only this review
        # source and immediately refreshes validation, preview and selection.
        widget._set_preview(candidate_accept)
        old_signature = widget._image_signature(candidate_accept)
        widget._open_alpha_mode()
        widget._alpha_session.apply_ellipse((20, 20, 100, 115), feather=0)
        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes,
        ), patch.object(
            widget.renderer, "invalidate_path", wraps=widget.renderer.invalidate_path,
        ) as invalidate:
            widget._save_alpha_mode()
        application.processEvents()
        invalidate.assert_called_once_with(candidate_accept)
        assert widget._alpha_session is None
        assert widget.tabs.isEnabled()
        assert widget.filename_value.text() == selected_name
        assert candidate_accept.read_bytes() != original_bytes
        saved_bytes = candidate_accept.read_bytes()
        backups = list((workspace.logs / "alpha_backups").glob("candidate_accept_*.png"))
        assert len(backups) == 1 and backups[0].read_bytes() == original_bytes
        assert widget._image_signature(candidate_accept) != old_signature
        assert not any(key[0] == old_signature for key in widget._preview_cache)
        assert widget._current_analysis is not None
        assert "Transparente Pixel" in widget.opening_diagnostics_label.text()
        assert not widget.preview_label.pixmap().isNull()

        initial_composite = widget.preview_label.pixmap().cacheKey()
        widget._move_demo_portrait(QPoint(12, -8))
        assert widget._demo_offset_x != 0.25 or widget._demo_offset_y != -0.35
        widget._set_demo_transform(0.65, -0.4, 1.9, refresh=False)
        widget._refresh_preview()
        assert widget.preview_label.pixmap().cacheKey() != initial_composite
        widget._reset_demo_portrait()
        widget._refresh_preview()
        assert (widget._demo_offset_x, widget._demo_offset_y, widget._demo_zoom) == (0.0, 0.0, 1.0)
        widget._set_preview_mode("opening")
        widget._refresh_preview()
        assert not widget.preview_label.pixmap().isNull()
        assert candidate_accept.read_bytes() == saved_bytes
        widget._set_preview_mode("original")
        widget._refresh_preview()
        assert not widget.preview_label.pixmap().isNull()
        widget._set_preview_mode("composite")
        widget._set_demo_transform(0.35, -0.2, 1.75, refresh=False)
        widget._save_demo_portrait_preset()
        assert load_gravestone_category(candidate_accept) == "Menschen"
        assert widget._preset_for(candidate_accept, widget._sidecar_metadata(candidate_accept)) == (0.35, -0.2, 1.75)
        demo_path = widget.renderer.portrait_path
        widget.renderer.set_portrait(project_root / "missing-demo.png")
        widget._preview_cache.clear()
        widget._refresh_preview()
        assert not widget.preview_label.pixmap().isNull()
        widget.renderer.set_portrait(demo_path)
        assert [widget._view_buttons[name].text() for name in ("gallery", "list")] == [
            "Galerie", "Listenansicht",
        ]

        # All presentations share the queue selection. Reopening an unchanged
        # gallery keeps its tiles and cached QPixmaps instead of decoding again.
        widget._set_view("gallery")
        application.processEvents()
        assert id(widget.detail_frame) == detail_identity
        assert id(widget.preview_label) == preview_identity
        assert widget.filename_value.text() == candidate_accept.name
        assert len(widget._gallery_buttons) == 3
        gallery_button = widget._gallery_buttons[candidate_accept.name]
        assert gallery_button.text() == ""
        assert gallery_button.toolTip() == candidate_accept.name
        cached_thumbnail = widget._thumbnail(candidate_accept)
        assert widget._thumbnail(candidate_accept) is cached_thumbnail
        widget._refresh_gallery()
        assert widget._gallery_buttons[candidate_accept.name] is gallery_button
        widget._gallery_buttons[candidate_reject.name].click()
        application.processEvents()
        assert widget.filename_value.text() == candidate_reject.name
        selected_tile = widget._gallery_buttons[candidate_reject.name]
        widget._set_category("Gnome")
        assert widget._gallery_buttons[candidate_reject.name] is selected_tile

        stale_thumbnail = widget._thumbnail(candidate_error)
        stat = candidate_error.stat()
        os.utime(candidate_error, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        assert widget._thumbnail(candidate_error) is not stale_thumbnail
        assert sum(
            key[0][0] == str(candidate_error.resolve()) for key in widget._thumbnail_cache
        ) == 1

        widget._set_view("list")
        application.processEvents()
        assert id(widget.detail_frame) == detail_identity
        assert id(widget.preview_label) == preview_identity
        assert widget.list_table.rowCount() == 3
        assert widget.list_table.currentRow() == widget._lists["candidates"].currentRow()
        metadata_before = widget._image_metadata(candidate_reject)
        assert widget._image_metadata(candidate_reject) is metadata_before
        widget.list_table.selectRow(0)
        application.processEvents()
        assert widget.filename_value.text() == candidate_accept.name

        widget._set_view("gallery")
        selected_before_resize = widget.filename_value.text()
        widget.resize(850, 760)
        widget._finish_gallery_reflow()
        assert widget.filename_value.text() == selected_before_resize
        assert widget.filename_value.text() == candidate_accept.name
        # The Core validator itself has a dedicated self-test.  Keep this UI
        # transaction smoke focused and fast after proving validation is shown.
        widget.validator.validate = lambda _path: []

        widget._accept_current()
        assert not candidate_accept.exists()
        assert (workspace.accepted / candidate_accept.name).is_file()
        assert widget.tabs.tabText(0) == "Kandidaten (2)"
        assert widget.tabs.tabText(1) == "Akzeptiert (5)"

        select(widget, "candidates", candidate_reject.name)
        widget._reject_current()
        assert not candidate_reject.exists()
        assert (workspace.rejected / candidate_reject.name).is_file()

        select(widget, "candidates", candidate_error.name)
        with patch("tools.gravestone_review.gravestone_review_qt.accept_candidate", side_effect=OSError("forced move error")), \
             patch.object(QMessageBox, "critical"):
            widget._accept_current()
        assert candidate_error.is_file()
        assert "forced move error" in widget.feedback_label.text()
        assert widget.filename_value.text() == candidate_error.name
        candidate_error.write_bytes(b"not a png")
        widget._invalidate_cached_path(candidate_error)
        widget._open_alpha_mode()
        assert widget._alpha_session is None
        assert "Vorschaufehler" in widget.feedback_label.text()

        select(widget, "accepted", accepted_restore.name)
        assert widget._action_buttons["alpha"].isVisible()
        widget._restore_current()
        assert not accepted_restore.exists()
        assert (workspace.candidates / accepted_restore.name).is_file()

        select(widget, "accepted", accepted_approve.name)
        with patch.object(QMessageBox, "warning") as warning:
            widget._approve_current()
        warning.assert_called_once()
        assert accepted_approve.is_file()
        assert not (workspace.approved / accepted_approve.name).exists()

        for category in GRAVESTONE_CATEGORIES:
            widget._set_category(category)
            assert load_gravestone_category(accepted_approve) == category
            assert sum(button.isChecked() for button in widget._category_buttons.values()) == 1
        widget._approve_current()
        assert not accepted_approve.exists()
        assert (workspace.approved / accepted_approve.name).is_file()
        assert (workspace.approved_compressed / accepted_approve.name).is_file()

        select(widget, "accepted", accepted_bulk_a.name)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            widget._approve_all()
        assert not list(workspace.accepted.glob("*.png"))
        for name in (candidate_accept.name, accepted_bulk_a.name, accepted_bulk_b.name):
            assert (workspace.approved / name).is_file()
            assert (workspace.approved_compressed / name).is_file()

        select(widget, "approved", approved_existing.name)
        assert not widget._action_buttons["alpha"].isVisible()
        manifest_before_failed_promotion = (workspace.graveyard / "gravestones_manifest.json").read_bytes()
        productive_before_failed_promotion = sorted(workspace.graveyard.glob("gravestone_[0-9][0-9][0-9].png"))
        with patch("tools.gravestone_review.gravestone_review_qt.promote_approved_gravestones", side_effect=OSError("forced manifest error")), \
             patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
             patch.object(QMessageBox, "critical"):
            widget._promote_approved()
        assert (workspace.graveyard / "gravestones_manifest.json").read_bytes() == manifest_before_failed_promotion
        assert sorted(workspace.graveyard.glob("gravestone_[0-9][0-9][0-9].png")) == productive_before_failed_promotion

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            widget._promote_approved()
        productive_names = sorted(path.name for path in workspace.graveyard.glob("gravestone_[0-9][0-9][0-9].png"))
        assert productive_names == ["gravestone_001.png", "gravestone_002.png"]
        manifest_payload = json.loads((workspace.graveyard / "gravestones_manifest.json").read_text(encoding="utf-8"))
        assert len(manifest_payload["templates"]) == 2
        assert manifest_payload["templates"][1]["filename"] == "gravestone_002.png"
        approved_digest = hashlib.sha256(promotion_source.read_bytes()).hexdigest()
        approved_manifest_entry = next(
            entry for entry in manifest_payload["templates"] if entry["sha256"] == approved_digest
        )
        assert approved_manifest_entry["category"] == "Spezial"
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            widget._promote_approved()
        assert sorted(path.name for path in workspace.graveyard.glob("gravestone_[0-9][0-9][0-9].png")) == productive_names

        select(widget, "rejected", rejected_delete.name)
        assert widget._action_buttons["alpha"].isVisible()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            widget._delete_current()
        assert not rejected_delete.exists()

        select(widget, "productive", productive.name)
        assert not widget.view_controls.isVisible()
        assert not widget.workspace_splitter.isVisible()
        assert widget.productive_gallery_scroll.isVisible()
        assert widget.productive_gallery_grid.count() == len(widget._entries["productive"])
        first_productive_item = widget.productive_gallery_grid.itemAt(0).widget()
        assert first_productive_item.objectName() == "gravestoneReviewProductiveGalleryItem0"
        assert not first_productive_item.text()
        assert productive.name in first_productive_item.toolTip()
        assert not any(button.isVisible() for button in widget._action_buttons.values())
        assert not any(button.isEnabled() for button in widget._category_buttons.values())
        assert productive.is_file()
        assert not widget._action_buttons["alpha"].isVisible()
        productive_before_alpha_attempt = productive.read_bytes()
        widget._open_alpha_mode()
        assert widget._alpha_session is None
        assert productive.read_bytes() == productive_before_alpha_attempt
        widget.tabs.setCurrentIndex(QUEUE_ORDER.index("accepted"))
        widget._set_view("gallery")
        application.processEvents()
        assert widget.view_controls.isVisible()
        assert widget.workspace_splitter.isVisible()
        assert not widget.productive_gallery_scroll.isVisible()
        assert widget.gallery_grid.count() == 1
        assert widget.gallery_grid.itemAt(0).widget().objectName() == "gravestoneReviewGalleryEmpty"
        widget._set_view("list")
        assert widget.list_table.rowCount() == 0

        productive.unlink()
        widget._show_detail("productive", productive, {})
        assert "nicht verfügbar" in widget.preview_label.text()
        corrupt = workspace.rejected / "corrupt.png"
        corrupt.write_bytes(b"not a png")
        widget._show_detail("rejected", corrupt, {})
        assert "nicht verfügbar" in widget.preview_label.text()
        assert "nicht verfügbar" in widget.opening_diagnostics_label.text().casefold()
        widget.close()

        suite_i18n._translator.language = "en"
        english_widget = QtGravestoneReviewWidget(project_root, TOOL_DIR)
        application.processEvents()
        assert english_widget.tabs.tabText(0).startswith("Candidates")
        english_widget.tabs.setCurrentIndex(QUEUE_ORDER.index("productive"))
        application.processEvents()
        assert "read-only" in english_widget.readonly_notice.text().casefold()
        assert english_widget._action_buttons["accept"].text() == "ACCEPT"
        assert english_widget._action_buttons["alpha"].text() == "Edit Alpha"
        english_widget.close()

        class FakeWorker:
            def start(self) -> None:
                pass

            def request_batch_cancel(self) -> None:
                pass

            def submit(self, _action: str, **_payload) -> None:
                pass

        with patch.object(QtGravestoneReviewWidget, "reload", lambda self: None):
            embedded = GuildPortraitGrabberQt(worker_factory=lambda _events: FakeWorker(), config_data={})
        assert isinstance(embedded.review_page, QtGravestoneReviewWidget)
        assert embedded.tabs.indexOf(embedded.review_page) >= 0
        assert embedded.review_page._action_buttons["alpha"].text() == "Edit Alpha"
        assert embedded.review_page.alpha_save_button.text() == "Apply / Save"
        embedded.resize(1200, 800)
        embedded.tabs.setCurrentWidget(embedded.review_page)
        embedded.show()
        application.processEvents()
        embedded.review_page.workspace_splitter.setSizes([280, 720])
        application.processEvents()
        embedded._save_window_state()
        assert embedded.config_data["qt_review_splitter_sizes"][0] < (
            embedded.config_data["qt_review_splitter_sizes"][1]
        )
        embedded.close()
finally:
    suite_i18n._translator.language = old_language

print("Qt Gravestone Review Smoke: OK")
