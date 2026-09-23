# -*- coding: utf-8 -*-
"""Small offscreen smoke test for the PySide6 checker migration."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QFrame, QHeaderView, QPushButton
from app.GuildGearCheckerQt import (
    CHECKER_BANNER_HEIGHT, GuildGearCheckerQt, GuildModel, HeaderWidget, MemberEditDelegate,
    RAID_ATTENDANCE_FIXED_COLUMNS, RAID_MATRIX_BACKGROUND_ROLE,
    RAID_MATRIX_HEADER_HEIGHT, RAID_MATRIX_ROW_HEIGHT, MemberTable, RaidPointAdjustmentDialog,
    RaidEditorDialog, UnknownRaidMemberDialog,
)
from app import i18n as suite_i18n
from app.i18n import race_display
from app.GuildGearChecker import raid_role_display
from app.raid_points import character_points, player_points
from app.rewards import RewardAsset, RewardAssignments


class SmokeWindow(GuildGearCheckerQt):
    def _load_autosave_or_seed(self) -> None:
        self.model.new_empty()
        first = self.model.add_member("QtSmoke", "Smoke")
        first.race = "Human"
        first.className = "Rogue"
        first.spec = "Combat"
        second = self.model.add_member("QtSmokeTwo", "Smoke")
        second.className = "Priest"
        second.spec = "Holy"
        second.lifeStatus = "dead"
        second.deathDate = "2026-09-13"

    def _apply_character_cache_once(self) -> None:
        return

    def autosave(self) -> None:
        return


assert (ROOT / "assets" / "graveyard" / "Background_001.png").is_file()
assert (ROOT / "assets" / "checker_banner.png").is_file()
app = QApplication.instance() or QApplication([])
with patch("app.GuildGearCheckerQt.read_suite_settings", return_value={}):
    window = SmokeWindow()
window.show()
app.processEvents()

# Raidpunkte-Dialog bleibt innerhalb der verfügbaren Arbeitsfläche und hält
# Adjustment-/Reason-Eingaben auch bei längeren Tabellen lesbar.
dialog_model = GuildModel()
dialog_model.new_empty()
dialog_member = dialog_model.add_member("Adjustment Smoke Character", "Smoke")
dialog_player = dialog_model.add_player("Adjustment Smoke Player")
dialog_model.update_member_assignment(
    dialog_member.id, dialog_player.playerId, "main", "dps",
)
dialog_raid, _summary = dialog_model.create_raid_with_attendance(
    "2026-09-01", "Adjustment Smoke", "", "MC", [dialog_member.name],
)
adjust_dialog = RaidPointAdjustmentDialog(window, dialog_model, dialog_raid)
available_geometry = QApplication.primaryScreen().availableGeometry()
assert adjust_dialog.width() <= available_geometry.width()
assert adjust_dialog.height() <= available_geometry.height()
assert adjust_dialog.table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
assert adjust_dialog.table.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
assert adjust_dialog.table.verticalHeader().defaultSectionSize() >= 36
assert adjust_dialog.table.cellWidget(0, 4).minimumWidth() >= 100
assert adjust_dialog.table.cellWidget(0, 5).minimumWidth() >= 170
adjust_dialog.close()
adjust_dialog.deleteLater()

assert list(window._pages) == [
    "rooster", "player_profile", "graveyard", "management", "raid", "settings",
]
assert list(window._nav_buttons) == ["rooster", "graveyard", "management", "raid", "settings"]
assert window.stack.currentWidget() is window._pages["rooster"]
assert window.project_label.text() == "Kein Projekt geladen"
assert window.project_label.toolTip() == ""
with tempfile.TemporaryDirectory(prefix="ggc-qt-project-label-") as temp_dir:
    first_project = Path(temp_dir) / "Bierstube.ggc"
    second_project = Path(temp_dir) / "Andere_Gilde.ggc"
    window.model.save(first_project, backup=False)
    window.refresh_project_label()
    assert window.project_label.text() == "Projekt: Bierstube.ggc"
    assert window.project_label.toolTip() == str(first_project.resolve())
    window.model.save(second_project, backup=False)
    window.refresh_project_label()
    assert window.project_label.text() == "Projekt: Andere_Gilde.ggc"
    assert window.project_label.toolTip() == str(second_project.resolve())
    with patch("app.GuildGearCheckerQt.subprocess.Popen") as launched:
        window.open_portrait_grabber()
    launched.assert_called_once()
    launch_command = launched.call_args.args[0]
    assert Path(launch_command[1]).name == "GuildPortraitGrabberQt.py"
    assert "GuildPortraitGrabber.py" not in launch_command
    assert "--project" in launch_command
    assert str(second_project.resolve()) in launch_command
    assert "--session-id" in launch_command
    session_index = launch_command.index("--session-id")
    assert launch_command[session_index + 1] == window._project_handoff_session_id
    assert Path(launched.call_args.kwargs["cwd"]).resolve() == ROOT.resolve()
# Verwaltung verwendet intern weiterhin die bewährte member_* Logik. Der
# Standard-Unterfilter "Gildenliste" zeigt absichtlich nur aktive Charaktere.
window.switch_page("management")
app.processEvents()
assert window.stack.currentWidget() is window._pages["management"]
assert window.member_tab == "Gildenliste"
assert window.member_table.rowCount() == 1
assert window.member_table.columnCount() == 11
window.set_member_tab("Alle Charaktere")
app.processEvents()
assert window.member_table.rowCount() == 2
assert "Tot" in window._member_subnav_buttons
window.set_member_tab("Tot")
app.processEvents()
assert window.member_table.rowCount() == 1
assert window.member_table.item(0, 0).text() == "QtSmokeTwo"
window.set_member_tab("Gildenliste")
app.processEvents()
assert window.member_table.rowCount() == 1
window._select_member_in_table("m1000")
window.show_member("m1000")
assert window.detail_name.text() == "QtSmoke"
assert window.detail_portrait.width() == 220 and window.detail_portrait.height() == 220
assert hasattr(window, "detail_sections")
assert not hasattr(window, "detail_tabs")
assert window.member_wipe_button.text() == "Wipe"
header = window.findChild(HeaderWidget)
assert header is not None and header.height() == CHECKER_BANNER_HEIGHT == 200 and not header._source.isNull()
assert window.member_table.columnWidth(3) == MemberTable.DEFAULT_COLUMN_WIDTHS[3]
window.member_table.setColumnWidth(3, 210)
assert window.member_table.columnWidth(3) == 210
assert MemberEditDelegate.EDITOR_MIN_WIDTHS[3] >= 200
# The compact detail panel keeps actions below the tab content rather than overlapping it.
app.processEvents()
def _panel_rect(widget):
    top_left = widget.mapTo(window.detail_panel, QPoint(0, 0))
    return QRect(top_left, widget.size())


def _assert_detail_layout():
    content_rect = _panel_rect(window.detail_scroll)
    actions_rect = _panel_rect(window.detail_action_box)
    layout_geometry = (content_rect, actions_rect, window.detail_panel.contentsRect())
    assert not content_rect.intersects(actions_rect), layout_geometry
    assert 0 <= actions_rect.top() - content_rect.bottom() - 1 <= 12, layout_geometry
    assert window.detail_panel.contentsRect().contains(actions_rect), layout_geometry
    for action_button in (
        window.detail_save_button,
        window.armory_button,
        window.activity_button,
        window.life_button,
    ):
        assert actions_rect.contains(_panel_rect(action_button)), (layout_geometry, _panel_rect(action_button))


for width, height in ((1040, 680), (1500, 920)):
    window.resize(width, height)
    app.processEvents()
    _assert_detail_layout()
assert window.detail_sections.isVisible()
assert not hasattr(window, "source_value")
# Member detail fields are writable in Qt, including assignment fields.
window.race_combo.setCurrentText(race_display("Human"))
window.class_combo.setCurrentText("Rogue")
window.spec_combo.setCurrentText("Combat")
window.character_type_combo.setCurrentIndex(1)  # Main
window.raid_role_combo.setCurrentText(raid_role_display("dps"))
window.save_selected_member()
smoke = window.model.find_by_id("m1000")
assert smoke is not None
assert smoke.race == "Human" and smoke.className == "Rogue" and smoke.spec == "Combat"
assert smoke.characterType == "main" and smoke.raidRole == "dps"
# Inline table editing uses the same model.
assert window._apply_member_inline_edit(smoke, 2, "Priest")
assert smoke.className == "Priest" and smoke.spec == ""
assert window._apply_member_inline_edit(smoke, 3, "Holy")
assert smoke.spec == "Holy"
window.refresh_member_table()
window._reward_assignments = RewardAssignments(
    character_badges={
        smoke.id: RewardAsset(
            "Bronze_1", ROOT / "assets" / "ranks" / "48" / "Bronze_1.png", 80,
        )
    },
    main_frames={},
)

window.switch_page("rooster")
app.processEvents()
assert len(window._roster_cards) == 1  # Roster intentionally contains active members only
rank_card = window._roster_cards[0]
assert 28 <= rank_card.rank_icon.width() <= 58
assert 28 <= rank_card.rank_icon.height() <= 58
assert rank_card.rank_icon.x() <= rank_card.portrait.width() - 48
assert rank_card.rank_icon.y() >= 0
sections = window.roster_content.findChildren(QFrame, "rosterDraftSection")
assert len(sections) == 4  # Tank, Heiler, DPS und Nicht zugeordnet bleiben getrennt sichtbar.
assert window._roster_zoom_percent == 100
window.roster_zoom_slider.setValue(70)
window._roster_zoom_timer.stop()
window._roster_zoom_pending = 70
window._apply_roster_zoom()
app.processEvents()
assert window._roster_zoom_percent == 70
# Clicking a roster card opens the read-only detail side panel and stays in Roster.
assert window.roster_scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
window._reflow_roster_grids()
gallery_viewport_before_detail = window.roster_scroll.viewport().width()
assert window.roster_content.maximumWidth() == gallery_viewport_before_detail
window._roster_card_clicked("m1000")
app.processEvents()
window._reflow_roster_grids()
gallery_viewport_with_detail = window.roster_scroll.viewport().width()
assert gallery_viewport_with_detail < gallery_viewport_before_detail
assert window.roster_content.maximumWidth() == gallery_viewport_with_detail
assert window.stack.currentWidget() is window._pages["rooster"]
assert window.roster_detail_panel.isVisible()
assert window.roster_detail_name.text() == "QtSmoke"
identity_text = window.roster_detail_class.text()
assert "Mensch" in identity_text
assert "Priest" in identity_text
assert "Holy" in identity_text
assert "color:" in identity_text
assert window.roster_detail_rank.text() == "Bronze 1"
assert window.roster_rank_slot.width() == 116
assert window.roster_rank_icon.width() == 96
assert window.roster_rank_icon.x() >= 12
assert not hasattr(window, "roster_detail_race")
assert not hasattr(window, "roster_detail_gear")
assert not hasattr(window, "roster_detail_raid_overview")
# Karten-/Listenumschalter nutzt dieselbe aktive Datenquelle und Detailauswahl.
assert window.roster_cards_button.text() == "Kartenansicht"
assert window.roster_list_button.text() == "Listenansicht"
window.roster_search_edit.setText("QtSmoke")
window._set_roster_view("list")
app.processEvents()
assert window.roster_content_stack.currentWidget() is window.roster_list
assert window.roster_list.rowCount() == 1
assert [window.roster_list.horizontalHeaderItem(i).text() for i in range(10)] == [
    "Name", "Klasse", "Rolle", "Charaktertyp", "Gear-Status", "Raidstatus", "Aktivstatus",
    "Aktuelle DKP", "Eternal-DKP Charakter", "Eternal-DKP Spieler",
]
roster_class_item = window.roster_list.item(0, 1)
assert not roster_class_item.icon().isNull()
assert roster_class_item.foreground().color().name() != "#000000"
window.roster_list.sortItems(0, Qt.SortOrder.DescendingOrder)
window._roster_list_clicked(0)
assert window.roster_detail_panel.isVisible()
window._set_roster_view("cards")
app.processEvents()
window._reflow_roster_grids()
window._close_roster_detail()
app.processEvents()
window._reflow_roster_grids()
assert not window.roster_detail_panel.isVisible()
gallery_viewport_after_close = window.roster_scroll.viewport().width()
assert gallery_viewport_after_close > gallery_viewport_with_detail
assert window.roster_content.maximumWidth() == gallery_viewport_after_close
window._set_roster_view("cards")
app.processEvents()
assert window.roster_content_stack.currentWidget() is window.roster_scroll
assert len(window._roster_cards) == 1
window.roster_search_edit.clear()

window.switch_page("raid")
app.processEvents()
assert window.raid_subtabs.count() == 2
assert [window.raid_subtabs.tabText(index) for index in range(2)] == [
    "Raids", "Teilnahme",
]
assert "Teilnahme importieren" not in {
    button.text() for button in window._pages["raid"].findChildren(QPushButton)
}
create_dialog = RaidEditorDialog(window, model=window.model)
assert not create_dialog.save_button.isEnabled()
assert create_dialog.raid_type_combo.findData("World Boss") >= 0
create_dialog.raid_type_combo.setCurrentIndex(create_dialog.raid_type_combo.findData("MC"))
assert not create_dialog.save_button.isEnabled()  # CSV remains mandatory.
bench_member = window.model.add_member("QtBench", "Smoke")
bench_member.className = "Mage"
window.model.assign_character_type(bench_member.id, "main", None, "not_set")
bench_player = window.model.find_player_by_id(bench_member.playerId)
future_member = window.model.add_member("QtFuture", "Smoke")
future_member.className = "Warrior"
window.model.assign_character_type(future_member.id, "main", None, "not_set")
future_player = window.model.find_player_by_id(future_member.playerId)
window.model.set_player_membership(future_player.playerId, "2026-10-01", None)
create_dialog.csv_names = [smoke.name]
create_dialog.csv_ready = True
create_dialog._refresh_save_state()
assert create_dialog.save_button.isEnabled()
create_dialog._refresh_bench_state()
assert smoke.playerId not in {player.playerId for player, _member in create_dialog._bench_candidates()}
assert bench_player.playerId in {player.playerId for player, _member in create_dialog._bench_candidates()}
create_dialog.bench_player_ids = {bench_player.playerId}
assert create_dialog.creation_values()[-1] == [bench_player.playerId]
create_dialog.deleteLater()

# Der Raid-CSV-Dialog übernimmt bekannte Player sowie eindeutige Altbestands-
# Charaktere automatisch. Nur wirklich unbekannte Namen öffnen die Zuordnung.
with tempfile.TemporaryDirectory(prefix="ggc-raid-csv-") as temp_dir:
    mixed_model = GuildModel()
    mixed_model.new_empty()
    known_main = mixed_model.add_member("KnownMain", "Smoke")
    mixed_model.assign_character_type(known_main.id, "main", None, "not_set")
    known_player = mixed_model.find_player_by_id(known_main.playerId)
    known_twink = mixed_model.add_member("KnownTwink", "Smoke")
    mixed_model.assign_character_type(known_twink.id, "twink", known_main.id, "not_set")
    legacy_known = mixed_model.add_member("LegacyKnown", "Smoke")
    csv_bench = mixed_model.add_member("CsvBench", "Smoke")
    mixed_model.assign_character_type(csv_bench.id, "main", None, "not_set")
    csv_bench_player = mixed_model.find_player_by_id(csv_bench.playerId)
    mixed_path = Path(temp_dir) / "mixed.csv"
    mixed_path.write_text(
        "Name;Amount\nKnownMain;1\nKnownTwink;1\nLegacyKnown;1\nActuallyNew;1\n",
        encoding="utf-8",
    )
    assigned_names = []

    def accept_unknown_as_main(dialog):
        assigned_names.append(dialog.name)
        dialog.result_value = ("main", None)
        return QDialog.DialogCode.Accepted

    mixed_dialog = RaidEditorDialog(window, model=mixed_model)
    mixed_dialog.raid_type_combo.setCurrentIndex(
        mixed_dialog.raid_type_combo.findData("MC")
    )
    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(mixed_path), "")), \
            patch.object(UnknownRaidMemberDialog, "exec", accept_unknown_as_main):
        mixed_dialog._choose_csv()
    assert assigned_names == ["ActuallyNew"]
    assert mixed_dialog.csv_open_names == []
    assert mixed_dialog.csv_ready and mixed_dialog.save_button.isEnabled()
    assert mixed_dialog._csv_present_count() == 3
    assert "0 offene Zuordnungen" in mixed_dialog.csv_summary.text()
    assert mixed_dialog.bench_summary.text() == "3 teilgenommen · 0 Bench · 0 offene Zuordnungen"
    mixed_bench_ids = {
        player.playerId for player, _member in mixed_dialog._bench_candidates()
    }
    assert known_player.playerId not in mixed_bench_ids
    assert csv_bench_player.playerId in mixed_bench_ids
    assert mixed_dialog.bench_button.isEnabled()
    assert mixed_dialog.bench_button.toolTip() == ""
    mixed_dialog.bench_player_ids = {csv_bench_player.playerId}
    _mixed_raid, mixed_summary = mixed_model.create_raid_with_attendance(
        *mixed_dialog.creation_values()
    )
    assert (mixed_summary["participants"], mixed_summary["bench"]) == (3, 1)
    assert mixed_model.find_by_id(legacy_known.id).characterType == "main"
    mixed_entries = mixed_model.attendance_for_raid(_mixed_raid.id)
    assert len({entry.playerId for entry in mixed_entries}) == 4
    known_entry = next(entry for entry in mixed_entries if entry.playerId == known_player.playerId)
    assert (known_entry.memberId, known_entry.attendanceType) == (known_main.id, "main")
    mixed_dialog.deleteLater()

    empty_model = GuildModel()
    empty_model.new_empty()
    fresh_path = Path(temp_dir) / "fresh.csv"
    fresh_path.write_text("Name;Amount\nFreshCharacter;1\n", encoding="utf-8")
    fresh_assignments = []

    def accept_fresh_as_main(dialog):
        fresh_assignments.append(dialog.name)
        dialog.result_value = ("main", None)
        return QDialog.DialogCode.Accepted

    fresh_dialog = RaidEditorDialog(window, model=empty_model)
    fresh_dialog.raid_type_combo.setCurrentIndex(fresh_dialog.raid_type_combo.findData("MC"))
    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(fresh_path), "")), \
            patch.object(UnknownRaidMemberDialog, "exec", accept_fresh_as_main):
        fresh_dialog._choose_csv()
    assert fresh_assignments == ["FreshCharacter"]
    assert fresh_dialog.csv_ready and fresh_dialog.save_button.isEnabled()
    assert fresh_dialog._csv_present_count() == 1
    assert not fresh_dialog.bench_button.isEnabled()
    assert fresh_dialog.bench_button.toolTip() == "Keine verfügbaren Bank-Spieler"
    fresh_dialog.deleteLater()

    all_present_model = GuildModel()
    all_present_model.new_empty()
    all_present = all_present_model.add_member("AllPresent", "Smoke")
    all_present_model.assign_character_type(all_present.id, "main", None, "not_set")
    all_present_path = Path(temp_dir) / "all_present.csv"
    all_present_path.write_text("Name;Amount\nAllPresent;1\n", encoding="utf-8")
    all_present_dialog = RaidEditorDialog(window, model=all_present_model)
    all_present_dialog.raid_type_combo.setCurrentIndex(
        all_present_dialog.raid_type_combo.findData("MC")
    )
    with patch.object(
        QFileDialog, "getOpenFileName", return_value=(str(all_present_path), ""),
    ), patch.object(UnknownRaidMemberDialog, "exec") as unexpected_all_present_dialog:
        all_present_dialog._choose_csv()
    unexpected_all_present_dialog.assert_not_called()
    assert all_present_dialog.csv_ready and all_present_dialog.save_button.isEnabled()
    assert not all_present_dialog.bench_button.isEnabled()
    assert all_present_dialog.bench_button.toolTip() == "Keine verfügbaren Bank-Spieler"
    all_present_dialog.deleteLater()

    open_model = GuildModel()
    open_model.new_empty()
    open_known = open_model.add_member("OpenKnown", "Smoke")
    open_model.assign_character_type(open_known.id, "main", None, "not_set")
    open_bench = open_model.add_member("OpenBench", "Smoke")
    open_model.assign_character_type(open_bench.id, "main", None, "not_set")
    open_path = Path(temp_dir) / "open.csv"
    open_path.write_text(
        "Name;Amount\nOpenKnown;1\nActuallyUnknown;1\n", encoding="utf-8",
    )
    open_dialog = RaidEditorDialog(window, model=open_model)
    open_dialog.raid_type_combo.setCurrentIndex(open_dialog.raid_type_combo.findData("MC"))
    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(open_path), "")), \
            patch.object(
                UnknownRaidMemberDialog, "exec", return_value=QDialog.DialogCode.Rejected,
            ):
        open_dialog._choose_csv()
    assert open_dialog.csv_open_names == ["ActuallyUnknown"]
    assert open_dialog._csv_present_count() == 1
    assert not open_dialog.csv_ready
    assert not open_dialog.save_button.isEnabled()
    assert not open_dialog.bench_button.isEnabled()
    assert open_dialog.bench_summary.text() == (
        "1 teilgenommen · 0 Bench · 1 offene Zuordnungen"
    )
    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(open_path), "")), \
            patch.object(UnknownRaidMemberDialog, "exec", accept_unknown_as_main):
        open_dialog._choose_csv()
    assert open_dialog.csv_open_names == []
    assert open_dialog.csv_ready and open_dialog.save_button.isEnabled()
    assert open_dialog.bench_button.isEnabled()
    assert open_dialog._csv_present_count() == 2
    open_dialog.deleteLater()

    ambiguous_model = GuildModel()
    ambiguous_model.new_empty()
    ambiguous_model.add_member("Duplicate", "Smoke")
    duplicate = ambiguous_model.add_member("Temporary", "Smoke")
    duplicate.name = "Duplicate"
    ambiguous_path = Path(temp_dir) / "ambiguous.csv"
    ambiguous_path.write_text("Name;Amount\nDuplicate;1\n", encoding="utf-8")
    ambiguous_dialog = RaidEditorDialog(window, model=ambiguous_model)
    ambiguous_dialog.raid_type_combo.setCurrentIndex(
        ambiguous_dialog.raid_type_combo.findData("MC")
    )
    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(ambiguous_path), "")), \
            patch.object(UnknownRaidMemberDialog, "exec") as unexpected_unknown_dialog:
        ambiguous_dialog._choose_csv()
    unexpected_unknown_dialog.assert_not_called()
    assert ambiguous_dialog.csv_open_names == ["Duplicate"]
    assert not ambiguous_dialog.csv_ready and not ambiguous_dialog.save_button.isEnabled()
    assert ambiguous_dialog.bench_summary.text() == (
        "0 teilgenommen · 0 Bench · 1 offene Zuordnungen"
    )
    ambiguous_dialog.deleteLater()

first_raid = window.model.create_raid("2026-09-01", "Molten Core", raid_type="MC")
window.model.import_raid_attendance(first_raid.id, [smoke.name])
window.model.set_raid_bench_players(first_raid.id, [bench_player.playerId])
edit_dialog = RaidEditorDialog(window, raid=first_raid, model=window.model)
assert edit_dialog.bench_values() == [bench_player.playerId]
assert edit_dialog.bench_button.isEnabled()
assert bench_player.playerId in {
    player.playerId for player, _member in edit_dialog._bench_candidates()
}
edit_dialog.deleteLater()
second_raid = window.model.create_raid("2026-09-08", "Zul Gurub", raid_type="ZG")
window.model.import_raid_attendance(second_raid.id, [smoke.name])
window.model.set_raid_attendance_status(second_raid.id, smoke.playerId, "bench")
inactive_raid_member = window.model.add_member("QtInactiveRaid", "Smoke")
window.model.assign_character_type(inactive_raid_member.id, "main", None, "not_set")
dead_raid_member = window.model.add_member("QtDeadRaid", "Smoke")
window.model.assign_character_type(dead_raid_member.id, "main", None, "not_set")
for day in range(1, 10):
    older = window.model.create_raid(
        f"2026-08-{day:02d}", f"Older {day}", raid_type="MC",
    )
    older_names = [] if day == 1 else [smoke.name]
    if day == 9:
        older_names.extend([inactive_raid_member.name, dead_raid_member.name])
    window.model.import_raid_attendance(older.id, older_names)
inactive_raid_member.lifeStatus = "inactive"
dead_raid_member.lifeStatus = "dead"
dead_raid_member.deathDate = "2026-09-20"
window.refresh_raids()
app.processEvents()
assert window.raid_table.columnCount() == 6
first_raid_row = next(
    row for row in range(window.raid_table.rowCount())
    if window.raid_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == first_raid.id
)
window.raid_table.selectRow(first_raid_row)
window.refresh_raid_participants()
assert window.raid_participants_table.rowCount() == 2
participant_statuses = {
    window.raid_participants_table.item(row, 3).text()
    for row in range(window.raid_participants_table.rowCount())
}
assert participant_statuses == {"Teilgenommen", "Bench"}
bench_participant_row = next(
    row for row in range(window.raid_participants_table.rowCount())
    if window.raid_participants_table.item(row, 0).text() == bench_player.playerName
)
bench_character = window.raid_participants_table.item(bench_participant_row, 1)
assert not bench_character.icon().isNull()
assert bench_character.foreground().color().name() == "#3fc7eb"
assert window.raid_participants_table.item(bench_participant_row, 3).foreground().color().name() == "#e1c183"
assert all(
    window.raid_table.horizontalHeader().sectionResizeMode(column) == QHeaderView.ResizeMode.Interactive
    for column in range(window.raid_table.columnCount())
)
assert all(
    window.raid_participants_table.horizontalHeader().sectionResizeMode(column) == QHeaderView.ResizeMode.Interactive
    for column in range(window.raid_participants_table.columnCount())
)
window.raid_subtabs.setCurrentIndex(1)
window.refresh_raid_matrix()
assert window.raid_stats_table.rowCount() == 2
assert window.raid_stats_table.columnCount() == RAID_ATTENDANCE_FIXED_COLUMNS
assert window.raid_matrix_table.rowCount() == 2
assert window.matrix_active_only.isChecked()
assert not window.matrix_active_only.isVisible()
assert window.raid_matrix_table.columnCount() == 10
assert window.raid_stats_table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn
assert window.raid_matrix_table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn
assert window.raid_stats_table.horizontalHeader().height() == RAID_MATRIX_HEADER_HEIGHT
assert window.raid_matrix_table.horizontalHeader().height() == RAID_MATRIX_HEADER_HEIGHT
assert window.matrix_view_player_button.isChecked()
assert not window.matrix_view_character_button.isChecked()
assert not hasattr(window, "matrix_subject_mode")
assert window.matrix_subject_label.text() == "Spielerfilter"
assert window.matrix_subject.count() >= 1  # Die neutrale Auswahl bleibt immer verfügbar.
assert window.matrix_subject.findData(inactive_raid_member.playerId) < 0
assert window.matrix_subject.findData(dead_raid_member.playerId) < 0

# Letzte 10 gilt für Statistik UND Matrix derselben gemeinsamen Zeilenbasis.
rows_by_name = {
    window.raid_stats_table.item(row, 0).text(): row
    for row in range(window.raid_stats_table.rowCount())
}
smoke_row = rows_by_name[smoke.name]
assert future_player.playerName not in rows_by_name
assert inactive_raid_member.name not in rows_by_name
assert dead_raid_member.name not in rows_by_name
assert window.raid_stats_table.item(smoke_row, 1).data(Qt.ItemDataRole.DisplayRole) == 100
assert window.raid_stats_table.item(smoke_row, 4).data(Qt.ItemDataRole.DisplayRole) == 10
assert len(window._matrix_raids) == 10

matrix_columns = {raid.id: column for column, raid in enumerate(window._matrix_raids)}
assert window.raid_matrix_table.item(
    smoke_row, matrix_columns[first_raid.id]
).background().color().name() == "#248447"
assert window.raid_matrix_table.item(
    smoke_row, matrix_columns[second_raid.id]
).background().color().name() == "#b18420"
bench_row = rows_by_name[bench_player.playerName]
assert window.raid_matrix_table.item(
    bench_row, matrix_columns[second_raid.id]
).background().color().name() == "#11161d"

# Vertikal bleibt die Matrix exakt mit der Statistikzeile synchron.
window.raid_stats_table.setMaximumHeight(90)
window.raid_matrix_table.setMaximumHeight(90)
app.processEvents()
assert window.raid_stats_table.verticalScrollBar().maximum() > 0
window.raid_stats_table.verticalScrollBar().setValue(1)
assert window.raid_matrix_table.verticalScrollBar().value() == 1
window.raid_stats_table.setMaximumHeight(16_777_215)
window.raid_matrix_table.setMaximumHeight(16_777_215)

# Beide Tabellen besitzen unabhängige horizontale Scrollbereiche.
window.raid_stats_table.setMaximumWidth(250)
app.processEvents()
assert window.raid_stats_table.horizontalScrollBar().maximum() > 0
matrix_scroll_before = window.raid_matrix_table.horizontalScrollBar().value()
window.raid_stats_table.horizontalScrollBar().setValue(1)
assert window.raid_matrix_table.horizontalScrollBar().value() == matrix_scroll_before
window.raid_stats_table.setMaximumWidth(16_777_215)

window.raid_matrix_table.setMaximumWidth(250)
app.processEvents()
assert window.raid_matrix_table.horizontalScrollBar().maximum() > 0
stats_scroll_before = window.raid_stats_table.horizontalScrollBar().value()
window.raid_matrix_table.horizontalScrollBar().setValue(1)
assert window.raid_stats_table.horizontalScrollBar().value() == stats_scroll_before
window.raid_matrix_table.setMaximumWidth(16_777_215)

# "Alle" erweitert Matrix und Statistikbasis gemeinsam.
window.matrix_raid_limit.setCurrentIndex(window.matrix_raid_limit.findData(0))
app.processEvents()
rows_by_name = {
    window.raid_stats_table.item(row, 0).text(): row
    for row in range(window.raid_stats_table.rowCount())
}
smoke_row = rows_by_name[smoke.name]
assert len(window._matrix_raids) == 11
assert window.raid_matrix_table.columnCount() == 11
assert window.raid_stats_table.item(smoke_row, 4).data(Qt.ItemDataRole.DisplayRole) == 11
assert window.raid_stats_table.item(smoke_row, 1).data(Qt.ItemDataRole.DisplayRole) == 91
window.matrix_raid_limit.setCurrentIndex(window.matrix_raid_limit.findData(10))
app.processEvents()

# Alle zehn linken Statistikspalten sind sortierbar. Der Refresh ist absichtlich
# deferred, damit QHeaderView unter Windows nicht während sectionClicked umgebaut wird.
sort_keys = [
    "name", "percent", "present", "bench", "eligible",
    "main", "twink", "current_streak", "longest_streak", "last_attendance",
]
for column, expected_key in enumerate(sort_keys):
    window.raid_stats_table.horizontalHeader().sectionClicked.emit(column)
    app.processEvents()
    assert window._matrix_sort_key == expected_key
    assert window.matrix_sort.currentData() == expected_key
    assert window.raid_stats_table.horizontalHeader().sortIndicatorSection() == column

# Ein weiterer Sortierklick verwendet die bereits berechneten Zeilen und darf
# weder Attendance erneut aggregieren noch die Matrixbasis ersetzen.
original_rows_for_scope = window._attendance_rows_for_scope
window._attendance_rows_for_scope = lambda _raids: (_ for _ in ()).throw(
    AssertionError("Sortieren darf keine Attendance-Neuberechnung auslösen")
)
window.raid_stats_table.horizontalHeader().sectionClicked.emit(1)
app.processEvents()
window._attendance_rows_for_scope = original_rows_for_scope
for row, info in enumerate(window._matrix_players):
    assert window.raid_stats_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == info["identifier"]

# Raid-Header führt weiterhin zum Raid; anschließend zurück zur Teilnahme.
window._matrix_raid_clicked(0)
assert window.raid_subtabs.currentIndex() == 0
window.raid_subtabs.setCurrentIndex(1)

# Ansicht und Tabellenfilter wechseln immer gemeinsam Spieler <-> Charakter.
window.matrix_view_character_button.click()
app.processEvents()
assert window._raid_view_mode("matrix") == "character"
assert window.matrix_view_character_button.isChecked()
assert not window.matrix_view_player_button.isChecked()
assert window.matrix_subject_label.text() == "Charakterfilter"
assert window.matrix_subject.currentData() == ""
assert window.matrix_subject.findData(inactive_raid_member.id) < 0
assert window.matrix_subject.findData(dead_raid_member.id) < 0
assert window.raid_stats_table.horizontalHeaderItem(0).text() == "Charakter"
character_subject_index = window.matrix_subject.findData(smoke.id)
assert character_subject_index >= 0
window.matrix_subject.setCurrentIndex(character_subject_index)
app.processEvents()
assert window.raid_stats_table.rowCount() == 1
assert window.raid_matrix_table.rowCount() == 1

window.matrix_view_player_button.click()
app.processEvents()
assert window._raid_view_mode("matrix") == "player"
assert window.matrix_subject_label.text() == "Spielerfilter"
assert window.matrix_subject.currentData() == ""
player_subject_index = window.matrix_subject.findData(smoke.playerId)
assert player_subject_index >= 0
window.matrix_subject.setCurrentIndex(player_subject_index)
app.processEvents()
assert window.raid_stats_table.rowCount() == 1
assert window.raid_matrix_table.rowCount() == 1

# Klick auf den Namen behält die Schnellfilterfunktion.
window.matrix_subject.setCurrentIndex(0)
app.processEvents()
rows_by_name = {
    window.raid_stats_table.item(row, 0).text(): row
    for row in range(window.raid_stats_table.rowCount())
}
window._attendance_table_cell_clicked(rows_by_name[smoke.name], 0)
app.processEvents()
assert window.matrix_subject.currentData() == smoke.playerId
assert window.raid_stats_table.rowCount() == 1
assert window.raid_matrix_table.rowCount() == 1

# Matrix einklappen blendet nur den rechten Raidbereich aus und stellt ihn wieder her.
open_sizes = window.attendance_matrix_split.sizes()
assert open_sizes[1] > 0
window.matrix_toggle_button.click()
app.processEvents()
assert window.matrix_toggle_button.isChecked()
assert window.attendance_matrix_split.sizes()[1] == 0
window.matrix_toggle_button.click()
app.processEvents()
assert not window.matrix_toggle_button.isChecked()
assert window.attendance_matrix_split.sizes()[1] > 0

window.switch_page("graveyard")
window.refresh_graveyard()
app.processEvents()
assert window.grave_canvas.item_count == 2
assert window.grave_canvas.zoom_percent == 100
assert not window.grave_canvas.activation_enabled
window.grave_view.set_zoom_percent(80)
app.processEvents()
window._graveyard_zoom_timer.stop()
window._graveyard_zoom_pending = 80
window._apply_graveyard_zoom()
app.processEvents()
assert window.grave_canvas.zoom_percent == 80

# Verwaltung: Wipe kann mehrere lebende Charaktere als Tot markieren; Einzel-Tod
# bleibt ebenfalls in der Verwaltung und springt nicht automatisch zum Friedhof.
window.switch_page("management")
# Die Verwaltungssuche filtert die jeweilige Tab-Menge weiter und ist nicht
# an die Roster-Suche gekoppelt.
window.search_edit.setText("qtsmoke")
app.processEvents()
assert window.member_table.rowCount() == 1
assert window.member_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == smoke.id
window.set_member_tab("Tot")
window.search_edit.setText("qtsmoketwo")
app.processEvents()
assert window.member_table.rowCount() == 1
assert window.member_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == next(
    member.id for member in window.model.members if member.name == "QtSmokeTwo"
)
window.search_edit.clear()
window.set_member_tab("Gildenliste")
first_wipe = window.model.add_member("WipeOne", "Smoke")
second_wipe = window.model.add_member("WipeTwo", "Smoke")
second_wipe.lifeStatus = "inactive"
changed = window._mark_members_dead([first_wipe.id, second_wipe.id])
assert [member.id for member in changed] == [first_wipe.id, second_wipe.id]
assert first_wipe.lifeStatus == "dead" and second_wipe.lifeStatus == "dead"
assert first_wipe.deathDate and second_wipe.deathDate
no_jump = window.model.add_member("NoJump", "Smoke")
window.refresh_member_table()
window.show_member(no_jump.id)
# Patch the imported QMessageBox class directly; the page must remain management.
from PySide6.QtWidgets import QMessageBox
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
    window.mark_dead_selected()
assert no_jump.lifeStatus == "dead"
assert window.stack.currentWidget() is window._pages["management"]

# Reanimation verwendet denselben Datensatz und macht ihn ohne Neustart wieder
# in der aktiven Gildenliste sichtbar.
window.set_member_tab("Tot")
window._select_member_in_table(no_jump.id)
window.show_member(no_jump.id)
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
    window.toggle_activity_selected()
assert no_jump.lifeStatus == "active"
assert window.member_tab == "Gildenliste"
visible_ids = {
    window.member_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
    for row in range(window.member_table.rowCount())
}
assert no_jump.id in visible_ids

# Manuelle Raidpunkte-Anpassung bleibt nach Anzeige, Save/Load und beiden
# Rebuild-Aktionen persistent und an dieselbe Attendance-ID gebunden.
adjust_model = GuildModel()
adjust_model.new_empty()
adjust_player = adjust_model.add_player("Adjustment Player")
adjust_member = adjust_model.add_member("Grancapitan", "Smoke")
adjust_model.update_member_assignment(
    adjust_member.id, adjust_player.playerId, "main", "dps",
)
adjust_raid, _adjust_summary = adjust_model.create_raid_with_attendance(
    "2026-09-15", "AQ40", "", "AQ40", [adjust_member.name],
)
adjust_model.raid_points.enabled = True
adjust_model.raid_points.ever_enabled = True
adjust_model.raid_points.included_raid_ids.clear()
adjust_model.raid_points_legacy_scope_required = True
adjust_model.point_mode = "raid_points"
adjust_model.dkp_enabled = False
window.model = adjust_model
window._rebuild_raid_derived_state()
window.refresh_raids(force=True)
attendance_id = adjust_model.raid_attendance[0].id

def apply_manual_adjustment(dialog):
    editor_entry, adjustment_widget, reason_widget, _total_label = dialog._editors[0]
    assert editor_entry.id == attendance_id
    adjustment_widget.setValue(5)
    reason_widget.setText("Test")
    return QDialog.DialogCode.Accepted

with patch("app.GuildGearCheckerQt.QInputDialog.getItem", return_value=("Für alle Raids", True)) as migration_choice, \
        patch.object(RaidPointAdjustmentDialog, "exec", apply_manual_adjustment):
    window._adjust_raid_points(adjust_raid)
    migration_choice.assert_called_once()
assert not adjust_model.raid_points_legacy_scope_required
assert adjust_model.raid_points.calculation_mode == "all"

saved_adjustment = adjust_model.raid_points.adjustments[attendance_id]
assert saved_adjustment.value == 5 and saved_adjustment.reason == "Test"
participant_row = next(
    row for row in range(window.raid_participants_table.rowCount())
    if window.raid_participants_table.item(row, 1).text() == adjust_member.name
)
assert float(window.raid_participants_table.item(participant_row, 5).data(Qt.ItemDataRole.DisplayRole)) == 5
assert float(window.raid_participants_table.item(participant_row, 6).data(Qt.ItemDataRole.DisplayRole)) == 15
point_entries = window._raid_point_projection
assert len(point_entries) == 1
assert (point_entries[0].attendance_id, point_entries[0].adjustment, point_entries[0].total_points) == (
    attendance_id, 5, 15,
)
assert point_entries[0].reason == "Test"
assert character_points(adjust_model.raid_points, adjust_model.raids, adjust_model.raid_attendance, adjust_member.id) == 15
assert player_points(adjust_model.raid_points, adjust_model.raids, adjust_model.raid_attendance, adjust_player.playerId) == 15

with tempfile.TemporaryDirectory(prefix="ggc-manual-raid-points-") as temp_dir:
    saved_path = Path(temp_dir) / "adjustment.ggc"
    adjust_model.save(saved_path, backup=False)
    loaded_model = GuildModel()
    loaded_model.load(saved_path)
    loaded_adjustment = loaded_model.raid_points.adjustments[attendance_id]
    assert loaded_adjustment.value == 5 and loaded_adjustment.reason == "Test"
    window.model = loaded_model
    assert window._rebuild_raid_derived_state()
    history_after_load = window._raid_point_projection
    assert len(history_after_load) == 1
    assert (
        history_after_load[0].adjustment, history_after_load[0].total_points,
        history_after_load[0].reason,
    ) == (5, 15, "Test")
    assert character_points(
        loaded_model.raid_points, loaded_model.raids,
        loaded_model.raid_attendance, adjust_member.id,
    ) == 15
    assert player_points(
        loaded_model.raid_points, loaded_model.raids,
        loaded_model.raid_attendance, adjust_player.playerId,
    ) == 15
    window.rebuild_raid_statistics()
    stats_rebuild_history = window._raid_point_projection
    assert len(stats_rebuild_history) == 1
    assert (stats_rebuild_history[0].adjustment, stats_rebuild_history[0].total_points) == (5, 15)
    assert character_points(
        window.model.raid_points, window.model.raids,
        window.model.raid_attendance, adjust_member.id,
    ) == 15
    assert player_points(
        window.model.raid_points, window.model.raids,
        window.model.raid_attendance, adjust_player.playerId,
    ) == 15
    window.rebuild_raid_points()
    points_rebuild_history = window._raid_point_projection
    assert len(points_rebuild_history) == 1
    assert (points_rebuild_history[0].adjustment, points_rebuild_history[0].total_points) == (5, 15)
    assert character_points(
        window.model.raid_points, window.model.raids,
        window.model.raid_attendance, adjust_member.id,
    ) == 15
    assert player_points(
        window.model.raid_points, window.model.raids,
        window.model.raid_attendance, adjust_player.playerId,
    ) == 15
    assert window.model.raid_points.adjustments[attendance_id].reason == "Test"

    # Statuswechsel muss auch mit veraltetem Legacy-Scope zuerst migrieren und
    # anschließend Basis, History sowie Charakter-/Spielersummen neu projizieren.
    loaded_model.raid_points_legacy_scope_required = True
    loaded_model.raid_points.calculation_mode = None
    loaded_model.raid_points.calculation_start_date = None
    loaded_model.raid_points.included_raid_ids.clear()
    window.refresh_raids(force=True)
    participant_row = next(
        row for row in range(window.raid_participants_table.rowCount())
        if window.raid_participants_table.item(row, 1).text() == adjust_member.name
    )
    window.raid_participants_table.selectRow(participant_row)
    with patch(
        "app.GuildGearCheckerQt.QInputDialog.getItem",
        return_value=("Für alle Raids", True),
    ) as migration_choice:
        window.toggle_selected_attendance_status()
        migration_choice.assert_called_once()
    bench_entry = window._raid_point_projection[0]
    assert bench_entry.attendance_status == "bench"
    assert (bench_entry.base_points, bench_entry.adjustment, bench_entry.total_points) == (5, 5, 10)
    participant_row = next(
        row for row in range(window.raid_participants_table.rowCount())
        if window.raid_participants_table.item(row, 1).text() == adjust_member.name
    )
    assert float(window.raid_participants_table.item(participant_row, 5).data(Qt.ItemDataRole.DisplayRole)) == 5
    assert float(window.raid_participants_table.item(participant_row, 6).data(Qt.ItemDataRole.DisplayRole)) == 10
    assert character_points(
        window.model.raid_points, window.model.raids,
        window.model.raid_attendance, adjust_member.id,
    ) == 10
    assert player_points(
        window.model.raid_points, window.model.raids,
        window.model.raid_attendance, adjust_player.playerId,
    ) == 10

    window.model.set_raid_point_adjustment(attendance_id, 2, "Test +2")
    assert window._rebuild_raid_derived_state()
    window.refresh_raid_participants()
    participant_row = next(
        row for row in range(window.raid_participants_table.rowCount())
        if window.raid_participants_table.item(row, 1).text() == adjust_member.name
    )
    assert float(window.raid_participants_table.item(participant_row, 5).data(Qt.ItemDataRole.DisplayRole)) == 2
    assert float(window.raid_participants_table.item(participant_row, 6).data(Qt.ItemDataRole.DisplayRole)) == 7

    window.model.save(saved_path, backup=False)
    bench_loaded_model = GuildModel()
    bench_loaded_model.load(saved_path)
    assert bench_loaded_model.raid_attendance[0].status == "bench"
    assert bench_loaded_model.raid_points.adjustments[attendance_id].value == 2
    assert bench_loaded_model.raid_points.adjustments[attendance_id].reason == "Test +2"
    window.model = bench_loaded_model
    assert window._rebuild_raid_derived_state()
    assert window._raid_point_projection[0].total_points == 7
    window.rebuild_raid_statistics()
    assert (
        window._raid_point_projection[0].base_points,
        window._raid_point_projection[0].adjustment,
        window._raid_point_projection[0].total_points,
    ) == (5, 2, 7)
    window.rebuild_raid_points()
    assert (
        window._raid_point_projection[0].base_points,
        window._raid_point_projection[0].adjustment,
        window._raid_point_projection[0].total_points,
    ) == (5, 2, 7)
    window.refresh_raids(force=True)

    window.raid_participants_table.selectRow(participant_row)
    window.toggle_selected_attendance_status()
    present_entry = window._raid_point_projection[0]
    assert present_entry.attendance_status == "present"
    assert (present_entry.base_points, present_entry.adjustment, present_entry.total_points) == (10, 2, 12)

window.hide()
window.deleteLater()
app.processEvents()

# A second lightweight construction verifies the English surface after the
# German smoke path above without persisting a language change to user settings.
old_language = suite_i18n._translator.language
suite_i18n._translator.language = "en"
try:
    with patch("app.GuildGearCheckerQt.read_suite_settings", return_value={}):
        english_window = SmokeWindow()
    english_window.show()
    app.processEvents()
    assert english_window.project_label.text() == "No project loaded"
    assert english_window._nav_buttons["rooster"].text() == "Roster"
    assert english_window._nav_buttons["graveyard"].text() == "Graveyard"
    assert english_window._nav_buttons["management"].text() == "Management"
    assert english_window._nav_buttons["raid"].text() == "Raid"
    assert english_window._nav_buttons["settings"].text() == "Settings"
    assert english_window.roster_cards_button.text() == "Card View"
    assert english_window.roster_list_button.text() == "List View"
    assert [english_window.roster_list.horizontalHeaderItem(i).text() for i in range(10)] == [
        "Name", "Class", "Role", "Character Type", "Gear Status", "Raid Status", "Life Status",
        "Current DKP", "Eternal DKP Character", "Eternal DKP Player",
    ]
    english_window.hide()
    english_window.deleteLater()
    app.processEvents()
finally:
    suite_i18n._translator.language = old_language

print("Qt Checker Smoke: OK")
