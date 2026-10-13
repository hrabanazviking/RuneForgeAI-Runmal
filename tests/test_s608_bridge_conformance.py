"""S608 conformance: BRIDGE_PROTOCOL §14 walked end-to-end.

One suite, the whole checklist, against the real application through
its public surface — the same calls a third-party bridge makes.
(Idempotency duplication and outbox resume join this list from their
own slices, S610/S609, per the protocol doc §16.)
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.base import ChatBackend
from runmal.backends.errors import GenerationCancelled
from runmal.backends.events import Done, TextDelta
from runmal.backends.models import HealthStatus
from runmal.bridge import conversation
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

WARDEN = {"name": "Warden", "system_prompt": "You are the WARDEN."}
FERRYMAN = {"name": "Ferryman", "system_prompt": "You are the FERRYMAN."}


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    client.headers.update({"Authorization": f"Bearer {get_or_create_credential()}"})
    return client


def _bridge(client, scopes, name="conformance"):
    created = client.post(
        "/api/v1/bridge/credentials", json={"name": name, "scopes": scopes}
    ).json()
    return created, {"Authorization": f"Bearer {created['token']}"}


def _world(client):
    warden = client.post("/api/v1/characters", json={"card": WARDEN}).json()
    ferryman = client.post("/api/v1/characters", json={"card": FERRYMAN}).json()
    chat = client.post("/api/v1/chats", json={"title": "t", "character_id": warden["id"]}).json()
    return warden, ferryman, chat


def test_wrong_scope_and_revoked_denied(app_client) -> None:
    _, _, chat = _world(app_client)
    created, headers = _bridge(app_client, [f"chat:read:{chat['id']}"])
    # wrong scope: read-only token cannot write or generate
    assert (
        app_client.post(
            f"/api/v1/bridge/chats/{chat['id']}/turns",
            headers=headers,
            json={"speaker_kind": "user", "content": "x"},
        ).status_code
        == 403
    )
    assert (
        app_client.post(
            f"/api/v1/bridge/chats/{chat['id']}/generate", headers=headers, json={}
        ).status_code
        == 403
    )
    # revoked: even the granted read now fails as 401
    app_client.post(f"/api/v1/bridge/credentials/{created['id']}/revoke")
    assert app_client.get(f"/api/v1/bridge/chats/{chat['id']}", headers=headers).status_code == 401


def test_bridge_cannot_read_unrelated_chat(app_client) -> None:
    _, _, chat_a = _world(app_client)
    chat_b = app_client.post("/api/v1/chats", json={"title": "private"}).json()
    _, headers = _bridge(app_client, [f"chat:read:{chat_a['id']}", f"chat:write:{chat_a['id']}"])
    assert (
        app_client.get(f"/api/v1/bridge/chats/{chat_b['id']}", headers=headers).status_code == 403
    )
    # And the local surface without the local credential stays closed too.
    assert app_client.get(f"/api/v1/chats/{chat_b['id']}", headers=headers).status_code == 401


def test_persona_switch_affects_future_prompt_only(app_client) -> None:
    warden, ferryman, chat = _world(app_client)
    _, headers = _bridge(
        app_client,
        [
            f"chat:read:{chat['id']}",
            f"chat:write:{chat['id']}",
            f"persona:select:{ferryman['id']}",
        ],
    )
    app_client.post(f"/api/v1/bridge/chats/{chat['id']}/generate", headers=headers, json={})
    app_client.post(
        f"/api/v1/bridge/chats/{chat['id']}/persona",
        headers=headers,
        json={"character_id": ferryman["id"]},
    )
    app_client.post(f"/api/v1/bridge/chats/{chat['id']}/generate", headers=headers, json={})
    state = app_client.get(f"/api/v1/bridge/chats/{chat['id']}", headers=headers).json()
    speakers = [m["speaker_name"] for m in state["messages"]]
    assert speakers == ["Warden", "Ferryman"]  # history unrewritten


class _SlowBackend(ChatBackend):
    backend_key = "slow-conformance"

    async def chat_stream(self, messages, params, cancel):
        for index in range(100):
            if cancel.is_set():
                raise GenerationCancelled()
            yield TextDelta(text=f"tok{index} ")
            await asyncio.sleep(0.05)
        yield Done(reason="stop")

    async def list_models(self):
        return []

    async def health_check(self):
        return HealthStatus(ok=True, detail="slow but honest")


def test_cancellation_stops_generation(app_client, monkeypatch) -> None:
    _, _, chat = _world(app_client)
    _, headers = _bridge(app_client, [f"chat:write:{chat['id']}", f"chat:read:{chat['id']}"])
    slow = _SlowBackend()

    async def resolve(session, user_id, chat_row):
        return slow

    monkeypatch.setattr(conversation, "resolve_chat_backend", resolve)

    streamer = TestClient(app_client.app)
    with streamer.stream(
        "POST",
        f"/api/v1/bridge/chats/{chat['id']}/generate",
        headers=headers,
        json={"request_id": "conformance-1"},
    ) as response:
        events = (
            json.loads(line.removeprefix("data: "))
            for line in response.iter_lines()
            if line
        )
        first = next(events)
        assert first["type"] == "turn_started"
        second = next(events)
        assert second["type"] == "token"
        cancelled = app_client.post(
            f"/api/v1/bridge/chats/{chat['id']}/generate/cancel",
            headers=headers,
            json={"request_id": "conformance-1"},
        )
        assert cancelled.json() == {"cancelled": True}
        rest = list(events)
    kinds = [event["type"] for event in rest]
    assert "turn_stored" not in kinds  # a cancelled turn is never stored
    assert rest[-1] == {"type": "done", "finish_reason": "cancelled"}
    state = app_client.get(f"/api/v1/bridge/chats/{chat['id']}", headers=headers).json()
    assert state["messages"] == []
