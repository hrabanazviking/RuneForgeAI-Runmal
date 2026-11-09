"""P-196 - Hub content-shape census (Part XII, DERIVED).

Pins: the shape-census document (schema tag,
census_state under the closed SHAPE_CENSUS_STATES law
judged on the parsed axis: no_entries / no_shape /
some_shape / all_shape); composition verbatim (the
embedded list equals a direct P-187 list_document
call; each pack measured ONLY through its own layer's
verified parse road - parse_pack x3, parse_share for
the preset bundle - under P-188's locator law and
imported size bound, outcomes under P-193's imported
OUTCOMES law); the walk law (every payload node
counted once by type under the closed NODE_TYPES law,
a boolean never a number, every dict key counted once
as structure, depth with the root at 1, a
content_sha256 member excluded whole); the stated
agreement (the string NODE count equals P-193's
string-value count on the same estate while no volume
field appears here); the no-silent-omission law
(every entry parsed or named by its row outcome,
coverage_complete as data, count = parsed +
unavailable + invalid); the distinctness fence (no
P-189 browse/checksum axis, no P-193 volume axis, no
P-194 query axis, no P-195 grouping axis among this
census's own fields); the no-content law (no key name
and no value from any payload anywhere in the
document); the pure-read law (registry and pack bytes
unchanged); owner scoping (unit and HTTP); the HTTP
road (200 owner, 401 without a bearer); and the
neighbours (migration head stays 0041; the bound and
the outcomes are the banked modules' own objects).
No network: fixtures only.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.hub import browse as hub_browse
from runmal.hub import census as hub_census
from runmal.hub import content_census as hub_cc
from runmal.hub import content_shape_census as hub_csc
from runmal.hub import registry as hub
from runmal.lorebooks import packs as lorebook_packs
from runmal.plugins import service as plugin_service
from runmal.presets import bundles as preset_bundles
from runmal.presets import packs as prompt_packs
from runmal.scenarios import packs as scenario_packs
from runmal.scenarios.store import ScenarioStore

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


def _lorebook_file(tmp_path, name="lorebook-pack.json", entries=None):
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
    path = tmp_path / name
    path.write_bytes(lorebook_packs.pack_to_bytes(pack))
    return str(path), pack


def _prompt_file(tmp_path):
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
    path = tmp_path / "prompt-pack.json"
    path.write_bytes(prompt_packs.pack_to_bytes(pack))
    return str(path), pack


def _scenario_file(tmp_path):
    store = ScenarioStore(tmp_path / "scenarios.json")
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
    record = store.create("owner-p196", body, now=STAMP)
    pack = scenario_packs.build_pack(record, exported_at=STAMP)
    path = tmp_path / "scenario-pack.json"
    path.write_bytes(scenario_packs.pack_to_bytes(pack))
    return str(path), pack


def _bundle_file(tmp_path, *, bare: bool = False):
    bundle = preset_bundles.validate_bundle({
        "name": "Hall Bundle",
        "prompts": [{"identifier": "main",
                     "content": "Zephyr bundle text for the hall."}],
        "prompt_order": [{"identifier": "main", "enabled": True}],
    })
    share = preset_bundles.build_share(bundle, exported_at=STAMP)
    path = tmp_path / "preset-bundle.json"
    if bare:
        path.write_text(json.dumps(bundle))
        return str(path), bundle
    path.write_text(json.dumps(share))
    return str(path), share


def _expected_shape(entry, raw):
    """Independent test-side measure: the owning layer's
    own parse road, then a plain iterative walk under
    the shape law (content_sha256 members excluded
    whole, booleans never numbers, root at depth 1)."""
    if entry.kind == "lorebook_pack":
        payload = lorebook_packs.parse_pack(raw)["lorebook"]
    elif entry.kind == "prompt_pack":
        payload = prompt_packs.parse_pack(raw)["items"]
    elif entry.kind == "scenario_pack":
        payload = scenario_packs.parse_pack(raw)["scenario"]
    else:
        payload, _report = preset_bundles.parse_share(
            json.loads(raw.decode("utf-8")))
    shape = {"object_count": 0, "array_count": 0,
             "string_count": 0, "number_count": 0,
             "boolean_count": 0, "null_count": 0,
             "node_count": 0, "key_count": 0, "max_depth": 0}
    stack = [(payload, 1)]
    while stack:
        node, depth = stack.pop()
        shape["max_depth"] = max(shape["max_depth"], depth)
        shape["node_count"] += 1
        if isinstance(node, dict):
            shape["object_count"] += 1
            for key, value in node.items():
                if key == "content_sha256":
                    continue
                shape["key_count"] += 1
                stack.append((value, depth + 1))
        elif isinstance(node, list):
            shape["array_count"] += 1
            stack.extend((item, depth + 1) for item in node)
        elif isinstance(node, bool):
            shape["boolean_count"] += 1
        elif isinstance(node, str):
            shape["string_count"] += 1
        elif isinstance(node, (int, float)):
            shape["number_count"] += 1
        else:
            shape["null_count"] += 1
    return shape


def _full_estate(tmp_path, store):
    entries = []
    for kind, maker in (
            ("lorebook_pack", _lorebook_file),
            ("prompt_pack", _prompt_file),
            ("scenario_pack", _scenario_file),
            ("preset_bundle", _bundle_file)):
        locator, pack = maker(tmp_path)
        sha = pack["manifest"]["content_sha256"] \
            if "manifest" in pack else ""
        entries.append(_register(store, kind, "A pack", locator, sha))
    return entries


_SHAPE_FIELDS = (
    "object_count", "array_count", "string_count",
    "number_count", "boolean_count", "null_count",
    "node_count", "key_count", "max_depth")


# ------------------------------------------------------------ the estate view


def test_empty_estate_is_no_entries_with_zero_filled_axes(tmp_path):
    doc = hub_csc.content_shape_census_document([])
    assert doc["schema"] == "runmal-p196-hub-content-shape-census-v1"
    assert doc["census_state"] == "no_entries"
    assert doc["census_state"] in hub_csc.SHAPE_CENSUS_STATES
    assert doc["count"] == 0
    assert doc["entries"] == []
    assert doc["by_outcome"] == {
        "invalid": 0, "parsed": 0, "unavailable": 0}
    assert doc["by_kind_shape"] == {
        kind: {"entries": 0, "parsed": 0, "objects": 0,
               "arrays": 0, "strings": 0, "numbers": 0,
               "booleans": 0, "nulls": 0, "nodes": 0,
               "keys": 0, "max_depth": 0}
        for kind in hub.KIND_FORMATS}
    assert doc["by_node_type"] == {
        "array": 0, "boolean": 0, "null": 0,
        "number": 0, "object": 0, "string": 0}
    assert doc["total_nodes"] == 0 and doc["total_keys"] == 0
    assert doc["max_depth"] == 0
    assert doc["deepest_entry"] is None
    assert doc["coverage_complete"] is True
    assert doc["list"] == hub.list_document([])
    assert doc["kind_formats"] == hub.KIND_FORMATS
    assert doc["max_browse_bytes"] == hub_csc.MAX_BROWSE_BYTES


def test_full_estate_all_shape_and_measured_verbatim(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    doc = hub_csc.content_shape_census_document(
        store.list_for_owner("u1"))
    assert doc["census_state"] == "all_shape"
    assert doc["count"] == 4
    assert doc["parsed_count"] == 4
    assert doc["coverage_complete"] is True
    assert doc["list"] == hub.list_document(entries)
    assert doc["by_outcome"] == {
        "invalid": 0, "parsed": 4, "unavailable": 0}
    totals = {field: 0 for field in _SHAPE_FIELDS}
    totals["max_depth"] = 0
    for row, entry in zip(doc["entries"], entries, strict=True):
        raw = open(entry.locator, "rb").read()
        expected = _expected_shape(entry, raw)
        assert row["id"] == entry.id
        assert row["outcome"] == "parsed"
        assert row["error"] == ""
        for field in _SHAPE_FIELDS:
            assert row[field] == expected[field], (entry.kind, field)
            if field == "max_depth":
                totals[field] = max(totals[field], expected[field])
            else:
                totals[field] += expected[field]
        assert row["node_count"] == (
            row["object_count"] + row["array_count"]
            + row["string_count"] + row["number_count"]
            + row["boolean_count"] + row["null_count"])
        assert row["node_count"] > 0 and row["key_count"] > 0
        axis = doc["by_kind_shape"][entry.kind]
        assert axis["entries"] == 1 and axis["parsed"] == 1
        assert axis["nodes"] == expected["node_count"]
        assert axis["keys"] == expected["key_count"]
        assert axis["max_depth"] == expected["max_depth"]
    assert doc["total_objects"] == totals["object_count"]
    assert doc["total_arrays"] == totals["array_count"]
    assert doc["total_strings"] == totals["string_count"]
    assert doc["total_numbers"] == totals["number_count"]
    assert doc["total_booleans"] == totals["boolean_count"]
    assert doc["total_nulls"] == totals["null_count"]
    assert doc["total_nodes"] == totals["node_count"]
    assert doc["total_keys"] == totals["key_count"]
    assert doc["max_depth"] == totals["max_depth"]
    assert doc["by_node_type"] == {
        "array": totals["array_count"],
        "boolean": totals["boolean_count"],
        "null": totals["null_count"],
        "number": totals["number_count"],
        "object": totals["object_count"],
        "string": totals["string_count"]}
    assert sum(doc["by_node_type"].values()) == doc["total_nodes"]
    kind_nodes = sum(a["nodes"] for a in doc["by_kind_shape"].values())
    assert kind_nodes == doc["total_nodes"]
    deepest = doc["deepest_entry"]
    assert deepest["max_depth"] == doc["max_depth"]
    assert deepest["id"] in {row["id"] for row in doc["entries"]}


# ------------------------------------------------------------ the walk law


def test_walk_law_hand_pinned():
    payload = {
        "content_sha256": "z" * 64,
        "nested": {"content_sha256": {"deep": "hidden"},
                   "keep": "yes"},
        "items": ["one", 7, True, None, {"two": 2.5}],
        "empty_obj": {}, "empty_list": [],
        "flag": False, "nothing": None,
    }
    shape = hub_csc._shape_stats(payload)
    # Hand count: nodes = root obj; nested obj + "yes";
    # items list + "one", 7, True, None, {"two": 2.5}
    # obj + 2.5; empty obj; empty list; False; None.
    assert shape["object_count"] == 4
    assert shape["array_count"] == 2
    assert shape["string_count"] == 2
    assert shape["number_count"] == 2
    assert shape["boolean_count"] == 2
    assert shape["null_count"] == 2
    assert shape["node_count"] == 14
    # Keys: nested, items, empty_obj, empty_list, flag,
    # nothing at the root (content_sha256 excluded);
    # keep inside nested (its content_sha256 excluded);
    # two inside the items object.
    assert shape["key_count"] == 8
    assert shape["max_depth"] == 4
    assert hub_csc._shape_stats("scalar") == {
        "object_count": 0, "array_count": 0, "string_count": 1,
        "number_count": 0, "boolean_count": 0, "null_count": 0,
        "node_count": 1, "key_count": 0, "max_depth": 1}
    assert hub_csc._shape_stats([])["max_depth"] == 1
    assert hub_csc._shape_stats(True)["boolean_count"] == 1
    assert hub_csc._shape_stats(True)["number_count"] == 0


def test_string_nodes_agree_with_p193_but_no_volume_fields(tmp_path):
    store = make_store(tmp_path)
    _full_estate(tmp_path, store)
    estate = store.list_for_owner("u1")
    shape_doc = hub_csc.content_shape_census_document(estate)
    volume_doc = hub_cc.content_census_document(estate)
    # The stated expected agreement: the same string
    # nodes, counted here and counted by P-193.
    for srow, vrow in zip(shape_doc["entries"],
                          volume_doc["entries"], strict=True):
        assert srow["string_count"] == vrow["string_value_count"]
        assert srow["verified_content_sha256"] == \
            vrow["verified_content_sha256"]
    assert shape_doc["total_strings"] == volume_doc["total_string_values"]
    blob = json.dumps(shape_doc)
    assert "string_char" not in blob
    assert "string_value" not in blob
    assert "largest_content_entry" not in shape_doc
    assert "by_kind_content" not in shape_doc


def test_mixed_estate_is_some_shape_with_named_outcomes(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Good", locator,
              pack["manifest"]["content_sha256"])
    _register(store, "prompt_pack", "Ghost", str(tmp_path / "ghost.json"))
    bad = tmp_path / "broken.json"
    bad.write_bytes(b"{not a pack")
    _register(store, "scenario_pack", "Broken", str(bad))
    _register(store, "preset_bundle", "Dir", str(tmp_path))
    doc = hub_csc.content_shape_census_document(
        store.list_for_owner("u1"))
    assert doc["census_state"] == "some_shape"
    assert doc["coverage_complete"] is False
    assert doc["by_outcome"] == {
        "invalid": 1, "parsed": 1, "unavailable": 2}
    assert doc["count"] == (
        doc["by_outcome"]["parsed"]
        + doc["by_outcome"]["unavailable"]
        + doc["by_outcome"]["invalid"])
    rows = {row["title"]: row for row in doc["entries"]}
    assert rows["Ghost"]["outcome"] == "unavailable"
    assert rows["Ghost"]["locator_state"] == "missing"
    assert rows["Ghost"]["node_count"] == 0
    assert rows["Dir"]["outcome"] == "unavailable"
    assert rows["Dir"]["locator_state"] == "not_a_file"
    assert rows["Broken"]["outcome"] == "invalid"
    assert rows["Broken"]["error"] != ""
    assert rows["Broken"]["verified_content_sha256"] == ""
    assert rows["Good"]["node_count"] > 0
    assert doc["total_nodes"] == rows["Good"]["node_count"]


def test_all_missing_estate_is_no_shape(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", "Ghost", str(tmp_path / "g.json"))
    doc = hub_csc.content_shape_census_document(
        store.list_for_owner("u1"))
    assert doc["census_state"] == "no_shape"
    assert doc["parsed_count"] == 0
    assert doc["total_nodes"] == 0
    assert doc["max_depth"] == 0
    assert doc["deepest_entry"] is None
    assert doc["coverage_complete"] is False


def test_bare_bundle_parsed_with_empty_verified_checksum(tmp_path):
    store = make_store(tmp_path)
    locator, _bundle = _bundle_file(tmp_path, bare=True)
    _register(store, "preset_bundle", "Bare", locator)
    doc = hub_csc.content_shape_census_document(
        store.list_for_owner("u1"))
    row = doc["entries"][0]
    assert row["outcome"] == "parsed"
    assert row["verified_content_sha256"] == ""
    assert row["node_count"] > 0 and row["object_count"] >= 1
    assert doc["census_state"] == "all_shape"


def test_wrong_kind_pack_is_invalid_with_road_refusal(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _prompt_file(tmp_path)
    _register(store, "lorebook_pack", "Wrong kind", locator)
    doc = hub_csc.content_shape_census_document(
        store.list_for_owner("u1"))
    row = doc["entries"][0]
    assert row["outcome"] == "invalid"
    assert row["error"] != ""
    assert doc["census_state"] == "no_shape"


def test_oversize_pack_is_invalid_under_the_imported_bound(
        tmp_path, monkeypatch):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Big", locator)
    monkeypatch.setattr(hub_csc, "MAX_BROWSE_BYTES", 8)
    doc = hub_csc.content_shape_census_document(
        store.list_for_owner("u1"))
    row = doc["entries"][0]
    assert row["outcome"] == "invalid"
    assert row["error"] == "pack file too large to shape-census"
    assert doc["max_browse_bytes"] == 8


def test_deepest_entry_and_tie_keeps_store_order(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    doc = hub_csc.content_shape_census_document(
        store.list_for_owner("u1"))
    expected = {}
    for entry in entries:
        raw = open(entry.locator, "rb").read()
        expected[entry.id] = _expected_shape(entry, raw)
    best = max(expected.values(), key=lambda s: s["max_depth"])
    first_best = next(
        e for e in entries
        if expected[e.id]["max_depth"] == best["max_depth"])
    assert doc["deepest_entry"]["id"] == first_best.id
    assert doc["deepest_entry"]["max_depth"] == best["max_depth"]
    store2 = make_store(tmp_path / "second")
    a, _pa = _lorebook_file(tmp_path, "a.json")
    b, _pb = _lorebook_file(tmp_path, "b.json")
    first = _register(store2, "lorebook_pack", "First", a)
    _register(store2, "lorebook_pack", "Second", b)
    doc2 = hub_csc.content_shape_census_document(
        store2.list_for_owner("u1"))
    rows = doc2["entries"]
    assert rows[0]["max_depth"] == rows[1]["max_depth"]
    assert doc2["deepest_entry"]["id"] == first.id


# ------------------------------------------------------------ distinctness


def test_distinctness_fence_no_banked_axes(tmp_path):
    store = make_store(tmp_path)
    _full_estate(tmp_path, store)
    estate = store.list_for_owner("u1")
    doc = hub_csc.content_shape_census_document(estate)
    # No P-189 axis (browse verdicts / checksum claims).
    assert "by_browse_state" not in doc
    assert "by_checksum_match" not in doc
    # No P-193 volume axis (values measured for length).
    assert "by_kind_content" not in doc
    assert "total_string_values" not in doc
    assert "total_string_chars" not in doc
    assert "largest_content_entry" not in doc
    # No P-194 query axis and no P-195 grouping axis.
    assert "by_matched_by" not in doc
    assert "duplicate_groups" not in doc
    assert "duplicate_entry_count" not in doc
    for row in doc["entries"]:
        assert "browse_state" not in row
        assert "checksum_match" not in row
        assert "string_value_count" not in row
        assert "string_char_count" not in row
    # And the banked censuses carry no shape axis.
    p189 = hub_census.census_document(estate)
    assert "by_node_type" not in p189
    assert "total_nodes" not in json.dumps(p189)


def test_no_content_or_key_names_anywhere(tmp_path):
    store = make_store(tmp_path)
    _full_estate(tmp_path, store)
    doc = hub_csc.content_shape_census_document(
        store.list_for_owner("u1"))
    blob = json.dumps(doc)
    # Payload string VALUES never appear.
    assert "Zephyr Quill writes storms" not in blob
    assert "The Harbour Voice" not in blob
    # Payload KEY NAMES never appear (counts only).
    assert "inclusion_group" not in blob
    assert "initial_variables" not in blob
    assert '"excerpt":' not in blob
    assert '"payload":' not in blob


# ------------------------------------------------------------ pure read / scope


def test_census_writes_nothing(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    hub_bytes = (tmp_path / "data" / "hub.json").read_bytes()
    pack_bytes = {e.locator: open(e.locator, "rb").read()
                  for e in entries}
    hub_csc.content_shape_census_document(store.list_for_owner("u1"))
    assert (tmp_path / "data" / "hub.json").read_bytes() == hub_bytes
    for locator, raw in pack_bytes.items():
        assert open(locator, "rb").read() == raw


def test_foreign_entries_never_enter_the_census(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Mine", locator,
              pack["manifest"]["content_sha256"], owner="u1")
    _register(store, "lorebook_pack", "Theirs", locator,
              pack["manifest"]["content_sha256"], owner="u2")
    doc = hub_csc.content_shape_census_document(
        store.list_for_owner("u1"))
    assert doc["count"] == 1
    assert doc["entries"][0]["title"] == "Mine"


def test_http_road_owner_scoped_and_bearer_gated(tmp_path):
    _factory, client = _client(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Mine",
        "locator": locator,
        "content_sha256": pack["manifest"]["content_sha256"]})
    assert created.status_code == 201, created.text
    response = client.get("/api/v1/hub/content-shape-census")
    assert response.status_code == 200
    doc = response.json()
    assert doc["schema"] == "runmal-p196-hub-content-shape-census-v1"
    assert doc["count"] == 1
    assert doc["entries"][0]["outcome"] == "parsed"
    assert doc["entries"][0]["node_count"] > 0
    bare = TestClient(create_app(_factory))
    assert bare.get("/api/v1/hub/content-shape-census").status_code == 401


def test_neighbours_migration_head_and_imported_laws(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == MIGRATIONS[-1][0] == "0041"
    assert hub_csc.MAX_BROWSE_BYTES == 16 * 1024 * 1024
    assert hub_csc.MAX_BROWSE_BYTES == hub_browse.MAX_BROWSE_BYTES
    assert hub_csc.OUTCOMES is hub_cc.OUTCOMES
    assert hub_csc.NODE_TYPES == {
        "object", "array", "string", "number", "boolean", "null"}
    assert hub_csc.SHAPE_CENSUS_STATES == {
        "no_entries", "no_shape", "some_shape", "all_shape"}
