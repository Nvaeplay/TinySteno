"""Headless checks for the parts that do not need a window or a device."""

from __future__ import annotations

import sys

from tinysteno.analysis import Verdict, analyse
from tinysteno.dictionary import StenoDictionary
from tinysteno.lessons import ALL_LESSONS, sentence_lesson, validate_lessons
from tinysteno.protocol import (
    FrameReader,
    decode_frame,
    format_stroke,
    key_side,
    parse_outline,
    parse_stroke,
)
from tinysteno.session import Session, order_by_difficulty
from tinysteno.storage import Profile

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


def section(title: str) -> None:
    print(f"\n{title}")


def hexframe(text: str) -> bytes:
    return bytes(int(part, 16) for part in text.split())


# ---------------------------------------------------------------------------------------
section("Protocol — hardware captures (CLAUDE.md s3)")

check("80 08 20 00 04 00 decodes to KAT",
      format_stroke(decode_frame(hexframe("80 08 20 00 04 00"))) == "KAT")
check("80 08 20 00 10 00 decodes to KAL",
      format_stroke(decode_frame(hexframe("80 08 20 00 10 00"))) == "KAL")
check("K- A- -T are the keys",
      decode_frame(hexframe("80 08 20 00 04 00")) == {"K-", "A-", "-T"})

section("Protocol — hyphen convention")
check("-T is the right-hand T alone", format_stroke({"-T"}) == "-T")
check("T is the left-hand T alone", format_stroke({"T-"}) == "T")
check("TP-PL keeps its hyphen", format_stroke(parse_stroke("TP-PL")) == "TP-PL")
check("-PL keeps its hyphen", format_stroke(parse_stroke("-PL")) == "-PL")
check("vowel removes the hyphen", format_stroke({"T-", "A-", "-T"}) == "TAT")

section("Protocol — number bar")
check("W0R8D round-trips", format_stroke(parse_stroke("W0R8D")) == "W0R8D")
check("12K3W* round-trips", format_stroke(parse_stroke("12K3W*")) == "12K3W*")
check("1KWR-6 round-trips", format_stroke(parse_stroke("1KWR-6")) == "1KWR-6")

section("Protocol — frame reader resynchronisation")
reader = FrameReader()
stream = hexframe("80 08 20 00 04 00") + b"\x00\x11" + hexframe("80 08 20 00 10 00")
frames = reader.feed(stream)
check("recovers after junk bytes", len(frames) == 2, f"got {len(frames)}")
check("second frame is KAL",
      len(frames) == 2 and format_stroke(decode_frame(frames[1])) == "KAL")

reader.reset()
partial = reader.feed(hexframe("80 08 20"))
rest = reader.feed(hexframe("80 08 20 00 04 00"))
check("a truncated frame costs only itself", not partial and len(rest) == 1)

section("Protocol — multi-stroke outlines")
check("KAT/WAL parses to two strokes", len(parse_outline("KAT/WAL")) == 2)

# ---------------------------------------------------------------------------------------
section("Dictionary")
dictionary = StenoDictionary.load()
check("dictionary loaded", len(dictionary) > 100000, f"{len(dictionary)} entries")
check("KAT writes cat", dictionary.lookup("KAT") == "cat")
check("-T writes the", dictionary.lookup("-T") == "the")
check("THE writes they, not the", dictionary.lookup("THE") == "they")
check("T writes it", dictionary.lookup("T") == "it")
check("OPB writes on", dictionary.lookup("OPB") == "on")
check("reverse lookup finds cat", "KAT" in dictionary.outlines_for("cat"))
check("writes() is case tolerant", dictionary.writes("KAT", "Cat"))

# ---------------------------------------------------------------------------------------
section("Analysis — the left/right confusion from CLAUDE.md s7")

result = analyse(parse_stroke("-T"), parse_stroke("T"), "the", dictionary)
check("T- for -T is a side swap", result.verdict is Verdict.SIDE_SWAP, str(result.verdict))
check("names the T key", result.swaps and result.swaps[0].letter == "T")
check("reports what it wrote instead", result.actual_translation == "it")
check("detail mentions both sides",
      "left" in result.detail() and "right" in result.detail(), result.detail())

result = analyse(parse_stroke("OPB"), parse_stroke("POB"), "on", dictionary)
check("POB for OPB is a side swap", result.verdict is Verdict.SIDE_SWAP, str(result.verdict))
check("names the P key", result.swaps and result.swaps[0].letter == "P")

section("Analysis — other verdicts")
check("identical chords are correct",
      analyse(parse_stroke("KAT"), parse_stroke("KAT"), "cat", dictionary).verdict
      is Verdict.CORRECT)
check("a missing key is not a swap",
      analyse(parse_stroke("KAT"), parse_stroke("KA"), "cat", dictionary).verdict
      is Verdict.MISSING_KEYS)
check("an extra key is flagged",
      analyse(parse_stroke("KAT"), parse_stroke("KATS"), "cat", dictionary).verdict
      is Verdict.EXTRA_KEYS)
check("a bare star is undo",
      analyse(parse_stroke("KAT"), {"*"}, "cat", dictionary).verdict is Verdict.UNDO)

alt = analyse(parse_stroke("-T"), parse_stroke("-LT"), "the", dictionary)
check("an alternate outline for the same word passes",
      alt.verdict is Verdict.ALT_OUTLINE, str(alt.verdict))
check("alternate outline counts as success", alt.is_success)

wrong = analyse(parse_stroke("KAT"), parse_stroke("TKOG"), "cat", dictionary)
check("an unrelated chord is simply wrong", wrong.verdict is Verdict.WRONG)

section("Analysis — key sets are carried for the visualiser")
swap = analyse(parse_stroke("-T"), parse_stroke("T"), "the", dictionary)
check("expected_keys populated", swap.expected_keys == {"-T"})
check("actual_keys populated", swap.actual_keys == {"T-"})

# ---------------------------------------------------------------------------------------
section("Lessons — every curated outline verified against the real dictionary")
lessons, warnings = validate_lessons(dictionary)
for lesson, original in zip(lessons, ALL_LESSONS):
    check(f"{lesson.key}: all {len(original.items)} items verified",
          len(lesson.items) == len(original.items),
          f"kept {len(lesson.items)}")
check("no validation warnings", not warnings, "; ".join(warnings[:3]))

sentences = sentence_lesson(dictionary)
check("sentence lesson built", len(sentences.items) == 10, f"{len(sentences.items)}")
check("sentences are multi-stroke", all(item.stroke_count > 1 for item in sentences.items))

# ---------------------------------------------------------------------------------------
section("Session — the drill loop")
profile = Profile()
items = list(lessons[0].items)
session = Session(items, dictionary, profile, lesson_key="test", hint_mode="adaptive")

first = session.prompt
check("session starts on the first prompt", first is not None and first.text == items[0].text)

result = session.submit(parse_stroke(items[0].outline))
check("a correct stroke advances", result is not None and result.advanced)
check("single-stroke prompt completes", result.prompt_complete)
check("counted as clean", session.prompts_correct == 1)

session.next_prompt()
before = session.prompt.text
bad = session.submit({"W-"} if "W-" not in session.prompt.current_stroke else {"-Z"})
check("a wrong stroke does not advance", bad is not None and not bad.advanced)
check("still on the same prompt", session.prompt.text == before)

retry = session.submit(session.prompt.current_stroke)
check("the retry is accepted", retry.advanced)
check("a missed prompt is not counted clean", session.prompts_correct == 1)
check("missed item was requeued", session.total > len(items))

section("Session — multi-stroke walking")
multi = Session(list(sentences.items[:1]), dictionary, profile, hint_mode="always")
prompt = multi.prompt
strokes = prompt.strokes
check("prompt reports its stroke count", prompt.stroke_count == len(strokes))
for index, stroke in enumerate(strokes):
    step = multi.submit(stroke)
    expected_complete = index == len(strokes) - 1
    if step.prompt_complete != expected_complete:
        check(f"stroke {index + 1} completion flag", False,
              f"got {step.prompt_complete}")
        break
else:
    check("walks through every stroke in order", True)
    check("completes on the final stroke", True)

section("Session — undo resets the current prompt")
undo_session = Session(list(sentences.items[:1]), dictionary, profile, hint_mode="always")
undo_session.submit(undo_session.prompt.strokes[0])
check("advanced one stroke", undo_session.prompt.stroke_index == 1)
undo_session.submit({"*"})
check("undo returns to the first stroke", undo_session.prompt.stroke_index == 0)

section("Session — hint fading")
fresh = Profile()
fade = Session(list(lessons[0].items), dictionary, fresh, hint_mode="adaptive")
check("an unseen item shows the full hint", fade.hint_level().shows_outline)
stats = fresh.stats_for(fade.prompt.text, fade.prompt.outline)
stats.streak = 1
check("after one clean run the outline text drops",
      not fade.hint_level().shows_outline and fade.hint_level().shows_chord)
stats.streak = 3
check("once solid, no hint at all", not fade.hint_level().shows_chord)
fade.prompt.errors = 1
check("an error brings the full hint back", fade.hint_level().shows_outline)

section("Board profiles")
from tinysteno import board as board_module
from tinysteno.board import BUILTIN_PROFILES, BoardProfile, BoardRegistry

for _profile in BUILTIN_PROFILES:
    problems = board_module.validate(_profile)
    check(f"{_profile.id} is a valid profile", not problems, "; ".join(problems[:2]))
    check(f"{_profile.id} declares a supported protocol",
          _profile.protocol in board_module.SUPPORTED_PROTOCOLS)

TINYMOD = board_module.BUILTIN_PROFILES[0]
check("tinymod4 is the default board", board_module.DEFAULT_PROFILE_ID == TINYMOD.id)
check("tinymod4 has 24 switches", len(TINYMOD.keys) == 24, str(len(TINYMOD.keys)))
check("tinymod4 exposes 22 distinct steno keys",
      len(TINYMOD.steno_keys) == 22, str(len(TINYMOD.steno_keys)))
check("both S switches report S-", len(TINYMOD.keys_for("S-")) == 2)
check("both star switches report *", len(TINYMOD.keys_for("*")) == 2)
# 10 columns plus the clear space either side of the centre asterisk column. Widened
# deliberately when the asterisks were separated out; a change here that was not intended
# means the layout has drifted.
check("tinymod4 extents are as intended",
      abs(TINYMOD.width - 10.8) < 1e-9 and abs(TINYMOD.height - 3.42) < 1e-9,
      f"{TINYMOD.width} x {TINYMOD.height}")

section("Board geometry — the asterisk column stands alone, thumbs tuck against it")


def _span(keys):
    """(left, right) x-extent of a group of keys."""
    return min(k.col for k in keys), max(k.col + k.width for k in keys)


for _profile in BUILTIN_PROFILES:
    _stars = _profile.keys_for("*")
    _thumbs = [k for k in _profile.keys if k.key in ("A-", "O-", "-E", "-U")]
    if not _stars or not _thumbs:
        continue

    _star_l, _star_r = _span(_stars)
    _others = [
        k for k in _profile.keys
        if k.key != "*" and k not in _thumbs and k.key != "#"
    ]

    # Nothing may sit inside the asterisk column's horizontal band.
    _intruders = [
        k.key for k in _others if k.col < _star_r and _star_l < k.col + k.width
    ]
    check(f"{_profile.id}: the asterisk column has clear space either side",
          not _intruders, str(sorted(set(_intruders))))

    # Nor directly beneath it, which is what "by themselves" means.
    _under = [k.key for k in _thumbs if k.col < _star_r and _star_l < k.col + k.width]
    check(f"{_profile.id}: no thumb sits under the asterisks", not _under, str(_under))

    _left_thumbs = [k for k in _thumbs if k.key in ("A-", "O-")]
    _right_thumbs = [k for k in _thumbs if k.key in ("-E", "-U")]
    check(f"{_profile.id}: left thumbs tuck against the asterisk column",
          abs(_span(_left_thumbs)[1] - _star_l) < 1e-9,
          f"left thumbs end at {_span(_left_thumbs)[1]}, asterisks start at {_star_l}")
    check(f"{_profile.id}: right thumbs tuck against the asterisk column",
          abs(_span(_right_thumbs)[0] - _star_r) < 1e-9,
          f"right thumbs start at {_span(_right_thumbs)[0]}, asterisks end at {_star_r}")

    # Symmetric about the centre of the asterisk block.
    _thumb_l, _thumb_r = _span(_thumbs)
    check(f"{_profile.id}: thumbs are symmetric about the asterisks",
          abs((_thumb_l + _thumb_r) / 2 - (_star_l + _star_r) / 2) < 1e-9)

    # Thumbs sit inboard of the banks they belong to, not out at the edges.
    check(f"{_profile.id}: thumbs sit inboard of the outer columns",
          _thumb_l > _span(_profile.keys_for("S-"))[0]
          and _thumb_r < _span(_profile.keys_for("-Z"))[1])

check("a board reports what it can write", TINYMOD.supports(parse_stroke("KAT")))
_no_z = BoardProfile(id="t", name="t", keys=tuple(
    k for k in TINYMOD.keys if k.key != "-Z"))
check("a board without -Z says so", not _no_z.supports({"-Z"}))
check("...but still writes chords it has", _no_z.supports(parse_stroke("KAT")))

_round = BoardProfile.from_dict(TINYMOD.to_dict())
check("a profile round-trips through JSON",
      [(k.key, k.col, k.row, k.width, k.height) for k in _round.keys]
      == [(k.key, k.col, k.row, k.width, k.height) for k in TINYMOD.keys])

_registry = BoardRegistry.load()
check("the registry loads every built-in", len(_registry) >= len(BUILTIN_PROFILES))
check("an unknown id falls back to the default", _registry.resolve("nope").id == TINYMOD.id)
check("no id is used twice",
      len({p.id for p in _registry}) == len(list(_registry)))

section("Board profiles — overlap detection catches typos")
_broken = BoardProfile(id="x", name="x", keys=(
    board_module.ProfileKey("S-", "S", 0, 0),
    board_module.ProfileKey("T-", "T", 0.5, 0),
))
check("overlapping keys are rejected",
      any("overlap" in problem for problem in board_module.validate(_broken)))
_bad_key = BoardProfile(id="x", name="x", keys=(
    board_module.ProfileKey("Q-", "Q", 0, 0),
))
check("a non-steno key is rejected",
      any("not a steno key" in problem for problem in board_module.validate(_bad_key)))

# ---------------------------------------------------------------------------------------
section("Board designer — guessing the steno keys from geometry alone")
from tinysteno import boardimage

# The built-in profiles are layouts whose right answer is known, so they double as the
# fixture for the guesser. standard23 is the one that matters: its tall S and asterisk
# span both rows, which is what breaks a naive row-by-row count.
for _profile in BUILTIN_PROFILES:
    _boxes = [
        boardimage.Box(k.col, k.row, k.width, k.height) for k in _profile.keys
    ]
    _guessed = boardimage.infer_keys(_boxes)
    _actual = [k.key for k in _profile.keys]
    _wrong = [
        f"{a}->{g}" for a, g in zip(_actual, _guessed) if a != g
    ]
    check(f"{_profile.id}: every key is guessed from its position",
          not _wrong, f"{len(_wrong)} wrong: {_wrong[:4]}")

# Steno fixes the banks at four columns left and five right, so a row wider than nine can
# only be widening in the middle. Guessing that the surplus is asterisks is what makes the
# 26-key split board come out right, and it is the only reading the notation allows.
_wide = boardimage.infer_keys([boardimage.Box(col, 0.0) for col in range(11)])
check("a row wider than nine puts the surplus in the asterisk column",
      _wide.count("*") == 2 and _wide[0] == "S-" and _wide[-1] == "-D", str(_wide))
_narrow = boardimage.infer_keys([boardimage.Box(col, 0.0) for col in range(6)])
check("a row too short to be standard is still split across both hands",
      {key_side(k) for k in _narrow} == {"left", "right"}, str(_narrow))

section("Board designer — reading a layout out of a picture")
import tempfile as _tempfile
from pathlib import Path as _Path

from tools.synthboard import render as _render_board, tinymod_layout as _tinymod_layout

_positions, _bare = _tinymod_layout()
with _tempfile.TemporaryDirectory() as _tmp:
    _photo = _render_board(_Path(_tmp) / "board.png", _positions, _bare)
    _found = boardimage.detect(_photo)

    check("a board is found at all", _found.ok, str(_found.warnings))
    check("every keycap is detected",
          _found.detected == len(_positions) - len(_bare),
          f"{_found.detected} of {len(_positions) - len(_bare)}")
    # The asterisk column is photographed with no keycaps on it, exactly as on the real
    # hardware, so those three switches exist only as gaps in otherwise even rows.
    check("switches with no keycap are inferred from the gaps",
          _found.filled == len(_bare), f"{_found.filled} of {len(_bare)}")
    check("the layout comes back the size it went in",
          len(_found.boxes) == len(_positions),
          f"{len(_found.boxes)} of {len(_positions)}")

    _by_key: dict[str, int] = {}
    for _key in _found.keys:
        _by_key[_key] = _by_key.get(_key, 0) + 1
    check("both S switches are recognised", _by_key.get("S-") == 2, str(_by_key.get("S-")))
    check("all three asterisks are recognised", _by_key.get("*") == 3, str(_by_key.get("*")))
    check("the thumbs land on the vowels",
          all(_by_key.get(k) == 1 for k in ("A-", "O-", "-E", "-U")), str(_by_key))
    check("the detected layout is a usable profile",
          not board_module.validate(BoardProfile(
              id="detected", name="detected",
              keys=tuple(
                  board_module.ProfileKey(k, k.strip("-"), b.col, b.row, b.width, b.height)
                  for b, k in zip(_found.boxes, _found.keys)
              ),
          )))

    # Key pitch is what every other coordinate is expressed in, so an error here scales
    # the whole layout. Measured along the top row, which the synthetic board draws on an
    # exact 1.0 pitch nine keys wide -- across rows would compare the offset thumbs
    # against the banks and measure nothing.
    _top = sorted(b.col for b in _found.boxes if b.row < 0.5)
    check("the top row has ten keys", len(_top) == 10, str(len(_top)))
    check("key pitch is recovered to within 2%",
          abs((_top[-1] - _top[0]) / 9 - 1.0) < 0.02,
          f"{(_top[-1] - _top[0]) / 9:.4f}")
    # Individual caps may sit a few percent out; an inferred one lands at the midpoint of
    # its gap, because nothing in the photo says where inside the gap it really was.
    _real = sorted(b.col for b in _found.boxes if b.row < 0.5 and not b.inferred)
    check("neighbouring detected caps sit one pitch apart",
          all(abs(b - a - 1.0) < 0.05 for a, b in zip(_real, _real[1:])
              if b - a < 1.5),
          str([round(b - a, 3) for a, b in zip(_real, _real[1:])]))

section("Fingering — every key has an owner")
from tinysteno import fingering

unassigned = [key for key in TINYMOD.steno_keys if fingering.finger_for(key) is None]
check("every key on the board is assigned to a finger", not unassigned, str(unassigned))
check("no key is claimed by two fingers",
      len({k for f in fingering.FINGERS for k in f.keys}) ==
      sum(len(f.keys) for f in fingering.FINGERS))
check("both S switches share one finger",
      len({fingering.finger_for(k.key).id for k in TINYMOD.keys if k.key == "S-"}) == 1)
check("the right pinky covers the outer two columns",
      set(fingering.FINGERS_BY_ID["r-pinky"].keys) == {"-T", "-S", "-D", "-Z"})
check("the asterisk is not tied to one hand",
      fingering.FINGERS_BY_ID["star"].is_shared)
check("fingering mirrors across hands",
      all(
          fingering.FINGERS_BY_ID[f"l-{role}"].role
          == fingering.FINGERS_BY_ID[f"r-{role}"].role
          for role in ("ring", "middle", "index", "thumb", "pinky")
      ))

section("Fingering — one finger, two keys")
doubles = fingering.double_presses(parse_stroke("TKOG"))
check("TKOG needs a double press", len(doubles) == 1)
check("and it is the left ring finger", doubles and doubles[0][0].id == "l-ring")
check("holding T and K", doubles and set(doubles[0][1]) == {"T-", "K-"})

check("OPB doubles on the right middle",
      [f.id for f, _ in fingering.double_presses(parse_stroke("OPB"))] == ["r-middle"])
check("TKPWO doubles on two fingers",
      len(fingering.double_presses(parse_stroke("TKPWO"))) == 2)
check("KAT needs no double press", not fingering.double_presses(parse_stroke("KAT")))

check("chord description names the fingers",
      "left ring" in fingering.describe_chord(parse_stroke("TKOG")))
check("chord description flags the pair",
      "together" in fingering.describe_chord(parse_stroke("TKOG")))
check("single-key chords read cleanly",
      fingering.describe_chord({"-T"}) == "right pinky T",
      fingering.describe_chord({"-T"}))
check("no double-press line when none is needed",
      fingering.describe_double_presses(parse_stroke("KAT")) == "")
check("double-press coaching mentions simultaneity",
      "same time" in fingering.describe_double_presses(parse_stroke("TKOG")))

section("Fingering — rest positions are derived from the board, not hand-placed")

_rests = {rest.finger.id: rest for rest in fingering.rest_positions(TINYMOD)}
check("every finger on the board gets a resting position",
      len(_rests) == 11, str(sorted(_rests)))

# A finger owning a stacked pair should rest on the seam between them, which is the whole
# point of the guide. That is the boundary row, not the middle of either key.
for _fid, _seam_row in (("l-ring", 1.0), ("l-middle", 1.0), ("r-index", 1.0),
                        ("r-middle", 1.0), ("r-pinky", 1.0), ("l-pinky", 1.0)):
    check(f"{_fid} rests on the seam between the rows",
          abs(_rests[_fid].y - _seam_row) < 1e-9, f"y={_rests[_fid].y}")

# A thumb pad belongs in the gap between its two keys, so it covers neither label.
for _fid, _keys in (("l-thumb", ("A-", "O-")), ("r-thumb", ("-E", "-U"))):
    _boundary = max(k.col + k.width for k in TINYMOD.keys_for(_keys[0]))
    check(f"{_fid} rests between its two keys",
          abs(_rests[_fid].x - _boundary) < 1e-9,
          f"x={_rests[_fid].x}, boundary={_boundary}")
    check(f"{_fid} pad stays narrow so it covers no label", _rests[_fid].width <= 0.8)

check("stacked-pair pads span their column",
      abs(_rests["l-ring"].width - 1.0) < 1e-9)
check("the right pinky pad spans both its columns",
      abs(_rests["r-pinky"].width - 2.0) < 1e-9, str(_rests["r-pinky"].width))

for _profile in BUILTIN_PROFILES[1:]:
    _rests = fingering.rest_positions(_profile)
    check(f"{_profile.id} gets resting positions too", bool(_rests))
    check(f"{_profile.id} rests all land on the board",
          all(0 <= r.x <= _profile.width and 0 <= r.y <= _profile.height for r in _rests))

check("a tall key gets a narrow pad, not one covering its label",
      all(r.width <= 0.8 for r in fingering.rest_positions(BUILTIN_PROFILES[1])
          if r.finger.id == "l-pinky"))

section("Fingering — the guide's examples are real")
from tinysteno.screens.fingers import DOUBLE_PRESS_EXAMPLES

for word, outline, action, _why in DOUBLE_PRESS_EXAMPLES:
    check(f"{outline} really writes “{word}”", dictionary.writes(outline, word))
    found = fingering.double_presses(parse_stroke(outline))
    check(f"{outline} really needs a double press", bool(found))
    if found:
        check(f"{outline}: guide names the right finger",
              found[0][0].label.lower() in action, f"{action} vs {found[0][0].label}")

section("Packaging — the PyInstaller exclude list is still honest")
import ast
import pathlib
import re

_spec = pathlib.Path("tinysteno.spec")
if not _spec.exists():
    check("tinysteno.spec present", False, "spec file missing")
else:
    _excluded = set(re.findall(r'"(PySide6\.\w+)"', _spec.read_text(encoding="utf-8")))
    _imported: set[str] = set()
    for _path in pathlib.Path(".").rglob("*.py"):
        if {"build", "dist"} & set(_path.parts):
            continue
        _tree = ast.parse(_path.read_text(encoding="utf-8"))
        for _node in ast.walk(_tree):
            if isinstance(_node, ast.ImportFrom) and (_node.module or "").startswith("PySide6"):
                _imported.add(_node.module)
            elif isinstance(_node, ast.Import):
                _imported.update(
                    alias.name for alias in _node.names if alias.name.startswith("PySide6")
                )

    _clash = _imported & _excluded
    check("no excluded Qt module is actually imported", not _clash, str(sorted(_clash)))
    check("the app still needs only QtCore, QtGui and QtWidgets",
          _imported == {"PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"},
          str(sorted(_imported)))
    check("the exclude list is doing real work", len(_excluded) > 30, f"{len(_excluded)}")

section("Storage — round trip")
import tempfile
from pathlib import Path

profile2 = Profile()
profile2.stats_for("cat", "KAT").record(True, 900, "miss")
profile2.stats_for("the", "-T").record(False, 0, "side_swap")
profile2.settings["port"] = "COM7"
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "profile.json"
    profile2.save(path)
    reloaded = Profile.load(path)
check("settings persist", reloaded.settings["port"] == "COM7")
check("item stats persist", reloaded.stats_for("cat", "KAT").correct == 1)
check("side swaps persist", reloaded.total_side_swaps == 1)
check("review queue rebuilds", any(row[0] == "the" for row in reloaded.review_items()))

section("Session — difficulty ordering puts weak material first")
ordered_profile = Profile()
lesson_items = list(lessons[0].items)
weak = lesson_items[3]
weak_stats = ordered_profile.stats_for(weak.text, weak.outline)
weak_stats.attempts, weak_stats.correct = 4, 1
ordered = order_by_difficulty(lesson_items, ordered_profile)
check("the weakest item is drilled first", ordered[0].text == weak.text, ordered[0].text)

# ---------------------------------------------------------------------------------------
print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for name in FAILURES:
        print(f"  - {name}")
    sys.exit(1)
print("All checks passed.")
