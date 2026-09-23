# -*- coding: utf-8 -*-
"""Focused checks for project-scoped WCL aliases and bulk assignment choices."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["GGC_DISABLE_ICON_DOWNLOAD"] = "1"

from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QPushButton, QWidget

from app.GuildGearChecker import GuildModel
from app.GuildGearCheckerQt import BulkRaidImportDialog, UnknownRaidMemberDialog
from app.raid_attendance import exact_name_key
from app.i18n import tr


def run() -> None:
    app = QApplication.instance() or QApplication([])
    model = GuildModel()
    model.new_empty()
    player = model.add_player("Existing Player")
    main = model.add_member("Existing Main", "Smoke")
    target = model.add_member("Existing Twink", "Smoke")
    dead = model.add_member("Historical Twink", "Smoke")
    a_umlaut = model.add_member("Ännie", "Smoke")
    ascard = model.add_member("Ascard", "Smoke")
    model.update_member_assignment(main.id, player.playerId, "main", "tank")
    model.update_member_assignment(target.id, player.playerId, "twink", "dps")
    model.update_member_assignment(dead.id, player.playerId, "twink", "dps")
    model.update_member_assignment(a_umlaut.id, player.playerId, "twink", "dps")
    model.update_member_assignment(ascard.id, player.playerId, "twink", "dps")
    model.set_member_life_status(target.id, "inactive")
    dead.lifeStatus = "dead"
    dead.deathDate = "2025-01-01"

    with tempfile.TemporaryDirectory(prefix="wcl-alias-smoke-") as temp_dir:
        folder = Path(temp_dir)
        source = folder / "2026-09-18_BWL_Casts.csv"
        source.write_text('"Name","Amount"\n"WclGhost","1"\n', encoding="utf-8")
        parent = QWidget()
        with patch("app.GuildGearCheckerQt.read_suite_settings", return_value={}):
            dialog = BulkRaidImportDialog(parent, model, folder)
        dialog.show()
        app.processEvents()
        bulk_unknown = None
        legacy_unknown = None
        try:
            assert dialog.objectName() == "bulkRaidImportDialog"
            bulk_header = dialog.table.horizontalHeader()
            assert all(
                bulk_header.sectionResizeMode(column).name == "Interactive"
                for column in range(dialog.table.columnCount())
            )
            dialog.table.setColumnWidth(3, 420)
            dialog._refresh_view()
            assert dialog.table.columnWidth(3) == 420
            assert len(dialog.plans) == 1
            assert dialog.plans[0].status == "needs_assignment"
            assert dialog.plans[0].unknown_names == ("WclGhost",)
            assert dialog.participant_list.count() == 1
            row = dialog.participant_list.itemWidget(dialog.participant_list.item(0))
            combo = row.findChild(QComboBox)
            search = row.findChild(QLineEdit)
            assert combo is not None
            assert search is not None
            inactive_choice = combo.findData(target.id)
            dead_choice = combo.findData(dead.id)
            assert inactive_choice >= 0 and dead_choice >= 0
            assert target.id in combo.itemText(inactive_choice)
            assert "Twink" in combo.itemText(inactive_choice)
            assert tr("life.inactive") in combo.itemText(inactive_choice)
            assert tr("life.dead") in combo.itemText(dead_choice)

            all_choices = [
                combo.itemData(index) for index in range(combo.count())
                if combo.itemData(index)
            ]
            assert all_choices == [a_umlaut.id, ascard.id, main.id, target.id, dead.id]
            assert [combo.itemText(combo.findData(member_id)).split(" · ", 1)[0]
                    for member_id in all_choices] == [
                "Ännie", "Ascard", "Existing Main", "Existing Twink", "Historical Twink",
            ]
            search.setText("eXiStInG")
            app.processEvents()
            visible_choices = [
                combo.itemData(index) for index in range(combo.count())
                if combo.itemData(index)
            ]
            assert visible_choices == [main.id, target.id]
            assert model.wcl_member_aliases == {}
            search.setText("historical")
            app.processEvents()
            assert [combo.itemData(index) for index in range(combo.count())
                    if combo.itemData(index)] == [dead.id]
            search.clear()
            app.processEvents()
            assert [combo.itemData(index) for index in range(combo.count())
                    if combo.itemData(index)] == all_choices

            combo.setCurrentIndex(inactive_choice)
            app.processEvents()
            name_key = exact_name_key("WclGhost")
            assert model.wcl_member_aliases[name_key] == target.id
            assert dialog.plans[0].status == "new"
            assert dialog.plans[0].unknown_names == ()
            assert dialog._participant_preview[
                dialog._source_path_key(source)
            ] == (("WclGhost", True),)

            mains = [(f"{player.playerName} · {main.name}", main.id)]
            bulk_unknown = UnknownRaidMemberDialog(
                parent, "AnotherGhost", mains, bulk_context=True,
                existing_members=dialog._wcl_alias_candidates(),
            )
            bulk_labels = {button.text() for button in bulk_unknown.findChildren(QPushButton)}
            assert tr("raids.bulk_assign_existing") in bulk_labels
            assert tr("raids.add_as_main") in bulk_labels
            assert tr("raids.assign_as_twink") in bulk_labels
            assert tr("raids.bulk_discard_unknown") in bulk_labels
            assert tr("raid_clm_admin.history_action_dead") not in bulk_labels
            assert tr("raid_clm_admin.history_action_inactive") not in bulk_labels

            legacy_unknown = UnknownRaidMemberDialog(parent, "AnotherGhost", mains)
            legacy_labels = {button.text() for button in legacy_unknown.findChildren(QPushButton)}
            assert tr("raid_clm_admin.history_action_dead") in legacy_labels
            assert tr("raid_clm_admin.history_action_inactive") in legacy_labels

            project_path = folder / "aliases.ggc"
            model.save(project_path, backup=False)
            reloaded = GuildModel()
            reloaded.load(project_path)
            assert reloaded.wcl_member_aliases[name_key] == target.id
            reloaded_plan = reloaded.analyze_bulk_raid_csv_files((source,))[0]
            assert reloaded_plan.status == "new"
            assert reloaded_plan.unknown_names == ()
            result = reloaded.import_bulk_raid_csv_plans((reloaded_plan,))
            assert result.imported == 1 and result.failed == 0
            assert reloaded.attendance_for_raid(reloaded.raids[0].id)[0].memberId == target.id

            old_payload = copy.deepcopy(reloaded.to_payload())
            old_payload.pop("wclMemberAliases", None)
            legacy_project = GuildModel()
            legacy_project.load_payload(old_payload)
            assert legacy_project.wcl_member_aliases == {}

            orphan_payload = copy.deepcopy(reloaded.to_payload())
            orphan_payload["wclMemberAliases"]["oldname"] = "missing-member-id"
            orphan_project = GuildModel()
            orphan_project.load_payload(orphan_payload)
            assert "oldname" not in orphan_project.wcl_member_aliases
            assert orphan_project.resolve_raid_attendance(("OldName",)).unknown_names == ("OldName",)

            print("WCL Bulk Alias Smoke: OK")
        finally:
            for child in (bulk_unknown, legacy_unknown):
                if child is not None:
                    child.close()
                    child.deleteLater()
            dialog.close()
            dialog.deleteLater()
            parent.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    run()
