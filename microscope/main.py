"""Entry point for the IDS Camera Raman microscope acquisition GUI."""

import sys

from PyQt5.QtWidgets import QApplication

from microscope.gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("IDS Camera - Raman Microscope")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
