"""Palette, fonts and the application stylesheet.

Calm and dark by design: the learner is staring at this for twenty minutes at a stretch, so
the only bright things on screen should be the chord they are meant to press and the
feedback about what they pressed.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

# ---- palette ---------------------------------------------------------------------------

BG = "#14161a"
BG_PANEL = "#1b1e25"
BG_RAISED = "#232732"
BG_INPUT = "#111317"
BORDER = "#2c313d"
BORDER_SOFT = "#242833"

TEXT = "#e7e9ee"
TEXT_DIM = "#98a0b0"
TEXT_FAINT = "#616a7c"

# Key banks. Left and right deliberately sit far apart in hue, because telling them apart
# is the entire point of the hardest lesson. Right bank is teal rather than green so a lit
# right-hand key can never be mistaken for the green used to mean "you got it right".
LEFT_BANK = "#5b8def"
RIGHT_BANK = "#38c6cd"
VOWEL = "#f0a45e"
STAR = "#b07de0"

SUCCESS = "#3fbf8f"
WARNING = "#f0a45e"
ERROR = "#e8695f"
ACCENT = "#5b8def"

SIDE_COLORS = {
    "left": LEFT_BANK,
    "right": RIGHT_BANK,
    "center": STAR,
}


def bank_color(key: str) -> str:
    """The colour a key wears, with thumbs picked out from the rest of their bank."""
    if key in ("A-", "O-", "-E", "-U"):
        return VOWEL
    if key == "*":
        return STAR
    return LEFT_BANK if not key.startswith("-") else RIGHT_BANK


def qcolor(hex_color: str, alpha: float = 1.0) -> QColor:
    color = QColor(hex_color)
    if alpha < 1.0:
        color.setAlphaF(alpha)
    return color


def mix(a: str, b: str, t: float) -> QColor:
    """Blend two hex colours, t=0 gives a, t=1 gives b."""
    ca, cb = QColor(a), QColor(b)
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
    )


# ---- fonts -----------------------------------------------------------------------------

UI_FAMILY = "Segoe UI Variable, Segoe UI, sans-serif"
MONO_FAMILY = "Cascadia Code, Consolas, monospace"


# ---- stylesheet ------------------------------------------------------------------------

STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: {UI_FAMILY};
    font-size: 14px;
}}

/* Text and controls sit on top of whatever panel holds them, so they must not paint
   their own background -- otherwise every label shows as a dark bar inside a card. */
QLabel, QCheckBox, QRadioButton, QProgressBar {{ background: transparent; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}

#Sidebar {{
    background: {BG_PANEL};
    border-right: 1px solid {BORDER_SOFT};
}}

#SidebarTitle {{
    font-size: 15px;
    font-weight: 600;
    color: {TEXT};
    padding: 20px 18px 2px 18px;
}}

#SidebarSubtitle {{
    font-size: 11px;
    color: {TEXT_FAINT};
    padding: 0 18px 14px 18px;
}}

QPushButton#NavButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    color: {TEXT_DIM};
    text-align: left;
    padding: 10px 14px;
    margin: 1px 10px;
    font-size: 13.5px;
}}
QPushButton#NavButton:hover {{ background: {BG_RAISED}; color: {TEXT}; }}
QPushButton#NavButton:checked {{ background: {BG_RAISED}; color: {TEXT}; font-weight: 600; }}

QPushButton {{
    background: {BG_RAISED};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 16px;
    color: {TEXT};
}}
QPushButton:hover {{ background: #2a2f3b; border-color: #3a4150; }}
QPushButton:pressed {{ background: #1f2430; }}
QPushButton:disabled {{ color: {TEXT_FAINT}; background: {BG_PANEL}; border-color: {BORDER_SOFT}; }}

QPushButton#Primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: #0d1016;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: #6f9bf2; border-color: #6f9bf2; }}
QPushButton#Primary:pressed {{ background: #4a79d8; }}

QLabel#H1 {{ font-size: 26px; font-weight: 600; }}
QLabel#H2 {{ font-size: 17px; font-weight: 600; }}
QLabel#Dim {{ color: {TEXT_DIM}; }}
QLabel#Faint {{ color: {TEXT_FAINT}; font-size: 12px; }}

/* A Qt stylesheet beats setFont(), so every non-default size and family has to be
   declared here or the QWidget rule above silently clamps it to 14px sans. */
QLabel#Prompt {{ font-size: 42px; font-weight: 600; }}
QLabel#Headline {{ font-size: 30px; font-weight: 600; }}
QLabel#CardTitle {{ font-size: 16px; font-weight: 600; }}
QLabel#TileValue {{ font-size: 23px; font-weight: 600; }}
QLabel#Verdict {{ font-size: 15px; font-weight: 600; }}
QLabel#Translation {{ font-size: 19px; }}
QLabel#Outline {{ font-family: {MONO_FAMILY}; font-size: 19px; font-weight: 600; }}
QLabel#OutlineLarge {{ font-family: {MONO_FAMILY}; font-size: 26px; font-weight: 600; }}
QLabel#Mono {{ font-family: {MONO_FAMILY}; font-size: 13px; }}

#Card {{
    background: {BG_PANEL};
    border: 1px solid {BORDER_SOFT};
    border-radius: 12px;
}}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 10px;
    selection-background-color: {ACCENT};
    selection-color: #0d1016;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}

QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {BG_RAISED};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    selection-color: #0d1016;
    outline: none;
}}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 17px; height: 17px;
    border-radius: 5px;
    border: 1px solid {BORDER};
    background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QTableWidget {{
    background: {BG_PANEL};
    border: 1px solid {BORDER_SOFT};
    border-radius: 10px;
    gridline-color: {BORDER_SOFT};
    outline: none;
}}
QTableWidget::item {{ padding: 7px 10px; border: none; }}
QTableWidget::item:selected {{ background: {BG_RAISED}; color: {TEXT}; }}
QHeaderView::section {{
    background: {BG};
    color: {TEXT_FAINT};
    border: none;
    border-bottom: 1px solid {BORDER_SOFT};
    padding: 9px 10px;
    font-size: 12px;
    font-weight: 600;
}}

QProgressBar {{
    background: {BG_INPUT};
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: #333a48; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #414a5c; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 4px; }}
QScrollBar::handle:horizontal {{ background: #333a48; border-radius: 5px; min-width: 30px; }}

QToolTip {{
    background: {BG_RAISED};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 6px 8px;
    border-radius: 6px;
}}
"""
