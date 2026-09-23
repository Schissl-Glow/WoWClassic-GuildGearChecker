import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("guildgear_release", ROOT / "app" / "GuildGearChecker.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def dead_member():
    return SimpleNamespace(id="m0001", name="Placeholder", lifeStatus="dead", deathDate="2026-09-13", className="Mage", spec="Frost", portraitOffsetX=0.0, portraitOffsetY=0.0, portraitZoom=1.0, textOffsetX=0.0, textOffsetY=0.0, textScale=1.0)


class GraveyardPlaceholderTests(unittest.TestCase):
    def test_placeholder_variation_is_stable_and_in_range(self):
        path = Path("portrait_placeholder.png")
        first = MODULE.graveyard_placeholder_variation(dead_member(), path)
        second = MODULE.graveyard_placeholder_variation(dead_member(), path)
        other = dead_member(); other.id = "m0002"
        self.assertEqual(first, second)
        self.assertGreaterEqual(first[0], 0); self.assertLessEqual(first[0], 1)
        self.assertGreaterEqual(first[1], 0); self.assertLessEqual(first[1], 1)
        self.assertGreaterEqual(first[2], 1.3); self.assertLessEqual(first[2], 1.6)
        self.assertNotEqual(first, MODULE.graveyard_placeholder_variation(other, path))

    def test_final_compositing_uses_placeholder(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "placeholder.png"
            Image.new("RGBA", (80, 40), (18, 220, 70, 255)).save(source)
            card = MODULE.render_gravestone_card(dead_member(), Image.new("RGBA", (900, 900), (0, 0, 0, 0)), source, size=(900, 900))
            box = MODULE._scaled_gravestone_box(MODULE.GRAVESTONE_PORTRAIT_BOX, (900, 900))
            pixel = card.getpixel(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2))
            self.assertGreater(pixel[1], 150)
            self.assertLess(pixel[0], 100)

    def test_precedence_and_missing_placeholder_are_safe(self):
        resolver = object.__new__(MODULE.GuildGearCheckerApp)
        with tempfile.TemporaryDirectory() as td:
            real = Path(td) / "real.png"
            real.touch()
            resolver.portrait_candidates = lambda _member: iter((real,))
            self.assertEqual(resolver.graveyard_portrait_path(dead_member()), real)
        card = MODULE.render_gravestone_card(dead_member(), Image.new("RGBA", (900, 900), (0, 0, 0, 0)), None, size=(900, 900))
        self.assertEqual(card.size, (900, 900))

    def test_gravestone_placeholder_is_text_only_fallback(self):
        special = MODULE.gravestone_placeholder_path()
        self.assertTrue(special.is_file())
        frame = MODULE.prepare_gravestone_template(special, (900, 900))
        card = MODULE.render_gravestone_card(dead_member(), frame, None, size=(900, 900))
        self.assertEqual(card.size, (900, 900))
        self.assertGreater(max(card.getchannel("A").getdata()), 0)
        self.assertNotIn("gravestone_placeholder.png", MODULE.gravestone_manifest_path().read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
