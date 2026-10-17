import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pikepdf
import pymupdf as fitz
from PIL import Image, ImageDraw, ImageOps

from pdf_tools import images_to_pdf, optimize_pdf, export_page_images


class PdfToolsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def jpeg(self, name="source.jpg", orientation=1):
        image = Image.new("RGB", (120, 80), "white")
        draw = ImageDraw.Draw(image)
        for box, color in (((0, 0, 59, 39), "red"), ((60, 0, 119, 39), "green"),
                           ((0, 40, 59, 79), "blue"), ((60, 40, 119, 79), "yellow")):
            draw.rectangle(box, fill=color)
        exif = Image.Exif()
        exif[274] = orientation
        path = self.root / name
        image.save(path, "JPEG", quality=95, exif=exif, dpi=(96, 96))
        return path

    @staticmethod
    def document(pages=2):
        with fitz.open() as doc:
            for number in range(pages):
                page = doc.new_page(width=144, height=72)
                page.insert_text((10, 30), f"Page {number + 1}")
            return doc.tobytes()

    def test_direct_jpeg_stream_preserved_and_input_order(self):
        first = self.jpeg("first.jpg")
        second = self.root / "second.jpg"
        Image.new("RGB", (90, 150), "cyan").save(second, quality=88)
        output = images_to_pdf([str(second), str(first)])
        with pikepdf.open(io.BytesIO(output)) as pdf:
            self.assertEqual(len(pdf.pages), 2)
            for page, path in zip(pdf.pages, (second, first)):
                image = next(iter(page.get_images().values()))
                self.assertEqual(image.Filter, pikepdf.Name.DCTDecode)
                self.assertEqual(image.read_raw_bytes(), path.read_bytes())

    def test_all_eight_exif_orientations_without_jpeg_reencoding(self):
        for orientation in range(1, 9):
            with self.subTest(orientation=orientation):
                source = self.jpeg(f"orientation-{orientation}.jpg", orientation)
                output = images_to_pdf([str(source)])
                with Image.open(source) as image:
                    expected = ImageOps.exif_transpose(image).convert("RGB")
                with fitz.open(stream=output, filetype="pdf") as doc:
                    pixmap = doc[0].get_pixmap(dpi=96, alpha=False)
                    actual = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
                    self.assertAlmostEqual(actual.width / actual.height,
                                           expected.width / expected.height, places=2)
                    for fraction_x, fraction_y in ((.2, .2), (.8, .2), (.2, .8), (.8, .8)):
                        a = actual.getpixel((int(actual.width * fraction_x), int(actual.height * fraction_y)))
                        e = expected.getpixel((int(expected.width * fraction_x), int(expected.height * fraction_y)))
                        self.assertLess(max(abs(x-y) for x, y in zip(a, e)), 10)
                with pikepdf.open(io.BytesIO(output)) as pdf:
                    self.assertEqual(next(iter(pdf.pages[0].get_images().values())).read_raw_bytes(), source.read_bytes())

    def test_png_alpha_and_multiframe_tiff(self):
        source = self.root / "alpha.png"
        image = Image.new("RGBA", (70, 50), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((10, 10, 30, 30), fill=(255, 0, 0, 128))
        image.save(source)
        tiff = self.root / "pages.tiff"
        Image.new("RGB", (60, 40), "blue").save(tiff, save_all=True,
            append_images=[Image.new("RGB", (40, 60), "green")], compression="tiff_deflate")
        data = images_to_pdf([str(source), str(tiff)])
        with pikepdf.open(io.BytesIO(data)) as pdf:
            self.assertEqual(len(pdf.pages), 3)
            self.assertIn("/SMask", next(iter(pdf.pages[0].get_images().values())))
        with fitz.open(stream=data, filetype="pdf") as doc:
            self.assertEqual(len(doc), 3)
            alpha = doc[0].get_pixmap(dpi=96, alpha=True)
            self.assertTrue(alpha.alpha)
            self.assertEqual(alpha.pixel(2, 2)[-1], 0)
            self.assertGreater(doc[1].rect.width, doc[1].rect.height)
            self.assertLess(doc[2].rect.width, doc[2].rect.height)

    def test_a4_layout_and_validation(self):
        source = self.jpeg()
        with fitz.open(stream=images_to_pdf([str(source)], "a4"), filetype="pdf") as doc:
            self.assertAlmostEqual(min(doc[0].rect.width, doc[0].rect.height), 595.276, places=2)
            self.assertAlmostEqual(max(doc[0].rect.width, doc[0].rect.height), 841.890, places=2)
        for paths, size in (([], "original"), ([str(source)], "a3")):
            with self.assertRaises(ValueError):
                images_to_pdf(paths, size)
        with patch("pdf_tools.Image.MAX_IMAGE_PIXELS", 10):
            with self.assertRaises((Image.DecompressionBombError, Image.DecompressionBombWarning, ValueError)):
                images_to_pdf([str(source)])

    def test_tiff_orientation_and_cmyk_channels(self):
        source = self.jpeg()
        tiff = self.root / "rotated.tiff"
        with Image.open(source) as image:
            image.save(tiff, format="TIFF", tiffinfo={274: 6})
        data = images_to_pdf([str(tiff)])
        with fitz.open(stream=data, filetype="pdf") as doc:
            self.assertLess(doc[0].rect.width, doc[0].rect.height)
        cmyk = self.root / "print.tiff"
        Image.new("CMYK", (40, 30), (0, 255, 0, 0)).save(cmyk)
        with pikepdf.open(io.BytesIO(images_to_pdf([str(cmyk)]))) as pdf:
            self.assertEqual(next(iter(pdf.pages[0].get_images().values())).ColorSpace,
                             pikepdf.Name.DeviceCMYK)

    def test_optimization_preserves_text_forms_images_and_rendering(self):
        jpeg = self.jpeg()
        with fitz.open() as doc:
            page = doc.new_page(width=500, height=500)
            available = page.insert_textbox(fitz.Rect(20, 20, 480, 250), "Lossless content " * 40, fontsize=12)
            self.assertGreaterEqual(available, 0)
            page.insert_image(fitz.Rect(20, 280, 200, 400), filename=str(jpeg))
            widget = fitz.Widget()
            widget.field_name = "customer"
            widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            widget.field_value = "Sample Customer"
            widget.rect = fitz.Rect(230, 300, 450, 330)
            page.add_widget(widget)
            original = doc.tobytes(deflate=False, use_objstms=0)
        optimized, stats = optimize_pdf(original)
        self.assertLessEqual(len(optimized), len(original))
        self.assertEqual(stats["before"], len(original))
        self.assertEqual(stats["after"], len(optimized))
        self.assertEqual(stats["saved_bytes"], len(original) - len(optimized))
        self.assertTrue(stats["changed"])
        self.assertGreater(stats["saved_bytes"], 0)
        with fitz.open(stream=original, filetype="pdf") as before, fitz.open(stream=optimized, filetype="pdf") as after:
            self.assertIn("Lossless content", before[0].get_text())
            self.assertEqual(before[0].get_text(), after[0].get_text())
            self.assertEqual(next(after[0].widgets()).field_value, "Sample Customer")
            self.assertEqual(before[0].get_pixmap().samples, after[0].get_pixmap().samples)
        with pikepdf.open(io.BytesIO(optimized)) as pdf:
            self.assertEqual(next(iter(pdf.pages[0].get_images().values())).read_raw_bytes(), jpeg.read_bytes())

    def test_optimization_keeps_original_when_candidate_is_larger(self):
        original, _ = optimize_pdf(self.document(1))
        result, stats = optimize_pdf(original)
        self.assertEqual(result, original)
        self.assertFalse(stats["changed"])
        self.assertEqual(stats["saved_bytes"], 0)

    def test_export_selected_pages_png_and_jpeg_with_dpi(self):
        calls = []
        outputs = export_page_images(self.document(), [1, 0], str(self.root / "png"),
                                     dpi=144, progress=lambda n, total: calls.append((n, total)))
        self.assertEqual([Path(x).name for x in outputs], ["page-0002.png", "page-0001.png"])
        self.assertEqual(calls, [(1, 2), (2, 2)])
        with Image.open(outputs[0]) as image:
            self.assertEqual(image.size, (288, 144))
        jpeg = export_page_images(self.document(), [0], str(self.root / "jpeg"), fmt="jpeg")
        with Image.open(jpeg[0]) as image:
            self.assertEqual(image.format, "JPEG")

    def test_export_never_overwrites_without_explicit_choice(self):
        folder = self.root / "export"
        folder.mkdir()
        existing = folder / "page-0001.png"
        existing.write_bytes(b"keep me")
        with self.assertRaises(FileExistsError):
            export_page_images(self.document(), [0, 1], str(folder))
        self.assertEqual(existing.read_bytes(), b"keep me")
        self.assertEqual(list(folder.iterdir()), [existing])
        export_page_images(self.document(), [0], str(folder), overwrite=True)
        self.assertEqual(existing.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_export_cancel_and_callback_failure_leave_no_partial_files(self):
        folder = self.root / "cancel"
        count = [0]
        with self.assertRaises(InterruptedError):
            export_page_images(self.document(), [0, 1], str(folder),
                progress=lambda n, total: count.__setitem__(0, n), cancel=lambda: count[0] > 0)
        self.assertFalse(folder.exists())
        def fail(n, total):
            raise RuntimeError("progress failure")
        with self.assertRaises(RuntimeError):
            export_page_images(self.document(), [0, 1], str(folder), progress=fail)
        self.assertFalse(folder.exists())

    def test_export_commit_failure_restores_existing_files(self):
        folder = self.root / "rollback"
        folder.mkdir()
        existing = folder / "page-0001.png"
        existing.write_bytes(b"original")
        import pdf_tools
        actual_replace = pdf_tools.os.replace
        def fail_second(source, target):
            if Path(target).name == "page-0002.png":
                raise OSError("simulated write failure")
            return actual_replace(source, target)
        with patch("pdf_tools.os.replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                export_page_images(self.document(), [0, 1], str(folder), overwrite=True)
        self.assertEqual(existing.read_bytes(), b"original")
        self.assertEqual(list(folder.iterdir()), [existing])

    def test_export_rejects_duplicates_invalid_range_and_excessive_size(self):
        for indices, options in (([0, 0], {}), ([99], {}), ([0], {"dpi": 0}),
                                 ([0], {"fmt": "tiff"}), ([], {})):
            with self.subTest(indices=indices, options=options), self.assertRaises(ValueError):
                export_page_images(self.document(), indices, str(self.root / "invalid"), **options)
        self.assertFalse((self.root / "invalid").exists())

    def test_protected_pdf_permissions_enforced(self):
        with fitz.open(stream=self.document(), filetype="pdf") as doc:
            protected = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256,
                owner_pw="owner secret", user_pw="", permissions=fitz.PDF_PERM_PRINT)
            locked = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256,
                owner_pw="owner secret", user_pw="reader", permissions=fitz.PDF_PERM_PRINT)
        for data in (protected, locked):
            with self.subTest(kind="restricted" if data == protected else "locked"):
                with self.assertRaises(PermissionError):
                    export_page_images(data, [0], str(self.root / "protected"))
                with self.assertRaises((PermissionError, pikepdf.PasswordError)):
                    optimize_pdf(data)
        self.assertFalse((self.root / "protected").exists())


if __name__ == "__main__":
    unittest.main()
