"""Embedding backend seam (S304) — independent from chat (ADR-0001).

Ollama implementation uses the native ``POST /api/embed`` endpoint, verified
against the official Ollama API documentation on 2026-10-12 (audit note in
docs/BACKEND_CONTRACT.md section 12). Every result carries provenance
{provider, model, dims, version}; incompatible spaces must never mix
(INV-019). When embeddings are unavailable, callers degrade to the FTS
fallback contract below — a documented degraded result, never a crash.
"""

from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from runmal.backends.errors import BackendError, BackendUnavailable
from runmal.backends.models import HealthStatus
from runmal.backends.ollama import map_status_error


@dataclass(frozen=True)
class EmbeddingProvenance:
    provider: str
    model: str
    dims: int
    version: str = "1"

    def key(self) -> tuple:
        """Identity of the embedding space; different keys never mix."""
        return (self.provider, self.model, self.dims, self.version)

    def to_dict(self) -> dict:
        return {"provider": self.provider, "model": self.model,
                "dims": self.dims, "version": self.version}


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: tuple[tuple[float, ...], ...]
    provenance: EmbeddingProvenance

    def to_dict(self) -> dict:
        return {"vectors": [list(v) for v in self.vectors],
                "provenance": self.provenance.to_dict()}


@dataclass(frozen=True)
class EmbeddingModelInfo:
    model_id: str
    provider: str
    dims: int
    version: str = "1"

    def to_dict(self) -> dict:
        return {"model_id": self.model_id, "provider": self.provider,
                "dims": self.dims, "version": self.version}


@dataclass(frozen=True)
class FtsFallbackResult:
    """Documented degraded result: retrieval falls back to FTS5/structured."""

    degraded: bool = True
    mode: str = "fts"
    reason: str = ""
    provenance: EmbeddingProvenance | None = None

    def to_dict(self) -> dict:
        return {"degraded": self.degraded, "mode": self.mode,
                "reason": self.reason,
                "provenance": self.provenance.to_dict() if self.provenance else None}


class EmbeddingBackend(ABC):
    backend_key: str = "abstract"

    @abstractmethod
    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """Embed texts; raise BackendError subclasses on failure."""

    @abstractmethod
    def model_info(self) -> EmbeddingModelInfo:
        """Stable metadata for the embedding model."""

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Normalized health status."""


async def embed_or_fallback(
    backend: EmbeddingBackend, texts: list[str]
) -> EmbeddingResult | FtsFallbackResult:
    """Embed, or degrade to the FTS fallback contract without crashing."""
    try:
        return await backend.embed(texts)
    except BackendError as exc:
        return FtsFallbackResult(reason=exc.code)


class UnavailableEmbeddingBackend(EmbeddingBackend):
    backend_key = "unavailable"

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        raise BackendUnavailable("embeddings unavailable")

    def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(model_id="", provider="unavailable", dims=0)

    async def health_check(self) -> HealthStatus:
        return HealthStatus(ok=False, detail="embeddings unavailable")


class FakeEmbeddingBackend(EmbeddingBackend):
    backend_key = "fake"

    def __init__(self, dims: int = 8, model: str = "fake-embed-1",
                 fail: bool = False):
        self._dims = dims
        self._model = model
        self._fail = fail

    def _vector(self, text: str) -> tuple[float, ...]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return tuple(digest[i % len(digest)] / 255.0 for i in range(self._dims))

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if self._fail:
            raise BackendUnavailable("fake embeddings configured to fail")
        return EmbeddingResult(
            vectors=tuple(self._vector(t) for t in texts),
            provenance=EmbeddingProvenance(
                provider="fake", model=self._model, dims=self._dims, version="1"))

    def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(model_id=self._model, provider="fake",
                                   dims=self._dims, version="1")

    async def health_check(self) -> HealthStatus:
        return HealthStatus(ok=not self._fail, detail="fake embeddings")


class OllamaEmbeddingBackend(EmbeddingBackend):
    """Ollama embeddings via native POST /api/embed (verified 2026-10-12)."""

    backend_key = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434",
                 model: str = "nomic-embed-text",
                 client: httpx.AsyncClient | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 timeout_s: float = 60.0):
        self._model = model
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout_s, transport=transport)

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        try:
            resp = await self._client.post(
                "/api/embed", json={"model": self._model, "input": texts})
        except httpx.ConnectError as exc:
            raise BackendUnavailable("ollama unreachable") from exc
        if resp.status_code >= 400:
            raise map_status_error(resp.status_code, resp.text)
        vectors = tuple(tuple(float(x) for x in v)
                        for v in resp.json().get("embeddings", []))
        dims = len(vectors[0]) if vectors else 0
        return EmbeddingResult(
            vectors=vectors,
            provenance=EmbeddingProvenance(
                provider="ollama", model=self._model, dims=dims, version="1"))

    def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(model_id=self._model, provider="ollama", dims=0)

    async def health_check(self) -> HealthStatus:
        start = time.monotonic()
        try:
            resp = await self._client.get("/api/tags")
        except Exception as exc:  # health reports, never raises
            return HealthStatus(ok=False,
                                detail=f"ollama unreachable: {type(exc).__name__}")
        latency = (time.monotonic() - start) * 1000
        ok = resp.status_code < 400
        return HealthStatus(ok=ok, detail="ollama embeddings reachable" if ok
                            else f"ollama HTTP {resp.status_code}",
                            latency_ms=latency)


async def check_embedding_contract(backend: EmbeddingBackend) -> None:
    """Reusable contract checks for embedding backends."""
    info = backend.model_info()
    assert info.model_id and info.provider
    result = await backend.embed(["hello", "world"])
    assert len(result.vectors) == 2
    prov = result.provenance
    assert prov.provider and prov.model and prov.dims == len(result.vectors[0])
    assert all(len(v) == prov.dims for v in result.vectors)
    again = await backend.embed(["hello"])
    assert again.vectors[0] == result.vectors[0], "embeddings must be deterministic"
    health = await backend.health_check()
    assert isinstance(health.ok, bool)
