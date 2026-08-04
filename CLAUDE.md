# Stenography Context — TinyMod4 + Plover

Reference context for building stenography-related applications. Every fact here was verified
against real hardware on 2026-07-29, not taken from documentation. Where the vendor repo and the
physical board disagreed, **the board won** — see "Hard-won lessons".

---

## 1. Hardware

**TinyMod4** — open-source steno keyboard, CERN OHL v1.2, designed by Charley Shattuck.
Repo: `github.com/CharleyShattuck/Steno-Keyboard-Arduino` (`TinyMod4.ino`, `TinyMod4-setup.pdf`).
Arduino/Adafruit ItsyBitsy-class MCU + MCP23017 I2C port expander at address `0x20`.

USB identity — composite device, **both** interfaces always enumerate regardless of jumper position:

```
VID_239A & PID_800E
  MI_00  →  USB Serial Device (COM5)   [CDC serial, driver: usbser]
  MI_02  →  HID Keyboard Device         [driver: kbdhid]
```

**The presence of COM5 tells you nothing about which mode the firmware is in.** The USB descriptor
is fixed at compile time; the jumper only selects which interface the firmware actually writes to.

### Two firmware modes (selected by a jumper, read at power-up)

| Mode | Sticky note | Behavior |
|---|---|---|
| NKRO | `NKRO = A2Z` | HID keyboard. Types each steno key's **own letter** (K key → literal `k`) plus delimiter spaces. A solder-test mode for Notepad. **Not usable with Plover.** |
| Serial | `Serial = GeminiPiper` | Emits Gemini PR frames on the CDC port. **This is the Plover mode.** |

Changing the jumper requires a full USB power-cycle — it is read once at boot.

---

## 2. Plover

Installed via winget. Note winget lags GitHub releases (4.0.2 vs 5.4.0 as of 2026-07-29).

```bash
winget install --id OpenStenoProject.Plover -e
```

| Item | Path |
|---|---|
| Executable | `C:\Program Files\Open Steno Project\Plover 4.0.2\plover.exe` |
| Process name | `pythonw` (two processes; the GUI one has MainWindowTitle `Plover`) |
| Config dir | `%LOCALAPPDATA%\plover\plover\` |
| Config | `plover.cfg` |
| Main dictionary | `main.json` (~4.3 MB) |
| User dictionary | `user.json` |
| Command dictionary | `commands.json` |
| App log | `plover.log` |
| Stroke log | `strokes.log` (only written when stroke logging is enabled) |

### Working config

```ini
[Machine Configuration]
auto_start = True
machine_type = Gemini PR

[Gemini PR]
port = COM5
baudrate = 9600
bytesize = 8
parity = N
stopbits = 1
timeout = 2.0
xonxoff = False
rtscts = False

[Logging Configuration]
enable_stroke_logging = True
enable_translation_logging = True

[Output Configuration]
undo_levels = 100
```

`machine_type` **alone is not enough.** Without the matching `[Gemini PR]` section naming the port,
Plover logs `WARNING: Serial port is not open: None`, silently falls back to `Keyboard`, and saves
that fallback to `plover.cfg`. There is no error dialog. Always verify via `plover.log`:

```
INFO: setting machine: Gemini PR     ← success (and NO "Serial port is not open" line)
```

Plover force-killed (`Stop-Process -Force`) will not persist config changes on exit — useful when
writing `plover.cfg` externally, since a clean exit would overwrite it.

---

## 3. Gemini PR protocol

6-byte frames. **Byte 0 always has the MSB set (`0x80`)** — that's the frame-start marker, so
resynchronization is trivial: any byte with the high bit set begins a frame.

Bits within each byte run **MSB → LSB = left → right** in these tables (`0x40, 0x20, 0x10, 0x08,
0x04, 0x02, 0x01`). Byte 0's `0x80` is the marker, not a key.

| Byte | 0x40 | 0x20 | 0x10 | 0x08 | 0x04 | 0x02 | 0x01 |
|---|---|---|---|---|---|---|---|
| 0 | Fn | #1 | #2 | #3 | #4 | #5 | #6 |
| 1 | S1- | S2- | T- | K- | P- | W- | H- |
| 2 | R- | A- | O- | *1 | *2 | res | res |
| 3 | pwr | *3 | *4 | -E | -U | -F | -R |
| 4 | -P | -B | -L | -G | -T | -S | -D |
| 5 | #7 | #8 | #9 | #A | #B | #C | -Z |

One frame = one complete chord, sent on release. There is no key-down/key-up stream.

### Verified captures from real hardware

```
80 08 20 00 04 00   →  K- A- -T   →  "KAT"  →  "cat"
80 08 20 00 10 00   →  K- A- -L   →  "KAL"  →  (undefined)
```

Check: byte 1 `0x08` = 4th entry = `K-`; byte 2 `0x20` = 2nd entry = `A-`; byte 4 `0x04` = 5th
entry = `-T`. Confirmed end-to-end — Plover logged `Stroke(KAT : ['K-','A-','-T'])` → `"cat"`.

### Reading the port yourself

**DTR must be asserted or the board sends nothing.** The firmware gates transmission on the host
raising DTR (Arduino's `if (Serial)`). `.NET SerialPort` defaults `DtrEnable = false`, so the port
opens successfully and returns **zero bytes forever** — indistinguishable from dead hardware. This
cost hours to find.

```powershell
$port = New-Object System.IO.Ports.SerialPort "COM5", 9600, "None", 8, "One"
$port.DtrEnable = $true    # REQUIRED
$port.RtsEnable = $true
$port.Open()
```

pyserial asserts DTR on open by default, so Plover is unaffected.

**COM5 is exclusive.** Only one process may hold it. A debug listener blocks Plover and vice versa —
if Plover reports a connection failure, check that nothing else owns the port.

---

## 4. Steno layout

23 keys. Standard English Stenotype. Left bank starts a word, right bank ends it; vowels are thumbs.

```
 S-  T-  P-  H-  *      -F  -P  -L  -T  -D
 S-  K-  W-  R-  *      -R  -B  -G  -S  -Z
         A-  O-             -E  -U
```

- The two leftmost keys **both** send `S-` (one tall key on a real steno machine). Same for the two `*` keys.
- Notation is positional: `T-` is the left-hand T, `-T` is the right-hand T. **Different keys, different meanings.**
- Keys in a stroke are pressed simultaneously and always read left-to-right. Press order is irrelevant.
- There is no `C`, `X`, or `Y` key — steno encodes sound, not spelling. "cat" is `KAT`.
- `*` alone = **undo** the previous translation.

### QWERTY equivalents (Plover's `Keyboard` machine)

Relevant only if supporting keyboard input as a fallback. Note this maps by **position**, not letter:

```
 q   w   e   r   t         u   i   o   p   [
 a   s   d   f   g         j   k   l   ;   '
         c   v                 n   m
```

Aligned with the layout above: `q`/`a`→`S-`, `w`→`T-`, `s`→`K-`, `e`→`P-`, `d`→`W-`, `r`→`H-`,
`f`→`R-`, `t`/`g`→`*`, `u`→`-F`, `j`→`-R`, `i`→`-P`, `k`→`-B`, `o`→`-L`, `l`→`-G`, `p`→`-T`,
`;`→`-S`, `[`→`-D`, `'`→`-Z`, `c`→`A-`, `v`→`O-`, `n`→`-E`, `m`→`-U`.

So `s`+`c`+`p` on a normal keyboard produces "cat".

⚠️ In `Keyboard` mode Plover captures **every** keyboard on the machine and mangles all normal
typing. Serial mode has no such problem. Prefer serial.

---

## 5. Dictionary format

Flat JSON, `{"STROKE": "output"}`, one entry per line. Multi-stroke outlines join with `/`
(e.g. `"KAT/WAL": "casual"`). Plover loads `user.json`, `commands.json`, `main.json` in priority
order — earlier files win.

Plover **retroactively rewrites output** as multi-stroke outlines complete: stroking `KAT` emits
"cat", then a following `WAL` replaces it with "casual". Any app rendering live output must handle
retroactive correction, not append-only text.

### Output notation

| Notation | Meaning |
|---|---|
| `{^}` | attach — suppress the space on that side |
| `{^ ^}` | insert a literal space |
| `{^^}` | delete the space (glue words) |
| `{-\|}` | capitalize the next word |
| `{.}` | period (also applies sentence-end spacing/capitalization) |
| `{^s}`, `{^ed}` | suffixes that hook onto the previous word |

**Spacing is automatic** — one stroke is one word and Plover prepends a space to each translation
(default: space *before* output). There is no space key. Many small strokes therefore produce
heavily-spaced output, which is a useful diagnostic signature.

### Verified strokes (present in this `main.json`)

```
-T the      KAT cat     SAT sat     PHAT mat    HAT hat
TKOG dog    OPB on      SKP and     AEU a       EU I
RED red     PWEUG big   RUPB run    WORLD world OEFR over
TPOBGS fox  KWEUBG quick  PWROUPB brown  HRAEZ lazy
TP-PL .     -PL .       S-P space   TK-LS delete-space
KPA capitalize    H-PB hyphen
```

⚠️ `THE` is **"they"**, not "the". The word "the" is the single key `-T`. Steno notation resembles
spelling but is not spelling — **always verify strokes against `main.json` before presenting them
to a user.** `-PL` is a valid shorter period than `TP-PL`.

---

## 6. Hard-won lessons

1. **The repo's `TinyMod4.ino` did not match the flashed firmware.** The repo showed a QWERTY-letter
   NKRO mapping; the actual board typed steno key letters. Treat vendor source as a hint, verify
   against hardware.
2. **DTR gating** makes working hardware look dead. See §3.
3. **Plover's silent fallback** to `Keyboard` when serial config is incomplete. See §2.
4. **Serial port exclusivity** — debug tooling and Plover cannot both hold COM5.
5. **`strokes.log` is the ground truth** for what Plover actually received, and is far more reliable
   than asking a user what they pressed. Format:
   ```
   2026-07-29 19:17:20,708 Stroke(KAT : ['K-', 'A-', '-T'])
   2026-07-29 19:17:20,708 Translation(('KAT',) : "cat")
   ```
   A leading `*` on a line (`*Stroke`, `*Translation`) marks an undo/retroactive replacement.
   It logs everything written, so treat it as sensitive and disable when not debugging.

---

## 7. User context

Beginner stenographer, day one. Owns the hardware, is learning on Plover's default English
Stenotype dictionary. Confirmed working end-to-end: strokes `-T KAT SAT OPB -T` reliably.

**Known weak spot: left/right hand confusion.** Observed errors were all the same root cause —
reaching for the left bank where the right was needed:

```
T   → "it"          instead of  -T   → "the"
POB → "possible"    instead of  OPB  → "on"
```

A practice or drill application should specifically detect and coach this class of error: same
letters, wrong side. It is the dominant beginner mistake for someone coming from QWERTY.

Learning resources in use: Typey Type (`didoesdigital.com/typey-type`), Art of Chording
(`artofchording.com`), Learn Plover!, Plover Discord.

---
## 8. app brainstorm

# TinyMod4 Steno Trainer — Product Brief

## The idea in one sentence

Build a Windows 11 desktop app that teaches a learner to use a TinyMod4 steno device through focused, game-like practice: it shows what to write, displays the exact chord to press on a visual TinyMod keyboard, and gives immediate feedback when the device produces the intended text.

## What problem the app solves

Learning stenography is difficult because a beginner must connect three things at once:

1. The English word or sound they want to write.
2. The physical chord to press on the TinyMod4.
3. The text that chord produces through the configured steno dictionary.

Existing typing trainers measure speed, but they do not explain the chord or help someone build the physical muscle memory needed for stenography. This application should be a deliberate-practice coach, not just a WPM test.

## Product vision

Think of it as **Monkeytype meets a TinyMod4 driving instructor**. The learner practices real words, phrases, and eventually full passages. Before and during each exercise, the on-screen TinyMod4 diagram lights up the relevant keys, so the learner can see the chord, press it on their physical device, and immediately learn whether it produced the expected output.

The feeling should be calm, encouraging, and highly visual: less like studying a keyboard chart and more like learning an instrument through short, repeatable drills.

## Core experience

1. The learner connects their TinyMod4 and selects their existing steno configuration/dictionary.
2. They choose a practice mode or paste in their own text.
3. The app presents the next word, phrase, or lesson.
4. A visual TinyMod4 keyboard flashes/highlights every key in the correct chord.
5. The learner presses the chord on the physical device.
6. The app receives the resulting stroke/text, compares it with the expected answer, and gives clear feedback.
7. The app adapts by repeating difficult chords and tracking accuracy, consistency, and speed.

## Essential features for a first useful version

### 1. Interactive TinyMod4 visualizer

- An accurate, easily readable diagram of the user’s TinyMod4 layout.
- Keys light up together to show a chord, using distinct colors for left-hand keys, vowels, right-hand keys, and special keys if useful.
- Optional animation: show the chord before the learner attempts it, then replay it after an error.
- A tap/click mode so learners can explore the key layout without their physical device connected.

### 2. Guided word and chord drills

- Start with individual keys and simple chords, then introduce common words, briefs, and multi-stroke outlines.
- Show the target word and its chord/outlines.
- Support “demonstrate,” “practice with hints,” and “test without hints” states.
- Let a learner repeat a single chord until it feels automatic.

### 3. Custom-text practice

- A large paste box for any text: personal notes, books in the public domain, work vocabulary, or course material.
- Convert the pasted text into a practice queue, showing the best matching steno outline from the learner’s dictionary.
- Flag words with no known outline instead of silently failing, and let the learner skip, add a note, or choose an alternate outline.

### 4. Live device feedback

- Capture the TinyMod4’s strokes and resulting text in real time.
- Clearly distinguish: correct chord, correct text but different outline, wrong chord, and unrecognized input.
- Show what was actually pressed alongside what was expected.
- Include a connection/status indicator so setup problems are not confused with practice mistakes.

### 5. Progress and review

- Track accuracy, repetitions, response time, and error patterns by chord/word.
- Build an automatic “needs review” deck from missed or slow material.
- Keep sessions short and visible: e.g., 10 chords, 5 minutes, or one paragraph.

## Practice modes worth considering

| Mode | Learner goal | How it works |
| --- | --- | --- |
| Learn a chord | Build first muscle memory | See a chord, press it correctly several times, then fade the visual cue. |
| Word drills | Associate common words with outlines | Practice selected vocabulary, briefs, or dictionary entries. |
| Copy practice | Build fluent writing | Steno a sentence or passage at a comfortable pace, Monkeytype-style. |
| Listen and steno | Build realtime skills later | Hear dictated words/sentences and write them without looking. |
| Error review | Fix weak spots | The app serves only recent misses, hesitations, or confusing chords. |
| Custom vocabulary | Learn words that matter | Import/paste a word list or text for work, school, hobbies, or names. |

## Helpful learning design ideas

- **Progressive hint fading:** first show the whole chord, then only the word, then remove hints completely.
- **Spaced repetition:** reintroduce hard chords after a few successful items, then again in later sessions.
- **Minimal correction loop:** when the learner misses, briefly show “expected / pressed / output,” then immediately let them try again. Avoid punitive red screens.
- **Confusion pairs:** group similar chords that are often mixed up and practice them back-to-back.
- **Stroke-aware feedback:** teach the actual stroke, not merely whether the final text looked correct. This matters when multiple outlines can produce the same word.
- **Multi-stroke coaching:** for a word that needs several strokes, illuminate each stroke in sequence and show progress through the outline.

## Important technical questions to answer before building

1. **How does TinyMod4 connect and report strokes?** Determine whether it acts as a standard keyboard, exposes serial/HID data, uses Plover, or needs a bridge application. A standard keyboard only provides translated characters, while raw strokes allow much richer coaching.
2. **What source defines the chord-to-word mapping?** Ideally import/export the exact dictionary used by the learner (for example, a Plover-compatible dictionary) so the practice app teaches their real setup.
3. **What is the canonical TinyMod4 layout?** Create the visual keyboard from the actual hardware key positions and label conventions. The visualizer must match the physical device exactly.
4. **How should the app handle alternate outlines?** Mark a stroke as correct if it is one of several accepted outlines, while still allowing a lesson to require a particular outline when that is the teaching goal.

## Suggested first milestone (MVP)

Make the smallest version that proves the learning loop:

1. Windows 11 desktop app with a static, accurate TinyMod4 keyboard graphic.
2. A short built-in lesson of 20–50 known words/chords.
3. “Show chord → learner presses it → app reports correct/incorrect.”
4. Simple session results: correct, missed, and time per prompt.
5. A paste-text box that creates a word list and identifies words covered by the available dictionary.

Do not begin with competitive WPM, accounts, cloud sync, elaborate gamification, or full dictation. The high-value proof is whether a new learner can see a chord, physically practice it, and improve more quickly than they could with a static chart.

## Later possibilities

- Daily practice plans and streaks.
- Import lessons or word lists from existing steno courses.
- A dictionary editor for creating personal briefs.
- Side-by-side comparison of alternate outlines and their tradeoffs.
- Replayable “hand position” or keypress animations.
- Audio dictation and adaptive speed control.
- A compact always-on-top coach mode beside Plover or transcription software.
- Exportable progress reports for a teacher or practice partner.

## A concise product statement

**TinyMod4 Steno Trainer is a Windows 11 practice companion that turns a learner’s real TinyMod4 layout and dictionary into visual, adaptive drills. It teaches the connection between word, chord, physical press, and written output—so beginners can build reliable stenography muscle memory before focusing on speed.**