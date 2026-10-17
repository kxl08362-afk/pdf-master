"""Local PDF editing engine. Coordinates are unrotated PDF points unless documented."""
from __future__ import annotations

import io
import math
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
from typing import Callable

import pymupdf as fitz
from PIL import Image


class PasswordRequired(ValueError):
    pass


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "resources"


def _font_path() -> str:
    for path in (resource_root() / "fonts" / "DejaVuSans.ttf",
                 resource_root() / "fonts" / "NotoSans-Regular.ttf",
                 Path("C:/Windows/Fonts/arial.ttf")):
        if path.is_file():
            return str(path)
    raise RuntimeError("Не найден шрифт с поддержкой кириллицы в resources/fonts.")


def _atomic_write(path: str, data: bytes) -> None:
    target = Path(path).resolve()
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class PdfEngine:
    HISTORY_LIMIT = 15
    HISTORY_BYTES = 200 * 1024 * 1024

    def __init__(self):
        self.doc: fitz.Document | None = None
        self.path = ""
        self.dirty = False
        self._undo: list[tuple[bytes, bool]] = []
        self._redo: list[tuple[bytes, bool]] = []
        self._editable = True
        self._encrypted = False
        self._password = ""
        self._owner_password = ""
        self._permissions = -1
        self._can_copy = True
        self._can_fill = True

    @property
    def page_count(self) -> int:
        return len(self.doc) if self.doc is not None else 0

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def has_signatures(self) -> bool:
        if self.doc is None:
            return False
        if self.doc.get_sigflags() > 0:
            return True
        return any(widget.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE
                   for page in self.doc for widget in (page.widgets() or []))

    def _require(self) -> fitz.Document:
        if self.doc is None:
            raise ValueError("Сначала откройте PDF.")
        return self.doc

    def _require_edit(self):
        self._require()
        if not self._editable:
            raise PermissionError("Владелец PDF запретил изменение документа. Нужен пароль владельца.")

    def require_edit(self):
        self._require_edit()

    def require_copy(self):
        self._require()
        if not self._can_copy:
            raise PermissionError("Владелец PDF запретил копирование.")

    def require_fill(self):
        self._require()
        if not self._can_fill:
            raise PermissionError("Владелец PDF запретил заполнение форм. Нужен пароль владельца.")

    @property
    def has_xfa(self):
        if self.doc is None:
            return False
        kind, value = self.doc.xref_get_key(self.doc.pdf_catalog(), "AcroForm")
        if kind == "xref":
            return self.doc.xref_get_key(int(value.split()[0]), "XFA")[0] != "null"
        return kind == "dict" and "/XFA" in value

    def open(self, path: str, password: str | None = None):
        # Work from memory: a file-backed MuPDF document keeps its source handle
        # open on Windows and would prevent atomic Ctrl+S replacement of that file.
        candidate = fitz.open(stream=Path(path).read_bytes(), filetype="pdf")
        try:
            if not candidate.is_pdf:
                raise ValueError("Откройте файл формата PDF.")
            encrypted = bool(candidate.is_encrypted or candidate.needs_pass or candidate.metadata.get("encryption"))
            authentication = 0
            if candidate.needs_pass:
                if password is None or not (authentication := candidate.authenticate(password)):
                    raise PasswordRequired("Введите правильный пароль PDF.")
            elif encrypted:
                authentication = candidate.authenticate(password or "")
            permissions = candidate.permissions
            editable = not encrypted or bool(authentication & 4) or bool(permissions & fitz.PDF_PERM_MODIFY)
            if len(candidate) == 0:
                raise ValueError("В PDF нет страниц.")
        except Exception:
            candidate.close()
            raise
        if self.doc is not None:
            self.doc.close()
        self.doc = candidate
        self.path = str(Path(path).resolve())
        self.dirty = False
        self._undo.clear()
        self._redo.clear()
        self._editable = editable
        self._encrypted = encrypted
        self._password = password or ""
        self._owner_password = (password or "") if authentication & 4 else secrets.token_urlsafe(24)
        self._permissions = permissions
        self._can_copy = not encrypted or bool(authentication & 4) or bool(permissions & fitz.PDF_PERM_COPY)
        self._can_fill = not encrypted or bool(authentication & 4) or bool(permissions & fitz.PDF_PERM_FORM)

    def to_bytes(self) -> bytes:
        # Garbage collection renumbers xrefs and can invalidate MuPDF's image
        # resource cache on the still-open document. Snapshots must not renumber.
        return self._require().tobytes(garbage=0, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)

    def _load(self, data: bytes):
        candidate = fitz.open(stream=data, filetype="pdf")
        if candidate.needs_pass or not candidate.is_pdf or not len(candidate):
            candidate.close()
            raise ValueError("Некорректный PDF или документ без страниц.")
        old = self.doc
        self.doc = candidate
        if old is not None:
            old.close()

    def _trim_history(self):
        while len(self._undo) > self.HISTORY_LIMIT or (
            len(self._undo) > 1 and sum(len(item[0]) for item in self._undo) > self.HISTORY_BYTES
        ):
            self._undo.pop(0)

    def _transaction(self, operation: Callable[[], None], permission="edit"):
        if permission == "fill":
            self.require_fill()
        else:
            self._require_edit()
        before = self.to_bytes()
        dirty_before = self.dirty
        try:
            operation()
        except Exception:
            self._load(before)
            self.dirty = dirty_before
            raise
        self._undo.append((before, dirty_before))
        self._trim_history()
        self._redo.clear()
        self.dirty = True

    def replace_document(self, data: bytes):
        self._transaction(lambda: self._load(data))

    def new_document(self, data: bytes):
        self._load(data)
        self.path = ""
        self.dirty = True
        self._undo.clear()
        self._redo.clear()
        self._editable = self._can_copy = self._can_fill = True
        self._encrypted = False
        self._password = self._owner_password = ""
        self._permissions = -1

    def render_page(self, index: int, scale: float = 1.3) -> bytes:
        if not 0.05 <= scale <= 8:
            raise ValueError("Недопустимый масштаб.")
        return self._require()[index].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes("png")

    def page_size(self, index: int) -> tuple[float, float]:
        rect = self._require()[index].rect
        return rect.width, rect.height

    def text_lines(self, index: int) -> list[dict]:
        lines = []
        for block in self._require()[index].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = line["spans"]
                text = "".join(span["text"] for span in spans)
                if not text.strip():
                    continue
                largest = max(spans, key=lambda span: len(span["text"]))
                rgb = largest.get("color", 0)
                size = float(largest["size"])
                if "glyphless" in largest.get("font", "").lower():
                    # OCR's synthetic font size is not a usable size for a real font.
                    # Offer the largest real-font size fitting the recognized line.
                    font = fitz.Font(fontfile=_font_path())
                    bounds = fitz.Rect(line["bbox"])
                    size = min(size, bounds.height / (font.ascender - font.descender),
                               bounds.width / max(font.text_length(text, fontsize=1), 0.01))
                lines.append({"rect": tuple(line["bbox"]), "text": text,
                              "size": size,
                              "color": tuple(((rgb >> shift) & 255) / 255 for shift in (16, 8, 0))})
        return lines

    def search(self, query: str) -> list[tuple[int, tuple]]:
        if not query.strip():
            return []
        return [(page.number, tuple(rect)) for page in self._require() for rect in page.search_for(query)]

    def _checked_rect(self, index: int, rect) -> fitz.Rect:
        page = self._require()[index]
        result = fitz.Rect(rect)
        bounds = page.rect * page.derotation_matrix
        if result.is_empty or result.is_infinite or not bounds.contains(result):
            raise ValueError("Область должна находиться внутри страницы и иметь ненулевой размер.")
        return result

    def _insert_text(self, page, rect, text, size, color):
        if size <= 0 or size > 500:
            raise ValueError("Размер шрифта должен быть от 1 до 500.")
        font_path = _font_path()
        font = fitz.Font(fontfile=font_path)
        line_height = (font.ascender - font.descender) * size
        lines = []
        for paragraph in text.split("\n"):
            current = ""
            for word in re.findall(r"\S+\s*", paragraph):
                candidate = current + word
                if font.text_length(candidate.rstrip(), fontsize=size) <= rect.width + 0.5:
                    current = candidate
                else:
                    if current:
                        lines.append(current.rstrip())
                        current = ""
                    for character in word.lstrip():
                        if font.text_length(current + character, fontsize=size) > rect.width + 0.5:
                            if not current:
                                raise ValueError("Текст не помещается в выделенную область.")
                            lines.append(current.rstrip())
                            current = ""
                        current += character
            lines.append(current.rstrip())
        if len(lines) * line_height > rect.height + 0.1:
            raise ValueError("Текст не помещается в выделенную область. Уменьшите шрифт или сократите текст.")
        for number, line in enumerate(lines):
            page.insert_text((rect.x0, rect.y0 + font.ascender * size + number * line_height), line,
                             fontname="pdfdeskunicode", fontfile=font_path, fontsize=size, color=color,
                             overlay=True)

    def replace_text(self, index: int, rect, text: str, size: float | None = None, color=(0, 0, 0)):
        target = self._checked_rect(index, rect)
        if size is None:
            matches = [line for line in self.text_lines(index) if fitz.Rect(line["rect"]).intersects(target)]
            size = matches[0]["size"] if matches else 12

        def operation():
            page = self._require()[index]
            # Avoid touching neighbouring text whose glyph boxes only meet the boundary.
            inset = min(0.2, target.height * 0.02)
            removal = fitz.Rect(target.x0 + inset, target.y0 + inset, target.x1 - inset, target.y1 - inset)
            raster_text = any(
                "glyphless" in span.get("font", "").lower()
                and fitz.Rect(span["bbox"]).intersects(target)
                for block in page.get_text("dict")["blocks"]
                for line in block.get("lines", []) for span in line["spans"]
            )
            if raster_text:
                # OCR boxes round to glyph interiors. Clear the one-point scan
                # fringe too, otherwise old ink specks survive beside corrections.
                removal = (target + (-1, -1, 1, 1)) & (page.rect * page.derotation_matrix)
            page.add_redact_annot(removal, fill=(1, 1, 1), cross_out=False)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=0, text=0)
            # MuPDF 1.28 can attach an invalid built-in sRGB profile to the
            # replacement raster created by redaction. DeviceRGB describes the
            # same sRGB pixels without that malformed profile.
            for image in page.get_images():
                kind, value = self.doc.xref_get_key(image[0], "ColorSpace")
                color_space = self.doc.xref_object(int(value.split()[0])) if kind == "xref" else value
                match = re.search(r"/ICCBased\s+(\d+)\s+0\s+R", color_space)
                if match:
                    profile = self.doc.xref_stream(int(match.group(1))) or b""
                    if b"Artifex Software sRGB ICC Profile" in profile:
                        self.doc.xref_set_key(image[0], "ColorSpace", "/DeviceRGB")
            if text:
                self._insert_text(page, target, text, size, color)
        self._transaction(operation)

    def add_text(self, index: int, rect, text: str, size: float = 12):
        target = self._checked_rect(index, rect)
        if not text.strip():
            raise ValueError("Введите текст.")
        self._transaction(lambda: self._insert_text(self._require()[index], target, text, size, (0, 0, 0)))

    def insert_image(self, index: int, image_path: str, rect, remove_white: bool = False):
        target = self._checked_rect(index, rect)
        with Image.open(image_path) as source:
            image = source.convert("RGBA")
            if remove_white:
                # A continuous white-to-alpha ramp also removes JPEG halos around pen strokes.
                pixels = image.load()
                for y in range(image.height):
                    for x in range(image.width):
                        r, g, b, alpha = pixels[x, y]
                        whiteness = min(r, g, b)
                        opacity = min(255, max(0, round((255 - whiteness) * 255 / 40)))
                        pixels[x, y] = (r, g, b, round(alpha * opacity / 255))
            stream = io.BytesIO()
            image.save(stream, format="PNG")
        self._transaction(lambda: self._require()[index].insert_image(target, stream=stream.getvalue(),
                                                                      rotate=self._require()[index].rotation,
                                                                      keep_proportion=True, overlay=True))

    def rotate_page(self, index: int):
        self.rotate_pages([index])

    def delete_page(self, index: int):
        self.delete_pages([index])

    def _page_indices(self, indices):
        self._require()
        values = list(indices)
        if not values or any(not isinstance(i, int) or isinstance(i, bool) or i < 0 or i >= self.page_count
                             for i in values):
            raise ValueError("Выберите существующие страницы.")
        return sorted(set(values))

    def rotate_pages(self, indices, degrees=90):
        selected = self._page_indices(indices)
        if not isinstance(degrees, int) or degrees % 90:
            raise ValueError("Поворот должен быть кратен 90 градусам.")
        if degrees % 360 == 0:
            return
        def operation():
            for index in selected:
                page = self.doc[index]
                page.set_rotation((page.rotation + degrees) % 360)
        self._transaction(operation)

    def delete_pages(self, indices):
        selected = self._page_indices(indices)
        if len(selected) >= self.page_count:
            raise ValueError("В документе должна остаться хотя бы одна страница.")
        self._transaction(lambda: self.doc.delete_pages(selected))

    def duplicate_pages(self, indices):
        selected = self._page_indices(indices)
        def operation():
            # Independent source documents make annotations/widgets independent.
            # insert_pdf registers form fields and renames colliding field names.
            original = self.to_bytes()
            for index in reversed(selected):
                with fitz.open(stream=original, filetype="pdf") as source:
                    self.doc.insert_pdf(source, from_page=index, to_page=index,
                                        start_at=index + 1, annots=True, widgets=True, join_duplicates=False)
        self._transaction(operation)

    def reorder_pages(self, order):
        self._require()
        if any(not isinstance(i, int) or isinstance(i, bool) for i in order) or sorted(order) != list(range(self.page_count)):
            raise ValueError("Новый порядок должен содержать каждую страницу ровно один раз.")
        if list(order) == list(range(self.page_count)):
            return
        self._transaction(lambda: self.doc.select(list(order)))

    def crop_page(self, index: int, visual_margins_pt):
        if len(visual_margins_pt) != 4:
            raise ValueError("Укажите поля: слева, сверху, справа, снизу.")
        left, top, right, bottom = map(float, visual_margins_pt)
        if any(not math.isfinite(v) or v < 0 for v in (left, top, right, bottom)):
            raise ValueError("Поля должны быть неотрицательными числами.")
        page = self._require()[index]
        visual = page.rect
        if left + right >= visual.width - 1 or top + bottom >= visual.height - 1:
            raise ValueError("После обрезки должна остаться непустая страница.")
        if not any(visual_margins_pt):
            return
        # Derotation gives coordinates local to the CURRENT CropBox. The new
        # CropBox is specified relative to the original unrotated MediaBox.
        rectangle = fitz.Rect(left, top, visual.width - right, visual.height - bottom) * page.derotation_matrix
        rectangle += (page.cropbox.x0, page.cropbox.y0, page.cropbox.x0, page.cropbox.y0)
        self._transaction(lambda: self.doc[index].set_cropbox(rectangle))

    def redact_area(self, index: int, rect, fill=(0, 0, 0)):
        target = self._checked_rect(index, rect)
        if len(fill) != 3 or any(not 0 <= float(c) <= 1 for c in fill):
            raise ValueError("Цвет удаления должен содержать три числа от 0 до 1.")
        def operation():
            page = self.doc[index]
            for link in list(page.get_links()):
                if fitz.Rect(link["from"]).intersects(target):
                    page.delete_link(link)
            for widget in list(page.widgets() or []):
                if widget.rect.intersects(target):
                    page.delete_widget(widget)
            for annot in list(page.annots() or []):
                if annot.rect.intersects(target):
                    page.delete_annot(annot)
            page.add_redact_annot(target, fill=fill, cross_out=False)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS,
                                  graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                                  text=fitz.PDF_REDACT_TEXT_REMOVE)
            page.clean_contents(sanitize=True)
        self._transaction(operation)

    def form_fields(self, index=None):
        doc = self._require()
        pages = range(len(doc)) if index is None else [index]
        types = {fitz.PDF_WIDGET_TYPE_TEXT: "text", fitz.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
                 fitz.PDF_WIDGET_TYPE_COMBOBOX: "combo", fitz.PDF_WIDGET_TYPE_LISTBOX: "list",
                 fitz.PDF_WIDGET_TYPE_RADIOBUTTON: "radio", fitz.PDF_WIDGET_TYPE_SIGNATURE: "signature",
                 fitz.PDF_WIDGET_TYPE_BUTTON: "button"}
        xfa = self.has_xfa
        result = []
        for page_index in pages:
            page = doc[page_index]
            for widget in page.widgets() or []:
                field_type = types.get(widget.field_type, "unknown")
                readonly = bool(widget.field_flags & fitz.PDF_FIELD_IS_READ_ONLY)
                value = widget.field_value
                if field_type == "checkbox":
                    value = value not in (False, None, "Off", "", 0)
                result.append({"page": page_index, "xref": widget.xref, "name": widget.field_name or "",
                               "label": widget.field_label or widget.field_name or "",
                               "type": field_type, "value": value, "rect": tuple(widget.rect),
                               "choices": list(widget.choice_values or []), "readonly": readonly,
                               "supported": not xfa and not readonly and field_type in {"text", "checkbox"}})
        return result

    def _text_field_appearance(self, page_index, xref, text):
        page = self.doc[page_index]
        widget = page.load_widget(xref)
        rect = widget.rect
        width, height = rect.width, rect.height
        color = tuple(widget.text_color or (0, 0, 0))
        background = widget.fill_color
        border = widget.border_color
        border_width = widget.border_width or 0
        font = fitz.Font(fontfile=_font_path())
        display_text = "•" * len(text) if widget.field_flags & fitz.PDF_TX_FIELD_IS_PASSWORD else text
        multiline = bool(widget.field_flags & fitz.PDF_TX_FIELD_IS_MULTILINE)
        if not multiline and "\n" in display_text:
            raise ValueError("Это поле поддерживает только одну строку.")
        margin = max(2, border_width + 1)
        usable_width, usable_height = width - 2 * margin, height - 2 * margin
        if usable_width <= 0 or usable_height <= 0:
            raise ValueError("Поле слишком мало для заполнения.")
        size = float(widget.text_fontsize or 12)
        size = min(size, usable_height / (font.ascender - font.descender))
        if not multiline:
            size = min(size, usable_width / max(font.text_length(display_text, fontsize=1), 0.01))
        # AcroForm accepts arbitrary Unicode values; the appearance embeds our
        # actual font rather than Base14, whose Cyrillic glyphs are unavailable.
        temp = self.doc.new_page(width=width, height=height)
        temp_index = temp.number
        try:
            if background:
                temp.draw_rect(temp.rect, fill=background, color=None)
            if border and border_width:
                temp.draw_rect(temp.rect + (border_width/2, border_width/2, -border_width/2, -border_width/2),
                               color=border, width=border_width)
            area = fitz.Rect(margin, margin, width - margin, height - margin)
            # Find the largest readable size that fits a multiline value.
            if multiline:
                for _ in range(60):
                    estimate = sum(max(1, math.ceil(font.text_length(line, fontsize=size) / usable_width))
                                   for line in display_text.split("\n"))
                    if estimate * (font.ascender-font.descender) * size <= usable_height:
                        break
                    size *= 0.9
            if size < 1:
                raise ValueError("Значение слишком длинное для видимой области поля.")
            if display_text:
                self._insert_text(temp, area, display_text, size, color)
            resources_type, resources = self.doc.xref_get_key(temp.xref, "Resources")
            appearance = self.doc.get_new_xref()
            self.doc.update_object(appearance,
                                   f"<< /Type /XObject /Subtype /Form /BBox [0 0 {width} {height}] "
                                   f"/Resources {resources if resources_type != 'null' else '<< >>'} >>")
            content = b"\n".join(self.doc.xref_stream(stream) for stream in temp.get_contents())
            self.doc.update_stream(appearance, content)
        finally:
            self.doc.delete_page(temp_index)
        self.doc.xref_set_key(xref, "AP", f"<< /N {appearance} 0 R >>")
        self.doc.xref_set_key(xref, "AS", "null")

    def fill_form(self, values):
        self.require_fill()
        if self.has_xfa:
            raise ValueError("Формы XFA не поддерживаются. Исходный документ сохранён.")
        fields = {field["xref"]: field for field in self.form_fields()}
        prepared = {}
        for xref, value in values.items():
            if xref not in fields or not fields[xref]["supported"]:
                raise ValueError("Поле отсутствует, доступно только для чтения или не поддерживается.")
            field = fields[xref]
            if field["type"] == "checkbox":
                if not isinstance(value, bool):
                    raise ValueError("Для флажка передайте значение да или нет.")
            elif not isinstance(value, str):
                raise ValueError("Значение текстового поля должно быть строкой.")
            prepared[xref] = value
        if not prepared:
            return
        def operation():
            for xref, value in prepared.items():
                field = fields[xref]
                page = self.doc[field["page"]]
                widget = page.load_widget(xref)
                if field["type"] == "checkbox":
                    widget.field_value = widget.on_state() if value else "Off"
                else:
                    if widget.text_maxlen and len(value) > widget.text_maxlen:
                        raise ValueError(f"В поле {field['name']} допустимо не более {widget.text_maxlen} символов.")
                    widget.field_value = value
                widget.update()
                if field["type"] == "text":
                    self._text_field_appearance(field["page"], xref, value)
        self._transaction(operation, permission="fill")

    def move_page(self, index: int, offset: int):
        target = index + offset
        if not 0 <= index < self.page_count or not 0 <= target < self.page_count:
            raise ValueError("Страницу нельзя переместить за границы документа.")
        if target == index:
            return
        def operation():
            order = list(range(self.page_count))
            order.insert(target, order.pop(index))
            self._require().select(order)
        self._transaction(operation)

    def append_pdf(self, path: str, password: str | None = None):
        with fitz.open(path) as source:
            if not source.is_pdf:
                raise ValueError("Можно добавить только PDF.")
            if source.needs_pass and (password is None or not source.authenticate(password)):
                raise PasswordRequired("Введите правильный пароль добавляемого PDF.")
            if not (source.permissions & fitz.PDF_PERM_COPY):
                raise PermissionError("Владелец добавляемого PDF запретил копирование.")
            self._transaction(lambda: self._require().insert_pdf(source))

    def extract_pages(self, indices: list[int], path: str):
        doc = self._require()
        if not indices or any(index < 0 or index >= len(doc) for index in indices):
            raise ValueError("Выберите существующие страницы.")
        if not self._can_copy:
            raise PermissionError("Владелец PDF запретил копирование.")
        if self.path and Path(path).resolve() == Path(self.path):
            raise ValueError("Сохраните извлечённые страницы в отдельный файл.")
        with fitz.open() as output:
            for index in indices:
                output.insert_pdf(doc, from_page=index, to_page=index)
            _atomic_write(path, output.tobytes(garbage=3, deflate=True))

    def save(self, path: str):
        self._require()
        if not (self._editable or self._can_fill):
            raise PermissionError("Владелец PDF запретил изменение и заполнение документа.")
        options = {"garbage": 3, "deflate": True}
        if self._encrypted:
            options.update(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=self._password,
                           owner_pw=self._owner_password, permissions=self._permissions)
        # Compact only an independent copy; keep all live-page resource caches intact.
        with fitz.open(stream=self.to_bytes(), filetype="pdf") as output:
            _atomic_write(path, output.tobytes(**options))
        self.path = str(Path(path).resolve())
        self.dirty = False
        # Older snapshots can no longer reliably identify the disk revision after save.
        self._undo = [(data, True) for data, _ in self._undo]
        self._redo = [(data, True) for data, _ in self._redo]

    def undo(self):
        if not self._undo:
            return
        previous = self._undo.pop()
        self._redo.append((self.to_bytes(), self.dirty))
        self._load(previous[0])
        self.dirty = previous[1]

    def redo(self):
        if not self._redo:
            return
        future = self._redo.pop()
        self._undo.append((self.to_bytes(), self.dirty))
        self._load(future[0])
        self.dirty = future[1]

    def export_text(self, path: str):
        doc = self._require()
        if not self._can_copy:
            raise PermissionError("Владелец PDF запретил копирование текста.")
        text = "\n\n".join(f"Страница {page.number + 1}\n{page.get_text()}" for page in doc)
        _atomic_write(path, text.encode("utf-8"))


def ocr_pdf(data: bytes, pages: list[int], language: str = "rus+eng", dpi: int = 300,
            progress=None, cancel=None, skip_existing_text=True, deskew=False, enhance_contrast=False) -> bytes:
    """Replace requested pages with lossless page rasters plus searchable hidden OCR text.

    OCR owns its independent document. Cancellation/errors never change the caller's PDF.
    Rasterization preserves rotation and the visible page extent. An existing
    scan is rendered once; annotations and native artwork are flattened on these pages.
    """
    if not 150 <= dpi <= 600:
        raise ValueError("Разрешение OCR должно быть от 150 до 600 DPI.")
    tessdata = resource_root() / "tessdata"
    for model in language.split("+"):
        if model not in {"rus", "eng"} or not (tessdata / f"{model}.traineddata").is_file():
            raise RuntimeError(f"Не найдена локальная модель OCR: {model}.")
    with fitz.open(stream=data, filetype="pdf") as source:
        indices = list(dict.fromkeys(pages))
        if any(index < 0 or index >= len(source) for index in indices):
            raise ValueError("Выбрана несуществующая страница OCR.")

        def recognize(pix):
            if deskew or enhance_contrast:
                from scan_preprocess import preprocess_scan
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                image, _angle = preprocess_scan(image, deskew=deskew, enhance_contrast=enhance_contrast)
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                pix = fitz.Pixmap(buffer.getvalue())
                pix.set_dpi(dpi, dpi)
            return pix.pdfocr_tobytes(language=language, tessdata=str(tessdata))

        for done, index in enumerate(indices):
            if cancel and cancel():
                raise RuntimeError("Распознавание отменено.")
            page = source[index]
            if skip_existing_text and page.get_text().strip():
                if progress:
                    progress(done + 1, len(indices))
                continue
            rotation = page.rotation
            # MuPDF integrates Tesseract; no installed executable or system PATH is used.
            pix = page.get_pixmap(dpi=dpi, alpha=False, colorspace=fitz.csRGB)
            recognized = recognize(pix)
            output_rotation = 0
            original_width, original_height = page.rect.width, page.rect.height
            if rotation:
                # Honour manually corrected scan orientation first. Also try original
                # content orientation: PDF rotation may intentionally display native
                # writing sideways. Pick the reading with coherent word sequences.
                def score(pdf):
                    with fitz.open(stream=pdf, filetype="pdf") as probe:
                        words = re.findall(r"[\w]+", probe[0].get_text(), flags=re.UNICODE)
                        return sum(len(word) ** 2 for word in words if len(word) >= 2)
                page.set_rotation(0)
                try:
                    alternative = recognize(page.get_pixmap(dpi=dpi, alpha=False, colorspace=fitz.csRGB))
                    if score(alternative) > score(recognized):
                        recognized = alternative
                        output_rotation = rotation
                        original_width, original_height = page.rect.width, page.rect.height
                finally:
                    page.set_rotation(rotation)
            if cancel and cancel():
                raise RuntimeError("Распознавание отменено.")
            with fitz.open(stream=recognized, filetype="pdf") as result:
                # Some MuPDF builds emit an empty ICC profile in pdfocr output.
                # This raster was explicitly rendered in RGB, so DeviceRGB is exact
                # and avoids malformed profile warnings in readers and redaction.
                for image in result[0].get_images():
                    result.xref_set_key(image[0], "ColorSpace", "/DeviceRGB")
                # Pixel rounding can otherwise enlarge dimensions by a fraction of a point.
                result[0].set_mediabox(fitz.Rect(0, 0, original_width, original_height))
                result[0].set_rotation(output_rotation)
                source.delete_page(index)
                source.insert_pdf(result, start_at=index)
            if progress:
                progress(done + 1, len(indices))
        return source.tobytes(garbage=3, deflate=True)
