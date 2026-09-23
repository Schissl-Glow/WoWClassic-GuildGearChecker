# -*- coding: utf-8 -*-
"""Process-private Windows font registration with a safe UI fallback."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path

DEFAULT_UI_FONT = "Segoe UI"
FR_PRIVATE = 0x10


def detect_font_family(path: Path) -> str | None:
    try:
        from PIL import ImageFont  # type: ignore
        return str(ImageFont.truetype(str(path), 24).getname()[0]).strip() or None
    except Exception:
        return None


def load_lifecraft_font(path: Path) -> str:
    """Register a TTF for this process only and return its Tk family name."""
    path = Path(path)
    if not path.is_file():
        return DEFAULT_UI_FONT
    family = detect_font_family(path)
    if not family or os.name != "nt":
        return DEFAULT_UI_FONT
    try:
        added = ctypes.windll.gdi32.AddFontResourceExW(str(path.resolve()), FR_PRIVATE, 0)
        return family if added else DEFAULT_UI_FONT
    except Exception:
        return DEFAULT_UI_FONT
