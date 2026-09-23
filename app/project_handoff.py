"""Projektbezogener, UI-unabhängiger Action-Handoff zwischen Checker und Grabber."""
from __future__ import annotations

import json
import importlib.util
import sys
import time
import uuid
from pathlib import Path
from typing import Iterable, Mapping

try:
    from app.project_storage import atomic_write_json, project_paths
except ImportError:
    _storage_spec = importlib.util.spec_from_file_location(
        "guild_suite_handoff_storage", Path(__file__).resolve().with_name("project_storage.py")
    )
    _storage_module = importlib.util.module_from_spec(_storage_spec)
    sys.modules.setdefault(_storage_spec.name, _storage_module)
    _storage_spec.loader.exec_module(_storage_module)
    atomic_write_json = _storage_module.atomic_write_json
    project_paths = _storage_module.project_paths


HANDOFF_FORMAT = "GuildGearCheckerProjectActions"
HANDOFF_VERSION = 1
ACTION_TYPES = {
    "add_members",
    "update_member_metadata",
    "graveyard_reset",
    "graveyard_save",
}


def new_session_id() -> str:
    return uuid.uuid4().hex


def _clean_token(value: object) -> str:
    token = str(value or "").strip()
    if not token or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in token):
        raise ValueError("Ungültiger Handoff-Token.")
    return token


def make_action(action_type: str, data: Mapping[str, object], *,
                token: str | None = None) -> dict:
    kind = str(action_type or "").strip()
    if kind not in ACTION_TYPES:
        raise ValueError(f"Unbekannter Handoff-Aktionstyp: {kind}")
    return {
        "token": _clean_token(token or uuid.uuid4().hex),
        "type": kind,
        "data": dict(data),
    }


def queue_action(project_path: Path | str, session_id: str, action_type: str,
                 data: Mapping[str, object], *, token: str | None = None) -> str:
    """Schreibt genau eine Aktion atomar; parallele Aktionen teilen keine Schreibdatei."""
    session = str(session_id or "").strip()
    if not session:
        raise ValueError("Für den laufenden Checker-Handoff fehlt die Session-ID.")
    action = make_action(action_type, data, token=token)
    envelope = {
        "format": HANDOFF_FORMAT,
        "formatVersion": HANDOFF_VERSION,
        "sessionId": session,
        "actions": [action],
    }
    folder = project_paths(project_path).handoff
    atomic_write_json(folder / f"{time.time_ns()}-{action['token']}.action.json", envelope)
    return action["token"]


def pending_actions(
    project_path: Path | str,
    session_id: str,
    processed_tokens: Iterable[str] = (),
    known_file_signatures: set[tuple[str, int, int]] | None = None,
) -> list[dict]:
    folder = project_paths(project_path).handoff
    if not folder.is_dir():
        if known_file_signatures is not None:
            known_file_signatures.clear()
        return []
    session = str(session_id or "").strip()
    processed = set(processed_tokens)
    actions: list[dict] = []
    current_signatures: set[tuple[str, int, int]] = set()
    for path in sorted(folder.glob("*.action.json")):
        try:
            stat = path.stat()
            signature = (path.name, int(stat.st_mtime_ns), int(stat.st_size))
            current_signatures.add(signature)
            if known_file_signatures is not None and signature in known_file_signatures:
                continue
            try:
                text = path.read_text(encoding="utf-8-sig")
            except OSError:
                continue
            try:
                payload = json.loads(text)
            except (ValueError, json.JSONDecodeError):
                if known_file_signatures is not None:
                    known_file_signatures.add(signature)
                continue
            if (not isinstance(payload, dict)
                    or payload.get("format") != HANDOFF_FORMAT
                    or payload.get("formatVersion") != HANDOFF_VERSION
                    or payload.get("sessionId") != session
                    or not isinstance(payload.get("actions"), list)):
                if known_file_signatures is not None:
                    known_file_signatures.add(signature)
                continue
            has_pending_action = False
            for action in payload["actions"]:
                if not isinstance(action, dict):
                    continue
                token = str(action.get("token") or "")
                if token and token not in processed:
                    actions.append(action)
                    has_pending_action = True
            if known_file_signatures is not None and not has_pending_action:
                known_file_signatures.add(signature)
        except (OSError, ValueError):
            continue
    if known_file_signatures is not None:
        known_file_signatures.intersection_update(current_signatures)
    return actions


def write_receipt(project_path: Path | str, session_id: str, token: str,
                  result: Mapping[str, object]) -> Path:
    clean_token = _clean_token(token)
    payload = {
        "format": HANDOFF_FORMAT,
        "formatVersion": HANDOFF_VERSION,
        "sessionId": str(session_id or "").strip(),
        "token": clean_token,
        "processedAtNs": time.time_ns(),
        "result": dict(result),
    }
    target = project_paths(project_path).handoff / f"{clean_token}.receipt.json"
    return atomic_write_json(target, payload)


def read_receipt(project_path: Path | str, session_id: str,
                 token: str) -> dict | None:
    target = project_paths(project_path).handoff / f"{_clean_token(token)}.receipt.json"
    try:
        payload = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if (not isinstance(payload, dict)
            or payload.get("format") != HANDOFF_FORMAT
            or payload.get("formatVersion") != HANDOFF_VERSION
            or payload.get("sessionId") != str(session_id or "").strip()
            or payload.get("token") != token
            or not isinstance(payload.get("result"), dict)):
        return None
    return dict(payload["result"])


def apply_actions(model, actions: Iterable[Mapping[str, object]],
                  processed_tokens: set[str] | None = None) -> dict:
    """Wendet Entity-Aktionen über die vorhandenen GuildModel-Regeln an."""
    processed = processed_tokens if processed_tokens is not None else set()
    receipts: list[dict] = []
    changed = False
    graveyard_changed = False
    for raw in actions:
        token = str(raw.get("token") or "").strip()
        if not token or token in processed:
            continue
        processed.add(token)
        kind = str(raw.get("type") or "").strip()
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        try:
            if kind == "add_members":
                records = data.get("members") if isinstance(data.get("members"), list) else []
                summary = model.import_grabber_members(records, source="Portrait Grabber")
                action_changed = bool(summary.get("added"))
            elif kind == "update_member_metadata":
                action_changed = model.update_member_metadata(
                    str(data.get("memberId") or ""), data.get("race"), data.get("className"),
                )
                summary = {"updated": int(action_changed)}
            elif kind == "graveyard_reset":
                model.reset_gravestone_adjustment(str(data.get("memberId") or ""))
                action_changed = True
                graveyard_changed = True
                summary = {"reset": 1}
            elif kind == "graveyard_save":
                member_id = str(data.get("memberId") or "")
                member = model.find_by_id(member_id)
                if member is None:
                    raise ValueError("Charakter wurde im Projekt nicht gefunden.")
                model.set_gravestone_adjustment(
                    member_id, str(data.get("graveTemplateId") or ""),
                    data.get("portraitOffsetX", 0.0), data.get("portraitOffsetY", 0.0),
                    data.get("portraitZoom", 1.0), data.get("textOffsetX", 0.0),
                    data.get("textOffsetY", 0.0), data.get("textScale", 1.0),
                    data.get("deathDate") or member.deathDate,
                )
                action_changed = True
                graveyard_changed = True
                summary = {"saved": 1}
            else:
                raise ValueError(f"Unbekannter Handoff-Aktionstyp: {kind}")
            changed = changed or action_changed
            receipts.append({"token": token, "ok": True, "summary": summary})
        except Exception as exc:
            receipts.append({"token": token, "ok": False, "error": str(exc)})
    return {"changed": changed, "graveyardChanged": graveyard_changed, "receipts": receipts}


def apply_actions_to_project(project_path: Path | str,
                             actions: Iterable[Mapping[str, object]]) -> dict:
    """Standalone-Pfad: frisch laden, Entity-Aktionen anwenden, atomar speichern."""
    try:
        from app.GuildGearChecker import GuildModel
    except ImportError:
        from GuildGearChecker import GuildModel  # type: ignore
    project = project_paths(project_path).project
    model = GuildModel()
    model.load(project)
    result = apply_actions(model, actions)
    if result["changed"]:
        model.save(project, backup=True)
    return result
