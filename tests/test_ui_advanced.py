"""Native-widget and real-file integration tests for version 0.2 tools."""
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
from PySide6.QtCore import Qt, QPoint, QPointF, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QCheckBox, QDoubleSpinBox, QMessageBox, QPushButton, QLineEdit
from engine import _font_path
from stamp_library import StampLibrary
from ui import MainWindow, FormsDialog, ImagesToPdfDialog


class AdvancedUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pdf = self.root / "Оригинал.pdf"
        with fitz.open() as doc:
            for number in range(3):
                page = doc.new_page(width=500, height=400)
                page.insert_text((45, 90), f"Секретный текст {number + 1}", fontname="unicode", fontfile=_font_path(), fontsize=20)
            doc.save(self.pdf, deflate=False)
        self.window = MainWindow()
        self.window.stamp_library = StampLibrary(self.root / "library")
        self.window._refresh_library()
        self.window.show()
        self.app.processEvents()
        self.errors = []
        self.notices = []
        for name, target in [("warning", self.errors), ("information", self.notices)]:
            mock = patch("ui.QMessageBox." + name, side_effect=lambda *args, target=target: target.append(args[2]))
            mock.start()
            self.addCleanup(mock.stop)
        self.addCleanup(self.dispose)
        self.assertTrue(self.window.open_file(self.pdf))
        self.app.processEvents()

    def dispose(self):
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

    def wait_until(self, callback, timeout=6):
        end = time.monotonic() + timeout
        while not callback() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()
        self.assertTrue(callback(), "Background operation timed out")

    def select_two_pages(self):
        view = self.window.page_list
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.visualItemRect(view.item(0)).center())
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier,
                         pos=view.visualItemRect(view.item(1)).center())
        self.assertEqual(self.window.selected_pages(), [0, 1])

    def click_scene(self, point):
        self.window.view.ensureVisible(point.x(), point.y(), 1, 1, 15, 15)
        self.app.processEvents()
        QTest.mouseClick(self.window.view.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.window.view.mapFromScene(point))

    def test_ctrl_selection_batch_rotate_duplicate_delete_and_undo(self):
        self.select_two_pages()
        rotate = next(button for button in self.window.inspector.findChildren(QPushButton) if button.text() == "Повернуть ↻")
        QTest.mouseClick(rotate, Qt.MouseButton.LeftButton)
        self.assertEqual([p.rotation for p in self.window.engine.doc], [90, 90, 0])
        self.assertEqual(self.window.selected_pages(), [0, 1])
        self.window.undo()
        self.select_two_pages()
        self.window.duplicate_action.trigger()
        self.assertEqual(self.window.engine.page_count, 5)
        self.window.undo()
        self.assertEqual(self.window.engine.page_count, 3)
        self.select_two_pages()
        with patch("ui.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            self.window.delete_action.trigger()
        self.assertEqual(self.window.engine.page_count, 1)
        self.assertIn("текст 3", self.window.engine.doc[0].get_text())
        self.window.undo()
        self.assertEqual(self.window.engine.page_count, 3)
        self.assertEqual(self.errors, [])

    def test_drag_order_signal_commits_document_order_and_can_undo(self):
        self.assertEqual(self.window.page_list.dragDropMode(), self.window.page_list.DragDropMode.InternalMove)
        first = self.window.page_list.takeItem(0)
        self.window.page_list.insertItem(2, first)
        order = [self.window.page_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(3)]
        self.window.page_list.order_changed.emit(order)
        self.assertEqual(order, [1, 2, 0])
        self.assertIn("текст 2", self.window.engine.doc[0].get_text())
        self.window.undo()
        self.assertIn("текст 1", self.window.engine.doc[0].get_text())
        self.assertEqual(self.errors, [])

    def test_crop_dialog_real_controls_and_undo(self):
        def interact():
            dialog = self.app.activeModalWidget()
            for spin in dialog.findChildren(QDoubleSpinBox):
                spin.setValue(5)
            QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)
        QTimer.singleShot(0, interact)
        self.window.crop_action.trigger()
        width, height = self.window.engine.page_size(0)
        self.assertAlmostEqual(width, 500 - 10 * 72 / 25.4, delta=.01)
        self.assertAlmostEqual(height, 400 - 10 * 72 / 25.4, delta=.01)
        self.assertIn("Секретный", self.window.engine.doc[0].get_text())
        self.window.undo()
        self.assertEqual(self.window.engine.page_size(0), (500, 400))
        self.assertEqual(self.errors, [])

    def test_redaction_rubberband_clicks_delete_text_and_undo(self):
        self.window.redact_action.trigger()
        line = self.window.engine.text_lines(0)[0]
        rect = self.window._visual_rect(line["rect"]).adjusted(-3, -3, 3, 3)
        self.window.view.ensureVisible(rect)
        self.app.processEvents()
        start = self.window.view.mapFromScene(rect.topLeft())
        end = self.window.view.mapFromScene(rect.bottomRight())
        with patch("ui.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            QTest.mousePress(self.window.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(self.window.view.viewport(), end)
            QTest.mouseRelease(self.window.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertNotIn("Секретный", self.window.engine.doc[0].get_text())
        saved = self.root / "Удалено.pdf"
        self.assertTrue(self.window.save_to(saved))
        with fitz.open(saved) as doc:
            self.assertNotIn("Секретный", doc[0].get_text())
        self.window.undo()
        self.assertIn("Секретный", self.window.engine.doc[0].get_text())
        self.assertEqual(self.errors, [])

    def test_existing_form_dialog_fills_cyrillic_checkbox_and_disables_unknown(self):
        form_pdf = self.root / "Форма.pdf"
        with fitz.open() as doc:
            page = doc.new_page(width=500, height=400)
            field = fitz.Widget()
            field.field_name = "customer"
            field.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            field.rect = fitz.Rect(40, 60, 400, 105)
            field.field_value = "Initial"
            field.text_fontsize = 20
            page.add_widget(field)
            checkbox = fitz.Widget()
            checkbox.field_name = "approved"
            checkbox.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
            checkbox.rect = fitz.Rect(40, 150, 70, 180)
            page.add_widget(checkbox)
            doc.save(form_pdf)
        self.assertTrue(self.window.open_file(form_pdf))
        def interact():
            dialog = self.app.activeModalWidget()
            for editor in dialog.editors.values():
                if isinstance(editor, QCheckBox):
                    QTest.mouseClick(editor, Qt.MouseButton.LeftButton, pos=QPoint(8, editor.height() // 2))
                else:
                    editor.setText("Иван Петров")
            QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save), Qt.MouseButton.LeftButton)
        QTimer.singleShot(0, interact)
        self.window.forms_action.trigger()
        fields = self.window.engine.form_fields()
        self.assertEqual(next(f["value"] for f in fields if f["type"] == "text"), "Иван Петров")
        self.assertTrue(next(f["value"] for f in fields if f["type"] == "checkbox"))
        dialog = FormsDialog([dict(page=0, xref=99, name="signature", label="Подпись", type="signature", value="", readonly=False, supported=False)])
        self.assertEqual(dialog.editors, {})
        self.assertFalse(dialog.findChild(QLineEdit, "form_99").isEnabled())
        self.assertEqual(self.errors, [])

    def test_stamp_library_persistence_angle_opacity_and_actual_pointer_preview(self):
        source = self.root / "Печать.png"
        Image.new("RGBA", (180, 60), (20, 50, 180, 200)).save(source)
        self.assertTrue(self.window.load_stamp(source))
        self.assertEqual(self.window._library().items(), [])
        with patch("ui.QInputDialog.getText", return_value=("Моя печать", True)):
            self.window.save_library_stamp()
        reloaded = StampLibrary(self.root / "library")
        self.assertEqual(reloaded.items()[0]["name"], "Моя печать")
        self.window.select_library_stamp()
        self.window.stamp_angle.setValue(90)
        self.window.stamp_opacity.setValue(50)
        self.assertAlmostEqual(self.window.stamp_ratio, 1 / 3)
        point = QPointF(250 * self.window.scale, 230 * self.window.scale)
        self.window._page_mouse_moved(point)
        self.assertFalse(self.window.preview_item.pixmap().isNull())
        self.window.stamp_width.setValue(20)
        self.click_scene(point)
        self.assertEqual(len(self.window.engine.doc[0].get_images()), 1)
        with Image.open(source) as original:
            self.assertEqual(original.size, (180, 60))
        self.assertEqual(self.errors, [])

    def test_image_order_dialog_and_background_creation_use_real_files(self):
        paths = []
        for name, color in [("Красный.jpg", "red"), ("Синий.png", "blue")]:
            path = self.root / name
            Image.new("RGB", (90, 60), color).save(path)
            paths.append(str(path))
        dialog = ImagesToPdfDialog(paths)
        dialog.show()
        button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Ниже ↓")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        self.assertEqual(dialog.ordered_paths(), paths[::-1])
        self.window.create_pdf_from_images(dialog.ordered_paths(), "a4")
        self.wait_until(lambda: self.window.worker is None)
        self.assertEqual(self.window.engine.page_count, 2)
        self.assertTrue(self.window.engine.dirty)
        self.assertFalse(self.window.engine.path)
        pix = self.window.engine.doc[0].get_pixmap()
        rgb = pix.pixel(pix.width // 2, pix.height // 2)
        self.assertGreater(rgb[2], 200)
        self.assertLess(rgb[0], 20)
        dialog.close()
        self.assertEqual(self.errors, [])

    def test_real_png_export_dedicated_directory_and_optimization(self):
        self.window.export_images([1, 0], self.root, "png", 150)
        self.wait_until(lambda: self.window.worker is None)
        folders = list(self.root.glob("PDFMaster-pages-*"))
        self.assertEqual(len(folders), 1)
        self.assertEqual(len(list(folders[0].glob("*.png"))), 2)
        self.assertFalse(self.window.engine.dirty)
        self.assertEqual(self.window.engine.page_count, 3)
        optimized = self.root / "Оптимизировано.pdf"
        self.window.optimize_document(optimized)
        self.wait_until(lambda: self.window.worker is None)
        if optimized.exists():
            with fitz.open(optimized) as doc:
                self.assertEqual(len(doc), 3)
                self.assertIn("Секретный", doc[0].get_text())
        else:
            self.assertTrue(any("уже оптимизирован" in notice for notice in self.notices))
        self.assertEqual(self.errors, [])

    def test_ocr_advanced_flags_and_default_skip_reach_background_worker(self):
        calls = []
        def fake_ocr(data, pages, **options):
            calls.append(options)
            return data
        with patch("ui.ocr_pdf", side_effect=fake_ocr):
            self.window.run_ocr([0], skip_existing_text=True, deskew=True, enhance_contrast=True)
            self.wait_until(lambda: self.window.worker is None)
        self.assertTrue(calls[0]["skip_existing_text"])
        self.assertTrue(calls[0]["deskew"])
        self.assertTrue(calls[0]["enhance_contrast"])
        self.assertEqual(self.errors, [])

    def test_background_export_permission_guard_and_cancel_preserve_document(self):
        with patch.object(self.window.engine, "require_copy", side_effect=PermissionError("Копирование запрещено")):
            self.assertFalse(self.window.export_images([0], self.root))
        self.assertIn("Копирование запрещено", self.errors.pop())
        started = threading.Event()
        def operation(progress, cancel):
            started.set()
            end = time.monotonic() + 3
            while not cancel() and time.monotonic() < end:
                time.sleep(.01)
            return b"should not apply"
        called = []
        self.window._run_background("Тест отмены", operation, called.append)
        self.wait_until(started.is_set)
        self.assertFalse(self.window.open_action.isEnabled())
        self.window.cancel_ocr()
        self.wait_until(lambda: self.window.worker is None)
        self.assertEqual(called, [])
        self.assertFalse(self.window.engine.dirty)
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
