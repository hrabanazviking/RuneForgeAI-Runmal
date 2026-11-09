"""P-186 Part XI gate battery: Workspaces, whole.

Gate discipline (P-030 / P-048 / P-064 / P-080 / P-100 /
P-116 / P-130 / P-154 / P-168 pattern): the gate builds
no new behaviour; it judges the banked Part XI slices
(P-169..P-185) end to end through their own public
contracts, from measured evidence only. Part XI's slice
definitions are DERIVED (the filed roadmap gives Part XI
only its part line, "XI | Workspaces - the Companion
That Works | P-169 - P-186"); the census this gate
judges is the one the banked slice docs declare.

Relation to P-185, stated plainly: the P-185
reconciliation battery is IN this gate's base and the
gate STANDS ON it - its 24 tests run beside this battery
as neighbours and its verdicts are not re-derived here.
This battery RE-MEASURES, on a fresh gate world
(ZqxGate186, query "copper", a shape P-185 never built),
the load-bearing cross-surface arithmetic the gate
verdict rests on, and it alone judges P-185 itself
(present exactly once, doc + battery + init bullet) and
the gate-shape facts P-185 could not state (the full
P-169..P-185 row census and the exact package file
census). Where a check repeats a P-185 measurement in
kind, it does so on the new world and says so.

- Area A (census): every P-169..P-185 surface present
  exactly once - 17 slice docs, 14 truth modules, 12
  router modules, 15 unique v1 schemas, the __init__
  map, OpenAPI naming exactly the 18 workspace roads,
  the P-185 battery accounted, migration head 0041.
- Area B (together): the fresh gate world exercised
  through every surface; estate, folder, tree, content,
  unified and history arithmetic reconciles exactly.
- Area C (custody / honesty): every resolve a pure
  read, no census retains file content, owner scoping
  holds everywhere, mutating roads exactly the three
  banked writes, no write / execution / watching
  surface exists.
- Area D (accounting): the carried items pinned ABSENT
  by measurement (label update, retention / bulk clear,
  unified-search history, watching, execution), the
  package file census exact, and depth-cap truncated
  honesty reconciled on the gate world.
- Hygiene: migration head stays 0041; the gate world
  lives only in this battery.

Clean-room note: the gate world is fresh-authored for
this gate (P-005 discipline); no SillyTavern or Voxta
source was inspected, and no real user files are read.
Plain pytest functions, no test classes. No network.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import os
from pathlib import Path

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
from runmal.workspaces import census as ce
from runmal.workspaces import content as co
from runmal.workspaces import content_census as cc
from runmal.workspaces import content_search as cs
from runmal.workspaces import folder_census as fc
from runmal.workspaces import history as hi
from runmal.workspaces import history_census as hc
from runmal.workspaces import listing as ls
from runmal.workspaces import search as se
from runmal.workspaces import tree as tr
from runmal.workspaces import tree_census as tc
from runmal.workspaces import unified_search as us
from runmal.workspaces import unified_search_census as usc

REPO = Path(__file__).parent.parent
SECRET = "ZqxGate186Secret"
QUERY = "copper"

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


async def seed_chat(factory, uid, title):
    async with factory() as session:
        chat = await chats_svc.create_chat(
            session, uid, title=title, character_id=None,
            greeting=GreetingChoice(mode="quiet"))
        await session.commit()
        return chat.id


def bench(folder):
    (folder / "alpha.txt").write_bytes(b"the copper thread runs\n")
    (folder / "beta.md").write_bytes(b"plain water only\n")
    (folder / "copper-song.txt").write_bytes(b"copper bells ring\n")
    (folder / ".hidden.txt").write_bytes(b"copper hidden note\n")
    (folder / "secret.txt").write_bytes(
        (SECRET + " never censused\n").encode())
    (folder / "blob.bin").write_bytes(bytes(range(256)))
    (folder / "big.txt").write_bytes(b"x" * (co.MAX_CONTENT_BYTES + 10))
    sub = folder / "sub"
    sub.mkdir()
    (sub / "inner.txt").write_bytes(b"a copper lining waits\n")
    (sub / "deep-note.txt").write_bytes(b"nothing here\n")
    os.symlink("alpha.txt", folder / "link-in")
    os.symlink("/etc/passwd", folder / "link-out")
    return sub


async def world(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    c1 = await seed_chat(factory, uid, "One")
    c2 = await seed_chat(factory, uid, "Two")
    c3 = await seed_chat(factory, uid, "Three")
    c4 = await seed_chat(factory, uid, "Four")
    store = make_store(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    bench(folder)
    ws.register_binding(store, owner_id=uid, chat_id=c1,
                        folder_path=str(folder), label="bench")
    ws.register_binding(store, owner_id=uid, chat_id=c2,
                        folder_path=str(folder))
    ws.register_binding(store, owner_id=uid, chat_id=c4,
                        folder_path=str(tmp_path / "gone"))
    return factory, uid, (c1, c2, c3, c4), store, folder


async def resolve_all(factory, store, uid, chat_id, query=QUERY):
    async with factory() as session:
        return {
            "binding": await ws.resolve_chat_workspace(
                session, store, uid, chat_id),
            "listing": await ls.resolve_chat_listing(
                session, store, uid, chat_id),
            "folder_census": await fc.resolve_chat_folder_census(
                session, store, uid, chat_id),
            "tree": await tr.resolve_chat_tree(
                session, store, uid, chat_id, "", tr.MAX_DEPTH),
            "tree_census": await tc.resolve_chat_tree_census(
                session, store, uid, chat_id),
            "content_census": await cc.resolve_chat_content_census(
                session, store, uid, chat_id),
            "search": await se.resolve_chat_search(
                session, store, uid, chat_id, query),
            "content_search": await cs.resolve_chat_content_search(
                session, store, uid, chat_id, query),
            "unified": await us.resolve_chat_unified_search(
                session, store, uid, chat_id, query),
            "unified_census": await
            usc.resolve_chat_unified_search_census(
                session, store, uid, chat_id, query),
        }


def walk_nodes(node, prefix=""):
    rows = []
    for child in node.get("children") or []:
        path = prefix + child["name"]
        rows.append((path, child))
        rows.extend(walk_nodes(child, path + "/"))
    return rows

# ---------------------------------------------------------- Area A

SLICE_DOCS = [
    "WORKSPACE_BINDING_2026-11-09.md",
    "WORKSPACE_LISTING_2026-11-09.md",
    "WORKSPACE_CENSUS_2026-11-09.md",
    "WORKSPACE_CONTENT_READ_2026-11-09.md",
    "WORKSPACE_BINDING_HISTORY_2026-11-09.md",
    "WORKSPACE_FOLDER_CENSUS_2026-11-09.md",
    "WORKSPACE_HISTORY_DELETION_2026-11-09.md",
    "WORKSPACE_FOLDER_TREE_2026-11-09.md",
    "WORKSPACE_HISTORY_CENSUS_2026-11-09.md",
    "WORKSPACE_FILENAME_SEARCH_2026-11-09.md",
    "WORKSPACE_TREE_TRUNCATED_FIX_2026-11-09.md",
    "WORKSPACE_CONTENT_SEARCH_2026-11-09.md",
    "WORKSPACE_TREE_CENSUS_2026-11-09.md",
    "WORKSPACE_UNIFIED_SEARCH_2026-11-09.md",
    "WORKSPACE_CONTENT_CENSUS_2026-11-09.md",
    "WORKSPACE_UNIFIED_SEARCH_CENSUS_2026-11-09.md",
    "WORKSPACE_RECONCILIATION_2026-11-09.md",
]

TRUTH_MODULES = {
    "bindings": "resolve_chat_workspace",
    "listing": "resolve_chat_listing",
    "census": "resolve_workspace_census",
    "content": "resolve_chat_content",
    "history": "resolve_workspace_history",
    "folder_census": "resolve_chat_folder_census",
    "tree": "resolve_chat_tree",
    "history_census": "resolve_workspace_history_census",
    "search": "resolve_chat_search",
    "content_search": "resolve_chat_content_search",
    "tree_census": "resolve_chat_tree_census",
    "unified_search": "resolve_chat_unified_search",
    "content_census": "resolve_chat_content_census",
    "unified_search_census": "resolve_chat_unified_search_census",
}

ROUTER_MODULES = [
    "router", "census_router", "history_router",
    "folder_census_router", "tree_router",
    "history_census_router", "search_router",
    "content_search_router", "tree_census_router",
    "unified_search_router", "content_census_router",
    "unified_search_census_router",
]

SCHEMAS = [
    ws.BINDING_SCHEMA, ws.LIST_SCHEMA, ws.HISTORY_SCHEMA,
    ls.LISTING_SCHEMA, ce.CENSUS_SCHEMA, co.CONTENT_SCHEMA,
    fc.FOLDER_CENSUS_SCHEMA, tr.TREE_SCHEMA,
    hc.HISTORY_CENSUS_SCHEMA, se.SEARCH_SCHEMA,
    cs.CONTENT_SEARCH_SCHEMA, tc.TREE_CENSUS_SCHEMA,
    us.UNIFIED_SEARCH_SCHEMA, cc.CONTENT_CENSUS_SCHEMA,
    usc.UNIFIED_SEARCH_CENSUS_SCHEMA,
]

EXPECTED_ROADS = {
    ("POST", "/api/v1/workspaces/bindings"),
    ("GET", "/api/v1/workspaces/bindings"),
    ("GET", "/api/v1/workspaces"),
    ("DELETE", "/api/v1/workspaces/bindings/{binding_id}"),
    ("GET", "/api/v1/workspaces/files"),
    ("GET", "/api/v1/workspaces/content"),
    ("GET", "/api/v1/workspaces/census"),
    ("GET", "/api/v1/workspaces/history"),
    ("DELETE", "/api/v1/workspaces/history/{entry_id}"),
    ("GET", "/api/v1/workspaces/folder-census"),
    ("GET", "/api/v1/workspaces/tree"),
    ("GET", "/api/v1/workspaces/history-census"),
    ("GET", "/api/v1/workspaces/search"),
    ("GET", "/api/v1/workspaces/content-search"),
    ("GET", "/api/v1/workspaces/tree-census"),
    ("GET", "/api/v1/workspaces/unified-search"),
    ("GET", "/api/v1/workspaces/content-census"),
    ("GET", "/api/v1/workspaces/unified-search-census"),
}


def test_a_slice_docs_all_present():
    for name in SLICE_DOCS:
        assert (REPO / "docs" / name).is_file(), name
    assert len(SLICE_DOCS) == 17  # P-169..P-185, one doc each


def test_a_truth_modules_and_resolvers_present():
    for mod_name, resolver in TRUTH_MODULES.items():
        mod = importlib.import_module(
            f"runmal.workspaces.{mod_name}")
        assert callable(getattr(mod, resolver)), mod_name


def test_a_router_modules_present():
    for mod_name in ROUTER_MODULES:
        mod = importlib.import_module(
            f"runmal.workspaces.{mod_name}")
        assert getattr(mod, "router") is not None, mod_name


def test_a_schemas_unique_and_versioned():
    assert len(SCHEMAS) == 15
    assert len(set(SCHEMAS)) == 15
    for schema in SCHEMAS:
        assert schema.startswith("runmal-p1")
        assert schema.endswith("-v1")


def test_a_init_map_accounts_for_every_module():
    init_text = (REPO / "src" / "runmal" / "workspaces"
                 / "__init__.py").read_text()
    for name in list(TRUTH_MODULES) + ROUTER_MODULES:
        assert name in init_text, name
    assert "test_p185_workspace_reconciliation.py" in init_text


def test_a_openapi_names_exactly_the_workspace_roads(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    roads = set()
    for path, ops in spec.json()["paths"].items():
        if "/workspaces" in path:
            for method in ops:
                roads.add((method.upper(), path))
    assert roads == EXPECTED_ROADS


def test_a_p185_reconciliation_battery_stands_in_base():
    # The gate stands on P-185: its battery is in this base
    # with its full 24 tests and its doc; the gate does not
    # re-derive its verdicts, it runs them as neighbours.
    path = REPO / "tests" / "test_p185_workspace_reconciliation.py"
    assert path.is_file()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tests = [n.name for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name.startswith("test_")]
    assert len(tests) == 24
    assert (REPO / "docs" / "WORKSPACE_RECONCILIATION_2026-11-09.md").is_file()


def test_a_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0041"
    assert len([p for p in (REPO / "src" / "runmal" / "db"
                            / "migrations").glob("m0042*")]) == 0

# ---------------------------------------------------------- Area B
# Re-measured on the fresh gate world (query "copper");
# P-185 measured the same arithmetic on its own world.

@pytest.mark.asyncio
async def test_b_binding_document_agrees_everywhere(tmp_path):
    factory, uid, (c1, *_), store, _ = await world(tmp_path)
    docs = await resolve_all(factory, store, uid, c1)
    binding = docs["binding"]
    assert binding is not None
    assert docs["listing"]["binding_document"] == binding
    assert docs["folder_census"]["listing_document"] == docs["listing"]
    assert docs["tree"]["binding_document"] == binding
    assert docs["tree"]["root_listing"] == docs["listing"]
    for key in ("folder_census", "tree", "tree_census",
                "content_census", "search", "content_search",
                "unified", "unified_census"):
        assert docs[key]["folder_state"] == "ready", key


@pytest.mark.asyncio
async def test_b_estate_census_reconciles_with_bindings(tmp_path):
    factory, uid, chats, store, folder = await world(tmp_path)
    async with factory() as session:
        census = await ce.resolve_workspace_census(session, store, uid)
        owner = await ws.list_owner_workspaces(session, store, uid)
    assert census["chat_count"] == 4
    assert census["binding_count"] == 3
    assert census["bound_chat_count"] == 3
    assert census["unbound_chat_count"] == 1
    assert census["bound_chat_count"] + census["unbound_chat_count"] == census["chat_count"]
    assert census["ready_count"] == 2
    assert census["missing_count"] == 1
    assert sum(census["folder_state_counts"].values()) == 3
    assert census["distinct_folder_count"] == 2
    assert census["shared_folder_count"] == 1
    assert census["bindings_on_shared_folders"] == 2
    assert census["workspaces"] == owner["workspaces"]
    assert census["census_state"] == "some_ready"


@pytest.mark.asyncio
async def test_b_tree_census_reconciles_with_tree_walk(tmp_path):
    factory, uid, (c1, *_), store, _ = await world(tmp_path)
    docs = await resolve_all(factory, store, uid, c1)
    tree, census = docs["tree"], docs["tree_census"]
    assert census["tree_document"] == tree
    nodes = walk_nodes(tree["tree"])
    assert census["node_count"] == tree["node_count"] == len(nodes)
    for kind in ("directory", "file", "symlink", "other"):
        assert census["kind_counts"][kind] == sum(1 for _, n in nodes if n["kind"] == kind), kind
    assert census["total_file_bytes"] == sum(n["size_bytes"] for _, n in nodes if n["kind"] == "file")
    folder_census = docs["folder_census"]
    level_one = [(p, n) for p, n in nodes if "/" not in p]
    assert folder_census["entry_count"] == len(level_one)
    assert folder_census["total_file_bytes"] == sum(n["size_bytes"] for _, n in level_one if n["kind"] == "file")


@pytest.mark.asyncio
async def test_b_content_census_reconciles_with_reads(tmp_path):
    factory, uid, (c1, *_), store, _ = await world(tmp_path)
    docs = await resolve_all(factory, store, uid, c1)
    census = docs["content_census"]
    nodes = walk_nodes(docs["tree"]["tree"])
    file_paths = [p for p, n in nodes if n["kind"] == "file"]
    assert census["files_considered"] == len(file_paths)
    assert sum(census["outcome_counts"].values()) == len(file_paths)
    async with factory() as session:
        binding = await ws.resolve_chat_workspace(session, store, uid, c1)
        folder_path = binding["binding"]["folder_path"]
        outcomes = {}
        readable_bytes = 0
        for path in file_paths:
            read = co.build_content_read(binding, folder_path, path)
            outcomes[path] = read["outcome"]
            if read["outcome"] == "ok":
                readable_bytes += read["size_bytes"]
    assert census["readable_count"] == sum(1 for o in outcomes.values() if o == "ok")
    assert census["total_readable_bytes"] == readable_bytes
    unreadable = {row["path"]: row["outcome"] for row in census["unreadable_files"]}
    assert unreadable == {p: o for p, o in outcomes.items() if o != "ok"}
    skipped = {row["path"]: row["outcome"] for row in docs["content_search"]["skipped_files"]}
    assert skipped == unreadable


@pytest.mark.asyncio
async def test_b_unified_search_is_the_union_of_the_searches(tmp_path):
    factory, uid, (c1, *_), store, _ = await world(tmp_path)
    docs = await resolve_all(factory, store, uid, c1)
    name_paths = {m["path"] for m in docs["search"]["matches"]}
    content_paths = {m["path"] for m in docs["content_search"]["matches"]}
    unified = docs["unified"]
    assert unified["name_search_document"] == docs["search"]
    assert unified["content_search_document"] == docs["content_search"]
    assert unified["tree_document"] == docs["tree"]
    by_path = {m["path"]: m for m in unified["matches"]}
    assert set(by_path) == name_paths | content_paths
    for path, match in by_path.items():
        expected = ("both" if path in name_paths and path in content_paths else "name" if path in name_paths else "content")
        assert match["matched_by"] == expected, path
    assert unified["both_count"] == len(name_paths & content_paths)
    assert unified["match_count"] == len(name_paths | content_paths)
    census = docs["unified_census"]
    assert census["unified_search_document"] == unified
    assert census["match_count"] == unified["match_count"]
    assert census["census_state"] == "mixed"


@pytest.mark.asyncio
async def test_b_history_census_reconciles_with_history(tmp_path):
    factory, uid, (c1, c2, *_), store, folder = await world(tmp_path)
    binding_c2 = store.get_for_chat(c2)
    store.remove_binding(binding_c2.id)
    async with factory() as session:
        assert await chats_svc.delete_chat(session, uid, c1) is True
        await session.commit()
    async with factory() as session:
        history = await hi.resolve_workspace_history(session, store, uid)
        census = await hc.resolve_workspace_history_census(session, store, uid)
        estate = await ce.resolve_workspace_census(session, store, uid)
    assert history["entry_count"] == 2
    assert history["unbound_count"] == 1
    assert history["chat_deleted_count"] == 1
    assert census["history_document"] == history
    assert census["live_chat_entry_count"] == 1
    assert census["gone_chat_entry_count"] == 1
    assert census["census_state"] == "some_live_chats"
    assert estate["binding_count"] == 1


@pytest.mark.asyncio
async def test_b_non_ready_folder_is_data_everywhere(tmp_path):
    factory, uid, chats, store, _ = await world(tmp_path)
    c4 = chats[3]
    docs = await resolve_all(factory, store, uid, c4)
    assert docs["binding"]["folder_state"] == "missing"
    assert docs["listing"]["entries"] == []
    assert docs["folder_census"]["census_state"] == "folder_not_ready"
    assert docs["tree_census"]["census_state"] == "folder_not_ready"
    assert docs["content_census"]["census_state"] == "folder_not_ready"
    assert docs["unified_census"]["census_state"] == "folder_not_ready"
    c3 = chats[2]
    docs3 = await resolve_all(factory, store, uid, c3)
    assert all(doc is None for doc in docs3.values())

# ---------------------------------------------------------- Area C

def _folder_snapshot(folder):
    snap = {}
    for path in sorted(folder.rglob("*")):
        rel = str(path.relative_to(folder))
        if path.is_symlink():
            snap[rel] = ("symlink", os.readlink(path))
        elif path.is_dir():
            snap[rel] = ("directory", None)
        else:
            snap[rel] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
    return snap


@pytest.mark.asyncio
async def test_c_every_resolve_is_a_pure_read(tmp_path):
    factory, uid, (c1, *_), store, folder = await world(tmp_path)
    store_bytes = store.index_path.read_bytes()
    folder_before = _folder_snapshot(folder)
    first = await resolve_all(factory, store, uid, c1)
    async with factory() as session:
        await ce.resolve_workspace_census(session, store, uid)
        await hi.resolve_workspace_history(session, store, uid)
        await hc.resolve_workspace_history_census(session, store, uid)
    second = await resolve_all(factory, store, uid, c1)
    assert store.index_path.read_bytes() == store_bytes
    assert _folder_snapshot(folder) == folder_before
    assert first == second


@pytest.mark.asyncio
async def test_c_no_census_retains_file_content(tmp_path):
    factory, uid, (c1, *_), store, _ = await world(tmp_path)
    docs = await resolve_all(factory, store, uid, c1)
    async with factory() as session:
        estate = await ce.resolve_workspace_census(session, store, uid)
    censuses = [docs["folder_census"], docs["tree_census"], docs["content_census"], docs["unified_census"], estate]
    for doc in censuses:
        assert SECRET not in json.dumps(doc), doc["schema"]
    async with factory() as session:
        binding = await ws.resolve_chat_workspace(session, store, uid, c1)
    read = co.build_content_read(binding, binding["binding"]["folder_path"], "secret.txt")
    assert read["outcome"] == "ok" and SECRET in read["content"]


@pytest.mark.asyncio
async def test_c_owner_scoping_holds_on_every_surface(tmp_path):
    factory, uid, (c1, *_), store, _ = await world(tmp_path)
    other = await make_user(factory, "mallory")
    foreign = await resolve_all(factory, store, other, c1)
    assert all(doc is None for doc in foreign.values())
    async with factory() as session:
        estate = await ce.resolve_workspace_census(session, store, other)
        history = await hi.resolve_workspace_history(session, store, other)
    assert estate["binding_count"] == 0
    assert estate["census_state"] == "no_chats"
    assert history["entry_count"] == 0


def test_c_mutating_roads_are_exactly_the_banked_writes(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    paths = client.get("/openapi.json").json()["paths"]
    mutating = {(method.upper(), path) for path, ops in paths.items() if "/workspaces" in path for method in ops if method.upper() != "GET"}
    assert mutating == {
        ("POST", "/api/v1/workspaces/bindings"),
        ("DELETE", "/api/v1/workspaces/bindings/{binding_id}"),
        ("DELETE", "/api/v1/workspaces/history/{entry_id}"),
    }


@pytest.mark.asyncio
async def test_c_http_roads_answer_together(tmp_path):
    factory, uid, (c1, *_), store, folder = await world(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    base = "/api/v1/workspaces"
    checks = [
        ("/census", {}, "chat_count", 4),
        ("/folder-census", {"chat_id": c1}, "entry_count", 10),
        ("/tree", {"chat_id": c1}, "node_count", 12),
        ("/tree-census", {"chat_id": c1}, "file_count", 9),
        ("/content-census", {"chat_id": c1}, "files_considered", 9),
        ("/search", {"chat_id": c1, "q": QUERY}, "match_count", 1),
        ("/content-search", {"chat_id": c1, "q": QUERY}, "match_count", 4),
        ("/unified-search", {"chat_id": c1, "q": QUERY}, "match_count", 4),
        ("/unified-search-census", {"chat_id": c1, "q": QUERY}, "match_count", 4),
        ("/history-census", {}, "entry_count", 0),
        ("/history", {}, "entry_count", 0),
    ]
    for suffix, params, key, expected in checks:
        got = client.get(base + suffix, params=params)
        assert got.status_code == 200, (suffix, got.text)
        assert got.json()[key] == expected, suffix


# ---------------------------------------------------------- Area D

PACKAGE_FILES = {
    "__init__.py", "bindings.py", "census.py", "census_router.py",
    "content.py", "content_census.py", "content_census_router.py",
    "content_search.py", "content_search_router.py",
    "folder_census.py", "folder_census_router.py", "history.py",
    "history_census.py", "history_census_router.py",
    "history_router.py", "listing.py", "router.py", "search.py",
    "search_router.py", "tree.py", "tree_census.py",
    "tree_census_router.py", "tree_router.py", "unified_search.py",
    "unified_search_census.py", "unified_search_census_router.py",
    "unified_search_router.py",
}


def test_d_package_file_census_exact():
    ws_dir = REPO / "src" / "runmal" / "workspaces"
    names = {p.name for p in ws_dir.glob("*.py")}
    assert names == PACKAGE_FILES
    assert len(names) == 27  # no write / exec / watch module exists


def test_d_carried_items_pinned_absent():
    ws_dir = REPO / "src" / "runmal" / "workspaces"
    names = {p.name for p in ws_dir.glob("*.py")}
    for forbidden in ("label", "retention", "watch", "exec", "search_history", "bulk"):
        assert not any(forbidden in n for n in names), forbidden
    verbs = [n for n in dir(ws) if not n.startswith("_")]
    assert not any("label" in n.lower() and ("update" in n.lower() or "set" in n.lower() or "rename" in n.lower()) for n in verbs)
    assert not any("retention" in n.lower() or "bulk" in n.lower() for n in verbs)
    store_verbs = [n for n in dir(ws.WorkspaceStore) if not n.startswith("_")]
    assert "remove_history_entry" in store_verbs
    assert not any("clear" in n.lower() for n in store_verbs)


@pytest.mark.asyncio
async def test_d_depth_cap_truncation_reconciles(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid, "Deep")
    store = make_store(tmp_path)
    folder = tmp_path / "deep"
    folder.mkdir()
    level = folder
    for name in ("d1", "d2", "d3", "d4", "d5"):
        level = level / name
        level.mkdir()
        (level / "leaf.txt").write_bytes(b"copper at depth\n")
    ws.register_binding(store, owner_id=uid, chat_id=chat_id, folder_path=str(folder))
    docs = await resolve_all(factory, store, uid, chat_id)
    assert docs["tree"]["truncated"] is True
    assert docs["tree_census"]["truncated"] is True
    assert docs["content_census"]["truncated"] is True
    assert docs["content_census"]["coverage_complete"] is False
    assert docs["search"]["truncated"] is True
    assert docs["content_census"]["files_considered"] < 5


# ---------------------------------------------------------- Hygiene

def test_h_migration_head_and_gate_scope():
    assert MIGRATIONS[-1][0] == "0041"


def test_h_gate_world_marker_lives_only_in_gate_files():
    hits = []
    for path in (REPO / "src").rglob("*.py"):
        if "ZqxGate186" in path.read_text(encoding="utf-8", errors="ignore"):
            hits.append(str(path))
    assert hits == []
