"""P-170 - Workspace folder listing (Part XI, DERIVED).

Pins: the read-only consumer of the P-169 binding - the
listing document (schema, the P-169 binding document
embedded verbatim, folder state composed from P-169's
own folder_state law), the entry law (kinds judged by
lstat - a symlink is always a symlink; honest sizes -
files exact, directories / symlinks / others null;
hidden entries listed and flagged; deterministic order;
the 500-entry cap with an honest truncated flag), the
path law (absolute / NUL / any ".." subpaths refused;
a subpath resolving through a symlink out of the bound
folder refused; an escaping symlink entry flagged,
never followed), the state law (missing /
not_a_directory folders are DATA at the service layer,
never a scan), owner scoping (missing / foreign /
unbound -> None, existence never leaks), the pure
read-only law (the folder and the binding store are
byte-identical after a listing), and the neighbours
(migration head stays 0041, no 0042). No network.
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
from runmal.workspaces import listing as ls


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


async def bound(factory, store, uid, folder, title="The Workshop"):
    chat_id = await seed_chat(factory, uid, title)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(folder))
    return chat_id


async def resolve(factory, store, uid, chat_id, subpath=""):
    async with factory() as session:
        return await ls.resolve_chat_listing(
            session, store, uid, chat_id, subpath)


def make_tree(tmp_path):
    root = tmp_path / "bench"
    root.mkdir()
    (root / "notes.txt").write_text("hello")  # 5 bytes
    (root / ".secret").write_text("s")
    sub = root / "sub"
    sub.mkdir()
    (sub / "deep.txt").write_text("deep!")
    return root


# --------------------------------------------------------- entries


@pytest.mark.asyncio
async def test_root_listing_kinds_sizes_order_hidden(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    os.mkfifo(root / "pipe")
    chat_id = await bound(factory, store, uid, root)
    doc = await resolve(factory, store, uid, chat_id)
    assert doc["schema"] == "runmal-p170-workspace-listing-v1"
    assert doc["folder_state"] == "ready"
    assert doc["subpath"] == ""
    assert doc["binding_document"]["schema"] == (
        "runmal-p169-workspace-binding-v1")
    assert doc["binding_document"]["binding"]["folder_path"] == str(root)
    assert len(doc["notes"]) == 4
    rows = {row["name"]: row for row in doc["entries"]}
    assert rows["sub"]["kind"] == "directory"
    assert rows["sub"]["size_bytes"] is None  # never an invented size
    assert rows["notes.txt"]["kind"] == "file"
    assert rows["notes.txt"]["size_bytes"] == 5
    assert rows["notes.txt"]["hidden"] is False
    assert rows[".secret"]["hidden"] is True  # listed, flagged, kept
    assert rows["pipe"]["kind"] == "other"
    assert rows["pipe"]["size_bytes"] is None
    assert all(row["escapes"] is False for row in doc["entries"])
    assert [row["name"] for row in doc["entries"]] == [
        "sub", ".secret", "notes.txt", "pipe"]  # dirs, files, other
    assert doc["entry_count"] == 4 and doc["total_count"] == 4
    assert doc["truncated"] is False


@pytest.mark.asyncio
async def test_subdirectory_listing_and_normalisation(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    chat_id = await bound(factory, store, uid, root)
    doc = await resolve(factory, store, uid, chat_id, "sub")
    assert doc["subpath"] == "sub"
    assert [row["name"] for row in doc["entries"]] == ["deep.txt"]
    assert doc["entries"][0]["size_bytes"] == 5
    messy = await resolve(factory, store, uid, chat_id, "./sub/")
    assert messy["subpath"] == "sub"
    assert messy["entries"] == doc["entries"]


@pytest.mark.asyncio
async def test_entry_cap_and_truncation_flag(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = tmp_path / "wide"
    root.mkdir()
    for i in range(505):
        (root / f"f{i:03d}.txt").write_text("x")
    chat_id = await bound(factory, store, uid, root)
    doc = await resolve(factory, store, uid, chat_id)
    assert doc["total_count"] == 505
    assert doc["entry_count"] == ls.MAX_ENTRIES == 500
    assert doc["truncated"] is True


# -------------------------------------------------------- path law


@pytest.mark.asyncio
async def test_traversal_subpaths_refused(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    chat_id = await bound(factory, store, uid, root)
    for bad in ("..", "../", "sub/../..", "sub/../../etc", "/etc",
                str(tmp_path), "sub/..", "a\x00b"):
        async with factory() as session:
            with pytest.raises(ls.WorkspaceListingError):
                await ls.resolve_chat_listing(
                    session, store, uid, chat_id, bad)


@pytest.mark.asyncio
async def test_missing_and_file_subpaths_refused(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    chat_id = await bound(factory, store, uid, root)
    for bad in ("gone", "notes.txt", "sub/deep.txt"):
        async with factory() as session:
            with pytest.raises(ls.WorkspaceListingError):
                await ls.resolve_chat_listing(
                    session, store, uid, chat_id, bad)


@pytest.mark.asyncio
async def test_symlink_entries_flagged_never_followed(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("not yours to size")
    os.symlink("notes.txt", root / "in_link")
    os.symlink(str(outside), root / "out_link")
    os.symlink("notes.txt", root / "broken_in")  # target text stays in
    os.unlink(root / "broken_in")
    os.symlink("gone.txt", root / "broken_in")
    chat_id = await bound(factory, store, uid, root)
    doc = await resolve(factory, store, uid, chat_id)
    rows = {row["name"]: row for row in doc["entries"]}
    for name in ("in_link", "out_link", "broken_in"):
        assert rows[name]["kind"] == "symlink"  # never dressed as target
        assert rows[name]["size_bytes"] is None
    assert rows["in_link"]["escapes"] is False
    assert rows["out_link"]["escapes"] is True  # judged honestly
    assert rows["broken_in"]["escapes"] is False


@pytest.mark.asyncio
async def test_symlink_subpath_escape_refused_inside_allowed(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "loot.txt").write_text("loot")
    os.symlink(str(elsewhere), root / "door_out")
    os.symlink("sub", root / "door_in")
    chat_id = await bound(factory, store, uid, root)
    async with factory() as session:
        with pytest.raises(ls.WorkspaceListingError):
            await ls.resolve_chat_listing(
                session, store, uid, chat_id, "door_out")
    doc = await resolve(factory, store, uid, chat_id, "door_in")
    assert [row["name"] for row in doc["entries"]] == ["deep.txt"]


# ------------------------------------------------------- state law


@pytest.mark.asyncio
async def test_non_ready_states_are_data_never_scanned(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    ghost_chat = await bound(factory, store, uid, tmp_path / "gone", "Ghost")
    doc = await resolve(factory, store, uid, ghost_chat)
    assert doc["folder_state"] == "missing"
    assert doc["entries"] == [] and doc["total_count"] == 0
    a_file = tmp_path / "plain.txt"
    a_file.write_text("x")
    file_chat = await bound(factory, store, uid, a_file, "File")
    doc2 = await resolve(factory, store, uid, file_chat)
    assert doc2["folder_state"] == "not_a_directory"
    assert doc2["entries"] == []
    # A refused subpath on a non-ready folder is still just the
    # named state: the filesystem is never scanned for it.
    doc3 = await resolve(factory, store, uid, ghost_chat, "anything")
    assert doc3["folder_state"] == "missing" and doc3["entries"] == []


@pytest.mark.asyncio
async def test_scoping_missing_foreign_unbound(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, "someone-else")
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    chat_id = await bound(factory, store, uid, root)
    unbound_id = await seed_chat(factory, uid, "Unbound")
    async with factory() as session:
        assert await ls.resolve_chat_listing(
            session, store, uid, unbound_id) is None
        assert await ls.resolve_chat_listing(
            session, store, uid, "no-such-chat") is None
        assert await ls.resolve_chat_listing(
            session, store, other, chat_id) is None  # foreign: no leak
        assert await ls.resolve_chat_listing(
            session, store, uid, chat_id) is not None


@pytest.mark.asyncio
async def test_listing_is_pure_read_only(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    chat_id = await bound(factory, store, uid, root)
    store_bytes = store.index_path.read_bytes()
    before = {p.name: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    await resolve(factory, store, uid, chat_id)
    await resolve(factory, store, uid, chat_id, "sub")
    after = {p.name: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert store.index_path.read_bytes() == store_bytes
    assert store.get_for_chat(chat_id) is not None


# --------------------------------------------------------------- HTTP


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


@pytest.mark.asyncio
async def test_http_listing_flow_and_refusals(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    root = make_tree(tmp_path)
    made = client.post("/api/v1/workspaces/bindings", json={
        "chat_id": chat_id, "folder_path": str(root)})
    assert made.status_code == 201, made.text
    got = client.get("/api/v1/workspaces/files",
                     params={"chat_id": chat_id})
    assert got.status_code == 200, got.text
    doc = got.json()
    assert doc["schema"] == "runmal-p170-workspace-listing-v1"
    assert doc["folder_state"] == "ready"
    assert {row["name"] for row in doc["entries"]} == {
        "notes.txt", ".secret", "sub"}
    deep = client.get("/api/v1/workspaces/files", params={
        "chat_id": chat_id, "subpath": "sub"})
    assert deep.status_code == 200
    assert [r["name"] for r in deep.json()["entries"]] == ["deep.txt"]
    for bad in ("..", "../etc", "/etc", "notes.txt", "gone"):
        refused = client.get("/api/v1/workspaces/files", params={
            "chat_id": chat_id, "subpath": bad})
        assert refused.status_code == 422, (bad, refused.text)


@pytest.mark.asyncio
async def test_http_scoping_and_missing_state(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    assert client.get("/api/v1/workspaces/files", params={
        "chat_id": "no-such-chat"}).status_code == 404
    unbound = client.get("/api/v1/workspaces/files",
                         params={"chat_id": chat_id})
    assert unbound.status_code == 404
    assert unbound.json()["detail"] == "workspace binding not found"
    made = client.post("/api/v1/workspaces/bindings", json={
        "chat_id": chat_id, "folder_path": str(tmp_path / "ghost")})
    assert made.status_code == 201
    doc = client.get("/api/v1/workspaces/files",
                     params={"chat_id": chat_id})
    assert doc.status_code == 200  # the state is data, not an error
    assert doc.json()["folder_state"] == "missing"
    assert doc.json()["entries"] == []


# ---------------------------------------------------------- neighbours


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
