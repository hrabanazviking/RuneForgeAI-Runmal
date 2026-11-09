"""P-176 - Workspace folder tree (Part XI, DERIVED).

Pins: the tree document (P-170's root listing composed
verbatim and embedded whole, its binding document
carried), the node law (P-170's entry fields verbatim;
directories alone carry children/expanded; files,
symlinks and other kinds are leaves), the depth law
(max_depth counts expanded levels, root included;
default 2; closed range 1..4; a refused depth raises,
never clamps), the node cap (500, P-170's per-level cap
carried to the tree; a capped tree is truncated and
its unexpanded directories are named, never dressed
as empty), per-level truncation carried, symlinks
never descended (inside or escaping), a mid-walk
expansion refusal as DATA on the node (expand_refused)
while the root subpath's own refusal raises P-170's
error unchanged, non-ready folders as DATA (never an
error, never a scan), owner scoping (missing / foreign
/ unbound -> None, existence never leaks), live
re-judgement, the pure-read law (the folder and the
binding store are byte-identical after a tree), the
HTTP road (GET /workspaces/tree: two 404s kept apart,
refused subpath and refused depth at 422, every state
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
from runmal.workspaces import listing as ls
from runmal.workspaces import tree as tr


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


async def tree(factory, store, uid, chat_id, subpath="", max_depth=2):
    async with factory() as session:
        return await tr.resolve_chat_tree(
            session, store, uid, chat_id, subpath, max_depth)


def nested(folder):
    (folder / "top.txt").write_bytes(b"1")
    sub = folder / "sub"
    sub.mkdir()
    (sub / "mid.txt").write_bytes(b"22")
    deep = sub / "deep"
    deep.mkdir()
    (deep / "deep.txt").write_bytes(b"333")
    return sub, deep


def by_name(children):
    return {node["name"]: node for node in children}


# ------------------------------------------------------------ empty


@pytest.mark.asyncio
async def test_empty_folder_is_an_empty_expanded_root(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await tree(factory, store, uid, chat_id)
    assert doc["schema"] == "runmal-p176-workspace-tree-v1"
    assert doc["folder_state"] == "ready"
    assert doc["subpath"] == ""
    assert doc["max_depth"] == 2
    assert doc["truncated"] is False
    assert doc["node_count"] == 0
    root = doc["tree"]
    assert root["name"] == ""
    assert root["kind"] == "directory"
    assert root["expanded"] is True
    assert root["children"] == []
    assert len(doc["notes"]) == 5


# ------------------------------------------------------------- depth


@pytest.mark.asyncio
async def test_default_depth_expands_two_levels(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await tree(factory, store, uid, chat_id)
    assert doc["node_count"] == 4
    root_kids = by_name(doc["tree"]["children"])
    assert root_kids["top.txt"]["kind"] == "file"
    assert root_kids["top.txt"]["size_bytes"] == 1
    assert "children" not in root_kids["top.txt"]
    sub = root_kids["sub"]
    assert sub["expanded"] is True
    sub_kids = by_name(sub["children"])
    assert sub_kids["mid.txt"]["size_bytes"] == 2
    deep = sub_kids["deep"]
    assert deep["expanded"] is False
    assert deep["children"] is None
    assert "expand_refused" not in deep


@pytest.mark.asyncio
async def test_max_depth_one_and_three(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    one = await tree(factory, store, uid, chat_id, max_depth=1)
    assert one["node_count"] == 2
    sub = by_name(one["tree"]["children"])["sub"]
    assert sub["expanded"] is False
    assert sub["children"] is None
    three = await tree(factory, store, uid, chat_id, max_depth=3)
    assert three["node_count"] == 5
    deep = by_name(by_name(three["tree"]["children"])["sub"]["children"])["deep"]
    assert deep["expanded"] is True
    assert by_name(deep["children"])["deep.txt"]["size_bytes"] == 3


@pytest.mark.asyncio
async def test_max_depth_outside_the_closed_range_is_refused(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    for bad in (0, 5, -1):
        with pytest.raises(tr.WorkspaceTreeError):
            await tree(factory, store, uid, chat_id, max_depth=bad)
    assert tr.MAX_DEPTH == 4
    assert tr.DEFAULT_DEPTH == 2


# ---------------------------------------------------------- symlinks


@pytest.mark.asyncio
async def test_symlinks_are_leaves_never_descended(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    real = folder / "real"
    real.mkdir()
    (real / "inside.txt").write_bytes(b"x")
    os.symlink(real, folder / "link_in")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_bytes(b"y")
    os.symlink(outside, folder / "link_out")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await tree(factory, store, uid, chat_id, max_depth=4)
    kids = by_name(doc["tree"]["children"])
    assert kids["link_in"]["kind"] == "symlink"
    assert kids["link_in"]["escapes"] is False
    assert "children" not in kids["link_in"]
    assert kids["link_out"]["kind"] == "symlink"
    assert kids["link_out"]["escapes"] is True
    assert "children" not in kids["link_out"]
    assert kids["real"]["expanded"] is True
    assert doc["node_count"] == 4


# --------------------------------------------------------------- caps


@pytest.mark.asyncio
async def test_node_cap_truncates_and_names_unexpanded(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "MAX_NODES", 3)
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "top.txt").write_bytes(b"1")
    sub = folder / "sub"
    sub.mkdir()
    (sub / "a.txt").write_bytes(b"a")
    (sub / "b.txt").write_bytes(b"b")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await tree(factory, store, uid, chat_id)
    assert doc["truncated"] is True
    assert doc["node_count"] == 3
    sub_node = by_name(doc["tree"]["children"])["sub"]
    assert sub_node["expanded"] is True
    assert [n["name"] for n in sub_node["children"]] == ["a.txt"]


@pytest.mark.asyncio
async def test_a_truncated_level_is_carried(tmp_path, monkeypatch):
    monkeypatch.setattr(ls, "MAX_ENTRIES", 1)
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    (folder / "a.txt").write_bytes(b"a")
    (folder / "b.txt").write_bytes(b"b")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await tree(factory, store, uid, chat_id)
    assert doc["root_listing"]["truncated"] is True
    assert doc["truncated"] is True
    assert doc["node_count"] == 1


# ----------------------------------------------------- mid-walk race


def test_expand_refused_is_data_on_the_node(tmp_path):
    folder = tmp_path / "bench"
    folder.mkdir()
    root_listing = {
        "schema": ls.LISTING_SCHEMA,
        "binding_document": {"binding": {"folder_path": str(folder)}},
        "folder_state": "ready", "subpath": "", "total_count": 1,
        "entry_count": 1, "truncated": False,
        "entries": [
            {"name": "ghost", "kind": "directory", "size_bytes": None,
             "hidden": False, "escapes": False}],
        "notes": []}
    doc = tr.build_tree(root_listing, 2)
    node = doc["tree"]["children"][0]
    assert node["name"] == "ghost"
    assert node["expanded"] is False
    assert node["children"] is None
    assert node["expand_refused"] is True
    assert doc["node_count"] == 1


# --------------------------------------------------------- not ready


@pytest.mark.asyncio
async def test_missing_folder_is_data_never_an_error(tmp_path):
    factory = make_factory(tmp_path)
    uid, chat_id, store = await bound(factory, tmp_path, tmp_path / "gone")
    doc = await tree(factory, store, uid, chat_id)
    assert doc["folder_state"] == "missing"
    assert doc["tree"]["expanded"] is False
    assert doc["tree"]["children"] is None
    assert doc["node_count"] == 0
    assert doc["truncated"] is False


@pytest.mark.asyncio
async def test_file_bound_as_folder_is_data(tmp_path):
    factory = make_factory(tmp_path)
    not_a_dir = tmp_path / "plain.txt"
    not_a_dir.write_bytes(b"x")
    uid, chat_id, store = await bound(factory, tmp_path, not_a_dir)
    doc = await tree(factory, store, uid, chat_id)
    assert doc["folder_state"] == "not_a_directory"
    assert doc["tree"]["children"] is None
    assert doc["node_count"] == 0


# ------------------------------------------------------------ subpath


@pytest.mark.asyncio
async def test_subpath_tree_and_root_refusal(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await tree(factory, store, uid, chat_id, subpath="sub")
    assert doc["subpath"] == "sub"
    assert doc["tree"]["name"] == "sub"
    kids = by_name(doc["tree"]["children"])
    assert kids["mid.txt"]["size_bytes"] == 2
    assert doc["node_count"] == 3
    with pytest.raises(ls.WorkspaceListingError):
        await tree(factory, store, uid, chat_id, subpath="../bench")


# ---------------------------------------------------- verbatim + None


@pytest.mark.asyncio
async def test_root_listing_is_composed_verbatim(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await tree(factory, store, uid, chat_id)
    async with factory() as session:
        listing_doc = await ls.resolve_chat_listing(
            session, store, uid, chat_id)
    assert doc["root_listing"] == listing_doc
    assert doc["binding_document"] == listing_doc["binding_document"]
    assert doc["folder_state"] == listing_doc["folder_state"]
    assert doc["subpath"] == listing_doc["subpath"]
    root_names = [n["name"] for n in doc["tree"]["children"]]
    assert root_names == [e["name"] for e in listing_doc["entries"]]


@pytest.mark.asyncio
async def test_missing_foreign_and_unbound_chats_are_none(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    other = await make_user(factory, "someone-else")
    unbound_chat = await seed_chat(factory, uid, "Unbound")
    assert await tree(factory, store, uid, "no-such-chat") is None
    assert await tree(factory, store, other, chat_id) is None
    assert await tree(factory, store, uid, unbound_chat) is None


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
    first = await tree(factory, store, uid, chat_id)
    assert first["node_count"] == 1
    sub = folder / "newdir"
    sub.mkdir()
    (sub / "new.md").write_bytes(b"123456")
    second = await tree(factory, store, uid, chat_id)
    assert second["node_count"] == 3
    newdir = by_name(second["tree"]["children"])["newdir"]
    assert newdir["expanded"] is True
    assert keep.read_bytes() == b"mine"
    assert store.index_path.read_bytes() == store_bytes
    third = await tree(factory, store, uid, chat_id)
    assert third == second


# --------------------------------------------------------------- HTTP


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


@pytest.mark.asyncio
async def test_http_tree_road(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    unbound_chat = await seed_chat(factory, uid, "Unbound")
    store = make_store(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    nested(folder)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(folder))
    got = client.get("/api/v1/workspaces/tree",
                     params={"chat_id": chat_id})
    assert got.status_code == 200, got.text
    doc = got.json()
    assert doc["schema"] == "runmal-p176-workspace-tree-v1"
    assert doc["node_count"] == 4
    shallow = client.get("/api/v1/workspaces/tree",
                         params={"chat_id": chat_id, "max_depth": 1})
    assert shallow.status_code == 200, shallow.text
    assert shallow.json()["node_count"] == 2
    missing = client.get("/api/v1/workspaces/tree",
                         params={"chat_id": "no-such-chat"})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "chat not found"
    unbound = client.get("/api/v1/workspaces/tree",
                         params={"chat_id": unbound_chat})
    assert unbound.status_code == 404
    assert unbound.json()["detail"] == "workspace binding not found"
    refused_path = client.get("/api/v1/workspaces/tree",
                              params={"chat_id": chat_id,
                                      "subpath": "../bench"})
    assert refused_path.status_code == 422
    refused_depth = client.get("/api/v1/workspaces/tree",
                               params={"chat_id": chat_id,
                                       "max_depth": 9})
    assert refused_depth.status_code == 422


@pytest.mark.asyncio
async def test_http_not_ready_folder_is_data_at_200(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(tmp_path / "gone"))
    got = client.get("/api/v1/workspaces/tree",
                     params={"chat_id": chat_id})
    assert got.status_code == 200, got.text
    assert got.json()["folder_state"] == "missing"
    assert got.json()["tree"]["children"] is None


# ---------------------------------------------------------- neighbours


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
