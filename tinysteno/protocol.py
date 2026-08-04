"""Gemini PR protocol decoding and RTFCRE stroke formatting.

Every table here was verified against the physical TinyMod4 on 2026-07-29 (see CLAUDE.md
section 3). Byte 0 always has the MSB set -- that is the frame-start marker, which makes
resynchronisation trivial: any byte with the high bit set begins a frame.
"""

from __future__ import annotations

FRAME_SIZE = 6
FRAME_START_MASK = 0x80

# Bits run MSB -> LSB = left -> right, i.e. 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01.
# Byte 0's 0x80 is the frame marker, not a key.
GEMINI_TABLE: tuple[tuple[str, ...], ...] = (
    ("Fn", "#1", "#2", "#3", "#4", "#5", "#6"),
    ("S1-", "S2-", "T-", "K-", "P-", "W-", "H-"),
    ("R-", "A-", "O-", "*1", "*2", "res1", "res2"),
    ("pwr", "*3", "*4", "-E", "-U", "-F", "-R"),
    ("-P", "-B", "-L", "-G", "-T", "-S", "-D"),
    ("#7", "#8", "#9", "#A", "#B", "#C", "-Z"),
)

BIT_VALUES = (0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01)

# Physical switch -> canonical steno key. The TinyMod4 has two S switches and two star
# switches; both members of each pair report the same steno key, exactly as a single tall
# key would on a real stenotype. Fn / pwr / reserved bits carry no steno meaning.
_PHYSICAL_TO_CANONICAL: dict[str, str | None] = {
    "Fn": None,
    "pwr": None,
    "res1": None,
    "res2": None,
    "S1-": "S-",
    "S2-": "S-",
    "*1": "*",
    "*2": "*",
    "*3": "*",
    "*4": "*",
}
for _n in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "A", "B", "C"):
    _PHYSICAL_TO_CANONICAL[f"#{_n}"] = "#"

# Canonical steno order for English Stenotype: #STKPWHRAO*EUFRPBLGTSDZ
LEFT_KEYS = ("S-", "T-", "K-", "P-", "W-", "H-", "R-")
MIDDLE_KEYS = ("A-", "O-", "*", "-E", "-U")
RIGHT_KEYS = ("-F", "-R", "-P", "-B", "-L", "-G", "-T", "-S", "-D", "-Z")
STENO_ORDER = ("#",) + LEFT_KEYS + MIDDLE_KEYS + RIGHT_KEYS
_ORDER_INDEX = {key: i for i, key in enumerate(STENO_ORDER)}

# The number bar remaps ten keys to digits. Plover writes the digits inline in the outline
# (verified in main.json: "W0R8D" for world, "12K3W*", "1KWR-6").
NUMBER_MAP = {
    "S-": "1", "T-": "2", "P-": "3", "H-": "4", "A-": "5",
    "O-": "0", "-F": "6", "-P": "7", "-L": "8", "-T": "9",
}


def key_letter(key: str) -> str:
    """The bare letter of a steno key, with its side stripped. 'T-' and '-T' both -> 'T'."""
    return key.strip("-")


def key_side(key: str) -> str:
    """'left', 'right' or 'center'. Thumbs count with their hand: A-/O- left, -E/-U right."""
    if key in ("*", "#"):
        return "center"
    if key.startswith("-"):
        return "right"
    return "left"


def sort_keys(keys) -> list[str]:
    """Order a collection of canonical keys into steno order."""
    return sorted(keys, key=lambda k: _ORDER_INDEX.get(k, 99))


def decode_frame(frame: bytes) -> set[str]:
    """Decode one 6-byte Gemini PR frame into a set of canonical steno keys.

    Physical switches collapse onto their canonical key, so both S switches yield 'S-'
    and any of the four star bits yields '*'.
    """
    if len(frame) != FRAME_SIZE:
        raise ValueError(f"Gemini PR frames are {FRAME_SIZE} bytes, got {len(frame)}")
    keys: set[str] = set()
    for byte_index, byte in enumerate(frame):
        for bit_index, bit_value in enumerate(BIT_VALUES):
            if byte & bit_value:
                physical = GEMINI_TABLE[byte_index][bit_index]
                canonical = _PHYSICAL_TO_CANONICAL.get(physical, physical)
                if canonical is not None:
                    keys.add(canonical)
    return keys


def decode_frame_physical(frame: bytes) -> set[str]:
    """Decode a frame into the *physical* switch names, keeping S1/S2 and *1..*4 distinct.

    Used by the visualiser so it can light the exact switch that fired.
    """
    if len(frame) != FRAME_SIZE:
        raise ValueError(f"Gemini PR frames are {FRAME_SIZE} bytes, got {len(frame)}")
    switches: set[str] = set()
    for byte_index, byte in enumerate(frame):
        for bit_index, bit_value in enumerate(BIT_VALUES):
            if byte & bit_value:
                switches.add(GEMINI_TABLE[byte_index][bit_index])
    return switches


def format_stroke(keys) -> str:
    """Render canonical keys as an RTFCRE outline string, the form Plover dictionaries use.

    The hyphen appears only when right-hand keys are present with no middle section, which
    is what makes '-T' (the) distinct from 'T-' (it), and 'TP-PL' distinct from 'TPPL'.
    """
    keys = set(keys)
    if not keys:
        return ""

    numbered = "#" in keys
    substitutions = {}
    if numbered:
        substitutions = {k: NUMBER_MAP[k] for k in keys if k in NUMBER_MAP}

    def render(key: str) -> str:
        return substitutions.get(key, key_letter(key))

    left = "".join(render(k) for k in LEFT_KEYS if k in keys)
    middle = "".join(render(k) for k in MIDDLE_KEYS if k in keys)
    right = "".join(render(k) for k in RIGHT_KEYS if k in keys)

    # A number bar press that converted nothing still has to be represented.
    prefix = "#" if numbered and not substitutions else ""

    if not left and not middle and not right:
        return prefix or "#"

    separator = "-" if right and not middle else ""
    return f"{prefix}{left}{separator}{middle}{right}"


def parse_stroke(outline: str) -> set[str]:
    """Inverse of format_stroke: turn an RTFCRE outline into canonical keys.

    Handles the hyphen convention and inline digits. Raises ValueError on malformed input.
    """
    outline = outline.strip()
    if not outline:
        raise ValueError("empty outline")

    digit_to_key = {v: k for k, v in NUMBER_MAP.items()}
    has_digit = any(c.isdigit() for c in outline)
    if outline.startswith("#"):
        outline = outline[1:]
        has_digit = True
    if not outline:
        return {"#"}

    keys: set[str] = {"#"} if has_digit else set()

    # Split on the explicit hyphen when present; otherwise walk steno order to find the
    # boundary between the left bank and the right bank.
    if "-" in outline:
        left_text, right_text = outline.split("-", 1)
        middle_text = ""
        # Any vowel/star characters sitting in the left part actually belong to the middle.
        boundary = len(left_text)
        for i, ch in enumerate(left_text):
            if ch in "AO*EU":
                boundary = i
                break
        middle_text, left_text = left_text[boundary:], left_text[:boundary]
    else:
        left_text = middle_text = right_text = ""
        section = 0  # 0 = left, 1 = middle, 2 = right
        for ch in outline:
            if ch in "AO*EU05" and section < 2:
                # '5' is A- and '0' is O-, both middle-section digits.
                if ch in "AO*EU" or (ch in "05" and has_digit):
                    section = max(section, 1)
                    middle_text += ch
                    continue
            if section == 1 and ch not in "AO*EU05":
                section = 2
            if section == 2:
                right_text += ch
            else:
                left_text += ch

    def consume(text: str, candidates: tuple[str, ...], target: set[str]) -> None:
        remaining = list(candidates)
        for ch in text:
            key = digit_to_key.get(ch) if ch.isdigit() else None
            if key is None:
                matches = [k for k in remaining if key_letter(k) == ch]
                if not matches:
                    raise ValueError(f"'{ch}' is not valid here in outline {outline!r}")
                key = matches[0]
            elif key not in remaining:
                raise ValueError(f"digit '{ch}' is not valid here in outline {outline!r}")
            target.add(key)
            remaining = remaining[remaining.index(key) + 1:]

    consume(left_text, LEFT_KEYS, keys)
    consume(middle_text, MIDDLE_KEYS, keys)
    consume(right_text, RIGHT_KEYS, keys)
    return keys


def parse_outline(outline: str) -> list[set[str]]:
    """Parse a possibly multi-stroke outline ('KAT/WAL') into a list of key sets."""
    return [parse_stroke(part) for part in outline.split("/") if part.strip()]


class FrameReader:
    """Incremental Gemini PR frame extractor.

    Feed it arbitrary byte chunks; it yields complete 6-byte frames. Because byte 0 is the
    only byte permitted to have the high bit set, a stray or truncated frame costs at most
    one dropped chord rather than desynchronising the stream.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        frames: list[bytes] = []
        for byte in data:
            if byte & FRAME_START_MASK:
                # A start byte always begins a fresh frame; discard any partial one.
                self._buffer = bytearray([byte])
            elif self._buffer:
                self._buffer.append(byte)
            else:
                continue  # Continuation byte with no frame in progress -- ignore.
            if len(self._buffer) == FRAME_SIZE:
                frames.append(bytes(self._buffer))
                self._buffer.clear()
        return frames

    def reset(self) -> None:
        self._buffer.clear()
