"""S307 (roadmap): chat wired through the backend seam.

POST /generate resolves the chat's persisted backend profile and streams
through a ChatBackend, bridging normalized events to UI SSE. Default is the
fake backend: the suite passes with no Ollama/OpenRouter present.
"""

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends import profiles as backend_profiles
from runmal.backends.messages import ChatMessage
from runmal.backends.ollama import OllamaChatBackend
from runmal.backends.openrouter import OpenRouterChatBackend
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.owners import get_or_create_owner
from runmal.generation.service import _cancel_tokens, generate_events

FIX = Path(__file__).parent / "fixtures" / "backends"


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    auth_token = get_or_create_credential()
    client.headers.update({"Authorization": "Bearer " + auth_token})
    return client, factory


def parse_sse(body: str) -> list[dict]:
    events = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))
    return events


async def _make_profile(factory, **kwargs) -> str:
    async with factory() as session:
        owner = await get_or_create_owner(session)
        profile = await backend_profiles.create_profile(
            session, owner.id, name=kwargs.pop("name", "seam-fake"), **kwargs)
        return profile.id


def test_chat_profile_selection_persists_and_generate_uses_it(tmp_path, monkeypatch):
    client, factory = make_client(tmp_path, monkeypatch)
    profile_id = asyncio.run(_make_profile(factory, chat_backend="fake"))
    chat = client.post("/api/v1/chats", json={"title": "seam"})
    assert chat.status_code == 201, chat.text
    chat_id = chat.json()["id"]
    assert chat.json()["backend_profile_id"] is None

    pinned = client.post(f"/api/v1/chats/{chat_id}/backend-profile",
                         json={"profile_id": profile_id})
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["backend_profile_id"] == profile_id
    fetched = client.get(f"/api/v1/chats/{chat_id}")
    assert fetched.json()["backend_profile_id"] == profile_id

    resp = client.post("/api/v1/generate", json={
        "chat_id": chat_id,
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert resp.status_code == 200
    assert resp.headers["x-backend-key"] == "fake"
    events = parse_sse(resp.text)
    tokens = [e for e in events if e["type"] == "token"]
    # The profile's own FakeChatBackend script — NOT the service stub text:
    # proof the stream really came through the resolved profile backend.
    assert "".join(t["text"] for t in tokens) == "Rúnmál hears you."
    assert events[-1] == {"type": "done", "finish_reason": "stop"}

    plain = client.post("/api/v1/generate", json={
        "messages": [{"role": "user", "content": "hi"}],
    })
    plain_tokens = [e for e in parse_sse(plain.text) if e["type"] == "token"]
    assert "".join(t["text"] for t in plain_tokens) == \
        "Rúnmál hears you. This is a stub."

    cleared = client.post(f"/api/v1/chats/{chat_id}/backend-profile",
                          json={"profile_id": None})
    assert cleared.json()["backend_profile_id"] is None


def test_generate_unknown_chat_or_profile_is_404(tmp_path, monkeypatch):
    client, _factory = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/generate", json={
        "chat_id": "missing",
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert resp.status_code == 404
    resp = client.post("/api/v1/generate", json={
        "profile_id": "missing",
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert resp.status_code == 404
    chat = client.post("/api/v1/chats", json={"title": "x"})
    resp = client.post(
        f"/api/v1/chats/{chat.json()['id']}/backend-profile",
        json={"profile_id": "missing"})
    assert resp.status_code == 404


async def test_seam_streams_ollama_fixture_backend():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=(FIX / "ollama_chat.ndjson").read_bytes())

    backend = OllamaChatBackend(transport=httpx.MockTransport(handler))
    events = [e async for e in generate_events(
        "s307-ollama",
        messages=[ChatMessage("user", "hi")], backend=backend)]
    tokens = [e for e in events if e["type"] == "token"]
    assert "".join(t["text"] for t in tokens) == "Hello from Ollama"
    assert events[-1] == {"type": "done", "finish_reason": "stop"}
    assert "s307-ollama" not in _cancel_tokens


async def test_seam_streams_openrouter_fixture_backend():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=(FIX / "openrouter_chat.sse").read_bytes())

    backend = OpenRouterChatBackend(api_key="k",
                                    transport=httpx.MockTransport(handler))
    events = [e async for e in generate_events(
        "s307-openrouter",
        messages=[ChatMessage("user", "hi")], backend=backend)]
    tokens = [e for e in events if e["type"] == "token"]
    assert "".join(t["text"] for t in tokens) == "Hello from OpenRouter"
    assert events[-1] == {"type": "done", "finish_reason": "stop"}


def _ollama_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=0.3):
            return True
    except OSError:
        return False


@pytest.mark.skipif(not _ollama_reachable(), reason="no local Ollama")
async def test_real_ollama_end_to_end():
    backend = OllamaChatBackend()
    models = await backend.list_models()
    if not models:
        pytest.skip("Ollama reachable but no models installed")
    events = [e async for e in generate_events(
        "s307-real-ollama",
        messages=[ChatMessage("user", "Say hi in one word.")], backend=backend)]
    assert events[-1]["type"] == "done"
