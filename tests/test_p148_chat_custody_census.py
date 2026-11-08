"""P-148 - Binding chat-custody census (Part IX, DERIVED).

Pins: the honest zero; the two states judged against the
live Chat table (live for a standing chat; orphaned after
a REAL chat deletion - delete_chat leaves the binding
document byte-untouched - for a never-existent chat id,
and for another owner's chat, existence being judged
owner-scoped so the other owner's own census of the same
chat reads it live); foreign binding rows never counted;
the two axes independent (orphaned + stale on one row;
live beside a superseded pin); rows as P-135 summaries
verbatim plus exactly the two custody keys; per-definition
rollups and census counts summed from the rows so they
reconcile exactly, including the hand-damaged
duplicate-chat-rows case (bindings counted per row, chats
counted distinct); writes-nothing at service and HTTP
level (both store documents byte-untouched, chat history
untouched); and the HTTP road (the literal chat-census
road winning over the {chat_id} binding read, the
orphaned chat's per-chat binding read STILL answering its
record beside the census, the unbind road still removing
the named orphan, owner isolation, the P-135 / P-144
neighbour roads untouched beside it); and the migration
head pinned at 0041. No network: fixtures only.
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
    list_bindings,
)
from runmal.scenarios.chatcensus import (
    CHAT_CUSTODY_STATES,
    census_binding_chats,
)
from runmal.scenarios.store import ScenarioStore, definitions_path

NOW = "2026-11-08T19:00:00+00:00"
OWNER = "owner-p148"
FOREIGN = "foreign-p148"

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
    live = {row.id for row in definitions.list_for_owner(owner)}
    async with factory() as session:
        return await census_binding_chats(session, bindings, owner, live)


ZERO_COUNTS = {
    "bindings_total": 0, "live": 0, "orphaned": 0,
    "chats_live": 0, "chats_orphaned": 0,
    "definitions_referenced": 0, "definitions_with_live": 0,
    "definitions_with_orphaned": 0,
}


# ------------------------------------------------------- service


async def test_service_no_bindings_is_the_honest_zero(tmp_path):
    factory = make_factory(tmp_path)
    definitions, _bindings = _stores(tmp_path)
    definitions.create(OWNER, body(), now=NOW)
    out = await _census(factory, tmp_path, OWNER)
    assert out["bindings"] == []
    assert out["by_definition"] == []
    assert out["counts"] == ZERO_COUNTS
    assert len(out["notes"]) == 5
    assert CHAT_CUSTODY_STATES == ("live", "orphaned")


async def test_service_one_live_binding(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    out = await _census(factory, tmp_path, user)
    assert out["counts"]["bindings_total"] == 1
    assert out["counts"]["live"] == 1
    assert out["counts"]["chats_live"] == 1
    assert out["counts"]["definitions_with_live"] == 1
    row = out["bindings"][0]
    assert row["chat_exists"] is True
    assert row["chat_state"] == "live"
    group = out["by_definition"][0]
    assert group["definition_id"] == record.id
    assert group["live"] == 1 and group["orphaned"] == 0
    assert group["chat_ids"] == [chat_id]


async def test_service_never_existent_chat_is_orphaned(tmp_path):
    factory = make_factory(tmp_path)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    bindings.add(_rec("b1", OWNER, "chat-ghost", record.id,
                      name=record.name, rev=1))
    out = await _census(factory, tmp_path, OWNER)
    assert out["counts"]["orphaned"] == 1
    assert out["counts"]["chats_orphaned"] == 1
    row = out["bindings"][0]
    assert row["chat_exists"] is False
    assert row["chat_state"] == "orphaned"


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
    assert out["counts"]["live"] == 1
    binds_file = tmp_path / "scenario_bindings.json"
    before = binds_file.read_bytes()
    async with factory() as session:
        assert await svc.delete_chat(session, user, chat_id) is True
    # chat deletion cleans its own custodies but never the
    # binding store: the document is byte-untouched
    assert binds_file.read_bytes() == before
    out = await _census(factory, tmp_path, user)
    assert out["counts"]["live"] == 0
    assert out["counts"]["orphaned"] == 1
    assert out["bindings"][0]["chat_id"] == chat_id
    assert out["bindings"][0]["chat_state"] == "orphaned"


async def test_service_foreign_chat_reads_orphaned_for_caller(tmp_path):
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
    out = await _census(factory, tmp_path, mine)
    assert out["counts"]["bindings_total"] == 1
    assert out["bindings"][0]["chat_state"] == "orphaned"
    out = await _census(factory, tmp_path, theirs)
    assert out["counts"]["bindings_total"] == 1
    assert out["bindings"][0]["chat_state"] == "live"


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
    out = await _census(factory, tmp_path, user)
    assert out["counts"]["bindings_total"] == 1
    assert all(
        row["definition_id"] != foreign_record.id
        for row in out["bindings"])


async def test_service_two_axes_are_independent(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    first = definitions.create(user, body(), now=NOW)
    second = definitions.create(user, body("Second"), now=NOW)
    chat_one = await make_chat(factory, user, "One")
    chat_two = await make_chat(factory, user, "Two")
    bindings.add(_rec("b1", user, chat_one, first.id,
                      name=first.name, rev=1))
    bindings.add(_rec("b2", user, chat_two, second.id,
                      name=second.name, rev=1))
    # b2: a replace lands, the chat stands - live on the
    # chat axis beside its superseded pin (P-144's axis)
    definitions.replace(second.id, user, revised_body(), now=NOW)
    # b1: definition deleted AND chat deleted - orphaned
    # here, stale on the definition axis, at once
    definitions.remove(first.id, user)
    async with factory() as session:
        assert await svc.delete_chat(session, user, chat_one) is True
    out = await _census(factory, tmp_path, user)
    rows = {row["id"]: row for row in out["bindings"]}
    assert rows["b1"]["chat_state"] == "orphaned"
    assert rows["b1"]["definition_exists"] is False
    assert rows["b2"]["chat_state"] == "live"
    assert rows["b2"]["definition_exists"] is True
    assert rows["b2"]["definition_revision"] == 1
    assert out["counts"]["live"] == 1
    assert out["counts"]["orphaned"] == 1
    assert out["counts"]["definitions_with_live"] == 1
    assert out["counts"]["definitions_with_orphaned"] == 1


async def test_service_rows_are_p135_summaries_verbatim(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    bindings.add(_rec("b2", user, "chat-ghost", record.id,
                      name=record.name, rev=1))
    live = {row.id for row in definitions.list_for_owner(user)}
    summaries = list_bindings(bindings, user, live)
    out = await _census(factory, tmp_path, user)
    assert len(out["bindings"]) == len(summaries)
    for row, summary in zip(out["bindings"], summaries, strict=True):
        stripped = {
            key: value for key, value in row.items()
            if key not in ("chat_exists", "chat_state")
        }
        assert stripped == summary


async def test_service_counts_reconcile_and_chats_are_distinct(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    first = definitions.create(user, body(), now=NOW)
    second = definitions.create(user, body("Second"), now=NOW)
    chat_id = await make_chat(factory, user)
    # hand-damaged store: two rows for one chat (bind
    # forbids it) - rows count per row, chats distinct
    bindings.add(_rec("b1", user, chat_id, first.id,
                      name=first.name, rev=1))
    bindings.add(_rec("b2", user, chat_id, second.id,
                      name=second.name, rev=1))
    bindings.add(_rec("b3", user, "chat-ghost", first.id,
                      name=first.name, rev=1))
    out = await _census(factory, tmp_path, user)
    counts = out["counts"]
    assert counts["bindings_total"] == 3
    assert counts["live"] == 2 and counts["orphaned"] == 1
    assert counts["live"] + counts["orphaned"] == counts["bindings_total"]
    assert counts["chats_live"] == 1
    assert counts["chats_orphaned"] == 1
    assert counts["definitions_referenced"] == 2
    groups = {g["definition_id"]: g for g in out["by_definition"]}
    assert groups[first.id]["bindings_total"] == 2
    assert groups[first.id]["live"] == 1
    assert groups[first.id]["orphaned"] == 1
    assert groups[first.id]["chat_ids"] == [chat_id, "chat-ghost"]
    assert groups[second.id]["bindings_total"] == 1
    for group in out["by_definition"]:
        assert group["live"] + group["orphaned"] == group["bindings_total"]


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
    res = client.get("/api/v1/scenarios/bindings/chat-census")
    assert res.status_code == 200
    out = res.json()
    assert out["bindings"] == []
    assert out["by_definition"] == []
    assert out["counts"] == ZERO_COUNTS
    assert len(out["notes"]) == 5


def test_http_live_then_orphaned_then_unbound(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _bind(client, definition["id"])
    out = client.get("/api/v1/scenarios/bindings/chat-census").json()
    assert out["counts"]["live"] == 1
    assert out["bindings"][0]["chat_state"] == "live"
    res = client.delete(f"/api/v1/chats/{chat['id']}")
    assert res.status_code == 200
    out = client.get("/api/v1/scenarios/bindings/chat-census").json()
    assert out["counts"]["live"] == 0
    assert out["counts"]["orphaned"] == 1
    assert out["counts"]["chats_orphaned"] == 1
    # the custody fact this slice names: the orphaned
    # chat's per-chat binding read STILL answers its
    # record, exactly as if the chat lived
    got = client.get(f"/api/v1/scenarios/bindings/{chat['id']}")
    assert got.status_code == 200
    assert got.json()["chat_id"] == chat["id"]
    # and the unbind road still removes the named orphan
    res = client.delete(f"/api/v1/scenarios/bindings/{chat['id']}")
    assert res.status_code == 200
    assert res.json()["unbound"] is True
    out = client.get("/api/v1/scenarios/bindings/chat-census").json()
    assert out["counts"] == ZERO_COUNTS


def test_http_literal_chat_census_not_a_chat_id(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _bind(client, definition["id"])
    res = client.get("/api/v1/scenarios/bindings/chat-census")
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
    out = client.get("/api/v1/scenarios/bindings/chat-census").json()
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
    res = client.get("/api/v1/scenarios/bindings/chat-census")
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
    listing = client.get("/api/v1/scenarios/bindings")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert client.get("/api/v1/scenarios/bindings/census").status_code == 200
    assert client.get(f"{base}/bindings").status_code == 200
    assert client.get(f"{base}/bind-plan").status_code == 200
    assert client.get(f"{base}/replace-impact").status_code == 200
    assert client.get(f"{base}/delete-impact").status_code == 200
    assert client.get(
        f"/api/v1/scenarios/bindings/{chat['id']}").status_code == 200
    assert client.get(
        "/api/v1/scenarios/bindings/chat-census").status_code == 200


# ----------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    assert MIGRATIONS[-1][0] == "0041"
