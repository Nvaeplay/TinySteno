"""Small shared building blocks."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..machine import State


class Card(QFrame):
    """A padded panel with a soft border."""

    def __init__(self, parent: QWidget | None = None, padding: int = 20) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setSpacing(12)
        self.body = layout


class StatTile(QFrame):
    """One number with a caption under it."""

    def __init__(self, caption: str, value: str = "—", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(2)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("TileValue")

        self.caption_label = QLabel(caption)
        self.caption_label.setObjectName("Faint")

        layout.addWidget(self.value_label)
        layout.addWidget(self.caption_label)

    def set_value(self, value: str, color: str | None = None) -> None:
        self.value_label.setText(value)
        self.value_label.setStyleSheet(f"color: {color};" if color else "")


class StatusPill(QWidget):
    """Connection state: a coloured dot and a short message."""

    _COLORS = {
        State.CONNECTED: theme.SUCCESS,
        State.CONNECTING: theme.WARNING,
        State.PORT_BUSY: theme.WARNING,
        State.ERROR: theme.ERROR,
        State.DISCONNECTED: theme.TEXT_FAINT,
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {theme.TEXT_FAINT}; font-size: 12px;")
        self.text = QLabel("Not connected")
        self.text.setObjectName("Faint")

        layout.addWidget(self.dot)
        layout.addWidget(self.text)
        layout.addStretch()

    def set_status(self, state: str, message: str) -> None:
        color = self._COLORS.get(state, theme.TEXT_FAINT)
        self.dot.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.text.setText(message)
        self.text.setStyleSheet(
            f"color: {color if state in (State.ERROR, State.PORT_BUSY) else theme.TEXT_FAINT};"
            f" font-size: 12px;"
        )


class StrokeDots(QWidget):
    """Progress through a multi-stroke outline: one dot per stroke."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(7)
        self._layout.setAlignment(Qt.AlignCenter)
        self._dots: list[QLabel] = []

    def set_progress(self, total: int, done: int) -> None:
        while len(self._dots) < total:
            dot = QLabel("●")
            dot.setStyleSheet("font-size: 9px;")
            self._dots.append(dot)
            self._layout.addWidget(dot)
        for index, dot in enumerate(self._dots):
            dot.setVisible(index < total and total > 1)
            if index < done:
                dot.setStyleSheet(f"color: {theme.SUCCESS}; font-size: 9px;")
            elif index == done:
                dot.setStyleSheet(f"color: {theme.ACCENT}; font-size: 9px;")
            else:
                dot.setStyleSheet(f"color: {theme.BORDER}; font-size: 9px;")


def heading(text: str, level: int = 1) -> QLabel:
    label = QLabel(text)
    label.setObjectName("H1" if level == 1 else "H2")
    return label


def dim(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Dim")
    label.setWordWrap(True)
    return label


def faint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Faint")
    label.setWordWrap(True)
    return label


def mono_label(text: str = "", object_name: str = "Mono", color: str = theme.TEXT) -> QLabel:
    """A monospaced label. Sizing comes from the stylesheet rule for `object_name`."""
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setStyleSheet(f"color: {color};")
    label.setAlignment(Qt.AlignCenter)
    return label


def hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"color: {theme.BORDER_SOFT}; background: {theme.BORDER_SOFT};")
    line.setFixedHeight(1)
    return line
