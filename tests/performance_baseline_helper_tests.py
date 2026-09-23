"""Gezielte Tests der isolierten v0.9.1-Performance-Messhilfe."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "performance"))
import performance_baseline_helper as helper  # noqa: E402


class PerformanceBaselineHelperTests(unittest.TestCase):
    def test_frame_calculation_and_invalid_values(self) -> None:
        result = helper.calculate_frame_measurement(60, 1250, 1322)
        self.assertEqual(result["frame_delta"], 72)
        self.assertEqual(result["duration_seconds_text"], "1.200")
        for fps, start, end in ((0, 1, 2), (-1, 1, 2), (60, -1, 2), (60, 3, 3), (60, 4, 3)):
            with self.assertRaises(ValueError):
                helper.calculate_frame_measurement(fps, start, end)

    def test_statistics_and_seven_run_status(self) -> None:
        session = helper.new_session()
        for index in range(7):
            helper.add_run(session, "PERF-001", "cold", 60, index * 100, index * 100 + 60)
        runs = helper.runs_for(session, "PERF-001", "cold")
        stats = helper.statistics_for(runs)
        self.assertEqual(len(runs), 7)
        self.assertEqual(helper.block_status(runs), "FERTIG")
        self.assertAlmostEqual(stats["median"], 1.0)
        self.assertAlmostEqual(stats["mean"], 1.0)
        self.assertAlmostEqual(stats["minimum"], 1.0)
        self.assertAlmostEqual(stats["maximum"], 1.0)
        with self.assertRaises(ValueError):
            helper.add_run(session, "PERF-001", "cold", 60, 800, 860)

    def test_cold_warm_separation_and_correction(self) -> None:
        session = helper.new_session()
        helper.add_run(session, "PERF-002", "cold", 60, 0, 60)
        helper.add_run(session, "PERF-002", "warm", 60, 0, 30)
        self.assertEqual(len(helper.runs_for(session, "PERF-002", "cold")), 1)
        self.assertEqual(len(helper.runs_for(session, "PERF-002", "warm")), 1)
        with self.assertRaises(ValueError):
            helper.add_run(session, "PERF-001", "warm", 60, 0, 30)
        replaced = helper.replace_run(session, "PERF-002", "warm", 1, 60, 0, 90, "korrigiert")
        self.assertEqual(replaced["duration_seconds_text"], "1.500")
        removed = helper.remove_run(session, "PERF-002", "cold", 1)
        self.assertEqual(removed["run_number"], 1)
        self.assertFalse(helper.runs_for(session, "PERF-002", "cold"))

    def test_save_load_continue_and_markdown_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "results" / "session.json"
            export_path = root / "report.md"
            session = helper.new_session()
            helper.update_environment(session, {"computer": "Test-PC", "recording_fps": "60"})
            helper.add_run(session, "PERF-001", "cold", 60, 10, 70, "erster Lauf")
            helper.save_session(result_path, session)
            resumed = helper.load_session(result_path)
            self.assertEqual(helper.next_run_number(resumed, "PERF-001", "cold"), 2)
            helper.export_markdown(export_path, resumed)
            report = export_path.read_text(encoding="utf-8")
            self.assertIn("PERF-001", report)
            self.assertIn("1.000 s", report)
            self.assertIn("Test-PC", report)

    def test_damaged_file_is_rejected_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text("{defekt", encoding="utf-8")
            with self.assertRaises(helper.SessionDataError):
                helper.load_or_create_session(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "{defekt")
            path.write_text(json.dumps(helper.new_session()), encoding="utf-8")
            session = helper.load_session(path)
            session["runs"].append({"perf_id": "PERF-001", "mode": "cold", "run_number": 1})
            with self.assertRaises(helper.SessionDataError):
                helper.validate_session(session)


if __name__ == "__main__":
    unittest.main()
