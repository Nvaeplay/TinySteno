"""The board designer: turn a photo of a steno keyboard into a profile you can practise on.

Three ways in, because no one of them is reliable on its own:

* **From a photo.** The detector finds the keycaps and guesses the steno key for each one.
  It gets a well-lit, square-on shot of a standard arrangement right, and it gets an
  awkward one wrong, so everything it produces is editable.
* **From a built-in.** Start with a board that is close and move what differs.
* **By hand.** Double-click to add a key, drag it where it goes.

And one way to settle what the photo cannot: press the key on the actual hardware. The
board reports which switch fired, so the layout can be labelled from the device rather than
from a guess -- which is the only way to know what an unlabelled switch really is.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .. import boardimage
from ..board import (
    BOARDS_DIR,
    BUILTIN_PROFILES,
    BoardProfile,
    validate,
)
from ..protocol import STENO_ORDER, format_stroke, sort_keys
from ..widgets.common import Card, faint, heading
from ..widgets.layoutcanvas import EditKey, LayoutCanvas

_SNAP_STEPS = [
    ("Free", 0.0),
    ("0.05", 0.05),
    ("0.1", 0.1),
    ("0.25", 0.25),
    ("0.5", 0.5),
    ("Whole key", 1.0),
]

_IMAGE_FILTER = "Photos (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All files (*)"


def slugify(text: str) -> str:
    """A filename-safe id from a board name."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "my-board"


class BoardEditorScreen(QWidget):
    """Draw a board layout over a photo of the real thing."""

    board_saved = Signal(str)          # Profile id, once written to the boards folder.
    learn_mode_changed = Signal(bool)  # So the window knows to route strokes here.

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self._learning = False
        self._photo_path: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(14)

        root.addWidget(heading("Board designer"))
        root.addWidget(
            faint(
                "Load a photo of your keyboard and the keys are found for you, then drag "
                "them until they match. Detection is a starting point, not an answer — a "
                "shot taken straight down in even light works best, and anything it gets "
                "wrong is yours to fix. Double-click an empty spot to add a key; drag a "
                "box round several to move them together."
            )
        )

        # The canvas exists before the controls, because every control acts on it.
        self.canvas = LayoutCanvas()
        self.canvas.selection_changed.connect(self._on_selection)
        self.canvas.layout_changed.connect(self._on_layout_changed)

        root.addLayout(self._build_toolbar())
        root.addLayout(self._build_photo_bar())

        middle = QHBoxLayout()
        middle.setSpacing(14)

        frame = QFrame()
        frame.setObjectName("Card")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        frame_layout.addWidget(self.canvas)
        middle.addWidget(frame, stretch=1)

        middle.addWidget(self._build_inspector())
        root.addLayout(middle, stretch=1)

        root.addLayout(self._build_footer())

        self._set_keys_from(BUILTIN_PROFILES[0])
        self.name_edit.setText("My board")
        self._on_selection()

    # ---- construction ---------------------------------------------------------------

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(8)

        load = QPushButton("Load a photo…")
        load.clicked.connect(self._load_photo)
        bar.addWidget(load)

        self.detect_button = QPushButton("Find the keys")
        self.detect_button.setObjectName("Primary")
        self.detect_button.setEnabled(False)
        self.detect_button.clicked.connect(self._detect)
        bar.addWidget(self.detect_button)

        bar.addSpacing(12)
        bar.addWidget(QLabel("Start from"))
        self.template_combo = QComboBox()
        for profile in BUILTIN_PROFILES:
            self.template_combo.addItem(profile.name, profile.id)
        bar.addWidget(self.template_combo)
        use_template = QPushButton("Use")
        use_template.clicked.connect(self._use_template)
        bar.addWidget(use_template)

        bar.addStretch()
        return bar

    def _build_photo_bar(self) -> QHBoxLayout:
        """Backdrop controls, on their own row so nothing here squeezes the actions above."""
        bar = QHBoxLayout()
        bar.setSpacing(8)

        caption = QLabel("Backdrop")
        caption.setObjectName("Faint")
        bar.addWidget(caption)

        self.photo_visible = QCheckBox("Show")
        self.photo_visible.setChecked(True)
        self.photo_visible.toggled.connect(self.canvas.set_photo_visible)
        bar.addWidget(self.photo_visible)

        self.photo_mode = QCheckBox("Drag the photo, not the keys")
        self.photo_mode.setToolTip(
            "Move the photo itself, to line the backdrop up under the keys. "
            "The square at its bottom-right corner scales it."
        )
        self.photo_mode.toggled.connect(self.canvas.set_photo_mode)
        bar.addWidget(self.photo_mode)

        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setFixedWidth(130)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(55)
        self.opacity.setToolTip("How strongly the photo shows through")
        self.opacity.valueChanged.connect(
            lambda value: self.canvas.set_photo_opacity(value / 100)
        )
        bar.addWidget(self.opacity)

        fit = QPushButton("Fit to keys")
        fit.clicked.connect(self.canvas.fit_photo)
        bar.addWidget(fit)

        bar.addStretch()
        return bar

    def _build_inspector(self) -> QWidget:
        panel = Card(padding=16)

        title = QLabel("Selected key")
        title.setObjectName("CardTitle")
        panel.body.addWidget(title)

        self.selection_label = faint("Nothing selected")
        panel.body.addWidget(self.selection_label)

        form = QFormLayout()
        form.setSpacing(9)

        self.key_combo = QComboBox()
        for key in STENO_ORDER:
            self.key_combo.addItem(key, key)
        self.key_combo.currentIndexChanged.connect(self._apply_key)
        form.addRow("Steno key", self.key_combo)

        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("printed on the cap")
        self.label_edit.textEdited.connect(self._apply_label)
        form.addRow("Label", self.label_edit)

        self.switch_edit = QLineEdit()
        self.switch_edit.setPlaceholderText("e.g. S1-, *3")
        self.switch_edit.textEdited.connect(self._apply_switch)
        form.addRow("Switch", self.switch_edit)

        panel.body.addLayout(form)

        # Two across rather than four: at four the boxes are narrower than the numbers in
        # them, and a coordinate you cannot read is worse than one more row of panel.
        grid = QGridLayout()
        grid.setSpacing(7)
        self.spins: dict[str, QDoubleSpinBox] = {}
        for position, (field, caption) in enumerate(
            (("col", "Across"), ("row", "Down"), ("width", "Width"), ("height", "Height"))
        ):
            spin = QDoubleSpinBox()
            spin.setRange(-50.0 if field in ("col", "row") else 0.1, 60.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            spin.setMinimumWidth(78)
            spin.valueChanged.connect(
                lambda value, name=field: self._apply_geometry(name, value)
            )
            caption_label = QLabel(caption)
            caption_label.setObjectName("Faint")
            row, column = divmod(position, 2)
            grid.addWidget(caption_label, row * 2, column)
            grid.addWidget(spin, row * 2 + 1, column)
            self.spins[field] = spin
        panel.body.addLayout(grid)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        for text, slot in (
            ("Duplicate", self.canvas.duplicate_selected),
            ("Delete", self.canvas.delete_selected),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        panel.body.addLayout(buttons)

        tools_title = QLabel("Several at once")
        tools_title.setObjectName("CardTitle")
        panel.body.addWidget(tools_title)
        panel.body.addWidget(
            faint("Drag a box round a row or a bank, then straighten it in one go.")
        )

        row_buttons = QHBoxLayout()
        row_buttons.setSpacing(6)
        align = QPushButton("Line up")
        align.setToolTip("Put every selected key on one row, at one height.")
        align.clicked.connect(self.canvas.align_selected_rows)
        spread = QPushButton("Space evenly")
        spread.setToolTip("Even out the gaps, holding the outermost keys still.")
        spread.clicked.connect(self.canvas.space_selected_evenly)
        row_buttons.addWidget(align)
        row_buttons.addWidget(spread)
        panel.body.addLayout(row_buttons)

        learn_title = QLabel("Learn from the board")
        learn_title.setObjectName("CardTitle")
        panel.body.addWidget(learn_title)
        panel.body.addWidget(
            faint(
                "Select a key, arm this, then press that key on your keyboard. Whatever "
                "the board reports is written into the layout, and the selection moves on "
                "— so you can walk the whole board once and have it labelled from the "
                "hardware rather than from a guess."
            )
        )
        self.learn_button = QPushButton("Press keys on my board")
        self.learn_button.setCheckable(True)
        self.learn_button.toggled.connect(self._toggle_learn)
        panel.body.addWidget(self.learn_button)

        self.learn_status = faint("")
        panel.body.addWidget(self.learn_status)

        panel.body.addStretch()

        # Scrolled, so the explanatory text at the bottom cannot be clipped off on a
        # short window -- which is exactly where someone reads it for the first time.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(310)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(panel)
        return scroll

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setSpacing(10)

        footer.addWidget(QLabel("Name"))
        self.name_edit = QLineEdit()
        self.name_edit.setFixedWidth(180)
        self.name_edit.setPlaceholderText("My board")
        footer.addWidget(self.name_edit)

        footer.addSpacing(10)
        footer.addWidget(QLabel("Snap"))
        self.snap_combo = QComboBox()
        for caption, value in _SNAP_STEPS:
            self.snap_combo.addItem(caption, value)
        self.snap_combo.setCurrentIndex(1)
        self.snap_combo.setFixedWidth(112)
        self.snap_combo.currentIndexChanged.connect(
            lambda: self.canvas.set_snap(float(self.snap_combo.currentData()))
        )
        footer.addWidget(self.snap_combo)
        footer.addSpacing(10)

        assign = QPushButton("Guess the keys")
        assign.setToolTip(
            "Work out which steno key each box is from where it sits. Run it again after "
            "moving things."
        )
        assign.clicked.connect(self._auto_assign)
        footer.addWidget(assign)

        tidy = QPushButton("Tidy up")
        tidy.setToolTip("Pull the layout back to the origin, so nothing sits in a margin.")
        tidy.clicked.connect(self.canvas.normalise)
        footer.addWidget(tidy)

        footer.addStretch()

        # One line, and elided rather than wrapped -- a long "saved to ..." path must not
        # reflow the footer and shove the save button off the end of it.
        self.status_label = QLabel("")
        self.status_label.setObjectName("Faint")
        self.status_label.setWordWrap(False)
        self.status_label.setMaximumWidth(240)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        footer.addWidget(self.status_label)

        save = QPushButton("Save board")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        footer.addWidget(save)

        return footer

    # ---- photo ----------------------------------------------------------------------

    def _load_photo(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "A photo of your keyboard", str(Path.home()), _IMAGE_FILTER
        )
        if not chosen:
            return
        pixmap = QPixmap(chosen)
        if pixmap.isNull():
            QMessageBox.warning(
                self, "Could not open that photo",
                "That file could not be read as an image. JPEG and PNG are safest; "
                "an iPhone HEIC needs exporting as JPEG first.",
            )
            return
        self._photo_path = Path(chosen)
        self.canvas.set_photo(pixmap)
        self.canvas.fit_photo()
        self.detect_button.setEnabled(True)
        self.photo_visible.setChecked(True)
        self._set_status(f"Loaded {self._photo_path.name}. Now find the keys.")

    def _detect(self) -> None:
        if self._photo_path is None:
            return
        self.setCursor(Qt.WaitCursor)
        try:
            result = boardimage.detect(self._photo_path)
        finally:
            self.unsetCursor()

        if not result.ok:
            QMessageBox.information(
                self, "No keys found",
                "\n\n".join(result.warnings)
                or "No keycaps could be picked out of that photo.",
            )
            return

        keys = [
            EditKey(
                key=steno_key,
                label=steno_key.strip("-"),
                col=box.col, row=box.row, width=box.width, height=box.height,
                inferred=box.inferred,
            )
            for box, steno_key in zip(result.boxes, result.keys)
        ]
        self.canvas.set_keys(keys)
        # The detection reports where the photo sits in the same units as the boxes, so
        # the backdrop lines up with them without anyone having to nudge it.
        self.canvas.set_photo(
            self.canvas.photo,
            QRectF(result.photo_col, result.photo_row,
                   result.photo_width, result.photo_height),
        )

        found = result.detected
        filled = result.filled
        message = f"Found {found} keycap(s)"
        if filled:
            message += f" and {filled} gap(s) where a cap looks to be missing"
        self._set_status(message + ". Check every key before saving.")

        if result.warnings:
            QMessageBox.information(self, "Worth checking", "\n\n".join(result.warnings))

    def _use_template(self) -> None:
        profile = next(
            (p for p in BUILTIN_PROFILES if p.id == self.template_combo.currentData()),
            BUILTIN_PROFILES[0],
        )
        self._set_keys_from(profile)
        self._set_status(f"Started from {profile.name}.")

    def _set_keys_from(self, profile: BoardProfile) -> None:
        self.canvas.load_profile(profile)
        if self.canvas.photo is not None:
            self.canvas.fit_photo()

    # ---- editing ---------------------------------------------------------------------

    def _auto_assign(self) -> None:
        keys = self.canvas.keys
        if not keys:
            return
        boxes = [
            boardimage.Box(key.col, key.row, key.width, key.height) for key in keys
        ]
        for key, guess in zip(keys, boardimage.infer_keys(boxes)):
            key.key = guess
            key.label = guess.strip("-")
        self.canvas.layout_changed.emit()
        self.canvas.update()
        self._on_selection()
        self._set_status("Keys guessed from their positions.")

    def _on_selection(self) -> None:
        selected = self.canvas.selected_keys()
        self._loading = True

        enabled = bool(selected)
        for widget in (self.key_combo, self.label_edit, self.switch_edit):
            widget.setEnabled(enabled)
        for spin in self.spins.values():
            spin.setEnabled(len(selected) == 1)

        if not selected:
            self.selection_label.setText("Nothing selected — click a key, or drag a box.")
        elif len(selected) == 1:
            key = selected[0]
            self.selection_label.setText(
                f"{key.key} at {key.col:g}, {key.row:g}"
                + ("   ·   filled from a gap" if key.inferred else "")
            )
            self.key_combo.setCurrentIndex(max(0, self.key_combo.findData(key.key)))
            self.label_edit.setText(key.label)
            self.switch_edit.setText(key.switch)
            for field, spin in self.spins.items():
                spin.setValue(getattr(key, field))
        else:
            self.selection_label.setText(f"{len(selected)} keys selected")
            self.label_edit.setText("")
            self.switch_edit.setText("")

        self._loading = False

    def _on_layout_changed(self) -> None:
        selected = self.canvas.selected_keys()
        if len(selected) == 1 and not self._loading:
            self._loading = True
            for field, spin in self.spins.items():
                spin.setValue(getattr(selected[0], field))
            self._loading = False

    def _apply_key(self) -> None:
        if self._loading:
            return
        key = str(self.key_combo.currentData())
        self.canvas.update_selected(key=key, label=key.strip("-"))
        self._loading = True
        self.label_edit.setText(key.strip("-"))
        self._loading = False

    def _apply_label(self, text: str) -> None:
        if not self._loading:
            self.canvas.update_selected(label=text)

    def _apply_switch(self, text: str) -> None:
        if not self._loading:
            self.canvas.update_selected(switch=text.strip())

    def _apply_geometry(self, field: str, value: float) -> None:
        if self._loading:
            return
        self.canvas.update_selected(**{field: round(value, 3)})

    # ---- learning from the hardware --------------------------------------------------

    def _toggle_learn(self, enabled: bool) -> None:
        self._learning = enabled
        self.learn_button.setText(
            "Listening — press a key" if enabled else "Press keys on my board"
        )
        self.learn_status.setText(
            "Press the key you have selected." if enabled else ""
        )
        self.learn_mode_changed.emit(enabled)

    @property
    def learning(self) -> bool:
        return self._learning

    def apply_stroke(self, keys: set[str], physical: set[str]) -> None:
        """A chord arrived from the board while learn mode was armed.

        One key pressed is the useful case: it names the selected box outright. More than
        one is reported rather than guessed at, because there is no way to tell which of
        them the user meant.
        """
        if not self._learning:
            return

        selected = self.canvas.selected_indexes
        if not selected:
            self.learn_status.setText("Select a key on the layout first.")
            return

        if len(keys) != 1:
            self.learn_status.setText(
                f"Heard {format_stroke(keys) or 'nothing'} — "
                f"{len(keys)} keys at once. Press one key on its own."
            )
            return

        steno_key = next(iter(keys))
        # The physical switch name distinguishes the two S switches and the four asterisk
        # bits, which is exactly what the canonical key throws away and what someone
        # describing their own board most wants recorded.
        switch = sorted(physical)[0] if len(physical) == 1 else ""

        for index in selected:
            key = self.canvas.keys[index]
            key.key = steno_key
            key.label = steno_key.strip("-")
            key.inferred = False
            if switch:
                key.switch = switch
        self.canvas.layout_changed.emit()
        self.canvas.update()

        detail = f" ({switch})" if switch else ""
        self.learn_status.setText(f"Set to {steno_key}{detail}.")

        # Walk on to the next key, so the whole board can be labelled without going back
        # to the mouse between presses.
        following = (max(selected) + 1) % max(1, len(self.canvas.keys))
        self.canvas.select([following])

    # ---- saving -----------------------------------------------------------------------

    def _save(self) -> None:
        name = self.name_edit.text().strip() or "My board"
        profile_id = slugify(name)
        keys = self.canvas.to_profile_keys()

        profile = BoardProfile(
            id=profile_id,
            name=name,
            description=f"{len(keys)} keys, drawn in the board designer.",
            notes=(
                f"Traced from {self._photo_path.name}."
                if self._photo_path else "Drawn by hand in the board designer."
            ),
            keys=keys,
        )

        problems = validate(profile)
        if problems:
            QMessageBox.warning(
                self, "Not saved yet",
                "This layout cannot be used as it stands:\n\n"
                + "\n".join(f"  •  {problem}" for problem in problems[:8])
                + ("\n\n…and more." if len(problems) > 8 else ""),
            )
            return

        missing = sorted(set(STENO_ORDER) - {"#"} - {key.key for key in keys})
        if missing:
            keep_going = QMessageBox.question(
                self, "Some steno keys are missing",
                "This board has no key for: "
                + ", ".join(missing)
                + ".\n\nThat is fine for a board that genuinely lacks them — lessons "
                "needing those keys are dropped rather than asking you to press something "
                "you do not have. Save anyway?",
            )
            if keep_going != QMessageBox.Yes:
                return

        path = BOARDS_DIR / f"{profile_id}.json"
        if path.exists():
            overwrite = QMessageBox.question(
                self, "Replace that board?",
                f"{path.name} already exists in your boards folder.\n\nReplace it?",
            )
            if overwrite != QMessageBox.Yes:
                return

        try:
            written = profile.export()
        except OSError as exc:
            QMessageBox.warning(self, "Could not save", str(exc))
            return

        self._set_status(f"Saved to {written}")
        self.board_saved.emit(profile_id)

    def _set_status(self, message: str) -> None:
        # Elided rather than clipped, so a long saved-to path ends in an ellipsis instead
        # of being cut mid-word. The full text stays available as the tooltip.
        metrics = QFontMetrics(self.status_label.font())
        self.status_label.setText(
            metrics.elidedText(message, Qt.ElideMiddle, self.status_label.maximumWidth())
        )
        self.status_label.setToolTip(message)

    # ---- outline preview --------------------------------------------------------------

    def describe(self) -> str:
        """A one-line summary of the layout, useful in tests and for the status line."""
        keys = self.canvas.keys
        return f"{len(keys)} keys: {format_stroke(sort_keys({key.key for key in keys}))}"
