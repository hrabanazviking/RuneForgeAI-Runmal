"""P-191 - Hub pack-content search (Part XII, DERIVED).

Pins: the content-search document (schema tag,
search_state under the closed SEARCH_STATES law);
composition verbatim (each pack searched ONLY through
its own layer's verified parse road - parse_pack x3,
parse_share for the preset bundle - under P-188's
locator law and size bound, imported as one bound);
the literal match law over STRING VALUES of the
verified payload only; the honesty exclusions (registry
metadata, pack envelope, content_sha256 values and
dict keys are NEVER searched); occurrences and the
bounded excerpt; the no-silent-omission law (skips
named unavailable / invalid under the closed OUTCOMES
law, coverage_complete as data, considered = searched
+ skipped); the query and kind-filter laws (blank
refused, unknown kind refused); cap honesty
(MAX_MATCHES, true total, truncated); the pure-read
law (registry and pack bytes unchanged); owner
scoping (unit and HTTP); the HTTP road (200 owner,
401 without a bearer, 422 blank query / unknown kind,
skips as data at 200); and the neighbours (migration
head stays 0041; the bound is P-188's own).
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
from runmal.hub import content_search as hub_cs
from runmal.hub import registry as hub
from runmal.lorebooks import packs as lorebook_packs
from runmal.plugins import service as plugin_service
from runmal.presets import bundles as preset_bundles
from runmal.presets import packs as prompt_packs
from runmal.scenarios import packs as scenario_packs
from runmal.scenarios.store import ScenarioStore

STAMP = "2026-11-09T00:00:00+00:00"
SHA_WRONG = "b" * 64


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


def _scenario_file(tmp_path, note=None):
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
    record = store.create("owner-p191", body, now=STAMP)
    pack = scenario_packs.build_pack(record, exported_at=STAMP, note=note)
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
    doc = hub_cs.content_search_document([], "zephyr")
    assert doc["schema"] == "runmal-p191-hub-content-search-v1"
    assert doc["search_state"] == "no_matches"
    assert doc["query"] == "zephyr"
    assert doc["kind"] is None
    assert doc["matches"] == []
    assert doc["match_count"] == 0
    assert doc["total_matches"] == 0
    assert doc["truncated"] is False
    assert doc["entries_considered"] == 0
    assert doc["entries_searched"] == 0
    assert doc["skipped_entries"] == []
    assert doc["coverage_complete"] is True
    assert doc["max_browse_bytes"] == hub_browse.MAX_BROWSE_BYTES
    assert doc["list"] == hub.list_document([])
    assert doc["kind_formats"] == hub.KIND_FORMATS


def test_no_content_match_is_no_matches_but_searched(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Plain Title", locator)
    doc = hub_cs.content_search_document(
        store.list_for_owner("u1"), "harbour")
    assert doc["search_state"] == "no_matches"
    assert doc["entries_searched"] == 1
    assert doc["coverage_complete"] is True


# ------------------------------------------------------------ content found, per kind


def test_lorebook_entry_content_is_found(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    entry = _register(store, "lorebook_pack", "Plain Title", locator)
    doc = hub_cs.content_search_document(
        store.list_for_owner("u1"), "zephyr quill")
    assert doc["search_state"] == "matches"
    assert doc["total_matches"] == 1
    row = doc["matches"][0]
    assert row["id"] == entry.id
    assert row["occurrences"] == 1
    assert "Zephyr Quill" in row["excerpt"]
    assert row["verified_content_sha256"] == (
        pack["manifest"]["content_sha256"])


def test_prompt_item_text_is_found(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _prompt_file(tmp_path)
    _register(store, "prompt_pack", "Plain Title", locator)
    doc = hub_cs.content_search_document(
        store.list_for_owner("u1"), "zephyr prompt")
    assert doc["total_matches"] == 1
    assert doc["matches"][0]["verified_content_sha256"] == (
        pack["manifest"]["content_sha256"])


def test_scenario_text_is_found(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _scenario_file(tmp_path)
    _register(store, "scenario_pack", "Plain Title", locator)
    doc = hub_cs.content_search_document(
        store.list_for_owner("u1"), "zephyr ferry")
    assert doc["total_matches"] == 1
    assert doc["matches"][0]["verified_content_sha256"] == (
        pack["manifest"]["content_sha256"])


def test_bundle_text_is_found_with_verified_checksum(tmp_path):
    store = make_store(tmp_path)
    locator, share = _bundle_file(tmp_path)
    _register(store, "preset_bundle", "Plain Title", locator)
    doc = hub_cs.content_search_document(
        store.list_for_owner("u1"), "zephyr bundle")
    assert doc["total_matches"] == 1
    assert doc["matches"][0]["verified_content_sha256"] == (
        share["manifest"]["content_sha256"])


def test_bare_bundle_is_found_with_empty_verified_checksum(tmp_path):
    store = make_store(tmp_path)
    locator, _bundle = _bundle_file(tmp_path, bare=True)
    _register(store, "preset_bundle", "Plain Title", locator)
    doc = hub_cs.content_search_document(
        store.list_for_owner("u1"), "zephyr bundle")
    assert doc["total_matches"] == 1
    assert doc["matches"][0]["verified_content_sha256"] == ""


# ------------------------------------------------------------ honesty exclusions


def test_registry_metadata_is_never_searched_here(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Metadataonly Title", locator,
              note="metadataonly note")
    entries = store.list_for_owner("u1")
    assert hub_cs.content_search_document(
        entries, "metadataonly")["total_matches"] == 0


def test_envelope_is_never_searched(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _scenario_file(tmp_path, note="provenanceonly token")
    _register(store, "scenario_pack", "Plain Title", locator)
    entries = store.list_for_owner("u1")
    # the note lives only in the pack provenance (the envelope)
    assert hub_cs.content_search_document(
        entries, "provenanceonly")["total_matches"] == 0
    # the format string is envelope, not content
    assert hub_cs.content_search_document(
        entries, "runmal-scenario-pack")["total_matches"] == 0


def test_checksums_and_keys_are_never_searched(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _prompt_file(tmp_path)
    _register(store, "prompt_pack", "Plain Title", locator)
    entries = store.list_for_owner("u1")
    assert hub_cs.content_search_document(
        entries, pack["manifest"]["content_sha256"])["total_matches"] == 0
    item_sha = pack["items"][0]["content_sha256"]
    assert hub_cs.content_search_document(
        entries, item_sha)["total_matches"] == 0
    lore_locator, _lp = _lorebook_file(tmp_path, name="second.json")
    _register(store, "lorebook_pack", "Other Title", lore_locator)
    entries = store.list_for_owner("u1")
    # a dict key name is structure, not content
    assert hub_cs.content_search_document(
        entries, "secondary_keys")["total_matches"] == 0


def test_match_is_literal_casefolded_never_fuzzy_or_regex(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Plain Title", locator)
    entries = store.list_for_owner("u1")
    doc = hub_cs.content_search_document(entries, "  ZEPHYR QUILL ")
    assert doc["query"] == "ZEPHYR QUILL"
    assert doc["total_matches"] == 1
    assert hub_cs.content_search_document(
        entries, ".*")["total_matches"] == 0
    assert hub_cs.content_search_document(
        entries, "zephr")["total_matches"] == 0


def test_occurrences_counted_and_excerpt_windowed(tmp_path):
    store = make_store(tmp_path)
    long_content = "x" * 100 + " needleword " + "y" * 100
    entries = [
        _lore_entry("e1", "One", "zephyr zephyr ZEPHYR", ["a"]),
        _lore_entry("e2", "Two", long_content, ["b"]),
    ]
    locator, _pack = _lorebook_file(tmp_path, entries=entries)
    _register(store, "lorebook_pack", "Plain Title", locator)
    owned = store.list_for_owner("u1")
    doc = hub_cs.content_search_document(owned, "zephyr")
    assert doc["matches"][0]["occurrences"] == 3
    doc = hub_cs.content_search_document(owned, "needleword")
    excerpt = doc["matches"][0]["excerpt"]
    assert "needleword" in excerpt
    assert len(excerpt) == 40 + len("needleword") + 40
    assert excerpt == "x" * 39 + " needleword " + "y" * 39


def test_claimed_checksum_stays_a_claim_on_the_row(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Plain Title", locator, SHA_WRONG)
    doc = hub_cs.content_search_document(
        store.list_for_owner("u1"), "zephyr")
    row = doc["matches"][0]
    assert row["content_sha256"] == SHA_WRONG
    assert row["verified_content_sha256"] == (
        pack["manifest"]["content_sha256"])


# ------------------------------------------------------------ skips + coverage


def test_missing_and_directory_locators_are_named_unavailable(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", "Gone", "/no/such/pack.json")
    _register(store, "prompt_pack", "Dir", str(tmp_path))
    doc = hub_cs.content_search_document(
        store.list_for_owner("u1"), "zephyr")
    assert doc["entries_considered"] == 2
    assert doc["entries_searched"] == 0
    assert doc["coverage_complete"] is False
    assert [row["outcome"] for row in doc["skipped_entries"]] == [
        "unavailable", "unavailable"]
    assert doc["skipped_entries"][0]["locator_state"] == "missing"
    assert doc["skipped_entries"][1]["locator_state"] == "not_a_file"


def test_corrupt_and_wrong_kind_packs_are_named_invalid(tmp_path):
    store = make_store(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"this is not a pack")
    _register(store, "lorebook_pack", "Bad", str(bad))
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "scenario_pack", "Wrong Kind", locator)
    doc = hub_cs.content_search_document(
        store.list_for_owner("u1"), "zephyr")
    assert doc["entries_searched"] == 0
    assert doc["coverage_complete"] is False
    assert [row["outcome"] for row in doc["skipped_entries"]] == [
        "invalid", "invalid"]
    assert all(row["error"] for row in doc["skipped_entries"])


def test_oversize_pack_is_named_invalid(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Big", locator)
    monkeypatch.setattr(hub_cs, "MAX_BROWSE_BYTES", 8)
    doc = hub_cs.content_search_document(
        store.list_for_owner("u1"), "zephyr")
    assert doc["skipped_entries"][0]["outcome"] == "invalid"
    assert "too large" in doc["skipped_entries"][0]["error"]


def test_coverage_invariant_with_mixed_estate(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Good", locator)
    _register(store, "prompt_pack", "Gone", "/no/such/pack.json")
    doc = hub_cs.content_search_document(
        store.list_for_owner("u1"), "zephyr")
    assert doc["entries_considered"] == 2
    assert doc["entries_searched"] == 1
    assert len(doc["skipped_entries"]) == 1
    assert doc["entries_considered"] == (
        doc["entries_searched"] + len(doc["skipped_entries"]))
    assert doc["coverage_complete"] is False
    assert doc["total_matches"] == 1


# ------------------------------------------------------------ query + filter law


def test_blank_or_missing_query_is_refused(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Plain Title", locator)
    entries = store.list_for_owner("u1")
    for bad in ("", "   ", None, 42):
        with pytest.raises(hub_cs.HubContentSearchError):
            hub_cs.content_search_document(entries, bad)


def test_kind_filter_narrows_before_searching(tmp_path):
    store = make_store(tmp_path)
    lore_locator, _lp = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Lore", lore_locator)
    _register(store, "prompt_pack", "Gone", "/no/such/pack.json")
    entries = store.list_for_owner("u1")
    doc = hub_cs.content_search_document(entries, "zephyr",
                                         kind="lorebook_pack")
    assert doc["kind"] == "lorebook_pack"
    assert doc["entries_considered"] == 1
    assert doc["skipped_entries"] == []
    assert doc["coverage_complete"] is True
    assert doc["total_matches"] == 1


def test_unknown_kind_filter_is_refused(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Plain Title", locator)
    entries = store.list_for_owner("u1")
    for bad in ("nope", "", "LOREBOOK_PACK"):
        with pytest.raises(hub_cs.HubContentSearchError):
            hub_cs.content_search_document(entries, "zephyr", kind=bad)


# ------------------------------------------------------------ cap + composition


def test_cap_honesty(tmp_path, monkeypatch):
    assert hub_cs.MAX_MATCHES == 100
    store = make_store(tmp_path)
    for i in range(3):
        locator, _pack = _lorebook_file(
            tmp_path, name=f"pack-{i}.json")
        _register(store, "lorebook_pack", f"Title {i}", locator)
    monkeypatch.setattr(hub_cs, "MAX_MATCHES", 2)
    doc = hub_cs.content_search_document(
        store.list_for_owner("u1"), "zephyr")
    assert doc["search_state"] == "matches_truncated"
    assert doc["total_matches"] == 3
    assert doc["match_count"] == 2
    assert doc["truncated"] is True
    assert doc["list"]["count"] == 2


def test_composition_is_the_p187_list_document_verbatim(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    keep = _register(store, "lorebook_pack", "Plain Title", locator)
    _register(store, "prompt_pack", "Gone", "/no/such/pack.json")
    doc = hub_cs.content_search_document(
        store.list_for_owner("u1"), "zephyr")
    assert doc["list"] == hub.list_document([keep])
    assert doc["list"]["count"] == doc["match_count"] == 1
    assert doc["matches"][0]["id"] == keep.id
    assert doc["matches"][0]["locator_state"] == "ready"


def test_search_writes_nothing(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Plain Title", locator)
    registry_bytes = (tmp_path / "data" / "hub.json").read_bytes()
    pack_bytes = (tmp_path / "lorebook-pack.json").read_bytes()
    hub_cs.content_search_document(store.list_for_owner("u1"), "zephyr")
    assert (tmp_path / "data" / "hub.json").read_bytes() == registry_bytes
    assert (tmp_path / "lorebook-pack.json").read_bytes() == pack_bytes


# ------------------------------------------------------------ owner scoping + HTTP


def test_foreign_entries_are_never_considered(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", "Foreign", locator, owner="u2")
    _register(store, "prompt_pack", "Foreign Gone", "/no/such.json",
              owner="u2")
    doc = hub_cs.content_search_document(
        store.list_for_owner("u1"), "zephyr")
    assert doc["entries_considered"] == 0
    assert doc["total_matches"] == 0
    assert doc["skipped_entries"] == []


def test_http_content_search_owner_scoped(tmp_path):
    _factory, client = _client(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Plain Title",
        "locator": locator})
    assert created.status_code == 201, created.text
    got = client.get("/api/v1/hub/content-search", params={"q": "zephyr"})
    assert got.status_code == 200
    body = got.json()
    assert body["schema"] == "runmal-p191-hub-content-search-v1"
    assert body["total_matches"] == 1
    assert body["matches"][0]["occurrences"] == 1


def test_http_skips_are_data_at_200_and_refusals_are_422(tmp_path):
    _factory, client = _client(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Gone",
        "locator": "/no/such/pack.json"})
    assert created.status_code == 201, created.text
    got = client.get("/api/v1/hub/content-search", params={"q": "zephyr"})
    assert got.status_code == 200
    assert got.json()["coverage_complete"] is False
    assert got.json()["skipped_entries"][0]["outcome"] == "unavailable"
    blank = client.get("/api/v1/hub/content-search", params={"q": "  "})
    assert blank.status_code == 422
    bad_kind = client.get("/api/v1/hub/content-search",
                          params={"q": "zephyr", "kind": "nope"})
    assert bad_kind.status_code == 422


def test_http_content_search_requires_bearer(tmp_path):
    factory, _client_used = _client(tmp_path)
    bare = TestClient(create_app(factory))
    got = bare.get("/api/v1/hub/content-search", params={"q": "zephyr"})
    assert got.status_code == 401


# ------------------------------------------------------------ neighbours


def test_migration_head_stays_0041_and_bound_is_p188s(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS
    make_factory(tmp_path)
    assert current_revision(tmp_path / "test.db") == "0041"
    assert hub_cs.MAX_BROWSE_BYTES == hub_browse.MAX_BROWSE_BYTES
    assert hub_cs.OUTCOMES == {"searched", "unavailable", "invalid"}
    assert hub_cs.SEARCH_STATES == {
        "no_matches", "matches", "matches_truncated"}
