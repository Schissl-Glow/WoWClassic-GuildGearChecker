"""Create guild projects in the existing Identity V2 .ggc storage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unicodedata
import uuid

from .clm_detection import identity_key, select_database
from .clm_v2_initialization import inspect_clm_v2_source
from .identity_v2 import (
    IdentityV2Store, POINT_MODE_ETERNAL, POINT_MODE_RAID,
)
from .identity_v2_storage import save_new_identity_v2
from .project_catalog import ProjectCatalog


@dataclass(frozen=True)
class CreatedGuild:
    path: Path
    store: IdentityV2Store


def create_guild(
    guild_name: str, realm: str, point_mode: str,
    *, clm_lua_path: Path | str | None = None,
    projects_root: Path | str | None = None,
    catalog: ProjectCatalog | None = None,
) -> CreatedGuild:
    """Validate inputs and create one empty guild in its own project folder."""
    name = unicodedata.normalize("NFC", str(guild_name or "").strip())
    server = unicodedata.normalize("NFC", str(realm or "").strip())
    if not name or not server:
        raise ValueError("Gildenname und Realm sind Pflichtfelder.")
    if point_mode not in {POINT_MODE_ETERNAL, POINT_MODE_RAID}:
        raise ValueError("Ungültiges Punktesystem.")
    lua: Path | None = None
    if point_mode == POINT_MODE_ETERNAL:
        if clm_lua_path is None:
            raise ValueError("ClassicLootManager.lua ist erforderlich.")
        lua = Path(clm_lua_path).expanduser().resolve()
        if lua.name.casefold() != "classiclootmanager.lua" or not lua.is_file():
            raise ValueError("Eine gültige ClassicLootManager.lua ist erforderlich.")
        inspection = inspect_clm_v2_source(lua)
        matches = [item for item in inspection.databases
                   if item.active and identity_key(item.guild_name) == identity_key(name)
                   and identity_key(item.realm) == identity_key(server)]
        if not matches:
            select_database(inspection.databases, name, server)
    elif clm_lua_path is not None:
        raise ValueError("Raidpunkte-Gilden verwenden keine ClassicLootManager.lua.")

    store = IdentityV2Store(guildName=name, realm=server, pointMode=point_mode)
    store.validate()
    root = (Path(projects_root) if projects_root is not None else
            Path(__file__).resolve().parents[1] / "data" / "projects")
    project = root.expanduser().resolve() / f"guild_{uuid.uuid4().hex}" / "project.ggc"
    saved = save_new_identity_v2(store, project)
    refs = catalog or ProjectCatalog()
    refs.add_project(saved, store=store)
    if lua is not None:
        refs.set_clm_path(saved, lua)
    return CreatedGuild(saved.resolve(), store)
