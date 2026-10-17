"""Real OCR worker -> interactive edit -> stamp -> saved PDF, without a mock OCR."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import time
import io
import pymupdf as fitz
from PIL import Image
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from scripts.qa_fixtures import make_fixtures
from ui import MainWindow


def test_real_ocr_worker_edit_stamp_and_reopen(tmp_path):
    app=QApplication.instance() or QApplication([])
    qa=make_fixtures()
    window=MainWindow()
    window.show()
    failures=[]
    window._error=lambda title,exc: failures.append((title,str(exc)))
    try:
        window.open_file(str(qa/'scan.pdf'))
        assert not window.engine.doc[0].get_text().strip()
        window.run_ocr([0],language='rus+eng',dpi=300)
        deadline=time.monotonic()+60
        while window.worker is not None and time.monotonic()<deadline:
            QTest.qWait(30)
        assert window.worker is None, 'OCR did not finish'
        assert not failures, failures
        assert '12500' in window.engine.doc[0].get_text()
        window.set_mode('edit')
        window.scale=0.85
        window.render_current()
        line=next(x for x in window.lines if '12500' in x['text'])
        rect=fitz.Rect(line['rect']) * window.engine.doc[0].rotation_matrix
        pos=window.view.mapFromScene(QPointF((rect.x0+rect.x1)/2*window.scale,(rect.y0+rect.y1)/2*window.scale))
        QTest.mouseClick(window.view.viewport(),Qt.MouseButton.LeftButton,pos=pos)
        assert '12500' in window.text_edit.toPlainText()
        window.text_edit.setPlainText('Стоимость: 14700 рублей.')
        window.apply_text()
        assert not failures, failures
        window.load_stamp(str(qa/'stamp.png'))
        window.stamp_width.setValue(42)
        window.remove_white.setChecked(True)
        point=window.view.mapFromScene(QPointF(430*window.scale,680*window.scale))
        window.view.ensureVisible(420*window.scale,660*window.scale,40,40)
        app.processEvents()
        point=window.view.mapFromScene(QPointF(430*window.scale,680*window.scale))
        QTest.mouseClick(window.view.viewport(),Qt.MouseButton.LeftButton,pos=point)
        assert not failures, failures
        target=tmp_path/'result.pdf'
        window.save_to(str(target))
        with fitz.open(target) as result:
            assert '14700' in result[0].get_text()
            assert '12500' not in result[0].get_text()
            pix=result[0].get_pixmap(dpi=72)
            image=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
            blue=sum(1 for r,g,b in image.get_flattened_data() if b>r+40 and b>g+20)
            assert blue>100, 'Saved stamp must actually render'
    finally:
        window.engine.dirty=False
        window.close()
        app.processEvents()
