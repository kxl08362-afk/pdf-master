"""Keyboard command finder tests exercise actual Qt event dispatch."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow

from command_menu import Command, CommandPalette, search_commands, normalize_query, availability_reason


class CommandMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = QMainWindow()
        self.window.resize(1030, 700)
        self.window.engine = SimpleNamespace(doc=object())
        self.window.worker = None
        self.calls = []
        definitions = [
            ("ocr", "Инструменты", "Распознать текст", "Текст из сканов", "ocr скан русский английский"),
            ("stamp", "Правка", "Подпись и печать", "Разместить изображение", "подписать штамп"),
            ("save", "Файл", "Сохранить копию", "Выбрать имя файла", "save as"),
        ]
        self.commands = []
        for definition in definitions:
            action = QAction(definition[2], self.window)
            key = definition[0]
            action.triggered.connect(lambda checked=False, key=key: self.calls.append(key))
            self.commands.append(Command(*definition, action))
        self.commands[2].action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.window.command_catalog = tuple(self.commands)
        self.window.show()
        self.dialog = CommandPalette(self.window)
        self.dialog.show()
        self.app.processEvents()

    def tearDown(self):
        self.dialog.reject()
        self.dialog.deleteLater()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_search_uses_synonyms_case_and_all_words(self):
        for query, expected in [("OCR", "ocr"), ("СКАН русский", "ocr"),
                                ("подписать", "stamp"), ("печать", "stamp"),
                                ("Ctrl shift S", "save")]:
            with self.subTest(query=query):
                self.assertEqual([c.key for c in search_commands(self.commands, query)], [expected])
        self.assertEqual(normalize_query("  ЕЩЁ, текст! "), "еще текст")
        self.assertEqual(search_commands(self.commands, "скан печать"), [])

    def test_empty_query_lists_all_and_no_matches_cannot_execute(self):
        self.assertEqual(self.dialog.results.count(), 3)
        self.dialog.search.setText("несуществующаякоманда")
        self.assertEqual(self.dialog.results.count(), 0)
        self.assertTrue(self.dialog.empty.isVisible())
        QTest.keyClick(self.dialog.search, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.calls, [])
        self.assertTrue(self.dialog.isVisible())

    def test_enter_executes_once_after_dialog_closes(self):
        self.dialog.search.setText("подписать")
        QTest.keyClick(self.dialog.search, Qt.Key.Key_Return)
        self.assertFalse(self.dialog.isVisible())
        self.app.processEvents()
        self.assertEqual(self.calls, ["stamp"])

    def test_disabled_command_shows_reason_and_never_executes(self):
        self.commands[0].action.setEnabled(False)
        self.window.worker = object()
        self.dialog.search.setText("OCR")
        self.assertIn("Дождитесь", self.dialog.hint.text())
        QTest.keyClick(self.dialog.search, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.calls, [])
        self.assertTrue(self.dialog.isVisible())

    def test_enabled_state_is_rechecked_at_deferred_execution(self):
        self.dialog.search.setText("подписать")
        self.dialog.execute_current()
        self.commands[1].action.setEnabled(False)
        self.app.processEvents()
        self.assertEqual(self.calls, [])

    def test_keyboard_arrows_then_enter(self):
        QTest.keyClick(self.dialog.search, Qt.Key.Key_Down)
        self.assertEqual(self.dialog.results.currentRow(), 1)
        QTest.keyClick(self.dialog.search, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.calls, ["stamp"])

    def test_escape_closes_without_executing(self):
        QTest.keyClick(self.dialog.search, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(self.dialog.isVisible())
        self.assertEqual(self.calls, [])

    def test_state_changes_preserve_query_and_selection(self):
        self.dialog.search.setText("подписать")
        self.commands[1].action.setEnabled(False)
        self.assertEqual(self.dialog.search.text(), "подписать")
        self.assertIn("Недоступно", self.dialog.results.currentItem().text())
        self.commands[1].action.setEnabled(True)
        self.assertEqual(self.dialog.results.count(), 1)
        self.assertNotIn("Недоступно", self.dialog.results.currentItem().text())

    def test_unavailable_without_document_explains_next_step(self):
        self.window.engine.doc = None
        self.commands[0].action.setEnabled(False)
        self.assertEqual(availability_reason(self.window, self.commands[0]), "Сначала откройте PDF")


if __name__ == "__main__":
    unittest.main()
