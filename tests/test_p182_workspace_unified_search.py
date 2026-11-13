"""P-182 - Workspace unified search (Part XI, DERIVED).

Pins: the unified search document (ONE P-176 tree
document composed verbatim at its maximum depth and
embedded whole, both banked search documents - P-178
filename, P-180 content - built from that same tree and
embedded whole), the union law (by folder-relative
path, each path once, matched_by under the closed
name / content / both law, the tree's own depth-first
order), the kept-apart law (a name match is a name fact
only - no occurrences, no excerpt invented; a content
match is a content fact only), the cap honesty law
(the union is over the two RETURNED lists; both source
totals ride verbatim, so a capped source is named by
truncated, never dressed as complete), the file
honesty law carried verbatim from P-180 (every
candidate a match, a counted searched non-match, or a
named skip; a file the content road cannot search can
still name-match, and a file that vanishes after the
walk keeps its name match beside its refused skip),
the query law (required, stripped; empty or blank
refused plainly, never match-everything), symlinks
(name-matched as themselves, never content
candidates), non-ready folders as DATA, owner scoping
(missing / foreign / unbound -> None), the pure-read
law, the HTTP road (GET /workspaces/unified-search:
two 404s kept apart, refusals at 422, states DATA at
200), and the neighbours (migration head stays 0041).
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
from runmal.workspaces import bindings as ws
from runmal.workspaces import content as co
from runmal.workspaces import content_search as cs
from runmal.workspaces import listing as ls
from runmal.workspaces import search as ns
from runmal.workspaces import tree as tr
from runmal.workspaces import unified_search as us
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


async def usearch(factory, store, uid, chat_id, q, subpath=""):
    async with factory() as session:
        return await us.resolve_chat_unified_search(
            session, store, uid, chat_id, q, subpath)


def bench(folder):
    (folder / "silver-named.txt").write_bytes(b"plain water only")
    (folder / "report.txt").write_bytes(b"the silver thread runs")
    (folder / "silver-song.txt").write_bytes(b"silver bells ring")
    (folder / "notes.md").write_bytes(b"nothing relevant here")
    sub = folder / "sub"
    sub.mkdir()
    (sub / "inner.txt").write_bytes(b"a silver lining waits")
    return sub


def paths(doc):
    return [m["path"] for m in doc["matches"]]


def by_path(doc):
    return {m["path"]: m for m in doc["matches"]}


def skips(doc):
    return {s["path"]: s["outcome"] for s in doc["skipped_files"]}


def tree_order(doc):
    order = []

    def walk(children, prefix):
        for node in children or []:
            path = f"{prefix}/{node['name']}" if prefix else node["name"]
            order.append(path)
            if node.get("expanded"):
                walk(node.get("children"), path)

    root = doc["tree_document"]["tree"]
    if root.get("expanded"):
        walk(root.get("children"), doc["tree_document"]["subpath"])
    return order


# ------------------------------------------------------------- the union


@pytest.mark.asyncio
async def test_union_merges_name_content_and_both(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await usearch(factory, store, uid, chat_id, "silver")
    assert doc["schema"] == "runmal-p182-workspace-unified-search-v1"
    assert doc["query"] == "silver"
    assert doc["folder_state"] == "ready"
    # The both-match is counted ONCE in the union.
    assert doc["total_matches"] == 4 and doc["match_count"] == 4
    assert doc["name_match_count"] == 2
    assert doc["content_match_count"] == 3
    assert doc["both_count"] == 1
    assert doc["name_total_matches"] == 2
    assert doc["content_total_matches"] == 3
    assert doc["files_considered"] == 5
    assert doc["files_searched"] == 5
    assert doc["skipped_files"] == []
    assert doc["truncated"] is False
    assert doc["coverage_complete"] is True
    assert doc["max_matches"] == us.MAX_MATCHES == 100
    assert doc["max_content_bytes"] == co.MAX_CONTENT_BYTES
    found = by_path(doc)
    assert set(found) == {
        "silver-named.txt", "report.txt",
        "silver-song.txt", "sub/inner.txt"}
    assert found["silver-named.txt"]["matched_by"] == "name"
    assert found["report.txt"]["matched_by"] == "content"
    assert found["silver-song.txt"]["matched_by"] == "both"
    assert found["sub/inner.txt"]["matched_by"] == "content"


@pytest.mark.asyncio
async def test_match_kinds_are_kept_apart(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await usearch(factory, store, uid, chat_id, "silver")
    found = by_path(doc)
    name_only = found["silver-named.txt"]
    assert name_only["name_match"] is True
    assert name_only["content_match"] is False
    # No content fact is invented for a name-only match.
    assert name_only["occurrences"] is None
    assert name_only["excerpt"] is None
    content_only = found["report.txt"]
    assert content_only["name_match"] is False
    assert content_only["content_match"] is True
    assert content_only["occurrences"] == 1
    assert "silver" in content_only["excerpt"].casefold()
    both = found["silver-song.txt"]
    assert both["occurrences"] == 1
    assert "silver" in both["excerpt"].casefold()
    # A path component is never a match: "sub" names the
    # directory itself, and the file inside it - whose
    # path carries "sub" - is not matched by either law.
    by_sub = await usearch(factory, store, uid, chat_id, "sub")
    assert paths(by_sub) == ["sub"]
    assert by_sub["matches"][0]["kind"] == "directory"
    assert by_sub["matches"][0]["matched_by"] == "name"


@pytest.mark.asyncio
async def test_union_rides_in_the_trees_own_order(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await usearch(factory, store, uid, chat_id, "silver")
    order = tree_order(doc)
    assert paths(doc) == sorted(paths(doc), key=order.index)
    assert len(paths(doc)) == len(set(paths(doc)))


@pytest.mark.asyncio
async def test_query_is_stripped_and_blank_refused(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await usearch(factory, store, uid, chat_id, "  silver  ")
    assert doc["query"] == "silver" and doc["total_matches"] == 4
    for bad in ("", "   ", None):
        with pytest.raises(us.WorkspaceUnifiedSearchError):
            await usearch(factory, store, uid, chat_id, bad)
    with pytest.raises(us.WorkspaceUnifiedSearchError):
        us.build_unified_search(doc["tree_document"], "")


# --------------------------------------------------------- cap honesty


@pytest.mark.asyncio
async def test_match_cap_and_source_totals_stay_honest(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    for i in range(105):
        (folder / f"common-{i:03d}.txt").write_bytes(b"unrelated text")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await usearch(factory, store, uid, chat_id, "common")
    # The name source's true total rides verbatim even
    # though its returned list - and so the union - is
    # capped: the partiality is data, never hidden.
    assert doc["name_total_matches"] == 105
    assert doc["name_search_document"]["total_matches"] == 105
    assert doc["match_count"] == us.MAX_MATCHES == 100
    assert doc["total_matches"] == 100
    assert doc["truncated"] is True
    assert doc["coverage_complete"] is False


# ------------------------------------------------------ honesty / caps


@pytest.mark.asyncio
async def test_unsearchable_file_can_still_name_match(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    (folder / "plain.txt").write_bytes(b"a silver line")
    (folder / "blob.bin").write_bytes(b"silver\x00hidden")
    big = b"silver at the start " + b"x" * co.MAX_CONTENT_BYTES
    (folder / "silver-big.txt").write_bytes(big)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await usearch(factory, store, uid, chat_id, "silver")
    found = by_path(doc)
    # The oversize file was never searched in part, so it
    # is no content match - but its NAME is a tree-time
    # fact and still matches, beside its named skip.
    assert found["silver-big.txt"]["matched_by"] == "name"
    assert found["silver-big.txt"]["occurrences"] is None
    assert found["plain.txt"]["matched_by"] == "content"
    assert "blob.bin" not in found
    assert skips(doc) == {
        "blob.bin": "binary", "silver-big.txt": "oversize"}
    assert doc["files_considered"] == 3
    assert doc["files_searched"] == 1
    assert doc["files_considered"] == \
        doc["files_searched"] + len(doc["skipped_files"])
    assert doc["truncated"] is True
    assert doc["coverage_complete"] is False


@pytest.mark.asyncio
async def test_unexpanded_depth_is_not_matched(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    here = folder
    for name in ("a", "b", "c", "d"):
        here = here / name; here.mkdir()
    (here / "treasure.txt").write_bytes(b"buried treasure")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await usearch(factory, store, uid, chat_id, "treasure")
    assert doc["matches"] == []
    assert doc["tree_document"]["max_depth"] == tr.MAX_DEPTH
    assert doc["truncated"] is True
    assert doc["coverage_complete"] is False


@pytest.mark.asyncio
async def test_symlink_name_matches_but_is_no_content_candidate(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    (folder / "real.txt").write_bytes(b"the needle rests")
    os.symlink(folder / "real.txt", folder / "needle-link")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await usearch(factory, store, uid, chat_id, "needle")
    found = by_path(doc)
    assert found["needle-link"]["matched_by"] == "name"
    assert found["needle-link"]["kind"] == "symlink"
    assert found["real.txt"]["matched_by"] == "content"
    assert doc["files_considered"] == 1  # the link is no candidate


@pytest.mark.asyncio
async def test_vanished_file_keeps_name_match_beside_refused_skip(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    (folder / "ghost-silver.txt").write_bytes(b"a silver ghost")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    async with factory() as session:
        tree_doc = await tr.resolve_chat_tree(
            session, store, uid, chat_id, "", tr.MAX_DEPTH)
    (folder / "ghost-silver.txt").unlink()  # the two-moment race
    doc = us.build_unified_search(tree_doc, "silver")
    found = by_path(doc)
    # The name answer is a fact of the composed tree and
    # survives; the content road's refusal is named too.
    assert found["ghost-silver.txt"]["matched_by"] == "name"
    assert skips(doc) == {"ghost-silver.txt": "refused"}
    assert doc["files_considered"] == 6
    assert doc["files_searched"] == 5
    assert doc["truncated"] is True


# ------------------------------------------------------- states / scope


@pytest.mark.asyncio
async def test_non_ready_folder_is_data_with_no_matches(tmp_path):
    factory = make_factory(tmp_path)
    uid, chat_id, store = await bound(
        factory, tmp_path, tmp_path / "gone")
    doc = await usearch(factory, store, uid, chat_id, "any")
    assert doc["folder_state"] == "missing"
    assert doc["matches"] == [] and doc["total_matches"] == 0
    assert doc["name_total_matches"] == 0
    assert doc["content_total_matches"] == 0
    assert doc["files_considered"] == 0 and doc["files_searched"] == 0
    assert doc["skipped_files"] == []
    assert doc["tree_document"]["tree"]["children"] is None


@pytest.mark.asyncio
async def test_subpath_roots_the_search_and_refusal_raises(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await usearch(factory, store, uid, chat_id, "silver", "sub")
    assert doc["subpath"] == "sub"
    assert paths(doc) == ["sub/inner.txt"]
    assert doc["files_considered"] == 1
    with pytest.raises(ls.WorkspaceListingError):
        await usearch(factory, store, uid, chat_id, "x", "../bench")


@pytest.mark.asyncio
async def test_none_trio_missing_foreign_unbound(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    other = await make_user(factory, "other")
    foreign = await seed_chat(factory, other, "Foreign")
    unbound = await seed_chat(factory, uid, "Unbound")
    assert await usearch(factory, store, uid, "no-such", "x") is None
    assert await usearch(factory, store, uid, foreign, "x") is None
    assert await usearch(factory, store, uid, unbound, "x") is None


@pytest.mark.asyncio
async def test_one_tree_composed_verbatim_and_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    before = {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    store_bytes = store.index_path.read_bytes()
    doc = await usearch(factory, store, uid, chat_id, "silver")
    async with factory() as session:
        direct = await tr.resolve_chat_tree(
            session, store, uid, chat_id, "", tr.MAX_DEPTH)
    # ONE tree: the unified document's tree and both
    # embedded search documents' trees are the same
    # composed document - the two answers describe the
    # same walk, never two walks that could disagree.
    assert doc["tree_document"] == direct
    assert doc["name_search_document"]["tree_document"] == direct
    assert doc["content_search_document"]["tree_document"] == direct
    assert doc["binding_document"] == direct["binding_document"]
    after = {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    assert before == after
    assert store.index_path.read_bytes() == store_bytes
    again = await usearch(factory, store, uid, chat_id, "silver")
    assert again == doc


@pytest.mark.asyncio
async def test_embedded_documents_equal_their_own_resolves(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await usearch(factory, store, uid, chat_id, "silver")
    async with factory() as session:
        name_doc = await ns.resolve_chat_search(
            session, store, uid, chat_id, "silver")
        content_doc = await cs.resolve_chat_content_search(
            session, store, uid, chat_id, "silver")
    assert doc["name_search_document"] == name_doc
    assert doc["content_search_document"] == content_doc


# --------------------------------------------------------------- HTTP


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


@pytest.mark.asyncio
async def test_http_unified_search_road(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    unbound = await seed_chat(factory, uid, "Unbound")
    store = make_store(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(folder))
    got = client.get("/api/v1/workspaces/unified-search",
                     params={"chat_id": chat_id, "q": "silver"})
    assert got.status_code == 200, got.text
    assert got.json()["total_matches"] == 4
    assert got.json()["both_count"] == 1
    missing = client.get("/api/v1/workspaces/unified-search",
                         params={"chat_id": "nope", "q": "x"})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "chat not found"
    unb = client.get("/api/v1/workspaces/unified-search",
                     params={"chat_id": unbound, "q": "x"})
    assert unb.status_code == 404
    assert unb.json()["detail"] == "workspace binding not found"
    blank = client.get("/api/v1/workspaces/unified-search",
                       params={"chat_id": chat_id, "q": "  "})
    assert blank.status_code == 422
    bad = client.get("/api/v1/workspaces/unified-search",
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
    got = client.get("/api/v1/workspaces/unified-search",
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
