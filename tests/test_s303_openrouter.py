"""S303 (roadmap): OpenRouter adapter — fixture SSE contract tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from runmal.backends import contract
from runmal.backends.errors import AuthenticationFailed, RateLimited
from runmal.backends.events import Done, TextDelta, UsageUpdate
from runmal.backends.messages import ChatMessage
from runmal.backends.openrouter import OpenRouterChatBackend
from runmal.backends.params import SamplingParams

FIX = Path(__file__).parent / "fixtures" / "backends"
MSGS = [ChatMessage("user", "hi")]


def fixture_transport(chat: bytes | None = None, status: int = 200):
    sse = chat if chat is not None else (FIX / "openrouter_chat.sse").read_bytes()
    models = (FIX / "openrouter_models.json").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(status, content=sse,
                                  headers={"Content-Type": "text/event-stream"})
        if request.url.path.endswith("/models"):
            return httpx.Response(200, content=models,
                                  headers={"Content-Type": "application/json"})
        return httpx.Response(404, content=b"{}")

    return httpx.MockTransport(handler)


def backend(**kw) -> OpenRouterChatBackend:
    return OpenRouterChatBackend(api_key=contract.CANARY,
                                 transport=fixture_transport(**kw))


async def test_fixture_backend_passes_contract():
    await contract.run_all(backend())


async def test_sse_stream_usage_and_done():
    events = [e async for e in backend().chat_stream(
        MSGS, SamplingParams(), asyncio.Event())]
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) \
        == "Hello from OpenRouter"
    usages = [e for e in events if isinstance(e, UsageUpdate)]
    assert usages and usages[0].total_tokens == 14
    assert isinstance(events[-1], Done) and events[-1].reason == "stop"
    # No provider wire objects leak: every event serializes to our vocabulary.
    types = {e.to_dict()["type"] for e in events}
    assert types <= {"text_delta", "usage", "done"}


async def test_namespaced_model_ids_in_metadata_only():
    b = backend()
    models = await b.list_models()
    assert models[0].model_id == "openai/gpt-4o-mini"
    assert models[0].display_name == "OpenAI: GPT-4o Mini"
    assert models[0].capabilities.context_length == 128000
    assert models[0].capabilities.max_output_tokens == 16384
    assert models[0].backend_key == "openrouter"


async def test_error_payload_and_http_errors_map():
    err_sse = (FIX / "openrouter_error.sse").read_bytes()
    with pytest.raises(RateLimited):
        _ = [e async for e in backend(chat=err_sse).chat_stream(
            MSGS, SamplingParams(), asyncio.Event())]
    with pytest.raises(AuthenticationFailed):
        _ = [e async for e in backend(status=401).chat_stream(
            MSGS, SamplingParams(), asyncio.Event())]


async def test_wire_payload_uses_openai_names_and_filters():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200, content=(FIX / "openrouter_chat.sse").read_bytes())

    b = OpenRouterChatBackend(api_key="k", transport=httpx.MockTransport(handler))
    params = SamplingParams(temperature=0.3, max_output_tokens=16,
                            frequency_penalty=0.2, top_k=5)
    _ = [e async for e in b.chat_stream(MSGS, params, asyncio.Event())]
    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 16
    assert captured["frequency_penalty"] == 0.2
    assert "top_k" not in captured
    assert captured["model"] == "openai/gpt-4o-mini"
    assert captured["auth"] == "Bearer k"
