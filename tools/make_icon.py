"""Generate the application icon.

Draws a simplified steno board with a chord lit, then assembles a multi-resolution .ico.
Deliberately few shapes: at 16 px an accurate 24-key layout is unreadable mush, so the
icon shows a 3x2 bank plus a thumb key and relies on the lit keys for identity.

    py tools/make_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tinysteno import theme  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)
OUTPUT = ROOT / "assets" / "tinysteno.ico"
PREVIEW = ROOT / "assets" / "icon-preview.png"

# Grid of keys: (column, row, colour). Row 2 is the thumb.
KEYS = (
    (0, 0, None), (1, 0, theme.LEFT_BANK), (2, 0, None),
    (0, 1, None), (1, 1, None), (2, 1, theme.RIGHT_BANK),
    (1, 2, theme.VOWEL),
)


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)

    # Rounded-square backplate.
    pad = size * 0.04
    plate = QRectF(pad, pad, size - pad * 2, size - pad * 2)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#1b1e25"))
    painter.drawRoundedRect(plate, size * 0.22, size * 0.22)

    painter.setPen(Qt.NoPen)
    border = QColor("#2c313d")
    painter.setBrush(Qt.NoBrush)

    # Key grid, inset inside the plate.
    inner = plate.adjusted(size * 0.13, size * 0.13, -size * 0.13, -size * 0.13)
    pitch_x = inner.width() / 3
    pitch_y = inner.height() / 3
    gap = size * 0.022
    radius = size * 0.045

    for col, row, colour in KEYS:
        x = inner.x() + col * pitch_x
        y = inner.y() + row * pitch_y
        cell = QRectF(x + gap, y + gap, pitch_x - gap * 2, pitch_y - gap * 2)
        if row == 2:  # thumb key, nudged in and slightly wider
            cell = QRectF(
                inner.x() + pitch_x * 0.55 + gap,
                y + gap,
                pitch_x * 1.9 - gap * 2,
                pitch_y - gap * 2,
            )
        if colour:
            painter.setBrush(QColor(colour))
            painter.setPen(Qt.NoPen)
        else:
            painter.setBrush(QColor("#2a2f3b"))
            painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(cell, radius, radius)

    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    # The QByteArray must outlive the QBuffer that wraps it, so it is held in a local
    # rather than passed as a temporary.
    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def build_ico(images: list[QImage]) -> bytes:
    """Assemble a PNG-payload .ico. Qt has no ICO writer, but the container is trivial."""
    payloads = [png_bytes(image) for image in images]
    header = struct.pack("<HHH", 0, 1, len(payloads))
    offset = len(header) + 16 * len(payloads)

    entries = b""
    for image, payload in zip(images, payloads):
        dimension = 0 if image.width() >= 256 else image.width()
        entries += struct.pack(
            "<BBBBHHII",
            dimension, dimension, 0, 0, 1, 32, len(payload), offset,
        )
        offset += len(payload)

    return header + entries + b"".join(payloads)


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841 -- QPainter needs a QGuiApplication
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    images = [render(size) for size in SIZES]
    OUTPUT.write_bytes(build_ico(images))
    render(256).save(str(PREVIEW), "PNG")

    print(f"wrote {OUTPUT}  ({OUTPUT.stat().st_size:,} bytes, sizes {list(SIZES)})")
    print(f"wrote {PREVIEW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
