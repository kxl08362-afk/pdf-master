"""Quiet native desktop tokens: paper, ink, focus blue and one yellow action."""
COLORS = {
    "ink": "#202124", "muted": "#686E78", "line": "#E2E4E8",
    "paper": "#FFFFFF", "panel": "#FAFAFB", "desk": "#ECEEF1",
    "yellow": "#FFCF38", "focus": "#3674D8", "selection": "#EDF2FA",
}


def stylesheet():
    return _STYLE.replace("__FONT__", "DejaVu Sans")


_STYLE = """
QMainWindow, QWidget { background: #FAFAFB; color: #202124; font-family: '__FONT__'; font-size: 9pt; }
QMenuBar { background: #FAFAFB; color: #34373D; padding: 4px 14px; border-bottom: 1px solid #E7E8EB; }
QMenuBar::item { padding: 5px 10px; border-radius: 5px; }
QMenuBar::item:selected { background: #E9EBEF; }
QMenu { background: #FFFFFF; border: 1px solid #DADDE3; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 8px 28px 8px 12px; border-radius: 4px; }
QMenu::item:selected { background: #EDF2FA; color: #202124; }
QMenu::item:disabled { color: #A1A5AD; }
QMenu::separator { height: 1px; background: #ECEEF1; margin: 6px 9px; }
QMenu::section { color: #686E78; padding: 7px 12px 3px; font-size: 8pt; }
QToolBar#mainToolbar { background: #FFFFFF; border: none; border-bottom: 1px solid #E2E4E8; padding: 10px 14px; spacing: 6px; }
QToolBar::separator { width: 1px; background: #E3E5E9; margin: 6px 7px; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 7px 10px; color: #34373D; }
QToolButton:hover { background: #F0F1F4; }
QToolButton:pressed { background: #E3E5EA; }
QToolButton:checked { background: #FFFFFF; border-color: #D6D9E0; color: #202124; }
QToolButton:disabled { color: #AAADB4; }
QToolButton:focus { border: 1px solid #3674D8; }
QToolButton[role="primary"] { background: #FFCF38; border: 1px solid #F5C62F; color: #282710; font-weight: 600; padding: 8px 12px; }
QToolButton[role="primary"]:hover { background: #F7C52A; }
QToolButton[role="primary"]:pressed { background: #E9B51F; }
QToolButton[role="primary"]:disabled { background: #F4E5AE; border-color: #EEE3BD; color: #A29975; }
QToolButton[role="primary"]:focus { border: 1px solid #3674D8; }
QFrame#modeSegments { background: #F1F2F5; border: 1px solid #E4E6EB; border-radius: 8px; }
QFrame#modeSegments QToolButton { padding: 6px 10px; }
QFrame#modeSegments QToolButton:hover { background: #E7E9EF; }
QFrame#modeSegments QToolButton:checked { background: #FFF4CC; border-color: #E8D191; }
QFrame#modeSegments QToolButton:focus { border: 1px solid #3674D8; }
QLabel#toolbarBrand { color: #202124; font-size: 10pt; font-weight: 700; background: transparent; padding-right: 8px; }
QLabel#modeHint { background: #F8F9FB; color: #6A6F78; border-bottom: 1px solid #E4E6EB; padding: 8px 18px; font-size: 8pt; }
QLabel#eyebrow { color: #686E78; font-size: 8pt; font-weight: 600; }
QLabel#title { font-size: 34pt; font-weight: 600; color: #24272D; background: transparent; }
QLabel#description { font-size: 13pt; color: #686E78; background: transparent; }
QLabel#sectionTitle { font-size: 12pt; font-weight: 600; color: #24272D; }
QLabel#hint { color: #686E78; font-size: 8pt; }
QLabel#documentBadge { background: #FFFFFF; border: 1px solid #E3E6EB; border-radius: 5px; padding: 5px 8px; color: #686E78; font-size: 8pt; }
QFrame#startActions { background: #FFFFFF; border: 1px solid #E0E4EA; border-radius: 12px; }
QLabel#welcomeMark { background: transparent; }
QFrame#startActions QLabel { background: transparent; }
QLabel#welcomeFootnote { color: #686E78; background: transparent; font-size: 8pt; }
QWidget#pageSidebar, QWidget#inspector { background: #FAFAFB; }
QWidget#documentControls { background: #FFFFFF; border-bottom: 1px solid #E4E6EB; }
QWidget#documentControls QLabel { background: transparent; }
QPushButton { background: #FFFFFF; border: 1px solid #DDE1E7; padding: 8px 11px; border-radius: 6px; color: #34373D; }
QPushButton:hover { background: #F3F5F8; border-color: #C7CDD7; }
QPushButton:pressed { background: #E8EBF0; }
QPushButton:focus { border: 1px solid #3674D8; }
QPushButton:disabled { color: #AAADB4; background: #F6F7F9; border-color: #E7E9ED; }
QPushButton#primary { background: #FFCF38; border-color: #F4C531; color: #292711; font-weight: 600; }
QPushButton#primary:hover { background: #F7C52A; }
QPushButton#primary:pressed { background: #E9B51F; }
QPushButton#primary:disabled { background: #F4E5AE; border-color: #EEE3BD; color: #A29975; }
QPushButton#primary:focus { border: 1px solid #3674D8; }
QPushButton[role="navigation"] { text-align: left; border-color: transparent; background: transparent; padding: 10px 6px; }
QPushButton[role="navigation"]:hover { background: #EDF0F5; }
QPushButton[role="navigation"]:focus { border-color: #3674D8; }
QPushButton[role="compact"] { font-size: 8pt; padding: 7px 8px; }
QLineEdit, QTextEdit, QDoubleSpinBox, QComboBox { background: #FFFFFF; border: 1px solid #DDE1E7; border-radius: 6px; padding: 7px 8px; selection-background-color: #D4E2F9; selection-color: #202124; placeholder-text-color: #686E78; }
QLineEdit:focus, QTextEdit:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: #3674D8; }
QLineEdit:disabled, QTextEdit:disabled { color: #969BA4; background: #F3F5F7; }
QTextEdit { line-height: 1.4; }
QListWidget { background: #FAFAFB; border: none; outline: none; }
QListWidget::item { padding: 10px; border: 1px solid transparent; color: #686E78; border-radius: 6px; margin: 3px 7px; }
QListWidget::item:selected { background: #E7EDF7; border-color: #CBD8EE; color: #2F4C7B; }
QListWidget::item:hover { background: #F0F2F6; }
QListWidget#pageList::item { padding: 5px; margin: 3px; }
QGraphicsView { background: #ECEEF1; border: none; }
QGroupBox { border: none; border-top: 1px solid #E0E4EA; margin-top: 16px; padding-top: 16px; font-weight: 600; color: #34373D; }
QGroupBox::title { subcontrol-origin: margin; padding: 0 0 5px; }
QStatusBar { background: #FAFAFB; color: #686E78; border-top: 1px solid #E4E6EB; font-size: 8pt; padding: 2px 8px; }
QStatusBar QLabel { background: transparent; }
QProgressBar { border: 1px solid #DCE2EC; background: #F0F3F8; border-radius: 4px; height: 12px; text-align: center; }
QProgressBar::chunk { background: #6B91D1; border-radius: 3px; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #A5AEBB; border-radius: 4px; background: #FFFFFF; }
QCheckBox::indicator:checked { background: #4478C8; border: 3px solid #D9E6F9; }
QCheckBox::indicator:focus { border-color: #3674D8; }
QScrollArea { border: none; background: #FAFAFB; }
QSplitter::handle { background: #E2E5EB; width: 1px; }
QScrollBar:vertical { width: 10px; background: #F1F3F6; }
QScrollBar::handle:vertical { background: #BEC5D0; min-height: 30px; border-radius: 4px; margin: 2px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #292D35; color: #FFFFFF; border: none; padding: 7px 10px; border-radius: 5px; }
"""
