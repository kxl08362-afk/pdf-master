# Third-party components

PDF Мастер 0.3.0 is distributed under GNU AGPL version 3 only; see LICENSE.txt. The corresponding application source and build scripts accompany the release. You may modify and redistribute the application under that license. There is no warranty.

| Component | Version / source | License / notices |
| --- | --- | --- |
| PyMuPDF / MuPDF | PyMuPDF 1.28.2, https://github.com/pymupdf/PyMuPDF | AGPL-3.0 (open-source choice); Artifex alternative commercial licensing is not used. See licenses/PyMuPDF-COPYING.txt and LICENSE.txt. |
| PySide6 Essentials, Shiboken6, Qt | 6.12.0, https://code.qt.io/pyside/pyside-setup.git and https://code.qt.io/qt/qtbase.git | LGPL-3.0 open-source choice, including corresponding GPL terms and Qt exception where applicable; DLLs remain separate and replaceable. See licenses/LGPL-3.0.txt, GPL-3.0.txt, Qt-GPL-exception-1.0.txt and Qt-THIRD-PARTY-NOTICE.md. |
| Pillow | 13.0.0, https://github.com/python-pillow/Pillow | HPND and bundled dependency notices; licenses/Pillow-LICENSE.txt. |
| img2pdf | 0.6.3, https://gitlab.mister-muffin.de/josch/img2pdf | LGPL-3.0-or-later; actual image-to-PDF conversion dependency, unmodified. See licenses/conversion-libraries/img2pdf/LICENSE and GPL-3.0.txt. |
| pikepdf | 10.17.0, https://github.com/pikepdf/pikepdf | MPL-2.0; actual lossless PDF optimizer and img2pdf PDF backend, unmodified. See licenses/conversion-libraries/pikepdf/LICENSE.txt. |
| QPDF and its Windows-wheel dependencies | QPDF 12.4.2 inside pikepdf wheel | Apache-2.0; includes native QPDF, libjpeg-turbo, OpenSSL, zlib and VC runtime notices under licenses/conversion-libraries/pikepdf/third-party-licenses/. |
| lxml | 6.1.3; bundled libxml2 2.11.9 and libxslt 1.1.45 | BSD-3-Clause and included MIT/PSF/component terms; licenses/conversion-libraries/lxml/LICENSE.txt and LICENSES.txt. |
| packaging | 26.3, https://github.com/pypa/packaging | Apache-2.0 OR BSD-2-Clause; licenses/conversion-libraries/packaging/. |
| CPython | Version recorded in build environment, https://www.python.org/ | Python Software Foundation and bundled notices; licenses/Python-LICENSE.txt. |
| PyInstaller bootloader | 6.22.3, https://github.com/pyinstaller/pyinstaller | GPL-2.0-or-later with special distribution exception; licenses/PyInstaller-COPYING.txt. |
| Tesseract language data, rus + eng (best) | https://github.com/tesseract-ocr/tessdata_best | Apache-2.0; licenses/tessdata-LICENSE.txt. |
| DejaVu Sans | https://dejavu-fonts.github.io/ | Bitstream Vera / DejaVu terms; licenses/DejaVu-LICENSE.txt. |
| Inno Setup installer runtime | 6.2.2, https://github.com/jrsoftware/issrc | Inno Setup license; licenses/InnoSetup-LICENSE.txt. Compiler is a build tool. |

Application source archives contain the complete application-specific code, installer recipe and pinned build requirements. The open-source license texts are included with the installed program under `_internal/licenses`. Qt shared libraries are not locked or signature-checked by this application; replacement for debugging modified libraries is permitted under the LGPL. Reverse engineering for that purpose is permitted to the extent required by LGPL.

Exact upstream corresponding source:

- PyMuPDF 1.28.2: https://github.com/pymupdf/PyMuPDF/tree/1.28.2
- Native MuPDF 1.28.2, including Git submodules: https://github.com/ArtifexSoftware/mupdf/tree/1.28.2 ; exact third-party component commits and saved notices are under `licenses/mupdf-third-party/`.
- Qt 6.12.0: https://github.com/qt/qtbase/tree/v6.12.0 , https://github.com/qt/qtimageformats/tree/v6.12.0 and https://github.com/qt/qtsvg/tree/v6.12.0
- PySide6 / Shiboken6 6.12.0: https://github.com/qtproject/pyside-pyside-setup/tree/v6.12.0
- Pillow 13.0.0: https://github.com/python-pillow/Pillow/tree/13.0.0
- CPython 3.12.14: https://github.com/python/cpython/tree/v3.12.14
- PyInstaller 6.22.3: https://github.com/pyinstaller/pyinstaller/tree/v6.22.3
- Inno Setup 6.2.2: https://github.com/jrsoftware/issrc/tree/is-6_2_2

Exact source archive download URLs and SHA256 for img2pdf 0.6.3, pikepdf 10.17.0, lxml 6.1.3 and packaging 26.3 are recorded in `licenses/conversion-libraries/corresponding-sources.json`. Native QPDF source: https://github.com/qpdf/qpdf/tree/v12.4.2 . lxml's compiled libraries: https://gitlab.gnome.org/GNOME/libxml2/-/tree/v2.11.9 and https://gitlab.gnome.org/GNOME/libxslt/-/tree/v1.1.45 . No patches to these libraries are applied. Their notices and source references accompany both application binaries and application source. Rebuilding with a modified library is permitted under the applicable LGPL/MPL conditions.

User signatures and seals are images supplied by the user. They are not covered by the application license. The application does not provide cryptographic electronic signatures.
