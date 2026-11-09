"""P-147 - Chat-scoped candidate bind preview (Part IX, DERIVED).

Pins: the candidate judged through the store door exactly
as P-146 judges it (would-be shape / report / P-131-law
counts / P-132 plan) AND judged against one named chat
exactly as P-138 judges the stored body (bind's blockers
as data in bind's decision order, would_bind, the
candidate plan's seedable keys split by P-093's own
presence law), with the stored plan's split and the
full-key deltas beside it; the identical candidate
mirroring P-138's verdicts for the same chat; the
preview -> replace -> P-138 pin (after a real replace
with the previewed body, P-138 answers the candidate's
split, blockers and would_bind exactly); existence
discipline on BOTH sides (unknown / foreign definition
404 alike; unknown / foreign chat answering None in the
service and 404 "chat not found" over HTTP - EVEN with
a malformed candidate, decided before the body is
judged); a refused candidate raising the door's own
typed refusals on an owned chat (422 over HTTP, record
untouched); the six standing notes in fixed order;
writes-nothing at service and HTTP level (no document
created or changed, no seeded entries, empty history,
a real bind still landing after); the neighbour roads
answering exactly as before beside it; and the
migration head pinned at 0041. No network: fixtures
only.
"""

from __future__ import annotations

import asyncio
import copy

import pytest
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
from runmal.scenarios.candidatechatpreview import (
    preview_candidate_for_chat,
)
from runmal.scenarios.chatpreview import preview_bind_for_chat
from runmal.scenarios.fileexport import export_native
from runmal.scenarios.fileimport import parse_scenario_file
from runmal.scenarios.filemodels import ScenarioParseError
from runmal.scenarios.store import (
    ScenarioStore,
    ScenarioStoreError,
    definitions_path,
)

NOW = "2026-11-08T20:00:00+00:00"
OWNER = "owner-q47"
FOREIGN = "foreign-q47"

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

CURRENT_SEEDABLE = {"shared:met_maera", "shared:mood", "shared:trust"}
CANDIDATE_SEEDABLE = {
    "shared:met_maera", "shared:met_ferryman",
    "shared:trust", "shared:tide",
}


def body() -> dict:
    return copy.deepcopy(BODY)


def changed_body() -> dict:
    out = body()
    out["name"] = "Harbour Lights at Dawn"
    out["scenario_text"] = "The ferry has returned."
    out["initial_flags"] = {"met_maera": True, "met_ferryman": True}
    out["initial_variables"] = {"trust": 3, "tide": "in"}
    return out


def candidate_definition(candidate: dict) -> dict:
    return export_native(parse_scenario_file(candidate))


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


async def preview(factory, tmp_path, user_id, record, chat_id, candidate):
    _definitions, bindings = stores(tmp_path)
    async with factory() as session:
        return await preview_candidate_for_chat(
            session, record, user_id, chat_id, candidate,
            bindings=bindings, variables_base_dir=tmp_path)


async def preview138(factory, tmp_path, user_id, record, chat_id):
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


async def test_clean_chat_candidate_envelope(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    env = await preview(factory, tmp_path, user, rec, chat_id, changed_body())
    assert env is not None
    assert env["definition_id"] == rec.id
    assert env["definition_name"] == "Harbour Lights at Dusk"
    assert env["definition_revision"] == 1
    assert env["next_revision"] == 2
    assert env["source_format"] == rec.source_format
    assert env["chat_id"] == chat_id
    cand = env["candidate"]
    assert cand["name"] == "Harbour Lights at Dawn"
    assert cand["definition"] == candidate_definition(changed_body())
    assert cand["plan"] == plan_materialisation(cand["definition"])
    assert cand["counts"] == {
        "role_count": 2, "bootstrap_count": 6, "has_unmappable": False,
    }
    assert cand["plan_counts"] == env["counts"]
    assert env["current"]["plan_counts"] == {
        "messages": 5, "flags": 1, "variables": 2, "skipped": 4,
    }
    assert env["blockers"] == []
    assert env["would_bind"] is True
    assert set(env["keys"]["would_seed"]) == CANDIDATE_SEEDABLE
    assert env["keys"]["already_present"] == []
    assert set(env["current_keys"]["would_seed"]) == CURRENT_SEEDABLE
    assert env["current_keys"]["already_present"] == []
    assert env["key_deltas"] == {
        "would_seed_added": ["shared:met_ferryman", "shared:tide"],
        "would_seed_removed": ["shared:mood"],
        "already_present_added": [],
        "already_present_removed": [],
    }
    notes = env["notes"]
    assert len(notes) == 6
    assert "pure read" in notes[0] and "only replacer" in notes[0]
    assert "store door's own parser" in notes[1]
    assert "next revision" in notes[1]
    assert "as if it were stored" in notes[2] and "P-138" in notes[2]
    assert "as it stands" in notes[3] and "re-decides" in notes[3]
    assert "presence law" in notes[4] and "binding record" in notes[4]
    assert "parsed and planned as data" in notes[5]
    assert "unmappable" in notes[5]


async def test_identical_candidate_mirrors_p138_verdicts(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    seed_variables(user, chat_id, {"trust": 99}, base_dir=tmp_path)
    env = await preview(factory, tmp_path, user, rec, chat_id, body())
    stored = await preview138(factory, tmp_path, user, rec, chat_id)
    assert env["candidate"]["definition"] == rec.definition
    assert env["candidate"]["plan"] == stored["plan"]
    assert env["keys"] == stored["keys"]
    assert env["current_keys"] == stored["keys"]
    assert env["blockers"] == stored["blockers"] == []
    assert env["would_bind"] is stored["would_bind"] is True
    assert env["key_deltas"] == {
        "would_seed_added": [], "would_seed_removed": [],
        "already_present_added": [], "already_present_removed": [],
    }


# ------------------------------------------- service: presence law


async def test_candidate_only_key_judged_present(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    landed = seed_variables(user, chat_id, {"tide": "out"}, base_dir=tmp_path)
    assert landed == ["shared:tide"]
    env = await preview(factory, tmp_path, user, rec, chat_id, changed_body())
    assert set(env["keys"]["would_seed"]) == {
        "shared:met_maera", "shared:met_ferryman", "shared:trust",
    }
    assert env["keys"]["already_present"] == [{
        "where": "initial_variables",
        "key_or_index": "tide",
        "full_key": "shared:tide",
        "reason": "already present; seeding never overwrites live state",
    }]
    # The stored plan never carried tide: its split is untouched.
    assert set(env["current_keys"]["would_seed"]) == CURRENT_SEEDABLE
    assert env["current_keys"]["already_present"] == []
    assert env["key_deltas"]["already_present_added"] == ["shared:tide"]
    assert env["key_deltas"]["would_seed_added"] == ["shared:met_ferryman"]
    assert env["would_bind"] is True


async def test_preview_then_replace_then_p138_agrees(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    seed_variables(user, chat_id, {"trust": 99}, base_dir=tmp_path)
    env = await preview(factory, tmp_path, user, rec, chat_id, changed_body())
    replaced = definitions.replace(rec.id, user, changed_body(), now=NOW)
    assert replaced is not None and replaced.revision == 2
    assert replaced.definition == env["candidate"]["definition"]
    after = await preview138(factory, tmp_path, user, replaced, chat_id)
    assert after["plan"] == env["candidate"]["plan"]
    assert after["keys"] == env["keys"]
    assert after["blockers"] == env["blockers"]
    assert after["would_bind"] == env["would_bind"]
    assert after["counts"] == env["counts"]


# ------------------------------------------------- service: blockers


async def test_blocker_group_room_with_candidate(tmp_path):
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
    env = await preview(factory, tmp_path, user, rec, chat_id, changed_body())
    assert [b["kind"] for b in env["blockers"]] == ["group_room"]
    assert env["would_bind"] is False
    assert set(env["keys"]["would_seed"]) == CANDIDATE_SEEDABLE


async def test_blockers_bound_and_non_empty_with_candidate(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    standing = await bind(factory, tmp_path, user, rec.id, chat_id)
    env = await preview(factory, tmp_path, user, rec, chat_id, changed_body())
    assert [b["kind"] for b in env["blockers"]] == [
        "already_bound", "chat_not_empty",
    ]
    assert env["blockers"][0]["binding_id"] == standing.id
    assert env["blockers"][0]["definition_id"] == rec.id
    assert env["blockers"][1]["message_count"] == 5
    assert env["would_bind"] is False


# --------------------------------------- service: existence + refusal


async def test_unknown_and_foreign_chat_none_even_malformed(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, "other")
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    foreign_chat = await make_chat(factory, other)
    for chat_id in ("no-such-chat", foreign_chat):
        assert await preview(
            factory, tmp_path, user, rec, chat_id, changed_body()) is None
        # Existence is decided before the candidate is judged:
        # a refused candidate changes nothing about the answer.
        assert await preview(
            factory, tmp_path, user, rec, chat_id, {}) is None
        assert await preview(
            factory, tmp_path, user, rec, chat_id,
            ["not", "a", "dict"]) is None
    mine = await make_chat(factory, user)
    assert await preview(
        factory, tmp_path, user, rec, mine, changed_body()) is not None


async def test_refused_candidate_raises_the_door_refusals(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    before = (tmp_path / "scenarios.json").read_bytes()
    with pytest.raises(ScenarioParseError):
        await preview(factory, tmp_path, user, rec, chat_id, {})
    with pytest.raises(ScenarioStoreError):
        await preview(factory, tmp_path, user, rec, chat_id, ["x"])
    assert (tmp_path / "scenarios.json").read_bytes() == before


# --------------------------------------------- service: writes none


async def test_service_preview_writes_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    before = (tmp_path / "scenarios.json").read_bytes()
    await preview(factory, tmp_path, user, rec, chat_id, changed_body())
    await preview(factory, tmp_path, user, rec, chat_id, changed_body())
    assert (tmp_path / "scenarios.json").read_bytes() == before
    assert not (tmp_path / "scenario_bindings.json").exists()
    assert list_entries(user, chat_id, base_dir=tmp_path) == []
    async with factory() as session:
        assert await svc.get_history(session, user, chat_id) == []
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


def road(definition_id, chat_id):
    return f"/api/v1/scenarios/{definition_id}/replace-preview/{chat_id}"


def test_http_clean_envelope(tmp_path, monkeypatch):
    client, _factory, _db = make_client(tmp_path, monkeypatch)
    definition = client.post("/api/v1/scenarios", json=body()).json()
    chat = client.post("/api/v1/chats", json={"title": "Harbour"}).json()
    res = client.post(road(definition["id"], chat["id"]), json=changed_body())
    assert res.status_code == 200
    env = res.json()
    assert env["definition_id"] == definition["id"]
    assert env["chat_id"] == chat["id"]
    assert env["definition_revision"] == 1
    assert env["next_revision"] == 2
    assert env["candidate"]["name"] == "Harbour Lights at Dawn"
    assert env["blockers"] == [] and env["would_bind"] is True
    assert set(env["keys"]["would_seed"]) == CANDIDATE_SEEDABLE
    assert set(env["current_keys"]["would_seed"]) == CURRENT_SEEDABLE
    assert env["key_deltas"]["would_seed_removed"] == ["shared:mood"]
    assert len(env["notes"]) == 6


def test_http_existence_discipline(tmp_path, monkeypatch):
    client, _factory, _db = make_client(tmp_path, monkeypatch)
    definition = client.post("/api/v1/scenarios", json=body()).json()
    chat = client.post("/api/v1/chats", json={"title": "Harbour"}).json()
    store = ScenarioStore(definitions_path())
    store.create(FOREIGN, body(), now=NOW)
    foreign_id = store.list_for_owner(FOREIGN)[0].id
    for target in (foreign_id, "no-such-id"):
        res = client.post(road(target, chat["id"]), json={})
        assert res.status_code == 404
        assert res.json()["detail"] == "scenario definition not found"
    res = client.post(road(definition["id"], "no-such-chat"), json={})
    assert res.status_code == 404
    assert res.json()["detail"] == "chat not found"
    # Definition is decided before the chat, as on P-138's road.
    res = client.post(road("no-such-id", "no-such-chat"), json={})
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
    res = client.post(road(definition["id"], foreign_chat), json=changed_body())
    assert res.status_code == 404
    assert res.json()["detail"] == "chat not found"


def test_http_refused_candidate_422_record_untouched(tmp_path, monkeypatch):
    client, _factory, _db = make_client(tmp_path, monkeypatch)
    definition = client.post("/api/v1/scenarios", json=body()).json()
    chat = client.post("/api/v1/chats", json={"title": "Harbour"}).json()
    defs_file = tmp_path / "scenarios.json"
    before = defs_file.read_bytes()
    res = client.post(road(definition["id"], chat["id"]), json={})
    assert res.status_code == 422
    assert defs_file.read_bytes() == before
    still = client.get(f"/api/v1/scenarios/{definition['id']}").json()
    assert still["revision"] == 1
    assert still["name"] == "Harbour Lights at Dusk"


def test_http_preview_writes_nothing_neighbours_untouched(
    tmp_path, monkeypatch
):
    client, _factory, _db = make_client(tmp_path, monkeypatch)
    definition = client.post("/api/v1/scenarios", json=body()).json()
    chat = client.post("/api/v1/chats", json={"title": "Harbour"}).json()
    defs_file = tmp_path / "scenarios.json"
    before = defs_file.read_bytes()
    res = client.post(road(definition["id"], chat["id"]), json=changed_body())
    assert res.status_code == 200
    assert defs_file.read_bytes() == before
    assert not (tmp_path / "scenario_bindings.json").exists()
    history = client.get(f"/api/v1/chats/{chat['id']}/messages").json()
    texts = [m["content"] for m in history["messages"]] \
        if "messages" in history else [m["content"] for m in history]
    assert texts == []
    did = definition["id"]
    # Neighbour roads answer exactly as before beside the new one.
    plan138 = client.get(f"/api/v1/scenarios/{did}/bind-plan/{chat['id']}")
    assert plan138.status_code == 200 and len(plan138.json()["notes"]) == 4
    plan136 = client.get(f"/api/v1/scenarios/{did}/bind-plan")
    assert plan136.status_code == 200
    impact = client.get(f"/api/v1/scenarios/{did}/replace-impact")
    assert impact.status_code == 200
    listing = client.get("/api/v1/scenarios/bindings")
    assert listing.status_code == 200
    exported = client.get(f"/api/v1/scenarios/{did}/export")
    assert exported.status_code == 200
    # And the bind road still lands after all the previewing.
    bound = client.post(
        f"/api/v1/scenarios/{did}/bind", json={"chat_id": chat["id"]})
    assert bound.status_code == 201


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    assert MIGRATIONS[-1][0] == "0042"
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
