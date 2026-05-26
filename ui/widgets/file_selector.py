from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog,
)
from PySide6.QtCore import Signal


class FileSelector(QWidget):
    """Reusable file picker: label + text field + Browse button."""

    file_selected = Signal(str)

    def __init__(self, label: str, file_filter: str = "All Files (*)", parent=None):
        super().__init__(parent)
        self._filter = file_filter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel(label)
        self._label.setFixedWidth(160)
        layout.addWidget(self._label)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("No file selected")
        self._edit.setReadOnly(True)
        layout.addWidget(self._edit, 1)

        self._btn = QPushButton("Browse…")
        self._btn.clicked.connect(self._browse)
        layout.addWidget(self._btn)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, f"Select {self._label.text()}", "", self._filter)
        if path:
            self._edit.setText(path)
            self.file_selected.emit(path)

    def path(self) -> str:
        return self._edit.text()

    def set_path(self, path: str):
        self._edit.setText(path)


class MultiFileSelector(QWidget):
    """File picker that allows selecting multiple files."""

    files_selected = Signal(list)

    def __init__(self, label: str, file_filter: str = "All Files (*)", parent=None):
        super().__init__(parent)
        self._filter = file_filter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel(label)
        self._label.setFixedWidth(160)
        layout.addWidget(self._label)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("No files selected")
        self._edit.setReadOnly(True)
        layout.addWidget(self._edit, 1)

        self._btn = QPushButton("Browse…")
        self._btn.clicked.connect(self._browse)
        layout.addWidget(self._btn)

        self._paths: list[str] = []

    def _browse(self):
        paths, _ = QFileDialog.getOpenFileNames(self, f"Select {self._label.text()}", "", self._filter)
        if paths:
            self._paths = paths
            self._edit.setText("; ".join(paths))
            self.files_selected.emit(paths)

    def paths(self) -> list[str]:
        return self._paths


class DirectorySelector(QWidget):
    """Directory picker: label + text field + Browse button."""

    directory_selected = Signal(str)

    def __init__(self, label: str, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel(label)
        self._label.setFixedWidth(160)
        layout.addWidget(self._label)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("Same as vehicle file directory")
        layout.addWidget(self._edit, 1)

        self._btn = QPushButton("Browse…")
        self._btn.clicked.connect(self._browse)
        layout.addWidget(self._btn)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self._edit.setText(path)
            self.directory_selected.emit(path)

    def path(self) -> str:
        return self._edit.text()

    def set_path(self, path: str):
        self._edit.setText(path)
