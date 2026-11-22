"""R-15 acceptance (widgets): the Appearance dialog and the
MainWindow wiring — startup theming, live Apply, saving.

Skips cleanly when PySide6 is absent (R-04 pattern). The
appearance QSettings key is cleared around every test so a
saved choice can never leak between tests or onto the host's
real settings.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from runmal.desktop.engine import EngineHandle  # noqa: E402
from runmal.desktop.theme import AppearancePrefs, build_qss  # noqa: E402
from runmal.desktop.window import (  # noqa: E402
    _APPEARANCE_SETTINGS_KEY,
    AppearanceDialog,
    MainWindow,
    load_appearance_prefs,
    save_appearance_prefs,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def clean_appearance_settings(qapp):
    settings = QSettings("Runmal", "Runmal Desktop")
    settings.remove(_APPEARANCE_SETTINGS_KEY)
    settings.sync()
    yield
    settings.remove(_APPEARANCE_SETTINGS_KEY)
    settings.sync()


class FakeClient:
    def new_request_id(self):
        return "req-r15"

    def list_presets(self):
        return []


# ------------------------------------------------------------- dialog


def test_dialog_opens_with_current_prefs(qapp) -> None:
    applied: list = []
    prefs = AppearancePrefs(
        variant="light",
        ornament="quiet",
        text_scale=1.5,
        reduced_motion=True,
    )
    dialog = AppearanceDialog(None, prefs, applied.append)
    dialog.show()
    try:
        assert dialog.variant_combo.currentData() == "light"
        assert dialog.ornament_combo.currentData() == "quiet"
        assert dialog.scale_spin.value() == 150
        assert dialog.scale_slider.value() == 150
        assert dialog.reduced_motion_check.isChecked()
        assert dialog.current_prefs() == prefs
        # The words say what the controls do and where the
        # choices live.
        assert "engine data is untouched" in dialog.PERSISTENCE_NOTE
    finally:
        dialog.close()


def test_dialog_slider_and_spinbox_stay_in_step(qapp) -> None:
    dialog = AppearanceDialog(None, AppearancePrefs(), lambda prefs: None)
    dialog.show()
    try:
        dialog.scale_slider.setValue(175)
        assert dialog.scale_spin.value() == 175
        dialog.scale_spin.setValue(125)
        assert dialog.scale_slider.value() == 125
    finally:
        dialog.close()


# ------------------------------------------------------------- window


def test_fresh_window_comes_up_themed_with_defaults(qapp) -> None:
    window = MainWindow(EngineHandle(), client=FakeClient())
    window.show()
    try:
        assert window.appearance_prefs == AppearancePrefs()
        assert window.reduced_motion is False
        sheet = QApplication.instance().styleSheet()
        assert sheet == build_qss("dark", "standard", 1.0)
        assert window.action_appearance.text() == "Appearance…"
        assert "Appearance…" not in window.placeholder_actions
    finally:
        window.close()


def test_apply_light_variant_changes_stylesheet_and_saves(qapp) -> None:
    window = MainWindow(EngineHandle(), client=FakeClient())
    window.show()
    try:
        dialog = window.open_appearance_dialog()
        assert isinstance(dialog, AppearanceDialog)
        index = dialog.variant_combo.findData("light")
        dialog.variant_combo.setCurrentIndex(index)
        dialog._apply()
        assert QApplication.instance().styleSheet() == build_qss(
            "light", "standard", 1.0
        )
        assert window.appearance_prefs.variant == "light"
        assert load_appearance_prefs().variant == "light"
        assert "Applied and saved" in dialog.status_label.text()
        dialog.close()
    finally:
        window.close()


def test_apply_scaling_and_reduced_motion(qapp) -> None:
    window = MainWindow(EngineHandle(), client=FakeClient())
    window.show()
    try:
        dialog = window.open_appearance_dialog()
        dialog.scale_spin.setValue(150)
        dialog.reduced_motion_check.setChecked(True)
        dialog._apply()
        sheet = QApplication.instance().styleSheet()
        assert sheet == build_qss("dark", "standard", 1.5)
        assert "font-size: 20px" in sheet
        assert QApplication.instance().font().pixelSize() == 20
        assert window.reduced_motion is True
        saved = load_appearance_prefs()
        assert saved.text_scale == 1.5
        assert saved.reduced_motion is True
        dialog.close()
    finally:
        window.close()


def test_saved_prefs_are_applied_at_startup(qapp) -> None:
    first = MainWindow(EngineHandle(), client=FakeClient())
    first.apply_appearance(
        AppearancePrefs(variant="light", ornament="ceremonial")
    )
    save_appearance_prefs(first.appearance_prefs)
    first.close()
    second = MainWindow(EngineHandle(), client=FakeClient())
    second.show()
    try:
        assert second.appearance_prefs.variant == "light"
        assert second.appearance_prefs.ornament == "ceremonial"
        assert QApplication.instance().styleSheet() == build_qss(
            "light", "ceremonial", 1.0
        )
    finally:
        second.close()
