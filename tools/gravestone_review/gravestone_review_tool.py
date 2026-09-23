from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageTk, __version__ as PILLOW_VERSION

try:
    from .gravestone_review_core import (
    ASSET_DIR_NAME,
    LOGGER,
    SUPPORTED_SUFFIXES,
    AssetValidator,
    CheckResult,
    GeometryConfig,
    OpeningAnalysis,
    opening_transparency_metrics,
    accept_candidate,
    approve_accepted,
    delete_rejected,
    ensure_workspace,
    flush_review_logs,
    list_accepted,
    list_approved,
    list_candidates,
    list_rejected,
    locate_project_root,
    log_validation,
    normalize_review_image,
    reject_candidate,
    restore_accepted,
    review_counts,
    run_core_self_test,
    setup_review_logging,
    )
except ImportError:  # Standalone script execution
    from gravestone_review_core import (
    ASSET_DIR_NAME,
    LOGGER,
    SUPPORTED_SUFFIXES,
    AssetValidator,
    CheckResult,
    GeometryConfig,
    OpeningAnalysis,
    opening_transparency_metrics,
    accept_candidate,
    approve_accepted,
    delete_rejected,
    ensure_workspace,
    flush_review_logs,
    list_accepted,
    list_approved,
    list_candidates,
    list_rejected,
    locate_project_root,
    log_validation,
    normalize_review_image,
    reject_candidate,
    restore_accepted,
    review_counts,
    run_core_self_test,
    setup_review_logging,
    )

# Same cover-fit implementation as the checker; gravestone_review_core already
# makes the suite root importable for standalone execution.
from app.gravestone_portrait import fit_portrait as fit_shared_gravestone_portrait
from app.i18n import get_language, gravestone_category_display, tr
try:
    from .gravestone_alpha_editor import AlphaEditorDialog
except ImportError:  # Standalone script execution
    from gravestone_alpha_editor import AlphaEditorDialog
from app.gravestone_categories import (
    GRAVESTONE_CATEGORIES,
    GRAVESTONE_CATEGORY_LABEL,
    GRAVESTONE_CATEGORY_FIELD,
    GRAVESTONE_DEFAULT_OFFSET_X_FIELD,
    GRAVESTONE_DEFAULT_OFFSET_Y_FIELD,
    GRAVESTONE_DEFAULT_ZOOM_FIELD,
    GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD,
    load_gravestone_category,
    load_gravestone_portrait_preset,
    load_gravestone_text_safe_area,
    normalize_gravestone_category,
    save_gravestone_category,
    save_gravestone_portrait_preset,
)
from app.gravestone_templates import MANIFEST_FILENAME

APP_TITLE = "Gravestone Review Tool – v0.7.0"

QUEUE_TRANSLATION_KEYS = {
    "Kandidaten": "review.queue_candidates",
    "Akzeptiert": "review.queue_accepted",
    "Abgelehnt": "review.queue_rejected",
    "Freigegeben": "review.queue_approved",
    "Produktiv": "review.queue_productive",
}
BROWSER_VIEW_TRANSLATION_KEYS = {
    "Einzelansicht": "review.single_view",
    "Galerie": "review.gallery_view",
    "Listenansicht": "review.list_view",
}
VIEW_TRANSLATION_KEYS = {
    "Graveyard": "review.view_graveyard",
    "Dunkel": "review.view_dark",
    "Transparenz": "review.view_transparency",
}
MODE_TRANSLATION_KEYS = {
    "Zusammengesetzt": "review.mode_composite",
    "Original PNG": "review.mode_original",
    "Öffnung prüfen": "review.mode_opening_check",
}


CHECK_LABEL_TRANSLATION_KEYS = {
    "Bild lesbar": "review_core.image_readable",
    "Flexible Canvas-Größe": "review_core.flexible_canvas_size",
    "Alpha-Kanal": "review_core.alpha_channel",
    "Canvas-Kante frei": "review_core.canvas_edge_clear",
    "Sicherheitsabstand": "review_core.safety_margin",
    "Portraitöffnung erkannt": "review_core.opening_detected",
    "Portraitöffnung Position": "review_core.opening_position",
    "Portraitöffnung Größe plausibel": "review_core.opening_size_plausible",
    "Portraitöffnung Form plausibel": "review_core.opening_shape_plausible",
    "Portraitöffnung Master-Überdeckung": "review_core.opening_master_overlap",
    "Master-Kernvergleich": "review_core.master_core_comparison",
    "Transparenz innerhalb Portraitöffnung": "review_core.transparency_inside_opening",
    "Innenkante / Anti-Aliasing plausibel": "review_core.inner_edge_plausible",
    "Portraitrahmen plausibel": "review_core.portrait_frame_plausible",
    "Keine auffälligen Alpha-Inseln": "review_core.no_alpha_islands",
}

CORE_PROGRESS_TRANSLATION_KEYS = {
    "Technische Prüfung": "review_core.progress_technical",
    "Nach Akzeptiert verschieben": "review_core.progress_accept_move",
    "Akzeptiert": "review_core.progress_accepted",
    "1/5 Prüfung": "review_core.progress_1",
    "2/5 Master freigeben": "review_core.progress_2",
    "3/5 537×732-PNG erzeugen": "review_core.progress_3",
    "4/5 kleine PNG prüfen": "review_core.progress_4",
    "5/5 Abschluss": "review_core.progress_5",
}


def _localize_check_label(text: str) -> str:
    key = CHECK_LABEL_TRANSLATION_KEYS.get(str(text))
    return tr(key) if key else str(text)


def _localize_progress_text(text: str) -> str:
    key = CORE_PROGRESS_TRANSLATION_KEYS.get(str(text))
    return tr(key) if key else str(text)


def _localize_core_detail(text: str) -> str:
    """Localize validator diagnostics at the UI boundary without changing core behavior/logs."""
    value = str(text or "")
    if not value or get_language() == "de":
        return value

    exact = {
        "Keine adaptive Portraitöffnung erkannt; Legacy-Fallback aktiv": tr("review_core.no_adaptive"),
        "Keine Öffnung erkannt": tr("review_core.no_opening"),
        "Keine technisch nutzbare adaptive Öffnung erkannt": tr("review_core.no_usable_opening"),
        "Keine Portraitmaske verfügbar": tr("review_core.no_mask"),
        "Kein adaptiver Innenkanten-Prüfring verfügbar": tr("review_core.no_inner_ring"),
        "Kein adaptiver Prüfring verfügbar": tr("review_core.no_ring"),
        "Öffnung berührt den Canvas-Rand": tr("review_core.opening_touches_border"),
        "Öffnung geometrisch unplausibel": tr("review_core.opening_implausible"),
        "Transparenter Seed ergab keine zusammenhängende Öffnung": tr("review_core.seed_no_opening"),
        "Adaptive Portraitöffnung erkannt": tr("review_core.adaptive_detected"),
    }
    if value in exact:
        return exact[value]

    # Opening-detector fallback reasons can contain multiple semicolon-separated parts.
    if "; " in value:
        localized_parts = [_localize_core_detail(part) for part in value.split("; ")]
        if any(a != b for a, b in zip(localized_parts, value.split("; "))):
            return "; ".join(localized_parts)

    m = re.fullmatch(r"Quelle: (\d+)×(\d+)(?:; wird proportional auf (\d+)×(\d+) eingepasst)?", value)
    if m:
        result = tr("review_core.source", width=m.group(1), height=m.group(2))
        if m.group(3):
            result += "; " + tr("review_core.scaled_fit", width=m.group(3), height=m.group(4))
        return result
    m = re.fullmatch(r"Modus: (.+)", value)
    if m:
        return tr("review_core.mode", mode=m.group(1))
    m = re.fullmatch(r"Nicht transparente Pixel in den äußeren (\d+)px: (\d+) \(oben (\d+), unten (\d+), links (\d+), rechts (\d+)\)", value)
    if m:
        return tr("review_core.outer_pixels", px=m.group(1), count=m.group(2), top=m.group(3), bottom=m.group(4), left=m.group(5), right=m.group(6))
    m = re.fullmatch(r"Erkannte Öffnung vorhanden; Fläche (\d+) px", value)
    if m:
        return tr("review_core.opening_exists_area", area=m.group(1))
    m = re.fullmatch(r"Abstand zur Referenzmitte: ([\d.]+)px(?: \((.+)\))?", value)
    if m:
        result = tr("review_core.center_distance", value=m.group(1))
        return result + _localized_diagnostic_suffix(m.group(2))
    m = re.fullmatch(r"Flächenverhältnis zur Referenzöffnung: ([\d.]+)(?: \((.+)\))?", value)
    if m:
        result = tr("review_core.area_ratio", value=m.group(1))
        return result + _localized_diagnostic_suffix(m.group(2))
    m = re.fullmatch(r"Breite ([\d.]+)×, Höhe ([\d.]+)× der Referenzöffnung(?: \((.+)\))?", value)
    if m:
        result = tr("review_core.width_height_ratio", width=m.group(1), height=m.group(2))
        return result + _localized_diagnostic_suffix(m.group(3))
    m = re.fullmatch(r"Überdeckung mit Referenzöffnung: ([\d.]+%)(?: \((.+)\))?", value)
    if m:
        result = tr("review_core.overlap", value=m.group(1))
        return result + _localized_diagnostic_suffix(m.group(2))
    m = re.fullmatch(r"Transparenz im Master-Kernvergleich: ([\d.]+%)(?: \((.+)\))?", value)
    if m:
        result = tr("review_core.master_transparency", value=m.group(1))
        return result + _localized_diagnostic_suffix(m.group(2))
    m = re.fullmatch(r"Adaptive Innenkante: transparent ([\d.]+%), halbtransparent ([\d.]+%), opak ([\d.]+%)", value)
    if m:
        return tr("review_core.adaptive_inner_edge", transparent=m.group(1), semi=m.group(2), opaque=m.group(3))
    m = re.fullmatch(r"Rahmenbelegung um reale Öffnung: ([\d.]+%)", value)
    if m:
        return tr("review_core.frame_coverage", value=m.group(1))
    m = re.fullmatch(r"Isolierte Alpha-Bereiche: (\d+)", value)
    if m:
        return tr("review_core.isolated_alpha", count=m.group(1))
    m = re.fullmatch(r"transparent (\d+), teiltransparent (\d+), nichttransparent (\d+); Transparenz-Anteil ([\d.]+%)", value)
    if m:
        return tr("review_core.transparency_counts", transparent=m.group(1), semi=m.group(2), opaque=m.group(3), ratio=m.group(4))
    m = re.fullmatch(r"Fläche zu klein \((\d+) < (\d+)\)", value)
    if m:
        return tr("review_core.area_too_small", area=m.group(1), minimum=m.group(2))
    m = re.fullmatch(r"Fläche zu groß \((\d+) > (\d+)\)", value)
    if m:
        return tr("review_core.area_too_large", area=m.group(1), maximum=m.group(2))
    m = re.fullmatch(r"Breite zu klein \((\d+)px\)", value)
    if m:
        return tr("review_core.width_too_small", width=m.group(1))
    m = re.fullmatch(r"Höhe zu klein \((\d+)px\)", value)
    if m:
        return tr("review_core.height_too_small", height=m.group(1))
    return value


def _localized_diagnostic_suffix(text: str | None) -> str:
    if not text:
        return ""
    keys = {
        "Designabweichung": "review_core.design_deviation",
        "starke Designabweichung": "review_core.strong_design_deviation",
        "für Portraitnutzung unplausibel": "review_core.implausible_portrait",
        "nur Warnung": "review_core.warning_only",
        "nur Warnung; adaptive Öffnungserkennung ist maßgeblich": "review_core.warning_only_adaptive",
    }
    key = keys.get(text)
    return f" ({tr(key) if key else text})"



def _localize_core_error(error: object) -> str:
    text = str(error or "")
    if not text or get_language() == "de":
        return text
    exact = {
        "Kandidat liegt nicht direkt in _candidates": "review_error.candidate_location",
        "gravestone_placeholder.png ist eine Sonderdatei und kein Kandidat": "review_error.placeholder_not_candidate",
        "Datei liegt nicht direkt in _accepted": "review_error.accepted_location",
        "gravestone_placeholder.png ist eine Sonderdatei": "review_error.placeholder_special",
        "Löschen ist ausschließlich in _rejected erlaubt": "review_error.delete_only_rejected",
        "gravestone_placeholder.png darf nicht gelöscht werden": "review_error.placeholder_delete_forbidden",
        "Nur PNG-Dateien dürfen gelöscht werden": "review_error.png_only",
        "Grabstein-Kategorie muss gewählt sein.": "review_error.category_required",
        "Text-Safe-Area ist ungültig.": "review_error.text_safe_area_invalid",
        "Produktives Grabstein-Manifest ist ungültig.": "review_error.manifest_invalid",
    }
    if text in exact:
        return tr(exact[text])
    prefixes = (
        ("Akzeptierte Datei existiert bereits: ", "review_error.accepted_exists", "path"),
        ("Kandidat existiert bereits: ", "review_error.candidate_exists", "path"),
        ("Freigegebener Master existiert bereits: ", "review_error.approved_master_exists", "path"),
        ("Komprimierte Datei existiert bereits: ", "review_error.compressed_exists", "path"),
        ("Grabstein-Metadaten existieren bereits: ", "review_error.metadata_exists", "path"),
        ("Abgelehnte Datei existiert bereits: ", "review_error.rejected_exists", "path"),
        ("Unbekannte Grabstein-ID: ", "review_error.unknown_gravestone_id", "id"),
    )
    for prefix, key, field in prefixes:
        if text.startswith(prefix):
            return tr(key, **{field: text[len(prefix):]})
    critical = "Kritische technische Fehler: "
    if text.startswith(critical):
        parts = [part.strip() for part in text[len(critical):].split(",") if part.strip()]
        return tr("review_error.critical_errors", items=", ".join(_localize_check_label(part) for part in parts))
    small_png = "Technische Prüfung der kleinen PNG fehlgeschlagen: "
    if text.startswith(small_png):
        return tr("review_error.small_png_failed", detail=_localize_core_detail(text[len(small_png):]))
    return text

class GraveyardRenderer:
    def __init__(self, geometry: GeometryConfig, tool_dir: Path, project_root: Path):
        self.geometry = geometry
        self.tool_dir = tool_dir
        self.project_root = project_root
        self.background_path = project_root / "assets" / ASSET_DIR_NAME / "Background_001.png"
        self.test_portrait_path = tool_dir / "reference" / "test_portrait.png"
        self.portrait_path: Path | None = self.test_portrait_path if self.test_portrait_path.exists() else None
        self.portrait_offset_x = 0.0
        self.portrait_offset_y = 0.0
        self.portrait_zoom = 1.0
        self._portrait_cache_key: tuple[str, int, int] | None = None
        self._portrait_cache_image: Image.Image | None = None
        self._background_cache: dict[tuple, Image.Image] = {}
        self._stone_cache: dict[tuple, Image.Image] = {}

    @staticmethod
    def _image_signature(path: Path) -> tuple[str, int, int]:
        try:
            stat = path.stat()
            return str(path.resolve()), stat.st_mtime_ns, stat.st_size
        except OSError:
            return str(path.absolute()), 0, 0

    def invalidate_path(self, path: Path) -> None:
        resolved = self._image_signature(path)[0]
        for key in list(self._stone_cache):
            if key[0][0] == resolved:
                self._stone_cache.pop(key, None)

    def _stone_image(self, path: Path, size: tuple[int, int]) -> Image.Image:
        signature = self._image_signature(path)
        key = (signature, size)
        cached = self._stone_cache.get(key)
        if cached is None:
            with Image.open(path) as source:
                cached = normalize_review_image(source.convert("RGBA"), size)
            stale = [item for item in self._stone_cache if item[0][0] == signature[0] and item != key]
            for item in stale:
                self._stone_cache.pop(item, None)
            self._stone_cache[key] = cached
            while len(self._stone_cache) > 12:
                self._stone_cache.pop(next(iter(self._stone_cache)))
        return cached

    def set_portrait(self, path: Path) -> None:
        self.portrait_path = path
        self._portrait_cache_key = None
        self._portrait_cache_image = None

    def set_portrait_transform(self, offset_x: float, offset_y: float, zoom: float) -> None:
        self.portrait_offset_x = max(-1.0, min(1.0, float(offset_x)))
        self.portrait_offset_y = max(-1.0, min(1.0, float(offset_y)))
        self.portrait_zoom = max(1.0, min(3.0, float(zoom)))

    def portrait_image(self) -> Image.Image | None:
        path = self.portrait_path
        if path is None or not path.exists():
            return None
        stat = path.stat()
        key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        if self._portrait_cache_key != key or self._portrait_cache_image is None:
            with Image.open(path) as raw:
                self._portrait_cache_image = raw.convert("RGBA")
            self._portrait_cache_key = key
        return self._portrait_cache_image.copy()

    def render(
        self,
        gravestone_path: Path,
        *,
        view: str,
        composite: bool,
        show_portrait_overlay: bool,
        show_text_overlay: bool,
        show_diagnostic_overlay: bool,
        name: str,
        class_name: str,
        death_date: str,
        analysis: OpeningAnalysis | None,
        opening_check: bool = False,
        text_safe_area: tuple[int, int, int, int] | None = None,
    ) -> Image.Image:
        w, h = self.geometry.canvas_size
        base = self._checkerboard((w, h), 32) if opening_check else self._background(w, h, view)
        if composite or opening_check:
            portrait_layer = self._portrait_layer(w, h, analysis)
            base.alpha_composite(portrait_layer)
        stone = self._stone_image(gravestone_path, (w, h))
        base.alpha_composite(stone)
        if composite:
            self._draw_text(base, name, class_name, death_date, text_safe_area)
        if opening_check:
            self._draw_opening_check(base, stone, analysis)
        if show_portrait_overlay:
            self._draw_portrait_overlay(base, analysis)
        if show_text_overlay:
            ImageDraw.Draw(base).rectangle(text_safe_area or self.geometry.text_safe_area, outline=(70, 220, 255, 255), width=5)
        if show_diagnostic_overlay and analysis:
            self._draw_diagnostics(base, analysis)
        return base

    def _draw_opening_check(
        self, image: Image.Image, stone: Image.Image, analysis: OpeningAnalysis | None
    ) -> None:
        metrics = opening_transparency_metrics(stone, analysis)
        edge = metrics.expected_mask.filter(ImageFilter.FIND_EDGES)
        green = Image.new("RGBA", image.size, (35, 255, 95, 0))
        green.putalpha(edge.point(lambda value: 230 if value else 0))
        image.alpha_composite(green)
        magenta = Image.new("RGBA", image.size, (255, 0, 190, 0))
        magenta.putalpha(metrics.problem_mask.point(lambda value: 190 if value else 0))
        image.alpha_composite(magenta)

    def _draw_portrait_overlay(self, image: Image.Image, analysis: OpeningAnalysis | None) -> None:
        """Show the actual render mask; the old ellipse is fallback only."""
        if analysis is not None and analysis.mask is not None and analysis.bbox is not None:
            edge = analysis.mask.filter(ImageFilter.FIND_EDGES)
            alpha = edge.point(lambda p: 230 if p > 0 else 0)
            overlay = Image.new("RGBA", image.size, (255, 210, 60, 0))
            overlay.putalpha(alpha)
            image.alpha_composite(overlay)
            return
        ImageDraw.Draw(image).ellipse(self.geometry.portrait_bbox, outline=(255, 210, 60, 255), width=5)

    def _draw_diagnostics(self, image: Image.Image, analysis: OpeningAnalysis) -> None:
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.ellipse(self.geometry.portrait_bbox, outline=(255, 220, 40, 200), width=4)
        if analysis.mask is not None:
            edge = analysis.mask.filter(ImageFilter.FIND_EDGES)
            green_alpha = edge.point(lambda p: 190 if p > 0 else 0)
            green = Image.new("RGBA", image.size, (40, 255, 100, 0))
            green.putalpha(green_alpha)
            overlay.alpha_composite(green)
        if analysis.core_problem_mask is not None:
            red_alpha = analysis.core_problem_mask.point(lambda p: 180 if p > 0 else 0)
            red = Image.new("RGBA", image.size, (255, 30, 30, 0))
            red.putalpha(red_alpha)
            overlay.alpha_composite(red)
        image.alpha_composite(overlay)

    def _background(self, w: int, h: int, view: str) -> Image.Image:
        signature = self._image_signature(self.background_path) if view == "Graveyard" else None
        key = (view, w, h, signature)
        cached = self._background_cache.get(key)
        if cached is not None:
            return cached.copy()
        if view == "Graveyard" and self.background_path.exists():
            with Image.open(self.background_path) as source:
                result = self._cover(source.convert("RGBA"), (w, h))
        elif view == "Transparenz":
            result = self._checkerboard((w, h), 32)
        else:
            result = Image.new("RGBA", (w, h), (28, 28, 32, 255))
        self._background_cache[key] = result
        while len(self._background_cache) > 8:
            self._background_cache.pop(next(iter(self._background_cache)))
        return result.copy()

    @staticmethod
    def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
        tw, th = size
        ratio = max(tw / image.width, th / image.height)
        nw, nh = math.ceil(image.width * ratio), math.ceil(image.height * ratio)
        image = image.resize((nw, nh), Image.Resampling.LANCZOS)
        left = (nw - tw) // 2
        top = (nh - th) // 2
        return image.crop((left, top, left + tw, top + th))

    @staticmethod
    def _checkerboard(size: tuple[int, int], cell: int) -> Image.Image:
        w, h = size
        img = Image.new("RGBA", size, (205, 205, 205, 255))
        d = ImageDraw.Draw(img)
        c1 = (205, 205, 205, 255)
        c2 = (155, 155, 155, 255)
        for y in range(0, h, cell):
            for x in range(0, w, cell):
                d.rectangle((x, y, x + cell - 1, y + cell - 1), fill=c1 if ((x // cell + y // cell) % 2 == 0) else c2)
        return img

    def _portrait_layer(self, w: int, h: int, analysis: OpeningAnalysis | None) -> Image.Image:
        """Render with the exact detector mask and cover-fit used by the checker."""
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        portrait = self.portrait_image()
        if portrait is None:
            return layer

        if analysis is not None and analysis.bbox is not None and analysis.mask is not None:
            x1, y1, x2, y2 = analysis.bbox
            full_mask = analysis.mask
        else:
            x1, y1, x2, y2 = self.geometry.portrait_bbox
            full_mask = Image.new("L", (w, h), 0)
            ImageDraw.Draw(full_mask).ellipse((x1, y1, x2, y2), fill=255)

        pw, ph = max(1, x2 - x1), max(1, y2 - y1)
        fitted = fit_shared_gravestone_portrait(
            portrait, (pw, ph), self.portrait_offset_x, self.portrait_offset_y, self.portrait_zoom
        )
        mask = full_mask.crop((x1, y1, x2, y2))
        if mask.size != (pw, ph):
            mask = mask.resize((pw, ph), Image.Resampling.LANCZOS)
        layer.paste(fitted, (x1, y1), mask)
        return layer

    def _font(self, size: int, bold: bool = False) -> ImageFont.ImageFont:
        candidates = ["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf"]
        for name in candidates:
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _draw_text(self, image: Image.Image, name: str, class_name: str, death_date: str,
                   text_safe_area: tuple[int, int, int, int] | None = None) -> None:
        x1, y1, x2, y2 = text_safe_area or self.geometry.text_safe_area
        draw = ImageDraw.Draw(image)
        name_font = self._font(40, bold=True)
        meta_font = self._font(28)
        small_font = self._font(26)
        center = (x1 + x2) // 2
        current_y = y1 + 16
        for text, font, fill in (
            (name, name_font, (235, 228, 208, 255)),
            (class_name, meta_font, (205, 198, 180, 255)),
            (f"{tr('graveyard.death_date_label')}: {death_date}", small_font, (190, 182, 168, 255)),
        ):
            wrapped = self._wrap_text(text, font, x2 - x1 - 30)
            for line in wrapped:
                bbox = draw.textbbox((0, 0), line, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text((center - tw / 2, current_y), line, font=font, fill=fill)
                current_y += th + 8
            current_y += 6

    def _wrap_text(self, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
        dummy = Image.new("RGBA", (10, 10))
        draw = ImageDraw.Draw(dummy)
        words = text.split()
        if not words:
            return [text]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines




def open_in_file_manager(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])

class ReviewApp:
    def __init__(self, root: tk.Misc, project_root: Path, tool_dir: Path):
        self.root = root
        self.project_root = project_root
        self.tool_dir = tool_dir
        self.geometry = GeometryConfig.load(tool_dir / "master_geometry.json")
        self.validator = AssetValidator(self.geometry)
        self.renderer = GraveyardRenderer(self.geometry, tool_dir, project_root)
        self.workspace = ensure_workspace(project_root)
        self.graveyard_dir = self.workspace.graveyard
        self.candidate_dir = self.workspace.candidates
        self.accepted_dir = self.workspace.accepted
        self.approved_dir = self.workspace.approved
        self.approved_compressed_dir = self.workspace.approved_compressed
        self.rejected_dir = self.workspace.rejected
        self.log_dir = self.workspace.logs
        self.latest_log_path = self.log_dir / "gravestone_review_latest.log"

        # self.candidates contains the currently selected review queue.  The
        # attribute name is kept for backwards compatibility with the embedded
        # Grabber integration, which calls reload_candidates().
        self.candidates: list[Path] = []
        self.index = 0
        self.queue_var = tk.StringVar(value="Kandidaten")
        self.current_image: Image.Image | None = None
        self.current_checks: list[CheckResult] = []
        self.current_analysis: OpeningAnalysis | None = None
        self.current_text_safe_area: tuple[int, int, int, int] | None = None
        self.photo: ImageTk.PhotoImage | None = None

        self.browser_view_var = tk.StringVar(value="Einzelansicht")
        self.view_var = tk.StringVar(value="Graveyard")
        self.mode_var = tk.StringVar(value="Zusammengesetzt")
        self.zoom_var = tk.StringVar(value=tr("review.fit"))
        self.name_var = tk.StringVar(value="Waltørdin")
        self.class_var = tk.StringVar(value="Warrior")
        self.date_var = tk.StringVar(value="2026-09-12")
        self.demo_offset_x_var = tk.DoubleVar(value=0.0)
        self.demo_offset_y_var = tk.DoubleVar(value=0.0)
        self.demo_zoom_var = tk.DoubleVar(value=1.0)
        self.demo_preset_status_var = tk.StringVar(value=tr("review.no_preset"))
        self.opening_diagnostics_var = tk.StringVar(value=tr("review.opening_unknown"))
        self.category_var = tk.StringVar(value="")
        self.portrait_overlay_var = tk.BooleanVar(value=False)
        self.text_overlay_var = tk.BooleanVar(value=False)
        self.diagnostic_overlay_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value=tr("review.ready"))
        self.progress_text_var = tk.StringVar(value=tr("review.ready"))
        self.progress_value_var = tk.DoubleVar(value=0.0)
        self.log_path_var = tk.StringVar(value=str(self.latest_log_path))
        self.count_candidates_var = tk.StringVar(value=tr("review.queue_count", label=tr("review.queue_candidates"), count=0))
        self.count_accepted_var = tk.StringVar(value=tr("review.queue_count", label=tr("review.queue_accepted"), count=0))
        self.count_approved_var = tk.StringVar(value=tr("review.queue_count", label=tr("review.queue_approved"), count=0))
        self.count_rejected_var = tk.StringVar(value=tr("review.queue_count", label=tr("review.queue_rejected"), count=0))
        self.count_productive_var = tk.StringVar(value=tr("review.queue_count", label=tr("review.queue_productive"), count=0))
        self._productive_manifest_key: tuple[int | None, int | None] | None = None
        self._productive_paths_cache: list[Path] = []
        self._productive_metadata_cache: dict[str, dict] = {}
        self._preview_after_id: str | None = None
        self._single_resize_after_id: str | None = None
        self._preview_scale = 1.0
        self._demo_drag_start: tuple[int, int] | None = None
        self._demo_drag_offsets: tuple[float, float] | None = None
        # Background validation is read-only and never touches Tk.  The result is
        # consumed by the main thread on the next navigation step.
        self._prefetch_lock = threading.Lock()
        self._prefetch_signature: tuple[str, int, int] | None = None
        self._prefetch_result: tuple[list[CheckResult], OpeningAnalysis | None] | None = None
        self._prefetch_running_signature: tuple[str, int, int] | None = None
        self._prefetch_after_id: str | None = None
        # The queue selector is intentionally always visible.  A previous
        # combobox hid the other review states until opened and made it easy
        # to miss that accepted/rejected assets can be reviewed again.
        self.queue_button_text_vars = {
            queue: tk.StringVar(value=tr("review.queue_button", label=tr(key), count=0))
            for queue, key in QUEUE_TRANSLATION_KEYS.items()
        }

        self._build_ui()
        self.reload_candidates()

    def _build_ui(self) -> None:
        # Standalone uses a real window; the Grabber integration passes a Frame.
        # Keep one UI implementation for both modes instead of duplicating review logic.
        if isinstance(self.root, (tk.Tk, tk.Toplevel)):
            self.root.title(APP_TITLE)
            self.root.geometry("1380x930")
            self.root.minsize(1050, 720)

        toolbar = ttk.Frame(self.root, padding=(8, 8))
        toolbar.pack(fill="x")
        self.prev_button = ttk.Button(toolbar, text=tr("review.previous"), command=self.previous)
        self.prev_button.pack(side="left")
        self.next_button = ttk.Button(toolbar, text=tr("review.next"), command=self.next)
        self.next_button.pack(side="left", padx=(6, 16))
        self.counter_label = ttk.Label(toolbar, text=tr("review.candidate_counter", current=0, total=0))
        self.counter_label.pack(side="left")
        ttk.Label(toolbar, text=tr("review.view")).pack(side="left", padx=(18, 6))
        self.queue_buttons: dict[str, ttk.Radiobutton] = {}
        for queue_name in ("Kandidaten", "Akzeptiert", "Abgelehnt", "Freigegeben", "Produktiv"):
            button = ttk.Radiobutton(
                toolbar,
                textvariable=self.queue_button_text_vars[queue_name],
                value=queue_name,
                variable=self.queue_var,
                command=self._switch_queue,
                style="Toolbutton",
            )
            button.pack(side="left", padx=(0, 4))
            self.queue_buttons[queue_name] = button
        ttk.Button(toolbar, text=tr("review.reload"), command=self.reload_candidates).pack(side="right")
        ttk.Button(toolbar, text=tr("review.open_current_folder"), command=self.open_current_folder).pack(side="right", padx=(0, 8))
        ttk.Button(toolbar, text=tr("review.open_current_log"), command=self.open_latest_log).pack(side="right", padx=(0, 8))
        ttk.Button(toolbar, text=tr("review.open_log_folder"), command=self.open_log_folder).pack(side="right", padx=(0, 8))

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        right = ttk.Frame(body, padding=10)
        body.add(left, weight=4)
        body.add(right, weight=2)

        viewbar = ttk.Frame(left, padding=(8, 2, 8, 6))
        viewbar.pack(fill="x")
        ttk.Label(viewbar, text=tr("review.display")).pack(side="left", padx=(0, 4))
        self.browser_view_buttons: dict[str, ttk.Radiobutton] = {}
        for display_name, label_key in BROWSER_VIEW_TRANSLATION_KEYS.items():
            button = ttk.Radiobutton(
                viewbar,
                text=tr(label_key),
                value=display_name,
                variable=self.browser_view_var,
                command=self._switch_browser_view,
                style="Toolbutton",
            )
            button.pack(side="left", padx=(0, 4))
            self.browser_view_buttons[display_name] = button
        ttk.Separator(viewbar, orient="vertical").pack(side="left", fill="y", padx=8)
        for text, label_key in VIEW_TRANSLATION_KEYS.items():
            ttk.Radiobutton(viewbar, text=tr(label_key), value=text, variable=self.view_var, command=self.refresh_preview).pack(side="left", padx=(0, 8))
        ttk.Separator(viewbar, orient="vertical").pack(side="left", fill="y", padx=8)
        self.mode_buttons: dict[str, ttk.Radiobutton] = {}
        for text, label_key in MODE_TRANSLATION_KEYS.items():
            button = ttk.Radiobutton(
                viewbar, text=tr(label_key), value=text, variable=self.mode_var,
                command=self.refresh_preview,
            )
            button.pack(side="left", padx=(0, 8))
            self.mode_buttons[text] = button
        ttk.Separator(viewbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(viewbar, text=tr("review.zoom")).pack(side="left")
        zoom = ttk.Combobox(viewbar, textvariable=self.zoom_var, values=[tr("review.fit"), "50%", "100%", "200%", "400%"], width=7, state="readonly")
        zoom.pack(side="left", padx=(4, 0))
        zoom.bind("<<ComboboxSelected>>", lambda _e: self.refresh_preview())

        self.browser_container = ttk.Frame(left)
        self.browser_container.pack(fill="both", expand=True)

        self.single_view_frame = ttk.Frame(self.browser_container)
        self.canvas = tk.Canvas(self.single_view_frame, background="#161619", highlightthickness=0)
        xscroll = ttk.Scrollbar(self.single_view_frame, orient="horizontal", command=self.canvas.xview)
        yscroll = ttk.Scrollbar(self.single_view_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.single_view_frame.rowconfigure(0, weight=1)
        self.single_view_frame.columnconfigure(0, weight=1)
        self.canvas.bind("<Configure>", self._on_single_canvas_configure)
        self.canvas.bind("<ButtonPress-1>", self._demo_drag_press)
        self.canvas.bind("<B1-Motion>", self._demo_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._demo_drag_release)

        self.gallery_view_frame = ttk.Frame(self.browser_container)
        self.gallery_canvas = tk.Canvas(self.gallery_view_frame, background="#161619", highlightthickness=0)
        self.gallery_scrollbar = ttk.Scrollbar(self.gallery_view_frame, orient="vertical", command=self.gallery_canvas.yview)
        self.gallery_canvas.configure(yscrollcommand=self.gallery_scrollbar.set)
        self.gallery_canvas.grid(row=0, column=0, sticky="nsew")
        self.gallery_scrollbar.grid(row=0, column=1, sticky="ns")
        self.gallery_view_frame.rowconfigure(0, weight=1)
        self.gallery_view_frame.columnconfigure(0, weight=1)
        self.gallery_inner = ttk.Frame(self.gallery_canvas, padding=8)
        self.gallery_window = self.gallery_canvas.create_window((0, 0), window=self.gallery_inner, anchor="nw")
        self.gallery_inner.bind(
            "<Configure>",
            lambda _e: self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all")),
        )
        self.gallery_canvas.bind(
            "<Configure>",
            self._on_gallery_canvas_configure,
        )
        self.gallery_photos: list[ImageTk.PhotoImage] = []
        self.gallery_item_buttons: list[ttk.Button] = []
        # Keep thumbnails and lightweight image metadata in memory.  The key
        # includes the resolved path, nanosecond mtime and file size so an
        # unchanged PNG is not decoded/scaled again when the gallery is opened
        # repeatedly, while modified files automatically receive a fresh entry.
        self._gallery_thumbnail_cache: dict[tuple, ImageTk.PhotoImage] = {}
        self._image_metadata_cache: dict[tuple, tuple[str, str]] = {}
        self._gallery_render_key: tuple | None = None
        self._gallery_reflow_after_id: str | None = None

        self.list_view_frame = ttk.Frame(self.browser_container)
        self.list_tree = ttk.Treeview(
            self.list_view_frame,
            columns=("name", "dimensions", "size"),
            show="headings",
            selectmode="browse",
        )
        self.list_tree.heading("name", text=tr("review.file"))
        self.list_tree.heading("dimensions", text=tr("review.dimensions"))
        self.list_tree.heading("size", text=tr("review.size"))
        self.list_tree.column("name", width=430, minwidth=180, anchor="w")
        self.list_tree.column("dimensions", width=120, minwidth=90, anchor="center")
        self.list_tree.column("size", width=100, minwidth=80, anchor="e")
        list_scroll = ttk.Scrollbar(self.list_view_frame, orient="vertical", command=self.list_tree.yview)
        self.list_tree.configure(yscrollcommand=list_scroll.set)
        self.list_tree.grid(row=0, column=0, sticky="nsew")
        list_scroll.grid(row=0, column=1, sticky="ns")
        self.list_view_frame.rowconfigure(0, weight=1)
        self.list_view_frame.columnconfigure(0, weight=1)
        self.list_tree.bind("<ButtonRelease-1>", self._on_list_click)
        self.list_tree.bind("<Return>", self._on_list_activate)

        self._show_browser_view()

        self.filebox = ttk.LabelFrame(right, text=tr("review.candidate"), padding=8)
        self.filebox.pack(fill="x")
        self.filename_label = ttk.Label(self.filebox, text="–", wraplength=360)
        self.filename_label.pack(anchor="w")
        ttk.Label(self.filebox, text=tr("review.project", path=self.project_root), wraplength=360).pack(anchor="w", pady=(6, 0))
        ttk.Label(self.filebox, text=tr("review.log"), wraplength=360).pack(anchor="w", pady=(4, 0))
        ttk.Label(self.filebox, textvariable=self.log_path_var, wraplength=360).pack(anchor="w")
        queuebox = ttk.LabelFrame(right, text=tr("review.review_status"), padding=8)
        queuebox.pack(fill="x", pady=(10, 0))
        ttk.Label(queuebox, textvariable=self.count_candidates_var).pack(anchor="w")
        ttk.Label(queuebox, textvariable=self.count_accepted_var).pack(anchor="w")
        ttk.Label(queuebox, textvariable=self.count_rejected_var).pack(anchor="w")
        ttk.Label(queuebox, textvariable=self.count_approved_var).pack(anchor="w")
        ttk.Label(queuebox, textvariable=self.count_productive_var).pack(anchor="w")
        ttk.Label(
            queuebox,
            text=tr("review.accepted_help"),
            wraplength=340,
        ).pack(anchor="w", pady=(5, 0))

        testbox = ttk.LabelFrame(right, text=tr("review.preview_data"), padding=8)
        testbox.pack(fill="x", pady=(10, 0))
        self._labeled_entry(testbox, tr("common.name"), self.name_var)
        self._labeled_entry(testbox, tr("common.class"), self.class_var)
        self._labeled_entry(testbox, tr("graveyard.death_date_label"), self.date_var)
        buttons = ttk.Frame(testbox)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text=tr("review.long_name"), command=self.use_long_name).pack(side="left")
        ttk.Button(buttons, text=tr("review.change_portrait"), command=self.choose_portrait).pack(side="left", padx=6)
        ttk.Button(buttons, text=tr("review.reset_demo_portrait"), command=self._reset_demo_portrait).pack(side="left")
        demo_zoom = ttk.Frame(testbox)
        demo_zoom.pack(fill="x", pady=(6, 0))
        ttk.Label(demo_zoom, text=tr("review.demo_zoom")).pack(side="left")
        ttk.Scale(
            demo_zoom, from_=1.0, to=3.0, variable=self.demo_zoom_var,
            orient="horizontal", command=lambda _value: self._schedule_preview(),
        ).pack(side="left", fill="x", expand=True, padx=(6, 8))
        self.demo_transform_label = ttk.Label(demo_zoom, text="X 0.00 · Y 0.00 · 1.00×")
        self.demo_transform_label.pack(side="right")
        preset_row = ttk.Frame(testbox)
        preset_row.pack(fill="x", pady=(6, 0))
        self.save_preset_button = ttk.Button(
            preset_row,
            text=tr("review.save_preset"),
            command=self._save_demo_portrait_preset,
        )
        self.save_preset_button.pack(side="left")
        ttk.Label(
            preset_row, textvariable=self.demo_preset_status_var, wraplength=250,
        ).pack(side="left", padx=(8, 0))
        for var in (self.name_var, self.class_var, self.date_var):
            var.trace_add("write", lambda *_args: self.refresh_preview())

        overlaybox = ttk.LabelFrame(right, text=tr("review.debug_overlays"), padding=8)
        overlaybox.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(overlaybox, text=tr("review.master_portrait_mask"), variable=self.portrait_overlay_var, command=self.refresh_preview).pack(anchor="w")
        ttk.Checkbutton(overlaybox, text=tr("review.text_safe_area"), variable=self.text_overlay_var, command=self.refresh_preview).pack(anchor="w")
        ttk.Checkbutton(overlaybox, text=tr("review.diagnostic_overlay"), variable=self.diagnostic_overlay_var, command=self.refresh_preview).pack(anchor="w")
        ttk.Label(overlaybox, text=tr("review.diagnostic_help"), wraplength=340).pack(anchor="w", pady=(6, 0))
        ttk.Label(overlaybox, textvariable=self.opening_diagnostics_var, wraplength=360).pack(anchor="w", pady=(6, 0))
        self.alpha_editor_button = ttk.Button(
            overlaybox, text=tr("review.adjust_alpha"), command=self.open_alpha_editor,
        )
        self.alpha_editor_button.pack(fill="x", pady=(8, 0))

        self.actionbox = ttk.LabelFrame(right, text=tr("review.decision"), padding=8)
        self.actionbox.pack(fill="x", pady=(10, 0))
        self.accept_button = ttk.Button(self.actionbox, text=tr("review.accept"), command=self.accept)
        self.reject_button = ttk.Button(self.actionbox, text=tr("review.reject"), command=self.reject)
        self.remove_accepted_button = ttk.Button(self.actionbox, text=tr("review.remove"), command=self.remove_accepted)
        self.approve_button = ttk.Button(self.actionbox, text=tr("review.approve"), command=self.approve_current)
        self.approve_all_button = ttk.Button(self.actionbox, text=tr("review.approve_all"), command=self.approve_all)
        self.delete_rejected_button = ttk.Button(self.actionbox, text=tr("review.delete_png"), command=self.delete_current_rejected)
        self.readonly_action_label = ttk.Label(self.actionbox, text=tr("review.approved_readonly"))
        ttk.Label(self.actionbox, text=tr("review.category_label", label=tr("gravestone_category.label"))).pack(anchor="w")
        category_buttons_frame = ttk.Frame(self.actionbox)
        category_buttons_frame.pack(fill="x", pady=(4, 8))
        self.category_buttons: dict[str, tk.Button] = {}
        for category in GRAVESTONE_CATEGORIES:
            button = tk.Button(
                category_buttons_frame,
                text=gravestone_category_display(category),
                command=lambda value=category: self._category_changed(value),
                relief=tk.RAISED,
                bd=2,
                padx=4,
                pady=2,
                takefocus=True,
            )
            button.pack(side="left", fill="x", expand=True, padx=(0, 4))
            self.category_buttons[category] = button
        self._refresh_category_buttons()
        self._update_action_layout()

        checksbox = ttk.LabelFrame(right, text=tr("review.results"), padding=8)
        checksbox.pack(fill="both", expand=True, pady=(10, 0))
        self.check_text = tk.Text(checksbox, width=45, height=18, wrap="word", state="disabled")
        self.check_text.pack(fill="both", expand=True)

        statusbar = ttk.Frame(self.root, padding=(8, 6))
        statusbar.pack(fill="x")
        ttk.Label(statusbar, textvariable=self.status_var).pack(side="left")
        ttk.Label(statusbar, textvariable=self.progress_text_var).pack(side="right")
        progress_frame = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        progress_frame.pack(fill="x")
        self.progress = ttk.Progressbar(progress_frame, mode="determinate", maximum=100, variable=self.progress_value_var)
        self.progress.pack(fill="x")

    def _switch_queue(self) -> None:
        """Switch to a review queue from the always-visible status buttons."""
        self.index = 0
        self.reload_candidates()

    def _switch_browser_view(self) -> None:
        """Switch between single, gallery and list presentation without moving files."""
        self._show_browser_view()
        self.refresh_browser_view()
        self._update_action_states()

    @staticmethod
    def _is_gallery_view(value: str) -> bool:
        # "Abbildungsansicht" was the name used by the first browser prototype.
        # Accept it internally for compatibility with older tests/runtime state,
        # while the visible UI now uses the shorter label "Galerie".
        return value in {"Galerie", "Abbildungsansicht"}

    def _show_browser_view(self) -> None:
        for frame in (self.single_view_frame, self.gallery_view_frame, self.list_view_frame):
            frame.pack_forget()
        selected = self.browser_view_var.get()
        if self._is_gallery_view(selected):
            self.gallery_view_frame.pack(fill="both", expand=True)
        elif selected == "Listenansicht":
            self.list_view_frame.pack(fill="both", expand=True)
        else:
            self.single_view_frame.pack(fill="both", expand=True)

    def refresh_browser_view(self) -> None:
        selected = self.browser_view_var.get()
        if self._is_gallery_view(selected):
            self._refresh_gallery()
        elif selected == "Listenansicht":
            self._refresh_list()
        else:
            self.refresh_preview()

    def _on_single_canvas_configure(self, _event: tk.Event) -> None:
        if self.zoom_var.get() != tr("review.fit") or self.browser_view_var.get() != "Einzelansicht":
            return
        if self._single_resize_after_id is not None:
            try:
                self.root.after_cancel(self._single_resize_after_id)
            except (tk.TclError, ValueError):
                pass
        self._single_resize_after_id = self.root.after(60, self._finish_single_resize)

    def _finish_single_resize(self) -> None:
        self._single_resize_after_id = None
        if self.zoom_var.get() == tr("review.fit") and self.browser_view_var.get() == "Einzelansicht":
            self.refresh_preview()

    def _on_gallery_canvas_configure(self, event: tk.Event) -> None:
        """Keep the gallery window full-width and reflow only when needed.

        On the first switch to the gallery Tk may report a canvas width of 1 px
        until geometry management has completed.  The old implementation then
        fell back to 520 px and rendered only two columns.  A later visit used
        the real width, which explains the observed 2-column first render.
        """
        self.gallery_canvas.itemconfigure(self.gallery_window, width=max(1, event.width))
        if not self._is_gallery_view(self.browser_view_var.get()):
            return
        if self._gallery_reflow_after_id is not None:
            try:
                self.root.after_cancel(self._gallery_reflow_after_id)
            except (tk.TclError, ValueError):
                pass
        # Coalesce configure bursts caused by mapping/resizing.  Thumbnails are
        # cached, so a genuine column-count change only rebuilds lightweight UI.
        self._gallery_reflow_after_id = self.root.after(25, self._finish_gallery_reflow)

    def _finish_gallery_reflow(self) -> None:
        self._gallery_reflow_after_id = None
        if self._is_gallery_view(self.browser_view_var.get()):
            self._refresh_gallery()

    def _gallery_available_width(self) -> int:
        """Return a stable gallery width even during the first mapping cycle."""
        widths = []
        for widget in (self.gallery_canvas, self.gallery_view_frame, self.browser_container):
            try:
                widths.append(int(widget.winfo_width()))
            except (tk.TclError, ValueError):
                continue
        usable = max(widths, default=1)
        # A width <= 1 means Tk has not laid the widget out yet.  Give geometry
        # management one chance to settle, then read all relevant containers
        # again instead of inventing a narrow 520 px fallback.
        if usable <= 1:
            try:
                self.root.update_idletasks()
            except tk.TclError:
                pass
            widths = []
            for widget in (self.gallery_canvas, self.gallery_view_frame, self.browser_container):
                try:
                    widths.append(int(widget.winfo_width()))
                except (tk.TclError, ValueError):
                    continue
            usable = max(widths, default=1)
        return max(1, usable)

    def _gallery_column_count(self) -> int:
        width = self._gallery_available_width()
        # Keep the existing tile density: about 180 px are required per tile.
        # When the window is genuinely narrow, one column is better than forcing
        # two clipped columns.  Normal desktop widths still cap at six columns.
        return max(1, min(6, width // 180))

    @staticmethod
    def _human_file_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    @staticmethod
    def _image_signature(path: Path) -> tuple[str, int, int]:
        """Return the same kind of cheap file identity used by the Friedhof caches."""
        try:
            resolved = str(path.resolve())
        except OSError:
            resolved = str(path.absolute())
        try:
            stat = path.stat()
            return resolved, stat.st_mtime_ns, stat.st_size
        except OSError:
            return resolved, 0, 0

    @staticmethod
    def _trim_image_cache(cache: dict, limit: int) -> None:
        while len(cache) > limit:
            cache.pop(next(iter(cache)))

    def _invalidate_cached_path(self, path: Path) -> None:
        """Drop cached representations for a file that is moved/deleted by review actions."""
        resolved = self._image_signature(path)[0]
        for key in list(self._gallery_thumbnail_cache):
            signature = key[0]
            if signature and signature[0] == resolved:
                self._gallery_thumbnail_cache.pop(key, None)
        for key in list(self._image_metadata_cache):
            if key and key[0] == resolved:
                self._image_metadata_cache.pop(key, None)
        # The gallery tile set may still reference the old path even if the
        # thumbnail itself was never cached (for example after a failed load).
        self._gallery_render_key = None
        self.validator.invalidate(path)

    def _image_metadata(self, path: Path) -> tuple[str, str]:
        signature = self._image_signature(path)
        cached = self._image_metadata_cache.get(signature)
        if cached is not None:
            return cached
        try:
            with Image.open(path) as image:
                dimensions = f"{image.width} × {image.height}"
        except Exception:  # noqa: BLE001
            dimensions = tr("review.metadata_error")
        file_size = self._human_file_size(signature[2]) if signature[1] or signature[2] else "–"
        result = (dimensions, file_size)
        # Remove obsolete entries for an overwritten file before inserting the
        # new signature.  This keeps repeated edits from growing the cache.
        stale = [key for key in self._image_metadata_cache if key[0] == signature[0] and key != signature]
        for key in stale:
            self._image_metadata_cache.pop(key, None)
        self._image_metadata_cache[signature] = result
        self._trim_image_cache(self._image_metadata_cache, 1024)
        return result

    def _gallery_thumbnail(self, path: Path, size: tuple[int, int] = (145, 198)) -> ImageTk.PhotoImage:
        signature = self._image_signature(path)
        cache_key = (signature, size)
        cached = self._gallery_thumbnail_cache.get(cache_key)
        if cached is not None:
            return cached

        width, height = size
        background = Image.new("RGBA", size, (22, 22, 25, 255))
        try:
            with Image.open(path) as image:
                source = image.convert("RGBA")
                fitted = ImageOps.contain(source, (width - 10, height - 10), Image.Resampling.LANCZOS)
                background.alpha_composite(
                    fitted,
                    ((width - fitted.width) // 2, (height - fitted.height) // 2),
                )
        except Exception:  # noqa: BLE001
            draw = ImageDraw.Draw(background)
            draw.rectangle((8, 8, width - 9, height - 9), outline=(150, 75, 75, 255), width=2)
            draw.text((14, height // 2 - 8), tr("review.preview_error_short"), fill=(230, 205, 205, 255))
        photo = ImageTk.PhotoImage(background, master=self.root)

        stale = [
            key for key in self._gallery_thumbnail_cache
            if key[0][0] == signature[0] and key[0] != signature
        ]
        for key in stale:
            self._gallery_thumbnail_cache.pop(key, None)
        self._gallery_thumbnail_cache[cache_key] = photo
        self._trim_image_cache(self._gallery_thumbnail_cache, 384)
        return photo

    def _refresh_gallery(self) -> None:
        columns = self._gallery_column_count()
        render_key = (
            self.queue_var.get(),
            columns,
            tuple(self._image_signature(path) for path in self.candidates),
        )

        # The gallery frame itself survives a switch to list/single view.  If
        # neither files nor layout changed, leave all Tk widgets in place and
        # reuse the existing PhotoImages.  This makes reopening a gallery much
        # cheaper than destroying and rebuilding every tile.
        if render_key == self._gallery_render_key and self.gallery_inner.winfo_children():
            self.gallery_canvas.update_idletasks()
            self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all"))
            return

        for child in self.gallery_inner.winfo_children():
            child.destroy()
        self.gallery_photos.clear()
        self.gallery_item_buttons.clear()
        self._gallery_render_key = render_key
        if not self.candidates:
            ttk.Label(
                self.gallery_inner,
                text=tr("review.no_files", queue=tr(QUEUE_TRANSLATION_KEYS[self.queue_var.get()])),
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
            self.gallery_canvas.update_idletasks()
            self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all"))
            return

        for column in range(columns):
            self.gallery_inner.columnconfigure(column, weight=1, uniform="gallery")

        for idx, path in enumerate(self.candidates):
            row, column = divmod(idx, columns)
            tile = ttk.Frame(self.gallery_inner, padding=5, relief="solid", borderwidth=1)
            tile.grid(row=row, column=column, sticky="n", padx=5, pady=5)
            photo = self._gallery_thumbnail(path)
            self.gallery_photos.append(photo)
            button = ttk.Button(
                tile,
                image=photo,
                command=lambda item_index=idx: self._open_browser_index(item_index),
                takefocus=True,
            )
            button.pack()
            ttk.Label(tile, text=path.name, wraplength=155, justify="center").pack(fill="x", pady=(4, 0))
            self.gallery_item_buttons.append(button)
        self.gallery_canvas.update_idletasks()
        self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all"))

    def _refresh_list(self) -> None:
        for item in self.list_tree.get_children():
            self.list_tree.delete(item)
        for idx, path in enumerate(self.candidates):
            dimensions, file_size = self._image_metadata(path)
            self.list_tree.insert("", "end", iid=str(idx), values=(path.name, dimensions, file_size))
        self._sync_list_selection()

    def _sync_list_selection(self) -> None:
        iid = str(self.index)
        if self.candidates and self.list_tree.exists(iid):
            self.list_tree.selection_set(iid)
            self.list_tree.focus(iid)
            self.list_tree.see(iid)

    def _on_list_click(self, event: tk.Event) -> None:
        row = self.list_tree.identify_row(event.y)
        if not row:
            return
        try:
            index = int(row)
        except ValueError:
            return
        self._open_browser_index(index)

    def _on_list_activate(self, _event: tk.Event) -> None:
        selection = self.list_tree.selection()
        if not selection:
            return
        try:
            index = int(selection[0])
        except ValueError:
            return
        self._open_browser_index(index)

    def _open_browser_index(self, index: int) -> None:
        if index < 0 or index >= len(self.candidates):
            return
        self.index = index
        self.browser_view_var.set("Einzelansicht")
        self._show_browser_view()
        self.load_current()

    def _update_action_layout(self) -> None:
        for child in (
            self.accept_button,
            self.reject_button,
            self.remove_accepted_button,
            self.approve_button,
            self.approve_all_button,
            self.delete_rejected_button,
            self.readonly_action_label,
        ):
            child.pack_forget()

        queue = self.queue_var.get()
        if queue == "Kandidaten":
            self.accept_button.pack(side="left", fill="x", expand=True)
            self.reject_button.pack(side="left", fill="x", expand=True, padx=(8, 0))
        elif queue == "Akzeptiert":
            self.remove_accepted_button.pack(side="left", fill="x", expand=True)
            self.approve_button.pack(side="left", fill="x", expand=True, padx=(8, 0))
            self.approve_all_button.pack(side="left", fill="x", expand=True, padx=(8, 0))
        elif queue == "Abgelehnt":
            self.delete_rejected_button.pack(side="left", fill="x", expand=True)
        else:
            self.readonly_action_label.configure(
                text=tr("review.productive_readonly") if queue == "Produktiv" else tr("review.approved_readonly")
            )
            self.readonly_action_label.pack(anchor="w")

    @staticmethod
    def _labeled_entry(parent: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=f"{label}:", width=10).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)

    def _productive_manifest_entries(self) -> tuple[list[Path], dict[str, dict]]:
        manifest_path = self.graveyard_dir / MANIFEST_FILENAME
        try:
            stat = manifest_path.stat()
            key = (int(stat.st_mtime_ns), int(stat.st_size))
        except OSError:
            key = (None, None)
        if key == self._productive_manifest_key:
            return list(self._productive_paths_cache), dict(self._productive_metadata_cache)

        paths: list[Path] = []
        metadata: dict[str, dict] = {}
        if not manifest_path.is_file():
            self._productive_manifest_key = key
            self._productive_paths_cache = paths
            self._productive_metadata_cache = metadata
            return [], {}
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            templates = payload.get("templates") if isinstance(payload, dict) else None
            if not isinstance(templates, list):
                raise ValueError("Produktives Grabstein-Manifest ist ungültig.")
            for raw in templates:
                if not isinstance(raw, dict):
                    continue
                filename = str(raw.get("filename") or "").strip()
                if not filename or Path(filename).name != filename:
                    continue
                path = self.graveyard_dir / filename
                if (
                    path.is_file()
                    and path.suffix.lower() in SUPPORTED_SUFFIXES
                    and path.name != "gravestone_placeholder.png"
                ):
                    paths.append(path)
                    metadata[path.name] = dict(raw)
        except (OSError, TypeError, ValueError) as exc:
            LOGGER.warning("PRODUCTIVE_MANIFEST_READ_ERROR | %s", exc)
            paths = []
            metadata = {}

        self._productive_manifest_key = key
        self._productive_paths_cache = paths
        self._productive_metadata_cache = metadata
        return list(paths), dict(metadata)

    def _productive_metadata(self, path: Path) -> dict:
        _paths, metadata = self._productive_manifest_entries()
        return metadata.get(Path(path).name, {})

    @staticmethod
    def _bounded_manifest_float(value: object, minimum: float, maximum: float, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, number))

    def _productive_review_metadata(
        self, path: Path,
    ) -> tuple[str | None, tuple[float, float, float] | None, tuple[int, int, int, int] | None]:
        raw = self._productive_metadata(path)
        category = normalize_gravestone_category(raw.get(GRAVESTONE_CATEGORY_FIELD))
        preset = None
        if all(field in raw for field in (
            GRAVESTONE_DEFAULT_OFFSET_X_FIELD,
            GRAVESTONE_DEFAULT_OFFSET_Y_FIELD,
            GRAVESTONE_DEFAULT_ZOOM_FIELD,
        )):
            preset = (
                self._bounded_manifest_float(raw[GRAVESTONE_DEFAULT_OFFSET_X_FIELD], -1.0, 1.0, 0.0),
                self._bounded_manifest_float(raw[GRAVESTONE_DEFAULT_OFFSET_Y_FIELD], -1.0, 1.0, 0.0),
                self._bounded_manifest_float(raw[GRAVESTONE_DEFAULT_ZOOM_FIELD], 1.0, 3.0, 1.0),
            )
        safe_area = None
        raw_safe_area = raw.get(GRAVESTONE_DEFAULT_TEXT_SAFE_AREA_FIELD)
        if isinstance(raw_safe_area, (list, tuple)) and len(raw_safe_area) == 4:
            try:
                values = tuple(round(float(value)) for value in raw_safe_area)
            except (TypeError, ValueError):
                values = ()
            if len(values) == 4 and values[2] > values[0] and values[3] > values[1]:
                safe_area = values
        return category, preset, safe_area

    def current_path(self) -> Path | None:
        if not self.candidates:
            return None
        return self.candidates[self.index]

    def _current_queue_folder(self) -> Path:
        return {
            "Kandidaten": self.candidate_dir,
            "Akzeptiert": self.accepted_dir,
            "Abgelehnt": self.rejected_dir,
            "Freigegeben": self.approved_dir,
            "Produktiv": self.graveyard_dir,
        }.get(self.queue_var.get(), self.candidate_dir)

    def _list_current_queue(self) -> list[Path]:
        if self.queue_var.get() == "Produktiv":
            return self._productive_manifest_entries()[0]
        loader = {
            "Kandidaten": list_candidates,
            "Akzeptiert": list_accepted,
            "Abgelehnt": list_rejected,
            "Freigegeben": list_approved,
        }.get(self.queue_var.get(), list_candidates)
        return loader(self.workspace)

    def _queue_item_label(self) -> str:
        return {
            "Kandidaten": tr("review.candidate"),
            "Akzeptiert": tr("review.queue_accepted"),
            "Abgelehnt": tr("review.queue_rejected"),
            "Freigegeben": tr("review.queue_approved"),
            "Produktiv": tr("review.queue_productive"),
        }.get(self.queue_var.get(), tr("review.queue_file_label"))

    def _set_progress(self, value: float, text: str) -> None:
        self.progress_value_var.set(value)
        self.progress_text_var.set(_localize_progress_text(text))
        self.root.update_idletasks()
        flush_review_logs()

    def _category_changed(self, category: str | None = None) -> None:
        if self.queue_var.get() == "Produktiv":
            return
        if category is not None:
            self.category_var.set(category)
        selected = normalize_gravestone_category(self.category_var.get())
        if selected is None:
            return
        self.category_var.set(selected)
        self._refresh_category_buttons()
        path = self.current_path()
        if path is None:
            return
        try:
            save_gravestone_category(path, selected)
            self.status_var.set(tr("review.category_saved", label=tr("gravestone_category.label"), category=gravestone_category_display(selected)))
            self._update_action_states()
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("CATEGORY_SAVE_ERROR | file=%s", path)
            messagebox.showerror(tr("review.category_save_failed"), _localize_core_error(exc))

    def _refresh_category_buttons(self) -> None:
        selected = normalize_gravestone_category(self.category_var.get())
        for category, button in self.category_buttons.items():
            active = category == selected
            button.configure(
                relief=tk.SUNKEN if active else tk.RAISED,
                bg="#cfe3ff" if active else "#f0f0f0",
                activebackground="#cfe3ff",
            )

    def _action_widgets(self) -> list[ttk.Button]:
        return [
            self.prev_button,
            self.next_button,
            self.accept_button,
            self.reject_button,
            self.remove_accepted_button,
            self.approve_button,
            self.approve_all_button,
            self.delete_rejected_button,
            self.alpha_editor_button,
        ]

    def _set_busy(self, busy: bool) -> None:
        if busy:
            for widget in self._action_widgets():
                widget.state(["disabled"])
        else:
            self._update_action_states()
        self.root.update_idletasks()

    def _update_action_states(self) -> None:
        has_item = self.current_path() is not None
        blockers = [r for r in self.current_checks if r.critical and not r.ok]
        has_accepted = bool(list_accepted(self.workspace))
        single_view = self.browser_view_var.get() == "Einzelansicht"

        for widget in self._action_widgets():
            widget.state(["disabled"])
        if has_item and single_view:
            self.prev_button.state(["!disabled"])
            self.next_button.state(["!disabled"])

        queue = self.queue_var.get()
        if queue == "Kandidaten" and has_item and single_view:
            self.reject_button.state(["!disabled"])
            if not blockers:
                self.accept_button.state(["!disabled"])
        elif queue == "Akzeptiert":
            # Bulk approval is intentionally available from every presentation.
            # File-specific actions require the single view so there is no
            # ambiguity about which PNG is being changed.
            self.approve_all_button.state(["!disabled"] if has_accepted else ["disabled"])
            if has_item and single_view:
                self.remove_accepted_button.state(["!disabled"])
                if not blockers and normalize_gravestone_category(self.category_var.get()):
                    self.approve_button.state(["!disabled"])
        elif queue == "Abgelehnt" and has_item and single_view:
            self.delete_rejected_button.state(["!disabled"])
        if has_item and single_view and queue in {"Kandidaten", "Akzeptiert", "Abgelehnt"}:
            self.alpha_editor_button.state(["!disabled"])

        productive_readonly = queue == "Produktiv"
        for button in self.category_buttons.values():
            button.configure(state=tk.DISABLED if productive_readonly else tk.NORMAL)
        if productive_readonly or not has_item or not single_view:
            self.save_preset_button.state(["disabled"])
        else:
            self.save_preset_button.state(["!disabled"])

    def refresh_counts(self) -> None:
        counts = review_counts(self.workspace)
        productive_count = len(self._productive_manifest_entries()[0])
        count_values = {
            "Kandidaten": counts.candidates, "Akzeptiert": counts.accepted,
            "Abgelehnt": counts.rejected, "Freigegeben": counts.approved,
            "Produktiv": productive_count,
        }
        self.count_candidates_var.set(tr("review.queue_count", label=tr("review.queue_candidates"), count=counts.candidates))
        self.count_accepted_var.set(tr("review.queue_count", label=tr("review.queue_accepted"), count=counts.accepted))
        self.count_rejected_var.set(tr("review.queue_count", label=tr("review.queue_rejected"), count=counts.rejected))
        self.count_approved_var.set(tr("review.queue_count", label=tr("review.queue_approved"), count=counts.approved))
        self.count_productive_var.set(tr("review.queue_count", label=tr("review.queue_productive"), count=productive_count))
        for queue, count in count_values.items():
            self.queue_button_text_vars[queue].set(
                tr("review.queue_button", label=tr(QUEUE_TRANSLATION_KEYS[queue]), count=count)
            )

    def _consume_prefetch(self, path: Path) -> bool:
        signature = self._image_signature(path)
        with self._prefetch_lock:
            if self._prefetch_signature != signature or self._prefetch_result is None:
                return False
            results, analysis = self._prefetch_result
            self._prefetch_signature = None
            self._prefetch_result = None
        self.validator.seed_cache(path, results, analysis)
        return True

    def _schedule_next_validation_prefetch(self) -> None:
        if len(self.candidates) < 2:
            return
        # Do not compete with initial Tk layout/tests.  In the real application
        # the window becomes mapped and the delayed callback starts prefetching
        # during the user's reading/decision time.
        try:
            mapped = bool(self.root.winfo_ismapped())
        except tk.TclError:
            mapped = False
        if not mapped:
            if self._prefetch_after_id is None:
                try:
                    self._prefetch_after_id = self.root.after(250, self._finish_prefetch_delay)
                except tk.TclError:
                    pass
            return
        next_path = self.candidates[(self.index + 1) % len(self.candidates)]
        signature = self._image_signature(next_path)
        with self._prefetch_lock:
            if self._prefetch_signature == signature or self._prefetch_running_signature == signature:
                return
            self._prefetch_running_signature = signature

        def worker() -> None:
            try:
                validator = AssetValidator(self.geometry)
                results = validator.validate(next_path)
                analysis = validator.last_analysis
                if self._image_signature(next_path) != signature:
                    return
                with self._prefetch_lock:
                    self._prefetch_signature = signature
                    self._prefetch_result = (list(results), analysis)
            except Exception:  # noqa: BLE001
                LOGGER.debug("VALIDATE_PREFETCH_ERROR | path=%s", next_path, exc_info=True)
            finally:
                with self._prefetch_lock:
                    if self._prefetch_running_signature == signature:
                        self._prefetch_running_signature = None

        threading.Thread(target=worker, name="gravestone-validate-prefetch", daemon=True).start()

    def _finish_prefetch_delay(self) -> None:
        self._prefetch_after_id = None
        try:
            if self.root.winfo_ismapped():
                self._schedule_next_validation_prefetch()
        except tk.TclError:
            pass

    def _remove_current_from_queue(self) -> None:
        """Update the active queue after a move/delete without rescanning its folder."""
        if self.candidates:
            self.candidates.pop(self.index)
        if self.candidates:
            self.index = min(self.index, len(self.candidates) - 1)
        else:
            self.index = 0
        self.refresh_counts()
        self._update_action_layout()
        self._gallery_render_key = None
        self.load_current()
        if self.browser_view_var.get() != "Einzelansicht":
            self.refresh_browser_view()

    def reload_candidates(self) -> None:
        """Reload the currently selected queue (name retained for Grabber compatibility)."""
        current_name = self.current_path().name if self.current_path() else None
        self.candidates = self._list_current_queue()
        LOGGER.info(
            "QUEUE_RELOAD | queue=%s | count=%d | dir=%s",
            self.queue_var.get(), len(self.candidates), self._current_queue_folder(),
        )
        if current_name:
            matches = [i for i, p in enumerate(self.candidates) if p.name == current_name]
            self.index = matches[0] if matches else min(self.index, max(0, len(self.candidates) - 1))
        else:
            self.index = min(self.index, max(0, len(self.candidates) - 1))
        self.refresh_counts()
        self._update_action_layout()
        self.load_current()
        if self.browser_view_var.get() != "Einzelansicht":
            self.refresh_browser_view()

    def load_current(self) -> None:
        path = self.current_path()
        label = self._queue_item_label()
        self.filebox.configure(text=label)
        if path is None:
            self.counter_label.config(text=f"{label} 0 / 0")
            self.filename_label.config(text=tr("review.no_files", queue=tr(QUEUE_TRANSLATION_KEYS[self.queue_var.get()])))
            self.status_var.set(tr("review.folder_status", path=self._current_queue_folder()))
            self.current_checks = []
            self.current_analysis = None
            self.current_text_safe_area = None
            self.opening_diagnostics_var.set(tr("review.opening_unknown"))
            self.category_var.set("")
            self.demo_offset_x_var.set(0.0)
            self.demo_offset_y_var.set(0.0)
            self.demo_zoom_var.set(1.0)
            self.demo_preset_status_var.set(tr("review.no_preset"))
            self._refresh_category_buttons()
            self._write_checks([])
            self.canvas.delete("all")
            self._update_action_states()
            self._set_progress(0, tr("review.ready"))
            return

        self.counter_label.config(text=f"{label} {self.index + 1} / {len(self.candidates)}")
        self.filename_label.config(text=path.name)
        if self.queue_var.get() == "Produktiv":
            category, preset, safe_area = self._productive_review_metadata(path)
            self.category_var.set(category or "")
            self.current_text_safe_area = safe_area
        else:
            self.category_var.set(load_gravestone_category(path) or "")
            self.current_text_safe_area = load_gravestone_text_safe_area(path, self.geometry.canvas_size)
            preset = load_gravestone_portrait_preset(path)
        if preset is None:
            preset = (0.0, 0.0, 1.0)
            self.demo_preset_status_var.set(tr("review.no_preset"))
        else:
            self.demo_preset_status_var.set(
                tr("review.preset_status", x=preset[0], y=preset[1], zoom=preset[2])
            )
        self.demo_offset_x_var.set(preset[0])
        self.demo_offset_y_var.set(preset[1])
        self.demo_zoom_var.set(preset[2])
        self.renderer.set_portrait_transform(*preset)
        self.demo_transform_label.configure(
            text=f"X {preset[0]:.2f} · Y {preset[1]:.2f} · {preset[2]:.2f}×"
        )
        self._refresh_category_buttons()
        self._consume_prefetch(path)
        validation_started = time.perf_counter()
        self.current_checks = self.validator.validate(path)
        self.current_analysis = self.validator.last_analysis
        LOGGER.debug(
            "UI_VALIDATE | path=%s | elapsed_ms=%.1f | cache_hits=%d | cache_misses=%d",
            path, (time.perf_counter() - validation_started) * 1000.0,
            self.validator.cache_hits, self.validator.cache_misses,
        )
        self._update_opening_diagnostics(path)
        log_validation(path, self.current_checks, self.current_analysis)
        self._write_checks(self.current_checks)
        blockers = [r.label for r in self.current_checks if r.critical and not r.ok]
        warnings = [r.label for r in self.current_checks if not r.critical and not r.ok]
        queue = self.queue_var.get()
        if blockers:
            self.status_var.set(tr("review.technical_blocked", items=", ".join(_localize_check_label(x) for x in blockers)))
        elif queue == "Akzeptiert":
            self.status_var.set(tr("review.accepted_status"))
        elif queue == "Abgelehnt":
            self.status_var.set(tr("review.rejected_status"))
        elif queue == "Freigegeben":
            self.status_var.set(tr("review.approved_status"))
        elif queue == "Produktiv":
            self.status_var.set(tr("review.productive_status"))
        elif warnings:
            self.status_var.set(tr("review.technical_warnings", items=", ".join(_localize_check_label(x) for x in warnings)))
        else:
            self.status_var.set(tr("review.candidate_status"))
        self._update_action_states()
        self._set_progress(0, tr("review.ready"))
        if self.browser_view_var.get() == "Listenansicht":
            self._sync_list_selection()
        elif self.browser_view_var.get() == "Einzelansicht":
            self.refresh_preview()
        self._schedule_next_validation_prefetch()

    def _write_checks(self, checks: list[CheckResult]) -> None:
        self.check_text.config(state="normal")
        self.check_text.delete("1.0", "end")
        if not checks:
            self.check_text.insert("end", tr("review.no_check") + "\n")
        for result in checks:
            icon = "✓" if result.ok else ("✗" if result.critical else "!")
            severity = "" if result.ok else (f" [{tr('review.blocked_tag')}]" if result.critical else f" [{tr('review.warning_tag')}]")
            suffix = f" — {_localize_core_detail(result.detail)}" if result.detail else ""
            self.check_text.insert("end", f"{icon} {_localize_check_label(result.label)}{severity}{suffix}\n")
        self.check_text.config(state="disabled")

    def refresh_preview(self) -> None:
        path = self.current_path()
        if not path:
            return
        try:
            mode = self.mode_var.get()
            composite = mode == "Zusammengesetzt"
            self.renderer.set_portrait_transform(
                self.demo_offset_x_var.get(), self.demo_offset_y_var.get(), self.demo_zoom_var.get()
            )
            image = self.renderer.render(
                path,
                view=self.view_var.get(),
                composite=composite,
                show_portrait_overlay=self.portrait_overlay_var.get(),
                show_text_overlay=self.text_overlay_var.get(),
                show_diagnostic_overlay=self.diagnostic_overlay_var.get(),
                name=self.name_var.get(),
                class_name=self.class_var.get(),
                death_date=self.date_var.get(),
                analysis=self.current_analysis,
                opening_check=mode == "Öffnung prüfen",
                text_safe_area=self.current_text_safe_area,
            )
            self.current_image = image
            display = self._scaled_for_view(image)
            self.photo = ImageTk.PhotoImage(display)
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
            self.canvas.configure(scrollregion=(0, 0, display.width, display.height))
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("PREVIEW_ERROR | candidate=%s", path)
            self.status_var.set(tr("review.preview_error", error=_localize_core_error(exc)))
            flush_review_logs()

    def _scaled_for_view(self, image: Image.Image) -> Image.Image:
        zoom = self.zoom_var.get()
        if zoom == tr("review.fit"):
            cw = max(200, self.canvas.winfo_width() - 16)
            ch = max(200, self.canvas.winfo_height() - 16)
            ratio = min(cw / image.width, ch / image.height)
        else:
            ratio = int(zoom.rstrip("%")) / 100
        self._preview_scale = ratio
        nw = max(1, int(image.width * ratio))
        nh = max(1, int(image.height * ratio))
        resampling = Image.Resampling.NEAREST if ratio >= 2 else Image.Resampling.LANCZOS
        return image.resize((nw, nh), resampling)

    def _schedule_preview(self) -> None:
        """Coalesce fast demo zoom/drag events into one preview render."""
        if self._preview_after_id is not None:
            try:
                self.root.after_cancel(self._preview_after_id)
            except (tk.TclError, ValueError):
                pass
        self._preview_after_id = self.root.after(30, self._finish_scheduled_preview)

    def _finish_scheduled_preview(self) -> None:
        self._preview_after_id = None
        self.renderer.set_portrait_transform(
            self.demo_offset_x_var.get(), self.demo_offset_y_var.get(), self.demo_zoom_var.get()
        )
        self.demo_transform_label.configure(
            text=(
                f"X {self.demo_offset_x_var.get():.2f} · "
                f"Y {self.demo_offset_y_var.get():.2f} · {self.demo_zoom_var.get():.2f}×"
            )
        )
        if self.browser_view_var.get() == "Einzelansicht":
            self.refresh_preview()

    def _reset_demo_portrait(self) -> None:
        self.demo_offset_x_var.set(0.0)
        self.demo_offset_y_var.set(0.0)
        self.demo_zoom_var.set(1.0)
        self._schedule_preview()

    def _save_demo_portrait_preset(self) -> None:
        if self.queue_var.get() == "Produktiv":
            return
        path = self.current_path()
        if path is None:
            return
        try:
            values = (
                self.demo_offset_x_var.get(),
                self.demo_offset_y_var.get(),
                self.demo_zoom_var.get(),
            )
            save_gravestone_portrait_preset(path, *values)
            preset = load_gravestone_portrait_preset(path) or (0.0, 0.0, 1.0)
            self.demo_preset_status_var.set(
                tr("review.preset_status", x=preset[0], y=preset[1], zoom=preset[2])
            )
            self.status_var.set(tr("review.preset_saved", name=path.name))
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("PORTRAIT_PRESET_SAVE_ERROR | gravestone=%s", path)
            messagebox.showerror(tr("review.preset_save_failed"), _localize_core_error(exc))

    def _demo_drag_press(self, event: tk.Event) -> None:
        if self.mode_var.get() not in {"Zusammengesetzt", "Öffnung prüfen"}:
            return
        self._demo_drag_start = (int(self.canvas.canvasx(event.x)), int(self.canvas.canvasy(event.y)))
        self._demo_drag_offsets = (self.demo_offset_x_var.get(), self.demo_offset_y_var.get())

    def _demo_drag_motion(self, event: tk.Event) -> None:
        if self._demo_drag_start is None or self._demo_drag_offsets is None:
            return
        x = int(self.canvas.canvasx(event.x))
        y = int(self.canvas.canvasy(event.y))
        analysis = self.current_analysis
        bbox = analysis.bbox if analysis and analysis.bbox else self.geometry.portrait_bbox
        display_width = max(1.0, (bbox[2] - bbox[0]) * self._preview_scale)
        display_height = max(1.0, (bbox[3] - bbox[1]) * self._preview_scale)
        dx = (x - self._demo_drag_start[0]) * 2.0 / display_width
        dy = (y - self._demo_drag_start[1]) * 2.0 / display_height
        self.demo_offset_x_var.set(max(-1.0, min(1.0, self._demo_drag_offsets[0] + dx)))
        self.demo_offset_y_var.set(max(-1.0, min(1.0, self._demo_drag_offsets[1] + dy)))
        self._schedule_preview()

    def _demo_drag_release(self, _event: tk.Event) -> None:
        self._demo_drag_start = None
        self._demo_drag_offsets = None

    def _update_opening_diagnostics(self, path: Path) -> None:
        try:
            with Image.open(path) as source:
                metrics = opening_transparency_metrics(source.convert("RGBA"), self.current_analysis)
            detected = tr("review.opening_yes") if metrics.found else tr("review.opening_fallback")
            self.opening_diagnostics_var.set(tr(
                "review.opening_diagnostics",
                detected=detected,
                transparent=metrics.transparent_pixels,
                semi=metrics.semitransparent_pixels,
                opaque=metrics.nontransparent_pixels,
                ratio=f"{metrics.transparency_ratio:.1%}",
            ))
        except Exception as exc:  # noqa: BLE001
            self.opening_diagnostics_var.set(tr("review.opening_diagnostics_unavailable", error=exc))

    def open_alpha_editor(self) -> None:
        path = self.current_path()
        if path is None:
            return
        allowed = {self.candidate_dir.resolve(), self.accepted_dir.resolve(), self.rejected_dir.resolve()}
        if path.parent.resolve() not in allowed:
            messagebox.showerror(
                tr("review.adjust_alpha_title"),
                tr("review.readonly_alpha"),
            )
            return
        AlphaEditorDialog(
            self.root,
            path,
            self.geometry,
            self.renderer.portrait_image(),
            (
                self.demo_offset_x_var.get(),
                self.demo_offset_y_var.get(),
                self.demo_zoom_var.get(),
            ),
            self.log_dir / "alpha_backups",
            self._alpha_edit_saved,
        )

    def _alpha_edit_saved(self, path: Path) -> None:
        self._invalidate_cached_path(path)
        self.renderer.invalidate_path(path)
        self.current_text_safe_area = load_gravestone_text_safe_area(path, self.geometry.canvas_size)
        self.current_checks = self.validator.validate(path)
        self.current_analysis = self.validator.last_analysis
        log_validation(path, self.current_checks, self.current_analysis)
        self._write_checks(self.current_checks)
        self._update_opening_diagnostics(path)
        self._update_action_states()
        self.refresh_preview()

    def previous(self) -> None:
        if self.candidates:
            self.index = (self.index - 1) % len(self.candidates)
            self.load_current()

    def next(self) -> None:
        if self.candidates:
            self.index = (self.index + 1) % len(self.candidates)
            self.load_current()

    def open_current_folder(self) -> None:
        open_in_file_manager(self._current_queue_folder())

    def open_candidates_folder(self) -> None:
        # Kept for compatibility with older callers.
        open_in_file_manager(self.candidate_dir)

    def open_log_folder(self) -> None:
        open_in_file_manager(self.log_dir)

    def open_latest_log(self) -> None:
        if not self.latest_log_path.exists():
            self.latest_log_path.parent.mkdir(parents=True, exist_ok=True)
            self.latest_log_path.write_text("", encoding="utf-8")
        try:
            if os.name == "nt":
                os.startfile(str(self.latest_log_path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.latest_log_path)])
            else:
                subprocess.Popen(["xdg-open", str(self.latest_log_path)])
        except Exception:
            open_in_file_manager(self.log_dir)

    def choose_portrait(self) -> None:
        path = filedialog.askopenfilename(title=tr("review.portrait_select"), filetypes=[(tr("review.images"), "*.png;*.jpg;*.jpeg;*.webp")])
        if path:
            p = Path(path)
            self.renderer.set_portrait(p)
            LOGGER.info("PORTRAIT_CHANGE | portrait=%s", p)
            self.refresh_preview()

    def use_long_name(self) -> None:
        self.name_var.set(tr("review.long_name_value"))

    def accept(self) -> None:
        path = self.current_path()
        blockers = [r.label for r in self.current_checks if r.critical and not r.ok]
        if blockers:
            LOGGER.warning("ACCEPT_BLOCKED | candidate=%s | blockers=%s", path, blockers)
            flush_review_logs()
            messagebox.showerror(
                tr("review.not_possible"),
                tr("review.critical_candidate", blockers="\n".join(f"- {b}" for b in blockers)),
            )
            return
        if not path:
            return
        self._set_busy(True)
        try:
            LOGGER.info("ACCEPT | candidate=%s", path)
            result = accept_candidate(
                path, self.workspace, self.validator, progress=self._set_progress,
                category=normalize_gravestone_category(self.category_var.get()),
            )
            self.validator.transfer_cache(path, result.accepted_path)
            self._invalidate_cached_path(path)
            self.status_var.set(tr("review.accepted_file", name=result.accepted_path.name))
            flush_review_logs()
            self._remove_current_from_queue()
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("ACCEPT_ERROR | candidate=%s", path)
            flush_review_logs()
            messagebox.showerror(tr("review.accept_failed"), f"{_localize_core_error(exc)}\n\n{tr('review.details_log')}")
            self.status_var.set(f"{tr('review.accept_failed')}: {_localize_core_error(exc)}")
        finally:
            self._set_busy(False)
            self._set_progress(0, tr("review.ready"))

    def reject(self) -> None:
        path = self.current_path()
        if not path:
            return
        try:
            LOGGER.info("REJECT | candidate=%s", path)
            moved = reject_candidate(path, self.workspace)
            self.validator.transfer_cache(path, moved)
            self._invalidate_cached_path(path)
            self.status_var.set(tr("review.rejected_file", name=moved.name))
            flush_review_logs()
            self._remove_current_from_queue()
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("REJECT_ERROR | candidate=%s", path)
            flush_review_logs()
            messagebox.showerror(tr("review.reject_failed"), f"{_localize_core_error(exc)}\n\n{tr('review.details_log')}")

    def remove_accepted(self) -> None:
        path = self.current_path()
        if not path:
            return
        try:
            restored = restore_accepted(path, self.workspace)
            self.validator.transfer_cache(path, restored)
            self._invalidate_cached_path(path)
            self.status_var.set(tr("review.restored_file", name=restored.name))
            flush_review_logs()
            self._remove_current_from_queue()
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("ACCEPT_RESTORE_ERROR | accepted=%s", path)
            flush_review_logs()
            messagebox.showerror(tr("review.remove_failed"), f"{_localize_core_error(exc)}\n\n{tr('review.details_log')}")

    def approve_current(self) -> None:
        path = self.current_path()
        category = normalize_gravestone_category(self.category_var.get())
        if category is None:
            messagebox.showerror(
                tr("review.approve_not_possible"),
                tr("review.category_required", label=tr("gravestone_category.label")),
            )
            return
        blockers = [r.label for r in self.current_checks if r.critical and not r.ok]
        if blockers:
            messagebox.showerror(
                tr("review.approve_not_possible"),
                tr("review.critical_accepted", blockers="\n".join(f"- {b}" for b in blockers)),
            )
            return
        if not path:
            return
        self._set_busy(True)
        try:
            LOGGER.info("APPROVE | accepted=%s", path)
            result = approve_accepted(
                path, self.workspace, self.validator, progress=self._set_progress,
                category=category,
            )
            self.validator.transfer_cache(path, result.master_path)
            self._invalidate_cached_path(path)
            self.status_var.set(tr("review.approved_file", name=result.master_path.name))
            flush_review_logs()
            self._remove_current_from_queue()
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("APPROVE_ERROR | accepted=%s", path)
            flush_review_logs()
            messagebox.showerror(tr("review.approve_failed"), f"{_localize_core_error(exc)}\n\n{tr('review.details_log')}")
            self.status_var.set(f"{tr('review.approve_failed')}: {_localize_core_error(exc)}")
        finally:
            self._set_busy(False)
            self._set_progress(0, tr("review.ready"))

    def approve_all(self) -> None:
        accepted_files = list_accepted(self.workspace)
        if not accepted_files:
            return
        categories = {path: load_gravestone_category(path) for path in accepted_files}
        missing = [path.name for path, category in categories.items() if category is None]
        if missing:
            messagebox.showerror(
                tr("review.approve_not_possible"),
                tr("review.missing_categories", count=len(missing), label=tr("gravestone_category.label"), names="\n".join(f"- {name}" for name in missing)),
            )
            return
        if not messagebox.askyesno(
            tr("review.approve_all_title"),
            tr("review.approve_all_question", count=len(accepted_files)),
        ):
            return

        self._set_busy(True)
        approved_count = 0
        try:
            total = len(accepted_files)
            for idx, path in enumerate(accepted_files, start=1):
                base = (idx - 1) / total * 100
                span = 100 / total
                approve_accepted(
                    path,
                    self.workspace,
                    self.validator,
                    progress=lambda value, text, base=base, span=span, idx=idx, total=total: self._set_progress(
                        base + (value / 100) * span,
                        f"{idx}/{total}: {text}",
                    ),
                    category=categories[path],
                )
                self._invalidate_cached_path(path)
                approved_count += 1
            self.status_var.set(tr("review.approved_all", count=approved_count))
            flush_review_logs()
            self.reload_candidates()
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("APPROVE_ALL_ERROR | completed=%d", approved_count)
            flush_review_logs()
            self.reload_candidates()
            messagebox.showerror(
                tr("review.approve_all_aborted"),
                tr("review.approve_all_error", count=approved_count, error=exc),
            )
        finally:
            self._set_busy(False)
            self._set_progress(0, tr("review.ready"))

    def delete_current_rejected(self) -> None:
        path = self.current_path()
        if not path:
            return
        if not messagebox.askyesno(
            tr("review.delete_rejected_title"),
            tr("review.delete_rejected_question", name=path.name),
        ):
            return
        try:
            delete_rejected(path, self.workspace)
            self._invalidate_cached_path(path)
            self.status_var.set(tr("review.deleted_rejected", name=path.name))
            flush_review_logs()
            self._remove_current_from_queue()
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("REJECT_DELETE_ERROR | rejected=%s", path)
            flush_review_logs()
            messagebox.showerror(tr("review.delete_failed"), f"{_localize_core_error(exc)}\n\n{tr('review.details_log')}")


def generate_test_portrait(path: Path) -> None:
    size = 900
    img = Image.new("RGB", (size, size), (44, 61, 76))
    d = ImageDraw.Draw(img)
    d.ellipse((190, 105, 710, 625), fill=(176, 126, 92), outline=(54, 40, 32), width=20)
    d.polygon([(180, 230), (120, 70), (300, 175)], fill=(70, 55, 45))
    d.polygon([(720, 230), (780, 70), (600, 175)], fill=(70, 55, 45))
    d.ellipse((300, 290, 380, 360), fill=(235, 235, 225), outline=(25, 25, 25), width=8)
    d.ellipse((520, 290, 600, 360), fill=(235, 235, 225), outline=(25, 25, 25), width=8)
    d.ellipse((333, 315, 352, 342), fill=(30, 95, 135))
    d.ellipse((553, 315, 572, 342), fill=(30, 95, 135))
    d.polygon([(450, 365), (420, 470), (480, 470)], fill=(122, 79, 58))
    d.arc((320, 420, 590, 600), start=20, end=160, fill=(70, 35, 30), width=16)
    d.rounded_rectangle((170, 610, 730, 900), radius=80, fill=(72, 82, 97), outline=(34, 40, 48), width=18)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)



def self_test(tool_dir: Path) -> int:
    return run_core_self_test(tool_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--project-root", help="Guildchecker-Projektstamm")
    parser.add_argument("--self-test", action="store_true", help="Headless Self-Test ausführen")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tool_dir = Path(__file__).resolve().parent
    test_portrait = tool_dir / "reference" / "test_portrait.png"
    if not test_portrait.exists():
        generate_test_portrait(test_portrait)
    if args.self_test:
        return self_test(tool_dir)

    project_root = locate_project_root(args.project_root, tool_dir)
    workspace = ensure_workspace(project_root)
    latest_log, session_log = setup_review_logging(workspace.logs)
    LOGGER.info("APP_START | title=%s", APP_TITLE)
    LOGGER.info("PATHS | project_root=%s | graveyard=%s | tool_dir=%s", project_root, workspace.graveyard, tool_dir)
    if workspace.legacy_detected:
        LOGGER.warning(
            "LEGACY_PATH_DETECTED | old=%s | new_review_workspace=%s | legacy_not_modified=True",
            workspace.legacy_graveyard,
            workspace.graveyard,
        )
    LOGGER.info("RUNTIME | executable=%s", sys.executable)
    LOGGER.info("RUNTIME | python=%s", sys.version.replace("\n", " "))
    LOGGER.info("RUNTIME | platform=%s", platform.platform())
    LOGGER.info("RUNTIME | pillow=%s", PILLOW_VERSION)
    LOGGER.info("LOG_FILES | latest=%s | session=%s", latest_log, session_log)
    flush_review_logs()

    root = tk.Tk()

    def report_callback_exception(exc_type, exc_value, exc_traceback) -> None:
        LOGGER.error("TK_CALLBACK_EXCEPTION", exc_info=(exc_type, exc_value, exc_traceback))
        flush_review_logs()
        try:
            messagebox.showerror(
                tr("review.unexpected_error"),
                f"{exc_type.__name__}: {exc_value}\n\n{tr('review.details_log')}",
            )
        except Exception:
            pass

    root.report_callback_exception = report_callback_exception
    ReviewApp(root, project_root, tool_dir)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
