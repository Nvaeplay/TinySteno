"""Build the window, drive a simulated session, and render each screen to PNG.

Runs without a board attached: strokes are injected exactly as the serial thread would
deliver them, so this exercises the real drill path rather than a stub.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QApplication

from tinysteno import theme
from tinysteno.dictionary import StenoDictionary
from tinysteno.mainwindow import MainWindow
from tinysteno.protocol import parse_stroke
from tinysteno.storage import Profile

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "shots")
OUT.mkdir(parents=True, exist_ok=True)

app = QApplication(sys.argv)
app.setStyleSheet(theme.STYLESHEET)
app.setFont(QFont(theme.UI_FAMILY.split(",")[0], 10))

dictionary = StenoDictionary.load()

# A profile with some history, so Progress and the review deck have something to show.
profile = Profile()
profile.settings["auto_connect"] = False
for text, outline, good, bad in [
    ("cat", "KAT", 6, 0), ("the", "-T", 4, 3), ("on", "OPB", 2, 4),
    ("dog", "TKOG", 5, 1), ("mat", "PHAT", 3, 2), ("and", "SKP", 4, 0),
]:
    stats = profile.stats_for(text, outline)
    for _ in range(good):
        stats.record(True, 1400, "miss")
    for _ in range(bad):
        stats.record(False, 0, "miss")
        stats.errors["side_swap"] = stats.errors.get("side_swap", 0) + 1
        stats.side_swaps += 1
for text, outline, count in [("on", "OPB", 4), ("the", "-T", 3)]:
    pass
profile.stats_for("mat", "PHAT").errors["missing_keys"] = 3
profile.stats_for("dog", "TKOG").errors["wrong"] = 2

window = MainWindow(dictionary, profile)
window.resize(1180, 860)
window.show()
app.processEvents()


def settle(rounds: int = 6) -> None:
    for _ in range(rounds):
        QCoreApplication.processEvents()


def shot(name: str) -> None:
    settle()
    path = OUT / f"{name}.png"
    window.grab().save(str(path))
    print(f"  wrote {path}")


print("Rendering screens…")
shot("01-lessons")

window._navigate("fingers")
shot("02-finger-positions")
window.fingers._highlight_finger("l-ring")
shot("03-finger-highlighted")

window._navigate("custom")
window.custom.editor.setPlainText(
    "the quick brown fox jumps over the lazy dog\n"
    "supercalifragilistic zzzyzx cat mat"
)
window.custom._analyse()
shot("05-custom-text")

window._navigate("explore")
window.explore.finger_check.setChecked(True)
window.explore.show_stroke(parse_stroke("TKOG"))
shot("04-explore")

window._navigate("progress")
shot("06-progress")

# ---- the board designer, from a photo all the way to a saved profile -------------------
print("Designing a board from a photo…")
import tempfile
from pathlib import Path as _Path

from PySide6.QtWidgets import QMessageBox

from tinysteno import mainwindow as mainwindow_module
from tinysteno.board import BOARDS_DIR, BoardRegistry
from tinysteno.screens import editor as editor_module
from tools.synthboard import render as render_board, tinymod_layout

# Saving a board raises modal dialogs from two modules: the designer validates, and the
# window confirms the switch. Both have to be answered from here, or the smoke test hangs
# on a dialog nobody is there to click. Answering them keeps the real code path rather
# than reaching past it.
_dialogs: list[str] = []


class _Answers:
    Yes = QMessageBox.Yes

    @staticmethod
    def information(_parent, title, text):
        _dialogs.append(f"info: {title}")

    @staticmethod
    def warning(_parent, title, text):
        _dialogs.append(f"warning: {title} — {text.splitlines()[0]}")

    @staticmethod
    def question(_parent, title, _text):
        _dialogs.append(f"question: {title}")
        return _Answers.Yes


editor_module.QMessageBox = _Answers
mainwindow_module.QMessageBox = _Answers

with tempfile.TemporaryDirectory() as tmp:
    photo = render_board(_Path(tmp) / "board.png", *tinymod_layout())
    designer = window.editor
    designer._photo_path = photo
    designer.canvas.set_photo(QPixmap(str(photo)))
    designer.detect_button.setEnabled(True)
    designer._detect()
    settle()

    print(f"  detected {len(designer.canvas.keys)} keys from the photo")
    print(f"  status: {designer.status_label.text()}")

    designer.canvas.select([4])
    designer._on_selection()
    window._navigate("editor")
    shot("14-board-designer")

    # Learn mode: a stroke off the board names the selected key and moves on.
    designer.learn_button.setChecked(True)
    designer.canvas.select([0])
    window._on_stroke({"S-"}, {"S2-"})
    settle()
    print(f"  learned from a press: {designer.canvas.keys[0].key} "
          f"({designer.canvas.keys[0].switch}), {designer.learn_status.text()}")
    designer.learn_button.setChecked(False)

    designer.name_edit.setText("Smoke test board")
    designer._save()
    settle()

saved_path = BOARDS_DIR / "smoke-test-board.json"
try:
    reloaded = BoardRegistry.load().get("smoke-test-board")
    print(f"  saved and reloaded: {reloaded.name if reloaded else 'MISSING'}, "
          f"{len(reloaded.keys) if reloaded else 0} keys")
    print(f"  dialogs raised: {_dialogs}")
finally:
    if saved_path.exists():
        saved_path.unlink()
    window._on_settings_changed({**profile.settings, "board": "tinymod4"})
    settle()

# ---- switch boards and confirm everything follows --------------------------------------
print("Switching boards…")
for board_id in ("standard23", "split-ortho"):
    window._on_settings_changed({**profile.settings, "board": board_id})
    settle()
    window._navigate("fingers")
    settle()
    print(f"  {board_id}: {len(window.board.keys)} keys, "
          f"{len(window.lessons)} lessons, "
          f"{sum(len(l.items) for l in window.lessons)} prompts still drillable")
    shot(f"13-board-{board_id}")
window._on_settings_changed({**profile.settings, "board": "tinymod4"})
settle()
print(f"  back to tinymod4: {sum(len(l.items) for l in window.lessons)} prompts")

window._navigate("settings")
shot("07-settings")

# ---- drive a real drill ---------------------------------------------------------------
print("Driving the left/right lesson…")
window._start_lesson("left-right")
settle()
prompt = window.practice._session.prompt
print(f"  prompt: {prompt.text!r} expects {prompt.outline}")
shot("08-practice-chord-shown")

# Press the mirrored chord: exactly the mistake CLAUDE.md describes.
wrong = {"T-"} if prompt.outline == "-T" else parse_stroke(prompt.outline)
window._on_stroke(wrong, set())
settle()
print(f"  verdict shown: {window.practice.verdict_label.text()!r}")
print(f"  detail: {window.practice.detail_label.text()!r}")
shot("09-practice-side-swap")

# Now the correct chord, written *during* the error pause. This used to be discarded
# outright; it is the whole point of the change. Age the pause past its read debounce,
# which is all a moment of real time would have done, and take the real interrupt path
# rather than clearing the lock by hand.
window.practice._pause_started -= 1.0
window._on_stroke(parse_stroke(prompt.outline), set())
settle()
print(f"  mid-pause stroke accepted: {window.practice._pending is not None}")
print(f"  verdict shown: {window.practice.verdict_label.text()!r}")
shot("10-practice-correct")

# Finish the session to reach the summary. Each pause is ended by calling the very
# continuation its timer would have called, so no screen state is faked.
session = window.practice._session
guard = 0
while session is not None and not session.finished and guard < 200:
    guard += 1
    current = session.prompt
    if current is None:
        break
    window._on_stroke(current.current_stroke, set())
    settle(2)
    if window.practice._locked:
        window.practice._end_pause()
    settle(1)
    if window.practice._session is None:
        break
settle()
if window.stack.currentWidget() is not window.summary:
    window.practice._finish()
settle()
shot("11-summary")

print("\nSession summary tiles:")
print(f"  prompts:  {window.summary.tile_prompts.value_label.text()}")
print(f"  accuracy: {window.summary.tile_accuracy.value_label.text()}")
print(f"  mix-ups:  {window.summary.tile_swaps.value_label.text()}")
print(f"  headline: {window.summary.headline.text()!r}")

window.close()
print("\nGUI smoke test finished with no exceptions.")
