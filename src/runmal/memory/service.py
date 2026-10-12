"""Memory persistence service (Campaign IV): canonical records + sources.

All writes go through here so provenance is never optional (INV-013).
FTS rows are maintained alongside records for hybrid retrieval (S403).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import Memory, MemoryChunk, MemorySource
from runmal.memory.models import memory_to_dict


def _now() -> datetime:
    return datetime.now(UTC)


async def create_memory(
    session: AsyncSession,
    user_id: str,
    *,
    content: str,
    kind: str = "semantic",
    subject: str = "",
    predicate: str = "",
    state: str = "active",
    salience: float = 0.5,
    stability: float = 0.5,
    pinned: bool = False,
    confidence: float = 1.0,
    scope: str = "user",
    witnesses: tuple[str, ...] | list[str] = (),
    character_id: str | None = None,
    chat_id: str | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    supersedes_id: str | None = None,
    extractor: dict | None = None,
    embedding: dict | None = None,
    sources: tuple[tuple[str, str, str | None], ...] = (),
    memory_id: str | None = None,
) -> Memory:
    m = Memory(
        id=memory_id or str(uuid.uuid4()),
        user_id=user_id,
        kind=kind,
        content=content,
        subject=subject,
        predicate=predicate,
        state=state,
        salience=salience,
        stability=stability,
        pinned=pinned,
        confidence=confidence,
        scope=scope,
        witnesses_json=json.dumps(list(witnesses)),
        character_id=character_id,
        chat_id=chat_id,
        valid_from=valid_from,
        valid_until=valid_until,
        supersedes_id=supersedes_id,
        extractor_json=json.dumps(extractor or {}),
        embedding_json=json.dumps(embedding or {}),
    )
    session.add(m)
    await session.flush()
    for kind_, source_id, src_chat in sources:
        await add_source(session, m.id, kind_, source_id, src_chat)
    await index_fts(session, m)
    return m


async def add_source(
    session: AsyncSession, memory_id: str, source_kind: str, source_id: str,
    chat_id: str | None = None,
) -> None:
    existing = await session.get(MemorySource, (memory_id, source_kind, source_id))
    if existing is None:
        session.add(MemorySource(
            memory_id=memory_id, source_kind=source_kind,
            source_id=source_id, chat_id=chat_id))
        await session.flush()


async def list_sources(session: AsyncSession, memory_id: str) -> list[MemorySource]:
    rows = await session.scalars(
        select(MemorySource).where(MemorySource.memory_id == memory_id)
        .order_by(MemorySource.source_kind, MemorySource.source_id))
    return list(rows)


async def get_memory(session: AsyncSession, user_id: str, memory_id: str) -> Memory | None:
    m = await session.get(Memory, memory_id)
    if m is None or m.user_id != user_id:
        return None
    return m


async def list_memories(
    session: AsyncSession, user_id: str, *, state: str | None = None,
    kind: str | None = None,
) -> list[Memory]:
    q = select(Memory).where(Memory.user_id == user_id)
    if state:
        q = q.where(Memory.state == state)
    if kind:
        q = q.where(Memory.kind == kind)
    rows = await session.scalars(q.order_by(Memory.created_at, Memory.id))
    return list(rows)


async def index_fts(session: AsyncSession, memory: Memory) -> None:
    await session.execute(
        text("DELETE FROM memory_fts WHERE memory_id = :mid"), {"mid": memory.id})
    await session.execute(
        text("INSERT INTO memory_fts (content, memory_id) VALUES (:c, :mid)"),
        {"c": memory.content, "mid": memory.id})


async def delete_memory(session: AsyncSession, user_id: str, memory_id: str) -> bool:
    m = await get_memory(session, user_id, memory_id)
    if m is None:
        return False
    await session.execute(
        text("DELETE FROM memory_fts WHERE memory_id = :mid"), {"mid": memory_id})
    await session.execute(delete(Memory).where(Memory.id == memory_id))
    await session.flush()
    return True


async def add_chunk(
    session: AsyncSession, memory: Memory, chunk_index: int, chunk_text: str,
    provenance,
) -> MemoryChunk:
    chunk = MemoryChunk(
        memory_id=memory.id, chunk_index=chunk_index, text=chunk_text,
        provider=provenance.provider, model=provenance.model,
        dims=provenance.dims, version=provenance.version)
    session.add(chunk)
    await session.flush()
    return chunk


__all__ = [
    "add_chunk", "add_source", "create_memory", "delete_memory", "get_memory",
    "index_fts", "list_memories", "list_sources", "memory_to_dict",
]
