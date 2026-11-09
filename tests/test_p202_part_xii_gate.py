"""P-202 Part XII gate battery: The Hub, whole.

Gate discipline (P-030 / P-116 / P-186 pattern): the
gate builds no new behaviour; it judges the banked
Part XII slices (P-187..P-201) end to end through
their own public contracts, from measured evidence
only. Part XII's slice definitions are DERIVED (the
filed roadmap gives Part XII only its part line,
"XII | The Hub, Sovereign Shape | P-187..P-202");
the census this gate judges is the one the banked
slice docs declare.

Relation to P-201, stated plainly: the P-201 hub
reconciliation battery is IN this gate's base and the
gate STANDS ON it - its 26 tests run beside this
battery as neighbours and its verdicts are not
re-derived here. This battery RE-MEASURES, on a fresh
gate world (ZqxGate202, nonce query, a shape P-201
never built), the load-bearing cross-surface
arithmetic the gate verdict rests on, and it alone
judges P-201 itself (present exactly once, doc +
battery + clean-room entry) and the exact package
file census P-201 did not state.

- Area A (census x9): every P-187..P-201 surface
  present exactly once - 15 slice docs, 15 hub
  modules (14 truth + router), 15 schema tags, 17
  OpenAPI operations on 16 paths, P-201 accounted,
  migration head 0041, one-law objects, exact
  package census (16 files).
- Area B (together x12): the fresh gate world
  exercised through every surface; list, browse,
  six-census, string-volume, structure, duplicate,
  size, unified-union, refusal, kind-narrowing,
  truncation and register arithmetic reconciles.
- Area C (custody x5): every read a pure read, no
  census retains content, owner scoping everywhere,
  mutating roads exactly the two banked writes, one
  HTTP session walks all 17 operations dict-equal.
- Area D (accounting x6): carried items K-A..K-H
  pinned absent or present-as-law at full strength,
  and the honest limitations L-2 / L-4 / L-7 pinned
  (oversize is INVALID on the tree as banked - the
  design text's "unavailable" wording does not hold
  against the banked P-188 / P-193 batteries, and
  this gate pins the tree's own verdict).
- Hygiene x2: migration head stays 0041; the gate
  world marker lives only in gate files.

Clean-room note: the gate world is fresh-authored
for this gate (P-005 discipline); no SillyTavern or
Voxta source was inspected, and no real user files
are read. Plain pytest functions, no test classes.
No network.
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
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.hub import breadth_census as hub_breadth
from runmal.hub import browse as hub_browse
from runmal.hub import census as hub_census
from runmal.hub import content_census as hub_cc
from runmal.hub import content_search as hub_cs
from runmal.hub import content_shape_census as hub_shape
from runmal.hub import distinct_census as hub_distinct
from runmal.hub import duplicate_census as hub_dup
from runmal.hub import registry as hub
from runmal.hub import schema_census as hub_schema
from runmal.hub import search as hub_search
from runmal.hub import size_census as hub_size
from runmal.hub import unified_search as hub_unified
from runmal.hub import unified_search_census as hub_usc
from runmal.lorebooks import packs as lorebook_packs
from runmal.plugins import service as plugin_service
from runmal.presets import bundles as preset_bundles
from runmal.presets import packs as prompt_packs
from runmal.scenarios import packs as scenario_packs
from runmal.scenarios.store import ScenarioStore

REPO = Path(__file__).parent.parent
STAMP = "2026-11-09T00:00:00+00:00"
NONCE = "ZqxGate202Nonce"


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
    return hub.HubStore(tmp_path / "data")


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


def _register(store, kind, title, locator, sha="", owner="u1"):
    return hub.register_entry(
        store, owner_id=owner, kind=kind, title=title,
        locator=locator, content_sha256=sha)

# ------------------------------------------------------------ pack fixtures
# Fresh-authored for this gate in the P-199 / P-200 /
# P-201 fixture pattern: four pack builders, one per
# hub kind, all content carrying the Zephyr texts.


def _lore_entry(eid, name, content, keys):
    return {
        "id": eid, "lorebook_id": "book-1", "name": name,
        "content": content, "keys": keys, "secondary_keys": [],
        "selective_logic": "and_any", "inclusion_group": "",
        "group_weight": 100, "probability": 100, "priority": 100,
        "position": "before_char", "depth": None, "role": "system",
        "enabled": True, "constant": False, "vectorised": False,
        "case_sensitive": False, "whole_word": True,
        "sticky_prompts": 0, "cooldown_prompts": 0,
        "delay_prompts": 0,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": None,
    }


def _lorebook_file(base, name="lorebook-pack.json", entries=None):
    if entries is None:
        entries = [_lore_entry(
            "e1", "Mist Entry",
            "The Zephyr Quill writes storms.", ["quill"])]
    book = {
        "id": "book-1", "name": "Plain Book",
        "description": "World lore.", "scan_depth": 7,
        "token_budget": 900, "scan_mode": "depth",
        "scan_external_context": False,
        "created_at": "2026-01-01T00:00:00+00:00",
        "entry_count": len(entries),
    }
    pack = lorebook_packs.build_pack(book, entries, exported_at=STAMP)
    path = base / name
    path.write_bytes(lorebook_packs.pack_to_bytes(pack))
    return str(path), pack


def _prompt_file(base):
    item = {
        "kind": "preset", "name": "Hall Preset",
        "payload": {
            "name": "Hall Preset",
            "params": {"temperature": 0.7},
            "template_ref": "", "source_format": "st-chat",
            "raw": {"temperature": 0.7},
            "prompts": [{"identifier": "main",
                        "content": "Zephyr prompt text for the hall."}],
            "prompt_order": [{"identifier": "main", "enabled": True}],
        },
    }
    pack = prompt_packs.build_pack("Workshop", [item], exported_at=STAMP)
    path = base / "prompt-pack.json"
    path.write_bytes(prompt_packs.pack_to_bytes(pack))
    return str(path), pack


def _scenario_file(base):
    store = ScenarioStore(base / "scenarios.json")
    body = {
        "name": "Harbour Lights",
        "description": "A quiet harbour.",
        "scenario_text": "The Zephyr ferry has just left.",
        "flow": "story", "style": "storytelling",
        "narrator_name": "The Harbour Voice",
        "impersonation_name": "Ash",
        "roles": [{"name": "Narrator", "character_name": "Maera",
                   "enabled_on_start": True, "can_speak": True}],
        "bootstrap_messages": [
            {"kind": "note", "text": "The tide is going out.",
             "role": "Narrator"}],
        "initial_flags": {"met_maera": True},
        "initial_variables": {"trust": 2},
    }
    record = store.create("owner-p202", body, now=STAMP)
    pack = scenario_packs.build_pack(record, exported_at=STAMP)
    path = base / "scenario-pack.json"
    path.write_bytes(scenario_packs.pack_to_bytes(pack))
    return str(path), pack


def _bundle_file(base, *, bare: bool = False):
    bundle = preset_bundles.validate_bundle({
        "name": "Hall Bundle",
        "prompts": [{"identifier": "main",
                     "content": "Zephyr bundle text for the hall."}],
        "prompt_order": [{"identifier": "main", "enabled": True}],
    })
    share = preset_bundles.build_share(bundle, exported_at=STAMP)
    path = base / "preset-bundle.json"
    if bare:
        path.write_text(json.dumps(bundle))
        return str(path), bundle
    path.write_text(json.dumps(share))
    return str(path), share

# ------------------------------------------------------------ the gate world
# ZqxGate202: 9 entries for owner u1 - the full four-
# kind verified estate, the same lorebook pack again
# under a second locator (the duplicate group), one
# bare bundle, one missing locator, one broken pack,
# one wrong-kind payload. Parsed 6, unavailable 1,
# invalid 2. Claimed checksums on the verified packs;
# the bare / ghost / broken / wrong entries unclaimed.


def _gate_estate(tmp_path, store, owner="u1"):
    base = tmp_path / "gate-full"
    base.mkdir(parents=True, exist_ok=True)
    entries = []
    for kind, maker, title in (
            ("lorebook_pack", _lorebook_file, "Gate Lore Pack"),
            ("prompt_pack", _prompt_file, "Gate Prompt Pack"),
            ("scenario_pack", _scenario_file, "Gate Scenario Pack"),
            ("preset_bundle", _bundle_file, "Gate Bundle Pack")):
        locator, pack = maker(base)
        sha = pack["manifest"]["content_sha256"] \
            if "manifest" in pack else ""
        entries.append(_register(store, kind, title, locator, sha,
                                 owner=owner))
    copy_path = base / "lorebook-copy.json"
    copy_path.write_bytes(Path(entries[0].locator).read_bytes())
    entries.append(_register(
        store, "lorebook_pack", "Gate Lore Copy Pack",
        str(copy_path), entries[0].content_sha256, owner=owner))
    bare_dir = tmp_path / "gate-bare"
    bare_dir.mkdir(parents=True, exist_ok=True)
    locator, _bundle = _bundle_file(bare_dir, bare=True)
    entries.append(_register(store, "preset_bundle", "Gate Bare Pack",
                             locator, owner=owner))
    entries.append(_register(
        store, "prompt_pack", "Gate Ghost Pack",
        str(tmp_path / "gate-ghost.json"), owner=owner))
    bad = tmp_path / "gate-broken.json"
    bad.write_bytes(b"{not a pack")
    entries.append(_register(store, "scenario_pack", "Gate Broken Pack",
                             str(bad), owner=owner))
    wrong_dir = tmp_path / "gate-wrong"
    wrong_dir.mkdir(parents=True, exist_ok=True)
    locator, _pack = _prompt_file(wrong_dir)
    entries.append(_register(store, "lorebook_pack", "Gate Wrong Pack",
                             locator, owner=owner))
    return entries


def _probe_estate(tmp_path, store, owner="u1"):
    """Three lorebook packs splitting the nonce answer:
    one matched on both sides, one content-only, one
    metadata-only (the B8 union probe)."""
    base = tmp_path / "gate-probe"
    base.mkdir(parents=True, exist_ok=True)
    specs = [
        (NONCE + " Tales", "both.json", "Tale Entry",
         "The " + NONCE + " Quill writes storms."),
        ("Plain Tales", "content.json", "Wind Entry",
         NONCE + " winds rise at dawn."),
        (NONCE + " Index", "meta.json", "Index Entry",
         "Calm waters hold still."),
    ]
    entries = []
    for title, fname, ename, content in specs:
        locator, pack = _lorebook_file(
            base, fname,
            entries=[_lore_entry("e1", ename, content, ["quill"])])
        entries.append(_register(
            store, "lorebook_pack", title, locator,
            pack["manifest"]["content_sha256"], owner=owner))
    return entries


def _truncation_estate(tmp_path, store, owner="u1"):
    entries = []
    for i in range(hub_search.MAX_MATCHES + 1):
        entries.append(_register(
            store, "lorebook_pack", f"Match Pack {i}",
            f"/packs/m{i}.json", owner=owner))
    return entries


PARSE_CENSUSES = [
    (hub_cc, "content_census_document", hub_cc.CONTENT_CENSUS_STATES,
     "no_content", "some_content", "all_content"),
    (hub_shape, "content_shape_census_document",
     hub_shape.SHAPE_CENSUS_STATES,
     "no_shape", "some_shape", "all_shape"),
    (hub_size, "size_census_document", hub_size.SIZE_CENSUS_STATES,
     "no_sizes", "some_sizes", "all_sizes"),
    (hub_breadth, "breadth_census_document",
     hub_breadth.BREADTH_CENSUS_STATES,
     "no_breadth", "some_breadth", "all_breadth"),
    (hub_distinct, "distinct_census_document",
     hub_distinct.DISTINCT_CENSUS_STATES,
     "no_distinct", "some_distinct", "all_distinct"),
    (hub_schema, "schema_census_document",
     hub_schema.SCHEMA_CENSUS_STATES,
     "no_schema", "some_schema", "all_schema"),
]


def _parse_docs(entries):
    return {mod.__name__.rsplit(".", 1)[-1]: getattr(mod, fn)(entries)
            for mod, fn, *_rest in PARSE_CENSUSES}

# ---------------------------------------------------------- Area A - CENSUS

SLICE_DOCS = [
    "HUB_REGISTRY_2026-11-09.md",
    "HUB_BROWSE_2026-11-09.md",
    "HUB_CENSUS_2026-11-09.md",
    "HUB_SEARCH_2026-11-09.md",
    "HUB_CONTENT_SEARCH_2026-11-09.md",
    "HUB_UNIFIED_SEARCH_2026-11-09.md",
    "HUB_CONTENT_CENSUS_2026-11-09.md",
    "HUB_UNIFIED_SEARCH_CENSUS_2026-11-09.md",
    "HUB_DUPLICATE_CENSUS_2026-11-09.md",
    "HUB_CONTENT_SHAPE_CENSUS_2026-11-09.md",
    "HUB_SIZE_CENSUS_2026-11-09.md",
    "HUB_BREADTH_CENSUS_2026-11-09.md",
    "HUB_DISTINCT_CONTENT_CENSUS_2026-11-09.md",
    "HUB_SCHEMA_CENSUS_2026-11-09.md",
    "HUB_RECONCILIATION_2026-11-09.md",
]

TRUTH_MODULES = {
    "registry": ("register_entry", "entry_document", "list_document"),
    "browse": ("browse_document",),
    "census": ("census_document",),
    "search": ("search_document",),
    "content_search": ("content_search_document",),
    "unified_search": ("unified_search_document",),
    "content_census": ("content_census_document",),
    "unified_search_census": ("unified_search_census_document",),
    "duplicate_census": ("duplicate_census_document",),
    "content_shape_census": ("content_shape_census_document",),
    "size_census": ("size_census_document",),
    "breadth_census": ("breadth_census_document",),
    "distinct_census": ("distinct_census_document",),
    "schema_census": ("schema_census_document",),
}

SCHEMAS = [
    hub.ENTRY_SCHEMA, hub.LIST_SCHEMA,
    hub_browse.BROWSE_SCHEMA, hub_census.CENSUS_SCHEMA,
    hub_search.SEARCH_SCHEMA, hub_cs.CONTENT_SEARCH_SCHEMA,
    hub_unified.UNIFIED_SEARCH_SCHEMA, hub_cc.CONTENT_CENSUS_SCHEMA,
    hub_usc.UNIFIED_SEARCH_CENSUS_SCHEMA,
    hub_dup.DUPLICATE_CENSUS_SCHEMA,
    hub_shape.CONTENT_SHAPE_CENSUS_SCHEMA, hub_size.SIZE_CENSUS_SCHEMA,
    hub_breadth.BREADTH_CENSUS_SCHEMA,
    hub_distinct.DISTINCT_CENSUS_SCHEMA, hub_schema.SCHEMA_CENSUS_SCHEMA,
]

EXPECTED_ROADS = {
    ("POST", "/api/v1/hub/entries"),
    ("GET", "/api/v1/hub/census"),
    ("GET", "/api/v1/hub/content-census"),
    ("GET", "/api/v1/hub/duplicate-census"),
    ("GET", "/api/v1/hub/content-shape-census"),
    ("GET", "/api/v1/hub/size-census"),
    ("GET", "/api/v1/hub/breadth-census"),
    ("GET", "/api/v1/hub/distinct-census"),
    ("GET", "/api/v1/hub/schema-census"),
    ("GET", "/api/v1/hub/search"),
    ("GET", "/api/v1/hub/content-search"),
    ("GET", "/api/v1/hub/unified-search"),
    ("GET", "/api/v1/hub/unified-search-census"),
    ("GET", "/api/v1/hub/entries/{entry_id}"),
    ("GET", "/api/v1/hub/entries/{entry_id}/browse"),
    ("GET", "/api/v1/hub"),
    ("DELETE", "/api/v1/hub/entries/{entry_id}"),
}


def _openapi_hub_roads(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    roads = set()
    for path, ops in spec.json()["paths"].items():
        if path.startswith("/api/v1/hub"):
            for method in ops:
                roads.add((method.upper(), path))
    return roads


def test_a1_slice_docs_all_present():
    for name in SLICE_DOCS:
        assert (REPO / "docs" / name).is_file(), name
    assert len(SLICE_DOCS) == 15  # P-187..P-201, one doc each


def test_a2_truth_modules_and_router_functions_present():
    assert len(TRUTH_MODULES) == 14
    for mod_name, functions in TRUTH_MODULES.items():
        mod = importlib.import_module(f"runmal.hub.{mod_name}")
        for fn in functions:
            assert callable(getattr(mod, fn)), (mod_name, fn)
    router_mod = importlib.import_module("runmal.hub.router")
    assert router_mod.router is not None


def test_a3_schemas_unique_and_versioned():
    # P-187 entry + list, then one tag per slice
    # P-188..P-201: the enumerated truth is 15 tags
    # (the P-201 correction stands, never 16).
    assert len(SCHEMAS) == 15
    assert len(set(SCHEMAS)) == 15
    for schema in SCHEMAS:
        assert schema.startswith("runmal-p"), schema
        assert schema.endswith("-v1"), schema


def test_a4_openapi_names_exactly_the_hub_roads(tmp_path):
    roads = _openapi_hub_roads(tmp_path)
    assert ("GET", "/api/v1/hub/distinct-census") in roads
    assert ("GET", "/api/v1/hub/schema-census") in roads
    assert roads == EXPECTED_ROADS
    assert len(roads) == 17  # operations
    assert len({path for _m, path in roads}) == 16  # paths

def test_a5_router_declaration_order():
    source = (REPO / "src" / "runmal" / "hub" / "router.py").read_text()
    markers = [
        '@router.get("/hub/census")',
        '@router.get("/hub/content-census")',
        '@router.get("/hub/duplicate-census")',
        '@router.get("/hub/content-shape-census")',
        '@router.get("/hub/size-census")',
        '@router.get("/hub/breadth-census")',
        '@router.get("/hub/distinct-census")',
        '@router.get("/hub/schema-census")',
        '@router.get("/hub/search")',
        '@router.get("/hub/content-search")',
        '@router.get("/hub/unified-search")',
        '@router.get("/hub/unified-search-census")',
        '@router.get("/hub/entries/{entry_id}")',
        '@router.get("/hub/entries/{entry_id}/browse")',
        '@router.get("/hub")',
        '@router.delete("/hub/entries/{entry_id}")',
    ]
    positions = []
    for marker in markers:
        at = source.find(marker)
        assert at >= 0, marker
        positions.append(at)
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)
    # The POST register road is declared before the
    # census group (it opens the router's hub roads).
    assert source.find('@router.post("/hub/entries"') >= 0
    assert source.find('@router.post("/hub/entries"') < positions[0]


def test_a6_p201_itself_judged_present_exactly_once():
    path = REPO / "tests" / "test_p201_hub_reconciliation.py"
    assert path.is_file()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tests = [n.name for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name.startswith("test_")]
    assert len(tests) == 26  # sync + async both counted
    assert (REPO / "docs" / "HUB_RECONCILIATION_2026-11-09.md").is_file()
    log = (REPO / "docs" / "CLEAN_ROOM_LOG_2026-10-30.md").read_text(
        encoding="utf-8")
    assert log.count("- **P-201 (") == 1


def test_a7_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    migrations_dir = REPO / "src" / "runmal" / "db" / "migrations"
    assert not list(migrations_dir.glob("m0042*"))


def test_a8_one_law_objects_hold():
    for mod in (hub_shape, hub_size, hub_breadth,
                hub_distinct, hub_schema):
        assert mod.OUTCOMES is hub_cc.OUTCOMES, mod.__name__
    assert hub_cc.OUTCOMES == frozenset(
        {"parsed", "unavailable", "invalid"})
    assert hub_cs.OUTCOMES == frozenset(
        {"searched", "unavailable", "invalid"})
    assert hub_cs.OUTCOMES is not hub_cc.OUTCOMES
    assert hub_browse.MAX_BROWSE_BYTES == 16 * 1024 * 1024
    for mod in (hub_cs, hub_cc, hub_shape, hub_size,
                hub_breadth, hub_distinct, hub_schema):
        assert mod.MAX_BROWSE_BYTES is hub_browse.MAX_BROWSE_BYTES, \
            mod.__name__
    assert hub_search.MAX_MATCHES == 100
    assert hub_cs.MAX_MATCHES == 100
    assert hub_unified.MAX_MATCHES == 100


def test_a9_exact_package_census():
    hub_dir = REPO / "src" / "runmal" / "hub"
    names = {p.name for p in hub_dir.glob("*.py")}
    assert names == {
        "__init__.py", "registry.py", "browse.py", "census.py",
        "search.py", "content_search.py", "unified_search.py",
        "content_census.py", "unified_search_census.py",
        "duplicate_census.py", "content_shape_census.py",
        "size_census.py", "breadth_census.py",
        "distinct_census.py", "schema_census.py", "router.py"}
    assert len(names) == 16  # 15 modules + __init__
    for forbidden in ("history", "retention", "sign", "exchange",
                      "import", "update"):
        assert not any(forbidden in n for n in names), forbidden

# ---------------------------------------------------------- Area B - TOGETHER
# Re-measured on the fresh gate world (nonce query);
# P-201 measured the same arithmetic on its own world.


def test_b1_list_identity_across_surfaces(tmp_path):
    store = make_store(tmp_path)
    entries = _gate_estate(tmp_path, store)
    list_doc = hub.list_document(entries)
    assert list_doc["count"] == len(entries) == 9
    census = hub_census.census_document(entries)
    assert census["list"] == list_doc
    assert census["count"] == 9
    for key, doc in _parse_docs(entries).items():
        assert doc["list"] == list_doc, key
        assert doc["count"] == 9, key
    dup = hub_dup.duplicate_census_document(entries)
    assert dup["content_census"]["list"] == list_doc
    assert dup["count"] == 9
    by_kind = {}
    by_state = {}
    for entry in entries:
        by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1
        state = hub.locator_state(entry.locator)
        by_state[state] = by_state.get(state, 0) + 1
    for kind, count in by_kind.items():
        assert list_doc["by_kind"][kind] == count, kind
    assert sum(list_doc["by_kind"].values()) == 9
    for state, count in by_state.items():
        assert list_doc["by_locator_state"][state] == count, state
    assert sum(list_doc["by_locator_state"].values()) == 9


def test_b2_browse_tally_and_checksum_axes(tmp_path):
    store = make_store(tmp_path)
    entries = _gate_estate(tmp_path, store)
    census = hub_census.census_document(entries)
    tallies = {state: 0 for state in sorted(hub_browse.BROWSE_STATES)}
    checksum_keys = {"match": 0, "mismatch": 0, "undetermined": 0}
    inspected = set()
    rows_by_id = {row["id"]: row for row in census["entries"]}
    for entry in entries:
        doc = hub_browse.browse_document(entry)
        tallies[doc["browse_state"]] += 1
        key = ("match" if doc["checksum_match"] is True else
               "mismatch" if doc["checksum_match"] is False else
               "undetermined")
        checksum_keys[key] += 1
        row = rows_by_id[entry.id]
        assert row["browse_state"] == doc["browse_state"]
        assert row["locator_state"] == doc["locator_state"]
        assert row["verified_content_sha256"] == \
            doc["verified_content_sha256"]
        assert row["checksum_match"] == doc["checksum_match"]
        # L-9: the claim stays the claim, never upgraded.
        assert row["content_sha256"] == entry.content_sha256
        if doc["browse_state"] == hub_browse.BROWSE_INSPECTED:
            inspected.add(entry.id)
    assert census["by_browse_state"] == tallies
    assert census["by_checksum_match"] == checksum_keys
    cc = hub_cc.content_census_document(entries)
    parsed = {row["id"] for row in cc["entries"]
              if row["outcome"] == "parsed"}
    assert inspected == parsed
    # Both claim states are exercised on this estate.
    assert any(e.content_sha256 for e in entries)
    assert any(not e.content_sha256 for e in entries)
    assert checksum_keys["match"] >= 1


def test_b3_six_parse_censuses_agree(tmp_path):
    store = make_store(tmp_path)
    entries = _gate_estate(tmp_path, store)
    reference = None
    for mod, fn, states, _no_m, some_m, _all_m in PARSE_CENSUSES:
        doc = getattr(mod, fn)(entries)
        view = (doc["entries_considered"], doc["by_outcome"],
                doc["parsed_count"], doc["coverage_complete"])
        if reference is None:
            reference = view
        assert view == reference, mod.__name__
        assert doc["entries_considered"] == 9, mod.__name__
        assert doc["parsed_count"] == 6, mod.__name__
        assert doc["by_outcome"] == {
            "parsed": 6, "unavailable": 1, "invalid": 2}, mod.__name__
        assert doc["census_state"] == some_m, mod.__name__
        assert doc["census_state"] in states, mod.__name__
        assert doc["coverage_complete"] is False, mod.__name__
    # F-2 / L-5: P-189 and P-190 keep their own shapes.
    census189 = hub_census.census_document(entries)
    assert "entries_considered" not in census189
    assert "coverage_complete" not in census189
    search190 = hub_search.search_document(entries, "pack")
    assert "entries_considered" not in search190
    assert "coverage_complete" not in search190


def test_b4_string_volume_three_ways(tmp_path):
    store = make_store(tmp_path)
    entries = _gate_estate(tmp_path, store)
    cc = hub_cc.content_census_document(entries)
    shape = hub_shape.content_shape_census_document(entries)
    distinct = hub_distinct.distinct_census_document(entries)
    assert cc["total_string_values"] == shape["total_strings"]
    assert shape["total_strings"] == distinct["total_string_values"]
    cc_rows = {row["id"]: row["string_value_count"]
               for row in cc["entries"]}
    dc_rows = {row["id"]: row["string_value_count"]
               for row in distinct["entries"]}
    assert cc_rows == dc_rows


def test_b5_structure_agrees_across_censuses(tmp_path):
    store = make_store(tmp_path)
    entries = _gate_estate(tmp_path, store)
    shape = hub_shape.content_shape_census_document(entries)
    breadth = hub_breadth.breadth_census_document(entries)
    schema = hub_schema.schema_census_document(entries)
    assert breadth["total_containers"] == \
        shape["total_objects"] + shape["total_arrays"]
    assert schema["total_objects"] == shape["total_objects"]
    shape_rows = {row["id"]: row["object_count"]
                  for row in shape["entries"]}
    schema_rows = {row["id"]: row["object_count"]
                   for row in schema["entries"]}
    assert shape_rows == schema_rows


def test_b6_duplicate_partition_closes(tmp_path):
    store = make_store(tmp_path)
    entries = _gate_estate(tmp_path, store)
    dup = hub_dup.duplicate_census_document(entries)
    assert dup["content_census"] == hub_cc.content_census_document(entries)
    assert (dup["duplicate_entry_count"] + dup["unique_entry_count"]
            + dup["unidentified_entry_count"]) == dup["count"] == 9
    # The twice-registered lorebook pack: exactly one
    # group, of exactly those two entries.
    assert dup["duplicate_group_count"] == 1
    group = dup["duplicate_groups"][0]
    assert group["count"] == 2
    assert {m["id"] for m in group["entries"]} == \
        {entries[0].id, entries[4].id}
    assert dup["duplicate_entry_count"] == 2
    # L-6: the bare bundle is unidentified, never grouped.
    bare = next(e for e in entries if e.title == "Gate Bare Pack")
    grouped_ids = {m["id"] for g in dup["duplicate_groups"]
                   for m in g["entries"]}
    assert bare.id not in grouped_ids

def test_b7_size_rows_agree_with_files(tmp_path):
    store = make_store(tmp_path)
    entries = _gate_estate(tmp_path, store)
    size = hub_size.size_census_document(entries)
    rows = {row["id"]: row for row in size["entries"]}
    parsed_bytes = 0
    for entry in entries:
        row = rows[entry.id]
        if hub.locator_state(entry.locator) != "ready":
            assert row["file_bytes"] is None, entry.title
        else:
            assert row["file_bytes"] == os.path.getsize(entry.locator), \
                entry.title
        if row["outcome"] == "parsed":
            parsed_bytes += row["file_bytes"]
    assert size["total_verified_bytes"] == parsed_bytes


def test_b8_unified_is_union_and_census_reconciles(tmp_path):
    store = make_store(tmp_path)
    entries = _probe_estate(tmp_path, store)
    both, content_only, meta_only = entries
    meta = hub_search.search_document(entries, NONCE)
    content = hub_cs.content_search_document(entries, NONCE)
    unified = hub_unified.unified_search_document(entries, NONCE)
    assert unified["metadata_search"] == meta
    assert unified["content_search"] == content
    meta_ids = {row["id"] for row in meta["matches"]}
    content_ids = {row["id"] for row in content["matches"]}
    assert meta_ids == {both.id, meta_only.id}
    assert content_ids == {both.id, content_only.id}
    rows = {row["id"]: row for row in unified["matches"]}
    assert set(rows) == meta_ids | content_ids
    assert rows[both.id]["matched_by"] == "both"
    assert rows[content_only.id]["matched_by"] == "content"
    assert rows[meta_only.id]["matched_by"] == "metadata"
    assert unified["total_matches"] == len(meta_ids | content_ids)
    assert (unified["metadata_match_count"]
            + unified["content_match_count"]
            - unified["both_count"]) == unified["total_matches"]
    # P-194 reconciles with the P-192 document it
    # composes, on the gate estate (Zephyr query).
    gate_store = make_store(tmp_path / "second")
    gate_entries = _gate_estate(tmp_path / "second", gate_store)
    unified_g = hub_unified.unified_search_document(gate_entries, "Zephyr")
    census = hub_usc.unified_search_census_document(gate_entries, "Zephyr")
    assert hub_usc.build_unified_search_census(unified_g) == census
    assert census["unified_search"] == unified_g
    assert census["entries_considered"] == unified_g["entries_considered"]
    assert census["coverage_complete"] == unified_g["coverage_complete"]
    assert census["coverage_complete"] is False
    by_skip = {outcome: 0 for outcome in hub_usc.SKIP_OUTCOMES}
    for row in unified_g["skipped_entries"]:
        by_skip[row["outcome"]] += 1
    assert census["by_skip_outcome"] == by_skip
    assert by_skip == {"unavailable": 1, "invalid": 2}
    assert hub_usc.SKIP_OUTCOMES == ("unavailable", "invalid")
    assert "searched" not in hub_usc.SKIP_OUTCOMES


def test_b9_search_refusals_agree(tmp_path):
    store = make_store(tmp_path)
    entries = _gate_estate(tmp_path, store)
    for bad_query in ("", "   "):
        with pytest.raises(hub_search.HubSearchError):
            hub_search.search_document(entries, bad_query)
        with pytest.raises(hub_cs.HubContentSearchError):
            hub_cs.content_search_document(entries, bad_query)
        with pytest.raises(hub_unified.HubUnifiedSearchError):
            hub_unified.unified_search_document(entries, bad_query)
        with pytest.raises(hub_unified.HubUnifiedSearchError):
            hub_usc.unified_search_census_document(entries, bad_query)
    for fn, err in (
            (hub_search.search_document, hub_search.HubSearchError),
            (hub_cs.content_search_document, hub_cs.HubContentSearchError),
            (hub_unified.unified_search_document,
             hub_unified.HubUnifiedSearchError),
            (hub_usc.unified_search_census_document,
             hub_unified.HubUnifiedSearchError)):
        with pytest.raises(err):
            fn(entries, "Zephyr", kind="bogus_kind")
    _factory, client = _client(tmp_path)
    for road in ("/hub/search", "/hub/content-search",
                 "/hub/unified-search", "/hub/unified-search-census"):
        assert client.get("/api/v1" + road).status_code == 422, road
        refused = client.get("/api/v1" + road,
                             params={"q": "Zephyr", "kind": "bogus_kind"})
        assert refused.status_code == 422, road
    assert client.get("/api/v1/hub",
                      params={"kind": "bogus_kind"}).status_code == 422


def test_b10_kind_narrowing_agrees(tmp_path):
    store = make_store(tmp_path)
    entries = _gate_estate(tmp_path, store)
    meta_all = hub_search.search_document(entries, "pack")
    assert meta_all["total_matches"] == 9
    lore_ids = {e.id for e in entries if e.kind == "lorebook_pack"}
    assert len(lore_ids) == 3  # original, copy, wrong-kind
    meta_one = hub_search.search_document(
        entries, "pack", kind="lorebook_pack")
    assert {row["id"] for row in meta_one["matches"]} == lore_ids
    content_one = hub_cs.content_search_document(
        entries, "Zephyr", kind="lorebook_pack")
    assert content_one["entries_considered"] == 3
    assert {row["id"] for row in content_one["matches"]} == \
        {entries[0].id, entries[4].id}
    unified_one = hub_unified.unified_search_document(
        entries, "Zephyr", kind="lorebook_pack")
    assert unified_one["entries_considered"] == 3
    assert {row["id"] for row in unified_one["matches"]} == \
        {entries[0].id, entries[4].id}
    with pytest.raises(TypeError):
        hub_cc.content_census_document(entries, kind="lorebook_pack")
    with pytest.raises(TypeError):
        hub_census.census_document(entries, kind="lorebook_pack")
    assert hub_cc.content_census_document(entries)["count"] == 9


def test_b11_truncation_agrees_at_the_cap(tmp_path):
    store = make_store(tmp_path)
    entries = _truncation_estate(tmp_path, store)
    meta = hub_search.search_document(entries, "match pack")
    assert meta["total_matches"] == hub_search.MAX_MATCHES + 1
    assert meta["match_count"] == hub_search.MAX_MATCHES
    assert meta["truncated"] is True
    assert meta["search_state"] == "matches_truncated"
    content = hub_cs.content_search_document(entries, "match pack")
    assert content["entries_searched"] == 0
    assert len(content["skipped_entries"]) == hub_search.MAX_MATCHES + 1
    assert all(row["outcome"] == "unavailable"
               for row in content["skipped_entries"])
    unified = hub_unified.unified_search_document(entries, "match pack")
    assert unified["metadata_total_matches"] == hub_search.MAX_MATCHES + 1
    assert unified["match_count"] == hub_search.MAX_MATCHES
    assert unified["truncated"] is True
    assert unified["coverage_complete"] is False
    census = hub_usc.unified_search_census_document(entries, "match pack")
    assert census["truncated"] is True
    assert census["coverage_complete"] is False
    assert census["match_count"] == hub_search.MAX_MATCHES
    assert census["metadata_total_matches"] == hub_search.MAX_MATCHES + 1


def test_b12_register_law_and_exact_removal(tmp_path):
    store = make_store(tmp_path)
    entries = _gate_estate(tmp_path, store)
    before = len(store.list_for_owner("u1"))
    assert before == 9
    bad_calls = [
        dict(kind="lorebook_pack", title="", locator="/x.json"),
        dict(kind="lorebook_pack", title="T", locator=""),
        dict(kind="bogus_kind", title="T", locator="/x.json"),
        dict(kind="lorebook_pack", title="T", locator="/x.json",
             content_sha256="not-hex"),
        dict(kind=entries[0].kind, title="Dup", locator=entries[0].locator),
    ]
    for kwargs in bad_calls:
        with pytest.raises(hub.HubError):
            hub.register_entry(store, owner_id="u1", **kwargs)
    assert len(store.list_for_owner("u1")) == before
    # A miss removes nothing and writes nothing.
    hub_bytes = (tmp_path / "data" / "hub.json").read_bytes()
    assert store.remove_entry("no-such-id") is None
    assert (tmp_path / "data" / "hub.json").read_bytes() == hub_bytes
    # Exact removal: gone from list, census and searches.
    victim = entries[1]
    removed = store.remove_entry(victim.id)
    assert removed is not None and removed.id == victim.id
    remaining = store.list_for_owner("u1")
    assert len(remaining) == before - 1
    assert hub.list_document(remaining)["count"] == before - 1
    assert hub_census.census_document(remaining)["count"] == before - 1
    assert hub_search.search_document(
        remaining, "Gate Prompt Pack")["total_matches"] == 0
    assert store.get_entry(victim.id) is None

# ---------------------------------------------------------- Area C - CUSTODY


def _all_unit_documents(entries):
    docs = [hub.list_document(entries), hub_census.census_document(entries),
            hub_search.search_document(entries, "Zephyr"),
            hub_search.search_document(entries, "pack"),
            hub_cs.content_search_document(entries, "Zephyr"),
            hub_unified.unified_search_document(entries, "Zephyr"),
            hub_usc.unified_search_census_document(entries, "Zephyr")]
    docs += [doc for doc in _parse_docs(entries).values()]
    docs.append(hub_dup.duplicate_census_document(entries))
    for entry in entries:
        docs.append(hub.entry_document(entry))
        docs.append(hub_browse.browse_document(entry))
    return docs


def test_c1_every_hub_read_is_a_pure_read(tmp_path):
    store = make_store(tmp_path)
    entries = _gate_estate(tmp_path, store)
    hub_bytes = (tmp_path / "data" / "hub.json").read_bytes()
    pack_bytes = {}
    for entry in entries:
        if os.path.isfile(entry.locator):
            pack_bytes[entry.locator] = open(entry.locator, "rb").read()
    first = _all_unit_documents(entries)
    second = _all_unit_documents(entries)
    assert first == second
    assert (tmp_path / "data" / "hub.json").read_bytes() == hub_bytes
    for locator, raw in pack_bytes.items():
        assert open(locator, "rb").read() == raw
    # Over HTTP: every GET road leaves the same bytes.
    _factory, client = _client(tmp_path)
    base = tmp_path / "c1-http"
    base.mkdir(parents=True, exist_ok=True)
    locator, pack = _lorebook_file(base, "http-pack.json")
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Http Pack",
        "locator": locator,
        "content_sha256": pack["manifest"]["content_sha256"]})
    assert created.status_code == 201, created.text
    entry_id = created.json()["entry"]["id"]
    hub_bytes = (tmp_path / "data" / "hub.json").read_bytes()
    pack_raw = open(locator, "rb").read()
    get_roads = [
        "/hub", "/hub/census", "/hub/content-census",
        "/hub/duplicate-census", "/hub/content-shape-census",
        "/hub/size-census", "/hub/breadth-census",
        "/hub/distinct-census", "/hub/schema-census",
        f"/hub/entries/{entry_id}", f"/hub/entries/{entry_id}/browse",
    ]
    for road in get_roads:
        got = client.get("/api/v1" + road)
        assert got.status_code == 200, (road, got.text)
    for road in ("/hub/search", "/hub/content-search",
                 "/hub/unified-search", "/hub/unified-search-census"):
        got = client.get("/api/v1" + road, params={"q": "Zephyr"})
        assert got.status_code == 200, (road, got.text)
    assert (tmp_path / "data" / "hub.json").read_bytes() == hub_bytes
    assert open(locator, "rb").read() == pack_raw


PAYLOAD_STRINGS = (
    "The Zephyr Quill writes storms.",
    "Zephyr prompt text for the hall.",
    "The Zephyr ferry has just left.",
    "Zephyr bundle text for the hall.",
)
PAYLOAD_KEYS = ("selective_logic", "inclusion_group", "sticky_prompts")


def test_c2_no_census_retains_content(tmp_path):
    store = make_store(tmp_path)
    entries = _gate_estate(tmp_path, store)
    census_docs = [
        hub_census.census_document(entries),
        hub_cc.content_census_document(entries),
        hub_dup.duplicate_census_document(entries),
        hub_shape.content_shape_census_document(entries),
        hub_size.size_census_document(entries),
        hub_breadth.breadth_census_document(entries),
        hub_distinct.distinct_census_document(entries),
        hub_schema.schema_census_document(entries),
    ]
    usc = hub_usc.unified_search_census_document(entries, "Zephyr")
    census_docs.append(
        {k: v for k, v in usc.items() if k != "unified_search"})
    digests = {hashlib.sha256(text.encode()).hexdigest()
               for text in PAYLOAD_STRINGS}
    for doc in census_docs:
        blob = json.dumps(doc)
        for text in PAYLOAD_STRINGS:
            assert text not in blob, doc["schema"]
        for key in PAYLOAD_KEYS:
            assert key not in blob, (doc["schema"], key)
        for digest in digests:
            assert digest not in blob, doc["schema"]
        assert '"excerpt":' not in blob, doc["schema"]
    meta_blob = json.dumps(hub_search.search_document(entries, "Zephyr"))
    assert '"excerpt":' not in meta_blob
    content = hub_cs.content_search_document(entries, "Zephyr")
    assert content["matches"]
    assert all("excerpt" in row for row in content["matches"])


def test_c3_owner_scoping_on_every_surface(tmp_path):
    store = make_store(tmp_path)
    base_a = tmp_path / "c3-a"
    base_a.mkdir(parents=True, exist_ok=True)
    base_b = tmp_path / "c3-b"
    base_b.mkdir(parents=True, exist_ok=True)
    loc_a, pack_a = _lorebook_file(base_a, "a.json")
    loc_b, pack_b = _lorebook_file(base_b, "b.json")
    mine1 = _register(store, "lorebook_pack", "Mine Lore", loc_a,
                      pack_a["manifest"]["content_sha256"], owner="u1")
    theirs1 = _register(store, "lorebook_pack", "Theirs Lore", loc_b,
                        pack_b["manifest"]["content_sha256"], owner="u2")
    loc_a2, _pp = _prompt_file(base_a)
    mine2 = _register(store, "prompt_pack", "Mine Prompt", loc_a2,
                      owner="u1")
    loc_b2, _sp = _scenario_file(base_b)
    theirs2 = _register(store, "scenario_pack", "Theirs Scenario", loc_b2,
                        owner="u2")
    foreign_ids = {theirs1.id, theirs2.id}
    estate = store.list_for_owner("u1")
    assert {e.id for e in estate} == {mine1.id, mine2.id}
    for doc in _all_unit_documents(estate):
        blob = json.dumps(doc)
        for fid in foreign_ids:
            assert fid not in blob, doc.get("schema")
    assert hub_search.search_document(estate, "Theirs")["total_matches"] == 0
    assert hub_unified.unified_search_document(
        estate, "Theirs")["total_matches"] == 0
    _factory, client = _client(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Http Mine",
        "locator": loc_a,
        "content_sha256": pack_a["manifest"]["content_sha256"]})
    assert created.status_code == 201, created.text
    http_mine = created.json()["entry"]["id"]
    foreign = _register(store, "lorebook_pack", "Http Theirs", loc_b,
                        pack_b["manifest"]["content_sha256"],
                        owner="foreign-owner")
    listing = client.get("/api/v1/hub")
    assert listing.status_code == 200
    assert {row["id"] for row in listing.json()["entries"]} == {http_mine}
    assert client.get("/api/v1/hub/census").json()["count"] == 1
    assert client.get(
        f"/api/v1/hub/entries/{foreign.id}").status_code == 404
    assert client.get(
        f"/api/v1/hub/entries/{foreign.id}/browse").status_code == 404
    assert client.delete(
        f"/api/v1/hub/entries/{foreign.id}").status_code == 404
    assert store.get_entry(foreign.id) is not None
    bare = TestClient(create_app(_factory))
    get_roads = [
        "/hub", "/hub/census", "/hub/content-census",
        "/hub/duplicate-census", "/hub/content-shape-census",
        "/hub/size-census", "/hub/breadth-census",
        "/hub/distinct-census", "/hub/schema-census",
        f"/hub/entries/{http_mine}", f"/hub/entries/{http_mine}/browse",
    ]
    for road in get_roads:
        assert bare.get("/api/v1" + road).status_code == 401, road
    for road in ("/hub/search", "/hub/content-search",
                 "/hub/unified-search", "/hub/unified-search-census"):
        got = bare.get("/api/v1" + road, params={"q": "Zephyr"})
        assert got.status_code == 401, road

def test_c4_mutating_roads_are_exactly_the_banked_writes(tmp_path):
    roads = _openapi_hub_roads(tmp_path)
    mutating = {(method, path) for method, path in roads
                if method != "GET"}
    assert mutating == {
        ("POST", "/api/v1/hub/entries"),
        ("DELETE", "/api/v1/hub/entries/{entry_id}"),
    }
    for method, path in roads:
        if "census" in path or "search" in path:
            assert method == "GET", (method, path)
    # Data-only: no hub road names an import, fetch,
    # execute, install or sync operation.
    for _method, path in roads:
        for word in ("import", "fetch", "execute", "install", "sync"):
            assert word not in path, (word, path)


def test_c5_http_session_walks_all_17_operations(tmp_path):
    _factory, client = _client(tmp_path)
    base = tmp_path / "c5"
    base.mkdir(parents=True, exist_ok=True)
    made = []
    for kind, maker in (
            ("lorebook_pack", _lorebook_file),
            ("prompt_pack", _prompt_file),
            ("scenario_pack", _scenario_file),
            ("preset_bundle", _bundle_file)):
        locator, pack = maker(base)
        sha = pack["manifest"]["content_sha256"] \
            if "manifest" in pack else ""
        made.append((kind, locator, sha))
    ids = []
    owner_id = None
    for kind, locator, sha in made:
        created = client.post("/api/v1/hub/entries", json={
            "kind": kind, "title": "A pack", "locator": locator,
            "content_sha256": sha})
        assert created.status_code == 201, created.text
        ids.append(created.json()["entry"]["id"])
        owner_id = created.json()["entry"]["owner_id"]
    estate = make_store(tmp_path).list_for_owner(owner_id)
    assert [e.id for e in estate] == ids
    checks = [
        ("/hub", None, hub.list_document(estate)),
        ("/hub/census", None, hub_census.census_document(estate)),
        ("/hub/content-census", None,
         hub_cc.content_census_document(estate)),
        ("/hub/duplicate-census", None,
         hub_dup.duplicate_census_document(estate)),
        ("/hub/content-shape-census", None,
         hub_shape.content_shape_census_document(estate)),
        ("/hub/size-census", None, hub_size.size_census_document(estate)),
        ("/hub/breadth-census", None,
         hub_breadth.breadth_census_document(estate)),
        ("/hub/distinct-census", None,
         hub_distinct.distinct_census_document(estate)),
        ("/hub/schema-census", None,
         hub_schema.schema_census_document(estate)),
        ("/hub/search", {"q": "pack"},
         hub_search.search_document(estate, "pack")),
        ("/hub/content-search", {"q": "Zephyr"},
         hub_cs.content_search_document(estate, "Zephyr")),
        ("/hub/unified-search", {"q": "Zephyr"},
         hub_unified.unified_search_document(estate, "Zephyr")),
        ("/hub/unified-search-census", {"q": "Zephyr"},
         hub_usc.unified_search_census_document(estate, "Zephyr")),
        (f"/hub/entries/{ids[0]}", None, hub.entry_document(estate[0])),
        (f"/hub/entries/{ids[0]}/browse", None,
         hub_browse.browse_document(estate[0])),
    ]
    assert len(checks) == 15  # + POST above + DELETE below = 17 ops
    for road, params, want in checks:
        got = client.get("/api/v1" + road, params=params)
        assert got.status_code == 200, (road, got.text)
        assert got.json() == want, road
    deleted = client.delete(f"/api/v1/hub/entries/{ids[3]}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": ids[3]}
    assert client.get(f"/api/v1/hub/entries/{ids[3]}").status_code == 404
    assert client.get("/api/v1/hub").json()["count"] == 3

# ---------------------------------------------------------- Area D - ACCOUNTING


def test_d1_ka_no_entry_update_road(tmp_path):
    roads = _openapi_hub_roads(tmp_path)
    for _method, path in roads:
        assert "update" not in path, path
    assert not any(method in ("PUT", "PATCH") for method, _p in roads)
    store_verbs = [n for n in dir(hub.HubStore) if not n.startswith("_")]
    assert not any("update" in n.lower() for n in store_verbs)
    # Remove-then-register IS the title-change path.
    store = make_store(tmp_path)
    base = tmp_path / "d1"
    base.mkdir(parents=True, exist_ok=True)
    locator, pack = _lorebook_file(base, "d1.json")
    entry = _register(store, "lorebook_pack", "Old Title", locator,
                      pack["manifest"]["content_sha256"])
    with pytest.raises(hub.HubError):
        _register(store, "lorebook_pack", "New Title", locator)
    assert store.remove_entry(entry.id) is not None
    changed = _register(store, "lorebook_pack", "New Title", locator)
    assert changed.title == "New Title"
    assert changed.id != entry.id


def test_d2_kb_no_retention_or_bulk_clear(tmp_path):
    roads = _openapi_hub_roads(tmp_path)
    for _method, path in roads:
        for word in ("retention", "bulk", "clear"):
            assert word not in path, (word, path)
    hub_dir = REPO / "src" / "runmal" / "hub"
    for path in hub_dir.glob("*.py"):
        for word in ("retention", "bulk", "clear"):
            assert word not in path.name, (word, path.name)
    store_verbs = [n for n in dir(hub.HubStore) if not n.startswith("_")]
    assert "remove_entry" in store_verbs
    assert not any("clear" in n.lower() for n in store_verbs)
    assert not any("retention" in n.lower() or "bulk" in n.lower()
                   for n in store_verbs)


def test_d3_kc_no_search_history_anywhere(tmp_path):
    roads = _openapi_hub_roads(tmp_path)
    for _method, path in roads:
        assert "history" not in path, path
    hub_dir = REPO / "src" / "runmal" / "hub"
    assert not any("history" in p.name for p in hub_dir.glob("*.py"))
    store = make_store(tmp_path)
    entries = _gate_estate(tmp_path, store)
    docs = _all_unit_documents(entries)
    for doc in docs:
        if isinstance(doc, dict):
            assert "history" not in doc, doc.get("schema")


def test_d4_kd_ke_declined_not_shipped(tmp_path):
    roads = _openapi_hub_roads(tmp_path)
    for _method, path in roads:
        for word in ("sign", "attest", "exchange", "fetch", "sync", "peer"):
            assert word not in path, (word, path)
    hub_dir = REPO / "src" / "runmal" / "hub"
    for path in hub_dir.glob("*.py"):
        for word in ("sign", "attest", "exchange"):
            assert word not in path.name, (word, path.name)
    # A WRONG claim stays a claim: browse reports the
    # verified checksum beside it, match False, and the
    # stored claim is never upgraded (K-D's positive pin).
    store = make_store(tmp_path)
    base = tmp_path / "d4"
    base.mkdir(parents=True, exist_ok=True)
    locator, pack = _lorebook_file(base, "d4.json")
    verified = pack["manifest"]["content_sha256"]
    wrong_claim = "0" * 64 if verified != "0" * 64 else "1" * 64
    entry = _register(store, "lorebook_pack", "Claimed", locator,
                      wrong_claim)
    doc = hub_browse.browse_document(entry)
    assert doc["browse_state"] == "inspected"
    assert doc["verified_content_sha256"] == verified
    assert doc["checksum_match"] is False
    assert hub.entry_document(entry)["entry"]["content_sha256"] == \
        wrong_claim


def test_d5_kf_kg_kh_no_import_lifecycle_or_central_surface(tmp_path):
    roads = _openapi_hub_roads(tmp_path)
    for _method, path in roads:
        for word in ("import", "install", "catalog", "profile",
                     "creator", "central"):
            assert word not in path, (word, path)
    # Lifecycle depth is exactly register + remove at
    # the store: the banked verb set, nothing more.
    store_verbs = {n for n in dir(hub.HubStore) if not n.startswith("_")}
    assert store_verbs == {
        "add_entry", "get_entry", "find_entry",
        "list_for_owner", "remove_entry"}
    hub_dir = REPO / "src" / "runmal" / "hub"
    for path in hub_dir.glob("*.py"):
        for word in ("import", "catalog", "profile", "creator"):
            assert word not in path.name, (word, path.name)


def test_d6_limitations_at_full_strength(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    base = tmp_path / "d6"
    base.mkdir(parents=True, exist_ok=True)
    locator, _pack = _lorebook_file(base, "d6.json")
    entry = _register(store, "lorebook_pack", "Gate Big Pack", locator)
    entries = store.list_for_owner("u1")
    # L-2 (tree truth): oversize is INVALID, never
    # partially read - on browse and on every parse
    # census under the shrunk bound (the banked
    # P-188 / P-193 verdict, not "unavailable").
    monkeypatch.setattr(hub_browse, "MAX_BROWSE_BYTES", 8)
    browse_doc = hub_browse.browse_document(entry)
    assert browse_doc["browse_state"] == "invalid"
    assert browse_doc["error"] == "pack file too large to browse"
    for mod, fn, *_rest in PARSE_CENSUSES:
        monkeypatch.setattr(mod, "MAX_BROWSE_BYTES", 8)
        doc = getattr(mod, fn)(entries)
        row = doc["entries"][0]
        assert row["outcome"] == "invalid", mod.__name__
        assert "too large" in row["error"], mod.__name__
    monkeypatch.setattr(hub_cs, "MAX_BROWSE_BYTES", 8)
    searched = hub_cs.content_search_document(entries, "Zephyr")
    assert searched["skipped_entries"][0]["outcome"] == "invalid"
    # Restore the true bound before the literal legs
    # (monkeypatch undoes the rest at test end).
    monkeypatch.setattr(hub_cs, "MAX_BROWSE_BYTES", 16 * 1024 * 1024)
    # L-4: literal only - a regex-shaped query matches
    # literally or not at all; casefold literal does hit.
    gate_store = make_store(tmp_path / "lit")
    gate_entries = _gate_estate(tmp_path / "lit", gate_store)
    regex_shaped = hub_search.search_document(gate_entries, "Gate.*Pack")
    assert regex_shaped["total_matches"] == 0
    content_regex = hub_cs.content_search_document(
        gate_entries, "Zephyr.*Quill")
    assert content_regex["total_matches"] == 0
    lowered = hub_search.search_document(gate_entries, "gate lore pack")
    assert lowered["total_matches"] == 1
    # L-7: a value under a content_sha256 key is never
    # walked, by any content surface's own walk.
    payload = {
        "content_sha256": {"deep": NONCE + "Hidden"},
        "nested": {"content_sha256": NONCE + "Hidden", "keep": "yes"},
        "items": ["visible"],
    }
    for mod in (hub_cc, hub_cs, hub_distinct):
        walked = list(mod._string_values(payload))
        assert "visible" in walked, mod.__name__
        assert "yes" in walked, mod.__name__
        assert not any(NONCE in value for value in walked), mod.__name__

# ---------------------------------------------------------- Hygiene


def test_h_migration_head_and_gate_scope():
    assert MIGRATIONS[-1][0] == "0041"
    assert hub_browse.MAX_BROWSE_BYTES == 16 * 1024 * 1024


def test_h_gate_world_marker_lives_only_in_gate_files():
    hits = []
    for path in (REPO / "src").rglob("*.py"):
        if "ZqxGate202" in path.read_text(encoding="utf-8", errors="ignore"):
            hits.append(str(path))
    assert hits == []
