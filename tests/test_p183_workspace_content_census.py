"""P-183 - Workspace content census (Part XI, DERIVED).

Pins: the content census document (P-176's tree composed
verbatim at its own MAX_DEPTH ceiling and embedded
whole), every candidate file judged ONLY through P-172's
own read under its stated cap and counted under its
outcome (readable / binary / oversize / unreadable /
refused under P-172's closed law plus P-180's refused
name), the closed census law (folder_not_ready / empty /
no_files / none_readable / some_readable / all_readable),
the no-silent-omission arithmetic (files_considered ==
the sum of the outcome counts, every non-readable file
named in unreadable_files in tree order), the readable
axes (total readable bytes from the ok reads' own sizes,
the largest readable file - first wins on a tie in
depth-first order, readable extension counts from names
only), the no-content law (no content field, no excerpt
and no file bytes anywhere in the document - a known
secret string in a readable file never appears),
partiality honesty (truncated from the tree's own flag,
from any unexpanded directory or any refused expansion;
a non-ok outcome never sets it - every candidate was
judged and counted), non-ready folders as DATA (never
an error, never opened), the subpath law inherited from
P-170 through P-176, live re-judgement, owner scoping
(missing / foreign / unbound -> None, existence never
leaks), the pure-read law (the folder and the binding
store byte-identical after a census), the HTTP road
(GET /workspaces/content-census: two 404s kept apart,
refused subpath 422, every state DATA at 200), and the
neighbours (migration head stays 0041, no 0042). No
network.
"""

from __future__ import annotations

import json
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
from runmal.workspaces import content_census as cc
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
        return await cc.resolve_chat_content_census(
            session, store, uid, chat_id, subpath)


def mixed(folder):
    (folder / "notes.txt").write_bytes(b"hello world")
    (folder / "draft.MD").write_bytes(b"# Draft\n")
    (folder / "blob.bin").write_bytes(b"a\x00b")
    (folder / "raw.dat").write_bytes(b"\xff\xfe\x00\x01")
    sub = folder / "sub"
    sub.mkdir()
    (sub / "deep.txt").write_bytes(b"deep text here")
    (sub / "noext").write_bytes(b"plain")
    return sub


def assert_arithmetic(doc):
    total = (doc["readable_count"] + doc["binary_count"]
             + doc["oversize_count"] + doc["unreadable_count"]
             + doc["refused_count"] + doc["folder_not_ready_count"])
    assert doc["files_considered"] == total
    assert sum(doc["outcome_counts"].values()) == total
    assert len(doc["unreadable_files"]) == total - doc["readable_count"]


# ------------------------------------------------------------ document


@pytest.mark.asyncio
async def test_mixed_folder_document(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    mixed(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["schema"] == "runmal-p183-workspace-content-census-v1"
    assert doc["census_state"] == "some_readable"
    assert doc["census_state"] in cc.CONTENT_CENSUS_STATES
    assert doc["folder_state"] == "ready"
    assert doc["files_considered"] == 6
    assert doc["readable_count"] == 4
    assert doc["binary_count"] == 2
    assert doc["oversize_count"] == 0
    assert doc["unreadable_count"] == 0
    assert doc["refused_count"] == 0
    assert doc["folder_not_ready_count"] == 0
    assert doc["outcome_counts"]["ok"] == 4
    assert_arithmetic(doc)
    assert doc["max_content_bytes"] == ct.MAX_CONTENT_BYTES
    assert doc["max_depth"] == 4
    assert doc["tree_document"]["schema"].startswith("runmal-p176")
    assert doc["binding_document"]["binding"]["chat_id"] == chat_id
    assert len(doc["notes"]) == 6
    assert doc["truncated"] is False
    assert doc["coverage_complete"] is True


@pytest.mark.asyncio
async def test_unreadable_files_named_in_tree_order(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    mixed(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    named = doc["unreadable_files"]
    assert [row["path"] for row in named] == ["blob.bin", "raw.dat"]
    assert all(row["outcome"] == "binary" for row in named)
    assert named[0]["name"] == "blob.bin"
    assert named[0]["size_bytes"] == 3


@pytest.mark.asyncio
async def test_readable_axes(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    mixed(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    # readable bytes: 11 + 8 + 14 + 5 (readable files only)
    assert doc["total_readable_bytes"] == 38
    assert doc["readable_extension_counts"] == {
        "md": 1, "txt": 2, "(none)": 1}
    largest = doc["largest_readable_file"]
    assert largest == {"name": "deep.txt", "path": "sub/deep.txt",
                       "size_bytes": 14}


@pytest.mark.asyncio
async def test_largest_readable_tie_first_wins_and_binary_ignored(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "a.txt").write_bytes(b"12345678")
    (folder / "b.txt").write_bytes(b"abcdefgh")
    (folder / "big.bin").write_bytes(b"x\x00" + b"y" * 100)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["largest_readable_file"]["name"] == "a.txt"
    assert doc["total_readable_bytes"] == 16


@pytest.mark.asyncio
async def test_no_content_anywhere_in_document(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    secret = "the raven password is HUGINN-7741"
    (folder / "diary.txt").write_bytes(secret.encode())
    (folder / "other.txt").write_bytes(b"ordinary")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["readable_count"] == 2

    def keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keys(value)
        elif isinstance(node, list):
            for value in node:
                yield from keys(value)

    assert "content" not in set(keys(doc))
    assert "excerpt" not in set(keys(doc))
    assert secret not in json.dumps(doc)
    assert "HUGINN" not in json.dumps(doc)


@pytest.mark.asyncio
async def test_all_readable(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "one.txt").write_bytes(b"one")
    (folder / "two.md").write_bytes(b"two two")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["census_state"] == "all_readable"
    assert doc["unreadable_files"] == []
    assert_arithmetic(doc)


@pytest.mark.asyncio
async def test_none_readable(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "a.bin").write_bytes(b"\x00\x01")
    (folder / "b.bin").write_bytes(b"\xff\xff")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["census_state"] == "none_readable"
    assert doc["readable_count"] == 0
    assert doc["largest_readable_file"] is None
    assert doc["total_readable_bytes"] == 0
    assert doc["readable_extension_counts"] == {}
    assert_arithmetic(doc)


@pytest.mark.asyncio
async def test_oversize_file_is_named_not_readable(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "huge.txt").write_bytes(b"a" * (ct.MAX_CONTENT_BYTES + 1))
    (folder / "small.txt").write_bytes(b"small")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["oversize_count"] == 1
    assert doc["readable_count"] == 1
    named = doc["unreadable_files"]
    assert len(named) == 1
    assert named[0]["path"] == "huge.txt"
    assert named[0]["outcome"] == "oversize"
    assert doc["truncated"] is False  # judged and counted, not unseen
    assert_arithmetic(doc)


# -------------------------------------------------------------- states


@pytest.mark.asyncio
async def test_empty_folder_is_empty_state(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["census_state"] == "empty"
    assert doc["node_count"] == 0
    assert doc["files_considered"] == 0
    assert doc["largest_readable_file"] is None
    assert_arithmetic(doc)


@pytest.mark.asyncio
async def test_folder_with_only_directories_is_no_files(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "sub").mkdir()
    (folder / "sub" / "inner").mkdir()
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["census_state"] == "no_files"
    assert doc["node_count"] > 0
    assert doc["files_considered"] == 0
    assert_arithmetic(doc)


@pytest.mark.asyncio
async def test_missing_folder_is_data_not_error(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(tmp_path / "gone"))
    doc = await census(factory, store, uid, chat_id)
    assert doc["census_state"] == "folder_not_ready"
    assert doc["folder_state"] == "missing"
    assert doc["files_considered"] == 0
    assert doc["unreadable_files"] == []
    assert_arithmetic(doc)


@pytest.mark.asyncio
async def test_not_a_directory_folder_is_data(tmp_path):
    factory = make_factory(tmp_path)
    plain = tmp_path / "plain.txt"
    plain.write_bytes(b"not a folder")
    uid, chat_id, store = await bound(factory, tmp_path, plain)
    doc = await census(factory, store, uid, chat_id)
    assert doc["census_state"] == "folder_not_ready"
    assert doc["folder_state"] == "not_a_directory"
    assert doc["files_considered"] == 0


@pytest.mark.asyncio
async def test_symlinks_are_never_candidates(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "real.txt").write_bytes(b"real text")
    os.symlink(folder / "real.txt", folder / "link.txt")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["files_considered"] == 1
    assert doc["readable_count"] == 1
    assert doc["census_state"] == "all_readable"


@pytest.mark.asyncio
async def test_subpath_narrows_the_census(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    mixed(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "sub")
    assert doc["subpath"] == "sub"
    assert doc["files_considered"] == 2
    assert doc["census_state"] == "all_readable"
    with pytest.raises(ls.WorkspaceListingError):
        await census(factory, store, uid, chat_id, "../bench")


@pytest.mark.asyncio
async def test_truncated_below_depth_cap(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    level = folder
    for name in ("a", "b", "c", "d", "e"):
        level = level / name
        level.mkdir()
    (level / "deep.txt").write_bytes(b"too deep")
    (folder / "top.txt").write_bytes(b"top")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["truncated"] is True
    assert doc["coverage_complete"] is False
    paths = [row["path"] for row in doc["unreadable_files"]]
    assert "a/b/c/d/e/deep.txt" not in paths
    assert doc["files_considered"] == 1  # only top.txt was composed


# ---------------------------------------------------- scoping / purity


@pytest.mark.asyncio
async def test_owner_scoping_none_cases(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "x.txt").write_bytes(b"x")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    other = await make_user(factory, "someone-else")
    unbound_chat = await seed_chat(factory, uid, "Unbound")
    async with factory() as session:
        assert await cc.resolve_chat_content_census(
            session, store, uid, "no-such-chat") is None
        assert await cc.resolve_chat_content_census(
            session, store, other, chat_id) is None
        assert await cc.resolve_chat_content_census(
            session, store, uid, unbound_chat) is None


@pytest.mark.asyncio
async def test_census_is_a_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    mixed(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    store_bytes = (tmp_path / "data" / "workspaces.json").read_bytes()
    before = {str(p): p.read_bytes()
              for p in folder.rglob("*") if p.is_file()}
    await census(factory, store, uid, chat_id)
    assert (tmp_path / "data" / "workspaces.json").read_bytes() == store_bytes
    after = {str(p): p.read_bytes()
             for p in folder.rglob("*") if p.is_file()}
    assert before == after


@pytest.mark.asyncio
async def test_live_rejudgement(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "one.txt").write_bytes(b"one")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    first = await census(factory, store, uid, chat_id)
    assert first["files_considered"] == 1
    (folder / "two.bin").write_bytes(b"\x00")
    second = await census(factory, store, uid, chat_id)
    assert second["files_considered"] == 2
    assert second["binary_count"] == 1
    assert second["census_state"] == "some_readable"


# --------------------------------------------------------------- HTTP


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


@pytest.mark.asyncio
async def test_http_content_census_road(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    unbound_chat = await seed_chat(factory, uid, "Unbound")
    store = make_store(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    mixed(folder)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(folder))
    got = client.get("/api/v1/workspaces/content-census",
                     params={"chat_id": chat_id})
    assert got.status_code == 200, got.text
    doc = got.json()
    assert doc["schema"] == "runmal-p183-workspace-content-census-v1"
    assert doc["census_state"] == "some_readable"
    assert doc["files_considered"] == 6
    missing = client.get("/api/v1/workspaces/content-census",
                         params={"chat_id": "no-such-chat"})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "chat not found"
    unbound = client.get("/api/v1/workspaces/content-census",
                         params={"chat_id": unbound_chat})
    assert unbound.status_code == 404
    assert unbound.json()["detail"] == "workspace binding not found"
    refused = client.get("/api/v1/workspaces/content-census",
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
    got = client.get("/api/v1/workspaces/content-census",
                     params={"chat_id": chat_id})
    assert got.status_code == 200, got.text
    assert got.json()["census_state"] == "folder_not_ready"


# ---------------------------------------------------------- neighbours


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "mig.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
