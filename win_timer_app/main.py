from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .controller import AppController
from .main_window import MainWindow
from .storage import Storage


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    controller = AppController(Storage())
    window = MainWindow(controller, app)
    window.show()
    return app.exec()
