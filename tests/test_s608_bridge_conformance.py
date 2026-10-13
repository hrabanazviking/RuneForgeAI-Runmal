"""S608 conformance: BRIDGE_PROTOCOL §14 walked end-to-end.

One suite, the whole checklist, against the real application through
its public surface — the same calls a third-party bridge makes.
(Idempotency duplication and outbox resume join this list from their
own slices, S610/S609, per the protocol doc §16.)
"""

from __future__ import annotations

import asyncio

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
            await asyncio.sleep(0.01)
        yield Done(reason="stop")

    async def list_models(self):
        return []

    async def health_check(self):
        return HealthStatus(ok=True, detail="slow but honest")


async def test_cancellation_stops_generation(app_client, monkeypatch) -> None:
    """§14: cancellation stops generation — and stores nothing.

    Driven at the service layer (the HTTP cancel endpoint is a
    one-line delegation to generation.service.cancel_request, scoped
    and plumbed in S602's tests): this environment's TestClient
    portals do not share module state across threads reliably, so a
    cross-thread HTTP cancel cannot observe the registry here. In
    the real single-process server the registry is shared by
    construction — the same dict the stream registered into.
    """
    from runmal.characters.service import create_character
    from runmal.chats.service import create_chat, get_history
    from runmal.db.owners import get_or_create_owner
    from runmal.generation import service as generation_service

    slow = _SlowBackend()

    async def resolve(session, user_id, chat_row):
        return slow

    monkeypatch.setattr(conversation, "resolve_chat_backend", resolve)

    factory = app_client.app.state.session_factory
    async with factory() as session:
        owner = await get_or_create_owner(session)
        character = await create_character(session, owner.id, WARDEN)
        chat = await create_chat(session, owner.id, "t", character_id=character.id)
        owner_id, chat_id = owner.id, chat.id

    seen: list[dict] = []

    async def consume():
        async for event in conversation.stream_generation(
            factory, owner_id, "bridge-x", chat_id, "conformance-cancel"
        ):
            seen.append(event)
            tokens = [e for e in seen if e["type"] == "token"]
            if len(tokens) >= 3:
                generation_service.cancel_request("conformance-cancel")

    await consume()
    kinds = [event["type"] for event in seen]
    assert kinds[0] == "turn_started"
    assert "turn_stored" not in kinds  # a cancelled turn is never stored
    assert seen[-1] == {"type": "done", "finish_reason": "cancelled"}
    async with factory() as session:
        history = await get_history(session, owner_id, chat_id)
    assert history == []
