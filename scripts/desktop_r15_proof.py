"""Desktop proof (R-15): Appearance & the doctrine pass, with
the Book XIV removal battery, in the real windowed app.

Launches the REAL windowed app on a fresh throwaway data dir
(QSettings hermetic under a scratch XDG_CONFIG_HOME) and:

- The app comes up themed out of the box: the Appendix B
  dark token stylesheet is in force before any dialog opens.
- A real chat with real content is put on stage, so the
  battery judges the app dressed, not an empty shell
  (Book XIV's screenshot-bias failure mode).
- The Appearance dialog switches the app to the Light
  variant, raises text scaling to 200%, sets ceremonial
  ornament and reduced motion — each verified against the
  running application (stylesheet identity, base font size,
  the window's reduced-motion flag), never just the dialog.
- BATTERY (Book XIV removal tests): a screenshot set is
  captured — dark/standard, dark/quiet (ornament removed),
  dark/ceremonial, light/standard, dark at 200% text, and
  grayscale conversions of the dark and light shots — so a
  reviewer can run the grayscale / no-glow / no-art legs and
  the three-second silhouette read on real content.
- Contrast is spot-checked mechanically: every AA pair in
  the theme module must hold >= 4.5 in BOTH variants.
- RESTART the app: the saved appearance (light, ceremonial,
  150%, reduced motion) is in force again — QSettings
  persistence, engine data untouched.
- Clean quit stops the engine.

Usage (with the ``desktop`` extra installed)::

    RUNMAL_DATA_DIR=<fresh scratch> XDG_CONFIG_HOME=<scratch> \
        QT_QPA_PLATFORM=offscreen \
        python scripts/desktop_r15_proof.py

Prints one line:  R15_RESULT {json}
Exit code 0 only on a full pass.
"""

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULT = {"slice": "R-15", "platform": sys.platform,
          "python": sys.version.split()[0], "checks": {},
          "battery": {}}

CARD = {
    "name": "Gate Keeper",
    "description": "Guards the high pass.",
    "personality": "Calm, dry, kind.",
    "scenario": "A mountain pass above the tree line.",
    "system_prompt": "You guard the high pass.",
    "first_mes": "Well met, traveller. The pass is open.",
}


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULT["checks"][name] = {"ok": bool(ok), "detail": detail}
    return bool(ok)


def wait_until(app, predicate, timeout=25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    app.processEvents()
    return predicate()


def main() -> int:
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import qVersion
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    RESULT["pyside6"] = pyside_version
    RESULT["qt"] = qVersion()
    RESULT["qpa"] = os.environ.get("QT_QPA_PLATFORM", "")

    app = QApplication(sys.argv)
    data_dir = Path(os.environ["RUNMAL_DATA_DIR"])
    RESULT["data_dir"] = str(data_dir)
    shots = data_dir.parent / (data_dir.name + "-shots")
    shots.mkdir(parents=True, exist_ok=True)

    from runmal.desktop.app import create_window
    from runmal.desktop.engine import EngineHandle, EngineState
    from runmal.desktop.theme import (
        AA_PAIRS,
        BASE_FONT_PX,
        DARK_TOKENS,
        LIGHT_TOKENS,
        build_qss,
        contrast_ratio,
        motion_duration,
    )

    def grab(window, name: str) -> Path:
        app.processEvents()
        path = shots / name
        window.grab().save(str(path))
        return path

    engine = EngineHandle()
    window = create_window(engine)
    window.resize(1280, 800)
    window.show()
    app.processEvents()
    check("window_shown", window.isVisible(), window.windowTitle())

    # Themed out of the box, before any dialog: the dark
    # Appendix B stylesheet is the running stylesheet.
    sheet0 = app.styleSheet()
    check(
        "themed_out_of_the_box",
        sheet0 == build_qss("dark", "standard", 1.0)
        and DARK_TOKENS["void-000"] in sheet0,
        f"{len(sheet0)} chars of QSS",
    )
    prefs0 = window.appearance_prefs
    check(
        "default_prefs",
        (prefs0.variant, prefs0.ornament, prefs0.text_scale,
         prefs0.reduced_motion) == ("dark", "standard", 1.0, False),
        str(prefs0),
    )

    window.start_engine_blocking()
    app.processEvents()
    status = engine.status()
    check("engine_running", status.state is EngineState.RUNNING,
          status.label)
    if window._wizard is not None:
        window._wizard.close()
        app.processEvents()
        window._wizard = None

    client = window.client()
    profile = client.create_backend_profile(
        "Demo", "fake", chat_model="fake-1"
    )
    check("profile_seeded", bool(profile.id))
    keeper = client.create_character(dict(CARD), name="Gate Keeper")
    check("character_seeded", bool(keeper.id))
    chat = client.create_chat(title="Gate chat", character_id=keeper.id)
    window.open_chat_blocking(chat.id)
    app.processEvents()
    window.composer_edit.setPlainText(
        "Tell me about the ember at the gate."
    )
    window.send_button.click()
    check(
        "turn_sent",
        wait_until(app, lambda: not window._streaming, timeout=30.0)
        and len(window.current_messages) >= 2,
        str(len(window.current_messages)),
    )

    # ---- Contrast spot-check: every AA pair, both variants.
    worst = {}
    for variant, tokens in (("dark", DARK_TOKENS),
                            ("light", LIGHT_TOKENS)):
        low = min(
            contrast_ratio(tokens[fg], tokens[bg])
            for fg, bg in AA_PAIRS
        )
        worst[variant] = round(low, 2)
    check(
        "contrast_aa_both_variants",
        all(v >= 4.5 for v in worst.values()),
        str(worst),
    )

    # ---- The battery screenshot set (real content on stage).
    battery = {}
    battery["dark_standard"] = str(grab(window, "dark-standard.png"))
    dialog = window.open_appearance_dialog()
    check(
        "appearance_shown",
        dialog is not None and dialog.isVisible(),
    )

    def apply_dialog() -> None:
        dialog.apply_button.click()
        app.processEvents()

    def set_combo(combo, value: str) -> None:
        idx = combo.findData(value)
        assert idx >= 0, f"{value} not in combo"
        combo.setCurrentIndex(idx)

    set_combo(dialog.ornament_combo, "quiet")
    apply_dialog()
    battery["dark_quiet"] = str(grab(window, "dark-quiet.png"))
    set_combo(dialog.ornament_combo, "ceremonial")
    apply_dialog()
    battery["dark_ceremonial"] = str(
        grab(window, "dark-ceremonial.png")
    )
    set_combo(dialog.ornament_combo, "standard")
    set_combo(dialog.variant_combo, "light")
    apply_dialog()
    check(
        "light_variant_applied",
        app.styleSheet() == build_qss("light", "standard", 1.0)
        and LIGHT_TOKENS["panel"] in app.styleSheet(),
        window.appearance_prefs.variant,
    )
    battery["light_standard"] = str(
        grab(window, "light-standard.png")
    )
    set_combo(dialog.variant_combo, "dark")
    dialog.scale_spin.setValue(200)
    apply_dialog()
    check(
        "text_scale_200_applied",
        app.font().pixelSize() == round(BASE_FONT_PX * 2.0),
        f"font pixel size {app.font().pixelSize()}",
    )
    battery["dark_200"] = str(grab(window, "dark-200.png"))
    dialog.scale_spin.setValue(100)
    dialog.reduced_motion_check.setChecked(True)
    apply_dialog()
    check(
        "reduced_motion_applied",
        window.reduced_motion is True
        and motion_duration("standard", True) == 0
        and motion_duration("standard", False) == 180,
        str(window.reduced_motion),
    )
    # Grayscale legs of the battery (Book XIV: hierarchy must
    # survive colour removal entirely).
    for src_name, out_name in (
        ("dark-standard.png", "dark-standard-gray.png"),
        ("light-standard.png", "light-standard-gray.png"),
    ):
        img = QImage(str(shots / src_name))
        gray = img.convertToFormat(QImage.Format.Format_Grayscale8)
        gray.save(str(shots / out_name))
        battery[out_name.removesuffix(".png").replace("-", "_")] = str(
            shots / out_name
        )
    RESULT["battery"] = battery
    shot_sizes = {
        name: Path(p).stat().st_size for name, p in battery.items()
    }
    check(
        "battery_shots_captured",
        len(battery) == 7
        and all(s > 4000 for s in shot_sizes.values()),
        str(shot_sizes),
    )

    # ---- Persistence: choose the kept look, restart, verify.
    set_combo(dialog.variant_combo, "light")
    set_combo(dialog.ornament_combo, "ceremonial")
    dialog.scale_spin.setValue(150)
    apply_dialog()
    dialog.close()
    kept = window.appearance_prefs
    check(
        "kept_prefs_recorded",
        (kept.variant, kept.ornament, kept.text_scale,
         kept.reduced_motion) == ("light", "ceremonial", 1.5, True),
        str(kept),
    )
    window.close()
    app.processEvents()
    check(
        "engine_stopped_for_restart",
        wait_until(
            app, lambda: engine.status().state is EngineState.STOPPED
        ),
        engine.status().label,
    )
    engine2 = EngineHandle()
    window2 = create_window(engine2)
    window2.show()
    app.processEvents()
    prefs2 = window2.appearance_prefs
    check(
        "prefs_persist_across_restart",
        (prefs2.variant, prefs2.ornament, prefs2.text_scale,
         prefs2.reduced_motion) == ("light", "ceremonial", 1.5, True)
        and app.styleSheet()
        == build_qss("light", "ceremonial", 1.5),
        str(prefs2),
    )
    window2.start_engine_blocking()
    app.processEvents()
    check(
        "engine_running_after_restart",
        engine2.status().state is EngineState.RUNNING,
        engine2.status().label,
    )

    window2.close()
    app.processEvents()
    check(
        "engine_stopped_on_quit",
        wait_until(
            app, lambda: engine2.status().state is EngineState.STOPPED
        ),
        engine2.status().label,
    )
    import urllib.request

    try:
        urllib.request.urlopen(engine2.base_url + "/healthz", timeout=2)
        healthz_gone = False
    except Exception:
        healthz_gone = True
    check("healthz_gone_after_quit", healthz_gone)

    RESULT["pass"] = all(c["ok"] for c in RESULT["checks"].values())
    print("R15_RESULT " + json.dumps(RESULT))
    return 0 if RESULT["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
