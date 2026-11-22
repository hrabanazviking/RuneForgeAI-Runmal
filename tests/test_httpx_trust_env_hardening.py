"""Elective hardening (commissioned by Volmarr, 2026-11-22): every backend
httpx client is built with ``trust_env=False``.

Background: on a host whose ambient ``NO_PROXY``/``no_proxy`` contains a
bracketed IPv6 entry (e.g. ``[::1]``), httpx raises ``InvalidURL`` while
*constructing* a client that trusts the environment, so backend routes
surface as 500s. Classified 2026-11-14 as an environment case, not an
engine bug; this hardening is defensive — a malformed ambient proxy env
must never crash Rúnmál's clients. The clients all target configured
base URLs directly; none deliberately relies on env proxies.

These tests exercise REAL client construction through the production
default-transport path (no injected transport — with an explicit
transport httpx never parses the proxy env, so such a test would prove
nothing) and real request paths against a real loopback HTTP server.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from runmal.backends.aesir import AesirChatBackend
from runmal.backends.embeddings import (
    AesirEmbeddingBackend,
    OllamaEmbeddingBackend,
    OpenAICompatibleEmbeddingBackend,
)
from runmal.backends.ollama import OllamaChatBackend
from runmal.backends.openai_compat import OpenAICompatibleChatBackend
from runmal.backends.openrouter import OpenRouterChatBackend
from runmal.bridges.bridge_http import HTTPBridgeSource
from runmal.diagnostics.doctor import _default_provider_probe
from runmal.voice.openai_compat import OpenAICompatibleTTSBackend

MALFORMED_NO_PROXY = "[::1],127.0.0.1"
FIX = Path(__file__).parent / "fixtures" / "backends"


@pytest.fixture
def malformed_proxy_env(monkeypatch):
    monkeypatch.setenv("NO_PROXY", MALFORMED_NO_PROXY)
    monkeypatch.setenv("no_proxy", MALFORMED_NO_PROXY)


@pytest.fixture
def loopback_server():
    tags = (FIX / "ollama_tags.json").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server naming
            if self.path in ("/api/tags", "/models"):
                body = tags
            elif self.path.startswith("/api/v1/bridge/chats/"):
                body = json.dumps({"chat_id": "c1", "turns": []}).encode()
            else:
                body = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep the suite quiet
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join(timeout=5)


def test_control_raw_httpx_still_raises(malformed_proxy_env):
    """Control: the malformed env really is malformed in this process —
    an unguarded httpx construction raises, so the tests below are not
    vacuous."""
    with pytest.raises(httpx.InvalidURL):
        httpx.AsyncClient(base_url="http://127.0.0.1:9")


async def test_async_chat_backends_construct(malformed_proxy_env):
    backends = [
        OllamaChatBackend(),
        OpenAICompatibleChatBackend(),
        OpenRouterChatBackend(),
        AesirChatBackend(),
    ]
    try:
        for backend in backends:
            assert backend._client._trust_env is False, type(backend).__name__
    finally:
        for backend in backends:
            await backend._client.aclose()


async def test_embedding_backends_construct(malformed_proxy_env):
    backends = [
        OllamaEmbeddingBackend(),
        AesirEmbeddingBackend(),
        OpenAICompatibleEmbeddingBackend(),
    ]
    try:
        for backend in backends:
            assert backend._client._trust_env is False, type(backend).__name__
    finally:
        for backend in backends:
            await backend._client.aclose()


async def test_ollama_chat_request_path_real_loopback(
    malformed_proxy_env, loopback_server
):
    backend = OllamaChatBackend(base_url=loopback_server)
    try:
        models = await backend.list_models()
    finally:
        await backend._client.aclose()
    assert [m.model_id for m in models] == ["llama3.1", "nomic-embed-text"]


async def test_ollama_embedding_health_real_loopback(
    malformed_proxy_env, loopback_server
):
    backend = OllamaEmbeddingBackend(base_url=loopback_server)
    try:
        health = await backend.health_check()
    finally:
        await backend._client.aclose()
    assert health.ok is True


def test_sync_voice_client_request_path_real_loopback(
    malformed_proxy_env, loopback_server
):
    backend = OpenAICompatibleTTSBackend(base_url=loopback_server)
    try:
        assert backend._client._trust_env is False
        response = backend._client.get("/api/tags")
    finally:
        backend._client.close()
    assert response.status_code == 200


def test_bridge_source_real_loopback(malformed_proxy_env, loopback_server):
    source = HTTPBridgeSource(loopback_server, token="t", chat_id="c1")
    state = source.fetch_state()
    assert state["chat_id"] == "c1"


def test_doctor_probe_real_loopback(malformed_proxy_env, loopback_server):
    ok, detail = _default_provider_probe("ollama", loopback_server)
    assert ok is True, detail
