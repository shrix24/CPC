from PySide6.QtWidgets import QWidget, QVBoxLayout

from gnb_clock_estimator.gui import FiveGEstimatorWidget


class FiveGTab(QWidget):
    """5G gNB clock bias / drift correction tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(FiveGEstimatorWidget())
