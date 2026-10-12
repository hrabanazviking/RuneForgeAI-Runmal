"""S302 (roadmap): Ollama chat adapter — recorded-fixture contract tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from runmal.backends import contract
from runmal.backends.errors import (
    GenerationCancelled,
    ModelNotFound,
    ProviderError,
)
from runmal.backends.events import Done, TextDelta
from runmal.backends.messages import ChatMessage
from runmal.backends.ollama import OllamaChatBackend
from runmal.backends.params import SamplingParams

FIX = Path(__file__).parent / "fixtures" / "backends"
MSGS = [ChatMessage("user", "hi")]


def fixture_transport(chat_body: bytes | None = None, chat_status: int = 200):
    ndjson = chat_body if chat_body is not None else (FIX / "ollama_chat.ndjson").read_bytes()
    tags = (FIX / "ollama_tags.json").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            return httpx.Response(chat_status, content=ndjson,
                                  headers={"Content-Type": "application/x-ndjson"})
        if request.url.path == "/api/tags":
            return httpx.Response(200, content=tags,
                                  headers={"Content-Type": "application/json"})
        return httpx.Response(404, content=b"{}")

    return httpx.MockTransport(handler)


def backend(**kw) -> OllamaChatBackend:
    return OllamaChatBackend(transport=fixture_transport(**kw), api_key=contract.CANARY)


async def test_fixture_backend_passes_contract():
    await contract.run_all(backend())


async def test_fixture_stream_events_and_usage():
    events = [e async for e in backend().chat_stream(MSGS, SamplingParams(), asyncio.Event())]
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Hello from Ollama"
    assert isinstance(events[-1], Done) and events[-1].reason == "stop"
    assert events[-1].usage.prompt_tokens == 11
    assert events[-1].usage.total_tokens == 18


async def test_options_mapping_and_param_filtering():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        body = (FIX / "ollama_chat.ndjson").read_bytes()
        return httpx.Response(200, content=body)

    b = OllamaChatBackend(transport=httpx.MockTransport(handler))
    params = SamplingParams(temperature=0.5, max_output_tokens=32,
                            repetition_penalty=1.1, presence_penalty=0.5)
    _ = [e async for e in b.chat_stream(MSGS, params, asyncio.Event())]
    options = captured["options"]
    assert options == {"temperature": 0.5, "num_predict": 32, "repeat_penalty": 1.1}
    assert captured["stream"] is True and captured["model"] == "llama3.1"


async def test_error_mapping_status_and_error_line():
    with pytest.raises(ModelNotFound):
        _ = [e async for e in backend(chat_status=404).chat_stream(
            MSGS, SamplingParams(), asyncio.Event())]
    body = b'{"error": "something broke"}\n'
    with pytest.raises(ProviderError):
        _ = [e async for e in backend(chat_body=body).chat_stream(
            MSGS, SamplingParams(), asyncio.Event())]


async def test_cancellation_closes_stream():
    closed = False

    class TrackedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"message": {"content": "one"}, "done": false}\n'
            yield b'{"message": {"content": "two"}, "done": false}\n'
            yield b'{"message": {"content": ""}, "done": true}\n'

        async def aclose(self):
            nonlocal closed
            closed = True

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=TrackedStream())

    b = OllamaChatBackend(transport=httpx.MockTransport(handler))
    cancel = asyncio.Event()

    async def run():
        async for _e in b.chat_stream(MSGS, SamplingParams(), cancel):
            cancel.set()

    with pytest.raises(GenerationCancelled):
        await run()
    assert closed


async def test_list_models_and_health_from_fixtures():
    b = backend()
    models = await b.list_models()
    assert [m.model_id for m in models] == ["llama3.1", "nomic-embed-text"]
    assert models[0].capabilities.context_length == 131072
    assert (await b.health_check()).ok


@pytest.mark.skipif(True, reason="live Ollama not required in ordinary suite")
async def test_real_ollama_tagged():
    b = OllamaChatBackend()
    assert (await b.health_check()).ok
