"""The application window: navigation, and the wiring between device, drills and storage."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .dictionary import StenoDictionary
from .lessons import LessonItem, sentence_lesson, validate_lessons
from .machine import State, StenoMachine
from .screens.custom import CustomTextScreen
from .screens.explore import ExploreScreen
from .screens.fingers import FingersScreen
from .screens.home import HomeScreen
from .screens.practice import PracticeScreen
from .screens.progress import ProgressScreen
from .screens.settings import SettingsScreen
from .screens.summary import SummaryScreen
from .session import (
    Session,
    build_review_session,
    limit_session,
    order_by_difficulty,
)
from .storage import Profile, SessionRecord

_NAV = [
    ("home", "Lessons"),
    ("fingers", "Finger positions"),
    ("custom", "Your own text"),
    ("explore", "Explore the board"),
    ("progress", "Progress"),
    ("settings", "Settings"),
]


class MainWindow(QMainWindow):
    def __init__(self, dictionary: StenoDictionary, profile: Profile) -> None:
        super().__init__()
        self.setWindowTitle("TinyMod4 Steno Trainer")
        self.resize(1120, 820)
        self.setMinimumSize(880, 700)

        self.dictionary = dictionary
        self.profile = profile
        self.lessons, self.lesson_warnings = validate_lessons(dictionary)
        self.lessons.append(sentence_lesson(dictionary))
        self._lessons_by_key = {lesson.key: lesson for lesson in self.lessons}
        self._last_session: tuple[list[LessonItem], str, str] | None = None

        self._build()

        self.machine = StenoMachine(port=profile.settings.get("port", "COM5"))
        self.machine.stroke.connect(self._on_stroke)
        self.machine.status_changed.connect(self._on_status)

        self._apply_settings()
        if profile.settings.get("auto_connect", True):
            QTimer.singleShot(150, self.machine.start)

        self._show_home()

    # ---- construction -------------------------------------------------------------

    def _build(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        root.addWidget(self.stack, stretch=1)
        self.setCentralWidget(central)

        self.home = HomeScreen()
        self.home.lesson_selected.connect(self._start_lesson)

        self.practice = PracticeScreen()
        self.practice.session_finished.connect(self._on_session_finished)
        self.practice.exit_requested.connect(self._show_home)

        self.fingers = FingersScreen()

        self.custom = CustomTextScreen()
        self.custom.set_dictionary(self.dictionary)
        self.custom.start_requested.connect(self._start_custom)

        self.explore = ExploreScreen()
        self.explore.set_dictionary(self.dictionary)

        self.progress = ProgressScreen()
        self.progress.review_requested.connect(lambda: self._start_lesson("review"))

        self.settings = SettingsScreen()
        self.settings.load(self.profile.settings)
        self.settings.set_dictionary_info(self.dictionary, self.lesson_warnings)
        self.settings.settings_changed.connect(self._on_settings_changed)
        self.settings.reconnect_requested.connect(self._reconnect)

        self.summary = SummaryScreen()
        self.summary.home_requested.connect(self._show_home)
        self.summary.practice_again.connect(self._repeat_session)
        self.summary.review_requested.connect(lambda: self._start_lesson("review"))

        for screen in (
            self.home, self.practice, self.fingers, self.custom,
            self.explore, self.progress, self.settings, self.summary,
        ):
            self.stack.addWidget(screen)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(212)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 14)
        layout.setSpacing(0)

        title = QLabel("TinyMod4")
        title.setObjectName("SidebarTitle")
        subtitle = QLabel("Steno Trainer")
        subtitle.setObjectName("SidebarSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_buttons: dict[str, QPushButton] = {}

        for key, label in _NAV:
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked, k=key: self._navigate(k))
            self._nav_group.addButton(button)
            self._nav_buttons[key] = button
            layout.addWidget(button)

        layout.addStretch()

        self._sidebar_status = QLabel("Not connected")
        self._sidebar_status.setObjectName("Faint")
        self._sidebar_status.setWordWrap(True)
        self._sidebar_status.setContentsMargins(18, 0, 14, 0)
        layout.addWidget(self._sidebar_status)

        return sidebar

    # ---- navigation ---------------------------------------------------------------

    def _navigate(self, key: str) -> None:
        if key == "home":
            self._show_home()
        elif key == "fingers":
            self.stack.setCurrentWidget(self.fingers)
        elif key == "custom":
            self.stack.setCurrentWidget(self.custom)
        elif key == "explore":
            self.stack.setCurrentWidget(self.explore)
        elif key == "progress":
            self.progress.refresh(self.profile)
            self.stack.setCurrentWidget(self.progress)
        elif key == "settings":
            self.settings.load(self.profile.settings)
            self.stack.setCurrentWidget(self.settings)
        if key in self._nav_buttons:
            self._nav_buttons[key].setChecked(True)

    def _show_home(self) -> None:
        self.home.refresh(
            self.lessons, self.profile, len(self.profile.review_items())
        )
        self.stack.setCurrentWidget(self.home)
        self._nav_buttons["home"].setChecked(True)

    # ---- sessions -----------------------------------------------------------------

    def _start_lesson(self, key: str) -> None:
        if key == "review":
            items = build_review_session(
                self.profile, self.dictionary,
                limit=int(self.profile.settings.get("session_length", 20)),
            )
            title = "Review"
            if not items:
                self._show_home()
                return
        else:
            lesson = self._lessons_by_key.get(key)
            if lesson is None or not lesson.items:
                return
            items = order_by_difficulty(list(lesson.items), self.profile)
            items = limit_session(
                items, int(self.profile.settings.get("session_length", 20))
            )
            title = lesson.title

        self._launch(items, title, key)

    def _start_custom(self, items: list[LessonItem], title: str) -> None:
        items = limit_session(
            order_by_difficulty(items, self.profile),
            int(self.profile.settings.get("session_length", 20)),
        )
        self._launch(items, title, "custom")

    def _launch(self, items: list[LessonItem], title: str, key: str) -> None:
        if not items:
            return
        self._last_session = (items, title, key)
        session = Session(
            items=items,
            dictionary=self.dictionary,
            profile=self.profile,
            lesson_key=key,
            hint_mode=self.profile.settings.get("hint_mode", "adaptive"),
        )
        self._apply_settings()
        self.practice.set_status(self.machine.state, self.machine.message)
        self.practice.start(session, title)
        self.stack.setCurrentWidget(self.practice)
        self._nav_group.setExclusive(False)
        for button in self._nav_buttons.values():
            button.setChecked(False)
        self._nav_group.setExclusive(True)

    def _repeat_session(self) -> None:
        if self._last_session is None:
            self._show_home()
            return
        items, title, key = self._last_session
        self._launch(list(items), title, key)

    def _on_session_finished(self, summary: dict) -> None:
        self.profile.history.append(
            SessionRecord(
                started=summary.get("started", time.time()),
                lesson=summary.get("lesson", "custom"),
                prompts=summary.get("prompts", 0),
                correct=summary.get("correct", 0),
                duration_s=summary.get("duration_s", 0.0),
                side_swaps=summary.get("side_swaps", 0),
            )
        )
        self.profile.save()
        self.summary.show_summary(summary, len(self.profile.review_items()))
        self.stack.setCurrentWidget(self.summary)

    # ---- device -------------------------------------------------------------------

    def _on_stroke(self, keys: set, _physical: set) -> None:
        current = self.stack.currentWidget()
        if current is self.practice:
            self.practice.submit_chord(set(keys))
        elif current is self.explore:
            self.explore.show_stroke(set(keys))

    def _on_status(self, state: str, message: str) -> None:
        self._sidebar_status.setText(message)
        colour = {
            State.CONNECTED: theme.SUCCESS,
            State.PORT_BUSY: theme.WARNING,
            State.ERROR: theme.ERROR,
        }.get(state, theme.TEXT_FAINT)
        self._sidebar_status.setStyleSheet(f"color: {colour}; font-size: 11px;")
        self.practice.set_status(state, message)
        self.explore.set_status(state, message)
        self.settings.set_status(state, message)

    def _reconnect(self) -> None:
        port = self.settings.current_port()
        if port:
            self.profile.settings["port"] = port
            self.profile.save()
        self.machine.start(port or None)

    # ---- settings -----------------------------------------------------------------

    def _on_settings_changed(self, values: dict) -> None:
        port_changed = values.get("port") and values["port"] != self.profile.settings.get("port")
        self.profile.settings.update(values)
        self.profile.save()
        self._apply_settings()
        if port_changed:
            self.machine.start(values["port"])

    def _apply_settings(self) -> None:
        self.practice.set_keyboard_fallback(
            bool(self.profile.settings.get("keyboard_fallback", False))
        )
        self.practice.set_finger_guidance(
            bool(self.profile.settings.get("finger_guidance", True))
        )

    # ---- shutdown -----------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self.machine.stop()
        self.profile.save()
        super().closeEvent(event)
