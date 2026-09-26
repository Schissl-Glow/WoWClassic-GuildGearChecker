"""JSON file persistence for the isolated Identity V2 store."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from app.identity_v2 import IDENTITY_FORMAT, IdentityV2Store, IdentityV2ValidationError


def save_identity_v2(store: IdentityV2Store, path: Path | str) -> Path:
    """Write an explicit V2 save; refuse to replace an existing legacy file."""
    target = Path(path)
    if not target.exists():
        return save_new_identity_v2(store, target)
    try:
        existing = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IdentityV2ValidationError(
            "Vorhandene Datei ist kein lesbarer Identity-V2-Save und wird nicht überschrieben.") from exc
    if not isinstance(existing, dict) or existing.get("identityFormat") != IDENTITY_FORMAT:
        raise IdentityV2ValidationError(
            "Vorhandene Datei ist kein Identity-V2-Save und wird nicht überschrieben.")
    payload = store.to_payload()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


def load_identity_v2(path: Path | str) -> IdentityV2Store:
    """Load only files explicitly marked with the Identity V2 format."""
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IdentityV2ValidationError(f"Identity-V2-Datei kann nicht gelesen werden: {source}") from exc
    return IdentityV2Store.from_payload(payload)


def save_new_identity_v2(store: IdentityV2Store, path: Path | str) -> Path:
    """Atomically create a new V2 file without replacing any existing file."""
    target = Path(path)
    payload = store.to_payload()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError as exc:
            raise IdentityV2ValidationError(
                f"Die Zieldatei existiert bereits und wird nicht überschrieben: {target}"
            ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target
