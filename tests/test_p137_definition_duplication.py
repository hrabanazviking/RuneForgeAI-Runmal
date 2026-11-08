"""P-137 — Scenario definition duplication (Part IX, DERIVED scope).

Pins: the faithful clone (definition deep-equal except
the name field, the P-131 import report deep-equal
EXACTLY — the preservation the composed P-133 export ->
P-131 create road provably cannot give, pinned here as
a contrast — and source_format preserved); the identity
law (fresh id, same owner, revision 1, one birth stamp,
the characters S303 " (copy)" name on the record and on
the definition's own name field alike, a copy of a copy
appending again); independence (a later replace on
either record leaves the other byte-untouched, the pair
surviving reload in store order); refusals (unknown and
foreign answer None / 404 indistinguishably and write
nothing); no carry (no organisation row — the clone
reads with the computed unorganised default — and no
binding; duplicating creates neither document); the
HTTP road (201 full record beside the untouched P-131
and P-026 roads); and the migration head pinned at
0041. No network: fixtures only.
"""

from __future__ import annotations

import copy
import json

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.scenarios.binding import ScenarioBindingStore
from runmal.scenarios.fileexport import export_native
from runmal.scenarios.fileimport import parse_scenario_file
from runmal.scenarios.organisation import (
    ScenarioOrganisationStore,
    organisation_view,
)
from runmal.scenarios.store import ScenarioStore, definitions_path
from runmal.scenarios.storedexport import export_stored_definition

NOW = "2026-11-08T14:00:00+00:00"
LATER = "2026-11-08T14:30:00+00:00"
OWNER = "owner-p137"
FOREIGN = "foreign-p137"

NATIVE_BODY = {
    "name": "Harbour Lights at Dusk",
    "description": "A quiet harbour, first evening.",
    "scenario_text": "The ferry has just left.",
    "flow": "story",
    "style": "storytelling",
    "narrator_name": "The Harbour Voice",
    "roles": [
        {
            "name": "Narrator",
            "character_name": "Maera",
            "enabled_on_start": True,
            "can_speak": True,
        }
    ],
    "bootstrap_messages": [
        {"kind": "note", "text": "The tide is going out.", "role": "Narrator"}
    ],
    "initial_flags": {"met_maera": True},
    "initial_variables": {"trust": 2},
}

VOXTA_BODY = {
    "name": "Vox Harbour",
    "chatFlow": "Story",
    "scenario": "A harbour, voiced.",
    "scripts": [{"code": "x=1"}],
}


def native_body() -> dict:
    return copy.deepcopy(NATIVE_BODY)


def voxta_body() -> dict:
    return copy.deepcopy(VOXTA_BODY)


def _store(tmp_path) -> ScenarioStore:
    return ScenarioStore(tmp_path / "scenarios.json")


def _without_name(definition: dict) -> dict:
    out = copy.deepcopy(definition)
    out.pop("name", None)
    return out


# ----------------------------------------------------- faithfulness


def test_duplicate_voxta_clone_is_faithful(tmp_path):
    store = _store(tmp_path)
    source = store.create(OWNER, voxta_body(), now=NOW)
    assert [u["kind"] for u in source.report["unmappable"]] == ["scripting"]
    clone = store.duplicate(source.id, OWNER, now=LATER)
    assert clone is not None
    # the report rides EXACTLY — every unmappable element
    # still named with its path / kind / name / reason
    assert clone.report == source.report
    assert clone.summary()["has_unmappable"] is True
    assert clone.source_format == "voxta" == source.source_format
    # the definition is deep-equal except the name field
    assert _without_name(clone.definition) == _without_name(source.definition)
    assert clone.definition["name"] == "Vox Harbour (copy)"


def test_duplicate_native_clone_is_faithful_and_fixed_point(tmp_path):
    store = _store(tmp_path)
    source = store.create(OWNER, native_body(), now=NOW)
    clone = store.duplicate(source.id, OWNER, now=LATER)
    assert clone is not None
    assert clone.report == source.report
    assert clone.source_format == "native"
    assert _without_name(clone.definition) == _without_name(source.definition)
    # the clone's stored definition is itself a P-026
    # fixed point, name included — it could re-enter the
    # store door whole
    assert export_native(parse_scenario_file(clone.definition)) == clone.definition


def test_clone_preserves_what_the_composed_road_loses(tmp_path):
    # The gap this slice closes, pinned as a contrast:
    # P-133 export (native) -> P-131 create reproduces
    # the definition but re-parses, so the new record's
    # report is a fresh native report that cannot name
    # the Voxta file's unmappable elements (P-133's
    # one-way naming law). The clone loses nothing.
    store = _store(tmp_path)
    source = store.create(OWNER, voxta_body(), now=NOW)
    file_dict, _report = export_stored_definition(source, "native")
    composed = store.create(OWNER, file_dict, now=LATER)
    assert composed.definition == source.definition
    assert composed.report != source.report
    assert composed.report["unmappable"] == []
    clone = store.duplicate(source.id, OWNER, now=LATER)
    assert clone is not None
    assert clone.report == source.report
    assert clone.report["unmappable"] != []


# ------------------------------------------------------ identity law


def test_duplicate_identity_law(tmp_path):
    store = _store(tmp_path)
    source = store.create(OWNER, native_body(), now=NOW)
    store.replace(source.id, OWNER, native_body(), now=NOW)  # revision 2
    source = store.get(source.id, OWNER)
    clone = store.duplicate(source.id, OWNER, now=LATER)
    assert clone is not None
    assert clone.id != source.id
    assert clone.owner_id == OWNER
    # a new citizen: the source's replace history is the
    # source's — the clone starts at revision 1 with one
    # birth stamp, not the source's created_at
    assert clone.revision == 1
    assert clone.created_at == LATER and clone.updated_at == LATER
    # the S303 name, on the record and in the definition
    assert clone.name == "Harbour Lights at Dusk (copy)"
    assert clone.definition["name"] == clone.name
    # appended in store order, and the pair survives reload
    assert [r.id for r in store.list_for_owner(OWNER)] == [source.id, clone.id]
    fresh = _store(tmp_path)
    assert fresh.get(clone.id, OWNER) == clone
    assert fresh.get(source.id, OWNER) == source


def test_duplicate_of_copy_appends_again(tmp_path):
    store = _store(tmp_path)
    source = store.create(OWNER, native_body(), now=NOW)
    clone = store.duplicate(source.id, OWNER, now=NOW)
    grandchild = store.duplicate(clone.id, OWNER, now=LATER)
    assert grandchild is not None
    # the S303 law applied to the source's own name —
    # never trimmed by an invented rule
    assert grandchild.name == "Harbour Lights at Dusk (copy) (copy)"
    assert grandchild.definition["name"] == grandchild.name
    assert grandchild.revision == 1
    assert grandchild.report == source.report


def test_duplicate_unknown_and_foreign_write_nothing(tmp_path):
    store = _store(tmp_path)
    source = store.create(OWNER, native_body(), now=NOW)
    before = (tmp_path / "scenarios.json").read_bytes()
    assert store.duplicate("no-such-id", OWNER, now=LATER) is None
    assert store.duplicate(source.id, FOREIGN, now=LATER) is None
    assert (tmp_path / "scenarios.json").read_bytes() == before
    assert [r.id for r in store.list_for_owner(OWNER)] == [source.id]


# ------------------------------------------------------ independence


def test_clone_and_source_are_independent(tmp_path):
    store = _store(tmp_path)
    source = store.create(OWNER, native_body(), now=NOW)
    clone = store.duplicate(source.id, OWNER, now=NOW)
    assert clone is not None
    changed = native_body()
    changed["name"] = "Second Evening"
    changed["initial_variables"] = {"trust": 9}
    store.replace(source.id, OWNER, changed, now=LATER)
    after = store.get(clone.id, OWNER)
    assert after == clone  # definition, report, revision untouched
    changed_back = native_body()
    changed_back["name"] = "Clone Rewritten"
    store.replace(clone.id, OWNER, changed_back, now=LATER)
    source_after = store.get(source.id, OWNER)
    assert source_after is not None
    assert source_after.name == "Second Evening"
    assert source_after.revision == 2
    assert store.get(clone.id, OWNER).revision == 2


def test_duplicate_carries_no_organisation_or_bindings(tmp_path):
    store = _store(tmp_path)
    source = store.create(OWNER, native_body(), now=NOW)
    org = ScenarioOrganisationStore(tmp_path / "scenario_organisation.json")
    org.set_tags(source.id, OWNER, ["harbour"])
    org.set_favourite(source.id, OWNER, True)
    org_before = (tmp_path / "scenario_organisation.json").read_bytes()
    clone = store.duplicate(source.id, OWNER, now=LATER)
    assert clone is not None
    # no organisation row is written for the clone: it
    # reads with P-134's computed unorganised default,
    # and the organisation document is byte-untouched
    assert org.get(clone.id, OWNER) is None
    view = organisation_view(clone, org.get(clone.id, OWNER))
    assert view["tags"] == [] and view["is_favourite"] is False
    assert (tmp_path / "scenario_organisation.json").read_bytes() == org_before
    # no binding is carried and no bindings document is
    # created by duplicating
    bindings = ScenarioBindingStore(tmp_path / "scenario_bindings.json")
    assert bindings.list_for_definition(clone.id, OWNER) == []
    assert bindings.list_for_owner(OWNER) == []
    assert not (tmp_path / "scenario_bindings.json").exists()


# -------------------------------------------------------------- HTTP


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    app = create_app(factory)
    client = TestClient(app)
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, db_path


def test_http_duplicate_201_and_get_and_list(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    mine = client.post("/api/v1/scenarios", json=voxta_body()).json()
    res = client.post(f"/api/v1/scenarios/{mine['id']}/duplicate")
    assert res.status_code == 201
    clone = res.json()
    assert clone["id"] != mine["id"]
    assert clone["owner_id"] == mine["owner_id"]
    assert clone["name"] == "Vox Harbour (copy)"
    assert clone["revision"] == 1
    assert clone["source_format"] == "voxta"
    # the faithful copy, over the wire as in the store
    assert clone["report"] == mine["report"]
    assert clone["report"]["unmappable"][0]["kind"] == "scripting"
    assert clone["definition"]["name"] == "Vox Harbour (copy)"
    got = client.get(f"/api/v1/scenarios/{clone['id']}")
    assert got.status_code == 200
    assert got.json() == clone
    listing = client.get("/api/v1/scenarios").json()
    assert listing["total"] == 2
    assert [s["id"] for s in listing["scenarios"]] == [mine["id"], clone["id"]]
    # the P-131 roads answer exactly as before beside it
    assert client.get(f"/api/v1/scenarios/{mine['id']}").status_code == 200


def test_http_duplicate_unknown_and_foreign_404(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    foreign = ScenarioStore(definitions_path()).create(
        FOREIGN, voxta_body(), now=NOW
    )
    assert client.post("/api/v1/scenarios/no-such-id/duplicate").status_code == 404
    assert client.post(f"/api/v1/scenarios/{foreign.id}/duplicate").status_code == 404
    # nothing was created for anyone
    assert client.get("/api/v1/scenarios").json()["total"] == 0
    assert ScenarioStore(definitions_path()).list_for_owner(FOREIGN) == [foreign]


def test_http_duplicate_creates_no_other_documents(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    mine = client.post("/api/v1/scenarios", json=native_body()).json()
    res = client.post(f"/api/v1/scenarios/{mine['id']}/duplicate")
    assert res.status_code == 201
    # only the definitions document exists in the data dir
    assert (tmp_path / "scenarios.json").exists()
    assert not (tmp_path / "scenario_organisation.json").exists()
    assert not (tmp_path / "scenario_bindings.json").exists()
    # the P-026 stateless roads are untouched beside it
    out = client.post("/api/v1/scenarios/import", json=voxta_body())
    assert out.status_code == 200
    assert out.json()["report"]["unmappable"][0]["kind"] == "scripting"


# ----------------------------------------------------- migration pin


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    assert MIGRATIONS[-1][0] == "0041"
    _client, db_path = make_client(tmp_path, monkeypatch)
    assert current_revision(db_path) == "0041"
    doc = json.loads((tmp_path / "scenarios.json").read_text()) if (
        tmp_path / "scenarios.json"
    ).exists() else None
    assert doc is None  # nothing written by merely building a client
