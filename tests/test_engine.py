import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf as fitz
from PIL import Image
from engine import PdfEngine, PasswordRequired, ocr_pdf, _font_path


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "original.pdf"
        with fitz.open() as doc:
            for text in ("Исходная строка", "Вторая страница"):
                page = doc.new_page(width=500, height=400)
                page.insert_text((50, 100), text, fontname="unicode", fontfile=_font_path(), fontsize=20)
            doc.save(self.source)
        self.engine = PdfEngine()
        self.engine.open(str(self.source))
        self.addCleanup(lambda: self.engine.doc.close() if self.engine.doc else None)

    def test_real_cyrillic_replacement_and_undo(self):
        line = self.engine.text_lines(0)[0]
        self.engine.replace_text(0, line["rect"], "Новая строка", size=20)
        text = self.engine.doc[0].get_text()
        self.assertIn("Новая строка", text)
        self.assertNotIn("Исходная", text)
        self.assertTrue(self.engine.can_undo)
        self.engine.undo()
        self.assertIn("Исходная", self.engine.doc[0].get_text())
        self.assertFalse(self.engine.dirty)
        self.engine.redo()
        self.assertIn("Новая строка", self.engine.doc[0].get_text())
        target = self.root / "edited.pdf"
        self.engine.save(str(target))
        with fitz.open(target) as saved:
            self.assertIn("Новая строка", saved[0].get_text())
            self.assertNotIn("Исходная", saved[0].get_text())
        self.assertFalse(self.engine.dirty)

    def test_overflow_rolls_back_and_does_not_enter_history(self):
        line = self.engine.text_lines(0)[0]
        with self.assertRaises(ValueError):
            self.engine.replace_text(0, line["rect"], "Очень длинная строка " * 100, size=20)
        self.assertIn("Исходная строка", self.engine.doc[0].get_text())
        self.assertFalse(self.engine.can_undo)
        self.assertFalse(self.engine.dirty)

    def test_page_operations_and_render(self):
        self.engine.rotate_page(0)
        self.assertEqual(self.engine.page_size(0), (400, 500))
        png = Image.open(io.BytesIO(self.engine.render_page(0, 1)))
        self.assertEqual(png.size, (400, 500))
        self.engine.move_page(0, 1)
        self.assertIn("Вторая", self.engine.doc[0].get_text())
        self.engine.append_pdf(str(self.source))
        self.assertEqual(self.engine.page_count, 4)
        self.engine.delete_page(2)
        extracted = self.root / "extract.pdf"
        self.engine.extract_pages([1, 0], str(extracted))
        with fitz.open(extracted) as doc:
            self.assertEqual(len(doc), 2)
            self.assertIn("Исходная", doc[0].get_text())
        self.assertEqual(len(self.engine.search("строка")), 1)
        output = self.root / "text.txt"
        self.engine.export_text(str(output))
        self.assertIn("Вторая страница", output.read_text(encoding="utf-8"))

    def test_transparent_stamp_and_add_text(self):
        image_path = self.root / "stamp.png"
        image = Image.new("RGBA", (80, 30), (255, 255, 255, 255))
        for x in range(10, 70):
            image.putpixel((x, 15), (0, 0, 200, 255))
        image.save(image_path)
        self.engine.insert_image(0, str(image_path), (50, 150, 210, 210), remove_white=True)
        images = self.engine.doc[0].get_images()
        self.assertTrue(images)
        self.assertGreater(images[0][1], 0)  # Soft mask confirms alpha survived.
        self.engine.add_text(0, (50, 230, 350, 270), "Подписано", 16)
        self.assertIn("Подписано", self.engine.doc[0].get_text())

    def test_stamp_upright_on_rotated_page(self):
        image_path = self.root / "orientation.png"
        image = Image.new("RGB", (90, 30), "red")
        image.paste("blue", (45, 0, 90, 30))
        image.save(image_path)
        for rotation in (90, 180, 270):
            self.engine.open(str(self.source))
            self.engine.doc[0].set_rotation(rotation)
            page = self.engine.doc[0]
            target = fitz.Rect(50, 50, 230, 110) * page.derotation_matrix
            self.engine.insert_image(0, str(image_path), target)
            render = Image.open(io.BytesIO(self.engine.render_page(0, 1)))
            self.assertEqual(render.getpixel((60, 80)), (255, 0, 0))
            self.assertEqual(render.getpixel((220, 80)), (0, 0, 255))

    def test_password_permissions_survive_undo(self):
        encrypted = self.root / "protected.pdf"
        with fitz.open(self.source) as doc:
            doc.save(encrypted, encryption=fitz.PDF_ENCRYPT_AES_256,
                     owner_pw="owner-secret", user_pw="reader", permissions=fitz.PDF_PERM_PRINT)
        with self.assertRaises(PasswordRequired):
            self.engine.open(str(encrypted))
        self.assertIn("Исходная", self.engine.doc[0].get_text())  # Failed open preserves current doc.
        self.engine.open(str(encrypted), "reader")
        with self.assertRaises(PermissionError):
            self.engine.rotate_page(0)
        with self.assertRaises(PermissionError):
            self.engine.export_text(str(self.root / "blocked.txt"))
        self.engine.open(str(encrypted), "owner-secret")
        self.engine.rotate_page(0)
        self.engine.undo()
        self.engine.rotate_page(0)
        saved = self.root / "owner-copy.pdf"
        self.engine.save(str(saved))
        self.engine.open(str(saved), "owner-secret")
        self.engine.rotate_page(0)  # Saving an owner-authenticated PDF preserves owner access.

    def test_ocr_russian_scan_search_edit_and_cancel(self):
        with fitz.open() as doc:
            page = doc.new_page(width=500, height=400)
            page.insert_text((45, 100), "Договор номер 12345", fontname="unicode",
                             fontfile=_font_path(), fontsize=24)
            pix = page.get_pixmap(dpi=200)
            with fitz.open() as scan:
                p = scan.new_page(width=500, height=400)
                p.insert_image(p.rect, pixmap=pix)
                raw = scan.tobytes()
        updates = []
        result = ocr_pdf(raw, [0], progress=lambda done, total: updates.append((done, total)))
        self.engine.replace_document(result)
        self.assertIn("Договор", self.engine.doc[0].get_text())
        self.assertTrue(self.engine.search("12345"))
        self.assertEqual(updates, [(1, 1)])
        line = self.engine.text_lines(0)[0]
        self.engine.replace_text(0, line["rect"], "Договор номер 67890", size=line["size"])
        self.assertIn("67890", self.engine.doc[0].get_text())
        self.assertNotIn("12345", self.engine.doc[0].get_text())
        # Regression: compacting live snapshots used to corrupt cached image
        # ColorSpace references after OCR/redaction, making later stamps invisible.
        saved = self.root / "ocr-edited.pdf"
        self.engine.save(str(saved))
        stamp = self.root / "blue-stamp.png"
        Image.new("RGBA", (60, 20), (0, 0, 200, 255)).save(stamp)
        self.engine.insert_image(0, str(stamp), (300, 300, 420, 340))
        self.engine.save(str(saved))
        with fitz.open(saved) as verified:
            rendered = Image.open(io.BytesIO(verified[0].get_pixmap().tobytes("png")))
            self.assertEqual(rendered.getpixel((350, 320)), (0, 0, 200))
            self.assertIn("67890", verified[0].get_text())
            self.assertNotIn("12345", verified[0].get_text())
        with self.assertRaisesRegex(RuntimeError, "отменено"):
            ocr_pdf(raw, [0], cancel=lambda: True)
        with fitz.open(stream=raw, filetype="pdf") as original:
            self.assertFalse(original[0].get_text().strip())

    def test_rotated_ocr_visual_size(self):
        with fitz.open(self.source) as doc:
            doc[0].set_rotation(90)
            raw = doc.tobytes()
        result = ocr_pdf(raw, [0], dpi=200)
        with fitz.open(stream=result, filetype="pdf") as doc:
            self.assertAlmostEqual(doc[0].rect.width, 400)
            self.assertAlmostEqual(doc[0].rect.height, 500)
            self.assertEqual(doc[0].rotation, 90)
            self.assertIn("Исходная", doc[0].get_text())

    def test_sideways_scan_manually_rotated_upright_ocr(self):
        with fitz.open(self.source) as native:
            native[0].set_rotation(90)
            raster = native[0].get_pixmap(dpi=200)
        with fitz.open() as scan:
            page = scan.new_page(width=400, height=500)
            page.insert_image(page.rect, pixmap=raster)
            page.set_rotation(270)
            raw = scan.tobytes()
        result = ocr_pdf(raw, [0], dpi=200)
        with fitz.open(stream=result, filetype="pdf") as doc:
            self.assertIn("Исходная", doc[0].get_text())
            self.assertAlmostEqual(doc[0].rect.width, 500)
            self.assertAlmostEqual(doc[0].rect.height, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
