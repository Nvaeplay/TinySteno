"""The drill engine: what to ask next, and what to make of the answer.

Handles multi-stroke outlines by walking the learner through one stroke at a time, fades
hints as an item becomes reliable, and re-queues anything missed so it comes back while it
is still fresh.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from .analysis import Analysis, Verdict, analyse
from .lessons import LessonItem
from .storage import MASTERY_STREAK, Profile


class Hint(Enum):
    """How much help is on screen."""

    FULL = "full"        # Word, outline text, and the chord lit on the keyboard
    CHORD = "chord"      # Word and the lit chord, but no outline text
    NONE = "none"        # Word only

    @property
    def shows_outline(self) -> bool:
        return self is Hint.FULL

    @property
    def shows_chord(self) -> bool:
        return self in (Hint.FULL, Hint.CHORD)


# How many correct answers in a row before the next hint drops away.
_FADE_AT = {0: Hint.FULL, 1: Hint.CHORD}

# Where a missed item is re-inserted, relative to the current position.
_RETRY_GAPS = (2, 6)


@dataclass
class Prompt:
    """One thing to write, plus where the learner is inside it."""

    item: LessonItem
    stroke_index: int = 0
    attempts: int = 0
    errors: int = 0
    started: float = field(default_factory=time.monotonic)
    completed_strokes: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.item.text

    @property
    def outline(self) -> str:
        return self.item.outline

    @property
    def strokes(self) -> list[set[str]]:
        return self.item.strokes

    @property
    def stroke_count(self) -> int:
        return len(self.strokes)

    @property
    def is_multi_stroke(self) -> bool:
        return self.stroke_count > 1

    @property
    def current_stroke(self) -> set[str]:
        return self.strokes[min(self.stroke_index, self.stroke_count - 1)]

    @property
    def current_outline_part(self) -> str:
        return self.outline.split("/")[min(self.stroke_index, self.stroke_count - 1)]

    @property
    def is_complete(self) -> bool:
        return self.stroke_index >= self.stroke_count

    @property
    def was_clean(self) -> bool:
        return self.errors == 0

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)

    def reset(self) -> None:
        """Back to the first stroke — used when the learner strokes undo."""
        self.stroke_index = 0
        self.completed_strokes.clear()


@dataclass
class Result:
    """What the session made of one attempt, handed to the UI."""

    analysis: Analysis
    prompt: Prompt
    advanced: bool          # This stroke was accepted
    prompt_complete: bool   # The whole outline is now finished
    elapsed_ms: int


class Session:
    """A run through a queue of prompts."""

    def __init__(
        self,
        items: list[LessonItem],
        dictionary,
        profile: Profile,
        lesson_key: str = "custom",
        hint_mode: str = "adaptive",
    ) -> None:
        self._queue: list[LessonItem] = list(items)
        self._dictionary = dictionary
        self._profile = profile
        self._lesson_key = lesson_key
        self._hint_mode = hint_mode

        self._position = 0
        self._prompt: Prompt | None = None
        self._started = time.time()
        self._monotonic_start = time.monotonic()

        self.prompts_seen = 0
        self.prompts_correct = 0
        self.total_strokes = 0
        self.side_swaps = 0
        self.finished = False

        self._advance()

    # ---- queue state --------------------------------------------------------------

    @property
    def prompt(self) -> Prompt | None:
        return self._prompt

    @property
    def total(self) -> int:
        return len(self._queue)

    @property
    def position(self) -> int:
        """1-based index of the current prompt, for '7 of 20' style display."""
        return min(self._position, len(self._queue))

    @property
    def accuracy(self) -> float:
        return self.prompts_correct / self.prompts_seen if self.prompts_seen else 0.0

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self._monotonic_start

    def _advance(self) -> None:
        if self._position >= len(self._queue):
            self._prompt = None
            self.finished = True
            return
        self._prompt = Prompt(self._queue[self._position])
        self._position += 1

    # ---- hints --------------------------------------------------------------------

    def hint_level(self) -> Hint:
        """How much to show for the current prompt."""
        prompt = self._prompt
        if prompt is None:
            return Hint.NONE
        if self._hint_mode == "always":
            return Hint.FULL
        if self._hint_mode == "never":
            # Still open up after repeated misses; a learner stuck with no help is stuck.
            return Hint.FULL if prompt.errors >= 2 else Hint.NONE

        # Adaptive: an error inside this prompt always brings the full hint back.
        if prompt.errors:
            return Hint.FULL
        stats = self._profile.stats_for(prompt.text, prompt.outline)
        return _FADE_AT.get(stats.streak, Hint.NONE)

    # ---- the main loop ------------------------------------------------------------

    def submit(self, keys: set[str]) -> Result | None:
        """Feed one chord in. Returns None when the session is already finished."""
        prompt = self._prompt
        if prompt is None or self.finished:
            return None

        self.total_strokes += 1
        prompt.attempts += 1
        expected = prompt.current_stroke

        analysis = analyse(
            expected_keys=expected,
            actual_keys=keys,
            expected_text=prompt.text if not prompt.is_multi_stroke else prompt.current_outline_part,
            dictionary=self._dictionary,
        )

        # Undo clears progress on the current prompt rather than counting as a miss.
        if analysis.verdict is Verdict.UNDO:
            prompt.reset()
            return Result(analysis, prompt, advanced=False, prompt_complete=False,
                          elapsed_ms=prompt.elapsed_ms())

        if analysis.verdict is Verdict.SIDE_SWAP:
            self.side_swaps += 1

        if analysis.is_success:
            prompt.completed_strokes.append(analysis.actual_outline)
            prompt.stroke_index += 1
            complete = prompt.is_complete
            if complete:
                self._finish_prompt(prompt)
            return Result(analysis, prompt, advanced=True, prompt_complete=complete,
                          elapsed_ms=prompt.elapsed_ms())

        prompt.errors += 1
        return Result(analysis, prompt, advanced=False, prompt_complete=False,
                      elapsed_ms=prompt.elapsed_ms())

    def _finish_prompt(self, prompt: Prompt) -> None:
        self.prompts_seen += 1
        stats = self._profile.stats_for(prompt.text, prompt.outline)
        stats.record(
            success=prompt.was_clean,
            elapsed_ms=prompt.elapsed_ms(),
            verdict="miss",
        )
        if prompt.was_clean:
            self.prompts_correct += 1
        else:
            self._requeue(prompt.item)

    def _requeue(self, item: LessonItem) -> None:
        """Put a missed item back into the queue so it returns while it is still fresh."""
        already = sum(1 for queued in self._queue[self._position:] if queued is item)
        if already >= len(_RETRY_GAPS):
            return
        gap = _RETRY_GAPS[min(already, len(_RETRY_GAPS) - 1)]
        insert_at = min(self._position + gap, len(self._queue))
        self._queue.insert(insert_at, item)

    def record_error(self, analysis: Analysis) -> None:
        """Log a miss against the item's long-term stats."""
        prompt = self._prompt
        if prompt is None:
            return
        stats = self._profile.stats_for(prompt.text, prompt.outline)
        stats.errors[analysis.verdict.value] = stats.errors.get(analysis.verdict.value, 0) + 1
        if analysis.verdict is Verdict.SIDE_SWAP:
            stats.side_swaps += 1

    def next_prompt(self) -> Prompt | None:
        """Move to the next prompt. Call once the UI has shown the completion beat."""
        self._advance()
        return self._prompt

    def skip(self) -> Prompt | None:
        prompt = self._prompt
        if prompt is not None:
            self.prompts_seen += 1
            self._requeue(prompt.item)
        self._advance()
        return self._prompt

    # ---- summary ------------------------------------------------------------------

    def summary(self) -> dict:
        return {
            "lesson": self._lesson_key,
            "prompts": self.prompts_seen,
            "correct": self.prompts_correct,
            "accuracy": self.accuracy,
            "strokes": self.total_strokes,
            "side_swaps": self.side_swaps,
            "duration_s": self.elapsed_s,
            "started": self._started,
        }


def build_review_session(profile: Profile, dictionary, limit: int = 20) -> list[LessonItem]:
    """Assemble a queue from whatever the learner has been getting wrong."""
    items: list[LessonItem] = []
    for text, outline, _stats in profile.review_items()[:limit]:
        items.append(LessonItem(text=text, outline=outline))
    return items


def order_by_difficulty(items: list[LessonItem], profile: Profile) -> list[LessonItem]:
    """Front-load the shakiest material, but keep unseen items early too."""

    def rank(item: LessonItem) -> tuple:
        stats = profile.stats_for(item.text, item.outline)
        if stats.attempts == 0:
            return (1, 0.0, item.text)          # Unseen: after the known-weak, before the solid.
        if stats.is_mastered:
            return (2, -stats.accuracy, item.text)
        return (0, stats.accuracy, item.text)   # Weak: first.

    return sorted(items, key=rank)


def limit_session(items: list[LessonItem], length: int) -> list[LessonItem]:
    """Trim or cycle a queue to the configured session length."""
    if not items:
        return []
    if len(items) >= length:
        return items[:length]
    out = list(items)
    while len(out) < length:
        out.extend(items[: length - len(out)])
    return out
