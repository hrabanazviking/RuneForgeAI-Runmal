"""S703 (roadmap): Aesir embeddings — provenance + FTS fallback contract.

The fixture transport answers the OpenAI-compatible ``POST /embeddings``
surface with deterministic per-text vectors in the recorded response
shape, so the shared embedding contract checks run unchanged. Failure
paths prove the documented degradation: ``embed_or_fallback`` returns
the FTS fallback result — never a crash, never a mixed space (INV-019).
"""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from runmal.backends.embeddings import (
    AesirEmbeddingBackend,
    EmbeddingProvenance,
    FtsFallbackResult,
    check_embedding_contract,
    embed_or_fallback,
)
from runmal.backends.errors import BackendUnavailable
from runmal.backends.profiles import build_embedding_backend, create_profile
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User

DIMS = 8


def _vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [digest[i % len(digest)] / 255.0 for i in range(DIMS)]


def fixture_transport(status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/embeddings"):
            if status >= 400:
                return httpx.Response(status, content=b'{"error": "boom"}')
            body = json.loads(request.content)
            data = [
                {"object": "embedding", "index": i, "embedding": _vector(t)}
                for i, t in enumerate(body.get("input", []))
            ]
            return httpx.Response(
                200,
                content=json.dumps(
                    {"object": "list", "data": data, "model": body.get("model")}
                ).encode(),
            )
        if request.url.path.endswith("/models"):
            return httpx.Response(200, content=b'{"data": []}')
        return httpx.Response(404, content=b"{}")

    return httpx.MockTransport(handler)


def backend(**kw) -> AesirEmbeddingBackend:
    kw.setdefault("transport", fixture_transport())
    return AesirEmbeddingBackend(**kw)


async def test_aesir_embeddings_pass_contract():
    await check_embedding_contract(backend())


async def test_provenance_is_aesir_and_space_isolated():
    b = backend(model="aesir-embed-1")
    result = await b.embed(["hello", "world"])
    prov = result.provenance
    assert prov == EmbeddingProvenance(
        provider="aesir", model="aesir-embed-1", dims=DIMS, version="1"
    )
    assert prov.key() == ("aesir", "aesir-embed-1", DIMS, "1")
    # A different provider with the same dims is a different space (INV-019).
    assert prov.key() != ("ollama", "aesir-embed-1", DIMS, "1")
    info = b.model_info()
    assert info.provider == "aesir" and info.model_id == "aesir-embed-1"
    health = await b.health_check()
    assert health.ok


async def test_wire_shape_and_index_order():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        # Deliberately reversed index order: adapter must restore order.
        data = [
            {"index": 1, "embedding": _vector("world")},
            {"index": 0, "embedding": _vector("hello")},
        ]
        return httpx.Response(200, content=json.dumps({"data": data}).encode())

    b = AesirEmbeddingBackend(model="m", transport=httpx.MockTransport(handler))
    result = await b.embed(["hello", "world"])
    assert captured == {"model": "m", "input": ["hello", "world"]}
    assert list(result.vectors[0]) == _vector("hello")
    assert list(result.vectors[1]) == _vector("world")


async def test_failure_degrades_to_fts_fallback():
    down = backend(transport=fixture_transport(status=503))
    result = await embed_or_fallback(down, ["hello"])
    assert isinstance(result, FtsFallbackResult)
    assert result.degraded and result.mode == "fts" and result.reason

    def connect_fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    unreachable = backend(transport=httpx.MockTransport(connect_fail))
    with pytest.raises(BackendUnavailable):
        await unreachable.embed(["hello"])
    result = await embed_or_fallback(unreachable, ["hello"])
    assert isinstance(result, FtsFallbackResult)
    health = await unreachable.health_check()
    assert not health.ok and "aesir" in health.detail


async def test_profile_builds_aesir_embedding_backend(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        profile = await create_profile(
            session,
            user.id,
            name="aesir-emb",
            chat_backend="fake",
            embedding_backend="aesir",
            embedding_model="aesir-embed-1",
            config={"base_url": "http://127.0.0.1:9000/v1"},
        )
        built = await build_embedding_backend(session, profile)
    assert isinstance(built, AesirEmbeddingBackend)
    assert built.model_info().provider == "aesir"
    assert str(built._client.base_url).rstrip("/") == "http://127.0.0.1:9000/v1"
