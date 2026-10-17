"""Offline conversion/export tools using img2pdf, pikepdf/QPDF and PyMuPDF.

Operations work on independent documents. Callers must also enforce permissions
of their original open document before passing a decrypted working copy here.
"""
from __future__ import annotations

import io
import math
import os
from pathlib import Path
import shutil
import tempfile
import warnings

import img2pdf
import pikepdf
import pymupdf as fitz
from PIL import Image, ImageOps


MAX_FRAME_PIXELS = 80_000_000


def _check_pixels(width: int, height: int) -> None:
    limit = min(Image.MAX_IMAGE_PIXELS or MAX_FRAME_PIXELS, MAX_FRAME_PIXELS)
    if width <= 0 or height <= 0 or width * height > limit:
        raise ValueError("Изображение слишком велико для безопасной обработки.")


def images_to_pdf(paths: list[str], page_size: str = "original") -> bytes:
    """Create ordered pages, preserving original JPEG streams and EXIF orientation.

    img2pdf embeds JPEG/PNG data; TIFF frames are normalized losslessly to PNG
    because Pillow can apply TIFF orientation while decoding. EXIF reflections
    are PDF matrix operations, so even mirrored JPEGs are never re-encoded.
    """
    if page_size not in ("original", "a4"):
        raise ValueError("Размер страницы должен быть original или a4.")
    if not paths:
        raise ValueError("Выберите хотя бы одно изображение.")
    images: list[bytes] = []
    orientations: list[int] = []
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        for name in paths:
            source = Path(name)
            if not source.is_file():
                raise FileNotFoundError(f"Изображение не найдено: {source.name}")
            raw = source.read_bytes()
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ("JPEG", "PNG", "TIFF"):
                    raise ValueError(f"Поддерживаются JPG, PNG и TIFF: {source.name}")
                if image.format == "TIFF":
                    for frame_index in range(image.n_frames):
                        image.seek(frame_index)
                        _check_pixels(*image.size)
                        frame = ImageOps.exif_transpose(image)
                        buffer = io.BytesIO()
                        # PNG cannot represent CMYK. A one-frame lossless TIFF
                        # keeps those channels for img2pdf instead of converting
                        # a print-color scan through an implicit RGB transform.
                        if frame.mode == "CMYK":
                            frame.save(buffer, format="TIFF", compression="tiff_deflate",
                                       dpi=image.info.get("dpi", (96, 96)))
                        else:
                            frame.save(buffer, format="PNG", dpi=image.info.get("dpi", (96, 96)))
                        images.append(buffer.getvalue())
                        orientations.append(1)
                else:
                    _check_pixels(*image.size)
                    orientation = image.getexif().get(274, 1)
                    if orientation not in range(1, 9):
                        raise ValueError(f"Некорректная EXIF-ориентация: {source.name}")
                    images.append(raw)
                    orientations.append(orientation)
        layout = (img2pdf.get_layout_fun(pagesize=(img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297)),
                                        fit=img2pdf.FitMode.into, auto_orient=True)
                  if page_size == "a4" else img2pdf.default_layout_fun)
        converted = img2pdf.convert(*images, rotation=img2pdf.Rotation.none,
                                   layout_fun=layout, engine=img2pdf.Engine.pikepdf,
                                   nodate=True, allow_oversized=False)
    # Orientation is a property of the page geometry, never of JPEG pixels.
    with pikepdf.open(io.BytesIO(converted)) as pdf:
        if len(pdf.pages) != len(orientations):
            raise ValueError("Количество страниц после преобразования не совпало с изображениями.")
        for page, orientation in zip(pdf.pages, orientations):
            width = float(page.MediaBox[2]) - float(page.MediaBox[0])
            height = float(page.MediaBox[3]) - float(page.MediaBox[1])
            if orientation in (2, 5, 7):
                page.contents_add(f"q -1 0 0 1 {width:.8f} 0 cm\n".encode(), prepend=True)
                page.contents_add(b"\nQ\n")
            elif orientation == 4:
                page.contents_add(f"q 1 0 0 -1 0 {height:.8f} cm\n".encode(), prepend=True)
                page.contents_add(b"\nQ\n")
            page.Rotate = {3: 180, 5: 270, 6: 90, 7: 90, 8: 270}.get(orientation, 0)
        output = io.BytesIO()
        pdf.save(output, compress_streams=True, object_stream_mode=pikepdf.ObjectStreamMode.generate)
        return output.getvalue()


def optimize_pdf(data: bytes) -> tuple[bytes, dict]:
    """Lossless QPDF structural/Flate optimization; keep original if not smaller."""
    original = bytes(data)
    with pikepdf.open(io.BytesIO(original)) as pdf:
        if pdf.is_encrypted and not pdf.owner_password_matched and not pdf.allow.modify_other:
            raise PermissionError("В этом PDF запрещено редактирование.")
        output = io.BytesIO()
        pdf.save(output, compress_streams=True, recompress_flate=True,
                 object_stream_mode=pikepdf.ObjectStreamMode.generate,
                 stream_decode_level=pikepdf.StreamDecodeLevel.generalized,
                 normalize_content=False, encryption=True if pdf.is_encrypted else False)
        candidate = output.getvalue()
    result = candidate if len(candidate) < len(original) else original
    return result, {"before": len(original), "after": len(result),
                    "saved_bytes": len(original) - len(result), "changed": result != original}


def _cancelled(cancel) -> None:
    if cancel and cancel():
        raise InterruptedError("Экспорт отменён.")


def export_page_images(data: bytes, indices: list[int], directory: str,
                       fmt: str = "png", dpi: int = 150, overwrite: bool = False,
                       progress=None, cancel=None) -> list[str]:
    """Render selected pages, staging all output before an atomic-file commit.

    progress(completed, total) is called after each staged page. cancel() must
    return bool. Cancellation or an exception rolls back this entire export;
    explicit overwrite additionally backs up/restores prior files on failure.
    """
    if fmt not in ("png", "jpeg"):
        raise ValueError("Формат экспорта должен быть png или jpeg.")
    if isinstance(dpi, bool) or not isinstance(dpi, int) or not 36 <= dpi <= 1200:
        raise ValueError("Разрешение должно быть целым числом от 36 до 1200 DPI.")
    if not indices or any(isinstance(i, bool) or not isinstance(i, int) for i in indices):
        raise ValueError("Выберите страницы для экспорта.")
    if len(set(indices)) != len(indices):
        raise ValueError("Одна страница выбрана для экспорта несколько раз.")
    target_dir = Path(directory).resolve()
    extension = "jpg" if fmt == "jpeg" else "png"
    targets = [target_dir / f"page-{i + 1:04d}.{extension}" for i in indices]
    staging: Path | None = None
    committed: list[Path] = []
    backups: dict[Path, Path] = {}
    created_directory = False
    with fitz.open(stream=bytes(data), filetype="pdf") as doc:
        if doc.needs_pass:
            raise PermissionError("Сначала откройте защищённый PDF с паролем в программе.")
        if not doc.permissions & fitz.PDF_PERM_COPY:
            raise PermissionError("В этом PDF запрещено копирование содержимого.")
        if any(i < 0 or i >= len(doc) for i in indices):
            raise ValueError("Номер страницы выходит за пределы PDF.")
        for i in indices:
            rect = doc[i].rect
            _check_pixels(math.ceil(rect.width * dpi / 72), math.ceil(rect.height * dpi / 72))
        for target in targets:
            if target.exists() and (not overwrite or not target.is_file()):
                raise FileExistsError(f"Файл уже существует: {target.name}")
        _cancelled(cancel)
        try:
            created_directory = not target_dir.exists()
            target_dir.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=".pdfmaster-export-", dir=target_dir))
            for completed, (index, target) in enumerate(zip(indices, targets), 1):
                _cancelled(cancel)
                pixmap = doc[index].get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
                (staging / target.name).write_bytes(pixmap.tobytes(fmt, jpg_quality=95))
                del pixmap
                if progress:
                    progress(completed, len(indices))
            _cancelled(cancel)
            for number, target in enumerate(targets):
                _cancelled(cancel)
                source = staging / target.name
                if overwrite:
                    if target.exists():
                        if not target.is_file():
                            raise FileExistsError(f"Путь занят папкой: {target.name}")
                        backup = staging / f".backup-{number}"
                        os.replace(target, backup)
                        backups[target] = backup
                    os.replace(source, target)
                elif os.name == "nt":
                    os.rename(source, target)  # Windows rename refuses existing destinations.
                else:
                    os.link(source, target)  # Atomic exclusive creation on POSIX.
                    source.unlink()
                committed.append(target)
            _cancelled(cancel)
        except BaseException:
            for target in reversed(committed):
                target.unlink(missing_ok=True)
            for target, backup in backups.items():
                os.replace(backup, target)
            raise
        finally:
            if staging is not None:
                shutil.rmtree(staging)
            if created_directory and target_dir.exists():
                try:
                    target_dir.rmdir()  # Remove only an empty directory created by this operation.
                except OSError:
                    pass
    return [str(target) for target in targets]
