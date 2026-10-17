# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs

root = Path(SPECPATH)
datas = [(str(root / "resources"), "resources"), (str(root / "licenses"), "licenses")]
for name in ("LICENSE.txt", "THIRD_PARTY.md", "README.md", "USER_GUIDE.md", "SOURCES.md"):
    if (root / name).is_file():
        datas.append((str(root / name), "."))

a = Analysis(
    [str(root / "app.py")],
    pathex=[str(root)],
    binaries=collect_dynamic_libs("pymupdf"),
    datas=datas,
    hiddenimports=["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets", "command_menu", "ui_theme", "ui_icons"],
    hookspath=[str(root / "installer" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtMultimedia", "PySide6.QtSql", "PySide6.QtTest"],
    noarchive=False,
    optimize=0,
)
# Qt 6.12 uses Windows 11's system ICU (unversioned exports). PATH may
# contain an unrelated ICU build (e.g. Tesseract's suffixed ICU78), which
# PyInstaller would otherwise bundle by basename and break QtCore startup.
# Windows 11 already provides the required icuuc.dll; never override it.
a.binaries = [entry for entry in a.binaries if not (
    Path(entry[0]).name.lower() == "icuuc.dll"
    or (Path(entry[0]).name.lower().startswith("icudt") and Path(entry[0]).suffix.lower() == ".dll")
)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="PDFMaster", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
    icon=str(root / "resources" / "icon.ico"),
    version=str(root / "installer" / "version.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PDFMaster")
