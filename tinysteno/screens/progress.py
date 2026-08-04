"""Progress, error patterns, and what to review next."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..widgets.common import Card, StatTile, faint, heading

_VERDICT_LABELS = {
    "side_swap": "Right letters, wrong hand",
    "missing_keys": "Missed a key",
    "extra_keys": "Extra key pressed",
    "wrong": "A different chord entirely",
    "alt_outline": "A different valid outline",
    "miss": "Prompts needing more than one try",
}


class ProgressScreen(QWidget):
    """Long-term statistics and the review queue."""

    review_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        scroll.setWidget(content)

        layout.addWidget(heading("Progress"))

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.tile_attempts = StatTile("Prompts written")
        self.tile_accuracy = StatTile("First-try accuracy")
        self.tile_mastered = StatTile("Solid items")
        self.tile_swaps = StatTile("Hand mix-ups")
        for tile in (self.tile_attempts, self.tile_accuracy, self.tile_mastered, self.tile_swaps):
            tiles.addWidget(tile)
        layout.addLayout(tiles)

        # Error breakdown
        self.errors_card = Card(padding=18)
        errors_header = QLabel("Where the mistakes are")
        errors_header.setObjectName("H2")
        self.errors_card.body.addWidget(errors_header)
        self.errors_body = QVBoxLayout()
        self.errors_body.setSpacing(7)
        self.errors_card.body.addLayout(self.errors_body)
        layout.addWidget(self.errors_card)

        # Review queue
        review_card = Card(padding=18)
        header_row = QHBoxLayout()
        review_header = QLabel("Worth another look")
        review_header.setObjectName("H2")
        self.review_button = QPushButton("Practise these")
        self.review_button.setObjectName("Primary")
        self.review_button.clicked.connect(self.review_requested)
        header_row.addWidget(review_header)
        header_row.addStretch()
        header_row.addWidget(self.review_button)
        review_card.body.addLayout(header_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Word", "Outline", "Accuracy", "Tries", "Hand mix-ups"]
        )
        for column, alignment in enumerate(
            [Qt.AlignLeft, Qt.AlignLeft, Qt.AlignCenter, Qt.AlignCenter, Qt.AlignCenter]
        ):
            self.table.horizontalHeaderItem(column).setTextAlignment(
                alignment | Qt.AlignVCenter
            )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 5):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(230)
        review_card.body.addWidget(self.table)

        self.empty_label = faint(
            "Nothing here yet. Finish a lesson and anything shaky will collect in this list."
        )
        review_card.body.addWidget(self.empty_label)
        layout.addWidget(review_card)
        layout.addStretch()

    def refresh(self, profile) -> None:
        self.tile_attempts.set_value(str(profile.total_attempts))

        accuracy = profile.overall_accuracy
        colour = (
            theme.SUCCESS if accuracy >= 0.9
            else theme.WARNING if accuracy >= 0.7
            else theme.ERROR if profile.total_attempts else None
        )
        self.tile_accuracy.set_value(
            f"{accuracy:.0%}" if profile.total_attempts else "—", colour
        )
        self.tile_mastered.set_value(str(profile.mastered_count))
        swaps = profile.total_side_swaps
        self.tile_swaps.set_value(str(swaps), theme.WARNING if swaps else None)

        self._refresh_errors(profile)
        self._refresh_table(profile)

    def _refresh_errors(self, profile) -> None:
        while self.errors_body.count():
            item = self.errors_body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                _clear_layout(item.layout())

        breakdown = {
            verdict: count
            for verdict, count in profile.error_breakdown().items()
            if verdict != "miss" and count
        }
        if not breakdown:
            self.errors_body.addWidget(
                faint("No errors recorded yet.")
            )
            return

        total = sum(breakdown.values())
        for verdict, count in sorted(breakdown.items(), key=lambda kv: -kv[1]):
            row = QHBoxLayout()
            row.setSpacing(10)
            label = QLabel(_VERDICT_LABELS.get(verdict, verdict))
            if verdict == "side_swap":
                label.setStyleSheet(f"color: {theme.WARNING};")
            bar = _MiniBar(count / total, theme.WARNING if verdict == "side_swap" else theme.ACCENT)
            count_label = faint(f"{count}  ·  {count / total:.0%}")
            row.addWidget(label, stretch=3)
            row.addWidget(bar, stretch=4)
            row.addWidget(count_label, stretch=1)
            self.errors_body.addLayout(row)

        if breakdown.get("side_swap"):
            tip = faint(
                "Reaching across the board is the most common beginner error. The "
                "“Left hand, right hand” lesson drills exactly this."
            )
            tip.setStyleSheet(f"color: {theme.WARNING}; font-size: 12px;")
            self.errors_body.addWidget(tip)

    def _refresh_table(self, profile) -> None:
        rows = profile.review_items()
        self.table.setRowCount(len(rows))
        self.table.setVisible(bool(rows))
        self.empty_label.setVisible(not rows)
        self.review_button.setEnabled(bool(rows))

        for index, (text, outline, stats) in enumerate(rows):
            cells = [
                text,
                outline,
                f"{stats.accuracy:.0%}",
                str(stats.attempts),
                str(stats.side_swaps) if stats.side_swaps else "—",
            ]
            for column, value in enumerate(cells):
                cell = QTableWidgetItem(value)
                if column >= 2:
                    cell.setTextAlignment(Qt.AlignCenter)
                if column == 2 and stats.accuracy < 0.6:
                    cell.setForeground(theme.qcolor(theme.ERROR))
                if column == 4 and stats.side_swaps:
                    cell.setForeground(theme.qcolor(theme.WARNING))
                self.table.setItem(index, column, cell)


class _MiniBar(QWidget):
    """A slim proportion bar used in the error breakdown."""

    def __init__(self, fraction: float, colour: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fraction = max(0.0, min(1.0, fraction))
        self._colour = colour
        self.setFixedHeight(7)

    def paintEvent(self, event) -> None:
        from PySide6.QtGui import QPainter

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.qcolor(theme.BG_INPUT))
        painter.drawRoundedRect(self.rect(), 3, 3)
        width = int(self.width() * self._fraction)
        if width > 0:
            painter.setBrush(theme.qcolor(self._colour))
            painter.drawRoundedRect(0, 0, width, self.height(), 3, 3)
        painter.end()


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear_layout(item.layout())
