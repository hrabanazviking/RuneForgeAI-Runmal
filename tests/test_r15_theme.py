"""R-15 acceptance (logic): the Appendix-B token theme.

Qt-free by design — ``runmal.desktop.theme`` must import and
run without PySide6. Pins: the dark token hexes match
Appendix B of the design lawbook exactly; both variants share
one role set; the built QSS carries the ladder colours;
ornament levels differ as documented (quiet has no double
frame and no ceremonial rules; ceremonial adds them); text
scaling doubles the base font size at 2.0; every AA pair the
app relies on holds >= 4.5 in BOTH variants; prefs survive a
dict round trip and bad stored values fall back to defaults.
"""

from pathlib import Path

from runmal.desktop import theme
from runmal.desktop.theme import (
    AA_PAIRS,
    DARK_TOKENS,
    LIGHT_TOKENS,
    MOTION_TOKENS,
    SPACING,
    AppearancePrefs,
    build_qss,
    contrast_ratio,
    motion_duration,
    prefs_from_dict,
    prefs_to_dict,
)

# Appendix B, transcribed from the lawbook's :root block.
APPENDIX_B_DARK = {
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
}


def test_theme_module_is_qt_free() -> None:
    source = Path(theme.__file__).read_text(encoding="utf-8")
    assert "import PySide6" not in source
    assert "from PySide6" not in source


def test_dark_tokens_match_appendix_b_exactly() -> None:
    for name, hex_value in APPENDIX_B_DARK.items():
        assert DARK_TOKENS[name] == hex_value


def test_variants_share_one_role_set() -> None:
    assert set(DARK_TOKENS) == set(LIGHT_TOKENS)
    # Four distinct ladder surfaces in each variant.
    ladder = ("void-000", "void-100", "panel", "panel-raised")
    for tokens in (DARK_TOKENS, LIGHT_TOKENS):
        assert len({tokens[name] for name in ladder}) == 4


def test_spacing_and_motion_scales_match_appendix_b() -> None:
    assert list(SPACING.values()) == [4, 8, 12, 16, 24, 32, 48, 64, 96]
    assert MOTION_TOKENS == {
        "fast": 100,
        "standard": 180,
        "structural": 320,
        "ceremonial": 600,
    }
    assert motion_duration("standard") == 180
    assert motion_duration("standard", reduced_motion=True) == 0


def test_build_qss_carries_the_ladder_for_both_variants() -> None:
    dark_qss = build_qss("dark", "standard", 1.0)
    for name in ("void-000", "void-100", "panel", "panel-raised"):
        assert DARK_TOKENS[name] in dark_qss
    light_qss = build_qss("light", "standard", 1.0)
    for name in ("void-000", "void-100", "panel", "panel-raised"):
        assert LIGHT_TOKENS[name] in light_qss
    # The widget families the shell is built from are covered.
    for selector in (
        "QMainWindow",
        "QDialog",
        "QMenuBar",
        "QMenu",
        "QToolBar",
        "QDockWidget",
        "QListWidget",
        "QTextBrowser",
        "QPlainTextEdit",
        "QLineEdit",
        "QComboBox",
        "QSpinBox",
        "QPushButton:hover",
        "QPushButton:pressed",
        "QPushButton:disabled",
        "QPushButton:focus",
        "QTabBar::tab",
        "QCheckBox",
        "QRadioButton",
        "QScrollBar",
        "QStatusBar",
        "QLabel",
        "QGroupBox",
        "QToolTip",
    ):
        assert selector in dark_qss, selector


def test_ornament_levels_differ_as_documented() -> None:
    quiet = build_qss("dark", "quiet", 1.0)
    standard = build_qss("dark", "standard", 1.0)
    ceremonial = build_qss("dark", "ceremonial", 1.0)
    # Quiet: single iron border only — no double frame, no
    # ceremonial rules at all.
    assert "double" not in quiet
    assert "ceremonial" not in quiet
    # Standard: the stepped double-border frame system, still
    # no ceremonial accent tips.
    assert "double" in standard
    assert "ceremonial" not in standard
    # Ceremonial: double frame plus the accent-tipped section.
    assert "double" in ceremonial
    assert "ornament: ceremonial frame tips" in ceremonial
    assert DARK_TOKENS["forge"] in ceremonial
    assert DARK_TOKENS["bifrost"] in ceremonial


def test_text_scale_doubles_the_base_font_size() -> None:
    assert "font-size: 13px" in build_qss("dark", "standard", 1.0)
    assert "font-size: 26px" in build_qss("dark", "standard", 2.0)
    assert "font-size: 20px" in build_qss("dark", "standard", 1.5)
    # Out-of-range scales clamp to the 1.0-2.0 band.
    assert "font-size: 26px" in build_qss("dark", "standard", 3.0)


def test_aa_pairs_hold_in_both_variants() -> None:
    for variant, tokens in (("dark", DARK_TOKENS), ("light", LIGHT_TOKENS)):
        for fg_role, bg_role in AA_PAIRS:
            ratio = contrast_ratio(tokens[fg_role], tokens[bg_role])
            assert ratio >= 4.5, (variant, fg_role, bg_role, ratio)


def test_contrast_ratio_known_values() -> None:
    assert contrast_ratio("#000000", "#FFFFFF") == 21.0
    assert contrast_ratio("#CCD6DF", "#CCD6DF") == 1.0


def test_prefs_dict_round_trip() -> None:
    prefs = AppearancePrefs(
        variant="light",
        ornament="ceremonial",
        text_scale=1.75,
        reduced_motion=True,
    )
    assert prefs_from_dict(prefs_to_dict(prefs)) == prefs
    assert prefs_from_dict(prefs_to_dict(AppearancePrefs())) == AppearancePrefs()


def test_prefs_from_dict_falls_back_safely() -> None:
    assert prefs_from_dict(None) == AppearancePrefs()
    assert prefs_from_dict({}) == AppearancePrefs()
    assert prefs_from_dict({"variant": "neon"}) == AppearancePrefs()
    clamped = prefs_from_dict({"text_scale": 9.0})
    assert clamped.text_scale == 2.0
    broken = prefs_from_dict({"text_scale": "wide"})
    assert broken.text_scale == 1.0
