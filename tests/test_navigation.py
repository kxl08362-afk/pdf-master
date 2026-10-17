"""Independent native-Qt integration regressions for navigation 0.3."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf as fitz
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolButton
from engine import _font_path
from command_menu import show_command_palette
from ui import MainWindow


SOURCE_KEYS = {
    "open", "images_pdf", "quick_save", "save", "merge", "extract", "undo", "redo", "view",
    "edit", "text", "stamp", "find", "fit", "rotate", "duplicate", "crop", "up", "down",
    "delete", "ocr", "forms", "redact", "export", "export_images", "optimize",
}


class NavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pdf = self.root / "Навигация.pdf"
        with fitz.open() as doc:
            for text in ("Исходная строка", "Вторая страница"):
                page = doc.new_page(width=500, height=400)
                page.insert_text((50, 100), text, fontname="unicode", fontfile=_font_path(), fontsize=20)
            doc.save(self.pdf)
        self.window = MainWindow()
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()
        self.errors = []
        self.warning = patch("ui.QMessageBox.warning", side_effect=lambda *args: self.errors.append(args[2]))
        self.warning.start()
        self.addCleanup(self.warning.stop)
        self.addCleanup(self.dispose)

    def dispose(self):
        palette = getattr(self.window, "command_palette", None)
        if palette is not None:
            palette.reject()
            self.app.processEvents()
        if self.window.worker:
            self.window.cancel_ocr()
            self.window.worker.wait(5000)
            self.app.processEvents()
        self.window.engine.dirty = False
        self.window.close()
        if self.window.engine.doc:
            self.window.engine.doc.close()
        self.window.deleteLater()
        self.app.processEvents()

    def open_pdf(self):
        self.assertTrue(self.window.open_file(self.pdf))
        self.app.processEvents()

    def palette(self):
        dialog = show_command_palette(self.window)
        self.app.processEvents()
        return dialog

    def select_command(self, palette, key):
        for index in range(palette.results.count()):
            item = palette.results.item(index)
            if item.data(Qt.ItemDataRole.UserRole).key == key:
                palette.results.setCurrentRow(index)
                return item
        self.fail(f"Command {key} is absent")

    def wait_until(self, callback, timeout=5):
        until = time.monotonic() + timeout
        while not callback() and time.monotonic() < until:
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()
        self.assertTrue(callback(), "UI operation timed out")

    def test_every_existing_tool_reachable_from_native_menus_and_catalog(self):
        catalog = self.window.command_catalog
        self.assertEqual({command.key for command in catalog}, SOURCE_KEYS)
        self.assertEqual(len(catalog), 26)
        menu_sources = []
        for menu in self.window.navigation_menus.values():
            menu_sources.extend(action for action in menu.actions() if not action.isSeparator())
        for command in catalog:
            with self.subTest(command=command.key):
                source = getattr(self.window, command.key + "_action")
                self.assertIs(command.action, source)
                self.assertIsInstance(source, QAction)
                self.assertIn(source, self.window.actions())
                self.assertEqual(menu_sources.count(source), 1)
        self.assertIn(self.window.command_action, menu_sources)
        self.assertEqual(self.window.command_action.shortcut().toString(), "Ctrl+K")

    def test_empty_document_disabled_rows_stay_inspectable_and_cannot_execute(self):
        self.assertEqual(self.window.engine.page_count, 0)
        palette = self.palette()
        self.select_command(palette, "edit")
        self.assertFalse(self.window.edit_action.isEnabled())
        self.assertIn("откройте", palette.hint.text().lower())
        QTest.keyClick(palette.search, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertTrue(palette.isVisible())
        self.assertEqual(self.window.mode, "view")
        self.assertEqual(self.window.engine.page_count, 0)
        self.assertTrue(self.window.open_action.isEnabled())
        self.assertTrue(self.window.images_pdf_action.isEnabled())
        self.assertEqual(self.errors, [])

    def test_source_enabled_state_live_in_menu_toolbar_and_open_palette(self):
        self.open_pdf()
        palette = self.palette()
        palette.search.setText("править текст")
        self.select_command(palette, "edit")
        source = self.window.edit_action
        self.assertTrue(source.isEnabled())
        source.setEnabled(False)
        self.app.processEvents()
        selected = self.select_command(palette, "edit")
        self.assertIn("недоступно", selected.text().lower())
        self.assertTrue(palette.hint.text())
        self.assertFalse(self.window.mode_buttons["edit"].isEnabled())
        QTest.keyClick(palette.search, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertTrue(palette.isVisible())
        self.assertEqual(self.window.mode, "view")
        source.setEnabled(True)
        self.app.processEvents()
        self.assertTrue(self.window.mode_buttons["edit"].isEnabled())
        self.select_command(palette, "edit")
        QTest.keyClick(palette.search, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.window.mode, "edit")
        self.assertTrue(source.isChecked())
        self.assertTrue(self.window.mode_buttons["edit"].isChecked())

    def test_keyboard_command_route_escape_scope_and_find_shortcut(self):
        self.open_pdf()
        self.window.view.setFocus()
        self.window.activateWindow()
        self.app.processEvents()
        QTest.keyClick(self.window.view, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
        self.app.processEvents()
        self.assertEqual(self.window.mode, "edit")
        QTest.keyClick(self.window.view, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
        self.app.processEvents()
        palette = self.window.command_palette
        self.assertIsNotNone(palette)
        self.assertTrue(palette.isVisible())
        QTest.keyClick(palette.search, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertEqual(self.window.mode, "edit", "Esc inside command dialog must only close that dialog")
        self.window.activateWindow()
        self.window.view.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.window.view, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        self.app.processEvents()
        self.assertTrue(self.window.search_field.hasFocus())
        QTest.keyClick(self.window.search_field, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertEqual(self.window.mode, "view")

    def test_primary_modes_execute_through_segment_and_keep_real_pdf_editing(self):
        self.open_pdf()
        QTest.mouseClick(self.window.mode_buttons["edit"], Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.mode, "edit")
        self.assertTrue(self.window.text_panel.isVisible())
        rectangle = self.window._visual_rect(self.window.lines[0]["rect"])
        self.window.view.ensureVisible(rectangle)
        self.app.processEvents()
        QTest.mouseClick(self.window.view.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.window.view.mapFromScene(rectangle.center()))
        self.window.text_edit.setPlainText("Новая строка")
        QTest.mouseClick(self.window.apply_button, Qt.MouseButton.LeftButton)
        self.assertIn("Новая строка", self.window.engine.doc[0].get_text())
        self.window.view.setFocus()
        QTest.keyClick(self.window.view, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
        self.app.processEvents()
        self.assertFalse(self.window.engine.dirty)
        with fitz.open(self.pdf) as saved:
            self.assertIn("Новая строка", saved[0].get_text())
        self.window.undo_action.trigger()
        self.assertIn("Исходная строка", self.window.engine.doc[0].get_text())
        QTest.mouseClick(self.window.mode_buttons["stamp"], Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.mode, "stamp")
        self.assertTrue(self.window.stamp_panel.isVisible())
        self.assertFalse(self.window.text_panel.isVisible())
        QTest.mouseClick(self.window.mode_buttons["view"], Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.mode, "view")
        self.assertTrue(self.window.view_panel.isVisible())
        self.assertFalse(self.window.stamp_action.isChecked())
        self.assertEqual(self.errors, [])

    def test_busy_operation_locks_existing_sources_and_new_navigation(self):
        self.open_pdf()
        started = threading.Event()
        release = threading.Event()
        def operation(progress, cancel):
            started.set()
            release.wait(3)
            return None
        self.window._run_background("Проверка блокировки", operation, lambda value: None)
        try:
            self.wait_until(started.is_set)
            palette = self.palette()
            self.select_command(palette, "edit")
            self.assertFalse(self.window.edit_action.isEnabled())
            self.assertFalse(self.window.mode_buttons["edit"].isEnabled())
            self.assertIn("завершения", palette.hint.text().lower())
            QTest.keyClick(palette.search, Qt.Key.Key_Return)
            self.app.processEvents()
            self.assertEqual(self.window.mode, "view")
            palette.reject()
        finally:
            release.set()
            self.wait_until(lambda: self.window.worker is None)
        self.assertTrue(self.window.edit_action.isEnabled())
        self.assertTrue(self.window.mode_buttons["edit"].isEnabled())
        self.assertEqual(self.errors, [])

    def test_minimum_width_primary_navigation_and_workbench_are_reachable(self):
        self.open_pdf()
        self.window.resize(1030, 700)
        self.app.processEvents()
        self.assertEqual(self.window.width(), 1030)
        toolbar = self.window.main_toolbar
        self.assertLessEqual(toolbar.width(), self.window.width())
        self.assertGreater(self.window.view.viewport().width(), 280)
        self.assertGreater(self.window.inspector.width(), 230)
        controls = list(self.window.mode_buttons.values())
        controls += [self.window.toolbar_buttons[key] for key in ("open_action", "save_action", "command_action")]
        for control in controls:
            with self.subTest(control=control.objectName()):
                self.assertTrue(control.isVisible())
                self.assertGreater(control.width(), 20)
                position = control.mapTo(self.window, QPoint(0, 0))
                self.assertGreaterEqual(position.x(), 0)
                self.assertLessEqual(position.x() + control.width(), self.window.width())
                self.assertLessEqual(position.y() + control.height(), self.window.height())
        QTest.mouseClick(self.window.toolbar_buttons["command_action"], Qt.MouseButton.LeftButton)
        self.app.processEvents()
        palette = self.window.command_palette
        self.assertIsNotNone(palette)
        self.assertTrue(palette.search.isVisible())
        self.assertTrue(palette.results.isVisible())
        self.assertLessEqual(palette.width(), self.window.width())
        self.assertLessEqual(palette.height(), self.window.height())


if __name__ == "__main__":
    unittest.main(verbosity=2)
