"""Save license notices of exact MuPDF submodules used by version 1.28.2."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "licenses" / "mupdf-third-party"
OUT.mkdir(exist_ok=True)

def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "PDFMaster-license-collector/1.0"}), timeout=30) as response:
        return response.read()

def collect(item):
    if not item.get("html_url") or "/tree/" not in item["html_url"]:
        return None
    repo, commit = item["html_url"].removeprefix("https://github.com/").split("/tree/")
    tree = json.loads(fetch(f"https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1"))["tree"]
    notices = [entry["path"] for entry in tree if entry["type"] == "blob" and (
        ("/" not in entry["path"] and re.search(r"(COPYING|COPYRIGHT|LICENSE|LICENCE|NOTICE)", entry["path"], re.I))
        or entry["path"] in ("docs/FTL.TXT", "docs/GPLv2.TXT", "README.ijg", "README", "README.md")
    )]
    dest = OUT / item["name"]
    dest.mkdir(exist_ok=True)
    for path in notices:
        (dest / path.replace("/", "__")).write_bytes(fetch(f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"))
    return {"name": item["name"], "source": item["html_url"], "notices": notices}

items = json.loads(fetch("https://api.github.com/repos/ArtifexSoftware/mupdf/contents/thirdparty?ref=1.28.2"))
with ThreadPoolExecutor(max_workers=4) as pool:
    result = [x for x in pool.map(collect, items) if x]
(OUT / "sources.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Collected notices from {len(result)} exact MuPDF submodule commits.")
