"""Package already-verified release files; no publishing or installation."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import zipfile
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.prepare_repository import collect_files
OUTPUT=ROOT/'dist/release'
VERSION='0.3.0'

def build_release(output=OUTPUT):
    OUTPUT=Path(output).resolve()
    OUTPUT.mkdir(exist_ok=True, parents=True)
    installer=ROOT/f'dist/installers/PDFMaster-Setup-{VERSION}.exe'
    if not installer.exists():
        raise FileNotFoundError(installer)
    shutil.copy2(installer,OUTPUT/installer.name)
    manual=f'PDFMaster-{VERSION}-Инструкция.txt'
    source_archive=f'PDFMaster-{VERSION}-Исходники.zip'
    shutil.copy2(ROOT/'README.md',OUTPUT/manual)
    # Use the same reviewed public allowlist as repository preparation.
    # Private application/contact data, machine QA and agent history never ship.
    files=collect_files(ROOT)
    with zipfile.ZipFile(OUTPUT/source_archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(set(files)):
            archive.write(path,'PDFMaster/'+path.relative_to(ROOT).as_posix())
        if (ROOT/'dist/build-manifest.json').is_file():
            archive.write(ROOT/'dist/build-manifest.json','PDFMaster/build-manifest.json')
    extra=[]
    for original,suffix in [('BUILD_VERIFICATION.md','Проверки.txt'),('SOURCES.md','Источники.txt')]:
        if (ROOT/original).is_file():
            name=f'PDFMaster-{VERSION}-{suffix}'
            shutil.copy2(ROOT/original,OUTPUT/name)
            extra.append(name)
    manifest={'version':VERSION,'platform':'Windows 11 x64','created_utc':datetime.now(timezone.utc).isoformat(),
              'files':{}}
    for name in [installer.name,manual,source_archive,*extra]:
        path=OUTPUT/name
        manifest['files'][name]={'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    (OUTPUT/f'PDFMaster-{VERSION}-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    build_release(parser.parse_args().output)
