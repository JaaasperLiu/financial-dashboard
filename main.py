"""Entry point for the Financial Dashboard desktop app."""
from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication

from app.data import db
from app.ui.main_window import MainWindow


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    db.init_db()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
