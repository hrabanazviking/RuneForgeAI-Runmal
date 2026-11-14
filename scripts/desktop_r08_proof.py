"""Desktop proof (R-08): Characters in the real windowed app.

Launches the REAL windowed app on a fresh throwaway data dir
and drives the R-08 surfaces through the window's own controls,
verifying state via the API after each:

- Create a character FROM SCRATCH in the editor dialog (fields,
  tags, an alternate greeting added through the greetings editor).
- Library: tag census loads, search narrows the roster, the
  favourite toggle + favourites-only filter work.
- Chat with the new character through the character picker; a
  composed turn lands.
- Edit the character in the dialog (description changes), upload
  an avatar and an asset through the flow the dialog's buttons
  run, bind + unbind a lorebook through the dialog's Book tab.
- Versions: a same-name create lands as v2; restoring v1 onto it
  (the dialog's restore road) puts the v1 card back.
- Duplicate through the dock button's road, delete it through
  the confirmation box, Undo Delete restores it.
- Export to a JSON file; import a second character from a file.
- RESTART the whole app on the same data dir: the character, its
  edited card, its tags and the chat history all persist.
- Clean quit stops the engine.

Usage (with the ``desktop`` extra installed)::

    RUNMAL_DATA_DIR=<fresh scratch> QT_QPA_PLATFORM=offscreen \
        python scripts/desktop_r08_proof.py

Prints one line:  R08_RESULT {json}
Exit code 0 only on a full pass.
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULT = {"slice": "R-08", "platform": sys.platform,
          "python": sys.version.split()[0], "checks": {}}

GREETING = "Well met, traveller. The pass is open."
ALT_GREETING = "Well met. State your name, traveller."
EDITED_DESCRIPTION = "Now guards the LOW pass."
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d4944415478da6364f8cf500f00038601805a347d6b"
    "0000000049454e44ae426082"
)


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
    from PySide6.QtCore import Qt, qVersion
    from PySide6.QtWidgets import QApplication

    RESULT["pyside6"] = pyside_version
    RESULT["qt"] = qVersion()
    RESULT["qpa"] = os.environ.get("QT_QPA_PLATFORM", "")

    app = QApplication(sys.argv)
    data_dir = Path(os.environ["RUNMAL_DATA_DIR"])

    import httpx

    from runmal.desktop.app import create_window
    from runmal.desktop.client import DesktopSession
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
    flow = window.character_flow()
    profile = client.create_backend_profile(
        "Demo mode", "fake", chat_model="fake-1"
    )
    check("demo_profile_seeded", bool(profile.id), profile.id)

    # ---- Create a character FROM SCRATCH in the editor dialog.
    dialog = window.open_new_character_editor()
    check("create_dialog_shown", dialog is not None and dialog.isVisible())
    dialog.name_edit.setText("Gate Keeper")
    dialog.description_edit.setPlainText("Guards the high pass.")
    dialog.personality_edit.setPlainText("Calm, dry, kind.")
    dialog.system_prompt_edit.setPlainText("You guard the high pass.")
    dialog.first_mes_edit.setPlainText(GREETING)
    dialog.creator_edit.setText("Proof")
    dialog.version_edit.setText("1.0")
    dialog.tags_edit.setText("guard, pass")
    dialog.greeting_edit.setPlainText(ALT_GREETING)
    dialog.add_greeting_button.click()
    app.processEvents()
    check("greeting_added_in_dialog", dialog.greetings_list.count() == 1,
          f"count={dialog.greetings_list.count()}")
    created = window.save_editor_blocking(dialog)
    dialog.close()
    app.processEvents()
    character_id = created.id
    card = client.get_character_card(character_id)
    check(
        "character_created_via_dialog",
        card.name == "Gate Keeper"
        and card.description == "Guards the high pass."
        and card.alternate_greetings == [ALT_GREETING],
        f"id={character_id}",
    )
    check(
        "create_tags_via_organisation",
        flow.organisation(character_id).tags == ["guard", "pass"],
        str(flow.organisation(character_id).tags),
    )
    window.refresh_blocking()
    app.processEvents()
    check("roster_lists_new_character", window.characters_list.count() == 1,
          f"count={window.characters_list.count()}")

    # ---- Library: tag census, search, favourite filter.
    tags = window.refresh_library_tags_blocking()
    check("library_tag_census", {t.tag for t in tags} == {"guard", "pass"},
          str([t.tag for t in tags]))
    window.character_search_edit.setText("keeper")
    total, items = window.refresh_library_blocking()
    check("library_search_narrows", total == 1 and items[0].id == character_id,
          f"total={total}")
    check("favourite_toggles", window.toggle_favourite_blocking(character_id) is True)
    window.favourites_only_check.setChecked(True)
    total, _items = window.refresh_library_blocking()
    check("favourites_only_filter", total == 1, f"total={total}")
    window.favourites_only_check.setChecked(False)
    window.character_search_edit.setText("")
    window.refresh_library_blocking()
    app.processEvents()

    # ---- Chat with the new character (picker + composed turn).
    chat_dialog = window.open_new_chat_dialog()
    chat_dialog.select_character(character_id)
    chat_dialog.accept()
    opened = wait_until(app, lambda: window.current_chat_id is not None)
    chat_id = window.current_chat_id or ""
    check("chat_created_via_picker", opened and bool(chat_id), chat_id)
    check("greeting_in_stage", GREETING in window.message_view.toPlainText())
    client.set_chat_backend_profile(chat_id, profile.id)
    window.open_chat_blocking(chat_id)
    app.processEvents()
    window.composer_edit.setPlainText("I seek passage.")
    window.send_button.click()
    sent = wait_until(
        app,
        lambda: not window._streaming
        and "Rúnmál hears you." in window.message_view.toPlainText(),
        timeout=30.0,
    )
    check("composed_turn_landed", sent,
          window.message_view.toPlainText()[:120])

    # ---- Edit in the dialog; avatar + asset through its roads.
    editor = window.open_character_editor_blocking(character_id)
    check("editor_dialog_shows_card",
          editor.name_edit.text() == "Gate Keeper"
          and editor.description_edit.toPlainText() == "Guards the high pass.")
    editor.description_edit.setPlainText(EDITED_DESCRIPTION)
    saved = window.save_editor_blocking(editor)
    check("edit_saved_via_dialog", saved.description == EDITED_DESCRIPTION,
          saved.description)
    avatar_path = data_dir / "r08-avatar.png"
    avatar_path.write_bytes(PNG_BYTES)
    stored = flow.set_avatar(character_id, avatar_path.name, PNG_BYTES)
    avatar = flow.avatar_bytes(character_id)
    check("avatar_round_trip",
          stored == "r08-avatar.png" and avatar is not None
          and avatar[0] == PNG_BYTES,
          f"stored={stored}")
    editor.set_avatar(avatar[0], avatar[1])
    check("avatar_preview_label", "Avatar: set" in editor.avatar_label.text(),
          editor.avatar_label.text())
    asset = flow.add_asset(character_id, "pass-map.png", PNG_BYTES)
    editor.refresh_assets(flow.assets(character_id))
    check("asset_uploaded_and_listed",
          asset.status == "stored" and editor.assets_list.count() >= 1,
          f"assets={editor.assets_list.count()}")

    # ---- Book tab: bind + unbind a world lorebook.
    session = DesktopSession.from_local_credential(engine.base_url)
    with httpx.Client(base_url=engine.base_url, trust_env=False) as http:
        session.apply(http)
        made = http.post(
            "/api/v1/lorebooks",
            json={"name": "World Facts", "description": "Things."},
        )
        book_id = made.json()["id"] if made.status_code == 201 else ""
    check("world_lorebook_made", bool(book_id), book_id)
    # The editor bundle predates the book; reopen so the picker has it.
    editor.close()
    app.processEvents()
    editor = window.open_character_editor_blocking(character_id)
    for index in range(editor.lorebook_combo.count()):
        if editor.lorebook_combo.itemData(index) == book_id:
            editor.lorebook_combo.setCurrentIndex(index)
            break
    editor.precedence_edit.setText("world_first")
    window._editor_bind(editor)
    bound = wait_until(
        app, lambda: client.get_lorebook_binding(character_id).bound
    )
    check("binding_landed_via_dialog", bound,
          client.get_lorebook_binding(character_id).label)
    window._editor_unbind(editor)
    unbound = wait_until(
        app, lambda: not client.get_lorebook_binding(character_id).bound
    )
    check("unbind_landed_via_dialog", unbound)
    editor.close()
    app.processEvents()

    # ---- Versions: same-name create is v2; restore v1 onto it.
    second = client.create_character(
        {
            "name": "Gate Keeper",
            "description": "Second telling.",
            "first_mes": GREETING,
        },
        name="Gate Keeper",
    )
    check("same_name_create_is_v2", second.version_no == 2,
          f"v={second.version_no}")
    history = flow.versions(character_id)
    check("version_history_lists_both",
          [v.version_no for v in history.versions] == [1, 2],
          str([v.version_no for v in history.versions]))
    restored = flow.restore_version(second.id, 1)
    check("version_restore_landed",
          restored.description == EDITED_DESCRIPTION,
          restored.description)
    flow.delete(second.id)  # keep the roster to the one keeper

    # ---- Duplicate, delete through the box, undo delete.
    clone = window.duplicate_character_blocking(character_id)
    check("duplicate_landed", clone.name == "Gate Keeper (copy)", clone.name)
    window.refresh_blocking()
    app.processEvents()
    for index in range(window.characters_list.count()):
        item = window.characters_list.item(index)
        if item.data(Qt.ItemDataRole.UserRole) == clone.id:
            window.characters_list.setCurrentItem(item)
            break
    box = window.confirm_delete_selected_character()
    check("delete_character_box_shown", box is not None and box.isVisible())
    if box is not None:
        delete_button = next(b for b in box.buttons() if b.text() == "Delete")
        box.buttonClicked.emit(delete_button)
    deleted = wait_until(
        app, lambda: all(c.id != clone.id for c in client.list_characters())
    )
    check("soft_delete_landed", deleted)
    check("undo_armed", wait_until(
        app, lambda: window.undo_delete_character_button.isEnabled()))
    restored_clone = window.undo_delete_character_blocking()
    check("undo_delete_restored", restored_clone.id == clone.id)
    flow.delete(clone.id)  # tidy: the clone's work here is done

    # ---- Export + import through the window's roads.
    export_path = data_dir / "gate-keeper-export.json"
    window.export_character_to_path(character_id, str(export_path))
    document = json.loads(export_path.read_text(encoding="utf-8"))
    data_level = document.get("data", document)
    check("export_file_is_the_card",
          data_level.get("name") == "Gate Keeper"
          and data_level.get("description") == EDITED_DESCRIPTION)
    ferry_path = data_dir / "ferryman.json"
    ferry_path.write_text(json.dumps({
        "spec": "chara_card_v2", "spec_version": "2.0",
        "data": {"name": "Ferryman", "description": "Rows the river.",
                 "first_mes": "Coin first."},
    }), encoding="utf-8")
    outcome = window.import_characters_blocking([str(ferry_path)])
    check("bulk_import_landed",
          bool(outcome.created_ids)
          and any(c.name == "Ferryman" for c in client.list_characters()),
          outcome.status_words)

    # ---- RESTART the app on the same data dir: persistence.
    window.close()
    app.processEvents()
    deadline = time.time() + 10
    stopped = False
    while time.time() < deadline:
        if engine.status().state is EngineState.STOPPED:
            stopped = True
            break
        time.sleep(0.2)
    check("engine_stopped_before_restart", stopped, engine.status().label)

    engine2 = EngineHandle()
    window2 = create_window(engine2)
    window2.show()
    app.processEvents()
    snapshot2 = window2.start_engine_blocking()
    app.processEvents()
    if window2._wizard is not None:
        window2._wizard.close()
        app.processEvents()
        window2._wizard = None
    client2 = window2.client()
    check("not_first_run_after_restart",
          snapshot2 is not None and snapshot2.first_run.is_first_run is False)
    card2 = client2.get_character_card(character_id)
    check("character_persists_after_restart",
          card2.description == EDITED_DESCRIPTION
          and card2.alternate_greetings == [ALT_GREETING],
          card2.description)
    check("tags_persist_after_restart",
          window2.character_flow().organisation(character_id).tags
          == ["guard", "pass"])
    check("avatar_persists_after_restart",
          client2.get_character(character_id).has_avatar is True)
    window2.open_chat_blocking(chat_id)
    app.processEvents()
    history2 = client2.list_chat_messages(chat_id)
    check("chat_history_persists_after_restart",
          [m.role for m in history2] == ["assistant", "user", "assistant"]
          and GREETING in window2.message_view.toPlainText(),
          f"roles={[m.role for m in history2]}")

    # ---- Clean quit stops the engine.
    window2.close()
    app.processEvents()
    deadline = time.time() + 10
    stopped2 = False
    while time.time() < deadline:
        if engine2.status().state is EngineState.STOPPED:
            stopped2 = True
            break
        time.sleep(0.2)
    check("engine_stopped_on_quit", stopped2, engine2.status().label)
    try:
        urllib.request.urlopen(f"{engine2.base_url}/healthz", timeout=2)
        health_after = True
    except Exception:
        health_after = False
    check("healthz_gone_after_quit", not health_after)

    app.quit()
    passed = all(c["ok"] for c in RESULT["checks"].values())
    RESULT["pass"] = passed
    print("R08_RESULT " + json.dumps(RESULT, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
