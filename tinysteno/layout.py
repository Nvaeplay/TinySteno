"""The physical TinyMod4 key layout, for the on-screen keyboard.

Positions follow the verified layout in CLAUDE.md section 4:

     S-  T-  P-  H-  *      -F  -P  -L  -T  -D
     S-  K-  W-  R-  *      -R  -B  -G  -S  -Z
             A-  O-             -E  -U

24 physical switches. The two leftmost keys both send S-, and both star keys send *, so a
chord containing S- or * lights both members of the pair -- exactly as one tall key would
behave on a real stenotype.
"""

from __future__ import annotations

from dataclasses import dataclass

from .protocol import key_side


@dataclass(frozen=True)
class KeyCap:
    """One physical switch on the board."""

    key: str        # Canonical steno key, e.g. 'S-', '*', '-T'
    label: str      # What is printed on screen
    col: float      # Grid column (0-based, left bank 0-4, right bank 5-9)
    row: float      # Grid row (0 top, 1 home, 2 thumbs)
    switch: str     # Physical switch name from the Gemini table

    @property
    def side(self) -> str:
        return key_side(self.key)


# Column 5 begins the right bank; a visual gutter is inserted between the banks.
BANK_GAP_AFTER_COL = 4

KEYCAPS: tuple[KeyCap, ...] = (
    # Top row, left bank
    KeyCap("S-", "S", 0, 0, "S1-"),
    KeyCap("T-", "T", 1, 0, "T-"),
    KeyCap("P-", "P", 2, 0, "P-"),
    KeyCap("H-", "H", 3, 0, "H-"),
    KeyCap("*", "*", 4, 0, "*1"),
    # Top row, right bank
    KeyCap("-F", "F", 5, 0, "-F"),
    KeyCap("-P", "P", 6, 0, "-P"),
    KeyCap("-L", "L", 7, 0, "-L"),
    KeyCap("-T", "T", 8, 0, "-T"),
    KeyCap("-D", "D", 9, 0, "-D"),
    # Home row, left bank
    KeyCap("S-", "S", 0, 1, "S2-"),
    KeyCap("K-", "K", 1, 1, "K-"),
    KeyCap("W-", "W", 2, 1, "W-"),
    KeyCap("R-", "R", 3, 1, "R-"),
    KeyCap("*", "*", 4, 1, "*3"),
    # Home row, right bank
    KeyCap("-R", "R", 5, 1, "-R"),
    KeyCap("-B", "B", 6, 1, "-B"),
    KeyCap("-G", "G", 7, 1, "-G"),
    KeyCap("-S", "S", 8, 1, "-S"),
    KeyCap("-Z", "Z", 9, 1, "-Z"),
    # Thumbs
    KeyCap("A-", "A", 2, 2, "A-"),
    KeyCap("O-", "O", 3, 2, "O-"),
    KeyCap("-E", "E", 6, 2, "-E"),
    KeyCap("-U", "U", 7, 2, "-U"),
)

GRID_COLS = 10
GRID_ROWS = 3

# QWERTY equivalents for Plover's Keyboard machine, kept for the reference panel. Note this
# maps by position, not by letter.
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


def caps_for_key(key: str) -> list[KeyCap]:
    """Every physical switch that reports the given canonical key."""
    return [cap for cap in KEYCAPS if cap.key == key]


def caps_for_chord(keys) -> list[KeyCap]:
    """Every switch to light up for a chord, including both S keys / both star keys."""
    keys = set(keys)
    return [cap for cap in KEYCAPS if cap.key in keys]
