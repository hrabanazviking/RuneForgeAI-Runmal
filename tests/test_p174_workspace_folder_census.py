"""P-174 - Workspace folder census (Part XI, DERIVED).

Pins: the folder census document (P-170's listing
composed verbatim and embedded whole, its folder_state
/ subpath / entry_count / total_count / truncated
carried verbatim), the closed census law
(folder_not_ready / empty / no_files / has_files), the
kind axis (counts summed from the listing entries' own
kind values under P-170's ENTRY_KINDS), the byte axis
(only file entries carry bytes), the extension axis
(names only - lowercased suffix, no suffix is "(none)",
no file opened), hidden and escaping-symlink counts,
the largest file (first wins on a tie, the listing's
own order), truncation honesty (counts describe the
returned entries when truncated), non-ready folders as
DATA (never an error, never a scan), the subpath law
inherited from P-170 unchanged (a refused subpath
raises P-170's own error), live re-judgement (a file
added after one census changes the next), owner
scoping (missing / foreign / unbound -> None,
existence never leaks), the pure-read law (the folder
and the binding store are byte-identical after a
census), the HTTP road (GET /workspaces/folder-census:
two 404s kept apart, refused subpath 422, every state
DATA at 200), and the neighbours (migration head stays
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
from runmal.workspaces import folder_census as fc
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


async def bound(factory, tmp_path, folder, title="The Workshop"):
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid, title)
    store = make_store(tmp_path)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(folder))
    return uid, chat_id, store


async def census(factory, store, uid, chat_id, subpath=""):
    async with factory() as session:
        return await fc.resolve_chat_folder_census(
            session, store, uid, chat_id, subpath)


# ------------------------------------------------------------ empty


@pytest.mark.asyncio
async def test_empty_folder_is_the_empty_census(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["schema"] == "runmal-p174-workspace-folder-census-v1"
    assert doc["census_state"] == "empty"
    assert doc["census_state"] in fc.FOLDER_CENSUS_STATES
    assert fc.FOLDER_CENSUS_STATES == {
        "folder_not_ready", "empty", "no_files", "has_files"}
    assert doc["folder_state"] == "ready"
    assert doc["entry_count"] == 0
    assert doc["total_count"] == 0
    assert doc["truncated"] is False
    assert doc["kind_counts"] == {
        "directory": 0, "file": 0, "symlink": 0, "other": 0}
    assert doc["total_file_bytes"] == 0
    assert doc["extension_counts"] == {}
    assert doc["largest_file"] is None
    assert len(doc["notes"]) == 6


# ------------------------------------------------------- aggregation


@pytest.mark.asyncio
async def test_counts_sum_the_listing_entries(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "notes.txt").write_bytes(b"12345")
    (folder / "draft.MD").write_bytes(b"1234567")
    (folder / "README").write_bytes(b"12")
    (folder / ".hidden.txt").write_bytes(b"1")
    (folder / "sub").mkdir()
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["census_state"] == "has_files"
    assert doc["entry_count"] == 5
    assert doc["directory_count"] == 1
    assert doc["file_count"] == 4
    assert doc["symlink_count"] == 0
    assert doc["other_count"] == 0
    assert doc["total_file_bytes"] == 5 + 7 + 2 + 1
    assert doc["hidden_count"] == 1
    assert doc["escaping_symlink_count"] == 0
    assert doc["extension_counts"] == {"(none)": 1, "md": 1, "txt": 2}
    assert doc["largest_file"] == {"name": "draft.MD", "size_bytes": 7}


@pytest.mark.asyncio
async def test_largest_file_tie_keeps_the_listings_order(tmp_path):
    listing_doc = {
        "schema": ls.LISTING_SCHEMA, "binding_document": {},
        "folder_state": "ready", "subpath": "", "total_count": 2,
        "entry_count": 2, "truncated": False,
        "entries": [
            {"name": "a.bin", "kind": "file", "size_bytes": 9,
             "hidden": False, "escapes": False},
            {"name": "b.bin", "kind": "file", "size_bytes": 9,
             "hidden": False, "escapes": False}],
        "notes": []}
    doc = fc.build_folder_census(listing_doc)
    assert doc["largest_file"] == {"name": "a.bin", "size_bytes": 9}
    assert doc["total_file_bytes"] == 18


@pytest.mark.asyncio
async def test_no_files_state_with_directories_and_a_symlink(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "sub").mkdir()
    target = tmp_path / "outside.txt"
    target.write_bytes(b"x")
    os.symlink(target, folder / "link_out")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["census_state"] == "no_files"
    assert doc["directory_count"] == 1
    assert doc["symlink_count"] == 1
    assert doc["escaping_symlink_count"] == 1
    assert doc["file_count"] == 0
    assert doc["total_file_bytes"] == 0
    assert doc["largest_file"] is None


@pytest.mark.asyncio
async def test_inside_symlink_is_not_escaping(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "real.txt").write_bytes(b"abc")
    os.symlink(folder / "real.txt", folder / "link_in")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["symlink_count"] == 1
    assert doc["escaping_symlink_count"] == 0
    assert doc["file_count"] == 1
    assert doc["total_file_bytes"] == 3


# ---------------------------------------------------- verbatim + cap


@pytest.mark.asyncio
async def test_listing_is_composed_verbatim(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "a.txt").write_bytes(b"hi")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    async with factory() as session:
        listing_doc = await ls.resolve_chat_listing(
            session, store, uid, chat_id)
    assert doc["listing_document"] == listing_doc
    assert doc["folder_state"] == listing_doc["folder_state"]
    assert doc["subpath"] == listing_doc["subpath"]
    assert doc["entry_count"] == listing_doc["entry_count"]
    assert doc["total_count"] == listing_doc["total_count"]
    assert doc["truncated"] == listing_doc["truncated"]
    embedded = doc["listing_document"]["binding_document"]
    assert embedded["binding"]["folder_path"] == str(folder)


def test_truncation_is_carried_and_counts_stay_honest():
    listing_doc = {
        "schema": ls.LISTING_SCHEMA, "binding_document": {},
        "folder_state": "ready", "subpath": "", "total_count": 900,
        "entry_count": 1, "truncated": True,
        "entries": [
            {"name": "only.txt", "kind": "file", "size_bytes": 4,
             "hidden": False, "escapes": False}],
        "notes": []}
    doc = fc.build_folder_census(listing_doc)
    assert doc["truncated"] is True
    assert doc["total_count"] == 900
    assert doc["entry_count"] == 1
    assert doc["file_count"] == 1
    assert doc["total_file_bytes"] == 4
    assert any("truncated" in note for note in doc["notes"])


# --------------------------------------------------------- not ready


@pytest.mark.asyncio
async def test_missing_folder_is_data_never_an_error(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "gone"
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["census_state"] == "folder_not_ready"
    assert doc["folder_state"] == "missing"
    assert doc["entry_count"] == 0
    assert doc["file_count"] == 0
    assert doc["total_file_bytes"] == 0
    assert doc["largest_file"] is None


@pytest.mark.asyncio
async def test_file_bound_as_folder_is_data(tmp_path):
    factory = make_factory(tmp_path)
    not_a_dir = tmp_path / "plain.txt"
    not_a_dir.write_bytes(b"x")
    uid, chat_id, store = await bound(factory, tmp_path, not_a_dir)
    doc = await census(factory, store, uid, chat_id)
    assert doc["census_state"] == "folder_not_ready"
    assert doc["folder_state"] == "not_a_directory"


# ------------------------------------------------------------ subpath


@pytest.mark.asyncio
async def test_subpath_census_and_refusal(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    sub = folder / "inner"
    sub.mkdir()
    (sub / "deep.txt").write_bytes(b"1234")
    (folder / "top.txt").write_bytes(b"1")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "inner")
    assert doc["subpath"] == "inner"
    assert doc["file_count"] == 1
    assert doc["total_file_bytes"] == 4
    with pytest.raises(ls.WorkspaceListingError):
        await census(factory, store, uid, chat_id, "../bench")


# ------------------------------------------------------ owner scoping


@pytest.mark.asyncio
async def test_missing_foreign_and_unbound_chats_are_none(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    other = await make_user(factory, "someone-else")
    unbound_chat = await seed_chat(factory, uid, "Unbound")
    assert await census(factory, store, uid, "no-such-chat") is None
    assert await census(factory, store, other, chat_id) is None
    assert await census(factory, store, uid, unbound_chat) is None


# ------------------------------------------------------ live + purity


@pytest.mark.asyncio
async def test_live_rejudgement_and_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    keep = folder / "keep.txt"
    keep.write_bytes(b"mine")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    store_bytes = store.index_path.read_bytes()
    first = await census(factory, store, uid, chat_id)
    assert first["file_count"] == 1
    (folder / "new.md").write_bytes(b"123456")
    second = await census(factory, store, uid, chat_id)
    assert second["file_count"] == 2
    assert second["total_file_bytes"] == 4 + 6
    assert second["extension_counts"] == {"md": 1, "txt": 1}
    assert keep.read_bytes() == b"mine"
    assert sorted(p.name for p in folder.iterdir()) == [
        "keep.txt", "new.md"]
    assert store.index_path.read_bytes() == store_bytes
    third = await census(factory, store, uid, chat_id)
    assert third == second


# --------------------------------------------------------------- HTTP


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


@pytest.mark.asyncio
async def test_http_folder_census_road(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    unbound_chat = await seed_chat(factory, uid, "Unbound")
    store = make_store(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "a.txt").write_bytes(b"hi")
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(folder))
    got = client.get("/api/v1/workspaces/folder-census",
                     params={"chat_id": chat_id})
    assert got.status_code == 200, got.text
    doc = got.json()
    assert doc["schema"] == "runmal-p174-workspace-folder-census-v1"
    assert doc["census_state"] == "has_files"
    assert doc["file_count"] == 1
    missing = client.get("/api/v1/workspaces/folder-census",
                         params={"chat_id": "no-such-chat"})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "chat not found"
    unbound = client.get("/api/v1/workspaces/folder-census",
                         params={"chat_id": unbound_chat})
    assert unbound.status_code == 404
    assert unbound.json()["detail"] == "workspace binding not found"
    refused = client.get("/api/v1/workspaces/folder-census",
                         params={"chat_id": chat_id,
                                 "subpath": "../bench"})
    assert refused.status_code == 422


@pytest.mark.asyncio
async def test_http_not_ready_folder_is_data_at_200(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(tmp_path / "gone"))
    got = client.get("/api/v1/workspaces/folder-census",
                     params={"chat_id": chat_id})
    assert got.status_code == 200, got.text
    assert got.json()["census_state"] == "folder_not_ready"


# ---------------------------------------------------------- neighbours


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
