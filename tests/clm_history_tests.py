from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from app.clm_history import (
        ClmEarning, ClmHistoryProjection, ClmRaidHistory, EternalDkpRecord, EternalDkpState,
        classify_manual_dkp, replay_clm_history,
    )
    from app.clm_history_sync import ClmRaidSyncPreview, apply_clm_raid_history
    from app.GuildGearChecker import GuildModel, POINT_MODE_ETERNAL, POINT_MODE_RAID
except ImportError:
    from clm_history import (  # type: ignore
        ClmEarning, ClmHistoryProjection, ClmRaidHistory, EternalDkpRecord, EternalDkpState,
        classify_manual_dkp, replay_clm_history,
    )
    from clm_history_sync import ClmRaidSyncPreview, apply_clm_raid_history  # type: ignore
    import raid_attendance as staged_raid_attendance  # type: ignore
    sys.modules["app.raid_attendance"] = staged_raid_attendance
    from GuildGearChecker import GuildModel, POINT_MODE_ETERNAL, POINT_MODE_RAID  # type: ignore


def _entry(opcode: str, timestamp: int, index: int = 0, **values: object) -> dict:
    return {
        "_a": 900, "_b": index, "_c": timestamp, "_d": opcode, "_e": 1,
        **values,
    }


def _ledger() -> list[dict]:
    start = 1_725_824_400  # 2024-09-08 local evening
    raid_id = f"{start + 10}-0-1-900"
    ignored_id = f"{start + 16}-0-1-900"
    return [
        _entry("P0", start, g=[1, 101], n="Main-Stitches", c=1),
        _entry("P0", start + 1, g=[1, 102], n="Alt-Stitches"),
        _entry("P0", start + 2, g=[1, 103], n="Bench-Stitches"),
        _entry("AC", start + 10, r="roster", n="AQ + ZG", c={}),
        _entry("AS", start + 11, r=raid_id, p=[[1, 101], [1, 102]], s=[[1, 103]]),
        _entry("DR", start + 12, r=raid_id, v=10, t="Start", s=True, n=False),
        _entry("AU", start + 13, r=raid_id, j=[[1, 103]], l=[[1, 102]]),
        _entry("DR", start + 14, r=raid_id, v=5, t="Boss", s=False, n=False),
        _entry("II", start + 15, r=raid_id, p=[1, 101], i=19019, v=500),
        _entry("DR", start + 16, r=raid_id, v=99, t="ignored", s=False, n=False),
        _entry("IGN", start + 17, ref=ignored_id),
        _entry("AE", start + 18, r=raid_id),
        _entry("DM", start + 20, r="roster", p=[[1, 102]], v=8, t="Bench ZG", n=False),
        _entry("DM", start + 21, r="roster", p=[[1, 102]], v=-4, t="Fehlende WBs", n=False),
        _entry("DM", start + 22, r="roster", p=[[1, 102]], v=100, t="DKP Switch", n=False),
        _entry("DM", start + 23, r="roster", p=[[1, 102]], v=-8, t="Bench ZG", n=False),
    ]


class ClmHistoryTests(unittest.TestCase):
    def test_replay_character_snapshot_join_leave_dkp_bench_loot_ign(self) -> None:
        projection = replay_clm_history(_ledger(), "roster")
        self.assertEqual(set(projection.characters.values()), {"Main", "Alt", "Bench"})
        self.assertEqual(projection.character_classes["1:101"], 1)
        self.assertEqual(len(projection.raids), 1)
        raid = projection.raids[0]
        self.assertEqual(raid.raid_types, ("AQ20", "ZG"))
        self.assertTrue(raid.combined)
        self.assertEqual(len(raid.participant_guids), 3)
        self.assertEqual(len(raid.bench_guids), 1)
        totals: dict[str, float] = {}
        bench: dict[str, float] = {}
        for item in projection.earnings:
            totals[item.character_name] = totals.get(item.character_name, 0) + float(item.value)
            if item.kind in {"EARNED_BENCH", "CORRECTION"}:
                bench[item.character_name] = bench.get(item.character_name, 0) + float(item.value)
        self.assertEqual(totals, {"Main": 15, "Alt": 10, "Bench": 15})
        self.assertEqual(bench, {"Alt": 0, "Bench": 10})
        self.assertNotIn(99, [item.value for item in projection.earnings])

    def test_manual_classification_is_earned_only(self) -> None:
        self.assertEqual(classify_manual_dkp("Bank DKP", 10), "EARNED_BENCH")
        self.assertEqual(classify_manual_dkp("DKP Switch", 10), "TRANSFER")
        self.assertEqual(classify_manual_dkp("Fehlende WBs", -10), "PENALTY")
        self.assertEqual(classify_manual_dkp("unklar", 10), "UNRESOLVED")

    def test_character_and_player_totals_roundtrip(self) -> None:
        model = GuildModel(); model.new_empty()
        main = model.add_member("Main", "Test")
        model.assign_character_type(main.id, "main", None, "not_set")
        alt = model.add_member("Alt", "Test")
        model.assign_character_type(alt.id, "twink", main.id, "not_set")
        state = EternalDkpState(records=[
            EternalDkpRecord("a", main.id, main.name, 1000, "EARNED_RAID"),
            EternalDkpRecord("b", alt.id, alt.name, 50, "EARNED_BENCH"),
        ])
        model.eternal_dkp = EternalDkpState.from_dict(state.to_dict())
        self.assertEqual(model.eternal_character_totals()[alt.id], (50, 50))
        self.assertEqual(model.eternal_player_totals()[main.playerId], (1050, 50))

    def test_legacy_both_flags_prefers_eternal_and_preserves_raid_points(self) -> None:
        model = GuildModel(); model.new_empty()
        payload = model.to_payload()
        payload.pop("pointMode", None)
        payload["dkpModeEnabled"] = True
        payload["raidPoints"] = {
            "enabled": True, "everEnabled": True, "includedRaidIds": ["legacy"],
        }
        loaded = GuildModel(); loaded.load_payload(payload)
        self.assertEqual(loaded.active_point_mode(), POINT_MODE_ETERNAL)
        self.assertTrue(loaded.raid_points.enabled)
        self.assertIn("legacy", loaded.raid_points.included_raid_ids)
        loaded.point_mode = POINT_MODE_RAID
        self.assertEqual(loaded.active_point_mode(), POINT_MODE_RAID)

    def test_combined_sync_is_idempotent_and_does_not_duplicate_earnings(self) -> None:
        model = GuildModel(); model.new_empty()
        main = model.add_member("Main", "Test")
        model.assign_character_type(main.id, "main", None, "not_set")
        projection = replay_clm_history(_ledger(), "roster")
        preview = ClmRaidSyncPreview(
            Path("ClassicLootManager.lua"), None, "db", "roster", projection,
            {guid: main.id for guid, name in projection.characters.items() if name == "Main"},
            tuple(name for name in projection.characters.values() if name != "Main"), (), {},
        )
        decisions = {"Alt": ("twink", main.id), "Bench": ("main", None)}
        first = apply_clm_raid_history(model, preview, decisions)
        second_preview = ClmRaidSyncPreview(
            preview.source_path, None, "db", "roster", projection,
            {
                guid: model.find_by_name(name).id
                for guid, name in projection.characters.items()
            }, (), (), {},
        )
        second = apply_clm_raid_history(model, second_preview)
        self.assertEqual(first.created_raids, 1)
        self.assertEqual(second.created_raids, 0)
        self.assertEqual(len(model.raids), 1)
        self.assertEqual(len(model.eternal_dkp.records), len({r.event_id for r in model.eternal_dkp.records}))

    def test_persistence_keeps_eternal_projection(self) -> None:
        model = GuildModel(); model.new_empty()
        model.point_mode = POINT_MODE_ETERNAL
        model.dkp_enabled = True
        model.eternal_dkp.records.append(
            EternalDkpRecord("event", "m1", "Name", 12, "EARNED_BENCH"),
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "project.ggc"
            model.save(path, backup=False)
            loaded = GuildModel(); loaded.load(path)
        self.assertEqual(loaded.active_point_mode(), POINT_MODE_ETERNAL)
        self.assertEqual(loaded.eternal_dkp.character_totals()["m1"], (12, 12))

    def test_csv_enriches_clm_raid_and_same_report_may_cover_two_instances(self) -> None:
        model = GuildModel(); model.new_empty()
        main = model.add_member("Main", "Test")
        model.assign_character_type(main.id, "main", None, "not_set")
        existing = model.create_raid("2026-09-08", "ZG", "", "ZG")
        existing.sources = ("clm",)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = "https://vanilla.warcraftlogs.com/reports/TestReport123"
            paths = []
            for raid_type in ("ZulGurub", "AQ20"):
                path = root / f"2026-09-08_{raid_type}_Casts.csv"
                path.write_text(
                    f'"META_RAID_TYPE","{raid_type}"\n'
                    f'"META_RAID_DATE","2026-09-08"\n'
                    f'"META_REPORT_URL","{report}"\n'
                    '"Name","Amount","Ilvl","Active","CPM",""\n'
                    '"Main","1","60","1","1",""\n',
                    encoding="utf-8",
                )
                paths.append(path)
            plans = model.analyze_bulk_raid_csv_files(paths)
            self.assertEqual({plan.status for plan in plans}, {"merge", "new"})
            result = model.import_bulk_raid_csv_plans(plans)
            self.assertEqual(result.imported, 2)
            self.assertEqual(len(model.raids), 2)
            self.assertEqual({raid.warcraftLogsUrl for raid in model.raids}, {report})
            repeated = model.analyze_bulk_raid_csv_files(paths)
            self.assertTrue(all(plan.status == "existing" for plan in repeated))

    def test_csv_raid_without_clm_is_enriched_once_and_keeps_attendance(self) -> None:
        model = GuildModel(); model.new_empty()
        model.point_mode = POINT_MODE_ETERNAL
        model.dkp_enabled = True
        main = model.add_member("CSV Main", "Test")
        model.assign_character_type(main.id, "main", None, "not_set")
        csv_raid, _summary = model.create_raid_with_attendance(
            "2026-09-08", "ZG", "https://vanilla.warcraftlogs.com/reports/csv",
            "ZG", [main.name],
        )
        attendance_before = [entry.to_dict() for entry in model.attendance_for_raid(csv_raid.id)]
        self.assertEqual(model.eternal_dkp.records, [])

        history = ClmRaidHistory(
            "clm-csv-zg", "roster", "ZG", 1_725_824_400, "2026-09-08", ("ZG",),
        )
        history.participant_guids.add("1:1")
        projection = ClmHistoryProjection(
            characters={"1:1": main.name}, character_classes={}, raids=(history,),
            standalone_earnings=(ClmEarning(
                "earned-csv-zg", history.clm_raid_id, "1:1", main.name,
                25, "EARNED_RAID", 1,
            ),), unresolved_events=(), ignored_event_ids=(),
        )
        preview = ClmRaidSyncPreview(
            Path("ClassicLootManager.lua"), None, "db", "roster", projection,
            {"1:1": main.id}, (), (), {},
        )

        first = apply_clm_raid_history(model, preview)
        self.assertEqual((first.created_raids, first.enriched_raids), (0, 1))
        self.assertEqual(len(model.raids), 1)
        self.assertEqual(model.raids[0].id, csv_raid.id)
        self.assertEqual(model.raids[0].clmRaidIds, [history.clm_raid_id])
        self.assertEqual(
            [entry.to_dict() for entry in model.attendance_for_raid(csv_raid.id)],
            attendance_before,
        )
        self.assertEqual(
            [(record.event_id, record.raid_id, record.value) for record in model.eternal_dkp.records],
            [("earned-csv-zg", csv_raid.id, 25)],
        )

        second = apply_clm_raid_history(model, preview)
        self.assertEqual((second.created_raids, second.enriched_raids), (0, 1))
        self.assertEqual(len(model.raids), 1)
        self.assertEqual(
            [entry.to_dict() for entry in model.attendance_for_raid(csv_raid.id)],
            attendance_before,
        )
        self.assertEqual(
            [(record.event_id, record.raid_id, record.value) for record in model.eternal_dkp.records],
            [("earned-csv-zg", csv_raid.id, 25)],
        )

    def test_clm_raid_id_has_priority_and_ambiguous_csv_raids_are_not_linked(self) -> None:
        model = GuildModel(); model.new_empty()
        main = model.add_member("Main", "Test")
        model.assign_character_type(main.id, "main", None, "not_set")
        linked, _summary = model.create_raid_with_attendance(
            "2026-09-01", "Old ZG", "", "ZG", [main.name],
        )
        same_day, _summary = model.create_raid_with_attendance(
            "2026-09-08", "CSV ZG", "", "ZG", [main.name],
        )
        linked.clmRaidIds.append("clm-priority")
        duplicate, _summary = model.create_raid_with_attendance(
            "2026-09-08", "Second CSV ZG", "", "ZG", [main.name],
        )

        prioritized = ClmRaidHistory(
            "clm-priority", "roster", "ZG", 1_725_824_400, "2026-09-08", ("ZG",),
        )
        ambiguous = ClmRaidHistory(
            "clm-ambiguous", "roster", "ZG", 1_725_824_500, "2026-09-08", ("ZG",),
        )
        projection = ClmHistoryProjection(
            characters={"1:1": main.name}, character_classes={},
            raids=(prioritized, ambiguous), standalone_earnings=(),
            unresolved_events=(), ignored_event_ids=(),
        )
        preview = ClmRaidSyncPreview(
            Path("ClassicLootManager.lua"), None, "db", "roster", projection,
            {"1:1": main.id}, (), (), {},
        )

        apply_clm_raid_history(model, preview)

        self.assertIn("clm-priority", linked.clmRaidIds)
        self.assertEqual(same_day.clmRaidIds, [])
        self.assertEqual(duplicate.clmRaidIds, [])
        created = [raid for raid in model.raids if "clm-ambiguous" in raid.clmRaidIds]
        self.assertEqual(len(created), 1)
        self.assertNotIn(created[0].id, {same_day.id, duplicate.id})

    def test_ambiguous_historical_name_can_select_existing_incarnation(self) -> None:
        model = GuildModel(); model.new_empty()
        active = model.add_member("Twin", "Test")
        model.assign_character_type(active.id, "main", None, "not_set")
        historical = model.make_member("Twin", "Test")
        historical.lifeStatus = "dead"
        model.members.append(historical)
        projection = ClmHistoryProjection(
            characters={"1:1": "Twin"}, character_classes={"1:1": 1}, raids=(),
            standalone_earnings=(ClmEarning(
                "event", "", "1:1", "Twin", 10, "EARNED_OTHER", 1,
            ),), unresolved_events=(), ignored_event_ids=(),
        )
        preview = ClmRaidSyncPreview(
            Path("ClassicLootManager.lua"), None, "db", "roster", projection,
            {}, (), ("Twin",), {"twin": (active.id, historical.id)},
        )
        apply_clm_raid_history(model, preview, {"Twin": ("existing", historical.id)})
        self.assertEqual(model.eternal_dkp.records[0].member_id, historical.id)

    def test_replay_scopes_sessions_and_profiles_to_selected_roster_id(self) -> None:
        start = 1_725_824_400
        bierstube_raid = f"{start + 10}-10-1-900"
        foreign_raid = f"{start + 20}-20-1-900"
        ledger = [
            _entry("P0", start, g=[1, 101], n="Bierstube-Stitches", c=1),
            _entry("P0", start + 1, g=[1, 201], n="Testchar-Stitches", c=2),
            _entry("AC", start + 10, 10, r="1730228604", n="ZG"),
            _entry("AS", start + 11, 11, r=bierstube_raid, p=[[1, 101]]),
            _entry("DR", start + 12, 12, r=bierstube_raid, v=10, t="Boss", n=False),
            _entry("AE", start + 13, 13, r=bierstube_raid),
            _entry("AC", start + 20, 20, r="test-roster", n="AQ20"),
            _entry("AS", start + 21, 21, r=foreign_raid, p=[[1, 201]]),
            _entry("DR", start + 22, 22, r=foreign_raid, v=99, t="Boss", n=False),
            _entry("AE", start + 23, 23, r=foreign_raid),
            _entry("DM", start + 24, 24, r="test-roster", p=[[1, 201]], v=8, t="Bench AQ20", n=False),
        ]

        projection = replay_clm_history(ledger, "1730228604")

        self.assertEqual([raid.clm_raid_id for raid in projection.raids], [bierstube_raid])
        self.assertEqual(projection.characters, {"1:101": "Bierstube"})
        self.assertEqual(
            [(entry.character_name, entry.value) for entry in projection.earnings],
            [("Bierstube", 10)],
        )

    def test_historical_assignment_actions_keep_guild_history_and_exclude_irrelevant(self) -> None:
        model = GuildModel(); model.new_empty()
        main = model.add_member("Main A", "Test")
        model.assign_character_type(main.id, "main", None, "not_set")
        raid = ClmRaidHistory("clm-1", "1730228604", "ZG", 1_725_824_400, "2024-09-08", ("ZG",))
        raid.participant_guids.update({"1:2", "1:3", "1:4", "1:6"})
        dead_twink_raid = ClmRaidHistory("clm-2", "1730228604", "AQ20", 1_725_910_800, "2024-09-09", ("AQ20",))
        dead_twink_raid.participant_guids.add("1:5")
        projection = ClmHistoryProjection(
            characters={"1:2": "Twink B", "1:3": "Portchar C", "1:4": "Tot D", "1:5": "Tot Twink E", "1:6": "PUG F"},
            character_classes={}, raids=(raid, dead_twink_raid),
            standalone_earnings=tuple(
                ClmEarning(f"event-{guid}", "clm-1", guid, name, 10, "EARNED_RAID", 1)
                for guid, name in {
                    "1:2": "Twink B", "1:3": "Portchar C", "1:4": "Tot D", "1:5": "Tot Twink E", "1:6": "PUG F",
                }.items()
            ), unresolved_events=(), ignored_event_ids=(),
        )
        preview = ClmRaidSyncPreview(
            Path("ClassicLootManager.lua"), None, "db", "1730228604", projection,
            {}, ("Twink B", "Portchar C", "Tot D", "Tot Twink E", "PUG F"), (), {},
        )
        apply_clm_raid_history(model, preview, {
            "Twink B": ("twink", main.id), "Portchar C": ("inactive", None),
            "Tot D": ("dead", None), "Tot Twink E": ("dead_twink", main.id),
            "PUG F": ("irrelevant", None),
        })

        twink_b = model.find_by_name("Twink B")
        portchar_c = model.find_by_name("Portchar C")
        dead_d = model.find_by_name("Tot D")
        dead_e = model.find_by_name("Tot Twink E")
        self.assertEqual((twink_b.characterType, twink_b.playerId), ("twink", main.playerId))
        self.assertEqual(portchar_c.lifeStatus, "inactive")
        self.assertEqual((dead_d.lifeStatus, dead_d.deathDate, dead_d.graveTemplateId), ("dead", "", ""))
        self.assertEqual((dead_e.lifeStatus, dead_e.characterType, dead_e.playerId), ("dead", "twink", main.playerId))
        self.assertIsNone(model.find_by_name("PUG F"))
        self.assertEqual({record.character_name for record in model.eternal_dkp.records}, {"Twink B", "Portchar C", "Tot D", "Tot Twink E"})
        self.assertEqual({entry.characterNameSnapshot for entry in model.raid_attendance}, {"Twink B", "Portchar C", "Tot D", "Tot Twink E"})
        self.assertIn("1:6", model.eternal_dkp.ignored_character_guids)
        self.assertEqual(model.eternal_player_totals()[main.playerId][0], 20)
        model.activate_raid_points(include_existing=True)
        self.assertEqual(sum(entry.total_points for entry in model.raid_point_history()), 40)

    def test_historical_dead_twink_bench_bypasses_only_manual_eligibility(self) -> None:
        model = GuildModel(); model.new_empty()
        main = model.add_member("Main A", "Test")
        model.assign_character_type(main.id, "main", None, "not_set")
        historical = model.add_member("Historischer Twink", "Test")
        model.assign_character_type(historical.id, "twink", main.id, "not_set")
        historical.lifeStatus = "dead"
        raid = ClmRaidHistory("clm-bench", "1730228604", "ZG", 1_725_824_400, "2024-09-08", ("ZG",))
        raid.bench_guids.add("1:2")
        projection = ClmHistoryProjection(
            characters={"1:2": historical.name}, character_classes={}, raids=(raid,),
            standalone_earnings=(ClmEarning("bench-earned", "clm-bench", "1:2", historical.name, 10, "EARNED_BENCH", 1),),
            unresolved_events=(), ignored_event_ids=(),
        )
        preview = ClmRaidSyncPreview(
            Path("ClassicLootManager.lua"), None, "db", "1730228604", projection,
            {"1:2": historical.id}, (), (), {},
        )
        apply_clm_raid_history(model, preview)

        bench_entries = [entry for entry in model.raid_attendance if entry.status == "bench"]
        self.assertEqual([(entry.memberId, entry.playerId) for entry in bench_entries], [(historical.id, main.playerId)])
        self.assertEqual(model.eternal_player_totals()[main.playerId][0], 10)
        model.activate_raid_points(include_existing=True)
        self.assertEqual(sum(entry.total_points for entry in model.raid_point_history()), 5)
        model.set_historical_raid_bench_members(model.raids[0].id, [historical.id])
        self.assertEqual(len([entry for entry in model.raid_attendance if entry.status == "bench"]), 1)

        blocked = model.add_member("Manuell blockiert", "Test")
        model.assign_character_type(blocked.id, "main", None, "not_set")
        model.find_player_by_id(blocked.playerId).membershipStartDate = "2025-01-01"
        manual = model.create_raid("2024-09-09", "Manual", "", "ZG")
        manual.status = "recorded"
        with self.assertRaises(ValueError):
            model.set_raid_bench_players(manual.id, [blocked.playerId])

    def test_historical_present_wins_over_bench_for_the_same_player(self) -> None:
        model = GuildModel(); model.new_empty()
        main = model.add_member("Main A", "Test")
        model.assign_character_type(main.id, "main", None, "not_set")
        twink = model.add_member("Twink B", "Test")
        model.assign_character_type(twink.id, "twink", main.id, "not_set")
        twink.lifeStatus = "dead"
        raid = ClmRaidHistory("clm-conflict", "1730228604", "ZG", 1_725_824_400, "2024-09-08", ("ZG",))
        raid.participant_guids.add("1:2")
        raid.bench_guids.add("1:1")
        projection = ClmHistoryProjection(
            characters={"1:1": main.name, "1:2": twink.name}, character_classes={}, raids=(raid,),
            standalone_earnings=(), unresolved_events=(), ignored_event_ids=(),
        )
        preview = ClmRaidSyncPreview(
            Path("ClassicLootManager.lua"), None, "db", "1730228604", projection,
            {"1:1": main.id, "1:2": twink.id}, (), (), {},
        )
        apply_clm_raid_history(model, preview)

        entries = model.attendance_for_raid(model.raids[0].id)
        self.assertEqual(
            [(entry.playerId, entry.memberId, entry.status) for entry in entries],
            [(main.playerId, twink.id, "present")],
        )
        model.activate_raid_points(include_existing=True)
        self.assertEqual(sum(entry.total_points for entry in model.raid_point_history()), 10)

        blocked = model.add_member("Manuell blockiert", "Test")
        model.assign_character_type(blocked.id, "main", None, "not_set")
        model.find_player_by_id(blocked.playerId).membershipStartDate = "2025-01-01"
        manual = model.create_raid("2024-09-09", "Manual", "", "ZG")
        manual.status = "recorded"
        with self.assertRaises(ValueError):
            model.set_raid_bench_players(manual.id, [blocked.playerId])


if __name__ == "__main__":
    unittest.main()
