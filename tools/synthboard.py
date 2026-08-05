"""Render a fake photo of a steno keyboard, with known geometry.

Detection has to be tested against something whose right answer is known, and a real
photograph does not come with one. This draws a board from a layout the caller specifies,
so a test can assert that what came back out matches what went in.

It deliberately renders the awkward case as well as the easy one: keycaps only a little
lighter than the board they sit on, and switches with the keycap pulled off, which is what
an asterisk column normally looks like in a photo of a hobbyist board.

Shared by tests.py and smoke_gui.py so there is one renderer rather than two that drift.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

# A TinyMod-style arrangement: four keys, the asterisk column, five keys, twice over, then
# thumbs tucked inboard either side of the asterisks.
STAR_COL = 4.15
RIGHT_COL = 5.1


def tinymod_layout() -> tuple[list[tuple[float, float]], set[int]]:
    """(positions, indexes of the asterisk column). 25 switches, 3 of them bare."""
    positions: list[tuple[float, float]] = []
    for row in (0.0, 1.0):
        positions += [(col, row) for col in (0.0, 1.0, 2.0, 3.0)]
        positions.append((STAR_COL, row))
        positions += [(RIGHT_COL + i, row) for i in range(5)]
    positions += [
        (1.9, 2.45), (2.9, 2.45), (STAR_COL, 2.45), (RIGHT_COL, 2.45), (RIGHT_COL + 1, 2.45)
    ]
    bare = {index for index, (col, _row) in enumerate(positions) if col == STAR_COL}
    return positions, bare


def render(
    path: Path,
    positions: list[tuple[float, float]],
    bare: set[int] = frozenset(),
    pitch: int = 64,
    cap: int = 54,
    margin: int = 70,
) -> Path:
    """Draw the board and save it. `bare` indexes render as a switch with no keycap."""
    width = int(max(col for col, _ in positions) * pitch + cap + margin * 2)
    height = int(max(row for _, row in positions) * pitch + cap + margin * 2)

    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(QColor("#141414"))          # A dark desk mat, as in the real photos.
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)

    for index, (col, row) in enumerate(positions):
        x = margin + col * pitch
        y = margin + row * pitch
        if index in bare:
            # An empty switch: dark housing, bright cross stem. Small enough that the
            # area filter rejects it, which is what leaves the gap to be inferred.
            painter.setBrush(QColor("#1d1d1d"))
            painter.drawRect(QRectF(x, y, cap, cap))
            painter.setBrush(QColor("#d8d8d8"))
            painter.drawRect(QRectF(x + cap / 2 - 3, y + cap / 2 - 9, 6, 18))
            continue
        painter.setBrush(QColor("#4a4a4a"))
        painter.drawRoundedRect(QRectF(x, y, cap, cap), 6, 6)

    painter.end()
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path))
    return path
