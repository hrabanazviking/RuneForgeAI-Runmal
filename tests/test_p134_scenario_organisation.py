"""P-134 — Scenario library organisation (Part IX, DERIVED scope).

Pins: the tag law is P-024's own (casefold identity, first
display wins — imported, never re-implemented); the
organisation store is its own versioned JSON document
(tolerant load, owner scoping, computed defaults never
persisted); the P-131 definitions document is byte-
untouched by organising; the query service (q search,
tag any/all, favourites, named sorts, limit/offset with
the filtered total before paging); orphan rows never
surface; the owner-scoped HTTP roads (library/tags not
swallowed by {definition_id}, existence before body
verdicts, 404 foreign/unknown, 422 invalid); the P-131
list default unchanged; migration head pinned at 0041.
No network: fixtures only.
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
from runmal.library.organise import normalise_tag
from runmal.scenarios.organisation import (
    ScenarioOrganisationError,
    ScenarioOrganisationStore,
    list_tags,
    organisation_path,
    query_definitions,
)
from runmal.scenarios.store import ScenarioStore, definitions_path

NOW = "2026-11-08T13:00:00+00:00"
LATER = "2026-11-08T13:30:00+00:00"
OWNER = "owner-q34"
FOREIGN = "foreign-q34"


def body(name, description="", text=""):
    return {
        "name": name,
        "description": description,
        "scenario_text": text,
        "flow": "story",
        "style": "storytelling",
        "roles": [],
        "bootstrap_messages": [],
    }


def _defs(tmp_path):
    return ScenarioStore(tmp_path / "scenarios.json")


def _org(tmp_path):
    return ScenarioOrganisationStore(tmp_path / "scenario_organisation.json")


def _three(tmp_path):
    store = _defs(tmp_path)
    a = store.create(OWNER, body("Harbour Lights", "A quiet harbour", "ferry"), now=NOW)
    b = store.create(OWNER, body("Mountain Gate", "High pass", "snow"), now=NOW)
    c = store.create(OWNER, body("harbour nights", "Another harbour", "tide"), now=NOW)
    return store, a, b, c


def _by_id(org, owner=OWNER):
    return {r.definition_id: r for r in org.list_for_owner(owner)}


# --------------------------------------------------------- tag law


def test_tag_law_is_p024s_law(tmp_path):
    org = _org(tmp_path)
    rec = org.set_tags("d1", OWNER, ["Sci Fi", "sci  fi", "SCI FI"], now=NOW)
    assert list(rec.tags) == ["Sci Fi"]
    assert normalise_tag("Sci Fi")[1] == normalise_tag("sci fi")[1]
    with pytest.raises(ScenarioOrganisationError):
        org.set_tags("d1", OWNER, [""], now=NOW)
    with pytest.raises(ScenarioOrganisationError):
        org.set_tags("d1", OWNER, "not-a-list", now=NOW)
    with pytest.raises(ScenarioOrganisationError):
        org.set_tags("d1", OWNER, ["x" * 65], now=NOW)


def test_set_add_remove_favourite_verbs(tmp_path):
    org = _org(tmp_path)
    org.set_tags("d1", OWNER, ["Harbour", "Calm"], now=NOW)
    rec = org.add_tags("d1", OWNER, ["harbour", "Storm"], now=LATER)
    assert list(rec.tags) == ["Harbour", "Calm", "Storm"]
    assert rec.updated_at == LATER
    rec = org.remove_tag("d1", OWNER, "CALM", now=LATER)
    assert list(rec.tags) == ["Harbour", "Storm"]
    rec = org.remove_tag("d1", OWNER, "absent", now=LATER)
    assert list(rec.tags) == ["Harbour", "Storm"]
    rec = org.set_favourite("d1", OWNER, True, now=LATER)
    assert rec.is_favourite is True and list(rec.tags) == ["Harbour", "Storm"]
    with pytest.raises(ScenarioOrganisationError):
        org.set_favourite("d1", OWNER, "yes", now=LATER)


def test_store_owner_scoping_and_tolerant_load(tmp_path):
    org = _org(tmp_path)
    org.set_tags("d1", OWNER, ["Mine"], now=NOW)
    org.set_tags("d1", FOREIGN, ["Theirs"], now=NOW)
    assert list(org.get("d1", OWNER).tags) == ["Mine"]
    assert org.get("nope", OWNER) is None
    path = tmp_path / "scenario_organisation.json"
    path.write_text("{corrupt")
    assert org.list_for_owner(OWNER) == []
    path.write_text(json.dumps({"version": 1, "organisations": [
        {"definition_id": "d1", "owner_id": OWNER, "tags": ["Ok"],
         "is_favourite": False, "updated_at": NOW},
        {"definition_id": 5},
        "junk",
    ]}))
    rows = org.list_for_owner(OWNER)
    assert [r.definition_id for r in rows] == ["d1"]


def test_organising_never_touches_definitions_document(tmp_path):
    store, a, _b, _c = _three(tmp_path)
    before = (tmp_path / "scenarios.json").read_bytes()
    org = _org(tmp_path)
    org.set_tags(a.id, OWNER, ["Harbour"], now=NOW)
    org.set_favourite(a.id, OWNER, True, now=NOW)
    assert (tmp_path / "scenarios.json").read_bytes() == before
    assert store.get(a.id, OWNER).definition == a.definition


# ------------------------------------------------------------- query


def test_query_defaults_creation_order_enriched(tmp_path):
    store, a, b, c = _three(tmp_path)
    org = _org(tmp_path)
    org.set_tags(b.id, OWNER, ["Pass"], now=NOW)
    page, total = query_definitions(store.list_for_owner(OWNER), _by_id(org))
    assert total == 3
    assert [r["id"] for r in page] == [a.id, b.id, c.id]
    assert page[0]["tags"] == [] and page[0]["is_favourite"] is False
    assert page[1]["tags"] == ["Pass"]
    assert page[0]["role_count"] == 0  # P-131 summary keys survive


def test_query_search_tags_favourites(tmp_path):
    store, a, b, c = _three(tmp_path)
    org = _org(tmp_path)
    org.set_tags(a.id, OWNER, ["Water", "Calm"], now=NOW)
    org.set_tags(c.id, OWNER, ["Water"], now=NOW)
    org.set_favourite(b.id, OWNER, True, now=NOW)
    defs = store.list_for_owner(OWNER)
    page, total = query_definitions(defs, _by_id(org), q="HARBOUR")
    assert total == 2 and [r["id"] for r in page] == [a.id, c.id]
    page, total = query_definitions(defs, _by_id(org), q="snow")
    assert [r["id"] for r in page] == [b.id]
    page, _ = query_definitions(defs, _by_id(org), tags=["water"], tag_mode="any")
    assert [r["id"] for r in page] == [a.id, c.id]
    page, _ = query_definitions(defs, _by_id(org), tags=["Water", "calm"], tag_mode="all")
    assert [r["id"] for r in page] == [a.id]
    page, _ = query_definitions(defs, _by_id(org), favourites_only=True)
    assert [r["id"] for r in page] == [b.id]


def test_query_sorts_and_paging(tmp_path):
    store, a, b, c = _three(tmp_path)
    org = _org(tmp_path)
    org.set_favourite(c.id, OWNER, True, now=NOW)
    defs = store.list_for_owner(OWNER)
    page, _ = query_definitions(defs, _by_id(org), sort="newest")
    assert [r["id"] for r in page] == [c.id, b.id, a.id]
    page, _ = query_definitions(defs, _by_id(org), sort="name")
    assert [r["name"] for r in page] == ["Harbour Lights", "harbour nights", "Mountain Gate"]
    page, _ = query_definitions(defs, _by_id(org), sort="favourites_first")
    assert page[0]["id"] == c.id
    page, total = query_definitions(defs, _by_id(org), limit=1, offset=1)
    assert total == 3 and [r["id"] for r in page] == [b.id]
    with pytest.raises(ScenarioOrganisationError):
        query_definitions(defs, _by_id(org), sort="bogus")
    with pytest.raises(ScenarioOrganisationError):
        query_definitions(defs, _by_id(org), tag_mode="bogus")
    with pytest.raises(ScenarioOrganisationError):
        query_definitions(defs, _by_id(org), limit=0)
    with pytest.raises(ScenarioOrganisationError):
        query_definitions(defs, _by_id(org), offset=-1)
    with pytest.raises(ScenarioOrganisationError):
        query_definitions(defs, _by_id(org), tags=[""])


def test_list_tags_census_and_orphans_never_surface(tmp_path):
    store, a, b, _c = _three(tmp_path)
    org = _org(tmp_path)
    org.set_tags(a.id, OWNER, ["Water"], now=NOW)
    org.set_tags(b.id, OWNER, ["water", "Pass"], now=NOW)
    org.set_tags("ghost-id", OWNER, ["Ghost"], now=NOW)
    census = list_tags(store.list_for_owner(OWNER), _by_id(org))
    assert census == [
        {"tag": "Pass", "key": "pass", "count": 1},
        {"tag": "Water", "key": "water", "count": 2},
    ]
    store.remove(a.id, OWNER)
    census = list_tags(store.list_for_owner(OWNER), _by_id(org))
    assert {row["key"] for row in census} == {"water", "pass"}
    assert [row for row in census if row["key"] == "water"][0]["count"] == 1


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


def _mk(client, name="Harbour Lights"):
    return client.post("/api/v1/scenarios", json=body(name, "A quiet harbour", "ferry")).json()


def test_http_organisation_roads(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    mine = _mk(client)
    res = client.get(f"/api/v1/scenarios/{mine['id']}/organisation")
    assert res.status_code == 200
    assert res.json() == {"definition_id": mine["id"], "name": "Harbour Lights",
                          "tags": [], "is_favourite": False}
    assert not (tmp_path / "scenario_organisation.json").exists()  # default not persisted
    res = client.put(f"/api/v1/scenarios/{mine['id']}/tags", json={"tags": ["Sci Fi", "Calm"]})
    assert res.status_code == 200 and res.json()["tags"] == ["Sci Fi", "Calm"]
    res = client.post(f"/api/v1/scenarios/{mine['id']}/tags", json={"tags": ["sci fi", "Storm"]})
    assert res.json()["tags"] == ["Sci Fi", "Calm", "Storm"]
    res = client.delete(f"/api/v1/scenarios/{mine['id']}/tags/calm")
    assert res.json()["tags"] == ["Sci Fi", "Storm"]
    res = client.put(f"/api/v1/scenarios/{mine['id']}/favourite", json={"is_favourite": True})
    assert res.json()["is_favourite"] is True
    res = client.get("/api/v1/scenarios/library/tags")
    assert res.status_code == 200
    assert {t["key"] for t in res.json()["tags"]} == {"sci fi", "storm"}


def test_http_refusals_existence_first(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    mine = _mk(client)
    ScenarioStore(definitions_path()).create(FOREIGN, body("Theirs"), now=NOW)
    foreign_id = ScenarioStore(definitions_path()).list_for_owner(FOREIGN)[0].id
    for target in (foreign_id, "no-such-id"):
        assert client.get(f"/api/v1/scenarios/{target}/organisation").status_code == 404
        assert client.put(f"/api/v1/scenarios/{target}/tags", json={"tags": [""]}).status_code == 404
        assert client.put(f"/api/v1/scenarios/{target}/favourite", json={"is_favourite": "x"}).status_code == 404
    assert client.put(f"/api/v1/scenarios/{mine['id']}/tags", json={"tags": [""]}).status_code == 422
    assert client.put(f"/api/v1/scenarios/{mine['id']}/favourite", json={"is_favourite": "x"}).status_code == 422
    assert client.get("/api/v1/scenarios", params={"sort": "bogus"}).status_code == 422
    assert client.get("/api/v1/scenarios", params={"tag_mode": "bogus"}).status_code == 422
    assert client.get("/api/v1/scenarios", params={"limit": 0}).status_code == 422


def test_http_list_surface_and_p131_default(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    first = _mk(client, "Harbour Lights")
    second = client.post("/api/v1/scenarios", json=body("Mountain Gate", "High pass", "snow")).json()
    res = client.get("/api/v1/scenarios")
    assert res.status_code == 200
    payload = res.json()
    assert payload["total"] == 2
    assert [s["id"] for s in payload["scenarios"]] == [first["id"], second["id"]]
    assert payload["scenarios"][0]["tags"] == []
    client.put(f"/api/v1/scenarios/{second['id']}/tags", json={"tags": ["Pass"]})
    client.put(f"/api/v1/scenarios/{second['id']}/favourite", json={"is_favourite": True})
    res = client.get("/api/v1/scenarios", params={"tag": "pass"})
    assert [s["id"] for s in res.json()["scenarios"]] == [second["id"]]
    res = client.get("/api/v1/scenarios", params={"favourites_only": "true"})
    assert [s["id"] for s in res.json()["scenarios"]] == [second["id"]]
    res = client.get("/api/v1/scenarios", params={"q": "harbour"})
    assert [s["id"] for s in res.json()["scenarios"]] == [first["id"]]
    res = client.get("/api/v1/scenarios", params={"limit": 1, "offset": 1})
    assert res.json()["total"] == 2 and len(res.json()["scenarios"]) == 1


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    assert MIGRATIONS[-1][0] == "0041"
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
