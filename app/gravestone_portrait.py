# -*- coding: utf-8 -*-
"""Shared gravestone portrait opening detection and compositing helpers.

The Guild Gear Checker and the Gravestone Review Tool deliberately use this
same module so a reviewed asset is rendered with the same adaptive portrait
window that is used later in the graveyard.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps


GRAVESTONE_RENDER_ANALYSIS_SIZE = (220, 300)


@dataclass(frozen=True)
class PortraitOpening:
    """Portrait opening detected in one concrete gravestone frame.

    ``box`` and ``mask`` are the crop-sized values used for rendering.
    ``full_mask`` is the same anti-aliased mask on the full frame and is useful
    for review overlays/diagnostics. ``component_mask`` contains the binary
    transparent component before anti-alias expansion.
    """

    box: tuple[int, int, int, int]
    mask: Image.Image
    full_mask: Image.Image
    component_mask: Image.Image
    adaptive: bool
    seed: tuple[int, int] | None = None
    area: int = 0
    centroid: tuple[float, float] | None = None
    touches_border: bool = False
    reason: str = ""


def ellipse_mask(size: tuple[int, int], box: tuple[int, int, int, int]) -> Image.Image:
    """Return a full-size ellipse mask for a legacy portrait box."""
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse(box, fill=255)
    return mask


def fallback_portrait_opening(
    size: tuple[int, int],
    legacy_box: tuple[int, int, int, int],
    *,
    reason: str = "Keine brauchbare adaptive Portraitöffnung erkannt",
) -> PortraitOpening:
    """Build the historical ellipse as a safe rendering fallback."""
    x1, y1, x2, y2 = legacy_box
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    crop_mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(crop_mask).ellipse((0, 0, width - 1, height - 1), fill=255)
    full_mask = Image.new("L", size, 0)
    full_mask.paste(crop_mask, (x1, y1))
    component = full_mask.copy()
    return PortraitOpening(
        box=legacy_box,
        mask=crop_mask,
        full_mask=full_mask,
        component_mask=component,
        adaptive=False,
        reason=reason,
    )


def _detect_portrait_opening_native(
    template_image: Image.Image,
    legacy_box: tuple[int, int, int, int],
    *,
    alpha_threshold: int = 64,
    search_radius_factor: float = 0.70,
    min_area_ratio: float = 0.006,
    max_area_ratio: float = 0.32,
    min_width_ratio: float = 0.16,
    min_height_ratio: float = 0.12,
) -> PortraitOpening:
    """Detect the enclosed transparent ornament opening of a gravestone.

    The search is anchored near the historical portrait position, but the
    resulting opening may vary substantially in shape, size, and position.
    Only closed, portrait-sized transparent components are accepted. When no
    plausible opening exists, the historical ellipse is returned as fallback.
    """
    frame = template_image.convert("RGBA")
    width, height = frame.size
    fallback = fallback_portrait_opening((width, height), legacy_box)
    alpha = frame.getchannel("A")
    pixels = alpha.load()

    expected_center = (
        (legacy_box[0] + legacy_box[2]) / 2.0,
        (legacy_box[1] + legacy_box[3]) / 2.0,
    )
    expected_span = max(legacy_box[2] - legacy_box[0], legacy_box[3] - legacy_box[1])
    search_radius = max(8.0, expected_span * search_radius_factor)
    search_radius_sq = search_radius * search_radius

    seed: tuple[int, int] | None = None
    best_distance_sq = search_radius_sq + 1.0
    left = max(0, int(expected_center[0] - search_radius))
    right = min(width, int(expected_center[0] + search_radius) + 1)
    top = max(0, int(expected_center[1] - search_radius))
    bottom = min(height, int(expected_center[1] + search_radius) + 1)
    for y in range(top, bottom):
        dy = y - expected_center[1]
        for x in range(left, right):
            if pixels[x, y] > alpha_threshold:
                continue
            dx = x - expected_center[0]
            distance_sq = dx * dx + dy * dy
            if distance_sq <= search_radius_sq and distance_sq < best_distance_sq:
                seed = (x, y)
                best_distance_sq = distance_sq

    if seed is None:
        return PortraitOpening(**{**fallback.__dict__, "reason": "Kein transparenter Seedpunkt nahe der Portraitzone gefunden"})

    stack = [seed]
    visited = {seed}
    coords: list[tuple[int, int]] = []
    touches_border = False
    min_x = max_x = seed[0]
    min_y = max_y = seed[1]
    while stack:
        x, y = stack.pop()
        coords.append((x, y))
        min_x = min(min_x, x)
        max_x = max(max_x, x)
        min_y = min(min_y, y)
        max_y = max(max_y, y)
        if x == 0 or y == 0 or x == width - 1 or y == height - 1:
            touches_border = True
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            point = (nx, ny)
            if not (0 <= nx < width and 0 <= ny < height) or point in visited:
                continue
            if pixels[nx, ny] > alpha_threshold:
                continue
            visited.add(point)
            stack.append(point)

    if not coords:
        return PortraitOpening(**{**fallback.__dict__, "seed": seed, "reason": "Transparenter Seed ergab keine zusammenhängende Öffnung"})

    area = len(coords)
    box = (min_x, min_y, max_x + 1, max_y + 1)
    box_width = box[2] - box[0]
    box_height = box[3] - box[1]
    min_area = max(32, round(width * height * min_area_ratio))
    max_area = max(min_area + 1, round(width * height * max_area_ratio))
    usable = (
        not touches_border
        and min_area <= area <= max_area
        and box_width >= width * min_width_ratio
        and box_height >= height * min_height_ratio
    )
    if not usable:
        reason_bits: list[str] = []
        if touches_border:
            reason_bits.append("Öffnung berührt den Canvas-Rand")
        if area < min_area:
            reason_bits.append(f"Fläche zu klein ({area} < {min_area})")
        if area > max_area:
            reason_bits.append(f"Fläche zu groß ({area} > {max_area})")
        if box_width < width * min_width_ratio:
            reason_bits.append(f"Breite zu klein ({box_width}px)")
        if box_height < height * min_height_ratio:
            reason_bits.append(f"Höhe zu klein ({box_height}px)")
        return PortraitOpening(
            box=fallback.box,
            mask=fallback.mask,
            full_mask=fallback.full_mask,
            component_mask=fallback.component_mask,
            adaptive=False,
            seed=seed,
            area=area,
            centroid=(sum(x for x, _ in coords) / area, sum(y for _, y in coords) / area),
            touches_border=touches_border,
            reason="; ".join(reason_bits) or "Öffnung geometrisch unplausibel",
        )

    component = Image.new("L", (width, height), 0)
    component_pixels = component.load()
    for x, y in coords:
        component_pixels[x, y] = 255

    # Include the anti-aliased inner rim, but never unrelated transparent areas.
    expanded = component.filter(ImageFilter.MaxFilter(5))
    inverse_alpha = ImageOps.invert(alpha)
    smooth_mask = ImageChops.multiply(inverse_alpha, expanded)
    smooth_bbox = smooth_mask.getbbox() or box
    pad = 1
    crop_box = (
        max(0, smooth_bbox[0] - pad),
        max(0, smooth_bbox[1] - pad),
        min(width, smooth_bbox[2] + pad),
        min(height, smooth_bbox[3] + pad),
    )
    centroid = (sum(x for x, _ in coords) / area, sum(y for _, y in coords) / area)
    return PortraitOpening(
        box=crop_box,
        mask=smooth_mask.crop(crop_box),
        full_mask=smooth_mask,
        component_mask=component,
        adaptive=True,
        seed=seed,
        area=area,
        centroid=centroid,
        touches_border=False,
        reason="Adaptive Portraitöffnung erkannt",
    )



def _scale_box(
    box: tuple[int, int, int, int],
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    sx = target_size[0] / source_size[0]
    sy = target_size[1] / source_size[1]
    return (
        round(box[0] * sx),
        round(box[1] * sy),
        round(box[2] * sx),
        round(box[3] * sy),
    )


def detect_portrait_opening(
    template_image: Image.Image,
    legacy_box: tuple[int, int, int, int],
    *,
    analysis_size: tuple[int, int] | None = None,
    alpha_threshold: int = 64,
    search_radius_factor: float = 0.70,
    min_area_ratio: float = 0.006,
    max_area_ratio: float = 0.32,
    min_width_ratio: float = 0.16,
    min_height_ratio: float = 0.12,
) -> PortraitOpening:
    """Detect an opening at a stable analysis resolution and scale it back.

    Passing the graveyard card size as ``analysis_size`` makes full-size review
    previews, normal cards, and editor previews agree even when tiny alpha
    corridors appear or disappear at different image resolutions.
    """
    frame = template_image.convert("RGBA")
    original_size = frame.size
    if analysis_size is None or original_size == analysis_size:
        return _detect_portrait_opening_native(
            frame,
            legacy_box,
            alpha_threshold=alpha_threshold,
            search_radius_factor=search_radius_factor,
            min_area_ratio=min_area_ratio,
            max_area_ratio=max_area_ratio,
            min_width_ratio=min_width_ratio,
            min_height_ratio=min_height_ratio,
        )

    analysis_frame = frame.resize(analysis_size, Image.Resampling.LANCZOS)
    analysis_legacy_box = _scale_box(legacy_box, original_size, analysis_size)
    detected = _detect_portrait_opening_native(
        analysis_frame,
        analysis_legacy_box,
        alpha_threshold=alpha_threshold,
        search_radius_factor=search_radius_factor,
        min_area_ratio=min_area_ratio,
        max_area_ratio=max_area_ratio,
        min_width_ratio=min_width_ratio,
        min_height_ratio=min_height_ratio,
    )

    if not detected.adaptive:
        fallback = fallback_portrait_opening(original_size, legacy_box, reason=detected.reason)
        sx = original_size[0] / analysis_size[0]
        sy = original_size[1] / analysis_size[1]
        seed = None if detected.seed is None else (round(detected.seed[0] * sx), round(detected.seed[1] * sy))
        centroid = None if detected.centroid is None else (detected.centroid[0] * sx, detected.centroid[1] * sy)
        return PortraitOpening(
            box=fallback.box,
            mask=fallback.mask,
            full_mask=fallback.full_mask,
            component_mask=fallback.component_mask,
            adaptive=False,
            seed=seed,
            area=round(detected.area * sx * sy),
            centroid=centroid,
            touches_border=detected.touches_border,
            reason=detected.reason,
        )

    scaled_box = _scale_box(detected.box, analysis_size, original_size)
    full_mask = detected.full_mask.resize(original_size, Image.Resampling.LANCZOS)
    component = detected.component_mask.resize(original_size, Image.Resampling.NEAREST)
    mask = full_mask.crop(scaled_box)
    sx = original_size[0] / analysis_size[0]
    sy = original_size[1] / analysis_size[1]
    seed = None if detected.seed is None else (round(detected.seed[0] * sx), round(detected.seed[1] * sy))
    centroid = None if detected.centroid is None else (detected.centroid[0] * sx, detected.centroid[1] * sy)
    return PortraitOpening(
        box=scaled_box,
        mask=mask,
        full_mask=full_mask,
        component_mask=component,
        adaptive=True,
        seed=seed,
        area=round(detected.area * sx * sy),
        centroid=centroid,
        touches_border=False,
        reason=detected.reason,
    )

def fit_portrait(
    source: Image.Image,
    size: tuple[int, int],
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    zoom: float = 1.0,
) -> Image.Image:
    """Cover-fit a portrait and pan it without exposing empty space."""
    image = ImageOps.exif_transpose(source).convert("RGB")
    if offset_x == 0.0 and offset_y == 0.0 and zoom == 1.0:
        return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
    scale = max(size[0] / image.width, size[1] / image.height) * zoom
    resized_size = (
        max(size[0], round(image.width * scale)),
        max(size[1], round(image.height * scale)),
    )
    resized = image.resize(resized_size, Image.Resampling.LANCZOS)
    overflow_x = resized.width - size[0]
    overflow_y = resized.height - size[1]
    left = round(overflow_x * (1.0 - offset_x) / 2.0)
    top = round(overflow_y * (1.0 - offset_y) / 2.0)
    left = max(0, min(overflow_x, left))
    top = max(0, min(overflow_y, top))
    return resized.crop((left, top, left + size[0], top + size[1]))


def portrait_layer(
    canvas_size: tuple[int, int],
    portrait_source: Image.Image,
    opening: PortraitOpening,
    *,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    zoom: float = 1.0,
) -> Image.Image:
    """Render one portrait through the supplied detected opening."""
    x1, y1, x2, y2 = opening.box
    portrait_size = (max(1, x2 - x1), max(1, y2 - y1))
    fitted = fit_portrait(portrait_source, portrait_size, offset_x, offset_y, zoom)
    mask = opening.mask
    if mask.size != portrait_size:
        mask = mask.resize(portrait_size, Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    layer.paste(fitted, (x1, y1), mask)
    return layer


__all__ = [
    "GRAVESTONE_RENDER_ANALYSIS_SIZE",
    "PortraitOpening",
    "detect_portrait_opening",
    "ellipse_mask",
    "fallback_portrait_opening",
    "fit_portrait",
    "portrait_layer",
]
