"""P-151 - Library definition census (Part IX, DERIVED).

Pins: the honest zero; definitions with no bindings
rowing as unbound (the one census a never-bound
definition appears in at all); the four binding custody
states judged by joining P-144's definition verdicts
and P-148's chat verdicts (sound beside a standing chat
at the current revision; definition_drift after a real
replace, and for a hand-damaged ahead pin;
chat_orphaned after a REAL chat deletion - delete_chat
leaves the binding document byte-untouched;
doubly_broken when both land); the definition-state
precedence with the row's per-state counts naming every
binding, so the precedence hides nothing; stale
bindings (definition deleted) counted in the totals
and rowing under no definition; foreign definitions
and bindings never rowed or counted; rows as P-131
summaries verbatim plus exactly the census keys;
counts summed from the rows so they reconcile exactly,
including the hand-damaged duplicate-chat-rows case
(bindings counted per row, chats counted distinct);
writes-nothing at service and HTTP level (both store
documents byte-untouched); and the HTTP road (the
literal library/census road answering beside the
P-134 / P-145 library roads and the P-144 / P-148
binding censuses, owner isolation, the state moving
unbound -> sound -> chat_orphaned across the live
flow); and the migration head pinned at 0041. No
network: fixtures only.
"""

from __future__ import annotations

import copy

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.scenarios.binding import (
    ScenarioBinding,
    ScenarioBindingStore,
    bind_scenario,
    bindings_path,
)
from runmal.scenarios.definitioncensus import (
    DEFINITION_CUSTODY_STATES,
    census_definitions,
)
from runmal.scenarios.store import ScenarioStore, definitions_path

NOW = "2026-11-08T21:00:00+00:00"
OWNER = "owner-p151"
FOREIGN = "foreign-p151"

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


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


async def make_chat(factory, user_id, title="Harbour"):
    async with factory() as session:
        chat = await svc.create_chat(session, user_id, title)
        return chat.id


async def _census(factory, tmp_path, owner):
    definitions, bindings = _stores(tmp_path)
    records = definitions.list_for_owner(owner)
    async with factory() as session:
        return await census_definitions(session, bindings, owner, records)


ZERO_COUNTS = {
    "definitions_total": 0, "definitions_unbound": 0,
    "definitions_sound": 0, "definitions_definition_drift": 0,
    "definitions_chat_orphaned": 0, "definitions_doubly_broken": 0,
    "bindings_total": 0, "bindings_on_live_definitions": 0,
    "bindings_stale": 0, "bindings_sound": 0,
    "bindings_definition_drift": 0, "bindings_chat_orphaned": 0,
    "bindings_doubly_broken": 0,
}

ADDED_KEYS = {
    "binding_count", "sound", "definition_drift", "chat_orphaned",
    "doubly_broken", "chats_bound", "chats_live", "state",
}


# ------------------------------------------------------- service


async def test_service_no_definitions_is_the_honest_zero(tmp_path):
    factory = make_factory(tmp_path)
    out = await _census(factory, tmp_path, OWNER)
    assert out["definitions"] == []
    assert out["counts"] == ZERO_COUNTS
    assert len(out["notes"]) == 5
    assert DEFINITION_CUSTODY_STATES == (
        "unbound", "sound", "definition_drift",
        "chat_orphaned", "doubly_broken")


async def test_service_definitions_without_bindings_are_unbound(tmp_path):
    factory = make_factory(tmp_path)
    definitions, _bindings = _stores(tmp_path)
    first = definitions.create(OWNER, body(), now=NOW)
    second = definitions.create(OWNER, body("Second"), now=NOW)
    out = await _census(factory, tmp_path, OWNER)
    assert [row["id"] for row in out["definitions"]] == [first.id, second.id]
    assert all(row["state"] == "unbound" for row in out["definitions"])
    assert all(row["binding_count"] == 0 for row in out["definitions"])
    assert out["counts"]["definitions_total"] == 2
    assert out["counts"]["definitions_unbound"] == 2
    assert out["counts"]["bindings_total"] == 0


async def test_service_one_sound_binding(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    out = await _census(factory, tmp_path, user)
    row = out["definitions"][0]
    assert row["state"] == "sound"
    assert row["binding_count"] == 1 and row["sound"] == 1
    assert row["chats_bound"] == 1 and row["chats_live"] == 1
    assert out["counts"]["definitions_sound"] == 1
    assert out["counts"]["bindings_sound"] == 1
    assert out["counts"]["bindings_on_live_definitions"] == 1


async def test_service_unbound_definition_rows_beside_a_sound_one(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    bound = definitions.create(user, body(), now=NOW)
    unbound = definitions.create(user, body("Unbound"), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, bound.id,
                      name=bound.name, rev=1))
    out = await _census(factory, tmp_path, user)
    rows = {row["id"]: row for row in out["definitions"]}
    # the never-bound definition appears in this census -
    # it appears in no binding census at all
    assert rows[unbound.id]["state"] == "unbound"
    assert rows[bound.id]["state"] == "sound"
    assert out["counts"]["definitions_unbound"] == 1
    assert out["counts"]["definitions_sound"] == 1


async def test_service_drift_after_a_real_replace(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    definitions.replace(record.id, user, revised_body(), now=NOW)
    out = await _census(factory, tmp_path, user)
    row = out["definitions"][0]
    assert row["state"] == "definition_drift"
    assert row["definition_drift"] == 1 and row["sound"] == 0
    assert row["chats_live"] == 1
    assert out["counts"]["bindings_definition_drift"] == 1


async def test_service_ahead_pin_is_drift(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    # hand-damaged store: a pin newer than the live
    # revision - impossible by construction, named drift
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=99))
    out = await _census(factory, tmp_path, user)
    assert out["definitions"][0]["state"] == "definition_drift"
    assert out["definitions"][0]["definition_drift"] == 1


async def test_service_orphaned_after_real_bind_and_delete(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    async with factory() as session:
        bound = await bind_scenario(
            session, user, record.id, chat_id,
            definitions=definitions, bindings=bindings,
            variables_base_dir=tmp_path, now=NOW)
    assert bound.chat_id == chat_id
    out = await _census(factory, tmp_path, user)
    assert out["definitions"][0]["state"] == "sound"
    binds_file = tmp_path / "scenario_bindings.json"
    before = binds_file.read_bytes()
    async with factory() as session:
        assert await svc.delete_chat(session, user, chat_id) is True
    assert binds_file.read_bytes() == before
    out = await _census(factory, tmp_path, user)
    row = out["definitions"][0]
    assert row["state"] == "chat_orphaned"
    assert row["chat_orphaned"] == 1
    assert row["chats_bound"] == 1 and row["chats_live"] == 0
    assert out["counts"]["definitions_chat_orphaned"] == 1


async def test_service_doubly_broken(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    definitions.replace(record.id, user, revised_body(), now=NOW)
    async with factory() as session:
        assert await svc.delete_chat(session, user, chat_id) is True
    out = await _census(factory, tmp_path, user)
    row = out["definitions"][0]
    assert row["state"] == "doubly_broken"
    assert row["doubly_broken"] == 1
    assert out["counts"]["definitions_doubly_broken"] == 1
    assert out["counts"]["bindings_doubly_broken"] == 1


async def test_service_precedence_names_every_binding(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    live_chat = await make_chat(factory, user, "Live")
    gone_chat = await make_chat(factory, user, "Gone")
    bindings.add(_rec("b1", user, live_chat, record.id,
                      name=record.name, rev=1))
    bindings.add(_rec("b2", user, gone_chat, record.id,
                      name=record.name, rev=1))
    async with factory() as session:
        assert await svc.delete_chat(session, user, gone_chat) is True
    out = await _census(factory, tmp_path, user)
    row = out["definitions"][0]
    # the precedence picks the strongest standing fact,
    # and the row's own counts name both bindings
    assert row["state"] == "chat_orphaned"
    assert row["sound"] == 1 and row["chat_orphaned"] == 1
    assert row["binding_count"] == 2
    assert row["chats_bound"] == 2 and row["chats_live"] == 1


async def test_service_stale_binding_is_counted_not_rowed(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    standing = definitions.create(user, body("Standing"), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    definitions.remove(record.id, user)
    out = await _census(factory, tmp_path, user)
    assert [row["id"] for row in out["definitions"]] == [standing.id]
    counts = out["counts"]
    assert counts["bindings_total"] == 1
    assert counts["bindings_stale"] == 1
    assert counts["bindings_on_live_definitions"] == 0
    assert counts["definitions_total"] == 1


async def test_service_foreign_rows_never_counted(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    foreign = definitions.create(FOREIGN, body("Foreign"), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    bindings.add(_rec("bf", FOREIGN, "chat-foreign", foreign.id, rev=1))
    out = await _census(factory, tmp_path, user)
    assert [row["id"] for row in out["definitions"]] == [record.id]
    assert out["counts"]["bindings_total"] == 1
    out = await _census(factory, tmp_path, FOREIGN)
    assert [row["id"] for row in out["definitions"]] == [foreign.id]
    assert out["definitions"][0]["state"] == "chat_orphaned"


async def test_service_rows_are_p131_summaries_verbatim(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    out = await _census(factory, tmp_path, user)
    row = out["definitions"][0]
    stripped = {
        key: value for key, value in row.items() if key not in ADDED_KEYS
    }
    assert stripped == record.summary()
    assert set(row) == set(record.summary()) | ADDED_KEYS


async def test_service_counts_reconcile_and_chats_are_distinct(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    first = definitions.create(user, body(), now=NOW)
    second = definitions.create(user, body("Second"), now=NOW)
    chat_id = await make_chat(factory, user)
    # hand-damaged store: two rows for one chat on one
    # definition (bind forbids it) - rows count per row,
    # chats count distinct
    bindings.add(_rec("b1", user, chat_id, first.id,
                      name=first.name, rev=1))
    bindings.add(_rec("b2", user, chat_id, first.id,
                      name=first.name, rev=1))
    bindings.add(_rec("b3", user, "chat-ghost", second.id,
                      name=second.name, rev=1))
    out = await _census(factory, tmp_path, user)
    counts = out["counts"]
    rows = {row["id"]: row for row in out["definitions"]}
    assert rows[first.id]["binding_count"] == 2
    assert rows[first.id]["chats_bound"] == 1
    assert rows[first.id]["sound"] == 2
    assert rows[second.id]["state"] == "chat_orphaned"
    assert counts["bindings_total"] == 3
    assert counts["bindings_on_live_definitions"] == 3
    assert counts["bindings_sound"] == 2
    assert counts["bindings_chat_orphaned"] == 1
    assert counts["bindings_sound"] + counts["bindings_definition_drift"] \
        + counts["bindings_chat_orphaned"] \
        + counts["bindings_doubly_broken"] \
        == counts["bindings_on_live_definitions"]
    assert counts["definitions_total"] == 2
    assert counts["definitions_unbound"] + counts["definitions_sound"] \
        + counts["definitions_definition_drift"] \
        + counts["definitions_chat_orphaned"] \
        + counts["definitions_doubly_broken"] \
        == counts["definitions_total"]
    for row in out["definitions"]:
        assert row["sound"] + row["definition_drift"] \
            + row["chat_orphaned"] + row["doubly_broken"] \
            == row["binding_count"]


async def test_service_census_writes_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    binds_file = tmp_path / "scenario_bindings.json"
    defs_file = tmp_path / "scenarios.json"
    before = (binds_file.read_bytes(), defs_file.read_bytes())
    await _census(factory, tmp_path, user)
    assert (binds_file.read_bytes(), defs_file.read_bytes()) == before


# ---------------------------------------------------------- HTTP


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
    res = client.get("/api/v1/scenarios/library/census")
    assert res.status_code == 200
    out = res.json()
    assert out["definitions"] == []
    assert out["counts"] == ZERO_COUNTS
    assert len(out["notes"]) == 5


def test_http_state_moves_unbound_sound_orphaned(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    other = _create(client)
    out = client.get("/api/v1/scenarios/library/census").json()
    assert out["counts"]["definitions_unbound"] == 2
    chat = _bind(client, definition["id"])
    out = client.get("/api/v1/scenarios/library/census").json()
    rows = {row["id"]: row for row in out["definitions"]}
    assert rows[definition["id"]]["state"] == "sound"
    assert rows[other["id"]]["state"] == "unbound"
    res = client.delete(f"/api/v1/chats/{chat['id']}")
    assert res.status_code == 200
    out = client.get("/api/v1/scenarios/library/census").json()
    rows = {row["id"]: row for row in out["definitions"]}
    assert rows[definition["id"]]["state"] == "chat_orphaned"
    assert rows[definition["id"]]["chats_live"] == 0
    # the standing unbind road still removes the named
    # orphan, and the definition reads unbound again
    res = client.delete(f"/api/v1/scenarios/bindings/{chat['id']}")
    assert res.status_code == 200
    out = client.get("/api/v1/scenarios/library/census").json()
    rows = {row["id"]: row for row in out["definitions"]}
    assert rows[definition["id"]]["state"] == "unbound"


def test_http_census_is_owner_scoped(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    _bind(client, definition["id"])
    store = ScenarioStore(definitions_path())
    foreign = store.create(FOREIGN, body(), now=NOW)
    bstore = ScenarioBindingStore(bindings_path())
    bstore.add(_rec("bf", FOREIGN, "chat-foreign", foreign.id, rev=1))
    out = client.get("/api/v1/scenarios/library/census").json()
    assert out["counts"]["definitions_total"] == 1
    assert out["counts"]["bindings_total"] == 1
    assert all(
        row["id"] != foreign.id for row in out["definitions"])


def test_http_census_writes_nothing(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _bind(client, definition["id"])
    binds_file = tmp_path / "scenario_bindings.json"
    defs_file = tmp_path / "scenarios.json"
    before = (binds_file.read_bytes(), defs_file.read_bytes())
    res = client.get("/api/v1/scenarios/library/census")
    assert res.status_code == 200
    assert (binds_file.read_bytes(), defs_file.read_bytes()) == before
    history = client.get(f"/api/v1/chats/{chat['id']}/messages")
    assert history.status_code == 200
    assert len(history.json()) == 2


def test_http_neighbour_roads_untouched_beside_it(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _bind(client, definition["id"])
    base = f"/api/v1/scenarios/{definition['id']}"
    assert client.get("/api/v1/scenarios/library/tags").status_code == 200
    assert client.get(
        "/api/v1/scenarios/library/unmappable").status_code == 200
    assert client.get("/api/v1/scenarios/library/census").status_code == 200
    assert client.get("/api/v1/scenarios/bindings").status_code == 200
    assert client.get(
        "/api/v1/scenarios/bindings/census").status_code == 200
    assert client.get(
        "/api/v1/scenarios/bindings/chat-census").status_code == 200
    assert client.get(f"{base}/bindings").status_code == 200
    assert client.get(f"{base}/delete-impact").status_code == 200
    assert client.get(
        f"/api/v1/scenarios/bindings/{chat['id']}").status_code == 200
    # "library" is never read as a definition id
    assert client.get("/api/v1/scenarios/library").status_code == 404


# ----------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    assert MIGRATIONS[-1][0] == "0041"
