"""Aesir admission bounds (P-009 D7) - repair of 2026-11-20.

P-009 recorded D7 as DIVERGENT at scale: the adapter sent full
history unbounded while Aesir's chat route admits at most 128
messages, 64 KiB per text field, and a 131072-byte POST body -
the long roleplay chats that are Runmal's home territory would
be refused with 400. F-02's minimum repair did not name D7, so
it stood open until Volmarr's 2026-11-20 correction order (work
proven only against fixtures is finished to real, or not at
all). The adapter now refuses an over-bound request itself,
with ``ContextOverflow``, before any byte is sent. These pins
cover the three bounds and the no-send guarantee; the live
half of the proof is the purplelongship smoke recorded in
``docs/AESIR_ADMISSION_REPAIR_AND_LIVE_SMOKE_2026-11-20.md``.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from runmal.backends.aesir import (
    ADMISSION_MAX_BODY_BYTES,
    ADMISSION_MAX_FIELD_BYTES,
    ADMISSION_MAX_MESSAGES,
    AesirChatBackend,
    check_admission,
)
from runmal.backends.errors import ContextOverflow
from runmal.backends.messages import ChatMessage
from runmal.backends.params import SamplingParams


def payload_for(messages):
    return {
        "model": "local-model",
        "messages": [m.to_dict() for m in messages],
        "stream": True,
    }


def test_admission_bounds_are_aesirs_own_numbers():
    # P-009 section 2, from Aesir's v1 matrix: 128 messages,
    # 64 KiB per text field, 131072 bytes per POST body.
    assert ADMISSION_MAX_MESSAGES == 128
    assert ADMISSION_MAX_FIELD_BYTES == 65536
    assert ADMISSION_MAX_BODY_BYTES == 131072


def test_admission_accepts_an_ordinary_chat():
    check_admission(payload_for([ChatMessage("user", "hi")]))


def test_admission_accepts_exactly_the_message_bound():
    msgs = [ChatMessage("user", "x")] * ADMISSION_MAX_MESSAGES
    check_admission(payload_for(msgs))


def test_admission_refuses_too_many_messages():
    msgs = [ChatMessage("user", "x")] * (ADMISSION_MAX_MESSAGES + 1)
    with pytest.raises(ContextOverflow):
        check_admission(payload_for(msgs))


def test_admission_refuses_an_oversized_field():
    big = "a" * (ADMISSION_MAX_FIELD_BYTES + 1)
    with pytest.raises(ContextOverflow):
        check_admission(payload_for([ChatMessage("user", big)]))


def test_admission_refuses_an_oversized_body_under_the_field_cap():
    chunk = "a" * (ADMISSION_MAX_FIELD_BYTES // 2)
    msgs = [ChatMessage("user", chunk)] * 5  # ~160 KiB total, each field legal
    with pytest.raises(ContextOverflow):
        check_admission(payload_for(msgs))


def test_chat_stream_refuses_over_bound_history_without_sending():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise AssertionError("over-bound request must never reach the transport")

    backend = AesirChatBackend(transport=httpx.MockTransport(handler))
    msgs = [ChatMessage("user", "x")] * (ADMISSION_MAX_MESSAGES + 1)

    async def drain():
        async for _ in backend.chat_stream(msgs, SamplingParams(), asyncio.Event()):
            pass

    with pytest.raises(ContextOverflow):
        asyncio.run(drain())
    assert calls == []


# --- D5 live repair (2026-11-20): readiness against the deployed build.
# The Aesir build deployed on purplelongship (2026-10-10) predates the
# schema-v1 /health/ready route and 404s it; it serves the same
# resident truth at the legacy /health. The check falls back on a 404
# and reports the server's own word either way.


def _readiness_backend(ready_status: int, legacy_body: bytes | None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/health/ready"):
            return httpx.Response(ready_status, content=b"{}")
        if request.url.path.endswith("/health"):
            if legacy_body is None:
                return httpx.Response(404, content=b"{}")
            return httpx.Response(200, content=legacy_body)
        return httpx.Response(404, content=b"{}")

    return AesirChatBackend(transport=httpx.MockTransport(handler))


def test_readiness_falls_back_to_legacy_health_when_ready_route_404s():
    backend = _readiness_backend(404, b'{"status": "ready", "model": "llama3.2:3b"}')
    status = asyncio.run(backend.readiness_check())
    assert status.ok
    assert "llama3.2:3b" in status.detail
    assert "legacy" in status.detail


def test_readiness_legacy_health_not_ready_is_not_ready():
    backend = _readiness_backend(404, b'{"status": "loading"}')
    status = asyncio.run(backend.readiness_check())
    assert not status.ok


def test_readiness_no_health_route_at_all_is_not_ready():
    backend = _readiness_backend(404, None)
    status = asyncio.run(backend.readiness_check())
    assert not status.ok
