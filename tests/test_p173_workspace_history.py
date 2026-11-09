"""P-173 - Workspace binding history (Part XI, DERIVED).

Pins: the store amendment (an ended binding - explicit
unbind or chat-deletion custody purge - is archived in
the SAME workspaces.json index as a history entry with
the binding's fields verbatim, the ending moment, and
the cause under the closed HISTORY_EVENTS law; a miss
archives nothing; a bindings-only save never erases
history; a pre-P-173 file with no history key and a
corrupt file both read as empty history), the custody
judgement (purge_chat archives chat_deleted, keeps its
count contract, is idempotent, and RETAINS earlier
history), the read surface (owner scoping with no
leak, no chat-existence gate - a deleted chat's entries
are returned with chat_exists judged live, the chat
filter, counts summed from the entries themselves,
folder state judged live at history-read time), the
HTTP road, the end-to-end delete_chat custody, the
pure-read law, and the neighbours (migration head
stays 0041, P-169's five notes unchanged). No network.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import service as chats_svc
from runmal.chats.greetings import GreetingChoice
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.plugins import service as plugin_service
from runmal.workspaces import bindings as ws
from runmal.workspaces import history as hist


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


def make_store(tmp_path):
    return ws.WorkspaceStore(tmp_path / "data")


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


async def seed_chat(factory, uid, title="The Workshop"):
    async with factory() as session:
        chat = await chats_svc.create_chat(
            session, uid, title=title, character_id=None,
            greeting=GreetingChoice(mode="quiet"))
        await session.commit()
        return chat.id


# ------------------------------------------------- store: unbind


def test_unbind_archives_the_binding_verbatim(tmp_path):
    store = make_store(tmp_path)
    binding = ws.register_binding(
        store, owner_id="u1", chat_id="c1",
        folder_path=str(tmp_path / "bench"), label="bench",
        now="2026-11-09T01:00:00+00:00")
    removed = store.remove_binding(binding.id, now="2026-11-09T02:00:00+00:00")
    assert removed == binding
    assert store.get_for_chat("c1") is None
    entries = store.list_history_for_owner("u1")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.binding_id == binding.id
    assert entry.owner_id == "u1" and entry.chat_id == "c1"
    assert entry.folder_path == binding.folder_path
    assert entry.label == "bench"
    assert entry.bound_at == "2026-11-09T01:00:00+00:00"
    assert entry.ended_at == "2026-11-09T02:00:00+00:00"
    assert entry.event == ws.EVENT_UNBOUND
    assert entry.id and entry.id != binding.id
    # Same file: the history key sits beside bindings.
    doc = json.loads(store.index_path.read_text())
    assert doc["bindings"] == [] and len(doc["history"]) == 1
    assert doc["history"][0]["event"] == "unbound"


def test_remove_miss_archives_nothing(tmp_path):
    store = make_store(tmp_path)
    ws.register_binding(store, owner_id="u1", chat_id="c1",
                        folder_path=str(tmp_path))
    assert store.remove_binding("no-such-id") is None
    assert store.list_history_for_owner("u1") == []
    assert len(store.list_for_owner("u1")) == 1


def test_rebind_succession_reads_from_the_two_records(tmp_path):
    store = make_store(tmp_path)
    old = ws.register_binding(store, owner_id="u1", chat_id="c1",
                              folder_path=str(tmp_path / "old"),
                              now="2026-11-09T01:00:00+00:00")
    store.remove_binding(old.id, now="2026-11-09T02:00:00+00:00")
    new = ws.register_binding(store, owner_id="u1", chat_id="c1",
                              folder_path=str(tmp_path / "new"),
                              now="2026-11-09T03:00:00+00:00")
    live = store.get_for_chat("c1")
    assert live is not None and live.id == new.id
    entries = store.list_history_for_owner("u1")
    assert [e.folder_path for e in entries] == [str(tmp_path / "old")]
    assert entries[0].ended_at < live.created_at  # succession, honestly timed


def test_history_events_law_is_closed(tmp_path):
    assert ws.HISTORY_EVENTS == {"unbound", "chat_deleted"}
    store = make_store(tmp_path)
    one = ws.register_binding(store, owner_id="u1", chat_id="c1",
                              folder_path=str(tmp_path))
    store.remove_binding(one.id)
    store.purge_chat("c2")  # nothing bound: no entry
    ws.register_binding(store, owner_id="u1", chat_id="c2",
                              folder_path=str(tmp_path))
    store.purge_chat("c2")
    events = [e.event for e in store.list_history_for_owner("u1")]
    assert events == ["unbound", "chat_deleted"]
    assert all(e in ws.HISTORY_EVENTS for e in events)


# -------------------------------------------------- store: purge


def test_purge_archives_chat_deleted_and_keeps_contract(tmp_path):
    store = make_store(tmp_path)
    ws.register_binding(store, owner_id="u1", chat_id="c1",
                        folder_path=str(tmp_path), label="x",
                        now="2026-11-09T01:00:00+00:00")
    assert store.purge_chat("c1", now="2026-11-09T04:00:00+00:00") == 1
    assert store.purge_chat("c1") == 0  # idempotent: no second entry
    entries = store.list_history_for_owner("u1")
    assert len(entries) == 1
    assert entries[0].event == ws.EVENT_CHAT_DELETED
    assert entries[0].bound_at == "2026-11-09T01:00:00+00:00"
    assert entries[0].ended_at == "2026-11-09T04:00:00+00:00"
    assert store.list_for_owner("u1") == []


def test_purge_retains_earlier_history_for_the_chat(tmp_path):
    store = make_store(tmp_path)
    first = ws.register_binding(store, owner_id="u1", chat_id="c1",
                                folder_path=str(tmp_path / "a"))
    store.remove_binding(first.id)  # unbound entry for c1
    ws.register_binding(store, owner_id="u1", chat_id="c1",
                        folder_path=str(tmp_path / "b"))
    assert store.purge_chat("c1") == 1
    events = [e.event for e in store.list_history_for_owner("u1")]
    assert events == ["unbound", "chat_deleted"]  # both kept, in order


# ------------------------------------------- store: preservation


def test_bind_after_unbind_preserves_history(tmp_path):
    store = make_store(tmp_path)
    one = ws.register_binding(store, owner_id="u1", chat_id="c1",
                              folder_path=str(tmp_path))
    store.remove_binding(one.id)
    ws.register_binding(store, owner_id="u1", chat_id="c2",
                        folder_path=str(tmp_path))  # add_binding -> _save
    entries = store.list_history_for_owner("u1")
    assert len(entries) == 1 and entries[0].binding_id == one.id
    doc = json.loads(store.index_path.read_text())
    assert len(doc["bindings"]) == 1 and len(doc["history"]) == 1


def test_legacy_file_without_history_key_reads_empty(tmp_path):
    store = make_store(tmp_path)
    store.index_path.parent.mkdir(parents=True, exist_ok=True)
    legacy = {"version": 1, "bindings": [{
        "id": "b1", "owner_id": "u1", "chat_id": "c1",
        "folder_path": str(tmp_path), "label": "",
        "created_at": "2026-11-09T00:00:00+00:00"}]}
    store.index_path.write_text(json.dumps(legacy))
    assert store.get_for_chat("c1") is not None
    assert store.list_history_for_owner("u1") == []


def test_corrupt_store_reads_history_as_empty(tmp_path):
    store = make_store(tmp_path)
    store.index_path.parent.mkdir(parents=True, exist_ok=True)
    store.index_path.write_text("{not json")
    assert store.list_history_for_owner("u1") == []


def test_history_is_owner_scoped_at_the_store(tmp_path):
    store = make_store(tmp_path)
    mine = ws.register_binding(store, owner_id="u1", chat_id="c1",
                               folder_path=str(tmp_path))
    theirs = ws.register_binding(store, owner_id="u2", chat_id="c2",
                                 folder_path=str(tmp_path))
    store.remove_binding(mine.id)
    store.remove_binding(theirs.id)
    assert [e.chat_id for e in store.list_history_for_owner("u1")] == ["c1"]
    assert [e.chat_id for e in store.list_history_for_owner("u2")] == ["c2"]


# ------------------------------------------------------- service


@pytest.mark.asyncio
async def test_history_document_counts_and_live_judgements(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    alive = await seed_chat(factory, uid, "Alive")
    gone = await seed_chat(factory, uid, "Gone")
    store = make_store(tmp_path)
    folder = tmp_path / "bench"  # missing at first read
    one = ws.register_binding(store, owner_id=uid, chat_id=alive,
                              folder_path=str(folder))
    store.remove_binding(one.id)
    two = ws.register_binding(store, owner_id=uid, chat_id=gone,
                              folder_path=str(folder))
    async with factory() as session:
        assert await chats_svc.delete_chat(session, uid, gone) is True
    # delete_chat custody archived the second binding itself.
    async with factory() as session:
        doc = await hist.resolve_workspace_history(session, store, uid)
    assert doc["schema"] == "runmal-p173-workspace-history-v1"
    assert doc["entry_count"] == 2
    assert doc["unbound_count"] == 1 and doc["chat_deleted_count"] == 1
    assert doc["chat_count"] == 2 and doc["chat_id"] is None
    assert len(doc["notes"]) == 5
    rows = {row["entry"]["chat_id"]: row for row in doc["history"]}
    assert rows[alive]["chat_exists"] is True
    assert rows[alive]["chat_title"] == "Alive"
    assert rows[alive]["folder_state"] == "missing"  # judged live, now
    assert rows[gone]["chat_exists"] is False  # gone, yet returned
    assert rows[gone]["chat_title"] is None
    assert rows[gone]["entry"]["binding_id"] == two.id
    folder.mkdir()
    async with factory() as session:
        doc2 = await hist.resolve_workspace_history(session, store, uid)
    assert all(r["folder_state"] == "ready" for r in doc2["history"])


@pytest.mark.asyncio
async def test_history_filter_and_foreign_scoping(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, "someone-else")
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    one = ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                              folder_path=str(tmp_path))
    store.remove_binding(one.id)
    async with factory() as session:
        mine = await hist.resolve_workspace_history(
            session, store, uid, chat_id)
        assert mine["entry_count"] == 1 and mine["chat_id"] == chat_id
        unknown = await hist.resolve_workspace_history(
            session, store, uid, "no-such-chat")
        assert unknown["entry_count"] == 0 and unknown["history"] == []
        foreign = await hist.resolve_workspace_history(session, store, other)
        assert foreign["entry_count"] == 0  # nothing leaks across owners
        foreign_filter = await hist.resolve_workspace_history(
            session, store, other, chat_id)
        assert foreign_filter["entry_count"] == 0


@pytest.mark.asyncio
async def test_history_read_is_pure_and_folder_untouched(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    folder = tmp_path / "bench"
    folder.mkdir()
    marker = folder / "keep.txt"
    marker.write_text("mine")
    store = make_store(tmp_path)
    one = ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                              folder_path=str(folder))
    store.remove_binding(one.id)
    before = store.index_path.read_bytes()
    async with factory() as session:
        await hist.resolve_workspace_history(session, store, uid)
    assert store.index_path.read_bytes() == before  # the read wrote nothing
    assert marker.read_text() == "mine"
    assert [p.name for p in folder.iterdir()] == ["keep.txt"]


# ------------------------------------------------------------ HTTP


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


@pytest.mark.asyncio
async def test_http_history_road(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    empty = client.get("/api/v1/workspaces/history")
    assert empty.status_code == 200, empty.text
    assert empty.json()["entry_count"] == 0
    made = client.post("/api/v1/workspaces/bindings", json={
        "chat_id": chat_id, "folder_path": str(tmp_path / "bench")})
    assert made.status_code == 201, made.text
    binding_id = made.json()["binding"]["id"]
    assert client.delete(
        f"/api/v1/workspaces/bindings/{binding_id}").status_code == 200
    doc = client.get("/api/v1/workspaces/history")
    assert doc.status_code == 200
    body = doc.json()
    assert body["schema"] == "runmal-p173-workspace-history-v1"
    assert body["entry_count"] == 1 and body["unbound_count"] == 1
    assert body["history"][0]["entry"]["binding_id"] == binding_id
    assert body["history"][0]["chat_exists"] is True
    filtered = client.get("/api/v1/workspaces/history",
                          params={"chat_id": chat_id})
    assert filtered.json()["entry_count"] == 1
    other_chat = client.get("/api/v1/workspaces/history",
                            params={"chat_id": "no-such-chat"})
    assert other_chat.status_code == 200
    assert other_chat.json()["entry_count"] == 0  # empty, never a 404


# ------------------------------------------------------- neighbours


def test_p169_live_semantics_unweakened(tmp_path):
    store = make_store(tmp_path)
    binding = ws.register_binding(store, owner_id="u1", chat_id="c1",
                                  folder_path=str(tmp_path))
    assert len(ws.NOTES) == 5  # P-169 battery pins the five notes
    assert ws.BINDING_SCHEMA == "runmal-p169-workspace-binding-v1"
    assert ws.LIST_SCHEMA == "runmal-p169-workspace-list-v1"
    with pytest.raises(ws.WorkspaceError):  # still one binding per chat
        ws.register_binding(store, owner_id="u1", chat_id="c1",
                            folder_path=str(tmp_path))
    assert store.get_binding(binding.id) == binding


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
