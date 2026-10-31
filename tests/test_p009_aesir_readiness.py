"""P-009 acceptance: the Aesir readiness check.

The ledger (docs/AESIR_READINESS_2026-10-30.md) judges what
Rúnmál's Aesir adapters assume against what Aesir's own v1 API
matrix says it serves. These tests pin the tree-side facts the
ledger rests on — above all the divergences D1 (stream_options
sent on every request) and D2 (the declared sampler set vs the
served OpenAI-route subset) — so a future slice that repairs the
adapter must update the ledger deliberately instead of the
ledger silently going stale.

F-02 (the P-014 gate's Aesir binding repair) was that slice:
the pins below now record the REPAIRED tree (served sampler
subset declared, no stream_options on the wire, native-port
default), the ledger gained its appended F-02 follow-on
section, and the full F-02 pin lives in
tests/test_f02_aesir_binding.py. The ledger's original
divergence record stands as the record of the gap; Aesir chat
remains NOT PROVEN LIVE until the owed live smoke runs.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from runmal.backends.aesir import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    SAMPLERS,
    UNSUPPORTED_SAMPLERS,
    AesirChatBackend,
)
from runmal.backends.embeddings import AesirEmbeddingBackend
from runmal.backends.messages import ChatMessage
from runmal.backends.params import SamplingParams

LEDGER = (
    Path(__file__).parent.parent / "docs" / "AESIR_READINESS_2026-10-30.md"
)
FIX = Path(__file__).parent / "fixtures" / "backends"
MSGS = [ChatMessage("user", "hi")]

# The sampler subset Aesir's OpenAI chat route accepts, per its
# v1 API support matrix as recorded in the ledger (D2). The
# adapter's declared-honoured set minus this subset is exactly
# the divergent set.
AESIR_OPENAI_CHAT_ACCEPTED = {"temperature", "top_p", "max_tokens", "seed"}
AESIR_OPENAI_CHAT_DIVERGENT = {"top_k", "min_p", "repetition_penalty", "stop"}


def _chat_backend(captured: dict) -> AesirChatBackend:
    sse = (FIX / "aesir_chat.sse").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        captured["path"] = request.url.path
        return httpx.Response(
            200, content=sse, headers={"Content-Type": "text/event-stream"}
        )

    return AesirChatBackend(transport=httpx.MockTransport(handler))


def test_adapter_defaults_are_the_ledger_values() -> None:
    # D4, repaired by F-02: the shipped default is now Aesir's
    # native serve port (18434); the ledger records both ports
    # (18434 native, 11434 ollama-mode) and its original D4
    # record of the :8000 default stands as history.
    assert DEFAULT_BASE_URL == "http://127.0.0.1:18434/v1"
    assert DEFAULT_MODEL == "local-model"
    text = LEDGER.read_text(encoding="utf-8")
    assert "18434" in text and "11434" in text


def test_declared_sampler_sets_are_pinned() -> None:
    # Repaired by F-02: the declared-honoured set IS the served
    # OpenAI-route subset; the formerly divergent controls are
    # declared unsupported alongside the S702 originals.
    assert SAMPLERS == {
        "temperature",
        "top_p",
        "max_tokens",
        "seed",
    }
    assert UNSUPPORTED_SAMPLERS == {
        "top_k",
        "min_p",
        "repetition_penalty",
        "stop",
        "presence_penalty",
        "frequency_penalty",
        "context_length",
    }


def test_sampler_divergence_against_served_subset() -> None:
    # D2, computed and closed by F-02: the declared-honoured set
    # minus the served subset is now empty — the divergent set
    # survives only as the declared-unsupported remainder.
    assert set(SAMPLERS) - AESIR_OPENAI_CHAT_ACCEPTED == set()
    assert AESIR_OPENAI_CHAT_ACCEPTED == set(SAMPLERS)
    assert AESIR_OPENAI_CHAT_DIVERGENT <= set(UNSUPPORTED_SAMPLERS)


async def test_wire_carries_stream_options_and_renamed_sampler() -> None:
    # D1 + D2 on the wire itself, repaired by F-02: no
    # stream_options is sent, and a set top_k is dropped with
    # the other unserved controls instead of travelling.
    captured: dict = {}
    backend = _chat_backend(captured)
    params = SamplingParams(temperature=0.3, top_k=40)
    _ = [e async for e in backend.chat_stream(MSGS, params, asyncio.Event())]
    assert captured["path"].endswith("/chat/completions")
    assert "stream_options" not in captured
    assert "top_k" not in captured
    assert captured["temperature"] == 0.3


async def test_embedding_backend_posts_to_undeserved_route() -> None:
    # D3: the embedding adapter posts to /embeddings, a route
    # Aesir's matrix does not list in either mode.
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        body = {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}
        return httpx.Response(200, content=json.dumps(body).encode())

    backend = AesirEmbeddingBackend(transport=httpx.MockTransport(handler))
    result = await backend.embed(["hello"])
    assert captured["path"].endswith("/embeddings")
    assert result.provenance.provider == "aesir"


def test_ledger_records_the_divergences_and_the_gate() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    # The headline honesty: never proven against a live server.
    assert "NOT PROVEN LIVE" in text
    # D1/D2/D3 named with their operative facts.
    assert "stream_options" in text
    for name in AESIR_OPENAI_CHAT_DIVERGENT:
        assert name in text
    assert "NOT SERVED" in text and "/v1/embeddings" in text
    # The unconsumed text-paradigm endpoint (P-008 kin).
    assert "/v1/completions" in text
    # Admission bounds and the repair's road home.
    assert "131072" in text
    assert "NO HOME" in text and "P-014" in text
    # The Aesir-side source pin this check read.
    assert "1eed9706" in text and "API_SUPPORT_MATRIX_V1" in text
