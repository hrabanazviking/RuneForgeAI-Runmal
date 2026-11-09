"""P-189 - Hub census over the registry estate (Part XII, DERIVED).

Pins: the census document (schema tag, census_state under
the closed CENSUS_STATES law judged on the browse axis:
no_entries / none_inspected / some_inspected /
all_inspected); composition verbatim - the embedded list
equals a direct P-187 list_document call, and every row's
browse fields equal that entry's direct P-188
browse_document values, with no inspection embedded;
the axes summed from the composed documents' own values
(by_browse_state zero-filled under BROWSE_STATES;
by_checksum_match under match / mismatch / undetermined,
the claim never upgraded); a bad pack is an invalid row,
never a census failure; the census writes NOTHING
(registry bytes and pack bytes unchanged, nothing
imported); owner scoping (a foreign owner's entries
never enter a census, unit and HTTP); the HTTP road (200
for the owner, 401 without a bearer); and the neighbours
(migration head stays 0041; the P-187/P-188 laws
unchanged). No network: fixtures only.
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


def _lorebook_file(tmp_path) -> tuple[str, dict]:
    book = {
        "id": "book-1", "name": "Fjord Sagas",
        "description": "World lore.", "scan_depth": 7,
        "token_budget": 900, "scan_mode": "depth",
        "scan_external_context": False,
        "created_at": "2026-01-01T00:00:00+00:00",
        "entry_count": 0,
    }
    pack = lorebook_packs.build_pack(book, [], exported_at=STAMP)
    path = tmp_path / "lorebook-pack.json"
    path.write_bytes(lorebook_packs.pack_to_bytes(pack))
    return str(path), pack


def _prompt_file(tmp_path) -> tuple[str, dict]:
    item = {
        "kind": "preset", "name": "Hall Preset",
        "payload": {
            "name": "Hall Preset",
            "params": {"temperature": 0.7},
            "template_ref": "", "source_format": "st-chat",
            "raw": {"temperature": 0.7},
            "prompts": [{"identifier": "main", "content": "Hi."}],
            "prompt_order": [{"identifier": "main", "enabled": True}],
        },
    }
    pack = prompt_packs.build_pack("Workshop", [item], exported_at=STAMP)
    path = tmp_path / "prompt-pack.json"
    path.write_bytes(prompt_packs.pack_to_bytes(pack))
    return str(path), pack


def _scenario_file(tmp_path) -> tuple[str, dict]:
    store = ScenarioStore(tmp_path / "scenarios.json")
    body = {
        "name": "Harbour Lights at Dusk",
        "description": "A quiet harbour, first evening.",
        "scenario_text": "The ferry has just left.",
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
    record = store.create("owner-p189", body, now=STAMP)
    pack = scenario_packs.build_pack(record, exported_at=STAMP)
    path = tmp_path / "scenario-pack.json"
    path.write_bytes(scenario_packs.pack_to_bytes(pack))
    return str(path), pack


def _bundle_file(tmp_path, *, bare: bool = False) -> tuple[str, dict]:
    bundle = preset_bundles.validate_bundle({"name": "Bare Bundle"})
    share = preset_bundles.build_share(bundle, exported_at=STAMP)
    path = tmp_path / "preset-bundle.json"
    if bare:
        path.write_text(json.dumps(bundle))
        return str(path), bundle
    path.write_text(json.dumps(share))
    return str(path), share


def _register(store, kind, locator, sha="", owner="u1"):
    return hub.register_entry(
        store, owner_id=owner, kind=kind, title="A pack",
        locator=locator, content_sha256=sha)


def _full_estate(tmp_path, store):
    """One ready, correctly-claimed entry of each kind."""
    entries = []
    for kind, maker in (
            ("lorebook_pack", _lorebook_file),
            ("prompt_pack", _prompt_file),
            ("scenario_pack", _scenario_file),
            ("preset_bundle", _bundle_file)):
        locator, pack = maker(tmp_path)
        entries.append(_register(
            store, kind, locator, pack["manifest"]["content_sha256"]))
    return entries


# ------------------------------------------------------------ the estate view


def test_empty_estate_is_no_entries_with_zero_filled_axes(tmp_path):
    doc = hub_census.census_document([])
    assert doc["schema"] == "runmal-p189-hub-census-v1"
    assert doc["census_state"] == "no_entries"
    assert doc["count"] == 0
    assert doc["entries"] == []
    assert doc["by_browse_state"] == {
        "inspected": 0, "invalid": 0, "unavailable": 0}
    assert doc["by_checksum_match"] == {
        "match": 0, "mismatch": 0, "undetermined": 0}
    assert doc["list"] == hub.list_document([])
    assert doc["kind_formats"] == hub.KIND_FORMATS


def test_full_estate_all_inspected_and_composed_verbatim(tmp_path):
    store = make_store(tmp_path)
    entries = _full_estate(tmp_path, store)
    doc = hub_census.census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "all_inspected"
    assert doc["count"] == 4
    assert doc["list"] == hub.list_document(entries)
    assert doc["list"]["by_kind"] == {
        "lorebook_pack": 1, "preset_bundle": 1,
        "prompt_pack": 1, "scenario_pack": 1}
    assert doc["by_browse_state"] == {
        "inspected": 4, "invalid": 0, "unavailable": 0}
    assert doc["by_checksum_match"] == {
        "match": 4, "mismatch": 0, "undetermined": 0}
    for row, entry in zip(doc["entries"], entries, strict=True):
        browse_doc = hub_browse.browse_document(entry)
        assert row["id"] == entry.id
        assert row["format"] == hub.KIND_FORMATS[entry.kind]
        assert row["browse_state"] == browse_doc["browse_state"]
        assert row["locator_state"] == browse_doc["locator_state"]
        assert row["verified_content_sha256"] == (
            browse_doc["verified_content_sha256"])
        assert row["checksum_match"] == browse_doc["checksum_match"]
        assert row["error"] == browse_doc["error"]
        assert "inspection" not in row  # stays on the P-188 road


def test_missing_locator_estate_is_none_inspected(tmp_path):
    store = make_store(tmp_path)
    _register(store, "lorebook_pack", str(tmp_path / "ghost.json"))
    doc = hub_census.census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "none_inspected"
    assert doc["by_browse_state"] == {
        "inspected": 0, "invalid": 0, "unavailable": 1}
    assert doc["by_checksum_match"]["undetermined"] == 1
    assert doc["entries"][0]["locator_state"] == "missing"


def test_mixed_estate_is_some_inspected(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", locator,
              pack["manifest"]["content_sha256"])
    _register(store, "prompt_pack", str(tmp_path / "ghost.json"))
    doc = hub_census.census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "some_inspected"
    assert doc["by_browse_state"] == {
        "inspected": 1, "invalid": 0, "unavailable": 1}
    assert doc["list"]["by_locator_state"]["ready"] == 1
    assert doc["list"]["by_locator_state"]["missing"] == 1


def test_corrupt_pack_is_an_invalid_row_never_a_census_failure(tmp_path):
    store = make_store(tmp_path)
    bad = tmp_path / "broken.json"
    bad.write_bytes(b"{not a pack")
    _register(store, "lorebook_pack", str(bad))
    doc = hub_census.census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "none_inspected"
    assert doc["by_browse_state"]["invalid"] == 1
    assert doc["entries"][0]["browse_state"] == "invalid"
    assert doc["entries"][0]["error"] != ""


# ------------------------------------------------------------ checksum axis


def test_wrong_claim_counts_as_mismatch(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", locator, SHA_WRONG)
    doc = hub_census.census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "all_inspected"
    assert doc["by_checksum_match"] == {
        "match": 0, "mismatch": 1, "undetermined": 0}
    # the claim in the row is still the claim, never upgraded
    assert doc["entries"][0]["content_sha256"] == SHA_WRONG
    assert doc["entries"][0]["checksum_match"] is False


def test_no_claim_and_bare_bundle_are_undetermined(tmp_path):
    store = make_store(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", locator)  # no claim at all
    bare_locator, _bundle = _bundle_file(tmp_path, bare=True)
    _register(store, "preset_bundle", bare_locator, SHA_WRONG)
    doc = hub_census.census_document(store.list_for_owner("u1"))
    assert doc["census_state"] == "all_inspected"
    assert doc["by_checksum_match"] == {
        "match": 0, "mismatch": 0, "undetermined": 2}


# ------------------------------------------------------------ read-only + scoping


def test_census_writes_nothing(tmp_path):
    store = make_store(tmp_path)
    _full_estate(tmp_path, store)
    hub_bytes_before = (tmp_path / "data" / "hub.json").read_bytes()
    pack_bytes_before = (tmp_path / "lorebook-pack.json").read_bytes()
    doc = hub_census.census_document(store.list_for_owner("u1"))
    assert doc["count"] == 4
    assert (tmp_path / "data" / "hub.json").read_bytes() == hub_bytes_before
    assert (tmp_path / "lorebook-pack.json").read_bytes() == pack_bytes_before
    assert len(store.list_for_owner("u1")) == 4  # nothing added or imported


def test_census_never_includes_a_foreign_owners_entries(tmp_path):
    store = make_store(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    _register(store, "lorebook_pack", locator,
              pack["manifest"]["content_sha256"])
    _register(store, "prompt_pack", str(tmp_path / "ghost.json"),
              owner="someone-else")
    doc = hub_census.census_document(store.list_for_owner("u1"))
    assert doc["count"] == 1
    assert doc["entries"][0]["owner_id"] == "u1"


# ------------------------------------------------------------ HTTP road


def test_http_census_owner_and_scoping(tmp_path):
    _factory, client = _client(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Fjord pack",
        "locator": locator,
        "content_sha256": pack["manifest"]["content_sha256"]})
    assert created.status_code == 201, created.text
    # a foreign owner's entry in the same store must not appear
    store = make_store(tmp_path)
    hub.register_entry(
        store, owner_id="someone-else", kind="prompt_pack",
        title="Foreign", locator=str(tmp_path / "ghost.json"))
    resp = client.get("/api/v1/hub/census")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["schema"] == "runmal-p189-hub-census-v1"
    assert body["census_state"] == "all_inspected"
    assert body["count"] == 1
    assert body["entries"][0]["title"] == "Fjord pack"


def test_http_census_empty_estate_and_bearer(tmp_path):
    factory, client = _client(tmp_path)
    resp = client.get("/api/v1/hub/census")
    assert resp.status_code == 200, resp.text
    assert resp.json()["census_state"] == "no_entries"
    assert resp.json()["count"] == 0
    bare = TestClient(create_app(factory))
    assert bare.get("/api/v1/hub/census").status_code == 401


# ------------------------------------------------------------ neighbours


def test_neighbours_heads_and_closed_laws(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS
    make_factory(tmp_path)
    assert current_revision(tmp_path / "test.db") == "0041"
    assert hub_census.CENSUS_STATES == {
        "no_entries", "none_inspected", "some_inspected", "all_inspected"}
    assert hub_census.CHECKSUM_KEYS == {
        "match", "mismatch", "undetermined"}
    assert hub_browse.BROWSE_STATES == {
        "inspected", "unavailable", "invalid"}
    assert set(hub.HUB_KINDS) == {
        "lorebook_pack", "prompt_pack", "preset_bundle", "scenario_pack"}
    assert hub.ENTRY_SCHEMA == "runmal-p187-hub-entry-v1"
    assert hub_browse.BROWSE_SCHEMA == "runmal-p188-hub-browse-v1"
