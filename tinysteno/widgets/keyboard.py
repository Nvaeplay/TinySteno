"""The on-screen TinyMod4.

Shows the chord to press, then shows what actually happened. When a key was pressed on the
wrong side of the board, the two keys involved are joined by an arc so the swap is visible
at a glance rather than something to work out from two lists of key names.
"""

from __future__ import annotations

import math
from enum import Enum

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import theme
from ..layout import BANK_GAP_AFTER_COL, GRID_COLS, KEYCAPS, KeyCap

# Layout constants in "key pitch" units.
GUTTER = 0.55        # Gap between the left and right banks.
THUMB_DROP = 0.42    # How far the thumb row sits below the home row.
KEY_INSET = 0.06     # Padding inside each pitch cell, so keys do not touch.
CORNER = 0.16        # Corner radius as a fraction of key size.


class KeyState(Enum):
    IDLE = "idle"
    EXPECTED = "expected"    # Part of the chord to press
    CORRECT = "correct"      # Pressed, and it belonged
    EXTRA = "extra"          # Pressed, but it did not belong
    MISSED = "missed"        # Belonged, but was not pressed
    SWAP_FROM = "swap_from"  # Pressed here, should have been the mirror key
    SWAP_TO = "swap_to"      # The mirror key that was wanted


class StenoKeyboard(QWidget):
    """A painted TinyMod4 that can display a chord and critique an attempt."""

    key_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None, interactive: bool = False) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(190)
        self.setMouseTracking(True)

        self._interactive = interactive
        self._expected: set[str] = set()
        self._states: dict[str, KeyState] = {}
        self._swap_arcs: list[tuple[str, str]] = []
        self._hover: KeyCap | None = None
        self._show_qwerty = False

        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    # ---- public API ---------------------------------------------------------------

    def show_chord(self, keys) -> None:
        """Light the chord the learner should press."""
        self._expected = set(keys)
        self._states = {key: KeyState.EXPECTED for key in self._expected}
        self._swap_arcs = []
        self._ensure_animation()
        self.update()

    def show_attempt(self, expected, actual, swaps=()) -> None:
        """Overlay what was pressed on top of what was wanted."""
        expected, actual = set(expected), set(actual)
        self._expected = expected
        states: dict[str, KeyState] = {}

        for key in expected & actual:
            states[key] = KeyState.CORRECT
        for key in expected - actual:
            states[key] = KeyState.MISSED
        for key in actual - expected:
            states[key] = KeyState.EXTRA

        arcs = []
        for swap in swaps:
            states[swap.actual] = KeyState.SWAP_FROM
            states[swap.expected] = KeyState.SWAP_TO
            arcs.append((swap.actual, swap.expected))

        self._states = states
        self._swap_arcs = arcs
        self._ensure_animation()
        self.update()

    def show_success(self, keys) -> None:
        self._expected = set(keys)
        self._states = {key: KeyState.CORRECT for key in self._expected}
        self._swap_arcs = []
        self._ensure_animation()
        self.update()

    def clear(self) -> None:
        self._expected = set()
        self._states = {}
        self._swap_arcs = []
        self._timer.stop()
        self.update()

    def set_qwerty_labels(self, enabled: bool) -> None:
        self._show_qwerty = enabled
        self.update()

    # ---- animation ----------------------------------------------------------------

    def _ensure_animation(self) -> None:
        needs_pulse = any(
            state in (KeyState.EXPECTED, KeyState.MISSED, KeyState.SWAP_TO)
            for state in self._states.values()
        )
        if needs_pulse and not self._timer.isActive():
            self._phase = 0.0
            self._timer.start()
        elif not needs_pulse:
            self._timer.stop()
            self.update()

    def _tick(self) -> None:
        self._phase += 0.055
        self.update()

    def _pulse(self) -> float:
        """A gentle 0..1 breathing value."""
        return 0.5 + 0.5 * math.sin(self._phase * math.pi)

    # ---- geometry -----------------------------------------------------------------

    def _unit(self) -> float:
        total_w = GRID_COLS + GUTTER
        total_h = 3 + THUMB_DROP
        return min(self.width() / total_w, self.height() / total_h)

    def _origin(self) -> QPointF:
        unit = self._unit()
        board_w = (GRID_COLS + GUTTER) * unit
        board_h = (3 + THUMB_DROP) * unit
        return QPointF((self.width() - board_w) / 2, (self.height() - board_h) / 2)

    def _cell(self, cap: KeyCap) -> QRectF:
        unit = self._unit()
        origin = self._origin()
        x = cap.col * unit
        if cap.col > BANK_GAP_AFTER_COL:
            x += GUTTER * unit
        y = cap.row * unit
        if cap.row == 2:
            y += THUMB_DROP * unit
        inset = KEY_INSET * unit
        return QRectF(
            origin.x() + x + inset,
            origin.y() + y + inset,
            unit - inset * 2,
            unit - inset * 2,
        )

    def _cap_at(self, pos) -> KeyCap | None:
        for cap in KEYCAPS:
            if self._cell(cap).contains(pos):
                return cap
        return None

    # ---- events -------------------------------------------------------------------

    def mouseMoveEvent(self, event) -> None:
        cap = self._cap_at(event.position())
        if cap is not self._hover:
            self._hover = cap
            self.setCursor(
                Qt.PointingHandCursor if (cap and self._interactive) else Qt.ArrowCursor
            )
            if cap:
                self.setToolTip(f"{cap.key}  ·  {cap.side} bank")
            self.update()

    def leaveEvent(self, event) -> None:
        self._hover = None
        self.update()

    def mousePressEvent(self, event) -> None:
        cap = self._cap_at(event.position())
        if cap and self._interactive:
            self.key_clicked.emit(cap.key)

    # ---- painting -----------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        unit = self._unit()
        pulse = self._pulse()

        for cap in KEYCAPS:
            self._paint_key(painter, cap, unit, pulse)

        for from_key, to_key in self._swap_arcs:
            self._paint_swap_arc(painter, from_key, to_key, unit, pulse)

        painter.end()

    def _paint_key(self, painter: QPainter, cap: KeyCap, unit: float, pulse: float) -> None:
        rect = self._cell(cap)
        radius = CORNER * unit
        state = self._states.get(cap.key, KeyState.IDLE)
        base = theme.bank_color(cap.key)

        fill, border, text_color, glow = self._colors_for(state, base, pulse)

        if glow > 0.02:
            self._paint_glow(painter, rect, radius, QColor(border), glow, unit)

        painter.setPen(QPen(QColor(border), max(1.2, unit * 0.035)))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, radius, radius)

        if cap is self._hover and state is KeyState.IDLE:
            painter.setPen(Qt.NoPen)
            painter.setBrush(theme.qcolor(base, 0.12))
            painter.drawRoundedRect(rect, radius, radius)

        # Key letter.
        font = QFont(theme.UI_FAMILY.split(",")[0])
        font.setPixelSize(max(10, int(unit * 0.40)))
        font.setWeight(QFont.DemiBold if state is not KeyState.IDLE else QFont.Medium)
        painter.setFont(font)
        painter.setPen(QColor(text_color))

        label_rect = QRectF(rect)
        if self._show_qwerty:
            label_rect.setHeight(rect.height() * 0.68)
        painter.drawText(label_rect, Qt.AlignCenter, cap.label)

        if self._show_qwerty:
            from ..layout import QWERTY_HINTS

            hints = QWERTY_HINTS.get(cap.key, ())
            if hints:
                small = QFont(theme.MONO_FAMILY.split(",")[0])
                small.setPixelSize(max(7, int(unit * 0.20)))
                painter.setFont(small)
                painter.setPen(QColor(theme.TEXT_FAINT))
                hint_rect = QRectF(
                    rect.x(), rect.y() + rect.height() * 0.62,
                    rect.width(), rect.height() * 0.32,
                )
                painter.drawText(hint_rect, Qt.AlignCenter, " ".join(hints))

    def _colors_for(self, state: KeyState, base: str, pulse: float):
        """(fill, border, text, glow strength) for a key in a given state."""
        if state is KeyState.IDLE:
            return (
                theme.qcolor(theme.BG_RAISED),
                QColor(theme.BORDER),
                QColor(theme.TEXT_FAINT),
                0.0,
            )
        if state is KeyState.EXPECTED:
            strength = 0.55 + 0.45 * pulse
            return (
                theme.qcolor(base, 0.20 + 0.18 * pulse),
                theme.mix(theme.BORDER, base, strength),
                QColor(base),
                0.35 + 0.35 * pulse,
            )
        if state is KeyState.CORRECT:
            return (
                theme.qcolor(theme.SUCCESS, 0.30),
                QColor(theme.SUCCESS),
                QColor(theme.SUCCESS),
                0.45,
            )
        if state is KeyState.EXTRA or state is KeyState.SWAP_FROM:
            return (
                theme.qcolor(theme.ERROR, 0.28),
                QColor(theme.ERROR),
                QColor(theme.ERROR),
                0.45,
            )
        if state is KeyState.MISSED or state is KeyState.SWAP_TO:
            strength = 0.6 + 0.4 * pulse
            return (
                theme.qcolor(theme.WARNING, 0.14 + 0.16 * pulse),
                theme.mix(theme.BORDER, theme.WARNING, strength),
                QColor(theme.WARNING),
                0.30 + 0.35 * pulse,
            )
        return (
            theme.qcolor(theme.BG_RAISED),
            QColor(theme.BORDER),
            QColor(theme.TEXT_FAINT),
            0.0,
        )

    def _paint_glow(
        self, painter: QPainter, rect: QRectF, radius: float,
        color: QColor, strength: float, unit: float,
    ) -> None:
        """Concentric translucent outlines, which reads as a soft glow without a blur pass."""
        painter.setBrush(Qt.NoBrush)
        layers = 4
        for i in range(layers, 0, -1):
            spread = unit * 0.055 * i
            alpha = strength * 0.16 * (1 - (i - 1) / layers)
            pen_color = QColor(color)
            pen_color.setAlphaF(min(0.55, max(0.0, alpha)))
            painter.setPen(QPen(pen_color, unit * 0.10))
            painter.drawRoundedRect(
                rect.adjusted(-spread, -spread, spread, spread),
                radius + spread, radius + spread,
            )

    def _paint_swap_arc(
        self, painter: QPainter, from_key: str, to_key: str, unit: float, pulse: float,
    ) -> None:
        """Draw an arc from the key that was pressed to the key that was wanted."""
        from_caps = [c for c in KEYCAPS if c.key == from_key]
        to_caps = [c for c in KEYCAPS if c.key == to_key]
        if not from_caps or not to_caps:
            return

        # With paired keys (both S, both stars) pick the closest pair so the arc is short.
        best = min(
            ((f, t) for f in from_caps for t in to_caps),
            key=lambda pair: abs(pair[0].col - pair[1].col) + abs(pair[0].row - pair[1].row),
        )
        # Run the arc between the top edges of the two keys rather than their centres, so
        # the arrowhead lands on the target key without covering its letter.
        from_cell, to_cell = self._cell(best[0]), self._cell(best[1])
        start = QPointF(from_cell.center().x(), from_cell.top() - unit * 0.04)
        end = QPointF(to_cell.center().x(), to_cell.top() - unit * 0.04)

        # Bow the arc upward, clear of the keycaps.
        lift = unit * (0.55 + 0.30 * abs(best[0].col - best[1].col) / GRID_COLS)
        control = QPointF((start.x() + end.x()) / 2, min(start.y(), end.y()) - lift)

        path = QPainterPath(start)
        path.quadTo(control, end)

        color = QColor(theme.WARNING)
        color.setAlphaF(0.45 + 0.35 * pulse)
        pen = QPen(color, max(1.6, unit * 0.055))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # Arrowhead at the key that should have been pressed.
        tangent = QPointF(end.x() - control.x(), end.y() - control.y())
        length = math.hypot(tangent.x(), tangent.y()) or 1.0
        ux, uy = tangent.x() / length, tangent.y() / length
        size = unit * 0.20
        left = QPointF(end.x() - ux * size - uy * size * 0.55,
                       end.y() - uy * size + ux * size * 0.55)
        right = QPointF(end.x() - ux * size + uy * size * 0.55,
                        end.y() - uy * size - ux * size * 0.55)
        head = QPainterPath(end)
        head.lineTo(left)
        head.lineTo(right)
        head.closeSubpath()
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawPath(head)
