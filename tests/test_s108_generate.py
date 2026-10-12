"""S108 acceptance: generation stub + normalized SSE."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.generation import fake_backend
from runmal.generation.service import _cancel_tokens, cancel_request, generate_events


@pytest.fixture()
def authed_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def parse_sse(body: str) -> list[dict]:
    events = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:") :].strip()))
    return events


def test_stream_parses_and_ends_with_done(authed_client) -> None:
    resp = authed_client.post(
        "/api/v1/generate", json={"messages": [{"role": "user", "content": "hi"}]}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    request_id = resp.headers["x-request-id"]
    assert request_id
    events = parse_sse(resp.text)
    assert events, "stream must parse into SSE events"
    tokens = [e for e in events if e["type"] == "token"]
    assert "".join(t["text"] for t in tokens) == "Rúnmál hears you. This is a stub."
    assert events[-1] == {"type": "done", "finish_reason": "stop"}
    # registry cleaned after a completed stream
    assert request_id not in _cancel_tokens


def test_raw_provider_format_does_not_leak(authed_client) -> None:
    resp = authed_client.post(
        "/api/v1/generate", json={"messages": [{"role": "user", "content": "hi"}]}
    )
    assert '"choices"' not in resp.text
    assert '"delta"' not in resp.text
    assert "chat.completion.chunk" not in resp.text
    for event in parse_sse(resp.text):
        assert set(event) <= {"type", "text", "finish_reason"}


def test_generate_requires_auth(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    assert client.post("/api/v1/generate", json={"messages": []}).status_code == 401
    assert client.post("/api/v1/generate/cancel", json={"request_id": "x"}).status_code == 401


def test_generate_rejects_empty_messages(authed_client) -> None:
    assert authed_client.post("/api/v1/generate", json={"messages": []}).status_code == 422


def test_cancel_unknown_request_id(authed_client) -> None:
    resp = authed_client.post("/api/v1/generate/cancel", json={"request_id": "nope"})
    assert resp.json() == {"cancelled": False}


async def test_cancel_token_stops_stub_with_cancelled_done() -> None:
    request_id = "s108-cancel-test"
    events: list[dict] = []

    async def consume() -> None:
        async for event in generate_events(request_id, "hi"):
            events.append(event)
            if len(events) == 2:
                assert cancel_request(request_id) is True

    await consume()
    assert events[-1] == {"type": "done", "finish_reason": "cancelled"}
    assert all(e["type"] != "done" or e is events[-1] for e in events)
    assert request_id not in _cancel_tokens


async def test_disconnect_close_leaves_no_orphan_task() -> None:
    before = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}
    request_id = "s108-disconnect-test"
    gen = generate_events(request_id, "hi")
    first = await gen.__anext__()
    assert first["type"] == "token"
    await gen.aclose()  # simulates client disconnect mid-stream
    await asyncio.sleep(0)
    lingering = {t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()}
    assert lingering <= before, "no orphan task may survive a disconnect"
    assert request_id not in _cancel_tokens


async def test_full_stream_cleans_registry() -> None:
    request_id = "s108-full-test"
    events = [e async for e in generate_events(request_id, "hi")]
    assert events[-1]["type"] == "done"
    assert request_id not in _cancel_tokens


def test_normalize_never_emits_provider_keys() -> None:
    for raw in (fake_backend._raw_chunk("x"), fake_backend._raw_stop_chunk()):
        event = fake_backend.normalize_chunk(raw)
        assert event is not None
        assert "choices" not in event and "delta" not in event
    assert fake_backend.normalize_chunk({"choices": [{"delta": {}}]}) is None
