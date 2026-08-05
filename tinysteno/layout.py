"""QWERTY equivalents for Plover's Keyboard machine.

Physical board geometry lives in board.py as profiles. What is left here is the mapping
used by the keyboard-fallback input mode, which is a property of Plover's Keyboard machine
rather than of any steno keyboard, so it is the same whatever board is selected.

Note this maps by **position**, not by letter: `s` is K- because it sits where K- sits on a
stenotype, not because of the letter s. So `s`+`c`+`p` writes "cat".

    q   w   e   r   t         u   i   o   p   [
    a   s   d   f   g         j   k   l   ;   '
            c   v                 n   m
"""

from __future__ import annotations

QWERTY_HINTS: dict[str, tuple[str, ...]] = {
    "S-": ("q", "a"),
    "T-": ("w",),
    "K-": ("s",),
    "P-": ("e",),
    "W-": ("d",),
    "H-": ("r",),
    "R-": ("f",),
    "*": ("t", "g"),
    "A-": ("c",),
    "O-": ("v",),
    "-E": ("n",),
    "-U": ("m",),
    "-F": ("u",),
    "-R": ("j",),
    "-P": ("i",),
    "-B": ("k",),
    "-L": ("o",),
    "-G": ("l",),
    "-T": ("p",),
    "-S": (";",),
    "-D": ("[",),
    "-Z": ("'",),
}

# Reverse map for the keyboard-fallback input mode.
QWERTY_TO_KEY: dict[str, str] = {
    char: key for key, chars in QWERTY_HINTS.items() for char in chars
}
