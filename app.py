"""Application entry point (source and PyInstaller)."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox


def main(argv=None):
    parser = argparse.ArgumentParser(description="PDF Мастер")
    parser.add_argument("file", nargs="?")
    parser.add_argument("--open", dest="open_file")
    parser.add_argument("--screenshot", metavar="PNG")
    parser.add_argument("--self-test", metavar="JSON")
    args = parser.parse_args(argv)
    if args.self_test:
        from diagnostics import run_self_test
        return run_self_test(args.self_test)
    log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PDFMaster" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_dir / "application.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("PDF Мастер")
    app.setApplicationVersion("0.3.0")
    app.setOrganizationName("PDFMaster")
    from ui import MainWindow
    window = MainWindow()
    def exception_hook(kind, value, traceback):
        logging.critical("Uncaught exception", exc_info=(kind, value, traceback))
        QMessageBox.critical(window, "Ошибка программы", str(value) + "\n\nЖурнал: " + str(log_dir / "application.log"))
    sys.excepthook = exception_hook
    window.show()
    if args.open_file or args.file:
        window.open_file(args.open_file or args.file)
    if args.screenshot:
        def capture():
            Path(args.screenshot).parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(args.screenshot)
            app.quit()
        QTimer.singleShot(1100, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
