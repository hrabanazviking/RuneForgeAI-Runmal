"""P-175 - Workspace binding history deletion (Part XI, DERIVED).

Pins: the store deletion law (remove_history_entry drops
exactly one entry permanently, returns it verbatim, carries
live bindings verbatim in the same save, and writes NOTHING
on a miss - no save, no file created; get_history_entry reads
one entry by id), permanence (a deleted entry never
resurrects through P-173's bindings-only save preservation,
and a later ending appends after the survivors in order),
the owner-scoped service (unknown OR foreign reads as None,
a foreign entry is never deleted), both ending events being
deletable (unbound and chat_deleted alike), the neighbours
(purge_chat still RETAINS history and keeps its count
contract, remove_binding still archives, the P-173 read
document and its five notes unchanged in shape, migration
head stays 0041), the HTTP road (DELETE
/workspaces/history/{entry_id} answers the P-169 unbind
shape {"deleted": True, "id"} at 200 for an owned entry,
one 404 "workspace history entry not found" for unknown,
foreign and already-deleted alike, and a second delete of
the same entry is a 404, never a silent success), and the
honesty law (deletion touches no bound folder and ends no
live binding). No network.
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


def seed_history(store, owner="u1", chat="c1", folder="/bench"):
    binding = ws.register_binding(
        store, owner_id=owner, chat_id=chat, folder_path=folder)
    store.remove_binding(binding.id)
    return store.list_history_for_owner(owner)[-1]


# ------------------------------------------------------- store


def test_remove_drops_exactly_one_entry_and_returns_it(tmp_path):
    store = make_store(tmp_path)
    first = seed_history(store, chat="c1", folder="/a")
    second = seed_history(store, chat="c2", folder="/b")
    live = ws.register_binding(store, owner_id="u1", chat_id="c3",
                               folder_path="/live")
    removed = store.remove_history_entry(first.id)
    assert removed == first
    assert store.get_history_entry(first.id) is None
    assert [e.id for e in store.list_history_for_owner("u1")] == [second.id]
    doc = json.loads(store.index_path.read_text())
    assert [row["id"] for row in doc["history"]] == [second.id]
    assert [row["id"] for row in doc["bindings"]] == [live.id]
    assert store.get_for_chat("c3") == live  # live binding untouched


def test_remove_miss_writes_nothing(tmp_path):
    store = make_store(tmp_path)
    entry = seed_history(store)
    before = store.index_path.read_bytes()
    assert store.remove_history_entry("no-such-id") is None
    assert store.index_path.read_bytes() == before  # byte-identical
    assert store.list_history_for_owner("u1") == [entry]


def test_remove_miss_on_empty_store_creates_no_file(tmp_path):
    store = make_store(tmp_path)
    assert store.remove_history_entry("no-such-id") is None
    assert not store.index_path.exists()


def test_get_history_entry_hit_and_miss(tmp_path):
    store = make_store(tmp_path)
    entry = seed_history(store)
    assert store.get_history_entry(entry.id) == entry
    assert store.get_history_entry("no-such-id") is None
    assert store.get_history_entry("") is None


def test_both_ending_events_are_deletable(tmp_path):
    store = make_store(tmp_path)
    unbound = seed_history(store, chat="c1")
    ws.register_binding(store, owner_id="u1", chat_id="c2",
                        folder_path="/b")
    store.purge_chat("c2")
    entries = store.list_history_for_owner("u1")
    assert [e.event for e in entries] == ["unbound", "chat_deleted"]
    assert store.remove_history_entry(entries[1].id) is not None
    assert store.remove_history_entry(unbound.id) is not None
    assert store.list_history_for_owner("u1") == []


def test_deletion_is_permanent_and_never_resurrects(tmp_path):
    store = make_store(tmp_path)
    doomed = seed_history(store, chat="c1", folder="/a")
    kept = seed_history(store, chat="c2", folder="/b")
    store.remove_history_entry(doomed.id)
    # A later bind (bindings-only save, P-173 preservation
    # law) must carry the SURVIVING history, not the deleted.
    live = ws.register_binding(store, owner_id="u1", chat_id="c3",
                               folder_path="/c")
    fresh = ws.WorkspaceStore(tmp_path / "data")  # reload from disk
    assert [e.id for e in fresh.list_history_for_owner("u1")] == [kept.id]
    # A later ending appends after the survivors, in order.
    store.remove_binding(live.id)
    entries = store.list_history_for_owner("u1")
    assert [e.id for e in entries[:-1]] == [kept.id]
    assert entries[-1].binding_id == live.id and len(entries) == 2


def test_order_of_survivors_is_store_order(tmp_path):
    store = make_store(tmp_path)
    one = seed_history(store, chat="c1", folder="/a")
    two = seed_history(store, chat="c2", folder="/b")
    three = seed_history(store, chat="c3", folder="/c")
    store.remove_history_entry(two.id)
    assert [e.id for e in store.list_history_for_owner("u1")] == [
        one.id, three.id]


# ----------------------------------------------------- service


def test_service_deletes_only_the_callers_own_entry(tmp_path):
    store = make_store(tmp_path)
    mine = seed_history(store, owner="u1", chat="c1")
    theirs = seed_history(store, owner="u2", chat="c2")
    assert hist.delete_workspace_history_entry(
        store, "u2", mine.id) is None  # foreign: no leak, no delete
    assert store.get_history_entry(mine.id) == mine
    assert hist.delete_workspace_history_entry(
        store, "u1", "no-such-id") is None
    removed = hist.delete_workspace_history_entry(store, "u1", mine.id)
    assert removed == mine
    assert store.get_history_entry(mine.id) is None
    assert store.get_history_entry(theirs.id) == theirs


@pytest.mark.asyncio
async def test_read_document_counts_drop_after_deletion(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    entry = seed_history(store, owner=uid, chat=chat_id)
    async with factory() as session:
        doc = await hist.resolve_workspace_history(session, store, uid)
    assert doc["entry_count"] == 1 and len(doc["notes"]) == 5
    assert doc["schema"] == "runmal-p173-workspace-history-v1"
    assert hist.delete_workspace_history_entry(store, uid, entry.id) == entry
    async with factory() as session:
        doc2 = await hist.resolve_workspace_history(session, store, uid)
    assert doc2["entry_count"] == 0 and doc2["history"] == []


# --------------------------------------------------- neighbours


def test_purge_and_unbind_contracts_unweakened(tmp_path):
    store = make_store(tmp_path)
    ws.register_binding(store, owner_id="u1", chat_id="c1",
                        folder_path="/a")
    assert store.purge_chat("c1") == 1  # archives, count contract kept
    entries = store.list_history_for_owner("u1")
    assert len(entries) == 1 and entries[0].event == "chat_deleted"
    assert store.purge_chat("c1") == 0  # retained history is NOT purged
    assert store.list_history_for_owner("u1") == entries
    binding = ws.register_binding(store, owner_id="u1", chat_id="c2",
                                  folder_path="/b")
    assert store.remove_binding(binding.id) == binding  # still archives
    assert len(store.list_history_for_owner("u1")) == 2


def test_deletion_touches_no_folder_and_no_live_binding(tmp_path):
    folder = tmp_path / "bench"
    folder.mkdir()
    marker = folder / "keep.txt"
    marker.write_text("mine")
    store = make_store(tmp_path)
    entry = seed_history(store, chat="c1", folder=str(folder))
    live = ws.register_binding(store, owner_id="u1", chat_id="c2",
                               folder_path=str(folder))
    assert store.remove_history_entry(entry.id) == entry
    assert marker.read_text() == "mine"
    assert [p.name for p in folder.iterdir()] == ["keep.txt"]
    assert store.get_for_chat("c2") == live


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"


# ------------------------------------------------------------ HTTP


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


@pytest.mark.asyncio
async def test_http_delete_road_round_trip(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    made = client.post("/api/v1/workspaces/bindings", json={
        "chat_id": chat_id, "folder_path": str(tmp_path / "bench")})
    assert made.status_code == 201, made.text
    binding_id = made.json()["binding"]["id"]
    assert client.delete(
        f"/api/v1/workspaces/bindings/{binding_id}").status_code == 200
    doc = client.get("/api/v1/workspaces/history").json()
    assert doc["entry_count"] == 1
    entry_id = doc["history"][0]["entry"]["id"]
    gone = client.delete(f"/api/v1/workspaces/history/{entry_id}")
    assert gone.status_code == 200, gone.text
    assert gone.json() == {"deleted": True, "id": entry_id}
    assert client.get(
        "/api/v1/workspaces/history").json()["entry_count"] == 0
    again = client.delete(f"/api/v1/workspaces/history/{entry_id}")
    assert again.status_code == 404  # a second delete is not a success
    assert again.json()["detail"] == "workspace history entry not found"


@pytest.mark.asyncio
async def test_http_unknown_and_foreign_entries_are_one_404(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    await seed_chat(factory, uid)
    store = make_store(tmp_path)
    foreign = seed_history(store, owner="someone-else", chat="cX")
    for target in ("no-such-id", foreign.id):
        resp = client.delete(f"/api/v1/workspaces/history/{target}")
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == (
            "workspace history entry not found")
    # The foreign entry survived both attempts, untouched.
    assert store.get_history_entry(foreign.id) == foreign


@pytest.mark.asyncio
async def test_http_delete_leaves_live_bindings_alone(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    other_chat = await seed_chat(factory, uid, "Second")
    store = make_store(tmp_path)
    entry = seed_history(store, owner=uid, chat=chat_id)
    made = client.post("/api/v1/workspaces/bindings", json={
        "chat_id": other_chat, "folder_path": str(tmp_path / "live")})
    assert made.status_code == 201, made.text
    resp = client.delete(f"/api/v1/workspaces/history/{entry.id}")
    assert resp.status_code == 200, resp.text
    listed = client.get("/api/v1/workspaces").json()
    assert listed["binding_count"] == 1  # the live binding stands
    assert listed["workspaces"][0]["binding"]["chat_id"] == other_chat
