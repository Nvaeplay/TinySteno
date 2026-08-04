"""Entry point for the TinyMod4 Steno Trainer."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QLabel

from tinysteno import theme
from tinysteno.dictionary import StenoDictionary
from tinysteno.mainwindow import MainWindow
from tinysteno.storage import Profile


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("TinyMod4 Steno Trainer")
    app.setStyleSheet(theme.STYLESHEET)
    app.setFont(QFont(theme.UI_FAMILY.split(",")[0], 10))

    # main.json is ~4.3 MB, so say something while it loads.
    splash = QLabel("Loading your Plover dictionary…")
    splash.setAlignment(Qt.AlignCenter)
    splash.setStyleSheet(
        f"background: {theme.BG}; color: {theme.TEXT_DIM}; font-size: 15px;"
    )
    splash.resize(420, 130)
    splash.setWindowFlag(Qt.FramelessWindowHint)
    splash.show()
    app.processEvents()

    profile = Profile.load()
    paths = [Path(p) for p in profile.settings.get("dictionary_paths") or []]
    dictionary = StenoDictionary.load(paths or None)

    splash.close()

    if not dictionary.entries:
        error = QLabel(
            "No Plover dictionary was found.\n\n"
            "Expected it at %LOCALAPPDATA%\\plover\\plover\\main.json.\n"
            "Install Plover, or point the app at a dictionary in Settings."
        )
        error.setAlignment(Qt.AlignCenter)
        error.setStyleSheet(
            f"background: {theme.BG}; color: {theme.TEXT}; font-size: 14px; padding: 30px;"
        )
        error.resize(520, 220)
        error.show()
        return app.exec()

    window = MainWindow(dictionary, profile)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
