"""Sicherer Datenparser für ``CLM2_DB`` aus WoW-SavedVariables.

Der Parser versteht ausschließlich die von SavedVariables benötigte
Lua-Datenliteral-Teilmenge. Er führt niemals Lua-Code aus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

try:
    from .clm_models import ClmIntegrationError
except ImportError:
    from clm_models import ClmIntegrationError  # type: ignore


class SavedVariablesParseError(ClmIntegrationError):
    pass


@dataclass(frozen=True)
class SavedVariablesDocument:
    source_path: Path | None
    modified_at: float | None
    variable_name: str
    data: Mapping[object, object]


@dataclass(frozen=True)
class _Token:
    kind: str
    value: object
    position: int


_NUMBER_RE = re.compile(
    r"[+-]?(?:0[xX][0-9A-Fa-f]+|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
)
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PUNCTUATION = {"{": "LBRACE", "}": "RBRACE", "[": "LBRACKET", "]": "RBRACKET",
                "=": "EQUAL", ",": "COMMA", ";": "SEMICOLON"}


def _decode_quoted_string(source: str, start: int) -> tuple[str, int]:
    quote = source[start]
    index = start + 1
    result: list[str] = []
    escapes = {"a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r",
               "t": "\t", "v": "\v", "\\": "\\", '"': '"', "'": "'"}
    while index < len(source):
        char = source[index]
        if char == quote:
            return "".join(result), index + 1
        if char != "\\":
            result.append(char)
            index += 1
            continue
        index += 1
        if index >= len(source):
            break
        escaped = source[index]
        if escaped.isdigit():
            match = re.match(r"\d{1,3}", source[index:])
            assert match is not None
            result.append(chr(int(match.group(0), 10)))
            index += len(match.group(0))
            continue
        if escaped == "z":
            index += 1
            while index < len(source) and source[index].isspace():
                index += 1
            continue
        if escaped == "\n":
            result.append("\n")
            index += 1
            continue
        if escaped == "\r":
            result.append("\n")
            index += 1
            if index < len(source) and source[index] == "\n":
                index += 1
            continue
        result.append(escapes.get(escaped, escaped))
        index += 1
    raise SavedVariablesParseError(f"Nicht abgeschlossene Zeichenkette bei Position {start}.")


def _tokenize(source: str) -> list[_Token]:
    tokens: list[_Token] = []
    index = 0
    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if source.startswith("--[[", index):
            end = source.find("]]", index + 4)
            if end < 0:
                raise SavedVariablesParseError("Nicht abgeschlossener Lua-Kommentar.")
            index = end + 2
            continue
        if source.startswith("--", index):
            end = source.find("\n", index + 2)
            index = len(source) if end < 0 else end + 1
            continue
        if source.startswith("[[", index):
            end = source.find("]]", index + 2)
            if end < 0:
                raise SavedVariablesParseError("Nicht abgeschlossene lange Zeichenkette.")
            tokens.append(_Token("STRING", source[index + 2:end], index))
            index = end + 2
            continue
        if char in {'"', "'"}:
            value, end = _decode_quoted_string(source, index)
            tokens.append(_Token("STRING", value, index))
            index = end
            continue
        number = _NUMBER_RE.match(source, index)
        if number:
            raw = number.group(0)
            if raw.lower().lstrip("+-").startswith("0x"):
                sign = -1 if raw.startswith("-") else 1
                unsigned = raw[1:] if raw[:1] in "+-" else raw
                value: int | float = sign * int(unsigned, 16)
            elif any(marker in raw for marker in ".eE"):
                value = float(raw)
            else:
                value = int(raw, 10)
            tokens.append(_Token("NUMBER", value, index))
            index = number.end()
            continue
        identifier = _IDENT_RE.match(source, index)
        if identifier:
            tokens.append(_Token("IDENT", identifier.group(0), index))
            index = identifier.end()
            continue
        kind = _PUNCTUATION.get(char)
        if kind:
            tokens.append(_Token(kind, char, index))
            index += 1
            continue
        raise SavedVariablesParseError(
            f"Nicht erlaubtes Lua-Element bei Position {index}: {char!r}."
        )
    tokens.append(_Token("EOF", None, len(source)))
    return tokens


class _LiteralParser:
    def __init__(self, tokens: list[_Token], index: int) -> None:
        self.tokens = tokens
        self.index = index

    @property
    def current(self) -> _Token:
        return self.tokens[self.index]

    def _advance(self) -> _Token:
        token = self.current
        self.index += 1
        return token

    def _expect(self, kind: str) -> _Token:
        if self.current.kind != kind:
            raise SavedVariablesParseError(
                f"Erwartet {kind}, gefunden {self.current.kind} "
                f"bei Position {self.current.position}."
            )
        return self._advance()

    def parse_value(self) -> object:
        token = self.current
        if token.kind == "LBRACE":
            return self.parse_table()
        if token.kind in {"STRING", "NUMBER"}:
            return self._advance().value
        if token.kind == "IDENT":
            value = str(self._advance().value)
            if value == "true":
                return True
            if value == "false":
                return False
            if value == "nil":
                return None
            raise SavedVariablesParseError(
                f"Lua-Ausdrücke sind nicht erlaubt: {value!r} bei Position {token.position}."
            )
        raise SavedVariablesParseError(
            f"Datenliteral erwartet bei Position {token.position}."
        )

    def parse_table(self) -> dict[object, object]:
        self._expect("LBRACE")
        result: dict[object, object] = {}
        next_array_index = 1
        while self.current.kind != "RBRACE":
            if self.current.kind == "EOF":
                raise SavedVariablesParseError("Nicht abgeschlossene Lua-Tabelle.")
            if self.current.kind == "LBRACKET":
                self._advance()
                key = self.parse_value()
                self._expect("RBRACKET")
                self._expect("EQUAL")
                value = self.parse_value()
            elif (self.current.kind == "IDENT"
                  and self.tokens[self.index + 1].kind == "EQUAL"):
                key = self._advance().value
                self._expect("EQUAL")
                value = self.parse_value()
            else:
                while next_array_index in result:
                    next_array_index += 1
                key = next_array_index
                next_array_index += 1
                value = self.parse_value()
            if key is None:
                raise SavedVariablesParseError("nil ist kein gültiger Lua-Tabellenschlüssel.")
            if key in result:
                raise SavedVariablesParseError(f"Doppelter Lua-Tabellenschlüssel: {key!r}.")
            result[key] = value
            if self.current.kind in {"COMMA", "SEMICOLON"}:
                self._advance()
            elif self.current.kind != "RBRACE":
                raise SavedVariablesParseError(
                    f"Tabellentrenner erwartet bei Position {self.current.position}."
                )
        self._expect("RBRACE")
        return result


def parse_saved_variable(source: str, variable_name: str = "CLM2_DB") -> Mapping[object, object]:
    tokens = _tokenize(source)
    assignment_index = next((
        index for index, token in enumerate(tokens[:-1])
        if token.kind == "IDENT" and token.value == variable_name
        and tokens[index + 1].kind == "EQUAL"
    ), None)
    if assignment_index is None:
        raise SavedVariablesParseError(f"SavedVariable {variable_name} wurde nicht gefunden.")
    parser = _LiteralParser(tokens, assignment_index + 2)
    value = parser.parse_value()
    if not isinstance(value, Mapping):
        raise SavedVariablesParseError(f"SavedVariable {variable_name} ist keine Lua-Tabelle.")
    return value


def load_saved_variables(
    path: Path | str, variable_name: str = "CLM2_DB",
) -> SavedVariablesDocument:
    source_path = Path(path)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    source = source_path.read_text(encoding="utf-8-sig")
    return SavedVariablesDocument(
        source_path=source_path,
        modified_at=source_path.stat().st_mtime,
        variable_name=variable_name,
        data=parse_saved_variable(source, variable_name),
    )
