from PIL import Image,ImageDraw
import pytest
from stamp_library import StampLibrary,prepare_stamp,prepare_stamp_file
from pathlib import Path

def sample(tmp_path):
    p=tmp_path/'my.png'
    im=Image.new('RGBA',(100,40),'white')
    ImageDraw.Draw(im).rectangle((10,10,80,30),fill=(0,0,180,255))
    im.save(p)
    return p

def test_library_persists_and_removes_own_copy(tmp_path):
    source=sample(tmp_path)
    library=StampLibrary(tmp_path/'library')
    added=library.add(source,'Моя печать')
    restored=StampLibrary(tmp_path/'library')
    assert restored.items()[0]['name']=='Моя печать'
    assert Path(restored.image_path(added['id'])).exists()
    restored.rename(added['id'],'Другая')
    assert restored.items()[0]['name']=='Другая'
    restored.remove(added['id'])
    assert not restored.items()
    assert source.exists()

def test_rotation_alpha_and_white_removal(tmp_path):
    p=sample(tmp_path)
    out=prepare_stamp(p,angle=90,opacity=.5,remove_white=True)
    assert out.size==(40,100)
    assert out.getpixel((0,0))[3]==0
    assert out.getchannel('A').getextrema()[1]==128
    angled=prepare_stamp(p,angle=23,opacity=.6,remove_white=True)
    assert angled.getchannel('A').getextrema()[1]<=153
    with Image.open(p) as original:
        assert original.size==(100,40) and original.getpixel((0,0))[3]==255
    temp=prepare_stamp_file(p,angle=90)
    try:
        assert Image.open(temp).size==(40,100)
    finally:
        Path(temp).unlink()

def test_library_rejects_paths_in_identifiers_and_bad_names(tmp_path):
    library=StampLibrary(tmp_path/'lib')
    with pytest.raises(ValueError):library.image_path('../outside')
    with pytest.raises(ValueError):library.add(sample(tmp_path),' ')
    with pytest.raises(ValueError):prepare_stamp(sample(tmp_path),opacity=5)
