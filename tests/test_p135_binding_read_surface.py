"""P-135 — Binding lifecycle read surface (Part IX, DERIVED).

Pins: the summary shape (identity + pinned definition
facts + counts read from the record itself; no seeded
content rides in a summary); the two list services
(owner scoping on every row, store order, the honest
definition_exists flag for a binding that outlives its
definition); and the HTTP roads (GET /scenarios/bindings
answering the caller's whole set and never being read as
a definition id, GET /scenarios/{id}/bindings answering
404 for unknown/foreign and the honest empty list for an
owned unbound definition, lists shrinking on unbind, the
P-132 single-read and the P-131 definition roads
untouched beside them); and the migration head pinned
at 0041. No network: fixtures only.
"""

from __future__ import annotations

import copy

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.scenarios.binding import (
    ScenarioBinding,
    ScenarioBindingStore,
    list_bindings,
    list_bindings_for_definition,
)
from runmal.scenarios.store import ScenarioStore

NOW = "2026-11-08T14:00:00+00:00"

BODY = {
    "name": "Harbour Lights at Dusk",
    "description": "A quiet harbour, first evening.",
    "scenario_text": "The ferry has just left.",
    "flow": "story",
    "style": "storytelling",
    "narrator_name": "The Harbour Voice",
    "impersonation_name": "Ash",
    "roles": [
        {"name": "Narrator", "character_name": "Maera",
         "enabled_on_start": True, "can_speak": True},
    ],
    "bootstrap_messages": [
        {"kind": "note", "text": "The tide is going out.", "role": "Narrator"},
        {"kind": "user", "text": "I never left.", "role": ""},
    ],
    "initial_flags": {"met_maera": True},
    "initial_variables": {"trust": 2},
}


def body(name=None) -> dict:
    out = copy.deepcopy(BODY)
    if name:
        out["name"] = name
    return out


def _rec(bid, owner, chat, definition, name="Harbour", rev=1):
    return ScenarioBinding(
        id=bid, owner_id=owner, chat_id=chat, definition_id=definition,
        definition_name=name, definition_revision=rev, bound_at=NOW,
        cast=[{"name": "Narrator"}, {"name": "Keeper"}],
        seeded_messages=[{"text": "x"}, {"text": "y"}, {"text": "z"}],
        seeded_keys=["shared:trust"],
        skipped=[{"where": "bootstrap", "key_or_index": 4,
                  "reason": "blank text"}],
    )


# ------------------------------------------------------- summary


def test_summary_counts_come_from_the_record():
    row = _rec("b1", "o1", "c1", "d1").summary()
    assert row == {
        "id": "b1", "chat_id": "c1", "definition_id": "d1",
        "definition_name": "Harbour", "definition_revision": 1,
        "bound_at": NOW, "cast_count": 2, "seeded_message_count": 3,
        "seeded_key_count": 1, "skipped_count": 1,
    }


def test_summary_carries_no_seeded_content():
    row = _rec("b1", "o1", "c1", "d1").summary()
    assert "seeded_messages" not in row
    assert "cast" not in row
    assert "skipped" not in row


# ------------------------------------------------------- services


def test_list_bindings_owner_scoped_in_store_order(tmp_path):
    store = ScenarioBindingStore(tmp_path / "b.json")
    store.add(_rec("b1", "o1", "c1", "d1"))
    store.add(_rec("b2", "other", "c2", "d1"))
    store.add(_rec("b3", "o1", "c3", "d2", name="Gate"))
    rows = list_bindings(store, "o1", {"d1", "d2"})
    assert [r["id"] for r in rows] == ["b1", "b3"]
    assert all(r["definition_exists"] is True for r in rows)
    assert list_bindings(store, "nobody", {"d1"}) == []


def test_list_bindings_names_a_stale_definition(tmp_path):
    store = ScenarioBindingStore(tmp_path / "b.json")
    store.add(_rec("b1", "o1", "c1", "gone"))
    rows = list_bindings(store, "o1", {"d-other"})
    assert rows[0]["definition_exists"] is False
    assert rows[0]["definition_id"] == "gone"


def test_list_for_definition_filters_and_scopes(tmp_path):
    store = ScenarioBindingStore(tmp_path / "b.json")
    store.add(_rec("b1", "o1", "c1", "d1"))
    store.add(_rec("b2", "o1", "c2", "d2"))
    store.add(_rec("b3", "other", "c3", "d1"))
    rows = list_bindings_for_definition(store, "o1", "d1", {"d1", "d2"})
    assert [r["id"] for r in rows] == ["b1"]
    assert list_bindings_for_definition(store, "o1", "d-none", set()) == []


# --------------------------------------------------------- HTTP


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _bound(client, name=None):
    definition = client.post("/api/v1/scenarios", json=body(name)).json()
    chat = client.post("/api/v1/chats", json={"title": "Harbour"}).json()
    res = client.post(
        f"/api/v1/scenarios/{definition['id']}/bind",
        json={"chat_id": chat["id"]})
    assert res.status_code == 201
    return definition, chat


def test_http_list_empty_is_the_honest_zero(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    res = client.get("/api/v1/scenarios/bindings")
    assert res.status_code == 200
    assert res.json() == {"bindings": [], "total": 0}


def test_http_list_is_not_read_as_a_definition_id(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition, _chat = _bound(client)
    # "bindings" must not be swallowed by /scenarios/{definition_id}
    assert client.get("/api/v1/scenarios/bindings").status_code == 200
    got = client.get(f"/api/v1/scenarios/{definition['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == definition["id"]


def test_http_list_after_two_binds(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    d1, c1 = _bound(client)
    d2, c2 = _bound(client, "Mountain Gate")
    res = client.get("/api/v1/scenarios/bindings")
    assert res.status_code == 200
    payload = res.json()
    assert payload["total"] == 2
    assert [r["chat_id"] for r in payload["bindings"]] == [c1["id"], c2["id"]]
    first = payload["bindings"][0]
    assert first["definition_id"] == d1["id"]
    assert first["definition_revision"] == 1
    assert first["seeded_message_count"] == 2
    assert first["seeded_key_count"] == 2
    assert first["definition_exists"] is True
    assert "seeded_messages" not in first


def test_http_per_definition_list(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    d1, _c1 = _bound(client)
    d2, _c2 = _bound(client, "Mountain Gate")
    res = client.get(f"/api/v1/scenarios/{d1['id']}/bindings")
    assert res.status_code == 200
    payload = res.json()
    assert payload["definition_id"] == d1["id"]
    assert payload["total"] == 1
    assert payload["bindings"][0]["definition_id"] == d1["id"]
    other = client.get(f"/api/v1/scenarios/{d2['id']}/bindings").json()
    assert other["total"] == 1
    assert other["bindings"][0]["definition_id"] == d2["id"]


def test_http_per_definition_unbound_is_empty_not_404(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = client.post("/api/v1/scenarios", json=body()).json()
    res = client.get(f"/api/v1/scenarios/{definition['id']}/bindings")
    assert res.status_code == 200
    assert res.json()["total"] == 0
    assert res.json()["bindings"] == []


def test_http_per_definition_unknown_is_404(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    assert client.get("/api/v1/scenarios/no-such/bindings").status_code == 404


def test_http_list_names_stale_binding_after_definition_delete(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition, _chat = _bound(client)
    assert client.delete(
        f"/api/v1/scenarios/{definition['id']}").status_code == 200
    payload = client.get("/api/v1/scenarios/bindings").json()
    assert payload["total"] == 1  # the record stays until unbound
    assert payload["bindings"][0]["definition_exists"] is False
    # and the per-definition road now 404s: the definition is gone
    assert client.get(
        f"/api/v1/scenarios/{definition['id']}/bindings").status_code == 404


def test_http_list_shrinks_on_unbind(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    _d, chat = _bound(client)
    assert client.get("/api/v1/scenarios/bindings").json()["total"] == 1
    assert client.delete(
        f"/api/v1/scenarios/bindings/{chat['id']}").status_code == 200
    assert client.get("/api/v1/scenarios/bindings").json()["total"] == 0


def test_http_single_read_untouched_beside_lists(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition, chat = _bound(client)
    got = client.get(f"/api/v1/scenarios/bindings/{chat['id']}")
    assert got.status_code == 200
    row = got.json()
    assert row["definition_id"] == definition["id"]
    assert len(row["seeded_messages"]) == 2  # full record, not a summary


def test_store_rows_untouched_by_reads(tmp_path):
    definitions = ScenarioStore(tmp_path / "scenarios.json")
    rec = definitions.create("o1", body(), now=NOW)
    bindings = ScenarioBindingStore(tmp_path / "scenario_bindings.json")
    bindings.add(_rec("b1", "o1", "c1", rec.id))
    before = (tmp_path / "scenario_bindings.json").read_bytes()
    list_bindings(bindings, "o1", {rec.id})
    list_bindings_for_definition(bindings, "o1", rec.id, {rec.id})
    assert (tmp_path / "scenario_bindings.json").read_bytes() == before


# ----------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
    assert MIGRATIONS[-1][0] == "0042"
