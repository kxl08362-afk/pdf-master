"""Collect installed conversion-library notices plus exact source archive URLs."""
from importlib.metadata import distribution
from pathlib import Path
from urllib.request import urlopen
import json
import shutil
import pikepdf
import lxml.etree

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "licenses" / "conversion-libraries"
out.mkdir(exist_ok=True)
provenance = {}
for name in ("img2pdf", "pikepdf", "lxml", "packaging"):
    package = distribution(name)
    for relative in package.files:
        normalized = str(relative).replace("\\", "/")
        if ".dist-info/licenses/" in normalized:
            dest = out / name / normalized.split(".dist-info/licenses/", 1)[1]
            dest.parent.mkdir(exist_ok=True, parents=True)
            shutil.copyfile(package.locate_file(relative), dest)
    with urlopen(f"https://pypi.org/pypi/{name}/{package.version}/json", timeout=30) as response:
        info = json.load(response)
    provenance[name] = {
        "version": package.version,
        "source_archives": [{"url": item["url"], "sha256": item["digests"]["sha256"]}
                            for item in info["urls"] if item["packagetype"] == "sdist"],
        "project_urls": info["info"].get("project_urls"),
    }
provenance["native_qpdf"] = {"version": pikepdf.__libqpdf_version__,
    "source": f"https://github.com/qpdf/qpdf/tree/v{pikepdf.__libqpdf_version__}"}
provenance["native_libxml2"] = {"version": ".".join(map(str, lxml.etree.LIBXML_VERSION)),
    "source": "https://gitlab.gnome.org/GNOME/libxml2/-/tree/v" + ".".join(map(str, lxml.etree.LIBXML_VERSION))}
provenance["native_libxslt"] = {"version": ".".join(map(str, lxml.etree.LIBXSLT_VERSION)),
    "source": "https://gitlab.gnome.org/GNOME/libxslt/-/tree/v" + ".".join(map(str, lxml.etree.LIBXSLT_VERSION))}
(out / "corresponding-sources.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
print("Collected exact notices and source archive checksums for conversion dependencies.")
