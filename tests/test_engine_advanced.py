"""Regression tests for source-inspired offline document tools."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf as fitz
from PIL import Image
from engine import PdfEngine, ocr_pdf, resource_root, _font_path


def add_form(page):
    widget = fitz.Widget()
    widget.field_name = "customer"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.field_value = "Initial"
    widget.rect = fitz.Rect(40, 170, 350, 215)
    widget.text_fontsize = 22
    widget.border_color = (0, 0, 0)
    widget.border_width = 1
    page.add_widget(widget)
    checkbox = fitz.Widget()
    checkbox.field_name = "approved"
    checkbox.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    checkbox.rect = fitz.Rect(40, 235, 65, 260)
    checkbox.field_value = "Off"
    page.add_widget(checkbox)


class AdvancedEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.pdf"
        with fitz.open() as doc:
            page = doc.new_page(width=400, height=300)
            page.insert_text((40, 70), "Native first page", fontsize=18)
            page.add_text_annot((370, 20), "Annotation original")
            add_form(page)
            page = doc.new_page(width=400, height=300)
            page.insert_text((40, 70), "Second page", fontsize=18)
            doc.save(self.source)
        self.engine = PdfEngine()
        self.engine.open(str(self.source))
        self.addCleanup(lambda: self.engine.doc.close() if self.engine.doc else None)

    def test_batch_transaction_validation_undo_and_independent_duplicate(self):
        self.engine.duplicate_pages([1, 0, 0])
        self.assertEqual(self.engine.page_count, 4)
        self.assertIn("Native first", self.engine.doc[1].get_text())
        self.assertIn("Second", self.engine.doc[2].get_text())
        fields = self.engine.form_fields()
        original = next(f for f in fields if f["page"] == 0 and f["type"] == "text")
        duplicate = next(f for f in fields if f["page"] == 1 and f["type"] == "text")
        self.assertNotEqual(original["xref"], duplicate["xref"])
        self.assertNotEqual(original["name"], duplicate["name"])
        self.engine.fill_form({duplicate["xref"]: "Копия"})
        self.assertEqual(next(f for f in self.engine.form_fields(0) if f["type"] == "text")["value"], "Initial")
        self.engine.undo()
        self.engine.undo()
        self.assertEqual(self.engine.page_count, 2)

        self.assertFalse(self.engine.can_undo)
        self.engine.rotate_pages([0, 1], 90)
        self.assertEqual([self.engine.doc[i].rotation for i in range(2)], [90, 90])
        self.engine.undo()
        self.assertEqual([self.engine.doc[i].rotation for i in range(2)], [0, 0])
        with self.assertRaises(ValueError):
            self.engine.delete_pages([0, 1])
        with self.assertRaises(ValueError):
            self.engine.reorder_pages([0, 0])
        self.assertFalse(self.engine.can_undo)
        self.engine.reorder_pages([1, 0])
        self.assertIn("Second", self.engine.doc[0].get_text())
        self.engine.delete_pages([1])
        self.assertEqual(self.engine.page_count, 1)
        self.engine.undo()
        self.assertEqual(self.engine.page_count, 2)

    def test_atomic_save_over_original_open_file_and_continue_editing(self):
        self.assertEqual(self.engine.path, str(self.source.resolve()))
        self.engine.rotate_page(0)
        self.engine.save(str(self.source))
        self.assertFalse(self.engine.dirty)
        with fitz.open(self.source) as saved:
            self.assertEqual(saved[0].rotation, 90)
            self.assertIn("Native first page", saved[0].get_text())
        self.engine.rotate_page(0)
        self.engine.save(str(self.source))
        with fitz.open(self.source) as saved:
            self.assertEqual(saved[0].rotation, 180)
        self.engine.undo()
        self.assertEqual(self.engine.doc[0].rotation, 90)

    def test_crop_rotations_repeated_and_undo(self):
        for rotation in (0, 90, 180, 270):
            self.engine.open(str(self.source))
            self.engine.doc[0].set_rotation(rotation)
            width, height = self.engine.page_size(0)
            self.engine.crop_page(0, (10, 20, 30, 40))
            self.assertEqual(self.engine.page_size(0), (width - 40, height - 60))
            self.engine.crop_page(0, (2, 3, 4, 5))
            self.assertEqual(self.engine.page_size(0), (width - 46, height - 68))
            self.engine.undo()
            self.engine.undo()
            self.assertEqual(self.engine.page_size(0), (width, height))
        with self.assertRaises(ValueError):
            self.engine.crop_page(0, (float("nan"), 0, 0, 0))
        with self.assertRaises(ValueError):
            self.engine.crop_page(0, (2000, 0, 0, 0))

    def test_crop_pixels_and_hidden_content_are_preserved(self):
        with fitz.open() as doc:
            page = doc.new_page(width=400, height=300)
            page.draw_rect((0, 0, 80, 300), fill=(1, 0, 0))
            page.draw_rect((80, 0, 400, 90), fill=(0, 0, 1))
            page.insert_text((300, 250), "Hidden text")
            raw = doc.tobytes()
        for rotation in (0, 90, 180, 270):
            self.engine.new_document(raw)
            self.engine.doc[0].set_rotation(rotation)
            before = Image.open(io.BytesIO(self.engine.render_page(0, 1))).convert("RGB")
            self.engine.crop_page(0, (20, 30, 40, 50))
            after = Image.open(io.BytesIO(self.engine.render_page(0, 1))).convert("RGB")
            for point in ((5, 5), (40, 40), (100, 100)):
                self.assertEqual(after.getpixel(point), before.getpixel((point[0]+20, point[1]+30)))
        self.engine.new_document(raw)
        self.engine.crop_page(0, (0, 0, 200, 0))
        # A visual crop retains the original content stream: it is not redaction.
        streams = b"".join(self.engine.doc.xref_stream(x) for x in self.engine.doc[0].get_contents())
        self.assertIn(b"48696464656e2074657874", streams.lower())

    def test_redact_native_raster_and_interactive_data_saved(self):
        with fitz.open() as doc:
            page = doc.new_page(width=400, height=300)
            image = Image.new("RGB", (400, 300), "white")
            image.paste("red", (30, 30, 200, 110))
            image.paste("blue", (280, 250, 360, 280))
            buffer = io.BytesIO(); image.save(buffer, format="PNG")
            page.insert_image(page.rect, stream=buffer.getvalue())
            page.insert_text((40, 70), "SECRET-12500", fontsize=18)
            page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(40, 40, 180, 90),
                              "uri": "https://secret-link.example/12500"})
            page.add_text_annot((50, 50), "Secret annotation contents")
            field = fitz.Widget(); field.field_name = "secret-widget"; field.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            field.rect = fitz.Rect(50, 50, 190, 90); field.field_value = "Secret form value"; page.add_widget(field)
            raw = doc.tobytes()
        self.engine.new_document(raw)
        self.engine.redact_area(0, (20, 20, 220, 130))
        self.assertNotIn("12500", self.engine.doc[0].get_text())
        self.assertFalse(self.engine.form_fields())
        self.assertFalse(self.engine.doc[0].get_links())
        self.assertFalse(list(self.engine.doc[0].annots() or []))
        saved = self.root / "redacted.pdf"
        self.engine.save(str(saved))
        with fitz.open(saved) as verified:
            self.assertNotIn("12500", verified[0].get_text())
            rendered = Image.open(io.BytesIO(verified[0].get_pixmap().tobytes("png"))).convert("RGB")
            self.assertEqual(rendered.getpixel((100, 80)), (0, 0, 0))
            self.assertEqual(rendered.getpixel((320, 265)), (0, 0, 255))
            for info in verified[0].get_images():
                payload = verified.extract_image(info[0])["image"]
                raster = Image.open(io.BytesIO(payload)).convert("RGB")
                self.assertEqual(raster.getpixel((100, 80)), (255, 255, 255))
            objects = "\n".join(verified.xref_object(i) for i in range(1, verified.xref_length()))
            self.assertNotIn("secret-link", objects)
            self.assertNotIn("secret-widget", objects)
            self.assertNotIn("Secret form value", objects)
            self.assertNotIn("Secret annotation contents", objects)
        self.engine.undo()
        self.assertIn("12500", self.engine.doc[0].get_text())

    def test_unicode_forms_values_rendering_reopen_undo_and_atomic(self):
        fields = self.engine.form_fields()
        text = next(field for field in fields if field["type"] == "text")
        checkbox = next(field for field in fields if field["type"] == "checkbox")
        initial = self.engine.doc[0].get_pixmap(clip=fitz.Rect(checkbox["rect"]), dpi=150)
        self.engine.fill_form({text["xref"]: "Иван Петров", checkbox["xref"]: True})
        values = {f["name"]: f["value"] for f in self.engine.form_fields()}
        self.assertEqual(values["customer"], "Иван Петров")
        self.assertTrue(values["approved"])
        checked = self.engine.doc[0].get_pixmap(clip=fitz.Rect(checkbox["rect"]), dpi=150)
        self.assertGreater(sum(v < 100 for v in checked.samples), sum(v < 100 for v in initial.samples))
        path = self.root / "forms.pdf"
        self.engine.save(str(path))
        self.engine.open(str(path))
        field = next(f for f in self.engine.form_fields() if f["type"] == "text")
        self.assertEqual(field["value"], "Иван Петров")
        # OCR the actual rendered appearance: a stored Unicode /V alone is not evidence.
        page = self.engine.doc[0]
        pix = page.get_pixmap(clip=fitz.Rect(field["rect"]), dpi=300)
        visual_ocr = pix.pdfocr_tobytes(language="rus+eng", tessdata=str(resource_root()/"tessdata"))
        with fitz.open(stream=visual_ocr, filetype="pdf") as probe:
            self.assertIn("иван петров", " ".join(probe[0].get_text().split()).casefold())
        self.engine.fill_form({field["xref"]: "Другое значение"})
        self.engine.undo()
        self.assertEqual(next(f for f in self.engine.form_fields() if f["type"] == "text")["value"], "Иван Петров")
        with self.assertRaises(ValueError):
            self.engine.fill_form({field["xref"]: "Modified", 999999: "invalid"})
        self.assertEqual(next(f for f in self.engine.form_fields() if f["type"] == "text")["value"], "Иван Петров")

    def test_readonly_rejected_without_history(self):
        page = self.engine.doc[0]
        widget = page.first_widget
        widget.field_flags |= fitz.PDF_FIELD_IS_READ_ONLY
        widget.update()
        field = next(f for f in self.engine.form_fields() if f["type"] == "text")
        self.assertTrue(field["readonly"])
        self.assertFalse(field["supported"])
        with self.assertRaises(ValueError):
            self.engine.fill_form({field["xref"]: "Forbidden"})
        self.assertFalse(self.engine.can_undo)

    def test_form_only_encrypted_permission_preserved_and_other_edits_denied(self):
        protected = self.root / "form-only.pdf"
        with fitz.open(self.source) as doc:
            doc.save(protected, encryption=fitz.PDF_ENCRYPT_AES_256,
                     user_pw="reader", owner_pw="owner", permissions=fitz.PDF_PERM_FORM)
        self.engine.open(str(protected), "reader")
        self.engine.require_fill()
        with self.assertRaises(PermissionError):
            self.engine.require_edit()
        with self.assertRaises(PermissionError):
            self.engine.require_copy()
        fields = self.engine.form_fields()
        field = next(f for f in fields if f["type"] == "text")
        check = next(f for f in fields if f["type"] == "checkbox")
        self.engine.fill_form({field["xref"]: "Иван Петров", check["xref"]: True})
        for operation in (lambda: self.engine.delete_page(0),
                          lambda: self.engine.redact_area(0, (10, 10, 100, 100)),
                          lambda: self.engine.rotate_pages([0, 1])):
            with self.assertRaises(PermissionError):
                operation()
        saved = self.root / "filled-protected.pdf"
        self.engine.save(str(saved))
        self.engine.open(str(saved), "reader")
        self.assertEqual(next(f for f in self.engine.form_fields() if f["type"] == "text")["value"], "Иван Петров")
        self.assertTrue(next(f for f in self.engine.form_fields() if f["type"] == "checkbox")["value"])
        with self.assertRaises(PermissionError):
            self.engine.require_edit()
        with self.assertRaises(PermissionError):
            self.engine.require_copy()
    
    def test_xfa_rejected_without_history(self):
        doc = self.engine.doc
        kind, value = doc.xref_get_key(doc.pdf_catalog(), "AcroForm")
        if kind == "xref":
            form_xref = int(value.split()[0])
            doc.xref_set_key(form_xref, "XFA", "(Unsupported XFA marker)")
        else:
            doc.xref_set_key(doc.pdf_catalog(), "AcroForm/XFA", "(Unsupported XFA marker)")
        self.assertTrue(self.engine.has_xfa)
        self.assertTrue(all(not f["supported"] for f in self.engine.form_fields()))
        with self.assertRaisesRegex(ValueError, "XFA"):
            self.engine.fill_form({})
        self.assertFalse(self.engine.can_undo)

    def test_safe_ocr_skip_preserves_forms_and_annotations(self):
        with fitz.open(self.source) as mixed:
            pix = mixed[1].get_pixmap(dpi=160)
            mixed.delete_page(1)
            page = mixed.new_page(width=400, height=300)
            page.insert_image(page.rect, pixmap=pix)
            data = mixed.tobytes()
        updates = []
        processed = ocr_pdf(data, [0, 1], dpi=200, progress=lambda d, t: updates.append((d, t)))
        self.engine.new_document(processed)
        self.assertEqual(len(self.engine.form_fields(0)), 2)
        self.assertEqual(len(list(self.engine.doc[0].annots() or [])), 1)
        self.assertIn("Native first", self.engine.doc[0].get_text())
        self.assertIn("Second", self.engine.doc[1].get_text())
        self.assertEqual(updates, [(1, 2), (2, 2)])
        force = ocr_pdf(data, [0], dpi=200, skip_existing_text=False)
        self.engine.new_document(force)
        self.assertFalse(self.engine.form_fields(0))

    def test_ocr_preprocess_options_dispatch_and_cancellation(self):
        with fitz.open(self.source) as doc:
            data = doc.tobytes()
        calls = []
        def process(image, deskew=False, enhance_contrast=False):
            calls.append((image.size, deskew, enhance_contrast))
            return image, 0.0
        with patch("scan_preprocess.preprocess_scan", process):
            result = ocr_pdf(data, [0], dpi=200, skip_existing_text=False, deskew=True, enhance_contrast=True)
        self.assertTrue(calls)
        self.assertEqual(calls[0][1:], (True, True))
        with fitz.open(stream=result, filetype="pdf") as doc:
            self.assertEqual(tuple(doc[0].rect), (0, 0, 400, 300))
        with self.assertRaisesRegex(RuntimeError, "отменено"):
            ocr_pdf(data, [0, 1], cancel=lambda: True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
