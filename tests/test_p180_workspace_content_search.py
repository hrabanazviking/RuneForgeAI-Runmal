"""P-180 - Workspace content search (Part XI, DERIVED).

Pins: the content search document (P-176's tree document
composed verbatim at its maximum depth and embedded
whole), the match law (casefold substring of the file's
decoded CONTENT only - never the name, never a path
component), the coverage law (expanded nodes only; an
unexpanded directory is never dressed as searched), the
honesty law (every candidate file is a match, a counted
searched non-match, or a named skip - binary / oversize /
unreadable / refused; an oversize file is never searched
in part), the query law (required, stripped; empty or
blank refused plainly, never match-everything), the match
cap (100, with total_matches honest and truncated set),
match paths (folder-relative, the input P-172 consumes),
occurrences and the bounded verbatim excerpt, symlinks
never followed for content, non-ready folders as DATA,
owner scoping (missing / foreign / unbound -> None), the
pure-read law, the HTTP road (GET
/workspaces/content-search: two 404s kept apart, refusals
at 422, states DATA at 200), and the neighbours (migration
head stays 0041). No network.
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
from runmal.workspaces import content as co
from runmal.workspaces import content_search as cs
from runmal.workspaces import listing as ls
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


async def csearch(factory, store, uid, chat_id, q, subpath=""):
    async with factory() as session:
        return await cs.resolve_chat_content_search(
            session, store, uid, chat_id, q, subpath)


def nested(folder):
    (folder / "Report.txt").write_bytes(b"the silver thread runs")
    (folder / "notes.md").write_bytes(b"plain water, no metal")
    sub = folder / "sub"
    sub.mkdir()
    (sub / "report-final.txt").write_bytes(
        b"Silver again and silver twice")
    deep = sub / "deep"
    deep.mkdir()
    (deep / "REPORT card.md").write_bytes(b"stone and wood only")
    return sub, deep


def paths(doc):
    return [m["path"] for m in doc["matches"]]


def skips(doc):
    return {s["path"]: s["outcome"] for s in doc["skipped_files"]}


# ------------------------------------------------------------- matches


@pytest.mark.asyncio
async def test_find_by_content_at_every_depth(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await csearch(factory, store, uid, chat_id, "silver")
    assert doc["schema"] == "runmal-p180-workspace-content-search-v1"
    assert doc["query"] == "silver"
    assert doc["folder_state"] == "ready"
    assert doc["total_matches"] == 2 and doc["match_count"] == 2
    assert paths(doc) == ["sub/report-final.txt", "Report.txt"]
    assert doc["files_considered"] == 4
    assert doc["files_searched"] == 4
    assert doc["skipped_files"] == []
    assert doc["truncated"] is False
    assert doc["coverage_complete"] is True
    assert doc["max_content_bytes"] == co.MAX_CONTENT_BYTES
    assert doc["max_matches"] == cs.MAX_MATCHES == 100
    first = doc["matches"][0]
    assert first["occurrences"] == 2
    assert "silver" in first["excerpt"].casefold()
    assert first["kind"] == "file" and first["hidden"] is False


@pytest.mark.asyncio
async def test_match_is_content_only_never_name_or_path(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    (folder / "silver-named.txt").write_bytes(b"nothing inside")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await csearch(factory, store, uid, chat_id, "silver")
    assert "silver-named.txt" not in paths(doc)
    # "deep" names a directory on the path of a real file;
    # no file's CONTENT holds it, so nothing matches.
    by_path = await csearch(factory, store, uid, chat_id, "deep")
    assert by_path["matches"] == [] and by_path["total_matches"] == 0
    assert by_path["files_searched"] == 5


@pytest.mark.asyncio
async def test_query_is_stripped_and_blank_refused(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await csearch(factory, store, uid, chat_id, "  silver  ")
    assert doc["query"] == "silver" and doc["total_matches"] == 2
    for bad in ("", "   ", None):
        with pytest.raises(cs.WorkspaceContentSearchError):
            await csearch(factory, store, uid, chat_id, bad)
    with pytest.raises(cs.WorkspaceContentSearchError):
        cs.build_content_search(doc["tree_document"], "")


@pytest.mark.asyncio
async def test_occurrences_and_bounded_verbatim_excerpt(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    body = ("x" * 200) + "needle" + ("y" * 200) + "needle"
    (folder / "long.txt").write_bytes(body.encode())
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await csearch(factory, store, uid, chat_id, "NEEDLE")
    assert doc["total_matches"] == 1
    match = doc["matches"][0]
    assert match["occurrences"] == 2
    assert match["excerpt"] in body
    assert len(match["excerpt"]) <= len("needle") + 2 * cs.EXCERPT_CONTEXT
    assert match["excerpt"].casefold().count("needle") == 1


@pytest.mark.asyncio
async def test_match_cap_is_honest(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    for i in range(105):
        (folder / f"item-{i:03d}.txt").write_bytes(b"common word")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await csearch(factory, store, uid, chat_id, "common")
    assert doc["match_count"] == cs.MAX_MATCHES == 100
    assert doc["total_matches"] == 105
    assert doc["files_searched"] == 105
    assert doc["truncated"] is True
    assert doc["coverage_complete"] is False


# ------------------------------------------------------ honesty / caps


@pytest.mark.asyncio
async def test_binary_and_oversize_are_named_skips_never_partial(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    (folder / "plain.txt").write_bytes(b"a silver line")
    (folder / "blob.bin").write_bytes(b"silver\x00hidden")
    big = b"silver at the start " + b"x" * co.MAX_CONTENT_BYTES
    (folder / "big.txt").write_bytes(big)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await csearch(factory, store, uid, chat_id, "silver")
    # The oversize file holds the needle at its start and is
    # still NOT a match: it was never searched in part.
    assert paths(doc) == ["plain.txt"]
    assert skips(doc) == {"big.txt": "oversize", "blob.bin": "binary"}
    assert doc["files_considered"] == 3
    assert doc["files_searched"] == 1
    assert doc["files_considered"] == doc["files_searched"] + len(doc["skipped_files"])
    assert doc["truncated"] is True  # partiality named, not hidden
    assert doc["coverage_complete"] is False
    big_skip = [s for s in doc["skipped_files"] if s["path"] == "big.txt"][0]
    assert big_skip["size_bytes"] == len(big)


@pytest.mark.asyncio
async def test_unexpanded_depth_is_not_searched(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    here = folder
    for name in ("a", "b", "c", "d"):
        here = here / name; here.mkdir()
    (here / "buried.txt").write_bytes(b"buried treasure")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await csearch(factory, store, uid, chat_id, "treasure")
    assert doc["matches"] == []
    assert doc["tree_document"]["max_depth"] == tr.MAX_DEPTH
    assert doc["truncated"] is True
    assert doc["coverage_complete"] is False


@pytest.mark.asyncio
async def test_symlinks_are_never_searched_for_content(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    (folder / "real.txt").write_bytes(b"the needle rests")
    os.symlink(folder / "real.txt", folder / "needle-link")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await csearch(factory, store, uid, chat_id, "needle")
    assert paths(doc) == ["real.txt"]
    assert doc["files_considered"] == 1  # the link is no candidate


@pytest.mark.asyncio
async def test_file_vanishing_after_the_walk_is_a_named_refusal(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    async with factory() as session:
        tree_doc = await tr.resolve_chat_tree(
            session, store, uid, chat_id, "", tr.MAX_DEPTH)
    (folder / "Report.txt").unlink()  # the two-moment race
    doc = cs.build_content_search(tree_doc, "silver")
    assert paths(doc) == ["sub/report-final.txt"]
    assert skips(doc) == {"Report.txt": "refused"}
    assert doc["files_considered"] == 4
    assert doc["files_searched"] == 3
    assert doc["truncated"] is True


# ------------------------------------------------------- states / scope


@pytest.mark.asyncio
async def test_non_ready_folder_is_data_with_no_search(tmp_path):
    factory = make_factory(tmp_path)
    uid, chat_id, store = await bound(
        factory, tmp_path, tmp_path / "gone")
    doc = await csearch(factory, store, uid, chat_id, "any")
    assert doc["folder_state"] == "missing"
    assert doc["matches"] == [] and doc["total_matches"] == 0
    assert doc["files_considered"] == 0 and doc["files_searched"] == 0
    assert doc["skipped_files"] == []
    assert doc["tree_document"]["tree"]["children"] is None


@pytest.mark.asyncio
async def test_subpath_roots_the_search_and_refusal_raises(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await csearch(factory, store, uid, chat_id, "silver", "sub")
    assert doc["subpath"] == "sub"
    assert paths(doc) == ["sub/report-final.txt"]
    assert doc["files_considered"] == 2
    with pytest.raises(ls.WorkspaceListingError):
        await csearch(factory, store, uid, chat_id, "x", "../bench")


@pytest.mark.asyncio
async def test_none_trio_missing_foreign_unbound(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    other = await make_user(factory, "other")
    foreign = await seed_chat(factory, other, "Foreign")
    unbound = await seed_chat(factory, uid, "Unbound")
    assert await csearch(factory, store, uid, "no-such", "x") is None
    assert await csearch(factory, store, uid, foreign, "x") is None
    assert await csearch(factory, store, uid, unbound, "x") is None


@pytest.mark.asyncio
async def test_tree_embedded_verbatim_and_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    before = {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    store_bytes = store.index_path.read_bytes()
    doc = await csearch(factory, store, uid, chat_id, "silver")
    async with factory() as session:
        direct = await tr.resolve_chat_tree(
            session, store, uid, chat_id, "", tr.MAX_DEPTH)
    assert doc["tree_document"] == direct
    assert doc["binding_document"] == direct["binding_document"]
    after = {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    assert before == after
    assert store.index_path.read_bytes() == store_bytes
    again = await csearch(factory, store, uid, chat_id, "silver")
    assert again == doc


# --------------------------------------------------------------- HTTP


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


@pytest.mark.asyncio
async def test_http_content_search_road(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    unbound = await seed_chat(factory, uid, "Unbound")
    store = make_store(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); nested(folder)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(folder))
    got = client.get("/api/v1/workspaces/content-search",
                     params={"chat_id": chat_id, "q": "silver"})
    assert got.status_code == 200, got.text
    assert got.json()["total_matches"] == 2
    assert got.json()["files_searched"] == 4
    missing = client.get("/api/v1/workspaces/content-search",
                         params={"chat_id": "nope", "q": "x"})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "chat not found"
    unb = client.get("/api/v1/workspaces/content-search",
                     params={"chat_id": unbound, "q": "x"})
    assert unb.status_code == 404
    assert unb.json()["detail"] == "workspace binding not found"
    blank = client.get("/api/v1/workspaces/content-search",
                       params={"chat_id": chat_id, "q": "  "})
    assert blank.status_code == 422
    bad = client.get("/api/v1/workspaces/content-search",
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
    got = client.get("/api/v1/workspaces/content-search",
                     params={"chat_id": chat_id, "q": "any"})
    assert got.status_code == 200, got.text
    assert got.json()["folder_state"] == "missing"
    assert got.json()["matches"] == []
    assert got.json()["files_considered"] == 0


# ---------------------------------------------------------- neighbours


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
