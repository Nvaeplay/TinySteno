"""The editable board layout: keys you can drag, over a photo you can trace.

This is the half of the board designer that is direct manipulation. The photo sits behind
the keys in the same key-pitch coordinate space the profile uses, so dragging a key onto
the picture of a switch is the same act as writing its coordinates -- which is the point,
because nobody wants to type twenty-five pairs of numbers.

Selection is deliberately a set rather than a single key. Most of the work of matching a
layout to real hardware is moving a whole bank or a whole row at once, and doing that one
key at a time loses the even spacing that made it a bank in the first place.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import theme
from ..board import BoardProfile, ProfileKey

HANDLE = 9.0        # Resize grip, in pixels.
PADDING = 0.6       # Blank space kept around the layout, in key-pitch units.
MIN_SIZE = 0.25     # Smallest a key may be dragged to, in key-pitch units.


@dataclass
class EditKey:
    """A key being edited. The profile's own ProfileKey is frozen, this one is not."""

    key: str
    label: str
    col: float
    row: float
    width: float = 1.0
    height: float = 1.0
    switch: str = ""
    finger: str = ""
    inferred: bool = False   # Detected from a gap rather than a keycap; worth flagging.

    @classmethod
    def from_profile_key(cls, key: ProfileKey) -> "EditKey":
        return cls(
            key=key.key, label=key.label, col=key.col, row=key.row,
            width=key.width, height=key.height, switch=key.switch, finger=key.finger,
        )

    def to_profile_key(self) -> ProfileKey:
        return ProfileKey(
            key=self.key, label=self.label or self.key.strip("-"),
            col=round(self.col, 3), row=round(self.row, 3),
            width=round(self.width, 3), height=round(self.height, 3),
            switch=self.switch, finger=self.finger,
        )

    @property
    def centre(self) -> tuple[float, float]:
        return (self.col + self.width / 2, self.row + self.height / 2)


class _Drag:
    NONE = "none"
    MOVE = "move"
    RESIZE = "resize"
    BAND = "band"
    PHOTO_MOVE = "photo_move"
    PHOTO_SCALE = "photo_scale"


class LayoutCanvas(QWidget):
    """Drag keys around over a traced photo."""

    selection_changed = Signal()
    layout_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(320)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        self._keys: list[EditKey] = []
        self._selected: set[int] = set()
        self._hover: int | None = None

        self._photo: QPixmap | None = None
        self._photo_rect = QRectF(0, 0, 10, 4)   # In key-pitch units.
        self._photo_opacity = 0.55
        self._photo_visible = True
        self._photo_mode = False

        self._snap = 0.05
        self._drag = _Drag.NONE
        self._drag_origin = QPointF()
        self._band = QRectF()
        self._before: list[EditKey] = []
        self._photo_before = QRectF()

    # ---- contents -------------------------------------------------------------------

    @property
    def keys(self) -> list[EditKey]:
        return self._keys

    def set_keys(self, keys: list[EditKey]) -> None:
        self._keys = keys
        self._selected.clear()
        self._hover = None
        self.selection_changed.emit()
        self.layout_changed.emit()
        self.update()

    def load_profile(self, profile: BoardProfile) -> None:
        self.set_keys([EditKey.from_profile_key(key) for key in profile.keys])

    def to_profile_keys(self) -> tuple[ProfileKey, ...]:
        return tuple(key.to_profile_key() for key in self._keys)

    def set_photo(self, pixmap: QPixmap | None, rect: QRectF | None = None) -> None:
        self._photo = pixmap
        if pixmap is not None and rect is not None:
            self._photo_rect = QRectF(rect)
        elif pixmap is not None:
            self.fit_photo()
        self.update()

    @property
    def photo(self) -> QPixmap | None:
        return self._photo

    def fit_photo(self) -> None:
        """Scale the photo to sit behind the current keys, keeping its aspect ratio."""
        if self._photo is None:
            return
        bounds = self._key_bounds()
        if bounds.isEmpty():
            bounds = QRectF(0, 0, 10, 4)
        ratio = self._photo.height() / max(1, self._photo.width())
        width = bounds.width()
        height = width * ratio
        self._photo_rect = QRectF(
            bounds.x(), bounds.center().y() - height / 2, width, height
        )
        self.update()

    def set_photo_opacity(self, value: float) -> None:
        self._photo_opacity = max(0.0, min(1.0, value))
        self.update()

    def set_photo_visible(self, visible: bool) -> None:
        self._photo_visible = visible
        self.update()

    def set_photo_mode(self, enabled: bool) -> None:
        """Drag the photo instead of the keys, to line the backdrop up under them."""
        self._photo_mode = enabled
        self.update()

    def set_snap(self, step: float) -> None:
        self._snap = max(0.0, step)

    @property
    def snap(self) -> float:
        return self._snap

    # ---- selection ------------------------------------------------------------------

    @property
    def selected_indexes(self) -> list[int]:
        return sorted(self._selected)

    def selected_keys(self) -> list[EditKey]:
        return [self._keys[i] for i in self.selected_indexes]

    def select(self, indexes) -> None:
        self._selected = {i for i in indexes if 0 <= i < len(self._keys)}
        self.selection_changed.emit()
        self.update()

    def select_all(self) -> None:
        self.select(range(len(self._keys)))

    def update_selected(self, **changes) -> None:
        """Apply field changes to every selected key."""
        if not self._selected:
            return
        for index in self._selected:
            self._keys[index] = replace(self._keys[index], **changes)
        self.layout_changed.emit()
        self.update()

    # ---- editing --------------------------------------------------------------------

    def add_key(self, col: float, row: float, key: str = "S-") -> None:
        self._keys.append(
            EditKey(key=key, label=key.strip("-"), col=self._round(col), row=self._round(row))
        )
        self.select([len(self._keys) - 1])
        self.layout_changed.emit()
        self.update()

    def delete_selected(self) -> None:
        if not self._selected:
            return
        self._keys = [
            key for index, key in enumerate(self._keys) if index not in self._selected
        ]
        self._selected.clear()
        self.selection_changed.emit()
        self.layout_changed.emit()
        self.update()

    def duplicate_selected(self) -> None:
        if not self._selected:
            return
        added = []
        for index in self.selected_indexes:
            copy = replace(self._keys[index], col=self._keys[index].col + 1, inferred=False)
            self._keys.append(copy)
            added.append(len(self._keys) - 1)
        self.select(added)
        self.layout_changed.emit()
        self.update()

    def nudge(self, dx: float, dy: float) -> None:
        for index in self._selected:
            key = self._keys[index]
            self._keys[index] = replace(key, col=key.col + dx, row=key.row + dy)
        if self._selected:
            self.layout_changed.emit()
            self.update()

    def align_selected_rows(self) -> None:
        """Put every selected key on one row, at one height. Straightens a traced row."""
        keys = self.selected_keys()
        if len(keys) < 2:
            return
        top = self._round(sum(key.row for key in keys) / len(keys))
        height = self._round(sum(key.height for key in keys) / len(keys))
        self.update_selected(row=top, height=height)

    def space_selected_evenly(self) -> None:
        """Spread the selection horizontally at an even pitch, outermost keys held fixed."""
        indexes = sorted(self._selected, key=lambda i: self._keys[i].col)
        if len(indexes) < 3:
            return
        first, last = self._keys[indexes[0]], self._keys[indexes[-1]]
        step = (last.col - first.col) / (len(indexes) - 1)
        for position, index in enumerate(indexes):
            self._keys[index] = replace(
                self._keys[index], col=self._round(first.col + position * step)
            )
        self.layout_changed.emit()
        self.update()

    def normalise(self) -> None:
        """Move the layout so its top-left corner is the origin.

        Coordinates from a photo start wherever the board happened to sit in the frame.
        Pulling them back to zero keeps exported profiles comparable with the built-in
        ones, and stops the renderer wasting a margin on empty space.
        """
        if not self._keys:
            return
        bounds = self._key_bounds()
        dx, dy = -bounds.x(), -bounds.y()
        self._keys = [
            replace(key, col=self._round(key.col + dx), row=self._round(key.row + dy))
            for key in self._keys
        ]
        self._photo_rect.translate(dx, dy)
        self.layout_changed.emit()
        self.update()

    def _round(self, value: float) -> float:
        if self._snap <= 0:
            return round(value, 3)
        return round(round(value / self._snap) * self._snap, 3)

    # ---- geometry -------------------------------------------------------------------

    def _key_bounds(self) -> QRectF:
        if not self._keys:
            return QRectF()
        left = min(key.col for key in self._keys)
        top = min(key.row for key in self._keys)
        right = max(key.col + key.width for key in self._keys)
        bottom = max(key.row + key.height for key in self._keys)
        return QRectF(left, top, right - left, bottom - top)

    def _content_bounds(self) -> QRectF:
        bounds = self._key_bounds()
        if self._photo is not None and self._photo_visible:
            bounds = self._photo_rect if bounds.isEmpty() else bounds.united(self._photo_rect)
        if bounds.isEmpty():
            bounds = QRectF(0, 0, 10, 4)
        return bounds.adjusted(-PADDING, -PADDING, PADDING, PADDING)

    def _unit(self) -> float:
        bounds = self._content_bounds()
        return min(
            self.width() / max(bounds.width(), 0.001),
            self.height() / max(bounds.height(), 0.001),
        )

    def _origin(self) -> QPointF:
        bounds = self._content_bounds()
        unit = self._unit()
        return QPointF(
            (self.width() - bounds.width() * unit) / 2 - bounds.x() * unit,
            (self.height() - bounds.height() * unit) / 2 - bounds.y() * unit,
        )

    def _to_pixels(self, rect: QRectF) -> QRectF:
        unit = self._unit()
        origin = self._origin()
        return QRectF(
            origin.x() + rect.x() * unit, origin.y() + rect.y() * unit,
            rect.width() * unit, rect.height() * unit,
        )

    def _cell(self, key: EditKey) -> QRectF:
        return self._to_pixels(QRectF(key.col, key.row, key.width, key.height))

    def _to_units(self, point: QPointF) -> QPointF:
        unit = self._unit()
        origin = self._origin()
        return QPointF((point.x() - origin.x()) / unit, (point.y() - origin.y()) / unit)

    def _handle_rect(self, rect: QRectF) -> QRectF:
        return QRectF(
            rect.right() - HANDLE / 2, rect.bottom() - HANDLE / 2, HANDLE, HANDLE
        )

    def _key_at(self, point: QPointF) -> int | None:
        # Topmost first, so a key dropped on top of another can be picked up again.
        for index in reversed(range(len(self._keys))):
            if self._cell(self._keys[index]).contains(point):
                return index
        return None

    # ---- mouse ----------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        self.setFocus()
        position = event.position()
        self._drag_origin = position
        self._before = [replace(key) for key in self._keys]
        self._photo_before = QRectF(self._photo_rect)

        if self._photo_mode and self._photo is not None:
            photo = self._to_pixels(self._photo_rect)
            self._drag = (
                _Drag.PHOTO_SCALE if self._handle_rect(photo).contains(position)
                else _Drag.PHOTO_MOVE
            )
            return

        if len(self._selected) == 1:
            only = self._cell(self._keys[next(iter(self._selected))])
            if self._handle_rect(only).contains(position):
                self._drag = _Drag.RESIZE
                return

        index = self._key_at(position)
        additive = bool(event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier))

        if index is None:
            if not additive:
                self.select([])
            self._drag = _Drag.BAND
            self._band = QRectF(position, position)
            return

        if additive:
            self._selected.symmetric_difference_update({index})
            self.selection_changed.emit()
        elif index not in self._selected:
            self.select([index])
        self._drag = _Drag.MOVE
        self.update()

    def mouseMoveEvent(self, event) -> None:
        position = event.position()

        if self._drag == _Drag.NONE:
            hover = self._key_at(position)
            if hover != self._hover:
                self._hover = hover
                self.setCursor(Qt.OpenHandCursor if hover is not None else Qt.ArrowCursor)
                self.update()
            return

        unit = self._unit()
        dx = (position.x() - self._drag_origin.x()) / unit
        dy = (position.y() - self._drag_origin.y()) / unit

        if self._drag == _Drag.BAND:
            self._band = QRectF(self._drag_origin, position).normalized()
            self.update()
            return

        if self._drag == _Drag.PHOTO_MOVE:
            self._photo_rect = self._photo_before.translated(dx, dy)
            self.update()
            return

        if self._drag == _Drag.PHOTO_SCALE:
            ratio = self._photo_before.height() / max(0.001, self._photo_before.width())
            width = max(1.0, self._photo_before.width() + dx)
            self._photo_rect = QRectF(
                self._photo_before.x(), self._photo_before.y(), width, width * ratio
            )
            self.update()
            return

        if self._drag == _Drag.RESIZE:
            index = next(iter(self._selected))
            original = self._before[index]
            self._keys[index] = replace(
                original,
                width=max(MIN_SIZE, self._round(original.width + dx)),
                height=max(MIN_SIZE, self._round(original.height + dy)),
            )
            self.layout_changed.emit()
            self.update()
            return

        if self._drag == _Drag.MOVE and self._selected:
            # Snap the key under the cursor and move the rest by the same amount, so a
            # selection keeps its internal spacing instead of collapsing onto the grid.
            anchor = self._before[min(self._selected)]
            snapped_dx = self._round(anchor.col + dx) - anchor.col
            snapped_dy = self._round(anchor.row + dy) - anchor.row
            for index in self._selected:
                original = self._before[index]
                self._keys[index] = replace(
                    original,
                    col=round(original.col + snapped_dx, 3),
                    row=round(original.row + snapped_dy, 3),
                )
            self.layout_changed.emit()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag == _Drag.BAND:
            hits = [
                index for index, key in enumerate(self._keys)
                if self._band.intersects(self._cell(key))
            ]
            additive = bool(event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier))
            self.select(set(hits) | (self._selected if additive else set()))
            self._band = QRectF()
        self._drag = _Drag.NONE
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        if self._key_at(event.position()) is None and not self._photo_mode:
            point = self._to_units(event.position())
            self.add_key(point.x() - 0.5, point.y() - 0.5)

    # ---- keyboard -------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        step = self._snap if self._snap > 0 else 0.05
        if event.modifiers() & Qt.ShiftModifier:
            step *= 5

        moves = {
            Qt.Key_Left: (-step, 0.0), Qt.Key_Right: (step, 0.0),
            Qt.Key_Up: (0.0, -step), Qt.Key_Down: (0.0, step),
        }
        if event.key() in moves and self._selected:
            self.nudge(*moves[event.key()])
        elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
        elif event.key() == Qt.Key_A and event.modifiers() & Qt.ControlModifier:
            self.select_all()
        elif event.key() == Qt.Key_D and event.modifiers() & Qt.ControlModifier:
            self.duplicate_selected()
        else:
            super().keyPressEvent(event)

    # ---- painting -------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        unit = self._unit()

        if self._photo is not None and self._photo_visible:
            painter.setOpacity(self._photo_opacity)
            painter.drawPixmap(self._to_pixels(self._photo_rect), self._photo,
                               QRectF(self._photo.rect()))
            painter.setOpacity(1.0)
            if self._photo_mode:
                rect = self._to_pixels(self._photo_rect)
                painter.setPen(QPen(QColor(theme.ACCENT), 1.4, Qt.DashLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(rect)
                self._paint_handle(painter, self._handle_rect(rect))

        self._paint_grid(painter, unit)

        for index, key in enumerate(self._keys):
            self._paint_key(painter, index, key, unit)

        if not self._band.isEmpty():
            painter.setPen(QPen(QColor(theme.ACCENT), 1.2, Qt.DashLine))
            painter.setBrush(theme.qcolor(theme.ACCENT, 0.10))
            painter.drawRect(self._band)

        painter.end()

    def _paint_grid(self, painter: QPainter, unit: float) -> None:
        """A faint one-unit grid, so key pitch is something you can see rather than count."""
        if unit < 14:
            return
        bounds = self._content_bounds()
        painter.setPen(QPen(theme.qcolor(theme.BORDER_SOFT, 0.55), 1.0))
        start_x = int(bounds.x() // 1)
        start_y = int(bounds.y() // 1)
        for step in range(start_x, int(bounds.right()) + 1):
            x = self._to_pixels(QRectF(step, 0, 0, 0)).x()
            painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        for step in range(start_y, int(bounds.bottom()) + 1):
            y = self._to_pixels(QRectF(0, step, 0, 0)).y()
            painter.drawLine(QPointF(0, y), QPointF(self.width(), y))

    def _paint_key(self, painter: QPainter, index: int, key: EditKey, unit: float) -> None:
        rect = self._cell(key)
        radius = 0.16 * unit
        selected = index in self._selected
        base = theme.bank_color(key.key) if key.key else theme.TEXT_FAINT

        fill = theme.qcolor(base, 0.30 if selected else 0.16)
        border = QColor(theme.ACCENT) if selected else theme.mix(theme.BORDER, base, 0.55)

        painter.setBrush(fill)
        painter.setPen(QPen(border, 2.0 if selected else 1.2))
        painter.drawRoundedRect(rect, radius, radius)

        if key.inferred and not selected:
            # A key the detector invented to fill a gap. Dashed, because it is the one
            # thing on screen that was never actually seen in the photo.
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(theme.WARNING), 1.4, Qt.DashLine))
            painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), radius, radius)

        if index == self._hover and not selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(theme.qcolor(base, 0.12))
            painter.drawRoundedRect(rect, radius, radius)

        font = QFont(theme.UI_FAMILY.split(",")[0])
        font.setPixelSize(max(8, int(min(unit, rect.height()) * 0.38)))
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(base))
        painter.drawText(rect, Qt.AlignCenter, key.label or "?")

        if selected and len(self._selected) == 1:
            self._paint_handle(painter, self._handle_rect(rect))

    def _paint_handle(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(QPen(QColor(theme.BG), 1.0))
        painter.setBrush(QColor(theme.ACCENT))
        painter.drawRect(rect)
