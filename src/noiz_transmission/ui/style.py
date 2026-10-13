"""Compact, native-friendly visual language for the acoustic workbench."""

STYLESHEET = """
QMainWindow, QWidget { color: #263d4c; font-size: 12px; }
QMainWindow { background: #edf1f4; }
QWidget#workspace { background: #edf1f4; }
QScrollArea QWidget { background: #ffffff; }
QWidget#sheet, QFrame#sheet { background: #ffffff; border: 1px solid #d9e2e8; border-radius: 5px; }
QLabel { background: transparent; }
QLabel#brand { color: #113e50; font-size: 19px; font-weight: 700; }
QLabel#sectionTitle { font-weight: 600; color: #164b61; font-size: 13px; }
QLabel#muted { color: #667b89; font-size: 11px; }
QLabel#metric { color: #006b86; font-size: 25px; font-weight: 600; }
QLabel#status { color: #746021; background: #fff8e4; border: 1px solid #eadba4; border-radius: 3px; padding: 5px; }
QLabel#error { color: #a52b37; background: #fff0f0; border: 1px solid #ebc6cb; border-radius: 3px; padding: 5px; }
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QTextEdit {
 background: #ffffff; border: 1px solid #c4d2dc; border-radius: 3px; padding: 4px 6px; min-height: 21px;
 selection-background-color: #cee8f0; selection-color: #193d50;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus { border: 1px solid #007c99; }
QLineEdit:disabled, QDoubleSpinBox:disabled { background: #f1f4f6; color: #92a0a9; }
QComboBox QAbstractItemView { background: white; selection-background-color: #d7edf3; selection-color: #163e50; }
QPushButton, QToolButton { background: #ffffff; border: 1px solid #c5d3dc; border-radius: 3px; padding: 6px 10px; }
QPushButton:hover, QToolButton:hover { background: #e6f2f6; border-color: #77aabc; }
QPushButton:pressed, QToolButton:pressed { background: #cfE5ec; }
QPushButton:disabled { color: #97a6af; background: #f0f3f5; border-color: #dbe2e7; }
QPushButton#primary { background: #006f89; color: #ffffff; border-color: #006f89; font-weight: 600; }
QPushButton#primary:hover { background: #005d75; }
QPushButton#nav { text-align: left; padding: 16px 10px; font-size: 15px; border: none; border-radius: 3px; background: transparent; }
QPushButton#nav:checked { background: #006986; color: #ffffff; font-weight: 700; border-left: 3px solid #007c99; }
QPushButton#nav:hover { background: #e0ebf0; }
QToolBar { background: #ffffff; border-bottom: 1px solid #d9e2e8; spacing: 4px; padding: 3px 7px; }
QToolBar QToolButton { border: none; padding: 5px 8px; }
QMenuBar { background: #ffffff; border-bottom: 1px solid #e2e9ed; }
QMenuBar::item:selected, QMenu::item:selected { background: #d5eaf1; }
QMenu { background: #ffffff; border: 1px solid #c4d2dc; padding: 4px; }
QMenu::item { padding: 6px 23px; }
QTabWidget::pane { background: white; border: 1px solid #d4dfe6; }
QTabBar::tab { background: #edf3f6; color: #536c7a; padding: 8px 15px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { background: white; color: #00647e; border-bottom: 2px solid #007c99; font-weight: 600; }
QTabBar::tab:hover { background: #e2eef3; }
QTabBar#topologyTabs::tab { background: #f3f7f9; color: #276379; padding: 10px 12px; font-size: 13px; }
QTabBar#topologyTabs::tab:selected { background: #006986; color: white; border-bottom: 2px solid #006986; }
QTabBar#partTabs::tab { background: #ffffff; color: #8d4737; padding: 8px 8px; }
QTabBar#partTabs::tab:selected { background: #a44330; color: white; border-bottom: 2px solid #a44330; }
QTabBar#layerTabs::tab { background: #f5f8fa; padding: 8px 9px; }
QTabBar#layerTabs::tab:selected { background: #d9ecf3; color: #006986; border-bottom: 2px solid #006986; }
QListWidget { background: white; alternate-background-color: #f5f8fa; border: 1px solid #d4dfe6; outline: none; }
QListWidget::item { padding: 3px 4px; }
QListWidget::item:selected { background: #d5eaf4; color: #124b67; }
QLabel#pickerHeading { color: #0b607a; font-weight: 600; padding: 3px 4px; background: #eaf2f6; }
QTableWidget, QTreeWidget { background: white; alternate-background-color: #f5f8fa; border: 1px solid #d4dfe6; gridline-color: #e6edf1; outline: none; selection-background-color: #d9edf4; selection-color: #18465a; }
QHeaderView::section { background: #eaf1f5; color: #476476; font-weight: 600; padding: 6px; border: none; border-bottom: 1px solid #ccdce5; }
QTreeWidget::item, QTableWidget::item { padding: 4px; }
QGroupBox { border: 1px solid #d6e1e8; border-radius: 4px; margin-top: 12px; padding-top: 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #385c70; }
QStatusBar { background: #ffffff; color: #647987; border-top: 1px solid #d7e2e9; font-size: 11px; }
QSplitter::handle { background: #dfe7ec; }
QSplitter::handle:hover { background: #a7c8d6; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { width: 10px; background: #edf2f5; }
QScrollBar:horizontal { height: 10px; background: #edf2f5; }
QScrollBar::handle { background: #bdccd6; border-radius: 4px; min-height: 24px; min-width: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QProgressBar { border: none; background: #e7f1f5; height: 3px; }
QProgressBar::chunk { background: #007e99; }
QToolTip { background: #f8fbfd; color: #234454; border: 1px solid #a7bdc9; padding: 5px; }
"""
