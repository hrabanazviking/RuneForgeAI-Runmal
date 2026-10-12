"""Reusable ChatBackend contract checks (S301).

Later adapter tests (Ollama S302, OpenRouter S303, Aesir S701) consume these
same checks against recorded fixtures or fake transports. Cancellation
contract: a pre-set cancel event raises GenerationCancelled from chat_stream.
"""

from __future__ import annotations

import asyncio
import json

from runmal.backends.base import ChatBackend
from runmal.backends.errors import GenerationCancelled
from runmal.backends.events import Done, TextDelta
from runmal.backends.messages import ChatMessage
from runmal.backends.params import SamplingParams
from runmal.tokens import TokenCount, TokenQuality

CANARY = "SECRET-CANARY-301"
_MSGS = [ChatMessage(role="user", content="hello")]


async def _collect(backend, cancel=None):
    events = []
    async for event in backend.chat_stream(
        list(_MSGS), SamplingParams(), cancel or asyncio.Event()
    ):
        events.append(event)
    return events


async def check_streaming_text(backend: ChatBackend) -> None:
    events = await _collect(backend)
    texts = [e.text for e in events if isinstance(e, TextDelta)]
    assert texts and "".join(texts), "expected non-empty streamed text"


async def check_terminal_done(backend: ChatBackend) -> None:
    events = await _collect(backend)
    assert events and isinstance(events[-1], Done), "stream must end with Done"


async def check_cancellation(backend: ChatBackend) -> None:
    cancel = asyncio.Event()
    cancel.set()
    try:
        await _collect(backend, cancel)
    except GenerationCancelled:
        return
    raise AssertionError("pre-set cancel must raise GenerationCancelled")


async def check_health(backend: ChatBackend) -> None:
    health = await backend.health_check()
    assert isinstance(health.ok, bool) and isinstance(health.detail, str)


async def check_model_metadata(backend: ChatBackend) -> None:
    models = await backend.list_models()
    assert models, "expected at least one model"
    for model in models:
        assert model.model_id and model.display_name
        assert model.backend_key == backend.backend_key


def check_count_tokens_quality(backend: ChatBackend) -> None:
    count = backend.count_tokens(list(_MSGS), "any")
    assert isinstance(count, TokenCount) and count.value >= 0
    assert isinstance(count.quality, TokenQuality)


async def check_no_secret_leak(backend: ChatBackend) -> None:
    """Backend built with api_key=CANARY must never serialize the canary."""
    blobs: list[str] = []
    try:
        events = await _collect(backend)
        blobs += [json.dumps(e.to_dict()) for e in events]
    except Exception as exc:  # failure output must also be canary-free
        blobs.append(str(exc))
        to_dict = getattr(exc, "to_event_dict", None)
        if to_dict:
            blobs.append(json.dumps(to_dict()))
    blobs.append(json.dumps((await backend.health_check()).to_dict()))
    blobs += [json.dumps(m.to_dict()) for m in await backend.list_models()]
    for blob in blobs:
        assert CANARY not in blob, "secret canary leaked into backend output"


async def run_all(backend: ChatBackend) -> None:
    await check_streaming_text(backend)
    await check_terminal_done(backend)
    await check_cancellation(backend)
    await check_health(backend)
    await check_model_metadata(backend)
    check_count_tokens_quality(backend)
    await check_no_secret_leak(backend)
