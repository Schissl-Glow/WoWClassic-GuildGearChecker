"""Lokale Eingabehilfe fuer die Performance-Baseline.

Die Anwendung steuert keinen GuildGearChecker und wertet keine Bilder aus. Sie unterstuetzt
einen komfortablen Direkt-Timer (unter Windows global per F8) sowie weiterhin die praezisere
Frame-Auswertung einer Bildschirmaufnahme. Messwerte werden validiert, gespeichert und
statistisch zusammengefasst.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REFERENCE_VERSION = "0.9.1"
REFERENCE_COMMIT = "bab236f4e9fd14ec1c057fdc4ea995dc556a2691"
SCHEMA_VERSION = 1
RUNS_PER_BLOCK = 7
METHOD_FRAME = "frame"
METHOD_TIMER = "timer"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_PATH = PROJECT_ROOT / "performance_results" / "performance_baseline_v091.json"
DEFAULT_EXPORT_PATH = (
    PROJECT_ROOT / "docs" / "migration" / "PYSIDE6_GRABBER_PHASE1_PERFORMANCE_RESULTS_V091.md"
)


@dataclass(frozen=True)
class PerfPoint:
    identifier: str
    title: str
    start: str
    end: str
    data: str
    modes: tuple[str, ...]


# Verbindlich aus PYSIDE6_GRABBER_PHASE1_PERFORMANCE_BASELINE.md, Abschnitt 4.
PERFORMANCE_POINTS: tuple[PerfPoint, ...] = (
    PerfPoint(
        "PERF-001", "Portrait Grabber starten",
        "Erstes Videoframe nach Betätigen von STARTEN_PortraitGrabber.bat beziehungsweise Enter im vorbereiteten Starterfenster.",
        "Hauptfenster ist vollständig gezeichnet, Starttab sichtbar, Status zeigt Bereitschaft und UI nimmt Eingaben an.",
        "Unveränderter Workspace; kein automatisch geöffnetes Projekt.", ("cold",),
    ),
    PerfPoint(
        "PERF-002", "Projekt öffnen/laden",
        "Klick auf Öffnen im bereits auf die Referenzdatei eingestellten Dateidialog.",
        "Projektstatus, Charaktertabelle, Zähler und erste zulässige Auswahl sind vollständig aktualisiert; kein Ladezustand mehr sichtbar.",
        "Festes lokales Referenzprojekt mit dokumentiertem Hash.", ("cold", "warm"),
    ),
    PerfPoint(
        "PERF-003", "Charakter auswählen",
        "Mouse-up auf der festgelegten Tabellenzeile eines Charakters ohne Portrait.",
        "Zeile ist selektiert, Detail-/Statuswerte und sicherer Leerzustand der Portraitvorschau sind vollständig sichtbar.",
        "Geladenes Referenzprojekt; festgelegter aktiver Charakter ohne Portrait.", ("cold", "warm"),
    ),
    PerfPoint(
        "PERF-004", "Vorhandenes Portrait laden",
        "Mouse-up auf der festgelegten Tabellenzeile des Portraitcharakters.",
        "Portrait ist proportional vollständig gezeichnet, Name/Status und zugehörige Aktionen sind aktualisiert.",
        "Referenzprojekt und unveränderte konkrete Portrait-PNG.", ("cold", "warm"),
    ),
    PerfPoint(
        "PERF-005", "Portrait aktualisieren und Preview neu laden",
        "Mouse-up auf Speichern/Anwenden im Portraiteditor einer vorbereiteten, identischen Arbeitskopie.",
        "Editor ist geschlossen; Tabellenstatus und neu geladene Portraitvorschau sind vollständig gezeichnet und wieder bedienbar.",
        "Disposable Kopie des Referenzprojekts samt Portrait; identischer No-op-Edit pro Lauf.", ("cold", "warm"),
    ),
    PerfPoint(
        "PERF-006", "Friedhof öffnen",
        "Mouse-up auf dem Tab Friedhof aus dem festgelegten Starttab.",
        "Friedhofsliste, festgelegter Eintrag, Detailwerte und gerenderte Grabsteinvorschau sind vollständig sichtbar und scrollbar.",
        "Referenzprojekt mit Totem, historischem Portrait und zugewiesenem Grabstein.", ("cold", "warm"),
    ),
    PerfPoint(
        "PERF-007", "Grabstein wechseln",
        "Mouse-up auf Nächster beziehungsweise Auswahl der vorher dokumentierten Ziel-ID im bereits geöffneten Unified Editor.",
        "Ziel-ID/Name ist aktualisiert, neue Vorschau vollständig gezeichnet und Editor reagiert wieder auf Eingaben.",
        "Derselbe Friedhofseintrag; zwei dokumentierte verfügbare produktive Grabsteine.", ("cold", "warm"),
    ),
    PerfPoint(
        "PERF-008", "Gravestone Review Tool öffnen",
        "Mouse-up auf den integrierten Tab Grabstein Review in der laufenden Grabber-Anwendung.",
        "Kompakter Kopf, Queuezähler, erster Dateiname, Prüfergebnisse, Kategorie-/Aktionsbereich und erste Vorschau sind vollständig sichtbar.",
        "Unveränderte vier versionierte _candidates; Einzelansicht als Startansicht.", ("cold", "warm"),
    ),
    PerfPoint(
        "PERF-009", "Review-Kandidat wechseln",
        "Mouse-up auf Nächster vom festgelegten Ausgangskandidaten.",
        "Neuer Dateiname/Index, Bildvorschau, Prüfergebnisse, Kategorie und Aktionszustände gehören sichtbar zum Zielkandidaten; UI ist bedienbar.",
        "Feste Reihenfolge der vier Kandidaten; keine Queueoperation während der Serie.", ("cold", "warm"),
    ),
    PerfPoint(
        "PERF-010", "Galerie öffnen",
        "Mouse-up auf Galerie aus der Einzelansicht.",
        "Alle vier Kandidatentiles, Dateinamen und Thumbnails sind aufgebaut; Scrollregion/Reflow stabil und bedienbar.",
        "Unveränderte vier Kandidaten; feste Fensterbreite.", ("cold", "warm"),
    ),
    PerfPoint(
        "PERF-011", "Portraiteditor öffnen",
        "Mouse-up auf Portrait bearbeiten für den festgelegten Portraitcharakter.",
        "Editorfenster und erste hochauflösende Preview sind vollständig gezeichnet; Pan/Zoom/Crop reagieren.",
        "Referenzprojekt; konkrete unveränderte Portrait-PNG.", ("cold", "warm"),
    ),
    PerfPoint(
        "PERF-012", "Unified Graveyard Editor öffnen",
        "Mouse-up auf Grabstein anpassen beim festgelegten Friedhofseintrag.",
        "Editorcontrols, aktuelle Template-/Kategorie-/Presetwerte und erste zusammengesetzte Vorschau sind vollständig sichtbar und bedienbar.",
        "Referenzprojekt, Friedhofseintrag, Portrait, produktives Manifest und 54 reguläre Grabsteine.", ("cold", "warm"),
    ),
)
POINTS_BY_ID = {point.identifier: point for point in PERFORMANCE_POINTS}
ENVIRONMENT_FIELDS = (
    "computer", "windows_version", "resolution", "windows_scaling", "language",
    "recording_fps", "reference_project", "notes",
)


class SessionDataError(ValueError):
    """Raised when an existing result file cannot be safely continued."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_session() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "reference": {"version": REFERENCE_VERSION, "commit": REFERENCE_COMMIT},
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "environment": {field: "" for field in ENVIRONMENT_FIELDS},
        "runs": [],
    }


def _validate_mode(point: PerfPoint, mode: str) -> None:
    if mode not in point.modes:
        allowed = ", ".join(point.modes)
        raise ValueError(f"{point.identifier} erlaubt nur: {allowed}.")


def calculate_frame_measurement(fps: float, start_frame: int, end_frame: int) -> dict[str, Any]:
    if not isinstance(fps, (int, float)) or isinstance(fps, bool) or not math.isfinite(fps) or fps <= 0:
        raise ValueError("FPS muss eine endliche Zahl größer als 0 sein.")
    if not isinstance(start_frame, int) or isinstance(start_frame, bool) or start_frame < 0:
        raise ValueError("Startframe muss eine ganze Zahl ab 0 sein.")
    if not isinstance(end_frame, int) or isinstance(end_frame, bool) or end_frame <= start_frame:
        raise ValueError("Endframe muss eine ganze Zahl größer als der Startframe sein.")
    frame_delta = end_frame - start_frame
    duration_seconds = frame_delta / float(fps)
    return {
        "fps": float(fps),
        "start_frame": start_frame,
        "end_frame": end_frame,
        "frame_delta": frame_delta,
        "duration_seconds": round(duration_seconds, 6),
        "duration_seconds_text": f"{duration_seconds:.3f}",
    }


def calculate_timer_measurement(duration_seconds: float) -> dict[str, Any]:
    if (not isinstance(duration_seconds, (int, float)) or isinstance(duration_seconds, bool)
            or not math.isfinite(duration_seconds) or duration_seconds <= 0):
        raise ValueError("Timerdauer muss eine endliche Zahl größer als 0 sein.")
    duration = float(duration_seconds)
    return {
        "measurement_method": METHOD_TIMER,
        "timer_clock": "time.perf_counter",
        "duration_seconds": round(duration, 6),
        "duration_seconds_text": f"{duration:.3f}",
    }


def run_measurement_method(run: dict[str, Any]) -> str:
    # Alte v0.9.1-Sitzungen kannten noch kein Feld measurement_method; sie sind Frame-Messungen.
    return str(run.get("measurement_method") or METHOD_FRAME)


def validate_session(session: dict[str, Any]) -> None:
    if not isinstance(session, dict) or session.get("schema_version") != SCHEMA_VERSION:
        raise SessionDataError("Unbekanntes oder beschädigtes Sitzungsformat.")
    reference = session.get("reference")
    runs = session.get("runs")
    if not isinstance(reference, dict) or not isinstance(runs, list):
        raise SessionDataError("Die Sitzungsdatei enthält keine gültige Referenz oder Laufdaten.")
    if reference.get("version") != REFERENCE_VERSION or reference.get("commit") != REFERENCE_COMMIT:
        raise SessionDataError("Die Sitzungsdatei gehört nicht zur v0.9.1-Referenzbaseline.")
    seen: set[tuple[str, str, int]] = set()
    block_methods: dict[tuple[str, str], str] = {}
    for run in runs:
        if not isinstance(run, dict):
            raise SessionDataError("Die Sitzungsdatei enthält einen ungültigen Messlauf.")
        point = POINTS_BY_ID.get(run.get("perf_id"))
        mode = run.get("mode")
        number = run.get("run_number")
        if point is None or not isinstance(mode, str) or not isinstance(number, int):
            raise SessionDataError("Ein Messlauf enthält ungültige PERF-ID, Modus oder Laufnummer.")
        _validate_mode(point, mode)
        key = (point.identifier, mode, number)
        if key in seen:
            raise SessionDataError("Die Sitzungsdatei enthält doppelte Laufnummern.")
        seen.add(key)

        method = run_measurement_method(run)
        if method not in {METHOD_FRAME, METHOD_TIMER}:
            raise SessionDataError(f"Unbekannte Messmethode: {method}")
        block_key = (point.identifier, mode)
        previous = block_methods.setdefault(block_key, method)
        if previous != method:
            raise SessionDataError(
                f"{point.identifier} {mode.upper()} mischt Frame- und Timer-Messungen. "
                "Ein Messblock muss eine einheitliche Methode verwenden."
            )
        try:
            if method == METHOD_FRAME:
                calculate_frame_measurement(run.get("fps"), run.get("start_frame"), run.get("end_frame"))
            else:
                calculate_timer_measurement(run.get("duration_seconds"))
        except ValueError as exc:
            label = "Framedaten" if method == METHOD_FRAME else "Timerdaten"
            raise SessionDataError(f"Ein Messlauf enthält ungültige {label}: {exc}") from exc


def load_session(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionDataError(f"Ergebnisdatei kann nicht gelesen werden: {exc}") from exc
    validate_session(payload)
    return payload


def load_or_create_session(path: Path) -> dict[str, Any]:
    path = Path(path)
    if path.exists():
        return load_session(path)
    return new_session()


def save_session(path: Path, session: dict[str, Any]) -> None:
    validate_session(session)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    session["updated_at"] = utc_now()
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, target)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def runs_for(session: dict[str, Any], perf_id: str, mode: str) -> list[dict[str, Any]]:
    return sorted(
        (run for run in session["runs"] if run["perf_id"] == perf_id and run["mode"] == mode),
        key=lambda item: item["run_number"],
    )


def next_run_number(session: dict[str, Any], perf_id: str, mode: str) -> int:
    used = {run["run_number"] for run in runs_for(session, perf_id, mode)}
    for number in range(1, RUNS_PER_BLOCK + 1):
        if number not in used:
            return number
    raise ValueError("Dieser Messblock enthält bereits sieben gültige Läufe.")


def block_method(session: dict[str, Any], perf_id: str, mode: str) -> str | None:
    methods = {run_measurement_method(run) for run in runs_for(session, perf_id, mode)}
    if not methods:
        return None
    if len(methods) != 1:
        raise SessionDataError(f"{perf_id} {mode.upper()} enthält gemischte Messmethoden.")
    return next(iter(methods))


def _new_run(perf_id: str, mode: str, run_number: int, fps: float, start_frame: int,
             end_frame: int, note: str) -> dict[str, Any]:
    point = POINTS_BY_ID.get(perf_id)
    if point is None:
        raise ValueError(f"Unbekannte PERF-ID: {perf_id}")
    _validate_mode(point, mode)
    if not isinstance(run_number, int) or run_number < 1 or run_number > RUNS_PER_BLOCK:
        raise ValueError(f"Laufnummer muss zwischen 1 und {RUNS_PER_BLOCK} liegen.")
    measurement = calculate_frame_measurement(fps, start_frame, end_frame)
    return {
        "recorded_at": utc_now(),
        "perf_id": perf_id,
        "mode": mode,
        "run_number": run_number,
        "measurement_method": METHOD_FRAME,
        **measurement,
        "note": str(note).strip(),
    }


def add_run(session: dict[str, Any], perf_id: str, mode: str, fps: float, start_frame: int,
            end_frame: int, note: str = "") -> dict[str, Any]:
    existing_method = block_method(session, perf_id, mode)
    if existing_method not in {None, METHOD_FRAME}:
        raise ValueError("Dieser Messblock verwendet bereits den Direkt-Timer und darf nicht gemischt werden.")
    number = next_run_number(session, perf_id, mode)
    run = _new_run(perf_id, mode, number, fps, start_frame, end_frame, note)
    session["runs"].append(run)
    return run


def _new_timer_run(perf_id: str, mode: str, run_number: int, duration_seconds: float,
                   note: str) -> dict[str, Any]:
    point = POINTS_BY_ID.get(perf_id)
    if point is None:
        raise ValueError(f"Unbekannte PERF-ID: {perf_id}")
    _validate_mode(point, mode)
    if not isinstance(run_number, int) or run_number < 1 or run_number > RUNS_PER_BLOCK:
        raise ValueError(f"Laufnummer muss zwischen 1 und {RUNS_PER_BLOCK} liegen.")
    measurement = calculate_timer_measurement(duration_seconds)
    return {
        "recorded_at": utc_now(),
        "perf_id": perf_id,
        "mode": mode,
        "run_number": run_number,
        **measurement,
        "note": str(note).strip(),
    }


def add_timer_run(session: dict[str, Any], perf_id: str, mode: str, duration_seconds: float,
                  note: str = "") -> dict[str, Any]:
    existing_method = block_method(session, perf_id, mode)
    if existing_method not in {None, METHOD_TIMER}:
        raise ValueError("Dieser Messblock verwendet bereits Frame-Messungen und darf nicht gemischt werden.")
    number = next_run_number(session, perf_id, mode)
    run = _new_timer_run(perf_id, mode, number, duration_seconds, note)
    session["runs"].append(run)
    return run


def remove_run(session: dict[str, Any], perf_id: str, mode: str, run_number: int) -> dict[str, Any]:
    for index, run in enumerate(session["runs"]):
        if (run["perf_id"], run["mode"], run["run_number"]) == (perf_id, mode, run_number):
            return session["runs"].pop(index)
    raise ValueError("Der angegebene Messlauf existiert nicht.")


def replace_run(session: dict[str, Any], perf_id: str, mode: str, run_number: int, fps: float,
                start_frame: int, end_frame: int, note: str = "") -> dict[str, Any]:
    replacement = _new_run(perf_id, mode, run_number, fps, start_frame, end_frame, note)
    for index, run in enumerate(session["runs"]):
        if (run["perf_id"], run["mode"], run["run_number"]) == (perf_id, mode, run_number):
            session["runs"][index] = replacement
            return replacement
    raise ValueError("Der angegebene Messlauf existiert nicht.")


def replace_timer_run(session: dict[str, Any], perf_id: str, mode: str, run_number: int,
                      duration_seconds: float, note: str = "") -> dict[str, Any]:
    replacement = _new_timer_run(perf_id, mode, run_number, duration_seconds, note)
    for index, run in enumerate(session["runs"]):
        if (run["perf_id"], run["mode"], run["run_number"]) == (perf_id, mode, run_number):
            session["runs"][index] = replacement
            return replacement
    raise ValueError("Der angegebene Messlauf existiert nicht.")


def statistics_for(runs: Iterable[dict[str, Any]]) -> dict[str, float] | None:
    values = [float(run["duration_seconds"]) for run in runs]
    if not values:
        return None
    return {
        "median": statistics.median(values),
        "mean": statistics.fmean(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def block_status(runs: Iterable[dict[str, Any]]) -> str:
    count = len(list(runs))
    if count >= RUNS_PER_BLOCK:
        return "FERTIG"
    if count:
        return "TEILWEISE"
    return "OFFEN"


def summary_rows(session: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for point in PERFORMANCE_POINTS:
        for mode in point.modes:
            runs = runs_for(session, point.identifier, mode)
            rows.append({
                "perf_id": point.identifier,
                "title": point.title,
                "mode": mode,
                "method": block_method(session, point.identifier, mode),
                "runs": len(runs),
                "statistics": statistics_for(runs),
                "status": block_status(runs),
            })
    return rows


def update_environment(session: dict[str, Any], values: dict[str, str]) -> None:
    environment = session.setdefault("environment", {field: "" for field in ENVIRONMENT_FIELDS})
    for field in ENVIRONMENT_FIELDS:
        if field in values:
            environment[field] = str(values[field]).strip()


def _seconds(value: float | None) -> str:
    return "–" if value is None else f"{value:.3f} s"


def _method_label(method: str | None) -> str:
    if method == METHOD_TIMER:
        return "TIMER"
    if method == METHOD_FRAME:
        return "FRAME"
    return "–"


def render_markdown(session: dict[str, Any]) -> str:
    validate_session(session)
    environment = session.get("environment", {})
    lines = [
        "# Performance-Baseline-Ergebnisse v0.9.1",
        "",
        "## Referenz",
        "",
        f"- GuildGearChecker: `{REFERENCE_VERSION}`",
        f"- Baseline-Commit: `{REFERENCE_COMMIT}`",
        "- Messmethoden: Direkt-Timer (`time.perf_counter`) oder Frame-Auswertung.",
        "- Ein Messblock verwendet immer genau eine Methode; Timer- und Frame-Werte werden nicht gemischt.",
        "- Der Frame-Modus bleibt die präzisere Kontrollmethode; der Direkt-Timer ist für schnelle, reproduzierbare Vergleichsläufe vorgesehen.",
        "",
        "## Messumgebung",
        "",
        "| Feld | Wert |",
        "|---|---|",
    ]
    labels = {
        "computer": "Rechner", "windows_version": "Windows-Version", "resolution": "Bildschirmauflösung",
        "windows_scaling": "Windows-Skalierung", "language": "Sprache", "recording_fps": "Aufnahme-FPS",
        "reference_project": "Referenzprojekt", "notes": "Bemerkungen",
    }
    for field in ENVIRONMENT_FIELDS:
        value = str(environment.get(field, "")).replace("|", "\\|").replace("\n", "<br>")
        lines.append(f"| {labels[field]} | {value} |")

    lines.extend([
        "", "## Übersicht", "",
        "| PERF-ID | Modus | Methode | Läufe | Median | Mittel | Min | Max | Status |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ])
    for row in summary_rows(session):
        stats = row["statistics"] or {}
        lines.append(
            f"| {row['perf_id']} | {row['mode'].upper()} | {_method_label(row['method'])} | "
            f"{row['runs']}/{RUNS_PER_BLOCK} | {_seconds(stats.get('median'))} | "
            f"{_seconds(stats.get('mean'))} | {_seconds(stats.get('minimum'))} | "
            f"{_seconds(stats.get('maximum'))} | {row['status']} |"
        )

    lines.extend(["", "## Einzelmessungen", ""])
    for point in PERFORMANCE_POINTS:
        for mode in point.modes:
            runs = runs_for(session, point.identifier, mode)
            if not runs:
                continue
            stats = statistics_for(runs) or {}
            method = block_method(session, point.identifier, mode)
            lines.extend([
                f"### {point.identifier} – {point.title} ({mode.upper()}, {_method_label(method)})",
                "",
                f"Start: {point.start}",
                "",
                f"Ende: {point.end}",
                "",
            ])
            if method == METHOD_TIMER:
                lines.extend([
                    "| Lauf | Sekunden | Bemerkung |",
                    "|---:|---:|---|",
                ])
                for run in runs:
                    note = str(run.get("note", "")).replace("|", "\\|").replace("\n", "<br>")
                    lines.append(
                        f"| {run['run_number']} | {float(run['duration_seconds']):.3f} s | {note} |"
                    )
            else:
                lines.extend([
                    "| Lauf | FPS | Startframe | Endframe | Frames | Sekunden | Bemerkung |",
                    "|---:|---:|---:|---:|---:|---:|---|",
                ])
                for run in runs:
                    note = str(run.get("note", "")).replace("|", "\\|").replace("\n", "<br>")
                    lines.append(
                        f"| {run['run_number']} | {run['fps']:g} | {run['start_frame']} | {run['end_frame']} | "
                        f"{run['frame_delta']} | {float(run['duration_seconds']):.3f} s | {note} |"
                    )
            lines.extend([
                "",
                f"Median: **{_seconds(stats['median'])}** · Mittel: {_seconds(stats['mean'])} · "
                f"Min: {_seconds(stats['minimum'])} · Max: {_seconds(stats['maximum'])}",
                "",
            ])
    if not session["runs"]:
        lines.extend(["Noch keine bestätigten Messungen vorhanden.", ""])
    return "\n".join(lines)


def export_markdown(path: Path, session: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(render_markdown(session), encoding="utf-8")
        os.replace(temporary, target)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _prompt(text: str, allow_empty: bool = False) -> str | None:
    try:
        value = input(text).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nEingabe abgebrochen.")
        return None
    if not value and not allow_empty:
        print("Bitte einen Wert eingeben.")
        return _prompt(text, allow_empty=False)
    return value


def _prompt_float(text: str) -> float | None:
    value = _prompt(text)
    if value is None:
        return None
    try:
        parsed = float(value.replace(",", "."))
        calculate_frame_measurement(parsed, 0, 1)
        return parsed
    except ValueError as exc:
        print(f"Ungültige FPS: {exc}")
        return _prompt_float(text)


def _prompt_frame(text: str) -> int | None:
    value = _prompt(text)
    if value is None:
        return None
    try:
        parsed = int(value)
        if parsed < 0:
            raise ValueError
        return parsed
    except ValueError:
        print("Bitte eine ganze Zahl ab 0 eingeben.")
        return _prompt_frame(text)


def _choose_point() -> PerfPoint | None:
    print("\nMesspunkte:")
    for index, point in enumerate(PERFORMANCE_POINTS, start=1):
        modes = "/".join(mode.upper() for mode in point.modes)
        print(f"  {index:>2}. {point.identifier} – {point.title} [{modes}]")
    value = _prompt("PERF-ID oder Nummer (Enter = zurück): ", allow_empty=True)
    if not value:
        return None
    if value.isdigit() and 1 <= int(value) <= len(PERFORMANCE_POINTS):
        return PERFORMANCE_POINTS[int(value) - 1]
    point = POINTS_BY_ID.get(value.upper())
    if point is None:
        print("Unbekannter Messpunkt.")
        return _choose_point()
    return point


def _choose_mode(point: PerfPoint) -> str | None:
    if len(point.modes) == 1:
        print("Modus: COLD (Frischstart)")
        return point.modes[0]
    value = _prompt("Modus [C]old / [W]arm (Enter = zurück): ", allow_empty=True)
    if not value:
        return None
    mapping = {"c": "cold", "cold": "cold", "w": "warm", "warm": "warm"}
    mode = mapping.get(value.casefold())
    if mode not in point.modes:
        print("Bitte COLD oder WARM wählen.")
        return _choose_mode(point)
    return mode


def _print_point(point: PerfPoint, mode: str, session: dict[str, Any]) -> None:
    runs = runs_for(session, point.identifier, mode)
    print(f"\n{point.identifier} – {point.title} [{mode.upper()}]")
    print(f"Start: {point.start}")
    print(f"Ende:  {point.end}")
    print(f"Daten: {point.data}")
    print(f"Fortschritt: {len(runs)}/{RUNS_PER_BLOCK} – {block_status(runs)}")


def _confirm(text: str) -> bool:
    value = _prompt(f"{text} [j/N]: ", allow_empty=True)
    return bool(value and value.casefold() in {"j", "ja", "y", "yes"})


def _choose_measurement_method(session: dict[str, Any], point: PerfPoint, mode: str) -> str | None:
    existing = block_method(session, point.identifier, mode)
    if existing is not None:
        print(f"Messmethode für diesen Block: {_method_label(existing)} (durch vorhandene Läufe festgelegt)")
        return existing
    value = _prompt(
        "Messmethode [T]imer (empfohlen) / [F]rame (präzise Kontrolle), Enter = Timer: ",
        allow_empty=True,
    )
    if value is None:
        return None
    normalized = value.casefold()
    if normalized in {"", "t", "timer", "direkt", "direkttimer"}:
        return METHOD_TIMER
    if normalized in {"f", "frame", "frames"}:
        return METHOD_FRAME
    print("Bitte TIMER oder FRAME wählen.")
    return _choose_measurement_method(session, point, mode)


def _beep(frequency: int = 880, duration_ms: int = 80) -> None:
    if sys.platform != "win32":
        return
    try:
        import winsound
        winsound.Beep(frequency, duration_ms)
    except Exception:
        pass


def _capture_timer_console() -> dict[str, Any] | None:
    print("\nDirekt-Timer (Konsolen-Fallback)")
    print("Enter startet die Uhr; nach Erreichen des Endzustands erneut Enter drücken.")
    print("Hinweis: Ein Fensterwechsel kann in diesem Fallback die Zeit verfälschen.")
    action = _prompt("Enter = START, A = Abbrechen: ", allow_empty=True)
    if action is None or action:
        return None
    started = time.perf_counter()
    try:
        input("LÄUFT ... Enter = STOPP ")
    except (EOFError, KeyboardInterrupt):
        print("\nTimer abgebrochen.")
        return None
    ended = time.perf_counter()
    return calculate_timer_measurement(ended - started)


def _capture_timer_windows_global() -> dict[str, Any] | None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    WM_HOTKEY = 0x0312
    MOD_NOREPEAT = 0x4000
    VK_F8 = 0x77
    VK_F10 = 0x79
    HOTKEY_TOGGLE = 0xB501
    HOTKEY_CANCEL = 0xB502

    registered_toggle = bool(user32.RegisterHotKey(None, HOTKEY_TOGGLE, MOD_NOREPEAT, VK_F8))
    registered_cancel = bool(user32.RegisterHotKey(None, HOTKEY_CANCEL, MOD_NOREPEAT, VK_F10))
    if not (registered_toggle and registered_cancel):
        if registered_toggle:
            user32.UnregisterHotKey(None, HOTKEY_TOGGLE)
        if registered_cancel:
            user32.UnregisterHotKey(None, HOTKEY_CANCEL)
        print("Globale Hotkeys F8/F10 konnten nicht registriert werden.")
        print("Es wird auf den Konsolen-Timer zurückgefallen.")
        return _capture_timer_console()

    print("\nDirekt-Timer – globale Windows-Hotkeys")
    print("  F8  = START / STOPP")
    print("  F10 = Messung abbrechen")
    print("Wechsle jetzt zum GuildGearChecker und positioniere Maus/Fokus für den Messablauf.")
    print("Drücke F8 möglichst unmittelbar am definierten Startpunkt; beim vollständigen Endzustand erneut F8.")
    print("Die Hotkeys funktionieren auch, wenn dieses Konsolenfenster nicht im Vordergrund ist.")

    msg = wintypes.MSG()
    started: float | None = None
    try:
        while True:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result == -1:
                raise OSError("Windows-Hotkey-Nachricht konnte nicht gelesen werden.")
            if result == 0:
                return None
            if msg.message != WM_HOTKEY:
                continue
            if int(msg.wParam) == HOTKEY_CANCEL:
                print("Messung abgebrochen.")
                _beep(440, 100)
                return None
            if int(msg.wParam) != HOTKEY_TOGGLE:
                continue
            if started is None:
                started = time.perf_counter()
                print("START – Timer läuft ...", flush=True)
                _beep(1000, 70)
            else:
                ended = time.perf_counter()
                measurement = calculate_timer_measurement(ended - started)
                print(f"STOPP – {measurement['duration_seconds_text']} s", flush=True)
                _beep(700, 90)
                return measurement
    finally:
        user32.UnregisterHotKey(None, HOTKEY_TOGGLE)
        user32.UnregisterHotKey(None, HOTKEY_CANCEL)


def _capture_timer_measurement() -> dict[str, Any] | None:
    if sys.platform == "win32":
        return _capture_timer_windows_global()
    return _capture_timer_console()


def _record_run(session: dict[str, Any], results_path: Path) -> None:
    point = _choose_point()
    if point is None:
        return
    mode = _choose_mode(point)
    if mode is None:
        return
    _print_point(point, mode, session)
    try:
        number = next_run_number(session, point.identifier, mode)
    except ValueError as exc:
        print(exc)
        return
    method = _choose_measurement_method(session, point, mode)
    if method is None:
        return

    if method == METHOD_TIMER:
        print(f"Direkt-Timer – Lauf {number} von {RUNS_PER_BLOCK}.")
        calculated = _capture_timer_measurement()
        if calculated is None:
            return
        print(f"Gemessene Zeit: {calculated['duration_seconds_text']} s")
        if not _confirm("Messung bestätigen und speichern?"):
            print("Messung verworfen; Statistik und Datei bleiben unverändert.")
            return
        note = _prompt("Optionale Bemerkung (Enter = keine): ", allow_empty=True)
        add_timer_run(
            session, point.identifier, mode, float(calculated["duration_seconds"]), note or ""
        )
    else:
        print(f"Frame-Modus – Lauf {number} von {RUNS_PER_BLOCK}.")
        fps = _prompt_float("FPS der Aufnahme: ")
        if fps is None:
            return
        start_frame = _prompt_frame("Startframe: ")
        if start_frame is None:
            return
        end_frame = _prompt_frame("Endframe: ")
        if end_frame is None:
            return
        try:
            calculated = calculate_frame_measurement(fps, start_frame, end_frame)
        except ValueError as exc:
            print(f"Messung verworfen: {exc}")
            return
        print(f"Differenz: {calculated['frame_delta']} Frames – Zeit: {calculated['duration_seconds_text']} s")
        if not _confirm("Messung bestätigen und speichern?"):
            print("Messung verworfen; Statistik und Datei bleiben unverändert.")
            return
        note = _prompt("Optionale Bemerkung (Enter = keine): ", allow_empty=True)
        add_run(session, point.identifier, mode, fps, start_frame, end_frame, note or "")

    save_session(results_path, session)
    print(f"Gespeichert: {results_path}")


def _print_summary(session: dict[str, Any]) -> None:
    print("\nPERF-ID   Modus  Methode Läufe   Median     Mittel     Min        Max        Status")
    print("-" * 88)
    for row in summary_rows(session):
        stats = row["statistics"] or {}
        print(
            f"{row['perf_id']:<10}{row['mode'].upper():<7}{_method_label(row['method']):<8}"
            f"{row['runs']:>1}/{RUNS_PER_BLOCK:<5}{_seconds(stats.get('median')):<11}"
            f"{_seconds(stats.get('mean')):<11}{_seconds(stats.get('minimum')):<11}"
            f"{_seconds(stats.get('maximum')):<11}{row['status']}"
        )


def _correct_run(session: dict[str, Any], results_path: Path) -> None:
    point = _choose_point()
    if point is None:
        return
    mode = _choose_mode(point)
    if mode is None:
        return
    existing = runs_for(session, point.identifier, mode)
    if not existing:
        print("Für diesen Messblock gibt es keine gespeicherten Läufe.")
        return
    method = block_method(session, point.identifier, mode) or METHOD_FRAME
    _print_point(point, mode, session)
    print(f"Messmethode: {_method_label(method)}")
    for run in existing:
        if method == METHOD_TIMER:
            detail = "Direkt-Timer"
        else:
            detail = f"{run['start_frame']}→{run['end_frame']} @ {run['fps']:g} FPS"
        print(f"  Lauf {run['run_number']}: {float(run['duration_seconds']):.3f} s ({detail})")
    raw_number = _prompt("Laufnummer für Korrektur (Enter = zurück): ", allow_empty=True)
    if not raw_number:
        return
    try:
        number = int(raw_number)
    except ValueError:
        print("Ungültige Laufnummer.")
        return
    action = _prompt("[E]rsetzen oder [L]öschen (Enter = zurück): ", allow_empty=True)
    if not action:
        return
    if action.casefold() in {"l", "löschen", "loeschen"}:
        if _confirm(f"Lauf {number} wirklich entfernen?"):
            remove_run(session, point.identifier, mode, number)
            save_session(results_path, session)
            print("Einzelmessung entfernt.")
        return
    if action.casefold() not in {"e", "ersetzen"}:
        print("Unbekannte Korrekturaktion.")
        return

    if method == METHOD_TIMER:
        print("Timer-Lauf wird neu gemessen.")
        calculated = _capture_timer_measurement()
        if calculated is None:
            return
        print(f"Neue Zeit: {calculated['duration_seconds_text']} s")
        if not _confirm("Korrektur speichern?"):
            return
        note = _prompt("Optionale Bemerkung (Enter = keine): ", allow_empty=True)
        replace_timer_run(
            session, point.identifier, mode, number, float(calculated["duration_seconds"]), note or ""
        )
    else:
        fps = _prompt_float("Neue FPS: ")
        start_frame = _prompt_frame("Neuer Startframe: ") if fps is not None else None
        end_frame = _prompt_frame("Neuer Endframe: ") if start_frame is not None else None
        if fps is None or start_frame is None or end_frame is None:
            return
        try:
            calculated = calculate_frame_measurement(fps, start_frame, end_frame)
        except ValueError as exc:
            print(f"Korrektur verworfen: {exc}")
            return
        print(f"Neue Zeit: {calculated['duration_seconds_text']} s")
        if not _confirm("Korrektur speichern?"):
            return
        note = _prompt("Optionale Bemerkung (Enter = keine): ", allow_empty=True)
        replace_run(session, point.identifier, mode, number, fps, start_frame, end_frame, note or "")

    save_session(results_path, session)
    print("Einzelmessung ersetzt.")


def _edit_environment(session: dict[str, Any], results_path: Path) -> None:
    environment = session.setdefault("environment", {field: "" for field in ENVIRONMENT_FIELDS})
    labels = {
        "computer": "Rechner/CPU", "windows_version": "Windows-Version", "resolution": "Auflösung",
        "windows_scaling": "Windows-Skalierung", "language": "Sprache", "recording_fps": "Aufnahme-FPS",
        "reference_project": "Referenzprojekt", "notes": "Allgemeine Bemerkungen",
    }
    values: dict[str, str] = {}
    print("\nMessumgebung bearbeiten. Leere Eingabe behält den bisherigen Wert.")
    for field in ENVIRONMENT_FIELDS:
        old = str(environment.get(field, ""))
        value = _prompt(f"{labels[field]} [{old}]: ", allow_empty=True)
        if value:
            values[field] = value
    if values:
        update_environment(session, values)
        save_session(results_path, session)
        print("Messumgebung gespeichert.")


def run_console(results_path: Path, export_path: Path) -> int:
    try:
        session = load_or_create_session(results_path)
    except SessionDataError as exc:
        print(f"FEHLER: {exc}")
        print("Die vorhandene Datei wird nicht überschrieben. Bitte sichern und prüfen:")
        print(results_path)
        return 2
    if not results_path.exists():
        save_session(results_path, session)

    print("GuildGearChecker v0.9.1 – Performance-Baseline-Hilfe")
    print("Direkt-Timer: unter Windows global mit F8 start/stop; Frame-Modus bleibt verfügbar.")
    print("Messmethoden werden innerhalb eines PERF-/COLD-WARM-Blocks niemals gemischt.")
    while True:
        _print_summary(session)
        print("\n1 Messlauf erfassen   2 Einzelwert korrigieren   3 Messumgebung")
        print("4 Markdown exportieren   0 Beenden")
        choice = _prompt("Auswahl: ", allow_empty=True)
        if choice is None or choice == "0":
            return 0
        if choice == "1":
            _record_run(session, results_path)
        elif choice == "2":
            _correct_run(session, results_path)
        elif choice == "3":
            _edit_environment(session, results_path)
        elif choice == "4":
            try:
                export_markdown(export_path, session)
                print(f"Markdown-Export erstellt: {export_path}")
            except OSError as exc:
                print(f"Export fehlgeschlagen, bestehende Datei bleibt erhalten: {exc}")
        else:
            print("Unbekannte Auswahl.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lokale Timer-/Frame-Messhilfe für die v0.9.1-Performance-Baseline")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS_PATH, help="JSON-Sitzungsdatei")
    parser.add_argument("--export", action="store_true", help="Vorhandene Sitzung direkt als Markdown exportieren")
    parser.add_argument("--export-path", type=Path, default=DEFAULT_EXPORT_PATH, help="Ziel des Markdown-Exports")
    args = parser.parse_args(argv)
    if args.export:
        try:
            session = load_session(args.results)
            export_markdown(args.export_path, session)
            print(f"Markdown-Export erstellt: {args.export_path}")
            return 0
        except SessionDataError as exc:
            print(f"FEHLER: {exc}")
            return 2
        except OSError as exc:
            print(f"FEHLER beim Export: {exc}")
            return 3
    return run_console(args.results, args.export_path)


if __name__ == "__main__":
    raise SystemExit(main())
