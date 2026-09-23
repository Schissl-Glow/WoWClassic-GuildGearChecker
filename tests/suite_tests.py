# -*- coding: utf-8 -*-
"""Robustheits- und Integrationstests fuer Guild Gear Checker Suite v0.5.1."""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import queue
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
REFERENCE = ROOT / "docs" / "reference" / "GuildPortraitGrabber_v0.1.2_ORIGINAL.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def method_dump(src: str, class_name: str, method_name: str) -> str:
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return ast.dump(item, include_attributes=False)
    raise AssertionError(f"{class_name}.{method_name} fehlt")


def core_tests() -> None:
    os.environ["GGC_DISABLE_ICON_DOWNLOAD"] = "1"
    g = load_module("ggc_v050_core", APP / "GuildGearChecker.py")
    p = load_module("grabber_v014_core", APP / "GuildPortraitGrabber.py")

    g.run_self_tests()
    assert p.run_self_test() == 0
    assert p.APP_VERSION == g.APP_VERSION

    # Aufgeraeumte Suite-Pfade.
    assert g.app_base_dir().resolve() == ROOT.resolve()
    assert p.suite_root_dir().resolve() == ROOT.resolve()
    project = ROOT / "test-project.ggc"
    assert g.shared_portrait_folder(project).resolve() == (ROOT / "portraits").resolve()
    assert p.default_output_dir(project).resolve() == (ROOT / "portraits").resolve()
    for no_project in (g.shared_portrait_folder, p.default_output_dir):
        try:
            no_project()
            raise AssertionError("Globaler Portraitordner wurde weiterhin akzeptiert")
        except (ValueError, RuntimeError):
            pass
    assert p.config_path().resolve() == (ROOT / "config" / "portrait_grabber.json").resolve()
    assert (ROOT / "assets" / "Graveyard.jpg").exists()
    assert len(list((ROOT / "assets" / "classes" / "fallback").glob("*.png"))) == 9
    assert g.RIGHT_PORTRAIT_SIZE == 220

    # Im Root liegen keine Python-/Vorschau-/Assetdateien mehr herum.
    forbidden_root_ext = {".py", ".png", ".jpg", ".jpeg", ".json", ".cmd"}
    bad = [x.name for x in ROOT.iterdir() if x.is_file() and x.suffix.casefold() in forbidden_root_ext]
    assert not bad, f"Unaufgeraeumte Dateien im Root: {bad}"

    # Der empfindliche v0.1.2 Browser-/Viewer-Kern muss AST-identisch bleiben.
    original_src = REFERENCE.read_text(encoding="utf-8")
    enhanced_src = (APP / "GuildPortraitGrabber.py").read_text(encoding="utf-8")
    for method in ("_ensure_browser", "_goto", "_unlock_viewer", "_mark_best_viewer", "_raw_screenshot"):
        assert method_dump(original_src, "BrowserWorker", method) == method_dump(enhanced_src, "BrowserWorker", method), method
    assert '"capture_mode": "playwright"' in enhanced_src
    assert enhanced_src.find('("msedge", "Microsoft Edge")') < enhanced_src.find('("chrome", "Google Chrome")')

    # Alle fehlenden: verschiedene erlaubte Bildformate gelten als vorhanden.
    class Var:
        def __init__(self, value): self.value = value
        def get(self): return self.value
    with tempfile.TemporaryDirectory() as td_raw:
        td = Path(td_raw)
        dummy = object.__new__(p.App)
        dummy.project_path = td / "Test.ggc"
        dummy.names = ["Aba", "Ánníe", "Burgûs", "Tazgø"]
        dummy.character_records = {
            name.casefold(): {"memberId": f"m{index:04d}", "characterName": name}
            for index, name in enumerate(dummy.names, 1)
        }
        portraits = td / "portraits"
        portraits.mkdir()
        (portraits / "m0001.png").write_bytes(b"x")
        (portraits / "m0002.png").write_bytes(b"x")
        (portraits / "m0003.png").write_bytes(b"x")
        assert p.App._missing_names(dummy) == ["Tazgø"]

    # STOPP beendet Stapel zwischen zwei Charakteren.
    events = queue.Queue(); bw = p.BrowserWorker(events); calls = []
    def fake_capture(**kwargs):
        calls.append(kwargs["name"])
        bw._batch_cancel.set()
    bw._capture_character = fake_capture
    bw._capture_all(names=["A", "B", "C"], region="EU", realm="stitches", game_version="classic1x",
                    preferred_channel="msedge", wait_after_load=0, output_dir=str(ROOT / "data" / "portraits"),
                    crop=p.clamp_crop({}))
    emitted = []
    while not events.empty(): emitted.append(events.get())
    done = [e for e in emitted if e.get("type") == "batch_done"][-1]
    assert calls == ["A"] and done["cancelled"] and done["processed"] == 1

    # Alte Grabber-Konfiguration wird in der neuen Struktur gelesen, damit Crop/Modus nicht verloren gehen.
    with tempfile.TemporaryDirectory() as td_raw:
        td = Path(td_raw)
        old_config_path, old_legacy_path = p.config_path, p.legacy_config_path
        try:
            new_cfg = td / "new" / "portrait_grabber.json"
            legacy_cfg = td / "old" / "config.json"
            legacy_cfg.parent.mkdir(parents=True)
            legacy_cfg.write_text(json.dumps({
                "region": "EU", "realm": "stitches", "crop": {"x1": .11, "y1": .12, "x2": .66, "y2": .88},
                "capture_mode": "playwright", "standard_wait_after_open": 7.5
            }), encoding="utf-8")
            p.config_path = lambda: new_cfg
            p.legacy_config_path = lambda: legacy_cfg
            migrated = p.load_config()
            assert migrated["crop"]["x1"] == .11 and migrated["crop"]["y2"] == .88
            assert migrated["capture_mode"] == "playwright"
            p.save_config(migrated)
            assert new_cfg.exists()
        finally:
            p.config_path, p.legacy_config_path = old_config_path, old_legacy_path

    # Standardbereich inkl. Multi-Monitor.
    assert p.validate_screen_region((100, 100, 300, 525), (0, 0, 1920, 1080))[0]
    assert p.validate_screen_region((-1100, 50, 300, 525), (-1280, 0, 3200, 1080))[0]
    assert not p.validate_screen_region((0, 0, 20, 20), (0, 0, 1920, 1080))[0]

    # Alte GGC-Daten bleiben kompatibel; Tot bleibt Tot.
    legacy = {"members": [
        {"id": "1", "name": "Oldwar", "classSpec": "Warrior / Fury", "lifeStatus": "active"},
        {"id": "2", "name": "Olddead", "classSpec": "Priest / Shadow", "lifeStatus": "dead"},
    ]}
    gm = g.GuildModel(); gm.load_payload(legacy)
    assert gm.find_by_name("Oldwar").className == "Warrior"
    assert gm.find_by_name("Oldwar").spec == "Fury"
    assert gm.find_by_name("Olddead").lifeStatus == "dead"

    # GGC -> Grabber: aktive Charaktere only, ohne Fuzzy-Matching.
    with tempfile.TemporaryDirectory() as td_raw:
        td = Path(td_raw)
        f = td / "guild.ggc"
        f.write_text(json.dumps({"members": [
            {"name": "Bífi", "lifeStatus": "active"},
            {"name": "Bifibifi", "lifeStatus": "active"},
            {"name": "Deadone", "lifeStatus": "dead"},
        ]}, ensure_ascii=False), encoding="utf-8")
        assert p.parse_ggc_names(f, True) == ["Bífi", "Bifibifi"]
        assert p.parse_ggc_names(f, False) == ["Bífi", "Bifibifi", "Deadone"]

    # Echter WCL-Export dieser Entwicklungssitzung, wenn vorhanden.
    real_csv = ROOT.parent / "Fähigkeiten - Encounters and Trash Fights (All Encounters and Trash Fights) - Report Molten Core Warcraft Logs Vanilla(1).csv"
    if real_csv.exists():
        names = p.parse_csv_names(real_csv)
        assert len(names) == 34 and "Tazgø" in names and "Ánníe" in names

    # Starter und Ordnerstruktur verweisen auf die neuen Pfade.
    # Der Hauptstarter verwendet Qt; der Tkinter-Checker bleibt separat als Legacy-Referenz.
    starter_g = (ROOT / "STARTEN_GuildGearChecker.bat").read_text(encoding="utf-8")
    starter_p = (ROOT / "STARTEN_PortraitGrabber.bat").read_text(encoding="utf-8")
    assert "app\\GuildGearCheckerQt.py" in starter_g
    assert "import PySide6" in starter_g
    assert "app\\GuildPortraitGrabberQt.py" in starter_p
    assert "app\\GuildPortraitGrabber.py" not in starter_p
    assert "--output-dir" not in starter_p
    assert "tools\\_FIND_QT_PYTHON.cmd" in starter_p
    starter_p_legacy = (ROOT / "STARTEN_PortraitGrabber_LEGACY.bat").read_text(
        encoding="utf-8"
    )
    assert "app\\GuildPortraitGrabber.py" in starter_p_legacy
    assert "tools\\_FIND_MINIFORGE.cmd" in starter_p_legacy

    print("CORE/INTEGRATION TESTS OK")


def ui_smoke_tests() -> None:
    import tkinter as tk
    from tkinter import ttk
    os.environ["GGC_DISABLE_ICON_DOWNLOAD"] = "1"
    g = load_module("ggc_v050_ui", APP / "GuildGearChecker.py")
    p = load_module("grabber_v014_ui", APP / "GuildPortraitGrabber.py")

    with tempfile.TemporaryDirectory() as td_raw:
        td = Path(td_raw)
        # Tests duerfen keine echten Nutzer-Konfigurationen veraendern.
        p.config_path = lambda: td / "portrait_grabber.json"
        p.legacy_config_path = lambda: td / "legacy_portrait_grabber.json"
        p.app_data_dir = lambda: td / "grabber_temp"

        # Gear Checker: kleine Aufloesung + rechte Scrollspalte + 220px Portrait.
        app = g.GuildGearCheckerApp()
        app.geometry("1040x680+0+0"); app.update_idletasks(); app.update()
        assert app.model.members == [] and app.model.project_path is None
        checker_project = td / "Checker.ggc"
        checker_payload = g.GuildModel()
        checker_payload.members = [g.Member(id="m0001", name="Aba")]
        checker_payload.save(checker_project, backup=False)
        app.model.load(checker_project)
        app.refresh_all(select_first=True)
        assert set(app.tab_buttons) == set(g.TAB_ORDER)
        for tab in g.TAB_ORDER:
            app.switch_tab(tab); app.update_idletasks(); app.update(); assert app.current_tab == tab
        aba = app.model.find_by_name("Aba"); assert aba
        app.show_member(aba.id); app.update_idletasks(); app.update()
        assert app.portrait_frame.winfo_width() == 220 and app.portrait_frame.winfo_height() == 220
        assert app.detail_canvas.cget("yscrollcommand")
        app.detail_canvas.yview_moveto(1.0); app.update_idletasks()

        # Der Grabber erhält exakt das aktive echte .ggc-Projekt.
        popen_calls = []
        original_popen = g.subprocess.Popen
        try:
            g.subprocess.Popen = lambda args, cwd=None: popen_calls.append((list(args), cwd)) or object()
            app.open_portrait_grabber()
            assert popen_calls
            cmd, cwd = popen_calls[-1]
            assert str(ROOT / "app" / "GuildPortraitGrabber.py") in cmd
            assert "--project" in cmd and str(checker_project.resolve()) in cmd
            assert "--roster-json" not in cmd and "--output-dir" not in cmd
            assert Path(cwd).resolve() == ROOT.resolve()
        finally:
            g.subprocess.Popen = original_popen
        app.destroy()

        # Solo-Grabber startet ohne Projekt/Seed, Review bleibt trotzdem verfügbar.
        solo = p.App()
        solo.update_idletasks(); solo.update()
        assert solo.project_path is None and solo.names == [] and solo.dead_names == []
        assert str(solo.single_btn.cget("state")) == "disabled"
        assert hasattr(solo, "review_frame") and solo.review_frame.winfo_exists()
        solo._on_close()

        # Grabber: genau ein vorhandenes, zwei fehlende Portraits.
        out = td / "portraits"; out.mkdir()
        p.Image.new("RGB", (384, 672), "gray").save(out / "m0001.png")
        grabber_project = td / "Grabber.ggc"
        grabber_project.write_text(json.dumps({"members": [
            {"id": "m0001", "name": "Aba"},
            {"id": "m0002", "name": "Ánníe"},
            {"id": "m0003", "name": "Tazgø"},
        ]}, ensure_ascii=False), encoding="utf-8")
        records, context = p.parse_ggc_characters(grabber_project, active_only=False)
        grab = p.App(initial_characters=records, armory_context=context,
                     project_path=str(grabber_project))
        grab.geometry("760x520+0+0"); grab.update_idletasks(); grab.update()

        tabs = [grab.notebook.tab(i, "text") for i in range(grab.notebook.index("end"))]
        assert tabs == ["Portraits", "Friedhof", "Ausschnitt", "Einstellungen", "Grabstein Review"]
        assert hasattr(grab, "review_frame") and grab.review_frame.winfo_exists()
        assert grab._missing_names() == ["Ánníe", "Tazgø"]
        assert "2 fehlen" in grab.summary_var.get()
        assert str(grab.stop_btn.cget("state")) == "disabled"

        # Jeder inhaltsreiche Hauptreiter besitzt vertikale UND horizontale Scrollbars.
        for sf in (grab.portrait_scroll, grab.crop_scroll, grab.settings_scroll):
            assert sf.vbar.winfo_exists() and sf.hbar.winfo_exists()
            assert sf.canvas.cget("yscrollcommand") and sf.canvas.cget("xscrollcommand")
            sf._sync_scrollregion(); grab.update_idletasks()
            assert sf.canvas.cget("scrollregion")

        # Tabelle und Log sind separat scrollbar; Log kann ein-/ausgeklappt werden.
        assert grab.tree.cget("yscrollcommand") and grab.tree.cget("xscrollcommand")
        assert grab.log_text.cget("yscrollcommand") and grab.log_text.cget("xscrollcommand")
        grab.show_log_var.set(True); grab._toggle_log(); grab.update_idletasks()
        assert grab.log_frame.winfo_ismapped()
        grab.show_log_var.set(False); grab._toggle_log(); grab.update_idletasks()
        assert not grab.log_frame.winfo_ismapped()

        # "Alle fehlenden" reicht nur fehlende Namen an den vorhandenen v0.1.2 Batchpfad weiter.
        submitted = []
        original_submit = grab.worker.submit
        original_ask = p.messagebox.askyesno
        try:
            grab.worker.submit = lambda action, **payload: submitted.append((action, payload))
            p.messagebox.askyesno = lambda *a, **k: True
            grab._capture_missing()
            assert submitted and submitted[-1][0] == "capture_all"
            assert submitted[-1][1]["names"] == ["Ánníe", "Tazgø"]
            assert grab.batch_running
            assert str(grab.missing_btn.cget("state")) == "disabled"
            assert str(grab.stop_btn.cget("state")) == "normal"
            grab._request_stop()
            assert grab.worker._batch_cancel.is_set()
            assert str(grab.stop_btn.cget("state")) == "disabled"
            grab._handle_event({"type":"batch_done", "processed":2, "total":2, "successes":2, "failures":0, "cancelled":True})
            assert not grab.batch_running and str(grab.missing_btn.cget("state")) == "normal"
        finally:
            grab.worker.submit = original_submit
            p.messagebox.askyesno = original_ask

        # Nach erfolgreicher Dateiablage aktualisiert sich der Fehlend-Zaehler.
        p.Image.new("RGB", (384, 672), "gray").save(out / "m0002.png")
        grab._populate_tree(); grab.update_idletasks()
        assert grab._missing_names() == ["Tazgø"] and "1 fehlen" in grab.summary_var.get()

        # Scrollbare Informations-/Bilddialoge.
        txt = p.ScrollableTextDialog(grab, "Test", "Zeile\n" * 100)
        txt.update_idletasks(); txt.update()
        text_widgets = []
        def walk(w):
            for ch in w.winfo_children():
                if isinstance(ch, tk.Text): text_widgets.append(ch)
                walk(ch)
        walk(txt)
        assert text_widgets and text_widgets[0].cget("yscrollcommand") and text_widgets[0].cget("xscrollcommand")
        txt.destroy()

        raw = td / "raw.png"; p.Image.new("RGB", (1600, 1100), "gray").save(raw)
        crop = p.CropDialog(grab, raw, p.clamp_crop({}), lambda _crop: None)
        crop.update_idletasks(); crop.update()
        assert crop.canvas.cget("yscrollcommand") and crop.canvas.cget("xscrollcommand")
        crop.destroy()

        shot = p.Image.new("RGB", (1400, 900), "gray")
        sel = p.ScreenRegionSelector(grab, shot, (0,0,1400,900), lambda _r: None)
        sel.update_idletasks(); sel.update()
        assert sel.canvas.cget("yscrollcommand") and sel.canvas.cget("xscrollcommand")
        sel.destroy()

        prev = p.ImagePreviewDialog(grab, shot, "Vorschau")
        prev.update_idletasks(); prev.update()
        canvases = []
        def walk_canvas(w):
            for ch in w.winfo_children():
                if isinstance(ch, tk.Canvas): canvases.append(ch)
                walk_canvas(ch)
        walk_canvas(prev)
        assert canvases and canvases[0].cget("yscrollcommand") and canvases[0].cget("xscrollcommand")
        prev.destroy()

        grab.worker.request_batch_cancel(); grab.worker.submit("stop")
        grab.destroy()

    print("GUI/SCROLL/ALLE-FEHLENDEN TESTS OK")


def playwright_smoke() -> None:
    p = load_module("grabber_v014_browser", APP / "GuildPortraitGrabber.py")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = None; errors = []
        for kwargs in ({"headless": True}, {"channel": "msedge", "headless": True}, {"channel": "chrome", "headless": True}):
            try:
                browser = pw.chromium.launch(**kwargs); break
            except Exception as exc:
                errors.append(str(exc))
        if browser is None and Path("/usr/bin/chromium").exists():
            browser = pw.chromium.launch(executable_path="/usr/bin/chromium", headless=True)
        if browser is None:
            raise RuntimeError("Kein Chromium fuer Smoke-Test: " + " | ".join(errors))
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        page.set_content('''<html><body><div id="character-viewer"><canvas id="c" width="500" height="620" style="width:500px;height:620px"></canvas></div><script>const c=document.getElementById('c');const x=c.getContext('2d');x.fillStyle='#777';x.fillRect(0,0,500,620);x.fillStyle='#eee';x.fillRect(170,70,160,430);</script></body></html>''')
        worker = p.BrowserWorker(queue.Queue()); worker._browser = browser; worker._context = page.context; worker._page = page
        assert worker._mark_best_viewer()
        out = ROOT / "data" / "temp" / "playwright_smoke.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        page.locator('[data-gpg-target="1"]').first.screenshot(path=str(out))
        assert out.exists() and out.stat().st_size > 1000
        out.unlink(missing_ok=True)
        browser.close()
    print("PLAYWRIGHT v0.1.2 BROWSER SMOKE TEST OK")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", action="store_true")
    ap.add_argument("--ui", action="store_true")
    ap.add_argument("--playwright", action="store_true")
    args = ap.parse_args()
    if not (args.core or args.ui or args.playwright):
        args.core = True
    if args.core: core_tests()
    if args.ui: ui_smoke_tests()
    if args.playwright: playwright_smoke()


if __name__ == "__main__":
    main()
