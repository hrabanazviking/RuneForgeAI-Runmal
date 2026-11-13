"""P-187 - Hub registry foundation (Part XII opener, DERIVED).

Pins: the registry record (one owner-scoped index entry
per pack artefact, kind under the closed HUB_KINDS law
mapped to the four sealed pack formats, locator stored
verbatim as data in the house JSON store, no migration),
the register refusals (empty title, empty locator,
unknown kind, malformed checksum, duplicate triple -
nothing stored), the checksum law (caller-claimed,
shape-checked, stored lowercased, never verified), the
locator-state law judged LIVE at read time (ready /
missing / not_a_file / unreadable; a state never stored),
the entry and list documents (schema tags, kind formats,
counts computed from the entries themselves, zero-filled),
owner scoping (foreign == unknown, existence never
leaks), remove hit/miss (a miss writes nothing), the
pure-data law (registering reads nothing at the locator
and creates nothing there), and the neighbours (migration
head stays 0041; KIND_FORMATS equal the pack layers' own
format constants). No network.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.hub import registry as hub
from runmal.lorebooks import packs as lorebook_packs
from runmal.plugins import service as plugin_service
from runmal.presets import bundles as preset_bundles
from runmal.presets import packs as prompt_packs
from runmal.scenarios import packs as scenario_packs

SHA = "a" * 64
SHA2 = "0123456789abcdef" * 4


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


# ------------------------------------------------------------ store


def test_register_stores_fields_verbatim_after_strip(tmp_path):
    store = make_store(tmp_path)
    entry = hub.register_entry(
        store, owner_id="u1", kind="lorebook_pack",
        title="  Waterdeep Lore  ", locator="  /packs/waterdeep.json  ",
        content_sha256=SHA.upper(), note="  from a friend  ")
    assert entry.title == "Waterdeep Lore"
    assert entry.locator == "/packs/waterdeep.json"
    assert entry.content_sha256 == SHA  # normalised lower
    assert entry.note == "from a friend"
    assert entry.to_dict()["format"] == "runmal-lorebook-pack"
    again = store.get_entry(entry.id)
    assert again == entry
    raw = json.loads((tmp_path / "data" / "hub.json").read_text())
    assert raw["version"] == 1 and len(raw["entries"]) == 1


def test_register_never_requires_the_locator_to_exist(tmp_path):
    store = make_store(tmp_path)
    ghost = tmp_path / "not-there.json"
    entry = hub.register_entry(
        store, owner_id="u1", kind="prompt_pack",
        title="Ghost pack", locator=str(ghost))
    assert entry.locator == str(ghost)
    assert not ghost.exists()  # registering created nothing


def test_register_refusals_store_nothing(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(hub.HubError):
        hub.register_entry(store, owner_id="u1", kind="lorebook_pack",
                           title="  ", locator="/x.json")
    with pytest.raises(hub.HubError):
        hub.register_entry(store, owner_id="u1", kind="lorebook_pack",
                           title="T", locator="   ")
    with pytest.raises(hub.HubError):
        hub.register_entry(store, owner_id="u1", kind="card_pack",
                           title="T", locator="/x.json")
    with pytest.raises(hub.HubError):
        hub.register_entry(store, owner_id="u1", kind="lorebook_pack",
                           title="T", locator="/x.json",
                           content_sha256="not-a-checksum")
    with pytest.raises(hub.HubError):
        hub.register_entry(store, owner_id="u1", kind="lorebook_pack",
                           title="T", locator="/x.json",
                           content_sha256="a" * 63)
    assert store.list_for_owner("u1") == []
    assert not (tmp_path / "data" / "hub.json").exists()


def test_duplicate_triple_refused_near_duplicates_allowed(tmp_path):
    store = make_store(tmp_path)
    hub.register_entry(store, owner_id="u1", kind="lorebook_pack",
                       title="One", locator="/packs/a.json")
    with pytest.raises(hub.HubError):
        hub.register_entry(store, owner_id="u1", kind="lorebook_pack",
                           title="Again", locator="/packs/a.json")
    assert len(store.list_for_owner("u1")) == 1
    # same locator, different kind: a different entry
    hub.register_entry(store, owner_id="u1", kind="prompt_pack",
                       title="Two", locator="/packs/a.json")
    # same locator + kind, different owner: a different entry
    hub.register_entry(store, owner_id="u2", kind="lorebook_pack",
                       title="Three", locator="/packs/a.json")
    assert len(store.list_for_owner("u1")) == 2
    assert len(store.list_for_owner("u2")) == 1


def test_checksum_optional_and_claimed_not_verified(tmp_path):
    store = make_store(tmp_path)
    bare = hub.register_entry(store, owner_id="u1", kind="scenario_pack",
                              title="No checksum", locator="/s.json")
    assert bare.content_sha256 == ""
    # a well-shaped checksum for a locator that does not exist is
    # stored as the caller's claim - the hub has read nothing
    claimed = hub.register_entry(
        store, owner_id="u1", kind="scenario_pack", title="Claimed",
        locator="/missing.json", content_sha256=SHA2)
    assert claimed.content_sha256 == SHA2
    doc = hub.entry_document(claimed)
    assert doc["locator_state"] == "missing"
    assert any("never" in n and "verified" in n for n in doc["notes"])


def test_tolerant_load_corrupt_store_reads_empty(tmp_path):
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "hub.json").write_text("{not json")
    store = hub.HubStore(data)
    assert store.list_for_owner("u1") == []
    (data / "hub.json").write_text(json.dumps(["not", "a", "dict"]))
    assert store.list_for_owner("u1") == []
    entry = hub.register_entry(store, owner_id="u1", kind="prompt_pack",
                               title="After", locator="/p.json")
    assert store.get_entry(entry.id) == entry


def test_remove_hit_and_miss_writes_nothing_on_miss(tmp_path):
    store = make_store(tmp_path)
    entry = hub.register_entry(store, owner_id="u1", kind="preset_bundle",
                               title="Bundle", locator="/b.json")
    path = tmp_path / "data" / "hub.json"
    before = path.read_bytes()
    assert store.remove_entry("no-such-id") is None
    assert path.read_bytes() == before  # a miss writes nothing
    removed = store.remove_entry(entry.id)
    assert removed == entry
    assert store.get_entry(entry.id) is None
    assert store.list_for_owner("u1") == []


# ------------------------------------------------------ locator law


def test_locator_states_judged_live(tmp_path):
    store = make_store(tmp_path)
    real = tmp_path / "pack.json"
    real.write_text("{}")
    folder = tmp_path / "dir"
    folder.mkdir()
    e_ready = hub.register_entry(store, owner_id="u1", kind="lorebook_pack",
                                 title="Ready", locator=str(real))
    e_missing = hub.register_entry(store, owner_id="u1", kind="lorebook_pack",
                                   title="Missing", locator=str(tmp_path / "gone.json"))
    e_dir = hub.register_entry(store, owner_id="u1", kind="lorebook_pack",
                               title="Dir", locator=str(folder))
    assert hub.locator_state(str(real)) == "ready"
    assert hub.entry_document(e_ready)["locator_state"] == "ready"
    assert hub.entry_document(e_missing)["locator_state"] == "missing"
    assert hub.entry_document(e_dir)["locator_state"] == "not_a_file"
    # judged live, never stored: create the file, the state changes
    (tmp_path / "gone.json").write_text("{}")
    assert hub.entry_document(e_missing)["locator_state"] == "ready"
    raw = json.loads((tmp_path / "data" / "hub.json").read_text())
    assert all("locator_state" not in row for row in raw["entries"])


def test_list_document_counts_from_the_entries(tmp_path):
    store = make_store(tmp_path)
    real = tmp_path / "pack.json"
    real.write_text("{}")
    hub.register_entry(store, owner_id="u1", kind="lorebook_pack",
                       title="A", locator=str(real))
    hub.register_entry(store, owner_id="u1", kind="lorebook_pack",
                       title="B", locator="/missing-b.json")
    hub.register_entry(store, owner_id="u1", kind="scenario_pack",
                       title="C", locator="/missing-c.json")
    hub.register_entry(store, owner_id="u2", kind="prompt_pack",
                       title="Foreign", locator="/f.json")
    doc = hub.list_document(store.list_for_owner("u1"))
    assert doc["schema"] == hub.LIST_SCHEMA
    assert doc["count"] == 3
    assert doc["by_kind"] == {
        "lorebook_pack": 2, "preset_bundle": 0,
        "prompt_pack": 0, "scenario_pack": 1}
    assert doc["by_locator_state"] == {
        "missing": 2, "not_a_file": 0, "ready": 1, "unreadable": 0}
    assert doc["kind_formats"] == hub.KIND_FORMATS
    assert [row["title"] for row in doc["entries"]] == ["A", "B", "C"]
    empty = hub.list_document([])
    assert empty["count"] == 0
    assert set(empty["by_kind"].values()) == {0}


def test_entry_document_shape(tmp_path):
    store = make_store(tmp_path)
    entry = hub.register_entry(store, owner_id="u1", kind="prompt_pack",
                               title="Doc", locator="/d.json")
    doc = hub.entry_document(entry)
    assert doc["schema"] == hub.ENTRY_SCHEMA
    assert doc["entry"]["id"] == entry.id
    assert doc["entry"]["format"] == "runmal-prompt-pack"
    assert doc["locator_state"] in hub.LOCATOR_STATES
    assert doc["notes"] == list(hub.NOTES)


# -------------------------------------------------------------- http


def test_http_register_read_list_remove(tmp_path):
    factory, client = _client(tmp_path)
    pack = tmp_path / "pack.json"
    pack.write_text("{}")
    made = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "HTTP Pack",
        "locator": str(pack), "content_sha256": SHA})
    assert made.status_code == 201, made.text
    doc = made.json()
    assert doc["locator_state"] == "ready"
    entry_id = doc["entry"]["id"]
    dupe = client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "Dupe", "locator": str(pack)})
    assert dupe.status_code == 422
    got = client.get(f"/api/v1/hub/entries/{entry_id}")
    assert got.status_code == 200 and got.json()["entry"]["id"] == entry_id
    listed = client.get("/api/v1/hub")
    assert listed.status_code == 200 and listed.json()["count"] == 1
    filtered = client.get("/api/v1/hub", params={"kind": "prompt_pack"})
    assert filtered.status_code == 200 and filtered.json()["count"] == 0
    bad_filter = client.get("/api/v1/hub", params={"kind": "card_pack"})
    assert bad_filter.status_code == 422
    gone = client.delete(f"/api/v1/hub/entries/{entry_id}")
    assert gone.status_code == 200 and gone.json() == {
        "deleted": True, "id": entry_id}
    assert client.get(f"/api/v1/hub/entries/{entry_id}").status_code == 404
    assert client.delete(f"/api/v1/hub/entries/{entry_id}").status_code == 404


def test_http_refusals_and_missing_locator_state(tmp_path):
    factory, client = _client(tmp_path)
    assert client.post("/api/v1/hub/entries", json={
        "kind": "card_pack", "title": "T",
        "locator": "/x.json"}).status_code == 422
    assert client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "  ",
        "locator": "/x.json"}).status_code == 422
    assert client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "T", "locator": "/x.json",
        "content_sha256": "zz"}).status_code == 422
    made = client.post("/api/v1/hub/entries", json={
        "kind": "scenario_pack", "title": "Ghost",
        "locator": str(tmp_path / "ghost.json")})
    assert made.status_code == 201
    assert made.json()["locator_state"] == "missing"  # state is data


def test_http_foreign_entry_answers_404(tmp_path):
    factory, client = _client(tmp_path)
    store = hub.HubStore(tmp_path / "data")
    foreign = hub.register_entry(store, owner_id="someone-else",
                                 kind="prompt_pack", title="Foreign",
                                 locator="/foreign.json")
    assert client.get(f"/api/v1/hub/entries/{foreign.id}").status_code == 404
    assert client.delete(f"/api/v1/hub/entries/{foreign.id}").status_code == 404
    listed = client.get("/api/v1/hub")
    assert listed.json()["count"] == 0  # foreign never listed
    assert store.get_entry(foreign.id) is not None  # and never removed


def test_http_requires_auth(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    assert client.get("/api/v1/hub").status_code == 401
    assert client.post("/api/v1/hub/entries", json={
        "kind": "lorebook_pack", "title": "T",
        "locator": "/x.json"}).status_code == 401


# ---------------------------------------------------------- neighbours


def test_kind_formats_match_the_pack_layers(tmp_path):
    assert hub.KIND_FORMATS["lorebook_pack"] == lorebook_packs.PACK_FORMAT
    assert hub.KIND_FORMATS["prompt_pack"] == prompt_packs.PACK_FORMAT
    assert hub.KIND_FORMATS["preset_bundle"] == preset_bundles.SHARE_FORMAT
    assert hub.KIND_FORMATS["scenario_pack"] == scenario_packs.PACK_FORMAT
    assert hub.HUB_KINDS == frozenset(hub.KIND_FORMATS)


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
