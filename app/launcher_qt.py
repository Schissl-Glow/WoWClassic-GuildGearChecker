"""The first visible Qt window: choose or create a guild project."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QLinearGradient,
    QPainter, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QRadioButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from app.app_info import APP_NAME, APP_VERSION
from app.i18n import get_language, set_language, tr
from app.identity_v2 import IdentityV2Store, POINT_MODE_ETERNAL, POINT_MODE_RAID
from app.identity_v2_storage import load_identity_v2
from app.project_catalog import ProjectCatalog, ProjectEntry
from app.qt_theme import (
    BG, BLUE, GOLD, LAUNCHER_STYLE_SHEET, decorative_font_family,
)

if TYPE_CHECKING:
    from app.guild_projects import CreatedGuild


BANNER_PATH = Path(__file__).resolve().parents[1] / "assets" / "startmenu_banner.jpg"


def _refresh_style(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _shortened(label: QLabel, value: str, width: int) -> None:
    label.setText(QFontMetrics(label.font()).elidedText(
        value, Qt.TextElideMode.ElideRight, width))
    label.setToolTip(value)


def _opened_text(value: str | None) -> str:
    if not value:
        return tr("launcher.never_opened")
    try:
        stamp = datetime.fromisoformat(value).astimezone()
        pattern = "%d.%m.%Y %H:%M" if get_language() == "de" else "%Y-%m-%d %H:%M"
        return tr("launcher.last_opened", date=stamp.strftime(pattern))
    except ValueError:
        return tr("launcher.never_opened")


class BannerHeader(QFrame):
    """Optional asset, scaled without distortion and with a dark text overlay."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(138)
        self._image = QPixmap(str(BANNER_PATH))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 17, 25, 15)
        title_column = QVBoxLayout()
        title_column.setSpacing(2)
        self.title_label = QLabel("GuildGearChecker")
        self.title_label.setObjectName("launcherTitle")
        family = decorative_font_family()
        self.title_label.setFont(QFont(family, 25))
        self.title_label.setStyleSheet(
            f'font-family: "{family}"; font-size: 25pt; color: #f3ead7; background: transparent;')
        self.version_label = QLabel(f"Version {APP_VERSION}")
        self.version_label.setObjectName("launcherVersion")
        title_column.addWidget(self.title_label)
        title_column.addWidget(self.version_label)
        title_column.addStretch(1)
        layout.addLayout(title_column)
        layout.addStretch(1)
        language_column = QVBoxLayout()
        language_column.setSpacing(0)
        language_row = QHBoxLayout()
        language_row.setSpacing(5)
        self.de_button = QPushButton("DE")
        self.en_button = QPushButton("EN")
        for button in (self.de_button, self.en_button):
            button.setObjectName("languageButton")
            button.setFixedWidth(44)
            button.setFixedHeight(29)
        separator = QLabel("|")
        separator.setStyleSheet("background:transparent;color:#d0d5da;")
        language_row.addWidget(self.de_button)
        language_row.addWidget(separator)
        language_row.addWidget(self.en_button)
        language_column.addLayout(language_row)
        language_column.addStretch(1)
        layout.addLayout(language_column)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._image.isNull():
            fallback = QLinearGradient(0, 0, self.width(), self.height())
            fallback.setColorAt(0, QColor(BG))
            fallback.setColorAt(1, QColor(BLUE))
            painter.fillRect(self.rect(), fallback)
        else:
            scaled = self._image.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap((self.width() - scaled.width()) // 2,
                               (self.height() - scaled.height()) // 2, scaled)
        overlay = QLinearGradient(0, 0, self.width(), 0)
        overlay.setColorAt(0, QColor(12, 16, 21, 230))
        overlay.setColorAt(0.57, QColor(12, 16, 21, 95))
        overlay.setColorAt(1, QColor(12, 16, 21, 120))
        painter.fillRect(self.rect(), overlay)
        painter.setPen(QColor(GOLD))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class GuildCard(QFrame):
    clicked = Signal(str)
    relocate_requested = Signal(str)
    remove_requested = Signal(str)
    confirm_remove_requested = Signal(str)

    def __init__(self, entry: ProjectEntry, *, recent: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("guildCard")
        self.setProperty("recent", recent)
        self.setProperty("missing", entry.missing)
        self.setProperty("pressed", False)
        self.setProperty("card", True)
        self.setFixedHeight(115 if entry.missing else 89 if recent else 76)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if not entry.missing
                            else Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor if not entry.missing
                       else Qt.CursorShape.ArrowCursor)
        body = QVBoxLayout(self)
        body.setContentsMargins(17, 8, 17, 8)
        body.setSpacing(3)
        first = QHBoxLayout()
        self.name_label = QLabel()
        name_font = QFont("Segoe UI", 13 if recent else 11)
        name_font.setBold(True)
        self.name_label.setFont(name_font)
        _shortened(self.name_label, entry.guild_name or entry.path.stem, 490)
        first.addWidget(self.name_label, 1)
        self.mode_label = QLabel(tr(
            "launcher.eternal_dkp" if entry.point_mode == POINT_MODE_ETERNAL
            else "launcher.raid_points"))
        self.mode_label.setStyleSheet("color:#e1c183;background:transparent;")
        first.addWidget(self.mode_label)
        if not entry.missing:
            self.menu_button = QPushButton("⋯")
            self.menu_button.setObjectName("cardMenuButton")
            self.menu_button.setFixedSize(28, 26)
            self.menu_button.setToolTip(tr("launcher.card_actions"))
            self.menu_button.setAccessibleName(tr("launcher.card_actions"))
            self.menu_button.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation)
            self.card_menu = QMenu(self.menu_button)
            self.remove_menu_action = self.card_menu.addAction(tr("launcher.remove"))
            self.remove_menu_action.triggered.connect(
                lambda: self.confirm_remove_requested.emit(str(entry.path)))
            self.menu_button.clicked.connect(lambda: self.card_menu.popup(
                self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft())))
            first.addWidget(self.menu_button)
        body.addLayout(first)
        second = QHBoxLayout()
        self.realm_label = QLabel()
        self.realm_label.setObjectName("launcherMuted")
        _shortened(self.realm_label, entry.realm, 420)
        second.addWidget(self.realm_label, 1)
        self.date_label = QLabel(tr("launcher.missing") if entry.missing
                                 else _opened_text(entry.last_opened_at))
        self.date_label.setObjectName("launcherMuted")
        second.addWidget(self.date_label)
        body.addLayout(second)
        if entry.missing:
            actions = QHBoxLayout()
            self.relocate_button = QPushButton(tr("launcher.relocate"))
            self.remove_button = QPushButton(tr("launcher.remove"))
            self.relocate_button.clicked.connect(
                lambda: self.relocate_requested.emit(str(entry.path)))
            self.remove_button.clicked.connect(
                lambda: self.remove_requested.emit(str(entry.path)))
            actions.addWidget(self.relocate_button)
            actions.addWidget(self.remove_button)
            actions.addStretch(1)
            body.addLayout(actions)
        for label in (self.name_label, self.mode_label,
                      self.realm_label, self.date_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setToolTip(str(entry.path))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self.entry.missing and event.button() == Qt.MouseButton.LeftButton:
            self.setProperty("pressed", True)
            _refresh_style(self)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        pressed = bool(self.property("pressed"))
        self.setProperty("pressed", False)
        _refresh_style(self)
        if (pressed and self.isEnabled() and self.rect().contains(event.position().toPoint())
                and not self.entry.missing):
            self.clicked.emit(str(self.entry.path))
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if (not self.entry.missing and self.isEnabled()
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)):
            self.clicked.emit(str(self.entry.path))
            event.accept()
            return
        super().keyPressEvent(event)


class NewGuildDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(550, 320)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        form = QFormLayout()
        form.setSpacing(12)
        self.name_label = QLabel()
        self.name_edit = QLineEdit()
        self.realm_label = QLabel()
        self.realm_edit = QLineEdit()
        self.point_label = QLabel()
        modes = QHBoxLayout()
        modes.setSpacing(20)
        self.eternal_radio = QRadioButton()
        self.raid_radio = QRadioButton()
        self.raid_radio.setChecked(True)
        modes.addWidget(self.eternal_radio)
        modes.addWidget(self.raid_radio)
        modes.addStretch(1)
        mode_widget = QWidget()
        mode_widget.setLayout(modes)
        form.addRow(self.name_label, self.name_edit)
        form.addRow(self.realm_label, self.realm_edit)
        form.addRow(self.point_label, mode_widget)
        root.addLayout(form)
        self.lua_row = QWidget()
        lua_layout = QHBoxLayout(self.lua_row)
        lua_layout.setContentsMargins(0, 0, 0, 0)
        self.lua_label = QLabel("ClassicLootManager.lua")
        self.lua_edit = QLineEdit()
        self.lua_browse = QPushButton()
        self.lua_browse.clicked.connect(self._browse_lua)
        lua_layout.addWidget(self.lua_label)
        lua_layout.addWidget(self.lua_edit, 1)
        lua_layout.addWidget(self.lua_browse)
        root.addWidget(self.lua_row)
        root.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton()
        self.create_button = QPushButton()
        self.create_button.setProperty("primary", True)
        self.cancel_button.clicked.connect(self.reject)
        self.create_button.clicked.connect(self.accept)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.create_button)
        root.addLayout(buttons)
        self.eternal_radio.toggled.connect(self._update_mode)
        self._update_mode()
        self.retranslate_ui()

    def _update_mode(self) -> None:
        self.lua_row.setVisible(self.eternal_radio.isChecked())

    def _browse_lua(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, tr("launcher.select_lua"), self.lua_edit.text(),
            "ClassicLootManager.lua (ClassicLootManager.lua);;Lua (*.lua)")
        if path:
            self.lua_edit.setText(path)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("launcher.new_title"))
        self.name_label.setText(tr("launcher.guild_name"))
        self.realm_label.setText(tr("launcher.realm"))
        self.point_label.setText(tr("launcher.point_system"))
        self.eternal_radio.setText(tr("launcher.eternal_dkp"))
        self.raid_radio.setText(tr("launcher.raid_points"))
        self.lua_browse.setText(tr("launcher.browse"))
        self.cancel_button.setText(tr("launcher.cancel"))
        self.create_button.setText(tr("launcher.create"))

    def values(self) -> tuple[str, str, str, str | None]:
        mode = POINT_MODE_ETERNAL if self.eternal_radio.isChecked() else POINT_MODE_RAID
        lua = self.lua_edit.text().strip() if mode == POINT_MODE_ETERNAL else None
        return self.name_edit.text().strip(), self.realm_edit.text().strip(), mode, lua

    def accept(self) -> None:
        name, realm, mode, lua = self.values()
        if not name or not realm:
            QMessageBox.warning(self, APP_NAME, tr("launcher.required_fields"))
            return
        if mode == POINT_MODE_ETERNAL and not lua:
            QMessageBox.warning(self, APP_NAME, tr("launcher.required_lua"))
            return
        super().accept()


class LauncherWindow(QMainWindow):
    def __init__(
        self, catalog: ProjectCatalog | None = None, *,
        window_factory: Callable[[IdentityV2Store, Path], QMainWindow] | None = None,
        guild_factory: Callable[..., CreatedGuild] | None = None,
    ) -> None:
        super().__init__()
        self.catalog = catalog or ProjectCatalog()
        self._window_factory = window_factory or self._create_checker
        self._guild_factory = guild_factory or self._create_guild
        self._busy = False
        self.main_window: QMainWindow | None = None
        self._cards: list[GuildCard] = []
        self.setFixedSize(900, 580)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setStyleSheet(LAUNCHER_STYLE_SHEET)
        self._build_ui()
        self.retranslate_ui()

    @staticmethod
    def _create_checker(store: IdentityV2Store, path: Path) -> QMainWindow:
        from app.GuildGearCheckerQt import GuildGearCheckerQt
        return GuildGearCheckerQt(store, path)

    @staticmethod
    def _create_guild(name: str, realm: str, mode: str,
                      *, clm_lua_path: str | None,
                      catalog: ProjectCatalog) -> CreatedGuild:
        from app.guild_projects import create_guild
        return create_guild(name, realm, mode, clm_lua_path=clm_lua_path,
                            catalog=catalog)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = BannerHeader()
        self.header.de_button.clicked.connect(lambda: self._choose_language("de"))
        self.header.en_button.clicked.connect(lambda: self._choose_language("en"))
        root.addWidget(self.header)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 15, 24, 12)
        content_layout.setSpacing(8)
        self.recent_title = QLabel()
        self.recent_title.setObjectName("launcherSection")
        content_layout.addWidget(self.recent_title)
        self.recent_host = QWidget()
        self.recent_layout = QVBoxLayout(self.recent_host)
        self.recent_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_layout.setSpacing(0)
        content_layout.addWidget(self.recent_host)
        self.others_title = QLabel()
        self.others_title.setObjectName("launcherSection")
        content_layout.addWidget(self.others_title)
        self.other_scroll = QScrollArea()
        self.other_scroll.setWidgetResizable(True)
        self.other_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.other_container = QWidget()
        self.other_layout = QVBoxLayout(self.other_container)
        self.other_layout.setContentsMargins(0, 0, 2, 0)
        self.other_layout.setSpacing(8)
        self.other_scroll.setWidget(self.other_container)
        content_layout.addWidget(self.other_scroll, 1)
        root.addWidget(content, 1)

        footer = QFrame()
        footer.setObjectName("launcherFooter")
        footer.setFixedHeight(73)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 12, 24, 12)
        footer_layout.setSpacing(9)
        self.new_button = QPushButton()
        self.new_button.setProperty("primary", True)
        self.add_button = QPushButton()
        self.exit_button = QPushButton()
        self.new_button.clicked.connect(self._new_guild)
        self.add_button.clicked.connect(self._add_existing)
        self.exit_button.clicked.connect(self.close)
        self.status_label = QLabel()
        self.status_label.setObjectName("launcherMuted")
        footer_layout.addWidget(self.new_button)
        footer_layout.addWidget(self.add_button)
        footer_layout.addWidget(self.status_label, 1)
        footer_layout.addWidget(self.exit_button)
        root.addWidget(footer)

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def _add_card(self, entry: ProjectEntry, layout: QVBoxLayout,
                  *, recent: bool = False) -> None:
        card = GuildCard(entry, recent=recent)
        card.clicked.connect(self._open_project)
        card.relocate_requested.connect(self._relocate)
        card.remove_requested.connect(self._remove)
        card.confirm_remove_requested.connect(self._confirm_remove)
        layout.addWidget(card)
        self._cards.append(card)

    def refresh_cards(self) -> None:
        self._clear_layout(self.recent_layout)
        self._clear_layout(self.other_layout)
        self._cards.clear()
        sorted_entries = self.catalog.sorted_entries()
        recent = self.catalog.last_project()
        if recent is None:
            recent = next((entry for entry in sorted_entries
                           if entry.last_opened_at is not None), None)
        if recent is None:
            empty = QLabel(tr("launcher.no_recent") if sorted_entries
                           else tr("launcher.empty"))
            empty.setObjectName("launcherMuted")
            empty.setFixedHeight(78)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.recent_layout.addWidget(empty)
        else:
            self._add_card(recent, self.recent_layout, recent=True)
        others = [entry for entry in sorted_entries
                  if recent is None or entry.path != recent.path]
        for entry in others:
            self._add_card(entry, self.other_layout)
        self.other_layout.addStretch(1)
        self.other_container.setMinimumHeight(
            sum(115 if entry.missing else 76 for entry in others)
            + self.other_layout.spacing() * max(0, len(others) - 1))
        self.other_layout.activate()
        self.other_scroll.verticalScrollBar().setValue(0)
        self._set_busy(self._busy)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(f"GuildGearChecker · {APP_VERSION}")
        self.recent_title.setText(tr("launcher.recent"))
        self.others_title.setText(tr("launcher.others"))
        self.new_button.setText(tr("launcher.new_guild"))
        self.add_button.setText(tr("launcher.add_existing"))
        self.exit_button.setText(tr("launcher.exit"))
        self.status_label.setText(tr("launcher.loading") if self._busy else "")
        for language, button in (("de", self.header.de_button),
                                 ("en", self.header.en_button)):
            button.setProperty("active", language == get_language())
            _refresh_style(button)
        self.refresh_cards()

    def _choose_language(self, language: str) -> None:
        if self._busy or language == get_language():
            return
        try:
            set_language(language)
            self.retranslate_ui()
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for widget in (self.new_button, self.add_button, self.exit_button,
                       self.header.de_button, self.header.en_button, *self._cards):
            widget.setEnabled(not busy)
        self.status_label.setText(tr("launcher.loading") if busy else "")

    def _begin_open(self) -> bool:
        if self._busy:
            return False
        self._set_busy(True)
        QApplication.processEvents()
        return True

    def _finish_open(self, store: IdentityV2Store, path: Path) -> None:
        window: QMainWindow | None = None
        try:
            window = self._window_factory(store, path)
            window.show()
            self.catalog.mark_opened(path, store)
            self.main_window = window
            self.close()
        except Exception as exc:
            if window is not None:
                window.hide()
                window.deleteLater()
            self._set_busy(False)
            QMessageBox.critical(self, APP_NAME, tr("launcher.open_failed", error=exc))

    def _open_project(self, raw_path: str) -> None:
        if not self._begin_open():
            return
        try:
            path = Path(raw_path)
            store = load_identity_v2(path)
        except Exception as exc:
            self._set_busy(False)
            self.refresh_cards()
            QMessageBox.critical(self, APP_NAME, tr("launcher.open_failed", error=exc))
            return
        self._finish_open(store, path)

    def _add_existing(self) -> None:
        if self._busy:
            return
        path, _filter = QFileDialog.getOpenFileName(
            self, tr("launcher.select_project"), "", "Guild Gear Checker (*.ggc)")
        if not path:
            return
        try:
            self.catalog.add_project(path)
            self.refresh_cards()
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, tr("launcher.add_failed", error=exc))

    def _relocate(self, old_path: str) -> None:
        if self._busy:
            return
        path, _filter = QFileDialog.getOpenFileName(
            self, tr("launcher.select_project"), "", "Guild Gear Checker (*.ggc)")
        if not path:
            return
        try:
            self.catalog.relocate_project(old_path, path)
            self.refresh_cards()
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, tr("launcher.relocate_failed", error=exc))

    def _remove(self, path: str) -> None:
        if self._busy:
            return
        self.catalog.remove_project(path)
        self.refresh_cards()

    def _remove_dialog(self) -> tuple[QMessageBox, QPushButton]:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(tr("launcher.remove_title"))
        dialog.setText(tr("launcher.remove_question"))
        dialog.setInformativeText(tr("launcher.remove_warning"))
        cancel = dialog.addButton(tr("launcher.cancel"), QMessageBox.ButtonRole.RejectRole)
        remove = dialog.addButton(tr("launcher.remove_action"),
                                  QMessageBox.ButtonRole.DestructiveRole)
        remove.setProperty("danger", True)
        dialog.setDefaultButton(cancel)
        return dialog, remove

    def _ask_remove(self) -> bool:
        dialog, remove = self._remove_dialog()
        dialog.exec()
        return dialog.clickedButton() is remove

    def _confirm_remove(self, path: str) -> None:
        if self._busy or not self._ask_remove():
            return
        self._remove(path)

    def _new_guild(self) -> None:
        if self._busy:
            return
        dialog = NewGuildDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not self._begin_open():
            return
        name, realm, mode, lua = dialog.values()
        try:
            created = self._guild_factory(
                name, realm, mode, clm_lua_path=lua, catalog=self.catalog)
            store = created.store
            if mode == POINT_MODE_ETERNAL:
                from app.clm_v2_initialization_ui import run_clm_v2_initialization
                from app.identity_v2_storage import save_identity_v2

                imported = run_clm_v2_initialization(
                    self, initial_store=store, source_path=lua)
                if imported is None:
                    self._set_busy(False)
                    self.refresh_cards()
                    return
                save_identity_v2(imported, created.path)
                store = imported
        except Exception as exc:
            self._set_busy(False)
            QMessageBox.critical(self, APP_NAME, tr("launcher.create_failed", error=exc))
            return
        self._finish_open(store, created.path)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        screen = (QGuiApplication.screenAt(QCursor.pos()) or self.screen()
                  or QApplication.primaryScreen())
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.x() + (area.width() - self.width()) // 2,
                      area.y() + (area.height() - self.height()) // 2)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    try:
        window = LauncherWindow()
        window.show()
        return app.exec()
    except Exception:
        import traceback

        detail = traceback.format_exc()
        print(detail, file=sys.stderr, flush=True)
        try:
            log_path = Path(__file__).resolve().parents[1] / "logs" / "qt_startup_error.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(detail, encoding="utf-8")
        except OSError:
            pass
        try:
            QMessageBox.critical(None, APP_NAME, tr("checker.qt_start_error")
                                 + "\n\n" + detail)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
