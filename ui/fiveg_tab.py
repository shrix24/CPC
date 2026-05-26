from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class FiveGTab(QWidget):
    """Placeholder tab for future 5G gNB clock bias/drift correction."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("5G gNB Clock Bias / Drift Correction")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #555;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Coming Soon")
        subtitle.setStyleSheet("font-size: 16px; color: #999; margin-top: 10px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        desc = QLabel(
            "This module will implement 5G gNB clock bias and clock drift correction.\n"
            "The functionality is under development and will be available in a future release."
        )
        desc.setStyleSheet("font-size: 12px; color: #aaa; margin-top: 20px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)
