"""S602 acceptance: versioned bridge conversation-state API.

Contract tests for BRIDGE_PROTOCOL §3/§6/§7: state read, turn writes
with speaker kinds + provenance, ownership/scope enforcement on every
operation, and server-composed generation whose finished turn lands in
the chat as the active persona.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

CARD = {
    "name": "Bridge Warden",
    "description": "Keeper of the bridge at TESTHOLD.",
    "personality": "Stern but fair.",
    "scenario": "A stone bridge over a cold river.",
    "first_mes": "State your business.",
    "system_prompt": "You are the Bridge Warden of TESTHOLD.",
}


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    client.headers.update({"Authorization": f"Bearer {get_or_create_credential()}"})
    return client


def _bridge(client, scopes, name="bridge"):
    created = client.post(
        "/api/v1/bridge/credentials", json={"name": name, "scopes": scopes}
    ).json()
    return {"Authorization": f"Bearer {created['token']}"}


def _world(client, with_persona=True):
    character = client.post("/api/v1/characters", json={"card": CARD}).json()
    body = {"title": "Bridge chat"}
    if with_persona:
        body["character_id"] = character["id"]
    chat = client.post("/api/v1/chats", json=body).json()
    return character, chat


def _scopes(chat_id, *extras):
    return [f"chat:read:{chat_id}", f"chat:write:{chat_id}", *extras]


def _sse_events(response):
    events = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


# --- state read --------------------------------------------------------------


def test_state_read_shape_and_persona(app_client) -> None:
    character, chat = _world(app_client)
    headers = _bridge(app_client, _scopes(chat["id"]))
    response = app_client.get(f"/api/v1/bridge/chats/{chat['id']}", headers=headers)
    assert response.status_code == 200
    state = response.json()
    assert state["protocol_version"] == "1"
    assert state["chat"]["id"] == chat["id"]
    assert state["persona"] == {
        "character_id": character["id"],
        "name": "Bridge Warden",
    }
    assert state["messages"] == []


def test_state_read_scope_and_existence(app_client) -> None:
    _, chat = _world(app_client)
    other = _bridge(app_client, _scopes("some-other-chat"))
    response = app_client.get(f"/api/v1/bridge/chats/{chat['id']}", headers=other)
    assert response.status_code == 403  # scoped to a different chat
    star = _bridge(app_client, ["chat:read:*"])
    response = app_client.get("/api/v1/bridge/chats/does-not-exist", headers=star)
    assert response.status_code == 404


# --- turn writes ---------------------------------------------------------------


def test_append_user_turn_and_provenance(app_client) -> None:
    _, chat = _world(app_client)
    headers = _bridge(app_client, _scopes(chat["id"]))
    response = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns",
        headers=headers,
        json={
            "speaker_kind": "user",
            "content": "I seek passage.",
            "speaker_name": "Traveller",
            "bridge_timestamp": "2026-10-13T09:00:00Z",
            "metadata": {"world": "testhold"},
        },
    )
    assert response.status_code == 201, response.text
    message = response.json()
    assert message["role"] == "user"
    assert message["speaker_name"] == "Traveller"

    state = app_client.get(f"/api/v1/bridge/chats/{chat['id']}", headers=headers).json()
    assert [m["id"] for m in state["messages"]] == [message["id"]]

    events = app_client.get(f"/api/v1/chats/{chat['id']}/events").json()
    appended = [e for e in events if e["kind"] == "message.appended"]
    assert appended[-1]["data"]["source"] == "bridge"
    assert appended[-1]["data"]["bridge_timestamp"] == "2026-10-13T09:00:00Z"
    assert appended[-1]["data"]["metadata"] == {"world": "testhold"}
    assert appended[-1]["data"]["bridge_id"]


def test_append_companion_and_environment_turns(app_client) -> None:
    character, chat = _world(app_client)
    headers = _bridge(app_client, _scopes(chat["id"]))
    companion = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns",
        headers=headers,
        json={"speaker_kind": "companion", "content": "Pass, friend."},
    ).json()
    # Companion turns default to the chat's active persona, snapshotted.
    assert companion["role"] == "assistant"
    assert companion["speaker_id"] == character["id"]
    assert companion["speaker_name"] == "Bridge Warden"

    environment = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns",
        headers=headers,
        json={"speaker_kind": "environment", "content": "The river rises."},
    ).json()
    assert environment["role"] == "system"
    assert environment["speaker_name"] == "environment"

    bad = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns",
        headers=headers,
        json={"speaker_kind": "companion", "content": "?", "speaker_id": "ghost"},
    )
    assert bad.status_code == 422
    bad = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns",
        headers=headers,
        json={"speaker_kind": "user", "content": "?", "speaker_id": character["id"]},
    )
    assert bad.status_code == 422


def test_turn_write_requires_write_scope(app_client) -> None:
    _, chat = _world(app_client)
    reader = _bridge(app_client, [f"chat:read:{chat['id']}"])
    response = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns",
        headers=reader,
        json={"speaker_kind": "user", "content": "hello"},
    )
    assert response.status_code == 403


# --- generation -----------------------------------------------------------------


def test_generate_streams_and_stores_persona_turn(app_client) -> None:
    character, chat = _world(app_client)
    headers = _bridge(app_client, _scopes(chat["id"]))
    app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns",
        headers=headers,
        json={"speaker_kind": "user", "content": "I seek passage."},
    )
    response = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/generate", headers=headers, json={}
    )
    assert response.status_code == 200
    assert response.headers["X-Bridge-Protocol"] == "1"
    events = _sse_events(response)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "turn_started"
    assert "token" in kinds and kinds[-1] == "turn_stored"
    assert events[0]["backend"] == "fake"

    state = app_client.get(f"/api/v1/bridge/chats/{chat['id']}", headers=headers).json()
    assistant = [m for m in state["messages"] if m["role"] == "assistant"]
    assert len(assistant) == 1
    assert assistant[0]["content"] == "Rúnmál hears you. This is a stub."
    assert assistant[0]["speaker_id"] == character["id"]
    assert assistant[0]["speaker_name"] == "Bridge Warden"
    assert assistant[0]["id"] == events[-1]["message_id"]


async def test_generate_composes_persona_system_prompt(tmp_path) -> None:
    # Unit-level: the composed messages lead with the persona's card
    # system prompt, then history in order (protocol §7).
    from runmal.bridge import conversation
    from runmal.characters.service import create_character
    from runmal.chats.service import append_message, create_chat
    from runmal.db.owners import get_or_create_owner

    db_path = tmp_path / "compose.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    async with factory() as session:
        owner = await get_or_create_owner(session)
        character = await create_character(session, owner.id, CARD)
        chat = await create_chat(session, owner.id, "t", character_id=character.id)
        await append_message(session, owner.id, chat.id, "user", "Hail.")
        messages = await conversation.compose_messages(session, owner.id, chat)
    await engine.dispose()
    assert messages[0].role == "system"
    assert "Bridge Warden of TESTHOLD" in messages[0].content
    assert messages[-1].role == "user" and messages[-1].content == "Hail."


def test_generate_unknown_chat_and_cancel(app_client) -> None:
    star = _bridge(app_client, ["chat:write:*"])
    response = app_client.post("/api/v1/bridge/chats/nope/generate", headers=star, json={})
    assert response.status_code == 404

    _, chat = _world(app_client)
    headers = _bridge(app_client, _scopes(chat["id"]))
    response = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/generate/cancel",
        headers=headers,
        json={"request_id": "never-started"},
    )
    assert response.status_code == 200
    assert response.json() == {"cancelled": False}
    reader = _bridge(app_client, [f"chat:read:{chat['id']}"])
    response = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/generate/cancel",
        headers=reader,
        json={"request_id": "never-started"},
    )
    assert response.status_code == 403
