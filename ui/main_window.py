from PySide6.QtWidgets import QMainWindow, QTabWidget
from PySide6.QtCore import Qt

from ui.rtk_tab import RTKTab
from ui.fiveg_tab import FiveGTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CPC — GNSS Post-Processing Correction")
        self.setMinimumSize(1100, 750)

        tabs = QTabWidget()
        tabs.setStyleSheet("QTabBar::tab { padding: 8px 20px; font-size: 13px; }")

        self._rtk_tab = RTKTab()
        tabs.addTab(self._rtk_tab, "RTK Post-Processing")

        self._fiveg_tab = FiveGTab()
        tabs.addTab(self._fiveg_tab, "5G Correction")

        self.setCentralWidget(tabs)
