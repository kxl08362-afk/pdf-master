"""One command catalog for native menus and the offline command finder."""
from __future__ import annotations

from dataclasses import dataclass
import re

from PySide6.QtCore import Qt, QTimer, QSize, QRect, QEvent
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QLabel, QPushButton, QStyledItemDelegate, QStyle,
)

from ui_icons import icon


@dataclass(frozen=True)
class Command:
    key: str
    category: str
    title: str
    description: str
    keywords: str
    action: QAction


# Descriptions explain the resulting document operation, rather than UI location.
COMMANDS = (
    ("open", "Файл", "Открыть PDF", "Выбрать документ на компьютере", "загрузить файл open"),
    ("images_pdf", "Файл", "PDF из изображений", "Собрать фотографии и сканы в один PDF", "создать фото jpg jpeg png картинки"),
    ("quick_save", "Файл", "Сохранить", "Записать изменения в текущий файл", "save запись"),
    ("save", "Файл", "Сохранить копию", "Выбрать имя и сохранить отдельный PDF", "save as скачать результат"),
    ("merge", "Страницы", "Добавить PDF", "Присоединить страницы другого документа", "объединить склеить merge"),
    ("extract", "Страницы", "Извлечь страницы", "Сохранить нужные страницы отдельным PDF", "разделить split выбрать"),
    ("undo", "Правка", "Отменить", "Вернуть состояние до последнего изменения", "undo назад"),
    ("redo", "Правка", "Повторить", "Повторить отменённое изменение", "redo вернуть"),
    ("view", "Вид", "Просмотр", "Перемещаться по документу без правок", "читать рука режим"),
    ("edit", "Правка", "Править текст", "Выбрать строку на странице и изменить её", "редактировать исправить заменить текст"),
    ("text", "Правка", "Добавить текст", "Напечатать новый текст в выбранном месте", "надпись вставить аннотация"),
    ("stamp", "Правка", "Подпись и печать", "Разместить свою подпись или печать из изображения", "подписать подписывать штамп факсимиле png jpeg"),
    ("find", "Вид", "Найти в документе", "Искать текст в открытом PDF", "поиск find"),
    ("fit", "Вид", "По ширине окна", "Подобрать масштаб страницы к рабочей области", "масштаб zoom размер"),
    ("rotate", "Страницы", "Повернуть страницы", "Повернуть выбранные страницы на 90°", "поворот rotate"),
    ("duplicate", "Страницы", "Дублировать выбранные", "Создать копии выделенных страниц", "копировать копия"),
    ("crop", "Страницы", "Обрезать поля", "Изменить видимую область выбранных страниц", "обрезка crop рамка края"),
    ("up", "Страницы", "Переместить выше", "Поднять текущую страницу в списке", "порядок переставить вверх"),
    ("down", "Страницы", "Переместить ниже", "Опустить текущую страницу в списке", "порядок переставить вниз"),
    ("delete", "Страницы", "Удалить выбранные страницы", "Убрать выделенные страницы из документа", "delete убрать"),
    ("ocr", "Инструменты", "Распознать текст", "Сделать сканы доступными для поиска и правки", "ocr скан распознавание русский английский"),
    ("forms", "Инструменты", "Заполнить форму", "Заполнить текстовые поля и флажки PDF", "анкета бланк acroform checkbox"),
    ("redact", "Инструменты", "Удалить содержимое области", "Безвозвратно убрать текст и изображение в области", "редакция замазать скрыть данные redact"),
    ("export", "Файл", "Сохранить текст", "Выгрузить текст документа в TXT", "экспорт выгрузить txt"),
    ("export_images", "Файл", "Страницы в PNG / JPEG", "Экспортировать страницы в изображения", "экспорт выгрузить фото картинки jpg"),
    ("optimize", "Инструменты", "Оптимизировать PDF", "Оптимизация структуры файла без потери качества", "сжать размер уменьшить compress qpdf"),
)


def normalize_query(value: str) -> str:
    return " ".join(re.findall(r"[\w]+", value.casefold().replace("ё", "е")))


def search_commands(catalog, query: str) -> list[Command]:
    words = normalize_query(query).split()
    if not words:
        return list(catalog)
    matches = []
    for index, command in enumerate(catalog):
        title = normalize_query(command.title)
        searchable = normalize_query(" ".join((command.title, command.category,
            command.description, command.keywords, command.action.shortcut().toString())))
        if all(word in searchable for word in words):
            keywords = normalize_query(command.keywords)
            rank = (0 if title.startswith(" ".join(words)) else
                    1 if all(word in title for word in words) else
                    2 if all(word in keywords for word in words) else 3)
            matches.append((rank, index, command))
    return [row[2] for row in sorted(matches, key=lambda row: row[:2])]


def availability_reason(window, command: Command) -> str:
    if command.action.isEnabled():
        return ""
    if getattr(window, "worker", None):
        return "Дождитесь завершения текущей операции"
    if not getattr(window.engine, "doc", None):
        return "Сначала откройте PDF"
    if command.key == "undo":
        return "Нет изменений для отмены"
    if command.key == "redo":
        return "Нет отменённых изменений"
    return "Недоступно для текущего состояния или разрешений PDF"


class CommandDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(500, 66)

    def paint(self, painter, option, index):
        command = index.data(Qt.ItemDataRole.UserRole)
        if command is None:
            return super().paint(painter, option, index)
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        enabled = command.action.isEnabled()
        rect = option.rect.adjusted(3, 2, -3, -2)
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#FFF1A6"))
            painter.drawRoundedRect(rect, 6, 6)
        left = rect.left() + 12
        width = rect.width() - 24
        base = QFont(option.font)
        base.setPointSizeF(9)
        title_font = QFont(base)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor("#202124" if enabled else "#6E7278"))
        shortcut = command.action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
        shortcut_width = 110 if shortcut else 0
        title_rect = QRect(left, rect.top() + 8, width-shortcut_width, 22)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(command.title, Qt.TextElideMode.ElideRight, title_rect.width()))
        painter.setFont(base)
        painter.setPen(QColor("#646970"))
        if shortcut:
            painter.drawText(QRect(left+width-shortcut_width, rect.top()+8, shortcut_width, 22),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, shortcut)
        detail = f"{command.category} · {command.description}" if enabled else f"{command.category} · Недоступно сейчас"
        detail_rect = QRect(left, rect.top()+32, width, 20)
        painter.drawText(detail_rect, Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(detail, Qt.TextElideMode.ElideRight, detail_rect.width()))
        painter.restore()


class CommandPalette(QDialog):
    """A searchable view of existing actions; execution always rechecks QAction."""
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.catalog = window.command_catalog
        self.setObjectName("commandPalette")
        self.setWindowTitle("Найти команду")
        self.setModal(True)
        self.resize(min(700, window.width()-64), min(610, window.height()-70))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 12)
        layout.setSpacing(12)
        title = QLabel("Найти команду")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.search = QLineEdit()
        self.search.setObjectName("commandSearch")
        self.search.setAccessibleName("Поиск команд")
        self.search.setPlaceholderText("Название действия, например: распознать")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(42)
        layout.addWidget(self.search)
        self.results = QListWidget()
        self.results.setObjectName("commandResults")
        self.results.setAccessibleName("Найденные команды")
        self.results.setItemDelegate(CommandDelegate(self.results))
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setMinimumHeight(190)
        layout.addWidget(self.results, 1)
        self.empty = QLabel("Команды не найдены. Попробуйте другое слово.")
        self.empty.setObjectName("hint")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setMinimumHeight(100)
        layout.addWidget(self.empty)
        self.hint = QLabel()
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        self.hint.setMinimumHeight(34)
        self.hint.setAccessibleName("Доступность команды")
        layout.addWidget(self.hint)
        footer = QHBoxLayout()
        footer.addWidget(QLabel("↑ ↓ выбрать    Enter выполнить    Esc закрыть"), 1)
        close = QPushButton("Закрыть")
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        footer.addWidget(close)
        layout.addLayout(footer)
        self.search.textChanged.connect(self.refresh)
        self.results.currentItemChanged.connect(self.update_hint)
        self.results.itemActivated.connect(self.execute_current)
        self.search.installEventFilter(self)
        self.results.installEventFilter(self)
        for command in self.catalog:
            command.action.changed.connect(self.refresh)
        self._signals_connected = True
        self.finished.connect(self.disconnect_actions)
        self.refresh()
        self.search.setFocus()

    def disconnect_actions(self, *_):
        if not self._signals_connected:
            return
        self._signals_connected = False
        for command in self.catalog:
            try:
                command.action.changed.disconnect(self.refresh)
            except (RuntimeError, TypeError):
                pass

    def refresh(self, *_):
        previous = self.results.currentItem()
        previous_command = previous.data(Qt.ItemDataRole.UserRole) if previous else None
        self.results.clear()
        matches = search_commands(self.catalog, self.search.text())
        selected = 0
        for index, command in enumerate(matches):
            item = QListWidgetItem(command.title + " — " + command.description)
            item.setData(Qt.ItemDataRole.UserRole, command)
            item.setToolTip(command.description + ("\n" + availability_reason(self.window, command)
                if not command.action.isEnabled() else ""))
            # Keep unavailable results inspectable, but execution below always rejects them.
            if not command.action.isEnabled():
                item.setText(item.text() + " — Недоступно")
            self.results.addItem(item)
            if command == previous_command:
                selected = index
        self.empty.setVisible(not matches)
        self.results.setVisible(bool(matches))
        self.results.setCurrentRow(selected if matches else -1)
        self.update_hint()
        self.results.setMinimumHeight(min(190, 66 * max(1, len(matches))))
        self.resize(self.width(), min(self.window.height()-70, 220 + 66*min(len(matches), 6)))

    def update_hint(self, *_):
        item = self.results.currentItem()
        command = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.hint.setText(availability_reason(self.window, command) if command else "")

    def execute_current(self, *_):
        item = self.results.currentItem()
        if not item:
            return
        command = item.data(Qt.ItemDataRole.UserRole)
        if not command.action.isEnabled():
            self.update_hint()
            return
        self.accept()
        # Do not stack a file dialog or processing dialog above the command dialog.
        QTimer.singleShot(0, lambda: command.action.trigger() if command.action.isEnabled() else None)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.execute_current()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.reject()
                return True
            if watched is self.search and event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                count = self.results.count()
                if count:
                    step = 1 if event.key() == Qt.Key.Key_Down else -1
                    self.results.setCurrentRow((self.results.currentRow()+step) % count)
                return True
        return super().eventFilter(watched, event)


def show_command_palette(window):
    existing = getattr(window, "command_palette", None)
    if existing is not None and existing.isVisible():
        existing.raise_()
        existing.search.setFocus()
        return existing
    dialog = CommandPalette(window)
    window.command_palette = dialog
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.finished.connect(lambda *_: setattr(window, "command_palette", None))
    dialog.open()
    return dialog


def install_navigation(window):
    """Build once, after source actions exist. Keep all source QAction ownership."""
    window.command_catalog = tuple(Command(*row, getattr(window, row[0]+"_action")) for row in COMMANDS)
    window.command_action = QAction("Найти команду…", window)
    window.command_action.setShortcut(QKeySequence("Ctrl+K"))
    window.command_action.setToolTip("Найти инструмент или действие · Ctrl+K")
    window.command_action.triggered.connect(lambda: show_command_palette(window))
    window.addAction(window.command_action)
    bar = window.menuBar()
    bar.clear()
    window.navigation_menus = {}
    groups = (
        ("Файл", (("open", "images_pdf"), ("quick_save", "save"), ("export", "export_images"))),
        ("Правка", (("undo", "redo"), ("edit", "text", "stamp"))),
        ("Вид", (("view", "find", "fit"),)),
        ("Страницы", (("merge", "extract"), ("rotate", "duplicate", "crop"), ("up", "down"), ("delete",))),
        ("Инструменты", (("ocr", "forms"), ("redact",), ("optimize",))),
    )
    lookup = {command.key: command for command in window.command_catalog}
    icon_names = {"quick_save": "save", "text": "text", "forms": "form", "export": "text",
                  "export_images": "export", "images_pdf": "images", "rotate": "rotate", "find": "search"}
    for title, sections in groups:
        menu = bar.addMenu("&" + title)
        window.navigation_menus[title] = menu
        for index, section in enumerate(sections):
            if index:
                menu.addSeparator()
            for key in section:
                command = lookup[key]
                command.action.setStatusTip(command.description)
                command.action.setIcon(icon(icon_names.get(key, key)))
                menu.addAction(command.action)
    window.navigation_menus["Файл"].addSeparator()
    exit_action = window.navigation_menus["Файл"].addAction("Выход", window.close)
    exit_action.setShortcut(QKeySequence("Alt+F4"))
    window.navigation_menus["Вид"].addSeparator()
    window.navigation_menus["Вид"].addAction(window.command_action)
    window.command_action.setIcon(icon("commands"))
    help_menu = bar.addMenu("Помо&щь")
    window.navigation_menus["Помощь"] = help_menu
    help_menu.addAction("Как работать", window.show_help)
    help_menu.addAction("О программе", window.show_about)
