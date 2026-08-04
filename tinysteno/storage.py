"""Persistent progress, settings and per-item statistics.

Everything lives in one JSON file under %LOCALAPPDATA%\\TinyStenoTrainer. Writes go through
a temporary file and a replace, so a crash mid-save cannot leave a truncated profile.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

DATA_DIR = Path(os.path.expandvars(r"%LOCALAPPDATA%\TinyStenoTrainer"))
PROFILE_PATH = DATA_DIR / "profile.json"

# An item is considered learned once it has been written correctly this many times in a row.
MASTERY_STREAK = 3


@dataclass
class ItemStats:
    """How the learner is doing on one specific word/outline pair."""

    attempts: int = 0
    correct: int = 0
    streak: int = 0
    best_streak: int = 0
    total_ms: int = 0
    last_seen: float = 0.0
    side_swaps: int = 0
    errors: dict[str, int] = field(default_factory=dict)

    @property
    def accuracy(self) -> float:
        return self.correct / self.attempts if self.attempts else 0.0

    @property
    def average_ms(self) -> int:
        return int(self.total_ms / self.correct) if self.correct else 0

    @property
    def is_mastered(self) -> bool:
        return self.streak >= MASTERY_STREAK

    @property
    def needs_review(self) -> bool:
        """Either the last attempt was a miss, or the running accuracy is still shaky."""
        if self.attempts == 0:
            return False
        return self.streak == 0 or self.accuracy < 0.8

    def record(self, success: bool, elapsed_ms: int, verdict: str) -> None:
        self.attempts += 1
        self.last_seen = time.time()
        if success:
            self.correct += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            self.total_ms += max(0, elapsed_ms)
        else:
            self.streak = 0
            self.errors[verdict] = self.errors.get(verdict, 0) + 1
            if verdict == "side_swap":
                self.side_swaps += 1


@dataclass
class SessionRecord:
    """A finished practice session, kept for the history chart."""

    started: float
    lesson: str
    prompts: int
    correct: int
    duration_s: float
    side_swaps: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.prompts if self.prompts else 0.0


DEFAULT_SETTINGS = {
    "port": "COM5",
    "auto_connect": True,
    "hint_mode": "adaptive",       # adaptive | always | never
    "session_length": 20,
    "dictionary_paths": [],        # empty = use Plover's default trio
    "keyboard_fallback": False,    # accept QWERTY input when no device is present
    "finger_guidance": True,       # name the fingers for the chord during practice
}


class Profile:
    """The learner's saved state: settings, per-item stats and session history."""

    def __init__(self) -> None:
        self.settings: dict = dict(DEFAULT_SETTINGS)
        self.items: dict[str, ItemStats] = {}
        self.history: list[SessionRecord] = []

    # ---- keys ---------------------------------------------------------------------

    @staticmethod
    def item_key(text: str, outline: str) -> str:
        return f"{text}␟{outline}"

    def stats_for(self, text: str, outline: str) -> ItemStats:
        key = self.item_key(text, outline)
        if key not in self.items:
            self.items[key] = ItemStats()
        return self.items[key]

    # ---- aggregates ---------------------------------------------------------------

    @property
    def total_attempts(self) -> int:
        return sum(s.attempts for s in self.items.values())

    @property
    def total_correct(self) -> int:
        return sum(s.correct for s in self.items.values())

    @property
    def overall_accuracy(self) -> float:
        return self.total_correct / self.total_attempts if self.total_attempts else 0.0

    @property
    def total_side_swaps(self) -> int:
        return sum(s.side_swaps for s in self.items.values())

    @property
    def mastered_count(self) -> int:
        return sum(1 for s in self.items.values() if s.is_mastered)

    def review_items(self) -> list[tuple[str, str, ItemStats]]:
        """Everything worth revisiting, weakest first."""
        rows = []
        for key, stats in self.items.items():
            if not stats.needs_review:
                continue
            text, _, outline = key.partition("␟")
            rows.append((text, outline, stats))
        rows.sort(key=lambda row: (row[2].accuracy, -row[2].attempts))
        return rows

    def error_breakdown(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for stats in self.items.values():
            for verdict, count in stats.errors.items():
                totals[verdict] = totals.get(verdict, 0) + count
        return totals

    # ---- persistence --------------------------------------------------------------

    @classmethod
    def load(cls, path: Path = PROFILE_PATH) -> "Profile":
        profile = cls()
        if not path.exists():
            return profile
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return profile

        settings = data.get("settings")
        if isinstance(settings, dict):
            profile.settings.update(
                {k: v for k, v in settings.items() if k in DEFAULT_SETTINGS}
            )

        for key, raw in (data.get("items") or {}).items():
            if not isinstance(raw, dict):
                continue
            stats = ItemStats()
            for field_name, value in raw.items():
                if hasattr(stats, field_name):
                    setattr(stats, field_name, value)
            profile.items[key] = stats

        for raw in data.get("history") or []:
            if isinstance(raw, dict):
                try:
                    profile.history.append(SessionRecord(**raw))
                except TypeError:
                    continue
        return profile

    def save(self, path: Path = PROFILE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "settings": self.settings,
            "items": {key: asdict(stats) for key, stats in self.items.items()},
            "history": [asdict(record) for record in self.history[-200:]],
        }
        temp = path.with_suffix(".tmp")
        try:
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=1)
            os.replace(temp, path)
        except OSError:
            pass
