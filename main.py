import shutil
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from ui.main_window import MainWindow


def check_dependencies():
    missing = []
    if not shutil.which("convbin"):
        missing.append("convbin")
    if not shutil.which("rnx2rtkp"):
        missing.append("rnx2rtkp")

    if missing:
        app = QApplication(sys.argv)
        QMessageBox.critical(
            None,
            "Missing Dependencies",
            f"The following RTKLIB tools were not found on PATH:\n\n"
            f"  {', '.join(missing)}\n\n"
            f"Please install RTKLIB before running this application.\n"
            f"On Ubuntu/Debian: sudo apt install rtklib\n"
            f"On macOS: brew install rtklib",
        )
        sys.exit(1)


def main():
    check_dependencies()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
