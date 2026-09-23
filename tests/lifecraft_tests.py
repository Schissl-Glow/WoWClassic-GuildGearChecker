# -*- coding: utf-8 -*-
"""Regression tests for optional private LifeCraft font loading."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest


font_utils = None
repo_root = None


class LifeCraftTests(unittest.TestCase):
    def test_missing_font_uses_readable_fallback_without_crash(self):
        with tempfile.TemporaryDirectory(prefix="ggc-font-") as temp:
            result = font_utils.load_lifecraft_font(Path(temp) / "missing.ttf")
        self.assertEqual(result, font_utils.DEFAULT_UI_FONT)

    def test_repository_font_exists_and_embedded_family_is_detected(self):
        path = repo_root / "assets" / "fonts" / "LifeCraft_Font.ttf"
        self.assertTrue(path.is_file())
        family = font_utils.detect_font_family(path)
        self.assertTrue(family)
        self.assertNotEqual(family, font_utils.DEFAULT_UI_FONT)

    def test_private_registration_never_requires_system_install(self):
        path = repo_root / "assets" / "fonts" / "LifeCraft_Font.ttf"
        family = font_utils.load_lifecraft_font(path)
        self.assertIn(family, {font_utils.detect_font_family(path), font_utils.DEFAULT_UI_FONT})
        if os.name == "nt":
            self.assertEqual(family, font_utils.detect_font_family(path))
        self.assertEqual(font_utils.FR_PRIVATE, 0x10)

    def test_both_applications_use_loaded_family_for_decorative_headers(self):
        for filename in ("GuildGearChecker.py", "GuildPortraitGrabber.py"):
            source = (repo_root / "app" / filename).read_text(encoding="utf-8")
            self.assertIn("load_lifecraft_font(", source)
            self.assertIn("font=(self.header_font_family", source)


def main() -> int:
    global font_utils, repo_root
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    path = repo_root / "app" / "font_utils.py"
    if path.exists():
        spec = importlib.util.spec_from_file_location("ggc_font_target", path)
        font_utils = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = font_utils
        spec.loader.exec_module(font_utils)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LifeCraftTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
