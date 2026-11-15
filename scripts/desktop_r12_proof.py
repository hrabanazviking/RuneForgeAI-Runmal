"""Desktop proof (R-12): Memory, Scenarios, Inspector & Tools
in the real windowed app.

Launches the REAL windowed app on a fresh throwaway data dir
and drives the four R-12 surfaces through the window's own
controls:

- A real turn is sent in a chat about the ember; the Prompt
  Inspector (opened from the window, bound to that chat)
  explains the prompt that was actually built: ledger line,
  a lore slot Included with its reason and its trigger, and
  the Overview / Events / Reasoning documents render.
- A scenario with bootstrap lines is created, then bound —
  through the Scenarios dialog — to a fresh empty chat; the
  chat gains the scenario's opening lines.
- The Memory browser opens and honestly reports the fresh
  store (no memories yet) and names where embeddings live.
- The Compose & Macros explorer lists the engine's macros,
  expands one, and previews a composed prompt.
- RESTART the whole app on the same data dir: the scenario
  and its binding persist.
- Clean quit stops the engine.

Usage (with the ``desktop`` extra installed)::

    RUNMAL_DATA_DIR=<fresh scratch> QT_QPA_PLATFORM=offscreen \
        python scripts/desktop_r12_proof.py

Prints one line:  R12_RESULT {json}
Exit code 0 only on a full pass.
"""

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULT = {"slice": "R-12", "platform": sys.platform,
          "python": sys.version.split()[0], "checks": {}}

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
    from PySide6.QtWidgets import QApplication, QLabel

    RESULT["pyside6"] = pyside_version
    RESULT["qt"] = qVersion()
    RESULT["qpa"] = os.environ.get("QT_QPA_PLATFORM", "")

    app = QApplication(sys.argv)
    data_dir = Path(os.environ["RUNMAL_DATA_DIR"])
    RESULT["data_dir"] = str(data_dir)

    from runmal.desktop.app import create_window
    from runmal.desktop.engine import EngineHandle, EngineState
    from runmal.desktop.lore_logic import LoreFlow, schema_fields

    engine = EngineHandle()
    window = create_window(engine)
    window.show()
    app.processEvents()
    check("window_shown", window.isVisible(), window.windowTitle())

    snapshot = window.start_engine_blocking()
    app.processEvents()
    status = engine.status()
    check("engine_running", status.state is EngineState.RUNNING, status.label)
    check(
        "first_run_true_on_fresh",
        snapshot is not None and snapshot.first_run.is_first_run is True,
        snapshot.first_run.label if snapshot else "no snapshot",
    )
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

    # A keyworded lorebook scoped to the keeper (R-10 pattern).
    lore = LoreFlow(client)
    schema = lore.schema()
    book = lore.save_book(None, schema_fields(schema, "book"), {
        "name": "Gate World", "description": "", "scan_depth": 4,
        "token_budget": None, "scan_mode": "depth",
        "scan_external_context": False,
    }, None)
    entry = lore.save_entry(book.id, None, schema_fields(schema, "entry"), {
        "name": "Ember fact",
        "content": "Embers remember every fire.",
        "keys": ["ember"], "secondary_keys": [],
        "selective_logic": "and_any", "inclusion_group": "",
        "group_weight": 100, "probability": 100, "priority": 100,
        "position": "before_char", "depth": None, "role": "system",
        "enabled": True, "constant": False, "vectorised": False,
        "case_sensitive": False, "whole_word": True,
        "sticky_prompts": 0, "cooldown_prompts": 0, "delay_prompts": 0,
    }, None)
    check("lorebook_seeded", bool(entry.id))
    lore.assign_scope(book.id, "character", keeper.id)

    window.refresh_blocking()
    app.processEvents()

    # ---- A real turn in a real chat.
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
        and any(
            "ember" in m.content.lower() for m in window.current_messages
        ),
        str(len(window.current_messages)),
    )

    # ---- The Inspector, bound to the open chat.
    inspector = window.open_inspector_dialog()
    check(
        "inspector_shown",
        inspector is not None and inspector.isVisible(),
    )
    check(
        "ledger_in_words",
        "input budget" in inspector.ledger_label.text(),
        inspector.ledger_label.text(),
    )
    slot_texts = [
        inspector.slots_list.item(i).text()
        for i in range(inspector.slots_list.count())
    ]
    check("slots_listed", len(slot_texts) >= 3, str(len(slot_texts)))
    lore_slots = [t for t in slot_texts if t.startswith("lore")]
    check(
        "lore_slot_included",
        any("Included" in t for t in lore_slots),
        " | ".join(lore_slots)[:160],
    )
    check(
        "lore_slot_names_trigger",
        any("ember" in t for t in lore_slots),
        " | ".join(lore_slots)[:160],
    )
    overview_text = inspector._doc_views["overview"].toPlainText()
    events_text = inspector._doc_views["events"].toPlainText()
    reasoning_text = inspector._doc_views["reasoning"].toPlainText()
    check(
        "overview_document",
        "chat" in overview_text.lower(),
        overview_text[:80],
    )
    check(
        "events_document",
        bool(events_text.strip()),
        events_text[:80],
    )
    check(
        "reasoning_document",
        bool(reasoning_text.strip()),
        reasoning_text[:80],
    )
    inspector.close()

    # ---- A scenario, created then bound through the dialog.
    scenario = window.scenarios_flow().create({
        "name": "Gate Watch",
        "description": "A night at the pass.",
        "scenario_text": "Snow closes in.",
        "flow": "chat",
        "bootstrap_messages": [
            {"kind": "message", "role": "assistant",
             "text": "The watch begins."}
        ],
    })
    check("scenario_created", bool(scenario.id), scenario.id)
    stage = client.create_chat(title="Empty stage")
    # The dialog binds to the window's open chat, and binding
    # requires an empty one — open the stage chat in the window.
    window.open_chat_blocking(stage.id)
    app.processEvents()
    scenarios = window.open_scenarios_dialog()
    check(
        "scenarios_shown",
        scenarios is not None and scenarios.isVisible(),
    )
    scenarios._reload()
    app.processEvents()
    names = [
        scenarios.library_list.item(i).text()
        for i in range(scenarios.library_list.count())
    ]
    check("scenario_in_library", any("Gate Watch" in n for n in names),
          str(names))
    scenarios._scenario = scenario
    scenarios._bind()
    app.processEvents()
    seeded = [
        m.content for m in client.list_chat_messages(stage.id)
    ]
    check("bootstrap_seeded", "The watch begins." in seeded, str(seeded))
    check(
        "binding_named_in_dialog",
        "Bound scenario: Gate Watch" in scenarios.binding_label.text(),
        scenarios.binding_label.text(),
    )
    scenarios.close()

    # ---- The Memory browser: honest on a fresh store.
    memory = window.open_memory_dialog()
    check("memory_shown", memory is not None and memory.isVisible())
    check(
        "memory_empty_state_honest",
        memory.memories_list.count() == 0
        and "No memories match" in memory.detail_text.toPlainText(),
        memory.detail_text.toPlainText()[:80],
    )
    note_texts = [
        label.text() for label in memory.findChildren(QLabel)
    ]
    check(
        "embedding_note_present",
        any("Connections" in t for t in note_texts),
        " | ".join(note_texts)[:120],
    )
    memory.close()

    # ---- Compose & Macros.
    compose = window.open_compose_dialog()
    check("compose_shown", compose is not None and compose.isVisible())
    check(
        "macros_listed",
        compose.macros_list.count() > 0,
        str(compose.macros_list.count()),
    )
    compose.expand_text.setText("{{char}} stands watch.")
    compose.expand_char.setText("Gate Keeper")
    compose._expand()
    check(
        "macro_expanded",
        compose.expand_output.toPlainText() == "Gate Keeper stands watch.",
        compose.expand_output.toPlainText(),
    )
    compose.compose_system.setPlainText("Be kind.")
    compose._compose()
    check(
        "compose_preview",
        "[system] Be kind." in compose.compose_output.toPlainText(),
        compose.compose_output.toPlainText()[:120],
    )
    compose.close()

    # ---- Restart: scenario + binding persist.
    window.close()
    app.processEvents()
    check(
        "engine_stopped_for_restart",
        wait_until(app, lambda: engine.status().state is EngineState.STOPPED),
        engine.status().label,
    )
    engine2 = EngineHandle()
    window2 = create_window(engine2)
    window2.show()
    window2.start_engine_blocking()
    app.processEvents()
    check(
        "engine_running_after_restart",
        engine2.status().state is EngineState.RUNNING,
        engine2.status().label,
    )
    client2 = window2.client()
    library2 = client2.list_scenarios()
    check(
        "scenario_persists",
        any(s.name == "Gate Watch" for s in library2),
        str([s.name for s in library2]),
    )
    binding2 = client2.get_chat_binding(stage.id)
    check(
        "binding_persists",
        binding2 is not None
        and binding2.get("definition_name") == "Gate Watch",
        str(binding2),
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
    print("R12_RESULT " + json.dumps(RESULT))
    return 0 if RESULT["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
