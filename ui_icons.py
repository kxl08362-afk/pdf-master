"""Small authored line icons; no platform emoji, font glyph or remote assets."""
from functools import lru_cache
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


@lru_cache(maxsize=96)
def icon(name, color="#454B56", size=20):
    result = QIcon()
    for mode, paint in [(QIcon.Mode.Normal, color), (QIcon.Mode.Disabled, "#A8AFBA"), (QIcon.Mode.Active, color)]:
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size * 2 / 24, size * 2 / 24)
        painter.setPen(QPen(QColor(paint), 1.65, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        _draw(painter, name)
        painter.end()
        pixmap.setDevicePixelRatio(2)
        result.addPixmap(pixmap, mode)
    return result


def _draw(p, name):
    def path(points):
        line = QPainterPath(QPointF(*points[0]))
        for point in points[1:]:
            line.lineTo(*point)
        p.drawPath(line)
    def line(a, b):
        p.drawLine(QPointF(*a), QPointF(*b))
    def rect(x, y, w, h, r=1.5):
        p.drawRoundedRect(QRectF(x, y, w, h), r, r)
    if name in ("document", "view", "form", "text"):
        path([(6, 3), (15, 3), (19, 7), (19, 21), (5, 21), (5, 3), (6, 3)])
        path([(14, 3), (14, 8), (19, 8)])
        if name == "form":
            rect(8, 11, 3, 3, .5); line((13, 12.5), (16, 12.5)); line((8, 17), (16, 17))
        elif name == "text":
            line((8, 12), (16, 12)); line((12, 12), (12, 18)); line((10, 18), (14, 18))
        else:
            line((8, 12), (16, 12)); line((8, 16), (14, 16))
    elif name == "open":
        path([(3, 19), (3, 6), (9, 6), (11, 8), (20, 8), (20, 11)])
        path([(3, 19), (6, 11), (22, 11), (19, 19), (3, 19)])
    elif name == "save":
        path([(4, 3), (18, 3), (21, 6), (21, 21), (3, 21), (3, 3), (4, 3)])
        rect(7, 3, 9, 6, .5); rect(7, 14, 10, 7, .5); line((14, 5), (14, 7))
    elif name in ("undo", "redo"):
        if name == "redo":
            p.translate(24, 0); p.scale(-1, 1)
        path([(7, 4), (3, 8), (7, 12)])
        p.drawArc(QRectF(4, 8, 16, 11), 0, 180 * 16)
        line((4, 8), (13, 8)); line((20, 13), (20, 17))
    elif name == "edit":
        path([(5, 15), (15, 5), (19, 9), (9, 19), (4, 20), (5, 15)])
        line((13, 7), (17, 11)); line((5, 15), (9, 19))
    elif name == "stamp":
        path([(6, 15), (9, 12), (9, 7), (10, 4), (14, 4), (15, 7), (15, 12), (18, 15)])
        rect(4, 15, 16, 4, 1); line((6, 22), (18, 22))
    elif name == "ocr":
        for points in [[(3, 8), (3, 3), (8, 3)], [(16, 3), (21, 3), (21, 8)], [(21, 16), (21, 21), (16, 21)], [(8, 21), (3, 21), (3, 16)]]:
            path(points)
        line((8, 8), (16, 8)); line((8, 12), (16, 12)); line((8, 16), (13, 16))
    elif name == "commands":
        for x, y in [(4, 4), (14, 4), (4, 14), (14, 14)]:
            rect(x, y, 6, 6, 1.5)
    elif name == "search":
        p.drawEllipse(QRectF(3, 3, 13, 13)); line((14, 14), (21, 21))
    elif name in ("plus", "minus"):
        line((5, 12), (19, 12))
        if name == "plus": line((12, 5), (12, 19))
    elif name == "fit":
        rect(3, 5, 18, 14, 1); line((3, 12), (8, 12)); path([(6, 9), (9, 12), (6, 15)])
        line((16, 12), (21, 12)); path([(18, 9), (15, 12), (18, 15)])
    elif name == "rotate":
        p.drawArc(QRectF(4, 4, 15, 15), 40 * 16, 285 * 16)
        path([(20, 4), (20, 10), (14, 10)])
    elif name == "delete":
        line((4, 6), (20, 6)); path([(9, 6), (9, 3), (15, 3), (15, 6)])
        path([(6, 6), (7, 21), (17, 21), (18, 6)]); line((10, 10), (10, 17)); line((14, 10), (14, 17))
    elif name == "duplicate":
        rect(8, 8, 12, 13, 1); path([(15, 5), (15, 3), (3, 3), (3, 16), (5, 16)])
    elif name == "crop":
        path([(7, 2), (7, 17), (22, 17)]); path([(2, 7), (17, 7), (17, 22)])
    elif name == "redact":
        rect(3, 5, 18, 14, 1); p.fillRect(QRectF(6, 9, 12, 6), p.pen().color())
    elif name in ("images", "export"):
        rect(3, 4, 18, 16, 1); p.drawEllipse(QRectF(6, 7, 4, 4)); path([(4, 18), (10, 12), (14, 16), (17, 12), (20, 15)])
        if name == "export": path([(13, 3), (21, 3), (21, 11)]); line((21, 3), (13, 11))
    elif name == "optimize":
        path([(3, 8), (8, 8), (8, 3)]); line((3, 3), (8, 8))
        path([(21, 8), (16, 8), (16, 3)]); line((21, 3), (16, 8))
        path([(3, 16), (8, 16), (8, 21)]); line((3, 21), (8, 16))
        path([(21, 16), (16, 16), (16, 21)]); line((21, 21), (16, 16))
    elif name in ("up", "down"):
        if name == "down": p.translate(24, 24); p.rotate(180)
        line((12, 20), (12, 4)); path([(5, 11), (12, 4), (19, 11)])
    elif name == "chevron":
        path([(9, 5), (16, 12), (9, 19)])
    elif name == "extract":
        rect(3, 4, 12, 16, 1); line((10, 12), (22, 12)); path([(18, 8), (22, 12), (18, 16)])
    elif name == "merge":
        rect(3, 3, 10, 14, 1); rect(11, 7, 10, 14, 1); line((14, 14), (18, 14)); line((16, 12), (16, 16))
    elif name == "shield":
        path([(12, 2), (20, 5), (19, 14), (16, 19), (12, 22), (8, 19), (5, 14), (4, 5), (12, 2)])
        path([(8, 12), (11, 15), (16, 9)])
    else:
        p.drawEllipse(QRectF(4, 4, 16, 16)); line((12, 8), (12, 13)); p.drawPoint(QPointF(12, 17))
