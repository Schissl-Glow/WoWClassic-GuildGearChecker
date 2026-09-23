"""Focused alpha/opening editor for non-productive gravestone review files."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageTk

from app.gravestone_portrait import detect_portrait_opening, portrait_layer
from app.i18n import tr
from app.gravestone_categories import (
    load_gravestone_text_safe_area,
    save_gravestone_text_safe_area,
)

try:
    from .gravestone_review_core import (
        GeometryConfig,
        OpeningAnalysis,
        opening_transparency_metrics,
    )
except ImportError:  # Standalone script execution
    from gravestone_review_core import (
        GeometryConfig,
        OpeningAnalysis,
        opening_transparency_metrics,
    )


class AlphaMaskSession:
    """In-memory, undoable edits to one PNG alpha channel."""

    def __init__(self, image: Image.Image, ellipse_bbox: tuple[int, int, int, int],
                 text_safe_area: tuple[int, int, int, int]):
        self.original = image.convert("RGBA")
        self.image = self.original.copy()
        self.original_alpha = self.original.getchannel("A")
        self.ellipse_bbox = tuple(int(value) for value in ellipse_bbox)
        self.text_safe_area = tuple(int(value) for value in text_safe_area)
        self.undo_stack: list[tuple[Image.Image, tuple[int, int, int, int], tuple[int, int, int, int]]] = []
        self.redo_stack: list[tuple[Image.Image, tuple[int, int, int, int], tuple[int, int, int, int]]] = []

    def checkpoint(self) -> None:
        self.undo_stack.append((self.image.getchannel("A").copy(), self.ellipse_bbox, self.text_safe_area))
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _restore_state(self, state) -> None:
        alpha, self.ellipse_bbox, self.text_safe_area = state
        self.image.putalpha(alpha.copy())

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        current = (self.image.getchannel("A").copy(), self.ellipse_bbox, self.text_safe_area)
        self.redo_stack.append(current)
        self._restore_state(self.undo_stack.pop())
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        current = (self.image.getchannel("A").copy(), self.ellipse_bbox, self.text_safe_area)
        self.undo_stack.append(current)
        self._restore_state(self.redo_stack.pop())
        return True

    def apply_ellipse(self, bbox: tuple[int, int, int, int], feather: int = 2) -> None:
        self.checkpoint()
        x1, y1, x2, y2 = (int(value) for value in bbox)
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        x1 = max(0, min(self.image.width - 1, x1))
        y1 = max(0, min(self.image.height - 1, y1))
        x2 = max(x1 + 1, min(self.image.width, x2))
        y2 = max(y1 + 1, min(self.image.height, y2))
        previous_bbox = self.ellipse_bbox
        # The source already contains the former transparent opening.  Merely
        # erasing a second ellipse leaves both openings transparent; the
        # detector then commonly keeps selecting the old, central opening.
        # Close the known previous opening first so drawing/moving the master
        # mask actually replaces it.
        if previous_bbox != (x1, y1, x2, y2):
            self._restore_ellipse(previous_bbox, feather)
        self.ellipse_bbox = (x1, y1, x2, y2)
        self._erase_ellipse(self.ellipse_bbox, feather)

    def _erase_ellipse(self, bbox: tuple[int, int, int, int], feather: int) -> None:
        erase = Image.new("L", self.image.size, 0)
        ImageDraw.Draw(erase).ellipse(bbox, fill=255)
        if feather > 0:
            erase = erase.filter(ImageFilter.GaussianBlur(float(feather)))
        alpha = ImageChops.darker(self.image.getchannel("A"), ImageOps.invert(erase))
        self.image.putalpha(alpha)

    def _restore_ellipse(self, bbox: tuple[int, int, int, int], feather: int) -> None:
        """Close the prior editable opening before replacing it elsewhere."""
        restore = Image.new("L", self.image.size, 0)
        ImageDraw.Draw(restore).ellipse(bbox, fill=255)
        if feather > 0:
            restore = restore.filter(ImageFilter.GaussianBlur(float(feather)))
        alpha = ImageChops.lighter(self.image.getchannel("A"), restore)
        self.image.putalpha(alpha)

    def move_ellipse(self, dx: int, dy: int, feather: int = 2) -> None:
        x1, y1, x2, y2 = self.ellipse_bbox
        width, height = x2 - x1, y2 - y1
        nx1 = max(0, min(self.image.width - width, x1 + int(dx)))
        ny1 = max(0, min(self.image.height - height, y1 + int(dy)))
        self.apply_ellipse((nx1, ny1, nx1 + width, ny1 + height), feather)

    def set_text_safe_area(self, bbox: tuple[int, int, int, int]) -> None:
        self.checkpoint()
        x1, y1, x2, y2 = (int(value) for value in bbox)
        x1, x2 = sorted((max(0, x1), min(self.image.width, x2)))
        y1, y2 = sorted((max(0, y1), min(self.image.height, y2)))
        self.text_safe_area = (x1, y1, max(x1 + 24, x2), max(y1 + 24, y2))

    def move_text_safe_area(self, dx: int, dy: int) -> None:
        x1, y1, x2, y2 = self.text_safe_area
        width, height = x2 - x1, y2 - y1
        nx1 = max(0, min(self.image.width - width, x1 + int(dx)))
        ny1 = max(0, min(self.image.height - height, y1 + int(dy)))
        self.set_text_safe_area((nx1, ny1, nx1 + width, ny1 + height))

    def clear_outer_border(self, pixels: int = 8) -> None:
        """Make only the outer alpha border transparent; RGB data is retained."""
        self.checkpoint()
        width, height = self.image.size
        border = max(1, min(int(pixels), width // 2, height // 2))
        alpha = self.image.getchannel("A")
        draw = ImageDraw.Draw(alpha)
        draw.rectangle((0, 0, width - 1, border - 1), fill=0)
        draw.rectangle((0, height - border, width - 1, height - 1), fill=0)
        draw.rectangle((0, 0, border - 1, height - 1), fill=0)
        draw.rectangle((width - border, 0, width - 1, height - 1), fill=0)
        self.image.putalpha(alpha)

    def brush(self, x: int, y: int, radius: int, *, restore: bool, feather: int = 1) -> None:
        brush = Image.new("L", self.image.size, 0)
        ImageDraw.Draw(brush).ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
        if feather > 0:
            brush = brush.filter(ImageFilter.GaussianBlur(float(feather)))
        alpha = self.image.getchannel("A")
        if restore:
            restored = Image.composite(self.original_alpha, alpha, brush)
            self.image.putalpha(restored)
        else:
            self.image.putalpha(ImageChops.darker(alpha, ImageOps.invert(brush)))


def save_alpha_edit_atomic(image: Image.Image, target: Path, backup_dir: Path) -> Path:
    """Back up and atomically replace one review PNG."""
    target = Path(target)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = backup_dir / f"{target.stem}_{stamp}.png"
    with Image.open(target) as source:
        source.save(backup, format="PNG")
    temporary = target.with_name(f".{target.stem}.alpha-edit.tmp.png")
    try:
        image.save(temporary, format="PNG")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return backup


class AlphaEditorDialog:
    """Small modal editor for ellipse and brush-based alpha correction."""

    def __init__(
        self,
        parent: tk.Misc,
        image_path: Path,
        geometry: GeometryConfig,
        portrait: Image.Image | None,
        portrait_transform: tuple[float, float, float],
        backup_dir: Path,
        on_saved,
    ):
        self.path = Path(image_path)
        self.geometry = geometry
        self.portrait = portrait.copy() if portrait is not None else None
        self.portrait_transform = tuple(float(value) for value in portrait_transform)
        self.backup_dir = Path(backup_dir)
        self.on_saved = on_saved
        with Image.open(self.path) as source:
            image = source.convert("RGBA")
        portrait_bbox = geometry.scale_box(geometry.portrait_bbox, image.size)
        opening = detect_portrait_opening(image, portrait_bbox)
        text_safe_area = load_gravestone_text_safe_area(self.path, image.size) or geometry.text_safe_area
        self.session = AlphaMaskSession(image, opening.box, text_safe_area)
        self.window = tk.Toplevel(parent)
        self.window.title(tr("alpha_editor.title", name=self.path.name))
        self.window.geometry("1040x850")
        self.window.minsize(820, 650)
        self.mode_var = tk.StringVar(value="ellipse")
        self.preview_var = tk.StringVar(value="Öffnung prüfen")
        self.brush_var = tk.IntVar(value=24)
        self.feather_var = tk.IntVar(value=2)
        self.status_var = tk.StringVar(value=tr("alpha_editor.status_initial"))
        self.photo: ImageTk.PhotoImage | None = None
        self._display_scale = 1.0
        self._drag_start: tuple[int, int] | None = None
        self._move_origin: tuple[int, int, int, int] | None = None
        self._stroke_active = False
        self._refresh_after_id: str | None = None
        self._checkerboard_cache: dict[tuple[tuple[int, int], int], Image.Image] = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.window, padding=8)
        toolbar.pack(fill="x")
        for text, value in (
            (tr("alpha_editor.mode_draw_ellipse"), "ellipse"),
            (tr("alpha_editor.mode_move_ellipse"), "move"),
            (tr("alpha_editor.mode_erase"), "erase"),
            (tr("alpha_editor.mode_restore"), "restore"),
            (tr("alpha_editor.mode_text_resize"), "text_resize"),
            (tr("alpha_editor.mode_text_move"), "text_move"),
        ):
            ttk.Radiobutton(toolbar, text=text, value=value, variable=self.mode_var, style="Toolbutton").pack(side="left", padx=(0, 5))
        ttk.Button(toolbar, text=tr("alpha_editor.undo"), command=self._undo).pack(side="left", padx=(8, 3))
        ttk.Button(toolbar, text=tr("alpha_editor.redo"), command=self._redo).pack(side="left")

        controls = ttk.Frame(self.window, padding=(8, 0, 8, 6))
        controls.pack(fill="x")
        ttk.Label(controls, text=tr("alpha_editor.brush")).pack(side="left")
        ttk.Scale(controls, from_=4, to=80, variable=self.brush_var, orient="horizontal", length=140).pack(side="left", padx=(4, 12))
        ttk.Label(controls, text=tr("alpha_editor.feather")).pack(side="left")
        ttk.Scale(controls, from_=0, to=10, variable=self.feather_var, orient="horizontal", length=120).pack(side="left", padx=(4, 12))
        for text, value in ((tr("alpha_editor.opening_check"), "Öffnung prüfen"), (tr("alpha_editor.composite"), "Zusammengesetzt")):
            ttk.Radiobutton(controls, text=text, value=value, variable=self.preview_var, command=self.refresh).pack(side="left", padx=(0, 5))
        ttk.Button(
            controls,
            text=tr("alpha_editor.clear_outer_border"),
            command=self._clear_outer_border,
        ).pack(side="left", padx=(10, 0))

        self.canvas = tk.Canvas(self.window, background="#161619", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=4)
        self.canvas.bind("<Configure>", lambda _event: self.refresh())
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)

        footer = ttk.Frame(self.window, padding=8)
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.status_var).pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text=tr("common.cancel"), command=self.window.destroy).pack(side="right")
        ttk.Button(footer, text=tr("alpha_editor.apply_save"), command=self._save).pack(side="right", padx=(0, 8))

    def _canvas_to_image(self, event: tk.Event) -> tuple[int, int]:
        return (
            max(0, min(self.session.image.width - 1, round(event.x / self._display_scale))),
            max(0, min(self.session.image.height - 1, round(event.y / self._display_scale))),
        )

    def _press(self, event: tk.Event) -> None:
        point = self._canvas_to_image(event)
        self._drag_start = point
        mode = self.mode_var.get()
        if mode == "move":
            self._move_origin = self.session.ellipse_bbox
        elif mode == "text_move":
            self._move_origin = self.session.text_safe_area
        elif mode in {"erase", "restore"}:
            self.session.checkpoint()
            self._stroke_active = True
            self._paint(point)

    def _motion(self, event: tk.Event) -> None:
        if self._drag_start is None:
            return
        point = self._canvas_to_image(event)
        mode = self.mode_var.get()
        if mode in {"erase", "restore"} and self._stroke_active:
            self._paint(point)
        elif mode == "ellipse":
            self._draw_preview_box((*self._drag_start, *point))
        elif mode == "move" and self._move_origin is not None:
            dx, dy = point[0] - self._drag_start[0], point[1] - self._drag_start[1]
            x1, y1, x2, y2 = self._move_origin
            self._draw_preview_box((x1 + dx, y1 + dy, x2 + dx, y2 + dy))
        elif mode == "text_resize":
            self._draw_preview_text_box((*self._drag_start, *point))
        elif mode == "text_move" and self._move_origin is not None:
            dx, dy = point[0] - self._drag_start[0], point[1] - self._drag_start[1]
            x1, y1, x2, y2 = self._move_origin
            self._draw_preview_text_box((x1 + dx, y1 + dy, x2 + dx, y2 + dy))

    def _release(self, event: tk.Event) -> None:
        if self._drag_start is None:
            return
        point = self._canvas_to_image(event)
        mode = self.mode_var.get()
        if mode == "ellipse":
            if abs(point[0] - self._drag_start[0]) >= 12 and abs(point[1] - self._drag_start[1]) >= 12:
                self.session.apply_ellipse((*self._drag_start, *point), self.feather_var.get())
        elif mode == "move" and self._move_origin is not None:
            self.session.ellipse_bbox = self._move_origin
            self.session.move_ellipse(
                point[0] - self._drag_start[0], point[1] - self._drag_start[1], self.feather_var.get()
            )
        elif mode == "text_resize":
            self.session.set_text_safe_area((*self._drag_start, *point))
        elif mode == "text_move" and self._move_origin is not None:
            self.session.text_safe_area = self._move_origin
            self.session.move_text_safe_area(point[0] - self._drag_start[0], point[1] - self._drag_start[1])
        self._drag_start = None
        self._move_origin = None
        self._stroke_active = False
        if self._refresh_after_id is not None:
            try:
                self.window.after_cancel(self._refresh_after_id)
            except (tk.TclError, ValueError):
                pass
            self._refresh_after_id = None
        self.refresh()

    def _paint(self, point: tuple[int, int]) -> None:
        self.session.brush(
            point[0], point[1], max(2, self.brush_var.get()),
            restore=self.mode_var.get() == "restore", feather=self.feather_var.get(),
        )
        # Brush motion can generate hundreds of events per second.  Coalesce them
        # to roughly 30 FPS; the exact full-resolution alpha data is still edited
        # immediately and the final release event performs an exact refresh.
        if self._refresh_after_id is None:
            self._refresh_after_id = self.window.after(33, self._finish_scheduled_refresh)

    def _finish_scheduled_refresh(self) -> None:
        self._refresh_after_id = None
        if self.window.winfo_exists():
            self.refresh()

    def _undo(self) -> None:
        if self.session.undo():
            self.refresh()

    def _redo(self) -> None:
        if self.session.redo():
            self.refresh()

    def _clear_outer_border(self) -> None:
        self.session.clear_outer_border(self.geometry.edge_clear_px)
        self.status_var.set(
            tr("alpha_editor.outer_border_cleared", pixels=self.geometry.edge_clear_px)
        )
        self.refresh()

    def _render_source(self) -> tuple[Image.Image, OpeningAnalysis]:
        image = self.session.image
        portrait_bbox = self.geometry.scale_box(self.geometry.portrait_bbox, image.size)
        opening = detect_portrait_opening(image, portrait_bbox)
        analysis = OpeningAnalysis(
            opening.adaptive, opening.seed, opening.full_mask, opening.box,
            area=opening.area, centroid=opening.centroid, notes=[opening.reason],
        )
        checker = self._checkerboard(image.size, 28)
        if self.preview_var.get() == "Zusammengesetzt" and self.portrait is not None:
            checker.alpha_composite(
                portrait_layer(
                    image.size,
                    self.portrait,
                    opening,
                    offset_x=self.portrait_transform[0],
                    offset_y=self.portrait_transform[1],
                    zoom=self.portrait_transform[2],
                )
            )
        checker.alpha_composite(image)
        metrics = opening_transparency_metrics(image, analysis)
        if self.preview_var.get() == "Öffnung prüfen":
            edge = metrics.expected_mask.filter(ImageFilter.FIND_EDGES)
            green = Image.new("RGBA", image.size, (35, 255, 95, 0))
            green.putalpha(edge.point(lambda value: 220 if value else 0))
            checker.alpha_composite(green)
            magenta = Image.new("RGBA", image.size, (255, 0, 190, 0))
            magenta.putalpha(metrics.problem_mask.point(lambda value: 190 if value else 0))
            checker.alpha_composite(magenta)
        return checker, analysis

    def _checkerboard(self, size: tuple[int, int], cell: int) -> Image.Image:
        key = (tuple(size), int(cell))
        cached = self._checkerboard_cache.get(key)
        if cached is not None:
            return cached.copy()
        image = Image.new("RGBA", size, (210, 210, 210, 255))
        draw = ImageDraw.Draw(image)
        for y in range(0, size[1], cell):
            for x in range(0, size[0], cell):
                color = (150, 150, 150, 255) if (x // cell + y // cell) % 2 else (210, 210, 210, 255)
                draw.rectangle((x, y, x + cell, y + cell), fill=color)
        self._checkerboard_cache[key] = image
        return image.copy()

    def _draw_preview_box(self, bbox: tuple[int, int, int, int]) -> None:
        # During dragging only the guide changes.  Re-running opening detection,
        # masks and full image scaling for every mouse event made the editor laggy.
        self.canvas.delete("edit-guide")
        scaled = tuple(round(value * self._display_scale) for value in bbox)
        self.canvas.create_oval(*scaled, outline="#ffe13b", width=3, tags="edit-guide")

    def _draw_preview_text_box(self, bbox: tuple[int, int, int, int]) -> None:
        self.canvas.delete("edit-guide")
        scaled = tuple(round(value * self._display_scale) for value in bbox)
        self.canvas.create_rectangle(*scaled, outline="#56d9ff", width=3, tags="edit-guide")

    def refresh(self) -> None:
        image, _analysis = self._render_source()
        width = max(300, self.canvas.winfo_width() - 8)
        height = max(300, self.canvas.winfo_height() - 8)
        self._display_scale = min(width / image.width, height / image.height)
        display = image.resize(
            (max(1, round(image.width * self._display_scale)), max(1, round(image.height * self._display_scale))),
            Image.Resampling.LANCZOS,
        )
        self.photo = ImageTk.PhotoImage(display)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        bbox = tuple(round(value * self._display_scale) for value in self.session.ellipse_bbox)
        self.canvas.create_oval(*bbox, outline="#ffe13b", width=2)
        text_bbox = tuple(round(value * self._display_scale) for value in self.session.text_safe_area)
        self.canvas.create_rectangle(*text_bbox, outline="#56d9ff", width=2)

    def _save(self) -> None:
        if not messagebox.askyesno(
            tr("alpha_editor.save_title"),
            tr("alpha_editor.save_question"),
            parent=self.window,
        ):
            return
        try:
            backup = save_alpha_edit_atomic(self.session.image, self.path, self.backup_dir)
            save_gravestone_text_safe_area(self.path, self.session.text_safe_area, self.session.image.size)
            self.on_saved(self.path)
            self.status_var.set(tr("alpha_editor.saved_backup", name=backup.name))
            self.window.destroy()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(tr("alpha_editor.save_failed"), str(exc), parent=self.window)


__all__ = ["AlphaMaskSession", "AlphaEditorDialog", "save_alpha_edit_atomic"]
