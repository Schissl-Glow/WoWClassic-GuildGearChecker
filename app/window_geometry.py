# -*- coding: utf-8 -*-
"""Small shared helpers for work-area aware Tk window geometry."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re


@dataclass(frozen=True)
class WorkArea:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True)
class WindowGeometry:
    width: int
    height: int
    x: int
    y: int

    def as_tk(self) -> str:
        return f"{self.width}x{self.height}{self.x:+d}{self.y:+d}"


GEOMETRY_PATTERN = re.compile(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$")


def primary_work_area(root) -> WorkArea:
    """Return the Windows work area, falling back to Tk's current screen."""
    try:
        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            if width > 0 and height > 0:
                return WorkArea(int(rect.left), int(rect.top), width, height)
    except (AttributeError, OSError):
        pass
    return WorkArea(0, 0, max(1, int(root.winfo_screenwidth())),
                    max(1, int(root.winfo_screenheight())))


def work_area_for_geometry(root, saved: object) -> WorkArea:
    """Use the work area of the Windows monitor containing a saved window."""
    parsed = parse_geometry(saved)
    if parsed is not None:
        try:
            rect = wintypes.RECT(
                parsed.x, parsed.y, parsed.x + parsed.width, parsed.y + parsed.height,
            )
            monitor = ctypes.windll.user32.MonitorFromRect(ctypes.byref(rect), 0)
            if monitor:
                class MonitorInfo(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
                    ]
                info = MonitorInfo()
                info.cbSize = ctypes.sizeof(info)
                if ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    work = info.rcWork
                    return WorkArea(
                        int(work.left), int(work.top),
                        int(work.right - work.left), int(work.bottom - work.top),
                    )
        except (AttributeError, OSError):
            pass
    return primary_work_area(root)


def parse_geometry(value: object) -> WindowGeometry | None:
    match = GEOMETRY_PATTERN.fullmatch(str(value or "").strip())
    if not match:
        return None
    width, height, x, y = map(int, match.groups())
    return WindowGeometry(width, height, x, y)


def default_geometry(work_area: WorkArea, width_ratio: float = 0.85,
                     height_ratio: float = 0.89) -> WindowGeometry:
    width = min(work_area.width, max(1, round(work_area.width * width_ratio)))
    height = min(work_area.height, max(1, round(work_area.height * height_ratio)))
    x = work_area.x + (work_area.width - width) // 2
    y = work_area.y + (work_area.height - height) // 2
    return WindowGeometry(width, height, x, y)


def geometry_is_usable(geometry: WindowGeometry | None, work_area: WorkArea,
                       minimum: tuple[int, int]) -> bool:
    if geometry is None:
        return False
    if geometry.width < minimum[0] or geometry.height < minimum[1]:
        return False
    if geometry.width > work_area.width or geometry.height > work_area.height:
        return False
    overlap_width = max(0, min(geometry.x + geometry.width, work_area.right)
                        - max(geometry.x, work_area.x))
    overlap_height = max(0, min(geometry.y + geometry.height, work_area.bottom)
                         - max(geometry.y, work_area.y))
    return overlap_width >= min(160, geometry.width) and overlap_height >= min(100, geometry.height)


def resolve_geometry(saved: object, work_area: WorkArea,
                     minimum: tuple[int, int]) -> WindowGeometry:
    parsed = parse_geometry(saved)
    return parsed if geometry_is_usable(parsed, work_area, minimum) else default_geometry(work_area)


def dynamic_minimum(work_area: WorkArea, preferred: tuple[int, int],
                    floor: tuple[int, int]) -> tuple[int, int]:
    width = max(floor[0], min(preferred[0], work_area.width))
    height = max(floor[1], min(preferred[1], work_area.height))
    return (min(width, work_area.width), min(height, work_area.height))


def read_suite_settings(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def update_suite_settings(path: Path, **values) -> None:
    path = Path(path)
    data = read_suite_settings(path)
    data.update(values)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
