"""Reading Gemini PR strokes straight off the TinyMod4's serial port.

Two hard-won details from CLAUDE.md are load-bearing here:

* DTR must be asserted or the board sends nothing. The firmware gates transmission on the
  host raising DTR (Arduino's `if (Serial)`). Without it the port opens fine and returns
  zero bytes forever, which is indistinguishable from dead hardware.
* The port is exclusive. Plover and this app cannot both hold COM5, so a busy port gets
  its own status message rather than a generic failure.
"""

from __future__ import annotations

import time

import serial
from serial.tools import list_ports
from PySide6.QtCore import QObject, QThread, Signal

from .protocol import FrameReader, decode_frame, decode_frame_physical

# The TinyMod4 enumerates as a composite device; MI_00 is the CDC serial interface.
TINYMOD_VID = 0x239A
TINYMOD_PID = 0x800E

BAUDRATE = 9600
READ_TIMEOUT = 0.2
RECONNECT_DELAY = 2.0


class State:
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    PORT_BUSY = "port_busy"
    ERROR = "error"


def find_tinymod_ports() -> list[str]:
    """Serial ports whose USB IDs match the TinyMod4, most likely first."""
    matches, others = [], []
    for port in list_ports.comports():
        if port.vid == TINYMOD_VID and port.pid == TINYMOD_PID:
            matches.append(port.device)
        else:
            others.append(port.device)
    return matches + others


def describe_ports() -> list[tuple[str, str]]:
    """(device, human description) for every serial port on the machine."""
    result = []
    for port in list_ports.comports():
        label = port.description or "Serial port"
        if port.vid == TINYMOD_VID and port.pid == TINYMOD_PID:
            label = f"TinyMod4 — {label}"
        result.append((port.device, label))
    return result


class StenoMachine(QObject):
    """Owns a background thread that holds the serial port and emits decoded chords.

    One Gemini PR frame is one complete chord, sent on release; there is no key-down/key-up
    stream, so every frame emitted here is a finished stroke.
    """

    stroke = Signal(set, set)          # canonical keys, physical switches
    status_changed = Signal(str, str)  # State, human-readable message

    def __init__(self, port: str = "COM5", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._port_name = port
        self._thread: QThread | None = None
        self._worker: _SerialWorker | None = None
        self._state = State.DISCONNECTED
        self._message = "Not connected"

    # ---- properties ---------------------------------------------------------------

    @property
    def port_name(self) -> str:
        return self._port_name

    @property
    def state(self) -> str:
        return self._state

    @property
    def message(self) -> str:
        return self._message

    @property
    def is_connected(self) -> bool:
        return self._state == State.CONNECTED

    # ---- lifecycle ----------------------------------------------------------------

    def start(self, port: str | None = None) -> None:
        if port:
            self._port_name = port
        self.stop()

        self._thread = QThread()
        self._worker = _SerialWorker(self._port_name)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.stroke.connect(self.stroke)
        self._worker.status_changed.connect(self._on_status)
        self._thread.start()

    def stop(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None
        self._worker = None
        if self._state != State.DISCONNECTED:
            self._on_status(State.DISCONNECTED, "Not connected")

    def _on_status(self, state: str, message: str) -> None:
        self._state, self._message = state, message
        self.status_changed.emit(state, message)


class _SerialWorker(QObject):
    """The thread body: open the port, read bytes, emit chords, reconnect on loss."""

    stroke = Signal(set, set)
    status_changed = Signal(str, str)

    def __init__(self, port_name: str) -> None:
        super().__init__()
        self._port_name = port_name
        self._stopping = False

    def request_stop(self) -> None:
        self._stopping = True

    def run(self) -> None:
        reader = FrameReader()
        while not self._stopping:
            port = self._open()
            if port is None:
                self._sleep(RECONNECT_DELAY)
                continue

            reader.reset()
            self.status_changed.emit(
                State.CONNECTED, f"Connected on {self._port_name}"
            )
            try:
                while not self._stopping:
                    data = port.read(64)
                    if not data:
                        continue
                    for frame in reader.feed(data):
                        self.stroke.emit(
                            decode_frame(frame), decode_frame_physical(frame)
                        )
            except serial.SerialException as exc:
                if not self._stopping:
                    self.status_changed.emit(
                        State.ERROR, f"Lost {self._port_name}: {_clean(exc)}"
                    )
            finally:
                try:
                    port.close()
                except Exception:
                    pass
            if not self._stopping:
                self._sleep(RECONNECT_DELAY)

    def _open(self) -> serial.Serial | None:
        self.status_changed.emit(
            State.CONNECTING, f"Opening {self._port_name}…"
        )
        try:
            port = serial.Serial(
                port=self._port_name,
                baudrate=BAUDRATE,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=READ_TIMEOUT,
            )
        except serial.SerialException as exc:
            text = str(exc).lower()
            if "access is denied" in text or "permission" in text:
                self.status_changed.emit(
                    State.PORT_BUSY,
                    f"{self._port_name} is held by another program — close Plover and it "
                    f"will connect automatically.",
                )
            elif "could not open" in text or "not found" in text or "filenotfound" in text:
                self.status_changed.emit(
                    State.ERROR,
                    f"{self._port_name} not found — check the TinyMod4 is plugged in.",
                )
            else:
                self.status_changed.emit(State.ERROR, _clean(exc))
            return None

        # REQUIRED: the firmware will not transmit until the host raises DTR.
        try:
            port.dtr = True
            port.rts = True
        except OSError:
            pass
        port.reset_input_buffer()
        return port

    def _sleep(self, seconds: float) -> None:
        """Sleep in short slices so a stop request is honoured promptly."""
        deadline = time.monotonic() + seconds
        while not self._stopping and time.monotonic() < deadline:
            time.sleep(0.05)


def _clean(exc: Exception) -> str:
    text = str(exc)
    if ":" in text and text.count(":") >= 2:
        text = text.split(":", 1)[-1].strip()
    return text[:160]
