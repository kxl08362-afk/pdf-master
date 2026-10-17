"""Offline acceptance check, including the frozen distribution's OCR resources."""
from pathlib import Path
import json
import sys
import time
import traceback


def run_self_test(output):
    report_path = Path(output).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    evidence = report_path.parent / (report_path.stem + '-files')
    evidence.mkdir(exist_ok=True)
    report = {'ok': False, 'frozen': bool(getattr(sys, 'frozen', False)), 'checks': [], 'evidence': str(evidence)}
    started = time.monotonic()
    try:
        import pymupdf as fitz
        from PIL import Image, ImageDraw
        from engine import PdfEngine
        resources = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'resources'
        font = resources / 'fonts/DejaVuSans.ttf'
        assert font.exists(), 'Нет поставляемого шрифта'
        assert all((resources / 'tessdata' / (lang+'.traineddata')).exists() for lang in ('rus','eng'))
        report['checks'].append('Встроенные шрифт и модели rus+eng')
        native = fitz.open()
        page = native.new_page(width=595, height=842)
        page.insert_font(fontname='DV',fontfile=str(font))
        page.insert_text((45,80),'ПРОВЕРКА РАСПОЗНАВАНИЯ',fontname='DV',fontsize=18)
        page.insert_text((45,140),'Стоимость: 12500 рублей.',fontname='DV',fontsize=14)
        page.insert_text((45,185),'Russian and English recognition.',fontname='DV',fontsize=14)
        native_path=evidence/'native.pdf'
        native.save(str(native_path))
        scan = fitz.open()
        raster=scan.new_page(width=595,height=842)
        raster.insert_image(raster.rect, stream=page.get_pixmap(dpi=160).tobytes('png'))
        scan_path=evidence/'scan.pdf'
        scan.save(str(scan_path))
        scan.close()
        native.close()
        engine = PdfEngine()
        engine.open(str(native_path))
        line=next(x for x in engine.text_lines(0) if '12500' in x['text'])
        engine.replace_text(0,line['rect'],'Стоимость: 14700 рублей.',size=line['size'])
        assert '14700' in engine.doc[0].get_text() and '12500' not in engine.doc[0].get_text()
        engine.undo()
        assert '12500' in engine.doc[0].get_text()
        engine.redo()
        assert '14700' in engine.doc[0].get_text()
        report['checks'].append('Кириллица: замена, удаление исходного текста, Undo/Redo')
        engine.save(str(evidence/'edited-native.pdf'))
        from engine import ocr_pdf
        data=ocr_pdf(scan_path.read_bytes(),[0],language='rus+eng',dpi=300)
        engine.open(str(scan_path))
        engine.replace_document(data)
        ocr_text=engine.doc[0].get_text()
        assert '12500' in ocr_text, 'OCR не распознал контрольное число'
        assert 'руб' in ocr_text.lower(), 'OCR не распознал кириллицу'
        assert engine.search('12500'), 'Поиск не находит распознанный текст'
        report['ocr_text']=ocr_text
        report['checks'].append('OCR растрового PDF, русский и английский, поиск')
        line=next(x for x in engine.text_lines(0) if '12500' in x['text'])
        engine.replace_text(0,line['rect'],'Стоимость: 14700 рублей.',size=line['size'])
        assert '14700' in engine.doc[0].get_text() and '12500' not in engine.doc[0].get_text()
        stamp=Image.new('RGBA',(350,110),(255,255,255,255))
        drawing=ImageDraw.Draw(stamp)
        drawing.ellipse((5,5,345,105),outline=(20,70,180,255),width=5)
        drawing.text((110,45),'TEST SAMPLE',fill=(20,70,180,255))
        stamp_path=evidence/'stamp.png'
        stamp.save(stamp_path)
        engine.insert_image(0,str(stamp_path),(350,600,500,650),remove_white=True)
        result=evidence/'edited-scan-with-stamp.pdf'
        engine.save(str(result))
        with fitz.open(str(result)) as saved:
            assert saved.page_count==1
            assert '14700' in saved[0].get_text()
            assert '12500' not in saved[0].get_text()
            assert saved[0].get_images()
            pix=saved[0].get_pixmap(dpi=100)
            rendered=Image.open(__import__('io').BytesIO(pix.tobytes('png'))).convert('RGB')
            assert sum(1 for r,g,b in rendered.get_flattened_data() if b>r+40 and b>g+20)>100
            pix.save(str(evidence/'result.png'))
        report['checks'].append('Редактирование OCR и прозрачная печать; повторное открытие PDF')
        _advanced_checks(evidence,report)
        report['ok']=True
    except Exception:
        report['error']=traceback.format_exc()
    report['elapsed_seconds']=round(time.monotonic()-started,2)
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['ok'] else 1


def _advanced_checks(evidence,report):
    import io
    import pymupdf as fitz
    from PIL import Image,ImageDraw,ImageFont
    from engine import PdfEngine,resource_root,ocr_pdf
    from pdf_tools import images_to_pdf,optimize_pdf,export_page_images
    from stamp_library import StampLibrary,prepare_stamp_file
    from scan_preprocess import preprocess_scan
    photo=evidence/'photo.jpg'
    image=Image.new('RGB',(420,260),'white')
    ImageDraw.Draw(image).rectangle((30,30,220,140),fill=(20,60,180))
    image.save(photo,quality=90)
    converted=images_to_pdf([str(photo),str(photo)])
    with fitz.open(stream=converted,filetype='pdf') as document:
        assert len(document)==2
        xref=document[0].get_images()[0][0]
        assert document.extract_image(xref)['image']==photo.read_bytes(),'JPEG был перекодирован'
    (evidence/'from-images.pdf').write_bytes(converted)
    optimized,stats=optimize_pdf(converted)
    assert len(optimized)<=len(converted)
    files=export_page_images(optimized,[1,0],str(evidence/'page-images'),fmt='png',dpi=72,overwrite=True)
    assert len(files)==2 and all(Path(p).is_file() for p in files)
    report['checks'].append('img2pdf: JPEG без перекодирования; pikepdf: оптимизация; PNG-экспорт')
    report['optimization']=stats

    forms=evidence/'form.pdf'
    with fitz.open(str(evidence/'native.pdf')) as document:
        field=fitz.Widget()
        field.field_name='client'
        field.field_type=fitz.PDF_WIDGET_TYPE_TEXT
        field.rect=fitz.Rect(45,300,400,340)
        document[0].add_widget(field)
        check=fitz.Widget()
        check.field_name='approved'
        check.field_type=fitz.PDF_WIDGET_TYPE_CHECKBOX
        check.rect=fitz.Rect(45,370,65,390)
        document[0].add_widget(check)
        document.save(forms)
    engine=PdfEngine()
    engine.open(str(forms))
    fields=engine.form_fields()
    engine.fill_form({f['xref']:('Иван Петров' if f['name']=='client' else True) for f in fields})
    form_output=evidence/'filled-form.pdf'
    engine.save(str(form_output))
    with fitz.open(form_output) as document:
        values={w.field_name:w.field_value for w in document[0].widgets()}
        assert values['client']=='Иван Петров' and values['approved'] not in ('Off',False,None,'')
        document[0].get_pixmap(dpi=120).save(str(evidence/'filled-form.png'))
    safe=ocr_pdf(engine.to_bytes(),[0],skip_existing_text=True)
    with fitz.open(stream=safe,filetype='pdf') as document:
        assert len(list(document[0].widgets()))==2
    report['checks'].append('AcroForm: кириллица и флажок; OCR пропускает готовый текст и сохраняет поля')

    engine.duplicate_pages([0])
    assert engine.page_count==2
    engine.rotate_pages([0,1],90)
    engine.undo()
    engine.crop_page(0,(5,7,5,7))
    engine.undo()
    engine.reorder_pages([1,0])
    engine.undo()
    engine.undo()
    assert engine.page_count==1
    textline=next(line for line in engine.text_lines(0) if '12500' in line['text'])
    engine.redact_area(0,textline['rect'])
    redacted=evidence/'redacted.pdf'
    engine.save(str(redacted))
    with fitz.open(redacted) as document:
        assert '12500' not in document[0].get_text()
    report['checks'].append('Пакетные страницы, дублирование, crop и отмена; реальное удаление текста')

    library=StampLibrary(evidence/'stamp-library')
    item=library.add(str(evidence/'stamp.png'),'Тестовая печать')
    restored=StampLibrary(evidence/'stamp-library')
    assert any(x['id']==item['id'] for x in restored.items())
    prepared=prepare_stamp_file(restored.image_path(item['id']),angle=20,opacity=.6,remove_white=True)
    try:
        with Image.open(prepared) as stamp:
            assert stamp.mode=='RGBA' and stamp.getchannel('A').getextrema()[1]<=153
    finally:
        Path(prepared).unlink(missing_ok=True)
    restored.remove(item['id'])
    report['checks'].append('Локальная библиотека печатей, перезагрузка, поворот и непрозрачность')

    font=ImageFont.truetype(str(resource_root()/'fonts/DejaVuSans.ttf'),26)
    scan=Image.new('RGB',(900,1200),'white')
    drawing=ImageDraw.Draw(scan)
    for row in range(10):
        drawing.text((70,100+row*65),'Договор номер 67890. Тест распознавания.',font=font,fill='black')
    tilted=scan.rotate(3,resample=Image.Resampling.BICUBIC,fillcolor='white')
    corrected,angle=preprocess_scan(tilted,deskew=True,enhance_contrast=True)
    assert abs(angle+3)<.6 and corrected.size==tilted.size
    buffer=io.BytesIO()
    tilted.save(buffer,format='PNG')
    with fitz.open() as document:
        page=document.new_page(width=450,height=600)
        page.insert_image(page.rect,stream=buffer.getvalue())
        raster=document.tobytes()
    recognized=ocr_pdf(raster,[0],dpi=200,deskew=True,enhance_contrast=True)
    with fitz.open(stream=recognized,filetype='pdf') as document:
        assert '67890' in document[0].get_text()
    report['checks'].append('Наклонённый скан: выравнивание, контраст и настоящий OCR')
