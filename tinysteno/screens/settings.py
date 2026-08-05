"""Device, dictionary and practice settings."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..machine import describe_ports
from ..widgets.common import Card, StatusPill, faint, heading

_HINT_MODES = [
    ("adaptive", "Adaptive — fade the hints as each item becomes reliable"),
    ("always", "Always show the chord"),
    ("never", "Never show the chord unless I get it wrong twice"),
]


class SettingsScreen(QWidget):
    """Everything configurable, plus the connection troubleshooting notes."""

    settings_changed = Signal(dict)
    reconnect_requested = Signal()
    export_requested = Signal()
    open_boards_requested = Signal()
    design_board_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        scroll.setWidget(content)

        layout.addWidget(heading("Settings"))

        # ---- board --------------------------------------------------------------
        board_card = Card(padding=18)
        board_header = QLabel("Board")
        board_header.setObjectName("H2")
        board_card.body.addWidget(board_header)

        board_form = QFormLayout()
        board_form.setSpacing(11)
        self.board_combo = QComboBox()
        self.board_combo.currentIndexChanged.connect(self._emit)
        board_form.addRow("Layout", self.board_combo)
        board_card.body.addLayout(board_form)

        self.board_description = faint("")
        self.board_notes = QLabel("")
        self.board_notes.setWordWrap(True)
        self.board_notes.setStyleSheet(f"color: {theme.TEXT_DIM};")
        board_card.body.addWidget(self.board_description)
        board_card.body.addWidget(self.board_notes)

        board_buttons = QHBoxLayout()
        board_buttons.setSpacing(8)
        self.design_board = QPushButton("Design from a photo…")
        self.design_board.setObjectName("Primary")
        self.design_board.clicked.connect(self.design_board_requested)
        board_buttons.addWidget(self.design_board)
        self.export_board = QPushButton("Save a copy I can edit")
        self.export_board.clicked.connect(self.export_requested)
        self.open_boards = QPushButton("Open boards folder")
        self.open_boards.clicked.connect(self.open_boards_requested)
        board_buttons.addWidget(self.export_board)
        board_buttons.addWidget(self.open_boards)
        board_buttons.addStretch()
        board_card.body.addLayout(board_buttons)

        self.board_help = faint(
            "If your board is not here, photograph it and trace it in the designer — or "
            "save a copy of the closest one and edit the JSON by hand. Either way it "
            "lands in the folder above, one file per board. A file reusing a built-in id "
            "replaces it, so a layout we got wrong can be corrected without waiting for "
            "a new build."
        )
        board_card.body.addWidget(self.board_help)

        self.board_warnings = QLabel("")
        self.board_warnings.setWordWrap(True)
        self.board_warnings.setStyleSheet(f"color: {theme.WARNING};")
        self.board_warnings.setVisible(False)
        board_card.body.addWidget(self.board_warnings)
        layout.addWidget(board_card)

        # ---- device -------------------------------------------------------------
        device_card = Card(padding=18)
        device_header = QLabel("Connection")
        device_header.setObjectName("H2")
        device_card.body.addWidget(device_header)

        self.status = StatusPill()
        device_card.body.addWidget(self.status)

        form = QFormLayout()
        form.setSpacing(11)
        form.setLabelAlignment(Qt.AlignLeft)

        port_row = QHBoxLayout()
        port_row.setSpacing(8)
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.currentTextChanged.connect(self._emit)
        refresh_button = QPushButton("Rescan")
        refresh_button.clicked.connect(self.refresh_ports)
        reconnect_button = QPushButton("Reconnect")
        reconnect_button.setObjectName("Primary")
        reconnect_button.clicked.connect(self.reconnect_requested)
        port_row.addWidget(self.port_combo, stretch=1)
        port_row.addWidget(refresh_button)
        port_row.addWidget(reconnect_button)
        form.addRow("Serial port", port_row)

        self.auto_connect = QCheckBox("Connect automatically when the app starts")
        self.auto_connect.toggled.connect(self._emit)
        form.addRow("", self.auto_connect)

        self.keyboard_fallback = QCheckBox(
            "Accept QWERTY input as a stand-in when the device is unavailable"
        )
        self.keyboard_fallback.toggled.connect(self._emit)
        form.addRow("", self.keyboard_fallback)

        device_card.body.addLayout(form)

        notes = faint(
            "The board must be in Serial mode — the jumper marked “Serial = GeminiPiper”. "
            "The jumper is read once at power-up, so a change needs a full USB replug.\n\n"
            "The port is exclusive: Plover and this app cannot both hold it. Close Plover "
            "before practising and this app will pick the port up on its own."
        )
        device_card.body.addWidget(notes)
        layout.addWidget(device_card)

        # ---- practice -----------------------------------------------------------
        practice_card = Card(padding=18)
        practice_header = QLabel("Practice")
        practice_header.setObjectName("H2")
        practice_card.body.addWidget(practice_header)

        practice_form = QFormLayout()
        practice_form.setSpacing(11)

        self.hint_combo = QComboBox()
        for value, label in _HINT_MODES:
            self.hint_combo.addItem(label, value)
        self.hint_combo.currentIndexChanged.connect(self._emit)
        practice_form.addRow("Hints", self.hint_combo)

        self.length_spin = QSpinBox()
        self.length_spin.setRange(5, 100)
        self.length_spin.setSingleStep(5)
        self.length_spin.setSuffix(" prompts")
        self.length_spin.valueChanged.connect(self._emit)
        practice_form.addRow("Session length", self.length_spin)

        self.finger_guidance = QCheckBox(
            "Name the fingers for each chord while practising"
        )
        self.finger_guidance.toggled.connect(self._emit)
        practice_form.addRow("", self.finger_guidance)

        practice_card.body.addLayout(practice_form)
        layout.addWidget(practice_card)

        # ---- dictionaries -------------------------------------------------------
        self.dictionary_card = Card(padding=18)
        dictionary_header = QLabel("Dictionaries")
        dictionary_header.setObjectName("H2")
        self.dictionary_card.body.addWidget(dictionary_header)
        self.dictionary_card.body.addWidget(
            faint(
                "Loaded in order, with earlier files winning — the same priority Plover "
                "uses. Leave the list empty to use Plover's own user, commands and main "
                "dictionaries."
            )
        )

        self.dictionary_list = QListWidget()
        self.dictionary_list.setMaximumHeight(132)
        self.dictionary_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.dictionary_card.body.addWidget(self.dictionary_list)

        dictionary_buttons = QHBoxLayout()
        dictionary_buttons.setSpacing(8)
        add_button = QPushButton("Add…")
        add_button.clicked.connect(self._add_dictionary)
        remove_button = QPushButton("Remove")
        remove_button.clicked.connect(self._remove_dictionary)
        up_button = QPushButton("Move up")
        up_button.clicked.connect(lambda: self._move_dictionary(-1))
        reset_button = QPushButton("Use Plover's")
        reset_button.clicked.connect(self._reset_dictionaries)
        for button in (add_button, remove_button, up_button):
            dictionary_buttons.addWidget(button)
        dictionary_buttons.addStretch()
        dictionary_buttons.addWidget(reset_button)
        self.dictionary_card.body.addLayout(dictionary_buttons)

        self.dictionary_label = faint("")
        self.dictionary_card.body.addWidget(self.dictionary_label)
        layout.addWidget(self.dictionary_card)

        layout.addStretch()

    # ---- wiring -------------------------------------------------------------------

    def refresh_ports(self) -> None:
        current = self.port_combo.currentText()
        self._loading = True
        self.port_combo.clear()
        for device, label in describe_ports():
            self.port_combo.addItem(f"{device} — {label}", device)
        if current:
            index = self.port_combo.findData(current)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
            else:
                self.port_combo.setEditText(current)
        self._loading = False

    def set_boards(self, registry, selected_id: str) -> None:
        """Populate the board picker from the loaded registry."""
        self._loading = True
        self.board_combo.clear()
        for profile in registry:
            suffix = "" if profile.builtin else "  (yours)"
            self.board_combo.addItem(f"{profile.name}{suffix}", profile.id)
        index = self.board_combo.findData(selected_id)
        self.board_combo.setCurrentIndex(max(0, index))
        self._loading = False
        self._describe_board(registry)

        if registry.warnings:
            self.board_warnings.setText(
                "Some board files were skipped:\n"
                + "\n".join(f"    {warning}" for warning in registry.warnings[:5])
            )
            self.board_warnings.setVisible(True)
        else:
            self.board_warnings.setVisible(False)

    def _describe_board(self, registry) -> None:
        profile = registry.get(self.current_board())
        if profile is None:
            return
        parts = [f"{len(profile.keys)} keys"]
        if profile.vendor:
            parts.append(profile.vendor)
        parts.append(profile.protocol.replace("_", " ").upper())
        self.board_description.setText(f"{profile.description}   ·   {'  ·  '.join(parts)}")
        self.board_notes.setText(profile.notes)
        self.board_notes.setVisible(bool(profile.notes))
        self.export_board.setEnabled(True)

    def current_board(self) -> str:
        return str(self.board_combo.currentData() or "")

    # ---- dictionaries -------------------------------------------------------------

    def _set_dictionary_list(self, paths: list[str]) -> None:
        self.dictionary_list.clear()
        for path in paths:
            self.dictionary_list.addItem(path)
        self._update_dictionary_placeholder()

    def _update_dictionary_placeholder(self) -> None:
        empty = self.dictionary_list.count() == 0
        self.dictionary_list.setStyleSheet(
            f"color: {theme.TEXT_FAINT};" if empty else ""
        )
        if empty:
            self.dictionary_list.addItem("(using Plover's own dictionaries)")
            self.dictionary_list.item(0).setFlags(Qt.NoItemFlags)

    def current_dictionaries(self) -> list[str]:
        paths = []
        for index in range(self.dictionary_list.count()):
            item = self.dictionary_list.item(index)
            if item.flags() != Qt.NoItemFlags:
                paths.append(item.text())
        return paths

    def _add_dictionary(self) -> None:
        chosen, _ = QFileDialog.getOpenFileNames(
            self, "Add a steno dictionary", str(Path.home()),
            "Steno dictionaries (*.json);;All files (*)",
        )
        if not chosen:
            return
        existing = self.current_dictionaries()
        for path in chosen:
            if path not in existing:
                existing.append(path)
        self._set_dictionary_list(existing)
        self._emit()

    def _remove_dictionary(self) -> None:
        row = self.dictionary_list.currentRow()
        paths = self.current_dictionaries()
        if 0 <= row < len(paths):
            del paths[row]
            self._set_dictionary_list(paths)
            self._emit()

    def _move_dictionary(self, delta: int) -> None:
        row = self.dictionary_list.currentRow()
        paths = self.current_dictionaries()
        target = row + delta
        if 0 <= row < len(paths) and 0 <= target < len(paths):
            paths[row], paths[target] = paths[target], paths[row]
            self._set_dictionary_list(paths)
            self.dictionary_list.setCurrentRow(target)
            self._emit()

    def _reset_dictionaries(self) -> None:
        self._set_dictionary_list([])
        self._emit()

    # ---- loading ------------------------------------------------------------------

    def load(self, settings: dict) -> None:
        self._loading = True
        self.refresh_ports()
        self._set_dictionary_list(list(settings.get("dictionary_paths") or []))
        port = settings.get("port", "COM5")
        index = self.port_combo.findData(port)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)
        else:
            self.port_combo.setEditText(port)
        self.auto_connect.setChecked(bool(settings.get("auto_connect", True)))
        self.keyboard_fallback.setChecked(bool(settings.get("keyboard_fallback", False)))
        hint_index = self.hint_combo.findData(settings.get("hint_mode", "adaptive"))
        self.hint_combo.setCurrentIndex(max(0, hint_index))
        self.length_spin.setValue(int(settings.get("session_length", 20)))
        self.finger_guidance.setChecked(bool(settings.get("finger_guidance", True)))
        self._loading = False

    def set_status(self, state: str, message: str) -> None:
        self.status.set_status(state, message)

    def set_dictionary_info(self, dictionary, warnings: list[str]) -> None:
        lines = [
            f"{len(dictionary):,} outlines loaded, covering {dictionary.known_words():,} words."
        ]
        for name, count in dictionary.sources:
            lines.append(f"    {name} — {count:,} entries")
        if warnings:
            lines.append("")
            lines.append(f"{len(warnings)} lesson item(s) skipped after validation:")
            lines.extend(f"    {warning}" for warning in warnings[:6])
        self.dictionary_label.setText("\n".join(lines))

    def current_port(self) -> str:
        data = self.port_combo.currentData()
        if data:
            return str(data)
        text = self.port_combo.currentText()
        return text.split(" — ")[0].strip()

    def _emit(self, *_args) -> None:
        if self._loading:
            return
        self.settings_changed.emit(
            {
                "port": self.current_port(),
                "auto_connect": self.auto_connect.isChecked(),
                "keyboard_fallback": self.keyboard_fallback.isChecked(),
                "hint_mode": self.hint_combo.currentData(),
                "session_length": self.length_spin.value(),
                "finger_guidance": self.finger_guidance.isChecked(),
                "board": self.current_board(),
                "dictionary_paths": self.current_dictionaries(),
            }
        )
