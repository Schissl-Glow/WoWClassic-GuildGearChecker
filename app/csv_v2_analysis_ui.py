"""One read-only bulk review for V2 CSV raids and occurrence-level identity conflicts."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QDialog, QHBoxLayout,
    QHeaderView, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSizePolicy, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from .csv_import import CANONICAL_CLASSES, exact_name_key
from .csv_v2_analysis import (
    CsvAmbiguousMemberMatch, CsvBlockedMemberMatch, CsvRaidImportPlan,
    analyze_csv_raids_for_v2,
    TemporalMatchIndicator,
)
from .csv_v2_materialization import (
    CsvImportDecisions, CsvMemberImportChoice, CsvRaidDecision,
    materialize_csv_raid_import,
)
from .i18n import tr
from .identity_v2 import IdentityV2Store
from .raid_attendance import RAID_TYPES
from .qt_row_hover import install_row_hover


def _table(
    headers: tuple[str, ...], *, tooltips: tuple[str, ...] | None = None,
) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.row_hover = install_row_hover(table)
    table.setHorizontalHeaderLabels(headers)
    table.setSortingEnabled(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setWordWrap(False)
    table.verticalHeader().setDefaultSectionSize(36)
    header = table.horizontalHeader()
    header.setSectionsClickable(True)
    header.setStretchLastSection(False)
    header.setMinimumSectionSize(76)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    for column, title in enumerate(headers):
        header_item = table.horizontalHeaderItem(column)
        if header_item is not None:
            header_item.setToolTip(tooltips[column] if tooltips else title)
    return table


def _item(value: object, *, tooltip: str | None = None) -> QTableWidgetItem:
    item = QTableWidgetItem(str(value))
    if tooltip:
        item.setToolTip(tooltip)
    return item


def _set_column_layout(
    table: QTableWidget, widths: tuple[int, ...], *,
    content_columns: tuple[int, ...] = (), stretch_column: int | None = None,
) -> None:
    """Keep short fields compact and reserve readable space for long text/choices."""
    header = table.horizontalHeader()
    for column, width in enumerate(widths):
        table.setColumnWidth(column, width)
    for column in content_columns:
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
    if stretch_column is not None:
        header.setSectionResizeMode(stretch_column, QHeaderView.ResizeMode.Stretch)


def _configure_combo(combo: QComboBox, minimum_width: int) -> None:
    combo.setMinimumWidth(minimum_width)
    combo.setMinimumHeight(30)
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(max(18, minimum_width // 9))
    combo.view().setMinimumWidth(max(300, minimum_width))


def _existing_raid_label(option) -> str:
    try:
        display_date = date.fromisoformat(option.raid_date).strftime("%d.%m.%Y")
    except ValueError:
        display_date = option.raid_date
    return (
        f"{display_date} · {option.raid_name or '–'} · "
        f"{tr('csv_v2_analysis.participant_count', count=option.participant_count)}"
    )


def temporal_indicator_text(indicator: TemporalMatchIndicator | None) -> str:
    if indicator is None or indicator.relation == "NO_ATTENDANCE_DATA":
        return tr("csv_v2_analysis.temporal_none")
    if indicator.relation == "WITHIN_KNOWN_RANGE":
        return tr("csv_v2_analysis.temporal_within")
    if indicator.relation == "BEFORE_FIRST_ATTENDANCE":
        return tr("csv_v2_analysis.temporal_before", days=indicator.distance_days)
    return tr("csv_v2_analysis.temporal_after", days=indicator.distance_days)


class CsvV2AnalysisDialog(QDialog):
    """Keep choices session-local until the explicit Apply action succeeds."""

    def __init__(self, plan: CsvRaidImportPlan, parent: QWidget | None = None,
                 *, store: IdentityV2Store | None = None):
        super().__init__(parent)
        self.base_plan = plan
        self.plan = plan
        self.store = store
        self.enabled_raid_paths = {item.source_path for item in plan.raid_candidates}
        self.raid_type_overrides: dict[Path, str] = {}
        self._analysis_error = False
        self.selections: dict[tuple[Path, str], str] = {}
        self.raid_decisions: dict[Path, CsvRaidDecision] = {}
        self.new_member_classes: dict[str, str] = {}
        self.new_member_choices: dict[str, CsvMemberImportChoice] = {}
        self.result_store: IdentityV2Store | None = None
        self.result_summary = None
        self._base_raid_rows = list(plan.raid_candidates)
        self._raid_rows = list(plan.raid_candidates)
        self._duplicate_rows = list(plan.possible_duplicates)
        for row in self._duplicate_rows:
            default = self._default_raid_decision(row)
            if default is not None:
                self.raid_decisions[row.source_path] = default
        self._saved_raid_decisions = dict(self.raid_decisions)
        self._new_rows = list(plan.new_member_candidates)
        self._conflict_rows: list[CsvAmbiguousMemberMatch | CsvBlockedMemberMatch] = [
            *plan.ambiguous_member_matches, *plan.blocked_member_matches,
        ]
        self._raid_sort: tuple[int, bool] | None = None
        self._duplicate_sort: tuple[int, bool] | None = None
        self._new_sort: tuple[int, bool] | None = None
        self._conflict_sort: tuple[int, bool] | None = None
        self.setWindowTitle(tr("csv_v2_analysis.title"))
        self.resize(1120, 720)
        layout = QVBoxLayout(self)
        self.summary_label = QLabel(self._summary_text(plan))
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        tabs = QTabWidget()
        self.raid_table = _table((
            tr("csv_v2_analysis.import_enabled"), tr("csv_v2_analysis.date"),
            tr("csv_v2_analysis.raid_type"), tr("csv_v2_analysis.source"),
            tr("csv_v2_analysis.participants"), tr("csv_v2_analysis.status"),
            tr("csv_v2_analysis.target"), tr("csv_v2_analysis.report_url"),
        ))
        self.raid_table.horizontalHeader().sectionClicked.connect(self._sort_raids)
        _set_column_layout(
            self.raid_table, (95, 105, 150, 180, 95, 145, 260, 260),
            content_columns=(0, 1, 4), stretch_column=6,
        )
        self.raid_table.itemChanged.connect(self._raid_enabled_changed)
        self.raid_table.itemSelectionChanged.connect(self._populate_participants)
        self.participant_table = _table((
            tr("csv_v2_analysis.csv_name"), tr("identity_v2_views.class"),
            tr("csv_v2_analysis.v2_assignment"),
            tr("csv_v2_analysis.participant_status"),
        ))
        _set_column_layout(
            self.participant_table, (185, 115, 235, 205), stretch_column=2,
        )
        raid_splitter = QSplitter(Qt.Orientation.Vertical)
        raid_splitter.addWidget(self.raid_table)
        raid_splitter.addWidget(self.participant_table)
        raid_splitter.setStretchFactor(0, 2)
        raid_splitter.setStretchFactor(1, 1)
        tabs.addTab(raid_splitter, tr("csv_v2_analysis.raids_tab"))
        self.duplicate_table = _table((
            tr("csv_v2_analysis.date"), tr("csv_v2_analysis.raid"),
            tr("csv_v2_analysis.participants"),
            tr("csv_v2_analysis.raid_decision"),
            tr("csv_v2_analysis.existing_raid_options"),
            tr("csv_v2_analysis.existing"), tr("csv_v2_analysis.additional"),
        ))
        self.duplicate_table.horizontalHeader().sectionClicked.connect(
            self._sort_duplicates,
        )
        _set_column_layout(
            self.duplicate_table, (95, 105, 95, 280, 300, 110, 125),
            content_columns=(0, 2, 5, 6), stretch_column=4,
        )
        duplicate_page = QWidget()
        duplicate_layout = QVBoxLayout(duplicate_page)
        duplicate_hint = QLabel(tr("csv_v2_analysis.clm_metadata_only_hint"))
        duplicate_hint.setWordWrap(True)
        duplicate_layout.addWidget(duplicate_hint)
        duplicate_layout.addWidget(self.duplicate_table, 1)
        tabs.addTab(duplicate_page, tr("csv_v2_analysis.duplicates_tab"))
        self.conflict_table = _table((
            tr("csv_v2_analysis.date"), tr("csv_v2_analysis.raid"),
            tr("csv_v2_analysis.csv_name"), tr("csv_v2_analysis.options"),
            tr("csv_v2_analysis.selection"),
        ))
        self.conflict_table.horizontalHeader().sectionClicked.connect(self._sort_conflicts)
        _set_column_layout(
            self.conflict_table, (95, 105, 125, 440, 265),
            content_columns=(0,), stretch_column=4,
        )
        tabs.addTab(self.conflict_table, tr("csv_v2_analysis.conflicts_tab"))
        self.new_table = _table((
            tr("csv_v2_analysis.csv_name"), tr("csv_v2_analysis.source"),
            tr("identity_v2_views.class"), tr("csv_v2_analysis.import_classification"),
            tr("csv_v2_analysis.blocker"),
        ))
        self.new_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection,
        )
        self.new_table.horizontalHeader().sectionClicked.connect(self._sort_new)
        _set_column_layout(
            self.new_table, (155, 200, 150, 330, 320),
            stretch_column=4,
        )
        new_page = QWidget()
        new_layout = QVBoxLayout(new_page)
        new_hint = QLabel(tr("csv_v2_analysis.new_only_csv"))
        new_hint.setWordWrap(True)
        new_layout.addWidget(new_hint)
        new_layout.addWidget(self.new_table, 1)
        tabs.addTab(new_page, tr("csv_v2_analysis.new_tab"))
        self.warning_text = QTextEdit()
        self.warning_text.setReadOnly(True)
        self.warning_text.setPlainText("\n".join(plan.warnings))
        tabs.addTab(self.warning_text, tr("csv_v2_analysis.warnings_tab"))
        layout.addWidget(tabs, 1)
        bulk_actions = QHBoxLayout()
        self.bulk_active_button = QPushButton(tr("csv_v2_analysis.bulk_active"))
        self.bulk_active_button.setEnabled(bool(plan.new_member_candidates))
        self.bulk_active_button.clicked.connect(
            lambda: self._classify_open_members("ACTIVE_UNKNOWN"),
        )
        bulk_actions.addWidget(self.bulk_active_button)
        self.bulk_inactive_button = QPushButton(tr("csv_v2_analysis.bulk_inactive"))
        self.bulk_inactive_button.setEnabled(bool(plan.new_member_candidates))
        self.bulk_inactive_button.clicked.connect(
            lambda: self._classify_open_members("INACTIVE_UNKNOWN"),
        )
        bulk_actions.addWidget(self.bulk_inactive_button)
        self.selected_irrelevant_button = QPushButton(
            tr("csv_v2_analysis.selected_irrelevant")
        )
        self.selected_irrelevant_button.setEnabled(bool(plan.new_member_candidates))
        self.selected_irrelevant_button.clicked.connect(self._ignore_selected_members)
        bulk_actions.addWidget(self.selected_irrelevant_button)
        bulk_actions.addStretch(1)
        layout.addLayout(bulk_actions)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        cancel = QPushButton(tr("common.cancel"))
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        close = QPushButton(tr("common.close"))
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        self.apply_button = QPushButton(tr("csv_v2_analysis.apply"))
        self.apply_button.setEnabled(store is not None)
        self.apply_button.clicked.connect(self._apply_clicked)
        bottom.addWidget(self.apply_button)
        layout.addLayout(bottom)
        self._populate_raids()
        self._populate_duplicates()
        self._populate_conflicts()
        self._populate_new()
        self._update_apply_enabled()

    @staticmethod
    def _occurrence_key(
        row: CsvAmbiguousMemberMatch | CsvBlockedMemberMatch,
    ) -> tuple[Path, str]:
        return row.source_path, exact_name_key(row.csv_name)

    @staticmethod
    def _default_raid_decision(row) -> CsvRaidDecision | None:
        if row.automatic_csv_raid_id:
            return CsvRaidDecision("MERGE_EXISTING", row.automatic_csv_raid_id)
        if row.automatic_clm_raid_ids:
            return CsvRaidDecision(
                "LINK_CLM_RAIDS", existing_raid_ids=row.automatic_clm_raid_ids)
        return None

    def _summary_text(self, plan: CsvRaidImportPlan) -> str:
        return tr(
            "csv_v2_analysis.summary",
            files=len(self._base_raid_rows), raids=len(self.enabled_raid_paths),
            new=sum(item.status == "NEW_RAID" for item in plan.raid_candidates),
            known=len(plan.known_raids), duplicates=len(plan.possible_duplicates),
            attendance=len(plan.attendance_candidates),
            bracket=len(plan.clm_bracket_matches),
            ambiguous=len(plan.ambiguous_member_matches),
            blocked=len(plan.blocked_member_matches),
            new_members=len(plan.new_member_candidates),
            ignored=len(plan.ignored_occurrences),
        )

    def _update_apply_enabled(self) -> None:
        required = {row.source_path for row in self._duplicate_rows}
        self.apply_button.setEnabled(
            self.store is not None and bool(self.enabled_raid_paths)
            and not self._analysis_error and required <= set(self.raid_decisions))

    def _refresh_review_analysis(self) -> None:
        if self.store is None:
            effective = self.base_plan
        elif not self.enabled_raid_paths:
            effective = replace(
                self.base_plan, raid_candidates=(), attendance_candidates=(),
                resolved_member_matches=(), ambiguous_member_matches=(),
                blocked_member_matches=(), new_member_candidates=(),
                existing_death_conflicts=(), known_raids=(),
                possible_duplicates=(), warnings=(), clm_bracket_matches=(),
                ignored_occurrences=(),
            )
        else:
            active = [item.source_path for item in self._base_raid_rows
                      if item.source_path in self.enabled_raid_paths]
            overrides = {source: raid_type for source, raid_type
                         in self.raid_type_overrides.items()
                         if source in self.enabled_raid_paths}
            try:
                effective = analyze_csv_raids_for_v2(
                    self.store, active, raid_type_overrides=overrides)
            except (OSError, ValueError) as exc:
                self._analysis_error = True
                self.apply_button.setEnabled(False)
                QMessageBox.warning(self, tr("csv_v2_analysis.title"), str(exc))
                return
        self._analysis_error = False
        self.plan = effective
        self.summary_label.setText(self._summary_text(effective))
        by_path = {item.source_path: item for item in effective.raid_candidates
                   if item.source_path in self.enabled_raid_paths}
        order = {item.source_path: index for index, item in enumerate(self._raid_rows)}
        self._raid_rows = [
            by_path.get(item.source_path) or replace(
                item, status="DISABLED",
                raid_type=self.raid_type_overrides.get(item.source_path, item.raid_type),
                raid_name=self.raid_type_overrides.get(item.source_path, item.raid_name),
            ) for item in self._base_raid_rows
        ]
        self._raid_rows.sort(key=lambda item: order.get(item.source_path, len(order)))
        previous = {**self._saved_raid_decisions, **self.raid_decisions}
        self.raid_decisions = {}
        for row in effective.possible_duplicates:
            choice = previous.get(row.source_path)
            valid_ids = {option.raid_id for option in row.existing_raid_options}
            clm_ids = {option.raid_id for option in row.existing_raid_options
                       if option.clm_raid_id}
            if choice is not None and (
                    choice.action == "CREATE_NEW"
                    or choice.action == "MERGE_EXISTING"
                    and choice.existing_raid_id in valid_ids
                    or choice.action == "LINK_CLM_RAIDS"
                    and bool(choice.existing_raid_ids)
                    and set(choice.existing_raid_ids) <= clm_ids):
                self.raid_decisions[row.source_path] = choice
            else:
                default = self._default_raid_decision(row)
                if default is not None:
                    self.raid_decisions[row.source_path] = default
        self._saved_raid_decisions.update(self.raid_decisions)
        self._duplicate_rows = list(effective.possible_duplicates)
        self._conflict_rows = [*effective.ambiguous_member_matches,
                               *effective.blocked_member_matches]
        self._new_rows = list(effective.new_member_candidates)
        for button in (self.bulk_active_button, self.bulk_inactive_button,
                       self.selected_irrelevant_button):
            button.setEnabled(bool(self._new_rows))
        self._update_apply_enabled()
        self._populate_raids()
        self._populate_duplicates()
        self._populate_conflicts()
        self._populate_new()

    def _target_label(self, row) -> str:
        if row.status == "DISABLED":
            return "–"
        options = {item.raid_id: item for item in row.existing_raid_options}
        if row.automatic_csv_raid_id:
            chosen = (row.automatic_csv_raid_id,)
        elif row.automatic_clm_raid_ids:
            chosen = row.automatic_clm_raid_ids
        else:
            decision = self.raid_decisions.get(row.source_path)
            if decision is None:
                return tr("csv_v2_analysis.open_raid_choice")
            if decision.action == "CREATE_NEW":
                return tr("csv_v2_analysis.create_separate")
            chosen = (decision.existing_raid_id,) if decision.action == "MERGE_EXISTING" \
                else decision.existing_raid_ids
        return "; ".join(_existing_raid_label(options[raid_id])
                         for raid_id in chosen if raid_id in options) or "–"

    def _raid_enabled_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        source = Path(item.data(Qt.ItemDataRole.UserRole))
        if item.checkState() == Qt.CheckState.Checked:
            self.enabled_raid_paths.add(source)
        else:
            self.enabled_raid_paths.discard(source)
        self._refresh_review_analysis()

    def _raid_type_changed(self, source: Path, raid_type: str) -> None:
        original = next(item.raid_type for item in self._base_raid_rows
                        if item.source_path == source)
        self.raid_decisions.pop(source, None)
        self._saved_raid_decisions.pop(source, None)
        if raid_type == original:
            self.raid_type_overrides.pop(source, None)
        else:
            self.raid_type_overrides[source] = raid_type
        self._refresh_review_analysis()

    def _sort_raids(self, column: int) -> None:
        descending = self._raid_sort == (column, False)
        keys = (
            lambda row: row.source_path in self.enabled_raid_paths,
            lambda row: row.raid_date, lambda row: row.raid_type.casefold(),
            lambda row: row.source_path.name.casefold(),
            lambda row: len(row.participant_names), lambda row: row.status,
            lambda row: self._target_label(row),
            lambda row: row.report_url or "",
        )
        self._raid_rows.sort(key=lambda row: (keys[column](row), str(row.source_path)),
                             reverse=descending)
        self._raid_sort = (column, descending)
        self._populate_raids()

    def _populate_raids(self) -> None:
        table = self.raid_table
        current = table.currentRow()
        selected_raid = (table.item(current, 0).data(Qt.ItemDataRole.UserRole)
                         if current >= 0 and table.item(current, 0) else None)
        scroll = table.verticalScrollBar().value()
        table.blockSignals(True)
        table.setRowCount(len(self._raid_rows))
        selected_row = -1
        status_labels = {
            "NEW_RAID": tr("csv_v2_analysis.status_csv_only"),
            "KNOWN_RAID": tr("csv_v2_analysis.status_clm_linked"),
            "POSSIBLE_DUPLICATE": tr("csv_v2_analysis.status_review"),
            "DISABLED": tr("csv_v2_analysis.status_disabled"),
        }
        for index, row in enumerate(self._raid_rows):
            target_text = self._target_label(row)
            status_text = (tr("csv_v2_analysis.status_csv_reimport")
                           if row.automatic_csv_raid_id and row.status == "KNOWN_RAID"
                           else status_labels.get(row.status, row.status))
            values = ("", row.raid_date, row.raid_type, row.source_path.name,
                      len(row.participant_names),
                      status_text, target_text,
                      row.report_url or "")
            for column, value in enumerate(values):
                item = _item(value, tooltip=(row.report_url if column == 7
                                             else target_text if column == 6 else None))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, str(row.source_path))
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(
                        Qt.CheckState.Checked if row.source_path in self.enabled_raid_paths
                        else Qt.CheckState.Unchecked)
                table.setItem(index, column, item)
            combo = QComboBox()
            _configure_combo(combo, 135)
            current_type = self.raid_type_overrides.get(row.source_path, row.raid_type)
            if current_type not in RAID_TYPES:
                combo.addItem(current_type, current_type)
            for raid_type in RAID_TYPES:
                combo.addItem(raid_type, raid_type)
            combo.setCurrentIndex(combo.findData(current_type))
            combo.currentIndexChanged.connect(
                lambda _index, source=row.source_path, control=combo:
                self._raid_type_changed(source, control.currentData()))
            table.setCellWidget(index, 2, combo)
            if str(row.source_path) == selected_raid:
                selected_row = index
        if selected_row < 0 and self._raid_rows:
            selected_row = 0
        if selected_row >= 0:
            table.selectRow(selected_row)
        table.blockSignals(False)
        table.verticalScrollBar().setValue(scroll)
        self._populate_participants()

    def _populate_participants(self) -> None:
        table = self.participant_table
        current = self.raid_table.currentRow()
        selected = self.raid_table.item(current, 0) if current >= 0 else None
        if selected is None:
            table.setRowCount(0)
            return
        source = Path(selected.data(Qt.ItemDataRole.UserRole))
        plan = self.plan if source in self.enabled_raid_paths else self.base_plan
        raid_candidate = next((item for item in self._raid_rows
                               if item.source_path == source), None)
        decision = self.raid_decisions.get(source)
        linked_clm = bool(raid_candidate and raid_candidate.automatic_clm_raid_ids
                          and not raid_candidate.automatic_csv_raid_id)
        if decision is not None and decision.action == "LINK_CLM_RAIDS":
            linked_clm = True
        elif (decision is not None and decision.action == "MERGE_EXISTING"
              and self.store is not None):
            linked_clm = any(item.raidId == decision.existing_raid_id
                             and item.clmRaidId for item in self.store.raids)
        occurrences = [item for item in plan.attendance_candidates
                       if item.source_path == source]
        members = ({item.memberId: item for item in self.store.members}
                   if self.store is not None else {})
        new_members = {exact_name_key(item.name): item
                       for item in plan.new_member_candidates}
        table.setRowCount(len(occurrences))
        for row_index, occurrence in enumerate(occurrences):
            member_id = occurrence.member_id
            if occurrence.status == "AMBIGUOUS":
                member_id = self.selections.get((source, exact_name_key(
                    occurrence.csv_name)))
            member = members.get(member_id)
            new_candidate = new_members.get(exact_name_key(occurrence.csv_name))
            class_name = (member.className if member is not None else
                          new_candidate.class_name if new_candidate is not None else None)
            if occurrence.status == "IGNORED":
                status = tr("csv_v2_analysis.participant_ignored")
            elif occurrence.status == "NO_ELIGIBLE_MEMBER":
                status = tr("csv_v2_analysis.participant_blocked")
            elif occurrence.status == "AMBIGUOUS" and member is None:
                status = tr("csv_v2_analysis.participant_ambiguous")
            elif occurrence.existing_attendance:
                status = tr("csv_v2_analysis.participant_existing_attendance")
            elif linked_clm:
                status = tr("csv_v2_analysis.participant_clm_only")
            elif occurrence.status == "NEW_MEMBER_CANDIDATE":
                choice = self.new_member_choices.get(exact_name_key(
                    occurrence.csv_name))
                status = (tr("csv_v2_analysis.participant_ignored")
                          if choice is not None and choice.relevance == "irrelevant"
                          else tr("csv_v2_analysis.participant_new"))
            else:
                status = tr("csv_v2_analysis.participant_existing_member")
            assignment = (member.name if member is not None else
                          tr("csv_v2_analysis.participant_new")
                          if occurrence.status == "NEW_MEMBER_CANDIDATE" else "–")
            values = (occurrence.csv_name, class_name or "–", assignment, status)
            for column, value in enumerate(values):
                item = _item(value, tooltip=(member_id if member_id and column == 2
                                             else None))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole,
                                 (str(source), exact_name_key(occurrence.csv_name)))
                table.setItem(row_index, column, item)

    def _sort_duplicates(self, column: int) -> None:
        descending = self._duplicate_sort == (column, False)
        keys = (
            lambda row: row.raid_date, lambda row: row.raid_name.casefold(),
            lambda row: len(row.participant_names),
            lambda row: self.raid_decisions.get(row.source_path, CsvRaidDecision("")).action,
            lambda row: ", ".join(option.raid_id for option in row.existing_raid_options),
            lambda row: row.existing_attendance_count,
            lambda row: row.additional_attendance_count,
        )
        self._duplicate_rows.sort(
            key=lambda row: (keys[column](row), str(row.source_path)),
            reverse=descending,
        )
        self._duplicate_sort = (column, descending)
        self._populate_duplicates()

    def _populate_duplicates(self) -> None:
        table = self.duplicate_table
        current = table.currentRow()
        selected_source = (table.item(current, 0).data(Qt.ItemDataRole.UserRole)
                           if current >= 0 and table.item(current, 0) else None)
        scroll = table.verticalScrollBar().value()
        table.setRowCount(len(self._duplicate_rows))
        selected_row = -1
        for index, row in enumerate(self._duplicate_rows):
            options_text = "; ".join(
                f"{_existing_raid_label(option)} · "
                f"{tr('csv_v2_analysis.confirmed_overlap', count=option.overlap_count)}"
                for option in row.existing_raid_options
            ) or "–"
            values = {
                0: row.raid_date, 1: row.raid_name,
                2: len(row.participant_names),
                4: options_text, 5: row.existing_attendance_count,
                6: row.additional_attendance_count,
            }
            for column, value in values.items():
                item = _item(value, tooltip=(options_text if column == 4 else None))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, str(row.source_path))
                table.setItem(index, column, item)
            if str(row.source_path) == selected_source:
                selected_row = index
            choices = QListWidget()
            choices.setMinimumWidth(270)
            choices.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            choices.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            choices.setSpacing(2)
            available_options = list(row.existing_raid_options)
            chosen = self.raid_decisions.get(row.source_path)
            chosen_ids = (
                set(chosen.existing_raid_ids)
                if chosen and chosen.action == "LINK_CLM_RAIDS"
                else {chosen.existing_raid_id}
                if chosen and chosen.action == "MERGE_EXISTING"
                else set()
            )
            new_item = QListWidgetItem(tr("csv_v2_analysis.create_separate"))
            new_item.setData(Qt.ItemDataRole.UserRole, "CREATE_NEW")
            new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            new_item.setCheckState(
                Qt.CheckState.Checked if chosen and chosen.action == "CREATE_NEW"
                else Qt.CheckState.Unchecked
            )
            choices.addItem(new_item)
            for option in available_options:
                item = QListWidgetItem(_existing_raid_label(option))
                item.setData(Qt.ItemDataRole.UserRole, option.raid_id)
                item.setData(int(Qt.ItemDataRole.UserRole) + 1,
                             bool(option.clm_raid_id))
                item.setData(Qt.ItemDataRole.ToolTipRole,
                             f"{_existing_raid_label(option)} · raidId={option.raid_id}"
                             + (f" · clmRaidId={option.clm_raid_id}"
                                if option.clm_raid_id else ""))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if option.raid_id in chosen_ids
                                   else Qt.CheckState.Unchecked)
                choices.addItem(item)
            choices.itemChanged.connect(
                lambda changed, source=row.source_path, control=choices:
                self._raid_choice_changed(source, control, changed)
            )
            table.setCellWidget(index, 3, choices)
            table.setRowHeight(index, min(176, max(74, 33 * choices.count())))
        if selected_row >= 0:
            table.selectRow(selected_row)
        table.verticalScrollBar().setValue(scroll)

    def _raid_choice_changed(
        self, source: Path, choices: QListWidget, changed: QListWidgetItem,
    ) -> None:
        if changed.checkState() == Qt.CheckState.Checked:
            choices.blockSignals(True)
            try:
                if changed.data(Qt.ItemDataRole.UserRole) == "CREATE_NEW":
                    for index in range(1, choices.count()):
                        choices.item(index).setCheckState(Qt.CheckState.Unchecked)
                else:
                    choices.item(0).setCheckState(Qt.CheckState.Unchecked)
                    chosen_is_clm = bool(changed.data(
                        int(Qt.ItemDataRole.UserRole) + 1))
                    for index in range(1, choices.count()):
                        option = choices.item(index)
                        if option is changed:
                            continue
                        if (not chosen_is_clm or not option.data(
                                int(Qt.ItemDataRole.UserRole) + 1)):
                            option.setCheckState(Qt.CheckState.Unchecked)
            finally:
                choices.blockSignals(False)
        if choices.item(0).checkState() == Qt.CheckState.Checked:
            self.raid_decisions[source] = CsvRaidDecision("CREATE_NEW")
            self._saved_raid_decisions[source] = self.raid_decisions[source]
            self._update_apply_enabled()
            self._populate_raids()
            return
        selected_ids = tuple(
            choices.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(1, choices.count())
            if choices.item(index).checkState() == Qt.CheckState.Checked
        )
        if selected_ids:
            if len(selected_ids) == 1 and any(
                    choices.item(index).data(Qt.ItemDataRole.UserRole) == selected_ids[0]
                    and not choices.item(index).data(int(Qt.ItemDataRole.UserRole) + 1)
                    for index in range(1, choices.count())):
                self.raid_decisions[source] = CsvRaidDecision(
                    "MERGE_EXISTING", existing_raid_id=selected_ids[0])
            else:
                self.raid_decisions[source] = CsvRaidDecision(
                    "LINK_CLM_RAIDS", existing_raid_ids=selected_ids,
                )
        else:
            self.raid_decisions.pop(source, None)
        if source in self.raid_decisions:
            self._saved_raid_decisions[source] = self.raid_decisions[source]
        else:
            self._saved_raid_decisions.pop(source, None)
        self._update_apply_enabled()
        self._populate_raids()

    def _sort_conflicts(self, column: int) -> None:
        descending = self._conflict_sort == (column, False)
        keys = (
            lambda row: row.raid_date, lambda row: row.raid_name.casefold(),
            lambda row: row.csv_name.casefold(),
            lambda row: ", ".join(option.member_id for option in row.options),
            lambda row: self.selections.get(self._occurrence_key(row), ""),
        )
        self._conflict_rows.sort(key=lambda row: (
            keys[column](row), str(row.source_path), exact_name_key(row.csv_name),
        ), reverse=descending)
        self._conflict_sort = (column, descending)
        self._populate_conflicts()

    def _populate_conflicts(self) -> None:
        table = self.conflict_table
        current = table.currentRow()
        selected_occurrence = (table.item(current, 0).data(Qt.ItemDataRole.UserRole)
                               if current >= 0 and table.item(current, 0) else None)
        scroll = table.verticalScrollBar().value()
        table.setRowCount(len(self._conflict_rows))
        selected_row = -1
        for index, row in enumerate(self._conflict_rows):
            option_text = "; ".join(
                f"{item.member_id} · {item.class_name or tr('identity_v2_views.unknown_class')} · "
                f"Start {item.raid_start_date or '–'} · "
                f"{item.first_attendance or '–'}–{item.last_attendance or '–'} · "
                f"{temporal_indicator_text(item.temporal)}"
                for item in row.options
            )
            if isinstance(row, CsvAmbiguousMemberMatch) and row.clm_bracket:
                bracket = row.clm_bracket
                context = " · ".join((
                    tr("csv_v2_analysis.clm_before",
                       date=bracket.before_date or "–",
                       members=", ".join(bracket.before_member_ids) or "–"),
                    tr("csv_v2_analysis.clm_after",
                       date=bracket.after_date or "–",
                       members=", ".join(bracket.after_member_ids) or "–"),
                ))
                option_text = f"{context}; {option_text}"
            excluded_text = "; ".join(
                f"{item.member_id} · {item.class_name or tr('identity_v2_views.unknown_class')} · "
                f"{tr('csv_v2_analysis.excluded_after_death', date=item.death_date)}"
                for item in row.excluded_options
            )
            if excluded_text:
                option_text = f"{option_text}; {excluded_text}" if option_text else excluded_text
            for column, value in enumerate((row.raid_date, row.raid_name,
                                            row.csv_name, option_text)):
                item = _item(value, tooltip=(option_text if column == 3 else None))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole,
                                 (str(row.source_path), exact_name_key(row.csv_name)))
                table.setItem(index, column, item)
            if (str(row.source_path), exact_name_key(row.csv_name)) == selected_occurrence:
                selected_row = index
            combo = QComboBox()
            _configure_combo(combo, 250)
            combo.addItem(
                tr("csv_v2_analysis.open_choice") if row.options
                else tr("csv_v2_analysis.no_eligible"), None,
            )
            combo.setEnabled(bool(row.options))
            if row.suggested_member_id:
                combo.setToolTip(tr("csv_v2_analysis.suggestion_hint"))
            for option in row.options:
                marker = "★ " if option.member_id == row.suggested_member_id else ""
                combo.addItem(
                    f"{marker}{option.member_id} · "
                    f"{option.class_name or tr('identity_v2_views.unknown_class')} · "
                    f"{temporal_indicator_text(option.temporal)}",
                              option.member_id)
            chosen_member_id = self.selections.get(self._occurrence_key(row))
            if chosen_member_id:
                combo.setCurrentIndex(combo.findData(chosen_member_id))
            combo.currentIndexChanged.connect(
                lambda _index, occurrence=row, control=combo:
                self._choice_changed(occurrence, control.currentData())
            )
            table.setCellWidget(index, 4, combo)
        if selected_row >= 0:
            table.selectRow(selected_row)
        table.verticalScrollBar().setValue(scroll)

    def _choice_changed(self, row: CsvAmbiguousMemberMatch, member_id: str | None) -> None:
        key = self._occurrence_key(row)
        if member_id is None:
            self.selections.pop(key, None)
        else:
            self.selections[key] = member_id
        self._populate_participants()

    def _sort_new(self, column: int) -> None:
        descending = self._new_sort == (column, False)
        keys = (
            lambda row: row.name.casefold(),
            lambda row: ", ".join(path.name for path in row.source_paths),
            lambda row: self.new_member_classes.get(exact_name_key(row.name),
                                                    row.class_name or ""),
            lambda row: self._classification_token(
                self.new_member_choices.get(exact_name_key(row.name))),
            lambda row: row.blocker,
        )
        self._new_rows.sort(key=lambda row: (keys[column](row), row.name.casefold()),
                            reverse=descending)
        self._new_sort = (column, descending)
        self._populate_new()

    def _populate_new(self) -> None:
        table = self.new_table
        current = table.currentRow()
        selected_name = (table.item(current, 0).data(Qt.ItemDataRole.UserRole)
                         if current >= 0 and table.item(current, 0) else None)
        scroll = table.verticalScrollBar().value()
        table.setRowCount(len(self._new_rows))
        selected_row = -1
        for index, row in enumerate(self._new_rows):
            key = exact_name_key(row.name)
            name_item = _item(row.name)
            name_item.setData(Qt.ItemDataRole.UserRole, key)
            table.setItem(index, 0, name_item)
            table.setItem(index, 1, _item(
                ", ".join(path.name for path in row.source_paths),
            ))
            if key == selected_name:
                selected_row = index
            combo = QComboBox()
            _configure_combo(combo, 135)
            combo.addItem(tr("identity_v2_views.unknown_class"), None)
            for class_name in CANONICAL_CLASSES:
                combo.addItem(class_name, class_name)
            chosen = self.new_member_classes.get(key) or row.class_name
            if chosen:
                combo.setCurrentIndex(combo.findData(chosen))
            combo.currentIndexChanged.connect(
                lambda _index, member_key=key, control=combo:
                self._class_changed(member_key, control.currentData())
            )
            table.setCellWidget(index, 2, combo)
            classification = QComboBox()
            _configure_combo(classification, 300)
            classification.addItem(tr("csv_v2_analysis.open_classification"), None)
            classification.addItem(tr("csv_v2_analysis.active_unknown"), "ACTIVE_UNKNOWN")
            classification.addItem(tr("csv_v2_analysis.inactive_unknown"), "INACTIVE_UNKNOWN")
            if self.store is not None:
                for player in self.store.players:
                    player_label = player.playerName or player.playerId
                    classification.addItem(
                        tr("csv_v2_analysis.active_twink", player=player_label),
                        f"ACTIVE_PLAYER:{player.playerId}",
                    )
                    classification.addItem(
                        tr("csv_v2_analysis.inactive_player", player=player_label),
                        f"INACTIVE_PLAYER:{player.playerId}",
                    )
            classification.addItem(tr("csv_v2_analysis.irrelevant"), "IRRELEVANT")
            token = self._classification_token(self.new_member_choices.get(key))
            if token:
                classification.setCurrentIndex(classification.findData(token))
            classification.currentIndexChanged.connect(
                lambda _index, member_key=key, control=classification:
                self._classification_changed(member_key, control.currentData())
            )
            table.setCellWidget(index, 3, classification)
            table.setItem(index, 4, _item("" if chosen else row.blocker))
        if selected_row >= 0:
            table.selectRow(selected_row)
        table.verticalScrollBar().setValue(scroll)

    def _class_changed(self, key: str, class_name: str | None) -> None:
        if class_name is None:
            self.new_member_classes.pop(key, None)
        else:
            self.new_member_classes[key] = class_name
        for row_index, candidate in enumerate(self._new_rows):
            if exact_name_key(candidate.name) == key:
                blocker = self.new_table.item(row_index, 4)
                if blocker is not None:
                    blocker.setText("" if class_name or candidate.class_name
                                    else candidate.blocker)
                break
        self._populate_participants()

    @staticmethod
    def _classification_token(choice: CsvMemberImportChoice | None) -> str:
        if choice is None:
            return ""
        if choice.relevance == "irrelevant":
            return "IRRELEVANT"
        if choice.player_id:
            return (f"ACTIVE_PLAYER:{choice.player_id}"
                    if choice.activity_status == "active"
                    else f"INACTIVE_PLAYER:{choice.player_id}")
        return ("ACTIVE_UNKNOWN" if choice.activity_status == "active"
                else "INACTIVE_UNKNOWN")

    def _classification_changed(self, key: str, token: str | None) -> None:
        if token is None:
            self.new_member_choices.pop(key, None)
        elif token == "ACTIVE_UNKNOWN":
            self.new_member_choices[key] = CsvMemberImportChoice()
        elif token == "INACTIVE_UNKNOWN":
            self.new_member_choices[key] = CsvMemberImportChoice(activity_status="inactive")
        elif token == "IRRELEVANT":
            self.new_member_choices[key] = CsvMemberImportChoice(relevance="irrelevant")
        elif token.startswith("ACTIVE_PLAYER:"):
            self.new_member_choices[key] = CsvMemberImportChoice(
                player_id=token.partition(":")[2], current_role="twink",
            )
        elif token.startswith("INACTIVE_PLAYER:"):
            self.new_member_choices[key] = CsvMemberImportChoice(
                activity_status="inactive", player_id=token.partition(":")[2],
            )
        self._populate_participants()

    def _classify_open_members(self, token: str) -> None:
        for row in self._new_rows:
            key = exact_name_key(row.name)
            if key not in self.new_member_choices:
                self._classification_changed(key, token)
        self._populate_new()

    def _ignore_selected_members(self) -> None:
        for index in self.new_table.selectionModel().selectedRows():
            item = self.new_table.item(index.row(), 0)
            if item is not None:
                self._classification_changed(
                    item.data(Qt.ItemDataRole.UserRole), "IRRELEVANT",
                )
        self._populate_new()

    def _apply_clicked(self) -> None:
        if self.store is None or self._analysis_error or not self.enabled_raid_paths:
            return
        decisions = CsvImportDecisions(
            raid_decisions=dict(self.raid_decisions),
            member_selections=dict(self.selections),
            new_member_classes=dict(self.new_member_classes),
            new_member_choices=dict(self.new_member_choices),
            active_raid_paths=frozenset(self.enabled_raid_paths),
            raid_type_overrides=dict(self.raid_type_overrides),
        )
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result, summary = materialize_csv_raid_import(
                self.store, self.base_plan, decisions,
            )
        except Exception as exc:
            QMessageBox.warning(self, tr("csv_v2_analysis.title"), str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        answer = QMessageBox.question(
            self, tr("csv_v2_analysis.apply"),
            tr("csv_v2_analysis.apply_summary",
               new_raids=summary.new_raids,
               merged=summary.merged_existing_raids,
               separate=summary.separate_duplicate_raids,
               skipped=summary.existing_attendance_skipped,
               attendance=summary.new_attendance,
               members=summary.new_members,
               ignored=summary.ignored_members,
               linked=summary.clm_metadata_reports,
               csv_names_not_attended=summary.csv_names_not_attended_to_clm,
               csv_extra_names=summary.csv_extra_names_against_clm,
               blockers=0, shifts=summary.raid_start_shifts,
               death=summary.death_conflicts),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.result_store = result
        self.result_summary = summary
        self.accept()
