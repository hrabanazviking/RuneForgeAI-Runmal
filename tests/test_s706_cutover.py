"""S706 (roadmap): Aesir cutover hardening.

Acceptance: end-to-end chat + memory run on an Aesir profile through
the seam alone, and no domain code depends on provider identity — the
domain packages contain no provider-key literals at all; provider names
live only in seam-owned registries (the S208 compat profiles and the
S211 connections list), never in domain logic.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import httpx
from sqlalchemy import select

from runmal.backends.aesir import AesirChatBackend
from runmal.backends.embeddings import (
    AesirEmbeddingBackend,
    EmbeddingProvenance,
)
from runmal.backends.messages import ChatMessage
from runmal.backends.profiles import (
    build_chat_backend,
    build_embedding_backend,
    create_profile,
)
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import MemoryChunk, User
from runmal.generation.service import generate_events
from runmal.memory.ingestion import ingest_document
from runmal.memory.vectorstore import InMemoryVectorStore

FIX = Path(__file__).parent / "fixtures" / "backends"
SRC = Path(__file__).parent.parent / "src" / "runmal"
DIMS = 8


def chat_transport() -> httpx.MockTransport:
    sse = (FIX / "aesir_chat.sse").read_bytes()
    models = (FIX / "aesir_models.json").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(200, content=sse, headers={"Content-Type": "text/event-stream"})
        if request.url.path.endswith("/models"):
            return httpx.Response(200, content=models, headers={"Content-Type": "application/json"})
        return httpx.Response(404, content=b"{}")

    return httpx.MockTransport(handler)


def _vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [digest[i % len(digest)] / 255.0 for i in range(DIMS)]


def embedding_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/embeddings"):
            body = json.loads(request.content)
            data = [
                {"object": "embedding", "index": i, "embedding": _vector(t)}
                for i, t in enumerate(body.get("input", []))
            ]
            return httpx.Response(200, content=json.dumps({"data": data}).encode())
        if request.url.path.endswith("/models"):
            return httpx.Response(200, content=b'{"data": []}')
        return httpx.Response(404, content=b"{}")

    return httpx.MockTransport(handler)


async def test_end_to_end_chat_and_memory_on_aesir_profile(tmp_path):
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
            name="aesir-sovereign",
            chat_backend="aesir",
            chat_model="llama-3.1-8b-instruct",
            embedding_backend="aesir",
            embedding_model="aesir-embed-1",
            config={"base_url": "http://127.0.0.1:8000/v1"},
        )
        # The profile resolves to Aesir backends through the builders.
        assert isinstance(await build_chat_backend(session, profile), AesirChatBackend)
        assert isinstance(await build_embedding_backend(session, profile), AesirEmbeddingBackend)

        # Chat: a full generation through the service seam, Aesir surface.
        chat = AesirChatBackend(model="llama-3.1-8b-instruct", transport=chat_transport())
        events = [
            e
            async for e in generate_events(
                "req-706",
                messages=[ChatMessage("user", "greet the hall")],
                backend=chat,
            )
        ]
        tokens = "".join(e["text"] for e in events if e["type"] == "token")
        assert tokens == "Hello from Aesir"
        assert events[-1] == {"type": "done", "finish_reason": "stop"}

        # Memory: ingest with Aesir embeddings, retrieve in the same space.
        embeddings = AesirEmbeddingBackend(model="aesir-embed-1", transport=embedding_transport())
        store = InMemoryVectorStore()
        text = " ".join(f"memory{i}" for i in range(50))
        out = await ingest_document(
            session,
            user.id,
            embeddings,
            store,
            document_id="cutover-doc",
            text=text,
        )
        await session.commit()
        assert out.provenance["provider"] == "aesir"
        chunks = list(await session.scalars(select(MemoryChunk)))
        assert chunks and all(c.provider == "aesir" for c in chunks)

        prov = EmbeddingProvenance("aesir", "aesir-embed-1", DIMS, "1")
        query = await embeddings.embed(["memory1 memory2"])
        hits = store.search(prov, query.vectors[0], top_k=3)
        assert hits, "ingested memory must be retrievable in its own space"
        # Spaces never mix: the same vector under another provider's
        # provenance finds nothing (INV-019).
        foreign = EmbeddingProvenance("ollama", "aesir-embed-1", DIMS, "1")
        assert store.search(foreign, query.vectors[0], top_k=3) == []


_DOMAIN_PACKAGES = (
    "generation",
    "memory",
    "prompt",
    "persona",
    "groupchat",
    "bridge",
    "cards",
    "characters",
    "lorebooks",
    "presets",
)
_PROVIDER_LITERAL = re.compile(r"""["'](ollama|openrouter|aesir)["']""")


def test_no_domain_code_depends_on_provider_identity():
    offenders: dict[str, list[str]] = {}
    files = [SRC / "chats" / "service.py"]
    for pkg in _DOMAIN_PACKAGES:
        files.extend(sorted((SRC / pkg).rglob("*.py")))
    for path in files:
        hits = _PROVIDER_LITERAL.findall(path.read_text(encoding="utf-8"))
        if hits:
            offenders[str(path.relative_to(SRC))] = sorted(set(hits))
    # The single allowed home for a provider name in this set is the
    # S208 compat registry (generation/compat.py), whose declared data IS
    # the per-provider wire profiles — seam machinery, not domain logic.
    # (Its other profile is named for the OpenAI wire shape it maps.)
    assert offenders == {"generation/compat.py": ["ollama"]}, offenders
