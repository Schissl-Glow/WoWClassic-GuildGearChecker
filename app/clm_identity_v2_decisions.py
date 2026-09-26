"""Unpersisted review decisions for Identity V2 multi-GUID groups."""

from __future__ import annotations

from dataclasses import dataclass

from .clm_identity_v2_analysis import (
    ClmGuidHistory, ClmGuidPair, ClmIdentityAnalysis, ClmMultiGuidGroup,
    display_date,
)
from .clm_matching import character_key


CONTINUE = "continue"
NEW_CHARACTER = "new_character"


class ClmIdentityDecisionError(ValueError):
    """A review choice is missing or contradicts the analyzer evidence."""


@dataclass(frozen=True)
class ClmNameDecision:
    normalized_name: str
    ordered_guids: tuple[str, ...]
    character_groups: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class ClmIdentityDecisionSet:
    database_id: str
    roster_id: str
    decisions: tuple[ClmNameDecision, ...]


@dataclass(frozen=True)
class ClmIdentityDecisionRow:
    normalized_name: str
    character_class: str
    guid: str
    first_date: str
    last_date: str
    distance: str
    status: str
    analysis: str
    decision: str | None
    can_continue: bool
    forced_new: bool


def format_distance(pair: ClmGuidPair | None) -> str:
    if pair is None:
        return "–"
    if pair.overlap_days is not None:
        if pair.overlap_days == 0:
            return "Überlappung: gleicher Zeitpunkt"
        return f"Überlappung: {_duration(pair.overlap_days)}"
    if pair.gap_days is not None:
        return _duration(pair.gap_days)
    return "Zeitabstand unbekannt"


def _duration(days: float) -> str:
    seconds = max(0, round(days * 86400))
    if seconds >= 86400:
        value = round(seconds / 86400)
        return f"{value} Tag" if value == 1 else f"{value} Tage"
    if seconds >= 3600:
        value = round(seconds / 3600)
        return f"{value} Stunde" if value == 1 else f"{value} Stunden"
    if seconds >= 60:
        value = round(seconds / 60)
        return f"{value} Minute" if value == 1 else f"{value} Minuten"
    return f"{seconds} Sekunde" if seconds == 1 else f"{seconds} Sekunden"


_CONFLICT_LABELS = {
    "SAME_RAID_COEXISTENCE": "Gleichzeitig im selben Raid belegt – getrennte Charaktere erforderlich",
    "CLASS_CONFLICT": "Klassenkonflikt – getrennte Charaktere erforderlich",
    "TIME_OVERLAP": "Zeitliche Überlappung – getrennt prüfen",
    "DATA_CONFLICT": "Datenkonflikt – getrennt prüfen",
    "CLASS_UNKNOWN": "Klasse unbekannt – getrennt prüfen",
    "TIME_UNKNOWN": "Zeitfolge unbekannt – getrennt prüfen",
}


def _analysis_label(pair: ClmGuidPair | None, history: ClmGuidHistory) -> str:
    if pair is None:
        return "Erste GUID" + (" · Datenkonflikt" if "DATA_CONFLICT" in history.warnings else "")
    if pair.continuation_plausible:
        return "Fortsetzung plausibel"
    return "; ".join(_CONFLICT_LABELS.get(code, code) for code in pair.conflicts)


class ClmIdentityDecisionDraft:
    """Mutable UI draft; it never changes the analyzer or any GGC store."""

    def __init__(self, analysis: ClmIdentityAnalysis) -> None:
        self.analysis = analysis
        self._groups = {
            character_key(group.normalized_name): group
            for group in analysis.multi_guid_groups
        }
        if len(self._groups) != len(analysis.multi_guid_groups):
            raise ClmIdentityDecisionError("Doppelte Multi-GUID-Namensgruppe.")
        self.group_order = list(self._groups)
        self._choices: dict[tuple[str, str], str | None] = {}
        for name_key, group in self._groups.items():
            for index, history in enumerate(group.guid_histories):
                if index == 0:
                    continue
                pair = self._adjacent_pair(group, index)
                self._choices[(name_key, history.guid)] = (
                    None if pair.continuation_plausible else NEW_CHARACTER
                )

    @staticmethod
    def _adjacent_pair(group: ClmMultiGuidGroup, index: int) -> ClmGuidPair:
        older = group.guid_histories[index - 1].guid
        newer = group.guid_histories[index].guid
        pair = next((item for item in group.pairwise
                     if item.older_guid == older and item.newer_guid == newer), None)
        if pair is None:
            raise ClmIdentityDecisionError(f"Zeitvergleich für {older} und {newer} fehlt.")
        return pair

    def group(self, name: str) -> ClmMultiGuidGroup:
        key = character_key(name)
        if key not in self._groups:
            raise ClmIdentityDecisionError(f"Unbekannte Multi-GUID-Gruppe: {name!r}.")
        return self._groups[key]

    def allowed_actions(self, name: str, guid: str) -> tuple[str, ...]:
        group = self.group(name)
        index = next((i for i, item in enumerate(group.guid_histories)
                      if item.guid == guid), None)
        if index is None or index == 0:
            return ()
        pair = self._adjacent_pair(group, index)
        return (CONTINUE, NEW_CHARACTER) if pair.continuation_plausible else (NEW_CHARACTER,)

    def choice(self, name: str, guid: str) -> str | None:
        key = (character_key(name), guid)
        if key not in self._choices:
            raise ClmIdentityDecisionError(f"GUID {guid!r} hat keine wählbare Entscheidung.")
        return self._choices[key]

    def set_choice(self, name: str, guid: str, action: str | None) -> None:
        allowed = self.allowed_actions(name, guid)
        if not allowed:
            raise ClmIdentityDecisionError(f"GUID {guid!r} ist der erste Charakter der Gruppe.")
        if action not in allowed and not (action is None and len(allowed) > 1):
            raise ClmIdentityDecisionError(f"Entscheidung {action!r} ist für {guid!r} unzulässig.")
        self._choices[(character_key(name), guid)] = action

    def rows_for(self, name: str) -> tuple[ClmIdentityDecisionRow, ...]:
        group = self.group(name)
        rows: list[ClmIdentityDecisionRow] = []
        for index, history in enumerate(group.guid_histories):
            pair = self._adjacent_pair(group, index) if index else None
            action = self.choice(name, history.guid) if index else None
            rows.append(ClmIdentityDecisionRow(
                normalized_name=history.normalized_name,
                character_class=history.character_class or "Unbekannt",
                guid=history.guid,
                first_date=display_date(history.first_seen),
                last_date=display_date(history.last_seen),
                distance=format_distance(pair),
                status="Aktiv" if history.active_at_end else "Historisch",
                analysis=_analysis_label(pair, history),
                decision=action,
                can_continue=bool(pair and pair.continuation_plausible),
                forced_new=bool(pair and not pair.continuation_plausible),
            ))
        return tuple(rows)

    def sort_groups(self, column: int, descending: bool = False) -> None:
        """Sort whole groups only when the user clicks a header."""
        if column not in range(9):
            raise ValueError(column)

        def sort_key(name_key: str) -> tuple[object, ...]:
            group = self._groups[name_key]
            first = group.guid_histories[0]
            last = group.guid_histories[-1]
            first_pair = self._adjacent_pair(group, 1)
            distance = (
                -first_pair.overlap_days if first_pair.overlap_days is not None
                else first_pair.gap_days if first_pair.gap_days is not None
                else float("inf")
            )
            selected = {
                0: group.normalized_name.casefold(),
                1: (first.character_class or "Unbekannt").casefold(),
                2: first.guid,
                3: first.first_seen if first.first_seen is not None else -1,
                4: max((item.last_seen or -1) for item in group.guid_histories),
                5: distance,
                6: last.active_at_end,
                7: "; ".join(group.conflicts).casefold(),
                8: sum(self._choices[(name_key, item.guid)] is None
                       for item in group.guid_histories[1:]),
            }[column]
            return selected, name_key

        self.group_order.sort(key=sort_key, reverse=descending)

    def to_decision_set(self) -> ClmIdentityDecisionSet:
        decisions: list[ClmNameDecision] = []
        for name_key, group in self._groups.items():
            histories = group.guid_histories
            character_groups: list[list[str]] = [[histories[0].guid]]
            for history in histories[1:]:
                action = self._choices[(name_key, history.guid)]
                if action is None:
                    raise ClmIdentityDecisionError(
                        f"Für {group.normalized_name} / {history.guid} fehlt eine Entscheidung.")
                if action == CONTINUE:
                    character_groups[-1].append(history.guid)
                else:
                    character_groups.append([history.guid])
            decisions.append(ClmNameDecision(
                normalized_name=group.normalized_name,
                ordered_guids=tuple(history.guid for history in histories),
                character_groups=tuple(tuple(items) for items in character_groups),
            ))
        return ClmIdentityDecisionSet(
            database_id=self.analysis.database_id, roster_id=self.analysis.roster_id,
            decisions=tuple(decisions),
        )
