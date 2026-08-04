"""End-of-session results."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..widgets.common import Card, StatTile, faint


class SummaryScreen(QWidget):
    """What happened in the session just finished."""

    practice_again = Signal()
    review_requested = Signal()
    home_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addStretch()

        self.headline = QLabel("Session complete")
        self.headline.setObjectName("Headline")
        self.headline.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.headline)

        self.subline = faint("")
        self.subline.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.subline)

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.tile_prompts = StatTile("Prompts")
        self.tile_accuracy = StatTile("Clean first try")
        self.tile_time = StatTile("Time")
        self.tile_swaps = StatTile("Hand mix-ups")
        for tile in (self.tile_prompts, self.tile_accuracy, self.tile_time, self.tile_swaps):
            tiles.addWidget(tile)
        layout.addLayout(tiles)

        self.coaching = Card(padding=16)
        self.coaching_label = QLabel("")
        self.coaching_label.setWordWrap(True)
        self.coaching.body.addWidget(self.coaching_label)
        layout.addWidget(self.coaching)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch()
        self.home_button = QPushButton("Back to lessons")
        self.review_button = QPushButton("Practise what I missed")
        self.again_button = QPushButton("Go again")
        self.again_button.setObjectName("Primary")
        self.home_button.clicked.connect(self.home_requested)
        self.review_button.clicked.connect(self.review_requested)
        self.again_button.clicked.connect(self.practice_again)
        buttons.addWidget(self.home_button)
        buttons.addWidget(self.review_button)
        buttons.addWidget(self.again_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        layout.addStretch()

    def show_summary(self, summary: dict, review_count: int) -> None:
        prompts = summary.get("prompts", 0)
        accuracy = summary.get("accuracy", 0.0)
        duration = summary.get("duration_s", 0.0)
        swaps = summary.get("side_swaps", 0)

        if prompts == 0:
            self.headline.setText("Session ended")
            self.subline.setText("Nothing written this time.")
        elif accuracy >= 0.95:
            self.headline.setText("Clean run")
            self.subline.setText("That material is solid. Try it again with the hints off.")
        elif accuracy >= 0.75:
            self.headline.setText("Good session")
            self.subline.setText("Most of that landed first time.")
        else:
            self.headline.setText("Session complete")
            self.subline.setText("Plenty to build on — the misses are queued for review.")

        self.tile_prompts.set_value(str(prompts))
        colour = (
            theme.SUCCESS if accuracy >= 0.9
            else theme.WARNING if accuracy >= 0.7
            else theme.ERROR
        )
        self.tile_accuracy.set_value(f"{accuracy:.0%}" if prompts else "—", colour if prompts else None)
        minutes, seconds = divmod(int(duration), 60)
        self.tile_time.set_value(f"{minutes}:{seconds:02d}")
        self.tile_swaps.set_value(str(swaps), theme.WARNING if swaps else None)

        if swaps:
            self.coaching_label.setText(
                f"You reached for the wrong side of the board {swaps} time"
                f"{'s' if swaps != 1 else ''} this session. That is the most common mistake "
                f"coming from a QWERTY keyboard, and it is worth drilling on its own — the "
                f"“Left hand, right hand” lesson is built for exactly this."
            )
            self.coaching_label.setStyleSheet(f"color: {theme.WARNING};")
            self.coaching.setVisible(True)
        elif prompts:
            self.coaching_label.setText(
                "No left/right mix-ups this session. The sides are sticking."
            )
            self.coaching_label.setStyleSheet(f"color: {theme.SUCCESS};")
            self.coaching.setVisible(True)
        else:
            self.coaching.setVisible(False)

        self.review_button.setEnabled(review_count > 0)
