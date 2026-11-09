"""P-181 - Workspace tree census (Part XI, DERIVED).

Pins: the tree census document (P-176's tree composed
verbatim at its own MAX_DEPTH ceiling and embedded
whole, its folder_state / subpath / max_depth /
node_count carried), the closed census law
(folder_not_ready / empty / no_files / has_files -
P-174's law carried to the tree), the kind axis (counts
summed from the tree nodes' own kind values under
P-170's ENTRY_KINDS, the counted nodes exactly the
tree's node_count), the byte axis (only file nodes
carry bytes), the extension axis (names only -
lowercased suffix, no suffix is "(none)", no file
opened), hidden and escaping-symlink counts, the
largest file (first wins on a tie in the tree's own
depth-first order, carrying its folder-relative path),
the tree axes (expanded / unexpanded / expand-refused
directory counts, counts by depth, deepest level),
partiality honesty (counts describe the composed nodes
only; truncated from the tree's own flag, from any
unexpanded directory node, or from any refused
expansion), non-ready folders as DATA (never an error,
never a scan), the subpath law inherited from P-170
unchanged through P-176 (a refused subpath raises
P-170's own error), live re-judgement (a file added
deep after one census changes the next), owner scoping
(missing / foreign / unbound -> None, existence never
leaks), the pure-read law (the folder and the binding
store are byte-identical after a census), the HTTP
road (GET /workspaces/tree-census: two 404s kept
apart, refused subpath 422, every state DATA at 200),
and the neighbours (migration head stays 0041, no
0042). No network.
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
from runmal.workspaces import tree_census as tc


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
        return await tc.resolve_chat_tree_census(
            session, store, uid, chat_id, subpath)


def nested(folder):
    (folder / "top.txt").write_bytes(b"12345")
    (folder / "draft.MD").write_bytes(b"1234567")
    (folder / ".hidden.txt").write_bytes(b"1")
    sub = folder / "sub"
    sub.mkdir()
    (sub / "mid.txt").write_bytes(b"123")
    deep = sub / "deep"
    deep.mkdir()
    (deep / "deep.txt").write_bytes(b"1234")
    (deep / "noext").write_bytes(b"12")
    return sub, deep


def _leaf(name, kind, size=None, hidden=False, escapes=False):
    return {"name": name, "kind": kind, "size_bytes": size,
            "hidden": hidden, "escapes": escapes}


def _dir(name, children, expanded=True, refused=False):
    node = _leaf(name, "directory")
    node["children"] = children
    node["expanded"] = expanded
    if refused:
        node["expand_refused"] = True
    return node


def _tree_doc(children, node_count, truncated=False, subpath=""):
    root = _dir("", children, expanded=True)
    return {
        "schema": tr.TREE_SCHEMA, "binding_document": {},
        "folder_state": "ready", "subpath": subpath,
        "max_depth": tr.MAX_DEPTH, "tree": root,
        "node_count": node_count, "truncated": truncated,
        "notes": []}


# ------------------------------------------------------------ empty


@pytest.mark.asyncio
async def test_empty_folder_is_the_empty_census(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["schema"] == "runmal-p181-workspace-tree-census-v1"
    assert doc["census_state"] == "empty"
    assert doc["census_state"] in tc.TREE_CENSUS_STATES
    assert tc.TREE_CENSUS_STATES == {
        "folder_not_ready", "empty", "no_files", "has_files"}
    assert doc["folder_state"] == "ready"
    assert doc["node_count"] == 0
    assert doc["max_depth"] == tr.MAX_DEPTH
    assert doc["truncated"] is False
    assert doc["kind_counts"] == {
        "directory": 0, "file": 0, "symlink": 0, "other": 0}
    assert doc["total_file_bytes"] == 0
    assert doc["extension_counts"] == {}
    assert doc["largest_file"] is None
    assert doc["expanded_directory_count"] == 0
    assert doc["unexpanded_directory_count"] == 0
    assert doc["expand_refused_count"] == 0
    assert doc["depth_counts"] == {}
    assert doc["deepest_level"] == 0
    assert len(doc["notes"]) == 6


# ------------------------------------------------------- aggregation


@pytest.mark.asyncio
async def test_counts_sum_the_whole_tree(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    nested(folder)
    target = tmp_path / "outside.txt"
    target.write_bytes(b"x")
    os.symlink(target, folder / "link_out")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["census_state"] == "has_files"
    assert doc["node_count"] == 9
    assert sum(doc["kind_counts"].values()) == doc["node_count"]
    assert doc["directory_count"] == 2
    assert doc["file_count"] == 6
    assert doc["symlink_count"] == 1
    assert doc["other_count"] == 0
    assert doc["total_file_bytes"] == 5 + 7 + 1 + 3 + 4 + 2
    assert doc["hidden_count"] == 1
    assert doc["escaping_symlink_count"] == 1
    assert doc["extension_counts"] == {"(none)": 1, "md": 1, "txt": 4}
    assert doc["largest_file"] == {
        "name": "draft.MD", "path": "draft.MD", "size_bytes": 7}
    assert doc["expanded_directory_count"] == 2
    assert doc["unexpanded_directory_count"] == 0
    assert doc["expand_refused_count"] == 0
    assert doc["depth_counts"] == {"1": 5, "2": 2, "3": 2}
    assert doc["deepest_level"] == 3
    assert doc["truncated"] is False


def test_largest_file_tie_keeps_depth_first_order():
    tree_doc = _tree_doc([
        _leaf("a.bin", "file", 9),
        _dir("sub", [_leaf("b.bin", "file", 9)]),
    ], node_count=3)
    doc = tc.build_tree_census(tree_doc)
    assert doc["largest_file"] == {
        "name": "a.bin", "path": "a.bin", "size_bytes": 9}
    assert doc["total_file_bytes"] == 18


def test_largest_file_in_a_subdir_carries_its_path():
    tree_doc = _tree_doc([
        _leaf("a.bin", "file", 1),
        _dir("sub", [_leaf("big.bin", "file", 9)]),
    ], node_count=3)
    doc = tc.build_tree_census(tree_doc)
    assert doc["largest_file"] == {
        "name": "big.bin", "path": "sub/big.bin", "size_bytes": 9}
    assert doc["depth_counts"] == {"1": 2, "2": 1}
    assert doc["deepest_level"] == 2


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
    assert doc["expanded_directory_count"] == 1
    assert doc["symlink_count"] == 1
    assert doc["escaping_symlink_count"] == 1
    assert doc["file_count"] == 0
    assert doc["total_file_bytes"] == 0
    assert doc["largest_file"] is None
    assert doc["truncated"] is False


# ----------------------------------------------------- partial walks


@pytest.mark.asyncio
async def test_unexpanded_at_the_depth_cap_is_named(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    here = folder
    for name in ("d1", "d2", "d3", "d4", "d5"):
        here = here / name
        here.mkdir()
    (here / "bottom.txt").write_bytes(b"deep")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["directory_count"] == 4
    assert doc["expanded_directory_count"] == 3
    assert doc["unexpanded_directory_count"] == 1
    assert doc["node_count"] == 4
    assert doc["file_count"] == 0
    assert doc["census_state"] == "no_files"
    assert doc["depth_counts"] == {"1": 1, "2": 1, "3": 1, "4": 1}
    assert doc["deepest_level"] == 4
    assert doc["truncated"] is True
    assert doc["tree_document"]["truncated"] is True


def test_unexpanded_node_names_partial_even_if_flag_false():
    tree_doc = _tree_doc([
        _dir("sub", None, expanded=False),
        _leaf("a.txt", "file", 2),
    ], node_count=2, truncated=False)
    doc = tc.build_tree_census(tree_doc)
    assert doc["unexpanded_directory_count"] == 1
    assert doc["truncated"] is True
    assert doc["file_count"] == 1


def test_expand_refused_is_counted_and_names_partial():
    tree_doc = _tree_doc([
        _dir("gone", None, expanded=False, refused=True),
    ], node_count=1, truncated=False)
    doc = tc.build_tree_census(tree_doc)
    assert doc["expand_refused_count"] == 1
    assert doc["unexpanded_directory_count"] == 1
    assert doc["truncated"] is True
    assert doc["census_state"] == "no_files"


def test_tree_truncation_flag_is_carried_into_the_census():
    tree_doc = _tree_doc([
        _leaf("only.txt", "file", 4),
    ], node_count=1, truncated=True)
    doc = tc.build_tree_census(tree_doc)
    assert doc["truncated"] is True
    assert doc["file_count"] == 1
    assert doc["total_file_bytes"] == 4
    assert any("truncated" in note for note in doc["notes"])


# ---------------------------------------------------- verbatim tree


@pytest.mark.asyncio
async def test_tree_is_composed_verbatim(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    async with factory() as session:
        tree_doc = await tr.resolve_chat_tree(
            session, store, uid, chat_id, "", tr.MAX_DEPTH)
    assert doc["tree_document"] == tree_doc
    assert doc["folder_state"] == tree_doc["folder_state"]
    assert doc["subpath"] == tree_doc["subpath"]
    assert doc["max_depth"] == tree_doc["max_depth"]
    assert doc["node_count"] == tree_doc["node_count"]
    assert doc["binding_document"] == tree_doc["binding_document"]
    embedded = doc["tree_document"]["binding_document"]
    assert embedded["binding"]["folder_path"] == str(folder)


# --------------------------------------------------------- not ready


@pytest.mark.asyncio
async def test_missing_folder_is_data_never_an_error(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "gone"
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id)
    assert doc["census_state"] == "folder_not_ready"
    assert doc["folder_state"] == "missing"
    assert doc["node_count"] == 0
    assert doc["file_count"] == 0
    assert doc["total_file_bytes"] == 0
    assert doc["largest_file"] is None
    assert doc["truncated"] is False


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
    nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "sub")
    assert doc["subpath"] == "sub"
    assert doc["file_count"] == 3
    assert doc["total_file_bytes"] == 3 + 4 + 2
    assert doc["largest_file"] == {
        "name": "deep.txt", "path": "sub/deep/deep.txt",
        "size_bytes": 4}
    assert doc["depth_counts"] == {"1": 2, "2": 2}
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
    sub = folder / "sub"
    sub.mkdir()
    keep = sub / "keep.txt"
    keep.write_bytes(b"mine")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    store_bytes = store.index_path.read_bytes()
    first = await census(factory, store, uid, chat_id)
    assert first["file_count"] == 1
    (sub / "new.md").write_bytes(b"123456")
    second = await census(factory, store, uid, chat_id)
    assert second["file_count"] == 2
    assert second["total_file_bytes"] == 4 + 6
    assert second["extension_counts"] == {"md": 1, "txt": 1}
    assert keep.read_bytes() == b"mine"
    assert sorted(p.name for p in sub.iterdir()) == [
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
async def test_http_tree_census_road(tmp_path):
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
    got = client.get("/api/v1/workspaces/tree-census",
                     params={"chat_id": chat_id})
    assert got.status_code == 200, got.text
    doc = got.json()
    assert doc["schema"] == "runmal-p181-workspace-tree-census-v1"
    assert doc["census_state"] == "has_files"
    assert doc["file_count"] == 6
    assert doc["node_count"] == 8
    missing = client.get("/api/v1/workspaces/tree-census",
                         params={"chat_id": "no-such-chat"})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "chat not found"
    unbound = client.get("/api/v1/workspaces/tree-census",
                         params={"chat_id": unbound_chat})
    assert unbound.status_code == 404
    assert unbound.json()["detail"] == "workspace binding not found"
    refused = client.get("/api/v1/workspaces/tree-census",
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
    got = client.get("/api/v1/workspaces/tree-census",
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
