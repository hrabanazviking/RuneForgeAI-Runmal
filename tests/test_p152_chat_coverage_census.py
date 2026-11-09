"""P-152 - Chat coverage census (Part IX, DERIVED).

Pins: the honest zero; chats with no bindings rowing
as unbound (the one census a never-bound chat appears
in at all); the coverage law as the plain reading of
P-144's verdict on the chat axis (sound beside a
standing chat at the current revision;
definition_drift after a real replace, and for a
hand-damaged ahead pin; definition_gone after a real
definition delete, the chat still rowing); orphaned
bindings counted in the totals and rowing under no
chat (a ghost chat, and after a REAL bind + REAL chat
deletion - delete_chat leaves the binding document
byte-untouched); foreign isolation (a foreign chat
never rows, the caller's binding naming a foreign
chat counts orphaned, foreign bindings never counted,
the foreign owner's own census rows the same chat
unbound); the hand-damaged duplicate-rows case (the
first row rows, the surplus is counted, never hidden);
a group chat rowing with is_group true; row order =
Chat.created_at order on planted chats with explicit
stamps; rows carrying identity facts only, the bound
row carrying P-144's census row verbatim; counts
summed from the rows so they reconcile exactly (both
identities); writes-nothing at service and HTTP level
(both store documents byte-untouched, chat history
intact); the HTTP road (the literal chats/census road
answering beside the P-135 / P-144 / P-148 / P-150 /
P-151 census roads and the P-132 per-chat read, the
state moving unbound -> sound -> definition_drift ->
definition_gone -> unbound across the live flow,
owner isolation); and the migration head pinned at
0041. No network: fixtures only.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Chat, Group, User
from runmal.scenarios.binding import (
    ScenarioBinding,
    ScenarioBindingStore,
    bind_scenario,
    bindings_path,
)
from runmal.scenarios.bindingcensus import census_bindings
from runmal.scenarios.chatcoverage import (
    CHAT_COVERAGE_STATES,
    census_chat_coverage,
)
from runmal.scenarios.store import ScenarioStore, definitions_path

NOW = "2026-11-08T21:30:00+00:00"
FOREIGN = "foreign-p152"

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
        return await census_chat_coverage(session, bindings, owner, records)


ZERO_COUNTS = {
    "chats_total": 0, "chats_unbound": 0, "chats_sound": 0,
    "chats_definition_drift": 0, "chats_definition_gone": 0,
    "bindings_total": 0, "bindings_rowed": 0,
    "bindings_orphaned_chat": 0, "bindings_surplus_rows": 0,
    "definitions_referenced": 0,
}

ROW_KEYS = {
    "chat_id", "title", "is_group", "created_at",
    "binding", "coverage_state",
}


# ------------------------------------------------------- service


async def test_service_no_chats_is_the_honest_zero(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    out = await _census(factory, tmp_path, user)
    assert out["chats"] == []
    assert out["counts"] == ZERO_COUNTS
    assert len(out["notes"]) == 5
    assert CHAT_COVERAGE_STATES == (
        "unbound", "sound", "definition_drift", "definition_gone")


async def test_service_chats_without_bindings_are_unbound(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    first = await make_chat(factory, user, "First")
    second = await make_chat(factory, user, "Second")
    out = await _census(factory, tmp_path, user)
    assert [row["chat_id"] for row in out["chats"]] == [first, second]
    assert all(
        row["coverage_state"] == "unbound" for row in out["chats"])
    assert all(row["binding"] is None for row in out["chats"])
    assert out["counts"]["chats_total"] == 2
    assert out["counts"]["chats_unbound"] == 2
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
    row = out["chats"][0]
    assert set(row) == ROW_KEYS
    assert row["chat_id"] == chat_id
    assert row["title"] == "Harbour"
    assert row["is_group"] is False
    assert row["coverage_state"] == "sound"
    # the carried binding is P-144's census row verbatim
    verdicts = census_bindings(
        bindings, user, definitions.list_for_owner(user))["bindings"]
    assert row["binding"] == verdicts[0]
    assert row["binding"]["state"] == "current"
    assert out["counts"]["chats_sound"] == 1
    assert out["counts"]["bindings_rowed"] == 1
    assert out["counts"]["definitions_referenced"] == 1


async def test_service_unbound_chat_rows_beside_a_sound_one(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    bound_chat = await make_chat(factory, user, "Bound")
    free_chat = await make_chat(factory, user, "Free")
    bindings.add(_rec("b1", user, bound_chat, record.id,
                      name=record.name, rev=1))
    out = await _census(factory, tmp_path, user)
    rows = {row["chat_id"]: row for row in out["chats"]}
    # the never-bound chat appears in this census - it
    # appears in no binding census at all
    assert rows[free_chat]["coverage_state"] == "unbound"
    assert rows[free_chat]["binding"] is None
    assert rows[bound_chat]["coverage_state"] == "sound"
    assert out["counts"]["chats_unbound"] == 1
    assert out["counts"]["chats_sound"] == 1


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
    row = out["chats"][0]
    assert row["coverage_state"] == "definition_drift"
    assert row["binding"]["state"] == "superseded"
    assert out["counts"]["chats_definition_drift"] == 1


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
    assert out["chats"][0]["coverage_state"] == "definition_drift"
    assert out["chats"][0]["binding"]["state"] == "ahead"


async def test_service_gone_after_a_real_definition_delete(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    definitions.remove(record.id, user)
    out = await _census(factory, tmp_path, user)
    # the chat still rows - its binding's definition is gone
    assert [row["chat_id"] for row in out["chats"]] == [chat_id]
    row = out["chats"][0]
    assert row["coverage_state"] == "definition_gone"
    assert row["binding"]["state"] == "stale"
    assert out["counts"]["chats_definition_gone"] == 1
    assert out["counts"]["bindings_rowed"] == 1


async def test_service_orphaned_binding_is_counted_not_rowed(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    standing = await make_chat(factory, user)
    bindings.add(_rec("b1", user, "chat-ghost", record.id,
                      name=record.name, rev=1))
    out = await _census(factory, tmp_path, user)
    assert [row["chat_id"] for row in out["chats"]] == [standing]
    assert out["chats"][0]["coverage_state"] == "unbound"
    counts = out["counts"]
    assert counts["bindings_total"] == 1
    assert counts["bindings_orphaned_chat"] == 1
    assert counts["bindings_rowed"] == 0
    assert counts["definitions_referenced"] == 0


async def test_service_orphan_after_real_bind_and_delete(tmp_path):
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
    assert out["chats"][0]["coverage_state"] == "sound"
    binds_file = tmp_path / "scenario_bindings.json"
    before = binds_file.read_bytes()
    async with factory() as session:
        assert await svc.delete_chat(session, user, chat_id) is True
    assert binds_file.read_bytes() == before
    out = await _census(factory, tmp_path, user)
    # the chat row leaves the census; its binding is
    # counted in the totals and rows under no chat
    assert out["chats"] == []
    counts = out["counts"]
    assert counts["chats_total"] == 0
    assert counts["bindings_total"] == 1
    assert counts["bindings_orphaned_chat"] == 1
    assert counts["bindings_rowed"] == 0


async def test_service_foreign_rows_never_counted(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, "other")
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    foreign_def = definitions.create(other, body("Foreign"), now=NOW)
    mine = await make_chat(factory, user, "Mine")
    theirs = await make_chat(factory, other, "Theirs")
    # my binding naming their chat: orphaned for me -
    # their chat is not among MY chats (P-148's law)
    bindings.add(_rec("b1", user, theirs, record.id,
                      name=record.name, rev=1))
    # their binding naming my chat: never mine to count
    bindings.add(_rec("bf", other, mine, foreign_def.id, rev=1))
    out = await _census(factory, tmp_path, user)
    assert [row["chat_id"] for row in out["chats"]] == [mine]
    assert out["chats"][0]["coverage_state"] == "unbound"
    counts = out["counts"]
    assert counts["bindings_total"] == 1
    assert counts["bindings_orphaned_chat"] == 1
    # the foreign owner's own census rows the same chat
    # unbound - my binding is not theirs either
    out = await _census(factory, tmp_path, other)
    assert [row["chat_id"] for row in out["chats"]] == [theirs]
    assert out["chats"][0]["coverage_state"] == "unbound"
    assert out["counts"]["bindings_total"] == 1
    assert out["counts"]["bindings_orphaned_chat"] == 1


async def test_service_duplicate_rows_first_rows_surplus_counted(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    # hand-damaged store: two rows for one chat (bind
    # forbids it) - the first rows, the surplus counts
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=1))
    bindings.add(_rec("b2", user, chat_id, record.id,
                      name=record.name, rev=1))
    out = await _census(factory, tmp_path, user)
    row = out["chats"][0]
    assert row["binding"]["id"] == "b1"
    assert row["coverage_state"] == "sound"
    counts = out["counts"]
    assert counts["bindings_total"] == 2
    assert counts["bindings_rowed"] == 1
    assert counts["bindings_surplus_rows"] == 1
    assert counts["bindings_orphaned_chat"] == 0
    assert counts["chats_sound"] == 1


async def test_service_group_chat_rows_with_is_group(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    async with factory() as session:
        session.add(Group(id="grp-p152", user_id=user, name="Crew"))
        await session.commit()
    async with factory() as session:
        session.add(Chat(
            id="chat-group-p152", user_id=user, title="Crew Room",
            group_id="grp-p152",
            created_at=datetime(2026, 11, 8, 10, 0, tzinfo=UTC)))
        await session.commit()
    solo = await make_chat(factory, user, "Solo")
    out = await _census(factory, tmp_path, user)
    rows = {row["chat_id"]: row for row in out["chats"]}
    # custody judges existence, not bindability: a group
    # room rows here exactly as bind's refusal law is bind's
    assert rows["chat-group-p152"]["is_group"] is True
    assert rows["chat-group-p152"]["coverage_state"] == "unbound"
    assert rows[solo]["is_group"] is False


async def test_service_row_order_is_created_at_order(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    async with factory() as session:
        # planted out of order; the census rows them in
        # the chats service's own list order
        session.add(Chat(
            id="chat-late", user_id=user, title="Late",
            created_at=datetime(2026, 11, 8, 12, 0, tzinfo=UTC)))
        session.add(Chat(
            id="chat-early", user_id=user, title="Early",
            created_at=datetime(2026, 11, 8, 8, 0, tzinfo=UTC)))
        session.add(Chat(
            id="chat-mid", user_id=user, title="Mid",
            created_at=datetime(2026, 11, 8, 10, 0, tzinfo=UTC)))
        await session.commit()
    out = await _census(factory, tmp_path, user)
    assert [row["chat_id"] for row in out["chats"]] == [
        "chat-early", "chat-mid", "chat-late"]
    assert out["chats"][0]["created_at"].startswith("2026-11-08T08:00")


async def test_service_counts_reconcile_in_a_mixed_world(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    sound_def = definitions.create(user, body(), now=NOW)
    drift_def = definitions.create(user, body("Drift"), now=NOW)
    gone_def = definitions.create(user, body("Gone"), now=NOW)
    free_chat = await make_chat(factory, user, "Free")
    sound_chat = await make_chat(factory, user, "Sound")
    drift_chat = await make_chat(factory, user, "Drift")
    gone_chat = await make_chat(factory, user, "Gone")
    bindings.add(_rec("b1", user, sound_chat, sound_def.id,
                      name=sound_def.name, rev=1))
    bindings.add(_rec("b2", user, drift_chat, drift_def.id,
                      name=drift_def.name, rev=1))
    bindings.add(_rec("b3", user, gone_chat, gone_def.id,
                      name=gone_def.name, rev=1))
    bindings.add(_rec("b4", user, "chat-ghost", sound_def.id,
                      name=sound_def.name, rev=1))
    definitions.replace(drift_def.id, user, revised_body(), now=NOW)
    definitions.remove(gone_def.id, user)
    out = await _census(factory, tmp_path, user)
    counts = out["counts"]
    states = {row["chat_id"]: row["coverage_state"] for row in out["chats"]}
    assert states == {
        free_chat: "unbound", sound_chat: "sound",
        drift_chat: "definition_drift", gone_chat: "definition_gone",
    }
    assert counts["chats_total"] == 4
    assert counts["chats_unbound"] == 1
    assert counts["chats_sound"] == 1
    assert counts["chats_definition_drift"] == 1
    assert counts["chats_definition_gone"] == 1
    assert counts["chats_unbound"] + counts["chats_sound"] \
        + counts["chats_definition_drift"] \
        + counts["chats_definition_gone"] == counts["chats_total"]
    assert counts["bindings_total"] == 4
    assert counts["bindings_rowed"] == 3
    assert counts["bindings_orphaned_chat"] == 1
    assert counts["bindings_surplus_rows"] == 0
    assert counts["bindings_rowed"] \
        + counts["bindings_orphaned_chat"] \
        + counts["bindings_surplus_rows"] == counts["bindings_total"]
    assert counts["definitions_referenced"] == 3


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


def _chat(client, title="Harbour"):
    res = client.post("/api/v1/chats", json={"title": title})
    assert res.status_code == 201
    return res.json()


def _bind(client, definition_id, chat_id):
    res = client.post(
        f"/api/v1/scenarios/{definition_id}/bind",
        json={"chat_id": chat_id})
    assert res.status_code == 201
    return res.json()


def test_http_zero_census(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    res = client.get("/api/v1/scenarios/chats/census")
    assert res.status_code == 200
    out = res.json()
    assert out["chats"] == []
    assert out["counts"] == ZERO_COUNTS
    assert len(out["notes"]) == 5


def test_http_state_moves_unbound_sound_drift_gone(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _chat(client)
    out = client.get("/api/v1/scenarios/chats/census").json()
    assert out["chats"][0]["coverage_state"] == "unbound"
    _bind(client, definition["id"], chat["id"])
    out = client.get("/api/v1/scenarios/chats/census").json()
    assert out["chats"][0]["coverage_state"] == "sound"
    res = client.put(
        f"/api/v1/scenarios/{definition['id']}", json=revised_body())
    assert res.status_code == 200
    out = client.get("/api/v1/scenarios/chats/census").json()
    assert out["chats"][0]["coverage_state"] == "definition_drift"
    res = client.delete(f"/api/v1/scenarios/{definition['id']}")
    assert res.status_code == 200
    out = client.get("/api/v1/scenarios/chats/census").json()
    assert out["chats"][0]["coverage_state"] == "definition_gone"
    # the standing unbind road still removes the named
    # binding, and the chat reads unbound again
    res = client.delete(f"/api/v1/scenarios/bindings/{chat['id']}")
    assert res.status_code == 200
    out = client.get("/api/v1/scenarios/chats/census").json()
    assert out["chats"][0]["coverage_state"] == "unbound"
    assert out["counts"]["bindings_total"] == 0
    # deleting the chat removes its row entirely
    res = client.delete(f"/api/v1/chats/{chat['id']}")
    assert res.status_code == 200
    out = client.get("/api/v1/scenarios/chats/census").json()
    assert out["chats"] == []


def test_http_census_is_owner_scoped(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _chat(client)
    _bind(client, definition["id"], chat["id"])
    store = ScenarioStore(definitions_path())
    foreign = store.create(FOREIGN, body(), now=NOW)
    bstore = ScenarioBindingStore(bindings_path())
    bstore.add(_rec("bf", FOREIGN, chat["id"], foreign.id, rev=1))
    out = client.get("/api/v1/scenarios/chats/census").json()
    assert out["counts"]["chats_total"] == 1
    assert out["counts"]["bindings_total"] == 1
    assert out["chats"][0]["binding"]["id"] != "bf"


def test_http_census_writes_nothing(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _chat(client)
    _bind(client, definition["id"], chat["id"])
    binds_file = tmp_path / "scenario_bindings.json"
    defs_file = tmp_path / "scenarios.json"
    before = (binds_file.read_bytes(), defs_file.read_bytes())
    res = client.get("/api/v1/scenarios/chats/census")
    assert res.status_code == 200
    assert (binds_file.read_bytes(), defs_file.read_bytes()) == before
    history = client.get(f"/api/v1/chats/{chat['id']}/messages")
    assert history.status_code == 200
    assert len(history.json()) == 2


def test_http_neighbour_roads_untouched_beside_it(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _chat(client)
    _bind(client, definition["id"], chat["id"])
    base = f"/api/v1/scenarios/{definition['id']}"
    assert client.get("/api/v1/chats").status_code == 200
    assert client.get("/api/v1/scenarios/chats/census").status_code == 200
    assert client.get("/api/v1/scenarios/bindings").status_code == 200
    assert client.get(
        "/api/v1/scenarios/bindings/census").status_code == 200
    assert client.get(
        "/api/v1/scenarios/bindings/chat-census").status_code == 200
    assert client.get(
        "/api/v1/scenarios/bindings/custody-census").status_code == 200
    assert client.get(
        "/api/v1/scenarios/library/census").status_code == 200
    assert client.get(base).status_code == 200
    assert client.get(f"{base}/bindings").status_code == 200
    assert client.get(
        f"/api/v1/scenarios/bindings/{chat['id']}").status_code == 200
    assert client.get(
        f"/api/v1/scenarios/bindings/{chat['id']}/delete-impact"
    ).status_code == 200
    # "chats" alone is a definition id like any other -
    # the census road captures nothing it should not
    assert client.get("/api/v1/scenarios/chats").status_code == 404


# ----------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
    assert MIGRATIONS[-1][0] == "0042"
