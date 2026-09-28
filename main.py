import sys

from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon

from core.paths import resource_path
from ui.main_window import MainWindow


DARK_STYLE = """
QWidget {
    background-color: #14192b;
    color: #dce3f0;
    font-size: 10.5pt;
}
QMainWindow, QDialog {
    background-color: #14192b;
}
QMenuBar {
    background-color: #1b2138;
    color: #dce3f0;
}
QMenuBar::item:selected {
    background-color: #2a3358;
}
QMenu {
    background-color: #1b2138;
    color: #dce3f0;
    border: 1px solid #2a3358;
}
QMenu::item:selected {
    background-color: #2a3358;
}
QTabWidget::pane {
    border: 1px solid #2a3358;
    background-color: #171d33;
}
QTabBar::tab {
    background-color: #1b2138;
    color: #9fb0d0;
    padding: 6px 14px;
    border: 1px solid #2a3358;
    border-bottom: none;
}
QTabBar::tab:selected {
    background-color: #26305a;
    color: #ffffff;
}
QPushButton {
    background-color: #26305a;
    color: #e8edf7;
    border: 1px solid #3a4a86;
    border-radius: 4px;
    padding: 6px 10px;
}
QPushButton:hover {
    background-color: #34428a;
}
QPushButton:pressed {
    background-color: #1c2547;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
    background-color: #0f1424;
    color: #dce3f0;
    border: 1px solid #2a3358;
    border-radius: 3px;
    padding: 3px;
}
QTableWidget {
    background-color: #0f1424;
    alternate-background-color: #171d33;
    gridline-color: #2a3358;
    color: #dce3f0;
    border: 1px solid #2a3358;
}
QHeaderView::section {
    background-color: #1b2138;
    color: #9fb0d0;
    padding: 4px;
    border: 1px solid #2a3358;
}
QProgressBar {
    background-color: #0f1424;
    border: 1px solid #2a3358;
    border-radius: 3px;
    text-align: center;
    color: #dce3f0;
}
QProgressBar::chunk {
    background-color: #4fd1e8;
    border-radius: 3px;
}
QStatusBar {
    background-color: #1b2138;
    color: #9fb0d0;
}
QGroupBox {
    border: 1px solid #2a3358;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #9fb0d0;
}
QLabel {
    color: #dce3f0;
}
"""


def main():
    # Must be set before QSettings/QStandardPaths are used anywhere (paths.py
    # relies on this to find the right per-user AppData folder).
    QCoreApplication.setOrganizationName("KaranKataria")
    QCoreApplication.setApplicationName("Dockomo")

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLE)
    win = MainWindow()
    win.setWindowIcon(QIcon(resource_path("assets", "icon.ico")))
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
