"""The on-screen steno board.

Draws whatever board profile it is given: key positions, sizes and the gap between banks
all come from the profile in key-pitch units, so nothing here is specific to one keyboard.

Shows the chord to press, then shows what actually happened. When a key was pressed on the
wrong side of the board, the two keys involved are joined by an arc so the swap is visible
at a glance rather than something to work out from two lists of key names.
"""

from __future__ import annotations

import math
from enum import Enum

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import fingering, theme
from ..board import BoardProfile, ProfileKey
from ..layout import QWERTY_HINTS

KEY_INSET = 0.06   # Padding inside each key's cell, so keys do not touch.
CORNER = 0.16      # Corner radius as a fraction of key size.


class KeyState(Enum):
    IDLE = "idle"
    EXPECTED = "expected"    # Part of the chord to press
    CORRECT = "correct"      # Pressed, and it belonged
    EXTRA = "extra"          # Pressed, but it did not belong
    MISSED = "missed"        # Belonged, but was not pressed
    SWAP_FROM = "swap_from"  # Pressed here, should have been the mirror key
    SWAP_TO = "swap_to"      # The mirror key that was wanted


class StenoKeyboard(QWidget):
    """A painted steno board that can display a chord and critique an attempt."""

    key_clicked = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        interactive: bool = False,
        profile: BoardProfile | None = None,
    ) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(190)
        self.setMouseTracking(True)

        self._interactive = interactive
        self._profile = profile
        self._expected: set[str] = set()
        self._states: dict[str, KeyState] = {}
        self._swap_arcs: list[tuple[str, str]] = []
        self._hover: ProfileKey | None = None
        self._show_qwerty = False
        self._finger_mode = False
        self._seam_mode = False

        # Cached derived state. Both were being rebuilt from scratch on every frame of a
        # 30 fps animation, and the geometry on every mouse-move as well.
        self._geom: tuple[float, QPointF] | None = None
        self._fonts: dict[tuple[str, int, int], QFont] = {}
        self._ui_family = theme.UI_FAMILY.split(",")[0]
        self._mono_family = theme.MONO_FAMILY.split(",")[0]

        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    # ---- public API ---------------------------------------------------------------

    def set_profile(self, profile: BoardProfile) -> None:
        self._profile = profile
        self._geom = None
        self._hover = None
        self.update()

    @property
    def profile(self) -> BoardProfile | None:
        return self._profile

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

    def set_finger_colors(self, enabled: bool) -> None:
        """Tint resting keys by the finger that owns them."""
        self._finger_mode = enabled
        self.update()

    def set_seam_hints(self, enabled: bool) -> None:
        """Mark where each finger rests: in the seam between the two rows, not on a key."""
        self._seam_mode = enabled
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

    def hideEvent(self, event) -> None:
        """Stop animating a board nobody can see.

        Qt does not paint a hidden widget, so this costs no frames -- but all three
        StenoKeyboards live for the whole session in a QStackedWidget, and without this
        every one of them keeps waking the event loop 30 times a second whether or not it
        is the screen you are looking at.
        """
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        self._ensure_animation()
        super().showEvent(event)

    def _pulse(self) -> float:
        """A gentle 0..1 breathing value."""
        return 0.5 + 0.5 * math.sin(self._phase * math.pi)

    # ---- geometry -----------------------------------------------------------------

    def _keys(self) -> tuple[ProfileKey, ...]:
        return self._profile.keys if self._profile else ()

    def _font(self, family: str, pixel_size: int, weight) -> QFont:
        """A QFont from the cache. Building one per key per frame is not free."""
        key = (family, pixel_size, int(weight))
        font = self._fonts.get(key)
        if font is None:
            font = QFont(family)
            font.setPixelSize(pixel_size)
            font.setWeight(weight)
            self._fonts[key] = font
        return font

    def _geometry(self) -> tuple[float, QPointF]:
        """Pixels per key pitch, and the board's top-left corner. Cached.

        `BoardProfile.width` and `.height` are `max(...)` generators over the whole key
        tuple, and `_cell()` used to reach them six times per call -- so hit-testing one
        24-key board cost about 3,500 generator steps, on every mouse-move event. None of
        it can change unless the widget resizes or the profile is swapped, so it is
        computed once and invalidated in exactly those two places.
        """
        if self._geom is None:
            if not self._profile:
                self._geom = (1.0, QPointF(0, 0))
            else:
                board_w, board_h = self._profile.width, self._profile.height
                unit = min(
                    self.width() / max(board_w, 0.001),
                    self.height() / max(board_h, 0.001),
                )
                self._geom = (
                    unit,
                    QPointF(
                        (self.width() - board_w * unit) / 2,
                        (self.height() - board_h * unit) / 2,
                    ),
                )
        return self._geom

    def _unit(self) -> float:
        """Pixels per key pitch, sized to fit the profile's extents."""
        return self._geometry()[0]

    def _origin(self) -> QPointF:
        return self._geometry()[1]

    def resizeEvent(self, event) -> None:
        self._geom = None
        super().resizeEvent(event)

    def _cell(self, key: ProfileKey) -> QRectF:
        unit, origin = self._geometry()
        inset = KEY_INSET * unit
        return QRectF(
            origin.x() + key.col * unit + inset,
            origin.y() + key.row * unit + inset,
            key.width * unit - inset * 2,
            key.height * unit - inset * 2,
        )

    def _point(self, x: float, y: float) -> QPointF:
        """Convert key-pitch coordinates to widget pixels."""
        unit, origin = self._geometry()
        return QPointF(origin.x() + x * unit, origin.y() + y * unit)

    def _key_at(self, pos) -> ProfileKey | None:
        for key in self._keys():
            if self._cell(key).contains(pos):
                return key
        return None

    # ---- events -------------------------------------------------------------------

    def mouseMoveEvent(self, event) -> None:
        key = self._key_at(event.position())
        if key is not self._hover:
            self._hover = key
            self.setCursor(
                Qt.PointingHandCursor if (key and self._interactive) else Qt.ArrowCursor
            )
            if key:
                finger = fingering.finger_for_profile_key(key)
                hint = f"  ·  {finger.label}" if finger else ""
                self.setToolTip(f"{key.key}{hint}")
            self.update()

    def leaveEvent(self, event) -> None:
        self._hover = None
        self.update()

    def mousePressEvent(self, event) -> None:
        key = self._key_at(event.position())
        if key and self._interactive:
            self.key_clicked.emit(key.key)

    # ---- painting -----------------------------------------------------------------

    def paintEvent(self, event) -> None:
        if not self._profile:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        unit = self._unit()
        pulse = self._pulse()

        for key in self._keys():
            self._paint_key(painter, key, unit, pulse)

        if self._seam_mode:
            self._paint_seams(painter, unit)

        for from_key, to_key in self._swap_arcs:
            self._paint_swap_arc(painter, from_key, to_key, unit, pulse)

        painter.end()

    def _paint_key(
        self, painter: QPainter, key: ProfileKey, unit: float, pulse: float
    ) -> None:
        rect = self._cell(key)
        radius = CORNER * unit
        state = self._states.get(key.key, KeyState.IDLE)

        # In finger mode the whole board speaks in finger colours rather than bank colours,
        # so a highlighted key matches its row in the legend.
        base = theme.bank_color(key.key)
        if self._finger_mode:
            finger = fingering.finger_for_profile_key(key)
            # A key with no standard finger (the number bar) stays neutral rather than
            # borrowing a colour that would imply an assignment we are not making.
            base = finger.color if finger is not None else theme.TEXT_FAINT

        fill, border, text_color, glow = self._colors_for(state, base, pulse)

        if state is KeyState.IDLE and self._finger_mode:
            fill = theme.qcolor(base, 0.14)
            border = theme.mix(theme.BORDER, base, 0.55)
            text_color = QColor(base)

        if glow > 0.02:
            self._paint_glow(painter, rect, radius, QColor(border), glow, unit)

        painter.setPen(QPen(QColor(border), max(1.2, unit * 0.035)))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, radius, radius)

        if key is self._hover and state is KeyState.IDLE:
            painter.setPen(Qt.NoPen)
            painter.setBrush(theme.qcolor(base, 0.12))
            painter.drawRoundedRect(rect, radius, radius)

        # Key letter.
        painter.setFont(self._font(
            self._ui_family,
            max(9, int(min(unit, rect.height()) * 0.40)),
            QFont.DemiBold if state is not KeyState.IDLE else QFont.Medium,
        ))
        painter.setPen(QColor(text_color))

        label_rect = QRectF(rect)
        if self._show_qwerty:
            label_rect.setHeight(rect.height() * 0.68)
        painter.drawText(label_rect, Qt.AlignCenter, key.label)

        if self._show_qwerty:
            hints = QWERTY_HINTS.get(key.key, ())
            if hints:
                painter.setFont(self._font(
                    self._mono_family, max(7, int(unit * 0.20)), QFont.Normal
                ))
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

    def _paint_seams(self, painter: QPainter, unit: float) -> None:
        """Draw a fingertip pad at each resting position, derived from the profile."""
        height = unit * 0.20
        for rest in fingering.rest_positions(self._profile):
            centre = self._point(rest.x, rest.y)
            pad = QRectF(
                centre.x() - rest.width * unit * 0.30,
                centre.y() - height / 2,
                rest.width * unit * 0.60,
                height,
            )
            colour = QColor(rest.finger.color)

            if rest.finger.is_shared:
                # The asterisk has no owning hand, so it gets an outline rather than a pad.
                colour.setAlphaF(0.75)
                pen = QPen(colour, max(1.0, unit * 0.030))
                pen.setStyle(Qt.DashLine)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
            else:
                painter.setPen(Qt.NoPen)
                glow = QColor(colour)
                glow.setAlphaF(0.22)
                painter.setBrush(glow)
                painter.drawRoundedRect(
                    pad.adjusted(-unit * 0.05, -unit * 0.05, unit * 0.05, unit * 0.05),
                    height, height,
                )
                colour.setAlphaF(0.92)
                painter.setBrush(colour)
            painter.drawRoundedRect(pad, height / 2, height / 2)

    def _paint_swap_arc(
        self, painter: QPainter, from_key: str, to_key: str, unit: float, pulse: float,
    ) -> None:
        """Draw an arc from the key that was pressed to the key that was wanted."""
        from_keys = [k for k in self._keys() if k.key == from_key]
        to_keys = [k for k in self._keys() if k.key == to_key]
        if not from_keys or not to_keys:
            return

        # With paired keys (both S, both stars) pick the closest pair so the arc is short.
        best = min(
            ((f, t) for f in from_keys for t in to_keys),
            key=lambda pair: abs(pair[0].col - pair[1].col) + abs(pair[0].row - pair[1].row),
        )

        # Run the arc between the top edges of the two keys rather than their centres, so
        # the arrowhead lands on the target key without covering its letter.
        from_cell, to_cell = self._cell(best[0]), self._cell(best[1])
        start = QPointF(from_cell.center().x(), from_cell.top() - unit * 0.04)
        end = QPointF(to_cell.center().x(), to_cell.top() - unit * 0.04)

        # Bow the arc upward, clear of the keycaps.
        spread = abs(best[0].col - best[1].col) / max(self._profile.width, 1.0)
        lift = unit * (0.55 + 0.30 * spread)
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
