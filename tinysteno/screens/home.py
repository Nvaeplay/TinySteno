"""Lesson picker."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..lessons import Lesson
from ..widgets.common import faint, heading


class LessonCard(QFrame):
    """One clickable tile with a progress bar."""

    clicked = Signal(str)

    def __init__(
        self,
        key: str,
        title: str,
        subtitle: str,
        total: int,
        mastered: int,
        unit: str = "prompts",
        highlight: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._key = key
        self._highlight = highlight
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(134)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(7)

        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")

        subtitle_label = faint(subtitle)
        subtitle_label.setWordWrap(True)

        bar = QProgressBar()
        bar.setTextVisible(False)
        bar.setFixedHeight(5)
        bar.setMaximum(max(1, total))
        bar.setValue(mastered)
        colour = theme.SUCCESS if total and mastered >= total else theme.ACCENT
        bar.setStyleSheet(
            f"QProgressBar {{ background: {theme.BG_INPUT}; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {colour}; border-radius: 3px; }}"
        )

        footer = QHBoxLayout()
        footer.addWidget(faint(f"{total} {unit}"))
        footer.addStretch()
        footer.addWidget(faint(f"{mastered} of {total} solid"))

        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addStretch()
        layout.addWidget(bar)
        layout.addLayout(footer)

        self._apply_border(highlight)

    def _apply_border(self, colour: str | None) -> None:
        self.setStyleSheet(f"#Card {{ border: 1px solid {colour}; }}" if colour else "")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._key)

    def enterEvent(self, event) -> None:
        self._apply_border(theme.ACCENT)

    def leaveEvent(self, event) -> None:
        self._apply_border(self._highlight)


class HomeScreen(QWidget):
    """The landing page: pick a lesson, or jump into review."""

    lesson_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(28, 24, 28, 24)
        self._layout.setSpacing(14)
        scroll.setWidget(self._content)

    def refresh(self, lessons: list[Lesson], profile, review_count: int) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._layout.addWidget(heading("Practice"))
        self._layout.addWidget(
            faint("Pick a lesson. Each one shows the chord, waits for you to press it on the "
                  "board, and tells you exactly what happened.")
        )

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 8, 0, 0)
        grid.setSpacing(14)

        cards: list[LessonCard] = []

        if review_count:
            cards.append(
                LessonCard(
                    key="review",
                    title="Review what you missed",
                    subtitle=(
                        f"{review_count} item{'s' if review_count != 1 else ''} you have been "
                        f"getting wrong or writing slowly."
                    ),
                    total=review_count,
                    mastered=0,
                    unit="to revisit",
                    highlight=theme.WARNING,
                )
            )

        for lesson in lessons:
            if not lesson.items:
                continue
            mastered = sum(
                1 for item in lesson.items
                if profile.stats_for(item.text, item.outline).is_mastered
            )
            cards.append(
                LessonCard(
                    key=lesson.key,
                    title=lesson.title,
                    subtitle=lesson.subtitle,
                    total=len(lesson.items),
                    mastered=mastered,
                    highlight=theme.WARNING if lesson.focus_side_confusion else None,
                )
            )

        for index, card in enumerate(cards):
            card.clicked.connect(self.lesson_selected)
            grid.addWidget(card, index // 2, index % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self._layout.addWidget(grid_host)
        self._layout.addStretch()
