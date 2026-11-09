"""P-200 - Hub schema census (Part XII, DERIVED).

Pins: the schema-census document (schema tag,
census_state under the closed SCHEMA_CENSUS_STATES
law judged on the parsed axis: no_entries / no_schema
/ some_schema / all_schema); composition verbatim
(the embedded list equals a direct P-187 list_document
call; each pack measured ONLY through its own layer's
verified parse road - parse_pack x3, parse_share for
the preset bundle - under P-188's locator law and
imported size bound); the signature law (an object's
shape is the SET of its counted keys - unordered,
exact; the empty object counts as a shape;
content_sha256 members excluded whole - not a counted
key of the parent, subtree never walked; lists and
scalars never shapes); the identity axes (per-row
distinct / repeated / extra / shared shapes; estate
distinct / repeated / shared / extra shapes; the
by-kind pooled distinct-shape axis; the largest
schema holder); the occurrence agreement (each row's
object_count equals P-196's on the same estate, while
no node / key-total / depth axis appears anywhere);
the sub-pack overlap heart (two P-195-unique packs
sharing record shapes are stated as sharing shapes;
one pack twice shares every shape); the
no-silent-omission law (every entry parsed or named
by its row outcome under P-193's imported OUTCOMES
law, coverage_complete as data, count = parsed +
unavailable + invalid; shared counts over parsed
entries only); the no-content law (no payload key
name, no key-set digest and no payload value anywhere
in the document); the distinctness fence (no P-189,
P-193, P-194, P-195, P-196, P-197, P-198 or P-199 axis
among this census's own fields); the pure-read law
(registry and pack bytes unchanged); owner scoping
(unit and HTTP); the HTTP road (200 owner, 401
without a bearer); and the neighbours (migration head
stays 0041; the outcomes law and the bound are the
banked modules' own objects). No network: fixtures
only.
"""

from __future__ import annotations

import hashlib
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
from runmal.hub import content_shape_census as hub_sh
from runmal.hub import duplicate_census as hub_dup
from runmal.hub import registry as hub
from runmal.hub import schema_census as hub_sc
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
    record = store.create("owner-p200", body, now=STAMP)
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


def _expected_shapes(entry, raw):
    """Independent test-side measure: the owning layer's
    own parse road, then a plain recursive walk holding
    the raw key-set of every dict node (the test may
    hold key-sets; the census document never does). A
    content_sha256 member is skipped whole."""
    if entry.kind == "lorebook_pack":
        payload = lorebook_packs.parse_pack(raw)["lorebook"]
    elif entry.kind == "prompt_pack":
        payload = prompt_packs.parse_pack(raw)["items"]
    elif entry.kind == "scenario_pack":
        payload = scenario_packs.parse_pack(raw)["scenario"]
    else:
        payload, _report = preset_bundles.parse_share(
            json.loads(raw.decode("utf-8")))
    shapes = []
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            keys = frozenset(
                key for key in node if key != "content_sha256")
            shapes.append(keys)
            for key in keys:
                stack.append(node[key])
        elif isinstance(node, list):
            stack.extend(node)
    return shapes


def _expected_estate(entries):
    """Per-entry shape lists plus the estate-wide
    distinct / repeated / shared expectations, computed
    from the raw key-sets alone."""
    per_entry = []
    for entry in entries:
        raw = open(entry.locator, "rb").read()
        per_entry.append(_expected_shapes(entry, raw))
    distinct_sets = [set(shapes) for shapes in per_entry]
    estate_distinct = set().union(*distinct_sets) if distinct_sets else set()
    shared = {s for s in estate_distinct
              if sum(1 for d in distinct_sets if s in d) >= 2}
    occurrences = [len(shapes) for shapes in per_entry]
    estate_occurrences = sum(occurrences)
    repeated = {s for s in estate_distinct
                if sum(shapes.count(s) for shapes in per_entry) >= 2}
    return per_entry, {
        "total_objects": estate_occurrences,
        "total_distinct_shapes": len(estate_distinct),
        "total_repeated_shapes": len(repeated),
        "total_shared_shapes": len(shared),
        "total_extra_shapes": estate_occurrences - len(estate_distinct),
    }


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


# ------------------------------------------------------------ the estate view


def test_empty_estate_is_no_entries_with_zero_filled_axes(tmp_path):
    doc = hub_sc.schema_census_document([])
    assert doc["schema"] == "runmal-p200-hub-schema-census-v1"
    assert doc["census_state"] == "no_entries"
    assert doc["census_state"] in hub_sc.SCHEMA_CENSUS_STATES
    assert doc["count"] == 0
    assert doc["entries"] == []
    assert doc["by_outcome"] == {
        "invalid": 0, "parsed": 0, "unavailable": 0}
    assert doc["by_kind_schema"] == {
        kind: {"entries": 0, "parsed": 0, "objects": 0,
               "distinct_shapes": 0, "extra_shapes": 0}
        for kind in hub.KIND_FORMATS}
    assert doc["total_objects"] == 0
    assert doc["total_distinct_shapes"] == 0
    assert doc["total_repeated_shapes"] == 0
    assert doc["total_shared_shapes"] == 0
    assert doc["total_extra_shapes"] == 0
    assert doc["largest_schema_entry"] is None
    assert doc["coverage_complete"] is True
    assert doc["list"] == hub.list_document([])
    assert doc["kind_formats"] == hub.KIND_FORMATS
    assert doc["max_browse_bytes"] == hub_sc.MAX_BROWSE_BYTES


def test_full_estate_all_schema_and_measured_verbatim(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    per_entry, expected = _expected_estate(entries)
    doc = hub_sc.schema_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "all_schema"
    assert doc["count"] == 4
    assert doc["parsed_count"] == 4
    assert doc["coverage_complete"] is True
    assert doc["list"] == hub.list_document(entries)
    assert doc["by_outcome"] == {
        "invalid": 0, "parsed": 4, "unavailable": 0}
    distinct_sets = [set(shapes) for shapes in per_entry]
    for row, entry, shapes in zip(
            doc["entries"], entries, per_entry, strict=True):
        assert row["id"] == entry.id
        assert row["outcome"] == "parsed"
        assert row["error"] == ""
        assert row["object_count"] == len(shapes)
        assert row["distinct_shape_count"] == len(set(shapes))
        assert row["repeated_shape_count"] == sum(
            1 for s in set(shapes) if shapes.count(s) >= 2)
        assert row["extra_shape_count"] == (
            len(shapes) - len(set(shapes)))
        assert row["shared_shape_count"] == sum(
            1 for s in set(shapes)
            if sum(1 for d in distinct_sets if s in d) >= 2)
        assert row["verified_content_sha256"] == entry.content_sha256
        axis = doc["by_kind_schema"][entry.kind]
        assert axis["entries"] == 1 and axis["parsed"] == 1
        assert axis["objects"] == len(shapes)
        assert axis["distinct_shapes"] == len(set(shapes))
        assert axis["extra_shapes"] == len(shapes) - len(set(shapes))
    for field, want in expected.items():
        assert doc[field] == want, field
    assert doc["total_shared_shapes"] <= doc["total_repeated_shapes"]
    kind_axes = doc["by_kind_schema"].values()
    assert sum(a["objects"] for a in kind_axes) == doc["total_objects"]
    largest = doc["largest_schema_entry"]
    assert largest["distinct_shape_count"] == max(
        row["distinct_shape_count"] for row in doc["entries"])
    assert largest["id"] in {row["id"] for row in doc["entries"]}


def test_verified_checksums_are_the_parse_roads_own(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    doc = hub_sc.schema_census_document(entries)
    for row, entry in zip(doc["entries"], entries, strict=True):
        assert row["verified_content_sha256"] == entry.content_sha256
        assert row["verified_content_sha256"] != ""


# ------------------------------------------------------------ the signature law


def test_signature_law_hand_pinned():
    payload = {
        "content_sha256": {"inner": {"deep": 1}},
        "alpha": {"x": 1, "y": 2},
        "beta": {"y": 2, "x": 1},
        "gamma": {"x": 1},
        "empty": {},
        "items": [{"x": 1, "y": 2}, {"z": 0}, "text", 7, None],
        "nested": {"content_sha256": "abc",
                   "keep": {"x": 1, "y": 2}},
    }
    total, counts = hub_sc._shape_stats(payload)
    # Root (content_sha256 not a counted key), alpha,
    # beta, gamma, empty, two item objects, nested
    # (its counted key-set is {keep} alone) and keep:
    # nine object occurrences.
    assert total == 9
    assert len(counts) == 6
    repeated = sum(1 for n in counts.values() if n >= 2)
    assert repeated == 1  # only the {x, y} shape repeats
    assert counts[hub_sc._signature({"x", "y"})] == 4
    assert counts[hub_sc._signature(set())] == 1
    assert counts[hub_sc._signature({"keep"})] == 1
    # Member order is not structure.
    assert hub_sc._signature(["y", "x"]) == hub_sc._signature(["x", "y"])
    # The excluded subtree contributes no shape, and the
    # root's signature never includes content_sha256.
    assert hub_sc._signature({"inner"}) not in counts
    root_with = {"alpha", "beta", "gamma", "empty",
                 "items", "nested", "content_sha256"}
    assert hub_sc._signature(root_with) not in counts
    assert counts[hub_sc._signature(root_with - {"content_sha256"})] == 1


# ------------------------------------------------- agreement + the overlap heart


def test_occurrence_agreement_with_p196_and_no_count_axis(tmp_path):
    store = make_store(tmp_path)
    _full_estate(tmp_path, store)
    estate = store.list_for_owner("u1")
    doc = hub_sc.schema_census_document(estate)
    p196 = hub_sh.content_shape_census_document(estate)
    # The stated expected agreement: the same objects
    # counted - P-196's per-row and total object counts
    # match exactly, because both censuses walk the
    # same law.
    assert doc["total_objects"] == p196["total_objects"]
    for row, prow in zip(doc["entries"], p196["entries"], strict=True):
        assert row["object_count"] == prow["object_count"]
    # And no node, key-total or depth fact was carried.
    blob = json.dumps(doc)
    assert "key_count" not in blob
    assert "node_count" not in blob
    assert "max_depth" not in blob
    assert "deepest_entry" not in doc
    assert "by_node_type" not in doc
    assert "by_kind_shape" not in doc


def test_sub_pack_overlap_shared_but_not_a_duplicate(tmp_path):
    store = make_store(tmp_path)
    entries_a = [
        _lore_entry("a1", "Dawn Entry", "Shared dawn text.", ["dawn"]),
        _lore_entry("a2", "A Only", "Only in A.", ["alpha"])]
    entries_b = [
        _lore_entry("b1", "Dawn Copy", "Different words entirely.", ["dawn"]),
        _lore_entry("b2", "B Only", "Only in B, unlike A.", ["beta"])]
    loc_a, pack_a = _lorebook_file(tmp_path, "a.json", entries_a)
    loc_b, pack_b = _lorebook_file(tmp_path, "b.json", entries_b)
    first = _register(store, "lorebook_pack", "Version A", loc_a,
                      pack_a["manifest"]["content_sha256"])
    second = _register(store, "lorebook_pack", "Version B", loc_b,
                       pack_b["manifest"]["content_sha256"])
    estate = store.list_for_owner("u1")
    _per_entry, expected = _expected_estate([first, second])
    doc = hub_sc.schema_census_document(estate)
    # Different text throughout, one record shape: every
    # shape the two packs use is shared.
    assert doc["total_shared_shapes"] == expected["total_shared_shapes"]
    assert doc["total_shared_shapes"] > 0
    assert doc["total_shared_shapes"] == doc["total_distinct_shapes"]
    for row in doc["entries"]:
        assert row["shared_shape_count"] == row["distinct_shape_count"]
    # The same estate at P-195's whole-pack grain: the two
    # packs are simply unique - no duplicate group exists.
    dup = hub_dup.duplicate_census_document(estate)
    assert dup["census_state"] == "no_duplicates"
    assert dup["duplicate_group_count"] == 0
    assert dup["distinct_content_count"] == 2


def test_same_pack_twice_shares_every_distinct_shape(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path, "orig.json")
    raw = open(locator, "rb").read()
    copy_path = tmp_path / "copy.json"
    copy_path.write_bytes(raw)
    sha = pack["manifest"]["content_sha256"]
    _register(store, "lorebook_pack", "Original", locator, sha)
    _register(store, "lorebook_pack", "Copy", str(copy_path), sha)
    doc = hub_sc.schema_census_document(store.list_for_owner("u1"))
    rows = doc["entries"]
    assert rows[0]["distinct_shape_count"] == rows[1]["distinct_shape_count"]
    assert doc["total_distinct_shapes"] == rows[0]["distinct_shape_count"]
    assert doc["total_shared_shapes"] == doc["total_distinct_shapes"]
    for row in rows:
        assert row["shared_shape_count"] == row["distinct_shape_count"]
    assert doc["total_objects"] == 2 * rows[0]["object_count"]
    # The by-kind axis pools: the kind's distinct count is
    # the single pack's, not the sum of the rows'.
    axis = doc["by_kind_schema"]["lorebook_pack"]
    assert axis["distinct_shapes"] == rows[0]["distinct_shape_count"]
    assert axis["objects"] == doc["total_objects"]


# ------------------------------------------------------------ outcomes / honesty


def test_mixed_estate_is_some_schema_with_named_outcomes(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Good", locator,
              pack["manifest"]["content_sha256"])
    _register(store, "prompt_pack", "Ghost", str(tmp_path / "ghost.json"))
    bad = tmp_path / "broken.json"
    bad.write_bytes(b"{not a pack")
    _register(store, "scenario_pack", "Broken", str(bad))
    _register(store, "preset_bundle", "Dir", str(tmp_path))
    doc = hub_sc.schema_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "some_schema"
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
    assert rows["Ghost"]["distinct_shape_count"] == 0
    assert rows["Ghost"]["shared_shape_count"] == 0
    assert rows["Dir"]["outcome"] == "unavailable"
    assert rows["Dir"]["locator_state"] == "not_a_file"
    assert rows["Broken"]["outcome"] == "invalid"
    assert rows["Broken"]["error"] != ""
    assert rows["Broken"]["verified_content_sha256"] == ""
    # Shared counts are computed over parsed entries only:
    # with one parsed entry nothing can be shared.
    assert doc["total_shared_shapes"] == 0
    assert rows["Good"]["shared_shape_count"] == 0
    assert doc["total_distinct_shapes"] == \
        rows["Good"]["distinct_shape_count"]


def test_all_missing_estate_is_no_schema(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", "Ghost", str(tmp_path / "g.json"))
    doc = hub_sc.schema_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "no_schema"
    assert doc["parsed_count"] == 0
    assert doc["total_objects"] == 0
    assert doc["total_distinct_shapes"] == 0
    assert doc["largest_schema_entry"] is None
    assert doc["coverage_complete"] is False


def test_bare_bundle_parsed_with_empty_verified_checksum(tmp_path):
    store = make_store(tmp_path)
    locator, _bundle = _bundle_file(tmp_path, bare=True)
    _register(store, "preset_bundle", "Bare", locator)
    doc = hub_sc.schema_census_document(store.list_for_owner("u1"))
    row = doc["entries"][0]
    assert row["outcome"] == "parsed"
    assert row["verified_content_sha256"] == ""
    assert row["object_count"] > 0
    assert row["distinct_shape_count"] > 0
    assert doc["census_state"] == "all_schema"


def test_wrong_kind_pack_is_invalid_with_road_refusal(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _prompt_file(tmp_path)
    _register(store, "lorebook_pack", "Wrong kind", locator)
    doc = hub_sc.schema_census_document(store.list_for_owner("u1"))
    row = doc["entries"][0]
    assert row["outcome"] == "invalid"
    assert row["error"] != ""
    assert doc["census_state"] == "no_schema"


def test_oversize_pack_is_invalid_under_the_imported_bound(
        tmp_path, monkeypatch):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Big", locator)
    monkeypatch.setattr(hub_sc, "MAX_BROWSE_BYTES", 8)
    doc = hub_sc.schema_census_document(store.list_for_owner("u1"))
    row = doc["entries"][0]
    assert row["outcome"] == "invalid"
    assert row["error"] == "pack file too large to schema-census"
    assert doc["max_browse_bytes"] == 8


def test_largest_schema_entry_and_tie_keeps_store_order(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    per_entry, _expected = _expected_estate(entries)
    doc = hub_sc.schema_census_document(store.list_for_owner("u1"))
    distincts = [len(set(shapes)) for shapes in per_entry]
    want = entries[distincts.index(max(distincts))]
    largest = doc["largest_schema_entry"]
    assert largest["id"] == want.id
    assert largest["distinct_shape_count"] == max(distincts)
    store2 = make_store(tmp_path / "second")
    a, _pa = _lorebook_file(tmp_path, "a.json")
    raw = open(a, "rb").read()
    bpath = tmp_path / "b.json"
    bpath.write_bytes(raw)
    first = _register(store2, "lorebook_pack", "First", a)
    _register(store2, "lorebook_pack", "Second", str(bpath))
    doc2 = hub_sc.schema_census_document(store2.list_for_owner("u1"))
    rows = doc2["entries"]
    assert rows[0]["distinct_shape_count"] == rows[1]["distinct_shape_count"]
    assert doc2["largest_schema_entry"]["id"] == first.id


# ------------------------------------------------------------ distinctness fence


def test_distinctness_fence_against_banked_censuses(tmp_path):
    store = make_store(tmp_path)
    _full_estate(tmp_path, store)
    estate = store.list_for_owner("u1")
    doc = hub_sc.schema_census_document(estate)
    own_blob = json.dumps(doc)
    for banned in ("by_browse_state", "by_checksum_match",
                   "browse_state", "checksum_match",
                   "string_value_count", "string_char_count",
                   "total_string_chars", "by_kind_content",
                   "largest_content_entry", "matched_by",
                   "duplicate_groups", "duplicate_entry_count",
                   "distinct_content_count",
                   "unidentified_entry_count", "node_count",
                   "key_count", "max_depth", "deepest_entry",
                   "by_node_type", "file_bytes", "by_size_bucket",
                   "widest", "total_breadth", "by_kind_breadth",
                   "distinct_value_count", "repeated_value_count",
                   "shared_value_count", "by_kind_distinct",
                   "largest_distinct_entry"):
        assert banned not in own_blob, banned
    for row in doc["entries"]:
        assert "error" in row and "outcome" in row
    # And the banked censuses carry no schema axis.
    p196 = hub_sh.content_shape_census_document(estate)
    assert "distinct_shape_count" not in json.dumps(p196)
    dup = hub_dup.duplicate_census_document(estate)
    assert "shared_shape_count" not in json.dumps(dup)
    p189 = hub_census.census_document(estate)
    assert "total_distinct_shapes" not in json.dumps(p189)


def test_no_names_digests_or_content_anywhere(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "A pack", locator)
    doc = hub_sc.schema_census_document(store.list_for_owner("u1"))
    blob = json.dumps(doc)
    # No payload value.
    assert "The Zephyr Quill writes storms." not in blob
    # No payload key name that is not also registry data:
    # the lorebook entry record's own field names never
    # appear (they are payload structure, not entry data).
    assert "selective_logic" not in blob
    assert "inclusion_group" not in blob
    # No digest of a payload key-set: the entry record's
    # key-set digest, computed test-side, is absent.
    entry_keys = sorted(_lore_entry("e", "n", "c", []))
    canonical = json.dumps(entry_keys, ensure_ascii=False,
                           separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert digest not in blob
    assert '"excerpt":' not in blob
    assert '"payload":' not in blob


# ------------------------------------------------------------ pure read / scope


def test_census_writes_nothing(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    hub_bytes = (tmp_path / "data" / "hub.json").read_bytes()
    pack_bytes = {e.locator: open(e.locator, "rb").read()
                  for e in entries}
    hub_sc.schema_census_document(store.list_for_owner("u1"))
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
    doc = hub_sc.schema_census_document(store.list_for_owner("u1"))
    assert doc["count"] == 1
    assert doc["entries"][0]["title"] == "Mine"
    # The foreign copy must not make Mine's shapes "shared".
    assert doc["total_shared_shapes"] == 0


def test_http_road_owner_scoped_and_bearer_gated(tmp_path):
    _factory, client = _client(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Mine",
        "locator": locator,
        "content_sha256": pack["manifest"]["content_sha256"]})
    assert created.status_code == 201, created.text
    response = client.get("/api/v1/hub/schema-census")
    assert response.status_code == 200
    doc = response.json()
    assert doc["schema"] == "runmal-p200-hub-schema-census-v1"
    assert doc["count"] == 1
    assert doc["entries"][0]["outcome"] == "parsed"
    assert doc["entries"][0]["distinct_shape_count"] > 0
    bare = TestClient(create_app(_factory))
    assert bare.get("/api/v1/hub/schema-census").status_code == 401


def test_neighbours_migration_head_and_imported_laws(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == MIGRATIONS[-1][0] == "0041"
    assert hub_sc.MAX_BROWSE_BYTES == 16 * 1024 * 1024
    assert hub_sc.MAX_BROWSE_BYTES == hub_browse.MAX_BROWSE_BYTES
    assert hub_sc.OUTCOMES is hub_cc.OUTCOMES
    assert hub_sc.OUTCOME_PARSED == hub_cc.OUTCOME_PARSED
    assert hub_sc.SCHEMA_CENSUS_STATES == frozenset({
        "no_entries", "no_schema", "some_schema", "all_schema"})
