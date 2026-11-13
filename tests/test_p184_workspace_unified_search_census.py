"""P-184 - Workspace unified search census (Part XI, DERIVED).

Pins: the census document (P-182's unified search
document composed verbatim and embedded whole, every
count summed from that document's own returned-match
and skipped-file fields), the returned-axis arithmetic
(name_only + content_only + both_match == the returned
match_count, always), the source-axis honesty law
(P-182's own uncapped counts and both source totals
carried verbatim beside the returned sums, so a capped
union is censused as capped and neither truth is
dressed as the other), the kind / extension / byte /
occurrence / depth axes (kinds under P-170's closed
ENTRY_KINDS, extensions from file-match names only,
bytes from file matches only, no occurrence invented
for a name-only match, depth counted in segments below
the composed subpath), the skip axis (skipped files
counted by their P-172 outcome or refused, P-180's
files arithmetic carried verbatim), the closed census
law (folder_not_ready / no_matches / name_only /
content_only / mixed, non-ready folders DATA as the
honest zero document), the query law inherited from
P-182 (required, stripped; blank refused plainly by
P-182's own error), owner scoping (missing / foreign /
unbound -> None), the pure-read law, the HTTP road
(GET /workspaces/unified-search-census: two 404s kept
apart, refusals at 422, states DATA at 200), and the
neighbours (migration head stays 0041). No network.
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
from runmal.workspaces import listing as ls
from runmal.workspaces import unified_search as us
from runmal.workspaces import unified_search_census as usc
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


async def census(factory, store, uid, chat_id, q, subpath=""):
    async with factory() as session:
        return await usc.resolve_chat_unified_search_census(
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


ZERO_SKIPS = {"binary": 0, "folder_not_ready": 0, "oversize": 0,
              "refused": 0, "unreadable": 0}


# ------------------------------------------------------ the census


@pytest.mark.asyncio
async def test_census_of_mixed_bench(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "silver")
    assert doc["schema"] == \
        "runmal-p184-workspace-unified-search-census-v1"
    assert doc["census_state"] == "mixed"
    assert doc["census_state"] in usc.UNIFIED_SEARCH_CENSUS_STATES
    assert doc["query"] == "silver"
    assert doc["folder_state"] == "ready"
    assert doc["subpath"] == ""
    # The returned axis adds up exactly.
    assert doc["match_count"] == 4
    assert doc["name_only_count"] == 1
    assert doc["content_only_count"] == 2
    assert doc["both_match_count"] == 1
    assert doc["name_only_count"] + doc["content_only_count"] \
        + doc["both_match_count"] == doc["match_count"]
    # The source axis rides verbatim beside it.
    assert doc["total_matches"] == 4
    assert doc["source_name_match_count"] == 2
    assert doc["source_content_match_count"] == 3
    assert doc["source_both_count"] == 1
    assert doc["name_total_matches"] == 2
    assert doc["content_total_matches"] == 3
    # Kind, extension, byte, occurrence and depth axes.
    assert doc["kind_counts"] == {"directory": 0, "file": 4,
                                  "other": 0, "symlink": 0}
    assert doc["file_match_count"] == 4
    assert doc["extension_counts"] == {"txt": 4}
    assert doc["total_match_bytes"] == 16 + 22 + 17 + 21
    assert doc["largest_match"] == {
        "name": "report.txt", "path": "report.txt",
        "size_bytes": 22, "matched_by": "content"}
    assert doc["total_occurrences"] == 3
    assert doc["depth_counts"] == {"1": 3, "2": 1}
    assert doc["deepest_level"] == 2
    assert doc["hidden_count"] == 0
    assert doc["escaping_count"] == 0
    # File honesty carried verbatim; nothing skipped.
    assert doc["files_considered"] == 5
    assert doc["files_searched"] == 5
    assert doc["skipped_count"] == 0
    assert doc["skip_outcome_counts"] == ZERO_SKIPS
    assert doc["max_matches"] == us.MAX_MATCHES == 100
    assert doc["max_content_bytes"] == co.MAX_CONTENT_BYTES
    assert doc["truncated"] is False
    assert doc["coverage_complete"] is True
    assert len(doc["notes"]) == 6


@pytest.mark.asyncio
async def test_census_name_only_state(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "notes")
    assert doc["census_state"] == "name_only"
    assert doc["match_count"] == 1
    assert doc["name_only_count"] == 1
    assert doc["content_only_count"] == 0
    assert doc["both_match_count"] == 0
    assert doc["extension_counts"] == {"md": 1}
    assert doc["total_match_bytes"] == 21
    assert doc["largest_match"]["path"] == "notes.md"
    # A name-only match contributes no occurrence count.
    assert doc["total_occurrences"] == 0


@pytest.mark.asyncio
async def test_census_content_only_state(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "thread")
    assert doc["census_state"] == "content_only"
    assert doc["match_count"] == 1
    assert doc["content_only_count"] == 1
    assert doc["name_only_count"] == 0
    assert doc["total_occurrences"] == 1
    assert doc["largest_match"]["path"] == "report.txt"


@pytest.mark.asyncio
async def test_census_no_matches_is_zero_document(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "quartz")
    assert doc["census_state"] == "no_matches"
    assert doc["match_count"] == 0
    assert doc["name_only_count"] == 0
    assert doc["content_only_count"] == 0
    assert doc["both_match_count"] == 0
    assert doc["total_matches"] == 0
    assert doc["kind_counts"] == {"directory": 0, "file": 0,
                                  "other": 0, "symlink": 0}
    assert doc["extension_counts"] == {}
    assert doc["total_match_bytes"] == 0
    assert doc["largest_match"] is None
    assert doc["total_occurrences"] == 0
    assert doc["depth_counts"] == {}
    assert doc["deepest_level"] == 0
    # The folder WAS searched: the file counts say so.
    assert doc["files_considered"] == 5
    assert doc["files_searched"] == 5
    assert doc["truncated"] is False


@pytest.mark.asyncio
async def test_census_non_ready_folder_is_data(tmp_path):
    factory = make_factory(tmp_path)
    uid, chat_id, store = await bound(
        factory, tmp_path, tmp_path / "gone")
    doc = await census(factory, store, uid, chat_id, "any")
    assert doc["census_state"] == "folder_not_ready"
    assert doc["folder_state"] == "missing"
    assert doc["match_count"] == 0
    assert doc["total_matches"] == 0
    assert doc["files_considered"] == 0
    assert doc["files_searched"] == 0
    assert doc["skipped_count"] == 0
    assert doc["skip_outcome_counts"] == ZERO_SKIPS
    assert doc["largest_match"] is None
    assert doc["depth_counts"] == {}
    assert doc["deepest_level"] == 0


@pytest.mark.asyncio
async def test_census_directory_match_has_no_bytes(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "sub")
    assert doc["census_state"] == "name_only"
    assert doc["match_count"] == 1
    assert doc["directory_match_count"] == 1
    assert doc["file_match_count"] == 0
    # A directory carries no size and no extension: the
    # census invents neither.
    assert doc["extension_counts"] == {}
    assert doc["total_match_bytes"] == 0
    assert doc["largest_match"] is None
    assert doc["depth_counts"] == {"1": 1}


# ------------------------------------------------------- skip axis


@pytest.mark.asyncio
async def test_census_skip_outcomes_are_counted(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    (folder / "plain.txt").write_bytes(b"a silver line")
    (folder / "blob.bin").write_bytes(b"silver\x00hidden")
    big = b"silver at the start " + b"x" * co.MAX_CONTENT_BYTES
    (folder / "silver-big.txt").write_bytes(big)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "silver")
    assert doc["census_state"] == "mixed"
    assert doc["skipped_count"] == 2
    assert doc["skip_outcome_counts"] == {
        "binary": 1, "folder_not_ready": 0, "oversize": 1,
        "refused": 0, "unreadable": 0}
    assert doc["files_considered"] == 3
    assert doc["files_searched"] == 1
    assert doc["files_considered"] == \
        doc["files_searched"] + doc["skipped_count"]
    # The oversize file still name-matches beside its skip.
    assert doc["name_only_count"] == 1
    assert doc["content_only_count"] == 1
    assert doc["truncated"] is True
    assert doc["coverage_complete"] is False


# ------------------------------------------------------ cap honesty


@pytest.mark.asyncio
async def test_census_cap_sums_returned_and_carries_totals(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    for i in range(105):
        (folder / f"common-{i:03d}.txt").write_bytes(b"unrelated text")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "common")
    # The census sums the RETURNED matches only...
    assert doc["match_count"] == 100
    assert doc["name_only_count"] == 100
    assert doc["extension_counts"] == {"txt": 100}
    # ...while the source's true total rides verbatim
    # beside the sums - the capped truth, stated twice
    # over and conflated nowhere.
    assert doc["name_total_matches"] == 105
    assert doc["unified_search_document"]["total_matches"] == 100
    assert doc["truncated"] is True
    assert doc["coverage_complete"] is False
    assert doc["census_state"] == "name_only"


# ------------------------------------------------------ query / scope


@pytest.mark.asyncio
async def test_census_query_stripped_and_blank_refused(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "  silver  ")
    assert doc["query"] == "silver" and doc["match_count"] == 4
    for bad in ("", "   ", None):
        with pytest.raises(us.WorkspaceUnifiedSearchError):
            await census(factory, store, uid, chat_id, bad)
    # The pure build half agrees with the resolve half.
    built = usc.build_unified_search_census(
        doc["unified_search_document"])
    assert built == doc


@pytest.mark.asyncio
async def test_census_none_trio_missing_foreign_unbound(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    other = await make_user(factory, "other")
    foreign = await seed_chat(factory, other, "Foreign")
    unbound = await seed_chat(factory, uid, "Unbound")
    assert await census(factory, store, uid, "no-such", "x") is None
    assert await census(factory, store, uid, foreign, "x") is None
    assert await census(factory, store, uid, unbound, "x") is None


@pytest.mark.asyncio
async def test_census_subpath_roots_and_refusal_raises(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "silver", "sub")
    assert doc["subpath"] == "sub"
    assert doc["census_state"] == "content_only"
    assert doc["match_count"] == 1
    # Depth is counted below the composed subpath.
    assert doc["depth_counts"] == {"1": 1}
    assert doc["deepest_level"] == 1
    assert doc["files_considered"] == 1
    with pytest.raises(ls.WorkspaceListingError):
        await census(factory, store, uid, chat_id, "x", "../bench")


# ------------------------------------------------------ axes in depth


@pytest.mark.asyncio
async def test_census_hidden_and_escaping_symlink(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    (folder / ".silver.txt").write_bytes(b"silver dust")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside text")
    os.symlink(outside, folder / "silver-link.txt")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "silver")
    assert doc["hidden_count"] == 1
    assert doc["escaping_count"] == 1
    assert doc["symlink_match_count"] == 1
    assert doc["file_match_count"] == 1
    # The symlink is no file match: no bytes, no extension.
    assert doc["extension_counts"] == {"txt": 1}
    assert doc["total_match_bytes"] == len(b"silver dust")


@pytest.mark.asyncio
async def test_census_occurrences_sum(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    (folder / "a.txt").write_bytes(b"silver silver silver")
    (folder / "silver-b.txt").write_bytes(b"silver")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "silver")
    assert doc["total_occurrences"] == 4
    assert doc["content_only_count"] == 1
    assert doc["both_match_count"] == 1
    assert doc["census_state"] == "mixed"


@pytest.mark.asyncio
async def test_census_extension_law(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    (folder / "UPPER.TXT").write_bytes(b"silver")
    (folder / "SILVERFILE").write_bytes(b"silver")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "silver")
    # Extensions come from names only: lowercased suffix,
    # and no suffix is the honest "(none)" key.
    assert doc["extension_counts"] == {"(none)": 1, "txt": 1}
    assert doc["file_match_count"] == 2


@pytest.mark.asyncio
async def test_census_depth_counts_nested(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    deep = folder / "a" / "b"
    deep.mkdir(parents=True)
    (deep / "deep.txt").write_bytes(b"a silver depth")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "silver")
    assert doc["match_count"] == 1
    assert doc["depth_counts"] == {"3": 1}
    assert doc["deepest_level"] == 3


@pytest.mark.asyncio
async def test_census_largest_match_first_wins_tie(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir()
    (folder / "a.txt").write_bytes(b"silver tie!")
    (folder / "b.txt").write_bytes(b"silver tie!")
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    doc = await census(factory, store, uid, chat_id, "silver")
    assert doc["match_count"] == 2
    assert doc["total_match_bytes"] == 22
    assert doc["largest_match"]["path"] == "a.txt"
    assert doc["largest_match"]["size_bytes"] == 11


@pytest.mark.asyncio
async def test_census_embedded_document_and_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    uid, chat_id, store = await bound(factory, tmp_path, folder)
    before = {str(p): p.read_bytes()
              for p in folder.rglob("*") if p.is_file()}
    store_bytes = store.index_path.read_bytes()
    doc = await census(factory, store, uid, chat_id, "silver")
    async with factory() as session:
        direct = await us.resolve_chat_unified_search(
            session, store, uid, chat_id, "silver")
    # The embedded document IS P-182's own resolve - the
    # census sums that document, never a second search.
    assert doc["unified_search_document"] == direct
    assert doc["binding_document"] == direct["binding_document"]
    after = {str(p): p.read_bytes()
             for p in folder.rglob("*") if p.is_file()}
    assert before == after
    assert store.index_path.read_bytes() == store_bytes
    again = await census(factory, store, uid, chat_id, "silver")
    assert again == doc


# --------------------------------------------------------------- HTTP


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


@pytest.mark.asyncio
async def test_http_unified_search_census_road(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    unbound = await seed_chat(factory, uid, "Unbound")
    store = make_store(tmp_path)
    folder = tmp_path / "bench"; folder.mkdir(); bench(folder)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(folder))
    got = client.get("/api/v1/workspaces/unified-search-census",
                     params={"chat_id": chat_id, "q": "silver"})
    assert got.status_code == 200, got.text
    assert got.json()["census_state"] == "mixed"
    assert got.json()["match_count"] == 4
    assert got.json()["both_match_count"] == 1
    missing = client.get("/api/v1/workspaces/unified-search-census",
                         params={"chat_id": "nope", "q": "x"})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "chat not found"
    unb = client.get("/api/v1/workspaces/unified-search-census",
                     params={"chat_id": unbound, "q": "x"})
    assert unb.status_code == 404
    assert unb.json()["detail"] == "workspace binding not found"
    blank = client.get("/api/v1/workspaces/unified-search-census",
                       params={"chat_id": chat_id, "q": "  "})
    assert blank.status_code == 422
    bad = client.get("/api/v1/workspaces/unified-search-census",
                     params={"chat_id": chat_id, "q": "x",
                             "subpath": "../bench"})
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_http_non_ready_folder_is_data_at_200(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(tmp_path / "gone"))
    got = client.get("/api/v1/workspaces/unified-search-census",
                     params={"chat_id": chat_id, "q": "any"})
    assert got.status_code == 200, got.text
    assert got.json()["census_state"] == "folder_not_ready"
    assert got.json()["folder_state"] == "missing"
    assert got.json()["match_count"] == 0


# ---------------------------------------------------------- neighbours


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
