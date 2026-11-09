"""P-201 - Hub reconciliation battery (Part XII, DERIVED).

The pre-gate reconciliation of P-187..P-200 as ONE
system, modelled on the P-185 workspace battery. This
battery builds NO new behaviour: no new src module, no
new road, no migration (head stays 0041). It judges the
banked hub estate end to end through its own public
contracts, from measured evidence only, ahead of the
P-202 gate:

- Section A (presence / shape, static): the 14 slice
docs, the 15 hub modules (14 truth + router), the 15
schema tags pairwise distinct and versioned, OpenAPI
naming exactly the 17 hub operations on 16 paths (the
F-1 union pin: the distinct-census AND schema-census
roads both present), the router declaration order, the
migration head, and the one-law objects (P-193's
OUTCOMES imported is-identically by every later parse
census, P-188's 16 MiB bound, MAX_MATCHES 100 in all
three searches; P-189 / P-190 predate the coverage
document shape and are mapped by their own shapes -
the F-2 asymmetry, pinned, never fixed).
- Section B (cross-surface agreement, live estates):
one registry list agreed everywhere, the browse axis
reconciled with the census, all six parse censuses
agreeing on outcomes, string volume three ways,
structure across censuses, the duplicate partition,
size / breadth rows against the files themselves, the
unified search as the exact union, its census as an
exact recomputation, and the refusal / kind-narrowing
/ truncation agreements.
- Section C (fences): every hub read a pure read, no
census or search retaining content (excerpts only
inside P-191 / P-192 match rows), owner scoping on
every surface, the mutating roads exactly the banked
writes, and all 17 HTTP operations answering together
with the unit documents dict-equal.
- Section D (carried items / gate readiness): the
three carried items pinned absent by measurement, and
the no-orphan closure in both directions (every truth
module reachable from its banked road, every road's
handler calling a banked truth module).

Estates: EMPTY, FULL (four kinds, verified), MIXED
(full + bare bundle + missing + invalid + wrong-kind),
FOREIGN (a second owner interleaved) and TRUNCATION
(101 metadata entries, one search past MAX_MATCHES).
Expected numbers are computed from the fixture estates
themselves or read from the files, never copied from a
sibling document's output - the sibling documents are
the things being reconciled. Clean-room: fixtures
fresh-authored in the P-199 / P-200 pattern; no
SillyTavern or Voxta source inspected. No network.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
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
from runmal.hub import distinct_census as hub_distinct
from runmal.hub import duplicate_census as hub_dup
from runmal.hub import registry as hub
from runmal.hub import schema_census as hub_schema
from runmal.hub import search as hub_search
from runmal.hub import size_census as hub_size
from runmal.hub import content_shape_census as hub_shape
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
# The P-199 / P-200 fixture pattern, built fresh here:
# four pack builders, one per hub kind.


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
    record = store.create("owner-p201", body, now=STAMP)
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


# ------------------------------------------------------------ the estates


def _full_estate(tmp_path, store, sub="full", owner="u1"):
    """Four kinds, every one verified: parsed 4 of 4."""
    base = tmp_path / sub
    base.mkdir(parents=True, exist_ok=True)
    entries = []
    for kind, maker in (
            ("lorebook_pack", _lorebook_file),
            ("prompt_pack", _prompt_file),
            ("scenario_pack", _scenario_file),
            ("preset_bundle", _bundle_file)):
        locator, pack = maker(base)
        sha = pack["manifest"]["content_sha256"] \
            if "manifest" in pack else ""
        entries.append(_register(store, kind, "A pack", locator, sha,
                                 owner=owner))
    return entries


def _mixed_estate(tmp_path, store, owner="u1"):
    """FULL + bare bundle + missing + broken + wrong-kind:
    8 entries, parsed 5, unavailable 1, invalid 2."""
    entries = _full_estate(tmp_path, store, "mixed-full", owner=owner)
    bare_dir = tmp_path / "mixed-bare"
    bare_dir.mkdir(parents=True, exist_ok=True)
    locator, _bundle = _bundle_file(bare_dir, bare=True)
    entries.append(_register(store, "preset_bundle", "Bare Bundle",
                             locator, owner=owner))
    entries.append(_register(
        store, "prompt_pack", "Ghost",
        str(tmp_path / "mixed-ghost.json"), owner=owner))
    bad = tmp_path / "mixed-broken.json"
    bad.write_bytes(b"{not a pack")
    entries.append(_register(store, "scenario_pack", "Broken",
                             str(bad), owner=owner))
    wrong_dir = tmp_path / "mixed-wrong"
    wrong_dir.mkdir(parents=True, exist_ok=True)
    locator, _pack = _prompt_file(wrong_dir)
    entries.append(_register(store, "lorebook_pack", "Wrong Kind",
                             locator, owner=owner))
    return entries


def _truncation_estate(tmp_path, store, owner="u1"):
    """101 metadata entries whose locators name no file:
    one metadata search runs past MAX_MATCHES (the
    design's metadata-side truncation estate)."""
    entries = []
    for i in range(hub_search.MAX_MATCHES + 1):
        entries.append(_register(
            store, "lorebook_pack", f"Match Pack {i}",
            f"/packs/m{i}.json", owner=owner))
    return entries


PARSE_CENSUSES = [
    # (module, document function, states, no-member,
    #  some-member, all-member) - each census judged under
    # its OWN closed law (the scout's section 1 table).
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


# ---------------------------------------------------------- Section A

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


def test_a_slice_docs_all_present():
    for name in SLICE_DOCS:
        assert (REPO / "docs" / name).is_file(), name
    assert len(SLICE_DOCS) == 14  # P-187..P-200, one doc each


def test_a_truth_modules_present():
    assert len(TRUTH_MODULES) == 14
    for mod_name, functions in TRUTH_MODULES.items():
        mod = importlib.import_module(f"runmal.hub.{mod_name}")
        for fn in functions:
            assert callable(getattr(mod, fn)), (mod_name, fn)
    router_mod = importlib.import_module("runmal.hub.router")
    assert router_mod.router is not None
    # 14 truth modules + the router = the whole hub package
    # surface beside __init__.
    names = {p.stem for p in (REPO / "src" / "runmal" / "hub").glob("*.py")}
    assert names == set(TRUTH_MODULES) | {"router", "__init__"}


def test_a_schemas_unique_and_versioned():
    # P-187 entry + list, then one tag per slice P-188..P-200:
    # the enumerated truth is 15 tags (the scout's count).
    assert len(SCHEMAS) == 15
    assert len(set(SCHEMAS)) == 15
    for schema in SCHEMAS:
        assert schema.startswith("runmal-p"), schema
        assert schema.endswith("-v1"), schema


def test_a_openapi_names_exactly_the_hub_roads(tmp_path):
    roads = _openapi_hub_roads(tmp_path)
    # The F-1 union pin: BOTH the distinct-census road
    # (P-199) and the schema-census road (P-200) present,
    # and no other hub road exists.
    assert ("GET", "/api/v1/hub/distinct-census") in roads
    assert ("GET", "/api/v1/hub/schema-census") in roads
    assert roads == EXPECTED_ROADS
    assert len(roads) == 17  # operations
    assert len({path for _method, path in roads}) == 16  # paths


def test_a_router_declaration_order():
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
    # Estate censuses in slice order (breadth -> distinct
    # -> schema, the F-1 merged order), searches after,
    # per-entry reads after those, list then delete last.
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)


def test_a_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
    migrations_dir = REPO / "src" / "runmal" / "db" / "migrations"
    assert [p.name for p in migrations_dir.glob("m0042*")] == ["m0042_message_reasoning.py"]  # P-205 banking heal


def test_a_one_law_objects():
    # One OUTCOMES object: every parse census after P-193
    # imports P-193's own frozenset, is-identically.
    for mod in (hub_shape, hub_size, hub_breadth,
                hub_distinct, hub_schema):
        assert mod.OUTCOMES is hub_cc.OUTCOMES, mod.__name__
    assert hub_cc.OUTCOMES == frozenset(
        {"parsed", "unavailable", "invalid"})
    # F-2's sibling asymmetry, pinned not fixed: P-191's
    # own outcomes law is a DIFFERENT object with the
    # searched outcome (searched, not parsed).
    assert hub_cs.OUTCOMES == frozenset(
        {"searched", "unavailable", "invalid"})
    assert hub_cs.OUTCOMES is not hub_cc.OUTCOMES
    # One bound: P-188's 16 MiB int, carried by assignment.
    assert hub_browse.MAX_BROWSE_BYTES == 16 * 1024 * 1024
    for mod in (hub_cs, hub_cc, hub_shape, hub_size,
                hub_breadth, hub_distinct, hub_schema):
        assert mod.MAX_BROWSE_BYTES is hub_browse.MAX_BROWSE_BYTES, \
            mod.__name__
    # One cap: MAX_MATCHES 100 in all three searches.
    assert hub_search.MAX_MATCHES == 100
    assert hub_cs.MAX_MATCHES == 100
    assert hub_unified.MAX_MATCHES == 100


# ---------------------------------------------------------- Section B


def _three_estates(tmp_path, store):
    return [
        ("EMPTY", [], 0),
        ("FULL", _full_estate(tmp_path, store, "b-full"), 4),
        ("MIXED", _mixed_estate(tmp_path, store), 5),
    ]


def test_b_registry_list_agrees_everywhere(tmp_path):
    store = make_store(tmp_path)
    for name, entries, _parsed in _three_estates(tmp_path, store):
        list_doc = hub.list_document(entries)
        assert list_doc["count"] == len(entries), name
        # P-189 embeds the list under its OWN older shape
        # (F-2): count + embedded list, mapped as-is.
        census = hub_census.census_document(entries)
        assert census["list"] == list_doc, name
        assert census["count"] == len(entries), name
        for key, doc in _parse_docs(entries).items():
            assert doc["list"] == list_doc, (name, key)
            assert doc["count"] == len(entries), (name, key)
        dup = hub_dup.duplicate_census_document(entries)
        assert dup["content_census"]["list"] == list_doc, name
        assert dup["count"] == len(entries), name


def test_b_browse_axis_reconciles_with_census(tmp_path):
    store = make_store(tmp_path)
    for sub, builder in (("b2-full", _full_estate),
                         ("b2-mixed", _mixed_estate)):
        if builder is _full_estate:
            entries = builder(tmp_path, store, sub)
        else:
            entries = builder(tmp_path, store)
        census = hub_census.census_document(entries)
        tallies = {state: 0 for state in sorted(hub_browse.BROWSE_STATES)}
        inspected = set()
        rows_by_id = {row["id"]: row for row in census["entries"]}
        for entry in entries:
            doc = hub_browse.browse_document(entry)
            tallies[doc["browse_state"]] += 1
            # The census row carries the browse verdict verbatim.
            row = rows_by_id[entry.id]
            assert row["browse_state"] == doc["browse_state"]
            assert row["locator_state"] == doc["locator_state"]
            assert row["verified_content_sha256"] == \
                doc["verified_content_sha256"]
            assert row["checksum_match"] == doc["checksum_match"]
            if doc["browse_state"] == hub_browse.BROWSE_INSPECTED:
                inspected.add(entry.id)
        assert census["by_browse_state"] == tallies
        # Same dispatch, same locator law: the inspected
        # set is exactly the parse censuses' parsed set.
        cc = hub_cc.content_census_document(entries)
        parsed = {row["id"] for row in cc["entries"]
                  if row["outcome"] == "parsed"}
        assert inspected == parsed


def test_b_all_parse_censuses_agree_on_outcomes(tmp_path):
    store = make_store(tmp_path)
    for name, entries, parsed_want in _three_estates(tmp_path, store):
        total = len(entries)
        reference = None
        for mod, fn, states, no_m, some_m, all_m in PARSE_CENSUSES:
            doc = getattr(mod, fn)(entries)
            view = (doc["entries_considered"], doc["by_outcome"],
                    doc["parsed_count"], doc["coverage_complete"])
            if reference is None:
                reference = view
            assert view == reference, (name, mod.__name__)
            assert doc["entries_considered"] == total, (name, mod.__name__)
            assert doc["parsed_count"] == parsed_want, (name, mod.__name__)
            assert doc["by_outcome"] == {
                "parsed": parsed_want,
                "unavailable": sum(
                    1 for e in entries
                    if hub.locator_state(e.locator) != "ready"
                    and _unavailable(e, entries)),
                "invalid": total - parsed_want - sum(
                    1 for e in entries
                    if hub.locator_state(e.locator) != "ready"
                    and _unavailable(e, entries))}, (name, mod.__name__)
            if total == 0:
                want_state = "no_entries"
            elif parsed_want == 0:
                want_state = no_m
            elif parsed_want == total:
                want_state = all_m
            else:
                want_state = some_m
            assert doc["census_state"] == want_state, (name, mod.__name__)
            assert doc["census_state"] in states, (name, mod.__name__)
            assert doc["coverage_complete"] is (parsed_want == total)


def _unavailable(entry, _entries):
    # An entry is unavailable exactly when its locator is
    # not ready (no read attempted); ready-but-refused is
    # invalid. Fixture-derived, from the locator law.
    return hub.locator_state(entry.locator) != "ready"


def test_b_string_volume_agrees_three_ways(tmp_path):
    store = make_store(tmp_path)
    for name, entries, _parsed in _three_estates(tmp_path, store):
        cc = hub_cc.content_census_document(entries)
        shape = hub_shape.content_shape_census_document(entries)
        distinct = hub_distinct.distinct_census_document(entries)
        assert cc["total_string_values"] == shape["total_strings"], name
        assert shape["total_strings"] == distinct["total_string_values"], name
        cc_rows = {row["id"]: row["string_value_count"]
                   for row in cc["entries"]}
        dc_rows = {row["id"]: row["string_value_count"]
                   for row in distinct["entries"]}
        assert cc_rows == dc_rows, name


def test_b_structure_agrees_across_censuses(tmp_path):
    store = make_store(tmp_path)
    for name, entries, _parsed in _three_estates(tmp_path, store):
        if name == "EMPTY":
            continue
        shape = hub_shape.content_shape_census_document(entries)
        breadth = hub_breadth.breadth_census_document(entries)
        schema = hub_schema.schema_census_document(entries)
        # Every container is an object or an array.
        assert breadth["total_containers"] == \
            shape["total_objects"] + shape["total_arrays"], name
        # The same objects, counted for identity.
        assert schema["total_objects"] == shape["total_objects"], name
        shape_rows = {row["id"]: row["object_count"]
                      for row in shape["entries"]}
        schema_rows = {row["id"]: row["object_count"]
                       for row in schema["entries"]}
        assert shape_rows == schema_rows, name


def test_b_duplicate_census_reconciles(tmp_path):
    store = make_store(tmp_path)
    entries = _mixed_estate(tmp_path, store)
    dup = hub_dup.duplicate_census_document(entries)
    # The embedded content census IS a direct P-193 call.
    assert dup["content_census"] == hub_cc.content_census_document(entries)
    # Independent test-side grouping by verified checksum,
    # from the composed rows alone.
    groups: dict[str, list[str]] = {}
    unidentified = 0
    for row in dup["content_census"]["entries"]:
        verified = row["verified_content_sha256"]
        if row["outcome"] != "parsed" or not verified:
            unidentified += 1
        else:
            groups.setdefault(verified, []).append(row["id"])
    want_groups = {sha: sorted(ids) for sha, ids in groups.items()
                   if len(ids) >= 2}
    got_groups = {g["verified_content_sha256"]:
                  sorted(m["id"] for m in g["entries"])
                  for g in dup["duplicate_groups"]}
    assert got_groups == want_groups
    assert dup["duplicate_entry_count"] == sum(
        len(ids) for ids in want_groups.values())
    assert dup["unique_entry_count"] == sum(
        1 for ids in groups.values() if len(ids) == 1)
    assert dup["unidentified_entry_count"] == unidentified
    assert (dup["duplicate_entry_count"] + dup["unique_entry_count"]
            + dup["unidentified_entry_count"]) == dup["count"]
    # The bare bundle: parsed, no verified checksum, so
    # unidentified and in no group.
    bare = next(e for e in entries if e.title == "Bare Bundle")
    grouped_ids = {m["id"] for g in dup["duplicate_groups"]
                   for m in g["entries"]}
    assert bare.id not in grouped_ids
    # The same pack registered twice: exactly one group of 2.
    store2 = make_store(tmp_path / "second")
    base = tmp_path / "twice"
    base.mkdir(parents=True, exist_ok=True)
    locator, pack = _lorebook_file(base, "orig.json")
    copy_path = base / "copy.json"
    copy_path.write_bytes(open(locator, "rb").read())
    sha = pack["manifest"]["content_sha256"]
    _register(store2, "lorebook_pack", "Original", locator, sha)
    _register(store2, "lorebook_pack", "Copy", str(copy_path), sha)
    dup2 = hub_dup.duplicate_census_document(store2.list_for_owner("u1"))
    assert dup2["duplicate_group_count"] == 1
    assert dup2["duplicate_groups"][0]["count"] == 2
    assert dup2["duplicate_entry_count"] == 2
    assert dup2["unique_entry_count"] == 0
    assert dup2["unidentified_entry_count"] == 0
    assert dup2["census_state"] == "all_duplicates"


def test_b_size_and_breadth_rows_agree_with_files(tmp_path):
    store = make_store(tmp_path)
    for name, entries, _parsed in _three_estates(tmp_path, store):
        if name == "EMPTY":
            continue
        size = hub_size.size_census_document(entries)
        rows = {row["id"]: row for row in size["entries"]}
        parsed_bytes = 0
        for entry in entries:
            row = rows[entry.id]
            if hub.locator_state(entry.locator) != "ready":
                assert row["file_bytes"] is None, (name, entry.title)
            else:
                # The row's bytes are the file's own bytes.
                assert row["file_bytes"] == os.path.getsize(entry.locator), \
                    (name, entry.title)
            if row["outcome"] == "parsed":
                parsed_bytes += row["file_bytes"]
        assert size["total_verified_bytes"] == parsed_bytes, name
        if name == "FULL":
            assert size["total_file_bytes"] == parsed_bytes, name
        breadth = hub_breadth.breadth_census_document(entries)
        assert sum(row["breadth_container_count"]
                   for row in breadth["entries"]
                   if row["outcome"] == "parsed") == \
            breadth["total_containers"], name
        for row in breadth["entries"]:
            assert row["widest_container_width"] <= \
                breadth["widest_container_width"], name


def _probe_estate(tmp_path, store):
    """Three lorebook packs splitting the Zephyr answer:
    one matched on both sides, one content-only, one
    metadata-only."""
    base = tmp_path / "probe"
    base.mkdir(parents=True, exist_ok=True)
    specs = [
        ("Zephyr Tales", "both.json", "Tale Entry",
         "The Zephyr Quill writes storms."),
        ("Plain Tales", "content.json", "Wind Entry",
         "Zephyr winds rise at dawn."),
        ("Zephyr Index", "meta.json", "Index Entry",
         "Calm waters hold still."),
    ]
    entries = []
    for title, fname, ename, content in specs:
        locator, pack = _lorebook_file(
            base, fname,
            entries=[_lore_entry("e1", ename, content, ["quill"])])
        entries.append(_register(
            store, "lorebook_pack", title, locator,
            pack["manifest"]["content_sha256"]))
    return entries


def test_b_unified_search_is_the_union(tmp_path):
    store = make_store(tmp_path)
    entries = _probe_estate(tmp_path, store)
    both, content_only, meta_only = entries
    meta = hub_search.search_document(entries, "Zephyr")
    content = hub_cs.content_search_document(entries, "Zephyr")
    unified = hub_unified.unified_search_document(entries, "Zephyr")
    # Composition verbatim: both banked documents embedded whole.
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
    assert rows[content_only.id]["matched_fields"] == []
    assert rows[meta_only.id]["occurrences"] is None
    assert rows[meta_only.id]["excerpt"] is None
    # Totals add without double counting the both-match.
    assert unified["total_matches"] == len(meta_ids | content_ids)
    assert unified["metadata_match_count"] == len(meta_ids)
    assert unified["content_match_count"] == len(content_ids)
    assert unified["both_count"] == len(meta_ids & content_ids)
    assert (unified["metadata_match_count"]
            + unified["content_match_count"]
            - unified["both_count"]) == unified["total_matches"]
    # A metadata-only probe and a no-hit probe agree too.
    tales = hub_unified.unified_search_document(entries, "Tales")
    assert {row["id"] for row in tales["matches"]} == {both.id, content_only.id}
    assert all(row["matched_by"] == "metadata" for row in tales["matches"])
    none = hub_unified.unified_search_document(entries, "qqqabsent")
    assert none["total_matches"] == 0
    assert none["search_state"] == "no_matches"


def test_b_unified_census_reconciles_with_unified(tmp_path):
    store = make_store(tmp_path)
    entries = _mixed_estate(tmp_path, store)
    unified = hub_unified.unified_search_document(entries, "Zephyr")
    census = hub_usc.unified_search_census_document(entries, "Zephyr")
    # The aggregator over a direct document IS the wrapper.
    assert hub_usc.build_unified_search_census(unified) == census
    assert census["unified_search"] == unified
    # Independent recomputation from the P-192 document.
    by_matched_by = {"metadata": 0, "content": 0, "both": 0}
    occurrences = 0
    for row in unified["matches"]:
        by_matched_by[row["matched_by"]] += 1
        if row["occurrences"] is not None:
            occurrences += row["occurrences"]
    assert census["by_matched_by"] == by_matched_by
    assert census["match_count"] == unified["match_count"]
    assert census["total_occurrences"] == occurrences
    assert census["total_matches"] == unified["total_matches"]
    assert census["source_metadata_match_count"] == \
        unified["metadata_match_count"]
    assert census["source_content_match_count"] == \
        unified["content_match_count"]
    assert census["source_both_count"] == unified["both_count"]
    by_skip = {outcome: 0 for outcome in hub_usc.SKIP_OUTCOMES}
    for row in unified["skipped_entries"]:
        by_skip[row["outcome"]] += 1
    assert census["by_skip_outcome"] == by_skip
    assert census["skipped_count"] == len(unified["skipped_entries"])
    assert census["entries_considered"] == unified["entries_considered"]
    assert census["entries_searched"] == unified["entries_searched"]
    assert census["truncated"] == unified["truncated"]
    assert census["coverage_complete"] == unified["coverage_complete"]
    # The MIXED estate's skips are real: ghost unavailable,
    # broken + wrong-kind invalid; coverage is incomplete.
    assert by_skip == {"unavailable": 1, "invalid": 2}
    assert census["coverage_complete"] is False
    # The searched outcome never appears among the skips.
    assert hub_usc.SKIP_OUTCOMES == ("unavailable", "invalid")
    assert "searched" not in hub_usc.SKIP_OUTCOMES


def test_b_search_refusals_agree(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store, "b10")
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
    # The same refusals over HTTP are 422s, list included.
    _factory, client = _client(tmp_path)
    for road in ("/hub/search", "/hub/content-search",
                 "/hub/unified-search", "/hub/unified-search-census"):
        assert client.get("/api/v1" + road).status_code == 422, road
        refused = client.get("/api/v1" + road,
                             params={"q": "Zephyr", "kind": "bogus_kind"})
        assert refused.status_code == 422, road
    assert client.get("/api/v1/hub",
                      params={"kind": "bogus_kind"}).status_code == 422


def test_b_kind_narrowing_agrees(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store, "b11")
    lore = next(e for e in entries if e.kind == "lorebook_pack")
    meta_all = hub_search.search_document(entries, "pack")
    assert meta_all["total_matches"] == 4
    meta_one = hub_search.search_document(
        entries, "pack", kind="lorebook_pack")
    assert meta_one["total_matches"] == 1
    assert meta_one["matches"][0]["id"] == lore.id
    content_one = hub_cs.content_search_document(
        entries, "Zephyr", kind="lorebook_pack")
    assert content_one["entries_considered"] == 1
    assert {row["id"] for row in content_one["matches"]} == {lore.id}
    unified_one = hub_unified.unified_search_document(
        entries, "Zephyr", kind="lorebook_pack")
    assert unified_one["entries_considered"] == 1
    assert {row["id"] for row in unified_one["matches"]} == {lore.id}
    # The censuses take no kind parameter at all and always
    # cover the whole estate handed to them.
    with pytest.raises(TypeError):
        hub_cc.content_census_document(entries, kind="lorebook_pack")
    with pytest.raises(TypeError):
        hub_census.census_document(entries, kind="lorebook_pack")
    assert hub_cc.content_census_document(entries)["count"] == 4


def test_b_truncation_agrees(tmp_path):
    store = make_store(tmp_path)
    entries = _truncation_estate(tmp_path, store)
    meta = hub_search.search_document(entries, "match pack")
    assert meta["total_matches"] == hub_search.MAX_MATCHES + 1
    assert meta["match_count"] == hub_search.MAX_MATCHES
    assert meta["truncated"] is True
    assert meta["search_state"] == "matches_truncated"
    # The content side's true answer on this estate: every
    # locator is missing, so nothing was searched and the
    # skips are all named unavailable (no truncation can
    # arise - there are no content matches to cap).
    content = hub_cs.content_search_document(entries, "match pack")
    assert content["entries_considered"] == hub_search.MAX_MATCHES + 1
    assert content["entries_searched"] == 0
    assert content["total_matches"] == 0
    assert len(content["skipped_entries"]) == hub_search.MAX_MATCHES + 1
    assert all(row["outcome"] == "unavailable"
               for row in content["skipped_entries"])
    assert content["coverage_complete"] is False
    unified = hub_unified.unified_search_document(entries, "match pack")
    assert unified["metadata_total_matches"] == hub_search.MAX_MATCHES + 1
    assert unified["content_total_matches"] == 0
    assert unified["match_count"] == hub_search.MAX_MATCHES
    assert unified["total_matches"] == hub_search.MAX_MATCHES
    assert unified["truncated"] is True
    assert unified["search_state"] == "matches_truncated"
    assert unified["coverage_complete"] is False
    # P-194 inherits the same capped verdict.
    census = hub_usc.unified_search_census_document(entries, "match pack")
    assert census["truncated"] is True
    assert census["coverage_complete"] is False
    assert census["match_count"] == hub_search.MAX_MATCHES
    assert census["metadata_total_matches"] == hub_search.MAX_MATCHES + 1


# ---------------------------------------------------------- Section C


def _all_unit_documents(entries):
    """Every hub document function over one estate."""
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


def test_c_every_hub_read_is_a_pure_read(tmp_path):
    store = make_store(tmp_path)
    entries = _mixed_estate(tmp_path, store)
    hub_bytes = (tmp_path / "data" / "hub.json").read_bytes()
    pack_bytes = {}
    for entry in entries:
        if os.path.isfile(entry.locator):
            pack_bytes[entry.locator] = open(entry.locator, "rb").read()
    _all_unit_documents(entries)
    assert (tmp_path / "data" / "hub.json").read_bytes() == hub_bytes
    for locator, raw in pack_bytes.items():
        assert open(locator, "rb").read() == raw
    # And over HTTP: every GET road leaves the same bytes.
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


def test_c_no_census_or_search_retains_content(tmp_path):
    store = make_store(tmp_path)
    entries = _mixed_estate(tmp_path, store)
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
    # P-194's OWN fields only: the embedded P-192 document
    # is the search's own answer and is judged with it.
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
    # The metadata search retains no excerpt either; the
    # only excerpts in the whole surface live inside the
    # P-191 / P-192 match rows, where the design allows.
    meta_blob = json.dumps(hub_search.search_document(entries, "Zephyr"))
    assert '"excerpt":' not in meta_blob
    content = hub_cs.content_search_document(entries, "Zephyr")
    assert content["matches"]  # the exception is exercised
    assert all("excerpt" in row for row in content["matches"])


def test_c_owner_scoping_holds_on_every_surface(tmp_path):
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
    # A search for the foreign titles finds nothing here.
    assert hub_search.search_document(estate, "Theirs")["total_matches"] == 0
    assert hub_unified.unified_search_document(
        estate, "Theirs")["total_matches"] == 0
    # Over HTTP the same law: the foreign entry is invisible
    # in lists and censuses and 404 on every per-entry road.
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
    assert store.get_entry(foreign.id) is not None  # nothing removed
    # Every GET road without a bearer is 401.
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


def test_c_mutating_roads_are_exactly_the_banked_writes(tmp_path):
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


def test_c_http_roads_answer_together(tmp_path):
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
    # All 17 operations, one session, one estate; every
    # HTTP document dict-equals the unit document.
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
    for road, params, want in checks:
        got = client.get("/api/v1" + road, params=params)
        assert got.status_code == 200, (road, got.text)
        assert got.json() == want, road
    deleted = client.delete(f"/api/v1/hub/entries/{ids[3]}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": ids[3]}
    assert client.get(f"/api/v1/hub/entries/{ids[3]}").status_code == 404
    assert client.get("/api/v1/hub").json()["count"] == 3


# ---------------------------------------------------------- Section D

FORBIDDEN_SURFACE_WORDS = ("history", "retention", "label", "bulk", "clear")


def test_d_carried_items_pinned_absent(tmp_path):
    # The three carried items - (1) binding label update,
    # (2) history retention / bulk clear, (3) unified-
    # search history - stay exactly as open as at P-199:
    # no road, no module, no public verb names any of them.
    roads = _openapi_hub_roads(tmp_path)
    for _method, path in roads:
        for word in FORBIDDEN_SURFACE_WORDS:
            assert word not in path, (word, path)
    hub_dir = REPO / "src" / "runmal" / "hub"
    for path in hub_dir.glob("*.py"):
        for word in FORBIDDEN_SURFACE_WORDS:
            assert word not in path.name, (word, path.name)
    for mod_name in list(TRUTH_MODULES) + ["router"]:
        mod = importlib.import_module(f"runmal.hub.{mod_name}")
        for name in dir(mod):
            if name.startswith("_"):
                continue
            for word in ("history", "retention", "label"):
                assert word not in name.lower(), (mod_name, name)
    # The only store writes are the banked pair: add and
    # the single-entry remove (no clear-all verb exists).
    store_verbs = [n for n in dir(hub.HubStore) if not n.startswith("_")]
    assert "add_entry" in store_verbs
    assert "remove_entry" in store_verbs
    assert not any("clear" in n.lower() for n in store_verbs)


KNOWN_HANDLER_CALLS = (
    "register_entry(", "entry_document(", "list_document(",
    "get_entry(", "remove_entry(",
    "browse_document(", "census_document(",
    "content_census_document(", "duplicate_census_document(",
    "content_shape_census_document(", "size_census_document(",
    "breadth_census_document(", "distinct_census_document(",
    "schema_census_document(", "search_document(",
    "content_search_document(", "unified_search_document(",
    "unified_search_census_document(",
)


def test_d_no_orphaned_module_or_road():
    source = (REPO / "src" / "runmal" / "hub" / "router.py").read_text()
    imports = dict(re.findall(
        r"from runmal\.hub import (\w+) as (hub_\w+)", source))
    # Every truth module is imported by the router, and
    # the router imports nothing else from the package.
    assert set(imports) == set(TRUTH_MODULES)
    handlers = source.split("router = APIRouter", 1)[1]
    for mod_name, alias in imports.items():
        # ... and used below the wiring line (no orphan import).
        assert (alias + ".") in handlers, mod_name
        # ... and its document function is called there.
        for fn in TRUTH_MODULES[mod_name]:
            if fn in ("register_entry", "entry_document", "list_document"):
                assert ("hub_service." + fn + "(") in handlers, fn
            else:
                assert (fn + "(") in handlers, fn
    # Every road's handler calls a banked truth function:
    # split the source into handler blocks and judge each.
    blocks = re.split(r"@router\.(?:get|post|delete)\(", source)[1:]
    assert len(blocks) == 17
    for block in blocks:
        assert any(call in block for call in KNOWN_HANDLER_CALLS), \
            block[:120]
