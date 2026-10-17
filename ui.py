"""Russian, offline PDF workbench for Windows 11."""
from __future__ import annotations

import logging
import math
import threading
import tempfile
from pathlib import Path

import pymupdf as fitz
from PySide6.QtCore import Qt, QSize, QRectF, QPointF, QThread, Signal, QTimer
from PySide6.QtGui import QAction, QColor, QPixmap, QIcon, QPen, QBrush, QPainter, QKeySequence, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QToolBar, QFileDialog, QMessageBox, QInputDialog, QLineEdit,
    QTextEdit, QDoubleSpinBox, QCheckBox, QComboBox, QProgressBar, QSplitter,
    QListWidget, QListWidgetItem, QAbstractItemView, QStackedWidget, QFrame,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsPixmapItem,
    QFormLayout, QGroupBox, QMenu, QSizePolicy, QDialog, QDialogButtonBox, QScrollArea, QToolButton,
)

from engine import PdfEngine, PasswordRequired, ocr_pdf, resource_root


from ui_theme import stylesheet
from ui_icons import icon



def parse_page_ranges(value: str, page_count: int) -> list[int]:
    """Parse human, one-based page ranges, preserving the supplied order."""
    result = []
    for part in value.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        limits = part.split("-")
        try:
            if len(limits) == 1:
                candidates = [int(limits[0])]
            elif len(limits) == 2:
                start, end = map(int, limits)
                if end < start:
                    raise ValueError
                candidates = range(start, end + 1)
            else:
                raise ValueError
        except ValueError:
            raise ValueError("Введите номера страниц, например: 1, 3-5, 8.") from None
        for number in candidates:
            if not 1 <= number <= page_count:
                raise ValueError(f"Номера страниц должны быть от 1 до {page_count}.")
            if number - 1 not in result:
                result.append(number - 1)
    if not result:
        raise ValueError("Укажите хотя бы одну страницу.")
    return result


class ActionToolButton(QToolButton):
    """A compact presentation of a shared QAction, preserving its full menu title."""
    def __init__(self, action, text=None, icon_only=False, parent=None):
        super().__init__(parent)
        self.action = action
        self.setText(text if text is not None else action.text())
        self.setIcon(action.icon())
        self.setIconSize(QSize(18, 18))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if icon_only else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setMinimumHeight(34)
        self.setCheckable(action.isCheckable())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(action.text())
        if icon_only:
            self.setFixedWidth(34)
        def sync():
            self.setEnabled(action.isEnabled())
            self.setChecked(action.isChecked())
            self.setIcon(action.icon())
            shortcut = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            self.setToolTip(action.text() + (" · " + shortcut if shortcut else ""))
        action.changed.connect(sync)
        self.clicked.connect(lambda checked=False: action.trigger())
        sync()


class PageView(QGraphicsView):
    clicked = Signal(object)
    moved = Signal(object)
    area_selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setAccessibleName("Страница PDF")
        self.area_mode = False
        self.area_start = None
        self.area_item = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.area_mode:
                self.area_start = self.mapToScene(event.position().toPoint())
                self.area_item = self.scene().addRect(QRectF(self.area_start, self.area_start), QPen(QColor("#A34332"), 2), QBrush(QColor(70, 25, 20, 55)))
                self.area_item.setZValue(10)
                event.accept()
                return
            self.clicked.emit(self.mapToScene(event.position().toPoint()))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.area_mode and self.area_start is not None and self.area_item is not None:
            point = self.mapToScene(event.position().toPoint())
            self.area_item.setRect(QRectF(self.area_start, point).normalized())
            event.accept()
            return
        self.moved.emit(self.mapToScene(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.area_mode and self.area_start is not None:
            rect = QRectF(self.area_start, self.mapToScene(event.position().toPoint())).normalized()
            if self.area_item:
                self.scene().removeItem(self.area_item)
            self.area_start = self.area_item = None
            if rect.width() > 4 and rect.height() > 4:
                self.area_selected.emit(rect)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class PageList(QListWidget):
    order_changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.reordering = False
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)

    def dropEvent(self, event):
        self.reordering = True
        try:
            super().dropEvent(event)
            order = [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
            self.order_changed.emit(order)
        finally:
            self.reordering = False


class BackgroundWorker(QThread):
    progress_changed = Signal(int, int)
    result_ready = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.cancel_event = threading.Event()

    def run(self):
        try:
            result = self.operation(self.progress_changed.emit, self.cancel_event.is_set)
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.result_ready.emit(result)
        except Exception as exc:
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                logging.exception("Background PDF tool failed")
                self.failed.emit(str(exc))


class OcrWorker(QThread):
    progress_changed = Signal(int, int)
    result_ready = Signal(bytes)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, data, pages, parent=None, language="rus+eng", dpi=300,
                 skip_existing_text=True, deskew=False, enhance_contrast=False):
        super().__init__(parent)
        self.data, self.pages = data, pages
        self.language, self.dpi = language, dpi
        self.skip_existing_text, self.deskew, self.enhance_contrast = skip_existing_text, deskew, enhance_contrast
        self.cancel_event = threading.Event()

    def run(self):
        try:
            output = ocr_pdf(
                self.data, self.pages, language=self.language, dpi=self.dpi,
                progress=lambda done, total: self.progress_changed.emit(done, total),
                cancel=self.cancel_event.is_set,
                skip_existing_text=self.skip_existing_text, deskew=self.deskew,
                enhance_contrast=self.enhance_contrast,
            )
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.result_ready.emit(output)
        except Exception as exc:
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                logging.exception("OCR failed")
                self.failed.emit(str(exc))


class FormsDialog(QDialog):
    def __init__(self, fields, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Заполнить PDF-форму")
        self.resize(650, 570)
        self.editors = {}
        layout = QVBoxLayout(self)
        note = QLabel("Меняются существующие текстовые поля и флажки. Остальные типы и поля только для чтения показаны без возможности изменения.")
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for field in fields:
            supported = field.get("supported", False) and not field.get("readonly", False)
            if field["type"] == "checkbox":
                editor = QCheckBox("Отмечено")
                editor.setChecked(bool(field.get("value")))
            else:
                editor = QLineEdit(str(field.get("value") or ""))
            editor.setEnabled(supported)
            editor.setObjectName(f"form_{field['xref']}")
            editor.setAccessibleName(field.get("label") or field.get("name") or "Поле")
            label = field.get("label") or field.get("name") or "Без названия"
            label += f" · стр. {field['page'] + 1}"
            if not supported:
                label += "\nТолько чтение" if field.get("readonly") else f"\nТип «{field['type']}» не поддерживается"
            form.addRow(label, editor)
            if supported:
                self.editors[field["xref"]] = editor
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Применить поля")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return {xref: editor.isChecked() if isinstance(editor, QCheckBox) else editor.text()
                for xref, editor in self.editors.items()}


class ImagesToPdfDialog(QDialog):
    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDF из изображений")
        self.resize(620, 520)
        layout = QVBoxLayout(self)
        note = QLabel("Порядок строк — порядок страниц. Перетащите изображения или используйте кнопки. Все кадры многостраничного TIFF включаются последовательно.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.files = QListWidget()
        self.files.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.files.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.files.setAccessibleName("Порядок изображений для PDF")
        for path in paths:
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.files.addItem(item)
        self.files.setCurrentRow(0)
        layout.addWidget(self.files, 1)
        row = QHBoxLayout()
        for text, offset in [("Выше ↑", -1), ("Ниже ↓", 1)]:
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, offset=offset: self.move_current(offset))
            row.addWidget(button)
        layout.addLayout(row)
        self.page_size = QComboBox()
        self.page_size.addItem("Размер исходного изображения", "original")
        self.page_size.addItem("Лист A4 — вписать без растяжения", "a4")
        layout.addWidget(self.page_size)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Создать PDF")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def move_current(self, offset):
        row = self.files.currentRow()
        target = row + offset
        if row >= 0 and 0 <= target < self.files.count():
            item = self.files.takeItem(row)
            self.files.insertItem(target, item)
            self.files.setCurrentRow(target)

    def ordered_paths(self):
        return [self.files.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.files.count())]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        font_path = resource_root() / "fonts" / "DejaVuSans.ttf"
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
        self.engine = PdfEngine()
        self.current_page = 0
        self.scale = 1.3
        self.mode = "view"
        self.lines = []
        self.selected_line = None
        self.selected_rect = None
        self.overlays = []
        self.selection_item = None
        self.preview_item = None
        self.stamp_path = None
        self.stamp_ratio = 1.0
        self.stamp_pixmap = None
        self._stamp_transform_key = None
        self.stamp_library = None
        self._task_result = None
        self._task_success = None
        self.worker = None
        self.search_results = []
        self.search_index = -1
        self._list_refreshing = False
        self._thumb_generation = 0
        self._thumbnail_pages = set()
        self._thumbnail_placeholder = None
        self.setWindowTitle("PDF Мастер")
        self.resize(1420, 920)
        self.setMinimumSize(1030, 700)
        self.setStyleSheet(stylesheet())
        self._create_actions()
        self._assign_action_icons()
        self._build_ui()
        self.setAcceptDrops(True)
        self._update_actions()
        self.statusBar().showMessage("Локальная работа с PDF · Документы остаются на вашем компьютере")

    def _action(self, text, callback, shortcut=None, checkable=False):
        action = QAction(text, self)
        action.setCheckable(checkable)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        self.addAction(action)
        return action

    def _create_actions(self):
        self.open_action = self._action("Открыть PDF", self.choose_file, "Ctrl+O")
        self.save_action = self._action("Сохранить копию", self.save_copy, "Ctrl+Shift+S")
        self.quick_save_action = self._action("Сохранить", self.quick_save, "Ctrl+S")
        self.undo_action = self._action("Отменить", self.undo, "Ctrl+Z")
        self.redo_action = self._action("Повторить", self.redo, "Ctrl+Y")
        self.ocr_action = self._action("Распознать текст", self.start_ocr)
        self.edit_action = self._action("Править текст", lambda: self.set_mode("edit"), "Ctrl+E", True)
        self.stamp_action = self._action("Подпись / печать", lambda: self.set_mode("stamp"), None, True)
        self.text_action = self._action("Добавить текст", lambda: self.set_mode("add"), None, True)
        self.view_action = self._action("Просмотр", lambda: self.set_mode("view"), "Escape", True)
        self.rotate_action = self._action("Повернуть ↻", self.rotate_page)
        self.delete_action = self._action("Удалить выбранные", self.delete_page)
        self.duplicate_action = self._action("Дублировать выбранные", self.duplicate_pages)
        self.crop_action = self._action("Обрезать поля…", self.crop_dialog)
        self.redact_action = self._action("Удалить содержимое области", lambda: self.set_mode("redact"), None, True)
        self.forms_action = self._action("Заполнить форму…", self.fill_forms_dialog)
        self.images_pdf_action = self._action("PDF из изображений…", self.images_pdf_dialog)
        self.export_images_action = self._action("Страницы в PNG / JPEG…", self.export_images_dialog)
        self.optimize_action = self._action("Оптимизировать PDF…", self.optimize_document)
        self.up_action = self._action("Выше ↑", lambda: self.move_page(-1))
        self.down_action = self._action("Ниже ↓", lambda: self.move_page(1))
        self.merge_action = self._action("Добавить PDF", self.merge_pdf)
        self.extract_action = self._action("Извлечь страницы", self.extract_pages)
        self.export_action = self._action("Сохранить текст…", self.export_text)
        self.fit_action = self._action("По ширине", self.fit_width, "Ctrl+0")
        self.find_action = self._action("Найти", lambda: self.search_field.setFocus(), "Ctrl+F")

    def _assign_action_icons(self):
        mapping = {
            "open": "open", "save": "save", "quick_save": "save", "undo": "undo", "redo": "redo",
            "view": "view", "edit": "edit", "text": "text", "stamp": "stamp", "ocr": "ocr",
            "rotate": "rotate", "delete": "delete", "duplicate": "duplicate", "crop": "crop",
            "redact": "redact", "forms": "form", "images_pdf": "images", "export_images": "export",
            "optimize": "optimize", "up": "up", "down": "down", "merge": "merge", "extract": "extract",
            "export": "text", "find": "search", "fit": "fit",
        }
        for name, drawing in mapping.items():
            getattr(self, name + "_action").setIcon(icon(drawing))

    def _build_toolbar(self):
        self.main_toolbar = QToolBar("Основные действия", self)
        self.main_toolbar.setObjectName("mainToolbar")
        self.main_toolbar.setMovable(False)
        self.main_toolbar.setFloatable(False)
        self.main_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.main_toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(self.main_toolbar)
        self.toolbar_buttons = {}
        def add(name, text=None, icon_only=False):
            button = ActionToolButton(getattr(self, name), text, icon_only)
            button.setObjectName("tool_" + name)
            self.toolbar_buttons[name] = button
            self.main_toolbar.addWidget(button)
            return button
        add("open_action", "Открыть")
        save = add("save_action", "Сохранить копию")
        save.setProperty("role", "primary")
        self.main_toolbar.addSeparator()
        add("undo_action", icon_only=True)
        add("redo_action", icon_only=True)
        self.main_toolbar.addSeparator()
        self.mode_segment = QFrame()
        self.mode_segment.setObjectName("modeSegments")
        mode_layout = QHBoxLayout(self.mode_segment)
        mode_layout.setContentsMargins(3, 3, 3, 3)
        mode_layout.setSpacing(2)
        self.mode_buttons = {}
        for mode, title, action in [("view", "Просмотр", self.view_action), ("edit", "Текст", self.edit_action), ("stamp", "Подпись", self.stamp_action)]:
            button = ActionToolButton(action, title)
            button.setObjectName("mode_" + mode)
            self.mode_buttons[mode] = button
            mode_layout.addWidget(button)
        self.main_toolbar.addWidget(self.mode_segment)
        self.main_toolbar.addSeparator()
        add("ocr_action", "Распознать")
        spacer = QWidget()
        spacer.setObjectName("toolbarSpacer")
        spacer.setStyleSheet("background: transparent;")
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.main_toolbar.addWidget(spacer)
        self.command_action.setIcon(icon("commands"))
        add("command_action", "Команды")

    def _build_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.mode_hint = QLabel("Откройте PDF или перетащите его в окно")
        self.mode_hint.setObjectName("modeHint")
        root_layout.addWidget(self.mode_hint)
        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_welcome())
        self.stack.addWidget(self._build_workbench())
        self.setCentralWidget(root)

        self.progress = QProgressBar()
        self.progress.setFixedWidth(200)
        self.progress.hide()
        self.cancel_button = QPushButton("Отменить OCR")
        self.cancel_button.clicked.connect(self.cancel_ocr)
        self.cancel_button.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().addPermanentWidget(self.cancel_button)
        self.page_status = QLabel("")
        self.statusBar().addPermanentWidget(self.page_status)
        from command_menu import install_navigation
        install_navigation(self)
        self._build_toolbar()
        self._build_context_menus()

    def _build_context_menus(self):
        self.page_context_menu = QMenu("Страницы", self)
        self.page_context_menu.setAccessibleName("Действия с выбранными страницами")
        for action in [self.rotate_action, self.duplicate_action, self.crop_action, None,
                       self.up_action, self.down_action, None, self.extract_action,
                       self.export_images_action, None, self.delete_action]:
            self.page_context_menu.addAction(action) if action else self.page_context_menu.addSeparator()
        self.document_context_menu = QMenu("Документ", self)
        self.document_context_menu.setAccessibleName("Инструменты документа")
        for action in [self.view_action, self.edit_action, self.text_action, self.stamp_action, None,
                       self.ocr_action, self.forms_action, self.redact_action, None,
                       self.fit_action, self.command_action]:
            self.document_context_menu.addAction(action) if action else self.document_context_menu.addSeparator()
        self.page_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.page_list.customContextMenuRequested.connect(self._show_page_context)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._show_document_context)
        self.page_context_menu.aboutToShow.connect(self._update_actions)
        self.document_context_menu.aboutToShow.connect(self._update_actions)

    def _show_page_context(self, point):
        item = self.page_list.itemAt(point)
        if item is not None and not item.isSelected():
            self.page_list.setCurrentItem(item)
        self.page_context_menu.popup(self.page_list.viewport().mapToGlobal(point))

    def _show_document_context(self, point):
        self.document_context_menu.popup(self.view.viewport().mapToGlobal(point))


    def _build_welcome(self):
        welcome = QWidget()
        welcome.setObjectName("welcomePage")
        outer = QHBoxLayout(welcome)
        outer.setContentsMargins(58, 36, 58, 36)
        outer.addStretch()
        content = QWidget()
        content.setMaximumWidth(1000)
        columns = QHBoxLayout(content)
        columns.setSpacing(62)
        columns.setContentsMargins(0, 0, 0, 0)
        column = QVBoxLayout()
        column.setSpacing(16)
        column.addStretch(2)
        mark = QLabel()
        mark.setObjectName("welcomeMark")
        mark.setPixmap(icon("document", "#858E9D", 56).pixmap(56, 56))
        column.addWidget(mark)
        eyebrow = QLabel("ВАШ РАБОЧИЙ СТОЛ ДЛЯ PDF")
        eyebrow.setObjectName("eyebrow")
        column.addWidget(eyebrow)
        title = QLabel("PDF Мастер")
        title.setObjectName("title")
        column.addWidget(title)
        description = QLabel("Открывайте, исправляйте\nи подписывайте документы.")
        description.setObjectName("description")
        column.addWidget(description)
        column.addSpacing(8)
        open_button = QPushButton("Открыть PDF")
        open_button.setIcon(icon("open"))
        open_button.setIconSize(QSize(20, 20))
        open_button.setObjectName("primary")
        open_button.setMinimumHeight(46)
        open_button.setMaximumWidth(280)
        open_button.clicked.connect(self.choose_file)
        column.addWidget(open_button)
        shortcut = QLabel("Ctrl+O   или перетащите файл в окно")
        shortcut.setObjectName("hint")
        column.addWidget(shortcut)
        column.addStretch(2)
        local = QLabel("Документы остаются на вашем компьютере.\nВсе инструменты работают без интернета.")
        local.setObjectName("welcomeFootnote")
        column.addWidget(local)
        columns.addLayout(column, 1)
        side = QVBoxLayout()
        side.addStretch()
        quick = QFrame()
        quick.setObjectName("startActions")
        quick_layout = QVBoxLayout(quick)
        quick_layout.setContentsMargins(24, 22, 24, 24)
        quick_layout.setSpacing(7)
        heading = QLabel("С чего начать")
        heading.setObjectName("sectionTitle")
        quick_layout.addWidget(heading)
        quick_layout.addSpacing(10)
        for mode, title, detail, drawing in [
            ("ocr", "Распознать скан", "Русский и английский текст", "ocr"),
            ("edit", "Исправить текст", "Выберите строку и внесите правки", "edit"),
            ("stamp", "Подписать документ", "Своя подпись или печать из файла", "stamp"),
        ]:
            button = QPushButton(title)
            button.setProperty("role", "navigation")
            button.setIcon(icon(drawing))
            button.setIconSize(QSize(21, 21))
            button.clicked.connect(lambda checked=False, mode=mode: self._welcome_workflow(mode))
            quick_layout.addWidget(button)
            detail_label = QLabel(detail)
            detail_label.setObjectName("hint")
            detail_label.setContentsMargins(30, 0, 0, 8)
            quick_layout.addWidget(detail_label)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #E5E8ED;")
        quick_layout.addWidget(divider)
        create = QPushButton("Создать PDF из изображений")
        create.setProperty("role", "navigation")
        create.setIcon(icon("images"))
        create.clicked.connect(self.images_pdf_dialog)
        quick_layout.addWidget(create)
        side.addWidget(quick)
        side.addStretch()
        columns.addLayout(side, 1)
        outer.addWidget(content, 10)
        outer.addStretch()
        return welcome

    def _welcome_workflow(self, mode):
        if self.worker:
            return
        self.choose_file()
        if self.engine.page_count:
            if mode == "ocr":
                self.start_ocr()
            else:
                self.set_mode(mode)

    def _build_workbench(self):
        splitter = QSplitter()
        left = QWidget()
        left.setObjectName("pageSidebar")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 14, 0, 0)
        header = QHBoxLayout()
        header.setContentsMargins(15, 0, 12, 7)
        title = QLabel("Страницы")
        title.setObjectName("eyebrow")
        header.addWidget(title)
        header.addStretch()
        self.sidebar_counter = QLabel("0")
        self.sidebar_counter.setObjectName("hint")
        header.addWidget(self.sidebar_counter)
        left_layout.addLayout(header)
        self.page_list = PageList()
        self.page_list.setObjectName("pageList")
        self.page_list.setIconSize(QSize(85, 115))
        self.page_list.setUniformItemSizes(False)
        self.page_list.setWordWrap(False)
        self.page_list.setAccessibleName("Страницы документа")
        self.page_list.currentRowChanged.connect(self._page_selected)
        self.page_list.itemSelectionChanged.connect(self._update_actions)
        self.page_list.order_changed.connect(self.reorder_pages)
        self.page_list.setToolTip("Ctrl / Shift — выбрать несколько страниц. Перетащите страницы для изменения порядка.")
        left_layout.addWidget(self.page_list)
        left.setMinimumWidth(140)
        left.setMaximumWidth(240)
        splitter.addWidget(left)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        tools = QWidget()
        tools.setObjectName("documentControls")
        line = QHBoxLayout(tools)
        line.setContentsMargins(12, 9, 12, 9)
        line.setSpacing(6)
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Найти в документе…")
        self.search_field.setMaximumWidth(260)
        self.search_field.setMinimumWidth(100)
        self.search_field.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.search_field.returnPressed.connect(self.find_next)
        self.search_field.textChanged.connect(self._reset_search)
        line.addWidget(self.search_field)
        self.find_next_button = QPushButton()
        self.find_next_button.setIcon(icon("down"))
        self.find_next_button.setFixedWidth(33)
        self.find_next_button.setToolTip("Следующее совпадение · Enter")
        self.find_next_button.setAccessibleName("Следующее совпадение")
        self.find_next_button.clicked.connect(self.find_next)
        line.addWidget(self.find_next_button)
        line.addStretch()
        for drawing, label, callback in [("minus", "Уменьшить масштаб", lambda: self.change_zoom(1 / 1.2)), ("plus", "Увеличить масштаб", lambda: self.change_zoom(1.2))]:
            button = QPushButton()
            button.setIcon(icon(drawing))
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.setFixedWidth(34)
            button.clicked.connect(callback)
            line.addWidget(button)
        self.zoom_label = QLabel("130 %")
        self.zoom_label.setMinimumWidth(53)
        line.addWidget(self.zoom_label)
        fit = QPushButton("По ширине")
        fit.setIcon(icon("fit"))
        fit.clicked.connect(self.fit_width)
        line.addWidget(fit)
        center_layout.addWidget(tools)
        self.view = PageView()
        self.view.clicked.connect(self._page_clicked)
        self.view.moved.connect(self._page_mouse_moved)
        self.view.area_selected.connect(self.redact_selection)
        center_layout.addWidget(self.view, 1)
        splitter.addWidget(center)
        self.inspector = self._build_inspector()
        self.inspector.setMinimumWidth(270)
        self.inspector.setMaximumWidth(340)
        inspector_scroll = QScrollArea()
        inspector_scroll.setFrameShape(QFrame.Shape.NoFrame)
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setWidget(self.inspector)
        inspector_scroll.setMinimumWidth(285)
        inspector_scroll.setMaximumWidth(355)
        splitter.addWidget(inspector_scroll)
        splitter.setSizes([165, 935, 290])
        splitter.setStretchFactor(1, 1)
        return splitter

    def _build_inspector(self):
        panel = QWidget()
        panel.setObjectName("inspector")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(10)
        self.file_label = QLabel("ДОКУМЕНТ")
        self.file_label.setObjectName("documentBadge")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)
        self.inspector_title = QLabel("Просмотр документа")
        self.inspector_title.setObjectName("sectionTitle")
        layout.addWidget(self.inspector_title)
        self.inspector_hint = QLabel("Выберите инструмент на верхней панели.")
        self.inspector_hint.setWordWrap(True)
        self.inspector_hint.setObjectName("hint")
        layout.addWidget(self.inspector_hint)

        self.text_panel = QWidget()
        text_layout = QVBoxLayout(self.text_panel)
        text_layout.setContentsMargins(0, 0, 0, 0)
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Нажмите на строку текста на странице")
        self.text_edit.setMinimumHeight(130)
        self.text_edit.setMaximumHeight(230)
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setAccessibleName("Текст выбранной строки")
        text_layout.addWidget(self.text_edit)
        form = QFormLayout()
        self.font_size = QDoubleSpinBox()
        self.font_size.setRange(4, 120)
        self.font_size.setValue(12)
        self.font_size.setSuffix(" пт")
        form.addRow("Размер шрифта", self.font_size)
        text_layout.addLayout(form)
        self.apply_button = QPushButton("Применить к странице")
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(self.apply_text)
        text_layout.addWidget(self.apply_button)
        add_text_button = QPushButton("Вставить новый текст")
        add_text_button.clicked.connect(lambda: self.set_mode("add"))
        text_layout.addWidget(add_text_button)
        self.text_note = QLabel("Скан сначала распознайте. После исправления проверьте страницу: шрифт и переносы могут отличаться.")
        self.text_note.setWordWrap(True)
        self.text_note.setObjectName("hint")
        text_layout.addWidget(self.text_note)
        layout.addWidget(self.text_panel)

        self.stamp_panel = QWidget()
        stamp_layout = QVBoxLayout(self.stamp_panel)
        stamp_layout.setContentsMargins(0, 0, 0, 0)
        choose_stamp = QPushButton("Загрузить подпись / печать…")
        choose_stamp.setIcon(icon("open"))
        choose_stamp.clicked.connect(self.choose_stamp)
        stamp_layout.addWidget(choose_stamp)
        self.stamp_preview = QLabel("PNG или JPEG")
        self.stamp_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stamp_preview.setMinimumHeight(90)
        self.stamp_preview.setObjectName("hint")
        stamp_layout.addWidget(self.stamp_preview)
        stamp_form = QFormLayout()
        self.stamp_width = QDoubleSpinBox()
        self.stamp_width.setRange(5, 250)
        self.stamp_width.setValue(45)
        self.stamp_width.setSuffix(" мм")
        self.stamp_width.valueChanged.connect(self._refresh_preview_size)
        stamp_form.addRow("Ширина", self.stamp_width)
        self.stamp_angle = QDoubleSpinBox()
        self.stamp_angle.setRange(-180, 180)
        self.stamp_angle.setSuffix(" °")
        self.stamp_angle.setSingleStep(5)
        stamp_form.addRow("Поворот", self.stamp_angle)
        self.stamp_opacity = QDoubleSpinBox()
        self.stamp_opacity.setRange(10, 100)
        self.stamp_opacity.setValue(100)
        self.stamp_opacity.setSuffix(" %")
        stamp_form.addRow("Непрозрачность", self.stamp_opacity)
        stamp_layout.addLayout(stamp_form)
        self.remove_white = QCheckBox("Убрать белый фон")
        stamp_layout.addWidget(self.remove_white)
        for control in [self.stamp_angle, self.stamp_opacity]:
            control.valueChanged.connect(self._refresh_stamp_preview)
        self.remove_white.toggled.connect(self._refresh_stamp_preview)
        library_group = QGroupBox("Моя библиотека")
        library_layout = QVBoxLayout(library_group)
        library_layout.setContentsMargins(0, 4, 0, 0)
        self.stamp_library_combo = QComboBox()
        self.stamp_library_combo.setAccessibleName("Сохранённые подписи и печати")
        library_layout.addWidget(self.stamp_library_combo)
        library_row = QHBoxLayout()
        for text, callback in [("Выбрать", self.select_library_stamp), ("Удалить", self.remove_library_stamp)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            library_row.addWidget(button)
        library_layout.addLayout(library_row)
        save_to_library = QPushButton("Сохранить в библиотеку")
        save_to_library.clicked.connect(self.save_library_stamp)
        library_layout.addWidget(save_to_library)
        library_note = QLabel("Изображения добавляются только кнопкой «Сохранить в библиотеку» и хранятся на этом компьютере.")
        library_note.setWordWrap(True)
        library_note.setObjectName("hint")
        library_layout.addWidget(library_note)
        stamp_layout.addWidget(library_group)
        self._refresh_library()
        stamp_note = QLabel("После загрузки нажмите на страницу — это центр изображения.\n\nВставляется изображение подписи или печати. Криптографическая электронная подпись не создаётся.")
        stamp_note.setWordWrap(True)
        stamp_note.setObjectName("hint")
        stamp_layout.addWidget(stamp_note)
        layout.addWidget(self.stamp_panel)

        self.view_panel = QWidget()
        view_layout = QVBoxLayout(self.view_panel)
        view_layout.setContentsMargins(0, 0, 0, 0)
        for label, drawing, callback in [("Править текст", "edit", lambda: self.set_mode("edit")),
                                ("Добавить текст", "text", lambda: self.set_mode("add")),
                                ("Подпись / печать", "stamp", lambda: self.set_mode("stamp")),
                                ("Заполнить форму…", "form", self.fill_forms_dialog),
                                ("Удалить содержимое области", "redact", lambda: self.set_mode("redact"))]:
            button = QPushButton(label)
            button.setProperty("role", "navigation")
            button.setIcon(icon(drawing))
            button.setIconSize(QSize(18, 18))
            button.clicked.connect(callback)
            view_layout.addWidget(button)
        layout.addWidget(self.view_panel)

        group = QGroupBox("Выбранные страницы")
        self.page_group = group
        page_layout = QVBoxLayout(group)
        page_layout.setContentsMargins(0, 6, 0, 0)
        self.selection_count = QLabel("Ctrl / Shift — выбор страниц")
        self.selection_count.setObjectName("hint")
        self.selection_count.setWordWrap(True)
        self.selection_count.setMinimumHeight(36)
        page_layout.addWidget(self.selection_count)
        for actions in [[self.rotate_action, self.delete_action], [self.duplicate_action, self.crop_action],
                        [self.up_action, self.down_action], [self.merge_action], [self.extract_action]]:
            row = QHBoxLayout()
            row.setSpacing(6)
            for action in actions:
                short_labels = {self.delete_action: "Удалить", self.duplicate_action: "Дублировать"}
                button = QPushButton(short_labels.get(action, action.text()))
                button.setProperty("role", "compact")
                button.setToolTip(action.text())
                button.clicked.connect(action.trigger)
                action.changed.connect(lambda b=button, a=action: b.setEnabled(a.isEnabled()))
                row.addWidget(button)
            page_layout.addLayout(row)
        layout.addWidget(group)
        layout.addStretch()
        self.local_note = QLabel("Локальная обработка\nРусский + English")
        self.local_note.setObjectName("hint")
        layout.addWidget(self.local_note)
        self._set_panel_mode()
        return panel

    def _guard_dirty(self):
        if not self.engine.dirty:
            return True
        answer = QMessageBox.question(self, "Несохранённые изменения",
            "Сохранить изменения перед продолжением?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save_copy()
        return True

    def choose_file(self):
        if self.worker:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Открыть PDF", "", "Документы PDF (*.pdf)")
        if path:
            self.open_file(path)

    def open_file(self, path):
        if self.worker or not self._guard_dirty():
            return False
        try:
            password = None
            while True:
                try:
                    self.engine.open(str(path), password=password)
                    break
                except PasswordRequired:
                    password, accepted = QInputDialog.getText(self, "Пароль PDF", "Введите пароль документа:", QLineEdit.EchoMode.Password)
                    if not accepted:
                        return False
            self.current_page = 0
            self.search_field.clear()
            self.stack.setCurrentIndex(1)
            self.set_mode("view", render=False)
            self.refresh_document()
            QTimer.singleShot(0, self.fit_width)
            if self.engine.has_signatures:
                QMessageBox.warning(self, "В PDF есть цифровая подпись", "Изменение документа может нарушить его цифровую подпись. Сохраните результат отдельной копией.")
            return True
        except Exception as exc:
            self._error("Не удалось открыть PDF", exc)
            return False

    def refresh_document(self, rebuild_list=True):
        count = self.engine.page_count
        if not count:
            return
        self.current_page = min(max(self.current_page, 0), count - 1)
        self.selected_line = None
        self.selected_rect = None
        self.search_results = []
        self.search_index = -1
        self.text_edit.clear()
        self.file_label.setText(Path(self.engine.path or "Документ").name)
        self.sidebar_counter.setText(str(count))
        if rebuild_list:
            self._list_refreshing = True
            self.page_list.clear()
            self._thumbnail_pages.clear()
            if self._thumbnail_placeholder is None:
                placeholder = QPixmap(105, 145)
                placeholder.fill(Qt.GlobalColor.transparent)
                painter = QPainter(placeholder)
                painter.setPen(QPen(QColor("#DDE2EA"), 1))
                painter.setBrush(QBrush(QColor("#FDFDFE")))
                painter.drawRect(1, 1, 102, 142)
                painter.setPen(QPen(QColor("#E7EAF0"), 2))
                for position, width in [(26, 68), (38, 68), (50, 45)]:
                    painter.drawLine(18, position, 18 + width, position)
                painter.end()
                self._thumbnail_placeholder = QIcon(placeholder)
            for index in range(count):
                item = QListWidgetItem(f"{index + 1:02d}")
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setToolTip(f"Страница {index + 1}")
                item.setIcon(self._thumbnail_placeholder)
                item.setSizeHint(QSize(130, 158))
                self.page_list.addItem(item)
            self.page_list.setCurrentRow(self.current_page)
            self._list_refreshing = False
        self.render_current()
        self._update_actions()

    def render_current(self):
        if not self.engine.page_count:
            return
        try:
            data = self.engine.render_page(self.current_page, scale=self.scale)
            pixmap = QPixmap()
            if not pixmap.loadFromData(data):
                raise ValueError("Не удалось отобразить страницу.")
            scene = self.view.scene()
            scene.clear()
            self.preview_item = None
            self.selection_item = None
            self.overlays = []
            self.page_item = scene.addPixmap(pixmap)
            scene.setSceneRect(QRectF(-24, -24, pixmap.width() + 48, pixmap.height() + 48))
            self.lines = self.engine.text_lines(self.current_page) if self.mode == "edit" else []
            if self.mode == "edit":
                for line in self.lines:
                    rectangle = self._visual_rect(line["rect"])
                    item = scene.addRect(rectangle, QPen(QColor(54, 116, 216, 95), 1), QBrush(QColor(54, 116, 216, 12)))
                    item.setZValue(2)
                    self.overlays.append(item)
            if self.selected_rect:
                self._draw_selection(self.selected_rect)
            self.zoom_label.setText(f"{round(self.scale * 100)} %")
            self.page_status.setText(f"Страница {self.current_page + 1} из {self.engine.page_count}")
            self._update_title()
            self._load_current_thumbnail()
        except Exception as exc:
            self._error("Не удалось отобразить страницу", exc)

    def _load_current_thumbnail(self):
        # Load a bounded neighbourhood; shared paper placeholders keep row heights stable.
        if self.page_list.item(self.current_page) is None:
            return
        try:
            for index in range(max(0, self.current_page - 1), min(self.engine.page_count, self.current_page + 3)):
                if index in self._thumbnail_pages:
                    continue
                width, height = self.engine.page_size(index)
                thumb = QPixmap()
                thumb.loadFromData(self.engine.render_page(index, scale=max(.05, min(8, 85 / width, 115 / height))))
                if not thumb.isNull():
                    self.page_list.item(index).setIcon(QIcon(thumb))
                    self._thumbnail_pages.add(index)
            keep = set(sorted(self._thumbnail_pages, key=lambda index: abs(index - self.current_page))[:40])
            for index in self._thumbnail_pages - keep:
                item = self.page_list.item(index)
                if item:
                    item.setIcon(self._thumbnail_placeholder)
            self._thumbnail_pages = keep
        except Exception:
            logging.exception("Thumbnail failed")

    def _page_selected(self, row):
        if self._list_refreshing or self.page_list.reordering or row < 0 or self.worker:
            return
        self.current_page = row
        self.selected_line = self.selected_rect = None
        self.text_edit.clear()
        self.render_current()
        self._update_actions()

    def _visual_rect(self, rectangle):
        rect = fitz.Rect(rectangle) * self.engine.doc[self.current_page].rotation_matrix
        return QRectF(rect.x0 * self.scale, rect.y0 * self.scale, rect.width * self.scale, rect.height * self.scale)

    def _unrotated_point(self, scene_point):
        return fitz.Point(scene_point.x() / self.scale, scene_point.y() / self.scale) * self.engine.doc[self.current_page].derotation_matrix

    def _draw_selection(self, rectangle):
        if self.selection_item:
            self.view.scene().removeItem(self.selection_item)
        self.selection_item = self.view.scene().addRect(self._visual_rect(rectangle), QPen(QColor("#3674D8"), 2), QBrush(QColor(54, 116, 216, 28)))
        self.selection_item.setZValue(5)

    def _page_clicked(self, scene_point):
        if self.worker or not self.engine.page_count or self.mode == "view":
            return
        page = self.engine.doc[self.current_page]
        point = self._unrotated_point(scene_point)
        if not page.rect.contains(fitz.Point(scene_point.x() / self.scale, scene_point.y() / self.scale)):
            return
        if self.mode == "edit":
            choices = [line for line in self.lines if fitz.Rect(line["rect"]).contains(point)]
            if choices:
                self.selected_line = min(choices, key=lambda x: fitz.Rect(x["rect"]).get_area())
                self.selected_rect = self.selected_line["rect"]
                self.text_edit.setPlainText(self.selected_line["text"])
                self.font_size.setValue(self.selected_line.get("size", 12))
                self._draw_selection(self.selected_rect)
                self.apply_button.setEnabled(True)
                self.text_edit.setFocus()
            else:
                self.statusBar().showMessage("Здесь нет текстового слоя. Для скана нажмите «Распознать текст».", 6500)
        elif self.mode == "add":
            visual = fitz.Rect(scene_point.x() / self.scale, scene_point.y() / self.scale,
                               min(scene_point.x() / self.scale + 240, page.rect.width - 8),
                               min(scene_point.y() / self.scale + 70, page.rect.height - 8))
            if visual.width < 15 or visual.height < 10:
                self.statusBar().showMessage("Выберите место дальше от правого и нижнего края страницы.", 4500)
                return
            self.selected_rect = tuple(visual * page.derotation_matrix)
            self.selected_line = None
            self._draw_selection(self.selected_rect)
            self.apply_button.setEnabled(True)
            self.text_edit.setFocus()
        elif self.mode == "stamp":
            if not self.stamp_path:
                self.choose_stamp()
                return
            self._refresh_stamp_preview()
            width = self.stamp_width.value() * 72 / 25.4
            height = width / self.stamp_ratio
            visual = fitz.Rect(scene_point.x() / self.scale - width / 2, scene_point.y() / self.scale - height / 2,
                               scene_point.x() / self.scale + width / 2, scene_point.y() / self.scale + height / 2)
            if not page.rect.contains(visual):
                self.statusBar().showMessage("Изображение выходит за край. Уменьшите ширину или выберите другое место.", 6500)
                return
            rect = tuple(visual * page.derotation_matrix)
            from stamp_library import prepare_stamp_file
            prepared = None
            try:
                prepared = prepare_stamp_file(self.stamp_path, angle=self.stamp_angle.value(),
                    opacity=self.stamp_opacity.value() / 100, remove_white=self.remove_white.isChecked())
                self._mutate(lambda: self.engine.insert_image(self.current_page, prepared, rect, remove_white=False), "Подпись / печать добавлена. Ctrl+Z — отменить.")
            except Exception as exc:
                self._error("Не удалось подготовить изображение", exc)
            finally:
                if prepared:
                    Path(prepared).unlink(missing_ok=True)

    def _page_mouse_moved(self, point):
        if self.mode != "stamp" or not self.stamp_path or not self.engine.page_count or self.worker:
            return
        self._refresh_stamp_preview()
        width = self.stamp_width.value() * 72 / 25.4 * self.scale
        height = width / self.stamp_ratio
        if self.stamp_pixmap is None:
            return
        pixmap = self.stamp_pixmap.scaled(max(1, round(width)), max(1, round(height)), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if self.preview_item is None:
            self.preview_item = self.view.scene().addPixmap(pixmap)
            self.preview_item.setZValue(8)
            self.preview_item.setOpacity(.78)
        else:
            self.preview_item.setPixmap(pixmap)
        self.preview_item.setPos(point.x() - width / 2, point.y() - height / 2)

    def _refresh_preview_size(self):
        if self.preview_item:
            self._page_mouse_moved(self.preview_item.sceneBoundingRect().center())

    def set_mode(self, mode, render=True):
        if self.worker:
            return
        self.mode = mode
        self.selected_line = self.selected_rect = None
        self.text_edit.clear()
        self._set_panel_mode()
        self._update_actions()
        if render and self.engine.page_count:
            self.render_current()

    def _set_panel_mode(self):
        if not hasattr(self, "text_panel"):
            return
        self.text_panel.setVisible(self.mode in ("edit", "add"))
        self.stamp_panel.setVisible(self.mode == "stamp")
        self.view_panel.setVisible(self.mode == "view")
        self.page_group.setVisible(self.mode == "view")
        titles = {"view": "Просмотр документа", "edit": "Исправление текста", "add": "Новый текст", "stamp": "Подпись / печать", "redact": "Удаление содержимого"}
        hints = {"view": "Выберите инструмент для работы с документом.",
                 "edit": "Нажмите на выделенную строку, исправьте её и примените изменение.",
                 "add": "Нажмите на страницу в месте начала текста, затем введите текст ниже.",
                 "stamp": "Загрузите своё изображение и выберите место на странице.",
                 "redact": "Протяните прямоугольник на странице. После подтверждения текст и пиксели внутри будут удалены. Метаданные и вложения отдельно не очищаются."}
        self.inspector_title.setText(titles[self.mode])
        self.inspector_hint.setText(hints[self.mode])
        if hasattr(self, "mode_hint"):
            self.mode_hint.setText(hints[self.mode] + "   Esc — просмотр")
        self.edit_action.setChecked(self.mode == "edit")
        self.stamp_action.setChecked(self.mode == "stamp")
        self.text_action.setChecked(self.mode == "add")
        self.view_action.setChecked(self.mode == "view")
        self.redact_action.setChecked(self.mode == "redact")
        if hasattr(self, "view"):
            self.view.area_mode = self.mode == "redact"
            self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if self.mode == "view" else QGraphicsView.DragMode.NoDrag)
            self.view.setCursor(Qt.CursorShape.ArrowCursor if self.mode == "view" else Qt.CursorShape.CrossCursor)

    def _available(self, name):
        value = getattr(self.engine, name)
        return value() if callable(value) else value

    def _update_actions(self):
        ready = bool(self.engine.page_count) and self.worker is None
        for action in [self.save_action, self.quick_save_action, self.ocr_action, self.edit_action,
                       self.stamp_action, self.text_action, self.view_action, self.rotate_action,
                       self.merge_action, self.extract_action, self.export_action, self.fit_action,
                       self.find_action,
                       self.duplicate_action, self.crop_action, self.redact_action, self.forms_action,
                       self.export_images_action, self.optimize_action]:
            action.setEnabled(ready)
        self.images_pdf_action.setEnabled(self.worker is None)
        self.open_action.setEnabled(self.worker is None)
        self.undo_action.setEnabled(ready and self._available("can_undo"))
        self.redo_action.setEnabled(ready and self._available("can_redo"))
        selected = self.selected_pages() if hasattr(self, "page_list") else []
        self.delete_action.setEnabled(ready and 0 < len(selected) < self.engine.page_count)
        self.up_action.setEnabled(ready and self.current_page > 0)
        self.down_action.setEnabled(ready and self.current_page < self.engine.page_count - 1)
        if hasattr(self, "inspector"):
            self.inspector.setEnabled(ready)
            self.page_list.setEnabled(self.worker is None)
            self.search_field.setEnabled(ready)
            self.find_next_button.setEnabled(ready)
            self.apply_button.setEnabled(ready and self.selected_rect is not None)
            self.selection_count.setText(f"Выбрано страниц: {len(selected)}\nCtrl / Shift — выбор нескольких")
        self._update_title()

    def _update_title(self):
        name = Path(self.engine.path).name if self.engine.path else ""
        self.setWindowTitle(("● " if self.engine.dirty else "") + (name + " — " if name else "") + "PDF Мастер")

    def _mutate(self, callback, message="Изменение применено"):
        if self.worker or not self.engine.page_count:
            return False
        try:
            callback()
            self.refresh_document()
            self.statusBar().showMessage(message, 6500)
            return True
        except Exception as exc:
            self._error("Не удалось применить изменение", exc)
            return False

    def apply_text(self):
        if not self.selected_rect or self.worker:
            return
        text = self.text_edit.toPlainText()
        rect = tuple(self.selected_rect)
        size = self.font_size.value()
        if self.mode == "edit":
            color = self.selected_line.get("color", (0, 0, 0))
            self._mutate(lambda: self.engine.replace_text(self.current_page, rect, text, size=size, color=color))
        else:
            self._mutate(lambda: self.engine.add_text(self.current_page, rect, text, size=size))

    def choose_stamp(self):
        path, _ = QFileDialog.getOpenFileName(self, "Загрузить подпись или печать", "", "Изображения (*.png *.jpg *.jpeg)")
        if path:
            self.load_stamp(path)

    def load_stamp(self, path):
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._error("Не удалось загрузить изображение", ValueError("Выберите исправный файл PNG или JPEG."))
            return False
        self.stamp_path = str(path)
        self._stamp_transform_key = None
        self._refresh_stamp_preview()
        self.stamp_preview.setToolTip(Path(path).name)
        self.set_mode("stamp")
        return True

    def _refresh_stamp_preview(self, *args):
        if not self.stamp_path:
            return
        key = (self.stamp_path, self.stamp_angle.value(), self.stamp_opacity.value(), self.remove_white.isChecked())
        if key == self._stamp_transform_key:
            return
        try:
            from stamp_library import prepare_stamp
            from PIL.ImageQt import ImageQt
            prepared = prepare_stamp(self.stamp_path, angle=key[1], opacity=key[2] / 100, remove_white=key[3])
            pixmap = QPixmap.fromImage(ImageQt(prepared))
            self.stamp_ratio = pixmap.width() / pixmap.height()
            self.stamp_pixmap = pixmap
            self._stamp_transform_key = key
            self.stamp_preview.setPixmap(pixmap.scaled(220, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except Exception as exc:
            self._error("Не удалось подготовить подпись / печать", exc)

    def _library(self):
        if self.stamp_library is None:
            from stamp_library import StampLibrary
            self.stamp_library = StampLibrary()
        return self.stamp_library

    def _refresh_library(self, select_id=None):
        if not hasattr(self, "stamp_library_combo"):
            return
        self.stamp_library_combo.clear()
        try:
            for item in self._library().items():
                self.stamp_library_combo.addItem(item["name"], item["id"])
            if select_id:
                self.stamp_library_combo.setCurrentIndex(self.stamp_library_combo.findData(select_id))
            if not self.stamp_library_combo.count():
                self.stamp_library_combo.addItem("Библиотека пуста", None)
        except Exception:
            logging.exception("Stamp library unavailable")
            self.stamp_library_combo.addItem("Библиотека недоступна", None)

    def save_library_stamp(self):
        if not self.stamp_path:
            self.statusBar().showMessage("Сначала загрузите изображение подписи или печати.", 6000)
            return
        name, accepted = QInputDialog.getText(self, "Сохранить в библиотеку", "Название изображения:", text=Path(self.stamp_path).stem)
        if accepted and name.strip():
            try:
                saved = self._library().add(self.stamp_path, name.strip())
                self._refresh_library(saved["id"])
                self.statusBar().showMessage("Изображение сохранено в локальной библиотеке.", 6000)
            except Exception as exc:
                self._error("Не удалось сохранить изображение", exc)

    def select_library_stamp(self):
        identity = self.stamp_library_combo.currentData()
        if identity:
            try:
                self.load_stamp(self._library().image_path(identity))
            except Exception as exc:
                self._error("Не удалось загрузить изображение из библиотеки", exc)

    def remove_library_stamp(self):
        identity = self.stamp_library_combo.currentData()
        if not identity:
            return
        if QMessageBox.question(self, "Удалить из библиотеки", "Удалить сохранённое изображение из локальной библиотеки? Исходный файл не меняется.") == QMessageBox.StandardButton.Yes:
            try:
                library_path = self._library().image_path(identity)
                self._library().remove(identity)
                if self.stamp_path and Path(self.stamp_path).resolve() == Path(library_path).resolve():
                    self.stamp_path = None
                    self.stamp_pixmap = None
                    self._stamp_transform_key = None
                    self.stamp_preview.clear()
                    self.stamp_preview.setText("PNG или JPEG")
                    if self.preview_item:
                        self.view.scene().removeItem(self.preview_item)
                        self.preview_item = None
                self._refresh_library()
            except Exception as exc:
                self._error("Не удалось удалить изображение", exc)

    def selected_pages(self):
        if not self.engine.page_count:
            return []
        selected = sorted(item.data(Qt.ItemDataRole.UserRole) for item in self.page_list.selectedItems())
        return selected or [self.current_page]

    def _select_pages(self, indices):
        self.page_list.clearSelection()
        for index in indices:
            item = self.page_list.item(index)
            if item:
                item.setSelected(True)

    def rotate_page(self):
        selected = self.selected_pages()
        if self._mutate(lambda: self.engine.rotate_pages(selected), f"Повернуто страниц: {len(selected)}"):
            self._select_pages(selected)

    def delete_page(self):
        selected = self.selected_pages()
        if len(selected) >= self.engine.page_count:
            return
        answer = QMessageBox.question(self, "Удалить страницы", f"Удалить выбранные страницы ({len(selected)})? Действие можно отменить.")
        if answer == QMessageBox.StandardButton.Yes:
            self._mutate(lambda: self.engine.delete_pages(selected))

    def duplicate_pages(self):
        selected = self.selected_pages()
        self._mutate(lambda: self.engine.duplicate_pages(selected), f"Добавлены копии страниц: {len(selected)}")

    def reorder_pages(self, order):
        if self.worker or self._list_refreshing or order == list(range(self.engine.page_count)):
            return
        previous = self.current_page
        def apply():
            self.engine.reorder_pages(order)
            self.current_page = order.index(previous)
        if not self._mutate(apply, "Порядок страниц изменён. Ctrl+Z — отменить."):
            self.refresh_document()

    def crop_dialog(self):
        if self.worker or not self.engine.page_count:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Обрезать поля текущей страницы")
        layout = QVBoxLayout(dialog)
        warning = QLabel("Обрезка скрывает края листа, сохраняя содержимое PDF. Для удаления конфиденциальных данных используйте «Удалить содержимое области».")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        form = QFormLayout()
        margins = []
        for label in ["Слева", "Сверху", "Справа", "Снизу"]:
            spin = QDoubleSpinBox()
            spin.setRange(0, 500)
            spin.setSuffix(" мм")
            spin.setObjectName("crop_" + str(len(margins)))
            form.addRow(label, spin)
            margins.append(spin)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Обрезать страницу")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.crop_current([spin.value() for spin in margins])

    def crop_current(self, margins_mm):
        values = tuple(value * 72 / 25.4 for value in margins_mm)
        if self._mutate(lambda: self.engine.crop_page(self.current_page, visual_margins_pt=values), "Поля страницы обрезаны. Скрытое содержимое остаётся в PDF."):
            self.fit_width()

    def redact_selection(self, scene_rect):
        if self.worker or self.mode != "redact" or not self.engine.page_count:
            return
        page = self.engine.doc[self.current_page]
        visual = fitz.Rect(scene_rect.left() / self.scale, scene_rect.top() / self.scale,
                           scene_rect.right() / self.scale, scene_rect.bottom() / self.scale) & page.rect
        if visual.is_empty:
            return
        answer = QMessageBox.question(self, "Удалить содержимое области",
            "Удалить текст и пиксели изображения в выделенной области текущей страницы и закрыть её чёрным? До сохранения действие можно отменить.\n\nМетаданные, вложения и данные вне области отдельно не очищаются.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            rect = tuple(visual * page.derotation_matrix)
            self._mutate(lambda: self.engine.redact_area(self.current_page, rect), "Содержимое области удалено. Проверьте копию перед отправкой.")

    def fill_forms_dialog(self):
        if self.worker or not self.engine.page_count:
            return
        try:
            self.engine.require_fill()
            if self.engine.has_xfa:
                QMessageBox.information(self, "Форма XFA не поддерживается", "Эта PDF-форма использует XFA. PDF Мастер не изменяет такие формы. Откройте её в программе, поддерживающей XFA.")
                return
            fields = self.engine.form_fields()
            if not fields:
                QMessageBox.information(self, "В документе нет полей формы", "Редактируемые поля AcroForm не найдены. Для обычного текста используйте «Править текст» или «Добавить текст».")
                return
            dialog = FormsDialog(fields, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                values = dialog.values()
                if values:
                    self._mutate(lambda: self.engine.fill_form(values), "Поля формы заполнены. Проверьте значения и сохраните копию.")
        except Exception as exc:
            self._error("Не удалось заполнить форму", exc)

    def move_page(self, offset):
        def move():
            self.engine.move_page(self.current_page, offset)
            self.current_page += offset
        self._mutate(move)

    def merge_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Добавить страницы из PDF", "", "Документы PDF (*.pdf)")
        if not path:
            return
        def append():
            password = None
            while True:
                try:
                    self.engine.append_pdf(path, password=password)
                    return
                except PasswordRequired:
                    password, accepted = QInputDialog.getText(self, "Пароль PDF", "Пароль добавляемого документа:", QLineEdit.EchoMode.Password)
                    if not accepted:
                        raise ValueError("Добавление отменено.")
        self._mutate(append, "Страницы добавлены в конец документа")

    def extract_pages(self):
        value, accepted = QInputDialog.getText(self, "Извлечь страницы", "Номера страниц, например 1, 3-5:", text=str(self.current_page + 1))
        if not accepted:
            return
        try:
            indices = parse_page_ranges(value, self.engine.page_count)
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить выбранные страницы", "Страницы.pdf", "Документы PDF (*.pdf)")
            if path:
                self.engine.extract_pages(indices, self._pdf_path(path))
                self.statusBar().showMessage(f"Сохранено страниц: {len(indices)}", 6000)
        except Exception as exc:
            self._error("Не удалось извлечь страницы", exc)

    def undo(self):
        if self._available("can_undo"):
            self._mutate(self.engine.undo, "Изменение отменено")

    def redo(self):
        if self._available("can_redo"):
            self._mutate(self.engine.redo, "Изменение повторено")

    def _pdf_path(self, path):
        return path if str(path).lower().endswith(".pdf") else str(path) + ".pdf"

    def save_copy(self):
        if self.worker or not self.engine.page_count:
            return False
        original = Path(self.engine.path) if self.engine.path else Path("Документ.pdf")
        suggestion = str(original.with_name(original.stem + " — копия.pdf"))
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить PDF", suggestion, "Документы PDF (*.pdf)")
        return self.save_to(self._pdf_path(path)) if path else False

    def quick_save(self):
        if self.worker or not self.engine.page_count:
            return False
        if self.engine.path:
            return self.save_to(self.engine.path)
        return self.save_copy()

    def save_to(self, path):
        if self.worker:
            return False
        try:
            self.engine.save(str(path))
            self.file_label.setText(Path(path).name)
            self._update_actions()
            self.statusBar().showMessage("PDF сохранён: " + str(path), 9000)
            return True
        except Exception as exc:
            self._error("Не удалось сохранить PDF", exc)
            return False

    def export_text(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить текст", "Текст документа.txt", "Текст UTF-8 (*.txt)")
        if path:
            try:
                self.engine.export_text(path)
                self.statusBar().showMessage("Текст сохранён: " + path, 7000)
            except Exception as exc:
                self._error("Не удалось сохранить текст", exc)

    def change_zoom(self, factor):
        if self.worker or not self.engine.page_count:
            return
        self.scale = min(3.5, max(0.25, self.scale * factor))
        # Bound raster memory for unusually large PDF sheets.
        width, height = self.engine.page_size(self.current_page)
        self.scale = min(self.scale, math.sqrt(28_000_000 / max(width * height, 1)))
        self.render_current()

    def fit_width(self):
        if not self.engine.page_count or self.worker:
            return
        width, height = self.engine.page_size(self.current_page)
        self.scale = max(0.15, min(3.5, (self.view.viewport().width() - 58) / width, math.sqrt(28_000_000 / max(width * height, 1))))
        self.render_current()

    def _reset_search(self):
        self.search_results = []
        self.search_index = -1

    def find_next(self):
        if self.worker or not self.engine.page_count:
            return
        query = self.search_field.text().strip()
        if not query:
            return
        try:
            if not self.search_results:
                self.search_results = self.engine.search(query)
            if not self.search_results:
                self.statusBar().showMessage("Совпадений нет. Если это скан, сначала распознайте текст.", 6500)
                return
            self.search_index = (self.search_index + 1) % len(self.search_results)
            page_index, rectangle = self.search_results[self.search_index]
            self.page_list.setCurrentRow(page_index)
            self.selected_rect = rectangle
            self._draw_selection(rectangle)
            self.view.ensureVisible(self._visual_rect(rectangle), 60, 60)
            self.statusBar().showMessage(f"Совпадение {self.search_index + 1} из {len(self.search_results)}", 6000)
        except Exception as exc:
            self._error("Не удалось найти текст", exc)

    def start_ocr(self):
        if self.worker or not self.engine.page_count:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Распознать текст")
        dialog.setMinimumWidth(480)
        layout = QVBoxLayout(dialog)
        heading = QLabel("Распознавание печатного текста")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        form = QFormLayout()
        scope = QComboBox()
        scope.addItems(["Текущая страница", "Весь документ"])
        language = QComboBox()
        language.addItem("Русский + английский", "rus+eng")
        language.addItem("Русский", "rus")
        language.addItem("English", "eng")
        quality = QComboBox()
        for dpi in [200, 300, 400, 600]:
            quality.addItem(str(dpi) + (" DPI — рекомендуется" if dpi == 300 else " DPI"), dpi)
        quality.setCurrentIndex(1)
        form.addRow("Страницы", scope)
        form.addRow("Язык", language)
        form.addRow("Качество", quality)
        layout.addLayout(form)
        skip_existing = QCheckBox("Пропускать страницы с готовым текстом")
        skip_existing.setChecked(True)
        skip_existing.setObjectName("ocr_skip_existing")
        deskew = QCheckBox("Выравнивать небольшой наклон скана")
        deskew.setObjectName("ocr_deskew")
        contrast = QCheckBox("Улучшать контраст скана")
        contrast.setObjectName("ocr_contrast")
        for option in [skip_existing, deskew, contrast]:
            layout.addWidget(option)
        note = QLabel("По умолчанию страницы с текстом сохраняются. Снимите первый флажок только для принудительного OCR. Обработанные страницы станут изображениями с поисковым слоем; формы и аннотации на них будут сведены в изображение.\n\nРасположение текста не восстанавливается автоматически. После OCR проверьте имена, числа и таблицы. Для мелкого текста попробуйте 400–600 DPI: обработка потребует больше времени и памяти.")
        note.setWordWrap(True)
        note.setObjectName("hint")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Распознать")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        pages = [self.current_page] if scope.currentIndex() == 0 else list(range(self.engine.page_count))
        self.run_ocr(pages, language=language.currentData(), dpi=quality.currentData(),
                     skip_existing_text=skip_existing.isChecked(), deskew=deskew.isChecked(),
                     enhance_contrast=contrast.isChecked())

    def run_ocr(self, pages, language="rus+eng", dpi=300, skip_existing_text=True,
                deskew=False, enhance_contrast=False):
        if self.worker or not self.engine.page_count:
            return
        try:
            data = self.engine.to_bytes()
            self.engine.require_edit()
            self.worker = OcrWorker(data, pages, self, language=language, dpi=dpi,
                skip_existing_text=skip_existing_text, deskew=deskew, enhance_contrast=enhance_contrast)
            self.worker.progress_changed.connect(self._ocr_progress)
            self.worker.result_ready.connect(self._ocr_success)
            self.worker.failed.connect(self._ocr_error)
            self.worker.cancelled.connect(lambda: self.statusBar().showMessage("Распознавание отменено. Документ не изменён.", 6500))
            self.worker.finished.connect(self._ocr_finished)
            self.progress.setRange(0, len(pages))
            self.progress.setValue(0)
            self.progress.show()
            self.cancel_button.setEnabled(True)
            self.cancel_button.setText("Отменить OCR")
            self.cancel_button.show()
            self._update_actions()
            self.mode_hint.setText("Распознаём текст на вашем компьютере. Большие страницы могут занять несколько минут.")
            self.statusBar().showMessage("Распознавание: подготовка…")
            self.worker.start()
        except Exception as exc:
            self.worker = None
            self._update_actions()
            self._error("Не удалось начать распознавание", exc)

    def _ocr_progress(self, done, total):
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.statusBar().showMessage(f"Распознавание: {done} из {total} страниц")

    def _ocr_success(self, data):
        try:
            self.engine.replace_document(data)
            self.refresh_document()
            self.statusBar().showMessage("Текст распознан. Проверьте результат, затем сохраните копию PDF.", 12000)
        except Exception as exc:
            self._error("Не удалось применить распознанный текст", exc)

    def _ocr_error(self, message):
        self._error("Не удалось распознать текст", ValueError(message))

    def _ocr_finished(self):
        previous = self.worker
        self.worker = None
        self.progress.hide()
        self.cancel_button.hide()
        self._set_panel_mode()
        self._update_actions()
        if previous:
            previous.deleteLater()

    def cancel_ocr(self):
        if self.worker:
            self.worker.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.mode_hint.setText("Отмена после завершения текущего этапа…")

    def _run_background(self, title, operation, on_success):
        if self.worker:
            return False
        self._task_result = None
        self._task_has_result = False
        self._task_success = on_success
        self.worker = BackgroundWorker(operation, self)
        self.worker.progress_changed.connect(self._background_progress)
        self.worker.result_ready.connect(self._background_result)
        self.worker.failed.connect(lambda message: self._error(title, ValueError(message)))
        self.worker.cancelled.connect(lambda: self.statusBar().showMessage("Операция отменена. Открытый документ не изменён.", 7000))
        self.worker.finished.connect(self._background_finished)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.cancel_button.setText("Отменить операцию")
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.mode_hint.setText(title + ". Обработка выполняется на вашем компьютере.")
        self._update_actions()
        self.worker.start()
        return True

    def _background_progress(self, done, total):
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    def _background_result(self, result):
        self._task_result = result
        self._task_has_result = True

    def _background_finished(self):
        previous = self.worker
        self.worker = None
        self.progress.hide()
        self.cancel_button.hide()
        self._set_panel_mode()
        self._update_actions()
        callback, result, completed = self._task_success, self._task_result, self._task_has_result
        self._task_success = self._task_result = None
        self._task_has_result = False
        if previous:
            previous.deleteLater()
        if completed and callback:
            try:
                callback(result)
            except Exception as exc:
                self._error("Не удалось завершить операцию", exc)

    def images_pdf_dialog(self):
        if self.worker:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Выберите изображения для PDF", "", "Изображения (*.jpg *.jpeg *.png *.tif *.tiff)")
        if not paths:
            return
        dialog = ImagesToPdfDialog(paths, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and self._guard_dirty():
            self.create_pdf_from_images(dialog.ordered_paths(), dialog.page_size.currentData())

    def create_pdf_from_images(self, paths, page_size="original"):
        if self.worker:
            return False
        from pdf_tools import images_to_pdf
        def operation(progress, cancel):
            if cancel():
                return None
            return images_to_pdf(list(paths), page_size=page_size)
        def completed(data):
            self.engine.new_document(data)
            self.current_page = 0
            self.stack.setCurrentIndex(1)
            self.set_mode("view", render=False)
            self.refresh_document()
            self.file_label.setText("Новый PDF из изображений")
            self.fit_width()
            self.statusBar().showMessage("PDF создан. Сохраните документ кнопкой «Сохранить копию».", 10000)
        return self._run_background("Создание PDF из изображений", operation, completed)

    def export_images_dialog(self):
        if self.worker or not self.engine.page_count:
            return
        try:
            self.engine.require_copy()
        except Exception as exc:
            self._error("Экспорт недоступен", exc)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Страницы в PNG / JPEG")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        ranges = QLineEdit(", ".join(str(i + 1) for i in self.selected_pages()))
        ranges.setObjectName("export_page_ranges")
        fmt = QComboBox()
        fmt.addItem("PNG — без потери качества", "png")
        fmt.addItem("JPEG — для изображений", "jpeg")
        dpi = QComboBox()
        for value in [150, 300, 600]:
            dpi.addItem(str(value) + " DPI", value)
        form.addRow("Страницы", ranges)
        form.addRow("Формат", fmt)
        form.addRow("Качество", dpi)
        layout.addLayout(form)
        note = QLabel("Будет создана отдельная папка с изображениями страниц. Существующие файлы не перезаписываются.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Выбрать папку…")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            indices = parse_page_ranges(ranges.text(), self.engine.page_count)
            folder = QFileDialog.getExistingDirectory(self, "Папка для изображений страниц")
            if folder:
                self.export_images(indices, folder, fmt.currentData(), dpi.currentData())
        except Exception as exc:
            self._error("Не удалось экспортировать страницы", exc)

    def export_images(self, indices, directory, fmt="png", dpi=150):
        if self.worker:
            return False
        try:
            self.engine.require_copy()
            data = self.engine.to_bytes()
            from pdf_tools import export_page_images
            folder = tempfile.mkdtemp(prefix="PDFMaster-pages-", dir=str(directory))
            def operation(progress, cancel):
                return export_page_images(data, list(indices), folder, fmt=fmt, dpi=dpi,
                                          overwrite=False, progress=progress, cancel=cancel)
            def completed(paths):
                self.statusBar().showMessage(f"Сохранено изображений: {len(paths)} · {folder}", 15000)
                QMessageBox.information(self, "Страницы экспортированы", f"Сохранено изображений: {len(paths)}\n\nПапка: {folder}")
            return self._run_background("Экспорт страниц в изображения", operation, completed)
        except Exception as exc:
            self._error("Не удалось экспортировать страницы", exc)
            return False

    @staticmethod
    def _format_bytes(size):
        return f"{size / 1024 / 1024:.2f} МБ" if size >= 1024 * 1024 else f"{size / 1024:.1f} КБ"

    def optimize_document(self, save_path=None):
        if self.worker or not self.engine.page_count:
            return False
        try:
            self.engine.require_edit()
            data = self.engine.to_bytes()
            from pdf_tools import optimize_pdf
            def operation(progress, cancel):
                return optimize_pdf(data)
            def completed(result):
                optimized, stats = result
                description = f"До: {self._format_bytes(stats['before'])}\nПосле: {self._format_bytes(stats['after'])}"
                if not stats.get("changed"):
                    QMessageBox.information(self, "Уменьшить файл не удалось", description + "\n\nДокумент уже оптимизирован. Текст и изображения не менялись.")
                    self.statusBar().showMessage("Оптимизация не дала уменьшения. Документ не изменён.", 8000)
                    return
                destination = save_path if isinstance(save_path, (str, Path)) else None
                if destination is None:
                    source = Path(self.engine.path) if self.engine.path else Path("Документ.pdf")
                    destination, _ = QFileDialog.getSaveFileName(self,
                        "Оптимизация: " + description.replace("\n", " → ") + " · Сохранить копию",
                        str(source.with_name(source.stem + " — оптимизировано.pdf")), "Документы PDF (*.pdf)")
                if not destination:
                    self.statusBar().showMessage("Сохранение оптимизированной копии отменено. Документ не изменён.", 8000)
                    return
                self.engine.replace_document(optimized)
                self.refresh_document()
                if self.save_to(self._pdf_path(str(destination))):
                    QMessageBox.information(self, "Оптимизированная копия сохранена", description + "\n\nТекст, формы и качество изображений сохранены.")
            return self._run_background("Оптимизация PDF без потери качества", operation, completed)
        except Exception as exc:
            self._error("Не удалось оптимизировать PDF", exc)
            return False

    def _error(self, title, exc):
        logging.error("%s: %s", title, exc)
        QMessageBox.warning(self, title, str(exc) or "Неизвестная ошибка. Попробуйте другой файл.")

    def show_help(self):
        QMessageBox.information(self, "Как работать в PDF Мастере",
            "1. Откройте PDF кнопкой или перетащите файл в окно.\n\n"
            "2. Для скана нажмите «Распознать текст». Выберите текущую страницу или весь документ. Результат OCR нужно проверить.\n\n"
            "3. «Править текст»: нажмите на строку, исправьте её справа, затем нажмите «Применить». Если строка не помещается, уменьшите размер шрифта. Новый текст добавляется через «Вставить новый текст».\n\n"
            "4. «Подпись / печать»: загрузите PNG или JPEG, задайте ширину и нажмите на страницу. PNG сохраняет прозрачность. Для белого фона есть отдельный переключатель. Это изображение, а не сертификатная ЭП.\n\n"
            "5. Сохраните копию. Ctrl+Z отменяет изменения; Ctrl+Y повторяет. Ctrl+F ищет текст, Ctrl+0 подгоняет страницу по ширине.\n\n"
            "6. Ctrl / Shift в списке слева выбирает несколько страниц для поворота, удаления или дублирования. Порядок меняется перетаскиванием. «Обрезать поля» скрывает края, сохраняя их содержимое.\n\n"
            "7. Меню «Инструменты»: заполнение существующих полей формы, удаление содержимого выделенной области, PDF из изображений, экспорт PNG / JPEG и оптимизация без потери качества.\n\n"
            "8. В режиме подписи доступны поворот и непрозрачность. Кнопка «Сохранить в библиотеку» явно добавляет изображение для последующего использования на этом компьютере.\n\n"
            "9. Ctrl+K открывает поиск по всем командам. Введите название задачи, выберите команду и нажмите Enter. Меню по правой кнопке мыши показывает действия для страницы или документа.\n\n"
            "PDF сохраняет расположение элементов. Правка строки не перевёрстывает весь документ и может изменить шрифт. Сложные таблицы и рукописный текст требуют ручной проверки.")

    def show_about(self):
        QMessageBox.information(self, "О программе", "PDF Мастер 0.3.0\nЛокальный редактор PDF для Windows 11.\n\nOCR, исправление строк, библиотека подписей, формы, работа со страницами, удаление областей, изображения и оптимизация PDF.\n\nОткрытый исходный код: AGPL-3.0.\nДвижок PDF: PyMuPDF / MuPDF. Интерфейс: PySide6. OCR: Tesseract.\nПреобразования: img2pdf и pikepdf / QPDF.\nСведения о лицензиях и источниках входят в комплект программы.")

    def dragEnterEvent(self, event):
        if self.worker:
            return
        if event.mimeData().hasUrls() and any(url.toLocalFile().lower().endswith(".pdf") for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.worker:
            return
        for url in event.mimeData().urls():
            if url.toLocalFile().lower().endswith(".pdf"):
                self.open_file(url.toLocalFile())
                event.acceptProposedAction()
                return

    def closeEvent(self, event):
        if self.worker:
            self.cancel_ocr()
            QMessageBox.information(self, "Операция завершается", "Запрошена отмена. Дождитесь завершения текущего этапа, затем закройте программу.")
            event.ignore()
            return
        if self._guard_dirty():
            event.accept()
        else:
            event.ignore()
