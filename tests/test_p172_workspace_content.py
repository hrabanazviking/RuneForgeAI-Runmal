"""P-172 - Workspace file content read (Part XI, DERIVED).

Pins: the read-only content consumer of the P-169
binding - the content document (schema, the P-169
binding document embedded verbatim, folder state
composed from P-169's own folder_state law), the
outcome law (ok / folder_not_ready / binary / oversize
/ unreadable as DATA, never a crash and never dressed
as ok), the honesty law (text is strict UTF-8 with no
NUL under MAX_CONTENT_BYTES; an oversize body is never
read; content is never truncated or decoded with
replacements), the path law re-judged at use (empty /
absolute / NUL / any ".." paths refused; a path
resolving through a symlink out of the bound folder
refused; a symlink final component refused, never
followed; missing / directory / non-regular refused by
name), the state law (missing / not_a_directory folders
are DATA at the service layer, never opened), owner
scoping (missing / foreign / unbound -> None,
existence never leaks), the pure read-only law (the
folder and the binding store are byte-identical after
a read), and the neighbours (migration head stays
0041, no 0042). No network.
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
from runmal.workspaces import content as ct


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


async def resolve(factory, store, uid, chat_id, path=""):
    async with factory() as session:
        return await ct.resolve_chat_content(
            session, store, uid, chat_id, path)


def make_tree(tmp_path):
    root = tmp_path / "bench"
    root.mkdir()
    (root / "notes.txt").write_text("hello")  # 5 bytes
    (root / "empty.txt").write_text("")
    sub = root / "sub"
    sub.mkdir()
    (sub / "deep.txt").write_text("deep!")
    return root


# ------------------------------------------------------------ reads


@pytest.mark.asyncio
async def test_text_read_ok_root_subdir_and_empty(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    chat_id = await bound(factory, store, uid, root)
    doc = await resolve(factory, store, uid, chat_id, "notes.txt")
    assert doc["schema"] == "runmal-p172-workspace-content-v1"
    assert doc["folder_state"] == "ready"
    assert doc["path"] == "notes.txt"
    assert doc["outcome"] == "ok"
    assert doc["content"] == "hello"
    assert doc["size_bytes"] == 5
    assert doc["max_bytes"] == ct.MAX_CONTENT_BYTES == 262144
    assert doc["binding_document"]["schema"] == (
        "runmal-p169-workspace-binding-v1")
    assert doc["binding_document"]["binding"]["folder_path"] == str(root)
    assert len(doc["notes"]) == 4
    assert ct.OUTCOMES == {"ok", "folder_not_ready", "binary",
                           "oversize", "unreadable"}
    deep = await resolve(factory, store, uid, chat_id, "sub/deep.txt")
    assert deep["content"] == "deep!" and deep["outcome"] == "ok"
    empty = await resolve(factory, store, uid, chat_id, "empty.txt")
    assert empty["outcome"] == "ok" and empty["content"] == ""
    assert empty["size_bytes"] == 0


@pytest.mark.asyncio
async def test_unicode_text_and_normalisation(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    (root / "rune.txt").write_text("\u16a6 wyrd \u00fe\u00f0", encoding="utf-8")
    chat_id = await bound(factory, store, uid, root)
    doc = await resolve(factory, store, uid, chat_id, "rune.txt")
    assert doc["outcome"] == "ok"
    assert doc["content"] == "\u16a6 wyrd \u00fe\u00f0"
    messy = await resolve(factory, store, uid, chat_id, "./sub//deep.txt")
    assert messy["path"] == "sub/deep.txt"
    assert messy["content"] == "deep!"


@pytest.mark.asyncio
async def test_exact_cap_is_ok(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    (root / "cap.txt").write_text("x" * ct.MAX_CONTENT_BYTES)
    chat_id = await bound(factory, store, uid, root)
    doc = await resolve(factory, store, uid, chat_id, "cap.txt")
    assert doc["outcome"] == "ok"
    assert doc["size_bytes"] == ct.MAX_CONTENT_BYTES
    assert len(doc["content"]) == ct.MAX_CONTENT_BYTES


# --------------------------------------------------------- outcomes


@pytest.mark.asyncio
async def test_binary_outcomes_never_dumped_as_text(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    (root / "nul.bin").write_bytes(b"ab\x00cd")
    (root / "latin.bin").write_bytes("caf\u00e9".encode("latin-1"))
    chat_id = await bound(factory, store, uid, root)
    for name, size in (("nul.bin", 5), ("latin.bin", 4)):
        doc = await resolve(factory, store, uid, chat_id, name)
        assert doc["outcome"] == "binary", name
        assert doc["content"] is None
        assert doc["size_bytes"] == size


@pytest.mark.asyncio
async def test_oversize_outcome_body_never_claimed(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    big = root / "big.txt"
    big.write_text("y" * (ct.MAX_CONTENT_BYTES + 1))
    chat_id = await bound(factory, store, uid, root)
    doc = await resolve(factory, store, uid, chat_id, "big.txt")
    assert doc["outcome"] == "oversize"
    assert doc["content"] is None  # never truncated into a claim
    assert doc["size_bytes"] == ct.MAX_CONTENT_BYTES + 1


@pytest.mark.asyncio
@pytest.mark.skipif(os.geteuid() == 0, reason="root reads past mode 0")
async def test_unreadable_outcome_is_data(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    locked = root / "locked.txt"
    locked.write_text("sealed")
    locked.chmod(0)
    chat_id = await bound(factory, store, uid, root)
    try:
        doc = await resolve(factory, store, uid, chat_id, "locked.txt")
    finally:
        locked.chmod(0o644)
    assert doc["outcome"] == "unreadable"
    assert doc["content"] is None


# ---------------------------------------------------------- path law


@pytest.mark.asyncio
async def test_traversal_absolute_and_empty_refused(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    chat_id = await bound(factory, store, uid, root)
    for bad in ("", ".", "..", "../notes.txt", "sub/../../etc/passwd",
                "/etc/passwd", str(root / "notes.txt"), "a\x00b"):
        async with factory() as session:
            with pytest.raises(ct.WorkspaceContentError):
                await ct.resolve_chat_content(
                    session, store, uid, chat_id, bad)


@pytest.mark.asyncio
async def test_missing_directory_and_nonregular_refused(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    os.mkfifo(root / "pipe")
    chat_id = await bound(factory, store, uid, root)
    for bad in ("gone.txt", "sub", "sub/", "pipe"):
        async with factory() as session:
            with pytest.raises(ct.WorkspaceContentError):
                await ct.resolve_chat_content(
                    session, store, uid, chat_id, bad)


@pytest.mark.asyncio
async def test_symlink_never_followed_for_content(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("not yours")
    os.symlink("notes.txt", root / "in_link")
    os.symlink(str(outside), root / "out_link")
    chat_id = await bound(factory, store, uid, root)
    for bad in ("in_link", "out_link"):
        async with factory() as session:
            with pytest.raises(ct.WorkspaceContentError):
                await ct.resolve_chat_content(
                    session, store, uid, chat_id, bad)


@pytest.mark.asyncio
async def test_symlink_dir_escape_refused_inside_allowed(tmp_path):
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
        with pytest.raises(ct.WorkspaceContentError):
            await ct.resolve_chat_content(
                session, store, uid, chat_id, "door_out/loot.txt")
    doc = await resolve(factory, store, uid, chat_id, "door_in/deep.txt")
    assert doc["outcome"] == "ok" and doc["content"] == "deep!"


# --------------------------------------------------------- state law


@pytest.mark.asyncio
async def test_non_ready_states_are_data_never_opened(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    ghost_chat = await bound(factory, store, uid, tmp_path / "gone", "Ghost")
    doc = await resolve(factory, store, uid, ghost_chat, "notes.txt")
    assert doc["folder_state"] == "missing"
    assert doc["outcome"] == "folder_not_ready"
    assert doc["content"] is None and doc["size_bytes"] is None
    a_file = tmp_path / "plain.txt"
    a_file.write_text("x")
    file_chat = await bound(factory, store, uid, a_file, "File")
    doc2 = await resolve(factory, store, uid, file_chat, "notes.txt")
    assert doc2["folder_state"] == "not_a_directory"
    assert doc2["outcome"] == "folder_not_ready"


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
        assert await ct.resolve_chat_content(
            session, store, uid, unbound_id, "notes.txt") is None
        assert await ct.resolve_chat_content(
            session, store, uid, "no-such-chat", "notes.txt") is None
        assert await ct.resolve_chat_content(
            session, store, other, chat_id, "notes.txt") is None
        assert await ct.resolve_chat_content(
            session, store, uid, chat_id, "notes.txt") is not None


@pytest.mark.asyncio
async def test_read_is_pure_read_only(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    root = make_tree(tmp_path)
    chat_id = await bound(factory, store, uid, root)
    store_bytes = store.index_path.read_bytes()
    before = {p.name: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    await resolve(factory, store, uid, chat_id, "notes.txt")
    await resolve(factory, store, uid, chat_id, "sub/deep.txt")
    after = {p.name: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert store.index_path.read_bytes() == store_bytes


# --------------------------------------------------------------- HTTP


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


@pytest.mark.asyncio
async def test_http_content_flow_outcomes_and_refusals(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    root = make_tree(tmp_path)
    (root / "blob.bin").write_bytes(b"a\x00b")
    made = client.post("/api/v1/workspaces/bindings", json={
        "chat_id": chat_id, "folder_path": str(root)})
    assert made.status_code == 201, made.text
    got = client.get("/api/v1/workspaces/content", params={
        "chat_id": chat_id, "path": "notes.txt"})
    assert got.status_code == 200, got.text
    doc = got.json()
    assert doc["schema"] == "runmal-p172-workspace-content-v1"
    assert doc["outcome"] == "ok" and doc["content"] == "hello"
    blob = client.get("/api/v1/workspaces/content", params={
        "chat_id": chat_id, "path": "blob.bin"})
    assert blob.status_code == 200  # the outcome is data, not an error
    assert blob.json()["outcome"] == "binary"
    assert blob.json()["content"] is None
    for bad in ("..", "../etc/passwd", "/etc/passwd", "sub",
                "gone.txt", ""):
        refused = client.get("/api/v1/workspaces/content", params={
            "chat_id": chat_id, "path": bad})
        assert refused.status_code == 422, (bad, refused.text)


@pytest.mark.asyncio
async def test_http_scoping_and_missing_state(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    assert client.get("/api/v1/workspaces/content", params={
        "chat_id": "no-such-chat", "path": "x.txt"}).status_code == 404
    unbound = client.get("/api/v1/workspaces/content", params={
        "chat_id": chat_id, "path": "x.txt"})
    assert unbound.status_code == 404
    assert unbound.json()["detail"] == "workspace binding not found"
    made = client.post("/api/v1/workspaces/bindings", json={
        "chat_id": chat_id, "folder_path": str(tmp_path / "ghost")})
    assert made.status_code == 201
    doc = client.get("/api/v1/workspaces/content", params={
        "chat_id": chat_id, "path": "x.txt"})
    assert doc.status_code == 200  # the state is data, not an error
    assert doc.json()["folder_state"] == "missing"
    assert doc.json()["outcome"] == "folder_not_ready"


# ---------------------------------------------------------- neighbours


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
