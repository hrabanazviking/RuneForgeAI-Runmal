"""P-150 - Binding custody census, both axes (Part IX, DERIVED).

Pins: the honest zero; the four custody states as the
plain conjunction of the two standing verdicts (sound =
current + live; definition_drift = superseded, ahead or
stale beside a standing chat; chat_orphaned = a current
pin whose chat is gone; doubly_broken = both axes broken
at once, reached by a REAL bind followed by a REAL chat
deletion and a REAL definition deletion, the binding
document byte-untouched by both); the ahead hand-damage
named as drift, never hidden; existence judged
owner-scoped (another owner's chat reads orphaned for the
caller and live for its owner); foreign binding rows never
counted; joined rows as the P-144 census row verbatim plus
exactly the P-148 pair and the custody key, with both
parent verdicts equal to the parent censuses' own;
per-definition rollups and census counts summed from the
rows so they reconcile exactly, chats counted distinct
under the hand-damaged duplicate-rows case; writes-nothing
at service and HTTP level (both store documents
byte-untouched, chat history untouched); and the HTTP road
(the literal custody-census road winning over the {chat_id}
binding read, the named doubly-broken binding still
removable by the standing unbind road, owner isolation,
the P-144 / P-148 neighbour census roads untouched beside
it); and the migration head pinned at 0041. No network:
fixtures only.
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
from runmal.scenarios.bindingcensus import census_bindings
from runmal.scenarios.chatcensus import census_binding_chats
from runmal.scenarios.custodycensus import (
    CUSTODY_STATES,
    census_binding_custody,
)
from runmal.scenarios.store import ScenarioStore, definitions_path

NOW = "2026-11-08T21:00:00+00:00"
OWNER = "owner-p150"
FOREIGN = "foreign-p150"

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


async def _custody(factory, tmp_path, owner):
    definitions, bindings = _stores(tmp_path)
    records = definitions.list_for_owner(owner)
    async with factory() as session:
        return await census_binding_custody(
            session, bindings, owner, records)


ZERO_COUNTS = {
    "bindings_total": 0, "current": 0, "superseded": 0,
    "ahead": 0, "stale": 0, "live": 0, "orphaned": 0,
    "sound": 0, "definition_drift": 0, "chat_orphaned": 0,
    "doubly_broken": 0, "chats_live": 0, "chats_orphaned": 0,
    "definitions_referenced": 0, "definitions_with_sound": 0,
    "definitions_with_definition_drift": 0,
    "definitions_with_chat_orphaned": 0,
    "definitions_with_doubly_broken": 0,
}


# ------------------------------------------------------- service


async def test_service_no_bindings_is_the_honest_zero(tmp_path):
    factory = make_factory(tmp_path)
    definitions, _bindings = _stores(tmp_path)
    definitions.create(OWNER, body(), now=NOW)
    out = await _custody(factory, tmp_path, OWNER)
    assert out["bindings"] == []
    assert out["by_definition"] == []
    assert out["counts"] == ZERO_COUNTS
    assert len(out["notes"]) == 5
    assert CUSTODY_STATES == (
        "sound", "definition_drift", "chat_orphaned", "doubly_broken")


async def test_service_one_sound_binding(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    out = await _custody(factory, tmp_path, user)
    counts = out["counts"]
    assert counts["bindings_total"] == 1
    assert counts["sound"] == 1 and counts["current"] == 1
    assert counts["live"] == 1 and counts["chats_live"] == 1
    assert counts["definitions_with_sound"] == 1
    row = out["bindings"][0]
    assert row["state"] == "current" and row["chat_state"] == "live"
    assert row["chat_exists"] is True
    assert row["custody_state"] == "sound"
    group = out["by_definition"][0]
    assert group["definition_id"] == record.id
    assert group["sound"] == 1 and group["doubly_broken"] == 0
    assert group["chat_ids"] == [chat_id]


async def test_service_superseded_pin_beside_live_chat_is_drift(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    definitions.replace(record.id, user, revised_body(), now=NOW)
    out = await _custody(factory, tmp_path, user)
    row = out["bindings"][0]
    assert row["state"] == "superseded" and row["chat_state"] == "live"
    assert row["custody_state"] == "definition_drift"
    assert out["counts"]["definition_drift"] == 1
    assert out["counts"]["superseded"] == 1
    assert out["counts"]["definitions_with_definition_drift"] == 1


async def test_service_stale_beside_live_chat_is_drift(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    definitions.remove(record.id, user)
    out = await _custody(factory, tmp_path, user)
    row = out["bindings"][0]
    assert row["state"] == "stale" and row["chat_state"] == "live"
    assert row["definition_exists"] is False
    assert row["custody_state"] == "definition_drift"
    assert out["counts"]["stale"] == 1


async def test_service_current_pin_with_gone_chat_is_chat_orphaned(tmp_path):
    factory = make_factory(tmp_path)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    bindings.add(_rec("b1", OWNER, "chat-ghost", record.id,
                      name=record.name, rev=1))
    out = await _custody(factory, tmp_path, OWNER)
    row = out["bindings"][0]
    assert row["state"] == "current" and row["chat_state"] == "orphaned"
    assert row["chat_exists"] is False
    assert row["custody_state"] == "chat_orphaned"
    assert out["counts"]["chat_orphaned"] == 1
    assert out["counts"]["chats_orphaned"] == 1
    assert out["counts"]["definitions_with_chat_orphaned"] == 1


async def test_service_doubly_broken_after_real_bind_and_deletes(tmp_path):
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
    out = await _custody(factory, tmp_path, user)
    assert out["bindings"][0]["custody_state"] == "sound"
    binds_file = tmp_path / "scenario_bindings.json"
    before = binds_file.read_bytes()
    async with factory() as session:
        assert await svc.delete_chat(session, user, chat_id) is True
    assert binds_file.read_bytes() == before
    out = await _custody(factory, tmp_path, user)
    assert out["bindings"][0]["custody_state"] == "chat_orphaned"
    definitions.remove(record.id, user)
    assert binds_file.read_bytes() == before
    out = await _custody(factory, tmp_path, user)
    row = out["bindings"][0]
    assert row["state"] == "stale" and row["chat_state"] == "orphaned"
    assert row["custody_state"] == "doubly_broken"
    assert out["counts"]["doubly_broken"] == 1
    assert out["counts"]["definitions_with_doubly_broken"] == 1


async def test_service_superseded_and_orphaned_is_doubly_broken(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    bindings.add(_rec("b1", user, "chat-ghost", record.id,
                      name=record.name, rev=1))
    definitions.replace(record.id, user, revised_body(), now=NOW)
    out = await _custody(factory, tmp_path, user)
    row = out["bindings"][0]
    assert row["state"] == "superseded"
    assert row["chat_state"] == "orphaned"
    assert row["custody_state"] == "doubly_broken"


async def test_service_ahead_hand_damage_is_named_as_drift(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    # hand-damaged store: a pin newer than the live revision
    # (impossible by construction) - named, never hidden
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=5))
    out = await _custody(factory, tmp_path, user)
    row = out["bindings"][0]
    assert row["state"] == "ahead"
    assert row["custody_state"] == "definition_drift"
    assert out["counts"]["ahead"] == 1


async def test_service_foreign_chat_flips_custody_by_caller(tmp_path):
    factory = make_factory(tmp_path)
    mine = await make_user(factory, "mine")
    theirs = await make_user(factory, "theirs")
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(mine, body(), now=NOW)
    their_record = definitions.create(theirs, body("Theirs"), now=NOW)
    chat_id = await make_chat(factory, theirs)
    bindings.add(_rec("b1", mine, chat_id, record.id,
                      name=record.name, rev=1))
    bindings.add(_rec("b2", theirs, chat_id, their_record.id,
                      name=their_record.name, rev=1))
    out = await _custody(factory, tmp_path, mine)
    assert out["counts"]["bindings_total"] == 1
    assert out["bindings"][0]["custody_state"] == "chat_orphaned"
    out = await _custody(factory, tmp_path, theirs)
    assert out["counts"]["bindings_total"] == 1
    assert out["bindings"][0]["custody_state"] == "sound"


async def test_service_foreign_binding_rows_never_counted(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    foreign_record = definitions.create(FOREIGN, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    bindings.add(_rec("bf", FOREIGN, "chat-foreign", foreign_record.id,
                      rev=1))
    out = await _custody(factory, tmp_path, user)
    assert out["counts"]["bindings_total"] == 1
    assert all(
        row["definition_id"] != foreign_record.id
        for row in out["bindings"])


async def test_service_rows_join_both_parents_verbatim(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    first = definitions.create(user, body(), now=NOW)
    second = definitions.create(user, body("Second"), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, first.id,
                      name=first.name, rev=1))
    bindings.add(_rec("b2", user, "chat-ghost", second.id,
                      name=second.name, rev=1))
    definitions.replace(second.id, user, revised_body(), now=NOW)
    records = definitions.list_for_owner(user)
    live = {row.id for row in records}
    parent_def = census_bindings(bindings, user, records)
    async with factory() as session:
        parent_chat = await census_binding_chats(
            session, bindings, user, live)
        out = await census_binding_custody(session, bindings, user, records)
    assert len(out["bindings"]) == len(parent_def["bindings"])
    chat_by_id = {row["id"]: row for row in parent_chat["bindings"]}
    for row, parent in zip(
            out["bindings"], parent_def["bindings"], strict=True):
        stripped = {
            key: value for key, value in row.items()
            if key not in ("chat_exists", "chat_state", "custody_state")
        }
        assert stripped == parent
        assert row["chat_exists"] == chat_by_id[row["id"]]["chat_exists"]
        assert row["chat_state"] == chat_by_id[row["id"]]["chat_state"]
    # and the parent censuses' own counts ride through whole
    for key in ("current", "superseded", "ahead", "stale"):
        assert out["counts"][key] == parent_def["counts"][key]
    for key in ("live", "orphaned", "chats_live", "chats_orphaned"):
        assert out["counts"][key] == parent_chat["counts"][key]


async def test_service_counts_reconcile_and_chats_are_distinct(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    first = definitions.create(user, body(), now=NOW)
    second = definitions.create(user, body("Second"), now=NOW)
    chat_id = await make_chat(factory, user)
    # hand-damaged store: two rows for one chat (bind forbids it)
    bindings.add(_rec("b1", user, chat_id, first.id,
                      name=first.name, rev=1))
    bindings.add(_rec("b2", user, chat_id, second.id,
                      name=second.name, rev=1))
    bindings.add(_rec("b3", user, "chat-ghost", first.id,
                      name=first.name, rev=1))
    definitions.remove(second.id, user)
    out = await _custody(factory, tmp_path, user)
    counts = out["counts"]
    assert counts["bindings_total"] == 3
    assert counts["sound"] == 1
    assert counts["definition_drift"] == 1
    assert counts["chat_orphaned"] == 1
    assert counts["doubly_broken"] == 0
    assert (counts["sound"] + counts["definition_drift"]
            + counts["chat_orphaned"] + counts["doubly_broken"]
            == counts["bindings_total"])
    assert counts["current"] + counts["superseded"] + counts["ahead"] \
        + counts["stale"] == counts["bindings_total"]
    assert counts["live"] + counts["orphaned"] == counts["bindings_total"]
    assert counts["chats_live"] == 1 and counts["chats_orphaned"] == 1
    assert counts["definitions_referenced"] == 2
    groups = {g["definition_id"]: g for g in out["by_definition"]}
    assert groups[first.id]["bindings_total"] == 2
    assert groups[first.id]["sound"] == 1
    assert groups[first.id]["chat_orphaned"] == 1
    assert groups[first.id]["chat_ids"] == [chat_id, "chat-ghost"]
    assert groups[second.id]["definition_drift"] == 1
    for group in out["by_definition"]:
        assert (group["sound"] + group["definition_drift"]
                + group["chat_orphaned"] + group["doubly_broken"]
                == group["bindings_total"])


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
    await _custody(factory, tmp_path, user)
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
    res = client.get("/api/v1/scenarios/bindings/custody-census")
    assert res.status_code == 200
    out = res.json()
    assert out["bindings"] == []
    assert out["by_definition"] == []
    assert out["counts"] == ZERO_COUNTS
    assert len(out["notes"]) == 5


def test_http_sound_then_orphaned_then_doubly_then_unbound(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _bind(client, definition["id"])
    out = client.get("/api/v1/scenarios/bindings/custody-census").json()
    assert out["counts"]["sound"] == 1
    assert out["bindings"][0]["custody_state"] == "sound"
    res = client.delete(f"/api/v1/chats/{chat['id']}")
    assert res.status_code == 200
    out = client.get("/api/v1/scenarios/bindings/custody-census").json()
    assert out["bindings"][0]["custody_state"] == "chat_orphaned"
    res = client.delete(f"/api/v1/scenarios/{definition['id']}")
    assert res.status_code == 200
    out = client.get("/api/v1/scenarios/bindings/custody-census").json()
    assert out["bindings"][0]["custody_state"] == "doubly_broken"
    assert out["counts"]["doubly_broken"] == 1
    # the standing unbind road still removes the named binding
    res = client.delete(f"/api/v1/scenarios/bindings/{chat['id']}")
    assert res.status_code == 200
    assert res.json()["unbound"] is True
    out = client.get("/api/v1/scenarios/bindings/custody-census").json()
    assert out["counts"] == ZERO_COUNTS


def test_http_literal_custody_census_not_a_chat_id(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _bind(client, definition["id"])
    res = client.get("/api/v1/scenarios/bindings/custody-census")
    assert res.status_code == 200
    assert res.json()["counts"]["bindings_total"] == 1
    got = client.get(f"/api/v1/scenarios/bindings/{chat['id']}")
    assert got.status_code == 200
    assert got.json()["chat_id"] == chat["id"]


def test_http_census_is_owner_scoped(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    _bind(client, definition["id"])
    store = ScenarioStore(definitions_path())
    foreign = store.create(FOREIGN, body(), now=NOW)
    bstore = ScenarioBindingStore(bindings_path())
    bstore.add(_rec("bf", FOREIGN, "chat-foreign", foreign.id, rev=1))
    out = client.get("/api/v1/scenarios/bindings/custody-census").json()
    assert out["counts"]["bindings_total"] == 1
    assert all(
        row["definition_id"] != foreign.id for row in out["bindings"])


def test_http_census_writes_nothing(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _bind(client, definition["id"])
    binds_file = tmp_path / "scenario_bindings.json"
    defs_file = tmp_path / "scenarios.json"
    before = (binds_file.read_bytes(), defs_file.read_bytes())
    res = client.get("/api/v1/scenarios/bindings/custody-census")
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
    assert client.get("/api/v1/scenarios/bindings").status_code == 200
    assert client.get("/api/v1/scenarios/bindings/census").status_code == 200
    assert client.get(
        "/api/v1/scenarios/bindings/chat-census").status_code == 200
    assert client.get(f"{base}/bindings").status_code == 200
    assert client.get(f"{base}/bind-plan").status_code == 200
    assert client.get(f"{base}/delete-impact").status_code == 200
    assert client.get(
        f"/api/v1/scenarios/bindings/{chat['id']}").status_code == 200


# ----------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    assert MIGRATIONS[-1][0] == "0041"
