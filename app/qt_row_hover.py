"""Subtle whole-row hover for interactive Qt tables without model mutation."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QStyle, QStyledItemDelegate, QStyleOptionViewItem


_HOVER_BRUSH = QBrush(QColor("#332b20"))


class RowHoverTracker(QObject):
    def __init__(self, table: QAbstractItemView) -> None:
        super().__init__(table)
        self.table = table
        self.row = -1
        viewport = table.viewport()
        viewport.setMouseTracking(True)
        viewport.installEventFilter(self)

    def eventFilter(self, watched, event):  # noqa: N802
        table = getattr(self, "table", None)
        if table is None:
            return False
        try:
            viewport = table.viewport()
        except RuntimeError:
            return False
        if watched is viewport:
            if event.type() == QEvent.Type.MouseMove:
                row = table.indexAt(event.position().toPoint()).row()
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.Hide):
                row = -1
            else:
                return False
            if row != self.row:
                self.row = row
                viewport.update()
        return False

    def paint_option(self, option: QStyleOptionViewItem, index):
        if (index.row() != self.row
                or option.state & QStyle.StateFlag.State_Selected
                or index.data(Qt.ItemDataRole.BackgroundRole) is not None):
            return option
        painted = QStyleOptionViewItem(option)
        painted.backgroundBrush = _HOVER_BRUSH
        return painted


class RowHoverDelegate(QStyledItemDelegate):
    def __init__(self, table: QAbstractItemView,
                 tracker: RowHoverTracker) -> None:
        super().__init__(table)
        self.tracker = tracker

    def paint(self, painter, option, index):
        super().paint(painter, self.tracker.paint_option(option, index), index)


def install_row_hover(table: QAbstractItemView, *,
                      custom_delegate: bool = False) -> RowHoverTracker:
    tracker = RowHoverTracker(table)
    if not custom_delegate:
        table.setItemDelegate(RowHoverDelegate(table, tracker))
    return tracker
