"""Desktop proof (R-07): Chat Stage II in the real windowed app.

Launches the REAL windowed app on a fresh throwaway data dir,
seeds a Demo profile + character through the real API, opens a
greeted chat through the character picker, sends one composed
turn, and then drives EACH R-07 action once through the window's
own controls, verifying the resulting state via the API after
each:

- Edit the user line through the Edit dialog.
- Swipe deck: add an alternate (client road — the deck's source),
  walk it with Swipe ▶, then the Swipes dialog selects the first
  alternate back and deletes the second.
- Pin the reply with the Pin button (button flips to Unpin; the
  pinned-messages API lists it), then unpin.
- Author's Note through its editor dialog (API read-back).
- Continue button (the reply grows or a new reply lands).
- Impersonate dialog: accept the draft — a user line lands.
- Regenerate button after a fresh turn: a NEW reply message
  replaces the old one, history shape unchanged.
- Branch through its dialog from the first message: the window
  lands in the new chat; the source chat is untouched.
- Search dialog: the seeded word is found and listed.
- Checkpoints: create one from the dialog road, delete a message
  through its confirmation box, Undo restores it, restore the
  checkpoint as a new chat, delete the checkpoint.
- Clean quit stops the engine.

Usage (with the ``desktop`` extra installed)::

    RUNMAL_DATA_DIR=<fresh scratch> QT_QPA_PLATFORM=offscreen \
        python scripts/desktop_r07_proof.py

Prints one line:  R07_RESULT {json}
Exit code 0 only on a full pass.
"""

import json
import os
import sys
import time
import urllib.request

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULT = {"slice": "R-07", "platform": sys.platform,
          "python": sys.version.split()[0], "checks": {}}

GREETING = "Well met, traveller. The pass is open."
USER_LINE = "I seek passage."
EDITED_LINE = "I seek the high pass."
ALT_GREETING = "Well met. State your name, traveller."
NOTE_TEXT = "The keeper answers tersely."


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


def select_row(window, index: int) -> None:
    window.message_list.setCurrentRow(index)
    window._update_message_chrome()


def main() -> int:
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication

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

    # ---- Seed + open a greeted chat + one composed turn.
    profile = client.create_backend_profile(
        "Demo mode", "fake", chat_model="fake-1"
    )
    character = client.create_character(
        {
            "name": "Gate Keeper",
            "description": "Guards the high pass.",
            "personality": "Calm, dry, kind.",
            "first_mes": GREETING,
        },
        name="Gate Keeper",
    )
    check("seeded_via_real_api", bool(profile.id and character.id),
          f"profile={profile.id} character={character.id}")
    window.refresh_blocking()
    app.processEvents()

    dialog = window.open_new_chat_dialog()
    dialog.select_character(character.id)
    dialog.accept()
    created = wait_until(app, lambda: window.current_chat_id is not None)
    chat_id = window.current_chat_id or ""
    check("chat_created_via_picker", created and bool(chat_id), chat_id)
    client.set_chat_backend_profile(chat_id, profile.id)
    window.open_chat_blocking(chat_id)
    app.processEvents()

    window.composer_edit.setPlainText(USER_LINE)
    window.send_button.click()
    sent = wait_until(
        app,
        lambda: not window._streaming
        and "Rúnmál hears you." in window.message_view.toPlainText(),
        timeout=30.0,
    )
    check("composed_turn_landed", sent,
          window.message_view.toPlainText()[:120])
    history = client.list_chat_messages(chat_id)
    check(
        "history_shape",
        [m.role for m in history] == ["assistant", "user", "assistant"],
        f"roles={[m.role for m in history]}",
    )
    greeting_msg, user_msg, reply_msg = history

    # ---- Edit the user line through the Edit dialog.
    select_row(window, 1)
    edit_dialog = window.open_edit_message_dialog()
    check("edit_dialog_shown", edit_dialog is not None and edit_dialog.isVisible())
    if edit_dialog is not None:
        edit_dialog.text_edit.setPlainText(EDITED_LINE)
        edit_dialog.accept()
    edited = wait_until(
        app,
        lambda: client.list_chat_messages(chat_id)[1].content == EDITED_LINE,
    )
    check("edit_landed_via_api", edited,
          client.list_chat_messages(chat_id)[1].content)

    # ---- Swipe deck: adding an alternate makes it active (the
    # engine's P-065 semantics); walk back with Swipe ◀, then the
    # dialog selects the alternate and deletes it.
    client.add_swipe(chat_id, greeting_msg.id, ALT_GREETING)
    window.open_chat_blocking(chat_id)
    app.processEvents()
    added = client.list_chat_messages(chat_id)[0]
    check("swipe_added_and_active",
          added.swipe_count == 2 and added.content == ALT_GREETING,
          f"count={added.swipe_count} active={added.content!r}")
    select_row(window, 0)
    check("swipe_prev_enabled", window.swipe_prev_button.isEnabled())
    window.swipe_prev_button.click()
    walked = wait_until(
        app,
        lambda: client.list_chat_messages(chat_id)[0].content == GREETING,
    )
    check("swipe_prev_landed", walked,
          client.list_chat_messages(chat_id)[0].content)
    swipe_dialog = window.open_swipe_dialog()
    check("swipe_dialog_shown",
          swipe_dialog is not None and swipe_dialog.isVisible())
    if swipe_dialog is not None:
        check("swipe_dialog_lists_deck", swipe_dialog.swipe_list.count() == 2,
              f"count={swipe_dialog.swipe_list.count()}")
        swipe_dialog.swipe_list.setCurrentRow(1)
        swipe_dialog.select_button.click()
        selected = wait_until(
            app,
            lambda: client.list_chat_messages(chat_id)[0].content
            == ALT_GREETING,
        )
        check("swipe_select_landed", selected)
        swipe_dialog.swipe_list.setCurrentRow(1)
        swipe_dialog.delete_button.click()
        deleted_swipe = wait_until(
            app, lambda: swipe_dialog.swipe_list.count() == 1
        )
        check("swipe_delete_landed", deleted_swipe,
              f"deck now {client.list_chat_messages(chat_id)[0].swipe_count}")
        swipe_dialog.close()
        app.processEvents()
    window.open_chat_blocking(chat_id)
    app.processEvents()

    # ---- Pin the reply, then unpin (button words flip).
    select_row(window, 2)
    window.pin_button.click()
    pinned = wait_until(
        app,
        lambda: window.pin_button.text() == "Unpin"
        and [m.id for m in client.list_pinned_messages(chat_id)] == [reply_msg.id],
    )
    check("pin_landed_via_api", pinned,
          f"pinned={[m.id for m in client.list_pinned_messages(chat_id)]}")
    check("pin_words_in_transcript",
          "pinned" in window.message_view.toPlainText())
    window.pin_button.click()
    unpinned = wait_until(
        app,
        lambda: window.pin_button.text() == "Pin"
        and client.list_pinned_messages(chat_id) == [],
    )
    check("unpin_landed_via_api", unpinned)

    # ---- Author's Note through its editor dialog.
    window.open_authors_note_dialog()
    got_dialog = wait_until(app, lambda: window._note_dialog is not None)
    check("authors_note_dialog_shown", got_dialog)
    if window._note_dialog is not None:
        window._note_dialog.text_edit.setPlainText(NOTE_TEXT)
        window._note_dialog.depth_spin.setValue(2)
        window._note_dialog.accept()
    noted = wait_until(
        app, lambda: client.get_authors_note(chat_id).text == NOTE_TEXT
    )
    note = client.get_authors_note(chat_id)
    check("authors_note_saved_via_api", noted and note.depth == 2,
          f"text={note.text!r} depth={note.depth}")

    # ---- Continue: the conversation grows.
    before = client.list_chat_messages(chat_id)
    window.continue_button.click()
    continued = wait_until(
        app,
        lambda: (
            lambda after: len(after) > len(before)
            or after[-1].content != before[-1].content
        )(client.list_chat_messages(chat_id)),
        timeout=30.0,
    )
    check("continue_landed_via_api", continued,
          window.chat_stage_status.text())

    # ---- Impersonate: draft dialog, accept lands a user line.
    count_before = len(client.list_chat_messages(chat_id))
    window.open_impersonate()
    got_imp = wait_until(app, lambda: window._impersonate_dialog is not None,
                         timeout=30.0)
    check("impersonate_dialog_shown", got_imp)
    draft_text = ""
    if window._impersonate_dialog is not None:
        draft_text = window._impersonate_dialog.text()
        window._impersonate_dialog.accept_button.click()
    accepted = wait_until(
        app,
        lambda: len(client.list_chat_messages(chat_id)) == count_before + 1
        and client.list_chat_messages(chat_id)[-1].role == "user",
        timeout=30.0,
    )
    check("impersonate_accept_landed", accepted and bool(draft_text),
          f"draft={draft_text!r}")

    # ---- A fresh turn, then Regenerate replaces its reply.
    window.composer_edit.setPlainText("Open the gate.")
    window.send_button.click()
    sent2 = wait_until(app, lambda: not window._streaming, timeout=30.0)
    check("second_turn_landed", sent2)
    before_regen = client.list_chat_messages(chat_id)
    old_reply_id = before_regen[-1].id
    window.regenerate_button.click()
    regen = wait_until(
        app,
        lambda: not window._streaming
        and client.list_chat_messages(chat_id)[-1].id != old_reply_id,
        timeout=30.0,
    )
    after_regen = client.list_chat_messages(chat_id)
    check(
        "regenerate_landed_via_api",
        regen and len(after_regen) == len(before_regen)
        and after_regen[-1].content == "Rúnmál hears you.",
        f"old={old_reply_id} new={after_regen[-1].id}",
    )

    # ---- Branch from the first message; source untouched.
    source_len = len(client.list_chat_messages(chat_id))
    window.open_chat_blocking(chat_id)
    app.processEvents()
    select_row(window, 0)
    branch_dialog = window.open_branch_dialog()
    check("branch_dialog_shown",
          branch_dialog is not None and branch_dialog.isVisible())
    if branch_dialog is not None:
        branch_dialog.title_edit.setText("The other road")
        branch_dialog.accept()
    branched = wait_until(
        app, lambda: window.current_chat_id not in (None, chat_id)
    )
    branch_id = window.current_chat_id or ""
    check(
        "branch_landed_via_api",
        branched and len(client.list_chat_messages(branch_id)) == 1
        and len(client.list_chat_messages(chat_id)) == source_len,
        f"branch={branch_id} msgs="
        f"{len(client.list_chat_messages(branch_id)) if branch_id else -1}",
    )
    window.open_chat_blocking(chat_id)
    app.processEvents()

    # ---- Search dialog finds the edited line.
    search_dialog = window.open_search_dialog()
    search_dialog.query_edit.setText("high pass")
    search_dialog.run_search()
    found = wait_until(
        app, lambda: search_dialog.results_list.count() >= 1
    )
    check("search_found_via_dialog", found,
          search_dialog.results_label.text())
    search_dialog.close()
    app.processEvents()

    # ---- Checkpoints & undo: create, delete via confirm box,
    # undo restores, restore-as-new-chat, delete checkpoint.
    checkpoints_dialog = window.open_checkpoints_dialog()
    check("checkpoints_dialog_shown",
          checkpoints_dialog is not None and checkpoints_dialog.isVisible())
    if checkpoints_dialog is not None:
        checkpoints_dialog.close()
        app.processEvents()
    checkpoint = window.create_checkpoint_blocking("Before deletion")
    total_now = len(client.list_chat_messages(chat_id))
    check("checkpoint_created_via_api",
          checkpoint.message_count == total_now,
          f"count={checkpoint.message_count} total={total_now}")
    select_row(window, 0)
    box = window.confirm_delete_selected_message()
    check("delete_message_box_shown", box is not None and box.isVisible())
    if box is not None:
        delete_button = next(
            b for b in box.buttons() if b.text() == "Delete"
        )
        box.buttonClicked.emit(delete_button)
    deleted_msg = wait_until(
        app,
        lambda: len(client.list_chat_messages(chat_id)) == total_now - 1,
    )
    check("message_delete_landed", deleted_msg)
    journal = window.flow().undo_journal(chat_id)
    check("delete_journaled", bool(journal),
          journal[0].label if journal else "empty journal")
    window.undo_blocking()
    restored_history = client.list_chat_messages(chat_id)
    check("undo_restored_message",
          len(restored_history) == total_now
          and restored_history[0].content == GREETING,
          f"count={len(restored_history)}")
    restored_chat = window.restore_checkpoint_blocking(checkpoint.id)
    check(
        "checkpoint_restored_as_new_chat",
        restored_chat.id != chat_id
        and len(client.list_chat_messages(restored_chat.id)) == total_now,
        f"restored={restored_chat.id}",
    )
    window.open_chat_blocking(chat_id)
    app.processEvents()
    deleted_cp = window.delete_checkpoint_blocking(checkpoint.id)
    check("checkpoint_deleted_via_api",
          deleted_cp and client.list_checkpoints(chat_id) == [])

    # ---- Clean quit stops the engine.
    window.close()
    app.processEvents()
    deadline = time.time() + 10
    stopped_engine = False
    while time.time() < deadline:
        if engine.status().state is EngineState.STOPPED:
            stopped_engine = True
            break
        time.sleep(0.2)
    check("engine_stopped_on_quit", stopped_engine, engine.status().label)
    try:
        urllib.request.urlopen(f"{engine.base_url}/healthz", timeout=2)
        health_after = True
    except Exception:
        health_after = False
    check("healthz_gone_after_quit", not health_after)

    app.quit()
    passed = all(c["ok"] for c in RESULT["checks"].values())
    RESULT["pass"] = passed
    print("R07_RESULT " + json.dumps(RESULT, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
