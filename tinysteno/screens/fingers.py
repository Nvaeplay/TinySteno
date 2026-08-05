"""The finger placement guide.

Teaches three things, in order of how much they matter:

1. Each finger owns one vertical column.
2. Fingers rest in the *seam* between the two rows, not on a key.
3. Because of (2), one finger can and must hold both keys of its column at once.

Point 3 is the one beginners miss, and it is not optional -- "dog" is TKOG, which needs the
left ring finger on T and K simultaneously.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import fingering, theme
from ..protocol import parse_stroke
from ..widgets.common import Card, faint, heading
from ..widgets.keyboard import StenoKeyboard

# Verified against the built-in lessons: each of these genuinely needs one finger on two
# keys at the same time.
DOUBLE_PRESS_EXAMPLES = (
    ("dog", "TKOG", "left ring holds T and K", "T + K make the D sound"),
    ("big", "PWEUG", "left middle holds P and W", "P + W make the B sound"),
    ("on", "OPB", "right middle holds P and B", "P + B make the N sound"),
    ("lazy", "HRAEZ", "left index holds H and R", "H + R make the L sound"),
)


class FingerRow(QFrame):
    """One clickable line in the legend: swatch, finger, its keys, and a note."""

    clicked = Signal(str)

    def __init__(self, finger: fingering.Finger, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._finger = finger
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(11)

        swatch = QLabel("●")
        swatch.setStyleSheet(f"color: {finger.color}; font-size: 15px;")
        swatch.setFixedWidth(16)

        label = QLabel(finger.label)
        label.setStyleSheet("font-weight: 600;")
        label.setFixedWidth(96)

        keys = QLabel("  ".join(finger.keys))
        keys.setObjectName("Mono")
        keys.setStyleSheet(f"color: {finger.color};")
        keys.setFixedWidth(112)

        note = faint(finger.note)
        note.setWordWrap(True)

        layout.addWidget(swatch)
        layout.addWidget(label)
        layout.addWidget(keys)
        layout.addWidget(note, stretch=1)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._finger.id)

    def enterEvent(self, event) -> None:
        self.setStyleSheet(f"#Card {{ border: 1px solid {self._finger.color}; }}")

    def leaveEvent(self, event) -> None:
        self.setStyleSheet("")


class FingersScreen(QWidget):
    """Where each finger goes, and how to hold your hands."""

    def __init__(self, parent: QWidget | None = None, profile=None) -> None:
        super().__init__(parent)
        self._selected: str | None = None
        self._profile = profile

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(15)
        scroll.setWidget(content)

        layout.addWidget(heading("Finger positions"))
        layout.addWidget(
            faint(
                "Each finger owns one vertical column. This is the standard stenotype "
                "assignment — every major theory teaches the same one, because the layout "
                "does not really allow another. Click any finger below to light its keys."
            )
        )

        # ---- the board ----------------------------------------------------------
        self.keyboard = StenoKeyboard(profile=profile)
        self.keyboard.setMinimumHeight(270)
        self.keyboard.set_finger_colors(True)
        self.keyboard.set_seam_hints(True)
        layout.addWidget(self.keyboard)

        self.board_label = faint("")
        self.board_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.board_label)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.seam_check = QCheckBox("Show where fingers rest")
        self.seam_check.setChecked(True)
        self.seam_check.toggled.connect(self.keyboard.set_seam_hints)
        self.show_all = QPushButton("Clear highlight")
        self.show_all.clicked.connect(self._clear_highlight)
        controls.addWidget(self.seam_check)
        controls.addStretch()
        controls.addWidget(self.show_all)
        layout.addLayout(controls)

        # ---- the seam, which is the whole technique ------------------------------
        seam_card = Card(padding=18)
        seam_title = QLabel("Rest in the seam, not on a key")
        seam_title.setObjectName("H2")
        seam_card.body.addWidget(seam_title)
        seam_card.body.addWidget(
            faint(
                "Your eight non-thumb fingers sit on the line between the top and bottom "
                "rows — the coloured pads above — so that each one can press the upper key, "
                "the lower key, or both at once by flattening slightly. Thumbs rest on the "
                "vowels.\n\n"
                "This is not a stylistic preference. Many sounds are written by pressing "
                "both keys of a column together, and you cannot reach them from a "
                "one-finger-per-key resting position."
            )
        )
        layout.addWidget(seam_card)

        # ---- worked examples -----------------------------------------------------
        examples_card = Card(padding=18)
        examples_title = QLabel("One finger, two keys")
        examples_title.setObjectName("H2")
        examples_card.body.addWidget(examples_title)
        examples_card.body.addWidget(
            faint("Four words from the built-in lessons that are impossible without it:")
        )

        # Each example is its own widget so it can be hidden on a board that lacks the
        # keys the chord needs.
        self._example_rows: list[tuple[QWidget, set[str]]] = []
        for word, outline, action, why in DOUBLE_PRESS_EXAMPLES:
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(9)

            word_label = QLabel(word)
            word_label.setStyleSheet("font-weight: 600;")
            word_label.setFixedWidth(56)

            outline_label = QLabel(outline)
            outline_label.setObjectName("Mono")
            outline_label.setStyleSheet(f"color: {theme.ACCENT};")
            outline_label.setFixedWidth(78)

            action_label = QLabel(action)
            action_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
            action_label.setFixedWidth(196)

            row.addWidget(word_label)
            row.addWidget(outline_label)
            row.addWidget(action_label)
            row.addWidget(faint(why), stretch=1)

            examples_card.body.addWidget(row_widget)
            self._example_rows.append((row_widget, parse_stroke(outline)))

        self.examples_card = examples_card
        layout.addWidget(examples_card)

        # ---- the legend ----------------------------------------------------------
        legend_title = QLabel("Every finger")
        legend_title.setObjectName("H2")
        layout.addWidget(legend_title)

        for finger in fingering.FINGERS:
            row = FingerRow(finger)
            row.clicked.connect(self._highlight_finger)
            layout.addWidget(row)

        # ---- technique -----------------------------------------------------------
        technique = Card(padding=18)
        technique_title = QLabel("How a stroke is made")
        technique_title.setObjectName("H2")
        technique.body.addWidget(technique_title)
        technique.body.addWidget(
            faint(
                "Press every key of the chord down together and release them together. "
                "Press order does not matter and is not recorded — the board sends one "
                "frame when you let go, which is why a stroke either lands whole or not at "
                "all.\n\n"
                "Keep your fingers in contact with the keys between strokes rather than "
                "lifting away. Steno is a light, flat motion from the seam, not the "
                "individual key-hunting of a normal keyboard."
            )
        )
        layout.addWidget(technique)

        caveats = Card(padding=18)
        caveats_title = QLabel("Where there is genuinely no standard")
        caveats_title.setObjectName("H2")
        caveats.body.addWidget(caveats_title)
        caveats_body = QLabel(
            "•  <b>The asterisk.</b> Either index finger reaches in for it. Pick whichever "
            "hand is free in the chord you are writing; there is no accepted rule.<br><br>"
            "•  <b>The right pinky.</b> It is the only finger covering two columns "
            "(T/S and D/Z). Whether you stretch to reach D and Z or shift the whole hand "
            "depends on your hand size.<br><br>"
            "•  <b>Hobbyist boards in particular.</b> A production stenotype has sculpted, "
            "lightly-sprung keys that guide your fingers into the seam. Most DIY boards use "
            "flat, separate keys, so the resting position takes more conscious effort to "
            "hold. Expect that to feel awkward before it feels natural."
        )
        caveats_body.setWordWrap(True)
        caveats_body.setStyleSheet(f"color: {theme.TEXT_DIM};")
        caveats.body.addWidget(caveats_body)
        layout.addWidget(caveats)

        layout.addStretch()

    # ---- board ----------------------------------------------------------------------

    def set_profile(self, profile) -> None:
        self._profile = profile
        self.keyboard.set_profile(profile)
        self._clear_highlight()
        self.board_label.setText(f"Showing the {profile.name} layout")

        # A board without a key cannot demonstrate the chord that needs it.
        shown = 0
        for row_widget, chord in self._example_rows:
            supported = profile.supports(chord)
            row_widget.setVisible(supported)
            shown += supported
        self.examples_card.setVisible(shown > 0)

    # ---- interaction --------------------------------------------------------------

    def _highlight_finger(self, finger_id: str) -> None:
        if self._selected == finger_id:
            self._clear_highlight()
            return
        finger = fingering.FINGERS_BY_ID[finger_id]
        self._selected = finger_id
        self.keyboard.show_chord(finger.keys)

    def _clear_highlight(self) -> None:
        self._selected = None
        self.keyboard.clear()
