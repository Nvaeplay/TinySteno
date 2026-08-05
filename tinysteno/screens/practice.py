"""The practice screen: show a chord, take a stroke, say what happened.

The loop is deliberately gentle. A miss shows the learner exactly which keys were involved
and then puts the full hint back before letting them try again, rather than stopping the
session or marking the screen red.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import fingering, theme
from ..analysis import Verdict
from ..layout import QWERTY_TO_KEY
from ..session import Hint, Session
from ..widgets.common import Card, StatusPill, StrokeDots, faint, mono_label
from ..widgets.keyboard import StenoKeyboard

# How long feedback stays on screen before the drill resets for another go.
#
# These are ceilings on reading time, not floors on how fast you may write: a stroke that
# arrives during a pause ends it early and is acted on, rather than being dropped. That
# distinction is the whole point -- see `submit_chord`. Because the learner can always cut
# a pause short, these can be generous without ever being in the way.
_SUCCESS_PAUSE_MS = 380
_STROKE_PAUSE_MS = 160
_ERROR_PAUSE_MS = 1200

# ...with one exception. Gemini PR sends a frame on release, so if the learner rolls
# straight into the next chord its frame can land a few tens of milliseconds after the
# feedback renders. Without a floor, the explanation of what went wrong would be replaced
# before it could possibly be read. This is a debounce against a stroke already in flight,
# not a lockout, and it is deliberately shorter than a reaction time.
_MIN_READ_MS = 120


class PracticeScreen(QWidget):
    """Runs one Session from start to finish."""

    session_finished = Signal(dict)
    exit_requested = Signal()

    def __init__(self, parent: QWidget | None = None, profile=None) -> None:
        super().__init__(parent)
        self._profile = profile
        self._session: Session | None = None
        self._locked = False
        self._pending = None            # What the pause will do when it ends
        self._pause_started = 0.0       # monotonic seconds, for the _MIN_READ_MS debounce
        self._keyboard_fallback = False
        self._show_finger_guidance = True
        self._held: set[str] = set()
        self._chord: set[str] = set()

        self._build()

        self._clock = QTimer(self)
        self._clock.setInterval(500)
        self._clock.timeout.connect(self._update_header)

        # One reusable timer for the feedback pause, rather than QTimer.singleShot, because
        # a singleShot cannot be cancelled -- and being able to cancel it is what lets an
        # incoming stroke cut the pause short instead of being thrown away.
        self._pause_timer = QTimer(self)
        self._pause_timer.setSingleShot(True)
        self._pause_timer.timeout.connect(self._end_pause)

        self.setFocusPolicy(Qt.StrongFocus)

    # ---- construction -------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(14)

        # Header
        header = QHBoxLayout()
        header.setSpacing(16)
        self.title_label = QLabel("Practice")
        self.title_label.setObjectName("H2")
        self.counter_label = faint("")
        self.accuracy_label = faint("")
        self.timer_label = faint("")
        header.addWidget(self.title_label)
        header.addStretch()
        for widget in (self.counter_label, self.accuracy_label, self.timer_label):
            header.addWidget(widget)
        root.addLayout(header)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        root.addWidget(self.progress)

        # Prompt card
        prompt_card = Card(padding=18)
        self.prompt_label = QLabel("")
        self.prompt_label.setObjectName("Prompt")
        self.prompt_label.setAlignment(Qt.AlignCenter)
        self.prompt_label.setWordWrap(True)

        self.outline_label = mono_label("", "Outline", theme.TEXT_DIM)
        self.note_label = faint("")
        self.note_label.setAlignment(Qt.AlignCenter)
        self.dots = StrokeDots()

        prompt_card.body.addWidget(self.prompt_label)
        prompt_card.body.addWidget(self.outline_label)
        prompt_card.body.addWidget(self.dots)
        prompt_card.body.addWidget(self.note_label)
        root.addWidget(prompt_card)

        # Keyboard
        self.keyboard = StenoKeyboard(profile=self._profile)
        root.addWidget(self.keyboard, stretch=1)

        # Which finger does what for the chord on screen.
        self.fingers_label = faint("")
        self.fingers_label.setAlignment(Qt.AlignCenter)
        self.doubles_label = faint("")
        self.doubles_label.setAlignment(Qt.AlignCenter)
        self.doubles_label.setStyleSheet(f"color: {theme.VOWEL}; font-size: 12px;")
        root.addWidget(self.fingers_label)
        root.addWidget(self.doubles_label)

        # Feedback
        self.feedback_card = Card(padding=14)
        self.feedback_card.setMinimumHeight(86)
        self.verdict_label = QLabel("")
        self.verdict_label.setObjectName("Verdict")
        self.detail_label = faint("")
        self.compare_label = mono_label("", "Mono", theme.TEXT_FAINT)
        self.compare_label.setAlignment(Qt.AlignLeft)
        self.feedback_card.body.addWidget(self.verdict_label)
        self.feedback_card.body.addWidget(self.detail_label)
        self.feedback_card.body.addWidget(self.compare_label)
        root.addWidget(self.feedback_card)

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.status = StatusPill()
        self.hint_button = QPushButton("Show chord")
        self.skip_button = QPushButton("Skip")
        self.end_button = QPushButton("End session")
        self.hint_button.clicked.connect(self._force_hint)
        self.skip_button.clicked.connect(self._skip)
        self.end_button.clicked.connect(self._end)
        footer.addWidget(self.status, stretch=1)
        footer.addWidget(self.hint_button)
        footer.addWidget(self.skip_button)
        footer.addWidget(self.end_button)
        root.addLayout(footer)

    # ---- session lifecycle --------------------------------------------------------

    def start(self, session: Session, title: str) -> None:
        # A pause left over from the previous session would otherwise fire into this one.
        self._cancel_pause()
        self._session = session
        self.title_label.setText(title)
        self.progress.setMaximum(max(1, session.total))
        self._clear_feedback()
        self._show_prompt()
        self._clock.start()
        self.setFocus()

    def set_status(self, state: str, message: str) -> None:
        self.status.set_status(state, message)

    def set_keyboard_fallback(self, enabled: bool) -> None:
        self._keyboard_fallback = enabled
        self.keyboard.set_qwerty_labels(enabled)

    def set_profile(self, profile) -> None:
        self.keyboard.set_profile(profile)

    def set_finger_guidance(self, enabled: bool) -> None:
        self._show_finger_guidance = enabled
        if not enabled:
            self.fingers_label.setText("")
            self.doubles_label.setText("")

    # ---- display ------------------------------------------------------------------

    def _show_prompt(self) -> None:
        session = self._session
        if session is None:
            return
        prompt = session.prompt
        if prompt is None:
            self._finish()
            return

        self.prompt_label.setText(prompt.text)
        self.dots.set_progress(prompt.stroke_count, prompt.stroke_index)
        self.note_label.setText(prompt.item.note)
        self.note_label.setVisible(bool(prompt.item.note))

        hint = session.hint_level()
        if hint.shows_outline:
            if prompt.is_multi_stroke:
                parts = prompt.outline.split("/")
                shown = " / ".join(
                    part if index == prompt.stroke_index else "·" * len(part)
                    for index, part in enumerate(parts)
                )
                self.outline_label.setText(shown)
            else:
                self.outline_label.setText(prompt.outline)
            self.outline_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
        else:
            self.outline_label.setText("")

        if hint.shows_chord:
            self.keyboard.show_chord(prompt.current_stroke)
        else:
            self.keyboard.clear()

        self._show_fingers(prompt.current_stroke, hint)
        self.hint_button.setEnabled(hint is not Hint.FULL)
        self._update_header()

    def _show_fingers(self, keys: set[str], hint: Hint) -> None:
        """Name the fingers for the chord on screen.

        The double-press coaching only appears at the full hint level -- once an item is
        reliable the learner has the technique, and repeating it every time is noise.
        """
        if not self._show_finger_guidance or not hint.shows_chord:
            self.fingers_label.setText("")
            self.doubles_label.setText("")
            return

        self.fingers_label.setText(fingering.describe_chord(keys))
        doubles = fingering.describe_double_presses(keys) if hint.shows_outline else ""
        self.doubles_label.setText(doubles)
        self.doubles_label.setVisible(bool(doubles))

    def _update_header(self) -> None:
        session = self._session
        if session is None:
            return
        self.counter_label.setText(f"{session.position} of {session.total}")
        if session.prompts_seen:
            accuracy = session.accuracy
            color = (
                theme.SUCCESS if accuracy >= 0.9
                else theme.WARNING if accuracy >= 0.7
                else theme.ERROR
            )
            self.accuracy_label.setText(f"{accuracy:.0%} clean")
            self.accuracy_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        else:
            self.accuracy_label.setText("")
        elapsed = int(session.elapsed_s)
        self.timer_label.setText(f"{elapsed // 60}:{elapsed % 60:02d}")
        self.progress.setValue(session.position)

    def _clear_feedback(self) -> None:
        self.verdict_label.setText("Ready when you are")
        self.verdict_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
        self.detail_label.setText(
            "Press the lit chord on your board. All keys at once — press order does not matter."
        )
        self.compare_label.setText("")

    # ---- input --------------------------------------------------------------------

    # ---- feedback pauses ------------------------------------------------------------

    def _pause(self, milliseconds: int, action) -> None:
        """Hold the feedback on screen, then run `action`.

        The learner can cut this short simply by writing again -- see `submit_chord`.
        """
        self._pending = action
        self._locked = True
        self._pause_started = time.monotonic()
        self._pause_timer.start(milliseconds)

    def _end_pause(self) -> None:
        """Finish the current pause now, whether it timed out or was interrupted.

        Runs exactly the continuation the timer would have run, so the screen reaches an
        identical state either way -- only sooner.
        """
        self._pause_timer.stop()
        action, self._pending = self._pending, None
        self._locked = False
        if action is not None:
            action()

    def _cancel_pause(self) -> None:
        """Drop a pending pause without running it, for skip/finish/restart."""
        self._pause_timer.stop()
        self._pending = None
        self._locked = False

    # ---- input ----------------------------------------------------------------------

    def submit_chord(self, keys: set[str]) -> None:
        """Entry point for a decoded chord, from the device or the keyboard fallback."""
        if self._session is None or not keys:
            return

        if self._locked:
            # A stroke is a deliberate physical action -- one Gemini PR frame is one whole
            # chord, sent on release. Discarding it because feedback happens to be on
            # screen loses the learner's work and reads as the app being unresponsive. So
            # writing again ends the pause and the stroke counts.
            if (time.monotonic() - self._pause_started) * 1000 < _MIN_READ_MS:
                return
            self._end_pause()
            if self._session is None:      # The pause may have finished the session.
                return

        result = self._session.submit(keys)
        if result is None:
            return

        analysis = result.analysis

        if analysis.verdict is Verdict.UNDO:
            self.verdict_label.setText("Undo")
            self.verdict_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
            self.detail_label.setText("Back to the first stroke of this word.")
            self.compare_label.setText("")
            self._show_prompt()
            return

        if result.advanced:
            self._on_success(result)
        else:
            self._on_error(result)

    def _on_success(self, result) -> None:
        analysis = result.analysis
        self.keyboard.show_success(analysis.actual_keys)
        self.verdict_label.setText(analysis.headline())
        self.verdict_label.setStyleSheet(f"color: {theme.SUCCESS};")
        self.detail_label.setText(analysis.detail())
        self.compare_label.setText("")
        self.dots.set_progress(result.prompt.stroke_count, result.prompt.stroke_index)

        if result.prompt_complete:
            self._pause(_SUCCESS_PAUSE_MS, self._next_prompt)
        else:
            self._pause(_STROKE_PAUSE_MS, self._resume)

    def _on_error(self, result) -> None:
        analysis = result.analysis
        session = self._session
        if session is not None:
            session.record_error(analysis)

        prompt = result.prompt
        self.keyboard.show_attempt(
            expected=analysis.expected_keys,
            actual=analysis.actual_keys,
            swaps=analysis.swaps,
        )

        color = theme.WARNING if analysis.verdict is Verdict.SIDE_SWAP else theme.ERROR
        self.verdict_label.setText(analysis.headline())
        self.verdict_label.setStyleSheet(f"color: {color};")
        self.detail_label.setText(analysis.detail())

        wrote = analysis.actual_translation
        wrote_text = f"“{wrote}”" if wrote else "nothing in the dictionary"
        self.compare_label.setText(
            f"wanted  {analysis.expected_outline}"
            f"      you wrote  {analysis.actual_outline}  →  {wrote_text}"
        )
        self.compare_label.setStyleSheet(f"color: {theme.TEXT_FAINT};")

        self._pause(_ERROR_PAUSE_MS, self._resume)

    # Both continuations below run only as a pause action, and `_pause`/`_end_pause`/
    # `_cancel_pause` own `_locked` between them -- so neither touches it.

    def _resume(self) -> None:
        self._show_prompt()

    def _next_prompt(self) -> None:
        session = self._session
        if session is None:
            return
        if session.next_prompt() is None:
            self._finish()
        else:
            self._clear_feedback()
            self._show_prompt()

    # ---- controls -----------------------------------------------------------------

    def _force_hint(self) -> None:
        # Pressing a button is as clear a "I have read it, move on" as writing is, so it
        # ends a pause for the same reason a stroke does.
        if self._locked:
            self._end_pause()
        session = self._session
        if session is None or session.prompt is None:
            return
        session.prompt.errors = max(session.prompt.errors, 1)
        self._show_prompt()

    def _skip(self) -> None:
        session = self._session
        if session is None:
            return
        # Drop any pending pause rather than letting it fire: its continuation would
        # advance or re-show a prompt we have already moved past.
        self._cancel_pause()
        if session.skip() is None:
            self._finish()
        else:
            self._clear_feedback()
            self._show_prompt()

    def _end(self) -> None:
        self._finish()

    def _finish(self) -> None:
        self._clock.stop()
        self._cancel_pause()
        self.keyboard.clear()
        session, self._session = self._session, None
        if session is not None:
            self.session_finished.emit(session.summary())
        else:
            self.exit_requested.emit()

    # ---- QWERTY fallback ----------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        if not self._keyboard_fallback or event.isAutoRepeat():
            super().keyPressEvent(event)
            return
        char = event.text().lower()
        key = QWERTY_TO_KEY.get(char)
        if key is None:
            super().keyPressEvent(event)
            return
        self._held.add(char)
        self._chord.add(key)
        self.keyboard.show_chord(self._chord)

    def keyReleaseEvent(self, event) -> None:
        if not self._keyboard_fallback or event.isAutoRepeat():
            super().keyReleaseEvent(event)
            return
        char = event.text().lower()
        if char not in self._held:
            super().keyReleaseEvent(event)
            return
        self._held.discard(char)
        # A chord is sent when the last key comes up, matching how the hardware behaves.
        if not self._held and self._chord:
            chord, self._chord = self._chord, set()
            self.submit_chord(chord)
