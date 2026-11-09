"""P-188 - Hub-side browse over entry contents (Part XII, DERIVED).

Pins: the browse document (schema tag, the P-187 entry
row verbatim, locator state judged live); the closed
BROWSE_STATES law (inspected / unavailable / invalid,
all data at 200, never an error dressed as success);
composition verbatim - the inspection equals a direct
call of the owning layer's own verified road for all
four kinds (inspect_pack x3, parse_share for the preset
bundle, whose layer owns no inspect_pack); the
checksum law (the entry claim stays a claim: the road's
verified checksum rides beside it and checksum_match is
true / false / null - null when no claim was registered
and null when the road verifies none, the bare bundle);
unavailable for missing and not_a_file locators (no read
attempted); invalid for corrupt contents and for a pack
of the wrong kind, with the owning road's own refusal as
the error; the size bound; browse writes NOTHING
(registry bytes and pack bytes unchanged, nothing
imported); owner scoping on the HTTP road (unknown and
foreign both 404, no bearer 401); and the neighbours
(migration head stays 0041; the dispatch covers exactly
HUB_KINDS). No network: fixtures only.
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


# ------------------------------------------------------------ pack fixtures


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
    record = store.create("owner-p188", body, now=STAMP)
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


def _register(store, kind, locator, sha=""):
    return hub.register_entry(
        store, owner_id="u1", kind=kind, title="A pack",
        locator=locator, content_sha256=sha)


# ------------------------------------------------------------ inspected, verbatim


def test_browse_lorebook_pack_composes_inspect_verbatim(tmp_path):
    locator, pack = _lorebook_file(tmp_path)
    entry = _register(make_store(tmp_path), "lorebook_pack", locator,
                      pack["manifest"]["content_sha256"])
    doc = hub_browse.browse_document(entry)
    assert doc["schema"] == "runmal-p188-hub-browse-v1"
    assert doc["entry"]["id"] == entry.id
    assert doc["locator_state"] == "ready"
    assert doc["browse_state"] == "inspected"
    assert doc["inspection"] == lorebook_packs.inspect_pack(
        (tmp_path / "lorebook-pack.json").read_bytes())
    assert doc["inspection"]["checksum_verified"] is True
    assert doc["verified_content_sha256"] == pack["manifest"]["content_sha256"]
    assert doc["checksum_match"] is True
    assert doc["error"] == ""


def test_browse_prompt_pack_composes_inspect_verbatim(tmp_path):
    locator, pack = _prompt_file(tmp_path)
    entry = _register(make_store(tmp_path), "prompt_pack", locator,
                      pack["manifest"]["content_sha256"])
    doc = hub_browse.browse_document(entry)
    assert doc["browse_state"] == "inspected"
    assert doc["inspection"] == prompt_packs.inspect_pack(
        (tmp_path / "prompt-pack.json").read_bytes())
    assert doc["checksum_match"] is True


def test_browse_scenario_pack_composes_inspect_verbatim(tmp_path):
    locator, pack = _scenario_file(tmp_path)
    entry = _register(make_store(tmp_path), "scenario_pack", locator,
                      pack["manifest"]["content_sha256"])
    doc = hub_browse.browse_document(entry)
    assert doc["browse_state"] == "inspected"
    assert doc["inspection"] == scenario_packs.inspect_pack(
        (tmp_path / "scenario-pack.json").read_bytes())
    assert doc["checksum_match"] is True


def test_browse_preset_bundle_composes_parse_share(tmp_path):
    locator, share = _bundle_file(tmp_path)
    entry = _register(make_store(tmp_path), "preset_bundle", locator,
                      share["manifest"]["content_sha256"])
    doc = hub_browse.browse_document(entry)
    assert doc["browse_state"] == "inspected"
    inspection = doc["inspection"]
    _bundle, report = preset_bundles.parse_share(share)
    assert inspection["schema"] == preset_bundles.BUNDLE_SCHEMA
    assert inspection["format"] == "runmal-preset-bundle"
    assert inspection["bundle_name"] == "Bare Bundle"
    assert inspection["report"] == report
    assert inspection["checksum_verified"] is True
    assert doc["verified_content_sha256"] == share["manifest"]["content_sha256"]
    assert doc["checksum_match"] is True


def test_browse_bare_bundle_verifies_no_checksum(tmp_path):
    locator, _bundle = _bundle_file(tmp_path, bare=True)
    entry = _register(make_store(tmp_path), "preset_bundle", locator, SHA_WRONG)
    doc = hub_browse.browse_document(entry)
    assert doc["browse_state"] == "inspected"
    assert doc["inspection"]["checksum_verified"] is False
    assert doc["verified_content_sha256"] == ""
    assert doc["checksum_match"] is None  # nothing verified: no verdict faked


# ------------------------------------------------------------ checksum law


def test_checksum_match_false_for_a_wrong_claim(tmp_path):
    locator, _pack = _lorebook_file(tmp_path)
    entry = _register(make_store(tmp_path), "lorebook_pack", locator, SHA_WRONG)
    doc = hub_browse.browse_document(entry)
    assert doc["browse_state"] == "inspected"
    assert doc["checksum_match"] is False  # the claim stays a claim


def test_checksum_match_none_without_a_claim(tmp_path):
    locator, _pack = _lorebook_file(tmp_path)
    entry = _register(make_store(tmp_path), "lorebook_pack", locator)
    doc = hub_browse.browse_document(entry)
    assert doc["browse_state"] == "inspected"
    assert doc["verified_content_sha256"] != ""
    assert doc["checksum_match"] is None


# ------------------------------------------------------------ unavailable / invalid


def test_browse_missing_locator_is_unavailable(tmp_path):
    entry = _register(make_store(tmp_path), "lorebook_pack",
                      str(tmp_path / "ghost.json"))
    doc = hub_browse.browse_document(entry)
    assert doc["browse_state"] == "unavailable"
    assert doc["locator_state"] == "missing"
    assert doc["inspection"] is None


def test_browse_directory_locator_is_unavailable(tmp_path):
    entry = _register(make_store(tmp_path), "lorebook_pack", str(tmp_path))
    doc = hub_browse.browse_document(entry)
    assert doc["browse_state"] == "unavailable"
    assert doc["locator_state"] == "not_a_file"
    assert doc["inspection"] is None


def test_browse_corrupt_contents_is_invalid_with_reason(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_bytes(b"{not a pack")
    entry = _register(make_store(tmp_path), "lorebook_pack", str(bad))
    doc = hub_browse.browse_document(entry)
    assert doc["browse_state"] == "invalid"
    assert doc["inspection"] is None
    assert doc["error"] != ""


def test_browse_wrong_kind_contents_is_invalid(tmp_path):
    locator, _pack = _lorebook_file(tmp_path)
    entry = _register(make_store(tmp_path), "scenario_pack", locator)
    doc = hub_browse.browse_document(entry)
    assert doc["browse_state"] == "invalid"
    assert "runmal-scenario-pack" in doc["error"]


def test_browse_tampered_bundle_is_invalid(tmp_path):
    locator, share = _bundle_file(tmp_path)
    tampered = json.loads(json.dumps(share))
    tampered["bundle"]["name"] = "Altered Bundle"
    (tmp_path / "preset-bundle.json").write_text(json.dumps(tampered))
    entry = _register(make_store(tmp_path), "preset_bundle", locator,
                      share["manifest"]["content_sha256"])
    doc = hub_browse.browse_document(entry)
    assert doc["browse_state"] == "invalid"
    assert doc["error"] != ""


def test_browse_oversize_is_invalid_without_a_read(tmp_path, monkeypatch):
    locator, _pack = _lorebook_file(tmp_path)
    monkeypatch.setattr(hub_browse, "MAX_BROWSE_BYTES", 8)
    entry = _register(make_store(tmp_path), "lorebook_pack", locator)
    doc = hub_browse.browse_document(entry)
    assert doc["browse_state"] == "invalid"
    assert doc["error"] == "pack file too large to browse"


# ------------------------------------------------------------ read-only law


def test_browse_writes_nothing(tmp_path):
    locator, pack = _lorebook_file(tmp_path)
    store = make_store(tmp_path)
    entry = _register(store, "lorebook_pack", locator,
                      pack["manifest"]["content_sha256"])
    hub_bytes_before = (tmp_path / "data" / "hub.json").read_bytes()
    pack_bytes_before = (tmp_path / "lorebook-pack.json").read_bytes()
    doc = hub_browse.browse_document(entry)
    assert doc["browse_state"] == "inspected"
    assert (tmp_path / "data" / "hub.json").read_bytes() == hub_bytes_before
    assert (tmp_path / "lorebook-pack.json").read_bytes() == pack_bytes_before
    assert len(store.list_for_owner("u1")) == 1  # nothing added or imported


# ------------------------------------------------------------ HTTP road


def test_http_browse_owner_foreign_unknown(tmp_path):
    _factory, client = _client(tmp_path)
    locator, pack = _lorebook_file(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Fjord pack",
        "locator": locator,
        "content_sha256": pack["manifest"]["content_sha256"]})
    assert created.status_code == 201, created.text
    entry_id = created.json()["entry"]["id"]

    resp = client.get(f"/api/v1/hub/entries/{entry_id}/browse")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["browse_state"] == "inspected"
    assert body["inspection"]["book_name"] == "Fjord Sagas"
    assert body["checksum_match"] is True

    assert client.get(
        "/api/v1/hub/entries/no-such-id/browse").status_code == 404

    # A foreign owner's entry answers exactly like an unknown one:
    # register directly under another owner in the same store.
    store = make_store(tmp_path)
    foreign = hub.register_entry(
        store, owner_id="someone-else", kind="lorebook_pack",
        title="Foreign", locator=locator)
    resp = client.get(f"/api/v1/hub/entries/{foreign.id}/browse")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "hub entry not found"


def test_http_browse_requires_bearer(tmp_path):
    factory, client = _client(tmp_path)
    locator, _pack = _lorebook_file(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Fjord pack", "locator": locator})
    entry_id = created.json()["entry"]["id"]
    bare = TestClient(create_app(factory))
    assert bare.get(
        f"/api/v1/hub/entries/{entry_id}/browse").status_code == 401


def test_http_browse_unavailable_is_data_at_200(tmp_path):
    _factory, client = _client(tmp_path)
    created = client.post("/api/v1/hub/entries", json={
        "kind": "prompt_pack", "title": "Ghost",
        "locator": str(tmp_path / "ghost.json")})
    entry_id = created.json()["entry"]["id"]
    resp = client.get(f"/api/v1/hub/entries/{entry_id}/browse")
    assert resp.status_code == 200, resp.text
    assert resp.json()["browse_state"] == "unavailable"


# ------------------------------------------------------------ neighbours


def test_neighbours_head_and_dispatch_coverage(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS
    make_factory(tmp_path)
    assert current_revision(tmp_path / "test.db") == "0041"
    assert hub_browse.BROWSE_STATES == {
        "inspected", "unavailable", "invalid"}
    assert set(hub.HUB_KINDS) == {
        "lorebook_pack", "prompt_pack", "preset_bundle", "scenario_pack"}
