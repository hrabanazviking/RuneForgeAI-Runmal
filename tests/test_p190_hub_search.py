"""P-190 - Hub search over entries (Part XII, DERIVED).

Pins: the search document (schema tag, search_state under
the closed SEARCH_STATES law: no_matches / matches /
matches_truncated); the literal match law (the query
casefolded as a substring of a searched field's casefolded
value, over the closed SEARCH_FIELDS only - title /
locator / note / kind / format - with matched_fields in
that law's order); the honesty law (pack contents, the
claimed checksum, ids and timestamps are NEVER searched;
no fuzzy or semantic matching); the query law (required,
stripped; empty or blank refused plainly, never
match-everything); composition verbatim (the embedded
list equals a direct P-187 list_document call over the
capped matched set, rows carry P-187's live locator
state); the kind filter (narrows before searching;
unknown kind refused); cap honesty (MAX_MATCHES rows,
the true total carried, truncated named); the
by_matched_field axis (sums fields, not rows); the
pure-read law (writes nothing, opens no pack - a corrupt
pack at a matching locator still matches on metadata);
owner scoping (unit and HTTP); the HTTP road (200 for
the owner, 401 without a bearer, 422 for a blank query
or an unknown kind); and the neighbours (migration head
stays 0041; the P-187/P-188/P-189 laws unchanged).
No network: fixtures only.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.hub import browse as hub_browse
from runmal.hub import census as hub_census
from runmal.hub import registry as hub
from runmal.hub import search as hub_search
from runmal.lorebooks import packs as lorebook_packs
from runmal.plugins import service as plugin_service

STAMP = "2026-11-09T00:00:00+00:00"
SHA_A = "a" * 64


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


def _lorebook_file(tmp_path) -> tuple[str, dict]:
    book = {
        "id": "book-1", "name": "Zephyr Quill Tales",
        "description": "World lore.", "scan_depth": 7,
        "token_budget": 900, "scan_mode": "depth",
        "scan_external_context": False,
        "created_at": "2026-01-01T00:00:00+00:00",
        "entry_count": 0,
    }
    pack = lorebook_packs.build_pack(book, [], exported_at=STAMP)
    path = tmp_path / "plain-name.json"
    path.write_bytes(lorebook_packs.pack_to_bytes(pack))
    return str(path), pack


# ------------------------------------------------------------ document basics


def test_empty_estate_is_no_matches_with_zero_filled_axes(tmp_path):
    doc = hub_search.search_document([], "fjord")
    assert doc["schema"] == "runmal-p190-hub-search-v1"
    assert doc["search_state"] == "no_matches"
    assert doc["query"] == "fjord"
    assert doc["kind"] is None
    assert doc["matches"] == []
    assert doc["match_count"] == 0
    assert doc["total_matches"] == 0
    assert doc["truncated"] is False
    assert doc["by_matched_field"] == {
        "title": 0, "locator": 0, "note": 0, "kind": 0, "format": 0}
    assert doc["searched_fields"] == [
        "title", "locator", "note", "kind", "format"]
    assert doc["list"] == hub.list_document([])
    assert doc["kind_formats"] == hub.KIND_FORMATS


def test_no_match_query_is_no_matches(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", "Fjord Sagas", "/packs/fjord.json")
    doc = hub_search.search_document(store.list_for_owner("u1"), "harbour")
    assert doc["search_state"] == "no_matches"
    assert doc["total_matches"] == 0
    assert doc["list"]["count"] == 0


# ------------------------------------------------------------ the literal law


def test_title_match_is_casefolded_substring(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", "Fjord Sagas", "/packs/one.json")
    _register(store, "prompt_pack", "Hall Preset", "/packs/two.json")
    doc = hub_search.search_document(
        store.list_for_owner("u1"), "  JORD sag ")
    assert doc["query"] == "JORD sag"  # stripped, case kept
    assert doc["search_state"] == "matches"
    assert doc["total_matches"] == 1
    row = doc["matches"][0]
    assert row["title"] == "Fjord Sagas"
    assert row["matched_fields"] == ["title"]


def test_each_searched_field_matches_and_fields_keep_law_order(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", "Alpha Pack", "/alpha/pack.json",
              note="alpha note")
    _register(store, "preset_bundle", "Plain", "/packs/bundle.json")
    _register(store, "scenario_pack", "Plain Two", "/packs/scene.json")
    entries = store.list_for_owner("u1")
    doc = hub_search.search_document(entries, "alpha")
    assert doc["total_matches"] == 1
    assert doc["matches"][0]["matched_fields"] == [
        "title", "locator", "note"]
    doc = hub_search.search_document(entries, "preset_bundle")
    assert doc["total_matches"] == 1
    assert doc["matches"][0]["matched_fields"] == ["kind"]
    doc = hub_search.search_document(entries, "runmal-scenario-pack")
    assert doc["total_matches"] == 1
    assert doc["matches"][0]["matched_fields"] == ["format"]
    doc = hub_search.search_document(entries, "bundle.json")
    assert doc["total_matches"] == 1
    assert doc["matches"][0]["matched_fields"] == ["locator"]


def test_by_matched_field_sums_fields_not_rows(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", "Alpha Pack", "/alpha/pack.json",
              note="alpha note")
    _register(store, "prompt_pack", "Alpha Other", "/packs/other.json")
    doc = hub_search.search_document(store.list_for_owner("u1"), "alpha")
    assert doc["total_matches"] == 2
    assert doc["match_count"] == 2
    assert doc["by_matched_field"] == {
        "title": 2, "locator": 1, "note": 1, "kind": 0, "format": 0}


def test_match_is_literal_never_fuzzy_or_regex(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", "Fjord Sagas", "/packs/fjord.json")
    entries = store.list_for_owner("u1")
    assert hub_search.search_document(entries, ".*")["total_matches"] == 0
    assert hub_search.search_document(entries, "fjrd")["total_matches"] == 0
    assert hub_search.search_document(
        entries, "sagas fjord")["total_matches"] == 0


def test_pack_contents_and_claimed_checksum_are_never_searched(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Plain Title", locator, SHA_A)
    entries = store.list_for_owner("u1")
    # "Zephyr Quill" lives only inside the pack's contents
    assert hub_search.search_document(
        entries, "zephyr quill")["total_matches"] == 0
    # the claimed checksum is a claim, not search text
    assert hub_search.search_document(
        entries, SHA_A)["total_matches"] == 0
    assert hub_search.search_document(
        entries, pack["manifest"]["content_sha256"])["total_matches"] == 0


# ------------------------------------------------------------ query + filter law


def test_blank_or_missing_query_is_refused_never_match_everything(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", "Fjord Sagas", "/packs/fjord.json")
    entries = store.list_for_owner("u1")
    for bad in ("", "   ", None, 42):
        with pytest.raises(hub_search.HubSearchError):
            hub_search.search_document(entries, bad)


def test_kind_filter_narrows_before_searching(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", "Alpha Lore", "/packs/a.json")
    _register(store, "prompt_pack", "Alpha Prompt", "/packs/b.json")
    entries = store.list_for_owner("u1")
    doc = hub_search.search_document(entries, "alpha", kind="prompt_pack")
    assert doc["kind"] == "prompt_pack"
    assert doc["total_matches"] == 1
    assert doc["matches"][0]["kind"] == "prompt_pack"
    assert doc["list"]["by_kind"]["prompt_pack"] == 1
    assert doc["list"]["by_kind"]["lorebook_pack"] == 0


def test_unknown_kind_filter_is_refused(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", "Alpha Lore", "/packs/a.json")
    entries = store.list_for_owner("u1")
    for bad in ("nope", "", "LOREBOOK_PACK"):
        with pytest.raises(hub_search.HubSearchError):
            hub_search.search_document(entries, "alpha", kind=bad)


# ------------------------------------------------------------ composition


def test_composition_is_the_p187_list_document_verbatim(tmp_path):
    store = make_store(tmp_path)
    keep = _register(
        store, "lorebook_pack", "Fjord Sagas", str(tmp_path / "real.json"))
    _register(store, "prompt_pack", "Hall Preset", "/packs/two.json")
    entries = store.list_for_owner("u1")
    doc = hub_search.search_document(entries, "fjord")
    assert doc["list"] == hub.list_document([keep])
    assert doc["list"]["count"] == doc["match_count"] == 1
    row = doc["matches"][0]
    assert row["id"] == keep.id
    assert row["format"] == hub.KIND_FORMATS["lorebook_pack"]
    assert row["locator_state"] == "missing"  # judged live by P-187
    assert row["matched_fields"] == ["title"]


def test_cap_honesty_over_max_matches(tmp_path):
    store = make_store(tmp_path)
    for i in range(hub_search.MAX_MATCHES + 1):
        _register(store, "lorebook_pack", f"Match Pack {i}",
                  f"/packs/m{i}.json")
    entries = store.list_for_owner("u1")
    doc = hub_search.search_document(entries, "match pack")
    assert doc["total_matches"] == hub_search.MAX_MATCHES + 1
    assert doc["match_count"] == hub_search.MAX_MATCHES
    assert len(doc["matches"]) == hub_search.MAX_MATCHES
    assert doc["truncated"] is True
    assert doc["search_state"] == "matches_truncated"
    assert doc["list"] == hub.list_document(entries[:hub_search.MAX_MATCHES])
    assert doc["list"]["count"] == hub_search.MAX_MATCHES


# ------------------------------------------------------------ read-only + scoping


def test_search_writes_nothing_and_opens_no_pack(tmp_path):
    store = make_store(tmp_path)
    bad = tmp_path / "broken.json"
    bad.write_bytes(b"{not a pack")
    _register(store, "lorebook_pack", "Broken Fjord", str(bad))
    hub_bytes_before = (tmp_path / "data" / "hub.json").read_bytes()
    pack_bytes_before = bad.read_bytes()
    doc = hub_search.search_document(store.list_for_owner("u1"), "fjord")
    # a corrupt pack still matches on its entry metadata: no
    # pack was opened, so nothing about it could fail here
    assert doc["total_matches"] == 1
    assert doc["matches"][0]["matched_fields"] == ["title"]
    assert (tmp_path / "data" / "hub.json").read_bytes() == hub_bytes_before
    assert bad.read_bytes() == pack_bytes_before
    assert len(store.list_for_owner("u1")) == 1


def test_search_never_includes_a_foreign_owners_entries(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", "Fjord Mine", "/packs/mine.json")
    _register(store, "lorebook_pack", "Fjord Foreign", "/packs/foreign.json",
              owner="someone-else")
    doc = hub_search.search_document(store.list_for_owner("u1"), "fjord")
    assert doc["total_matches"] == 1
    assert doc["matches"][0]["title"] == "Fjord Mine"
    assert doc["matches"][0]["owner_id"] == "u1"


# ------------------------------------------------------------ HTTP road


def test_http_search_owner_and_results(tmp_path):
    _factory, client = _client(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Fjord Pack",
        "locator": "/packs/fjord.json", "note": "harbour copy"})
    assert created.status_code == 201, created.text
    resp = client.get("/api/v1/hub/search", params={"q": "harbour"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["schema"] == "runmal-p190-hub-search-v1"
    assert body["search_state"] == "matches"
    assert body["total_matches"] == 1
    assert body["matches"][0]["title"] == "Fjord Pack"
    assert body["matches"][0]["matched_fields"] == ["note"]
    resp = client.get("/api/v1/hub/search", params={
        "q": "fjord", "kind": "prompt_pack"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_matches"] == 0


def test_http_search_refusals_and_bearer(tmp_path):
    factory, client = _client(tmp_path)
    assert client.get(
        "/api/v1/hub/search", params={"q": "  "}).status_code == 422
    assert client.get("/api/v1/hub/search").status_code == 422
    assert client.get("/api/v1/hub/search", params={
        "q": "x", "kind": "nope"}).status_code == 422
    bare = TestClient(create_app(factory))
    assert bare.get(
        "/api/v1/hub/search", params={"q": "x"}).status_code == 401


def test_http_search_never_includes_foreign_entries(tmp_path):
    _factory, client = _client(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Fjord Own",
        "locator": "/packs/own.json"})
    assert created.status_code == 201, created.text
    store = make_store(tmp_path)
    hub.register_entry(
        store, owner_id="someone-else", kind="lorebook_pack",
        title="Fjord Foreign", locator="/packs/foreign.json")
    resp = client.get("/api/v1/hub/search", params={"q": "fjord"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_matches"] == 1
    assert body["matches"][0]["title"] == "Fjord Own"


# ------------------------------------------------------------ neighbours


def test_neighbours_heads_and_closed_laws(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS
    make_factory(tmp_path)
    assert current_revision(tmp_path / "test.db") == "0041"
    assert hub_search.SEARCH_STATES == {
        "no_matches", "matches", "matches_truncated"}
    assert hub_search.SEARCH_FIELDS == (
        "title", "locator", "note", "kind", "format")
    assert hub_search.MAX_MATCHES == 100
    assert hub_census.CENSUS_STATES == {
        "no_entries", "none_inspected", "some_inspected", "all_inspected"}
    assert hub_browse.BROWSE_STATES == {
        "inspected", "unavailable", "invalid"}
    assert set(hub.HUB_KINDS) == {
        "lorebook_pack", "prompt_pack", "preset_bundle", "scenario_pack"}
    assert hub.ENTRY_SCHEMA == "runmal-p187-hub-entry-v1"
    assert hub_browse.BROWSE_SCHEMA == "runmal-p188-hub-browse-v1"
    assert hub_census.CENSUS_SCHEMA == "runmal-p189-hub-census-v1"
