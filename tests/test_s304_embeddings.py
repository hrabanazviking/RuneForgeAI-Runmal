"""S304 (roadmap): embedding backend seam + FTS fallback + Ollama /api/embed."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from runmal.backends.embeddings import (
    EmbeddingResult,
    FakeEmbeddingBackend,
    FtsFallbackResult,
    OllamaEmbeddingBackend,
    UnavailableEmbeddingBackend,
    check_embedding_contract,
    embed_or_fallback,
)
from runmal.backends.errors import BackendUnavailable

FIX = Path(__file__).parent / "fixtures" / "backends"


async def test_fake_embedding_contract():
    await check_embedding_contract(FakeEmbeddingBackend())


async def test_fake_provenance_and_determinism():
    b = FakeEmbeddingBackend(dims=4)
    result = await b.embed(["alpha", "beta"])
    assert result.provenance.provider == "fake"
    assert result.provenance.model == "fake-embed-1"
    assert result.provenance.dims == 4
    assert result.provenance.version == "1"
    assert b.model_info().dims == 4


async def test_ollama_embed_fixture_uses_native_endpoint():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["payload"] = json.loads(request.content) if request.content else {}
        if request.url.path == "/api/embed":
            return httpx.Response(
                200, content=(FIX / "ollama_embed.json").read_bytes())
        return httpx.Response(200, content=b'{"models": []}')

    b = OllamaEmbeddingBackend(transport=httpx.MockTransport(handler))
    result = await b.embed(["one", "two"])
    assert captured["path"] == "/api/embed"
    assert captured["payload"] == {"model": "nomic-embed-text",
                                    "input": ["one", "two"]}
    assert result.vectors == ((0.1, 0.2, 0.3), (0.4, 0.5, 0.6))
    assert result.provenance.provider == "ollama"
    assert result.provenance.dims == 3
    assert (await b.health_check()).ok


async def test_unavailable_embeddings_degrade_to_fts_without_crash():
    result = await embed_or_fallback(UnavailableEmbeddingBackend(), ["x"])
    assert isinstance(result, FtsFallbackResult)
    assert result.degraded is True and result.mode == "fts"
    assert result.reason == "backend_unavailable"
    failing = await embed_or_fallback(FakeEmbeddingBackend(fail=True), ["x"])
    assert isinstance(failing, FtsFallbackResult)


async def test_embed_or_fallback_success_path():
    result = await embed_or_fallback(FakeEmbeddingBackend(), ["x"])
    assert isinstance(result, EmbeddingResult)


def test_provenance_keys_distinguish_spaces():
    a = FakeEmbeddingBackend(dims=4, model="m1")
    b = FakeEmbeddingBackend(dims=4, model="m2")
    import asyncio

    pa = asyncio.run(a.embed(["x"])).provenance
    pb = asyncio.run(b.embed(["x"])).provenance
    assert pa.key() != pb.key()
    with pytest.raises(BackendUnavailable):
        asyncio.run(UnavailableEmbeddingBackend().embed(["x"]))
