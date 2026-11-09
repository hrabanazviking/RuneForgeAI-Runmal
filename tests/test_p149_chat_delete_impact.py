"""P-149 - Chat delete-impact preview (Part IX, DERIVED).

Pins: the leak-free None (unknown chat, foreign chat,
foreign binding - all alike); the honest zero for an
owned unbound chat; the full envelope for a really-bound
live chat (P-132's record verbatim, P-144's current
state, impact counts read from the record); the
definition axis judged beside the chat axis (superseded
after a real replace, stale after a real definition
delete, ahead on a hand-damaged pin); the
already-orphaned answers (after a REAL chat deletion,
for a never-existent chat id, and for another owner's
chat - existence judged owner-scoped on both sides);
today's no-cascade law pinned on BOTH sides (delete_chat
leaves the binding document byte-untouched and the
per-chat binding read still answers the orphan, while
the unbind road still removes it); writes-nothing at
service and HTTP level (both store documents
byte-untouched, chat history untouched); the HTTP road
(404 shape, owner isolation, neighbour roads untouched
beside it); and the migration head pinned at 0041.
No network: fixtures only.
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
    get_binding,
)
from runmal.scenarios.chatdeletepreview import (
    preview_chat_delete_impact,
)
from runmal.scenarios.store import ScenarioStore, definitions_path

NOW = "2026-11-08T20:00:00+00:00"
OWNER = "owner-p149"
FOREIGN = "foreign-p149"

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


async def _preview(factory, tmp_path, owner, chat_id):
    definitions, bindings = _stores(tmp_path)
    async with factory() as session:
        return await preview_chat_delete_impact(
            session, bindings, definitions, owner, chat_id)


async def _real_bind(factory, tmp_path, user, record_id, chat_id):
    definitions, bindings = _stores(tmp_path)
    async with factory() as session:
        return await bind_scenario(
            session, user, record_id, chat_id,
            definitions=definitions, bindings=bindings,
            variables_base_dir=tmp_path, now=NOW)


ZERO_IMPACT = {
    "binding_would_orphan": False,
    "binding_already_orphaned": False,
    "seeded_message_count": 0,
    "seeded_key_count": 0,
    "cast_count": 0,
}


# ------------------------------------------------------- service


async def test_service_unknown_chat_answers_none(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    out = await _preview(factory, tmp_path, user, "chat-ghost")
    assert out is None


async def test_service_owned_unbound_chat_is_the_honest_zero(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await make_chat(factory, user)
    out = await _preview(factory, tmp_path, user, chat_id)
    assert out["chat_id"] == chat_id
    assert out["chat_exists"] is True
    assert out["binding"] is None
    assert out["binding_state"] is None
    assert out["definition_exists"] is None
    assert out["definition_current_revision"] is None
    assert out["definition_current_name"] is None
    assert out["impact"] == ZERO_IMPACT
    assert len(out["notes"]) == 5


async def test_service_bound_live_chat_full_envelope(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bound = await _real_bind(factory, tmp_path, user, record.id, chat_id)
    out = await _preview(factory, tmp_path, user, chat_id)
    assert out["chat_exists"] is True
    assert out["binding"] == bound.to_dict()
    assert out["binding_state"] == "current"
    assert out["definition_exists"] is True
    assert out["definition_current_revision"] == 1
    assert out["definition_current_name"] == record.name
    impact = out["impact"]
    assert impact["binding_would_orphan"] is True
    assert impact["binding_already_orphaned"] is False
    assert impact["seeded_message_count"] == len(bound.seeded_messages) == 2
    assert impact["seeded_key_count"] == len(bound.seeded_keys)
    assert impact["seeded_key_count"] >= 1
    assert impact["cast_count"] == len(bound.cast) == 1


async def test_service_superseded_pin_beside_live_chat(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    await _real_bind(factory, tmp_path, user, record.id, chat_id)
    definitions.replace(record.id, user, revised_body(), now=NOW)
    out = await _preview(factory, tmp_path, user, chat_id)
    assert out["chat_exists"] is True
    assert out["binding_state"] == "superseded"
    assert out["binding"]["definition_revision"] == 1
    assert out["definition_current_revision"] == 2
    assert out["impact"]["binding_would_orphan"] is True


async def test_service_stale_after_definition_delete(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    await _real_bind(factory, tmp_path, user, record.id, chat_id)
    definitions.remove(record.id, user)
    out = await _preview(factory, tmp_path, user, chat_id)
    assert out["chat_exists"] is True
    assert out["binding_state"] == "stale"
    assert out["definition_exists"] is False
    assert out["definition_current_revision"] is None
    assert out["definition_current_name"] is None
    assert out["impact"]["binding_would_orphan"] is True


async def test_service_ahead_pin_is_named(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bindings.add(_rec("b1", user, chat_id, record.id,
                      name=record.name, rev=99))
    out = await _preview(factory, tmp_path, user, chat_id)
    assert out["binding_state"] == "ahead"
    assert out["definition_current_revision"] == 1
    assert out["impact"]["binding_would_orphan"] is True


async def test_service_already_orphaned_after_real_delete(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    bound = await _real_bind(factory, tmp_path, user, record.id, chat_id)
    binds_file = tmp_path / "scenario_bindings.json"
    before = binds_file.read_bytes()
    async with factory() as session:
        assert await svc.delete_chat(session, user, chat_id) is True
    # today's law, pinned on the chats side: chat deletion
    # cleans its own custodies but never the binding store
    assert binds_file.read_bytes() == before
    out = await _preview(factory, tmp_path, user, chat_id)
    assert out is not None
    assert out["chat_exists"] is False
    assert out["binding"] == bound.to_dict()
    assert out["binding_state"] == "current"
    assert out["impact"]["binding_would_orphan"] is False
    assert out["impact"]["binding_already_orphaned"] is True
    # and on the scenario side: the per-chat read still
    # answers the orphan as if live, and unbind still
    # removes it - the custody facts this preview names
    assert get_binding(bindings, user, chat_id) is not None
    from runmal.scenarios.binding import unbind

    assert unbind(bindings, user, chat_id) is not None
    out = await _preview(factory, tmp_path, user, chat_id)
    assert out is None


async def test_service_never_existent_chat_with_binding(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    bindings.add(_rec("b1", user, "chat-ghost", record.id,
                      name=record.name, rev=1))
    out = await _preview(factory, tmp_path, user, "chat-ghost")
    assert out is not None
    assert out["chat_exists"] is False
    assert out["impact"]["binding_already_orphaned"] is True
    assert out["impact"]["seeded_message_count"] == 1
    assert out["impact"]["seeded_key_count"] == 1
    assert out["impact"]["cast_count"] == 1


async def test_service_foreign_chat_with_own_binding(tmp_path):
    factory = make_factory(tmp_path)
    mine = await make_user(factory, "mine")
    theirs = await make_user(factory, "theirs")
    definitions, bindings = _stores(tmp_path)
    my_record = definitions.create(mine, body(), now=NOW)
    chat_id = await make_chat(factory, theirs)
    bindings.add(_rec("b1", mine, chat_id, my_record.id,
                      name=my_record.name, rev=1))
    # for the caller the chat does not exist (owner-scoped
    # existence), and their own binding reads already
    # orphaned - nothing about the other owner leaks
    out = await _preview(factory, tmp_path, mine, chat_id)
    assert out is not None
    assert out["chat_exists"] is False
    assert out["impact"]["binding_already_orphaned"] is True
    # for the chat's owner, with no binding of their own,
    # the same chat is the honest zero
    out = await _preview(factory, tmp_path, theirs, chat_id)
    assert out is not None
    assert out["chat_exists"] is True
    assert out["binding"] is None
    assert out["impact"] == ZERO_IMPACT


async def test_service_foreign_binding_and_chat_answer_none(tmp_path):
    factory = make_factory(tmp_path)
    mine = await make_user(factory, "mine")
    theirs = await make_user(factory, "theirs")
    definitions, bindings = _stores(tmp_path)
    their_record = definitions.create(theirs, body(), now=NOW)
    chat_id = await make_chat(factory, theirs)
    bindings.add(_rec("b1", theirs, chat_id, their_record.id,
                      name=their_record.name, rev=1))
    out = await _preview(factory, tmp_path, mine, chat_id)
    assert out is None


async def test_service_preview_writes_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    definitions, _bindings = _stores(tmp_path)
    record = definitions.create(user, body(), now=NOW)
    chat_id = await make_chat(factory, user)
    await _real_bind(factory, tmp_path, user, record.id, chat_id)
    binds_file = tmp_path / "scenario_bindings.json"
    defs_file = tmp_path / "scenarios.json"
    before = (binds_file.read_bytes(), defs_file.read_bytes())
    await _preview(factory, tmp_path, user, chat_id)
    assert (binds_file.read_bytes(), defs_file.read_bytes()) == before
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
    assert len(history) == 2


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


def test_http_unknown_chat_is_404(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    res = client.get("/api/v1/scenarios/bindings/chat-ghost/delete-impact")
    assert res.status_code == 404
    assert res.json()["detail"] == "chat not found"


def test_http_owned_unbound_chat_zero_envelope(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat = client.post("/api/v1/chats", json={"title": "Harbour"}).json()
    res = client.get(
        f"/api/v1/scenarios/bindings/{chat['id']}/delete-impact")
    assert res.status_code == 200
    out = res.json()
    assert out["chat_exists"] is True
    assert out["binding"] is None
    assert out["impact"] == ZERO_IMPACT
    assert len(out["notes"]) == 5


def test_http_bound_then_deleted_then_unbound(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _bind(client, definition["id"])
    url = f"/api/v1/scenarios/bindings/{chat['id']}/delete-impact"
    out = client.get(url).json()
    assert out["chat_exists"] is True
    assert out["binding_state"] == "current"
    assert out["binding"]["chat_id"] == chat["id"]
    assert out["impact"]["binding_would_orphan"] is True
    assert out["impact"]["seeded_message_count"] == 2
    res = client.delete(f"/api/v1/chats/{chat['id']}")
    assert res.status_code == 200
    # the preview still answers for the orphaned binding -
    # it does not collapse into the 404 case
    res = client.get(url)
    assert res.status_code == 200
    out = res.json()
    assert out["chat_exists"] is False
    assert out["impact"]["binding_already_orphaned"] is True
    assert out["impact"]["binding_would_orphan"] is False
    res = client.delete(f"/api/v1/scenarios/bindings/{chat['id']}")
    assert res.status_code == 200
    assert client.get(url).status_code == 404


def test_http_preview_is_owner_scoped(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    _bind(client, definition["id"])
    store = ScenarioStore(definitions_path())
    foreign = store.create(FOREIGN, body(), now=NOW)
    bstore = ScenarioBindingStore(bindings_path())
    bstore.add(_rec("bf", FOREIGN, "chat-foreign", foreign.id, rev=1))
    res = client.get("/api/v1/scenarios/bindings/chat-foreign/delete-impact")
    assert res.status_code == 404


def test_http_preview_writes_nothing(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _bind(client, definition["id"])
    binds_file = tmp_path / "scenario_bindings.json"
    defs_file = tmp_path / "scenarios.json"
    before = (binds_file.read_bytes(), defs_file.read_bytes())
    res = client.get(
        f"/api/v1/scenarios/bindings/{chat['id']}/delete-impact")
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
    assert client.get(f"{base}/bindings").status_code == 200
    assert client.get(f"{base}/bind-plan").status_code == 200
    assert client.get(f"{base}/delete-impact").status_code == 200
    assert client.get(f"{base}/replace-impact").status_code == 200
    assert client.get(
        f"/api/v1/scenarios/bindings/{chat['id']}").status_code == 200
    assert client.get(
        f"/api/v1/scenarios/bindings/{chat['id']}/delete-impact"
    ).status_code == 200


# ----------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
    assert MIGRATIONS[-1][0] == "0042"
