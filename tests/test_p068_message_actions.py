"""P-068 message actions battery (TESTER).

Pins the complete message-action set on persisted chat messages:
the pure variant-history / move contracts (chats/actions.py), edit
with variant history composing with the P-065 swipe deck (prior
contents retained and inspectable, never silently overwritten;
identical edit is a no-op), delete (pin cleanup, renumbering),
move (strict target, position materialisation), copy-to-branch
(fork-at-message into a new chat, or single copy into an owned
chat; deep copies; never pinned), pin-to-memory (a REAL pinned
Memory + MemorySource link surfacing through memory retrieval;
idempotent; unpin), cross-user isolation throughout, metadata-only
events (a planted secret never reaches the event log), the REST
API, and PROVISIONAL migration 0038.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import actions as act
from runmal.chats import service as svc
from runmal.chats.service import event_to_dict, message_to_dict
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Memory, MemorySource, Message, User
from runmal.memory import service as memory_svc
from runmal.memory.retrieval import fts_hits

SECRET = "ZqxActionSecret68"

# ---------------- pure: variant history ----------------

def test_parse_history_defensive():
    assert act.parse_history(None) == []
    assert act.parse_history("") == []
    assert act.parse_history("[]") == []
    assert act.parse_history("not json") == []
    assert act.parse_history('{"a": 1}') == []
    assert act.parse_history('[{"content": "x"}, {"nope": 1}, "s", 5]') == [
        {"content": "x", "edited_at": None, "swipe_id": None}
    ]
    good = [{"content": "a", "edited_at": "t0", "swipe_id": 2}]
    assert act.parse_history(json.dumps(good)) == good


def test_record_edit_appends_without_mutating():
    base = [{"content": "v1", "edited_at": "t0", "swipe_id": 0}]
    out = act.record_edit(base, "v2", "t1", 1)
    assert [e["content"] for e in out] == ["v1", "v2"]
    assert out[-1] == {"content": "v2", "edited_at": "t1", "swipe_id": 1}
    assert len(base) == 1  # input untouched


def test_record_edit_caps_at_max():
    history = []
    for i in range(act.MAX_VARIANTS + 5):
        history = act.record_edit(history, f"v{i}", "t", 0)
    assert len(history) == act.MAX_VARIANTS
    assert history[-1]["content"] == f"v{act.MAX_VARIANTS + 4}"
    assert history[0]["content"] == "v5"  # oldest dropped


def test_record_edit_rejects_empty():
    with pytest.raises(ValueError):
        act.record_edit([], "", "t", 0)
    with pytest.raises(ValueError):
        act.record_edit([], None, "t", 0)

# ---------------- pure: move contract ----------------

def test_validate_move_target_strict():
    assert act.validate_move_target(3, 0) == 0
    assert act.validate_move_target(3, 2) == 2
    for bad in (-1, 3, 99, True, "1", 1.5, None):
        with pytest.raises(ValueError):
            act.validate_move_target(3, bad)
    with pytest.raises(ValueError):
        act.validate_move_target(0, 0)


def test_move_index_pure():
    assert act.move_index(["a", "b", "c", "d"], 3, 0) == ["d", "a", "b", "c"]
    assert act.move_index(["a", "b", "c", "d"], 0, 2) == ["b", "c", "a", "d"]
    src = ["a", "b"]
    assert act.move_index(src, 0, 0) == ["a", "b"]
    assert src == ["a", "b"]

# ---------------- service harness ----------------

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


async def history_dicts(factory, user_id, chat_id):
    async with factory() as session:
        history = await svc.get_history(session, user_id, chat_id)
        assert history is not None
        return [message_to_dict(m) for m in history]


async def event_dicts(factory, user_id, chat_id):
    async with factory() as session:
        events = await svc.list_events(session, user_id, chat_id)
        assert events is not None
        return [event_to_dict(e) for e in events]

# ---------------- service: edit + variant history ----------------

async def test_edit_records_variant_history(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["original"])
    async with factory() as session:
        msg = await svc.edit_message(session, user, chat_id, mid, "second")
        assert msg is not None and msg.content == "second"
    async with factory() as session:
        variants = await svc.get_message_variants(session, user, chat_id, mid)
    assert [v["content"] for v in variants] == ["original"]
    assert variants[0]["swipe_id"] == 0
    state = (await history_dicts(factory, user, chat_id))[0]
    assert state["variant_count"] == 1
    assert state["variant_history"][0]["content"] == "original"


async def test_edit_history_accumulates_in_order(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["v1"])
    for new in ("v2", "v3"):
        async with factory() as session:
            await svc.edit_message(session, user, chat_id, mid, new)
    async with factory() as session:
        variants = await svc.get_message_variants(session, user, chat_id, mid)
    assert [v["content"] for v in variants] == ["v1", "v2"]
    state = (await history_dicts(factory, user, chat_id))[0]
    assert state["content"] == "v3" and state["variant_count"] == 2


async def test_edit_identical_is_noop(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["same"])
    before = await event_dicts(factory, user, chat_id)
    async with factory() as session:
        msg = await svc.edit_message(session, user, chat_id, mid, "same")
        assert msg is not None
    async with factory() as session:
        assert await svc.get_message_variants(session, user, chat_id, mid) == []
    assert await event_dicts(factory, user, chat_id) == before  # no new event


async def test_edit_composes_with_swipe_deck(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["a"])
    async with factory() as session:
        await svc.add_swipe(session, user, chat_id, mid, "b")
        await svc.select_swipe(session, user, chat_id, mid, index=0)
        msg = await svc.edit_message(session, user, chat_id, mid, "a-edited")
        assert msg is not None
    state = (await history_dicts(factory, user, chat_id))[0]
    assert state["swipes"] == ["a-edited", "b"]  # active only; invariant holds
    assert state["content"] == state["swipes"][state["swipe_id"]]
    assert [v["content"] for v in state["variant_history"]] == ["a"]
    assert state["variant_history"][0]["swipe_id"] == 0


async def test_edit_rejects_empty_and_missing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["x"])
    async with factory() as session:
        with pytest.raises(ValueError):
            await svc.edit_message(session, user, chat_id, mid, "")
        assert await svc.edit_message(session, user, chat_id, "nope", "y") is None
        assert await svc.get_message_variants(session, user, chat_id, "nope") is None

# ---------------- service: move ----------------

async def test_move_materialises_positions(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await setup_chat(factory, user, ["m0", "m1", "m2", "m3"])
    before = await history_dicts(factory, user, chat_id)
    assert all(d["position"] is None for d in before)  # legacy order
    async with factory() as session:
        msg = await svc.move_message(session, user, chat_id, ids[3], 0)
        assert msg is not None
    after = await history_dicts(factory, user, chat_id)
    assert [d["content"] for d in after] == ["m3", "m0", "m1", "m2"]
    assert [d["position"] for d in after] == [0, 1, 2, 3]


async def test_move_middle_and_append_after(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await setup_chat(factory, user, ["m0", "m1", "m2"])
    async with factory() as session:
        await svc.move_message(session, user, chat_id, ids[0], 2)
        await svc.append_message(session, user, chat_id, "user", "m3")
    after = await history_dicts(factory, user, chat_id)
    assert [d["content"] for d in after] == ["m1", "m2", "m0", "m3"]
    assert [d["position"] for d in after] == [0, 1, 2, 3]


async def test_move_strict_target_changes_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await setup_chat(factory, user, ["m0", "m1"])
    for bad in (-1, 2, 99):
        async with factory() as session:
            with pytest.raises(ValueError):
                await svc.move_message(session, user, chat_id, ids[0], bad)
    after = await history_dicts(factory, user, chat_id)
    assert [d["content"] for d in after] == ["m0", "m1"]
    assert all(d["position"] is None for d in after)  # nothing materialised


async def test_move_noop_same_index_no_event(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await setup_chat(factory, user, ["m0", "m1"])
    before = await event_dicts(factory, user, chat_id)
    async with factory() as session:
        msg = await svc.move_message(session, user, chat_id, ids[1], 1)
        assert msg is not None
    assert await event_dicts(factory, user, chat_id) == before
    after = await history_dicts(factory, user, chat_id)
    assert all(d["position"] is None for d in after)

# ---------------- service: delete ----------------

async def test_delete_message_basic(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await setup_chat(factory, user, ["m0", "m1", "m2"])
    async with factory() as session:
        assert await svc.delete_message(session, user, chat_id, ids[1]) is True
        assert await svc.delete_message(session, user, chat_id, ids[1]) is False
    after = await history_dicts(factory, user, chat_id)
    assert [d["content"] for d in after] == ["m0", "m2"]


async def test_delete_renumbers_materialised_chat(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await setup_chat(factory, user, ["m0", "m1", "m2", "m3"])
    async with factory() as session:
        await svc.move_message(session, user, chat_id, ids[0], 1)  # materialise
        assert await svc.delete_message(session, user, chat_id, ids[2]) is True
    after = await history_dicts(factory, user, chat_id)
    assert [d["content"] for d in after] == ["m1", "m0", "m3"]
    assert [d["position"] for d in after] == [0, 1, 2]

# ---------------- service: copy-to-branch ----------------

async def test_copy_fork_new_chat_upto_message(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await setup_chat(factory, user, ["m0", "m1", "m2"])
    async with factory() as session:
        result = await svc.copy_message_to_branch(session, user, chat_id, ids[1])
        assert result is not None
        assert result["mode"] == "fork" and result["copied_count"] == 2
        branch_id = result["target_chat"].id
        assert result["target_chat"].title == "Hall (branch)"
    branch = await history_dicts(factory, user, branch_id)
    assert [d["content"] for d in branch] == ["m0", "m1"]  # m2 not carried
    assert [d["position"] for d in branch] == [0, 1]
    assert all(d["id"] not in ids for d in branch)  # fresh rows
    source = await history_dicts(factory, user, chat_id)
    assert [d["content"] for d in source] == ["m0", "m1", "m2"]  # untouched


async def test_copy_preserves_deck_and_is_deep(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["a"])
    async with factory() as session:
        await svc.add_swipe(session, user, chat_id, mid, "b")
        await svc.edit_message(session, user, chat_id, mid, "b-edited")
        result = await svc.copy_message_to_branch(session, user, chat_id, mid)
        branch_id = result["target_chat"].id
        copy_id = result["copied_message"].id
    copied = (await history_dicts(factory, user, branch_id))[0]
    assert copied["swipes"] == ["a", "b-edited"]
    assert [v["content"] for v in copied["variant_history"]] == ["b"]
    async with factory() as session:  # edit the copy; the original must not bleed
        await svc.edit_message(session, user, branch_id, copy_id, "copy-only")
    original = (await history_dicts(factory, user, chat_id))[0]
    assert original["content"] == "b-edited"
    assert [v["content"] for v in original["variant_history"]] == ["b"]


async def test_copy_into_existing_chat_appends(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await setup_chat(factory, user, ["src0", "src1"])
    target_id, _tids = await setup_chat(factory, user, ["dst0"], title="Target")
    async with factory() as session:
        result = await svc.copy_message_to_branch(
            session, user, chat_id, ids[0], target_chat_id=target_id)
        assert result["mode"] == "copy" and result["copied_count"] == 1
    target = await history_dicts(factory, user, target_id)
    assert [d["content"] for d in target] == ["dst0", "src0"]


async def test_copy_foreign_target_raises_and_missing_source_none(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, "intruder")
    chat_id, ids = await setup_chat(factory, user, ["m0"])
    foreign_id, _ = await setup_chat(factory, other, ["theirs"])
    async with factory() as session:
        with pytest.raises(KeyError):
            await svc.copy_message_to_branch(
                session, user, chat_id, ids[0], target_chat_id=foreign_id)
        assert await svc.copy_message_to_branch(
            session, other, chat_id, ids[0]) is None
        assert await svc.copy_message_to_branch(
            session, user, chat_id, "nope") is None


async def test_copy_never_carries_pin(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["pinned-one"])
    async with factory() as session:
        await svc.pin_message_to_memory(session, user, chat_id, mid)
        result = await svc.copy_message_to_branch(session, user, chat_id, mid)
        branch_id = result["target_chat"].id
    copied = (await history_dicts(factory, user, branch_id))[0]
    assert copied["pinned"] is False
    async with factory() as session:
        assert await svc.list_pinned_messages(session, user, branch_id) == []
        memories = await memory_svc.list_memories(session, user, state="pinned")
        assert len(memories) == 1  # only the original pin exists

# ---------------- service: pin-to-memory ----------------

async def test_pin_creates_real_memory_with_source(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, [f"remember {SECRET}"])
    async with factory() as session:
        memory = await svc.pin_message_to_memory(session, user, chat_id, mid)
        assert memory is not None
        assert memory.pinned is True and memory.state == "pinned"
        assert memory.kind == "episodic" and memory.scope == "chat"
        assert memory.chat_id == chat_id
        assert memory.content == f"remember {SECRET}"
        sources = await memory_svc.list_sources(session, memory.id)
        assert [(s.source_kind, s.source_id, s.chat_id) for s in sources] == [
            ("message", mid, chat_id)]
    state = (await history_dicts(factory, user, chat_id))[0]
    assert state["pinned"] is True


async def test_pin_surfaces_through_memory_retrieval(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["the ZqxHarbour68 light"])
    async with factory() as session:
        memory = await svc.pin_message_to_memory(session, user, chat_id, mid)
        hits = await fts_hits(session, user, "ZqxHarbour68")
        assert memory.id in hits  # the existing FTS retrieval road sees it
        pinned = await svc.list_pinned_messages(session, user, chat_id)
        assert [m.id for m in pinned] == [mid]


async def test_pin_idempotent_and_unpin(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["once"])
    async with factory() as session:
        first = await svc.pin_message_to_memory(session, user, chat_id, mid)
        second = await svc.pin_message_to_memory(session, user, chat_id, mid)
        assert first.id == second.id
        memories = await memory_svc.list_memories(session, user, state="pinned")
        assert len(memories) == 1
        assert await svc.unpin_message_from_memory(session, user, chat_id, mid) is True
        assert await svc.unpin_message_from_memory(session, user, chat_id, mid) is False
        assert await svc.unpin_message_from_memory(session, user, chat_id, "nope") is None
        assert await memory_svc.list_memories(session, user, state="pinned") == []
        assert await svc.list_pinned_messages(session, user, chat_id) == []
    state = (await history_dicts(factory, user, chat_id))[0]
    assert state["pinned"] is False


async def test_edit_of_pinned_refreshes_memory(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["before"])
    async with factory() as session:
        memory = await svc.pin_message_to_memory(session, user, chat_id, mid)
        await svc.edit_message(session, user, chat_id, mid, "after")
        refreshed = await memory_svc.get_memory(session, user, memory.id)
        assert refreshed is not None and refreshed.content == "after"


async def test_delete_pinned_removes_memory(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["doomed pin"])
    async with factory() as session:
        memory = await svc.pin_message_to_memory(session, user, chat_id, mid)
        assert await svc.delete_message(session, user, chat_id, mid) is True
        assert await memory_svc.get_memory(session, user, memory.id) is None
        sources = await session.scalars(
            select(MemorySource).where(MemorySource.source_id == mid))
        assert list(sources) == []  # no orphaned source link

# ---------------- isolation + event hygiene ----------------

async def test_actions_cross_user_isolation(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, "intruder")
    chat_id, ids = await setup_chat(factory, user, ["mine0", "mine1"])
    async with factory() as session:
        assert await svc.edit_message(session, other, chat_id, ids[0], "x") is None
        assert await svc.move_message(session, other, chat_id, ids[0], 1) is None
        assert await svc.delete_message(session, other, chat_id, ids[0]) is False
        assert await svc.pin_message_to_memory(session, other, chat_id, ids[0]) is None
        assert await svc.unpin_message_from_memory(session, other, chat_id, ids[0]) is None
        assert await svc.get_message_variants(session, other, chat_id, ids[0]) is None
        assert await svc.list_pinned_messages(session, other, chat_id) is None
    after = await history_dicts(factory, user, chat_id)
    assert [d["content"] for d in after] == ["mine0", "mine1"]


async def test_events_never_carry_message_text(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await setup_chat(factory, user, [f"{SECRET} alpha", "beta"])
    async with factory() as session:
        await svc.edit_message(session, user, chat_id, ids[0], f"{SECRET} edited")
        await svc.move_message(session, user, chat_id, ids[1], 0)
        result = await svc.copy_message_to_branch(session, user, chat_id, ids[0])
        branch_id = result["target_chat"].id
        await svc.pin_message_to_memory(session, user, chat_id, ids[0])
        await svc.unpin_message_from_memory(session, user, chat_id, ids[0])
        await svc.delete_message(session, user, chat_id, ids[1])
    for cid in (chat_id, branch_id):
        for event in await event_dicts(factory, user, cid):
            assert SECRET not in json.dumps(event), event
    kinds = [e["kind"] for e in await event_dicts(factory, user, chat_id)]
    for expected in ("message.edited", "message.moved",
                     "message.copied_to_branch", "message.pinned_to_memory",
                     "message.unpinned_from_memory", "message.deleted"):
        assert expected in kinds

# ---------------- REST API ----------------

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


def _api_chat_with_messages(client, contents):
    chat = client.post("/api/v1/chats", json={"title": "Hall"}).json()
    ids = []
    for i, content in enumerate(contents):
        role = "user" if i % 2 == 0 else "assistant"
        msg = client.post(f"/api/v1/chats/{chat['id']}/messages",
                          json={"role": role, "content": content}).json()
        ids.append(msg["id"])
    return chat["id"], ids


def test_api_message_actions_flow(app_client):
    chat_id, ids = _api_chat_with_messages(app_client, ["one", "two", "three"])
    base = f"/api/v1/chats/{chat_id}/messages/{ids[0]}"
    resp = app_client.patch(base, json={"content": "one-edited"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["variant_count"] == 1
    resp = app_client.get(f"{base}/variants")
    assert resp.status_code == 200, resp.text
    assert [v["content"] for v in resp.json()["variants"]] == ["one"]
    resp = app_client.post(f"/api/v1/chats/{chat_id}/messages/{ids[2]}/move",
                           json={"to_index": 0})
    assert resp.status_code == 200, resp.text
    history = app_client.get(f"/api/v1/chats/{chat_id}/messages").json()
    assert [m["content"] for m in history] == ["three", "one-edited", "two"]
    assert [m["position"] for m in history] == [0, 1, 2]
    resp = app_client.post(f"{base}/pin")
    assert resp.status_code == 201, resp.text
    assert resp.json()["pinned"] is True and resp.json()["state"] == "pinned"
    pinned = app_client.get(f"/api/v1/chats/{chat_id}/pinned-messages")
    assert [m["id"] for m in pinned.json()] == [ids[0]]
    resp = app_client.post(f"{base}/copy-to-branch", json={})
    assert resp.status_code == 201, resp.text
    payload = resp.json()
    assert payload["mode"] == "fork" and payload["copied_count"] == 2
    branch_history = app_client.get(
        f"/api/v1/chats/{payload['target_chat']['id']}/messages").json()
    assert [m["content"] for m in branch_history] == ["three", "one-edited"]
    resp = app_client.delete(f"{base}/pin")
    assert resp.status_code == 200 and resp.json()["unpinned"] is True
    resp = app_client.delete(base)
    assert resp.status_code == 200, resp.text
    history = app_client.get(f"/api/v1/chats/{chat_id}/messages").json()
    assert [m["content"] for m in history] == ["three", "two"]


def test_api_message_actions_errors(app_client):
    chat_id, ids = _api_chat_with_messages(app_client, ["one", "two"])
    base = f"/api/v1/chats/{chat_id}/messages/{ids[0]}"
    resp = app_client.post(f"{base}/move", json={"to_index": 5})
    assert resp.status_code == 422, resp.text
    resp = app_client.post(f"{base}/move", json={"to_index": -1})
    assert resp.status_code == 422, resp.text
    for url in (f"/api/v1/chats/{chat_id}/messages/nope/variants",
                f"/api/v1/chats/nope/messages/{ids[0]}/variants"):
        assert app_client.get(url).status_code == 404
    assert app_client.post(f"{base}/pin-missing").status_code == 404
    resp = app_client.post(
        f"{base}/copy-to-branch", json={"target_chat_id": "missing"})
    assert resp.status_code == 404, resp.text
    resp = app_client.get(f"/api/v1/chats/nope/pinned-messages")
    assert resp.status_code == 404

# ---------------- migration: PROVISIONAL 0038 ----------------

def _apply_up_to(db_path, revision):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "revision TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        for rev, _desc, module in MIGRATIONS:
            if rev > revision:
                break
            module.upgrade(conn)
            conn.execute(
                "INSERT INTO schema_migrations (revision, applied_at) VALUES (?, ?)",
                (rev, "test"))
            conn.commit()
    finally:
        conn.close()


def test_migration_head_is_0039_p073(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert "PROVISIONAL" in MIGRATIONS[-1][1]
    db_path = tmp_path / "m.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0042"
    assert current_revision(db_path) == "0042"
    assert migrate_to_head(db_path) == []  # idempotent


def test_migration_0038_applies_exactly_and_adds_columns(tmp_path):
    db_path = tmp_path / "m.db"
    _apply_up_to(db_path, "0036")
    assert current_revision(db_path) == "0036"
    assert migrate_to_head(db_path) == ["0037", "0038", "0039", "0040", "0041", "0042"]
    assert current_revision(db_path) == "0042"
    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    finally:
        conn.close()
    assert {"variant_history_json", "pinned", "position"} <= columns


async def test_legacy_row_reads_as_unedited_unpinned(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, (mid,) = await setup_chat(factory, user, ["legacy"])
    async with factory() as session:  # hand-shape a pre-0038 row
        msg = await session.get(Message, mid)
        msg.variant_history_json = "[]"
        msg.pinned = False
        msg.position = None
        await session.commit()
    state = (await history_dicts(factory, user, chat_id))[0]
    assert state["variant_history"] == [] and state["variant_count"] == 0
    assert state["pinned"] is False and state["position"] is None


async def test_list_pinned_truth_is_the_source_link(tmp_path):
    """list_pinned_messages follows the MemorySource join, not the flag:
    a flag set without a pin Memory does not list, and a pin Memory
    whose flag was cleared by hand still lists (tester check #19)."""
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await setup_chat(factory, user, ["flagonly", "realpin"])
    async with factory() as session:
        await svc.pin_message_to_memory(session, user, chat_id, ids[1])
        flag_only = await session.get(Message, ids[0])
        flag_only.pinned = True  # flag lies: no Memory behind it
        real = await session.get(Message, ids[1])
        real.pinned = False  # flag lies the other way: Memory exists
        await session.commit()
    async with factory() as session:
        pinned = await svc.list_pinned_messages(session, user, chat_id)
        assert [m.id for m in pinned] == [ids[1]]
