"""P-178 - Workspace filename search (Part XI, DERIVED).

Pins: the search document (P-176's tree document composed
verbatim at its maximum depth and embedded whole), the
match law (casefold substring of the entry NAME only -
never a path component, never content), the coverage law
(expanded nodes only; an unexpanded directory is never
dressed as searched), the query law (required, stripped;
empty or blank refused plainly, never match-everything),
the match cap (100, with total_matches honest and
truncated set), match paths (folder-relative, the input
P-172 consumes), symlinks as matches never descended,
non-ready folders as DATA, owner scoping (missing /
foreign / unbound -> None), the pure-read law, the HTTP
road (GET /workspaces/search: two 404s kept apart,
refusals at 422, states DATA at 200), and the neighbours
(migration head stays 0041). No network.
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
from runmal.workspaces import bindings as ws
from runmal.workspaces import listing as ls
from runmal.workspaces import search as se
from runmal.workspaces import tree as tr
from runmal.plugins import service as plugin_service
from runmal.db.models import User


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


async def search(factory, store, uid, chat_id, q, subpath=""):
    async with factory() as session:
        return await se.resolve_chat_search(
            session, store, uid, chat_id, q, subpath)


def nested(folder):
    (folder / "Report.txt").write_bytes(b"1")
    (folder / "notes.md").write_bytes(b"2")
    sub = folder / "sub"
    sub.mkdir()
    (sub / "report-final.txt").write_bytes(b"33")
    deep = sub / "deep"
    deep.mkdir()
    (deep / "REPORT card.md").write_bytes(b"444")
    return sub, deep


def paths(doc):
    return [m["path"] for m in doc["matches"]]


# ------------------------------------------------------------- matches


@pytest.mark.asyncio
async def test_find_by_name_at_every_depth(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await search(factory, store, uid, chat_id, "report")
    assert doc["schema"] == "runmal-p178-workspace-search-v1"
    assert doc["query"] == "report"
    assert doc["folder_state"] == "ready"
    assert doc["total_matches"] == 3 and doc["match_count"] == 3
    assert doc["truncated"] is False
    assert paths(doc) == ["sub/deep/REPORT card.md",
                          "sub/report-final.txt", "Report.txt"]
    first = doc["matches"][-1]
    assert first["name"] == "Report.txt" and first["size_bytes"] == 1
    assert first["hidden"] is False and first["escapes"] is False


@pytest.mark.asyncio
async def test_match_is_casefold_substring_of_name_only(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await search(factory, store, uid, chat_id, "EPOR")
    assert doc["total_matches"] == 3
    # "sub" names the directory only - its children are NOT
    # matched through their path.
    by_dir = await search(factory, store, uid, chat_id, "sub")
    assert paths(by_dir) == ["sub"]
    assert by_dir["matches"][0]["kind"] == "directory"
    none = await search(factory, store, uid, chat_id, "zzz")
    assert none["matches"] == [] and none["total_matches"] == 0


@pytest.mark.asyncio
async def test_query_is_stripped_and_blank_refused(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await search(factory, store, uid, chat_id, "  notes  ")
    assert doc["query"] == "notes" and doc["total_matches"] == 1
    for bad in ("", "   ", None):
        with pytest.raises(se.WorkspaceSearchError):
            await search(factory, store, uid, chat_id, bad)
    with pytest.raises(se.WorkspaceSearchError):
        se.build_search(doc["tree_document"], "")


@pytest.mark.asyncio
async def test_match_cap_is_honest(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    for i in range(105):
        (folder / f"item-{i:03d}.txt").write_bytes(b"x")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await search(factory, store, uid, chat_id, "item-")
    assert doc["match_count"] == se.MAX_MATCHES == 100
    assert doc["total_matches"] == 105
    assert doc["truncated"] is True


@pytest.mark.asyncio
async def test_unexpanded_depth_is_not_searched(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    here = folder
    for name in ("a", "b", "c", "d"):
        here = here / name; here.mkdir()
    (here / "buried-treasure.txt").write_bytes(b"x")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await search(factory, store, uid, chat_id, "treasure")
    assert doc["matches"] == []
    assert doc["tree_document"]["max_depth"] == tr.MAX_DEPTH
    assert doc["truncated"] is True  # partiality named, not hidden


@pytest.mark.asyncio
async def test_symlinks_match_but_are_never_descended(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    real = folder / "real"; real.mkdir()
    (real / "needle.txt").write_bytes(b"x")
    os.symlink(real, folder / "needle-link")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await search(factory, store, uid, chat_id, "needle")
    assert paths(doc) == ["real/needle.txt", "needle-link"]
    link = doc["matches"][1]
    assert link["kind"] == "symlink" and link["size_bytes"] is None


# ------------------------------------------------------- states / scope


@pytest.mark.asyncio
async def test_non_ready_folder_is_data_with_no_matches(tmp_path):
    factory = make_factory(tmp_path)
    uid, chat_id, store = await bound(
        factory, tmp_path, tmp_path / "gone")
    doc = await search(factory, store, uid, chat_id, "any")
    assert doc["folder_state"] == "missing"
    assert doc["matches"] == [] and doc["total_matches"] == 0
    assert doc["tree_document"]["tree"]["children"] is None


@pytest.mark.asyncio
async def test_subpath_roots_the_search_and_refusal_raises(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await search(factory, store, uid, chat_id, "report", "sub")
    assert doc["subpath"] == "sub"
    assert paths(doc) == ["sub/deep/REPORT card.md",
                          "sub/report-final.txt"]
    with pytest.raises(ls.WorkspaceListingError):
        await search(factory, store, uid, chat_id, "x", "../bench")


@pytest.mark.asyncio
async def test_none_trio_missing_foreign_unbound(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    other = await make_user(factory, "other")
    foreign = await seed_chat(factory, other, "Foreign")
    unbound = await seed_chat(factory, uid, "Unbound")
    assert await search(factory, store, uid, "no-such", "x") is None
    assert await search(factory, store, uid, foreign, "x") is None
    assert await search(factory, store, uid, unbound, "x") is None


@pytest.mark.asyncio
async def test_tree_embedded_verbatim_and_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    before = {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    store_bytes = store.index_path.read_bytes()
    doc = await search(factory, store, uid, chat_id, "report")
    async with factory() as session:
        direct = await tr.resolve_chat_tree(
            session, store, uid, chat_id, "", tr.MAX_DEPTH)
    assert doc["tree_document"] == direct
    assert doc["binding_document"] == direct["binding_document"]
    after = {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    assert before == after
    assert store.index_path.read_bytes() == store_bytes
    again = await search(factory, store, uid, chat_id, "report")
    assert again == doc


# --------------------------------------------------------------- HTTP


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


@pytest.mark.asyncio
async def test_http_search_road(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    unbound = await seed_chat(factory, uid, "Unbound")
    store = make_store(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(folder))
    got = client.get("/api/v1/workspaces/search",
                     params={"chat_id": chat_id, "q": "report"})
    assert got.status_code == 200, got.text
    assert got.json()["total_matches"] == 3
    missing = client.get("/api/v1/workspaces/search",
                         params={"chat_id": "nope", "q": "x"})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "chat not found"
    unb = client.get("/api/v1/workspaces/search",
                     params={"chat_id": unbound, "q": "x"})
    assert unb.status_code == 404
    assert unb.json()["detail"] == "workspace binding not found"
    blank = client.get("/api/v1/workspaces/search",
                       params={"chat_id": chat_id, "q": "  "})
    assert blank.status_code == 422
    bad = client.get("/api/v1/workspaces/search",
                     params={"chat_id": chat_id, "q": "x",
                             "subpath": "../bench"})
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_http_not_ready_folder_is_data_at_200(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(tmp_path / "gone"))
    got = client.get("/api/v1/workspaces/search",
                     params={"chat_id": chat_id, "q": "any"})
    assert got.status_code == 200, got.text
    assert got.json()["folder_state"] == "missing"
    assert got.json()["matches"] == []


# ---------------------------------------------------------- neighbours


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
