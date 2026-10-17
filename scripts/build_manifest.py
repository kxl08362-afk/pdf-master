"""Prove frozen Python code equals current source and record release inputs."""
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
import hashlib
import json
import marshal
import os
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
if list((ROOT / "dist/PDFMaster").rglob("icuuc.dll")):
    raise SystemExit("Unexpected bundled icuuc.dll: Qt requires Windows 11 system ICU")
archive = CArchiveReader(str(ROOT / "dist/PDFMaster/PDFMaster.exe"))
pyz = ZlibArchiveReader(str(ROOT / "build/PDFMaster/PYZ-00.pyz"))
matches = {}
for name in ("app", "engine", "ui", "diagnostics", "pdf_tools", "stamp_library", "scan_preprocess",
             "command_menu", "ui_theme", "ui_icons"):
    frozen = marshal.loads(archive.extract(name)) if name == "app" else pyz.extract(name)
    source = compile((ROOT / f"{name}.py").read_bytes(), frozen.co_filename, "exec", optimize=0)
    matches[name] = frozen == source
if not all(matches.values()):
    raise SystemExit(f"Source / frozen bytecode mismatch: {matches}; rebuild before release")

def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

inputs = [*ROOT.glob("*.py"), *(p for p in ROOT.glob("*.md") if p.name != "VERIFICATION.md"), ROOT / "LICENSE.txt", ROOT / "requirements.txt", ROOT / "build.ps1", ROOT / "PDFMaster.spec"]
inputs += [p for folder in ("resources", "licenses", "scripts") for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
inputs += [ROOT / "installer/PDFMaster.iss", ROOT / "installer/version.txt", ROOT / "installer/BUILD.md"]
inputs += list((ROOT / "installer/hooks").glob("*.py"))
installer = ROOT / "dist/installers/PDFMaster-Setup-0.3.0.exe"
manifest = {
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "python": sys.version,
    "platform": platform.platform(),
    "dependencies": {name: version(name) for name in ("PySide6-Essentials", "shiboken6", "PyMuPDF", "Pillow", "img2pdf", "pikepdf", "lxml", "packaging", "PyInstaller", "pyinstaller-hooks-contrib")},
    "frozen_bytecode_matches_current_source": matches,
    "uses_windows_11_system_icu": True,
    "source_repository": os.environ.get("GITHUB_REPOSITORY"),
    "source_commit": os.environ.get("GITHUB_SHA"),
    "installer": {"path": installer.relative_to(ROOT).as_posix(), "bytes": installer.stat().st_size, "sha256": checksum(installer)},
    "inputs_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): checksum(p) for p in sorted(set(inputs))},
}
(ROOT / "dist/build-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"bytecode_matches": matches, "installer": manifest["installer"]}, ensure_ascii=False))
