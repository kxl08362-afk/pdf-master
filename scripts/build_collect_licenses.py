"""Refresh dependency notices; only used by release maintainers, with internet access."""
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import distribution
from pathlib import Path
from html.parser import HTMLParser
from urllib.request import Request, urlopen
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "licenses"
OUT.mkdir(exist_ok=True)

def fetch(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": "PDFMaster-license-collector/1.0"}), timeout=40) as response:
        return response.read()

for package, relative, target in [
    ("PyMuPDF", "COPYING", "PyMuPDF-COPYING.txt"),
    ("Pillow", "licenses/LICENSE", "Pillow-LICENSE.txt"),
    ("PyInstaller", "licenses/COPYING.txt", "PyInstaller-COPYING.txt"),
]:
    dist = distribution(package)
    match = next(p for p in dist.files if str(p).replace("\\", "/").endswith(".dist-info/" + relative))
    shutil.copyfile(dist.locate_file(match), OUT / target)
shutil.copyfile(Path(sys.base_prefix) / "LICENSE.txt", OUT / "Python-LICENSE.txt")
shutil.copyfile(ROOT / "installer/tools/InnoSetup/License.txt", OUT / "InnoSetup-LICENSE.txt")

for name, url in {
    "LICENSE.txt": "https://raw.githubusercontent.com/spdx/license-list-data/main/text/AGPL-3.0-only.txt",
    "licenses/LGPL-3.0.txt": "https://raw.githubusercontent.com/spdx/license-list-data/main/text/LGPL-3.0-only.txt",
    "licenses/GPL-3.0.txt": "https://raw.githubusercontent.com/spdx/license-list-data/main/text/GPL-3.0-only.txt",
    "licenses/Qt-GPL-exception-1.0.txt": "https://raw.githubusercontent.com/qt/qtbase/v6.12.0/LICENSES/Qt-GPL-exception-1.0.txt",
}.items():
    (ROOT / name).write_bytes(fetch(url))

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()
    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href", "")
        if tag == "a" and href.startswith(("qtcore-", "qtgui-", "qtwidgets-", "qtnetwork-", "qtimageformats-", "qtsvg-")):
            self.links.add(href)

base = "https://doc.qt.io/qt-6/"
page = fetch(base + "licenses-used-in-qt.html")
qtout = OUT / "qt-third-party"
qtout.mkdir(exist_ok=True)
(qtout / "index.html").write_bytes(page)
parser = Links()
parser.feed(page.decode())

def download_notice(link):
    safe = link.split("#", 1)[0]
    if not safe:
        return
    (qtout / safe).write_bytes(fetch(base + safe))
    return safe

with ThreadPoolExecutor(max_workers=5) as pool:
    result = list(pool.map(download_notice, sorted(parser.links)))
(OUT / "Qt-THIRD-PARTY-NOTICE.md").write_text(
    "# Qt third-party notices\n\nQt 6.12.0; official Qt license notices for Core, GUI, Widgets, Network, SVG and Image Formats are saved under qt-third-party/.\n\n"
    "Source index: https://doc.qt.io/qt-6/licenses-used-in-qt.html\n\n"
    + "\n".join(f"- {base}{x}" for x in result if x) + "\n", encoding="utf-8")
print(f"Collected runtime licenses and {len(result)} Qt third-party notices.")
