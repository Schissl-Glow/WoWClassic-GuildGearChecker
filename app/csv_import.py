"""Shared Warcraft Logs CSV decoding and character-name extraction."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SUPPORTED_CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
CSV_METADATA_KEYS = {
    "META_RAID_TYPE": "raid_type",
    "META_RAID_DATE": "raid_date",
    "META_REPORT_URL": "report_url",
}
CSV_RAID_TYPE_ALIASES = {
    "zulgurub": "zg",
    "zul'gurub": "zg",
    "zul gurub": "zg",
    "molten core": "mc",
    "blackwing lair": "bwl",
    "worldboss": "world boss",
    "world boss": "world boss",
    "azuregos": "world boss",
    "lord kazzak": "world boss",
    "kazzak": "world boss",
    "emeriss": "world boss",
    "lethon": "world boss",
    "taerar": "world boss",
    "ysondre": "world boss",
}


@dataclass(frozen=True)
class RaidCsvMetadata:
    raid_type: str | None = None
    raid_date: str | None = None
    report_url: str | None = None


@dataclass(frozen=True)
class RaidCsvImport:
    names: tuple[str, ...]
    duplicates: tuple[str, ...]
    metadata: RaidCsvMetadata


RAID_CASTS_FILENAME_PATTERN = re.compile(
    r"^(?P<raid_date>\d{4}-\d{2}-\d{2})_(?P<raid_type>.+)_Casts\.csv$",
    re.IGNORECASE,
)


def exact_name_key(value: object) -> str:
    """Return the application's exact, case-insensitive character-name key."""
    return unicodedata.normalize("NFC", str(value or "").strip()).casefold()


def decode_csv_bytes(raw: bytes) -> str:
    """Decode the encodings accepted by the existing member CSV import."""
    for encoding in SUPPORTED_CSV_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Zeichencodierung der CSV konnte nicht erkannt werden.")


def normalize_csv_raid_type(value: object, valid_raid_types: Iterable[str]) -> str | None:
    """Resolve an exact CSV value or explicit alias to an existing raid type."""
    text = unicodedata.normalize("NFC", str(value or "").strip())
    if not text:
        return None
    canonical_by_key = {
        exact_name_key(raid_type): raid_type
        for raid_type in valid_raid_types
        if str(raid_type or "").strip()
    }
    key = exact_name_key(text)
    if key in canonical_by_key:
        return canonical_by_key[key]
    alias_target = CSV_RAID_TYPE_ALIASES.get(key)
    return canonical_by_key.get(alias_target) if alias_target else None


def raid_csv_filename_metadata(path: Path | str) -> RaidCsvMetadata:
    """Read the established date/type fallback from a Casts CSV filename."""
    match = RAID_CASTS_FILENAME_PATTERN.fullmatch(Path(path).name)
    if match is None:
        return RaidCsvMetadata()
    return RaidCsvMetadata(
        raid_type=unicodedata.normalize("NFC", match.group("raid_type").strip()),
        raid_date=match.group("raid_date"),
    )


def _csv_rows(text: str) -> list[list[str]]:
    if not text or not text.strip():
        raise ValueError("CSV ist leer.")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        first_line = text.splitlines()[0] if text.splitlines() else ""
        delimiter = max([",", ";", "\t"], key=first_line.count)
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if not rows:
        raise ValueError("CSV ist leer.")
    return rows


def _split_leading_metadata(
    rows: list[list[str]],
) -> tuple[RaidCsvMetadata, list[list[str]]]:
    values: dict[str, str] = {}
    table_start = 0
    for index, row in enumerate(rows):
        if not any(str(cell).strip() for cell in row):
            table_start = index + 1
            continue
        key = str(row[0] if row else "").lstrip("\ufeff").strip().upper()
        if not key.startswith("META_"):
            table_start = index
            break
        field = CSV_METADATA_KEYS.get(key)
        if field and len(row) > 1:
            values[field] = unicodedata.normalize("NFC", row[1].strip())
        table_start = index + 1
    return RaidCsvMetadata(**values), rows[table_start:]


def detect_raid_csv(text: str) -> RaidCsvImport:
    """Split optional leading metadata from the established Name table."""
    metadata, rows = _split_leading_metadata(_csv_rows(text))
    if not rows:
        raise ValueError("Spalte 'Name' wurde nicht gefunden.")
    headers = [header.lstrip("\ufeff").strip() for header in rows[0]]
    name_index = next(
        (index for index, header in enumerate(headers) if header.casefold() == "name"),
        None,
    )
    if name_index is None:
        raise ValueError("Spalte 'Name' wurde nicht gefunden.")
    seen: set[str] = set()
    result: list[str] = []
    duplicates: list[str] = []
    for row in rows[1:]:
        if row and str(row[0]).lstrip("\ufeff").strip().upper().startswith("META_"):
            continue
        if name_index >= len(row):
            continue
        name = unicodedata.normalize("NFC", row[name_index].strip())
        key = exact_name_key(name)
        if not name:
            continue
        if key in seen:
            duplicates.append(name)
            continue
        seen.add(key)
        result.append(name)
    return RaidCsvImport(tuple(result), tuple(duplicates), metadata)


def detect_csv_name_details(text: str) -> tuple[list[str], list[str]]:
    """Extract unique names and exact duplicate rows without fuzzy matching."""
    parsed = detect_raid_csv(text)
    return list(parsed.names), list(parsed.duplicates)


def detect_csv_names(text: str) -> list[str]:
    """Extract unique names from the Name column without fuzzy matching."""
    return detect_csv_name_details(text)[0]


def read_csv_names(path: Path) -> list[str]:
    """Read a CSV path and extract names through the shared parser."""
    return detect_csv_names(decode_csv_bytes(Path(path).read_bytes()))


def read_csv_name_details(path: Path) -> tuple[list[str], list[str]]:
    """Read a CSV path and return unique names plus duplicate appearances."""
    return detect_csv_name_details(decode_csv_bytes(Path(path).read_bytes()))


def read_raid_csv(path: Path) -> RaidCsvImport:
    """Read a raid CSV including optional leading metadata."""
    return detect_raid_csv(decode_csv_bytes(Path(path).read_bytes()))
