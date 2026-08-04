"""Comparing what the learner stroked against what the drill asked for.

The headline case is the side-swap: reaching for the left bank where the right was needed.
Per CLAUDE.md section 7 this is the dominant beginner mistake for someone coming from
QWERTY -- 'T-' for '-T', 'POB' for 'OPB' -- so it gets named and coached explicitly rather
than being lumped in with generic wrong answers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .protocol import format_stroke, key_letter, key_side, sort_keys


class Verdict(Enum):
    CORRECT = "correct"
    ALT_OUTLINE = "alt_outline"       # Right text, different valid outline.
    SIDE_SWAP = "side_swap"           # Same letters, wrong hand. The one to coach.
    MISSING_KEYS = "missing_keys"     # Under-pressed: keys left out.
    EXTRA_KEYS = "extra_keys"         # Over-pressed: stray keys added.
    WRONG = "wrong"                   # Something else entirely.
    UNDO = "undo"                     # A bare star: the learner asked to take it back.


@dataclass
class SwapPair:
    """One key that was pressed on the wrong side of the board."""

    expected: str
    actual: str

    @property
    def letter(self) -> str:
        return key_letter(self.expected)

    def describe(self) -> str:
        wanted, got = key_side(self.expected), key_side(self.actual)
        return f"{self.letter}: you pressed the {got} {self.letter}, the word needs the {wanted} one"


@dataclass
class Analysis:
    """The full verdict on one attempt."""

    verdict: Verdict
    expected_outline: str
    actual_outline: str
    expected_text: str
    actual_translation: str | None
    expected_keys: set[str] = field(default_factory=set)
    actual_keys: set[str] = field(default_factory=set)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    swaps: list[SwapPair] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.verdict in (Verdict.CORRECT, Verdict.ALT_OUTLINE)

    def headline(self) -> str:
        if self.verdict is Verdict.CORRECT:
            return "Correct"
        if self.verdict is Verdict.ALT_OUTLINE:
            return "Correct — a different valid outline"
        if self.verdict is Verdict.SIDE_SWAP:
            return "Right letters, wrong hand"
        if self.verdict is Verdict.MISSING_KEYS:
            return "Almost — a key was missed"
        if self.verdict is Verdict.EXTRA_KEYS:
            return "Almost — an extra key crept in"
        if self.verdict is Verdict.UNDO:
            return "Undo"
        return "Not this one"

    def detail(self) -> str:
        """The one-line explanation shown under the verdict."""
        if self.verdict is Verdict.CORRECT:
            return ""
        if self.verdict is Verdict.ALT_OUTLINE:
            return f"{self.actual_outline} also writes “{self.expected_text}”. The lesson outline is {self.expected_outline}."
        if self.verdict is Verdict.SIDE_SWAP:
            return "; ".join(swap.describe() for swap in self.swaps)
        if self.verdict is Verdict.MISSING_KEYS:
            return "Missing " + ", ".join(self.missing)
        if self.verdict is Verdict.EXTRA_KEYS:
            return "Remove " + ", ".join(self.extra)
        if self.actual_translation:
            return f"{self.actual_outline} writes “{self.actual_translation}”."
        return f"{self.actual_outline} is not in the dictionary."


def find_side_swaps(missing: set[str], extra: set[str]) -> list[SwapPair]:
    """Pair up keys that share a letter but sit on opposite sides of the board.

    Works on the difference between the two chords rather than requiring the whole stroke
    to be a mirror, so it still fires when the learner swapped a hand *and* fumbled a
    second key -- which is how the mistake usually shows up in practice.
    """
    swaps: list[SwapPair] = []
    unclaimed = set(extra)
    for missed in sort_keys(missing):
        for pressed in sort_keys(unclaimed):
            if key_letter(missed) == key_letter(pressed) and key_side(missed) != key_side(pressed):
                swaps.append(SwapPair(expected=missed, actual=pressed))
                unclaimed.discard(pressed)
                break
    return swaps


def _leftover(missing: set[str], extra: set[str], swaps: list[SwapPair]) -> set[str]:
    """The differing keys a set of swaps does not account for."""
    claimed = {swap.expected for swap in swaps} | {swap.actual for swap in swaps}
    return (missing | extra) - claimed


def analyse(
    expected_keys: set[str],
    actual_keys: set[str],
    expected_text: str,
    dictionary=None,
) -> Analysis:
    """Compare one pressed chord against the chord the drill asked for."""
    expected_keys, actual_keys = set(expected_keys), set(actual_keys)
    expected_outline = format_stroke(expected_keys)
    actual_outline = format_stroke(actual_keys)
    translation = dictionary.lookup(actual_outline) if dictionary else None

    missing = expected_keys - actual_keys
    extra = actual_keys - expected_keys
    swaps = find_side_swaps(missing, extra)

    def build(verdict: Verdict) -> Analysis:
        return Analysis(
            verdict=verdict,
            expected_outline=expected_outline,
            actual_outline=actual_outline,
            expected_text=expected_text,
            actual_translation=translation,
            expected_keys=expected_keys,
            actual_keys=actual_keys,
            missing=sort_keys(missing),
            extra=sort_keys(extra),
            swaps=swaps,
        )

    if not missing and not extra:
        return build(Verdict.CORRECT)

    # A bare star is Plover's undo, not a wrong answer -- treat it as a retry request.
    if actual_keys == {"*"}:
        return build(Verdict.UNDO)

    # A different outline that writes the same word is a success, not an error. The drill
    # still names the outline it was teaching so the learner sees both.
    if dictionary is not None and dictionary.writes(actual_outline, expected_text):
        return build(Verdict.ALT_OUTLINE)

    # Only call it a side swap when the swap actually explains the mistake. Two chords can
    # share a letter across the banks by coincidence -- TKOG against KAT has a T on each
    # side -- and calling that "right letters, wrong hand" would teach the wrong lesson.
    # The swapped keys must account for at least as much as everything left over.
    if swaps and 2 * len(swaps) >= len(_leftover(missing, extra, swaps)):
        return build(Verdict.SIDE_SWAP)
    if missing and not extra:
        return build(Verdict.MISSING_KEYS)
    if extra and not missing:
        return build(Verdict.EXTRA_KEYS)
    return build(Verdict.WRONG)
