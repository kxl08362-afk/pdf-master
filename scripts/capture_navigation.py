"""One bounded visual QA batch for the desktop navigation, without user data."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf as fitz
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from engine import _font_path
from ui import MainWindow
from command_menu import show_command_palette

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "qa/navigation"


def create_demo():
    path = QA / "Пример договора.pdf"
    with fitz.open() as doc:
        for number in range(3):
            page = doc.new_page(width=595, height=842)
            page.insert_font(fontname="demo", fontfile=_font_path())
            def text(y, value, size=11, color=(.14, .16, .19)):
                page.insert_text((54, y), value, fontsize=size, fontname="demo", color=color)
            text(64, "ПРИМЕР ДОКУМЕНТА", 9, (.40, .44, .49))
            page.draw_line((54, 81), (541, 81), color=(.82, .84, .87), width=.6)
            if number == 0:
                text(126, "Договор оказания услуг", 23)
                text(154, "№ 18/10 · 18 октября 2026 года", 10, (.4, .43, .47))
                for y, line in [(215,"1. Предмет договора"), (332,"2. Порядок выполнения работ"), (472,"3. Результат и приёмка")]:
                    text(y,line,13)
                lines = {
                    243:"Исполнитель оказывает услуги по подготовке документов.",
                    263:"Состав работ и сроки стороны согласуют в приложении.",
                    283:"Заказчик предоставляет необходимые исходные сведения.",
                    360:"Работы начинаются после согласования задания.",
                    380:"В ходе работы стороны обмениваются документами",
                    400:"и согласуют необходимые уточнения.",
                    500:"Результат передаётся заказчику в электронном виде.",
                    520:"После проверки стороны подписывают акт оказанных услуг.",
                    634:"Исполнитель                              Заказчик",
                    682:"__________________                       __________________",
                }
                for y, value in lines.items(): text(y,value)
                text(740,"Учебный пример. Сведения о реальных сторонах не используются.",8,(.45,.47,.5))
            elif number == 1:
                text(126,"Условия работы",23)
                for y,value in [(204,"4. Сроки и взаимодействие"),(238,"Сроки определяются согласованным заданием."),(272,"О готовности результата исполнитель сообщает заказчику."),(354,"5. Документы и изменения"),(388,"Изменения задания согласуются обеими сторонами."),(422,"Копии документов сохраняются у участников договора.")]:
                    text(y,value,13 if y in (204,354) else 11)
            else:
                text(126,"Приложение к договору",23)
                for y,value in [(204,"Перечень работ"),(248,"01    Подготовка и проверка исходных сведений"),(292,"02    Согласование содержания документов"),(336,"03    Передача готового комплекта заказчику")]: text(y,value,12)
            text(794,f"Пример договора                                                     {number+1} / 3",9,(.45,.47,.5))
        doc.save(path)
    return path


def main():
    QA.mkdir(parents=True, exist_ok=True)
    if not (ROOT / "qa/stamp.png").exists():
        from scripts.qa_fixtures import make_fixtures
        make_fixtures()
    demo = create_demo()
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    def settle():
        app.processEvents()
        QTest.qWait(120)
        app.processEvents()
    def capture(name, widget=window):
        settle()
        if not widget.grab().save(str(QA / (name + ".png"))):
            raise RuntimeError(name)
    window.resize(1420,920)
    capture("01-welcome-desktop")
    window.resize(1030,700)
    capture("02-welcome-small")
    if not window.open_file(demo): raise RuntimeError("Demo open failed")
    window.resize(1420,920)
    window.fit_width()
    capture("03-document-desktop")
    window.set_mode("edit")
    capture("04-text-desktop")
    window.resize(1030,700)
    window.fit_width()
    capture("05-text-small")
    window.set_mode("stamp")
    window.load_stamp(ROOT / "qa/stamp.png")
    capture("06-stamp-small")
    window.set_mode("view")
    window.resize(1420,920)
    window.fit_width()
    dialog = show_command_palette(window)
    dialog.search.setText("скан")
    capture("07-command-search", dialog)
    dialog.search.clear()
    capture("08-command-all", dialog)
    dialog.search.setText("несуществующий запрос")
    capture("09-command-empty", dialog)
    dialog.reject()
    settle()
    menu = window.navigation_menus["Инструменты"]
    menu.popup(window.mapToGlobal(window.rect().center()))
    capture("10-tools-menu", menu)
    menu.close()
    window.engine.dirty=False
    window.close()
    print(str(QA))


if __name__ == "__main__": main()
