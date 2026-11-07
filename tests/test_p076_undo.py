"""P-076 Undo battery.

Pins the undo contract from hidden_files/P076_DESIGN.md: a
sealed per-chat journal (files, NO new migration -- head
stays 0039) captures the chat's whole restorable state
BEFORE each covered operation; undo pops the newest entry
and restores it in place, byte/state-exactly, consuming the
entry. Areas: A recording + no-op exclusions, B message ops
(append/edit/delete/move, pinned delete), C swipes,
D chat settings + branch rename, E pin/unpin + metadata,
F stack discipline, G isolation + honesty, H pins (head,
cap, seal, chat deletion), R REST flow.
"""

from __future__ import annotations

import hashlib
import json
import stat

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import branches, undo
from runmal.chats import metadata as meta_mod
from runmal.chats import service as svc
from runmal.chats.service import chat_to_dict, event_to_dict, message_to_dict
from runmal.chats.undo import UndoError
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import BackendProfile, Character, Memory, SamplingPreset, User

UNKNOWN_ID = "12345678-1234-4234-9234-1234567890ab"
META_KEYS = {"id", "chat_id", "seq", "operation", "detail", "created_at", "message_count"}


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    return tmp_path


# ---------------- service harness (copied from test_p068) ----------------


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


async def setup_chat(factory, user_id, contents, title="Hall"):
    async with factory() as session:
        chat = await svc.create_chat(session, user_id, title)
        ids = []
        for i, content in enumerate(contents):
            role = "user" if i % 2 == 0 else "assistant"
            msg = await svc.append_message(session, user_id, chat.id, role, content)
            ids.append(msg.id)
        return chat.id, ids


async def journal(factory, user_id, chat_id):
    async with factory() as session:
        entries = await undo.list_journal(session, user_id, chat_id)
        assert entries is not None
        return entries


async def journal_ops(factory, user_id, chat_id):
    return [e["operation"] for e in await journal(factory, user_id, chat_id)]


async def history_dicts(factory, user_id, chat_id):
    async with factory() as session:
        history = await svc.get_history(session, user_id, chat_id)
        assert history is not None
        return [message_to_dict(m) for m in history]


async def contents(factory, user_id, chat_id):
    return [m["content"] for m in await history_dicts(factory, user_id, chat_id)]


async def chat_dict(factory, user_id, chat_id):
    async with factory() as session:
        chat = await svc.get_chat(session, user_id, chat_id)
        assert chat is not None
        history = await svc.get_history(session, user_id, chat_id)
        return chat_to_dict(chat, len(history or []))


async def do_undo(factory, user_id, chat_id, entry_id=None):
    async with factory() as session:
        return await undo.undo_last(session, user_id, chat_id, entry_id)


# ---------------- A. recording + no-op exclusions ----------------


async def test_each_append_journals_one_entry(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ids = await setup_chat(factory, user, ["one", "two", "three"])
    entries = await journal(factory, user, chat_id)
    assert [e["operation"] for e in entries] == ["message.append"] * 3
    assert [e["seq"] for e in entries] == [3, 2, 1]  # top first
    assert [e["message_count"] for e in entries] == [2, 1, 0]
    assert all(set(e) == META_KEYS for e in entries)


async def test_noop_operations_do_not_journal(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["only"])
    before = len(await journal(factory, user, chat_id))
    async with factory() as session:
        await svc.edit_message(session, user, chat_id, mid, "only")  # identical
        await svc.move_message(session, user, chat_id, mid, 0)  # same index
        result = await svc.unpin_message_from_memory(session, user, chat_id, mid)
        assert result is False
        await svc.set_chat_persona(session, user, chat_id, None)  # already None
    assert len(await journal(factory, user, chat_id)) == before


async def test_failed_operations_do_not_journal(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["only"])
    before = len(await journal(factory, user, chat_id))
    async with factory() as session:
        with pytest.raises(ValueError):
            await svc.move_message(session, user, chat_id, mid, 5)
        with pytest.raises(ValueError):
            await svc.edit_message(session, user, chat_id, mid, "")
        with pytest.raises(ValueError):
            await svc.delete_swipe(session, user, chat_id, mid, 0)  # only swipe
    assert len(await journal(factory, user, chat_id)) == before
    assert await contents(factory, user, chat_id) == ["only"]


# ---------------- B. message operations undo ----------------


async def test_undo_append_restores_prior_state_exactly(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await setup_chat(factory, user, ["one", "two"])
    before = await history_dicts(factory, user, chat_id)
    async with factory() as session:
        await svc.append_message(session, user, chat_id, "user", "three")
    assert await contents(factory, user, chat_id) == ["one", "two", "three"]
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "message.append"
    assert result["restored_message_count"] == 2
    after = await history_dicts(factory, user, chat_id)
    assert after == before  # ids, timestamps, decks, positions: exact
    assert [m["id"] for m in after] == ids


async def test_undo_edit_restores_content_deck_and_variants(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["draft"])
    async with factory() as session:
        await svc.add_swipe(session, user, chat_id, mid, "alt")
        await svc.select_swipe(session, user, chat_id, mid, index=0)
        await svc.edit_message(session, user, chat_id, mid, "draft-v2")
    state = (await history_dicts(factory, user, chat_id))[0]
    assert state["content"] == "draft-v2"
    assert state["variant_count"] == 1
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "message.edit"
    state = (await history_dicts(factory, user, chat_id))[0]
    assert state["content"] == "draft"
    assert state["swipes"] == ["draft", "alt"]
    assert state["swipe_id"] == 0
    assert state["variant_history"] == []
    assert state["id"] == mid


async def test_undo_delete_restores_message_and_positions(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await setup_chat(factory, user, ["a", "b", "c"])
    async with factory() as session:
        await svc.move_message(session, user, chat_id, ids[2], 0)  # materialise
    before = await history_dicts(factory, user, chat_id)
    assert [m["content"] for m in before] == ["c", "a", "b"]
    async with factory() as session:
        await svc.delete_message(session, user, chat_id, ids[0])
    assert await contents(factory, user, chat_id) == ["c", "b"]
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "message.delete"
    after = await history_dicts(factory, user, chat_id)
    assert after == before  # the deleted message returns AS ITSELF
    assert [m["position"] for m in after] == [0, 1, 2]


async def test_undo_delete_of_pinned_restores_pin_memory(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["keep me"])
    async with factory() as session:
        memory = await svc.pin_message_to_memory(session, user, chat_id, mid)
        memory_id = memory.id
    async with factory() as session:
        await svc.delete_message(session, user, chat_id, mid)
        gone = await session.execute(select(Memory).where(Memory.id == memory_id))
        assert gone.scalar_one_or_none() is None
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "message.delete"
    state = (await history_dicts(factory, user, chat_id))[0]
    assert state["id"] == mid and state["pinned"] is True
    async with factory() as session:
        pinned = await svc.list_pinned_messages(session, user, chat_id)
        assert pinned is not None and [m.id for m in pinned] == [mid]
        row = await session.execute(select(Memory).where(Memory.id == memory_id))
        restored = row.scalar_one()
        assert restored.content == "keep me"  # SAME memory id, back exactly


async def test_undo_move_restores_order(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await setup_chat(factory, user, ["a", "b", "c"])
    async with factory() as session:
        await svc.move_message(session, user, chat_id, ids[0], 2)
    assert await contents(factory, user, chat_id) == ["b", "c", "a"]
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "message.move"
    after = await history_dicts(factory, user, chat_id)
    assert [m["content"] for m in after] == ["a", "b", "c"]
    assert [m["id"] for m in after] == ids
    # the pre-move chat was legacy (positions NULL) and returns so
    assert all(m["position"] is None for m in after)


# ---------------- C. swipes undo ----------------


async def test_undo_swipe_add_select_delete(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["base"])
    async with factory() as session:
        await svc.add_swipe(session, user, chat_id, mid, "alt-1")
    state = (await history_dicts(factory, user, chat_id))[0]
    assert state["swipes"] == ["base", "alt-1"] and state["swipe_id"] == 1
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "message.swipe_add"
    state = (await history_dicts(factory, user, chat_id))[0]
    assert state["swipes"] == ["base"] and state["content"] == "base"
    async with factory() as session:
        await svc.add_swipe(session, user, chat_id, mid, "alt-1")
        await svc.select_swipe(session, user, chat_id, mid, index=0)
        await svc.delete_swipe(session, user, chat_id, mid, 1)
    state = (await history_dicts(factory, user, chat_id))[0]
    assert state["swipes"] == ["base"]
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "message.swipe_delete"
    state = (await history_dicts(factory, user, chat_id))[0]
    assert state["swipes"] == ["base", "alt-1"] and state["swipe_id"] == 0
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "message.swipe_select"
    state = (await history_dicts(factory, user, chat_id))[0]
    assert state["swipe_id"] == 1 and state["content"] == "alt-1"


# ---------------- D. chat settings + branch rename undo ----------------


async def test_undo_rename_and_note_settings(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await setup_chat(factory, user, ["x"], title="Old Title")
    async with factory() as session:
        await svc.rename_chat(session, user, chat_id, "New Title")
        await svc.set_chat_authors_note(
            session, user, chat_id,
            {"text": "be kind", "depth": 2, "frequency": 1, "enabled": True, "role": "system"},
        )
        await svc.set_chat_post_history(
            session, user, chat_id, {"text": "wrap up", "enabled": True, "role": "user"}
        )
        await svc.set_chat_swipe_settings(
            session, user, chat_id, {"enabled": True, "params": {"temperature": 0.7}}
        )
    assert (await chat_dict(factory, user, chat_id))["title"] == "New Title"
    for expected_op in ("chat.swipe_settings", "chat.post_history", "chat.authors_note"):
        result = await do_undo(factory, user, chat_id)
        assert result["undone"] == expected_op
    state = await chat_dict(factory, user, chat_id)
    assert state["authors_note"]["text"] == ""
    assert state["post_history"]["text"] == ""
    assert state["swipe_settings"]["params"] == {}
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "chat.rename"
    assert (await chat_dict(factory, user, chat_id))["title"] == "Old Title"


async def test_undo_preset_persona_backend(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await setup_chat(factory, user, ["x"])
    async with factory() as session:
        preset = SamplingPreset(user_id=user, name="P", params_json="{}")
        profile = BackendProfile(user_id=user, name="B")
        character = Character(user_id=user, name="Saga", card_json="{}")
        session.add_all([preset, profile, character])
        await session.commit()
        preset_id, profile_id, character_id = preset.id, profile.id, character.id
    async with factory() as session:
        await svc.set_chat_preset(session, user, chat_id, preset_id)
        await svc.set_chat_backend_profile(session, user, chat_id, profile_id)
        await svc.set_chat_persona(session, user, chat_id, character_id)
    state = await chat_dict(factory, user, chat_id)
    assert state["preset_id"] == preset_id
    assert state["backend_profile_id"] == profile_id
    assert state["character_id"] == character_id
    for expected_op in ("chat.persona", "chat.backend_profile", "chat.preset"):
        result = await do_undo(factory, user, chat_id)
        assert result["undone"] == expected_op
    state = await chat_dict(factory, user, chat_id)
    assert state["preset_id"] is None
    assert state["backend_profile_id"] is None
    assert state["character_id"] is None


async def test_undo_branch_rename(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await setup_chat(factory, user, ["x"], title="Trunk")
    async with factory() as session:
        await branches.rename_branch(session, user, chat_id, "Named Branch")
    assert (await chat_dict(factory, user, chat_id))["title"] == "Named Branch"
    assert (await journal(factory, user, chat_id))[0]["operation"] == "branch.rename"
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "branch.rename"
    assert (await chat_dict(factory, user, chat_id))["title"] == "Trunk"


# ---------------- E. pin/unpin + metadata undo ----------------


async def test_undo_pin_and_unpin(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["pin me"])
    async with factory() as session:
        memory = await svc.pin_message_to_memory(session, user, chat_id, mid)
        memory_id = memory.id
        again = await svc.pin_message_to_memory(session, user, chat_id, mid)
        assert again.id == memory_id  # idempotent: no second journal entry
    assert (await journal_ops(factory, user, chat_id))[0] == "message.pin"
    assert (await journal_ops(factory, user, chat_id)).count("message.pin") == 1
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "message.pin"
    async with factory() as session:
        pinned = await svc.list_pinned_messages(session, user, chat_id)
        assert pinned == []
        row = await session.execute(select(Memory).where(Memory.id == memory_id))
        assert row.scalar_one_or_none() is None
    async with factory() as session:
        repinned = await svc.pin_message_to_memory(session, user, chat_id, mid)
        repin_id = repinned.id  # a fresh pin is a NEW memory; undoing the
        # first pin deleted the original for good (that IS the undo)
        assert repin_id != memory_id
        await svc.unpin_message_from_memory(session, user, chat_id, mid)
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "message.unpin"
    async with factory() as session:
        pinned = await svc.list_pinned_messages(session, user, chat_id)
        assert pinned is not None and [m.id for m in pinned] == [mid]
        row = await session.execute(select(Memory).where(Memory.id == repin_id))
        assert row.scalar_one() is not None  # the unpinned pin memory returns


async def test_undo_metadata_update_and_favourite(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await setup_chat(factory, user, ["alpha beta"], title="Orig")
    async with factory() as session:
        before = await meta_mod.get_metadata(session, user, chat_id)
        await meta_mod.update_metadata(
            session, user, chat_id,
            {"title": "Changed", "summary": "New summary", "tags": ["Quest", "Sea"]},
        )
        await meta_mod.set_favourite(session, user, chat_id, True)
        changed = await meta_mod.get_metadata(session, user, chat_id)
    assert changed["title"] == "Changed" and changed["is_favourite"] is True
    assert changed["tags"] == ["Quest", "Sea"]
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "chat.favourite"
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "chat.metadata"
    async with factory() as session:
        after = await meta_mod.get_metadata(session, user, chat_id)
    assert after == before  # title, summary, tags, provenance, favourite: exact


async def test_undo_metadata_regenerate(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await setup_chat(
        factory, user, ["the harbour bell rang over cold water"], title="Orig"
    )
    async with factory() as session:
        out = await meta_mod.regenerate_metadata(session, user, chat_id, fields=["title"])
        assert out["generated"] == ["title"]
    assert (await chat_dict(factory, user, chat_id))["title"] != "Orig"
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "chat.metadata_regenerate"
    assert (await chat_dict(factory, user, chat_id))["title"] == "Orig"


# ---------------- F. stack discipline ----------------


async def test_stack_walks_backwards_and_consumes(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await setup_chat(factory, user, ["seed"], title="T0")
    async with factory() as session:
        await svc.rename_chat(session, user, chat_id, "T1")
        await svc.append_message(session, user, chat_id, "user", "extra")
    # stack (top first): append, rename, append(seed)
    assert await journal_ops(factory, user, chat_id) == [
        "message.append", "chat.rename", "message.append",
    ]
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "message.append"
    assert await contents(factory, user, chat_id) == ["seed"]
    assert (await chat_dict(factory, user, chat_id))["title"] == "T1"
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "chat.rename"
    assert (await chat_dict(factory, user, chat_id))["title"] == "T0"
    assert len(await journal(factory, user, chat_id)) == 1  # only the seed append
    # the undo itself was NOT journaled (no redo): the next undo
    # goes further back, never forward
    result = await do_undo(factory, user, chat_id)
    assert result["undone"] == "message.append"
    assert await contents(factory, user, chat_id) == []
    assert await do_undo(factory, user, chat_id) is None  # empty stack


async def test_undo_records_event_and_journal_shrinks(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await setup_chat(factory, user, ["seed"])
    await do_undo(factory, user, chat_id)
    async with factory() as session:
        events = await svc.list_events(session, user, chat_id)
        dicts = [event_to_dict(e) for e in events or []]
    undo_events = [e for e in dicts if e["kind"] == "undo.performed"]
    assert len(undo_events) == 1
    assert undo_events[0]["data"]["operation"] == "message.append"
    assert await journal(factory, user, chat_id) == []


async def test_out_of_order_undo_refused(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await setup_chat(factory, user, ["one", "two"])
    entries = await journal(factory, user, chat_id)
    older, top = entries[1], entries[0]
    async with factory() as session:
        with pytest.raises(ValueError):
            await undo.undo_last(session, user, chat_id, older["id"])
    assert await contents(factory, user, chat_id) == ["one", "two"]  # unchanged
    assert len(await journal(factory, user, chat_id)) == 2  # nothing consumed
    result = await do_undo(factory, user, chat_id, top["id"])  # explicit top: fine
    assert result["entry_id"] == top["id"]
    assert await contents(factory, user, chat_id) == ["one"]


# ---------------- G. isolation + honesty ----------------


async def test_foreign_user_gets_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, "intruder")
    chat_id, _ = await setup_chat(factory, user, ["mine"])
    async with factory() as session:
        assert await undo.list_journal(session, other, chat_id) is None
        assert await undo.undo_last(session, other, chat_id) is None
        assert await undo.clear_journal(session, other, chat_id) is None
        entries = await undo.list_journal(session, user, chat_id)
        assert entries is not None
        assert await undo.get_entry(session, other, chat_id, entries[0]["id"]) is None
    assert len(await journal(factory, user, chat_id)) == 1  # untouched
    assert await contents(factory, user, chat_id) == ["mine"]


async def test_tampered_top_entry_blocks_undo_until_cleared(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await setup_chat(factory, user, ["precious"])
    entries = await journal(factory, user, chat_id)
    path = tmp_path / "undo" / user / chat_id / f"{entries[0]['id']}.json"
    doc = json.loads(path.read_text())
    doc["payload"]["chat"]["title"] = "FORGED"  # any payload change breaks the seal
    path.write_text(json.dumps(doc))
    async with factory() as session:
        with pytest.raises(UndoError):
            await undo.undo_last(session, user, chat_id)
        with pytest.raises(UndoError):
            await undo.get_entry(session, user, chat_id, entries[0]["id"])
    assert await contents(factory, user, chat_id) == ["precious"]  # nothing restored
    assert len(await journal(factory, user, chat_id)) == 1  # entry NOT consumed
    async with factory() as session:
        assert await undo.clear_journal(session, user, chat_id) == 1
    assert await do_undo(factory, user, chat_id) is None


async def test_foreign_entry_file_copied_in_is_refused(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await setup_chat(factory, user, ["first chat"])
    other_chat, _ = await setup_chat(factory, user, ["second chat"], title="Other")
    async with factory() as session:
        await undo.clear_journal(session, user, other_chat)  # only the foreign file remains
    entries = await journal(factory, user, chat_id)
    src = tmp_path / "undo" / user / chat_id / f"{entries[0]['id']}.json"
    dst_dir = tmp_path / "undo" / user / other_chat
    dst_dir.mkdir(parents=True, exist_ok=True)
    (dst_dir / src.name).write_bytes(src.read_bytes())
    async with factory() as session:
        with pytest.raises(UndoError):
            await undo.get_entry(session, user, other_chat, entries[0]["id"])
        with pytest.raises(UndoError):
            await undo.undo_last(session, user, other_chat)
    assert await contents(factory, user, other_chat) == ["second chat"]


async def test_malformed_entry_ids_refused(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await setup_chat(factory, user, ["x"])
    async with factory() as session:
        for bad in ("../x", "..", "a/b", "a\\b", ""):
            with pytest.raises(ValueError):
                await undo.get_entry(session, user, chat_id, bad)
        with pytest.raises(ValueError):
            await undo.undo_last(session, user, chat_id, "a/b")
        assert await undo.get_entry(session, user, chat_id, UNKNOWN_ID) is None


async def test_journal_metadata_never_carries_content(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await setup_chat(factory, user, ["a very secret sentence"])
    entries = await journal(factory, user, chat_id)
    assert "a very secret sentence" not in json.dumps(entries)
    assert all(set(e) == META_KEYS for e in entries)


# ---------------- H. pins: head, seal, cap, deletion ----------------


def test_migration_head_stays_0039(tmp_path):
    assert MIGRATIONS[-1][0] == "0039"
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0039"


async def test_entry_file_is_sealed_and_matches_state(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await setup_chat(factory, user, ["sealed one", "sealed two"])
    entries = await journal(factory, user, chat_id)
    path = tmp_path / "undo" / user / chat_id / f"{entries[0]['id']}.json"
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    doc = json.loads(path.read_text())
    assert doc["format"] == "runmal-undo-journal" and doc["format_version"] == 1
    canonical = json.dumps(doc["payload"], sort_keys=True, separators=(",", ":")).encode()
    assert doc["checksum"] == hashlib.sha256(canonical).hexdigest()
    # the top entry is the before-image of the second append:
    # exactly the first message, archive row shape
    assert [m["content"] for m in doc["payload"]["messages"]] == ["sealed one"]
    assert doc["payload"]["messages"][0]["id"] == ids[0]
    assert doc["payload"]["chat"]["id"] == chat_id


async def test_journal_cap_prunes_oldest(tmp_path, monkeypatch):
    monkeypatch.setattr(undo, "MAX_ENTRIES", 3)
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await setup_chat(factory, user, ["m1", "m2", "m3", "m4", "m5"])
    entries = await journal(factory, user, chat_id)
    assert [e["seq"] for e in entries] == [5, 4, 3]  # bounded, oldest pruned
    result = await do_undo(factory, user, chat_id)
    assert result["seq"] == 5  # the surviving top still undoes exactly
    assert await contents(factory, user, chat_id) == ["m1", "m2", "m3", "m4"]


async def test_delete_chat_removes_journal(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, _ = await setup_chat(factory, user, ["doomed"])
    directory = tmp_path / "undo" / user / chat_id
    assert directory.is_dir()
    async with factory() as session:
        assert await svc.delete_chat(session, user, chat_id) is True
    assert not directory.exists()  # the journal dies with its chat
    assert undo.remove_chat_undo(user, chat_id) is True  # already gone: True


# ---------------- R. REST flow ----------------


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _chat(client, title="Saga"):
    r = client.post("/api/v1/chats", json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()


def _msg(client, chat_id, content, role="user"):
    r = client.post(
        f"/api/v1/chats/{chat_id}/messages", json={"role": role, "content": content}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_api_undo_flow(app_client):
    chat = _chat(app_client)
    cid = chat["id"]
    _msg(app_client, cid, "first")
    second = _msg(app_client, cid, "second")
    r = app_client.patch(
        f"/api/v1/chats/{cid}/messages/{second['id']}", json={"content": "second-v2"}
    )
    assert r.status_code == 200, r.text
    r = app_client.get(f"/api/v1/chats/{cid}/undo")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 3 and body["can_undo"] is True
    assert [e["operation"] for e in body["entries"]] == [
        "message.edit", "message.append", "message.append",
    ]
    top_id = body["entries"][0]["id"]
    r = app_client.get(f"/api/v1/chats/{cid}/undo/{top_id}")
    assert r.status_code == 200 and r.json()["operation"] == "message.edit"
    # out-of-order via REST: the oldest entry id is refused
    r = app_client.post(
        f"/api/v1/chats/{cid}/undo", json={"entry_id": body["entries"][2]["id"]}
    )
    assert r.status_code == 422, r.text
    r = app_client.post(f"/api/v1/chats/{cid}/undo", json={})
    assert r.status_code == 200, r.text
    assert r.json()["undone"] == "message.edit"
    r = app_client.get(f"/api/v1/chats/{cid}/messages")
    assert [m["content"] for m in r.json()] == ["first", "second"]
    r = app_client.post(f"/api/v1/chats/{cid}/undo")  # no body at all
    assert r.status_code == 200 and r.json()["undone"] == "message.append"
    r = app_client.get(f"/api/v1/chats/{cid}/messages")
    assert [m["content"] for m in r.json()] == ["first"]
    r = app_client.delete(f"/api/v1/chats/{cid}/undo")
    assert r.status_code == 200 and r.json() == {"cleared": 1}
    r = app_client.post(f"/api/v1/chats/{cid}/undo", json={})
    assert r.status_code == 404, r.text  # nothing to undo
    r = app_client.get(f"/api/v1/chats/{UNKNOWN_ID}/undo")
    assert r.status_code == 404, r.text
    r = app_client.get(f"/api/v1/chats/{cid}/undo/{UNKNOWN_ID}")
    assert r.status_code == 404, r.text
    r = app_client.get(f"/api/v1/chats/{cid}/undo/..%2Fx")
    assert r.status_code in (404, 422), r.text
