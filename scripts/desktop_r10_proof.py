"""Desktop proof (R-10): Persona & Lorebooks in the real
windowed app.

Launches the REAL windowed app on a fresh throwaway data dir
and drives the R-10 surfaces through the window's own controls,
verifying state via the API after each:

- The Persona dialog sets the persisted ``{{user}}`` name and
  switches the chat's persona character (the Session dock
  follows), then switches it back.
- The Lorebooks dialog creates a book and a keyworded entry
  through the census-generated forms and assigns the book to
  the chat's character through a scope.
- The chat is asked about the keyworded fact (a real send
  through the Demo profile), and the dialog's layered chat
  preview shows the entry fired — Included, matched key named;
  the book-only preview agrees.
- RESTART the whole app on the same data dir: the user name,
  the book, the entry, the scope, and the persona persist.
- Clean quit stops the engine.

Usage (with the ``desktop`` extra installed)::

    RUNMAL_DATA_DIR=<fresh scratch> QT_QPA_PLATFORM=offscreen \
        python scripts/desktop_r10_proof.py

Prints one line:  R10_RESULT {json}
Exit code 0 only on a full pass.
"""

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULT = {"slice": "R-10", "platform": sys.platform,
          "python": sys.version.split()[0], "checks": {}}

CARD = {
    "name": "Gate Keeper",
    "description": "Guards the high pass.",
    "personality": "Calm, dry, kind.",
    "scenario": "A mountain pass above the tree line.",
    "system_prompt": "You guard the high pass.",
    "first_mes": "Well met, traveller. The pass is open.",
}
MASK_CARD = {**CARD, "name": "Mask Bearer"}
DEMO_REPLY = "Rúnmál hears you."


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


def send_line(app, window, text: str) -> bool:
    window.composer_edit.setPlainText(text)
    window.send_button.click()
    return wait_until(app, lambda: not window._streaming, timeout=30.0)


def main() -> int:
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication

    RESULT["pyside6"] = pyside_version
    RESULT["qt"] = qVersion()
    RESULT["qpa"] = os.environ.get("QT_QPA_PLATFORM", "")

    app = QApplication(sys.argv)
    data_dir = Path(os.environ["RUNMAL_DATA_DIR"])
    RESULT["data_dir"] = str(data_dir)

    from runmal.desktop.app import create_window
    from runmal.desktop.engine import EngineHandle, EngineState

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
    keeper = client.create_character(dict(CARD), name="Gate Keeper")
    mask = client.create_character(dict(MASK_CARD), name="Mask Bearer")
    chat = client.create_chat(title="Gate chat", character_id=keeper.id)
    profile = client.create_backend_profile(
        "Demo", "fake", chat_model="fake-1"
    )
    check("demo_profile_seeded", bool(profile.id), profile.id)
    window.refresh_blocking()
    window.open_chat_blocking(chat.id)
    chat_row = client.get_chat(chat.id)
    check(
        "chat_opened",
        chat_row is not None and chat_row.id == chat.id,
    )

    # ---- Persona: name + switch through the dialog.
    persona = window.open_persona_dialog()
    check("persona_dialog_shown", persona is not None and persona.isVisible())
    check(
        "persona_dialog_loaded",
        wait_until(app, lambda: "built-in default" in persona.user_name_state.text()),
        persona.user_name_state.text(),
    )
    persona.user_name_edit.setText("Volmarr")
    persona.save_name_button.click()
    check(
        "user_name_set_via_dialog",
        wait_until(app, lambda: client.get_user_name().get("is_set") is True),
        str(client.get_user_name()),
    )
    index = persona.persona_combo.findData(mask.id)
    persona.persona_combo.setCurrentIndex(index)
    persona.set_persona_button.click()
    check(
        "persona_switched_via_dialog",
        wait_until(
            app,
            lambda: client.get_chat_persona(chat.id).character_id == mask.id,
        ),
    )
    check(
        "session_dock_follows_persona",
        wait_until(
            app, lambda: "Mask Bearer" in window.session_persona_label.text()
        ),
        window.session_persona_label.text(),
    )
    index = persona.persona_combo.findData(keeper.id)
    persona.persona_combo.setCurrentIndex(index)
    persona.set_persona_button.click()
    check(
        "persona_restored_via_dialog",
        wait_until(
            app,
            lambda: client.get_chat_persona(chat.id).character_id == keeper.id,
        ),
    )
    persona.close()
    app.processEvents()

    # ---- Lorebooks: book + entry + scope through the dialog.
    lore = window.open_lorebooks_dialog()
    check("lorebooks_dialog_shown", lore is not None and lore.isVisible())
    check(
        "schema_forms_built",
        wait_until(app, lambda: lore.book_form is not None
                   and lore.entry_form is not None),
    )
    check(
        "entry_form_generated_from_census",
        lore.entry_form.editor_for("keys") is not None
        and lore.entry_form.editor_for("sticky_prompts") is not None
        and lore.entry_form.editor_for("activation_kind") is not None,
    )
    lore.new_book()
    lore.book_form.set_field_value("name", "Gate World")
    lore.save_book_button.click()
    check(
        "book_created_via_dialog",
        wait_until(app, lambda: len(client.list_lorebook_views()) == 1),
    )
    book = client.list_lorebook_views()[0]
    check(
        "dialog_tracks_saved_book",
        wait_until(app, lambda: lore.books_combo.currentData() == book.id),
        lore.books_combo.currentText(),
    )
    lore.new_entry()
    lore.entry_form.set_field_value("name", "Ember fact")
    lore.entry_form.set_field_value(
        "content", "The gate ember remembers every traveller."
    )
    lore.entry_form.set_field_value("keys", ["ember"])
    lore.save_entry_button.click()
    check(
        "entry_created_via_dialog",
        wait_until(app, lambda: len(client.list_lore_entries(book.id)) == 1),
    )
    entries = client.list_lore_entries(book.id)
    check(
        "entry_keys_exact",
        entries[0].raw.get("keys") == ["ember"],
        str(entries[0].raw.get("keys")),
    )
    kind_index = lore.scope_kind_combo.findData("character")
    lore.scope_kind_combo.setCurrentIndex(kind_index)
    check(
        "scope_owner_combo_populated",
        wait_until(app, lambda: lore.scope_owner_combo.findData(keeper.id) >= 0),
    )
    lore.scope_owner_combo.setCurrentIndex(
        lore.scope_owner_combo.findData(keeper.id)
    )
    lore.assign_scope_button.click()
    check(
        "scope_assigned_via_dialog",
        wait_until(app, lambda: len(client.list_book_scopes(book.id)) == 1),
    )
    check(
        "scopes_list_shows_assignment",
        wait_until(app, lambda: lore.scopes_list.count() == 1),
        lore.scopes_list.item(0).text() if lore.scopes_list.count() else "",
    )

    # ---- Ask about the keyworded fact, then preview.
    sent = send_line(app, window, "tell me about the ember")
    check("message_sent", sent)
    check(
        "demo_reply_landed",
        wait_until(
            app,
            lambda: any(
                m.role == "assistant" and DEMO_REPLY in m.content
                for m in client.list_chat_messages(chat.id)
            ),
        ),
    )
    lore.preview_messages.setPlainText("tell me about the ember")
    lore.preview_chat_button.click()
    check(
        "chat_preview_shows_lore_fired",
        wait_until(
            app,
            lambda: "Included" in lore.preview_results.toPlainText()
            and "matched ember" in lore.preview_results.toPlainText(),
        ),
        lore.preview_results.toPlainText()[:200],
    )
    lore.preview_book_button.click()
    check(
        "book_preview_agrees",
        wait_until(
            app,
            lambda: "Ember fact: Included"
            in lore.preview_results.toPlainText(),
        ),
        lore.preview_results.toPlainText()[:200],
    )
    lore.close()
    app.processEvents()

    # ---- Restart: everything persists.
    window.close()
    app.processEvents()
    stopped = wait_until(
        app, lambda: engine.status().state is EngineState.STOPPED, timeout=30.0
    )
    check("engine_stopped_for_restart", stopped, engine.status().label)

    engine2 = EngineHandle()
    window2 = create_window(engine2)
    window2.show()
    app.processEvents()
    window2.start_engine_blocking()
    app.processEvents()
    check(
        "engine_running_after_restart",
        engine2.status().state is EngineState.RUNNING,
        engine2.status().label,
    )
    client2 = window2.client()
    check(
        "user_name_persists",
        client2.get_user_name().get("user_name") == "Volmarr"
        and client2.get_user_name().get("is_set") is True,
        str(client2.get_user_name()),
    )
    books2 = client2.list_lorebook_views()
    check(
        "book_persists",
        len(books2) == 1 and books2[0].name == "Gate World",
        str([b.name for b in books2]),
    )
    entries2 = client2.list_lore_entries(books2[0].id) if books2 else []
    check(
        "entry_persists",
        len(entries2) == 1 and entries2[0].raw.get("keys") == ["ember"],
    )
    scopes2 = client2.list_book_scopes(books2[0].id) if books2 else []
    check(
        "scope_persists",
        len(scopes2) == 1 and scopes2[0].scope_kind == "character"
        and scopes2[0].owner_id == keeper.id,
        str([(s.scope_kind, s.owner_id) for s in scopes2]),
    )
    check(
        "persona_persists",
        client2.get_chat_persona(chat.id).character_id == keeper.id,
    )

    window2.close()
    app.processEvents()
    stopped2 = wait_until(
        app, lambda: engine2.status().state is EngineState.STOPPED,
        timeout=30.0,
    )
    check("engine_stopped_on_quit", stopped2, engine2.status().label)
    gone = True
    try:
        import urllib.request

        urllib.request.urlopen(engine2.base_url + "/healthz", timeout=2)
        gone = False
    except Exception:
        gone = True
    check("healthz_gone_after_quit", gone)

    RESULT["pass"] = all(c["ok"] for c in RESULT["checks"].values())
    print("R10_RESULT " + json.dumps(RESULT))
    return 0 if RESULT["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
