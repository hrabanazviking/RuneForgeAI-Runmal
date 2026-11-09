"""P-179 - Workspace tree truncated at the depth cap (FIX).

Commissioned fix for the defect P-178 found in banked
P-176: the tree document did not set ``truncated`` for
a directory left unexpanded at the depth cap, though
P-176's own notes claim ``truncated`` names every
partial tree - a capped partial tree was dressed as
whole. Pins: a directory at the cap (at the root level
or nested) sets truncated; a tree with nothing left
unexpanded at the cap stays truncated False (uncapped
depth, a file-only cap level, a symlink at the cap -
a leaf, never a directory node - an empty root at
depth 1); a non-ready folder is not a depth cap and
stays False (P-176's own expectation, preserved); the
pure build_tree road and the HTTP road carry the flag.
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
from runmal.db.migrate import migrate_to_head
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


# ------------------------------------------------------- the defect


@pytest.mark.asyncio
async def test_depth_cap_at_root_marks_truncated(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await tree(factory, store, uid, chat_id, max_depth=1)
    sub = by_name(doc["tree"]["children"])["sub"]
    assert sub["expanded"] is False
    assert sub["children"] is None
    assert doc["truncated"] is True


@pytest.mark.asyncio
async def test_nested_depth_cap_marks_truncated(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await tree(factory, store, uid, chat_id)  # default depth 2
    deep = by_name(
        by_name(doc["tree"]["children"])["sub"]["children"])["deep"]
    assert deep["expanded"] is False
    assert deep["children"] is None
    assert doc["truncated"] is True


def test_pure_build_tree_depth_cap_marks_truncated(tmp_path, monkeypatch):
    folder = tmp_path / "bench"
    folder.mkdir()

    def entry(name, kind):
        return {"name": name, "kind": kind,
                "size_bytes": None if kind == "directory" else 1,
                "hidden": False, "escapes": False}

    def listing(subpath, entries):
        return {"schema": ls.LISTING_SCHEMA,
                "binding_document": {
                    "binding": {"folder_path": str(folder)}},
                "folder_state": "ready", "subpath": subpath,
                "total_count": len(entries),
                "entry_count": len(entries), "truncated": False,
                "entries": entries, "notes": []}

    listings = {
        "": listing("", [entry("sub", "directory"),
                         entry("top.txt", "file")]),
        "sub": listing("sub", [entry("mid.txt", "file")]),
    }
    monkeypatch.setattr(
        ls, "build_listing",
        lambda bd, fp, sp: listings[sp])
    capped = tr.build_tree(listings[""], 1)
    assert capped["tree"]["children"][0]["expanded"] is False
    assert capped["truncated"] is True
    whole = tr.build_tree(listings[""], 2)
    assert whole["tree"]["children"][0]["expanded"] is True
    assert whole["truncated"] is False


# ------------------------------------------- honest False stays False


@pytest.mark.asyncio
async def test_uncapped_tree_stays_not_truncated(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await tree(factory, store, uid, chat_id, max_depth=3)
    deep = by_name(
        by_name(doc["tree"]["children"])["sub"]["children"])["deep"]
    assert deep["expanded"] is True
    assert doc["truncated"] is False


@pytest.mark.asyncio
async def test_file_only_cap_level_stays_not_truncated(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    sub = folder / "sub"
    sub.mkdir()
    (sub / "only.txt").write_bytes(b"x")
    (folder / "top.txt").write_bytes(b"1")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await tree(factory, store, uid, chat_id)  # depth 2: cap level
    sub_node = by_name(doc["tree"]["children"])["sub"]
    assert sub_node["expanded"] is True
    assert doc["truncated"] is False
    shallow = await tree(factory, store, uid, chat_id, max_depth=1)
    assert by_name(shallow["tree"]["children"])["sub"]["expanded"] is False
    assert shallow["truncated"] is True


@pytest.mark.asyncio
async def test_symlink_at_cap_stays_not_truncated(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    real = tmp_path / "real"
    real.mkdir()
    (real / "inside.txt").write_bytes(b"x")
    os.symlink(real, folder / "link")
    (folder / "top.txt").write_bytes(b"1")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await tree(factory, store, uid, chat_id, max_depth=1)
    link = by_name(doc["tree"]["children"])["link"]
    assert link["kind"] == "symlink"
    assert "children" not in link
    assert doc["truncated"] is False


@pytest.mark.asyncio
async def test_empty_root_at_depth_one_stays_not_truncated(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await tree(factory, store, uid, chat_id, max_depth=1)
    assert doc["tree"]["children"] == []
    assert doc["truncated"] is False


@pytest.mark.asyncio
async def test_missing_folder_is_not_a_depth_cap(tmp_path):
    factory = make_factory(tmp_path)
    uid, chat_id, store = await bound(factory, tmp_path, tmp_path / "gone")
    doc = await tree(factory, store, uid, chat_id, max_depth=1)
    assert doc["folder_state"] == "missing"
    assert doc["tree"]["expanded"] is False
    assert doc["truncated"] is False


# --------------------------------------------------------------- HTTP


@pytest.mark.asyncio
async def test_http_tree_carries_the_cap_flag(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    nested(folder)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(folder))
    shallow = client.get("/api/v1/workspaces/tree",
                         params={"chat_id": chat_id, "max_depth": 1})
    assert shallow.status_code == 200, shallow.text
    assert shallow.json()["truncated"] is True
    deep = client.get("/api/v1/workspaces/tree",
                      params={"chat_id": chat_id, "max_depth": 3})
    assert deep.status_code == 200, deep.text
    assert deep.json()["truncated"] is False
