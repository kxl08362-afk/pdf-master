"""Keep the Windows wheel's versioned QPDF DLL and DLL-directory patch intact."""
from PyInstaller.utils.hooks import collect_delvewheel_libs_directory

datas, binaries = collect_delvewheel_libs_directory("pikepdf")
hiddenimports = ["pikepdf._cpphelpers", "pikepdf._methods", "pikepdf.codec"]
