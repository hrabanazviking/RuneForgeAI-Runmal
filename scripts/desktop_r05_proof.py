"""Desktop proof (R-05): first run → wizard → greeted chat → answer.

Launches the REAL windowed app the way ``runmal.desktop.app`` does
(auto-wizard on), on a fresh throwaway data dir. The First-Run Setup
wizard must appear by itself; the driver then works its controls
exactly as a user would:

- Step 1: pick Demo mode (honestly labelled — not a real model) and
  Connect it through the R-02 client roads.
- Step 2: the proof page runs its health probe; the verdict must be
  plain words starting "Reachable".
- Step 3: fill the character form, Create — a greeted chat must land
  (greeting seeded, chat pinned to the Demo profile).
- Step 4: set the user name and Finish.

After the wizard closes, the main window must show the greeted chat
(stage title + greeting + chat list), first-run must read FALSE, and
the resulting chat must ANSWER through the configured backend: a
composed turn (R-03) via the window's own client returns the Demo
backend's canned line with backend key "fake" and mode "composed" —
honest evidence for the Demo road. Clean quit must stop the engine.

Usage (with the ``desktop`` extra installed)::

    RUNMAL_DATA_DIR=<fresh scratch> QT_QPA_PLATFORM=offscreen \
        python scripts/desktop_r05_proof.py

Prints one line:  R05_RESULT {json}
Exit code 0 only on a full pass.
"""

import json
import os
import sys
import time
import urllib.request

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULT = {"slice": "R-05", "platform": sys.platform,
          "python": sys.version.split()[0], "checks": {}}

GREETING = "Well met, traveller. The pass is open."
USER_NAME = "Proof User"


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULT["checks"][name] = {"ok": bool(ok), "detail": detail}
    return bool(ok)


def wait_until(app, predicate, timeout=20.0) -> bool:
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
    from PySide6.QtWidgets import QApplication, QWizard

    RESULT["pyside6"] = pyside_version
    RESULT["qt"] = qVersion()
    RESULT["qpa"] = os.environ.get("QT_QPA_PLATFORM", "")

    app = QApplication(sys.argv)

    from runmal.desktop.app import create_window
    from runmal.desktop.engine import EngineHandle, EngineState

    engine = EngineHandle()
    window = create_window(engine)
    window.show()
    app.processEvents()
    check("window_shown", window.isVisible(), window.windowTitle())

    # Engine through the window's own lifecycle; the first refresh
    # finds a first run and (auto-wizard road) opens the wizard.
    snapshot = window.start_engine_blocking()
    app.processEvents()
    status = engine.status()
    check("engine_running", status.state is EngineState.RUNNING, status.label)
    check(
        "first_run_true_on_fresh",
        snapshot is not None and snapshot.first_run.is_first_run is True,
        snapshot.first_run.label if snapshot else "no snapshot",
    )
    wizard = window._wizard
    appeared = wait_until(
        app, lambda: window._wizard is not None and window._wizard.isVisible()
    )
    wizard = window._wizard
    check("wizard_appeared_on_first_run", appeared and wizard is not None)
    if wizard is None:
        RESULT["pass"] = False
        print("R05_RESULT " + json.dumps(RESULT, sort_keys=True))
        window.close()
        return 1

    from runmal.desktop.wizard import PAGE_MEET, PAGE_NAME, PAGE_PROVE

    check(
        "wizard_starts_on_connect_page",
        wizard.currentId() == 0,
        str(wizard.currentId()),
    )
    demo_button = wizard.connect_page.kind_buttons["fake"]
    check(
        "demo_honestly_labelled",
        "not a real model" in demo_button.text().lower(),
        demo_button.text(),
    )

    # ---- Step 1: connect Demo mode.
    demo_button.setChecked(True)
    app.processEvents()
    wizard.connect_page.connect_button.click()
    connected = wait_until(app, wizard.connect_page.isComplete)
    check("step1_demo_connected", connected,
          wizard.connect_page.connect_status.text())
    check(
        "step1_demo_words_honest",
        "canned" in wizard.connect_page.connect_status.text(),
        wizard.connect_page.connect_status.text(),
    )
    wizard.button(QWizard.WizardButton.NextButton).click()
    app.processEvents()
    check("step2_page", wizard.currentId() == PAGE_PROVE, str(wizard.currentId()))

    # ---- Step 2: the probe runs itself on entry.
    proved = wait_until(app, wizard.prove_page.isComplete)
    prove_words = wizard.prove_page.prove_status.text()
    check("step2_proved_in_words", proved and prove_words.startswith("Reachable"),
          prove_words)
    check("step2_no_raw_json", "{" not in prove_words, prove_words[:80])
    wizard.button(QWizard.WizardButton.NextButton).click()
    app.processEvents()
    check("step3_page", wizard.currentId() == PAGE_MEET, str(wizard.currentId()))

    # ---- Step 3: create the first character; greeted chat lands.
    wizard.meet_page.char_name_edit.setText("Gate Keeper")
    wizard.meet_page.char_description_edit.setPlainText("Guards the high pass.")
    wizard.meet_page.char_personality_edit.setText("Calm, dry, kind.")
    wizard.meet_page.char_greeting_edit.setPlainText(GREETING)
    wizard.meet_page.meet_button.click()
    met = wait_until(app, wizard.meet_page.isComplete)
    result = wizard.setup_result
    check("step3_character_and_chat", met and bool(result.get("chat_id")),
          json.dumps(result))
    check(
        "step3_greeting_preview",
        GREETING in wizard.meet_page.greeting_preview.text(),
        wizard.meet_page.greeting_preview.text(),
    )
    wizard.button(QWizard.WizardButton.NextButton).click()
    app.processEvents()
    check("step4_page", wizard.currentId() == PAGE_NAME, str(wizard.currentId()))

    # ---- Step 4: the user name, then Finish.
    named = wait_until(
        app, lambda: wizard.name_page.user_name_edit.text() == "User"
    )
    check("step4_name_prefilled_default", named,
          wizard.name_page.user_name_edit.text())
    wizard.name_page.user_name_edit.setText(USER_NAME)
    wizard.name_page.save_name_button.click()
    saved = wait_until(app, wizard.name_page.isComplete)
    check("step4_name_saved", saved, wizard.name_page.name_status.text())
    wizard.button(QWizard.WizardButton.FinishButton).click()

    def wizard_closed() -> bool:
        if window._wizard is not None:
            return False
        try:
            return not wizard.isVisible()
        except RuntimeError:
            return True  # a deleted wizard is a closed wizard

    finished = wait_until(app, wizard_closed)
    check("wizard_finished_and_closed", finished)
    check(
        "window_landed_in_greeted_chat",
        window.setup_chat_id == result.get("chat_id")
        and window.stage_title.text() == "Chat with Gate Keeper"
        and GREETING in window.stage_body.text(),
        f"stage={window.stage_title.text()!r} chat={window.setup_chat_id}",
    )

    # Window refresh shows the chat; first run is over.
    snapshot2 = window.refresh_blocking()
    app.processEvents()
    chat_titles = [
        window.chats_list.item(i).text()
        for i in range(window.chats_list.count())
    ]
    check(
        "chat_listed_in_window",
        "First chat with Gate Keeper" in chat_titles,
        ",".join(chat_titles),
    )
    check(
        "first_run_false_after_wizard",
        snapshot2 is not None and snapshot2.first_run.is_first_run is False,
        snapshot2.first_run.label if snapshot2 else "no snapshot",
    )

    # The greeted chat answers through the configured (Demo) backend:
    # a composed turn via the window's own client layer.
    client = window.client()
    messages = client.list_chat_messages(result["chat_id"])
    greeting_seeded = any(
        m.role == "assistant" and m.content == GREETING for m in messages
    )
    check("greeting_seeded_in_chat", greeting_seeded,
          f"messages={len(messages)}")
    reply = client.generate_composed(result["chat_id"])
    check(
        "chat_answers_through_configured_backend",
        reply.text == "Rúnmál hears you."
        and reply.backend_key == "fake"
        and reply.mode == "composed",
        f"text={reply.text!r} backend={reply.backend_key} mode={reply.mode}",
    )
    user_name = client.get_user_name()
    check(
        "user_name_persisted",
        user_name.get("user_name") == USER_NAME
        and user_name.get("is_set") is True,
        json.dumps(user_name),
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
    print("R05_RESULT " + json.dumps(RESULT, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
