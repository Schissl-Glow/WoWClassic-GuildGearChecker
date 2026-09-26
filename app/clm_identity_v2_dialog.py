"""One grouped Qt review dialog for all Identity V2 multi-GUID decisions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox, QHeaderView,
    QLabel, QMessageBox, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .clm_identity_v2_analysis import ClmIdentityAnalysis, display_date
from .clm_identity_v2_decisions import (
    CONTINUE, NEW_CHARACTER, ClmIdentityDecisionDraft, ClmIdentityDecisionError,
    ClmIdentityDecisionSet,
)
from .clm_matching import character_key
from .identity_v2 import IdentityV2Store


HEADERS = (
    "Name", "Klasse", "GUID", "Erstes Datum", "Letztes Datum",
    "Abstand", "Status", "Analyse", "Entscheidung",
)
_GROUP_CONFLICT_LABELS = {
    "SAME_RAID_COEXISTENCE": "Gleichzeitig im selben Raid belegt",
    "CLASS_CONFLICT": "Klassenkonflikt",
    "TIME_OVERLAP": "Zeitliche Überlappung",
    "DATA_CONFLICT": "Datenkonflikt",
    "CLASS_UNKNOWN": "Klasse unbekannt",
    "TIME_UNKNOWN": "Zeitfolge unbekannt",
}


class ClmIdentityDecisionDialog(QDialog):
    """Review all groups at once; accept returns decisions, reject returns none."""

    def __init__(
        self, analysis: ClmIdentityAnalysis, parent: QWidget | None = None,
        *, draft: ClmIdentityDecisionDraft | None = None,
        review_group_keys: set[str] | None = None,
        locked_choices: set[tuple[str, str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.draft = draft if draft is not None else ClmIdentityDecisionDraft(analysis)
        self._review_group_keys = review_group_keys
        self._locked_choices = locked_choices or set()
        self.result_value: ClmIdentityDecisionSet | None = None
        self._group_items: dict[str, QTreeWidgetItem] = {}
        self._last_sort_column: int | None = None
        self._sort_descending = False
        self.setWindowTitle("CLM-Identitäten prüfen")

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Alle Namen mit mehreren CLM-GUIDs in einer Maske prüfen. "
            "Die erste GUID beginnt einen Charakter. Für jede folgende GUID "
            "Fortsetzung oder neuen Charakter wählen. Es werden noch keine Daten gespeichert."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(len(HEADERS) + 1)
        self.tree.setHeaderLabels((*HEADERS, "_sort"))
        self.tree.hideColumn(len(HEADERS))
        self.tree.setSortingEnabled(False)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.header().setSectionsClickable(True)
        self.tree.header().sectionClicked.connect(self._header_clicked)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tree.header().setStretchLastSection(False)
        metrics = self.tree.fontMetrics()
        padding = metrics.horizontalAdvance("MMMM")
        self.tree.header().setMinimumSectionSize(max(76, metrics.height() * 3))
        widths = [max(width, metrics.horizontalAdvance(label) + padding)
                  for label, width in zip(
                      HEADERS, (175, 105, 155, 110, 110, 175, 100, 320, 225))]
        for column, width in enumerate(widths):
            self.tree.setColumnWidth(column, width)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        margins = layout.contentsMargins()
        preferred_width = (sum(widths) + self.tree.verticalScrollBar().sizeHint().width()
                           + margins.left() + margins.right() + padding)
        self.resize(
            min(preferred_width, int(available.width() * 0.94)) if available else preferred_width,
            min(850, int(available.height() * 0.86)) if available else 800,
        )
        self.setMinimumSize(800, 430)
        layout.addWidget(self.tree, 1)

        for rank, name_key in enumerate(self.draft.group_order):
            if (self._review_group_keys is not None
                    and name_key not in self._review_group_keys):
                continue
            group = self.draft.group(name_key)
            group_item = QTreeWidgetItem()
            self._group_items[name_key] = group_item
            self.tree.addTopLevelItem(group_item)
            group_item.setText(len(HEADERS), f"{rank:06d}")
            group_item.setText(0, group.normalized_name)
            group_item.setText(1, f"{len(group.guid_histories)} GUIDs")
            group_item.setText(3, self.draft.rows_for(name_key)[0].first_date)
            group_item.setText(4, display_date(max(
                (item.last_seen for item in group.guid_histories if item.last_seen is not None),
                default=None,
            )))
            group_item.setText(7, "; ".join(
                _GROUP_CONFLICT_LABELS.get(code, code) for code in group.conflicts
            ) or "Fortsetzung prüfen")
            if group.conflicts:
                group_item.setForeground(7, QColor("#b15443"))
            for index, row in enumerate(self.draft.rows_for(name_key)):
                item = QTreeWidgetItem(group_item)
                for column, value in enumerate((
                    "", row.character_class, row.guid, row.first_date,
                    row.last_date, row.distance, row.status, row.analysis,
                )):
                    item.setText(column, value)
                history = group.guid_histories[index]
                if history.warnings:
                    item.setToolTip(7, ", ".join(history.warnings))
                if row.forced_new:
                    item.setForeground(7, QColor("#b15443"))
                    item.setText(8, "Neuer Charakter (erforderlich)")
                elif index == 0:
                    item.setText(8, "Erster Charakter")
                else:
                    combo = QComboBox(self.tree)
                    combo.addItem("Bitte entscheiden", None)
                    combo.addItem("Fortsetzung", CONTINUE)
                    combo.addItem("Neuer Charakter", NEW_CHARACTER)
                    choice = self.draft.choice(name_key, row.guid)
                    if choice is not None:
                        combo.setCurrentIndex(combo.findData(choice))
                    if (name_key, row.guid) in self._locked_choices:
                        combo.setEnabled(False)
                    combo.currentIndexChanged.connect(
                        lambda _index, name=name_key, guid=row.guid, box=combo:
                        self._choice_changed(name, guid, box.currentData())
                    )
                    self.tree.setItemWidget(item, 8, combo)
            group_item.setExpanded(True)

        self.status = QLabel(self)
        layout.addWidget(self.status)
        self._refresh_status()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Entscheidungen übernehmen")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self._accept_decisions)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choice_changed(self, name: str, guid: str, action: str | None) -> None:
        self.draft.set_choice(name, guid, action)
        self._refresh_status()

    def _refresh_status(self) -> None:
        open_count = sum(
            self.draft.choice(group.normalized_name, history.guid) is None
            for group in self.draft.analysis.multi_guid_groups
            if (self._review_group_keys is None or
                character_key(group.normalized_name) in self._review_group_keys)
            for history in group.guid_histories[1:]
        )
        group_count = sum(
            self._review_group_keys is None or
            character_key(group.normalized_name) in self._review_group_keys
            for group in self.draft.analysis.multi_guid_groups)
        self.status.setText(
            f"{open_count} offene Entscheidungen · "
            f"{group_count} Multi-GUID-Gruppen"
        )

    def _header_clicked(self, column: int) -> None:
        self._sort_descending = (
            not self._sort_descending if self._last_sort_column == column else False
        )
        self._last_sort_column = column
        selected = self.tree.currentItem()
        scroll = self.tree.verticalScrollBar().value()
        self.draft.sort_groups(column, self._sort_descending)
        for rank, name_key in enumerate(self.draft.group_order):
            if name_key in self._group_items:
                self._group_items[name_key].setText(len(HEADERS), f"{rank:06d}")
        self.tree.invisibleRootItem().sortChildren(len(HEADERS), Qt.SortOrder.AscendingOrder)
        if selected is not None:
            self.tree.setCurrentItem(selected)
        self.tree.verticalScrollBar().setValue(scroll)

    def _accept_decisions(self) -> None:
        try:
            result = self.draft.to_decision_set()
        except ClmIdentityDecisionError as exc:
            QMessageBox.warning(self, "Entscheidungen fehlen", str(exc))
            return
        self.result_value = result
        self.accept()


def collect_clm_identity_decisions(
    analysis: ClmIdentityAnalysis, parent: QWidget | None = None,
    *, target_store: IdentityV2Store | None = None,
) -> ClmIdentityDecisionSet | None:
    """Open one modal review dialog and return only the unpersisted result."""
    draft = None
    review_group_keys = None
    locked_choices = None
    if target_store is not None:
        from .clm_v2_refresh import prepare_clm_identity_refresh_review

        draft, review_group_keys, locked_choices = (
            prepare_clm_identity_refresh_review(target_store, analysis))
        if not review_group_keys:
            return draft.to_decision_set()
    if not analysis.multi_guid_groups:
        return ClmIdentityDecisionDraft(analysis).to_decision_set()
    dialog = ClmIdentityDecisionDialog(
        analysis, parent, draft=draft, review_group_keys=review_group_keys,
        locked_choices=locked_choices)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.result_value
    return None
