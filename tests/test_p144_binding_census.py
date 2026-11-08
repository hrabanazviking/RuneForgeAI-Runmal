"""P-144 - Global binding census (Part IX, DERIVED).

Pins: the honest zero; the four states judged against
the live definition store (current; superseded after a
real replace; stale after a real delete; ahead from a
hand-written row - a damaged store named, never hidden);
rows as P-135 summaries verbatim plus the live facts and
the state; per-definition rollups and census counts
summed from the rows so they reconcile exactly; foreign
rows never counted; writes-nothing at service and HTTP
level (both store documents byte-untouched); and the
HTTP road (the literal census road winning over the
{chat_id} binding read, owner isolation, the P-135 /
P-132 neighbour roads untouched beside it); and the
migration head pinned at 0041. No network: fixtures only.
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
    bindings_path,
    list_bindings,
)
from runmal.scenarios.bindingcensus import census_bindings
from runmal.scenarios.store import ScenarioStore, definitions_path

NOW = "2026-11-08T18:00:00+00:00"
OWNER = "owner-p144"
FOREIGN = "foreign-p144"

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


def revised_body() -> dict:
    out = body()
    out["scenario_text"] = "The ferry has returned."
    return out


def _rec(bid, owner, chat, definition, name="Harbour", rev=1):
    return ScenarioBinding(
        id=bid, owner_id=owner, chat_id=chat, definition_id=definition,
        definition_name=name, definition_revision=rev, bound_at=NOW,
        cast=[{"name": "Narrator"}],
        seeded_messages=[{"message_id": "m1"}],
        seeded_keys=["shared:trust"],
        skipped=[],
    )


def _stores(tmp_path):
    definitions = ScenarioStore(tmp_path / "scenarios.json")
    bindings = ScenarioBindingStore(tmp_path / "scenario_bindings.json")
    return definitions, bindings


def _census(definitions, bindings, owner=OWNER):
    return census_bindings(
        bindings, owner, definitions.list_for_owner(owner))


ZERO_COUNTS = {
    "bindings_total": 0, "current": 0, "superseded": 0, "ahead": 0,
    "stale": 0, "chats_affected": 0, "definitions_referenced": 0,
    "definitions_with_current": 0, "definitions_with_superseded": 0,
    "definitions_with_stale": 0,
}


# ------------------------------------------------------- service


def test_service_no_bindings_is_the_honest_zero(tmp_path):
    definitions, bindings = _stores(tmp_path)
    definitions.create(OWNER, body(), now=NOW)
    out = _census(definitions, bindings)
    assert out["bindings"] == []
    assert out["by_definition"] == []
    assert out["counts"] == ZERO_COUNTS
    assert len(out["notes"]) == 5


def test_service_one_current_binding(tmp_path):
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    bindings.add(_rec("b1", OWNER, "chat-1", record.id,
                      name=record.name, rev=1))
    out = _census(definitions, bindings)
    assert out["counts"]["bindings_total"] == 1
    assert out["counts"]["current"] == 1
    assert out["counts"]["chats_affected"] == 1
    assert out["counts"]["definitions_referenced"] == 1
    assert out["counts"]["definitions_with_current"] == 1
    row = out["bindings"][0]
    assert row["state"] == "current"
    assert row["current_revision"] == 1
    assert row["current_name"] == "Harbour Lights at Dusk"
    assert row["definition_exists"] is True
    group = out["by_definition"][0]
    assert group["definition_id"] == record.id
    assert group["current"] == 1 and group["bindings_total"] == 1
    assert group["chat_ids"] == ["chat-1"]


def test_service_rows_are_p135_summaries_verbatim(tmp_path):
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    bindings.add(_rec("b1", OWNER, "chat-1", record.id,
                      name=record.name, rev=1))
    out = _census(definitions, bindings)
    plain = list_bindings(bindings, OWNER, {record.id})
    assert len(plain) == 1
    for key, value in plain[0].items():
        assert out["bindings"][0][key] == value
    assert set(out["bindings"][0]) - set(plain[0]) == {
        "current_revision", "current_name", "state"}


def test_service_superseded_after_a_real_replace(tmp_path):
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    bindings.add(_rec("b1", OWNER, "chat-1", record.id,
                      name=record.name, rev=1))
    definitions.replace(record.id, OWNER, revised_body(), now=NOW)
    out = _census(definitions, bindings)
    row = out["bindings"][0]
    assert row["state"] == "superseded"
    assert row["definition_revision"] == 1
    assert row["current_revision"] == 2
    assert row["definition_exists"] is True
    assert out["counts"]["superseded"] == 1
    assert out["counts"]["definitions_with_superseded"] == 1
    assert out["by_definition"][0]["superseded"] == 1


def test_service_stale_after_a_real_delete(tmp_path):
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    bindings.add(_rec("b1", OWNER, "chat-1", record.id,
                      name=record.name, rev=1))
    definitions.remove(record.id, OWNER)
    out = _census(definitions, bindings)
    row = out["bindings"][0]
    assert row["state"] == "stale"
    assert row["definition_exists"] is False
    assert row["current_revision"] is None
    assert row["current_name"] is None
    assert out["counts"]["stale"] == 1
    assert out["counts"]["definitions_with_stale"] == 1
    group = out["by_definition"][0]
    assert group["definition_exists"] is False
    assert group["current_revision"] is None
    # the group name falls back to the pinned name the
    # binding itself carries - the live record is gone
    assert group["definition_name"] == record.name


def test_service_ahead_row_is_named_never_hidden(tmp_path):
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    # a hand-damaged store: a pin newer than the live
    # revision is impossible by construction
    bindings.add(_rec("b1", OWNER, "chat-1", record.id,
                      name=record.name, rev=9))
    out = _census(definitions, bindings)
    row = out["bindings"][0]
    assert row["state"] == "ahead"
    assert row["definition_revision"] == 9
    assert row["current_revision"] == 1
    assert out["counts"]["ahead"] == 1
    assert out["by_definition"][0]["ahead"] == 1


def test_service_mixed_census_reconciles(tmp_path):
    definitions, bindings = _stores(tmp_path)
    first = definitions.create(OWNER, body("First"), now=NOW)
    second = definitions.create(OWNER, body("Second"), now=NOW)
    third = definitions.create(OWNER, body("Third"), now=NOW)
    bindings.add(_rec("b1", OWNER, "chat-1", first.id, rev=1))
    bindings.add(_rec("b2", OWNER, "chat-2", first.id, rev=1))
    bindings.add(_rec("b3", OWNER, "chat-3", second.id, rev=1))
    bindings.add(_rec("b4", OWNER, "chat-4", third.id, rev=1))
    definitions.replace(first.id, OWNER, revised_body(), now=NOW)
    bindings.add(_rec("b5", OWNER, "chat-5", first.id, rev=2))
    definitions.remove(third.id, OWNER)
    out = _census(definitions, bindings)
    counts = out["counts"]
    assert counts["bindings_total"] == 5
    assert counts["current"] == 2
    assert counts["superseded"] == 2
    assert counts["stale"] == 1
    assert counts["ahead"] == 0
    assert counts["chats_affected"] == 5
    assert counts["definitions_referenced"] == 3
    # the four states always reconcile with the total
    assert (counts["current"] + counts["superseded"]
            + counts["ahead"] + counts["stale"]) == 5
    groups = {g["definition_id"]: g for g in out["by_definition"]}
    assert groups[first.id]["superseded"] == 2
    assert groups[first.id]["current"] == 1
    assert groups[first.id]["chat_ids"] == ["chat-1", "chat-2", "chat-5"]
    assert groups[second.id]["current"] == 1
    assert groups[third.id]["stale"] == 1
    assert sum(g["bindings_total"] for g in groups.values()) == 5
    # groups appear in first-binding order
    assert [g["definition_id"] for g in out["by_definition"]] == [
        first.id, second.id, third.id]


def test_service_foreign_rows_never_counted(tmp_path):
    definitions, bindings = _stores(tmp_path)
    mine = definitions.create(OWNER, body(), now=NOW)
    theirs = definitions.create(FOREIGN, body(), now=NOW)
    bindings.add(_rec("b1", OWNER, "chat-1", mine.id, rev=1))
    bindings.add(_rec("b2", FOREIGN, "chat-2", theirs.id, rev=1))
    bindings.add(_rec("b3", FOREIGN, "chat-3", mine.id, rev=1))
    out = _census(definitions, bindings)
    assert out["counts"]["bindings_total"] == 1
    assert out["bindings"][0]["id"] == "b1"
    foreign = census_bindings(
        bindings, FOREIGN, definitions.list_for_owner(FOREIGN))
    assert foreign["counts"]["bindings_total"] == 2


def test_service_census_writes_nothing(tmp_path):
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    bindings.add(_rec("b1", OWNER, "chat-1", record.id, rev=1))
    before_defs = (tmp_path / "scenarios.json").read_bytes()
    before_binds = (tmp_path / "scenario_bindings.json").read_bytes()
    _census(definitions, bindings)
    assert (tmp_path / "scenarios.json").read_bytes() == before_defs
    assert (tmp_path / "scenario_bindings.json").read_bytes() == before_binds
    # and the census consumed nothing: the binding and
    # the definition still read back exactly
    assert bindings.get_for_chat("chat-1", OWNER) is not None
    assert definitions.get(record.id, OWNER) is not None


def test_service_definitions_argument_not_mutated(tmp_path):
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    bindings.add(_rec("b1", OWNER, "chat-1", record.id, rev=1))
    records = definitions.list_for_owner(OWNER)
    snapshot = [row.to_dict() for row in records]
    census_bindings(bindings, OWNER, records)
    assert [row.to_dict() for row in records] == snapshot


def test_service_notes_state_the_bounds(tmp_path):
    definitions, bindings = _stores(tmp_path)
    out = _census(definitions, bindings)
    notes = out["notes"]
    assert len(notes) == 5
    assert "written, unbound and cascaded" in notes[0]
    assert "unbound per" in notes[1] and "cleans nothing" in notes[1]
    assert "keeps the revision it pinned" in notes[2]
    assert "hand-damaged store" in notes[3]
    assert "judges no chat" in notes[4]


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


def _create(client):
    res = client.post("/api/v1/scenarios", json=body())
    assert res.status_code == 201
    return res.json()


def _bind(client, definition_id):
    chat = client.post("/api/v1/chats", json={"title": "Harbour"}).json()
    res = client.post(
        f"/api/v1/scenarios/{definition_id}/bind",
        json={"chat_id": chat["id"]})
    assert res.status_code == 201
    return chat


def test_http_zero_census(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    res = client.get("/api/v1/scenarios/bindings/census")
    assert res.status_code == 200
    out = res.json()
    assert out["bindings"] == []
    assert out["by_definition"] == []
    assert out["counts"] == ZERO_COUNTS
    assert len(out["notes"]) == 5


def test_http_census_across_real_acts(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    first = _create(client)
    chat_one = _bind(client, first["id"])
    res = client.put(f"/api/v1/scenarios/{first['id']}", json=revised_body())
    assert res.status_code == 200
    chat_two = _bind(client, first["id"])
    second = client.post("/api/v1/scenarios", json=body("Second")).json()
    chat_three = _bind(client, second["id"])
    res = client.delete(f"/api/v1/scenarios/{second['id']}")
    assert res.status_code == 200
    out = client.get("/api/v1/scenarios/bindings/census").json()
    counts = out["counts"]
    assert counts["bindings_total"] == 3
    assert counts["superseded"] == 1
    assert counts["current"] == 1
    assert counts["stale"] == 1
    assert counts["definitions_referenced"] == 2
    states = {row["chat_id"]: row["state"] for row in out["bindings"]}
    assert states[chat_one["id"]] == "superseded"
    assert states[chat_two["id"]] == "current"
    assert states[chat_three["id"]] == "stale"
    stale_row = next(
        row for row in out["bindings"] if row["state"] == "stale")
    assert stale_row["current_revision"] is None
    assert stale_row["definition_exists"] is False


def test_http_literal_census_not_a_chat_id(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _bind(client, definition["id"])
    # the census road answers the census, not a 404 from
    # the per-chat binding read for a chat named census
    res = client.get("/api/v1/scenarios/bindings/census")
    assert res.status_code == 200
    assert res.json()["counts"]["bindings_total"] == 1
    # and the real per-chat read still answers beside it
    got = client.get(f"/api/v1/scenarios/bindings/{chat['id']}")
    assert got.status_code == 200
    assert got.json()["chat_id"] == chat["id"]


def test_http_census_is_owner_scoped(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    _bind(client, definition["id"])
    # plant a foreign definition + binding directly in
    # the stores, as another owner truth
    store = ScenarioStore(definitions_path())
    foreign = store.create(FOREIGN, body(), now=NOW)
    bstore = ScenarioBindingStore(bindings_path())
    bstore.add(_rec("bf", FOREIGN, "chat-foreign", foreign.id, rev=1))
    out = client.get("/api/v1/scenarios/bindings/census").json()
    assert out["counts"]["bindings_total"] == 1
    assert all(
        row["definition_id"] != foreign.id for row in out["bindings"])
    assert all(
        g["definition_id"] != foreign.id for g in out["by_definition"])


def test_http_census_writes_nothing(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _bind(client, definition["id"])
    binds_file = tmp_path / "scenario_bindings.json"
    defs_file = tmp_path / "scenarios.json"
    before = (binds_file.read_bytes(), defs_file.read_bytes())
    assert client.get("/api/v1/scenarios/bindings/census").status_code == 200
    assert (binds_file.read_bytes(), defs_file.read_bytes()) == before
    history = client.get(f"/api/v1/chats/{chat['id']}/messages")
    assert history.status_code == 200
    assert len(history.json()) == 2


def test_http_neighbour_roads_untouched_beside_it(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _bind(client, definition["id"])
    base = f"/api/v1/scenarios/{definition['id']}"
    listing = client.get("/api/v1/scenarios/bindings")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert client.get(f"{base}/bindings").status_code == 200
    assert client.get(f"{base}/bind-plan").status_code == 200
    assert client.get(f"{base}/replace-impact").status_code == 200
    assert client.get(f"{base}/delete-impact").status_code == 200
    assert client.get(
        f"/api/v1/scenarios/bindings/{chat['id']}").status_code == 200
    assert client.get("/api/v1/scenarios/bindings/census").status_code == 200


# ----------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    assert MIGRATIONS[-1][0] == "0041"
