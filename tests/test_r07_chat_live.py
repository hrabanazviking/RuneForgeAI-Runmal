"""R-07 acceptance (live engine): Chat Stage II actions against
the real in-process engine on a fresh data dir — edit/delete,
swipes, pin, branch, Author's Note, regenerate, continue,
impersonate, search, checkpoints and undo, all through the
client roads the window uses, with state verified through the
same API afterwards.

No Qt here (the stage widgets are driven by
``scripts/desktop_r07_proof.py`` and ``test_r07_desktop_window.py``).
"""

import pytest

from runmal.desktop.chat_logic import ChatFlow
from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.engine import EngineHandle, EngineState

GREETING = "Well met, traveller. The pass is open."


@pytest.fixture()
def live_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    handle = EngineHandle()
    assert handle.start(timeout=30.0).state is EngineState.RUNNING
    yield handle
    handle.stop()


def make_client(handle) -> RunmalClient:
    return RunmalClient(DesktopSession.from_local_credential(handle.base_url))


def seed_demo_chat(client: RunmalClient):
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
    flow = ChatFlow(client)
    opened = flow.create_chat(
        character_id=character.id, title="First chat with Gate Keeper"
    )
    client.set_chat_backend_profile(opened.chat.id, profile.id)
    result = flow.send_turn(opened.chat.id, "I seek passage.")
    assert result.landed is True
    return flow, opened.chat.id


def test_stage_ii_actions_on_real_engine(live_engine) -> None:
    client = make_client(live_engine)
    try:
        flow, chat_id = seed_demo_chat(client)
        history = client.list_chat_messages(chat_id)
        assert [m.role for m in history] == ["assistant", "user", "assistant"]
        greeting, user_line, reply = history

        # Edit + swipe deck on the greeting.
        edited = flow.edit_message(chat_id, user_line.id, "I seek the high pass.")
        assert edited.content == "I seek the high pass."
        decked = flow.add_swipe(chat_id, greeting.id, "Well met. State your name.")
        assert decked.swipe_count >= 2
        # P-065: the new alternate becomes the active one.
        assert decked.content == "Well met. State your name."
        shown = flow.swipe_prev(chat_id, greeting.id)
        assert shown.content == GREETING
        shown = flow.swipe_next(chat_id, greeting.id)
        assert shown.content == "Well met. State your name."
        shown = flow.select_swipe(chat_id, greeting.id, 0)
        assert shown.content == GREETING
        trimmed = flow.delete_swipe(chat_id, greeting.id, 1)
        assert trimmed.swipe_count == 1

        # Pin the reply; the pinned list is the proof.
        assert flow.set_pinned(chat_id, reply, True) is True
        assert [m.id for m in flow.pinned_messages(chat_id)] == [reply.id]

        # Author's Note round trip.
        note = flow.save_authors_note(
            chat_id, text="The keeper answers tersely.", depth=2,
            frequency=1, enabled=True, role="system",
        )
        assert note.text == "The keeper answers tersely."
        assert flow.authors_note(chat_id).depth == 2

        # Branch at the user line: new chat, source untouched.
        branch = flow.branch_from(
            chat_id, message_id=user_line.id, name="The other road"
        )
        assert branch.id != chat_id
        assert len(client.list_chat_messages(branch.id)) == 2
        assert len(client.list_chat_messages(chat_id)) == 3

        # Search finds the edited line, scoped and global.
        outcome = flow.search("high pass")
        assert outcome.total >= 1
        assert any(h.chat_id == chat_id for h in outcome.hits)

        # Continue lands (extend or next — the engine decides);
        # history grows or the last reply grows, never shrinks.
        before = client.list_chat_messages(chat_id)
        outcome = flow.continue_turn(chat_id)
        after = client.list_chat_messages(chat_id)
        assert outcome.content
        assert len(after) >= len(before)
        assert after[-1].content != before[-1].content or len(after) > len(before)

        # Impersonate: draft stores nothing; accept lands a user
        # line; a second draft discarded stores nothing either.
        count = len(client.list_chat_messages(chat_id))
        draft = flow.impersonate(chat_id)
        assert draft.content
        assert len(client.list_chat_messages(chat_id)) == count
        landed = flow.accept_impersonate(chat_id, draft, draft.content)
        assert landed.role == "user"
        assert len(client.list_chat_messages(chat_id)) == count + 1
        draft2 = flow.impersonate(chat_id)
        assert flow.discard_impersonate(chat_id, draft2) is True
        assert len(client.list_chat_messages(chat_id)) == count + 1

        # Checkpoint now; delete a message; restore as a NEW chat
        # holding the checkpoint-time history; undo the delete in
        # the original.
        checkpoint = flow.create_checkpoint(chat_id, name="Before deletion")
        assert checkpoint.message_count == count + 1
        victim = client.list_chat_messages(chat_id)[0]
        assert flow.delete_message(chat_id, victim.id) is True
        assert len(client.list_chat_messages(chat_id)) == count
        restored = flow.restore_checkpoint(chat_id, checkpoint.id)
        assert restored.id != chat_id
        assert len(client.list_chat_messages(restored.id)) == count + 1
        journal = flow.undo_journal(chat_id)
        assert journal, "the delete must be journaled"
        undone = flow.undo_last(chat_id)
        assert undone.get("undone")
        assert len(client.list_chat_messages(chat_id)) == count + 1
        assert flow.delete_checkpoint(chat_id, checkpoint.id) is True

        # Unpin for a clean end state.
        reply_now = next(
            m for m in client.list_chat_messages(chat_id) if m.id == reply.id
        )
        assert flow.set_pinned(chat_id, reply_now, False) is False
        assert flow.pinned_messages(chat_id) == []
    finally:
        client.close()


def test_regenerate_on_real_engine(live_engine) -> None:
    client = make_client(live_engine)
    try:
        flow, chat_id = seed_demo_chat(client)
        before = client.list_chat_messages(chat_id)
        old_reply_id = before[-1].id
        result = flow.regenerate(chat_id)
        assert result.landed is True, result.status_words
        after = client.list_chat_messages(chat_id)
        assert [m.role for m in after] == ["assistant", "user", "assistant"]
        assert after[-1].id != old_reply_id
        assert after[-1].content == "Rúnmál hears you."
        assert after[1].content == "I seek passage."
    finally:
        client.close()
