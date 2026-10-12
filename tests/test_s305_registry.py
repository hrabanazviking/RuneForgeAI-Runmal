"""S305 (roadmap): model listing + health + token counting service layer."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from runmal.backends.fake import FakeChatBackend
from runmal.backends.messages import ChatMessage
from runmal.backends.ollama import OllamaChatBackend
from runmal.backends.openrouter import OpenRouterChatBackend
from runmal.backends.registry import BackendRegistry
from runmal.tokens import TokenCount, TokenQuality

FIX = Path(__file__).parent / "fixtures" / "backends"
MSGS = [ChatMessage("user", "hello world this is a test")]


def ollama_backend() -> OllamaChatBackend:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, content=(FIX / "ollama_tags.json").read_bytes())
        return httpx.Response(
            200, content=(FIX / "ollama_chat.ndjson").read_bytes())

    return OllamaChatBackend(transport=httpx.MockTransport(handler))


def openrouter_backend() -> OpenRouterChatBackend:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200, content=(FIX / "openrouter_models.json").read_bytes())
        return httpx.Response(
            200, content=(FIX / "openrouter_chat.sse").read_bytes())

    return OpenRouterChatBackend(api_key="k",
                                 transport=httpx.MockTransport(handler))


def registry() -> BackendRegistry:
    reg = BackendRegistry()
    reg.register(FakeChatBackend())
    reg.register(ollama_backend())
    reg.register(openrouter_backend())
    return reg


async def test_aggregated_model_listing_from_fixtures():
    reg = registry()
    models = await reg.list_all_models()
    keys = {(m.backend_key, m.model_id) for m in models}
    assert ("fake", "fake-1") in keys
    assert ("ollama", "llama3.1") in keys
    assert ("ollama", "nomic-embed-text") in keys
    assert ("openrouter", "openai/gpt-4o-mini") in keys
    assert ("openrouter", "anthropic/claude-sonnet") in keys
    assert len(models) == 5
    ollama_models = await reg.list_models_for("ollama")
    assert len(ollama_models) == 2


async def test_aggregated_health():
    reg = registry()
    health = await reg.health_all()
    assert set(health) == {"fake", "ollama", "openrouter"}
    assert all(status.ok for status in health.values())
    dicts = await reg.health_dicts()
    assert dicts["ollama"]["ok"] is True


def test_token_count_quality_is_surfaced():
    reg = registry()
    report = reg.token_count("fake", MSGS, "fake-1")
    assert report.quality is TokenQuality.ESTIMATED
    assert report.is_estimate is True
    assert report.to_dict()["quality"] == "estimated"

    class ProviderCounter(FakeChatBackend):
        def count_tokens(self, messages, model_id):
            return TokenCount(42, TokenQuality.PROVIDER)

    reg.register(ProviderCounter(), name="provider-counter")
    exactish = reg.token_count("provider-counter", MSGS, "m")
    assert exactish.quality is TokenQuality.PROVIDER
    assert exactish.is_estimate is False
    assert exactish.count.value == 42


def test_token_count_from_usage_is_provider_quality():
    reg = registry()
    report = reg.token_count_from_usage("openrouter", {"prompt_tokens": 9})
    assert report is not None
    assert report.count.value == 9
    assert report.quality is TokenQuality.PROVIDER
    assert reg.token_count_from_usage("openrouter", None) is None
    assert reg.token_count_from_usage("openrouter", {}) is None


def test_unknown_backend_raises():
    reg = registry()
    with pytest.raises(KeyError):
        reg.get("nope")
    with pytest.raises(KeyError):
        reg.token_count("nope", MSGS, "m")
