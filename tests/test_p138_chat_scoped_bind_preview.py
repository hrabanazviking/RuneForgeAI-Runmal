"""P-138 — Chat-scoped bind preview (Part IX, DERIVED scope).

Pins: the chat-scoped envelope (P-136's definition four +
chat_id; the plan is P-136's preview plan and P-132's
plan_materialisation verbatim; counts read from the plan);
the blocker facts reported as data in bind's decision
order (group room, already bound — naming the standing
binding — and non-empty chat, with its message count),
each standing alone and in combination; would_bind as a
statement about the chat as it stands; the seedable keys
split by the P-093 store's own presence law into
would-seed full keys and already-present entries carrying
bind's own reason, its where and its full key; the
preview == bind pin (a real bind afterwards lands
exactly the previewed would-seed keys, accounts exactly
the previewed already-present skips, and seeds exactly
the previewed message count); existence discipline
(unknown / foreign definition 404 alike over HTTP;
unknown / foreign chat answering None in the service
and 404 "chat not found" over HTTP); the four standing
notes in fixed order; previewing writes nothing — at
service level and over HTTP — and consumes nothing (a
real bind still succeeds after); the P-136 / P-132 /
P-131 roads answering exactly as before beside it; and
the migration head pinned at 0041. No network:
fixtures only.
"""

from __future__ import annotations

import asyncio
import copy

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Chat, Group, User
from runmal.plugins.variables import list_entries, seed_variables
from runmal.scenarios.binding import (
    ScenarioBindingStore,
    bind_scenario,
    plan_materialisation,
)
from runmal.scenarios.bindpreview import preview_bind_plan
from runmal.scenarios.chatpreview import preview_bind_for_chat
from runmal.scenarios.store import ScenarioStore, definitions_path

NOW = "2026-11-08T13:00:00+00:00"
OWNER = "owner-q38"
FOREIGN = "foreign-q38"

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
        {"name": "Keeper", "character_name": "",
         "enabled_on_start": True, "can_speak": True},
    ],
    "bootstrap_messages": [
        {"kind": "instructions", "text": "Keep the lamps lit.", "role": ""},
        {"kind": "note", "text": "The tide is going out.", "role": "Narrator"},
        {"kind": "char", "text": "You came back.", "role": "Keeper"},
        {"kind": "user", "text": "I never left.", "role": ""},
        {"kind": "story", "text": "Gulls settle on the mast.", "role": ""},
        {"kind": "note", "text": "   ", "role": "Narrator"},
    ],
    "initial_flags": {"met_maera": True, "bad_flag": "yes"},
    "initial_variables": {
        "trust": 2, "mood": "calm", "nested": {"x": 1}, "bad key!": 3,
    },
}

SEEDABLE = {"shared:met_maera", "shared:mood", "shared:trust"}


def body() -> dict:
    return copy.deepcopy(BODY)


# ------------------------------------------------------------ harness


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


def stores(tmp_path):
    return (
        ScenarioStore(tmp_path / "scenarios.json"),
        ScenarioBindingStore(tmp_path / "scenario_bindings.json"),
    )


async def preview(factory, tmp_path, user_id, record, chat_id):
    _definitions, bindings = stores(tmp_path)
    async with factory() as session:
        return await preview_bind_for_chat(
            session, record, user_id, chat_id,
            bindings=bindings, variables_base_dir=tmp_path)


async def bind(factory, tmp_path, user_id, definition_id, chat_id):
    definitions, bindings = stores(tmp_path)
    async with factory() as session:
        return await bind_scenario(
            session, user_id, definition_id, chat_id,
            definitions=definitions, bindings=bindings,
            variables_base_dir=tmp_path, now=NOW)


# ---------------------------------------------------- service: clean


async def test_clean_chat_envelope_plan_and_keys(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    env = await preview(factory, tmp_path, user, rec, chat_id)
    assert env is not None
    assert env["definition_id"] == rec.id
    assert env["definition_name"] == "Harbour Lights at Dusk"
    assert env["definition_revision"] == 1
    assert env["source_format"] == rec.source_format
    assert env["chat_id"] == chat_id
    assert env["plan"] == plan_materialisation(rec.definition)
    assert env["plan"] == preview_bind_plan(rec)["plan"]
    assert env["counts"] == {
        "messages": 5, "flags": 1, "variables": 2, "skipped": 4,
    }
    assert env["blockers"] == []
    assert env["would_bind"] is True
    assert env["keys"]["already_present"] == []
    assert set(env["keys"]["would_seed"]) == SEEDABLE
    assert env["keys"]["would_seed"][0] == "shared:met_maera"
    notes = env["notes"]
    assert len(notes) == 4
    assert "current state" in notes[0] and "nothing" in notes[0]
    assert "re-decides" in notes[1]
    assert "presence law" in notes[2] and "binding record" in notes[2]
    assert "current" in notes[3] and "revision" in notes[3]


async def test_bare_definition_clean_chat(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, {"name": "Bare"}, now=NOW)
    chat_id = await make_chat(factory, user)
    env = await preview(factory, tmp_path, user, rec, chat_id)
    assert env["counts"] == {
        "messages": 0, "flags": 0, "variables": 0, "skipped": 0,
    }
    assert env["blockers"] == [] and env["would_bind"] is True
    assert env["keys"] == {"would_seed": [], "already_present": []}


# ------------------------------------------- service: presence law


async def test_already_present_split_by_p093_law(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    landed = seed_variables(user, chat_id, {"trust": 99}, base_dir=tmp_path)
    assert landed == ["shared:trust"]
    env = await preview(factory, tmp_path, user, rec, chat_id)
    assert set(env["keys"]["would_seed"]) == {"shared:met_maera", "shared:mood"}
    assert env["keys"]["already_present"] == [{
        "where": "initial_variables",
        "key_or_index": "trust",
        "full_key": "shared:trust",
        "reason": "already present; seeding never overwrites live state",
    }]
    # The definition-side plan is untouched by the chat's state.
    assert env["counts"]["variables"] == 2
    assert env["would_bind"] is True


async def test_preview_verdicts_match_the_real_bind(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    seed_variables(user, chat_id, {"trust": 99}, base_dir=tmp_path)
    env = await preview(factory, tmp_path, user, rec, chat_id)
    record = await bind(factory, tmp_path, user, rec.id, chat_id)
    assert set(record.seeded_keys) == set(env["keys"]["would_seed"])
    bind_present = {
        (s["where"], s["key_or_index"]) for s in record.skipped
        if s["reason"].startswith("already present")
    }
    preview_present = {
        (s["where"], s["key_or_index"])
        for s in env["keys"]["already_present"]
    }
    assert bind_present == preview_present == {("initial_variables", "trust")}
    assert len(record.seeded_messages) == env["counts"]["messages"] == 5
    # The pre-seeded value was never overwritten by the bind.
    entries = {e["key"]: e["value"] for e in list_entries(
        user, chat_id, base_dir=tmp_path)}
    assert entries["shared:trust"] == 99


# ------------------------------------------------- service: blockers


async def test_blocker_group_room_alone(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user, "Room")
    async with factory() as session:
        group = Group(user_id=user, name="Room")
        session.add(group)
        await session.flush()
        chat = await session.get(Chat, chat_id)
        chat.group_id = group.id
        await session.commit()
    env = await preview(factory, tmp_path, user, rec, chat_id)
    assert [b["kind"] for b in env["blockers"]] == ["group_room"]
    assert "group rooms take no scenario binding" in env["blockers"][0]["detail"]
    assert env["would_bind"] is False


async def test_blocker_non_empty_chat_alone(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    async with factory() as session:
        await svc.append_message(session, user, chat_id, "user", "Already talking.")
    env = await preview(factory, tmp_path, user, rec, chat_id)
    assert [b["kind"] for b in env["blockers"]] == ["chat_not_empty"]
    assert env["blockers"][0]["message_count"] == 1
    assert env["would_bind"] is False


async def test_blocker_already_bound_empty_chat_alone(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    bare = definitions.create(user, {"name": "Bare"}, now=NOW)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    standing = await bind(factory, tmp_path, user, bare.id, chat_id)
    env = await preview(factory, tmp_path, user, rec, chat_id)
    assert [b["kind"] for b in env["blockers"]] == ["already_bound"]
    blocker = env["blockers"][0]
    assert blocker["binding_id"] == standing.id
    assert blocker["definition_id"] == bare.id
    assert env["would_bind"] is False
    # Key verdicts are still computed honestly beside the blocker.
    assert set(env["keys"]["would_seed"]) == SEEDABLE


async def test_blockers_already_bound_and_non_empty_together(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    await bind(factory, tmp_path, user, rec.id, chat_id)
    env = await preview(factory, tmp_path, user, rec, chat_id)
    assert [b["kind"] for b in env["blockers"]] == [
        "already_bound", "chat_not_empty",
    ]
    assert env["blockers"][1]["message_count"] == 5
    assert env["would_bind"] is False


# ------------------------------------------------ service: existence


async def test_unknown_and_foreign_chat_answer_none(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, "other")
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    foreign_chat = await make_chat(factory, other)
    assert await preview(factory, tmp_path, user, rec, "no-such-chat") is None
    assert await preview(factory, tmp_path, user, rec, foreign_chat) is None
    mine = await make_chat(factory, user)
    assert await preview(factory, tmp_path, user, rec, mine) is not None


# --------------------------------------------- service: writes none


async def test_service_preview_writes_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    before = (tmp_path / "scenarios.json").read_bytes()
    await preview(factory, tmp_path, user, rec, chat_id)
    await preview(factory, tmp_path, user, rec, chat_id)
    assert (tmp_path / "scenarios.json").read_bytes() == before
    assert not (tmp_path / "scenario_bindings.json").exists()
    assert list_entries(user, chat_id, base_dir=tmp_path) == []
    async with factory() as session:
        assert await svc.get_history(session, user, chat_id) == []
    # Previewing consumed nothing: the real bind still lands.
    record = await bind(factory, tmp_path, user, rec.id, chat_id)
    assert len(record.seeded_messages) == 5


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
    return client, factory, db_path


def test_http_clean_chat_envelope(tmp_path, monkeypatch):
    client, _factory, _db = make_client(tmp_path, monkeypatch)
    definition = client.post("/api/v1/scenarios", json=body()).json()
    chat = client.post("/api/v1/chats", json={"title": "Harbour"}).json()
    res = client.get(
        f"/api/v1/scenarios/{definition['id']}/bind-plan/{chat['id']}")
    assert res.status_code == 200
    env = res.json()
    assert env["definition_id"] == definition["id"]
    assert env["chat_id"] == chat["id"]
    assert env["definition_revision"] == 1
    assert env["counts"] == {
        "messages": 5, "flags": 1, "variables": 2, "skipped": 4,
    }
    assert env["blockers"] == [] and env["would_bind"] is True
    assert set(env["keys"]["would_seed"]) == SEEDABLE
    assert env["keys"]["already_present"] == []
    assert len(env["notes"]) == 4


def test_http_existence_discipline(tmp_path, monkeypatch):
    client, _factory, _db = make_client(tmp_path, monkeypatch)
    definition = client.post("/api/v1/scenarios", json=body()).json()
    chat = client.post("/api/v1/chats", json={"title": "Harbour"}).json()
    store = ScenarioStore(definitions_path())
    store.create(FOREIGN, body(), now=NOW)
    foreign_id = store.list_for_owner(FOREIGN)[0].id
    for target in (foreign_id, "no-such-id"):
        res = client.get(f"/api/v1/scenarios/{target}/bind-plan/{chat['id']}")
        assert res.status_code == 404
        assert res.json()["detail"] == "scenario definition not found"
    res = client.get(
        f"/api/v1/scenarios/{definition['id']}/bind-plan/no-such-chat")
    assert res.status_code == 404
    assert res.json()["detail"] == "chat not found"
    # A definition check is decided before the chat is read:
    # unknown definition + unknown chat still names the definition.
    res = client.get("/api/v1/scenarios/no-such-id/bind-plan/no-such-chat")
    assert res.status_code == 404
    assert res.json()["detail"] == "scenario definition not found"


def test_http_foreign_chat_answers_chat_not_found(tmp_path, monkeypatch):
    client, _factory, db_path = make_client(tmp_path, monkeypatch)
    definition = client.post("/api/v1/scenarios", json=body()).json()

    async def make_foreign():
        factory = create_session_factory(create_db_engine(db_path))
        async with factory() as session:
            user = User(name="foreign")
            session.add(user)
            await session.commit()
            uid = user.id
        async with factory() as session:
            chat = await svc.create_chat(session, uid, "Foreign")
            return chat.id

    foreign_chat = asyncio.run(make_foreign())
    res = client.get(
        f"/api/v1/scenarios/{definition['id']}/bind-plan/{foreign_chat}")
    assert res.status_code == 404
    assert res.json()["detail"] == "chat not found"


def test_http_preview_after_bind_names_blockers(tmp_path, monkeypatch):
    client, _factory, _db = make_client(tmp_path, monkeypatch)
    definition = client.post("/api/v1/scenarios", json=body()).json()
    chat = client.post("/api/v1/chats", json={"title": "Harbour"}).json()
    bound = client.post(
        f"/api/v1/scenarios/{definition['id']}/bind",
        json={"chat_id": chat["id"]})
    assert bound.status_code == 201
    res = client.get(
        f"/api/v1/scenarios/{definition['id']}/bind-plan/{chat['id']}")
    assert res.status_code == 200
    env = res.json()
    assert env["would_bind"] is False
    assert [b["kind"] for b in env["blockers"]] == [
        "already_bound", "chat_not_empty",
    ]
    assert env["blockers"][0]["binding_id"] == bound.json()["id"]


def test_http_preview_writes_nothing_and_roads_untouched(
    tmp_path, monkeypatch
):
    client, _factory, _db = make_client(tmp_path, monkeypatch)
    definition = client.post("/api/v1/scenarios", json=body()).json()
    chat = client.post("/api/v1/chats", json={"title": "Harbour"}).json()
    defs_file = tmp_path / "scenarios.json"
    before = defs_file.read_bytes()
    res = client.get(
        f"/api/v1/scenarios/{definition['id']}/bind-plan/{chat['id']}")
    assert res.status_code == 200
    assert defs_file.read_bytes() == before
    assert not (tmp_path / "scenario_bindings.json").exists()
    history = client.get(f"/api/v1/chats/{chat['id']}/messages").json()
    texts = [m["content"] for m in history["messages"]] \
        if "messages" in history else [m["content"] for m in history]
    assert texts == []
    # P-136's definition-side road answers exactly as before.
    plan = client.get(f"/api/v1/scenarios/{definition['id']}/bind-plan")
    assert plan.status_code == 200 and len(plan.json()["notes"]) == 4
    # And the bind road still lands after all the previewing.
    bound = client.post(
        f"/api/v1/scenarios/{definition['id']}/bind",
        json={"chat_id": chat["id"]})
    assert bound.status_code == 201


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    assert MIGRATIONS[-1][0] == "0041"
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
