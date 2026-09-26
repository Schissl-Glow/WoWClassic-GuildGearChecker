"""Focused offscreen checks for table hover and stable Qt interaction geometry."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QPushButton, QStyle, QStyleOptionViewItem, QTabWidget,
    QTableWidget, QTableWidgetItem, QWidget,
)

from app.GuildGearCheckerQt import STYLE_SHEET
from app.GuildPortraitGrabberQt import GRABBER_INTERACTION_STYLE
from app.qt_row_hover import install_row_hover


class QtRowHoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_row_hover_is_visual_only_and_selection_and_status_win(self):
        table = QTableWidget(2, 3)
        self.addCleanup(table.close)
        tracker = install_row_hover(table)
        for row in range(2):
            for column in range(3):
                item = QTableWidgetItem(f"{row}:{column}")
                item.setData(Qt.ItemDataRole.UserRole, f"m{row}")
                table.setItem(row, column, item)
        table.item(0, 2).setBackground(QColor("#248447"))
        table.show()
        self.app.processEvents()
        heights = (table.rowHeight(0), table.rowHeight(1))
        widths = tuple(table.columnWidth(column) for column in range(3))
        before = [(table.item(row, column).text(),
                   table.item(row, column).data(Qt.ItemDataRole.UserRole))
                  for row in range(2) for column in range(3)]
        QTest.mouseMove(table.viewport(),
                        table.visualItemRect(table.item(0, 0)).center())
        self.app.processEvents()
        self.assertEqual(tracker.row, 0)
        option = QStyleOptionViewItem()
        option.state = QStyle.StateFlag.State_Enabled
        plain = tracker.paint_option(option, table.model().index(0, 0))
        self.assertEqual(plain.backgroundBrush.color(), QColor("#332b20"))
        self.assertIs(tracker.paint_option(
            option, table.model().index(0, 2)), option)
        option.state |= QStyle.StateFlag.State_Selected
        self.assertIs(tracker.paint_option(
            option, table.model().index(0, 0)), option)
        QApplication.sendEvent(table.viewport(), QEvent(QEvent.Type.Leave))
        self.assertEqual(tracker.row, -1)
        self.assertEqual((table.rowHeight(0), table.rowHeight(1)), heights)
        self.assertEqual(tuple(table.columnWidth(column) for column in range(3)),
                         widths)
        self.assertEqual([(table.item(row, column).text(),
                           table.item(row, column).data(Qt.ItemDataRole.UserRole))
                          for row in range(2) for column in range(3)], before)

    def test_shared_button_and_tab_states_keep_fixed_borders(self):
        self.assertIn('QPushButton[multiSelected="true"]', STYLE_SHEET)
        self.assertIn("#8a5a20", STYLE_SHEET)
        self.assertIn("QToolButton:hover", STYLE_SHEET)
        self.assertIn("QToolButton:disabled", STYLE_SHEET)
        self.assertLess(STYLE_SHEET.index("QPushButton#navButton:hover"),
                        STYLE_SHEET.index("QPushButton#navButton:checked"))
        self.assertIn("QPushButton#navButton:checked:hover", STYLE_SHEET)
        self.assertIn("QPushButton#subnavButton:checked:hover", STYLE_SHEET)
        for style in (STYLE_SHEET, GRABBER_INTERACTION_STYLE):
            self.assertIn("QPushButton:hover", style)
            self.assertIn("QPushButton:pressed", style)
            self.assertIn("QPushButton:disabled", style)
            self.assertIn("QPushButton:focus", style)
            self.assertIn("QTabBar::tab:hover", style)
            self.assertIn("QTabBar::tab:selected", style)
            self.assertIn("QTabBar::tab:disabled", style)
            self.assertIn("border-top:2pxsolidtransparent", style.replace(" ", ""))

        for style in (STYLE_SHEET, GRABBER_INTERACTION_STYLE):
            button = QPushButton("Aktion")
            self.addCleanup(button.close)
            button.setStyleSheet(style)
            button.show()
            self.app.processEvents()
            size = button.size()
            QTest.mouseMove(button, button.rect().center())
            QTest.mousePress(button, Qt.MouseButton.LeftButton)
            QTest.mouseRelease(button, Qt.MouseButton.LeftButton)
            button.setEnabled(False)
            self.app.processEvents()
            self.assertEqual(button.size(), size)

            tabs = QTabWidget()
            self.addCleanup(tabs.close)
            tabs.setStyleSheet(style)
            tabs.addTab(QWidget(), "Erster")
            tabs.addTab(QWidget(), "Zweiter")
            tabs.show()
            self.app.processEvents()
            first_size = tabs.tabBar().tabRect(0).size()
            QTest.mouseMove(tabs.tabBar(), tabs.tabBar().tabRect(0).center())
            tabs.setCurrentIndex(1)
            self.app.processEvents()
            self.assertEqual(tabs.tabBar().tabRect(0).size(), first_size)


if __name__ == "__main__":
    unittest.main()
