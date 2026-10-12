"""Embedding ingestion (S402): chunk -> embed -> store, full provenance.

Fixture documents produce chunk vectors whose every record carries
profile/model/dim/version metadata from the S304 EmbeddingBackend
result provenance (INV-013/INV-019). Chunks are indexed into the S401
vector store under the chunk id and into FTS5 via the memory record.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends.embeddings import EmbeddingBackend
from runmal.memory import service
from runmal.memory.vectorstore import VectorStore


def chunk_text(text: str, *, size: int = 40, overlap: int = 8) -> list[str]:
    """Deterministic word-window chunking (fixed size/overlap)."""
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError("invalid chunk size/overlap")
    words = text.split()
    if not words:
        return []
    chunks = []
    step = size - overlap
    for start in range(0, len(words), step):
        window = words[start:start + size]
        if window:
            chunks.append(" ".join(window))
        if start + size >= len(words):
            break
    return chunks


@dataclass(frozen=True)
class IngestedDocument:
    memory_ids: tuple[str, ...]
    chunk_ids: tuple[str, ...]
    provenance: dict

    def to_dict(self) -> dict:
        return {"memory_ids": list(self.memory_ids), "chunk_ids": list(self.chunk_ids),
                "provenance": self.provenance}


async def ingest_document(
    session: AsyncSession,
    user_id: str,
    backend: EmbeddingBackend,
    store: VectorStore,
    *,
    document_id: str,
    text: str,
    chat_id: str | None = None,
    witnesses: tuple[str, ...] = (),
    scope: str = "user",
    character_id: str | None = None,
    chunk_size: int = 40,
    chunk_overlap: int = 8,
) -> IngestedDocument:
    """Ingest one document: one memory per chunk, all provenance kept."""
    pieces = chunk_text(text, size=chunk_size, overlap=chunk_overlap)
    if not pieces:
        return IngestedDocument((), (), {})
    result = await backend.embed(pieces)
    prov = result.provenance
    memory_ids: list[str] = []
    chunk_ids: list[str] = []
    for index, (piece, vector) in enumerate(zip(pieces, result.vectors, strict=True)):
        memory = await service.create_memory(
            session, user_id, content=piece, kind="episodic",
            scope=scope, witnesses=witnesses, character_id=character_id,
            chat_id=chat_id, embedding=prov.to_dict(),
            extractor={"kind": "ingestion", "document_id": document_id},
            sources=(("document", document_id, chat_id),))
        chunk = await service.add_chunk(session, memory, index, piece, prov)
        store.insert(prov, chunk.id, vector)
        memory_ids.append(memory.id)
        chunk_ids.append(chunk.id)
    return IngestedDocument(tuple(memory_ids), tuple(chunk_ids), prov.to_dict())
