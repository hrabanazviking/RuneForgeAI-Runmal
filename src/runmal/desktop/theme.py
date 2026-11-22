"""Appearance theme for the desktop shell (R-15) — Qt-free.

The tokens are Appendix B of Volmarr's Cyber-Viking Master
Visual Design Lawbook, carried verbatim for the dark variant;
the spacing scale (4/8/12/16/24/32/48/64/96) and the motion
scale (fast 100 ms, standard 180 ms, structural 320 ms,
ceremonial 600 ms) come from the same appendix. Doctrine rules
that bind this module:

* at least four distinct dark surfaces from the ladder
  (void-000 / void-100 / panel / panel-raised);
* accents are seasoning — 5-12% coverage: borders, selection,
  focus, key glyphs; never whole backgrounds or body text;
* content centres stay calm (no ornament behind working text);
* status is icon + words, never colour alone — the accent
  roles here are therefore always paired with text by the
  widgets that use them; this module only supplies colour.

Corner language — an honest translation, not a claim: the
doctrine's chamfered corners cannot be expressed in Qt
stylesheets (QSS has no clip-path and no corner cutting).
The theme therefore renders primary frames SQUARED
(``border-radius: 0`` on windows, dialogs, panels, docks and
group boxes) and carries the doctrine's frame strength as a
stepped double-border system — an outer iron line plus an
inner line — via QSS ``double`` borders at the "standard"
and "ceremonial" ornament levels. Small controls (buttons,
fields, tabs) keep a small radius (<= 4 px). Nothing here
claims to be a true chamfer.

Ornament levels:

* ``quiet`` — a single iron border; no decorative frame lines.
* ``standard`` — the stepped double-border frame system.
* ``ceremonial`` — standard, plus accent-tipped frame corners
  and headers (forge / bifrost at low coverage: group-box and
  dock titles, the selected tab's underline).

Persistence split: this module stays Qt-free so it can be
unit-tested without PySide6. It defines :class:`AppearancePrefs`
and its dict (de)serialisation (:func:`prefs_to_dict` /
:func:`prefs_from_dict`). The QSettings read/write that
persists those dicts on the machine lives in the Qt glue in
``window.py`` (``load_appearance_prefs`` /
``save_appearance_prefs``), never here.
"""

from __future__ import annotations

from dataclasses import dataclass
from string import Template

# ---------------------------------------------------------------- tokens

# Dark variant — Appendix B verbatim for the core tokens.
# Derived roles are named as such; each is either an alias of a
# core token or a blend derived from one, noted per role.
DARK_TOKENS: dict[str, str] = {
    # Appendix B core (verbatim).
    "void-000": "#05080D",
    "void-100": "#081019",
    "panel": "#0B1620",
    "panel-raised": "#101F2A",
    "iron": "#24313A",
    "silver": "#CCD6DF",
    "muted": "#8CA0AE",
    "bifrost": "#42DDF5",
    "rune": "#5AA8FF",
    "seidr": "#9B70FF",
    "forge": "#E3B75B",
    "aurora": "#59DFAE",
    "ember": "#F36A62",
    # Derived roles.
    "text": "#CCD6DF",  # = silver
    "text-muted": "#8CA0AE",  # = muted
    "text-disabled": "#617584",  # silver darkened toward iron
    "border": "#24313A",  # = iron
    "border-strong": "#3D5261",  # iron lightened one step
    "selection-bg": "#173F63",  # rune deepened to a calm wash
    "selection-fg": "#CCD6DF",  # = silver
    "focus": "#42DDF5",  # = bifrost
    "link": "#5AA8FF",  # = rune
    "accent-info": "#42DDF5",  # = bifrost
    "accent-success": "#59DFAE",  # = aurora
    "accent-warning": "#E3B75B",  # = forge
    "accent-danger": "#F36A62",  # = ember
    "accent-seidr": "#9B70FF",  # = seidr
}

# Light variant — the same roles and the same civilization:
# the ladder is pale iron/paper derived from the iron/silver
# family, text is near-void ink, and each accent keeps its hue
# family, darkened only where the Appendix B value fails AA on
# light surfaces. Per-token choices:
#   bifrost #42DDF5 -> #067089 (cyan kept, deepened; the raw
#     token is ~1.6:1 on paper, the deepened one >= 4.8:1)
#   rune    #5AA8FF -> #1F5FC4 (blue kept, deepened)
#   seidr   #9B70FF -> #6D3FD4 (violet kept, deepened)
#   forge   #E3B75B -> #7D5A0E (gold becomes bronze-ink)
#   aurora  #59DFAE -> #0B6E4F (green kept, deepened)
#   ember   #F36A62 -> #B3372F (red kept, deepened)
#   silver's role (primary text) becomes ink #16222C, a
#     void-family near-black; muted darkens to #43586A.
LIGHT_TOKENS: dict[str, str] = {
    # Core roles, light ladder (iron/silver family, pale).
    "void-000": "#E8EDF1",
    "void-100": "#EEF3F6",
    "panel": "#F5F8FA",
    "panel-raised": "#FFFFFF",
    "iron": "#8CA0AE",
    "silver": "#16222C",
    "muted": "#43586A",
    "bifrost": "#067089",
    "rune": "#1F5FC4",
    "seidr": "#6D3FD4",
    "forge": "#7D5A0E",
    "aurora": "#0B6E4F",
    "ember": "#B3372F",
    # Derived roles.
    "text": "#16222C",  # = silver role (ink)
    "text-muted": "#43586A",  # = muted
    "text-disabled": "#7E93A1",  # muted lightened toward iron
    "border": "#8CA0AE",  # = iron
    "border-strong": "#5F7482",  # iron darkened one step
    "selection-bg": "#BCD9EA",  # bifrost/rune pale wash
    "selection-fg": "#16222C",  # = text ink
    "focus": "#067089",  # = bifrost (deepened)
    "link": "#1F5FC4",  # = rune (deepened)
    "accent-info": "#067089",  # = bifrost (deepened)
    "accent-success": "#0B6E4F",  # = aurora (deepened)
    "accent-warning": "#7D5A0E",  # = forge (bronze-ink)
    "accent-danger": "#B3372F",  # = ember (deepened)
    "accent-seidr": "#6D3FD4",  # = seidr (deepened)
}

VARIANTS = ("dark", "light")
ORNAMENTS = ("quiet", "standard", "ceremonial")

_TOKENS_BY_VARIANT = {"dark": DARK_TOKENS, "light": LIGHT_TOKENS}

# Appendix B spacing scale (space-1 .. space-9).
SPACING: dict[str, int] = {
    "space-1": 4,
    "space-2": 8,
    "space-3": 12,
    "space-4": 16,
    "space-5": 24,
    "space-6": 32,
    "space-7": 48,
    "space-8": 64,
    "space-9": 96,
}

# Appendix B motion scale, milliseconds.
MOTION_TOKENS: dict[str, int] = {
    "fast": 100,
    "standard": 180,
    "structural": 320,
    "ceremonial": 600,
}

# Type scale: the base size every other size derives from;
# text_scale multiplies all of them.
BASE_FONT_PX = 13
_SMALL_PX = 11
_LARGE_PX = 16
_TITLE_PX = 20

TEXT_SCALE_MIN = 1.0
TEXT_SCALE_MAX = 2.0

# The (foreground role, background role) pairs the app actually
# relies on for text: body and muted text on every ladder
# surface, selection, links, and the accent roles used as
# status text (always with words, per doctrine) on panels.
# Tests assert every pair holds WCAG AA (>= 4.5) in BOTH
# variants via contrast_ratio().
AA_PAIRS: list[tuple[str, str]] = [
    ("text", "void-000"),
    ("text", "void-100"),
    ("text", "panel"),
    ("text", "panel-raised"),
    ("text-muted", "void-100"),
    ("text-muted", "panel"),
    ("text-muted", "panel-raised"),
    ("selection-fg", "selection-bg"),
    ("link", "panel"),
    ("link", "panel-raised"),
    ("accent-info", "panel"),
    ("accent-info", "panel-raised"),
    ("accent-success", "panel"),
    ("accent-success", "panel-raised"),
    ("accent-warning", "panel"),
    ("accent-warning", "panel-raised"),
    ("accent-danger", "panel"),
    ("accent-danger", "panel-raised"),
    ("accent-seidr", "panel"),
    ("accent-seidr", "panel-raised"),
]


def tokens_for(variant: str) -> dict[str, str]:
    """The token table for ``variant`` ("dark" or "light")."""
    try:
        return _TOKENS_BY_VARIANT[variant]
    except KeyError:
        raise ValueError(f"unknown theme variant: {variant!r}") from None


def motion_duration(name: str, reduced_motion: bool = False) -> int:
    """Milliseconds for a motion token; 0 when reduced motion
    is on (the shell's animations are cut, not merely slowed)."""
    if reduced_motion:
        return 0
    return MOTION_TOKENS[name]


# ------------------------------------------------------------- contrast


def _relative_luminance(hex_colour: str) -> float:
    value = hex_colour.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def linearise(channel: float) -> float:
        if channel <= 0.03928:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linearise(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """WCAG contrast ratio between two ``#RRGGBB`` colours."""
    first = _relative_luminance(fg_hex)
    second = _relative_luminance(bg_hex)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


# ---------------------------------------------------------------- prefs


@dataclass
class AppearancePrefs:
    """The user's appearance choices (shell-local state).

    These persist on this machine via QSettings (the glue is
    in ``window.py``); they never touch engine data.
    """

    variant: str = "dark"
    ornament: str = "standard"
    text_scale: float = 1.0
    reduced_motion: bool = False


def clamp_text_scale(value: float) -> float:
    """Clamp a text scale to the supported 1.0-2.0 range."""
    return max(TEXT_SCALE_MIN, min(TEXT_SCALE_MAX, float(value)))


def prefs_to_dict(prefs: AppearancePrefs) -> dict:
    """Serialise prefs to a plain dict (QSettings-friendly)."""
    return {
        "variant": prefs.variant,
        "ornament": prefs.ornament,
        "text_scale": prefs.text_scale,
        "reduced_motion": prefs.reduced_motion,
    }


def prefs_from_dict(data: dict | None) -> AppearancePrefs:
    """Rebuild prefs from a dict, falling back to the defaults
    for anything missing or unknown (a corrupt stored value
    must never stop the app from coming up themed)."""
    if not isinstance(data, dict):
        return AppearancePrefs()
    variant = data.get("variant")
    if variant not in VARIANTS:
        variant = "dark"
    ornament = data.get("ornament")
    if ornament not in ORNAMENTS:
        ornament = "standard"
    try:
        text_scale = clamp_text_scale(float(data.get("text_scale", 1.0)))
    except (TypeError, ValueError):
        text_scale = 1.0
    return AppearancePrefs(
        variant=variant,
        ornament=ornament,
        text_scale=text_scale,
        reduced_motion=bool(data.get("reduced_motion", False)),
    )


# ------------------------------------------------------------------ qss

_QSS_BODY = """
QWidget {
    background-color: $panel;
    color: $text;
    font-size: ${base}px;
    selection-background-color: $selection_bg;
    selection-color: $selection_fg;
}
QMainWindow, QDialog {
    background-color: $void_000;
    border-radius: 0px;
}
QMainWindow::separator {
    background-color: $border;
    width: 1px; height: 1px;
}
QLabel {
    background-color: transparent;
    color: $text;
}
QLabel:disabled { color: $text_disabled; }
QToolTip {
    background-color: $panel_raised;
    color: $text;
    border: 1px solid $border_strong;
    padding: 4px 8px;
}
QMenuBar {
    background-color: $void_100;
    color: $text;
    border-bottom: 1px solid $border;
}
QMenuBar::item { background-color: transparent; padding: 4px 12px; }
QMenuBar::item:selected { background-color: $panel_raised; }
QMenuBar::item:pressed { background-color: $selection_bg; color: $selection_fg; }
QMenu {
    background-color: $panel_raised;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 0px;
    padding: 4px 0px;
}
QMenu::item { padding: 4px 24px 4px 12px; }
QMenu::item:selected { background-color: $selection_bg; color: $selection_fg; }
QMenu::item:disabled { color: $text_disabled; }
QMenu::separator { background-color: $border; height: 1px; margin: 4px 8px; }
QToolBar {
    background-color: $void_100;
    border-bottom: 1px solid $border;
    spacing: 4px;
    padding: 4px;
}
QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 4px 8px;
}
QToolButton:hover { background-color: $panel_raised; border-color: $border; }
QToolButton:pressed { background-color: $selection_bg; color: $selection_fg; }
QDockWidget {
    background-color: $panel;
    color: $text;
    border-radius: 0px;
    titlebar-close-icon: none;
}
QDockWidget::title {
    background-color: $void_100;
    border-bottom: 1px solid $border;
    padding: 4px 8px;
    text-align: left;
}
QGroupBox {
    background-color: $panel;
    border: 1px solid $border;
    border-radius: 0px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0px 4px;
    color: $text_muted;
}
QFrame { border-radius: 0px; }
QListWidget, QTreeWidget, QTableWidget,
QListView, QTreeView, QTableView {
    background-color: $void_100;
    alternate-background-color: $panel;
    color: $text;
    border: 1px solid $border;
    border-radius: 0px;
    outline: 0px;
}
QListWidget::item, QTreeWidget::item, QTableWidget::item {
    padding: 4px 8px;
}
QListWidget::item:selected, QTreeWidget::item:selected,
QTableWidget::item:selected,
QListView::item:selected, QTreeView::item:selected,
QTableView::item:selected {
    background-color: $selection_bg;
    color: $selection_fg;
}
QHeaderView::section {
    background-color: $panel_raised;
    color: $text_muted;
    border: none;
    border-right: 1px solid $border;
    border-bottom: 1px solid $border;
    padding: 4px 8px;
    font-size: ${small}px;
}
QTextBrowser, QPlainTextEdit, QTextEdit {
    background-color: $void_100;
    color: $text;
    border: 1px solid $border;
    border-radius: 0px;
    padding: 8px;
}
QTextBrowser:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border-color: $focus;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: $void_100;
    color: $text;
    border: 1px solid $border;
    border-radius: 2px;
    padding: 4px 8px;
    min-height: 16px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: $focus;
}
QLineEdit:disabled, QComboBox:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled {
    color: $text_disabled;
    border-color: $border;
}
QComboBox::drop-down {
    border-left: 1px solid $border;
    width: 16px;
}
QComboBox QAbstractItemView {
    background-color: $panel_raised;
    color: $text;
    border: 1px solid $border_strong;
    selection-background-color: $selection_bg;
    selection-color: $selection_fg;
}
QPushButton {
    background-color: $panel_raised;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 2px;
    padding: 4px 12px;
    min-height: 16px;
}
QPushButton:hover { border-color: $focus; }
QPushButton:pressed { background-color: $selection_bg; color: $selection_fg; }
QPushButton:disabled { color: $text_disabled; border-color: $border; }
QPushButton:focus { border: 1px solid $focus; outline: none; }
QTabWidget::pane {
    background-color: $panel;
    border: 1px solid $border;
    border-radius: 0px;
    top: -1px;
}
QTabBar::tab {
    background-color: $void_100;
    color: $text_muted;
    border: 1px solid $border;
    border-bottom: none;
    border-radius: 0px;
    padding: 4px 12px;
    margin-right: 2px;
    font-size: ${small}px;
}
QTabBar::tab:selected { background-color: $panel; color: $text; }
QTabBar::tab:hover { color: $text; }
QCheckBox, QRadioButton {
    background-color: transparent;
    color: $text;
    spacing: 8px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 14px; height: 14px;
    background-color: $void_100;
    border: 1px solid $border_strong;
}
QCheckBox::indicator { border-radius: 2px; }
QRadioButton::indicator { border-radius: 7px; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: $focus;
    border-color: $focus;
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    border-color: $border;
}
QScrollBar:vertical {
    background-color: $void_100;
    width: 12px;
    margin: 0px;
}
QScrollBar:horizontal {
    background-color: $void_100;
    height: 12px;
    margin: 0px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background-color: $border_strong;
    border-radius: 0px;
    min-height: 24px; min-width: 24px;
}
QScrollBar::handle:hover { background-color: $text_muted; }
QScrollBar::add-line, QScrollBar::sub-line {
    background-color: transparent;
    height: 0px; width: 0px;
}
QScrollBar::add-page, QScrollBar::sub-page { background-color: transparent; }
QStatusBar {
    background-color: $void_100;
    color: $text_muted;
    border-top: 1px solid $border;
    font-size: ${small}px;
}
QStatusBar QLabel { color: $text_muted; }
QProgressBar {
    background-color: $void_100;
    border: 1px solid $border;
    border-radius: 0px;
    text-align: center;
    color: $text;
}
QProgressBar::chunk { background-color: $focus; }
QSplitter::handle { background-color: $border; }
QSlider::groove:horizontal {
    background-color: $border;
    height: 4px;
}
QSlider::handle:horizontal {
    background-color: $panel_raised;
    border: 1px solid $border_strong;
    width: 14px;
    margin: -6px 0px;
    border-radius: 2px;
}
"""

# The stepped double-border frame system (ornament "standard"
# and "ceremonial"): an outer iron line plus an inner line,
# expressed as a QSS double border on the primary frames.
_QSS_DOUBLE_FRAME = """
QMainWindow, QDialog { border: 3px double $border_strong; }
QGroupBox { border: 3px double $border; }
QDockWidget { border: 1px solid $border_strong; }
"""

# Ornament "ceremonial": the double frame, plus accent-tipped
# frame corners/headers — forge titles, a bifrost dock-title
# rule, a forge underline on the selected tab. Accent coverage
# stays in the doctrine's seasoning band: titles and one rule
# per frame, never a filled background.
_QSS_CEREMONIAL = """
/* ornament: ceremonial frame tips */
QGroupBox::title { color: $forge; }
QDockWidget::title {
    color: $forge;
    border-bottom: 2px solid $bifrost;
}
QTabBar::tab:selected { border-bottom: 2px solid $forge; }
QMenuBar::item:selected { color: $bifrost; }
"""


def build_qss(variant: str, ornament: str, text_scale: float) -> str:
    """The application stylesheet for the given appearance.

    ``variant`` is "dark" or "light"; ``ornament`` is "quiet",
    "standard" or "ceremonial"; ``text_scale`` (1.0-2.0,
    clamped) multiplies every font size in the sheet.
    """
    tokens = tokens_for(variant)
    if ornament not in ORNAMENTS:
        raise ValueError(f"unknown ornament level: {ornament!r}")
    scale = clamp_text_scale(text_scale)
    values = {key.replace("-", "_"): value for key, value in tokens.items()}
    values["base"] = str(round(BASE_FONT_PX * scale))
    values["small"] = str(round(_SMALL_PX * scale))
    values["large"] = str(round(_LARGE_PX * scale))
    values["title"] = str(round(_TITLE_PX * scale))
    sheet = Template(_QSS_BODY).substitute(values)
    if ornament in ("standard", "ceremonial"):
        sheet += Template(_QSS_DOUBLE_FRAME).substitute(values)
    if ornament == "ceremonial":
        sheet += Template(_QSS_CEREMONIAL).substitute(values)
    return sheet
