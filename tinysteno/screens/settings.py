"""Device, dictionary and practice settings."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
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

        # ---- device -------------------------------------------------------------
        device_card = Card(padding=18)
        device_header = QLabel("TinyMod4")
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

        # ---- dictionary ---------------------------------------------------------
        self.dictionary_card = Card(padding=18)
        dictionary_header = QLabel("Dictionary")
        dictionary_header.setObjectName("H2")
        self.dictionary_card.body.addWidget(dictionary_header)
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

    def load(self, settings: dict) -> None:
        self._loading = True
        self.refresh_ports()
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
            }
        )
