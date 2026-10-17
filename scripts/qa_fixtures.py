"""Synthetic, non-personal PDF/image fixtures for application acceptance checks."""
from pathlib import Path
import io
import pymupdf as fitz
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa'

def make_fixtures():
    QA.mkdir(exist_ok=True)
    font = ROOT / 'resources/fonts/DejaVuSans.ttf'
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname='DV', fontfile=str(font))
    def line(x, y, text, size=12, color=(0.12, 0.16, 0.18)):
        page.insert_text((x,y),text,fontname='DV',fontsize=size,color=color)
    page.draw_rect(fitz.Rect(42,40,49,104), color=None,fill=(0.08,0.45,0.35))
    line(65,66,'ДОКУМЕНТ ДЛЯ ПРОВЕРКИ',18)
    line(65,91,'PDF Мастер / тестовый образец',10)
    page.draw_line((42,125),(553,125),color=(0.7,0.75,0.73),width=0.6)
    line(42,165,'Договор № 102 от 17 октября 2026 года',14)
    line(42,205,'Заказчик: ООО Пример',12)
    line(42,235,'Предмет: подготовка образца документа.',12)
    line(42,265,'Стоимость: 12500 рублей.',12)
    line(42,305,'Russian and English text recognition.',12)
    line(42,345,'Документ создан для тестирования программы.',11)
    line(42,365,'Все названия и сведения условные.',11)
    page.draw_rect(fitz.Rect(42,400,553,500),color=(0.6,0.65,0.63),width=0.6)
    for y in (434,467):
        page.draw_line((42,y),(553,y),color=(0.6,0.65,0.63),width=0.6)
    page.draw_line((410,400),(410,500),color=(0.6,0.65,0.63),width=0.6)
    line(54,422,'Наименование',11)
    line(425,422,'Количество',11)
    line(54,455,'Пример позиции',11)
    line(437,455,'12',11)
    line(54,488,'Тестовая строка',11)
    line(437,488,'25',11)
    line(42,680,'Подпись: __________________',12)
    line(345,680,'Место для печати',11)
    line(42,785,'Тестовый образец. Не является реальным договором.',9)
    doc.save(QA/'native.pdf')
    scan = fitz.open()
    target=scan.new_page(width=595,height=842)
    target.insert_image(target.rect,stream=page.get_pixmap(dpi=180).tobytes('png'))
    scan.save(QA/'scan.pdf')
    scan.close()
    p2=doc.new_page(width=595,height=842)
    p2.insert_font(fontname='DV',fontfile=str(font))
    p2.insert_text((42,80),'Вторая страница для проверки объединения.',fontname='DV',fontsize=12)
    doc.save(QA/'two-pages.pdf')
    doc.close()
    stamp=Image.new('RGBA',(500,190),(255,255,255,255))
    draw=ImageDraw.Draw(stamp)
    draw.ellipse((8,8,491,181),outline=(24,70,180,255),width=6)
    draw.text((145,80),'TEST SAMPLE',fill=(24,70,180,255),stroke_width=1)
    stamp.save(QA/'stamp.png')
    return QA

if __name__=='__main__':
    print(make_fixtures())
