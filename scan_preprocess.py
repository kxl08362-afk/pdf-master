"""Small-angle deskew and optional tonal correction, implemented with Pillow.

This is an independent projection-profile implementation, not OCRmyPDF's
Tesseract deskew or unpaper noise/background removal.
"""
from __future__ import annotations
from PIL import Image, ImageOps


def _projection_score(binary):
    data=binary.tobytes()
    width,height=binary.size
    rows=[sum(data[y*width:(y+1)*width]) for y in range(height)]
    ink=sum(rows)
    return sum((a-b)**2 for a,b in zip(rows,rows[1:])) / max(ink,1)


def estimate_skew(image,max_angle=5.0):
    if not 0 < max_angle <= 7:
        raise ValueError('Диапазон выравнивания должен быть от 0 до 7 градусов.')
    gray=ImageOps.grayscale(image)
    gray.thumbnail((1000,1000),Image.Resampling.LANCZOS)
    if min(gray.size)<60:
        return 0.0
    # Exclude scanner borders and use ink, rather than a bright paper margin.
    margin=max(3,round(min(gray.size)*0.035))
    gray=gray.crop((margin,margin,gray.width-margin,gray.height-margin))
    binary=gray.point(lambda x:255 if x<170 else 0)
    ink=sum(binary.tobytes())/255
    if ink < binary.width*binary.height*0.0015 or ink>binary.width*binary.height*0.45:
        return 0.0
    baseline=_projection_score(binary)
    def score(angle):
        return _projection_score(binary.rotate(angle,resample=Image.Resampling.BILINEAR,
                                                expand=False,fillcolor=0))
    coarse=[i/2 for i in range(-int(max_angle*2),int(max_angle*2)+1)]
    scored=[(score(angle),angle) for angle in coarse]
    best_score,best_angle=max(scored)
    if best_score <= baseline*1.12 or abs(best_angle)<0.35:
        return 0.0
    fine=[round(best_angle+i/10,2) for i in range(-5,6) if abs(best_angle+i/10)<=max_angle]
    best_score,best_angle=max((score(angle),angle) for angle in fine)
    return round(best_angle,2) if best_score>baseline*1.12 else 0.0


def preprocess_scan(image,deskew=False,enhance_contrast=False):
    result=image.convert('RGB')
    if enhance_contrast:
        result=ImageOps.autocontrast(result,cutoff=0.5,preserve_tone=True)
    angle=estimate_skew(result) if deskew else 0.0
    if abs(angle)>=0.1:
        result=result.rotate(angle,resample=Image.Resampling.BICUBIC,expand=False,fillcolor=(255,255,255))
    return result,angle
