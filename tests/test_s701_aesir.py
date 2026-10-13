"""S701 (roadmap): Aesir ChatBackend adapter — fixture contract tests.

The same shared contract suite every adapter passes (S301) runs against
recorded Aesir-surface fixtures; no live Aesir server is involved.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from runmal.backends import contract
from runmal.backends.aesir import AesirChatBackend
from runmal.backends.errors import AuthenticationFailed, RateLimited
from runmal.backends.events import Done, TextDelta, UsageUpdate
from runmal.backends.messages import ChatMessage
from runmal.backends.params import SamplingParams
from runmal.backends.profiles import build_chat_backend, create_profile
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User

FIX = Path(__file__).parent / "fixtures" / "backends"
MSGS = [ChatMessage("user", "hi")]


def fixture_transport(chat: bytes | None = None, status: int = 200):
    sse = chat if chat is not None else (FIX / "aesir_chat.sse").read_bytes()
    models = (FIX / "aesir_models.json").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                status, content=sse, headers={"Content-Type": "text/event-stream"}
            )
        if request.url.path.endswith("/models"):
            return httpx.Response(200, content=models, headers={"Content-Type": "application/json"})
        return httpx.Response(404, content=b"{}")

    return httpx.MockTransport(handler)


def backend(**kw) -> AesirChatBackend:
    return AesirChatBackend(api_key=contract.CANARY, transport=fixture_transport(**kw))


async def test_fixture_backend_passes_contract():
    await contract.run_all(backend())


async def test_sse_stream_usage_and_done():
    events = [e async for e in backend().chat_stream(MSGS, SamplingParams(), asyncio.Event())]
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Hello from Aesir"
    usages = [e for e in events if isinstance(e, UsageUpdate)]
    assert usages and usages[0].total_tokens == 14
    assert isinstance(events[-1], Done) and events[-1].reason == "stop"
    # No provider wire objects leak: every event serializes to our vocabulary.
    types = {e.to_dict()["type"] for e in events}
    assert types <= {"text_delta", "usage", "done"}


async def test_model_metadata_normalized():
    b = backend()
    models = await b.list_models()
    assert [m.model_id for m in models] == ["llama-3.1-8b-instruct", "qwen-2.5-7b-instruct"]
    assert models[0].display_name == "Llama 3.1 8B Instruct (Aesir local)"
    # Display name falls back to the plain (non-namespaced) model ID.
    assert models[1].display_name == "qwen-2.5-7b-instruct"
    assert models[0].capabilities.context_length == 8192
    assert models[0].capabilities.max_output_tokens == 2048
    assert all(m.backend_key == "aesir" for m in models)
    health = await b.health_check()
    assert health.ok and "aesir" in health.detail


async def test_error_payload_and_http_errors_map():
    err_sse = (FIX / "aesir_error.sse").read_bytes()
    with pytest.raises(RateLimited):
        _ = [
            e
            async for e in backend(chat=err_sse).chat_stream(
                MSGS, SamplingParams(), asyncio.Event()
            )
        ]
    with pytest.raises(AuthenticationFailed):
        _ = [
            e
            async for e in backend(status=401).chat_stream(MSGS, SamplingParams(), asyncio.Event())
        ]


async def test_wire_payload_uses_aesir_names():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, content=(FIX / "aesir_chat.sse").read_bytes())

    b = AesirChatBackend(
        api_key="k", model="llama-3.1-8b-instruct", transport=httpx.MockTransport(handler)
    )
    params = SamplingParams(temperature=0.3, max_output_tokens=16, repetition_penalty=1.1)
    _ = [e async for e in b.chat_stream(MSGS, params, asyncio.Event())]
    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 16
    assert captured["repeat_penalty"] == 1.1
    assert "repetition_penalty" not in captured
    assert captured["model"] == "llama-3.1-8b-instruct"
    assert captured["auth"] == "Bearer k"


async def test_profile_builds_aesir_backend(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        profile = await create_profile(
            session,
            user.id,
            name="aesir-local",
            chat_backend="aesir",
            chat_model="llama-3.1-8b-instruct",
            config={"base_url": "http://127.0.0.1:9000/v1"},
        )
        built = await build_chat_backend(session, profile)
    assert isinstance(built, AesirChatBackend)
    assert built.backend_key == "aesir"
    assert str(built._client.base_url).rstrip("/") == "http://127.0.0.1:9000/v1"
