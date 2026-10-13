"""S610 acceptance: idempotency + protocol capability discovery.

BRIDGE_PROTOCOL §4/§14 + INV-030: a duplicate turn submission
(network retry, bridge restart mid-request) returns the original
result and creates exactly one message; the same key with a
different request is a 409; capability discovery reports version,
scopes, features, event kinds, and limits to any paired bridge.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

CARD = {"name": "Warden", "system_prompt": "You are the WARDEN."}


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    client.headers.update({"Authorization": f"Bearer {get_or_create_credential()}"})
    return client


@pytest.fixture()
def world(app_client):
    character = app_client.post("/api/v1/characters", json={"card": CARD}).json()
    chat = app_client.post(
        "/api/v1/chats", json={"title": "t", "character_id": character["id"]}
    ).json()
    scopes = [
        f"chat:read:{chat['id']}",
        f"chat:write:{chat['id']}",
        f"events:read:{chat['id']}",
    ]
    created = app_client.post(
        "/api/v1/bridge/credentials", json={"name": "idem", "scopes": scopes}
    ).json()
    headers = {"Authorization": f"Bearer {created['token']}"}
    return chat, headers


def _messages(client, headers, chat_id):
    state = client.get(f"/api/v1/bridge/chats/{chat_id}", headers=headers).json()
    return state["messages"]


def test_duplicate_turn_returns_original_and_stores_once(app_client, world) -> None:
    chat, headers = world
    body = {"speaker_kind": "user", "content": "Hail.", "idempotency_key": "turn-1"}
    first = app_client.post(f"/api/v1/bridge/chats/{chat['id']}/turns", headers=headers, json=body)
    assert first.status_code == 201
    retry = app_client.post(f"/api/v1/bridge/chats/{chat['id']}/turns", headers=headers, json=body)
    assert retry.status_code == 201
    assert retry.headers.get("Idempotency-Replayed") == "true"
    assert retry.json()["id"] == first.json()["id"]
    assert [m["content"] for m in _messages(app_client, headers, chat["id"])] == ["Hail."]


def test_same_key_different_request_conflicts(app_client, world) -> None:
    chat, headers = world
    body = {"speaker_kind": "user", "content": "Hail.", "idempotency_key": "k"}
    assert (
        app_client.post(
            f"/api/v1/bridge/chats/{chat['id']}/turns", headers=headers, json=body
        ).status_code
        == 201
    )
    conflict = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns",
        headers=headers,
        json={**body, "content": "Different words."},
    )
    assert conflict.status_code == 409
    assert len(_messages(app_client, headers, chat["id"])) == 1


def test_header_key_and_distinct_keys(app_client, world) -> None:
    chat, headers = world
    via_header = {**headers, "Idempotency-Key": "hdr-1"}
    body = {"speaker_kind": "user", "content": "Once."}
    first = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns", headers=via_header, json=body
    )
    retry = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns", headers=via_header, json=body
    )
    assert first.json()["id"] == retry.json()["id"]
    other = app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns",
        headers=headers,
        json={**body, "idempotency_key": "another"},
    )
    assert other.json()["id"] != first.json()["id"]  # distinct key -> distinct turn
    assert len(_messages(app_client, headers, chat["id"])) == 2


def test_duplicate_generation_replays_summary_without_restoring(app_client, world) -> None:
    chat, headers = world
    app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/turns",
        headers=headers,
        json={"speaker_kind": "user", "content": "Speak."},
    )

    def generate():
        response = app_client.post(
            f"/api/v1/bridge/chats/{chat['id']}/generate",
            headers=headers,
            json={"idempotency_key": "gen-1"},
        )
        assert response.status_code == 200, response.text
        return [
            json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
        ], response

    first_events, _ = generate()
    first_stored = [e for e in first_events if e["type"] == "turn_stored"]
    assert len(first_stored) == 1

    retry_events, retry_response = generate()
    assert retry_response.headers.get("Idempotency-Replayed") == "true"
    retry_stored = [e for e in retry_events if e["type"] == "turn_stored"]
    assert retry_stored == first_stored  # same stored message id
    assert not [e for e in retry_events if e["type"] == "token"]  # summary, not a re-performance
    assistants = [m for m in _messages(app_client, headers, chat["id"]) if m["role"] == "assistant"]
    assert len(assistants) == 1  # exactly one companion turn exists


def test_capabilities_discovery(app_client, world) -> None:
    chat, headers = world
    response = app_client.get("/api/v1/bridge/capabilities", headers=headers)
    assert response.status_code == 200
    caps = response.json()
    assert caps["protocol_version"] == "1"
    assert caps["api"] == "v1"
    assert caps["bridge_id"]
    assert f"chat:read:{chat['id']}" in caps["scopes"]
    assert caps["features"]["idempotency"] is True
    assert caps["features"]["event_outbox"] is True
    assert "turn_appended" in caps["event_kinds"]
    assert caps["limits"]["outbox_retention_per_chat"] == 1000
    assert app_client.get("/api/v1/bridge/capabilities").status_code == 401
