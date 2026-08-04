"""Built-in lesson content.

main.json contains a great many misstroke-forgiveness entries, so ranking outlines by
length alone would happily teach 'OB' for "on" instead of 'OPB'. Lesson outlines are
therefore curated, and `validate_lessons` checks every one against the learner's actual
dictionary at startup -- an outline that does not write the word it claims is dropped
rather than silently taught.

Outlines marked "verified 2026-07-29" came from real hardware captures (CLAUDE.md s5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .protocol import parse_outline


@dataclass
class LessonItem:
    """One prompt in a lesson."""

    text: str                    # What the learner should write
    outline: str                 # The outline being taught, e.g. 'KAT' or 'KAT/WAL'
    note: str = ""               # Optional coaching line shown with the prompt

    @property
    def strokes(self) -> list[set[str]]:
        return parse_outline(self.outline)

    @property
    def stroke_count(self) -> int:
        return self.outline.count("/") + 1


@dataclass
class Lesson:
    """A named group of prompts."""

    key: str
    title: str
    subtitle: str
    items: list[LessonItem] = field(default_factory=list)
    focus_side_confusion: bool = False

    def __len__(self) -> int:
        return len(self.items)


def _items(pairs) -> list[LessonItem]:
    return [
        LessonItem(text, outline, note)
        for text, outline, *rest in pairs
        for note in (rest[0] if rest else "",)
    ]


# --------------------------------------------------------------------------------------
# Lesson 1 — First words (all verified against hardware on 2026-07-29)
# --------------------------------------------------------------------------------------

FIRST_WORDS = Lesson(
    key="first-words",
    title="First words",
    subtitle="Ten short words to get the feel of pressing a whole chord at once",
    items=_items([
        ("the", "-T", "One key, right hand. The most common word in English."),
        ("cat", "KAT", "Steno spells sound, not letters — there is no C key."),
        ("hat", "HAT"),
        ("sat", "SAT"),
        ("mat", "PHAT", "P and H together make the M sound."),
        ("on", "OPB", "P and B together make the N sound."),
        ("dog", "TKOG", "T and K together make the D sound."),
        ("and", "SKP", "S, K and P pressed together."),
        ("a", "AEU"),
        ("I", "EU"),
    ]),
)

# --------------------------------------------------------------------------------------
# Lesson 2 — Left hand, right hand
#
# The dominant beginner mistake per CLAUDE.md s7: reaching for the left bank where the
# right was needed. These are minimal pairs -- the same letters, mirrored -- so the only
# way to get them right is to have the sides straight.
# --------------------------------------------------------------------------------------

LEFT_RIGHT = Lesson(
    key="left-right",
    title="Left hand, right hand",
    subtitle="Same letters, opposite sides. The mistake that catches everyone coming from QWERTY.",
    focus_side_confusion=True,
    items=_items([
        ("the", "-T", "Right-hand T. Nothing on the left."),
        ("it", "T", "Left-hand T. Same letter, other hand."),
        ("top", "TOP", "T starts it, P ends it."),
        ("pot", "POT", "Now they swap: P starts, T ends."),
        ("tap", "TAP"),
        ("pat", "PAT", "Mirror of tap."),
        ("tip", "TEUP"),
        ("pit", "PEUT", "Mirror of tip."),
        ("is", "S", "Left-hand S alone."),
        ("us", "US", "The S moved to the right hand."),
        ("pets", "PETS"),
        ("step", "STEP", "Every consonant swapped sides."),
    ]),
)

# --------------------------------------------------------------------------------------
# Lesson 3 — The four thumb keys
# --------------------------------------------------------------------------------------

VOWELS = Lesson(
    key="vowels",
    title="The four thumbs",
    subtitle="A and O on the left, E and U on the right — and the combinations they make",
    items=_items([
        ("at", "AT"),
        ("it", "T"),
        ("out", "OUT", "O and U together."),
        ("up", "UP"),
        ("a", "AEU", "A and E and U — the long A sound."),
        ("I", "EU", "E and U — the long I sound."),
        ("see", "SAOE", "A and O together make the long E sound."),
        ("too", "TAO", "A and O again, this time long OO."),
        ("go", "TKPWO", "T K P W together make the G sound."),
        ("so", "SO"),
    ]),
)

# --------------------------------------------------------------------------------------
# Lesson 4 — Everyday briefs
# --------------------------------------------------------------------------------------

BRIEFS = Lesson(
    key="briefs",
    title="Everyday briefs",
    subtitle="Very common words that collapse to one or two keys",
    items=_items([
        ("the", "-T"),
        ("is", "S"),
        ("with", "W"),
        ("of", "-F"),
        ("you", "U"),
        ("be", "-B"),
        ("can", "K"),
        ("if", "TP"),
        ("in", "TPH"),
        ("this", "TH"),
        ("do", "TKO"),
        ("have", "SR"),
        ("and", "SKP"),
        ("to", "TO"),
        ("for", "TP-R"),
        ("from", "TPR"),
    ]),
)

# --------------------------------------------------------------------------------------
# Lesson 5 — Longer words
# --------------------------------------------------------------------------------------

LONGER_WORDS = Lesson(
    key="longer-words",
    title="Longer words",
    subtitle="Fuller chords using both hands at once",
    items=_items([
        ("red", "RED"),
        ("big", "PWEUG", "P and W together make the B sound."),
        ("run", "RUPB"),
        ("world", "WORLD"),
        ("over", "OEFR"),
        ("fox", "TPOBGS", "T and P make F; B G S make the X sound."),
        ("quick", "KWEUBG", "K and W make QU; B and G make the K ending."),
        ("brown", "PWROUPB"),
        ("lazy", "HRAEZ", "H and R together make the L sound."),
        ("time", "TAOEUPL"),
    ]),
)

# --------------------------------------------------------------------------------------
# Lesson 6 — Punctuation and commands
# --------------------------------------------------------------------------------------

PUNCTUATION = Lesson(
    key="punctuation",
    title="Punctuation and commands",
    subtitle="Spacing is automatic in steno, so these are how you take control of it",
    items=_items([
        (".", "-PL", "A shorter period than TP-PL."),
        (".", "TP-PL", "The longer form of the same thing."),
        ("space", "S-P", "Insert a literal space."),
        ("capitalize", "KPA", "Capitalise the next word."),
        ("hyphen", "H-PB"),
        ("delete-space", "TK-LS", "Glue the next word onto the previous one."),
    ]),
)

# --------------------------------------------------------------------------------------
# Lesson 7 — Sentences (copy practice)
#
# Built only from words already taught above, so nothing new appears mid-sentence.
# --------------------------------------------------------------------------------------

SENTENCES: tuple[str, ...] = (
    "the cat sat on the mat",
    "the dog and the cat",
    "the big red dog",
    "I can see the cat",
    "the fox is quick",
    "it is on the mat",
    "you have the time",
    "the dog sat and the cat sat",
    "a big brown fox",
    "the lazy dog",
)

ALL_LESSONS: tuple[Lesson, ...] = (
    FIRST_WORDS,
    LEFT_RIGHT,
    VOWELS,
    BRIEFS,
    LONGER_WORDS,
    PUNCTUATION,
)


def validate_lessons(dictionary) -> tuple[list[Lesson], list[str]]:
    """Check every curated outline against the learner's dictionary.

    Returns the lessons with unverifiable items removed, plus a list of warnings. An
    outline is kept when the dictionary agrees it writes the claimed text; the punctuation
    lesson is exempt because those entries write formatting operators, not plain words.
    """
    from .dictionary import plain_text

    validated: list[Lesson] = []
    warnings: list[str] = []

    for lesson in ALL_LESSONS:
        kept: list[LessonItem] = []
        for item in lesson.items:
            translation = dictionary.lookup(item.outline)
            if translation is None:
                warnings.append(
                    f"{lesson.key}: {item.outline} is not in the dictionary (wanted “{item.text}”)"
                )
                continue
            if lesson.key != "punctuation":
                if plain_text(translation).strip().lower() != item.text.strip().lower():
                    warnings.append(
                        f"{lesson.key}: {item.outline} writes “{translation}”, not “{item.text}”"
                    )
                    continue
            kept.append(item)
        validated.append(
            Lesson(
                key=lesson.key,
                title=lesson.title,
                subtitle=lesson.subtitle,
                items=kept,
                focus_side_confusion=lesson.focus_side_confusion,
            )
        )

    return validated, warnings


def sentence_lesson(dictionary, sentences=SENTENCES) -> Lesson:
    """Build the copy-practice lesson, resolving each word through the curated table."""
    curated = {
        item.text.lower(): item.outline
        for lesson in ALL_LESSONS
        for item in lesson.items
        if lesson.key != "punctuation"
    }
    items: list[LessonItem] = []
    for sentence in sentences:
        words = sentence.split()
        if all(word.lower() in curated for word in words):
            items.append(
                LessonItem(
                    text=sentence,
                    outline="/".join(curated[word.lower()] for word in words),
                )
            )
    return Lesson(
        key="sentences",
        title="Sentences",
        subtitle="Full phrases, one stroke per word — Plover adds the spaces for you",
        items=items,
    )
