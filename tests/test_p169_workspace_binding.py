"""P-169 - Workspace binding foundation (Part XI opener, DERIVED).

Pins: the binding record (one owned chat bound to one
real folder path, stored verbatim as data in the house
JSON store, no migration), the register refusals (empty
path, empty chat, already-bound chat - nothing stored),
the folder-state law judged LIVE at read time (ready /
missing / not_a_directory / unreadable; a state never
stored and never claimed at bind time), the single and
list documents (schema tags, chat facts verbatim, counts
carried from the documents' own states, orphans counted
and never presented as live), owner scoping (unknown /
foreign chat or binding -> None / 404, existence never
leaks), chat-deletion custody (the binding dies with
the chat), the pure-data law (binding a folder reads
nothing in it and writes nothing into it), and the
neighbours (migration head stays 0041, no 0042).
No network.
"""

from __future__ import annotations

import os

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


# ------------------------------------------------------------ store


def test_register_stores_path_verbatim_after_strip(tmp_path):
    store = make_store(tmp_path)
    folder = tmp_path / "real folder"
    binding = ws.register_binding(
        store, owner_id="u1", chat_id="c1",
        folder_path=f"  {folder}  ", label="  bench  ")
    assert binding.folder_path == str(folder)
    assert binding.label == "bench"
    assert binding.owner_id == "u1" and binding.chat_id == "c1"
    again = store.get_for_chat("c1")
    assert again is not None and again.id == binding.id
    assert store.get_binding(binding.id) == binding


def test_register_never_requires_the_folder_to_exist(tmp_path):
    store = make_store(tmp_path)
    ghost = tmp_path / "not-there-yet"
    binding = ws.register_binding(
        store, owner_id="u1", chat_id="c1", folder_path=str(ghost))
    assert binding.folder_path == str(ghost)
    assert not ghost.exists()  # binding created nothing


def test_register_refusals_store_nothing(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(ws.WorkspaceError):
        ws.register_binding(store, owner_id="u1", chat_id="c1",
                            folder_path="   ")
    with pytest.raises(ws.WorkspaceError):
        ws.register_binding(store, owner_id="u1", chat_id="",
                            folder_path=str(tmp_path))
    assert store.list_for_owner("u1") == []
    ws.register_binding(store, owner_id="u1", chat_id="c1",
                        folder_path=str(tmp_path))
    with pytest.raises(ws.WorkspaceError):
        ws.register_binding(store, owner_id="u1", chat_id="c1",
                            folder_path=str(tmp_path / "other"))
    assert len(store.list_for_owner("u1")) == 1


def test_same_folder_may_be_bound_by_several_chats(tmp_path):
    store = make_store(tmp_path)
    ws.register_binding(store, owner_id="u1", chat_id="c1",
                        folder_path=str(tmp_path))
    ws.register_binding(store, owner_id="u1", chat_id="c2",
                        folder_path=str(tmp_path))
    assert len(store.list_for_owner("u1")) == 2


def test_corrupt_store_reads_as_empty(tmp_path):
    store = make_store(tmp_path)
    store.index_path.parent.mkdir(parents=True, exist_ok=True)
    store.index_path.write_text("{not json")
    assert store.list_for_owner("u1") == []
    assert store.get_for_chat("c1") is None


def test_remove_and_purge_chat(tmp_path):
    store = make_store(tmp_path)
    one = ws.register_binding(store, owner_id="u1", chat_id="c1",
                              folder_path=str(tmp_path))
    ws.register_binding(store, owner_id="u1", chat_id="c2",
                        folder_path=str(tmp_path))
    assert store.remove_binding(one.id) == one
    assert store.remove_binding(one.id) is None
    assert store.purge_chat("c2") == 1
    assert store.purge_chat("c2") == 0
    assert store.list_for_owner("u1") == []


# ------------------------------------------------------ folder state


def test_folder_state_law(tmp_path):
    real = tmp_path / "dir"
    real.mkdir()
    assert ws.folder_state(str(real)) == ws.FOLDER_READY
    assert ws.folder_state(str(tmp_path / "gone")) == ws.FOLDER_MISSING
    a_file = tmp_path / "file.txt"
    a_file.write_text("x")
    assert ws.folder_state(str(a_file)) == ws.FOLDER_NOT_A_DIRECTORY
    assert ws.FOLDER_STATES == {
        "ready", "missing", "not_a_directory", "unreadable"}


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads anything")
def test_folder_state_unreadable(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        assert ws.folder_state(str(locked)) == ws.FOLDER_UNREADABLE
    finally:
        locked.chmod(0o755)


# ---------------------------------------------------------- documents


@pytest.mark.asyncio
async def test_resolve_states_and_document_shape(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, "someone-else")
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    folder = tmp_path / "bench"
    async with factory() as session:
        assert await ws.resolve_chat_workspace(
            session, store, uid, chat_id) is None  # unbound
        assert await ws.resolve_chat_workspace(
            session, store, uid, "no-such-chat") is None
        assert await ws.resolve_chat_workspace(
            session, store, other, chat_id) is None  # foreign
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(folder), label="bench")
    async with factory() as session:
        doc = await ws.resolve_chat_workspace(session, store, uid, chat_id)
    assert doc is not None
    assert doc["schema"] == "runmal-p169-workspace-binding-v1"
    assert doc["binding"]["folder_path"] == str(folder)
    assert doc["binding"]["label"] == "bench"
    assert doc["chat"] == {
        "id": chat_id, "title": "The Workshop", "character_id": None}
    assert doc["folder_state"] == "missing"  # judged live: not created
    assert len(doc["notes"]) == 5
    folder.mkdir()
    async with factory() as session:
        doc2 = await ws.resolve_chat_workspace(session, store, uid, chat_id)
    assert doc2["folder_state"] == "ready"  # live re-judgement, no store


@pytest.mark.asyncio
async def test_list_document_counts_and_orphans(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    ready_chat = await seed_chat(factory, uid, "Ready")
    missing_chat = await seed_chat(factory, uid, "Missing")
    store = make_store(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    ws.register_binding(store, owner_id=uid, chat_id=ready_chat,
                        folder_path=str(real))
    ws.register_binding(store, owner_id=uid, chat_id=missing_chat,
                        folder_path=str(tmp_path / "gone"))
    # An orphan: a binding whose chat never existed (store-level row).
    ws.register_binding(store, owner_id=uid, chat_id="ghost-chat",
                        folder_path=str(real))
    async with factory() as session:
        doc = await ws.list_owner_workspaces(session, store, uid)
    assert doc["schema"] == "runmal-p169-workspace-list-v1"
    assert doc["binding_count"] == 2
    assert doc["ready_count"] == 1
    assert doc["orphan_count"] == 1
    assert [row["chat"]["title"] for row in doc["workspaces"]] == [
        "Ready", "Missing"]


@pytest.mark.asyncio
async def test_binding_is_pure_data_folder_untouched(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    folder = tmp_path / "bench"
    folder.mkdir()
    marker = folder / "keep.txt"
    marker.write_text("mine")
    store = make_store(tmp_path)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(folder))
    async with factory() as session:
        await ws.resolve_chat_workspace(session, store, uid, chat_id)
        await ws.list_owner_workspaces(session, store, uid)
    assert marker.read_text() == "mine"
    assert [p.name for p in folder.iterdir()] == ["keep.txt"]


@pytest.mark.asyncio
async def test_chat_deletion_purges_the_binding(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(tmp_path))
    async with factory() as session:
        assert await chats_svc.delete_chat(session, uid, chat_id) is True
    assert store.get_for_chat(chat_id) is None


# --------------------------------------------------------------- HTTP


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


@pytest.mark.asyncio
async def test_http_bind_read_list_unbind(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    folder = tmp_path / "bench"
    folder.mkdir()
    made = client.post("/api/v1/workspaces/bindings", json={
        "chat_id": chat_id, "folder_path": str(folder), "label": "b"})
    assert made.status_code == 201, made.text
    doc = made.json()
    assert doc["folder_state"] == "ready"
    binding_id = doc["binding"]["id"]
    dupe = client.post("/api/v1/workspaces/bindings", json={
        "chat_id": chat_id, "folder_path": str(folder)})
    assert dupe.status_code == 422
    got = client.get("/api/v1/workspaces/bindings",
                     params={"chat_id": chat_id})
    assert got.status_code == 200 and got.json()["binding"]["id"] == binding_id
    listed = client.get("/api/v1/workspaces")
    assert listed.status_code == 200
    assert listed.json()["binding_count"] == 1
    gone = client.delete(f"/api/v1/workspaces/bindings/{binding_id}")
    assert gone.status_code == 200 and gone.json() == {
        "deleted": True, "id": binding_id}
    assert client.get("/api/v1/workspaces/bindings",
                      params={"chat_id": chat_id}).status_code == 404
    assert client.delete(
        f"/api/v1/workspaces/bindings/{binding_id}").status_code == 404


@pytest.mark.asyncio
async def test_http_scoping_and_missing_folder_state(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    assert client.post("/api/v1/workspaces/bindings", json={
        "chat_id": "no-such-chat",
        "folder_path": str(tmp_path)}).status_code == 404
    assert client.get("/api/v1/workspaces/bindings", params={
        "chat_id": "no-such-chat"}).status_code == 404
    unbound = client.get("/api/v1/workspaces/bindings",
                         params={"chat_id": chat_id})
    assert unbound.status_code == 404
    assert unbound.json()["detail"] == "workspace binding not found"
    made = client.post("/api/v1/workspaces/bindings", json={
        "chat_id": chat_id, "folder_path": str(tmp_path / "ghost")})
    assert made.status_code == 201
    assert made.json()["folder_state"] == "missing"  # state is data
    empty = client.post("/api/v1/workspaces/bindings", json={
        "chat_id": chat_id, "folder_path": "  "})
    assert empty.status_code == 422


# ---------------------------------------------------------- neighbours


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
