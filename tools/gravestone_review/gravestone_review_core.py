from __future__ import annotations

import json
import logging
import math
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps


# The review tool and the checker intentionally share the exact same portrait
# opening detector. Standalone execution starts inside tools/gravestone_review,
# so make the suite root importable before loading the shared app helper.
_PROJECT_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_FOR_IMPORT))
try:
    from app.gravestone_portrait import GRAVESTONE_RENDER_ANALYSIS_SIZE, detect_portrait_opening
except ImportError:
    import importlib.util

    _portrait_spec = importlib.util.spec_from_file_location(
        "guild_suite_gravestone_portrait_review",
        _PROJECT_ROOT_FOR_IMPORT / "app" / "gravestone_portrait.py",
    )
    _portrait_module = importlib.util.module_from_spec(_portrait_spec)
    sys.modules.setdefault(_portrait_spec.name, _portrait_module)
    _portrait_spec.loader.exec_module(_portrait_module)
    GRAVESTONE_RENDER_ANALYSIS_SIZE = _portrait_module.GRAVESTONE_RENDER_ANALYSIS_SIZE
    detect_portrait_opening = _portrait_module.detect_portrait_opening

from app.gravestone_categories import (
    GRAVESTONE_CATEGORIES,
    delete_gravestone_category,
    gravestone_metadata_path,
    load_gravestone_category,
    move_gravestone_category,
    normalize_gravestone_category,
    require_gravestone_category,
    save_gravestone_category,
)

LOGGER = logging.getLogger("gravestone_review")
SUPPORTED_SUFFIXES = {".png"}
ASSET_DIR_NAME = "graveyard"
LEGACY_ASSET_DIR_NAME = "gaveyard"
PLACEHOLDER_NAME = "gravestone_placeholder.png"
PRODUCTIVE_MANIFEST_NAME = "gravestones_manifest.json"
COMPRESSED_SIZE = (537, 732)

@dataclass
class GeometryConfig:
    canvas_size: tuple[int, int]
    portrait_bbox: tuple[int, int, int, int]
    text_safe_area: tuple[int, int, int, int]
    border_safety_px: int = 12
    edge_clear_px: int = 8
    portrait_core_inset_px: int = 50
    portrait_core_transparency_min: float = 0.98
    portrait_core_block_min: float = 0.95
    portrait_geometry_outer_opaque_min: float = 0.20
    portrait_annulus_opaque_min: float = 0.50

    def scale_box(
        self, box: tuple[int, int, int, int], target_size: tuple[int, int]
    ) -> tuple[int, int, int, int]:
        """Scale one master-canvas box to an arbitrary source canvas."""
        sx = target_size[0] / self.canvas_size[0]
        sy = target_size[1] / self.canvas_size[1]
        return tuple(round(value * (sx if index % 2 == 0 else sy)) for index, value in enumerate(box))

    @classmethod
    def load(cls, path: Path) -> "GeometryConfig":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            canvas_size=tuple(data["canvas_size"]),
            portrait_bbox=tuple(data["portrait_bbox"]),
            text_safe_area=tuple(data["text_safe_area"]),
            border_safety_px=int(data.get("border_safety_px", 12)),
            edge_clear_px=int(data.get("edge_clear_px", 8)),
            portrait_core_inset_px=int(data.get("portrait_core_inset_px", 50)),
            portrait_core_transparency_min=float(data.get("portrait_core_transparency_min", 0.98)),
            portrait_core_block_min=float(data.get("portrait_core_block_min", 0.95)),
            portrait_geometry_outer_opaque_min=float(data.get("portrait_geometry_outer_opaque_min", 0.20)),
            portrait_annulus_opaque_min=float(data.get("portrait_annulus_opaque_min", 0.50)),
        )


@dataclass
class CheckResult:
    label: str
    ok: bool
    critical: bool
    detail: str = ""


@dataclass
class OpeningAnalysis:
    found: bool
    seed: tuple[int, int] | None
    mask: Image.Image | None
    bbox: tuple[int, int, int, int] | None
    area: int = 0
    centroid: tuple[float, float] | None = None
    center_distance: float = 0.0
    area_ratio: float = 0.0
    width_ratio: float = 0.0
    height_ratio: float = 0.0
    core_transparency_ratio: float = 0.0
    core_problem_mask: Image.Image | None = None
    overlap_ratio: float = 0.0
    notes: list[str] | None = None

    @classmethod
    def empty(cls, size: tuple[int, int]) -> "OpeningAnalysis":
        return cls(False, None, Image.new("L", size, 0), None, notes=[])


@dataclass(frozen=True)
class OpeningTransparencyMetrics:
    """Measured alpha quality inside the detected portrait opening."""

    found: bool
    transparent_pixels: int
    semitransparent_pixels: int
    nontransparent_pixels: int
    total_pixels: int
    transparency_ratio: float
    expected_mask: Image.Image
    problem_mask: Image.Image


def _fill_binary_holes(mask: Image.Image) -> Image.Image:
    """Fill opaque islands enclosed by one detected transparent component."""
    binary = mask.convert("L").point(lambda value: 255 if value > 8 else 0)
    inverse = ImageOps.invert(binary)
    outside = inverse.copy()
    if outside.size[0] and outside.size[1]:
        ImageDraw.floodfill(outside, (0, 0), 128, thresh=0)
    outside_mask = outside.point(lambda value: 255 if value == 128 else 0)
    holes = ImageChops.subtract(inverse, outside_mask)
    return ImageChops.lighter(binary, holes)


def opening_transparency_metrics(
    image: Image.Image,
    analysis: OpeningAnalysis | None,
) -> OpeningTransparencyMetrics:
    """Return transparent/problem pixels for the actual detected opening.

    The detected component is hole-filled before measuring. This makes opaque
    islands inside an otherwise usable opening visible without treating the
    surrounding ornament as part of the portrait window.
    """
    rgba = image.convert("RGBA")
    size = rgba.size
    if analysis is None or analysis.mask is None or analysis.bbox is None:
        empty = Image.new("L", size, 0)
        return OpeningTransparencyMetrics(False, 0, 0, 0, 0, 0.0, empty, empty.copy())

    source_mask = analysis.mask
    if source_mask.size != size:
        source_mask = source_mask.resize(size, Image.Resampling.NEAREST)
    expected_mask = _fill_binary_holes(source_mask)
    alpha = rgba.getchannel("A")
    # The original implementation walked every pixel in Python.  Histogram(mask=...)
    # performs the same counting in Pillow's native code and is dramatically faster.
    histogram = alpha.histogram(mask=expected_mask)
    transparent = int(sum(histogram[:17]))
    semitransparent = int(sum(histogram[17:33]))
    nontransparent = int(sum(histogram[33:]))
    total = transparent + semitransparent + nontransparent
    problem_mask = ImageChops.multiply(expected_mask, _binary_threshold(alpha, low=33))
    ratio = (transparent + semitransparent) / total if total else 0.0
    return OpeningTransparencyMetrics(
        bool(analysis.found), transparent, semitransparent, nontransparent,
        total, ratio, expected_mask, problem_mask,
    )


def normalize_review_image(image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    """Fit an arbitrary RGBA canvas into the review canvas without distortion."""
    rgba = image.convert("RGBA")
    if rgba.size == target_size:
        return rgba.copy()
    fitted = ImageOps.contain(rgba, target_size, Image.Resampling.LANCZOS)
    normalized = Image.new("RGBA", target_size, (0, 0, 0, 0))
    normalized.alpha_composite(
        fitted,
        ((target_size[0] - fitted.width) // 2, (target_size[1] - fitted.height) // 2),
    )
    return normalized


def _hist_count(image: Image.Image, low: int = 1, high: int = 255, mask: Image.Image | None = None) -> int:
    """Count grayscale pixels in an inclusive value range via Pillow's C histogram path."""
    histogram = image.histogram(mask=mask)
    return int(sum(histogram[max(0, low):min(255, high) + 1]))


def _binary_threshold(image: Image.Image, *, low: int = 0, high: int = 255) -> Image.Image:
    """Return an L-mode 0/255 mask for values inside the inclusive range."""
    lut = [255 if low <= value <= high else 0 for value in range(256)]
    return image.point(lut)


class AssetValidator:
    def __init__(self, geometry: GeometryConfig):
        self.geometry = geometry
        self.last_analysis: OpeningAnalysis | None = None
        self._validation_cache: dict[tuple[str, int, int], tuple[list[CheckResult], OpeningAnalysis | None]] = {}
        self._mask_cache: dict[tuple[tuple[int, int], tuple[int, int, int, int], int], Image.Image] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    @staticmethod
    def _signature(path: Path) -> tuple[str, int, int]:
        path = Path(path)
        try:
            stat = path.stat()
            return str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size)
        except OSError:
            return str(path.absolute()), 0, 0

    def invalidate(self, path: Path) -> None:
        resolved = self._signature(path)[0]
        for key in list(self._validation_cache):
            if key[0] == resolved:
                self._validation_cache.pop(key, None)

    def seed_cache(self, path: Path, results: list[CheckResult], analysis: OpeningAnalysis | None) -> None:
        signature = self._signature(path)
        self.invalidate(path)
        self._validation_cache[signature] = (list(results), analysis)
        while len(self._validation_cache) > 16:
            self._validation_cache.pop(next(iter(self._validation_cache)))

    def transfer_cache(self, source: Path, destination: Path) -> None:
        source_resolved = str(Path(source).absolute())
        cached = None
        for key in list(self._validation_cache):
            if key[0] in {source_resolved, str(Path(source).resolve())}:
                cached = self._validation_cache.pop(key)
        if cached is not None and Path(destination).is_file():
            self.seed_cache(destination, cached[0], cached[1])

    def validate(self, path: Path) -> list[CheckResult]:
        path = Path(path)
        signature = self._signature(path)
        cached = self._validation_cache.get(signature)
        if cached is not None:
            self.cache_hits += 1
            self.last_analysis = cached[1]
            LOGGER.debug("VALIDATE_CACHE_HIT | path=%s", path)
            return list(cached[0])

        self.cache_misses += 1
        started = time.perf_counter()
        results: list[CheckResult] = []
        self.last_analysis = None
        try:
            with Image.open(path) as src:
                src.load()
                fmt = src.format
                mode = src.mode
                size = src.size
                has_alpha = mode in {"RGBA", "LA", "PA"} or (mode == "P" and "transparency" in src.info)
                image = src.convert("RGBA")
        except Exception as exc:  # noqa: BLE001
            return [CheckResult("Bild lesbar", False, True, str(exc))]

        results.append(CheckResult("PNG", fmt == "PNG", True, f"Format: {fmt}"))
        size_detail = f"Quelle: {size[0]}×{size[1]}"
        if size != self.geometry.canvas_size:
            size_detail += f"; wird proportional auf {self.geometry.canvas_size[0]}×{self.geometry.canvas_size[1]} eingepasst"
        results.append(CheckResult("Flexible Canvas-Größe", True, False, size_detail))
        results.append(CheckResult("Alpha-Kanal", has_alpha, True, f"Modus: {mode}"))

        if fmt != "PNG" or not has_alpha:
            self.last_analysis = OpeningAnalysis.empty(self.geometry.canvas_size)
            alpha = image.getchannel("A")
            edge_ok, edge_detail = self._check_border(alpha, self.geometry.edge_clear_px)
            results.append(CheckResult("Canvas-Kante frei", edge_ok, False, edge_detail))
            border_ok, border_detail = self._check_border(alpha, self.geometry.border_safety_px)
            results.append(CheckResult("Sicherheitsabstand", border_ok, False, border_detail))
            self.seed_cache(path, results, self.last_analysis)
            LOGGER.debug("VALIDATE_CACHE_MISS | path=%s | elapsed_ms=%.1f", path, (time.perf_counter() - started) * 1000.0)
            return list(results)

        source_alpha = image.getchannel("A")
        edge_ok, edge_detail = self._check_border(source_alpha, self.geometry.edge_clear_px)
        results.append(CheckResult("Canvas-Kante frei", edge_ok, False, edge_detail))

        border_ok, border_detail = self._check_border(source_alpha, self.geometry.border_safety_px)
        results.append(CheckResult("Sicherheitsabstand", border_ok, False, border_detail))

        image = normalize_review_image(image, self.geometry.canvas_size)
        alpha = image.getchannel("A")

        analysis = self._detect_opening(image)
        self.last_analysis = analysis

        found_ok, found_critical, found_detail = self._check_opening_found(analysis)
        results.append(CheckResult("Portraitöffnung erkannt", found_ok, found_critical, found_detail))

        cent_ok, _cent_critical, cent_detail = self._check_opening_center(analysis)
        results.append(CheckResult("Portraitöffnung Position", cent_ok, False, cent_detail))

        size_ok, size_critical, size_detail = self._check_opening_size(analysis)
        results.append(CheckResult("Portraitöffnung Größe plausibel", size_ok, size_critical, size_detail))

        shape_ok, shape_critical, shape_detail = self._check_opening_shape(analysis)
        results.append(CheckResult("Portraitöffnung Form plausibel", shape_ok, shape_critical, shape_detail))

        overlap_ok, _overlap_critical, overlap_detail = self._check_opening_overlap(analysis)
        results.append(CheckResult("Portraitöffnung Master-Überdeckung", overlap_ok, False, overlap_detail))

        core_ok, core_detail = self._check_master_core_warning(analysis)
        results.append(CheckResult("Master-Kernvergleich", core_ok, False, core_detail))

        metrics = opening_transparency_metrics(image, analysis)
        opaque_ratio = (
            metrics.nontransparent_pixels / metrics.total_pixels
            if metrics.total_pixels else 1.0
        )
        transparency_ok = metrics.nontransparent_pixels == 0
        transparency_critical = bool(metrics.found and opaque_ratio > 0.12)
        results.append(CheckResult(
            "Transparenz innerhalb Portraitöffnung",
            transparency_ok,
            transparency_critical,
            (
                f"transparent {metrics.transparent_pixels}, "
                f"teiltransparent {metrics.semitransparent_pixels}, "
                f"nichttransparent {metrics.nontransparent_pixels}; "
                f"Transparenz-Anteil {metrics.transparency_ratio:.1%}"
            ),
        ))

        rim_ok, rim_detail = self._check_portrait_edge(alpha, analysis)
        results.append(CheckResult("Innenkante / Anti-Aliasing plausibel", rim_ok, False, rim_detail))

        annulus_ok, annulus_detail = self._check_portrait_annulus(alpha, analysis)
        results.append(CheckResult("Portraitrahmen plausibel", annulus_ok, False, annulus_detail))

        component_ok, component_detail = self._check_stray_alpha(image)
        results.append(CheckResult("Keine auffälligen Alpha-Inseln", component_ok, False, component_detail))
        self.seed_cache(path, results, self.last_analysis)
        LOGGER.debug("VALIDATE_CACHE_MISS | path=%s | elapsed_ms=%.1f", path, (time.perf_counter() - started) * 1000.0)
        return list(results)

    def _check_border(self, alpha: Image.Image, safety_px: int) -> tuple[bool, str]:
        w, h = alpha.size
        s = max(1, safety_px)
        named_strips = {
            "oben": alpha.crop((0, 0, w, s)),
            "unten": alpha.crop((0, h - s, w, h)),
            "links": alpha.crop((0, 0, s, h)),
            "rechts": alpha.crop((w - s, 0, w, h)),
        }
        counts = {name: _hist_count(strip, 9, 255) for name, strip in named_strips.items()}
        nonzero = sum(counts.values())
        detail = (
            f"Nicht transparente Pixel in den äußeren {s}px: {nonzero} "
            f"(oben {counts['oben']}, unten {counts['unten']}, links {counts['links']}, rechts {counts['rechts']})"
        )
        return nonzero == 0, detail

    def _ellipse_mask(self, size: tuple[int, int], bbox: tuple[int, int, int, int], inset: int = 0) -> Image.Image:
        key = (tuple(size), tuple(bbox), int(inset))
        cached = self._mask_cache.get(key)
        if cached is not None:
            return cached
        x1, y1, x2, y2 = bbox
        box = (x1 + inset, y1 + inset, x2 - inset, y2 - inset)
        mask = Image.new("L", size, 0)
        ImageDraw.Draw(mask).ellipse(box, fill=255)
        self._mask_cache[key] = mask
        return mask

    def _detect_opening(self, image: Image.Image) -> OpeningAnalysis:
        """Analyze the same adaptive opening that the checker will render."""
        size = image.size
        alpha = image.getchannel("A")
        opening = detect_portrait_opening(image, self.geometry.portrait_bbox, analysis_size=GRAVESTONE_RENDER_ANALYSIS_SIZE)
        analysis = OpeningAnalysis.empty(size)
        analysis.seed = opening.seed
        analysis.mask = opening.full_mask
        analysis.bbox = opening.box
        analysis.area = opening.area
        analysis.centroid = opening.centroid
        analysis.notes = []

        if not opening.adaptive:
            analysis.notes.append(opening.reason or "Keine adaptive Portraitöffnung erkannt; Legacy-Fallback aktiv")
        else:
            analysis.found = True
            x1, y1, x2, y2 = self.geometry.portrait_bbox
            exp_w = x2 - x1
            exp_h = y2 - y1
            exp_area = math.pi * (exp_w / 2) * (exp_h / 2)
            exp_center = ((x1 + x2) / 2, (y1 + y2) / 2)
            bbox = opening.box
            centroid = opening.centroid or ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
            analysis.center_distance = math.dist(centroid, exp_center)
            analysis.area_ratio = opening.area / exp_area if exp_area else 0.0
            analysis.width_ratio = (bbox[2] - bbox[0]) / exp_w if exp_w else 0.0
            analysis.height_ratio = (bbox[3] - bbox[1]) / exp_h if exp_h else 0.0

        core_inset = max(1, self.geometry.portrait_core_inset_px + 10)
        master_core = self._ellipse_mask(size, self.geometry.portrait_bbox, inset=core_inset)
        core_histogram = alpha.histogram(mask=master_core)
        core_count = int(sum(core_histogram))
        if core_count:
            transparent = int(sum(core_histogram[:17]))
            analysis.core_transparency_ratio = transparent / core_count
            analysis.core_problem_mask = ImageChops.multiply(master_core, _binary_threshold(alpha, low=33))

        if opening.adaptive:
            master_open = self._ellipse_mask(size, self.geometry.portrait_bbox)
            component_binary = _binary_threshold(opening.component_mask, low=1)
            inter_mask = ImageChops.multiply(component_binary, master_open)
            inter = _hist_count(inter_mask, 1, 255)
            master_count = _hist_count(master_open, 1, 255)
            analysis.overlap_ratio = inter / master_count if master_count else 0.0
        return analysis

    def _check_opening_found(self, analysis: OpeningAnalysis) -> tuple[bool, bool, str]:
        if not analysis.found:
            detail = "; ".join(analysis.notes or []) or "Keine Öffnung erkannt"
            return False, True, detail
        return True, False, f"Erkannte Öffnung vorhanden; Fläche {analysis.area} px"

    def _graded_check(self, value: float, good_low: float, good_high: float, warn_low: float, warn_high: float, label: str) -> tuple[bool, bool, str]:
        if good_low <= value <= good_high:
            return True, False, f"{label}: {value:.1f}"
        if warn_low <= value <= warn_high:
            return False, False, f"{label}: {value:.1f} (Warnbereich)"
        return False, True, f"{label}: {value:.1f} (kritisch)"

    def _check_opening_center(self, analysis: OpeningAnalysis) -> tuple[bool, bool, str]:
        if not analysis.found:
            return False, True, "Keine Öffnung erkannt"
        d = analysis.center_distance
        if d <= 45:
            return True, False, f"Abstand zur Referenzmitte: {d:.1f}px"
        if d <= 120:
            return False, False, f"Abstand zur Referenzmitte: {d:.1f}px (Designabweichung)"
        return False, False, f"Abstand zur Referenzmitte: {d:.1f}px (starke Designabweichung)"

    def _check_opening_size(self, analysis: OpeningAnalysis) -> tuple[bool, bool, str]:
        if not analysis.found:
            return False, True, "Keine technisch nutzbare adaptive Öffnung erkannt"
        r = analysis.area_ratio
        if 0.35 <= r <= 1.80:
            return True, False, f"Flächenverhältnis zur Referenzöffnung: {r:.2f}"
        if 0.20 <= r <= 2.20:
            return False, False, f"Flächenverhältnis zur Referenzöffnung: {r:.2f} (starke Designabweichung)"
        return False, True, f"Flächenverhältnis zur Referenzöffnung: {r:.2f} (für Portraitnutzung unplausibel)"

    def _check_opening_shape(self, analysis: OpeningAnalysis) -> tuple[bool, bool, str]:
        if not analysis.found or not analysis.bbox:
            return False, True, "Keine technisch nutzbare adaptive Öffnung erkannt"
        wr = analysis.width_ratio
        hr = analysis.height_ratio
        if 0.55 <= wr <= 1.55 and 0.55 <= hr <= 1.55:
            return True, False, f"Breite {wr:.2f}×, Höhe {hr:.2f}× der Referenzöffnung"
        if 0.30 <= wr <= 2.00 and 0.30 <= hr <= 2.00:
            return False, False, f"Breite {wr:.2f}×, Höhe {hr:.2f}× der Referenzöffnung (starke Designabweichung)"
        return False, True, f"Breite {wr:.2f}×, Höhe {hr:.2f}× der Referenzöffnung (für Portraitnutzung unplausibel)"

    def _check_opening_overlap(self, analysis: OpeningAnalysis) -> tuple[bool, bool, str]:
        if not analysis.found:
            return False, True, "Keine Öffnung erkannt"
        overlap = analysis.overlap_ratio
        if overlap >= 0.82:
            return True, False, f"Überdeckung mit Referenzöffnung: {overlap:.1%}"
        if overlap >= 0.45:
            return False, False, f"Überdeckung mit Referenzöffnung: {overlap:.1%} (Designabweichung)"
        return False, False, f"Überdeckung mit Referenzöffnung: {overlap:.1%} (starke Designabweichung)"

    def _check_master_core_warning(self, analysis: OpeningAnalysis) -> tuple[bool, str]:
        ratio = analysis.core_transparency_ratio
        if ratio >= 0.95:
            return True, f"Transparenz im Master-Kernvergleich: {ratio:.1%}"
        if ratio >= 0.88:
            return False, f"Transparenz im Master-Kernvergleich: {ratio:.1%} (nur Warnung)"
        return False, f"Transparenz im Master-Kernvergleich: {ratio:.1%} (nur Warnung; adaptive Öffnungserkennung ist maßgeblich)"

    def _opening_region(
        self, analysis: OpeningAnalysis, size: tuple[int, int], pad: int
    ) -> tuple[int, int, int, int]:
        box = analysis.bbox or self.geometry.portrait_bbox
        return (
            max(0, box[0] - pad),
            max(0, box[1] - pad),
            min(size[0], box[2] + pad),
            min(size[1], box[3] + pad),
        )

    def _check_portrait_edge(self, alpha: Image.Image, analysis: OpeningAnalysis) -> tuple[bool, str]:
        if analysis.mask is None:
            return False, "Keine Portraitmaske verfügbar"
        region = self._opening_region(analysis, alpha.size, 8)
        mask_crop = analysis.mask.crop(region)
        alpha_crop = alpha.crop(region)
        binary = mask_crop.point(lambda p: 255 if p > 8 else 0)
        outer = binary.filter(ImageFilter.MaxFilter(11))
        inner = binary.filter(ImageFilter.MinFilter(11))
        ring = ImageChops.subtract(outer, inner)
        histogram = alpha_crop.histogram(mask=ring)
        total = int(sum(histogram))
        if not total:
            return False, "Kein adaptiver Innenkanten-Prüfring verfügbar"
        transparent = int(sum(histogram[:9]))
        semi = int(sum(histogram[9:247]))
        opaque = int(sum(histogram[247:]))
        return True, (
            f"Adaptive Innenkante: transparent {transparent/total:.1%}, "
            f"halbtransparent {semi/total:.1%}, opak {opaque/total:.1%}"
        )

    def _check_portrait_annulus(self, alpha: Image.Image, analysis: OpeningAnalysis) -> tuple[bool, str]:
        if analysis.mask is None:
            return False, "Keine Portraitmaske verfügbar"
        region = self._opening_region(analysis, alpha.size, 32)
        mask_crop = analysis.mask.crop(region)
        alpha_crop = alpha.crop(region)
        binary = mask_crop.point(lambda p: 255 if p > 8 else 0)
        # About 25 px around the real opening, matching the historical safety
        # ring without one very large (and slow) morphology kernel.
        outer = binary
        for _ in range(5):
            outer = outer.filter(ImageFilter.MaxFilter(11))
        ring = ImageChops.subtract(outer, binary)
        histogram = alpha_crop.histogram(mask=ring)
        total = int(sum(histogram))
        if not total:
            return False, "Kein adaptiver Prüfring verfügbar"
        opaque = int(sum(histogram[64:]))
        ratio = opaque / total
        ok = ratio >= self.geometry.portrait_annulus_opaque_min
        return ok, f"Rahmenbelegung um reale Öffnung: {ratio:.1%}"

    def _check_stray_alpha(self, image: Image.Image) -> tuple[bool, str]:
        alpha = image.getchannel("A")
        w, h = alpha.size
        tile = 24
        occupied: set[tuple[int, int]] = set()
        for ty in range(0, h, tile):
            for tx in range(0, w, tile):
                crop = alpha.crop((tx, ty, min(tx + tile, w), min(ty + tile, h)))
                count = _hist_count(crop, 17, 255)
                if count >= 8:
                    occupied.add((tx // tile, ty // tile))
        sparse_islands = 0
        for cell in occupied:
            x, y = cell
            neighbors = sum((x + dx, y + dy) in occupied for dx in (-1, 0, 1) for dy in (-1, 0, 1) if not (dx == 0 and dy == 0))
            if neighbors == 0:
                sparse_islands += 1
        ok = sparse_islands == 0
        return ok, f"Isolierte Alpha-Bereiche: {sparse_islands}"

    @staticmethod
    def has_critical_failure(results: Iterable[CheckResult]) -> bool:
        return any(r.critical and not r.ok for r in results)



@dataclass(frozen=True)
class WorkspacePaths:
    project_root: Path
    graveyard: Path
    candidates: Path
    accepted: Path
    approved: Path
    approved_compressed: Path
    rejected: Path
    logs: Path
    placeholder: Path
    legacy_graveyard: Path
    legacy_detected: bool


@dataclass(frozen=True)
class ReviewCounts:
    candidates: int
    accepted: int
    approved: int
    rejected: int


@dataclass(frozen=True)
class ProductiveEntry:
    """One manifest-authoritative productive item for a read-only review UI."""

    path: Path
    metadata: dict


@dataclass(frozen=True)
class CompressedCheck:
    ok: bool
    detail: str
    size: tuple[int, int] | None = None
    mode: str | None = None


@dataclass(frozen=True)
class AcceptResult:
    accepted_path: Path
    category: str | None = None


@dataclass(frozen=True)
class ReleaseResult:
    master_path: Path
    compressed_path: Path
    compressed_check: CompressedCheck
    category: str


ProgressCallback = Callable[[int, str], None]


def review_workspace(project_root: Path) -> WorkspacePaths:
    """Resolve review paths without creating or changing anything on disk."""
    project_root = Path(project_root).expanduser().resolve()
    graveyard = project_root / "assets" / ASSET_DIR_NAME
    legacy = project_root / "assets" / LEGACY_ASSET_DIR_NAME
    paths = WorkspacePaths(
        project_root=project_root,
        graveyard=graveyard,
        candidates=graveyard / "_candidates",
        accepted=graveyard / "_accepted",
        approved=graveyard / "_approved_new",
        approved_compressed=graveyard / "_approved_new" / "compressed",
        rejected=graveyard / "_rejected",
        logs=graveyard / "_review_logs",
        placeholder=graveyard / PLACEHOLDER_NAME,
        legacy_graveyard=legacy,
        legacy_detected=legacy.is_dir(),
    )
    return paths


def ensure_workspace(project_root: Path) -> WorkspacePaths:
    """Create the review workspace below assets/graveyard.

    A legacy assets/gaveyard directory is detected for diagnostics only. It is
    never used as the destination for newly created review folders.
    """
    paths = review_workspace(project_root)
    for folder in (
        paths.graveyard,
        paths.candidates,
        paths.accepted,
        paths.approved,
        paths.approved_compressed,
        paths.rejected,
        paths.logs,
    ):
        folder.mkdir(parents=True, exist_ok=True)
    return paths


def _count_png_files(folder: Path) -> int:
    try:
        return sum(
            1 for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() == ".png" and p.name != PLACEHOLDER_NAME
        )
    except OSError:
        return 0


def _list_png_files(folder: Path) -> list[Path]:
    try:
        return sorted(
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES and p.name != PLACEHOLDER_NAME
        )
    except OSError:
        return []


def review_counts(workspace: WorkspacePaths) -> ReviewCounts:
    # approved_compressed is a subfolder and intentionally not counted here.
    return ReviewCounts(
        candidates=_count_png_files(workspace.candidates),
        accepted=_count_png_files(workspace.accepted),
        approved=_count_png_files(workspace.approved),
        rejected=_count_png_files(workspace.rejected),
    )


def list_candidates(workspace: WorkspacePaths) -> list[Path]:
    return _list_png_files(workspace.candidates)


def list_accepted(workspace: WorkspacePaths) -> list[Path]:
    return _list_png_files(workspace.accepted)


def list_approved(workspace: WorkspacePaths) -> list[Path]:
    return _list_png_files(workspace.approved)


def list_rejected(workspace: WorkspacePaths) -> list[Path]:
    return _list_png_files(workspace.rejected)


def list_productive(workspace: WorkspacePaths) -> list[ProductiveEntry]:
    """Return only manifest-listed productive PNGs in manifest order.

    The function is intentionally non-mutating: read-only review views must
    never infer productive items from arbitrary graveyard files or rewrite a
    manifest while they inspect it.
    """
    manifest_path = workspace.graveyard / PRODUCTIVE_MANIFEST_NAME
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        templates = payload.get("templates") if isinstance(payload, dict) else None
    except (OSError, TypeError, ValueError):
        return []
    if not isinstance(templates, list):
        return []

    entries: list[ProductiveEntry] = []
    for raw in templates:
        if not isinstance(raw, dict):
            continue
        filename = str(raw.get("filename") or "").strip()
        if not filename or Path(filename).name != filename or filename == PLACEHOLDER_NAME:
            continue
        path = workspace.graveyard / filename
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            entries.append(ProductiveEntry(path=path, metadata=dict(raw)))
    return entries


def set_review_category(image_path: Path, workspace: WorkspacePaths, category: object) -> Path:
    """Persist one category only for files inside a mutable review queue."""
    image_path = Path(image_path)
    allowed_parents = {
        workspace.candidates.resolve(), workspace.accepted.resolve(),
        workspace.rejected.resolve(), workspace.approved.resolve(),
    }
    if image_path.parent.resolve() not in allowed_parents:
        raise ValueError("Kategorie darf nur in einer Review-Queue geändert werden")
    if image_path.name == PLACEHOLDER_NAME:
        raise ValueError("gravestone_placeholder.png ist eine Sonderdatei")
    if not image_path.is_file():
        raise FileNotFoundError(image_path)
    return save_gravestone_category(image_path, category)


def validate_compressed_png(path: Path) -> CompressedCheck:
    try:
        with Image.open(path) as src:
            src.load()
            fmt = src.format
            size = src.size
            mode = src.mode
            has_alpha = mode in {"RGBA", "LA", "PA"} or (mode == "P" and "transparency" in src.info)
    except Exception as exc:  # noqa: BLE001
        return CompressedCheck(False, f"Datei nicht lesbar: {exc}")

    problems: list[str] = []
    if fmt != "PNG":
        problems.append(f"Format {fmt} statt PNG")
    if size != COMPRESSED_SIZE:
        problems.append(f"Größe {size[0]}×{size[1]} statt {COMPRESSED_SIZE[0]}×{COMPRESSED_SIZE[1]}")
    if not has_alpha:
        problems.append(f"kein Alpha-Kanal (Modus {mode})")
    if problems:
        return CompressedCheck(False, "; ".join(problems), size=size, mode=mode)
    return CompressedCheck(True, f"PNG {size[0]}×{size[1]}, Alpha vorhanden, Modus {mode}", size=size, mode=mode)


def create_compressed_png(source: Path, target: Path) -> CompressedCheck:
    """Create a high-quality 537×732 RGBA PNG without distorting the source."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as src:
        src.load()
        rgba = src.convert("RGBA")
        resized = normalize_review_image(rgba, COMPRESSED_SIZE)
        resized.save(target, format="PNG", optimize=True, compress_level=9)
    return validate_compressed_png(target)


def _critical_blockers(results: Iterable[CheckResult]) -> list[str]:
    return [r.label for r in results if r.critical and not r.ok]


def accept_candidate(
    candidate: Path,
    workspace: WorkspacePaths,
    validator: AssetValidator,
    progress: ProgressCallback | None = None,
    category: str | None = None,
) -> AcceptResult:
    """Move a technically valid candidate to the _accepted intermediate queue.

    Acceptance intentionally does not create the compressed release copy. That
    happens only during the explicit Freigabe step.
    """
    candidate = Path(candidate)
    if candidate.parent.resolve() != workspace.candidates.resolve():
        raise ValueError("Kandidat liegt nicht direkt in _candidates")
    if candidate.name == PLACEHOLDER_NAME:
        raise ValueError("gravestone_placeholder.png ist eine Sonderdatei und kein Kandidat")
    if not candidate.exists():
        raise FileNotFoundError(candidate)
    if category not in (None, ""):
        category = require_gravestone_category(category)
    else:
        category = load_gravestone_category(candidate)

    if progress:
        progress(25, "Technische Prüfung")
    results = validator.validate(candidate)
    blockers = _critical_blockers(results)
    if blockers:
        raise RuntimeError("Kritische technische Fehler: " + ", ".join(blockers))

    target = workspace.accepted / candidate.name
    if target.exists():
        raise FileExistsError(f"Akzeptierte Datei existiert bereits: {target}")
    if progress:
        progress(75, "Nach Akzeptiert verschieben")
    LOGGER.info("ACCEPT_MOVE | source=%s | destination=%s", candidate, target)
    shutil.move(str(candidate), str(target))
    metadata_moved = False
    try:
        metadata_moved = gravestone_metadata_path(candidate).is_file()
        move_gravestone_category(candidate, target)
        if category is not None:
            save_gravestone_category(target, category)
    except Exception:
        if metadata_moved and gravestone_metadata_path(target).is_file():
            move_gravestone_category(target, candidate)
        else:
            delete_gravestone_category(target)
        shutil.move(str(target), str(candidate))
        raise
    if progress:
        progress(100, "Akzeptiert")
    return AcceptResult(target, category)


def restore_accepted(accepted: Path, workspace: WorkspacePaths) -> Path:
    """Undo an accidental acceptance by moving the file back to _candidates."""
    accepted = Path(accepted)
    if accepted.parent.resolve() != workspace.accepted.resolve():
        raise ValueError("Datei liegt nicht direkt in _accepted")
    if accepted.name == PLACEHOLDER_NAME:
        raise ValueError("gravestone_placeholder.png ist eine Sonderdatei")
    if not accepted.exists():
        raise FileNotFoundError(accepted)
    target = workspace.candidates / accepted.name
    if target.exists():
        raise FileExistsError(f"Kandidat existiert bereits: {target}")
    LOGGER.info("ACCEPT_RESTORE | source=%s | destination=%s", accepted, target)
    shutil.move(str(accepted), str(target))
    try:
        move_gravestone_category(accepted, target)
    except Exception:
        shutil.move(str(target), str(accepted))
        raise
    return target


def approve_accepted(
    accepted: Path,
    workspace: WorkspacePaths,
    validator: AssetValidator,
    progress: ProgressCallback | None = None,
    category: str | None = None,
) -> ReleaseResult:
    """Release one accepted master into _approved_new and create its small copy.

    The productive assets/graveyard root and manifest remain untouched. On a
    compression/verification failure the master is rolled back to _accepted.
    """
    accepted = Path(accepted)
    if accepted.parent.resolve() != workspace.accepted.resolve():
        raise ValueError("Datei liegt nicht direkt in _accepted")
    if accepted.name == PLACEHOLDER_NAME:
        raise ValueError("gravestone_placeholder.png ist eine Sonderdatei")
    if not accepted.exists():
        raise FileNotFoundError(accepted)
    selected_category = require_gravestone_category(
        category if category not in (None, "") else load_gravestone_category(accepted)
    )

    def step(value: int, text: str) -> None:
        if progress:
            progress(value, text)

    step(10, "1/5 Prüfung")
    results = validator.validate(accepted)
    blockers = _critical_blockers(results)
    if blockers:
        raise RuntimeError("Kritische technische Fehler: " + ", ".join(blockers))

    master_target = workspace.approved / accepted.name
    compressed_target = workspace.approved_compressed / accepted.name
    if master_target.exists():
        raise FileExistsError(f"Freigegebener Master existiert bereits: {master_target}")
    if compressed_target.exists():
        raise FileExistsError(f"Komprimierte Datei existiert bereits: {compressed_target}")
    if gravestone_metadata_path(master_target).exists():
        raise FileExistsError(f"Grabstein-Metadaten existieren bereits: {gravestone_metadata_path(master_target)}")

    moved = False
    metadata_moved = False
    tmp_compressed = compressed_target.with_name(compressed_target.name + ".tmp")
    if tmp_compressed.exists():
        tmp_compressed.unlink()

    try:
        step(30, "2/5 Master freigeben")
        LOGGER.info("APPROVE_MASTER | source=%s | destination=%s", accepted, master_target)
        shutil.move(str(accepted), str(master_target))
        moved = True

        step(55, "3/5 537×732-PNG erzeugen")
        LOGGER.info("COMPRESSED_CREATE | source=%s | temp=%s", master_target, tmp_compressed)
        check = create_compressed_png(master_target, tmp_compressed)

        step(80, "4/5 kleine PNG prüfen")
        LOGGER.info("COMPRESSED_VERIFY | file=%s | ok=%s | detail=%s", tmp_compressed, check.ok, check.detail)
        if not check.ok:
            raise RuntimeError("Technische Prüfung der kleinen PNG fehlgeschlagen: " + check.detail)
        os.replace(tmp_compressed, compressed_target)

        metadata_moved = gravestone_metadata_path(accepted).is_file()
        move_gravestone_category(accepted, master_target)
        save_gravestone_category(master_target, selected_category)

        step(100, "5/5 Abschluss")
        LOGGER.info("APPROVE_DONE | master=%s | compressed=%s", master_target, compressed_target)
        return ReleaseResult(master_target, compressed_target, check, selected_category)
    except Exception:
        LOGGER.exception("APPROVE_TRANSACTION_FAILED | accepted=%s", accepted)
        try:
            if tmp_compressed.exists():
                tmp_compressed.unlink()
        except Exception:
            LOGGER.exception("APPROVE_CLEANUP_FAILED | temp=%s", tmp_compressed)
        try:
            if compressed_target.exists():
                compressed_target.unlink()
        except Exception:
            LOGGER.exception("APPROVE_CLEANUP_FAILED | compressed=%s", compressed_target)
        try:
            if metadata_moved and gravestone_metadata_path(master_target).is_file():
                move_gravestone_category(master_target, accepted)
            else:
                delete_gravestone_category(master_target)
        except Exception:
            LOGGER.exception("APPROVE_CLEANUP_FAILED | metadata=%s", master_target)
        if moved and master_target.exists() and not accepted.exists():
            try:
                shutil.move(str(master_target), str(accepted))
                LOGGER.warning("APPROVE_ROLLBACK | master restored to accepted=%s", accepted)
            except Exception:
                LOGGER.exception("APPROVE_ROLLBACK_FAILED | master=%s | accepted=%s", master_target, accepted)
        raise


def reject_candidate(candidate: Path, workspace: WorkspacePaths) -> Path:
    candidate = Path(candidate)
    if candidate.parent.resolve() != workspace.candidates.resolve():
        raise ValueError("Kandidat liegt nicht direkt in _candidates")
    if candidate.name == PLACEHOLDER_NAME:
        raise ValueError("gravestone_placeholder.png ist eine Sonderdatei und kein Kandidat")
    target = workspace.rejected / candidate.name
    if target.exists():
        raise FileExistsError(f"Abgelehnte Datei existiert bereits: {target}")
    LOGGER.info("REJECT_MOVE | source=%s | destination=%s", candidate, target)
    shutil.move(str(candidate), str(target))
    try:
        move_gravestone_category(candidate, target)
    except Exception:
        shutil.move(str(target), str(candidate))
        raise
    return target


def delete_rejected(rejected: Path, workspace: WorkspacePaths) -> None:
    """Permanently delete exactly one PNG from _rejected and nowhere else."""
    rejected = Path(rejected)
    if rejected.parent.resolve() != workspace.rejected.resolve():
        raise ValueError("Löschen ist ausschließlich in _rejected erlaubt")
    if rejected.name == PLACEHOLDER_NAME:
        raise ValueError("gravestone_placeholder.png darf nicht gelöscht werden")
    if rejected.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("Nur PNG-Dateien dürfen gelöscht werden")
    if not rejected.exists():
        raise FileNotFoundError(rejected)
    LOGGER.warning("REJECT_DELETE | file=%s", rejected)
    rejected.unlink()
    delete_gravestone_category(rejected)


class FsyncFileHandler(logging.FileHandler):
    """File handler that forces every record to disk for reliable debug logs."""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        try:
            self.flush()
            if self.stream is not None:
                os.fsync(self.stream.fileno())
        except Exception:
            pass


def flush_review_logs() -> None:
    for handler in LOGGER.handlers:
        try:
            handler.flush()
            stream = getattr(handler, "stream", None)
            if stream is not None:
                os.fsync(stream.fileno())
        except Exception:
            pass


def setup_review_logging(log_dir: Path) -> tuple[Path, Path]:
    log_dir.mkdir(parents=True, exist_ok=True)
    latest = log_dir / "gravestone_review_latest.log"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session = log_dir / f"gravestone_review_{stamp}.log"

    LOGGER.setLevel(logging.DEBUG)
    LOGGER.propagate = False
    for handler in list(LOGGER.handlers):
        LOGGER.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    for path in (latest, session):
        handler = FsyncFileHandler(path, mode="w", encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        LOGGER.addHandler(handler)
    return latest, session


def log_validation(path: Path, results: list[CheckResult], analysis: OpeningAnalysis | None) -> None:
    LOGGER.info("VALIDATE | candidate=%s", path)
    if analysis is not None:
        LOGGER.info(
            "OPENING | found=%s | area=%s | area_ratio=%.3f | center_distance=%.2f | width_ratio=%.3f | height_ratio=%.3f | overlap=%.3f | core_ratio=%.3f | bbox=%s",
            analysis.found,
            analysis.area,
            analysis.area_ratio,
            analysis.center_distance,
            analysis.width_ratio,
            analysis.height_ratio,
            analysis.overlap_ratio,
            analysis.core_transparency_ratio,
            analysis.bbox,
        )
    for result in results:
        level = "OK" if result.ok else ("ERROR" if result.critical else "WARN")
        LOGGER.info("CHECK | %s | critical=%s | label=%s | detail=%s", level, result.critical, result.label, result.detail)
    blockers = [r.label for r in results if r.critical and not r.ok]
    warnings = [r.label for r in results if not r.ok and not r.critical]
    LOGGER.info("ACCEPT_GATE | enabled=%s | blockers=%s | warnings=%s", not blockers, blockers, warnings)
    flush_review_logs()


def locate_project_root(explicit: str | None, tool_dir: Path) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    home = Path.home()
    standard = home / "Documents" / "Codex" / "Guildchecker"
    candidates = [Path.cwd(), standard, tool_dir, *tool_dir.parents]
    for candidate in candidates:
        if (candidate / "assets" / ASSET_DIR_NAME).is_dir():
            return candidate.resolve()
    # Controlled legacy discovery: identify the project, but all new review
    # folders will still be created under assets/graveyard by ensure_workspace.
    for candidate in candidates:
        if (candidate / "assets" / LEGACY_ASSET_DIR_NAME).is_dir():
            return candidate.resolve()
    if standard.exists() and standard.is_dir():
        return standard.resolve()
    return tool_dir.parents[1].resolve()


def run_core_self_test(tool_dir: Path) -> int:
    geometry = GeometryConfig.load(tool_dir / "master_geometry.json")
    validator = AssetValidator(geometry)
    reference = tool_dir / "reference" / "master_reference.png"
    variant = tool_dir / "reference" / "good_reference_variant.png"
    if not reference.exists():
        print("SELF-TEST FAIL: master_reference.png fehlt")
        return 1

    good = validator.validate(reference)
    if AssetValidator.has_critical_failure(good):
        print("SELF-TEST FAIL: gute Referenz wurde blockiert")
        return 1
    if variant.exists() and AssetValidator.has_critical_failure(validator.validate(variant)):
        print("SELF-TEST FAIL: gute Variantenreferenz wurde blockiert")
        return 1

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "Guildchecker"
        legacy = root / "assets" / LEGACY_ASSET_DIR_NAME
        legacy.mkdir(parents=True)
        legacy_sentinel = legacy / "legacy.txt"
        legacy_sentinel.write_text("legacy", encoding="utf-8")
        ws = ensure_workspace(root)
        expected = [ws.candidates, ws.accepted, ws.approved, ws.approved_compressed, ws.rejected, ws.logs]
        if not all(p.is_dir() for p in expected):
            print("SELF-TEST FAIL: Workspace unvollständig")
            return 1
        if not ws.legacy_detected or legacy_sentinel.read_text(encoding="utf-8") != "legacy":
            print("SELF-TEST FAIL: Legacy-Erkennung verändert Altbestand")
            return 1

        placeholder = ws.placeholder
        Image.new("RGB", (64, 64), (35, 35, 35)).save(placeholder)
        placeholder_before = placeholder.read_bytes()

        c1 = ws.candidates / "candidate_01.png"
        c2 = ws.candidates / "candidate_02.png"
        shutil.copy2(reference, c1)
        shutil.copy2(reference, c2)
        shutil.copy2(reference, ws.approved / "already_approved.png")
        small_tmp = ws.approved_compressed / "already_approved.png"
        chk = create_compressed_png(reference, small_tmp)
        if not chk.ok:
            print("SELF-TEST FAIL: kleine PNG konnte nicht erzeugt werden")
            return 1
        counts = review_counts(ws)
        if counts != ReviewCounts(candidates=2, accepted=0, approved=1, rejected=0):
            print("SELF-TEST FAIL: Statuszähler falsch", counts)
            return 1

        # Warning-only file remains acceptable: edge contact is warning only.
        edge_candidate = ws.candidates / "edge_warning.png"
        edge_img = Image.open(reference).convert("RGBA")
        ImageDraw.Draw(edge_img).rectangle((0, 650, 5, 760), fill=(90, 90, 90, 255))
        edge_img.save(edge_candidate)
        edge_results = validator.validate(edge_candidate)
        if AssetValidator.has_critical_failure(edge_results):
            print("SELF-TEST FAIL: reine Warnung blockiert")
            return 1

        # Clearly broken opening must block.
        bad = ws.candidates / "bad_opening.png"
        bad_img = Image.open(reference).convert("RGBA")
        x1, y1, x2, y2 = geometry.portrait_bbox
        ImageDraw.Draw(bad_img).ellipse((x1 + 20, y1 + 20, x2 - 20, y2 - 20), fill=(80, 80, 80, 255))
        bad_img.save(bad)
        if not AssetValidator.has_critical_failure(validator.validate(bad)):
            print("SELF-TEST FAIL: kaputte Portraitöffnung blockiert nicht")
            return 1

        # Accept only moves to _accepted and creates no compressed copy.
        accepted = accept_candidate(c1, ws, validator, category=GRAVESTONE_CATEGORIES[0])
        if not accepted.accepted_path.exists() or c1.exists():
            print("SELF-TEST FAIL: Accept-Zwischenstufe fehlt")
            return 1
        if (ws.approved / c1.name).exists() or (ws.approved_compressed / c1.name).exists():
            print("SELF-TEST FAIL: Accept hat vorzeitig Freigabe-Dateien erzeugt")
            return 1

        # Accidental acceptance can be undone.
        restored = restore_accepted(accepted.accepted_path, ws)
        if not restored.exists() or (ws.accepted / c1.name).exists():
            print("SELF-TEST FAIL: Entfernen aus Akzeptiert funktioniert nicht")
            return 1
        accepted = accept_candidate(restored, ws, validator, category=GRAVESTONE_CATEGORIES[0])

        # Freigabe creates master + compressed and leaves productive assets untouched.
        result = approve_accepted(accepted.accepted_path, ws, validator)
        if not result.master_path.exists() or not result.compressed_path.exists():
            print("SELF-TEST FAIL: Freigabe-Ausgabe fehlt")
            return 1
        if not result.compressed_check.ok:
            print("SELF-TEST FAIL: kleine PNG-Prüfung fehlgeschlagen")
            return 1
        with Image.open(result.compressed_path) as im:
            if im.size != COMPRESSED_SIZE or "A" not in im.getbands():
                print("SELF-TEST FAIL: kleine PNG Größe/Alpha falsch")
                return 1

        # Transaction safety: a compression failure rolls back to _accepted.
        rollback_candidate = ws.candidates / "rollback_test.png"
        shutil.copy2(reference, rollback_candidate)
        rollback_accepted = accept_candidate(
            rollback_candidate, ws, validator, category=GRAVESTONE_CATEGORIES[0]
        ).accepted_path
        original_creator = globals()["create_compressed_png"]
        previous_logger_disabled = LOGGER.disabled
        def _forced_compression_failure(source: Path, target: Path) -> CompressedCheck:
            raise RuntimeError("forced compression failure")
        globals()["create_compressed_png"] = _forced_compression_failure
        LOGGER.disabled = True
        try:
            try:
                approve_accepted(rollback_accepted, ws, validator)
                print("SELF-TEST FAIL: erzwungener Freigabe-Fehler wurde nicht ausgelöst")
                return 1
            except RuntimeError as exc:
                if "forced compression failure" not in str(exc):
                    raise
        finally:
            LOGGER.disabled = previous_logger_disabled
            globals()["create_compressed_png"] = original_creator
        if not rollback_accepted.exists() or (ws.approved / rollback_accepted.name).exists():
            print("SELF-TEST FAIL: Freigabe-Rollback hat Akzeptiert-Datei nicht wiederhergestellt")
            return 1

        # Reject only moves to _rejected; deletion is restricted to that folder.
        rejected = reject_candidate(c2, ws)
        if not rejected.exists() or (ws.approved_compressed / c2.name).exists():
            print("SELF-TEST FAIL: Reject-Workflow falsch")
            return 1
        try:
            delete_rejected(result.master_path, ws)
            print("SELF-TEST FAIL: Löschschutz außerhalb _rejected greift nicht")
            return 1
        except ValueError:
            pass
        delete_rejected(rejected, ws)
        if rejected.exists():
            print("SELF-TEST FAIL: Abgelehnte PNG wurde nicht gelöscht")
            return 1

        counts = review_counts(ws)
        if counts.approved != 2 or counts.accepted != 1 or counts.rejected != 0:
            print("SELF-TEST FAIL: Statuszähler nach Workflow falsch", counts)
            return 1

        if placeholder.read_bytes() != placeholder_before:
            print("SELF-TEST FAIL: Placeholder wurde verändert")
            return 1
        if list(ws.graveyard.glob("gravestone_[0-9][0-9][0-9].png")):
            print("SELF-TEST FAIL: Review hat produktive gravestone_XXX erzeugt")
            return 1

    print("SELF-TEST OK")
    return 0


__all__ = [
    "ASSET_DIR_NAME",
    "LEGACY_ASSET_DIR_NAME",
    "PLACEHOLDER_NAME",
    "PRODUCTIVE_MANIFEST_NAME",
    "COMPRESSED_SIZE",
    "LOGGER",
    "SUPPORTED_SUFFIXES",
    "GeometryConfig",
    "CheckResult",
    "OpeningAnalysis",
    "normalize_review_image",
    "OpeningTransparencyMetrics",
    "opening_transparency_metrics",
    "AssetValidator",
    "WorkspacePaths",
    "ReviewCounts",
    "ProductiveEntry",
    "CompressedCheck",
    "AcceptResult",
    "ReleaseResult",
    "ensure_workspace",
    "review_workspace",
    "review_counts",
    "list_candidates",
    "list_accepted",
    "list_approved",
    "list_rejected",
    "list_productive",
    "set_review_category",
    "validate_compressed_png",
    "create_compressed_png",
    "accept_candidate",
    "restore_accepted",
    "approve_accepted",
    "reject_candidate",
    "delete_rejected",
    "flush_review_logs",
    "setup_review_logging",
    "log_validation",
    "locate_project_root",
    "run_core_self_test",
]
