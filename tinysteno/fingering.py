"""Recommended finger placement for a TinyMod-style board.

Standard stenotype fingering is more settled than it looks from the outside: every major
theory (StenEd, Phoenix, Magnum, Learn Plover!) teaches the same column-per-finger
assignment, because the machine's geometry does not really allow another one. Each finger
owns one vertical column, the thumbs take the vowels, and the right pinky stretches to
cover the outer two columns.

What is genuinely not standardised, and is marked as such in the guide:

* which hand presses the asterisk -- either index finger is normal;
* how the right pinky reaches -D and -Z, since that depends on hand size;
* how well the "rest in the seam" technique works on a TinyMod, whose keys are flat and
  unsculpted where a real stenotype's are contoured to encourage it.

The load-bearing idea here is the seam. Fingers rest *between* the top and bottom rows,
not centred on a key, because a great many sounds need both keys of a column pressed at
once -- T+K is D, P+W is B, H+R is L, -P+-B is N. A learner who rests one finger per key
cannot write "dog" at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from .protocol import sort_keys

# Mirrored colours: the same role wears the same colour on both hands, so the symmetry
# between (say) the two ring fingers is visible rather than something to be memorised.
ROLE_COLORS = {
    "pinky": "#b07de0",
    "ring": "#5b8def",
    "middle": "#38c6cd",
    "index": "#f0a45e",
    "thumb": "#e8695f",
}


@dataclass(frozen=True)
class Finger:
    """One finger and the column it owns."""

    id: str
    label: str          # "Left ring"
    hand: str           # left | right | either
    role: str           # pinky | ring | middle | index | thumb
    keys: tuple[str, ...]
    note: str = ""

    @property
    def color(self) -> str:
        return ROLE_COLORS[self.role]

    @property
    def is_shared(self) -> bool:
        return self.hand == "either"


FINGERS: tuple[Finger, ...] = (
    Finger("l-pinky", "Left pinky", "left", "pinky", ("S-",),
           "Both S keys are one tall key on a real stenotype — the pinky covers them as one."),
    Finger("l-ring", "Left ring", "left", "ring", ("T-", "K-"),
           "T and K together make D."),
    Finger("l-middle", "Left middle", "left", "middle", ("P-", "W-"),
           "P and W together make B."),
    Finger("l-index", "Left index", "left", "index", ("H-", "R-"),
           "H and R together make L."),
    Finger("l-thumb", "Left thumb", "left", "thumb", ("A-", "O-"),
           "Rolls between A and O, or presses both for the long OO sound."),
    Finger("star", "Either index", "either", "index", ("*",),
           "Reach in with whichever index finger is free. There is no fixed rule."),
    Finger("r-thumb", "Right thumb", "right", "thumb", ("-E", "-U"),
           "Rolls between E and U, or presses both."),
    Finger("r-index", "Right index", "right", "index", ("-F", "-R")),
    Finger("r-middle", "Right middle", "right", "middle", ("-P", "-B"),
           "P and B together make N."),
    Finger("r-ring", "Right ring", "right", "ring", ("-L", "-G")),
    Finger("r-pinky", "Right pinky", "right", "pinky", ("-T", "-S", "-D", "-Z"),
           "The only finger covering two columns. How far you stretch versus shift the "
           "whole hand is down to your hand size."),
)

FINGERS_BY_ID = {finger.id: finger for finger in FINGERS}

KEY_TO_FINGER: dict[str, Finger] = {
    key: finger for finger in FINGERS for key in finger.keys
}

# Display order runs left to right across the board.
DISPLAY_ORDER = tuple(finger.id for finger in FINGERS)


def finger_for(key: str) -> Finger | None:
    return KEY_TO_FINGER.get(key)


def color_for(key: str) -> str | None:
    finger = KEY_TO_FINGER.get(key)
    return finger.color if finger else None


def fingers_for_chord(keys) -> list[tuple[Finger, list[str]]]:
    """Which fingers press a chord, and which keys each one takes. Left to right."""
    keys = set(keys)
    grouped: dict[str, list[str]] = {}
    for key in keys:
        finger = KEY_TO_FINGER.get(key)
        if finger is not None:
            grouped.setdefault(finger.id, []).append(key)
    return [
        (FINGERS_BY_ID[finger_id], sort_keys(grouped[finger_id]))
        for finger_id in DISPLAY_ORDER
        if finger_id in grouped
    ]


def double_presses(keys) -> list[tuple[Finger, list[str]]]:
    """The fingers that have to hold down more than one key at once for this chord.

    This is the technique beginners miss: it needs the finger resting in the seam between
    the rows, not centred on a key.
    """
    return [
        (finger, pressed)
        for finger, pressed in fingers_for_chord(keys)
        if len(pressed) > 1
    ]


def _letters(keys: list[str]) -> str:
    return "+".join(key.strip("-") for key in keys)


def describe_chord(keys) -> str:
    """A one-line reading of which finger does what, e.g. for the practice screen."""
    parts = []
    for finger, pressed in fingers_for_chord(keys):
        label = finger.label.lower()
        if len(pressed) > 1:
            parts.append(f"{label} {_letters(pressed)} together")
        else:
            parts.append(f"{label} {_letters(pressed)}")
    return "  ·  ".join(parts)


def describe_double_presses(keys) -> str:
    """A coaching line naming only the fingers that must hold two keys, or '' if none."""
    doubles = double_presses(keys)
    if not doubles:
        return ""
    parts = [
        f"{finger.label.lower()} holds {_letters(pressed)} at the same time"
        for finger, pressed in doubles
    ]
    if len(parts) == 1:
        return f"One finger, two keys: {parts[0]}."
    return "Two fingers press pairs: " + "; ".join(parts) + "."
