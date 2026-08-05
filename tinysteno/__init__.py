"""TinyMod4 Steno Trainer."""

import sys
from pathlib import Path

__version__ = "1.1.0"
APP_NAME = "TinyMod4 Steno Trainer"


def resource_path(relative: str) -> Path:
    """Locate a bundled file, whether running from source or from a PyInstaller build.

    PyInstaller unpacks data files to sys._MEIPASS; from source they sit next to the
    package.
    """
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root / relative
