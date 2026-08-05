"""Board profiles: what keys a steno keyboard has and where they sit.

Geometry is expressed in "key pitch" units with fractional positions, so the gap between
the two banks and the drop to the thumb row are just coordinates rather than special cases
in the renderer. A key may also span more than one unit, which is how a real stenotype's
tall S and asterisk keys are described.

What does *not* vary by board is the steno system itself. Steno order, the hyphen rule and
the Gemini PR wire format are properties of English Stenotype and of the protocol, not of
any particular keyboard, so they stay in protocol.py. A profile only describes which keys
a board exposes and how they are arranged.

Built-in profiles are defined in Python rather than shipped as data files, so a packaging
mistake can never leave the app with no board at all. Users add their own boards as JSON in
%LOCALAPPDATA%\\TinyStenoTrainer\\boards\\, and any built-in can be exported there as a
starting template.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .protocol import STENO_ORDER
from .storage import DATA_DIR

BOARDS_DIR = DATA_DIR / "boards"

# Protocols the app can actually decode. The field exists so a profile can declare what its
# board speaks; adding another means implementing a reader in machine.py, not editing JSON.
SUPPORTED_PROTOCOLS = ("gemini_pr",)

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ProfileKey:
    """One physical key on a board."""

    key: str            # Canonical steno key, e.g. 'S-', '*', '-T'
    label: str          # What is printed on it
    col: float          # Left edge, in key-pitch units
    row: float          # Top edge, in key-pitch units
    width: float = 1.0
    height: float = 1.0
    switch: str = ""    # Protocol switch name, for showing exactly which one fired
    finger: str = ""    # Optional override; otherwise derived from the canonical key

    @property
    def centre(self) -> tuple[float, float]:
        return (self.col + self.width / 2, self.row + self.height / 2)

    def to_dict(self) -> dict:
        data = {"key": self.key, "label": self.label, "col": self.col, "row": self.row}
        if self.width != 1.0:
            data["width"] = self.width
        if self.height != 1.0:
            data["height"] = self.height
        if self.switch:
            data["switch"] = self.switch
        if self.finger:
            data["finger"] = self.finger
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ProfileKey":
        return cls(
            key=str(data["key"]),
            label=str(data.get("label", data["key"].strip("-"))),
            col=float(data["col"]),
            row=float(data["row"]),
            width=float(data.get("width", 1.0)),
            height=float(data.get("height", 1.0)),
            switch=str(data.get("switch", "")),
            finger=str(data.get("finger", "")),
        )


@dataclass(frozen=True)
class BoardProfile:
    """A steno keyboard the trainer knows how to draw and read."""

    id: str
    name: str
    description: str = ""
    protocol: str = "gemini_pr"
    vendor: str = ""
    notes: str = ""
    builtin: bool = False
    source: Path | None = None
    keys: tuple[ProfileKey, ...] = ()

    # ---- geometry -----------------------------------------------------------------

    @property
    def width(self) -> float:
        return max((key.col + key.width for key in self.keys), default=1.0)

    @property
    def height(self) -> float:
        return max((key.row + key.height for key in self.keys), default=1.0)

    # ---- key inventory ------------------------------------------------------------

    @property
    def steno_keys(self) -> set[str]:
        """The canonical steno keys this board can produce."""
        return {key.key for key in self.keys}

    def keys_for(self, steno_key: str) -> list[ProfileKey]:
        """Every physical key reporting a given canonical key (both S keys, all stars)."""
        return [key for key in self.keys if key.key == steno_key]

    def caps_for_chord(self, chord) -> list[ProfileKey]:
        wanted = set(chord)
        return [key for key in self.keys if key.key in wanted]

    def supports(self, chord) -> bool:
        """Whether this board can physically write a chord."""
        return set(chord) <= self.steno_keys

    # ---- serialisation ------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "protocol": self.protocol,
            "vendor": self.vendor,
            "notes": self.notes,
            "keys": [key.to_dict() for key in self.keys],
        }

    @classmethod
    def from_dict(cls, data: dict, source: Path | None = None) -> "BoardProfile":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            description=str(data.get("description", "")),
            protocol=str(data.get("protocol", "gemini_pr")),
            vendor=str(data.get("vendor", "")),
            notes=str(data.get("notes", "")),
            builtin=False,
            source=source,
            keys=tuple(ProfileKey.from_dict(entry) for entry in data.get("keys", ())),
        )

    def export(self, directory: Path = BOARDS_DIR) -> Path:
        """Write this profile to the user boards folder as an editable template."""
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path


def validate(profile: BoardProfile) -> list[str]:
    """Problems that would make a profile unusable. Empty list means it is fine."""
    problems: list[str] = []

    if not profile.id:
        problems.append("missing id")
    if not profile.keys:
        problems.append("no keys defined")
    if profile.protocol not in SUPPORTED_PROTOCOLS:
        problems.append(
            f"protocol '{profile.protocol}' is not supported "
            f"(known: {', '.join(SUPPORTED_PROTOCOLS)})"
        )

    for key in profile.keys:
        if key.key not in STENO_ORDER:
            problems.append(f"'{key.key}' is not a steno key")
        if key.width <= 0 or key.height <= 0:
            problems.append(f"{key.key} at ({key.col}, {key.row}) has a non-positive size")

    # Overlapping keycaps almost always mean a typo in the coordinates.
    for i, a in enumerate(profile.keys):
        for b in profile.keys[i + 1:]:
            overlap_x = a.col < b.col + b.width and b.col < a.col + a.width
            overlap_y = a.row < b.row + b.height and b.row < a.row + a.height
            if overlap_x and overlap_y:
                problems.append(
                    f"{a.key} at ({a.col}, {a.row}) overlaps {b.key} at ({b.col}, {b.row})"
                )

    return problems


# ---------------------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------------------

# Clear space on each side of the centre asterisk column, so it reads as its own column
# between the banks rather than as the last key of the left hand. Baked into the
# coordinates below rather than applied by the renderer.
_STAR_GAP = 0.4
_THUMB = 2.42

# The thumbs sit inboard, tucked against the asterisk column from either side, which is
# where thumbs naturally fall. Nothing sits directly beneath the asterisks.
_LEFT_THUMB_START = 2.4    # A- and O- occupy 2.4-3.4 and 3.4-4.4
_RIGHT_THUMB_START = 5.4   # -E and -U occupy 5.4-6.4 and 6.4-7.4


def _right(col: float) -> float:
    """Shift a right-bank column clear of the centre asterisk column."""
    return col + 2 * _STAR_GAP


def _star(col: float) -> float:
    return col + _STAR_GAP


def _tinymod4() -> BoardProfile:
    """The layout verified against real hardware on 2026-07-29 (see CLAUDE.md s4).

    24 physical switches. Both S switches report S- and both star switches report *, the
    way one tall key would on a production stenotype.
    """
    keys = tuple(
        ProfileKey(key=key, label=label, col=col, row=row, switch=switch)
        for key, label, col, row, switch in (
            # Left bank
            ("S-", "S", 0, 0, "S1-"), ("T-", "T", 1, 0, "T-"),
            ("P-", "P", 2, 0, "P-"), ("H-", "H", 3, 0, "H-"),
            ("S-", "S", 0, 1, "S2-"), ("K-", "K", 1, 1, "K-"),
            ("W-", "W", 2, 1, "W-"), ("R-", "R", 3, 1, "R-"),
            # Centre column, alone
            ("*", "*", _star(4), 0, "*1"), ("*", "*", _star(4), 1, "*3"),
            # Right bank
            ("-F", "F", _right(5), 0, "-F"), ("-P", "P", _right(6), 0, "-P"),
            ("-L", "L", _right(7), 0, "-L"), ("-T", "T", _right(8), 0, "-T"),
            ("-D", "D", _right(9), 0, "-D"),
            ("-R", "R", _right(5), 1, "-R"), ("-B", "B", _right(6), 1, "-B"),
            ("-G", "G", _right(7), 1, "-G"), ("-S", "S", _right(8), 1, "-S"),
            ("-Z", "Z", _right(9), 1, "-Z"),
            # Thumbs, tucked against the centre column from either side
            ("A-", "A", _LEFT_THUMB_START, _THUMB, "A-"),
            ("O-", "O", _LEFT_THUMB_START + 1, _THUMB, "O-"),
            ("-E", "E", _RIGHT_THUMB_START, _THUMB, "-E"),
            ("-U", "U", _RIGHT_THUMB_START + 1, _THUMB, "-U"),
        )
    )
    return BoardProfile(
        id="tinymod4",
        name="TinyMod4",
        vendor="Charley Shattuck",
        description="24-switch open-source board. Two S keys and two asterisk keys.",
        notes=(
            "Verified against real hardware. Must be in Serial mode — the jumper marked "
            "'Serial = GeminiPiper'. The jumper is read once at power-up, so changing it "
            "needs a full USB replug."
        ),
        builtin=True,
        keys=keys,
    )


def _standard_stenotype() -> BoardProfile:
    """The reference English Stenotype layout: 23 keys, with tall S and asterisk.

    This is the arrangement every steno theory is taught on, so it doubles as a
    hardware-neutral board for anyone practising without a specific machine in mind.
    """
    number_bar_h = 0.6
    top = number_bar_h + 0.15
    home = top + 1
    thumb = home + 1.42

    keys: list[ProfileKey] = [
        ProfileKey("#", "#", 0, 0, width=_right(10), height=number_bar_h, switch="#1"),
        # S and the asterisk are single tall keys here, spanning both rows.
        ProfileKey("S-", "S", 0, top, height=2, switch="S1-"),
        ProfileKey("*", "*", _star(4), top, height=2, switch="*1"),
    ]
    for key, label, col in (("T-", "T", 1), ("P-", "P", 2), ("H-", "H", 3)):
        keys.append(ProfileKey(key, label, col, top, switch=key))
    for key, label, col in (("K-", "K", 1), ("W-", "W", 2), ("R-", "R", 3)):
        keys.append(ProfileKey(key, label, col, home, switch=key))
    for key, label, col in (("-F", "F", 5), ("-P", "P", 6), ("-L", "L", 7),
                            ("-T", "T", 8), ("-D", "D", 9)):
        keys.append(ProfileKey(key, label, _right(col), top, switch=key))
    for key, label, col in (("-R", "R", 5), ("-B", "B", 6), ("-G", "G", 7),
                            ("-S", "S", 8), ("-Z", "Z", 9)):
        keys.append(ProfileKey(key, label, _right(col), home, switch=key))
    for key, label, col in (("A-", "A", _LEFT_THUMB_START),
                            ("O-", "O", _LEFT_THUMB_START + 1)):
        keys.append(ProfileKey(key, label, col, thumb, switch=key))
    for key, label, col in (("-E", "E", _RIGHT_THUMB_START),
                            ("-U", "U", _RIGHT_THUMB_START + 1)):
        keys.append(ProfileKey(key, label, col, thumb, switch=key))

    return BoardProfile(
        id="standard23",
        name="Standard stenotype (23 keys)",
        description="The reference layout, with tall S and asterisk keys and a number bar.",
        notes=(
            "Hardware-neutral. Use this if your board follows the classic stenotype "
            "arrangement, or to practise the layout without a specific machine in mind."
        ),
        builtin=True,
        keys=tuple(keys),
    )


def _split_ortho() -> BoardProfile:
    """A generic split ortholinear steno shape: 2x5 per hand plus two thumbs each.

    Described as a geometry rather than as any particular product. It is the commonest
    arrangement among DIY steno boards, and is meant as a starting point to adjust rather
    than an exact match for a specific keyboard.
    """
    # Two asterisk columns sit together in the middle, so the thumbs tuck against the
    # outside of that block rather than against a single column.
    star_left, star_right = _star(4), _star(5)
    right_thumb = star_right + 1
    keys = tuple(
        ProfileKey(key=key, label=label, col=col, row=row)
        for key, label, col, row in (
            ("S-", "S", 0, 0), ("T-", "T", 1, 0), ("P-", "P", 2, 0), ("H-", "H", 3, 0),
            ("S-", "S", 0, 1), ("K-", "K", 1, 1), ("W-", "W", 2, 1), ("R-", "R", 3, 1),
            ("*", "*", star_left, 0), ("*", "*", star_right, 0),
            ("*", "*", star_left, 1), ("*", "*", star_right, 1),
            ("-F", "F", _right(6), 0), ("-P", "P", _right(7), 0),
            ("-L", "L", _right(8), 0), ("-T", "T", _right(9), 0),
            ("-D", "D", _right(10), 0),
            ("-R", "R", _right(6), 1), ("-B", "B", _right(7), 1),
            ("-G", "G", _right(8), 1), ("-S", "S", _right(9), 1),
            ("-Z", "Z", _right(10), 1),
            ("A-", "A", _LEFT_THUMB_START, _THUMB),
            ("O-", "O", _LEFT_THUMB_START + 1, _THUMB),
            ("-E", "E", right_thumb, _THUMB), ("-U", "U", right_thumb + 1, _THUMB),
        )
    )
    return BoardProfile(
        id="split-ortho",
        name="Generic split (26 keys)",
        description=(
            "Two rows per hand, four asterisk keys down the middle, two thumbs per side."
        ),
        notes=(
            "A shape, not a specific product — the commonest arrangement among DIY steno "
            "boards. Export it and edit the coordinates to match your own hardware."
        ),
        builtin=True,
        keys=keys,
    )


BUILTIN_PROFILES: tuple[BoardProfile, ...] = (
    _tinymod4(),
    _standard_stenotype(),
    _split_ortho(),
)

DEFAULT_PROFILE_ID = "tinymod4"


# ---------------------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------------------


@dataclass
class BoardRegistry:
    """Every board the app knows about: the built-ins plus the user's own JSON files."""

    profiles: list[BoardProfile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, user_dir: Path = BOARDS_DIR) -> "BoardRegistry":
        registry = cls(profiles=list(BUILTIN_PROFILES))

        if user_dir.exists():
            for path in sorted(user_dir.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    registry.warnings.append(f"{path.name}: could not be read ({exc})")
                    continue
                try:
                    profile = BoardProfile.from_dict(data, source=path)
                except (KeyError, TypeError, ValueError) as exc:
                    registry.warnings.append(f"{path.name}: malformed ({exc})")
                    continue

                problems = validate(profile)
                if problems:
                    registry.warnings.append(f"{path.name}: {problems[0]}")
                    continue

                # A user file replaces a built-in of the same id, so anyone can correct a
                # layout we got wrong without waiting for a new build.
                registry.profiles = [
                    existing for existing in registry.profiles if existing.id != profile.id
                ]
                registry.profiles.append(profile)

        registry.profiles.sort(key=lambda p: (not p.builtin, p.name))
        return registry

    def get(self, profile_id: str) -> BoardProfile | None:
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile
        return None

    def resolve(self, profile_id: str | None) -> BoardProfile:
        """The requested profile, falling back to the default and then to anything at all."""
        return (
            (self.get(profile_id) if profile_id else None)
            or self.get(DEFAULT_PROFILE_ID)
            or self.profiles[0]
        )

    def __iter__(self):
        return iter(self.profiles)

    def __len__(self) -> int:
        return len(self.profiles)
