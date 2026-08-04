"""Practice with your own text.

Every word is resolved against the learner's real dictionary. Words with no outline are
listed rather than silently dropped, because "this word is not in your dictionary" is
useful information, not a failure.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..lessons import ALL_LESSONS, LessonItem
from ..widgets.common import Card, faint, heading

_WORD_RE = re.compile(r"[A-Za-z']+")

SAMPLE = (
    "the quick brown fox jumps over the lazy dog\n"
    "I can see the big red cat on the mat"
)


class CustomTextScreen(QWidget):
    """Paste text, see what your dictionary covers, then drill it."""

    start_requested = Signal(list, str)   # items, title

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dictionary = None
        self._resolved: list[LessonItem] = []
        self._missing: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        scroll.setWidget(content)

        layout.addWidget(heading("Your own text"))
        layout.addWidget(
            faint("Paste anything — notes, a passage, vocabulary for work. Each word is looked "
                  "up in your Plover dictionary and turned into a drill.")
        )

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(SAMPLE)
        self.editor.setMinimumHeight(150)
        self.editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.editor)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.analyse_button = QPushButton("Check coverage")
        self.analyse_button.clicked.connect(self._analyse)
        self.sample_button = QPushButton("Use sample text")
        self.sample_button.clicked.connect(lambda: self.editor.setPlainText(SAMPLE))
        self.start_button = QPushButton("Start practice")
        self.start_button.setObjectName("Primary")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self._start)
        buttons.addWidget(self.analyse_button)
        buttons.addWidget(self.sample_button)
        buttons.addStretch()
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)

        self.result_card = Card(padding=16)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("H2")
        self.covered_label = faint("")
        self.missing_label = QLabel("")
        self.missing_label.setWordWrap(True)
        self.missing_label.setStyleSheet(f"color: {theme.WARNING};")
        self.result_card.body.addWidget(self.summary_label)
        self.result_card.body.addWidget(self.covered_label)
        self.result_card.body.addWidget(self.missing_label)
        self.result_card.setVisible(False)
        layout.addWidget(self.result_card)

        layout.addStretch()

    def set_dictionary(self, dictionary) -> None:
        self._dictionary = dictionary

    # ---- analysis -----------------------------------------------------------------

    def _on_text_changed(self) -> None:
        self.start_button.setEnabled(False)
        self.result_card.setVisible(False)

    def _curated(self) -> dict[str, str]:
        return {
            item.text.lower(): item.outline
            for lesson in ALL_LESSONS
            for item in lesson.items
            if lesson.key != "punctuation"
        }

    def _analyse(self) -> None:
        if self._dictionary is None:
            return
        text = self.editor.toPlainText().strip()
        words = [match.group(0) for match in _WORD_RE.finditer(text)]
        if not words:
            self.summary_label.setText("Nothing to practise yet")
            self.covered_label.setText("Type or paste some text above.")
            self.missing_label.setText("")
            self.result_card.setVisible(True)
            return

        curated = self._curated()
        resolved: list[LessonItem] = []
        missing: list[str] = []
        seen: set[str] = set()

        for word in words:
            lowered = word.lower()
            outline = curated.get(lowered) or self._dictionary.best_outline(lowered)
            if outline is None:
                if lowered not in missing:
                    missing.append(lowered)
                continue
            if lowered in seen:
                continue
            seen.add(lowered)
            alternates = self._dictionary.outlines_for(lowered)
            note = ""
            if len(alternates) > 1:
                others = ", ".join(alternates[1:4])
                note = f"Also written {others}"
            resolved.append(LessonItem(text=lowered, outline=outline, note=note))

        self._resolved = resolved
        self._missing = missing

        total_unique = len(seen) + len(missing)
        self.summary_label.setText(
            f"{len(resolved)} of {total_unique} words are in your dictionary"
        )
        self.covered_label.setText(
            f"{len(words)} words in the text, {len(seen)} unique and drillable."
        )
        if missing:
            shown = ", ".join(missing[:20])
            more = f" and {len(missing) - 20} more" if len(missing) > 20 else ""
            self.missing_label.setText(f"No outline found for: {shown}{more}")
        else:
            self.missing_label.setText("")
        self.missing_label.setVisible(bool(missing))

        self.result_card.setVisible(True)
        self.start_button.setEnabled(bool(resolved))

    def _start(self) -> None:
        if self._resolved:
            self.start_requested.emit(self._resolved, "Your own text")
