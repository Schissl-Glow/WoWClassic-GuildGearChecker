# -*- coding: utf-8 -*-
"""
Guild Portrait Grabber v0.1.2
---------------------------
Separate helper tool for creating character portraits from ClassicWoWArmory.
Designed for Windows + Miniforge/Python 3.12.

Key design goals:
- No Blizzard or Warcraft Logs API key required.
- Uses a real browser session (Microsoft Edge preferred) via Playwright.
- Supports visible/manual positioning of the 3D model before capture.
- Tries to find the 3D viewer/canvas automatically.
- One-time crop calibration can be reused for all portraits.
- Imports names from TXT, Warcraft Logs CSV, and Guild Gear Checker .ggc files.
- Never modifies the .ggc file it imports.
"""

from __future__ import annotations

import csv
import io
import json
import os
import queue
import re
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageTk
except Exception:  # pragma: no cover - handled by startup checks
    Image = None
    ImageTk = None

APP_NAME = "Guild Portrait Grabber"
APP_VERSION = "0.1.2"
DEFAULT_REGION = "EU"
DEFAULT_REALM = "stitches"
DEFAULT_GAME_VERSION = "classic1x"
PORTRAIT_WIDTH = 384
PORTRAIT_HEIGHT = 672

SEED_NAMES = [
    "Aba", "Albinoanton", "Burgûs", "Bífi", "Dirksson", "Gigagenossin",
    "Gullinborsti", "Janos", "Kolben", "Opine", "Schlübbeer", "Schneeflocke",
    "Soregdrei", "Sysem", "Tiberior", "Varnika", "Venog", "Wariwariluke",
    "Zwirrlin", "Ánníe",
]

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "GuildPortraitGrabber"
    return Path.home() / ".guild_portrait_grabber"


def default_output_dir() -> Path:
    # Keep portraits next to the script by default, which makes it easy to copy
    # the whole folder to another PC or integrate it with Guild Gear Checker.
    return Path(__file__).resolve().parent / "portraits"


def build_armory_url(name: str, region: str = DEFAULT_REGION,
                     realm: str = DEFAULT_REALM,
                     game_version: str = DEFAULT_GAME_VERSION) -> str:
    name = name.strip()
    if not name:
        raise ValueError("Charaktername darf nicht leer sein.")
    return (
        "https://classicwowarmory.com/character/"
        f"{urllib.parse.quote(region.strip(), safe='')}/"
        f"{urllib.parse.quote(realm.strip(), safe='')}/"
        f"{urllib.parse.quote(name, safe='')}"
        f"?game_version={urllib.parse.quote(game_version.strip(), safe='')}"
    )


def safe_filename(name: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", name.strip()).rstrip(". ")
    return cleaned or "character"


def read_text_flexible(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def dedupe_names(names: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = str(raw).strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(name)
    return result


def parse_txt_names(path: Path) -> list[str]:
    text = read_text_flexible(path)
    return dedupe_names(line.strip() for line in text.splitlines())


def _sniff_dialect(text: str):
    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def parse_csv_names(path: Path) -> list[str]:
    text = read_text_flexible(path)
    dialect = _sniff_dialect(text)
    stream = io.StringIO(text)
    reader = csv.reader(stream, dialect)
    rows = list(reader)
    if not rows:
        return []

    header = [c.strip().lstrip("\ufeff") for c in rows[0]]
    name_col: Optional[int] = None
    for i, col in enumerate(header):
        if col.casefold() == "name":
            name_col = i
            break

    start = 1 if name_col is not None else 0
    if name_col is None:
        name_col = 0

    names: list[str] = []
    for row in rows[start:]:
        if name_col < len(row):
            value = row[name_col].strip()
            if value:
                names.append(value)
    return dedupe_names(names)


def parse_ggc_names(path: Path, active_only: bool = True) -> list[str]:
    text = read_text_flexible(path)
    obj = json.loads(text)
    members = obj.get("members") if isinstance(obj, dict) else None
    if not isinstance(members, list):
        raise ValueError("Keine gueltige Guild-Gear-Checker-Projektdatei: 'members' fehlt.")

    names: list[str] = []
    for member in members:
        if not isinstance(member, dict):
            continue
        if active_only and str(member.get("lifeStatus", "active")).casefold() == "dead":
            continue
        name = str(member.get("name", "")).strip()
        if name:
            names.append(name)
    return dedupe_names(names)


def load_names_from_file(path: Path, active_only: bool = True) -> list[str]:
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        return parse_csv_names(path)
    if suffix == ".ggc":
        return parse_ggc_names(path, active_only=active_only)
    return parse_txt_names(path)


def clamp_crop(crop: dict) -> dict:
    # Default crop tuned for a taller in-game portrait similar to the user's example:
    # full head, shoulders, torso and upper legs with little empty side margin.
    defaults = {"x1": 0.30, "y1": 0.05, "x2": 0.70, "y2": 0.86}
    out = {}
    for key, default in defaults.items():
        try:
            out[key] = min(1.0, max(0.0, float(crop.get(key, default))))
        except Exception:
            out[key] = default
    if out["x2"] <= out["x1"] + 0.02 or out["y2"] <= out["y1"] + 0.02:
        return defaults.copy()
    return out


def crop_portrait(source: Path, destination: Path, crop: dict,
                  width: int = PORTRAIT_WIDTH, height: int = PORTRAIT_HEIGHT) -> None:
    if Image is None:
        raise RuntimeError("Pillow ist nicht installiert.")
    crop = clamp_crop(crop)
    with Image.open(source) as im:
        im = im.convert("RGB")
        w, h = im.size
        x1 = int(round(crop["x1"] * w))
        y1 = int(round(crop["y1"] * h))
        x2 = int(round(crop["x2"] * w))
        y2 = int(round(crop["y2"] * h))
        x1, y1 = max(0, min(w - 1, x1)), max(0, min(h - 1, y1))
        x2, y2 = max(x1 + 1, min(w, x2)), max(y1 + 1, min(h, y2))
        cut = im.crop((x1, y1, x2, y2))

        # Fit the chosen crop to the target portrait ratio without distortion.
        target_ratio = width / height
        cw, ch = cut.size
        current_ratio = cw / ch if ch else target_ratio
        if current_ratio > target_ratio:
            new_w = max(1, int(round(ch * target_ratio)))
            left = max(0, (cw - new_w) // 2)
            cut = cut.crop((left, 0, left + new_w, ch))
        elif current_ratio < target_ratio:
            new_h = max(1, int(round(cw / target_ratio)))
            top = max(0, (ch - new_h) // 2)
            cut = cut.crop((0, top, cw, top + new_h))

        resampling = getattr(Image, "Resampling", Image).LANCZOS
        cut = cut.resize((width, height), resampling)
        destination.parent.mkdir(parents=True, exist_ok=True)
        cut.save(destination, format="PNG", optimize=True)


def image_has_detail(path: Path) -> bool:
    """Reject obviously blank/solid screenshots (e.g. failed WebGL canvas capture)."""
    if Image is None:
        return True
    try:
        with Image.open(path) as im:
            gray = im.convert("L").resize((64, 64))
            lo, hi = gray.getextrema()
            return (hi - lo) >= 8
    except Exception:
        return False


def config_path() -> Path:
    return app_data_dir() / "config.json"


def load_config() -> dict:
    defaults = {
        "region": DEFAULT_REGION,
        "realm": DEFAULT_REALM,
        "game_version": DEFAULT_GAME_VERSION,
        "output_dir": str(default_output_dir()),
        "crop": clamp_crop({}),
        "browser_channel": "msedge",
        "wait_after_load": 3.0,
    }
    path = config_path()
    try:
        obj = json.loads(read_text_flexible(path))
        if isinstance(obj, dict):
            defaults.update(obj)
    except Exception:
        pass
    defaults["crop"] = clamp_crop(defaults.get("crop", {}))
    return defaults


def save_config(config: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class BrowserCommand:
    action: str
    payload: dict


class BrowserWorker(threading.Thread):
    """Owns all Playwright objects in one dedicated thread."""

    def __init__(self, event_queue: queue.Queue):
        super().__init__(daemon=True)
        self.commands: queue.Queue[BrowserCommand] = queue.Queue()
        self.events = event_queue
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._running = True
        self._browser_name = ""

    def emit(self, kind: str, **payload) -> None:
        self.events.put({"type": kind, **payload})

    def submit(self, action: str, **payload) -> None:
        self.commands.put(BrowserCommand(action, payload))

    def _format_error(self, exc: BaseException) -> str:
        text = str(exc).strip()
        if text:
            return f"{type(exc).__name__}: {text}"
        return type(exc).__name__ or "Unbekannter Fehler"

    def _write_error_log(self, context: str, exc: BaseException) -> Path:
        path = app_data_dir() / "fehler.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        detail = traceback.format_exc()
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(f"\n===== {stamp} | {context} =====\n")
                f.write(self._format_error(exc) + "\n")
                f.write(detail + "\n")
        except Exception:
            pass
        return path

    def run(self) -> None:  # pragma: no cover - browser thread needs GUI/browser
        while self._running:
            try:
                cmd = self.commands.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                if cmd.action == "stop":
                    self._running = False
                    self._close_browser()
                    break
                if cmd.action == "test_browser":
                    self._test_browser(**cmd.payload)
                elif cmd.action == "open":
                    self._open_character(**cmd.payload)
                elif cmd.action == "capture":
                    self._capture_character(**cmd.payload)
                elif cmd.action == "capture_raw":
                    self._capture_raw_character(**cmd.payload)
                elif cmd.action == "capture_all":
                    self._capture_all(**cmd.payload)
            except Exception as exc:
                log_path = self._write_error_log(cmd.action, exc)
                self.emit(
                    "error",
                    message=self._format_error(exc),
                    detail=traceback.format_exc(),
                    log_path=str(log_path),
                )

    def _browser_is_healthy(self) -> bool:
        try:
            if self._browser is None or not self._browser.is_connected():
                return False
            if self._context is None:
                return False
            if self._page is not None and not self._page.is_closed():
                return True
            pages = [p for p in self._context.pages if not p.is_closed()]
            if pages:
                self._page = pages[0]
                self._page.set_default_timeout(12_000)
                return True
            self._page = self._context.new_page()
            self._page.set_default_timeout(12_000)
            return True
        except Exception:
            return False

    def _ensure_browser(self, preferred_channel: str = "msedge") -> None:
        # v0.1.1 intentionally uses a normal Playwright browser/context instead of
        # launch_persistent_context. This avoids stale profile locks and makes
        # recovery after manually closing Edge much more reliable.
        if self._browser_is_healthy():
            return

        self._close_browser()
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError(
                "Playwright ist nicht installiert. Bitte INSTALLIEREN.bat ausfuehren."
            ) from exc

        self._playwright = sync_playwright().start()
        attempts = []
        # Fixed robust order requested for this project: Edge -> Chrome -> bundled Chromium.
        candidates = [
            ("msedge", "Microsoft Edge"),
            ("chrome", "Google Chrome"),
            (None, "Playwright Chromium"),
        ]

        for channel, label in candidates:
            browser = None
            try:
                kwargs = {"headless": False}
                if channel:
                    kwargs["channel"] = channel
                browser = self._playwright.chromium.launch(**kwargs)
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = context.new_page()
                page.set_default_timeout(12_000)
                # Local smoke test: proves that the browser/context/page are really usable.
                page.set_content("<html><body><h1>Guild Portrait Grabber</h1></body></html>")
                if "Guild Portrait Grabber" not in page.locator("body").inner_text(timeout=3_000):
                    raise RuntimeError("Browser-Seite konnte nicht initialisiert werden.")

                self._browser = browser
                self._context = context
                self._page = page
                self._browser_name = label
                self.emit("browser_ready", browser=label)
                return
            except Exception as exc:
                attempts.append(f"{label}: {self._format_error(exc)}")
                try:
                    if browser is not None:
                        browser.close()
                except Exception:
                    pass
                self._browser = None
                self._context = None
                self._page = None

        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = None
        raise RuntimeError(
            "Kein nutzbarer Browser konnte gestartet werden. "
            "Reihenfolge: Microsoft Edge, Google Chrome, Playwright Chromium.\n\n"
            + "\n\n".join(attempts)
        )

    def _test_browser(self, preferred_channel: str = "msedge", **_unused) -> None:
        self.emit("progress", message="Teste Microsoft Edge / Browsersteuerung …")
        self._ensure_browser(preferred_channel)
        if not self._browser_is_healthy() or self._page is None:
            raise RuntimeError("Browser wurde gestartet, ist aber nicht steuerbar.")
        self._page.set_content(
            "<html><body style='font-family:sans-serif'><h1>Browser-Test OK</h1>"
            "<p>Playwright kann diesen Browser steuern.</p></body></html>"
        )
        text = self._page.locator("body").inner_text(timeout=3_000)
        if "Browser-Test OK" not in text:
            raise RuntimeError("Lokaler Browser-Funktionstest fehlgeschlagen.")
        self.emit("browser_test_ok", browser=self._browser_name)

    def _close_browser(self) -> None:
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._context = None
        self._browser = None
        self._playwright = None
        self._page = None
        self._browser_name = ""

    def _require_page(self):
        if not self._browser_is_healthy() or self._page is None:
            raise RuntimeError("Browser-Seite ist nicht verfügbar. Der Browser wird neu gestartet.")
        return self._page

    def _goto(self, name: str, region: str, realm: str, game_version: str,
              preferred_channel: str, wait_after_load: float) -> str:
        self._ensure_browser(preferred_channel)
        page = self._require_page()
        url = build_armory_url(name, region, realm, game_version)
        self.emit("progress", name=name, message=f"Oeffne {name} …")
        response = page.goto(url, wait_until="domcontentloaded", timeout=35_000)
        status = response.status if response is not None else None
        if status in (401, 403, 429):
            self.emit(
                "progress", name=name,
                message=f"HTTP {status}: Browser offen lassen; ggf. Schutzseite manuell bestaetigen."
            )
        try:
            page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass
        time.sleep(max(0.0, min(15.0, float(wait_after_load))))
        return url

    def _unlock_viewer(self) -> bool:
        page = self._require_page()
        candidates = [
            re.compile(r"click\s+to\s+unlock\s+the\s+3d\s+viewer", re.I),
            re.compile(r"unlock.*3d.*viewer", re.I),
            re.compile(r"3d\s+viewer", re.I),
        ]
        for rx in candidates:
            try:
                loc = page.get_by_text(rx).first
                if loc.count() and loc.is_visible():
                    loc.scroll_into_view_if_needed()
                    loc.click(timeout=5_000)
                    time.sleep(2.5)
                    return True
            except Exception:
                continue
        return False

    def _mark_best_viewer(self) -> bool:
        """Mark the most plausible visible viewer element with data-gpg-target=1."""
        page = self._require_page()
        script = r"""
        () => {
          document.querySelectorAll('[data-gpg-target="1"]').forEach(e => e.removeAttribute('data-gpg-target'));
          const selectors = [
            'canvas',
            '[class*="viewer" i]', '[id*="viewer" i]',
            '[class*="model" i]', '[id*="model" i]',
            '[class*="character" i] canvas', '[id*="character" i] canvas'
          ];
          const set = new Set();
          selectors.forEach(s => { try { document.querySelectorAll(s).forEach(e => set.add(e)); } catch (_) {} });
          let best = null, bestScore = 0;
          for (const e of set) {
            const r = e.getBoundingClientRect();
            const st = getComputedStyle(e);
            if (r.width < 180 || r.height < 220 || st.display === 'none' || st.visibility === 'hidden') continue;
            let score = r.width * r.height;
            if (e.tagName === 'CANVAS') score *= 4;
            const hint = ((e.id || '') + ' ' + (e.className || '')).toLowerCase();
            if (hint.includes('viewer') || hint.includes('model') || hint.includes('character')) score *= 1.7;
            if (score > bestScore) { best = e; bestScore = score; }
          }
          if (best) {
            best.setAttribute('data-gpg-target', '1');
            best.scrollIntoView({block:'center', inline:'center'});
            return {ok:true, tag:best.tagName, score:bestScore};
          }
          return {ok:false};
        }
        """
        try:
            result = page.evaluate(script)
            return bool(result and result.get("ok"))
        except Exception:
            return False

    def _raw_screenshot(self, name: str) -> tuple[Path, str]:
        page = self._require_page()
        self._unlock_viewer()
        time.sleep(1.5)
        found = self._mark_best_viewer()
        tmp_dir = app_data_dir() / "temp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        raw_path = tmp_dir / f"{safe_filename(name)}_raw.png"

        method = "viewport"
        if found:
            try:
                loc = page.locator('[data-gpg-target="1"]').first
                loc.scroll_into_view_if_needed()
                time.sleep(0.5)
                page.bring_to_front()
                loc.screenshot(path=str(raw_path), animations="disabled", timeout=15_000)
                if image_has_detail(raw_path):
                    method = "3D-Viewer/Canvas"
                    return raw_path, method
                self.emit("progress", name=name, message="Viewer-Screenshot war leer; nutze Viewport-Fallback …")
            except Exception:
                pass

        # Fallback: current viewport. This is intentionally still useful, because
        # the user can place/zoom the model manually in the visible browser.
        page.screenshot(path=str(raw_path), full_page=False, animations="disabled")
        return raw_path, method

    def _open_character(self, name: str, region: str, realm: str, game_version: str,
                        preferred_channel: str, wait_after_load: float) -> None:
        url = self._goto(name, region, realm, game_version, preferred_channel, wait_after_load)
        self._unlock_viewer()
        self.emit("opened", name=name, url=url)

    def _current_page_is_character(self, name: str, region: str, realm: str, game_version: str) -> bool:
        if self._page is None:
            return False
        try:
            is_closed = getattr(self._page, "is_closed", None)
            if callable(is_closed) and is_closed():
                return False
            expected = urllib.parse.urlparse(build_armory_url(name, region, realm, game_version))
            current = urllib.parse.urlparse(self._page.url)
            # Ignore query ordering and harmless extra parameters; the character path is decisive.
            return urllib.parse.unquote(current.path).casefold().rstrip("/") == urllib.parse.unquote(expected.path).casefold().rstrip("/")
        except Exception:
            return False

    def _capture_character(self, name: str, region: str, realm: str, game_version: str,
                           preferred_channel: str, wait_after_load: float,
                           output_dir: str, crop: dict, navigate: bool = True) -> None:
        self._ensure_browser(preferred_channel)
        # Preserve manual rotation/zoom if the correct character is already open.
        if navigate and not self._current_page_is_character(name, region, realm, game_version):
            self._goto(name, region, realm, game_version, preferred_channel, wait_after_load)
        raw_path, method = self._raw_screenshot(name)
        dest = Path(output_dir) / f"{safe_filename(name)}.png"
        crop_portrait(raw_path, dest, crop)
        self.emit("portrait_saved", name=name, path=str(dest), method=method)

    def _capture_raw_character(self, name: str, region: str, realm: str, game_version: str,
                               preferred_channel: str, wait_after_load: float,
                               navigate: bool = True) -> None:
        self._ensure_browser(preferred_channel)
        if navigate and not self._current_page_is_character(name, region, realm, game_version):
            self._goto(name, region, realm, game_version, preferred_channel, wait_after_load)
        raw_path, method = self._raw_screenshot(name)
        self.emit("raw_capture", name=name, path=str(raw_path), method=method)

    def _capture_all(self, names: list[str], region: str, realm: str, game_version: str,
                     preferred_channel: str, wait_after_load: float,
                     output_dir: str, crop: dict) -> None:
        total = len(names)
        failures = 0
        for idx, name in enumerate(names, 1):
            self.emit("batch_progress", index=idx, total=total, name=name)
            try:
                self._capture_character(
                    name=name, region=region, realm=realm, game_version=game_version,
                    preferred_channel=preferred_channel, wait_after_load=wait_after_load,
                    output_dir=output_dir, crop=crop, navigate=True,
                )
            except Exception as exc:
                failures += 1
                self.emit("item_error", name=name, message=str(exc))
        self.emit("batch_done", total=total, failures=failures)


class CropDialog(tk.Toplevel):
    def __init__(self, parent, image_path: Path, initial_crop: dict,
                 on_accept: Callable[[dict], None]):
        super().__init__(parent)
        self.title("Portrait-Ausschnitt kalibrieren")
        self.transient(parent)
        self.grab_set()
        self.on_accept = on_accept
        self.original = Image.open(image_path).convert("RGB")
        self.initial_crop = clamp_crop(initial_crop)
        self.selection = None
        self.start = None
        self.rect_id = None

        max_w, max_h = 1000, 700
        w, h = self.original.size
        scale = min(max_w / w, max_h / h, 1.0)
        self.display_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        self.display = self.original.resize(self.display_size)
        self.photo = ImageTk.PhotoImage(self.display)

        msg = (
            "Ziehe mit der Maus ein Rechteck um Gesicht/Kopfbereich. "
            "Der Ausschnitt wird auf ein vertikales Portrait zugeschnitten und als 384×672 gespeichert."
        )
        ttk.Label(self, text=msg, wraplength=900).pack(fill="x", padx=10, pady=(10, 6))
        self.canvas = tk.Canvas(self, width=self.display_size[0], height=self.display_size[1],
                                highlightthickness=1, highlightbackground="#555")
        self.canvas.pack(padx=10, pady=5)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self._draw_initial()

        row = ttk.Frame(self)
        row.pack(fill="x", padx=10, pady=10)
        ttk.Button(row, text="Standard", command=self._reset).pack(side="left")
        ttk.Button(row, text="Abbrechen", command=self.destroy).pack(side="right", padx=(5, 0))
        ttk.Button(row, text="Ausschnitt übernehmen", command=self._accept).pack(side="right")

    def _coords_from_crop(self, crop: dict):
        w, h = self.display_size
        return (crop["x1"] * w, crop["y1"] * h, crop["x2"] * w, crop["y2"] * h)

    def _draw_initial(self):
        self.selection = self._coords_from_crop(self.initial_crop)
        self._draw_rect()

    def _draw_rect(self):
        if self.rect_id is not None:
            self.canvas.delete(self.rect_id)
        if not self.selection:
            return
        x1, y1, x2, y2 = self.selection
        self.rect_id = self.canvas.create_rectangle(x1, y1, x2, y2, outline="yellow", width=3)

    def _press(self, event):
        self.start = (event.x, event.y)
        self.selection = (event.x, event.y, event.x, event.y)
        self._draw_rect()

    def _drag(self, event):
        if not self.start:
            return
        w, h = self.display_size
        x = max(0, min(w, event.x))
        y = max(0, min(h, event.y))
        self.selection = (self.start[0], self.start[1], x, y)
        self._draw_rect()

    def _release(self, event):
        self._drag(event)
        self.start = None

    def _reset(self):
        self.selection = self._coords_from_crop(clamp_crop({}))
        self._draw_rect()

    def _accept(self):
        if not self.selection:
            return
        x1, y1, x2, y2 = self.selection
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        w, h = self.display_size
        if (x2 - x1) < 10 or (y2 - y1) < 10:
            messagebox.showwarning("Ausschnitt", "Der markierte Bereich ist zu klein.", parent=self)
            return
        crop = clamp_crop({"x1": x1 / w, "y1": y1 / h, "x2": x2 / w, "y2": y2 / h})
        self.on_accept(crop)
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1180x760")
        self.minsize(980, 650)
        self.config_data = load_config()
        self.names = dedupe_names(SEED_NAMES)
        self.events: queue.Queue = queue.Queue()
        self.worker = BrowserWorker(self.events)
        self.worker.start()
        self.status_by_name: dict[str, str] = {}
        self._build_ui()
        self._populate_tree()
        self.after(100, self._poll_events)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        pad = {"padx": 8, "pady": 5}
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)

        ttk.Label(top, text="Region").grid(row=0, column=0, sticky="w")
        self.region_var = tk.StringVar(value=self.config_data.get("region", DEFAULT_REGION))
        ttk.Entry(top, textvariable=self.region_var, width=8).grid(row=1, column=0, **pad)

        ttk.Label(top, text="Realm").grid(row=0, column=1, sticky="w")
        self.realm_var = tk.StringVar(value=self.config_data.get("realm", DEFAULT_REALM))
        ttk.Entry(top, textvariable=self.realm_var, width=18).grid(row=1, column=1, **pad)

        ttk.Label(top, text="Game-Version").grid(row=0, column=2, sticky="w")
        self.game_var = tk.StringVar(value=self.config_data.get("game_version", DEFAULT_GAME_VERSION))
        ttk.Entry(top, textvariable=self.game_var, width=14).grid(row=1, column=2, **pad)

        ttk.Label(top, text="Portrait-Ordner").grid(row=0, column=3, sticky="w")
        self.output_var = tk.StringVar(value=self.config_data.get("output_dir", str(default_output_dir())))
        ttk.Entry(top, textvariable=self.output_var, width=48).grid(row=1, column=3, sticky="ew", **pad)
        ttk.Button(top, text="…", width=3, command=self._choose_output).grid(row=1, column=4, padx=(0, 8), pady=5)
        top.columnconfigure(3, weight=1)

        tool = ttk.Frame(self)
        tool.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Button(tool, text="Liste importieren", command=self._import_names).pack(side="left", padx=(0, 5))
        ttk.Button(tool, text="Warcraft-Logs-CSV laden", command=self._import_wcl_csv).pack(side="left", padx=5)
        ttk.Button(tool, text="Name hinzufügen", command=self._add_name).pack(side="left", padx=5)
        ttk.Button(tool, text="Entfernen", command=self._remove_selected).pack(side="left", padx=5)
        ttk.Separator(tool, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(tool, text="Browser testen", command=self._test_browser).pack(side="left", padx=5)
        ttk.Button(tool, text="Im Browser öffnen", command=self._open_selected).pack(side="left", padx=5)
        ttk.Button(tool, text="Portrait erstellen", command=self._capture_selected).pack(side="left", padx=5)
        ttk.Button(tool, text="Ausschnitt kalibrieren", command=self._calibrate_selected).pack(side="left", padx=5)
        ttk.Button(tool, text="Alle Portraits", command=self._capture_all).pack(side="left", padx=5)
        ttk.Button(tool, text="Portrait-Ordner öffnen", command=self._open_output_folder).pack(side="right")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        columns = ("name", "status", "portrait")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("name", text="Charakter")
        self.tree.heading("status", text="Status")
        self.tree.heading("portrait", text="Portrait-Datei")
        self.tree.column("name", width=220, anchor="w")
        self.tree.column("status", width=340, anchor="w")
        self.tree.column("portrait", width=520, anchor="w")
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self._open_selected())

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 5))
        self.status_var = tk.StringVar(value="Bereit. Für beste Ergebnisse zuerst einen Charakter öffnen, den Portrait-Ausschnitt kalibrieren oder ein Warcraft-Logs-CSV laden.")
        ttk.Label(bottom, textvariable=self.status_var, anchor="w").pack(fill="x")
        ttk.Label(
            bottom,
            text=("Tipp: Nutze bei Problemen zuerst 'Browser testen'. Microsoft Edge ist Standard; Chrome und "
                  "Playwright Chromium sind Fallbacks. Das sichtbare 3D-Modell kann vor dem Screenshot gedreht/gezoomt werden."),
            wraplength=1120,
            foreground="#555",
        ).pack(fill="x", pady=(4, 0))

    def _selected_name(self) -> Optional[str]:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Auswahl", "Bitte zuerst einen Charakter auswählen.")
            return None
        return self.tree.item(sel[0], "values")[0]

    def _common_payload(self) -> dict:
        self._save_settings()
        return {
            "region": self.region_var.get().strip() or DEFAULT_REGION,
            "realm": self.realm_var.get().strip() or DEFAULT_REALM,
            "game_version": self.game_var.get().strip() or DEFAULT_GAME_VERSION,
            "preferred_channel": self.config_data.get("browser_channel", "msedge"),
            "wait_after_load": float(self.config_data.get("wait_after_load", 3.0)),
        }

    def _save_settings(self):
        self.config_data["region"] = self.region_var.get().strip() or DEFAULT_REGION
        self.config_data["realm"] = self.realm_var.get().strip() or DEFAULT_REALM
        self.config_data["game_version"] = self.game_var.get().strip() or DEFAULT_GAME_VERSION
        self.config_data["output_dir"] = self.output_var.get().strip() or str(default_output_dir())
        self.config_data["crop"] = clamp_crop(self.config_data.get("crop", {}))
        save_config(self.config_data)

    def _populate_tree(self):
        existing_selection = self._selected_tree_name_no_dialog()
        for item in self.tree.get_children():
            self.tree.delete(item)
        output = Path(self.output_var.get() or default_output_dir())
        for name in sorted(self.names, key=str.casefold):
            portrait = output / f"{safe_filename(name)}.png"
            status = self.status_by_name.get(name)
            if not status:
                status = "Portrait vorhanden" if portrait.exists() else "Noch kein Portrait"
            item = self.tree.insert("", "end", values=(name, status, str(portrait) if portrait.exists() else ""))
            if name == existing_selection:
                self.tree.selection_set(item)

    def _selected_tree_name_no_dialog(self):
        sel = self.tree.selection() if hasattr(self, "tree") else ()
        return self.tree.item(sel[0], "values")[0] if sel else None

    def _choose_output(self):
        folder = filedialog.askdirectory(initialdir=self.output_var.get() or str(default_output_dir()))
        if folder:
            self.output_var.set(folder)
            self._save_settings()
            self._populate_tree()

    def _import_specific(self, title: str, filetypes, active_only: bool = True):
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        if not path:
            return
        try:
            p = Path(path)
            names = load_names_from_file(p, active_only=active_only)
            before = len(self.names)
            self.names = dedupe_names([*self.names, *names])
            added = len(self.names) - before
            self.status_var.set(f"Import: {len(names)} Namen erkannt, {added} neu hinzugefügt.")
            self._populate_tree()
        except Exception as exc:
            messagebox.showerror("Import fehlgeschlagen", str(exc))

    def _import_wcl_csv(self):
        self._import_specific(
            title="Warcraft-Logs-CSV importieren",
            filetypes=[
                ("Warcraft Logs CSV", "*.csv"),
                ("Alle Dateien", "*.*"),
            ],
            active_only=True,
        )

    def _import_names(self):
        # In .ggc projects, dead characters are excluded by default because
        # portraits are mainly meant for the current active guild roster.
        self._import_specific(
            title="Charakterliste importieren",
            filetypes=[
                ("Unterstützte Dateien", "*.txt *.csv *.ggc"),
                ("Guild Gear Checker", "*.ggc"),
                ("Warcraft Logs CSV", "*.csv"),
                ("Textdatei", "*.txt"),
                ("Alle Dateien", "*.*"),
            ],
            active_only=True,
        )

    def _add_name(self):
        dlg = tk.Toplevel(self)
        dlg.title("Charakter hinzufügen")
        dlg.transient(self)
        dlg.grab_set()
        ttk.Label(dlg, text="Charaktername:").pack(anchor="w", padx=12, pady=(12, 4))
        var = tk.StringVar()
        ent = ttk.Entry(dlg, textvariable=var, width=35)
        ent.pack(fill="x", padx=12)
        ent.focus_set()

        def add():
            name = var.get().strip()
            if not name:
                return
            self.names = dedupe_names([*self.names, name])
            self._populate_tree()
            dlg.destroy()

        ttk.Button(dlg, text="Hinzufügen", command=add).pack(pady=12)
        ent.bind("<Return>", lambda _e: add())

    def _remove_selected(self):
        name = self._selected_name()
        if not name:
            return
        if messagebox.askyesno("Entfernen", f"{name} aus dieser Portrait-Liste entfernen?\n\nDas vorhandene PNG wird nicht gelöscht."):
            self.names = [n for n in self.names if n.casefold() != name.casefold()]
            self._populate_tree()

    def _test_browser(self):
        self.status_var.set("Teste Microsoft Edge …")
        self.worker.submit("test_browser", **self._common_payload())

    def _open_selected(self):
        name = self._selected_name()
        if not name:
            return
        self.status_by_name[name] = "Browser wird geöffnet …"
        self._populate_tree()
        self.worker.submit("open", name=name, **self._common_payload())

    def _capture_selected(self):
        name = self._selected_name()
        if not name:
            return
        self.status_by_name[name] = "Erstelle Portrait …"
        self._populate_tree()
        payload = self._common_payload()
        payload.update(output_dir=self.output_var.get(), crop=self.config_data.get("crop", clamp_crop({})), navigate=True)
        self.worker.submit("capture", name=name, **payload)

    def _calibrate_selected(self):
        name = self._selected_name()
        if not name:
            return
        self.status_by_name[name] = "Lade Bild für Kalibrierung …"
        self._populate_tree()
        self.worker.submit("capture_raw", name=name, navigate=True, **self._common_payload())

    def _capture_all(self):
        if not self.names:
            return
        if not messagebox.askyesno(
            "Alle Portraits",
            f"Für {len(self.names)} Charaktere nacheinander Portraits erstellen?\n\n"
            "Das Browserfenster bleibt sichtbar. Bereits vorhandene PNGs werden aktualisiert."
        ):
            return
        self.progress["maximum"] = max(1, len(self.names))
        self.progress["value"] = 0
        payload = self._common_payload()
        payload.update(output_dir=self.output_var.get(), crop=self.config_data.get("crop", clamp_crop({})))
        self.worker.submit("capture_all", names=list(self.names), **payload)

    def _open_output_folder(self):
        p = Path(self.output_var.get() or default_output_dir())
        p.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(p))  # type: ignore[attr-defined]
        except Exception:
            messagebox.showinfo("Portrait-Ordner", str(p))

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _handle_event(self, event: dict):
        kind = event.get("type")
        name = event.get("name", "")
        if kind == "browser_ready":
            self.status_var.set(f"Browser bereit: {event.get('browser')}")
        elif kind == "browser_test_ok":
            browser = event.get("browser", "Browser")
            self.status_var.set(f"Browser-Test erfolgreich: {browser}")
            messagebox.showinfo(
                "Browser-Test erfolgreich",
                f"{browser} wurde gestartet und kann von der Anwendung gesteuert werden."
            )
        elif kind == "progress":
            if name:
                self.status_by_name[name] = event.get("message", "")
            self.status_var.set(event.get("message", ""))
            self._populate_tree()
        elif kind == "opened":
            self.status_by_name[name] = "Im Browser geöffnet – Modell kann jetzt gedreht/gezoomt werden"
            self.status_var.set(f"{name} geöffnet. Positioniere das Modell bei Bedarf und klicke danach auf Portrait erstellen.")
            self._populate_tree()
        elif kind == "portrait_saved":
            self.status_by_name[name] = f"Portrait gespeichert ({event.get('method', '')})"
            self.status_var.set(f"Gespeichert: {event.get('path')}")
            self._populate_tree()
        elif kind == "raw_capture":
            self.status_by_name[name] = f"Kalibrierbild bereit ({event.get('method', '')})"
            self._populate_tree()
            path = Path(event["path"])
            CropDialog(self, path, self.config_data.get("crop", clamp_crop({})),
                       lambda crop, n=name, p=path: self._apply_calibration(crop, n, p))
        elif kind == "batch_progress":
            self.progress["maximum"] = max(1, int(event.get("total", 1)))
            self.progress["value"] = int(event.get("index", 0)) - 1
            self.status_var.set(f"{event.get('index')}/{event.get('total')}: {name}")
        elif kind == "item_error":
            self.status_by_name[name] = "FEHLER: " + event.get("message", "")[:140]
            self._populate_tree()
        elif kind == "batch_done":
            self.progress["value"] = int(event.get("total", 0))
            self.status_var.set(
                f"Fertig: {event.get('total', 0)} bearbeitet, {event.get('failures', 0)} Fehler."
            )
            self._populate_tree()
        elif kind == "error":
            message = (event.get("message") or "Unbekannter Browser-/Screenshot-Fehler").strip()
            log_path = event.get("log_path") or str(app_data_dir() / "fehler.log")
            self.status_var.set("Fehler: " + message)
            messagebox.showerror(
                "Browser-/Screenshot-Fehler",
                message + "\n\nTechnische Details wurden gespeichert unter:\n" + log_path
            )

    def _apply_calibration(self, crop: dict, name: str, raw_path: Path):
        self.config_data["crop"] = clamp_crop(crop)
        self._save_settings()
        try:
            dest = Path(self.output_var.get()) / f"{safe_filename(name)}.png"
            crop_portrait(raw_path, dest, crop)
            self.status_by_name[name] = "Kalibriert + Portrait gespeichert"
            self.status_var.set("Ausschnitt gespeichert. Dieser Bereich wird jetzt für weitere Portraits verwendet.")
            self._populate_tree()
        except Exception as exc:
            messagebox.showerror("Portrait", str(exc))

    def _on_close(self):
        try:
            self._save_settings()
            self.worker.submit("stop")
        finally:
            self.destroy()


def run_self_test() -> int:
    """Fast offline checks. No live website/browser is required."""
    import tempfile

    print(f"{APP_NAME} v{APP_VERSION} - Selbsttest")
    failures = []

    def check(name, fn):
        try:
            fn()
            print(f"[OK] {name}")
        except Exception as exc:
            failures.append((name, exc))
            print(f"[FEHLER] {name}: {exc}")

    check("URL + Unicode", lambda: (
        (_ for _ in ()).throw(AssertionError("URL falsch"))
        if "%C3%81nn%C3%ADe" not in build_armory_url("Ánníe") else None
    ))

    check("Dateiname Sonderzeichen", lambda: (
        (_ for _ in ()).throw(AssertionError("Dateiname falsch"))
        if safe_filename('A:b?c*') != "A_b_c_" else None
    ))

    def test_current_page_matching():
        worker = BrowserWorker(queue.Queue())
        worker._page = type("FakePage", (), {"url": build_armory_url("Bífi") + "&foo=bar"})()
        assert worker._current_page_is_character("Bífi", "EU", "stitches", "classic1x")
        assert not worker._current_page_is_character("Sorap", "EU", "stitches", "classic1x")
    check("Manuelle Browserposition bleibt erhalten", test_current_page_matching)

    def test_empty_error_message():
        worker = BrowserWorker(queue.Queue())
        text = worker._format_error(AssertionError())
        assert text == "AssertionError"
    check("Leere Exceptions werden sichtbar", test_empty_error_message)

    def test_browser_fallback_order():
        # Configuration must not be able to put Chrome ahead of Edge.
        src = Path(__file__).read_text(encoding="utf-8")
        edge_pos = src.find('(\"msedge\", \"Microsoft Edge\")')
        chrome_pos = src.find('(\"chrome\", \"Google Chrome\")')
        assert edge_pos >= 0 and chrome_pos > edge_pos
    check("Browser-Reihenfolge Edge vor Chrome", test_browser_fallback_order)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        def test_txt():
            p = td / "names.txt"
            p.write_text("Bífi\nSorap\nBífi\nÁnníe\n", encoding="utf-8")
            assert parse_txt_names(p) == ["Bífi", "Sorap", "Ánníe"]
        check("TXT-Import", test_txt)

        def test_csv():
            p = td / "raid.csv"
            p.write_text("Name;Amount;Active Time\nBämäräng;1;2\nTazgø;3;4\n", encoding="utf-8-sig")
            assert parse_csv_names(p) == ["Bämäräng", "Tazgø"]
        check("CSV-Import Name-Spalte", test_csv)

        def test_ggc():
            p = td / "guild.ggc"
            p.write_text(json.dumps({"members": [
                {"name": "Aktivchar", "lifeStatus": "active"},
                {"name": "Totchar", "lifeStatus": "dead"}
            ]}, ensure_ascii=False), encoding="utf-8")
            assert parse_ggc_names(p, active_only=True) == ["Aktivchar"]
            assert parse_ggc_names(p, active_only=False) == ["Aktivchar", "Totchar"]
        check("GGC-Import Aktiv/Tot", test_ggc)

        def test_crop():
            if Image is None:
                raise AssertionError("Pillow fehlt")
            src = td / "raw.png"
            dst = td / "portrait.png"
            Image.new("RGB", (800, 1000), (120, 50, 20)).save(src)
            crop_portrait(src, dst, {"x1": .2, "y1": .1, "x2": .8, "y2": .7})
            with Image.open(dst) as im:
                assert im.size == (384, 672)
                assert im.mode == "RGB"
        check("Bildcrop 384x672", test_crop)

        def test_blank_detection():
            blank = td / "blank.png"
            detailed = td / "detailed.png"
            Image.new("RGB", (100, 100), (0, 0, 0)).save(blank)
            im = Image.new("RGB", (100, 100), (0, 0, 0))
            for x in range(30, 70):
                for y in range(30, 70):
                    im.putpixel((x, y), (255, 255, 255))
            im.save(detailed)
            assert not image_has_detail(blank)
            assert image_has_detail(detailed)
        check("Leerer WebGL-Screenshot wird erkannt", test_blank_detection)

    try:
        import playwright  # noqa: F401
        print("[OK] Playwright-Pythonmodul vorhanden")
    except Exception as exc:
        failures.append(("Playwright-Pythonmodul", exc))
        print("[FEHLER] Playwright-Pythonmodul fehlt")

    print()
    if failures:
        print(f"Selbsttest beendet: {len(failures)} Fehler")
        return 1
    print("Selbsttest beendet: alle Offline-Tests erfolgreich")
    print("Hinweis: Der Live-3D-Viewer kann nur auf einem PC mit Browser und Internet vollständig end-to-end getestet werden.")
    return 0


def main():
    if "--self-test" in sys.argv:
        raise SystemExit(run_self_test())
    missing = []
    if Image is None:
        missing.append("Pillow")
    try:
        import playwright  # noqa: F401
    except Exception:
        missing.append("Playwright")
    if missing:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror(
            APP_NAME,
            "Fehlende Pakete: " + ", ".join(missing) + "\n\nBitte zuerst INSTALLIEREN.bat ausführen."
        )
        root.destroy()
        return
    App().mainloop()


if __name__ == "__main__":
    main()
