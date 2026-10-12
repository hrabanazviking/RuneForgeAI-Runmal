"""S308 (roadmap): campaign hardening — the full backend contract suite.

One gate running the S301 contract checks against the fake backend and
both recorded-fixture adapters (Ollama + OpenRouter), the embedding
contract, error-taxonomy mapping for the §13 list (timeout, auth, rate
limit, context overflow), and sampler filtering — all offline.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from runmal.backends import contract
from runmal.backends.embeddings import (
    FakeEmbeddingBackend,
    OllamaEmbeddingBackend,
    check_embedding_contract,
)
from runmal.backends.errors import (
    AuthenticationFailed,
    BackendTimeout,
    ContextOverflow,
    RateLimited,
)
from runmal.backends.fake import FakeChatBackend
from runmal.backends.messages import ChatMessage
from runmal.backends.ollama import OllamaChatBackend, map_status_error, map_text_error
from runmal.backends.openrouter import OpenRouterChatBackend
from runmal.backends.openrouter import map_error as openrouter_map_error
from runmal.backends.params import SamplingParams

FIX = Path(__file__).parent / "fixtures" / "backends"
MSGS = [ChatMessage("user", "hi")]


def ollama_backend() -> OllamaChatBackend:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, content=(FIX / "ollama_tags.json").read_bytes())
        return httpx.Response(
            200, content=(FIX / "ollama_chat.ndjson").read_bytes())

    return OllamaChatBackend(transport=httpx.MockTransport(handler),
                             api_key="SECRET-CANARY-301")


def openrouter_backend() -> OpenRouterChatBackend:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200, content=(FIX / "openrouter_models.json").read_bytes())
        return httpx.Response(
            200, content=(FIX / "openrouter_chat.sse").read_bytes())

    return OpenRouterChatBackend(api_key="SECRET-CANARY-301",
                                 transport=httpx.MockTransport(handler))


async def test_contract_suite_fake():
    await contract.run_all(FakeChatBackend(api_key="SECRET-CANARY-301"))


async def test_contract_suite_openrouter_fixture():
    await contract.run_all(openrouter_backend())


async def test_contract_suite_ollama_fixture():
    backend = ollama_backend()
    await contract.check_streaming_text(backend)
    await contract.check_terminal_done(backend)
    await contract.check_health(backend)
    await contract.check_model_metadata(backend)
    contract.check_count_tokens_quality(backend)
    await contract.check_no_secret_leak(backend)


async def test_embedding_contract_suite():
    await check_embedding_contract(FakeEmbeddingBackend())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/embed":
            return httpx.Response(
                200, content=(FIX / "ollama_embed.json").read_bytes())
        return httpx.Response(200, content=b'{"models": []}')

    await check_embedding_contract(
        OllamaEmbeddingBackend(transport=httpx.MockTransport(handler)))


def test_error_taxonomy_mapping():
    # §13 list: authentication failure, rate limiting, context overflow.
    assert isinstance(map_status_error(401, "bad key"), AuthenticationFailed)
    assert isinstance(map_status_error(429, "slow down"), RateLimited)
    assert isinstance(map_text_error("context length exceeded"), ContextOverflow)
    assert isinstance(openrouter_map_error(401, "nope"), AuthenticationFailed)
    assert isinstance(openrouter_map_error(429, "rl"), RateLimited)
    assert isinstance(
        openrouter_map_error(400, "context length exceeded the maximum"),
        ContextOverflow)


async def test_timeout_maps_to_backend_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    backend = OllamaChatBackend(transport=httpx.MockTransport(handler))
    with pytest.raises(BackendTimeout):
        async for _ in backend.chat_stream(MSGS, SamplingParams(), asyncio.Event()):
            pass


async def test_unsupported_sampler_filtering():
    backend = FakeChatBackend()
    filtered, warnings = backend.filter_params(
        SamplingParams(temperature=0.5, top_k=40, min_p=0.1))
    assert filtered.temperature == 0.5
    assert filtered.top_k is None and filtered.min_p is None
    assert {w.split(": ")[-1] for w in warnings} == {"top_k", "min_p"}
    with pytest.raises(ValueError):
        SamplingParams(top_p=2.0)
