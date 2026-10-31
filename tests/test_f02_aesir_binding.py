"""F-02 acceptance: the Aesir binding repair.

Part I follow-on F-02 (homed by the P-014 gate from P-009's
first recommendation): the minimum honest repair of Rúnmál's
Aesir chat binding — no ``stream_options`` (D1), the declared
sampler set re-declared to the OpenAI route's served subset
(D2), the default base URL corrected to Aesir's native serve
port (D4), 422 mapped (D8), no fabricated ``Done`` on an
incomplete stream (D6), resident-model readiness surfaced
from ``/health/ready`` (D5 / VX-19 narrowed), and the
embeddings binding rule recorded (D3). Fixture transports
only; no live Aesir server is involved, and Aesir chat
remains NOT PROVEN LIVE until the owed purplelongship smoke
runs.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from runmal.backends import contract
from runmal.backends.aesir import (
    DEFAULT_BASE_URL,
    SAMPLERS,
    UNSUPPORTED_SAMPLERS,
    WIRE_NAMES,
    AesirChatBackend,
    map_error,
)
from runmal.backends.embeddings import AesirEmbeddingBackend
from runmal.backends.errors import ContextOverflow, ProviderError
from runmal.backends.messages import ChatMessage
from runmal.backends.negotiation import CANONICAL_CONTROLS
from runmal.backends.params import SamplingParams
from runmal.backends.profiles import build_chat_backend, create_profile
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.diagnostics.doctor import check_providers

FIX = Path(__file__).parent / "fixtures" / "backends"
DOCS = Path(__file__).parent.parent / "docs"
MSGS = [ChatMessage("user", "hi")]
AESIR_SERVED_SUBSET = {"temperature", "top_p", "max_tokens", "seed"}


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


def test_default_base_url_is_aesir_native_port():
    # D4 repaired: 18434 is Aesir serve's native default port;
    # the old :8000 default reached neither Aesir port.
    assert DEFAULT_BASE_URL == "http://127.0.0.1:18434/v1"
    assert AesirChatBackend()._client.base_url.host == "127.0.0.1"
    assert AesirChatBackend()._client.base_url.port == 18434


async def test_profile_builder_default_matches_adapter(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        profile = await create_profile(
            session, user.id, name="aesir-default", chat_backend="aesir",
            chat_model="llama-3.1-8b-instruct",
        )
        built = await build_chat_backend(session, profile)
    assert isinstance(built, AesirChatBackend)
    assert str(built._client.base_url).rstrip("/") == DEFAULT_BASE_URL


def test_doctor_default_matches_adapter(tmp_path):
    # The doctor keeps its default as an import-light literal;
    # this pin keeps the two from drifting apart again.
    db = tmp_path / "runmal.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE backend_profiles (chat_backend TEXT, config_json TEXT)"
    )
    conn.execute("INSERT INTO backend_profiles VALUES ('aesir', '{}')")
    conn.commit()
    conn.close()
    seen: dict = {}

    def probe(backend_name: str, base_url: str):
        seen[backend_name] = base_url
        return True, "probe ok"

    findings = check_providers(db, probe=probe)
    assert seen["aesir"] == DEFAULT_BASE_URL
    assert any(f.check == "provider:aesir" and f.status == "ok" for f in findings)


def test_sampler_truth_is_the_served_subset():
    assert SAMPLERS == AESIR_SERVED_SUBSET
    assert WIRE_NAMES == {k: k for k in AESIR_SERVED_SUBSET}
    # Declared + unsupported still account for every canonical
    # control — no third, silently ignored category (INV-005).
    assert set(SAMPLERS) | set(UNSUPPORTED_SAMPLERS) == set(CANONICAL_CONTROLS)
    assert not (set(SAMPLERS) & set(UNSUPPORTED_SAMPLERS))
    for dropped in ("top_k", "min_p", "repetition_penalty", "stop"):
        assert dropped in UNSUPPORTED_SAMPLERS


async def test_wire_carries_only_served_controls_and_no_stream_options():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, content=(FIX / "aesir_chat.sse").read_bytes())

    b = AesirChatBackend(model="m", transport=httpx.MockTransport(handler))
    params = SamplingParams(
        temperature=0.3, top_p=0.9, max_output_tokens=16, seed=7,
        top_k=40, min_p=0.05, repetition_penalty=1.1, stop=("END",),
    )
    _ = [e async for e in b.chat_stream(MSGS, params, asyncio.Event())]
    assert captured["temperature"] == 0.3
    assert captured["top_p"] == 0.9
    assert captured["max_tokens"] == 16
    assert captured["seed"] == 7
    for absent in (
        "stream_options", "top_k", "min_p", "repetition_penalty",
        "repeat_penalty", "stop",
    ):
        assert absent not in captured


async def test_422_maps_to_context_overflow():
    # D8 repaired: Aesir's admission refusal is 422.
    assert isinstance(map_error(422, ""), ContextOverflow)
    assert isinstance(map_error(422, "context admission refused"), ContextOverflow)
    with pytest.raises(ContextOverflow):
        _ = [e async for e in backend(status=422).chat_stream(
            MSGS, SamplingParams(), asyncio.Event())]


async def test_incomplete_stream_raises_instead_of_faking_done():
    # D6 repaired: a post-header failure can end the stream with
    # no terminal marker and no finish reason — that raises.
    truncated = (
        b'data: {"choices": [{"delta": {"content": "partial"},'
        b' "finish_reason": null}]}\n\n'
    )
    with pytest.raises(ProviderError):
        _ = [e async for e in backend(chat=truncated).chat_stream(
            MSGS, SamplingParams(), asyncio.Event())]


async def test_readiness_surfaces_resident_model_from_server_root():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        if request.url.path == "/health/ready":
            body = {"status": "ready", "model": "llama-3.1-8b-instruct"}
            return httpx.Response(200, content=json.dumps(body).encode())
        return httpx.Response(404, content=b"{}")

    b = AesirChatBackend(transport=httpx.MockTransport(handler))
    readiness = await b.readiness_check()
    # The readiness route lives at the server root, not under /v1.
    assert captured["path"] == "/health/ready"
    assert readiness.ok and "llama-3.1-8b-instruct" in readiness.detail


async def test_readiness_reports_not_ready_honestly():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"{}")

    b = AesirChatBackend(transport=httpx.MockTransport(handler))
    readiness = await b.readiness_check()
    assert not readiness.ok and "not ready" in readiness.detail
    # Reachability via /models is a separate, weaker claim and
    # is not upgraded into readiness (D5).
    health = await b.health_check()
    assert isinstance(health.ok, bool)


def test_embeddings_binding_rule_and_live_status_are_recorded():
    # D3's rule, recorded where the next builder will read it:
    # Aesir embeddings are NOT SERVED; embeddings bind to Ollama.
    doc = inspect.getdoc(AesirEmbeddingBackend) or ""
    assert "NOT SERVED" in doc and "Ollama" in doc
    repair = (DOCS / "AESIR_BINDING_REPAIR_2026-10-30.md").read_text(encoding="utf-8")
    assert "NOT PROVEN LIVE" in repair
    assert "18434" in repair and "stream_options" in repair
    ledger = (DOCS / "AESIR_READINESS_2026-10-30.md").read_text(encoding="utf-8")
    assert "F-02 follow-on" in ledger
