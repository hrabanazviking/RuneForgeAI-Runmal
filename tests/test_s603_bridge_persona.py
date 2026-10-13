"""S603 acceptance: bridge persona switching API.

BRIDGE_PROTOCOL §8: switching is an explicit state change; the prompt
composition for future turns reflects the new persona, and stored
messages retain their original speakers.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

WARDEN = {
    "name": "Bridge Warden",
    "description": "Keeper of the bridge.",
    "system_prompt": "You are the Bridge Warden of TESTHOLD.",
}
FERRYMAN = {
    "name": "Ferryman",
    "description": "Rows the cold river.",
    "system_prompt": "You are the Ferryman of the COLD RIVER.",
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


def _bridge(client, scopes):
    created = client.post("/api/v1/bridge/credentials", json={"name": "b", "scopes": scopes}).json()
    return {"Authorization": f"Bearer {created['token']}"}


def _world(client):
    warden = client.post("/api/v1/characters", json={"card": WARDEN}).json()
    ferryman = client.post("/api/v1/characters", json={"card": FERRYMAN}).json()
    chat = client.post("/api/v1/chats", json={"title": "t", "character_id": warden["id"]}).json()
    return warden, ferryman, chat


def _scopes(chat, *personas):
    base = [f"chat:read:{chat['id']}", f"chat:write:{chat['id']}"]
    return base + [f"persona:select:{p['id']}" for p in personas]


def _sse(response):
    return [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_switch_changes_future_turns_only(app_client) -> None:
    warden, ferryman, chat = _world(app_client)
    headers = _bridge(app_client, _scopes(chat, ferryman))

    # A turn as the Warden first.
    app_client.post(f"/api/v1/bridge/chats/{chat['id']}/generate", headers=headers, json={})
    state = app_client.get(f"/api/v1/bridge/chats/{chat['id']}", headers=headers).json()
    assert state["messages"][0]["speaker_id"] == warden["id"]

    switched = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/persona",
        headers=headers,
        json={"character_id": ferryman["id"]},
    )
    assert switched.status_code == 200
    assert switched.json()["persona"] == {
        "character_id": ferryman["id"],
        "name": "Ferryman",
    }
    assert switched.json()["previous_character_id"] == warden["id"]

    # The next generation speaks as the Ferryman...
    events = _sse(
        app_client.post(f"/api/v1/bridge/chats/{chat['id']}/generate", headers=headers, json={})
    )
    assert events[-1]["type"] == "turn_stored"
    state = app_client.get(f"/api/v1/bridge/chats/{chat['id']}", headers=headers).json()
    assert state["persona"]["character_id"] == ferryman["id"]
    first, second = state["messages"]
    # ...while history keeps its original speakers (protocol §8).
    assert first["speaker_id"] == warden["id"]
    assert first["speaker_name"] == "Bridge Warden"
    assert second["speaker_id"] == ferryman["id"]
    assert second["speaker_name"] == "Ferryman"

    events_log = app_client.get(f"/api/v1/chats/{chat['id']}/events").json()
    changes = [e for e in events_log if e["kind"] == "persona.changed"]
    assert len(changes) == 1
    assert changes[0]["data"]["from"] == warden["id"]
    assert changes[0]["data"]["to"] == ferryman["id"]
    assert changes[0]["data"]["source"] == "bridge"


async def test_prompt_composition_reflects_switch(tmp_path) -> None:
    from runmal.bridge import conversation
    from runmal.characters.service import create_character
    from runmal.chats.service import create_chat, get_chat, set_chat_persona
    from runmal.db.owners import get_or_create_owner

    db_path = tmp_path / "switch.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    async with factory() as session:
        owner = await get_or_create_owner(session)
        warden = await create_character(session, owner.id, WARDEN)
        ferryman = await create_character(session, owner.id, FERRYMAN)
        chat = await create_chat(session, owner.id, "t", character_id=warden.id)
        before = await conversation.compose_messages(session, owner.id, chat)
        await set_chat_persona(session, owner.id, chat.id, ferryman.id)
        chat = await get_chat(session, owner.id, chat.id)
        after = await conversation.compose_messages(session, owner.id, chat)
    await engine.dispose()
    assert "Bridge Warden of TESTHOLD" in before[0].content
    assert "Ferryman of the COLD RIVER" in after[0].content


def test_switch_scope_and_existence(app_client) -> None:
    warden, ferryman, chat = _world(app_client)
    # No persona scope at all -> 403.
    plain = _bridge(app_client, [f"chat:write:{chat['id']}"])
    response = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/persona",
        headers=plain,
        json={"character_id": ferryman["id"]},
    )
    assert response.status_code == 403
    # Scope for the WRONG persona -> 403.
    wrong = _bridge(app_client, _scopes(chat, warden))
    response = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/persona",
        headers=wrong,
        json={"character_id": ferryman["id"]},
    )
    assert response.status_code == 403
    # Unknown character -> 422; unknown chat -> 404; wildcard can clear.
    star = _bridge(app_client, ["persona:select:*"])
    response = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/persona",
        headers=star,
        json={"character_id": "ghost"},
    )
    assert response.status_code == 422
    response = app_client.post(
        "/api/v1/bridge/chats/nope/persona",
        headers=star,
        json={"character_id": ferryman["id"]},
    )
    assert response.status_code == 404
    cleared = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/persona",
        headers=star,
        json={"character_id": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["persona"] is None
