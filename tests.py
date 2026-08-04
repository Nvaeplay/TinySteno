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
