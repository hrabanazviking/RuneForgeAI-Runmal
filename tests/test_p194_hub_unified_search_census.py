"""P-194 - Hub unified search census (Part XII, DERIVED).

Pins: the census document (schema tag, census_state
under the closed CENSUS_STATES law judged on the
RETURNED matches' sides); composition verbatim (P-192's
unified search composed verbatim and embedded WHOLE,
equal to a direct call; the pure aggregator over a
direct document equals the composing wrapper); the
returned axis (by_matched_by zero-filled under
MATCHED_BY and summing exactly to match_count, by_kind
under HUB_KINDS, by_matched_field under SEARCH_FIELDS
summing fields not rows, total_occurrences with no
content fact invented for a metadata-only row, and
most_occurrences with the store-order tie law); the
source axis (P-192's full-union counts and both source
totals carried verbatim beside the returned sums, the
two truths differing exactly when capped); cap honesty
(a source truncation and the union's own cap both
census as capped, the state judged on returned rows
only); coverage honesty carried from P-191 (skips
counted by outcome, a skipped entry can still be a
returned metadata match, the considered = searched +
skipped invariant); the query and kind laws (P-192's
own refusal propagates unchanged); distinctness (no
P-189 browse / checksum axis and no P-193 string-volume
axis among the census's own fields); the pure-read law;
owner scoping (unit and HTTP); the HTTP road (200 for
the owner, 401 without a bearer, 422 for a blank query
or an unknown kind, skips as data at 200); and the
neighbours (migration head stays 0041; the censused
laws are the banked ones). No network: fixtures only.
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
from runmal.hub import unified_search_census as hub_usc
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
    record = store.create("owner-p194", body, now=STAMP)
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


def test_empty_estate_is_no_matches_zero_filled(tmp_path):
    doc = hub_usc.unified_search_census_document([], "zephyr")
    assert doc["schema"] == "runmal-p194-hub-unified-search-census-v1"
    assert doc["census_state"] == "no_matches"
    assert doc["query"] == "zephyr"
    assert doc["kind"] is None
    assert doc["match_count"] == 0
    assert doc["by_matched_by"] == {
        "both": 0, "content": 0, "metadata": 0}
    assert doc["by_kind"] == {
        "lorebook_pack": 0, "preset_bundle": 0,
        "prompt_pack": 0, "scenario_pack": 0}
    assert doc["by_matched_field"] == {
        "title": 0, "locator": 0, "note": 0, "kind": 0, "format": 0}
    assert doc["total_occurrences"] == 0
    assert doc["most_occurrences"] is None
    assert doc["total_matches"] == 0
    assert doc["source_metadata_match_count"] == 0
    assert doc["source_content_match_count"] == 0
    assert doc["source_both_count"] == 0
    assert doc["metadata_total_matches"] == 0
    assert doc["content_total_matches"] == 0
    assert doc["entries_considered"] == 0
    assert doc["entries_searched"] == 0
    assert doc["skipped_count"] == 0
    assert doc["by_skip_outcome"] == {"invalid": 0, "unavailable": 0}
    assert doc["truncated"] is False
    assert doc["coverage_complete"] is True
    assert doc["unified_search"] == hub_unified.unified_search_document(
        [], "zephyr")
    assert doc["kind_formats"] == hub.KIND_FORMATS


def test_no_match_estate_is_no_matches_with_coverage(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Amber Archive", locator)
    doc = hub_usc.unified_search_census_document(
        store.list_for_owner("u1"), "obsidian")
    assert doc["census_state"] == "no_matches"
    assert doc["match_count"] == 0
    assert doc["entries_searched"] == 1
    assert doc["skipped_count"] == 0
    assert doc["coverage_complete"] is True
    assert doc["most_occurrences"] is None


def test_aggregator_over_direct_document_equals_wrapper(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Amber Archive", locator)
    _register(store, "prompt_pack", "Gone", "/no/such.json")
    entries = store.list_for_owner("u1")
    wrapped = hub_usc.unified_search_census_document(entries, "zephyr")
    direct = hub_unified.unified_search_document(entries, "zephyr")
    assert wrapped["unified_search"] == direct
    assert hub_usc.build_unified_search_census(direct) == wrapped


# ------------------------------------------------------------ the returned axis


def test_metadata_only_census_invents_no_content_facts(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(
        tmp_path, content="Plain sailing words.")
    _register(store, "lorebook_pack", "Amber Archive", locator)
    doc = hub_usc.unified_search_census_document(
        store.list_for_owner("u1"), "amber")
    assert doc["census_state"] == "metadata_only"
    assert doc["match_count"] == 1
    assert doc["by_matched_by"] == {
        "both": 0, "content": 0, "metadata": 1}
    assert doc["by_kind"]["lorebook_pack"] == 1
    assert doc["by_matched_field"]["title"] == 1
    assert doc["total_occurrences"] == 0
    assert doc["most_occurrences"] is None
    assert doc["source_metadata_match_count"] == 1
    assert doc["source_content_match_count"] == 0
    assert doc["source_both_count"] == 0
    assert doc["total_matches"] == 1
    assert doc["coverage_complete"] is True


def test_content_only_census_sums_occurrences(tmp_path):
    store = make_store(tmp_path)
    heavy_loc, _p1 = _lorebook_file(
        tmp_path, name="heavy.json",
        content="Zephyr one and Zephyr two and Zephyr three.")
    light_loc, _p2 = _prompt_file(tmp_path, text="Zephyr prompt text.")
    heavy = _register(store, "lorebook_pack", "Plain Lore", heavy_loc)
    _register(store, "prompt_pack", "Plain Prompt", light_loc)
    doc = hub_usc.unified_search_census_document(
        store.list_for_owner("u1"), "zephyr")
    assert doc["census_state"] == "content_only"
    assert doc["match_count"] == 2
    assert doc["by_matched_by"] == {
        "both": 0, "content": 2, "metadata": 0}
    assert doc["by_kind"]["lorebook_pack"] == 1
    assert doc["by_kind"]["prompt_pack"] == 1
    assert doc["by_matched_field"] == {
        "title": 0, "locator": 0, "note": 0, "kind": 0, "format": 0}
    assert doc["total_occurrences"] == 4
    assert doc["most_occurrences"] == {
        "id": heavy.id, "title": "Plain Lore",
        "kind": "lorebook_pack", "occurrences": 3}
    assert doc["source_content_match_count"] == 2
    assert doc["content_total_matches"] == 2


def test_mixed_estate_axes_are_exact(tmp_path):
    store = make_store(tmp_path)
    s_loc, _sp = _scenario_file(tmp_path)
    l_loc, _lp = _lorebook_file(
        tmp_path, name="l.json", content="Calm water.")
    p_loc, _pp = _prompt_file(tmp_path, text="harbour bells ring.")
    _register(store, "scenario_pack", "Harbour Lights Pack", s_loc)
    _register(store, "lorebook_pack", "Harbour Lore", l_loc)
    _register(store, "prompt_pack", "Plain Prompt", p_loc)
    doc = hub_usc.unified_search_census_document(
        store.list_for_owner("u1"), "harbour")
    assert doc["census_state"] == "mixed"
    assert doc["match_count"] == 3
    assert doc["by_matched_by"] == {
        "both": 1, "content": 1, "metadata": 1}
    assert sum(doc["by_matched_by"].values()) == doc["match_count"]
    assert doc["by_kind"] == {
        "lorebook_pack": 1, "preset_bundle": 0,
        "prompt_pack": 1, "scenario_pack": 1}
    assert doc["by_matched_field"]["title"] == 2
    assert sum(doc["by_matched_field"].values()) == 2
    assert doc["total_occurrences"] == 4
    assert doc["most_occurrences"]["kind"] == "scenario_pack"
    assert doc["most_occurrences"]["occurrences"] == 3
    assert doc["source_metadata_match_count"] == 2
    assert doc["source_content_match_count"] == 2
    assert doc["source_both_count"] == 1
    assert doc["total_matches"] == 3
    assert doc["metadata_total_matches"] == 2
    assert doc["content_total_matches"] == 2
    assert doc["entries_considered"] == 3
    assert doc["entries_searched"] == 3
    assert doc["coverage_complete"] is True


def test_most_occurrences_tie_keeps_returned_order(tmp_path):
    store = make_store(tmp_path)
    a_loc, _p1 = _lorebook_file(
        tmp_path, name="a.json", content="Zephyr and Zephyr.")
    b_loc, _p2 = _prompt_file(
        tmp_path, text="Zephyr plus Zephyr prompt.")
    first = _register(store, "lorebook_pack", "Plain Lore", a_loc)
    _register(store, "prompt_pack", "Plain Prompt", b_loc)
    doc = hub_usc.unified_search_census_document(
        store.list_for_owner("u1"), "zephyr")
    assert doc["total_occurrences"] == 4
    assert doc["most_occurrences"]["id"] == first.id
    assert doc["most_occurrences"]["occurrences"] == 2


# ------------------------------------------------------------ cap honesty


def test_source_truncation_censuses_as_capped(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    for num, title in enumerate(("Amber One", "Amber Two", "Amber Three")):
        _register(store, "lorebook_pack", title, f"/no/such-{num}.json")
    monkeypatch.setattr(hub_search, "MAX_MATCHES", 2)
    monkeypatch.setattr(hub_cs, "MAX_MATCHES", 2)
    doc = hub_usc.unified_search_census_document(
        store.list_for_owner("u1"), "amber")
    assert doc["match_count"] == 2
    assert doc["by_matched_by"] == {
        "both": 0, "content": 0, "metadata": 2}
    assert doc["census_state"] == "metadata_only"
    assert doc["total_matches"] == 2
    assert doc["source_metadata_match_count"] == 2
    assert doc["metadata_total_matches"] == 3
    assert doc["content_total_matches"] == 0
    assert doc["truncated"] is True
    assert doc["coverage_complete"] is False
    assert doc["skipped_count"] == 3
    assert doc["by_skip_outcome"] == {"invalid": 0, "unavailable": 3}


def test_union_cap_state_judged_on_returned_only(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    a_loc, _p1 = _lorebook_file(
        tmp_path, name="a.json", content="Plain words only.")
    b_loc, _p2 = _prompt_file(tmp_path, text="Mist prompt text.")
    _register(store, "lorebook_pack", "Mist Archive", a_loc)
    _register(store, "prompt_pack", "Plain Prompt", b_loc)
    monkeypatch.setattr(hub_unified, "MAX_MATCHES", 1)
    doc = hub_usc.unified_search_census_document(
        store.list_for_owner("u1"), "mist")
    assert doc["match_count"] == 1
    assert doc["by_matched_by"] == {
        "both": 0, "content": 0, "metadata": 1}
    assert doc["census_state"] == "metadata_only"
    assert doc["total_matches"] == 2
    assert doc["source_metadata_match_count"] == 1
    assert doc["source_content_match_count"] == 1
    assert doc["source_both_count"] == 0
    assert doc["total_occurrences"] == 0
    assert doc["most_occurrences"] is None
    assert doc["truncated"] is True
    assert doc["coverage_complete"] is False


# ------------------------------------------------------------ coverage honesty


def test_skips_counted_by_outcome_and_still_censused(tmp_path):
    store = make_store(tmp_path)
    ghost = _register(
        store, "lorebook_pack", "Amber Ghost", "/no/such/pack.json")
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"not a pack at all")
    _register(store, "lorebook_pack", "Amber Broken", str(bad))
    doc = hub_usc.unified_search_census_document(
        store.list_for_owner("u1"), "amber")
    assert doc["entries_considered"] == 2
    assert doc["entries_searched"] == 0
    assert doc["skipped_count"] == 2
    assert doc["by_skip_outcome"] == {"invalid": 1, "unavailable": 1}
    assert doc["entries_considered"] == (
        doc["entries_searched"] + doc["skipped_count"])
    assert doc["match_count"] == 2
    assert doc["by_matched_by"]["metadata"] == 2
    assert doc["census_state"] == "metadata_only"
    assert doc["coverage_complete"] is False
    assert doc["truncated"] is False
    skipped_ids = {
        row["id"] for row in doc["unified_search"]["skipped_entries"]}
    assert ghost.id in skipped_ids


# ------------------------------------------------------------ query + kind law


def test_query_refusals_are_p192s_own_error(tmp_path):
    for bad in ("", "   ", None, 42):
        with pytest.raises(hub_unified.HubUnifiedSearchError):
            hub_usc.unified_search_census_document([], bad)
    with pytest.raises(hub_unified.HubUnifiedSearchError):
        hub_usc.unified_search_census_document([], "zephyr", kind="nope")


def test_kind_filter_narrows_the_census(tmp_path):
    store = make_store(tmp_path)
    l_loc, _lp = _lorebook_file(tmp_path)
    p_loc, _pp = _prompt_file(tmp_path)
    _register(store, "lorebook_pack", "Plain Lore", l_loc)
    _register(store, "prompt_pack", "Plain Prompt", p_loc)
    entries = store.list_for_owner("u1")
    doc = hub_usc.unified_search_census_document(
        entries, "zephyr", kind="lorebook_pack")
    assert doc["kind"] == "lorebook_pack"
    assert doc["entries_considered"] == 1
    assert doc["match_count"] == 1
    assert doc["by_kind"] == {
        "lorebook_pack": 1, "preset_bundle": 0,
        "prompt_pack": 0, "scenario_pack": 0}
    assert doc["unified_search"] == hub_unified.unified_search_document(
        entries, "zephyr", kind="lorebook_pack")


# ------------------------------------------------------------ distinctness + purity


def test_census_carries_no_p189_or_p193_axis(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Amber Archive", locator)
    doc = hub_usc.unified_search_census_document(
        store.list_for_owner("u1"), "zephyr")
    assert "by_browse_state" not in doc
    assert "by_checksum_match" not in doc
    assert "browse_state" not in doc
    for key in doc:
        assert "string_value" not in key
        assert "string_char" not in key
        assert "excerpt" not in key


def test_census_writes_nothing(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Amber Archive", locator)
    index_path = tmp_path / "data" / "hub.json"
    before_index = index_path.read_bytes()
    before_pack = (tmp_path / "lorebook-pack.json").read_bytes()
    hub_usc.unified_search_census_document(
        store.list_for_owner("u1"), "amber")
    hub_usc.unified_search_census_document(
        store.list_for_owner("u1"), "zephyr")
    assert index_path.read_bytes() == before_index
    assert (tmp_path / "lorebook-pack.json").read_bytes() == before_pack


def test_foreign_entries_are_never_censused(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Amber Foreign", locator, owner="u2")
    _register(store, "prompt_pack", "Amber Gone", "/no/such.json", owner="u2")
    doc = hub_usc.unified_search_census_document(
        store.list_for_owner("u1"), "amber")
    assert doc["census_state"] == "no_matches"
    assert doc["entries_considered"] == 0
    assert doc["match_count"] == 0
    assert doc["skipped_count"] == 0
    assert doc["total_occurrences"] == 0


# ------------------------------------------------------------ HTTP


def test_http_census_owner_and_results(tmp_path):
    _factory, client = _client(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Plain Title",
        "locator": locator})
    assert created.status_code == 201, created.text
    got = client.get(
        "/api/v1/hub/unified-search-census", params={"q": "zephyr"})
    assert got.status_code == 200
    body = got.json()
    assert body["schema"] == "runmal-p194-hub-unified-search-census-v1"
    assert body["census_state"] == "content_only"
    assert body["match_count"] == 1
    assert body["by_matched_by"]["content"] == 1
    assert body["total_occurrences"] == 1
    assert body["most_occurrences"]["occurrences"] == 1
    meta = client.get(
        "/api/v1/hub/unified-search-census", params={"q": "title"})
    assert meta.status_code == 200
    assert meta.json()["census_state"] == "metadata_only"


def test_http_skips_are_data_at_200_and_refusals_are_422(tmp_path):
    _factory, client = _client(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Gone",
        "locator": "/no/such/pack.json"})
    assert created.status_code == 201, created.text
    got = client.get(
        "/api/v1/hub/unified-search-census", params={"q": "gone"})
    assert got.status_code == 200
    body = got.json()
    assert body["census_state"] == "metadata_only"
    assert body["coverage_complete"] is False
    assert body["by_skip_outcome"] == {"invalid": 0, "unavailable": 1}
    blank = client.get(
        "/api/v1/hub/unified-search-census", params={"q": "  "})
    assert blank.status_code == 422
    missing = client.get("/api/v1/hub/unified-search-census")
    assert missing.status_code == 422
    bad_kind = client.get("/api/v1/hub/unified-search-census",
                          params={"q": "gone", "kind": "nope"})
    assert bad_kind.status_code == 422


def test_http_census_requires_bearer(tmp_path):
    factory, _client_used = _client(tmp_path)
    bare = TestClient(create_app(factory))
    got = bare.get(
        "/api/v1/hub/unified-search-census", params={"q": "zephyr"})
    assert got.status_code == 401


# ------------------------------------------------------------ neighbours


def test_migration_head_stays_0041_and_laws_are_the_banked_ones(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS
    make_factory(tmp_path)
    assert current_revision(tmp_path / "test.db") == "0042"
    assert hub_usc.CENSUS_STATES == {
        "no_matches", "metadata_only", "content_only", "mixed"}
    assert hub_usc.SKIP_OUTCOMES == (
        hub_cs.OUTCOME_UNAVAILABLE, hub_cs.OUTCOME_INVALID)
    assert set(hub_usc.build_unified_search_census(
        hub_unified.unified_search_document([], "zephyr"))
        ["by_matched_by"]) == set(hub_unified.MATCHED_BY)
    assert list(hub_search.SEARCH_FIELDS) == [
        "title", "locator", "note", "kind", "format"]
