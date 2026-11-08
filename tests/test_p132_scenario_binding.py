"""P-132 — Scenario-to-chat binding (Part IX, DERIVED scope).

Pins: the pure materialisation plan (kind -> chat-role
map, cast-resolved speaker names with no fabricated ids,
blank / non-string bootstrap entries skipped with
reasons, P-093 seedability decided by the P-093 store's
own law); the binding store (versioned JSON, tolerant
load, owner scoping on every verb); the bind service
(bootstrap lines land in order as the chat's opening
messages with exact author text, P-075 provenance naming
the definition + pinned revision + bootstrap index,
flags / variables seeded through P-093 under the
scenario writer with missing-keys-only honesty, skipped
entries accounted in the record, every refusal decided
before any write — foreign / unknown, non-empty chat,
group room, double bind); unbind removing only the
record; the HTTP roads (201 / 404 / 409 / 422, GET +
DELETE, P-131 and P-026 roads untouched beside them);
and the migration head pinned at 0041. No network:
fixtures only.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import service as svc
from runmal.chats.provenance import active_view
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Chat, Group, User
from runmal.plugins.variables import list_entries
from runmal.scenarios.binding import (
    BindingConflictError,
    BindingNotFoundError,
    ScenarioBindingStore,
    bind_scenario,
    get_binding,
    plan_materialisation,
    unbind,
)
from runmal.scenarios.store import ScenarioStore

NOW = "2026-11-08T13:00:00+00:00"

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


async def bind(factory, tmp_path, user_id, definition_id, chat_id):
    definitions, bindings = stores(tmp_path)
    async with factory() as session:
        return await bind_scenario(
            session, user_id, definition_id, chat_id,
            definitions=definitions, bindings=bindings,
            variables_base_dir=tmp_path, now=NOW)


async def history(factory, user_id, chat_id):
    async with factory() as session:
        rows = await svc.get_history(session, user_id, chat_id)
        assert rows is not None
        return rows


# ------------------------------------------------------- pure: plan


def test_plan_role_map_and_speakers():
    plan = plan_materialisation(_definition())
    assert [(m["kind"], m["chat_role"]) for m in plan["messages"]] == [
        ("instructions", "system"), ("note", "assistant"),
        ("char", "assistant"), ("user", "user"), ("story", "assistant"),
    ]
    assert [m["speaker_name"] for m in plan["messages"]] == [
        None, "Maera", "Keeper", "Ash", "The Harbour Voice",
    ]
    assert [m["bootstrap_index"] for m in plan["messages"]] == [0, 1, 2, 3, 4]


def _definition() -> dict:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        rec = ScenarioStore(Path(td) / "s.json").create("owner-x", body(), now=NOW)
        return rec.definition


def test_plan_skips_blank_and_records_reasons():
    plan = plan_materialisation(_definition())
    skipped = {(s["where"], s["key_or_index"]): s["reason"] for s in plan["skipped"]}
    assert "blank" in skipped[("bootstrap", 5)]
    assert "not a bool" in skipped[("initial_flags", "bad_flag")]
    assert "not a typed scalar" in skipped[("initial_variables", "nested")]
    assert "key refused" in skipped[("initial_variables", "bad key!")]
    assert plan["flags"] == {"met_maera": True}
    assert plan["variables"] == {"trust": 2, "mood": "calm"}


def test_plan_empty_definition_plans_nothing():
    plan = plan_materialisation({"name": "Bare"})
    assert plan == {"messages": [], "flags": {}, "variables": {}, "skipped": []}


# ------------------------------------------------------ store pins


def test_binding_store_round_trip_and_scoping(tmp_path):
    _, bindings = stores(tmp_path)
    from runmal.scenarios.binding import ScenarioBinding

    rec = ScenarioBinding(
        id="b1", owner_id="o1", chat_id="c1", definition_id="d1",
        definition_name="Harbour", definition_revision=3, bound_at=NOW,
        cast=[{"name": "Narrator"}], seeded_keys=["shared:trust"])
    bindings.add(rec)
    fresh = ScenarioBindingStore(tmp_path / "scenario_bindings.json")
    assert fresh.get_for_chat("c1", "o1") == rec
    assert fresh.get_for_chat("c1", "other") is None
    assert fresh.get_for_chat("nope", "o1") is None
    assert fresh.list_for_definition("d1", "o1") == [rec]
    assert fresh.list_for_owner("o1") == [rec]
    assert fresh.remove_for_chat("c1", "other") is None
    assert fresh.remove_for_chat("c1", "o1") == rec
    assert fresh.get_for_chat("c1", "o1") is None


def test_binding_store_tolerant_load(tmp_path):
    path = tmp_path / "scenario_bindings.json"
    path.write_text("{corrupt")
    assert ScenarioBindingStore(path).list_for_owner("o1") == []
    path.write_text(json.dumps({"version": 1, "bindings": "nope"}))
    assert ScenarioBindingStore(path).list_for_owner("o1") == []


# ---------------------------------------------------- service pins


async def test_bind_materialises_opening(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    binding = await bind(factory, tmp_path, user, rec.id, chat_id)
    assert binding.owner_id == user and binding.chat_id == chat_id
    assert binding.definition_id == rec.id
    assert binding.definition_revision == 1 and binding.bound_at == NOW
    assert binding.cast == rec.definition["roles"]
    rows = await history(factory, user, chat_id)
    assert [m.content for m in rows] == [
        "Keep the lamps lit.", "The tide is going out.",
        "You came back.", "I never left.", "Gulls settle on the mast.",
    ]
    assert [m.role for m in rows] == [
        "system", "assistant", "assistant", "user", "assistant"]
    assert [m.speaker_name for m in rows] == [
        None, "Maera", "Keeper", "Ash", "The Harbour Voice"]
    assert all(m.speaker_id is None for m in rows)
    # the append road's own position law: a chat built purely
    # from appends is a legacy-ordered chat (positions NULL,
    # display order by created_at) - the binding invents no
    # second ordering law over it
    assert [m.position for m in rows] == [None] * 5
    assert [s["message_id"] for s in binding.seeded_messages] == [m.id for m in rows]
    assert [s["bootstrap_index"] for s in binding.seeded_messages] == [0, 1, 2, 3, 4]


async def test_bind_provenance_names_definition(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _ = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    await bind(factory, tmp_path, user, rec.id, chat_id)
    rows = await history(factory, user, chat_id)
    for index, message in enumerate(rows):
        view = active_view(message, 0)
        assert view["recorded"] is True
        assert view["origin"]["kind"] == "manual"
        assert view["origin"]["source"] == "scenario_bootstrap"
        assert view["origin"]["definition_id"] == rec.id
        assert view["origin"]["definition_revision"] == 1
        assert view["origin"]["bootstrap_index"] == index
        assert view["model"]["status"] == "not_applicable"
        assert view["lore"]["status"] == "not_applicable"


async def test_bind_seeds_state_through_p093(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _ = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    binding = await bind(factory, tmp_path, user, rec.id, chat_id)
    # flags seed before variables (the service's law); within
    # a mapping the order is the stored definition's own -
    # the P-131 store writes sort_keys, so mood precedes trust
    assert binding.seeded_keys == [
        "shared:met_maera", "shared:mood", "shared:trust"]
    entries = list_entries(user, chat_id, base_dir=tmp_path)
    by_key = {e["key"]: e for e in entries}
    assert by_key["shared:met_maera"]["kind"] == "flag"
    assert by_key["shared:met_maera"]["value"] is True
    assert by_key["shared:trust"]["value"] == 2
    assert by_key["shared:mood"]["value"] == "calm"
    for entry in entries:
        assert entry["writer_kind"] == "scenario"
        assert entry["writer_id"] == "runmal.scenario"
    skipped = {(s["where"], s["key_or_index"]) for s in binding.skipped}
    assert ("bootstrap", 5) in skipped
    assert ("initial_flags", "bad_flag") in skipped
    assert ("initial_variables", "nested") in skipped
    assert ("initial_variables", "bad key!") in skipped


async def test_bind_records_already_present_keys(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _ = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    from runmal.plugins.variables import set_variable

    set_variable(user, chat_id, "trust", 99, writer_kind="host",
                 writer_id="runmal.host", base_dir=tmp_path)
    binding = await bind(factory, tmp_path, user, rec.id, chat_id)
    assert "shared:trust" not in binding.seeded_keys
    entries = {e["key"]: e for e in list_entries(user, chat_id, base_dir=tmp_path)}
    assert entries["shared:trust"]["value"] == 99  # never overwritten
    assert any(
        s["where"] == "initial_variables" and s["key_or_index"] == "trust"
        and "already present" in s["reason"] for s in binding.skipped)


async def test_bind_pins_revision_at_bind_time(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    await bind(factory, tmp_path, user, rec.id, chat_id)
    changed = body()
    changed["name"] = "Renamed Harbour"
    definitions.replace(rec.id, user, changed, now=NOW)
    binding = get_binding(bindings, user, chat_id)
    assert binding.definition_revision == 1
    assert binding.definition_name == "Harbour Lights at Dusk"


async def test_bind_refusals_write_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, "other")
    definitions, bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    foreign = definitions.create(other, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    foreign_chat = await make_chat(factory, other)
    async with factory() as session:
        with pytest.raises(BindingNotFoundError):
            await bind_scenario(session, user, "no-such", chat_id,
                                definitions=definitions, bindings=bindings,
                                variables_base_dir=tmp_path)
        with pytest.raises(BindingNotFoundError):
            await bind_scenario(session, user, foreign.id, chat_id,
                                definitions=definitions, bindings=bindings,
                                variables_base_dir=tmp_path)
        with pytest.raises(BindingNotFoundError):
            await bind_scenario(session, user, rec.id, foreign_chat,
                                definitions=definitions, bindings=bindings,
                                variables_base_dir=tmp_path)
        with pytest.raises(BindingNotFoundError):
            await bind_scenario(session, user, rec.id, "no-such-chat",
                                definitions=definitions, bindings=bindings,
                                variables_base_dir=tmp_path)
    assert await history(factory, user, chat_id) == []
    assert bindings.list_for_owner(user) == []
    assert list_entries(user, chat_id, base_dir=tmp_path) == []


async def test_bind_conflicts_write_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    busy = await make_chat(factory, user, "Busy")
    async with factory() as session:
        await svc.append_message(session, user, busy, "user", "Already talking.")
        with pytest.raises(BindingConflictError):
            await bind_scenario(session, user, rec.id, busy,
                                definitions=definitions, bindings=bindings,
                                variables_base_dir=tmp_path)
    group_chat = await make_chat(factory, user, "Room")
    async with factory() as session:
        group = Group(user_id=user, name="Room")
        session.add(group)
        await session.flush()
        chat = await session.get(Chat, group_chat)
        chat.group_id = group.id
        await session.commit()
    async with factory() as session:
        with pytest.raises(BindingConflictError):
            await bind_scenario(session, user, rec.id, group_chat,
                                definitions=definitions, bindings=bindings,
                                variables_base_dir=tmp_path)
    chat_id = await make_chat(factory, user)
    await bind(factory, tmp_path, user, rec.id, chat_id)
    async with factory() as session:
        with pytest.raises(BindingConflictError):
            await bind_scenario(session, user, rec.id, chat_id,
                                definitions=definitions, bindings=bindings,
                                variables_base_dir=tmp_path)
    assert len(bindings.list_for_owner(user)) == 1
    assert len(await history(factory, user, chat_id)) == 5


async def test_unbind_removes_only_the_record(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = stores(tmp_path)
    rec = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    binding = await bind(factory, tmp_path, user, rec.id, chat_id)
    assert unbind(bindings, user, chat_id) == binding
    assert get_binding(bindings, user, chat_id) is None
    assert unbind(bindings, user, chat_id) is None
    assert len(await history(factory, user, chat_id)) == 5  # seeded lines stay
    assert len(list_entries(user, chat_id, base_dir=tmp_path)) == 3  # state stays
    # the chat is no longer empty, so a fresh bind refuses
    async with factory() as session:
        with pytest.raises(BindingConflictError):
            await bind_scenario(session, user, rec.id, chat_id,
                                definitions=definitions, bindings=bindings,
                                variables_base_dir=tmp_path)


# --------------------------------------------------------- HTTP


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    app = create_app(factory)
    client = TestClient(app)
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _http_setup(client):
    definition = client.post("/api/v1/scenarios", json=body()).json()
    chat = client.post("/api/v1/chats", json={"title": "Harbour"}).json()
    return definition, chat


def test_http_bind_201_and_record(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition, chat = _http_setup(client)
    res = client.post(
        f"/api/v1/scenarios/{definition['id']}/bind", json={"chat_id": chat["id"]})
    assert res.status_code == 201
    row = res.json()
    assert row["chat_id"] == chat["id"]
    assert row["definition_id"] == definition["id"]
    assert row["definition_revision"] == 1
    assert row["seeded_keys"] == ["shared:met_maera", "shared:mood", "shared:trust"]
    assert len(row["seeded_messages"]) == 5
    assert len(row["skipped"]) == 4
    history = client.get(f"/api/v1/chats/{chat['id']}/messages").json()
    texts = [m["content"] for m in history["messages"]] if "messages" in history else [
        m["content"] for m in history]
    assert texts == [
        "Keep the lamps lit.", "The tide is going out.", "You came back.",
        "I never left.", "Gulls settle on the mast."]


def test_http_get_and_delete_binding(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition, chat = _http_setup(client)
    assert client.get(f"/api/v1/scenarios/bindings/{chat['id']}").status_code == 404
    client.post(f"/api/v1/scenarios/{definition['id']}/bind", json={"chat_id": chat["id"]})
    got = client.get(f"/api/v1/scenarios/bindings/{chat['id']}")
    assert got.status_code == 200
    assert got.json()["definition_id"] == definition["id"]
    res = client.delete(f"/api/v1/scenarios/bindings/{chat['id']}")
    assert res.status_code == 200
    assert res.json()["unbound"] is True
    assert res.json()["seeded_content_kept"] is True
    assert client.get(f"/api/v1/scenarios/bindings/{chat['id']}").status_code == 404
    assert client.delete(f"/api/v1/scenarios/bindings/{chat['id']}").status_code == 404


def test_http_bind_refusals(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition, chat = _http_setup(client)
    assert client.post(
        "/api/v1/scenarios/no-such/bind", json={"chat_id": chat["id"]}
    ).status_code == 404
    assert client.post(
        f"/api/v1/scenarios/{definition['id']}/bind", json={"chat_id": "no-such"}
    ).status_code == 404
    assert client.post(
        f"/api/v1/scenarios/{definition['id']}/bind", json={}
    ).status_code == 422
    assert client.post(
        f"/api/v1/scenarios/{definition['id']}/bind", json={"chat_id": 7}
    ).status_code == 422
    ok = client.post(
        f"/api/v1/scenarios/{definition['id']}/bind", json={"chat_id": chat["id"]})
    assert ok.status_code == 201
    again = client.post(
        f"/api/v1/scenarios/{definition['id']}/bind", json={"chat_id": chat["id"]})
    assert again.status_code == 409


def test_http_p131_and_p026_roads_untouched(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition, chat = _http_setup(client)
    client.post(f"/api/v1/scenarios/{definition['id']}/bind", json={"chat_id": chat["id"]})
    got = client.get(f"/api/v1/scenarios/{definition['id']}")
    assert got.status_code == 200 and got.json()["revision"] == 1
    listing = client.get("/api/v1/scenarios").json()
    assert listing["total"] == 1
    imported = client.post("/api/v1/scenarios/import", json=body())
    assert imported.status_code == 200
    assert imported.json()["scenario"]["name"] == "Harbour Lights at Dusk"


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    assert MIGRATIONS[-1][0] == "0041"
