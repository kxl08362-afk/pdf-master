from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from scan_preprocess import estimate_skew,preprocess_scan

def page():
    im=Image.new('RGB',(900,1200),'white')
    font=ImageFont.truetype(str(Path(__file__).resolve().parents[1]/'resources/fonts/DejaVuSans.ttf'),25)
    draw=ImageDraw.Draw(im)
    for i in range(15):
        draw.text((90,130+i*50),'Договор номер 12345. Пример строки текста.',font=font,fill='black')
    return im

def test_deskew_small_angle_without_size_change():
    original=page()
    tilted=original.rotate(3,resample=Image.Resampling.BICUBIC,fillcolor='white')
    angle=estimate_skew(tilted)
    assert abs(angle+3)<0.5
    fixed,correction=preprocess_scan(tilted,deskew=True)
    assert fixed.size==original.size and abs(correction+3)<0.5
    assert abs(estimate_skew(fixed))<0.4

def test_blank_and_straight_pages_are_not_rotated():
    assert estimate_skew(Image.new('RGB',(900,1200),'white'))==0
    assert abs(estimate_skew(page()))<0.4

def test_contrast_is_explicit_and_preserves_dimensions():
    source=Image.new('RGB',(100,100),(190,190,190))
    ImageDraw.Draw(source).rectangle((20,20,70,70),fill=(100,100,100))
    untouched,angle=preprocess_scan(source)
    improved,_=preprocess_scan(source,enhance_contrast=True)
    assert untouched.tobytes()==source.tobytes() and angle==0
    assert improved.size==source.size and improved.getpixel((0,0))[0]>190
