"""Explicit, local storage of user-supplied signature and stamp images."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import re
import tempfile
import uuid
from PIL import Image, ImageChops, ImageOps


def prepare_stamp(path, angle=0, opacity=1.0, remove_white=False):
    """Return a fresh RGBA image; positive angles rotate clockwise."""
    angle, opacity=float(angle),float(opacity)
    if not math.isfinite(angle) or not math.isfinite(opacity) or not 0 <= opacity <= 1:
        raise ValueError('Непрозрачность должна быть от 0 до 1, угол — конечным числом.')
    with Image.open(path) as original:
        image=ImageOps.exif_transpose(original).convert('RGBA')
    image.info.clear()
    alpha=image.getchannel('A')
    if remove_white:
        darkest=ImageChops.darker(ImageChops.darker(image.getchannel('R'),image.getchannel('G')),image.getchannel('B'))
        white_alpha=darkest.point([min(255,max(0,round((255-x)*255/40))) for x in range(256)])
        alpha=ImageChops.multiply(alpha,white_alpha)
    image.putalpha(alpha)
    if angle % 360:
        image=image.rotate(-angle,resample=Image.Resampling.BICUBIC,expand=True,fillcolor=(255,255,255,0))
    if opacity != 1:
        image.putalpha(image.getchannel('A').point([round(x*opacity) for x in range(256)]))
    return image


def prepare_stamp_file(path, angle=0, opacity=1.0, remove_white=False):
    image=prepare_stamp(path,angle,opacity,remove_white)
    fd,name=tempfile.mkstemp(prefix='pdfmaster-stamp-',suffix='.png')
    os.close(fd)
    try:
        image.save(name,format='PNG')
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
    return name


class StampLibrary:
    def __init__(self,directory=None):
        base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))
        self.directory=Path(directory) if directory is not None else base/'PDFMaster/stamps'
        self.index=self.directory/'index.json'

    def _records(self):
        if not self.index.exists():
            return []
        try:
            data=json.loads(self.index.read_text(encoding='utf-8'))
            if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('items'),list):
                raise ValueError
            records=[]
            for item in data['items']:
                if not isinstance(item,dict) or not re.fullmatch('[a-f0-9]{32}',str(item.get('id',''))):
                    raise ValueError
                if not isinstance(item.get('name'),str) or not item['name'].strip():
                    raise ValueError
                records.append({'id':item['id'],'name':item['name']})
            return records
        except (OSError,ValueError,TypeError) as exc:
            raise ValueError('Каталог подписей повреждён. Сохраните резервную копию index.json перед восстановлением.') from exc

    def _write(self,records):
        self.directory.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.index-',suffix='.tmp',dir=self.directory)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as stream:
                json.dump({'version':1,'items':records},stream,ensure_ascii=False,indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name,self.index)
        finally:
            Path(name).unlink(missing_ok=True)

    @staticmethod
    def _name(name):
        value=str(name).strip()
        if not value or len(value)>100:
            raise ValueError('Введите название от 1 до 100 символов.')
        return value

    def image_path(self,identifier):
        if not re.fullmatch('[a-f0-9]{32}',str(identifier)):
            raise ValueError('Некорректный идентификатор подписи.')
        if not any(x['id']==identifier for x in self._records()):
            raise ValueError('Подпись не найдена в библиотеке.')
        path=self.directory/(identifier+'.png')
        if path.is_symlink() or not path.is_file():
            raise ValueError('Файл подписи не найден или недоступен.')
        return str(path.resolve())

    def items(self):
        result=[]
        for record in self._records():
            path=self.directory/(record['id']+'.png')
            if path.is_file() and not path.is_symlink():
                result.append({**record,'path':str(path.resolve())})
        return result

    def add(self,path,name):
        name=self._name(name)
        records=self._records()
        image=prepare_stamp(path)
        self.directory.mkdir(parents=True,exist_ok=True)
        record={'id':uuid.uuid4().hex,'name':name}
        destination=self.directory/(record['id']+'.png')
        try:
            image.save(destination,format='PNG')
            self._write(records+[record])
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return {**record,'path':str(destination.resolve())}

    def remove(self,identifier):
        path=Path(self.image_path(identifier))
        records=self._records()
        self._write([x for x in records if x['id']!=identifier])
        try:
            path.unlink()
        except OSError:
            self._write(records)
            raise

    def rename(self,identifier,name):
        name=self._name(name)
        self.image_path(identifier)
        records=self._records()
        for record in records:
            if record['id']==identifier:
                record['name']=name
        self._write(records)
