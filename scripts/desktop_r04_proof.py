"""Desktop-shell proof (R-04): launch the real window, drive it.

Creates the QApplication + MainWindow, shows the window, asserts the
§2.3 menus exist, triggers real actions programmatically (dock
toggles, About, First-Run status, engine start via the window's own
lifecycle), reads the status bar's engine state against a REAL
/healthz answer, exercises first-run detection on a fresh data dir
(true) and after configuring a profile + character through the
client/API (false), then clean-quits and asserts the engine stopped.

Usage (with the ``desktop`` extra installed)::

    RUNMAL_DATA_DIR=<fresh scratch> QT_QPA_PLATFORM=offscreen \
        python scripts/desktop_r04_proof.py

Prints one line:  R04_RESULT {json}
Exit code 0 only on a full pass.
"""

import json
import os
import sys
import time
import urllib.request

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULT = {"slice": "R-04", "platform": sys.platform,
          "python": sys.version.split()[0], "checks": {}}


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULT["checks"][name] = {"ok": bool(ok), "detail": detail}
    return bool(ok)


def main() -> int:
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication

    RESULT["pyside6"] = pyside_version
    RESULT["qt"] = qVersion()
    RESULT["qpa"] = os.environ.get("QT_QPA_PLATFORM", "")

    app = QApplication(sys.argv)

    from runmal.desktop.engine import EngineHandle, EngineState
    from runmal.desktop.window import MENU_TITLES, MainWindow

    engine = EngineHandle()
    window = MainWindow(engine)
    window.show()
    app.processEvents()
    check("window_shown", window.isVisible(), window.windowTitle())
    check("window_title", window.windowTitle() == "Rúnmál")

    titles = [a.text() for a in window.menuBar().actions()]
    check("menus", titles == MENU_TITLES, ",".join(titles))

    # Trigger real, non-modal actions programmatically.
    window.library_dock.toggleViewAction().trigger()
    app.processEvents()
    dock_hidden = not window.library_dock.isVisible()
    window.library_dock.toggleViewAction().trigger()
    app.processEvents()
    check("dock_toggle", dock_hidden and window.library_dock.isVisible())
    window.action_about.trigger()
    app.processEvents()
    about = getattr(window, "_about_dialog", None)
    check("about_dialog", about is not None and about.isVisible())
    if about is not None:
        about.close()
    window.placeholder_actions["Connections…"].trigger()
    app.processEvents()
    check(
        "placeholder_honest",
        "R-09" in window.statusBar().currentMessage(),
        window.statusBar().currentMessage(),
    )

    # Engine lifecycle through the window's own blocking road.
    snapshot = window.start_engine_blocking()
    app.processEvents()
    status = engine.status()
    check("engine_running", status.state is EngineState.RUNNING, status.label)
    check(
        "status_bar_engine",
        "running" in window.engine_status_label.text(),
        window.engine_status_label.text(),
    )
    health = None
    try:
        with urllib.request.urlopen(
            f"{engine.base_url}/healthz", timeout=5
        ) as resp:
            health = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # recorded, not hidden
        RESULT["healthz_error"] = f"{exc.__class__.__name__}: {exc}"
    check("healthz_real", bool(health and health.get("status") == "ok"),
          json.dumps(health))

    # First-run detection against the fresh data dir: must be TRUE.
    check("snapshot_returned", snapshot is not None)
    if snapshot is not None:
        check(
            "first_run_true_on_fresh",
            snapshot.first_run.is_first_run is True,
            snapshot.first_run.label,
        )
        check("first_run_banner", window.first_run_banner.isVisible())
        window.action_first_run.trigger()
        app.processEvents()
        check(
            "first_run_action_message",
            "First run detected" in window.statusBar().currentMessage(),
            window.statusBar().currentMessage(),
        )

    # Configure via the real API, then detection must flip to FALSE.
    import httpx

    from runmal.auth import get_or_create_credential

    token = get_or_create_credential()
    card = {
        "name": "Proof Companion",
        "description": "Stands at the R-04 proof gate.",
        "personality": "Calm.",
        "scenario": "A test hall.",
        "first_mes": "Well met.",
        "system_prompt": "You are the Proof Companion.",
    }
    with httpx.Client(
        base_url=engine.base_url, trust_env=False, timeout=10.0,
        headers={"Authorization": f"Bearer {token}"},
    ) as http:
        created = http.post(
            "/api/v1/backend-profiles",
            json={"name": "hearth", "chat_backend": "fake",
                  "chat_model": "fake-1"},
        )
        made = http.post("/api/v1/characters", json={"card": card})
    check("configure_api", created.status_code == 201
          and made.status_code in (200, 201),
          f"profile={created.status_code} character={made.status_code}")

    snapshot2 = window.refresh_blocking()
    app.processEvents()
    check(
        "first_run_false_after_configure",
        snapshot2.first_run.is_first_run is False,
        snapshot2.first_run.label,
    )
    check(
        "lists_rendered",
        window.chats_list.count() >= 0
        and window.characters_list.count() == 1
        and window.characters_list.item(0).text() == "Proof Companion",
        f"characters={window.characters_list.count()}",
    )
    check(
        "session_backend_label",
        "hearth" in window.session_backend_label.text(),
        window.session_backend_label.text(),
    )

    # Clean quit: closing the window stops the engine.
    window.close()
    app.processEvents()
    deadline = time.time() + 10
    stopped = False
    while time.time() < deadline:
        if engine.status().state is EngineState.STOPPED:
            stopped = True
            break
        time.sleep(0.2)
    check("engine_stopped_on_quit", stopped, engine.status().label)
    try:
        urllib.request.urlopen(f"{engine.base_url}/healthz", timeout=2)
        health_after = True
    except Exception:
        health_after = False
    check("healthz_gone_after_quit", not health_after)

    app.quit()
    passed = all(c["ok"] for c in RESULT["checks"].values())
    RESULT["pass"] = passed
    print("R04_RESULT " + json.dumps(RESULT, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
