"""Loading Plover dictionaries and finding outlines for words.

Plover loads user.json, commands.json and main.json in priority order with earlier files
winning, and this mirrors that so the trainer teaches the learner's real setup.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .protocol import parse_stroke

PLOVER_CONFIG_DIR = Path(os.path.expandvars(r"%LOCALAPPDATA%\plover\plover"))
DEFAULT_DICTIONARIES = ("user.json", "commands.json", "main.json")

# Plover output notation, e.g. {^ing}, {-|}, {&z}, {.}
_BRACE_RE = re.compile(r"\{[^}]*\}")
_WORD_RE = re.compile(r"[A-Za-z']+")


@dataclass
class Entry:
    """One outline and what it writes."""

    outline: str
    translation: str

    @property
    def stroke_count(self) -> int:
        return self.outline.count("/") + 1

    @property
    def key_count(self) -> int:
        total = 0
        for part in self.outline.split("/"):
            try:
                total += len(parse_stroke(part))
            except ValueError:
                total += len(part)
        return total


def plain_text(translation: str) -> str:
    """Strip Plover's formatting notation down to the literal text a translation writes."""
    return _BRACE_RE.sub("", translation).strip()


def is_plain_word(translation: str) -> bool:
    """True when a translation is an ordinary word or phrase, with no formatting operators.

    The reverse index is built only from these, so looking up 'cat' can never return an
    outline that actually writes '{^cat}' or a command.
    """
    if not translation or "{" in translation or "\\" in translation:
        return False
    return bool(_WORD_RE.fullmatch(translation.replace(" ", "").replace("-", "")))


@dataclass
class StenoDictionary:
    """A merged, priority-ordered view of the learner's Plover dictionaries."""

    entries: dict[str, str] = field(default_factory=dict)
    sources: list[tuple[str, int]] = field(default_factory=list)
    _reverse: dict[str, list[str]] = field(default_factory=dict, repr=False)

    # ---- construction -------------------------------------------------------------

    @classmethod
    def load(cls, paths: list[Path] | None = None) -> "StenoDictionary":
        if paths is None:
            paths = [PLOVER_CONFIG_DIR / name for name in DEFAULT_DICTIONARIES]

        merged: dict[str, str] = {}
        sources: list[tuple[str, int]] = []
        for path in paths:
            if not path.exists():
                continue
            try:
                with open(path, encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            added = 0
            for outline, translation in data.items():
                # Earlier dictionaries win, matching Plover's priority order.
                if outline not in merged and isinstance(translation, str):
                    merged[outline] = translation
                    added += 1
            sources.append((path.name, added))

        dictionary = cls(entries=merged, sources=sources)
        dictionary._build_reverse()
        return dictionary

    def _build_reverse(self) -> None:
        reverse: dict[str, list[str]] = {}
        for outline, translation in self.entries.items():
            if not is_plain_word(translation):
                continue
            reverse.setdefault(translation.lower(), []).append(outline)
        for outlines in reverse.values():
            outlines.sort(key=self._outline_rank)
        self._reverse = reverse

    def _outline_rank(self, outline: str) -> tuple:
        """Rank outlines so the cleanest one sorts first.

        Fewest strokes wins, then fewest keys, then alphabetical for stability. main.json
        contains a lot of misstroke forgiveness entries, so this is a heuristic -- the UI
        always shows the alternates rather than pretending the top pick is the only answer.
        """
        entry = Entry(outline, self.entries.get(outline, ""))
        return (entry.stroke_count, entry.key_count, outline)

    # ---- lookup -------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.entries)

    def lookup(self, outline: str) -> str | None:
        """What a given outline writes, or None if it is not in the dictionary."""
        return self.entries.get(outline)

    def outlines_for(self, text: str) -> list[str]:
        """Every outline that writes exactly this text, best first."""
        return list(self._reverse.get(text.strip().lower(), ()))

    def best_outline(self, text: str) -> str | None:
        candidates = self.outlines_for(text)
        return candidates[0] if candidates else None

    def writes(self, outline: str, text: str) -> bool:
        """True when this outline produces this text (ignoring case and surrounding space)."""
        translation = self.lookup(outline)
        if translation is None:
            return False
        return plain_text(translation).strip().lower() == text.strip().lower()

    def known_words(self) -> int:
        return len(self._reverse)
