"""A free-play board.

Click keys to build a chord, or press them on the TinyMod4, and see the outline plus what
your dictionary would write. Doubles as the connection test: if strokes appear here, the
serial link is working.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..protocol import format_stroke, sort_keys
from ..widgets.common import Card, StatusPill, faint, heading, mono_label
from ..widgets.keyboard import StenoKeyboard


class ExploreScreen(QWidget):
    """Tap the board, or use the device, and see what each chord writes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dictionary = None
        self._chord: set[str] = set()
        self._history: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(14)

        layout.addWidget(heading("Explore the board"))
        layout.addWidget(
            faint("Click keys to build a chord, or press them on your TinyMod4. Strokes from "
                  "the device show up here too, which makes this a quick connection test.")
        )

        self.keyboard = StenoKeyboard(interactive=True)
        self.keyboard.key_clicked.connect(self._toggle_key)
        layout.addWidget(self.keyboard, stretch=1)

        readout = Card(padding=18)
        self.outline_label = mono_label("—", "OutlineLarge", theme.ACCENT)
        self.translation_label = QLabel("Build a chord to see what it writes")
        self.translation_label.setObjectName("Translation")
        self.translation_label.setAlignment(Qt.AlignCenter)
        self.keys_label = faint("")
        self.keys_label.setAlignment(Qt.AlignCenter)

        readout.body.addWidget(self.outline_label)
        readout.body.addWidget(self.translation_label)
        readout.body.addWidget(self.keys_label)
        layout.addWidget(readout)

        self.history_label = faint("")
        self.history_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.history_label)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.status = StatusPill()
        self.qwerty_check = QCheckBox("Show QWERTY equivalents")
        self.qwerty_check.toggled.connect(self.keyboard.set_qwerty_labels)
        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self._clear)
        footer.addWidget(self.status, stretch=1)
        footer.addWidget(self.qwerty_check)
        footer.addWidget(clear_button)
        layout.addLayout(footer)

    def set_dictionary(self, dictionary) -> None:
        self._dictionary = dictionary

    def set_status(self, state: str, message: str) -> None:
        self.status.set_status(state, message)

    # ---- interaction --------------------------------------------------------------

    def _toggle_key(self, key: str) -> None:
        if key in self._chord:
            self._chord.discard(key)
        else:
            self._chord.add(key)
        self._refresh()

    def show_stroke(self, keys: set[str]) -> None:
        """A chord arrived from the hardware."""
        self._chord = set(keys)
        self._refresh(from_device=True)

    def _clear(self) -> None:
        self._chord = set()
        self._history.clear()
        self.history_label.setText("")
        self._refresh()

    def _refresh(self, from_device: bool = False) -> None:
        if not self._chord:
            self.keyboard.clear()
            self.outline_label.setText("—")
            self.translation_label.setText("Build a chord to see what it writes")
            self.translation_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
            self.keys_label.setText("")
            return

        outline = format_stroke(self._chord)
        self.keyboard.show_chord(self._chord)
        self.outline_label.setText(outline)
        self.keys_label.setText("  ".join(sort_keys(self._chord)))

        translation = self._dictionary.lookup(outline) if self._dictionary else None
        if translation:
            self.translation_label.setText(f"“{translation}”")
            self.translation_label.setStyleSheet(f"color: {theme.SUCCESS};")
        else:
            self.translation_label.setText("not in your dictionary")
            self.translation_label.setStyleSheet(f"color: {theme.TEXT_FAINT};")

        if from_device:
            self._history.append(outline)
            self.history_label.setText("  ".join(self._history[-12:]))
