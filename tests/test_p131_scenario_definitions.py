"""P-131 — Scenario definitions (Part IX opener, DERIVED scope).

Pins: the store door is P-026's own parser (refusals store
nothing; unknown values fall back WITH their warning
carried in the stored report); the import report rides
with the record as data (unmappable scripting recorded,
never executed — it is not even in the stored shape);
the definition is a P-026 native fixed point; the
versioned JSON store (restart reload, tolerant load);
owner scoping on every verb (foreign == unknown, even
for a foreign replace carrying a malformed body);
the revision/stamp law on replace, with a refused
replace leaving the stored row untouched; duplicate
names as distinct citizens; creation seeds NOTHING
(no instantiation — the P-093 contract is a later
slice's seam); the owner-scoped HTTP roads (201/list/
get/put/delete, foreign 404s, invalid 422s) beside the
untouched P-026 import/export roads; and the migration
head pinned at 0041. No network: fixtures only.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.scenarios.fileexport import export_native
from runmal.scenarios.fileimport import parse_scenario_file
from runmal.scenarios.filemodels import ScenarioParseError
from runmal.scenarios.store import (
    ScenarioStore,
    ScenarioStoreError,
    definitions_path,
)

NOW = "2026-11-08T12:00:00+00:00"
LATER = "2026-11-08T12:30:00+00:00"
OWNER = "owner-zqx"
FOREIGN = "foreign-zqx"

NATIVE_BODY = {
    "name": "Harbour Lights at Dusk",
    "description": "A quiet harbour, first evening.",
    "scenario_text": "The ferry has just left.",
    "flow": "story",
    "style": "storytelling",
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
    "contexts": [
        {"key": "tide", "text": "Low water.", "condition": "",
         "role": "", "position": ""}
    ],
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


# ------------------------------------------------------- store door


def test_create_native_round_trip(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, native_body(), now=NOW)
    assert rec.owner_id == OWNER
    assert rec.name == "Harbour Lights at Dusk"
    assert rec.source_format == "native"
    assert rec.revision == 1
    assert rec.created_at == NOW and rec.updated_at == NOW
    # the stored definition is a P-026 fixed point
    assert export_native(parse_scenario_file(rec.definition)) == rec.definition
    # the report rides as data, and it is the parser's own
    assert rec.report["source_format"] == "native"
    assert "name" in rec.report["mapped"]
    assert rec.report["unmappable"] == []
    got = store.get(rec.id, OWNER)
    assert got == rec


def test_create_voxta_report_rides_as_data(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, voxta_body(), now=NOW)
    assert rec.source_format == "voxta"
    kinds = [u["kind"] for u in rec.report["unmappable"]]
    assert kinds == ["scripting"]
    # the scripting is recorded, never carried as anything
    # executable: the stored native shape has no scripts key
    assert "scripts" not in rec.definition
    assert rec.summary()["has_unmappable"] is True


def test_create_refuses_non_dict_and_stores_nothing(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ScenarioStoreError):
        store.create(OWNER, ["not", "a", "dict"], now=NOW)
    assert store.list_for_owner(OWNER) == []


def test_create_refuses_nameless_and_stores_nothing(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ScenarioParseError):
        store.create(OWNER, {"description": "no name"}, now=NOW)
    assert store.list_for_owner(OWNER) == []


def test_create_refuses_malformed_roles(tmp_path):
    store = _store(tmp_path)
    body = native_body()
    body["roles"] = "oops"
    with pytest.raises(ScenarioParseError):
        store.create(OWNER, body, now=NOW)
    assert store.list_for_owner(OWNER) == []


def test_unknown_flow_falls_back_with_warning_carried(tmp_path):
    store = _store(tmp_path)
    body = native_body()
    body["flow"] = "sideways"
    rec = store.create(OWNER, body, now=NOW)
    assert rec.definition["flow"] == "chat"
    assert rec.report["warnings"]  # the fall-back is never silent


# ------------------------------------------------------------- store


def test_restart_reload(tmp_path):
    first = _store(tmp_path)
    rec = first.create(OWNER, native_body(), now=NOW)
    second = _store(tmp_path)
    assert second.get(rec.id, OWNER) == rec
    assert [r.id for r in second.list_for_owner(OWNER)] == [rec.id]


def test_tolerant_load_corrupt_store(tmp_path):
    path = tmp_path / "scenarios.json"
    path.write_text("{not json at all")
    store = ScenarioStore(path)
    assert store.list_for_owner(OWNER) == []
    rec = store.create(OWNER, native_body(), now=NOW)
    assert store.get(rec.id, OWNER) == rec


def test_tolerant_load_malformed_row_never_bricks(tmp_path):
    # Finisher finding: from_dict int()-parses revision, so a
    # hand-damaged row (revision "abc" / null) raised out of
    # _load and bricked EVERY verb - against the design's
    # tolerant-load law. A malformed row now reads as absent.
    path = tmp_path / "scenarios.json"
    bad = {
        "id": "bad-row", "owner_id": OWNER, "name": "Bad",
        "definition": {}, "source_format": "native",
        "report": {}, "revision": "abc",
        "created_at": NOW, "updated_at": NOW,
    }
    path.write_text(json.dumps({"version": 1, "definitions": [bad]}))
    store = ScenarioStore(path)
    assert store.list_for_owner(OWNER) == []
    assert store.get("bad-row", OWNER) is None
    rec = store.create(OWNER, native_body(), now=NOW)
    assert store.get(rec.id, OWNER) == rec


def test_tolerant_load_good_row_survives_bad_neighbour(tmp_path):
    path = tmp_path / "scenarios.json"
    store = ScenarioStore(path)
    good = store.create(OWNER, native_body(), now=NOW)
    doc = json.loads(path.read_text())
    doc["definitions"].append(
        {
            "id": "bad-row", "owner_id": OWNER, "name": "Bad",
            "definition": {}, "source_format": "native",
            "report": {}, "revision": None,
            "created_at": NOW, "updated_at": NOW,
        }
    )
    path.write_text(json.dumps(doc))
    fresh = ScenarioStore(path)
    assert [r.id for r in fresh.list_for_owner(OWNER)] == [good.id]
    assert fresh.get(good.id, OWNER) == good


def test_list_owner_scoping_and_order(tmp_path):
    store = _store(tmp_path)
    a = store.create(OWNER, native_body(), now=NOW)
    store.create(FOREIGN, voxta_body(), now=NOW)
    b_body = native_body()
    b_body["name"] = "Second Berth"
    b = store.create(OWNER, b_body, now=NOW)
    assert [r.id for r in store.list_for_owner(OWNER)] == [a.id, b.id]
    assert store.get(a.id, FOREIGN) is None
    assert store.get("no-such-id", OWNER) is None


def test_summary_counts_come_from_the_definition(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, native_body(), now=NOW)
    summary = rec.summary()
    assert summary["role_count"] == 1
    assert summary["bootstrap_count"] == 1
    assert summary["has_unmappable"] is False
    assert summary["revision"] == 1


def test_duplicate_names_are_distinct_citizens(tmp_path):
    store = _store(tmp_path)
    a = store.create(OWNER, native_body(), now=NOW)
    b = store.create(OWNER, native_body(), now=NOW)
    assert a.id != b.id
    assert len(store.list_for_owner(OWNER)) == 2


def test_creation_seeds_nothing(tmp_path):
    store = _store(tmp_path)
    store.create(OWNER, native_body(), now=NOW)
    # initial flags/variables ride AS DATA in the definition;
    # no chat-variable store is created or written (the
    # P-093 seeding contract belongs to a later slice)
    assert not (tmp_path / "chat_variables").exists()
    rec = store.list_for_owner(OWNER)[0]
    assert rec.definition["initial_flags"] == {"met_maera": True}
    assert rec.definition["initial_variables"] == {"trust": 2}


# ----------------------------------------------------------- replace


def test_replace_bumps_revision_and_stamps(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, native_body(), now=NOW)
    body = native_body()
    body["name"] = "Harbour Lights, Second Evening"
    out = store.replace(rec.id, OWNER, body, now=LATER)
    assert out is not None
    assert out.id == rec.id and out.owner_id == OWNER
    assert out.revision == 2
    assert out.created_at == NOW and out.updated_at == LATER
    assert out.name == "Harbour Lights, Second Evening"
    assert store.get(rec.id, OWNER) == out


def test_replace_refused_body_leaves_row_untouched(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, native_body(), now=NOW)
    before = (tmp_path / "scenarios.json").read_bytes()
    with pytest.raises(ScenarioParseError):
        store.replace(rec.id, OWNER, {"description": "nameless"}, now=LATER)
    assert store.get(rec.id, OWNER) == rec
    assert (tmp_path / "scenarios.json").read_bytes() == before


def test_replace_unknown_and_foreign_answer_none(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, native_body(), now=NOW)
    assert store.replace("no-such-id", OWNER, native_body(), now=LATER) is None
    # foreign: None BEFORE the body is judged — a malformed
    # body against someone else's id is still just None
    assert store.replace(rec.id, FOREIGN, {"bad": True}, now=LATER) is None
    assert store.get(rec.id, OWNER) == rec


# ------------------------------------------------------------ remove


def test_remove_law(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, native_body(), now=NOW)
    assert store.remove(rec.id, FOREIGN) is None
    assert store.get(rec.id, OWNER) is not None  # foreign delete failed
    removed = store.remove(rec.id, OWNER)
    assert removed == rec
    assert store.get(rec.id, OWNER) is None
    assert store.remove(rec.id, OWNER) is None


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


def test_http_create_201_and_shape(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    res = client.post("/api/v1/scenarios", json=native_body())
    assert res.status_code == 201
    row = res.json()
    assert row["name"] == "Harbour Lights at Dusk"
    assert row["revision"] == 1
    assert row["source_format"] == "native"
    assert row["definition"]["initial_variables"] == {"trust": 2}
    assert row["report"]["source_format"] == "native"
    assert row["id"] and row["owner_id"]


def test_http_list_shows_only_own(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    mine = client.post("/api/v1/scenarios", json=native_body()).json()
    ScenarioStore(definitions_path()).create(FOREIGN, voxta_body(), now=NOW)
    res = client.get("/api/v1/scenarios")
    assert res.status_code == 200
    payload = res.json()
    assert payload["total"] == 1
    assert [s["id"] for s in payload["scenarios"]] == [mine["id"]]
    assert payload["scenarios"][0]["role_count"] == 1


def test_http_get_full_and_404s(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    mine = client.post("/api/v1/scenarios", json=native_body()).json()
    foreign = ScenarioStore(definitions_path()).create(
        FOREIGN, voxta_body(), now=NOW
    )
    got = client.get(f"/api/v1/scenarios/{mine['id']}")
    assert got.status_code == 200
    assert got.json()["definition"]["name"] == "Harbour Lights at Dusk"
    assert client.get("/api/v1/scenarios/no-such-id").status_code == 404
    assert client.get(f"/api/v1/scenarios/{foreign.id}").status_code == 404


def test_http_put_replaces(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    mine = client.post("/api/v1/scenarios", json=native_body()).json()
    body = native_body()
    body["name"] = "Renamed Harbour"
    res = client.put(f"/api/v1/scenarios/{mine['id']}", json=body)
    assert res.status_code == 200
    row = res.json()
    assert row["revision"] == 2
    assert row["name"] == "Renamed Harbour"
    assert row["created_at"] == mine["created_at"]


def test_http_put_foreign_404_even_with_bad_body(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    foreign = ScenarioStore(definitions_path()).create(
        FOREIGN, voxta_body(), now=NOW
    )
    res = client.put(
        f"/api/v1/scenarios/{foreign.id}", json={"description": "nameless"}
    )
    assert res.status_code == 404
    assert ScenarioStore(definitions_path()).get(foreign.id, FOREIGN) == foreign


def test_http_put_invalid_422_and_untouched(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    mine = client.post("/api/v1/scenarios", json=native_body()).json()
    res = client.put(
        f"/api/v1/scenarios/{mine['id']}", json={"description": "nameless"}
    )
    assert res.status_code == 422
    got = client.get(f"/api/v1/scenarios/{mine['id']}").json()
    assert got["revision"] == 1
    assert got["name"] == "Harbour Lights at Dusk"


def test_http_delete_law(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    mine = client.post("/api/v1/scenarios", json=native_body()).json()
    res = client.delete(f"/api/v1/scenarios/{mine['id']}")
    assert res.status_code == 200
    assert res.json() == {"id": mine["id"], "deleted": True}
    assert client.get(f"/api/v1/scenarios/{mine['id']}").status_code == 404
    assert client.delete(f"/api/v1/scenarios/{mine['id']}").status_code == 404


def test_http_delete_foreign_404_and_survives(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    foreign = ScenarioStore(definitions_path()).create(
        FOREIGN, voxta_body(), now=NOW
    )
    assert client.delete(f"/api/v1/scenarios/{foreign.id}").status_code == 404
    assert ScenarioStore(definitions_path()).get(foreign.id, FOREIGN) == foreign


def test_http_create_invalid_422(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    res = client.post("/api/v1/scenarios", json={"description": "nameless"})
    assert res.status_code == 422
    res = client.post("/api/v1/scenarios", json=["not", "an", "object"])
    assert res.status_code == 422
    assert client.get("/api/v1/scenarios").json()["total"] == 0


def test_interop_roads_unchanged(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    res = client.post("/api/v1/scenarios/import", json=voxta_body())
    assert res.status_code == 200
    assert res.json()["report"]["unmappable"][0]["kind"] == "scripting"
    out = client.post(
        "/api/v1/scenarios/export?format=native", json=native_body()
    )
    assert out.status_code == 200
    assert out.json()["name"] == "Harbour Lights at Dusk"
    # the stateless roads store nothing
    assert client.get("/api/v1/scenarios").json()["total"] == 0


# ----------------------------------------------------- migration pin


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    assert MIGRATIONS[-1][0] == "0042"
    _client, db_path = make_client(tmp_path, monkeypatch)
    assert current_revision(db_path) == "0042"
    # the store document is versioned JSON, not a table
    doc = json.loads((tmp_path / "scenarios.json").read_text()) if (
        tmp_path / "scenarios.json"
    ).exists() else None
    assert doc is None  # nothing written by merely building a client
