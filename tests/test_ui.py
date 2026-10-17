"""Integration tests exercise the native widgets against real PDF documents."""
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
from PIL import Image
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from engine import _font_path
from ui import MainWindow, parse_page_ranges


class PageRangeTests(unittest.TestCase):
    def test_ranges_preserve_order_deduplicate_and_validate(self):
        self.assertEqual(parse_page_ranges("3,1-2,2", 3), [2, 0, 1])
        for invalid in ["", "0", "4", "2-1", "a", "1-2-3"]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_page_ranges(invalid, 3)


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.pdf = self.folder / "Документ.pdf"
        with fitz.open() as doc:
            for text in ["Исходная строка", "Вторая страница"]:
                page = doc.new_page(width=500, height=400)
                page.insert_text((50, 100), text, fontname="unicode", fontfile=_font_path(), fontsize=20)
            doc.save(self.pdf)
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        self.errors = []
        self.warning_patch = patch("ui.QMessageBox.warning", side_effect=lambda *args: self.errors.append(args[2]))
        self.warning_patch.start()
        self.addCleanup(self.warning_patch.stop)
        self.addCleanup(self._dispose)
        self.assertTrue(self.window.open_file(self.pdf))
        self.app.processEvents()

    def _dispose(self):
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

    def wait_until(self, callback, timeout=4):
        end = time.monotonic() + timeout
        while not callback() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()
        self.assertTrue(callback(), "UI operation timed out")

    def click_pdf_point(self, point):
        self.window.view.ensureVisible(point.x(), point.y(), 1, 1, 10, 10)
        self.app.processEvents()
        position = self.window.view.mapFromScene(point)
        QTest.mouseClick(self.window.view.viewport(), Qt.MouseButton.LeftButton, pos=position)
        self.app.processEvents()

    def test_real_native_click_edit_undo_redo_and_save(self):
        self.window.set_mode("edit")
        rectangle = self.window._visual_rect(self.window.lines[0]["rect"])
        self.click_pdf_point(rectangle.center())
        self.assertEqual(self.window.text_edit.toPlainText(), "Исходная строка")
        self.window.text_edit.setPlainText("Новая строка")
        QTest.mouseClick(self.window.apply_button, Qt.MouseButton.LeftButton)
        self.assertIn("Новая строка", self.window.engine.doc[0].get_text())
        self.assertNotIn("Исходная", self.window.engine.doc[0].get_text())
        self.assertTrue(self.window.undo_action.isEnabled())
        self.window.undo_action.trigger()
        self.assertIn("Исходная", self.window.engine.doc[0].get_text())
        self.window.redo_action.trigger()
        target = self.folder / "Исправлено.pdf"
        self.assertTrue(self.window.save_to(target))
        with fitz.open(target) as saved:
            self.assertIn("Новая строка", saved[0].get_text())
        self.assertEqual(self.errors, [])

    def test_rotated_text_selection_and_replacement(self):
        self.window.rotate_page()
        self.window.set_mode("edit")
        rectangle = self.window._visual_rect(self.window.lines[0]["rect"])
        self.click_pdf_point(rectangle.center())
        self.assertEqual(self.window.text_edit.toPlainText(), "Исходная строка")
        self.window.text_edit.setPlainText("Новая строка")
        self.window.apply_text()
        self.assertEqual(self.window.engine.doc[0].rotation, 90)
        self.assertIn("Новая строка", self.window.engine.doc[0].get_text())
        self.assertEqual(self.errors, [])

    def test_stamp_click_places_image_and_undo_removes_it(self):
        stamp = self.folder / "Подпись.png"
        Image.new("RGBA", (200, 60), (30, 60, 190, 160)).save(stamp)
        self.assertTrue(self.window.load_stamp(stamp))
        self.window.stamp_width.setValue(40)
        point = QPointF(250 * self.window.scale, 280 * self.window.scale)
        self.click_pdf_point(point)
        self.assertEqual(len(self.window.engine.doc[0].get_images()), 1)
        image_info = self.window.engine.doc[0].get_image_info()[0]
        rect = fitz.Rect(image_info["bbox"])
        self.assertAlmostEqual(rect.width, 40 * 72 / 25.4, delta=.1)
        self.assertAlmostEqual((rect.x0 + rect.x1) / 2, 250, delta=1)
        self.window.undo()
        self.assertEqual(len(self.window.engine.doc[0].get_images()), 0)
        self.assertEqual(self.errors, [])

    def test_search_changes_page_and_page_actions_update_selection(self):
        self.window.search_field.setText("Вторая")
        self.window.find_next()
        self.assertEqual(self.window.current_page, 1)
        self.assertIsNotNone(self.window.selection_item)
        self.window.up_action.trigger()
        self.assertEqual(self.window.current_page, 0)
        self.assertIn("Вторая", self.window.engine.doc[0].get_text())
        self.window.undo()
        self.assertIn("Исходная", self.window.engine.doc[0].get_text())
        self.assertEqual(self.errors, [])

    def test_dirty_open_cancel_preserves_current_document(self):
        self.window.rotate_page()
        with patch("ui.QMessageBox.question", return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.window.open_file(self.pdf))
        self.assertEqual(self.window.engine.doc[0].rotation, 90)
        self.assertTrue(self.window.engine.dirty)

    def test_ocr_keeps_main_document_until_result_and_locks_changes(self):
        started = threading.Event()
        release = threading.Event()
        def fake_ocr(data, pages, **kwargs):
            self.assertEqual(kwargs["language"], "rus")
            self.assertEqual(kwargs["dpi"], 400)
            started.set()
            release.wait(3)
            kwargs["progress"](1, 1)
            with fitz.open(stream=data, filetype="pdf") as doc:
                doc[0].set_rotation(90)
                return doc.tobytes()
        with patch("ui.ocr_pdf", side_effect=fake_ocr):
            self.window.run_ocr([0], language="rus", dpi=400)
            self.wait_until(started.is_set)
            self.assertFalse(self.window.open_action.isEnabled())
            self.assertFalse(self.window.save_action.isEnabled())
            self.assertEqual(self.window.engine.doc[0].rotation, 0)
            self.assertFalse(self.window.save_to(self.folder / "blocked.pdf"))
            self.window.rotate_page()
            self.assertEqual(self.window.engine.doc[0].rotation, 0)
            release.set()
            self.wait_until(lambda: self.window.worker is None)
        self.assertEqual(self.window.engine.doc[0].rotation, 90)
        self.assertTrue(self.window.engine.can_undo)
        self.assertTrue(self.window.save_action.isEnabled())
        self.assertEqual(self.errors, [])

    def test_cancelled_ocr_does_not_replace_original(self):
        started = threading.Event()
        def fake_ocr(data, pages, **kwargs):
            started.set()
            end = time.monotonic() + 3
            while not kwargs["cancel"]() and time.monotonic() < end:
                time.sleep(.01)
            raise RuntimeError("Cancelled")
        with patch("ui.ocr_pdf", side_effect=fake_ocr):
            self.window.run_ocr([0])
            self.wait_until(started.is_set)
            self.window.cancel_ocr()
            self.wait_until(lambda: self.window.worker is None)
        self.assertEqual(self.window.engine.doc[0].rotation, 0)
        self.assertFalse(self.window.engine.dirty)
        self.assertFalse(self.window.engine.can_undo)
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
