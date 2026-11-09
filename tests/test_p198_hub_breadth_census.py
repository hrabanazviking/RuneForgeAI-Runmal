"""P-198 - Hub breadth census (Part XII, DERIVED).

Pins: the breadth-census document (schema tag,
census_state under the closed BREADTH_CENSUS_STATES
law judged on the parsed axis: no_entries /
no_breadth / some_breadth / all_breadth); the breadth
law (every container measured once: a dict width is
its counted keys with a content_sha256 member
excluded whole, a list width is its length); the
closed BREADTH_BUCKETS law over containers of parsed
rows (edge widths belong to the higher bucket);
per-kind breadth axes summing exactly to the totals;
the widest entry over parsed rows, first in store
order on a tie; the distinctness fence (no P-189
browse/checksum axis, no P-193 volume axis, no P-194
matched axis, no P-195 duplicate axis, no P-196
shape axis and no P-197 byte axis among the census
own fields or rows); the pure-read law; owner
scoping (unit and HTTP); the HTTP road (200 owner,
401 without a bearer); and the neighbours (migration
head stays 0041; the composed laws are P-187, P-188
and P-193 banked ones). No network: fixtures only.
"""

from __future__ import annotations

import json
import os
import shutil

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.hub import browse as hub_browse
from runmal.hub import content_census as hub_cc
from runmal.hub import registry as hub
from runmal.hub import breadth_census as hub_bc
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
    record = store.create("owner-p198", body, now=STAMP)
    pack = scenario_packs.build_pack(record, exported_at=STAMP)
    path = tmp_path / "scenario-pack.json"
    path.write_bytes(scenario_packs.pack_to_bytes(pack))
    return str(path), pack


def _bundle_file(tmp_path, bare=False, name="preset-bundle.json"):
    bundle = preset_bundles.validate_bundle({
        "name": "Hall Bundle",
        "prompts": [{"identifier": "main",
                     "content": "Zephyr bundle text for the hall."}],
        "prompt_order": [{"identifier": "main", "enabled": True}],
    })
    share = preset_bundles.build_share(bundle, exported_at=STAMP)
    path = tmp_path / name
    if bare:
        path.write_text(json.dumps(bundle))
        return str(path), bundle
    path.write_text(json.dumps(share))
    return str(path), share


def _full_estate(tmp_path, store):
    entries = []
    makers = (
        ("lorebook_pack", _lorebook_file),
        ("prompt_pack", _prompt_file),
        ("scenario_pack", _scenario_file),
        ("preset_bundle", _bundle_file))
    for kind, maker in makers:
        locator, pack = maker(tmp_path)
        sha = ""
        if "manifest" in pack:
            sha = pack["manifest"]["content_sha256"]
        entries.append(_register(store, kind, "A pack", locator, sha))
    return entries


def _copy(tmp_path, locator, name):
    target = tmp_path / name
    shutil.copyfile(locator, target)
    return str(target)


def _stat(locator):
    return os.stat(locator).st_size


# ------------------------------------------------------------ the estate view


def _ref_widths(payload):
    """Independent breadth walk for cross-checking the
    module: widths of every container, document order."""
    widths = []

    def walk(node):
        if isinstance(node, dict):
            kept = [v for k, v in node.items()
                    if k != "content_sha256"]
            widths.append(len(kept))
            for v in kept:
                walk(v)
        elif isinstance(node, list):
            widths.append(len(node))
            for item in node:
                walk(item)

    walk(payload)
    return widths


def _ref_stats(payload):
    widths = _ref_widths(payload)
    return widths


def test_empty_estate_is_no_entries_with_zero_filled_axes(tmp_path):
    doc = hub_bc.breadth_census_document([])
    assert doc["schema"] == "runmal-p198-hub-breadth-census-v1"
    assert doc["census_state"] == "no_entries"
    assert doc["census_state"] in hub_bc.BREADTH_CENSUS_STATES
    assert doc["count"] == 0
    assert doc["entries_considered"] == 0
    assert doc["parsed_count"] == 0
    assert doc["coverage_complete"] is True
    assert doc["total_containers"] == 0
    assert doc["total_breadth"] == 0
    assert doc["widest_container_width"] == 0
    assert doc["widest_entry"] is None
    assert doc["by_outcome"] == {
        "invalid": 0, "parsed": 0, "unavailable": 0}
    assert doc["by_kind_breadth"] == {
        kind: {"entries": 0, "parsed": 0, "containers": 0,
               "breadth": 0, "widest_container_width": 0}
        for kind in hub.KIND_FORMATS}
    assert doc["by_breadth_bucket"] == {
        bucket: 0 for bucket in hub_bc.BREADTH_BUCKETS}
    assert doc["list"] == hub.list_document([])
    assert doc["kind_formats"] == hub.KIND_FORMATS
    assert doc["max_browse_bytes"] == hub_browse.MAX_BROWSE_BYTES


def test_breadth_stats_hand_pins_on_literal_payloads():
    stats, widths = hub_bc._breadth_stats(
        {"a": [1, 2, 3], "content_sha256": "deadbeef"})
    assert widths == [1, 3]
    assert stats == {
        "breadth_container_count": 2, "breadth_total": 4,
        "widest_container_width": 3, "widest_object_width": 1,
        "widest_array_width": 3}
    stats, widths = hub_bc._breadth_stats([])
    assert widths == [0]
    assert stats["breadth_container_count"] == 1
    assert stats["breadth_total"] == 0
    assert stats["widest_container_width"] == 0
    stats, widths = hub_bc._breadth_stats([[1, 2], [3]])
    assert widths == [2, 2, 1]
    assert stats["breadth_total"] == 5
    assert stats["widest_object_width"] == 0
    assert stats["widest_array_width"] == 2
    stats, widths = hub_bc._breadth_stats("scalar")
    assert widths == []
    assert stats["breadth_container_count"] == 0
    stats, widths = hub_bc._breadth_stats(
        {"items": [{"content_sha256": "x", "v": 1}]})
    assert widths == [1, 1, 1]
    assert stats["breadth_total"] == 3


def test_bucket_law_edges_belong_to_the_higher_bucket():
    assert hub_bc.container_bucket(0) == "empty"
    assert hub_bc.container_bucket(1) == "narrow"
    assert hub_bc.container_bucket(2) == "narrow"
    assert hub_bc.container_bucket(3) == "medium"
    assert hub_bc.container_bucket(5) == "medium"
    assert hub_bc.container_bucket(6) == "wide"
    assert hub_bc.container_bucket(10) == "wide"
    assert hub_bc.container_bucket(11) == "vast"
    assert hub_bc.container_bucket(500) == "vast"
    assert hub_bc.BREADTH_BUCKETS == frozenset(
        {"empty", "narrow", "medium", "wide", "vast"})


def test_full_estate_all_breadth_and_axes_sum_exactly(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    listed = store.list_for_owner("u1")
    doc = hub_bc.breadth_census_document(listed)
    assert doc["census_state"] == "all_breadth"
    assert doc["count"] == 4
    assert doc["parsed_count"] == 4
    assert doc["coverage_complete"] is True
    exp_containers = 0
    exp_breadth = 0
    exp_widest = 0
    exp_buckets = {b: 0 for b in hub_bc.BREADTH_BUCKETS}
    for row, entry in zip(doc["entries"], listed, strict=True):
        assert row["outcome"] == "parsed"
        raw = open(entry.locator, "rb").read()
        payload, _sha = hub_bc._parse_payload(entry, raw)
        widths = _ref_widths(payload)
        assert row["breadth_container_count"] == len(widths)
        assert row["breadth_total"] == sum(widths)
        assert row["widest_container_width"] == max(widths)
        exp_containers += len(widths)
        exp_breadth += sum(widths)
        exp_widest = max(exp_widest, max(widths))
        for w in widths:
            exp_buckets[hub_bc.container_bucket(w)] += 1
    assert doc["total_containers"] == exp_containers
    assert doc["total_breadth"] == exp_breadth
    assert doc["widest_container_width"] == exp_widest
    assert doc["by_breadth_bucket"] == exp_buckets
    assert sum(doc["by_breadth_bucket"].values()) == exp_containers
    kind_containers = sum(
        a["containers"] for a in doc["by_kind_breadth"].values())
    kind_breadth = sum(
        a["breadth"] for a in doc["by_kind_breadth"].values())
    assert kind_containers == exp_containers
    assert kind_breadth == exp_breadth
    for axis in doc["by_kind_breadth"].values():
        assert axis["entries"] == 1
        assert axis["parsed"] == 1
    assert doc["widest_entry"]["widest_container_width"] == exp_widest


def test_mixed_estate_no_silent_omission(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    _register(store, "lorebook_pack", "Good", locator, sha)
    _register(store, "lorebook_pack", "Ghost",
              str(tmp_path / "ghost.json"))
    _register(store, "lorebook_pack", "Folder", str(tmp_path))
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("this is not a pack at all")
    _register(store, "lorebook_pack", "Corrupt", str(corrupt))
    doc = hub_bc.breadth_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "some_breadth"
    assert doc["count"] == 4
    assert doc["coverage_complete"] is False
    assert doc["by_outcome"] == {
        "invalid": 1, "parsed": 1, "unavailable": 2}
    rows = {row["title"]: row for row in doc["entries"]}
    assert rows["Ghost"]["outcome"] == "unavailable"
    assert rows["Ghost"]["breadth_container_count"] == 0
    assert rows["Folder"]["locator_state"] == "not_a_file"
    assert rows["Corrupt"]["outcome"] == "invalid"
    assert rows["Corrupt"]["error"] != ""
    assert rows["Corrupt"]["breadth_total"] == 0
    good = rows["Good"]
    assert doc["total_containers"] == good["breadth_container_count"]
    assert doc["total_breadth"] == good["breadth_total"]
    assert doc["widest_entry"]["title"] == "Good"


def test_all_missing_estate_is_no_breadth(tmp_path):
    store = make_store(tmp_path)
    _register(store, "prompt_pack", "Ghost",
              str(tmp_path / "ghost.json"))
    doc = hub_bc.breadth_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "no_breadth"
    assert doc["total_containers"] == 0
    assert doc["widest_entry"] is None
    assert doc["coverage_complete"] is False


def test_bare_bundle_parsed_with_empty_sha(tmp_path):
    store = make_store(tmp_path)
    locator, bundle = _bundle_file(tmp_path, bare=True)
    _register(store, "preset_bundle", "Bare", locator)
    doc = hub_bc.breadth_census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "all_breadth"
    row = doc["entries"][0]
    assert row["outcome"] == "parsed"
    assert row["verified_content_sha256"] == ""
    widths = _ref_widths(bundle)
    assert row["breadth_container_count"] == len(widths)
    assert row["widest_object_width"] == len(bundle)


def test_wrong_kind_pack_is_invalid(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    _register(store, "scenario_pack", "Wrong kind", locator)
    doc = hub_bc.breadth_census_document(store.list_for_owner("u1"))
    row = doc["entries"][0]
    assert row["outcome"] == "invalid"
    assert row["breadth_container_count"] == 0
    assert doc["census_state"] == "no_breadth"
    assert doc["total_breadth"] == 0


def test_oversize_is_invalid_with_own_error_text(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    _register(store, "lorebook_pack", "Big", locator, sha)
    monkeypatch.setattr(hub_bc, "MAX_BROWSE_BYTES", 10)
    doc = hub_bc.breadth_census_document(store.list_for_owner("u1"))
    row = doc["entries"][0]
    assert row["outcome"] == "invalid"
    assert row["error"] == "pack file too large to breadth-census"
    assert doc["total_containers"] == 0


def test_widest_entry_names_the_widest_payload(tmp_path):
    store = make_store(tmp_path)
    many = [_lore_entry(f"e{i}", f"Entry {i}", "Text.", ["k"])
            for i in range(6)]
    wide_locator, wide_pack = _lorebook_file(
        tmp_path, name="wide.json", entries=many)
    _register(store, "lorebook_pack", "Wide Book", wide_locator,
              wide_pack["manifest"]["content_sha256"])
    bare_locator, bundle = _bundle_file(tmp_path, bare=True)
    _register(store, "preset_bundle", "Bare", bare_locator)
    doc = hub_bc.breadth_census_document(store.list_for_owner("u1"))
    rows = {row["title"]: row for row in doc["entries"]}
    assert rows["Wide Book"]["widest_array_width"] == 6
    assert (doc["widest_entry"]["widest_container_width"]
            == max(rows["Wide Book"]["widest_container_width"],
                   rows["Bare"]["widest_container_width"]))
    assert doc["widest_entry"]["title"] in ("Wide Book", "Bare")
    assert (doc["widest_container_width"]
            == doc["widest_entry"]["widest_container_width"])


def test_widest_tie_keeps_store_order(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    first = _register(store, "lorebook_pack", "First", locator, sha)
    _register(store, "lorebook_pack", "Second",
              _copy(tmp_path, locator, "copy.json"), sha)
    doc = hub_bc.breadth_census_document(store.list_for_owner("u1"))
    assert doc["widest_entry"]["id"] == first.id


def test_distinctness_fence_no_banked_axis_anywhere(tmp_path):
    store = make_store(tmp_path)
    _full_estate(tmp_path, store)
    doc = hub_bc.breadth_census_document(store.list_for_owner("u1"))
    own = set(doc) - {"list"}
    for banned in (
            "by_browse_state", "by_checksum_match",
            "total_string_values", "total_string_chars",
            "by_kind_content", "largest_content_entry",
            "duplicate_groups", "duplicate_group_count",
            "duplicate_entry_count", "distinct_content_count",
            "by_kind_shape", "by_node_type", "total_nodes",
            "total_keys", "max_depth", "deepest_entry",
            "by_kind_size", "by_size_bucket", "total_file_bytes",
            "total_verified_bytes", "largest_file_entry",
            "smallest_file_entry", "file_bytes"):
        assert banned not in own
    for row in doc["entries"]:
        for banned in (
                "browse_state", "checksum_match",
                "string_value_count", "string_char_count",
                "object_count", "array_count", "node_count",
                "key_count", "max_depth", "file_bytes"):
            assert banned not in row


def test_no_content_text_anywhere_in_document(tmp_path):
    store = make_store(tmp_path)
    _full_estate(tmp_path, store)
    doc = hub_bc.breadth_census_document(store.list_for_owner("u1"))
    blob = json.dumps(doc)
    assert "Zephyr Quill writes storms" not in blob
    assert "Zephyr prompt text" not in blob
    assert "Zephyr bundle text" not in blob
    assert "Zephyr ferry" not in blob


def test_pure_read_registry_and_pack_bytes_unchanged(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    _register(store, "lorebook_pack", "A", locator, sha)
    index_bytes = (tmp_path / "data" / "hub.json").read_bytes()
    pack_bytes = open(locator, "rb").read()
    hub_bc.breadth_census_document(store.list_for_owner("u1"))
    assert (tmp_path / "data" / "hub.json").read_bytes() == index_bytes
    assert open(locator, "rb").read() == pack_bytes


def test_owner_scoping_foreign_entries_never_counted(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    _register(store, "lorebook_pack", "Mine", locator, sha, owner="u1")
    _register(store, "lorebook_pack", "Theirs",
              _copy(tmp_path, locator, "copy.json"), sha, owner="u2")
    doc = hub_bc.breadth_census_document(store.list_for_owner("u1"))
    assert doc["count"] == 1
    assert doc["total_containers"] > 0


def test_neighbours_laws_are_the_banked_ones():
    assert hub_bc.OUTCOMES is hub_cc.OUTCOMES
    assert hub_bc.OUTCOME_PARSED == hub_cc.OUTCOME_PARSED
    assert hub_bc.MAX_BROWSE_BYTES == hub_browse.MAX_BROWSE_BYTES
    assert hub.HUB_KINDS == frozenset({
        "lorebook_pack", "prompt_pack",
        "preset_bundle", "scenario_pack"})
    assert hub_bc.BREADTH_CENSUS_STATES == frozenset(
        {"no_entries", "no_breadth", "some_breadth", "all_breadth"})
    assert MIGRATIONS[-1][0] == "0042"


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "mig.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"


# ------------------------------------------------------------ HTTP


def test_http_breadth_census_owner_reads_200(tmp_path):
    _factory, client = _client(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    sha = pack["manifest"]["content_sha256"]
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "A",
        "locator": locator, "content_sha256": sha})
    assert created.status_code == 201, created.text
    response = client.get("/api/v1/hub/breadth-census")
    assert response.status_code == 200
    doc = response.json()
    assert doc["schema"] == "runmal-p198-hub-breadth-census-v1"
    assert doc["census_state"] == "all_breadth"
    assert doc["total_containers"] > 0
    assert doc["widest_entry"]["title"] == "A"


def test_http_breadth_census_skips_are_data_at_200(tmp_path):
    _factory, client = _client(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "prompt_pack", "title": "Ghost",
        "locator": str(tmp_path / "ghost.json")})
    assert created.status_code == 201, created.text
    response = client.get("/api/v1/hub/breadth-census")
    assert response.status_code == 200
    doc = response.json()
    assert doc["census_state"] == "no_breadth"
    assert doc["entries"][0]["breadth_container_count"] == 0
    assert doc["coverage_complete"] is False


def test_http_breadth_census_requires_bearer(tmp_path):
    _factory, client = _client(tmp_path)
    client.headers.pop("Authorization")
    response = client.get("/api/v1/hub/breadth-census")
    assert response.status_code == 401
