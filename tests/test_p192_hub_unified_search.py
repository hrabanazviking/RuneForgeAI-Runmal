"""P-192 - Unified hub search (Part XII, DERIVED).

Pins: the unified-search document (schema tag,
search_state under the closed SEARCH_STATES law);
composition verbatim (P-190's metadata search and
P-191's content search embedded WHOLE and equal to
direct calls over the same inputs; no second search,
parse or counting law); the union law (by entry id, in
store order, matched_by under the closed MATCHED_BY
law - metadata / content / both - with the metadata
side's matched_fields verbatim or empty and the
content side's occurrences / excerpt / verified
checksum verbatim or null, never invented); cap
honesty composed (either source's truncation or the
union's own cap names a truncated answer; both source
totals carried verbatim); coverage honesty carried
from P-191 (skips named, coverage_complete as data, a
skipped entry can still metadata-match with null
content facts); the query and kind-filter laws (blank
or non-string refused by this slice's own error,
unknown kind refused, kind narrows both sources);
the pure-read law (registry and pack bytes unchanged);
owner scoping (unit and HTTP); the HTTP road (200 for
the owner, 401 without a bearer, 422 for a blank query
or an unknown kind, skips as data at 200); and the
neighbours (migration head stays 0041; the caps are
the banked searches' own). No network: fixtures only.
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
from runmal.hub import content_search as hub_cs
from runmal.hub import registry as hub
from runmal.hub import search as hub_search
from runmal.hub import unified_search as hub_unified
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


def _register(store, kind, title, locator, sha="", note="", owner="u1"):
    return hub.register_entry(
        store, owner_id=owner, kind=kind, title=title,
        locator=locator, content_sha256=sha, note=note)


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


def _lorebook_file(tmp_path, name="lorebook-pack.json",
                   content="The Zephyr Quill writes storms."):
    entries = [_lore_entry("e1", "Plain Entry", content, ["quill"])]
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


def _prompt_file(tmp_path, name="prompt-pack.json",
                 text="Zephyr prompt text for the hall."):
    item = {
        "kind": "preset", "name": "Hall Preset",
        "payload": {
            "name": "Hall Preset",
            "params": {"temperature": 0.7},
            "template_ref": "", "source_format": "st-chat",
            "raw": {"temperature": 0.7},
            "prompts": [{"identifier": "main", "content": text}],
            "prompt_order": [{"identifier": "main", "enabled": True}],
        },
    }
    pack = prompt_packs.build_pack("Workshop", [item], exported_at=STAMP)
    path = tmp_path / name
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
    record = store.create("owner-p192", body, now=STAMP)
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


# ------------------------------------------------------------ document basics


def test_empty_estate_is_no_matches_with_full_coverage(tmp_path):
    doc = hub_unified.unified_search_document([], "zephyr")
    assert doc["schema"] == "runmal-p192-hub-unified-search-v1"
    assert doc["search_state"] == "no_matches"
    assert doc["query"] == "zephyr"
    assert doc["kind"] is None
    assert doc["matches"] == []
    assert doc["match_count"] == 0
    assert doc["total_matches"] == 0
    assert doc["truncated"] is False
    assert doc["coverage_complete"] is True
    assert doc["metadata_match_count"] == 0
    assert doc["content_match_count"] == 0
    assert doc["both_count"] == 0
    assert doc["metadata_total_matches"] == 0
    assert doc["content_total_matches"] == 0
    assert doc["entries_considered"] == 0
    assert doc["entries_searched"] == 0
    assert doc["skipped_entries"] == []
    assert doc["metadata_search"] == hub_search.search_document([], "zephyr")
    assert doc["content_search"] == hub_cs.content_search_document([], "zephyr")
    assert doc["list"] == hub.list_document([])
    assert doc["kind_formats"] == hub.KIND_FORMATS


def test_no_match_anywhere_is_no_matches(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Amber Archive", locator)
    doc = hub_unified.unified_search_document(
        store.list_for_owner("u1"), "obsidian")
    assert doc["search_state"] == "no_matches"
    assert doc["total_matches"] == 0
    assert doc["entries_searched"] == 1
    assert doc["coverage_complete"] is True


# ------------------------------------------------------------ the union law


def test_metadata_only_match_carries_no_content_facts(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(
        tmp_path, content="Plain sailing words.")
    entry = _register(store, "lorebook_pack", "Amber Archive", locator)
    doc = hub_unified.unified_search_document(
        store.list_for_owner("u1"), "amber")
    assert doc["search_state"] == "matches"
    assert doc["total_matches"] == 1
    row = doc["matches"][0]
    assert row["id"] == entry.id
    assert row["matched_by"] == "metadata"
    assert row["metadata_match"] is True
    assert row["content_match"] is False
    assert row["matched_fields"] == ["title"]
    assert row["occurrences"] is None
    assert row["excerpt"] is None
    assert row["verified_content_sha256"] is None
    assert doc["metadata_match_count"] == 1
    assert doc["content_match_count"] == 0
    assert doc["both_count"] == 0
    assert doc["metadata_total_matches"] == 1
    assert doc["content_total_matches"] == 0
    assert doc["entries_searched"] == 1
    assert doc["coverage_complete"] is True
    assert doc["list"]["count"] == doc["match_count"] == 1


def test_content_only_match_carries_content_facts_verbatim(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    entry = _register(store, "lorebook_pack", "Plain Title", locator)
    doc = hub_unified.unified_search_document(
        store.list_for_owner("u1"), "zephyr")
    assert doc["total_matches"] == 1
    row = doc["matches"][0]
    assert row["id"] == entry.id
    assert row["matched_by"] == "content"
    assert row["metadata_match"] is False
    assert row["content_match"] is True
    assert row["matched_fields"] == []
    assert row["occurrences"] == 1
    assert "Zephyr" in row["excerpt"]
    assert row["verified_content_sha256"] == pack["manifest"]["content_sha256"]
    content_row = doc["content_search"]["matches"][0]
    assert row["occurrences"] == content_row["occurrences"]
    assert row["excerpt"] == content_row["excerpt"]
    assert row["verified_content_sha256"] == (
        content_row["verified_content_sha256"])
    assert doc["metadata_match_count"] == 0
    assert doc["content_match_count"] == 1
    assert doc["both_count"] == 0


def test_content_only_match_for_each_remaining_kind(tmp_path):
    store = make_store(tmp_path)
    p_loc, p_pack = _prompt_file(tmp_path)
    s_loc, s_pack = _scenario_file(tmp_path)
    b_loc, b_share = _bundle_file(tmp_path)
    _register(store, "prompt_pack", "Plain Prompt", p_loc)
    _register(store, "scenario_pack", "Plain Scenario", s_loc)
    _register(store, "preset_bundle", "Plain Bundle", b_loc)
    doc = hub_unified.unified_search_document(
        store.list_for_owner("u1"), "zephyr")
    assert doc["total_matches"] == 3
    assert doc["content_match_count"] == 3
    by_kind = {row["kind"]: row for row in doc["matches"]}
    assert by_kind["prompt_pack"]["matched_by"] == "content"
    assert by_kind["prompt_pack"]["occurrences"] == 1
    assert by_kind["prompt_pack"]["verified_content_sha256"] == (
        p_pack["manifest"]["content_sha256"])
    assert by_kind["scenario_pack"]["occurrences"] == 1
    assert by_kind["scenario_pack"]["verified_content_sha256"] == (
        s_pack["manifest"]["content_sha256"])
    assert by_kind["preset_bundle"]["occurrences"] == 1
    assert by_kind["preset_bundle"]["verified_content_sha256"] == (
        b_share["manifest"]["content_sha256"])


def test_bare_bundle_content_match_verified_is_empty_verbatim(tmp_path):
    store = make_store(tmp_path)
    locator, _bundle = _bundle_file(tmp_path, bare=True)
    _register(store, "preset_bundle", "Plain Bundle", locator)
    doc = hub_unified.unified_search_document(
        store.list_for_owner("u1"), "zephyr")
    row = doc["matches"][0]
    assert row["matched_by"] == "content"
    assert row["verified_content_sha256"] == ""


def test_both_match_carries_both_sides_verbatim(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _scenario_file(tmp_path)
    entry = _register(store, "scenario_pack", "Harbour Lights Pack", locator)
    doc = hub_unified.unified_search_document(
        store.list_for_owner("u1"), "harbour")
    assert doc["total_matches"] == 1
    row = doc["matches"][0]
    assert row["id"] == entry.id
    assert row["matched_by"] == "both"
    assert row["metadata_match"] is True
    assert row["content_match"] is True
    assert "title" in row["matched_fields"]
    assert row["occurrences"] >= 1
    assert row["verified_content_sha256"]
    assert doc["both_count"] == 1
    assert doc["metadata_match_count"] == 1
    assert doc["content_match_count"] == 1


def test_union_keeps_store_order_across_sides(tmp_path):
    store = make_store(tmp_path)
    a_loc, _p1 = _lorebook_file(
        tmp_path, name="a.json", content="Plain words only.")
    b_loc, _p2 = _prompt_file(tmp_path, text="Mist prompt text.")
    first = _register(store, "lorebook_pack", "Mist Archive", a_loc)
    second = _register(store, "prompt_pack", "Plain Prompt", b_loc)
    doc = hub_unified.unified_search_document(
        store.list_for_owner("u1"), "mist")
    assert [row["id"] for row in doc["matches"]] == [first.id, second.id]
    assert [row["matched_by"] for row in doc["matches"]] == [
        "metadata", "content"]
    assert [row["id"] for row in doc["list"]["entries"]] == [
        first.id, second.id]


def test_count_axes_over_a_mixed_estate(tmp_path):
    store = make_store(tmp_path)
    s_loc, _sp = _scenario_file(tmp_path)
    l_loc, _lp = _lorebook_file(
        tmp_path, name="l.json", content="Calm water.")
    p_loc, _pp = _prompt_file(tmp_path, text="harbour bells ring.")
    _register(store, "scenario_pack", "Harbour Lights Pack", s_loc)
    _register(store, "lorebook_pack", "Harbour Lore", l_loc)
    _register(store, "prompt_pack", "Plain Prompt", p_loc)
    doc = hub_unified.unified_search_document(
        store.list_for_owner("u1"), "harbour")
    assert doc["total_matches"] == 3
    assert doc["match_count"] == 3
    assert doc["metadata_match_count"] == 2
    assert doc["content_match_count"] == 2
    assert doc["both_count"] == 1
    assert doc["list"]["count"] == 3


def test_casefolded_literal_on_both_sides(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Amber Archive", locator)
    entries = store.list_for_owner("u1")
    content_doc = hub_unified.unified_search_document(entries, "ZEPHYR")
    assert content_doc["matches"][0]["matched_by"] == "content"
    meta_doc = hub_unified.unified_search_document(entries, "AMBER")
    assert meta_doc["matches"][0]["matched_by"] == "metadata"


def test_no_fuzzy_or_regex_matching_on_either_side(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Amber Archive", locator)
    entries = store.list_for_owner("u1")
    for query in ("zeph.r", "zephyrr", "amb.r"):
        doc = hub_unified.unified_search_document(entries, query)
        assert doc["total_matches"] == 0, query


def test_embedded_documents_equal_direct_calls(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Amber Archive", locator)
    _register(store, "prompt_pack", "Gone", "/no/such.json")
    entries = store.list_for_owner("u1")
    doc = hub_unified.unified_search_document(entries, "zephyr")
    assert doc["metadata_search"] == hub_search.search_document(
        entries, "zephyr")
    assert doc["content_search"] == hub_cs.content_search_document(
        entries, "zephyr")
    assert doc["entries_considered"] == doc["content_search"]["entries_considered"]
    assert doc["skipped_entries"] == doc["content_search"]["skipped_entries"]


# ------------------------------------------------------------ coverage honesty


def test_skipped_entry_can_still_metadata_match(tmp_path):
    store = make_store(tmp_path)
    entry = _register(
        store, "lorebook_pack", "Amber Ghost", "/no/such/pack.json")
    doc = hub_unified.unified_search_document(
        store.list_for_owner("u1"), "amber")
    assert doc["total_matches"] == 1
    row = doc["matches"][0]
    assert row["id"] == entry.id
    assert row["matched_by"] == "metadata"
    assert row["occurrences"] is None
    assert row["verified_content_sha256"] is None
    assert doc["entries_considered"] == 1
    assert doc["entries_searched"] == 0
    assert doc["skipped_entries"][0]["id"] == entry.id
    assert doc["skipped_entries"][0]["outcome"] == "unavailable"
    assert doc["coverage_complete"] is False
    assert doc["truncated"] is False
    assert doc["search_state"] == "matches"


def test_corrupt_pack_metadata_match_and_invalid_skip(tmp_path):
    store = make_store(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"not a pack at all")
    _register(store, "lorebook_pack", "Amber Broken", str(bad))
    doc = hub_unified.unified_search_document(
        store.list_for_owner("u1"), "amber")
    assert doc["matches"][0]["matched_by"] == "metadata"
    assert doc["skipped_entries"][0]["outcome"] == "invalid"
    assert doc["skipped_entries"][0]["error"] != ""
    assert doc["coverage_complete"] is False


# ------------------------------------------------------------ query + kind law


def test_query_refusals_are_this_slices_own_error(tmp_path):
    for bad in ("", "   ", None, 42):
        with pytest.raises(hub_unified.HubUnifiedSearchError):
            hub_unified.unified_search_document([], bad)


def test_kind_filter_narrows_both_sources(tmp_path):
    store = make_store(tmp_path)
    l_loc, _lp = _lorebook_file(tmp_path)
    p_loc, _pp = _prompt_file(tmp_path)
    _register(store, "lorebook_pack", "Plain Lore", l_loc)
    _register(store, "prompt_pack", "Plain Prompt", p_loc)
    entries = store.list_for_owner("u1")
    doc = hub_unified.unified_search_document(
        entries, "zephyr", kind="lorebook_pack")
    assert doc["kind"] == "lorebook_pack"
    assert doc["entries_considered"] == 1
    assert doc["total_matches"] == 1
    assert doc["matches"][0]["kind"] == "lorebook_pack"
    meta = hub_unified.unified_search_document(
        entries, "plain", kind="prompt_pack")
    assert meta["total_matches"] == 1
    assert meta["matches"][0]["kind"] == "prompt_pack"
    with pytest.raises(hub_unified.HubUnifiedSearchError):
        hub_unified.unified_search_document(entries, "zephyr", kind="nope")


# ------------------------------------------------------------ cap honesty


def test_source_truncation_names_the_unified_answer(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    for num, title in enumerate(("Amber One", "Amber Two", "Amber Three")):
        _register(store, "lorebook_pack", title, f"/no/such-{num}.json")
    monkeypatch.setattr(hub_search, "MAX_MATCHES", 2)
    monkeypatch.setattr(hub_cs, "MAX_MATCHES", 2)
    doc = hub_unified.unified_search_document(
        store.list_for_owner("u1"), "amber")
    assert doc["metadata_total_matches"] == 3
    assert doc["content_total_matches"] == 0
    assert doc["total_matches"] == 2
    assert doc["match_count"] == 2
    assert doc["truncated"] is True
    assert doc["search_state"] == "matches_truncated"
    assert doc["list"]["count"] == 2
    assert doc["coverage_complete"] is False


def test_union_cap_names_the_unified_answer(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    a_loc, _p1 = _lorebook_file(
        tmp_path, name="a.json", content="Plain words only.")
    b_loc, _p2 = _prompt_file(tmp_path, text="Mist prompt text.")
    _register(store, "lorebook_pack", "Mist Archive", a_loc)
    _register(store, "prompt_pack", "Plain Prompt", b_loc)
    monkeypatch.setattr(hub_unified, "MAX_MATCHES", 1)
    doc = hub_unified.unified_search_document(
        store.list_for_owner("u1"), "mist")
    assert doc["total_matches"] == 2
    assert doc["match_count"] == 1
    assert doc["truncated"] is True
    assert doc["search_state"] == "matches_truncated"
    assert doc["list"]["count"] == 1
    assert doc["coverage_complete"] is False


# ------------------------------------------------------------ pure read + scoping


def test_unified_search_writes_nothing(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Amber Archive", locator)
    index_path = tmp_path / "data" / "hub.json"
    before_index = index_path.read_bytes()
    before_pack = (tmp_path / "lorebook-pack.json").read_bytes()
    hub_unified.unified_search_document(store.list_for_owner("u1"), "amber")
    hub_unified.unified_search_document(store.list_for_owner("u1"), "zephyr")
    assert index_path.read_bytes() == before_index
    assert (tmp_path / "lorebook-pack.json").read_bytes() == before_pack


def test_foreign_entries_are_never_in_the_union(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Amber Foreign", locator, owner="u2")
    _register(store, "prompt_pack", "Amber Gone", "/no/such.json", owner="u2")
    doc = hub_unified.unified_search_document(
        store.list_for_owner("u1"), "amber")
    assert doc["entries_considered"] == 0
    assert doc["total_matches"] == 0
    assert doc["skipped_entries"] == []
    assert doc["metadata_search"]["total_matches"] == 0
    assert doc["content_search"]["total_matches"] == 0


# ------------------------------------------------------------ HTTP


def test_http_unified_search_owner_and_results(tmp_path):
    _factory, client = _client(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Plain Title",
        "locator": locator})
    assert created.status_code == 201, created.text
    got = client.get("/api/v1/hub/unified-search", params={"q": "zephyr"})
    assert got.status_code == 200
    body = got.json()
    assert body["schema"] == "runmal-p192-hub-unified-search-v1"
    assert body["total_matches"] == 1
    assert body["matches"][0]["matched_by"] == "content"
    assert body["matches"][0]["occurrences"] == 1
    meta = client.get("/api/v1/hub/unified-search", params={"q": "title"})
    assert meta.status_code == 200
    assert meta.json()["matches"][0]["matched_by"] == "metadata"


def test_http_skips_are_data_at_200_and_refusals_are_422(tmp_path):
    _factory, client = _client(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Gone",
        "locator": "/no/such/pack.json"})
    assert created.status_code == 201, created.text
    got = client.get("/api/v1/hub/unified-search", params={"q": "gone"})
    assert got.status_code == 200
    body = got.json()
    assert body["matches"][0]["matched_by"] == "metadata"
    assert body["coverage_complete"] is False
    assert body["skipped_entries"][0]["outcome"] == "unavailable"
    blank = client.get("/api/v1/hub/unified-search", params={"q": "  "})
    assert blank.status_code == 422
    missing = client.get("/api/v1/hub/unified-search")
    assert missing.status_code == 422
    bad_kind = client.get("/api/v1/hub/unified-search",
                          params={"q": "gone", "kind": "nope"})
    assert bad_kind.status_code == 422


def test_http_unified_search_requires_bearer(tmp_path):
    factory, _client_used = _client(tmp_path)
    bare = TestClient(create_app(factory))
    got = bare.get("/api/v1/hub/unified-search", params={"q": "zephyr"})
    assert got.status_code == 401


# ------------------------------------------------------------ neighbours


def test_migration_head_stays_0041_and_laws_are_the_banked_ones(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS
    make_factory(tmp_path)
    assert current_revision(tmp_path / "test.db") == "0042"
    assert hub_unified.MATCHED_BY == {"metadata", "content", "both"}
    assert hub_unified.SEARCH_STATES == {
        "no_matches", "matches", "matches_truncated"}
    assert hub_unified.MAX_MATCHES == hub_search.MAX_MATCHES
    assert hub_unified.MAX_MATCHES == hub_cs.MAX_MATCHES == 100
